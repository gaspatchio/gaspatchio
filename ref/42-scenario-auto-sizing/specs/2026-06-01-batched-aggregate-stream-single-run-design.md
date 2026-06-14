# Batched aggregate-and-stream for single runs — design

Date: 2026-06-01 · Status: spike-validated, ready to productize · Origin: user insight
("we have rolling aggregators at the scenario level — could we leverage that for a single
run… aggregate and stream… batch the policies?")

## Problem

At 100K policies the L4 VA model peaks at **~4.66 GB RSS**, of which **~3.8 GB** is
`List(Float64)` data across **126 output columns**, and runs at ~20K pts/s. Per-policy cost
is **2.35× worse at 100K than 10K** (49µs vs 21µs) — the 3.8 GB working set blows past cache,
so the run is **memory-bandwidth bound**. Kernel micro-opts wash out under the streaming
engine, and `[profile.release]` LTO only buys a modest uniform few-%.

But the dominant cost — materialising every per-policy list column — is **pure waste when the
caller only wants aggregate figures** (total cashflows per projection period, PV, reserves —
the common actuarial reporting case). You compute 3.8 GB to then sum it away.

## Spike result (measured, this machine, release build)

Per-period portfolio totals over all `List(Float64)` columns at 100K, three ways
(checksums match to float-reassociation; see `/tmp/gsp_perf/agg_spike.py`):

| approach | peak RSS | time |
|---|---:|---:|
| full materialise + aggregate (status quo) | 4486 MB | 21.4s |
| terminal aggregation in the lazy plan ("let Polars stream it") | **5800 MB** | 56.7s |
| **batched aggregate-and-merge, K=10** (10K/batch) | **812 MB** | **8.5s** |
| K=20 (5K/batch) | 508 MB | 11.1s |
| K=50 (2K/batch) | 308 MB | 23.4s |

**Headline: at K=10, 5.5× less peak RSS (4.66 GB → 812 MB) AND 2.5× faster (21.4s → 8.5s)** —
both goals at once. The speed-up is the cache-fit killing the superlinearity; the memory cap
is the batching. Tunable down to ~308 MB.

### Two findings that shaped the design

1. **Polars will NOT do it for you.** Terminating the model in the aggregation and collecting
   streamed *worse* (5.8 GB). The Rust lookup plugin + the dependent ~54-node `with_columns`
   chain prevent the optimizer from pushing the cross-row `group_by/sum` back through the
   chain; the per-policy intermediates must coexist. **Explicit policy-batching is required.**
   (`for_each_scenario` already concedes this — it eagerly `collect()`s each batch for the
   same reason.)
2. **The aggregation must be per-column explode, not all-at-once.** `DataFrame.sum()` returns
   *null* for list columns (no native element-wise across-row list sum), and exploding all 58
   columns together rebuilds a **2.2 GB long-form frame per batch** — erasing the win (first
   attempt peaked at 4.8 GB). The working reduction is, **per column**:
   `explode([period, col]) → group_by(period) → sum`, where `period = int_ranges(col.list.len())`
   (this also handles **jagged** per-policy timelines correctly by aligning on period index).

## Design: reuse the scenario machinery over policy batches

The `for_each_scenario` bounded-memory loop is **already** the right topology — it just drives
over scenarios. We add a thin single-run driver that drives the same skeleton over policy
row-slices.

### Reuse verbatim (no change)
- `_chunks` (generic list slicer) — `scenarios/_for_each.py`
- `_collect_with_peak` / `_measure_peak_delta` (materialise one batch, sample peak RSS)
- `resolve_batch_size` + `_batch_profile` (RSS-budget batch sizing — **already keyed per
  policy**: `bytes_per_cell * n_policies * n_periods`) — `scenarios/_auto_batch.py`
- peak-RSS high-water tracking, `BatchSnapshot` / `on_batch` convergence hook
- the result/snapshot shapes

### What changes (two things only)
1. **Batch axis** — replace the scenario cross-join `with_scenarios(af, batch_sids)` with a
   policy row-slice `ActuarialFrame(af._df.slice(start, B))` (no `scenario_id`, no cross-join);
   pass `n_scenarios=1` to `resolve_batch_size` so the batched axis is policies.
2. **The fold** — the existing scalar fold (`group_by([scenario_id,*by]).agg(...) → iter_rows →
   float(value) → add_input`) rejects a list (`Sum.add_input` does `float(value)`). Replace it
   with a **per-period reduction** (per-column explode→group_by(period)→sum) folded into a
   **vector accumulator**.

### The only genuinely new code: per-period vector accumulators
A small additive family alongside the scalar aggregators, accumulator state = `np.float64`
vector of length `n_periods`:
- `PeriodSum`  — init zeros; `add(v) → state += batch_partial`; `merge(a,b) → a + b`
- `PeriodCount`, `PeriodMean` (Welford-stable) — same pattern
- per-period quantile/CTE → route to the existing mergeable **DDSketch** path (do NOT sum
  partials; non-decomposable). Reuse `SignedSketch.merge`.

Per-policy *scalar* PVs (`pv_net_cf`, etc.) reuse the existing scalar `Sum` directly (exactly
additive across batches).

### Proposed API
```python
from gaspatchio_core.scenarios import run_aggregated, PeriodSum

result = run_aggregated(
    model_fn=main,                      # the model's main(af) -> af
    model_points=mp,                    # full portfolio
    aggregations={                      # column -> aggregator
        "net_cf":   PeriodSum(),        # per-period portfolio total
        "claims":   PeriodSum(),
        "reserve":  PeriodSum(),
        "pv_net_cf": Sum(),             # per-policy scalar, portfolio total
    },
    batch_size="auto",                  # RSS-budget sizing, reuses GSP-89
)
# result.net_cf -> np.ndarray[n_periods] of portfolio totals; peak RSS bounded to one batch
```

## Correctness

Sum is associative/commutative and the B-policy batches partition the policy set, so
`batched == full` up to **float reassociation only** (`np.allclose(atol=1e-6)`; cashflows are
well-conditioned, sub-ULP). The authoritative baseline is the full-run per-period total.
Validated in the spike: identical to the float-ordering digits across all K.

## Risks / caveats

1. **Jagged timelines** (`projection.set(per_policy=True)`, now default): lists have unequal
   length → period `t` aligns by index, which is correct for a common-valuation-date grid; the
   reduction must use `explode + group_by(period)` (robust), not native list `.sum()`. Assert a
   common period origin; the L4/L5 reporting case is uniform-origin.
2. **Non-additive aggregates** — per-period median/quantile/CTE only compose via DDSketch;
   support additive `PeriodSum/Count/Mean`, route the rest to the sketch or reject.
3. **Global assumption-table state** — `main()` re-registers tables per batch; registration is
   idempotent (`force_replace`), but the spike must confirm no rising RSS floor across batches.
4. **Mean/Var/Std** via Welford-Chan are stable but not bit-exact across batch size
   (`O(eps·logN)`) — fine for reporting, document it.
5. **API ergonomics** — ship as a thin driver beside `ScenarioRun.run`; do NOT overload
   `for_each_scenario` with a dual scenario/policy axis flag. Share the merge primitive.

## Scope note (honest)

This does **not** speed up producing the *full per-policy output* (that genuinely needs the
3.8 GB). It's transformative only for the **aggregate-reporting** path — but that's the common
valuation/reporting case, and it's the one big 100K lever found (kernel opts washed out;
LTO is ~few-%).

## Next steps
1. Productize the spike into `run_aggregated` + the `PeriodSum` family (reuse `_for_each`
   skeleton; ~1 new module + driver).
2. Wire `batch_size='auto'` to the existing RSS-budget picker.
3. Add a batched-vs-full equivalence test (per-period `np.allclose`) + an RSS-cap test.
4. Reproduce: `/tmp/gsp_perf/agg_spike.py` (modes: naive / lazy / batched).
