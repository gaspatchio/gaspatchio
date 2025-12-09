# Scenario Support: Performance and Scale Guide

**Parent RFC**: [RFC 27: Scenario Support](./27-scenario-support-rfc.md)
**Status**: Draft
**Date**: 2025-12-07

## Overview

This document covers performance considerations, memory management, and scaling patterns for running actuarial models across large scenario sets. It complements the main RFC with practical guidance for production-scale workloads.

## Scale Categories

| Scale | Model Points | Scenarios | Expanded Rows | Typical Use Case |
|-------|--------------|-----------|---------------|------------------|
| **Development** | 8-100 | 3-10 | <1K | Model debugging, reconciliation |
| **Testing** | 100-1K | 100-1K | 100K-1M | Validation, UAT |
| **Production** | 1K-10K | 1K-10K | 1M-100M | Regular reporting |
| **Stress Testing** | 10K-100K | 10K | 100M-1B | Regulatory, capital |

## Why the Design Is Already Fast

The Gaspatchio scenario architecture provides real performance wins over naive approaches. Understanding *why* helps you avoid accidentally undoing these benefits.

### Lazy + Streaming Is Often Faster Than Eager

Using `scan_parquet()` + lazy operations + `collect(engine="streaming")` isn't just about avoiding out-of-memory crashes. The streaming engine is **often faster than the in-memory engine**, even when data fits in RAM, because it:

- Applies more aggressive predicate/projection pushdown
- Keeps less data live at once (better cache utilization)
- Writes in large sequential chunks to disk

For scenario-level aggregations:

```python
scenario_totals = (
    result_lf
    .group_by("scenario_id")
    .agg(pl.col("pv_net_cf").sum())
    .collect(engine="streaming")
)
```

You typically see **lower memory AND faster wall-clock** than `collect()` with the in-memory engine, especially in the 100M+ row band.

### Streaming Sinks Avoid Materialization

Using `sink_parquet()` for large result sets:

- Uses the streaming engine by default
- Writes batches directly to disk - you **never** materialize the full table in Python
- Enables selective reads later (`scan_parquet(".../scenario_id=123/*.parquet")`)

Compared to "materialize then write", this is both more memory-efficient and typically faster.

### Early Aggregation Is The Key Pattern

The RFC pattern of "aggregate to per-scenario metrics first, then compute CTE/VaR on that small table" is critical:

| Data | Size |
|------|------|
| Full results | O(policies × scenarios × periods) |
| Scenario totals | O(scenarios) |

By making scenario-level aggregation a first-class pattern (with streaming), you massively cut what flows into later analysis, plotting, and reporting.

### Polars Expressions Avoid Python Overhead

The design pushes all heavy work into:

- `gs.Table` → Rust/Polars lookups
- `ActuarialFrame` columns → Polars expressions
- No Python row loops in the hot path

This is exactly what Polars performance guides recommend: avoid Python UDFs; keep everything as expressions.

## Memory Estimation

### Formula

```
Memory (bytes) ≈ rows × columns × 8 × overhead_factor

Where:
- rows = model_points × scenarios × projection_periods (if materialized)
- columns = number of output columns
- 8 = bytes per float64
- overhead_factor ≈ 1.5-2x for Polars internal structures
```

### Worked Examples

**Small (fits in memory):**
```
1,000 policies × 10,000 scenarios × 1 row/policy = 10M rows
10M rows × 50 columns × 8 bytes × 1.5 = 6 GB
```

**Large (needs streaming):**
```
10,000 policies × 10,000 scenarios × 1 row/policy = 100M rows
100M rows × 50 columns × 8 bytes × 1.5 = 60 GB
```

**With projection arrays (list columns):**
```
If each row has 82-period projection arrays:
10M rows × 10 list columns × 82 periods × 8 bytes × 1.5 = 98 GB
```

## Polars Streaming Mode

Polars has a streaming execution engine that processes data in batches automatically, keeping memory usage bounded regardless of total data size.

### Make Streaming the Default

Rather than remembering `engine="streaming"` everywhere, set it globally at the start of your runner:

```python
import polars as pl

# Make streaming the default for all collect() calls
pl.Config.set_engine_affinity("streaming")
```

Then:
- `lf.collect()` → uses streaming where possible
- For unsupported operations, Polars transparently falls back to in-memory for that subgraph
- Users accidentally get the faster/safer path

