# Migration Guide — Projection Axis API

This document is for actuaries with existing models on the pre-`af.projection.set(...)` API. It shows the rewrite for every common pattern, grounded in the actual tutorial models in `tutorial/`.

The migration is **mechanical** — every existing pattern has a one-to-one rewrite. There is no shim, no deprecation period, no transitional behaviour. Read top-to-bottom; run the diffs against your code.

**TL;DR**

| If you have | Replace with |
|---|---|
| `af.date.create_projection_timeline(...)` | `af.projection.set(...)` |
| `Schedule.from_inception(...)` directly + pass via `schedule=` to `rollforward(...)` | `af.projection.set(schedule=sched)`; assign `af.contract_boundary = af.projection.contract_boundary()`; then `rollforward(..., contract_boundary=pl.col("contract_boundary"))` |
| `Schedule.from_calendar_grid(...)` for synthetic / pattern demo | `af.projection.set(start_date=..., n_periods=..., frequency=...)` |
| `rollforward(..., schedule=sched)` | Call `af.projection.set(...)` first; drop `schedule=` from the rollforward call |

The rest of this doc walks the patterns one at a time.

---

## 1. The headline change

`af.date.create_projection_timeline(...)` is **deleted**. There is no shim. Calling it raises `AttributeError`.

Replace with `af.projection.set(...)`. The kwargs map cleanly:

| Old kwarg | New kwarg |
|---|---|
| `valuation_date=` | `valuation_date=` (unchanged) |
| `projection_end_type="maximum_age"` | `until="maximum_age"` |
| `projection_end_value=100` | `until_value=100` |
| `projection_frequency="monthly"` | `frequency="monthly"` |
| `issue_age_column="issue_age"` | `issue_age_column="issue_age"` (unchanged) |
| `projection_start_offset_months=N` | (deprecated — express via `start_date=` if you need it) |
| `store_start_date=True` | always-on; not configurable |
| `store_end_date=True` | always-on; not configurable |
| `output_column="proj_dates"` | (removed — `proj_dates` is now lazy via `af.projection.period_dates()`) |

Frame mutation: the new method **returns a new frame** (Polars convention). You must rebind:

```python
# OLD — mutates in place
af.date.create_projection_timeline(...)

# NEW — returns new frame
af = af.projection.set(...)
```

If you forget to rebind, your model silently runs without projection metadata; the next `rollforward(...)` call will fail with a clear error.

---

## 2. Pattern: simple monthly projection to maximum age

**Before** (from `tutorial/level-3-mini-va/base/model.py`):

```python
af = af.date.create_projection_timeline(
    valuation_date=VALUATION_DATE,
    projection_end_type="term_months",
    projection_end_value=PROJECTION_MONTHS,
    projection_frequency="monthly",
    output_column="projection_date",
)
```

**After:**

```python
af = af.projection.set(
    valuation_date=VALUATION_DATE,
    until="term_months",
    until_value=PROJECTION_MONTHS,
    frequency="monthly",
)
# projection_date column is now af.projection.period_dates() — lazy
# To get the same eager column behaviour:
af.projection_date = af.projection.period_dates()
```

The three columns `projection_start_date`, `projection_end_date`, `num_proj_months` are still stamped automatically. The `proj_dates` (or `projection_date`) column is no longer eager — assign it explicitly if you want it materialised in `af.collect()`.

---

## 3. Pattern: per-policy projection from a column

**Before:**

```python
af = af.date.create_projection_timeline(
    valuation_date=val_date,
    projection_end_type="term_months",
    projection_end_value="remaining_term_months",   # column name
    projection_frequency="monthly",
)
```

**After:**

```python
af = af.projection.set(
    valuation_date=val_date,
    until="term_months",
    until_value="remaining_term_months",   # column name — unchanged
    frequency="monthly",
)
```

`until_value=` accepts the same shapes as `projection_end_value=` did:
- `int` (uniform across policies)
- `str` (column name for per-policy)
- `pl.Expr` (computed expression for per-policy)

