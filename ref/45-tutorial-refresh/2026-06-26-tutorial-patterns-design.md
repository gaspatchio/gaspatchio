# Tutorial concept-guides (`patterns/`) + ScenarioRun default — design

> **Status:** design (brainstormed 2026-06-26). Core-repo authoring effort, branch
> `feat/tutorial-patterns` off `develop`. Downstream of the coverage detector
> (gaspatchio-docs `ref/02-skill-sync/2026-06-26-coverage-detector-*`), which
> generated the grounded gap worklist this spec closes.

**Goal:** Give every uncovered public concept a runnable, self-asserting example by
adding a Diátaxis concept-guide layer (`tutorials/patterns/`), and make `ScenarioRun`
the discoverable default for scenarios.

**Why now:** The coverage detector's worklist (`--surface added`, top-level concepts,
human-eyeballed) is exactly three clusters with no runnable example: the
streaming/aggregate-at-scale family, the `Period*` aggregators, and `DayCount`/scheduling.
The skills already *teach* these (skill-refresh references); no tutorial *runs* them.

---

## The concept-guide unit (generalize `rollforward-patterns/`)

The existing `tutorials/rollforward-patterns/` is the template: a folder of self-contained
numbered scripts, each declaring its own data, doing ONE concept, and **asserting against a
closed-form or hand-computed expectation** (a clean run IS the test) — plus a `README.md`
with a `File | Pattern | Reference` table, a "Running" block, and an "API surface used"
list. Each new guide follows this shape exactly. Scripts are standalone (synthetic inline
data, no external assumption files), so `uv run python <script>` is the whole test.

## Directory layout

```
tutorials/patterns/
  rollforward-patterns/      ← MOVED here (final task; updates ~4 cross-refs)
  aggregate-at-scale/        ← NEW
  period-aggregators/        ← NEW
  curves-and-scheduling/     ← NEW
```
New guides land under `tutorials/patterns/` immediately. Moving `rollforward-patterns/`
under it (for Diátaxis coherence) is **in scope** as the last task — a path move (`git mv`)
+ cross-ref updates (tutorials/README.md, any skill referencing it, AGENTS.md). Done last so
it doesn't block guide authoring.

---

## Guide 1 — `aggregate-at-scale/`

**Concept:** memory-bounded portfolio runs — `run_aggregated` (fold to aggregates) and
`run_to_parquet` (spill per-policy), `AggregatedResult`/`SpillResult`, `batch_size`.
Grounded in skill-refresh `running-at-scale.md`.

**Key property each script asserts:** *batched aggregation equals full aggregation* — the
fold is exact, not approximate.

| File | Pattern | Asserts |
|---|---|---|
| `01_run_aggregated.py` | `Sum` + `PeriodSum` fold over batches | `res.pv_net_cf` == direct `collect()`-then-sum on the same synthetic portfolio (fold == materialize) |
| `02_spill_to_parquet.py` | `run_to_parquet` → `scan_parquet` read-back | concatenated spill row-count == `n_policies`; a column total == the full-run total |
| `03_batching.py` | `batch_size="auto"` vs explicit int | results **identical** across `batch_size` ∈ {1, 7, "auto"} (batch-invariance); comments document the cgroup-blind gotcha (explicit int in CI/containers) |
| `04_over_partition.py` | `.over("product_line")` partitioned aggregation | per-partition sums reconcile to the portfolio total |

