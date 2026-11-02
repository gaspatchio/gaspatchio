# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
GMDB / GMAB variable annuity, reconciled to lifelib IntegratedLife.

A full monthly projection of a guaranteed-benefit variable annuity: select
mortality with duration scalars, dynamic lapse driven by how far the account
value sits in the money, an account-value recurrence, death / lapse / maturity
claims, expenses, commissions, and the present values those cashflows come to.
Every present value matches lifelib to 0.0000% (``reconcile.py``), and so does
every intermediate variable, period by period (``reconcile_full.py``).

The projection reads like a worksheet. Simple arithmetic is written with
operators, because the formula is the calculation; the operations with an
actuarial name of their own -- cumulative survival, the account-value
accumulation, discount factors, period shifts -- are called by that name.

Sections
--------
1.  Time setup: entry duration, remaining term, the projection timeline
2.  Mortality rates (select table x duration scalar, annual -> monthly)
3.  Base lapse rates
5.  Investment returns per fund
6.  Account value (a linear recurrence through ``projection.accumulate``)
7.  Dynamic lapse (DL001 / DL002 in-the-money formulas)
8.  Policy counts (cumulative survival, maturities, new business, decrements)
9.  Death claims       10. Lapse claims (net of surrender charge)
11. Maturity claims    12. Premiums
13. Expenses           14. Commissions
15. Net cashflow       16. Discount factors        17. Present values
"""

import datetime
from pathlib import Path
from typing import Literal

import polars as pl
from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import PeriodSum, Sum

StorageModeType = Literal["auto", "hash", "array"]

# What a total of this book means. Two columns rather than seventeen: a
# portfolio total is a number somebody reports, and the rest of the model
# is how it was arrived at. Nothing here folds a rate, because there is no
# portfolio value of a monthly mortality rate.
#
# This is the tuple `run_aggregated` takes, so a scenario sweep and
# `gspio calc-graph --portfolio` read one declaration rather than two.
# `Sum` folds across the book and `PeriodSum` down the timeline:
# `pv_net_cf` holds one value per policy and `net_cf` one per month, so
# each column takes the fold its own shape asks for.
AGGREGATIONS = (Sum("pv_net_cf"), PeriodSum("net_cf"))

# Model configuration — overridable for different model point sets
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
    """Load the assumption tables the projection reads.

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

    # Join product params to get mort_table_male, mort_scalar_id, lapse_id, dyn_lapse_param_id, dyn_lapse_floor, maint_fee_rate
    # Also get GMDB/GMAB flags, commission, load, surrender charge, and premium type
    # The enrichment happens on the frame itself rather than on a collected
    # DataFrame that is then re-wrapped: every column arriving from a
    # parameter table comes through a door the frame records, so the model
    # can still say where maint_fee_rate came from (*Audit by default*).
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

    # Dynamic lapse parameters (formula_id, U, L, M, D, FactorCap, FactorFloor, Y, Power).
    # DL001 uses U/L/M/D and DL002 uses FactorCap/FactorFloor/Y/Power, so every
    # row of the parameter table leaves the other formula's columns empty. Those
    # neutral defaults belong to the parameter table, so they are filled on the
    # assumption data before it reaches the frame rather than on the model
    # points afterwards.
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

    # Join space parameters (expense_acq, expense_maint)
    # Note: All model points in this dataset are GMXB products (GMDB/GMAB)
    # Filter space_params to GMXB and add to all model points
    gmxb_expenses = space_params.filter(pl.col("space") == "GMXB").select(
        ["expense_acq", "expense_maint"]
    )

    # Every model point uses the GMXB space parameters, so each expense is one
    # number written straight onto the frame.
    af.expense_acq = float(gmxb_expenses["expense_acq"].item())
    af.expense_maint = float(gmxb_expenses["expense_maint"].item())

    # =========================================================================
    # SECTION 1: TIME SETUP
    # =========================================================================

    # Parse the entry date. The model points carry it as text, and turning
    # text into a date is the one step in this section with no gaspatchio
    # form of its own: the engine's own parser does it.
    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # Duration in months at the valuation date: whole calendar months from
    # entry to valuation, which is exactly what lifelib's
    # (val.year * 12 + val.month) - (entry.year * 12 + entry.month) counts.
    af.duration_mth_init = af.entry_date_parsed.date.months_between(VALUATION_DATE)

    # Remaining term in months per policy: floored at zero, because a policy
    # already past its term projects nothing, and capped at the projection
    # horizon.
    af.term_months_left = af.policy_term * 12 - af.duration_mth_init
    af.remaining_term_months = (
        when(af.term_months_left < 0)
        .then(0)
        .otherwise(
            when(af.term_months_left > projection_months)
            .then(projection_months)
            .otherwise(af.term_months_left)
        )
    )

    # Create per-policy projection timeline (each policy projects only as long as
    # needed). per_policy=True yields variable-length (jagged) timelines, so a
    # short-term policy doesn't carry the longest-lived policy's horizon.
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
        per_policy=True,
    )
    af.projection_date = af.projection.period_dates()

    # projection.set() has already stamped af.month -- elapsed whole months
    # from the valuation date, 0, 1, 2, ... down each policy's own timeline.
    # Deriving it a second time from the period dates would be the same
    # number written twice.

    # Duration at time t (months since issue). Named duration_mth_t to avoid
    # a clash with the duration_mth input column.
    af.duration_mth_t = af.duration_mth_init + af.month

    # Duration in years (for assumption lookups)
    af.duration = af.duration_mth_t // 12

    # Attained age at time t
    af.age = af.age_at_entry + af.duration

    # =========================================================================
    # SECTION 2: MORTALITY RATES
    # =========================================================================

    # Select mortality table based on sex
    # Every model point in this set is male; the lookup stays general.
    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    # Duration capped for select period lookup: past the select period the
    # table holds one ultimate row, so every later duration reads that row.
    af.duration_capped = (
        when(af.duration > SELECT_PERIOD_LEN - 1)
        .then(SELECT_PERIOD_LEN - 1)
        .otherwise(af.duration)
    )

    # Base mortality rate from select table
    af.base_mort_rate = mortality_select.lookup(
        table_id=af.mort_table_id,
        attained_age=af.age,
        duration=af.duration_capped,
    )

    # Mortality scalar by duration, on a key capped at the scalar table's
    # last duration.
    af.scalar_duration_capped = (
        when(af.duration > SCALAR_DURATION_CAP)
        .then(SCALAR_DURATION_CAP)
        .otherwise(af.duration)
    )
    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.scalar_duration_capped,
    )

    # Final mortality rate (annual)
    # Note: lifelib has an off-by-one in mort_scalar_key() where it caps duration
    # at mort_scalar_len (=15) instead of mort_scalar_len-1 (=14). At duration 15,
    # the reindex fails → NaN → mort_rate=0. To match lifelib, we zero mort_rate
    # at durations beyond the scalar table range.
    af.mort_rate = (
        when((af.duration >= 0) & (af.duration <= SCALAR_DURATION_CAP))
        .then(af.mort_scalar * af.base_mort_rate)
        .otherwise(0.0)
    )

    # Convert annual to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =========================================================================
    # SECTION 3: BASE LAPSE RATES (lookup only - dynamic adjustment comes later)
    # =========================================================================

    # Duration capped for lapse lookup (L001 goes to duration 14)
    af.lapse_duration_capped = (
        when(af.duration > LAPSE_DURATION_CAP)
        .then(LAPSE_DURATION_CAP)
        .otherwise(af.duration)
    )

    # Base lapse rate from lapse table (annual rate)
    # Same lifelib off-by-one as mort_scalar: lapse_len()=15 caps at 15 not 14.
    # Zero lapse_rate at durations beyond the table range to match lifelib.
    af.base_lapse_rate = (
        when((af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP))
        .then(
            lapse_rates.lookup(
                lapse_id=af.lapse_id,
                duration=af.lapse_duration_capped,
            )
        )
        .otherwise(0.0)
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

    # Account value recurrence (lifelib ProductBase):
    #   av_pp_bef_fee(t) = av_pp_bef_prem(t) + prem_to_av(t)
    #   av_pp_bef_inv(t) = av_pp_bef_fee(t) * (1 - fee_rate/12)
    #   av_pp_bef_prem(t+1) = av_pp_bef_inv(t) * (1 + return(t))
    #
    # Rearranging into linear recurrence on av_pp_bef_fee:
    #   av_pp_bef_fee(t) = av_pp_bef_fee(t-1) * growth(t-1) + prem_to_av(t)
    #   where growth(t) = (1 - fee_rate/12) * (1 + return(t))
    #
    # This is computed by accumulate(): state[t] = state[t-1] * M[t] + A[t]
    # Works for both IF (prem_to_av=0) and NB (prem_to_av>0 at entry).

    # Combined growth factor per period: (1 - fee/12) * (1 + return)
    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    # Premium deposited to account value: premium after load, only at entry
    # prem_to_av = premium_pp * (1 - load_prem_rate) when duration_mth_t == 0
    af.prem_to_av = (
        when(af.duration_mth_t == 0)
        .then(af.premium_pp * (1.0 - af.load_prem_rate))
        .otherwise(0.0)
    )

    # Shifted growth: multiplier[t] = growth[t-1], with 1.0 at t=0
    # At t=0 no growth is applied (state = initial + premium)
    af.shifted_growth = af.combined_growth_factor.projection.previous_period(
        fill_value=1.0
    )

    # Accumulate: av_bef_fee[t] = av_bef_fee[t-1] * growth[t-1] + prem_to_av[t]
    af.av_pp_bef_fee = af.shifted_growth.projection.accumulate(
        initial=af.av_pp_init,
        multiplier=af.shifted_growth,
        addend=af.prem_to_av,
    )

    # av_pp_bef_prem is av_pp_bef_fee before premium (for use in maturity claims)
    # = av_pp_bef_fee - prem_to_av (only differs at entry period)
    af.av_pp_bef_prem = af.av_pp_bef_fee - af.prem_to_av

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

    # DL001 formula: 1 - M * (1/ITM - D), held between the floor L and the cap U
    af.dl001_unbounded = 1.0 - af.M * (1.0 / af.itm - af.D)
    af.dl001_factor = (
        when(af.dl001_unbounded < af.L)
        .then(af.L)
        .otherwise(
            when(af.dl001_unbounded > af.U).then(af.U).otherwise(af.dl001_unbounded)
        )
    )

    # DL002 formula: Y * ITM^Power, held between FactorFloor and FactorCap
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

    # Select factor based on formula_id
    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

    # Final lapse_rate: max(dyn_lapse_floor, dyn_lapse_factor * base_lapse_rate)
    # Zero at durations beyond lapse table range (lifelib off-by-one: lapse_len=15, table 0-14)
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

    # Convert to monthly: lapse_rate_mth = 1 - (1 - lapse_rate)^(1/12)
    af.lapse_rate_mth = 1.0 - (1.0 - af.lapse_rate) ** (1.0 / 12.0)

    # =========================================================================
    # SECTION 8: POLICY COUNTS
    # =========================================================================

    # Combined decrement rate: 1 - (1 - mort) * (1 - lapse)
    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)

    # Cumulative survival from the combined decrement:
    #   tpx[t] = (1 - q[0]) * (1 - q[1]) * ... * (1 - q[t-1])
    # rate_timing="beginning_of_period" is the default and the convention this
    # model needs: the decrement at t has NOT yet been applied, so the first
    # element is 1.0 and every policy is fully in force at the valuation date.
    af.survival_prob = af.combined_decrement.projection.cumulative_survival()

    # Maturity month (policy_term in years * 12)
    af.maturity_month = af.policy_term * 12

    # Policies in force before maturity: active only when before/at maturity
    # AND after the entry month. NB enters via pols_new_biz at duration_mth_t == 0;
    # pols_if_bef_mat must be 0 there. For IF business duration_mth_t > 0 holds
    # throughout projection.
    af.pols_if_bef_mat = (
        when((af.duration_mth_t > 0) & (af.duration_mth_t <= af.maturity_month))
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    # pols_if = pols_if_bef_mat (lifelib's pols_if is BEF_MAT)
    af.pols_if = af.pols_if_bef_mat

    # Policies maturing this period (at exact maturity month)
    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.pols_if_bef_mat)
        .otherwise(0.0)
    )

    # Policies in force before new business
    af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity

    # New business: enters at duration_mth_t == 0
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)

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

    # For GMDB products, calculate max(sum_assured, av_pp_mid_mth)
    # For non-GMDB products, just use av_pp_mid_mth
    # Use nested when() to handle both the GMDB check and the max logic
    af.claim_pp_death = (
        when(af.has_gmdb)
        .then(
            # GMDB: return sum_assured if it's greater, else av_pp_mid_mth
            when(af.av_pp_mid_mth > af.sum_assured)
            .then(af.av_pp_mid_mth)
            .otherwise(af.sum_assured)
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
    af.duration_year_capped = (
        when(af.duration_year > SURR_CHARGE_DURATION_CAP)
        .then(SURR_CHARGE_DURATION_CAP)
        .otherwise(af.duration_year)
    )

    # Lookup surrender charge rate by duration_year and surr_charge_id.
    # Polars evaluates BOTH branches of when/then/otherwise, so the lookup
    # still runs for policies without a surrender schedule (null id). Those
    # rows are expected misses discarded by the guard — declare that with
    # on_missing="nan" so genuine misses on guarded rows stay visible.
    af.surr_charge_rate = (
        when(af.has_surr_charge)
        .then(
            surrender_charges.lookup(
                duration=af.duration_year_capped,
                surr_charge_id=af.surr_charge_id,
                on_missing="nan",
            )
        )
        .otherwise(0.0)
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
            when(af.av_pp_bef_prem > af.sum_assured)
            .then(af.av_pp_bef_prem)
            .otherwise(af.sum_assured)
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

    # Premium per policy: non-zero only at t=0 for single-premium products.
    # premium_pp is a scalar from model points; this gives a list column that's
    # the per-policy premium at t=0 and 0.0 elsewhere.
    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)

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

    # Inflation factor: (1 + inflation_rate)^(month/12) per period.
    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)

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
    # A bare string is a dimension VALUE (VLOOKUP semantics), so "USD" and
    # "BASE" name the currency and the rate scenario themselves; a column is
    # named as af.scenario_id.
    # The dtype IS the distinction, so ask the frame for it -- af.schema reads
    # it off the plan, nothing run. A label is a label however parquet stored
    # it: Categorical and Enum are labels too, never a quiet fall back to BASE.
    rate_scenario = (
        af.scenario_id
        if af.schema.get("scenario_id") in (pl.String, pl.Categorical, pl.Enum)
        else "BASE"
    )
    af.disc_rate = risk_free_rates.lookup(
        scenario=rate_scenario, currency="USD", year=af.year
    )

    # Convert annual rate to monthly: (1 + r_ann)^(1/12) - 1
    af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0

    # Discount factors: (1 + disc_rate_mth)^(-month) per period. "spot" is
    # that formula exactly -- the period's own rate raised to minus the
    # period's own month -- which is how lifelib builds them.
    af = af.finance.discount_factor(
        rate_col="disc_rate_mth",
        periods_col="month",
        output_col="disc_factors",
        method="spot",
    )

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


# =========================================================================
# STANDALONE EXECUTION
# =========================================================================

if __name__ == "__main__":
    # Standalone entry point. `gspio run-model` never runs this block: it
    # builds the frame from your model-points file and calls main() directly,
    # so everything main() needs must be created inside main().
    mp = pl.read_parquet(MODEL_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(result.select(["point_id", "product_id", "pv_net_cf", "pv_claims"]))
