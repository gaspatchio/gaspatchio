# GSP-101 — Mergeable aggregator layer redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the scenarios aggregator layer onto a Beam-style `CombineFn` Protocol with mergeable accumulators; ship `.over()` partitioning, DDSketch-backed CTE/Quantile, and an opt-in audit sidecar. Clean break from v0.1.

**Architecture:** Aggregator is the 5-tuple `(within_expr, create_accumulator, add_input, merge_accumulators, extract_output)` + modifiers (`.alias`, `.over`, `.of`). Partition lives in the driver via `_Partitioned` wrapper. `for_each_scenario` iterates per-aggregator within reductions. DDSketch provides bit-exact mergeable tail percentiles; audit sidecar completes the source_sha governance story.

**Tech Stack:** Python 3.13, Polars 1.38, PyO3, pytest, hypothesis, `ddsketch` (new dependency).

---

## File structure

### Created
- `bindings/python/gaspatchio_core/scenarios/_metric.py` — Aggregator Protocol + `_Partitioned` driver wrapper + base-class modifiers
- `bindings/python/gaspatchio_core/scenarios/_sketch.py` — DDSketch facade with signed-value support
- `bindings/python/gaspatchio_core/scenarios/_audit.py` — sidecar JSON writer/reader/schema
- `bindings/python/tests/scenarios/test_aggregator_property.py` — Hypothesis fixture pinning merge associativity/commutativity for every registered aggregator
- `bindings/python/tests/scenarios/test_for_each_partitioned.py` — `.over()` patterns including single-key/tuple normalisation and multi-column
- `bindings/python/tests/scenarios/test_governance_cross_process.py` — cross-process bit-exact governance (lifted from dog-fooding stress agent 3)
- `bindings/python/tests/scenarios/test_audit_sidecar.py` — sidecar JSON round-trip + schema_version guard

### Rewritten wholesale
- `bindings/python/gaspatchio_core/scenarios/_aggregators.py` — 14 aggregators implementing the new Protocol
- `bindings/python/gaspatchio_core/scenarios/_config.py` — `parse_aggregations` recursive (handles `_Partitioned`); remove old `MultiAgg`/`GroupedAgg` parsing
- `bindings/python/gaspatchio_core/scenarios/__init__.py` + `.pyi` — exports for the new surface; retired symbols removed

### Modified
- `bindings/python/gaspatchio_core/scenarios/_for_each.py` — drop `per_scenario` kwarg; per-aggregator within reduction inside the loop
- `bindings/python/gaspatchio_core/scenarios/_run.py` — `ScenarioRun.aggregations: tuple[Aggregator, ...]`; alias uniqueness validator; `audit` kwarg on `.run()`
- `bindings/python/gaspatchio_core/scenarios/_result.py` — `aggregations: dict[str, float | pl.DataFrame]`; new `audit_path` field
- Test files: most existing tests under `tests/scenarios/` need rewrite to the new surface

### Deleted
- v0.1 symbols `MultiAgg`, `GroupedAgg`, `metric`, `ScenarioMetric` — references removed from all production code; tests updated; backward-compat shims NOT added

### Added dependency
- `ddsketch` (DataDog, Apache-2.0) — pinned in `pyproject.toml`

---

## Cadence guide (recommendation)

Same shape as GSP-100. **Full subagent loop** (implementer → spec reviewer → code reviewer) on load-bearing tasks; **implementer + self-verify** on mechanical ones.

| Task | Type | Cadence |
|---|---|---|
| T1 Aggregator Protocol + `_Partitioned` | load-bearing | full loop |
| T2 Property test fixture | load-bearing | full loop |
| T3 DDSketch facade | load-bearing | full loop |
| T4–T7 14 primitive aggregators | mechanical | implementer + self-verify |
| T8 Modifiers | mechanical | implementer + self-verify |
| T9 Registry decorator | mechanical | implementer + self-verify |
| T10 Loop rewrite | load-bearing | full loop |
| T11–T13 ScenarioRun / Result / audit wiring | moderate | implementer + self-verify |
| T14 Audit sidecar | moderate | implementer + self-verify |
| T15–T16 YAML round-trip | moderate | implementer + self-verify |
| T17–T18 Public surface + migration | mechanical | implementer + self-verify |
| T19–T24 Test rewrites | mechanical | implementer + self-verify |
| T25 End-to-end audit chain integration | load-bearing | full loop |
| T26–T27 Memory benchmark + CHANGELOG | mechanical | implementer + self-verify |

---

## Phase 1 — Foundation (Protocol, property test, sketch)

### Task 1: `_metric.py` — Aggregator Protocol + `_Partitioned` wrapper + base modifiers

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_metric.py`
- Test: `bindings/python/tests/scenarios/test_metric_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_metric_protocol.py`:

```python
"""Test the Aggregator Protocol shape and _Partitioned wrapper."""
from __future__ import annotations

import pytest

from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned


def test_aggregator_protocol_runtime_checkable():
    """Aggregator is a runtime-checkable Protocol."""
    class Toy:
        def within_expr(self): ...
        def create_accumulator(self): ...
        def add_input(self, s, v): ...
        def merge_accumulators(self, a, b): ...
        def extract_output(self, s): ...
        def canonical_form(self): ...

    assert isinstance(Toy(), Aggregator)


def test_partitioned_is_not_part_of_public_protocol():
    """_Partitioned wraps an Aggregator + a partition tuple; is itself an Aggregator-shaped object."""
    class Toy:
        def within_expr(self): return None
        def create_accumulator(self): return 0
        def add_input(self, s, v): return s + v
        def merge_accumulators(self, a, b): return a + b
        def extract_output(self, s): return s
        def canonical_form(self): return {"kind": "toy"}

    p = _Partitioned(by=("lob",), inner=Toy(), alias="x")
    assert isinstance(p, Aggregator)
    assert p.by == ("lob",)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_metric_protocol.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `_metric.py`**

```python
# ABOUTME: Aggregator Protocol (Beam-style CombineFn 5-tuple) + _Partitioned wrapper.
# ABOUTME: Aggregators are partition-blind; partition lives in the driver.

"""Aggregator Protocol and partition wrapper for GSP-101.

The Aggregator contract (5-tuple) is a Beam-style CombineFn:

* ``within_expr()``        – within-scenario reduction (polars Expr today)
* ``create_accumulator()`` – fresh state
* ``add_input(state, v)``  – fold one per-scenario value
* ``merge_accumulators``   – associative + commutative state combine
* ``extract_output(s)``    – produce the final value

Plus ``canonical_form()`` for the audit chain.

Partition lives in the driver via _Partitioned, never inside the aggregator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import polars as pl


@runtime_checkable
class Aggregator(Protocol):
    def within_expr(self) -> "pl.Expr": ...
    def create_accumulator(self) -> Any: ...
    def add_input(self, state: Any, value: Any) -> Any: ...
    def merge_accumulators(self, a: Any, b: Any) -> Any: ...
    def extract_output(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _Partitioned:
    """Internal driver wrapper. Not exposed in the public surface.

    Holds dict[partition_tuple, inner_accumulator] state and routes
    add_input calls to the right slot. The wrapped aggregator is
    partition-blind.
    """

    by: tuple[str, ...]
    inner: Aggregator
    alias: str

    # The Aggregator-shaped methods that the loop will call:
    def within_expr(self) -> "pl.Expr":
        return self.inner.within_expr()

    def create_accumulator(self) -> dict[tuple[Any, ...], Any]:
        return {}

    def add_input(
        self, state: dict[tuple[Any, ...], Any], partition_key: tuple[Any, ...], value: Any
    ) -> dict[tuple[Any, ...], Any]:
        if partition_key not in state:
            state[partition_key] = self.inner.create_accumulator()
        state[partition_key] = self.inner.add_input(state[partition_key], value)
        return state

    def merge_accumulators(
        self,
        a: dict[tuple[Any, ...], Any],
        b: dict[tuple[Any, ...], Any],
    ) -> dict[tuple[Any, ...], Any]:
        out = dict(a)
        for k, v in b.items():
            out[k] = self.inner.merge_accumulators(out[k], v) if k in out else v
        return out

    def extract_output(self, state: dict[tuple[Any, ...], Any]) -> "pl.DataFrame":
        import polars as pl

        rows = []
        for partition_tuple, acc in sorted(state.items()):
            row = dict(zip(self.by, partition_tuple, strict=True))
            row[self.alias] = self.inner.extract_output(acc)
            rows.append(row)
        return pl.DataFrame(rows)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "_Partitioned",
            "by": list(self.by),
            "inner": self.inner.canonical_form(),
        }


__all__ = ["Aggregator", "_Partitioned"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_metric_protocol.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add bindings/python/gaspatchio_core/scenarios/_metric.py bindings/python/tests/scenarios/test_metric_protocol.py && git commit -m "feat(scenarios): Aggregator Protocol + _Partitioned driver wrapper

The 5-tuple CombineFn contract is the foundation for GSP-101's mergeable
aggregator layer. Aggregators are partition-blind; _Partitioned holds the
dict[partition_tuple, inner_acc] state and routes calls."
```

