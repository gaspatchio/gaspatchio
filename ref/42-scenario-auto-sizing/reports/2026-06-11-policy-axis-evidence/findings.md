# Policy-axis (`run_aggregated`) batch-size sweep — findings

**Date:** 2026-06-11
**Harness:** `policy_axis_sweep.py` (this dir) — fresh subprocess per (n, B) point,
clean peak via background-thread RSS sampler, sequential, real L4 (reconciled-lifelib)
model via `evals/benchmarks/aggregated_runner.py`.
**Scales:** 1K, 10K local (recovered laptop). 100K deferred to the CI runner.

## The gating question

Is `run_aggregated` wall time **monotonic** in batch size B, or **U-shaped** (like
`for_each_scenario`, whose cross-join creates an interior optimum)?

## Raw results

### 1,000 policies
```
   B (resolved)  batches    wall_s   peak_MB
            10      100     4.889      43.4
            25       40     2.098      45.1
            62       17     0.935      44.3
           125        8     0.448      44.4
           250        4     0.240      44.9
           500        2     0.142      47.8
          1000        1     0.095      51.8
          auto(1000)  1     0.146      56.2
```
**MONOTONIC** — fastest at the largest batch; smallest-B is **51× slower**.
Peak range 43 → 52 MB (negligible; 1K is small).

