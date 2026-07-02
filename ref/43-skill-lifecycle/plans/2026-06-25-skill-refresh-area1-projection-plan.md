# Area 1 — Projection backbone: refresh plan

> **For agentic workers:** execute via the `skill-update` loop. The grounded API
> below is verified against develop; do not write a call from memory — cross-check
> every example against `bindings/python/gaspatchio_core/accessors/projection_frame.py`
> and `tests/accessors/test_projection_set.py`.

**Goal:** Replace every skill reference to the removed `af.date.create_projection_timeline(...)`
with the current `af.projection.set(...)` API, with verified examples. This is the
Phase-2 backbone of every model and is currently *broken* (models generated under
the skills fail with `AttributeError`).

**Scope:** fix-only (the removed→new migration). New per-policy/jagged capability
is taught lightly where it clarifies; deep coverage of new sibling APIs (Curve
`t_years`, etc.) is Areas 3–5.

---

## The grounded API (verified — `test_projection_set.py`, `projection_frame.py`)

**Old (removed):**
```python
af = af.date.create_projection_timeline(
    valuation_date=datetime.date(2025, 1, 1),
    projection_end_type="maximum_age",
    projection_end_value=100,
    projection_frequency="monthly",
)
```

**New (`af.projection.set`, keyword-only):**
```python
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="maximum_age",        # "maximum_age" | "term_years" | "term_months" | "fixed_date" | "next_anniversary"
    until_value=100,            # int | date | column-name str | pl.Expr
    frequency="monthly",
)
```

**Parameter mapping:**

| Old | New |
|---|---|
| `valuation_date=` | `valuation_date=` (unchanged) |
| `projection_end_type="maximum_age"` | `until="maximum_age"` |
| `projection_end_value=100` | `until_value=100` |
| `projection_frequency="monthly"` | `frequency="monthly"` |

**What `set()` produces (verified):**
- **Eager stamps:** `projection_start_date`, `projection_end_date`, `num_proj_months`
  (so the old "there is *no* automatic period counter" claim in `model-phases.md`
  is now **false** — `num_proj_months` is stamped). For `until="maximum_age",
  until_value=100`, issue_age 30 → `num_proj_months == 70*12 + 1` (the **+1** is
  the start boundary).
- **Lazy accessors** (one List per policy):
  `af.projection.period_dates()` → `List<Date>`;
  `af.projection.year_fractions()` → per-period dt;
  `af.projection.t_years()` → cumulative year-fractions (feeds `Curve.discount_factor`);
  `af.projection.anniversary_mask()`, `af.projection.is_in_force()`.
- **Deriving `month` from dates** (replaces any old period-counter trick):
  ```python
  af.projection_date = af.projection.period_dates()
  af.month = (af.projection_date.dt.year() - 2025) * 12 + (af.projection_date.dt.month() - 1)
  ```

**New capability worth a one-line mention (not deep coverage):** a **per-policy
(jagged)** timeline — pass a column name as `until_value` with a `term_*` horizon
and each policy projects only its own length (auto-selected):
```python
af = af.projection.set(valuation_date=..., until="term_months",
                       until_value="remaining_term_months", frequency="monthly")
```

**The off-by-one gotcha, restated:** the old `projection_end_value=99` vs `100`
trap becomes `until_value=99` vs `100` — `until_value=100` projects *through* age
100; `99` truncates the final year. Keep the gotcha; update the call.

---

## Worklist — exact files & occurrences (grep-confirmed)

| File | Lines | Nature |
|---|---|---|
| `skills/quickstart/SKILL.md` | 74 | one-line "use `af.date.create_projection_timeline()`" |
| `skills/model-building/SKILL.md` | 84, 150 | table cell + a full Phase-2 example |
| `skills/model-building/references/model-phases.md` | 3, 48, 79, 82, 96, 109, 112, 127 | **heaviest** — the Phase-1/2 boundary narrative, the `t`/period-counter claim, the accessor table |
| `skills/model-building/references/common-mistakes.md` | 38, 41, 150, 245, 252 | the 99-vs-100 gotcha + several call sites |
| `skills/model-building/references/aggregate-patterns.md` | 23 | phase table cell |
| `skills/extending-gaspatchio/references/performance-ladder.md` | 21 | accessor inventory (`date` row lists `create_projection_timeline`) |

Skills touched: **quickstart, model-building (+3 refs), extending-gaspatchio**.

---

## Execution (the `skill-update` loop)

1. **MAP** — confirm each grep hit is a real API reference (not prose coincidence).
2. **EDIT** — apply the mapping above. Per file:
   - Mechanical call-sites (quickstart:74, model-building:84/150, aggregate-patterns:23,
     performance-ladder:21): rename + remap params.
   - `model-phases.md` (heaviest): rewrite the `create_projection_timeline()`
     narrative to `af.projection.set()`; **fix the false "no automatic period
     counter" claim** — `num_proj_months`/`projection_start_date`/`projection_end_date`
     are stamped; update the `t`/`month` derivation to `period_dates()`; correct the
     accessor table (`af.projection.set`, not `af.date.create_projection_timeline`).
   - `common-mistakes.md`: restate the 99-vs-100 gotcha as `until_value`.
   - Note `af.projection.set` is on the **`projection`** frame accessor, not `af.date`
     (the old method was on `af.date`). Update any "boundary is on `af.date`" phrasing.
3. **Skill voice** — imperative, example-dense; realistic actuarial data; keep each
   file ≤500 lines.

## Verification

1. **Grep gate (must be zero):** `grep -rn "create_projection_timeline" skills/` → no hits.
2. **Source cross-check:** every new `af.projection.set(...)` example uses only
   params that exist in `bindings/python/gaspatchio_core/accessors/projection_frame.py::set`
   (`valuation_date, until, until_value, issue_age_column, inception_column,
   start_date, n_periods, frequency, per_policy, schedule`). No invented params.
3. **Structural gate** (from `bindings/python`):
   `uv run pytest ../../tests/skills/ -q` and
   `uv run python ../../scripts/gen_skill_manifests.py --check` → pass.
4. **Deferred:** the L3 lift spot-check (`skill_verify.py`) once #138 lands — it
   will *measure* the fix (broken → working) on model-building.

## REVIEW

Report the diff + the grep/structural results. Commit on `feat/skill-refresh`
(this is a tracked branch heading to a reviewed PR — not an auto-merge to develop).
Do **not** touch `AGENTS.md` here (it also teaches the old method, but it is a core
doc, not a `skills/` artifact — handled separately).
