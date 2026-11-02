# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number no ``i64`` holds is refused where it is written into a formula.

Every integer in a calculation graph is an ``i64`` (section 10), a literal as
much as a column: section 12.1 writes a whole-number literal as one. A literal
past that range has no name in the record, and the engine gave it none either:
``af.pid == 2**64 - 1`` on an ``Int64`` column answered null for every policy,
``af.pid + 2**64`` a null, ``when(...).then(2**64)`` an ``Int128`` column the
vocabulary does not name, and the record carried a number no consumer reads.
Such a literal is now refused at the line it is written on, naming it, with
the two moves: an identifier compared as text through ``to_text()``, a quantity
written as a decimal literal. A literal inside the range is unchanged, to its
endpoints. The refusal is a ``ValueError`` (``IntegerLiteralPastI64Error``),
which a method's argument recogniser does not decline as it declines a NaN.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"pid": [7, 8], "x": [1.5, 2.5]})

# Each place a number is written into a line, with a literal one past either
# end of the signed 64-bit range.
_WRITTEN: list[tuple[str, Callable[[Any], Any], int]] = [
    ("pid == 2**64 - 1", lambda af: af.pid == 2**64 - 1, 2**64 - 1),
    ("pid != 2**64 - 1", lambda af: af.pid != 2**64 - 1, 2**64 - 1),
    ("pid < 2**63", lambda af: af.pid < 2**63, 2**63),
    ("pid >= -(2**63) - 1", lambda af: af.pid >= -(2**63) - 1, -(2**63) - 1),
    ("pid + 2**64", lambda af: af.pid + 2**64, 2**64),
    ("2**64 - x", lambda af: 2**64 - af.x, 2**64),
    ("pid * 2**63", lambda af: af.pid * 2**63, 2**63),
    ("x / 2**63", lambda af: af.x / 2**63, 2**63),
    ("pid // 2**63", lambda af: af.pid // 2**63, 2**63),
    ("pid % 2**63", lambda af: af.pid % 2**63, 2**63),
    ("pid ** 2**64", lambda af: af.pid**2**64, 2**64),
    ("x + 2**64 (a float column)", lambda af: af.x + 2**64, 2**64),
    (
        "when(...).then(2**64)",
        lambda af: when(af.x > 2).then(2**64).otherwise(0),
        2**64,
    ),
    ("pid.is_in([2**64 - 1, 7])", lambda af: af.pid.is_in([2**64 - 1, 7]), 2**64 - 1),
    ("pid.replace([7], [2**64])", lambda af: af.pid.replace([7], [2**64]), 2**64),
    ("x.clip(0, 2**64)", lambda af: af.x.clip(0, 2**64), 2**64),
    ("x.fill_null(2**64)", lambda af: af.x.fill_null(2**64), 2**64),
    (
        "a numpy uint64 past i64",
        lambda af: af.pid == np.uint64(2**64 - 1),
        2**64 - 1,
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "literal"), _WRITTEN, ids=[w[0] for w in _WRITTEN]
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_literal_past_i64_is_refused_where_it_is_written(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    literal: int,
    door: str,
) -> None:
    af = ActuarialFrame(_BOOK if door == "DataFrame" else _BOOK.lazy())

    with pytest.raises(ValueError, match="outside the signed 64-bit range") as caught:
        af.r = line(af)

    message = str(caught.value)
    assert f"The integer literal {literal}" in message
    assert "outside the signed 64-bit range" in message
    assert ".to_text()" in message
    assert f"{float(literal)!r}" in message


def test_a_member_of_a_sequence_is_named_by_its_position() -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="outside the signed 64-bit range") as caught:
        af.r = af.pid.is_in([7, 2**64 - 1])

    assert "18446744073709551615 at position 1 of a sequence" in str(caught.value)


@pytest.mark.parametrize(
    ("line", "operation", "setting"),
    [
        (lambda af: af.x.round(2**64), "round", "decimals"),
        (lambda af: af.x.round_sig_figs(2**64), "round_sig_figs", "digits"),
    ],
    ids=["round", "round_sig_figs"],
)
def test_a_setting_past_i64_is_refused_naming_the_operation(
    line: Callable[[Any], Any], operation: str, setting: str
) -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="outside the signed 64-bit range") as caught:
        af.r = line(af)

    assert (
        f"The integer {2**64} given as {operation}'s {setting!r} is outside the "
        "signed 64-bit range"
    ) in str(caught.value)


def test_an_offset_past_i64_is_refused_where_it_answered_nulls() -> None:
    """``at_period(2**64)`` built a record no consumer reads, and answered nulls."""
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.v = af.x * af.month

    with pytest.raises(ValueError, match="'relative_period'"):
        af.r = af.v.projection.at_period(2**64)


# The endpoints themselves are i64s and unchanged, with their hand values over
# pid = [7, 8].
_ENDPOINTS: list[tuple[str, Callable[[Any], Any], str, list[object]]] = [
    ("pid == 2**63 - 1", lambda af: af.pid == 2**63 - 1, "Float64", [0.0, 0.0]),
    ("pid > -(2**63)", lambda af: af.pid > -(2**63), "Float64", [1.0, 1.0]),
    (
        "pid + -(2**63)",
        lambda af: af.pid + (-(2**63)),
        "Int64",
        [-9223372036854775801, -9223372036854775800],
    ),
    (
        "(2**63 - 1) - pid",
        lambda af: (2**63 - 1) - af.pid,
        "Int64",
        [9223372036854775800, 9223372036854775799],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "dtype", "expected"), _ENDPOINTS, ids=[e[0] for e in _ENDPOINTS]
)
def test_a_literal_at_either_end_of_i64_is_unchanged(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    dtype: str,
    expected: list[object],
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = line(af)
    out = af.collect()

    assert str(out.schema["r"]) == dtype
    assert out["r"].to_list() == expected


def test_an_identifier_past_i64_is_compared_as_text() -> None:
    """The refusal's first move, on a column the door left in its width."""
    book = pl.DataFrame({"pid": pl.Series([7, 2**64 - 1], dtype=pl.UInt64)})
    af = ActuarialFrame(book)
    af.r = af.pid.to_text() == "18446744073709551615"

    assert af.collect()["r"].to_list() == [0.0, 1.0]


def test_a_quantity_past_i64_is_written_as_a_decimal() -> None:
    """The second move: 1.5 + 2**64 and 2.5 + 2**64, each the double they round to."""
    af = ActuarialFrame(_BOOK)
    af.r = af.x + 1.8446744073709552e19

    assert af.collect()["r"].to_list() == [1.8446744073709552e19] * 2


def test_the_author_s_own_polars_keeps_polars_meaning() -> None:
    """A raw predicate is the engine's fragment: it is not lifted into the record.

    Polars compares an ``Int64`` with a literal no ``i64`` holds as null, so
    the filter keeps no row -- the engine's own answer, left as written.
    """
    af = ActuarialFrame(_BOOK)

    kept = af.filter(pl.col("pid") == 2**64 - 1)

    assert kept.collect().height == 0
