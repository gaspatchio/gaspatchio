# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gh#69 — track_increments=True emits real per-op deltas.
# ABOUTME: Replaces the interim refusal tests shipped by gh#98.

"""``track_increments=True`` emits signed per-op deltas (gh#69).

Every op contributes an ``increment_{key}`` struct field holding the delta it
actually applied to its target — negative for charges, positive for credits,
zero after a stop or lapse. Zero-after-lapse is the honest representation:
reconstructing flows from state differences conflates "no charge" with
"nothing left to charge against", which was silently wrong for 55 of 111
projection years in a universal-life model conversion.

A step the model's author named takes that name as its key. ``Floor`` and
``Round`` carry no label field and take the synthetic ``{kind}@{ordinal}``
the kernel builds from their position in the chain, so that no step of a
tracked rollforward goes unreported and ``closing = opening + Σ movements``
closes on quoted rows rather than on a derived residual.
"""

from __future__ import annotations

import datetime
from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._ops import increment_keys
from gaspatchio.schedule import Schedule


def _sched(n: int = 12) -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=n,
        frequency="1M",
    )


def _frame(**cols: object) -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], **cols}))
    n = max(
        len(v[0]) if isinstance(v, list) and isinstance(v[0], list) else 1
        for v in cols.values()
    )
    return af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=n, frequency="1Y"
    )


