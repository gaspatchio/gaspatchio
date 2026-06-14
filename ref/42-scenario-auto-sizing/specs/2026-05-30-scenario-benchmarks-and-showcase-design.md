# Scenario benchmarks + stochastic showcase — design

Date: 2026-05-30
Branch: `gsp-100-post-merge` (PR #106 → develop)
Topic: `ref/42-scenario-auto-sizing/` (this benchmark exists to track and showcase the
auto-sizing / jagged / learned-cache work that shipped in PR #106)

---

## 1. Problem & goals

PR #106 made the scenario path fast and memory-bounded by default (`batch_size="auto"`,
jagged `per_policy` timelines, learned calibration cache). **None of it is benchmarked.**
The dashboard's `"VA + Scenarios (3x)"` series still uses the *old* `with_scenarios(["BASE",
"UP","DOWN"])` API (`evals/benchmarks/run_model_benchmarks.py::bench_l5`, line 198) — 3
deterministic scenarios, no `ScenarioRun` / `for_each_scenario` / `auto` / `per_policy`. A
regression in the new path would be invisible on https://opioinc.github.io/gaspatchio-core/.

Three goals:

1. **Track the default scenario path over time** on the gh-pages dashboard (the recurring
   time-series the user values), exercising the *real* `ScenarioRun.run(..., batch_size="auto")`.
2. **Test-drive the work across models and profiles** locally — characterise auto vs fixed
   vs serial-seeded vs per_policy, and prove results are identical across profiles.
3. **Produce something meaningful for actuaries** — a stochastic VA reserving showcase
   (distribution + CTE, percentile fan chart) reusable in both the performance pages and the
   docs, with chart **data generation kept separate from chart rendering**.

---

## 2. Background — how the pipeline works (verified)

- **Adding a chart is data-driven.** `run_model_benchmarks.py` emits a flat JSON array of
  `{name, unit, value}`; `benchmark-action/github-action-benchmark@v1` appends each run to
  `data.js` on the `gh-pages` branch and auto-renders one Chart.js line chart **per unique
  `name`**. New series = new name. New page = new `benchmark-data-dir-path`. No HTML to write.
- **Existing pages:** `dev/model-bench/`, `dev/comparison/`, `dev/bench/`, `dev/evals/`.
- **CI:** `.github/workflows/evals.yml`; the `comparison-benchmarks` job already runs at a
  **120-min** timeout on `ubuntu-latest-m`, so a heavy dedicated scenario job is precedented.
- **`ScenarioResult` already carries the metrics we chart** — `wall_time_s`, `peak_rss_mb`,
  `batch_size`, `batch_size_resolution` (`manual`/`auto_probe`/`auto_calibrated`/`auto_cached`).
  The harness reads these off the result instead of re-instrumenting.
- **The L5 model already supports Monte Carlo** — Section 5 (`has_stochastic_returns`) looks
  up `inv_return_mth` by integer `scenario_id`; Section 16 handles integer (stochastic)
  `scenario_id` by broadcasting the curve; `main(..., scenario_returns_override=...)` is a hook.
  Per-policy/per-scenario output is `pv_net_cf` (line 809) — the natural reserving metric.
- **Altair is already the tutorial charting lib** (`tutorial/level-5-scenarios/benchmark.py`,
  `gaspatchio` theme, PNG + markdown report). Altair → Vega-Lite JSON is itself a data/spec
  split. We reuse it for the showcase and the local report.

---

## 3. The hard constraint & the grid

A scenario is a full portfolio re-projection, so N scenarios ≈ N× single-projection cost. On
`ubuntu-latest-m`, one 100K-point projection is ~37s (current dashboard value). Therefore:

| Grid | Effective projections | Est. wall | Fits CI? |
|---|---|---|---|
| 1K scenarios × 1K pts | 1M | ~6 min | ✅ |
| 100 scenarios × 100K pts | 10M | ~60 min | ⚠️ needs 90–120-min job |
| **1K scenarios × 100K pts** | **100M** | **~10 hr** | ❌ never |

**Decision: grid B** — an L-shaped 5-cell grid that tells both stories without the 10-hr corner:

```
                 scenarios →   10      100     1000
model points ↓
   1K                          ✓       ✓(*)    ✓        scenario-scaling arm
   10K                                 ✓
   100K                                ✓                portfolio-scaling arm
                              (1000 × 100K = EXCLUDED, ~10 hr)
