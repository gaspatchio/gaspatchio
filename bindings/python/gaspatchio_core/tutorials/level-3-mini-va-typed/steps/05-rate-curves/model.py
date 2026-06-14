# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 (Typed Inputs Variant) -> Step 05: Rate Curves — Parallel & Key-Rate Shifts

Demonstrates Curve.shift_parallel() and Curve.key_rate_shift() by computing
present values under three interest rate scenarios side-by-side:

  BASE        — non-flat zero-rate curve loaded from curve.parquet
  PARALLEL+100 — every knot rate +100 bps (parallel shift up)
  KEYRATE+50   — 5-year knot only +50 bps (localized key-rate shock)

This step is feature exploration, not numerical parity with the untyped
step 05.  The untyped step 05 uses forward-rate tables looked up by projection
year; here we use Curve typed inputs throughout.

Delta from typed Step 02 (select-mort):
  - SECTION 1: curve.parquet replaced with a 5-knot upward-sloping curve
  - main() refactored: Curve extracted as an argument so three scenarios
    can be evaluated without re-running the full projection three times
  - SECTION 11: disc_factors computed from the passed-in Curve (unchanged
    mechanics, different curve per call)
  - __main__: calls main() three times — once per scenario — assembles a
    side-by-side comparison DataFrame and prints it

What the Curve API does:
  curve.shift_parallel(bps=100)     — returns a NEW Curve, all knots +100bps
  curve.key_rate_shift(tenor=5.0, bps=50) — returns a NEW Curve, 5y knot +50bps
  curve.discount_factor(t_years)    — list[float] of discount factors at each t
