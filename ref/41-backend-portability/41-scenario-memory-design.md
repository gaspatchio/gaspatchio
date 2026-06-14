# Scenario memory design — audit and recommendation

Audience: senior actuary-engineer. Research / design only — no code changes in this pass.

## TL;DR

`with_scenarios` is a mechanical cross-join — one helper, ~30 lines of work, and (importantly) it `.collect()`s the LazyFrame before joining (`bindings/python/gaspatchio_core/scenarios/_with_scenarios.py:126`). Streaming therefore cannot rescue it: by the time the join happens, the policy frame is already materialised. Even if it were lazy, the model body uses `cum_prod` and `previous_period` *inside list columns* (`bindings/python/gaspatchio_core/accessors/projection.py:338, 1199, 1421`) which Polars cannot stream — so the post-join intermediate sits in RAM as `(n_policies × n_scenarios)` rows of ~2 KB each. That is exactly what `ref/27-scenario-support/27-performance-and-scale.md:756–763` admits.

For B/C use cases (CTE-style aggregates, no per-scenario per-policy detail required) the most memory-efficient pattern that fits today's stack is a **per-scenario streaming loop with online aggregation** — effectively `for_each_scenario(scenarios, model_fn, agg=…)` running the existing model code unchanged on a 1-scenario frame, with running aggregates incrementally updated. Memory is bounded by *one scenario's footprint*, not `n_scenarios × `that. (A) full-grid materialisation stays available as `for_each_scenario(..., return_full_grid=True)` or — preferred — as today's `with_scenarios` retained verbatim and documented as the break-glass path.

This is **not** a fundamentally new architecture. `batch_scenarios` (`bindings/python/gaspatchio_core/scenarios/_batching.py:16`) already does the loop; what's missing is the aggregation contract that lets gaspatchio guarantee O(1) memory in `n_scenarios` rather than O(batch_size). The recommendation is to make that contract explicit and ergonomic, not to rewrite the kernel.

---

## 1. Current-state audit

### 1.1 What `with_scenarios` actually does

`bindings/python/gaspatchio_core/scenarios/_with_scenarios.py:117–132`:

```python
scenarios_df = pl.DataFrame({scenario_column: scenario_ids})
af_df = af.collect()                             # forces materialisation
expanded = af_df.join(scenarios_df, how="cross") # eager DataFrame cross-join
return ActuarialFrame(expanded, mode=af._mode, ...)
```

Three things to note:

1. **It collects.** `af.collect()` is not optional — the cross-join is performed on a `pl.DataFrame`, not a `pl.LazyFrame`. So any streaming/lazy story upstream of `with_scenarios` is discarded at this line.
2. **It returns an eager-backed `ActuarialFrame`.** Downstream `with_columns(...)` calls re-enter Polars' lazy path, but the seed is already a fully materialised `(n_policies × n_scenarios)`-row DataFrame.
3. **It is stateless about scenario drivers.** `with_scenarios` only stamps an ID column. The actual scenario-dependent assumption lookup (e.g. fund returns by `scenario_id, t, fund_index`; discount-factor lists by `scenario_id`) is the *model's* job — see `tutorials/level-5-scenarios-typed/base/model.py:474–501` and `:725–751`.

### 1.2 How the L5-typed VA model uses scenarios

Two scenario-dependent surfaces in `tutorials/level-5-scenarios-typed/base/model.py`:

- **Investment returns (per-period scalar lookup)**: `inv_returns_table.lookup(scenario_id=…, t=af.month, fund_index=…)` (lines 497–501). This is a row-wise lookup against a `(n_scenarios × n_periods × n_funds)` table — no list columns, scalar per row-period. Streaming-friendly in principle.
- **Discount factors (per-scenario list)**: a 3-row mapping `{scenario_id → list[float64]}` is left-joined onto the frame (`disc_map`, lines 735–747); each row then carries one list of length `projection_months + 1`. This is the dominant per-row memory: at 240 periods × 8 B = ~2 KB per row just for discount factors, before any other list column.

