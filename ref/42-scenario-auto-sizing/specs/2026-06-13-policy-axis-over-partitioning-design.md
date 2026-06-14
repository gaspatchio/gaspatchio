# `.over()` partitioning on `run_aggregated` — design

**Status:** design (awaiting review) — 2026-06-13
**Topic:** `ref/42-scenario-auto-sizing`
**Follows:** PR #111 code review (the deferred feature from findings #5/#6/#8/#11). See the
fix commits `1ba4088`..`3817eaa`, which rejected `.over()` on the policy axis with a clear
error and noted full per-axis support as deferred.

---

## 1. Problem

`run_aggregated` folds over **policy** batches to per-period aggregates, but every aggregator
applies to the whole portfolio. Actuaries routinely want the same projection **split by a
low-cardinality dimension** — product, cohort, distribution channel, reinsurance treaty — to
report per-segment cashflows side by side without re-running the model per segment.

The scenario axis already expresses this as `agg.over("product")` (a `_Partitioned` wrapper);
the policy axis rejects it. The headline use case is:

```python
res = run_aggregated(
    model_fn, model_points,
    aggregations=[PeriodSum("net_cf").alias("net_cf").over("product")],
)
# res.net_cf -> a tidy DataFrame: one row per (product, period)
```

## 2. Scope

**In scope** — `.over(by)` on `run_aggregated` for:
- **scalar** aggregators whose fold is value-driven and axis-agnostic (`Sum`, `Min`, `Max`, and
  any `_BaseAggregator` of the same shape — the plan confirms the exact set, e.g. whether a
  scalar `Mean` folds correctly across batches) → one value per partition.
- **vector (`Period*`) aggregators** with a single-array per-period output: `PeriodSum`,
  `PeriodCount`, `PeriodMin`, `PeriodMax`, `PeriodMean`, `PeriodVariance`, `PeriodStd`,
  `PeriodMedian`, `PeriodCTE` → a per-period vector per partition.
- multi-column `by` (e.g. `.over(("product", "cohort"))`).

**Out of scope (unchanged / deferred):**
- `Count`, `ArgMin`, `ArgMax` on the policy axis — still rejected (they count / identify
  *scenarios*; on the policy axis a "group" is a batch or a partition, not a meaningful count
  or arg). The rejection from the review fixes stays, with or without `.over()`.
- A **cardinality guard** — deliberately deferred (per review). `.over()` is documented as a
  low-cardinality reporting dimension; high-cardinality misuse (`.over("policy_id")`) is the
  user's responsibility for now.
- `.over()` on **`for_each_scenario`'s vector path** (the other half of review #6). The shared
  helpers below make this a small follow-on, but it is not built here.

## 3. Output contract

Partitioned outputs are **tidy/long `pl.DataFrame`s**, keyed in `AggregatedResult.aggregations`
by the aggregator's alias (same as today):

| aggregator | output |
|---|---|
| scalar `Sum("pv").alias("pv").over("product")` | `{product, pv}` — one row per partition |
| vector `PeriodSum("cf").alias("cf").over("product")` | `{product, period, cf}` — one row per partition × period |
| multi-col `Sum(...).over(("product","cohort"))` | `{product, cohort, pv}` |

Rationale for tidy over vector-in-cell (the scenario-axis `_Partitioned` shape):
- The vector-`.over()` shape does not exist on **either** axis yet, so there is no existing
  contract to stay consistent with — we are defining it fresh.
- Tidy is the shape actuaries consume: filter to a product, group periods into years, join
  product metadata, diff two products, plot. Vector-in-cell would be `.explode()`d into exactly
  this ~90% of the time.
- Tidy is the most auditable form (a readable `(product, period, value)` table).
- It is **perf-neutral** — see §6.

Unpartitioned outputs are unchanged: scalar → a Python scalar, `Period*` → a numpy vector,
`PeriodQuantile` → `{level: vector}`.

## 4. Architecture

**Decision: share the partition machinery; keep the two `_fold_batch` entry points separate.**

The review's altitude finding suggested unifying `_for_each._fold_batch` and
`_aggregated._fold_batch`. On inspection they genuinely differ in the **scalar** path — the
scenario axis groups by `scenario_id` (one contribution per scenario; this is *why* `Count`
counts scenarios), while the policy axis treats the whole batch as one contribution
(`.item()`). Merging those risks regressions in the well-tested scenario path for little gain.

