# Scenario API Quick Reference

## Plan & loop

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

## Shock composables

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

## Aggregators (with `.alias(name)` + `.over(by)` / `.of(expr)`)

| Class | Reduction |
|---|---|
| `Sum`, `Mean`, `Min`, `Max`, `Count` | Trivial parallel-merge |
| `ArgMin`, `ArgMax` | Returns the partition key (e.g. `scenario_id`) |
| `Variance`, `Std` | Welford-Chan parallel-merge |
| `Quantile(levels=…)`, `Median` | DDSketch-backed, mergeable |
| `CTE(level=…, direction=…)` | Tail conditional expectation (SCR-shape) |
| `QuantileRank(at=…)` | Inverse — fraction below a threshold |
| `BaseAggregator` | Subclass for custom merge-able metrics |

## Per-Period Aggregators (vector output — term structure)

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

## Helpers (still public, less canonical than `ScenarioRun`)

| Symbol | When To Use |
|---|---|
| `parse_scenario_config(config_list)` | When the recipe arrives as JSON/dict (typical LLM emission) — produces the `shocks` dict for `ScenarioRun` |
| `Table.with_shock(shock, name=…)` | Apply a single shock to a single Table — interactive one-off exploration. Give each copy its own `name=`: without one every copy is `<name>_shocked`, and the second re-registers over the first |
| `Table.from_scenario_files(…)` / `from_scenario_template(…)` | Load scenario-varying assumption tables that come as separate files |

> **Same aggregators, no-scenario path.** The `Sum`, `PeriodSum`, `PeriodQuantile` family
> above also drives `run_aggregated` — the base-case (no-scenario) scale runner. If you
> need portfolio totals or term-structure metrics without stress scenarios, see
> the running-at-scale reference in the `gaspatchio-model-building` skill.