### How It Works

1. Operations are built as a lazy computation graph
2. `collect()` (with streaming affinity) executes in memory-bounded batches
3. Polars automatically determines optimal batch sizes
4. Results can be written incrementally to disk via `sink_*()`

### Enabling Streaming in Gaspatchio

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame
import polars as pl

# Set streaming as default engine
pl.Config.set_engine_affinity("streaming")

# === 1. Use lazy mode for scenario expansion ===
af = ActuarialFrame(pl.scan_parquet("model_points.parquet"))  # LazyFrame
af = gs.with_scenarios(af, scenario_ids)  # Returns lazy ActuarialFrame

# === 2. Run model (operations stay lazy) ===
result = main(af)

# === 3. Collection options ===
# Option A: Collect to memory (streaming engine used automatically)
df = result.collect()

# Option B: Write directly to disk without full materialization
result.sink_parquet("results/scenario_results.parquet")

# Option C: Write partitioned by scenario
result.sink_parquet(
    "results/by_scenario/",
    partition_by=["scenario_id"],
)
```

### Streaming-Compatible Operations

Most Polars operations work in streaming mode:

| Operation | Streaming? | Notes |
|-----------|------------|-------|
| `select`, `with_columns` | Yes | |
| `filter` | Yes | |
| `join` (left, inner) | Yes | If right side fits in memory |
| `group_by.agg` | Yes | |
| `sort` | Partial | Requires all data for global sort |
| `head`, `tail` | Partial | `head` works, `tail` needs all data |
| `explode` | Partial | Can break streaming on huge frames |

### Avoiding Streaming Footguns

One stray `sort` or `explode` can turn your nice streaming pipeline into a huge in-memory operation.

**Best practices:**

1. **Aggregate before sorting** - Don't sort 100M rows; aggregate to 10K scenario rows first, then sort
2. **Use `explain()` to verify streaming** - Check which parts are non-streaming:
   ```python
   print(result_lf.explain(streaming=True))
   ```
3. **Avoid global operations on large frames** - `sort`, `tail`, `sample` need all data

### Table Lookups in Streaming Mode

For streaming to work, assumption tables should fit in memory (they usually do):

```python
# Assumption tables are typically small - load eagerly
mortality_table = gs.Table(
    source=pl.read_parquet("mortality.parquet"),  # Eager load
    dimensions={"age": "age", "sex": "sex"},
    value="qx",
)

# Scenario-varying tables may be larger but still manageable
# 10K scenarios × 150 years × 6 funds = 9M rows ≈ 200MB
returns_table = gs.Table(
    source=pl.read_parquet("fund_returns_10k.parquet"),
    dimensions={"scenario_id": "scenario_id", "t": "t", "fund_index": "fund_index"},
    value="inv_return_mth",
)

# Model points stream through, joining against in-memory tables
```

### When Streaming Isn't Enough

Streaming helps with **row-wise** scale but not when:

1. **Assumption tables are huge** (10K scenarios × complex dimensions > 1GB)
2. **Operations require global state** (percentiles, global sorts)
3. **Memory is very constrained** (< 4GB available)

In these cases, use explicit batching (see below).

## Scenario ID Encoding

**This is a significant performance lever.**

String scenario IDs (`"SCEN_00001"`) are:
- Larger in memory
- Slower to `group_by`/`join` than integers or categoricals

Polars recently overhauled `Categorical` specifically to work better with the streaming engine.

### Recommended: Integer or Categorical IDs

```python
# Option A: Integer IDs (best performance)
scenario_ids = list(range(1, 10001))  # UInt32/Int32
af = gs.with_scenarios(af, scenario_ids)

# Option B: Categorical strings (if you need readable IDs)
scenario_ids = [f"SCEN_{i:05d}" for i in range(1, 10001)]
af = gs.with_scenarios(af, scenario_ids, categorical=True)
# Internally stored as dictionary-encoded integers
```

### Why This Matters

| ID Type | Memory (10K IDs × 100M rows) | Join Speed |
|---------|------------------------------|------------|
| String (`"SCEN_00001"`) | ~1.2 GB | Slower |
| Categorical | ~400 MB | Fast |
| UInt32 | ~400 MB | Fastest |

For scenario-level aggregations and CTE/VaR calculations, this directly speeds up:
- `group_by("scenario_id")`
- Joins against scenario-varying assumption tables

### Pattern: Internal Integer, External Label

If you need human-readable scenario names:

```python
# Keep integer IDs internally for performance
af = gs.with_scenarios(af, list(range(1, 10001)))

