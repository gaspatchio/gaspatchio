# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the attribution window as a cursor into the calculation log.

The frame's calculation log is append-only and permanent. Attribution --
"which of the calculations since the last known-good point could have
caused this failure?" -- is a *view* onto its tail, delimited by one
integer: ``_window_start``. A structural operation (filter, select, join,
rename, drop, sort) or a successful materialisation moves the cursor to the
end of the log; nothing is ever removed.

That distinction is the whole point of this suite. The window narrowing is
what keeps diagnosis honest -- replaying calculations from before a filter
against a post-filter plan would name the wrong column. The log surviving
is what keeps the model auditable: a reviewer asking "how was
``death_claims`` calculated?" gets an answer whether or not a filter ran
afterwards.

``_baseline_df`` is the plan a window replays *from*, snapshotted once, when
the window's first record is about to land -- never on every assignment,
which would silently make the baseline equal the live plan and attribute
every failure to the last column touched.

The cursor delimits the LIVE window, and that is all this suite pins. A
structural operation also keeps the window it closed, paired with the
baseline that window opened over, in ``_sealed_windows`` -- which is a
different question (can a failure still be attributed to a calculation
written before a filter?) and is pinned in
``tests/errors/test_filter_attribution.py``.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.calculations import BoundaryRecord, CalculationRecord
from gaspatchio.scenarios import with_scenarios

# --- fixtures ---------------------------------------------------------------


def _policy_frame() -> ActuarialFrame:
    """Return a three-policy model point frame, named the way an actuary would."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "issue_age": [30, 31, 30],
                "sum_assured": [100_000.0, 200_000.0, 150_000.0],
                "annual_premium": [1_200.0, 2_400.0, 1_800.0],
                "mortality_rate": [0.001, 0.002, 0.0015],
            }
        )
    )


def _traced_ragged_frame() -> ActuarialFrame:
    """Return a traced-run frame with list columns of differing lengths.

    Setting ``_traced_run`` directly is how this suite stands in for the
    trace decorator, which is the one place the flag is really set; the
    ragged list columns are what make a mis-replayed operation fail loudly
    instead of silently.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six_periods": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
                "three_periods": [[1.0, 2.0, 3.0]],
                "accumulator": [[1.0, 2.0, 3.0]],
            }
        )
    )
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    return af


def _with_timeline(frame: ActuarialFrame) -> ActuarialFrame:
    """Stamp a six-period monthly projection timeline onto ``frame``.

    ``projection.set`` mutates the frame it is called on and hands it back,
    so the log continues rather than restarting; what moves is the cursor.
    """
    return frame.projection.set(
        start_date=datetime.date(2026, 1, 1),
        n_periods=6,
        frequency="monthly",
    )


def _calculations(frame: ActuarialFrame) -> list[CalculationRecord]:
    """Return the calculation records on ``frame``, boundaries excluded."""
    return [
        entry
        for entry in frame._calculations  # noqa: SLF001 -- the log under test
        if isinstance(entry, CalculationRecord)
    ]


def _log(frame: ActuarialFrame) -> list[object]:
    return frame._calculations  # noqa: SLF001 -- the log under test


def _cursor(frame: ActuarialFrame) -> int:
    return frame._window_start  # noqa: SLF001 -- the cursor under test


# --- initial state ----------------------------------------------------------


def test_a_fresh_frame_starts_with_an_empty_log_and_window() -> None:
    """Nothing has been calculated, so there is nothing to attribute."""
    af = _policy_frame()

    assert _log(af) == []
    assert _cursor(af) == 0
    assert af._attribution_ops() == []  # noqa: SLF001
    assert af._baseline_df is None  # noqa: SLF001


def test_a_fresh_frame_remembers_the_columns_it_arrived_with() -> None:
    """The input columns are not calculations; the frame records them as its start."""
    af = _policy_frame()

    assert af._initial_columns == frozenset(  # noqa: SLF001
        {"policy_id", "issue_age", "sum_assured", "annual_premium", "mortality_rate"}
    )


# --- the cursor advances, the log does not shrink ---------------------------


