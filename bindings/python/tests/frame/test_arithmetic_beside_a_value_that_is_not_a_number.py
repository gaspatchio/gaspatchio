# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Arithmetic between a number and text or a date is refused at the line.

``af.n * af.code`` over text and ``af.issue + 1`` over dates each failed
only when the frame ran, in Polars' words -- ``arithmetic on dtypes str and
i64 is not allowed``. Arithmetic is the numbers' (11.1.25), so the line is
refused where the model writes it, naming the kind and the number to write
instead. A fixed-point decimal is not among them: the book's decimals are
read as the doubles they denote where they enter the frame, so every
operator answers over them as over any double.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    [
        pl.Series("n", [3, 4], dtype=pl.Int64),
        pl.Series("x", [2.5, 1.0], dtype=pl.Float64),
        pl.Series("Ln", [[1, 2], [3, 4]], dtype=pl.List(pl.Int64)),
        pl.Series("Lx", [[0.5, 0.25], [2.0, 4.0]], dtype=pl.List(pl.Float64)),
        pl.Series("t", ["A", "B"], dtype=pl.String),
        pl.Series("Lt", [["a", "b"], ["c", "d"]], dtype=pl.List(pl.String)),
        pl.Series("d", [date(2025, 1, 1), date(2024, 2, 29)], dtype=pl.Date),
        pl.Series(
            "Ld",
            [[date(2025, 1, 1)], [date(2024, 1, 1)]],
            dtype=pl.List(pl.Date),
        ),
        pl.Series(
            "dt",
            [datetime(2025, 1, 1, 1), datetime(2025, 1, 2)],  # noqa: DTZ001 -- a naive book column
            dtype=pl.Datetime("us"),
        ),
        pl.Series(
            "dec", [Decimal("1.0050"), Decimal("2.5000")], dtype=pl.Decimal(20, 4)
        ),
        pl.Series(
            "Ldec",
            [[Decimal("1.5"), Decimal("0.25")], [Decimal("2.5"), Decimal(4)]],
            dtype=pl.List(pl.Decimal(20, 4)),
        ),
        pl.Series(
            "Ldec2",
            [[Decimal(3), Decimal(1)], [Decimal(2), Decimal(8)]],
            dtype=pl.List(pl.Decimal(20, 2)),
        ),
    ]
)

_NOT_A_NUMBER = "arithmetic reads numbers"

# Each line, and the words its refusal carries.
_REFUSED: dict[str, tuple[Callable[[ActuarialFrame], object], str]] = {
    "n * t": (lambda af: af.n * af.t, _NOT_A_NUMBER),
    "t + 1": (lambda af: af.t + 1, _NOT_A_NUMBER),
    "-t": (lambda af: -af.t, _NOT_A_NUMBER),
    "x * '10'": (lambda af: af.x * "10", _NOT_A_NUMBER),
    "Lt * Lx": (lambda af: af.Lt * af.Lx, _NOT_A_NUMBER),
    "Ln + t": (lambda af: af.Ln + af.t, _NOT_A_NUMBER),
    "d + 1": (lambda af: af.d + 1, _NOT_A_NUMBER),
    "x - d": (lambda af: af.x - af.d, _NOT_A_NUMBER),
    "Ld * Ln": (lambda af: af.Ld * af.Ln, _NOT_A_NUMBER),
    "dt / 2": (lambda af: af.dt / 2, _NOT_A_NUMBER),
}

# The same refusals where one operand is itself arithmetic: Polars refused
# each in its own words, because an arithmetic operand's type was not read.
_REFUSED_WITH_AN_ARITHMETIC_OPERAND: dict[
    str, tuple[Callable[[ActuarialFrame], object], str]
] = {
    "d + (n * 365)": (
        lambda af: af.d + (af.n * 365),
        r"af\.d \+ \(af\.n \* 365\): the column 'd' is a date",
    ),
    "(x + n) * t": (
        lambda af: (af.x + af.n) * af.t,
        r"\(af\.x \+ af\.n\) \* af\.t: the column 't' is text",
    ),
    "(x + n) % '10'": (
        lambda af: (af.x + af.n) % "10",
        r"'10' is text",
    ),
    "Ld + (n - n)": (
        lambda af: af.Ld + (af.n - af.n),
        r"the column 'Ld' is a date",
    ),
}


@pytest.mark.parametrize("line", list(_REFUSED_WITH_AN_ARITHMETIC_OPERAND))
def test_an_arithmetic_operand_is_typed_and_the_line_refused(line: str) -> None:
    make, words = _REFUSED_WITH_AN_ARITHMETIC_OPERAND[line]
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match=words):
        af.r = make(af)


