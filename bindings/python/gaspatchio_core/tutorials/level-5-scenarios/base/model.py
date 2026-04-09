"""
Level 5: Scenario-Ready Variable Annuity Model

This is the reconciled L4 appliedlife model, ready for scenario analysis.
The model accepts optional assumption overrides and scenario-specific
investment returns, making it compatible with gaspatchio's scenario API.

Key scenario entry points:
  - assumptions_override: dict of shocked Table objects (for parameter shocks)
  - scenario_returns_override: DataFrame with scenario_id column (for stochastic)
  - scenario_id column on ActuarialFrame: used for discount rate lookup (BASE/UP/DOWN)
"""

import datetime
import math
from pathlib import Path
from typing import Literal

import polars as pl
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table

StorageModeType = Literal["auto", "hash", "array"]

# Model configuration
VALUATION_DATE = datetime.date(2024, 1, 1)  # base_date + 1 day
PROJECTION_MONTHS = 82  # Default for 2023Q4IF; 252 for 202401NB

# Paths
MODEL_DIR = Path(__file__).parent
ASSUMPTIONS_DIR = MODEL_DIR / "assumptions"

# Assumption table caps (from lifelib)
SELECT_PERIOD_LEN = 25  # Select mortality period is 25 years
SCALAR_DURATION_CAP = 14  # Mortality scalar table has durations 0-14
LAPSE_DURATION_CAP = 14  # Lapse table has durations 0-14


