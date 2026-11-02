# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for af.projection.rollforward() reading schedule from the frame."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward, when
from gaspatchio.scenarios import with_scenarios
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable


class TestRollforwardReadsFromFrame:
    def test_basic_single_state(self) -> None:
        af = ActuarialFrame(
            {
                "id": ["P1"],
                "av_init": [1000.0],
                "fund_return": [[0.01] * 12],
            }
        )
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        b = af.projection.rollforward(states={"av": pl.col("av_init")})
        b["av"].grow(pl.col("fund_return"))
        compiled = compile_rollforward(b)
        af.av = compiled.expr_for("av")
        result = af.collect()
        assert "av" in result.columns


class TestRollforwardErrorPaths:
    def test_schedule_kwarg_raises_typeerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(TypeError, match="schedule= is no longer accepted"):
            af.projection.rollforward(
                states={"av": pl.col("av_init")},
                schedule=sched,
            )

    def test_no_projection_raises_valueerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        with pytest.raises(ValueError, match="no projection"):
            af.projection.rollforward(states={"av": pl.col("av_init")})


def _a_tracked_fund() -> tuple[ActuarialFrame, object]:
    """Return a frame holding a tracked rollforward's state, and its compilation."""
    af = ActuarialFrame(
        pl.DataFrame(
            {"av_init": [1000.0], "fund_return": [[0.01] * 3], "fee": [[5.0] * 3]}
        )
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(
        states={"av": af["av_init"]},
        points=["bop", "after_growth", "eop"],
        track_increments=True,
    )
    b["av"].between("bop", "after_growth").grow(af["fund_return"], label="growth")
    b["av"].subtract(af["fee"], label="fee")
    compiled = compile_rollforward(b)
    af.av = compiled.expr_for("av")
    return af, compiled


class TestStateAccessorsReadTheirCompilation:
    """``af.av.increments`` and ``af.av.captures`` read the rollforward behind ``av``.

    Both were documented and neither worked: they read a column named
    ``__rollforward_av`` that nothing ever wrote, and raised a KeyError. They
    now follow the column's own definition in the calculation log to the
    compilation it was assigned from, and ask it what ``increment_for`` and
    ``expr_for`` give.
    """

    def test_increments_reads_a_labelled_step_s_movement(self) -> None:
        af, compiled = _a_tracked_fund()

        af.growth_credit = af.av.increments["growth"]
        af.direct = compiled.increment_for("growth")

        result = af.collect()
        assert result["growth_credit"].to_list() == result["direct"].to_list()
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_captures_reads_the_state_at_another_point(self) -> None:
        af, compiled = _a_tracked_fund()

        af.after_growth = af.av.captures["after_growth"]
        af.direct = compiled.expr_for("av", point="after_growth")

        result = af.collect()
        assert result["after_growth"].to_list() == result["direct"].to_list()
        assert result["after_growth"].to_list()[0] == pytest.approx(
            [1010.0, 1015.05, 1020.1505]
        )

    def test_the_kernel_still_runs_once(self) -> None:
        """Every read shares the one struct the state's assignment materialised."""
        af, _compiled = _a_tracked_fund()

        af.growth_credit = af.av.increments["growth"]
        af.after_growth = af.av.captures["after_growth"]

        scratch = [n for n in af._schema or () if n.startswith("__rollforward_")]  # noqa: SLF001
        assert len(scratch) == 1

    def test_a_column_no_rollforward_produced_says_where_to_read_instead(
        self,
    ) -> None:
        af, _compiled = _a_tracked_fund()

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af.fee.increments["growth"]

        message = str(refusal.value)
        assert "af['fee'].increments" in message
        assert "no definition of 'fee'" in message
        assert "compiled.increment_for(label)" in message
        assert "compiled.expr_for(state, point=...)" in message

    def test_an_untracked_rollforward_says_to_track_it(self) -> None:
        af = ActuarialFrame(pl.DataFrame({"av_init": [1000.0], "fee": [[5.0] * 3]}))
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
        )
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].subtract(af["fee"], label="fee")
        af.av = compile_rollforward(b).expr_for("av")

        with pytest.raises(ValueError, match="track_increments=True"):
            af.av.increments["fee"]

    def test_an_unknown_label_names_the_ones_there_are(self) -> None:
        af, _compiled = _a_tracked_fund()

        with pytest.raises(KeyError, match="no step of this rollforward emits"):
            af.av.increments["premium"]


def _kernel_calls(af: ActuarialFrame) -> int:
    """Return how many rollforward kernel calls the frame's plan makes."""
    plan = af._df  # noqa: SLF001 -- the plan under test
    assert plan is not None
    return plan.explain(optimized=False).count(":rollforward(")