Self-contained: a ~15-line `model_fn` (premiums − claims projection) + a synthetic
`pl.DataFrame` of model points built inline. `model_points` is a plain `pl.DataFrame`
(gotcha #4). Every aggregator carries `.alias(...)` (gotcha #1). `AggregatedResult` read by
attribute, never `.collect()` (gotcha #2).
**Reference column:** the batched aggregate-stream design (repo `ref/41-backend-portability`,
GSP-89/#111) — engineering provenance, not academic.

## Guide 2 — `period-aggregators/`

**Concept:** per-period term-structure outputs — the `Period*` family — vs scalar
aggregators. A `Period*` aggregator returns a vector (one value per projection period): a
term structure of the statistic. Grounded in `running-at-scale.md` + `model-scenarios` skill.

| File | Pattern | Asserts |
|---|---|---|
| `01_period_sum_mean.py` | `PeriodSum` / `PeriodMean` over a known portfolio | output vector == hand-computed per-period sum/mean (NumPy on the same data) |
| `02_period_tail_metrics.py` | `PeriodCTE(level=)` / `PeriodQuantile(levels=)` | `PeriodCTE` per period == hand CTE/TVaR on a small known loss vector; `PeriodQuantile` tidy `{period, level, value}` shape verified |
| `03_period_over_and_limits.py` | `Period*.over(by)` + the documented limit | partitioned term structures reconcile; `PeriodQuantile(...).over(...)` raises `NotImplementedError` (assert the guardrail) |

**Reference column:** Hardy (2003) *Investment Guarantees* §9 (CTE/TVaR); Klugman/Panjer/
Willmot *Loss Models* (quantiles/VaR). These are the regulatory risk measures the
`Period*` term structures compute, so the citations are real.

## Guide 3 — `curves-and-scheduling/`

**Concept:** term-structure discounting (`Curve`) and explicit schedule construction
(`Schedule`/`Calendar`/`DayCount`/`BusinessDayConvention`). This is the guide that finally
gives `DayCount` (zero coverage today) a runnable home. Grounded in
`curves-and-scheduling.md`.

| File | Pattern | Asserts |
|---|---|---|
| `01_curve_construction.py` | `Curve.from_zero_rates` / `from_par_rates`, `spot_rate`/`discount_factor`/`forward_rate` | `discount_factor(t)` == `(1+r(t))**(-t)` closed form; `discount_factor(0.0) == 1.0`; linear-interp spot at a mid-knot == hand interpolation; `from_par_rates` bootstrap re-prices its input pars to ~1.0 |
| `02_curve_stress.py` | `shift_parallel(bps=)`, `key_rate_shift(tenor=, bps=)` | shifted curve's knot rates moved by exactly the bps; original unchanged (immutability); a non-knot `key_rate_shift` tenor raises |
| `03_schedule_daycount.py` | `Schedule.from_calendar_grid` + `OneTwelfth` vs `ActualActualISDA` | `year_fractions()` for `OneTwelfth` == constant 1/12; for `ActualActualISDA` across a leap-year boundary differs and matches a hand Act/Act calc; `period_dates()` length == n_periods+1 |
| `04_curve_precompute_discount.py` | production pre-compute: `sched.cumulative_year_fractions()` → `curve.discount_factor(list)` → `pl.lit(...).broadcast` | PV via broadcast DF == PV via a direct per-period reference; comment marks this as the GSP-116-avoiding (no `map_elements`) path |

**Reference column:** Hull *Options, Futures, and Other Derivatives* (curve/forward rates);
EIOPA risk-free-rate technical docs (term structure); ISDA day-count definitions.
`04` doubles as the canonical reference for avoiding the GSP-116 `map_elements` footgun.

---

## ScenarioRun — make it the default (decision: content + top-level export)

`ScenarioRun` (`gaspatchio_core.scenarios._run.ScenarioRun`) is the typed scenario plan and
is well covered in the L5 *steps*, but (a) the L5 **base** entry model leads with the older
low-level `with_scenarios()`, and (b) it is **not** a top-level export while `with_scenarios`
**is** — backwards for the recommended default.

**Change A — lead the L5 base with `ScenarioRun`.** Rework
`tutorials/level-5-scenarios/base/run_scenarios.py` so the entry-point scenario example uses
`ScenarioRun(...).run(...)` (the typed plan) rather than `with_scenarios(...)`. Keep it
runnable + reconciling (the base model's existing expected output / parity must still hold).
`with_scenarios` stays valid and may be shown as the lower-level primitive, but `ScenarioRun`
leads.

**Change B — top-level export.** Add `ScenarioRun` to `gaspatchio_core/__init__.py`
(`from gaspatchio_core.scenarios import ScenarioRun` + `"ScenarioRun"` in `__all__`) so
`from gaspatchio_core import ScenarioRun` works. It stays available via
`gaspatchio_core.scenarios.ScenarioRun` too. This shifts the public API surface — so it must
also: pass `mypy.stubtest` (pure-Python class, no `.pyi` change expected — verify), keep
`uv run pytest` green, and the DRIFT detector will see one added top-level symbol (expected).

**Change C — promote the concrete scheduling primitives to top-level (discoverability).**
The abstract bases (`Calendar`, `DayCount`, `BusinessDayConvention`) are already top-level,
but the concrete classes a user instantiates live only under `gaspatchio_core.schedule`.
Promote them to `gaspatchio_core` (`__init__.py` import + `__all__`), submodule path kept valid:
- **Day-counts:** `OneTwelfth`, `ActualActualISDA`, `Actual365Fixed`, `Actual360`, `Thirty360`.
- **Calendars:** `NullCalendar`, `TARGET`, `UnitedKingdom`, `UnitedStates`.

`BespokeCalendar`/`JointCalendar` and the `*_from_name` helpers stay submodule-scoped
(advanced/internal). Guide 3 then imports `ActualActualISDA`, `TARGET`, etc. from the top
level uniformly. Same verification as Change B (`pytest` + `mypy.stubtest` green; drift
detector sees the added symbols, expected).

---

## Verification (definition of done)

1. **Every new script runs clean and asserts**: `uv run python tutorials/patterns/<guide>/<NN>_*.py`
   exits 0 for all scripts (a failing assert is a red test).
2. **Each guide README** has the `File | Pattern | Reference` table + "API surface used".
3. **New top-level exports**: `from gaspatchio_core import ScenarioRun, ActualActualISDA, TARGET`
   (and the rest of Changes B–C) all import; the L5 base `run_scenarios.py` runs + reconciles;
   `uv run pytest -q` and `mypy.stubtest` green.
4. **Coverage closes**: after authoring, `tutorials_coverage --surface added` no longer
   flags `run_aggregated`/`run_to_parquet`/`AggregatedResult`/`SpillResult`/`Period*`/
   `DayCount` (the detector confirms the gap is closed — the loop's payoff). Bump
   `.tutorials-sync.yml synced_sha` once merged.
5. **CI smoke (optional)**: add `tutorials/patterns/**/[0-9]*.py` to the tutorial-smoke
   matrix so the guides stay executable.

## Scope / non-goals

- **No L6 ladder rung** this effort (Monte-Carlo/VaR narrative is separate; the scale
  *mechanics* land here as concept-guides).
- **Synthetic, self-contained scripts** — guides do NOT depend on the L4 lifelib assumption
  files (keeps each script a standalone test, matching `rollforward-patterns/`).
- **Detector de-noise** (filter worklist to `__all__`, dropping `polars_backend`/
  `tutorial_cli`/`tutorials` noise) is a *separate* docs-repo follow-up, not here.
- `rollforward-patterns/` move is the last, separable task.

## Resolved decisions (confirmed 2026-06-26)

- **`rollforward-patterns/` move:** IN SCOPE — the last task (`git mv` into `patterns/` +
  cross-ref updates).
- **Day-count promotion:** YES — concrete day-counts *and* the concrete calendars promoted to
  top-level (Change C above), so Guide 3's imports are uniform (`from gaspatchio_core import
  ActualActualISDA, TARGET`).