def load_assumptions(storage_mode: StorageModeType = "auto"):
    """Load assumption tables needed for the model.

    Args:
        storage_mode: Storage backend for tables - "auto" (default), "hash", or "array".

    """
    product_params = pl.read_parquet(ASSUMPTIONS_DIR / "product_params_gmxb.parquet")

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

    scenario_returns_df = pl.read_parquet(ASSUMPTIONS_DIR / "scenario_returns.parquet")

    dyn_lapse_params_df = pl.read_parquet(
        ASSUMPTIONS_DIR / "dynamic_lapse_params.parquet"
    )

    space_params_df = pl.read_parquet(ASSUMPTIONS_DIR / "space_params.parquet")

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
    assumptions_override: dict[str, object] | None = None,
    projection_months: int = PROJECTION_MONTHS,
) -> ActuarialFrame:
    """
    Main model entry point.

    Args:
        af: ActuarialFrame with model points
        scenario_returns_override: Optional DataFrame of investment returns.
            If provided, uses these instead of loading from assumptions.
            For stochastic mode, include a 'scenario_id' column.
            Format: columns = [scenario_id (optional)], t, FUND1, ..., FUND6
        assumptions_override: Optional dict of assumption overrides.
            Keys match load_assumptions() output; missing keys fall back to defaults.
        projection_months: Number of months to project. Default 82 for IF,
            use 252 for 202401NB.

    Returns:
        ActuarialFrame with projection results

    """
    # Load assumptions (allow external overrides for scenario analysis)
    assumptions = assumptions_override or load_assumptions()
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

    # Join product params to get lookup IDs and product flags
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

    # Join dynamic lapse parameters
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
            # Fill nulls with neutral defaults
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
    gmxb_expenses = space_params.filter(pl.col("space") == "GMXB").select(
        ["expense_acq", "expense_maint"]
    )
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

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # duration_mth_init = (val_date.year * 12 + val_date.month) - (entry_date.year * 12 + entry_date.month)
    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    # Remaining term in months per policy, capped at projection horizon
    af.remaining_term_months = (af.policy_term * 12 - af.duration_mth_init).clip(
        lower_bound=0, upper_bound=projection_months
    )

    # Create per-policy projection timeline (each policy projects only as long as needed)
    af = af.date.create_projection_timeline(
        valuation_date=VALUATION_DATE,
        projection_end_type="term_months",
        projection_end_value="remaining_term_months",
        projection_frequency="monthly",
        output_column="projection_date",
    )

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =========================================================================
    # SECTION 2: MORTALITY RATES
    # =========================================================================

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

    # Zero mort_rate at durations beyond scalar table range (lifelib off-by-one)
    af.mort_rate = when(
        (af.duration >= 0) & (af.duration <= SCALAR_DURATION_CAP)
    ).then(af.mort_scalar * af.base_mort_rate).otherwise(0.0)

    # Convert annual to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =========================================================================
    # SECTION 3: BASE LAPSE RATES
    # =========================================================================

    af.lapse_duration_capped = af.duration.clip(upper_bound=LAPSE_DURATION_CAP)

    # Zero lapse_rate at durations beyond table range (lifelib off-by-one)
    af.base_lapse_rate = when(
        (af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP)
    ).then(
        lapse_rates.lookup(
            lapse_id=af.lapse_id,
            duration=af.lapse_duration_capped,
        )
    ).otherwise(0.0)

    # =========================================================================
    # SECTION 5: INVESTMENT RETURNS
    # =========================================================================

    # Detect stochastic mode (scenario_id column in returns data)
    has_stochastic_returns = "scenario_id" in scenario_returns.columns

    scenario_returns_long = scenario_returns.unpivot(
        index=["scenario_id", "t"] if has_stochastic_returns else "t",
        on=["FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6"],
        variable_name="fund_index",
        value_name="inv_return_mth",
    )

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

    # Account value recurrence:
    #   av_pp_bef_fee(t) = av_pp_bef_fee(t-1) * growth(t-1) + prem_to_av(t)
    #   growth(t) = (1 - fee_rate/12) * (1 + return(t))
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    # Premium deposited to AV: premium after load, only at entry
    af.prem_to_av = (
        af.premium_pp * (1.0 - af.load_prem_rate) * (af.duration_mth_t == 0)
    )

    af.shifted_growth = af.combined_growth_factor.projection.previous_period(
        fill_value=1.0
    )

    af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
        initial=af.av_pp_init,
        multiply=af.shifted_growth,
        add=af.prem_to_av,
    )

    af.av_pp_bef_prem = af.av_pp_bef_fee - af.prem_to_av
    af.maint_fee_pp = af.av_pp_bef_fee * af.maint_fee_rate / 12.0
    af.av_pp_bef_inv = af.av_pp_bef_fee - af.maint_fee_pp
    af.inv_income_pp = af.inv_return_mth * af.av_pp_bef_inv
    af.av_pp_mid_mth = af.av_pp_bef_inv + 0.5 * af.inv_income_pp

    # =========================================================================
    # SECTION 7: DYNAMIC LAPSE
    # =========================================================================

    # ITM (in-the-money) ratio
    af.itm = af.av_pp_mid_mth / af.sum_assured

    # DL001: clip(1 - M * (1/ITM - D), L, U)
    af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

    # DL002: clip(Y * ITM^Power, FactorFloor, FactorCap)
    af.dl002_factor = (af.Y * af.itm**af.Power).clip(af.FactorFloor, af.FactorCap)

    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

    # Final lapse_rate: max(dyn_lapse_floor, dyn_lapse_factor * base_lapse_rate)
    af.lapse_rate = when(
        (af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP)
    ).then(
        (af.dyn_lapse_factor * af.base_lapse_rate).clip(af.dyn_lapse_floor, None)
    ).otherwise(0.0)

    # Convert to monthly: lapse_rate_mth = 1 - (1 - lapse_rate)^(1/12)
    af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =========================================================================
    # SECTION 8: POLICY COUNTS
    # =========================================================================

    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)
    af.survival_factor = 1.0 - af.combined_decrement
    af.cumulative_survival = af.survival_factor.cum_prod()
    af.survival_prob = af.cumulative_survival.projection.previous_period(fill_value=1.0)

    af.maturity_month = af.policy_term * 12

    af.pols_if_bef_mat = (
        af.survival_prob
        * af.policy_count
        * (af.duration_mth_t <= af.maturity_month)
        * (af.duration_mth_t > 0)
    )

    af.pols_if = af.pols_if_bef_mat
    af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)
    af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity
    af.pols_new_biz = af.policy_count * (af.duration_mth_t == 0)
    af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz
    af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
    af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth

    # =========================================================================
    # SECTION 9: DEATH CLAIMS
    # =========================================================================

    af.sum_assured_f = af.sum_assured.cast(pl.Float64)

    # GMDB: max(sum_assured, av_pp_mid_mth); non-GMDB: av_pp_mid_mth
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

    # =========================================================================
    # SECTION 10: LAPSE CLAIMS (with surrender charges)
    # =========================================================================

    af.claim_pp_lapse = af.av_pp_mid_mth

    af.duration_year = af.duration_mth_t // 12
    SURR_CHARGE_DURATION_CAP = 9
    af.duration_year_capped = af.duration_year.clip(
        upper_bound=SURR_CHARGE_DURATION_CAP
    )

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

    af.surr_charge = af.surr_charge_rate * af.av_pp_mid_mth * af.pols_lapse
    af.claims_lapse = af.av_pp_mid_mth * af.pols_lapse - af.surr_charge

    # =========================================================================
    # SECTION 11: MATURITY CLAIMS
    # =========================================================================

    # GMAB: max(sum_assured, av_pp_bef_prem); non-GMAB: av_pp_bef_prem
    af.claim_pp_maturity = (
        when(af.has_gmab)
        .then(
            when(af.av_pp_bef_prem > af.sum_assured_f)
            .then(af.av_pp_bef_prem)
            .otherwise(af.sum_assured_f)
        )
        .otherwise(af.av_pp_bef_prem)
    )

    af.claims_maturity = af.claim_pp_maturity * af.pols_maturity

    # =========================================================================
    # SECTION 12: PREMIUMS
    # =========================================================================

    # Single premium: non-zero only at entry (duration_mth_t == 0)
    af.premium_pp_list = af.premium_pp * (af.duration_mth_t == 0)
    af.premiums = af.premium_pp_list * af.pols_if_bef_decr

    # =========================================================================
    # SECTION 13: EXPENSES
    # =========================================================================

    INFLATION_RATE = 0.01  # 1% annual inflation

    # Inflation factor: (1 + inflation_rate)^(month/12)
    af.inflation_factor = (af.month / 12.0 * math.log(1.0 + INFLATION_RATE)).exp()

    af.expense_acq_total = af.expense_acq * af.pols_new_biz
    af.expense_maint_total = (
        (af.expense_maint / 12.0) * af.pols_if_bef_decr * af.inflation_factor
    )
    af.expenses = af.expense_acq_total + af.expense_maint_total

    # =========================================================================
    # SECTION 14: COMMISSIONS
    # =========================================================================

    af.commissions = af.commission_rate * af.premiums

    # =========================================================================
    # SECTION 15: NET CASHFLOW
    # =========================================================================

    af.av_at_bef_mat = af.av_pp_bef_prem * af.pols_if_bef_mat
    af.av_at_bef_mat_next = af.av_at_bef_mat.projection.next_period(fill_value=0.0)
    af.av_change = af.av_at_bef_mat_next - af.av_at_bef_mat

    af.pols_if_bef_mat_next = af.pols_if_bef_mat.projection.next_period(fill_value=0.0)

    # inv_income = inv_income_pp * surviving_pols + 0.5 * inv_income_pp * decrementing_pols
    af.inv_income = (
        af.inv_income_pp * af.pols_if_bef_mat_next
        + 0.5 * af.inv_income_pp * (af.pols_death + af.pols_lapse)
    )

    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    # net_cf = premiums + inv_income - claims - expenses - commissions - av_change
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

    af.year = af.month // 12

    # Scenario-aware discount rate lookup:
    # - String scenario_id (BASE/UP/DOWN): use for discount rate lookup
    # - Integer scenario_id (stochastic): always use BASE discount rates
    # - No scenario_id: use BASE
    if "scenario_id" in af.columns:
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

    # Discount factors: (1 + disc_rate_mth)^(-month) via exp/log identity
    af.disc_factors = (
        af.month.cast(pl.Float64) * -1.0 * (1.0 + af.disc_rate_mth).log()
    ).exp()

    # =========================================================================
    # SECTION 17: PRESENT VALUES
    # =========================================================================

    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_claims_death = (af.claims_death * af.disc_factors).list.sum()
    af.pv_claims_lapse = (af.claims_lapse * af.disc_factors).list.sum()
    af.pv_claims_maturity = (af.claims_maturity * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
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


if __name__ == "__main__":
    mp = pl.read_parquet(MODEL_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"]))
