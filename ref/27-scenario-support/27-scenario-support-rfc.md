# RFC 27: Scenario Support for Gaspatchio

**Status**: Draft
**Author**: Matt Wright
**Date**: 2025-12-05

## Summary

Add minimal framework support for running actuarial models across multiple economic scenarios in a single vectorized execution, enabling efficient risk metric calculation (CTE, VaR) without changing the core model structure.

## Motivation

### The Problem

Actuarial models need to run under multiple economic scenarios for:
- **Interest rate sensitivity** (regulatory: Solvency II, C3 Phase II)
- **Stochastic projections** (100-10,000 scenarios for CTE/VaR calculation)
- **Stress testing** (custom adverse scenarios)

Currently, users must either:
1. Run the model multiple times sequentially (inefficient - repeats fixed calculations)
2. Manually cross-join model points with scenarios and modify lookups (error-prone)

### The Opportunity

A single vectorized run across N scenarios is significantly more efficient than N sequential runs because:
- Projection timeline creation happens once
- Fixed assumption lookups (mortality, base lapse) execute once
- Polars parallelizes across the expanded row set automatically
- CPU cache stays hot (data locality)

### Design Goals

1. **Minimal framework surface** - two helpers, not a subsystem
2. **Model code largely unchanged** - only lookup calls that vary by scenario need modification
3. **Transparent operations** - "the formula IS the code" philosophy
4. **New scenarios = new data, not new code** - add scenario rows to tables, no model changes

### Design Philosophy: Scenario-Ready by Default

**Every Gaspatchio model should be scenario-aware from day one.**

This is not an upgrade path - it's the default architecture. Even a simple deterministic model includes scenario infrastructure:

```python
# A "single scenario" model is just a model with one scenario
af = gs.with_scenarios(af, ["DETERMINISTIC"])
```

**The principle:** Model code is identical whether running 1 scenario or 10,000 scenarios.

| Aspect | Scenario-Ready Pattern | Why |
|--------|------------------------|-----|
| `scenario_id` column | **Always exists** | Even with value `"DETERMINISTIC"` |
| Table dimensions | **Always include `scenario_id`** | Even if only one value in table |
| Lookups | **Always use `af.scenario_id`** | Never `pl.lit("BASE")` |
| Results | **Always have `scenario_id`** | Aggregation code works unchanged |

**What this means in practice:**

```python
# This model works with 1 scenario or 10,000 - zero code changes
def main(af: ActuarialFrame) -> ActuarialFrame:
    # Lookup uses af.scenario_id (not hardcoded)
    af.disc_rate = rates_table.lookup(
        scenario_id=af.scenario_id,
        year=af.year
    )

    # All calculations work on whatever scenarios are present
    af.pv_claims = (af.claims * af.disc_factors).list.sum()

    return af

# Running with 1 scenario
af = gs.with_scenarios(af, ["DETERMINISTIC"])
result = main(af)

# Running with 10,000 scenarios - SAME MODEL CODE
af = gs.with_scenarios(af, [str(i) for i in range(10000)])
result = main(af)
```

**Benefits:**
1. **No migration** - adding scenarios means changing one line, not refactoring the model
2. **Consistent patterns** - every model follows the same structure
3. **Testing parity** - test with 1 scenario, run with 10,000
4. **Documentation clarity** - one pattern to learn, not "basic" vs "advanced"

**The Migration Guide below is for converting legacy models that weren't built this way.**

## Proposed API

### 1. `gs.with_scenarios(af, scenario_ids)`

Expands an ActuarialFrame across scenario IDs via cross-join.

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame

# Load model points (8 policies)
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))

# Expand across scenarios
af = gs.with_scenarios(af, ["BASE", "UP", "DOWN"])

# Result: 8 × 3 = 24 rows, with scenario_id column added
# All original columns preserved
```

**Implementation** (conceptually simple):
```python
def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    categorical: bool = False,
) -> ActuarialFrame:
    """
    Expand ActuarialFrame across scenarios via cross-join.

    Args:
        af: Input ActuarialFrame
        scenario_ids: List of scenario identifiers (strings or integers)
        scenario_column: Name for the scenario ID column (default: "scenario_id")
        categorical: If True and scenario_ids are strings, use Categorical dtype
                    for better performance (default: False)

    Returns:
        ActuarialFrame with len(af) × len(scenario_ids) rows,
        original columns preserved, scenario_column added.
    """
    scenarios_df = pl.DataFrame({scenario_column: scenario_ids})
    if categorical and scenarios_df[scenario_column].dtype == pl.Utf8:
        scenarios_df = scenarios_df.with_columns(
            pl.col(scenario_column).cast(pl.Categorical)
        )
    expanded = af.collect().join(scenarios_df, how="cross")
    return ActuarialFrame(expanded)