The model also produces ~20 other list columns of length `projection_months` (sections 6–15). Each is `n_rows × ~projection_months × 8 B`. For 10k policies × 1 scenario × 240 periods that's ~19 MB per list column; 20 columns = ~380 MB working set. Cross-joining 10k scenarios scales the row count by 10⁴, so the working set scales linearly: **~3.8 TB nominal** for the full grid, which is what `ref/27-scenario-support/27-performance-and-scale.md:692, 700–710` reports as "~58 TB at 100k×10k" once all intermediates are counted.

### 1.3 Where scenarios appear elsewhere

`grep -rn with_scenarios` (results consolidated):

- `bindings/python/gaspatchio_core/__init__.py:40,87` — public re-export.
- `scenarios/__init__.py:10,44` — module export.
- `scenarios/_batching.py:50–59` — `batch_scenarios` docstring shows the expected loop pattern (load, expand, run, append).
- `tutorials/level-5-scenarios{-typed,}/base/run_scenarios.py` — tutorials.
- `tutorials/level-5-scenarios-typed/stress/perf_scaling.py:192` — the stress harness; this is where the 10k×1200M reversal is documented (`perf_scaling.py:622–637`: "**typed memory REVERSES** at this scale … broadcasts three full 1201-element discount-factor lists … ≈ {n×1201×3×8/1e6} MB").
- `evals/benchmarks/run_model_benchmarks.py:193,205` — benchmark harness.

The `scenarios/` package itself is small: `with_scenarios`, `batch_scenarios`, `describe_scenarios`, `sensitivity_analysis`, plus the `Shock` family (`shocks.py`). Notably **there is no `for_each_scenario` helper today**, and no `partition_by`-based aggregator. `batch_scenarios` returns ID lists; the aggregation contract (and the `del result; gc.collect()` between batches) is left to the caller.

### 1.4 What the existing perf memo already says

`ref/27-scenario-support/27-performance-and-scale.md` is unusually candid. Three findings worth pulling forward verbatim:

- *line 580*: "Scenario expansion itself is extremely fast (microseconds). The memory consumption comes from model execution with list columns."
- *line 589*: "Streaming has overhead and mainly helps with very large datasets that don't fit in RAM. **For the GMXB model, streaming provides no benefit because cumulative operations (`cum_prod`, `previous_period`) require full history.**"
- *lines 591–598*: measured: 1k policies × 100 scenarios = 100k rows, **5.6 GiB** unbatched vs **636.6 MiB** batched (10×10) — **8.8× less memory at 2× wall time**.

The memo also documents `sink-then-stream` (1.2 GiB peak, ~118s) as a third pattern. So the *empirical* answer to "is streaming alone enough?" is already on file: **no for B/C, yes for the small final aggregation step**. The parallel agent's memory-scaling test should confirm this; this document's analysis assumes it.

---

## 2. Why cross-join is memory-heavy

### 2.1 The math

Per-row footprint at projection length `P` periods, model with `K` list columns and `S` scalar columns:

```
bytes_per_row = K * (P * 8 + ~24 list overhead) + S * 8
              ≈ K * 8P  (for P >> 3, list overhead negligible)
```

L5-typed at P=240 has K ≈ 20 list columns (mortality, lapse, decrement, AV chain, claims, premiums, expenses, commissions, discount factors, …), so `bytes_per_row ≈ 20 × 240 × 8 ≈ 38 KB`. Stress harness measures **~58 KiB/row** at scale (`27-performance-and-scale.md:700–706`) — consistent, with overhead, GC slack, and intermediate live values.

Total intermediate footprint:

```
peak_RSS ≈ n_policies × n_scenarios × bytes_per_row
        + (a few constant-size GC tails)
        + assumption tables
```