def _materialized_then_input_changed(af: ActuarialFrame) -> ActuarialFrame:
    af = af.materialize()
    af.fund_return = af.fund_return * 10
    return af


def _materialized(af: ActuarialFrame) -> ActuarialFrame:
    return af.materialize()


def _continued_with_input_changed_outside(af: ActuarialFrame) -> ActuarialFrame:
    values = af.collect().with_columns(
        pl.col("fund_return").list.eval(pl.element() * 10)
    )
    return ActuarialFrame(values, continue_from=af)


def _selected_without_the_run(af: ActuarialFrame) -> ActuarialFrame:
    return af.select("av_init", "fund_return", "fee", "av")


def _selected_down_to_the_state(af: ActuarialFrame) -> ActuarialFrame:
    return af.select("av")


def _without_the_run(af: ActuarialFrame) -> ActuarialFrame:
    """Select every column of the model, which leaves the run behind."""
    return af.select(
        "av_init",
        "fund_return",
        "fee",
        "av",
        "projection_start_date",
        "projection_end_date",
        "num_proj_months",
        "month",
    )


def _run_again_after_the_run_left(af: ActuarialFrame) -> ActuarialFrame:
    """Drop the run, and let a later extraction run it again over the same inputs."""
    compiled = _a_tracked_fund()[1]
    af = _without_the_run(af)
    af.later = compiled.expr_for("av", point="after_growth")
    return af


class TestStateAccessorsReadOnlyTheColumnsOwnRun:
    """A state's increments and captures come from the run that produced it.

    They are read from the struct the frame's plan holds. When the plan no
    longer holds the run the column came from -- after materialize(), on a
    frame rebuilt from collected values, after a select that drops it -- a
    read used to run the rollforward again over its inputs as they were by
    then, and could answer for a different run than the column's own.
    """

    def test_the_run_still_in_the_frame_answers_with_one_kernel_call(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.other = af.av_init * 2
        af.collect()

        af.growth_credit = af.av.increments["growth"]
        af.after_growth = af.av.captures["after_growth"]

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )
        assert result["after_growth"].to_list()[0] == pytest.approx(
            [1010.0, 1015.05, 1020.1505]
        )

    @pytest.mark.parametrize(
        "route",
        [
            _materialized_then_input_changed,
            _materialized,
            _continued_with_input_changed_outside,
            _selected_without_the_run,
            _selected_down_to_the_state,
            _run_again_after_the_run_left,
        ],
        ids=[
            "materialize-then-input-changed",
            "materialize",
            "continue-from-with-input-changed",
            "select-without-the-run",
            "select-down-to-the-state",
            "run-again-after-the-run-left",
        ],
    )
    def test_a_run_no_longer_in_the_frame_is_refused(
        self, route: Callable[[ActuarialFrame], ActuarialFrame]
    ) -> None:
        af = route(_a_tracked_fund()[0])

        for read in (
            lambda: af.av.increments["growth"],
            lambda: af.av.captures["after_growth"],
        ):
            with pytest.raises(ValueError, match="no longer in the frame") as refusal:
                read()
            message = str(refusal.value)
            assert "before materialize()" in message
            assert "compiled.increment_for(label)" in message
            assert "inputs as they are now" in message

    def test_a_column_from_the_later_run_reads_that_run(self) -> None:
        """The run's own columns still answer, from the run they came from."""
        af = _run_again_after_the_run_left(_a_tracked_fund()[0])

        af.later_growth = af.later.increments["growth"]

        assert af.collect()["later_growth"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )


def _shocked(af: ActuarialFrame) -> ActuarialFrame:
    """Write one of the rollforward's inputs again, after the frame read it."""
    af.fund_return = af.fund_return * 10
    return af


def _fee_as_itself(af: ActuarialFrame) -> None:
    af.fee = af.fee


def _fee_times_one(af: ActuarialFrame) -> None:
    af.fee = af.fee * 1


def _one_times_fee(af: ActuarialFrame) -> None:
    af.fee = 1.0 * af.fee


def _fee_as_itself_under_an_alias(af: ActuarialFrame) -> None:
    af.with_columns(pl.col("fee").alias("fee"))


def _a_fund_charged_its_projection_length() -> tuple[ActuarialFrame, object]:
    """Return a fund whose kernel reads a column projection.set stamps."""
    af = ActuarialFrame(
        pl.DataFrame({"av_init": [1000.0], "fund_return": [[0.01] * 3]})
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].grow(af["fund_return"], label="growth")
    b["av"].subtract(af["num_proj_months"], label="per_period_charge")
    compiled = compile_rollforward(b)
    af.av = compiled.expr_for("av")
    return af, compiled


