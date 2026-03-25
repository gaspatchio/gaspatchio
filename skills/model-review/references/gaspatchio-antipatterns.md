# Gaspatchio Model Anti-Patterns

This reference lists the 10 most common anti-patterns found in gaspatchio model code, with wrong and right examples for each. Use this during Layer 1 (Code Quality) of a model review.

---

## 1. `map_elements` / `apply` in model code (Critical)

Using `map_elements` or `apply` defeats Polars' vectorized execution engine and causes ~14x slowdowns. There is almost never a valid reason to use these in model code.

**Wrong:**
```python
af.annual_rate = af.col.map_elements(lambda x: min(x * 1.1, 0.5), return_dtype=pl.Float64)
```

**Right:**
```python
af.annual_rate = (af.base_rate * 1.1).clip(upper_bound=0.5)
```

**Wrong:**
```python
af.status = af.col.map_elements(lambda x: "lapsed" if x > 10 else "active", return_dtype=pl.Utf8)
```

**Right:**
```python
af.status = when(af.duration > 10).then(pl.lit("lapsed")).otherwise(pl.lit("active"))
```

---

## 2. Python for-loops over data rows (Critical)

Iterating over rows in Python bypasses Polars entirely. The model will be orders of magnitude slower and will not scale to production workloads.

**Wrong:**
```python
results = []
for row in df.iter_rows(named=True):
    rate = lookup_mortality(row["age"], row["sex"])
    results.append(rate)
df = df.with_columns(pl.Series("mort_rate", results))
```

**Right:**
```python
af.mort_rate = tables["mortality"].lookup(age=af.age, sex=af.sex)
```

**Wrong:**
```python
for i in range(len(df)):
    df[i, "survival"] = df[i-1, "survival"] * (1 - df[i, "mort_rate"])
```

**Right:**
```python
af.survival = af.mort_rate.projection.cumulative_survival()
```

---

## 3. Scalar/list confusion (Critical)

Gaspatchio columns in projection phase are list-typed (one list per policy, one element per time step). Passing a scalar where a list is expected (or vice versa) causes runtime crashes or silently wrong results.

**Wrong:**
```python
# Scalar in a when/then that expects a list column
af.benefit = when(af.age > 65).then(1000.0).otherwise(af.account_value)
# Crashes: "Unsupported combination of list/scalar inputs"
```

**Right:**
```python
# Wrap the scalar in a broadcast to match the list shape
af.benefit = when(af.age > 65).then(af.account_value * 0 + 1000.0).otherwise(af.account_value)
# Or better: assign the constant as a column first
af.flat_benefit = 1000.0
af.benefit = when(af.age > 65).then(af.flat_benefit).otherwise(af.account_value)
```

**Wrong:**
```python
# Using .item() or .to_list()[0] on a projection column
rate = af.mort_rate.to_list()[0]  # Extracts a single value, loses time dimension
```

**Right:**
```python
# Keep the column as-is; operate on it vectorially
af.death_cost = af.mort_rate * af.sum_assured
```

---

## 4. Inline Polars instead of `Table.lookup()` (Important)

Raw Polars joins and filters bypass gaspatchio's assumption handling, which manages dimension alignment, broadcasting, and error reporting. Use `Table.lookup()` for all assumption lookups.

**Wrong:**
```python
mort_df = pl.read_parquet("assumptions/mortality.parquet")
af_df = af.collect()
af_df = af_df.join(mort_df, left_on="age", right_on="attained_age", how="left")
af = ActuarialFrame(af_df)
```

**Right:**
```python
mort = Table(name="mortality", source=mort_df, dimensions={"attained_age": "age"}, value="rate")
af.mort_rate = mort.lookup(age=af.age)
```

---

## 5. Guessed API signatures (Important)

LLM agents get gaspatchio method signatures wrong approximately 70% of the time when guessing. Always verify with `gspio docs` before using any method.

**Wrong:**
```python
# Invented method — does not exist
af.pv = af.cashflows.discounted_value(rate=0.03, method="continuous")
```

**Right:**
```bash
# First, look it up
uv run gspio docs "prospective_value"
```
```python
# Then use the verified signature
af.pv = af.cashflows.projection.prospective_value(discount_rate=0.03)
```

