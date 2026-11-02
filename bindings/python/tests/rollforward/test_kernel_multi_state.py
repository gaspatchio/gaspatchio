# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end multi-state §4.7 VA + GMDB ratchet path.

Exercises the kernel's multi-point seeding and chain semantics:
- 3 declared points (bop, after_growth, eop)
- Two states (av, guarantee), each with its own Op chain
- between(p1, p2) scoping for av (grow during bop->after_growth, floor during
  after_growth->eop)
- Ratchet with when= conditional firing on the guarantee state
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule
from tests.rollforward.conftest import _standalone_state_expr


class TestVaGmdbRatchet:
    def test_av_grows_guarantee_ratchets_at_anniversary(self) -> None:
        # 12-period schedule; anniversary fires only at period 11 (t=11)
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init"), "guarantee": pl.col("av_init")},
            points=["bop", "after_growth", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "after_growth").grow(pl.col("fund_return"), label="G")
        b["av"].between("after_growth", "eop").floor(0.0)
        b["guarantee"].grow(pl.col("roll_up"), label="RollUp")
        b["guarantee"].ratchet(
            to=pl.col("av_after_growth"),
            when=pl.col("anniv"),
            label="GMDB",
        )
        compiled = compile_rollforward(b)

        # Single policy; constant 1% fund return, 4%/12 monthly roll-up,
        # av-after-growth placeholder = 130.0 at anniversary.
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "fund_return": [[0.01] * 12],
                "roll_up": [[0.04 / 12] * 12],
                "av_after_growth": [[101.0] * 11 + [130.0]],
                "anniv": [[False] * 11 + [True]],
            }
        )
        result = df.with_columns(
            av=_standalone_state_expr(compiled, "av"),
            g=_standalone_state_expr(compiled, "guarantee"),
        )
        # AV: 100 -> grow by 1% each period -> 100 * 1.01^12 ≈ 112.68
        av = result.get_column("av").to_list()[0]
        assert av[-1] == pytest.approx(100 * 1.01**12, rel=1e-9)
        # Guarantee rolls up at 4%/12 per month for 12 months → 100 * (1+0.04/12)^12
        # then ratchets to 130 at the final anniversary.
        g = result.get_column("g").to_list()[0]
        # Period 0: roll_up gives 100*(1+0.04/12) ≈ 100.333; anniv False → no ratchet
        assert g[0] == pytest.approx(100 * (1 + 0.04 / 12), rel=1e-9)
        # Period 11: rolled-up value is 100 * (1+0.04/12)^12 ≈ 104.07; anniv fires →
        # max(104.07, 130) = 130.0
        assert g[-1] == pytest.approx(130.0, rel=1e-9)


class TestDeductNAR:
    def test_coi_charged_against_net_amount_at_risk(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=2,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            schedule=sched,
        )
        b["av"].deduct_nar(pl.col("coi"), death_benefit=pl.col("db"), label="COI")
        compiled = compile_rollforward(b)

        # av=100, coi=0.01, db=200 → NAR=100 → charge=0.01*100=1.0 → av=99
        # Period 1: av=99, coi=0.01, db=200 → NAR=101 → charge=1.01 → av=97.99
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "coi": [[0.01, 0.01]],
                "db": [[200.0, 200.0]],
            }
        )
        av = (
            df.with_columns(av=_standalone_state_expr(compiled, "av"))
            .get_column("av")
            .to_list()[0]
        )
        assert av[0] == pytest.approx(99.0, rel=1e-9)
        assert av[1] == pytest.approx(97.99, rel=1e-9)


class TestGrowCapped:
    def test_rate_clamped_to_floor_and_cap(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            schedule=sched,
        )
        b["av"].grow_capped(
            pl.col("rate"),
            floor=pl.col("floor"),
            cap=pl.col("cap"),
            label="G",
        )
        compiled = compile_rollforward(b)

        # rates [-0.5, 0.05, 1.0] clamped to [-0.10, 0.20]:
        # period 0: clamped=-0.10 → av *= 0.90 → 90
        # period 1: clamped= 0.05 → av *= 1.05 → 94.5
        # period 2: clamped= 0.20 → av *= 1.20 → 113.4
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "rate": [[-0.5, 0.05, 1.0]],
                "floor": [[-0.1, -0.1, -0.1]],
                "cap": [[0.2, 0.2, 0.2]],
            }
        )
        av = (
            df.with_columns(av=_standalone_state_expr(compiled, "av"))
            .get_column("av")
            .to_list()[0]
        )
        assert av == pytest.approx([90.0, 94.5, 113.4], rel=1e-9)