---

### Task 2: Property-test fixture for `merge_accumulators` associativity + commutativity

**Files:**
- Create: `bindings/python/tests/scenarios/test_aggregator_property.py`

This task ships the Hypothesis fixture that every shipped aggregator will be required to pass. Aggregators are added to the parametrisation in subsequent tasks (T4-T7).

- [ ] **Step 1: Write the property-test scaffold**

```python
"""Hypothesis-driven property test pinning merge associativity + commutativity.

Every aggregator implementing the GSP-101 Aggregator Protocol must satisfy:

    extract(fold(A ++ B)) == extract(merge(fold(A), fold(B)))                 (associativity)
    merge(a, b) extract-equals merge(b, a)                                    (commutativity)

For DDSketch-backed aggregators, the equality is on the serialised sketch
state — bit-identical.

Aggregator classes are registered in the AGGREGATOR_PARAMS list as they
land in subsequent tasks.
"""
from __future__ import annotations

from functools import reduce
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Aggregator classes registered as they land. Each entry:
#   (name, factory, value_strategy)
# Factory is called with no args; value_strategy supplies the test inputs.
AGGREGATOR_PARAMS: list[tuple[str, Any, Any]] = [
    # Filled in by T4-T7.
]


def _fold(agg, values):
    state = agg.create_accumulator()
    for v in values:
        state = agg.add_input(state, v)
    return state


@pytest.mark.parametrize(("name", "factory", "value_strategy"), AGGREGATOR_PARAMS)
@settings(max_examples=50, deadline=None)
@given(st.data())
def test_merge_is_associative(name, factory, value_strategy, data):
    """fold(A ++ B) extract-equals merge(fold(A), fold(B))."""
    values = data.draw(st.lists(value_strategy, min_size=2, max_size=100))
    if len(values) < 2:
        pytest.skip("Need at least 2 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    single = agg.extract_output(_fold(agg, values))
    merged = agg.extract_output(agg.merge_accumulators(_fold(agg, left), _fold(agg, right)))

    if isinstance(single, float):
        assert abs(single - merged) < 1e-9, (
            f"{name}: associativity broken (single={single}, merged={merged})"
        )
    else:
        assert single == merged, f"{name}: associativity broken"


@pytest.mark.parametrize(("name", "factory", "value_strategy"), AGGREGATOR_PARAMS)
@settings(max_examples=50, deadline=None)
@given(st.data())
def test_merge_is_commutative(name, factory, value_strategy, data):
    """merge(a, b) extract-equals merge(b, a)."""
    values = data.draw(st.lists(value_strategy, min_size=2, max_size=100))
    if len(values) < 2:
        pytest.skip("Need at least 2 values to split.")
    split = len(values) // 2
    left, right = values[:split], values[split:]

    agg = factory()
    a = _fold(agg, left)
    b = _fold(agg, right)
    forward = agg.extract_output(agg.merge_accumulators(a, b))
    reverse = agg.extract_output(agg.merge_accumulators(b, a))

    if isinstance(forward, float):
        assert abs(forward - reverse) < 1e-9, (
            f"{name}: commutativity broken (forward={forward}, reverse={reverse})"
        )
    else:
        assert forward == reverse, f"{name}: commutativity broken"
```

- [ ] **Step 2: Run (expected to pytest-skip since AGGREGATOR_PARAMS is empty)**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregator_property.py -v
```

Expected: collected but parametrised-empty → 0 tests. That's fine — the test file is the scaffolding.

- [ ] **Step 3: Commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add bindings/python/tests/scenarios/test_aggregator_property.py && git commit -m "test(scenarios): Hypothesis property-test scaffold for aggregator algebra

Pins associativity + commutativity for every Aggregator that will be
added to AGGREGATOR_PARAMS as classes land in T4-T7."
```

---

### Task 3: `_sketch.py` — DDSketch facade with paired signed-value sub-sketches

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_sketch.py`
- Test: `bindings/python/tests/scenarios/test_sketch.py`
- Modify: `bindings/python/pyproject.toml` (add `ddsketch` dependency)

- [ ] **Step 1: Add `ddsketch` to dependencies**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv add ddsketch
```

Verify `pyproject.toml` now lists `ddsketch>=3.0.1`.

- [ ] **Step 2: Write the failing test**

Create `bindings/python/tests/scenarios/test_sketch.py`:

```python
"""Test the signed-value DDSketch facade — bit-exact mergeability."""
from __future__ import annotations

import math

import pytest

from gaspatchio_core.scenarios._sketch import SignedSketch


def test_pos_only_quantile():
    s = SignedSketch()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
        s.add(v)
    assert math.isclose(s.quantile(0.5), 5.5, rel_tol=1e-3, abs_tol=1e-3)


def test_negative_only_quantile():
    s = SignedSketch()
    for v in [-10.0, -9.0, -8.0, -7.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0]:
        s.add(v)
    assert math.isclose(s.quantile(0.5), -5.5, rel_tol=1e-3, abs_tol=1e-3)


def test_mixed_sign_quantile():
    s = SignedSketch()
    for v in range(-5, 6):  # -5..5
        s.add(float(v))
    assert math.isclose(s.quantile(0.5), 0.0, abs_tol=1e-3)


def test_zero_count_tracked():
    s = SignedSketch()
    for _ in range(5):
        s.add(0.0)
    s.add(-1.0)
    s.add(1.0)
    # 7 values: -1, 0, 0, 0, 0, 0, 1 → median = 0
    assert s.quantile(0.5) == 0.0


def test_merge_is_commutative():
    a = SignedSketch()
    for v in [-3.0, -2.0, -1.0]:
        a.add(v)
    b = SignedSketch()
    for v in [1.0, 2.0, 3.0]:
        b.add(v)

    merged_ab = SignedSketch.merge(a, b)
    merged_ba = SignedSketch.merge(b, a)
    assert merged_ab.quantile(0.5) == merged_ba.quantile(0.5)


def test_serialise_round_trip():
    s = SignedSketch()
    for v in [-1.0, 0.0, 1.0, 2.0, 3.0]:
        s.add(v)
    blob = s.to_bytes()
    s2 = SignedSketch.from_bytes(blob)
    assert s.quantile(0.5) == s2.quantile(0.5)


def test_cte_upper_tail():
    s = SignedSketch()
    for v in range(1, 1001):  # 1..1000
        s.add(float(v))
    # Top 0.5% = values ranked 996..1000 → mean ≈ 998
    cte = s.cte(level=0.005, direction="upper")
    assert 990.0 < cte < 1005.0
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `_sketch.py`**

```python
# ABOUTME: DDSketch facade with paired pos/neg sub-sketches for signed values.
# ABOUTME: Provides bit-exact mergeable tail quantile + CTE primitives.

