# Phase 2: Stepped Projection for Path-Dependent Products

**Status**: Draft / Design Exploration
**Authors:** Matt Wright, Claude
**Date**: 2025-12-06
**Depends on**: RFC 27 (Scenario Support)

## Summary

Add a period-stepping execution mode for actuarial models where period T calculations depend on period T-1 results. This enables modeling of unit-linked, with-profits, and variable annuity products with path-dependent guarantees.

## The Problem

### Why Vectorized Projection Breaks

Phase 1 scenario support assumes all projection periods can be calculated simultaneously using list columns:

```python
# Phase 1 pattern - works for term insurance, traditional annuities
af.pols_if = af.combined_decrement.projection.cumulative_survival()
af.claims = af.sum_assured * af.pols_death
```

This works because `cumulative_survival()` has a **closed-form solution** - we can compute all periods at once using cumulative products.

But for fund-based products, period T depends on period T-1:

```python
# This CANNOT be vectorized:
fund_value[t] = fund_value[t-1] * (1 + fund_return[t]) - charges[t]
guarantee_cost[t] = max(0, guarantee_floor - fund_value[t])  # Path-dependent!
```

The fund value at month 100 depends on the chain of 99 prior calculations. There's no closed-form - we must step through sequentially.

### Products Requiring Stepped Projection

| Product Type | Why Sequential? |
|--------------|-----------------|
| **Unit-linked** | Fund value accumulates with investment returns |
| **With-profits** | Bonus declarations depend on accumulated fund, smoothing |
| **Variable Annuities (GMAB/GMWB/GMIB)** | Guarantee value depends on account value path |
| **Universal Life** | Account value with credited interest, COI deductions |
| **Equity-indexed annuities** | Cap/floor/participation applied to accumulated value |

## Background: The With-Profits Problem

With-profits (also called "participating" policies in North America) represents perhaps the most complex case for actuarial modeling, and is a key driver for Phase 2's stepped projection design.

### What Makes With-Profits Special

With-profits policies share the insurer's investment profits with policyholders through a **bonus system**:

| Bonus Type | Description | Guaranteed? |
|------------|-------------|-------------|
| **Reversionary bonus** | Added annually to sum assured | Yes, once declared |
| **Terminal bonus** | Paid at maturity/claim | No - discretionary |
| **Interim bonus** | Pro-rata for mid-year events | Varies |

The key insight: **bonus declarations depend on the accumulated fund value**, which depends on prior bonus declarations. This creates an unavoidable sequential dependency.

### Why Vectorization Fails for With-Profits

#### 1. Asset Shares Require Sequential Accumulation

The **asset share** tracks what each policy is "worth" based on actual experience:

```python
# Asset share accumulation - CANNOT be vectorized
asset_share[t] = (
    asset_share[t-1]
    * (1 + investment_return[t])  # Scenario-dependent
    - mortality_cost[t]
    - expense_charge[t]
    + bonus_addition[t]  # Depends on asset_share[t-1]!
)
```

The asset share at year 20 depends on the chain of 19 prior calculations.

#### 2. Smoothing Creates Path Dependency

With-profits funds use **smoothing** to reduce policyholder volatility:

```python
# Smoothing mechanism (simplified)
if investment_return[t] > expected_return:
    # Good year: retain surplus in estate
    credited_return[t] = expected_return + smoothing_factor * (actual - expected)
    estate[t] = estate[t-1] + (actual - credited_return[t]) * fund_value[t-1]
else:
    # Bad year: draw from estate to maintain bonus
    estate_draw = min(estate[t-1], shortfall)
    credited_return[t] = expected_return - (shortfall - estate_draw) / fund_value[t-1]
    estate[t] = estate[t-1] - estate_draw
```

The credited return depends on the **estate balance**, which depends on all prior years' experience.

#### 3. Bonus Declarations Are Management Decisions

Unlike mortality or lapse rates, bonus rates involve **discretion**:

```python
# Simplified bonus decision logic
def declare_bonus(asset_share, guaranteed_value, estate, market_conditions):
    """
    Bonus declaration depends on:
    - Current asset shares (path-dependent)
    - Estate surplus/deficit (path-dependent)
    - Competitive positioning (market scenario)
    - Policyholder Reasonable Expectations (PRE)
    """
    supportable_bonus = (asset_share - guaranteed_value) / remaining_term

    # Can't cut bonuses arbitrarily (PRE constraint)
    minimum_bonus = previous_bonus * 0.9  # Example constraint

    # Estate must support the bonus
    if estate < 0:
        bonus = max(0, minimum_bonus)  # Reduced or zero in stressed scenarios
    else:
        bonus = min(supportable_bonus, target_bonus)

    return bonus
```

This logic **must execute period by period** because each decision depends on the cumulative state.

#### 4. Estate Dynamics Across the Book

With-profits funds often have **estate sharing** across generations of policies:

```python
# Estate affects all policies, not just individual policy
total_estate = sum(policy.asset_share - policy.guaranteed_value for policy in book)

# Bonus rates may be uniform across cohorts
if total_estate > threshold:
    bonus_rate = calculate_supportable_bonus(total_estate, total_liabilities)
else:
    bonus_rate = minimum_sustainable_rate
```

This means you can't even project policies independently - the **aggregate fund state** affects individual policy outcomes.

### With-Profits Under Stochastic Scenarios

Combining with-profits with stochastic scenarios is the ultimate test:

```
For each scenario (1 to 10,000):
    For each period (1 to 360):  # 30 years monthly
        1. Apply scenario's investment return to fund
        2. Calculate asset shares for all policies
        3. Determine estate surplus/deficit
        4. Declare bonuses (management action)
        5. Update guaranteed values
        6. Calculate decrements (dynamic lapse depends on ITM)
        7. Store results for risk metrics
```

This is **10,000 × 360 = 3.6 million** sequential period calculations, each affecting the next.

### Modeling Complexity Unique to With-Profits

| Challenge | Impact on Computation |
|-----------|----------------------|
| **Intergenerational equity** | Must track cohorts separately, but estate is shared |
| **Guaranteed Annuity Options (GAOs)** | Interest rate scenarios dramatically affect option value |
| **Policyholder Reasonable Expectations** | Constrains bonus reductions, creates asymmetry |
| **Terminal bonus calculation** | Depends on full accumulation history |
| **Surrender values** | May include discretionary terminal bonus |
| **Closed funds** | Estate runoff over decades with dwindling policyholders |

### Why This Matters for Gaspatchio

With-profits is a demanding use case that validates Phase 2 design:

1. **Period-stepping is unavoidable** - no closed-form solution exists
2. **Scenarios multiply complexity** - 10K scenarios × 360 periods
3. **Aggregate state matters** - can't fully parallelize across policies
4. **Management actions** - bonus decisions require conditional logic per period

If Phase 2 can handle with-profits efficiently, it can handle anything.

### Example: With-Profits Stepped Projection

```python
@gs.per_period(
    state=["asset_share", "guaranteed_value", "estate", "pols_if"],
    accumulate=["bonus_declared", "terminal_bonus_reserve"],
    # Note: estate is SHARED across policies, requires special handling
    shared_state=["estate"],
)
def project_with_profits(af: ActuarialFrame, t: int) -> ActuarialFrame:
    """Project one period of a with-profits fund."""

    # ---- Investment return (scenario-dependent) ----
    af.inv_return = returns_table.lookup(scenario_id=af.scenario_id, t=t)

    # ---- Asset share accumulation ----
    af.asset_share = (
        af.asset_share * (1 + af.inv_return)
        - af.mort_cost
        - af.expense_charge
    )

    # ---- Smoothing (affects credited return) ----
    expected_return = 0.04 / 12  # 4% annual target
    smoothing_factor = 0.3
    excess_return = af.inv_return - expected_return

    # Transfer excess to/from estate
    estate_transfer = af.pols_if * af.asset_share * excess_return * (1 - smoothing_factor)
    af.estate = af.estate + estate_transfer.sum()  # Aggregate across policies

    # ---- Bonus declaration (annual, at year-end) ----
    if t % 12 == 11:  # December
        af.bonus_rate = declare_annual_bonus(
            af.asset_share,
            af.guaranteed_value,
            af.estate,
            af.pols_if
        )
        af.guaranteed_value = af.guaranteed_value * (1 + af.bonus_rate)
        af.bonus_declared = af.guaranteed_value * af.bonus_rate
    else:
        af.bonus_declared = 0.0

    # ---- Dynamic lapse (policyholders hold when ITM) ----
    itm_ratio = af.asset_share / af.guaranteed_value
    daf = gs.clip(0.5 + 0.5 * itm_ratio, 0.3, 1.5)  # Wider range for WP
    af.lapse_rate = af.base_lapse_rate * daf

    # ---- Decrements ----
    af.pols_death = af.pols_if * af.mort_rate
    af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate
    af.pols_maturity = af.pols_if * (t == af.term_months)
    af.pols_if = af.pols_if - af.pols_death - af.pols_lapse - af.pols_maturity

    # ---- Terminal bonus on exit ----
    terminal_bonus = (af.asset_share - af.guaranteed_value).clip(lower=0)
    af.terminal_bonus_reserve = (
        terminal_bonus * (af.pols_death + af.pols_maturity + af.pols_lapse * 0.5)
    )

    return af
```

### The Scale Challenge

For stochastic risk calculations:
- 10,000 scenarios × 1,200 periods × 1,000 policies
- = 12 billion period-calculations
- Sequential through 1,200 periods
- But vectorized across 10M (scenarios × policies) within each period

This is computationally intensive but tractable with the right architecture.

## Design Principles

### 1. Vectorize What Can Be Vectorized

Within each period, calculations across policies × scenarios are independent:

```
Period 0: [Policy1×Scen1, Policy1×Scen2, ..., Policy1000×Scen10000]  → vectorized
Period 1: [Policy1×Scen1, Policy1×Scen2, ..., Policy1000×Scen10000]  → vectorized
...
Period 1199: [same]  → vectorized
```

Only the period-to-period progression is sequential.

### 2. Framework Manages the Loop

