# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A number filling flags, and a NaN fill where no NaN can be, refused at the line.

- ``af.flag.fill_null(0.0)`` failed with Polars' ``invalid or ambiguous
  dtypes: '[bool, dyn float]'``, and ``fill_null(0)`` answered, turning every
  flag into a 32-bit whole number nobody wrote.
- ``af.text.fill_nan(0.0)``, over a flag or a date likewise, failed at
  ``collect()`` with ``is_not_nan operation not supported for dtype``.
  11.1.13 states no answer there and the reference producer refuses; it now
  refuses where the line is written, naming the value's kind.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

_START = dt.date(2025, 1, 1)


def _frame() -> ActuarialFrame:
    """Two policies holding each kind once."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "x": [1.5, 4.0],
                "i": [1, 5],
                "s": ["a", "b"],
                "c": pl.Series(["a", "b"], dtype=pl.Categorical),
                "d": [_START, dt.date(2026, 6, 1)],
                "b": [True, None],
                "f": [1.0, float("nan")],
            }
        )
    )


def _projected() -> ActuarialFrame:
    """Return the book on a monthly axis, with a per-period decimal, text and flag."""
    af = _frame().projection.set(start_date=_START, n_periods=2, frequency="monthly")
    af.xl = af.x * af.month
    af.sl = when(af.month >= 1).then("y").otherwise("n")
    af.bl = af.xl.is_in([0, 1])
    return af


# --- fill_null over flags -----------------------------------------------------


@pytest.mark.parametrize("fill", [0.0, 0, 1.5], ids=["decimal", "whole", "rate"])
@pytest.mark.parametrize("shape", ["per-policy", "per-period"])
def test_a_number_filling_flags_is_refused_naming_the_move(
    fill: float, shape: str
) -> None:
    """``fill_null(0.0)`` failed in Polars' words; ``fill_null(0)`` made Int32."""
    af = _frame() if shape == "per-policy" else _projected()
    column = "b" if shape == "per-policy" else "bl"
    with pytest.raises(TypeError) as refused:
        af.r = af[column].fill_null(fill)
    said = str(refused.value)
    assert "the value it fills is a flag (True/False)" in said
    assert "Fill with True or False" in said
    assert f"when(af.{column}.is_null()).then(0.0).otherwise(af.{column})" in said


def test_the_flag_fills_that_stand_answer_as_before() -> None:
    """A flag into flags stays a flag; a flag into decimals is the 0.0 it was."""
    af = _frame()
    af.flags = af.b.fill_null(False)  # noqa: FBT003 -- the fill under test
    af.rates = af.x.fill_null(False)  # noqa: FBT003 -- the fill under test
    af.named_move = when(af.b.is_null()).then(0.0).otherwise(af.b)
    out = af.collect()
    assert out["flags"].dtype == pl.Boolean
    assert out["flags"].to_list() == [True, False]
    assert out["rates"].to_list() == [1.5, 4.0]
    assert out["named_move"].to_list() == [1.0, 0.0]


# --- fill_nan over values that hold no NaN ------------------------------------


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("s", "text"),
        ("c", "text"),
        ("b", "a flag (True/False)"),
        ("d", "a date"),
    ],
)
def test_a_nan_fill_over_a_value_that_holds_no_nan_is_refused_at_the_line(
    column: str, kind: str
) -> None:
    """The refusal names the value's kind and the fill for a missing value."""
    af = _frame()
    with pytest.raises(TypeError) as refused:
        af.r = af[column].fill_nan(0.0)
    said = str(refused.value)
    assert f"is {kind}, which never holds a NaN" in said
    assert f"af.{column}.fill_null(...)" in said


@pytest.mark.parametrize("column", ["sl", "bl"])
def test_a_per_period_nan_fill_over_text_or_flags_is_refused(column: str) -> None:
    """Per period the refusal is the same, at the line."""
    af = _projected()
    with pytest.raises(TypeError, match="never holds a NaN"):
        af.r = af[column].fill_nan(0.0)


def test_nan_fills_over_numbers_answer_as_before() -> None:
    """A decimal is filled; a whole number holds none and stands (11.1.13)."""
    af = _frame()
    af.decimals = af.f.fill_nan(0.0)
    af.wholes = af.i.fill_nan(0.0)
    out = af.collect()
    assert out["decimals"].to_list() == [1.0, 0.0]
    assert out["wholes"].to_list() == [1.0, 5.0]
