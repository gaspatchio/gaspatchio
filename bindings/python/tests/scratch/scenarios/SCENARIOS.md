# Scenario Support

Three approaches for running scenarios in Gaspatchio:

1. **Explicit scenario files** - Pre-built assumptions with `scenario_id` dimension
2. **Dynamic shocks** - Programmatically modify assumptions at runtime
3. **Stochastic Monte Carlo** - Generate 1000+ fund return scenarios for risk metrics

---

## Background: lifelib's Scenario Architecture

The lifelib IntegratedLife model (which we reconcile against) uses two types of scenarios:

| Type | Source | Count | What varies |
|------|--------|-------|-------------|
| **Interest rate** | Deterministic curves | 3 (BASE, UP, DOWN) | Discount rates |
| **Fund returns** | Stochastic Monte Carlo | 1-1000+ | Monthly fund returns |

**How lifelib generates stochastic fund returns:**
```python
# lifelib's Scenarios space generates risk-neutral returns
scen_size = 100  # Number of stochastic paths
seed = 12345     # Fixed seed for reproducibility

# For each scenario, monthly returns are generated using:
# log_return = (forward_rate - 0.5 * vol²) * dt + vol * √dt * Z
# where Z ~ N(0,1)
```

**Our reconciliation** uses `scen_size=1` (single deterministic path). The `scenario_returns.parquet` file contains scenario #1 from lifelib's stochastic generator.

**To extend to full stochastic:**
1. Generate 100+ fund return paths (from lifelib or your own ESG)
2. Add `scenario_id` dimension to returns file
3. Use `with_scenarios(af, range(1, 101))` to expand

---

## Quick Start

```bash
# Explicit scenarios (BASE/UP/DOWN interest rates)
uv run python appliedlife/model_scenarios.py

# Dynamic shocks (assumption sensitivity)
uv run python appliedlife/dynamic_scenarios.py
uv run python appliedlife/dynamic_scenarios.py --example mortality
uv run python appliedlife/dynamic_scenarios.py --example lapse
uv run python appliedlife/dynamic_scenarios.py --example combined
uv run python appliedlife/dynamic_scenarios.py --example stress

# Stochastic Monte Carlo (full model, risk metrics)
uv run python appliedlife/stochastic_scenarios.py
uv run python appliedlife/stochastic_scenarios.py --scenarios 50     # Fewer scenarios
uv run python appliedlife/stochastic_scenarios.py --save-returns     # Save generated returns
```

---

## Approach 1: Explicit Scenario Files

Use when you have pre-built scenario files (ESG output, regulatory curves, stress tests).

### Pattern

```python
from gaspatchio_core import ActuarialFrame, with_scenarios
from appliedlife.model_applied_life import main as run_model

# Load and expand across scenarios
mp = pl.read_parquet("appliedlife/model_points.parquet")
af = ActuarialFrame(mp)
af = with_scenarios(af, ["BASE", "UP", "DOWN"])  # 8 policies × 3 scenarios = 24 rows

# Run projection
result = run_model(af)

# Aggregate by scenario
summary = result.collect().group_by("scenario_id").agg([
    pl.col("pv_premiums").sum(),
    pl.col("pv_claims").sum(),
    pl.col("pv_net_cf").sum(),
])
```

### Assumption File Format

Scenario-varying files include a `scenario_id` column:

```
# risk_free_rates.parquet
scenario | currency | year | forward_rate
---------|----------|------|-------------
BASE     | USD      | 0    | 0.0250
BASE     | USD      | 1    | 0.0275
UP       | USD      | 0    | 0.0350
DOWN     | USD      | 0    | 0.0150
```

---

## Approach 2: Declarative What-If Configs

Use for ad-hoc sensitivity analysis with simple dict/JSON configs. No Python code needed for shock definitions - just specify what to shock and how.

### Config Format

```python
config = [
    {"id": "BASE"},                                           # No shocks
    {"id": "SCENARIO_NAME", "shocks": [shock, ...]},          # With shocks
]

shock = {
    "table": "table_name",      # Required: target assumption table
    "multiply": 1.2,            # OR "add": 0.01, OR "set": 0.05
}
```

### Shock Operations

| Operation | Effect | Example | Result |
|-----------|--------|---------|--------|
| `multiply` | Scale by factor | `{"table": "mortality", "multiply": 1.2}` | `value × 1.2` |
| `add` | Add constant | `{"table": "rates", "add": 0.01}` | `value + 0.01` |
| `set` | Replace with value | `{"table": "lapse", "set": 0.0}` | `value = 0.0` |

