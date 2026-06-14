# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 (Typed Inputs Variant) -> Step 07: Anniversary-Aware Cashflows

Demonstrates ``af.projection.anniversary_mask()`` to drive cashflows that
fire only on contract anniversaries.

New in this step vs Step 05 (rate curves):
  - ``af.projection.anniversary_mask()`` returns a per-row List<Boolean> of
    length ``n_periods``, ``True`` at every period that closes a full
    12-month anniversary from the schedule start. It is broadcast across
    all rows.
  - An "anniversary commission" cashflow of 0.5% × av_pp_init fires only on
    anniversary months, and its PV is added to the output alongside the
    existing PVs.

Real-model use cases: anniversary commissions, anniversary fees,
age-band step-ups, GMxB ratchets at anniversary.
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

# Anniversary commission: 50 bps of initial AV paid on each policy anniversary
ANNIVERSARY_COMMISSION_RATE = 0.005

# Assumption table caps
SCALAR_DURATION_CAP = 14  # Mortality scalars cover durations 0-14
SELECT_PERIOD = 24  # Select mortality covers durations 0-24


def load_assumptions() -> dict:
    """Load assumption tables and typed inputs from parquet files.

    Returns:
        Dict with keys: ``mortality``, ``mortality_scalars``, ``inv_returns``,
        ``curve_base`` (the non-flat zero-rate curve from parquet).

    """
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
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame, curve: Curve) -> pl.DataFrame:
    """Run the projection and return per-policy PVs including anniversary commission.

    Args:
        af: ActuarialFrame with model points.
        curve: Discount curve for Section 11.

    Returns:
        Collected DataFrame with per-policy PV columns including
        ``pv_anniversary_commission``.

    """
    assumptions = load_assumptions()
    mortality = assumptions["mortality"]
    mortality_scalars = assumptions["mortality_scalars"]
    inv_returns_table = assumptions["inv_returns"]

    # Shared calendar-grid schedule for discount-factor year-fractions.
    # 241 cumulative t-values matching the 240-period projection timeline.
    schedule_shared = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=PROJECTION_MONTHS,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    t_years_list = schedule_shared.cumulative_year_fractions()

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    af = af.projection.set(schedule=schedule_shared)
    af.projection_date = af.projection.period_dates()

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 2B: ANNIVERSARY MASK (NEW in step 07)
    # =====================================================================
    # ``af.projection.anniversary_mask()`` returns a per-row List<Boolean>
    # of length ``n_periods``, True at every period that closes a full
    # 12-month anniversary from the schedule start. The mask is purely
    # structural — it depends only on n_periods and frequency.
    #
    # The frame's other list columns are length ``n_periods + 1`` (one
    # entry per period boundary). Append ``False`` so the mask aligns
    # with the boundary list while preserving the True positions at
    # months 12, 24, ... within the projection window.
    af.is_anniversary = pl.concat_list(
        [
            af.projection.anniversary_mask(),
            pl.lit([False], dtype=pl.List(pl.Boolean)),
        ]
    )

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
    # SECTION 9B: ANNIVERSARY COMMISSION (NEW in step 07)
    # =====================================================================
    # On each anniversary month, pay 0.5% of the initial AV per surviving
    # policy.  af.is_anniversary is a list-of-bool; when() broadcasts it
    # element-wise across the projection list.
    #
    # Note: av_pp_init is a scalar (per-policy constant), so this commision
    # is a flat amount per survivor, not AV-at-time-t dependent.

    af.anniversary_commission = (
        when(af.is_anniversary)
        .then(af.av_pp_init * ANNIVERSARY_COMMISSION_RATE * af.pols_if)
        .otherwise(0.0)
    )

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
        - af.anniversary_commission
        - af.av_change
    )

    # =====================================================================
    # SECTION 11: DISCOUNT FACTORS & PRESENT VALUES
    # =====================================================================

    disc_factors_list = curve.discount_factor(t_years_list)  # list[float], len 241
    af.disc_factors = pl.lit(
        pl.Series("disc_factors", [disc_factors_list], dtype=pl.List(pl.Float64))
    ).first()

    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_net_cf = (af.net_cf * af.disc_factors).list.sum()

    # NEW: PV of anniversary commissions — should be positive (commissions paid out).
    af.pv_anniversary_commission = (
        af.anniversary_commission * af.disc_factors
    ).list.sum()

    return af.collect().select(
        [
            "point_id",
            "pv_net_cf",
            "pv_claims",
            "pv_premiums",
            "pv_anniversary_commission",
        ]
    )


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    mp = pl.read_parquet(DATA_DIR / "model_points.parquet")

    assumptions = load_assumptions()
    curve_base = assumptions["curve_base"]

    result = main(ActuarialFrame(mp), curve_base)

    print("PV Net Cashflow + Claims + Premiums + Anniversary Commission")
    print()
    print(result)

    # Sanity check: anniversary count per policy.
    # For monthly frequency, anniversary_mask has True at indices 11, 23, 35, ...
    # (every 12th period, 0-indexed).  With n_periods=241, the full mask has
    # 20 True values.  Each policy only runs policy_term*12 months from inception,
    # and has already been in-force for some time at the valuation date — so the
    # within-term count is less than policy_term.  See README.md for details.
    print()
    print("Anniversary count check (True values in mask, capped at policy_term):")
    for row in mp.iter_rows(named=True):
        expected_anniversaries = row["policy_term"]  # full-life count if new biz
        print(
            f"  policy {row['point_id']}: term={row['policy_term']}y"
            f"  → full-life count={expected_anniversaries}"
            f" (projection starts in-force; fewer in remaining term)"
        )