(*) shared cell between the two arms → 5 unique cells
```

- **Scenario-scaling arm** (fixed 1K pts; 10/100/1000 scen): headline **peak RSS stays flat
  as scenarios climb** — `auto` packs many scenarios per batch. This is the PR #106 win.
- **Portfolio-scaling arm** (fixed 100 scen; 1K/10K/100K pts): the **100 × 100K** cell — big
  book, fewer paths — engine stress at realistic portfolio size.
- `1000 × 100K` **explicitly excluded** and documented in `evals/benchmarks/README.md` trades
  table (no silent caps — repo ethos).

> Actuarial nuance that justifies the split: a smooth tail needs *many* scenarios, but many
> scenarios × a full book is infeasible even in production, so actuaries run stochastic on a
> *compressed* portfolio. So the **1000-scenario × 1K-pts** cell is the actuarially meaningful
> one (smooth tail → real CTE); the **100 × 100K** cell is engine stress only.

---

## 4. Deliverables

| | Deliverable | Output | Location |
|---|---|---|---|
| **D1** | Local profile-matrix test-drive | markdown + Altair PNGs; **calibrates D2's grid with real timings** | `ref/42-scenario-auto-sizing/` (+ optional Obsidian mirror) |
| **D2** | Recurring CI perf time-series | new `dev/scenario-bench/` gh-pages page | `evals/benchmarks/` + `evals.yml` |
| **D3** | Stochastic actuarial showcase | data JSON + Altair/Vega chart, reusable in perf pages **and** docs | `evals/benchmarks/` (data+render split) |

**Sequencing:** D1 first — it measures real per-cell timings so D2's grid is sized against
data, not estimates, and it validates the 1,000-stochastic-path wiring (see §8 risks) on small
N before scaling. Then D2, then D3 (D3 reuses D1's stochastic mechanism + Altair).

---

## 5. D2 — recurring CI perf time-series

### Harness — `evals/benchmarks/run_scenario_benchmarks.py` (new)

- `model_fn` = the L5 model (`tutorial/level-5-scenarios/base/model.py`), `per_policy=True`
  path (already in the model).
- Scenarios = a deterministic bank of N `MultiplicativeShock` sets, indexed by scenario number
  (reproducible — **no RNG**, no `Math.random`/`Date.now`).
- Aggregation = `Sum("net_cf")` (tiny result — the bounded-memory point).
- All cells: `ScenarioRun(...).run(af, model_fn, batch_size="auto")`.
- Read metrics straight off `ScenarioResult`.

> **Why D2 uses deterministic shocks, D3 uses stochastic returns (deliberate):** D2 only
> needs N scenarios flowing through the `auto` batched loop to track engine regressions, so it
> uses the **known-good** shock API — this de-risks perf tracking, which must work regardless
> of how risk #1 (§8) resolves. D3 needs *real* equity paths for a meaningful distribution, so
> it uses stochastic returns. If D1 proves the stochastic wiring clean, D2 and D3 can later
> share one scenario bank (D3 = the 1000×1K cell + actuarial aggregators); kept separate now
> to avoid blocking D2 on the open wiring question.

### Metrics & naming

Action `name: "Scenario Benchmarks"` → new entries key + `dev/scenario-bench/` page.
Per cell, four `{name, unit, value}` rows (zero-padded scenario counts for chart ordering):

| Metric | unit | source | tool |
|---|---|---|---|
| wall | seconds | `wall_time_s` | customSmallerIsBetter |
| rss | MB | `peak_rss_mb` | **headline — flat under auto** |
| throughput | scenario·points/sec | `(n_scen × n_pts) / wall` | (bigger better, but page is SmallerIsBetter; throughput emitted as derived, acceptable) |
| batch | count | `batch_size` | informational (what auto chose) |

Name scheme:
`"scen-scaling/1Kpts-0010sc-wall"`, `…-0100sc-wall`, `…-1000sc-wall`, … and
`"port-scaling/0100sc-1Kpts-wall"`, `…-10Kpts-…`, `…-100Kpts-…`.
`batch_size_resolution` is **logged, not charted** (categorical).

### CI job — `scenario-benchmarks` in `evals.yml` (new)

```yaml
runs-on: ubuntu-latest-m
timeout-minutes: 120        # precedent: comparison-benchmarks
# publish via github-action-benchmark → benchmark-data-dir-path: dev/scenario-bench
```

### Triggers (the configurable part)

| Trigger | Why |
|---|---|
| `push: [main, develop]` | runs on merge — keeps the time-series fed, same as other benchmarks |
| `pull_request: types:[labeled]` gated on **`performance`** label | lets us dry-run on **PR #106** now: add the label → full pipeline runs live on the cloud runner before merge. Distinct from the existing `benchmark` label so a perf run doesn't drag in the 120-min lifelib comparison. |
| `schedule` weekly cron + `workflow_dispatch` | recurring baseline + manual |

The job's `if:` guard mirrors the existing jobs but keys on `github.event.label.name == 'performance'`.

---

## 6. D3 — stochastic actuarial showcase

### The run

- 1,000 stochastic equity-return paths (a `scenario_returns` table with `scenario_id` 1..1000)
  on the **1K representative portfolio**, through the batched `auto` loop.
- Metric: **`pv_net_cf`** per policy; portfolio loss per scenario = `−Σ pv_net_cf`.
- Aggregations: `Sum("pv_net_cf").over("scenario_id")` (→ 1,000 portfolio totals = the
  distribution), plus `CTE("pv_net_cf", level=0.70)`, `CTE(level=0.95)`,
  `Quantile([0.05,0.25,0.5,0.75,0.95])` for the markers/fan.

### Purpose (grounded, not persona-derived)

Stochastic VA guarantee reserving / capital:
- **VM-21** (US VA statutory) — reserve = **CTE70** of the PV of accumulated deficiency.
- **Economic capital** — **CTE95/CTE98** tail.
- **Solvency II SCR** — VaR 99.5% (1-in-200).

Framed honestly as **illustrative on tutorial data** (not a certified reserve); fully auditable
— the CTE/quantile lines *are* the API calls, visible in the showcase code.

### Two panels (Altair)

- **Panel A — reserve distribution:** histogram of per-scenario portfolio loss
  (`−Σ pv_net_cf`) with CTE70 / CTE95 marker lines. "This is the CTE70 reserve."
- **Panel B — percentile fan chart:** 5/25/50/75/95 bands of a per-period series (account
  value or net CF) over projection months.

### Data / chart separation (the "keep charts separate" requirement)

```
run ─► scenario_showcase.json   (per-scenario totals + CTE/quantile aggregates + fan series)
            ├─► render (Altair) ─► perf-pages artifact  (dev/scenario-bench/showcase.*)
            └─► render (Altair) ─► docs artifact          (same JSON, same renderer)
