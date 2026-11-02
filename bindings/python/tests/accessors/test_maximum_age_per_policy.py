# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``until="maximum_age"`` runs each policy to its own age.

A policy's value is a function of its own data and the model. The horizon
``until_value`` less each policy's own issue age, in whole years at the
schedule's frequency, makes "until age 100" mean 100 for every life: a
70-year-old's annuity-due to age 100 is worth the same alone as beside a
50-year-old. One grid sized from the youngest life projected every older
life past the age asked for, so the 70-year-old's value moved with its
neighbour (17,028.46 alone, 17,778.09 beside a 50-year-old: the grid ran it
to 120).

The hand values are an annuity-due of 1,000 a year at 3% on a Gompertz table,
``q_x = min(1, 0.00004 * 1.1 ** (x - 18))``, paid at each boundary from the
issue age to the boundary at age 100 inclusive:
``sum_{k=0}^{100-x} 1000 * kp_x / 1.03**k``.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.assumptions import Table
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.scenarios import Sum

VALUED = datetime.date(2025, 1, 1)
AGES = range(18, 121)
QX = [min(1.0, 0.00004 * 1.1 ** (age - 18)) for age in AGES]

# The hand values, worked in the module docstring's sum.
HAND_P70 = 17028.456389041603
HAND_P50 = 24099.328834830787
# What the shared grid answered for the 70-year-old beside a 50-year-old: the
# same sum run on to the boundary at age 120.
SHARED_GRID_P70 = 17778.08690638139


def _hand(issue_age: int) -> float:
    """Return the annuity-due to the boundary at age 100, summed by hand."""
    survival, value = 1.0, 0.0
    for k, age in enumerate(range(issue_age, 101)):
        value += 1000.0 * survival / 1.03**k
        survival *= 1.0 - QX[age - 18]
    return value


def _table() -> Table:
    return Table(
        name="w5r89_gompertz",
        source=pl.DataFrame({"age": list(AGES), "qx": QX}),
        dimensions={"age": "age"},
        value="qx",
    )


def _annuity(af: ActuarialFrame, until_value: object = 100) -> ActuarialFrame:
    table = _table()
    af = af.projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=until_value,  # type: ignore[arg-type]
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.qx = table.lookup(age=af.attained_age)
    af.survival = af.qx.projection.cumulative_survival()
    af.pv = (af.survival * 1000.0).projection.prospective_value(
        discount_rate=0.03, timing="beginning_of_period"
    )
    af.pv0 = af.pv.list.get(0)
    return af


BOOK = pl.DataFrame(
    {"policy_id": ["P50", "P70"], "issue_age": [50, 70], "max_age": [100, 100]}
)


def test_the_hand_values_are_the_sums_they_say() -> None:
    assert _hand(70) == pytest.approx(HAND_P70, abs=1e-9)
    assert _hand(50) == pytest.approx(HAND_P50, abs=1e-9)


def test_a_policy_is_worth_the_same_alone_and_beside_a_younger_life() -> None:
    alone = _annuity(ActuarialFrame(BOOK.filter(pl.col("policy_id") == "P70")))
    beside = _annuity(ActuarialFrame(BOOK)).collect()

    assert alone.collect()["pv0"][0] == pytest.approx(HAND_P70, abs=1e-6)
    p70 = beside.filter(pl.col("policy_id") == "P70")
    assert p70["pv0"][0] == pytest.approx(HAND_P70, abs=1e-6)
    assert p70["pv0"][0] != pytest.approx(SHARED_GRID_P70, abs=1.0)
    assert beside["pv0"].to_list() == pytest.approx([HAND_P50, HAND_P70], abs=1e-6)


@pytest.mark.parametrize(
    "until_value",
    [100, "max_age", pl.col("max_age")],
    ids=["a-number", "a-column", "an-expression"],
)
def test_every_form_of_the_age_runs_each_policy_to_it(until_value: object) -> None:
    out = _annuity(ActuarialFrame(BOOK), until_value).collect()

    # 50 and 30 whole years at an annual cadence: 51 and 31 boundaries.
    assert out["num_proj_months"].to_list() == [51, 31]
    assert [len(months) for months in out["month"].to_list()] == [51, 31]
    assert [ages[-1] for ages in out["attained_age"].to_list()] == [100, 100]
    assert out["projection_end_date"].to_list() == [
        datetime.date(2075, 1, 1),
        datetime.date(2055, 1, 1),
    ]


def test_the_horizon_is_counted_at_the_schedules_frequency() -> None:
    af = ActuarialFrame(BOOK).projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=100,
        frequency="monthly",
    )
    assert af.collect()["num_proj_months"].to_list() == [50 * 12 + 1, 30 * 12 + 1]


def test_the_record_names_the_column_each_horizon_is_measured_from() -> None:
    af = _annuity(ActuarialFrame(BOOK))
    stamp = next(
        entry
        for entry in af._calculations  # noqa: SLF001 -- the frame's own log
        if isinstance(entry, CalculationRecord) and entry.column == "num_proj_months"
    )
    attrs = dict(stamp.node.attrs)  # type: ignore[union-attr]

    assert attrs["until"] == "maximum_age"
    assert attrs["until_value"] == 100
    assert attrs["issue_age_column"] == "issue_age"
    assert [arg.name for arg in stamp.node.args] == ["issue_age"]  # type: ignore[union-attr]


def test_the_schedule_recipe_states_the_age_in_the_form_written() -> None:
    def recipe(until_value: object) -> dict[str, object]:
        af = ActuarialFrame(BOOK).projection.set(
            valuation_date=VALUED,
            until="maximum_age",
            until_value=until_value,  # type: ignore[arg-type]
            frequency="annual",
        )
        return af._projection.canonical_form()  # type: ignore[union-attr]  # noqa: SLF001

    number = recipe(100)
    assert number["kind"] == "per_policy_grid"
    assert number["until_kind"] == "maximum_age"
    assert number["issue_age_column"] == "issue_age"
    assert number["maximum_age"] == 100
    assert "until_value_column" not in number
    assert recipe("max_age")["until_value_column"] == "max_age"
    assert recipe(pl.col("max_age"))["until_value_expr"] == 'col("max_age")'


def test_a_batch_runner_answers_the_hand_total_at_every_batch_size() -> None:
    totals = [
        run_aggregated(_annuity, BOOK, [Sum("pv0").alias("pv0")], batch_size=size).pv0
        for size in (1, 2)
    ]
    assert totals == pytest.approx([HAND_P50 + HAND_P70] * 2, abs=1e-6)


def test_per_policy_true_accepts_a_maximum_age() -> None:
    af = ActuarialFrame(BOOK).projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=100,
        frequency="annual",
        per_policy=True,
    )
    assert af.collect()["num_proj_months"].to_list() == [51, 31]
