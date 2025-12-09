# ruff: noqa: INP001, T201, D400, D415, ERA001, PGH003, E501
# type: ignore
"""
Stochastic Monte Carlo Valuation.

Generate 1000 fund return scenarios using lifelib's risk-neutral method,
run the FULL model across all scenarios, and calculate risk metrics (VaR, TVaR).

This script uses model_applied_life.main() with stochastic returns, providing
full model fidelity including dynamic lapse, GMDB/GMAB guarantees, surrender
charges, expenses, and commissions.

Usage:
    # Run with defaults (100 scenarios)
    uv run python stochastic_scenarios.py

    # Custom scenario count
    uv run python stochastic_scenarios.py --scenarios 50

    # Save generated returns (large file)
    uv run python stochastic_scenarios.py --save-returns
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from model_applied_life import main as run_model

from gaspatchio_core import ActuarialFrame, with_scenarios

ASSUMPTIONS_DIR = Path(__file__).parent / "assumptions"
OUTPUT_DIR = Path(__file__).parent / "output"


def generate_stochastic_returns(
    n_scenarios: int = 100,
    n_months: int = 180,
    seed: int = 12345,
) -> pl.DataFrame:
    """
    Generate risk-neutral fund returns using lifelib's method.

    Formula per month:
        log_return = (forward_rate - 0.5 * vol^2) * dt + vol * sqrt(dt) * Z
        monthly_return = exp(log_return) - 1

    Where Z ~ N(0,1) independent across scenarios.

    Args:
        n_scenarios: Number of stochastic scenarios to generate
        n_months: Number of monthly projection periods
        seed: Random seed for reproducibility (lifelib uses 12345)

    Returns:
        DataFrame with columns: scenario_id, t, FUND1, ..., FUND6

    """
    print(f"Generating {n_scenarios} stochastic scenarios...")
    print(f"  Seed: {seed}")
    print(f"  Months: {n_months}")

    # Load volatilities from index_parameters
    index_params = pl.read_parquet(ASSUMPTIONS_DIR / "index_parameters.parquet")
    funds = index_params["fund_index"].to_list()
    vols = {
        row["fund_index"]: row["volatility"]
        for row in index_params.iter_rows(named=True)
    }

    print(f"  Funds: {', '.join(f'{f} ({vols[f] * 100:.0f}% vol)' for f in funds)}")

    # Load forward rates (BASE scenario, USD - simplification)
    risk_free_df = pl.read_parquet(ASSUMPTIONS_DIR / "risk_free_rates.parquet")
    rf_usd = risk_free_df.filter(
        (pl.col("scenario") == "BASE") & (pl.col("currency") == "USD")
    ).sort("year")

    # Create forward rate lookup by year
    rf_by_year = {
        row["year"]: row["forward_rate"] for row in rf_usd.iter_rows(named=True)
    }
    max_year = max(rf_by_year.keys())

    # Set random seed
    rng = np.random.default_rng(seed)

    # Generate returns efficiently using vectorized operations
    dt = 1 / 12  # Monthly timestep
    sqrt_dt = np.sqrt(dt)

    # Pre-generate all random numbers at once
    # Shape: (n_scenarios, n_months, n_funds)
    z = rng.standard_normal((n_scenarios, n_months, len(funds)))

    # Build year array for forward rate lookup
    years = np.minimum(np.arange(n_months) // 12, max_year)
    rf_array = np.array([rf_by_year.get(y, rf_by_year[max_year]) for y in years])

    all_data = []
    for scen_idx in range(n_scenarios):
        scen_id = scen_idx + 1
        scenario_data = {
            "scenario_id": [scen_id] * n_months,
            "t": list(range(n_months)),
        }

        for fund_idx, fund in enumerate(funds):
            vol = vols[fund]
            # Risk-neutral drift: (rf - 0.5 * vol^2) * dt
            drift = (rf_array - 0.5 * vol**2) * dt
            # Volatility component: vol * sqrt(dt) * Z
            diffusion = vol * sqrt_dt * z[scen_idx, :, fund_idx]
            # Log return -> simple return
            log_returns = drift + diffusion
            simple_returns = np.exp(log_returns) - 1
            scenario_data[fund] = simple_returns.tolist()

        all_data.append(pl.DataFrame(scenario_data))

        # Progress indicator
        if scen_id % 100 == 0:
            print(f"  Generated {scen_id}/{n_scenarios} scenarios...")

    # Combine all scenarios
    result = pl.concat(all_data)
    print(f"  Total rows: {len(result):,}")

    return result


def run_stochastic_valuation(
    n_scenarios: int = 100,
    seed: int = 12345,
    model_points_path: Path | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Run the FULL model across all stochastic scenarios.

    Uses model_applied_life.main() with stochastic returns, providing
    full model fidelity including:
    - Select/ultimate mortality with scalars
    - Dynamic lapse based on ITM ratio
    - GMDB/GMAB guarantees
    - Surrender charges
    - Expenses with inflation
    - Commissions

    Args:
        n_scenarios: Number of scenarios to run
        seed: Random seed for scenario generation
        model_points_path: Path to model points file (default: model_points.parquet)

    Returns:
        Tuple of (scenario_results, stochastic_returns)

    """
    # Generate stochastic returns (180 months to match model projection)
    stochastic_returns = generate_stochastic_returns(
        n_scenarios=n_scenarios,
        n_months=180,  # Match model's projection length
        seed=seed,
    )

    # Load model points
    mp_path = model_points_path or (Path(__file__).parent / "model_points.parquet")
    mp = pl.read_parquet(mp_path)
    n_policies = len(mp)

    total_rows = n_policies * n_scenarios
    print(
        f"\nRunning FULL model: {n_policies} policies x {n_scenarios} scenarios = {total_rows:,} rows..."
    )

    # Create ActuarialFrame and expand with scenarios
    af = ActuarialFrame(mp)
    af = with_scenarios(af, list(range(1, n_scenarios + 1)))

    # Run the full model with stochastic returns
    start_time = time.time()
    result_af = run_model(af, scenario_returns_override=stochastic_returns)
    elapsed = time.time() - start_time
    print(f"  Model completed in {elapsed:.1f}s")

    # Aggregate results by scenario
    # Collect and select only the columns we need for aggregation
    print("Aggregating results by scenario...")
    pv_columns = [
        "scenario_id",
        "pv_premiums",
        "pv_claims",
        "pv_claims_death",
        "pv_claims_lapse",
        "pv_claims_maturity",
        "pv_expenses",
        "pv_commissions",
        "pv_inv_income",
        "pv_av_change",
        "pv_net_cf",
    ]
    result_df = result_af.collect().select(pv_columns)

    # Aggregate by scenario using lazy evaluation for efficiency
    scenario_results = (
        result_df.lazy()
        .group_by("scenario_id")
        .agg(
            [
                pl.col("pv_premiums").sum().alias("total_pv_premiums"),
                pl.col("pv_claims").sum().alias("total_pv_claims"),
                pl.col("pv_claims_death").sum().alias("total_pv_claims_death"),
                pl.col("pv_claims_lapse").sum().alias("total_pv_claims_lapse"),
                pl.col("pv_claims_maturity").sum().alias("total_pv_claims_maturity"),
                pl.col("pv_expenses").sum().alias("total_pv_expenses"),
                pl.col("pv_commissions").sum().alias("total_pv_commissions"),
                pl.col("pv_inv_income").sum().alias("total_pv_inv_income"),
                pl.col("pv_av_change").sum().alias("total_pv_av_change"),
                pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
            ]
        )
        .sort("scenario_id")
        .collect()
    )

    return scenario_results, stochastic_returns


