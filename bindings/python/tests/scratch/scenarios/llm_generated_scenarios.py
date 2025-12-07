# ABOUTME: Worked example of LLM-friendly scenario config parsing.
# ABOUTME: Shows LLM-generated scenarios from natural language, no Python needed.
# ruff: noqa: INP001, T201, PLR0915, PGH003

"""
LLM-Generated Scenario Analysis.

This example demonstrates how an LLM can generate scenario configurations
from natural language questions WITHOUT writing Python code.

The workflow:
1. User asks: "What if mortality increases 20% and lapse drops 10%?"
2. LLM generates a JSON/dict config
3. Framework parses and applies the shocks
4. Results are compared and presented

Run with:
    cd tests/scratch/scenarios
    uv run python llm_generated_scenarios.py
"""

import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import describe_scenarios
from gaspatchio_core.scenarios._config import parse_scenario_config

# =============================================================================
# STEP 1: LLM GENERATES THIS CONFIG FROM NATURAL LANGUAGE
# =============================================================================
# User asks: "What if mortality increases 20%, lapse drops 10%,
#            and what about a flat 5% discount rate?"
#
# LLM generates this JSON-serializable config:

LLM_GENERATED_CONFIG = [
    # Base case - no shocks
    {"id": "BASE"},
    # Single shock scenarios
    {
        "id": "MORT_UP_20",
        "shocks": [{"table": "mortality", "multiply": 1.2}],
    },
    {
        "id": "LAPSE_DOWN_10",
        "shocks": [{"table": "lapse", "multiply": 0.9}],
    },
    {
        "id": "DISC_FLAT_5PCT",
        "shocks": [{"table": "disc_rates", "set": 0.05}],
    },
    # Combined adverse scenario
    {
        "id": "ADVERSE",
        "shocks": [
            {"table": "mortality", "multiply": 1.2},
            {"table": "lapse", "multiply": 0.9},
            {"table": "disc_rates", "add": 0.01},
        ],
    },
]


def setup_base_assumptions(base_path: Path) -> tuple[Table, Table, Table]:
    """Load base assumption tables (pre-shock)."""
    premium_table = Table(
        name="premium_rates",
        source=base_path / "premium_table.parquet",
        dimensions={"age_at_entry": "age_at_entry", "policy_term": "policy_term"},
        value="premium_rate",
    )

    # Base mortality table - will be shocked
    mort_table = Table(
        name="mortality",
        source=base_path / "mort_table.parquet",
        dimensions={"age": "age", "duration": "duration"},
        value="mort_rate",
    )

    # Base discount rates - will be shocked
    disc_table = Table(
        name="disc_rates",
        source=base_path / "disc_rate_ann.parquet",
        dimensions={"year": "year"},
        value="disc_rate_ann",
    )

    return premium_table, mort_table, disc_table


def apply_shocks_to_table(
    base_table: Table,
    shocks: list,  # list of Shock objects
) -> Table:
    """Apply a list of shocks to a base table, returning shocked table."""
    if not shocks:
        return base_table

    table = base_table
    for shock in shocks:
        table = table.with_shock(shock)
    return table