```

**Why this design:**
- Transparent - it's just a cross-join, actuary understands what happened
- Returns ActuarialFrame - consistent with existing API
- No magic - visible row expansion

#### Scenario ID Encoding for Performance

For large scenario sets (1,000+), scenario ID encoding significantly impacts performance.

| ID Type | Memory | Join/GroupBy Speed |
|---------|--------|-------------------|
| String (`"SCEN_00001"`) | Larger | Slower |
| Categorical | ~3× smaller | Fast |
| Integer (UInt32) | ~3× smaller | Fastest |

**Recommended patterns:**

```python
# For stochastic runs: use integers (best performance)
af = gs.with_scenarios(af, list(range(1, 10001)))

# For named scenarios: use categorical encoding
af = gs.with_scenarios(af, ["BASE", "UP", "DOWN"], categorical=True)

# If you need readable labels with integer IDs:
af = gs.with_scenarios(af, list(range(1, 10001)))
# Join labels only for final reporting
scenario_labels = pl.DataFrame({
    "scenario_id": range(1, 10001),
    "label": [f"SCEN_{i:05d}" for i in range(1, 10001)],
})
```

Polars' recent categorical improvements work well with the streaming engine, so categorical encoding is a good middle ground when you need readable IDs.

> **See [Performance and Scale Guide](./27-performance-and-scale.md#scenario-id-encoding)** for detailed benchmarks.

### 2. `Table.from_scenario_files(mapping, ...)`

Class method to unify per-scenario assumption files into a single Table with scenario dimension.

```python
# When assumptions are stored as separate files per scenario
returns_table = gs.Table.from_scenario_files(
    {
        "BASE": "scenarios/BASE/returns.parquet",
        "UP": "scenarios/UP/returns.parquet",
        "DOWN": "scenarios/DOWN/returns.parquet",
    },
    scenario_column="scenario_id",
    dimensions={"t": "t", "fund_index": "fund_index"},
    value="inv_return_mth"
)

# Result: Single Table with scenario_id as a dimension
# Lookup works like any other Table
rate = returns_table.lookup(scenario_id=af.scenario_id, t=af.month, fund_index=af.fund_index)
```

**Implementation sketch:**
```python
@classmethod
def from_scenario_files(
    cls,
    scenario_files: dict[str, str | Path],
    scenario_column: str,
    dimensions: dict[str, str],
    value: str,
    name: str | None = None,
) -> "Table":
    """
    Create a Table by concatenating per-scenario files.

    Loads each file, adds scenario_column with the key, concatenates,
    and returns a Table with scenario_column as an additional dimension.

    Args:
        scenario_files: Mapping of scenario_id -> file path
        scenario_column: Name for the scenario ID column
        dimensions: Dimension mapping (excluding scenario, which is added automatically)
        value: Value column name
        name: Optional table name

    Returns:
        Table with scenario_column added to dimensions
    """
    dfs = []
    for scenario_id, path in scenario_files.items():
        df = pl.read_parquet(path)
        df = df.with_columns(pl.lit(scenario_id).alias(scenario_column))
        dfs.append(df)

    combined = pl.concat(dfs)

    all_dimensions = {scenario_column: scenario_column, **dimensions}

    return cls(
        name=name or "from_scenarios",
        source=combined,
        dimensions=all_dimensions,
        value=value,
    )
```

**Why this design:**
- Explicit file mapping - actuary sees which file is which scenario
- Returns a standard `Table` - use it like any other table
- Class method naming `from_scenario_files` follows Python's `from_*` constructor pattern
- No lazy magic - files are loaded and concatenated when called

### 3. `Table.from_scenario_template(path_template, scenario_ids, ...)` (alternative)

Convenience method when scenario files follow a naming convention.

```python
# When files follow a predictable pattern
returns_table = gs.Table.from_scenario_template(
    path_template="scenarios/{scenario_id}/returns.parquet",
    scenario_ids=["BASE", "UP", "DOWN"],
    scenario_column="scenario_id",
    dimensions={"t": "t", "fund_index": "fund_index"},
    value="inv_return_mth"
)

