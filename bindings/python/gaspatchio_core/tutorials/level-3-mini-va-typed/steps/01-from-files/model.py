# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 (Typed Inputs Variant) → Step 01: Load Assumptions from Files

Same model as level-3-mini-va-typed/base/model.py in every calculation.
Replaces all inline dictionaries with parquet files loaded from disk.

Delta from typed base:
  - SECTION 1: Inline dicts → pl.read_parquet() from data/ directory
  - Curve: built from curve.parquet (tenor + zero_rate columns)
  - MortalityTable: raw Table backed by mortality.parquet
  - inv_returns Table: backed by inv_returns.parquet
  - __main__ block: reads model_points.parquet
  - All other sections (2-11): UNCHANGED

Data files:
  data/model_points.parquet  — 4 policies (same as base)
  data/mortality.parquet     — ages 30-99 annual qx
  data/inv_returns.parquet   — FUND1 monthly returns (0.5%)
  data/curve.parquet         — flat 4% zero-rate curve (tenor, zero_rate)
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, Curve, MortalityTable, when
from gaspatchio_core.assumptions import Table
from gaspatchio_core.schedule import OneTwelfth, Schedule

# =========================================================================
# SECTION 1: FILE-BASED ASSUMPTIONS (was: INLINE DATA)
# =========================================================================

MODEL_DIR = Path(__file__).parent
DATA_DIR = MODEL_DIR / "data"

# Model parameters (not loaded from files — these are model choices)
LAPSE_RATE_ANNUAL = 0.05
INFLATION_RATE = 0.01
VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 240  # 20 years max


def load_assumptions() -> dict:
    """Load assumption tables and typed inputs from parquet files.

    Returns:
        Dict with keys: ``mortality``, ``inv_returns``, ``curve``.

    """
    # MortalityTable: raw Table backed by mortality.parquet
    mortality_table_raw = Table(
        name="mortality",
        source=pl.read_parquet(DATA_DIR / "mortality.parquet"),
        dimensions={"age": "age"},
        value="mort_rate",
    )
    mortality = MortalityTable(
        table=mortality_table_raw,
        age_basis="age_last_birthday",
        structure="aggregate",
    )

    # Investment returns: Table backed by inv_returns.parquet
    inv_returns_table = Table(
        name="inv_returns",
        source=pl.read_parquet(DATA_DIR / "inv_returns.parquet"),
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    # Curve: built from curve.parquet (tenor + zero_rate columns).
    # Curve.from_zero_rates requires list[float], so call .to_list()
    # on each Polars Series column after reading.
    curve_df = pl.read_parquet(DATA_DIR / "curve.parquet")
    curve = Curve.from_zero_rates(
        tenors=curve_df["tenor"].to_list(),
        rates=curve_df["zero_rate"].to_list(),
    )

    return {"mortality": mortality, "inv_returns": inv_returns_table, "curve": curve}


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
    assumptions = load_assumptions()
    mortality = assumptions["mortality"]
    inv_returns_table = assumptions["inv_returns"]
    curve = assumptions["curve"]

    # Schedule — generates the per-period year-fraction grid using
    # OneTwelfth day-count (each month = 1/12 of a year). year_fractions()
    # returns 240 per-period widths (each = 1/12). Prepend 0.0 and accumulate
    # to get the 241 cumulative t_years values: [0, 1/12, 2/12, ..., 240/12].
    schedule = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=PROJECTION_MONTHS,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    t_years_list = schedule.cumulative_year_fractions()

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    af = af.projection.set(schedule=schedule)
    af.projection_date = af.projection.period_dates()

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 3: MORTALITY RATES
    # =====================================================================

    # MortalityTable.at() routes through convention-aware dispatch. For
    # aggregate structure it calls table.lookup(age=...) internally.
    af.mort_rate = mortality.at(age=af.age)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 4: LAPSE RATES
    # =====================================================================

    af.lapse_rate = LAPSE_RATE_ANNUAL
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 5: INVESTMENT RETURNS & ACCOUNT VALUE
    # =====================================================================

    af.inv_return_mth = inv_returns_table.lookup(t=af.month, fund_index=af.fund_index)

    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    af.cumulative_growth = af.combined_growth_factor.cum_prod()
    af.prev_cumulative_growth = af.cumulative_growth.projection.previous_period(
        fill_value=1.0
    )

    af.av_pp = af.av_pp_init * af.prev_cumulative_growth
    af.maint_fee_pp = af.av_pp * af.maint_fee_rate / 12.0
    af.av_pp_after_fee = af.av_pp - af.maint_fee_pp
    af.inv_income_pp = af.inv_return_mth * af.av_pp_after_fee

    # =====================================================================
    # SECTION 6: POLICY COUNTS
    # =====================================================================

    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
    af.survival_factor = 1.0 - af.combined_decrement
    af.cumulative_survival = af.survival_factor.cum_prod()
    af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    af.maturity_month = af.policy_term * 12

    af.pols_if = (
        when(af.duration_mth_t < af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)

    af.pols_death = af.pols_if * af.mort_rate_mth
    af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth

    # =====================================================================
    # SECTION 7: CLAIMS
    # =====================================================================

    af.claims_death = af.av_pp * af.pols_death
    af.claims_lapse = af.av_pp * af.pols_lapse
    af.claims_maturity = af.av_pp * af.pols_maturity
    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    # =====================================================================
    # SECTION 8: PREMIUMS
    # =====================================================================

    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)
    af.premiums = af.premium_pp_list * af.pols_if

    # =====================================================================
    # SECTION 9: EXPENSES & COMMISSIONS
    # =====================================================================

    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)
    af.expense_acq_total = af.expense_acq * af.pols_new_biz
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if * af.inflation_factor
    )
    af.expenses = af.expense_acq_total + af.expense_maint_total
    af.commissions = af.commission_rate * af.premiums

    # =====================================================================
    # SECTION 10: NET CASHFLOW
    # =====================================================================

    af.pols_if_next = af.pols_if.projection.next_period(fill_value=0.0)
    af.inv_income = af.inv_income_pp * af.pols_if_next + 0.5 * af.inv_income_pp * (
        af.pols_death + af.pols_lapse
    )

    af.av_total = af.av_pp * af.pols_if
    af.av_total_next = af.av_total.projection.next_period(fill_value=0.0)
    af.av_change = af.av_total_next - af.av_total

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

    # Curve-based discount factors.
    # curve.discount_factor(t_years_list) accepts a Python list[float] and
    # returns list[float]. The Schedule-derived t_years_list (length 241)
    # gives values [0.0, 1/12, 2/12, ..., 240/12].
    # pl.lit(Series([list])).first() broadcasts the single list to all rows.
    disc_factors_list = curve.discount_factor(t_years_list)  # list[float], len 241
    af.disc_factors = pl.lit(
        pl.Series("disc_factors", [disc_factors_list], dtype=pl.List(pl.Float64))
    ).first()

    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_inv_income = (af.inv_income * af.disc_factors).list.sum()
    af.pv_av_change = (af.av_change * af.disc_factors).list.sum()

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
    mp = pl.read_parquet(DATA_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(result.select(["point_id", "pv_net_cf", "pv_claims", "pv_premiums"]))
