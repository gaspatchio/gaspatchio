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

## Hard gate

Do NOT claim scenario analysis is complete until a `report/report.md` exists containing charts (embedded PNGs) and the run's audit chain (plan SHA + JSON audit sidecar from `ScenarioRun.run(audit=True)`). Every scenario run produces a report.

---

## CRITICAL RULE: Two-Script Pattern

Scenario analysis uses two scripts with strict separation of concerns:

| Script | Purpose | Modify for scenarios? |
|---|---|---|
| `model.py` | The projection model (`def main(af, assumptions_override=None)`) | **NEVER** |
| `run_scenarios.py` | Scenario orchestration: build a `ScenarioRun`, run it, write the report | **YES** |

**`model.py` stays UNCHANGED.** All scenario logic goes in `run_scenarios.py`. The model exposes `assumptions_override` so a model-function wrapper in `run_scenarios.py` can hand shocked assumption tables back in. The model remains debuggable with `gspio run-model` for any single scenario.

```bash
# Model works standalone — no scenario machinery needed
uv run gspio run-single-policy model.py data.parquet 1

# Scenario analysis is layered on top
uv run python run_scenarios.py
```

---

## The Canonical Path: `ScenarioRun`

A `ScenarioRun` is the typed plan that captures shocks, base tables, aggregations, and an optional master seed as a single hashable value. You build it, run it, and the result carries the plan's SHA + an opt-in JSON audit sidecar — so the same shocks against the same tables always produce the same SHA, and re-running is one Python call.

```python
from gaspatchio_core.scenarios import (
    ScenarioRun,
    MultiplicativeShock,
    Sum,
)

plan = ScenarioRun(
    shocks={
        "BASE": [],
        "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality_select")],
        "LAPSE_DOWN_20": [MultiplicativeShock(factor=0.8, table="lapse_rates")],
    },
    base_tables=BASE_TABLES,
    aggregations=(
        Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
        Sum("pv_claims").alias("pv_claims").over("scenario_id"),
    ),
)
result = plan.run(af, model_fn, audit=True)
print(plan.source_sha())              # 'sha256:…'  — identity of the plan
print(result.aggregations["pv_net_cf"])  # DataFrame: one row per scenario
print(result.audit_path)              # Path to the JSON audit sidecar
```

**Three things make this path the default:**

- **Mergeable aggregators.** `Sum`, `Mean`, `Min`, `Max`, `ArgMin`, `ArgMax`, `Count`, `Variance`, `Std`, `Quantile`, `Median`, `CTE`, `QuantileRank`, plus `BaseAggregator` for custom ones (skewness, TVaR, anything mergeable). Each carries its own column and within-scenario reduction; `.alias(name).over("scenario_id")` produces one row per scenario.
- **Bounded memory.** The plan is driven by `for_each_scenario(batch_size=…)` under the hood — peak RSS is one batch's working set, not the cross-product of policies × scenarios.
- **Identity + audit.** `plan.source_sha()` is a content hash over `(shocks, base_tables, aggregations, master_seed)`. `plan.to_yaml(path)` round-trips flat shock recipes; `plan.run(audit=True)` writes a JSON sidecar capturing the SHA alongside the run for governance.

---

## Scenario Types (Progressive)

Teach and apply these in order. Each level builds on the previous.

### Level 1 — Interest Rate Scenarios (simplest)

The model's discount-rate lookup uses `scenario_id` automatically if the rate table has rows for each scenario. For pure rate scenarios with no table shocks, the low-level `with_scenarios()` cross-join is enough — promote to `ScenarioRun` when the analysis settles.

```python
from gaspatchio_core.scenarios import with_scenarios

af = with_scenarios(af, ["BASE", "UP", "DOWN"])
result = model.main(af).collect()
```

The assumption table `risk_free_rates.parquet` must have BASE/UP/DOWN rows. `with_scenarios()` cross-joins the ActuarialFrame with scenario IDs so every model point is projected under every scenario in one pass.