# Maintain a separate label mapping for reporting
scenario_labels = pl.DataFrame({
    "scenario_id": range(1, 10001),
    "scenario_label": [f"SCEN_{i:05d}" for i in range(1, 10001)],
})

# Join labels only for final output
final_report = scenario_totals.join(scenario_labels, on="scenario_id")
```

## Writing Results

### Strategy by Output Size

| Output Type | Rows (10K×10K) | Strategy |
|-------------|----------------|----------|
| Scenario aggregates | 10K | Single file, in-memory |
| Policy-scenario | 100M | Streaming sink, partitioned |
| Full projections | 8B+ | Batch + partition, or skip |

### Recommended: Partitioned Parquet

```python
# Write partitioned by scenario - efficient for queries like
# "show me results for scenario 5432"
result.sink_parquet(
    "results/scenario_output/",
    partition_by=["scenario_id"],
)

# Read back specific scenarios efficiently
scenario_5432 = pl.scan_parquet("results/scenario_output/scenario_id=5432/*.parquet")
```

### Two-Stage Pattern

For risk metric calculation, use a two-stage approach:

```python
# Stage 1: Streaming aggregation to scenario-level (always fits in memory)
scenario_totals = (
    result
    .group_by("scenario_id")
    .agg([
        pl.col("pv_net_cf").sum().alias("total_pv"),
        pl.col("pv_claims").sum().alias("total_claims"),
    ])
    .collect()  # Streaming engine used automatically with affinity set
)

# Stage 2: Risk metrics on small aggregated data
scenario_totals.write_parquet("results/scenario_totals.parquet")

reserves = scenario_totals.sort("total_pv", descending=True)["total_pv"]
cte_98 = reserves.head(int(0.02 * len(reserves))).mean()
```

## Automatic Strategy Selection

Rather than making users manually choose streaming vs batching, the framework can estimate sizes and choose automatically.

### Size Estimation

At the start of a run, estimate:
- Model points size
- Scenario-expanded assumption table sizes
- Expected result size

```python
def estimate_run_size(
    model_points_path: str,
    scenario_count: int,
    assumption_tables: list[gs.Table],
) -> dict:
    """Estimate memory requirements for a scenario run."""
    mp_size = Path(model_points_path).stat().st_size
    mp_rows = pl.scan_parquet(model_points_path).select(pl.len()).collect().item()

    expanded_rows = mp_rows * scenario_count

    # Rough estimate: 50 columns × 8 bytes × 1.5 overhead
    result_estimate_gb = expanded_rows * 50 * 8 * 1.5 / 1e9

    table_sizes_gb = sum(
        t.source.estimated_size() / 1e9
        for t in assumption_tables
    )

    return {
        "expanded_rows": expanded_rows,
        "result_estimate_gb": result_estimate_gb,
        "table_sizes_gb": table_sizes_gb,
        "recommended_strategy": (
            "streaming" if result_estimate_gb < 50 and table_sizes_gb < 1
            else "batching"
        ),
    }
```

### Strategy Selection

| Estimate | Strategy |
|----------|----------|
| Result < 50GB, tables < 1GB | **Streaming** - single shot |
| Result > 50GB or tables > 1GB | **Batching** - 1000-scenario chunks with streaming inside |
| Extreme scale (100K+ scenarios) | **Batching + period streaming** - for path-dependent products |

## Explicit Batching (Fallback)

When Polars streaming isn't sufficient, use explicit scenario batching.

### `gs.batch_scenarios()` Helper

```python
def batch_scenarios(
    scenario_ids: list[str | int],
    batch_size: int = 1000,
) -> Iterator[list[str | int]]:
    """
    Yield scenario IDs in batches.

    Args:
        scenario_ids: Full list of scenario IDs
        batch_size: Number of scenarios per batch

    Yields:
        Lists of scenario IDs, each of length <= batch_size
    """
    for i in range(0, len(scenario_ids), batch_size):
        yield scenario_ids[i:i + batch_size]
```

### Batched Execution Pattern

```python
import gaspatchio as gs
from gaspatchio_core import ActuarialFrame
import polars as pl
from pathlib import Path

