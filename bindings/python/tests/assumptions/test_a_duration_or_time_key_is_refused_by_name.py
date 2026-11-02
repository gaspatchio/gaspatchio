# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table keyed on a duration or a time of day is refused by name.

The content grammar names a date and an instant (section 12.3), and a table
keyed on either is fingerprinted as the dates or instants it holds. It names
no duration and no time of day, so a table keyed on one was fingerprinted by
the bare count of its unit: a five-millisecond duration key shared a
fingerprint with the integer five, with five microseconds and with five
nanoseconds. Every other door that hashes a column refuses those types by
name; a table now does too, at every route that builds one, and the refusal
names the move -- key on a whole number of the unit you mean, or on a date.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.assumptions import Table, TableBuilder
from gaspatchio.assumptions._dimensions import ComputedDimension
from gaspatchio.assumptions._processing import content_fingerprint_of
from gaspatchio.scenarios import MultiplicativeShock
from gaspatchio.scenarios._stack import shocked_table, stack_shocked_table

if TYPE_CHECKING:
    from collections.abc import Callable

_COUNT = iter(range(10_000))

_KEYS: dict[str, pl.Series] = {
    "duration ms": pl.Series("k", [5, 10], dtype=pl.Int64).cast(pl.Duration("ms")),
    "duration us": pl.Series("k", [5, 10], dtype=pl.Int64).cast(pl.Duration("us")),
    "duration ns": pl.Series("k", [5, 10], dtype=pl.Int64).cast(pl.Duration("ns")),
    "time of day": pl.Series("k", [dt.time(9), dt.time(17)]),
}
_REFUSED = r"key column 'k' holds .*whole number of the unit you mean.* or on a date"


def _name() -> str:
    return f"l1_duration_key_{next(_COUNT)}"


def _source(keys: pl.Series) -> pl.DataFrame:
    return pl.DataFrame({"k": keys, "v": [0.01, 0.02]})


@pytest.mark.parametrize("kind", list(_KEYS))
def test_a_table_keyed_on_it_is_refused(kind: str) -> None:
    with pytest.raises(ValueError, match=_REFUSED):
        Table(_name(), _source(_KEYS[kind]), {"k": "k"}, "v")


@pytest.mark.parametrize("kind", list(_KEYS))
def test_a_table_builder_keyed_on_it_is_refused(kind: str) -> None:
    builder = TableBuilder(_name()).from_source(_source(_KEYS[kind]))
    with pytest.raises(ValueError, match=_REFUSED):
        builder.with_data_dimension("k", "k").with_value_column("v").build()


def test_a_computed_dimension_that_makes_one_is_refused() -> None:
    computed = ComputedDimension(pl.duration(milliseconds=pl.col("ms")), "k")
    source = pl.DataFrame({"ms": [5, 10], "v": [0.01, 0.02]})
    with pytest.raises(ValueError, match=_REFUSED):
        Table(_name(), source, {"k": computed}, "v")


@pytest.mark.parametrize("kind", list(_KEYS))
@pytest.mark.parametrize(
    "held",
    [
        pl.Series("k", [1, 2]),
        pl.Series("k", [dt.date(2025, 1, 1), dt.date(2025, 1, 2)]),
    ],
    ids=["numbers", "dates"],
)
def test_an_extension_slice_keyed_on_it_is_refused(kind: str, held: pl.Series) -> None:
    table = Table(_name(), _source(held), {"k": "k"}, "v")
    before = table.fingerprint()
    with pytest.raises(ValueError, match=_REFUSED):
        table.extend(_source(_KEYS[kind]))
    assert table.fingerprint() == before


@pytest.mark.parametrize("kind", list(_KEYS))
def test_a_reread_of_a_file_keyed_on_it_is_refused(kind: str) -> None:
    with pytest.raises(ValueError, match=_REFUSED):
        content_fingerprint_of(_source(_KEYS[kind]), {"k": "k"}, "v")


_COPIES: dict[str, Callable[[Table], object]] = {
    "with_shock": lambda base: base.with_shock(MultiplicativeShock(factor=1.1)),
    "from_shocks": lambda base: Table.from_shocks(
        base, {"up": [MultiplicativeShock(factor=1.1)], "base": []}, "v"
    ),
    "shocked_table": lambda base: shocked_table(
        base, [MultiplicativeShock(factor=1.1)]
    ),
    "stack_shocked_table": lambda base: stack_shocked_table(
        base, {"up": [MultiplicativeShock(factor=1.1)], "base": []}
    ),
}


@pytest.mark.parametrize("route", list(_COPIES))
def test_a_copy_rebuilt_in_that_kind_is_refused(route: str) -> None:
    """A copy is rebuilt through the same door, so it cannot carry one either.

    No table holds such a key any more, so the base here is handed the kind
    after it was built: the copy restores its key in the kind kept beside the
    base, and the construction it goes through refuses it by name.
    """
    base = Table(_name(), _source(pl.Series("k", [5, 10])), {"k": "k"}, "v")
    base._key_kinds = {"k": pl.Duration("ms")}  # noqa: SLF001 - the kind a copy restores
    with pytest.raises(ValueError, match=_REFUSED):
        _COPIES[route](base)


def test_a_whole_number_of_the_unit_and_a_date_still_key_a_table() -> None:
    """The moves the refusal names build, and answer distinct fingerprints."""
    counts = Table(_name(), _source(pl.Series("k", [5, 10])), {"k": "k"}, "v")
    dates = Table(
        _name(),
        _source(pl.Series("k", [dt.date(1970, 1, 6), dt.date(1970, 1, 11)])),
        {"k": "k"},
        "v",
    )
    assert counts.fingerprint() != dates.fingerprint()