Instead, extract the part that is actually identical — **the partition logic** — into shared
helpers both drivers can call, and let each driver keep its own thin fold entry point. This
captures the real reuse safely and leaves `for_each_scenario`'s vector `.over()` as a small
later extension from the same helpers.

The accumulator/merge/extract layer is **already shared and correct**: `_Partitioned`
(`scenarios/_metric.py`) holds `dict[partition_tuple, inner_accumulator]`, routes
`add_input((partition_key, inner_value))` to the right slot, deep-copies on merge (sketch
safety), and `extract_output` emits a `pl.DataFrame`. We reuse it unchanged for accumulation;
only the **per-batch reduce** and the **extract reshape** are new.

## 5. Components

### 5.1 Partitioned per-period reduce (single pass)

Extend the existing `_reduce_by_period(frame, period, column, *aggs)` (which the review fixes
added) with a partition-aware sibling:

```
_reduce_by_period_over(frame, period, column, by, *aggs) -> pl.DataFrame
    explode([period, column]) -> drop null periods -> group_by([*by, period]) -> agg(*aggs)
    -> sort([*by, period]) -> collect
```

This is **one `group_by` pass per batch** (the partition columns are scalar-per-policy, so they
ride the existing explode — no new explode, no per-partition loop). The reduced frame is small
(`n_partitions × n_periods` rows). Chosen over a per-partition-slice loop (which would reuse
`batch_reduce` verbatim but do `n_partitions` collects per batch) specifically to keep the
streaming fold to one reduce-collect per batch.

### 5.2 `VectorAggregator.batch_reduce_over(frame, period, by) -> dict[tuple, partial]`

The partitioned analogue of `batch_reduce`, returning `{partition_tuple: partial}` where
`partial` is the **same partial type** the non-partitioned `batch_reduce` returns
(`PeriodSum` → vector; `PeriodMean` → `(sum_vec, count_vec)`; `_PeriodMoment` → `(n, mean, m2)`;
sketch family → `list[SignedSketch]`). Implementation reads the `_reduce_by_period_over` frame
and assembles per-partition partials by grouping its rows on `by` and ordering by `period`
(the per-aggregator column→numpy assembly mirrors each existing `batch_reduce`). Period indices
within a partition are dense `0..max` (they come from `int_ranges(list.len())`), so ragged
lengths across partitions/batches are absorbed by the existing `_pad_add`/Welford merges.

The sketch family (`_period_sketch.build_period_sketches`) gets the analogous `by`-grouped
build (`group_by([*by, __sign, __bin])` keyed by partition), reusing `from_binned`.

### 5.3 `run_aggregated._fold_batch` dispatch

Relax the blanket `_Partitioned` rejection. Per aggregator:

| aggregator | path |
|---|---|
| scalar, no `.over()` | `proj.select(within_expr).item()` → `add_input(value)` *(today)* |
| vector, no `.over()` | `batch_reduce` → `add_input(vector)` *(today)* |
| scalar `.over(by)` | `proj.group_by(by).agg(within_expr)` → per row `_Partitioned.add_input((partition, value))` *(new)* |
| vector `.over(by)` | `batch_reduce_over(by)` → per partition `_Partitioned.add_input((partition, partial))` *(new)* |

