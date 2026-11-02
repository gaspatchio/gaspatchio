# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A projection axis of fixed steps in years, with no calendar under it.

A teaching workbook, or a numerical solution of Thiele's or Kolmogorov's
equations, steps ``k`` times ``h`` years rather than calendar months: the
multi-state corpus room's Quiz tab steps ``h = 0.1`` for 2,947 steps, and its
3a and 3b tabs ``h = 1/12`` with no date anywhere in the sheet. Before this
axis existed the only way to build such a model was to carry the step index as
model-point data, with no projection at all -- so a period method on a
per-policy column ran down the policies, and there was no rollforward and no
``t_years()``.

The axis is ``projection.set(n_periods=T, step_years=h)`` or
``projection.set(n_periods=T, steps_per_year=n)``. Its time is ``k * h`` or
``k / n``, one rounding per boundary, so ``issue_age + t_years()`` is the
workbook's time column bit for bit in whichever spelling the workbook used. It
stamps ``step`` (reserved, as ``month`` is), ``num_proj_months``, and
``month`` only where a step is a whole number of months; it has no dates, and
refuses every reading that would need one.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule, compile_rollforward
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

POINTS = pl.DataFrame(
    {"policy_id": [1, 2, 3], "issue_age": [40.0, 50.0, 60.0], "q": [0.1, 0.2, 0.3]}
)


def _stepped(points: pl.DataFrame = POINTS, **step: float) -> ActuarialFrame:
    return ActuarialFrame(points).projection.set(**step)  # type: ignore[arg-type]


# --- the workbook's time column, bit for bit ---------------------------------


def test_step_years_reproduces_the_quiz_tab_column_b_bit_for_bit() -> None:
    # The Quiz tab: 2,947 steps of 0.1 years, column B written x + A*h.
    af = _stepped(n_periods=2947, step_years=0.1)
    af.x_t = af.issue_age + af.projection.t_years()
    af.t = af.projection.t_years()
    out = af.collect()
    t = out["t"][0].to_list()
    assert len(t) == 2948
    assert t == [k * 0.1 for k in range(2948)]
    for row, x in enumerate((40.0, 50.0, 60.0)):
        assert out["x_t"][row].to_list() == [x + k * 0.1 for k in range(2948)]
    # The spelling is what makes it bit for bit: the other one, and a running
    # sum, part from x + A*h in the last place at most boundaries.
    assert sum(a != k / 10 for k, a in enumerate(t)) > 900
    running, total = [], 0.0
    for _k in range(2948):
        running.append(total)
        total += 0.1
    assert sum(a != b for a, b in zip(t, running, strict=True)) > 2900


def test_steps_per_year_reproduces_sheet_3a_column_b_bit_for_bit() -> None:
    # Sheets 3a and 3b: a step of 1/12, column B written x + A/12.
    af = _stepped(n_periods=975, steps_per_year=12)
    af.x_t = af.issue_age + af.projection.t_years()
    af.t = af.projection.t_years()
    out = af.collect()
    t = out["t"][0].to_list()
    assert t == [k / 12 for k in range(976)]
    assert out["x_t"][0].to_list() == [40.0 + k / 12 for k in range(976)]
    assert sum(a != k * (1 / 12) for k, a in enumerate(t)) > 300


def test_a_calendar_monthly_grid_keeps_the_running_sum() -> None:
    # Unchanged on a calendar axis: t_years there is the running sum of the
    # year fractions, which is why it is not k / 12 in the last bits.
    af = ActuarialFrame(POINTS).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=974, frequency="monthly"
    )
    af.t = af.projection.t_years()
    t = af.collect()["t"][0].to_list()
    running, total = [], 0.0
    for _k in range(975):
        running.append(total)
        total += 1 / 12
    assert t == running
    assert sum(a != k / 12 for k, a in enumerate(t)) == 947


def test_year_fractions_are_one_step_each() -> None:
    af = _stepped(n_periods=4, step_years=0.1)
    af.dt = af.projection.year_fractions()
    assert af.collect()["dt"][0].to_list() == [0.1] * 4
    af = _stepped(n_periods=3, steps_per_year=12)
    af.dt = af.projection.year_fractions()
    assert af.collect()["dt"][0].to_list() == [1 / 12] * 3


# --- the columns the axis stamps ---------------------------------------------


