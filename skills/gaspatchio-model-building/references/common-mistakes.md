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

## 2. Arithmetic-masking blends in conditional code (obsolete workaround)

```python
# Don't write this in new code — it's the old workaround.
af.flag = when(af.real_attained_age > 99).then(1.0).otherwise(0.0)
af.cso = af.cso_table * (1 - af.flag) + 1.0 * af.flag

# Just write the conditional directly. gaspatchio routes the mixed
# scalar/list branches correctly via list_conditional.
af.cso = when(af.age > 99).then(1.0).otherwise(af.cso_table)
```

The arithmetic-masking blend was the workaround for a list/scalar mismatch that no longer exists (PRs #99 / #100 / #101). Reading code, the `when/then/otherwise` form is auditable; the multi-line flag-and-blend is not. See [conditionals-and-lists.md](conditionals-and-lists.md) for the rest of the story.

---

## 3. `until_value=99` — Truncated Projection

```python
# WRONG — truncates final year, ~3% BEL gap
af = af.projection.set(until="maximum_age", until_value=99, ...)

# RIGHT — projects through age 100; 99 drops the final high-mortality year
af = af.projection.set(until="maximum_age", until_value=100, ...)
```

---

## 4. `proj_year` vs `year` — Stress Scenarios Silently Wrong

```python
# WRONG — policy year, NEVER == 1 for established in-force policies
af.lapse_rate = when(af.policy_year == 1).then(0.50).otherwise(af.base_lapse)

# RIGHT — projection year, fires for ALL policies in first 12 months
af.proj_year = when(af.month == 0).then(1).otherwise((af.month + 11) // 12)
af.lapse_rate = when(af.proj_year == 1).then(0.50).otherwise(af.base_lapse)
```

Neither column exists until you derive it: the framework materialises only `af.month`.
See [timing-and-dates.md](timing-and-dates.md) for both formulas.

---

## 5. Bare `ceil(month / 12)` for Projection Year — Month 0 Is Year 0

```python
# WRONG — labels the month-0 boundary year 0, so a `proj_year == 1` shock skips it
af.proj_year = (af.month / 12.0).ceil()

# RIGHT — the month-0 boundary belongs to year 1
af.proj_year = when(af.month == 0).then(1).otherwise((af.month + 11) // 12)
```

When reconciling to a workbook that derives the year with `YEARFRAC` on period dates,
match its formula instead — the two disagree across leap days, and under stress
inflation a one-period offset compounded to a 21% BEL gap. See
[timing-and-dates.md](timing-and-dates.md).

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

# RIGHT — from a driver script, use importlib for file-based imports
import importlib.util
spec = importlib.util.spec_from_file_location("model", "my-model/model_calculation.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.main(af)
```

That is for a script that runs the model. **Inside the model, a helper module beside it is
imported by name**, at the top of the model file — `gspio` puts the model's directory on
`sys.path` while it imports the model:

```python
# WRONG — inside model_calculation.py: a helper loaded by its path
import importlib.util
spec = importlib.util.spec_from_file_location("helpers", Path(__file__).with_name("helpers.py"))

# RIGHT — inside model_calculation.py: a plain import
import helpers
from helpers import load_tables
```

The audit record's `model.modules` lists every local module the model's import statements
name, with its sha256, and `gspio verify --model` checks each one. A helper loaded by path is
on no import statement, so it is not on the record: `verify` names the call and reports the
modules as "could not be checked" (exit 4), and an edit to that helper would go unseen.

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

# RIGHT — after af.projection.set(), stay lazy
af.mort_rate = table.lookup(age=af.age)
af.derived = af.mort_rate * af.factor  # lazy expression
```

The collect-and-rebuild round-trip above is wrong in Phase 1 too, for a different reason: `ActuarialFrame(af.collect())` throws away everything the frame knew about itself — how each column was calculated, which projection axis it was on, which columns were inputs. To freeze the setup at the end of Phase 1, use `af = af.materialize()`, which freezes the values and keeps the frame.

Where the values genuinely have to leave the frame — a numpy generator, an enrichment routine that only speaks Polars — name the frame they came out of on the way back: `af = ActuarialFrame(values, continue_from=af)`. Every column still holding the values the model's calculations produced keeps its lineage; whatever the trip changed or added is recorded as data arriving at that point, with the line it came back on.

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
# Guard mortality table — replace it with 1.0 once age exceeds 99
af.cso_table = (
    when(af.real_attained_age > 99).then(1.0).otherwise(af.cso_table)
)

# Guard surrender charge too — not just mortality
af.surrender_charge = (
    when(af.real_attained_age > 99).then(0.0).otherwise(af.surrender_charge)
)
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
# WRONG — a column injected by rebuilding the frame from raw Polars
mp = af.collect()
mp = mp.with_columns(pl.lit(12).alias("months_to_start"))
af = ActuarialFrame(mp)          # also discards the frame's whole history
af = af.projection.set(...)
x = af.months_to_start  # may raise AttributeError

# RIGHT — assign on the frame, then freeze the setup
af.months_to_start = 12
af = af.materialize()
af = af.projection.set(...)
x = af.months_to_start
```

Columns created by rebuilding the frame around a raw Polars result (rather than `af.col = expr` or `af.with_columns(...)`) are accessible via bracket notation — `af["months_to_start"]` always works — but may fail with dot notation. Assigning on the frame avoids the problem and keeps the calculation log; `materialize()` is how you freeze the setup without rebuilding, and `ActuarialFrame(values, continue_from=af)` is how you rebuild when the values genuinely had to leave.

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

## 19. Power operations on list columns

Both directions of `**` work directly on list-shaped operands:

```python
# scalar ** list_column — works
af.inflation_factor = (1.0 + INFLATION_RATE) ** (af.month / 12.0)

# list_column ** scalar — works
af.discount_factor = (1.0 + RATE) ** (-af.month / 12.0)

# list_column ** list_column — works
af.compound = af.growth_factor ** af.holding_periods
```

`__rpow__` and `__pow__` route through the `list_pow` plugin under the hood. The earlier exp/log identity (`(b * log(a)).exp()`) was a workaround for a limitation that no longer exists; it still computes the same value, but the operator form is what new code should use.

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

---

## 23. `Table` with Multi-String-Key Dimensions Silently Returns NaN

If your Table has 2+ string-type dimension columns (e.g., `sex`, `smoker`, `product_code`), the default `storage_mode="auto"` silently returns NaN on lookup. No error, no warning — the model runs but produces wrong results.

```python
# WRONG — silently returns NaN for multi-string-key tables
mort = Table(name="mortality", source=df,
             dimensions={"age": "age", "sex": "sex", "smoker": "smoker"},
             value="qx")

# RIGHT — explicitly use hash storage for tables with 2+ string dimensions
mort = Table(name="mortality", source=df,
             dimensions={"age": "age", "sex": "sex", "smoker": "smoker"},
             value="qx",
             storage_mode="hash")
```

**Rule**: If your Table has 2 or more string-type dimension columns, always pass `storage_mode="hash"`. If lookups return NaN unexpectedly, this is the first thing to check.

---

## 21. Writing Running Totals or Account Values with Python Loops

```python
# WRONG — Python loops over periods, defeats vectorization
running_total = 0.0
for t in range(n_periods):
    running_total = running_total * growth[t] + deposit[t]
    results.append(running_total)

# RIGHT — accumulate() handles sequential dependency per policy
af.shifted_growth = af.growth_factor.projection.previous_period(fill_value=1.0)
af.balance = af.shifted_growth.projection.accumulate(
    initial=af.opening_balance,
    multiplier=af.shifted_growth,
    addend=af.deposits,
)
```

`accumulate` computes `state[t] = state[t-1] * multiplier[t] + addend[t]` via a Rust kernel.
Polars parallelises across policies automatically. See Level 3 Step 06 and Level 4 SECTION 5 for production examples.

---

## 22. Using Python stdlib or raw Polars Instead of Gaspatchio Methods

Gaspatchio wraps common numeric operations to work on both scalar and list columns. These are available on any AF column or expression via the proxy dispatch.

```python
# WRONG — Python stdlib (breaks on list columns, can't be lazy)
import math
gst_paid = math.ceil(income * GST * 100) / 100
rounded = round(value, 2)

# RIGHT — Gaspatchio methods (work on scalar AND list columns)
af.gst_paid = (af.income * GST * 100).ceil() / 100
af.rounded = af.value.round(2)
```

| Python / Polars | Gaspatchio Equivalent | Works on Lists? |
|---|---|---|
| `math.ceil(x)` | `af.col.ceil()` | Yes |
| `math.floor(x)` | `af.col.floor()` | Yes |
| `round(x, n)` | `af.col.round(n)` | Yes |
| `abs(x)` | `af.col.abs()` | Yes |
| `math.exp(x)` | `af.col.exp()` | Yes |
| `math.log(x)` | `af.col.log()` | Yes |
| `math.sqrt(x)` | `af.col.sqrt()` | Yes |
| `scipy.stats.norm.cdf(z)`, Excel `NORM.S.DIST(z, TRUE)` | `af.z.norm_cdf()` / `af.z.excel.norm_s_dist()`; `NORM.DIST(x, mean, sd, TRUE)` is `((af.x - mean) / sd).norm_cdf()` | Yes |
| `results[i-1]["col"]` | `af.col.projection.previous_period()` | Yes |
| `pl.col("x").shift(1)` | `af.x.projection.previous_period()` | Yes |
| `pl.col("x").cum_sum()` | `af.x.cum_sum()` — applies within each policy's list; a running balance is `initial + af.x.cum_sum()`, no `accumulate` needed | Yes |

**Key insight:** `ceil()`, `round()`, `norm_cdf()` and the other element-wise methods work on **both** list columns and scalar columns. The period methods — `previous_period()`, `accumulate()` — work within each policy's list; on a scalar column they run *across rows*, which is what a fund-level frame with one row per year wants (Phase 4) and is refused on a frame with a projection timeline, where the rows are policies (#26).

`af.z.norm_cdf()` is Φ(z), the standard normal distribution function, accurate to 1e-12
relative and recorded as a core operation that every engine runs. There is no inverse in 1.0:
for a constant fixed before the projection, such as the 99.5% point of a capital shock,
compute it in setup with `statistics.NormalDist().inv_cdf(0.995)` and use the number. The
density is written in core operations: `(-af.z**2 / 2).exp() / (2 * math.pi) ** 0.5`.

---

## 24. Reaching for `.polars_native()` Without Counting the Cost

A line written through `.polars_native()` records as `engine_native`: it runs only on Polars,
and so does every calculation that reads it — `af.graph.tiers()` (or `gspio graph tiers`)
names the line, and `gspio validate --engine jax` names it and every calculation that reads it. Prefer the declared form where one
exists:

| Need | Declared form (core) |
|---|---|
| Reverse each policy's list | `af.x.list.reverse()` |
| Replace a NaN with a number | `af.x.fill_nan(0.0)` |
| Φ, the standard normal distribution function | `af.z.norm_cdf()` |
| A recursion rolled back from the last period | `af.x.projection.accumulate(..., reverse=True)` |
| A band test (Polars' `is_between`) | `(af.x >= lo) & (af.x <= hi)` |
| A power with a list exponent | `base ** af.month` — no cast, no `log`/`exp` |

Where no declared form exists — a date part (`.dt.year()`), a reverse running maximum — the
escape is the honest route; check `af.graph.tiers()` afterwards so you know which lines it
reached. A declared name written through the escape is refused (`'round' as you have written
it is already in gaspatchio's vocabulary …`): drop `.polars_native()` from that line.

---

## 25. Kind Refusals: Two Kinds of Value on One Line

A line that would make Polars convert one kind of value into another — a number filled with
text, branches of two kinds, a date compared with a number, a flag shifted with a numeric fill
— is refused where it is written, naming the conversion to write instead; a flag in arithmetic
reads 1.0 or 0.0.

```python
# REFUSED — each at the assignment, each naming its move
af.x2 = af.x.fill_null("none")                           # text fill on a decimal
af.x3 = when(af.age > 40).then(af.x).otherwise("n/a")    # a decimal branch and a text branch
af.x4 = af.issue_date > 2020                             # a date against a whole number
af.x5 = af.status.replace({"IF": 1})                     # a number substituted into text
af.x6 = af.status.is_in([1])                             # a number member tested against text
af.x7 = af.status.fill_nan(0.0)                          # text never holds a NaN

# RIGHT — say the kind you mean
af.label = when(af.age > 40).then(af.x.to_text()).otherwise("n/a")
af.after = af.issue_date > date(2021, 1, 1)
af.code = af.status.replace({"IF": "INFORCE"})           # replace("IF", "INFORCE") is the same mapping
af.smoker_load = af.smoker * 100.0                       # a flag reads 1.0 / 0.0 in arithmetic
```

A shift of a Boolean column needs a flag fill (`previous_period(fill_value=False)`), and a
Boolean `accumulate` operand is refused — write the amount it stands for,
`when(af.flags).then(1.0).otherwise(0.0)`. A comparison stored on a timeline frame
(`af.flag = af.month > 0`) is held as 1.0/0.0, so these two meet only a Boolean list column
that arrived as one.

---

## 26. Row Guards: Reading Down the Policies

On a frame with a projection timeline the rows are policies, so anything that would read down
the rows — a period method on a per-policy column, a raw Polars row operation over a
per-period column, a statistic taken off a table read — is refused, and so is an unnamed
`with_columns`/`select` expression that would silently overwrite the column it reads.

```python
# REFUSED on a timeline frame
af.sa_prev = af.sum_assured.projection.previous_period()   # one value per policy
af = af.with_columns(pl.col("age") * 2)                      # would overwrite "age" unnamed

# RIGHT
af.sa_pp = af.sum_assured.projection.broadcast_to_periods()  # per-period first ...
af.sa_prev = af.sa_pp.projection.previous_period()           # ... then shift it
af.age2 = af.age * 2                                          # name the column it writes
```

If the calculation really does run down the model points, take it on a per-policy column, or
open the explicit escape, `af.<column>.polars_native()`, which records the line as
`engine_native` (#24).

---

## 27. A Table Read Inside an Engine Expression

A read of a table, mortality table, curve or schedule must be its own step: inside an
expression the framework cannot see into it is refused, because the model's fingerprint would
not move when the table did — continue with a declared operation, or store the read as its own
column and continue from that.

```python
# REFUSED — the read sits inside Polars' own expression
af.q = mort.lookup(age=af.age).polars_native().arctan()

# RIGHT — a declared operation keeps the read ...
af.q_f = mort.lookup(age=af.age).to_float()
af.q_clean = mort.lookup(age=af.age).fill_nan(0.0)
# ... or store the read first, then escape from the column
af.q_read = mort.lookup(age=af.age)
af.q = af.q_read.polars_native().arctan()
```

A read keyed by values rather than a column of the frame (`mort.lookup(age=40)`) answers only
Polars' own methods, so even a declared operation chained on it is refused: store it first,
`af.q40_read = mort.lookup(age=40)`, then `af.q40 = af.q40_read.fill_nan(0.0)`. A statistic
over each policy's periods is the declared `.list.sum()` (on the read or a stored column); a
bare `.sum()` on a read is not declared, and `.polars_native().sum()` on the read is refused
for the reason above.

---

## 28. `fill_nan`: Declared for a Number, Escaped for a Null

`af.x.fill_nan(0.0)` — or a fill from another column, `af.x.fill_nan(af.y)` — is a declared,
portable operation, including straight after a table read
(`mort.lookup(age=af.age).fill_nan(0.0)`); `fill_nan(None)` is not declared and stays on the
escape, `af.x.polars_native().fill_nan(None)`, which records `engine_native`. On text or a
flag it is refused (#25): a missing value there is a null, and its fill is `fill_null(...)`.

---

## 29. `previous_period()` Zeroes a Running Product

```python
# WRONG — the default fill is 0.0, so the product is 0.0 from the first period on
af.surv = af.p.projection.previous_period().cum_prod()          # [0.0, 0.0, 0.0]

# RIGHT — open the product at 1.0
af.surv = af.p.projection.previous_period(fill_value=1.0).cum_prod()   # [1.0, 0.99, 0.9702]
```

The default `fill_value=0.0` suits amounts (no cashflow before the start); a factor, a survival
probability or a growth multiplier opens at `1.0`.
