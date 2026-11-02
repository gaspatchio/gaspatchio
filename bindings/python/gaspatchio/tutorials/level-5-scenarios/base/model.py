# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 (Typed Inputs Variant): Scenario-Ready Variable Annuity Model

This is the model this level ships, built on the typed input doors.
The three structural swaps, each against the untyped pattern it replaces:

  **Swap 1 — MortalityTable** (select/ultimate, ``select_period=25``):
    The raw ``mortality_select`` Table is wrapped in
    ``MortalityTable(structure="select_ultimate", select_period=25)``.
    ``.at(age=..., duration=..., table_id=...)`` replaces the manual
    ``when(duration > 24).then(24) → lookup()`` capping pattern.

  **Swap 2 — Three Curve instances read through the recorded door**:
    Forward rates from ``risk_free_rates.parquet`` are converted to
    zero rates via ``forwards_to_zeros()`` (geometric mean of compounded
    forwards). Three ``Curve`` objects are constructed — one per scenario.
    Each is read with ``curve.discount_factor(af.t_years)`` on the tracked
    year-fraction column, and ``when/then`` on ``scenario_id`` picks the
    one that policy's row discounts on.

    Reading the curve on the frame is what puts it on the record: the
    audit artifact grows the curve's assumption entry (its knots and their
    digest), and the discount-factor node's fingerprint moves when the
    knots move even though the line of code does not. So a reviewer can
    re-hash the curve, and a quarter-over-quarter comparison can say which
    curve moved. Pre-computing the vectors in Python and handing them to
    the frame as a literal gives the same numbers with none of that
    (*Audit by default*).

    Policies have varying projection lengths (51–82 months), and the door
    needs no trimming for it: ``af.projection.t_years()`` is each policy's
    own year-fraction vector, so each row discounts on exactly the periods
    it has.

  **Swap 3 — the projection's own year fractions**:
    ``af.projection.t_years()`` replaces the manual
    ``[0.0, *accumulate(year_fractions())]`` pattern from L3-typed, and
    needs no ``Schedule`` of its own: the discounting rides the same
    per-policy grid the projection was built on rather than a second,
    separately-constructed calendar grid that has to be kept in step
    with it by hand.

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
from pathlib import Path
from typing import Literal

import polars as pl
from gaspatchio import ActuarialFrame, Curve, MortalityTable, when
from gaspatchio.assumptions import DataDimension, Table
from gaspatchio.scenarios import PeriodSum, Sum

StorageModeType = Literal["auto", "hash", "array"]

# What a total of this book means, cut the way this level cuts everything
# else: per scenario. A scenario axis is a cross-join on the model points,
# so one book of policies under three rate scenarios is three cuts of the
# same rows -- and a single portfolio total across all three would add
# BASE to UP to DOWN and report a number no scenario produced.
#
# ``.over("scenario_id")`` is what says so, and it is the same declaration
# ``run_scenarios.py`` hands to ``ScenarioRun``. It folds a frame carrying
# that column: ``model_points_scenarios.parquet`` beside this file is the
# cross-join, and a run over the plain book is refused by name rather than
# folded as though the scenarios were not there.
AGGREGATIONS = (
    Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
    PeriodSum("net_cf").alias("net_cf").over("scenario_id"),
)


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


