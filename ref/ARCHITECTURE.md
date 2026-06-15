# Gaspatchio Architecture

Gaspatchio is a high-performance actuarial modeling framework that pairs Python's ergonomics with
a Rust + Polars engine. This document covers the major components and the decisions behind them.

> To *use* the framework, see the [documentation](https://gaspatchio.dev/) and the
> [Python package README](../bindings/python/README.md). For contributor rules, see the
> per-directory `AGENTS.md` files.

## 1. Hybrid architecture: Python interface, Rust engine

- **Python layer** (`gaspatchio_core` package) — the user-facing API: `ActuarialFrame`, `Table`,
  the domain accessors, the scenario layer, and the `gspio` CLI. Owns ergonomics, typing, and
  Python-ecosystem integration.
- **Rust layer** (`gaspatchio_core_lib` crate, via PyO3) — the performance-critical components:
  the assumption-table registry, vectorized lookups, and custom Polars expression plugins.
- **Polars backbone** — all data operations run on [Polars](https://pola.rs/). `ActuarialFrame`
  wraps Polars structures to add actuarial intelligence without giving up Polars' multi-threaded,
  columnar performance.

## 2. ActuarialFrame: the core abstraction

`ActuarialFrame` wraps a Polars `LazyFrame`. Its columns are either:

- **scalar** — one value per policy (e.g. `sum_assured`), or
- **list** — one value per projection period (e.g. a monthly mortality vector).

Arithmetic between scalar and list columns **broadcasts automatically** ("vector shimming"), and
the formula is the code:

```python
af.pols_death = af.pols_if * af.mort_rate_mth                 # list * list, element-wise
af.net_cf = af.premiums - af.claims - af.expenses             # multiple list columns
af.pols_maturity = when(af.month == af.term * 12).then(af.surviving).otherwise(0.0)
```

Evaluation is **lazy**: assignments build a Polars query plan, and `af.collect()` executes it.
`collect()` defaults to Polars' **streaming engine**, which processes data in chunks for bounded
memory (§7). The `gspio` CLI's `--mode {debug,optimize}` selects verbosity/optimization for
command-line runs.

## 3. Domain accessors

Operations beyond plain arithmetic are organized into discoverable namespaces on columns and
frames (registered via a base-class + `@register_accessor` pattern, extensible by users):

- **`.projection`** — time-shifting and cumulative operations across periods:
  `cumulative_survival()`, `previous_period()`, `next_period()`, `at_period(t)`.
- **`.finance`** — rate conversions and financial maths (e.g. `to_monthly()`, discounting).
- **`.excel`** — Excel-compatible function semantics (e.g. `yearfrac`).
- **`.date`** — date arithmetic and projection-timeline construction.

## 4. Projection axis

Actuarial models roll a portfolio forward through time. The projection axis provides:

- **Per-policy timelines** — each policy gets its own start/end, so timelines are **jagged** (the
  default): no computation wasted padding short policies onto a common grid. A Rust kernel +
  period masks keep jagged and uniform timelines correct under one API.
- **A rollforward state-machine kernel** — period-to-period state transitions (in-force →
  death / lapse / maturity) compiled to Polars operations, unifying the projection-axis API.
- **The `.projection` accessor** (§3) for the period-relative reads actuaries use (`t-1`,
  cumulative survival, …), keeping rollforward formulas transparent and auditable.

## 5. Assumption tables

A specialized system for high-performance actuarial lookups, replacing manual joins.

- **`Table`** — a loaded assumption table (mortality, lapse, …); handles dimension processing and
  registration with the Rust registry. `TableBuilder` covers complex/programmatic construction.
- **Dimensions** — tables are keyed by dimensions (`age`, `duration`, `calendar_year`, …) that map
  your names to source columns. Dimension types (`DataDimension`, `MeltDimension` for wide-to-long,
  `CategoricalDimension`, `ComputedDimension`) and overflow strategies (`ExtendOverflow`,
  `FillForward`, `FillConstant`, `LinearInterpolate`) shape how data is read.
- **Storage** — the global, thread-safe Rust registry (`ArcSwap`, near lock-free reads)
  auto-selects the backend: **array storage** for dense integer-keyed tables (nanosecond lookups,
  20–40× faster than hash), **hash storage** for sparse / string-keyed tables.
- **Lookups** — `Table.lookup(...)` compiles to a Rust plugin call and resolves rates for an entire
  projection array in one vectorized operation.
- **Scenarios & shocks** — tables can be built from scenario files (`Table.from_scenario_files`) or
  by applying shocks (`Table.from_shocks` — multiplicative / additive / override) for sensitivity
  analysis, and carry governance metadata.

## 6. Scenarios & aggregation

A layer for stochastic / multi-scenario runs with bounded memory and reproducibility.

- **`ScenarioRun`** — a typed, reproducible run plan: shocks, base tables, and a tuple of
  aggregators. Exposes `canonical_form()` / `source_sha()` for input identity plus an opt-in JSON
  audit sidecar; `run()` delegates to `for_each_scenario`.
- **`for_each_scenario`** — the bounded-memory loop primitive: project each scenario, fold it into
  aggregator accumulators, never hold all scenarios at once. `batch_size="auto"` runs a measured
  streaming-batch search; `on_batch` streams a `BatchSnapshot` (running partials + progress/ETA)
  for live convergence-watching.
- **`run_aggregated`** — the policy-axis equivalent: batch a large book, fold each batch to
  per-period vectors, never co-resident. `run_to_parquet` spills the full per-policy grid to disk
  when a run can't fold.
- **Mergeable aggregators** — a Beam-style protocol (`create_accumulator` / `add_input` /
  `merge_accumulators` / `extract_output`): scalar aggregators (`Sum`, `Mean`, `CTE`, `Quantile`,
  … via DDSketch / Welford–Chan merges) and per-period `Period*` aggregators. `.over(by)`
  partitions any aggregator for portfolio splits without re-running the model.
- **Memory sizing** — batch sizes are chosen against a **cgroup-aware** memory budget (fails open
  to host RAM, fails loud rather than silently clamping to one).

## 7. Performance & memory

1. **Vectorization** — every operation is vectorized; there are no Python loops over policies.
2. **Lazy + streaming** — `ActuarialFrame` builds a Polars query plan optimized via
   projection / predicate pushdown; `collect()` runs it on the streaming engine. Custom plugins are
   marked `is_elementwise` so the streaming engine processes them in chunks instead of falling back
   to in-memory execution.
3. **Rust plugins** — operations hard to express efficiently in standard expressions (list
   conditionals, actuarial lookups) are custom Polars plugins, dispatched via the `polars_backend/`
   router.
4. **Zero-copy** — data crosses the Python/Rust boundary in Arrow format with minimal copying.
5. **Memory at scale** — peak memory is dominated by intermediate columns in the lazy plan.
   Model-point batching, `run_aggregated`'s policy-axis fold, and parquet spill cap peak RSS
   regardless of total scale.

## 8. Directory structure

- **`bindings/python/`** — the Python package (`gaspatchio_core`), PyO3 bindings, the `gspio` CLI,
  and the `polars_backend/` plugin router. The user-facing product.
- **`core/`** — the Rust engine: assumption registry, vector/Excel plugins, projection/rollforward
  kernels.
- **`tutorial/`** — incremental tutorial models (hello-world → reconciled lifelib → scenarios).
- **`evals/`** — benchmarks and model evals, published to the
  [dashboards](https://opioinc.github.io/gaspatchio-core/).
- **`ref/`** — design specs, architecture notes, and RFCs (numbered by topic).
