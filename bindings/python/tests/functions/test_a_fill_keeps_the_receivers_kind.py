# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A value written where another stood is the same kind, or the line is refused.

``af.rate.fill_null("n/a")`` over decimals ran and answered text,
``['1.0', 'n/a']``: Polars makes a fill fit by finding a type both sides can
be written in, and every number can be written as text. The second engine
and the conformance reader refuse the line; the frame now refuses it where it
is written, naming the move. The same silent conversion waited in every
operation that puts one value where another stood -- a conditional's branches
(11.1.28), a period shift's ``fill_value`` (11.1.19), a substitution's values
(11.1.6) and a clip's bounds (11.1.3) -- and the last two cut a wider number
down to the column's own type: ``{2.5: 9}`` matched the policy holding 2, and
whole numbers clipped at 1.5 were clipped at 1.

A whole number beside a decimal is the declared widening (11.1.13, 11.1.28)
and stays one. A flag is a number to this framework, which stores a
comparison assigned as a value as a 0/1 indicator, as it is to the second
engine; ``fill_nan``'s fill is a whole number or a decimal, its stated domain.
"""

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

NAN = float("nan")


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "rate": [1.0, None],
                "ratio": [1.0, NAN],
                "lives": [1, None],
                "code": ["a", None],
                "issued": [datetime.date(2025, 1, 1), None],
                "rates": [[1.0, None], [NAN]],
            }
        )
    )


def _projected() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"rate": [1.5], "code": ["a"], "whole": [2]}))
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.rates = af.rate.projection.broadcast_to_periods()
    af.codes = af.code.projection.broadcast_to_periods()
    return af


# --- the two fills -----------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "fill", "said"),
    [
        ("rate", "n/a", "'n/a' -- is text, and the value it fills is a decimal"),
        ("lives", "n/a", "'n/a' -- is text, and the value it fills is a whole"),
        ("issued", "n/a", "'n/a' -- is text, and the value it fills is a date"),
        ("code", 0.0, "0.0 -- is a decimal, and the value it fills is text"),
        ("rates", "n/a", "'n/a' -- is text, and the value it fills is a decimal"),
    ],
)
def test_a_null_fill_of_another_kind_is_refused_where_it_is_written(
    column: str, fill: object, said: str
) -> None:
    af = _frame()
    with pytest.raises(TypeError, match=said):
        af.filled = af[column].fill_null(fill)


@pytest.mark.parametrize("column", ["ratio", "rates"])
def test_a_text_nan_fill_is_refused_naming_the_conditional(column: str) -> None:
    af = _frame()
    with pytest.raises(TypeError, match=r"when\(af\.x\.is_nan\(\)\)\.then\('n/a'\)"):
        af.filled = af[column].fill_nan("n/a")


def test_a_fill_read_from_a_text_column_is_refused_by_its_name() -> None:
    af = _frame()
    with pytest.raises(TypeError, match="the column 'code' -- is text"):
        af.filled = af.rate.fill_null(af.code)
    with pytest.raises(TypeError, match="the column 'code' -- is text"):
        af.filled = af.ratio.fill_nan(af.code)


def test_a_flag_is_not_a_nan_fill() -> None:
    """11.1.13 states fill_nan over whole numbers and decimals."""
    af = _frame()
    with pytest.raises(TypeError, match="True -- is a flag"):
        af.filled = af.ratio.fill_nan(True)  # noqa: FBT003


def test_the_named_move_keeps_the_text_that_was_meant() -> None:
    af = _frame()
    af.label = af.rate.to_text().fill_null("n/a")
    af.nan_label = when(af.ratio.is_nan()).then("n/a").otherwise(af.ratio.to_text())
    out = af.collect()
    assert out["label"].to_list() == ["1.0", "n/a"]
    assert out["nan_label"].to_list() == ["1.0", "n/a"]


def test_fills_of_the_receivers_kind_answer_as_they_always_did() -> None:
    af = _frame()
    af.widened = af.lives.fill_null(0.5)
    af.whole_into_decimal = af.rate.fill_null(0)
    af.flag_into_decimal = af.rate.fill_null(False)  # noqa: FBT003
    af.coded = af.code.fill_null("z")
    af.dated = af.issued.fill_null(datetime.date(2026, 1, 1))
    af.periods = af.rates.fill_nan(0.0)
    out = af.collect()
    assert out["widened"].dtype == pl.Float64
    assert out["widened"].to_list() == [1.0, 0.5]
    assert out["whole_into_decimal"].to_list() == [1.0, 0.0]
    assert out["flag_into_decimal"].to_list() == [1.0, 0.0]
    assert out["coded"].to_list() == ["a", "z"]
    assert out["dated"].to_list()[1] == datetime.date(2026, 1, 1)
    assert out["periods"].to_list() == [[1.0, None], [0.0]]


# --- a conditional's branches (11.1.28) -------------------------------------


def test_a_text_branch_against_a_number_branch_is_refused() -> None:
    af = _frame()
    with pytest.raises(TypeError, match="otherwise branch -- 'n/a' -- is text"):
        af.status = when(af.lives > 0).then(af.rate).otherwise("n/a")
    with pytest.raises(TypeError, match="the column 'rate' -- is a decimal"):
        af.status = when(af.lives > 0).then("n/a").otherwise(af.rate)


def test_a_per_period_conditional_of_two_kinds_is_refused() -> None:
    af = _projected()
    with pytest.raises(TypeError, match="its then branch is text"):
        af.status = when(af.month > 0).then(af.codes).otherwise(af.rates)


def test_a_mismatch_anywhere_in_a_chain_is_refused() -> None:
    af = _frame()
    with pytest.raises(TypeError, match="when/then/otherwise"):
        af.band = (
            when(af.lives == 1).then(1.0).when(af.lives == 2).then("two").otherwise(3.0)
        )
    with pytest.raises(TypeError, match="when/then/otherwise"):
        af.band = (
            when(af.lives == 1).then("one").when(af.lives == 2).then(2.0).otherwise(3.0)
        )


def test_branches_of_one_kind_answer_as_they_always_did() -> None:
    af = _frame()
    af.mixed_numbers = when(af.lives > 0).then(af.lives).otherwise(0.5)
    af.labels = when(af.lives > 0).then("in force").otherwise(af.code)
    af.unset = when(af.lives > 0).then(af.rate).otherwise(None)
    af.indicator = when(af.lives > 0).then(af.rate > 0).otherwise(0.0)
    out = af.collect()
    assert out["mixed_numbers"].to_list() == [1.0, 0.5]
    assert out["labels"].to_list() == ["in force", None]
    assert out["unset"].to_list() == [1.0, None]


# --- a period shift's fill_value (11.1.19) ----------------------------------


def test_a_text_fill_value_on_a_run_of_rates_is_refused() -> None:
    af = _projected()
    with pytest.raises(TypeError, match="fill_value -- 'n/a' -- is text"):
        af.prior = af.rates.projection.previous_period(fill_value="n/a")
    with pytest.raises(TypeError, match="fill_value -- 'n/a' -- is text"):
        af.prior = af.rates.projection.at_period(1, fill_value="n/a")


def test_the_default_fill_value_on_a_run_of_codes_is_refused_naming_it() -> None:
    """It used to put the text '0.0' at period zero."""
    af = _projected()
    with pytest.raises(TypeError, match=r"the default, 0\.0, is for amounts"):
        af.prior = af.codes.projection.previous_period()
    af.prior = af.codes.projection.previous_period(fill_value="none")
    af.unset = af.codes.projection.next_period(fill_value=None)
    out = af.collect()
    assert out["prior"].to_list() == [["none", "a", "a"]]
    assert out["unset"].to_list() == [["a", "a", None]]


# --- a substitution's values (11.1.6) ---------------------------------------


@pytest.mark.parametrize(
    ("column", "mapping", "said"),
    [
        ("lives", {2.5: 9}, "value replaced -- 2.5 -- is a decimal"),
        ("lives", {1: 2.5}, "replacement -- 2.5 -- is a decimal"),
        ("lives", {"1": 5}, "value replaced -- '1' -- is text"),
        ("code", {"a": 1.0}, "replacement -- 1.0 -- is a decimal"),
        ("rate", {1.0: "x"}, "replacement -- 'x' -- is text"),
    ],
)
def test_a_substitution_of_another_kind_or_a_wider_number_is_refused(
    column: str, mapping: dict[object, object], said: str
) -> None:
    """``{2.5: 9}`` over whole numbers used to match the policy holding 2."""
    af = _frame()
    with pytest.raises(TypeError, match=said):
        af.mapped = af[column].replace(mapping)


def test_a_substitution_within_the_columns_kind_answers_as_it_did() -> None:
    af = _frame()
    af.whole_into_decimal = af.rate.replace({1: 5})
    af.renamed = af.code.replace({"a": "b"})
    out = af.collect()
    assert out["whole_into_decimal"].to_list() == [5.0, None]
    assert out["renamed"].to_list() == ["b", None]


# --- a clip's bounds (11.1.3) -----------------------------------------------


def test_a_decimal_bound_on_whole_numbers_is_refused() -> None:
    """Whole numbers clipped at 1.5 used to be clipped at 1."""
    af = _projected()
    with pytest.raises(TypeError, match=r"upper bound -- 1\.5 -- is a decimal"):
        af.held = af.whole.clip(0, 1.5)
    with pytest.raises(TypeError, match="lower bound -- the column 'rate'"):
        af.held = af.whole.clip(af.rate, 3)
    with pytest.raises(TypeError, match=r"lower bound -- 0\.5 -- is a decimal"):
        af.held = af.whole.projection.broadcast_to_periods().clip(0.5)


def test_a_bound_the_value_can_hold_answers_as_it_did() -> None:
    af = _projected()
    af.held = af.rate.clip(0, 1)
    af.whole_held = af.whole.clip(0, 1)
    out = af.collect()
    assert out["held"].to_list() == [1.0]
    assert out["whole_held"].to_list() == [1]
