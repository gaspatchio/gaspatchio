# GSP-100 ScenarioRun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core `ScenarioRun` + `for_each_scenario` bounded-memory stochastic runner library code per the design at `ref/41-backend-portability/specs/2026-05-11-gsp-100-scenariorun-design.md`. Tutorial rework and `gaspatchio-docs` updates are tracked as separate follow-on plans.

**Architecture:** Identity foundation (extract shared `canonical_bytes`; add `Table` identity; add `Shock` identity) → aggregator framework (Protocol + 15 starters + plugin registry + `ScenarioMetric`) → loop machinery (`stack_shocked_table`, `_auto_batch`, `_for_each`) → plan layer (`ScenarioRun` + delegation + YAML round-trip) → wiring + decommissioning.

**Tech Stack:** Python 3.12, Polars 1.x (with `pl.Expr.meta.serialize()`), pydantic v2, pytest, Hypothesis, Loguru, psutil. Project uses `uv` for everything: `uv run pytest -v` to test.

**Working directory for all commands:** `~/projects/gaspatchio/gaspatchio-core/bindings/python/`

**Branch:** `gsp-100-scenariorun-bounded-memory`

---

## Phase 1 — Identity foundation

### Task 1: Extract `canonical_bytes` to top-level `_identity.py`

`canonical_bytes` currently lives at `gaspatchio_core/schedule/_canonical.py` and is imported by Schedule, Curve, and MortalityTable. Lift it (and add a `source_sha_of` helper) to a top-level module so Table and ScenarioRun can use it without depending on `schedule/`.

**Files:**
- Create: `bindings/python/gaspatchio_core/_identity.py`
- Modify: `bindings/python/gaspatchio_core/schedule/_canonical.py` (re-export from new location)
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py:46` (import path)
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py:29` (import path)
- Modify: `bindings/python/gaspatchio_core/mortality/_mortality_table.py:32` (import path)
- Test: `bindings/python/tests/test_identity.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/test_identity.py`:

```python
"""Test the shared canonical_bytes + source_sha_of helpers."""
from __future__ import annotations

import pytest

from gaspatchio_core._identity import canonical_bytes, source_sha_of


def test_canonical_bytes_sorts_keys():
    assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_canonical_bytes_separators_compact():
    assert canonical_bytes({"a": 1}) == b'{"a":1}'


def test_canonical_bytes_rejects_nan():
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})


def test_canonical_bytes_rejects_unknown_types():
    class Custom:
        pass

    with pytest.raises(TypeError):
        canonical_bytes({"x": Custom()})


def test_source_sha_of_format():
    sha = source_sha_of({"a": 1})
    assert sha.startswith("sha256:")
    assert len(sha) == len("sha256:") + 64


def test_source_sha_of_determinism():
    sha1 = source_sha_of({"a": 1, "b": 2})
    sha2 = source_sha_of({"b": 2, "a": 1})
    assert sha1 == sha2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_identity.py -v
```

Expected: `ModuleNotFoundError: No module named 'gaspatchio_core._identity'`

- [ ] **Step 3: Create `_identity.py`**

Create `bindings/python/gaspatchio_core/_identity.py`:

```python
# ABOUTME: Shared canonical-form encoding and source SHA helpers.
# ABOUTME: Used by Schedule, Curve, MortalityTable, Table, and ScenarioRun.

"""Deterministic JSON encoding + SHA-256 helpers for the audit chain."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _raise_on_unknown(val: Any) -> Any:
    msg = f"canonical_bytes: cannot encode {type(val).__name__} ({val!r})"
    raise TypeError(msg)


def canonical_bytes(form: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for canonical_form dicts.

    Rules:
        - ``sort_keys=True`` at every level
        - ``separators=(',', ':')`` — no insignificant whitespace
        - ``ensure_ascii=True`` — stable bytes across platforms
        - ``allow_nan=False`` — explicit NaN raises (caller responsibility)
        - unknown types raise ``TypeError`` (no silent ``str()`` fallback)
    """
    return json.dumps(
        form,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_raise_on_unknown,
    ).encode("utf-8")


def source_sha_of(form: dict[str, Any]) -> str:
    """Return ``sha256:<hex>`` over ``canonical_bytes(form)``."""
    digest = hashlib.sha256(canonical_bytes(form)).hexdigest()
    return f"sha256:{digest}"


__all__ = ["canonical_bytes", "source_sha_of"]
```

- [ ] **Step 4: Update `schedule/_canonical.py` to re-export**

Read `bindings/python/gaspatchio_core/schedule/_canonical.py` first. Then replace its contents with:

```python
# ABOUTME: Backwards-compatible re-export of canonical_bytes from gaspatchio_core._identity.
# ABOUTME: New code should import from gaspatchio_core._identity directly.

"""Re-export of the shared canonical helper."""

from gaspatchio_core._identity import canonical_bytes

__all__ = ["canonical_bytes"]
```

- [ ] **Step 5: Update three import sites**

Edit `bindings/python/gaspatchio_core/schedule/_schedule.py` line 46:

Replace:
```python
from gaspatchio_core.schedule._canonical import canonical_bytes
```
With:
```python
from gaspatchio_core._identity import canonical_bytes
```

Edit `bindings/python/gaspatchio_core/curves/_curve.py` line 29: same replacement.

Edit `bindings/python/gaspatchio_core/mortality/_mortality_table.py` line 32: same replacement.

- [ ] **Step 6: Run tests to verify pass**

```bash
uv run pytest tests/test_identity.py tests/schedule/ tests/curves/ tests/mortality/ -v
```

Expected: all green. Schedule/Curve/MortalityTable existing tests continue to pass.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/_identity.py \
        bindings/python/gaspatchio_core/schedule/_canonical.py \
        bindings/python/gaspatchio_core/schedule/_schedule.py \
        bindings/python/gaspatchio_core/curves/_curve.py \
        bindings/python/gaspatchio_core/mortality/_mortality_table.py \
        bindings/python/tests/test_identity.py
git commit -m "refactor(identity): lift canonical_bytes to top-level _identity module

Adds source_sha_of helper for downstream consumers (Table, ScenarioRun).
schedule/_canonical.py becomes a thin re-export; Schedule/Curve/MortalityTable
import from the new location."
```

---

### Task 2: Add `Shock.canonical_form` on base class + auto-encoder

The 11 existing `Shock` dataclasses don't have `canonical_form` today. Add a default implementation on the `Shock` ABC that introspects `__dataclass_fields__`. Nested shock types (`PipelineShock`, `FilteredShock`, `TimeConditionalShock`, `MaxShock`, `MinShock`) recurse via the field encoder.

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/shocks.py` (add `canonical_form` to `Shock` ABC + `_encode_field` static method)
- Test: `bindings/python/tests/scenarios/test_shocks_canonical.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_shocks_canonical.py`:

```python
"""Test Shock.canonical_form for all 11 subclasses."""
from __future__ import annotations

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    RelativeFloorShock,
    TimeConditionalShock,
)


def test_multiplicative_canonical_form():
    shock = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    cf = shock.canonical_form()
    assert cf == {
        "kind": "MultiplicativeShock",
        "column": None,
        "factor": 1.15,
        "table": "mortality",
    }


def test_additive_canonical_form():
    shock = AdditiveShock(delta=0.005, table="rates", column="value")
    cf = shock.canonical_form()
    assert cf == {
        "kind": "AdditiveShock",
        "column": "value",
        "delta": 0.005,
        "table": "rates",
    }


def test_pipeline_canonical_form_recurses():
    inner_a = MultiplicativeShock(factor=1.5, table="lapse", column=None)
    inner_b = ClipShock(min_value=None, max_value=1.0, table="lapse", column=None)
    shock = PipelineShock(shocks=(inner_a, inner_b), table="lapse", column=None)
    cf = shock.canonical_form()
    assert cf["kind"] == "PipelineShock"
    assert cf["shocks"][0]["kind"] == "MultiplicativeShock"
    assert cf["shocks"][1]["kind"] == "ClipShock"
    assert cf["shocks"][0]["factor"] == 1.5
    assert cf["shocks"][1]["max_value"] == 1.0


def test_filtered_canonical_form_dict_sorted():
    inner = MultiplicativeShock(factor=2.0, table="mortality", column=None)
    shock = FilteredShock(
        shock=inner,
        where={"duration": {"lte": 5}},
        table="mortality",
        column=None,
    )
    cf = shock.canonical_form()
    assert cf["kind"] == "FilteredShock"
    assert cf["where"] == {"duration": {"lte": 5}}
    assert cf["shock"]["kind"] == "MultiplicativeShock"


def test_time_conditional_canonical_form():
    inner = AdditiveShock(delta=0.001, table="rates", column=None)
    shock = TimeConditionalShock(
        shock=inner,
        when={"t": {"eq": 0}},
        table="rates",
        column=None,
        time_column="t",
    )
    cf = shock.canonical_form()
    assert cf["kind"] == "TimeConditionalShock"
    assert cf["time_column"] == "t"
    assert cf["when"] == {"t": {"eq": 0}}


def test_max_min_canonical_form():
    a = MultiplicativeShock(factor=0.9, table="lapse", column=None)
    b = MultiplicativeShock(factor=1.1, table="lapse", column=None)
    max_shock = MaxShock(shock_a=a, shock_b=b, table="lapse", column=None)
    min_shock = MinShock(shock_a=a, shock_b=b, table="lapse", column=None)
    assert max_shock.canonical_form()["kind"] == "MaxShock"
    assert min_shock.canonical_form()["kind"] == "MinShock"
    assert max_shock.canonical_form()["shock_a"]["factor"] == 0.9


def test_override_canonical_form_scalar():
    shock = OverrideShock(value=0.5, table="mortality", column=None)
    cf = shock.canonical_form()
    assert cf["value"] == 0.5


def test_override_canonical_form_rejects_non_scalar():
    import pytest

    shock = OverrideShock(value=[1, 2, 3], table="mortality", column=None)
    with pytest.raises(TypeError, match="not canonical-encodable"):
        shock.canonical_form()


def test_relative_floor_canonical_form():
    shock = RelativeFloorShock(delta=0.001, table="rates", column=None)
    assert shock.canonical_form()["kind"] == "RelativeFloorShock"


def test_canonical_form_keys_sorted():
    shock = MultiplicativeShock(factor=1.2, table="z_table", column="a_col")
    cf = shock.canonical_form()
    keys = list(cf.keys())
    assert keys == sorted(keys)


def test_two_equal_shocks_same_canonical_form():
    a = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    b = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    assert a.canonical_form() == b.canonical_form()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_shocks_canonical.py -v
```

Expected: `AttributeError: 'MultiplicativeShock' object has no attribute 'canonical_form'`

- [ ] **Step 3: Add `canonical_form` + `_encode_field` to `Shock` base**

Read `bindings/python/gaspatchio_core/scenarios/shocks.py` first to find the `Shock` ABC definition. Add this method to the `Shock` base class (preserve all existing methods):

```python
    def canonical_form(self) -> dict[str, Any]:
        """Deterministic JSON-encodable identity recipe for the audit chain.

        Default implementation introspects ``__dataclass_fields__``;
        subclasses with nested shocks recurse via ``_encode_field``.

        Returns:
            Dict with ``"kind"`` (class name) plus every dataclass field,
            sorted by key. Nested ``Shock`` instances recurse.

        Raises:
            TypeError: If a field value is not JSON-encodable
                (e.g. ``OverrideShock`` with a non-scalar value).
        """
        from dataclasses import fields

        out: dict[str, Any] = {"kind": type(self).__name__}
        for fld in fields(self):
            out[fld.name] = Shock._encode_field(getattr(self, fld.name))
        return dict(sorted(out.items()))

    @staticmethod
    def _encode_field(val: Any) -> Any:
        """Recursive JSON-safe encoding for canonical_form field values."""
        if isinstance(val, Shock):
            return val.canonical_form()
        if isinstance(val, tuple):
            return [Shock._encode_field(v) for v in val]
        if isinstance(val, list):
            return [Shock._encode_field(v) for v in val]
        if isinstance(val, dict):
            return {
                k: Shock._encode_field(v)
                for k, v in sorted(val.items())
            }
        if isinstance(val, (int, float, str, bool, type(None))):
            return val
        msg = f"Shock field {type(val).__name__} not canonical-encodable"
        raise TypeError(msg)
```

If `Any` isn't already imported at the top of `shocks.py`, add `from typing import Any`.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_shocks_canonical.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/shocks.py \
        bindings/python/tests/scenarios/test_shocks_canonical.py
git commit -m "feat(shocks): add canonical_form on Shock ABC