# Equivalent to from_scenario_files with:
# {"BASE": "scenarios/BASE/returns.parquet", "UP": "scenarios/UP/returns.parquet", ...}
```

**Implementation sketch:**
```python
@classmethod
def from_scenario_template(
    cls,
    path_template: str,
    scenario_ids: list[str],
    scenario_column: str,
    dimensions: dict[str, str],
    value: str,
    name: str | None = None,
) -> "Table":
    """
    Create a Table from scenario files matching a path template.

    Args:
        path_template: Path with {scenario_id} placeholder
        scenario_ids: List of scenario IDs to load
        scenario_column: Name for the scenario ID column
        dimensions: Dimension mapping (excluding scenario)
        value: Value column name
        name: Optional table name

    Returns:
        Table with scenario_column added to dimensions
    """
    scenario_files = {
        scenario_id: path_template.format(scenario_id=scenario_id)
        for scenario_id in scenario_ids
    }
    return cls.from_scenario_files(
        scenario_files=scenario_files,
        scenario_column=scenario_column,
        dimensions=dimensions,
        value=value,
        name=name,
    )
```

**Why this design:**
- Convenience for common case (many scenarios, consistent naming)
- Builds on `from_scenario_files` - no new concepts
- Template pattern is explicit - actuary sees the path structure
- Scenario IDs still listed explicitly - no hidden globbing

### Summary: Four ways to load scenario-varying assumptions

| Approach | When to use | Example |
|----------|-------------|---------|
| **Standard Table** | Assumptions already have scenario_id column | `risk_free_rates.parquet` with (scenario, year, currency) |
| **from_scenario_files** | Explicit mapping of scenario → file | Different files, non-uniform naming |
| **from_scenario_template** | Files follow `{scenario_id}` naming pattern | `scenarios/BASE/returns.parquet`, `scenarios/UP/returns.parquet` |
| **Ad-hoc shocks** | Exploratory analysis, LLM-generated scenarios | Shock config with `filter` and `multiply`/`add`/`set` |

## Ad-hoc Shock Specifications

### 4. Ad-hoc Shock Specifications (LLM-Friendly)

For exploratory analysis and conversational workflows, scenarios can be defined as declarative shock specifications rather than pre-generated assumption files. This enables LLMs to generate scenarios from natural language questions without modifying model code.

#### Shock Specification Format

```python
# LLM generates this from: "what if interest rates rise 50 basis points?"
scenario_config = [
    {"id": "BASE"},
    {
        "id": "RATES_UP_50BPS",
        "shocks": [{
            "table": "discount_rates",
            "add": 0.005,
        }]
    },
]

# Model code UNCHANGED - shocks applied at runtime
af = gs.with_scenarios(af, scenario_config)
result = main(af)
```

#### Shock Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `multiply` | Scale values by factor | `"multiply": 0.8` (20% reduction) |
| `add` | Add constant | `"add": 0.01` (+100bps) |
| `set` | Override to fixed value | `"set": 0.0` (zero out) |
| `replace_with` | Use values from another file | `"replace_with": "path/to/file.parquet"` |

#### Filter Syntax

Filters specify which rows in the assumption table are affected:

```python
# Simple equality
{"sex": "F"}

# Comparison operators
{"attained_age": {"gte": 65}}
{"duration": {"lte": 5}}
{"year": {"between": [2025, 2030]}}

# Multiple conditions (AND)
{"sex": "F", "attained_age": {"gte": 65}}
```

#### Composable Shocks

Multiple shocks can be combined in a single scenario:

```python
# "What if rates rise AND early-duration lapses increase due to competition?"
scenario_config = [
    {"id": "BASE"},
    {
        "id": "RATE_RISE_WITH_LAPSE_STRESS",
        "shocks": [
            {"table": "discount_rates", "add": 0.005},
            {"table": "lapse_rates", "filter": {"duration": {"lte": 3}}, "multiply": 1.25},
        ]
    },
]
```

#### Transparency and Audit

For audit trail and debugging, describe what shocks are applied:

```python
gs.describe_scenarios(scenario_config)

