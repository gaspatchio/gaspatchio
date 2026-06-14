# Adversarial review of the two-point-race draft design — findings digest

> Source: 5-lens finder + partial 3-angle refutation panel (workflow `wf_268badc5-252`,
> killed mid-verify: 96/165 verdicts, 77 confirm / 19 refute). 55 raw findings → deduped
> below. Draft reviewed: `/tmp/gsp_design_review/draft-design.md`. Two findings were
> re-verified directly against committed data by the reviewer (not the agents).

## TIER 0 — RESOLVED by the run-2 measurement (2026-06-10, instrumented harness)

> Both Tier-0 items are **cleared**. Harness: `evidence_grid_instrumented.py` (full 14-cell
> grid + B per-pass timing via `on_batch`). Data: `evidence_results_v2.jsonl` +
> `per_pass_timeseries.jsonl`. Same 16 GiB box, polars 1.38.1, commit 6870e144.

**T0.1 — RESOLVED.** All 14 cells now measured in one run. The previously-missing decisive
cells reproduce the matrix: the three 1000sc cells are **A-wins** (A1_short 2.02×, A2_base
4.35×, A4_heavy 4.05×) and 100K is **A-infeasible** (sizer refused: "~640 MB/cell vs ~3448 MB
budget"; B ran at 75.2 s). All 14 cells are numerically identical A-vs-B (max rel-diff
**5.8e-16**, ~2.6 ULP — the one `checksum_match=False` flag was a 2-dp rounding-boundary
artifact, verified benign). `A4_heavy @ 100sc` is a genuine **near-tie** (run-1 flipped to A,
run-2 has B by 1.4%) — the CI guard must NOT assert a winner on near-ties.

**T0.2 — RESOLVED; the simple per-scenario comparator is SOUND.** Instrumented B's per-pass
wall across 4 cells and simulated the drafted race (mean of early post-warmup passes × N) vs
the actual total:

| cell | winner | drift (late/early) | race pred / actual |
|---|---|---|---|
| A2_base 100sc×1K | B | 0.984 | **0.994** |
| A1_short 1000sc×1K | A | 0.986 | **1.025** |
| A2_base 1000sc×1K | A | 1.039 | **0.962** |
| A4_heavy 1000sc×1K | A | 1.067 | **0.960** |

B's per-pass wall is **flat within each run** (drift ≤ 7%), so an early sample × N predicts the
total within **~4%** — including the A-win regime I feared it would mispredict. My original
T0.2 hypothesis (early-cheap / late-expensive drift) was **wrong**; the measurement was still
the right call (it cleared the mechanism rather than assuming it). The between-run gap that
triggered the concern (B per-scenario 0.115 s @100sc vs ~0.51 s @1000sc) is a **level shift
established at run start**, not within-run drift — almost certainly the registered
`inv_returns` lookup table being 10× larger at 1000 scenarios, so every pass's lookup is
costlier from pass #1. The race always measures inside the run it is deciding for, so it
captures whatever level applies. **No comparator change needed in the spec.**

---