Default implementation introspects dataclass fields; nested shocks
(Pipeline/Filtered/TimeConditional/Max/Min) recurse via _encode_field.
OverrideShock with non-scalar value raises TypeError at canonical_form()
time (documented limitation)."
```

---

### Task 3: Add `Table.canonical_form`, `Table.source_sha`, `Table._content_sha`

Mirror the pattern from Curve/Schedule/MortalityTable. Content hash is row-order-independent via parquet bytes of the sort-canonicalised frame.

**Files:**
- Modify: `bindings/python/gaspatchio_core/assumptions/_api.py` (add three methods to the `Table` class)
- Modify: `bindings/python/gaspatchio_core/assumptions/__init__.pyi` (add stub signatures)
- Test: `bindings/python/tests/assumptions/test_table_identity.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/assumptions/test_table_identity.py`:

```python
"""Test Table.canonical_form / source_sha / _content_sha."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def mortality_df():
    return pl.DataFrame({
        "age": [30, 31, 32, 30, 31, 32],
        "sex": ["M", "M", "M", "F", "F", "F"],
        "rate": [0.001, 0.0012, 0.0015, 0.0008, 0.001, 0.0012],
    })


@pytest.fixture
def mortality_table(mortality_df):
    return Table(
        name="mortality",
        source=mortality_df,
        dimensions={"age": "age", "sex": "sex"},
        value="rate",
    )


def test_canonical_form_shape(mortality_table):
    cf = mortality_table.canonical_form()
    assert cf["kind"] == "Table"
    assert cf["name"] == "mortality"
    assert cf["dimensions"] == ["age", "sex"]  # sorted
    assert cf["value_column"] == "rate"
    assert cf["content_sha"].startswith("sha256:")


def test_source_sha_format(mortality_table):
    sha = mortality_table.source_sha()
    assert sha.startswith("sha256:")
    assert len(sha) == len("sha256:") + 64


def test_two_tables_same_data_same_sha(mortality_df):
    t1 = Table(name="m", source=mortality_df, dimensions={"age": "age", "sex": "sex"}, value="rate")
    t2 = Table(name="m", source=mortality_df, dimensions={"age": "age", "sex": "sex"}, value="rate")
    assert t1.source_sha() == t2.source_sha()


def test_content_sha_row_order_independent(mortality_df):
    t1 = Table(name="m", source=mortality_df, dimensions={"age": "age", "sex": "sex"}, value="rate")
    t2 = Table(
        name="m",
        source=mortality_df.sample(fraction=1.0, shuffle=True, seed=42),
        dimensions={"age": "age", "sex": "sex"},
        value="rate",
    )
    assert t1._content_sha() == t2._content_sha()


def test_shocked_table_has_different_sha(mortality_table):
    shocked = mortality_table.with_shock(MultiplicativeShock(factor=1.2))
    assert mortality_table.source_sha() != shocked.source_sha()


def test_renamed_table_has_different_canonical_form(mortality_df):
    t1 = Table(name="m1", source=mortality_df, dimensions={"age": "age", "sex": "sex"}, value="rate")
    t2 = Table(name="m2", source=mortality_df, dimensions={"age": "age", "sex": "sex"}, value="rate")
    assert t1.source_sha() != t2.source_sha()
    # But content is identical
    assert t1._content_sha() == t2._content_sha()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/assumptions/test_table_identity.py -v
```

Expected: `AttributeError: 'Table' object has no attribute 'canonical_form'`

- [ ] **Step 3: Add three methods to the `Table` class**

Read `bindings/python/gaspatchio_core/assumptions/_api.py` to locate the `Table` class. Add these three methods (place them near `with_shock` for cohesion):

```python
    def canonical_form(self) -> dict[str, Any]:
        """Deterministic JSON-encodable identity recipe for the audit chain.

        Returns:
            Dict with name, sorted dimension keys, value column, and
            row-order-independent content_sha of the underlying data.
        """
        return {
            "kind": "Table",
            "name": self._name,
            "dimensions": sorted(self._dimensions.keys()),
            "value_column": self._value,
            "content_sha": self._content_sha(),
        }

    def source_sha(self) -> str:
        """sha256 over canonical_form bytes. Stable for the same content + name."""
        from gaspatchio_core._identity import source_sha_of
        return source_sha_of(self.canonical_form())

    def _content_sha(self) -> str:
        """Row-order-independent content hash via parquet bytes of sorted frame.

        Algorithm:
            1. Materialise frame as DataFrame.
            2. Select [sorted(dim_names) + [value_column]].
            3. Sort by all dimension columns.
            4. Hash the parquet-serialised bytes (sha256).
        """
        import hashlib
        import io

        df = self._materialised_df()
        dim_cols = sorted(self._dimensions.keys())
        sorted_df = df.select(dim_cols + [self._value]).sort(dim_cols)
        buf = io.BytesIO()
        sorted_df.write_parquet(buf)
        return f"sha256:{hashlib.sha256(buf.getvalue()).hexdigest()}"

    def _materialised_df(self) -> "pl.DataFrame":
        """Return a polars DataFrame view of the table's data.

        Internal helper for content_sha; handles DataFrame, LazyFrame,
        and path-loaded sources uniformly.
        """
        import polars as pl

        if self._df is not None:
            if isinstance(self._df, pl.LazyFrame):
                return self._df.collect()
            return self._df
        # Fall through: source is a path or other lazy reference.
        # Force materialisation through the public lookup pathway.
        # If this branch is reached, the Table was constructed without
        # eager materialisation; we collect now.
        if hasattr(self, "_source") and self._source is not None:
            if isinstance(self._source, pl.DataFrame):
                return self._source
            if isinstance(self._source, pl.LazyFrame):
                return self._source.collect()
        msg = "Table has no materialisable source"
        raise RuntimeError(msg)
```

Add `from typing import Any` to the top of `_api.py` if not already imported.

- [ ] **Step 4: Add stub signatures**

Edit `bindings/python/gaspatchio_core/assumptions/__init__.pyi`. Find the `Table` stub class. Add these signatures:

```python
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/assumptions/test_table_identity.py tests/assumptions/ -v
```

Expected: new tests green, all existing assumptions tests still green.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/assumptions/_api.py \
        bindings/python/gaspatchio_core/assumptions/__init__.pyi \
        bindings/python/tests/assumptions/test_table_identity.py
git commit -m "feat(table): add canonical_form, source_sha, content_sha

Row-order-independent content hash via parquet bytes of sort-canonicalised
frame. Mirrors Schedule/Curve/MortalityTable identity pattern. Shocked
tables produce different content_sha because the value column changed."
```

---

## Phase 2 — Aggregator framework

### Task 4: `ScenarioAggregator` Protocol + plugin registry

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_aggregator_registry.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregator_registry.py`:

```python
"""Test the aggregator plugin registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import (
    ScenarioAggregator,
    register_aggregator,
    scenario_aggregator,
    _AGGREGATOR_REGISTRY,
)


def test_register_aggregator_stores_class():
    @dataclass(frozen=True)
    class FakeAgg:
        def init(self) -> int: return 0
        def update(self, state: int, df: pl.DataFrame) -> int: return state + 1
        def finalize(self, state: int) -> int: return state
        def canonical_form(self) -> dict[str, Any]: return {"kind": "FakeAgg"}

    register_aggregator("FakeAgg_uniq1", FakeAgg)
    assert _AGGREGATOR_REGISTRY["FakeAgg_uniq1"] is FakeAgg


def test_register_aggregator_collision_raises():
    @dataclass(frozen=True)
    class A:
        def init(self): return 0
        def update(self, s, df): return s
        def finalize(self, s): return s
        def canonical_form(self): return {"kind": "A"}

    register_aggregator("collision_test", A)
    with pytest.raises(ValueError, match="already registered"):
        register_aggregator("collision_test", A)


def test_decorator_registers_class():
    @scenario_aggregator("decorated_test")
    @dataclass(frozen=True)
    class B:
        def init(self): return 0
        def update(self, s, df): return s
        def finalize(self, s): return s
        def canonical_form(self): return {"kind": "B"}

    assert _AGGREGATOR_REGISTRY["decorated_test"] is B


def test_decorator_uses_class_name_when_omitted():
    @scenario_aggregator()
    @dataclass(frozen=True)
    class UniqueClassName_47:
        def init(self): return 0
        def update(self, s, df): return s
        def finalize(self, s): return s
        def canonical_form(self): return {"kind": "UniqueClassName_47"}

    assert _AGGREGATOR_REGISTRY["UniqueClassName_47"] is UniqueClassName_47


def test_protocol_runtime_check():
    @dataclass(frozen=True)
    class Valid:
        def init(self): return 0
        def update(self, s, df): return s
        def finalize(self, s): return s
        def canonical_form(self): return {"kind": "Valid"}

    instance = Valid()
    assert isinstance(instance, ScenarioAggregator)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_aggregator_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._aggregators'`

- [ ] **Step 3: Create `_aggregators.py` with Protocol + registry**

Create `bindings/python/gaspatchio_core/scenarios/_aggregators.py`:

```python
# ABOUTME: ScenarioAggregator Protocol + 15 starter aggregators + plugin registry.
# ABOUTME: Public via gaspatchio_core.scenarios; see ScenarioMetric for the recipe envelope.

"""Cross-scenario aggregator framework and starter set."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import polars as pl

_AGGREGATOR_REGISTRY: dict[str, type] = {}


@runtime_checkable
class ScenarioAggregator(Protocol):
    """Cross-scenario reducer.

    ``update`` sees a per-batch frame with columns ``[scenario_id, value]``
    (plus group columns for the inner frame of GroupedAgg). Each implementation
    is responsible for being batch-equivalent: combining results from
    different ``batch_size`` values must produce the same final output
    (bit-exact for integer reducers; fp-tolerant for floating-point).
    """

    def init(self) -> Any: ...
    def update(self, state: Any, df: pl.DataFrame) -> Any: ...
    def finalize(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...


def register_aggregator(name: str, cls: type) -> None:
    """Register a user-defined aggregator class under ``name``.

    Raises ``ValueError`` on name collision. ``name`` must match the
    ``kind`` field returned by ``cls.canonical_form()``.
    """
    if name in _AGGREGATOR_REGISTRY:
        msg = f"Aggregator {name!r} already registered"
        raise ValueError(msg)
    _AGGREGATOR_REGISTRY[name] = cls


def scenario_aggregator(name: str | None = None):
    """Decorator: register a ScenarioAggregator with the registry.

    Example:
        @scenario_aggregator()
        @dataclass(frozen=True)
        class WorstK:
            k: int
            ...
    """
    def wrap(cls: type) -> type:
        register_aggregator(name or cls.__name__, cls)
        return cls
    return wrap


__all__ = [
    "ScenarioAggregator",
    "register_aggregator",
    "scenario_aggregator",
]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_aggregator_registry.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_aggregator_registry.py
git commit -m "feat(aggregators): ScenarioAggregator Protocol + plugin registry

register_aggregator(name, cls) + @scenario_aggregator() decorator.
Built-in aggregators (next commits) will register themselves via the
decorator. Registry is the resolution table for YAML round-trip."
```

---

### Task 5: Numeric aggregators (Sum, Count, Mean, Std, Variance, Min, Max)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py` (append the 7 classes)
- Test: `bindings/python/tests/scenarios/test_aggregators_numeric.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_numeric.py`:

```python
"""Test the seven numeric aggregators."""
from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import (
    Count,
    Max,
    Mean,
    Min,
    Std,
    Sum,
    Variance,
)


@pytest.fixture
def small_df():
    return pl.DataFrame({
        "scenario_id": [1, 2, 3, 4, 5],
        "value": [10.0, 20.0, 30.0, 40.0, 50.0],
    })


def _fold(agg, dfs):
    state = agg.init()
    for df in dfs:
        state = agg.update(state, df)
    return agg.finalize(state)


def test_sum_one_batch(small_df):
    assert _fold(Sum(), [small_df]) == 150.0


def test_sum_split_batches(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    assert _fold(Sum(), [a, b]) == 150.0


def test_count_split_batches(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    assert _fold(Count(), [a, b]) == 5


def test_mean_split_batches(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    assert _fold(Mean(), [a, b]) == pytest.approx(30.0)


def test_std_split_batches(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    result = _fold(Std(), [a, b])
    # Population std of [10,20,30,40,50] = sqrt(200) = 14.1421...
    assert result == pytest.approx(math.sqrt(200.0))


def test_variance_split_batches(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    result = _fold(Variance(), [a, b])
    assert result == pytest.approx(200.0)


def test_min_max(small_df):
    a, b = small_df.head(2), small_df.tail(3)
    assert _fold(Min(), [a, b]) == 10.0
    assert _fold(Max(), [a, b]) == 50.0


def test_canonical_forms():
    assert Sum().canonical_form() == {"kind": "Sum"}
    assert Count().canonical_form() == {"kind": "Count"}
    assert Mean().canonical_form() == {"kind": "Mean"}
    assert Std().canonical_form() == {"kind": "Std"}
    assert Variance().canonical_form() == {"kind": "Variance"}
    assert Min().canonical_form() == {"kind": "Min"}
    assert Max().canonical_form() == {"kind": "Max"}


def test_empty_input():
    empty = pl.DataFrame({"scenario_id": [], "value": []}, schema={"scenario_id": pl.Int64, "value": pl.Float64})
    assert _fold(Sum(), [empty]) == 0.0
    assert _fold(Count(), [empty]) == 0
    assert math.isnan(_fold(Mean(), [empty]))
    assert math.isnan(_fold(Std(), [empty]))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_aggregators_numeric.py -v
```

Expected: `ImportError: cannot import name 'Sum'`

- [ ] **Step 3: Append the seven classes to `_aggregators.py`**

Append to `bindings/python/gaspatchio_core/scenarios/_aggregators.py` (before the `__all__` line):

```python
from dataclasses import dataclass


@scenario_aggregator()
@dataclass(frozen=True)
class Sum:
    """Sum of per-scenario values across all scenarios."""

    def init(self) -> float:
        return 0.0

    def update(self, state: float, df: pl.DataFrame) -> float:
        s = df["value"].sum()
        return state + (s if s is not None else 0.0)

    def finalize(self, state: float) -> float:
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Sum"}


@scenario_aggregator()
@dataclass(frozen=True)
class Count:
    """Number of scenarios observed."""

    def init(self) -> int:
        return 0

    def update(self, state: int, df: pl.DataFrame) -> int:
        return state + df.height

    def finalize(self, state: int) -> int:
        return state

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Count"}


@scenario_aggregator()
@dataclass(frozen=True)
class Mean:
    """Arithmetic mean of per-scenario values via parallel Welford combine."""

    def init(self) -> tuple[int, float]:
        return (0, 0.0)

    def update(self, state: tuple[int, float], df: pl.DataFrame) -> tuple[int, float]:
        n0, m0 = state
        n1 = df.height
        if n1 == 0:
            return state
        m1 = df["value"].mean()
        n = n0 + n1
        return (n, (n0 * m0 + n1 * m1) / n)

    def finalize(self, state: tuple[int, float]) -> float:
        n, m = state
        return m if n > 0 else float("nan")

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Mean"}


@scenario_aggregator()
@dataclass(frozen=True)
class Std:
    """Population standard deviation via Chan/Welford parallel combine.

    State: (n, mean, M2) where M2 = sum((x - mean)^2).
    """

    def init(self) -> tuple[int, float, float]:
        return (0, 0.0, 0.0)

    def update(
        self, state: tuple[int, float, float], df: pl.DataFrame
    ) -> tuple[int, float, float]:
        n_a, mean_a, m2_a = state
        n_b = df.height
        if n_b == 0:
            return state
        vals = df["value"]
        mean_b = vals.mean()
        m2_b = ((vals - mean_b) ** 2).sum()
        n = n_a + n_b
        delta = mean_b - mean_a
        mean = mean_a + delta * n_b / n
        m2 = m2_a + m2_b + delta * delta * n_a * n_b / n
        return (n, mean, m2)

    def finalize(self, state: tuple[int, float, float]) -> float:
        n, _, m2 = state
        return (m2 / n) ** 0.5 if n > 0 else float("nan")

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Std"}


@scenario_aggregator()
@dataclass(frozen=True)
class Variance:
    """Population variance (Std squared) via the same Welford state."""

    def init(self) -> tuple[int, float, float]:
        return (0, 0.0, 0.0)

    def update(
        self, state: tuple[int, float, float], df: pl.DataFrame
    ) -> tuple[int, float, float]:
        return Std().update(state, df)

    def finalize(self, state: tuple[int, float, float]) -> float:
        n, _, m2 = state
        return m2 / n if n > 0 else float("nan")

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Variance"}


@scenario_aggregator()
@dataclass(frozen=True)
class Min:
    """Running minimum across scenarios."""

    def init(self) -> float:
        return float("inf")

    def update(self, state: float, df: pl.DataFrame) -> float:
        if df.height == 0:
            return state
        return min(state, df["value"].min())

    def finalize(self, state: float) -> float:
        return state if state != float("inf") else float("nan")

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Min"}


@scenario_aggregator()
@dataclass(frozen=True)
class Max:
    """Running maximum across scenarios."""

    def init(self) -> float:
        return float("-inf")

    def update(self, state: float, df: pl.DataFrame) -> float:
        if df.height == 0:
            return state
        return max(state, df["value"].max())

    def finalize(self, state: float) -> float:
        return state if state != float("-inf") else float("nan")

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Max"}
```

Update the `__all__` list to include the new classes:

```python
__all__ = [
    "ScenarioAggregator",
    "register_aggregator",
    "scenario_aggregator",
    "Sum", "Count", "Mean", "Std", "Variance", "Min", "Max",
]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_aggregators_numeric.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_aggregators_numeric.py
git commit -m "feat(aggregators): Sum, Count, Mean, Std, Variance, Min, Max

Seven numeric aggregators, all batch-equivalent. Mean and Std use parallel
Welford combine for numerical stability. Variance shares Std state and
returns the squared result."
```

---

### Task 6: Scenario-identity aggregators (ArgMin, ArgMax)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_argextreme.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_argextreme.py`:

```python
"""Test ArgMin / ArgMax aggregators (return scenario_id, not value)."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import ArgMax, ArgMin


@pytest.fixture
def values_df():
    return pl.DataFrame({
        "scenario_id": ["A", "B", "C", "D"],
        "value": [10.0, 50.0, 30.0, 50.0],   # ties on 50 between B and D
    })


def _fold(agg, dfs):
    state = agg.init()
    for df in dfs:
        state = agg.update(state, df)
    return agg.finalize(state)


def test_argmin_one_batch(values_df):
    assert _fold(ArgMin(), [values_df]) == "A"


def test_argmax_one_batch(values_df):
    # Ties: B and D both have 50; lexicographic tiebreak → "B"
    assert _fold(ArgMax(), [values_df]) == "B"


def test_argmin_split_batches(values_df):
    a, b = values_df.head(2), values_df.tail(2)
    assert _fold(ArgMin(), [a, b]) == "A"


def test_argmax_split_batches_tiebreak(values_df):
    a, b = values_df.head(2), values_df.tail(2)
    assert _fold(ArgMax(), [a, b]) == "B"


def test_canonical_form_includes_tiebreak():
    assert ArgMin().canonical_form() == {"kind": "ArgMin", "tiebreak": "lexicographic"}
    assert ArgMax().canonical_form() == {"kind": "ArgMax", "tiebreak": "lexicographic"}


def test_int_scenario_ids_tiebreak():
    df = pl.DataFrame({
        "scenario_id": [10, 20, 30],
        "value": [50.0, 50.0, 50.0],
    })
    # All tied; lexicographic on ints means smallest wins
    assert _fold(ArgMin(), [df]) == 10
    assert _fold(ArgMax(), [df]) == 10
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_aggregators_argextreme.py -v
```

Expected: `ImportError: cannot import name 'ArgMax'`

- [ ] **Step 3: Append ArgMin / ArgMax to `_aggregators.py`**

Append before `__all__`:

```python
def _better(candidate_val, candidate_sid, best_val, best_sid, direction: str) -> tuple:
    """Resolve which (value, scenario_id) wins. Lex tiebreak on scenario_id."""
    if best_sid is None:
        return (candidate_val, candidate_sid)
    if direction == "min":
        if candidate_val < best_val:
            return (candidate_val, candidate_sid)
        if candidate_val == best_val and candidate_sid < best_sid:
            return (candidate_val, candidate_sid)
    else:  # max
        if candidate_val > best_val:
            return (candidate_val, candidate_sid)
        if candidate_val == best_val and candidate_sid < best_sid:
            return (candidate_val, candidate_sid)
    return (best_val, best_sid)


@scenario_aggregator()
@dataclass(frozen=True)
class ArgMin:
    """Return the scenario_id with the smallest value (lex tiebreak)."""

    def init(self) -> tuple[float | None, Any]:
        return (None, None)

    def update(self, state: tuple, df: pl.DataFrame) -> tuple:
        best_val, best_sid = state
        for sid, val in zip(df["scenario_id"], df["value"], strict=True):
            best_val, best_sid = _better(val, sid, best_val, best_sid, "min")
        return (best_val, best_sid)

    def finalize(self, state: tuple) -> Any:
        return state[1]

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "ArgMin", "tiebreak": "lexicographic"}


@scenario_aggregator()
@dataclass(frozen=True)
class ArgMax:
    """Return the scenario_id with the largest value (lex tiebreak)."""

    def init(self) -> tuple[float | None, Any]:
        return (None, None)

    def update(self, state: tuple, df: pl.DataFrame) -> tuple:
        best_val, best_sid = state
        for sid, val in zip(df["scenario_id"], df["value"], strict=True):
            best_val, best_sid = _better(val, sid, best_val, best_sid, "max")
        return (best_val, best_sid)

    def finalize(self, state: tuple) -> Any:
        return state[1]

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "ArgMax", "tiebreak": "lexicographic"}
```

Update `__all__` to include `ArgMin`, `ArgMax`.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_aggregators_argextreme.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_aggregators_argextreme.py
git commit -m "feat(aggregators): ArgMin, ArgMax with lexicographic tiebreak

Return scenario_id of the extreme value, not the value itself. Required for
reverse stress testing (ORSA) and drill-down workflows. Tiebreak rule
exposed in canonical_form for explicit audit."
```

---

### Task 7: Tail / quantile aggregators (CTE, Quantile, Median, QuantileRank)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_tail.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_tail.py`:

```python
"""Test tail / quantile aggregators (CTE, Quantile, Median, QuantileRank)."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import (
    CTE,
    Median,
    Quantile,
    QuantileRank,
)


@pytest.fixture
def values_df():
    return pl.DataFrame({
        "scenario_id": list(range(1, 101)),
        "value": [float(i) for i in range(1, 101)],
    })


def _fold(agg, dfs):
    state = agg.init()
    for df in dfs:
        state = agg.update(state, df)
    return agg.finalize(state)


def test_cte_upper_one_batch(values_df):
    # CTE(0.05) upper = mean of worst 5% (i.e. top 5 values: 96..100) = 98.0
    result = _fold(CTE(level=0.05, direction="upper"), [values_df])
    assert result == pytest.approx(98.0)


def test_cte_lower_one_batch(values_df):
    # CTE(0.05) lower = mean of lowest 5% (1..5) = 3.0
    result = _fold(CTE(level=0.05, direction="lower"), [values_df])
    assert result == pytest.approx(3.0)


def test_cte_split_batches_bit_exact(values_df):
    a, b = values_df.head(50), values_df.tail(50)
    one = _fold(CTE(level=0.05, direction="upper"), [values_df])
    split = _fold(CTE(level=0.05, direction="upper"), [a, b])
    assert one == split


def test_median(values_df):
    # 100 values 1..100; median = mean of 50,51 = 50.5
    assert _fold(Median(), [values_df]) == pytest.approx(50.5)


def test_quantile_multiple_levels(values_df):
    result = _fold(Quantile(levels=(0.5, 0.95, 0.99)), [values_df])
    assert isinstance(result, dict)
    assert set(result.keys()) == {0.5, 0.95, 0.99}
    assert result[0.5] == pytest.approx(50.5)


def test_quantile_levels_sorted_in_canonical_form():
    cf = Quantile(levels=(0.99, 0.5, 0.95)).canonical_form()
    assert cf["levels"] == [0.5, 0.95, 0.99]


def test_quantile_rank(values_df):
    # Value 50 in [1..100] sits at percentile ~0.5
    result = _fold(QuantileRank(at=50.0), [values_df])
    assert result == pytest.approx(0.5, abs=0.01)


def test_quantile_rank_canonical_form():
    assert QuantileRank(at=1234.5).canonical_form() == {"kind": "QuantileRank", "at": 1234.5}


def test_cte_canonical_form():
    cf = CTE(level=0.995, direction="upper").canonical_form()
    assert cf == {"kind": "CTE", "level": 0.995, "direction": "upper"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_aggregators_tail.py -v
```

Expected: `ImportError: cannot import name 'CTE'`

- [ ] **Step 3: Append CTE / Quantile / Median / QuantileRank**

Append before `__all__`:

```python
import statistics


@scenario_aggregator()
@dataclass(frozen=True)
class CTE:
    """Conditional Tail Expectation at level α (e.g. 0.05 = SCR worst 5%).

    direction='upper' → mean of the largest α fraction (default; SCR shape).
    direction='lower' → mean of the smallest α fraction.
    """
    level: float
    direction: str = "upper"

    def init(self) -> list[float]:
        return []

    def update(self, state: list[float], df: pl.DataFrame) -> list[float]:
        state.extend(df["value"].to_list())
        return state

    def finalize(self, state: list[float]) -> float:
        if not state:
            return float("nan")
        ordered = sorted(state, reverse=(self.direction == "upper"))
        k = max(1, int(round(self.level * len(ordered))))
        return float(statistics.fmean(ordered[:k]))

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "CTE", "level": self.level, "direction": self.direction}


@scenario_aggregator()
@dataclass(frozen=True)
class Quantile:
    """Exact quantile(s) at given levels.

    Buffers all per-scenario values; reduction at finalize. For large
    n_scenarios (>1M) consider t-digest in a follow-up — out of scope v0.1.
    """
    levels: tuple[float, ...]

    def init(self) -> list[float]:
        return []

    def update(self, state: list[float], df: pl.DataFrame) -> list[float]:
        state.extend(df["value"].to_list())
        return state

    def finalize(self, state: list[float]) -> dict[float, float]:
        if not state:
            return {lvl: float("nan") for lvl in self.levels}
        ordered = sorted(state)
        n = len(ordered)
        out: dict[float, float] = {}
        for lvl in self.levels:
            # Type 7 (default) linear interpolation, matching numpy default.
            idx = lvl * (n - 1)
            lo = int(idx)
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            out[lvl] = ordered[lo] * (1 - frac) + ordered[hi] * frac
        return out

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Quantile", "levels": sorted(self.levels)}


@scenario_aggregator()
@dataclass(frozen=True)
class Median:
    """Median (50th percentile) — returns a scalar, not a dict."""

    def init(self) -> list[float]:
        return []

    def update(self, state: list[float], df: pl.DataFrame) -> list[float]:
        state.extend(df["value"].to_list())
        return state

    def finalize(self, state: list[float]) -> float:
        if not state:
            return float("nan")
        return float(statistics.median(state))

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "Median"}


@scenario_aggregator()
@dataclass(frozen=True)
class QuantileRank:
    """Percentile of ``at`` in the empirical CDF (IFRS 17 §119 disclosure)."""
    at: float

    def init(self) -> list[float]:
        return []

    def update(self, state: list[float], df: pl.DataFrame) -> list[float]:
        state.extend(df["value"].to_list())
        return state

    def finalize(self, state: list[float]) -> float:
        if not state:
            return float("nan")
        n = len(state)
        below = sum(1 for v in state if v <= self.at)
        return below / n

    def canonical_form(self) -> dict[str, Any]:
        return {"kind": "QuantileRank", "at": self.at}
```

Update `__all__` to include `CTE`, `Quantile`, `Median`, `QuantileRank`.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_aggregators_tail.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_aggregators_tail.py
git commit -m "feat(aggregators): CTE, Quantile, Median, QuantileRank

CTE (= TVaR / Expected Shortfall) supports upper/lower tails (SCR / VM-21
default = upper). Quantile takes multiple levels in one call. QuantileRank
satisfies IFRS 17 §119 confidence-level disclosure (input value → output
percentile). All bit-exact across batch sizes (sort happens at finalize)."
```

---

### Task 8: Composer aggregators (GroupedAgg, MultiAgg)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_aggregators_composers.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_aggregators_composers.py`:

```python
"""Test GroupedAgg and MultiAgg composer aggregators."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import (
    ArgMax,
    GroupedAgg,
    Mean,
    MultiAgg,
    Sum,
)


@pytest.fixture
def lob_df():
    return pl.DataFrame({
        "scenario_id": [1, 2, 3, 4],
        "lob": ["life", "life", "annuity", "annuity"],
        "value": [10.0, 20.0, 30.0, 40.0],
    })


def _fold(agg, dfs):
    state = agg.init()
    for df in dfs:
        state = agg.update(state, df)
    return agg.finalize(state)


def test_grouped_sum_one_batch(lob_df):
    result = _fold(GroupedAgg(by="lob", metric=Sum()), [lob_df])
    assert result == {"life": 30.0, "annuity": 70.0}


def test_grouped_mean_split_batches(lob_df):
    a, b = lob_df.head(2), lob_df.tail(2)
    result = _fold(GroupedAgg(by="lob", metric=Mean()), [a, b])
    assert result == {"life": pytest.approx(15.0), "annuity": pytest.approx(35.0)}


def test_grouped_argmax_returns_scenario_per_group(lob_df):
    """GSP-100 design §6.2 — GroupedAgg(by=..., metric=ArgMax()) is valid."""
    result = _fold(GroupedAgg(by="lob", metric=ArgMax()), [lob_df])
    assert result == {"life": 2, "annuity": 4}


def test_grouped_canonical_form():
    cf = GroupedAgg(by="lob", metric=Sum()).canonical_form()
    assert cf == {
        "kind": "GroupedAgg",
        "by": "lob",
        "metric": {"kind": "Sum"},
    }


def test_multi_agg_runs_named_metrics():
    df = pl.DataFrame({
        "scenario_id": [1, 2, 3],
        "pv_a": [100.0, 200.0, 300.0],
        "pv_b": [10.0, 20.0, 30.0],
    })
    multi = MultiAgg(metrics={"a_sum": Sum(), "b_mean": Mean()})
    result = _fold(multi, [df])
    assert result == {"a_sum": pytest.approx(600.0), "b_mean": pytest.approx(20.0)}


def test_multi_agg_canonical_form_keys_sorted():
    multi = MultiAgg(metrics={"z_metric": Sum(), "a_metric": Mean()})
    cf = multi.canonical_form()
    assert list(cf["metrics"].keys()) == ["a_metric", "z_metric"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_aggregators_composers.py -v
```

Expected: `ImportError: cannot import name 'GroupedAgg'`

- [ ] **Step 3: Append GroupedAgg + MultiAgg**

Append before `__all__`:

```python
@scenario_aggregator()
@dataclass(frozen=True)
class GroupedAgg:
    """Apply a sub-aggregator within each group of ``by`` values.

    The grouping column must be carried into the reduced frame by the
    per_scenario expression (e.g. ``per_scenario=pl.col('value').sum().over('lob')``).
    """
    by: str
    metric: ScenarioAggregator

    def init(self) -> dict[Any, Any]:
        return {}

    def update(self, state: dict[Any, Any], df: pl.DataFrame) -> dict[Any, Any]:
        for grp, sub in df.partition_by(self.by, as_dict=True).items():
            grp_val = grp[0] if isinstance(grp, tuple) else grp
            if grp_val not in state:
                state[grp_val] = self.metric.init()
            state[grp_val] = self.metric.update(state[grp_val], sub)
        return state

    def finalize(self, state: dict[Any, Any]) -> dict[Any, Any]:
        return {
            grp: self.metric.finalize(sub)
            for grp, sub in sorted(state.items(), key=lambda kv: str(kv[0]))
        }

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "GroupedAgg",
            "by": self.by,
            "metric": self.metric.canonical_form(),
        }


@scenario_aggregator()
@dataclass(frozen=True)
class MultiAgg:
    """Fan out to multiple named aggregators over the same reduced frame.

    Each sub-aggregator sees a per-metric slice with columns
    ``[scenario_id, value]``, renamed from the metric's column.
    ScenarioRun.run() uses this internally.
    """
    metrics: dict[str, ScenarioAggregator]

    def init(self) -> dict[str, Any]:
        return {name: m.init() for name, m in self.metrics.items()}

    def update(self, state: dict[str, Any], df: pl.DataFrame) -> dict[str, Any]:
        for name, sub_agg in self.metrics.items():
            sub_df = df.select([
                "scenario_id",
                pl.col(name).alias("value"),
            ])
            state[name] = sub_agg.update(state[name], sub_df)
        return state

    def finalize(self, state: dict[str, Any]) -> dict[str, Any]:
        return {name: self.metrics[name].finalize(state[name]) for name in self.metrics}

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "MultiAgg",
            "metrics": {
                name: m.canonical_form()
                for name, m in sorted(self.metrics.items())
            },
        }
```

Update `__all__` to include `GroupedAgg`, `MultiAgg`.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_aggregators_composers.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_aggregators_composers.py
git commit -m "feat(aggregators): GroupedAgg, MultiAgg composers

