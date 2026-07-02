# Tutorial concept-guides + ScenarioRun default — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development
> to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Author three self-asserting concept-guides under `tutorials/patterns/`, promote
`ScenarioRun` + the concrete scheduling primitives to top-level exports, lead the L5 base
with `ScenarioRun`, and move `rollforward-patterns/` under `patterns/` — closing the
coverage detector's worklist.

**Architecture:** Each guide is standalone numbered scripts (synthetic inline data) that
**assert against a closed-form / hand-computed expectation** — a clean `uv run python <script>`
IS the test (the `rollforward-patterns/` template). Exports are additive `__init__.py` edits.

**Tech stack:** Python 3.12, Polars, `gaspatchio_core` (built from THIS worktree via maturin),
`uv`, `pytest`, `mypy.stubtest`. Design: `ref/45-tutorial-refresh/2026-06-26-tutorial-patterns-design.md`.

**Branch:** `feat/tutorial-patterns` (worktree `.claude/worktrees/tutorial-patterns`, off `develop`).
All commits signed, conventional, **no AI/Co-Authored-By trailer**. Grounded API references
(read these before authoring): `skills/model-building/references/running-at-scale.md` and
`curves-and-scheduling.md` on branch `feat/skill-refresh` (worktree `.claude/worktrees/skill-refresh`).

---

## File Structure

- Create: `bindings/python/gaspatchio_core/tutorials/patterns/aggregate-at-scale/{01..04}_*.py` + `README.md`
- Create: `…/patterns/period-aggregators/{01..03}_*.py` + `README.md`
- Create: `…/patterns/curves-and-scheduling/{01..04}_*.py` + `README.md`
- Modify: `bindings/python/gaspatchio_core/__init__.py` (exports)
- Modify: `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/run_scenarios.py`
- Move:   `…/tutorials/rollforward-patterns/` → `…/tutorials/patterns/rollforward-patterns/`
- Modify: `…/tutorials/README.md`, root `AGENTS.md`, any skill referencing `rollforward-patterns`

---

### Task 0: Build setup + baseline (do first)

**Files:** none (environment)

