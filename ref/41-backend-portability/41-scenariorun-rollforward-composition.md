# ScenarioRun × Rollforward — how they compose

How the proposed `ScenarioRun` plan object (GSP-100) interacts with the rollforward kernel (GSP-92, shipped). Read alongside [`41-scenario-memory-design.md`](41-scenario-memory-design.md) and [`41-scenario-scaling-empirical.md`](41-scenario-scaling-empirical.md).

## TL;DR

`ScenarioRun` is the **outer scope**; the rollforward kernel is the **inner per-policy state-machine**. They sit at different levels of the stack, neither knows about the other directly, and that's the design. They compose at clear seams and ship independently.

| Layer | Concern | Owner |
|---|---|---|
| Outer loop | scenario-axis iteration, shock application, aggregation | `ScenarioRun` / `for_each_scenario` |
| Model logic | what to compute per scenario (rollforward, lookups, PV math) | user's `model_fn` |
| Inner kernel | per-policy per-period state machine | rollforward IR + Polars plugin (or future JAX/Mojo lowering) |

## Where they meet in code

The rollforward lives inside `model_fn`. `ScenarioRun.run()` calls `model_fn` once per scenario:

```python
def project_va(af: ActuarialFrame, *, tables: dict) -> ActuarialFrame:
    # ── Rollforward setup (per-policy state machine over periods) ──
    sched = Schedule.from_calendar_grid(...)
    af = af.projection.set(schedule=sched)
    b = af.projection.rollforward(states={"av": pl.col("av_init")})
    b["av"].deduct_nar(tables["mortality"].lookup(...), death_benefit=pl.col("db"))
    b["av"].charge(pl.col("admin_rate"))
    b["av"].grow(tables["fund_returns"].lookup(...))
    b["av"].floor(0.0)
    compiled = compile_rollforward(b)
    af.av = RollforwardCollector(compiled).expr_for("av")

    # ── Other model logic that uses scenario-shocked tables ──
    af.qx = tables["mortality"].lookup(age=af.attained_age, sex=af.sex)
    af.df = tables["discount_curve"].discount_factor(af.t)
    af.pv_claims = (af.qx * af.av * af.df).sum_lists()

    return af


scr = ScenarioRun(
    shocks={
        "BASE":     [],
        "MORT_UP":  [MultiplicativeShock(factor=1.15, table="mortality")],
        "RATES_UP": [AdditiveShock(delta=0.01, table="discount_curve")],
    },
    base_tables={"mortality": mortality, "discount_curve": dc, "fund_returns": fr},
    aggregations={"scr_capital": CTE("pv_claims", level=0.995)},
)

result = scr.run(af, model_fn=project_va)
```

What actually happens at runtime, one iteration of the outer loop:

```
ScenarioRun.run()
  └── for_each_scenario loop, scenario_id = "MORT_UP"
        ├── af_one = af.with_columns(scenario_id=lit("MORT_UP"))     ← outer: scenario tag
        ├── tables = {**base_tables, "mortality": mortality.apply_shock(MultShock(1.15))}
        ├── af_projected = project_va(af_one, tables=tables)         ← inner: model w/ rollforward
        │     └── compile_rollforward(b)                             ← rollforward kernel compiles
        │     └── RollforwardCollector(compiled).expr_for("av")      ← Polars plugin call
        │             └── rollforward kernel runs over n_policies rows × n_periods
        ├── df_one = af_projected.collect()                          ← rollforward executes here
        ├── state = agg.update(state, df_one)                        ← fold CTE sketch
        └── del df_one                                               ← peak RAM bounded
```

## Per-scenario isolation

Each scenario gets:

- **Its own shocked tables** (e.g. `MORT_UP` runs with `mortality × 1.15`; `BASE` runs with the base mortality table).
- **Its own compiled rollforward** built inside `model_fn`. The IR is stable across scenarios (see "Compile reuse" below) but the kernel call is fresh per scenario.
- **Its own per-policy state walk** — the rollforward kernel processes `n_policies` rows for `n_periods`, with state never leaking across scenarios.

The rollforward kernel never sees the scenario axis. From its perspective it ran once on `n_policies` policies. The fact that the same kernel ran `n_scenarios` times (once per scenario) is something only `ScenarioRun` knows.

## Memory composition

Peak RAM at any moment is bounded by **one scenario's full footprint**, which is:

```
policies frame
+ one scenario's shocked tables
+ rollforward state buffers (n_policies × n_states × n_points × 8 bytes)
+ per-period inputs (list columns)
+ collected result for this scenario
```

For the L5 typed VA at 1k policies × 240 periods × 1 state, that's ~570 MiB — same number measured in the empirical sweep. The rollforward state buffers are small relative to the list-column inputs (`1000 × 1 × 2 × 8 = 16 KB` of state vs ~110 KB/row of input lists). **Adding rollforward inside `model_fn` doesn't change the memory bound** — the outer-loop pattern dominates.

If `with_scenarios` had stayed in the picture, you'd cross-join to `n_policies × n_scenarios` rows and the rollforward kernel would run once on the giant frame — that's where the 570 GiB at 10k scenarios came from. `ScenarioRun` keeps `n_scenarios` out of the kernel's input shape entirely.

## Audit chain

Both objects carry identity. They roll up cleanly:

| Object | SHA / fingerprint method | Captures |
|---|---|---|
| Rollforward compiled IR | `compiled.fingerprint()` | op order, state graph, expression structure |
| `Schedule` | `source_sha()` | calendar grid, day count, business-day convention |
| `Curve` | `source_sha()` | tenors, rates, curve type |
| `MortalityTable` | `source_sha()` | dimensions, values |
| `ScenarioRun` | `source_sha()` | sorted shock IDs, shock canonical-forms, sorted aggregation keys, base-table source_shas |
| `ScenarioResult` | `plan_sha` field | snapshots `ScenarioRun.source_sha()` at run time |

The rollforward fingerprint is currently captured **inside the model** rather than exposed at the `ScenarioRun` level. If you want the audit chain to be fully closed at the run level, two options:

1. Record `compiled.fingerprint()` per run via instrumentation in `model_fn`.
2. Extend `ScenarioRun` to optionally accept a list of "model fingerprints" that `model_fn` declares before running.

Either is incremental and not blocking — file as a follow-up to GSP-100 if/when audit requires it.

## Compile reuse — a small optimization

The rollforward IR is **deterministic from the model spec**, not from the data. Shocks change the *values* feeding the IR (e.g. mortality rates) but not the IR's structure (states, ops, orderings). The compile step doesn't need to repeat per scenario.

Currently `model_fn` calls `compile_rollforward(b)` on every iteration. A user can hoist it once outside the loop:

```python
# Compile ONCE outside the loop
sched = Schedule.from_calendar_grid(...)
b = build_va_rollforward_builder(sched)
compiled_va = compile_rollforward(b)

def project_va(af, *, tables):
    af = af.projection.set(schedule=sched)
    af.av = RollforwardCollector(compiled_va).expr_for("av")  # reuses compiled IR
    af.qx = tables["mortality"].lookup(...)
    af.df = tables["discount_curve"].discount_factor(af.t)
    af.pv_claims = (af.qx * af.av * af.df).sum_lists()
    return af

result = scr.run(af, model_fn=project_va)  # compiled_va captured by closure
```

Compile is small relative to kernel execution at production scale, so this is "tidier" rather than "faster". Worth documenting in tutorials; not worth blocking on.

## Batching: per-scenario shocks composed into stacked tables

`batch_size=1` is the safe default — one scenario in flight, peak RAM bounded by one scenario's footprint. But it leaves throughput on the table: every batch pays per-call PyO3 / Polars / Rust setup overhead once, regardless of scenario count. At higher batch sizes the rollforward kernel runs on `batch_size × n_policies` rows in one pass; setup amortises across the batch.

The slider is a memory↔throughput tradeoff with no correctness consequences:

| `batch_size` | Behaviour | Equivalent to |
|---|---|---|
| `1` | One scenario per kernel call | today's `for_each_scenario` (or `batch_scenarios(size=1)`) |
| `N` | N scenarios per kernel call, peak RAM = `N × per_scenario_footprint` | today's `batch_scenarios(size=N)` |
| `n_scenarios` | All scenarios in one mini cross-join | today's `with_scenarios` |
| `"auto"` | Probe one scenario, measure peak RSS, extrapolate to safety-fraction of available RAM | new |

### Per-scenario shocks compose inside a batch

The batch is *not* restricted to scenarios with identical shocks. Different shocks per scenario in a batch is the whole point of batching for SCR / sensitivity work. The mechanism: each batch builds **scenario-stacked shocked tables** with `scenario_id` as an extra dimension.

