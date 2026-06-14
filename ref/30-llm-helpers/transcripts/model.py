# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Hello World — gaspatchio Level 1

Concepts covered:
  1. ActuarialFrame        — the projection container
  2. Column arithmetic     — defining cashflow formulas
  3. list_conditional      — element-wise when/then on projection vectors
  4. accumulate            — linear recurrence for policy reserves
  5. collect               — materialise and inspect results
"""

import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.functions.vector import accumulate, list_conditional

# ---------------------------------------------------------------------------
# 1.  Model points  (one row per policy)
# ---------------------------------------------------------------------------
PROJECTION_MONTHS = 60  # 5-year projection horizon

model_points = {
    "policy_id":       ["P001",    "P002",    "P003"],
    "age":             [35,        45,        55],
    "sum_assured":     [100_000.0, 200_000.0, 150_000.0],
    "annual_premium":  [1_200.0,   2_400.0,   2_100.0],
    "term_months":     [60,        36,        24],         # premium payment term
    # Projection timeline: list of monthly timesteps per policy
    "t": [[i for i in range(PROJECTION_MONTHS)]] * 3,
}

af = ActuarialFrame(model_points)

# ---------------------------------------------------------------------------
# 2.  Monthly premium cashflows
#     Pay annual_premium / 12 each month while t < term_months, then 0.
# ---------------------------------------------------------------------------
af = af.with_columns(
    list_conditional(
        pl.col("t"),
        pl.col("term_months"),
        then_val=pl.col("annual_premium") / 12,
        otherwise_val=pl.lit(0.0),
        operator="lt",
    ).alias("monthly_premium")
)

# ---------------------------------------------------------------------------
# 3.  Death benefit cashflow
#     Simplified: sum_assured paid only in the final projection month.
#     (In a real model you'd weight by monthly mortality probability.)
# ---------------------------------------------------------------------------
last_t = PROJECTION_MONTHS - 1
af = af.with_columns(
    list_conditional(
        pl.col("t"),
        pl.lit(last_t),
        then_val=pl.col("sum_assured"),
        otherwise_val=pl.lit(0.0),
        operator="eq",
    ).alias("death_benefit")
)

# ---------------------------------------------------------------------------
# 4.  Discount factors  (flat 5 % p.a. monthly)
#     v(t) = (1 / (1 + 0.05/12)) ^ t
#     Build as a list column of constant v values, then accumulate.
# ---------------------------------------------------------------------------
monthly_rate = 0.05 / 12
v = 1.0 / (1 + monthly_rate)

# _v_factor: list of [v, v, v, ...] — one per projection month, same for all rows
af = af.with_columns(
    pl.lit([v] * PROJECTION_MONTHS).alias("_v_factor")
)

# _zeros: list of 0.0 additive flows (no additions for pure compounding)
af = af.with_columns(
    pl.lit([0.0] * PROJECTION_MONTHS).alias("_zeros")
)

# Cumulative discount: v^t using native Polars list.eval (no Python UDF)
af = af.with_columns(
    pl.col("t")
    .list.eval(pl.lit(v) ** pl.element().cast(pl.Float64))
    .alias("discount_factor")
)

# ---------------------------------------------------------------------------
# 5.  Present values
#     PV(premium) = sum of monthly_premium[t] * discount_factor[t]
#     PV(benefit) = sum of death_benefit[t]  * discount_factor[t]
# ---------------------------------------------------------------------------
af = af.with_columns(
    (pl.col("monthly_premium") * pl.col("discount_factor"))
    .list.sum()
    .alias("pv_premiums"),

    (pl.col("death_benefit") * pl.col("discount_factor"))
    .list.sum()
    .alias("pv_benefits"),
)

af = af.with_columns(
    (pl.col("pv_benefits") - pl.col("pv_premiums")).alias("net_liability")
)

# ---------------------------------------------------------------------------
# 6.  Collect and display
# ---------------------------------------------------------------------------
result = af.collect()

print("\n=== Hello World — gaspatchio Level 1 ===\n")

print("── Model points ──────────────────────────────")
print(result.select(["policy_id", "age", "sum_assured", "annual_premium", "term_months"]))

print("\n── Premium cashflows (first 5 months, P001 vs P002) ──")
for pid in ["P001", "P002"]:
    row = result.filter(pl.col("policy_id") == pid).row(0, named=True)
    preview = [f"{v:.0f}" for v in row["monthly_premium"][:5]]
    print(f"  {pid}: {preview} ...")

print("\n── Present values ────────────────────────────")
print(result.select(["policy_id", "pv_premiums", "pv_benefits", "net_liability"]))

print("\nDone. Edit model.py to explore further.\n")