Users shouldn't write `for t in range(1200)` manually. The framework should:
- Manage period iteration
- Handle state carry-forward between periods
- Accumulate results
- Optimize memory (don't keep all periods in memory if not needed)

### 3. Formula IS the Code

Maintain the Gaspatchio philosophy - actuaries should see the calculation:

```python
# Clear: fund value = previous fund value × growth - charges
af.fund_value = af.fund_value_prev * (1 + af.fund_return) - af.charges
```

Not hidden behind abstraction:

```python
# Opaque - what formula is this?
af.fund_value = af.projection.accumulate("fund", growth=af.fund_return, deductions=af.charges)
```

### 4. Composable with Scenarios

Stepped projection must work seamlessly with Phase 1 scenario expansion:

```python
af = gs.expand_scenarios(af, scenario_ids)  # Phase 1
result = gs.run_stepped(af, project_period)  # Phase 2
metrics = result.group_by("scenario_id").agg(...)  # Aggregate
```

## Proposed API

### Option A: Decorator-Based Per-Period Function

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame

# Setup (same as Phase 1)
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
af = gs.expand_scenarios(af, scenario_ids=scenario_ids)

# Define per-period calculation
@gs.per_period
def project_period(af: ActuarialFrame, t: int, tables: dict) -> ActuarialFrame:
    """
    Called once per period t=0, 1, 2, ..., max_period.

    Within each call, af contains all policies × scenarios.
    Calculations are vectorized across this dimension.
    """
    # Lookup scenario-dependent assumptions for this period
    af.fund_return = tables["returns"].lookup(
        scenario_id=af.scenario_id,
        t=t,
        fund_index=af.fund_index
    )

    # Access previous period's values (framework handles this)
    fund_value_prev = af.fund_value  # At start of period, this is t-1's value

    # The formula IS the code - actuary can audit this
    af.fund_value = fund_value_prev * (1 + af.fund_return) - af.mgmt_charge

    # Path-dependent guarantee calculation
    af.guarantee_shortfall = gs.max(0, af.guarantee_floor - af.fund_value)

    # Dynamic lapse based on in-the-moneyness
    itm_ratio = af.fund_value / af.guarantee_floor
    af.daf = gs.clip(0.5 + 0.5 * itm_ratio, 0.5, 1.5)  # Dynamic Adjustment Factor
    af.lapse_rate = af.base_lapse_rate * af.daf

    # Decrements (vectorized across policies × scenarios)
    af.pols_lapse = af.pols_if * af.lapse_rate
    af.pols_death = af.pols_if * af.mort_rate
    af.pols_if = af.pols_if - af.pols_lapse - af.pols_death

    return af


# Run the stepped projection
result = gs.run_stepped(
    af=af,
    period_fn=project_period,
    max_periods=1200,
    tables={"returns": returns_table, "mortality": mort_table},
    initial_values={
        "fund_value": af.initial_investment,
        "pols_if": 1.0,
    },
    # Which columns to accumulate across periods (vs just carry forward)
    accumulate=["fund_value", "guarantee_shortfall", "pols_if", "pols_death"],
)

# Result has all periods - can aggregate for risk metrics
df = result.collect()
```

**Pros:**
- Clear separation of per-period logic
- Framework handles iteration, state management
- Familiar decorator pattern
- `t` is explicit - actuary knows which period they're in

**Cons:**
- More ceremony than Phase 1 models
- `tables` parameter feels awkward

### Option B: Context Manager with Period Iterator

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame

af = ActuarialFrame(pl.read_parquet("model_points.parquet"))
af = gs.expand_scenarios(af, scenario_ids=scenario_ids)

# Initialize values for t=0
af.fund_value = af.initial_investment
af.pols_if = 1.0

# Framework-managed period stepping
with gs.stepped_projection(af, max_periods=1200) as projection:
    for t in projection:
        # Access previous period values
        fund_value_prev = projection.previous("fund_value")

        # Lookup assumptions for this period
        af.fund_return = returns_table.lookup(
            scenario_id=af.scenario_id,
            t=t,
            fund_index=af.fund_index
        )

        # The formula IS the code
        af.fund_value = fund_value_prev * (1 + af.fund_return) - af.mgmt_charge

        # Dynamic policyholder behavior
        af.guarantee_shortfall = gs.max(0, af.guarantee_floor - af.fund_value)
        itm_ratio = af.fund_value / af.guarantee_floor
        af.lapse_rate = af.base_lapse_rate * gs.clip(0.5 + 0.5 * itm_ratio, 0.5, 1.5)

        # Decrements
        af.pols_lapse = af.pols_if * af.lapse_rate
        af.pols_death = af.pols_if * af.mort_rate
        af.pols_if = af.pols_if - af.pols_lapse - af.pols_death

        # Tell framework which values to carry forward / accumulate
        projection.commit(
            carry_forward=["fund_value", "pols_if"],
            accumulate=["guarantee_shortfall", "pols_death", "pols_lapse"]
        )

# After context exits, projection.result contains all accumulated periods
result = projection.result
```

**Pros:**
- Pythonic context manager pattern
- Explicit `projection.previous()` for accessing prior values
- Clear `commit()` separates carry-forward from accumulate
- User writes a loop (familiar) but framework manages complexity

**Cons:**
- `projection.commit()` at end of each iteration feels manual
- State management via `projection` object might confuse

### Option C: Hybrid - Model Class with Lifecycle Methods

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame

class UnitLinkedModel(gs.SteppedModel):
    """Model for unit-linked product with GMAB guarantee."""

    max_periods = 1200

    def setup(self, af: ActuarialFrame) -> ActuarialFrame:
        """Called once before projection starts."""
        af = gs.expand_scenarios(af, self.scenario_ids)

        # Load assumption tables
        self.returns_table = gs.Table.concat_scenario_files(...)
        self.mort_table = gs.Table(...)

        # Initialize period 0 values
        af.fund_value = af.initial_investment
        af.pols_if = 1.0

        return af

    def project_period(self, af: ActuarialFrame, t: int) -> ActuarialFrame:
        """Called for each period t=0, 1, ..., max_periods-1."""

        # Previous period access via accessor
        fund_value_prev = af.fund_value  # Framework swaps in previous values

        # Assumptions
        af.fund_return = self.returns_table.lookup(
            scenario_id=af.scenario_id,
            t=t,
            fund_index=af.fund_index
        )

        # Core calculation
        af.fund_value = fund_value_prev * (1 + af.fund_return) - af.mgmt_charge
        af.guarantee_shortfall = gs.max(0, af.guarantee_floor - af.fund_value)

        # Decrements
        af.pols_death = af.pols_if * af.mort_rate
        af.pols_lapse = af.pols_if * af.lapse_rate * self.dynamic_lapse_factor(af)
        af.pols_if = af.pols_if - af.pols_death - af.pols_lapse

        return af

    def dynamic_lapse_factor(self, af: ActuarialFrame) -> ColumnProxy:
        """Dynamic Adjustment Factor based on ITM ratio."""
        itm_ratio = af.fund_value / af.guarantee_floor
        return gs.clip(0.5 + 0.5 * itm_ratio, 0.5, 1.5)

    def finalize(self, af: ActuarialFrame) -> ActuarialFrame:
        """Called after all periods complete."""
        # Calculate present values, risk metrics, etc.
        af.pv_guarantee_cost = af.guarantee_shortfall.projection.discount(af.disc_rate)
        return af


# Usage
model = UnitLinkedModel(scenario_ids=scenario_ids)
result = model.run(pl.read_parquet("model_points.parquet"))
```

**Pros:**
- Clear lifecycle: setup → project_period → finalize
- Encapsulates tables and parameters in model class
- `project_period` is focused - just the per-period math
- Methods for complex logic (like dynamic lapse) keep main flow clean

**Cons:**
- More OOP than current Gaspatchio style
- Might feel heavy for simple cases

## Recommended Approach: Option A with Refinements

After considering the options, **Option A (decorator-based)** feels most aligned with Gaspatchio's philosophy:

1. **Simple models stay simple** - just add `@gs.per_period` decorator
2. **Formula is visible** - the per-period function IS the calculation
3. **Composable** - works with existing `expand_scenarios()`
4. **Clear mental model** - "this function runs once per period"

### Refined API

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame
import polars as pl

# ============================================================
# SETUP (before model)
# ============================================================

# Load model points
af = ActuarialFrame(pl.read_parquet("model_points.parquet"))

# Expand scenarios (Phase 1 API, unchanged)
scenario_ids = [str(i) for i in range(1, 1001)]  # 1000 stochastic scenarios
af = gs.expand_scenarios(af, scenario_ids=scenario_ids)

# Load scenario-varying assumption tables (Phase 1 API, unchanged)
returns_table = gs.Table(
    source="stochastic/fund_returns.parquet",
    dimensions={"scenario_id": "scenario_id", "t": "t", "fund_index": "fund_index"},
    value="monthly_return"
)

# ============================================================
# MODEL DEFINITION
# ============================================================

def main(af: ActuarialFrame) -> ActuarialFrame:
    """
    Unit-linked model with GMAB guarantee.

    Uses stepped projection because fund_value[t] depends on fund_value[t-1].
    """

    # Define the per-period calculation
    @gs.per_period(
        # Columns that carry forward from period to period
        state=["fund_value", "pols_if"],
        # Columns to accumulate (store all periods)
        accumulate=["guarantee_shortfall", "pols_death", "pols_lapse", "fund_value"],
    )
    def project(af: ActuarialFrame, t: int) -> ActuarialFrame:
        """
        Project one period. Called for t=0, 1, 2, ..., max_period.

        At entry:
        - af.fund_value contains the value from period t-1 (or initial for t=0)
        - af.pols_if contains survivors from period t-1 (or 1.0 for t=0)

        At exit:
        - af.fund_value should contain the NEW value for period t
        - Other columns will be accumulated or carried forward per decorator config
        """

        # ---- Assumptions lookup (vectorized across policies × scenarios) ----
        af.fund_return = returns_table.lookup(
            scenario_id=af.scenario_id,
            t=t,
            fund_index=af.fund_index
        )

        af.mort_rate = mort_table.lookup(age=af.age + t // 12)

        # ---- Fund value accumulation ----
        # The formula IS the code - actuary can audit this directly
        # Previous fund_value is already in af.fund_value (framework handled this)
        af.fund_value = af.fund_value * (1 + af.fund_return) - af.mgmt_charge_mth

        # ---- Guarantee calculation (path-dependent) ----
        af.guarantee_shortfall = (af.guarantee_floor - af.fund_value).clip(lower=0)

        # ---- Dynamic policyholder behavior ----
        # ITM ratio: fund_value / guarantee
        # When fund < guarantee (ITM for policyholder), they hold → lower lapse
        # When fund > guarantee (OTM), they may leave → higher lapse
        itm_ratio = af.fund_value / af.guarantee_floor
        daf = (0.5 + 0.5 * itm_ratio).clip(0.5, 1.5)  # Dynamic Adjustment Factor
        af.lapse_rate = af.base_lapse_rate * daf

        # ---- Decrements (order matters for dependent decrements) ----
        af.pols_death = af.pols_if * af.mort_rate
        af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate
        af.pols_if = af.pols_if - af.pols_death - af.pols_lapse

        return af

    # ---- Initial values for t=0 ----
    af.fund_value = af.initial_investment
    af.pols_if = pl.lit(1.0)

    # ---- Run the stepped projection ----
    af = gs.run_stepped(
        af,
        project,
        max_periods=af.policy_term.max() * 12,  # Monthly projection
    )

    # ---- Post-projection calculations ----
    # Now af has list columns with all periods accumulated

    # Discount factors
    af.disc_factors = af.disc_rate_mth.projection.discount_factors()

    # Present values
    af.pv_guarantee_cost = (af.guarantee_shortfall * af.disc_factors).list.sum()

    return af


# ============================================================
# EXECUTION & RISK METRICS
# ============================================================

result = main(af)
df = result.collect()

# Aggregate by scenario for risk metrics
by_scenario = df.group_by("scenario_id").agg([
    pl.col("pv_guarantee_cost").sum().alias("total_pv_guarantee"),
])

# Calculate CTE
import numpy as np
costs = by_scenario.sort("total_pv_guarantee", descending=True)["total_pv_guarantee"].to_numpy()
cte_98 = costs[:max(1, int(len(costs) * 0.02))].mean()
print(f"CTE 98%: {cte_98:,.0f}")
```

## Implementation Details

### State Management

The framework manages state between periods:

```python
@gs.per_period(state=["fund_value", "pols_if"], ...)
def project(af, t):
    # At entry: af.fund_value = value from t-1
    af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges
    # At exit: framework captures af.fund_value for t+1
    return af
```

Under the hood:
1. Before calling `project(af, t)`, framework sets `af.fund_value = state["fund_value"]`
2. After `project` returns, framework captures `state["fund_value"] = af.fund_value`
3. Accumulated columns are appended to result lists

### Memory Management

For 1000 scenarios × 1000 policies × 1200 periods:
- **Accumulate all**: 1.2B values per column × 8 bytes = ~10GB per column
- **Carry forward only**: Just current + previous period = ~16MB per column

Options:
```python
@gs.per_period(
    state=["fund_value", "pols_if"],  # Only current/previous kept
    accumulate=["pols_death"],         # All periods stored
    accumulate_every=12,               # Store every 12th period (annual snapshots)
    stream_to_disk=True,               # Write accumulated values to parquet incrementally
)
```

### Accessing Previous Period Values

Within `project()`, state columns contain previous period's values at entry:

```python
def project(af, t):
    # af.fund_value IS the previous period's value (framework handles this)
    prev_fund = af.fund_value
    af.fund_value = prev_fund * (1 + af.fund_return) - af.charges
```

For accessing t-2, t-3 etc., expand state:

```python
@gs.per_period(state=["fund_value", "fund_value_lag2"], ...)
def project(af, t):
    # Framework automatically shifts: lag2 = lag1, lag1 = current
    ...
```

### Error Handling

```python
def project(af, t):
    af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges

    # Framework validates after each period
    if (af.fund_value < 0).any():
        raise gs.ProjectionError(f"Negative fund value at period {t}")

    return af
```

## GPU Considerations

### Current Limitation

Polars GPU acceleration (via cuDF/RAPIDS) only works with pure Polars operations. Our Rust plugin (`gaspatchio_core._internal`) forces everything back to CPU.

### Path Forward

**Phase 2a (CPU):**
- Implement stepped projection on CPU
- Optimize with Rust parallelization within each period
- Profile to identify bottlenecks

**Phase 2b (GPU-friendly):**
- Identify hot paths that could use GPU
- Consider hybrid: GPU for inner vectorized ops, CPU for state management
- May require expressing more ops as pure Polars expressions

**Phase 2c (Full GPU):**
- Port key operations to GPU kernels
- Investigate Polars GPU plugin architecture
- Evaluate cuDF interop

### Performance Targets

| Configuration | Expected Runtime | Memory |
|---------------|------------------|--------|
| 100 scenarios × 100 policies × 360 periods (CPU) | ~5 seconds | ~500MB |
| 1000 scenarios × 1000 policies × 1200 periods (CPU) | ~5-10 minutes | ~10GB |
| 10000 scenarios × 1000 policies × 1200 periods (CPU) | ~1-2 hours | ~50GB+ |

GPU could potentially achieve 10-30x speedup on the inner vectorized operations.

## Compute Requirements & Resource Management

This section covers how to manage compute resources effectively when running stepped projections at scale. Understanding Polars internals is critical for production deployments.

### Polars Memory Model

#### Arrow Columnar Format

Polars uses Apache Arrow's columnar memory format. Key characteristics:

```
┌─────────────────────────────────────────────────────────────┐
│                    DataFrame in Memory                       │
├─────────────────────────────────────────────────────────────┤
│  Column: policy_id     Column: fund_value    Column: scenario│
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────┐ │
│  │ [1, 2, 3, ...]  │   │ [100K, 95K, ...]│   │ [1, 1, 1...]│ │
│  │ contiguous      │   │ contiguous      │   │ contiguous  │ │
│  │ memory          │   │ memory          │   │ memory      │ │
│  └─────────────────┘   └─────────────────┘   └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Implications for Phase 2:**
- Column operations are cache-friendly (sequential memory access)
- Adding columns is cheap (just add a new array)
- Row-wise operations are expensive (stride across columns)
- Memory is allocated per-column, not per-row

#### Copy-on-Write (CoW) Semantics

Polars uses copy-on-write to minimize allocations:

```python
# Original DataFrame
df1 = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

# "Copy" shares memory until mutation
df2 = df1  # No copy, same underlying buffers

# Mutation triggers copy of ONLY the modified column
df2 = df2.with_columns(a=pl.col("a") * 2)
# Now df2.a is new memory, but df2.b still shares with df1.b
```

**For stepped projection:**
```python
@gs.per_period(state=["fund_value"], ...)
def project(af, t):
    # This does NOT copy the entire DataFrame
    # Only fund_value column gets new allocation
    af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges
    return af
```

**Memory implication:** Each period only allocates memory for columns that change. Unchanged columns (policy_id, scenario_id, static assumptions) are never copied.

### Chunking in Polars

#### What Are Chunks?

A Polars Series can consist of multiple "chunks" - separate contiguous memory regions:

```
┌─────────────────────────────────────────────────────────────┐
│                    Chunked Series                            │
├─────────────────────────────────────────────────────────────┤
│  Chunk 0           Chunk 1           Chunk 2                 │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐           │
│  │ [1,2,3]  │ ───► │ [4,5,6]  │ ───► │ [7,8,9]  │           │
│  └──────────┘      └──────────┘      └──────────┘           │
│  (contiguous)      (contiguous)      (contiguous)           │
│                                                              │
│  Logical view: [1, 2, 3, 4, 5, 6, 7, 8, 9]                  │
└─────────────────────────────────────────────────────────────┘
```

#### When Chunks Accumulate

Chunks accumulate during append operations:

```python
# BAD: Creates many chunks (one per iteration)
accumulated = pl.DataFrame()
for t in range(1200):
    period_result = compute_period(t)
    accumulated = pl.concat([accumulated, period_result])
# Result: 1200 chunks! Slow subsequent operations.
```

#### Rechunking Strategy

```python
# GOOD: Collect then rechunk once
accumulated = []
for t in range(1200):
    period_result = compute_period(t)
    accumulated.append(period_result)

# Single rechunk at the end
final_df = pl.concat(accumulated, rechunk=True)
# Result: 1 chunk, fast operations
```

**When to rechunk:**
- After accumulation loop completes
- Before expensive operations (joins, group_by)
- Before writing to parquet (better compression)

**When NOT to rechunk:**
- During the loop (expensive, negates benefits)
- For small intermediate results
- When streaming to disk anyway

#### Chunk-Aware Accumulation Pattern

```python
class ChunkAwareAccumulator:
    """Accumulates results with periodic rechunking."""

    def __init__(self, rechunk_every: int = 100):
        self.rechunk_every = rechunk_every
        self.chunks = []
        self.period_count = 0

    def append(self, df: pl.DataFrame):
        self.chunks.append(df)
        self.period_count += 1

        # Periodic consolidation to prevent chunk explosion
        if self.period_count % self.rechunk_every == 0:
            self._consolidate()

    def _consolidate(self):
        if len(self.chunks) > 1:
            self.chunks = [pl.concat(self.chunks, rechunk=True)]

    def finalize(self) -> pl.DataFrame:
        self._consolidate()
        return self.chunks[0] if self.chunks else pl.DataFrame()
```

### Memory Management Strategies

#### Strategy 1: Estimate Before Running

```python
def estimate_memory_requirements(
    n_policies: int,
    n_scenarios: int,
    n_periods: int,
    state_columns: int = 2,
    accumulated_columns: int = 5,
    bytes_per_value: int = 8,
) -> dict:
    """
    Estimate memory requirements for stepped projection.

    Returns dict with memory estimates in GB.
    """
    n_rows = n_policies * n_scenarios

    # State: current + previous period for each state column
    state_bytes = n_rows * state_columns * 2 * bytes_per_value

    # Accumulated: all periods for each accumulated column
    accumulated_bytes = n_rows * n_periods * accumulated_columns * bytes_per_value

    # Working memory: intermediate calculations (~3x state)
    working_bytes = state_bytes * 3

    # Polars overhead: ~20% for metadata, alignment
    overhead_factor = 1.2

    total = (state_bytes + accumulated_bytes + working_bytes) * overhead_factor

    return {
        "state_gb": state_bytes / 1e9,
        "accumulated_gb": accumulated_bytes / 1e9,
        "working_gb": working_bytes / 1e9,
        "total_gb": total / 1e9,
        "recommendation": _memory_recommendation(total / 1e9),
    }

def _memory_recommendation(total_gb: float) -> str:
    if total_gb < 8:
        return "in_memory"
    elif total_gb < 32:
        return "periodic_snapshots"
    elif total_gb < 128:
        return "stream_to_disk"
    else:
        return "partitioned_execution"
```

#### Strategy 2: Periodic Snapshots

For medium-scale projections where full period granularity isn't needed:

```python
@gs.per_period(
    state=["fund_value", "pols_if"],
    accumulate=["claims", "fees"],
    accumulate_every=12,  # Store annual snapshots only
)
def project(af, t):
    ...
```

**Memory savings:** 12x reduction in accumulated data.

**Use when:**
- Risk metrics only need annual granularity
- Monthly detail can be reconstructed if needed
- Memory is constrained but not severely

#### Strategy 3: Stream to Disk

For large-scale projections:

```python
@gs.per_period(
    state=["fund_value", "pols_if"],
    accumulate=["claims", "fees"],
    stream_config=gs.StreamConfig(
        output_dir="results/projection/",
        batch_periods=100,
        compression="zstd",
        compression_level=3,
    )
)
def project(af, t):
    ...

# After projection, read results with streaming
results_lf = pl.scan_parquet("results/projection/*.parquet")
```

**How it works:**
1. Accumulate 100 periods in memory (~1-2GB)
2. Write to parquet with compression (~200-400MB on disk)
3. Clear memory, continue accumulation
4. Final analysis uses lazy scan (streaming read)

**Parquet compression comparison:**

| Compression | Write Speed | File Size | Read Speed |
|-------------|-------------|-----------|------------|
| None        | 1.0x        | 1.0x      | 1.0x       |
| snappy      | 0.9x        | 0.4x      | 0.95x      |
| zstd (3)    | 0.7x        | 0.25x     | 0.9x       |
| zstd (9)    | 0.3x        | 0.2x      | 0.9x       |

**Recommendation:** `zstd` level 3 for good balance of speed and compression.

#### Strategy 4: Partitioned Execution

For very large scale (>100GB), partition by scenario:

```python
def run_partitioned_projection(
    af: ActuarialFrame,
    project_fn: Callable,
    scenario_ids: list[str],
    partition_size: int = 1000,
    output_dir: str = "results/",
) -> None:
    """
    Run projection in scenario partitions to limit memory.
    """
    for i in range(0, len(scenario_ids), partition_size):
        partition_scenarios = scenario_ids[i:i + partition_size]

        # Filter to this partition
        af_partition = af.filter(pl.col("scenario_id").is_in(partition_scenarios))

        # Run projection for this partition
        result = gs.run_stepped(af_partition, project_fn, max_periods=1200)

        # Write partition results
        partition_path = f"{output_dir}/partition_{i:05d}.parquet"
        result.collect().write_parquet(partition_path)

        # Explicit cleanup
        del af_partition, result
        gc.collect()

    # Final aggregation uses streaming
    all_results = pl.scan_parquet(f"{output_dir}/partition_*.parquet")
    # ... aggregate with streaming engine
```

**Memory profile:**
```
┌────────────────────────────────────────────────────────────┐
│  Memory Usage Over Time (Partitioned Execution)            │
│                                                            │
│  RAM  ▲                                                    │
│   8GB │    ┌──┐    ┌──┐    ┌──┐    ┌──┐    ┌──┐           │
│       │    │  │    │  │    │  │    │  │    │  │           │
│   4GB │    │  │    │  │    │  │    │  │    │  │           │
│       │    │  │    │  │    │  │    │  │    │  │           │
│   0GB │────┴──┴────┴──┴────┴──┴────┴──┴────┴──┴──► Time   │
│       Part1    Part2    Part3    Part4    Part5           │
│                                                            │
│  Peak memory: ~8GB (one partition at a time)              │
│  Total data processed: 50GB+                               │
└────────────────────────────────────────────────────────────┘
```

### Polars Streaming Engine

The streaming engine processes data in batches without loading everything into memory.

#### When Streaming Helps

```python
# Scenario aggregation after projection
results_lf = pl.scan_parquet("results/**/*.parquet")  # 50GB on disk

# WITHOUT streaming: OOM
risk_metrics = results_lf.group_by("scenario_id").agg(...).collect()

# WITH streaming: Works on 8GB machine
risk_metrics = results_lf.group_by("scenario_id").agg(...).collect(engine="streaming")
```

#### Streaming Engine Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streaming Execution                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Source (50GB parquet)                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │  Batch 1    │   │  Batch 2    │   │  Batch N    │        │
│  │  (~100MB)   │──►│  (~100MB)   │──►│  (~100MB)   │        │
│  └─────────────┘   └─────────────┘   └─────────────┘        │
│         │                 │                 │                │
│         ▼                 ▼                 ▼                │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │  Process    │   │  Process    │   │  Process    │        │
│  │  (filter,   │   │  (filter,   │   │  (filter,   │        │
│  │   group)    │   │   group)    │   │   group)    │        │
│  └─────────────┘   └─────────────┘   └─────────────┘        │
│         │                 │                 │                │
│         └────────────┬────┴────────────────┘                │
│                      ▼                                       │
│               ┌─────────────┐                               │
│               │  Combine    │                               │
│               │  Partials   │                               │
│               └─────────────┘                               │
│                      │                                       │
│                      ▼                                       │
│               Final Result (~1MB)                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### Streaming-Compatible Operations

| Operation | Streaming Support | Notes |
|-----------|-------------------|-------|
| `filter` | ✅ Full | Per-batch filtering |
| `select` | ✅ Full | Column projection |
| `with_columns` | ✅ Full | Add computed columns |
| `group_by.agg` | ✅ Full | Partial aggregation per batch |
| `join` | ⚠️ Partial | Probe side must fit in memory |
| `sort` | ⚠️ Partial | External sort (slower) |
| `unique` | ⚠️ Partial | Hash table must fit |
| `explode` | ❌ No | Can blow up memory |

#### Configuring Streaming Batch Size

```python
# Set streaming batch size (rows per batch)
pl.Config.set_streaming_chunk_size(100_000)  # Default is ~50K-100K

# For memory-constrained environments
pl.Config.set_streaming_chunk_size(50_000)

# For high-memory environments (better throughput)
pl.Config.set_streaming_chunk_size(500_000)
```

#### Streaming for CTE Calculation

```python
def calculate_cte_streaming(
    results_dir: str,
    percentile: float = 0.98,
) -> float:
    """
    Calculate CTE using streaming for large result sets.
    """
    # Lazy scan all result files
    lf = pl.scan_parquet(f"{results_dir}/**/*.parquet")

    # Aggregate by scenario (streaming handles large data)
    scenario_totals = (
        lf
        .group_by("scenario_id")
        .agg([
            pl.col("pv_claims").sum().alias("total_claims"),
            pl.col("pv_premiums").sum().alias("total_premiums"),
        ])
        .with_columns([
            (pl.col("total_claims") - pl.col("total_premiums")).alias("loss")
        ])
        .collect(engine="streaming")
    )

    # CTE: average of worst (1-percentile) scenarios
    n_tail = max(1, int(len(scenario_totals) * (1 - percentile)))
    worst_losses = scenario_totals.sort("loss", descending=True).head(n_tail)
    cte = worst_losses["loss"].mean()

    return cte
```

### Compute Parallelism

#### Polars Thread Pool

Polars automatically parallelizes operations across CPU cores:

```python
# Check/set thread count
import polars as pl

print(pl.thread_pool_size())  # e.g., 8

# Limit threads (useful when running multiple projections)
# Set before any Polars operations
import os
os.environ["POLARS_MAX_THREADS"] = "4"
```

#### Parallelism Within vs Across Periods

```
┌─────────────────────────────────────────────────────────────┐
│            Parallelism in Stepped Projection                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Period Loop (SEQUENTIAL - cannot parallelize)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ for t in range(1200):                                 │   │
│  │     ┌────────────────────────────────────────────┐   │   │
│  │     │  Within Period (PARALLEL across rows)      │   │   │
│  │     │                                            │   │   │
│  │     │  10M rows split across 8 cores:            │   │   │
│  │     │  ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ... │   │   │
│  │     │  │1.2M│ │1.2M│ │1.2M│ │1.2M│ │1.2M│ │1.2M│   │   │   │
│  │     │  │   │ │   │ │   │ │   │ │   │ │   │     │   │   │
│  │     │  └───┘ └───┘ └───┘ └───┘ └───┘ └───┘     │   │   │
│  │     │  Core0 Core1 Core2 Core3 Core4 Core5     │   │   │
│  │     └────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Key: Sequential BETWEEN periods, parallel WITHIN periods   │
└─────────────────────────────────────────────────────────────┘
```

#### Expression Parallelism

Polars parallelizes independent expressions within `with_columns`:

```python
# These three expressions run in PARALLEL (independent)
af = af.with_columns([
    (pl.col("fund_value") * (1 + pl.col("return"))).alias("fund_value_new"),
    (pl.col("pols_if") * pl.col("mort_rate")).alias("pols_death"),
    (pl.col("premium") * pl.col("commission_rate")).alias("commission"),
])

# But this must be SEQUENTIAL (dependency)
af = af.with_columns(fund_value=pl.col("fund_value") * (1 + pl.col("return")))
af = af.with_columns(charge=pl.col("fund_value") * 0.01)  # Depends on new fund_value
```

**Optimization:** Batch independent calculations:

```python
# BAD: 6 sequential with_columns calls
af = af.with_columns(a=...)
af = af.with_columns(b=...)
af = af.with_columns(c=...)
af = af.with_columns(d=pl.col("a") + pl.col("b"))  # Depends on a, b
af = af.with_columns(e=...)
af = af.with_columns(f=...)

# GOOD: 2 batched calls
af = af.with_columns([
    (...).alias("a"),
    (...).alias("b"),
    (...).alias("c"),
    (...).alias("e"),
    (...).alias("f"),
])
af = af.with_columns(d=pl.col("a") + pl.col("b"))
```

### Monitoring and Profiling

#### Memory Monitoring

```python
import tracemalloc
import polars as pl

def profile_period_memory(project_fn, af, t):
    """Profile memory usage for a single period."""
    tracemalloc.start()

    af = project_fn(af, t)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "period": t,
        "current_mb": current / 1e6,
        "peak_mb": peak / 1e6,
    }

