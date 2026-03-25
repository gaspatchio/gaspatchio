# Scenario Modeling

## ScenarioParams Pattern

Use a dataclass to parameterize models for stress testing:

```python
from dataclasses import dataclass, field

@dataclass
class ScenarioParams:
    # Mortality
    mortality_factor: float = 1.0
    mortality_table: str = "2017_CSO"

    # Discounting
    discount_rate: float = 0.025
    discount_factors_vector: tuple | None = None  # for term-structure

    # Lapse / surrender
    surrender_rate_yr1: float = 0.03
    surrender_rate_yr2: float = 0.03
    surrender_rate_yr3: float = 0.03
    surrender_rate_yr4plus: float = 0.03

    # Inflation
    inflation_rates: tuple = (0.02, 0.02, 0.02, 0.02, 0.02)

    # Roll-forward
    roll_forward_months: int = 12

def main(af, params=None):
    if params is None:
        params = ScenarioParams()
    # Use params.mortality_factor, params.discount_rate, etc.
```

### Scenario Runner Pattern

Keep the model function pure (per-policy calculations only). Population-level operations belong in the scenario runner:

```python
# bscr_scenarios.py
def run_scenario(scenario_name, params, model_points):
    # Population filtering (e.g., remove largest policy)
    if scenario_name == "LARGEST_CLAIM":
        largest = model_points.sort("Face amount", descending=True).head(1)
        model_points = model_points.filter(
            pl.col("Policy number") != largest["Policy number"].item()
        )

    af = ActuarialFrame(model_points)
    result = main(af, params)
    return aggregate_results(result)
```

---

## Term-Structure Discounting

For yield curve scenarios, you cannot pass a single flat rate. Pre-compute a vector of discount factors.

### Flat Rate (Simple Case)

```python
params = ScenarioParams(discount_rate=0.025)
# Model uses: af.pv = af.cf.projection.prospective_value(discount_rate=params.discount_rate)
```

### Yield Curve (Term Structure)

```python
from scipy.interpolate import CubicSpline
import numpy as np

# 1. Build the spline from annual tenors
tenors = np.arange(1, 101)  # years 1-100
rates = np.array([...])      # annual spot rates at each tenor

spline = CubicSpline(tenors, rates)

# 2. Compute monthly discount factors: v(t) = (1 + r(t))^(-t/12)
max_periods = 1200
v_full = []
for t in range(max_periods):
    query_time = (t + 1) / 12  # Note: off-by-one vs exponent
    r_t = float(spline(query_time))
    v_t = (1 + r_t) ** (-t / 12)  # t=0 gives v=1.0
    v_full.append(v_t)

# 3. Pass as pre-computed vector
params = ScenarioParams(discount_factors_vector=tuple(v_full))
# Model uses: af.pv = af.cf.projection.prospective_value(discount_factor=af.v_t)
```

### Critical Details

- **Spline query uses `(t+1)/12`** but discount exponent uses `t/12` — off-by-one between interpolation and discounting
- **At t=0, v(0) = 1.0 always** (no discounting at the first period)
- **Rate capping**: Excel models often cap rates with `MIN(rate + shock, cap)`. Check for caps before assuming the shock applies directly.

### Using Pre-Computed Factors in the Model

```python
# In model_calculation.py
if params.discount_factors_vector is not None:
    # Broadcast the vector to a list column, then slice to match projection length
    mp = af.collect()
    mp = mp.with_columns(
        pl.lit(list(params.discount_factors_vector)).alias("v_t_full")
    ).with_columns(
        pl.col("v_t_full").list.head(pl.col("proj_periods")).alias("v_t")
    )
    af = ActuarialFrame(mp)
    af.pv = af.cashflow.projection.prospective_value(discount_factor=af.v_t)
else:
    af.pv = af.cashflow.projection.prospective_value(discount_rate=params.discount_rate)
```

---

## Population Scope

When comparing against regulatory targets (EBS, BSCR), always verify the population scope:

```python
# Excel EBS targets may only cover in-force policies
mp = mp.filter(pl.col("Policy number") <= 36)  # 36 in-force, not all 540
```

Running all policies against a 36-policy target produces ~50x inflated BEL. Document the scope prominently.

---

## BEL Formula

```python
bel = (
    pv_claims_death.sum()
    + pv_surrender_benefit.sum()
    + pv_total_expense.sum()
    - pv_premium_subtotal.sum()  # negative (income), so -sum() is positive
)
```

**Use `pv_premium_subtotal` not `pv_premium_paid`** — subtotal includes SVER (surrender value excess reserve). Missing SVER causes a systematic ~5% gap for policies with surrender values.

---

## Gaspatchio Scenario API

For built-in scenario support, look up:

```bash
uv run gspio docs "with_scenarios" -t code_example
uv run gspio docs "Table.from_scenario_files"
uv run gspio docs "batch_scenarios"
```
