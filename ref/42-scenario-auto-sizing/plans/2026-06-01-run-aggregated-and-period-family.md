# `run_aggregated` + Period Aggregator Family Implementation Plan (Plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the per-period (vector) aggregator family and a `run_aggregated` driver that batches the policy axis, folds each batch to per-period portfolio totals, and returns bounded-memory aggregate results — the same aggregator vocabulary `for_each_scenario` uses.

**Architecture:** Period aggregators are first-class in the existing Aggregator Protocol (`create/add/merge/extract`) with one new axis-agnostic seam, `batch_reduce(frame, period) -> np.ndarray`, that reduces a batch frame to a length-`n_periods` vector via `explode→group_by(period)→agg`. Merges pad-and-add (batches self-size their horizon). `run_aggregated` reuses the `_for_each` loop shape over policy row-slices, dispatching vector aggregators through `batch_reduce` and scalar aggregators (e.g. `Sum`) through the existing `within_expr` path, sized by Plan 1's cgroup-aware budget plus a working-set cap.

**Tech Stack:** Python 3.12, Polars (lazy + `explode`/`group_by`/`int_ranges`), NumPy (vector accumulators), `pytest`. Run tests with `uv run pytest` from `bindings/python/`. **Depends on Plan 1** (`scenarios/_memory.py`: `memory_budget`, `SizingDefaults`, `IrreducibleCellError`).

**Plan series:** Plan 1 ✅ cgroup-aware sizing (dependency). Plan 3 = policy-axis parquet spill sink (C1-tight/C2). Plan 4 = rank-based `PeriodQuantile/Median/CTE`. Spec: `ref/42-scenario-auto-sizing/specs/2026-06-01-unified-aggregation-surface-design.md`.

---

## File Structure

- **Create** `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py` — `VectorAggregator` base + `_pad_add`/`_pad_combine` helpers + `PeriodSum/PeriodCount/PeriodMean/PeriodMin/PeriodMax`. (Sibling of `_aggregators.py` rather than appending — that file is already 771 lines; keep this focused.)
- **Create** `bindings/python/gaspatchio_core/scenarios/_aggregated.py` — `run_aggregated` driver + `AggregatedResult` + the jagged origin guard.
- **Modify** `bindings/python/gaspatchio_core/scenarios/__init__.py` — export the `Period*` family, `run_aggregated`, `AggregatedResult`.
- **Modify** `bindings/python/gaspatchio_core/__init__.py` — top-level re-export of `run_aggregated` + the `Period*` family.
- **Test** `bindings/python/tests/scenarios/test_period_aggregators.py`, `bindings/python/tests/scenarios/test_run_aggregated.py`.

---

## Task 1: `VectorAggregator` base + pad helpers

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/scenarios/test_period_aggregators.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the per-period (vector) aggregator family."""

from __future__ import annotations

import numpy as np

from gaspatchio_core.scenarios._period_aggregators import _pad_add, _pad_combine


def test_pad_add_unequal_lengths():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([10.0, 20.0])
    out = _pad_add(a, b)
    assert out.tolist() == [11.0, 22.0, 3.0]  # tail of a survives


def test_pad_combine_min_keeps_single_batch_tail():
    a = np.array([5.0, 5.0, 5.0])
    b = np.array([2.0, 9.0])
    out = _pad_combine(a, b, np.minimum, np.inf)
    assert out.tolist() == [2.0, 5.0, 5.0]  # period 2 only in a -> a's value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._period_aggregators'`

- [ ] **Step 3: Write minimal implementation**

```python
# bindings/python/gaspatchio_core/scenarios/_period_aggregators.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Per-period (vector) aggregators sharing the Aggregator Protocol.
# ABOUTME: batch_reduce(frame, period) -> length-n_periods vector; merges pad-and-add.

"""Per-period vector aggregators.

These are first-class aggregators (same ``create/add/merge/extract`` Protocol as
``Sum``/``Mean``) with vector-valued state. The one new seam, ``batch_reduce``,
reduces a batch frame to a per-period vector via ``explode -> group_by(period)``;
it is axis-agnostic, so the same aggregator works over policy batches
(``run_aggregated``) and scenario batches (``for_each_scenario``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import polars as pl

from gaspatchio_core.scenarios._aggregators import _BaseAggregator

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _pad_add(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    """Element-wise add two vectors of possibly-unequal length (zero-pad shorter)."""
    n = max(a.shape[0], b.shape[0])
    out = np.zeros(n, dtype=np.float64)
    out[: a.shape[0]] += a
    out[: b.shape[0]] += b
    return out


def _pad_combine(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    op: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]],
    fill: float,
) -> NDArray[np.float64]:
    """Element-wise combine via ``op`` (np.minimum/np.maximum); ``fill`` pads the gap.

    A period present in only one operand keeps that operand's value (the other side
    is the identity ``fill``: +inf for min, -inf for max).
    """
    n = max(a.shape[0], b.shape[0])
    ap = np.full(n, fill, dtype=np.float64)
    bp = np.full(n, fill, dtype=np.float64)
    ap[: a.shape[0]] = a
    bp[: b.shape[0]] = b
    return op(ap, bp)