class TestAReadAfterAnInputMovedIsRefused:
    """A frame runs a compiled rollforward once, over its inputs at its first read.

    The calculation graph binds the compilation to those inputs there, as one
    node, and an engine evaluates it once. A read written after one of them
    was written again used to answer without a word: from the run over the
    earlier values while that run was on the plan, and from a second run over
    the later ones once it had left -- a run neither the graph nor an engine
    has, so the two disagreed about the same line.
    """

    @pytest.mark.parametrize(
        "read",
        [
            lambda compiled: compiled.expr_for("av"),
            lambda compiled: compiled.increment_for("growth"),
            lambda compiled: compiled.expr_for("av") * 1.0,
        ],
        ids=["expr_for", "increment_for", "an-expression-around-one"],
    )
    def test_a_read_written_after_an_input_moved_is_refused(
        self, read: Callable[[object], object]
    ) -> None:
        af, compiled = _a_tracked_fund()
        _shocked(af)

        with pytest.raises(
            ValueError, match="input 'fund_return' was written"
        ) as refusal:
            af.av_after = read(compiled)

        message = str(refusal.value)
        assert "after the frame first read the rollforward" in message
        assert "binds the rollforward there" in message
        assert "write this line before 'fund_return' is written again" in message
        assert "under a name of their own" in message
        assert "write 'fund_return' before the frame first reads" in message
        assert "av_after" not in af.columns

    @pytest.mark.parametrize(
        "route",
        [_materialized, _without_the_run],
        ids=["materialize", "select-without-the-run"],
    )
    def test_a_second_run_after_the_first_left_is_refused(
        self, route: Callable[[ActuarialFrame], ActuarialFrame]
    ) -> None:
        af, compiled = _a_tracked_fund()
        af = _shocked(route(af))

        with pytest.raises(ValueError, match="input 'fund_return' was written"):
            af.later = compiled.expr_for("av")

    def test_reading_before_the_input_moves_reads_that_run(self) -> None:
        """The refusal's first move: the same read, written before the write."""
        af, compiled = _a_tracked_fund()
        af.growth_credit = compiled.increment_for("growth")
        _shocked(af)

        assert _kernel_calls(af) == 1
        assert af.collect()["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_a_states_own_movements_still_answer_from_its_run(self) -> None:
        af, _compiled = _a_tracked_fund()
        _shocked(af)

        af.growth_credit = af.av.increments["growth"]
        af.after_growth = af.av.captures["after_growth"]

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av"].to_list()[0] == pytest.approx([1005.0, 1010.05, 1015.1505])
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )
        assert result["after_growth"].to_list()[0] == pytest.approx(
            [1010.0, 1015.05, 1020.1505]
        )

    @pytest.mark.parametrize(
        ("read", "expected"),
        [
            (lambda af: af.av.increments["growth"] * 2, [20.0, 20.1, 20.201]),
            (
                lambda af: (
                    when(af.fund_return > 0.005)
                    .then(af.av.captures["after_growth"])
                    .otherwise(0.0)
                ),
                [1010.0, 1015.05, 1020.1505],
            ),
            (
                lambda af: af.av.increments["growth"].projection.previous_period(),
                [0.0, 10.0, 10.05],
            ),
            (
                lambda af: af.av.captures["after_growth"] > 1012.0,
                [0.0, 1.0, 1.0],
            ),
        ],
        ids=["arithmetic", "when-then-otherwise", "an-accessor-method", "a-condition"],
    )
    def test_a_states_own_read_written_around_still_answers(
        self, read: Callable[[ActuarialFrame], object], expected: list[float]
    ) -> None:
        """Each used to be refused: only the bare read was known to be the state's."""
        af, _compiled = _a_tracked_fund()
        _shocked(af)

        af.written_around = read(af)

        assert _kernel_calls(af) == 1
        assert af.collect()["written_around"].to_list()[0] == pytest.approx(expected)

    def test_a_stale_read_written_beside_a_states_own_is_refused(self) -> None:
        af, compiled = _a_tracked_fund()
        _shocked(af)

        with pytest.raises(ValueError, match="input 'fund_return' was written"):
            af.mixed = af.av.increments["growth"] + compiled.increment_for("growth")

    @pytest.mark.parametrize(
        "rewrite",
        [_fee_as_itself, _fee_times_one, _one_times_fee, _fee_as_itself_under_an_alias],
        ids=["itself", "times-one", "one-times-it", "itself-under-an-alias"],
    )
    def test_a_rewrite_that_plainly_keeps_the_values_is_no_move(
        self, rewrite: Callable[[ActuarialFrame], None]
    ) -> None:
        """Each used to be refused, though the run over the values is the same run."""
        af, compiled = _a_tracked_fund()
        rewrite(af)

        af.av_again = compiled.expr_for("av")

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av_again"].to_list() == result["av"].to_list()

    def test_times_one_that_changes_the_type_is_a_move(self) -> None:
        af, compiled = _a_fund_with_a_guarantee()
        af.anniversary = af.anniversary * 1

        with pytest.raises(ValueError, match="input 'anniversary' was written"):
            af.guarantee_again = compiled.expr_for("gmdb")

    def test_a_rewrite_not_plainly_the_same_is_a_move_and_says_why(self) -> None:
        af, compiled = _a_tracked_fund()
        af.fee = af.fee + 0

        with pytest.raises(ValueError, match="input 'fee' was written") as refusal:
            af.av_again = compiled.expr_for("av")

        message = str(refusal.value)
        assert "write this line before 'fee' is written again" in message
        assert "only where that is plain from how it is written" in message
        assert "af['fee'] times one in the same type" in message

    def test_projection_set_stamping_the_same_timeline_again_is_no_move(
        self,
    ) -> None:
        af, compiled = _a_fund_charged_its_projection_length()
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
        )

        af.av_again = compiled.expr_for("av")

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av_again"].to_list() == result["av"].to_list()

    def test_projection_set_stamping_another_timeline_is_a_move(self) -> None:
        af, compiled = _a_fund_charged_its_projection_length()
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=6, frequency="monthly"
        )

        with pytest.raises(ValueError, match="input 'num_proj_months' was written"):
            af.av_again = compiled.expr_for("av")

    def test_a_read_with_every_input_as_it_was_shares_the_run(self) -> None:
        af, compiled = _a_tracked_fund()
        af.other = af.av_init * 2

        af.av_again = compiled.expr_for("av")

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av_again"].to_list() == result["av"].to_list()

    def test_renaming_the_state_between_two_reads_keeps_one_run(self) -> None:
        af, compiled = _a_tracked_fund()
        af.rename({"av": "account_value"})

        af.av_again = compiled.expr_for("av")
        af.growth_credit = af.account_value.increments["growth"]

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av_again"].to_list() == result["account_value"].to_list()
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_a_state_written_over_its_opening_column_shares_the_run(self) -> None:
        """The write that reads the run is not an input moving under it."""
        af = ActuarialFrame(
            pl.DataFrame(
                {"av": [1000.0], "fund_return": [[0.01] * 3], "fee": [[5.0] * 3]}
            )
        )
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
        )
        b = af.projection.rollforward(states={"av": af["av"]}, track_increments=True)
        b["av"].grow(af["fund_return"], label="growth")
        b["av"].subtract(af["fee"], label="fee")
        compiled = compile_rollforward(b)
        af.av = compiled.expr_for("av")

        af.growth_credit = compiled.increment_for("growth")

        assert _kernel_calls(af) == 1
        result = af.collect()
        assert result["av"].to_list()[0] == pytest.approx([1005.0, 1010.05, 1015.1505])
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_a_rename_onto_an_input_between_two_reads_is_refused(self) -> None:
        af, compiled = _a_tracked_fund()
        af.other_return = af.fund_return * 10
        af.rename({"fund_return": "first_return", "other_return": "fund_return"})

        with pytest.raises(
            ValueError,
            match="input 'fund_return' was replaced by 'other_return', renamed onto it",
        ):
            af.av_after = compiled.expr_for("av")

    def test_the_move_the_refusal_names_runs(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.shocked_return = af.fund_return * 10
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].grow(af["shocked_return"], label="growth")
        b["av"].subtract(af["fee"], label="fee")

        af.av_shocked = compile_rollforward(b).expr_for("av")

        assert _kernel_calls(af) == 2
        result = af.collect()
        assert result["av"].to_list()[0] == pytest.approx([1005.0, 1010.05, 1015.1505])
        assert result["av_shocked"].to_list()[0] == pytest.approx(
            [1095.0, 1199.5, 1314.45]
        )


