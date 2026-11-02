# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison across two kinds is refused at the line, naming the move.

``af.d < 3`` over a column of dates ran and answered ``0.0`` for every policy:
Polars compared each date's day count with 3. Text against a number was
refused only when the frame ran, in Polars' words. 11.1.26 infers no ordering
between two families, so every comparison -- the six operators, per policy
and per period, in either operand order, assigned as a value or written as a
condition -- now refuses two kinds where it is written. ``is_between`` is not
a declared operation; written in the vocabulary it is two comparisons, and
each is held to the same rule.
"""

from __future__ import annotations

import datetime as dt
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_OPERATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

_START = dt.date(2025, 1, 1)
_MID = dt.date(2025, 6, 1)


def _frame() -> ActuarialFrame:
    """Two policies with a date, a decimal, text, a flag and a timestamp each."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "x": [1.5, 4.0],
                "s": ["a", "b"],
                "d": [_START, dt.date(2026, 6, 1)],
                "ts": [dt.datetime(2025, 1, 1), dt.datetime(2026, 6, 1)],  # noqa: DTZ001
                "b": [True, None],
            }
        )
    )


def _projected() -> ActuarialFrame:
    """Return the same book on a monthly axis, with per-period columns."""
    af = _frame().projection.set(start_date=_START, n_periods=2, frequency="monthly")
    af.xl = af.x * af.month
    af.dl = af.projection.period_dates()
    af.sl = when(af.month >= 1).then("y").otherwise("n")
    return af


# Each pair: (a frame, the left operand, the right operand, the two kinds named).
_ACROSS: dict[str, tuple[Callable[[], ActuarialFrame], str, object, str]] = {
    "date-number": (_frame, "d", 3, "a date against a whole number"),
    "date-decimal-column": (_frame, "d", "@x", "a date against a decimal"),
    "date-text": (_frame, "d", "2025-06-01", "a date against text"),
    "text-number": (_frame, "s", 3, "text against a whole number"),
    "decimal-text": (_frame, "x", "a", "a decimal against text"),
    "decimal-text-column": (_frame, "x", "@s", "a decimal against text"),
    "datetime-date": (_frame, "ts", _MID, "a date and time against a date"),
    "flag-text": (_frame, "b", "a", "a flag (True/False) against text"),
    "per-period-date-number": (_projected, "dl", 3, "a date against a whole number"),
    "per-period-text-number": (_projected, "sl", 1, "text against a whole number"),
    "per-period-decimal-text": (_projected, "xl", "@s", "a decimal against text"),
    "per-policy-date-per-period-decimal": (
        _projected,
        "d",
        "@xl",
        "a date against a decimal",
    ),
}


def _operand(af: ActuarialFrame, written: object) -> object:
    """Return a column for ``"@name"`` and the value itself otherwise."""
    if isinstance(written, str) and written.startswith("@"):
        return af[written[1:]]
    return written


@pytest.mark.parametrize("symbol", list(_OPERATORS))
@pytest.mark.parametrize("pair", list(_ACROSS))
def test_a_comparison_across_kinds_is_refused_as_a_value(
    pair: str, symbol: str
) -> None:
    """Assigned as a value, every operator refuses two kinds, naming both."""
    make, left, right, named = _ACROSS[pair]
    af = make()
    with pytest.raises(TypeError, match=f"sets {_escaped(named)}"):
        af.r = _OPERATORS[symbol](af[left], _operand(af, right))


@pytest.mark.parametrize("symbol", list(_OPERATORS))
@pytest.mark.parametrize("pair", list(_ACROSS))
def test_the_reflected_order_is_refused_too(pair: str, symbol: str) -> None:
    """``3 > af.d`` is ``af.d < 3`` to the record, and it is refused the same way."""
    make, left, right, _ = _ACROSS[pair]
    af = make()
    with pytest.raises(TypeError, match="no order or equality between the two"):
        af.r = _OPERATORS[symbol](_operand(af, right), af[left])


