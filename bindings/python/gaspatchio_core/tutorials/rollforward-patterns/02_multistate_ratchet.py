# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Multi-state GMDB ratchet (Bauer/Kling/Russ 2008).

A GMxB rider attaches a guaranteed minimum benefit to a separate-account
variable annuity. The benefit base ratchets to the fund's high-water
mark on each policy anniversary:

    fund_eop  = fund_bop * (1 + return)
    gmdb_eop  = max(gmdb_bop, fund_eop)   if anniversary
              = gmdb_bop                  otherwise

This uses a *cross-state read*: GMDB's transition reads the fund's
eop value within the same period via ``pl.col("fund@eop")``. The
kernel resolves that against the live state vector — no precomputed
input column required.

Reference: Bauer, Kling, Russ (2008), "A Universal Pricing Framework
for Guaranteed Minimum Benefits in Variable Annuities", *ASTIN
Bulletin* 38(2).
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward


def main() -> None:
    n_periods = 60  # five years monthly
    fund_return = 0.008  # 0.8% monthly ≈ 10% annual

    # Anniversary fires at end-of-month 12, 24, 36, 48, 60 (1-indexed).
    anniv_mask = [(t + 1) % 12 == 0 for t in range(n_periods)]

    af = ActuarialFrame(
        {
            "fund_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "rate": [[fund_return] * n_periods],
            "anniv": [anniv_mask],
        },
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=n_periods,
        frequency="monthly",
    )

    b = af.projection.rollforward(
        states={
            "fund": af["fund_init"],
            "gmdb": af["gmdb_init"],
        },
    )
    b["fund"].grow(af["rate"], label="fund_growth")
    b["gmdb"].ratchet(
        to=pl.col("fund@eop"),
        when=af["anniv"],
        label="GMDB_ratchet",
    )

    compiled = compile_rollforward(b)
    collector = RollforwardCollector(compiled)
    af.fund = collector.expr_for("fund")
    af.gmdb = collector.expr_for("gmdb")
    out = af.collect()
    fund = out.get_column("fund").to_list()[0]
    gmdb = out.get_column("gmdb").to_list()[0]

    # Fund grows geometrically at 0.8%/month.
    for t in range(n_periods):
        expected = 100_000.0 * (1 + fund_return) ** (t + 1)
        assert abs(fund[t] - expected) < 1e-6, f"t={t}: fund {fund[t]} vs {expected}"

    # GMDB ratchets at every anniversary; flat between.
    last_anniv_idx = -1
    for t in range(n_periods):
        if anniv_mask[t]:
            last_anniv_idx = t
            assert abs(gmdb[t] - fund[t]) < 1e-6, (
                f"t={t} (anniv): gmdb {gmdb[t]} should equal fund {fund[t]}"
            )
        elif last_anniv_idx >= 0:
            assert abs(gmdb[t] - fund[last_anniv_idx]) < 1e-6, (
                f"t={t}: gmdb {gmdb[t]} should hold {fund[last_anniv_idx]}"
            )
        else:
            assert abs(gmdb[t] - 100_000.0) < 1e-6

    print("GMDB ratchet (Bauer/Kling/Russ 2008)")
    print(f"  Initial fund:       {100_000.0:>12,.2f}")
    print(f"  Monthly return:     {fund_return:>12.4%}")
    print(f"  Terminal fund:      {fund[-1]:>12,.2f}")
    print(f"  Terminal GMDB:      {gmdb[-1]:>12,.2f}")
    print("  GMDB at anniversaries (months 12, 24, 36, 48, 60):")
    for t in range(11, n_periods, 12):
        print(f"    month {t + 1:>2}: fund={fund[t]:>12,.2f}  gmdb={gmdb[t]:>12,.2f}")


if __name__ == "__main__":
    main()