GroupedAgg partitions by a column and dispatches per group.
GroupedAgg(by=..., metric=ArgMax()) returns dict[group, scenario_id]
— useful for worst-scenario-per-LoB drill-down. MultiAgg fans out to
named sub-aggregators by re-aliasing the metric column to 'value'."
```

---

### Task 9: `ScenarioMetric` dataclass

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_aggregators.py`
- Test: `bindings/python/tests/scenarios/test_scenario_metric.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_scenario_metric.py`:

```python
"""Test ScenarioMetric envelope + base64 expression serialisation."""
from __future__ import annotations

import polars as pl

from gaspatchio_core.scenarios._aggregators import (
    CTE,
    ScenarioMetric,
    Sum,
    metric,
)


def test_scenario_metric_canonical_form_round_trip():
    m = ScenarioMetric(
        per_scenario=pl.col("net_cf").sum(),
        across_scenario=CTE(level=0.995, direction="upper"),
    )
    cf = m.canonical_form()
    assert "per_scenario_expr_b64" in cf
    assert cf["across_scenario"] == {
        "kind": "CTE", "level": 0.995, "direction": "upper",
    }


def test_two_metrics_same_recipe_same_canonical_form():
    m1 = ScenarioMetric(
        per_scenario=pl.col("x").sum(),
        across_scenario=Sum(),
    )
    m2 = ScenarioMetric(
        per_scenario=pl.col("x").sum(),
        across_scenario=Sum(),
    )
    assert m1.canonical_form() == m2.canonical_form()


def test_metric_sugar():
    m = metric("net_cf", Sum())
    assert isinstance(m.per_scenario, pl.Expr)
    assert isinstance(m.across_scenario, Sum)
    assert m.canonical_form() == metric("net_cf", Sum()).canonical_form()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_scenario_metric.py -v
```

Expected: `ImportError: cannot import name 'ScenarioMetric'`

- [ ] **Step 3: Append ScenarioMetric + sugar**

Append to `_aggregators.py` before `__all__`:

```python
import base64


@dataclass(frozen=True)
class ScenarioMetric:
    """The full reduction recipe for one named metric.

    ``per_scenario`` collapses rows → 1 number per scenario.
    ``across_scenario`` reduces across scenarios to a final result.
    """
    per_scenario: pl.Expr
    across_scenario: ScenarioAggregator

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "ScenarioMetric",
            "per_scenario_expr_b64": base64.b64encode(
                self.per_scenario.meta.serialize()
            ).decode("ascii"),
            "across_scenario": self.across_scenario.canonical_form(),
        }


def metric(column: str, agg: ScenarioAggregator) -> ScenarioMetric:
    """Sugar for the sum-default case.

    ``metric("net_cf", CTE(0.995))`` ≡ ``ScenarioMetric(per_scenario=pl.col("net_cf").sum(),
    across_scenario=CTE(0.995))``.
    """
    return ScenarioMetric(
        per_scenario=pl.col(column).sum(),
        across_scenario=agg,
    )
```

Update `__all__` to include `ScenarioMetric`, `metric`.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_scenario_metric.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_aggregators.py \
        bindings/python/tests/scenarios/test_scenario_metric.py
git commit -m "feat(aggregators): ScenarioMetric envelope + metric() sugar

ScenarioMetric pairs a per_scenario reduction expression with a cross-scenario
aggregator. canonical_form serialises pl.Expr via meta.serialize() + base64
for JSON safety. metric(column, agg) is sugar for the sum-default case."
```

---

### Task 10: Batch-equivalence parametrised tests

**Files:**
- Create: `bindings/python/tests/scenarios/test_batch_equivalence.py`

- [ ] **Step 1: Write the parametrised test**

Create `bindings/python/tests/scenarios/test_batch_equivalence.py`:

```python
"""Test all 15 aggregators are batch-equivalent across batch_size ∈ {1, 8, 64}."""
from __future__ import annotations

import math
import random

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import (
    ArgMax, ArgMin, CTE, Count, GroupedAgg, Max, Mean, Median, Min, MultiAgg,
    Quantile, QuantileRank, Std, Sum, Variance,
)

N_SCENARIOS = 1000


@pytest.fixture
def values_df():
    random.seed(20260511)
    return pl.DataFrame({
        "scenario_id": list(range(N_SCENARIOS)),
        "value": [random.gauss(100, 30) for _ in range(N_SCENARIOS)],
    })


def _split(df, size):
    return [df.slice(i, size) for i in range(0, df.height, size)]


def _fold(agg, batches):
    state = agg.init()
    for b in batches:
        state = agg.update(state, b)
    return agg.finalize(state)


SCALAR_AGGS = [
    Sum(), Count(), Mean(), Std(), Variance(),
    Min(), Max(),
    CTE(level=0.05, direction="upper"),
    CTE(level=0.05, direction="lower"),
    Median(),
    QuantileRank(at=100.0),
]


@pytest.mark.parametrize("agg", SCALAR_AGGS, ids=lambda a: type(a).__name__)
@pytest.mark.parametrize("size", [1, 8, 64])
def test_scalar_batch_equivalence(values_df, agg, size):
    one_batch = _fold(agg, [values_df])
    n_batches = _fold(agg, _split(values_df, size))
    if isinstance(one_batch, float) and math.isnan(one_batch):
        assert math.isnan(n_batches)
    else:
        assert n_batches == pytest.approx(one_batch, rel=1e-9)


@pytest.mark.parametrize("size", [1, 8, 64])
def test_argmin_argmax_bit_exact(values_df, size):
    one_amin = _fold(ArgMin(), [values_df])
    n_amin = _fold(ArgMin(), _split(values_df, size))
    assert one_amin == n_amin
    one_amax = _fold(ArgMax(), [values_df])
    n_amax = _fold(ArgMax(), _split(values_df, size))
    assert one_amax == n_amax


@pytest.mark.parametrize("size", [1, 8, 64])
def test_quantile_bit_exact(values_df, size):
    q = Quantile(levels=(0.5, 0.95, 0.99))
    one = _fold(q, [values_df])
    n = _fold(q, _split(values_df, size))
    for lvl in q.levels:
        assert n[lvl] == pytest.approx(one[lvl], rel=1e-9)
```

- [ ] **Step 2: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_batch_equivalence.py -v
```

Expected: 33+ tests passing (11 scalars × 3 sizes + 6 argmin/argmax + 3 quantile).

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/scenarios/test_batch_equivalence.py
git commit -m "test(aggregators): batch equivalence across {1, 8, 64} batch sizes

Parametrised over all 13 single-value aggregators + ArgMin/ArgMax + Quantile.
Asserts fp-equivalent (rel=1e-9) for floats and bit-exact for ArgMin/ArgMax."
```

---

## Phase 3 — Loop machinery

### Task 11: `_validate.py` shared scenario validation

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_validate.py`
- Test: `bindings/python/tests/scenarios/test_validate.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_validate.py`:

```python
"""Test the shared scenario validators."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._validate import (
    check_no_scenario_column,
    check_no_duplicate_ids,
    check_non_empty,
)


def test_check_non_empty_raises_on_empty():
    with pytest.raises(ValueError, match="at least one"):
        check_non_empty([])


def test_check_non_empty_passes():
    check_non_empty([1, 2, 3])  # no exception


def test_check_no_duplicate_ids_raises():
    with pytest.raises(ValueError, match="duplicate"):
        check_no_duplicate_ids([1, 2, 1])


def test_check_no_duplicate_ids_passes():
    check_no_duplicate_ids([1, 2, 3])


def test_check_no_scenario_column_raises():
    af = ActuarialFrame({"scenario_id": [1, 2], "x": [10, 20]})
    with pytest.raises(ValueError, match="scenario_id"):
        check_no_scenario_column(af, "scenario_id")


def test_check_no_scenario_column_passes():
    af = ActuarialFrame({"policy_id": [1, 2], "x": [10, 20]})
    check_no_scenario_column(af, "scenario_id")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_validate.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_validate.py`**

Create `bindings/python/gaspatchio_core/scenarios/_validate.py`:

```python
# ABOUTME: Shared scenario validation helpers used by with_scenarios + for_each_scenario.
# ABOUTME: Single source of truth for duplicate-ID / column-collision / empty checks.

"""Shared validators for scenario primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from gaspatchio_core.frame import ActuarialFrame

T = TypeVar("T")


def check_non_empty(scenario_ids: list[T]) -> None:
    """Raise ValueError if the scenario list is empty."""
    if not scenario_ids:
        msg = (
            "scenarios must contain at least one entry. "
            "For single-scenario models, pass ['DETERMINISTIC']."
        )
        raise ValueError(msg)


def check_no_duplicate_ids(scenario_ids: list[T]) -> None:
    """Raise ValueError if any scenario_id appears more than once."""
    if len(scenario_ids) == len(set(scenario_ids)):
        return
    seen: set[T] = set()
    dups: list[T] = []
    for s in scenario_ids:
        if s in seen and s not in dups:
            dups.append(s)
        seen.add(s)
    msg = f"scenarios contains duplicate ids: {dups}. Each scenario_id must be unique."
    raise ValueError(msg)


def check_no_scenario_column(af: "ActuarialFrame", column: str) -> None:
    """Raise ValueError if the ActuarialFrame already has a column called ``column``."""
    cols = af.get_column_order()
    if column in cols:
        msg = (
            f"Column {column!r} already exists in ActuarialFrame. "
            f"Rename the existing column or pass a different scenario_column name. "
            f"Existing columns: {cols}"
        )
        raise ValueError(msg)


__all__ = [
    "check_no_duplicate_ids",
    "check_no_scenario_column",
    "check_non_empty",
]
```

- [ ] **Step 4: Refactor `_with_scenarios.py` to use the shared validators**

Read `bindings/python/gaspatchio_core/scenarios/_with_scenarios.py` first. Replace the inline validation block (lines around 84-114, the section that checks for empty list, duplicates, and existing columns) with imports + helper calls. Keep the rest of the function body intact.

Replace the validation block with:

```python
    from gaspatchio_core.scenarios._validate import (
        check_no_duplicate_ids,
        check_no_scenario_column,
        check_non_empty,
    )

    check_non_empty(scenario_ids)
    check_no_duplicate_ids(scenario_ids)
    check_no_scenario_column(af, scenario_column)
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_validate.py tests/scenarios/test_with_scenarios.py -v
```

Expected: new tests green, `test_with_scenarios.py` still green (the externally observable behaviour is unchanged).

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_validate.py \
        bindings/python/gaspatchio_core/scenarios/_with_scenarios.py \
        bindings/python/tests/scenarios/test_validate.py
git commit -m "refactor(scenarios): extract shared validators to _validate.py

with_scenarios delegates duplicate-id, column-collision, and empty checks
to the shared module. for_each_scenario will reuse these helpers."
```

---

### Task 12: `stack_shocked_table` helper

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_stack.py`
- Test: `bindings/python/tests/scenarios/test_stack_shocked_table.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_stack_shocked_table.py`:

```python
"""Test stack_shocked_table for batched per-scenario shocks."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios._stack import stack_shocked_table
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
)


@pytest.fixture
def mortality_table():
    df = pl.DataFrame({
        "age": [30, 31, 32],
        "rate": [0.001, 0.0012, 0.0015],
    })
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


def test_stack_adds_scenario_id_dimension(mortality_table):
    per_scenario = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=1.5)],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)

    assert "scenario_id" in stacked._dimensions
    df = stacked._materialised_df()
    assert set(df["scenario_id"].unique().to_list()) == {"BASE", "STRESS"}
    assert df.height == 6  # 3 ages × 2 scenarios


def test_stack_applies_per_scenario_shock(mortality_table):
    per_scenario = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=2.0)],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)
    df = stacked._materialised_df()

    base = df.filter(pl.col("scenario_id") == "BASE")["rate"].to_list()
    stress = df.filter(pl.col("scenario_id") == "STRESS")["rate"].to_list()

    assert base == [0.001, 0.0012, 0.0015]
    assert stress == [pytest.approx(0.002), pytest.approx(0.0024), pytest.approx(0.003)]


def test_stack_heterogeneous_shocks(mortality_table):
    per_scenario = {
        "A": [MultiplicativeShock(factor=1.5)],
        "B": [AdditiveShock(delta=0.001)],
        "C": [],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)
    df = stacked._materialised_df()

    a = df.filter(pl.col("scenario_id") == "A")["rate"].to_list()
    b = df.filter(pl.col("scenario_id") == "B")["rate"].to_list()
    c = df.filter(pl.col("scenario_id") == "C")["rate"].to_list()

    assert a == [pytest.approx(0.0015), pytest.approx(0.0018), pytest.approx(0.00225)]
    assert b == [pytest.approx(0.002), pytest.approx(0.0022), pytest.approx(0.0025)]
    assert c == [0.001, 0.0012, 0.0015]


def test_stack_preserves_value_column(mortality_table):
    per_scenario = {"X": []}
    stacked = stack_shocked_table(mortality_table, per_scenario)
    assert stacked._value == "rate"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_stack_shocked_table.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_stack.py`**

Create `bindings/python/gaspatchio_core/scenarios/_stack.py`:

```python
# ABOUTME: stack_shocked_table — builds scenario-stacked shocked Tables for batched runs.
# ABOUTME: Used inside for_each_scenario's loop when batch_size > 1 with shock-dict shape.

"""Helper for batched per-scenario shock composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.scenarios.shocks import Shock


def stack_shocked_table(
    base: "Table",
    per_scenario_shocks: dict,
) -> "Table":
    """Stack a base Table with ``scenario_id`` as an extra dimension.

    For each scenario, applies the per-scenario shock list (possibly empty)
    to the value column, then concatenates with a ``scenario_id`` column.
    The resulting Table has dimensions = {scenario_id, **base._dimensions}.

    Args:
        base: Source assumption table.
        per_scenario_shocks: Maps scenario_id → list of Shocks to apply.
            Empty list = base case (no shock).

    Returns:
        New Table with the additional scenario_id dimension.
    """
    from gaspatchio_core.assumptions import Table

    base_df = base._materialised_df()
    value_col = base._value

    parts = []
    for sid, shocks in per_scenario_shocks.items():
        value_expr = pl.col(value_col)
        for shock in shocks:
            value_expr = shock.to_expression(value_expr)
        scen_df = base_df.with_columns(
            value_expr.alias(value_col),
            pl.lit(sid).alias("scenario_id"),
        )
        parts.append(scen_df)

    stacked_df = pl.concat(parts, how="vertical_relaxed")

    new_dims = {"scenario_id": "scenario_id", **base._dimensions}
    return Table(
        name=f"{base._name}_stacked",
        source=stacked_df,
        dimensions=new_dims,
        value=value_col,
    )


__all__ = ["stack_shocked_table"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_stack_shocked_table.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_stack.py \
        bindings/python/tests/scenarios/test_stack_shocked_table.py
git commit -m "feat(scenarios): stack_shocked_table for batched per-scenario shocks

Builds a Table with scenario_id as an extra dimension; each scenario's
value column is computed by applying its shock list to the base. Enables
heterogeneous shocks within a single batched run."
```

---

