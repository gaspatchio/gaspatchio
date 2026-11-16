# How the plan reaches the model

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

## What a plan does not do in 1.0

- **No goal seek inside a plan.** Solve outside it (a bisection on `model.main` over the one policy), then ride the solved value in: `FilteredShock(shock=OverrideShock(value=solved), where={"policy_id": "P1"}, column="premium")`.
- **No yield-curve shock.** A shock names a table or a model-point column, and a `Curve` is neither. Carry the shift as a model-point column the model adds to the curve's rate (`af.spot_shifted = RFR.spot_rate(af.t) + af.curve_shift`) and shock that: `AdditiveShock(delta=0.01, column="curve_shift")`. Or keep the rate itself a model-point column.
