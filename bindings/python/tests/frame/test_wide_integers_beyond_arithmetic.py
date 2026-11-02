# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column still wider than ``i64`` is refused by every fold that would wrap it.

Section 10 reads a ``UInt64``, ``Int128`` or ``UInt128`` column as the ``Int64``
its values fit, keeps the width of one holding a value past that range, and
refuses arithmetic on it by name. Arithmetic was not the only read computing
in that width:

- a sum, a running sum or product and a remaining sum folded in it --
  ``[2**63, 2**63, 1]`` of a ``UInt64`` summed to 1 and ran to ``[2**63, 0, 1]``;
- an absolute value of a signed one wraps at the type's least value --
  ``abs(-2**127)`` of an ``Int128`` answered ``-2**127``;
- ``run_aggregated``'s ``Sum`` added a batch in it -- 7 and 2**64 - 1 summed
  to 6.

Each is now refused by name in the sentence arithmetic is, and reads a column
whose values fit as the ``Int64`` they are, whichever door the book came in
by. An unsigned column is its own absolute value and keeps its width.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import Max, Sum, run_aggregated

if TYPE_CHECKING:
    from collections.abc import Callable

_WIDE = [pl.UInt64, pl.Int128, pl.UInt128]
_PAST = {pl.UInt64: 2**64 - 1, pl.Int128: -(2**70), pl.UInt128: 2**64 - 1}


def _book(width: type[pl.DataType], ids: list[list[int]]) -> pl.DataFrame:
    return pl.DataFrame({"ids": pl.Series(ids, dtype=pl.List(width))})


def _door(book: pl.DataFrame, door: str) -> ActuarialFrame:
    return ActuarialFrame(book if door == "DataFrame" else book.lazy())


