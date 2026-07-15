# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 (Typed Inputs Variant): Scenario-Ready Variable Annuity Model

This is the typed-inputs version of ``level-5-scenarios/base/model.py``.
The three structural swaps vs the untyped L5:

  **Swap 1 — MortalityTable** (select/ultimate, ``select_period=25``):
    The raw ``mortality_select`` Table is wrapped in
    ``MortalityTable(structure="select_ultimate", select_period=25)``.
    ``.at(age=..., duration=..., table_id=...)`` replaces the manual
    ``duration.clip(upper_bound=24) → lookup()`` pattern.

  **Swap 2 — Three Curve instances + scenario→list join dispatch**:
    Forward rates from ``risk_free_rates.parquet`` are converted to
    zero rates via ``forwards_to_zeros()`` (geometric mean of compounded
    forwards). Three ``Curve`` objects are constructed — one per scenario.
    Per-scenario discount-factor lists are pre-computed from the Curve.

    A 3-row mapping ``{scenario_id → discount_factor_list}`` is then
    left-joined onto the frame so each row carries ONE list column —
    its own scenario's — rather than three columns broadcast to every
    row and then collapsed via ``when/then``. At 10k policies × 1200
    months this saves roughly two-thirds of the list-column memory.

    Since policies have varying projection lengths (51–82 months), the
    full-length list (83 elements, months 0..82) is trimmed per-policy
    with ``list.head(af.month.list.len())`` after the join.

  **Swap 3 — Schedule.from_calendar_grid for cumulative year fractions**:
    ``Schedule.cumulative_year_fractions()`` replaces the manual
    ``[0.0, *accumulate(year_fractions())]`` pattern from L3-typed.

Parity note:
  Numerical parity with the untyped L5 is intentionally NOT achieved.
  L5's discount factor formula uses the CURRENT year's forward rate to
  discount from t=0 (an approximation used by lifelib):

      disc_factors[t] = (1 + f[year(t)])^(-t/12)

  The typed version uses the mathematically correct zero-rate curve:

      disc_factors[t] = (product of (1+f[i]) for i in 0..year(t))^(-1)
                        * (1 + f[year(t)])^(-frac_month/12)

  At month 82, BASE scenario: L5 ≈ 0.793, Curve ≈ 0.775 (−2.3%).
  PV-level deviations are ~1.5–4% depending on policy term and scenario.
  UP/DOWN scenarios diverge further because the forward curves are more
  steeply shaped than BASE.