pl.Config.set_engine_affinity("streaming")

scenario_ids = list(range(1, 10001))  # Integer IDs for performance
output_dir = Path("results/batches")
output_dir.mkdir(exist_ok=True)

# Process in batches
batch_results = []
for batch_num, batch_ids in enumerate(gs.batch_scenarios(scenario_ids, batch_size=1000)):
    print(f"Processing batch {batch_num + 1}: scenarios {batch_ids[0]} to {batch_ids[-1]}")

    # Load and expand for this batch only
    af = ActuarialFrame(pl.scan_parquet("model_points.parquet"))
    af = gs.with_scenarios(af, batch_ids)

    # Run model
    result = main(af)

    # Aggregate this batch (streaming inside batch)
    batch_agg = result.group_by("scenario_id").agg([
        pl.col("pv_net_cf").sum().alias("total_pv"),
        pl.col("pv_claims").sum().alias("total_claims"),
        pl.col("pv_premiums").sum().alias("total_premiums"),
    ]).collect()

    # Write incrementally (recovery point)
    batch_agg.write_parquet(output_dir / f"batch_{batch_num:04d}.parquet")
    batch_results.append(batch_agg)

# Combine all batches
all_scenarios = pl.concat(batch_results)
all_scenarios.write_parquet("results/all_scenario_totals.parquet")

# Calculate risk metrics
reserves = all_scenarios.sort("total_pv", descending=True)["total_pv"].to_numpy()
cte_98 = reserves[:max(1, int(len(reserves) * 0.02))].mean()
```

### When to Use Batching vs Streaming

| Situation | Use Streaming | Use Batching |
|-----------|---------------|--------------|
| Standard workloads | Yes | |
| Assumption tables > 1GB | | Yes |
| Need recovery/restart points | | Yes |
| Memory < 8GB | | Yes |
| Debugging memory issues | | Yes |
| Maximum performance | Yes | |

## Table Micro-Optimizations

For inner-loop performance in hot paths:

### Sort Tables by Lookup Dimensions

Ensure scenario-varying tables are sorted by `(scenario_id, t, other_dims)` for cache-friendly joins:

```python
# When creating tables, sort for locality
returns_df = pl.read_parquet("fund_returns.parquet").sort(
    "scenario_id", "t", "fund_index"
)
returns_table = gs.Table(
    source=returns_df,
    dimensions={"scenario_id": "scenario_id", "t": "t", "fund_index": "fund_index"},
    value="inv_return_mth",
)
```

### Pre-slice for Stepped Projection

For the stepped projection engine, pre-slice tables per-batch rather than per-policy:

```python
# In stepped engine, slice once per period for the batch
period_returns = returns_table.filter(
    pl.col("scenario_id").is_in(batch_scenario_ids) &
    (pl.col("t") == current_period)
)
# Then lookup against this smaller slice
```

## GPU Acceleration (Future)

The Gaspatchio design is well-aligned for Polars GPU acceleration:

- Heavy columnar transforms
- Group-by aggregations at scale
- Parquet in/out
- Minimal Python UDFs

The RAPIDS + Polars GPU engine (as of late 2025) provides:
- Up to **13× faster** than CPU for compute-bound queries
- **Streaming execution on GPU** for larger-than-VRAM datasets

### Future API

```python
# Potential future flag
result = main(af)
scenario_totals = (
    result
    .group_by("scenario_id")
    .agg(pl.col("pv_net_cf").sum())
    .collect(engine="gpu")  # GPU acceleration for pure-Polars segments
)
```

For users with A10/RTX-class GPUs, scenario aggregations could drop from minutes to seconds.

**Note:** Custom Rust plugins would need GPU-compatible implementations. Start with CPU streaming; add GPU path for pure-Polars segments when beneficial.

## Approximate Risk Metrics (Future)

For 10K scenarios, exact CTE/VaR is trivial (10K rows is tiny). But for 100K+ scenarios:

### Streaming Quantile Sketches

Use approximate algorithms (t-digest, KLL) that don't require all scenario losses in memory:

```python
# Future API - streaming approximate percentile
from gaspatchio.stats import StreamingQuantile

quantile = StreamingQuantile(q=0.98)
for batch_ids in gs.batch_scenarios(scenario_ids, 10000):
    batch_totals = run_batch(batch_ids)
    quantile.update(batch_totals["total_pv"])

