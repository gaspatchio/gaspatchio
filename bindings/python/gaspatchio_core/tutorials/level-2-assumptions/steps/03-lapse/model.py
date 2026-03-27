"""
Level 2 → Step 03: Lapse Rate Table

Delta from Step 02:
  - lapse_rate column removed from model points
  - lapse_rates.parquet added to data/ (dimension: month)
  - lapse_table added alongside mort_table
  - af.lapse_rate_monthly now comes from a Table lookup
  - All other sections: UNCHANGED

New concept — multiple Tables and combined decrements:
  A model can use as many Tables as needed. Load each one in
  load_assumptions() and call .lookup() wherever needed in main().

  Lapse rates often vary by duration: policies lapse heavily in year 1
  then tail off as committed policyholders remain. Here we model this
  as a monthly lapse rate that declines over the 12-month projection.

  lapse_table = Table(
      name="lapse",
      source=lapse_data,
      dimensions={"month": "month"},   # lookup key: projection month
      value="lapse_rate_mth",
  )
  af.lapse_rate_monthly = lapse_table.lookup(month=af.month)

Combined decrements:
  With two stochastic decrements (death and lapse), the combined
  survival factor is:
    (1 - qx_monthly) * (1 - lapse_rate_monthly)
  This is the independent decrements model — it assumes death and lapse
  are independent events. The order of decrement matters slightly in
  practice; this is the simplest approximation.

How to run:
  uv run python model.py
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

# =========================================================================
# SECTION 1: FILE PATHS & CONSTANTS
# =========================================================================

DATA_DIR = Path(__file__).parent / "data"

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 12


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
        dimensions={"month": "month"},   # lookup key is projection month (0–11)
        value="lapse_rate_mth",
    )

    return mort_table, lapse_table


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the term life portfolio projection with dynamic lapse rates.

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

    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=PROJECTION_MONTHS,
        projection_frequency="monthly",
        output_column="projection_date",
    )

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration_yr = af.duration_mth_t // 12
    af.attained_age = af.age + af.duration_yr

    # =====================================================================
    # SECTION 3: MORTALITY & LAPSE RATES (two Tables)
    # =====================================================================

    # Mortality: look up by age and sex (unchanged from Step 02)
    af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)
    af.qx_monthly = 1.0 - (1.0 - af.qx_annual) ** (1.0 / 12.0)

    # Lapse: look up monthly rate by projection month (0 = highest lapse,
    # rates decline as duration increases through the projection year).
    # Unlike mortality, the lapse rate is already monthly — no conversion needed.
    af.lapse_rate_monthly = lapse_table.lookup(month=af.month)

    # =====================================================================
    # SECTION 4: POLICY COUNTS & SURVIVAL
    # =====================================================================

    # Combined decrement: independent decrements model
    # Each month, policies exit via death at rate qx_monthly, OR lapse
    # at rate lapse_rate_monthly. The combined survival is the product
    # of the two individual survival factors.
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
    mp = pl.read_parquet(DATA_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()

    print(result.select(["policy_id", "sex", "pv_net_cf"]))

    # Expected output (lower pv_net_cf vs Step 02 due to higher year-1 lapse):
    # ┌───────────┬─────┬─────────────┐
    # │ policy_id ┆ sex ┆ pv_net_cf   │
    # │ ---       ┆ --- ┆ ---         │
    # │ str       ┆ str ┆ f64         │
    # ╞═══════════╪═════╪═════════════╡
    # │ POL001    ┆ M   ┆ 376.592473  │
    # │ POL002    ┆ F   ┆ 1052.132448 │
    # │ POL003    ┆ M   ┆ 2430.497144 │
    # └───────────┴─────┴─────────────┘
