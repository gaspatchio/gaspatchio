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

**A ratchet is the movement schedule's sharpest row.** It moves the
benefit base on the anniversary and by nothing at all in between, so
the exported waterfall reads 0.00 for eleven months, the step-up at
month twelve, and 0.00 again — the step is quoted from the run rather
than worked out by whoever is reading it, and the eleven zeros are a
statement that nothing happened rather than an absence of one.

``main(af)`` takes the frame ``gspio`` builds from
``02_model_points.parquet``, so the same two states run under the CLI ——
``gspio calc-graph 02_multistate_ratchet.py 02_model_points.parquet`` ——
and the artifact carries what each step moved. The anniversary mask
rides the points beside the fund, exactly as it rode the frame the
script used to build for itself.

Reference: Bauer, Kling, Russ (2008), "A Universal Pricing Framework
for Guaranteed Minimum Benefits in Variable Annuities", *ASTIN
Bulletin* 38(2).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame, compile_rollforward

N_PERIODS = 60  # five years monthly

MODEL_POINTS = Path(__file__).with_name("02_model_points.parquet")


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Grow the fund, and ratchet the benefit base to it at each anniversary."""
    af = af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=N_PERIODS,
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
    # Both states read from ONE shared kernel call — the frame materialises
    # the rollforward struct once and each line extracts its field.
    af.fund = compiled.expr_for("fund")
    af.gmdb = compiled.expr_for("gmdb")
    return af


def demo() -> None:
    """Run the model over the shipped points and check the ratchet by hand."""
    out = main(ActuarialFrame(pl.read_parquet(MODEL_POINTS))).collect()
    fund = out.get_column("fund").to_list()[0]
    gmdb = out.get_column("gmdb").to_list()[0]
    initial = out.get_column("fund_init").to_list()[0]
    fund_return = out.get_column("rate").to_list()[0][0]
    anniv_mask = out.get_column("anniv").to_list()[0]

    # Fund grows geometrically at the monthly rate.
    for t in range(N_PERIODS):
        expected = initial * (1 + fund_return) ** (t + 1)
        assert abs(fund[t] - expected) < 1e-6, f"t={t}: fund {fund[t]} vs {expected}"

    # GMDB ratchets at every anniversary; flat between.
    last_anniv_idx = -1
    opening = out.get_column("gmdb_init").to_list()[0]
    for t in range(N_PERIODS):
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
            assert abs(gmdb[t] - opening) < 1e-6

    print("GMDB ratchet (Bauer/Kling/Russ 2008)")
    print(f"  Initial fund:       {initial:>12,.2f}")
    print(f"  Monthly return:     {fund_return:>12.4%}")
    print(f"  Terminal fund:      {fund[-1]:>12,.2f}")
    print(f"  Terminal GMDB:      {gmdb[-1]:>12,.2f}")
    print("  GMDB at anniversaries (months 12, 24, 36, 48, 60):")
    for t in range(11, N_PERIODS, 12):
        print(f"    month {t + 1:>2}: fund={fund[t]:>12,.2f}  gmdb={gmdb[t]:>12,.2f}")


if __name__ == "__main__":
    demo()