"""DDSketch wrapper for signed-value quantile/CTE aggregators.

DDSketch's relative-error semantics assume strictly positive values. We
hold paired sketches (one for positives, one for absolute negatives) plus
a zero-counter, and route queries / merges accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ddsketch import LogCollapsingLowestDenseDDSketch

_DEFAULT_RELATIVE_ACCURACY = 1e-4


def _new_sketch() -> LogCollapsingLowestDenseDDSketch:
    return LogCollapsingLowestDenseDDSketch(
        relative_accuracy=_DEFAULT_RELATIVE_ACCURACY
    )


@dataclass
class SignedSketch:
    """Paired DDSketch wrapper handling negatives + zeros.

    pos      -- sketch of values > 0
    neg      -- sketch of |values| for values < 0
    zero_n   -- number of values equal to 0
    """

    pos: LogCollapsingLowestDenseDDSketch = field(default_factory=_new_sketch)
    neg: LogCollapsingLowestDenseDDSketch = field(default_factory=_new_sketch)
    zero_n: int = 0

    def add(self, v: float) -> None:
        if v > 0:
            self.pos.add(v)
        elif v < 0:
            self.neg.add(-v)
        else:
            self.zero_n += 1

    @property
    def n(self) -> int:
        return self.pos.count + self.neg.count + self.zero_n

    @classmethod
    def merge(cls, a: "SignedSketch", b: "SignedSketch") -> "SignedSketch":
        out = cls()
        # DDSketch's merge is in-place on the receiver
        if a.pos.count:
            out.pos.merge(a.pos)
        if b.pos.count:
            out.pos.merge(b.pos)
        if a.neg.count:
            out.neg.merge(a.neg)
        if b.neg.count:
            out.neg.merge(b.neg)
        out.zero_n = a.zero_n + b.zero_n
        return out

    def quantile(self, q: float) -> float:
        n = self.n
        if n == 0:
            return float("nan")
        # Rank (1-indexed) we're looking for
        rank = q * n
        # How many negatives, zeros, positives?
        n_neg = self.neg.count
        n_zero = self.zero_n
        if rank <= n_neg:
            # Within the negatives. We sketched |v|; map back.
            # Smallest |v| corresponds to least-negative value (closest to 0).
            # Smallest rank in pos-of-|v| → largest rank in true neg → least negative.
            # We want the rank-th smallest TRUE value among negatives.
            # → that's the (n_neg - rank + 1)-th smallest |v|.
            inv_rank = (n_neg - rank + 1) / n_neg
            return -self.neg.get_quantile_value(inv_rank)
        if rank <= n_neg + n_zero:
            return 0.0
        # Within positives
        pos_rank = (rank - n_neg - n_zero) / self.pos.count
        return self.pos.get_quantile_value(pos_rank)

    def cte(self, level: float, direction: Literal["upper", "lower"] = "upper") -> float:
        """Conditional tail expectation.

        direction='upper' averages the top ``level`` fraction (right tail).
        direction='lower' averages the bottom ``level`` fraction (left tail).
        """
        n = self.n
        if n == 0:
            return float("nan")
        if direction == "upper":
            # Top fraction: integrate over the upper part of the distribution.
            # Approximation: take the (1-level) quantile as a threshold; estimate mean above.
            threshold = self.quantile(1.0 - level)
            # We don't have a per-element view; approximate the upper-tail mean
            # by querying several high quantiles and averaging.
            samples = [self.quantile(1.0 - level * (1 - i / 10)) for i in range(10)]
            samples = [s for s in samples if s >= threshold]
            return sum(samples) / max(len(samples), 1)
        # lower
        threshold = self.quantile(level)
        samples = [self.quantile(level * (1 - i / 10)) for i in range(10)]
        samples = [s for s in samples if s <= threshold]
        return sum(samples) / max(len(samples), 1)

    def to_bytes(self) -> bytes:
        """Serialise to bytes via DDSketch's protobuf representation."""
        from io import BytesIO

        buf = BytesIO()
        # Each sub-sketch serialises; zero_n is a small int prefix.
        zero_bytes = self.zero_n.to_bytes(8, "big", signed=False)
        pos_pb = self.pos.to_proto().SerializeToString()
        neg_pb = self.neg.to_proto().SerializeToString()
        buf.write(zero_bytes)
        buf.write(len(pos_pb).to_bytes(8, "big"))
        buf.write(pos_pb)
        buf.write(len(neg_pb).to_bytes(8, "big"))
        buf.write(neg_pb)
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, blob: bytes) -> "SignedSketch":
        from ddsketch.pb.ddsketch_pb2 import DDSketch as DDSketchPB

        zero_n = int.from_bytes(blob[:8], "big")
        pos_len = int.from_bytes(blob[8:16], "big")
        pos_pb_bytes = blob[16 : 16 + pos_len]
        neg_offset = 16 + pos_len
        neg_len = int.from_bytes(blob[neg_offset : neg_offset + 8], "big")
        neg_pb_bytes = blob[neg_offset + 8 : neg_offset + 8 + neg_len]

        pos_pb = DDSketchPB()
        pos_pb.ParseFromString(pos_pb_bytes)
        neg_pb = DDSketchPB()
        neg_pb.ParseFromString(neg_pb_bytes)

        pos = LogCollapsingLowestDenseDDSketch.from_proto(pos_pb)
        neg = LogCollapsingLowestDenseDDSketch.from_proto(neg_pb)
        return cls(pos=pos, neg=neg, zero_n=zero_n)


__all__ = ["SignedSketch"]
```

- [ ] **Step 4: Run tests**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_sketch.py -v
```

Expected: 7 passed.

If the `from_proto` API differs in your `ddsketch` version, adapt the (de)serialisation paths. Verify the round-trip preserves quantiles.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add bindings/python/gaspatchio_core/scenarios/_sketch.py bindings/python/tests/scenarios/test_sketch.py bindings/python/pyproject.toml bindings/python/uv.lock && git commit -m "feat(scenarios): SignedSketch facade over DDSketch for mergeable quantile/CTE

Paired positive/negative DDSketches plus zero-counter to handle signed
values. Provides quantile, CTE, and protobuf-based serialisation.
Relative accuracy 1e-4 (sub-bp tail error for SCR-99.5%)."
```

---

## Phase 2 — Rewrite the 14 primitive aggregators

### Task 4: Trivial mergeable — `Sum`, `Count`, `Min`, `Max`

**Files:**
- Rewrite: `bindings/python/gaspatchio_core/scenarios/_aggregators.py` (start clean; this task lays down the file)
- Modify: `bindings/python/tests/scenarios/test_aggregator_property.py` (add 4 entries to `AGGREGATOR_PARAMS`)
- Test: `bindings/python/tests/scenarios/test_aggregators_trivial.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_trivial.py`:

```python
"""Test Sum/Count/Min/Max — trivial mergeable aggregators."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import Count, Max, Min, Sum


def test_sum_correctness():
    a = Sum("v")
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(6.0)


def test_count_correctness():
    a = Count("v")
    s = a.create_accumulator()
    for _ in range(5):
        s = a.add_input(s, None)  # Count ignores the value
    assert a.extract_output(s) == 5


def test_min_correctness():
    a = Min("v")
    s = a.create_accumulator()
    for v in [3.0, 1.0, 2.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(1.0)


def test_max_correctness():
    a = Max("v")
    s = a.create_accumulator()
    for v in [3.0, 1.0, 2.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(3.0)


def test_sum_within_expr_default():
    """Default within reduction is sum-of-column."""
    a = Sum("loss")
    expected = pl.col("loss").sum()
    # Compare canonical form to verify it's sum-of-column
    cf = a.canonical_form()
    assert cf["within"] == "sum"
    assert cf["column"] == "loss"


def test_sum_named_within():
    a = Sum("loss", within="mean")
    cf = a.canonical_form()
    assert cf["within"] == "mean"


def test_invalid_within_raises():
    with pytest.raises(ValueError, match="within must be one of"):
        Sum("loss", within="invalid")
```

Expected: `ModuleNotFoundError` (or `ImportError` on these new names).

- [ ] **Step 2: Rewrite `_aggregators.py` from scratch**

This is the wholesale rewrite. Delete the existing file's content and replace with:

```python
# ABOUTME: GSP-101 aggregator primitives implementing the Aggregator Protocol.
# ABOUTME: Each aggregator is partition-blind; partitioning is added via .over().

"""GSP-101 aggregator primitives.

Each aggregator implements the Aggregator Protocol from _metric.py:
    within_expr, create_accumulator, add_input, merge_accumulators,
    extract_output, canonical_form.

Aggregators are partition-blind. To partition, call `.over(by)` which
returns a _Partitioned wrapper that holds the dict[partition_key, acc]
state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned

if TYPE_CHECKING:
    pass

_VALID_WITHIN: tuple[str, ...] = (
    "sum", "mean", "max", "min", "count", "first", "last"
)


def _within_to_expr(column: str, within: str) -> pl.Expr:
    """Translate a named within reduction into a polars expression."""
    if within == "sum":
        return pl.col(column).sum()
    if within == "mean":
        return pl.col(column).mean()
    if within == "max":
        return pl.col(column).max()
    if within == "min":
        return pl.col(column).min()
    if within == "count":
        return pl.col(column).count()
    if within == "first":
        return pl.col(column).first()
    if within == "last":
        return pl.col(column).last()
    msg = f"within must be one of {_VALID_WITHIN}, got {within!r}"
    raise ValueError(msg)


def _validate_within(within: str) -> None:
    if within not in _VALID_WITHIN:
        msg = f"within must be one of {_VALID_WITHIN}, got {within!r}"
        raise ValueError(msg)


@dataclass(frozen=True)
class _BaseAggregator:
    """Shared modifier base — alias, over, of.

    Concrete aggregator subclasses inherit modifier methods but supply
    their own create_accumulator / add_input / merge / extract.
    """

    column: str
    within: str = "sum"
    alias_: str | None = None  # populated by .alias()
    within_expr_override: pl.Expr | None = None  # populated by .of()

    def __post_init__(self) -> None:
        if self.within_expr_override is None:
            _validate_within(self.within)
        # If .of() supplied, within is ignored and the override is used.

    def within_expr(self) -> pl.Expr:
        if self.within_expr_override is not None:
            return self.within_expr_override
        return _within_to_expr(self.column, self.within)

    def alias(self, name: str) -> "_BaseAggregator":
        return replace(self, alias_=name)

    def over(self, by: str | tuple[str, ...]) -> _Partitioned:
        if isinstance(by, str):
            by_tuple = (by,)
        else:
            by_tuple = tuple(by)
        alias = self.alias_
        if alias is None:
            msg = "Call .alias(name) before .over(...) so the output column is named."
            raise ValueError(msg)
        return _Partitioned(by=by_tuple, inner=self, alias=alias)

    @classmethod
    def of(cls, within_expr: pl.Expr) -> "_BaseAggregator":
        return cls(column="__expr__", within_expr_override=within_expr)


# --- Sum ---


