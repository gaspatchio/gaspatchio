---
name: gaspatchio-model-scenarios
description: Use when running scenario analysis, applying parameter shocks, performing sensitivity sweeps, or producing scenario comparison reports on a gaspatchio model.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Model Scenarios

I'm using the gaspatchio model scenarios skill.

## When to use this skill

This skill can be used standalone on any gaspatchio model. It does NOT require model-building, model-discovery, or any other skill to have been run first. Use it whenever the user asks about:

- "What-if" analysis
- Sensitivity testing or sensitivity sweeps
- Stress testing or scenario analysis
- Comparing model results under different assumptions
- Parameter shocks (mortality, lapse, interest rates, expenses)
- Regulatory or economic scenario comparison

It also fires **without a user request** when the *source* is scenario-shaped: a
workbook under conversion whose variant/scenario tabs are the ask. Decide the axis
first via the model-building classification gate — input-shaped variants belong to
this skill's machinery; wiring-divergent variants become a model-point row axis
instead, and this skill's runner is the wrong tool.

## Hard gate

Do NOT claim scenario analysis is complete until a `report/report.md` exists containing charts (embedded PNGs) and the run's audit chain (plan SHA + JSON audit sidecar from `ScenarioRun.run(audit=True)`). Every scenario run produces a report.

---

## CRITICAL RULE: Two-Script Pattern

Scenario analysis uses two scripts with strict separation of concerns:

| Script | Purpose | Modify for scenarios? |
|---|---|---|
| `model.py` | The projection model as reconciled (`def main(af)`) | **NEVER** |
| `run_scenarios.py` | Scenario orchestration: build a `ScenarioRun`, run it, write the report | **YES** |

**`model.py` stays UNCHANGED.** All scenario logic goes in `run_scenarios.py`, and `plan.run(af, model.main)` runs the model exactly as `gspio run-model` does. The model needs no `assumptions_override`, no wrapper and no `scenario_id` guard at its lookups: the plan names its targets and answers the model's own reads of them (see *How the plan reaches the model*). The model remains debuggable with `gspio run-model` for any single scenario.

```bash
# Model works standalone — no scenario machinery needed
uv run gspio run-single-policy model.py data.parquet 1

# Scenario analysis is layered on top
uv run python run_scenarios.py
```

---

## The Canonical Path: `ScenarioRun`

A `ScenarioRun` is the typed plan that captures shocks, aggregations, and optionally the base tables it states and a master seed, as a single hashable value. You build it, run it against the model you reconciled, and the result carries the plan's SHA + an opt-in JSON audit sidecar — so the same plan always produces the same SHA, and re-running is one Python call.

```python
import model
from gaspatchio.scenarios import (
    ScenarioRun,
    AdditiveShock,
    MultiplicativeShock,
    Sum,
)

plan = ScenarioRun(
    shocks={
        "BASE": [],
        "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality_select")],
        "LAPSE_DOWN_20": [MultiplicativeShock(factor=0.8, table="lapse_rates")],
        "RATE_UP_100BP": [AdditiveShock(delta=0.01, column="valuation_rate")],
    },
    aggregations=(
        Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
        Sum("pv_claims").alias("pv_claims").over("scenario_id"),
    ),
)
result = plan.run(af, model.main, audit=True)
print(plan.source_sha())              # 'sha256:…'  — identity of the plan
print(result.aggregations["pv_net_cf"])  # DataFrame: one row per scenario
print(result.audit_path)              # the JSON audit sidecar: gaspatchio_audit/<run_id>.audit.json under the cwd
print(result.fingerprint("BASE"))     # == model.main(af).graph.fingerprint()
```

**Three things make this path the default:**

