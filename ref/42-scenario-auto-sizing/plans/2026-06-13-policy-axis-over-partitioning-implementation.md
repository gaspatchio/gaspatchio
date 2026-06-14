# `.over()` partitioning on `run_aggregated` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `run_aggregated` accept `agg.over(by)` for scalar and `Period*` (vector) aggregators, producing tidy/long per-partition output, by sharing the partition machinery with the scenario axis.

**Architecture:** A single-pass partitioned per-period reduce (`group_by([*by, period])`) feeds the existing `_Partitioned` accumulator (`dict[partition_tuple, inner_acc]`). Each `VectorAggregator` is factored into `_period_aggs()` + `_assemble_partial()` so one shared `batch_reduce_over` works for the whole family. `run_aggregated._fold_batch` gains a partition dispatch; partitioned vector outputs are exploded to tidy `{by…, period, alias}` in the finalize. The two `_fold_batch` entry points stay separate (their scalar paths differ); only the partition logic is shared.

**Tech Stack:** Python 3.12, Polars 1.38, numpy, pytest. All commands run from `bindings/python` with `uv run --no-sync`.

**Spec:** `ref/42-scenario-auto-sizing/specs/2026-06-13-policy-axis-over-partitioning-design.md`

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `gaspatchio_core/scenarios/_period_aggregators.py` | per-period vector aggregators | add `_reduce_by_period_over`; factor each into `_period_aggs`/`_assemble_partial`; add base `batch_reduce_over` |
| `gaspatchio_core/scenarios/_period_sketch.py` | sketch-backed per-period aggregators | add `build_period_sketches_over` + sketch `batch_reduce_over` |
| `gaspatchio_core/scenarios/_aggregated.py` | `run_aggregated` driver | `_alias_of` reads `_Partitioned.alias`; relax `_reject_scenario_axis_only`; `_fold_batch` partition dispatch; tidy extract in finalize |
| `tests/scenarios/test_period_aggregators.py` | vector aggregator unit tests | partitioned-reduce + `batch_reduce_over` tests |
| `tests/scenarios/test_period_sketch.py` | sketch unit tests | partitioned sketch test |
| `tests/scenarios/test_run_aggregated.py` | driver tests | scalar/vector `.over()`, reconciliation, multi-col, batched-equiv |

Reference (do not modify, read for the existing pattern): `_metric.py::_Partitioned` (accumulator), `_for_each.py::_fold_batch` lines ~365-424 (the scenario-axis scalar `.over()` fold to mirror minus `scenario_id`).

---

## Task 1: Single-pass partitioned per-period reduce

**Files:**
- Modify: `gaspatchio_core/scenarios/_period_aggregators.py` (add after `_reduce_by_period`)
- Test: `tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scenarios/test_period_aggregators.py` (uses the existing `_with_period` helper; extend it to take a `by` column):

```python
from gaspatchio_core.scenarios._period_aggregators import _reduce_by_period_over


def test_reduce_by_period_over_groups_by_partition_and_period() -> None:
    """One pass returns {partition_tuple: per-period frame}, sorted by period (#over)."""
    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 2.0], [3.0, 4.0], [10.0, 20.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    parts = _reduce_by_period_over(
        frame, "__period", "cf", ("product",), pl.col("cf").sum()
    )
    assert set(parts.keys()) == {("A",), ("B",)}
    assert parts[("A",)]["cf"].to_list() == [4.0, 6.0]  # period 0: 1+3, period 1: 2+4
    assert parts[("B",)]["cf"].to_list() == [10.0, 20.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_period_aggregators.py::test_reduce_by_period_over_groups_by_partition_and_period -v`
Expected: FAIL with `ImportError: cannot import name '_reduce_by_period_over'`

- [ ] **Step 3: Implement** (add directly below `_reduce_by_period` in `_period_aggregators.py`)