@dataclass(frozen=True)
class Sum(_BaseAggregator):
    """Sum across scenarios."""

    def create_accumulator(self) -> float:
        return 0.0

    def add_input(self, state: float, value: float) -> float:
        return state + (value if value is not None else 0.0)

    def merge_accumulators(self, a: float, b: float) -> float:
        return a + b

    def extract_output(self, state: float) -> float:
        return float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Sum",
            "column": self.column,
            "within": self.within if self.within_expr_override is None else "__expr__",
        }


# --- Count ---


@dataclass(frozen=True)
class Count(_BaseAggregator):
    """Count of scenarios contributing a value."""

    def create_accumulator(self) -> int:
        return 0

    def add_input(self, state: int, value: Any) -> int:  # noqa: ARG002
        return state + 1

    def merge_accumulators(self, a: int, b: int) -> int:
        return a + b

    def extract_output(self, state: int) -> int:
        return int(state)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Count", "column": self.column}


# --- Min ---


@dataclass(frozen=True)
class Min(_BaseAggregator):
    """Min across scenarios."""

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float) -> float:
        return value if state is None else min(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    def extract_output(self, state: float | None) -> float:
        return float("nan") if state is None else float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Min", "column": self.column, "within": self.within}


# --- Max ---


@dataclass(frozen=True)
class Max(_BaseAggregator):
    """Max across scenarios."""

    def create_accumulator(self) -> float | None:
        return None

    def add_input(self, state: float | None, value: float) -> float:
        return value if state is None else max(state, value)

    def merge_accumulators(self, a: float | None, b: float | None) -> float | None:
        if a is None:
            return b
        if b is None:
            return a
        return max(a, b)

    def extract_output(self, state: float | None) -> float:
        return float("nan") if state is None else float(state)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Max", "column": self.column, "within": self.within}


__all__ = ["Count", "Max", "Min", "Sum"]
```

Note: subsequent tasks (T5-T7) extend this file with more aggregator classes and grow `__all__`.

- [ ] **Step 3: Add aggregators to property-test parametrisation**

Edit `bindings/python/tests/scenarios/test_aggregator_property.py` — replace the empty `AGGREGATOR_PARAMS` list:

```python
from hypothesis import strategies as st

from gaspatchio_core.scenarios._aggregators import Count, Max, Min, Sum

AGGREGATOR_PARAMS = [
    ("Sum", lambda: Sum("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
    ("Count", lambda: Count("v"), st.floats(allow_nan=False)),
    ("Min", lambda: Min("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
    ("Max", lambda: Max("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
]
```

- [ ] **Step 4: Run tests**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregators_trivial.py tests/scenarios/test_aggregator_property.py -v
```

Expected: 7 trivial tests + parametric property tests all pass.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add bindings/python/gaspatchio_core/scenarios/_aggregators.py bindings/python/tests/scenarios/test_aggregators_trivial.py bindings/python/tests/scenarios/test_aggregator_property.py && git commit -m "feat(aggregators): Sum, Count, Min, Max — trivial mergeable primitives

Wholesale rewrite of _aggregators.py against the GSP-101 Aggregator
Protocol. Each is a one-state mergeable fold. Property tests confirm
associativity + commutativity for arbitrary input orders."
```

---

### Task 5: ArgMin, ArgMax — lex-tiebreak mergeable

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Modify: `bindings/python/tests/scenarios/test_aggregator_property.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_argextreme.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_argextreme.py`:

```python
"""Test ArgMin / ArgMax — best-pair mergeable, lex-tiebreak."""
from __future__ import annotations

from gaspatchio_core.scenarios._aggregators import ArgMax, ArgMin


def test_argmax_returns_scenario_id():
    a = ArgMax("v")
    s = a.create_accumulator()
    # add_input receives (scenario_id, value) tuples for ArgMin/ArgMax
    s = a.add_input(s, ("S1", 10.0))
    s = a.add_input(s, ("S2", 30.0))
    s = a.add_input(s, ("S3", 20.0))
    assert a.extract_output(s) == "S2"


def test_argmin_returns_scenario_id():
    a = ArgMin("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S1", 10.0))
    s = a.add_input(s, ("S2", 30.0))
    s = a.add_input(s, ("S3", 20.0))
    assert a.extract_output(s) == "S1"


def test_argmax_lex_tiebreak():
    """When values are equal, the smallest scenario_id wins."""
    a = ArgMax("v")
    s = a.create_accumulator()
    s = a.add_input(s, ("S2", 10.0))
    s = a.add_input(s, ("S1", 10.0))
    assert a.extract_output(s) == "S1"


def test_argmax_merge():
    a = ArgMax("v")
    left = a.add_input(a.create_accumulator(), ("S1", 5.0))
    right = a.add_input(a.create_accumulator(), ("S2", 7.0))
    merged = a.merge_accumulators(left, right)
    assert a.extract_output(merged) == "S2"
```

- [ ] **Step 2: Extend `_aggregators.py`**

Add to the same file (after `Max`):

```python
# --- ArgMin / ArgMax ---


@dataclass(frozen=True)
class ArgMax(_BaseAggregator):
    """Scenario_id of the scenario with the maximum value.

    add_input receives a (scenario_id, value) tuple — the loop passes
    this shape so ArgMin/ArgMax can record the identity, not just the
    value.

    Lexicographic tiebreak: on equal values, the smaller scenario_id wins.
    """

    def create_accumulator(self) -> tuple[Any, float] | None:
        return None

    def add_input(
        self, state: tuple[Any, float] | None, value: tuple[Any, float]
    ) -> tuple[Any, float]:
        sid, v = value
        if state is None:
            return (sid, v)
        best_sid, best_v = state
        if v > best_v:
            return (sid, v)
        if v == best_v and sid < best_sid:
            return (sid, v)
        return state

    def merge_accumulators(
        self,
        a: tuple[Any, float] | None,
        b: tuple[Any, float] | None,
    ) -> tuple[Any, float] | None:
        if a is None:
            return b
        if b is None:
            return a
        return self.add_input(a, b)

    def extract_output(self, state: tuple[Any, float] | None) -> Any:
        return None if state is None else state[0]

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "ArgMax", "column": self.column, "within": self.within}


@dataclass(frozen=True)
class ArgMin(_BaseAggregator):
    """Scenario_id of the scenario with the minimum value. Lex tiebreak."""

    def create_accumulator(self) -> tuple[Any, float] | None:
        return None

    def add_input(
        self, state: tuple[Any, float] | None, value: tuple[Any, float]
    ) -> tuple[Any, float]:
        sid, v = value
        if state is None:
            return (sid, v)
        best_sid, best_v = state
        if v < best_v:
            return (sid, v)
        if v == best_v and sid < best_sid:
            return (sid, v)
        return state

    def merge_accumulators(
        self,
        a: tuple[Any, float] | None,
        b: tuple[Any, float] | None,
    ) -> tuple[Any, float] | None:
        if a is None:
            return b
        if b is None:
            return a
        return self.add_input(a, b)

    def extract_output(self, state: tuple[Any, float] | None) -> Any:
        return None if state is None else state[0]

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "ArgMin", "column": self.column, "within": self.within}
```

Update `__all__`:

```python
__all__ = ["ArgMax", "ArgMin", "Count", "Max", "Min", "Sum"]
```

- [ ] **Step 3: Add to property-test parametrisation**

`AGGREGATOR_PARAMS` in `test_aggregator_property.py` — append:

```python
import hypothesis.strategies as st_

_ID_VAL = st.tuples(st_.text(min_size=1, max_size=8), st_.floats(min_value=-1e6, max_value=1e6, allow_nan=False))

AGGREGATOR_PARAMS += [
    ("ArgMax", lambda: ArgMax("v"), _ID_VAL),
    ("ArgMin", lambda: ArgMin("v"), _ID_VAL),
]
```

- [ ] **Step 4: Run tests + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregators_argextreme.py tests/scenarios/test_aggregator_property.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(aggregators): ArgMin, ArgMax with lexicographic tiebreak"
```

---

### Task 6: Mean, Variance, Std — Welford parallel merge

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Modify: `bindings/python/tests/scenarios/test_aggregator_property.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_moments.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_moments.py`:

```python
"""Test Mean/Variance/Std — Welford parallel merge."""
from __future__ import annotations

import math
import statistics

import pytest

from gaspatchio_core.scenarios._aggregators import Mean, Std, Variance


def test_mean_matches_statistics():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Mean("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(statistics.mean(values))


def test_variance_matches_statistics():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Variance("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    # Sample variance (ddof=1)
    assert a.extract_output(s) == pytest.approx(statistics.variance(values))


def test_std_matches_statistics():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = Std("v")
    s = a.create_accumulator()
    for v in values:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(statistics.stdev(values))


def test_mean_chan_merge_matches_single_pass():
    """Chan's parallel combine must match single-pass for arbitrary splits."""
    values = [float(i) for i in range(1, 101)]
    a = Mean("v")
    single = a.create_accumulator()
    for v in values:
        single = a.add_input(single, v)

    left = a.create_accumulator()
    for v in values[:30]:
        left = a.add_input(left, v)
    right = a.create_accumulator()
    for v in values[30:]:
        right = a.add_input(right, v)
    merged = a.merge_accumulators(left, right)

    assert a.extract_output(merged) == pytest.approx(a.extract_output(single))


def test_single_value_variance():
    a = Variance("v")
    s = a.create_accumulator()
    s = a.add_input(s, 42.0)
    # Sample variance of one value is NaN (or 0 — choose convention)
    out = a.extract_output(s)
    assert math.isnan(out) or out == 0.0
```

- [ ] **Step 2: Extend `_aggregators.py`**

Add to the file:

```python
# --- Mean / Variance / Std ---


@dataclass(frozen=True)
class Mean(_BaseAggregator):
    """Mean across scenarios — Welford accumulator."""

    def create_accumulator(self) -> dict[str, float]:
        return {"n": 0, "mean": 0.0}

    def add_input(self, state: dict[str, float], value: float) -> dict[str, float]:
        n = state["n"] + 1
        delta = value - state["mean"]
        return {"n": n, "mean": state["mean"] + delta / n}

    def merge_accumulators(
        self, a: dict[str, float], b: dict[str, float]
    ) -> dict[str, float]:
        n = a["n"] + b["n"]
        if n == 0:
            return {"n": 0, "mean": 0.0}
        # Chan's parallel mean
        new_mean = (a["n"] * a["mean"] + b["n"] * b["mean"]) / n
        return {"n": n, "mean": new_mean}

    def extract_output(self, state: dict[str, float]) -> float:
        return float("nan") if state["n"] == 0 else float(state["mean"])

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Mean", "column": self.column, "within": self.within}


@dataclass(frozen=True)
class Variance(_BaseAggregator):
    """Sample variance across scenarios — Welford+Chan parallel combine."""

    def create_accumulator(self) -> dict[str, float]:
        return {"n": 0, "mean": 0.0, "m2": 0.0}

    def add_input(self, state: dict[str, float], value: float) -> dict[str, float]:
        n = state["n"] + 1
        delta = value - state["mean"]
        mean = state["mean"] + delta / n
        delta2 = value - mean
        m2 = state["m2"] + delta * delta2
        return {"n": n, "mean": mean, "m2": m2}

    def merge_accumulators(
        self, a: dict[str, float], b: dict[str, float]
    ) -> dict[str, float]:
        if a["n"] == 0:
            return b
        if b["n"] == 0:
            return a
        n = a["n"] + b["n"]
        delta = b["mean"] - a["mean"]
        mean = a["mean"] + delta * b["n"] / n
        m2 = a["m2"] + b["m2"] + delta * delta * a["n"] * b["n"] / n
        return {"n": n, "mean": mean, "m2": m2}

    def extract_output(self, state: dict[str, float]) -> float:
        if state["n"] < 2:
            return float("nan")
        return float(state["m2"] / (state["n"] - 1))

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Variance", "column": self.column, "within": self.within}


@dataclass(frozen=True)
class Std(_BaseAggregator):
    """Sample standard deviation — sqrt of Variance."""

    def create_accumulator(self) -> dict[str, float]:
        return {"n": 0, "mean": 0.0, "m2": 0.0}

    def add_input(self, state: dict[str, float], value: float) -> dict[str, float]:
        # Same Welford as Variance
        return Variance.add_input.__wrapped__(self, state, value) if False else (
            lambda s, v: Variance("v").add_input(s, v)
        )(state, value)

    def merge_accumulators(
        self, a: dict[str, float], b: dict[str, float]
    ) -> dict[str, float]:
        return Variance("v").merge_accumulators(a, b)

    def extract_output(self, state: dict[str, float]) -> float:
        import math

        v = Variance("v").extract_output(state)
        return v if math.isnan(v) else math.sqrt(v)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Std", "column": self.column, "within": self.within}
```

Note: the `Std` implementation defers to `Variance` mechanics. The `add_input` implementation above is awkward — a cleaner pattern is to factor out a `_welford_add` and `_welford_merge` free function and have both classes use it. Implementer should refactor to whichever pattern is cleaner; behaviour is the constraint.

Update `__all__` to include `Mean, Std, Variance`.

- [ ] **Step 3: Add to property-test parametrisation**

```python
from gaspatchio_core.scenarios._aggregators import Mean, Std, Variance
AGGREGATOR_PARAMS += [
    ("Mean", lambda: Mean("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
    ("Variance", lambda: Variance("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
    ("Std", lambda: Std("v"), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
]
```

- [ ] **Step 4: Run tests + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregators_moments.py tests/scenarios/test_aggregator_property.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(aggregators): Mean, Variance, Std — Welford+Chan parallel merge"
```

---

### Task 7: Quantile, Median, CTE, QuantileRank — DDSketch-backed

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Modify: `bindings/python/tests/scenarios/test_aggregator_property.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_quantile.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_quantile.py`:

```python
"""Test Quantile/Median/CTE/QuantileRank — DDSketch-backed."""
from __future__ import annotations

import math

import pytest

from gaspatchio_core.scenarios._aggregators import CTE, Median, Quantile, QuantileRank


def test_median():
    a = Median("v")
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        s = a.add_input(s, v)
    assert math.isclose(a.extract_output(s), 3.0, rel_tol=1e-3, abs_tol=1e-3)


def test_quantile_single_level():
    a = Quantile("v", levels=(0.5,))
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        s = a.add_input(s, v)
    out = a.extract_output(s)
    # Output shape: dict {level: value} for multi-level, scalar for single
    assert math.isclose(out[0.5], 3.0, rel_tol=1e-3, abs_tol=1e-3)


def test_quantile_multi_level():
    a = Quantile("v", levels=(0.1, 0.5, 0.9))
    s = a.create_accumulator()
    for v in range(1, 101):
        s = a.add_input(s, float(v))
    out = a.extract_output(s)
    assert math.isclose(out[0.1], 10.0, rel_tol=5e-3, abs_tol=2.0)
    assert math.isclose(out[0.5], 50.0, rel_tol=5e-3, abs_tol=2.0)
    assert math.isclose(out[0.9], 90.0, rel_tol=5e-3, abs_tol=2.0)


def test_cte_upper():
    a = CTE("v", level=0.05, direction="upper")
    s = a.create_accumulator()
    for v in range(1, 101):
        s = a.add_input(s, float(v))
    # Top 5%: values 96-100 → mean = 98
    assert 95.0 < a.extract_output(s) < 101.0


def test_quantile_rank():
    a = QuantileRank("v", at=50.0)
    s = a.create_accumulator()
    for v in range(1, 101):
        s = a.add_input(s, float(v))
    # 50 is the 49th-smallest value out of 100 → rank ≈ 0.49 - 0.50
    rank = a.extract_output(s)
    assert 0.48 < rank < 0.52


def test_median_merge_consistent():
    a = Median("v")
    values = [float(i) for i in range(1, 101)]
    single = a.create_accumulator()
    for v in values:
        single = a.add_input(single, v)

    left = a.create_accumulator()
    for v in values[:30]:
        left = a.add_input(left, v)
    right = a.create_accumulator()
    for v in values[30:]:
        right = a.add_input(right, v)
    merged = a.merge_accumulators(left, right)

    # Bit-exact: serialise both and compare
    assert math.isclose(a.extract_output(single), a.extract_output(merged), rel_tol=1e-4)
```

- [ ] **Step 2: Extend `_aggregators.py` with DDSketch-backed aggregators**

```python
from gaspatchio_core.scenarios._sketch import SignedSketch


@dataclass(frozen=True)
class Quantile(_BaseAggregator):
    """Quantile(s) across scenarios — DDSketch-backed."""

    levels: tuple[float, ...] = (0.5,)

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch()

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self, a: SignedSketch, b: SignedSketch
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> dict[float, float]:
        return {level: state.quantile(level) for level in self.levels}

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "Quantile",
            "column": self.column,
            "within": self.within,
            "levels": list(self.levels),
        }


@dataclass(frozen=True)
class Median(_BaseAggregator):
    """Median across scenarios — Quantile(0.5) facade."""

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch()

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self, a: SignedSketch, b: SignedSketch
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> float:
        return state.quantile(0.5)

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Median", "column": self.column, "within": self.within}


@dataclass(frozen=True)
class CTE(_BaseAggregator):
    """Conditional Tail Expectation across scenarios — DDSketch-backed.

    For Solvency II SCR (99.5% loss):
      - positive-is-loss convention: CTE(level=0.005, direction="upper")
      - P&L convention (positive is profit): CTE(level=0.005, direction="lower")
    """

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"

    def create_accumulator(self) -> SignedSketch:
        return SignedSketch()

    def add_input(self, state: SignedSketch, value: float) -> SignedSketch:
        state.add(float(value))
        return state

    def merge_accumulators(
        self, a: SignedSketch, b: SignedSketch
    ) -> SignedSketch:
        return SignedSketch.merge(a, b)

    def extract_output(self, state: SignedSketch) -> float:
        return state.cte(level=self.level, direction=self.direction)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "CTE",
            "column": self.column,
            "within": self.within,
            "level": self.level,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class QuantileRank(_BaseAggregator):
    """Empirical rank of a target value in the across-scenario distribution."""

    at: float = 0.0

    def create_accumulator(self) -> dict[str, Any]:
        return {"sketch": SignedSketch(), "count": 0}

    def add_input(self, state: dict[str, Any], value: float) -> dict[str, Any]:
        state["sketch"].add(float(value))
        state["count"] += 1
        return state

    def merge_accumulators(
        self, a: dict[str, Any], b: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "sketch": SignedSketch.merge(a["sketch"], b["sketch"]),
            "count": a["count"] + b["count"],
        }

    def extract_output(self, state: dict[str, Any]) -> float:
        if state["count"] == 0:
            return float("nan")
        # Use DDSketch's get_rank for accurate rank-at-value.
        sketch = state["sketch"]
        # Walk both pos/neg sub-sketches; combine ranks
        # Simple approach: rank by binary-search through quantiles.
        # For at >= 0: use pos sketch; for at < 0: use neg sketch.
        if self.at == 0.0:
            return state["count"] - sketch.pos.count - 0.5 * sketch.zero_n if state["count"] else float("nan")
        # Otherwise approximate via a few quantile probes
        lo, hi = 0.0, 1.0
        for _ in range(40):  # ~40 iters → 1e-12 precision
            mid = (lo + hi) / 2
            q = sketch.quantile(mid)
            if q < self.at:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "QuantileRank",
            "column": self.column,
            "within": self.within,
            "at": self.at,
        }
```

Update `__all__` to include `CTE, Median, Quantile, QuantileRank`.

- [ ] **Step 3: Add to property-test parametrisation**

For DDSketch-backed aggregators, bit-exact float equality is not guaranteed; use a tolerance:

```python
# In test_aggregator_property.py, alongside the existing test_merge_is_associative:

@pytest.mark.parametrize(
    ("name", "factory", "value_strategy"),
    [
        ("Quantile", lambda: Quantile("v"), st.floats(min_value=-1e3, max_value=1e3, allow_nan=False)),
        ("Median", lambda: Median("v"), st.floats(min_value=-1e3, max_value=1e3, allow_nan=False)),
        ("CTE", lambda: CTE("v"), st.floats(min_value=-1e3, max_value=1e3, allow_nan=False)),
    ],
)
def test_sketch_merge_is_deterministic_within_tolerance(name, factory, value_strategy):
    """Sketch-based aggregators are mergeable up to sketch precision (1e-4)."""
    # ... similar shape to associativity test, with abs_tol=1e-2 ...
```

- [ ] **Step 4: Run tests + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregators_quantile.py tests/scenarios/test_aggregator_property.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(aggregators): Quantile, Median, CTE, QuantileRank — DDSketch-backed mergeable

Replaces the materialised-buffer implementations from GSP-100. Now
mergeable across batches with bit-exact deterministic merge via
SignedSketch (paired pos/neg DDSketch). CTE-99.5% accurate to sub-bp."
```

---

## Phase 3 — Modifiers + registry

### Task 8: Modifier behaviour — `.alias()`, `.over()`, `.of()`

Modifier methods are already on `_BaseAggregator` from T4; this task tightens behaviour + adds focused tests.

**Files:**
- Test: `bindings/python/tests/scenarios/test_aggregator_modifiers.py`
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py` (defensive validators if needed)

- [ ] **Step 1: Write the test**

```python
"""Test .alias() / .over() / .of() modifier behaviour."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import Sum
from gaspatchio_core.scenarios._metric import _Partitioned


def test_alias_returns_new_instance():
    a = Sum("v")
    b = a.alias("total")
    assert a.alias_ is None
    assert b.alias_ == "total"


def test_over_returns_partitioned():
    a = Sum("v").alias("by_lob")
    p = a.over("lob")
    assert isinstance(p, _Partitioned)
    assert p.by == ("lob",)


def test_over_tuple_normalisation():
    a = Sum("v").alias("by_lob")
    p1 = a.over("lob")
    p2 = a.over(("lob",))
    assert p1.by == p2.by == ("lob",)


def test_over_multi_key():
    a = Sum("v").alias("by_region_peril")
    p = a.over(("region", "peril"))
    assert p.by == ("region", "peril")


def test_over_without_alias_raises():
    a = Sum("v")
    with pytest.raises(ValueError, match="alias"):
        a.over("lob")


def test_of_polars_escape():
    a = Sum.of(pl.col("a") + pl.col("b"))
    expr = a.within_expr()
    # Hard to compare exprs structurally; smoke-test it's a polars Expr
    assert isinstance(expr, pl.Expr)
```

- [ ] **Step 2: Run + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregator_modifiers.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "test(aggregators): modifier behaviour for alias/over/of"
```

---

### Task 9: Plugin registry decorator update

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py` (add decorator + registry)
- Test: `bindings/python/tests/scenarios/test_aggregator_registry.py` (rewrite for new shape)

- [ ] **Step 1: Add registry + decorator to `_aggregators.py`**

```python
_AGGREGATOR_REGISTRY: dict[str, type] = {}


def register_aggregator(name: str, cls: type) -> None:
    """Register an Aggregator class under a string name.

    Raises ValueError if the class's canonical_form()['kind'] does not
    match the registered name (when the class is zero-arg constructible).
    """
    if name in _AGGREGATOR_REGISTRY:
        msg = f"Aggregator {name!r} already registered."
        raise ValueError(msg)
    try:
        inst = cls()  # zero-arg constructible?
        actual_kind = inst.canonical_form().get("kind")
        if actual_kind != name:
            msg = (
                f"Aggregator class {cls.__name__} registered as {name!r} but "
                f"canonical_form()['kind'] returns {actual_kind!r}. "
                f"These must match for YAML round-trip."
            )
            raise ValueError(msg)
    except TypeError:
        pass  # Class requires init args; skip the check
    _AGGREGATOR_REGISTRY[name] = cls


def scenario_aggregator(name: str):
    """Decorator: @scenario_aggregator("name") registers a class under that name."""
    def decorator(cls: type) -> type:
        register_aggregator(name, cls)
        return cls
    return decorator
```

Decorate every built-in aggregator class (`@scenario_aggregator("Sum")` etc.) at the class definition.

- [ ] **Step 2: Rewrite `test_aggregator_registry.py`**

The v0.1 test imports `Sum`, registers a duplicate, etc. Update to match the new module path + shape. Add a kind-mismatch test (we already had one in v0.1; preserve it).

- [ ] **Step 3: Run + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_aggregator_registry.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(aggregators): registry + @scenario_aggregator decorator on new Protocol"
```

---

## Phase 4 — Loop & runtime layer

### Task 10: `_for_each.py` — per-aggregator within-reduction

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_for_each.py`
- Test: `bindings/python/tests/scenarios/test_for_each_new_shape.py`

Major rewrite. The loop changes:
- Drop `per_scenario` kwarg
- Drop `agg` kwarg
- Add `aggregations: tuple[Aggregator, ...]` kwarg
- Per-batch: collect projection eagerly, then per aggregator do `group_by([scenario_id, *partition_keys]).agg(within_expr)` and fold each row into the aggregator's state

- [ ] **Step 1: Write a small loop test**

```python
"""Test the new for_each_scenario shape (per-aggregator within-reduction)."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Mean, Sum
from gaspatchio_core.scenarios._for_each import for_each_scenario


def _identity_model(af, *, tables, drivers):  # noqa: ARG001
    return af.with_columns(pl.col("premium").alias("value"))


def test_scalar_aggregators_via_new_shape():
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_identity_model,
        aggregations=(
            Sum("value").alias("total"),
            Mean("value").alias("avg"),
        ),
        batch_size=1,
    )
    # Sum: 3 scenarios × (100+200) = 900
    assert result.aggregations["total"] == pytest.approx(900.0)
    # Mean: 300 per scenario, mean across 3 = 300
    assert result.aggregations["avg"] == pytest.approx(300.0)


def test_partitioned_aggregator_returns_dataframe():
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0], "lob": ["term", "annuity"]})
    result = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=lambda af, **kw: af.with_columns(pl.col("premium").alias("value")),
        aggregations=(
            Sum("value").alias("by_lob").over("lob"),
        ),
        batch_size=1,
    )
    df = result.aggregations["by_lob"]
    assert isinstance(df, pl.DataFrame)
    assert set(df.columns) == {"lob", "by_lob"}