- **Mergeable aggregators.** `Sum`, `Mean`, `Min`, `Max`, `ArgMin`, `ArgMax`, `Count`, `Variance`, `Std`, `Quantile`, `Median`, `CTE`, `QuantileRank`, plus `BaseAggregator` for custom ones (skewness, TVaR, anything mergeable). Each carries its own column and within-scenario reduction; `.alias(name).over("scenario_id")` produces one row per scenario.
- **Bounded memory.** The plan is driven by `for_each_scenario(batch_size=…)` under the hood — peak RSS is one batch's working set, not the cross-product of policies × scenarios.
- **Identity + audit.** `plan.source_sha()` is a content hash over `(shocks, aggregations, master_seed)` and any `base_tables` the plan states. `plan.to_yaml(path)` writes every shock kind and reads back to the same SHA; `plan.run(audit=True)` writes a JSON audit sidecar capturing the SHA, each scenario's graph fingerprint (BASE's is the standalone model's) and, per shocked table, the content its shock was applied to (`bases`) — where it lands: *Audit Chain* below.

**The model's Phase 1 stays on the frame.** A batch is the book crossed with as many scenarios as `batch_size` (by default `"auto"`) packs into it, so a collected frame holds every scenario's copy of the book. Wherever a batch holds more than one scenario, a frame rebuilt from collected values -- `mp = af.collect()`, a column or a join in plain Polars, `af = ActuarialFrame(mp)` -- is refused by name, and a plan that ran with two scenarios can be refused with fifty. Write the setup the way the refusal says: compute a figure across the book (a share of sum assured) on the model points before the run, bring a side table in with `af.join(table, on=...)` and do per-row work by assignment, closing Phase 1 with `af.materialize()`; or, where the values genuinely have to leave the frame, run one scenario a batch, `plan.run(af, model.main, batch_size=1)`. Worked example: `model-building` → [references/scenarios.md](../gaspatchio-model-building/references/scenarios.md#phase-1-under-a-plan-keep-the-setup-on-the-frame).

---

## Scenario Types (Progressive)

Teach and apply these in order. Each level builds on the previous.

### Level 1 — Interest Rate Scenarios (simplest)

Where the model itself holds one rate curve per scenario and picks per row on `scenario_id` (the L5 model does, with three `Curve`s), a plan with empty shock lists is enough: it cross-joins the axis and the model's own dispatch does the rest.

```python
plan = ScenarioRun(shocks={"BASE": [], "UP": [], "DOWN": []}, aggregations=AGGREGATIONS)
result = plan.run(af, model.main, audit=True)
```

Each scenario still gets an identity of its own: a model that reads `scenario_id` is composed alone over a one-scenario axis, so UP's fingerprint is not BASE's. For exploration, the low-level `with_scenarios(af, ids)` cross-join does the same without a plan; promote to `ScenarioRun` when the analysis settles.

**Chart**: Grouped bar chart comparing PV metrics across scenarios.

### Level 2 — Parameter Shocks

**Note:** Stresses and shocks belong in this scenario system (`scenarios/shocks` composables), NOT as custom accessors. If someone asks to "add a lapse stress accessor," redirect them here. Use `gaspatchio-extending` only for new reusable calculations, not for stress/scenario modifications.

Declare per-scenario shock recipes as a `dict[str, list[Shock]]` and run the plan. Every shock names exactly one target: `table=` an assumption table the model reads, by the name its `Table` was built with, or `column=` a model-point column:

```python
from gaspatchio.scenarios import (
    ScenarioRun,
    MultiplicativeShock,
    AdditiveShock,
    OverrideShock,
    Sum,
)

SHOCKS = {
    "BASE": [],
    "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality_select")],
    "LAPSE_DOWN_20": [MultiplicativeShock(factor=0.8, table="lapse_rates")],
    # Scalars stay the model-point columns the conversion skill made them.
    "RATE_UP_100BP": [AdditiveShock(delta=0.01, column="valuation_rate")],
    "EXPENSE_UP_10": [MultiplicativeShock(factor=1.1, column="maint_expense")],
    "SOLVED_PREMIUM": [OverrideShock(value=1234.56, column="annual_premium")],
}

plan = ScenarioRun(
    shocks=SHOCKS,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)
result = plan.run(af, model.main, audit=True)
```

Do **not** move a scalar into a one-row table to make it shockable — `column=` shocks it where it is, with the same numbers bit for bit.

**Chart**: Tornado chart ranking sensitivities by absolute impact on the headline metric.

### Level 3 — Conditional Shocks

`FilteredShock`, `TimeConditionalShock`, and `PipelineShock` compose targeted stresses:

```python
from gaspatchio.scenarios import (
    FilteredShock,
    TimeConditionalShock,
    PipelineShock,
    MultiplicativeShock,
    ClipShock,
)

SHOCKS = {
    "ELDERLY_MORT_UP_25": [
        FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"age": {"gte": 65}},
            table="mortality_select",
        ),
    ],
    "SOLVENCY_II_LAPSE_UP": [
        PipelineShock(
            shocks=(MultiplicativeShock(factor=1.5), ClipShock(max_value=1.0)),
            table="lapse_rates",
        ),
    ],
    "EARLY_EXPENSE_UP_10": [
        TimeConditionalShock(
            shock=MultiplicativeShock(factor=1.10),
            when={"duration": {"lte": 5}},
            table="surrender_charges",
        ),
    ],
}
```

| Composable | Meaning |
|---|---|
| `FilteredShock(shock, where=…)` | Shock only applies to rows matching the filter — table keys for a `table=` shock, model-point columns for a `column=` one |
| `TimeConditionalShock(shock, when=…)` | Shock applies during a time window, named by the table's own time key (`table=` only: a model-point column has no periods) |
| `PipelineShock(shocks=(…))` | Chain transformations — apply in sequence |

The target goes on the outermost shock; an inner shock may repeat it or name none.

`where` takes a bare value for equality, or one of `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between: [lo, hi]`, `in: [...]`, `not_in: [...]`; several keys AND together. On a `column=` shock it reads model-point columns, so `FilteredShock(shock=AdditiveShock(delta=0.01), where={"policy_id": {"in": ["P1", "P2"]}}, column="disc_rate")` moves two policies' rate.

The shocks-shape `ScenarioRun` accepts these the same way it accepts `MultiplicativeShock` etc.

**Chart**: Cashflow line chart over projection time showing how conditional shocks diverge from base.

### Level 4 — Sensitivity Sweeps

Systematically vary a single parameter (or two, for a 2D interaction grid). There is no special helper — build the shocks dict with a list comprehension, hand it to `ScenarioRun`:

```python
import itertools
from gaspatchio.scenarios import ScenarioRun, MultiplicativeShock, Sum

mort_values = [0.8, 0.9, 1.0, 1.1, 1.2]

# 1D sweep
sweep_1d = {
    f"MORT_x{v:.2f}": (
        [MultiplicativeShock(factor=v, table="mortality_select")] if v != 1.0 else []
    )
    for v in mort_values
}

# 2D interaction grid (mortality × lapse)
lapse_values = [0.8, 0.9, 1.0, 1.1, 1.2]
sweep_2d = {}
for m, l in itertools.product(mort_values, lapse_values):
    shocks = []
    if m != 1.0:
        shocks.append(MultiplicativeShock(factor=m, table="mortality_select"))
    if l != 1.0:
        shocks.append(MultiplicativeShock(factor=l, table="lapse_rates"))
    sweep_2d[f"M{m:.2f}_L{l:.2f}"] = shocks

plan = ScenarioRun(
    shocks=sweep_2d,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)
result = plan.run(af, model.main)
# Pivot the result into a heatmap-ready DataFrame:
heatmap = result.aggregations["pv_net_cf"].with_columns(
    pl.col("scenario_id").str.split("_").list.get(0).str.strip_prefix("M").cast(pl.Float64).alias("mortality_mult"),
    pl.col("scenario_id").str.split("_").list.get(1).str.strip_prefix("L").cast(pl.Float64).alias("lapse_mult"),
).pivot(values="pv_net_cf", index="mortality_mult", on="lapse_mult")
```

A sweep of affine column shocks (multiply, add, set) runs as per-scenario factors, so even a thousand-point sweep of `AdditiveShock(…, column="valuation_rate")` fits one batch; other column shocks build one `when` branch per scenario, so keep large sweeps affine.

**Charts**: Sensitivity curve (1D) and heatmap (2D) showing how the metric responds across the parameter space.

### Level 5 — Regulatory Comparison

Named scenarios as economic narratives — each combines multiple per-table shocks into a coherent stress, and the audit chain captures the recipe alongside the run:

```python
SHOCKS = {
    "CENTRAL_ESTIMATE": [],
    "ADVERSE_MORTALITY": [
        MultiplicativeShock(factor=1.40, table="mortality_select"),
        FilteredShock(
            shock=MultiplicativeShock(factor=1.20),
            where={"age": {"gte": 65}},
            table="mortality_select",
        ),
    ],
    "ECONOMIC_DOWNTURN": [
        MultiplicativeShock(factor=0.75, table="lapse_rates"),
        MultiplicativeShock(factor=0.50, table="surrender_charges"),
    ],
}

# Optional: state the tables the plan shocks; the run then refuses a model
# whose table of that name holds other rates. Keyed by each table's own name.
plan = ScenarioRun(shocks=SHOCKS, base_tables=BASE_TABLES, aggregations=AGGREGATIONS)
print(plan.describe())                 # human-readable summary + SHA
plan.to_yaml(SCRIPT_DIR / "plan.yaml") # every shock kind, filters included
assert ScenarioRun.from_yaml(SCRIPT_DIR / "plan.yaml", base_tables=BASE_TABLES).source_sha() == plan.source_sha()
result = plan.run(af, model.main, audit=True)
print(result.audit_path)               # JSON audit sidecar
```

`plan.source_sha()` changes the moment the recipe changes; `plan.to_yaml()` writes the recipe to a file for governance archives, and `from_yaml` reads back the same plan to the same SHA, whatever kinds of shock it holds.

**Charts**: Grouped bar chart comparing scenario outcomes + full regulatory-style report with the audit chain.

---

## How the plan reaches the model

`plan.run(af, model.main)` calls the model once per batch as `model.main(af)`, with:

- `af` cross-joined with the batch's `scenario_id` column, every `column=` shock already applied to its column for each scenario's rows (recorded as an assignment at the plan's line).
- The model's own `Table.lookup` / `MortalityTable.at` reads of a table a shock names answered with that table stacked per scenario, keyed by the axis. Tables no shock names are read exactly as written.
- With `master_seed=` on the plan, each scenario's seed as the `rng_seed` column, at any batch size. A model that draws its own randomness reads `af.rng_seed`.
- A compiled rollforward reads a shocked table through a column: `af.coi = coi.lookup(age=af.attained)`, then `.charge(af["coi"])`. Each scenario's balances are then the ones it reaches alone, on Polars and on JAX. A lookup handed to the rollforward directly is refused, since its operands are bare columns.
- Every fold is the same bits at any batch size and on every run: each scenario is folded on its own rows, in the run's order.
- A read across rows in the model -- a `sum`, `rank` or `over` through `.polars_native()` or raw `pl.col`, or `pl.len()` -- is refused on the axis at any batch size, in a filter's condition as in an assignment, since its rows are every scenario's copy of every policy. Compute a figure across the book before the run, as a model-point column the model reads, or partition the read by the scenario: `pl.col("sa").sum().over("scenario_id")` reads one scenario's copy of the book, and a plan never cuts the policies into batches, so it is each scenario's own figure and runs; further keys stay inside that copy, so `.over(["scenario_id", "product"])` runs too. A shared projection grid sized from the rows (`per_policy=False` over a column horizon or a maximum age) is refused on the axis too: leave `per_policy` at its default.

A model written for the old door still runs: a `"scenario_id" in table.dimensions` guard is false on the model's own table. A function requiring `tables=`/`drivers=` is refused with the move; that three-argument form stays only on `for_each_scenario`'s ids and drivers shapes.

The binding is strict, and each refusal names the next move:

| You wrote | The run says |
|---|---|
| a shock with no target, or with both `table=` and `column=` | names the targets; confine rows with `FilteredShock(where=…)` |
| `table=` a name no read of the model reached | after the first batch, the tables the model did read, and the closest |
| `column=` a column the model points do not hold | the closest column, and the conversion skill's scalar rule |
| `TimeConditionalShock` on a `column=` | a model-point column has no periods |
| a `where=`/`when=` on a column the shocked table does not hold | the table's columns: a condition reads the table's own keys, not projection time |
| a `where=`/`when=` that selects no row of its table (`{"policy_year": {"eq": 0}}` on a table keyed from 1) | what the table holds (`'policy_year' holds 1 to 20`): the scenario would equal BASE |
| `table.to_dataframe()` of a shocked table inside the run | its rows differ by scenario; read it through `lookup()` |
| a model that returns (or reads from) a frame without `scenario_id` | carry the axis through the model |
| `base_tables` holding a table the model's differs from | the two content fingerprints |

**BASE is the reconciled model, checked.** Each scenario's fingerprint is the scenario composed alone — the model over the book, reading only its own shocked tables and columns — so `result.fingerprint("BASE") == model.main(af).graph.fingerprint()`. Put that equality in the report. On a run of more than one scenario `result.graph_fingerprint` is `None`: there is no one calculation to name, so ask `result.fingerprint(sid)` per scenario.

### What a plan does not do in 1.0

- **No goal seek inside a plan.** Solve outside it (a bisection on `model.main` over the one policy), then ride the solved value in: `FilteredShock(shock=OverrideShock(value=solved), where={"policy_id": "P1"}, column="premium")`.
- **No yield-curve shock.** A shock names a table or a model-point column, and a `Curve` is neither. Carry the shift as a model-point column the model adds to the curve's rate (`af.spot_shifted = RFR.spot_rate(af.t) + af.curve_shift`) and shock that: `AdditiveShock(delta=0.01, column="curve_shift")`. Or keep the rate itself a model-point column.

---

## Report Requirements (Non-Negotiable)

Every scenario run must produce `report/report.md` containing ALL of these sections:

### 1. Model Metadata

| Field | Example |
|---|---|
| Model points | 8 |
| Scenarios | 6 |
| Runtime | `result.wall_time_s` |
| Plan SHA | `plan.source_sha()` |

### 2. Scenario Configuration

`plan.describe()` output inline (it gives a human-readable summary of every scenario + the SHA). For YAML-serialisable plans, link to the `plan.yaml` sidecar.

### 3. Results Summary Table

| scenario_id | pv_net_cf | vs_base_pct |
|---|---|---|
| BASE | 1,234,567 | -- |
| MORT_UP_20 | 1,198,432 | -2.9% |
| RATES_DOWN | 1,301,234 | +5.4% |

Include % change from base for every scenario.

### 4. Embedded Chart PNGs

Charts saved as PNGs in `report/` and embedded with `![](chart_name.png)`.

### 5. Key Findings

Auto-generated observations. At minimum:
- Which scenario has the largest impact (and direction)
- Which scenario has the smallest impact
- Any notable asymmetries (e.g., rate up vs rate down convexity)

### 6. Audit Chain

- `plan.source_sha()` — pin this in the report so the run is reproducible.
- `result.audit_path` — the audit sidecar. `plan.run(af, model.main, audit=True)` writes `<run_id>.audit.json` into `./gaspatchio_audit/`, relative to the working directory — or into `sink_dir` when one is given; `audit="evidence/q3.audit.json"` writes exactly there. The `<run_id>` is the time to the second and the plan's sha, so a second run of one plan in the same second is refused (`FileExistsError`, nothing written over the first); a path you name is yours, and a later run replaces it. Name one path per run for release evidence.
- The sidecar's `run_metadata` carries the same library keys as an audit file's `producer.versions` — core and extension versions, the extension's digest, Polars, Python, platform — plus `ddsketch_version`; it does **not** carry `imports` or git. `run(versions="withheld")` withholds them for a sidecar committed as a golden.
- The audit file of the scenario run: `gspio calc-graph model.py data.parquet --scenarios run_scenarios.py -o scenarios.audit.json` runs the plan once and writes the run's own sidecar beside it as `scenarios.run.audit.json`. The script declares `SCENARIO_RUN` (a `ScenarioRun`, or a function returning one) and `MODEL_FN`; it is imported to reach them, so its own run goes under `if __name__ == "__main__":`.

---

## Chart Guidance

Match the chart to the analysis type. Using the wrong chart obscures the story.

| Analysis Type | Chart | What It Shows |
|---|---|---|
| Interest rate comparison | Grouped bar chart | Side-by-side scenario totals |
| Parameter shocks | Tornado chart | Ranked sensitivities by absolute impact |
| Conditional shocks | Cashflow line chart over time | Where and when scenarios diverge from base |
| Sensitivity sweep (1D) | Sensitivity curve | Metric response across parameter range |
| Sensitivity sweep (2D) | Heatmap | Interaction effects across two parameters |
| Regulatory comparison | Grouped bar + full report | Named scenarios with audit chain |

Use Altair for all charts.

---

## Tutorial Reference

Level 5 of the tutorial (`tutorial/level-5-scenarios/`) is the worked example for this skill. Every step is built around `ScenarioRun`:

| Tutorial Step | Skill Level | What It Demonstrates |
|---|---|---|
| Base | Level 1 | Interest rate scenarios: a plan with empty shocks, the model's own curve dispatch |
| Step 01 | Level 2 | `ScenarioRun` + `MultiplicativeShock` + per-scenario aggregators + audit sidecar + tornado data |
| Step 02 | Level 3 | `FilteredShock`, `TimeConditionalShock`, `PipelineShock` (Solvency II ×1.5 then clip 1.0) |
| Step 03 | Level 4 | 1D mortality sweep + 2D mortality × lapse interaction grid |
| Step 04 | Level 5 | Named regulatory stresses, full audit chain (`source_sha`, `to_yaml` round trip, stated `base_tables`, JSON sidecar) |
| Step 05 | — | 200 stochastic scenarios: each draw is the scenario's shock, so the plan carries every draw |

Every step has a working `run_scenarios.py`. Start from the step closest to what the user needs and adapt.

---

## gaspatchio Scenario API Quick Reference

### Plan & loop

| Symbol | What It Does |
|---|---|
| `ScenarioRun(shocks, aggregations, base_tables=…, master_seed=…)` | Typed plan dataclass; hashable; `source_sha()`, `to_yaml()`, `describe()`, `run()` |
| `ScenarioRun.run(af, model.main, *, batch_size, audit, versions, return_full_grid, sink_dir)` | Runs the reconciled model under the plan via the bounded-memory loop; returns `ScenarioResult`. `return_full_grid=True` writes every scenario's projection to Parquet, one file per batch, and needs `sink_dir=` |
| `ScenarioResult.aggregations[alias]` | With `.over("scenario_id")`: a `pl.DataFrame`, one row per scenario (a `Period*` one, one row per scenario and period). Without: one value folded over every row of the run — all scenarios together |
| `ScenarioResult.audit_path` | Path to the JSON audit sidecar when `run(audit=...)` |
| `ScenarioResult.graph_fingerprint` | `None` on a run of more than one scenario — use `fingerprint(sid)` |
| `ScenarioResult.fingerprint(sid)` | The calculation one scenario folded, composed alone (`audit=` runs) |
| `ScenarioResult.bases` | Per shocked table: the content fingerprint the shock was applied to, and its file |
| `for_each_scenario(af, scenarios, model_fn, aggregations)` | Lower-level loop; `ScenarioRun.run` builds on this. Ids and drivers shapes keep `model_fn(af, *, tables, drivers)` |
| `with_scenarios(af, ids)` | Low-level cross-join — escape hatch for one-shot exploration |

### Shock composables

In a plan every shock names exactly one target: `table=` an assumption table the model reads, by the name its `Table` was built with, or `column=` a model-point column. An untargeted or doubly-targeted shock, a table no read reaches, or a column the book does not hold is refused. A wrapped or piped inner shock takes its outer shock's target.

| Class | Operation |
|---|---|
| `MultiplicativeShock(factor=…)` | Scale by factor |
| `AdditiveShock(delta=…)` | Add constant |
| `OverrideShock(value=…)` | Replace |
| `ClipShock(min_value=…, max_value=…)` | Cap/floor |
| `FilteredShock(shock=…, where=…)` | Dimension WHERE clause |
| `TimeConditionalShock(shock=…, when=…)` | Time WHEN clause (`table=` only) |
| `PipelineShock(shocks=(…))` | Chain operations left-to-right |
| `MaxShock` / `MinShock` | Element-wise max/min of two shocks (`MaxShock(MultiplicativeShock(0.5), AdditiveShock(-0.2))` is the Solvency II lapse-down floor) |

### Aggregators (with `.alias(name)` + `.over(by)` / `.of(expr)`)

| Class | Reduction |
|---|---|
| `Sum`, `Mean`, `Min`, `Max`, `Count` | Trivial parallel-merge |
| `ArgMin`, `ArgMax` | Returns the partition key (e.g. `scenario_id`) |
| `Variance`, `Std` | Welford-Chan parallel-merge |
| `Quantile(levels=…)`, `Median` | DDSketch-backed, mergeable |
| `CTE(level=…, direction=…)` | Tail conditional expectation (SCR-shape) |
| `QuantileRank(at=…)` | Inverse — fraction below a threshold |
| `BaseAggregator` | Subclass for custom merge-able metrics |

### Per-Period Aggregators (vector output — term structure)

Every scalar aggregator above has a **`Period*` twin** that folds a per-period column period by period. Use `Period*` when you need the full term structure of a metric across the projection — e.g. net cashflow or reserve *over time* under each stress — not just its present value. (A scalar aggregator over a per-period column is refused, naming its `Period*` form.)

A `Period*` aggregator gives one value per projection boundary — `n_periods + 1` values. With `.alias(name).over("scenario_id")` it returns a long `pl.DataFrame`, one row per scenario and period (`scenario_id`, `period`, `name`); without `.over()` it returns an array summed over every row the run folded — on a scenario run, across all scenarios together, so name the scenario axis with `.over()` whenever the plan has more than one scenario.

| Class | Vector reduction |
|---|---|
| `PeriodSum`, `PeriodMean`, `PeriodMin`, `PeriodMax`, `PeriodCount` | Parallel-merge per period |
| `PeriodStd`, `PeriodVariance` | Welford-Chan per period |
| `PeriodMedian` | DDSketch-backed, mergeable |
| `PeriodQuantile(levels=(0.05, 0.5, 0.95))` | DDSketch-backed; `levels` kwarg |
| `PeriodCTE` | Per-period tail conditional expectation |
| `VectorAggregator` | Subclass for custom per-period metrics |

**Same modifier surface as scalar aggregators.** Chain `.alias()` and `.over()` identically:

```python
from gaspatchio.scenarios import PeriodSum, PeriodQuantile

aggregations=(
    PeriodSum("net_cf").alias("net_cf").over("scenario_id"),          # long frame: scenario_id, period, net_cf
    PeriodSum("reserve").alias("reserve"),           # no .over(): every scenario summed together
    PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("net_cf_q"),  # across the run, per level
)
```

**Quantiles per scenario.** `Median`, `CTE`, `QuantileRank`, `PeriodMedian` and `PeriodCTE` take `.over("scenario_id")`. `Quantile.over()` and `PeriodQuantile.over()` are not in 1.0 and are refused where `.over()` is written (`NotImplementedError`, naming the forms that work); use them without `.over()` for the run-wide distribution.

### Helpers (still public, less canonical than `ScenarioRun`)

| Symbol | When To Use |
|---|---|
| `parse_scenario_config(config_list)` | When the recipe arrives as JSON/dict (typical LLM emission) — produces the `shocks` dict for `ScenarioRun` |
| `Table.with_shock(shock, name=…)` | Apply a single shock to a single Table — interactive one-off exploration. Give each copy its own `name=`: without one every copy is `<name>_shocked`, and the second re-registers over the first |
| `Table.from_scenario_files(…)` / `from_scenario_template(…)` | Load scenario-varying assumption tables that come as separate files |

> **Same aggregators, no-scenario path.** The `Sum`, `PeriodSum`, `PeriodQuantile` family
> above also drives `run_aggregated` — the base-case (no-scenario) scale runner. If you
> need portfolio totals or term-structure metrics without stress scenarios, see
> `model-building` → [references/running-at-scale.md](../model-building/references/running-at-scale.md).

---

## Anti-Rationalizations

These are the most common ways agents try to shortcut scenario analysis. Each is wrong.

| Temptation | Correct Response |
|---|---|
| "I'll just modify the model for each scenario" | `model.py` stays unchanged. `plan.run(af, model.main)` runs it as reconciled; shocks name their tables and columns. The model must remain debuggable with `gspio run-model`. |
| "I'll add an `assumptions_override` parameter / a `model_fn` wrapper / a `scenario_id` guard" | Not needed — the plan answers the model's own reads. Each of those is a door the reconciled model never had. |
| "I'll move the valuation rate into a one-row table so I can shock it" | `AdditiveShock(0.01, column="valuation_rate")` shocks the model-point column where it is. |
| "I don't need a report" | Reports with the plan SHA + JSON audit sidecar are required for governance. `plan.run(audit=True)` writes the sidecar; copy `plan.source_sha()` into the report. A scenario analysis without these is incomplete. |
| "The tornado chart is enough" | Different analysis types need different charts. A tornado is meaningless for time-conditional shocks. Match the visualization to what you're showing. |
| "Phase 1 collects the frame and rebuilds it in plain Polars; it ran fine on two scenarios" | Under a plan that rebuild sees every scenario's copy of the book wherever a batch holds more than one scenario, and is refused by name there. Compute book-wide figures on the model points before the run, use `af.join(...)` and assignments then `af.materialize()`, or run `batch_size=1`. |
| "I'll apply shocks in-place and reload" | `ScenarioRun` handles fresh-tables-per-scenario for you (the model's tables are never changed; the run stacks + shocks per batch). Don't write your own apply-shock-then-restore dance. |
| "This is just one quick what-if" | Even a single what-if produces a plan SHA + audit sidecar. The overhead is trivial and the audit trail is always valuable. |
| "I'll bypass `ScenarioRun` and use `with_scenarios()` directly" | `with_scenarios` is the escape hatch — no `source_sha`, no audit sidecar, no YAML round-trip. Use it for interactive sessions only; promote to `ScenarioRun` when the analysis settles. |
| "I'll use the retired `describe_scenarios()` to generate the audit" | That function was removed. `plan.describe()` + `plan.source_sha()` + `result.audit_path` are the audit surface now. |
| "I'll use the retired `sensitivity_analysis()` helper" | Removed too. Sweeps are a Python list comprehension over `ScenarioRun` — see Level 4 above. |

---

## Integration

**Called after:**
- `gaspatchio-model-building` — when the base model is complete and stress testing is needed
- `gaspatchio-model-reconciliation` — when the base case is reconciled and scenario variants are needed

**REQUIRED next step:**
- `gaspatchio-model-review` — after scenarios are complete, review the full model including scenario infrastructure

**Routes to when needed:**
- `gaspatchio-extending` — only for new reusable aggregators (`BaseAggregator` subclasses), NOT for stress/scenario modifications (use shock composables instead)

**Called by:**
- `gaspatchio-model-building` — Integration section routes here when stress tests or sensitivities are needed

---

## Completion Gate

Scenario analysis is complete when ALL of these are true:

- [ ] `model.py` was NOT modified — all scenario logic is in `run_scenarios.py`
- [ ] `run_scenarios.py` executes without errors
- [ ] A `ScenarioRun` plan was built and run via `.run(af, model.main, audit=True)`, with `result.fingerprint("BASE")` equal to the standalone model's
- [ ] `report/report.md` exists and contains:
  - [ ] Model metadata (points, scenarios, runtime, **plan SHA**)
  - [ ] Scenario configuration (`plan.describe()` output or a summary table)
  - [ ] Results summary table with % change from base
  - [ ] At least one embedded chart PNG appropriate to the analysis type
  - [ ] Key findings (auto-generated)
  - [ ] **Audit chain reference**: the plan SHA pinned in prose, and the JSON sidecar path from `result.audit_path`
- [ ] Charts match the analysis type (see Chart Guidance table)

Do not claim the scenario analysis is done until every item is checked.