- [ ] **Step 1: Build `gaspatchio_core` from THIS worktree** so imports/scripts resolve here
  (multi-worktree editable installs otherwise point at another worktree's source):
  `cd bindings/python && maturin develop -uv` (or `uv run maturin develop`).
- [ ] **Step 2: Baseline green** — `uv run --directory bindings/python pytest -q -m "not benchmark"`
  passes (note the count); `uv run python -c "import gaspatchio_core; print(gaspatchio_core.__file__)"`
  resolves to THIS worktree's path. If the path is a different worktree, re-run `maturin develop`.

---

### Task 1: Top-level exports (ScenarioRun + scheduling primitives)

Do BEFORE Task 4 (curves guide imports the promoted classes). Pure-Python additive edit.

**Files:** Modify `bindings/python/gaspatchio_core/__init__.py`

- [ ] **Step 1: Read `__init__.py`** to learn the existing import grouping + `__all__` ordering.
- [ ] **Step 2: Add the imports** (place near related imports; `Calendar`/`DayCount`/
  `BusinessDayConvention` abstract bases are already imported — add the concretes):
```python
from gaspatchio_core.scenarios import ScenarioRun
from gaspatchio_core.schedule import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    NullCalendar,
    OneTwelfth,
    TARGET,
    Thirty360,
    UnitedKingdom,
    UnitedStates,
)
```
- [ ] **Step 3: Add to `__all__`** (keep its existing sort order):
  `"Actual360", "Actual365Fixed", "ActualActualISDA", "NullCalendar", "OneTwelfth",
  "ScenarioRun", "TARGET", "Thirty360", "UnitedKingdom", "UnitedStates"`.
- [ ] **Step 4: Verify imports** — `uv run python -c "from gaspatchio_core import ScenarioRun, ActualActualISDA, Actual360, Actual365Fixed, OneTwelfth, Thirty360, NullCalendar, TARGET, UnitedKingdom, UnitedStates; print('ok')"` → `ok`.
- [ ] **Step 5: Type + suite gates** — `uv run --directory bindings/python pytest -q -m "not benchmark"` green;
  `uv run --directory bindings/python python -m mypy.stubtest gaspatchio_core` passes (if it flags the new
  re-exports as missing-from-stub, add them to the stub the same way existing top-level classes are declared —
  match the established pattern; if `gaspatchio_core` uses inline types with `py.typed` and no `__init__.pyi`, no stub change is needed). Report what stubtest required.
- [ ] **Step 6: Commit** — `feat(api): promote ScenarioRun + concrete day-counts/calendars to top-level exports`

---

### Task 2: `aggregate-at-scale/` guide

**Files:** Create `…/tutorials/patterns/aggregate-at-scale/{01_run_aggregated,02_spill_to_parquet,03_batching,04_over_partition}.py` + `README.md`

Read `running-at-scale.md` (skill-refresh worktree) first for grounded signatures. Each
script: SPDX header (match an existing tutorial file), module docstring (concept + what it
asserts), a small self-contained `model_fn(af)->af` (e.g. `af.net_cf = af.premium - af.claim`
over a short projection) and a synthetic `pl.DataFrame` of model points built inline, then
the pattern, then `assert` against the closed form, then a short `print` of the result.
`model_points` is a plain `pl.DataFrame`; every aggregator carries `.alias(...)`;
`AggregatedResult` read by attribute (never `.collect()`).

- [ ] **01_run_aggregated.py** — `run_aggregated(model_fn, mp, [Sum("x").alias("x"), PeriodSum("net_cf").alias("net_cf")])`.
  **Assert:** `res.pv_net_cf` (scalar fold) == the same total computed by running `model_fn` on the
  full frame and summing directly; `res.net_cf` (np.ndarray) == per-period column sum. (fold == materialize)
- [ ] **02_spill_to_parquet.py** — `run_to_parquet(model_fn, mp, output_dir=tmp)` then `pl.scan_parquet(tmp/"*.parquet")`.
  **Assert:** read-back row count == `spill.n_policies`; a column total == the full-run total. Use a temp dir under the script's own folder or `tempfile`; clean it up.
- [ ] **03_batching.py** — run the SAME aggregation at `batch_size` ∈ {1, 7, "auto"}.
  **Assert:** all three give identical `res.pv_net_cf` / `res.net_cf` (batch-invariance). Comment documents the cgroup-blind `"auto"` gotcha (pass explicit int in CI/containers).
- [ ] **04_over_partition.py** — add a `product_line` column; `Sum("x").alias("x").over("product_line")`.
  **Assert:** the per-partition `pl.DataFrame` sums reconcile to the un-partitioned portfolio total.
- [ ] **README.md** — `File | Pattern | Asserts` table, a "Running" block (`uv run python tutorials/patterns/aggregate-at-scale/01_run_aggregated.py`), and "API surface used" list. Reference column: the batched aggregate-stream design (`ref/41-backend-portability`, GSP-89/#111).
- [ ] **Verify** — `for f in tutorials/patterns/aggregate-at-scale/[0-9]*.py; do uv run python "$f" || echo "FAIL $f"; done` → all exit 0.
- [ ] **Commit** — `docs(tutorials): aggregate-at-scale concept guide`

---

### Task 3: `period-aggregators/` guide

**Files:** Create `…/patterns/period-aggregators/{01_period_sum_mean,02_period_tail_metrics,03_period_over_and_limits}.py` + `README.md`

`Period*` aggregators return a per-period vector (term structure). Build a small known
portfolio so hand-computed expectations are exact. Import from `gaspatchio_core.scenarios`.

- [ ] **01_period_sum_mean.py** — `PeriodSum`/`PeriodMean` via `run_aggregated`.
  **Assert:** output vectors == NumPy per-period sum/mean on the same synthetic data.
- [ ] **02_period_tail_metrics.py** — `PeriodCTE(level=0.95)` and `PeriodQuantile(levels=(0.05,0.95))`.
  **Assert:** `PeriodCTE` per period == a hand CTE/TVaR on a small known per-period loss set; `PeriodQuantile` returns the tidy `{period, level, value}` shape (verify columns + a known quantile value).
- [ ] **03_period_over_and_limits.py** — `PeriodMedian(...).over("g")` / `PeriodCTE(...).over("g")` reconcile per group; then assert `PeriodQuantile(...).alias(...).over("g")` raises `NotImplementedError` (the documented guardrail) via `pytest.raises`-style try/except in the script.
- [ ] **README.md** — table + Running + API surface. Reference column: Hardy (2003) *Investment Guarantees* §9 (CTE/TVaR); Klugman/Panjer/Willmot *Loss Models* (quantiles/VaR).
- [ ] **Verify** — every script exits 0.
- [ ] **Commit** — `docs(tutorials): period-aggregators concept guide`

---

### Task 4: `curves-and-scheduling/` guide  (depends on Task 1 exports)

**Files:** Create `…/patterns/curves-and-scheduling/{01_curve_construction,02_curve_stress,03_schedule_daycount,04_curve_precompute_discount}.py` + `README.md`

Read `curves-and-scheduling.md` (skill-refresh) first. Import `Curve`, `Schedule` and the
promoted day-counts/calendars from the **top level** (`from gaspatchio_core import Curve, Schedule, ActualActualISDA, OneTwelfth, TARGET`).

- [ ] **01_curve_construction.py** — `Curve.from_zero_rates(tenors=, rates=)`; `spot_rate`, `discount_factor`, `forward_rate(t1=, t2=)`; `Curve.from_par_rates(...)`.
  **Assert:** `discount_factor(t)` == `(1+spot_rate(t))**(-t)`; `discount_factor(0.0)==1.0`; a mid-knot `spot_rate` == hand linear interpolation; `from_par_rates` output re-prices a par bond to ≈1.0 (or spot at a knot ≈ the documented bootstrap value).
- [ ] **02_curve_stress.py** — `shift_parallel(bps=100)`, `key_rate_shift(tenor=10.0, bps=25)`.
  **Assert:** shifted curve `spot_rate` at each knot == original + bps/1e4 (parallel); original curve unchanged (immutability — re-query and compare); a `key_rate_shift(tenor=...)` with a non-knot tenor raises.
- [ ] **03_schedule_daycount.py** — `Schedule.from_calendar_grid(start_date=, n_periods=, frequency="1M")` with `day_count=OneTwelfth()` vs `day_count=ActualActualISDA()` spanning a leap-year boundary (e.g. start `date(2024,1,31)`).
  **Assert:** `OneTwelfth` `year_fractions()` all == 1/12; `ActualActualISDA` year-fractions differ across the Feb-29 boundary and match a hand Act/Act calc; `period_dates()` length == `n_periods+1`. (This is the script that finally gives `DayCount` a runnable home.)
- [ ] **04_curve_precompute_discount.py** — the production pattern: `sched.cumulative_year_fractions()` → `curve.discount_factor(py_list)` → `pl.lit(..., dtype=pl.List(pl.Float64))` broadcast → `(af.net_cf * af.discount_factor).list.sum()`.
  **Assert:** PV via broadcast DF == PV computed directly from the same DF vector and a known `net_cf`. Comment marks this the GSP-116-avoiding (no `map_elements`) path.
- [ ] **README.md** — table + Running + API surface. Reference: Hull *Options, Futures & Other Derivatives* (curves/forwards); EIOPA RFR; ISDA day-count definitions.
- [ ] **Verify** — every script exits 0.
- [ ] **Commit** — `docs(tutorials): curves-and-scheduling concept guide`

---

### Task 5: Lead the L5 base with `ScenarioRun`

**Files:** Modify `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/run_scenarios.py`

- [ ] **Step 1: Read** the current base `run_scenarios.py` (uses `with_scenarios(af, SCENARIOS)`) and its expected-output / reconcile contract (so parity is preserved).
- [ ] **Step 2: Rework** the entry-point so the headline path builds a `ScenarioRun(...)` (typed plan: scenarios/shocks + base tables + `.alias()` aggregations) and calls `.run(...)`, rather than the low-level `with_scenarios` cross-join. `with_scenarios` may remain shown as the lower-level primitive in a comment, but `ScenarioRun` leads. Use `from gaspatchio_core import ScenarioRun` (now top-level).
- [ ] **Step 3: Verify** the script runs (exit 0) AND still reconciles / produces the same headline numbers as before (run it; compare against the prior expected output). If there's a reconcile assertion/expected_output file, it must still pass.
- [ ] **Step 4: Commit** — `docs(tutorials): lead L5 base with ScenarioRun (the typed default)`

---

### Task 6: Move `rollforward-patterns/` into `patterns/`

**Files:** `git mv` + cross-ref updates

- [ ] **Step 1:** `git -C <worktree> mv bindings/python/gaspatchio_core/tutorials/rollforward-patterns bindings/python/gaspatchio_core/tutorials/patterns/rollforward-patterns`
- [ ] **Step 2: Grep + update every reference** to the old path:
  `grep -rn "rollforward-patterns" --include='*.md' --include='*.py' .` across the repo (tutorials/README.md, root AGENTS.md, any `skills/**` reference). Update each `tutorials/rollforward-patterns` → `tutorials/patterns/rollforward-patterns`.
- [ ] **Step 3: Verify** the moved scripts still run (`uv run python tutorials/patterns/rollforward-patterns/01_single_state_fund.py` exit 0) and no stale path remains (`grep -rn "tutorials/rollforward-patterns" .` empty).
- [ ] **Step 4: Commit** — `refactor(tutorials): move rollforward-patterns under patterns/`

---

### Task 7: Close the loop — detector + READMEs + smoke

**Files:** `tutorials/README.md` (patterns section), optional CI smoke matrix

- [ ] **Step 1: Add a `patterns/` section** to `tutorials/README.md` listing the four concept-guides (rollforward-patterns + the 3 new) with one-line descriptions and the Diátaxis framing (concept-guides vs the level ladder).
- [ ] **Step 2: Detector closure** — from the docs worktree, run
  `uv run --directory ~/projects/gaspatchio/gaspatchio-docs python -m scripts.tutorials_coverage --surface added --json /tmp/wl2.json` and confirm the top-level concept gaps no longer include `run_aggregated`, `run_to_parquet`, `AggregatedResult`, `SpillResult`, the `Period*` family, or `DayCount`. (The detector confirms the gap is closed — the payoff. Bump `.tutorials-sync.yml synced_sha` only after this branch merges.)
- [ ] **Step 3 (optional): CI smoke** — extend the tutorial-smoke matrix to glob `tutorials/patterns/**/[0-9]*.py` so the guides stay executable.
- [ ] **Step 4: Commit** — `docs(tutorials): patterns/ index + close coverage loop`

---

## Self-Review (completed)

- **Spec coverage:** design Guide 1→Task 2, Guide 2→Task 3, Guide 3→Task 4; Change A→Task 5,
  Changes B–C→Task 1; rollforward move→Task 6; verification/detector-closure→Task 7. Setup→Task 0.
- **Ordering:** Task 1 (exports) precedes Task 4 (curves guide imports the promoted classes); Task 0 (build) precedes everything.
- **No placeholders:** each script has a concrete assertion property + grounded API surface; precise code given for the additive edits (Task 1) and exact commands for the move (Task 6).
- **Names:** the 10 promoted symbols match `gaspatchio_core.schedule.__all__` + `scenarios.ScenarioRun` exactly.

## Execution note

Self-asserting scripts are the test: "write the script (with asserts) → run it → exit 0" replaces
red/green TDD per-step. Treat a non-zero exit or failed assert as a red test to fix before commit.