def test_a_step_axis_stamps_step_and_the_boundary_count_and_no_dates() -> None:
    out = _stepped(n_periods=3, step_years=0.1).collect()
    assert out.columns == [*POINTS.columns, "num_proj_months", "step"]
    assert out["step"].dtype == pl.List(pl.Int64)
    assert out["step"].to_list() == [[0, 1, 2, 3]] * 3
    assert out["num_proj_months"].to_list() == [4, 4, 4]


@pytest.mark.parametrize("per_year", [1, 2, 3, 4, 6, 12])
def test_month_is_stamped_where_a_step_is_whole_months(per_year: int) -> None:
    out = _stepped(n_periods=4, steps_per_year=per_year).collect()
    months = 12 // per_year
    assert out["month"].dtype == pl.List(pl.Int64)
    assert out["month"][0].to_list() == [k * months for k in range(5)]


@pytest.mark.parametrize("step", [{"steps_per_year": 10}, {"steps_per_year": 5}])
def test_no_month_where_a_step_is_not_whole_months(step: dict[str, int]) -> None:
    assert "month" not in _stepped(n_periods=4, **step).collect().columns


def test_no_month_on_a_step_years_axis_even_at_a_twelfth() -> None:
    # Whether 0.25 years is meant as three months is a guess; steps_per_year=4
    # is how a model says so.
    assert "month" not in _stepped(n_periods=4, step_years=0.25).collect().columns


def test_a_frame_carrying_its_own_step_is_refused_with_both_exits() -> None:
    points = POINTS.with_columns(step=pl.lit(7))
    with pytest.raises(ValueError, match="already has a 'step' column") as caught:
        _stepped(points, n_periods=3, step_years=0.1)
    message = str(caught.value)
    assert 'mp.rename({"step": "source_step"})' in message
    assert 'mp.drop("step")' in message


def test_a_frame_carrying_its_own_month_is_refused_where_month_is_stamped() -> None:
    points = POINTS.with_columns(month=pl.lit(3))
    with pytest.raises(ValueError, match="already has a 'month' column"):
        _stepped(points, n_periods=3, steps_per_year=12)
    # Where the step axis stamps no month, the model's own is left alone.
    out = _stepped(points, n_periods=3, step_years=0.1).collect()
    assert out["month"].to_list() == [3, 3, 3]


def test_step_is_reserved_only_where_it_is_stamped() -> None:
    # A calendar axis stamps no step, so a model's own step column stays.
    points = POINTS.with_columns(step=pl.lit(7))
    af = ActuarialFrame(points).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="monthly"
    )
    assert af.collect()["step"].to_list() == [7, 7, 7]


# --- the axis methods --------------------------------------------------------


def test_period_dates_is_refused_naming_the_calendar_form() -> None:
    af = _stepped(n_periods=3, step_years=0.1)
    with pytest.raises(ValueError, match="a step axis has no calendar") as caught:
        af.projection.period_dates()
    assert 'frequency="monthly"' in str(caught.value)


def test_anniversary_mask_on_step_years_is_refused_naming_steps_per_year() -> None:
    af = _stepped(n_periods=20, step_years=0.1)
    with pytest.raises(ValueError, match="steps_per_year=10"):
        af.projection.anniversary_mask()


def test_anniversary_mask_on_steps_per_year_falls_on_every_nth_step() -> None:
    af = _stepped(n_periods=20, steps_per_year=10)
    af.anniversary = af.projection.anniversary_mask()
    mask = af.collect()["anniversary"][0].to_list()
    assert len(mask) == 20
    assert [t for t, flag in enumerate(mask) if flag] == [9, 19]


def test_the_in_force_and_boundary_masks_are_uniform() -> None:
    af = _stepped(n_periods=3, step_years=0.1)
    af.in_force = af.projection.is_in_force()
    af.boundary = af.projection.contract_boundary()
    out = af.collect()
    assert out["in_force"][0].to_list() == [True] * 3
    assert out["boundary"][0].to_list() == [False] * 3


@pytest.mark.parametrize("mask", ["is_in_force", "contract_boundary"])
def test_an_end_date_column_is_refused_on_a_step_axis(mask: str) -> None:
    af = _stepped(n_periods=3, step_years=0.1)
    with pytest.raises(ValueError, match="no period end to compare an end date"):
        getattr(af.projection, mask)(end_date_column="maturity")


