# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One operation, one meaning, whatever shape its operand arrived in.

A band from ``cut`` is an ordered category. ``band < "30 to 59"`` answered the
band's order per policy (``[1, 0, 0]``) and the letters' order per period, on
the JAX engine and in the reader (``[0, 0, 0]``), and the record could hold
only the second (audit C4-F9). Section 11.1.26 now refuses an ordering of a
band against text by name on both shapes; equality, inequality and ``is_in``
answer, a label outside the band's categories being unequal and no member.

And a null per-policy base raised to a run answered a null outer list -- a
policy with no periods -- where ``*``, ``+``, ``-`` and ``/`` answer a run of
nulls (audit D1-P13, 11.1.25).
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

LABELS = ["under 30", "30 to 59", "60 plus"]


def _frame(**columns: object) -> ActuarialFrame:
    book = pl.DataFrame({"issue_age": [25, 45, 70], "other": LABELS, **columns})
    af = ActuarialFrame(book)
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value=1,
        frequency="monthly",
    )
    af.att = af.issue_age + af.month * 0
    return af


def _band(value: object) -> object:
    return value.cut([29, 59], labels=LABELS)  # type: ignore[attr-defined]


@pytest.mark.parametrize("label", ["30 to 59", "Zeta"])
@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
@pytest.mark.parametrize("shape", ["issue_age", "att"])
def test_a_band_ordered_against_text_is_refused_by_name(
    label: str, op: str, shape: str
) -> None:
    af = _frame()
    band = _band(af[shape])
    lines = {
        "<": lambda: band < label,
        "<=": lambda: band <= label,
        ">": lambda: band > label,
        ">=": lambda: band >= label,
    }
    with pytest.raises(TypeError, match=r"a band -- an ordered category") as caught:
        af.flag = lines[op]()
    assert "af.issue_age < 30" in str(caught.value)
    assert ".to_text()" in str(caught.value)


def test_the_text_on_the_left_is_refused_the_same_way() -> None:
    af = _frame()
    with pytest.raises(TypeError, match=r"a band -- an ordered category"):
        af.flag = "30 to 59" > _band(af.issue_age)  # noqa: SIM300 -- the order under test


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_equality_and_membership_answer_a_label_outside_the_band(engine: str) -> None:
    af = _frame()
    af.eq_in = _band(af.issue_age) == "30 to 59"
    af.eq_out = _band(af.issue_age) == "Zeta"
    af.ne_out = _band(af.issue_age) != "Zeta"
    af.member = (
        when(_band(af.issue_age).is_in(["Zeta", "60 plus"])).then(1.0).otherwise(0.0)
    )
    af.renamed = _band(af.issue_age).replace({"Zeta": "z", "60 plus": "old"}) == "old"
    af.run_eq_out = _band(af.att) == "Zeta"
    out = af.collect(engine=engine)
    assert out["eq_in"].to_list() == [0.0, 1.0, 0.0]
    assert out["eq_out"].to_list() == [0.0, 0.0, 0.0]
    assert out["ne_out"].to_list() == [1.0, 1.0, 1.0]
    assert out["member"].to_list() == [0.0, 0.0, 1.0]
    assert out["renamed"].to_list() == [0.0, 0.0, 1.0]
    assert out["run_eq_out"].to_list() == [[0.0, 0.0]] * 3


def test_two_bands_of_one_set_of_categories_compare_in_their_order() -> None:
    same = pl.Series(["30 to 59"] * 3, dtype=pl.Enum(LABELS))
    af = _frame(same=same)
    af.below = _band(af.issue_age) < af.same
    assert af.collect()["below"].to_list() == [1.0, 0.0, 0.0]


def test_two_bands_of_different_categories_are_refused_by_name() -> None:
    other = pl.Series(["a", "b", "c"], dtype=pl.Enum(["a", "b", "c"]))
    af = _frame(letters=other)
    with pytest.raises(TypeError, match=r"two bands of different categories"):
        af.below = _band(af.issue_age) < af.letters


def test_a_category_against_text_still_compares_as_its_text() -> None:
    categories = pl.Series(LABELS, dtype=pl.Categorical)
    af = _frame(cat=categories)
    af.below = af.cat < "30 to 59"
    assert af.collect()["below"].to_list() == [0.0, 0.0, 0.0]


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_a_null_base_raised_to_a_run_is_a_run_of_nulls(engine: str) -> None:
    book = pl.DataFrame(
        {
            "b": [None, 2.0],
            "whole": [None, 2],
            "run": [[1.0, 2.0], [1.0, 2.0]],
        }
    )
    af = ActuarialFrame(book)
    af.power = af.b**af.run
    af.whole_power = af.whole**af.run
    af.times = af.b * af.run
    out = af.collect(engine=engine)
    assert out["power"].to_list() == [[None, None], [2.0, 4.0]]
    assert out["whole_power"].to_list() == [[None, None], [2.0, 4.0]]
    assert out["power"].to_list()[0] == out["times"].to_list()[0]
