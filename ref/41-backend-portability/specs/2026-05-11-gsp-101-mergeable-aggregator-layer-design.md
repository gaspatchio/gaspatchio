# GSP-101 — Mergeable aggregator layer redesign

**Status:** Design (in review)
**Base:** GSP-100 ScenarioRun + for_each_scenario (current branch `gsp-100-scenariorun-bounded-memory`).
**Branch:** same; this spec ships on top of the GSP-100 work.
**Breaking change:** yes — v0.2 of the scenarios surface. v0.1 plans do not load.

---

## 1. Problem

GSP-100 shipped a working scenario loop and 15 aggregators, but **dog-fooding surfaced a load-bearing architectural error in the metric/aggregator layer**:

- `GroupedAgg(by="lob", metric=ArgMax())` produces silently wrong answers when used inside `MultiAgg`. The loop pre-reduces to one row per scenario (`group_by("scenario_id").agg(per_scenario)`) *before* any aggregator runs, which collapses the LOB dimension. The "fix" landed in `9cdce83` removed the column-drop but the architecture cannot recover the lost granularity. Stress-test Agent 2 confirmed empirically: a 4-LOB run returned `{"endowment": 51M}` instead of `{"term": 12.97M, "annuity": 12.66M, "endowment": 13.24M, "wholelife": 12.39M}`.
- `parse_aggregations` constructs nested aggregators via flat `cls(**spec)`, so YAML round-trip silently breaks for any composed aggregator (`GroupedAgg`, `MultiAgg`).
- `MultiAgg.update`'s helpful "missing `by` column" message is dead code — Polars raises a bare `ColumnNotFoundError` first.

The root cause is not a bug. **`GroupedAgg`-as-aggregator is the wrong abstraction.** Partitioning is a property of the within-scenario reduction, not the across-scenario fold. The two concerns cannot be cleanly separated under "one shared `per_scenario` reduction used by every aggregator."

## 2. Goals & non-goals

### Goals