# --- the spelling, and what it refuses ---------------------------------------


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        ({"start_date": datetime.date(2025, 1, 31)}, "start_date"),
        ({"valuation_date": datetime.date(2025, 1, 31)}, "valuation_date"),
        ({"frequency": "monthly"}, "frequency"),
    ],
)
def test_a_calendar_argument_beside_a_step_is_refused(
    extra: dict[str, object], named: str
) -> None:
    with pytest.raises(ValueError, match="a fixed step") as caught:
        ActuarialFrame(POINTS).projection.set(
            n_periods=3,
            step_years=0.1,
            **extra,  # type: ignore[arg-type]
        )
    message = str(caught.value)
    assert named in message
    assert 'frequency="monthly"' in message


def test_a_horizon_beside_a_step_is_refused_naming_n_periods() -> None:
    with pytest.raises(ValueError, match="sized by n_periods alone"):
        ActuarialFrame(POINTS).projection.set(
            n_periods=3, steps_per_year=12, until="term_years", until_value=3
        )


def test_both_spellings_at_once_are_refused() -> None:
    with pytest.raises(ValueError, match="was given both"):
        ActuarialFrame(POINTS).projection.set(
            n_periods=3, step_years=0.1, steps_per_year=10
        )


def test_a_step_without_a_count_is_refused() -> None:
    with pytest.raises(ValueError, match="needs the number of steps"):
        ActuarialFrame(POINTS).projection.set(step_years=0.1)


def test_a_schedule_beside_the_step_arguments_is_refused() -> None:
    with pytest.raises(ValueError, match="schedule= cannot be combined"):
        ActuarialFrame(POINTS).projection.set(
            schedule=Schedule.fixed_step(n_periods=3, step_years=0.1),
            step_years=0.1,
        )


@pytest.mark.parametrize(
    "step",
    [
        {"steps_per_year": 0},
        {"steps_per_year": 12.0},
        {"step_years": 0.0},
        {"step_years": float("inf")},
        {"step_years": True},
    ],
)
def test_a_step_that_is_not_a_positive_step_is_refused(step: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="step"):
        Schedule.fixed_step(n_periods=3, **step)  # type: ignore[arg-type]


def test_the_two_spellings_are_two_schedules() -> None:
    twelfths = Schedule.fixed_step(n_periods=12, step_years=1 / 12)
    twelve = Schedule.fixed_step(n_periods=12, steps_per_year=12)
    assert twelfths.canonical_form() == {
        "kind": "fixed_step",
        "n_periods": 12,
        "step_years": 1 / 12,
    }
    assert twelve.canonical_form() == {
        "kind": "fixed_step",
        "n_periods": 12,
        "steps_per_year": 12,
    }
    assert twelfths.source_sha() != twelve.source_sha()


def test_the_schedule_form_lays_the_same_axis_as_the_arguments() -> None:
    by_arguments = _stepped(n_periods=4, steps_per_year=4)
    by_schedule = ActuarialFrame(POINTS).projection.set(
        schedule=Schedule.fixed_step(n_periods=4, steps_per_year=4)
    )
    for af in (by_arguments, by_schedule):
        af.t = af.projection.t_years()
    assert by_arguments.collect().equals(by_schedule.collect())


# --- the record ---------------------------------------------------------------


def _projection_record(af: ActuarialFrame) -> dict[str, object]:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    node = next(n for n in document["nodes"] if n["column"] == "step")
    return node["expr"]["attrs"]


def test_the_record_carries_the_step_as_written_and_no_frequency() -> None:
    assert _projection_record(_stepped(n_periods=3, step_years=0.1)) == {
        "frequency": None,
        "until": None,
        "until_value": None,
        "valuation_date": None,
        "n_periods": 3,
        "step_years": 0.1,
    }
    by_schedule = ActuarialFrame(POINTS).projection.set(
        schedule=Schedule.fixed_step(n_periods=3, steps_per_year=12)
    )
    assert _projection_record(by_schedule)["steps_per_year"] == 12
    assert "step_years" not in _projection_record(by_schedule)


def test_the_walk_through_names_a_fixed_step_axis_rather_than_a_gap() -> None:
    # frequency is null on purpose here; "not recorded boundaries" would read
    # as a field the producer failed to write.
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.graph.trace_voice import sentence_for

    attrs = tuple(_projection_record(_stepped(n_periods=3, step_years=0.1)).items())
    sentence = sentence_for(Call("projection_set", args=(), attrs=attrs), None)
    assert sentence is not None
    assert "fixed-step boundaries" in sentence


