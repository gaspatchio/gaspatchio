# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The fixed-step axis of 11.1.1, on this engine, to the reference producer's bit.

A fixed-step axis is ``T`` steps of a fixed number of years with no calendar
under it, and its time at boundary ``k`` is ``k * step_years`` or
``k / steps_per_year`` -- one IEEE operation per boundary. Here that is
``iota(T + 1)`` times or over the step, and the division is taken as written
rather than as a product by a rounded reciprocal, so a model reconciled to a
workbook's ``x + A*h`` or ``x + A/12`` on the reference producer is the same
model here, to the last bit. Each run below is collected on both engines and
compared exactly, a NaN as a NaN and a sign as a sign.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from tests.conftest import entry
from tests.test_lowerings_projection import refused
from tests.test_quotients import answers, both, same_bits

POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "issue_age": [40.0, 50.0, 60.0],
        "av0": [1000.0, 2500.0, 400.0],
        "premium": [100.0, 50.0, 0.0],
        "coi_annual": [0.012, 0.03, 0.05],
    }
)

# The multi-state room's two shapes -- the Quiz tab's 2,947 steps of 0.1 years
# and sheet 3a's 975 twelfths -- and one whose step is not whole months.
AXES = [
    {"n_periods": 2947, "step_years": 0.1},
    {"n_periods": 975, "steps_per_year": 12},
    {"n_periods": 30, "steps_per_year": 10},
]


def _on(step: dict[str, Any]) -> ActuarialFrame:
    return ActuarialFrame(POINTS).projection.set(**step)


@pytest.mark.parametrize(
    "step", AXES, ids=lambda step: "-".join(str(value) for value in step.values())
)
def test_every_column_of_a_step_axis_is_the_producers_own(step: dict[str, Any]) -> None:
    af = _on(step)
    af.t = af.projection.t_years()
    af.x_t = af.issue_age + af.projection.t_years()
    af.dt = af.projection.year_fractions()
    af.in_force = af.projection.is_in_force()
    producer, engine = both(af)
    assert producer.columns == engine.columns
    for column in ("t", "x_t", "dt"):
        assert same_bits(answers(engine, column), answers(producer, column)), column
    for column in (
        "step",
        "num_proj_months",
        "in_force",
        *(["month"] if "month" in producer.columns else []),
    ):
        assert engine[column].to_list() == producer[column].to_list(), column


def test_the_time_is_one_product_per_boundary_and_not_a_running_sum() -> None:
    af = _on({"n_periods": 2947, "step_years": 0.1})
    af.t = af.projection.t_years()
    _producer, engine = both(af)
    assert same_bits(answers(engine, "t")[:2948], [k * 0.1 for k in range(2948)])


def test_twelve_steps_a_year_divides_rather_than_multiplying_by_a_twelfth() -> None:
    af = _on({"n_periods": 975, "steps_per_year": 12})
    af.t = af.projection.t_years()
    _producer, engine = both(af)
    t = answers(engine, "t")[:976]
    assert same_bits(t, [k / 12 for k in range(976)])
    # The reciprocal's product parts from the quotient at hundreds of
    # boundaries, so the test above can tell the two apart.
    assert sum(a != k * (1 / 12) for k, a in enumerate(t)) > 300


def test_an_anniversary_falls_on_every_nth_step() -> None:
    af = _on({"n_periods": 20, "steps_per_year": 10})
    af.anniversary = af.projection.anniversary_mask()
    producer, engine = both(af)
    assert engine["anniversary"].to_list() == producer["anniversary"].to_list()
    assert [t for t, on in enumerate(engine["anniversary"][0]) if on] == [9, 19]


def test_a_rollforward_on_a_step_axis_is_the_producer_s_to_the_bit() -> None:
    af = _on({"n_periods": 24, "steps_per_year": 12})
    af.dt = af.projection.year_fractions()
    af.coi_rate = af.coi_annual * af.dt
    af.growth = (1.0 + 0.04) ** af.dt - 1.0
    builder = af.projection.rollforward(states={"av": af["av0"]})
    builder["av"].add(af["premium"])
    builder["av"].charge(af["coi_rate"])
    builder["av"].grow(af["growth"])
    af.av = compile_rollforward(builder).expr_for("av")
    producer, engine = both(af)
    assert same_bits(answers(engine, "av"), answers(producer, "av"))


def _fixed(payload: dict[str, Any]) -> list[dict[str, Any]]:
    recipe = entry("schedule", payload)
    return [
        {
            "kind": "schedule",
            "source_sha": recipe["fingerprint"],
            "payload": recipe["payload"],
        }
    ]


def test_a_dated_reading_of_a_step_axis_is_refused_by_name() -> None:
    carried = _fixed({"kind": "fixed_step", "n_periods": 2, "step_years": 0.1})
    report = refused(
        {
            "op": "call",
            "name": "projection_frame.period_dates",
            "args": [],
            "attrs": {"schedule": carried[0]["source_sha"]},
        },
        {"policy_id": {"dtype": "i64", "values": [1]}},
        "list[date]",
        carried,
    )
    assert "has no calendar" in report


def test_an_anniversary_on_step_years_is_refused_by_name() -> None:
    carried = _fixed({"kind": "fixed_step", "n_periods": 20, "step_years": 0.1})
    report = refused(
        {
            "op": "call",
            "name": "projection_frame.anniversary_mask",
            "args": [],
            "attrs": {"schedule": carried[0]["source_sha"]},
        },
        {"policy_id": {"dtype": "i64", "values": [1]}},
        "list[bool]",
        carried,
    )
    assert "steps_per_year" in report


def test_a_declaration_with_neither_a_frequency_nor_a_step_is_refused() -> None:
    report = refused(
        {
            "op": "call",
            "name": "projection_set",
            "args": [],
            "attrs": {
                "frequency": None,
                "until": None,
                "until_value": None,
                "valuation_date": None,
                "n_periods": 3,
            },
        },
        {"policy_id": {"dtype": "i64", "values": [1]}},
        "list[i64]",
    )
    assert "neither a frequency nor a fixed step" in report