def test_filter_advances_the_cursor_and_keeps_every_record() -> None:
    """A structural reset narrows attribution without erasing the calculations."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af.expenses = af.annual_premium * 0.05
    assert len(_log(af)) == 2

    af = af.filter(pl.col("policy_id") == 1)

    assert len(_log(af)) == 2
    assert _cursor(af) == 2
    assert af._attribution_ops() == []  # noqa: SLF001


def test_every_structural_operation_advances_the_cursor() -> None:
    """Select, join, rename, drop and sort each restart attribution.

    The cursor lands at the log's end whatever the operation appended to
    it: ``rename`` and ``join`` mint records of their own (the new name,
    the arriving column), and those have to sit behind the cursor too --
    replay could not honestly re-apply either one.
    """
    for structural in (
        lambda af: af.select("policy_id", "annual_premium", "expenses"),
        lambda af: af.join(
            pl.DataFrame({"policy_id": [1, 2, 3], "product_code": ["T", "T", "T"]}),
            on="policy_id",
        ),
        lambda af: af.rename({"annual_premium": "gross_premium"}),
        lambda af: af.drop("issue_age"),
        lambda af: af.sort("policy_id"),
    ):
        af = _policy_frame()
        af.expenses = af.annual_premium * 0.05

        af = structural(af)

        assert _calculations(af)[0].column == "expenses"
        assert _cursor(af) == len(_log(af))
        assert af._attribution_ops() == []  # noqa: SLF001


def test_a_successful_collect_closes_the_window() -> None:
    """Materialisation proves every recorded calculation sound, so the window ends."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate

    af.collect()

    assert len(_log(af)) == 1
    assert _cursor(af) == 1
    assert af._attribution_ops() == []  # noqa: SLF001


def test_calculations_after_a_reset_reopen_the_window() -> None:
    """The next assignment after a reset is the new window's first entry."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af = af.filter(pl.col("policy_id") == 1)

    af.expenses = af.annual_premium * 0.05

    assert [record.column for record in af._attribution_ops()] == ["expenses"]  # noqa: SLF001


# --- _attribution_ops is the window tail ------------------------------------


def test_attribution_ops_returns_only_the_records_since_the_cursor() -> None:
    """Everything before the cursor is history, not a suspect."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af.collect()

    af.expenses = af.annual_premium * 0.05
    af.commissions = af.annual_premium * 0.02

    assert [record.column for record in af._attribution_ops()] == [  # noqa: SLF001
        "expenses",
        "commissions",
    ]


def test_attribution_ops_skips_boundary_records_in_the_window() -> None:
    """A boundary defines no column, so it is never a candidate for blame."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    _log(af).append(
        BoundaryRecord(kind="materialization", position=len(_log(af)), source=None)
    )
    af.expenses = af.annual_premium * 0.05

    window = af._attribution_ops()  # noqa: SLF001

    assert all(isinstance(record, CalculationRecord) for record in window)
    assert [record.column for record in window] == ["death_claims", "expenses"]


# --- _baseline_df snapshots once per window ---------------------------------


def test_the_baseline_is_snapshotted_once_per_window() -> None:
    """Every calculation in one window replays from the same pre-window plan."""
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate
    baseline = af._baseline_df  # noqa: SLF001
    af.expenses = af.annual_premium * 0.05

    assert baseline is not None
    assert af._baseline_df is baseline  # noqa: SLF001


def test_a_new_window_snapshots_a_new_baseline() -> None:
    """After a reset the baseline is the post-reset plan, not the stale one."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    baseline = af._baseline_df  # noqa: SLF001

    af = af.filter(pl.col("policy_id") == 1)
    af.expenses = af.annual_premium * 0.05

    assert af._baseline_df is not baseline  # noqa: SLF001


def test_the_first_windows_baseline_predates_every_calculation() -> None:
    """The baseline holds the input columns only -- replay starts before the model."""
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate

    baseline = af._baseline_df  # noqa: SLF001
    assert baseline is not None
    assert "death_claims" not in baseline.collect_schema().names()


# --- a batch stays inside the window it landed in ---------------------------


def test_a_batch_leaves_the_baseline_where_the_window_opened() -> None:
    """A multi-column ``with_columns`` does not restart the window.

    Its records carry the operation id that says they came from one call,
    which is all replay needs to re-apply them as one ``with_columns``. So
    the batch stays a suspect, and the baseline the window opened over --
    the plan as it stood BEFORE the batch -- has to stay where it is. A
    baseline that already contained the batch would hand replay a plan
    holding the very operations it is about to re-apply: see the end-to-end
    consequence below.
    """
    af = _traced_ragged_frame()
    af = af.with_columns(
        pl.col("accumulator").list.concat(pl.col("accumulator")).alias("accumulator"),
        (pl.col("three_periods") * 2.0).alias("doubled"),
    )
    baseline = af._baseline_df  # noqa: SLF001
    assert baseline is not None
    assert "doubled" not in baseline.collect_schema().names()
    assert [record.column for record in af._attribution_ops()] == [  # noqa: SLF001
        "accumulator",
        "doubled",
    ]

    af.pair = af.accumulator - af.six_periods

    assert af._baseline_df is baseline  # noqa: SLF001


