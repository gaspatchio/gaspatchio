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
# The recursion reads the period AFTER it, so roll it back: reverse=True runs
# state[t] = state[t+1] * multiplier[t] + addend[t] from each policy's own last period,
# with `initial` the value after the last period (here the maturity benefit).
af.reserve = af.qx.projection.accumulate(
    initial=af.maturity_benefit,
    multiplier=af.v * (1 - af.qx),
    addend=af.v * af.qx * af.benefit,
    reverse=True,
)
```

A forward `accumulate` here would run the recursion the wrong way in time.

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
    initial=af.initial_av,
    multiplier=af.growth_factor,
    addend=af.net_cashflow,
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
af = af.join(rules_df, on="product_code", how="left")

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
# Whole months between two dates: a declared operation (positive when the argument is later)
af.duration_months = af.issue_date.date.months_between(af.valuation_date)

# Or use Gaspatchio's Excel accessor (YEARFRAC):
af.year_fraction = af.issue_date.excel.yearfrac(af.valuation_date)
```

A date *part* — year, month, day — has no declared form in 1.0; it is read through the
escape, `af.issue_date.polars_native().dt.year()`, which records the line `engine_native`: it
runs only on Polars, and so does every calculation that reads it. Reach for it only where no
declared operation says the same thing: `months_between` is exactly the year-and-month
arithmetic, `(year2 - year1) * 12 + (month2 - month1)`, written as one declared operation.

---

### 8. Raw Polars Row Operations on a Timeline Frame

**Actuarial example**: a running total or a shift written as a Polars window inside an accessor.

**Naive approach** (wrong numbers, not just slow — and refused):
```python
# WRONG: on a frame with a projection timeline the rows are policies
af.cum = af.rate * pl.col("reserve").cum_sum()        # reserve holds one value per period
af.sa_prev = af.sum_assured.projection.previous_period()  # one value per policy
```

**Why it's wrong**: on a frame with a projection timeline the rows are policies, so anything
that would read down the rows — a period method on a per-policy column, a raw Polars row
operation over a per-period column, a statistic taken off a table read — is refused, and so is
an unnamed `with_columns`/`select` expression that would silently overwrite the column it
reads. Taken down the rows, each policy would get the previous policy's value.

**Correct approach**: work inside each policy's own list — the declared operation where one
exists (`af.reserve.cum_sum()`, `.projection.previous_period()`), or
`.list.eval(pl.element().cum_sum())` inside a Polars-expression accessor body — and make a
per-policy value per-period first (`.projection.broadcast_to_periods()`).

---

### 9. A Table Read Inside a Polars Expression

**Actuarial example**: an accessor that takes a mortality lookup and post-processes it in
`pl.Expr`.

**Naive approach** (refused):
```python
# WRONG: the read ends up inside an expression the framework cannot see into
af.q = mort.lookup(age=af.age).risk.hazard_rate(a=1.0, b=1.0)   # a pl.Expr body
af.q = mort.lookup(age=af.age).polars_native().arctan()
```

**Why it's wrong**: a read of a table, mortality table, curve or schedule must be its own
step. Inside an expression the framework cannot see into it is refused, because the model's
fingerprint would not move when the table did.

**Correct approach**: continue with a declared operation (an accessor body composed from the
proxy's own operations is one), or store the read as its own column and continue from that:
`af.q_read = mort.lookup(age=af.age)`, then `af.q = af.q_read.polars_native().arctan()`.

---

## Summary Rule

If you find yourself writing any of these, stop:

- `for` loop over rows, policies, or timesteps
- `map_elements(lambda ...)`
- `.apply(func)`
- `.iter_rows()`
- Python `dict` used as a lookup table per row
- `datetime` or `relativedelta` per row

The correct approach is always: use Gaspatchio's declared operations and accessors, use `Table.lookup()`, or — where nothing is declared — compose Polars expressions inside each policy's list, knowing the line records `engine_native`.
