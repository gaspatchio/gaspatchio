# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A wide integer column is read as Int64 where it fits, and keeps its width where not.

Every integer a model computes in is the ``i64`` its record names. The narrow
widths already widened at the frame's door; the three wider ones were left as
they arrived, so a ``UInt64`` policy number of 7 less 10 answered
18,446,744,073,709,551,613, ``-pid`` answered a null where a value was past
``i64``, and a ``UInt128`` halved panicked the quotient kernel. One rule now
holds at the door:

- a column whose every value lies in ``[-2**63, 2**63 - 1]`` is read as
  ``Int64`` (a DataFrame's values are in hand; a LazyFrame's are judged where
  arithmetic reads the column, when the plan runs);
- a column holding any value outside keeps the width it arrived in, so
  ``to_text`` writes it by its digits and ``to_integer`` refuses it, as
  sections 11.1.39 and 11.1.23 publish;
- arithmetic on a column still wider than ``i64`` -- every operator, either
  side, per policy and per period -- is refused by name, never wrapped, under
  a gaspatchio sentence keyed on the frame's own check rather than on
  Polars' cast text.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_WIDE = [pl.UInt64, pl.Int128, pl.UInt128]
_PAST = {pl.UInt64: 2**64 - 1, pl.Int128: -(2**70), pl.UInt128: 2**64 - 1}
_REFUSED = (
    "Column 'pid' holds a whole number outside the signed 64-bit range, and "
    "arithmetic on it is refused."
)


def _shaped(book: pl.DataFrame, shape: str) -> Any:  # noqa: ANN401 -- the three doors
    return {
        "DataFrame": book,
        "LazyFrame": book.lazy(),
        "dict": {name: book[name] for name in book.columns},
    }[shape]


# Every operator the frame lowers, the column on the left and on the right,
# with the hand value over pid = [7, 8].
_OPERATIONS: list[tuple[str, Callable[[Any], Any], list[object]]] = [
    ("pid + 1", lambda af: af.pid + 1, [8, 9]),
    ("1 + pid", lambda af: 1 + af.pid, [8, 9]),
    ("pid - 10", lambda af: af.pid - 10, [-3, -2]),
    ("10 - pid", lambda af: 10 - af.pid, [3, 2]),
    ("pid * 2", lambda af: af.pid * 2, [14, 16]),
    ("2 * pid", lambda af: 2 * af.pid, [14, 16]),
    ("pid / 2", lambda af: af.pid / 2, [3.5, 4.0]),
    ("56 / pid", lambda af: 56 / af.pid, [8.0, 7.0]),
    ("pid // 3", lambda af: af.pid // 3, [2, 2]),
    ("20 // pid", lambda af: 20 // af.pid, [2, 2]),
    ("pid % 5", lambda af: af.pid % 5, [2, 3]),
    ("20 % pid", lambda af: 20 % af.pid, [6, 4]),
    ("pid ** 2", lambda af: af.pid**2, [49, 64]),
    ("2 ** pid", lambda af: 2**af.pid, [128, 256]),
    ("-pid", lambda af: -af.pid, [-7, -8]),
    ("pid + 1.5", lambda af: af.pid + 1.5, [8.5, 9.5]),
]


@pytest.mark.parametrize("shape", ["DataFrame", "dict"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_wide_column_whose_values_fit_is_read_as_int64(
    width: type[pl.DataType], shape: str
) -> None:
    af = ActuarialFrame(
        _shaped(pl.DataFrame({"pid": pl.Series([7, 8], dtype=width)}), shape)
    )
    af.d = af.pid - 10
    out = af.collect()

    # Hand values: 7 - 10 = -3 and 8 - 10 = -2, where a UInt64 wrapped.
    assert out.schema["pid"] == pl.Int64
    assert out["d"].to_list() == [-3, -2]
    assert out.schema["d"] == pl.Int64


@pytest.mark.parametrize(("name", "operation", "expected"), _OPERATIONS)
@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_arithmetic_on_a_wide_column_that_fits_answers_in_i64(
    width: type[pl.DataType],
    shape: str,
    name: str,
    operation: Callable[[Any], Any],
    expected: list[object],
) -> None:
    """A LazyFrame's column keeps its width; arithmetic reads it as the i64 it fits."""
    af = ActuarialFrame(
        _shaped(pl.DataFrame({"pid": pl.Series([7, 8], dtype=width)}), shape)
    )
    af.r = operation(af)
    out = af.collect()

    assert out["r"].to_list() == expected, name
    assert out.schema["r"] not in (pl.UInt64, pl.Int128, pl.UInt128), name


@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame", "dict"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_value_past_i64_keeps_its_width_and_its_digits(
    width: type[pl.DataType], shape: str
) -> None:
    past = _PAST[width]
    af = ActuarialFrame(
        _shaped(pl.DataFrame({"pid": pl.Series([7, past], dtype=width)}), shape)
    )
    af.as_text = af.pid.to_text()
    out = af.collect()

    assert out.schema["pid"] == width
    assert out["as_text"].to_list() == ["7", str(past)]

    refused = ActuarialFrame(
        _shaped(pl.DataFrame({"pid": pl.Series([7, past], dtype=width)}), shape)
    )
    refused.as_integer = refused.pid.to_integer()
    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match="holds a whole number outside the signed 64-bit range",
    ):
        refused.collect()


@pytest.mark.parametrize(("name", "operation", "expected"), _OPERATIONS)
@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame", "dict"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_arithmetic_on_a_value_past_i64_is_refused_by_name(
    width: type[pl.DataType],
    shape: str,
    name: str,
    operation: Callable[[Any], Any],
    expected: list[object],
) -> None:
    del expected
    af = ActuarialFrame(
        _shaped(pl.DataFrame({"pid": pl.Series([7, _PAST[width]], dtype=width)}), shape)
    )
    af.r = operation(af)
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect()
    message = str(refused.value)

    assert message.startswith(_REFUSED), name
    assert "af.pid.to_text()" in message
    assert "narrower type" in message


def test_the_refusal_is_the_frame_s_own_and_a_model_s_cast_keeps_polars_text() -> None:
    """The sentence is keyed on the frame's check, never on Polars' cast failure.

    A model that casts a wide column itself, through the escape, gets Polars'
    own account of its cast, not a sentence about arithmetic it did not write.
    """
    book = pl.DataFrame({"pid": pl.Series([7, 2**64 - 1], dtype=pl.UInt64)})
    af = ActuarialFrame(book.lazy())
    af.own = af.pid.polars_native().cast(pl.Int64)
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect()

    assert "arithmetic on it is refused" not in str(refused.value)
    assert "conversion from `u64` to `i64` failed" in str(refused.value)


@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame"])
def test_per_period_arithmetic_on_a_wide_column(shape: str) -> None:
    """A policy's wide number against the period axis: fits, i64; past, refused."""

    def projected(values: list[int]) -> ActuarialFrame:
        book = pl.DataFrame({"pid": pl.Series(values, dtype=pl.UInt64)})
        af = ActuarialFrame(_shaped(book, shape))
        return af.projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
        )

    fits = projected([7, 8])
    fits.r = fits.pid - fits.month - 8
    fits.s = fits.month - fits.pid
    out = fits.collect()
    # Hand values: 7 - [0, 1, 2] - 8 and [0, 1, 2] - 8.
    assert out["r"].to_list() == [[-1, -2, -3], [0, -1, -2]]
    assert out["s"].to_list() == [[-7, -6, -5], [-8, -7, -6]]

    past = projected([7, 2**64 - 1])
    past.r = past.pid + past.month
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        past.collect()
    assert str(refused.value).startswith(_REFUSED)