def test_a_traced_batch_still_blames_the_genuinely_broken_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the healthy column assigned after a traced batch is not blamed.

    ``accumulator`` is self-referential -- replaying it twice doubles it
    again, and ``pair``, which is healthy against the real frame, then
    fails on a length mismatch that only replay created. The baseline has
    to predate the batch for replay to stay truthful.

    The error mode is pinned because ``set_error_mode()`` writes it
    process-wide and earlier suites leave it at ``basic``/``off``.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    af = _traced_ragged_frame()
    af = af.with_columns(
        pl.col("accumulator").list.concat(pl.col("accumulator")).alias("accumulator"),
        (pl.col("three_periods") * 2.0).alias("doubled"),
    )
    af.pair = af.accumulator - af.six_periods

    af.broken = af.three_periods - af.six_periods

    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    reported = str(excinfo.value)
    assert "Operation: broken" in reported
    assert "Operation: pair" not in reported


# --- batches drive the cursor too -------------------------------------------


def test_a_multi_expression_batch_stays_inside_the_window() -> None:
    """A batch is replayable because its records say they came from one call.

    Every expression in a batch sees the pre-batch frame. Replaying them
    sequentially would feed a sibling's new output to an expression that
    read the old one -- so replay does not: it reads the shared operation
    id back and re-applies the whole batch as one ``with_columns``. The
    cursor therefore stays put and the batch remains a suspect.
    """
    af = _policy_frame()

    af = af.with_columns(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("death_claims"),
        (pl.col("annual_premium") * 0.05).alias("expenses"),
    )

    assert len(_log(af)) == 2
    assert _cursor(af) == 0
    window = af._attribution_ops()  # noqa: SLF001
    assert [record.column for record in window] == ["death_claims", "expenses"]
    assert len({record.operation_id for record in window}) == 1


def test_a_single_expression_batch_stays_inside_the_window() -> None:
    """One expression replays exactly like a setter assignment, so the window holds."""
    af = _policy_frame()

    af = af.with_columns((pl.col("annual_premium") * 0.05).alias("expenses"))

    assert [record.column for record in af._attribution_ops()] == ["expenses"]  # noqa: SLF001


# --- derived frames carry the log, not the window ---------------------------


def test_setting_the_projection_timeline_carries_the_log_forward() -> None:
    """Phase-1 calculations stay answerable once the timeline is stamped on."""
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05

    af = _with_timeline(af)

    first = _calculations(af)[0]
    assert first.column == "expenses"
    assert first.origin == "assignment"


def test_setting_the_projection_timeline_restarts_the_window() -> None:
    """The stamped plan is structurally new, so nothing before it is a suspect."""
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05
    pre_timeline_baseline = af._baseline_df  # noqa: SLF001

    af = _with_timeline(af)
    af.commissions = af.annual_premium * 0.02

    assert [record.column for record in af._attribution_ops()] == ["commissions"]  # noqa: SLF001
    assert af._baseline_df is not pre_timeline_baseline  # noqa: SLF001


def test_the_projected_frame_keeps_counting_ordinals_across_the_timeline() -> None:
    """Reassigning a column continues its count, it does not restart it."""
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05
    af = _with_timeline(af)

    af.expenses = af.expenses * 1.1

    assert [
        entry.ordinal for entry in _calculations(af) if entry.column == "expenses"
    ] == [1, 2]


def test_the_scenario_axis_carries_the_log_forward() -> None:
    """Cross-joining scenarios widens the same model; its history comes along.

    The axis itself joins the log rather than arriving beside it: the
    model-points file has no ``scenario_id``, and a column the cross-join
    put there is a column handed to the model at a line.
    """
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05

    af = with_scenarios(af, ["BASE", "MORTALITY_UP"])

    assert [
        entry.column for entry in _log(af) if isinstance(entry, CalculationRecord)
    ] == ["expenses", "scenario_id"]
    assert af._attribution_ops() == []  # noqa: SLF001


def test_a_derived_frame_calls_its_new_columns_inputs_not_calculations() -> None:
    """A column arriving with the derived frame is an input; a carried one is not.

    The scenario axis is in neither set. It is an input, but not one the
    data arrived with -- the step recorded it, so it is answerable as the
    injection it is rather than as a field of the book.
    """
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05

    af = with_scenarios(af, ["BASE", "MORTALITY_UP"])

    assert "scenario_id" not in af._initial_columns  # noqa: SLF001
    assert "expenses" not in af._initial_columns  # noqa: SLF001


def test_a_derived_frame_does_not_share_the_predecessors_log() -> None:
    """Two frames appending to one list would each hold the other's calculations."""
    af = _policy_frame()
    af.expenses = af.annual_premium * 0.05
    expanded = with_scenarios(af, ["BASE", "MORTALITY_UP"])

    expanded.commissions = expanded.annual_premium * 0.02

    assert [record.column for record in _calculations(af)] == ["expenses"]
    assert [record.column for record in _calculations(expanded)] == [
        "expenses",
        "scenario_id",
        "commissions",
    ]
