# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A maximum-age axis, measured per policy, on this engine and the reference producer.

``projection.set(until="maximum_age", until_value=100)`` runs each policy to
age 100: ``until_value`` less that policy's own issue age, in whole years. The
node names the issue-age column and reads it, so every policy's boundary count
is on the record and this engine lays it -- where before one grid was sized
from the youngest life in the book, and this engine refused an axis whose
length the record did not carry. A shared grid laid with ``per_policy=False``
still sizes from the book and is still refused; so is an age the model wrote
as an expression, which the record carries only as its rendering.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.report import EngineRefusal
from tests.conftest import entry
from tests.test_lowerings_projection import _call, _column, answered
from tests.test_quotients import both

VALUED = datetime.date(2025, 1, 1)

# A 50-year-old, a 70-year-old and a life already at the age: 50, 30 and no
# whole years to 100, so 51, 31 and 1 annual boundaries. Read from the column
# the ages are 100, 95 and 100, so 51, 26 and 1.
POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "issue_age": [50, 70, 100],
        "max_age": [100, 95, 100],
    }
)


def _projected(until_value: int | str) -> ActuarialFrame:
    af = ActuarialFrame(POINTS).projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=until_value,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    return af


@pytest.mark.parametrize(
    ("until_value", "boundaries"),
    [(100, [51, 31, 1]), ("max_age", [51, 26, 1])],
    ids=["a-number", "a-column"],
)
def test_each_policy_runs_to_its_own_age_on_both_engines(
    until_value: int | str, boundaries: list[int]
) -> None:
    producer, engine = both(_projected(until_value))
    assert producer["num_proj_months"].to_list() == boundaries
    for column in (
        "num_proj_months",
        "month",
        "projection_start_date",
        "projection_end_date",
        "attained_age",
    ):
        assert engine[column].to_list() == producer[column].to_list(), column
    last = [ages[-1] for ages in engine["attained_age"].to_list()]
    ages = POINTS["max_age"].to_list() if until_value == "max_age" else [100] * 3
    assert last == ages


def test_a_shared_grid_to_a_maximum_age_is_still_refused() -> None:
    """``per_policy=False`` sizes one grid from the book: not on the record."""
    af = ActuarialFrame(POINTS).projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=100,
        frequency="annual",
        per_policy=False,
    )
    with pytest.raises(EngineRefusal) as refusal:
        af.collect(engine="jax")
    assert "its length is not on the record" in refusal.value.report.render()


def test_an_age_written_as_an_expression_is_refused_by_name() -> None:
    af = ActuarialFrame(POINTS).projection.set(
        valuation_date=VALUED,
        until="maximum_age",
        until_value=pl.col("max_age") + 0,
        frequency="annual",
    )
    with pytest.raises(EngineRefusal) as refusal:
        af.collect(engine="jax")
    assert "computed with an expression" in refusal.value.report.render()


def test_the_projection_axis_counts_the_years_from_each_issue_age() -> None:
    """11.1.1: ``T_i = max(0, (age - issue_age) * p)``, read off the record alone."""
    attrs = {
        "frequency": "quarterly",
        "until": "maximum_age",
        "until_value": 100,
        "valuation_date": "2024-01-31",
        "issue_age_column": "issue_age",
    }
    book = {"issue_age": {"dtype": "i64", "values": [98, 100, 101]}}
    assert answered(
        _call("projection_set", [_column("issue_age")], attrs),
        book,
        "i64",
        column="num_proj_months",
    ) == [9, 1, 1]


def test_a_maximum_age_schedule_counts_each_policy_s_own_periods() -> None:
    """11.1.37: a per-policy grid to a maximum age, sized from the operands it reads."""
    recipe = entry(
        "schedule",
        {
            "kind": "per_policy_grid",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "6M",
            "n_periods": 4,
            "start_date": "2024-01-31",
            "until_kind": "maximum_age",
            "issue_age_column": "issue_age",
            "maximum_age": 100,
        },
    )
    carried = {
        "kind": "schedule",
        "source_sha": recipe["fingerprint"],
        "payload": recipe["payload"],
    }
    assert answered(
        _call(
            "schedule.per_policy_period_count",
            [_column("issue_age")],
            {"schedule": recipe["fingerprint"]},
        ),
        {"issue_age": {"dtype": "i64", "values": [98, 99, 100, 101]}},
        "i64",
        [carried],
    ) == [4, 2, 0, 0]