_NAMED_OPERATIONS = (
    "add",
    "subtract",
    "charge",
    "grow",
    "grow_capped",
    "deduct_nar",
    "ratchet",
    "floor",
    "round",
)


def _two_period_builder(*, track_increments: bool = False) -> RollforwardBuilder:
    return RollforwardBuilder(
        states={"av": pl.col("av_init")},
        schedule=Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=2,
            frequency="1M",
        ),
        track_increments=track_increments,
    )


def _assert_the_apply_refusal(message: str) -> None:
    """Assert the refusal names the step, why it cannot run, and what to write."""
    assert ".apply()" in message
    assert "'av'" in message
    assert "no evaluation" in message
    for operation in _NAMED_OPERATIONS:
        assert operation in message
    assert "as a column of the frame before the rollforward" in message
    # Setting the balance outright is what the step does, and no named
    # operation does it, so the refusal says so and names the composition
    # that does: take the balance off, then add the new value.
    assert "none of them sets the balance outright" in message
    assert ".subtract(pl.col('av@eop')).add(" in message


class TestApplyIsRefusedAtCompile:
    """The kernel has no evaluation for Apply, so the compiler refuses it.

    It used to compile, and every collect() then failed inside the kernel
    with "Apply is an escape hatch and is not yet evaluable by the kernel":
    the model learned at the end of a run that a step it had been allowed to
    write never runs. compile_rollforward says so before anything is built,
    and names what to write instead.
    """

    @pytest.mark.parametrize(
        "body",
        [pl.col("override"), pl.col("override") * -1],
        ids=["bare-column", "expression"],
    )
    def test_apply_is_refused_with_the_operations_to_use_instead(
        self, body: pl.Expr
    ) -> None:
        """Whatever the body, the refusal is about Apply, not its shape."""
        b = _two_period_builder()
        b["av"].apply(body, label="Override")

        with pytest.raises(NotImplementedError) as refusal:
            compile_rollforward(b)

        _assert_the_apply_refusal(str(refusal.value))
        assert "label='Override'" in str(refusal.value)

    def test_the_refusal_comes_before_a_label_tracking_would_ask_for(self) -> None:
        """A tracked rollforward is not sent to label a step that never runs."""
        b = _two_period_builder(track_increments=True)
        b["av"].apply(pl.col("override"))

        with pytest.raises(NotImplementedError) as refusal:
            compile_rollforward(b)

        _assert_the_apply_refusal(str(refusal.value))

    def test_an_ir_carrying_apply_is_refused_without_the_builder(self) -> None:
        """compile_rollforward takes an IR as well, and refuses it the same way."""
        b = _two_period_builder()
        b["av"].apply(pl.col("override"), label="Override")

        with pytest.raises(NotImplementedError) as refusal:
            compile_rollforward(b._build())

        _assert_the_apply_refusal(str(refusal.value))

    def test_the_kernel_lowering_never_emits_apply(self) -> None:
        """The lowering refuses it too, so no path hands the kernel an Apply."""
        from gaspatchio.rollforward._passes import (
            AssignCaptureSlots,
            LowerToPolarsPlugin,
        )

        b = _two_period_builder()
        b["av"].apply(pl.col("override"), label="Override")
        ir, slots = AssignCaptureSlots().apply_with_slots(b._build())

        with pytest.raises(NotImplementedError) as refusal:
            LowerToPolarsPlugin().lower(ir, slots)

        _assert_the_apply_refusal(str(refusal.value))

    def test_a_frame_that_compiles_an_apply_is_left_as_it_was(self) -> None:
        """The refusal lands before expr_for, so nothing reaches the frame."""
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "av_init": [1000.0],
                    "fund_return": [[0.01] * 3],
                    "fee": [[5.0] * 3],
                }
            )
        )
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
        )
        columns_before = list(af.columns)
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].grow(af["fund_return"], label="growth").apply(af["fee"], label="fee")

        with pytest.raises(NotImplementedError) as refusal:
            compile_rollforward(b)

        _assert_the_apply_refusal(str(refusal.value))
        assert "label='fee'" in str(refusal.value)
        assert list(af.columns) == columns_before

    def test_the_named_operation_it_points_to_runs(self) -> None:
        """The fee the repro meant to take off is a subtract, and it runs."""
        b = _two_period_builder()
        b["av"].subtract(pl.col("fee"), label="fee")
        compiled = compile_rollforward(b)

        df = pl.DataFrame({"av_init": [100.0], "fee": [[5.0, 5.0]]})
        av = (
            df.with_columns(av=_standalone_state_expr(compiled, "av"))
            .get_column("av")
            .to_list()[0]
        )
        assert av == pytest.approx([95.0, 90.0])

    def test_setting_the_balance_outright_is_a_subtract_and_an_add(self) -> None:
        """The composition the refusal names sets the balance, booking both moves.

        Subtracting the running balance itself clears it, and adding the column
        then sets it: each period closes at the column's value, and the
        tracked movements say what was taken off and what was put on.
        """
        b = _two_period_builder(track_increments=True)
        b["av"].subtract(pl.col("av@eop"), label="clear").add(
            pl.col("reset_to"), label="set"
        )
        compiled = compile_rollforward(b)

        df = pl.DataFrame({"av_init": [100.0], "reset_to": [[50.0, 60.0]]})
        struct = compiled.plugin_expr()
        result = df.with_columns(
            av=_standalone_state_expr(compiled, "av"),
            cleared=struct.struct.field("increment_clear"),
        )
        assert result.get_column("av").to_list()[0] == pytest.approx([50.0, 60.0])
        assert result.get_column("cleared").to_list()[0] == pytest.approx(
            [-100.0, -50.0]
        )

    def test_the_specification_says_the_producer_writes_no_apply(self) -> None:
        """Section 16 states what the compiler does, beside the reading it keeps.

        The format still names Apply, so a reader must still accept one; what
        the specification says of this producer has to match the refusal
        above, or a reader would go looking for an Apply it can never meet.
        """
        specification = (
            Path(__file__).resolve().parents[4]
            / "spec"
            / "graph-artifact"
            / "v0-preview.md"
        ).read_text(encoding="utf-8")

        rollforward = specification[specification.index("## 16. Rollforward") :]
        assert "**The reference producer writes no `Apply`.**" in rollforward
        assert "a reader still accepts an `Apply`" in rollforward

        b = _two_period_builder()
        b["av"].apply(pl.col("override"), label="Override")
        with pytest.raises(NotImplementedError, match="no evaluation"):
            compile_rollforward(b)

    def test_the_composition_sets_a_finite_balance_and_says_where_it_stops(
        self,
    ) -> None:
        """Subtract-then-add sets a finite balance; a non-finite one stays NaN.

        inf - inf is NaN, so a balance that has run to infinity comes out NaN
        where setting it outright would give the new value. Every place that
        names the composition says it holds for a finite balance.
        """
        from gaspatchio.rollforward._ops import Apply
        from gaspatchio.rollforward._passes import _apply_refusal
        from gaspatchio.rollforward._refs import StateRef

        b = _two_period_builder()
        b["av"].grow(pl.col("r"), label="growth").subtract(
            pl.col("av@eop"), label="clear"
        ).add(pl.col("reset_to"), label="set")
        compiled = compile_rollforward(b)
        df = pl.DataFrame(
            {
                "av_init": [100.0, 100.0],
                "r": [[0.5, 0.0], [float("inf"), 0.0]],
                "reset_to": [[50.0, 60.0], [50.0, 60.0]],
            }
        )
        av = df.with_columns(av=_standalone_state_expr(compiled, "av"))["av"]
        assert av.to_list()[0] == pytest.approx([50.0, 60.0])
        assert all(math.isnan(value) for value in av.to_list()[1])

        refusal = str(
            _apply_refusal(
                Apply(target=StateRef(state="av", point="eop"), body=pl.col("x"))
            )
        )
        assert "finite balance" in refusal
        assert "finite balance" in (Apply.__doc__ or "")
        assert "finite balance" in (_apply_refusal.__doc__ or "")
        assert "finite balance" in (type(b["av"]).apply.__doc__ or "")