### Task 13: `_auto_batch.py` probe + calibration

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_auto_batch.py`
- Test: `bindings/python/tests/scenarios/test_auto_batch.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_auto_batch.py`:

```python
"""Test auto batch-size resolution paths."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from gaspatchio_core.scenarios._auto_batch import (
    _SAFETY_CEILING,
    resolve_batch_size,
)


def test_manual_path_returns_input():
    size, resolution = resolve_batch_size(
        batch_size=16,
        n_policies=1000,
        n_periods=240,
        target_memory_fraction=0.5,
        bytes_per_cell=None,
        probe_fn=lambda: 0,
    )
    assert size == 16
    assert resolution == "manual"


def test_manual_with_bytes_per_cell_raises():
    with pytest.raises(ValueError, match="bytes_per_cell only applies"):
        resolve_batch_size(
            batch_size=8,
            n_policies=1000,
            n_periods=240,
            target_memory_fraction=0.5,
            bytes_per_cell=128,
            probe_fn=lambda: 0,
        )


def test_calibrated_path():
    # 16 GB available × 0.5 = 8 GB target
    # 1000 policies × 240 periods × 128 B/cell = 30.72 MB per scenario
    # 8 GB / 30.72 MB = ~260 → clamped at _SAFETY_CEILING (256)
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 16 * 1024**3
        size, resolution = resolve_batch_size(
            batch_size="auto",
            n_policies=1000,
            n_periods=240,
            target_memory_fraction=0.5,
            bytes_per_cell=128,
            probe_fn=lambda: 0,
        )
    assert resolution == "auto_calibrated"
    assert size == _SAFETY_CEILING


def test_probe_path():
    # Probe returns 100 MB per scenario
    # 8 GB / 100 MB = ~80 → returns 80
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 16 * 1024**3
        size, resolution = resolve_batch_size(
            batch_size="auto",
            n_policies=1000,
            n_periods=240,
            target_memory_fraction=0.5,
            bytes_per_cell=None,
            probe_fn=lambda: 100 * 1024**2,
        )
    assert resolution == "auto_probe"
    assert size <= _SAFETY_CEILING
    assert size > 1


def test_probe_path_clamps_to_one_when_tight():
    # Probe returns enormous per_scenario_bytes; should clamp to 1
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 1 * 1024**3
        size, resolution = resolve_batch_size(
            batch_size="auto",
            n_policies=1000,
            n_periods=240,
            target_memory_fraction=0.5,
            bytes_per_cell=None,
            probe_fn=lambda: 10 * 1024**3,
        )
    assert size == 1
    assert resolution == "auto_probe"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_auto_batch.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_auto_batch.py`**

Create `bindings/python/gaspatchio_core/scenarios/_auto_batch.py`:

```python
# ABOUTME: Auto batch-size resolution — psutil RSS probe + calibration-constant fallback.
# ABOUTME: Single file per design decision 7; no Rust extension; subprocess probe is v0.2.

"""Auto batch-size resolution for for_each_scenario / ScenarioRun.run.

Two paths under ``batch_size='auto'``:

1. ``auto_calibrated`` — when ``bytes_per_cell`` is supplied, skip the probe
   and size from the constant: ``per_scenario_bytes = bytes_per_cell × n_policies × n_periods``.
   Deterministic; user-controlled.

2. ``auto_probe`` — run one scenario, measure RSS delta via psutil, extrapolate
   to ``target = available × target_memory_fraction``. Conservative (biased up
   by Polars retained-but-not-active memory; safe failure mode = under-size).
"""

from __future__ import annotations

from typing import Callable, Literal

import psutil

_SAFETY_CEILING = 256
_MIN_PROBE_BYTES = 1_000_000     # 1 MB floor; defends against measurement noise


def process_rss_bytes() -> int:
    """Current process RSS in bytes."""
    return psutil.Process().memory_info().rss


def resolve_batch_size(
    batch_size: int | Literal["auto"],
    n_policies: int,
    n_periods: int,
    target_memory_fraction: float,
    bytes_per_cell: int | None,
    probe_fn: Callable[[], int],
) -> tuple[int, Literal["manual", "auto_probe", "auto_calibrated"]]:
    """Resolve a concrete batch size from the user-declared input.

    Args:
        batch_size: Either an int (manual) or "auto".
        n_policies: Row count of the ActuarialFrame (for the calibrated path).
        n_periods: Estimated number of projection periods.
        target_memory_fraction: Fraction of available RAM to target (default 0.5).
        bytes_per_cell: If set with batch_size="auto", use calibrated path.
            Must be None for manual batch_size.
        probe_fn: Zero-arg callable that runs one scenario and returns
            ``rss_after - rss_before`` in bytes.

    Returns:
        ``(resolved_size, resolution)`` where resolution is the audit-trail label.

    Raises:
        ValueError: If ``bytes_per_cell`` is set with a manual ``batch_size``.
    """
    if batch_size != "auto":
        if bytes_per_cell is not None:
            msg = "bytes_per_cell only applies when batch_size='auto'"
            raise ValueError(msg)
        return batch_size, "manual"

    available = psutil.virtual_memory().available
    target_bytes = int(available * target_memory_fraction)

    if bytes_per_cell is not None:
        per_scenario_bytes = bytes_per_cell * n_policies * n_periods
        raw = max(1, target_bytes // max(per_scenario_bytes, 1))
        return min(raw, _SAFETY_CEILING), "auto_calibrated"

    per_scenario_bytes = max(probe_fn(), _MIN_PROBE_BYTES)
    raw = max(1, target_bytes // per_scenario_bytes)
    return min(raw, _SAFETY_CEILING), "auto_probe"


__all__ = ["process_rss_bytes", "resolve_batch_size"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_auto_batch.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_auto_batch.py \
        bindings/python/tests/scenarios/test_auto_batch.py
git commit -m "feat(scenarios): auto batch-size resolution

resolve_batch_size handles three paths: 'manual' (literal int passed),
'auto_probe' (RSS delta from running scenario 1 via psutil), and
'auto_calibrated' (bytes_per_cell × n_policies × n_periods).
Cap at _SAFETY_CEILING=256. Probe is injected as probe_fn for testability."
```

---

### Task 14: `_result.py` — `ScenarioResult` dataclass

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_result.py`
- Test: `bindings/python/tests/scenarios/test_result.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_result.py`:

```python
"""Test ScenarioResult dataclass."""
from __future__ import annotations

from pathlib import Path

from gaspatchio_core.scenarios._result import ScenarioResult


def test_result_construction():
    r = ScenarioResult(
        aggregations={"scr": 1.234e6},
        plan_sha="sha256:abc",
        n_scenarios=500,
        batch_size=64,
        batch_size_resolution="auto_probe",
        wall_time_s=12.34,
        peak_rss_mb=1500.0,
        sink_dir=None,
    )
    assert r.aggregations == {"scr": 1.234e6}
    assert r.batch_size_resolution == "auto_probe"
    assert r.sink_dir is None


def test_result_with_sink_dir():
    r = ScenarioResult(
        aggregations={},
        plan_sha="sha256:def",
        n_scenarios=100,
        batch_size=10,
        batch_size_resolution="manual",
        wall_time_s=5.0,
        peak_rss_mb=500.0,
        sink_dir=Path("/tmp/foo"),
    )
    assert r.sink_dir == Path("/tmp/foo")


def test_result_is_frozen():
    import pytest

    r = ScenarioResult(
        aggregations={}, plan_sha="sha256:x", n_scenarios=1,
        batch_size=1, batch_size_resolution="manual",
        wall_time_s=0.1, peak_rss_mb=None, sink_dir=None,
    )
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        r.batch_size = 99
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_result.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_result.py`**

Create `bindings/python/gaspatchio_core/scenarios/_result.py`:

```python
# ABOUTME: ScenarioResult — typed output of ScenarioRun.run / for_each_scenario.
# ABOUTME: Carries plan_sha plus runtime metadata (batch_size, peak_rss_mb, wall_time_s).

"""Typed result envelope for stochastic runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ScenarioResult:
    """Output of ``ScenarioRun.run()`` or ``for_each_scenario``.

    Carries the aggregator outputs plus runtime metadata. ``plan_sha`` is
    the input identity (covers shocks, base_tables, aggregations, master_seed);
    ``batch_size`` is the resolved runtime value and **not** part of the SHA.
    """

    aggregations: dict[str, Any]
    plan_sha: str
    n_scenarios: int
    batch_size: int
    batch_size_resolution: Literal["manual", "auto_probe", "auto_calibrated"]
    wall_time_s: float
    peak_rss_mb: float | None
    sink_dir: Path | None


