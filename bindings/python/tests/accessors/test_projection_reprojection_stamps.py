# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A re-projection replaces the axis, and the previous axis's stamps go with it.

``projection.set()`` stamps the columns its axis mints: dates and ``month`` on a
calendar grid, ``step`` (and ``month`` where a step is whole months) on a fixed
step. Re-projecting a frame used to overwrite only the names the new axis mints,
so a weekly axis laid over a monthly one kept a 3-long ``month`` beside its 7
boundaries, and a calendar axis over a fixed step kept a ``step`` of the old
length. A stale per-period column of the wrong length is a wrong number waiting
for a read (``broadcast_to_periods()`` sizes itself from ``month``/``step``).

The frame knows which columns are its own stamps from its calculation log: a
column whose latest entry is the ``projection`` record. Only those are dropped,
and only those are the frame's to replace; a model-point column that shares a
reserved name is the user's, on a second ``set()`` as on the first.
"""

import datetime
from collections.abc import Callable

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule

_START = datetime.date(2025, 1, 31)
_Axis = Callable[[ActuarialFrame], ActuarialFrame]


def _frame(**extra: list[object]) -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "policy_inception": [datetime.date(2020, 3, 15)],
                **extra,
            }
        )
    )


def _monthly(af: ActuarialFrame) -> ActuarialFrame:
    return af.projection.set(start_date=_START, n_periods=2, frequency="monthly")


def _weekly(af: ActuarialFrame) -> ActuarialFrame:
    return af.projection.set(start_date=_START, n_periods=6, frequency="weekly")


def _fixed_step(af: ActuarialFrame) -> ActuarialFrame:
    return af.projection.set(n_periods=3, step_years=0.1)


def _from_inception(af: ActuarialFrame) -> ActuarialFrame:
    schedule = Schedule.from_inception(
        n_periods=4, frequency="1M", inception_column="policy_inception"
    )
    return af.projection.set(schedule=schedule)


_DATES = {"projection_start_date", "projection_end_date"}
_REPROJECTIONS = [
    pytest.param(_monthly, _weekly, _DATES | {"num_proj_months"}, id="monthly-weekly"),
    pytest.param(_monthly, _fixed_step, {"num_proj_months", "step"}, id="monthly-step"),
    pytest.param(
        _fixed_step, _monthly, _DATES | {"num_proj_months", "month"}, id="step-monthly"
    ),
    pytest.param(
        _monthly, _from_inception, _DATES | {"num_proj_months"}, id="monthly-inception"
    ),
    pytest.param(
        _weekly, _monthly, _DATES | {"num_proj_months", "month"}, id="weekly-monthly"
    ),
]


@pytest.mark.parametrize(("first", "second", "stamps"), _REPROJECTIONS)
def test_a_reprojection_holds_exactly_the_new_axis_stamps(
    first: _Axis, second: _Axis, stamps: set[str]
) -> None:
    """Every stamp the old axis made and the new one does not is gone."""
    out = second(first(_frame())).collect()
    assert set(out.columns) == {"policy_id", "policy_inception"} | stamps


def test_monthly_then_weekly_keeps_no_month_of_the_old_length() -> None:
    """The case the probe found: a 3-long month beside a 7-boundary axis."""
    out = _weekly(_monthly(_frame())).collect()
    assert "month" not in out.columns
    assert out["num_proj_months"].to_list() == [7]


def test_a_period_length_is_never_read_off_the_previous_axis() -> None:
    """broadcast_to_periods() sizes itself from month or step: never a stale one."""
    af = _weekly(_monthly(_frame(q=[0.1])))
    with pytest.raises(ValueError, match="no `month` or `step` period index"):
        af.qq = af.q.projection.broadcast_to_periods()


def test_step_then_calendar_keeps_no_step() -> None:
    """A fixed step's 4-long step does not survive a 3-boundary calendar axis."""
    out = _monthly(_fixed_step(_frame())).collect()
    assert "step" not in out.columns
    assert out["month"].to_list() == [[0, 1, 2]]


@pytest.mark.parametrize(("first", "second", "stamps"), _REPROJECTIONS)
def test_a_model_column_survives_every_reprojection(
    first: _Axis, second: _Axis, stamps: set[str]
) -> None:
    """A user column, and a calculation that read a stamp, are never dropped."""
    af = first(_frame(steps_taken=[7]))
    af.boundaries = af.num_proj_months + 0
    af = second(af)
    out = af.collect()
    assert out["steps_taken"].to_list() == [7]
    assert "boundaries" in out.columns
    assert set(out.columns) - {"steps_taken", "boundaries"} == (
        {"policy_id", "policy_inception"} | stamps
    )


def test_a_model_point_month_carried_through_weekly_is_still_the_users() -> None:
    """Weekly leaves the user's month alone; monthly afterwards refuses it."""
    af = _weekly(_frame(month=[7]))
    assert af.collect()["month"].to_list() == [7]
    with pytest.raises(ValueError, match="already has a 'month' column"):
        _monthly(af)


def test_a_model_point_step_carried_through_a_calendar_axis_is_still_the_users() -> (
    None
):
    """A calendar axis leaves the user's step alone; a fixed step refuses it."""
    af = _monthly(_frame(step=[7]))
    assert af.collect()["step"].to_list() == [7]
    with pytest.raises(ValueError, match="already has a 'step' column"):
        _fixed_step(af)


def test_a_stamp_the_model_wrote_over_is_the_models() -> None:
    """Assigned over, month is the model's column: kept, and not overwritten."""
    af = _monthly(_frame())
    af.month = af.month * 2
    kept = _weekly(af)
    assert kept.collect()["month"].to_list() == [[0, 2, 4]]
    with pytest.raises(ValueError, match="already has a 'month' column"):
        _monthly(kept)


def test_a_monthly_reprojection_still_replaces_its_own_month() -> None:
    """The frame's own stamp is still the frame's to replace."""
    af = _monthly(_frame())
    af = af.projection.set(start_date=_START, n_periods=4, frequency="monthly")
    assert af.collect()["month"].to_list() == [[0, 1, 2, 3, 4]]
