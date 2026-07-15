# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 → Step 04: Policyholder Behaviour — Dynamic Lapse

Replaces constant lapse with table-based rates adjusted by a dynamic
lapse factor that depends on how "in the money" the guarantee is.

Delta from Step 03:
  - SECTION 1: loads lapse_rates table; LAPSE_RATE_ANNUAL constant removed
  - SECTION 4: rewritten with table lookup + dynamic lapse factor
  - Section ordering: AV (section 5) computed before lapse (section 4 moved after 5)
  - Model points: added lapse_id, formula_id, dyn_lapse params
  - All other section contents: UNCHANGED (but section ordering changed)
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

DISCOUNT_RATE_ANNUAL = 0.04
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

    # NEW: Lapse rates by duration
    lapse_rates = Table(
        name="lapse_rates",
        source=pl.read_parquet(DATA_DIR / "lapse_rates.parquet"),
        dimensions={"lapse_id": "lapse_id", "duration": "duration"},
        value="lapse_rate",
    )

    return {
        "mortality_select": mortality_select,
        "mortality_scalars": mortality_scalars,
        "inv_returns": inv_returns_table,
        "surrender_charges": surrender_charges,
        "lapse_rates": lapse_rates,
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
    # SECTION 5: INVESTMENT RETURNS & ACCOUNT VALUE (moved before lapse)
    # =====================================================================
    # NOTE: Section 5 comes before Section 4 because dynamic lapse
    # depends on account value (ITM ratio)

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
    # SECTION 4: LAPSE RATES (was: constant rate)
    # =====================================================================
    # NEW: Table-based lapse + dynamic adjustment based on ITM ratio
    #
    # 1. Look up base lapse rate from table by duration
    # 2. Calculate ITM ratio: AV / guarantee (sum_assured)
    # 3. Apply dynamic lapse formula: clip(1 - M * (1/ITM - D), L, U)
    # 4. Final lapse = max(floor, factor * base_lapse)

    # Base lapse rate from table
    af.lapse_duration_capped = af.duration.clip(upper_bound=LAPSE_DURATION_CAP)
    af.base_lapse_rate = lapse_rates.lookup(
        lapse_id=af.lapse_id, duration=af.lapse_duration_capped
    )

    # ITM ratio: how "in the money" is the guarantee?
    # ITM > 1 means AV > guarantee (guarantee has less value)
    # ITM < 1 means guarantee > AV (guarantee is valuable, less likely to lapse)
    af.itm = af.av_pp_mid_mth / af.sum_assured.cast(pl.Float64)

    # Dynamic lapse formula DL001: clip(1 - M * (1/ITM - D), L, U)
    # With M=0 and D=0 (our simplified params), this gives factor = 1.0
    # meaning no dynamic adjustment. To see the effect, try M=0.5, D=1.0
    af.dyn_lapse_factor = (1.0 - af.M_param * (1.0 / af.itm - af.D_param)).clip(
        af.L, af.U
    )

    # Final lapse rate: apply factor, enforce floor
    af.lapse_rate = (af.dyn_lapse_factor * af.base_lapse_rate).clip(
        af.dyn_lapse_floor, None
    )

    # Convert to monthly
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
                # Expected misses (null surr_charge_id) are discarded
                # by the when() guard; declare them explicitly.
                on_missing="nan",
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
    # SECTION 11: DISCOUNT FACTORS & PRESENT VALUES
    # =====================================================================

    disc_rate_mth = (1 + DISCOUNT_RATE_ANNUAL) ** (1 / 12) - 1

    af.disc_factors = (
        af.month.cast(pl.Float64) * -1.0 * math.log(1 + disc_rate_mth)
    ).exp()

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
    print(
        result.select(
            ["point_id", "pv_net_cf", "pv_claims", "pv_claims_death", "pv_claims_lapse"]
        )
    )