```

The run emits **data only**; a single renderer (one module) turns the JSON into Vega-Lite/PNG.
One data file, one renderer, consumed by both the performance page and the docs — chart code
lives in exactly one place, never coupled to the run.

---

## 7. D1 — local profile-matrix test-drive

`run_scenario_testdrive.py` (new, local) + report. Across L4/L5 at a few sizes:

| Profile | Knob |
|---|---|
| auto (default) | `batch_size="auto"` |
| fixed | `batch_size=N` |
| serial-seeded | `master_seed=…` → resolves to serial |
| per_policy on/off | jagged vs uniform timeline |

Captures wall / peak-RSS / resolved batch / `batch_size_resolution`. **Asserts:**
- `auto` wall ≈ best fixed wall (within tolerance) — auto isn't leaving throughput on the table.
- **Results identical across all profiles** (correctness guard — the headline safety property).
Feeds measured timings into D2's grid sizing. Report style reuses `benchmark.py`'s
markdown + Altair-PNG shape.

---

## 8. Risks / open implementation questions (resolve in D1, small N first)

1. **1,000 stochastic paths through the batched loop.** The model reads stochastic returns via
   a `scenario_returns` table keyed by `scenario_id`; `for_each_scenario` is built around shocks
   on `base_tables`. Open question: feed paths via `base_tables` stacking, via
   `scenario_returns_override` per batch, or via the drivers-dict form. **Validate on N=8 that
   batched aggregation == single-shot `group_by("scenario_id")` before scaling to 1,000.**
2. **Fan chart per-period percentiles.** Panel B needs cross-scenario percentiles *at each
   month* — a per-period (vector) aggregation, not a per-scenario scalar. Confirm whether
   `Quantile.over` handles per-period or whether the per-period series is retained and
   percentiles taken at render time. Validate small.
3. **100 × 100K memory envelope on the runner.** At 100K points, `auto` may go near-serial; the
   single-projection peak must fit the runner's RAM budget (L4 100K used ~11 GB RSS and didn't
   OOM, so headroom exists). Confirm in the `performance`-label dry-run on PR #106.

---

## 9. Out of scope

- The excluded `1000 × 100K` cell (documented).
- Changing the existing `bench_l5` `"VA + Scenarios (3x)"` series (leave as-is; the new
  `Scenario Benchmarks` page is additive).
- Any production-reserve certification claim (showcase is illustrative).

---

## 10. File inventory

New:
- `evals/benchmarks/run_scenario_benchmarks.py` (D2 harness)
- `evals/benchmarks/run_scenario_showcase.py` (D3 run → JSON)
- `evals/benchmarks/render_scenario_showcase.py` (D3 JSON → Altair charts; shared by perf+docs)
- `evals/benchmarks/run_scenario_testdrive.py` (D1, local)
- `ref/42-scenario-auto-sizing/` report (D1)

Changed:
- `.github/workflows/evals.yml` (+ `scenario-benchmarks` job, `performance` label trigger)
- `evals/benchmarks/README.md` (+ scenario page docs, the excluded-cell trades note)
