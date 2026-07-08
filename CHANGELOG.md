# Changelog

## [0.5.3] — Scenario auto-batching can no longer OOM the box

The `batch_size="auto"` scenario search measures candidate batch sizes by
running them; three field-observed ways that measurement itself could exceed
physical memory and get the process kernel-killed are now closed. (#8, #10,
#11)

### Fixed
- `for_each_scenario(batch_size="auto")` no longer risks a kernel OOM-kill
  while *measuring* candidate batch sizes. The streaming-batch search now
  predicts each ladder rung from the last measured one and never launches a
  probe whose predicted peak already exceeds the memory budget. Previously
  the search ran every rung unconditionally and checked the budget only after
  the fact — a probe larger than physical memory died mid-`collect()`, before
  any back-off logic could run (observed as a CI runner death on a
  10-scenario × 100K-policy cell, where the b=4 streaming probe demanded
  ~11.5 GB on a 16 GB box). The prediction is linear-in-batch times
  `streaming_batch_inflation` (3.0): under the streaming engine the scenario
  cross-join peak is *super-linear* in batch at high policy counts
  (Polars #20786; the same cell measured b=4 at ~8.6× the b=1 rung, 2.2×
  above linear), so a bare linear gate still under-predicted the killer rung.
  Over-predicting costs at most a smaller batch; under-predicting costs the
  process. Probe peaks are additionally floored by the materialised frame's
  size: in a process with retained allocator pools a batch can be served
  entirely from pooled memory — RSS never grows, the sampler reads ~0, and
  any prediction multiplied from that zero is blind. The frame's bytes are
  live memory regardless of where the allocator got them (the same floor the
  policy axis has always applied to its seed measurement).

## [0.5.2] — Post-release correctness fixes

Correctness and robustness fixes surfaced by a thorough onboarding and
due-diligence review, plus a vectorised aggregation fold and a dependency
security bump. (#7)

### Changed
- **`prospective_value` timing now follows the Excel annuity convention.**
  `end_of_period` is the ordinary annuity (Excel `PV` type 0) and
  `beginning_of_period` is the annuity-due (type 1); the two labels were
  previously inverted. Models that passed a timing argument will see their
  present values change — re-check any `prospective_value` timing against the
  Excel convention.

### Fixed
- `maximum_age` projection grids are sized from the *youngest* life in the book,
  so no policy's horizon is silently truncated.
- Excel `pv` is computed per policy instead of broadcasting the first row's
  `nper`/`pmt`/`rate` across the whole frame.
- Assumption-table dimension null-fills stay within their group instead of
  bleeding across partitions.
- Re-registering a table under an existing name with *different* data now warns
  instead of silently keeping the first table.
- `Period*` scenario aggregators reduce across scenarios per period on the
  scenario axis.
- Non-additive `run_aggregated` aggregators (`Mean`, `Variance`, `Std`,
  `Median`, `CTE`) are batch-invariant — both the plain and partitioned
  `.over()` folds divide by the policy count, not the number of batches.
- `RelativeFloorShock` raises with guidance instead of silently doing nothing.
- A uniform book whose input lists all disagree with the schedule's `n_periods`
  now fails loudly instead of truncating to the wrong horizon; variable-horizon
  ("jagged") books are unaffected.

### Performance
- `run_aggregated` batch folds are vectorised: `Sum`/`Min`/`Max`/`Mean`/
  `Variance`/`Std` reduce each batch in a single Polars pass, and the
  partitioned `.over()` path folds per group rather than iterating per policy.

### Security
- Bumped `crossbeam-epoch` 0.9.18 → 0.9.20 (RUSTSEC-2026-0204).

### Documentation
- The install page explains how to install `uv` and adds a verify step; the
  rollforward inspection page and the bundled model-building skill were corrected.

## [0.5.1] — CLI model-points loading

Bug-fix release for the `gspio` CLI and assumption-file loading. No engine or API
changes. (#5)

### Fixed
- `run-model`, `run-single-policy`, and `calc-graph` load model points from CSV as well
  as Parquet — the loader was Parquet-only despite the `--help` text; unsupported
  extensions now raise a clear error.
- Model points may live in any directory: the CLI previously kept only the file's
  basename and looked for it next to the model, so a path elsewhere failed with
  `FileNotFoundError`.
- `Table.from_scenario_files()` and `from_scenario_template()` accept CSV, Parquet, or a
  mix, matching the other assumption loaders (which were already format-agnostic).
- `run-single-policy` auto-detects the policy-ID column (`policy_id`, `policy_number`, …)
  when `--policy-id-column` is omitted, honouring an explicit name case-insensitively.

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
