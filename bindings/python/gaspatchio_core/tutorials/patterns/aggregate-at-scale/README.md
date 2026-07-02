# Aggregate at Scale

Four runnable scripts that exercise the memory-bounded scale runners
(`run_aggregated`, `run_to_parquet`) and double as a reference vocabulary
for LLMs writing portfolio-scale jobs against this API.

For small portfolios and interactive development, `gspio run-model` and
`af.collect()` materialise the full result into memory — the right tool when
you want to inspect every column. At portfolio scale (tens of thousands of
policies and up) that OOMs. These runners slice `model_points` into batches,
process each batch, and either **fold to aggregates** (`run_aggregated`) or
**spill per-policy output to parquet** (`run_to_parquet`) — peak memory is
approximately one batch's working set, not the whole portfolio.

Each script is self-contained — a small inline synthetic `pl.DataFrame` of
model points, a tiny `model_fn` that projects a monthly net-cashflow term
structure, then the pattern, then an `assert` that the batched result equals a
closed-form / full-frame baseline. A clean run is the success signal: the
batched aggregate equals the full-frame aggregate, exactly.

| File | Pattern | Asserts |
|------|---------|---------|
| `01_run_aggregated.py` | `run_aggregated` folds scalar (`Sum`) + per-period (`PeriodSum`) | Batched fold `res.pv_net_cf` / `res.net_cf` == direct full-frame total, exactly |
| `02_spill_to_parquet.py` | `run_to_parquet` → `pl.scan_parquet` read-back | Read-back row count == `spill.n_policies`; column total == full-run total |
| `03_batching.py` | Same aggregation at `batch_size` ∈ {1, 7, `"auto"`} | All three produce identical `pv_net_cf` and `net_cf` (batch-invariance) |
| `04_over_partition.py` | `Sum(...).over("product_line")` partitioned fold | Per-partition subtotals reconcile to the un-partitioned portfolio total |

## Running

```bash
uv run python \
    bindings/python/gaspatchio_core/tutorials/patterns/aggregate-at-scale/01_run_aggregated.py
```

Swap in `02_spill_to_parquet.py`, `03_batching.py`, or `04_over_partition.py`.
Each script asserts internally; a clean run with the printed reconciliation is
the success signal. `02_spill_to_parquet.py` writes its parquet shards under
its own directory and cleans them up — never under `/tmp`.

## API surface used

- `run_aggregated(model_fn, model_points, aggregations, *, batch_size=...)` — fold a portfolio to aggregates without holding it whole
- `run_to_parquet(model_fn, model_points, output_dir=..., *, batch_size=...)` — spill full per-policy output to parquet shards
- `Sum(col).alias(name)` — scalar fold across the portfolio (`AggregatedResult.<name>` → `float`)
- `PeriodSum(col).alias(name)` — per-period vector fold (`AggregatedResult.<name>` → `np.ndarray`)
- `Sum(col).alias(name).over(by)` — partition a scalar fold by a low-cardinality column (`AggregatedResult.<name>` → `pl.DataFrame`)
- `AggregatedResult` — frozen dataclass; read by attribute (`.pv_net_cf`, `.net_cf`, `.n_policies`, `.n_periods`, `.batch_size`), never `.collect()`
- `SpillResult` — manifest with `.output_dir`, `.n_policies`, `.n_batches`; read parquet back with `pl.scan_parquet(out / "*.parquet")`
- `af.projection.set(valuation_date=..., until=..., until_value=..., frequency=...)` — declare the projection grid inside `model_fn`
- `af.projection.period_dates()` — materialise the per-period date vector as a list column

## Gotchas these scripts encode

- **`model_points` is a plain `pl.DataFrame`, not an `ActuarialFrame`.** The
  runner hands each batch to `model_fn` as an `ActuarialFrame` internally.
- **Every aggregator needs `.alias(name)`.** A missing alias raises
  `ValueError`; the alias is the attribute you read off the result.
- **`AggregatedResult` / `SpillResult` are read by attribute, never
  `.collect()`.** They are frozen dataclasses, not DataFrames.
- **`batch_size="auto"` is cgroup-blind** (sizes from host RAM via `psutil`).
  Pass an explicit integer in containers/CI to avoid OOM — see
  `03_batching.py`.
- **Never spill to `/tmp` on a RAM-backed filesystem.** `run_to_parquet`
  rejects `tmpfs`/`ramfs` on Linux; write shards to real disk.

## Provenance

The batched aggregate-and-stream design lives in the repo under
`ref/41-backend-portability` (GSP-89, shipped in PR #111). `run_aggregated` and
`run_to_parquet` are the user-facing surface of that work: cap peak memory at
roughly one batch regardless of total portfolio scale, while keeping the
aggregate bit-for-bit identical to a full-frame run.

## When to use which runner

- **Deliverable is a number or a vector** (BEL, portfolio PV, term structure,
  tail metric): `run_aggregated`. Start with `01_run_aggregated.py`.
- **Deliverable is the full per-policy frame** (regulatory audit export,
  downstream join, a transformation the aggregators cannot express):
  `run_to_parquet`. See `02_spill_to_parquet.py`.
- **Constrained memory** (container, CI runner, laptop): pin `batch_size` to an
  explicit integer rather than `"auto"`. See `03_batching.py`.
- **Need the answer split by a dimension** (product line, fund, scenario):
  `.over(by)`. See `04_over_partition.py`.
