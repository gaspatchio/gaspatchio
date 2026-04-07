## Anti-Patterns: What Never to Do

Every pattern below is tempting. Every one is wrong. Each causes 20-1000x performance degradation.

---

### 1. Python For-Loop Over Time Steps

**Actuarial example**: Reserve recursion `V(t) = v * (q * benefit + p * V(t+1))`

**Naive approach** (100-500x slower):
```python
# WRONG: Python loop backward through time
reserves = [0.0] * (n_periods + 1)
reserves[-1] = maturity_benefit
for t in range(n_periods - 1, -1, -1):
    reserves[t] = v * (qx[t] * benefit + (1 - qx[t]) * reserves[t + 1])
```

**Why it's slow**: Each iteration crosses the Python-Rust boundary. For 100K policies x 120 months = 12 million Python iterations vs one Rust kernel call.

**Correct approach**:
```python
# Use Gaspatchio's accumulate kernel (runs in Rust, parallelized across policies)
af.reserve = af.discount_factor.projection.accumulate(
    initial="maturity_benefit",
    multiply="survival_factor",
    add="benefit_cashflow",
)
```

---

### 2. If/Else Per Policy

**Actuarial example**: Product-specific formulas

**Naive approach** (50-200x slower):
```python
# WRONG: map_elements with conditional
df.with_columns(
    pl.struct(["product_type", "sum_assured", "account_value"])
    .map_elements(lambda x: x["sum_assured"] if x["product_type"] == "endowment" else 0.0)
    .alias("maturity_benefit")
)
```

**Why it's slow**: `map_elements` converts each value to a Python object, calls a Python function, converts back. Defeats all SIMD vectorization.

**Correct approach**:
```python
# Use when/then/otherwise (runs as vectorized Polars expression)
af.maturity_benefit = (
    when(af.product_type == "endowment").then(af.sum_assured)
    .when(af.product_type == "term").then(0.0)
    .otherwise(af.account_value)
)
```

---

### 3. Dict Lookup Per Row

**Actuarial example**: Mortality table query by age and duration

**Naive approach** (200-1000x slower):
```python
# WRONG: Python dict lookup
mortality_dict = {(age, dur): rate for age, dur, rate in mortality_table}
rates = []
for i in range(len(df)):
    age = int(df["age"][i])
    dur = int(df["duration"][i])
    rates.append(mortality_dict.get((age, dur), 0.0))
```

**Why it's slow**: Python dict lookups have interpreter overhead per row. For list columns with 120 monthly ages per policy, this becomes nested loops.

**Correct approach**:
```python
# Use Gaspatchio Table with Rust-backed lookup
mortality = Table(
    name="mortality",
    source=mortality_data,
    dimensions={"age": "attained_age", "duration": "policy_duration"},
    value="qx",
)
af.qx = mortality.lookup(age=af.age_vector, duration=af.duration_vector)
```

---

### 4. Iterative Running Totals

**Actuarial example**: Account value accumulation `AV(t) = AV(t-1) * (1+r) + premium - charges`

**Naive approach** (100-500x slower):
```python
# WRONG: nested Python loops
for policy_idx in range(len(df)):
    av = initial_av[policy_idx]
    for t in range(120):
        av = av * (1 + credit_rate[policy_idx][t]) + premium[policy_idx][t]
```

**Why it's slow**: Same as anti-pattern 1. Also: `cum_sum` and `cum_prod` are built-in but cannot express `state[t] = state[t-1] * M[t] + A[t]`.

**Correct approach**:
```python
# For simple cumulative products (survival):
af.tpx = af.qx.projection.cumulative_survival()

# For linear recurrence (AV with interest + cashflows):
af.av = af.growth_factor.projection.accumulate(
    initial="initial_av",
    multiply="growth_factor",
    add="net_cashflow",
)
```

---

### 5. For Policy in Policies

**Actuarial example**: Any per-policy processing

**Naive approach** (1000x+ slower):
```python
# WRONG: iterate over policies
results = []
for policy_id in df["policy_id"].unique():
    policy_data = df.filter(pl.col("policy_id") == policy_id)
    result = calculate_reserve(policy_data)
    results.append(result)
final_df = pl.concat(results)
```

**Why it's slow**: Creates N DataFrame copies. Prevents all parallelism. This is always wrong in Polars.

**Correct approach**: Every operation in Gaspatchio works on all policies at once. The ActuarialFrame stores each policy's projection as a list within a single row. Operations apply element-wise to every policy simultaneously. There is never a reason to loop over policies.

---

### 6. map_elements with Lambda

**Actuarial example**: String categorization, product code mapping

**Naive approach** (20-100x slower):
```python
# WRONG: lambda per row
product_rules = {"TERM20": 0.05, "WL": 0.08, "UL": 0.10}
df.with_columns(
    pl.col("product_code")
    .map_elements(lambda x: product_rules[x])
    .alias("expense_loading")
)
```

**Why it's slow**: Converts each string to a Python object and back. Defeats Polars' optimized string kernels.

**Correct approach**:
```python
# For few values: when/then
af.expense_loading = (
    when(af.product_code == "TERM20").then(0.05)
    .when(af.product_code == "WL").then(0.08)
    .otherwise(0.10)
)

# For many values: join against a lookup table
rules_df = pl.DataFrame({"product_code": ["TERM20", "WL", "UL"], "expense_loading": [0.05, 0.08, 0.10]})
af._df = af._df.join(rules_df.lazy(), on="product_code", how="left")

# Or use a Gaspatchio Table:
expense_table = Table(name="expenses", source=rules_df, dimensions={"product_code": "product_code"}, value="expense_loading")
af.expense_loading = expense_table.lookup(product_code=af.product_code)
```

---

### 7. Python Datetime Loops

**Actuarial example**: Calculating policy duration from issue date

**Naive approach** (50-200x slower):
```python
# WRONG: Python datetime per row
from dateutil.relativedelta import relativedelta
df.with_columns(
    pl.struct(["issue_date", "valuation_date"])
    .map_elements(lambda x: relativedelta(x["valuation_date"], x["issue_date"]).months)
    .alias("duration_months")
)
```

**Why it's slow**: Converts Polars temporal types to Python datetime objects and back. `relativedelta` is pure Python.

**Correct approach**:
```python
# Use Polars temporal expressions (SIMD on Arrow date representation)
af.duration_months = (
    (af.valuation_date.dt.year() - af.issue_date.dt.year()) * 12
    + (af.valuation_date.dt.month() - af.issue_date.dt.month())
)

# Or use Gaspatchio's date accessor:
af.year_fraction = af.issue_date.date.year_frac(af.valuation_date)
```

---

## Summary Rule

If you find yourself writing any of these, stop:

- `for` loop over rows, policies, or timesteps
- `map_elements(lambda ...)`
- `.apply(func)`
- `.iter_rows()`
- Python `dict` used as a lookup table per row
- `datetime` or `relativedelta` per row

The correct approach is always: compose Polars expressions, use Gaspatchio accessors, or use `Table.lookup()`.