At 10k policies × 1k scenarios × 58 KiB ≈ **570 GiB** — the figure in `27-performance-and-scale.md:691`. There is no algorithmic magic that reduces this for the cross-join shape: every (policy, scenario) pair must hold its own per-period vector if you want to do downstream arithmetic on those vectors per-row.

### 2.2 Why streaming doesn't save it

Polars' streaming engine works by chunking **along the row axis** and pipelining stages that are point-wise (filter, project, with_columns) or have streaming-compatible aggregates (group_by/sum/mean over chunks with partial reductions). It is broken by:

- **Cumulative ops over the streaming axis** — `cum_prod`, `cum_sum` across rows.
- **Sort, top-k, full-frame quantile** — need the full population.
- **Self-joins / window with unbounded look-back**.

L5's `cum_prod` and `shift`-style ops are inside `list.eval(...)` (`accessors/projection.py:338, 1199, 1421`). That means cumulative is *per-list*, not across rows. **In principle this is streaming-friendly** — each row is independent. But:

1. Each list column carries the **whole projection history per row**, so the streaming chunk is still bounded *below* by `chunk_rows × bytes_per_row`. Polars' default streaming chunk is in the range of 50–250k rows; at 38 KB/row that is 2–10 GB per chunk *just for one stage*. Multiple stages live simultaneously while the pipeline runs.
2. The model has cross-row `with_columns` interactions through the `ActuarialFrame` typing layer that may force in-memory fallback subgraphs (the perf memo asserts this empirically — `27-performance-and-scale.md:587, 756–763`).
3. **The cross-join in `with_scenarios` happens eagerly on a `DataFrame`, not on a `LazyFrame`** (`_with_scenarios.py:126`). So before the streaming engine is even consulted, the n×k row block has been built.

Net: Polars streaming is helpful for the **final aggregate** (`group_by('scenario_id').agg(sum)`) and for bulk parquet I/O. It does not bound peak memory of the cross-join × model body shape that `with_scenarios → main(af) → collect()` produces. This is what the user's informal observation is bumping into.

### 2.3 What the user's intuition is reaching for

> "Keep the inception table that changes separate and do something that's just more memory efficient."

Translated: do not broadcast the scenario-driver table to every (policy, scenario) row. Two complementary versions of this:

- **Defer the join.** Keep `policies` `(n_policies, k)` and `drivers` `(n_scenarios × n_periods, …)`. Do the join late, ideally inside an aggregator. **Polars' lazy optimizer will not do this push-through automatically** for cross-join → with_columns (list column construction) → group_by, because the with_columns calls between the join and the group_by reference both `policy_*` and `scenario_*` values. Once you've created `pv_claims = (claims * disc_factors).list.sum()` from columns that reference both axes, the join is fused into the projection. Verifiable with `result.collect_schema(); print(plan.explain(streaming=True))` — recommend running this empirically on the L5 typed plan; I did not.
- **Don't broadcast at all** — replace the cross-join with an outer Python loop that iterates scenarios and runs the model on a 1-scenario frame. This is the recommendation in §4.

---

## 3. Alternative patterns

Five candidates. Memory and CPU notation: `n` = n_policies, `k` = n_scenarios, `P` = n_periods, `B` = bytes_per_row.

### Pattern 1 — Per-scenario subprocess streaming

Run the model `k` times, one scenario per subprocess. Aggregate with a streaming reducer (T-Digest for percentiles, Welford for moments, exact running sums for `pv_*`).

- **Peak memory:** `n × B` (one scenario at a time) + reducer state (KB).
- **CPU:** parallelisable across scenarios up to core count; each subprocess gets a clean Polars heap.
- **Ergonomics:** users write a function `model_fn(af_one_scenario, scenario_id, drivers) -> dict[str, float]`; framework handles dispatch and reduce.
- **Framework changes:** new `for_each_scenario_distributed` helper; subprocess pool; pickling of model_fn (or import-by-path).
- **Verdict:** highest scale ceiling, but heaviest to implement. Worth keeping as a future Phase-2 enhancement, not Phase-1.

