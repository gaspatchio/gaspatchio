# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lapse stop-condition (GMWB-style fund depletion).

A Guaranteed Minimum Withdrawal Benefit (GMWB) projection terminates
naturally when the underlying fund is exhausted. The kernel's
``lapse_when_all_non_positive`` argument names states that — when *all*
of them go non-positive at the end of a period — flip the contract
into a stopped state. From that period onwards every state writes
zero and no further transitions accumulate.

This avoids spurious post-lapse cash flows in PV calculations and is
the canonical GMWB pricing convention: the rider pays the guaranteed
withdrawal stream until the underlying fund is exhausted, then the
contract terminates.

Two semantic notes worth memorising:

  1. The lapse-period state value is *not* clamped — if subtraction
     overshoots into negatives, that negative shows in the output for
     the lapse period. Only *subsequent* periods are zeroed.
  2. ``floor`` and ``lapse_when_all_non_positive`` interact: state
     touching zero (with or without a floor) is sufficient to trigger
     the stop condition — non-positive includes zero.

Reference: Milevsky and Salisbury (2006), "Financial Valuation of
Guaranteed Minimum Withdrawal Benefits", *Insurance: Mathematics
and Economics* 38(1).
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward


def main() -> None:
    n_periods = 12

    # AV starts at 50k, withdraw 6k/month — pure withdrawal, no growth.
    # t=0..7: 44k, 38k, 32k, 26k, 20k, 14k, 8k, 2k
    # t=8: 2k - 6k = -4k  (lapse fires, value preserved)
    # t=9..11: 0           (post-lapse zeros)
    av_init = 50_000.0
    monthly_withdrawal = 6_000.0

    af = ActuarialFrame(
        {
            "av_init": [av_init],
            "withdrawal": [[monthly_withdrawal] * n_periods],
        },
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=n_periods,
        frequency="monthly",
    )

    b = af.projection.rollforward(
        states={"av": af["av_init"]},
        lapse_when_all_non_positive=("av",),
    )
    b["av"].subtract(af["withdrawal"], label="withdrawal")

    compiled = compile_rollforward(b)
    collector = RollforwardCollector(compiled)
    af.av = collector.expr_for("av")
    av = af.collect().get_column("av").to_list()[0]

    # Pre-lapse periods: linear depletion.
    expected_pre = [av_init - monthly_withdrawal * (t + 1) for t in range(9)]
    for t, want in enumerate(expected_pre):
        assert abs(av[t] - want) < 1e-9, f"t={t}: {av[t]} vs {want}"

    # Lapse fires at t=8 (av=-4000). Periods 9, 10, 11 must be exactly 0.
    assert av[8] == -4_000.0
    for t in range(9, n_periods):
        assert av[t] == 0.0, f"t={t}: post-lapse {av[t]} should be 0"

    print("GMWB-style lapse stop (Milevsky/Salisbury 2006)")
    print(f"  Initial AV:         {av_init:>12,.2f}")
    print(f"  Monthly withdraw:   {monthly_withdrawal:>12,.2f}")
    print(f"  {'period':>6} {'av':>12}")
    for t in range(n_periods):
        marker = "  ← lapse" if t == 8 else ("  (zeroed)" if t > 8 else "")
        print(f"  {t + 1:>6} {av[t]:>12,.2f}{marker}")


if __name__ == "__main__":
    main()