# Run for first few periods to establish baseline
for t in range(5):
    stats = profile_period_memory(project, af, t)
    print(f"Period {t}: peak={stats['peak_mb']:.1f}MB")
```

#### Query Plan Inspection

```python
# See what Polars will do
lf = pl.scan_parquet("data.parquet").filter(...).group_by(...).agg(...)

# Print optimized query plan
print(lf.explain())

# Streaming plan
print(lf.explain(streaming=True))
```

#### Timing Breakdown

```python
import time

class PeriodTimer:
    """Track time spent in different phases of period calculation."""

    def __init__(self):
        self.timings = []

    def time_period(self, project_fn, af, t):
        timings = {"period": t}

        # Assumption lookup
        start = time.perf_counter()
        af = lookup_assumptions(af, t)
        timings["lookup_ms"] = (time.perf_counter() - start) * 1000

        # Core calculations
        start = time.perf_counter()
        af = calculate_period(af, t)
        timings["calc_ms"] = (time.perf_counter() - start) * 1000

        # State update
        start = time.perf_counter()
        af = update_state(af)
        timings["state_ms"] = (time.perf_counter() - start) * 1000

        self.timings.append(timings)
        return af

    def summary(self):
        df = pl.DataFrame(self.timings)
        return df.select([
            pl.col("lookup_ms").mean().alias("avg_lookup_ms"),
            pl.col("calc_ms").mean().alias("avg_calc_ms"),
            pl.col("state_ms").mean().alias("avg_state_ms"),
            (pl.col("lookup_ms") + pl.col("calc_ms") + pl.col("state_ms"))
                .mean().alias("avg_total_ms"),
        ])