1. **A principled aggregator contract** where partitioning is orthogonal to the fold (Beam's `CombineFn` + `CombinePerKey` separation).
2. **Mergeable everything** — every aggregator exposes associative + commutative `merge`, pinned by a Hypothesis property test. Bit-exact reproducibility across batch sizes, processes, and partition shapes.
3. **One coherent public surface** — variadic aggregator list with `.over()` partitioning, `.alias()` naming, and a `.of()` polars escape hatch for the long tail.
4. **Multi-column partitioning** — `.over(("region", "peril"))` works at the same cost as `.over("lob")`.
5. **Audit sidecar** — opt-in `<run_id>.audit.json` co-located with output, completing the `source_sha`-based governance story.
6. **Honest CTE/Quantile** — replace the materialised-buffer aggregators with DDSketch (bit-exact mergeable; bounded-relative-error).
7. **API surface is backend-blind in shape**; implementation is polars-bound today. The seam is in place for the rollforward backend-evolution story to extend across the pipeline later.

### Non-goals (explicitly deferred)

- **Actuarial aliases** (`AAL = Mean`, `VaR = Quantile`, `TVaR = CTE`) — follow-on PR; trivial additions over the primitives.
- **Backwards compatibility shims** for v0.1 names — clean break. v0.1 has never been released; the only users are our own tutorials and tests.
- **Cross-backend implementations** (pandas / DuckDB / Ibis) — out of scope until rollforward's backend story matures.
- **GROUPING SETS as a separate API** — research (S2) confirmed the actuarial idiom is N named flat aggregations, not SQL cubes with NULL super-rows. `.over(tuple)` covers the real need.
- **GPG signatures / CBOR variant** of the audit sidecar — minimal-viable now; gold-plating later if asked.
- **Polars `streaming_engine` UDAF integration** — not yet a stable Polars API; revisit when Polars #18349 lands.

## 3. Design decisions

| # | Decision | Source |
|---|---|---|
| 1 | Aggregator contract is Beam-style 5-tuple (`within_expr`, `create_accumulator`, `add_input`, `merge_accumulators`, `extract_output`). | R1 (Apache Beam) |
| 2 | Partitioning is a driver-level wrapper (`.over(...)` modifier compiles to `_Partitioned(by=..., agg=...)`); the aggregator itself is partition-blind. | R1 |
| 3 | Public API is variadic with alias-on-aggregator: `ScenarioRun(aggregations=(Sum("loss").alias("total"), ...))`. | R2 (Polars/dplyr/SQL) |
| 4 | The within-scenario reduction is **named-string-driven** for backend-blindness: `Sum("loss", within="sum")`. Set `{sum, mean, max, min, count, first, last}` covers 99% of cases. | R2 + backend-blindness review |
| 5 | `.of(pl_expr)` is the polars-bound escape hatch for the rare long-tail (e.g., `pl.col("a") * pl.col("b")`); explicitly marked as backend-specific. | R2 + backend-blindness review |
| 6 | Output shape: scalar metric → scalar; partitioned metric → DataFrame with partition columns + value column. Single-key `over("lob")` and 1-tuple `over(("lob",))` normalise to identical output. | R2 |
| 7 | Mergeable CTE/Quantile/Median/QuantileRank backed by **DDSketch**, not t-digest. DDSketch merge is integer bucket addition — bit-exact deterministic by construction. | S1 |
| 8 | DDSketch signed-value handling: paired positive/negative sub-sketches, wrapped in a frozen dataclass facade. | S1 |
| 9 | Multi-column partitioning via `.over(tuple)`; multi-key partitions appear as separate named columns in the output DataFrame. | S2 |
| 10 | Audit sidecar: opt-in via `audit: bool \| Path = False`; `True` writes `./gaspatchio_audit/<run_id>.audit.json`. JSON only. Fields: `{schema_version, source_sha, plan_canonical_form, run_metadata, aggregator_outputs, input_data_fingerprint}`. | S3 |
| 11 | Plugin registry keeps `@scenario_aggregator("name")` decorator; registered classes must implement the 5-tuple contract. Existing validation (kind-matches-name check) preserved. | continuation |
| 12 | Migration is a clean break: `MultiAgg`, `GroupedAgg`, `metric()`, `ScenarioMetric` are deleted. v0.1 YAML plans raise on load with a clear pointer to the migration table. | Q4 |

## 4. Public API surface

### 4.1 Aggregators (the primitive set, ~14 classes)

```python
from gaspatchio_core.scenarios import (
    # Across-scenario reducers — partition-blind
    Sum, Count, Mean, Std, Variance, Min, Max,
    ArgMin, ArgMax,
    CTE, Quantile, Median, QuantileRank,
)
```

Common constructor shape:

```python
Sum(column: str, *, within: str = "sum")
```

- `column`: name of the column the within-scenario reduction reads
- `within`: named within-reduction; one of `{"sum", "mean", "max", "min", "count", "first", "last"}`; default `"sum"`
- The across-scenario fold is implied by the class name (`Sum` → `add`, `CTE(0.005)` → tail-keep, etc.)

CTE/Quantile carry a level argument:

```python
CTE(column: str, level: float, direction: Literal["upper", "lower"] = "upper", *, within: str = "sum")
Quantile(column: str, levels: tuple[float, ...], *, within: str = "sum")
QuantileRank(column: str, at: float, *, within: str = "sum")
```

ArgMin/ArgMax return scenario_id (or scenario_id per partition):

```python
ArgMax(column: str, *, within: str = "sum")
```

### 4.2 Modifiers

Each aggregator exposes three chainable modifiers:

```python
.alias(name: str) -> Aggregator                      # name in the result dict; required (no default)
.over(by: str | tuple[str, ...]) -> Aggregator        # partition columns
.of(within_expr: pl.Expr) -> Aggregator               # polars escape hatch for the rare within reduction
```

Order doesn't matter — `.over(...).alias(...)` and `.alias(...).over(...)` produce identical aggregators. `.of(...)` replaces the named within reduction (incompatible with the `within=` constructor arg; using both raises `ValueError`).

### 4.3 ScenarioRun

```python
@dataclass(frozen=True)
class ScenarioRun:
    shocks: dict[ScenarioID, list[Shock]]
    base_tables: dict[str, Table]
    aggregations: tuple[Aggregator, ...]   # variadic; .alias required on each
    master_seed: int | None = None

    def source_sha(self) -> str: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def describe(self) -> str: ...

    def with_extra_aggregations(self, *more: Aggregator) -> ScenarioRun: ...
    def with_extra_shocks(self, more: dict[ScenarioID, list[Shock]]) -> ScenarioRun: ...
    def with_master_seed(self, seed: int) -> ScenarioRun: ...

    def run(
        self,
        af: ActuarialFrame,
        model_fn: ModelFn,
        *,
        batch_size: int | Literal["auto"] = 1,
        return_full_grid: bool = False,
        sink_dir: Path | None = None,
        audit: bool | Path = False,
    ) -> ScenarioResult: ...

    def to_yaml(self, path: Path) -> None: ...
    @classmethod
    def from_yaml(cls, path: Path, *, base_tables: dict[str, Table]) -> ScenarioRun: ...
```

Validation at construction:
- `aggregations` must be non-empty.
- Every aggregator must have a non-`None` `.alias()`. Aliases must be unique within the tuple. Both validated in `__post_init__` with clear `ValueError`.

### 4.4 ScenarioResult

```python
@dataclass(frozen=True)
class ScenarioResult:
    aggregations: dict[str, float | pl.DataFrame]   # keyed by aggregator alias
    plan_sha: str
    n_scenarios: int
    batch_size: int
    batch_size_resolution: Literal["manual", "auto_probe", "auto_calibrated"]
    wall_time_s: float
    peak_rss_mb: float | None
    sink_dir: Path | None
    audit_path: Path | None   # new: populated if audit was opt-in
```

Each entry in `result.aggregations`:
- **Scalar metric** (no `.over()`) → bare Python value (`float`, `str`, etc.) — whatever the aggregator's `extract_output` returns.
- **Partitioned metric** → `pl.DataFrame` with named partition columns + a value column whose name is the metric's alias.

Worked examples:

```python
result.aggregations["scr"]            # → 1_234_567.89 (float)
result.aggregations["worst_per_lob"]
# → pl.DataFrame({"lob": ["motor", "annuity", ...], "worst_per_lob": ["S12", "S05", ...]})
result.aggregations["scr_per_region_peril"]
# → pl.DataFrame({"region": [...], "peril": [...], "scr_per_region_peril": [...]})
```

Single-key tuple normalisation: `.over("lob")` and `.over(("lob",))` produce identical output (single `lob` column). Pinned by parametrised test.

### 4.5 Worked example — actuarial SCR with reverse stress

```python
import polars as pl
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import (
    ScenarioRun, Sum, Mean, CTE, ArgMax,
)
from gaspatchio_core.scenarios.shocks import MultiplicativeShock

af = ActuarialFrame({
    "policy_id": [1, 2, 3, 4, 5],
    "age": [30, 35, 40, 45, 50],
    "sum_insured": [100_000, 200_000, 150_000, 300_000, 250_000],
    "lob": ["term", "term", "annuity", "annuity", "endowment"],
})

mortality = Table(
    name="mortality",
    source=pl.DataFrame({"age": [30, 35, 40, 45, 50], "rate": [0.001, 0.0015, 0.002, 0.003, 0.004]}),
    dimensions={"age": "age"},
    value="rate",
)

def model_fn(af, *, tables, drivers):
    qx = tables["mortality"].lookup(scenario_id=pl.col("scenario_id"), age=pl.col("age"))
    return af.with_columns(
        (pl.col("sum_insured") * qx).alias("loss"),
    )

plan = ScenarioRun(
    shocks={
        "BASE": [],
        "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality")],
        "MORT_UP_40": [MultiplicativeShock(factor=1.4, table="mortality")],
        "COMBINED":   [MultiplicativeShock(factor=1.4, table="mortality")],
    },
    base_tables={"mortality": mortality},
    aggregations=(
        Sum("loss").alias("expected_loss"),
        Mean("loss").alias("avg_loss"),
        CTE("loss", level=0.005, direction="upper").alias("scr_loss"),
        ArgMax("loss").over("lob").alias("worst_scenario_per_lob"),
        Sum("loss").over("lob").alias("expected_loss_per_lob"),
        Sum("loss").over(("lob",)).alias("expected_loss_by_single_tuple"),  # identical to above
    ),
)

result = plan.run(af, model_fn, batch_size=4, audit=True)

assert isinstance(result.aggregations["expected_loss"], float)
assert isinstance(result.aggregations["worst_scenario_per_lob"], pl.DataFrame)
assert result.aggregations["worst_scenario_per_lob"].columns == ["lob", "worst_scenario_per_lob"]
# An audit sidecar was written:
assert result.audit_path == Path("./gaspatchio_audit/<run_id>.audit.json")
```

### 4.6 The polars escape hatch — `.of()` for the long tail

```python
# Weighted within-scenario reduction (rare, polars-bound)
Sum.of(pl.col("loss") * pl.col("policy_weight")).alias("weighted_loss")
```

Constructor signature when using `.of`:

```python
Sum.of(within_expr: pl.Expr) -> Sum   # classmethod
```

`Sum.of(...)` is incompatible with `Sum(column, within=...)`; using both raises `ValueError`. The aggregator marks itself as backend-specific in canonical_form (`{"backend_specific": true, "within_expr_b64": "..."}`), so YAML round-trip preserves it for polars consumers but raises a clear error if loaded on a future non-polars backend.

## 5. Internal contract — Beam-style `CombineFn`

Every aggregator implements:

```python
@runtime_checkable
class Aggregator(Protocol):
    def within_expr(self) -> pl.Expr:
        """The within-scenario reduction expression. Polars today;
        future backends may translate or refuse."""
        ...

    def create_accumulator(self) -> Any:
        """Return a fresh accumulator state."""
        ...

    def add_input(self, state: Any, value: Any) -> Any:
        """Fold a single per-scenario (or per-partition-cell) value into state.
        Must be commutative with merge_accumulators."""
        ...

    def merge_accumulators(self, a: Any, b: Any) -> Any:
        """Combine two accumulator states. MUST be associative and commutative."""
        ...

    def extract_output(self, state: Any) -> Any:
        """Produce the final value from the accumulator state."""
        ...

    def canonical_form(self) -> dict[str, Any]:
        """Recursive sorted dict for audit-chain hashing."""
        ...
```

The aggregator is **partition-blind**. Partitioning is the driver's concern, handled by an internal `_Partitioned` wrapper instantiated when the user calls `.over(...)`:

```python
@dataclass(frozen=True)
class _Partitioned:
    """Internal driver wrapper. Not part of the public surface."""
    by: tuple[str, ...]    # always normalised to tuple
    inner: Aggregator      # the wrapped, partition-blind aggregator
    alias: str

    def create_accumulators(self) -> dict[tuple, Any]: ...   # keyed by partition tuple
    def add_input(self, accs, partition_key, value) -> dict: ...
    def merge_accumulators(self, a, b) -> dict: ...   # merge by key
    def extract_output(self, accs) -> pl.DataFrame: ...   # one row per partition cell
```

## 6. Loop topology

The loop layer (`for_each_scenario`) is unchanged in shape from GSP-100; only the per-aggregator reduction step changes.

```python
def for_each_scenario(af, scenarios, model_fn, aggregations, ...) -> ScenarioResult:
    # 1. Classify scenarios shape (list / shocks-dict / drivers-dict) — unchanged
    # 2. Resolve batch_size — unchanged
    # 3. Initialise per-aggregator accumulator state (or per-(aggregator, partition_key) state)
    accumulators = {agg.alias: agg.create_accumulator_or_accumulators() for agg in aggregations}

    for batch_idx, batch_sids in enumerate(chunks(sids, resolved_size)):
        # 4. Build stacked tables (shocks shape) — unchanged
        # 5. Build per-batch drivers — unchanged
        # 6. Cross-join and run model_fn — unchanged
        af_proj = model_fn(af_batch, tables=stacked_tables, drivers=batch_drivers)

        # 7. NEW: per-aggregator within-scenario reduction
        proj_eager = af_proj._df.collect()   # eager batch projection (planner-fusion limitation; pre-existing)
        for agg in aggregations:
            reduced = build_within_reduction(proj_eager, agg)   # group_by [scenario_id, *agg.partition_keys] -> 1 row per scenario (× partition)
            for row in reduced.iter_rows(named=True):
                partition_key = tuple(row[k] for k in agg.partition_keys) if agg.partition_keys else None
                value = row[agg.alias]
                accumulators[agg.alias] = agg.add_input(accumulators[agg.alias], partition_key, value)

    # 8. Finalise — extract per aggregator
    final = {agg.alias: agg.extract_output(accumulators[agg.alias]) for agg in aggregations}
    return ScenarioResult(aggregations=final, ...)
```

The Polars dedupe optimisation: when multiple aggregators share the same `within_expr` (e.g., several aggregators all reading `pl.col("loss").sum()`), the projection is computed once per batch and reused — handled implicitly by Polars' query planner when `proj_eager` is the shared input.

### 6.1 Bounded-memory premise

Peak per batch is the eager projection (`n_policies × batch_size × n_periods × bytes_per_cell`).

Scalar-fold aggregators (`Sum`, `Mean`, `Min`, `Max`, `Count`, `Variance`, `ArgMax`, etc.) hold accumulators of <1 KB.

Sketch-backed aggregators (`CTE`, `Quantile`, `Median`, `QuantileRank`) hold a `DDSketch` whose memory is set by the *value range*, not the observation count — empirically ~1.2 MB per sub-sketch at `relative_accuracy=1e-4` for 6-decade lognormal data (100k observations across ~1e-6..1e6). The signed-value wrapper holds two sub-sketches, so the per-aggregator footprint is ~2.5 MB in this regime. Per-partition accumulator dicts scale as `|partition_values| × sketch_size`, so a 10-LOB CTE aggregator running at `rel_acc=1e-4` carries ~25 MB of sketch state at the end of a run.

Users can trade precision for memory via the `relative_accuracy` constructor parameter on sketch-backed aggregators (`SignedSketch(relative_accuracy=...)`). Empirically `rel_acc=1e-3` produces ~125 KB per sub-sketch (10× memory reduction) at indistinguishable CTE precision in our test regime (bucket-centre interpolation, not the relative-accuracy parameter, is the binding error source — see §14, caveat 1). `rel_acc=1e-3` is the recommended default for memory-constrained partitioned runs.

Per-partition accumulator dicts are bounded by `|partition_values|` per aggregator, which in practice is dozens to low thousands at most.

### 6.2 Hypothesis property test

A shared fixture pins the math for every registered aggregator:

```python
@given(values=lists(floats(allow_nan=False), min_size=1, max_size=200))
def test_merge_is_associative_and_commutative(agg_class, values):
    for split_point in [1, len(values) // 3, len(values) // 2, 3 * len(values) // 4]:
        left, right = values[:split_point], values[split_point:]
        agg = agg_class(column="value")

        # Single-pass
        single = reduce(lambda s, v: agg.add_input(s, None, v), values, agg.create_accumulator())

        # Two-pass + merge
        left_acc = reduce(lambda s, v: agg.add_input(s, None, v), left, agg.create_accumulator())
        right_acc = reduce(lambda s, v: agg.add_input(s, None, v), right, agg.create_accumulator())
        merged = agg.merge_accumulators(left_acc, right_acc)

        # Reverse merge order — must be identical (commutativity)
        merged_rev = agg.merge_accumulators(right_acc, left_acc)

        assert agg.extract_output(single) == agg.extract_output(merged)
        assert agg.extract_output(merged) == agg.extract_output(merged_rev)
```

For DDSketch-backed aggregators (CTE/Quantile/Median/QuantileRank), the equality is byte-identical on the serialised sketch state, not just on the extracted scalar.

## 7. DDSketch integration

### 7.1 Library choice

`ddsketch` on PyPI (DataDog, Apache-2.0, v3.0.1, pure Python). Selected over Apache DataSketches and t-digest variants because it is the only candidate that is provably bit-exact mergeable by construction (per S1):

- Bucket boundaries are data-independent (powers of γ)
- Merge is integer addition of bucket counts — associative, commutative, exact
- Pickle round-trip preserves the internal mapping object byte-identically across processes (the shipped protobuf path rebuilds the `LogarithmicMapping` from `(gamma, offset)` and drifts ~1 ULP on retrieved quantile values; pickle is used instead for the regulator-audit story — see §14, caveat 5)

**Variant chosen:** non-collapsing `DDSketch` with `DenseStore`. The collapsing variants (`LogCollapsingHighestDenseDDSketch`, `LogCollapsingLowestDenseDDSketch`) drop accuracy on the highest- or lowest-magnitude observed values once the bucket count exceeds `bin_limit`. Empirically (`tests/scratch/gsp101_t3_fix/measure.py`):

- `Highest` collapses *exactly the bins the upper-tail CTE reads from*. On 100k lognormal observations across 6 decades, `bin_limit=65536` (576 KB) drives q99.5 toward zero (>9000 bp error) — the collapsed tail is gone.
- `Lowest` would collapse the small-magnitude bins needed for the median-of-`1..10` test class.
- Plain non-collapsing `DDSketch` is the only variant that preserves both tails *and* gives deterministic, bit-exact merging across our actuarial workload.

**Parameters:** `DDSketch(relative_accuracy=1e-4)` is the project default, exposed on the `SignedSketch` constructor for caller tuning. Measured: ~47 bp relative error on the 99.5% quantile of 100k 6-decade lognormal data at `rel_acc=1e-4`, and ~46 bp at `rel_acc=1e-3` — bucket-centre interpolation, not the relative-accuracy parameter, is the binding error source. For SCR-99.5% and VM-21 CTE-70, single-digit-bp precision is well inside regulator tolerance.

### 7.2 Signed-value handling

DDSketch's relative-error semantics assume strictly positive values. Actuarial values cross zero (P&L, net surplus). The wrapper holds two sub-sketches:

```python
@dataclass(frozen=True)
class _SignedSketch:
    pos: DDSketch       # values > 0
    neg: DDSketch       # absolute values of values < 0
    zero_count: int     # values exactly 0
```

CTE/quantile queries route to the appropriate sub-sketch by sign; merge is element-wise on `pos`, `neg`, `zero_count`. Documented as the canonical signed-value pattern.

### 7.3 Within-batch step stays Polars

The within-scenario reduction (`pl.col("loss").sum()` grouped by scenario) remains a Polars expression. Only the across-batch fold uses DDSketch. This means within-batch quantile work uses Polars' exact `quantile_cont` (free, SIMD-fast); DDSketch earns its keep only when crossing batches.

## 8. `.over()` and multi-column partitioning

### 8.1 Surface

```python
Sum("loss").over("lob")                        # single key
Sum("loss").over(("region", "peril"))          # multi key
Sum("loss").over(("lob",))                     # normalised to single-key form
Sum("loss")                                    # no partition
```

Internally, `.over(by)` normalises `by` to a tuple and constructs a `_Partitioned` wrapper. The aggregator inside is unchanged.

### 8.2 Output shape

Partitioned aggregator output is always a `pl.DataFrame`:
- One column per partition key
- One value column named after the aggregator's alias
- Rows = number of distinct partition tuples that received any input

Single-key tuple normalisation (the S2 risk):
- `.over("lob")` and `.over(("lob",))` produce *identical* output (single `lob` column, NOT a tuple-keyed column).
- Pinned by parametrised test.

## 9. Audit sidecar

### 9.1 When written

Controlled by the `audit` parameter on `ScenarioRun.run()`:

- `audit=False` (default): nothing written
- `audit=True`: written to `./gaspatchio_audit/<run_id>.audit.json` (creates the directory if needed)
- `audit=Path(...)`: written to explicit path

`run_id` is derived as `f"{utc_timestamp}_{source_sha[:8]}"` — sortable by time, traceable by SHA prefix.

When `sink_dir` (full-grid mode) is set, the sidecar is written inside `sink_dir` instead of the default location.

### 9.2 Schema

```json
{
  "schema_version": "1.0",
  "source_sha": "sha256:6bb1a67c...",
  "plan_canonical_form": { ... },
  "run_metadata": {
    "started_utc": "2026-05-11T14:23:00Z",
    "wall_time_s": 12.34,
    "library_version": "0.2.0",
    "polars_version": "1.38.1",
    "ddsketch_version": "3.0.1",
    "python_version": "3.13.0",
    "master_seed": null,
    "host_fingerprint": "host:os-version (SHA of /etc/machine-id, optional)"
  },
  "aggregator_outputs": {
    "scr": 1234567.89,
    "worst_per_lob": {"motor": "S12", "annuity": "S05", ...}
  },
  "input_data_fingerprint": {
    "schema_sha": "sha256:...",
    "row_count": 5000,
    "column_names": ["policy_id", "age", "sum_insured", "lob"]
  }
}
```

Notes:
- Partitioned aggregator outputs are serialised as plain dicts in the sidecar (not parquet), keyed by partition values. Larger partitioned outputs (>10k cells) may overflow; v0.2 ships with inline-only and documents the limit. Path-to-parquet output is a follow-on if real datasets hit the ceiling.
- `input_data_fingerprint` is the schema SHA + row count, not the data SHA. The data is the firm's; we don't fingerprint it. This is enough to confirm "same shape of data" without exfiltrating values.
- `host_fingerprint` is optional and toggled by `GASPATCHIO_AUDIT_HOST=1`. Default off to avoid surprising users.

### 9.3 Reading the sidecar

A reader doesn't need gaspatchio. The file is plain JSON; any actuary with a text editor can inspect the SHA, run metadata, and outputs. The plan recipe is the same canonical form GSP-100 ships.

### 9.4 Cost

~250 LoC for the writer + reader + schema validation; ~5 tests including a golden-file snapshot. No new dependencies (JSON is stdlib).

## 10. Migration from v0.1 → v0.2

### 10.1 Symbol-level migration

| v0.1 symbol | v0.2 replacement |
|---|---|
| `MultiAgg({"name": Aggregator})` | `ScenarioRun(aggregations=(Aggregator(...).alias("name"), ...))` |
| `GroupedAgg(by="lob", metric=ArgMax())` | `ArgMax("col").over("lob")` |
| `metric("col", Sum())` | `Sum("col")` |
| `ScenarioMetric(per_scenario=expr, across_scenario=agg)` | (delete) — within-reduction lives on the aggregator now |
| `for_each_scenario(..., per_scenario=...)` | `per_scenario` kwarg removed; aggregator carries its own within reduction |
| `Sum().finalize(state)` (column-blind) | `Sum("col").extract_output(state)` |

### 10.2 YAML compatibility

v0.1 YAML plans (using the old `per_scenario_expr_b64` + flat `MultiAgg.metrics` shape) raise on load:

```
ValueError: Plan YAML uses v0.1 schema (aggregator 'MultiAgg' was retired
in v0.2). See ref/41-backend-portability/specs/2026-05-11-gsp-101-...
section 10 for the migration table.
```

We do not provide an automatic migrator. The user updates the recipe in Python and re-saves.

### 10.3 Files retired

```
bindings/python/gaspatchio_core/scenarios/_aggregators.py   # rewritten wholesale
bindings/python/gaspatchio_core/scenarios/_config.py        # parse_aggregations rewritten
bindings/python/gaspatchio_core/scenarios/_for_each.py      # loop body updated
bindings/python/gaspatchio_core/scenarios/_run.py           # ScenarioRun.aggregations type changes
bindings/python/gaspatchio_core/scenarios/_result.py        # aggregations type changes; audit_path added
```

Plus new files:
```
bindings/python/gaspatchio_core/scenarios/_metric.py        # NEW: Aggregator Protocol + _Partitioned wrapper
bindings/python/gaspatchio_core/scenarios/_sketch.py        # NEW: DDSketch facade with signed-value support
bindings/python/gaspatchio_core/scenarios/_audit.py         # NEW: sidecar writer/reader/schema
```

Tests updated wholesale; existing test names preserved where possible.

## 11. Module layout (final)

```
bindings/python/gaspatchio_core/scenarios/
├── __init__.py            # exports the 14 aggregators + ScenarioRun + ScenarioResult
├── __init__.pyi           # type stubs
├── _metric.py             # NEW: Aggregator Protocol + _Partitioned wrapper + modifiers
├── _aggregators.py        # 14 aggregators implementing the Protocol (rewritten)
├── _sketch.py             # NEW: DDSketch wrapper with paired signed-value sketches
├── _audit.py              # NEW: sidecar JSON schema + writer + reader
├── _for_each.py           # loop topology (per-aggregator within-reduction)
├── _run.py                # ScenarioRun typed plan
├── _result.py             # ScenarioResult (adds audit_path)
├── _stack.py              # stack_shocked_table (unchanged)
├── _config.py             # parse_aggregations + parse_scenario_config (rewritten)
├── _auto_batch.py         # batch_size resolution (unchanged)
├── _validate.py           # shared validators (unchanged)
├── _with_scenarios.py     # cross-join helper (unchanged)
└── shocks.py              # Shock primitives (unchanged)
```

## 12. Testing strategy

### 12.1 Unit tests per aggregator

For each of the 14 aggregators:
- Constructor validation (column required; within-name in allowed set; mutually exclusive `.of()`)
- Welford / sketch correctness against a numpy reference
- `merge_accumulators` is associative + commutative (Hypothesis fixture)
- `canonical_form` is deterministic + sorted
- YAML round-trip preserves SHA + bit-exact aggregations

### 12.2 Loop-level tests

Lift the existing GSP-100 scenarios test suite and update for the new surface:
- `test_for_each_scenario.py` — list-of-IDs shape; scalar aggregators
- `test_for_each_shocks.py` — shocks-dict shape; batch-equivalence
- `test_for_each_drivers.py` — drivers shape + master_seed (batch_size=1 only; raise at batch>1, unchanged)
- `test_for_each_partitioned.py` — NEW: `.over()` patterns including multi-key + single-key tuple normalisation
- `test_audit_chain.py` — end-to-end SHA stability + YAML round-trip + audit sidecar round-trip
- `test_governance_cross_process.py` — NEW: lift the stress-test agent-3 cross-process bit-exact pattern as a permanent test (with custom plugin aggregator)

### 12.3 Property tests

Single Hypothesis fixture parametrised over all registered aggregators; pins associativity, commutativity, batch-equivalence.

### 12.4 Reference comparison

For each non-trivial aggregator (Mean, Std, Variance, CTE, Quantile, ArgMax), assert agreement with a manual numpy reference on synthetic distributions (uniform, normal, skewed, all-equal degenerate, single-value degenerate).

## 13. Compositional contracts for deferred work

These layers are explicitly deferred but the spec commits to their shape so future implementation cannot drift:

### 13.1 Actuarial aliases (follow-on PR)

```python
# In a future PR; not in GSP-101:
AAL = Mean       # Average Annual Loss
VaR = Quantile   # Value at Risk
TVaR = CTE       # Tail-conditional Value at Risk
EP = Sum         # Expected Pure premium
```

Aliases are class-level (subclass with no overrides), so `AAL("loss").alias("aal")` works identically to `Mean("loss").alias("aal")`. The canonical_form's `kind` field uses the canonical (primitive) name to keep SHAs stable across alias usage.

### 13.2 Cross-backend implementations (post-rollforward backend evolution)

The `within_expr()` method on the Protocol returns `pl.Expr` today. The seam allows future backends:
- `within_expr()` → `BackendExpression` (abstract)
- Polars backend: returns `pl.Expr`
- Pandas backend: returns a callable `df -> df`
- DuckDB backend: returns a SQL fragment

`.of()` becomes `.of_polars()`; analogous `.of_pandas()` and `.of_sql()` are added per backend. Existing usage of `.of()` remains the polars-bound form.

### 13.3 Larger partitioned outputs (path-to-parquet)

If a partitioned aggregator's output exceeds an internal threshold (say 10k cells), v0.2 emits inline anyway with a warning. A future version may switch to writing partitioned output to a parquet file in `sink_dir` and storing the path in the sidecar's `aggregator_outputs` (a string starting with `parquet://`).

### 13.4 Partition audit in the sidecar

v0.2's sidecar records aggregator outputs but not which partition values were observed. A future minor version adds:
```json
"partition_audit": {
  "worst_per_lob": ["term", "annuity", "endowment", "wholelife"]
}
```
documenting the partition cells for downstream reconciliation.

## 14. Known caveats

1. **DDSketch CTE precision is bounded by bucket discretisation, not by integration step.** Measured: ~10.5 bp relative error on a uniform `1..1000` distribution at `level=0.005` (top-0.5% mean, true value 998, reported 996.95), independent of `n_probes` (refining the integration grid does not help). For SCR-99.5% and VM-21 CTE-70 this is well inside regulator tolerance (both accept single-digit-bp precision). Tighter precision would require `relative_accuracy=1e-5` at correspondingly higher memory cost, but the bucket-centre interpolation bias would still dominate; users needing exact small-domain CTE should fall back to materialised aggregators.
2. **YAML uses `Expr.meta.serialize(format="binary")` for the polars escape hatch.** Bit-exact on Polars 1.38.1 (verified). Pinned via test; documented Polars-version-pinning requirement.
3. **The eager `.collect()` at the batch boundary is preserved.** Same Polars planner-fusion limitation as GSP-100 (`lookup_by_table_and_hash` advertises wrong output dtype). Bounded memory holds at the batch level; "lazy through reduction" remains aspirational.
4. **`master_seed` and drivers still raise at `batch_size > 1`.** Unchanged from GSP-100's correctness behaviour. A future redesign of the drivers contract could lift this; out of scope.
5. **DDSketch state is serialised via pickle (not protobuf).** The protobuf round-trip rebuilds the mapping from `(gamma, offset)` and drifts ~1 ULP on retrieved quantile values; pickle preserves the mapping object exactly. Pickle stability requires pinning the `ddsketch` library version — recorded in the audit sidecar's `library_version` block alongside the Polars version. Cross-version pickle compatibility is not guaranteed; the regulator-audit replay story assumes the same `ddsketch` wheel is installed.

## 15. References

### Research
- R1 — Apache Beam CombineFn / CombinePerKey: https://beam.apache.org/documentation/programming-guide/#combine
- R1 — Apache DataSketches (mergeable summaries contract): https://datasketches.apache.org/docs/Background/TheChallenge.html
- R2 — Polars `df.group_by().agg(named_exprs...)`: https://docs.pola.rs/user-guide/expressions/aggregation/
- R2 — dplyr `summarise()` + `across()`: https://dplyr.tidyverse.org/reference/summarise.html
- R3 — Oasis LMF Results + ORD: https://oasislmf.github.io/sections/results.html
- S1 — DDSketch paper (VLDB 2019): https://www.vldb.org/pvldb/vol12/p2195-masson.pdf
- S1 — t-digest order-sensitivity issue: https://github.com/tdunning/t-digest/issues/94
- S2 — Polars GROUPING SETS feature request: https://github.com/pola-rs/polars/issues/7948
- S3 — Oasis ORD repository: https://github.com/OasisLMF/ODS_OpenResultsData
- S3 — Apache Beam Programming Guide: https://beam.apache.org/documentation/programming-guide/

### Internal
- GSP-100 spec: `ref/41-backend-portability/specs/2026-05-11-gsp-100-scenariorun-design.md`
- GSP-100 plan: `ref/41-backend-portability/plans/2026-05-11-gsp-100-scenariorun.md`
- DX backlog: `ref/41-backend-portability/2026-05-11-gsp-100-dx-improvements.md`
- Dog-fooding scratch (round 1): `bindings/python/tests/scratch/gsp100_dogfooding/`
- Stress-test scratch (round 2): `bindings/python/tests/scratch/gsp100_stress/`