All section headers, comments, and output columns match the untyped L5.
"""

import datetime
import math
from pathlib import Path
from typing import Literal

import polars as pl
from gaspatchio_core import ActuarialFrame, Curve, MortalityTable, when
from gaspatchio_core.assumptions import Table
from gaspatchio_core.assumptions._dimensions import DataDimension
from gaspatchio_core.schedule import OneTwelfth, Schedule

StorageModeType = Literal["auto", "hash", "array"]


def _maybe_scenario(table: Table | MortalityTable, af: ActuarialFrame) -> dict:
    """Return ``{'scenario_id': af.scenario_id}`` only if the table is scenario-stacked.

    ScenarioRun stacks base_tables with a ``scenario_id`` dimension. Lookups
    against a stacked table must supply ``scenario_id``; lookups against a
    plain (unstacked) table must not. This helper resolves which world we're
    in by inspecting the table's dimensions.
    """
    raw = table.table if isinstance(table, MortalityTable) else table
    if "scenario_id" in raw.dimensions and "scenario_id" in af.columns:
        return {"scenario_id": af.scenario_id}
    return {}


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

VALUATION_DATE = datetime.date(2024, 1, 1)
PROJECTION_MONTHS = 82  # Maximum projection horizon in months

# Paths
MODEL_DIR = Path(__file__).parent
ASSUMPTIONS_DIR = MODEL_DIR / "assumptions"

# Assumption table caps (from lifelib)
SELECT_PERIOD_LEN = 25  # Select mortality period is 25 years (durations 0-24)
SCALAR_DURATION_CAP = 14  # Mortality scalar table has durations 0-14
LAPSE_DURATION_CAP = 14  # Lapse table has durations 0-14


# ---------------------------------------------------------------------------
# Helper: forward rates → zero rates
# ---------------------------------------------------------------------------


def forwards_to_zeros(years: list[int], forwards: list[float]) -> list[float]:
    """Convert annual forward rates to annually-compounded zero rates.

    Args:
        years: Tenor years (e.g. ``[0, 1, 2, ...]``). The index of each
            element defines the period; ``years[i]`` is the *start* of the
            ``i``-th forward period.
        forwards: Annual forward rate for each period (parallel to ``years``).
            ``forwards[i]`` is the rate from ``years[i]`` to ``years[i]+1``.

    Returns:
        List of zero rates where ``zeros[i]`` is the zero rate at tenor
        ``years[i] + 1``.  Formula: ``zero[T] = (prod(1+f[0..T]))^(1/T) - 1``.

    """
    cum = 1.0
    zeros = []
    for i, f in enumerate(forwards):
        cum *= 1.0 + f
        zeros.append(cum ** (1.0 / (i + 1)) - 1.0)
    return zeros


# ---------------------------------------------------------------------------
# Assumptions loader
# ---------------------------------------------------------------------------


def load_assumptions(storage_mode: StorageModeType = "auto") -> dict:
    """Load assumption tables and typed inputs for the model.

    Swap 1: wraps ``mortality_select`` in ``MortalityTable`` with
    ``structure="select_ultimate"`` and ``select_period=25``.

    Swap 2: reads ``risk_free_rates.parquet``, converts forward rates to
    zero rates via ``forwards_to_zeros()``, and builds three ``Curve``
    instances — one per scenario (BASE, UP, DOWN).

    Args:
        storage_mode: Storage backend for raw Table objects.

    Returns:
        Dict with keys: ``product_params``, ``mortality``,
        ``mortality_scalars``, ``lapse_rates``, ``surrender_charges``,
        ``scenario_returns``, ``dyn_lapse_params``, ``space_params``,
        ``curves`` (dict of scenario → Curve).

    """
    product_params = pl.read_parquet(ASSUMPTIONS_DIR / "product_params_gmxb.parquet")

    # Swap 1: MortalityTable wraps the raw Table.
    # DataDimension(rename_to="age") renames parquet column "attained_age" → "age"
    # so that MortalityTable._at_select_ultimate can dispatch via table.lookup(age=...).
    mortality_select_raw = Table(
        name="mortality_select",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "mortality_select.parquet"),
        dimensions={
            "table_id": "table_id",
            "age": DataDimension(column="attained_age", rename_to="age"),
            "duration": "duration",
        },
        value="mort_rate",
        storage_mode=storage_mode,
    )
    mortality = MortalityTable(
        table=mortality_select_raw,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=SELECT_PERIOD_LEN,
    )

    mortality_scalars = Table(
        name="mortality_scalars",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "mortality_scalars.parquet"),
        dimensions={
            "duration": "duration",
            "scalar_id": "scalar_id",
        },
        value="mort_scalar",
        storage_mode=storage_mode,
    )

    lapse_rates = Table(
        name="lapse_rates",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "lapse_rates.parquet"),
        dimensions={
            "duration": "duration",
            "lapse_id": "lapse_id",
        },
        value="lapse_rate",
        storage_mode=storage_mode,
    )

    surrender_charges = Table(
        name="surrender_charges",
        source=pl.read_parquet(ASSUMPTIONS_DIR / "surrender_charges.parquet"),
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

    # Swap 2: Build three Curve objects from forward rates.
    # The risk_free_rates.parquet has years 0..149 and forward_rate per year.
    # Step 1: filter to USD, split by scenario.
    # Step 2: convert forward rates to zero rates (geometric mean of compounded forwards).
    # Step 3: build Curve.from_zero_rates with tenors = years+1 (year 0 forward → tenor 1).
    rfr_df = pl.read_parquet(ASSUMPTIONS_DIR / "risk_free_rates.parquet")
    usd_df = rfr_df.filter(pl.col("currency") == "USD")

    curves: dict[str, Curve] = {}
    for scenario in ["BASE", "UP", "DOWN"]:
        scen_df = usd_df.filter(pl.col("scenario") == scenario).sort("year")
        scen_years = scen_df["year"].to_list()
        scen_forwards = scen_df["forward_rate"].to_list()

        # forwards_to_zeros: zeros[i] is the zero rate at tenor (scen_years[i]+1)
        scen_zeros = forwards_to_zeros(scen_years, scen_forwards)

        # Tenors must be strictly > 0; year 0 forward yields zero rate at tenor=1
        tenors = [y + 1 for y in scen_years]  # [1, 2, 3, ..., 150]

        curves[scenario] = Curve.from_zero_rates(
            tenors=[float(t) for t in tenors],
            rates=scen_zeros,
        )

    return {
        "product_params": product_params,
        "mortality": mortality,
        "mortality_scalars": mortality_scalars,
        "lapse_rates": lapse_rates,
        "surrender_charges": surrender_charges,
        "scenario_returns": scenario_returns_df,
        "dyn_lapse_params": dyn_lapse_params_df,
        "space_params": space_params_df,
        "curves": curves,
    }


# ---------------------------------------------------------------------------
# Main model entry point
# ---------------------------------------------------------------------------


def main(
    af: ActuarialFrame,
    scenario_returns_override: pl.DataFrame | None = None,
    assumptions_override: dict[str, object] | None = None,
    projection_months: int = PROJECTION_MONTHS,
) -> ActuarialFrame:
    """Main model projection (typed-inputs version).

    Identical cashflow logic to ``level-5-scenarios/base/model.py``.
    Differs only in Sections 2 (mortality lookup), 16 (discount factors).

    Args:
        af: ActuarialFrame with model points.  Must have a ``scenario_id``
            column (string "BASE", "UP", or "DOWN") for scenario-aware
            discount factor dispatch.
        scenario_returns_override: Optional DataFrame of investment returns.
        assumptions_override: Optional dict overriding defaults from
            ``load_assumptions()``.
        projection_months: Number of months to project (default 82).

    Returns:
        ActuarialFrame with projection results including ``pv_net_cf`` and
        ``pv_claims``.

    """
    # ------------------------------------------------------------------
    # Load assumptions (allow external overrides for scenario analysis)
    # ------------------------------------------------------------------
    assumptions = assumptions_override or load_assumptions()
    product_params = assumptions["product_params"]
    mortality = assumptions["mortality"]
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
    curves: dict[str, Curve] = assumptions["curves"]

    # ------------------------------------------------------------------
    # Swap 2 (pre-compute): Build per-scenario discount-factor lists.
    #
    # Schedule.cumulative_year_fractions() replaces the manual
    # [0.0, *accumulate(year_fractions())] idiom from L3-typed.
    # The list has PROJECTION_MONTHS+1 elements: [0, 1/12, ..., 82/12].
    #
    # curve.discount_factor(t_years) returns list[float] of length
    # projection_months + 1. The lists are NOT broadcast to every row here;
    # Section 16 joins a 3-row scenario→list mapping so each row carries
    # only its own scenario's list (vs three columns × n_rows).
    # ------------------------------------------------------------------
    schedule = Schedule.from_calendar_grid(
        start_date=VALUATION_DATE,
        n_periods=projection_months,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    t_years_list = schedule.cumulative_year_fractions()  # len = projection_months + 1

    disc_factors_base_list = curves["BASE"].discount_factor(t_years_list)
    disc_factors_up_list = curves["UP"].discount_factor(t_years_list)
    disc_factors_down_list = curves["DOWN"].discount_factor(t_years_list)

    # ------------------------------------------------------------------
    # Join product params
    # ------------------------------------------------------------------
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

    af.duration_mth_init = (VALUATION_DATE.year * 12 + VALUATION_DATE.month) - (
        af.entry_date_parsed.dt.year() * 12 + af.entry_date_parsed.dt.month()
    )

    af.remaining_term_months = (af.policy_term * 12 - af.duration_mth_init).clip(
        lower_bound=0, upper_bound=projection_months
    )

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
        per_policy=True,
    )
    af.projection_date = af.projection.period_dates()

    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )

    af.duration_mth_t = af.duration_mth_init + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # =========================================================================
    # SECTION 2: MORTALITY RATES
    # =========================================================================

    # Swap 1: MortalityTable.at() replaces the manual clip→lookup pattern.
    # select_period=25 clamps duration at 25 internally (durations 0-24 exist
    # in the table; for these model points max duration ≈ 10, so the cap is
    # never hit). Extra dimension table_id flows through **other.
    af.mort_table_id = (
        when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
    )

    af.base_mort_rate = mortality.at(
        age=af.age,
        duration=af.duration,
        table_id=af.mort_table_id,
        **_maybe_scenario(mortality, af),
    )

    af.mort_scalar = mortality_scalars.lookup(
        scalar_id=af.mort_scalar_id,
        duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
        **_maybe_scenario(mortality_scalars, af),
    )

    # Zero mort_rate at durations beyond scalar table range (lifelib off-by-one)
    af.mort_rate = (
        when((af.duration >= 0) & (af.duration <= SCALAR_DURATION_CAP))
        .then(af.mort_scalar * af.base_mort_rate)
        .otherwise(0.0)
    )

    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)

    # =========================================================================
    # SECTION 3: BASE LAPSE RATES
    # =========================================================================

    af.lapse_duration_capped = af.duration.clip(upper_bound=LAPSE_DURATION_CAP)

    af.base_lapse_rate = (
        when((af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP))
        .then(
            lapse_rates.lookup(
                lapse_id=af.lapse_id,
                duration=af.lapse_duration_capped,
                **_maybe_scenario(lapse_rates, af),
            )
        )
        .otherwise(0.0)
    )

    # =========================================================================
    # SECTION 5: INVESTMENT RETURNS
    # =========================================================================

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

    af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (
        1.0 + af.inv_return_mth
    )

    af.prem_to_av = (
        when(af.duration_mth_t == 0)
        .then(af.premium_pp * (1.0 - af.load_prem_rate))
        .otherwise(0.0)
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

    af.itm = af.av_pp_mid_mth / af.sum_assured

    af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)
    af.dl002_factor = (af.Y * af.itm**af.Power).clip(af.FactorFloor, af.FactorCap)

    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

    af.lapse_rate = (
        when((af.duration >= 0) & (af.duration <= LAPSE_DURATION_CAP))
        .then((af.dyn_lapse_factor * af.base_lapse_rate).clip(af.dyn_lapse_floor, None))
        .otherwise(0.0)
    )

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
        when((af.duration_mth_t > 0) & (af.duration_mth_t <= af.maturity_month))
        .then(af.survival_prob * af.policy_count)
        .otherwise(0.0)
    )

    af.pols_if = af.pols_if_bef_mat
    af.pols_maturity = (
        when(af.duration_mth_t == af.maturity_month)
        .then(af.pols_if_bef_mat)
        .otherwise(0.0)
    )
    af.pols_if_bef_nb = af.pols_if_bef_mat - af.pols_maturity
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)
    af.pols_if_bef_decr = af.pols_if_bef_nb + af.pols_new_biz
    af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth
    af.pols_lapse = (af.pols_if_bef_decr - af.pols_death) * af.lapse_rate_mth

    # =========================================================================
    # SECTION 9: DEATH CLAIMS
    # =========================================================================

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
                # Expected misses (null surr_charge_id) are discarded
                # by the when() guard; declare them explicitly.
                on_missing="nan",
                duration=af.duration_year_capped,
                surr_charge_id=af.surr_charge_id,
                **_maybe_scenario(surrender_charges, af),
            )
        )
        .otherwise(0.0)
    )

    af.surr_charge = af.surr_charge_rate * af.av_pp_mid_mth * af.pols_lapse
    af.claims_lapse = af.av_pp_mid_mth * af.pols_lapse - af.surr_charge

    # =========================================================================
    # SECTION 11: MATURITY CLAIMS
    # =========================================================================

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

    af.premium_pp_list = when(af.duration_mth_t == 0).then(af.premium_pp).otherwise(0.0)
    af.premiums = af.premium_pp_list * af.pols_if_bef_decr

    # =========================================================================
    # SECTION 13: EXPENSES
    # =========================================================================

    INFLATION_RATE = 0.01

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

    af.inv_income = (
        af.inv_income_pp * af.pols_if_bef_mat_next
        + 0.5 * af.inv_income_pp * (af.pols_death + af.pols_lapse)
    )

    af.claims = af.claims_death + af.claims_lapse + af.claims_maturity

    af.net_cf = (
        af.premiums
        + af.inv_income
        - af.claims
        - af.expenses
        - af.commissions
        - af.av_change
    )

    # =========================================================================
    # SECTION 16: DISCOUNT FACTORS (Swap 2 — Curve-based)
    # =========================================================================
    #
    # Three Curve objects encode the zero-rate term structure for BASE, UP, DOWN.
    # The pre-computed discount-factor lists (one per scenario, len = projection_
    # months + 1) are joined onto the frame via a 3-row scenario→list mapping so
    # each row carries ONE list column — the one matching its own scenario_id —
    # rather than three columns broadcast to every row.
    #
    # At 10k policies × 1200 months, the previous broadcast-then-when/then design
    # materialised ~288 MB of list-column data (3 lists × n_rows × 1201 × 8B);
    # the join-then-trim design here uses ~1/3 of that.
    #
    # Per-policy list length trimming:
    #   Each policy has a different projection length (51–82 months). The full
    #   discount-factor list is trimmed to match each policy's month-list length
    #   via list.head(af.month.list.len()) so downstream list arithmetic
    #   (cashflow * disc_factors) operates on matching-length lists.
    #
    # Parity note: the Curve approach is mathematically correct (zero-rate
    # discounting). The untyped L5 uses an approximation (current year's forward
    # rate applied cumulatively); deviations at month 82 are ~2.3% on disc factors.
    # =========================================================================

    scenario_dtype = mp.schema.get("scenario_id")
    is_string_scenario = "scenario_id" in af.columns and scenario_dtype in (
        pl.Utf8,
        pl.String,
    )

    if is_string_scenario:
        # Join a 3-row mapping so each row gets ONE discount-factor list, never
        # three. Materialises the prior pipeline state once before joining;
        # Section 17 forces materialisation anyway, so this is not extra work.
        disc_map = pl.DataFrame(
            {
                "scenario_id": ["BASE", "UP", "DOWN"],
                "_disc_factors_full": [
                    disc_factors_base_list,
                    disc_factors_up_list,
                    disc_factors_down_list,
                ],
            },
            schema={"scenario_id": pl.Utf8, "_disc_factors_full": pl.List(pl.Float64)},
        )
        mp_with_disc = af.collect().join(disc_map, on="scenario_id", how="left")
        af = ActuarialFrame(mp_with_disc)
        # Re-bind the joined column through the gaspatchio typed path so
        # downstream `.list.head(per_row_expr)` accepts ExpressionProxy lengths.
        # Any scenario_id not in {BASE, UP, DOWN} (e.g. shock-driven scenarios
        # like "MORT_UP_20" in Step 01) falls back to the BASE curve — curve
        # selection is the rate-scenario concern; table shocks are orthogonal.
        af.disc_factors_full = pl.col("_disc_factors_full").fill_null(
            pl.lit(
                pl.Series("_fallback", [disc_factors_base_list], dtype=pl.List(pl.Float64))
            ).first()
        )
        af.disc_factors = af.disc_factors_full.list.head(af.month.list.len())
    else:
        # Integer scenario_id (stochastic) or no scenario_id column: only one
        # discount-factor list is needed; broadcast the BASE list directly.
        af.disc_factors_full = pl.lit(
            pl.Series(
                "_disc_factors_full",
                [disc_factors_base_list],
                dtype=pl.List(pl.Float64),
            )
        ).first()
        af.disc_factors = af.disc_factors_full.list.head(af.month.list.len())

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
    mp = pl.read_parquet(
        MODEL_DIR.parent.parent / "level-5-scenarios" / "base" / "model_points.parquet"
    )
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(
        result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"])
    )
