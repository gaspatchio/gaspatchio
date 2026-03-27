"""
Level 1 → Step 03: Time Shifting

Delta from Step 02:
  - SECTION 5: Add per-period death and lapse counts using previous_period (NEW)
  - SECTION 5: Add claims_death and net_cf
  - Remove total_premium/total_claims summary (they're now derived more precisely)

New concepts introduced here:

  - .projection.previous_period(fill_value): shifts a list column one period
    to the right, filling the first element with fill_value:
      [v0, v1, v2, ...] → [fill_value, v0, v1, ...]
    This is gaspatchio's vectorised "look back one period" — equivalent to
    "=B2" in Excel (referencing the cell above) or pols_if(t-1) in lifelib.
    All 13 periods are computed simultaneously; no recursion.

  - Why previous_period for death counts? Deaths in period t happen to the
    policies that were alive at the START of period t (i.e., pols_if at t-1,
    not pols_if at t). Using pols_if directly would undercount deaths because
    pols_if at t has already had those deaths removed.

  - Death/lapse ordering: deaths are applied first, then lapses:
      pols_death = pols_if_prev * mort_rate_mth
      pols_lapse = (pols_if_prev - pols_death) * lapse_rate_mth
    This "UDD" (Uniform Distribution of Deaths) assumption is standard in
    most actuarial models.

  - fill_value=1.0 for pols_if_prev: at t=0 there is no prior period. The
    fill_value represents the initial "policies in force" at inception.
    Setting it to 1.0 means the first month's deaths are calculated from
    a full cohort of 1 policy — the correct starting assumption.

  - Net cashflow: the simplest actuarial profit measure.
      net_cf = premiums collected - death claims paid - expenses
    Summing this over the projection gives the undiscounted profit.

Sections:
  1. Inline Data & Constants
  2. Time Setup
  3. Monthly Rates
  4. Cumulative Survival
  5. Per-Period Counts & Cashflows

How to run:
  uv run python model.py
"""

import datetime

from gaspatchio_core import ActuarialFrame

# =========================================================================
# SECTION 1: INLINE DATA & CONSTANTS
# =========================================================================

VALUATION_DATE = datetime.date(2025, 1, 1)
PROJECTION_MONTHS = 12

MODEL_POINTS = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500_000, 250_000, 100_000],
    "annual_premium": [450, 1_200, 2_800],
    "mortality_rate": [0.001, 0.004, 0.015],  # annual qx
    "lapse_rate": [0.05, 0.08, 0.03],  # annual lapse rate
    "expense_rate": [0.10, 0.10, 0.10],
    "entry_date": ["2024/01/15", "2023/06/01", "2022/03/10"],
}


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the 12-month term life projection with per-period cashflows.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=PROJECTION_MONTHS,
        projection_frequency="monthly",
        output_column="projection_date",
    )

    af.month = (
        af.projection_date.dt.year() - VALUATION_DATE.year
    ) * 12 + (af.projection_date.dt.month() - VALUATION_DATE.month)

    # =====================================================================
    # SECTION 3: MONTHLY RATES
    # =====================================================================

    af.mort_rate_mth = 1 - (1 - af.mortality_rate) ** (1 / 12)
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 4: CUMULATIVE SURVIVAL
    # =====================================================================

    af.combined_decrement = 1 - (1 - af.mort_rate_mth) * (1 - af.lapse_rate_mth)

    # Broadcast scalar to list (see Step 02 for explanation)
    af.decrement_list = af.combined_decrement + af.month * 0.0

    # Policies in force at beginning of each period (starts at 1.0)
    af.pols_if = af.decrement_list.projection.cumulative_survival()

    # =====================================================================
    # SECTION 5: PER-PERIOD COUNTS & CASHFLOWS
    # =====================================================================

    # Previous-period policies in force: what the cohort looked like at the
    # START of each period (before this period's decrements).
    # .projection.previous_period(fill_value=1.0) shifts pols_if right by one:
    #   [1.0, 0.996, 0.991, ...] → [1.0, 1.0, 0.996, ...]
    # fill_value=1.0 because at t=0 we start with a full cohort (1 policy).
    af.pols_if_prev = af.pols_if.projection.previous_period(fill_value=1.0)

    # Deaths: fraction of the prior-period cohort that dies this period
    af.pols_death = af.pols_if_prev * af.mort_rate_mth

    # Lapses: fraction of survivors (after death) that lapse this period
    af.pols_lapse = (af.pols_if_prev - af.pols_death) * af.lapse_rate_mth

    # Death claims: full sum assured paid for each death
    af.claims_death = af.sum_assured * af.pols_death

    # Premium income: monthly premium for policies still active
    af.monthly_premium = af.annual_premium / 12.0
    af.premium_income = af.monthly_premium * af.pols_if

    # Expenses: percentage of premium income
    af.expenses = af.premium_income * af.expense_rate

    # Net cashflow: inflows minus outflows per period
    af.net_cf = af.premium_income - af.claims_death - af.expenses

    # Aggregate over projection: undiscounted totals
    af.pv_net_cf = af.net_cf.list.sum()
    af.total_deaths = af.pols_death.list.sum()

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "pols_if", "net_cf", "pv_net_cf", "total_deaths"]))

    # pols_if and net_cf are list columns (13 elements each).
    # pv_net_cf and total_deaths are scalar summaries over the projection.
    #
    # From here, Level 2 replaces the hardcoded mortality_rate with a
    # Table lookup that varies by age — the same model, with real assumptions.
