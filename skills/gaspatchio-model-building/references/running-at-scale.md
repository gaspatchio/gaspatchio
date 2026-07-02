# Running at Portfolio Scale

For small portfolios and interactive development, `gspio run-model` and `af.collect()`
are the right tools — they materialise the full result into memory and let you inspect
every column. At portfolio scale (tens of thousands of policies and above) that approach
OOMs. Gaspatchio provides two memory-bounded scale runners for this case.

---

## Which runner do you need?

| Deliverable | Runner | Result type |
|---|---|---|
| Totals / per-period aggregates / tail metrics (BEL, CTE, VaR) | `run_aggregated` | `AggregatedResult` |
| Full per-policy cashflows (audit trail, downstream join) | `run_to_parquet` | `SpillResult` + parquet shards |
| Small portfolio, interactive development | `af.collect()` / `gspio run-model` | `pl.DataFrame` |

**Rule of thumb:** if your deliverable is a number or a vector — not a policy-by-policy
frame — use `run_aggregated`. The full-frame path (`run_to_parquet`) is for regulatory
audit exports and downstream joins where you genuinely need every policy.

---

## `run_aggregated` — fold to aggregates, never hold the portfolio

`run_aggregated` slices `model_points` into batches, runs `model_fn` on each batch, and
immediately folds the result into per-period accumulators. Peak RSS is approximately one
batch's working set, not the full portfolio.

### Imports

```python
from gaspatchio_core import run_aggregated, AggregatedResult
from gaspatchio_core.scenarios import Sum, PeriodSum, PeriodQuantile, PeriodMedian, PeriodCTE
```

Both are also importable from `gaspatchio_core.scenarios` directly.

### Signature

```python
run_aggregated(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,          # plain Polars DataFrame, NOT an ActuarialFrame
    aggregations: Sequence[Aggregator],  # every aggregator must have .alias(name)
    *,
    batch_size: int | "auto" = "auto",
    align: "calendar" | "duration" | None = None,
) -> AggregatedResult
```

### Realistic example

```python
import polars as pl
from pathlib import Path
from gaspatchio_core import run_aggregated
from gaspatchio_core.scenarios import Sum, PeriodSum, PeriodQuantile

# model_points is a plain pl.DataFrame; model_fn receives an ActuarialFrame per batch
model_points = pl.read_parquet("data/model_points.parquet")

aggregations = [
    Sum("pv_net_cf").alias("pv_net_cf"),             # scalar: one number for the portfolio
    Sum("pv_claims").alias("pv_claims"),
    PeriodSum("net_cf").alias("net_cf"),             # per-period vector (term structure)
    PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("net_cf_q"),  # term-structure quantiles
]

res = run_aggregated(model_fn, model_points, aggregations)  # batch_size="auto"
```

### Reading `AggregatedResult`

`AggregatedResult` is a frozen dataclass. It is **not a DataFrame** — do not call
`.collect()` on it. Read results by attribute.

| Attribute | Type | What it is |
|---|---|---|
| `res.pv_net_cf` | `float` | Scalar aggregate — sum of PV net cashflow across the portfolio |
| `res.net_cf` | `np.ndarray` | Per-period vector — portfolio net cashflow term structure |
| `res.net_cf_q` | `dict[float, np.ndarray]` | `{level: per-period array}` when `PeriodQuantile` with levels (un-partitioned) |
| `res.n_policies` | `int` | Total policies processed |
| `res.n_periods` | `int` | Maximum projection length observed |
| `res.batch_size` | `int` | Resolved batch size (useful when `"auto"`) |
| `res.wall_time_s` | `float` | Wall-clock seconds for the full run |
| `res.peak_rss_mb` | `float \| None` | Peak RSS in MB — reflects ONE batch, not the portfolio |

The alias key (`"pv_net_cf"`) becomes an attribute (`res.pv_net_cf`). This is done via
`__getattr__` — only names present in `res.aggregations` are reachable this way.

```python
# Reading results
print(f"Portfolio PV net cashflow: {res.pv_net_cf:,.0f}")
print(f"Term structure of net CF: {res.net_cf}")
print(f"Run: {res.n_policies} policies, {res.wall_time_s:.1f}s, peak {res.peak_rss_mb:.0f} MB per batch")

# Per-period quantile output is a dict keyed by level; each value is a
# per-period array (term structure), NOT a tidy DataFrame.
net_cf_q = res.net_cf_q              # {0.05: np.ndarray, 0.95: np.ndarray}
q05_term_structure = net_cf_q[0.05]  # one value per projection period
```