```python
def _reduce_by_period_over(
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    *aggs: pl.Expr,
) -> dict[tuple[Any, ...], pl.DataFrame]:
    """Partitioned per-period reduce in ONE pass: ``{partition_tuple: per-period frame}``.

    Like :func:`_reduce_by_period` but the partition column(s) ``by`` join the group key
    (``group_by([*by, period])``). The ``by`` columns are scalar-per-policy, so they ride
    the existing explode. Returns the reduced rows partitioned by ``by`` (key columns
    dropped), each sub-frame sorted by ``period`` — ready to feed ``_Partitioned``.
    """
    reduced = (
        frame.lazy()
        .select(*[pl.col(b) for b in by], pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
        .group_by([*by, period])
        .agg(*aggs)
        .sort([*by, period])
        .collect()
    )
    return reduced.partition_by(*by, as_dict=True, include_key=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/scenarios/test_period_aggregators.py::test_reduce_by_period_over_groups_by_partition_and_period -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): single-pass partitioned per-period reduce helper"
```

---

## Task 2: Factor VectorAggregator + add `batch_reduce_over`

Refactor each vector aggregator's `batch_reduce` into two seams — `_period_aggs()` (the agg expressions) and `_assemble_partial(reduced)` (reduced-frame → partial) — then add ONE shared `batch_reduce_over` on the base. The refactor is behaviour-preserving; the existing `test_period_aggregators.py` suite guards it.

**Files:**
- Modify: `gaspatchio_core/scenarios/_period_aggregators.py` (`VectorAggregator`, `PeriodSum`, `PeriodCount`, `_PeriodExtremum`, `PeriodMean`, `_PeriodMoment`)
- Test: `tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_batch_reduce_over_returns_partition_partials() -> None:
    """batch_reduce_over returns {partition: partial} matching per-partition batch_reduce."""
    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 2.0], [3.0, 4.0], [10.0, 20.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    agg = PeriodSum(column="cf")
    parts = agg.batch_reduce_over(frame, "__period", ("product",))
    assert parts[("A",)].tolist() == [4.0, 6.0]
    assert parts[("B",)].tolist() == [10.0, 20.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_period_aggregators.py::test_batch_reduce_over_returns_partition_partials -v`
Expected: FAIL with `AttributeError: 'PeriodSum' object has no attribute 'batch_reduce_over'`

- [ ] **Step 3: Implement**

3a. On `VectorAggregator` (the base), replace the `batch_reduce`/`within_expr` body with the two seams + both reduce methods:

```python
@dataclass(frozen=True)
class VectorAggregator(_BaseAggregator):
    """Aggregator with per-period vector state. Driver dispatches on batch_reduce."""

    def _period_aggs(self) -> list[pl.Expr]:
        """Per-period aggregation expression(s) for this aggregator. Override."""
        raise NotImplementedError

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        """Turn a period-sorted reduced frame into this aggregator's partial. Override."""
        raise NotImplementedError

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        return self._assemble_partial(
            _reduce_by_period(frame, period, self.column, *self._period_aggs())
        )

    def batch_reduce_over(
        self, frame: pl.DataFrame, period: str, by: tuple[str, ...]
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned reduce: ``{partition_tuple: partial}`` (one group_by pass)."""
        parts = _reduce_by_period_over(
            frame, period, self.column, by, *self._period_aggs()
        )
        return {key: self._assemble_partial(sub) for key, sub in parts.items()}

    def within_expr(self) -> pl.Expr:
        msg = "VectorAggregator reduces via batch_reduce(), not within_expr()."
        raise NotImplementedError(msg)
```

3b. Replace each subclass's `batch_reduce` with `_period_aggs` + `_assemble_partial`:

`PeriodSum`:
```python
    def _period_aggs(self) -> list[pl.Expr]:
        return [pl.col(self.column).sum()]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)
```

`PeriodCount` — identical but `.count()`:
```python
    def _period_aggs(self) -> list[pl.Expr]:
        return [pl.col(self.column).count()]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)
```

`_PeriodExtremum` (drop its `batch_reduce`, keep `_reduce_expr`):
```python
    def _period_aggs(self) -> list[pl.Expr]:
        return [self._reduce_expr(self.column)]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)
```

`PeriodMean`:
```python
    def _period_aggs(self) -> list[pl.Expr]:
        return [
            pl.col(self.column).sum().alias("s"),
            pl.col(self.column).count().alias("c"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return (
            reduced["s"].to_numpy().astype(np.float64),
            reduced["c"].to_numpy().astype(np.float64),
        )
```