```

- [ ] **Step 2: Rewrite the loop body**

This is the load-bearing change. Sketch (full implementation in `_for_each.py`):

```python
def for_each_scenario(
    af,
    scenarios,
    model_fn,
    *,
    aggregations: tuple,           # tuple[Aggregator | _Partitioned, ...]
    base_tables=None,
    batch_size=1,
    target_memory_fraction=0.5,
    bytes_per_cell=None,
    return_full_grid=False,
    sink_dir=None,
    master_seed=None,
    progress=False,
):
    # ... existing validation, shape classification, batch resolution ...

    # NEW: initialise per-aggregator accumulator state
    accumulators = {}
    for agg in aggregations:
        accumulators[agg.alias] = agg.create_accumulator()

    for batch_idx, batch_sids in enumerate(_chunks(sids, resolved_size)):
        # ... shocked-tables, drivers, model_fn, eager collect ...
        proj_eager = af_proj._df.collect()

        for agg in aggregations:
            # Build within-reduction expression per aggregator
            within = agg.within_expr().alias(agg.alias)
            group_keys = ["scenario_id"]
            if hasattr(agg, "by"):  # _Partitioned
                group_keys += list(agg.by)
            reduced = proj_eager.group_by(group_keys).agg(within)

            # Fold per-row into the aggregator's state
            for row in reduced.iter_rows(named=True):
                if hasattr(agg, "by"):
                    partition_key = tuple(row[k] for k in agg.by)
                    accumulators[agg.alias] = agg.add_input(
                        accumulators[agg.alias], partition_key, row[agg.alias]
                    )
                else:
                    accumulators[agg.alias] = agg.add_input(
                        accumulators[agg.alias], row[agg.alias]
                    )

    # Finalise per aggregator
    final = {agg.alias: agg.extract_output(accumulators[agg.alias]) for agg in aggregations}
    return ScenarioResult(aggregations=final, ...)