cte_98_approx = quantile.result()  # Approximate, but memory-bounded
```

This enables CTE/VaR calculation even when scenario-level results don't fit in memory.

## Performance Benchmarks

**Last Updated**: 2025-12-08
**Test System**: macOS Darwin, 16 GB RAM, Apple Silicon
**Model**: GMXB (applied_life) with 180-month projections, dynamic lapse, guarantees

### Actual Benchmark Results

#### Full Model (GMXB with Stochastic Returns)

| Policies | Scenarios | Rows | Memory (Peak) | Time | Notes |
|----------|-----------|------|---------------|------|-------|
| 8 | 10 | 80 | 92.8 MiB | ~0.8s | Baseline |
| 8 | 100 | 800 | 153.8 MiB | ~1.5s | |
| 1,000 | 10 | 10,000 | 745.7 MiB | ~11.5s | |
| 1,000 | 50 | 50,000 | 2.8 GiB | ~57.5s | |
| 1,000 | 100 | 100,000 | **5.7 GiB** | ~114s | ~58 KiB/row at scale |

#### Memory Breakdown (1k × 10 = 10k rows)

| Component | Memory |
|-----------|--------|
| Polars collect() | 368.8 MiB |
| Assumptions loading | 64.5 MiB |
| Other overhead | ~312 MiB |
| **Total Peak** | **745.7 MiB** |

#### Scenario Expansion Only (No Model Execution)

| Policies | Scenarios | Rows | Memory | Time |
|----------|-----------|------|--------|------|
| 8 | 100 | 800 | 10.8 KiB | 256 µs |
| 1,000 | 100 | 100,000 | ~540 µs | 540 µs |
| 10,000 | 100 | 1,000,000 | 170.3 MiB | 7.5 ms |

**Key insight**: Scenario expansion itself is extremely fast (microseconds). The memory consumption comes from model execution with list columns.

#### Streaming vs Non-Streaming (Expansion Only)

| Mode | Memory (10k × 100) | Notes |
|------|-------------------|-------|
| Non-streaming | 136.2 MiB | Default, simpler |
| Streaming | 212.4 MiB | Higher overhead for simple ops |

**Finding**: Streaming has overhead and mainly helps with very large datasets that don't fit in RAM. For the GMXB model, streaming provides no benefit because cumulative operations (`cum_prod`, `previous_period`) require full history.

#### Batched vs Unbatched (1k x 100 scenarios)

| Approach | Peak Memory | Time | Reduction |
|----------|-------------|------|-----------|
| Unbatched (all 100 at once) | **5.6 GiB** | ~114s | baseline |
| Batched (10 batches of 10) | **636.6 MiB** | ~223s | **8.8x less memory** |

**Key insight**: The `batch_scenarios()` API reduces peak memory by nearly 9x at the cost of ~2x runtime. This is essential for running large scenario counts on constrained hardware.

**How batching works**:
```
100 scenarios, batch_size=10
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  batch_scenarios([1..100], batch_size=10)               │
│  yields: [1-10], [11-20], [21-30], ... [91-100]         │
└─────────────────────────────────────────────────────────┘
         │
         ▼ (10 iterations)
┌─────────────────────────────────────────────────────────┐
│  For each batch:                                        │
│    1. Expand: 1k policies x 10 scenarios = 10k rows     │
│    2. Run model -> 10k rows with all columns            │
│    3. Aggregate: group_by("scenario_id").sum()          │
│       -> 10 rows (one per scenario)                     │
│    4. Append to batch_aggregates list                   │
│    5. GC clears the 10k-row intermediate                │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  pl.concat(batch_aggregates)                            │
│  -> 100 rows total (10 batches x 10 rows each)          │
└─────────────────────────────────────────────────────────┘
```

#### Sink-then-Stream Pattern (1k x 100 scenarios)

An alternative to batch-aggregate is **sink-then-stream**: write full results to files, then aggregate later using the streaming engine.

| Approach | Peak Memory | Time | Flexibility |
|----------|-------------|------|-------------|
| Unbatched | 5.6 GiB | ~114s | Full data in memory |
| Batch-aggregate | 636.6 MiB | ~223s | Must choose aggregation upfront |
| **Sink-then-stream** | **1.2 GiB** | **~118s** | **Any aggregation later** |

**Why sink-then-stream works**:
- Phase 1 (model run): Same memory constraint as batch-aggregate (~300 MiB per batch)
- Phase 2 (aggregation): Streaming works because `group_by/sum/mean` have no cumulative operations
- Data persists on disk for ad-hoc analysis

**Pattern**:
```python
from gaspatchio_core.scenarios import batch_scenarios, with_scenarios