class TestEmission:
    def test_signed_deltas_per_labelled_op(self) -> None:
        """Add then Charge: increments are the applied flows, signed.

        t1: 0 + 100 = 100, *0.9 -> 90     inc_P=+100, inc_F=-10
        t2: 90 + 100 = 190, *0.9 -> 171   inc_P=+100, inc_F=-19
        """
        af = _frame(
            av_init=[0.0],
            premium=[[100.0, 100.0]],
            rate=[[0.1, 0.1]],
        )
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="Premium")
        b["av"].charge(af["rate"], label="Fee")

        compiled = compile_rollforward(b)
        af.eop = compiled.expr_for("av")
        af.inc_p = compiled.increment_for("Premium")
        af.inc_f = compiled.increment_for("Fee")
        out = af.collect()

        assert out["eop"][0].to_list() == pytest.approx([90.0, 171.0])
        assert out["inc_p"][0].to_list() == pytest.approx([100.0, 100.0])
        assert out["inc_f"][0].to_list() == pytest.approx([-10.0, -19.0])

    def test_deduct_nar_increment_is_the_negated_coi(self) -> None:
        """The COI read straight from the kernel's applied delta.

        BOP: NAR = 10000 - 1000 = 9000; COI = 9000 * 0.001 = 9.0.
        """
        af = _frame(av_init=[1000.0], coi=[[0.001]], db=[[10000.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].deduct_nar(af["coi"], death_benefit=af["db"], label="COI")

        compiled = compile_rollforward(b)
        af.inc = compiled.increment_for("COI")
        out = af.collect()
        assert out["inc"][0].to_list() == pytest.approx([-9.0])

    def test_increments_zero_after_lapse(self) -> None:
        """Post-lapse periods read zero — applied, not notional (gh#69).

        Withdrawals drive the state non-positive at t2; the lapse stop
        fires and t3's increment is zero because the kernel applied
        nothing.
        """
        af = _frame(av_init=[100.0], w=[[50.0, 60.0, 50.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]},
            track_increments=True,
            lapse_when_all_non_positive=["av"],
        )
        b["av"].subtract(af["w"], label="Withdrawal")

        compiled = compile_rollforward(b)
        af.inc = compiled.increment_for("Withdrawal")
        out = af.collect()
        assert out["inc"][0].to_list() == pytest.approx([-50.0, -60.0, 0.0])


class TestStructuralSteps:
    """Every step emits, and the two with no label emit under `kind@ordinal`.

    A chain whose last step is a floor used to yield one movement fewer
    than it has steps, and the amount the floor absorbed -- the one number an
    account value that would have gone negative is audited by -- was on no
    file at all. The key is the kernel's, so that the row is quoted rather
    than derived from what the other rows do not explain.
    """

    def test_a_floor_that_bites_reports_what_it_absorbed(self) -> None:
        """100 - 60 = 40; 40 - 60 = -20, floored back to 0 by +20."""
        af = _frame(av_init=[100.0], draw=[[60.0, 60.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["draw"], label="drawdown").floor(value=0.0)

        compiled = compile_rollforward(b)
        af.eop = compiled.expr_for("av")
        af.inc_draw = compiled.increment_for("drawdown")
        af.inc_floor = compiled.increment_for("floor@2")
        out = af.collect()

        assert out["eop"][0].to_list() == pytest.approx([40.0, 0.0])
        assert out["inc_draw"][0].to_list() == pytest.approx([-60.0, -60.0])
        assert out["inc_floor"][0].to_list() == pytest.approx([0.0, 20.0])

    def test_a_floor_that_never_bites_reports_zero_in_every_period(self) -> None:
        """The field is there either way: absent and all-zero say different things."""
        af = _frame(av_init=[100.0], draw=[[10.0, 10.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["draw"], label="drawdown").floor(value=0.0)

        compiled = compile_rollforward(b)
        af.inc_floor = compiled.increment_for("floor@2")
        out = af.collect()
        assert out["inc_floor"][0].to_list() == pytest.approx([0.0, 0.0])

    def test_a_round_reports_the_rounding_delta(self) -> None:
        """100 - 33.333 = 66.667 -> 66.67, so the round put back +0.003."""
        af = _frame(av_init=[100.0], draw=[[33.333, 33.333]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["draw"], label="drawdown").round(decimals=2)

        compiled = compile_rollforward(b)
        af.eop = compiled.expr_for("av")
        af.inc_round = compiled.increment_for("round@2")
        out = af.collect()

        assert out["eop"][0].to_list() == pytest.approx([66.67, 33.34])
        assert out["inc_round"][0].to_list() == pytest.approx([0.003, 0.003])

    def test_a_chain_carrying_both_names_each_by_its_own_ordinal(self) -> None:
        """The ordinal is the step's 1-based position in the declared chain.

        The same number the artifact's ``increments`` array lists against the
        step, so a waterfall row and a summary entry name one step.
        """
        af = _frame(av_init=[100.0], draw=[[33.333]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["draw"], label="drawdown").floor(value=0.0).round(
            decimals=2
        )

        compiled = compile_rollforward(b)
        assert increment_keys(compiled.ir.transitions) == (
            "drawdown",
            "floor@2",
            "round@3",
        )
        af.inc_floor = compiled.increment_for("floor@2")
        af.inc_round = compiled.increment_for("round@3")
        out = af.collect()
        assert out["inc_floor"][0].to_list() == pytest.approx([0.0])
        assert out["inc_round"][0].to_list() == pytest.approx([0.003])

    def test_a_chain_with_no_structural_step_keeps_the_shape_it_had(self) -> None:
        """A fully labelled chain emits what it emitted before, in that order."""
        af = _frame(av_init=[0.0], premium=[[100.0, 100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="Premium")
        b["av"].subtract(af["premium"], label="Withdrawal")

        compiled = compile_rollforward(b)
        assert increment_keys(compiled.ir.transitions) == ("Premium", "Withdrawal")
        af.inc_p = compiled.increment_for("Premium")
        af.inc_w = compiled.increment_for("Withdrawal")
        out = af.collect()
        assert out["inc_p"][0].to_list() == pytest.approx([100.0, 100.0])
        assert out["inc_w"][0].to_list() == pytest.approx([-100.0, -100.0])

    def test_the_increments_sum_to_the_period_change_in_the_balance(self) -> None:
        """The rollforward's check line, on the kernel's own rows, with no residual.

        Opening at t is closing at t-1, with the initial state in front. The
        floor bites in the second period, so a chain tracking only its
        labelled step would miss the balance by the amount it absorbed.
        """
        af = _frame(av_init=[100.0], draw=[[60.0, 60.0, 10.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["draw"], label="drawdown").floor(value=0.0)

        compiled = compile_rollforward(b)
        af.eop = compiled.expr_for("av")
        af.inc_draw = compiled.increment_for("drawdown")
        af.inc_floor = compiled.increment_for("floor@2")
        out = af.collect()

        closing = out["eop"][0].to_list()
        movements = zip(out["inc_draw"][0].to_list(), out["inc_floor"][0].to_list())
        opening = 100.0
        for period, (close, (drawn, floored)) in enumerate(zip(closing, movements)):
            assert close - opening == pytest.approx(drawn + floored, abs=1e-12), (
                f"period {period}"
            )
            opening = close


class TestGates:
    def test_a_label_carrying_the_reserved_character_is_refused(self) -> None:
        """`@` is the kernel's own, and a label free to spell it collides."""
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="fund@1")
        with pytest.raises(ValueError, match="is reserved"):
            compile_rollforward(b)

    def test_the_reserved_character_is_refused_without_tracking_too(self) -> None:
        """The reservation is about the vocabulary, not about the flag.

        A label accepted while tracking is off and refused the moment it is
        switched on would make that flag a breaking change to a model that
        already ran.
        """
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].add(af["premium"], label="fund@1")
        with pytest.raises(ValueError, match="is reserved"):
            compile_rollforward(b)

    def test_unknown_label_names_the_available_ones(self) -> None:
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="Premium")
        compiled = compile_rollforward(b)
        with pytest.raises(KeyError, match="Premium"):
            compiled.increment_for("premium")  # case matters; message helps

    def test_increment_for_without_flag_points_at_the_flag(self) -> None:
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].add(af["premium"], label="Premium")
        compiled = compile_rollforward(b)
        with pytest.raises(ValueError, match="track_increments=True"):
            compiled.increment_for("Premium")

    def test_increment_handle_without_flag_points_at_the_flag(self) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=_sched(),
        )
        with pytest.raises(ValueError, match="track_increments=True"):
            b.increment("Premium")

    def test_unlabelled_op_refused_at_compile(self) -> None:
        """The gh#98 label gate survives: tracking needs labels."""
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"])  # no label
        with pytest.raises(ValueError, match="label"):
            compile_rollforward(b)

    def test_duplicate_labels_refused_at_compile(self) -> None:
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="X")
        b["av"].subtract(af["premium"], label="X")
        with pytest.raises(ValueError, match="duplicate op label"):
            compile_rollforward(b)

    def test_flag_default_off_and_builds(self) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=_sched(),
        )
        assert b._track_increments is False


class TestTheIncrementIsTheMovement:
    """``increment_for`` reports ``after - before``, not the operand (spec 16.2).

    ul-r7 read ``151.6199999999999`` for an interest credit rounded to 151.62
    and took it for a defect against the docstring's "what the op actually
    applied". The specification rules the movement, so the docstring now says
    so; this pins the contract both ways round.
    """

    def test_a_rounded_credit_reports_the_balance_movement(self) -> None:
        opening = 2238.2200000000003
        premium = 2500.0
        af = ActuarialFrame(
            {"av0": [opening], "prem": [[premium] * 2], "rate": [[0.032] * 2]}
        )
        af = af.projection.set(
            start_date=datetime.date(2026, 1, 31), n_periods=2, frequency="annual"
        )
        rf = af.projection.rollforward(states={"av": af["av0"]}, track_increments=True)
        rf["av"].add(af["prem"], label="premium").grow(
            af["rate"], round_charge=2, label="interest"
        )
        compiled = compile_rollforward(rf)
        af.av = compiled.expr_for("av")
        af.interest = compiled.increment_for("interest")
        af.premium = compiled.increment_for("premium")
        row = af.collect().row(0, named=True)

        before = opening + premium
        credited = round(before * 0.032, 2)
        assert credited == 151.62
        assert row["interest"][0] == (before + credited) - before
        assert row["interest"][0] != credited
        # ...which is what lets the period's increments close the balance.
        assert row["av"][0] == opening + row["premium"][0] + row["interest"][0]
