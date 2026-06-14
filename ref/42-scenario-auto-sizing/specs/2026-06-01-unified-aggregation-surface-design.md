# Unified aggregation surface (scenario + policy axes) — design

Date: 2026-06-01 · Status: design agreed, ready for implementation plan · Origin: user
("the same set of primitives around aggregation — same API surface — for both scenarios
and single runs")

Extends: [`2026-06-01-batched-aggregate-stream-single-run-design.md`](2026-06-01-batched-aggregate-stream-single-run-design.md)
(the spike-validated approach + measurements). That doc proves *that* batched
aggregate-and-stream works (5.5× less RSS, 2.5× faster at 100K). **This** doc resolves the
five caveats it left open into a buildable design, and folds the result into a single
aggregation vocabulary shared across two drivers.

---

## 1. The organising idea: the aggregator is the primitive, the driver is the axis

There is **one aggregation vocabulary** and **two sibling drivers** that differ only in
what they fan out over:

| driver | fans out over | a "cell" is | exists |
|---|---|---|---|
| `for_each_scenario(...)` | the **scenario** axis | one scenario's projection | yes (GSP-101) |
| `run_aggregated(...)` | the **policy-batch** axis | one batch's projection | **new** |

Both take the **same `aggregations=[...]` list of aliased aggregators**, draw from the
**same family**, and return the **same result shape**. Adding the per-period aggregators
therefore enriches *both* drivers at once.

### What unifies and what does not

**Unified (the aggregation surface):**
- the aggregator classes (`Sum`, `Mean`, `CTE`, `Quantile`, … **and** `PeriodSum`,
  `PeriodMean`, `PeriodQuantile`, …),
- the invocation shape (`aggregations=[Agg(col).alias(name), …]`),
- the merge primitive (`merge_accumulators`),
- the result shape (`{alias: ndarray[n_periods] | scalar}` + run metadata).

**Axis-specific (the driver's job, legitimately different):** how each driver feeds the
model. `for_each_scenario` cross-joins a `scenario_id` and injects shocked `tables=`;
`run_aggregated` row-slices the portfolio and calls plain `model_fn(af_batch)` that loads
its own tables. This is a *driver* concern, not an *aggregator* concern — so it is not a
contradiction of "same surface."

> **Not** a single entry point with an `axis=` flag. Two named drivers (per the prior
> spec's "do not overload `for_each_scenario`"), sharing one vocabulary.

### Architecture: period aggregators are first-class in the Aggregator Protocol (Approach A)

The existing aggregators (`_aggregators.py`) implement `create_accumulator / add_input /
merge_accumulators / extract_output` and are **scalar-valued** — each reduces a cell to one
number via a scalar `within_expr()`. The per-period aggregators need **vector-valued**
state (length `n_periods`) and a reduction that isn't a scalar `within_expr`. We keep the
Protocol verbatim and add **one** optional seam:

```python
class VectorAggregator(BaseAggregator):
    # create_accumulator / add_input / merge_accumulators / extract_output : SHARED Protocol
    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Partial: ...   # the ONE new seam
```

The driver prefers `batch_reduce` when present (vector path); else it uses the existing
scalar `within_expr` path. **Crucially, `batch_reduce` is axis-agnostic** — it reduces *a
cell's frame* to a per-period partial and does not care whether the cell is a scenario or a
policy batch. That single property is what lets `PeriodSum` run unchanged in *both*
drivers.

Rejected alternative — **driver-owned reduction** (the driver bakes
`explode→group_by→sum` inline, "aggregator" is just a tag): smaller surface, fastest
additive-only v1, but a second aggregation vocabulary that doesn't share the Protocol,
no natural home for per-period quantiles, and no path to reuse on the scenario axis.
Rejected because it forfeits exactly the unification this design is built around.

---

## 2. The unified API

```python
from gaspatchio_core import (
    run_aggregated, for_each_scenario,
    PeriodSum, PeriodMean, PeriodMin, PeriodMax, PeriodCount,
    PeriodVariance, PeriodStd, PeriodQuantile, PeriodMedian, PeriodCTE,
    Sum, CTE,                       # scalar family, reusable here
)

# POLICY axis — per-period portfolio figures, bounded memory.
result = run_aggregated(
    model_fn=main,                  # plain main(af) -> af; loads its own tables
    model_points=mp,                # full portfolio
    aggregations=[
        PeriodSum("net_cf").alias("net_cf"),
        PeriodSum("claims").alias("claims"),
        PeriodQuantile("net_cf", levels=[0.95]).alias("net_cf_p95"),
        Sum("pv_net_cf").alias("pv_net_cf"),        # per-policy scalar -> portfolio total
    ],
    batch_size="auto",              # RSS-budget sizing (GSP-89), reused verbatim
    align=None,                     # jagged-origin control; see §3
)
result.net_cf       # np.ndarray[n_periods]   — per-period portfolio total
result.pv_net_cf    # float                   — portfolio total PV
result.peak_rss_mb, result.wall_time_s, result.batch_size, result.n_policies, result.n_periods

# SCENARIO axis — the SAME period aggregators now work here too (per-period across scenarios).
scr = for_each_scenario(
    af, scenarios, model_fn=main_scn,
    aggregations=[
        PeriodMean("net_cf").alias("mean_path"),    # mean per-period cashflow across scenarios
        CTE("pv_net_cf", level=0.005).alias("scr"), # scalar tail across scenarios (existing)
    ],
)
```

- **Invocation = `list[Aggregator].alias(...)`**, identical to `for_each_scenario`. (The
  concise dict `{col: agg}` was considered and dropped: it cannot express two aggregates of
  one column and would break the shared surface for marginal conciseness.)
- **Driver dispatch per aggregator**: `VectorAggregator` → `batch_reduce(frame, period)`;
  scalar aggregator → existing `within_expr` path. Both fold through the shared `merge`.
- **Naming**: `Period*` prefix — no collision with the scenario `Sum` ("across the axis"),
  and discoverable for LLMs.
- **Home**: implemented in `scenarios/` (reuses `_for_each` skeleton, `_auto_batch`,
  `_aggregators`); **public re-export at top level** so the internal "scenarios for a single
  run" path stays hidden.
- **Result**: `AggregatedResult` mirrors `ScenarioResult` — `{alias: ndarray | scalar}` plus
  `peak_rss_mb / wall_time_s / batch_size / n_policies / n_periods`.

### v1 scope of the period family
`PeriodSum, PeriodCount, PeriodMean, PeriodMin, PeriodMax, PeriodVariance, PeriodStd,
PeriodQuantile, PeriodMedian, PeriodCTE` — **the complete family, including rank-based**
(§4). `Period*` aggregators are **specced for both drivers**; v1 tests/benchmarks centre on
the policy axis, but nothing in the design precludes the scenario axis.

### 2.0 Effective memory limit (cgroup-aware) — the load-bearing robustness fix

Every budget path today reads host RAM and is **cgroup-blind** (`_auto_batch.py:91`
`virtual_memory().available`; `_for_each.py:493` same; `_batch_profile.py:88` `.total`). In a
container capped at 1.5 GB, `psutil` reports the host's (say) 64 GB, the sizer picks a giant
batch, and the kernel OOM-kills inside the cgroup. So **"RAM-safe on many machines" is false
today** in exactly the open-source deployment we target (containers / CI / cgroup limits).
This is the single highest-value fix; *all* budget math routes through it.

```
def effective_limit():
    host = psutil.virtual_memory().available          # host figure, cgroup-blind on Linux
    cg_limit, cg_used = read_cgroup_self()            # walk slice chain to nearest FINITE limit
    if cg_limit is None or cg_limit >= host_physical: # v2 'max', v1 ~9.2EB sentinel, non-Linux
        return host                                   # unlimited
    headroom = cg_limit - cg_used                     # cgroup's OWN accounting (counts sidecars/
                                                      # page-cache) -- NOT cg_limit - own_rss
    return min(host, headroom)                        # fail-open to host on ANY parse error

def budget(fraction, base_rss):                       # base_rss = measured resident interp+tables
    return max(0, fraction * (effective_limit() - base_rss))
```

Two non-obvious points the red-team forced: **(a)** headroom must use the cgroup's *own* usage
(`memory.current` v2 / `memory.usage_in_bytes` v1), walked up to the slice that sets a finite
limit — `cg_limit − own_rss` over-reports by sidecars/page-cache; and treat any limit ≥ host
physical as *unlimited* (the `'max'`/sentinel cases), else a naive parse silently returns to
host RAM. **(b)** Subtract **measured base RSS** (the ~300–500 MB interpreter + assumption
tables already resident) *before* the fraction — `available × 0.5` ignoring it is the commonest
small-box overshoot.

### 2.1 Batch sizing — ONE axis-neutral rule (no throughput tuner)

Both drivers share **one** sizer. A "cell" is a *scenario* for `for_each_scenario` (fat,
~380 MB) and a *policy* for `run_aggregated` (thin, ~80 KB) — the **same formula** works
because `per_cell` is **measured, not assumed**:

```
B = clamp( min(memory_cap, working_set_cap, n_cells), 1, n_cells )
    memory_cap  = floor(SAFETY * (budget - fixed) / per_cell)   # cgroup-real -> never OOM
    working_cap = floor(working_set_target / per_cell)          # throughput-incidental; inf for spill
```

The cap that **binds tells you the machine**: tight/CI/cgroup boxes bind on `memory_cap`
(safety); roomy boxes bind on `working_set_cap` — a fixed ~256–512 MB working-set target that
lands *near* the measured U-floor **without ever measuring throughput**. That static cap banks
the headline win (4486 MB/21.4 s → 812 MB/8.5 s ≈ 5.5× RSS, 2.5× speed); the deleted hill-climb
chased only the last few-% increment.

- **`per_cell` from two REAL batches.** Fit `fixed + per_cell·k` from two *real*
  (folded/spilled) batches near the operating size — zero wasted compute. Keep the **two-point
  affine structure** (a single batch re-creates the documented single-point trap,
  `_auto_batch.py:28-30`, and mis-attributes ~100 MB fixed table/warm-up cost to `per_cell` on
  the fat axis); only the **throwaway micro-probe at k=1,4 is deleted**.
- **First-batch ceiling + ramp.** The first real batch always runs at
  `min(B, ABS_FIRST_BATCH_CEILING)` of *measured list-data*, then ramps — so a mis-measured
  `per_cell` can never size one catastrophic, uninterruptible `.collect()`. `_SAFETY_CEILING=256`
  is dropped as a thin-cell sizing constraint but **retained as an absolute fat-cell backstop**
  on the scenario axis; its warning re-points to the *over-sizing* case (B large AND `per_cell`
  suspiciously small).
- **Fail loud, never silently OOM.** If `B == 1` and one cell still exceeds the budget (e.g. a
  380 MB scenario cell on a <1 GB cgroup box), raise `IrreducibleCellError` with actionable
  guidance — never warn-and-collect into a kernel kill.
- **Cache = optional seed only.** The on-disk `_batch_profile` cache is demoted to a fail-open
  *seed* that never gates safety, re-keyed on the **effective (cgroup-aware) cap** — so a `B`
  learned under a 32 GB cap is never reused under a 2 GB cap. Two user knobs stay:
  `target_memory_fraction` and the explicit `batch_size=int` escape hatch.

**Deliberately NOT done** (avoided cleverness): no online hill-climb / U-curve-unimodality
assumption / ~80 KB-per-policy magic seed / policies-per-second timing / `B*` cache field; no
single-point probe; no removing both guardrails at once; no cross-axis (policy-within-scenario)
splitting to rescue a too-big fat cell — fail loud instead; no async/overlapped spill in v1.

### 2.2 Behaviour across the scale cases

Three regimes, one rule: *fits-one-go* (no batching), *throughput-incidental* (working-set cap
binds on roomy boxes), *memory-bound* (memory cap binds on tight/cgroup boxes or fat cells).
Full-output cases that can't fold use the **same** sizer with `working_set_cap` **off** plus a
**parquet-spill terminal** (write each batch, `del`).

| Case | Binding regime | Batches | Peak RAM | Key point |
|---|---|---|---|---|
| **C1** single, full, 1K–10K | fits-one-go (roomy) / spill (tight) | 1 · a few | ~800 MB / one batch | No-op **only on a roomy box**; on a 2 GB/cgroup box a 10K *full* output shares C2's spill path. |
| **C2** single, full, 100K–1M (OOM) | memory-bound (spill) | ~10–100 · ~100–1000 | one batch → parquet | Can't fold; spill each batch to disk. The policy-axis sink is **new code**, not "reuse" (§7). |
| **C3** single, aggregated, 10K | fits-one-go | 1 | sub-GB | The win is the **fold** (KB accumulators), not batching. |
| **C4** single, aggregated, 100K–1M | throughput (roomy) / memory (tight) | ~3–10 · ~100–200 | **~812 MB** | Headline case. Static working-set cap lands *near* the U-floor — banks 5.5×/2.5× with **no** hill-climb. |
| **C5** scenario, agg, 10K×100 | fits-one-go / light | 1–~10 | ~150–400 MB | Fat cell (~38 MB) handled by the **same formula** — `per_cell` is measured. |
| **C6** scenario, agg, 100K×100 | memory-bound | ~100 | ~one fat cell (~380 MB) | 380 MB is the irreducible unit; on a <1 GB cgroup box → **fail loud**, not kernel-OOM. |
| **C7** scenario, ESG, 100K×10K | compute-bound, memory-safe/cell | ~10K | ~one fat cell (~380 MB) | Memory-safe by construction; wall-clock is intrinsic to ~1e9 cells (no single-box sizer helps). The B≈1 reload tax motivates the deferred table-hoist. |

Both drivers share this one sizer; `for_each_scenario` keeps the fat-cell backstop, and the C2
spill path is the only axis-specific addition.

---

## 3. Caveat 1 — Jagged timelines

**Fact** (`schedule/_schedule.py`, `accessors/projection_frame.py`): jagged
(`per_policy=True`) is the auto-default whenever it applies. `n_periods` is the
portfolio-wide **maximum**; each policy's list is its own horizon. The schedule `_kind`
decides what list-index `t` *means*:

| `_kind` | index 0 = | period `t` = | sum-by-index valid? |
|---|---|---|---|
| `from_calendar_grid` | shared valuation date | calendar period t | ✅ |
| `per_policy_grid` | **shared** start date | calendar period t | ✅ |
| `from_inception` | **each policy's own** inception | policy *duration* t | ⚠️ only if duration totals are intended |

**Reduction (settled, spike-proven, jagged-robust).** Per column:
`explode([period, col]) → group_by(period) → sum`, with
`period = pl.int_ranges(pl.col(col).list.len())`. A 60-month policy contributes only to
periods 0–59; `group_by(period)` aligns everyone at index 0. (No native cross-row
`list.sum()`; it returns null.)

**Merge = pad-and-add (lives in the aggregator).** Because `run_aggregated` row-slices and
each batch builds *its own* timeline, a batch's vector length is *that batch's* max horizon.
`merge_accumulators` zero-extends the shorter vector to the longer and adds; final length =
portfolio max. (Pre-sizing every batch to a precomputed global max would force short-policy
batches onto a needlessly long grid — more compute/RSS — so self-size + pad-add wins.)

**Origin guard — hybrid (chosen).** Index-alignment is only calendar-correct when all
policies share a period origin. Inspect `schedule._kind`:

```python
kind = schedule._kind
if kind == "from_inception" and inceptions_differ(model_points):
    if align != "duration":
        raise ValueError(
            "Inception-aligned timeline: period index is policy DURATION, not calendar "
            "time. Summing across policies mixes calendar periods. Pass align='duration' "
            "to aggregate by duration, or rebuild with a shared valuation grid "
            "(per_policy=False) for calendar totals.")
# from_calendar_grid / per_policy_grid -> shared origin -> proceed
```

*Options considered.* **(a) Strict** (reject all inception books) — safest, but rejects
legitimate by-duration aggregation. **(b) Permissive** (always sum by index, document the
origin) — zero guard code, but an inception book silently yields duration totals that read
like calendar totals (the catastrophic `proj_year` vs `year` class of error). **(c) Hybrid
(chosen)** — correct-by-default for the common case, flexible via `align="duration"`, loud
only on the one genuinely ambiguous case.

---

## 4. Caveat 2 — Non-additive per-period aggregates (rank-based **in v1**)

The period family splits cleanly:

**Rank-free** — `PeriodSum / PeriodCount / PeriodMean / PeriodMin / PeriodMax`. Each is a
single vectorized `group_by(period).<sum|count|mean|min|max>()`; additive merge (sum/count
add, min/max take elementwise extremes, mean via §5). Cheap, jagged-robust.

**Rank-based** — `PeriodQuantile / PeriodMedian / PeriodCTE`. State = `list[SignedSketch]`
of length `n_periods`; merge = elementwise `SignedSketch.merge` (already bit-exact and
commutative). The performance trap, and how we avoid it:

> In `for_each_scenario`, `Quantile` gets **one** `sketch.add()` per *scenario* (thousands
> of adds). Here, period-`t`'s sketch must absorb **one value per policy** — 100K × ~240
> periods ≈ **24M `add()` calls** if done naively. That is the `map_elements` anti-pattern
> at full scale.

**The vectorized build (no per-value Python loop).** `SignedSketch` wraps ddsketch's
`DDSketch`, which supports **weighted** `add(value, weight)`, and splits values into
`pos / neg / zero`. So:

1. In Polars compute `sign`, `|v|`, and `bin =` ddsketch's `LogarithmicMapping.key(|v|)`
   reproduced as an expression (`gamma = (1+ra)/(1-ra)`; same offset; same rounding).
2. `group_by([period, sign, bin]).count()` → each period's histogram in **one pass**.
3. New `SignedSketch.from_binned(...)` loads the histogram by calling
   `add(gamma**key, weight=count)` per bin (the representative `gamma**key` provably
   re-keys to `key`). Calls ≈ *bins per period* (bounded, hundreds), **not** values. No
   store-internal surgery.

**Mandatory correctness gate — bit-exact dual-build test.** Build a sketch via per-value
`add()` and via `from_binned()` on the same data; assert **identical** quantiles. This is
the test that proves the Polars bin expression matches ddsketch's `key()` exactly (a
boundary ULP mismatch would shift bins).

*Options considered.* **(a) rank-free only, hard-reject the rest** — smallest, but leaves
a vague hole. **(b) include rank-based (chosen)** — complete day one; cost is the
`from_binned` bridge + the dual-build test + `n_periods`-sketch memory (bounded). **(c)
rank-free v1 + specced follow-up** — ships the win sooner, defers tails. Chosen **(b)**:
the unified surface is more valuable complete, and Approach A makes the sketch-vector a
real aggregator rather than driver-baked.

**New code here:** `SignedSketch.from_binned(hist)` + the Polars bin-index expression
(validated against the library). Everything else (`merge`, `quantile`, `cte`) already
exists.

---

## 5. Caveat 3 — Global assumption-table state

**Fact** (`assumptions/_api.py:636-650`): registration is
`register_or_replace_table(..., force_replace=True)` — *"Always replace for reentrancy."*
The Rust Arc-swap registry drops old storage at refcount zero. The spike re-ran `l4.main()`
(reload + re-register every table) per batch and held a **stable 812 MB across 10 batches**
— no observed creep.

**Decision — plain contract + standing RSS-floor test (chosen).** `run_aggregated` calls
plain `model_fn(af_batch)` per batch; the model loads its own tables exactly as a normal
run does. Re-registration is idempotent and leak-free. The ~10–30 ms/batch reload is
**~3–6 %** overhead (3.5 % at K=10, ~6 % at K=50) — small against a 5.5×/2.5× win.

Turn the spike's one-off observation into a **standing regression test**:

```python
peaks = [rss_after_batch(i) for i in range(20)]
assert peaks[-1] <= peaks[0] * 1.05      # no rising floor across batches
```

*Option considered & deferred.* A **two-phase contract** (`run_aggregated(model_fn,
tables=...)` / separate `setup_fn`) hoists table loading out of the loop and recovers the
few-%, but forces models to split setup from projection — a heavier contract not all models
follow. Documented opt-in for table-heavy models; not v1.

---

## 6. Caveat 4 — Mean / Variance / Std numerics

**The mean is exact and free.** We already maintain `PeriodSum` (Neumaier-compensated,
order-stable) and `PeriodCount` (exact). So:

```python
PeriodMean := PeriodSum / PeriodCount        # extracted at finalize
```

This is **exactly batch-size-invariant** — the same K-independence as `Sum`, with no
Welford. (Scenario `Mean` uses Welford only because it streams scalar values single-pass;
here we have the sum and count outright.)

**Variance/Std = vector Welford (chosen).** State = `{n, mean, m2}` per period, merged with
the existing `_welford_merge` (Chan parallel), `var[t] = m2[t]/(n[t]-1)`.

*Options considered.* **(a) Welford (chosen)** — stable for any data, reuses
`_aggregators.py` verbatim, consistent with scenario `Variance/Std`. *Not* bit-exact across
**different** K (`O(eps·log N)` ≈ 1e-13 relative drift); same K is fully reproducible.
Documented. **(b) Sum + SumOfSquares** — bit-exact across any K (pure additive), but
catastrophic cancellation when variance ≪ mean² (stable premium streams) — rejected as a
default. **(c) `exact=True` flag** offering (b) on demand — a documented later opt-in if
cross-K bit-reproducibility is ever required; not v1.

Drift is far below display precision and model/MC noise, for a diagnostic figure — so the
default favours stability over cross-K bit-exactness. The mean stays exact regardless.

---

## 7. New code vs reused

**Reused verbatim**
- `_for_each.py` skeleton: `_chunks`, `_collect_with_peak` / `_measure_peak_delta`,
  peak-RSS high-water tracking, `BatchSnapshot` / `on_batch`.
- `_batch_profile` on-disk calibration cache **structure** (per-`(plan_sha, shape_fp)` JSON,
  prune, fail-open) — kept, but **demoted to an optional seed** that never gates safety and
  **re-keyed on the effective (cgroup-aware) cap**, not host `.total` (§2.0–2.1).
- `_auto_batch.resolve_batch_size` **two-point affine structure** (`fixed + per_cell·k`) — kept
  (it correctly separates fixed from marginal cost); **generalized axis-neutral** (`n_cells` +
  per-cell dims) and re-pointed at real batches. Only the throwaway micro-probe at k=1,4 is
  removed; `_SAFETY_CEILING` is retained as a fat-cell backstop on the scenario axis.
- `_aggregators.py`: scalar `Sum/Mean/CTE/...` (usable directly here), `_welford_*`,
  `SignedSketch.merge/quantile/cte`, the `BaseAggregator` modifier base.

**New**
- `VectorAggregator` base with the `batch_reduce(frame, period)` seam.
- The `Period*` family (vector / list-of-sketch state) in `_aggregators.py`.
- `SignedSketch.from_binned(...)` + the Polars bin-index expression (§4).
- `run_aggregated(...)` driver: policy row-slice instead of scenario cross-join; per-
  aggregator dispatch (vector vs scalar); pad-and-add for vector merges; the §3 origin guard.
- `AggregatedResult` (mirror of `ScenarioResult`).
- **Unified sizer** (§2.0–2.1): cgroup-aware `effective_limit()` routed through *all* budget
  paths + base-RSS subtraction + `B = min(memory_cap, working_set_cap, n_cells)` with a
  measured two-real-batch `per_cell`, a first-batch absolute ceiling + ramp, and
  `IrreducibleCellError` on an irreducible over-budget cell. Defaults live in **one documented
  module-level dataclass** (auditable; no scattered magic constants). *No* throughput tuner.
- **Policy-axis parquet sink** for the full-output spill path (C1-tight / C2): **new code**,
  not reuse — fix `_for_each.py:693`'s hard-coded `sort("scenario_id")`, refuse tmpfs/RAM-backed
  targets, temp-in-same-dir atomic rename, preflight disk space.
- Top-level public re-exports.

---

## 8. Test plan (the gates)

1. **Batched == full equivalence** — per-period `np.allclose(atol=1e-6)` of every
   `Period*` output vs a single full run, across K ∈ {1, 10, 50}.
2. **RSS cap (effective limit)** — peak RSS ≤ the **effective (cgroup-aware) budget**, not
   host RAM, for the chosen batch; the headline 100K case ≲ 1 GB.
3. **RSS floor** — §5 standing no-creep test across ≥20 batches.
4. **Sketch dual-build** — §4 bit-exact `add()` vs `from_binned()` quantiles (the
   correctness gate for rank-based).
5. **Mean cross-K exactness** — `PeriodMean` identical across K (proves Sum/Count path).
6. **Jagged origin guard** — `from_inception` with differing inceptions raises without
   `align="duration"`; `per_policy_grid` / `from_calendar_grid` proceed; pad-and-add
   correctness on unequal batch lengths.
7. **Shared-surface smoke** — a `Period*` aggregator runs unchanged in `for_each_scenario`
   (per-period across scenarios), proving the axis-agnostic seam.
8. **cgroup cap respected** — a simulated cgroup limit (faked `/sys/fs/cgroup` root injected
   via a path param, *not* a monkeypatched constant) forces a small B that is **never
   exceeded**; the `'max'` / sentinel "unlimited" cases fall back to host.
9. **Spill safety** — the policy-axis sink refuses a tmpfs/RAM-backed target and preflights
   disk space (fails loud before batch 1); cross-FS atomic rename works.
10. **Irreducible cell fails loud** — one fat cell over the effective budget raises
    `IrreducibleCellError` with guidance, never a kernel OOM-kill.
11. **Small-N single batch** — a portfolio under the working-set target runs in one batch
    (auto is a no-op); the cache seed only shrinks B, never grows it.

---

## 9. Scope & follow-ups

**In v1:** the full `Period*` family (incl. rank-based) on the **policy axis** via
`run_aggregated`; the scalar family reusable in it; the shared invocation + result; the
**unified cgroup-aware sizer** (§2.0–2.1); the eleven gates above.

**Sequencing (deliver safety first, keep the change honestly small).** (1) ship cgroup-aware
`effective_limit()` + base-RSS subtraction + first-batch ceiling **alone** — the genuine
robustness win, small, gated by a real-cgroup test; (2) delete the throughput tuner (pure
subtraction); (3) keep the existing two-point probe, re-pointing its probes at real batches
**only if** measurement shows the micro-probe noise floor actually bites on the thin axis;
(4) consolidate every constant into one documented defaults dataclass.

**Specced, lighter v1 emphasis:** `Period*` on the **scenario axis** in `for_each_scenario`
(gate 7 proves the seam; broader scenario-axis tests can follow).

**Decided (§2.0–2.1):** both drivers share **one cgroup-aware memory-safety sizer**
(`B = min(memory_cap, working_set_cap, n_cells)`; effective cgroup limit; base-RSS subtraction;
two-real-batch affine `per_cell`; first-batch ceiling + ramp; `IrreducibleCellError` on an
irreducible cell). **No throughput tuner** — the static working-set cap banks ~all the win,
and the online hill-climb assumed a U-curve unimodal across hardware the project cannot test
(reversed after the scaling-challenge workflow, on the robustness-over-perf priority).

**Deferred (documented opt-ins):** two-phase table-hoist contract (§5); `exact=True`
sum-of-squares variance (§6).

**In scope via spill (C1-tight / C2):** the full per-policy output path is made *memory-safe*
(not faster) by the same sizer with `working_set_cap` off + a parquet-spill terminal — peak
bounded to one batch, the deliverable streamed to disk.

**Out of scope:** *speeding up* the full-output path (it genuinely needs the 3.8 GB);
horizontal scaling for C7's intrinsic ~1e9-cell wall-clock (single-box sizing can't help it);
cross-axis policy-within-scenario splitting to rescue a too-big fat cell (we fail loud).

---

## 10. References
- Spike + measurements: [`2026-06-01-batched-aggregate-stream-single-run-design.md`](2026-06-01-batched-aggregate-stream-single-run-design.md)
- Aggregators / sketch / Welford: `scenarios/_aggregators.py`, `scenarios/_sketch.py`
- Bounded-memory loop + batch sizing: `scenarios/_for_each.py`, `scenarios/_auto_batch.py`,
  `scenarios/_batch_profile.py`
- Jagged timelines: `schedule/_schedule.py`, `accessors/projection_frame.py` (#108)
- Table registry: `assumptions/_api.py`
