# Shape-aware `for_each_scenario` auto driver — design

Date: 2026-06-10 (rev. 2026-06-11) · Status: design agreed, ready for implementation plan ·
Origin: user ("`auto` should pick the fastest execution that still fits the memory budget —
measure, don't assume; simple and robust beats complex with minor gains; L5 is one of hundreds
of models, don't overfit; we don't need backwards compatibility").

Follows: PR #111 (unified aggregation surface). Evidence:
[`../reports/2026-06-10-shape-aware-driver-evidence.md`](../reports/2026-06-10-shape-aware-driver-evidence.md),
[`../reports/2026-06-10-design-review-findings.md`](../reports/2026-06-10-design-review-findings.md),
and the streaming-batch sweep / probes in
[`../reports/2026-06-10-evidence/`](../reports/2026-06-10-evidence/). Source basis:
`bindings/python/gaspatchio_core/scenarios/` @ `6870e144`.

> **Revision note (2026-06-11).** This supersedes the earlier *two-point race* framing
> (in-memory big-batch "A" vs streaming batch=1 "B"). A streaming-batch sweep showed that the
> two points were a degenerate slice of the real control surface: **streaming dominates
> in-memory on speed, and the real lever is the streaming *batch size*, whose per-scenario wall
> is U-shaped with an interior optimum that moves with the model.** The design below is a
> **measured coarse streaming-batch search with an in-memory floor**. Because we keep **no
> backwards compatibility**, it also **deletes** the existing learn-and-cache auto-sizing layer
> that the measured search makes redundant (§12) — this design is a *net code reduction*.

---

## 1. Objective (locked)

`batch_size="auto"` picks the **fastest execution whose peak memory fits the budget**. Memory is
a **hard ceiling** (cross it and you OOM); speed is maximised underneath it. The crossover is
**model-dependent**, so the choice is **measured per model at runtime — no hardcoded thresholds,
no model-derived constants** (L5 is one of hundreds; see §12).

**Design principles (user):** *simple and robust beats complex with minor gains*; *measure,
don't assume*; *don't overfit to one model*; *no backwards-compat burden*.

---

## 2. Why `batch_size` means scenarios-per-pass

`for_each_scenario` **always cross-joins** policies × scenarios (`_with_scenarios.py:109`;
batch loop `_for_each.py:634`). So `batch_size` is **scenarios-per-pass** (every policy present
every pass), and a `batch_size=1` pass is a 1-scenario cross-join of *all* policies — not
`run_aggregated`'s no-join policy slice. The projection collect is currently in-memory because
the Polars planner can't fuse the Rust lookup plugin with the downstream `group_by`
(`_for_each.py:654-657`); `_collect_with_peak` already accepts an `engine=` argument, so
streaming a pass is a call-site decision.

---

## 3. The cost surface (measured — structure generalises; numbers are L5 illustration only)

Established by the fresh-process streaming-batch sweep (evidence bundle). These are **structural
facts expected to hold for any model**; the specific L5 numbers are *not* design inputs.

1. **Streaming dominates in-memory on speed** in the overhead/moderate regimes (2.3–4.7× across
   the sweep), by amortising per-pass fixed cost (plan-build, table registration) across the
   batch. The old "biggest in-memory batch" point is *both slower and heavier* — it is retired.
2. **Per-scenario wall is U-shaped in streaming batch size** — falls as batching amortises
   overhead, then rises as the streamed cross-join intermediate bloats. **The optimum is
   interior.**
3. **The optimum batch moves across all axes** — more policies → smaller; more scenarios →
   bigger; longer horizon → smaller. No threshold or per-axis rule can place it ⇒ **measure per
   model**.
4. **Memory peak grows steeply with batch** (≈linear-to-superlinear) and with policies. The
   speed-optimal batch is frequently *memory-hungry*, so the budget often caps the batch *below*
   the speed optimum ⇒ the problem is genuinely **constrained: min wall s.t. peak ≤ budget**.
5. **At high policy counts streaming's cross-join peak inflates above in-memory** (the documented
   streaming-cross-join hazard, Polars #20786 — L5 @100K: stream@b1 ≈ 8.4 GB vs in-mem@b1 ≈
   5.3 GB). So **`in-mem@b1` is the lightest possible operating point** — the memory floor —
   even though it is the slowest. This is the *only* role in-memory retains.