def test_a_schedule_read_on_the_axis_is_carried_as_a_fixed_step_recipe() -> None:
    af = _stepped(n_periods=3, step_years=0.1)
    af.t = af.projection.t_years()
    document = json.loads(GraphExporter(af).export(profile="executable"))
    payloads = [
        a["payload"] for a in document["assumptions"] if a["kind"] == "schedule"
    ]
    assert payloads == [{"kind": "fixed_step", "n_periods": 3, "step_years": 0.1}]


# --- a period method cannot run down the policies -----------------------------

PERIOD_METHODS: dict[str, Callable[[object], object]] = {
    "previous_period()": lambda c: c.projection.previous_period(),  # type: ignore[attr-defined]
    "cumulative_survival()": lambda c: c.projection.cumulative_survival(),  # type: ignore[attr-defined]
}


def test_the_room_workaround_ran_previous_period_down_the_policies() -> None:
    # The step index carried as model-point data, no projection: the frame's
    # rows read as periods, and each policy took the previous policy's rate.
    af = ActuarialFrame(POINTS.with_columns(step=pl.lit(0), h=pl.lit(0.1)))
    af.q_prev = af.q.projection.previous_period()
    assert af.collect()["q_prev"].to_list() == [0.0, 0.1, 0.2]


@pytest.mark.parametrize("method", list(PERIOD_METHODS))
@pytest.mark.parametrize("step", [{"step_years": 0.1}, {"steps_per_year": 12}])
def test_a_policy_column_is_refused_on_a_step_axis(
    method: str, step: dict[str, float]
) -> None:
    af = _stepped(n_periods=3, **step)
    with pytest.raises(ValueError, match="one value per policy") as caught:
        af.out = PERIOD_METHODS[method](af.q)
    assert "af.issue_age + af.projection.t_years()" in str(caught.value)


@pytest.mark.parametrize("method", list(PERIOD_METHODS))
def test_a_frame_rebuilt_from_a_step_axis_still_refuses(method: str) -> None:
    rebuilt = ActuarialFrame(_stepped(n_periods=3, step_years=0.1).collect())
    with pytest.raises(ValueError, match="one value per policy") as caught:
        rebuilt.out = PERIOD_METHODS[method](rebuilt.q)
    assert "(af.step)" in str(caught.value)


def test_a_policy_value_broadcast_along_a_step_axis_is_the_named_fix() -> None:
    af = _stepped(n_periods=3, step_years=0.1)
    af.q_t = af.q.projection.broadcast_to_periods()
    af.survival = af.q_t.projection.cumulative_survival()
    survival = af.collect()["survival"].to_list()
    assert survival[0] == pytest.approx([1.0, 0.9, 0.81, 0.729])
    assert survival[1] == pytest.approx([1.0, 0.8, 0.64, 0.512])


# --- the rollforward ---------------------------------------------------------


def _universal_life(af: ActuarialFrame) -> pl.DataFrame:
    """Premium in, a charge for cover, interest credited, on whatever axis."""
    af.dt = af.projection.year_fractions()
    af.coi_rate = af.coi_annual * af.dt
    af.growth = (1.0 + 0.04) ** af.dt - 1.0
    builder = af.projection.rollforward(states={"av": af["av0"]})
    builder["av"].add(af["premium"])
    builder["av"].charge(af["coi_rate"])
    builder["av"].grow(af["growth"])
    af.av = compile_rollforward(builder).expr_for("av")
    return af.collect()


def test_a_rollforward_on_twelve_steps_a_year_equals_the_monthly_calendar() -> None:
    points = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "av0": [1000.0, 2500.0],
            "premium": [100.0, 50.0],
            "coi_annual": [0.012, 0.03],
        }
    )
    stepped = _universal_life(
        ActuarialFrame(points).projection.set(n_periods=24, steps_per_year=12)
    )
    calendar = _universal_life(
        ActuarialFrame(points).projection.set(
            start_date=datetime.date(2025, 1, 31), n_periods=24, frequency="monthly"
        )
    )
    assert len(stepped["av"][0]) == 24
    assert stepped["av"].to_list() == calendar["av"].to_list()
