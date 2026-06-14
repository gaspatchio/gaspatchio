# Scenario test-drive — profile matrix + grid calibration

Date: 2026-05-30
Branch: `gsp-100-post-merge`
Source: `evals/benchmarks/run_scenario_testdrive.py` → `scenario_testdrive_results.json`
Hardware: local Apple Silicon (CI `ubuntu-latest-m` is slower — see §4).

This report does three things: (1) records the **resolved wiring mechanism** for running the
L5 stochastic workload through the bounded-memory scenario loop, (2) characterises the
**profile matrix** (auto vs fixed vs serial-seeded), and (3) **calibrates the Phase B CI grid**
against measured timings.

---

## 1. Resolved wiring mechanism (spec risk #1 — closed)

`for_each_scenario(batch_size="auto")` reproduces the manual, known-good reference
(`with_scenarios` + `group_by("scenario_id").agg(pl.col("pv_net_cf").sum())`) **bit-for-bit**
(max abs diff = 0.0 across 8 scenarios; verified in `test_auto_loop_equals_manual_reference_n8`).

**Decision: Phase B and Phase C use `for_each_scenario(auto)` / `ScenarioRun.run(auto)`. No
`itertools.batched` fallback is needed.**

Two API facts pinned during the spike:
- **`.alias()` must precede `.over()`**: `Sum("pv_net_cf").alias("total").over("scenario_id")`.
  The reverse raises `ValueError: Call .alias(name) before .over(...)`.
- A partitioned aggregation (`.over("scenario_id")`) returns a polars `DataFrame`
  (`{scenario_id, total}`, one row per scenario) on `result.aggregations[alias]`; integer
  `scenario_id` is carried through correctly.

The model adapter (`make_stochastic_model_fn`) maps the loop's `model_fn(af, *, tables, drivers)`
contract onto L5's `main(af, scenario_returns_override=...)`. The loop hands each batch an `af`
already carrying its `scenario_id` column; L5's integer-`scenario_id` path (Section 5) looks up
each row's stochastic return.

---

## 2. Profile matrix (24 scenarios × 1,000 model points, L5 stochastic)

| Profile | batch | wall | peak RSS | resolution |
|---|---|---|---|---|
| **auto** | 24 (one batch) | **15.1 s** | **54.8 MB** | `auto_probe` → `auto_cached` on repeat |
| fixed-4 | 4 (6 batches) | 16.0 s | 220.3 MB | `manual` |
| serial-seeded | 1 (`master_seed=2024`) | 21.0 s | 9.0 MB | `manual` |

**Correctness guard:** all three profiles produce identical per-scenario totals to ≤1e-6
relative (differences only in the last 1–2 float digits, from chunk-ordering of the parallel
sum). This is the headline safety property — the batch size never changes the answer.

**Observations:**
- `auto` chose a single batch of all 24 scenarios and was both the **fastest** and the
  **lowest-RSS** profile — it sized to fit the whole set in the RAM budget.
- `fixed-4` matched `auto` on wall but used **4× the peak RSS** (more live intermediates per
  batch than auto's probe deemed necessary here at this small scale).
- `serial-seeded` (batch=1) is ~39% slower but has a tiny 9 MB footprint — the bounded-memory
  extreme. `master_seed` worked cleanly at batch_size=1.
- The repeat `auto` run resolved to `auto_cached` (the learned calibration cache served the
  probe result), confirming the PR #106 cache path is exercised.

---

## 3. Throughput basis for grid sizing

`auto`, 24 scenarios × 1,000 points, 15.1 s ⇒ **~0.63 s per scenario at 1K points** locally
(equivalently ~1,600 model-point-projections/sec for this L5 stochastic configuration). Scaling
is ~linear in `scenarios × points`, so a single **100K-point** projection ≈ **~63 s locally**.

---

## 4. Phase B grid calibration

Extrapolating §3 to the originally-specified grid (local seconds; CI `ubuntu-latest-m` is
slower — treat these as a lower bound):

| Cell | point-projections | est. wall (local) | verdict |
|---|---|---|---|
| 10 × 1K | 10K | ~6 s | ✅ |
| 100 × 1K | 100K | ~63 s | ✅ |
| 1,000 × 1K | 1M | ~10.5 min | ✅ (headline scenario count) |
| 10 × 10K | 100K | ~63 s | ✅ |
| 10 × 100K | 1M | ~10.5 min | ✅ |
| ~~100 × 10K~~ | 1M | ~10.5 min | ⚠️ feasible but redundant with 10×100K |
| ~~100 × 100K~~ (original) | 10M | **~100 min locally** | ❌ blows 120-min CI budget |
| 1,000 × 100K (always-excluded) | 100M | ~10 hr | ❌ excluded |

**Revision applied to `run_scenario_benchmarks.GRID`:** the portfolio arm is reduced from
100 to **10 scenarios**, giving a 5-cell grid:

```
scen-scaling (fixed 1K pts):   10, 100, 1000 scenarios
port-scaling (fixed 10 scen):  10K, 100K points
```

Total estimated local wall ≈ 23 min (10×100K is the dominant cell). With the 100K-point
generation step and probe overhead, this fits the 120-min CI job with comfortable headroom even
if CI runs 3–4× slower than local.

Both headline stories are preserved: **1,000 scenarios** (scenario-scaling arm at 1K pts, where
peak RSS should stay flat as the scenario count climbs) and **100K model points** (portfolio arm).
The portfolio-arm scenario count (10) is the conservative choice for the **first** live dry-run
(Phase D.1); once D.1 reports real `ubuntu-latest-m` timings, the 100K cell's scenario count can
be raised if there is budget headroom.

---

## 5. Next

- Phase B implements the 5-cell grid above and publishes `dev/scenario-bench/`.
- Phase D.1 runs the grid on the real runner via the `performance` PR label and confirms the
  budget; expand the 100K scenario count if headroom allows.