__all__ = ["ScenarioResult"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_result.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_result.py \
        bindings/python/tests/scenarios/test_result.py
git commit -m "feat(scenarios): ScenarioResult typed output envelope"
```

---

### Task 15: `_for_each.py` — loop core (list-of-IDs shape only)

Start with the simplest case (no shocks, no drivers, no auto-batch, no full-grid). Iterate from there.

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_for_each.py`
- Test: `bindings/python/tests/scenarios/test_for_each_scenario.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_for_each_scenario.py`:

```python
"""Test for_each_scenario core loop (Phase 1: list[ID] shape)."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Mean, Sum
from gaspatchio_core.scenarios._for_each import for_each_scenario


@pytest.fixture
def af():
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _identity_model(af, *, tables=None, drivers=None):
    # Each row gets a "value" column = premium × 1 (per scenario, all scenarios share).
    return af.assign(value=pl.col("premium"))


def test_list_of_ids_sum_one_batch(af):
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_identity_model,
        agg=Sum(),
        per_scenario=pl.col("value").sum(),
        batch_size=1,
    )
    # 3 policies × 3 scenarios × premium total (600) = 1800 / no wait,
    # per_scenario reduction is sum-of-value per scenario, then Sum across scenarios.
    # Each scenario's per_scenario sum is 100+200+300 = 600. 3 scenarios → 1800.
    assert result.aggregations == pytest.approx(1800.0)
    assert result.n_scenarios == 3
    assert result.batch_size == 1
    assert result.batch_size_resolution == "manual"


def test_list_of_ids_batched(af):
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C", "D", "E"],
        model_fn=_identity_model,
        agg=Mean(),
        per_scenario=pl.col("value").sum(),
        batch_size=2,
    )
    # Each scenario's per_scenario sum is 600. Mean across 5 scenarios = 600.
    assert result.aggregations == pytest.approx(600.0)
    assert result.batch_size == 2


def test_empty_scenarios_raises(af):
    with pytest.raises(ValueError, match="at least one"):
        for_each_scenario(
            af, scenarios=[], model_fn=_identity_model,
            agg=Sum(), per_scenario=pl.col("value").sum(),
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_for_each_scenario.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_for_each.py` (Phase 1 — list[ID] shape only)**

Create `bindings/python/gaspatchio_core/scenarios/_for_each.py`:

```python
# ABOUTME: for_each_scenario — bounded-memory scenario-loop primitive.
# ABOUTME: Public; ScenarioRun.run() is a thin delegate on top of this.

"""Bounded-memory scenario loop."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Literal, TypeVar

import polars as pl

from gaspatchio_core.scenarios._auto_batch import (
    process_rss_bytes,
    resolve_batch_size,
)
from gaspatchio_core.scenarios._result import ScenarioResult
from gaspatchio_core.scenarios._validate import (
    check_no_duplicate_ids,
    check_non_empty,
)
from gaspatchio_core.scenarios._with_scenarios import with_scenarios

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.frame import ActuarialFrame
    from gaspatchio_core.scenarios._aggregators import ScenarioAggregator
    from gaspatchio_core.scenarios.shocks import Shock

T = TypeVar("T", str, int)
ScenarioID = str | int


def _peak_rss_mb() -> float | None:
    """Return peak RSS in MB, or None on platforms without psutil access."""
    try:
        rss = process_rss_bytes()
        return rss / (1024 * 1024)
    except Exception:
        return None


def _chunks(seq: list[T], size: int) -> Iterator[list[T]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def for_each_scenario(  # noqa: PLR0913, C901
    af: "ActuarialFrame",
    scenarios: list[ScenarioID]
              | dict[ScenarioID, list["Shock"]]
              | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., "ActuarialFrame"],
    agg: "ScenarioAggregator",
    *,
    base_tables: dict[str, "Table"] | None = None,
    per_scenario: pl.Expr | dict[str, pl.Expr] | None = None,
    batch_size: int | Literal["auto"] = 1,
    target_memory_fraction: float = 0.5,
    bytes_per_cell: int | None = None,
    return_full_grid: bool = False,
    sink_dir: Path | None = None,
    master_seed: int | None = None,
    progress: bool = False,
) -> ScenarioResult:
    """Run ``model_fn`` once per scenario (or per batch); fold into ``agg``.

    See the GSP-100 design doc, section 5, for the full contract. Phase 1 of
    the implementation supports the ``list[ScenarioID]`` shape only.
    """
    # Phase 1: only list[ScenarioID] shape supported.
    if not isinstance(scenarios, list):
        msg = "for_each_scenario: only list[ScenarioID] shape supported in Phase 1"
        raise NotImplementedError(msg)
    check_non_empty(scenarios)
    check_no_duplicate_ids(scenarios)

    sids = list(scenarios)
    n_policies = af._df.select(pl.len()).collect().item()
    n_periods = 240  # placeholder for Phase 1; refined in Phase 2 task

    resolved_size, resolution = resolve_batch_size(
        batch_size=batch_size,
        n_policies=n_policies,
        n_periods=n_periods,
        target_memory_fraction=target_memory_fraction,
        bytes_per_cell=bytes_per_cell,
        probe_fn=lambda: 0,  # Phase 1: no probe yet (manual only); Phase 2 wires it in
    )

    if return_full_grid:
        sink_dir = sink_dir or Path(f"./scenarios_{int(time.time())}")
        sink_dir.mkdir(parents=True, exist_ok=True)

    state = agg.init()
    started = time.perf_counter()

    for batch_idx, batch_sids in enumerate(_chunks(sids, resolved_size)):
        af_batch = with_scenarios(af, batch_sids)
        af_proj = model_fn(af_batch, tables=base_tables or {}, drivers={})

        if per_scenario is not None:
            if isinstance(per_scenario, pl.Expr):
                reduced = (af_proj._df
                           .group_by("scenario_id", maintain_order=True)
                           .agg(per_scenario.alias("value")))
            else:
                aggs = [expr.alias(name) for name, expr in per_scenario.items()]
                reduced = (af_proj._df
                           .group_by("scenario_id", maintain_order=True)
                           .agg(aggs))
        else:
            reduced = af_proj._df

        if return_full_grid:
            (af_proj._df.sort("scenario_id")
                .sink_parquet(sink_dir / f"batch_{batch_idx:04d}.parquet"))

        df_small = reduced.collect()
        state = agg.update(state, df_small)

    return ScenarioResult(
        aggregations=agg.finalize(state),
        plan_sha="",
        n_scenarios=len(sids),
        batch_size=resolved_size,
        batch_size_resolution=resolution,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=_peak_rss_mb(),
        sink_dir=sink_dir if return_full_grid else None,
    )


__all__ = ["for_each_scenario", "ScenarioID"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_for_each_scenario.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_for_each.py \
        bindings/python/tests/scenarios/test_for_each_scenario.py
git commit -m "feat(scenarios): for_each_scenario loop core (list[ID] shape)

Phase 1 of the bounded-memory loop primitive. Supports list[ScenarioID]
scenario shape only; shocks-dict and drivers-dict shapes follow in the
next tasks. Lazy per_scenario reduction; eager aggregator update."
```

---

### Task 16: `_for_each.py` shocks-dict shape + stack integration

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_for_each.py`
- Test: `bindings/python/tests/scenarios/test_for_each_shocks.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_for_each_shocks.py`:

```python
"""Test for_each_scenario with dict[ID, list[Shock]] shape."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Sum
from gaspatchio_core.scenarios._for_each import for_each_scenario
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def af():
    return ActuarialFrame({"policy_id": [1, 2], "age": [30, 31]})


@pytest.fixture
def mortality_table():
    df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


def _shock_model(af, *, tables, drivers):
    mortality = tables["mortality"]
    qx = mortality.lookup(
        scenario_id=pl.col("scenario_id"),
        age=pl.col("age"),
    )
    return af.assign(value=qx * 1e6)  # scale to readable numbers


def test_shocks_dict_batched_equals_unbatched(af, mortality_table):
    shocks = {
        "BASE":   [],
        "STRESS": [MultiplicativeShock(factor=2.0)],
    }
    one = for_each_scenario(
        af, scenarios=shocks, model_fn=_shock_model,
        agg=Sum(), per_scenario=pl.col("value").sum(),
        base_tables={"mortality": mortality_table},
        batch_size=1,
    )
    two = for_each_scenario(
        af, scenarios=shocks, model_fn=_shock_model,
        agg=Sum(), per_scenario=pl.col("value").sum(),
        base_tables={"mortality": mortality_table},
        batch_size=2,
    )
    assert one.aggregations == pytest.approx(two.aggregations)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_for_each_shocks.py -v
```

Expected: `NotImplementedError: for_each_scenario: only list[ScenarioID] shape supported`

- [ ] **Step 3: Extend `_for_each.py` with shocks-dict support**

Edit `bindings/python/gaspatchio_core/scenarios/_for_each.py`. Replace the Phase-1 NotImplementedError block with a shape classifier and stack integration:

Add this helper near the top of the file:

```python
def _classify(scenarios) -> Literal["ids", "shocks", "drivers"]:
    if isinstance(scenarios, list):
        return "ids"
    if isinstance(scenarios, dict):
        values = list(scenarios.values())
        if not values:
            return "ids"  # empty dict treated as no scenarios; later raises non_empty
        types = {type(v) for v in values}
        if types == {list}:
            return "shocks"
        if types == {dict}:
            return "drivers"
        msg = f"scenarios dict has mixed value types {types}; expected all-list or all-dict"
        raise TypeError(msg)
    msg = f"scenarios must be list or dict, got {type(scenarios).__name__}"
    raise TypeError(msg)
```

Replace the Phase-1 NotImplementedError block. The new structure:

```python
    shape = _classify(scenarios)

    if shape == "ids":
        sids = list(scenarios)
    else:  # "shocks" or "drivers"
        sids = list(scenarios.keys())

    check_non_empty(sids)
    check_no_duplicate_ids(sids)
```

Inside the loop body, replace the table-handling block with:

```python
        # Build per-batch stacked tables for the shocks shape
        if shape == "shocks":
            from gaspatchio_core.scenarios._stack import stack_shocked_table

            stacked_tables = {
                name: stack_shocked_table(
                    base,
                    {sid: [s for s in scenarios[sid]
                           if getattr(s, "table", None) in (name, None)]
                     for sid in batch_sids},
                )
                for name, base in (base_tables or {}).items()
            }
        else:
            stacked_tables = base_tables or {}

        af_batch = with_scenarios(af, batch_sids)
        af_proj = model_fn(af_batch, tables=stacked_tables, drivers={})
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_shocks.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_for_each.py \
        bindings/python/tests/scenarios/test_for_each_shocks.py
git commit -m "feat(scenarios): for_each_scenario shocks-dict shape

Adds stack_shocked_table integration for dict[ID, list[Shock]] scenarios.
Per-batch builds scenario-stacked Tables; model_fn sees scenario_id as
an extra lookup key. Heterogeneous shocks within a batch compose
correctly (verified by batch-equivalence test)."
```

---

### Task 17: `_for_each.py` drivers shape + master_seed

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_for_each.py`
- Test: `bindings/python/tests/scenarios/test_for_each_drivers.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_for_each_drivers.py`:

```python
"""Test for_each_scenario drivers-dict shape + master_seed plumbing."""
from __future__ import annotations

import hashlib

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Sum
from gaspatchio_core.scenarios._for_each import (
    _per_scenario_seed,
    for_each_scenario,
)


@pytest.fixture
def af():
    return ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})


def _driver_model(af, *, tables, drivers):
    # Read a numeric driver field and multiply premium by it.
    factor = drivers.get("factor", 1.0)
    return af.assign(value=pl.col("premium") * factor)


def test_drivers_dict_shape(af):
    drivers_per_scenario = {
        "A": {"factor": 1.0},
        "B": {"factor": 2.0},
        "C": {"factor": 3.0},
    }
    # Note: drivers in this implementation are per-batch, so for batch_size=1
    # each scenario's drivers dict is forwarded. Each scenario's per_scenario sum =
    # factor × (100+200) = factor × 300. Total Sum = (1+2+3) × 300 = 1800.
    result = for_each_scenario(
        af,
        scenarios=drivers_per_scenario,
        model_fn=_driver_model,
        agg=Sum(),
        per_scenario=pl.col("value").sum(),
        batch_size=1,
    )
    assert result.aggregations == pytest.approx(1800.0)


def test_master_seed_derivation_deterministic():
    s1 = _per_scenario_seed(master_seed=42, scenario_id="A")
    s2 = _per_scenario_seed(master_seed=42, scenario_id="A")
    assert s1 == s2
    assert 0 <= s1 < 2**32


def test_master_seed_differs_per_scenario():
    s1 = _per_scenario_seed(master_seed=42, scenario_id="A")
    s2 = _per_scenario_seed(master_seed=42, scenario_id="B")
    assert s1 != s2


def test_master_seed_passed_through(af):
    received_seeds = {}

    def capture_model(af, *, tables, drivers):
        # scenario_id is in the cross-joined frame; pull first row's id + seed
        sid = af._df.select("scenario_id").first().collect().item()
        received_seeds[sid] = drivers.get("rng_seed")
        return af.assign(value=pl.col("premium"))

    for_each_scenario(
        af, scenarios=["X", "Y"], model_fn=capture_model,
        agg=Sum(), per_scenario=pl.col("value").sum(),
        master_seed=123, batch_size=1,
    )
    assert received_seeds["X"] == _per_scenario_seed(123, "X")
    assert received_seeds["Y"] == _per_scenario_seed(123, "Y")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_for_each_drivers.py -v
```

Expected: `ImportError: cannot import name '_per_scenario_seed'`

- [ ] **Step 3: Add `_per_scenario_seed` + drivers wiring**

Add this helper to `_for_each.py` (near `_peak_rss_mb`):

```python
def _per_scenario_seed(master_seed: int, scenario_id: ScenarioID) -> int:
    """Derive a deterministic 32-bit seed from (master_seed, scenario_id).

    Uses sha256 (NOT Python's hash()) because PYTHONHASHSEED randomises
    string hashing across processes. Same inputs → same output across
    machines and Python versions.
    """
    import hashlib

    payload = f"gsp-100|{master_seed}|{scenario_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _build_drivers(
    scenarios,
    batch_sids: list,
    shape: str,
    master_seed: int | None,
) -> dict:
    """Build the drivers dict passed to model_fn for this batch.

    For batch_size=1 (single sid in batch), forwards the scenario's drivers.
    For batch_size>1, drivers is per-scenario; we forward only the seed slice
    here. Multi-scenario drivers within a batch require model_fn to fan out
    via scenario_id internally (caller responsibility).
    """
    out: dict[str, Any] = {}

    if shape == "drivers" and len(batch_sids) == 1:
        out.update(scenarios[batch_sids[0]])

    if master_seed is not None and len(batch_sids) == 1:
        out["rng_seed"] = _per_scenario_seed(master_seed, batch_sids[0])

    return out
```

Inside the loop body, replace `drivers={}` with:

```python
        batch_drivers = _build_drivers(scenarios, batch_sids, shape, master_seed)
        af_proj = model_fn(af_batch, tables=stacked_tables, drivers=batch_drivers)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_for_each_drivers.py tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_shocks.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_for_each.py \
        bindings/python/tests/scenarios/test_for_each_drivers.py
git commit -m "feat(scenarios): for_each_scenario drivers shape + master_seed

dict[ID, dict] shape forwards per-scenario drivers to model_fn(drivers=...).
master_seed derives per-scenario seed via sha256(payload)[:4] →
drivers['rng_seed']. Deterministic across processes (no PYTHONHASHSEED
contamination)."
```

---

### Task 18: Memory benchmark (subprocess-based)

**Files:**
- Create: `bindings/python/benchmarks/scenariorun/test_scenariorun_scaling.py`
- Create: `bindings/python/benchmarks/scenariorun/_runner.py`

- [ ] **Step 1: Create the subprocess runner**

Create `bindings/python/benchmarks/scenariorun/_runner.py`:

```python
# ABOUTME: Subprocess entry point for memory-bounded ScenarioRun benchmarks.
# ABOUTME: Run as a child process and let the parent measure peak RSS via getrusage.

"""Inner runner for ScenarioRun scaling benchmarks (called by subprocess)."""

from __future__ import annotations

import json
import sys
import time

import polars as pl

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Sum
from gaspatchio_core.scenarios._for_each import for_each_scenario


def main() -> None:
    spec = json.loads(sys.argv[1])
    n_policies = spec["n_policies"]
    n_scenarios = spec["n_scenarios"]
    batch_size = spec["batch_size"]

    af = ActuarialFrame({
        "policy_id": list(range(n_policies)),
        "premium": [100.0 + i for i in range(n_policies)],
    })

    def model_fn(af, *, tables, drivers):
        return af.assign(value=pl.col("premium"))

    started = time.perf_counter()
    result = for_each_scenario(
        af,
        scenarios=list(range(n_scenarios)),
        model_fn=model_fn,
        agg=Sum(),
        per_scenario=pl.col("value").sum(),
        batch_size=batch_size,
    )
    elapsed = time.perf_counter() - started

    print(json.dumps({
        "wall_time_s": elapsed,
        "n_scenarios": result.n_scenarios,
        "batch_size": result.batch_size,
        "aggregations": result.aggregations,
    }))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create the benchmark harness**

Create `bindings/python/benchmarks/scenariorun/test_scenariorun_scaling.py`:

```python
"""Memory-scaling benchmark mirroring ref/41-backend-portability/41-scenario-scaling-empirical.md."""

from __future__ import annotations

import json
import resource
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).parent / "_runner.py"


def _run_subprocess(spec: dict) -> tuple[float, int, dict]:
    """Run the inner runner; return (wall_s, peak_rss_mb, result_dict)."""
    proc = subprocess.run(
        [sys.executable, str(RUNNER), json.dumps(spec)],
        capture_output=True,
        text=True,
        check=True,
    )
    # macOS reports ru_maxrss in bytes; Linux in kilobytes.
    rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if sys.platform == "darwin":
        peak_rss_mb = rusage.ru_maxrss / (1024 * 1024)
    else:
        peak_rss_mb = rusage.ru_maxrss / 1024
    result = json.loads(proc.stdout)
    return result["wall_time_s"], peak_rss_mb, result


@pytest.mark.bench
@pytest.mark.parametrize("batch_size", [1, 8])
def test_rss_bounded_within_batch_at_1k_policies(batch_size, tmp_path):
    """Peak RSS at 1k × 100 scenarios should not exceed a generous within-batch ceiling.

    The bound is loose — we're testing that the loop does NOT exhibit
    cross-product-scale RSS (which would be ~12 GB at 1k × 100 × per-row footprint).
    A working batched run should stay well under 4 GB.
    """
    wall_s, peak_rss_mb, _ = _run_subprocess({
        "n_policies": 1000,
        "n_scenarios": 100,
        "batch_size": batch_size,
    })
    assert peak_rss_mb < 4096, f"peak_rss_mb={peak_rss_mb:.0f} suggests cross-product behaviour"
```

- [ ] **Step 3: Run benchmark**

```bash
uv run pytest benchmarks/scenariorun/test_scenariorun_scaling.py -v -m bench
```

Expected: 2 passed; peak_rss_mb well under 4 GB for both batch sizes.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/benchmarks/scenariorun/
git commit -m "test(scenarios): subprocess-based memory benchmark

Mirrors the empirical-scaling methodology: child process runs the loop,
parent measures peak RSS via RUSAGE_CHILDREN. Asserts within-batch
bound (NOT cross-batch — that's the documented Polars allocator caveat)."
```

---

## Phase 4 — Plan layer

### Task 19: `ScenarioRun` dataclass + identity

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_run.py`
- Test: `bindings/python/tests/scenarios/test_scenario_run.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_scenario_run.py`:

```python
"""Test ScenarioRun plan dataclass + identity."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios._aggregators import CTE, Sum, metric
from gaspatchio_core.scenarios._run import ScenarioRun
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def mortality_table():
    df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


def test_canonical_form_shape(mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(factor=1.2)]},
        base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", CTE(level=0.005, direction="upper"))},
    )
    cf = plan.canonical_form()
    assert cf["kind"] == "ScenarioRun"
    assert set(cf["shocks"].keys()) == {"BASE", "UP"}
    assert "mortality" in cf["base_tables"]
    assert "scr" in cf["aggregations"]
    assert cf["master_seed"] is None