```python
def stack_shocked_table(
    base: Table,
    per_scenario_shocks: dict[ScenarioID, list[Shock]],
) -> Table:
    """Stack one shocked Table with scenario_id as an extra dimension.

    Each scenario in per_scenario_shocks gets its own slice of rows, with the
    value column carrying that scenario's shock-list applied via the existing
    Shock.to_expression() composition.
    """
    parts = []
    for sid, shocks in per_scenario_shocks.items():
        df = base._df.with_columns(scenario_id=pl.lit(sid))
        value_expr = pl.col(base._value)
        for shock in shocks:
            value_expr = shock.to_expression(value_expr)        # apply this scenario's deltas
        df = df.with_columns(value_expr.alias(base._value))
        parts.append(df)

    return Table(
        name=f"{base._name}_stacked",
        source=pl.concat(parts),
        dimensions={"scenario_id": "scenario_id", **base._dimensions},
        value=base._value,
    )
```

For a batch containing `MORT_UP` (mortality × 1.15), `LONGEVITY` (× 0.80), and `BASE` (no shock), the stacked mortality table is `3 × n_base_rows` long, each row keyed by `scenario_id` with the right shocked rate.

### What the model sees

Lookups gain `scenario_id` as a key when batched:

```python
def project_va(af, *, tables):
    af.qx = tables["mortality"].lookup(
        scenario_id=af.scenario_id,    # extra key — present whenever batch_size > 1
        age=af.attained_age,
        sex=af.sex,
    )
    af.lx = tables["lapse"].lookup(scenario_id=af.scenario_id, duration=af.duration)
    af.df = tables["discount_curve"].discount_factor(af.t)
    return run_va_engine(af)
```

The `scenario_id` column is already on every row of the mini cross-join `af_batch = with_scenarios(af, batch_ids)`. Polars's existing multi-dim hash and array-storage lookup paths handle the join — no kernel change needed.

### Loop with per-scenario shocks in a batch

```python
for batch_idx, batch in enumerate(chunks(scenarios.items(), batch_size)):
    # batch is e.g. [("MORT_UP", [MultShock(1.15, "mortality")]),
    #                ("LONGEVITY", [MultShock(0.80, "mortality")]),
    #                ("BASE", []), ...]

    # 1. Stack each base table along scenario_id, applying per-scenario shocks
    stacked_tables = {}
    for name, base_table in base_tables.items():
        per_scenario_shocks_for_table = {
            sid: [s for s in shock_list if s.table == name]
            for sid, shock_list in batch
        }
        stacked_tables[name] = stack_shocked_table(
            base_table, per_scenario_shocks_for_table,
        )

    # 2. Mini cross-join the policy frame with this batch's scenario IDs
    af_batch = with_scenarios(af, [sid for sid, _ in batch])

    # 3. Run the model — lookups join on scenario_id + native dims
    af_proj = model_fn(af_batch, tables=stacked_tables)

    # 4. Materialise this batch only, fold all N scenarios into agg, drop
    df_batch = af_proj.collect()
    state = agg.update(state, df_batch)
    if return_full_grid:
        df_batch.write_parquet(
            sink_dir / f"batch_{batch_idx:04d}.parquet",
            partition_by="scenario_id",        # one file per scenario on disk regardless
        )
    del df_batch
```

The rollforward kernel inside `model_fn` sees `batch_size × n_policies` rows in one call. State buffers grow to `n_policies × batch_size × n_states × n_points × 8 bytes` — still small compared to list-column inputs.

### Cost of the stack

Stacked-table memory is `n_table_rows × batch_size`, negligible for typical actuarial tables:

- Mortality: ~1k–10k rows × 64 batch = 64k–640k rows = MBs, not GBs.
- Lapse, expense, surrender: ~hundreds × 64 ≈ ~tens of thousands. Trivial.
- Discount curve: ~30 tenors × 64 ≈ 2k. Trivial.
- Long-form ESG returns table: already has a `scenario_id` dimension — no stacking needed; just filter to the batch's scenario IDs.

The dominant memory term remains `n_policies × batch_size × per_row_footprint` on the policy frame. Stacked tables add a few MB on top.

### Auto-sizing strategy

`batch_size="auto"` does a single probe-then-extrapolate:

1. Run scenario 1 solo, measure peak RSS via `psutil`.
2. Compute `target = available_memory × target_fraction` (default `0.5`).
3. Choose `batch_size = max(1, target // per_scenario_bytes)`, capped at a safety ceiling (e.g. 256).
4. Record the chosen size on `ScenarioResult.batch_size` and in `describe()` for reproducibility.

The probe scenario's result still flows into the aggregator — no wasted work. A more adaptive approach (progressive doubling with backpressure) is deferred until benchmarks justify the extra moving parts; the single probe cleanly answers "how big can we go on this machine for this model" without complicating the audit story.

### Edge cases

- **`FilteredShock` (`where=`) and `TimeConditionalShock` (`when=`)** carry Polars expressions. Stacking applies each scenario's condition on its slice of the stacked frame independently. Works as long as the condition expressions reference columns present on the stacked frame (typically dimensions, which are). Verify in tests.
- **`PipelineShock`** composes via `to_expression(col)` chaining inside the for-loop above — no special case needed.
- **`ParameterShock`** doesn't fit table-stacking (it modifies a scalar parameter, not a table). Best handled via the `scenarios=dict[id, dict]` driver-dict path of `for_each_scenario` rather than via `base_tables` shocks. Worth flagging in docs; not v0.1 critical.
- **Aggregator correctness.** `Mean` / `CTE` / `GroupedAgg.update()` fold rows in — they don't care whether one call carries one scenario or N. State evolves identically. Test by running the same plan at `batch_size=1` and `batch_size=N`; results should match bit-for-bit.

### Forward compat under JAX

When the JAX backend lands (GSP-99), batching becomes implicit — `vmap` over scenarios is the kernel's native parallelism, not an outer-loop concept. The Polars-backend `batch_size` knob stays correct as the laptop fallback; the JAX-backend path simply ignores it (or treats every "batch" as the full scenario axis under HBM constraints).

## Forward compatibility with the JAX backend

The rollforward IR already reserves `batch_axes` for the scenario-axis case (`bindings/python/gaspatchio_core/rollforward/_ir.py:11`). The intended evolution under GSP-99:

| Today (Polars backend) | Tomorrow (JAX backend, GSP-99) |
|---|---|
| `ScenarioRun` outer loop iterates scenarios sequentially | `ScenarioRun.run()` could detect `batch_axes=('scenario','policy')` IRs and dispatch to `LowerToJax` |
| Each iteration calls `compile_rollforward` (or reuses) and runs the Polars plugin on `n_policies` rows | The JAX kernel runs `vmap(scan)` over `(n_scenarios, n_policies)` in one go |
| Memory bounded by single-scenario footprint | Memory bounded by GPU HBM; scenarios run in parallel |
| Wall time linear in `n_scenarios` | Wall time near-constant in `n_scenarios` (within HBM) |

`ScenarioRun` stays correct in either world. The Polars-backend path is the laptop-friendly default; the JAX-backend path is the accelerator route. The user-facing API doesn't change — `scr.run(af, model_fn=project_va)` works in both cases.

## Why they're separate tickets

GSP-99 and GSP-100 are independent improvements at different layers. Land them in any order; ship one without the other.

- **GSP-100 alone** delivers bounded-memory stochastic runs on the laptop, today, on the existing Polars stack. The rollforward kernel doesn't change. ESG / SCR / sensitivity workloads that don't fit memory today start fitting.
- **GSP-99 alone** delivers a JAX-lowered rollforward kernel that vmaps over scenarios. Without `ScenarioRun`, users would invoke it via the existing rollforward API with `batch_axes=('scenario','policy')` and feed scenario tensors directly.
- **GSP-99 + GSP-100** is what pays off for nested-stochastic / GPU workloads. `ScenarioRun.run()` detects portable IRs and dispatches to JAX; everything else routes through the Polars-backend loop.

Each delivers value alone; the combination is multiplicative.

## See also

- GSP-99 — backend portability research synthesis (parent)
- GSP-100 — `ScenarioRun` + `for_each_scenario` ticket
- [`README.md`](README.md) — research bundle index
- [`41-scenario-memory-design.md`](41-scenario-memory-design.md) — design recommendation for `ScenarioRun`
- [`41-scenario-scaling-empirical.md`](41-scenario-scaling-empirical.md) — measurements that motivated `ScenarioRun`
- `bindings/python/gaspatchio_core/rollforward/_ir.py:11` — `batch_axes` slot reserved for scenario-axis vmap
- Commit `9824f2d` — lazy `with_scenarios` (contributing fix already shipped)