# Phase 1: Sink full results to parquet
for batch_num, batch_ids in enumerate(batch_scenarios(scenario_ids, batch_size=10)):
    af = ActuarialFrame(model_points)
    af = with_scenarios(af, batch_ids)
    result = run_model(af).collect()
    result.write_parquet(f"results/batch_{batch_num:04d}.parquet")
    del result  # Free memory

# Phase 2: Stream-aggregate from files (any aggregation you want!)
totals = (
    pl.scan_parquet("results/*.parquet")
    .group_by("scenario_id")
    .agg(pl.col("pv_net_cf").sum())
    .collect(engine="streaming")  # Works! No cum_prod in aggregation
)

# Run different aggregations without re-running the model
means = pl.scan_parquet("results/*.parquet").group_by("scenario_id").agg(
    pl.col("pv_net_cf").mean()
).collect(engine="streaming")

percentiles = pl.scan_parquet("results/*.parquet").select(
    pl.col("pv_net_cf").quantile(0.95)
).collect(engine="streaming")
```

**When to use each**:

| Pattern | Best For |
|---------|----------|
| **Unbatched** | Small runs (<4 GiB), one-off analysis |
| **Batch-aggregate** | Memory-constrained, known aggregation upfront |
| **Sink-then-stream** | Exploratory analysis, multiple reports, audit trail |

### Scaling Estimates

Based on measured benchmarks, extrapolated estimates:

| Configuration | Rows | Est. Memory | Est. Time | Strategy |
|--------------|------|-------------|-----------|----------|
| 1k × 100 | 100k | 5.7 GiB | ~2 min | Single-shot on 8+ GB RAM |
| 1k × 500 | 500k | ~28 GiB | ~10 min | **Batching required** |
| 1k × 1,000 | 1M | ~57 GiB | ~19 min | **Batching required** |
| 10k × 100 | 1M | ~57 GiB | ~19 min | **Batching required** |
| 10k × 1,000 | 10M | ~570 GiB | ~3.2 hrs | **Heavy batching** |
| 100k × 10k | **1B** | **~58 TB** | ~13.2 days | **See below** |

### Extreme Scale: 100K Model Points × 10K Scenarios

For regulatory stress testing at the extreme end (1 billion rows):

#### Why ~58 TB Peak Memory?

At scale, our benchmarks show memory stabilizes at **~58 KiB per row**:

| Rows | Measured Memory | Per-Row |
|------|-----------------|---------|
| 10k | 745.7 MiB | 74.6 KiB |
| 50k | 2.8 GiB | 57.3 KiB |
| 100k | 5.7 GiB | 58.4 KiB |

Extrapolating: `1,000,000,000 rows × 58 KiB = 58 TB`

This is **peak working memory** during model execution, not final result size. The model creates 180 months of intermediate columns during projection.

#### How to Actually Run 100K × 10K

**Option 1: Two-level batching (64 GB machine)**

With 64 GB RAM, you can run ~1M rows per batch:
- 1k policies × 1k scenarios = 1M rows per batch
- Total batches: 100 × 10 = **1,000 batches**
- Each batch: ~5.7 GiB, ~2 minutes
- Total wall time: ~33 hours (serial)
- With 8 parallel workers: ~4 hours

```python
from itertools import product

policy_batches = list(batch_sequence(range(100_000), batch_size=1_000))  # 100 batches
scenario_batches = list(batch_sequence(range(10_000), batch_size=1_000))  # 10 batches

for p_batch, s_batch in product(policy_batches, scenario_batches):
    mp_subset = model_points.filter(pl.col("policy_id").is_in(p_batch))
    af = ActuarialFrame(mp_subset)
    af = gs.with_scenarios(af, s_batch)
    result = main(af)
    # Aggregate and write incrementally
