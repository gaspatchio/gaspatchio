# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 → Step 06: Reconciled Model (reference answer)

This is the model_with_gaps.py with all 4 gaps fixed. It should reconcile
against lifelib IntegratedLife at 0.0000% for the 2023Q4IF dataset.

Fixes applied:
  FIX 1 (SECTION 5):  accumulate() for AV rollforward
  FIX 2 (SECTION 6):  BEF_DECR decrement ordering
  FIX 3 (SECTION 4):  DL001/DL002 formula selection
  FIX 4 (SECTION 11): Closed-form discount factors
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table

# =========================================================================
# SECTION 1: ASSUMPTIONS
# =========================================================================

STEP_DIR = Path(__file__).resolve().parent
L4_DIR = STEP_DIR.parent.parent.parent / "level-4-lifelib"
ASSUMPTIONS_DIR = L4_DIR / "base" / "assumptions"

INFLATION_RATE = 0.01
VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 82

SELECT_PERIOD_LEN = 25
SCALAR_DURATION_CAP = 14
LAPSE_DURATION_CAP = 14
SURR_CHARGE_DURATION_CAP = 9


def load_assumptions():
    """Load assumption tables from L4 parquet files."""
    mortality_select = Table(
        name="mortality_select",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "mortality_select.parquet"),
        dimensions={
            "table_id": "table_id",
            "attained_age": "attained_age",
            "duration": "duration",
        },
        value="mort_rate",
    )

    mortality_scalars = Table(
        name="mortality_scalars",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "mortality_scalars.parquet"),
        dimensions={"scalar_id": "scalar_id", "duration": "duration"},
        value="mort_scalar",
    )

    lapse_rates = Table(
        name="lapse_rates",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "lapse_rates.parquet"),
        dimensions={"lapse_id": "lapse_id", "duration": "duration"},
        value="lapse_rate",
    )

    surrender_charges = Table(
        name="surrender_charges",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "surrender_charges.parquet"),
        dimensions={"surr_charge_id": "surr_charge_id", "duration": "duration"},
        value="surr_charge_rate",
    )

    risk_free_rates = Table(
        name="risk_free_rates",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "risk_free_rates.parquet"),
        dimensions={"scenario": "scenario", "currency": "currency", "year": "year"},
        value="forward_rate",
    )

    # DataFrames for joins
    product_params = pl.read_parquet(ASSUMPTIONS_DIR / "product_params_gmxb.parquet")
    dyn_lapse_params = pl.read_parquet(ASSUMPTIONS_DIR / "dynamic_lapse_params.parquet")
    space_params = pl.read_parquet(ASSUMPTIONS_DIR / "space_params.parquet")

    # Scenario returns — unpivot from wide to long format
    scenario_returns = pl.read_parquet(ASSUMPTIONS_DIR / "scenario_returns.parquet")
    scenario_returns_long = scenario_returns.unpivot(
        index="t",
        on=["FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6"],
        variable_name="fund_index",
        value_name="inv_return_mth",
    )
    inv_returns_table = Table(
        name="inv_returns",
        source=scenario_returns_long,
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    return {
        "mortality_select": mortality_select,
        "mortality_scalars": mortality_scalars,
        "inv_returns": inv_returns_table,
        "surrender_charges": surrender_charges,
        "lapse_rates": lapse_rates,
        "risk_free_rates": risk_free_rates,
        "product_params": product_params,
        "dyn_lapse_params": dyn_lapse_params,
        "space_params": space_params,
    }


# =========================================================================
# MODEL ENTRY POINT
# =========================================================================


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Main model projection — reconciled reference answer."""
    assumptions = load_assumptions()
    mortality_select = assumptions["mortality_select"]
    mortality_scalars = assumptions["mortality_scalars"]
    inv_returns_table = assumptions["inv_returns"]
    surrender_charges = assumptions["surrender_charges"]
    lapse_rates = assumptions["lapse_rates"]
    risk_free_rates = assumptions["risk_free_rates"]
    product_params = assumptions["product_params"]
    dyn_lapse_params = assumptions["dyn_lapse_params"]
    space_params = assumptions["space_params"]

    # -----------------------------------------------------------------
    # DATA JOINS (L4 infrastructure — not gaps)
    # -----------------------------------------------------------------

    # Each join happens on the frame itself rather than on a collected
    # DataFrame that is then re-wrapped, so every parameter column arrives
    # through a door the frame records.

    # 1. Product params join
    af = af.join(
        product_params.select(
            [
                "product_id",
                "plan_id",
                "mort_table_male",
                "mort_table_female",
                "mort_scalar_id",
                "lapse_id",
                "dyn_lapse_param_id",
                "dyn_lapse_floor",
                "maint_fee_rate",
                "has_gmdb",
                "has_gmab",
                "surr_charge_id",
                "commission_rate",
                "load_prem_rate",
                "premium_type",
                "has_surr_charge",
            ]
        ),
        on=["product_id", "plan_id"],
        how="left",
        maintain_order="left",
    )

    # 2. Dynamic lapse params join. DL001 uses U/L/M/D and DL002 uses
    #    FactorCap/FactorFloor/Y/Power, so each row of the parameter table
    #    leaves the other formula's columns empty; those neutral defaults are
    #    filled on the parameter table, before it reaches the frame.
    dyn_lapse_params_filled = dyn_lapse_params.select(
        [
            "index",
            "formula_id",
            "U",
            "L",
            "M",
            "D",
            "FactorCap",
            "FactorFloor",
            "Y",
            "Power",
        ]
    ).with_columns(
        [
            pl.col("U").fill_null(2.0),
            pl.col("L").fill_null(0.5),
            pl.col("M").fill_null(0.0),
            pl.col("D").fill_null(0.0),
            pl.col("FactorCap").fill_null(2.0),
            pl.col("FactorFloor").fill_null(0.5),
            pl.col("Y").fill_null(1.0),
            pl.col("Power").fill_null(1.0),
        ]
    )
    af = af.join(
        dyn_lapse_params_filled,
        left_on="dyn_lapse_param_id",
        right_on="index",
        how="left",
        maintain_order="left",
    )

    # 3. Space params join
    gmxb_expenses = space_params.filter(pl.col("space") == "GMXB").select(
        ["expense_acq", "expense_maint"]
    )
    af.expense_acq = float(gmxb_expenses["expense_acq"].item())
    af.expense_maint = float(gmxb_expenses["expense_maint"].item())

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
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 3: MORTALITY RATES
    # =====================================================================

    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    af.duration_capped = (
        when(af.duration > SELECT_PERIOD_LEN - 1)
        .then(SELECT_PERIOD_LEN - 1)
        .otherwise(af.duration)
    )

    af.base_mort_rate = mortality_select.lookup(
        table_id=af.mort_table_id,
        attained_age=af.age,
        duration=af.duration_capped,
    )

    af.scalar_duration_capped = (
        when(af.duration > SCALAR_DURATION_CAP)
        .then(SCALAR_DURATION_CAP)
        .otherwise(af.duration)
    )
    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.scalar_duration_capped,
    )

    af.mort_rate = (
        when((af.duration >= 0) & (af.duration <= SCALAR_DURATION_CAP))
        .then(af.mort_scalar * af.base_mort_rate)
        .otherwise(0.0)
    )

    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =====================================================================
    # SECTION 3b: BASE LAPSE RATES
    # =====================================================================

    af.lapse_duration_capped = (
        when(af.duration > LAPSE_DURATION_CAP)
        .then(LAPSE_DURATION_CAP)
        .otherwise(af.duration)
    )

    af.base_lapse_rate = (
        when((af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP))
        .then(
            lapse_rates.lookup(lapse_id=af.lapse_id, duration=af.lapse_duration_capped)
        )
        .otherwise(0.0)
    )

    # =====================================================================
    # SECTION 5: INVESTMENT RETURNS & ACCOUNT VALUE (FIX 1)
    # =====================================================================

    af.inv_return_mth = inv_returns_table.lookup(t=af.month, fund_index=af.fund_index)

    # Account value via accumulate() — production pattern
    # Linear recurrence: av[t] = av[t-1] * growth[t-1] + prem_to_av[t]
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    # Premium deposited to AV: only at entry (duration_mth_t == 0)
    af.prem_to_av = (
        when(af.duration_mth_t == 0)
        .then(af.premium_pp * (1.0 - af.load_prem_rate))
        .otherwise(0.0)
    )

    # Shifted growth: multiplier[t] = growth[t-1], with 1.0 at t=0
    af.shifted_growth = af.combined_growth_factor.projection.previous_period(
        fill_value=1.0
    )

    # Accumulate: av_bef_fee[t] = av_bef_fee[t-1] * growth[t-1] + prem_to_av[t]
    af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
        initial=af.av_pp_init,
        multiplier=af.shifted_growth,
        addend=af.prem_to_av,
    )

    # Decompose AV into timing stages
    af.av_pp_bef_prem = af.av_pp_bef_fee - af.prem_to_av
    af.maint_fee_pp = af.av_pp_bef_fee * af.maint_fee_rate / 12.0
    af.av_pp_bef_inv = af.av_pp_bef_fee - af.maint_fee_pp
    af.inv_income_pp = af.inv_return_mth * af.av_pp_bef_inv
    af.av_pp_mid_mth = af.av_pp_bef_inv + 0.5 * af.inv_income_pp

    # =====================================================================
    # SECTION 4: DYNAMIC LAPSE (FIX 3)
    # =====================================================================

    af.itm = af.av_pp_mid_mth / af.sum_assured

    # DL001: clip(1 - M * (1/ITM - D), L, U)
    af.dl001_unbounded = 1.0 - af.M * (1.0 / af.itm - af.D)
    af.dl001_factor = (
        when(af.dl001_unbounded < af.L)
        .then(af.L)
        .otherwise(
            when(af.dl001_unbounded > af.U).then(af.U).otherwise(af.dl001_unbounded)
        )
    )

    # DL002: clip(Y * ITM^Power, FactorFloor, FactorCap)
    af.dl002_unbounded = af.Y * af.itm**af.Power
    af.dl002_factor = (
        when(af.dl002_unbounded < af.FactorFloor)
        .then(af.FactorFloor)
        .otherwise(
            when(af.dl002_unbounded > af.FactorCap)
            .then(af.FactorCap)
            .otherwise(af.dl002_unbounded)
        )
    )

    # Select by formula_id
    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

    # Finalize lapse rate with floor and monthly conversion
    af.lapse_rate_unfloored = af.dyn_lapse_factor * af.base_lapse_rate
    af.lapse_rate = (
        when((af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP))
        .then(
            when(af.lapse_rate_unfloored < af.dyn_lapse_floor)
            .then(af.dyn_lapse_floor)
            .otherwise(af.lapse_rate_unfloored)
        )
        .otherwise(0.0)
    )

    af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =====================================================================
    # SECTION 6: POLICY COUNTS (FIX 2)
    # =====================================================================

    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
    # Cumulative survival from the combined decrement:
    #   tpx[t] = (1 - q[0]) * (1 - q[1]) * ... * (1 - q[t-1])
    # rate_timing="beginning_of_period" is the default, and it is the
    # convention wanted here: the decrement at t has not been applied yet,
    # so the first element is 1.0 -- every policy in force at t=0.
    af.survival_prob = af.combined_decrement.projection.cumulative_survival()

    af.maturity_month = af.policy_term * 12

    # Policies in force before maturity (includes maturity month, excludes pre-entry)
    af.pols_if_bef_mat = (
        when((af.duration_mth_t > 0) & (af.duration_mth_t <= af.maturity_month))
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )
    af.pols_if = af.pols_if_bef_mat

    # Maturities first
    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.pols_if_bef_mat)
        .otherwise(0.0)
    )

    # Remove maturities, add new business
    af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)
    af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz

    # Deaths from BEF_DECR population, lapses from survivors
    af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
    af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth

    # =====================================================================
    # SECTION 7: CLAIMS
    # =====================================================================

    af.claim_pp_death = (
        when(af.has_gmdb)
        .then(
            when(af.av_pp_mid_mth > af.sum_assured)
            .then(af.av_pp_mid_mth)
            .otherwise(af.sum_assured)
        )
        .otherwise(af.av_pp_mid_mth)
    )
    af.claims_death = af.claim_pp_death * af.pols_death

    af.duration_year_capped = (
        when(af.duration > SURR_CHARGE_DURATION_CAP)
        .then(SURR_CHARGE_DURATION_CAP)
        .otherwise(af.duration)
    )
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
            when(af.av_pp_bef_prem > af.sum_assured)
            .then(af.av_pp_bef_prem)
            .otherwise(af.sum_assured)
        )
        .otherwise(af.av_pp_bef_prem)
    )
    af.claims_maturity = af.claim_pp_maturity * af.pols_maturity

    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    # =====================================================================
    # SECTION 8: PREMIUMS
    # =====================================================================

    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)
    af.premiums = af.premium_pp_list * af.pols_if_bef_decr

    # =====================================================================
    # SECTION 9: EXPENSES & COMMISSIONS
    # =====================================================================

    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)
    af.expense_acq_total = af.expense_acq * af.pols_new_biz
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if_bef_decr * af.inflation_factor
    )
    af.expenses = af.expense_acq_total + af.expense_maint_total
    af.commissions = af.commission_rate * af.premiums

    # =====================================================================
    # SECTION 10: NET CASHFLOW
    # =====================================================================

    # AV at BEF_MAT timing
    af.av_at_bef_mat = af.av_pp_bef_prem * af.pols_if_bef_mat
    af.av_at_bef_mat_next = af.av_at_bef_mat.projection.next_period(fill_value=0.0)
    af.av_change = af.av_at_bef_mat_next - af.av_at_bef_mat

    # Investment income with BEF_MAT next
    af.pols_if_bef_mat_next = af.pols_if_bef_mat.projection.next_period(fill_value=0.0)
    af.inv_income = (
        af.inv_income_pp * af.pols_if_bef_mat_next
        + 0.5 * af.inv_income_pp * (af.pols_death + af.pols_lapse)
    )

    af.net_cf = (
        af.premiums
        + af.inv_income
        - af.claims
        - af.expenses
        - af.commissions
        - af.av_change
    )

    # =====================================================================
    # SECTION 11: DISCOUNT FACTORS (FIX 4)
    # =====================================================================

    af.year = af.month // 12

    af.disc_rate = risk_free_rates.lookup(scenario="BASE", currency="USD", year=af.year)

    af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0

    # Discount factors: closed-form (1 + r)^(-t)
    # The ** operator works directly on the list column: no exp/log rewrite.
    af.disc_factors = (1.0 + af.disc_rate_mth) ** (af.month * -1.0)

    # =====================================================================
    # SECTION 12: PRESENT VALUES
    # =====================================================================

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
    mp = pl.read_parquet(L4_DIR / "base" / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(
        result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"])
    )