# Output:
# BASE: No modifications
# RATES_UP_50BPS:
#   - discount_rates + 0.005
# RATE_RISE_WITH_LAPSE_STRESS:
#   - discount_rates + 0.005
#   - lapse_rates × 1.25 where duration≤3
```

#### Two Modes, Same Model

| Mode | Use Case | Who Creates Scenarios | Audit Trail |
|------|----------|----------------------|-------------|
| **Ad-hoc shocks** | Exploration, Q&A, demos | LLM generates config | `describe_scenarios()` |
| **Explicit files** | Production, regulatory | Actuary prepares files | Version-controlled files |

The model code is identical in both modes - only the scenario specification differs.

#### Use Case: Conversational Actuarial Analysis

```python
# User asks: "What happens to our reserve if equity returns are 2% lower than base case for the first 5 years?"

# LLM generates:
scenario_config = [
    {"id": "BASE"},
    {
        "id": "EQUITY_STRESS_5Y",
        "shocks": [{
            "table": "fund_returns",
            "filter": {"year": {"lte": 5}},
            "add": -0.02,
        }]
    },
]

# Run and compare
af = gs.with_scenarios(af, scenario_config)
result = main(af)

# Aggregate results
by_scenario = result.collect().group_by("scenario_id").agg([
    pl.col("pv_guarantee_cost").sum().alias("total_guarantee_cost"),
])
# LLM presents: "With equity returns 2% lower for 5 years,
#               guarantee costs increase from X to Y, a Z% increase"
```

This workflow enables:
1. Natural language questions about model sensitivity
2. LLM generates shock specifications (no model code changes)
3. Framework applies shocks at runtime
4. Results compared and presented

#### Sensitivity Sweeps

For sensitivity analysis across a parameter range, use the `sweep` primitive instead of manually listing each scenario:

```python
# LLM generates this from: "show me sensitivity to rates from -100 to +100bps"
scenario_config = [
    {"id": "BASE"},
    {
        "sweep": {
            "id_template": "RATES_{bps:+04d}BPS",
            "table": "discount_rates",
            "add_range": {"from_bps": -100, "to_bps": 100, "step_bps": 25},
        }
    },
]

# Expands to 9 scenarios: RATES_-100BPS, RATES_-075BPS, ..., RATES_+100BPS
af = gs.with_scenarios(af, scenario_config)
```

This is equivalent to manually specifying each scenario but much more concise for parameter sweeps.

#### `sensitivity_analysis` - Analyzing Parameter Sensitivity

After running a sweep, use `sensitivity_analysis` to compute statistics across the scenarios:

```python
def sensitivity_analysis(
    df: pl.DataFrame,
    sweep_prefix: str,
    metrics: list[str],
    parameter_extractor: str | None = None,
) -> dict:
    """
    Summarize results across sweep scenarios.

    Args:
        df: DataFrame with scenario_id and metric columns (already grouped by scenario)
        sweep_prefix: Filter to scenarios starting with this prefix
        metrics: List of metric column names to summarize
        parameter_extractor: Regex to extract parameter value from scenario_id
                            Default: extracts signed integer before unit suffix

    Returns:
        Dictionary with summary statistics for each metric
    """
```

**Return structure:**

```python
{
    "parameter": "bps",  # Extracted from scenario IDs
    "scenarios_count": 9,
    "metrics": {
        "total_guarantee_cost": {
            "min": {"scenario": "RATES_+100BPS", "param": 100, "value": 1_200_000},
            "max": {"scenario": "RATES_-100BPS", "param": -100, "value": 2_800_000},
            "base": 2_000_000,  # From BASE scenario
            "mean": 2_000_000,
            "std": 534_000,
            "range": 1_600_000,
            "sensitivity_per_unit": -8_000,  # Change in metric per unit param change
        },
        "total_pv_premiums": {
            "min": {"scenario": "RATES_+100BPS", "param": 100, "value": 4_800_000},
            "max": {"scenario": "RATES_-100BPS", "param": -100, "value": 5_200_000},
            "base": 5_000_000,
            "mean": 5_000_000,
            "std": 134_000,
            "range": 400_000,
            "sensitivity_per_unit": -2_000,
        },
    },
    "data": sweep_df,  # Full DataFrame for custom analysis or plotting
}
```

#### Worked Example: Interest Rate Sensitivity Analysis

A portfolio manager asks: *"What's our exposure to interest rate movements? Show me how guarantee costs and profit margins change from -100bps to +100bps."*

**Step 1: LLM generates sweep configuration**

```python
scenario_config = [
    {"id": "BASE"},
    {
        "sweep": {
            "id_template": "RATES_{bps:+04d}BPS",
            "table": "discount_rates",
            "add_range": {"from_bps": -100, "to_bps": 100, "step_bps": 25},
        }
    },
]
```

**Step 2: Run the model (single vectorized execution)**

```python
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
af = gs.with_scenarios(af, scenario_config)  # 1000 policies × 9 scenarios = 9000 rows

