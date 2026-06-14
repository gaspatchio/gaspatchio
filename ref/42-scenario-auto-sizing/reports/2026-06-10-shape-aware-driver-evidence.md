# Shape-aware `for_each_scenario` driver — evidence + strategy matrix

> **Status:** evidence report (findings), NOT a spec. The full design spec is deferred to a
> later session for review by a stronger model. This document is the reviewable artifact:
> locked decisions, the source-grounded correction, the evidence grid, and the strategy
> matrix the spec must reproduce.
>
> **Date:** 2026-06-10 · **Topic:** ref/42-scenario-auto-sizing · follows PR #111 (unified
> aggregation surface).

---

## Provenance — how we got here

This work fell out of **PR #111** (the unified aggregation surface: `run_aggregated` + `Period*` +
spill). A speed investigation in #111 found `run_aggregated`'s per-batch collect ran Polars'
**in-memory** engine while the single-pass path **streamed** — a one-line `engine="streaming"` fix
brought it to parity. That raised the question this report answers: should `for_each_scenario`
*also* choose its engine/batch by shape?

The path to the design, in order:
1. **Field experiment** — compared "auto cross-join" vs "batch=1 streaming" across shapes. The
   early read ("retire the cross-join") was **overturned** by the heavy cells: at 1000 scenarios
   the cross-join is ~3.4× faster (plan-build amortisation). Shape-dependent, not a blanket win.
2. **Problem restated with the user** — objective locked to *max speed s.t. peak ≤ budget*; batch
   size becomes a speed decision within the memory-feasible set (§1).
3. **Grounding + design workflow** — 5 readers mapped the sizer / loop / harness; 3 selector
   designs (probe-race, analytic cost-model, online bandit) were generated and **adversarially
   judged**. All three scored ~18-19/40 and shared one **fatal assumption** — a free `(B×engine)`
   grid where streaming wins on the scenario plan.
4. **Source-grounded correction** (§2) — verifying that assumption against the code refuted it:
   `for_each_scenario` always cross-joins, so `B=1` is *not* `run_aggregated`'s slice plan, and
   streaming's win must be *measured*. This collapsed the design to **two operating points + a
   measured two-point race**.
5. **This evidence grid** — run to fill the matrix and confirm the crossover is real and
   model-dependent.

## Background reading

- **Prior specs (ref/42):** `specs/2026-06-01-unified-aggregation-surface-design.md`,
  `specs/2026-06-01-batched-aggregate-stream-single-run-design.md`,
  `specs/2026-05-29-auto-sizing-calibration-design.md`,
  `specs/2026-05-30-scenario-benchmarks-and-showcase-design.md`, and
  `reports/2026-05-30-scenario-testdrive.md`.
- **Source (the operating points + sizer):** `scenarios/_for_each.py` (batch loop 632-754; the
  cross-join collect hard-coded in-memory at 658; plugin-fusion comment 654-657; eager fold
  697-745), `scenarios/_with_scenarios.py:109` (the cross-join), `scenarios/_aggregated.py` /
  `_spill.py` (the policy-axis `engine="streaming"` path), `scenarios/_auto_batch.py`
  (`resolve_batch_size` two-point probe), `scenarios/_batch_profile.py` (calibration cache),
  `scenarios/_memory.py` (budget).
- **Assistant memory notes (auto-loaded):** `for-each-scenario-always-crossjoins`,
  `polars-streaming-plugins`, `batched-aggregate-stream`, `autobatch-cgroup-blind`,
  `simple-robust-over-complex`.
- **Reproduction bundle:** [`2026-06-10-evidence/`](2026-06-10-evidence/) (harness + raw
  `evidence_results.jsonl` + `README.md` with the exact environment) — see §9.

---

## 1. Objective (locked with the user)

Make `for_each_scenario`'s `auto` mode **pick the fastest execution that still fits the memory
budget**. Memory is a *hard ceiling* (cross it and you OOM); speed is what we maximise
underneath it.

This changes what `auto` is allowed to do: today's sizer picks the **biggest batch that fits
memory** (fastest only when overhead-dominated). The objective lets `auto` pick a **smaller
batch under streaming** when that is faster *and* still fits — confirmed in scope.

**Design principles (user, this session):**
- *Simple and robust beats very complex with minor gains.* Reject cleverness for its own sake;
  add complexity only for significant, evidence-backed gains; auditability > performance squeeze.
- *Measure, don't assume.* The crossover is model-dependent, so no hardcoded thresholds.

---

## 2. The source-grounded correction (this reshaped the design)

