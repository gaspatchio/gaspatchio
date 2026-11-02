# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The lookup boundary is loud: misses raise by default, and invalid inputs
error instead of silently returning wrong rates.

Covers the ways a lookup used to answer wrongly without saying so:
- missing keys raise under the default ``on_missing="raise"``; NaN and
  constant-fill behaviour are explicit opt-ins.
- null and narrow-integer keys miss (or widen) instead of aliasing to
  the hash bucket of key 0 and returning key 0's rate.
- duplicate key rows in the source error at build time (matching the
  append path) instead of silently last-write-winning.
- ragged inner key lists across vector key columns error instead of
  silently misaligning every subsequent policy's rates.
"""

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


def _age_table(name: str, storage_mode: str = "auto", **kwargs) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage_mode,
        **kwargs,
    )


# --- on_missing policy -----------------------------------------------------


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


# --- null / narrow-int keys must not alias -----------------------------------


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


@pytest.mark.parametrize("storage_mode", ["auto", "hash"])
@pytest.mark.parametrize("dtype", [pl.Int8, pl.Int16, pl.UInt8, pl.UInt16])
def test_narrow_int_keys_widen_and_match(dtype: pl.DataType, storage_mode: str) -> None:
    # Narrow-int keys fell into the hash codec catch-all (aliasing to key 0)
    # and had no KeyEncoder arms on the array path (missing entirely). They
    # must widen and match on both storage backends.
    table = Table(
        name=f"boundary_narrow_{dtype}_{storage_mode}",
        source=pl.DataFrame({"age": [0, 7], "rate": [0.111, 0.777]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage_mode,
    )
    af = ActuarialFrame(pl.DataFrame({"age": pl.Series([7], dtype=dtype)}))
    af.rate = table.lookup(age=af.age)
    assert af.collect()["rate"].to_list() == pytest.approx([0.777])


# --- duplicate key rows error at build --------------------------------------


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


# --- ragged inner key lists error -------------------------------------------


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


# --- prospective_value must not zero NaN ------------------------------------


def test_prospective_value_propagates_nan() -> None:
    af = ActuarialFrame({"cashflow": [[10.0, float("nan"), 10.0]]})
    af.pv = af.cashflow.projection.prospective_value(discount_rate=0.0)
    pv = af.collect()["pv"][0].to_list()
    assert math.isnan(pv[0]), "NaN cashflow was silently zeroed in PV(0)"
    assert math.isnan(pv[1]), "NaN cashflow was silently zeroed in PV(1)"
    assert pv[2] == pytest.approx(10.0)


# --- the refusal's first line is the stable part ------------------------------
#
# The collect-time replay names a calculation only when its replayed error
# opens with the same first line the original did. The count and the
# sampled keys vary with the batch -- the streaming collect counts the batch
# it was handed, the replay counts the head it was given -- so they sit on
# the second line, and the first names only the table and the key columns.


_PREFIX = "the plugin failed with message: "


def _first_line(message: str) -> str:
    return message.split("\n", 1)[0]


def _scattered_miss(name: str, engine: str) -> str:
    """Fifty thousand policies, three at an age the table lacks, spread out."""
    table = _age_table(name)
    ages = [40] * 50_000
    for row in (100, 25_000, 49_000):
        ages[row] = 99
    af = ActuarialFrame(pl.DataFrame({"policy_id": list(range(50_000)), "age": ages}))
    af.rate = table.lookup(age=af.age)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect(engine=engine)
    return str(caught.value)


def test_the_refusals_first_line_is_identical_under_both_engines() -> None:
    """Streaming counts a batch, in-memory the frame; line one knows neither."""
    streaming = _scattered_miss("boundary_first_line", "streaming")
    in_memory = _scattered_miss("boundary_first_line", "in-memory")

    assert _first_line(streaming) == _first_line(in_memory)
    assert _first_line(streaming) == (
        _PREFIX
        + "Lookup on table 'boundary_first_line' has missing keys (or NaN-valued "
        "entries) for key column 'age'."
    )
    for message in (streaming, in_memory):
        second_line = message.split("\n", 1)[1]
        assert second_line.startswith("Missed keys (first 3 distinct): (age=99)")


def test_the_first_line_names_every_key_column_of_a_multi_key_lookup() -> None:
    table = Table(
        name="boundary_two_keys",
        source=pl.DataFrame(
            {"age": [30, 40], "duration": [0, 0], "rate": [0.001, 0.002]}
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [30, 99], "duration": [0, 0]}))
    af.rate = table.lookup(age=af.age, duration=af.duration)

    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()

    assert _first_line(str(caught.value)) == (
        _PREFIX + "Lookup on table 'boundary_two_keys' has missing keys (or NaN-valued "
        "entries) for key columns 'age', 'duration'."
    )


def test_an_enum_key_on_a_hash_table_answers_rather_than_refusing() -> None:
    """The encoding refusal this boundary once split is no longer raised.

    Hash storage hashed an Enum key by its dictionary position and refused,
    naming the encoding; it now reads the label, as array storage does.
    """
    table = Table(
        name="boundary_encoding_line",
        source=pl.DataFrame({"fund": ["A", "B"], "rate": [0.1, 0.2]}),
        dimensions={"fund": "fund"},
        value="rate",
        storage_mode="hash",
    )
    labels = pl.Series(["B", "A"], dtype=pl.Enum(["A", "B"]))
    af = ActuarialFrame(pl.DataFrame({"fund": labels}))
    af.rate = table.lookup(fund=af.fund)

    assert af.collect()["rate"].to_list() == [0.2, 0.1]


def test_dimension_mapping_does_not_become_validation_control_arguments() -> None:
    table = Table(
        "dimension_named_like_mapping_parameter",
        pl.DataFrame({"raw_age": [30], "rate": [0.125]}),
        dimensions={"_dimensions": "raw_age"},
    )
    expression = table.lookup(_dimensions={"_dimensions": pl.lit(30)})
    assert pl.select(expression).item() == 0.125