**Chart**: Grouped bar chart comparing PV metrics across scenarios.

### Level 2 — Parameter Shocks

**Note:** Stresses and shocks belong in this scenario system (`scenarios/shocks` composables), NOT as custom accessors. If someone asks to "add a lapse stress accessor," redirect them here. Use `gaspatchio-extending` only for new reusable calculations, not for stress/scenario modifications.

Declare per-scenario shock recipes as a `dict[str, list[Shock]]` and run the plan:

```python
from gaspatchio_core.scenarios import (
    ScenarioRun,
    MultiplicativeShock,
    AdditiveShock,
    Sum,
)

SHOCKS = {
    "BASE": [],
    "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality_select")],
    "RATES_DOWN_50BP": [AdditiveShock(delta=-0.005, table="risk_free_rates")],
    "LAPSE_DOWN_20": [MultiplicativeShock(factor=0.8, table="lapse_rates")],
}

plan = ScenarioRun(
    shocks=SHOCKS,
    base_tables=BASE_TABLES,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)
result = plan.run(af, model_fn, audit=True)
```

ScenarioRun stacks each base table with a `scenario_id` dimension internally, applies the shock per scenario, and your `model_fn` reads the shocked value via a normal `Table.lookup(scenario_id=af["scenario_id"], …)` call. Fresh assumptions every iteration — shocks never stack.

**Chart**: Tornado chart ranking sensitivities by absolute impact on the headline metric.

### Level 3 — Conditional Shocks

`FilteredShock`, `TimeConditionalShock`, and `PipelineShock` compose targeted stresses:

```python
from gaspatchio_core.scenarios import (
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
            time_column="duration",
        ),
    ],
}
```

| Composable | Meaning |
|---|---|
| `FilteredShock(shock, where=…)` | Shock only applies to rows matching the dimension filter |
| `TimeConditionalShock(shock, when=…)` | Shock applies during a time window (uses a time column on the table) |
| `PipelineShock(shocks=(…))` | Chain transformations — apply in sequence |

The shocks-shape `ScenarioRun` accepts these the same way it accepts `MultiplicativeShock` etc.

**Chart**: Cashflow line chart over projection time showing how conditional shocks diverge from base.

### Level 4 — Sensitivity Sweeps

Systematically vary a single parameter (or two, for a 2D interaction grid). There is no special helper — build the shocks dict with a list comprehension, hand it to `ScenarioRun`:

```python
import itertools
from gaspatchio_core.scenarios import ScenarioRun, MultiplicativeShock, Sum

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
    base_tables=BASE_TABLES,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)
result = plan.run(af, model_fn)
# Pivot the result into a heatmap-ready DataFrame:
heatmap = result.aggregations["pv_net_cf"].with_columns(
    pl.col("scenario_id").str.split("_").list.get(0).str.strip_prefix("M").cast(pl.Float64).alias("mortality_mult"),
    pl.col("scenario_id").str.split("_").list.get(1).str.strip_prefix("L").cast(pl.Float64).alias("lapse_mult"),
).pivot(values="pv_net_cf", index="mortality_mult", on="lapse_mult")
```

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

plan = ScenarioRun(shocks=SHOCKS, base_tables=BASE_TABLES, aggregations=AGGREGATIONS)
print(plan.describe())                 # human-readable summary + SHA
plan.to_yaml(SCRIPT_DIR / "plan.yaml") # flat shocks round-trip through YAML
result = plan.run(af, model_fn, audit=True)
print(result.audit_path)               # JSON audit sidecar
```

`plan.source_sha()` changes the moment the recipe changes; `plan.to_yaml()` writes the recipe to a file for governance archives (flat shocks only — `FilteredShock`/`TimeConditionalShock`/`PipelineShock` aren't YAML-serialisable yet, fall back to plan SHA + JSON audit for those).

**Charts**: Grouped bar chart comparing scenario outcomes + full regulatory-style report with the audit chain.

---

## The `model_fn` Contract

`ScenarioRun.run(af, model_fn, audit=True)` calls `model_fn` once per batch:

```python
def model_fn(af, *, tables, drivers):
    """Bridge the shocked tables back into model.main's assumptions_override shape."""
    overrides = dict(base_assumptions)
    # ScenarioRun stacks each base_tables entry with a scenario_id dimension.
    # Re-wrap typed inputs (MortalityTable, etc.) around the shocked Table.
    if "mortality_select" in tables:
        overrides["mortality"] = MortalityTable(
            table=tables["mortality_select"],
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=SELECT_PERIOD,
        )
    for name in ("mortality_scalars", "lapse_rates", "surrender_charges"):
        if name in tables:
            overrides[name] = tables[name]
    return model.main(af, assumptions_override=overrides)