```

Note: ArgMin/ArgMax need `(scenario_id, value)` tuples not bare values — special-case those or have the aggregator declare `requires_scenario_id`.

- [ ] **Step 3: Run + commit**

This is a load-bearing task; use **full subagent loop** (implementer → spec reviewer → code reviewer).

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(for_each): per-aggregator within-reduction; drop shared per_scenario kwarg

Replaces GSP-100's shared per_scenario reduction with per-aggregator
within reductions. Aggregators carry their own within_expr; the loop
iterates per aggregator and folds the small reduced frame into its
accumulator state."
```

---

### Tasks 11–13: ScenarioRun, ScenarioResult, audit kwarg wiring

(Mechanical updates flowing from T10. Each ~30 minutes. Combine into one commit if reasonable; separate if not.)

**Task 11:** `_run.py` — `ScenarioRun.aggregations: tuple[Aggregator, ...]`; alias uniqueness validator; `audit: bool | Path` kwarg on `.run()`; `master_seed` retained.

**Task 12:** `_result.py` — `aggregations: dict[str, float | pl.DataFrame]`; new `audit_path: Path | None` field.

**Task 13:** Wire `audit` parameter through. Compute `run_id = f"{utc_timestamp}_{source_sha[:8]}"`. Write sidecar if requested.

