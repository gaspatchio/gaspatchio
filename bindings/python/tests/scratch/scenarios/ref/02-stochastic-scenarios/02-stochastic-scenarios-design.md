# Stochastic Scenarios Design

## Overview

Add `stochastic_scenarios.py` to demonstrate full Monte Carlo valuation: generate 1000 fund return scenarios using lifelib's risk-neutral method, run the model across all scenarios, and calculate risk metrics (VaR, TVaR).

## Deliverables

| File | Action | Purpose |
|------|--------|---------|
| `stochastic_scenarios.py` | Create | Monte Carlo scenario generation and valuation |
| `SCENARIOS.md` | Update | Add stochastic scenarios section |
| `output/stochastic_scenario_results.parquet` | Generated | Per-scenario PV totals |

## File Structure

```
stochastic_scenarios.py
├── generate_stochastic_returns()   # Monte Carlo scenario generation
├── run_stochastic_valuation()      # Run model across all scenarios
├── calculate_risk_metrics()        # VaR, TVaR, percentiles
├── main()                          # Orchestrate and display results
```

## Scenario Generation Algorithm

Replicate lifelib's risk-neutral approach:

```python
def generate_stochastic_returns(
    n_scenarios: int = 1000,
    n_months: int = 1200,
    seed: int = 12345
) -> pl.DataFrame:
    """
    Generate risk-neutral fund returns using lifelib's method.

    Formula per month:
        log_return = (forward_rate - 0.5 * vol²) * (1/12) + vol * √(1/12) * Z
        monthly_return = exp(log_return) - 1

    Where Z ~ N(0,1) independent across scenarios
    """
```

### Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| `n_scenarios` | 1000 | User requirement |
| `n_months` | 1200 | 100 years (matches projection horizon) |
| `seed` | 12345 | lifelib's seed for reproducibility |
| `dt` | 1/12 | Monthly timestep |
| Forward rates | By year | `risk_free_rates.parquet` (BASE scenario, USD) |
| Volatilities | By fund | `index_parameters.parquet` |

### Fund Volatilities (from lifelib)

| Fund | Volatility | Currency |
|------|------------|----------|
| FUND1 | 8% | EUR |
| FUND2 | 12% | GBP |
| FUND3 | 4% | JPY |
| FUND4 | 4% | USD |
| FUND5 | 12% | USD |
| FUND6 | 20% | USD |

### Output Format

```
scenario_id | t | FUND1 | FUND2 | FUND3 | FUND4 | FUND5 | FUND6
------------|---|-------|-------|-------|-------|-------|------
1           | 0 | 0.012 | 0.008 | ...   | ...   | ...   | 0.025
1           | 1 | -0.003| 0.015 | ...   | ...   | ...   | -0.018
...
1000        |1199| ...  | ...   | ...   | ...   | ...   | ...
```

Total rows: 1,000 scenarios × 1,200 months = 1.2M rows

## Model Execution

```python
def run_stochastic_valuation(n_scenarios: int = 1000) -> pl.DataFrame:
    """Run model across all stochastic scenarios."""

    # 1. Generate scenarios
    stochastic_returns = generate_stochastic_returns(n_scenarios)

    # 2. Load model points and expand
    mp = pl.read_parquet("model_points.parquet")
    af = ActuarialFrame(mp)
    af = with_scenarios(af, range(1, n_scenarios + 1))  # 8 × 1000 = 8000 rows

    # 3. Inject stochastic returns into assumptions

    # 4. Run model
    result = run_model(af)

    # 5. Aggregate by scenario
    return result.collect().group_by("scenario_id").agg([
        pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
        pl.col("pv_premiums").sum(),
        pl.col("pv_claims").sum(),
    ])
```

## Risk Metrics

```python
def calculate_risk_metrics(scenario_results: pl.DataFrame) -> dict:
    pv = scenario_results["total_pv_net_cf"]

    return {
        "mean": pv.mean(),
        "std": pv.std(),
        "min": pv.min(),
        "max": pv.max(),
        "var_95": pv.quantile(0.05),      # 95% VaR (5th percentile)
        "var_99": pv.quantile(0.01),      # 99% VaR
        "tvar_95": pv.filter(pv <= pv.quantile(0.05)).mean(),  # Tail VaR
        "percentiles": [1, 5, 25, 50, 75, 95, 99]
    }
```

## CLI Interface

```bash
# Run with defaults (1000 scenarios)
uv run python appliedlife/stochastic_scenarios.py

# Custom scenario count
uv run python appliedlife/stochastic_scenarios.py --scenarios 100

# Save generated returns (large file)
uv run python appliedlife/stochastic_scenarios.py --save-returns
```

## Output Files

| File | Contents |
|------|----------|
| `output/stochastic_scenario_results.parquet` | Per-scenario PV totals (1000 rows) |
| `output/stochastic_returns.parquet` | Generated returns (optional, 1.2M rows) |

## Data Flow

1. Load `index_parameters.parquet` → extract volatilities per fund
2. Load `risk_free_rates.parquet` → extract forward rates for drift
3. Generate 1000 × 1200 monthly returns per fund
4. Expand model points: 8 policies × 1000 scenarios = 8000 rows
5. Run model, aggregate by scenario
6. Calculate risk metrics, save results to parquet

---

**Design Date:** 2025-12-08