### Example 1: Mortality Sensitivity

"What if mortality increases by 10%, 20%, or 30%?"

```python
config = [
    {"id": "BASE"},
    {"id": "MORT_UP_10", "shocks": [{"table": "mortality", "multiply": 1.1}]},
    {"id": "MORT_UP_20", "shocks": [{"table": "mortality", "multiply": 1.2}]},
    {"id": "MORT_UP_30", "shocks": [{"table": "mortality", "multiply": 1.3}]},
]
```

### Example 2: Lapse Sensitivity

"What if lapses are 50% lower or 50% higher?"

```python
config = [
    {"id": "BASE"},
    {"id": "LAPSE_DOWN_50", "shocks": [{"table": "lapse", "multiply": 0.5}]},
    {"id": "LAPSE_UP_50", "shocks": [{"table": "lapse", "multiply": 1.5}]},
]
```

### Example 3: Combined Stress Scenarios

"Show me best case, base case, and worst case"

```python
config = [
    {"id": "BEST_CASE", "shocks": [
        {"table": "mortality", "multiply": 0.9},   # 10% lower mortality
        {"table": "lapse", "multiply": 1.1},       # 10% higher lapse
    ]},
    {"id": "BASE"},
    {"id": "WORST_CASE", "shocks": [
        {"table": "mortality", "multiply": 1.2},   # 20% higher mortality
        {"table": "lapse", "multiply": 0.8},       # 20% lower lapse
    ]},
]
```

### Running What-If Analysis

```python
from gaspatchio_core.scenarios import parse_scenario_config, describe_scenarios
from gaspatchio_core import Table

# Parse config to shock objects
scenarios = parse_scenario_config(config)

# Show audit trail
description = describe_scenarios(scenarios, output_format="text")
print(description)

# Apply shocks to tables
for scenario_id, shocks in scenarios.items():
    for shock in shocks:
        if shock.table == "mortality":
            mort_table = mort_table.with_shock(shock)
```

### CLI Usage

```bash
# Run specific example
uv run python appliedlife/dynamic_scenarios.py --example mortality
uv run python appliedlife/dynamic_scenarios.py --example lapse
uv run python appliedlife/dynamic_scenarios.py --example combined
uv run python appliedlife/dynamic_scenarios.py --example stress

# Custom config from JSON
uv run python appliedlife/dynamic_scenarios.py --config '[{"id": "BASE"}, {"id": "TEST", "shocks": [{"table": "mortality", "multiply": 1.5}]}]'
```

### LLM-Friendly Design

Natural language questions map directly to configs:

| Question | Config |
|----------|--------|
| "What if mortality is 20% higher?" | `{"table": "mortality", "multiply": 1.2}` |
| "What if lapse rates drop by half?" | `{"table": "lapse", "multiply": 0.5}` |
| "What if we assume zero lapses?" | `{"table": "lapse", "set": 0.0}` |
| "What if rates increase by 100bps?" | `{"table": "disc_rates", "add": 0.01}` |

---

## Approach 3: Stochastic Monte Carlo

Use for full Monte Carlo valuation with risk metrics (VaR, TVaR).

### Overview

The `stochastic_scenarios.py` script:
1. Generates risk-neutral fund return scenarios using lifelib's method
2. Runs the **full `model_applied_life.py`** across all scenarios
3. Calculates risk metrics from the distribution of PV net cashflows

This provides full model fidelity including:
- Select/ultimate mortality with scalars
- Dynamic lapse based on ITM ratio
- GMDB/GMAB guarantees
- Surrender charges
- Expenses with inflation
- Commissions

### Scenario Generation

Fund returns are generated using the risk-neutral formula:

```python
log_return = (forward_rate - 0.5 * vol²) * dt + vol * √dt * Z
monthly_return = exp(log_return) - 1
```

Where:
- `forward_rate` = risk-free rate from `risk_free_rates.parquet`
- `vol` = fund volatility from `index_parameters.parquet`
- `dt` = 1/12 (monthly timestep)
- `Z` = standard normal random variable

### Fund Volatilities

| Fund | Volatility | Currency |
|------|------------|----------|
| FUND1 | 8% | EUR |
| FUND2 | 12% | GBP |
| FUND3 | 4% | JPY |
| FUND4 | 4% | USD |
| FUND5 | 12% | USD |
| FUND6 | 20% | USD |

### Data Sources for Stochastic Scenarios

Three assumption files drive stochastic scenario generation:

#### 1. `scenario_returns.parquet` - Deterministic Fund Returns

Single-scenario fund returns used for reconciliation (lifelib scenario #1):

```
Shape: (180, 7)
Columns: t, FUND1, FUND2, FUND3, FUND4, FUND5, FUND6

┌─────┬───────────┬──────────┬───────────┬───────────┬──────────┬───────────┐
│ t   │ FUND4     │ FUND5    │ FUND6     │ FUND1     │ FUND2    │ FUND3     │
├─────┼───────────┼──────────┼───────────┼───────────┼──────────┼───────────┤
│ 0   │ 0.000816  │ 0.000665 │ -0.039755 │ -0.030219 │ 0.046698 │ -0.009248 │
│ 1   │ -0.018567 │ 0.088273 │ 0.059847  │ -0.028964 │ 0.02464  │ 0.004944  │
│ 2   │ 0.003113  │ 0.031075 │ -0.067928 │ -0.015224 │ 0.033671 │ -0.004619 │
└─────┴───────────┴──────────┴───────────┴───────────┴──────────┴───────────┘
```

**Usage:** Default returns for deterministic runs. Not used when `scenario_returns_override` is provided.

#### 2. `index_parameters.parquet` - Fund Parameters

Volatilities and other fund characteristics for stochastic generation:

```
Shape: (6, 6)
Columns: fund_index, currency, return, volatility, risk_free, sharpe_ratio

┌────────────┬──────────┬────────┬────────────┬───────────┬──────────────┐
│ fund_index │ currency │ return │ volatility │ risk_free │ sharpe_ratio │
├────────────┼──────────┼────────┼────────────┼───────────┼──────────────┤
│ FUND1      │ EUR      │ 0.05   │ 0.08       │ 0.03      │ 0.25         │
│ FUND2      │ GBP      │ 0.06   │ 0.12       │ 0.03      │ 0.25         │
│ FUND3      │ JPY      │ 0.02   │ 0.04       │ 0.01      │ 0.25         │
│ FUND4      │ USD      │ 0.06   │ 0.04       │ 0.05      │ 0.25         │
│ FUND5      │ USD      │ 0.08   │ 0.12       │ 0.05      │ 0.25         │
│ FUND6      │ USD      │ 0.10   │ 0.20       │ 0.05      │ 0.25         │
└────────────┴──────────┴────────┴────────────┴───────────┴──────────────┘
```

**Usage:** `volatility` column feeds the risk-neutral return formula. Other columns available for real-world scenarios.

#### 3. `risk_free_rates.parquet` - Forward Rate Curves

Multi-scenario interest rate curves by currency:

```
Shape: (1800, 4)
Columns: scenario, currency, year, forward_rate

┌──────────┬──────────┬──────┬──────────────┐
│ scenario │ currency │ year │ forward_rate │
├──────────┼──────────┼──────┼──────────────┤
│ BASE     │ EUR      │ 0    │ 0.03357      │
│ BASE     │ EUR      │ 1    │ 0.02690      │
│ BASE     │ EUR      │ 2    │ 0.02439      │
│ BASE     │ USD      │ 0    │ 0.02500      │
│ UP       │ USD      │ 0    │ 0.03500      │
│ DOWN     │ USD      │ 0    │ 0.01500      │
└──────────┴──────────┴──────┴──────────────┘
```

**Usage:**
- `forward_rate` provides drift term in risk-neutral formula
- Stochastic runs use BASE scenario (variation is in fund returns)
- Explicit scenarios (UP/DOWN) vary discount rates directly

### Output

```bash
$ uv run python appliedlife/stochastic_scenarios.py --scenarios 100

================================================================================
STOCHASTIC MONTE CARLO VALUATION (FULL MODEL)
================================================================================
Generating 100 stochastic scenarios...

Running FULL model across 8 policies x 100 scenarios = 800 rows...
  Model completed in 1.2s

================================================================================
RISK METRICS
================================================================================

Distribution of Total PV Net Cashflows:
  Mean:     $-5,312,871
  Std Dev:  $13,036,782
  Min:      $-22,067,061
  Max:      $14,159,263

Value at Risk:
  VaR 95%:  $-22,067,061
  VaR 99%:  $-22,067,061
  TVaR 95%: $-22,067,061

Results saved to: appliedlife/output/stochastic_scenario_results.parquet
```

### How It Works

The model is **stochastic-ready** - it automatically detects when scenario returns include a `scenario_id` column:

```python
from gaspatchio_core import ActuarialFrame, with_scenarios
from appliedlife.model_applied_life import main as run_model

# Generate stochastic returns with scenario_id column
stochastic_returns = generate_stochastic_returns(n_scenarios=100)
# Returns: DataFrame with columns [scenario_id, t, FUND1, ..., FUND6]

# Expand model points across scenarios
mp = pl.read_parquet("appliedlife/model_points.parquet")
af = ActuarialFrame(mp)
af = with_scenarios(af, list(range(1, 101)))  # 8 policies × 100 scenarios

# Run full model with stochastic returns
result = run_model(af, scenario_returns_override=stochastic_returns)

# Aggregate by scenario
scenario_results = result.collect().group_by("scenario_id").agg([
    pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
])
```

### Key Implementation Details

The model handles two types of scenarios:

1. **Explicit scenarios** (string IDs like "BASE", "UP", "DOWN"):
   - Used for interest rate scenarios
   - Discount rates vary by scenario_id

2. **Stochastic scenarios** (integer IDs like 1, 2, 3, ...):
   - Used for fund return Monte Carlo
   - Fund returns vary by scenario_id
   - Discount rates use "BASE" (stochastic variation is in returns only)

```python
# The model auto-detects scenario type based on dtype:
if "scenario_id" in scenario_returns.columns:
    # Stochastic mode: include scenario_id in returns lookup
    inv_returns_table = Table(
        dimensions={"scenario_id": "scenario_id", "t": "t", "fund_index": "fund_index"},
        ...
    )
else:
    # Deterministic mode: no scenario_id dimension
    inv_returns_table = Table(
        dimensions={"t": "t", "fund_index": "fund_index"},
        ...
    )
```

---

## Making Models Scenario-Ready

### The Pattern

Check for `scenario_id` column, default to BASE:

```python
scenario_col = af.scenario_id if "scenario_id" in af.columns else pl.lit("BASE")

af.disc_rate = risk_free_rates.lookup(
    scenario=scenario_col,
    currency=pl.lit("USD"),
    year=af.year
)
```

This allows the model to:
- Run standalone (defaults to BASE)
- Run with `with_scenarios()` (uses scenario_id from expanded frame)

### Which Assumptions Vary by Scenario?

**Typically vary:** Discount rates, investment returns, inflation

**Typically don't vary:** Mortality, lapse (unless dynamic), product parameters

---

## Risk Metrics

```python
pv_by_scenario = result_df.group_by("scenario_id").agg(pl.col("pv_net_cf").sum())

# VaR (95%)
var_95 = pv_by_scenario["pv_net_cf"].quantile(0.05)

# TVaR / CTE (95%)
tvar_95 = pv_by_scenario.filter(pl.col("pv_net_cf") <= var_95)["pv_net_cf"].mean()

# Scenario impact vs BASE
base_pv = pv_by_scenario.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]
impact = pv_by_scenario.with_columns([
    (pl.col("pv_net_cf") - base_pv).alias("impact"),
    ((pl.col("pv_net_cf") - base_pv) / abs(base_pv) * 100).alias("impact_pct")
])
```

---

## Scaling to 1000+ Scenarios

### Batch Processing

```python
batch_size = 100
for i in range(0, len(scenarios), batch_size):
    batch = scenarios[i:i+batch_size]
    af_batch = with_scenarios(af, batch)
    result_batch = run_model(af_batch)
    result_batch.collect().write_parquet(f"results_batch_{i}.parquet")
```

### Nested Stochastic (VM-21, IFRS 17)

```python
# Outer: real-world scenarios
# Inner: risk-neutral scenarios
af["outer_scenario"] = af.scenario_id
af = with_scenarios(af, inner_scenarios)  # Creates new scenario_id
```

---

## Files

| File | Description |
|------|-------------|
| `model_applied_life.py` | Full model (stochastic-ready, reconciled with lifelib) |
| `model_scenarios.py` | Explicit scenarios example (BASE/UP/DOWN interest rates) |
| `dynamic_scenarios.py` | Declarative what-if configs for assumption shocks |
| `stochastic_scenarios.py` | Monte Carlo valuation using full model (VaR/TVaR) |
| `assumptions/risk_free_rates.parquet` | Multi-scenario discount rates |
| `assumptions/scenario_returns.parquet` | Deterministic fund returns (single scenario) |
| `assumptions/index_parameters.parquet` | Fund volatilities for stochastic generation |
| `output/stochastic_scenario_results.parquet` | Per-scenario PV totals from Monte Carlo |