"""

import datetime
import math
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, Curve, MortalityTable, when
from gaspatchio_core.assumptions import Table
from gaspatchio_core.assumptions._dimensions import DataDimension
from gaspatchio_core.schedule import OneTwelfth, Schedule

# =========================================================================
# SECTION 1: FILE-BASED ASSUMPTIONS
# =========================================================================

MODEL_DIR = Path(__file__).parent
DATA_DIR = MODEL_DIR / "data"

# Model parameters
LAPSE_RATE_ANNUAL = 0.05
INFLATION_RATE = 0.01
VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 240

# Assumption table caps
SCALAR_DURATION_CAP = 14  # Mortality scalars cover durations 0-14
SELECT_PERIOD = 24  # Select mortality covers durations 0-24


def load_assumptions() -> dict:
    """Load assumption tables and typed inputs from parquet files.

    Returns:
        Dict with keys: ``mortality``, ``mortality_scalars``, ``inv_returns``,
        ``curve_base`` (the non-flat zero-rate curve from parquet).

    """
    # Select mortality: 3 dimensions (table_id, attained_age, duration).
    mortality_select_raw = Table(
        name="mortality_select",
        source=pl.read_parquet(DATA_DIR / "mortality_select.parquet"),
        dimensions={
            "table_id": "table_id",
            "age": DataDimension(column="attained_age", rename_to="age"),
            "duration": "duration",
        },
        value="mort_rate",
    )
    mortality = MortalityTable(
        table=mortality_select_raw,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=SELECT_PERIOD,
    )

    mortality_scalars = Table(
        name="mortality_scalars",
        source=pl.read_parquet(DATA_DIR / "mortality_scalars.parquet"),
        dimensions={"scalar_id": "scalar_id", "duration": "duration"},
        value="mort_scalar",
    )

    inv_returns_table = Table(
        name="inv_returns",
        source=pl.read_parquet(DATA_DIR / "inv_returns.parquet"),
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    # NEW (step 05): non-flat zero-rate curve — 5 knots, upward-sloping.
    # Contrast with step 02's flat 4% curve.
    # Knots: 1y=2%, 5y=2.5%, 10y=3.5%, 20y=4.0%, 30y=4.5%
    curve_df = pl.read_parquet(DATA_DIR / "curve.parquet")
    curve_base = Curve.from_zero_rates(
        tenors=curve_df["tenor"].to_list(),
        rates=curve_df["zero_rate"].to_list(),
    )

    return {
        "mortality": mortality,
        "mortality_scalars": mortality_scalars,
        "inv_returns": inv_returns_table,
        "curve_base": curve_base,
    }


# =========================================================================
# MODEL ENTRY POINT (Curve is an argument — enables multi-scenario runs)
# =========================================================================


def main(af: ActuarialFrame, curve: Curve) -> pl.DataFrame:
    """Run the projection with a given discount curve and return scalar PVs.

    Factoring Curve out of main() lets the caller swap scenarios without
    re-running the full model setup.  Three calls with three Curves produce
    three sets of present values for comparison.

    Args:
        af: ActuarialFrame with model points.
        curve: Discount curve to use for Section 11 (PV calculation).

    Returns:
        Collected DataFrame with per-policy PV columns.

    """
    assumptions = load_assumptions()
    mortality = assumptions["mortality"]
    mortality_scalars = assumptions["mortality_scalars"]
    inv_returns_table = assumptions["inv_returns"]

    # Schedule: per-period year-fraction grid (OneTwelfth day-count).
    # year_fractions() returns 240 widths; prepend 0.0 and accumulate for
    # 241 cumulative t-values matching the 240-period projection timeline.
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

    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    af.base_mort_rate = mortality.at(
        age=af.age,
        duration=af.duration,
        table_id=af.mort_table_id,
    )

    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
    )

    af.mort_rate = af.base_mort_rate * af.mort_scalar
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

    af.inflation_factor = (af.month / 12.0 * math.log(1.0 + INFLATION_RATE)).exp()
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
    # NEW (step 05): discount factors computed from the Curve argument,
    # not a hardcoded scalar rate.  The caller swaps curves to get
    # three independent PV sets without re-running sections 2-10.
    #
    # curve.discount_factor(t_years_list) returns list[float] (len 241).
    # pl.lit(Series([list])).first() broadcasts a single list to every row.

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

    return af.collect().select(["point_id", "pv_net_cf"])


# =========================================================================
# STANDALONE EXECUTION — three-scenario comparison
# =========================================================================

if __name__ == "__main__":
    mp = pl.read_parquet(DATA_DIR / "model_points.parquet")

    # Load assumptions to get the base curve
    assumptions = load_assumptions()
    curve_base = assumptions["curve_base"]

    # NEW: Curve shift API —
    #   shift_parallel(bps=100) shifts ALL knots by +100bps
    #   key_rate_shift(tenor=5.0, bps=50) shifts ONLY the 5y knot by +50bps
    # Both return new Curve objects; the original is unchanged.
    curve_parallel = curve_base.shift_parallel(bps=100)
    curve_keyrate = curve_base.key_rate_shift(tenor=5.0, bps=50)

    print("Curve knots (zero rates):")
    print(f"  BASE:         {[round(r, 4) for r in curve_base.rates]}")
    print(f"  PARALLEL+100: {[round(r, 4) for r in curve_parallel.rates]}")
    print(f"  KEYRATE+50:   {[round(r, 4) for r in curve_keyrate.rates]}")
    print()

    # Run main() once per scenario — cashflow sections are identical;
    # only Section 11 changes with the curve argument.
    result_base = main(ActuarialFrame(mp), curve_base).rename(
        {"pv_net_cf": "pv_net_cf_base"}
    )
    result_parallel = main(ActuarialFrame(mp), curve_parallel).rename(
        {"pv_net_cf": "pv_net_cf_parallel100"}
    )
    result_keyrate = main(ActuarialFrame(mp), curve_keyrate).rename(
        {"pv_net_cf": "pv_net_cf_keyrate50"}
    )

    # Assemble side-by-side comparison by joining on point_id
    comparison = result_base.join(result_parallel, on="point_id").join(
        result_keyrate, on="point_id"
    )

    print("PV Net Cashflow — Three-Scenario Comparison")
    print(
        "(BASE: non-flat curve | PARALLEL+100: all knots +100bps | KEYRATE+50: 5y knot +50bps)"
    )
    print()
    print(comparison)

    # Deltas to show impact
    delta_parallel = comparison.with_columns(
        (pl.col("pv_net_cf_parallel100") - pl.col("pv_net_cf_base")).alias(
            "delta_parallel"
        ),
        (pl.col("pv_net_cf_keyrate50") - pl.col("pv_net_cf_base")).alias(
            "delta_keyrate"
        ),
    ).select(["point_id", "delta_parallel", "delta_keyrate"])

    print()
    print("PV Impact (vs BASE):")
    print(delta_parallel)