def test_two_equivalent_plans_same_sha(mortality_table):
    p1 = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(factor=1.2)]},
        base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    p2 = ScenarioRun(
        shocks={"UP": [MultiplicativeShock(factor=1.2)], "BASE": []},  # different insertion order
        base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    assert p1.source_sha() == p2.source_sha()


def test_master_seed_changes_sha(mortality_table):
    base = ScenarioRun(
        shocks={"BASE": []}, base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    seeded = ScenarioRun(
        shocks={"BASE": []}, base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
        master_seed=42,
    )
    assert base.source_sha() != seeded.source_sha()


def test_with_master_seed_immutable_composer(mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": []}, base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    seeded = plan.with_master_seed(42)
    assert plan.master_seed is None
    assert seeded.master_seed == 42


def test_with_extra_shocks_immutable_composer(mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": []}, base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    extended = plan.with_extra_shocks({"UP": [MultiplicativeShock(factor=1.5)]})
    assert set(plan.shocks.keys()) == {"BASE"}
    assert set(extended.shocks.keys()) == {"BASE", "UP"}


def test_describe_returns_string(mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": []}, base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("net_cf", Sum())},
    )
    desc = plan.describe()
    assert isinstance(desc, str)
    assert "ScenarioRun" in desc or "scenario" in desc.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_scenario_run.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `_run.py`**

Create `bindings/python/gaspatchio_core/scenarios/_run.py`:

```python
# ABOUTME: ScenarioRun typed plan dataclass + identity + immutable composers + .run().
# ABOUTME: Audit chain rolls up shocks, base_tables, aggregations, master_seed.

"""ScenarioRun — typed, auditable stochastic-run plan."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from gaspatchio_core._identity import source_sha_of

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.frame import ActuarialFrame
    from gaspatchio_core.scenarios._aggregators import ScenarioMetric
    from gaspatchio_core.scenarios._result import ScenarioResult
    from gaspatchio_core.scenarios.shocks import Shock


@dataclass(frozen=True)
class ScenarioRun:
    """Reusable, auditable stochastic-run plan.

    Captures shocks, base tables, aggregation recipes, and (optionally) a
    master seed. Identity surface (``canonical_form``, ``source_sha``,
    ``describe``) mirrors Schedule / Curve / MortalityTable. Run via ``.run()``
    or convert to dict/YAML for governance archives.
    """

    shocks: dict[str, list["Shock"]]
    base_tables: dict[str, "Table"]
    aggregations: dict[str, "ScenarioMetric"]
    master_seed: int | None = None

    # ---- identity ----

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
                name: m.canonical_form()
                for name, m in sorted(self.aggregations.items())
            },
            "master_seed": self.master_seed,
        }

    def source_sha(self) -> str:
        return source_sha_of(self.canonical_form())

    def describe(self) -> str:
        n_shocks = sum(len(v) for v in self.shocks.values())
        return (
            f"ScenarioRun(scenarios={len(self.shocks)}, total_shocks={n_shocks}, "
            f"tables={list(self.base_tables.keys())}, "
            f"metrics={list(self.aggregations.keys())}, "
            f"master_seed={self.master_seed}, "
            f"sha={self.source_sha()})"
        )

    # ---- immutable composers ----

    def with_extra_shocks(self, more: dict[str, list["Shock"]]) -> "ScenarioRun":
        return replace(self, shocks={**self.shocks, **more})

    def with_extra_aggregations(
        self, more: dict[str, "ScenarioMetric"]
    ) -> "ScenarioRun":
        return replace(self, aggregations={**self.aggregations, **more})

    def with_master_seed(self, seed: int) -> "ScenarioRun":
        return replace(self, master_seed=seed)

    # ---- run delegation (next task) ----

    def run(  # noqa: PLR0913
        self,
        af: "ActuarialFrame",
        model_fn: Callable[..., "ActuarialFrame"],
        *,
        batch_size: int | Literal["auto"] = 1,
        target_memory_fraction: float = 0.5,
        bytes_per_cell: int | None = None,
        return_full_grid: bool = False,
        sink_dir: Path | None = None,
    ) -> "ScenarioResult":
        # Delegated to for_each_scenario; wiring in next task.
        from dataclasses import replace as _replace

        from gaspatchio_core.scenarios._aggregators import MultiAgg
        from gaspatchio_core.scenarios._for_each import for_each_scenario

        plan_sha = self.source_sha()
        multi = MultiAgg(
            metrics={name: m.across_scenario for name, m in self.aggregations.items()}
        )
        per_scen = {name: m.per_scenario for name, m in self.aggregations.items()}

        result = for_each_scenario(
            af,
            scenarios=self.shocks,
            model_fn=model_fn,
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
        return _replace(result, plan_sha=plan_sha)


__all__ = ["ScenarioRun"]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_scenario_run.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_run.py \
        bindings/python/tests/scenarios/test_scenario_run.py
git commit -m "feat(scenarios): ScenarioRun typed plan + identity + .run()

Mirrors Schedule/Curve/MortalityTable identity pattern. canonical_form
sorts every dict key for deterministic hashing. Immutable composers
return new instances. .run() delegates to for_each_scenario with the
metrics wrapped in MultiAgg."
```

---

### Task 20: ScenarioRun YAML / dict round-trip

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_config.py` (extend with `parse_aggregations`)
- Modify: `bindings/python/gaspatchio_core/scenarios/_run.py` (add `from_yaml`, `to_yaml`, `from_dict`, `to_dict`)
- Test: `bindings/python/tests/scenarios/test_scenario_run_yaml.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_scenario_run_yaml.py`:

```python
"""Test ScenarioRun YAML / dict round-trip."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios._aggregators import Sum, metric
from gaspatchio_core.scenarios._run import ScenarioRun
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def mortality_table():
    df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


def test_from_dict_round_trip(mortality_table):
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "STRESS": [MultiplicativeShock(factor=1.5, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations={"pv": metric("net_cf", Sum())},
        master_seed=42,
    )
    d = plan.to_dict()
    reloaded = ScenarioRun.from_dict(d, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()


def test_yaml_round_trip(tmp_path, mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": [], "STRESS": [MultiplicativeShock(factor=2.0, table="mortality")]},
        base_tables={"mortality": mortality_table},
        aggregations={"pv": metric("net_cf", Sum())},
    )
    out = tmp_path / "plan.yaml"
    plan.to_yaml(out)
    assert out.exists()
    reloaded = ScenarioRun.from_yaml(out, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_scenario_run_yaml.py -v
```

Expected: `AttributeError: type object 'ScenarioRun' has no attribute 'from_dict'`

- [ ] **Step 3: Add round-trip helpers to `_run.py`**

Append these methods to the `ScenarioRun` class in `_run.py`:

```python
    # ---- round-trip ----

    @classmethod
    def from_dict(
        cls,
        config: dict,
        *,
        base_tables: dict[str, "Table"],
    ) -> "ScenarioRun":
        from gaspatchio_core.scenarios._config import (
            parse_aggregations,
            parse_scenario_config,
        )

        shocks = parse_scenario_config(config.get("scenarios", []))
        aggregations = parse_aggregations(config.get("aggregations", {}))
        return cls(
            shocks=shocks,
            base_tables=base_tables,
            aggregations=aggregations,
            master_seed=config.get("master_seed"),
        )

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        base_tables: dict[str, "Table"],
    ) -> "ScenarioRun":
        import yaml

        with Path(path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls.from_dict(config, base_tables=base_tables)

    def to_dict(self) -> dict[str, Any]:
        from gaspatchio_core.scenarios._aggregators import ScenarioMetric

        scenarios = []
        for sid, shocks in self.shocks.items():
            entry: dict[str, Any] = {"id": sid}
            if shocks:
                entry["shocks"] = [_shock_to_dict(s) for s in shocks]
            scenarios.append(entry)

        aggregations = {
            name: _metric_to_dict(m) for name, m in self.aggregations.items()
        }

        out: dict[str, Any] = {
            "scenarios": scenarios,
            "aggregations": aggregations,
        }
        if self.master_seed is not None:
            out["master_seed"] = self.master_seed
        return out

    def to_yaml(self, path: Path) -> None:
        import yaml

        with Path(path).open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=True)
```

Add these module-level helpers at the bottom of `_run.py` (before `__all__`):

```python
def _shock_to_dict(shock: "Shock") -> dict[str, Any]:
    """Round-trip a Shock back to the dict shape that parse_shock_config accepts.

    This is a thin wrapper around canonical_form() that produces the same
    structure parse_shock_config emits — sufficient for YAML survival.
    """
    return shock.canonical_form()


def _metric_to_dict(m: "ScenarioMetric") -> dict[str, Any]:
    """Round-trip a ScenarioMetric. canonical_form is the audit form;
    to_dict produces the YAML-loadable form that parse_aggregations consumes."""
    return {
        "per_scenario_expr_b64": m.canonical_form()["per_scenario_expr_b64"],
        "across_scenario": m.across_scenario.canonical_form(),
    }
```

- [ ] **Step 4: Add `parse_aggregations` to `_config.py`**

Read `bindings/python/gaspatchio_core/scenarios/_config.py`. Append before the file's `__all__`:

```python
def parse_aggregations(config: dict[str, Any]) -> dict[str, "ScenarioMetric"]:
    """Parse aggregations dict from YAML/JSON config into ScenarioMetric instances.

    Schema:
        {
            "<name>": {
                "per_scenario_expr_b64": "<base64-encoded pl.Expr>",
                "across_scenario": {"kind": "<registered name>", ...params}
            },
            ...
        }
    """
    import base64

    import polars as pl

    from gaspatchio_core.scenarios._aggregators import (
        ScenarioMetric,
        _AGGREGATOR_REGISTRY,
    )

    out: dict[str, ScenarioMetric] = {}
    for name, spec in config.items():
        expr_bytes = base64.b64decode(spec["per_scenario_expr_b64"])
        per_scenario = pl.Expr.deserialize(expr_bytes)
        agg_spec = dict(spec["across_scenario"])
        kind = agg_spec.pop("kind")
        if kind not in _AGGREGATOR_REGISTRY:
            available = sorted(_AGGREGATOR_REGISTRY.keys())
            msg = (
                f"Aggregator {kind!r} is not registered. Available: {available}. "
                f"To register a custom aggregator, call register_aggregator() "
                f"before parsing."
            )
            raise ValueError(msg)
        cls = _AGGREGATOR_REGISTRY[kind]
        across_scenario = cls(**agg_spec)
        out[name] = ScenarioMetric(
            per_scenario=per_scenario,
            across_scenario=across_scenario,
        )
    return out
```

Add `parse_aggregations` to `_config.py`'s `__all__`.

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_scenario_run_yaml.py tests/scenarios/test_scenario_run.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_run.py \
        bindings/python/gaspatchio_core/scenarios/_config.py \
        bindings/python/tests/scenarios/test_scenario_run_yaml.py
git commit -m "feat(scenarios): ScenarioRun YAML round-trip

parse_aggregations resolves 'kind' through the plugin registry; clear
error names available registrations when an unknown name is encountered.
ScenarioRun.from_yaml / to_yaml / from_dict / to_dict preserve source_sha
across the round trip."
```

---

## Phase 5 — Wiring

### Task 21: Update `scenarios/__init__.py` + `.pyi` exports

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py`
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.pyi`
- Test: `bindings/python/tests/scenarios/test_public_surface.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/scenarios/test_public_surface.py`:

```python
"""Test the public scenarios surface exports the GSP-100 names."""
from __future__ import annotations

import pytest


def test_new_names_importable():
    from gaspatchio_core.scenarios import (
        ArgMax,
        ArgMin,
        CTE,
        Count,
        GroupedAgg,
        Max,
        Mean,
        Median,
        Min,
        MultiAgg,
        Quantile,
        QuantileRank,
        ScenarioAggregator,
        ScenarioMetric,
        ScenarioResult,
        ScenarioRun,
        Std,
        Sum,
        Variance,
        for_each_scenario,
        metric,
        register_aggregator,
        scenario_aggregator,
    )
    # smoke: names are defined
    assert ScenarioRun is not None
    assert for_each_scenario is not None


def test_retired_names_no_longer_exported():
    import gaspatchio_core.scenarios as mod

    assert "batch_scenarios" not in dir(mod)
    assert "describe_scenarios" not in dir(mod)
    assert "sensitivity_analysis" not in dir(mod)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scenarios/test_public_surface.py -v
```

Expected: failure on at least one import (the new names aren't re-exported yet).

- [ ] **Step 3: Update `scenarios/__init__.py`**

Replace `bindings/python/gaspatchio_core/scenarios/__init__.py` with:

```python
# ABOUTME: Public scenarios module — typed plans, loop primitive, aggregators, shocks.
# ABOUTME: GSP-100 introduces ScenarioRun + for_each_scenario as the primary surface.

"""Scenario support module for multi-scenario actuarial model execution."""

from gaspatchio_core.scenarios._aggregators import (
    ArgMax,
    ArgMin,
    CTE,
    Count,
    GroupedAgg,
    Max,
    Mean,
    Median,
    Min,
    MultiAgg,
    Quantile,
    QuantileRank,
    ScenarioAggregator,
    ScenarioMetric,
    Std,
    Sum,
    Variance,
    metric,
    register_aggregator,
    scenario_aggregator,
)
from gaspatchio_core.scenarios._config import (
    parse_aggregations,
    parse_scenario_config,
    parse_shock_config,
)
from gaspatchio_core.scenarios._for_each import for_each_scenario
from gaspatchio_core.scenarios._result import ScenarioResult
from gaspatchio_core.scenarios._run import ScenarioRun
from gaspatchio_core.scenarios._with_scenarios import with_scenarios
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    ParameterShock,
    PipelineShock,
    RelativeFloorShock,
    Shock,
    TimeConditionalShock,
)

__all__ = [
    # Shock primitives
    "AdditiveShock", "ClipShock", "FilteredShock", "MaxShock", "MinShock",
    "MultiplicativeShock", "OverrideShock", "ParameterShock", "PipelineShock",
    "RelativeFloorShock", "Shock", "TimeConditionalShock",
    # Low-level
    "with_scenarios", "parse_scenario_config", "parse_shock_config",
    "parse_aggregations",
    # Plan + loop (GSP-100)
    "ScenarioRun", "ScenarioResult", "ScenarioMetric",
    "ScenarioAggregator", "for_each_scenario",
    "register_aggregator", "scenario_aggregator", "metric",
    # Aggregators (GSP-100)
    "Sum", "Count", "Mean", "Std", "Variance",
    "Min", "Max", "ArgMin", "ArgMax",
    "CTE", "Quantile", "Median", "QuantileRank",
    "GroupedAgg", "MultiAgg",
]
```

- [ ] **Step 4: Update `scenarios/__init__.pyi`**

Read `bindings/python/gaspatchio_core/scenarios/__init__.pyi`. Replace it wholesale (this is the type stub; mirror the new public surface):

```python
"""Type stubs for gaspatchio_core.scenarios — GSP-100 surface."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol, overload, runtime_checkable

import polars as pl

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock as AdditiveShock,
    ClipShock as ClipShock,
    FilteredShock as FilteredShock,
    MaxShock as MaxShock,
    MinShock as MinShock,
    MultiplicativeShock as MultiplicativeShock,
    OverrideShock as OverrideShock,
    ParameterShock as ParameterShock,
    PipelineShock as PipelineShock,
    RelativeFloorShock as RelativeFloorShock,
    Shock as Shock,
    TimeConditionalShock as TimeConditionalShock,
)

ScenarioID = str | int

@runtime_checkable
class ScenarioAggregator(Protocol):
    def init(self) -> Any: ...
    def update(self, state: Any, df: pl.DataFrame) -> Any: ...
    def finalize(self, state: Any) -> Any: ...
    def canonical_form(self) -> dict[str, Any]: ...

class ScenarioMetric:
    per_scenario: pl.Expr
    across_scenario: ScenarioAggregator
    def __init__(self, per_scenario: pl.Expr, across_scenario: ScenarioAggregator) -> None: ...
    def canonical_form(self) -> dict[str, Any]: ...

def metric(column: str, agg: ScenarioAggregator) -> ScenarioMetric: ...

class ScenarioResult:
    aggregations: dict[str, Any]
    plan_sha: str
    n_scenarios: int
    batch_size: int
    batch_size_resolution: Literal["manual", "auto_probe", "auto_calibrated"]
    wall_time_s: float
    peak_rss_mb: float | None
    sink_dir: Path | None

class ScenarioRun:
    shocks: dict[str, list[Shock]]
    base_tables: dict[str, Table]
    aggregations: dict[str, ScenarioMetric]
    master_seed: int | None
    def __init__(
        self,
        shocks: dict[str, list[Shock]],
        base_tables: dict[str, Table],
        aggregations: dict[str, ScenarioMetric],
        master_seed: int | None = ...,
    ) -> None: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
    def describe(self) -> str: ...
    def with_extra_shocks(self, more: dict[str, list[Shock]]) -> "ScenarioRun": ...
    def with_extra_aggregations(self, more: dict[str, ScenarioMetric]) -> "ScenarioRun": ...
    def with_master_seed(self, seed: int) -> "ScenarioRun": ...
    @classmethod
    def from_dict(cls, config: dict, *, base_tables: dict[str, Table]) -> "ScenarioRun": ...
    @classmethod
    def from_yaml(cls, path: Path, *, base_tables: dict[str, Table]) -> "ScenarioRun": ...
    def to_dict(self) -> dict[str, Any]: ...
    def to_yaml(self, path: Path) -> None: ...
    def run(
        self,
        af: ActuarialFrame,
        model_fn: Callable[..., ActuarialFrame],
        *,
        batch_size: int | Literal["auto"] = ...,
        target_memory_fraction: float = ...,
        bytes_per_cell: int | None = ...,
        return_full_grid: bool = ...,
        sink_dir: Path | None = ...,
    ) -> ScenarioResult: ...

def for_each_scenario(
    af: ActuarialFrame,
    scenarios: list[ScenarioID] | dict[ScenarioID, list[Shock]] | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., ActuarialFrame],
    agg: ScenarioAggregator,
    *,
    base_tables: dict[str, Table] | None = ...,
    per_scenario: pl.Expr | dict[str, pl.Expr] | None = ...,
    batch_size: int | Literal["auto"] = ...,
    target_memory_fraction: float = ...,
    bytes_per_cell: int | None = ...,
    return_full_grid: bool = ...,
    sink_dir: Path | None = ...,
    master_seed: int | None = ...,
    progress: bool = ...,
) -> ScenarioResult: ...

def register_aggregator(name: str, cls: type) -> None: ...
def scenario_aggregator(name: str | None = ...) -> Callable[[type], type]: ...

def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = ...,
    *,
    categorical: bool = ...,
) -> ActuarialFrame: ...

def parse_scenario_config(config: list[str | dict]) -> dict[str, list[Shock | ParameterShock]]: ...
def parse_shock_config(config: dict[str, Any]) -> Shock | ParameterShock: ...
def parse_aggregations(config: dict[str, Any]) -> dict[str, ScenarioMetric]: ...

# Aggregators
class Sum: ...
class Count: ...
class Mean: ...
class Std: ...
class Variance: ...
class Min: ...
class Max: ...
class ArgMin: ...
class ArgMax: ...
class Median: ...
class QuantileRank:
    at: float
    def __init__(self, at: float) -> None: ...
class CTE:
    level: float
    direction: Literal["upper", "lower"]
    def __init__(self, level: float, direction: Literal["upper", "lower"] = ...) -> None: ...
class Quantile:
    levels: tuple[float, ...]
    def __init__(self, levels: tuple[float, ...]) -> None: ...
class GroupedAgg:
    by: str
    metric: ScenarioAggregator
    def __init__(self, by: str, metric: ScenarioAggregator) -> None: ...
class MultiAgg:
    metrics: dict[str, ScenarioAggregator]
    def __init__(self, metrics: dict[str, ScenarioAggregator]) -> None: ...
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_public_surface.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/__init__.py \
        bindings/python/gaspatchio_core/scenarios/__init__.pyi \
        bindings/python/tests/scenarios/test_public_surface.py
git commit -m "feat(scenarios): wire GSP-100 public surface

scenarios/__init__.py re-exports the new ScenarioRun / for_each_scenario /
ScenarioMetric / 15 aggregators / decorator. .pyi stub updated. Retired
names (batch_scenarios, describe_scenarios, sensitivity_analysis) removed
from both __all__ and the type stub."
```

---

## Phase 6 — Decommissioning

### Task 22: Retire `batch_scenarios`

**Files:**
- Delete: `bindings/python/gaspatchio_core/scenarios/_batching.py`
- Delete: `bindings/python/tests/scenarios/test_batching.py`
- Modify: any callers (search first)

- [ ] **Step 1: Find callers**

```bash
grep -rn "batch_scenarios" bindings/python/ --include="*.py" --include="*.pyi"
```

Expected: hits in tests, possibly tutorials. Note them.

- [ ] **Step 2: Delete the module and its test file**

```bash
rm bindings/python/gaspatchio_core/scenarios/_batching.py
rm bindings/python/tests/scenarios/test_batching.py
```

- [ ] **Step 3: Migrate any remaining callers**

For each caller of `batch_scenarios(...)`, replace with the equivalent `for_each_scenario(..., batch_size=N)` call. Tutorial migration is a separate plan; this task only handles non-tutorial callers.

- [ ] **Step 4: Run full scenarios test suite**

```bash
uv run pytest tests/scenarios/ -v
```

Expected: all green; no test references `batch_scenarios`.

- [ ] **Step 5: Commit**

```bash
git add -A bindings/python/
git commit -m "refactor(scenarios): retire batch_scenarios

Subsumed by for_each_scenario(batch_size=N). Deleted _batching.py and
test_batching.py. Per GSP-100 design decision §11 (breaking change OK)."
```

---

### Task 23: Internalise `sensitivity_analysis`

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py` (already done in Task 21)
- Modify: `bindings/python/gaspatchio_core/scenarios/_sensitivity.py` (remove from `__all__`)

- [ ] **Step 1: Verify `sensitivity_analysis` is no longer in scenarios `__all__`**

```bash
grep -n "sensitivity_analysis" bindings/python/gaspatchio_core/scenarios/__init__.py
```

Expected: no matches (Task 21 removed it).

- [ ] **Step 2: Remove from `_sensitivity.py`'s own `__all__`**

Read `bindings/python/gaspatchio_core/scenarios/_sensitivity.py`. Find the bottom line:

```python
__all__ = ["sensitivity_analysis"]
```

Replace with:

```python
# Module is now internal; no public __all__.
# Use ScenarioRun + sweep configs instead. The function remains importable
# from gaspatchio_core.scenarios._sensitivity for internal/tutorial callers.
```

- [ ] **Step 3: Migrate the sensitivity tutorial caller**

The tutorial `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/03-sensitivity/run_scenarios.py` uses `sensitivity_analysis()` (per the inventory). Update its import to:

```python
from gaspatchio_core.scenarios._sensitivity import sensitivity_analysis  # internal
```

(Full tutorial rewrite is a separate plan; this is the minimal compile-fix.)

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/scenarios/test_sensitivity_analysis.py tests/scenarios/test_shock_integration.py -v
```

Expected: tests update their imports to `_sensitivity` (internal) or to pass without the function; fix any remaining failures by updating imports.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_sensitivity.py \
        bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/03-sensitivity/run_scenarios.py \
        bindings/python/tests/scenarios/
git commit -m "refactor(scenarios): internalise sensitivity_analysis

Removed from public __all__ per GSP-100 §11. Function remains importable
from gaspatchio_core.scenarios._sensitivity for internal callers (tutorials,
tests). New scenario sweeps should use ScenarioRun + parametric configs."
```

---

### Task 24: Merge `describe_scenarios` into `ScenarioRun.describe()` overload, retire standalone

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_run.py` (extend `describe`)
- Delete: `bindings/python/gaspatchio_core/scenarios/_describe.py`
- Delete: `bindings/python/tests/scenarios/test_describe_scenarios.py`
- Modify: callers (tutorials + scratch tests)

- [ ] **Step 1: Find callers**

```bash
grep -rn "describe_scenarios" bindings/python/ --include="*.py" --include="*.pyi"
```

Expected: tutorial steps + scratch test files.

- [ ] **Step 2: Migrate callers to `ScenarioRun.from_dict(...).describe()`**

For each caller found in Step 1, replace `describe_scenarios(shocks_dict)` with the ScenarioRun-based equivalent. The minimal replacement for a caller that only has shocks (no base_tables/aggregations) is:

```python
# Before:
desc = describe_scenarios(shocks_dict, output_format="markdown")

# After:
from gaspatchio_core.scenarios import ScenarioRun
plan = ScenarioRun(shocks=shocks_dict, base_tables={}, aggregations={})
desc = plan.describe()
```

(Full markdown/text/dict format options were on `describe_scenarios`; `ScenarioRun.describe()` returns the one-paragraph audit string only. If callers actually need the formatted output, port the formatting into `ScenarioRun.describe(output_format=...)` — but most callers want the audit string. Add the overload only if a caller actually needs it.)

- [ ] **Step 3: Delete the standalone module**

```bash
rm bindings/python/gaspatchio_core/scenarios/_describe.py
rm bindings/python/tests/scenarios/test_describe_scenarios.py
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/scenarios/ -v
```

Expected: all green; no test references `describe_scenarios`.

- [ ] **Step 5: Commit**

```bash
git add -A bindings/python/
git commit -m "refactor(scenarios): retire describe_scenarios

ScenarioRun.describe() is now the canonical audit-string entry point.
Callers migrated to construct a ScenarioRun and call .describe(). Standalone
_describe.py and its test removed."
```

---

## Phase 7 — Integration

### Task 25: End-to-end audit-chain test

**Files:**
- Create: `bindings/python/tests/scenarios/test_audit_chain.py`

- [ ] **Step 1: Write the test**

Create `bindings/python/tests/scenarios/test_audit_chain.py`:

```python
"""End-to-end audit-chain test — SHA stability across plan reconstructions."""
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import (
    CTE,
    MultiplicativeShock,
    ScenarioRun,
    Sum,
    metric,
)


@pytest.fixture
def mortality_table():
    df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.0012, 0.0015]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