def run_single_scenario(  # noqa: PLR0913
    af: ActuarialFrame,
    scenario_id: str,
    shocks_for_scenario: list,
    val_date: datetime.date,
    premium_table: Table,
    base_mort_table: Table,
    base_disc_table: Table,
) -> pl.DataFrame:
    """Run projection for a single scenario with its shocks applied."""
    # Filter shocks by target table
    mort_shocks = [s for s in shocks_for_scenario if s.table == "mortality"]
    disc_shocks = [s for s in shocks_for_scenario if s.table == "disc_rates"]

    # Apply filtered shocks to assumption tables
    mort_table = apply_shocks_to_table(base_mort_table, mort_shocks)
    disc_table = apply_shocks_to_table(base_disc_table, disc_shocks)

    # Create projection timeline
    max_result = af.max()
    max_projection_length = max_result["policy_term"] * 12 - max_result["duration_mth"]

    af_proj = af.date.create_projection_timeline(
        valuation_date=val_date,
        projection_end_type="term_months",
        projection_end_value=max_projection_length,
        projection_frequency="monthly",
        output_column="projection_months",
    )

    # Time variables
    af_proj.month = (af_proj.projection_months.dt.year() - val_date.year) * 12 + (
        af_proj.projection_months.dt.month() - val_date.month
    )
    af_proj.duration_mth_t = af_proj.duration_mth + af_proj.month
    af_proj.duration = af_proj.duration_mth_t // 12
    af_proj.age = af_proj.age_at_entry + af_proj.duration

    # Mortality from shocked table
    af_proj.mort_rate = mort_table.lookup(
        age=af_proj.age.ceil(),
        duration=af_proj.duration.clip(lower_bound=0, upper_bound=5),
    )
    af_proj.mort_rate_mth = 1 - (1 - af_proj.mort_rate) ** (1 / 12)

    # Lapse (with shock support)
    lapse_base = (0.1 - 0.02 * af_proj.duration).clip(lower_bound=0.02, upper_bound=1.0)

    # Apply lapse shock if present
    lapse_shocks = [s for s in shocks_for_scenario if s.table == "lapse"]
    if lapse_shocks:
        for shock in lapse_shocks:
            lapse_base = shock.to_expression(lapse_base)

    af_proj.lapse_rate = lapse_base
    af_proj.lapse_rate_mth = 1 - (1 - af_proj.lapse_rate) ** (1 / 12)

    # Policies in force
    af_proj.combined_decrement = 1 - (
        (1 - af_proj.mort_rate_mth) * (1 - af_proj.lapse_rate_mth)
    )
    af_proj.survival_prob = af_proj.combined_decrement.projection.cumulative_survival()

    mask = (
        when(af_proj.duration_mth_t == af_proj.month)
        .then(af_proj.month.clip(lower_bound=0, upper_bound=1))
        .otherwise(1.0)
    )
    af_proj.pols_if_bef_mat = af_proj.survival_prob * af_proj.policy_count * mask
    af_proj.pols_maturity = (
        when(af_proj.duration_mth_t == af_proj.policy_term * 12)
        .then(af_proj.pols_if_bef_mat)
        .otherwise(0.0)
    )
    af_proj.pols_new_biz = (
        when(af_proj.duration_mth_t == 0).then(af_proj.policy_count).otherwise(0.0)
    )
    af_proj.pols_if = af_proj.pols_if_bef_mat
    af_proj.pols_if_bef_decr = (
        af_proj.pols_if - af_proj.pols_maturity + af_proj.pols_new_biz
    )
    af_proj.pols_death = af_proj.pols_if_bef_decr * af_proj.mort_rate_mth

    # Cashflows
    af_proj.premium_rate = premium_table.lookup(
        age_at_entry=af_proj.age_at_entry, policy_term=af_proj.policy_term
    )
    af_proj.premium_pp = (af_proj.sum_assured * af_proj.premium_rate).round(2)
    af_proj.premiums = af_proj.premium_pp * af_proj.pols_if_bef_decr
    af_proj.claims = af_proj.sum_assured * af_proj.pols_death
    af_proj.commissions = (
        when(af_proj.duration == 0).then(af_proj.premiums).otherwise(0.0)
    )

    # Expenses
    af_proj.inflation_factor = af_proj.month.finance.compound(
        rate=0.01, periods_per_year=12
    )
    af_proj.expenses = af_proj.pols_if_bef_decr * (60 / 12) * af_proj.inflation_factor

    # Discounting from shocked table
    af_proj.year_for_lookup = af_proj.month // 12
    af_proj.disc_rate_ann = disc_table.lookup(year=af_proj.year_for_lookup)
    af_proj.disc_rate_mth = af_proj.disc_rate_ann.finance.to_monthly(method="compound")

    af_proj = af_proj.finance.discount_factor(
        rate_col="disc_rate_mth",
        periods_col="month",
        output_col="disc_factors",
        method="spot",
    )

    # Present values
    af_proj.pv_premiums = (af_proj.premiums * af_proj.disc_factors).list.sum()
    af_proj.pv_claims = (af_proj.claims * af_proj.disc_factors).list.sum()
    af_proj.pv_expenses = (af_proj.expenses * af_proj.disc_factors).list.sum()
    af_proj.pv_commissions = (af_proj.commissions * af_proj.disc_factors).list.sum()
    af_proj.pv_net_cf = (
        af_proj.pv_premiums
        - af_proj.pv_claims
        - af_proj.pv_expenses
        - af_proj.pv_commissions
    )

    # Collect and add scenario ID
    result = af_proj.collect()
    return result.with_columns(pl.lit(scenario_id).alias("scenario_id"))


