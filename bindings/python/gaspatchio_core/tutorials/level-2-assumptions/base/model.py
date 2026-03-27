"""
Level 2: Assumptions — Table Lookup

Builds on Level 1 Step 03 (time-shifting) by replacing the hardcoded
mortality_rate column with a Table lookup. This is the gateway concept
for real actuarial models: assumptions live in structured tables, not
in model point data.

Key concepts introduced here:

  - Table: gaspatchio's assumption table class. You construct it from a
    Polars DataFrame (or parquet file), declare which column is the
    dimension key and which column is the value, then call .lookup() to
    join it into your projection.

    mort_table = Table(
        name="mortality",
        source=mort_data,            # polars DataFrame
        dimensions={"age": "age"},   # {dimension_name: column_name}
        value="qx",                  # value column
    )

  - .lookup(): performs an exact-match join between the Table and your
    projection. Pass keyword arguments matching the dimension names:
      af.mortality_rate = mort_table.lookup(age=af.age)
    For each policy at each projection month, gaspatchio finds the row
    in mort_data where age == af.age and returns the qx value.
    If no match exists the result is null — ensure your key column covers
    the full range of attained ages in your projection.

  - Attained age: af.age advances each month as the policy ages.
    Computed as age_at_entry + duration_in_years. The mortality rate
    therefore updates automatically as the insured gets older.

  - lapse_rate is still a hardcoded scalar here — Table for lapse comes
    in Step 03. Scalars broadcast automatically in gaspatchio arithmetic.

Projection structure:
  - 12 months (t=0..11)
  - cumulative_survival using .cum_prod() on survival factors
  - .projection.previous_period() shifts survival to beginning-of-period
  - net_cf = premium_income - claims - expenses

Sections:
  1. Inline Data & Mortality Table
  2. Time Setup
  3. Mortality Rates (Table lookup — the new concept)
  4. Policy Counts & Survival
  5. Cashflows

How to run:
  uv run python model.py
"""

import datetime

import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

# =========================================================================
# SECTION 1: INLINE DATA & MORTALITY TABLE
# =========================================================================

# Three term life insurance policies
MODEL_POINTS = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500_000, 250_000, 100_000],
    "annual_premium": [450, 1_200, 2_800],
    "lapse_rate": [0.05, 0.08, 0.03],   # scalar per policy (Step 03 replaces this)
    "expense_rate": [0.10, 0.10, 0.10],
    "entry_date": ["2024/01/15", "2023/06/01", "2022/03/10"],
}

# Mortality table: annual qx by attained age.
# In L1 these rates were hardcoded as model point columns.
# Here they live in a separate table — the model looks them up by age.
# The table must cover every attained age reached during the projection.
# With ages 30, 45, 60 at valuation and a 12-month projection, we need
# ages 30–31, 45–46, and 60–61 at minimum. We include ages 25–70 for safety.
#
# qx formula: a simple Gompertz-style function — purely illustrative.
# Real models use published life tables (e.g., CMI, SOA).
_ages = list(range(25, 71))
_qx = [round(0.00005 * 1.1 ** (a - 25), 6) for a in _ages]
mort_data = pl.DataFrame({"age": _ages, "qx": _qx})

mort_table = Table(
    name="mortality",
    source=mort_data,
    dimensions={"age": "age"},   # lookup key: dimension name → column name
    value="qx",                  # column to return
)

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 12


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the term life portfolio projection.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    # Parse entry date and compute initial duration
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    # Expand each policy to one row per projection month
    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=PROJECTION_MONTHS,
        projection_frequency="monthly",
        output_column="projection_date",
    )

    # Month index (0 = valuation date, 1 = one month later, ...)
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    # Duration in years at each projection month — used to compute attained age
    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration_yr = af.duration_mth_t // 12

    # Attained age at each projection month: advances as the insured ages
    af.attained_age = af.age + af.duration_yr

    # =====================================================================
    # SECTION 3: MORTALITY RATES (Table lookup)
    # =====================================================================

    # Look up annual qx from the mortality table by attained age.
    # mort_table.lookup(age=af.attained_age) performs an exact-match join:
    # for each element in the attained_age list, it returns the matching
    # qx from mort_data. The result is a list column — one rate per month.
    af.qx_annual = mort_table.lookup(age=af.attained_age)

    # Convert annual rate to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
    af.qx_monthly = 1.0 - (1.0 - af.qx_annual) ** (1.0 / 12.0)

    # Lapse: still a scalar per policy (Step 03 introduces a lapse Table)
    af.lapse_rate_monthly = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =====================================================================
    # SECTION 4: POLICY COUNTS & SURVIVAL
    # =====================================================================

    # Combined decrement: policies exit via death OR lapse
    af.combined_decrement = 1.0 - (1.0 - af.qx_monthly) * (1.0 - af.lapse_rate_monthly)
    af.survival_factor = 1.0 - af.combined_decrement

    # Cumulative survival: running product of monthly survival factors.
    # [0.995, 0.994, 0.993, ...] → [0.995, 0.989, 0.982, ...]
    af.cumulative_survival = af.survival_factor.cum_prod()

    # Shift to beginning-of-period so that at t=0 no policies have yet
    # decremented (survival = 1.0), and at t=1 the first month's decrement
    # has been applied. This is the .projection.previous_period() pattern.
    af.survival_bop = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    # Policies in force at beginning of each month (starting from 1 policy each)
    af.pols_if = af.survival_bop

    # =====================================================================
    # SECTION 5: CASHFLOWS
    # =====================================================================

    # Monthly premium income per policy
    af.premium_income = af.annual_premium / 12.0 * af.pols_if

    # Monthly death claims: sum assured × probability of dying this month
    af.claims = af.sum_assured * af.pols_if * af.qx_monthly

    # Expenses: % of monthly premium
    af.expenses = af.premium_income * af.expense_rate

    # Net cashflow: premiums collected minus outgo
    af.net_cf = af.premium_income - af.claims - af.expenses

    # Present value of net cashflow (simple sum over projection)
    af.pv_net_cf = af.net_cf.list.sum()

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "pv_net_cf"]))

    # Expected output (12-month projection, mortality from Table):
    # ┌───────────┬─────────────┐
    # │ policy_id ┆ pv_net_cf   │
    # │ ---       ┆ ---         │
    # │ str       ┆ f64         │
    # ╞═══════════╪═════════════╡
    # │ POL001    ┆ 384.59208   │
    # │ POL002    ┆ 1029.756785 │
    # │ POL003    ┆ 2507.831412 │
    # └───────────┴─────────────┘