```

**Option 2: Cloud burst (recommended)**

For one-off regulatory runs, burst to cloud:

| Cloud Instance | RAM | Cost/hr | Batch Size | Batches | Est. Time | Est. Cost |
|----------------|-----|---------|------------|---------|-----------|-----------|
| AWS r6i.8xlarge | 256 GB | ~$2 | 4M rows | 250 | ~8 hrs | ~$16 |
| AWS r6i.16xlarge | 512 GB | ~$4 | 8M rows | 125 | ~4 hrs | ~$16 |
| AWS r6i.metal | 1 TB | ~$8 | 16M rows | 63 | ~2.1 hrs | ~$17 |

**Option 3: Distributed (Polars on Spark/Ray)**

For regular 100K × 10K runs, consider:
- Polars on Ray or Spark for distributed execution
- Each worker handles a subset of policies
- Horizontal scaling up to cluster RAM

### Streaming Limitations

The GMXB model **cannot stream** due to these operations:
```python
af.cumulative_growth_factor = af.combined_growth_factor.cum_prod()  # Line 427
af.cumulative_survival = af.survival_factor.cum_prod()              # Line 491
af.survival_prob = af.cumulative_survival.projection.previous_period()  # Line 494
```

These require full history and force Polars to fall back to in-memory execution.

### Running Benchmarks

```bash
# All benchmarks with memory profiling
uv run pytest tests/scenarios/test_scenario_benchmarks.py -m benchmark --memray

# Specific scale
uv run pytest tests/scenarios/test_scenario_benchmarks.py -m benchmark --memray -k "1k_x_10"

# Streaming comparison
uv run pytest tests/scenarios/test_scenario_benchmarks.py -m benchmark --memray -k "TestStreamingComparison"
```

Factors affecting performance:
- Model complexity (number of calculations per row)
- Projection length (82 vs 360 periods)
- Number of list columns (array operations)
- Disk I/O speed (for streaming sink)
- Scenario ID encoding (integer vs string)

## Memory Profiling

### Quick Memory Check

```python
import polars as pl

# Check DataFrame memory usage
df = result.collect()
print(f"DataFrame memory: {df.estimated_size() / 1e9:.2f} GB")

# Check individual columns
for col in df.columns:
    size_mb = df.select(col).estimated_size() / 1e6
    print(f"  {col}: {size_mb:.1f} MB")
```

### Verify Streaming Plan

```python
# Check which parts of your query are streaming-compatible
print(result_lf.explain(streaming=True))
```

### Memory Budget Planning

```python
import psutil

available_gb = psutil.virtual_memory().available / 1e9
print(f"Available memory: {available_gb:.1f} GB")

# Rule of thumb: use at most 70% of available memory
max_working_memory = available_gb * 0.7

# Estimate if streaming will work
estimated_tables_gb = 0.5  # Assumption tables
estimated_working_gb = 2.0  # Polars working memory
buffer_gb = 1.0

if estimated_tables_gb + estimated_working_gb + buffer_gb < max_working_memory:
    print("Streaming should work")
else:
    print("Consider batching")
```

## Recommendations Summary

1. **Set streaming affinity globally** - `pl.Config.set_engine_affinity("streaming")`
2. **Use lazy mode** - `pl.scan_parquet()` instead of `pl.read_parquet()`
3. **Use integer scenario IDs** - Or categorical if you need string labels
4. **Aggregate early** - Reduce to scenario-level before collecting
5. **Partition outputs** - Use `partition_by=["scenario_id"]` for large writes
6. **Avoid streaming footguns** - No global `sort`/`tail` on large frames
7. **Batch if needed** - Fall back to explicit batching for edge cases
8. **Profile with `explain()`** - Verify your query plan is streaming-compatible

## Future Enhancements

- [ ] Automatic memory estimation and strategy selection before run
- [ ] Progress callbacks for long-running batches
- [ ] GPU engine support for pure-Polars segments
- [ ] Approximate percentile algorithms for streaming CTE/VaR
- [ ] Distributed execution (Dask/Ray integration)
- [ ] Pre-sorted table optimization in `gs.Table`

## References

- [Polars Streaming Engine](https://docs.pola.rs/user-guide/concepts/streaming/) - Official documentation
- [Polars Dec 2025 Update](https://pola.rs/posts/polars-in-aggregate-dec25/) - Streaming engine and categorical improvements
- [Polars GPU Engine](https://pola.rs/posts/gpu-engine-release/) - GPU acceleration with NVIDIA RAPIDS