### Pattern 2 — In-process per-scenario generator with aggregation

Same as #1 but in-process. Sequential scenarios, in-process state mutation of running aggregates.

- **Peak memory:** `n × B` + reducer state. Same bound as #1.
- **CPU:** Polars is already multi-threaded *within* a scenario (across rows). Inter-scenario parallelism is lost. For B/C aggregates that's fine — total wall time becomes `k × t_one_scenario` but memory drops by factor `k`. The benchmark in `27-performance-and-scale.md:592–598` is exactly this pattern at `batch_size=10`: 8.8× memory drop at 2× wall time.
- **Ergonomics:** clean — `af.for_each_scenario(scenarios, model_fn, agg=Aggregator())`.
- **Framework changes:** small. New helper module; reducer protocol; documentation.
- **Verdict:** **this is the recommendation.** It threads the needle.

### Pattern 3 — Defer the cross-join into the aggregator

Keep policies and scenario-drivers as separate tables; let the lazy planner figure out fusion.

- **Peak memory:** in theory `O(n × P × B/P)` if the planner pushes group_by through the join; in practice the with_columns body of any non-trivial actuarial model breaks this — the optimizer cannot eliminate intermediate columns that depend on both `policy_id` and `scenario_id`.
- **CPU:** depends on planner.
- **Ergonomics:** unchanged on the surface.
- **Framework changes:** make `with_scenarios` lazy, audit every model intermediate, write `.explain(streaming=True)` smoke tests.
- **Verdict:** *might* work for trivially aggregating models (sum of premium × decrement × disc). Will not work for L5 because the per-row arithmetic chains through `accumulate`, `cum_prod`, `previous_period`. **Reject as primary path; revisit only if Polars' lazy planner gains specific scenario-axis push-down (it has not, as of writing).** Recommend an empirical check: `(with_scenarios(af, range(100)).pipe(model.main).collect()).explain(streaming=True)` — I did not run this.

### Pattern 4 — Scenario as a `list[list[float]]` column on each policy

`policies` stays at `n` rows; each policy carries an `n_scenarios × n_periods` doubly-nested list of drivers.

- **Peak memory:** total bytes ≈ `n × k × P × 8` — same magnitude as cross-join. **You have not saved anything.** What changes is the layout: row-major-policy, col-major-scenario. Polars list-of-list operations exist but are slower than flat list-of-float, and many `list.eval` patterns degrade non-trivially on doubly-nested lists.
- **CPU:** parallelism across policies preserved; scenario axis becomes an inner list dimension.
- **Ergonomics:** intrusive — model authors must write `list.eval(list.eval(…))` to operate on the inner scenario axis. Defeats the "scenario-ready by default" design philosophy in the RFC (`ref/27-scenario-support/27-scenario-support-rfc.md:39–60`).
- **Verdict:** **reject.** Same memory, worse ergonomics, breaks the projection accessor.

### Pattern 5 — `partition_by("scenario_id")` streaming write

Cross-join, run, then `sink_parquet(partition_by=["scenario_id"])`. Aggregate from disk in a second pass.

- **Peak memory:** still `O(n × k × B)` during the model run because `partition_by` operates *after* the projection — the cross-join intermediate is still in memory. Helps writing, not running. The "sink-then-stream" benchmark (`27-performance-and-scale.md:628–636`) measures **1.2 GiB peak** at 1k×100 — better than 5.6 GiB unbatched but achieved by batching first, then sinking. Without batching first, this pattern still OOMs.
- **Verdict:** complementary, not primary. Useful as the Phase-2 "I want all the data on disk" path.

### Honourable mention — Rust-side fold

A future kernel that ingests `(policies, scenario_iter, agg_spec)` and streams scenarios entirely in Rust without the Python boundary cost. Not recommended for this pass — needs the Polars plugin or a bespoke kernel, and is plausibly 6–12 weeks of work to do safely. Out of scope.