@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame"])
def test_a_list_of_wide_integers_is_judged_element_by_element(shape: str) -> None:
    def frame(values: list[list[int]]) -> ActuarialFrame:
        book = pl.DataFrame({"ids": pl.Series(values, dtype=pl.List(pl.UInt64))})
        return ActuarialFrame(_shaped(book, shape))

    fits = frame([[7, 8], [9]])
    fits.r = fits.ids - 10
    out = fits.collect()
    # Hand values: [7 - 10, 8 - 10] and [9 - 10], where each wrapped past 2**64.
    assert out["r"].to_list() == [[-3, -2], [-1]]

    past = frame([[7, 2**63], [9]])
    assert past.collect().schema["ids"] == pl.List(pl.UInt64)
    past.r = past.ids * 2
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        past.collect()
    assert str(refused.value).startswith(
        "Column 'ids' holds a whole number outside the signed 64-bit range"
    )


def test_a_joined_wide_column_is_read_as_the_book_is() -> None:
    def joined(values: list[int]) -> ActuarialFrame:
        af = ActuarialFrame(pl.DataFrame({"k": [1, 2]}))
        right = pl.DataFrame({"k": [1, 2], "h": pl.Series(values, dtype=pl.UInt64)})
        return af.join(right, on="k")

    fits = joined([3, 4])
    fits.r = fits.h - 5
    out = fits.collect()
    assert out.schema["h"] == pl.Int64
    assert out["r"].to_list() == [-2, -1]

    past = joined([3, 2**64 - 1])
    assert past.collect().schema["h"] == pl.UInt64
    past.r = past.h - 5
    with pytest.raises(pl.exceptions.InvalidOperationError, match="Column 'h' holds"):
        past.collect()


def test_a_wide_column_the_model_computes_is_held_to_the_same_rule() -> None:
    """The escape's own UInt64 -- a hash, an unsigned count -- reads the same way."""
    hashed = ActuarialFrame(pl.DataFrame({"k": [1, 2]}))
    hashed.h = hashed.k.polars_native().hash()
    hashed.bucket = hashed.h % 100
    with pytest.raises(pl.exceptions.InvalidOperationError, match="Column 'h' holds"):
        hashed.collect()

    counted = ActuarialFrame(pl.DataFrame({"cf": [[], [1.0, 2.0]]}))
    counted.last = counted.cf.polars_native().list.len() - 1
    # Hand values: 0 - 1 and 2 - 1, where the unsigned count wrapped to 2**64 - 1.
    assert counted.collect()["last"].to_list() == [-1, 1]


def test_the_edges_of_the_signed_range_are_in_it() -> None:
    edges = pl.DataFrame(
        {
            "u": pl.Series([2**63 - 1], dtype=pl.UInt64),
            "i": pl.Series([-(2**63)], dtype=pl.Int128),
            "past": pl.Series([2**63], dtype=pl.UInt64),
        }
    )
    out = ActuarialFrame(edges).collect()
    assert out.row(0) == (2**63 - 1, -(2**63), 2**63)
    assert out.schema["u"] == out.schema["i"] == pl.Int64
    assert out.schema["past"] == pl.UInt64


def test_a_null_in_a_wide_column_is_a_null() -> None:
    af = ActuarialFrame(pl.DataFrame({"pid": pl.Series([None, 7], dtype=pl.UInt64)}))
    af.r = af.pid - 10
    out = af.collect()
    assert out.schema["pid"] == pl.Int64
    assert out["r"].to_list() == [None, -3]

    lazy = ActuarialFrame(
        pl.DataFrame({"pid": pl.Series([None, 7], dtype=pl.UInt64)}).lazy()
    )
    lazy.r = lazy.pid - 10
    assert lazy.collect()["r"].to_list() == [None, -3]
