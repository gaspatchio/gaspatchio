# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Sample actuarial model demonstrating scenario support.
# ABOUTME: Runs BasicTerm_ME across BASE, UP, DOWN discount rate scenarios.
# ruff: noqa: INP001, T201, PLR0915, PGH003

"""
BasicTerm_ME with Scenario Support.

This model demonstrates the full scenario workflow:
1. Load model points
2. Expand across scenarios with with_scenarios()
3. Load scenario-varying discount rates with Table.from_scenario_files()
4. Run projections with scenario-aware lookups
5. Aggregate results by scenario

Run with:
    cd tests/scratch/scenarios
    uv run python model_with_scenarios.py
"""

import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from gaspatchio_core import ActuarialFrame, when, with_scenarios
from gaspatchio_core.assumptions import Table


def setup_assumptions(base_path: Path) -> tuple[Table, Table, Table]:
    """Load all assumption tables."""
    # Premium table (not scenario-varying)
    premium_table = Table(
        name="premium_rates",
        source=base_path / "premium_table.parquet",
        dimensions={"age_at_entry": "age_at_entry", "policy_term": "policy_term"},
        value="premium_rate",
    )

    # Mortality table (not scenario-varying)
    mort_table = Table(
        name="mortality_std",
        source=base_path / "mort_table.parquet",
        dimensions={"age": "age", "duration": "duration"},
        value="mort_rate",
    )

    # Discount rates - SCENARIO-VARYING!
    disc_rate_table = Table.from_scenario_files(
        scenario_files={
            "BASE": base_path / "disc_rates" / "BASE.parquet",
            "UP": base_path / "disc_rates" / "UP.parquet",
            "DOWN": base_path / "disc_rates" / "DOWN.parquet",
        },
        scenario_column="scenario_id",
        dimensions={"year": "year"},
        value="disc_rate_ann",
        name="disc_rates_by_scenario",
    )

    return premium_table, mort_table, disc_rate_table


def run_projection(
    af: ActuarialFrame,
    val_date: datetime.date,
    premium_table: Table,
    mort_table: Table,
    disc_rate_table: Table,
) -> ActuarialFrame:
    """Run the actuarial projection."""
    # Create projection timeline
    max_result = af.max()
    max_projection_length = max_result["policy_term"] * 12 - max_result["duration_mth"]

    af = af.date.create_projection_timeline(
        valuation_date=val_date,
        projection_end_type="term_months",
        projection_end_value=max_projection_length,
        projection_frequency="monthly",
        output_column="projection_months",
    )

    # Time variables
    af.month = (af.projection_months.dt.year() - val_date.year) * 12 + (
        af.projection_months.dt.month() - val_date.month
    )
    af.duration_mth_t = af.duration_mth + af.month
    af.duration = af.duration_mth_t // 12
    af.age = af.age_at_entry + af.duration

    # Mortality & lapse
    af.mort_rate = mort_table.lookup(  # type: ignore[arg-type]
        age=af.age.ceil(), duration=af.duration.clip(lower_bound=0, upper_bound=5)
    )
    af.mort_rate_mth = 1 - (1 - af.mort_rate) ** (1 / 12)
    af.lapse_rate = (0.1 - 0.02 * af.duration).clip(lower_bound=0.02, upper_bound=1.0)
    af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

    # Policies in force
    af.combined_decrement = 1 - ((1 - af.mort_rate_mth) * (1 - af.lapse_rate_mth))
    af.survival_prob = af.combined_decrement.projection.cumulative_survival()

    mask = (
        when(af.duration_mth_t == af.month)
        .then(af.month.clip(lower_bound=0, upper_bound=1))
        .otherwise(1.0)
    )
    af.pols_if_bef_mat = af.survival_prob * af.policy_count * mask
    af.pols_maturity = (
        when(af.duration_mth_t == af.policy_term * 12)
        .then(af.pols_if_bef_mat)
        .otherwise(0.0)
    )
    af.pols_new_biz = when(af.duration_mth_t == 0).then(af.policy_count).otherwise(0.0)
    af.pols_if = af.pols_if_bef_mat
    af.pols_if_bef_decr = af.pols_if - af.pols_maturity + af.pols_new_biz
    af.pols_death = af.pols_if_bef_decr * af.mort_rate_mth

    # Cashflows
    af.premium_rate = premium_table.lookup(
        age_at_entry=af.age_at_entry, policy_term=af.policy_term
    )
    af.premium_pp = (af.sum_assured * af.premium_rate).round(2)
    af.premiums = af.premium_pp * af.pols_if_bef_decr
    af.claims = af.sum_assured * af.pols_death
    af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)

    # Expenses
    expense_acq = 300
    expense_maint = 60
    inflation_rate = 0.01

    af.inflation_factor = af.month.finance.compound(
        rate=inflation_rate, periods_per_year=12
    )
    af.acq_expense = expense_acq * af.pols_new_biz
    af.maint_expense = af.pols_if_bef_decr * (expense_maint / 12) * af.inflation_factor
    af.expenses = af.acq_expense + af.maint_expense
    af.net_cf = af.premiums - af.claims - af.expenses - af.commissions

    # DISCOUNTING - SCENARIO-AWARE!
    # Each row looks up its discount rate by BOTH year AND scenario_id
    af.year_for_lookup = af.month // 12
    af.disc_rate_ann_list = disc_rate_table.lookup(
        scenario_id=af.scenario_id,  # <-- THE MAGIC: each scenario gets its own rates
        year=af.year_for_lookup,
    )

    af.disc_rate_mth = af.disc_rate_ann_list.finance.to_monthly(method="compound")
    af = af.finance.discount_factor(
        rate_col="disc_rate_mth",
        periods_col="month",
        output_col="disc_factors",
        method="spot",
    )

    # Present values
    af.pv_premiums = (af.premiums * af.disc_factors).list.sum()
    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    af.pv_expenses = (af.expenses * af.disc_factors).list.sum()
    af.pv_commissions = (af.commissions * af.disc_factors).list.sum()
    af.pv_net_cf = af.pv_premiums - af.pv_claims - af.pv_expenses - af.pv_commissions

    return af