def main() -> pl.DataFrame:
    """Run LLM-generated scenario analysis."""
    base_path = Path(__file__).parent / "assumptions"
    val_date = datetime.date(2025, 1, 1)

    # =========================================================================
    # STEP 2: PARSE THE LLM-GENERATED CONFIG
    # =========================================================================
    logger.info("=" * 70)
    logger.info("LLM-GENERATED SCENARIO ANALYSIS")
    logger.info("=" * 70)

    print("\n[1] LLM Generated Config:")
    print("-" * 40)
    for item in LLM_GENERATED_CONFIG:
        if isinstance(item, str):
            print(f"  - {item}: (no shocks)")
        else:
            shocks = item.get("shocks", [])
            print(f"  - {item['id']}: {len(shocks)} shock(s)")
            for shock_cfg in shocks:
                shock_dict: dict = shock_cfg  # type: ignore[assignment]
                op = next(k for k in ["multiply", "add", "set"] if k in shock_dict)
                print(f"      {shock_dict['table']} {op} {shock_dict[op]}")

    # Parse config into Shock objects
    scenarios = parse_scenario_config(LLM_GENERATED_CONFIG)

    # =========================================================================
    # STEP 3: DESCRIBE FOR AUDIT TRAIL
    # =========================================================================
    print("\n[2] Parsed Scenario Description (Audit Trail):")
    print("-" * 40)
    print(describe_scenarios(scenarios, output_format="text"))

    # =========================================================================
    # STEP 4: LOAD BASE ASSUMPTIONS
    # =========================================================================
    premium_table, base_mort_table, base_disc_table = setup_base_assumptions(base_path)

    # =========================================================================
    # STEP 5: RUN EACH SCENARIO
    # =========================================================================
    model_points = pl.read_parquet(base_path / "model_point_table.parquet").head(10)
    logger.info(f"Running {len(scenarios)} scenarios with {len(model_points)} policies")

    all_results = []
    for scenario_id, shocks in scenarios.items():
        logger.info(f"  Running scenario: {scenario_id} ({len(shocks)} shocks)")
        af = ActuarialFrame(model_points)
        result = run_single_scenario(
            af,
            scenario_id,
            shocks,
            val_date,
            premium_table,
            base_mort_table,
            base_disc_table,
        )
        all_results.append(result)

    # Combine all scenario results
    combined = pl.concat(all_results)

    # =========================================================================
    # STEP 6: AGGREGATE AND PRESENT RESULTS
    # =========================================================================
    summary = (
        combined.group_by("scenario_id")
        .agg(
            [
                pl.col("pv_premiums").sum().alias("total_pv_premiums"),
                pl.col("pv_claims").sum().alias("total_pv_claims"),
                pl.col("pv_expenses").sum().alias("total_pv_expenses"),
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
            ]
        )
        .sort("scenario_id")
    )

    print("\n[3] Scenario Results Summary:")
    print("-" * 40)
    print(summary)

    # Impact analysis
    base_pv = summary.filter(pl.col("scenario_id") == "BASE")["total_pv_net_cf"].item()

    print("\n[4] Impact Analysis vs BASE:")
    print("-" * 40)
    print(f"{'Scenario':<15} {'PV Net CF':>15} {'Diff':>12} {'% Change':>10}")
    print("-" * 52)

    for row in summary.iter_rows(named=True):
        scenario = row["scenario_id"]
        pv = row["total_pv_net_cf"]
        diff = pv - base_pv
        pct = (diff / abs(base_pv)) * 100 if base_pv != 0 else 0
        print(f"{scenario:<15} {pv:>15,.2f} {diff:>+12,.2f} {pct:>+9.2f}%")

    print("-" * 52)

    # =========================================================================
    # STEP 7: LLM CAN NOW PRESENT FINDINGS
    # =========================================================================
    print("\n" + "=" * 70)
    print("LLM SUMMARY (what the LLM would tell the user):")
    print("=" * 70)

    # Find most impactful scenario
    impacts = [
        (row["scenario_id"], row["total_pv_net_cf"] - base_pv)
        for row in summary.iter_rows(named=True)
        if row["scenario_id"] != "BASE"
    ]

    most_negative = min(impacts, key=lambda x: x[1])
    most_positive = max(impacts, key=lambda x: x[1])

    print(f"""
Based on your scenario analysis:

- The ADVERSE scenario (mortality +20%, lapse -10%, rates +100bps) has
  the most negative impact: {most_negative[1]:,.2f} reduction in PV.

- The {most_positive[0]} scenario shows the most positive impact:
  {most_positive[1]:+,.2f} change in PV.

- A 20% increase in mortality alone (MORT_UP_20) reduces value by
  significantly more than a 10% decrease in lapse.

Key insight: Mortality risk dominates lapse risk for this portfolio.
""")

    return combined


if __name__ == "__main__":
    result = main()