result = main(af)  # All 9000 rows processed in parallel
```

**Step 3: Aggregate by scenario**

```python
by_scenario = result.collect().group_by("scenario_id").agg([
    pl.col("pv_guarantee_cost").sum().alias("total_guarantee_cost"),
    pl.col("pv_premiums").sum().alias("total_premiums"),
    pl.col("pv_claims").sum().alias("total_claims"),
    (pl.col("pv_premiums").sum() - pl.col("pv_claims").sum()).alias("profit_margin"),
])
```

| scenario_id | total_guarantee_cost | total_premiums | total_claims | profit_margin |
|-------------|---------------------|----------------|--------------|---------------|
| BASE | 2,000,000 | 5,000,000 | 3,500,000 | 1,500,000 |
| RATES_-100BPS | 2,800,000 | 5,200,000 | 3,600,000 | 1,600,000 |
| RATES_-075BPS | 2,600,000 | 5,150,000 | 3,575,000 | 1,575,000 |
| ... | ... | ... | ... | ... |
| RATES_+100BPS | 1,200,000 | 4,800,000 | 3,400,000 | 1,400,000 |

**Step 4: Summarize the sweep**

```python
summary = gs.sensitivity_analysis(
    by_scenario,
    sweep_prefix="RATES_",
    metrics=["total_guarantee_cost", "profit_margin"],
)
```

**Step 5: LLM generates narrative report**

```python
gc = summary["metrics"]["total_guarantee_cost"]
pm = summary["metrics"]["profit_margin"]

report = f"""
## Interest Rate Sensitivity Analysis

### Guarantee Costs
- **Base case**: ${gc['base']:,.0f}
- **Range**: ${gc['min']['value']:,.0f} (at {gc['min']['param']:+d}bps) to ${gc['max']['value']:,.0f} (at {gc['max']['param']:+d}bps)
- **Sensitivity**: ${abs(gc['sensitivity_per_unit']):,.0f} per basis point
- **Key insight**: Guarantee costs are {gc['range']/gc['base']*100:.0f}% higher in a -{abs(gc['max']['param'])}bps scenario

### Profit Margin
- **Base case**: ${pm['base']:,.0f}
- **Range**: ${pm['min']['value']:,.0f} to ${pm['max']['value']:,.0f}
- **Sensitivity**: ${abs(pm['sensitivity_per_unit']):,.0f} per basis point
- **Key insight**: Margins are relatively stable ({pm['range']/pm['base']*100:.0f}% variation across rate scenarios)

### Recommendation
The portfolio has significant guarantee cost sensitivity to falling rates.
Consider hedging strategies if rates drop below -{abs(gc['max']['param'])//2}bps.
"""
```

**Output:**

> ## Interest Rate Sensitivity Analysis
>
> ### Guarantee Costs
> - **Base case**: $2,000,000
> - **Range**: $1,200,000 (at +100bps) to $2,800,000 (at -100bps)
> - **Sensitivity**: $8,000 per basis point
> - **Key insight**: Guarantee costs are 80% higher in a -100bps scenario
>
> ### Profit Margin
> - **Base case**: $1,500,000
> - **Range**: $1,400,000 to $1,600,000
> - **Sensitivity**: $1,000 per basis point
> - **Key insight**: Margins are relatively stable (13% variation across rate scenarios)
>
> ### Recommendation
> The portfolio has significant guarantee cost sensitivity to falling rates.
> Consider hedging strategies if rates drop below -50bps.

## Usage Pattern

### Before (single scenario, hardcoded)

```python
def main(af: ActuarialFrame) -> ActuarialFrame:
    # Discount rate hardcoded to BASE scenario
    af.disc_rate = rates_table.lookup(
        scenario=pl.lit("BASE"),  # <-- Hardcoded
        year=af.year,
        currency=pl.lit("USD")
    )

    # ... rest of model
    return af
