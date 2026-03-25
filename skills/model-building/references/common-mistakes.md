# Common Mistakes

These are real failures from actual model-building sessions, ranked by frequency and severity. Each entry shows the wrong approach and the correct fix.

---

## 1. Guessing Method Signatures (~70% Error Rate)

Agents get gaspatchio method signatures wrong most of the time when guessing.

```bash
# ALWAYS do this first
uv run gspio docs "<method name>"
```

---

## 2. `when().then(scalar).otherwise(list_column)` — Runtime Crash

```python
# WRONG — crashes with "Unsupported combination of list/scalar inputs"
af.cso = when(af.age > 99).then(1.0).otherwise(af.cso_table)

# RIGHT — arithmetic masking
af.flag = when(af.real_attained_age > 99).then(1.0).otherwise(0.0)
af.cso = af.cso_table * (1 - af.flag) + 1.0 * af.flag
```

See [conditionals-and-lists.md](conditionals-and-lists.md) for full details.

---

## 3. `projection_end_value=99` — Truncated Projection

```python
# WRONG — truncates final year, ~3% BEL gap
af = af.date.create_projection_timeline(projection_end_value=99, ...)

# RIGHT
af = af.date.create_projection_timeline(projection_end_value=100, ...)
```

---

## 4. `proj_year` vs `year` — Stress Scenarios Silently Wrong

```python
# WRONG — policy year, NEVER == 1 for established in-force policies
af.lapse_rate = when(af.year == 1).then(0.50).otherwise(af.base_lapse)

# RIGHT — projection year, fires for ALL policies in first 12 months
af.lapse_rate = when(af.proj_year == 1).then(0.50).otherwise(af.base_lapse)
```

---

## 5. `ceil(t/12)` for Projection Year — Leap Year Bug

```python
# WRONG — leap year 2028 causes 1-month offset, compounds to 21% under stress
af.proj_year = (af.t / 12.0).ceil()

# RIGHT — YEARFRAC-based
af.proj_year = af.first_proj_date.excel.yearfrac(af["date"], 3).ceil().clip(lower_bound=1)
```

---

## 6. `python3` Instead of `uv run python3`

```bash
# WRONG — ModuleNotFoundError: No module named 'polars'
python3 -c "import polars as pl; ..."

# RIGHT
uv run python3 -c "import polars as pl; ..."
```

---

## 7. `--policy-id` Flag vs Positional Argument

```bash
# WRONG — "No such option: --policy-id"
uv run gspio run-single-policy model.py data.parquet --policy-id 123

# RIGHT — POLICY_ID is positional
uv run gspio run-single-policy model.py data.parquet 123
```

`--policy-id-column` is a separate option that specifies which column contains the policy identifier.

---

## 8. Importing Model Directories as Python Packages

```python
# WRONG — model directories are NOT packages
from my_model import model_calculation
import my_model.model_calculation as mc

# RIGHT — use importlib for file-based imports
import importlib.util
spec = importlib.util.spec_from_file_location("model", "my-model/model_calculation.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.main(af)
```

---

## 9. Column Name Case Sensitivity

```python
# WRONG — Polars is case-sensitive
df.filter(pl.col("Policy_Number") > 0)  # ColumnNotFoundError

# RIGHT — check columns first
print(df.columns)  # or: uv run gspio describe data.parquet
df.filter(pl.col("Policy number") > 0)
```

Column naming varies between models. Always verify with `df.columns` or `gspio describe`.

---

## 10. Underscore-Prefixed Column Names

```python
# WRONG — ActuarialFrame rejects underscore-prefixed attribute names
af._male_flag = when(af.sex == "M").then(1.0).otherwise(0.0)

# RIGHT — use descriptive name without leading underscore
af.male_flag = when(af.sex == "M").then(1.0).otherwise(0.0)
```

---

## 11. `.collect()` During Projection (Breaking Lazy Execution)

```python
# WRONG — breaks the computation graph, may produce incorrect results
af.mort_rate = table.lookup(age=af.age)
mp = af.collect()  # <-- DON'T do this after projection timeline
mp = mp.with_columns(...)
af = ActuarialFrame(mp)

# RIGHT — .collect() is only for Phase 1 (pre-projection setup)
# After create_projection_timeline(), stay lazy
af.mort_rate = table.lookup(age=af.age)
af.derived = af.mort_rate * af.factor  # lazy expression
```

---

## 12. Transformed Age Columns Used for Guards

```python
# WRONG — issue_age includes term_offset for VBT lookups, never reaches 100
af.age_guard = when(af.issue_age < 100).then(1.0).otherwise(0.0)  # always True

# RIGHT — use raw attained age for business logic guards
af.real_attained_age = af["Policyholder issue age"] + af.year - 1
af.age_guard = when(af.real_attained_age < 100).then(1.0).otherwise(0.0)
```

