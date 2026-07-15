# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The lookup boundary is loud: misses raise by default, and invalid inputs
error instead of silently returning wrong rates.

Covers the F3/F5 audit cluster:
- F3: missing keys raise under the default ``on_missing="raise"``; NaN and
  constant-fill behaviour are explicit opt-ins.
- F5a: null and narrow-integer keys miss (or widen) instead of aliasing to
  the hash bucket of key 0 and returning key 0's rate.
- F5b: duplicate key rows in the source error at build time (matching the
  append path) instead of silently last-write-winning.
- F5c: ragged inner key lists across vector key columns error instead of
  silently misaligning every subsequent policy's rates.
"""

import math

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table


def _age_table(name: str, storage_mode: str = "auto", **kwargs) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage_mode,
        **kwargs,
    )


# --- F3: on_missing policy -------------------------------------------------


@pytest.mark.parametrize("storage_mode", ["auto", "hash"])
@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_miss_raises_by_default(storage_mode: str, engine: str) -> None:
    table = _age_table(f"boundary_raise_{storage_mode}_{engine}", storage_mode)
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3], "age": [40, 35, 30]}))
    af.rate = table.lookup(age=af.age)
    with pytest.raises(pl.exceptions.ComputeError, match="missing"):
        af.collect(engine=engine)


def test_miss_error_names_table_and_keys() -> None:
    table = _age_table("boundary_named")
    af = ActuarialFrame(pl.DataFrame({"age": [35]}))
    af.rate = table.lookup(age=af.age)
    with pytest.raises(pl.exceptions.ComputeError, match="boundary_named"):
        af.collect()


def test_miss_raises_for_list_keys() -> None:
    table = _age_table("boundary_raise_list")
    af = ActuarialFrame(pl.DataFrame({"ages": [[30, 40], [40, 35]]}))
    af.rates = table.lookup(age=af.ages)
    with pytest.raises(pl.exceptions.ComputeError, match="missing"):
        af.collect()


def test_on_missing_nan_restores_silent_behaviour() -> None:
    table = _age_table("boundary_nan", on_missing="nan")
    af = ActuarialFrame(pl.DataFrame({"age": [40, 35, 30]}))
    af.rate = table.lookup(age=af.age)
    out = af.collect()
    assert out["rate"][0] == pytest.approx(0.002)
    assert math.isnan(out["rate"][1])
    assert out["rate"][2] == pytest.approx(0.001)


def test_on_missing_constant_fills() -> None:
    table = _age_table("boundary_fill", on_missing=0.5)
    af = ActuarialFrame(pl.DataFrame({"age": [40, 35]}))
    af.rate = table.lookup(age=af.age)
    out = af.collect()
    assert out["rate"].to_list() == pytest.approx([0.002, 0.5])


def test_on_missing_constant_fills_list_output() -> None:
    table = _age_table("boundary_fill_list", on_missing=0.0)
    af = ActuarialFrame(pl.DataFrame({"ages": [[30, 35], [40, 99]]}))
    af.rates = table.lookup(age=af.ages)
    out = af.collect()
    assert out["rates"].to_list()[0] == pytest.approx([0.001, 0.0])
    assert out["rates"].to_list()[1] == pytest.approx([0.002, 0.0])


def test_lookup_override_beats_table_default() -> None:
    table = _age_table("boundary_override", on_missing="nan")
    af = ActuarialFrame(pl.DataFrame({"age": [35]}))
    af.rate = table.lookup(age=af.age, on_missing="raise")
    with pytest.raises(pl.exceptions.ComputeError, match="missing"):
        af.collect()


def test_complete_keys_do_not_raise() -> None:
    table = _age_table("boundary_complete")
    af = ActuarialFrame(pl.DataFrame({"age": [30, 40, 50]}))
    af.rate = table.lookup(age=af.age)
    assert af.collect()["rate"].to_list() == pytest.approx([0.001, 0.002, 0.003])


def test_invalid_on_missing_rejected() -> None:
    with pytest.raises(ValueError, match="on_missing"):
        _age_table("boundary_invalid", on_missing="explode")


# --- F5a: null / narrow-int keys must not alias ------------------------------


def test_null_key_misses_instead_of_aliasing() -> None:
    # Hash storage: a null key hashed to the same bucket as key 0 and
    # returned key 0's rate. It must be a miss.
    table = Table(
        name="boundary_null_alias",
        source=pl.DataFrame({"age": [0, 40], "rate": [0.111, 0.002]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode="hash",
        on_missing="nan",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [None, 40]}))
    af.rate = table.lookup(age=af.age)
    out = af.collect()
    assert math.isnan(out["rate"][0]), f"null key returned {out['rate'][0]!r}"
    assert out["rate"][1] == pytest.approx(0.002)


@pytest.mark.parametrize("dtype", [pl.Int8, pl.Int16, pl.UInt8, pl.UInt16])
def test_narrow_int_keys_widen_and_match(dtype: pl.DataType) -> None:
    # Narrow-int keys fell into the codec catch-all and either aliased to
    # key 0 or missed entirely. They must widen and match.
    table = Table(
        name=f"boundary_narrow_{dtype}",
        source=pl.DataFrame({"age": [0, 7], "rate": [0.111, 0.777]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode="hash",
    )
    af = ActuarialFrame(
        pl.DataFrame({"age": pl.Series([7], dtype=dtype)})
    )
    af.rate = table.lookup(age=af.age)
    assert af.collect()["rate"].to_list() == pytest.approx([0.777])


# --- F5b: duplicate key rows error at build ---------------------------------


@pytest.mark.parametrize("storage_mode", ["auto", "hash"])
def test_duplicate_key_rows_error_at_build(storage_mode: str) -> None:
    with pytest.raises(Exception, match="[Dd]uplicate"):
        Table(
            name=f"boundary_dup_{storage_mode}",
            source=pl.DataFrame({"age": [40, 40], "rate": [0.41, 0.42]}),
            dimensions={"age": "age"},
            value="rate",
            storage_mode=storage_mode,
        )


# --- F5c: ragged inner key lists error --------------------------------------


@pytest.mark.parametrize("storage_mode", ["auto", "hash"])
def test_ragged_inner_key_lists_error(storage_mode: str) -> None:
    table = Table(
        name=f"boundary_ragged_{storage_mode}",
        source=pl.DataFrame(
            {
                "age": [30, 30, 30, 31, 31, 31],
                "dur": [0, 1, 2, 0, 1, 2],
                "rate": [30.0, 30.001, 30.002, 31.0, 31.001, 31.002],
            }
        ),
        dimensions={"age": "age", "dur": "dur"},
        value="rate",
        storage_mode=storage_mode,
    )
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "age": [[30, 30], [31, 31]],
                "dur": [[0, 1, 2], [0]],
            }
        )
    )
    af.rate = table.lookup(age=af.age, dur=af.dur)
    with pytest.raises(pl.exceptions.ComputeError, match="length|ragged"):
        af.collect()


# --- F3: prospective_value must not zero NaN --------------------------------


def test_prospective_value_propagates_nan() -> None:
    af = ActuarialFrame({"cashflow": [[10.0, float("nan"), 10.0]]})
    af.pv = af.cashflow.projection.prospective_value(discount_rate=0.0)
    pv = af.collect()["pv"][0].to_list()
    assert math.isnan(pv[0]), "NaN cashflow was silently zeroed in PV(0)"
    assert math.isnan(pv[1]), "NaN cashflow was silently zeroed in PV(1)"
    assert pv[2] == pytest.approx(10.0)