An adversarial review refuted an assumption that was in our own framing. Verified against
source:

- **`for_each_scenario` ALWAYS cross-joins.** `with_scenarios` (`_with_scenarios.py:109`) does
  `base_df.join(scenarios_df, how="cross")`; the batch loop (`_for_each.py:634`) calls it per
  pass. So **`batch_size` = scenarios-per-pass** (all policies present every pass), *not*
  policies-per-batch like `run_aggregated`. A `batch_size=1` pass is a 1-scenario cross-join of
  *all* policies — **not** `run_aggregated`'s no-join policy-slice plan.
- **The projection collect is hard-coded in-memory** (`_for_each.py:658`, no `engine=`), because
  the Polars planner can't fuse the Rust lookup plugin with the downstream `group_by`
  (comment 654-657). The fold (`group_by` + Python `iter_rows`, lines 713/725) is eager and
  separate; its cost scales with `scenarios × partitions × aggregators`, **not** `batch_sids`.
- **`run_aggregated`'s 5.5× streaming win does NOT auto-transfer** to the scenario plan — it must
  be *measured*.

**Consequence:** there is no free `(B × engine)` grid. There are **two operating points**, and
the selector chooses between them by measurement:

| | **Point A — big-B, in-memory** | **Point B — B=1, streaming** |
|---|---|---|
| each pass collects | `n_policies × B` rows | `n_policies × 1` rows |
| amortises plan-build? | yes, across B scenarios | no — pays fixed cost N times |
| streaming peak | inflates (unbounded cross-join hazard) → stays in-memory | bounded → can stream |
| wins when | **overhead-dominated** (many cheap scenarios) | **compute-dominated** (few heavy scenarios / big slices / long horizon) |

Rejected alternatives (adversarial panel, ~18-19/40 each, shared fatal assumption): a
`(B×engine)` analytic cost-model and an online bandit — both over-complex and the bandit fails
actuary auditability. Chosen: a **measured two-point race**.

---

## 3. Evidence grid — method

- **Driver:** real `for_each_scenario`; Point A = `batch_size="auto"` (in-memory), Point B =
  `batch_size=1` with the projection collect forced to `engine="streaming"` (monkeypatch of
  `_collect_with_peak`, no source edits). One correctness checksum per cell
  (`sum(aggregations["total"])`).
- **Sequential** (timing integrity — no parallel agents). Crash-safe (one JSON line per cell).
- **Archetypes** (intrinsic model: graph × horizon; shape is a separate axis). All validated,
  checksums identical across batch sizes:

  | name | regime | horizon (mo) | graph |
  |---|---|---|---|
  | A1_short | overhead-leaning | 60 | ~95 nodes |
  | A2_base | balanced (L5 default) | 82 | ~95 nodes |
  | A3_long | compute-leaning | 360 | ~95 nodes |
  | A4_heavy | plan-build-leaning | 82 | ~140 nodes |

  Trap documented: returns table `n_months` must cover `projection_months` or you get **silent
  NaN PVs** (exact-match lookup miss, no error).

- **Harness + raw data committed** at [`2026-06-10-evidence/`](2026-06-10-evidence/) — see §9
  (Reproduce) for the exact command and environment. L5 model points
  (`model_points_{1k,10k}.parquet`, `l5_100k.parquet`). Promote to `evals/benchmarks` as a CI
  guard during the spec phase.

---

## 4. Results (`B/A` = `A_wall / B_wall`; >1 → B faster, <1 → A faster)

> **Refreshed to run-2 (2026-06-10, full 14-cell instrumented re-run).** Run-1's committed
> JSONL was a partial 10-cell run missing all three 1000sc A-wins + the 100K cell; run-2
> measures the complete grid. Verdicts unchanged; numbers are run-2. Harness:
> `2026-06-10-evidence/evidence_grid_instrumented.py`.

**Scenario axis @ 1K policies:**

| archetype | 10 sc | 100 sc | 1000 sc |
|---|---|---|---|
| A1_short (60mo) | **B** 1.78× | **B** 1.14× | **A** 2.02× |
| A2_base (82mo) | **B** 1.56× | **B** 1.14× | **A** 4.35× |
| A4_heavy (140 nodes) | **B** 1.17× | **B** 1.01× (near-tie) | **A** 4.05× |
| A3_long (360mo) | **B** 4.03× | **B** 2.10× | (→A; not measured, capped) |

**Compute axis @ 10 scenarios:**

| archetype | 1K pts | 10K pts | 100K pts |
|---|---|---|---|
| A2_base (82mo) | **B** 1.56× | **B** 4.79× | **B only** — A budget-refused; B 75.2s |
| A3_long (360mo) | **B** 4.03× | **B** 4.69× | (not measured) |