```

### Resource Management Best Practices

#### 1. Pre-flight Checks

```python
def preflight_check(af: ActuarialFrame, config: ProjectionConfig) -> None:
    """Validate resources before running projection."""

    # Estimate memory
    mem_estimate = estimate_memory_requirements(
        n_policies=af.n_policies,
        n_scenarios=af.n_scenarios,
        n_periods=config.max_periods,
        accumulated_columns=len(config.accumulate),
    )

    # Check available memory
    import psutil
    available_gb = psutil.virtual_memory().available / 1e9

    if mem_estimate["total_gb"] > available_gb * 0.8:
        raise MemoryError(
            f"Estimated {mem_estimate['total_gb']:.1f}GB required, "
            f"but only {available_gb:.1f}GB available. "
            f"Recommendation: {mem_estimate['recommendation']}"
        )

    # Check disk space for streaming
    if config.stream_config:
        import shutil
        disk_free = shutil.disk_usage(config.stream_config.output_dir).free / 1e9
        # Estimate ~25% of in-memory size after compression
        disk_needed = mem_estimate["accumulated_gb"] * 0.25
        if disk_needed > disk_free * 0.8:
            raise IOError(f"Insufficient disk space: need {disk_needed:.1f}GB")
```

#### 2. Graceful Degradation

```python
def adaptive_projection_config(
    n_policies: int,
    n_scenarios: int,
    n_periods: int,
    available_memory_gb: float,
) -> dict:
    """
    Automatically select projection strategy based on resources.
    """
    mem_estimate = estimate_memory_requirements(
        n_policies, n_scenarios, n_periods
    )

    if mem_estimate["total_gb"] < available_memory_gb * 0.6:
        return {
            "strategy": "in_memory",
            "accumulate_every": 1,
            "stream_to_disk": False,
        }
    elif mem_estimate["total_gb"] < available_memory_gb * 2:
        return {
            "strategy": "periodic_snapshots",
            "accumulate_every": 12,  # Annual
            "stream_to_disk": False,
        }
    elif mem_estimate["total_gb"] < available_memory_gb * 10:
        return {
            "strategy": "stream_to_disk",
            "accumulate_every": 1,
            "stream_to_disk": True,
            "batch_periods": 100,
        }
    else:
        # Calculate partition size to fit in memory
        partition_size = int(n_scenarios * available_memory_gb * 0.5 /
                            mem_estimate["total_gb"])
        return {
            "strategy": "partitioned",
            "partition_size": max(100, partition_size),
            "stream_to_disk": True,
        }