---

## 4. Pattern: typed Schedule input (the L3 typed tutorial)

**Before** (from `tutorial/level-3-mini-va-typed/base/model.py`):

```python
schedule = Schedule.from_calendar_grid(
    start_date=VALUATION_DATE,
    n_periods=PROJECTION_MONTHS,
    frequency="1M",
    day_count=OneTwelfth(),
)
period_widths = schedule.year_fractions()
t_years_list = [0.0, *list(itertools.accumulate(period_widths))]
```

**After:**

```python
schedule = Schedule.from_calendar_grid(
    start_date=VALUATION_DATE,
    n_periods=PROJECTION_MONTHS,
    frequency="1M",
    day_count=OneTwelfth(),
)
af = af.projection.set(schedule=schedule)
# year_fractions and t_years are now accessor methods:
period_widths = af.projection.year_fractions()   # ExpressionProxy
t_years        = af.projection.t_years()           # ExpressionProxy — already cumulative
```

`Schedule` itself is unchanged — `from_calendar_grid(...)` and `from_inception(...)` still construct typed objects with the same kwargs, the same `canonical_form()`, the same `source_sha()`. What changes is how you wire it into the frame: pass it via `af.projection.set(schedule=...)` instead of via the rollforward's `schedule=` kwarg.

The manual `[0.0, *itertools.accumulate(...)]` cumulative trick is no longer needed — `af.projection.t_years()` returns the cumulative-year-fractions vector directly (length `n_periods + 1`).

---

## 5. Pattern: rollforward with explicit Schedule

**Before** (from `tutorial/rollforward-patterns/01_single_state_fund.py`):

```python
n_periods = 12
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),
    n_periods=n_periods,
    frequency="1M",
)
# ... build af ...
b = af.projection.rollforward(
    states={"av": pl.col("av_init")},
    schedule=sched,
)
```

**After:**

```python
n_periods = 12
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),
    n_periods=n_periods,
    frequency="1M",
)
# ... build af ...
af = af.projection.set(schedule=sched)
af.contract_boundary = af.projection.contract_boundary()  # materialize as column
b = af.projection.rollforward(
    states={"av": pl.col("av_init")},
    contract_boundary=pl.col("contract_boundary"),
)
```

Two changes:
1. The `schedule=sched` kwarg moves from the rollforward call to the new `af.projection.set(schedule=sched)` call.
2. The contract-boundary mask is materialized onto the frame as a column, then passed to `rollforward(..., contract_boundary=pl.col("contract_boundary"))`. (Previously the kernel handled boundary internally based on the schedule + per-policy term info; now it reads the mask from the frame.)

> **Why the extra `af.contract_boundary = ...` step?** The rollforward kernel reads `contract_boundary=` as a column reference (`pl.col("name")`), not as a list-literal expression. This is so the IR can capture a single column slot per policy. To pass the boundary mask, materialize it as a column on the frame first, then reference that column in the rollforward call. The intermediate column name (`contract_boundary` here) is yours to pick — any non-conflicting name works.

If your model genuinely has unbounded projection (no contract end — demographic forecasts, multi-decade pricing studies), omit `contract_boundary=`.

**`is_in_force()` vs `contract_boundary()` — the semantic distinction.** Both methods return a per-row `List<Boolean>` of length `n_periods`, and they are exact negations of one another. They serve different audiences:

- `af.projection.is_in_force()` — `True` means the period is **active** (contract still in force). Use it for actuarial expressions that read naturally as "is this policy alive at t?" — expected lives in-force, exposure-weighted aggregations, period-by-period premium counts.
- `af.projection.contract_boundary()` — `True` means the period is **terminated**. This matches the rollforward kernel's `contract_boundary=` semantics (True at period t zeros that period and every later period). Use it for the rollforward boundary mask only. Passing `is_in_force()` directly to `contract_boundary=` would zero every period — the opposite of what you want.

---

## 6. Pattern: synthetic projection (no policies)

