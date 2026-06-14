# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 2 → Step 04: Conditionals on List Columns

Delta from Step 03:
  - policy_term added to model points (in years)
  - Projection extended to 24 months (2 years)
  - af.maturity_month computed (policy_term * 12, measured from issue)
  - af.pols_if zeroed after policy maturity using when/then/otherwise
  - af.commissions added: 50% of first-year premium income, 0% after
  - net_cf now includes commissions as an additional outgo item

New concept — when/then/otherwise on list columns:
  In Level 1 you used when() on scalar columns (one value per policy).
  After af.projection.set(), assigning list-valued projection accessors
  produces list columns — one element per projection month.
  when/then/otherwise works identically, but now applies element-wise
  across every (policy, month) cell simultaneously.

  Example 1 — zero pols_if after maturity:
    af.pols_if = (
        when(af.duration_mth_t < af.maturity_month)
        .then(af.survival_bop)
        .otherwise(0.0)
    )
  For each policy, months before maturity use survival_bop; months at
  or after maturity produce 0. The condition af.duration_mth_t <
  af.maturity_month compares a list (duration_mth_t, changing each month)
  against a scalar (maturity_month, constant per policy). gaspatchio
  broadcasts the scalar automatically.

  Example 2 — first-year commissions only:
    af.commissions = (
        when(af.month < 12)
        .then(af.premium_income * 0.50)
        .otherwise(0.0)
    )
  af.month is a list [0, 1, 2, ..., 23]. months 0–11 pay 50% commission,
  months 12–23 pay nothing.

Why maturity matters:
  A 10-year term policy expires after 120 months. Without zeroing pols_if
  after maturity, the model would keep collecting premiums (and paying
  claims) indefinitely. The when/then/otherwise pattern is the natural
  way to express this "switch-off" logic.

How to run:
  uv run python model.py
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table

# =========================================================================
# SECTION 1: FILE PATHS & CONSTANTS
# =========================================================================

DATA_DIR = Path(__file__).parent / "data"

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 24  # 2 years — long enough to show maturity effect


def load_assumptions() -> tuple[Table, Table]:
    """Load mortality and lapse tables from parquet.

    Returns:
        Tuple of (mort_table, lapse_table).

    """
    mort_table = Table(
        name="mortality",
        source=pl.read_parquet(DATA_DIR / "mortality.parquet"),
        dimensions={"age": "age", "sex": "sex"},
        value="qx",
    )

    lapse_table = Table(
        name="lapse",
        source=pl.read_parquet(DATA_DIR / "lapse_rates.parquet"),
        dimensions={"month": "month"},
        value="lapse_rate_mth",
    )

    return mort_table, lapse_table


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the term life portfolio projection with maturity zeroing.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    mort_table, lapse_table = load_assumptions()

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    af.projection_date = af.projection.period_dates()

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration_yr = af.duration_mth_t // 12
    af.attained_age = af.age + af.duration_yr

    # Maturity month measured from issue (not from valuation).
    # policy_term is in years; multiply by 12 for months.
    # A policy with policy_term=1 issued at t=0 matures at duration_mth_t=12.
    af.maturity_month = af.policy_term * 12

    # =====================================================================
    # SECTION 3: MORTALITY & LAPSE RATES
    # =====================================================================

    af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)
    af.qx_monthly = 1.0 - (1.0 - af.qx_annual) ** (1.0 / 12.0)

    af.lapse_rate_monthly = lapse_table.lookup(month=af.month)

    # =====================================================================
    # SECTION 4: POLICY COUNTS & SURVIVAL
    # =====================================================================

    af.combined_decrement = 1.0 - (1.0 - af.qx_monthly) * (1.0 - af.lapse_rate_monthly)
    af.survival_factor = 1.0 - af.combined_decrement
    af.cumulative_survival = af.survival_factor.cum_prod()
    af.survival_bop = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    # Zero out pols_if after policy maturity.
    # when/then/otherwise on a list column:
    #   - af.duration_mth_t is a list [0, 1, 2, ..., 23]
    #   - af.maturity_month is a scalar per policy (12 or 24 or 20)
    #   - gaspatchio broadcasts the scalar and evaluates element-wise
    af.pols_if = (
        when(af.duration_mth_t < af.maturity_month).then(af.survival_bop).otherwise(0.0)
    )

    # =====================================================================
    # SECTION 5: CASHFLOWS
    # =====================================================================

    af.premium_income = af.annual_premium / 12.0 * af.pols_if
    af.claims = af.sum_assured * af.pols_if * af.qx_monthly
    af.expenses = af.premium_income * af.expense_rate

    # First-year commissions only: 50% of premium income in months 0–11, 0% after.
    # af.month is a list; the comparison month < 12 produces a boolean list.
    # when/then/otherwise returns premium_income * 0.50 for months 0–11 and
    # 0.0 for months 12+. This is the list conditional in action.
    af.commissions = when(af.month < 12).then(af.premium_income * 0.50).otherwise(0.0)

    af.net_cf = af.premium_income - af.claims - af.expenses - af.commissions
    af.pv_net_cf = af.net_cf.list.sum()

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    mp = pl.read_parquet(DATA_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "sex", "policy_term", "pv_net_cf"]))

    # Expected output (POL001 term=1 yr: matures after 12 months and pays
    # 50% first-year commissions; POL003 high claims reduce profit):
    # ┌───────────┬─────┬─────────────┬────────────┐
    # │ policy_id ┆ sex ┆ policy_term ┆ pv_net_cf  │
    # │ ---       ┆ --- ┆ ---         ┆ ---        │
    # │ str       ┆ str ┆ i64         ┆ f64        │
    # ╞═══════════╪═════╪═════════════╪════════════╡
    # │ POL001    ┆ M   ┆ 1           ┆ 133.475085 │
    # │ POL002    ┆ F   ┆ 2           ┆ 789.667273 │
    # │ POL003    ┆ M   ┆ 2           ┆ 159.906187 │
    # └───────────┴─────┴─────────────┴────────────┘