```

#### 3. Cleanup Protocol

```python
import gc

def run_with_cleanup(af, project_fn, config):
    """Run projection with explicit memory cleanup."""
    try:
        result = gs.run_stepped(af, project_fn, **config)
        return result
    finally:
        # Clear Polars string cache
        pl.StringCache().clear()

        # Force garbage collection
        gc.collect()

        # If using streaming, clear any temp files
        if config.get("stream_config"):
            # Temp files cleaned automatically, but force sync
            import os
            os.sync()
```

## Performance Deep Dive

### The Fundamental Performance Equation

For stepped projection, performance breaks down into:

```
Total Time = (Time per period) × (Number of periods)
           = (Polars overhead + Rust kernel time + Python overhead) × T
```

For 10M policy-scenarios × 1,200 periods = **12 billion operations**.

### Benchmark: Python vs Rust

From JuliaActuary research and our ref/26 analysis:

| Approach | Time per operation | For 12B operations |
|----------|-------------------|-------------------|
| Python loop | 2,314 ns | ~321 days |
| Python + Numba | 626 ns | ~87 days |
| **Rust plugin** | **7 ns** | **~23 hours** |

**Conclusion**: Rust plugin is non-negotiable for production workloads.

### Architecture: Where Time is Spent

```
┌─────────────────────────────────────────────────────────────────┐
│                     Period Loop (Python)                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  for t in range(1200):                      # ~1ms/iter   │  │
│  │      ┌─────────────────────────────────────────────────┐  │  │
│  │      │  1. Table lookup (Polars join)      # ~0.1ms    │  │  │
│  │      │  2. Rust accumulation kernel        # ~0.07ms   │  │  │
│  │      │  3. Decrement calculations          # ~0.05ms   │  │  │
│  │      │  4. State management                # ~0.01ms   │  │  │
│  │      │  5. Accumulation append             # ~0.02ms   │  │  │
│  │      └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Total: 1200 periods × ~0.25ms = ~5 minutes (1M policies)       │
└─────────────────────────────────────────────────────────────────┘
```

### Relationship to ref/26: Recursive Accumulation Primitives

Phase 2's stepped projection builds on the `scan_linear` primitive from ref/26:

```
ref/26 (Low-Level)              Phase 2 (High-Level)
─────────────────               ────────────────────
scan_linear(                    @gs.per_period(...)
  initial,                      def project(af, t):
  multiply,     ◄──────────────     af.fund_value = af.fund_value
  add                                   * (1 + af.fund_return)
) -> list                               - af.charges
                                    # Uses scan_linear internally
```

**Key difference**:
- **ref/26**: Assumes all inputs known upfront as list columns
- **Phase 2**: Inputs computed period-by-period (lookups, decisions)

**Within each period**, Phase 2 can still use ref/26's `scan_linear` for:
- Sub-period calculations (daily → monthly aggregation)
- Multi-timing-point accumulation
- Batch operations on list columns

### Polars Streaming Engine

The Polars streaming engine is critical for Phase 2's memory efficiency. It processes data in batches without loading everything into memory.

#### How Streaming Helps

```python
# WITHOUT streaming: Load all 50GB into memory
df = lf.collect()  # OOM for large datasets

# WITH streaming: Process in ~100MB batches
df = lf.collect(engine="streaming")  # Works on 8GB laptop
```

#### Streaming for Scenario Aggregation

After stepped projection completes, we aggregate results by scenario. This is where streaming shines:

```python
# Post-projection aggregation with streaming
result_lf = pl.scan_parquet("projection_results/*.parquet")

risk_metrics = (
    result_lf
    .group_by("scenario_id")
    .agg([
        pl.col("pv_claims").sum().alias("total_claims"),
        pl.col("pv_premiums").sum().alias("total_premiums"),
    ])
    .with_columns([
        (pl.col("total_claims") - pl.col("total_premiums")).alias("reserve")
    ])
    .sort("reserve", descending=True)
    .collect(engine="streaming")  # Process 50GB in 100MB chunks
)
```

#### Streaming During Accumulation

For very large projections, stream accumulated results to disk:

```python
@gs.per_period(
    state=["fund_value", "pols_if"],
    accumulate=["claims", "fees"],
    # Stream accumulated results to parquet every 100 periods
    stream_config=gs.StreamConfig(
        output_path="results/period_{t:04d}.parquet",
        batch_periods=100,
        compression="zstd",
    )
)
def project(af, t):
    ...
```

This pattern:
1. Accumulates 100 periods in memory (~800MB)
2. Writes to parquet with compression (~200MB on disk)
3. Clears memory, continues
4. Final read uses streaming scan across all parquet files

#### Streaming Performance Characteristics

| Operation | In-Memory | Streaming | Notes |
|-----------|-----------|-----------|-------|
| Simple aggregation | 1.0x | 0.9x | Slight overhead |
| Large group-by | OOM | ✅ Works | Memory-bounded |
| Joins | 1.0x | 0.7x | Slower but works |
| Sorting | 1.0x | 0.5x | External sort needed |

**When to use streaming**:
- Final aggregation over all scenarios
- Reading accumulated results from disk
- Memory-constrained environments

**When NOT to use streaming**:
- The period loop itself (need random access to state)
- Small datasets that fit in memory

### Accumulation Strategies

#### Strategy 1: In-Memory (Small/Medium)

```python
# For < 10GB total accumulated data
@gs.per_period(
    state=["fund_value"],
    accumulate=["claims", "fees", "fund_value"],  # All periods in memory
)
```

**Pros**: Fast, simple
**Cons**: Memory-limited

#### Strategy 2: Periodic Snapshots

```python
# Store every 12th period (annual snapshots)
@gs.per_period(
    state=["fund_value"],
    accumulate=["fund_value"],
    accumulate_every=12,  # Monthly projection, annual storage
)
```

**Pros**: 12x memory reduction
**Cons**: Lose monthly granularity (often acceptable for risk metrics)

#### Strategy 3: Streaming to Disk

```python
# Stream to parquet incrementally
@gs.per_period(
    state=["fund_value"],
    accumulate=["claims"],
    stream_config=gs.StreamConfig(
        output_path="results/",
        batch_periods=100,
    )
)
```

**Pros**: Unlimited scale
**Cons**: I/O overhead, ~2x slower

#### Strategy 4: Aggregation Only

```python
# Don't accumulate raw values, just running aggregates
@gs.per_period(
    state=["fund_value", "cumulative_claims"],
    accumulate=[],  # Nothing accumulated
)
def project(af, t):
    af.claims_t = af.pols_if * af.mort_rate * af.sum_assured
    af.cumulative_claims = af.cumulative_claims + af.claims_t
    ...
```

**Pros**: Minimal memory
**Cons**: Lose period-level detail

### Memory Budget Calculator

```python
def estimate_memory(
    n_policies: int,
    n_scenarios: int,
    n_periods: int,
    n_accumulated_columns: int,
    bytes_per_value: int = 8,
) -> dict:
    """Estimate memory requirements for stepped projection."""

    n_rows = n_policies * n_scenarios

    # State columns: just current period
    state_memory = n_rows * 2 * bytes_per_value  # fund_value + pols_if

    # Accumulated columns: all periods
    accumulated_memory = n_rows * n_periods * n_accumulated_columns * bytes_per_value

    # Working memory: ~2x state for intermediate calculations
    working_memory = state_memory * 2

    return {
        "state_mb": state_memory / 1e6,
        "accumulated_gb": accumulated_memory / 1e9,
        "working_mb": working_memory / 1e6,
        "total_gb": (state_memory + accumulated_memory + working_memory) / 1e9,
    }

# Example
estimate_memory(
    n_policies=1000,
    n_scenarios=10000,
    n_periods=1200,
    n_accumulated_columns=5,
)
# {'state_mb': 160.0, 'accumulated_gb': 48.0, 'working_mb': 320.0, 'total_gb': 48.5}
```

### Polars Best Practices for Phase 2

#### 1. Batch Column Updates

```python
# BAD: Multiple with_columns calls (overhead per call)
af = af.with_columns(x=pl.col("a") * 2)
af = af.with_columns(y=pl.col("b") + 1)
af = af.with_columns(z=pl.col("x") + pl.col("y"))

# GOOD: Single with_columns (parallel evaluation)
af = af.with_columns([
    (pl.col("a") * 2).alias("x"),
    (pl.col("b") + 1).alias("y"),
])
af = af.with_columns(z=pl.col("x") + pl.col("y"))
```

#### 2. Use Native Expressions

```python
# BAD: map_elements (Python per-row, ~100x slower)
af = af.with_columns(
    pl.col("x").map_elements(lambda x: x ** 2)
)

# GOOD: Native expression (vectorized, parallel)
af = af.with_columns(
    (pl.col("x") ** 2).alias("x_squared")
)
```

#### 3. Rechunk After Accumulation

```python
# During loop: append without rechunking (fast)
accumulated = []
for t in range(max_periods):
    accumulated.append(period_result)

# After loop: rechunk once (optimizes subsequent operations)
final_df = pl.concat(accumulated, rechunk=True)
```

#### 4. Lazy for Setup, Eager for Loop

```python
# GOOD: Lazy for initial setup (full optimization)
af = (
    pl.scan_parquet("model_points.parquet")
    .join(scenarios_lf, on="dummy", how="cross")
    .collect()  # Materialize before loop
)

# Loop uses eager operations (state mutation needed)
for t in range(max_periods):
    af = project(af, t)  # Eager DataFrame operations