```

### After (multi-scenario)

```python
# === Setup (before model) ===
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
af = gs.with_scenarios(af, ["BASE", "UP", "DOWN"])

# === Model (minimal changes) ===
def main(af: ActuarialFrame) -> ActuarialFrame:
    # Discount rate now uses scenario_id from the frame
    af.disc_rate = rates_table.lookup(
        scenario_id=af.scenario_id,  # <-- Now dynamic
        year=af.year,
        currency=pl.lit("USD")
    )

    # Fixed assumptions unchanged (no scenario dimension)
    af.mort_rate = mortality_table.lookup(age=af.age, duration=af.duration)

    # ... rest of model unchanged
    return af

# === Post-processing (just Polars) ===
result = main(af)
df = result.collect()

# Aggregate by scenario
by_scenario = df.group_by("scenario_id").agg([
    pl.col("pv_net_cf").sum().alias("total_pv"),
    pl.col("pv_claims").sum().alias("total_claims"),
])

# Calculate risk metrics
import numpy as np
reserves = by_scenario.sort("total_pv", descending=True)["total_pv"].to_numpy()
cte_98 = reserves[:int(len(reserves) * 0.02)].mean()
```

### Adding New Scenarios (zero code changes)

To add a new scenario (e.g., "EXTREME_DOWN"):
1. Add rows to assumption tables with `scenario_id = "EXTREME_DOWN"`
2. Include "EXTREME_DOWN" in `with_scenarios()` call
3. No model code changes required

## Migration Guide: Converting a Non-Scenario Model

This section walks through converting an existing model to support scenarios.

### Step 1: Identify scenario-varying assumptions

Review your model and identify which assumptions should vary by scenario:

| Assumption | Varies by scenario? | Notes |
|------------|---------------------|-------|
| Discount rates | **Yes** | Interest rate sensitivity |
| Fund returns | **Yes** | Equity/investment scenarios |
| Mortality rates | Usually no | Unless testing mortality shocks |
| Lapse rates | Usually no | Base rates fixed, dynamic lapse handles ITM |
| Expenses | Sometimes | Inflation scenarios |

**Rule of thumb:** Economic/market assumptions vary; demographic assumptions usually don't.

### Step 2: Ensure assumption tables have scenario dimension

For each scenario-varying table, add `scenario_id` as a dimension:

```python
# BEFORE: Single scenario in table
# risk_free_rates.parquet: (currency, year) → forward_rate

# AFTER: Multiple scenarios in table
# risk_free_rates.parquet: (scenario_id, currency, year) → forward_rate

# If you have separate files per scenario, use:
rates_table = gs.Table.from_scenario_files(
    {"BASE": "rates_base.parquet", "UP": "rates_up.parquet", "DOWN": "rates_down.parquet"},
    scenario_column="scenario_id",
    dimensions={"currency": "currency", "year": "year"},
    value="forward_rate"
)
```

### Step 3: Update Table definitions

Add `scenario_id` to the dimensions of scenario-varying tables:

```python
# BEFORE
rates_table = gs.Table(
    source="risk_free_rates.parquet",
    dimensions={"year": "year", "currency": "currency"},
    value="forward_rate"
)

# AFTER
rates_table = gs.Table(
    source="risk_free_rates.parquet",
    dimensions={"scenario_id": "scenario", "year": "year", "currency": "currency"},
    value="forward_rate"
)
```

### Step 4: Update model lookups (minimal changes)

Find lookups that use scenario-varying tables and add `scenario_id`:

```python
# BEFORE (hardcoded scenario)
af.disc_rate = rates_table.lookup(
    scenario=pl.lit("BASE"),  # Hardcoded
    year=af.year,
    currency=pl.lit("USD")
)

# AFTER (dynamic scenario)
af.disc_rate = rates_table.lookup(
    scenario_id=af.scenario_id,  # From expanded frame
    year=af.year,
    currency=pl.lit("USD")
)
```

**Note:** Lookups for non-scenario-varying assumptions (mortality, lapse) remain unchanged.

### Step 5: Add scenario expansion to model entry point

Wrap your model execution with scenario expansion:

```python
# BEFORE
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
result = main(af)