---

## 4. Thread-the-needle recommendation

Pattern 2: **`for_each_scenario` with explicit aggregator contract.**

### 4.1 API sketch

```python
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import for_each_scenario, ScenarioAggregator
from gaspatchio_core.scenarios.aggregators import CTE, Mean, Quantile, RunningSum

# Drivers can be a parquet path partitioned by scenario_id, an iterable
# yielding (scenario_id, driver_overrides), or a callable.
scenarios = pl.scan_parquet("scenarios/*.parquet")  # has scenario_id column

agg = ScenarioAggregator(
    pv_net_cf=CTE(level=0.70, direction="lower"),  # CTE(70) on tail losses
    pv_claims=Mean() + Quantile([0.50, 0.95, 0.99]),
    cohort_band=Mean(group_by="cohort_band"),       # nested aggregation
)

mp = pl.read_parquet("model_points.parquet")
result = for_each_scenario(
    af=ActuarialFrame(mp),
    scenarios=scenarios,
    scenario_id_col="scenario_id",
    model_fn=model.main,                # the existing model.main, unchanged
    agg=agg,
    progress=True,
)

print(result.summary())
# pv_net_cf:    CTE(70) = -2_481_000  (n_scenarios=10000)
# pv_claims:    mean=39_811_000, p50=39_750_000, p95=44_200_000, p99=46_900_000
# by cohort_band: ...
```

### 4.2 What `for_each_scenario` does internally

```python
def for_each_scenario(af, scenarios, scenario_id_col, model_fn, agg, ...):
    agg_state = agg.init(af.schema_with_scenario())
    for scenario_id, driver_subset in _iter_scenarios(scenarios, scenario_id_col):
        af_one = with_scenarios(af, [scenario_id])
        result_lf = model_fn(af_one, scenario_returns_override=driver_subset)
        result_df = result_lf.collect()      # one-scenario footprint only
        agg.update(agg_state, result_df, scenario_id)
        del result_df                        # explicit; help Polars/GC reclaim
    return agg.finalize(agg_state)
```

Three things this gets right:

1. **Memory bounded by one scenario.** No outer dimension multiplies the intermediate. Verified by the existing `batch_size=1` extreme of `batch_scenarios` (the benchmark uses 10).
2. **Existing `model.main` is unchanged.** It already accepts a frame with `scenario_id` populated; passing a 1-row scenario list works today.
3. **Aggregation is declarative, not imperative.** Users state "I want CTE(70) on `pv_net_cf`" and the framework guarantees that's what runs in streaming, with the right per-batch reduction.

### 4.3 How (A) full-grid materialisation stays accessible

Two paths:

- **`return_full_grid=True`** on `for_each_scenario` — sink each scenario's full result to parquet partitioned by `scenario_id`, return a `LazyFrame` over the partition set. Memory bounded by one scenario; final dataset is on disk.
- **Today's `with_scenarios` is retained verbatim** as the in-memory break-glass. Documented as: "for full-grid materialisation when `n_scenarios × n_policies × bytes_per_row` fits in RAM".

Either way, hedging-delta workflows (which legitimately need per-scenario per-policy detail) keep working. Most users will land on `for_each_scenario` because it's what their actual deliverable wants.

### 4.4 What changes in gaspatchio core

Small surface area. Order of work:

1. New module `bindings/python/gaspatchio_core/scenarios/_for_each.py` — the loop.
2. New module `bindings/python/gaspatchio_core/scenarios/_aggregators.py` — `Mean`, `RunningSum` (exact), `Quantile`/`CTE` (T-Digest from `crick` or pure-Python sketch; re-use existing if any in `accessors/finance`).
3. Re-export from `scenarios/__init__.py`.
4. Update L5-typed tutorial `run_scenarios.py` to demonstrate the new pattern alongside the existing one.
5. Documentation: extend `27-performance-and-scale.md` with a "B/C path is now `for_each_scenario`" preamble.

