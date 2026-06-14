# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
MVP Gaspatchio Model: GMDB PLAN_A Single Policy

This is a minimal model built incrementally to match lifelib output.
Start with the simplest possible implementation and add complexity
one variable at a time, reconciling after each step.

Model Point: point_id=1, GMDB PLAN_A, Male, age 70, 10-year term, 100 policies

Build Order (Phase 1 - Base Decrements - COMPLETE):
1. [x] Basic structure with projection timeline
2. [x] mort_rate - mortality lookup (select table + scalars)
3. [x] pols_death - deaths
4. [x] base lapse_rate - lapse lookup (without dynamic adjustment)
5. [x] pols_lapse - lapses
6. [x] pols_if with combined decrements
   STATUS: All policy variables match lifelib (0.0000% diff)
   NOTE: Dynamic lapse disabled in lifelib for this phase (see learnings.md)

Build Order (Phase 2 - Account Value & Dynamic Lapse):
7. [x] account value (av_pp_at) - requires scenario data
8. [x] dynamic lapse factor
9. [x] re-enable dynamic lapse in lifelib

Build Order (Phase 3 - Cashflows):
10. [x] claims (death, lapse, maturity)
11. [x] premiums
12. [x] expenses (acquisition + maintenance with inflation)
13. [x] commissions
14. [x] net cashflow (inv_income + av_change)