When columns are transformed for lookup purposes (e.g., `term_offset`), create a separate "real" column for guards. Document which columns are lookup-adjusted vs real.

---

## 13. Missing Age-100 Mortality Guard

When mortality reaches 1.0 (ultimate age), ALL dependent calculations must be guarded:

```python
af.is_age_over_99 = when(af.real_attained_age > 99).then(1.0).otherwise(0.0)

# Guard mortality table
af.cso_table = af.cso_table * (1 - af.is_age_over_99) + af.is_age_over_99

# Guard surrender charge too — not just mortality
af.surrender_charge = af.surrender_charge * (1 - af.is_age_over_99)
```

Unguarded formulas past age 100 produce negative survival probabilities that cascade through the entire projection tail.

---

## 14. `.list.head()` on Standalone Series

```python
# WRONG — .list.head() may fail on standalone Series
series = pl.Series("v", [[1.0, 2.0, 3.0]])
result = series.list.head(2)  # can error

# RIGHT — operate within DataFrame context
df = df.with_columns(
    pl.lit([1.0, 2.0, 3.0]).alias("v_full")
).with_columns(
    pl.col("v_full").list.head(2).alias("v_sliced")
)
```

---

## 15. `pv_premium_paid` vs `pv_premium_subtotal`

```python
# WRONG — misses SVER, ~5% BEL gap for policies with surrender values
bel = pv_death + pv_surrender + pv_expense - pv_premium_paid.sum()

# RIGHT — subtotal includes SVER
bel = pv_death + pv_surrender + pv_expense - pv_premium_subtotal.sum()
```

---

## 16. 540 Policies vs 36-Policy Regulatory Targets

```python
# WRONG — 50x inflated BEL
result = run_model(all_540_policies)
compare(result, excel_ebs_36_policy_targets)

# RIGHT — filter to matching scope
in_force = mp.filter(pl.col("Policy number") <= 36)
result = run_model(in_force)
compare(result, excel_ebs_36_policy_targets)
```

Always verify the population scope of gold standard data before comparing.

---

## 17. Attribute Access Fails After Projection for with_columns-Created Columns

```python
# WRONG — column created via Polars with_columns may not be accessible via dot notation
mp = af.collect()
mp = mp.with_columns(pl.lit(12).alias("months_to_start"))
af = ActuarialFrame(mp)
af = af.date.create_projection_timeline(...)
x = af.months_to_start  # may raise AttributeError

# RIGHT — use bracket notation, or compute before projection
x = af["months_to_start"]  # bracket notation works
```

After `create_projection_timeline()`, columns created via Polars `with_columns` (rather than `af.col = expr`) are accessible via bracket notation but may fail with dot notation.

---

## 18. Broadcasting Scalars to List Columns

```python
# WRONG — confusing hack that every agent questions
af.lapse_rate = af.month * 0 + LAPSE_RATE_ANNUAL

# RIGHT — scalar assignment broadcasts automatically
af.lapse_rate = LAPSE_RATE_ANNUAL
# When combined with list columns in arithmetic (e.g., in combined_decrement),
# gaspatchio broadcasts the scalar to match the list shape.
```

Assigning a scalar directly works fine. Gaspatchio handles broadcasting when the scalar is used in arithmetic with list columns.

---

## 19. Power Operations: `scalar ** list_column` (exp/log Identity)

```python
# WRONG — Polars doesn't support scalar ** list directly
af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)  # TypeError

# RIGHT — use the identity a^b = exp(b * ln(a))
af.inflation_factor = (af.month / 12.0 * math.log(1.0 + INFLATION_RATE)).exp()
```

This is the standard pattern for computing `constant^(list_column)` without breaking the lazy pipeline. Result: `[(1.01)^(0/12), (1.01)^(1/12), (1.01)^(2/12), ...]`

See also: Level 3 base model Section 9 (expenses) for a working example.

---

## 20. Table.lookup() is exact-match

**Wrong**: Creating a Table with breakpoint ages [25, 30, 35, 40] and expecting interpolation.

**Right**: Table.lookup() requires exact key matches. Generate full-range tables (every integer age).

```python
# BAD: sparse table with gaps
mort_data = pl.DataFrame({"age": [25, 30, 35], "qx": [0.001, 0.002, 0.004]})
# lookup(age=27) will FAIL — no exact match

# GOOD: full integer-age table
ages = list(range(20, 100))
mort_data = pl.DataFrame({"age": ages, "qx": [compute_qx(a) for a in ages]})
```

If you need interpolation, pre-compute the interpolated values and include them in the table.