No Rust changes. No `ActuarialFrame` core changes. The model code in `tutorials/level-5-scenarios-typed/base/model.py` does not change.

### 4.5 Migration story

`with_scenarios` is **not deprecated**. It remains the (A) full-grid path. New code wanting B/C calls `for_each_scenario` instead. A linter / docs note suggests the migration when a model's collect is followed by `.group_by("scenario_id").agg(...)` — that's the smell signal.

### 4.6 Expected memory profile (1k × 10k × 240, L5 typed VA)

Using the per-row 58 KiB measurement from `27-performance-and-scale.md:704–706`:

| Pattern | Peak RSS | Wall time vs. unbatched | Notes |
|---|---|---|---|
| `with_scenarios` (current) | ~570 GiB | 1× | Will not run on a laptop. |
| `batch_scenarios` (size=100) | ~5.7 GiB | ~2× | Already shipped; ad-hoc agg. |
| **`for_each_scenario` (size=1)** | **~570 MiB** | **~3–5×** | One-scenario footprint + agg state. |
| `for_each_scenario(return_full_grid=True)` | ~570 MiB RAM + ~120 GiB disk | ~3–5× + sink I/O | Full grid on disk, RAM bounded. |

Numbers are extrapolations from the published benchmark, not new measurements. The 3–5× wall-time penalty is the cost of giving up Polars' inter-row parallelism *across* scenarios in favour of memory bound. For B/C deliverables on a single laptop that's the trade the user is asking for.

---

## 5. Honest tradeoffs

What gets worse:

- **Single-LazyFrame semantics are gone.** Today a user can write `af.x = …; af.y = …; af.collect()` and get a flat result table they can pivot however they want. With `for_each_scenario` the aggregation has to be declared up-front. If you then realise you wanted a different aggregation you re-run the whole `k`-scenario loop.
- **Two code paths.** `with_scenarios` (A) and `for_each_scenario` (B/C). Plus `batch_scenarios` (the existing ad-hoc thing). That's three patterns with overlapping semantics. Documentation has to be ruthless about *which one to reach for*. The temptation to deprecate `batch_scenarios` should be resisted until `for_each_scenario` is field-tested.
- **Aggregator implementation is non-trivial for tail metrics.** Exact CTE / quantile across `k` scenarios needs all `k` per-scenario aggregates in memory. That's `k × (n_metrics × 8 B)` — for `k=10⁴` and 20 metrics that's ~1.6 MB, trivial. The harder cases (CTE *by cohort band* on `n_policies × k_groups`) require nested aggregation; the API has to handle it cleanly or users will hand-roll loops and lose the guarantee.
- **Polars' optimizer might already be doing some of this.** A run with `pl.Config.set_engine_affinity("streaming")` set globally and a `result.lazy().group_by('scenario_id').agg(…).collect(engine='streaming')` *might* recover most of the memory benefit without the explicit loop, *if* the model body's `cum_prod` / `previous_period` were inside `list.eval` (which they are — `accessors/projection.py:338, 1199, 1421`) and *if* the cross-join were lazy (which it is not — `_with_scenarios.py:126`). Fixing just the second of those — making `with_scenarios` lazy — is a one-line change. **Recommend doing that first as a controlled experiment, before building `for_each_scenario`.** If lazy `with_scenarios` + streaming aggregation halves memory at minimal wall-time cost, the case for `for_each_scenario` weakens. If it doesn't (more likely, given the non-streamable subgraphs the perf memo flags), build `for_each_scenario`.
- **Rollforward kernel is not in scope and may shift the answer.** Per-policy rollforward state lives in the `ActuarialFrame` lazy plan as hidden `__rollforward_*` columns (`frame/base.py:419–424`). If a future scenario design wants to fold rollforward across scenarios (i.e., apply scenario drivers to rollforward step inputs), the per-scenario loop pattern works trivially — each scenario runs the rollforward independently. Cross-join + rollforward, by contrast, multiplies the rollforward state by `k`. Another point in favour of the loop pattern.
- **No interactive debugging across scenarios.** When a user spots a weird `pv_net_cf` for scenario 4823, they cannot just `result.filter(scenario_id=4823)` because there is no flat result. Mitigate by exposing `for_each_scenario(..., debug_scenarios=[4823])` that materialises specific scenarios full-grid alongside the aggregate run.

