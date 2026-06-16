# Changelog

## [0.4.2] — First published release (docs + packaging)

Same engine as the v0.4.0 and v0.4.1 tags — neither shipped a populated release (0.4.0's
wheel build was blocked by a CI billing limit; 0.4.1's tag was burned when the release job
created an empty release under the org's immutable-releases policy). 0.4.2 is the first
published GitHub Release carrying wheels: identical computation, plus the documentation and
CI tidy-up landed since the 0.4.0 tag. No API or behaviour changes. (Distributed via GitHub
Release assets; PyPI publishing is not yet wired up.)

### Documentation
- Single canonical root `README.md` (the duplicate `readme.md` case-collision that left GitHub rendering a stale landing page is removed).
- Pydantic-style rewrites of the root, Python, and Rust READMEs — badges, docs-forward, cross-linked to [gaspatchio.dev](https://gaspatchio.dev/) and the [benchmark dashboards](https://opioinc.github.io/gaspatchio-core/).
- `ref/ARCHITECTURE.md` brought current: projection axis (jagged timelines + rollforward kernel), the scenarios/aggregation layer, and the streaming engine.

### Infrastructure
- Cut Actions spend: benchmark/eval jobs run on push to `main` (plus schedule / `benchmark` label / dispatch) instead of every push to `develop`; dropped the `windows-m` leg from the per-PR benchmark; grouped Dependabot updates into one PR per ecosystem; per-ref CI concurrency cancellation.
- Release job now creates a draft, attaches the wheels, then publishes — compatible with the org's immutable-releases policy, which locks a published release's assets at publish time.

---

## [0.4.0] — Unified aggregation surface + jagged timelines

Everything merged to `develop` since v0.3.1 (#99–#114). The headline is a single aggregation
vocabulary across two axes — **the aggregator is the primitive, the driver is the axis** — plus
jagged per-policy timelines becoming the default projection shape and live streaming/progress
on the scenario drivers.

### Added
- **`run_aggregated`** policy-axis driver: batch policies, fold each to per-period vectors, never co-resident. (#111)
- **`Period*` aggregator family** — `PeriodSum`/`Count`/`Mean`/`Min`/`Max`/`Variance`/`Std` (additive; `Mean` is exact Sum/Count, `Var`/`Std` are vector Welford–Chan), robust to jagged timelines. (#111)
- **`.over(by)` portfolio partitioning** on both drivers (`run_aggregated` and `for_each_scenario`) — product / cohort / channel splits without re-running the model; tidy long output, lossless (sum over partitions == the unpartitioned total). (#111)
- **`run_to_parquet`** policy-axis spill for the full-output path that can't fold: batch + stream each batch to parquet, refusing RAM-backed targets, preflighting disk, renaming atomically. (#111)
- **Rank-based per-period aggregates** — `PeriodQuantile`/`Median`/`CTE` via a vectorized DDSketch histogram (no per-value loop). (#111)
- **Shape-aware `for_each_scenario` auto driver** — `batch_size="auto"` runs a measured streaming-batch search over a geometric ladder and records the full `SelectionDecision`/`ProbeResult` ladder for audit. (#106, #111)
- **Cgroup-aware batch sizing** — sizes against the cgroup's own-usage headroom (v1/v2), subtracts base RSS, **fails open** to host RAM, **fails loud** (`IrreducibleCellError`) instead of silently clamping. (#111)
- **`ScenarioRun` + mergeable aggregator layer (v0.2 surface)** — Beam-style aggregator Protocol with `.alias()` / `.over()` / `.of()`, DDSketch CTE/Quantile/Median, Welford+Chan Mean/Variance/Std, opt-in audit-sidecar JSON. (#105)
- **Chained `.when()` on list columns** (GSP-87). (#99)
- **Streaming + progress on `ScenarioRun`** — `ScenarioRun.run(progress=…, on_batch=…)` forwards to the same loop as `for_each_scenario` (live observation only — `source_sha()` / audit unchanged); `BatchSnapshot` becomes a progress type (`elapsed_s` + `fraction_done` / `eta_s` / `throughput`) and `progress=True` logs `"47% · ETA 3m12s"`; `ScenarioResult` gains `n_batches`. (#114)

### Changed (behaviour)
- **Jagged per-policy timelines are now the default** projection shape (per-policy start/end via kernel + masks + reconciliation), replacing the uniform-grid default. (#108, #106)
- **Projection-axis API unification** on top of a rollforward state-machine kernel. (#104)
- Polars plugin dispatch extracted into a `polars_backend/` subpackage; `Shape` is now the single source of truth (`ColumnTypeDetector` removed). (GSP-95: #100, #101, #102)

### Performance
- **O(1) plan-build per assignment** via lazy + incremental schema resolution. (#109)

### Infrastructure
- **Apache-2.0 licensing** — root LICENSE + NOTICE, SPDX headers (REUSE 3.3), and an outbound-compatibility licence-check workflow.
- **Windows benchmark lanes** on core-matched runners. (#112)
- Dependency/security: cleared Rust OSV advisories via lockfile bumps. (#110)
- lifelib reference data extracted into a `gaspatchio-benchmarks` sister repo; agent instructions consolidated into `AGENTS.md` + `CLAUDE.md` shims. (#107)

### Known limits
- `PeriodQuantile.over()` is deferred (its multi-level output has no tidy single-column form); `Count` / `ArgMin` / `ArgMax` remain scenario-axis-only and are rejected under `.over()`.
- DDSketch CTE / Quantile precision ≈ 10 bp at the 99.5th percentile — within actuarial SCR / CTE-70 tolerance; tighten via a lower `relative_accuracy`.

---

## [0.2.0] — GSP-101 Mergeable Aggregator Layer

### Added
- Beam-style `Aggregator` Protocol (5-tuple: `within_expr`, `create_accumulator`, `add_input`, `merge_accumulators`, `extract_output`) plus `canonical_form()`
- `.alias(name)`, `.over(by)`, `.of(expr)` modifiers on every aggregator
- Multi-column partitioning via `.over(tuple)`; output shape: scalar metric → scalar, partitioned metric → `pl.DataFrame` keyed by partition columns
- DDSketch-backed mergeable `Quantile` / `Median` / `CTE` / `QuantileRank` (paired signed-value sub-sketches; `relative_accuracy` tunable, defaults to `1e-4`)
- Welford + Chan parallel-merge `Mean` / `Variance` / `Std`
- Hypothesis property test pinning merge associativity + commutativity for every built-in aggregator
- Opt-in audit sidecar JSON via `ScenarioRun.run(audit=True | Path)`; default location `./gaspatchio_audit/<run_id>.audit.json`
- Cross-process governance test: plan + custom aggregator survives YAML round-trip across fresh interpreters with bit-exact aggregations + identical `source_sha()`
- `parse_aggregations(spec)` recursive parser for the new list-of-dict YAML shape, including `_Partitioned` round-trip

### Removed (breaking)
- `MultiAgg` — pass aggregators directly: `ScenarioRun(aggregations=(Sum("loss").alias("total"), ...))`
- `GroupedAgg` — use `.over(by)`: `ArgMax("loss").over("lob").alias("worst")`
- `metric(col, agg)` — the column travels with the aggregator: `Sum("loss")` instead of `metric("loss", Sum())`
- `ScenarioMetric` — folded into the aggregator base class
- `for_each_scenario(agg=..., per_scenario=...)` kwargs — replaced by `aggregations: Sequence[Aggregator | _Partitioned]` where each aggregator carries its own `within_expr`
- `ScenarioRun.aggregations: dict[str, ScenarioMetric]` — now `tuple[Aggregator | _Partitioned, ...]` with `.alias()` providing the output key

### Migration table

| v0.1 | v0.2 |
|---|---|
| `MultiAgg({"total": Sum()})` | `(Sum("loss").alias("total"),)` |
| `GroupedAgg(by="lob", metric=ArgMax())` | `ArgMax("loss").alias("worst").over("lob")` |
| `metric("loss", CTE(0.005))` | `CTE("loss", level=0.005).alias("scr")` |
| `ScenarioMetric(per_scenario=expr, across_scenario=Sum())` | `Sum.of(expr).alias("name")` |
| `for_each_scenario(..., agg=Sum(), per_scenario=pl.col("loss").sum())` | `for_each_scenario(..., aggregations=(Sum("loss").alias("total"),))` |
| `ScenarioRun(aggregations={"total": metric("loss", Sum())})` | `ScenarioRun(aggregations=(Sum("loss").alias("total"),))` |
| `result.aggregations` (scalar) | `result.aggregations["total"]` (dict keyed by alias) |

Loading a v0.1-shaped YAML plan raises `ValueError("v0.1 plan format detected ...")` pointing at this table.

### Known limits
- DDSketch-backed aggregators allocate ~1.2 MB per sub-sketch at `relative_accuracy=1e-4`; tune via constructor kwarg (≈125 KB at `1e-3`)
- DDSketch CTE / Quantile precision ≈ 10 bp at the 99.5th percentile — within actuarial SCR / CTE-70 tolerance; tighten via lower `relative_accuracy`
- Polars 1.38.x pin required for `Expr.meta.serialize()` bit-exactness on the `.of(pl.Expr)` escape hatch
- `master_seed` + `batch_size > 1` raises `ValueError` (unchanged from GSP-100)
- Drivers-dict scenario shape forwards drivers only at `batch_size=1`; raises at `batch_size > 1` rather than silently dropping them

---

## [Unreleased] — GSP-100 ScenarioRun

### Added
- `ScenarioRun` typed plan with `canonical_form()` / `source_sha()` / `describe()`
- `for_each_scenario` bounded-memory loop primitive
- `ScenarioMetric(per_scenario, across_scenario)` reduction recipe with `metric()` sugar
- 15 starter aggregators: Sum, Count, Mean, Std, Variance, Min, Max, ArgMin, ArgMax, CTE, Quantile, Median, QuantileRank, GroupedAgg, MultiAgg
- `@scenario_aggregator()` decorator for user-defined plugins
- `Table.canonical_form()` and `Table.source_sha()`
- `master_seed` plumbing via `drivers["rng_seed"]` (sha256-derived)
- Memory benchmark verifying batch-bounded peak RSS

### Removed (breaking)
- `batch_scenarios` (use `for_each_scenario(batch_size=N)`)
- `describe_scenarios` (use `ScenarioRun.describe()`)
- `sensitivity_analysis` (now internal; use `ScenarioRun` configs)

### Internal
- `canonical_bytes` lifted from `schedule/_canonical.py` to `_identity.py`

### Known limits (v0.1)
- `master_seed` and the drivers-dict scenario shape currently inject per-scenario state only at `batch_size=1`. A `UserWarning` surfaces this when `batch_size > 1`. Spec §5.5 follow-up edit pending.