**Before** (from `tutorial/rollforward-patterns/01_single_state_fund.py`):

```python
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),
    n_periods=12,
    frequency="1M",
)
af = ActuarialFrame({"id": ["demo"]})
b = af.projection.rollforward(states={...}, schedule=sched)
```

**After (option 1 — kwargs path; cleanest for synthetic cases):**

```python
af = ActuarialFrame({"id": ["demo"]})
af = af.projection.set(
    start_date=date(2025, 1, 31),
    n_periods=12,
    frequency="monthly",
)
b = af.projection.rollforward(
    states={...},
    # Synthetic / unbounded — omit contract_boundary entirely. If you want
    # an explicit no-op mask for symmetry with non-synthetic call sites:
    # af.contract_boundary = af.projection.contract_boundary()
    # contract_boundary=pl.col("contract_boundary"),
)
```

**After (option 2 — typed path; keep if you want the explicit Schedule for parity with non-synthetic tutorials):**

```python
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),
    n_periods=12,
    frequency="1M",
)
af = ActuarialFrame({"id": ["demo"]}).projection.set(schedule=sched)
af.contract_boundary = af.projection.contract_boundary()  # materialize as column
b = af.projection.rollforward(
    states={...},
    contract_boundary=pl.col("contract_boundary"),
)
```

Both work. The kwargs path is slightly less ceremonious for pattern demos. For pure synthetic / unbounded projections you can omit `contract_boundary=` entirely — the kernel runs all periods.

---

## 7. Pattern: anniversary-aware projection (new in this release)

`until="next_anniversary"` is added by this release for products whose natural projection horizon is a contract anniversary rather than a calendar duration:

```python
af = af.projection.set(
    valuation_date=date(2025, 1, 1),
    until="next_anniversary",
    until_value=1,                 # 1 = next anniversary; 2 = anniversary after
    inception_column="policy_inception",   # default; override if your column is named differently
    frequency="monthly",
)
```

Useful for term-renewable life, anniversary-trigger riders, group renewable products. If your existing model approximates this with `term_months` + custom math, you can simplify it now.

---

## 8. Pattern: frequency strings

Both vocabularies are accepted:

```python
af = af.projection.set(..., frequency="monthly")    # tutorial-recommended
af = af.projection.set(..., frequency="1M")          # also works (Schedule-shorthand)
```

Map:

| English (recommended) | Schedule-shorthand |
|---|---|
| `"monthly"` | `"1M"` |
| `"quarterly"` | `"3M"` |
| `"semi-annual"` | `"6M"` |
| `"annual"` | `"1Y"` |
| `"weekly"` | `"1W"` |
| `"daily"` | `"1D"` |

You don't need to translate. Pick whichever matches the rest of your codebase.

---

## 9. Pattern: derived columns previously stamped by `create_projection_timeline`

The old API stamped four columns on `set`. Three remain eager; one is now lazy:

| Old eager column | New status |
|---|---|
| `projection_start_date` | Still eager. Still stamped on `set()`. |
| `projection_end_date` | Still eager. Still stamped on `set()`. |
| `num_proj_months` | Still eager. Still stamped on `set()`. |
| `proj_dates` (or whatever `output_column=` was) | **Lazy.** Access via `af.projection.period_dates()`; assign explicitly if you want it materialised. |

If your code reads `af.proj_dates` directly:

```python
# OLD — proj_dates was eagerly stamped
deaths = af.proj_dates.list.lengths()

# NEW — assign explicitly OR use the accessor
af.proj_dates = af.projection.period_dates()
deaths = af.proj_dates.list.lengths()
# OR — skip the assignment if you only use it once
deaths = af.projection.period_dates().list.lengths()
```

---

## 10. Pattern: deriving t_years for Curve.discount_factor

A common pattern in the typed-input tutorial was the manual cumulative trick:

```python
period_widths = schedule.year_fractions()
t_years_list = [0.0, *list(itertools.accumulate(period_widths))]
discount_factors = [curve.discount_factor(t) for t in t_years_list]
```