```

Key points:

- `af` arrives cross-joined with the batch's `scenario_id` column. Inside the model, use `af["scenario_id"]` when looking up against shock-stacked tables.
- `tables` is `dict[str, Table]` — per-batch, scenario-stacked. Pass through to `assumptions_override`; re-wrap any typed wrappers (`MortalityTable`, `Curve`, etc.).
- `drivers` is forwarded per-scenario kwargs (only at `batch_size=1`). Used for `master_seed` injection and any per-scenario scalars.

### The `_maybe_scenario` guard — let the model run standalone too

`ScenarioRun` stacks the base tables it knows about with an extra `scenario_id` dimension; lookups against the stacked table then *require* `scenario_id` as a kwarg. Standalone runs (`gspio run-single-policy model.py …`) call the same model with the *unstacked* table, where passing `scenario_id` is a dimension-mismatch error. To make the model file work in both contexts, gate the kwarg on the table's actual dimensions:

```python
def _maybe_scenario(table, af):
    """Return `{scenario_id: af.scenario_id}` only if the table has been scenario-stacked."""
    raw = table.table if hasattr(table, "table") else table  # unwrap MortalityTable
    if "scenario_id" in raw.dimensions and "scenario_id" in af.columns:
        return {"scenario_id": af["scenario_id"]}
    return {}


# Usage at every lookup site:
af.mort_rate = mortality.at(
    age=af["age"],
    duration=af["duration"],
    **_maybe_scenario(mortality, af),
)
```

This is the pattern the L5 tutorial model uses to stay debuggable under both `gspio run-single-policy` and `ScenarioRun.run`. Without the guard, the model only works inside one of the two paths and breaks in the other.

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
- `result.audit_path` — point at the JSON audit sidecar (`<run_id>.audit.json`) written by `plan.run(audit=True)`. Stick it alongside the report in the release evidence.

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
| Base | Level 1 | Interest rate scenarios with `with_scenarios()` (low-level cross-join) |
| Step 01 | Level 2 | `ScenarioRun` + `MultiplicativeShock` + per-scenario aggregators + audit sidecar + tornado data |
| Step 02 | Level 3 | `FilteredShock`, `TimeConditionalShock`, `PipelineShock` (Solvency II ×1.5 then clip 1.0) |
| Step 03 | Level 4 | 1D mortality sweep + 2D mortality × lapse interaction grid |
| Step 04 | Level 5 | Named regulatory stresses, full audit chain (`source_sha`, `to_yaml`, JSON sidecar) |

Every step has a working `run_scenarios.py`. Start from the step closest to what the user needs and adapt.

---

## gaspatchio Scenario API Quick Reference

### Plan & loop

| Symbol | What It Does |
|---|---|
| `ScenarioRun(shocks, base_tables, aggregations, master_seed=…)` | Typed plan dataclass; hashable; `source_sha()`, `to_yaml()`, `describe()`, `run()` |
| `ScenarioRun.run(af, model_fn, *, batch_size, audit)` | Runs the plan via the bounded-memory loop; returns `ScenarioResult` |
| `ScenarioResult.aggregations[alias]` | Scalar (plain aggregator) or `pl.DataFrame` (`.over(by)` aggregator) per alias |
| `ScenarioResult.audit_path` | Path to the JSON audit sidecar when `run(audit=True)` |
| `for_each_scenario(af, scenarios, model_fn, aggregations)` | Lower-level loop; `ScenarioRun.run` builds on this |
| `with_scenarios(af, ids)` | Low-level cross-join — escape hatch for one-shot exploration |

### Shock composables

| Class | Operation |
|---|---|
| `MultiplicativeShock(factor=…)` | Scale by factor |
| `AdditiveShock(delta=…)` | Add constant |
| `OverrideShock(value=…)` | Replace |
| `ClipShock(min_value=…, max_value=…)` | Cap/floor |
| `FilteredShock(shock=…, where=…)` | Dimension WHERE clause |
| `TimeConditionalShock(shock=…, when=…, time_column=…)` | Time WHEN clause |
| `PipelineShock(shocks=(…))` | Chain operations left-to-right |
| `MaxShock` / `MinShock` | Element-wise max/min of two shocks |
| `RelativeFloorShock` | Floor relative to original |
| `ParameterShock` | Scalar parameter shocks |

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

Every scalar aggregator above has a **`Period*` twin** that returns a **per-period vector** (length `n_periods`) instead of a single number. Use `Period*` when you need the full term structure of a metric across the projection — e.g. net cashflow or reserve *over time* under each stress — not just its present value.

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
from gaspatchio_core.scenarios import PeriodSum, PeriodQuantile

aggregations=(
    PeriodSum("net_cf").alias("net_cf").over("scenario_id"),
    PeriodSum("reserve").alias("reserve"),           # no .over() → portfolio total
    PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("net_cf_q"),
)
```