```

### Benchmark Requirements

Before shipping Phase 2, we need benchmarks for:

| Benchmark | Target | Measurement |
|-----------|--------|-------------|
| Per-period overhead | < 1ms | Time per `project()` call minus kernel time |
| Rust kernel throughput | > 100M ops/sec | scan_linear on 10M rows |
| Memory efficiency | < 2x theoretical | Actual vs calculated memory budget |
| Streaming I/O | > 500MB/s | Write throughput to parquet |
| Scenario aggregation | < 60s | CTE calculation on 10K scenarios |

```python
# Benchmark harness
import time

def benchmark_stepped_projection(n_policies, n_scenarios, n_periods):
    af = setup_test_data(n_policies, n_scenarios)

    start = time.perf_counter()
    result = gs.run_stepped(af, project_fn, max_periods=n_periods)
    elapsed = time.perf_counter() - start

    ops_per_second = (n_policies * n_scenarios * n_periods) / elapsed
    ms_per_period = (elapsed / n_periods) * 1000

    return {
        "total_seconds": elapsed,
        "ms_per_period": ms_per_period,
        "ops_per_second": ops_per_second,
    }
```

## Comparison: Phase 1 vs Phase 2 Models

| Aspect | Phase 1 (Vectorized) | Phase 2 (Stepped) |
|--------|---------------------|-------------------|
| **Products** | Term, whole life, traditional annuities | Unit-linked, with-profits, VAs |
| **Period calculation** | All at once (list columns) | One at a time (framework loop) |
| **Dependencies** | T independent of T-1 | T depends on T-1 |
| **Primary API** | `af.col = af.other_col.projection.method()` | `@gs.per_period` + `gs.run_stepped()` |
| **Scenario support** | `gs.expand_scenarios()` | Same - fully compatible |
| **Memory** | Store all periods upfront | Configurable accumulation |
| **GPU potential** | Limited (plugin forces CPU) | Higher (pure Polars ops in inner loop) |

## Design Philosophy: Stepped-Ready by Default

Following the same principle as scenario support (see RFC 27), **models that need stepped projection should be stepped-ready from day one**.

The question isn't "should I migrate to Phase 2?" - it's "does my product have path dependencies?"

| Product Type | Path Dependent? | Use |
|--------------|-----------------|-----|
| Term life | No | Phase 1 (vectorized) |
| Whole life | No | Phase 1 (vectorized) |
| Traditional annuities | No | Phase 1 (vectorized) |
| **Unit-linked** | **Yes** | **Phase 2 (stepped)** |
| **With-profits** | **Yes** | **Phase 2 (stepped)** |
| **Variable annuities** | **Yes** | **Phase 2 (stepped)** |
| **Universal life** | **Yes** | **Phase 2 (stepped)** |

**The principle:** If your product has `state[t] = f(state[t-1], ...)`, you need Phase 2. This is a product characteristic, not a model maturity level.

### Stepped-Ready Pattern

A stepped-ready model follows this structure from the start:

```python
def main(af: ActuarialFrame) -> ActuarialFrame:
    """Unit-linked model - stepped from day one."""

    @gs.per_period(
        state=["fund_value", "pols_if"],
        accumulate=["claims", "fees", "fund_value"],
    )
    def project(af: ActuarialFrame, t: int) -> ActuarialFrame:
        # Assumption lookups (always use af.scenario_id)
        af.fund_return = returns_table.lookup(
            scenario_id=af.scenario_id,
            t=t
        )

        # The formula IS the code
        af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges
        af.pols_death = af.pols_if * af.mort_rate
        af.pols_if = af.pols_if - af.pols_death - af.pols_lapse

        return af

    # Initialize state
    af.fund_value = af.initial_premium
    af.pols_if = 1.0

    # Run projection (same code for 1 or 10,000 scenarios)
    return gs.run_stepped(af, project, max_periods=1200)
```

**Benefits:**
1. **No migration needed** - model is stepped from the start
2. **Clear intent** - `@gs.per_period` declares "this product is path-dependent"
3. **Scenario-ready** - lookups use `af.scenario_id`, works with any number of scenarios
4. **Testable** - run with 1 scenario and 12 periods for fast unit tests

## Migration Guide: Converting Phase 1 Model to Phase 2

This guide is for converting existing Phase 1 (vectorized) models to Phase 2 (stepped). **Only do this if your product genuinely requires path-dependent calculations.**

### When to Migrate

**Migrate if:**
- You're adding fund accumulation logic (unit-linked, UL)
- You're adding path-dependent guarantees (GMAB, GMWB)
- You're adding dynamic policyholder behavior based on accumulated value
- Your existing model has "hacks" to approximate recursive calculations

**Don't migrate if:**
- Your product has closed-form solutions (term, whole life, traditional annuities)
- You're just adding scenarios (use Phase 1 `expand_scenarios`)
- You're optimizing performance (Phase 1 is usually faster for non-path-dependent products)

### Step 1: Identify State Variables

Review your model for variables that carry forward between periods:

```python
# BEFORE: Phase 1 - calculating pols_if as cumulative survival
af.pols_if = af.decrement.projection.cumulative_survival()

# ASK: Does pols_if depend on anything calculated during projection?
# If NO → keep Phase 1
# If YES → needs Phase 2 (e.g., dynamic lapse depends on fund value)
```

**Common state variables:**
| Variable | Why it's state |
|----------|----------------|
| `fund_value` | Accumulates with returns, charges |
| `pols_if` | Depends on dynamic lapse (ITM behavior) |
| `guarantee_base` | May ratchet based on fund value |
| `asset_share` | Accumulates with experience |
| `estate` | Shared across policies, accumulates |

### Step 2: Identify Accumulated Variables

Decide which variables you need for all periods (accumulated) vs just the final value:

```python
@gs.per_period(
    # State: only current/previous period kept
    state=["fund_value", "pols_if"],

    # Accumulated: all periods stored (for PV calculations, reporting)
    accumulate=["claims", "fees", "guarantee_shortfall"],
)
```

**Rule of thumb:**
- **State only:** Variables used in next period's calculation but not needed for output
- **Accumulate:** Variables needed for present value sums, period-by-period reporting

### Step 3: Extract Per-Period Logic

Convert vectorized list operations to explicit per-period calculations:

```python
# BEFORE: Phase 1 (vectorized across all periods at once)
def main(af):
    # All periods calculated in one operation
    af.disc_factors = af.disc_rate.projection.discount_factors()
    af.pols_if = af.decrement.projection.cumulative_survival()
    af.claims = af.sum_assured * af.pols_death * af.pols_if
    af.pv_claims = (af.claims * af.disc_factors).list.sum()
    return af


# AFTER: Phase 2 (explicit per-period)
def main(af):
    @gs.per_period(
        state=["pols_if"],
        accumulate=["claims", "pols_death"],
    )
    def project(af, t):
        # Explicit per-period calculation
        af.pols_death = af.pols_if * af.mort_rate[t]  # mort_rate is a list, index by t
        af.pols_lapse = af.pols_if * af.lapse_rate[t]
        af.pols_if = af.pols_if - af.pols_death - af.pols_lapse
        af.claims = af.sum_assured * af.pols_death
        return af

    # Initialize
    af.pols_if = 1.0

    # Run stepped projection
    af = gs.run_stepped(af, project, max_periods=af.term.max() * 12)

    # Post-projection: PV calculations on accumulated results
    af.disc_factors = af.disc_rate.projection.discount_factors()
    af.pv_claims = (af.claims * af.disc_factors).list.sum()

    return af
```

### Step 4: Update Assumption Lookups

Change from list-column lookups to per-period lookups:

```python
# BEFORE: Phase 1 - lookup returns list column for all periods
af.mort_rate = mort_table.lookup(age=af.age, duration=af.duration)
# mort_rate is a list: [q_0, q_1, q_2, ..., q_T]


# AFTER: Phase 2 - lookup returns scalar for period t
@gs.per_period(...)
def project(af, t):
    af.mort_rate = mort_table.lookup(
        scenario_id=af.scenario_id,
        age=af.age + t // 12,  # Age increases with t
        duration=t
    )
    # mort_rate is a scalar: q_t
```

**Alternative:** Keep list lookups, index by `t`:

```python
# Setup: get all rates as lists (once, outside the loop)
af.mort_rates_all = mort_table.lookup_list(age=af.age, max_t=1200)

@gs.per_period(...)
def project(af, t):
    # Index into the pre-computed list
    af.mort_rate = af.mort_rates_all.list.get(t)
```

### Step 5: Add Recursive Logic

Now you can add the path-dependent calculations that motivated the migration:

```python
@gs.per_period(
    state=["fund_value", "pols_if"],
    accumulate=["claims", "guarantee_cost"],
)
def project(af, t):
    # ---- Fund accumulation (the reason we migrated!) ----
    af.fund_return = returns_table.lookup(scenario_id=af.scenario_id, t=t)
    af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges

    # ---- Path-dependent guarantee ----
    af.guarantee_cost = (af.guarantee_floor - af.fund_value).clip(lower=0)

    # ---- Dynamic lapse (depends on fund vs guarantee) ----
    itm_ratio = af.fund_value / af.guarantee_floor
    daf = (0.5 + 0.5 * itm_ratio).clip(0.5, 1.5)
    af.lapse_rate = af.base_lapse * daf

    # ---- Decrements ----
    af.pols_death = af.pols_if * af.mort_rate
    af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate
    af.pols_if = af.pols_if - af.pols_death - af.pols_lapse

    return af
```

### Step 6: Update Post-Processing

Results now have list columns for accumulated variables:

```python
# BEFORE: Phase 1 - results already have list columns
df = result.collect()
total_claims = df["claims"].list.sum().sum()

# AFTER: Phase 2 - same structure! (accumulated columns are lists)
df = result.collect()
total_claims = df["claims"].list.sum().sum()

# Risk metrics work the same way
by_scenario = df.group_by("scenario_id").agg([
    pl.col("pv_claims").sum()
])
```

### Migration Checklist

- [ ] Confirm product genuinely requires path-dependent calculations
- [ ] Identify state variables (carry forward between periods)
- [ ] Identify accumulated variables (need all periods for output)
- [ ] Add `@gs.per_period` decorator with state/accumulate config
- [ ] Convert vectorized list operations to per-period logic
- [ ] Update assumption lookups (per-period or indexed)
- [ ] Add initialization for state variables before `gs.run_stepped()`
- [ ] Keep post-projection PV calculations after `gs.run_stepped()`
- [ ] Verify scenario_id used in all scenario-varying lookups
- [ ] Test: Run single scenario, compare key outputs to Phase 1 version
- [ ] Test: Run multiple scenarios, verify aggregation works
- [ ] Profile: Compare performance to Phase 1 baseline

### Validation: Phase 1 vs Phase 2 Equivalence

For products that CAN use Phase 1, Phase 2 should give **identical results**:

```python
def test_phase1_phase2_equivalence():
    """Verify Phase 2 matches Phase 1 for non-path-dependent product."""

    af = load_test_data()
    af = gs.expand_scenarios(af, scenario_ids=["BASE"])

    # Phase 1
    af1 = af.clone()
    af1.pols_if = af1.decrement.projection.cumulative_survival()
    af1.claims = af1.sum_assured * af1.pols_death
    result1 = af1.collect()

    # Phase 2
    af2 = af.clone()

    @gs.per_period(state=["pols_if"], accumulate=["claims"])
    def project(af, t):
        af.pols_death = af.pols_if * af.mort_rate.list.get(t)
        af.pols_lapse = af.pols_if * af.lapse_rate.list.get(t)
        af.pols_if = af.pols_if - af.pols_death - af.pols_lapse
        af.claims = af.sum_assured * af.pols_death
        return af

    af2.pols_if = 1.0
    af2 = gs.run_stepped(af2, project, max_periods=360)
    result2 = af2.collect()

    # Compare
    assert_frame_equal(
        result1.select(["policy_id", "claims"]),
        result2.select(["policy_id", "claims"]),
        rtol=1e-10
    )
