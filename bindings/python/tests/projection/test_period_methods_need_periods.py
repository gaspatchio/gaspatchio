# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A period method refuses a per-policy column on a frame with a timeline.

On a projected frame the rows are policies. A column holding one value per
policy -- a rate looked up by issue age where attained age was meant -- has
no periods of its own, and folding or shifting it down the rows crosses from
one policy into the next: policy 2's survival would become ``1 - q`` of
policy 1, and would change with which policies share the file and in what
order. The period methods refuse it and name the fix.

A frame without a timeline keeps the documented behaviour: each row is a
period, and the methods run down the rows (grouped with ``.over()``).
"""

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule

POINTS = pl.DataFrame(
    {"policy_id": [1, 2, 3], "q": [0.1, 0.2, 0.3], "remaining_term": [3, 2, 3]}
)

PERIOD_METHODS = {
    "cumulative_survival()": lambda c: c.projection.cumulative_survival(),
    "previous_period()": lambda c: c.projection.previous_period(),
    "next_period()": lambda c: c.projection.next_period(),
    "at_period()": lambda c: c.projection.at_period(-2),
    "remaining_sum()": lambda c: c.projection.remaining_sum(),
    "prospective_value()": lambda c: c.projection.prospective_value(discount_rate=0.03),
}


def _projected(points: pl.DataFrame = POINTS) -> ActuarialFrame:
    af = ActuarialFrame(points)
    return af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )


@pytest.mark.parametrize("method", list(PERIOD_METHODS))
def test_a_policy_column_is_refused_on_a_projected_frame(method: str) -> None:
    # Refused on the assignment: the line the model wrote, not a later collect().
    af = _projected()
    with pytest.raises(ValueError, match="one value per policy") as caught:
        af.out = PERIOD_METHODS[method](af.q)
    message = str(caught.value)
    assert method in message
    assert "broadcast_to_periods()" in message
    assert "af.issue_age + af.month // 12" in message


def test_a_frame_rebuilt_from_a_collected_projection_still_refuses() -> None:
    # The schedule does not survive collect(); the per-period month column does.
    af = ActuarialFrame(_projected().collect())
    with pytest.raises(ValueError, match="one value per policy"):
        af.out = af.q.projection.previous_period()


def _axis(kind: str) -> ActuarialFrame:
    """Project POINTS on one of the axes ``projection.set()`` lays."""
    af = ActuarialFrame(
        POINTS.with_columns(inception=pl.date(2024, 3, 15)),
    )
    if kind == "inception":
        return af.projection.set(
            schedule=Schedule.from_inception(
                inception_column="inception", n_periods=4, frequency="1M"
            )
        )
    return af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=4, frequency=kind
    )


# Every axis projection.set() lays. Monthly stamps a per-period ``month``;
# weekly, daily and inception axes stamp none, and every axis stamps
# ``num_proj_months``.
AXES = ["monthly", "quarterly", "weekly", "daily", "inception"]


@pytest.mark.parametrize("kind", AXES)
@pytest.mark.parametrize("method", ["previous_period()", "cumulative_survival()"])
def test_a_frame_rebuilt_from_its_own_output_refuses_on_every_axis(
    kind: str, method: str
) -> None:
    # On a weekly, daily or inception axis there is no ``month`` column, and a
    # rebuilt frame used to run the method down the policies: previous_period
    # gave [0.0, 0.1, 0.2], each policy the previous policy's rate.
    projected = _axis(kind)
    projected.dates = projected.projection.period_dates()
    rebuilt = ActuarialFrame(projected.collect())
    with pytest.raises(ValueError, match="one value per policy"):
        rebuilt.out = PERIOD_METHODS[method](rebuilt.q)


def test_a_long_format_frame_exploded_from_output_keeps_the_rows() -> None:
    # Exploded to one row per period the frame is long format again: it still
    # carries num_proj_months, but nothing on it is laid along periods, so the
    # rows are the periods and the documented fold runs down them.
    projected = _axis("weekly")
    projected.dates = projected.projection.period_dates()
    long_format = ActuarialFrame(
        projected.collect().explode("dates", empty_as_null=False)
    )
    long_format.q_prev = long_format.q.projection.previous_period()
    q_prev = long_format.collect()["q_prev"].to_list()
    assert q_prev[:6] == pytest.approx([0.0, 0.1, 0.1, 0.1, 0.1, 0.1])


def test_a_per_period_column_on_the_same_frame_still_runs() -> None:
    af = _projected()
    af.q_t = af.q + af.month * 0.0
    af.survival = af.q_t.projection.cumulative_survival()
    af.q_prev = af.q_t.projection.previous_period()
    result = af.collect()
    assert result["survival"][1].to_list() == pytest.approx([1.0, 0.8, 0.64, 0.512])
    assert result["q_prev"][1].to_list() == pytest.approx([0.0, 0.2, 0.2, 0.2])


def test_a_broadcast_policy_value_is_the_named_fix() -> None:
    af = _projected()
    af.q_t = af.q.projection.broadcast_to_periods()
    af.survival = af.q_t.projection.cumulative_survival()
    result = af.collect()
    # Each policy's survival is its own: no policy reads another's rate.
    assert result["survival"][0].to_list() == pytest.approx([1.0, 0.9, 0.81, 0.729])
    assert result["survival"][1].to_list() == pytest.approx([1.0, 0.8, 0.64, 0.512])


def test_without_a_timeline_the_rows_are_periods_and_the_fold_runs() -> None:
    long_format = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 1, 2, 2], "q": [0.1, 0.2, 0.3, 0.4]})
    )
    long_format.survival = long_format.q.projection.cumulative_survival()
    long_format.q_prev = long_format.q.projection.previous_period()
    result = long_format.collect()
    assert result["survival"].to_list() == pytest.approx([1.0, 0.9, 0.72, 0.504])
    assert result["q_prev"].to_list() == pytest.approx([0.0, 0.1, 0.2, 0.3])


def test_without_a_timeline_a_list_only_method_still_refuses_a_scalar() -> None:
    # remaining_sum has no down-the-rows form: a per-policy column is refused
    # by name rather than failing inside the query plan.
    plain = ActuarialFrame(POINTS)
    with pytest.raises(ValueError, match=r"remaining_sum\(\) works period by period"):
        plain.out = plain.q.projection.remaining_sum()


def test_set_names_a_missing_until_value_column() -> None:
    af = ActuarialFrame(POINTS)
    with pytest.raises(ValueError, match="no column of that name") as caught:
        af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value="remaining_term_months",
            frequency="monthly",
        )
    message = str(caught.value)
    assert "'remaining_term_months'" in message
    assert "policy_id, q, remaining_term" in message


def test_set_reads_a_present_until_value_column_per_policy() -> None:
    af = ActuarialFrame(POINTS).projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="remaining_term",
        frequency="monthly",
    )
    assert [len(m) for m in af.collect()["month"].to_list()] == [4, 3, 4]