def _root_names_asked_for_by_reads(
    monkeypatch: pytest.MonkeyPatch, columns: int, reads: int
) -> int:
    """Count the expressions asked for their columns while a run is read.

    The frame is given ``columns`` columns of its own first, then a
    rollforward is compiled and read ``reads`` times.
    """
    from polars.expr.meta import ExprMetaNameSpace

    af = ActuarialFrame(
        pl.DataFrame(
            {"av_init": [1000.0], "fund_return": [[0.01] * 3], "fee": [[5.0] * 3]}
        )
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    for i in range(columns):
        af[f"c{i}"] = af.av_init * i
    b = af.projection.rollforward(states={"av": af["av_init"]}, track_increments=True)
    b["av"].grow(af["fund_return"], label="growth")
    b["av"].subtract(af["fee"], label="fee")
    compiled = compile_rollforward(b)

    asked = 0
    root_names = ExprMetaNameSpace.root_names

    def counted(namespace: ExprMetaNameSpace) -> list[str]:
        nonlocal asked
        asked += 1
        return root_names(namespace)

    monkeypatch.setattr(ExprMetaNameSpace, "root_names", counted)
    af.av = compiled.expr_for("av")
    for i in range(reads):
        af[f"read{i}"] = compiled.increment_for("growth")
    monkeypatch.setattr(ExprMetaNameSpace, "root_names", root_names)
    return asked


class TestReadingARunReadsTheLogOnce:
    """A read of a run looks only at what the log gained since the last read.

    Each read used to read the whole log again, asking every record which
    columns it reads: 52 reads after 600 columns asked 31,874 times, where
    the reads themselves ask a few hundred.
    """

    def test_the_cost_of_a_read_does_not_grow_with_the_log(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        small = _root_names_asked_for_by_reads(monkeypatch, columns=20, reads=20)
        large = _root_names_asked_for_by_reads(monkeypatch, columns=300, reads=20)

        assert large - small < 20

    def test_a_scenario_frame_carries_on_from_where_its_parent_stopped(
        self,
    ) -> None:
        af, compiled = _a_tracked_fund()
        af.again = compiled.expr_for("av")
        scenarios = with_scenarios(af, ["base", "shocked"])
        _shocked(scenarios)

        with pytest.raises(ValueError, match="input 'fund_return' was written"):
            scenarios.later = compiled.expr_for("av")

    def test_a_continued_frame_sees_an_input_changed_outside(self) -> None:
        af, compiled = _a_tracked_fund()
        af.again = compiled.expr_for("av")
        changed = af.collect().with_columns(
            pl.col("fund_return").list.eval(pl.element() * 10)
        )
        continued = ActuarialFrame(changed, continue_from=af)

        with pytest.raises(ValueError, match="input 'fund_return' was written"):
            continued.later = compiled.expr_for("av")


class TestStateAccessorsFollowTheColumnsDefinition:
    """The accessors read the state a column holds, and say so when it holds none.

    A rename is a name-move, so the renamed column still holds the state and
    reads its run. A column whose live definition is not a rollforward's
    state is refused with what that definition is, rather than being told it
    was never assigned from one when it was.
    """

    def test_a_renamed_state_reads_its_own_run(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.rename({"av": "account_value"})

        af.growth_credit = af.account_value.increments["growth"]
        af.after_growth = af.account_value.captures["after_growth"]

        result = af.collect()
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )
        assert result["after_growth"].to_list()[0] == pytest.approx(
            [1010.0, 1015.05, 1020.1505]
        )

    def test_a_state_renamed_twice_reads_its_own_run(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.rename({"av": "account_value"})
        af.rename({"account_value": "fund"})

        af.growth_credit = af.fund.increments["growth"]

        assert af.collect()["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_an_extraction_renamed_with_alias_reads_its_run(self) -> None:
        """``alias`` is a name, not a calculation: the column holds the state.

        A rename keeps the node of the extraction it renames, so the column
        is defined by the rollforward's read rather than by an expression
        around it, and its accessors read the run as the state's own do.
        """
        af, compiled = _a_tracked_fund()
        af.with_columns(compiled.expr_for("av").alias("av_copy"))

        af.growth_credit = af.av_copy.increments["growth"]

        assert af.collect()["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    def test_a_formula_over_the_state_says_it_is_a_formula(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.av = af.av * 1.0

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af.av.increments["growth"]

        assert "a formula of the model's own" in str(refusal.value)

    def test_a_column_the_data_arrived_with_says_so(self) -> None:
        af, _compiled = _a_tracked_fund()

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af.av_init.captures["after_growth"]

        assert "no definition of 'av_init', which arrived with the data" in str(
            refusal.value
        )

    def test_a_renamed_column_the_data_arrived_with_says_under_what(self) -> None:
        af, _compiled = _a_tracked_fund()
        af.rename({"av_init": "opening"})

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af.opening.captures["after_growth"]

        assert "'opening', which arrived with the data as 'av_init'" in str(
            refusal.value
        )

    def test_a_column_a_select_named_is_answered_as_an_assignment_is(self) -> None:
        """The select records the copy, as an assignment would, and says so."""
        af, _compiled = _a_tracked_fund()
        af.select(pl.all(), account_value=af.av)

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af.account_value.increments["growth"]

        message = str(refusal.value)
        assert "arrived with the data" not in message
        assert "defined by a formula of the model's own" in message

    def test_a_column_written_into_the_plan_says_it_was_never_recorded(self) -> None:
        """It used to say the column arrived with the data, which it did not."""
        af, _compiled = _a_tracked_fund()
        af._df = af._df.with_columns(pl.col("av").alias("account_value"))  # noqa: SLF001

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af["account_value"].increments["growth"]

        message = str(refusal.value)
        assert "arrived with the data" not in message
        assert "with no account of itself" in message
        assert "af._df = ..." in message

    def test_a_column_the_frame_does_not_hold_says_so(self) -> None:
        af, _compiled = _a_tracked_fund()

        with pytest.raises(ValueError, match="is not a rollforward's state") as refusal:
            af["account_value"].increments["growth"]

        message = str(refusal.value)
        assert "the frame holds no column of that name" in message
        assert "arrived with the data" not in message


def _a_fund_with_a_guarantee() -> tuple[ActuarialFrame, object]:
    """Return a two-state model whose guarantee ratchets to the fund."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "av_init": [1000.0],
                "g_init": [1000.0],
                "fund_return": [[0.05, 0.10, -0.2]],
                "anniversary": [[False, True, True]],
            }
        )
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(
        states={"fund": af["av_init"], "gmdb": af["g_init"]}, track_increments=True
    )
    b["fund"].grow(af["fund_return"], label="growth")
    b["gmdb"].ratchet(
        to=pl.col("fund@eop"), when=af["anniversary"], label="GMDB_ratchet"
    )
    compiled = compile_rollforward(b)
    af.fund = compiled.expr_for("fund")
    af.guarantee = compiled.expr_for("gmdb")
    return af, compiled


# Each state's balance and its own step's movement, for the model above.
_HELD = {
    "fund": ([1050.0, 1155.0, 924.0], "growth", [50.0, 105.0, -231.0]),
    "gmdb": ([1000.0, 1155.0, 1155.0], "GMDB_ratchet", [0.0, 155.0, 0.0]),
}


def _assert_each_reads_the_state_it_holds(
    af: ActuarialFrame, holds: dict[str, str]
) -> None:
    """Assert each column's accessors read the state the column now holds."""
    for column, state in holds.items():
        _balance, label, _movement = _HELD[state]
        af[f"{column}_at_eop"] = af[column].captures["eop"]
        af[f"{column}_moved"] = af[column].increments[label]
    result = af.collect()
    for column, state in holds.items():
        balance, _label, movement = _HELD[state]
        assert result[column].to_list()[0] == pytest.approx(balance)
        assert result[f"{column}_at_eop"].to_list()[0] == pytest.approx(balance)
        assert result[f"{column}_moved"].to_list()[0] == pytest.approx(movement)


class TestStateAccessorsFollowOneRenameCall:
    """One rename() moves every name it maps at once, and the accessors follow it.

    The call writes one record per name, all under one operation id. Followed
    back one record at a time, a swap or a chain read as a sequence of
    renames: after ``af.rename({"fund": "guarantee", "guarantee": "fund"})``,
    ``af.fund`` held the guarantee's balance and ``af.fund.captures["eop"]``
    answered the fund's, without a word.
    """

    @pytest.mark.parametrize(
        ("renames", "holds"),
        [
            (
                {"fund": "guarantee", "guarantee": "fund"},
                {"fund": "gmdb", "guarantee": "fund"},
            ),
            (
                {"fund": "guarantee", "guarantee": "benefit"},
                {"guarantee": "fund", "benefit": "gmdb"},
            ),
            (
                {"guarantee": "benefit", "fund": "guarantee"},
                {"guarantee": "fund", "benefit": "gmdb"},
            ),
        ],
        ids=["swap", "chain", "chain-written-the-other-way"],
    )
    def test_each_name_reads_the_state_it_now_holds(
        self, renames: dict[str, str], holds: dict[str, str]
    ) -> None:
        af, _compiled = _a_fund_with_a_guarantee()
        af.rename(renames)

        _assert_each_reads_the_state_it_holds(af, holds)

    def test_renames_in_two_calls_read_in_turn(self) -> None:
        af, _compiled = _a_fund_with_a_guarantee()
        af.rename({"guarantee": "benefit"})
        af.rename({"fund": "guarantee"})

        _assert_each_reads_the_state_it_holds(
            af, {"guarantee": "fund", "benefit": "gmdb"}
        )

    def test_a_step_of_the_state_a_swap_moved_names_where_it_went(self) -> None:
        af, _compiled = _a_fund_with_a_guarantee()
        af.rename({"fund": "guarantee", "guarantee": "fund"})

        with pytest.raises(ValueError, match="moves the state 'fund'") as refusal:
            af.fund.increments["growth"]

        message = str(refusal.value)
        assert "not 'gmdb', which af['fund'] holds" in message
        assert "af['guarantee'].increments['growth']" in message


class TestIncrementsReadOnlyTheirOwnStatesSteps:
    """A state's increments are the steps that move that state, and no others."""

    def test_a_step_that_moves_the_state_reads(self) -> None:
        af, _compiled = _a_fund_with_a_guarantee()

        af.ratchet = af.guarantee.increments["GMDB_ratchet"]
        af.growth_credit = af.fund.increments["growth"]

        result = af.collect()
        assert result["ratchet"].to_list()[0] == pytest.approx([0.0, 155.0, 0.0])
        assert result["growth_credit"].to_list()[0] == pytest.approx(
            [50.0, 105.0, -231.0]
        )

    def test_a_step_that_moves_another_state_is_refused(self) -> None:
        """It used to answer with the other state's movement, under this one's name."""
        af, _compiled = _a_fund_with_a_guarantee()

        with pytest.raises(ValueError, match="moves the state 'gmdb'") as refusal:
            af.fund.increments["GMDB_ratchet"]

        message = str(refusal.value)
        assert "not 'fund'" in message
        assert "af['guarantee'].increments['GMDB_ratchet']" in message
        assert "compiled.increment_for('GMDB_ratchet')" in message


def _written_over(af: ActuarialFrame) -> ActuarialFrame:
    """Write the state over straight in the query plan, past the frame's operations."""
    plan = af._df  # noqa: SLF001 -- the route under test
    assert plan is not None
    af._df = plan.with_columns(pl.col("av").list.eval(pl.element() * 0))  # noqa: SLF001
    return af


def _written_over_then_materialized(af: ActuarialFrame) -> ActuarialFrame:
    return _written_over(af).materialize()


def _rebuilt(af: ActuarialFrame) -> ActuarialFrame:
    return ActuarialFrame(af.collect())


def _untouched(af: ActuarialFrame) -> ActuarialFrame:
    return af


def _renamed_twice(af: ActuarialFrame) -> ActuarialFrame:
    af.rename({"av": "account_value"})
    af.rename({"account_value": "fund"})
    return af


def _written_over_then_renamed_twice(af: ActuarialFrame) -> ActuarialFrame:
    return _renamed_twice(_written_over(af))


def _renamed_then_written_over(af: ActuarialFrame) -> ActuarialFrame:
    af.rename({"av": "fund"})
    plan = af._df  # noqa: SLF001 -- the route under test
    assert plan is not None
    af._df = plan.with_columns(pl.col("fund").list.eval(pl.element() * 0))  # noqa: SLF001
    return af


def _input_written_again(af: ActuarialFrame) -> ActuarialFrame:
    return _shocked(af)


def _input_written_over_in_the_plan(af: ActuarialFrame) -> ActuarialFrame:
    plan = af._df  # noqa: SLF001 -- the route under test
    assert plan is not None
    af._df = plan.with_columns(  # noqa: SLF001
        pl.col("fund_return").list.eval(pl.element() * 10)
    )
    return af


def _rebuilt_then_renamed(af: ActuarialFrame) -> ActuarialFrame:
    return _rebuilt(af).rename({"av": "fund"})


_WRITTEN_OVER = "written straight into the query plan"
_CALCULATED_ELSEWHERE = "calculated on another frame"
_RUN_GONE = "no longer in the frame"


class TestStateAccessorsRefuseAColumnTheLogNoLongerAccountsFor:
    """A state's column the log's word no longer covers is refused, plainly.

    ``af.av.increments`` follows ``av``'s live definition to its run. Two
    columns hold values that definition is not the account of: one written
    straight into the query plan after it, and one a frame was built holding
    from another frame's collect. Either may still hold a state's numbers,
    and pairing it with a run's movements would pair a column with movements
    it does not hold.

    This sits beside the rule that a run the frame no longer holds is
    refused. The column's own account is read first, since a column the log
    cannot vouch for is no state whatever the plan holds; each refusal says
    its own thing, and neither stands in for the other.
    """

    def test_a_state_written_over_in_the_plan_names_the_write(self) -> None:
        af = _written_over(_a_tracked_fund()[0])

        for read in (
            lambda: af.av.increments["growth"],
            lambda: af.av.captures["after_growth"],
        ):
            with pytest.raises(ValueError, match=_WRITTEN_OVER) as refusal:
                read()
            assert "af.av = compiled.expr_for('av')" in str(refusal.value)

    def test_a_state_written_over_before_a_rename_names_the_write(self) -> None:
        """The rename is followed back, and what it carried was the write."""
        af = _written_over(_a_tracked_fund()[0])
        af.rename({"av": "account_value"})

        with pytest.raises(ValueError, match=_WRITTEN_OVER) as refusal:
            af.account_value.increments["growth"]

        assert "holds what 'av' held when it was renamed" in str(refusal.value)

    def test_a_state_a_frame_was_rebuilt_holding_names_where_it_was_made(
        self,
    ) -> None:
        af, _compiled = _a_tracked_fund()
        rebuilt = ActuarialFrame(af.collect())

        with pytest.raises(ValueError, match=_CALCULATED_ELSEWHERE) as refusal:
            rebuilt.av.increments["growth"]
        message = str(refusal.value)
        assert "av@1" in message
        assert "Read increments on that frame, before it is collected" in message
        with pytest.raises(ValueError, match=_CALCULATED_ELSEWHERE):
            rebuilt.av.captures["after_growth"]

    def test_the_move_the_rebuilt_refusal_names_answers(self) -> None:
        """Read on the frame that calculated it, before the collect."""
        af, _compiled = _a_tracked_fund()

        af.growth_credit = af.av.increments["growth"]
        values = af.collect()

        assert values["growth_credit"].to_list()[0] == pytest.approx(
            [10.0, 10.05, 10.1005]
        )

    @pytest.mark.parametrize(
        ("route", "column", "says"),
        [
            (_untouched, "av", None),
            (_written_over, "av", _WRITTEN_OVER),
            (_rebuilt, "av", _CALCULATED_ELSEWHERE),
            (_materialized, "av", _RUN_GONE),
            (_continued_with_input_changed_outside, "av", _RUN_GONE),
            (_written_over_then_materialized, "av", _WRITTEN_OVER),
            (_renamed_twice, "fund", None),
            (_written_over_then_renamed_twice, "fund", _WRITTEN_OVER),
            (_renamed_then_written_over, "fund", _WRITTEN_OVER),
            (_input_written_again, "av", None),
            (_input_written_over_in_the_plan, "av", None),
            (_rebuilt_then_renamed, "fund", _CALCULATED_ELSEWHERE),
        ],
        ids=[
            "untouched",
            "written-over",
            "rebuilt",
            "materialized",
            "continued",
            "written-over-then-materialized",
            "renamed-twice",
            "written-over-then-renamed-twice",
            "renamed-then-written-over",
            "input-written-again",
            "input-written-over-in-the-plan",
            "rebuilt-then-renamed",
        ],
    )
    def test_each_rule_answers_for_its_own_case(
        self,
        route: Callable[[ActuarialFrame], ActuarialFrame],
        column: str,
        says: str | None,
    ) -> None:
        """Each case answers, or is refused by exactly one rule.

        A state's own movements still answer from its run after one of the
        rollforward's inputs is written again, through the frame or straight
        into the plan: they are the run the state came from.
        """
        af = route(_a_tracked_fund()[0])

        if says is None:
            af.growth_credit = af[column].increments["growth"]
            assert af.collect()["growth_credit"].to_list()[0] == pytest.approx(
                [10.0, 10.05, 10.1005]
            )
            return
        with pytest.raises(ValueError, match=says) as refusal:
            af[column].increments["growth"]
        others = {_WRITTEN_OVER, _CALCULATED_ELSEWHERE, _RUN_GONE} - {says}
        assert not any(other in str(refusal.value) for other in others)

    def test_a_swapped_state_written_over_is_refused_and_its_partner_reads(
        self,
    ) -> None:
        """One rename call swaps the names, and only the written-over one is refused."""
        af, _compiled = _a_fund_with_a_guarantee()
        af.rename({"fund": "guarantee", "guarantee": "fund"})
        plan = af._df  # noqa: SLF001 -- the route under test
        assert plan is not None
        af._df = plan.with_columns(pl.col("fund").list.eval(pl.element() * 0))  # noqa: SLF001

        with pytest.raises(ValueError, match=_WRITTEN_OVER):
            af.fund.increments["GMDB_ratchet"]
        _assert_each_reads_the_state_it_holds(af, {"guarantee": "fund"})

    def test_a_state_written_over_is_not_offered_for_another_states_step(
        self,
    ) -> None:
        """The other-state refusal names a column only while it holds that state."""
        af, _compiled = _a_fund_with_a_guarantee()
        plan = af._df  # noqa: SLF001 -- the route under test
        assert plan is not None
        af._df = plan.with_columns(  # noqa: SLF001
            pl.col("guarantee").list.eval(pl.element() * 0)
        )

        with pytest.raises(ValueError, match="moves the state 'gmdb'") as refusal:
            af.fund.increments["GMDB_ratchet"]

        message = str(refusal.value)
        assert "af['guarantee']" not in message
        assert "af['gmdb'] = compiled.expr_for('gmdb')" in message


class TestAnInputWrittenOverInThePlanMovesTheRun:
    """A write over an input straight into the plan moves it, as an assignment does."""

    def test_a_read_after_the_write_is_refused_naming_it(self) -> None:
        af, compiled = _a_tracked_fund()
        _input_written_over_in_the_plan(af)

        with pytest.raises(
            ValueError, match="input 'fund_return' was written"
        ) as refusal:
            af.av_after = compiled.expr_for("av")

        assert "written again straight into the query plan" in str(refusal.value)
        assert "av_after" not in af.columns
