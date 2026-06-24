# GSP-100 — ScenarioRun + for_each_scenario: bounded-memory stochastic runner

**Linear:** GSP-100
**Status:** Design
**Date:** 2026-05-11
**Branch:** `gsp-100-scenariorun-bounded-memory`
**Parent research:** GSP-99; `ref/41-backend-portability/`

---

## 1. Why this exists

Empirical measurements (May 2026, `ref/41-backend-portability/41-scenario-scaling-empirical.md`) confirm that `with_scenarios` row replication does not stay bounded by Polars streaming. On a 16 GB Mac at 1k policies × 240 months:

| n_scenarios | Peak RSS | Wall | Status |
| -- | -- | -- | -- |
| 50 | 6.2 GB | 5s | works |
| 100 | 8.8 GB | 14s | works |
| 200 | 8.9 GB | 48s | works |
| 500 | 9.2 GB RSS / **56 GB total VM** | killed | swap thrash |

Per-row footprint is ~110–125 KB. Memory grows linearly in `n_policies × n_scenarios` until physical RAM saturates and macOS swap-thrashes (Linux would OOM-kill). The streaming engine engages but ends in `in-memory-sink`, so the result re-materialises at the end. The lazy `with_scenarios` fix in commit `9824f2d` cut RSS 10–21% but did not change the shape — contributing fix, not the cure.

The cure is structural: replace the cross-join shape with an outer scenario loop that materialises one batch at a time, applies a within-scenario reduction lazily, and folds the small reduced frame into an aggregator. Peak memory becomes a function of `batch_size`, not `n_scenarios`.

---

## 2. Decisions log

Eleven decisions resolved during design. Each is load-bearing; reopening any of them changes downstream sections.