def calculate_risk_metrics(scenario_results: pl.DataFrame) -> dict:
    """
    Calculate VaR, TVaR, and distribution statistics.

    Args:
        scenario_results: DataFrame with scenario-level PV totals

    Returns:
        Dictionary of risk metrics

    """
    pv = scenario_results["total_pv_net_cf"]

    var_95_value = pv.quantile(0.05)
    var_99_value = pv.quantile(0.01)

    return {
        "mean": pv.mean(),
        "std": pv.std(),
        "min": pv.min(),
        "max": pv.max(),
        "var_95": var_95_value,
        "var_99": var_99_value,
        "tvar_95": pv.filter(pv <= var_95_value).mean(),
        "percentiles": {
            "p1": pv.quantile(0.01),
            "p5": pv.quantile(0.05),
            "p25": pv.quantile(0.25),
            "p50": pv.quantile(0.50),
            "p75": pv.quantile(0.75),
            "p95": pv.quantile(0.95),
            "p99": pv.quantile(0.99),
        },
    }


def format_currency(value: float) -> str:
    """Format a value as currency."""
    if value is None:
        return "N/A"
    return f"${value:,.0f}"


def main():
    """Run stochastic Monte Carlo valuation."""
    parser = argparse.ArgumentParser(
        description="Stochastic Monte Carlo Valuation (Full Model)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=100,
        help="Number of stochastic scenarios (default: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="Random seed for reproducibility (default: 12345, same as lifelib)",
    )
    parser.add_argument(
        "--save-returns",
        action="store_true",
        help="Save generated returns to parquet (large file)",
    )
    parser.add_argument(
        "--model-points",
        type=str,
        default=None,
        help="Path to model points file (default: model_points.parquet)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("STOCHASTIC MONTE CARLO VALUATION (FULL MODEL)")
    print("=" * 80)

    # Run valuation
    mp_path = Path(args.model_points) if args.model_points else None
    scenario_results, stochastic_returns = run_stochastic_valuation(
        n_scenarios=args.scenarios,
        seed=args.seed,
        model_points_path=mp_path,
    )

    # Calculate risk metrics
    metrics = calculate_risk_metrics(scenario_results)

    # Display results
    print("\n" + "=" * 80)
    print("RISK METRICS")
    print("=" * 80)

    print("\nDistribution of Total PV Net Cashflows:")
    print(f"  Mean:     {format_currency(metrics['mean'])}")
    print(f"  Std Dev:  {format_currency(metrics['std'])}")
    print(f"  Min:      {format_currency(metrics['min'])}")
    print(f"  Max:      {format_currency(metrics['max'])}")

    print("\nValue at Risk:")
    print(f"  VaR 95%:  {format_currency(metrics['var_95'])}")
    print(f"  VaR 99%:  {format_currency(metrics['var_99'])}")
    print(f"  TVaR 95%: {format_currency(metrics['tvar_95'])}")

    print("\nPercentiles:")
    pcts = metrics["percentiles"]
    print(f"  1%:   {format_currency(pcts['p1'])}")
    print(f"  5%:   {format_currency(pcts['p5'])}")
    print(f"  25%:  {format_currency(pcts['p25'])}")
    print(f"  50%:  {format_currency(pcts['p50'])}")
    print(f"  75%:  {format_currency(pcts['p75'])}")
    print(f"  95%:  {format_currency(pcts['p95'])}")
    print(f"  99%:  {format_currency(pcts['p99'])}")

    # Save results
    OUTPUT_DIR.mkdir(exist_ok=True)

    results_path = OUTPUT_DIR / "stochastic_scenario_results.parquet"
    scenario_results.write_parquet(results_path)
    print(f"\nResults saved to: {results_path}")

    if args.save_returns:
        returns_path = OUTPUT_DIR / "stochastic_returns.parquet"
        stochastic_returns.write_parquet(returns_path)
        print(f"Returns saved to: {returns_path}")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