# AFTER
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
af = gs.with_scenarios(af, ["BASE", "UP", "DOWN"])
result = main(af)
```

### Step 6: Update post-processing for scenario aggregation

Results now have `scenario_id` - aggregate accordingly:

```python
# BEFORE (single scenario)
df = result.collect()
total_pv = df["pv_net_cf"].sum()

# AFTER (multiple scenarios)
df = result.collect()
by_scenario = df.group_by("scenario_id").agg([
    pl.col("pv_net_cf").sum().alias("total_pv")
])

# Or calculate risk metrics
reserves = by_scenario.sort("total_pv", descending=True)["total_pv"].to_numpy()
var_99 = np.percentile(reserves, 99)
cte_98 = reserves[:max(1, int(len(reserves) * 0.02))].mean()
```

### Migration Checklist

- [ ] Identify which assumptions vary by scenario
- [ ] Add `scenario_id` to relevant assumption tables (or use `from_scenario_files`)
- [ ] Update Table definitions to include `scenario_id` dimension
- [ ] Update lookups: change `pl.lit("BASE")` to `af.scenario_id`
- [ ] Add `gs.with_scenarios()` before model execution
- [ ] Update post-processing to group by `scenario_id`
- [ ] Test with single scenario first (`["BASE"]`) to verify no regression
- [ ] Test with multiple scenarios

### Backwards Compatibility

A scenario-enabled model can still run single-scenario by expanding with one ID:

```python
# Run just BASE scenario (same as before, but framework-compatible)
af = gs.with_scenarios(af, ["BASE"])
result = main(af)
# Results have scenario_id column but only one value
```

This allows gradual migration - enable scenarios without breaking existing workflows.

## Large-Scale Stochastic Scenarios (10,000+)

For full stochastic projections (CTE/VaR calculations), you may need 1,000-10,000 scenarios.

> **See [Performance and Scale Guide](./27-performance-and-scale.md)** for detailed coverage of:
> - Memory estimation and budgeting
> - Polars streaming mode for bounded-memory execution
> - Explicit batching patterns for very large workloads
> - Writing and partitioning results
> - Performance benchmarks

### Scenario File Patterns

For 10K scenarios, ESG tools typically output unified files:

```python
# ESG outputs a single file with all scenarios
# fund_returns.parquet: (scenario_id, t, fund_index) → return
# 10K scenarios × 180 periods × 6 funds = 10.8M rows

returns_table = gs.Table(
    source="stochastic/fund_returns_10k.parquet",
    dimensions={"scenario_id": "scenario_id", "t": "t", "fund_index": "fund_index"},
    value="inv_return_mth"
)
```

### Example: 10K Stochastic Run with Streaming

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame
import polars as pl
import numpy as np

# === 1. Load scenarios (pre-generated by ESG) ===
scenario_ids = [str(i) for i in range(1, 10001)]

# === 2. Use lazy mode for streaming ===
af = ActuarialFrame(pl.scan_parquet("model_points.parquet"))  # LazyFrame
af = gs.with_scenarios(af, scenario_ids)

# === 3. Run model ===
result = main(af)

# === 4. Streaming aggregation (bounded memory) ===
by_scenario = (
    result
    .group_by("scenario_id")
    .agg([
        pl.col("pv_net_cf").sum().alias("total_pv"),
        pl.col("pv_claims").sum().alias("total_claims"),
    ])
    .collect(streaming=True)  # Memory-bounded execution
)

# === 5. Calculate risk metrics ===
reserves = by_scenario.sort("total_pv", descending=True)["total_pv"].to_numpy()
cte_98 = reserves[:max(1, int(len(reserves) * 0.02))].mean()

# === 6. Save results ===
by_scenario.write_parquet("results/scenario_totals.parquet")
```

### Scenario ID Helpers

```python
# Numeric range
af = gs.with_scenarios(af, scenario_range=(1, 10001))
# Equivalent to: [str(i) for i in range(1, 10001)]

# With prefix
af = gs.with_scenarios(af, scenario_range=(1, 10001), prefix="SCEN_")
# ["SCEN_0001", "SCEN_0002", ..., "SCEN_10000"]
```

