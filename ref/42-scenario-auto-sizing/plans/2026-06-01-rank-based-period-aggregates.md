# Rank-Based Per-Period Aggregates Implementation Plan (Plan 4 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-period quantile / median / CTE aggregators (`PeriodQuantile`, `PeriodMedian`, `PeriodCTE`) to the `run_aggregated` family, built without a per-value Python loop, via a vectorized DDSketch histogram (`SignedSketch.from_binned`) — gated by a build-from-binned == build-from-values correctness test.

**Architecture:** State is `list[SignedSketch]` (one signed DDSketch per projection period). `batch_reduce` computes each value's DDSketch bin in Polars (using the sketch's `gamma`), `group_by([period, sign, bin])` to a histogram of `(representative_value, count)`, and loads each period's sketch via weighted `add(representative, weight=count)` — so the number of `add` calls is *bins-per-period* (hundreds), not values (millions). Merges are elementwise `SignedSketch.merge`. The same aggregators run on the scenario axis too (shared seam).

**Tech Stack:** Python 3.12, `ddsketch` (weighted `add`), Polars (`log`/`ceil`/`group_by`), NumPy, `pytest`. **Depends on Plan 2** (`VectorAggregator`, `run_aggregated`) and the existing `SignedSketch` (`scenarios/_sketch.py`).

**Plan series:** Plans 1-3 ✅ (sizing, run_aggregated + Period*, spill). This is the last. Spec: `ref/42-scenario-auto-sizing/specs/2026-06-01-unified-aggregation-surface-design.md` (§4).

---

## File Structure

- **Modify** `bindings/python/gaspatchio_core/scenarios/_sketch.py` — add `SignedSketch.from_binned(...)`.
- **Create** `bindings/python/gaspatchio_core/scenarios/_period_sketch.py` — `_build_period_sketches` (the vectorized histogram build) + `PeriodQuantile`/`PeriodMedian`/`PeriodCTE`.
- **Modify** `bindings/python/gaspatchio_core/scenarios/__init__.py`, `bindings/python/gaspatchio_core/__init__.py` — exports.
- **Test** `bindings/python/tests/scenarios/test_period_sketch.py`.

---