`_reject_scenario_axis_only` keeps rejecting `Count`/`requires_scenario_id` aggregators
(with or without `.over()`). `_alias_of` is taught to read `_Partitioned.alias` (the review's
#5 was the missing branch).

### 5.4 Tidy extract

`_Partitioned.extract_output` already returns `{by…, alias}`. For a **vector** inner aggregator
the alias cell holds a per-period vector; the partitioned-vector extract explodes that into
`{by…, period, alias}` (a one-time step on the small final accumulator — §6). Scalar partitions
need no reshape. This lives next to the extract, not in the per-batch fold.

## 6. Performance

`run_aggregated` is a **bounded-memory streaming fold**, not a single terminal collect: each
batch's projection is collected once (streaming), reduced to small per-period vectors, and
accumulated in Python before the batch is freed. Partitioning stays entirely inside that model:

- **Reduce:** the partition columns join the `group_by` key (`[*by, period]`); the reduced
  output is `n_partitions × n_periods` rows. The expensive projection collect is unchanged. One
  reduce-collect per batch (the single-pass design, §5.1).
- **Accumulate:** `{partition: vector}` instead of one vector → `n_partitions ×` the small numpy
  merges per batch. Negligible at low cardinality.
- **Extract / tidy reshape:** one-time, on the final `n_partitions × n_periods` accumulator
  (a few thousand rows). The tidy explode happens here — **not** on any per-batch projection —
  so the output shape costs nothing measurable.
- **Sizer:** unaffected. Partitioning does not change the projection size, so `per_cell` and
  batch sizing are identical.

The one real cost is **cardinality** (accumulator dict + group count grow with `n_partitions`),
which is why `.over()` is a low-cardinality dimension. A guard is deferred (§2).

## 7. Error handling

- `Count`/`ArgMin`/`ArgMax`, with or without `.over()` → existing clear rejection (unchanged).
- Empty `[]` lists / all-null periods within a partition → already handled by the
  `drop_nulls(period)` in `_reduce_by_period`/`_reduce_by_period_over` and the all-null
  `n_periods` guard (`_max_period_len`) from the review fixes.
- A partition column missing from the projection → Polars raises a clear `ColumnNotFound` at the
  `group_by`; surface it as a `ValueError` naming the missing `by` column.
- Mixed aggregators (some `.over()`, some not) in one call → fine; each alias's output is
  independent.

## 8. Testing

TDD against the scenario test suite conventions. Anchor:

- **Reconciliation (lossless split):** `sum over partitions == unpartitioned total`.
  `PeriodSum("cf").over("product")` summed across products equals `PeriodSum("cf")`
  element-wise; likewise scalar `Sum(...).over(...)` summed across partitions equals `Sum(...)`.
- Scalar `.over()` shape `{product, value}`; vector `.over()` shape `{product, period, value}`.
- Multi-column `.over(("product","cohort"))`.
- Jagged/ragged partitions (different horizons per product) reconcile and pad correctly.
- `batched == single-batch` equivalence for a partitioned run (partition split is
  batch-size-invariant).
- `PeriodQuantile.over()` / `PeriodMedian.over()` produce per-partition quantiles consistent
  with per-partition sketches.
- `Count.over()` / `ArgMax.over()` still raise the clear rejection.

## 9. Rejected alternatives

- **Full fold unification** — merge `_for_each._fold_batch` and `_aggregated._fold_batch`.
  Rejected: the scalar paths differ (scenario_id grouping vs whole-batch), so merging risks
  scenario-axis regressions; the genuine reuse is the partition logic, which we share instead.
- **Per-partition-slice reduce** — loop distinct partitions, `frame.filter(...)`, reuse
  `batch_reduce`. Rejected: zero new aggregator code but `n_partitions` collects per batch,
  against the minimise-collects goal; the single-pass `group_by([*by, period])` keeps one
  reduce-collect per batch.
- **Vector-in-cell output** (reuse `_Partitioned.extract_output` as-is). Rejected: arrays in
  cells are awkward to slice/join/plot and less auditable; tidy is perf-neutral so there is no
  reason to prefer it.

## 10. Out of scope / future

- **`PeriodQuantile.over()`** — *deferred during implementation (2026-06-13).* Its output is
  multi-level (`{level: vector}`), which has no clean single-column tidy form and does not
  round-trip through the `_Partitioned` DataFrame extract. `run_aggregated` raises a clear
  `NotImplementedError` (via `_reject_multi_level_over`) pointing users to `PeriodMedian`/
  `PeriodCTE.over()` (single-level) or `PeriodQuantile` without `.over()`. A `{*by, period,
  level, value}` tidy form is a natural follow-on if multi-level partitioned quantiles are
  wanted.
- `.over()` on `for_each_scenario`'s vector path (the other half of review #6) — small follow-on
  using the same `batch_reduce_over` / `_reduce_by_period_over` helpers.
- A cardinality guard (warn/raise above N partitions).
- A single-pass perf optimisation for the per-partition-slice path (moot — we chose single-pass).