**Caveat — `PeriodQuantile.over()` (and `PeriodMedian.over()`) is deferred on the scenario axis (#6).** Calling `.over(...)` on a sketch-backed `Period*` raises `NotImplementedError`. Use scalar `Quantile`/`Median` with `.over("scenario_id")` for per-scenario quantiles, or use `PeriodQuantile` without `.over()` to get the portfolio-level term structure.

### Helpers (still public, less canonical than `ScenarioRun`)

| Symbol | When To Use |
|---|---|
| `parse_scenario_config(config_list)` | When the recipe arrives as JSON/dict (typical LLM emission) — produces the `shocks` dict for `ScenarioRun` |
| `Table.with_shock(shock)` | Apply a single shock to a single Table — interactive one-off exploration |
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
| "I'll just modify the model for each scenario" | `model.py` stays unchanged. Use `assumptions_override` via the `model_fn` wrapper. The model must remain debuggable with `gspio run-model`. |
| "I don't need a report" | Reports with the plan SHA + JSON audit sidecar are required for governance. `plan.run(audit=True)` writes the sidecar; copy `plan.source_sha()` into the report. A scenario analysis without these is incomplete. |
| "The tornado chart is enough" | Different analysis types need different charts. A tornado is meaningless for time-conditional shocks. Match the visualization to what you're showing. |
| "I'll apply shocks in-place and reload" | `ScenarioRun` handles fresh-tables-per-scenario for you (`base_tables` are immutable; the loop stacks + shocks per batch). Don't write your own apply-shock-then-restore dance. |
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
- [ ] A `ScenarioRun` plan was built and run via `.run(af, model_fn, audit=True)`
- [ ] `report/report.md` exists and contains:
  - [ ] Model metadata (points, scenarios, runtime, **plan SHA**)
  - [ ] Scenario configuration (`plan.describe()` output or a summary table)
  - [ ] Results summary table with % change from base
  - [ ] At least one embedded chart PNG appropriate to the analysis type
  - [ ] Key findings (auto-generated)
  - [ ] **Audit chain reference**: the plan SHA pinned in prose, and the JSON sidecar path from `result.audit_path`
- [ ] Charts match the analysis type (see Chart Guidance table)

Do not claim the scenario analysis is done until every item is checked.
