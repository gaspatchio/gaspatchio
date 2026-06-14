# 42 — Auto-sizing research findings (provenance)

Source: a 6-agent research workflow (4 investigators + 2 adversarial verifiers),
2026-05-29, grounded in the repo code + Polars internals (verified empirically in
polars 1.38.1) + prior art. This is the evidence base behind the design spec.

## What is knowable *before* `.collect()`

**Knowable** (verified): column names + dtypes via `LazyFrame.collect_schema()`
(no materialisation; already used at `frame/base.py:284`); the **count** of
`List(Float64)`/`List(Date)` columns; `n_rows` analytically as
`n_policies × batch` (`n_policies` via cheap `select(pl.len())`).

**NOT knowable:** per-row **list length** — `collect_schema()` reports
`List(Float64)` but never the length (a jagged `[0.0,1.0]` and a uniform
`[0.9,0.8,0.7]` column are byte-identical in dtype); output **row cardinality** —
`explain()` returns a `str` and its `ESTIMATED ROWS` is a parquet-leaf figure
that does **not** propagate through the cross-join (verified: stayed 1000 after
cross-join×50 + filter); the **transient peak** working set (Polars
materialisation temporaries — the thing that OOMs); `estimated_size()` is
eager-`DataFrame`-only (`hasattr(pl.LazyFrame,'estimated_size') == False`).
Polars deliberately has **no** cardinality/cost estimator (open "missing pass",
pola-rs/polars#23345).

## Adversarial verdicts (both REFUTED, high confidence)

**V1 — "a reliable per-batch memory estimate can be computed from the pre-collect
schema": REFUTED.**
- `collect_schema()` gives dtypes, not list lengths → `n_periods` unavailable
  from the schema.
- `for_each_scenario` never receives a `Schedule`; `n_periods` is hardcoded
  `_DEFAULT_N_PERIODS = 240` (`_for_each.py:69,360`).
- `Schedule.n_periods` is a uniform scalar; for jagged per-policy termination it
  is only the portfolio max → over-counts.
- The analytic formula is a **steady-state** estimate; it systematically
  under-counts the **transient peak** that risks OOM (the reason
  `_measure_peak_delta` exists). Verified ~2% vs `estimated_size()` only on a
  trivially-fused plan; a plan with a Rust lookup plugin + `group_by` (which the
  planner cannot fuse) spikes well above steady-state.
- ⇒ analytic sizing is at best an optional cross-check, **not** a probe
  replacement. Keep the peak probe as the cold-start authority.

**V2 — "pure-projection (no-rollforward) can be auto-detected before collect to
flip jagged on by default": REFUTED.**
- `set()` and `rollforward()` are separate methods; `rollforward()` runs *after*
  `set()`, so at `set()` time "will this model roll forward?" is unknowable. The
  fact is only certain at `collect()` — after every list column is already
  materialised on the chosen grid, and there is no safe late uniform→jagged
  rewrite (list lengths are untracked).
- Cross-column list-length mismatch is **statically undetectable** (List dtype
  carries no length). The L5-*typed* model combines a **uniform external list**,
  so a blanket default-flip risks breaking it; a test documents reconciliation
  changes under a default flip.
- The runtime failure is **loud** (`ShapeError: list lengths differed`), never a
  silent wrong number — and `rollforward()` already rejects a `per_policy_grid`.
- ⇒ keep `per_policy` opt-in; rely on fail-closed (guardrail + loud ShapeError).

## Learned calibration cache — FEASIBLE

`resolve_batch_size` already has `manual` / `auto_probe` / `auto_calibrated`
(`_auto_batch.py:53,94-97`). The cache supplies the learned cost automatically
(a 4th label, `auto_cached`). `plan_sha = ScenarioRun.source_sha()`
(`_run.py:109-111`, sha over shocks+base_tables+aggregations+master_seed) is the
identity key but is **necessary-not-sufficient**: it does not cover the input
frame size (`input_data_fingerprint == {}`, `_run.py:272`), `n_periods`, the box,
or the model's output shape — hence the spec keys on `plan_sha` + an
**output-shape fingerprint** (List columns + horizon, read cheaply via
`collect_schema()`) rather than a brittle source hash, so it survives model
evolution and re-learns only when the memory profile changes. The cache learns
the true effective per-cell cost (folding in the unknown `n_periods` + real
footprint), eliminating both the 240 guess and the probe on
warm runs.

## Prior-art mechanisms (transferable)

- **Cost-based optimizers (Spark Catalyst CBO, DuckDB):** size from plan +
  column stats. Not available in Polars (no estimator) → must be external.
- **Adaptive Query Execution (Spark AQE):** start conservative, **measure**
  runtime stats at materialisation boundaries, **re-size** remaining work from
  the measured number. Highest-leverage, lowest-complexity; self-tunes per box.
  → this is the probe-then-reuse shape.
- **Memory-aware operators (DuckDB):** budget = % of physical RAM (DuckDB
  default 80%); spill-to-disk so a mis-estimate degrades to *slow*, not *crash*.
  → budget-as-RAM-fraction (adopted); spill is a future safety net (out of scope).
- **Learned/historical calibration (SQL Server CE Feedback, DB2 LEO, Spark
  AQORA):** persist estimated-vs-actual across runs so repeated queries
  self-correct. → the learned cache (adopted).

## Key file:line map (ScenarioRun branch unless noted)

- `scenarios/_auto_batch.py:53` `resolve_batch_size`; `:94-97` `auto_calibrated`
  formula `bytes_per_cell × n_policies × n_periods`.
- `scenarios/_for_each.py:69,360` hardcoded `_DEFAULT_N_PERIODS = 240`;
  `:340` `n_scenarios = len(sids)`; `:359` `n_policies` via `select(pl.len())`;
  `:404-412` `resolve_batch_size` call site (cache hooks); `:486-498` per-batch
  `model_fn` build + `collect()` (wrap in `_measure_peak_delta`);
  `:567-586` steady-state peak tracking (do **not** use for the cache write).
- `scenarios/_run.py:88-107` `canonical_form`; `:109-111` `source_sha` (plan_sha);
  `:264` audit record; `:272` empty `input_data_fingerprint`.
- `scenarios/_with_scenarios.py:112` drops `_projection` on the cross-joined frame.
- MAIN repo: `frame/base.py:284` non-materialising `collect_schema()`;
  `schedule/_schedule.py` `n_periods` attribute + `per_policy_grid` (portfolio-max
  only); `accessors/projection_frame.py` `set(per_policy=...)` + `rollforward()`
  guardrail.