## Task 1: `SignedSketch.from_binned` (weighted add) + dual-build gate

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_sketch.py`
- Test: `bindings/python/tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/scenarios/test_period_sketch.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for rank-based per-period aggregators (sketch-backed)."""

from __future__ import annotations

from gaspatchio_core.scenarios._sketch import SignedSketch

_RA = 1e-4


def test_from_binned_equals_per_value_build():
    # Deterministic mixed-sign data with repeats (so binning actually groups).
    values = [round(1000 + (i % 50) * 1.0, 1) for i in range(2000)]
    values += [-(200 + (i % 30) * 1.0) for i in range(500)]
    values += [0.0] * 17

    # (A) per-value build (the ground truth)
    a = SignedSketch(relative_accuracy=_RA)
    for v in values:
        a.add(v)

    # (B) group by exact ddsketch key, then from_binned with a real representative
    a_map = SignedSketch(relative_accuracy=_RA).pos._mapping  # noqa: SLF001
    pos: dict[int, tuple[float, int]] = {}
    neg: dict[int, tuple[float, int]] = {}
    zero_n = 0
    for v in values:
        if v == 0:
            zero_n += 1
        elif v > 0:
            k = a_map.key(v)
            cur = pos.get(k)
            pos[k] = (v, 1) if cur is None else (cur[0], cur[1] + 1)
        else:
            k = a_map.key(-v)
            cur = neg.get(k)
            neg[k] = (-v, 1) if cur is None else (cur[0], cur[1] + 1)

    b = SignedSketch.from_binned(
        pos=list(pos.values()), neg=list(neg.values()), zero_n=zero_n, relative_accuracy=_RA
    )

    assert a.n == b.n
    for q in (0.01, 0.25, 0.5, 0.75, 0.99):
        assert a.quantile(q) == b.quantile(q)  # bit-exact: same keys, same weights
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k from_binned -v`
Expected: FAIL — `AttributeError: type object 'SignedSketch' has no attribute 'from_binned'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_sketch.py (inside class SignedSketch)
    @classmethod
    def from_binned(
        cls,
        *,
        pos: list[tuple[float, int]],
        neg: list[tuple[float, int]],
        zero_n: int,
        relative_accuracy: float = DEFAULT_RELATIVE_ACCURACY,
    ) -> SignedSketch:
        """Build a sketch from histograms: ``(representative_value, count)`` per bin.

        Each ``representative_value`` must be a real observed value from its bin, so
        the underlying ddsketch ``add(value, weight=count)`` places the whole count in
        the correct bucket by the library's own mapping — no per-value loop.
        ``pos``/``neg`` carry **positive** representatives (``neg`` is the abs value).
        """
        out = cls(relative_accuracy=relative_accuracy)
        for value, count in pos:
            out.pos.add(float(value), float(count))
        for value, count in neg:
            out.neg.add(float(value), float(count))
        out.zero_n = int(zero_n)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k from_binned -v`
Expected: PASS — bit-exact quantiles (same ddsketch keys, same weights).

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_sketch.py bindings/python/tests/scenarios/test_period_sketch.py
git commit -m "feat(scenarios): SignedSketch.from_binned (weighted histogram build)"
```

---

## Task 2: vectorized per-period sketch build

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_period_sketch.py`
- Test: `bindings/python/tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_sketch.py
import polars as pl

from gaspatchio_core.scenarios._period_sketch import build_period_sketches


def test_build_period_sketches_matches_per_value():
    # period 0 and period 1, mixed sign + a zero
    lists = [[1000.0, -200.0], [1000.0, 0.0], [1005.0, -205.0], [1010.0, -195.0]]
    df = pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    sketches = build_period_sketches(df, "__period", "cf", relative_accuracy=_RA)
    assert len(sketches) == 2

    # ground truth per period
    cols = [[1000.0, 1000.0, 1005.0, 1010.0], [-200.0, 0.0, -205.0, -195.0]]
    for t, vals in enumerate(cols):
        truth = SignedSketch(relative_accuracy=_RA)
        for v in vals:
            truth.add(v)
        assert sketches[t].n == truth.n
        for q in (0.25, 0.5, 0.75):
            assert sketches[t].quantile(q) == truth.quantile(q)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k build_period -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._period_sketch'`

- [ ] **Step 3: Write minimal implementation**

```python
# bindings/python/gaspatchio_core/scenarios/_period_sketch.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Rank-based per-period aggregators (PeriodQuantile/Median/CTE).
# ABOUTME: list[SignedSketch] state; vectorized histogram build, no per-value loop.

"""Per-period sketch-backed aggregators."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from gaspatchio_core.scenarios._aggregators import scenario_aggregator
from gaspatchio_core.scenarios._period_aggregators import VectorAggregator
from gaspatchio_core.scenarios._sketch import SignedSketch


def build_period_sketches(
    frame: pl.DataFrame, period: str, column: str, *, relative_accuracy: float
) -> list[SignedSketch]:
    """One :class:`SignedSketch` per period, built via a vectorized histogram.

    The DDSketch bin key is reproduced in Polars from ``gamma``; a real per-bin
    representative value (``first(|v|)``) is fed to ``from_binned`` so the
    library's own mapping assigns the bucket. Validated against per-value adds by
    the dual-build gate (Task 1 + the run_aggregated gate in Task 5).
    """
    gamma = (1.0 + relative_accuracy) / (1.0 - relative_accuracy)
    inv_log_gamma = 1.0 / math.log(gamma)
    exploded = frame.lazy().select(pl.col(period), pl.col(column)).explode([period, column])

    zeros = (
        exploded.filter(pl.col(column) == 0)
        .group_by(period)
        .agg(pl.len().alias("z"))
        .collect()
    )
    binned = (
        exploded.filter(pl.col(column) != 0)
        .with_columns(
            (pl.col(column) > 0).cast(pl.Int8).alias("__sign"),
            pl.col(column).abs().alias("__abs"),
        )
        .with_columns((pl.col("__abs").log() * inv_log_gamma).ceil().cast(pl.Int64).alias("__bin"))
        .group_by([period, "__sign", "__bin"])
        .agg(pl.col("__abs").first().alias("__rep"), pl.len().alias("__cnt"))
        .collect()
    )

    n_periods = 0
    for frame_part in (zeros, binned):
        if frame_part.height:
            n_periods = max(n_periods, int(frame_part[period].max()) + 1)

    pos: list[list[tuple[float, int]]] = [[] for _ in range(n_periods)]
    neg: list[list[tuple[float, int]]] = [[] for _ in range(n_periods)]
    zero_n = [0] * n_periods
    for row in zeros.iter_rows(named=True):
        zero_n[row[period]] = row["z"]
    for row in binned.iter_rows(named=True):
        t = row[period]
        entry = (float(row["__rep"]), int(row["__cnt"]))
        (pos if row["__sign"] == 1 else neg)[t].append(entry)

    return [
        SignedSketch.from_binned(
            pos=pos[t], neg=neg[t], zero_n=zero_n[t], relative_accuracy=relative_accuracy
        )
        for t in range(n_periods)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k build_period -v`
Expected: PASS

> If a boundary-ULP mismatch makes a quantile differ by one bucket, tighten the bin expr to reproduce `SignedSketch(...).pos._mapping` exactly (read its `_multiplier`/`_offset`); the Task-1 gate uses the library key directly and stays bit-exact, so any divergence is isolated to this expr.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_sketch.py bindings/python/tests/scenarios/test_period_sketch.py
git commit -m "feat(scenarios): vectorized per-period DDSketch histogram build"
```

---

## Task 3: `PeriodQuantile` aggregator

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_sketch.py`
- Test: `bindings/python/tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_sketch.py
import numpy as np

from gaspatchio_core.scenarios._period_sketch import PeriodQuantile


def _df(lists):
    return pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )


def test_period_quantile_per_period():
    # period 0: 1..100 ; period 1: 1001..1100
    lists = [[float(i), float(1000 + i)] for i in range(1, 101)]
    agg = PeriodQuantile("cf", levels=(0.5,))
    acc = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period"))
    out = agg.extract_output(acc)  # dict level -> ndarray[n_periods]
    assert np.isclose(out[0.5][0], 50.0, rtol=2e-2)
    assert np.isclose(out[0.5][1], 1050.0, rtol=2e-2)


def test_period_quantile_merge_equivalent():
    lists = [[float(i)] for i in range(1, 201)]
    agg = PeriodQuantile("cf", levels=(0.9,))
    whole = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period"))
    a = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists[:100]), "__period"))
    b = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists[100:]), "__period"))
    merged = agg.merge_accumulators(a, b)
    assert np.isclose(agg.extract_output(whole)[0.9][0], agg.extract_output(merged)[0.9][0], rtol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k period_quantile -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodQuantile'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_sketch.py
def _merge_sketch_lists(
    a: list[SignedSketch], b: list[SignedSketch], relative_accuracy: float
) -> list[SignedSketch]:
    """Elementwise SignedSketch.merge; pad the shorter with empty sketches."""
    n = max(len(a), len(b))
    out: list[SignedSketch] = []
    for t in range(n):
        sa = a[t] if t < len(a) else SignedSketch(relative_accuracy=relative_accuracy)
        sb = b[t] if t < len(b) else SignedSketch(relative_accuracy=relative_accuracy)
        out.append(SignedSketch.merge(sa, sb))
    return out


@dataclass(frozen=True)
class _PeriodSketchAgg(VectorAggregator):
    """Shared list[SignedSketch] machinery for rank-based per-period aggregators."""

    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return []

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        return build_period_sketches(
            frame, period, self.column, relative_accuracy=self.relative_accuracy
        )

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(state, value, self.relative_accuracy)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(a, b, self.relative_accuracy)


@scenario_aggregator("PeriodQuantile")
@dataclass(frozen=True)
class PeriodQuantile(_PeriodSketchAgg):
    """Per-period quantile(s) across the batched axis (DDSketch-backed)."""

    levels: tuple[float, ...] = (0.5,)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        import numpy as np

        return {
            level: np.array([sk.quantile(level) for sk in state], dtype=np.float64)
            for level in self.levels
        }

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "PeriodQuantile",
            "column": self.column,
            "levels": list(self.levels),
            "relative_accuracy": self.relative_accuracy,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k period_quantile -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_sketch.py bindings/python/tests/scenarios/test_period_sketch.py
git commit -m "feat(scenarios): PeriodQuantile (list[SignedSketch], elementwise merge)"
```

---

## Task 4: `PeriodMedian` + `PeriodCTE`

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_period_sketch.py`
- Test: `bindings/python/tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_sketch.py
from gaspatchio_core.scenarios._period_sketch import PeriodCTE, PeriodMedian


def test_period_median():
    lists = [[float(i), float(1000 + i)] for i in range(1, 101)]
    agg = PeriodMedian("cf")
    out = agg.extract_output(agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period")))
    assert np.isclose(out[0], 50.0, rtol=2e-2)


def test_period_cte_upper_tail():
    # period 0: 1..1000 ; CTE upper at 0.1 ~ mean of top 10% ~ 950
    lists = [[float(i)] for i in range(1, 1001)]
    agg = PeriodCTE("cf", level=0.1, direction="upper")
    out = agg.extract_output(agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period")))
    assert 930.0 <= out[0] <= 970.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k "period_median or period_cte" -v`
Expected: FAIL — `ImportError: cannot import name 'PeriodMedian'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_period_sketch.py
from typing import Literal


@scenario_aggregator("PeriodMedian")
@dataclass(frozen=True)
class PeriodMedian(_PeriodSketchAgg):
    """Per-period median across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        import numpy as np

        return np.array([sk.quantile(0.5) for sk in state], dtype=np.float64)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "PeriodMedian", "column": self.column, "relative_accuracy": self.relative_accuracy}


@scenario_aggregator("PeriodCTE")
@dataclass(frozen=True)
class PeriodCTE(_PeriodSketchAgg):
    """Per-period Conditional Tail Expectation across the batched axis."""

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        import numpy as np

        return np.array(
            [sk.cte(level=self.level, direction=self.direction) for sk in state], dtype=np.float64
        )

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "PeriodCTE",
            "column": self.column,
            "level": self.level,
            "direction": self.direction,
            "relative_accuracy": self.relative_accuracy,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_period_sketch.py bindings/python/tests/scenarios/test_period_sketch.py
git commit -m "feat(scenarios): PeriodMedian + PeriodCTE (sketch-backed)"
```

---

## Task 5: exports + end-to-end `run_aggregated` rank-based gate

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py`, `bindings/python/gaspatchio_core/__init__.py`
- Test: `bindings/python/tests/scenarios/test_period_sketch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_period_sketch.py
def test_run_aggregated_with_period_quantile_matches_full():
    from gaspatchio_core import ActuarialFrame, run_aggregated

    def model(af):
        df = af._df.with_columns(  # noqa: SLF001
            pl.concat_list([pl.col("value"), pl.col("value") * 2]).alias("cf")
        )
        return ActuarialFrame(df)

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 201)]})
    full = run_aggregated(model, mp, [PeriodQuantile("cf", levels=(0.5,)).alias("q")], batch_size=200)
    batched = run_aggregated(model, mp, [PeriodQuantile("cf", levels=(0.5,)).alias("q")], batch_size=37)
    assert np.allclose(full.q[0.5], batched.q[0.5], rtol=1e-9)  # sketch merge is order-stable


