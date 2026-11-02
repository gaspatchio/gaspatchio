# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One query against one table gives one answer, whichever storage it got.

A table is stored as an array where its keys are dense enough and as a hash
map otherwise, on request or by fallback, and the model never sees which. So
the answer cannot depend on it: a hit is the same rate, a miss goes to the
same ``on_missing`` policy, and a refusal is the same refusal.

The two storages used to disagree across the key families. Hash storage read
a number against a text table by hashing the number's decimal spelling, so
``5`` found the row keyed ``"5"`` where array storage missed; and it hashed a
categorical or Enum key by its dictionary index, so a label the table held
missed where array storage found it. Both now answer as array storage does,
and a key whose family -- text or number -- is not its dimension's is refused
by name when the lookup is written, before either storage is asked.

The matrix: four tables (text labels, numbers, digits declared text, digits
judged as numbers) by five key encodings (text, categorical, Enum, integer,
float), through a frame -- where the key is typed and a cross-family key is
refused -- and through a bare Polars expression, where no frame types the key
and the kernel decides it, as a miss.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import DataDimension, Table

if TYPE_CHECKING:
    from collections.abc import Callable

_STORAGES = ("array", "hash")
_KEY_ENCODINGS = ("text", "categorical", "enum", "integer", "float")
_TEXT_ENCODINGS = frozenset({"text", "categorical", "enum"})


@dataclass(frozen=True, slots=True)
class _Kind:
    """A table shape, and the two keys it holds spelled as text and as numbers."""

    cells: list[str] | list[int]
    declared_text: bool
    holds_text: bool
    text_keys: list[str]
    number_keys: list[int]


_KINDS = {
    "labels": _Kind(
        cells=["M", "F"],
        declared_text=False,
        holds_text=True,
        text_keys=["F", "M"],
        number_keys=[2, 1],
    ),
    "numbers": _Kind(
        cells=[40, 41],
        declared_text=False,
        holds_text=False,
        text_keys=["41", "40"],
        number_keys=[41, 40],
    ),
    "declared_digits": _Kind(
        cells=["1", "5"],
        declared_text=True,
        holds_text=True,
        text_keys=["5", "1"],
        number_keys=[5, 1],
    ),
    "judged_digits": _Kind(
        cells=["1", "5"],
        declared_text=False,
        holds_text=False,
        text_keys=["5", "1"],
        number_keys=[5, 1],
    ),
}

# Every table holds 0.1 at its first key and 0.2 at its second; every query
# reads the second, then the first.
_HIT = [0.2, 0.1]


def _table(kind: str, storage: str, on_missing: str | float, tag: str) -> Table:
    spec = _KINDS[kind]
    dimension: str | DataDimension = (
        DataDimension(column="k", dtype=pl.String) if spec.declared_text else "k"
    )
    return Table(
        name=f"agreement_{tag}_{kind}_{storage}_{on_missing}",
        source=pl.DataFrame({"k": spec.cells, "q": [0.1, 0.2]}),
        dimensions={"k": dimension},
        value="q",
        storage_mode=storage,
        on_missing=on_missing,
    )


def _keys(kind: str, encoding: str) -> pl.Series:
    spec = _KINDS[kind]
    match encoding:
        case "text":
            return pl.Series("s", spec.text_keys)
        case "categorical":
            return pl.Series("s", spec.text_keys, dtype=pl.Categorical)
        case "enum":
            return pl.Series("s", spec.text_keys, dtype=pl.Enum(spec.text_keys))
        case "integer":
            return pl.Series("s", spec.number_keys, dtype=pl.Int64)
        case _:
            return pl.Series("s", spec.number_keys, dtype=pl.Float64)


def _same_family(kind: str, encoding: str) -> bool:
    return _KINDS[kind].holds_text == (encoding in _TEXT_ENCODINGS)


def _outcome(read: Callable[[], list[float]]) -> tuple[str, object]:
    """Run one read and name what it gave: values (NaN as None), or the error."""
    try:
        values = read()
    except (TypeError, pl.exceptions.ComputeError) as exc:
        return ("refused", type(exc).__name__)
    return ("values", [None if math.isnan(v) else v for v in values])


@pytest.mark.parametrize("encoding", _KEY_ENCODINGS)
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_through_a_frame_both_storages_agree_and_a_cross_family_key_is_refused(
    kind: str, encoding: str
) -> None:
    def read(storage: str) -> list[float]:
        table = _table(kind, storage, "nan", "frame")
        af = ActuarialFrame(pl.DataFrame(_keys(kind, encoding)))
        af.q = table.lookup(k=af.s)
        return af.collect()["q"].to_list()

    outcomes = {storage: _outcome(lambda s=storage: read(s)) for storage in _STORAGES}

    assert outcomes["array"] == outcomes["hash"], outcomes
    expected = (
        ("values", _HIT) if _same_family(kind, encoding) else ("refused", "TypeError")
    )
    assert outcomes["array"] == expected


@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.0])
@pytest.mark.parametrize("encoding", _KEY_ENCODINGS)
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_with_no_frame_to_type_the_key_both_storages_agree(
    kind: str, encoding: str, on_missing: str | float
) -> None:
    """A bare Polars key reaches the kernel; a cross-family key is a miss there."""

    def read(storage: str) -> list[float]:
        table = _table(kind, storage, on_missing, "bare")
        frame = pl.DataFrame(_keys(kind, encoding))
        return frame.select(table.lookup(k=pl.col("s")).alias("q"))["q"].to_list()

    outcomes = {storage: _outcome(lambda s=storage: read(s)) for storage in _STORAGES}

    assert outcomes["array"] == outcomes["hash"], outcomes
    if _same_family(kind, encoding):
        assert outcomes["array"] == ("values", _HIT)
    elif on_missing == "raise":
        assert outcomes["array"] == ("refused", "ComputeError")
    else:
        miss = None if on_missing == "nan" else on_missing
        assert outcomes["array"] == ("values", [miss, miss])


def test_a_number_against_a_text_dimension_names_the_move() -> None:
    table = _table("labels", "auto", "raise", "message")
    af = ActuarialFrame(pl.DataFrame({"sex_code": [1.0, 2.0]}))

    with pytest.raises(TypeError) as caught:
        table.lookup(k=af.sex_code)

    message = str(caught.value)
    assert "dimension 'k' with a number" in message
    assert "pl.col('sex_code').cast(pl.Int64).cast(pl.String)" in message


def test_a_number_against_a_declared_text_dimension_names_the_declaration() -> None:
    table = _table("declared_digits", "auto", "raise", "message")

    with pytest.raises(TypeError) as caught:
        table.lookup(k=5)

    message = str(caught.value)
    assert "declared text" in message
    assert "drop dtype=pl.String" in message


def test_a_per_period_number_against_a_text_dimension_is_refused() -> None:
    table = _table("labels", "auto", "raise", "per_period")
    af = ActuarialFrame(pl.DataFrame({"code": [[1, 2]]}))

    with pytest.raises(TypeError, match="with a number"):
        table.lookup(k=af.code)