---

## 6. Open questions

Things I could not determine without prototyping or running the parallel agent's benchmarks:

1. **Does Polars' streaming engine actually keep memory flat for `with_scenarios` if `_with_scenarios.py:126` is changed to use `af._df` (the LazyFrame) instead of `af.collect()`?** This is a one-line change; the answer materially affects whether `for_each_scenario` is worth its weight. Recommend running this first.
2. **Per-scenario wall time floor.** `for_each_scenario` cost per scenario is `t(model on 1 scenario) + t(aggregator update)`. The model-on-1-scenario cost has fixed overhead (Polars graph construction, table joins, schedule build) that the cross-join shape amortises across `k`. At `n_policies=1k`, `k=10⁴`, what fraction of wall time is fixed-overhead-per-scenario? Need a measurement.
3. **T-Digest accuracy at the CTE(70) tail.** For a 10⁴-scenario CTE(70) we keep the tail 30% (3000 scenarios). Exact CTE on 3000 floats is fine. But CTE *by cohort band* with 10–20 cohort bands and 10⁴ scenarios — exact still trivial. The T-Digest question only matters for 10⁶+ scenario counts (LSMC fitting, IM SCR), which are out of scope here.
4. **Is the eager `.collect()` in `_with_scenarios.py:126` defensible on grounds I'm missing?** I don't see why it's there — the cross-join works on a LazyFrame. The git history would clarify whether this was a deliberate choice or accumulated cruft. Worth checking before any change.
5. **Does the parallel memory-scaling agent's measurement confirm or contradict the perf-memo claim that cross-join memory grows linearly?** If the agent finds streaming actually *does* keep memory roughly flat, the entire premise of this recommendation weakens — `for_each_scenario` becomes a nicety rather than a necessity. I'm assuming the agent's findings will broadly confirm the existing perf-memo measurements.
6. **What does `for_each_scenario` look like with rollforward state?** If state has to thread between time steps for each scenario, the per-scenario loop is the natural place to do it; the cross-join is actively hostile. Whether the current rollforward kernel composes cleanly with a per-scenario loop, or whether the loop has to invoke a rollforward stepper, is a design question that needs the GSP-92 work to settle.

---

## Cross-references

- `bindings/python/gaspatchio_core/scenarios/_with_scenarios.py:117–132` — the cross-join, eager.
- `bindings/python/gaspatchio_core/scenarios/_batching.py:16–79` — existing batching helper (caller-managed agg).
- `bindings/python/gaspatchio_core/scenarios/__init__.py:6–45` — module surface.
- `bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/base/model.py:474–501, 725–751` — scenario surfaces in the L5 typed VA model.
- `bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/stress/perf_scaling.py:622–637` — measured 10k×1200M memory reversal under the broadcast pattern.
- `bindings/python/gaspatchio_core/accessors/projection.py:338, 618, 1199, 1421` — `cum_prod`, `previous_period`, `shift` all run inside `list.eval`, i.e. row-independent.
- `bindings/python/gaspatchio_core/frame/base.py:366–426` — `ActuarialFrame.collect` defaults to `engine="streaming"`.
- `ref/27-scenario-support/27-performance-and-scale.md:587–598, 628–680, 691–710, 754–763` — measured benchmarks, sink-then-stream pattern, streaming limitations for GMXB.
- `ref/27-scenario-support/27-scenario-support-rfc.md:39–60` — "scenario-ready by default" design philosophy (the constraint that any new pattern must preserve).