### Partitioned aggregation with `.over()`

Use `.over(by)` to split a result by a low-cardinality dimension (product line, fund,
scenario id). Scalar aggregators return a `{*by, alias}` DataFrame; `Period*` aggregators
return a tidy `{*by, period, alias}` DataFrame.

```python
aggregations = [
    Sum("pv_net_cf").alias("pv_net_cf").over("product_line"),   # one row per product_line
    PeriodSum("net_cf").alias("net_cf").over("product_line"),   # tidy: {product_line, period, net_cf}
]
res = run_aggregated(model_fn, model_points, aggregations)

by_product = res.pv_net_cf    # pl.DataFrame: {product_line, pv_net_cf}
by_product_period = res.net_cf  # pl.DataFrame: {product_line, period, net_cf}
```

### Inception-aligned timelines

If your projection uses `from_inception` (per-policy duration origin rather than a shared
calendar grid), period index 0 means "year 1 of this policy's life" — summing across
policies mixes calendar years. Pass `align="duration"` to acknowledge you want
duration-aggregated totals:

```python
res = run_aggregated(model_fn, model_points, aggregations, align="duration")
```

Without this flag, `run_aggregated` raises `ValueError` when it detects an
inception-aligned frame.

---

## `run_to_parquet` — spill full per-policy output to disk

`run_to_parquet` runs the model in batches and writes each batch immediately to
`output_dir/batch_NNNN.parquet`. The full portfolio is never co-resident in memory.
Use this when you need every policy row — for regulatory audit exports, downstream
portfolio joins, or when `run_aggregated` cannot express the required transformation.

### Imports

```python
from gaspatchio_core import run_to_parquet, SpillResult
from pathlib import Path
```

### Signature

```python
run_to_parquet(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,          # plain Polars DataFrame, NOT an ActuarialFrame
    output_dir: Path,                    # directory; batch_NNNN.parquet written here
    *,
    batch_size: int | "auto" = "auto",
    mounts_text: str | None = None,      # injected for tests; leave None in production
) -> SpillResult
```

### Realistic example

```python
import polars as pl
from pathlib import Path
from gaspatchio_core import run_to_parquet

model_points = pl.read_parquet("data/model_points.parquet")
out = Path("output/projections")

spill = run_to_parquet(model_fn, model_points, output_dir=out)

# SpillResult manifest
print(f"{spill.n_batches} parquet files written to {spill.output_dir}")
print(f"{spill.n_policies} policies, {spill.wall_time_s:.1f}s, peak {spill.peak_rss_mb:.0f} MB per batch")

# Read back the full portfolio lazily — no memory spike
full_df = pl.scan_parquet(out / "*.parquet")

# Filter or aggregate downstream without re-running the model
reserve_by_product = (
    full_df
    .select(["policy_id", "product_line", "reserve"])
    .group_by("product_line")
    .agg(pl.col("reserve").list.sum().sum().alias("total_reserve"))
    .collect()
)
```

### `SpillResult` fields

| Field | Type | What it is |
|---|---|---|
| `spill.output_dir` | `Path` | Directory where `batch_NNNN.parquet` files were written |
| `spill.n_policies` | `int` | Total policies written |
| `spill.n_batches` | `int` | Number of parquet files |
| `spill.wall_time_s` | `float` | Wall-clock seconds for the full run |
| `spill.peak_rss_mb` | `float \| None` | Peak RSS per batch in MB |

The parquet files are written atomically (temp → rename) so a partial run never leaves
a corrupt shard. On Linux, `run_to_parquet` rejects RAM-backed filesystems (`tmpfs`,
`ramfs`) — spilling to `/tmp` on a tmpfs re-OOMs the process.

---

## `batch_size="auto"` — how sizing works and where it breaks

Both runners default to `batch_size="auto"`. Auto-sizing:

1. Runs a seed batch (~10% of policies, minimum 1) with RSS measurement.
2. Estimates per-policy memory cost from `max(measured_peak, frame_estimated_size)`.
3. Computes the largest batch that fits the available memory budget.

**Where it breaks — containers and CI.** The sizer reads *host* RAM via `psutil`, not
the cgroup memory limit. In a container or CI runner with a 2 GB memory cap on a 64 GB
host, `batch_size="auto"` will size to ~40 GB worth of policies and OOM.

**Fix: pass an explicit integer in constrained environments.**

```python
# Container / CI: explicit batch_size based on your cgroup limit
res = run_aggregated(model_fn, model_points, aggregations, batch_size=500)
spill = run_to_parquet(model_fn, model_points, out, batch_size=500)
```