Build Order (Phase 4 - Present Values - COMPLETE):
14. [x] discount rates
15. [x] present values
"""

import datetime
import math
from pathlib import Path
from typing import Literal

import polars as pl

from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table

StorageModeType = Literal["auto", "hash", "array"]

# Model configuration matching lifelib run_id=6
VALUATION_DATE = datetime.date(2024, 1, 1)  # base_date + 1 day
PROJECTION_MONTHS = 82  # From lifelib output

# Paths
MODEL_DIR = Path(__file__).parent
ASSUMPTIONS_DIR = MODEL_DIR / "assumptions"

# Assumption table caps (from lifelib)
SELECT_PERIOD_LEN = 25  # Select mortality period is 25 years
SCALAR_DURATION_CAP = 14  # Mortality scalar table has durations 0-14
LAPSE_DURATION_CAP = 14  # Lapse table has durations 0-14


def load_assumptions(storage_mode: StorageModeType = "auto"):
    """Load assumption tables needed for MVP.

    Args:
        storage_mode: Storage backend for tables - "auto" (default), "hash", or "array".

    """
    # Product params (to get mort_table_male, mort_scalar_id)
    product_params = pl.read_parquet(ASSUMPTIONS_DIR / "product_params_gmxb.parquet")

    # Mortality select table (table_id, attained_age, duration -> mort_rate)
    mort_select_df = pl.read_parquet(ASSUMPTIONS_DIR / "mortality_select.parquet")
    mortality_select = Table(
        name="mortality_select",
        source=mort_select_df,
        dimensions={
            "table_id": "table_id",
            "attained_age": "attained_age",
            "duration": "duration",
        },
        value="mort_rate",
        storage_mode=storage_mode,
    )

    # Mortality scalars (duration, scalar_id -> mort_scalar)
    mort_scalars_df = pl.read_parquet(ASSUMPTIONS_DIR / "mortality_scalars.parquet")
    mortality_scalars = Table(
        name="mortality_scalars",
        source=mort_scalars_df,
        dimensions={
            "duration": "duration",
            "scalar_id": "scalar_id",
        },
        value="mort_scalar",
        storage_mode=storage_mode,
    )

    # Lapse rates (duration, lapse_id -> lapse_rate)
    lapse_rates_df = pl.read_parquet(ASSUMPTIONS_DIR / "lapse_rates.parquet")
    lapse_rates = Table(
        name="lapse_rates",
        source=lapse_rates_df,
        dimensions={
            "duration": "duration",
            "lapse_id": "lapse_id",
        },
        value="lapse_rate",
        storage_mode=storage_mode,
    )

    # Surrender charges (duration, surr_charge_id -> surr_charge_rate)
    surr_charges_df = pl.read_parquet(ASSUMPTIONS_DIR / "surrender_charges.parquet")
    surrender_charges = Table(
        name="surrender_charges",
        source=surr_charges_df,
        dimensions={
            "duration": "duration",
            "surr_charge_id": "surr_charge_id",
        },
        value="surr_charge_rate",
        storage_mode=storage_mode,
    )

    # Scenario returns (fund_index, t -> inv_return_mth)
    scenario_returns_df = pl.read_parquet(ASSUMPTIONS_DIR / "scenario_returns.parquet")

    # Dynamic lapse params (param_id -> formula parameters)
    dyn_lapse_params_df = pl.read_parquet(
        ASSUMPTIONS_DIR / "dynamic_lapse_params.parquet"
    )

    # Space params (space -> expense_acq, expense_maint)
    space_params_df = pl.read_parquet(ASSUMPTIONS_DIR / "space_params.parquet")

    # Risk-free rates (scenario, currency, year -> forward_rate)
    # Note: Using full table with scenario/currency dimensions, will filter in lookup
    risk_free_rates_df = pl.read_parquet(ASSUMPTIONS_DIR / "risk_free_rates.parquet")
    risk_free_rates = Table(
        name="risk_free_rates",
        source=risk_free_rates_df,
        dimensions={
            "scenario": "scenario",
            "currency": "currency",
            "year": "year",
        },
        value="forward_rate",
        storage_mode=storage_mode,
    )

    return {
        "product_params": product_params,
        "mortality_select": mortality_select,
        "mortality_scalars": mortality_scalars,
        "lapse_rates": lapse_rates,
        "surrender_charges": surrender_charges,
        "scenario_returns": scenario_returns_df,
        "dyn_lapse_params": dyn_lapse_params_df,
        "space_params": space_params_df,
        "risk_free_rates": risk_free_rates,
    }


def main(
    af: ActuarialFrame,
    scenario_returns_override: pl.DataFrame | None = None,
) -> ActuarialFrame:
    """
    Main model entry point.

    Args:
        af: ActuarialFrame with model points
        scenario_returns_override: Optional DataFrame of investment returns.
            If provided, uses these instead of loading from assumptions.
            For stochastic mode, include a 'scenario_id' column.
            Format: columns = [scenario_id (optional)], t, FUND1, ..., FUND6

    Returns:
        ActuarialFrame with projection results

    """
    # Load assumptions
    assumptions = load_assumptions()
    product_params = assumptions["product_params"]
    mortality_select = assumptions["mortality_select"]
    mortality_scalars = assumptions["mortality_scalars"]
    lapse_rates = assumptions["lapse_rates"]
    surrender_charges = assumptions["surrender_charges"]
    scenario_returns = (
        scenario_returns_override
        if scenario_returns_override is not None
        else assumptions["scenario_returns"]
    )
    dyn_lapse_params = assumptions["dyn_lapse_params"]
    space_params = assumptions["space_params"]
    risk_free_rates = assumptions["risk_free_rates"]

    # Join product params to get mort_table_male, mort_scalar_id, lapse_id, dyn_lapse_param_id, dyn_lapse_floor, maint_fee_rate
    # Also get GMDB/GMAB flags, commission, load, surrender charge, and premium type
    mp = af.collect()
    mp = mp.join(
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
    )

    # Join dynamic lapse parameters (formula_id, U, L, M, D, FactorCap, FactorFloor, Y, Power)
    mp = mp.join(
        dyn_lapse_params.select(
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
        ),
        left_on="dyn_lapse_param_id",
        right_on="index",
        how="left",
    ).with_columns(
        [
            # Fill nulls with neutral defaults (DL001 uses U/L/M/D, DL002 uses FactorCap/FactorFloor/Y/Power)
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

    # Join space parameters (expense_acq, expense_maint)
    # Note: All model points in this dataset are GMXB products (GMDB/GMAB)
    # Filter space_params to GMXB and add to all model points
    gmxb_expenses = space_params.filter(pl.col("space") == "GMXB").select(
        ["expense_acq", "expense_maint"]
    )

    # Cross join to add expense parameters to all model points
    # (all model points use GMXB space parameters)
    mp = mp.with_columns(
        [
            pl.lit(gmxb_expenses["expense_acq"].item()).alias("expense_acq"),
            pl.lit(gmxb_expenses["expense_maint"].item()).alias("expense_maint"),
        ]
    )

    af = ActuarialFrame(mp)

    # =========================================================================
    # SECTION 1: TIME SETUP
    # =========================================================================

    # Parse entry date
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # Calculate initial duration in months (lifelib formula)
    # duration_mth_init = (val_date.year * 12 + val_date.month) - (entry_date.year * 12 + entry_date.month)
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    # Create projection timeline
    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value=PROJECTION_MONTHS,
        projection_frequency="monthly",
        output_column="projection_date",
    )

    # Month index (0 = valuation date)
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    # Duration at time t (months since issue) - rename to avoid conflict with input column
    af.duration_mth_t = af.duration_mth_init + af.month

    # Duration in years (for assumption lookups)
    af.duration = af.duration_mth_t // 12

    # Attained age at time t
    af.age = af.age_at_entry + af.duration

    # =========================================================================
    # SECTION 2: MORTALITY RATES
    # =========================================================================

    # Select mortality table based on sex
    # For MVP, we know it's Male, but let's be general
    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    # Duration capped for select period lookup
    af.duration_capped = af.duration.clip(upper_bound=SELECT_PERIOD_LEN - 1)

    # Base mortality rate from select table
    af.base_mort_rate = mortality_select.lookup(
        table_id=af.mort_table_id,
        attained_age=af.age,
        duration=af.duration_capped,
    )

    # Mortality scalar by duration
    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
    )

    # Final mortality rate (annual)
    af.mort_rate = af.mort_scalar * af.base_mort_rate

    # Convert annual to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =========================================================================
    # SECTION 3: BASE LAPSE RATES (lookup only - dynamic adjustment comes later)
    # =========================================================================

    # Duration capped for lapse lookup (L001 goes to duration 14)
    af.lapse_duration_capped = af.duration.clip(upper_bound=LAPSE_DURATION_CAP)

    # Base lapse rate from lapse table (annual rate)
    af.base_lapse_rate = lapse_rates.lookup(
        lapse_id=af.lapse_id,
        duration=af.lapse_duration_capped,
    )

    # Note: Final lapse_rate and lapse_rate_mth will be calculated in Section 7
    # after dynamic lapse factor is computed. Policy counts depend on this.

    # =========================================================================
    # SECTION 5: INVESTMENT RETURNS
    # =========================================================================

    # Check if scenario_returns has scenario_id (stochastic mode)
    # This allows the same model to work with:
    # - Single scenario returns (deterministic, no scenario_id column)
    # - Multiple scenario returns (stochastic, with scenario_id column)
    has_stochastic_returns = "scenario_id" in scenario_returns.columns

    # Unpivot scenario returns from wide format (FUND1-FUND6 columns) to long format
    # Include scenario_id in index if present (stochastic mode)
    scenario_returns_long = scenario_returns.unpivot(
        index=["scenario_id", "t"] if has_stochastic_returns else "t",
        on=["FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6"],
        variable_name="fund_index",
        value_name="inv_return_mth",
    )

    # Create a Table for investment returns lookup
    # Add scenario_id dimension if present (stochastic mode)
    if has_stochastic_returns:
        inv_returns_table = Table(
            name="inv_returns",
            source=scenario_returns_long,
            dimensions={
                "scenario_id": "scenario_id",
                "t": "t",
                "fund_index": "fund_index",
            },
            value="inv_return_mth",
        )
    else:
        inv_returns_table = Table(
            name="inv_returns",
            source=scenario_returns_long,
            dimensions={
                "t": "t",
                "fund_index": "fund_index",
            },
            value="inv_return_mth",
        )

    # Lookup investment returns using Table.lookup()
    # Use scenario_id from af if both returns and af have it (stochastic mode)
    if has_stochastic_returns and "scenario_id" in af.columns:
        af.inv_return_mth = inv_returns_table.lookup(
            scenario_id=af.scenario_id,
            t=af.month,
            fund_index=af.fund_index,
        )
    else:
        af.inv_return_mth = inv_returns_table.lookup(
            t=af.month,
            fund_index=af.fund_index,
        )

    # =========================================================================
    # SECTION 6: ACCOUNT VALUE
    # =========================================================================

    # Account value formulas (single premium, no COI):
    # av_pp_bef_prem(t=0) = av_pp_init
    # av_pp_bef_prem(t>0) = av_pp_bef_inv(t-1) + inv_income_pp(t-1)
    # av_pp_bef_fee(t) = av_pp_bef_prem(t) + premium_pp (0 after initial)
    # maint_fee_pp(t) = av_pp_bef_fee(t) * maint_fee_rate / 12
    # av_pp_bef_inv(t) = av_pp_bef_fee(t) - maint_fee_pp(t)
    # inv_income_pp(t) = inv_return_mth(t) * av_pp_bef_inv(t)
    # av_pp_mid_mth(t) = av_pp_bef_inv(t) + 0.5 * inv_income_pp(t)

    # For single premium (no premium after t=0), av_pp_bef_fee = av_pp_bef_prem
    # Combined factor per period: (1 - maint_fee_rate/12) * (1 + inv_return_mth)
    # Closed form: av_pp_bef_prem(t) = av_pp_init * prod(combined_factor[i], i=0..t-1)

    # Combined growth factor: (1 - fee/12) * (1 + return) - broadcasts scalar * list
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    # Cumulative product of growth factors
    af.cumulative_growth_factor = af.combined_growth_factor.cum_prod()

    # Shift by one period using projection accessor: at t=0 should be 1.0
    af.prev_cumulative_growth_factor = (
        af.cumulative_growth_factor.projection.previous_period(fill_value=1.0)
    )

    # av_pp_bef_prem(t) = av_pp_init * cumulative_factor(t-1)
    af.av_pp_bef_prem = af.av_pp_init * af.prev_cumulative_growth_factor

    # For single premium: av_pp_bef_fee = av_pp_bef_prem
    af.av_pp_bef_fee = af.av_pp_bef_prem

    # Maintenance fee per policy
    af.maint_fee_pp = af.av_pp_bef_fee * af.maint_fee_rate / 12.0

    # Account value before investment (after fee deduction)
    af.av_pp_bef_inv = af.av_pp_bef_fee - af.maint_fee_pp

    # Investment income for current period
    af.inv_income_pp = af.inv_return_mth * af.av_pp_bef_inv

    # Mid-month account value (used for ITM calculation)
    af.av_pp_mid_mth = af.av_pp_bef_inv + 0.5 * af.inv_income_pp

    # =========================================================================
    # SECTION 7: DYNAMIC LAPSE
    # =========================================================================

    # Calculate ITM (in-the-money) ratio
    af.itm = af.av_pp_mid_mth / af.sum_assured

    # Dynamic lapse params (formula_id, U, L, M, D, etc.) already joined in data preparation

    # DL001 formula: clip(1 - M * (1/ITM - D), L, U)
    af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

    # DL002 formula: clip(Y * ITM^Power, FactorFloor, FactorCap)
    af.dl002_factor = (af.Y * af.itm**af.Power).clip(af.FactorFloor, af.FactorCap)

    # Select factor based on formula_id
    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

    # Final lapse_rate: max(dyn_lapse_floor, dyn_lapse_factor * base_lapse_rate)
    af.lapse_rate = (af.dyn_lapse_factor * af.base_lapse_rate).clip(
        af.dyn_lapse_floor, None
    )

    # Convert to monthly: lapse_rate_mth = 1 - (1 - lapse_rate)^(1/12)
    af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =========================================================================
    # SECTION 8: POLICY COUNTS
    # =========================================================================

    # Combined decrement rate: 1 - (1 - mort) * (1 - lapse)
    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)

    # Survival factor per period
    af.survival_factor = 1.0 - af.combined_decrement

    # Cumulative survival: product of survival factors through each period
    af.cumulative_survival = af.survival_factor.cum_prod()

    # Shift by 1: survival_prob at t=0 is 1.0, at t=1 is cumulative[0], etc.
    af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    # Maturity month (policy_term in years * 12)
    af.maturity_month = af.policy_term * 12

    # Policies in force before maturity: survival_prob * policy_count * (before maturity)
    af.pols_if_bef_mat = (
        af.survival_prob * af.policy_count * (af.duration_mth_t <= af.maturity_month)
    )

    # pols_if = pols_if_bef_mat (lifelib's pols_if is BEF_MAT)
    af.pols_if = af.pols_if_bef_mat

    # Policies maturing this period (at exact maturity month)
    af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)

    # Policies in force before new business
    af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity

    # New business: enters at duration_mth_t == 0
    af.pols_new_biz = af.policy_count * (af.duration_mth_t == 0)

    # Policies in force before decrements
    af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz

    # Deaths: from BEF_DECR population
    af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth

    # Lapses: from surviving population after deaths
    af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth

    # =========================================================================
    # SECTION 9: DEATH CLAIMS
    # =========================================================================

    # Claim per policy on death:
    # - For GMDB products: max(sum_assured, av_pp_mid_mth)
    # - For non-GMDB products: just av_pp_mid_mth

    # Cast sum_assured to Float64 for type consistency
    af.sum_assured_f = af.sum_assured.cast(pl.Float64)

    # For GMDB products, calculate max(sum_assured, av_pp_mid_mth)
    # For non-GMDB products, just use av_pp_mid_mth
    # Use nested when() to handle both the GMDB check and the max logic
    af.claim_pp_death = (
        when(af.has_gmdb)
        .then(
            # GMDB: return sum_assured if it's greater, else av_pp_mid_mth
            when(af.av_pp_mid_mth > af.sum_assured_f)
            .then(af.av_pp_mid_mth)
            .otherwise(af.sum_assured_f)
        )
        .otherwise(af.av_pp_mid_mth)
    )

    # Total death claims: claim per policy * number of deaths
    af.claims_death = af.claim_pp_death * af.pols_death

    # =========================================================================
    # SECTION 10: LAPSE CLAIMS (with surrender charges)
    # =========================================================================

    # Lapse claims formula (lifelib):
    # claim_pp_lapse = av_pp_mid_mth (gross claim before surrender charge)
    # surr_charge = surr_charge_rate * av_pp_mid_mth * pols_lapse
    # claims_lapse = av_pp_mid_mth * pols_lapse - surr_charge
    #              = (1 - surr_charge_rate) * av_pp_mid_mth * pols_lapse

    # Claim per policy on lapse (before surrender charge)
    af.claim_pp_lapse = af.av_pp_mid_mth

    # Calculate duration in years for surrender charge lookup
    # duration_year = floor(duration_mth / 12)
    af.duration_year = af.duration_mth_t // 12

    # Cap duration for surrender charge lookup (table only has durations 0-9)
    SURR_CHARGE_DURATION_CAP = 9
    af.duration_year_capped = af.duration_year.clip(
        upper_bound=SURR_CHARGE_DURATION_CAP
    )

    # Lookup surrender charge rate by duration_year and surr_charge_id
    # Use when() to conditionally lookup - avoids NaN for policies without surrender charges
    # Note: otherwise() branch uses (duration_year * 0.0) to create a list of zeros matching the shape
    af.surr_charge_rate = (
        when(af.has_surr_charge)
        .then(
            surrender_charges.lookup(
                duration=af.duration_year_capped,
                surr_charge_id=af.surr_charge_id,
            )
        )
        .otherwise(af.duration_year * 0.0)
    )

    # Calculate surrender charge per lapsing policy
    # surr_charge = surr_charge_rate * av_pp_mid_mth * pols_lapse
    af.surr_charge = af.surr_charge_rate * af.av_pp_mid_mth * af.pols_lapse

    # Net lapse claims (after deducting surrender charges)
    # claims_lapse = av_pp_mid_mth * pols_lapse - surr_charge
    af.claims_lapse = af.av_pp_mid_mth * af.pols_lapse - af.surr_charge

    # =========================================================================
    # SECTION 11: MATURITY CLAIMS
    # =========================================================================

    # Maturity claims formula (lifelib):
    # claim_pp_maturity = max(sum_assured, av_pp_bef_prem) if has_gmab else av_pp_bef_prem
    # claims_maturity = claim_pp_maturity * pols_maturity
    #
    # Timing: Uses av_pp_bef_prem (before premium), not mid_mth like death/lapse claims
    # GMAB guarantee: For GMAB products, the maturity benefit is guaranteed to be at least
    # the sum_assured, even if the account value has fallen below that level

    # Claim per policy on maturity:
    # - For GMAB products: max(sum_assured, av_pp_bef_prem)
    # - For non-GMAB products: just av_pp_bef_prem
    af.claim_pp_maturity = (
        when(af.has_gmab)
        .then(
            # GMAB: return sum_assured if it's greater, else av_pp_bef_prem
            when(af.av_pp_bef_prem > af.sum_assured_f)
            .then(af.av_pp_bef_prem)
            .otherwise(af.sum_assured_f)
        )
        .otherwise(af.av_pp_bef_prem)
    )

    # Total maturity claims: claim per policy * number of maturities
    # Note: pols_maturity is non-zero only at the exact maturity month
    af.claims_maturity = af.claim_pp_maturity * af.pols_maturity

    # =========================================================================
    # SECTION 12: PREMIUMS
    # =========================================================================

    # Premium cashflow formula (lifelib):
    # For SINGLE premium products:
    #   premium_pp(t) = premium_pp if (premium_type == "SINGLE" and duration_mth == 0) else 0
    #   premiums(t) = premium_pp(t) * pols_if_at(t, "BEF_DECR")
    #
    # All model points in this dataset have premium_type = "SINGLE"
    # Premium is paid only at t=0 (first month of projection, when duration_mth_t == 0)
    # Use pols_if_bef_decr (policies in force before decrements)

    # Premium per policy: non-zero only at t=0 for single premium products
    # premium_pp is a scalar from model points; convert to list column that's non-zero only when duration_mth_t == 0
    af.premium_pp_list = af.premium_pp * (af.duration_mth_t == 0)

    # Total premiums: premium per policy * policies in force before decrements
    af.premiums = af.premium_pp_list * af.pols_if_bef_decr

    # =========================================================================
    # SECTION 13: EXPENSES
    # =========================================================================

    # Expense cashflow formula (lifelib):
    # 1. Acquisition expense: expense_acq * pols_new_biz(t)
    #    - One-time expense at policy issue
    #    - In this dataset: all policies are existing business (entered before valuation date)
    #    - Therefore pols_new_biz = 0 throughout projection -> expense_acq_total = 0
    #
    # 2. Maintenance expense: (expense_maint / 12) * pols_if_bef_decr * inflation_factor(t)
    #    - Monthly expense (expense_maint is annual, so divide by 12)
    #    - Applied to policies in force before decrements
    #    - Inflated at 1% annual rate: inflation_factor = (1 + 0.01)^(month/12)
    #
    # 3. Total expenses: expense_acq_total + expense_maint_total

    # Inflation rate (hardcoded for now - could be loaded from assumptions later)
    INFLATION_RATE = 0.01  # 1% annual inflation

    # Inflation factor: (1 + inflation_rate)^(month/12)
    # Using exp(b * ln(a)) identity to compute scalar^list without breaking pipeline
    af.inflation_factor = (af.month / 12.0 * math.log(1.0 + INFLATION_RATE)).exp()

    # Acquisition expense total
    # Note: pols_new_biz = 0 for all existing business, so this will be 0
    af.expense_acq_total = af.expense_acq * af.pols_new_biz

    # Maintenance expense total (monthly expense inflated)
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if_bef_decr * af.inflation_factor
    )

    # Total expenses
    af.expenses = af.expense_acq_total + af.expense_maint_total

    # =========================================================================
    # SECTION 14: COMMISSIONS
    # =========================================================================

    # Commission cashflow formula (lifelib):
    # commissions(t) = commission_rate * premiums(t)
    #
    # commission_rate is from product_params (3% for PLAN_A, 5% for PLAN_B)
    # premiums(t) is calculated in SECTION 12 (non-zero only at t=0 for single premium)
    #
    # Note: For this dataset, all policies are existing single premium business
    # with no future premiums, so premiums = 0 throughout the projection
    # Therefore commissions should also = 0 throughout

    af.commissions = af.commission_rate * af.premiums

    # =========================================================================
    # SECTION 15: NET CASHFLOW
    # =========================================================================

    # Net cashflow formula (lifelib):
    # net_cf(t) = premiums(t) + inv_income(t) - claims(t) - expenses(t) - commissions(t) - av_change(t)
    #
    # where:
    #   inv_income(t) = inv_income_pp(t) * pols_if_at(t+1, "BEF_MAT")
    #                   + 0.5 * inv_income_pp(t) * (pols_death(t) + pols_lapse(t))
    #   av_change(t) = av_at(t+1, "BEF_MAT") - av_at(t, "BEF_MAT")
    #   av_at(t, "BEF_MAT") = av_pp_at(t, "BEF_PREM") * pols_if_at(t, "BEF_MAT")

    # 1. Total account value at BEF_MAT timing
    #    av_at(t, "BEF_MAT") = av_pp_bef_prem * pols_if_bef_mat
    af.av_at_bef_mat = af.av_pp_bef_prem * af.pols_if_bef_mat

    # 2. Next period's av_at(t+1, "BEF_MAT") - shift forward by 1 period
    #    For t=last period, assume av_at(t+1) = 0
    af.av_at_bef_mat_next = af.av_at_bef_mat.projection.next_period(fill_value=0.0)

    # 3. Change in account value: av_change(t) = av_at(t+1) - av_at(t)
    af.av_change = af.av_at_bef_mat_next - af.av_at_bef_mat

    # 4. Next period's pols_if_bef_mat - shift forward by 1 period
    #    For t=last period, assume pols_if_at(t+1) = 0
    af.pols_if_bef_mat_next = af.pols_if_bef_mat.projection.next_period(fill_value=0.0)

    # 5. Investment income (lifelib formula):
    #    inv_income(t) = inv_income_pp(t) * pols_if_at(t+1, "BEF_MAT")
    #                    + 0.5 * inv_income_pp(t) * (pols_death(t) + pols_lapse(t))
    #
    #    Rationale:
    #    - Surviving policies (pols_if_at(t+1)) receive full period's investment income
    #    - Policies that decrement (death/lapse) receive half the period's income
    #      (assumed to occur mid-month on average)
    af.inv_income = (
        af.inv_income_pp * af.pols_if_bef_mat_next
        + 0.5 * af.inv_income_pp * (af.pols_death + af.pols_lapse)
    )

    # 6. Total claims (all types)
    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    # 7. Net cashflow (lifelib formula):
    #    net_cf = premiums + inv_income - claims - expenses - commissions - av_change
    #
    #    Interpretation:
    #    - Positive inflows: premiums, investment income
    #    - Negative outflows: claims, expenses, commissions
    #    - Change in reserves: av_change represents the increase in liabilities
    #      (account value owed to policyholders)
    af.net_cf = (
        af.premiums
        + af.inv_income
        - af.claims
        - af.expenses
        - af.commissions
        - af.av_change
    )

    # =========================================================================
    # SECTION 16: DISCOUNT FACTORS
    # =========================================================================

    # Discount factor calculation (lifelib formulas):
    # year = t // 12  (projection year from projection month)
    # disc_rate(t) = risk_free_rate[scenario=BASE, currency=USD, year]
    # disc_rate_mth(t) = (1 + disc_rate(t))^(1/12) - 1
    # disc_factors(t) = (1 + disc_rate_mth(t))^(-t)
    #
    # Note: disc_rate is the annual forward rate for the projection year
    #       disc_rate_mth is the equivalent monthly rate
    #       disc_factors are cumulative discount factors from t=0

    # Calculate projection year (0, 1, 2, ...) from projection month
    af.year = af.month // 12

    # Lookup annual discount rate by year
    # For explicit interest rate scenarios (string scenario_id like "BASE", "UP", "DOWN"):
    #   use scenario_id for discount rate lookup
    # For stochastic scenarios (integer scenario_id like 1, 2, 3):
    #   always use "BASE" discount rates (stochastic variation is in fund returns only)
    # For no scenarios: use "BASE"
    if "scenario_id" in af.columns:
        # Check dtype by getting schema from underlying data
        scenario_dtype = mp.schema.get("scenario_id", pl.Int64)
        is_string_scenario = scenario_dtype in (pl.Utf8, pl.String)
        scenario_col = af.scenario_id if is_string_scenario else pl.lit("BASE")
    else:
        scenario_col = pl.lit("BASE")

    af.disc_rate = risk_free_rates.lookup(
        scenario=scenario_col, currency=pl.lit("USD"), year=af.year
    )

    # Convert annual rate to monthly: (1 + r_ann)^(1/12) - 1
    af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0

    # Discount factors: (1 + disc_rate_mth)^(-month)
    # Using exp/log identity: a^b = exp(b * ln(a))
    # So (1 + r)^(-t) = exp(-t * ln(1 + r))
    af.disc_factors = (
        af.month.cast(pl.Float64) * -1.0 * (1.0 + af.disc_rate_mth).log()
    ).exp()

    # =========================================================================
    # SECTION 17: PRESENT VALUES
    # =========================================================================

    # Present value formulas (lifelib):
    # PV variables are scalar (one value per policy), calculated as sum over all t:
    # pv_claims = sum(claims(t) * disc_factors(t))
    # pv_claims_death = sum(claims_death(t) * disc_factors(t))
    # pv_claims_lapse = sum(claims_lapse(t) * disc_factors(t))
    # pv_claims_maturity = sum(claims_maturity(t) * disc_factors(t))
    # pv_expenses = sum(expenses(t) * disc_factors(t))
    # pv_commissions = sum(commissions(t) * disc_factors(t))
    # pv_premiums = sum(premiums(t) * disc_factors(t))
    # pv_inv_income = sum(inv_income(t) * disc_factors(t))
    # pv_av_change = sum(av_change(t) * disc_factors(t))
    # pv_net_cf = pv_premiums + pv_inv_income - pv_claims - pv_expenses - pv_commissions - pv_av_change

    # Calculate present values by discounting and summing
    # Use list.sum() to aggregate discounted cashflows into scalar values
    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_claims_death = (af.claims_death * af.disc_factors).list.sum()
    af.pv_claims_lapse = (af.claims_lapse * af.disc_factors).list.sum()
    af.pv_claims_maturity = (af.claims_maturity * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_inv_income = (af.inv_income * af.disc_factors).list.sum()
    af.pv_av_change = (af.av_change * af.disc_factors).list.sum()

    # Net present value (derived from components)
    af.pv_net_cf = (
        af.pv_premiums
        + af.pv_inv_income
        - af.pv_claims
        - af.pv_expenses
        - af.pv_commissions
        - af.pv_av_change
    )

    return af
