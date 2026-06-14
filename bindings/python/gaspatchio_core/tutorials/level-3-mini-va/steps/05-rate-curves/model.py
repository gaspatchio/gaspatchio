# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 → Step 05: Valuation Basis — Rate Curve Discounting

Replaces constant discount rate with risk-free rate curve from table.

Delta from Step 04:
  - SECTION 1: loads risk_free_rates table; DISCOUNT_RATE_ANNUAL removed
  - SECTION 11: rewritten — rate lookup by year, cum_prod discounting
  - __main__: output columns changed to show pv_premiums instead of claim breakdown
  - All other section contents: UNCHANGED
"""

import datetime
import math
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table

# =========================================================================
# SECTION 1: ASSUMPTIONS
# =========================================================================

MODEL_DIR = Path(__file__).parent
DATA_DIR = MODEL_DIR / "data"

INFLATION_RATE = 0.01
VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 240

SELECT_PERIOD_LEN = 25
SCALAR_DURATION_CAP = 14
LAPSE_DURATION_CAP = 14
SURR_CHARGE_DURATION_CAP = 9


def load_assumptions():
    """Load assumption tables from parquet files."""
    mortality_select = Table(
        name="mortality_select",
        source=pl.read_parquet(DATA_DIR / "mortality_select.parquet"),
        dimensions={
            "table_id": "table_id",
            "attained_age": "attained_age",
            "duration": "duration",
        },
        value="mort_rate",
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

    surrender_charges = Table(
        name="surrender_charges",
        source=pl.read_parquet(DATA_DIR / "surrender_charges.parquet"),
        dimensions={"surr_charge_id": "surr_charge_id", "duration": "duration"},
        value="surr_charge_rate",
    )

    lapse_rates = Table(
        name="lapse_rates",
        source=pl.read_parquet(DATA_DIR / "lapse_rates.parquet"),
        dimensions={"lapse_id": "lapse_id", "duration": "duration"},
        value="lapse_rate",
    )

    # NEW: Risk-free rate curve (scenario × currency × year)
    risk_free_rates = Table(
        name="risk_free_rates",
        source=pl.read_parquet(DATA_DIR / "risk_free_rates.parquet"),
        dimensions={"scenario": "scenario", "currency": "currency", "year": "year"},
        value="forward_rate",
    )

    return {
        "mortality_select": mortality_select,
        "mortality_scalars": mortality_scalars,
        "inv_returns": inv_returns_table,
        "surrender_charges": surrender_charges,
        "lapse_rates": lapse_rates,
        "risk_free_rates": risk_free_rates,
    }


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Main model projection."""
    assumptions = load_assumptions()
    mortality_select = assumptions["mortality_select"]
    mortality_scalars = assumptions["mortality_scalars"]
    inv_returns_table = assumptions["inv_returns"]
    surrender_charges = assumptions["surrender_charges"]
    lapse_rates = assumptions["lapse_rates"]
    risk_free_rates = assumptions["risk_free_rates"]

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
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 3: MORTALITY RATES
    # =====================================================================

    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    af.duration_capped = af.duration.clip(upper_bound=SELECT_PERIOD_LEN - 1)

    af.base_mort_rate = mortality_select.lookup(
        table_id=af.mort_table_id,
        attained_age=af.age,
        duration=af.duration_capped,
    )

    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
    )

    af.mort_rate = af.base_mort_rate * af.mort_scalar
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 5: INVESTMENT RETURNS & ACCOUNT VALUE (before lapse)
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
    af.av_pp_mid_mth = af.av_pp_after_fee + 0.5 * af.inv_income_pp

    # =====================================================================
    # SECTION 4: LAPSE RATES (with dynamic adjustment)
    # =====================================================================

    af.lapse_duration_capped = af.duration.clip(upper_bound=LAPSE_DURATION_CAP)
    af.base_lapse_rate = lapse_rates.lookup(
        lapse_id=af.lapse_id, duration=af.lapse_duration_capped
    )

    af.itm = af.av_pp_mid_mth / af.sum_assured.cast(pl.Float64)

    af.dyn_lapse_factor = (1.0 - af.M_param * (1.0 / af.itm - af.D_param)).clip(
        af.L, af.U
    )

    af.lapse_rate = (af.dyn_lapse_factor * af.base_lapse_rate).clip(
        af.dyn_lapse_floor, None
    )

    af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

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

    af.sum_assured_f = af.sum_assured.cast(pl.Float64)

    af.claim_pp_death = (
        when(af.has_gmdb)
        .then(
            when(af.av_pp_mid_mth > af.sum_assured_f)
            .then(af.av_pp_mid_mth)
            .otherwise(af.sum_assured_f)
        )
        .otherwise(af.av_pp_mid_mth)
    )
    af.claims_death = af.claim_pp_death * af.pols_death

    af.duration_year_capped = af.duration.clip(upper_bound=SURR_CHARGE_DURATION_CAP)
    af.surr_charge_rate = (
        when(af.has_surr_charge)
        .then(
            surrender_charges.lookup(
                surr_charge_id=af.surr_charge_id,
                duration=af.duration_year_capped,
            )
        )
        .otherwise(0.0)
    )
    af.surr_charge = af.surr_charge_rate * af.av_pp_mid_mth * af.pols_lapse
    af.claims_lapse = af.av_pp_mid_mth * af.pols_lapse - af.surr_charge

    af.claim_pp_maturity = (
        when(af.has_gmab)
        .then(
            when(af.av_pp > af.sum_assured_f).then(af.av_pp).otherwise(af.sum_assured_f)
        )
        .otherwise(af.av_pp)
    )
    af.claims_maturity = af.claim_pp_maturity * af.pols_maturity

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
    # SECTION 11: DISCOUNT FACTORS & PRESENT VALUES (was: constant rate)
    # =====================================================================
    # NEW: Discount rate from risk-free rate curve, looked up by projection year

    # Projection year for rate lookup
    af.year = af.month // 12

    # Look up annual discount rate from rate curve
    # Using "BASE" scenario and "USD" currency (hardcoded for now)
    af.disc_rate = risk_free_rates.lookup(
        scenario=pl.lit("BASE"), currency=pl.lit("USD"), year=af.year
    )

    # Convert annual rate to monthly: (1 + r_ann)^(1/12) - 1
    af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0

    # Discount factors: cumulative product of per-period factors.
    # With varying rates, we can't use (1+r)^(-t) because the rate changes
    # each year. Instead, compute 1/(1+r_mth) per period and take the
    # running product: df[t] = (1/(1+r[0])) × (1/(1+r[1])) × ... × (1/(1+r[t]))
    af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
    af.disc_factors = af.per_period_disc.cum_prod()

    # Present values
    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_claims_death = (af.claims_death * af.disc_factors).list.sum()
    af.pv_claims_lapse = (af.claims_lapse * af.disc_factors).list.sum()
    af.pv_claims_maturity = (af.claims_maturity * af.disc_factors).list.sum()
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