A conservative starting point: measure one batch manually with `batch_size=100`,
read `res.peak_rss_mb`, and scale accordingly.

---

## `peak_rss_mb` is per-batch, not portfolio-level

Both result types expose `peak_rss_mb`. This reflects the RSS delta during the highest-RSS
batch — approximately one batch's working set plus model intermediates. It does **not**
represent the peak RSS for the full portfolio run (that would require materialising
everything).

Use `peak_rss_mb` to:
- Verify that one batch fits your memory budget (expected to be much smaller than total
  portfolio RSS).
- Detect memory regressions across model versions by comparing per-batch peaks.

Do not use it to estimate total-run peak — multiply by `ceil(n_policies / batch_size)`
only as a loose upper bound.

---

## Gotchas

### 1. Every aggregator needs `.alias(name)` — no alias raises `ValueError`

```python
# WRONG — run_aggregated raises ValueError: "needs .alias(name)"
aggregations = [Sum("pv_net_cf"), PeriodSum("net_cf")]

# RIGHT
aggregations = [Sum("pv_net_cf").alias("pv_net_cf"), PeriodSum("net_cf").alias("net_cf")]
```

### 2. `AggregatedResult` is not a frame — no `.collect()`

```python
res = run_aggregated(model_fn, mp, aggregations)

# WRONG — AggregatedResult has no .collect() method
df = res.collect()

# RIGHT — read by attribute
pv = res.pv_net_cf          # scalar
cf_vec = res.net_cf         # np.ndarray (Period* aggregator)
```

### 3. `PeriodQuantile.over()` is not supported on `run_aggregated`

`PeriodQuantile` with `.over(by)` has no tidy single-column representation and raises
`NotImplementedError` early. Use one of these alternatives:

```python
# Instead of PeriodQuantile(...).alias(...).over("product"):

# Option A: PeriodMedian or PeriodCTE with .over() (both are supported)
PeriodMedian("net_cf").alias("net_cf_med").over("product_line"),
PeriodCTE("net_cf", level=0.95).alias("net_cf_cte").over("product_line"),

# Option B: PeriodQuantile without .over() (portfolio-level term structure)
PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("net_cf_q"),
```

### 4. `model_points` must be a `pl.DataFrame`, not an `ActuarialFrame`

`run_aggregated` and `run_to_parquet` both take a plain Polars `DataFrame` for
`model_points`. The `model_fn` callable receives an `ActuarialFrame` per batch — that is
handled internally.

```python
# WRONG — model_points is already an ActuarialFrame
af = ActuarialFrame(pl.read_parquet("data/model_points.parquet"))
res = run_aggregated(model_fn, af, aggregations)

# RIGHT — pass the underlying DataFrame
mp = pl.read_parquet("data/model_points.parquet")
res = run_aggregated(model_fn, mp, aggregations)
```

### 5. `Count`, `ArgMin`, `ArgMax` are not supported on `run_aggregated`

These aggregators require a scenario axis (they count or identify scenarios). They raise
`ValueError` when passed to `run_aggregated`. Use `Sum` or `Period*` aggregators instead.

---

## The aggregator catalogue

The full list of scalar and `Period*` aggregators — with signatures, merge semantics, and
usage examples — lives in the `model-scenarios` skill (aggregators are defined there
because they serve both `for_each_scenario` and `run_aggregated`). Load
`skills/gaspatchio-model-scenarios/SKILL.md` for the complete reference.

---

## Pattern: aggregate, then read back selected columns

A common pattern: aggregate the portfolio with `run_aggregated` for the headline numbers,
then use `run_to_parquet` for a filtered subpopulation that needs individual policy data.

```python
import polars as pl
from pathlib import Path
from gaspatchio_core import run_aggregated, run_to_parquet
from gaspatchio_core.scenarios import Sum, PeriodSum

model_points = pl.read_parquet("data/model_points.parquet")

# Step 1: fast aggregate pass for headline numbers
res = run_aggregated(model_fn, model_points, [
    Sum("pv_net_cf").alias("pv_net_cf"),
    PeriodSum("net_cf").alias("net_cf"),
])
print(f"Portfolio BEL: {res.pv_net_cf:,.0f}")

# Step 2: full output only for the high-lapse segment (audit)
high_lapse = model_points.filter(pl.col("lapse_band") == "HIGH")
spill = run_to_parquet(model_fn, high_lapse, Path("output/high_lapse/"))
detail = pl.scan_parquet("output/high_lapse/*.parquet")
```