@dataclass(frozen=True)
class VectorAggregator(_BaseAggregator):
    """Aggregator with per-period vector state.

    Shares the Protocol; the driver dispatches on the presence of ``batch_reduce``.
    ``within_expr`` is intentionally unsupported (the vector path never calls it).
    """

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        """Reduce one batch frame to a per-period vector. Override in subclasses."""
        raise NotImplementedError

    def within_expr(self) -> pl.Expr:
        msg = "VectorAggregator reduces via batch_reduce(), not within_expr()."
        raise NotImplementedError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): VectorAggregator base + pad-add/pad-combine helpers"
```

---

## Task 2: `PeriodSum` — the canonical per-period reduction (jagged-robust)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_aggregators.py
import polars as pl

from gaspatchio_core.scenarios._period_aggregators import PeriodSum


def _frame_with_lists(lists: list[list[float]]) -> pl.DataFrame:
    return pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)})


def test_period_sum_equal_lengths():
    df = _frame_with_lists([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]])
    agg = PeriodSum("cf")
    period = "__period"
    df2 = df.with_columns(pl.int_ranges(pl.col("cf").list.len()).alias(period))
    vec = agg.batch_reduce(df2, period)
    assert vec.tolist() == [11.0, 22.0, 33.0]


def test_period_sum_jagged_aligns_by_index():
    # policy 0 has 3 periods, policy 1 has 2 -> period 2 only gets policy 0
    df = _frame_with_lists([[1.0, 2.0, 3.0], [10.0, 20.0]])
    agg = PeriodSum("cf")
    df2 = df.with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    vec = agg.batch_reduce(df2, "__period")
    assert vec.tolist() == [11.0, 22.0, 3.0]


def test_period_sum_merge_is_pad_add():
    agg = PeriodSum("cf")
    a = agg.add_input(agg.create_accumulator(), np.array([1.0, 2.0, 3.0]))
    b = agg.add_input(agg.create_accumulator(), np.array([10.0, 20.0]))
    merged = agg.merge_accumulators(a, b)
    assert agg.extract_output(merged).tolist() == [11.0, 22.0, 3.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k period_sum -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodSum'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_aggregators.py
from gaspatchio_core.scenarios._aggregators import scenario_aggregator


@scenario_aggregator("PeriodSum")
@dataclass(frozen=True)
class PeriodSum(VectorAggregator):
    """Per-period portfolio total: sum across the batched axis at each period index."""

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        out = (
            frame.lazy()
            .select(pl.col(period), pl.col(self.column))
            .explode([period, self.column])
            .group_by(period)
            .agg(pl.col(self.column).sum())
            .sort(period)
            .collect()
        )
        return out[self.column].to_numpy().astype(np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _pad_add(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodSum", "column": self.column}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k period_sum -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): PeriodSum (jagged-robust per-period reduction, pad-add merge)"
```

---

## Task 3: `PeriodCount`, `PeriodMin`, `PeriodMax`

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_aggregators.py
from gaspatchio_core.scenarios._period_aggregators import PeriodCount, PeriodMax, PeriodMin


def _reduced(agg, lists):
    df = _frame_with_lists(lists).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    return agg.batch_reduce(df, "__period")


def test_period_count_counts_per_period():
    assert _reduced(PeriodCount("cf"), [[1.0, 2.0, 3.0], [10.0, 20.0]]).tolist() == [2, 2, 1]


def test_period_min_max():
    assert _reduced(PeriodMin("cf"), [[1.0, 8.0], [5.0, 2.0]]).tolist() == [1.0, 2.0]
    assert _reduced(PeriodMax("cf"), [[1.0, 8.0], [5.0, 2.0]]).tolist() == [5.0, 8.0]


