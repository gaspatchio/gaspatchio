# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3: Mini Variable Annuity Model

A simplified variable annuity projection with inline data.
Covers the core mechanics of a VA model without the complexity
of select/ultimate mortality, dynamic lapse, or guarantee logic.

This model mirrors the structure of the full appliedlife model
(Level 4) so the transition is natural. Each section maps 1:1.

Key concepts:
  - ActuarialFrame: a DataFrame where each row is one policy.
    After af.projection.set(), the frame carries a projection grid;
    assigning list-valued projection accessors materialises list
    columns — one element per projection month. All arithmetic then
    operates element-wise across the entire projection at once.

  - .projection accessor: gaspatchio's time-shifting namespace.
    Methods like .previous_period() and .next_period() shift list
    columns by one period — the vectorised equivalent of writing
    "=B2" in Excel to reference the row above. Instead of computing
    each period recursively (as in lifelib or Excel), gaspatchio
    shifts the whole list and computes all periods simultaneously.

  - when().then().otherwise(): gaspatchio's conditional, equivalent
    to Excel's IF(). Works element-wise on list columns so you can
    write business logic that reads like English.

  - .collect(): each assignment records what you want to calculate.
    Call .collect() when you want the actual numbers — gaspatchio runs
    all the formulas in one pass and returns the results as a Polars
    DataFrame.

  - Methods under .projection, .finance, .date, .excel are gaspatchio.
    Everything else (.cast(), .clip(), .cum_prod(), .list.sum()) is
    standard Polars — see the Polars documentation for those.

Sections:
  1. Inline Data & Assumptions
  2. Time Setup
  3. Mortality Rates
  4. Lapse Rates
  5. Investment Returns & Account Value
  6. Policy Counts
  7. Claims (Death, Lapse, Maturity)
  8. Premiums
  9. Expenses & Commissions
  10. Net Cashflow
  11. Discount Factors & Present Values

How to run:
  python model.py                          (standalone)
  gspio run-single-policy model.py ... 1   (single policy via CLI)
  gspio run-model model.py ...             (all policies via CLI)

How to inspect intermediate variables:
  Use gspio run-single-policy to see all computed columns for one
  policy. The output shows each list column as a vector of values
  across the projection — one row per policy, one element per month.