```

Include this test in your migration to catch regressions.

## Migration Guide: With-Profits and Estate Models

This guide covers migration to **recursive projection with shared state** - the pattern required for with-profits, participating policies, and any model where aggregate fund state affects individual policy outcomes.

### What Makes With-Profits Different

With-profits models have complexity beyond basic stepped projection:

| Aspect | Basic Stepped (UL/VA) | With-Profits |
|--------|----------------------|--------------|
| **State scope** | Per-policy only | Per-policy + **shared estate** |
| **State dependencies** | Policy independent | **Cross-policy dependencies** |
| **Decisions** | Algorithmic/formulaic | **Management actions** (discretionary) |
| **Aggregation timing** | After projection | **During each period** |
| **Constraints** | Contract terms | **PRE, smoothing, regulatory** |
| **Bonus mechanics** | N/A | Reversionary, terminal, interim |

**Key insight:** In with-profits, you cannot fully parallelize across policies because the **estate** (shared surplus) affects all policies, and bonus declarations depend on aggregate fund health.

### The Shared State Problem

Basic stepped projection assumes policies are independent within each period:

```python
# Basic stepped: each row is independent
@gs.per_period(state=["fund_value", "pols_if"], ...)
def project(af, t):
    # This calculation only uses data from THIS row
    af.fund_value = af.fund_value * (1 + af.fund_return) - af.charges
    return af
```

With-profits breaks this assumption:

```python
# With-profits: rows affect each other via shared estate
@gs.per_period(state=["asset_share", "guaranteed_value", "pols_if"], ...)
def project(af, t):
    # Asset share is per-policy...
    af.asset_share = af.asset_share * (1 + af.inv_return) - af.charges

    # ...but estate is AGGREGATE across all policies
    total_surplus = (af.asset_share - af.guaranteed_value) * af.pols_if
    estate = total_surplus.sum()  # Single value for entire fund!

    # Bonus rate depends on estate (affects ALL policies)
    bonus_rate = calculate_bonus(estate, total_liabilities)

    # All policies get the same bonus rate
    af.guaranteed_value = af.guaranteed_value * (1 + bonus_rate)

    return af
```

### Framework Support: Shared State

Phase 2 needs explicit support for shared (aggregate) state:

```python
@gs.per_period(
    # Per-policy state (one value per row)
    state=["asset_share", "guaranteed_value", "pols_if"],

    # Shared state (one value for entire fund, computed via aggregation)
    shared_state={
        "estate": lambda af: ((af.asset_share - af.guaranteed_value) * af.pols_if).sum(),
        "total_pols_if": lambda af: af.pols_if.sum(),
    },

    accumulate=["bonus_declared", "claims"],
)
def project(af, t):
    # af.estate is now available as a scalar (same value for all rows)
    ...
```

### Step-by-Step: Migrating a With-Profits Model

#### Step 1: Identify Per-Policy vs Shared State

Classify every state variable:

| Variable | Scope | Aggregation |
|----------|-------|-------------|
| `asset_share` | Per-policy | None |
| `guaranteed_value` | Per-policy | None |
| `pols_if` | Per-policy | None |
| `estate` | **Shared** | `sum((AS - GV) * pols_if)` |
| `smoothed_return` | **Shared** | Weighted average or fund-level |
| `bonus_rate` | **Shared** | Single rate for cohort/fund |

#### Step 2: Define Aggregation Functions

For each shared state variable, define how it's computed from per-policy data:

```python
shared_state_definitions = {
    # Estate: total surplus across all policies
    "estate": lambda af: (
        (af.asset_share - af.guaranteed_value) * af.pols_if
    ).sum(),

    # Total fund value (for smoothing calculations)
    "total_fund": lambda af: (af.asset_share * af.pols_if).sum(),

    # Weighted average asset share (for reporting)
    "avg_asset_share": lambda af: (
        (af.asset_share * af.pols_if).sum() / af.pols_if.sum()
    ),
}
```

#### Step 3: Implement Smoothing Logic

Smoothing spreads investment returns over time to reduce policyholder volatility:

```python
@gs.per_period(
    state=["asset_share", "smoothed_return_accumulator"],
    shared_state={"estate": ..., "total_fund": ...},
    ...
)
def project(af, t):
    # Actual investment return (scenario-dependent)
    af.actual_return = returns_table.lookup(scenario_id=af.scenario_id, t=t)

    # Smoothing parameters
    target_return = 0.04 / 12  # 4% annual target
    smoothing_weight = 0.2     # 20% of excess goes to/from estate

    # Calculate smoothed (credited) return
    excess = af.actual_return - target_return

    if af.estate > 0:
        # Estate healthy: can smooth more aggressively
        af.credited_return = target_return + excess * (1 - smoothing_weight)
        estate_transfer = excess * smoothing_weight * af.total_fund
    else:
        # Estate depleted: pass through more volatility
        af.credited_return = af.actual_return
        estate_transfer = 0

    # Update estate (this becomes input to shared_state for next period)
    af.estate_delta = estate_transfer

    # Apply credited return to asset shares
    af.asset_share = af.asset_share * (1 + af.credited_return) - af.charges

    return af
```

#### Step 4: Implement Bonus Declaration Logic

Bonus declarations are management actions - discretionary but constrained:

```python
def declare_bonus(
    af: ActuarialFrame,
    t: int,
    estate: float,
    config: BonusConfig,
) -> float:
    """
    Declare reversionary bonus rate.

    Constraints:
    - PRE: Can't cut bonuses arbitrarily (Policyholder Reasonable Expectations)
    - Estate: Must be supportable by available surplus
    - Competitive: Should be reasonable vs market
    """

    # Only declare annually (e.g., December)
    if t % 12 != 11:
        return 0.0

    # Calculate supportable bonus from asset shares
    total_surplus = estate
    total_guaranteed = (af.guaranteed_value * af.pols_if).sum()
    remaining_term_avg = af.remaining_term.mean()

    # What bonus rate can the estate support?
    supportable_rate = total_surplus / (total_guaranteed * remaining_term_avg)
    supportable_rate = max(0, supportable_rate)

    # PRE constraint: can't cut too fast from previous
    previous_rate = config.previous_bonus_rate
    min_rate = previous_rate * config.pre_floor  # e.g., 90% of previous

    # Apply constraints
    bonus_rate = max(min_rate, min(supportable_rate, config.target_rate))

    # If estate negative, may need to cut to zero
    if estate < config.estate_floor:
        bonus_rate = max(0, min_rate * 0.5)  # Emergency reduction

    return bonus_rate


@gs.per_period(...)
def project(af, t):
    ...

    # Annual bonus declaration
    bonus_rate = declare_bonus(af, t, af.estate, bonus_config)

    # Apply to all policies
    af.bonus_declared = af.guaranteed_value * bonus_rate
    af.guaranteed_value = af.guaranteed_value + af.bonus_declared

    ...
```

#### Step 5: Handle Terminal Bonus

Terminal bonus is paid on exit (death, maturity, surrender) and is discretionary:

```python
@gs.per_period(...)
def project(af, t):
    ...

    # Calculate terminal bonus entitlement (not guaranteed)
    # Typically: excess of asset share over guaranteed value
    af.terminal_bonus_entitlement = (af.asset_share - af.guaranteed_value).clip(lower=0)

    # Terminal bonus actually paid depends on estate and exit type
    # Death/maturity: typically full entitlement
    # Surrender: may apply MVA (Market Value Adjustment)

    af.terminal_bonus_death = af.terminal_bonus_entitlement * af.pols_death
    af.terminal_bonus_maturity = af.terminal_bonus_entitlement * af.pols_maturity

    # Surrender: apply MVA if estate stressed
    mva_factor = calculate_mva(af.estate, af.total_fund)
    af.terminal_bonus_surrender = (
        af.terminal_bonus_entitlement * mva_factor * af.pols_surrender
    )

    # Total terminal bonus outgo this period
    af.terminal_bonus_paid = (
        af.terminal_bonus_death +
        af.terminal_bonus_maturity +
        af.terminal_bonus_surrender
    )

    return af
```

#### Step 6: Cohort Handling

With-profits funds often have multiple cohorts (generations) with different terms:

```python
@gs.per_period(
    state=["asset_share", "guaranteed_value", "pols_if"],
    shared_state={
        # Estate shared across ALL cohorts
        "estate": lambda af: ((af.asset_share - af.guaranteed_value) * af.pols_if).sum(),
    },
    # But bonus rates may differ by cohort
    group_shared_state={
        "cohort_surplus": {
            "group_by": "cohort_id",
            "agg": lambda af: ((af.asset_share - af.guaranteed_value) * af.pols_if).sum(),
        }
    },
    ...
)
def project(af, t):
    # Estate is fund-wide
    fund_estate = af.estate

    # But bonus rate may vary by cohort
    af.bonus_rate = af.cohort_surplus / af.cohort_guaranteed * af.bonus_scale

    ...