def test_period_min_merge_keeps_tail():
    agg = PeriodMin("cf")
    a = agg.add_input(agg.create_accumulator(), np.array([5.0, 5.0, 5.0]))
    b = agg.add_input(agg.create_accumulator(), np.array([2.0, 9.0]))
    assert agg.extract_output(agg.merge_accumulators(a, b)).tolist() == [2.0, 5.0, 5.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k "period_count or period_min or period_max" -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodCount'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_aggregators.py
@scenario_aggregator("PeriodCount")
@dataclass(frozen=True)
class PeriodCount(VectorAggregator):
    """Per-period count of contributing (non-null) values across the batched axis."""

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        out = (
            frame.lazy()
            .select(pl.col(period), pl.col(self.column))
            .explode([period, self.column])
            .group_by(period)
            .agg(pl.col(self.column).count())
            .sort(period)
            .collect()
        )
        return out[self.column].to_numpy().astype(np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _pad_add(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodCount", "column": self.column}


@dataclass(frozen=True)
class _PeriodExtremum(VectorAggregator):
    """Shared min/max logic. ``_op``/``_fill``/``_polars`` set by subclasses."""

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def _reduce_expr(self, col: str) -> pl.Expr:  # overridden
        raise NotImplementedError

    @property
    def _fill(self) -> float:  # overridden
        raise NotImplementedError

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401  # overridden
        raise NotImplementedError

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        out = (
            frame.lazy()
            .select(pl.col(period), pl.col(self.column))
            .explode([period, self.column])
            .group_by(period)
            .agg(self._reduce_expr(self.column))
            .sort(period)
            .collect()
        )
        return out[self.column].to_numpy().astype(np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return self._combine(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return self._combine(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state


@scenario_aggregator("PeriodMin")
@dataclass(frozen=True)
class PeriodMin(_PeriodExtremum):
    """Per-period minimum across the batched axis."""

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).min()

    @property
    def _fill(self) -> float:
        return np.inf

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_combine(a, b, np.minimum, np.inf)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMin", "column": self.column}


@scenario_aggregator("PeriodMax")
@dataclass(frozen=True)
class PeriodMax(_PeriodExtremum):
    """Per-period maximum across the batched axis."""

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).max()

    @property
    def _fill(self) -> float:
        return -np.inf

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_combine(a, b, np.maximum, -np.inf)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMax", "column": self.column}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k "period_count or period_min or period_max" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): PeriodCount/PeriodMin/PeriodMax (pad-aware min/max merge)"
```

---

## Task 4: `PeriodMean` — exact `Sum/Count` composite (batch-size-invariant)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_aggregators.py
from gaspatchio_core.scenarios._period_aggregators import PeriodMean


def test_period_mean_equals_sum_over_count():
    df = _frame_with_lists([[2.0, 4.0], [4.0, 8.0]]).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    agg = PeriodMean("cf")
    acc = agg.add_input(agg.create_accumulator(), agg.batch_reduce(df, "__period"))
    assert agg.extract_output(acc).tolist() == [3.0, 6.0]


def test_period_mean_exact_across_batch_split():
    """Mean of all rows == mean computed by merging two row-batches (exactly)."""
    rows = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
    agg = PeriodMean("cf")

    def reduce(subset):
        df = _frame_with_lists(subset).with_columns(
            pl.int_ranges(pl.col("cf").list.len()).alias("__period")
        )
        return agg.batch_reduce(df, "__period")

    whole = agg.add_input(agg.create_accumulator(), reduce(rows))
    split = agg.merge_accumulators(
        agg.add_input(agg.create_accumulator(), reduce(rows[:1])),
        agg.add_input(agg.create_accumulator(), reduce(rows[1:])),
    )
    assert agg.extract_output(whole).tolist() == agg.extract_output(split).tolist()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k period_mean -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodMean'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_aggregators.py
@scenario_aggregator("PeriodMean")
@dataclass(frozen=True)
class PeriodMean(VectorAggregator):
    """Per-period mean across the batched axis.

    State is ``(sum_vec, count_vec)`` — both exactly additive — so the result is
    batch-size-invariant (no Welford needed; mean is extracted as sum/count).
    """

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return (np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        out = (
            frame.lazy()
            .select(pl.col(period), pl.col(self.column))
            .explode([period, self.column])
            .group_by(period)
            .agg(pl.col(self.column).sum().alias("s"), pl.col(self.column).count().alias("c"))
            .sort(period)
            .collect()
        )
        return (out["s"].to_numpy().astype(np.float64), out["c"].to_numpy().astype(np.float64))

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        s, c = state
        vs, vc = value
        return (_pad_add(s, vs), _pad_add(c, vc))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return (_pad_add(a[0], b[0]), _pad_add(a[1], b[1]))

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        s, c = state
        out = np.full(s.shape[0], np.nan, dtype=np.float64)
        nonzero = c > 0
        out[nonzero] = s[nonzero] / c[nonzero]
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMean", "column": self.column}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -v`
Expected: PASS (all in file)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): PeriodMean as exact Sum/Count composite (K-invariant)"
```

---

## Task 5: `AggregatedResult`

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_aggregated.py`
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/scenarios/test_run_aggregated.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for run_aggregated + AggregatedResult."""

from __future__ import annotations

import numpy as np

from gaspatchio_core.scenarios._aggregated import AggregatedResult


def test_aggregated_result_attribute_access():
    res = AggregatedResult(
        aggregations={"net_cf": np.array([1.0, 2.0]), "pv": 7.0},
        n_policies=10, n_periods=2, batch_size=10, wall_time_s=0.1, peak_rss_mb=12.0,
    )
    assert res.net_cf.tolist() == [1.0, 2.0]
    assert res.pv == 7.0
    assert res.n_policies == 10


def test_aggregated_result_missing_alias_raises_attributeerror():
    res = AggregatedResult(
        aggregations={}, n_policies=1, n_periods=1, batch_size=1, wall_time_s=0.0, peak_rss_mb=None
    )
    import pytest

    with pytest.raises(AttributeError):
        _ = res.does_not_exist
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k aggregated_result -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._aggregated'`

- [ ] **Step 3: Write minimal implementation**

```python
# bindings/python/gaspatchio_core/scenarios/_aggregated.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: run_aggregated -- policy-axis aggregate driver (bounded memory).
# ABOUTME: Mirrors for_each_scenario's loop over policy row-slices; AggregatedResult.

"""Bounded-memory per-period aggregation for a single (non-scenario) run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AggregatedResult:
    """Typed output of :func:`run_aggregated`. Aliases are attribute-accessible."""

    aggregations: dict[str, Any]
    n_policies: int
    n_periods: int
    batch_size: int
    wall_time_s: float
    peak_rss_mb: float | None

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        # Only consulted when normal attribute lookup misses (i.e. for aliases).
        if name.startswith("__"):
            raise AttributeError(name)
        aggregations = object.__getattribute__(self, "aggregations")
        if name in aggregations:
            return aggregations[name]
        raise AttributeError(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k aggregated_result -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): AggregatedResult with alias attribute access"
```

---

## Task 6: `run_aggregated` — single-batch path (dispatch + fold)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregated.py`
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_run_aggregated.py
import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import PeriodSum, Sum
from gaspatchio_core.scenarios._aggregated import run_aggregated


def _toy_model(af: ActuarialFrame) -> ActuarialFrame:
    # cf[t] = value * (t+1) for t in 0..2 ; pv = value (a per-policy scalar)
    df = af._df.with_columns(  # noqa: SLF001
        pl.concat_list([pl.col("value"), pl.col("value") * 2, pl.col("value") * 3]).alias("cf"),
        pl.col("value").alias("pv"),
    )
    return ActuarialFrame(df)


def test_run_aggregated_single_batch_matches_full():
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]})  # 4 policies
    res = run_aggregated(
        _toy_model, mp,
        aggregations=[PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")],
        batch_size=4,  # one batch
    )
    # cf totals per period: sum(value)*[1,2,3] = 10 * [1,2,3]
    assert res.cf.tolist() == [10.0, 20.0, 30.0]
    assert res.pv == 10.0
    assert res.n_policies == 4
    assert res.n_periods == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k single_batch -v`
Expected: FAIL — `ImportError: cannot import name 'run_aggregated'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_aggregated.py
import time
from typing import TYPE_CHECKING, Callable, Literal, Sequence

import polars as pl

from gaspatchio_core.frame import ActuarialFrame

if TYPE_CHECKING:
    from gaspatchio_core.scenarios._metric import Aggregator

_PERIOD = "__period"


def _alias_of(agg: Any) -> str:  # noqa: ANN401
    name = getattr(agg, "alias_", None)
    if not name:
        msg = f"Aggregator {type(agg).__name__} needs .alias(name) for run_aggregated."
        raise ValueError(msg)
    return name


def _fold_batch(
    proj: pl.DataFrame,
    aggregations: Sequence[Any],
    accumulators: dict[str, Any],
) -> None:
    """Fold one collected batch frame into every aggregator's accumulator."""
    has_lists = any(dt == pl.List(pl.Float64) for dt in proj.schema.values())
    proj_p = (
        proj.with_columns(
            pl.int_ranges(
                pl.col(next(c for c, dt in proj.schema.items() if dt == pl.List(pl.Float64))).list.len()
            ).alias(_PERIOD)
        )
        if has_lists
        else proj
    )
    for agg in aggregations:
        alias = _alias_of(agg)
        if hasattr(agg, "batch_reduce"):  # vector aggregator
            partial = agg.batch_reduce(proj_p, _PERIOD)
            accumulators[alias] = agg.add_input(accumulators[alias], partial)
        else:  # scalar aggregator (e.g. Sum) over a per-policy scalar column
            value = proj.select(agg.within_expr().alias(alias)).item()
            accumulators[alias] = agg.add_input(accumulators[alias], value)


def run_aggregated(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    aggregations: Sequence[Any],
    *,
    batch_size: int | Literal["auto"] = "auto",
    align: Literal["calendar", "duration"] | None = None,
) -> AggregatedResult:
    """Run ``model_fn`` over policy batches; fold each to per-period aggregates.

    ``aggregations`` is a list of aliased aggregators (same shape as
    ``for_each_scenario``); vector ``Period*`` aggregators yield per-period
    ndarrays, scalar aggregators (e.g. ``Sum``) yield portfolio scalars.
    """
    if model_points.height == 0:
        msg = "model_points is empty."
        raise ValueError(msg)
    aliases = [_alias_of(a) for a in aggregations]
    if len(set(aliases)) != len(aliases):
        msg = f"Aggregator aliases must be unique; got {aliases}."
        raise ValueError(msg)

    n_policies = model_points.height
    resolved = n_policies if batch_size == "auto" else int(batch_size)
    accumulators = {a: agg.create_accumulator() for a, agg in zip(aliases, aggregations, strict=True)}

    started = time.perf_counter()
    n_periods = 0
    for start in range(0, n_policies, resolved):
        batch = model_points.slice(start, resolved)
        proj = model_fn(ActuarialFrame(batch))._df.collect()  # noqa: SLF001
        list_cols = [c for c, dt in proj.schema.items() if dt == pl.List(pl.Float64)]
        if list_cols:
            n_periods = max(n_periods, int(proj.select(pl.col(list_cols[0]).list.len().max()).item()))
        _fold_batch(proj, aggregations, accumulators)
        del proj

    outputs = {a: agg.extract_output(accumulators[a]) for a, agg in zip(aliases, aggregations, strict=True)}
    return AggregatedResult(
        aggregations=outputs,
        n_policies=n_policies,
        n_periods=n_periods,
        batch_size=resolved,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k single_batch -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): run_aggregated single-batch fold (vector+scalar dispatch)"
```

---

## Task 7: policy batching + batched == full equivalence

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregated.py` (already loops; this task proves multi-batch correctness + peak-RSS capture)
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_run_aggregated.py
import pytest


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_batched_equals_full(k):
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    full = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")], batch_size=10)
    batched = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")], batch_size=k)
    assert np.allclose(batched.cf, full.cf, atol=1e-6)
    assert abs(batched.pv - full.pv) < 1e-6
    assert batched.n_periods == 3


def test_peak_rss_recorded():
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size=1)
    assert res.peak_rss_mb is None or res.peak_rss_mb >= 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k "batched_equals_full or peak_rss" -v`
Expected: PASS for equivalence (loop already correct), but `test_peak_rss_recorded` will PASS trivially (None). Add the peak-RSS capture so it is meaningful.

- [ ] **Step 3: Write minimal implementation**

Reuse `_for_each._collect_with_peak` to capture the per-batch transient peak. In `_aggregated.py`, replace the collect line and track the high-water mark:

```python
from gaspatchio_core.scenarios._for_each import _collect_with_peak
```

In the loop, replace `proj = model_fn(...)._df.collect()` with:

```python
        lazy = model_fn(ActuarialFrame(batch))._df  # noqa: SLF001
        proj, batch_peak = _collect_with_peak(lazy)
        max_batch_peak = max(max_batch_peak, batch_peak)
