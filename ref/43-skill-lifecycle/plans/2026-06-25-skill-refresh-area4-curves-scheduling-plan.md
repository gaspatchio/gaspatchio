# Area 4 — Curves & Scheduling: refresh plan

> **For agentic workers:** execute via the `skill-update` loop. This is a **pure
> draft** (new modules; no removed API). The grounded API below is verified
> against develop — still cross-check every signature against the source before
> writing.

**Goal:** Teach the new `curves` and `schedule` public modules in the
`model-building` skill — term-structure discounting (`Curve`) and explicit
schedule construction (`Schedule`/`Calendar`/`DayCount`/`BusinessDayConvention`).
The skills are currently silent on both.

**Fix vs draft:** DRAFT only. The existing flat-rate discounting the skills teach
(`projection.prospective_value(discount_rate=…)`, `finance.to_monthly()`, manual
`(1+r)**(-t/12)`) is **still valid on develop** — do NOT delete it. `Curve` is the
*term-structure upgrade* for when discounting comes from a yield curve (Solvency
II / IFRS17 / EIOPA), not a flat rate. Present it as the additional capability.

---

## Grounded API — `Curve` (verified: `curves/_curve.py`, `tests/curves/test_curve_accessors.py`)

`Curve` is a frozen dataclass; construct via classmethods (direct construction is
intentionally awkward):

```python
from gaspatchio_core import Curve

c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0, 30.0], rates=[0.025, 0.03, 0.035, 0.04])
# or bootstrap from par/swap rates:
c = Curve.from_par_rates(tenors=[...], rates=[...])
```

- `tenors` strictly increasing, ≥2 knots; `rates` same length. Linear interpolation
  on rates; **flat extrapolation** outside the knot range. Default day-count
  `ActualActualISDA` (override via `day_count=`).
- **Query methods** accept `float | list[float] | np.ndarray | pl.Series | pl.Expr`
  and return a matching shape:
  - `c.spot_rate(t)` — zero/spot rate at tenor `t`
  - `c.discount_factor(t)` — `discount_factor(0.0) == 1.0`; for a 3% flat curve
    `discount_factor(1.0) == 1/1.03`
  - `c.forward_rate(t1=…, t2=…)` — forward rate between two tenors
- **Stress:** `c.shift_parallel(bps=25)` and `c.key_rate_shift(tenor=…, bps=…)`
  return new `Curve`s (composes with the scenario `Shock` system for curve stresses).
- **Limitation:** static curves only (literal Python-list knots at construction);
  per-row column curves are not yet implemented.

**The headline pattern — vectorized per-period discounting (pairs with Area 1's
`t_years()`):**
```python
af.t = af.projection.t_years()                       # cumulative year-fractions, length n_periods+1
af.discount_factor = c.discount_factor(af.t)         # Curve accepts the list/expr → per-period DF vector
af.pv_net_cf = (af.net_cf * af.discount_factor).list.sum()
```
This is the term-structure alternative to `prospective_value(discount_rate=…)`
(flat) — show both; flat for a single rate, `Curve` for a yield curve.

## Grounded API — `Schedule` & friends (verify exact signatures before writing)

Explicit projection-schedule construction — the advanced alternative to Area 1's
`af.projection.set(valuation_date=, until=, until_value=, frequency=)` kwargs path.
Used as `af.projection.set(schedule=Schedule.from_…())`.

- `Schedule.from_calendar_grid(...)`, `Schedule.from_inception(...)`,
  `Schedule.from_per_policy_grid(...)` — classmethods (`schedule/_schedule.py:246+`).
- `Calendar`, `DayCount`, `BusinessDayConvention` — supporting types
  (`schedule/_calendar.py`, `_day_count.py`, `_business_day.py`).
- **Executor: introspect each classmethod's exact signature** (`help()` + read
  `tests/` under `bindings/python/tests/` that use `Schedule.from_…`) before
  writing any example. Teach this lighter than `Curve` — it's the advanced path;
  most models use the Area 1 kwargs path.

---

## What to edit

1. **Create `skills/model-building/references/curves-and-scheduling.md`** — the
   deep-dive (a sibling to `model-phases.md`). Sections:
   - **Term-structure discounting with `Curve`** (the main event): construction
     (`from_zero_rates`/`from_par_rates`), the vectorized `discount_factor(t_years())`
     pattern, curve stress (`shift_parallel`/`key_rate_shift`) and its tie to the
     scenario system, flat-vs-curve guidance. Realistic actuarial data (e.g. a
     EUR-style zero curve), never foo/bar.
   - **Explicit schedules with `Schedule`** (the advanced path): the three
     `from_*` constructors + `Calendar`/`DayCount`/`BusinessDayConvention`, used
     via `af.projection.set(schedule=…)`. Keep concise; signatures verified.
   - ≤600 lines (the L1 cap, just raised in Area 2).
2. **`skills/model-building/SKILL.md`** — add a short pointer to the new reference
   (in the reference-file list and/or near any discounting mention). A few lines.
3. **`skills/model-building/references/model-phases.md`** — in the discounting row
   (~line 136) and/or the accessor tables, add a one-line note that for a yield
   curve / term structure, use `Curve.discount_factor(af.projection.t_years())`
   (cross-link the new reference). Do NOT remove the existing flat-rate content.

**Check `model-discovery`** (the other Area-4 skill in the design): grep it for
discounting/curve scoping content; edit only if it genuinely references the input
data (likely a no-op, like model-review in Area 2 — report if so).

## Verification

1. **Source cross-check:** every `Curve`/`Schedule` example uses only real
   classmethods/params (per `curves/_curve.py` and `schedule/_schedule.py`).
2. **Grep gate:** `grep -rn "Curve\|Schedule" skills/model-building/` shows the new
   content; the headline `discount_factor(.*t_years` pattern is present.
3. **Structural gate** (worktree env can't plain `uv run` — lancedb):
   `uv run --no-project --with pytest --with pyyaml python -m pytest tests/skills/ -q`
   → all pass; confirm the new reference ≤600 lines.
4. **Deferred:** L3 lift spot-check once #138 lands.

## REVIEW

Report the diff + grep/structural results. Commit on `feat/skill-refresh`
(conventional, no AI trailer). Do not push. `AGENTS.md` is out of scope.