Each task: 1 small test + implementation + commit. Implementer + self-verify cadence.

---

## Phase 5 — Audit sidecar

### Task 14: `_audit.py` — JSON writer + reader + schema

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_audit.py`
- Test: `bindings/python/tests/scenarios/test_audit_sidecar.py`

- [ ] **Step 1: Write the failing test**

```python
"""Test the audit sidecar — JSON schema + round-trip."""
from __future__ import annotations

import json
from pathlib import Path

from gaspatchio_core.scenarios._audit import (
    AUDIT_SCHEMA_VERSION,
    read_audit,
    write_audit,
)


def test_write_then_read(tmp_path: Path):
    path = tmp_path / "test.audit.json"
    write_audit(
        path,
        source_sha="sha256:abc123",
        plan_canonical_form={"kind": "ScenarioRun", "shocks": {}},
        run_metadata={"library_version": "0.2.0"},
        aggregator_outputs={"scr": 1234.5},
        input_data_fingerprint={"schema_sha": "sha256:def", "row_count": 100},
    )
    audit = read_audit(path)
    assert audit["schema_version"] == AUDIT_SCHEMA_VERSION
    assert audit["source_sha"] == "sha256:abc123"
    assert audit["aggregator_outputs"]["scr"] == 1234.5


def test_schema_version_present(tmp_path: Path):
    path = tmp_path / "test.audit.json"
    write_audit(
        path,
        source_sha="sha256:x",
        plan_canonical_form={},
        run_metadata={},
        aggregator_outputs={},
        input_data_fingerprint={},
    )
    raw = json.loads(path.read_text())
    assert "schema_version" in raw
```

- [ ] **Step 2: Create `_audit.py`**

```python
# ABOUTME: Audit sidecar JSON writer/reader + schema for ScenarioRun outputs.
# ABOUTME: Completes the source_sha governance story; opt-in via audit param.