6. **Per-pass wall is flat *within* a run** (drift ≤ 7% over 1000 passes) ⇒ an early sub-sample is
   representative ⇒ a cheap runtime measurement suffices.
7. **Logging is not a confound** — DEBUG logging adds ~2–7% (~6 ms/pass), swamped by per-pass
   compute; it does not distort the U-shape or the optimum.

---

## 4. The candidate ladder

Order the operating points by memory (light → heavy) and by speed:

```
memory  (light → heavy):   in-mem@b1  <  stream@b1  <  stream@b4  <  stream@b16  <  stream@b64
speed   (fast → slow):     stream@b_opt  >  …  >  stream@b1  >  in-mem@b1
```

- **Primary lever:** the streaming batch size, searched over a **coarse geometric ladder**
  `LADDER = [1, 4, 16, 64]` (×4 steps), capped at `min(n_scenarios, _SAFETY_CEILING)`.
- **Memory floor:** `in-mem@b1` — a single fallback candidate, used only when no streaming rung
  fits the budget. The common path is pure streaming.

Geometric spacing is deliberate: the U-shape is broad (4× speed swings), so a coarse ladder
brackets the optimum without fine search, and each rung is one real batch (cheap to probe).

**Constants (in `SizingDefaults` — auditable, tunable; *mechanism/safety* constants, NOT
model-fitted optima):**

| constant | default | role |
|---|---|---|
| `LADDER` | `[1, 4, 16, 64]` | geometric streaming-batch rungs to probe |
| `SAFETY_MARGIN` | `1.3` | inflates a measured probe peak before the budget comparison (noise → feasible, never OOM) |

---

## 5. Selector — measured streaming-batch search (per run; NO cache)

For `batch_size="auto"`, free shape (no `master_seed`, not drivers-dict), `N ≥ 2`. Picks the
**fastest candidate whose measured peak fits the budget** — a single objective, no policy knob.

```
budget   = honest cgroup-aware memory budget (§10)
ladder   = [b for b in LADDER if b <= min(N, SAFETY_CEILING)]
probed   = []     # (batch, per_sc, peak) measured on REAL folded passes
for b in ladder (ascending):
    run ONE streaming batch of size b on the next `b` un-folded scenarios  # real work, folded
    record (b, per_sc = wall/b, peak = transient peak of that collect)
    if peak * SAFETY_MARGIN > budget:        # this rung over budget; larger rungs are heavier
        break                                #   → stop probing the ladder
fitting = [r in probed if r.peak * SAFETY_MARGIN <= budget]
if fitting:
    winner = the fitting rung with the smallest per_sc        # fastest that fits
else:                                                         # even stream@b1 won't fit
    run ONE in-mem batch of size 1 (the floor); measure its peak
    if floor.peak * SAFETY_MARGIN <= budget: winner = in-mem@b1
    else: raise IrreducibleCellError(guidance)                # genuinely too big for this box
run the REMAINING un-folded scenarios under `winner`'s (engine, batch)
```

- **Real folded passes, not throwaway.** Each probe batch folds its scenarios into the
  accumulators; the remainder runs the winner. Net probe tax over running the winner from the
  start: the ladder rungs `1+4+16+64 = 85` scenarios (capped at N), ran at non-winning sizes —
  bounded, and *real work* (nothing recomputed). Early-stop on the budget keeps the probe short
  in the high-policy regime (often just b1, b4). Validated from the sweep data: the search lands
  within **0.8% of the oracle optimum at 1000 scenarios** (tax grows only when N is small, where
  the run is short anyway), and beats the old in-memory point by **2.1–4.4×** net of probe cost.
- **Feasibility on measured peak, with a safety margin.** `SAFETY_MARGIN` (> 1) inflates the
  measured transient peak before comparing to budget — conservative, because a single pass
  surviving does not prove headroom for the rest of the run, and peak measurement is noisy
  (§8). Over-estimating peak errs toward the lighter/feasible choice, never toward OOM.