@pytest.mark.parametrize("line", list(_REFUSED))
def test_the_line_is_refused_where_it_is_written(line: str) -> None:
    make, words = _REFUSED[line]
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match=words):
        af.r = make(af)


def test_the_refusal_names_the_operand_and_the_move() -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError) as refused:
        af.r = af.n * af.t

    text = str(refused.value)
    assert "af.n * af.t" in text
    assert "the column 't' is text" in text
    assert "the number the text stands for" in text


def test_every_line_over_the_book_s_decimals_answers_as_their_doubles() -> None:
    """A decimal is read as its double where it enters, so no line meets one.

    These lines were refused by name, or answered at the decimal's own
    places (``2 / 1.0050`` as ``1.9900``), while the book's decimals reached
    the lines; read at the door, they answer as the same lines over doubles.
    """
    lines: dict[str, Callable[[ActuarialFrame], object]] = {
        "Ldec + Ln": lambda af: af.Ldec + af.Ln,
        "Ldec + Ldec2": lambda af: af.Ldec + af.Ldec2,
        "Ldec * dec": lambda af: af.Ldec * af.dec,
        "dec + Ln": lambda af: af.dec + af.Ln,
        "2 * Ldec": lambda af: 2 * af.Ldec,
        "Ldec // 2": lambda af: af.Ldec // 2,
        "Ldec ** 2.0": lambda af: af.Ldec**2.0,
        "dec // n": lambda af: af.dec // af.n,
        "dec % 2": lambda af: af.dec % 2,
        "dec ** 2.0": lambda af: af.dec**2.0,
        "dec + Ldec": lambda af: af.dec + af.Ldec,
    }
    doubles = _BOOK.with_columns(
        pl.col("dec").cast(pl.Float64),
        pl.col("Ldec", "Ldec2").cast(pl.List(pl.Float64)),
    )
    for name, make in lines.items():
        over_decimals = ActuarialFrame(_BOOK)
        over_decimals.r = make(over_decimals)
        over_doubles = ActuarialFrame(doubles)
        over_doubles.r = make(over_doubles)
        got = over_decimals.collect()["r"]
        want = over_doubles.collect()["r"]
        assert got.dtype == want.dtype, name
        assert got.to_list() == want.to_list(), name


# Lines that answer, with their answers by hand (a decimal as its double).
_ANSWERED: dict[str, tuple[Callable[[ActuarialFrame], object], list]] = {
    "Ldec * 2": (
        lambda af: af.Ldec * 2,
        [
            [Decimal("3.0000"), Decimal("0.5000")],
            [Decimal("5.0000"), Decimal("8.0000")],
        ],
    ),
    "Ldec - 2": (
        lambda af: af.Ldec - 2,
        [
            [Decimal("-0.5000"), Decimal("-1.7500")],
            [Decimal("0.5000"), Decimal("2.0000")],
        ],
    ),
    "-Ldec": (
        lambda af: -af.Ldec,
        [
            [Decimal("-1.5000"), Decimal("-0.2500")],
            [Decimal("-2.5000"), Decimal("-4.0000")],
        ],
    ),
    "Ldec / 2.0": (lambda af: af.Ldec / 2.0, [[0.75, 0.125], [1.25, 2.0]]),
    "Ldec % 2.0": (lambda af: af.Ldec % 2.0, [[1.5, 0.25], [0.5, 0.0]]),
    "dec + 2": (lambda af: af.dec + 2, [1.005 + 2, 4.5]),
    "2 / dec": (lambda af: 2 / af.dec, [2 / 1.005, 0.8]),
    "dec // 2.0": (lambda af: af.dec // 2.0, [0.0, 1.0]),
    "dec * dec": (lambda af: af.dec * af.dec, [1.005 * 1.005, 6.25]),
    "n * x": (lambda af: af.n * af.x, [7.5, 4.0]),
}


@pytest.mark.parametrize("line", list(_ANSWERED))
def test_a_line_that_answered_still_answers(line: str) -> None:
    make, hand = _ANSWERED[line]
    af = ActuarialFrame(_BOOK)
    af.r = make(af)

    assert af.collect()["r"].to_list() == hand


@pytest.mark.parametrize("compute", [operator.sub, operator.lt])
def test_two_dates_are_left_to_the_engine(
    compute: Callable[[object, object], object],
) -> None:
    af = ActuarialFrame(_BOOK)
    af.r = compute(af.d, af.d)

    assert af.collect()["r"].len() == 2