"""

import datetime
import math

import polars as pl
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table

# =========================================================================
# SECTION 1: INLINE DATA & ASSUMPTIONS
# =========================================================================

# Model points: 4 variable annuity policies
MODEL_POINTS = {
    "point_id": [1, 2, 3, 4],
    "age_at_entry": [55, 40, 65, 50],
    "sex": ["M", "F", "M", "F"],
    "policy_term": [10, 20, 5, 15],
    "policy_count": [100, 50, 200, 75],
    "premium_pp": [50000.0, 30000.0, 100000.0, 40000.0],
    "sum_assured": [50000.0, 30000.0, 100000.0, 40000.0],
    "av_pp_init": [55000.0, 35000.0, 95000.0, 48000.0],
    "entry_date": ["2020/01/01", "2015/06/01", "2022/01/01", "2018/01/01"],
    "fund_index": ["FUND1", "FUND1", "FUND1", "FUND1"],
    "maint_fee_rate": [0.015, 0.015, 0.015, 0.015],
    "commission_rate": [0.03, 0.03, 0.03, 0.03],
    "expense_acq": [500.0, 500.0, 500.0, 500.0],
    "expense_maint": [100.0, 100.0, 100.0, 100.0],
}

# Mortality table: simple age-based rates (annual qx)
MORTALITY_DATA = {
    "age": list(range(30, 100)),
    "mort_rate": [
        # Ages 30-39: low mortality
        0.0008,
        0.0009,
        0.0010,
        0.0011,
        0.0012,
        0.0014,
        0.0016,
        0.0018,
        0.0020,
        0.0023,
        # Ages 40-49: increasing
        0.0026,
        0.0030,
        0.0034,
        0.0039,
        0.0044,
        0.0050,
        0.0057,
        0.0065,
        0.0074,
        0.0084,
        # Ages 50-59: moderate
        0.0096,
        0.0109,
        0.0124,
        0.0141,
        0.0160,
        0.0182,
        0.0207,
        0.0235,
        0.0267,
        0.0303,
        # Ages 60-69: higher
        0.0344,
        0.0391,
        0.0444,
        0.0504,
        0.0573,
        0.0650,
        0.0739,
        0.0839,
        0.0953,
        0.1082,
        # Ages 70-79: significant
        0.1229,
        0.1396,
        0.1586,
        0.1802,
        0.2048,
        0.2327,
        0.2644,
        0.3003,
        0.3413,
        0.3878,
        # Ages 80-89: high
        0.4408,
        0.5000,
        0.5500,
        0.6000,
        0.6500,
        0.7000,
        0.7500,
        0.8000,
        0.8500,
        0.9000,
        # Ages 90-99: very high
        0.9200,
        0.9400,
        0.9500,
        0.9600,
        0.9700,
        0.9800,
        0.9850,
        0.9900,
        0.9950,
        1.0000,
    ],
}

# Investment returns: constant monthly return by fund
INVESTMENT_RETURNS = {
    "t": list(range(241)),  # Up to 20 years monthly
    "fund_index": ["FUND1"] * 241,
    "inv_return_mth": [0.005] * 241,  # ~6.2% annual
}

# Lapse rate: simplified to a constant (a realistic schedule would
# vary by duration, e.g., 10% year 0 declining to 2% — see Step 04)
LAPSE_RATE_ANNUAL = 0.05

# Discount rate: constant 4% annual
DISCOUNT_RATE_ANNUAL = 0.04

# Inflation rate: 1% annual
INFLATION_RATE = 0.01

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 240  # 20 years max


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Main model projection.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    # --- Load assumption tables ---
    mortality_table = Table(
        name="mortality",
        source=pl.DataFrame(MORTALITY_DATA),
        dimensions={"age": "age"},
        value="mort_rate",
    )

    inv_returns_table = Table(
        name="inv_returns",
        source=pl.DataFrame(INVESTMENT_RETURNS),
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    # Parse entry date
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # Duration at valuation (months since issue)
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    # Declare the projection time axis on the frame
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    # Materialise the per-period date vector as a list column
    af.projection_date = af.projection.period_dates()

    # Month index (0 = valuation date)
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    # Duration at time t (months since issue)
    af.duration_mth_t = af.duration_mth_init + af.month

    # Duration in years (for assumption lookups)
    af.duration = af.duration_mth_t // 12

    # Attained age at time t
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 3: MORTALITY RATES
    # =====================================================================

    # Lookup annual mortality rate by attained age.
    # Table.lookup() does an exact-match join: for each policy at each month,
    # it finds the row in the mortality table where age matches af.age.
    # If no match (e.g., age exceeds the table range), the result is null —
    # use .clip(upper_bound=max_age) on the key to prevent this.
    # Multiple keys are supported: lookup(age=af.age, duration=af.dur)
    af.mort_rate = mortality_table.lookup(age=af.age)

    # Convert annual to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 4: LAPSE RATES
    # =====================================================================

    # Constant annual lapse rate. Assigning a scalar here is fine —
    # gaspatchio automatically broadcasts it when combined with list
    # columns in arithmetic (e.g., in combined_decrement below).
    af.lapse_rate = LAPSE_RATE_ANNUAL
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 5: INVESTMENT RETURNS & ACCOUNT VALUE
    # =====================================================================

    # Lookup monthly investment return
    af.inv_return_mth = inv_returns_table.lookup(t=af.month, fund_index=af.fund_index)

    # Account value accumulation (single premium, no further contributions)
    # Combined growth factor per period: (1 - fee/12) * (1 + return)
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    # Cumulative growth from issue
    af.cumulative_growth = af.combined_growth_factor.cum_prod()

    # .projection.previous_period() answers "what was this value last period?"
    # It shifts list elements right by one and fills the first position:
    #   [g0, g1, g2, ...] → [1.0, g0, g1, ...]
    #
    # Read it as: "at each month t, give me the value from month t-1."
    # At t=0 there is no previous month, so fill_value provides the initial.
    #
    # This is the vectorised equivalent of "=B2" in Excel — referencing the
    # row above. In lifelib you'd write av_pp(t-1) as a recursive function
    # call; here, gaspatchio shifts the whole list at once and computes all
    # periods simultaneously.
    af.prev_cumulative_growth = af.cumulative_growth.projection.previous_period(
        fill_value=1.0
    )

    # Account value per policy before fees/investment at each period
    af.av_pp = af.av_pp_init * af.prev_cumulative_growth

    # Maintenance fee
    af.maint_fee_pp = af.av_pp * af.maint_fee_rate / 12.0

    # Account value after fee, before investment
    af.av_pp_after_fee = af.av_pp - af.maint_fee_pp

    # Investment income for current period
    af.inv_income_pp = af.inv_return_mth * af.av_pp_after_fee

    # =====================================================================
    # SECTION 6: POLICY COUNTS
    # =====================================================================

    # Combined decrement rate: 1 - (1 - mort) * (1 - lapse)
    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)

    # Survival factor per period
    af.survival_factor = 1.0 - af.combined_decrement

    # Cumulative survival: the product of all survival factors up to each period.
    # .cum_prod() is a standard Polars method that computes running products:
    #   [0.995, 0.994, 0.993] → [0.995, 0.989, 0.982]
    af.cumulative_survival = af.survival_factor.cum_prod()

    # Shift to beginning-of-period: at t=0 all policies are in force (1.0),
    # at t=1 the first month's decrement has been applied, etc.
    # Same .projection.previous_period() pattern as the AV calculation above.
    af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    # Maturity month (policy_term in years * 12, measured from issue)
    af.maturity_month = af.policy_term * 12

    # Policies in force: survival * count before maturity, zero after
    af.pols_if = (
        when(af.duration_mth_t < af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    # Policies maturing: only at exact maturity month
    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    # New business: enters at issue (duration = 0)
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)

    # Deaths and lapses
    af.pols_death = af.pols_if * af.mort_rate_mth
    af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth

    # =====================================================================
    # SECTION 7: CLAIMS
    # =====================================================================

    # Death claims: account value per policy * deaths
    # (No GMDB guarantee in L3 — simplified to just AV payout)
    af.claims_death = af.av_pp * af.pols_death

    # Lapse claims: account value per policy * lapses
    # (No surrender charges in L3)
    af.claims_lapse = af.av_pp * af.pols_lapse

    # Maturity claims: account value at maturity * maturing policies
    # (No GMAB guarantee in L3)
    af.claims_maturity = af.av_pp * af.pols_maturity

    # Total claims
    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    # =====================================================================
    # SECTION 8: PREMIUMS
    # =====================================================================

    # Single premium: paid only at issue (duration_mth_t == 0)
    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)
    af.premiums = af.premium_pp_list * af.pols_if

    # =====================================================================
    # SECTION 9: EXPENSES & COMMISSIONS
    # =====================================================================

    # Inflation factor: (1 + inflation_rate)^(month/12) per period.
    # Result: [(1.01)^(0/12), (1.01)^(1/12), (1.01)^(2/12), ...]
    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)

    # Acquisition expense: at new business only
    af.expense_acq_total = af.expense_acq * af.pols_new_biz

    # Maintenance expense: monthly, inflated
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if * af.inflation_factor
    )

    # Total expenses
    af.expenses = af.expense_acq_total + af.expense_maint_total

    # Commissions: rate * premiums
    af.commissions = af.commission_rate * af.premiums

    # =====================================================================
    # SECTION 10: NET CASHFLOW
    # =====================================================================

    # Investment income (full period for survivors, half for decrements)
    af.pols_if_next = af.pols_if.projection.next_period(fill_value=0.0)
    af.inv_income = af.inv_income_pp * af.pols_if_next + 0.5 * af.inv_income_pp * (
        af.pols_death + af.pols_lapse
    )

    # Change in account value (reserve change)
    af.av_total = af.av_pp * af.pols_if
    af.av_total_next = af.av_total.projection.next_period(fill_value=0.0)
    af.av_change = af.av_total_next - af.av_total

    # Net cashflow
    af.net_cf = (
        af.premiums
        + af.inv_income
        - af.claims
        - af.expenses
        - af.commissions
        - af.av_change
    )

    # =====================================================================
    # SECTION 11: DISCOUNT FACTORS & PRESENT VALUES
    # =====================================================================

    # Monthly discount rate (constant)
    disc_rate_mth = (1 + DISCOUNT_RATE_ANNUAL) ** (1 / 12) - 1

    # Discount factors: (1 + r_mth)^(-t)
    af.disc_factors = (
        af.month.cast(pl.Float64) * -1.0 * math.log(1 + disc_rate_mth)
    ).exp()

    # Present values
    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_inv_income = (af.inv_income * af.disc_factors).list.sum()
    af.pv_av_change = (af.av_change * af.disc_factors).list.sum()

    # Net present value
    af.pv_net_cf = (
        af.pv_premiums
        + af.pv_inv_income
        - af.pv_claims
        - af.pv_expenses
        - af.pv_commissions
        - af.pv_av_change
    )

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    # Show key outputs per policy
    print(result.select(["point_id", "pv_net_cf", "pv_claims", "pv_premiums"]))

    # Expected output (verify your model matches):
    # ┌──────────┬───────────────┬───────────┬─────────────┐
    # │ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_premiums │
    # │ ---      ┆ ---           ┆ ---       ┆ ---         │
    # │ i64      ┆ f64           ┆ f64       ┆ f64         │
    # ╞══════════╪═══════════════╪═══════════╪═════════════╡
    # │ 1        ┆ 345203.112821 ┆ 5.6454e6  ┆ 0.0         │
    # │ 2        ┆ 183780.777719 ┆ 1.8317e6  ┆ 0.0         │
    # │ 3        ┆ 643026.987196 ┆ 1.9260e7  ┆ 0.0         │
    # │ 4        ┆ 311048.533918 ┆ 3.7319e6  ┆ 0.0         │
    # └──────────┴───────────────┴───────────┴─────────────┘