- **Hard ceiling.** The raise protects the *remainder*: if a remainder is still un-folded and not
  even `in-mem@b1` fits → raise `IrreducibleCellError` with actionable guidance (fewer
  policies/shorter horizon/more memory). A run whose probes already folded **every** scenario has
  *completed* (the passes ran without OOM); it never raises on "fit" — there is nothing left to
  protect. Never silently continue an over-budget *remainder*.
- **"Step down" is implicit.** If the speed-optimal batch is over budget, the search simply picks
  the fastest *fitting* rung — smaller streaming batches are lighter, so it steps down the ladder
  naturally before reaching the in-memory floor.

### 5.1 Edge cases

- **`N == 1`** — no search is possible. Run the one scenario once on the **`in-mem@b1` floor** (the
  lightest engine — streaming inflates the cross-join peak at high policy counts, so the degenerate
  single-pass case never OOMs from inflation; speed for one pass is immaterial). No speed claim.
- **Forced `batch_size=1`** (`master_seed`, or drivers-dict — seeds/drivers inject only at
  `batch_size=1`, `_for_each.py:511-516`, `586-603`): the ladder collapses to `{1}`. Candidates =
  `stream@1` and `in-mem@1`; pick the faster feasible one (an engine-only choice). Seeds
  unaffected — engine choice does not touch the RNG.
- **Manual `batch_size=int`** — unchanged. No search, in-memory, user override respected.
- **No broad fail-open.** The selector's only deliberate abort is `IrreducibleCellError` (a
  remainder that cannot fit). `model_fn` errors during a probe pass **propagate** — they are real
  errors and must not be masked. (The earlier two-point revision specified a broad catch-and-continue;
  it is dropped here because the probes ARE the real run, so a swallowed exception would hide a
  genuine model failure. Simpler and more debuggable.)

---

## 6. Why this is safe and auditable

- **No throwaway compute** — probe passes are real folded work on disjoint scenario slices;
  result identity across batch partition *and* engine is measured-identical (run-2: 14/14 cells,
  max rel `5.8e-16`). The winner runs the remainder.
- **The decision is a small table of measured numbers** — `{batch → (per_sc, peak, fits?)}` plus
  the chosen `(engine, batch)` — fully reconstructable from the audit sidecar (§9). No
  extrapolation model, no cache, no bandit, no model-specific thresholds, no policy knob.
- **Known limitation (documented):** per-scenario cost is assumed roughly homogeneous across the
  scenario list; pathologically heterogeneous sets can mislead the per-rung measurement.

---

## 7. The `in-mem@b1` memory floor — evidence basis (honest)

`in-mem@b1` is kept as the single memory-floor fallback. Its justification:

- **Mechanism:** the streaming cross-join inflates peak at high policy counts (Polars #20786) —
  structural, not L5-specific. In-memory materialising one scenario avoids the streamed
  build-side inflation, so `in-mem@b1` is strictly lighter than `stream@b1`.
- **Measured:** one clean fresh-process point — L5 @ 100K×10sc: `in-mem@b1` 5.3 GB vs `stream@b1`
  8.4 GB (1.6× lighter), `stream@b1` 2.5× faster. Dropping the floor would make the genuinely
  memory-constrained case (tight box, or a model heavier than L5, where even `stream@b1` exceeds
  usable RAM) **fail or risk OOM** rather than run slower-but-safely.
- **Why it persists at scale (deferred measurement):** the floor gap is a *per-scenario* property
  (rolling aggregation frees each scenario), so bounded-memory logic says it must hold independent
  of scenario count — only wall scales with N. **Confirming this at 100/1000 scenarios is a
  dedicated-runner measurement** (it OOM/swap-risks a 16 GB laptop) folded into the CI benchmark
  (§11), *not* required to lock this design.

The floor is already minimal — it is *lazy* (only measured/used when no streaming rung fits), so
it adds no speculative cost on the common path.

---

## 8. Peak-measurement reliability (key implementation concern)

The feasibility gate depends on a trustworthy per-probe peak — and we learned peak measurement is
finicky: `peak_rss_mb` as *delta over a warm baseline* under-reads in a long-running process
(it returned `None`/noise in early probes; only a fresh-process absolute sampler was reliable).
For the **runtime** selector (single process, sequential probes), the spec requires:

- Sample the **transient peak during each probe collect** (`_measure_peak_delta` pattern) against
  the RSS *immediately before that collect* — not a once-at-loop-entry baseline.
- Apply `SAFETY_MARGIN` (conservative inflation) so noise errs toward feasible/lighter, never OOM.
- The **monotonic early-stop** (stop probing larger rungs once one is over budget) bounds both
  probe cost and exposure to a mis-measured large rung.
- The hard ceiling (raise if even `in-mem@b1` won't fit) is the backstop.

This is the one area the implementation plan must treat carefully and test against injected
budgets; the benchmark (§11) validates it on real shapes.

---

## 9. API surface

`ScenarioResult` (`scenarios/_result.py`):

- `batch_size_resolution` Literal is **redefined** (no backwards-compat) to `["manual",
  "auto_search"]`. The old `auto_probe` / `auto_calibrated` / `auto_cached` values are removed
  with the machinery that produced them (§12).
- New field `selection: SelectionDecision | None` (None when no search ran — manual, or `N==1`):

```python
@dataclass(frozen=True, slots=True)
class ProbeResult:
    batch: int
    engine: Literal["streaming", "in-memory"]
    per_sc_s: float
    peak_mb: float | None
    fits: bool

@dataclass(frozen=True, slots=True)
class SelectionDecision:
    engine: Literal["streaming", "in-memory"]   # the operating engine, explicit
    batch: int                                   # the operating batch
    reason: Literal["fastest_fitting", "floor", "single_scenario", "forced_b1"]
    probed: list[ProbeResult]                    # the full measured ladder (audit trail)
```

- `ScenarioResult.batch_size` = the winner's operating batch; `peak_rss_mb` keeps its
  whole-loop-delta meaning. `SelectionDecision.probed` records the measured ladder.
- `SelectionDecision`/`ProbeResult` live in `scenarios/_result.py`, exported from
  `scenarios/__init__`. Type stubs (`scenarios/__init__.pyi`) updated; **mypy + pyright +
  stubtest green**.
- **Removed parameters** (no backwards-compat): `bytes_per_cell` and `headroom_policy` are **not**
  added / are removed from `for_each_scenario` and `ScenarioRun.run` (§12).
- Docstrings: `_collect_with_peak`'s scenario-axis paragraph corrected (streaming pairs safely
  with small batches; peak grows with batch and inflates vs in-memory at high policy counts);
  `for_each_scenario` documents the search.

---

## 10. Cgroup fix on the budget path (in scope)

`_for_each.py:521-522` computes the budget as `psutil.virtual_memory().available ×
target_memory_fraction` — cgroup-blind and base-RSS-blind. Route it through
`_memory.memory_budget(target_memory_fraction)` (as the probe path already does). The feasibility
gate (§5) requires an honest budget; the cgroup-blind budget is a tracked pre-existing issue.

---

## 11. CI benchmark (in scope — and carries the deferred floor confirmation)

Promote the streaming-batch sweep harness into `evals/benchmarks/` as a scenario guard that, on a
**dedicated runner** (not a laptop):

- asserts the search picks a near-optimal feasible batch per shape (within ε of the measured
  ladder optimum), **skipping near-ties** to avoid flap;
- asserts checksum identity across batch sizes / engines (tol `1e-12`);
- **confirms the `in-mem@b1 < stream@b1` memory floor at 100K × {10, 100, 1000} scenarios** — the
  measurement deferred from local runs (§7), where the runner's memory headroom makes it safe.

Run heavy cells **sequentially**, capped, never RAM-buffering worker output (operational lesson:
repeated 100K runs saturate a 16 GB box's swap → fork failures). `evals/` is not importable →
keep the sys.path/importlib pattern.

---

## 12. What this DELETES (no backwards compatibility)

The measured-every-run search makes the old *learn-and-cache* auto-sizing layer redundant. Because
we keep no backwards compatibility, these are **removed outright** (not deprecated) — a net code
reduction:

| removed | why it's redundant |
|---|---|
| **`scenarios/_batch_profile.py`** (the whole learned calibration cache: `CacheEntry`, `read`/`write`/`valid`/`update_cost`/`size_from_cost`, `SCHEMA_VERSION`, env-validity, per-user cache files) | the optimum is N/shape-dependent and measured each run — there is nothing stable to cache |
| **the two-point RSS probe sizer** in `_auto_batch.resolve_batch_size` (the `delta(size)=fixed+per_cell·size` linear fit, `_SECOND_PROBE_SIZE`, the calibrated path) | the search measures peak per rung directly; keep only the **"one cell exceeds budget → raise `IrreducibleCellError`"** concept |
| **`bytes_per_cell`** parameter (`for_each_scenario`, `ScenarioRun.run`, `resolve_batch_size`) | a manual calibration hint for the in-memory sizer; the search measures directly |
| **`batch_size_resolution` values** `auto_probe` / `auto_calibrated` / `auto_cached` | replaced by the single `auto_search` |
| **`headroom_policy` / `peak_conservative`** (never shipped) | evidence shows it rarely changes the pick, and the hard ceiling already prevents OOM — a minor-gain knob cut per *simple-and-robust*; the selector has one objective (fastest-that-fits) |

The optimum is **measured every run**, faithful to *measure, don't assume* and *don't overfit to
one model*.

---

## 13. Correctness edges (consolidated)

| Edge | Handling |
|---|---|
| `model_fn` error during a probe pass | propagates (not masked); the only deliberate abort is `IrreducibleCellError` |
| Probes folded every scenario (remainder empty) | run completed → report fastest probed; never raise (§5) |
| No streaming rung fits, in-mem@b1 fits, remainder exists | use the floor |
| Remainder exists and even in-mem@b1 over budget | raise `IrreducibleCellError` (§5) |
| `return_full_grid` + chosen batch | sink granularity follows the winning batch; documented |
| `on_batch` / progress with mixed probe sizes | each probe pass emits a `BatchSnapshot`; `scenarios_done` monotonic; doc that early batch sizes differ during the search |
| Near-tie batches | low-stakes (walls ≈ equal); CI guard skips near-ties |
| `master_seed` determinism under engine choice | engine does not touch the RNG; identical results to float noise |

---

## 14. Testing

- **Unit (pure):** pick-fastest-fitting; ladder construction + caps; feasibility gate with
  `SAFETY_MARGIN`; monotonic early-stop; remainder-empty completes-without-raise; `N==1` floor;
  forced-`b1` engine choice; remainder-exists-nothing-fits raises.
- **Integration (L5 mini-run, 1K policies — laptop-safe):** checksum identity whichever batch
  wins; no-streaming-fits → in-mem floor (tiny injected budget); nothing-fits → raise; audit
  sidecar carries the selection + `AUDIT_SCHEMA_VERSION` bump (audit fields per §9 +
  `_run.py`/`_audit.py`).
- **Static:** mypy, pyright, stubtest — including that the deleted symbols (`_batch_profile`,
  `bytes_per_cell`) are gone with no dangling references.
- **Bench (dedicated runner):** the §11 guard, including the deferred floor confirmation.

---

## 15. Non-goals

- No cache, no cost-model extrapolation, no online bandit, no model-derived thresholds, no fine
  batch search (coarse geometric only), no headroom-policy knob.
- No change to `run_aggregated` / `run_to_parquet` / policy-axis paths.
- No new parallelism. Manual `batch_size` untouched.

---

## 16. Provenance & evidence status

- **Structural claims (§3.1–3.7):** measured on L5 via the fresh-process streaming-batch sweep
  and the logging-overhead probe. Treated as structure, not as design inputs (§12).
- **Selector net speedup (§5):** derived from the sweep data (probe-tax + remainder-at-winner) —
  2.1–4.4× over the old in-memory point, ≤0.8% probe tax at scale. Zero new machine load.
- **The `in-mem@b1` floor at scale (§7):** mechanism (#20786) + one clean 100K×10sc point +
  bounded-memory logic; the 100/1000-scenario confirmation is **deferred to the CI runner**
  (§11) — local 16 GB runs swap-saturate and were abandoned mid-measurement.
- **Audit sidecar / hard-ceiling / cgroup fix:** carried over and re-validated from the
  superseded two-point revision and its adversarial review
  (`../reports/2026-06-10-design-review-findings.md`).