`_PeriodMoment`:
```python
    def _period_aggs(self) -> list[pl.Expr]:
        return [
            pl.col(self.column).count().alias("n"),
            pl.col(self.column).mean().alias("mean"),
            (pl.col(self.column).var(ddof=0) * pl.col(self.column).count()).alias("m2"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return (
            reduced["n"].to_numpy().astype(np.float64),
            reduced["mean"].to_numpy().astype(np.float64),
            np.nan_to_num(reduced["m2"].to_numpy().astype(np.float64)),
        )
```

- [ ] **Step 4: Run tests to verify the refactor is behaviour-preserving AND the new method works**

Run: `uv run --no-sync pytest tests/scenarios/test_period_aggregators.py -v`
Expected: PASS (all existing tests still green + the new `batch_reduce_over` test)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): VectorAggregator batch_reduce_over via _period_aggs/_assemble_partial"
```

---

## Task 3: Partitioned sketch reduce (PeriodQuantile/Median/CTE)

**Files:**
- Modify: `gaspatchio_core/scenarios/_period_sketch.py` (add `build_period_sketches_over` + `_PeriodSketchAgg.batch_reduce_over`)
- Test: `tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
def test_period_sketch_batch_reduce_over_partitions() -> None:
    """Sketch reduce partitions into {partition: list[SignedSketch]} (#over)."""
    from gaspatchio_core.scenarios._period_sketch import PeriodMedian

    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 3.0], [5.0, 7.0], [100.0, 200.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    parts = PeriodMedian(column="cf").batch_reduce_over(frame, "__period", ("product",))
    assert set(parts.keys()) == {("A",), ("B",)}
    # product A, period 0: median(1,5)=3; product B, period 0: median(100)=100
    assert parts[("A",)][0].quantile(0.5) == 3.0
    assert parts[("B",)][0].quantile(0.5) == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_period_sketch.py::test_period_sketch_batch_reduce_over_partitions -v`
Expected: FAIL with `AttributeError: ... has no attribute 'batch_reduce_over'`

- [ ] **Step 3: Implement** in `_period_sketch.py`.

3a. Add `build_period_sketches_over` (mirrors `build_period_sketches` with `by` in every group key). After the existing `binned`/`zeros` lazy frames, change their group keys to `[*by, period, ...]` and the horizon/assembly to per-partition. Concretely, add:

```python
def build_period_sketches_over(
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    *,
    relative_accuracy: float,
) -> dict[tuple[Any, ...], list[SignedSketch]]:
    """Per-partition list[SignedSketch]: ``build_period_sketches`` grouped by ``by`` too."""
    parts: dict[tuple[Any, ...], list[SignedSketch]] = {}
    for key, sub in frame.partition_by(*by, as_dict=True, include_key=False).items():
        parts[key] = build_period_sketches(
            sub, period, column, relative_accuracy=relative_accuracy
        )
    return parts
```

> Note: the sketch reduce reuses `build_period_sketches` per partition slice (the histogram build is already vectorised; splitting the small eager batch by partition is cheap). This keeps the bit-exact dual-build gate intact for the partitioned path without duplicating the binning logic. (Single-pass binning is a possible later optimisation; the vector aggregators in Task 2 are the single-pass path.)

3b. Add `batch_reduce_over` to `_PeriodSketchAgg`:

```python
    def batch_reduce_over(
        self, frame: pl.DataFrame, period: str, by: tuple[str, ...]
    ) -> dict[tuple[Any, ...], Any]:
        return build_period_sketches_over(
            frame, period, self.column, by, relative_accuracy=self.relative_accuracy
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/scenarios/test_period_sketch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_sketch.py bindings/python/tests/scenarios/test_period_sketch.py
git commit -m "feat(scenarios): partitioned sketch reduce (PeriodQuantile/Median/CTE .over())"
```

---

## Task 4: Accept `.over()` in `run_aggregated` validation

**Files:**
- Modify: `gaspatchio_core/scenarios/_aggregated.py` (`_alias_of`, `_reject_scenario_axis_only`)
- Test: `tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test** (replace the now-wrong `test_run_aggregated_rejects_over_partition`)

```python
def test_run_aggregated_accepts_scalar_over() -> None:
    """run_aggregated accepts a scalar .over() and partitions the result (#over)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})

    def model(af: ActuarialFrame) -> ActuarialFrame:
        return ActuarialFrame(af._df.with_columns(pl.col("value").alias("pv")))  # noqa: SLF001

    res = run_aggregated(model, mp, [Sum("pv").alias("pv").over("product")])
    out = res.pv.sort("product")
    assert out["product"].to_list() == ["A", "B"]
    assert out["pv"].to_list() == [3.0, 7.0]  # A: 1+2, B: 3+4
```

Also keep `test_run_aggregated_rejects_count` and `test_run_aggregated_rejects_argmax` (they must still pass), and delete `test_run_aggregated_rejects_over_partition`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py::test_run_aggregated_accepts_scalar_over -v`
Expected: FAIL — `_reject_scenario_axis_only` raises `ValueError: run_aggregated does not support .over()`

- [ ] **Step 3: Implement** in `_aggregated.py`.

3a. `_alias_of` — read `_Partitioned.alias`:
```python
def _alias_of(agg: Any) -> str:  # noqa: ANN401
    """Return the alias set on an aggregator (handles _Partitioned), else raise."""
    if isinstance(agg, _Partitioned):
        return agg.alias
    name: str | None = getattr(agg, "alias_", None)
    if not name:
        msg = f"Aggregator {type(agg).__name__} needs .alias(name) for run_aggregated."
        raise ValueError(msg)
    return name
```

3b. `_reject_scenario_axis_only` — unwrap `_Partitioned`, drop the blanket `_Partitioned` rejection, keep Count/`requires_scenario_id`:
```python
def _reject_scenario_axis_only(aggregations: Sequence[Any]) -> None:
    """Reject aggregators that are only well-defined on the scenario axis.

    ``Count`` (counts scenarios) and ``ArgMin``/``ArgMax`` (need scenario identity) are
    inapplicable to the policy axis with or without ``.over()``. ``.over()`` partitioning
    itself IS supported (see _fold_batch).
    """
    for agg in aggregations:
        inner = agg.inner if isinstance(agg, _Partitioned) else agg
        if getattr(inner, "requires_scenario_id", False):
            msg = (
                f"{type(inner).__name__} needs a scenario axis (scenario_id) and is not "
                "applicable to run_aggregated; use it with for_each_scenario."
            )
            raise ValueError(msg)
        if isinstance(inner, Count):
            msg = (
                "Count counts scenarios and is not applicable to run_aggregated (the "
                "policy axis has no scenarios); use Sum/Period* aggregators instead."
            )
            raise ValueError(msg)
```

(The test will still fail after this step until Task 5 implements the fold dispatch — that is expected; this task only unblocks validation. Run the rejection tests to confirm they stay green:)

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py -k "rejects_count or rejects_argmax" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): run_aggregated accepts .over() in validation (Count/ArgMax still rejected)"
```

---

## Task 5: Partition dispatch in `run_aggregated._fold_batch`

**Files:**
- Modify: `gaspatchio_core/scenarios/_aggregated.py` (`_fold_batch`)
- Test: `tests/scenarios/test_run_aggregated.py` (the Task 4 scalar test now passes; add a vector test)

- [ ] **Step 1: Write the failing test**

```python
def test_run_aggregated_vector_over_partitions_per_period() -> None:
    """PeriodSum.over() yields per-partition per-period vectors as accumulator partials."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})
    res = run_aggregated(_toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")])
    # tidy frame asserted in Task 6; here assert it ran without raising and produced a frame
    assert res.cf is not None
```

Add the helper near `_toy_model`:
```python
def _toy_model_with_product(af: ActuarialFrame) -> ActuarialFrame:
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.concat_list([pl.col("value"), pl.col("value") * 2]).alias("cf"),
    )
    return ActuarialFrame(lazy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py::test_run_aggregated_vector_over_partitions_per_period -v`
Expected: FAIL — `_fold_batch` has no `_Partitioned` branch, so `_alias_of` succeeds but `hasattr(agg, "batch_reduce")` is False and the scalar branch calls `agg.within_expr()` → `_Partitioned.within_expr()` → inner vector `NotImplementedError`.

- [ ] **Step 3: Implement** — rewrite the per-aggregator loop in `_fold_batch`:

```python
    for agg in aggregations:
        alias = _alias_of(agg)
        if isinstance(agg, _Partitioned):
            by = agg.by
            if hasattr(agg.inner, "batch_reduce"):
                # vector .over(): {partition: partial} -> _Partitioned.add_input per partition
                agg_col: str = agg.inner.column
                proj_p = proj.with_columns(
                    pl.int_ranges(pl.col(agg_col).list.len()).alias(_PERIOD),
                )
                for key, partial in agg.inner.batch_reduce_over(proj_p, _PERIOD, by).items():
                    accumulators[alias] = agg.add_input(accumulators[alias], (key, partial))
            else:
                # scalar .over(): group_by(by), within_expr per group, add_input per partition
                reduced = proj.group_by(by).agg(agg.inner.within_expr().alias(alias))
                key_pos = [reduced.columns.index(b) for b in by]
                val_pos = reduced.columns.index(alias)
                for row in reduced.iter_rows():
                    key = tuple(row[p] for p in key_pos)
                    accumulators[alias] = agg.add_input(accumulators[alias], (key, row[val_pos]))
            continue
        if hasattr(agg, "batch_reduce"):
            agg_col2: str = agg.column
            proj_p2 = proj.with_columns(
                pl.int_ranges(pl.col(agg_col2).list.len()).alias(_PERIOD),
            )
            partial = agg.batch_reduce(proj_p2, _PERIOD)
            accumulators[alias] = agg.add_input(accumulators[alias], partial)
        else:
            value = proj.select(agg.within_expr().alias(alias)).item()
            accumulators[alias] = agg.add_input(accumulators[alias], value)
```

Keep the existing `has_vector_agg`/`list_col` guard at the top of `_fold_batch`, but compute `has_vector_agg` by unwrapping `_Partitioned`:
```python
    has_vector_agg = any(
        hasattr(a.inner if isinstance(a, _Partitioned) else a, "batch_reduce")
        for a in aggregations
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py -k "over" -v`
Expected: PASS (scalar `.over()` from Task 4 + the vector `.over()` smoke test)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): partition dispatch in run_aggregated._fold_batch"
```

---

## Task 6: Tidy extract for partitioned vectors

**Files:**
- Modify: `gaspatchio_core/scenarios/_aggregated.py` (the `outputs = {...}` finalize in `run_aggregated`)
- Test: `tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test** (the reconciliation anchor)

```python
def test_run_aggregated_vector_over_is_tidy_and_reconciles() -> None:
    """Vector .over() is tidy {by, period, alias} and sums across partitions to the total (#over)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})
    parted = run_aggregated(
        _toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")]
    )
    total = run_aggregated(_toy_model_with_product, mp, [PeriodSum("cf").alias("cf")])
    tidy = parted.cf
    assert tidy.columns == ["product", "period", "cf"]
    # sum over partitions, per period, equals the unpartitioned total vector
    recon = tidy.group_by("period").agg(pl.col("cf").sum()).sort("period")
    assert recon["cf"].to_list() == total.cf.tolist()  # [1+2+3+4, 2+4+6+8] = [10, 20]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py::test_run_aggregated_vector_over_is_tidy_and_reconciles -v`
Expected: FAIL — `parted.cf` is the `_Partitioned.extract_output` DataFrame with a vector-in-cell `cf` column, not `["product","period","cf"]`.

- [ ] **Step 3: Implement** — add a tidy helper and apply it in the finalize.

3a. Add helper to `_aggregated.py`:
```python
def _tidy_partitioned_vector(df: pl.DataFrame, *, by: tuple[str, ...], alias: str) -> pl.DataFrame:
    """Explode a {by..., alias:<per-period vector>} frame into tidy {by..., period, alias}."""
    return (
        df.with_columns(pl.col(alias).cast(pl.List(pl.Float64)))
        .with_columns(pl.int_ranges(pl.col(alias).list.len()).alias("period"))
        .explode([alias, "period"])
        .select([*by, "period", alias])
    )
```

3b. In `run_aggregated`'s finalize, reshape partitioned-vector outputs:
```python
    outputs: dict[str, Any] = {}
    for a, agg in zip(aliases, aggregations, strict=True):
        raw = agg.extract_output(accumulators[a])
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "batch_reduce"):
            raw = _tidy_partitioned_vector(raw, by=agg.by, alias=a)
        outputs[a] = raw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py::test_run_aggregated_vector_over_is_tidy_and_reconciles -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): tidy {by, period, alias} extract for partitioned vectors"
```

---

## Task 7: Multi-column `.over()`, batched-equivalence, and PeriodQuantile

**Files:**
- Test: `tests/scenarios/test_run_aggregated.py`
- Modify (only if a test fails): `gaspatchio_core/scenarios/_aggregated.py`

- [ ] **Step 1: Write the tests**

```python
def test_run_aggregated_over_multi_column() -> None:
    """.over(('product','cohort')) keys partitions by both columns (#over)."""
    mp = pl.DataFrame(
        {
            "value": [1.0, 2.0, 3.0],
            "product": ["A", "A", "B"],
            "cohort": [2020, 2021, 2020],
        }
    )

    def model(af: ActuarialFrame) -> ActuarialFrame:
        return ActuarialFrame(af._df.with_columns(pl.col("value").alias("pv")))  # noqa: SLF001

    res = run_aggregated(model, mp, [Sum("pv").alias("pv").over(("product", "cohort"))])
    out = res.pv.sort(["product", "cohort"])
    assert out["product"].to_list() == ["A", "A", "B"]
    assert out["cohort"].to_list() == [2020, 2021, 2020]
    assert out["pv"].to_list() == [1.0, 2.0, 3.0]


def test_run_aggregated_over_batched_equals_single_batch() -> None:
    """Partitioned output is batch-size-invariant (#over)."""
    mp = pl.DataFrame(
        {"value": [float(i) for i in range(1, 9)], "product": ["A", "B"] * 4}
    )
    full = run_aggregated(
        _toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")], batch_size=8
    )
    batched = run_aggregated(
        _toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")], batch_size=3
    )
    assert full.cf.sort(["product", "period"]).equals(batched.cf.sort(["product", "period"]))


def test_run_aggregated_period_median_over() -> None:
    """PeriodMedian.over() produces per-partition medians (#over)."""
    mp = pl.DataFrame({"value": [1.0, 5.0, 100.0, 300.0], "product": ["A", "A", "B", "B"]})
    res = run_aggregated(
        _toy_model_with_product, mp, [PeriodMedian("cf").alias("med").over("product")]
    )
    med = res.med.filter(pl.col("period") == 0).sort("product")
    assert med["med"].to_list() == [3.0, 200.0]  # median(1,5)=3 ; median(100,300)=200
```

Add `from gaspatchio_core.scenarios import PeriodMedian` to the test imports.

- [ ] **Step 2: Run the tests**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py -k "multi_column or batched_equals or period_median_over" -v`
Expected: the first two PASS (the dispatch already handles them); `period_median_over` PASS if the tidy helper handles the sketch partials. If `period_median_over` FAILs because `PeriodQuantile` returns a `{level: array}` cell (not a single vector), it is OUT OF SCOPE for tidy here — see Step 3.

- [ ] **Step 3: Handle the PeriodQuantile multi-level case (only if needed)**

`PeriodMedian`/`PeriodCTE` return a single per-period vector → the Task 6 tidy helper handles them. `PeriodQuantile` returns `{level: vector}`; its `_Partitioned.extract_output` cell is a dict, which `_tidy_partitioned_vector` cannot cast to `List(Float64)`. If a `PeriodQuantile.over()` test is desired, extend the finalize to detect a dict-valued alias column and emit tidy `{by…, period, level, alias}`:

```python
def _tidy_partitioned_quantile(df: pl.DataFrame, *, by: tuple[str, ...], alias: str) -> pl.DataFrame:
    """Explode {by..., alias:{level: vector}} into tidy {by..., period, level, alias}."""
    rows = []
    for r in df.iter_rows(named=True):
        for level, vec in r[alias].items():
            for period, val in enumerate(vec):
                rows.append({**{b: r[b] for b in by}, "period": period, "level": level, alias: float(val)})
    return pl.DataFrame(rows)
```
and branch on `isinstance(next-cell-value, dict)` in the finalize. **YAGNI:** only implement this if `PeriodQuantile.over()` is actually wanted now; `PeriodMedian`/`PeriodCTE`/all non-quantile vectors work via Task 6. If not needed, assert `PeriodQuantile.over()` raises a clear `NotImplementedError` instead and defer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/scenarios/test_run_aggregated.py -k "over" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/tests/scenarios/test_run_aggregated.py bindings/python/gaspatchio_core/scenarios/_aggregated.py
git commit -m "test(scenarios): multi-col .over(), batched-equivalence, PeriodMedian.over()"
```

---

## Task 8: Full suite + type/lint + docstring

**Files:**
- Modify: `gaspatchio_core/scenarios/_aggregated.py` (docstring of `run_aggregated`: document `.over()`)

- [ ] **Step 1: Update the `run_aggregated` docstring** — document that `aggregations` may include `agg.over(by)` for scalar and `Period*` aggregators, yielding a tidy `{by…, [period], alias}` DataFrame under that alias; note `Count`/`ArgMin`/`ArgMax` remain unsupported.

- [ ] **Step 2: Lint + type-check the changed files**

Run:
```bash
uv run --no-sync ruff check gaspatchio_core/scenarios/_aggregated.py gaspatchio_core/scenarios/_period_aggregators.py gaspatchio_core/scenarios/_period_sketch.py
uv run --no-sync mypy gaspatchio_core/scenarios/_aggregated.py gaspatchio_core/scenarios/_period_aggregators.py gaspatchio_core/scenarios/_period_sketch.py
```
Expected: clean (pre-existing `_audit.read_audit` no-any-return is unrelated; do not touch).

- [ ] **Step 3: Run the full scenarios suite**

Run: `uv run --no-sync pytest tests/scenarios -q`
Expected: all green (the ~494 from the review-fix baseline + the new `.over()` tests).

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py
git commit -m "docs(scenarios): document run_aggregated .over() partitioning"
```

---

## Self-Review

**Spec coverage:**
- §2 scope (vector + scalar `.over()`; Count/ArgMax rejected) → Tasks 4 (validation), 5 (dispatch), 2/3 (reduces).
- §3 tidy output contract → Task 6 (vector), Task 4 test (scalar), Task 7 (multi-col, quantile note).
- §4 architecture (share partition machinery, separate folds) → reuses `_Partitioned`; `_fold_batch` stays driver-local (Task 5).
- §5.1 single-pass reduce → Task 1. §5.2 `batch_reduce_over` → Task 2. §5.3 dispatch → Task 5. §5.4 tidy extract → Task 6.
- §6 perf (single-pass, low cardinality) → Task 1 (one group_by pass); sketch reuses per-partition build (Task 3, noted as acceptable).
- §7 error handling (Count/ArgMax, missing `by` col) → Task 4 + Polars `ColumnNotFound` surfaces at `group_by`.
- §8 testing (reconciliation, scalar/vector shape, multi-col, batched-equiv, quantile) → Tasks 4/6/7.

**Placeholder scan:** Task 7 Step 3 is explicitly YAGNI-gated (implement `PeriodQuantile.over()` tidy only if wanted now, else defer with a clear `NotImplementedError`) — not a hidden placeholder, a scoped decision point. No other TBDs.

**Type consistency:** `batch_reduce_over(frame, period, by) -> dict[tuple, partial]` is consistent across Tasks 2/3/5. `_reduce_by_period_over(frame, period, column, by, *aggs) -> dict[tuple, DataFrame]` consistent Tasks 1/2. `_tidy_partitioned_vector(df, *, by, alias)` consistent Tasks 6/7. `_Partitioned.add_input(acc, (key, value))` matches the `{key: partial}` shape from `batch_reduce_over`.

---

## Execution Handoff

After this plan: scenarios suite green, `.over()` works for scalar + single-vector `Period*` + sketch median/CTE on `run_aggregated`, tidy output, lossless reconciliation. Deferred (out of scope, noted): `PeriodQuantile.over()` multi-level tidy (Task 7 gate), `.over()` on `for_each_scenario`'s vector path, cardinality guard.
