# Scenario Support Design

## Overview

Add scenario support to the appliedlife model, demonstrating two approaches:
1. **Explicit scenario files** - Using pre-built BASE/UP/DOWN interest rate scenarios
2. **Dynamic shocks** - Creating scenarios programmatically for ad-hoc analysis

## Deliverables

| File | Action | Purpose |
|------|--------|---------|
| `model_applied_life.py` | Modify (2 lines) | Scenario-ready discount lookup |
| `model_scenarios.py` | Create | Explicit scenarios example (BASE/UP/DOWN) |
| `dynamic_scenarios.py` | Create | Dynamic shocks example (3 progressive examples) |
| `SCENARIOS.md` | Create | Documentation explaining both approaches |
| `README.md` | Modify | Add reference to SCENARIOS.md |

## Design Decisions

### 1. File Structure

Two separate example scripts that demonstrate each approach clearly:
- `model_scenarios.py` - explicit scenario files
- `dynamic_scenarios.py` - dynamic shocks

The base model (`model_applied_life.py`) remains the reconciled reference, with a small change to make it scenario-ready.

### 2. Scenario-Ready Base Model (Option 1b)

Make `model_applied_life.py` check if `scenario_id` column exists and use it, otherwise default to BASE:

```python
# Current (hard-coded)
af.disc_rate = risk_free_rates.lookup(
    scenario=pl.lit("BASE"),
    currency=pl.lit("USD"),
    year=af.year
)

# New (scenario-ready)
scenario_col = af.scenario_id if "scenario_id" in af.columns else pl.lit("BASE")
af.disc_rate = risk_free_rates.lookup(
    scenario=scenario_col,
    currency=pl.lit("USD"),
    year=af.year
)
```

**Benefits:**
- Base model still works standalone (defaults to BASE)
- Reconciliation still passes
- Zero code changes needed to add scenarios when wrapped with `with_scenarios()`

### 3. Explicit Scenarios (`model_scenarios.py`)

Demonstrates running the model across BASE/UP/DOWN interest rate scenarios using pre-built assumption files.

```python
"""
Explicit Scenario Example: Interest Rate Sensitivity (BASE/UP/DOWN)
"""
from gaspatchio_core import ActuarialFrame, with_scenarios
import polars as pl

from appliedlife.model_applied_life import main as run_model

def main():
    # 1. Load model points
    af = ActuarialFrame(pl.read_parquet("appliedlife/model_points.parquet"))

    # 2. Expand across scenarios (8 policies × 3 scenarios = 24 rows)
    af = with_scenarios(af, ["BASE", "UP", "DOWN"])

    # 3. Run model (unchanged - picks up scenario_id automatically)
    result = run_model(af)

    # 4. Aggregate by scenario
    summary = result.collect().group_by("scenario_id").agg([
        pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
    ])

    print(summary)
```

**Key point:** The model code is identical - we just add `with_scenarios()` before calling it.

### 4. Dynamic Shocks (`dynamic_scenarios.py`)

Three progressive examples answering genuine actuarial questions about fund return sensitivity:

#### Example 1: Single Point-in-Time Shock (Basic)
**Question:** "What if markets crash 30% in month 1?"

```python
shock = AdditiveShock(delta=-0.30, table="scenario_returns", column="t=0")
```

#### Example 2: Sustained Stress (Intermediate)
**Question:** "What if returns are 20% lower for the whole projection?"

```python
shock = MultiplicativeShock(factor=0.8, table="scenario_returns")
```

#### Example 3: Sensitivity Sweep (Advanced)
**Question:** "Show me PV across a range of return assumptions"

```python
scenarios = sensitivity_analysis(
    table="scenario_returns",
    shock_type="multiplicative",
    values=[0.7, 0.8, 0.9, 1.0, 1.1, 1.2],  # -30% to +20%
    include_base=True,
)
```

### 5. Documentation (`SCENARIOS.md`)

Structure:
1. **Overview** - What scenarios are and why they matter for GMDB/GMAB
2. **Quick Start** - Running both examples
3. **Approach 1: Explicit Scenario Files** - When to use, how it works, adding your own
4. **Approach 2: Dynamic Shocks** - Three progressive examples with explanations
5. **Making Models Scenario-Ready** - The pattern for new models
6. **Output Interpretation** - Reading results, calculating risk metrics

## Existing Data

Already available in `appliedlife/assumptions/`:
- `risk_free_rates.parquet` - Has BASE/UP/DOWN scenarios for interest rates
- `scenario_returns.parquet` - Single scenario fund returns (will be shocked dynamically)

## Verification

After implementation:
1. `verify_reconciliation.py` still passes (base model unchanged behavior)
2. `model_scenarios.py` produces results for 3 scenarios
3. `dynamic_scenarios.py` produces results showing fund return sensitivity

## Why Fund Return Shocks?

Research from Asset Adequacy Analysis Practice Notes shows:
- Lapse is #1 sensitivity test (91% of actuaries)
- But interest rates already covered by explicit scenarios
- Fund returns are the **core risk** for GMDB/GMAB products
- Market crash → account value drops → guarantee becomes valuable → higher claims

This makes fund return shocks the most genuine ad-hoc question for this model.

---

**Design Date:** 2025-12-08