**Wrong:**
```python
# Wrong parameter name — the actual parameter is discount_rate, not rate
af.pv = af.cashflows.projection.prospective_value(rate=0.03)
```

**Right:**
```python
af.pv = af.cashflows.projection.prospective_value(discount_rate=0.03)
```

---

## 6. Missing `--output-file` validation (Important)

Parsing stdout for model validation is fragile and loses type information. Always write results to parquet and inspect with `gspio describe`.

**Wrong:**
```bash
uv run gspio run-single-policy model.py data.parquet 1
# Then eyeball the terminal output
```

**Right:**
```bash
uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet
uv run gspio describe --json /tmp/result.parquet
```

---

## 7. Wrong projection accessor (Important)

Gaspatchio provides specialized accessors (`.projection.*`) for actuarial operations on list-typed columns. Using raw Polars list operations instead misses actuarial semantics (timing, decrement ordering).

**Wrong:**
```python
# Raw list operation — no actuarial timing awareness
af.survival = (1 - af.mort_rate).list.eval(pl.element().cum_prod())
```

**Right:**
```python
af.survival = af.mort_rate.projection.cumulative_survival()
```

**Wrong:**
```python
# Manual PV calculation — error-prone and misses timing conventions
af.pv = (af.cashflows * af.discount_factors).list.sum()
```

**Right:**
```python
af.pv = af.cashflows.projection.prospective_value(discount_rate=0.03)
```

---

## 8. Hardcoded assumptions (magic numbers) (Important)

Literal numbers embedded in model code are impossible to audit, difficult to change, and invisible to assumption governance. Every rate, factor, and threshold should come from a named source.

**Wrong:**
```python
af.lapse_charge = when(af.duration <= 7).then(af.account_value * 0.015).otherwise(0)
```

**Right:**
```python
af.lapse_charge_rate = tables["surrender_charges"].lookup(duration=af.duration)
af.lapse_charge = af.account_value * af.lapse_charge_rate
```

**Wrong:**
```python
af.expense = 250.0 + af.premium * 0.02
```

**Right:**
```python
EXPENSE_FIXED = params["expense_per_policy"]  # from config or assumption table
EXPENSE_PREM_RATE = params["expense_premium_rate"]
af.expense = EXPENSE_FIXED + af.premium * EXPENSE_PREM_RATE
```

---

## 9. Missing `when/then/otherwise` for conditionals (Minor)

Boolean masking (`value * (condition)`) works but is harder to read and audit than explicit `when/then/otherwise`. For simple cases it's acceptable; for complex branching logic it's a code smell.

**Wrong:**
```python
# Boolean mask — unclear intent for complex conditions
af.death_benefit = af.sum_assured * (af.in_force) + af.account_value * (1 - af.in_force) * (af.duration > 0)
```

**Right:**
```python
af.death_benefit = (
    when(af.in_force)
    .then(af.sum_assured)
    .when(af.duration > 0)
    .then(af.account_value)
    .otherwise(0)
)
```

---

## 10. No section header comments (Minor)

Models without section headers are difficult to navigate, review, and maintain. Use numbered section comments to divide the model into logical blocks.

**Wrong:**
```python
af.mort_rate = tables["mortality"].lookup(age=af.age)
af.lapse_rate = tables["lapse"].lookup(duration=af.duration)
af.survival = af.mort_rate.projection.cumulative_survival()
af.premium_income = af.premium * af.survival
af.claims = af.sum_assured * af.mort_rate
af.pv_profit = af.net_cashflow.projection.prospective_value(discount_rate=0.03)
```

**Right:**
```python
# ── SECTION 1: MORTALITY AND LAPSE RATES ──────────────────────────────
af.mort_rate = tables["mortality"].lookup(age=af.age)
af.lapse_rate = tables["lapse"].lookup(duration=af.duration)

# ── SECTION 2: SURVIVAL AND PERSISTENCY ───────────────────────────────
af.survival = af.mort_rate.projection.cumulative_survival()

# ── SECTION 3: CASHFLOWS ──────────────────────────────────────────────
af.premium_income = af.premium * af.survival
af.claims = af.sum_assured * af.mort_rate

# ── SECTION 4: PRESENT VALUES ─────────────────────────────────────────
af.pv_profit = af.net_cashflow.projection.prospective_value(discount_rate=0.03)
```