```

Initialise `max_batch_peak = 0` before the loop, and set the result field:

```python
        peak_rss_mb=(max_batch_peak / (1024 * 1024)) if max_batch_peak else None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): multi-batch run_aggregated + per-batch peak-RSS capture"
```

---

## Task 8: jagged origin guard (`align`)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregated.py`
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_run_aggregated.py
from dataclasses import dataclass as _dc


@_dc
class _StubSchedule:
    _kind: str
    n_periods: int


def _inception_model(af: ActuarialFrame) -> ActuarialFrame:
    out = _toy_model(af)
    object.__setattr__(out, "_projection", _StubSchedule(_kind="from_inception", n_periods=3))
    return out


def test_inception_aligned_requires_align_duration():
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    with pytest.raises(ValueError, match="DURATION"):
        run_aggregated(_inception_model, mp, [PeriodSum("cf").alias("cf")], batch_size=2)


def test_inception_aligned_proceeds_with_align_duration():
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(
        _inception_model, mp, [PeriodSum("cf").alias("cf")], batch_size=2, align="duration"
    )
    assert res.cf.tolist() == [3.0, 6.0, 9.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k inception -v`
Expected: FAIL — no guard yet; the first test does not raise.

- [ ] **Step 3: Write minimal implementation**

In `run_aggregated`, after the FIRST batch's `model_fn` produces `out_af` (refactor so the first projection is built once and inspected), add the guard. Simplest: inspect the schedule on the first projected frame inside the loop on `start == 0`:

```python
        proj_af = model_fn(ActuarialFrame(batch))
        if start == 0:
            _check_period_origin(proj_af, align)
        lazy = proj_af._df  # noqa: SLF001
        proj, batch_peak = _collect_with_peak(lazy)
```

And the guard helper:

```python
def _check_period_origin(af: ActuarialFrame, align: str | None) -> None:
    """Reject inception-aligned (per-policy-origin) timelines unless align='duration'.

    Index-aligned summation is calendar-correct only when policies share a period
    origin (from_calendar_grid / per_policy_grid). from_inception's index is policy
    DURATION; summing across policies then mixes calendar periods.
    """
    schedule = getattr(af, "_projection", None)
    kind = getattr(schedule, "_kind", None)
    if kind == "from_inception" and align != "duration":
        msg = (
            "Inception-aligned timeline: the period index is policy DURATION, not "
            "calendar time, so summing across policies mixes calendar periods. Pass "
            "align='duration' to aggregate by duration, or rebuild the projection with "
            "a shared valuation grid (per_policy=False) for calendar totals."
        )
        raise ValueError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): jagged calendar-vs-duration origin guard (align=)"
