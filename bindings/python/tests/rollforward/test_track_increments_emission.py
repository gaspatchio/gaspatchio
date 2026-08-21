# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gh#69 — track_increments=True emits real per-op deltas.
# ABOUTME: Replaces the interim refusal tests shipped by gh#98.

"""``track_increments=True`` emits signed per-op deltas (gh#69).

Each labelled op contributes an ``increment_{label}`` struct field holding
the delta it actually applied to its target — negative for charges, positive
for credits, zero after a stop or lapse. Zero-after-lapse is the honest
representation: reconstructing flows from state differences conflates "no
charge" with "nothing left to charge against", which was silently wrong for
55 of 111 projection years in the clean-room UL conversion.
"""

from __future__ import annotations

import datetime
from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.rollforward._builder import RollforwardBuilder
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


class TestGates:
    def test_unknown_label_names_the_available_ones(self) -> None:
        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="Premium")
        compiled = compile_rollforward(b)
        with pytest.raises(KeyError, match="Premium"):
            compiled.increment_for("premium")  # case matters; message helps

    def test_collector_unknown_label_refused_immediately(self) -> None:
        """The deprecated facade validates like the compiled path.

        Without this, an unknown label sails through to Polars collect and
        dies as a missing struct field, far from the call that asked (the
        gh#93 rule: refuse at the call, naming the valid labels).
        """
        from gaspatchio.rollforward._collector import RollforwardCollector

        af = _frame(av_init=[0.0], premium=[[100.0]])
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].add(af["premium"], label="Premium")
        collector = RollforwardCollector(compile_rollforward(b))
        with pytest.raises(KeyError, match="Premium"):
            collector.increment_for("premium")

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