# Each fold, with the words it is refused in and its hand value over the
# fitting run [[1, 2, 3], [4, 5, 6]].
_FOLDS: list[tuple[str, Callable[[Any], Any], str, list[object]]] = [
    ("list.sum()", lambda af: af.ids.list.sum(), "its sum is refused", [6, 15]),
    (
        "cum_sum()",
        lambda af: af.ids.cum_sum(),
        "a running sum of it is refused",
        [[1, 3, 6], [4, 9, 15]],
    ),
    (
        "cum_sum(reverse=True)",
        lambda af: af.ids.cum_sum(reverse=True),
        "a running sum of it is refused",
        [[6, 5, 3], [15, 11, 6]],
    ),
    (
        "cum_prod()",
        lambda af: af.ids.cum_prod(),
        "a running product of it is refused",
        [[1, 2, 6], [4, 20, 120]],
    ),
    (
        "projection.remaining_sum()",
        lambda af: af.ids.projection.remaining_sum(),
        "a remaining sum of it is refused",
        [[6, 5, 3], [15, 11, 6]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "refused", "fitting"), _FOLDS, ids=[f[0] for f in _FOLDS]
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_fold_over_a_value_past_i64_is_refused_by_name(  # noqa: PLR0913, PLR0917 -- the fold, its words, and where the book came in
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    refused: str,
    fitting: list[object],  # noqa: ARG001 -- the next test's
    door: str,
    width: type[pl.DataType],
) -> None:
    af = _door(_book(width, [[1, 2, 3], [_PAST[width], 5, 6]]), door)
    af.r = line(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    message = str(caught.value)
    assert message.startswith(
        "Column 'ids' holds a whole number outside the signed 64-bit range, and "
        f"{refused}."
    )
    assert "af.ids.to_text()" in message
    assert "narrower type" in message


@pytest.mark.parametrize(
    ("written", "line", "refused", "fitting"), _FOLDS, ids=[f[0] for f in _FOLDS]
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_fold_over_a_wide_run_that_fits_answers_in_int64(  # noqa: PLR0913, PLR0917 -- as above
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    refused: str,  # noqa: ARG001 -- the previous test's
    fitting: list[object],
    door: str,
    width: type[pl.DataType],
) -> None:
    af = _door(_book(width, [[1, 2, 3], [4, 5, 6]]), door)
    af.r = line(af)
    out = af.collect()

    assert out["r"].to_list() == fitting
    assert out.schema["r"] in {pl.Int64, pl.List(pl.Int64)}


def test_a_lazily_handed_sum_past_i64_is_refused_as_the_eager_door_s_is() -> None:
    """One width whichever door: 2**62 + 2**62 + 1 is past i64 on both, alike.

    Read as ``Int64`` on both doors, the total has no ``i64`` and is refused
    by name on both; computed in ``UInt64`` on the lazy one it answered
    9223372036854775809, a number the eager door never gave, and the eager
    door wrapped it.
    """
    book = _book(pl.UInt64, [[2**62, 2**62, 1]])
    for door in ("DataFrame", "LazyFrame"):
        af = _door(book, door)
        af.r = af.ids.list.sum()
        with pytest.raises(
            pl.exceptions.InvalidOperationError,
            match="Column 'ids' holds whole numbers whose sum lies outside",
        ):
            af.collect()


@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_the_absolute_value_of_a_signed_column_past_i64_is_refused(door: str) -> None:
    book = pl.DataFrame({"pid": pl.Series([-7, -(2**70)], dtype=pl.Int128)})
    af = _door(book, door)
    af.r = af.pid.abs()

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    assert str(caught.value).startswith(
        "Column 'pid' holds a whole number outside the signed 64-bit range, and "
        "its absolute value is refused."
    )


def test_the_absolute_value_of_int128_s_least_value_no_longer_wraps() -> None:
    """``abs(-2**127)`` answered ``-2**127`` in the column's own width."""
    book = pl.DataFrame({"pid": pl.Series([-(2**127), 5], dtype=pl.Int128)})
    af = ActuarialFrame(book)
    af.r = af.pid.abs()

    with pytest.raises(pl.exceptions.InvalidOperationError, match="absolute value"):
        af.collect()


@pytest.mark.parametrize("width", [pl.UInt64, pl.UInt128], ids=str)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_an_unsigned_column_past_i64_is_refused_as_any_carrying_read_is(
    width: type[pl.DataType], door: str
) -> None:
    """An unsigned value is its own absolute value, but the answer is in its width.

    It kept the width on both doors where a value did not fit, and on the
    LazyFrame door where every value did -- where the DataFrame door answered
    Int64. It is now read as every operation carrying its operand's type
    reads such a column: as Int64 where its values fit, refused where not.
    """
    book = pl.DataFrame({"pid": pl.Series([7, 2**64 - 1], dtype=width)})
    af = _door(book, door)
    af.r = af.pid.abs()

    with pytest.raises(pl.exceptions.InvalidOperationError, match="carrying it"):
        af.collect()


@pytest.mark.parametrize("width", [pl.UInt64, pl.UInt128], ids=str)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_an_unsigned_column_that_fits_is_its_own_absolute_value_as_int64(
    width: type[pl.DataType], door: str
) -> None:
    book = pl.DataFrame({"pid": pl.Series([7, 8], dtype=width)})
    af = _door(book, door)
    af.r = af.pid.abs()
    out = af.collect()

    assert out["r"].to_list() == [7, 8]
    assert out.schema["r"] == pl.Int64


def _passenger(af: ActuarialFrame) -> ActuarialFrame:
    af.r = af.amt * 2
    return af


@pytest.mark.parametrize("batch_size", [1, 3])
def test_run_aggregated_refuses_a_sum_over_a_value_past_i64(batch_size: int) -> None:
    """7 and 2**64 - 1 and 3 summed to 9 at batch_size=3 and to 1.8e19 at 1."""
    book = pl.DataFrame(
        {"pid": pl.Series([7, 2**64 - 1, 3], dtype=pl.UInt64), "amt": [2.0, 3.0, 4.0]}
    )

    with pytest.raises(ValueError, match="its sum is refused") as caught:
        run_aggregated(
            _passenger,
            book,
            aggregations=[Sum("pid").alias("t")],
            batch_size=batch_size,
        )

    assert str(caught.value).startswith(
        "Column 'pid' holds a whole number outside the signed 64-bit range"
    )


@pytest.mark.parametrize("batch_size", [1, 3])
def test_run_aggregated_sums_a_wide_column_that_fits(batch_size: int) -> None:
    """Hand value: 7 + 8 + 3."""
    book = pl.DataFrame(
        {"pid": pl.Series([7, 8, 3], dtype=pl.UInt64), "amt": [2.0, 3.0, 4.0]}
    )

    result = run_aggregated(
        _passenger, book, aggregations=[Sum("pid").alias("t")], batch_size=batch_size
    )

    assert result.aggregations["t"] == 18.0


def test_run_aggregated_still_takes_the_greatest_of_a_column_past_i64() -> None:
    """A greatest value cannot wrap, so it is not a sum and is not refused."""
    book = pl.DataFrame(
        {"pid": pl.Series([7, 2**64 - 1, 3], dtype=pl.UInt64), "amt": [2.0, 3.0, 4.0]}
    )

    result = run_aggregated(
        _passenger, book, aggregations=[Max("pid").alias("t")], batch_size=3
    )

    assert result.aggregations["t"] == float(2**64 - 1)
