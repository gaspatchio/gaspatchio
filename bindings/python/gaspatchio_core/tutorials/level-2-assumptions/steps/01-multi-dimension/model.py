# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 2 → Step 01: Multi-Dimension Table

Delta from base:
  - Mortality table gains a second dimension: sex ("M" / "F")
  - mort_table.lookup() now passes both age and sex
  - All other sections: UNCHANGED

New concept — multi-key lookup:
  A Table can have any number of dimensions. Each dimension is a column
  in the source DataFrame and corresponds to a keyword argument in .lookup().

  mort_table = Table(
      name="mortality",
      source=mort_data,
      dimensions={"age": "age", "sex": "sex"},   # two keys
      value="qx",
  )
  af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)

  gaspatchio performs a joint exact-match on all dimension columns.
  af.sex is a scalar string per policy; af.attained_age is a list column
  (one value per month). The lookup handles the broadcast automatically —
  for each (policy, month) cell it matches both age AND sex.

Why sex matters:
  Female mortality rates are typically 10–30% lower than male at the same
  age, especially in middle age. A single-dimension table by age would
  over-price female policies and under-price male ones.

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

MODEL_POINTS = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500_000, 250_000, 100_000],
    "annual_premium": [450, 1_200, 2_800],
    "lapse_rate": [0.05, 0.08, 0.03],
    "expense_rate": [0.10, 0.10, 0.10],
    "entry_date": ["2024/01/15", "2023/06/01", "2022/03/10"],
}

# Mortality table: annual qx by age × sex.
# Female rates are lower than male at the same age.
# The table has one row per (age, sex) combination.
_ages = list(range(25, 71))
_mort_rows: list[dict] = []
for a in _ages:
    # Male: Gompertz with base 0.00005 * 1.10^(age-25)
    # Female: 70% of male rate (simplified sex differential)
    qx_m = round(0.00005 * 1.10 ** (a - 25), 6)
    qx_f = round(qx_m * 0.70, 7)
    _mort_rows.append({"age": a, "sex": "M", "qx": qx_m})
    _mort_rows.append({"age": a, "sex": "F", "qx": qx_f})

mort_data = pl.DataFrame(_mort_rows)

# Two-dimension Table: keys are age AND sex
mort_table = Table(
    name="mortality",
    source=mort_data,
    dimensions={"age": "age", "sex": "sex"},  # both columns are lookup keys
    value="qx",
)

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 12


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the term life portfolio projection with age × sex mortality.

    Args:
        af: ActuarialFrame with model points.

    Returns:
        ActuarialFrame with projection results.

    """
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

    # =====================================================================
    # SECTION 3: MORTALITY RATES (two-dimension lookup)
    # =====================================================================

    # Lookup qx by age AND sex.
    # af.sex is a scalar (e.g., "M") that gaspatchio broadcasts to match
    # the list length of af.attained_age. The joint lookup returns the
    # row where both age == attained_age AND sex == af.sex.
    af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)
    af.qx_monthly = 1.0 - (1.0 - af.qx_annual) ** (1.0 / 12.0)

    af.lapse_rate_monthly = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =====================================================================
    # SECTION 4: POLICY COUNTS & SURVIVAL
    # =====================================================================

    af.combined_decrement = 1.0 - (1.0 - af.qx_monthly) * (1.0 - af.lapse_rate_monthly)
    af.survival_factor = 1.0 - af.combined_decrement
    af.cumulative_survival = af.survival_factor.cum_prod()
    af.survival_bop = af.cumulative_survival.projection.previous_period(fill_value=1.0)
    af.pols_if = af.survival_bop

    # =====================================================================
    # SECTION 5: CASHFLOWS
    # =====================================================================

    af.premium_income = af.annual_premium / 12.0 * af.pols_if
    af.claims = af.sum_assured * af.pols_if * af.qx_monthly
    af.expenses = af.premium_income * af.expense_rate
    af.net_cf = af.premium_income - af.claims - af.expenses
    af.pv_net_cf = af.net_cf.list.sum()

    return af


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    af = ActuarialFrame(MODEL_POINTS)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "sex", "pv_net_cf"]))

    # Expected output (POL002 female has lower mortality → higher pv_net_cf
    # compared to base: 1057 vs 1029 because fewer death claims):
    # ┌───────────┬─────┬─────────────┐
    # │ policy_id ┆ sex ┆ pv_net_cf   │
    # │ ---       ┆ --- ┆ ---         │
    # │ str       ┆ str ┆ f64         │
    # ╞═══════════╪═════╪═════════════╡
    # │ POL001    ┆ M   ┆ 384.59208   │
    # │ POL002    ┆ F   ┆ 1057.61069  │
    # │ POL003    ┆ M   ┆ 2507.831412 │
    # └───────────┴─────┴─────────────┘