```

---

## Task 9: `batch_size="auto"` — cgroup-aware budget + working-set cap

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregated.py`
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_run_aggregated.py
from unittest.mock import patch


def test_auto_sizes_from_working_set_target_and_is_equivalent():
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 21)]})  # 20 policies
    # Force a tiny working-set target so 'auto' splits into several batches, then
    # assert the aggregate still equals the single-batch result.
    full = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size=20)
    with patch("gaspatchio_core.scenarios._aggregated._WORKING_SET_TARGET_BYTES", 1):
        auto = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert auto.batch_size < 20  # actually batched
    assert np.allclose(auto.cf, full.cf, atol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k auto_sizes -v`
Expected: FAIL — `AttributeError: ... has no attribute '_WORKING_SET_TARGET_BYTES'` (auto currently = n_policies).

- [ ] **Step 3: Write minimal implementation**

Add a module constant and an auto-sizing helper that runs ONE seed batch, measures the transient peak, derives `per_cell`, and sizes `B = min(memory_cap, working_set_cap, n_policies)`. (Two-point affine refinement is deferred per the spec sequencing; the seed here is large enough to amortise fixed cost, and Plan 1's memory cap + Task 10's gate bound overshoot.)

```python
from gaspatchio_core.scenarios import _memory

_WORKING_SET_TARGET_BYTES = 384 * 1024**2  # ~U-floor working-set; see spec 2.1


def _resolve_auto(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    *,
    fraction: float = 0.5,
) -> tuple[int, pl.DataFrame, int]:
    """Run one seed batch, measure per-policy peak, return (B, seed_proj, seed_size).

    The seed batch is real work (its aggregates are folded by the caller), not a
    throwaway probe.
    """
    n_policies = model_points.height
    seed_size = min(n_policies, max(1, n_policies // 10))  # ~10% seed, >=1
    seed_lazy = model_fn(ActuarialFrame(model_points.slice(0, seed_size)))._df  # noqa: SLF001
    seed_proj, seed_peak = _collect_with_peak(seed_lazy)
    per_cell = max(1, seed_peak // max(1, seed_size))
    budget = _memory.memory_budget(fraction)
    memory_cap = max(1, budget // per_cell)
    working_cap = max(1, _WORKING_SET_TARGET_BYTES // per_cell)
    if memory_cap < 1 and seed_size >= 1:  # one cell already over budget
        from gaspatchio_core.scenarios._memory import IrreducibleCellError

        msg = "one policy's projection exceeds the memory budget; reduce horizon/columns."
        raise IrreducibleCellError(msg)
    b = min(memory_cap, working_cap, n_policies)
    return int(max(1, b)), seed_proj, seed_size
```

Then wire it into `run_aggregated`: when `batch_size == "auto"`, call `_resolve_auto`, fold the returned `seed_proj` immediately (don't recompute it), and loop the REMAINDER from `seed_size` in steps of `B`. Keep the explicit-int path unchanged.

```python
    if batch_size == "auto":
        resolved, seed_proj, seed_size = _resolve_auto(model_fn, model_points)
        _check_period_origin_df(seed_proj, align)  # guard on the seed's schema if available
        list_cols = [c for c, dt in seed_proj.schema.items() if dt == pl.List(pl.Float64)]
        if list_cols:
            n_periods = max(n_periods, int(seed_proj.select(pl.col(list_cols[0]).list.len().max()).item()))
        _fold_batch(seed_proj, aggregations, accumulators)
        del seed_proj
        loop_start = seed_size
    else:
        resolved = int(batch_size)
        loop_start = 0
    for start in range(loop_start, n_policies, resolved):
        ...  # existing loop body
```

> **Note:** for the explicit-int path keep the Task 8 origin guard on the first batch. For the auto path the guard runs on the seed projection — but the `_StubSchedule` used in tests is attached to the `ActuarialFrame`, not the collected DataFrame; in `_resolve_auto` keep a reference to the `ActuarialFrame` and pass it to `_check_period_origin` before collecting. Adjust `_resolve_auto` to build the seed `ActuarialFrame` once, guard it, then collect.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregated.py bindings/python/tests/scenarios/test_run_aggregated.py
git commit -m "feat(scenarios): run_aggregated batch_size=auto (cgroup budget + working-set cap)"
```

---

## Task 10: public exports + shared-surface smoke + small-N gate

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py`, `bindings/python/gaspatchio_core/__init__.py`
- Test: `bindings/python/tests/scenarios/test_run_aggregated.py`, `bindings/python/tests/scenarios/test_public_surface.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_run_aggregated.py
def test_top_level_exports():
    import gaspatchio_core as gsp

    assert hasattr(gsp, "run_aggregated")
    for name in ("PeriodSum", "PeriodCount", "PeriodMean", "PeriodMin", "PeriodMax"):
        assert hasattr(gsp, name)


def test_small_n_single_batch_is_no_op():
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
    res = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert res.batch_size == 3  # everything fit -> one batch


def test_period_aggregator_runs_in_for_each_scenario():
    """Shared-surface: a Period* aggregator works unchanged on the scenario axis."""
    from gaspatchio_core.scenarios import for_each_scenario

    af = ActuarialFrame(_toy_model(ActuarialFrame(pl.DataFrame({"value": [1.0, 2.0]})))._df.collect())
    # for_each_scenario folds via batch_reduce identically; one scenario id, no shocks.
    result = for_each_scenario(
        af, [1], model_fn=lambda a, **_: a, aggregations=[PeriodSum("cf").alias("cf")],
    )
    assert np.asarray(result.aggregations["cf"]).tolist() == [3.0, 6.0, 9.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_run_aggregated.py -k "top_level_exports or small_n or for_each_scenario" -v`
Expected: FAIL — `AttributeError: module 'gaspatchio_core' has no attribute 'run_aggregated'`; the for_each_scenario smoke may fail if the loop's scalar fold path doesn't recognise `batch_reduce` (see note).

- [ ] **Step 3: Write minimal implementation**

1. In `scenarios/__init__.py`, import and add to `__all__`:

```python
from gaspatchio_core.scenarios._aggregated import AggregatedResult, run_aggregated
from gaspatchio_core.scenarios._period_aggregators import (
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodSum,
)
```
Add each name to `__all__`.

2. In `gaspatchio_core/__init__.py`, re-export the same names (find the existing block that re-exports scenario symbols, or add):

```python
from gaspatchio_core.scenarios import (
    AggregatedResult,
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodSum,
    run_aggregated,
)
```
Add them to the top-level `__all__`.

3. If `test_period_aggregator_runs_in_for_each_scenario` fails because `for_each_scenario` calls `within_expr()` on vector aggregators, add a dispatch in `_for_each.py`'s fold (where it builds `within_exprs` / iterates rows): if `hasattr(member_agg, "batch_reduce")`, reduce that batch's collected `proj_eager` via `batch_reduce` (compute the `__period` column once) and `add_input` the vector, instead of the scalar `group_by(...).agg(within_expr)` path. Gate it so scalar aggregators are unchanged. (This is the shared-surface seam working on the scenario axis — spec §2.2 gate 7.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/ -q`
Expected: PASS (all green). Then:
Run: `cd bindings/python && uv run mypy gaspatchio_core/scenarios/_period_aggregators.py gaspatchio_core/scenarios/_aggregated.py && uv run ruff check gaspatchio_core/scenarios/`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/__init__.py bindings/python/gaspatchio_core/__init__.py bindings/python/gaspatchio_core/scenarios/_for_each.py bindings/python/tests/
git commit -m "feat(scenarios): export run_aggregated + Period* family; shared-surface seam"
```

---

## Task 11: `PeriodVariance` / `PeriodStd` (vector Welford-Chan)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_period_aggregators.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_aggregators.py
from gaspatchio_core.scenarios._period_aggregators import PeriodStd, PeriodVariance


def test_period_variance_matches_numpy():
    rows = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]]
    df = _frame_with_lists(rows).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    agg = PeriodVariance("cf")
    got = agg.extract_output(agg.add_input(agg.create_accumulator(), agg.batch_reduce(df, "__period")))
    col0 = np.array([1.0, 2.0, 3.0, 4.0])
    col1 = np.array([10.0, 20.0, 30.0, 40.0])
    assert np.allclose(got, [np.var(col0, ddof=1), np.var(col1, ddof=1)])


def test_period_variance_merge_matches_full():
    rows = [[1.0], [2.0], [3.0], [4.0], [5.0]]
    agg = PeriodVariance("cf")

    def reduce(sub):
        df = _frame_with_lists(sub).with_columns(
            pl.int_ranges(pl.col("cf").list.len()).alias("__period")
        )
        return agg.batch_reduce(df, "__period")

    whole = agg.add_input(agg.create_accumulator(), reduce(rows))
    split = agg.merge_accumulators(
        agg.add_input(agg.create_accumulator(), reduce(rows[:2])),
        agg.add_input(agg.create_accumulator(), reduce(rows[2:])),
    )
    assert np.allclose(agg.extract_output(whole), agg.extract_output(split))


def test_period_std_is_sqrt_variance():
    rows = [[1.0], [2.0], [3.0], [4.0]]
    df = _frame_with_lists(rows).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    v, s = PeriodVariance("cf"), PeriodStd("cf")
    av = v.extract_output(v.add_input(v.create_accumulator(), v.batch_reduce(df, "__period")))
    asd = s.extract_output(s.add_input(s.create_accumulator(), s.batch_reduce(df, "__period")))
    assert np.allclose(asd, np.sqrt(av))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -k "variance or std" -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodVariance'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_aggregators.py
def _welford_merge_vec(a: Any, b: Any) -> Any:  # noqa: ANN401
    """Elementwise Welford-Chan merge of two ``(n, mean, m2)`` vector states.

    Padding with zeros is the identity: a period present in only one operand keeps
    that operand's moments (the other side has n=0).
    """
    (na, ma, m2a), (nb, mb, m2b) = a, b
    length = max(na.shape[0], nb.shape[0])

    def fit(x: Any) -> Any:  # noqa: ANN401
        out = np.zeros(length, dtype=np.float64)
        out[: x.shape[0]] = x
        return out

    na, ma, m2a = fit(na), fit(ma), fit(m2a)
    nb, mb, m2b = fit(nb), fit(mb), fit(m2b)
    n = na + nb
    safe = n > 0
    delta = mb - ma
    ratio_b = np.divide(nb, n, out=np.zeros(length), where=safe)
    ratio_ab = np.divide(na * nb, n, out=np.zeros(length), where=safe)
    mean = ma + delta * ratio_b
    m2 = m2a + m2b + delta * delta * ratio_ab
    return (n, mean, m2)


@dataclass(frozen=True)
class _PeriodMoment(VectorAggregator):
    """Shared per-period ``(n, mean, m2)`` Welford state for Variance/Std."""

    def create_accumulator(self) -> Any:  # noqa: ANN401
        z = np.zeros(0, dtype=np.float64)
        return (z, z.copy(), z.copy())

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        out = (
            frame.lazy()
            .select(pl.col(period), pl.col(self.column))
            .explode([period, self.column])
            .group_by(period)
            .agg(
                pl.col(self.column).count().alias("n"),
                pl.col(self.column).mean().alias("mean"),
                (pl.col(self.column).var(ddof=0) * pl.col(self.column).count()).alias("m2"),
            )
            .sort(period)
            .collect()
        )
        n = out["n"].to_numpy().astype(np.float64)
        mean = out["mean"].to_numpy().astype(np.float64)
        m2 = np.nan_to_num(out["m2"].to_numpy().astype(np.float64))  # var() is null at count==1
        return (n, mean, m2)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _welford_merge_vec(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _welford_merge_vec(a, b)


@scenario_aggregator("PeriodVariance")
@dataclass(frozen=True)
class PeriodVariance(_PeriodMoment):
    """Per-period sample variance (ddof=1) across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        n, _mean, m2 = state
        out = np.full(n.shape[0], np.nan, dtype=np.float64)
        ok = n >= 2
        out[ok] = m2[ok] / (n[ok] - 1)
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodVariance", "column": self.column}


@scenario_aggregator("PeriodStd")
@dataclass(frozen=True)
class PeriodStd(_PeriodMoment):
    """Per-period sample standard deviation across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        n, _mean, m2 = state
        out = np.full(n.shape[0], np.nan, dtype=np.float64)
        ok = n >= 2
        out[ok] = np.sqrt(m2[ok] / (n[ok] - 1))
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodStd", "column": self.column}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_aggregators.py -v`
Expected: PASS (all). Add `PeriodVariance`/`PeriodStd` to the exports in **Task 10 Step 3** (scenarios `__init__` + top-level + `__all__`) — update that task's import list to include them.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_aggregators.py bindings/python/tests/scenarios/test_period_aggregators.py
git commit -m "feat(scenarios): PeriodVariance/PeriodStd via vector Welford-Chan"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** implements §1 (Approach A: VectorAggregator + batch_reduce seam), §2 (run_aggregated, list+alias invocation, AggregatedResult, naming), §2.2 gates (equivalence, small-N, shared-surface), §3 (jagged origin guard, pad-and-add — Tasks 2/3/8), §6 (PeriodMean exact, Task 4). The cgroup budget (§2.0) comes from Plan 1; the **two-point affine `per_cell`** and the **first-batch ramp** are simplified here to a single large seed (documented) — promote to two real seed batches if a thin-axis noise problem shows up (spec §9 sequencing step 3). Rank-based `PeriodQuantile/Median/CTE` (§4) are **Plan 4**. The parquet spill for full output (§2.2 C2) is **Plan 3**.
- **Type consistency:** `batch_reduce(frame, period)`, `add_input(state, value)`, `merge_accumulators(a, b)`, `extract_output(state)` are used identically across all `Period*` classes and the driver. `_alias_of` reads `alias_` (the `_BaseAggregator` field set by `.alias()`).
- **Variance/Std (§6):** implemented in **Task 11** (vector Welford-Chan, `(n, mean, m2)` per period; sample ddof=1; stable, not bit-exact across *different* K per spec §6). Remember Task 10's export list must include them.
- **No placeholders:** every step has runnable code + exact `uv run pytest` command + expected result.