| # | Decision | Resolution |
|---|---|---|
| 1 | `Table.canonical_form()` + `Table.source_sha()` scope | **In GSP-100.** Mirror Schedule/Curve/MortalityTable pattern. |
| 2a | Aggregator reduction axis | **Hybrid recipe:** `ScenarioMetric(per_scenario=pl.Expr, across_scenario=Aggregator)`. |
| 2b | Aggregator starter set | **15 + plugin registry.** Sum, Count, Mean, Std, Variance, Min, Max, ArgMin, ArgMax, CTE, Quantile, Median, QuantileRank, GroupedAgg, MultiAgg. |
| 2c | Aggregator API: eager vs lazy | **Aggregator API is eager (`pl.DataFrame`); loop is lazy through and including the per_scenario reduction.** |
| 3 | `batch_size="auto"` default + audit | **Default `1`; `"auto"` opt-in.** Resolved size + resolution method (`"manual" \| "auto_probe" \| "auto_calibrated"`) on `ScenarioResult`. **Not** part of plan SHA. |
| 4 | `return_full_grid` file layout | **`sink_dir/batch_<idx>.parquet`, no `partition_by`.** Each batch sorted by `scenario_id` before write for predicate pushdown. File count = `n_batches`. |
| 5 | RNG / reproducibility | **Optional `master_seed: int \| None`** on the plan. Per-scenario seed derived deterministically via SHA-256; passed via `drivers["rng_seed"]`. Folded into `canonical_form` when set. |
| 6 | `Table.with_shock` vs `apply_shock` | **`with_shock` is the existing name.** Ticket's `apply_shock` is a doc bug. |
| 7 | Auto-batch memory measurement | **Python-side `psutil.Process().memory_info().rss` delta probe, plus optional calibration constant `bytes_per_cell`.** Single file `_auto_batch.py`. No Rust extension. Subprocess probe + Rust allocator stats deferred to v0.2 (cites polars#27012). |
| 8 | Memory hygiene | **Drop `gc.collect()` from the loop** (polars#23128 confirms Python-side cleanup does not release Polars memory). Document bounded-within-batch / drift-between-batches caveat. Instrument `peak_rss_mb` on `ScenarioResult`. Subprocess-per-batch isolation deferred to v0.2. |
| 9 | User-defined aggregators | **In v0.1 via plugin registry.** `register_aggregator(name, cls)` + `@scenario_aggregator()` decorator. Built-ins dogfood the API. `from_yaml` resolves via registry. Plan SHA pins registered `kind` name, not implementation. |
| 10 | `with_scenarios` visibility | **Keep public** as low-level cross-join primitive; not used in tutorials. The "doesn't fit the aggregator model" escape hatch. |

---

## 3. Architecture (module layout)

Three new files, three extended files, no file exceeds ~500 LOC.

```
bindings/python/gaspatchio_core/
├── _identity.py                    # NEW (if not extracted from existing) — canonical_bytes / source_sha_of
├── scenarios/
│   ├── __init__.py                 # extended — new public exports
│   ├── _run.py                     # NEW — ScenarioRun dataclass + .run() + identity
│   ├── _for_each.py                # NEW — for_each_scenario primitive (the loop)
│   ├── _result.py                  # NEW — ScenarioResult dataclass
│   ├── _aggregators.py             # NEW — Protocol + ScenarioMetric + 15 starters + registry
│   ├── _stack.py                   # NEW — stack_shocked_table helper
│   ├── _auto_batch.py              # NEW — probe + calibration paths (psutil)
│   ├── _validate.py                # NEW — shared scenario-id / column-collision checks
│   ├── _config.py                  # extended — aggregations in YAML; ScenarioRun.from_yaml
│   ├── _batching.py                # RETIRED (deleted)
│   ├── _sensitivity.py             # internalised — no longer in __all__
│   ├── _with_scenarios.py          # kept public, uses _validate
│   ├── _describe.py                # merged into ScenarioRun.describe() then retired
│   └── shocks.py                   # extended — Shock.canonical_form on base + all 11 subclasses
└── assumptions/
    └── _api.py                     # extended — Table.canonical_form + Table.source_sha
```

`for_each_scenario` does not import `ScenarioRun`; `ScenarioRun.run()` calls `for_each_scenario`. An import lint enforces the one-way dependency.

### Public surface (`scenarios/__init__.py`)

```python
__all__ = [
    # kept
    "Shock", "MultiplicativeShock", "AdditiveShock", "OverrideShock",
    "ClipShock", "PipelineShock", "FilteredShock", "TimeConditionalShock",
    "RelativeFloorShock", "MaxShock", "MinShock", "ParameterShock",
    "with_scenarios",
    "parse_scenario_config", "parse_shock_config",
    # new in GSP-100
    "ScenarioRun", "ScenarioResult", "ScenarioMetric",
    "ScenarioAggregator", "for_each_scenario",
    "register_aggregator", "scenario_aggregator",
    "Sum", "Count", "Mean", "Std", "Variance",
    "Min", "Max", "ArgMin", "ArgMax",
    "CTE", "Quantile", "Median", "QuantileRank",
    "GroupedAgg", "MultiAgg",
]
```

Three names removed (breaking): `batch_scenarios`, `sensitivity_analysis`, `describe_scenarios`.

---

## 4. Data shapes

### 4.1 `ScenarioRun`

```python
@dataclass(frozen=True)
class ScenarioRun:
    """Reusable, auditable stochastic-run plan."""

    shocks: dict[str, list[Shock]]
    base_tables: dict[str, Table]
    aggregations: dict[str, ScenarioMetric]
    master_seed: int | None = None

    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
    def describe(self) -> str: ...

    def with_extra_shocks(self, more: dict[str, list[Shock]]) -> ScenarioRun: ...
    def with_extra_aggregations(self, more: dict[str, ScenarioMetric]) -> ScenarioRun: ...
    def with_master_seed(self, seed: int) -> ScenarioRun: ...

    @classmethod
    def from_yaml(cls, path: Path, *, base_tables: dict[str, Table]) -> ScenarioRun: ...
    @classmethod
    def from_dict(cls, config: dict, *, base_tables: dict[str, Table]) -> ScenarioRun: ...
    def to_yaml(self, path: Path) -> None: ...
    def to_dict(self) -> dict: ...

    def run(
        self,
        af: ActuarialFrame,
        model_fn: Callable[..., ActuarialFrame],
        *,
        batch_size: int | Literal["auto"] = 1,
        target_memory_fraction: float = 0.5,
        bytes_per_cell: int | None = None,
        return_full_grid: bool = False,
        sink_dir: Path | None = None,
    ) -> ScenarioResult: ...
```

`frozen=True` gives free `__eq__`/`__hash__`. We do **not** define `__eq__` from `source_sha` — structural equality is a separate concern from audit identity.

### 4.2 `ScenarioMetric`

```python
@dataclass(frozen=True)
class ScenarioMetric:
    """The full reduction recipe for one named metric.

    per_scenario collapses rows → 1 number per scenario.
    across_scenario reduces across scenarios to a final result.
    """
    per_scenario: pl.Expr
    across_scenario: ScenarioAggregator

    def canonical_form(self) -> dict[str, Any]:
        return {
            "per_scenario_expr_b64": base64.b64encode(
                self.per_scenario.meta.serialize()
            ).decode("ascii"),
            "across_scenario": self.across_scenario.canonical_form(),
        }


def metric(column: str, agg: ScenarioAggregator) -> ScenarioMetric:
    """Sugar for the sum-default case: ScenarioMetric(per_scenario=pl.col(column).sum(), ...)."""
    return ScenarioMetric(per_scenario=pl.col(column).sum(), across_scenario=agg)
```

`pl.Expr.meta.serialize()` returns binary bytes (Polars 1.x). Base64-encoded for JSON transport. Stable across patch versions; not guaranteed across minor versions — pin Polars version on regulator-bound runs.

### 4.3 `ScenarioResult`

```python
@dataclass(frozen=True)
class ScenarioResult:
    """Output of ScenarioRun.run() or for_each_scenario."""

    aggregations: dict[str, Any]
    plan_sha: str
    n_scenarios: int
    batch_size: int                                      # resolved
    batch_size_resolution: Literal["manual", "auto_probe", "auto_calibrated"]
    wall_time_s: float
    peak_rss_mb: float | None
    sink_dir: Path | None
```

Two same-plan runs on different machines share `plan_sha`. Their `batch_size`, `wall_time_s`, and `peak_rss_mb` may differ — runtime metadata, not plan identity.

### 4.4 `ScenarioAggregator` Protocol

```python
@runtime_checkable
class ScenarioAggregator(Protocol):
    """Cross-scenario reducer. update() sees one-row-per-scenario frames
    with columns [scenario_id, value] (+ group columns for GroupedAgg's inner df)."""

    def init(self) -> Any: ...
    def update(self, state: Any, df: pl.DataFrame) -> Any: ...
    def finalize(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...
```

Every aggregator reads `df["value"]`. `MultiAgg` re-aliases its named columns to `"value"` before passing the slice to each sub-aggregator — see §6.4.

### 4.5 `Table` additions

```python
class Table:
    # ... existing ...

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Table",
            "name": self._name,
            "dimensions": sorted(self._dimensions.keys()),
            "value_column": self._value,
            "content_sha": self._content_sha(),
        }

    def source_sha(self) -> str:
        return source_sha_of(self.canonical_form())

    def _content_sha(self) -> str:
        """Row-order-independent content hash via parquet bytes of sorted frame."""
        df = self._df_materialised()
        cols = sorted(self._dimensions.keys()) + [self._value]
        sorted_df = df.select(cols).sort(sorted(self._dimensions.keys()))
        parquet_bytes = sorted_df.write_parquet()                # in-memory
        return f"sha256:{hashlib.sha256(parquet_bytes).hexdigest()}"
```

A shocked table (`t.with_shock(...)`) has a different `content_sha`. A table loaded from CSV vs DataFrame source has the same `content_sha` if the data matches — source kind does not leak into identity.

---

## 5. Loop / `for_each_scenario` contract

### 5.1 Signature

```python
def for_each_scenario(
    af: ActuarialFrame,
    scenarios: list[ScenarioID]
              | dict[ScenarioID, list[Shock]]
              | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., ActuarialFrame],
    agg: ScenarioAggregator,
    *,
    base_tables: dict[str, Table] | None = None,
    per_scenario: pl.Expr | dict[str, pl.Expr] | None = None,
    batch_size: int | Literal["auto"] = 1,
    target_memory_fraction: float = 0.5,
    bytes_per_cell: int | None = None,
    return_full_grid: bool = False,
    sink_dir: Path | None = None,
    master_seed: int | None = None,
    progress: bool = False,
) -> ScenarioResult:
    ...
```

### 5.2 Shape polymorphism

| Shape | Used for | Table handling |
|---|---|---|
| `list[ScenarioID]` | scenarios without shocks | `base_tables` used as-is |
| `dict[ScenarioID, list[Shock]]` | per-scenario shocks | `stack_shocked_table` per batch |
| `dict[ScenarioID, dict[str, Any]]` | arbitrary drivers (ESG paths, ParameterShock) | `base_tables` as-is; drivers via `model_fn(drivers=...)` |

A `TypeError` at entry names the offending key if a dict mixes shapes.

### 5.3 Loop body

```python
def for_each_scenario(af, scenarios, model_fn, agg, *,
                     base_tables=None, per_scenario=None,
                     batch_size=1, target_memory_fraction=0.5,
                     bytes_per_cell=None,
                     return_full_grid=False, sink_dir=None,
                     master_seed=None, progress=False):

    shape = _classify(scenarios)
    sids = _scenario_ids(scenarios, shape)
    _validate.scenarios(sids, af)

    resolved_size, resolution = _resolve_batch_size(
        af, scenarios, model_fn, base_tables, per_scenario,
        batch_size, target_memory_fraction, bytes_per_cell,
    )

    if return_full_grid:
        sink_dir = sink_dir or Path(f"./scenarios_{uuid4().hex}")
        sink_dir.mkdir(parents=True, exist_ok=True)

    state = agg.init()
    started = time.perf_counter()

    for batch_idx, batch_sids in enumerate(_chunks(sids, resolved_size)):

        # Stacked tables only for the shocks shape
        if shape == "shocks":
            stacked_tables = {
                name: stack_shocked_table(
                    base,
                    {sid: [s for s in scenarios[sid] if s.table == name]
                     for sid in batch_sids},
                )
                for name, base in (base_tables or {}).items()
            }
        else:
            stacked_tables = base_tables or {}

        batch_drivers = _build_drivers(scenarios, batch_sids, shape, master_seed)

        af_batch = with_scenarios(af, list(batch_sids))

        af_proj = model_fn(af_batch, tables=stacked_tables, drivers=batch_drivers)

        if per_scenario is not None:
            reduced = (af_proj._df
                       .group_by("scenario_id", maintain_order=True)
                       .agg(_as_exprs(per_scenario)))
        else:
            reduced = af_proj._df

        if return_full_grid:
            (af_proj._df
                .sort("scenario_id")
                .sink_parquet(sink_dir / f"batch_{batch_idx:04d}.parquet"))

        df_small = reduced.collect(engine="streaming")
        state = agg.update(state, df_small)

        if progress:
            _emit_progress(batch_idx, len(sids), resolved_size)

    return ScenarioResult(
        aggregations=agg.finalize(state),
        plan_sha="",                                             # filled by ScenarioRun.run()
        n_scenarios=len(sids),
        batch_size=resolved_size,
        batch_size_resolution=resolution,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=_peak_rss_mb(),
        sink_dir=sink_dir if return_full_grid else None,
    )
```

### 5.4 Contracts

1. **`model_fn` MUST return a lazy `ActuarialFrame`** (`af._df` is `pl.LazyFrame`). The loop never collects until after `per_scenario`.
2. **`per_scenario` MUST reduce to one row per `scenario_id`.** Detected after collect; clear error names the offending metric.
3. **Batch equivalence:** same plan + `master_seed`, two different `batch_size` → aggregator outputs equal within fp tolerance for fp metrics, exactly equal for integer metrics.
4. **`progress=True`** uses Loguru (per project standards); no `print`. INFO-level batch-complete events.

### 5.5 Master seed derivation

```python
def _per_scenario_seed(master_seed: int, scenario_id: ScenarioID) -> int:
    payload = f"gsp-100|{master_seed}|{scenario_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")
```

`hashlib.sha256` (not Python `hash()`) because PYTHONHASHSEED randomises string hashing across processes. The derived seed is a deterministic 32-bit int passed in `drivers["rng_seed"]`. Per-scenario seed is the same regardless of `batch_size` → bit-equivalence preserved.

### 5.6 `ScenarioRun.run()` delegation

```python
def run(self, af, model_fn, *, batch_size=1, target_memory_fraction=0.5,
        bytes_per_cell=None, return_full_grid=False, sink_dir=None):
    plan_sha = self.source_sha()
    multi = MultiAgg({name: m.across_scenario for name, m in self.aggregations.items()})
    per_scen = {name: m.per_scenario for name, m in self.aggregations.items()}

    result = for_each_scenario(
        af, self.shocks, model_fn,
        agg=multi,
        base_tables=self.base_tables,
        per_scenario=per_scen,
        batch_size=batch_size,
        target_memory_fraction=target_memory_fraction,
        bytes_per_cell=bytes_per_cell,
        return_full_grid=return_full_grid,
        sink_dir=sink_dir,
        master_seed=self.master_seed,
    )
    return replace(result, plan_sha=plan_sha)
```

### 5.7 Memory hygiene caveats

**The bounded-memory guarantee holds within a batch, not across batches.** Polars-side memory is not guaranteed to return to the OS between batches (Rust allocator behaviour, polars#23128). On long runs, expect peak RSS drift. Mitigations:

- `peak_rss_mb` recorded on every `ScenarioResult` for drift detection.
- Acceptance benchmark asserts peak RSS is bounded *within batch*, not across run.
- Recommend `MIMALLOC_PURGE_DELAY=0` or jemalloc tuning on Linux (documented as an environment-variable recipe in `docs/concepts/scenarios/memory-and-seed.md`).
- Subprocess-per-batch isolation is the proper fix; deferred to v0.2.

`gc.collect()` is **not** called in the loop — empirical evidence (polars#23128, polars#20851) confirms it does not release Polars's Rust-side memory and pays a Python-heap traversal cost for no benefit.

### 5.8 Auto-batch resolution

Single file `_auto_batch.py`. Two paths:

```python
def _resolve_batch_size(af, scenarios, model_fn, base_tables, per_scenario,
                       batch_size, target_memory_fraction, bytes_per_cell):
    if batch_size != "auto":
        if bytes_per_cell is not None:
            raise ValueError("bytes_per_cell only applies when batch_size='auto'")
        return batch_size, "manual"

    available = psutil.virtual_memory().available
    target_bytes = int(available * target_memory_fraction)
    stacked_overhead = _estimate_stacked_overhead(base_tables, scenarios)

    if bytes_per_cell is not None:
        # Calibrated path — no probe
        n_policies = af._df.select(pl.len()).collect().item()
        n_periods = _estimate_n_periods(af)
        per_scenario_bytes = bytes_per_cell * n_policies * n_periods
        raw = (target_bytes - stacked_overhead) // per_scenario_bytes
        return max(1, min(raw, _SAFETY_CEILING)), "auto_calibrated"

    # Probe path — run scenario 1, measure rss delta
    rss_before = _process_rss_bytes()
    _run_one_batch_for_probe(af, scenarios, model_fn, base_tables, per_scenario,
                             master_seed=None)
    rss_after = _process_rss_bytes()
    per_scenario_bytes = max(rss_after - rss_before, _MIN_PROBE_BYTES)

    raw = (target_bytes - stacked_overhead) // per_scenario_bytes
    return max(1, min(raw, _SAFETY_CEILING)), "auto_probe"
```

`_SAFETY_CEILING = 256`. `_MIN_PROBE_BYTES = 1_000_000`. The probe scenario's result is **discarded** — clean semantics; one scenario's compute is spent on sizing.

**Known bias:** `psutil` RSS includes Polars-retained-but-not-active memory. Probe-derived per_scenario_bytes over-estimates; resolved `batch_size` is conservative. This is the safe failure mode (under-size, not OOM). Documented in `ScenarioResult.batch_size_resolution`.

---

## 6. Aggregators

### 6.1 Plugin registry

```python
_AGGREGATOR_REGISTRY: dict[str, type[ScenarioAggregator]] = {}

def register_aggregator(name: str, cls: type[ScenarioAggregator]) -> None:
    if name in _AGGREGATOR_REGISTRY:
        raise ValueError(f"Aggregator {name!r} already registered")
    _AGGREGATOR_REGISTRY[name] = cls

def scenario_aggregator(name: str | None = None):
    """@scenario_aggregator() decorator. Uses cls.__name__ if name omitted."""
    def wrap(cls):
        register_aggregator(name or cls.__name__, cls)
        return cls
    return wrap
```

Built-ins register themselves at import via the decorator. `parse_aggregations` looks up `kind` in the registry; raises a clear error naming the missing class if not found.

Plan SHA pins the registered `kind` name, not the implementation. Two installations with different `WorstK` implementations under the same name will hash the same plan but may produce different results — same caveat shape as Polars version pinning.

### 6.2 The 15 starter aggregators

All are `@dataclass(frozen=True)` decorated with `@scenario_aggregator()`. Each:
- Reads `df["value"]` (or `df[self.by]` for `GroupedAgg`'s grouping column).
- Returns a `canonical_form()` dict including `"kind"` and every output-affecting parameter.
- Is batch-equivalent across `batch_size ∈ {1, 8, 64}` — verified by parametrised tests.

Numeric reducers (Sum, Count, Mean, Std, Variance, Min, Max):
- `Sum` — state: float; runs total.
- `Count` — state: int; row count.
- `Mean` — state: `(n, mean)`; combined via parallel-Welford.
- `Std` — state: `(n, mean, m2)`; Chan/Welford parallel combine; population std in `finalize`.
- `Variance` — alias around `Std`, returns squared result.
- `Min` / `Max` — state: float; running min/max.

Scenario-identity reducers (ArgMin, ArgMax):
- State: `(extreme_value, extreme_scenario_id)`.
- Tiebreak rule: lexicographically smaller `scenario_id` wins on ties.
- **Composable inside `GroupedAgg`** — `GroupedAgg(by="lob", metric=ArgMax())` returns `dict[lob, ScenarioID]`, the "worst scenario per LoB" pattern. Output type is `ScenarioID`, not numeric; this is intentional.
- `canonical_form()` includes `{"tiebreak": "lexicographic"}` for explicit audit.

Tail and quantile reducers (CTE, Quantile, Median, QuantileRank):
- All buffer per-scenario values to a list; reduction at `finalize`.
- `CTE(level, direction="upper")` — mean of the upper-`level` tail.
- `Quantile(levels: tuple[float, ...])` — exact quantiles via `statistics.quantiles`; levels stored sorted in canonical form.
- `Median` — alias for `Quantile((0.5,))` returning a scalar.
- `QuantileRank(at: float)` — percentile of `at` in the empirical CDF; satisfies IFRS 17 §119 disclosure.

Composers (GroupedAgg, MultiAgg):

```python
@dataclass(frozen=True)
class GroupedAgg:
    """Apply a sub-aggregator within each group of `by` values.

    Group column must be carried into the reduced frame by the per_scenario
    expression (e.g. per_scenario=pl.col('value').sum().over('lob')).
    """
    by: str
    metric: ScenarioAggregator

    def init(self): return {}
    def update(self, state, df):
        for grp, sub in df.partition_by(self.by, as_dict=True).items():
            grp_val = grp[0]
            state.setdefault(grp_val, self.metric.init())
            state[grp_val] = self.metric.update(state[grp_val], sub)
        return state
    def finalize(self, state):
        return {grp: self.metric.finalize(sub) for grp, sub in state.items()}
    def canonical_form(self):
        return {"kind": "GroupedAgg", "by": self.by,
                "metric": self.metric.canonical_form()}


@dataclass(frozen=True)
class MultiAgg:
    """Fan out to multiple aggregators over the same reduced frame.

    Each sub-aggregator sees a per-metric slice with columns [scenario_id, value],
    where 'value' is renamed from the metric's column. ScenarioRun.run() uses
    this internally to dispatch one reduced frame to N aggregators.
    """
    metrics: dict[str, ScenarioAggregator]

    def init(self): return {name: m.init() for name, m in self.metrics.items()}
    def update(self, state, df):
        for name, sub_agg in self.metrics.items():
            sub_df = df.select(["scenario_id",
                                pl.col(name).alias("value")])
            state[name] = sub_agg.update(state[name], sub_df)
        return state
    def finalize(self, state):
        return {name: self.metrics[name].finalize(state[name])
                for name in self.metrics}
    def canonical_form(self):
        return {"kind": "MultiAgg",
                "metrics": {name: m.canonical_form()
                            for name, m in sorted(self.metrics.items())}}
```

### 6.3 Batch-equivalence

| Aggregator | Equivalence | Method |
|---|---|---|
| `Sum`, `Count`, `Min`, `Max` | Bit-exact for integers; fp-tolerant for floats | Associative |
| `Mean`, `Std`, `Variance` | fp-tolerant | Parallel Welford |
| `CTE`, `Quantile`, `Median`, `QuantileRank` | Bit-exact | All values buffered; sorted at `finalize` |
| `ArgMin`, `ArgMax` | Bit-exact | Lexicographic tiebreak resolves order ambiguity |
| `GroupedAgg`, `MultiAgg` | Inherit from inner | Trivial |

Acceptance test: `test_aggregators.py::test_batch_equivalence` parametrises across all 15 × `[1, 8, 64]` × a fixed 1000-scenario fixture.

### 6.4 Edge cases

- **Empty input:** `Sum=0`, `Count=0`, `Min/Max=nan`, others `nan` or empty dict.
- **All-NaN values:** Polars semantics (mean of all-NaN is NaN).
- **`CTE.level=1.0`:** mean of entire distribution.
- **`Quantile.levels` not sorted in input:** stored sorted in canonical form.
- **`GroupedAgg(by=..., metric=ArgMax())`:** supported; returns `dict[group_value, ScenarioID]`. Useful for per-LoB / per-cohort worst-scenario drill-down.

### 6.5 User-defined aggregator contract

Plugin authors must:
1. Implement the four Protocol methods.
2. Return `{"kind": <registered_name>, ...params}` from `canonical_form()` with stable, JSON-encodable params.
3. Register before `parse_aggregations` / `from_yaml` is called (typically at import time via the decorator).

Spec includes worked example: `WorstK(k=50)` (mean of worst K scenarios) as the canonical user-defined aggregator demo.

---

## 7. Audit chain

### 7.1 Roll-up structure

```
ScenarioRun.canonical_form()
├── kind: "ScenarioRun"
├── shocks: { sorted_scenario_id → [shock.canonical_form(), ...] }
├── base_tables: { sorted_table_name → table.canonical_form() }
├── aggregations: { sorted_name → metric.canonical_form() }
└── master_seed: int | None
```

Every level uses the same `canonical_bytes()` helper for deterministic JSON encoding.

### 7.2 `canonical_bytes` helper

```python
# bindings/python/gaspatchio_core/_identity.py

import hashlib, json
from typing import Any

def canonical_bytes(form: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for canonical_form dicts."""
    return json.dumps(
        form,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_raise_on_unknown,
    ).encode("utf-8")

def source_sha_of(form: dict[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(canonical_bytes(form)).hexdigest()}"
```

Implementation note: if `Schedule`/`Curve`/`MortalityTable` already have a local equivalent, lift to `_identity.py` and have all four (plus `Table` and `ScenarioRun`) import from it. Verified at implementation time.

### 7.3 `Shock.canonical_form` — added to all 11 subclasses

Base class implementation introspects `__dataclass_fields__`; subclasses with nested shocks recurse.

```python
class Shock(ABC):
    def canonical_form(self) -> dict[str, Any]:
        out = {"kind": type(self).__name__}
        for fld in fields(self):
            out[fld.name] = self._encode_field(getattr(self, fld.name))
        return dict(sorted(out.items()))

    @staticmethod
    def _encode_field(val: Any) -> Any:
        if isinstance(val, Shock): return val.canonical_form()
        if isinstance(val, tuple): return [Shock._encode_field(v) for v in val]
        if isinstance(val, dict): return {k: Shock._encode_field(v) for k, v in sorted(val.items())}
        if isinstance(val, (int, float, str, bool, type(None))): return val
        raise TypeError(f"Shock field {type(val).__name__} not canonical-encodable")
```

Edge cases verified:
- `FilteredShock.where` / `TimeConditionalShock.when` are `dict[str, Any]` → sorted-key encoding ✓
- `PipelineShock.shocks` is `tuple[Shock, ...]` → recurses ✓
- `MaxShock` / `MinShock` carry two nested Shocks → recurses ✓
- `OverrideShock.value` is `Any` → accepts scalar; raises for non-scalar (documented; rare in practice)

### 7.4 `ScenarioRun.canonical_form` implementation

```python
def canonical_form(self) -> dict[str, Any]:
    return {
        "kind": "ScenarioRun",
        "shocks": {
            sid: [s.canonical_form() for s in shocks]
            for sid, shocks in sorted(self.shocks.items())
        },
        "base_tables": {
            name: table.canonical_form()
            for name, table in sorted(self.base_tables.items())
        },
        "aggregations": {
            name: metric.canonical_form()
            for name, metric in sorted(self.aggregations.items())
        },
        "master_seed": self.master_seed,
    }

def source_sha(self) -> str:
    return source_sha_of(self.canonical_form())
```

### 7.5 What is NOT in `canonical_form`

| Excluded | Reason |
|---|---|
| `batch_size` (declared or resolved) | No correctness consequences; runtime metadata only |
| `target_memory_fraction`, `bytes_per_cell` | Runtime tuning |
| `return_full_grid`, `sink_dir` | Output mode, not plan identity |
| `wall_time_s`, `peak_rss_mb` | Observational |

`ScenarioResult` is **not** hashed. It carries `plan_sha` (input identity) plus runtime metadata.

---

## 8. Testing strategy

### 8.1 Test layout

```
bindings/python/tests/scenarios/
├── test_scenario_run.py
├── test_for_each_scenario.py
├── test_aggregators.py
├── test_aggregator_registry.py
├── test_stack_shocked_table.py
├── test_auto_batch.py
├── test_table_identity.py
├── test_shocks_canonical.py
└── test_audit_chain.py
```

### 8.2 Acceptance-criteria mapping (one-to-one with ticket checklist)

| Ticket criterion | Test |
|---|---|
| Batch equivalence (`batch_size ∈ {1, 8, 64}`) | `test_aggregators.py::test_batch_equivalence` (parametrised × 15 aggregators) |
| Per-scenario shocks compose inside a batch | `test_stack_shocked_table.py::test_heterogeneous_shocks_per_batch` |
| `canonical_form` deterministic + sorted | `test_audit_chain.py::test_sha_stability` |
| YAML round-trip | `test_scenario_run.py::test_yaml_roundtrip` (assert identical `source_sha`) |
| Memory bounded by `~batch_size × per_scenario_footprint` | `test_for_each_scenario.py::test_peak_rss_within_batch` (subprocess-based RSS measurement) |
| `master_seed` reproducibility | `test_for_each_scenario.py::test_master_seed_determinism` |
| `return_full_grid` sink layout | `test_for_each_scenario.py::test_sink_dir_layout` |

### 8.3 Property tests (Hypothesis)

1. `Shock.canonical_form` round-trip across all nested shock types.
2. `Table._content_sha` invariance under row-order / column-order permutation.
3. Aggregator batch-equivalence across random batch partitions.

### 8.4 Benchmark

`bindings/python/benchmarks/test_scenariorun_scaling.py` — methodology mirrors `ref/41-backend-portability/41-scenario-scaling-empirical.md` (subprocess + `RUSAGE_CHILDREN.ru_maxrss`). Tests 1k policies × {100, 1k, 10k} scenarios × 240 months × `batch_size ∈ {1, 8, "auto"}` × `return_full_grid ∈ {False, True}`. Result CSV checked into `evals/benchmarks/scenariorun/` for the existing gh-pages dashboard.

### 8.5 Error contracts

| Condition | Exception | Message contract |
|---|---|---|
| Mixed-shape `scenarios` dict | `TypeError` | Names offending key and both shapes seen |
| Empty `scenarios` | `ValueError` | "scenarios must contain at least one entry" |
| `per_scenario` produces >1 row per scenario_id | `ValueError` | "per_scenario for {name} produced N rows for scenario {sid}" |
| Unknown aggregator `kind` in YAML | `ValueError` | "Aggregator {kind!r} not registered. Available: [...]" |
| `register_aggregator` name collision | `ValueError` | "Aggregator {name!r} already registered" |
| `master_seed` set + `model_fn` lacks `drivers=` kwarg | `TypeError` | At call site with note about kwarg requirement |
| Probe fails | `RuntimeError` | Wraps underlying exception with scenario_id |
| `bytes_per_cell` + `batch_size != "auto"` | `ValueError` | "bytes_per_cell only applies when batch_size='auto'" |
| Aggregator `update` raises | `RuntimeError` | Wraps with batch_idx + metric name |

### 8.6 Logging (Loguru, per project standards)

| Event | Level | Fields |
|---|---|---|
| Loop start | INFO | plan_sha, n_scenarios, batch_size, resolution, master_seed |
| Batch complete | DEBUG (INFO with `progress=True`) | batch_idx, wall_ms, peak_rss_mb |
| Probe complete | INFO | per_scenario_bytes, resolved_batch_size |
| Loop end | INFO | wall_time_s, peak_rss_mb, plan_sha |

No `print` anywhere.

### 8.7 Not tested in v0.1

- Subprocess-per-batch isolation (deferred v0.2).
- Cross-Polars-version SHA stability (pin Polars in CI; documented limitation).
- Cross-platform SHA stability (Mac + Linux in CI; Windows not tested).
- Aggregator hot-swap during a run (out of scope).

---

## 9. Tutorial rework (`tutorial/level-5-scenarios/`)

Untyped path rewritten around `ScenarioRun` as primary surface. Typed path (`level-5-scenarios-typed/`) gets a parallel `base/` rewrite only.

### 9.1 Step plan (untyped)

| Step | Replaces | Teaches |
|---|---|---|
| `base/` rewritten | `base/run_scenarios.py` | `ScenarioRun.from_yaml` with three Curves; `metric("net_cf", Sum())`; identity surface |
| `steps/01-scenariorun-basics/` | *(new)* | Plan anatomy; `per_scenario` vs `across_scenario`; `describe()`; `source_sha()` |
| `steps/02-shock-yaml/` | `01-parameter-shocks` | Shocks in YAML inside `ScenarioRun`; tornado chart from aggregator output |
| `steps/03-conditional-shocks/` | `02-conditional-shocks` | `where`/`when`/`pipeline` inside a `ScenarioRun` plan |
| `steps/04-batching-memory/` | *(new)* | `batch_size: int \| "auto"`; `return_full_grid=True` parquet sink; peak RSS measurement |
| `steps/05-aggregators-builtin/` | `04-scenario-comparison` (regulatory narrative merged in) | All 15 starter aggregators; SCR(99.5) example; `GroupedAgg` by LoB; IFRS 17 RA via `QuantileRank` |
| `steps/06-custom-aggregator/` | *(new)* | `@scenario_aggregator` plugin; worked example (`WorstK`); audit-chain identity |
| `steps/07-sensitivity-2d/` | `03-sensitivity` | 1D and 2D sweeps via `ScenarioRun`; replaces standalone `sensitivity_analysis` loops |
| `migration-guide.md` | *(new)* | Old `with_scenarios`+manual-aggregation → `ScenarioRun`; retired entry points |

### 9.2 Scope

Levels 1–4 and `rollforward-patterns/` are untouched. `level-5-scenarios-typed/` gets `base/run_scenarios.py` rewritten only; `why-typed-inputs.md` remains the typed-inputs case study.

---

## 10. `gaspatchio-docs` updates

Docs repo: `~/projects/gaspatchio/gaspatchio-docs/`. MkDocs site with dedicated `Concepts → Scenarios` subtree.

### 10.1 Major rewrites

- `docs/concepts/scenarios.md` — repositions around `ScenarioRun`; adds the decision tree (`ScenarioRun` / `for_each_scenario` / `with_scenarios`).
- `docs/api/scenarios.md` — full new API surface (`ScenarioRun`, `ScenarioMetric`, `for_each_scenario`, 15 aggregators, `@scenario_aggregator`).

### 10.2 New concept pages

- `docs/concepts/audit-chain.md` — Schedule / Curve / MortalityTable / Table / ScenarioRun all have `canonical_form()` + `source_sha()`; how they roll up.
- `docs/concepts/scenarios/scenariorun-basics.md` — plan anatomy, identity, YAML round-trip.
- `docs/concepts/scenarios/aggregators.md` — 15 starters + plugin pattern.
- `docs/concepts/scenarios/cookbook.md` — SCR pack, sensitivity sweep, ESG paths, hedging deltas, IFRS 17 RA.
- `docs/concepts/scenarios/memory-and-seed.md` — Polars allocator caveat (cites polars#23128); `batch_size` guidance; `master_seed` derivation.

### 10.3 Minor updates

- `docs/concepts/scenarios/{shocks,table-sensitivities,what-if,performance,migration,llm-friendly-configs}.md` — add `ScenarioRun` cross-references; keep existing content valid.
- `docs/api/assumptions.md` — adds `Table.canonical_form()` / `Table.source_sha()`.
- `docs/tutorials.md` — Level 5 description updated.

### 10.4 Nav

`mkdocs.yml` adds new concept pages under `Concepts → Scenarios`. Existing pages stay in their positions.

### 10.5 Verified clean

Pre-search of docs repo finds zero references to `Table.apply_shock` (the ticket's doc-bug name) — no cleanup needed.

---

## 11. Decommissioning & simplification

Public-surface changes in `gaspatchio_core/scenarios/`. Breaking-change permission applied.

| Symbol | Action |
|---|---|
| `batch_scenarios` | **retire** — subsumed by `for_each_scenario(batch_size=N)` |
| `sensitivity_analysis` | **internalise** — no longer in `__all__`; tutorials migrate to `ScenarioRun` |
| `describe_scenarios` | **merge into `ScenarioRun.describe()`, retire standalone** — overload accepts dict shape for back-compat callers |
| `with_scenarios` | **keep public** — low-level cross-join primitive; not taught in tutorials |
| `parse_scenario_config`, `parse_shock_config` | **keep public** — declarative entry points used by LLM-generated configs |
| 11 `Shock` subclasses + `Shock` ABC | **keep public** — core extensibility |
| `FilterCondition` | already internal — no change |

### 11.1 Migration footprint

- **Tutorials updated:** `level-5-scenarios/steps/{01,02,03,04}` — already covered by §9.
- **Tests updated:** delete `test_batching.py`; update `test_scenario_benchmarks.py`; rewrite `test_shock_integration.py` (inline sensitivity logic); migrate three scratch fixtures to `ScenarioRun.describe()`.
- **Type stubs:** remove `batch_scenarios`, `describe_scenarios`, `sensitivity_analysis` from `scenarios/__init__.pyi`.

### 11.2 Net effect

Public surface in `gaspatchio_core.scenarios` loses 3 names and gains 6 + 15 aggregator classes + the decorator. Larger surface, but coherent around the typed-plan model.

### 11.3 Internal simplification

`_with_scenarios.py:92-114` validation logic (duplicate IDs, existing-column collision) is lifted to `_validate.py` and shared with `for_each_scenario`'s entry-point checks.

---

## 12. Out of scope

Deferred to follow-up tickets (v0.2 candidates):

- Subprocess-per-batch isolation (`batch_isolation: "subprocess"`) — proper fix for the cross-batch memory-drift hole. Requires `model_fn` pickling machinery.
- Subprocess-based `auto` probe — reuses the subprocess machinery. More accurate per_scenario_bytes measurement (no Polars cross-contamination).
- Rust-side allocator stats (cites polars#27012) — replaces psutil probe with `tikv-jemalloc-ctl::stats.allocated` once Polars exposes the interface.
- Adaptive progressive-doubling batch sizing — start at 1, double after each successful batch, back off on RSS jumps.
- `ParameterShock` integration into batched stacking — currently routed via `drivers=` dict path only.
- Parallel scenario execution within a batch — sequential first; parallelism behind a feature flag later.
- `Custom(init, update, finalize)` aggregator callable shape — rejected for v0.1 due to audit-chain incompatibility; revisit if the plugin registry pattern proves insufficient.
- Aggregator state checkpointing for resumable runs — long-run protection against process kill.
- `Skewness`, `Kurtosis` aggregators — ESG calibration diagnostics; nice-to-have, not blocking.
- `apply_shock` caching across same-shock-set scenarios — add only if benchmarks show it matters.

---

## 13. References

### Primary sources cited

- [pola-rs/polars#23128](https://github.com/pola-rs/polars/issues/23128) — Free RAM not released to OS after heavy dataframe operations (May 2026). Confirms `gc.collect()` / `del` / `malloc_trim` do not release Polars's Rust-side memory.
- [pola-rs/polars#20851](https://github.com/pola-rs/polars/issues/20851) — Memory leakage in with_columns and computation of statistics.
- [pola-rs/polars#22871](https://github.com/pola-rs/polars/issues/22871) — Memory leak (starting from polars 1.28).
- [pola-rs/polars#27012](https://github.com/pola-rs/polars/issues/27012) — No ability to inspect memory usage of jemalloc or mimalloc (open, March 2026). Future Rust-side allocator stats path.
- IFRS 17 §119 — equivalent-confidence-level disclosure requirement for the risk adjustment, justifying `QuantileRank`.
- [NAIC Valuation Manual Jan. 1, 2026 Edition](https://content.naic.org/sites/default/files/pbr_data_valuation_manual_current_edition.pdf) — VM-21 CTE(70) requirement for variable annuity stochastic reserves.
- [CRO Forum — ORSA Stress and Scenario Testing](https://www.thecroforum.org/wp-content/uploads/2023/02/CRO-ORSA-stress-and-scenario-testing.pdf) — reverse stress testing motivation for `ArgMin` / `ArgMax`.

### Internal references

- `ref/41-backend-portability/README.md` — research bundle index.
- `ref/41-backend-portability/41-scenariorun-rollforward-composition.md` — full composition mechanism including batching + shock-stacking.
- `ref/41-backend-portability/41-scenario-memory-design.md` — design recommendation §4.
- `ref/41-backend-portability/41-scenario-scaling-empirical.md` — measurements that justify this work.

### Existing code referenced

- `bindings/python/gaspatchio_core/scenarios/shocks.py` — existing Shock model.
- `bindings/python/gaspatchio_core/scenarios/_sensitivity.py` — `sensitivity_analysis()` (internalising).
- `bindings/python/gaspatchio_core/scenarios/_config.py` — `parse_scenario_config()` / `parse_shock_config()` (extending).
- `bindings/python/gaspatchio_core/scenarios/_batching.py` — `batch_scenarios()` (retiring).
- `bindings/python/gaspatchio_core/scenarios/_with_scenarios.py` — `with_scenarios()` (keep public).
- `bindings/python/gaspatchio_core/scenarios/_describe.py` — `describe_scenarios()` (merging then retiring).
- `bindings/python/gaspatchio_core/assumptions/_api.py:1411` — `Table.with_shock()`.
- `bindings/python/gaspatchio_core/schedule/_schedule.py` — reference `canonical_form` / `source_sha` pattern.
- `bindings/python/gaspatchio_core/curves/_curve.py` — same.
- `bindings/python/gaspatchio_core/mortality/_mortality_table.py` — same.
- Commit `9824f2d` — lazy `with_scenarios` (contributing fix already shipped).
