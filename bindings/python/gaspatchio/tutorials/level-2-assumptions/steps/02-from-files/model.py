# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 2 → Step 02: Load Data from Files

Delta from Step 01:
  - Model points loaded from data/model_points.parquet
  - Mortality table loaded from data/mortality.parquet
  - MODEL_POINTS and mort_data dicts removed from module level
  - DATA_DIR path constant added
  - All model logic: UNCHANGED

New concept — file-based assumptions:
  Real models load data from parquet files, not inline dicts. This
  separates the model code from the data, making it easy to:
    - swap in a different set of model points
    - update assumption tables without touching model code
    - version-control data files independently

  DATA_DIR = Path(__file__).parent / "data"
  mp = pl.read_parquet(DATA_DIR / "model_points.parquet")
  mort_data = pl.read_parquet(DATA_DIR / "mortality.parquet")

  The __main__ block reads model points as a Polars DataFrame, then wraps
  it in ActuarialFrame. The mortality parquet is loaded in load_assumptions()
  and passed directly to Table(source=...).

Parquet format:
  gaspatchio uses Polars which reads parquet natively and efficiently.
  Parquet preserves column types (int, float, string) without the type
  coercion risks of CSV. It also compresses well for large model point files.

How to run:
  uv run python model.py
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

# =========================================================================
# SECTION 1: FILE PATHS & CONSTANTS
# =========================================================================

DATA_DIR = Path(__file__).parent / "data"

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 12


def load_assumptions() -> Table:
    """Load mortality table from parquet.

    Returns:
        Table configured with age × sex mortality rates.

    """
    mort_data = pl.read_parquet(DATA_DIR / "mortality.parquet")
    return Table(
        name="mortality",
        source=mort_data,
        dimensions={"age": "age", "sex": "sex"},
        value="qx",
    )


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
    mort_table = load_assumptions()

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")
    af.duration_mth_init = af.entry_date_parsed.date.months_between(VALUATION_DATE)

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    af.projection_date = af.projection.period_dates()

    # projection.set() has already stamped af.month -- elapsed whole months
    # from the valuation date, 0, 1, 2, ... one per projection period.

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration_yr = af.duration_mth_t // 12
    af.attained_age = af.age + af.duration_yr

    # =====================================================================
    # SECTION 3: MORTALITY RATES
    # =====================================================================

    af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)
    af.qx_monthly = 1.0 - (1.0 - af.qx_annual) ** (1.0 / 12.0)

    af.lapse_rate_monthly = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =====================================================================
    # SECTION 4: POLICY COUNTS & SURVIVAL
    # =====================================================================

    af.combined_decrement = 1.0 - (1.0 - af.qx_monthly) * (1.0 - af.lapse_rate_monthly)
    # Cumulative survival from the combined decrement:
    #   tpx[t] = (1 - q[0]) * (1 - q[1]) * ... * (1 - q[t-1])
    # rate_timing="beginning_of_period" is the default, and it is the
    # convention wanted here: the decrement at t has not been applied yet,
    # so the first element is 1.0 -- every policy in force at t=0.
    af.survival_bop = af.combined_decrement.projection.cumulative_survival()
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

    # Expected output (identical to Step 01 — same data, different source):
    # ┌───────────┬─────┬─────────────┐
    # │ policy_id ┆ sex ┆ pv_net_cf   │
    # │ ---       ┆ --- ┆ ---         │
    # │ str       ┆ str ┆ f64         │
    # ╞═══════════╪═════╪═════════════╡
    # │ POL001    ┆ M   ┆ 384.59208   │
    # │ POL002    ┆ F   ┆ 1057.61069  │
    # │ POL003    ┆ M   ┆ 2507.831412 │
    # └───────────┴─────┴─────────────┘