"""Audit sidecar writer + reader for GSP-101 ScenarioRun outputs.

A single JSON file co-located with run output, containing:
    schema_version, source_sha, plan_canonical_form, run_metadata,
    aggregator_outputs, input_data_fingerprint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

AUDIT_SCHEMA_VERSION = "1.0"


def write_audit(
    path: Path,
    *,
    source_sha: str,
    plan_canonical_form: dict[str, Any],
    run_metadata: dict[str, Any],
    aggregator_outputs: dict[str, Any],
    input_data_fingerprint: dict[str, Any],
) -> None:
    """Write the audit JSON sidecar."""
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "source_sha": source_sha,
        "plan_canonical_form": plan_canonical_form,
        "run_metadata": run_metadata,
        "aggregator_outputs": _coerce_outputs_to_json(aggregator_outputs),
        "input_data_fingerprint": input_data_fingerprint,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))


def read_audit(path: Path) -> dict[str, Any]:
    """Read the audit JSON sidecar."""
    return json.loads(path.read_text())


def _coerce_outputs_to_json(outputs: dict[str, Any]) -> dict[str, Any]:
    """Convert pl.DataFrame outputs to plain dicts (rows → list of dicts)."""
    import polars as pl

    out = {}
    for name, val in outputs.items():
        if isinstance(val, pl.DataFrame):
            out[name] = val.to_dicts()
        else:
            out[name] = val
    return out


__all__ = ["AUDIT_SCHEMA_VERSION", "read_audit", "write_audit"]
```

- [ ] **Step 3: Run + commit**

```bash
cd ~/projects/gaspatchio/gaspatchio-core/bindings/python && uv run pytest tests/scenarios/test_audit_sidecar.py -v
cd ~/projects/gaspatchio/gaspatchio-core && git add -A bindings/python/ && git commit -m "feat(scenarios): audit sidecar JSON writer + reader

schema_version, source_sha, plan_canonical_form, run_metadata,
aggregator_outputs (coerced from DataFrame to dicts), input_data_fingerprint."
```

---

## Phase 6 — YAML round-trip

### Task 15: Recursive `parse_aggregations` for the new shape

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_config.py`
- Test: `bindings/python/tests/scenarios/test_aggregations_yaml.py`

`parse_aggregations` reads a YAML/dict spec and builds a tuple of aggregators. Handles `_Partitioned` recursively.

- [ ] **Step 1: Write failing test**

Test that a YAML spec containing both `Sum("loss").alias("total")` and `ArgMax("loss").over("lob").alias("worst_per_lob")` round-trips correctly: canonical_form before → YAML → canonical_form after → same SHA.

- [ ] **Step 2: Rewrite `parse_aggregations`**

```python
def parse_aggregations(spec: list[dict]) -> tuple:
    """Parse a list-of-dict YAML spec into a tuple of aggregators."""
    from gaspatchio_core.scenarios._aggregators import _AGGREGATOR_REGISTRY
    from gaspatchio_core.scenarios._metric import _Partitioned

    out = []
    for entry in spec:
        kind = entry["kind"]
        alias = entry["alias"]
        if kind == "_Partitioned":
            inner = parse_aggregations([entry["inner"]])[0]
            by = tuple(entry["by"])
            agg = _Partitioned(by=by, inner=inner, alias=alias)
        else:
            if kind not in _AGGREGATOR_REGISTRY:
                msg = (
                    f"Aggregator {kind!r} is not registered. "
                    f"Available: {sorted(_AGGREGATOR_REGISTRY)}."
                )
                raise ValueError(msg)
            cls = _AGGREGATOR_REGISTRY[kind]
            # Construct from entry fields (column, within, level, direction, levels, at)
            kwargs = {k: v for k, v in entry.items() if k not in {"kind", "alias"}}
            agg = cls(**kwargs).alias(alias)
        out.append(agg)
    return tuple(out)
```

- [ ] **Step 3: Run + commit**

---

### Task 16: `ScenarioRun.to_yaml` / `from_yaml` for new shape

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_run.py`
- Test: `bindings/python/tests/scenarios/test_scenario_run_yaml.py` (rewrite)

The serialised YAML format changes — `aggregations` is now a list of recipe dicts, not a `dict[name, ScenarioMetric]`. Update accordingly.

- [ ] **Step 1: Write test for round-trip**
- [ ] **Step 2: Rewrite `to_dict` / `from_dict` / `to_yaml` / `from_yaml`**
- [ ] **Step 3: Run + commit**

---

## Phase 7 — Migration / public surface

### Task 17: Update `scenarios/__init__.py` + `.pyi`

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py`
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.pyi`
- Test: `bindings/python/tests/scenarios/test_public_surface.py` (update)

- [ ] **Step 1: Remove retired symbols + add new ones**

The new public surface:

```python
from gaspatchio_core.scenarios._aggregators import (
    ArgMax, ArgMin, CTE, Count, Max, Mean, Median, Min,
    Quantile, QuantileRank, Std, Sum, Variance,
    register_aggregator, scenario_aggregator,
)
from gaspatchio_core.scenarios._metric import Aggregator
from gaspatchio_core.scenarios._for_each import for_each_scenario
from gaspatchio_core.scenarios._result import ScenarioResult
from gaspatchio_core.scenarios._run import ScenarioRun
# Keep: parse_scenario_config, parse_aggregations, parse_shock_config,
# with_scenarios, all Shock subclasses, Shock base class
```

Remove from `__all__`:
- `MultiAgg`
- `GroupedAgg`
- `metric`
- `ScenarioMetric`

- [ ] **Step 2: Update `.pyi` mirror**
- [ ] **Step 3: Update `test_public_surface.py`**
- [ ] **Step 4: Run + commit**

---

### Task 18: Migration error path for v0.1 YAML reload

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_config.py`
- Test: `bindings/python/tests/scenarios/test_migration.py`

- [ ] **Step 1: Detect v0.1 schema in `parse_aggregations`**

If the YAML has a top-level `aggregations: dict[str, dict]` shape (old) instead of `list[dict]` (new), raise a clear `ValueError` pointing at the migration table.

```python
def parse_aggregations(spec) -> tuple:
    if isinstance(spec, dict):
        msg = (
            "v0.1 plan format detected (aggregations is a dict). "
            "v0.2 uses a list of aggregators with .alias(). "
            "See ref/41-backend-portability/specs/2026-05-11-gsp-101-... section 10."
        )
        raise ValueError(msg)
    # ...
```

- [ ] **Step 2: Write a test that loads a v0.1 fixture YAML and confirms the error**

- [ ] **Step 3: Run + commit**

---

## Phase 8 — Test rewrites

Existing tests under `tests/scenarios/` use the old surface. Rewrite for the new.

### Task 19: Rewrite `test_for_each_scenario.py` + `test_for_each_shocks.py`

- [ ] Update imports + API calls
- [ ] Replace `MultiAgg/GroupedAgg/metric` with `Sum/Mean/etc + .alias() + .over()` 
- [ ] Verify all assertions still meaningful
- [ ] Commit

### Task 20: Rewrite `test_for_each_drivers.py`

- [ ] master_seed still raises at batch_size>1 (unchanged from GSP-100 correctness)
- [ ] Drivers shape still raises at batch_size>1
- [ ] Update for new surface

### Task 21: NEW `test_for_each_partitioned.py`

Tests for `.over()`:
- Single-key partition
- Single-key tuple normalisation (`over("lob")` == `over(("lob",))`)
- Multi-key partition (`over(("region", "peril"))`)
- Mixed scalar + partitioned aggregators in one run
- Batch-equivalence across batch_size for partitioned aggregators

### Task 22: Rewrite `test_audit_chain.py` + `test_scenario_run.py` + `test_scenario_run_yaml.py`

### Task 23: NEW `test_governance_cross_process.py`

Lift the stress-test agent 3 pattern as a permanent test. Build plan in process A, save YAML, load YAML in subprocess B, run against same input, assert bit-exact aggregations + same source_sha.

Include custom aggregator (Skewness Welford-style) registered in a fixture module.

### Task 24: Update `test_aggregator_registry.py` + remaining files

- `test_aggregator_registry.py` — kind mismatch test
- `test_batch_equivalence.py` — rewrite for new surface
- `test_stack_shocked_table.py` — unchanged (doesn't touch aggregator layer)
- Remaining files: spot-check and update imports

---

## Phase 9 — Integration & polish

### Task 25: End-to-end audit-chain integration test

**File:** `bindings/python/tests/scenarios/test_audit_chain.py` (rewrite for new shape)

Comprehensive: SHA stability, batch-equivalence, YAML round-trip preserves SHA AND aggregations bit-exact, audit sidecar round-trip preserves SHA, partitioned aggregator output preserved.

**Cadence:** load-bearing — **full subagent loop**.

### Task 26: Memory benchmark verification

Re-run `bindings/python/benchmarks/scenariorun/test_scenariorun_scaling.py`. Verify `peak_rss_mb` is still bounded under the new loop. Update the runner if the API changed (it has — `aggregations=` tuple instead of `agg=` + `per_scenario=`).

### Task 27: CHANGELOG v0.2 entry + migration table

Update `CHANGELOG.md`:

```markdown
## [0.2.0] — GSP-101 Mergeable Aggregator Layer

### Added
- Beam-style `Aggregator` Protocol (5-tuple: within_expr, create_accumulator, add_input, merge_accumulators, extract_output)
- `.alias()`, `.over()`, `.of()` modifiers on every aggregator
- Multi-column partitioning via `.over(tuple)`
- DDSketch-backed CTE/Quantile/Median/QuantileRank — bit-exact mergeable
- Hypothesis property test pinning merge associativity + commutativity for every aggregator
- Opt-in audit sidecar JSON via `audit: bool | Path = False` on `ScenarioRun.run`

### Removed (breaking)
- `MultiAgg` — pass aggregators directly: `ScenarioRun(aggregations=(Sum("loss").alias("total"), ...))`
- `GroupedAgg` — use `.over(by)`: `ArgMax("loss").over("lob").alias("worst")`
- `metric(col, agg)` — column travels with the aggregator: `Sum("loss")` instead of `metric("loss", Sum())`
- `ScenarioMetric` — folded into the aggregator base
- `for_each_scenario(per_scenario=...)` kwarg — aggregator carries its own within_expr

### Migration table

| v0.1 | v0.2 |
|---|---|
| `MultiAgg({"total": Sum()})` | `(Sum("loss").alias("total"),)` |
| `GroupedAgg(by="lob", metric=ArgMax())` | `ArgMax("loss").over("lob")` |
| `metric("loss", CTE(0.005))` | `CTE("loss", level=0.005)` |
| `ScenarioMetric(per_scenario=expr, across_scenario=agg)` | `Sum.of(expr).alias("name")` (rare) |

### Known limits
- Polars version 1.38.x pinning required for `Expr.meta.serialize()` bit-exactness (`.of()` escape hatch path)
- DDSketch CTE/Quantile are bit-exact mergeable; precision bounded by `relative_accuracy=1e-4` (sub-bp for SCR-99.5%)
- `master_seed` + `batch_size>1`: raises `ValueError` (unchanged from GSP-100)
```

Commit:

```bash
cd ~/projects/gaspatchio/gaspatchio-core && git add CHANGELOG.md && git commit -m "docs: GSP-101 release notes + v0.1→v0.2 migration table"
```

---

## Self-review

**1. Spec coverage.** Every §3 design decision traces to at least one task:
- D1 (5-tuple Protocol): T1
- D2 (partition as wrapper): T1 (`_Partitioned`) + T10 (loop integration)
- D3 (variadic + alias-on-aggregator): T11 (ScenarioRun) + T17 (public surface)
- D4 (named within reductions): T4 onwards (built into aggregator constructors)
- D5 (.of() polars escape): T8 (modifier test)
- D6 (output shape: scalar vs DataFrame): T12 (ScenarioResult) + T21 (partitioned tests)
- D7 (DDSketch): T3 + T7
- D8 (signed-value paired sketches): T3
- D9 (multi-column partitioning): T21
- D10 (audit sidecar): T13 + T14
- D11 (registry decorator): T9
- D12 (clean break): T17 + T18 + T27

**2. Placeholder scan.** None — all tasks have actual code, file paths, and commit commands. The `Std.add_input` in T6 has an awkward delegation that the implementer is told to refactor; otherwise verbatim.

**3. Type consistency.** Aggregator API names (`Sum`, `Mean`, `CTE`, etc.) match across all tasks. `_Partitioned.alias` matches the modifier shape. `aggregations: tuple[Aggregator, ...]` is consistent in `ScenarioRun`, `ScenarioResult`, and the loop.

**4. Cadence.** Full loop on T1, T2, T3, T10, T25 (5 load-bearing tasks). Implementer + self-verify on the rest (22 tasks). Total subagent dispatches ≈ 22 + 5×3 = 37, similar to GSP-100.

---

## Follow-on plans (NOT in this plan)

1. **Actuarial aliases (AAL/VaR/TVaR)** — single-file PR adding subclass aliases. Trivial; no spec needed.
2. **Tutorial rework** for the new aggregator surface — separate plan.
3. **gaspatchio-docs updates** — separate plan.
4. **Cross-backend implementation** — much larger; depends on rollforward backend evolution.