### T0.1 (original) Committed evidence is a partial run; the decisive cells are absent
`reports/2026-06-10-evidence/evidence_results.jsonl` holds **10 cells, not the report's 14**.
The 4 missing are exactly the verdict-defining ones:
`A1_short/A2_base/A4_heavy @ 1000sc` (**all three A-wins**) and `A2_base @ 100K` (**the
A-infeasible cell**). So the matrix's two headline claims — *A wins ≥~1000 scenarios* and
*100K ⇒ A infeasible, B only* — are **not backed by the committed bundle**. Additionally
`A4_heavy @ 100sc` shows **faster=A** on disk but **B (+5%)** in the report §4 matrix: the
near-crossover winner **flipped between runs**. (Finders #18, #35, #52, #28.)

### T0.2 The race comparator may be unsound exactly where A wins
Draft §3.5 assumes `total ≈ N × per_scenario_wall`. The report's own §8 raw table shows B's
per-scenario wall is **not** constant in N: A2_base@1K policies goes 0.084 (10sc) → 0.116
(100sc) → **0.484 (1000sc)** — a ~4× rise. A single early B pass (≈0.09–0.12 s) extrapolated
×N predicts B_total(1000) ≈ 120 s, but measured B = **484 s**, while A = 127 s. So a race that
times one B scenario and scales linearly would **under-predict B ~4× and wrongly crown B at
1000 scenarios — the cell A wins by 3.8×.** Either (a) linear extrapolation from a sub-sample
is invalid in the A-win regime (a hole in the drafted mechanism), or (b) B's per-scenario
superlinearity is a measurement artifact and the report's A-win numbers are themselves
unreliable. Unexplained; must be resolved before the selector can be trusted. (Sharper than
finders #34/#47, which circled the cost/keying but not the extrapolation break.)

## TIER 1 — real gaps that reshape spec sections

### T1.1 Hard-ceiling can be violated (the locked objective)
`spend_freely` picks the faster point; if B's measured pass peak exceeds budget, B can still
win on speed — contradicting *max speed s.t. peak ≤ budget*, and asymmetric with A (gated
before it runs). Compounded by: A-infeasible → fall back to B, but B's peak is unknown a
priori, so the fallback can OOM with no guidance, and "warn and continue" lets an over-budget
pick proceed. Need: B over budget ⇒ infeasible; if both infeasible ⇒ raise `IrreducibleCellError`,
don't silently continue. (Finders #22, #33, #43, #44.)

### T1.2 Winner-cache validity bounds (3× critical, all the same issue)
Bounds are on `n_policies` and A's `k` (2×) but **omit `n_scenarios`** — and the evidence's
headline winner flip is along the scenario axis. A winner cached from a 100sc run would be
wrongly reused for a 1000sc run. (See T0.2: the true driver is the n_scenarios↔resolved-k
interaction; bounds need rethinking, not just one more axis.) Also: the reuse bound anchors to
`CacheEntry.n_policies`, which every write-back overwrites → the 2× window creeps; needs a
frozen `race_n_policies`. (Finders #21, #31, #41, #14.)

### T1.3 Calibration write-back corruption
`update_cost` rebuilds `CacheEntry` from scratch → new race fields are wiped each run (#11).
The `(max_batch_peak, batch_used=resolved_size)` pairing computes per-cell cost as
`peak/(batch_used·n_policies)`; when B wins, `resolved_size` semantics break and the learned
cost is corrupted by ~`k_race` (#6, #12, #26, #42). The draft's "only update cost from A
passes" intent is right but under-specified — needs concrete write-back mechanics that keep
the A-sizer's cost model and its source engine in sync.

### T1.4 Audit sidecar ignored
`_run.py:257-274` builds `run_metadata` as a hard-coded dict; the race decision and
`headroom_policy` never reach the governance JSON (`_audit.py`). For an actuarial audit trail
this is the artifact that matters — loguru + a `ScenarioResult` field aren't enough. Extend
the sidecar; bump `AUDIT_SCHEMA_VERSION`. (Finders #2, #17, #23, #51.)

### T1.5 Resolution-label & result-field coherence
`batch_size_resolution` += `auto_race`/`auto_race_cached` is orthogonal to the existing
size-mechanism labels and duplicates `RaceDecision.source`; the mapping is unspecified for
A-infeasible / N==1 / fail-open / cached-k-vs-probed-k (#0, #24). Forced-B=1 currently labels
`"manual"`, so "manual ⇒ no race" is false (#1). When B wins after an A race pass at `k`,
`ScenarioResult.batch_size=1` and `peak_rss_mb` misrepresent the mixed run; `RaceDecision`
lacks the `k` the A measurement used (#3). `winner: "A"|"B"` is opaque across the two race
kinds; the operating engine is invisible on the result (#4).

## TIER 2 — precision / scope

- **T2.1** `n_scenarios==1 → pick B` cites a measurement never taken: no cell isolates engine
  at fixed batch size (A and B differ in *both* batch size and engine), so "streaming won
  every B=1 cell" is unsupported. Fix: N==1 → today's in-memory default, or an explicit
  engine-only race; don't assert B. (#9, #15, #25, #32, #53.)
- **T2.2** `auto + bytes_per_cell` (`auto_calibrated`) path is textually in the race but has
  no cache to hold measurements and no infeasibility signal. (#5, #19, #40, #48.)
- **T2.3** Fail-open *after* real-work race passes have folded scenarios risks **double-folding**
  → silently wrong aggregates. Fail-open target is also undefined once A is infeasible. (#29, #45.)
- **T2.4** `return_full_grid` sink layout changes with the winner (a B-win explodes the parquet
  file count); `BatchSnapshot`/`on_batch`/`progress` semantics with mixed pass sizes
  unspecified. (#49, #50.)
- **T2.5** Cgroup fix has a second consumer: `cache_budget_bytes` also feeds the OOM ratchet in
  the write-back — fine, but call it out. (#16.)
- **T2.6** `headroom_policy` doesn't control headroom; `target_memory_fraction` (adjacent in the
  signature) does — naming/placement. (#8.)
- **T2.7** `_collect_with_peak` docstring rewrite "pairs safely with B=1" overstates the memory
  story the evidence supports. (#10, #20.)

## Refuted / non-issues (sample)
A handful of findings were dismissed by ≥2 verify angles (e.g. duplicate restatements of the
audit-sidecar point counted once; "race_points kind is pure complexity" — partially valid,
folded into T1.5). Full raw set in workflow journal `wf_268badc5-252`.