```

### Complete With-Profits Example

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame
import polars as pl

def main(af: ActuarialFrame) -> ActuarialFrame:
    """
    With-profits model with estate management.

    Features:
    - Asset share accumulation with smoothing
    - Shared estate across policies
    - Annual reversionary bonus declaration
    - Terminal bonus on exit
    - PRE constraints on bonus reductions
    """

    # ---- Configuration ----
    bonus_config = BonusConfig(
        target_rate=0.02,        # 2% target annual bonus
        pre_floor=0.9,          # Can't cut more than 10% per year
        estate_floor=-1_000_000, # Emergency threshold
        previous_bonus_rate=0.02,
    )

    smoothing_config = SmoothingConfig(
        target_return=0.04 / 12,
        smoothing_weight=0.2,
    )

    # ---- Per-period projection ----
    @gs.per_period(
        state=["asset_share", "guaranteed_value", "pols_if", "estate_balance"],
        shared_state={
            "estate": lambda af: (
                (af.asset_share - af.guaranteed_value) * af.pols_if
            ).sum() + af.estate_balance.first(),
            "total_fund": lambda af: (af.asset_share * af.pols_if).sum(),
            "total_pols_if": lambda af: af.pols_if.sum(),
        },
        accumulate=[
            "bonus_declared",
            "terminal_bonus_paid",
            "claims_guaranteed",
            "claims_terminal",
        ],
    )
    def project(af: ActuarialFrame, t: int) -> ActuarialFrame:
        """Project one period of with-profits fund."""

        # ---- Investment return (scenario-dependent) ----
        af.actual_return = returns_table.lookup(
            scenario_id=af.scenario_id,
            t=t
        )

        # ---- Smoothing ----
        af.credited_return, estate_delta = apply_smoothing(
            af.actual_return,
            af.estate,
            af.total_fund,
            smoothing_config
        )

        # ---- Asset share accumulation ----
        af.asset_share = (
            af.asset_share * (1 + af.credited_return)
            - af.mortality_charge
            - af.expense_charge
        )

        # ---- Update estate balance ----
        af.estate_balance = af.estate + estate_delta

        # ---- Annual bonus declaration ----
        if t % 12 == 11:  # December
            bonus_rate = declare_bonus(af, t, af.estate, bonus_config)
            af.bonus_declared = af.guaranteed_value * bonus_rate
            af.guaranteed_value = af.guaranteed_value + af.bonus_declared
            bonus_config.previous_bonus_rate = bonus_rate
        else:
            af.bonus_declared = 0.0

        # ---- Terminal bonus calculation ----
        af.terminal_bonus_entitlement = (
            af.asset_share - af.guaranteed_value
        ).clip(lower=0)

        # ---- Dynamic lapse (ITM policyholders hold) ----
        itm_ratio = af.asset_share / af.guaranteed_value
        daf = (0.5 + 0.5 * itm_ratio).clip(0.3, 1.5)
        af.lapse_rate = af.base_lapse_rate * daf

        # ---- Decrements ----
        af.pols_death = af.pols_if * af.mort_rate
        af.pols_maturity = af.pols_if * (t == af.term_months)
        af.pols_surrender = (
            (af.pols_if - af.pols_death - af.pols_maturity) * af.lapse_rate
        )
        af.pols_if = (
            af.pols_if - af.pols_death - af.pols_maturity - af.pols_surrender
        )

        # ---- Claims ----
        # Guaranteed: sum assured + declared bonuses
        af.claims_guaranteed = af.guaranteed_value * (
            af.pols_death + af.pols_maturity + af.pols_surrender
        )

        # Terminal bonus (discretionary)
        mva = calculate_mva(af.estate, af.total_fund)
        af.terminal_bonus_paid = af.terminal_bonus_entitlement * (
            af.pols_death +           # Full on death
            af.pols_maturity +        # Full on maturity
            af.pols_surrender * mva   # MVA on surrender
        )

        # ---- Deduct claims from estate ----
        af.estate_balance = af.estate_balance - af.terminal_bonus_paid.sum()

        return af

    # ---- Initialize ----
    af.asset_share = af.initial_premium
    af.guaranteed_value = af.initial_sum_assured
    af.pols_if = 1.0
    af.estate_balance = af.initial_estate  # Starting estate (may be from prior periods)

    # ---- Run projection ----
    af = gs.run_stepped(af, project, max_periods=360)  # 30 years

    # ---- Post-projection: Present values ----
    af.disc_factors = af.disc_rate.projection.discount_factors()
    af.pv_claims_guaranteed = (af.claims_guaranteed * af.disc_factors).list.sum()
    af.pv_claims_terminal = (af.terminal_bonus_paid * af.disc_factors).list.sum()
    af.pv_claims_total = af.pv_claims_guaranteed + af.pv_claims_terminal

    return af


# ---- Helper functions ----

def apply_smoothing(actual_return, estate, total_fund, config):
    """Apply smoothing to investment returns."""
    excess = actual_return - config.target_return

    if estate > 0:
        credited = config.target_return + excess * (1 - config.smoothing_weight)
        delta = excess * config.smoothing_weight * total_fund
    else:
        credited = actual_return
        delta = 0

    return credited, delta


def calculate_mva(estate, total_fund):
    """Market Value Adjustment for surrenders when estate stressed."""
    if total_fund == 0:
        return 1.0

    estate_ratio = estate / total_fund

    if estate_ratio > 0.05:
        return 1.0  # No MVA
    elif estate_ratio > 0:
        return 0.95  # 5% MVA
    else:
        return 0.90  # 10% MVA (estate negative)
```

### With-Profits Migration Checklist

- [ ] **Identify shared vs per-policy state**
  - [ ] Estate/surplus: shared
  - [ ] Asset share: per-policy
  - [ ] Bonus rate: shared (possibly per-cohort)

- [ ] **Define aggregation functions for shared state**
  - [ ] Estate calculation
  - [ ] Total fund value
  - [ ] Per-cohort aggregations if needed

- [ ] **Implement smoothing logic**
  - [ ] Target return
  - [ ] Smoothing weights
  - [ ] Estate transfer mechanics

- [ ] **Implement bonus declaration**
  - [ ] Reversionary bonus (annual)
  - [ ] PRE constraints
  - [ ] Estate dependency
  - [ ] Store previous bonus rate for constraints

- [ ] **Implement terminal bonus**
  - [ ] Entitlement calculation
  - [ ] Payment on death/maturity (full)
  - [ ] MVA on surrender
  - [ ] Estate impact

- [ ] **Handle cohorts if applicable**
  - [ ] Different bonus scales by cohort
  - [ ] Cohort-level vs fund-level estate

- [ ] **Dynamic policyholder behavior**
  - [ ] ITM ratio based on asset share vs guaranteed
  - [ ] Surrender penalty sensitivity

- [ ] **Testing**
  - [ ] Single policy, deterministic scenario
  - [ ] Multiple policies, verify estate aggregation
  - [ ] Stress scenario: negative estate behavior
  - [ ] Bonus declaration constraints enforced

### Testing With-Profits Models

#### Test 1: Estate Aggregation

```python
def test_estate_aggregation():
    """Verify estate is correctly aggregated across policies."""
    af = create_test_policies(n=100)
    af = gs.expand_scenarios(af, ["DETERMINISTIC"])

    # Run one period
    result = gs.run_stepped(af, project, max_periods=1)

    # Estate should be sum of (AS - GV) * pols_if
    expected_estate = (
        (result["asset_share"] - result["guaranteed_value"]) *
        result["pols_if"]
    ).sum()

    assert abs(result["estate"].first() - expected_estate) < 1e-6
```

#### Test 2: Bonus PRE Constraints

```python
def test_bonus_pre_constraints():
    """Verify bonus can't be cut more than PRE allows."""
    # Setup with stressed estate
    af = create_stressed_scenario()

    results = []
    for year in range(10):
        result = gs.run_stepped(af, project, max_periods=12)
        bonus_rate = result["bonus_declared"].list.get(-1).mean()
        results.append(bonus_rate)
        af = result  # Continue projection

    # Verify no year-on-year cut exceeds 10%
    for i in range(1, len(results)):
        if results[i-1] > 0:
            cut_pct = (results[i-1] - results[i]) / results[i-1]
            assert cut_pct <= 0.10 + 1e-6, f"Year {i}: cut {cut_pct:.1%} exceeds PRE"
```

#### Test 3: Terminal Bonus MVA

```python
def test_terminal_bonus_mva():
    """Verify MVA applied correctly when estate stressed."""
    # Scenario 1: Healthy estate
    af_healthy = create_scenario(estate=1_000_000)
    result_healthy = gs.run_stepped(af_healthy, project, max_periods=12)

    # Scenario 2: Stressed estate
    af_stressed = create_scenario(estate=-100_000)
    result_stressed = gs.run_stepped(af_stressed, project, max_periods=12)

    # Surrender terminal bonus should be lower in stressed scenario
    tb_healthy = result_healthy["terminal_bonus_paid"].list.sum().sum()
    tb_stressed = result_stressed["terminal_bonus_paid"].list.sum().sum()

    assert tb_stressed < tb_healthy, "MVA should reduce terminal bonus in stressed estate"
```

### When to Use This Pattern

**Use with-profits pattern when:**
- Policies share a common estate/surplus
- Bonus rates are declared fund-wide (not per-policy)
- Management actions depend on aggregate fund health
- Smoothing spreads returns across time via estate
- Regulatory constraints (PRE) apply to bonus changes

**Don't use this pattern for:**
- Unit-linked with individual GMAB (no shared state)
- Universal life (account value is per-policy only)
- Variable annuities without fund-level guarantees

## Open Questions

### 1. Nested Loops for Inner Stochastic

For hedge effectiveness testing, need inner risk-neutral scenarios within outer real-world:

```python
@gs.per_period(...)
def project(af, t):
    # Every period, recalculate hedge Greeks with 1000 inner scenarios
    inner_pvs = gs.run_inner_stochastic(af, af.fund_value, inner_scenarios=1000)
    af.delta = inner_pvs.sensitivity_to("equity")
    ...
```

Defer to Phase 3?

### 2. Debugging / Tracing

How to debug period 847 of 1200?

```python
gs.run_stepped(af, project, max_periods=1200, breakpoint_at=847)
```

### 3. Checkpointing

For very long runs, save state to resume:

```python
gs.run_stepped(af, project, max_periods=1200, checkpoint_every=100)
# If interrupted, resume:
gs.run_stepped(af, project, max_periods=1200, resume_from="checkpoint_800.parquet")
```

### 4. Validation Against Phase 1

For products that CAN use Phase 1, stepped projection should give identical results:

```python
# Phase 1
af1.pols_if = af.decrement.projection.cumulative_survival()

# Phase 2 (should match exactly)
@gs.per_period(state=["pols_if"], ...)
def project(af, t):
    af.pols_if = af.pols_if * (1 - af.decrement)
    return af
```

Include validation tests in implementation.

## Implementation Roadmap

### Phase 2a: Core Stepped Projection (MVP)
1. Implement `@gs.per_period` decorator
2. Implement `gs.run_stepped()` executor
3. State management (carry forward between periods)
4. Basic accumulation (store all periods)
5. Integration with `expand_scenarios()`
6. Tests with simple unit-linked model

### Phase 2b: Memory & Performance
1. Configurable accumulation (every Nth period)
2. Stream-to-disk for large runs
3. Rust parallelization within periods
4. Performance benchmarks

### Phase 2c: Advanced Features
1. Multi-lag state access (t-2, t-3)
2. Checkpointing / resume
3. Debug / breakpoint support
4. GPU investigation

## References

- [RFC 27: Scenario Support](./27-scenario-support-rfc.md) - Phase 1 design
- [Scenario Primer](./27-scenario-primer.md) - Background on stochastic modeling
- [modelx Documentation](https://docs.modelx.io/) - Spreadsheet-like DAG approach
- [lifelib](https://lifelib.io/) - Reference actuarial models
- [Polars GPU](https://docs.pola.rs/user-guide/gpu-support/) - GPU acceleration constraints