def test_sha_stable_across_insertion_orders(mortality_table):
    p1 = ScenarioRun(
        shocks={"A": [], "B": [MultiplicativeShock(factor=1.5)]},
        base_tables={"mortality": mortality_table},
        aggregations={"x": metric("v", Sum()), "y": metric("v", CTE(0.05))},
    )
    p2 = ScenarioRun(
        shocks={"B": [MultiplicativeShock(factor=1.5)], "A": []},
        base_tables={"mortality": mortality_table},
        aggregations={"y": metric("v", CTE(0.05)), "x": metric("v", Sum())},
    )
    assert p1.source_sha() == p2.source_sha()


def test_sha_changes_with_shock_difference(mortality_table):
    p1 = ScenarioRun(
        shocks={"A": [MultiplicativeShock(factor=1.5)]},
        base_tables={"mortality": mortality_table},
        aggregations={"x": metric("v", Sum())},
    )
    p2 = ScenarioRun(
        shocks={"A": [MultiplicativeShock(factor=1.6)]},
        base_tables={"mortality": mortality_table},
        aggregations={"x": metric("v", Sum())},
    )
    assert p1.source_sha() != p2.source_sha()


def test_sha_changes_with_table_content(mortality_table):
    df_other = pl.DataFrame({"age": [30, 31, 32], "rate": [0.002, 0.0024, 0.003]})
    other_table = Table(name="mortality", source=df_other, dimensions={"age": "age"}, value="rate")
    p1 = ScenarioRun(
        shocks={"A": []},
        base_tables={"mortality": mortality_table},
        aggregations={"x": metric("v", Sum())},
    )
    p2 = ScenarioRun(
        shocks={"A": []},
        base_tables={"mortality": other_table},
        aggregations={"x": metric("v", Sum())},
    )
    assert p1.source_sha() != p2.source_sha()


def test_yaml_round_trip_preserves_sha(tmp_path, mortality_table):
    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(factor=1.2, table="mortality")]},
        base_tables={"mortality": mortality_table},
        aggregations={"scr": metric("v", CTE(level=0.005, direction="upper"))},
        master_seed=42,
    )
    out = tmp_path / "plan.yaml"
    plan.to_yaml(out)
    reloaded = ScenarioRun.from_yaml(out, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()
```

- [ ] **Step 2: Run tests to verify pass**

```bash
uv run pytest tests/scenarios/test_audit_chain.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/scenarios/test_audit_chain.py
git commit -m "test(scenarios): end-to-end audit-chain SHA stability

Covers GSP-100 acceptance criterion: same plan produces same source_sha
regardless of dict insertion order; SHA changes with any shock/table/agg
difference; YAML round-trip preserves SHA."
```

---

### Task 26: Run full test suite + verify benchmark

- [ ] **Step 1: Run all scenarios tests**

```bash
uv run pytest tests/scenarios/ tests/assumptions/test_table_identity.py tests/test_identity.py -v
```

Expected: all green.

- [ ] **Step 2: Run doctest of public stubs**

```bash
uv run pytest --doctest-modules --doctest-glob="*.pyi" bindings/python/gaspatchio_core/scenarios/ -v
```

Expected: green (no doctest failures).

- [ ] **Step 3: Run benchmark**

```bash
uv run pytest benchmarks/scenariorun/ -v -m bench
```

Expected: 2 passed; peak_rss_mb bounded.

- [ ] **Step 4: Run ruff**

```bash
uv run ruff check bindings/python/gaspatchio_core/scenarios/
uv run ruff format --check bindings/python/gaspatchio_core/scenarios/
```

Expected: no issues.

- [ ] **Step 5: Final commit (CHANGELOG)**

Edit `CHANGELOG.md` (if it exists) or create a brief release note. Add entry:

```markdown
## [Unreleased] — GSP-100 ScenarioRun

### Added
- `ScenarioRun` typed plan with `canonical_form()` / `source_sha()` / `describe()`
- `for_each_scenario` bounded-memory loop primitive
- `ScenarioMetric(per_scenario, across_scenario)` reduction recipe
- 15 starter aggregators: Sum, Count, Mean, Std, Variance, Min, Max, ArgMin, ArgMax, CTE, Quantile, Median, QuantileRank, GroupedAgg, MultiAgg
- `@scenario_aggregator()` decorator for user-defined plugins
- `Table.canonical_form()` and `Table.source_sha()`
- `master_seed` plumbing via `drivers["rng_seed"]` (sha256-derived)

### Removed (breaking)
- `batch_scenarios` (use `for_each_scenario(batch_size=N)`)
- `describe_scenarios` (use `ScenarioRun.describe()`)
- `sensitivity_analysis` (now internal; use `ScenarioRun` configs)

### Internal
- `canonical_bytes` lifted from `schedule/_canonical.py` to `_identity.py`
```

Commit:

```bash
git add CHANGELOG.md
git commit -m "docs: GSP-100 release notes — ScenarioRun + 15 aggregators"
```

---

## Follow-on plans (NOT in this plan)

1. **Tutorial rework** (`tutorial/level-5-scenarios/`) — rewritten around `ScenarioRun`. See spec §9. Save plan to `ref/41-backend-portability/plans/2026-05-NN-gsp-100-tutorial-rework.md`.
2. **gaspatchio-docs updates** (sister repo) — concept pages, API reference, decision tree, audit-chain page. See spec §10. Save plan to `ref/41-backend-portability/plans/2026-05-NN-gsp-100-docs-updates.md`.

These are independent of each other and depend on the core library landing first.

---

## Self-review

**1. Spec coverage:** Every numbered design decision (§2) traces to at least one task. §3 module layout ↔ task file paths. §4 data shapes ↔ Tasks 14, 19. §5 loop ↔ Tasks 15–17. §6 aggregators ↔ Tasks 4–9. §7 audit chain ↔ Tasks 1–3, 19, 25. §8 testing ↔ Tasks 10, 25; benchmark ↔ Task 18. §9 tutorial rework, §10 docs — explicitly deferred to follow-on plans (noted at end). §11 decommissioning ↔ Tasks 22–24.

**2. Placeholder scan:** No TBD/TODO/"implement later". The `_for_each.py` Phase 1 mentions `n_periods=240` as a "placeholder for Phase 1; refined in Phase 2 task" — this is a concrete number with a documented refinement path, not a TBD. Tutorial-step pyfile migration in Task 23 is one-line; the full tutorial rewrite is the separate follow-on plan.

**3. Type consistency:** Aggregator names match across tasks (verified `CTE`, `Quantile`, `Median`, `QuantileRank` spelling matches). `ScenarioMetric` field names (`per_scenario`, `across_scenario`) match between Task 9 and Task 19's `ScenarioRun.run` delegation. `ScenarioResult` fields (`batch_size_resolution`, `peak_rss_mb`, `sink_dir`) match between Task 14 and the spec.