def forwards_to_zeros(forwards: list[float]) -> list[float]:
    """Convert annual forward rates to annually-compounded zero rates.

    Args:
        forwards: Annual forward rate for each consecutive year from the
            valuation date. ``forwards[i]`` is the rate from year ``i`` to
            year ``i + 1``.

    Returns:
        List of zero rates where ``zeros[i]`` is the zero rate at tenor
        ``i + 1``.  Formula: ``zero[T] = (prod(1+f[0..T]))^(1/T) - 1``.

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
    # so that MortalityTable.at() dispatches through table.lookup(age=...).
    # select_ultimate clamps duration at select_period, so the source table
    # must carry the ultimate rates as duration == SELECT_PERIOD_LEN rows —
    # the select parquet alone stops at duration 24, and any projection past
    # the select period would look up a key that does not exist. The ultimate
    # rates ship alongside in mortality_ultimate.parquet; merge them in as
    # the clamp row (the table must cover every attained age and duration
    # the projection reaches).
    select_df = pl.read_parquet(ASSUMPTIONS_DIR / "mortality_select.parquet")
    ultimate_df = (
        pl.read_parquet(ASSUMPTIONS_DIR / "mortality_ultimate.parquet")
        .with_columns(pl.lit(SELECT_PERIOD_LEN, dtype=pl.Int64).alias("duration"))
        .select(select_df.columns)
    )
    mortality_select_raw = Table(
        name="mortality_select",
        source=pl.concat([select_df, ultimate_df]),
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

        # forwards_to_zeros: zeros[i] is the zero rate at tenor (scen_years[i]+1),
        # since scen_years runs 0, 1, 2, ... with one forward rate per year
        scen_zeros = forwards_to_zeros(scen_forwards)

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
    projection_months: int = PROJECTION_MONTHS,
) -> ActuarialFrame:
    """Main model projection (typed-inputs version).

    Identical cashflow logic to ``level-5-scenarios/base/model.py``.
    Differs only in Sections 2 (mortality lookup), 16 (discount factors).

    This is the model as reconciled, and a scenario plan runs it unchanged:
    ``plan.run(af, model.main)``. A plan's shock names a table this function
    builds -- ``table="mortality_select"`` -- and the plan answers this
    function's own read of it per scenario, so nothing here takes a shocked
    table, an override or a scenario guard.

    Args:
        af: ActuarialFrame with model points. Where it carries a
            ``scenario_id`` column (string "BASE", "UP", or "DOWN"), the
            discount curve is chosen per row on it.
        scenario_returns_override: Optional DataFrame of investment returns,
            keyed by ``scenario_id`` for a stochastic run.
        projection_months: Number of months to project (default 82).

    Returns:
        ActuarialFrame with projection results including ``pv_net_cf`` and
        ``pv_claims``.

    """
    # ------------------------------------------------------------------
    # Load assumptions
    # ------------------------------------------------------------------
    assumptions = load_assumptions()
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

    # The three Curve objects go to Section 16 as they are. Nothing is
    # pre-computed here: the year fractions the curves are read at come off
    # the projection built below (`af.projection.t_years()`), so there is no
    # second calendar grid to keep in step with the projection's own.

    # ------------------------------------------------------------------
    # Join product params
    # ------------------------------------------------------------------
    # The enrichment happens on the frame itself rather than on a collected
    # DataFrame that is then re-wrapped: every column arriving from a
    # parameter table comes through a door the frame records (*Audit by
    # default*).
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

    # Dynamic lapse parameters. DL001 uses U/L/M/D and DL002 uses
    # FactorCap/FactorFloor/Y/Power, so every row leaves the other formula's
    # columns empty; those neutral defaults belong to the parameter table and
    # are filled there, before it reaches the frame.
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

    # Space parameters (expense_acq, expense_maint): read from the space
    # table as the model reads any basis, so the record names the table and
    # its content and a scenario can shock it. A number pulled out with
    # .item() would sit in the record as a bare literal naming no file or row.
    expense_tables = {
        name: Table(
            name=f"space_{name}",
            source=space_params.select("space", name),
            dimensions={"space": "space"},
            value=name,
        )
        for name in ("expense_acq", "expense_maint")
    }
    af.expense_acq = expense_tables["expense_acq"].lookup(space="GMXB")
    af.expense_maint = expense_tables["expense_maint"].lookup(space="GMXB")

    # =========================================================================
    # SECTION 1: TIME SETUP
    # =========================================================================

    af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")

    # Whole calendar months from entry to the valuation date.
    af.duration_mth_init = af.entry_date_parsed.date.months_between(VALUATION_DATE)

    # Remaining term per policy: floored at zero, capped at the horizon.
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

    # Phase 1 is finished: the parameters are joined, the dates are parsed,
    # every policy knows how long it has left. Freezing here means the
    # projection below plans over settled model points instead of
    # re-deriving this setup on every collect -- and the frame is the same
    # frame afterwards, so a reader can still ask where `maint_fee_rate`
    # came from. `ActuarialFrame(af.collect())` would freeze the values and
    # throw that away; where the values genuinely have to leave the frame
    # (a numpy generator), `ActuarialFrame(df, continue_from=af)` is the
    # way back.
    af = af.materialize()

    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
        per_policy=True,
    )
    af.projection_date = af.projection.period_dates()

    # projection.set() has already stamped af.month -- elapsed whole months
    # from the valuation date, down each policy's own timeline.
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

    af.lapse_duration_capped = (
        when(af.duration > LAPSE_DURATION_CAP)
        .then(LAPSE_DURATION_CAP)
        .otherwise(af.duration)
    )

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
        multiplier=af.shifted_growth,
        addend=af.prem_to_av,
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

    # DL001: 1 - M * (1/ITM - D), held between the floor L and the cap U.
    af.dl001_unbounded = 1.0 - af.M * (1.0 / af.itm - af.D)
    af.dl001_factor = (
        when(af.dl001_unbounded < af.L)
        .then(af.L)
        .otherwise(
            when(af.dl001_unbounded > af.U).then(af.U).otherwise(af.dl001_unbounded)
        )
    )

    # DL002: Y * ITM^Power, held between FactorFloor and FactorCap.
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

    af.dyn_lapse_factor = (
        when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
    )

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

    # =========================================================================
    # SECTION 8: POLICY COUNTS
    # =========================================================================

    af.combined_decrement = 1.0 - (1.0 - af.mort_rate_mth) * (1.0 - af.lapse_rate_mth)

    # tpx[t] = (1 - q[0]) * ... * (1 - q[t-1]). The default
    # rate_timing="beginning_of_period" is the convention this model needs:
    # the decrement at t is not yet applied, so the first element is 1.0.
    af.survival_prob = af.combined_decrement.projection.cumulative_survival()

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

    # =========================================================================
    # SECTION 10: LAPSE CLAIMS (with surrender charges)
    # =========================================================================

    af.claim_pp_lapse = af.av_pp_mid_mth
    af.duration_year = af.duration_mth_t // 12
    SURR_CHARGE_DURATION_CAP = 9
    af.duration_year_capped = (
        when(af.duration_year > SURR_CHARGE_DURATION_CAP)
        .then(SURR_CHARGE_DURATION_CAP)
        .otherwise(af.duration_year)
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
            when(af.av_pp_bef_prem > af.sum_assured)
            .then(af.av_pp_bef_prem)
            .otherwise(af.sum_assured)
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

    # (1 + i)^(month/12). `**` broadcasts a scalar base over a per-period
    # exponent directly, so the exp/log identity is not needed.
    af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)

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
    # Each is read on the frame — curve.discount_factor(af.t_years) — so the
    # discount factors arrive through a door the record can see: the audit
    # artifact carries the curve's own assumption entry, and the node's
    # fingerprint moves when the knots move. Pre-computing the same vectors in
    # Python and handing them over as a literal produces identical numbers that
    # the artifact can say nothing about (*Audit by default*).
    #
    # No per-policy trimming is needed. af.projection.t_years() is each policy's
    # OWN year-fraction vector (51–82 elements here, one per period it actually
    # has), so the curve is evaluated on exactly that grid and downstream list
    # arithmetic (cashflow * disc_factors) already lines up.
    #
    # Parity note: the Curve approach is mathematically correct (zero-rate
    # discounting). The untyped L5 uses an approximation (current year's forward
    # rate applied cumulatively); deviations at month 82 are ~2.3% on disc factors.
    # =========================================================================

    af.t_years = af.projection.t_years()

    # An explicit rate scenario names its curve on the model point ("BASE",
    # "UP", "DOWN"); a stochastic run indexes simulations. That distinction is
    # scenario_id's dtype -- a label however parquet dictionary-encoded it.
    if af.schema.get("scenario_id") in (pl.String, pl.Categorical, pl.Enum):
        # One curve read per rate scenario, selected per row on scenario_id.
        # Any scenario_id not in {BASE, UP, DOWN} (e.g. shock-driven scenarios
        # like "MORT_UP_20" in Step 01) falls to the BASE curve — curve
        # selection is the rate-scenario concern; table shocks are orthogonal.
        af.disc_factors = (
            when(af.scenario_id == "UP")
            .then(curves["UP"].discount_factor(af.t_years))
            .otherwise(
                when(af.scenario_id == "DOWN")
                .then(curves["DOWN"].discount_factor(af.t_years))
                .otherwise(curves["BASE"].discount_factor(af.t_years))
            )
        )
    else:
        # Integer scenario_id (stochastic) or no scenario_id column: one rate
        # scenario, so only the BASE curve is read.
        af.disc_factors = curves["BASE"].discount_factor(af.t_years)

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
    # Standalone entry point. `gspio run-model` never runs this block: it
    # builds the frame from your model-points file and calls main() directly,
    # so everything main() needs must be created inside main().
    mp = pl.read_parquet(
        MODEL_DIR.parent.parent / "level-5-scenarios" / "base" / "model_points.parquet"
    )
    af = ActuarialFrame(mp)
    result_af = main(af)
    result = result_af.collect()
    print(
        result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"])
    )