def test_period_quantile_top_level_export():
    import gaspatchio_core as gsp

    for name in ("PeriodQuantile", "PeriodMedian", "PeriodCTE"):
        assert hasattr(gsp, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_period_sketch.py -k "run_aggregated_with or top_level" -v`
Expected: FAIL — `gsp.PeriodQuantile` missing; the run_aggregated test fails on import until exported.

- [ ] **Step 3: Write minimal implementation**

In `scenarios/__init__.py` and `gaspatchio_core/__init__.py`, import + add to `__all__`:

```python
from gaspatchio_core.scenarios._period_sketch import PeriodCTE, PeriodMedian, PeriodQuantile
```

(`run_aggregated`'s dispatch already routes any aggregator with `batch_reduce` through the vector path, so no driver change is needed — `PeriodQuantile.extract_output` returns a dict, which `AggregatedResult` exposes as `result.q[level]`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/ -q`
Expected: PASS (all green). Then:
Run: `cd bindings/python && uv run mypy gaspatchio_core/scenarios/_period_sketch.py && uv run ruff check gaspatchio_core/scenarios/_period_sketch.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/__init__.py bindings/python/gaspatchio_core/__init__.py bindings/python/tests/
git commit -m "feat(scenarios): export PeriodQuantile/Median/CTE; end-to-end rank-based gate"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** implements §4 — rank-based `Period*` via `list[SignedSketch]`, the vectorized `from_binned` build (weighted add, no per-value loop), and the dual-build correctness gate (Task 1 is bit-exact against per-value adds using the library key; Task 2 validates the Polars bin expr; Task 5 proves cross-K merge stability through `run_aggregated`).
- **The crux is Task 2's bin expr.** Task 1 is unconditionally bit-exact (it groups by the library's own `mapping.key`). Task 2 reproduces that key in Polars (`ceil(log(|v|)/log(gamma))`); if a boundary value ever lands one bucket off, Task 2's test catches it — tighten the expr to the mapping's exact `_multiplier`/`_offset` rather than weakening the test.
- **Memory note:** `list[SignedSketch]` is `n_periods` signed sketches per rank-based aggregator; each is compact (bounded buckets at `relative_accuracy`). Bounded, but document it for users adding many rank-based columns at long horizons.
- **Variance/Std** live in Plan 2 Task 11 (additive Welford), not here — only quantile/median/CTE are sketch-backed.