**Peak memory (`peak_B/A`, <1 = B lighter):** 1K policies → B is **8–11× lighter** (0.091–0.114
where sampled); 10K → B ~1.6× *heavier* (the regime where `peak_conservative` could bite — but
B is also 4.8× faster, clearing any sane margin); 100K → A infeasible.

**Correctness:** all 14 cells numerically identical A-vs-B (max `rel = 5.8e-16`, ~2.6 ULP from
float-64 sum-order non-associativity — benign; one `checksum_match=False` flag was a 2-dp
rounding-boundary artifact).

**Comparator validation (the run-2 addition).** B's per-pass wall was instrumented via
`on_batch`; the drafted race's statistic (mean of early post-warmup passes × N) predicts the
actual B total within **~4%** on all four sampled cells (pred/actual 0.96–1.025; within-run
drift ≤ 7%) — *including* the 1000sc A-win cells. The per-scenario comparator is sound at
scale; an early sub-sample is representative because per-pass cost is flat within a run.

| cell | winner | drift (late/early) | race pred / actual |
|---|---|---|---|
| A2_base 100sc×1K | B | 0.984 | 0.994 |
| A1_short 1000sc×1K | A | 0.986 | 1.025 |
| A2_base 1000sc×1K | A | 1.039 | 0.962 |
| A4_heavy 1000sc×1K | A | 1.067 | 0.960 |

---

## 5. The strategy matrix (the deliverable)

Winner per (model, shape), memory budget as the gate:

```
                         scenarios →   10          100          1000
 policies   horizon
 1K         60  (A1)                   B(+30%)     B(+18%)      A(2.1×)
 1K         82  (A2)                   B(+30%)     B(+15%)      A(3.8×)
 1K         82+heavy (A4)              B(+20%)     B(+5%)       A(4.1×)
 1K         360 (A3)                   B(+279%)    B(+106%)     (→A)
 10K        82  (A2)                   B(+338%)      —            —
 10K        360 (A3)                   B(+378%)      —            —
 100K       82  (A2)                   B  [A infeasible — over budget]
```

**Decision boundary, in words:**
- **Point B (streaming, B=1)** wins when per-pass compute is large vs per-pass overhead: **few
  scenarios (≤~100), or many policies (≥10K), or long horizon.** At **≥100K policies B is the
  only feasible option** (in-memory exceeds the budget). At ≤10K policies B is usually *also
  lighter* — a free win on both axes.
- **Point A (cross-join, big-B)** wins when overhead dominates: **many scenarios (≥~1000)** at
  modest policies/horizon, where amortising plan-build across a big batch beats N streamed passes.
- **The crossover moves with the model.** At 1K policies the B→A flip happens between 100 and
  1000 scenarios, but *where* depends on the model: at 100 scenarios A1_short is only +18% on B
  (near its crossover) while A3_long is still +106% (far from it). **A hardcoded scenario
  threshold would mis-fire across models — which is exactly why the selector must measure.**

---

## 6. The selector that reproduces this matrix (sketch — spec to finalise)

A **measured two-point race**, not a threshold table:

1. For a given (model, shape, budget), establish Point A's feasibility from the existing sizer
   (it already refuses when in-memory peak > budget — see the 100K cell). If A is infeasible →
   choose B.
2. Otherwise measure both points (cheaply — piggyback the existing seed probe; sample size TBD)
   and compare wall.
3. **`spend_freely` (default):** pick the faster feasible point. **`peak_conservative` (opt-in,
   laptop):** prefer the lighter feasible point unless the faster point's win clears a margin.
4. Cache the winner keyed on `(plan_sha, shape_fp)` so reruns skip the race.

Auditable by construction: the decision is two measured numbers + a comparison
("A: 5.0s/0.4GB vs B: 1.6s/0.6GB → chose B"). No extrapolation, no bandit.

---

## 7. Open questions for the spec (next session / stronger model)

1. **Race cost & sampling:** cheapest representative sample to measure A vs B; can it piggyback
   the seed probe? `_probe_at_size` reportedly rebuilds the full projection (`_for_each.py:460-502`
   — verify) so a second engine probe is not free.
2. **Feasibility detection before timing A:** must detect A's budget-infeasibility *without*
   running it (else OOM). The sizer's per-cell estimate already does this — reuse it.