def main() -> pl.DataFrame:
    """Run the model across multiple scenarios."""
    base_path = Path(__file__).parent / "assumptions"
    val_date = datetime.date(2025, 1, 1)
    scenarios = ["BASE", "UP", "DOWN"]

    logger.info(f"Running model with scenarios: {scenarios}")

    # 1. Load model points (subset for demo)
    model_points = pl.read_parquet(base_path / "model_point_table.parquet").head(10)
    logger.info(f"Using {len(model_points)} policies for demo")

    af = ActuarialFrame(model_points)

    # 2. EXPAND ACROSS SCENARIOS (10 policies x 3 scenarios = 30 rows)
    af = with_scenarios(af, scenarios)
    logger.info(f"Expanded to {len(af.collect())} rows (policies x scenarios)")

    # 3. Load assumptions
    premium_table, mort_table, disc_rate_table = setup_assumptions(base_path)

    # 4. Run projection
    af = run_projection(af, val_date, premium_table, mort_table, disc_rate_table)

    # 5. Collect and aggregate
    result_df = af.collect()

    summary = (
        result_df.group_by("scenario_id")
        .agg(
            [
                pl.col("pv_premiums").sum().alias("total_pv_premiums"),
                pl.col("pv_claims").sum().alias("total_pv_claims"),
                pl.col("pv_expenses").sum().alias("total_pv_expenses"),
                pl.col("pv_commissions").sum().alias("total_pv_commissions"),
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
                pl.len().alias("policy_count"),
            ]
        )
        .sort("scenario_id")
    )

    # Display results
    logger.info("=" * 60)
    logger.info("SCENARIO RESULTS SUMMARY")
    logger.info("=" * 60)

    print(summary)

    # Show impact vs BASE
    base_pv = summary.filter(pl.col("scenario_id") == "BASE")["total_pv_net_cf"].item()

    print("\n" + "-" * 60)
    print("SCENARIO IMPACT vs BASE:")
    print("-" * 60)

    for row in summary.iter_rows(named=True):
        scenario = row["scenario_id"]
        pv = row["total_pv_net_cf"]
        diff = pv - base_pv
        pct = (diff / abs(base_pv)) * 100 if base_pv != 0 else 0
        print(f"  {scenario:6}: PV = {pv:>12,.2f}  ({diff:>+10,.2f} / {pct:>+6.2f}%)")

    print("-" * 60)

    return result_df


if __name__ == "__main__":
    result = main()