@pytest.mark.parametrize("pair", list(_ACROSS))
def test_a_comparison_across_kinds_is_refused_as_a_condition(pair: str) -> None:
    """Written as a ``when`` condition, or under ``&``, it is refused as well."""
    make, left, right, named = _ACROSS[pair]
    af = make()
    with pytest.raises(TypeError, match=f"sets {_escaped(named)}"):
        af.r = when(af[left] < _operand(af, right)).then(1.0).otherwise(0.0)
    with pytest.raises(TypeError, match=f"sets {_escaped(named)}"):
        af.r = (
            when((af.x > 1) & (af[left] == _operand(af, right)))
            .then(1.0)
            .otherwise(0.0)
        )


def test_a_date_against_a_number_no_longer_answers_false_everywhere() -> None:
    """The defect as found: ``af.d < 3`` answered ``[0.0, 0.0]`` and now refuses."""
    af = _frame()
    with pytest.raises(TypeError) as refused:
        af.r = af.d < 3
    said = str(refused.value)
    assert "af.d < 3" in said
    assert "Compare it with a date: af.d < date(2025, 6, 1)" in said


def test_is_between_written_in_the_vocabulary_is_held_to_one_kind() -> None:
    """``is_between`` is two comparisons in the vocabulary; across kinds it refuses.

    The proxy declares no ``is_between`` (it names the escape), so the
    declared form is the pair of comparisons, and each is checked.
    """
    af = _frame()
    with pytest.raises(AttributeError, match="is_between"):
        af.d.is_between(1, 5)
    with pytest.raises(TypeError, match="sets a date against a whole number"):
        af.r = (af.d >= 1) & (af.d <= 5)
    af.r = (af.d >= _START) & (af.d <= _MID)
    assert af.collect()["r"].to_list() == [True, False]


def test_the_named_moves_run() -> None:
    """Each move a refusal names is a line the frame accepts and answers."""
    af = _frame()
    af.before_mid = af.d < _MID
    af.code_a = af.x.to_text() == "1.5"
    af.text_one = af.s == "3"
    out = af.collect()
    assert out["before_mid"].to_list() == [1.0, 0.0]
    assert out["code_a"].to_list() == [1.0, 0.0]
    assert out["text_one"].to_list() == [0.0, 0.0]


@pytest.mark.parametrize(
    ("name", "write", "want"),
    [
        ("date-date", lambda af: af.d < _MID, [1.0, 0.0]),
        ("decimal-whole", lambda af: af.x < 3, [1.0, 0.0]),
        ("whole-decimal", lambda af: af.x < 2, [1.0, 0.0]),
        ("flag-number", lambda af: af.b == 1, [1.0, None]),
        ("text-text", lambda af: af.s == "a", [1.0, 0.0]),
        ("datetime-datetime", lambda af: af.ts < dt.datetime(2026, 1, 1), [1.0, 0.0]),  # noqa: DTZ001
    ],
)
def test_two_operands_of_one_kind_compare_as_before(
    name: str, write: Callable[[ActuarialFrame], object], want: list[float | None]
) -> None:
    """Within one kind nothing changes: a flag is a number, a whole a decimal."""
    af = _frame()
    af.r = write(af)
    assert af.collect()["r"].to_list() == want, name


def test_per_period_comparisons_of_one_kind_compare_as_before() -> None:
    """Per period: dates against a date, codes against a code, amounts a number."""
    af = _projected()
    af.dates = af.dl < dt.date(2025, 2, 1)
    af.codes = af.sl == "y"
    af.amounts = af.xl < 1.5
    out = af.collect()
    assert out["dates"].to_list() == [[1.0, 0.0, 0.0]] * 2
    assert out["codes"].to_list() == [[0.0, 1.0, 1.0]] * 2
    assert out["amounts"].to_list() == [[1.0, 0.0, 0.0]] * 2


def test_a_categorical_column_against_its_labels_compares_as_before() -> None:
    """A category is text: equality with a label is one kind and answers."""
    af = ActuarialFrame(
        pl.DataFrame({"plan": pl.Series(["A", "B"], dtype=pl.Categorical)})
    )
    af.r = af.plan == "A"
    assert af.collect()["r"].to_list() == [1.0, 0.0]


def _escaped(text: str) -> str:
    """Return ``text`` as a literal regular expression."""
    import re

    return re.escape(text)