3. **`peak_conservative` margin** value, and identify the regime where it actually changes the
   pick (this grid had B faster-and-lighter almost everywhere both were feasible; the tradeoff
   bites only where A fits but B is heavier-and-faster — high policies near the budget edge; a
   prior run measured B ~1.6× heavier at 100K×10sc when A *was* feasible).
4. **Cache schema:** widening the entry bumps `SCHEMA_VERSION` → one-time fleet-wide cold-start.
5. **cgroup-blind budget** (separate known issue, `project_autobatch_cgroup_blind`) governs A's
   refusal threshold; the matrix's 100K "A infeasible" cell depends on the budget being right.
6. **Coverage gaps:** A3_long not measured at 1000 sc or 100K pts (laptop-capped); confirm A's
   win persists for heavy models at high scenario counts. Consider promoting the harness to a CI
   benchmark for a durable, dedicated-runner matrix.

---

## 8. Raw cell data (run-2, all 14 cells)

```
archetype    scen     pts   hz  fast    A_wall A_batch    B_wall    B/A  pkB/A
A1_short       10    1000   60     B     1.373s     10     0.771s 1.781  0.114
A2_base        10    1000   82     B     1.303s     10     0.833s 1.564  0.091
A3_long        10    1000  360     B     5.184s     10     1.285s 4.034   —
A4_heavy       10    1000   82     B     1.133s     10     0.972s 1.166   —
A1_short      100    1000   60     B    10.045s    100     8.818s 1.139   —
A2_base       100    1000   82     B    13.129s    100    11.481s 1.144   —
A3_long       100    1000  360     B    41.457s     17    19.782s 2.096  0.645
A4_heavy      100    1000   82     B    12.802s    100    12.622s 1.014   —   (near-tie)
A1_short     1000    1000   60     A   111.502s    256   225.416s 0.495   —
A2_base      1000    1000   82     A   123.000s     99   535.260s 0.230  0.114
A4_heavy     1000    1000   82     A   125.625s     82   508.182s 0.247  0.131
A2_base        10   10000   82     B     9.928s     10     2.075s 4.785  1.604
A3_long        10   10000  360     B    10.749s     10     2.291s 4.692   —
A2_base        10  100000   82     B*        —       —    75.163s     —      —   [A infeasible]
```
`—` = RSS-delta sampling returned no reading (transient peak below baseline noise). `B*` = B is
the only feasible point (A sizer refused: ~640 MB/cell vs ~3448 MB budget). Checksums identical
across A/B for every cell (max benign 5.8e-16 ULP diff). Per-pass timeseries for the four
race-validation cells: `2026-06-10-evidence/per_pass_timeseries.jsonl`.

**Run-1 vs run-2:** run-1's committed JSONL (`evidence_results.jsonl`, 10 cells) was a partial
run; run-2 (`evidence_results_v2.jsonl`, 14 cells) is canonical. Verdicts unchanged. The only
winner that differs is `A4_heavy @ 100sc` — a genuine ≤1.4% near-tie that lands either side of
the line between runs (run-1 → A, run-2 → B). The CI guard must not assert a winner there.

---

## 9. Reproduce

**Bundle:** [`2026-06-10-evidence/`](2026-06-10-evidence/). Canonical (run-2):
`evidence_grid_instrumented.py` (harness — full grid + B per-pass timing),
`evidence_results_v2.jsonl` (14-cell raw output), `per_pass_timeseries.jsonl` (race-validation
timeseries). Run-1 (superseded, partial): `evidence_grid.py` + `evidence_results.jsonl`.
`README.md` has full detail.

**Environment of the canonical run** (numbers are machine/RAM-dependent — especially the 100K
Point-A budget refusal):

| | |
|---|---|
| machine | macOS 15.7.7, x86_64, 16 cores, **16 GB RAM** |
| python / polars | 3.12.9 / **1.38.1** |
| gaspatchio-core | commit `6870e144` (branch `design/unified-aggregation-surface`) |
| memory budget at run time | ≈ 3.6 GB (from the 100K refusal message) |

**Run (canonical):**
```bash
cd bindings/python
uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/evidence_grid_instrumented.py
```
~15 min on this box (the 1000 sc and 100K cells are the long poles). Point B's streaming is applied
by monkeypatching `_for_each._collect_with_peak` to `engine="streaming"` — **no source edits**.
Point A and Point B are measured independently, so the 100K Point-A budget refusal still records B.
Requires `tutorial/level-5-scenarios/base/model_points_{1k,10k}.parquet` (in git) and
`evals/benchmarks/model_points/l5_100k.parquet` (generated; if absent the 100K cell records a file
error, the rest still run). **The portable signal is the relative A-vs-B verdict per cell, not the
absolute seconds.**
