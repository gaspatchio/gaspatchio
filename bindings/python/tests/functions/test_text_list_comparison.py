# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period text column compared with text decides by the text.

A plan code or a benefit option carried per period -- ``af.db_option_t ==
"A"`` -- failed at collect with "the plugin failed with message: right at row
0 is null": the per-period comparison kernel cast both sides to Float64, and
text cast to a number is null. The comparison now compares the strings, by
exact equality and, for the orderings, by code point, and selects between any
branches the numeric comparison can. Text against a number is refused by
name, because no answer to it is true.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when


def _frame() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame({"opt": ["A", "B"], "target": ["B", "B"], "sa": [100.0, 200.0]})
    )
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 31), n_periods=2, frequency="annual"
    )
    af.opt_t = af.opt.projection.broadcast_to_periods()
    return af


def test_a_per_period_text_column_equals_a_text_value() -> None:
    af = _frame()
    af.is_a = af.opt_t == "A"
    af.not_a = af.opt_t != "A"

    out = af.collect()

    assert out["is_a"].to_list() == [[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]
    assert out["not_a"].to_list() == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]


def test_the_commuted_form_reads_the_same() -> None:
    af = _frame()
    af.is_a = "A" == af.opt_t  # noqa: SIM300 - the commuted form is the case under test

    assert af.collect()["is_a"].to_list() == [[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]


def test_a_text_condition_selects_the_benefit() -> None:
    af = _frame()
    af.benefit = when(af.opt_t == "A").then(af.sa).otherwise(0.0)

    assert af.collect()["benefit"].to_list() == [[100.0] * 3, [0.0] * 3]


def test_a_text_condition_selects_text_branches() -> None:
    af = _frame()
    af.label = when(af.opt_t == "A").then("ratchet").otherwise("return of premium")

    assert af.collect()["label"].to_list() == [
        ["ratchet"] * 3,
        ["return of premium"] * 3,
    ]


def test_per_period_text_compares_with_a_per_policy_text_column() -> None:
    af = _frame()
    af.on_target = af.opt_t == af.target

    assert af.collect()["on_target"].to_list() == [[0.0] * 3, [1.0] * 3]


def test_text_against_a_number_is_refused_by_name() -> None:
    af = _frame()

    with pytest.raises(TypeError, match="sets text against a whole number"):
        af.wrong = af.opt_t == 1


def test_per_period_text_orders_by_code_point_and_a_null_answers_null() -> None:
    """Spec section 11.1.26: list-shaped text orders period by period by code point.

    ``"Ä"`` (U+00C4) sorts after ``"a"`` (U+0061), which sorts after ``"M"``
    (U+004D): an order by locale or by case-folding would put them otherwise.
    A null element answers null rather than either truth value.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": [["IF", "LAPSED", None, "Ä", "a"]],
                "other": [["IF", "IF", "IF", "Z", "B"]],
            }
        )
    )
    af.before_m = af.status < "M"
    af.from_m = af.status >= "M"
    af.after_other = af.status > af.other

    out = af.collect()

    assert out["before_m"].to_list() == [[1.0, 1.0, None, 0.0, 0.0]]
    assert out["from_m"].to_list() == [[0.0, 0.0, None, 1.0, 1.0]]
    assert out["after_other"].to_list() == [[0.0, 1.0, None, 1.0, 1.0]]