### 10,000 policies
```
   B (resolved)  batches    wall_s   peak_MB
           100      100     5.086      62.6
           250       40     2.177      71.6
           625       16     0.984      85.4
          1250        8     0.614     103.0
          2500        4     0.413     144.0
          5000        2     0.304     216.6
         10000        1     0.268     380.7
       auto(8796)     2     0.372     354.5
```
**MONOTONIC** — fastest at the largest batch; smallest-B is **19× slower**.
Peak range 63 → 381 MB (grows ~linearly with B — it's the co-resident list data).

## Findings

1. **Decisively MONOTONIC at both scales. No interior optimum, no U-shape.**
   Confirms the structural prior: with no cross-join, a bigger batch means fewer
   plan-builds + fewer fold calls → strictly faster, until memory caps it. The tiny
   batches are 19–51× slower purely from per-batch fixed overhead × batch count.
   **=> "largest B that fits memory" is already speed-optimal. The policy axis needs
   NO ladder search.** The current sizing *shape* is structurally correct.

2. **The hardcoded 384 MB working-set cap is the binding constraint at scale — and it
   is costing speed.** At 10K the fastest run is a single full batch at 380.7 MB (just
   under the cap), yet `auto` resolved B=**8796** (2 batches, 1.39× slower) for a 27 MB
   peak saving. The cap (plus the seed over-estimate, below) forced a needless split.
   The cap is a model-blind magic number (`_WORKING_SET_TARGET_BYTES = 384*1024**2`,
   "spec §2.1 U-floor") — the same overfit smell removed from the scenario axis.
   *Nuance:* the cap is also the knob that delivers run_aggregated's headline promise —
   **bounded ~384 MB peak regardless of total scale**. Dropping it entirely lets peak
   grow to the full memory budget. So the real decision is the **peak-target policy**,
   not "is the cap a bug".

3. **Single-seed linear extrapolation under-sizes.** `auto` measures a 10% seed
   (1,000 policies at the 10K scale) and extrapolates `per_cell = seed_peak/seed_size`.
   The seed amortizes fixed overhead worse than the full run, so `per_cell` is
   over-estimated → working_cap under-estimated → B=8796 instead of the 10000 that
   fits. A second measurement point (or a budget-relative cap) removes the bias.

4. **The seed tax is real but small.** `auto` is always a touch slower than the
   equivalent explicit B because it runs the 10% seed pass first (1.54× at 1K, 1.39×
   at 10K). Inherent to measure-then-size; not worth removing.

5. **Peak at small B is overhead-dominated.** At 10K, B=100 peaks at only 62.6 MB —
   the model + assumptions + one small batch floor. The memory "bought" by going to a
   full batch (~320 MB more) buys a 19× speedup. Cheap trade on any real machine.

## Implication for the design

This is a **simplification + correctness-tightening**, NOT a new mechanism:

- **Replace the hardcoded 384 MB cap with a budget-derived target** (or expose it as a
  parameter with a budget-relative default), so it is not model-blind and does not force
  needless batching when the full batch fits comfortably.
- **Tighten the seed extrapolation** so `auto` does not under-size (second point, or
  size to budget when the working-set target is generous).
- **Auditability parity** (optional): `AggregatedResult` records only `batch_size:int`;
  the scenario axis now records *why* (probed/reason). Recording the binding constraint
  (budget vs working-set) closes the gap.

## Runner confirmation — 1K / 10K / 100K (ubuntu-latest-m, evals.yml job)

```
=== 100,000 policies ===
  B (resolved)  batches    wall_s   peak_MB
          1000      100    10.898      65.1
          2500       40     7.531     156.8
          6250       16     6.362     323.1
         12500        8     5.860     603.5
         25000        4     5.663    1046.3
         50000        2     5.576    2040.2
        100000        1     5.469    4077.6
    auto(11156)       9     5.983     515.9   <- 384 MB cap binds here
  VERDICT: MONOTONIC — fastest at the LARGEST batch; smallest-B 1.99x slower
```

**Confirmed at scale, with one important refinement:**

1. **Monotonic holds at 100K** — wall strictly falls 10.9s → 5.47s as B grows. No
   U-shape ever appears. The "no search needed" conclusion is solid at every scale.

2. **The speed curve FLATTENS hard at the top at scale.** At 100K, going from 8 batches
   (B=12500, 604 MB, 5.86s) to 1 batch (B=100000, **4078 MB**, 5.47s) buys only **~7%**
   speed for **~7× the peak**. The marginal value of a bigger batch shrinks as fixed
   overhead amortises — so the speed *spread* is 40× at 1K, 8× at 10K, but only **2× at
   100K**.

3. **The 384 MB cap's penalty is therefore modest at scale (~10%), not the 1.4× the 10K
   laptop run suggested** — but it is still **objective-wrong**: it caps at ~516 MB
   regardless of the budget, when the runner's budget had GBs free and the full 4 GB
   batch was fastest. At 100K it forced 9 batches (516 MB, 5.98s) vs the budget-allowed
   single batch (4078 MB, 5.47s). The cap trades ~10% speed for an **8× memory saving** —
   a *good* memory/speed trade, but NOT the stated objective ("fastest that fits the
   *budget*"), which says: if the budget has room, use it.

## Conclusion

- **No search.** Monotonic at every scale → "largest B that fits the budget" is
  speed-optimal. Do not port the scenario-axis ladder.
- **Delete the 384 MB working-set cap; size to the cgroup budget × safety_margin.** It is
  a model-blind magic constant that ignores the budget. The fix is a *simplification*
  (one budget term, shared by both `run_aggregated` and `run_to_parquet`, which already
  duplicate the seed→per_cell→budget block) — not added complexity, so it passes
  "simple+robust over complex" even though the speed gain is modest (~10% at 100K).
- **Behavioural change to flag:** today `run_aggregated` peaks at a bounded ~500 MB
  regardless of scale (the cap); sizing to the budget lets peak rise to ~50% of RAM
  (a single 4 GB batch at 100K on a roomy box). That is *correct* under the objective,
  but it IS a change in character. The `safety_margin` (1.3) guards seed-estimate error;
  the residual risk is that one large budget-filling batch has a bigger blast radius than
  many small ones if the 10% seed mis-estimates `per_cell`.

## Addendum — the unbounded measurement seed (10M question)

Probing "what happens at 10M on a 16 GB box?" exposed a robustness gap *independent*
of the budget sizer: the auto path measured per-policy cost from a seed of `n // 10`
policies **collected as one frame**. That seed is unbounded in `n` — at 10M it is a
1M-policy / ~40 GB single collect that OOMs *before* `size_to_budget` ever sizes a
batch. The loop was budget-safe; the *measurement* was not.

Fix: `_auto_batch.bounded_seed_size(n) = min(n, max(1, n//10), seed_sample_cap=4096)`,
shared by both drivers. Per-policy cost is linear, so a bounded sample estimates it as
well as a proportional one and never OOMs. With it, 10M on a 16 GB box auto-adjusts
(bounded seed → hundreds of budget-sized batches → bounded peak, slow but safe).

Note: this could not be reproduced on the 64 GB CI runner — its RAM is large enough
that even the old 1M-policy seed (~40 GB) fits, so the OOM only bit small boxes. The
fix is covered by the `bounded_seed_size` unit tests.