After migration:

```python
af = af.projection.set(schedule=schedule)
af.t_years = af.projection.t_years()
af.discount_factor = af.t_years.map_elements(curve.discount_factor, return_dtype=pl.Float64)
```

`af.projection.t_years()` returns the cumulative year-fractions list of length `n_periods + 1` (i.e. `[0.0, dt[0], dt[0]+dt[1], ...]`) — exactly what `Curve.discount_factor(t)` expects. The off-by-one bookkeeping the old README flagged disappears entirely.

---

## 11. Common errors during migration

### `TypeError: schedule= is no longer accepted on rollforward()`

You passed `schedule=` to `af.projection.rollforward(...)`. Move it to `af.projection.set(schedule=...)` upstream.

### `ValueError: This frame has no projection. Call af.projection.set(...) before rollforward().`

You called `af.projection.rollforward(...)` without first declaring the projection on the frame. Add `af = af.projection.set(...)` before the rollforward call.

### `AttributeError: 'DateFrameAccessor' object has no attribute 'create_projection_timeline'`

You're still calling the old method. Rewrite per §1.

### `ValueError: schedule= cannot be combined with valuation_date / until / start_date / n_periods.`

You passed both `schedule=` and kwargs to `af.projection.set(...)`. Pick one.

### Numbers in the lapse month differ from before

You shouldn't see this — full-period termination semantics is unchanged under this migration. If you do, file a bug. (Mid-period termination is tracked in GSP-98 and is opt-in only.)

---

## 12. Tutorial migrations on this branch

The following tutorials were migrated as part of this release:

| Tutorial | Pattern |
|---|---|
| `level-1-hello-world/steps/01-projections/` | §2 (simple monthly to term) |
| `level-1-hello-world/steps/02-survival/` | §2 |
| `level-1-hello-world/steps/03-time-shifting/` | §2 |
| `level-3-mini-va/base/` | §2 |
| `level-3-mini-va/steps/*/` | §2 (all six steps) |
| `level-3-mini-va-typed/base/` | §4 + §10 (typed Schedule pass-through) |
| `level-3-mini-va-typed/steps/*/` | §4 + §10 |
| `level-3-mini-va-typed/steps/07-anniversary-aware/` | §7 (now uses `until="next_anniversary"` directly) |
| `level-5-scenarios/base/` | §2 |
| `level-5-scenarios-typed/` | §4 |
| `rollforward-patterns/01_single_state_fund.py` | §6 option 1 |
| `rollforward-patterns/02_multistate_ratchet.py` | §6 option 1 |
| `rollforward-patterns/03_lapse_stop.py` | §6 option 1 |

Each tutorial commit is a self-contained diff you can read for additional examples.

---

## 13. What did NOT change

- `Schedule`, `Calendar`, `DayCount`, `BusinessDayConvention` — all still public, all still importable from `gaspatchio_core`
- `Schedule.from_calendar_grid(...)` and `Schedule.from_inception(...)` — same kwargs, same return type
- `Schedule.canonical_form()` and `source_sha()` — same shape, same bytes for equivalent inputs
- `af.date.create_timeline(start_col, end_col, ...)` — different verb, untouched
- `af.date.add_duration(...)` — untouched
- `af.<col>.projection.accumulate(...)` — separate primitive, untouched
- `af.<col>.projection.cumulative_survival(...)`, `previous_period(...)`, `next_period(...)`, `at_period(...)` — column-level accessors, untouched
- Rollforward fingerprints — for any model whose recipe is unchanged, `CompiledRollforward.fingerprint()` produces the same bytes pre and post migration

---

## 14. Out of scope

Two future enhancements are tracked separately:

- GSP-97 — Native per-policy `n_periods` in the kernel. Memory optimisation. Currently the boundary-mask approach is fine; that approach stays.
- GSP-98 — Mid-period termination semantics. Currently full-period only. Will be opt-in when shipped; defaults will not change without explicit user action.

Neither affects this migration.