## Alternatives Considered

### A. Model-level orchestration

```python
# User loops through scenarios in model code
for scenario in ["BASE", "UP", "DOWN"]:
    af_scenario = af.filter(pl.col("scenario_id") == scenario)
    result = run_projection(af_scenario, scenario)
    results.append(result)
```

**Rejected because:**
- Sequential execution loses vectorization benefits
- Puts orchestration complexity in model code
- Repeats fixed calculations N times

### B. Heavy framework abstraction

```python
# Framework handles everything
results = gs.run_scenarios(
    model=main,
    model_points="model_points.parquet",
    scenario_config="scenarios.yaml",
    output_metrics=["cte_98", "var_995"]
)
```

**Rejected because:**
- Hides what's happening - violates "formula IS the code" principle
- Opinionated about config format
- Less flexible for custom workflows
- Actuary can't audit the expansion/aggregation

### C. Scenario as a first-class ActuarialFrame concept

```python
# ActuarialFrame knows about scenarios natively
af = ActuarialFrame(data, scenarios=["BASE", "UP", "DOWN"])
af.run_all_scenarios()
```

**Rejected because:**
- Over-engineers the ActuarialFrame
- Mixes concerns (data structure vs execution pattern)
- Harder to reason about

## Open Questions for Discussion

### 1. Location of `with_scenarios`

Should it be:
- `gs.with_scenarios(af, ...)` - module-level function
- `af.with_scenarios(...)` - method on ActuarialFrame
- `af.scenario.expand(...)` - accessor pattern

**Recommendation:** Module-level function `gs.with_scenarios()` keeps ActuarialFrame focused on data operations.

### 2. Performance with large scenario counts

For 1,000+ stochastic scenarios:
- Is eager expansion (all rows in memory) the right approach?
- Should we consider lazy expansion or chunked processing?

**Initial view:** Start with eager expansion. Polars handles millions of rows efficiently. Optimize if profiling shows issues.

### 3. Scenario metadata

Should scenarios carry metadata beyond the ID?
```python
af = gs.with_scenarios(af, scenarios=[
    {"id": "BASE", "weight": 1.0, "description": "Base case"},
    {"id": "UP", "weight": 1.0, "description": "+100bps parallel shift"},
])
```

**Initial view:** Keep it simple - just IDs. Metadata can live in separate lookup tables if needed.

### 4. Validation

Should `with_scenarios` validate that scenario_ids exist in assumption tables?

**Initial view:** No - fail at lookup time with clear error message. Avoids coupling expansion to specific tables.

### 5. Integration with `gspio` CLI

Should `gspio run-model` support a `--scenarios` flag?
```bash
gspio run-model model.py data.parquet --scenarios BASE,UP,DOWN
```

**Initial view:** Nice to have, but not required for MVP. Users can handle expansion in their model's `main()` function.

## Implementation Plan

### Phase 1: Core Helpers (MVP)
1. Implement `gs.with_scenarios()` (eager and lazy modes)
2. Implement `Table.from_scenario_files()`
3. Support Polars streaming via `collect(streaming=True)` and `sink_parquet()`
4. Add tests with simple scenario expansion
5. Document in API reference

### Phase 2: Validation & Polish
1. Clear error messages when scenario_id not found in lookup
2. Performance benchmarks with 100, 1000, 10000 scenarios
3. Example model demonstrating full workflow
4. Implement shock specification parser
5. Implement runtime shock application to Table lookups
6. Add `gs.describe_scenarios()` for audit trail
7. Implement `sweep` expansion in scenario config parser
8. Implement `gs.sensitivity_analysis()` for multi-metric aggregation
9. Add `gs.batch_scenarios()` helper for explicit batching (fallback for memory-constrained environments)

### Phase 3: CLI Integration (optional)
1. `gspio run-model --scenarios` flag
2. `gspio scenario-metrics` subcommand for CTE/VaR calculation

## References

- [Performance and Scale Guide](./27-performance-and-scale.md) - Streaming, batching, and memory management
- [Actuarial Scenario Modeling Primer](./27-scenario-primer.md) - Background research on scenario patterns
- [Gaspatchio API Philosophy](../project.md) - Design principles
- [Lifelib Scenario Implementation](https://lifelib.io) - Reference implementation study
