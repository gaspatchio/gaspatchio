# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 3 (Typed Inputs Variant) -> Step 02: Select/Ultimate Mortality

Upgrades simple age-based mortality to a select/ultimate table with
mortality scalars and sex-based table selection — using MortalityTable
instead of a manual Table.lookup() over a separately capped key.

Delta from typed Step 01:
  - SECTION 1: load_assumptions() now loads mortality_select (wrapped in
    MortalityTable) + mortality_scalars (raw Table)
  - SECTION 3: mortality.at(age, duration, table_id) replaces the three-step
    clip -> lookup -> scalar pattern
  - Model points: added mort_table_male, mort_table_female, mort_scalar_id
  - All other sections: UNCHANGED from typed Step 01

What's different from the untyped level-3-mini-va Step 02:
  - MortalityTable wraps the raw Table, carrying age_basis and structure
    metadata. select_period=24 clamps duration internally — no manual
    capped key column needed.
  - Table dimension key "age" maps to the parquet column "attained_age"
    so MortalityTable.at() dispatches correctly.
  - Discount factors computed via Curve + Schedule (same as typed base).

Parity gate: output must match level-3-mini-va/steps/02-select-mort/
expected output when MortalityTable's select_ultimate clamp semantics
(duration > select_period -> select_period) agree with the untyped step's
when(duration > SELECT_PERIOD_LEN - 1).then(SELECT_PERIOD_LEN - 1) cap.
SELECT_PERIOD_LEN=25, so that cap is 24, identical to clamping at
select_period=24.
"""

import datetime
from pathlib import Path

import polars as pl
from gaspatchio import ActuarialFrame, Curve, MortalityTable, when
from gaspatchio.assumptions import DataDimension, Table
from gaspatchio.schedule import OneTwelfth, Schedule

# =========================================================================
# SECTION 1: FILE-BASED ASSUMPTIONS
# =========================================================================

MODEL_DIR = Path(__file__).parent
DATA_DIR = MODEL_DIR / "data"

# Model parameters
LAPSE_RATE_ANNUAL = 0.05
DISCOUNT_RATE_ANNUAL = 0.04
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
        ``curve``.

    """
    # Select mortality: 3 dimensions (table_id, attained_age, duration).
    # DataDimension(rename_to="age") renames the parquet column "attained_age"
    # to "age" in the Table's internal DataFrame, so that MortalityTable.at()
    # reads table.lookup(age=..., duration=..., table_id=...) with consistent
    # dimension names. "table_id" flows through **other.
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
    # MortalityTable wraps the raw Table with actuarial convention metadata.
    # structure="select_ultimate" + select_period=24 means duration > 24
    # is clamped to 24 — identical to capping the key at 24 by hand.
    mortality = MortalityTable(
        table=mortality_select_raw,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=SELECT_PERIOD,
    )

    # Mortality scalars: adjustment factor by duration (not mortality-shaped;
    # keep as raw Table, not wrapped in MortalityTable).
    mortality_scalars = Table(
        name="mortality_scalars",
        source=pl.read_parquet(DATA_DIR / "mortality_scalars.parquet"),
        dimensions={"scalar_id": "scalar_id", "duration": "duration"},
        value="mort_scalar",
    )

    # Investment returns Table
    inv_returns_table = Table(
        name="inv_returns",
        source=pl.read_parquet(DATA_DIR / "inv_returns.parquet"),
        dimensions={"t": "t", "fund_index": "fund_index"},
        value="inv_return_mth",
    )

    # Curve: built from curve.parquet (tenor + zero_rate columns).
    curve_df = pl.read_parquet(DATA_DIR / "curve.parquet")
    curve = Curve.from_zero_rates(
        tenors=curve_df["tenor"].to_list(),
        rates=curve_df["zero_rate"].to_list(),
    )

    return {
        "mortality": mortality,
        "mortality_scalars": mortality_scalars,
        "inv_returns": inv_returns_table,
        "curve": curve,
    }


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
    mortality_scalars = assumptions["mortality_scalars"]
    inv_returns_table = assumptions["inv_returns"]
    curve = assumptions["curve"]

    # Schedule: generates the per-period year-fraction grid using
    # OneTwelfth day-count. Declared on the frame below; Section 11 reads
    # its 241 cumulative t_years values back with af.projection.t_years().
    schedule = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=PROJECTION_MONTHS,
        frequency="1M",
        day_count=OneTwelfth(),
    )

    # =====================================================================
    # SECTION 2: TIME SETUP
    # =====================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    af.duration_mth_init = af.entry_date_parsed.date.months_between(VALUATION_DATE)

    af = af.projection.set(schedule=schedule)
    af.projection_date = af.projection.period_dates()

    # projection.set() has already stamped af.month -- elapsed whole months
    # from the valuation date, 0, 1, 2, ... one per projection period.

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =====================================================================
    # SECTION 3: MORTALITY RATES (typed version)
    # =====================================================================
    # NEW (typed variant): MortalityTable.at() replaces the manual
    # clip -> lookup pattern from the untyped step 02.
    #
    # 1. Choose mortality table based on sex (male or female table)
    # 2. MortalityTable.at() handles the 3-dimensional lookup internally:
    #    - age=af.age: attained age lookup key
    #    - duration=af.duration: automatically clamped at select_period=24
    #    - table_id=af.mort_table_id: extra dimension passed through **other
    # 3. Apply mortality scalar by duration (calibration to product experience)
    # 4. Convert annual to monthly

    # Select table based on sex
    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    # MortalityTable.at(): convention-aware lookup with internal duration clamping.
    # select_period=24 means duration > 24 -> 24, the same rule the untyped step
    # writes out as when(duration > 24).then(24).otherwise(duration).
    # No manual af.duration_capped column needed.
    af.base_mort_rate = mortality.at(
        age=af.age,
        duration=af.duration,
        table_id=af.mort_table_id,
    )

    # Mortality scalar by duration (calibration adjustment)
    af.scalar_duration_capped = (
        when(af.duration > SCALAR_DURATION_CAP)
        .then(SCALAR_DURATION_CAP)
        .otherwise(af.duration)
    )
    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.scalar_duration_capped,
    )

    # Final mortality rate = base rate x scalar
    af.mort_rate = af.base_mort_rate * af.mort_scalar

    # Convert annual to monthly: q_mth = 1 - (1 - q_ann)^(1/12)
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
    # Cumulative survival from the combined decrement:
    #   tpx[t] = (1 - q[0]) * (1 - q[1]) * ... * (1 - q[t-1])
    # rate_timing="beginning_of_period" is the default, and it is the
    # convention wanted here: the decrement at t has not been applied yet,
    # so the first element is 1.0 -- every policy in force at t=0.
    af.survival_prob = af.combined_decrement.projection.cumulative_survival()

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

    # Curve-based discount factors (same as typed base and step 01), read
    # through the recorded door: curve.discount_factor() on the tracked
    # af.t_years column, so the artifact names the curve these liabilities
    # were discounted on (*Audit by default*).
    af.t_years = af.projection.t_years()
    af.disc_factors = curve.discount_factor(af.t_years)

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
