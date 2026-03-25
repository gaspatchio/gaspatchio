# GSP-86 Rollforward API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Phase 1 rollforward engine — a declarative method-chain builder that compiles to a high-performance Rust kernel, supporting single-state and multi-state account value projections with increment tracking, step composition, and model fingerprinting.

**Architecture:** A Python `RollforwardBuilder` captures step declarations as an immutable tuple of `StepDef` objects. On assignment to an `ActuarialFrame`, `_compile()` resolves column references to positional indices and serializes to JSON kwargs. A Rust Polars plugin function (`rollforward`) receives `&[Series]` inputs plus `RollforwardKwargs` and executes a step-dispatch inner loop per policy. Output is always a Struct column; Python extracts fields lazily.

**Tech Stack:** Rust (Polars 0.49, pyo3-polars 0.22, serde), Python (Polars 1.27, dataclasses), Maturin build

**Spec:** `ref/31-rollforward-api/31-rollforward-design.md` (911 lines)
**Composition spec:** `ref/31-rollforward-api/31-rollforward-composition.md` (917 lines)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `core/src/polars_functions/rollforward.rs` | Rust kernel: kwargs types, fast/slow path, step dispatch, Struct output |
| `bindings/python/gaspatchio_core/rollforward/__init__.py` | Public exports: `Step`, `StepDef`, `RollforwardBuilder` |
| `bindings/python/gaspatchio_core/rollforward/_step.py` | `StepDef` dataclass + `Step` factory namespace |
| `bindings/python/gaspatchio_core/rollforward/_builder.py` | `RollforwardBuilder` — immutable builder with step/composition methods |
| `bindings/python/gaspatchio_core/rollforward/_compile.py` | `compile_rollforward()` — builder → `(args, kwargs)` for `register_plugin_function` |
| `bindings/python/gaspatchio_core/rollforward/_explain.py` | `explain()` formatter, `canonical()` dict, `fingerprint()` SHA-256 |
| `bindings/python/gaspatchio_core/accessors/projection_frame.py` | `ProjectionFrameAccessor` — frame-level `af.projection.rollforward()` |
| `bindings/python/tests/rollforward/__init__.py` | Test package |
| `bindings/python/tests/rollforward/test_step.py` | StepDef + Step factory tests |
| `bindings/python/tests/rollforward/test_builder.py` | Builder construction, step methods, label validation |
| `bindings/python/tests/rollforward/test_composition.py` | Composition method tests |
| `bindings/python/tests/rollforward/test_compile.py` | _compile() output structure tests |
| `bindings/python/tests/rollforward/test_kernel_single.py` | Single-state kernel end-to-end tests |
| `bindings/python/tests/rollforward/test_kernel_multi.py` | Multi-state kernel end-to-end tests |
| `bindings/python/tests/rollforward/test_increments.py` | Increment tracking tests |
| `bindings/python/tests/rollforward/test_explain.py` | explain() + fingerprint() tests |
| `bindings/python/tests/rollforward/test_integration.py` | Full product rollforward tests (UL, VA+GMDB) |

### Modified Files

| File | Change |
|------|--------|
| `core/src/polars_functions/mod.rs` | Add `pub mod rollforward;` + re-export |
| `core/src/lib.rs` | Export `RollforwardKwargs` |
| `bindings/python/src/vector.rs` | Add `rollforward` PyO3 wrapper function |
| `bindings/python/gaspatchio_core/functions/vector.py` | Add `rollforward()` Python wrapper |
| `bindings/python/gaspatchio_core/accessors/__init__.py` | Import `projection_frame` module |
| `bindings/python/gaspatchio_core/frame/base.py` | `__setitem__` support for `RollforwardBuilder`, `collect()` strips hidden columns |
| `bindings/python/gaspatchio_core/__init__.py` | Re-export rollforward public API |

---

## Dependency Graph

```
Task 1 (StepDef + Step)
    ↓
Task 2 (Builder core) ← depends on Task 1
    ↓
Task 3 (Composition) ← depends on Task 2
    |
    |  Task 4 (Rust kwargs types) — independent
    |      ↓
    |  Task 5 (Rust single-state core) ← depends on Task 4
    |      ↓
    |  Task 6 (Rust advanced steps) ← depends on Task 5
    |      ↓
    |  Task 7 (Rust increment tracking) ← depends on Task 5
    |      ↓
    |  Task 8 (Rust multi-state) ← depends on Task 5, 7
    |      ↓
    |  Task 9 (Rust slow path) ← depends on Tasks 5, 6, 8
    |      ↓
    |  Task 10 (PyO3 wrapper) ← depends on Task 5
    |      ↓
    ↓      ↓
Task 11 (_compile) ← depends on Task 2, 10
    ↓
Task 12 (Frame accessor) ← depends on Task 11
    ↓
Task 13 (__setitem__ integration) ← depends on Task 12
    ↓
Task 14 (Increment/capture access) ← depends on Task 13, 7
    ↓
Task 15 (Multi-state Python) ← depends on Task 13, 8
    ↓
Task 16 (explain + fingerprint) ← depends on Task 2
    ↓
Task 17 (Integration tests) ← depends on all above
    ↓
Task 18 (Build + verify) ← depends on Task 17
```

Tasks 1-3 (Python) and Tasks 4-10 (Rust) can be developed in parallel.

## Review Findings & Decisions

These findings were identified during plan review and must be addressed during implementation:

1. **`__setattr__` guard**: `ActuarialFrame.__setattr__` has a `known_internal` set. Any new internal attributes (e.g., `_rollforward_builders`) must be added to it, or use `object.__setattr__()` directly.

2. **Canonical form must exclude labels**: Per spec Section 15 line 795, canonical form "Excludes column names, labels, input indices." The `canonical()` function must only include operation type, structural kwargs (floor/cap values), and step count — NOT labels or column names.

3. **Output type function for Struct**: The `rollforward_output` function returns a static Struct schema. Polars' lazy engine may validate schema at plan time. If this causes issues, Options:
   - A: Return `DataType::Unknown(UnknownKind::Any)` (permissive but loses optimization)
   - B: Always return `Struct { "result": List<Float64> }` and handle multi-state field mismatches
   - C: Pass field names through a secondary mechanism
   - **Validate approach A or B as a spike in Task 10 before Task 11.**

4. **Task 9 (slow path)**: Must be implemented AFTER Tasks 5, 6, AND 8 (needs all step types).

5. **Capture output to Struct**: Captures must appear as fields in the Struct output when `track_increments=True`. The Rust kernel must push capture values to output buffers alongside increments.

6. **`lapse_if_zero` semantics**: Current timestep value IS recorded (e.g., -50), only FUTURE timesteps are zeroed. This matches the design where lapse fires at end of timestep.

7. **Top-level re-export**: `gaspatchio_core/__init__.py` must re-export `RollforwardBuilder`, `Step`, `StepDef`.

---

### Task 1: StepDef Dataclass and Step Factory

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward/__init__.py`
- Create: `bindings/python/gaspatchio_core/rollforward/_step.py`
- Create: `bindings/python/tests/rollforward/__init__.py`
- Create: `bindings/python/tests/rollforward/test_step.py`

This task creates the foundational data structures. `StepDef` is the immutable internal representation of a rollforward step. `Step` is the public factory namespace for creating `StepDef` objects (used in composition).

- [ ] **Step 1: Write failing tests for StepDef**

```python
# tests/rollforward/test_step.py
from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._step import Step, StepDef


class TestStepDef:
    def test_creation(self) -> None:
        step = StepDef(operation="add", label="Premium", args=("premium",))
        assert step.operation == "add"
        assert step.label == "Premium"
        assert step.args == ("premium",)
        assert step.kwargs == {}

    def test_frozen(self) -> None:
        step = StepDef(operation="add", label="Premium", args=("premium",))
        with pytest.raises(AttributeError):
            step.operation = "charge"  # type: ignore[misc]

    def test_with_kwargs(self) -> None:
        step = StepDef(
            operation="deduct_nar",
            label="COI",
            args=("coi_rate",),
            kwargs={"death_benefit": "sum_assured"},
        )
        assert step.kwargs["death_benefit"] == "sum_assured"

    def test_equality(self) -> None:
        s1 = StepDef(operation="add", label="Premium", args=("premium",))
        s2 = StepDef(operation="add", label="Premium", args=("premium",))
        assert s1 == s2


class TestStepFactory:
    def test_add(self) -> None:
        step = Step.add("premium", "Premium")
        assert step.operation == "add"
        assert step.label == "Premium"
        assert step.args == ("premium",)

    def test_add_auto_label(self) -> None:
        step = Step.add("premium")
        assert step.label == "Add(premium)"

    def test_charge(self) -> None:
        step = Step.charge("admin_rate", "Admin")
        assert step.operation == "charge"
        assert step.label == "Admin"

    def test_grow(self) -> None:
        step = Step.grow("interest_rate", "Interest")
        assert step.operation == "grow"
        assert step.label == "Interest"

    def test_subtract(self) -> None:
        step = Step.subtract("expense", "Expense")
        assert step.operation == "subtract"
        assert step.label == "Expense"

    def test_grow_capped(self) -> None:
        step = Step.grow_capped("index_return", floor=0.0, cap=0.12, label="Index Credit")
        assert step.operation == "grow_capped"
        assert step.kwargs["floor"] == 0.0
        assert step.kwargs["cap"] == 0.12

    def test_deduct_nar(self) -> None:
        step = Step.deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
        assert step.operation == "deduct_nar"
        assert step.kwargs["death_benefit"] == "sum_assured"

    def test_floor(self) -> None:
        step = Step.floor(0.0)
        assert step.operation == "floor"
        assert step.label == "Floor(0.0)"
        assert step.args == (0.0,)

    def test_cap(self) -> None:
        step = Step.cap(1000000.0, "Max AV")
        assert step.operation == "cap"
        assert step.label == "Max AV"

    def test_add_if(self) -> None:
        step = Step.add_if("is_premium_month", "premium", "Conditional Premium")
        assert step.operation == "add_if"
        assert step.args == ("is_premium_month", "premium")

    def test_charge_if(self) -> None:
        step = Step.charge_if("is_vul", "me_rate", "M&E Fee")
        assert step.operation == "charge_if"
        assert step.args == ("is_vul", "me_rate")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_step.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create the rollforward package and StepDef dataclass**

```python
# bindings/python/gaspatchio_core/rollforward/__init__.py
"""Rollforward API for non-linear account value projections."""

from gaspatchio_core.rollforward._step import Step, StepDef

__all__ = ["Step", "StepDef"]
```

```python
# bindings/python/gaspatchio_core/rollforward/_step.py
"""StepDef dataclass and Step factory namespace for rollforward operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _col_name(ref: Any) -> str:  # noqa: ANN401
    """Extract a display name from a column reference."""
    if isinstance(ref, str):
        return ref
    if hasattr(ref, "name"):
        return ref.name
    return str(ref)


@dataclass(slots=True, frozen=True)
class StepDef:
    """Internal representation of a single rollforward step.

    Immutable. Used by RollforwardBuilder for storage and composition
    operations. Not part of the public API — users interact through
    builder methods or the Step factory.
    """

    operation: str
    label: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any] = field(default_factory=dict)


class Step:
    """Factory namespace for creating StepDef objects.

    Used with composition methods (insert_before, insert_after, replace,
    prepend, append). Column arguments accept ColumnProxy, ExpressionProxy,
    or str (for templates).

    Examples
    --------
    ```python
    from gaspatchio_core.rollforward import Step

    step = Step.charge(af.rider_rate, "Rider Fee")
    builder = base.insert_before("Interest", step)
    ```
    """

    def __init__(self) -> None:
        msg = "Step is a namespace class and cannot be instantiated."
        raise TypeError(msg)

    @staticmethod
    def add(
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create an Add step: av += amount[t]."""
        label = label or f"Add({_col_name(amount)})"
        return StepDef(operation="add", label=label, args=(amount,))

    @staticmethod
    def subtract(
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a Subtract step: av -= amount[t]."""
        label = label or f"Subtract({_col_name(amount)})"
        return StepDef(operation="subtract", label=label, args=(amount,))

    @staticmethod
    def charge(
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a Charge step: av *= (1 - rate[t])."""
        label = label or f"Charge({_col_name(rate)})"
        return StepDef(operation="charge", label=label, args=(rate,))

    @staticmethod
    def grow(
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a Grow step: av *= (1 + rate[t])."""
        label = label or f"Grow({_col_name(rate)})"
        return StepDef(operation="grow", label=label, args=(rate,))

    @staticmethod
    def grow_capped(
        rate: Any,  # noqa: ANN401
        *,
        floor: float,
        cap: float,
        label: str | None = None,
    ) -> StepDef:
        """Create a GrowCapped step: av *= (1 + clamp(rate[t], floor, cap))."""
        label = label or f"GrowCapped({_col_name(rate)})"
        return StepDef(
            operation="grow_capped",
            label=label,
            args=(rate,),
            kwargs={"floor": floor, "cap": cap},
        )

    @staticmethod
    def deduct_nar(
        rate: Any,  # noqa: ANN401
        *,
        death_benefit: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a DeductNAR step: av -= rate[t] * max(0, db[t] - av)."""
        label = label or f"DeductNAR({_col_name(rate)})"
        return StepDef(
            operation="deduct_nar",
            label=label,
            args=(rate,),
            kwargs={"death_benefit": death_benefit},
        )

    @staticmethod
    def floor(value: float, label: str | None = None) -> StepDef:
        """Create a Floor step: av = max(av, value)."""
        label = label or f"Floor({value})"
        return StepDef(operation="floor", label=label, args=(value,))

    @staticmethod
    def cap(value: float, label: str | None = None) -> StepDef:
        """Create a Cap step: av = min(av, value)."""
        label = label or f"Cap({value})"
        return StepDef(operation="cap", label=label, args=(value,))

    @staticmethod
    def add_if(
        condition: Any,  # noqa: ANN401
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a conditional Add step: if condition[t]: av += amount[t]."""
        label = label or f"AddIf({_col_name(amount)})"
        return StepDef(operation="add_if", label=label, args=(condition, amount))

    @staticmethod
    def charge_if(
        condition: Any,  # noqa: ANN401
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> StepDef:
        """Create a conditional Charge step: if condition[t]: av *= (1 - rate[t])."""
        label = label or f"ChargeIf({_col_name(rate)})"
        return StepDef(operation="charge_if", label=label, args=(condition, rate))
```

Also create the test package init:
```python
# tests/rollforward/__init__.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_step.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward/ bindings/python/tests/rollforward/
git commit -m "feat(rollforward): add StepDef dataclass and Step factory namespace"
```

---

### Task 2: RollforwardBuilder Core — Immutable Builder with Step Methods

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward/_builder.py`
- Create: `bindings/python/tests/rollforward/test_builder.py`
- Modify: `bindings/python/gaspatchio_core/rollforward/__init__.py`

The builder stores steps as a `tuple[StepDef, ...]`. Every method returns a new builder (immutable). Labels are required-unique with auto-generation.

- [ ] **Step 1: Write failing tests for builder construction and single-state step methods**

```python
# tests/rollforward/test_builder.py
from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._step import StepDef


class TestBuilderConstruction:
    def test_single_state_init(self) -> None:
        builder = RollforwardBuilder(
            frame=None,  # No frame needed for pure builder tests
            initial="av_init",
        )
        assert builder.steps == ()
        assert builder.labels == ()
        assert builder._track_increments is False

    def test_multi_state_init(self) -> None:
        builder = RollforwardBuilder(
            frame=None,
            states={"av": "av_init", "guarantee": "guarantee_init"},
        )
        assert builder._current_target == "av"  # first state

    def test_track_increments(self) -> None:
        builder = RollforwardBuilder(
            frame=None,
            initial="av_init",
            track_increments=True,
        )
        assert builder._track_increments is True


class TestStepMethods:
    @pytest.fixture
    def builder(self) -> RollforwardBuilder:
        return RollforwardBuilder(frame=None, initial="av_init")

    def test_add(self, builder: RollforwardBuilder) -> None:
        b2 = builder.add("premium", "Premium")
        assert len(b2.steps) == 1
        assert b2.steps[0].operation == "add"
        assert b2.steps[0].label == "Premium"

    def test_add_auto_label(self, builder: RollforwardBuilder) -> None:
        b2 = builder.add("premium")
        assert b2.steps[0].label == "Add(premium)"

    def test_subtract(self, builder: RollforwardBuilder) -> None:
        b2 = builder.subtract("expense", "Expense")
        assert b2.steps[0].operation == "subtract"

    def test_charge(self, builder: RollforwardBuilder) -> None:
        b2 = builder.charge("admin_rate", "Admin")
        assert b2.steps[0].operation == "charge"

    def test_grow(self, builder: RollforwardBuilder) -> None:
        b2 = builder.grow("interest_rate", "Interest")
        assert b2.steps[0].operation == "grow"

    def test_grow_capped(self, builder: RollforwardBuilder) -> None:
        b2 = builder.grow_capped("index_return", floor=0.0, cap=0.12, label="Index")
        assert b2.steps[0].operation == "grow_capped"
        assert b2.steps[0].kwargs["floor"] == 0.0
        assert b2.steps[0].kwargs["cap"] == 0.12

    def test_deduct_nar(self, builder: RollforwardBuilder) -> None:
        b2 = builder.deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
        assert b2.steps[0].operation == "deduct_nar"
        assert b2.steps[0].kwargs["death_benefit"] == "sum_assured"

    def test_floor(self, builder: RollforwardBuilder) -> None:
        b2 = builder.floor(0)
        assert b2.steps[0].operation == "floor"
        assert b2.steps[0].label == "Floor(0)"

    def test_cap(self, builder: RollforwardBuilder) -> None:
        b2 = builder.cap(1_000_000, "Max AV")
        assert b2.steps[0].operation == "cap"

    def test_lapse_if_zero(self, builder: RollforwardBuilder) -> None:
        b2 = builder.lapse_if_zero()
        assert b2.steps[0].operation == "lapse_if_zero"

    def test_add_if(self, builder: RollforwardBuilder) -> None:
        b2 = builder.add_if("is_premium_month", "premium", "Conditional Premium")
        assert b2.steps[0].operation == "add_if"

    def test_charge_if(self, builder: RollforwardBuilder) -> None:
        b2 = builder.charge_if("is_vul", "me_rate", "M&E Fee")
        assert b2.steps[0].operation == "charge_if"

    def test_capture(self, builder: RollforwardBuilder) -> None:
        b2 = builder.add("premium", "Premium").capture("av_after_premium")
        assert b2.steps[1].operation == "capture"
        assert b2.steps[1].args == ("av_after_premium",)


class TestImmutability:
    def test_add_returns_new_builder(self) -> None:
        b1 = RollforwardBuilder(frame=None, initial="av_init")
        b2 = b1.add("premium", "Premium")
        assert len(b1.steps) == 0
        assert len(b2.steps) == 1

    def test_chain_builds_correctly(self) -> None:
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
            .grow("interest_rate", "Interest")
            .floor(0)
        )
        assert len(b.steps) == 4
        assert b.labels == ("Premium", "Admin", "Interest", "Floor(0)")


class TestLabelValidation:
    def test_duplicate_label_raises(self) -> None:
        b = RollforwardBuilder(frame=None, initial="av_init").add("premium", "Premium")
        with pytest.raises(ValueError, match="Duplicate label"):
            b.add("bonus", "Premium")

    def test_auto_labels_unique(self) -> None:
        b = RollforwardBuilder(frame=None, initial="av_init").add("premium")
        with pytest.raises(ValueError, match="Duplicate label"):
            b.add("premium")  # same column → same auto-label


class TestMultiStateOn:
    def test_on_switches_target(self) -> None:
        b = RollforwardBuilder(
            frame=None,
            states={"av": "av_init", "guarantee": "g_init"},
        )
        b2 = b.on("av").add("premium", "Premium")
        assert b2.steps[0].kwargs.get("_target") == "av"

    def test_on_invalid_state_raises(self) -> None:
        b = RollforwardBuilder(
            frame=None,
            states={"av": "av_init", "guarantee": "g_init"},
        )
        with pytest.raises(ValueError, match="Unknown state"):
            b.on("invalid")

    def test_on_sticky(self) -> None:
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
            .on("guarantee")
            .grow("roll_up_rate", "Roll-up")
        )
        assert b.steps[0].kwargs.get("_target") == "av"
        assert b.steps[1].kwargs.get("_target") == "av"
        assert b.steps[2].kwargs.get("_target") == "guarantee"


class TestLapseWhen:
    def test_lapse_when_stored_separately(self) -> None:
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av").add("premium", "Premium")
            .lapse_when(all_non_positive=["av", "guarantee"])
        )
        assert b._lapse_condition == {"all_non_positive": ["av", "guarantee"]}
        # lapse_when is NOT a step
        assert all(s.operation != "lapse_when" for s in b.steps)

    def test_lapse_when_single_state_raises(self) -> None:
        b = RollforwardBuilder(frame=None, initial="av_init")
        with pytest.raises(ValueError, match="multi-state"):
            b.lapse_when(all_non_positive=["av"])

    def test_multiple_lapse_when_raises(self) -> None:
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .lapse_when(all_non_positive=["av"])
        )
        with pytest.raises(ValueError, match="one lapse_when"):
            b.lapse_when(all_non_positive=["guarantee"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_builder.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement RollforwardBuilder**

```python
# bindings/python/gaspatchio_core/rollforward/_builder.py
"""Immutable rollforward builder with step methods and composition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio_core.rollforward._step import StepDef, _col_name

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame


class RollforwardBuilder:
    """Bound rollforward builder with composition support.

    Created via af.projection.rollforward(initial=...). Immutable —
    every method returns a new builder. Steps stored as tuple[StepDef, ...].

    Parameters
    ----------
    frame
        Parent ActuarialFrame (None for pure builder tests).
    initial
        Initial value column reference (single-state mode).
    states
        Dict of state_name → initial_column_ref (multi-state mode).
    track_increments
        Whether to record per-step dollar increments.
    """

    __slots__ = (
        "_frame",
        "_initial",
        "_states",
        "_steps",
        "_track_increments",
        "_current_target",
        "_lapse_condition",
    )

    def __init__(
        self,
        frame: ActuarialFrame | None,
        *,
        initial: Any = None,  # noqa: ANN401
        states: dict[str, Any] | None = None,
        track_increments: bool = False,
        # Internal: used by _with_steps to preserve state
        _steps: tuple[StepDef, ...] = (),
        _current_target: str | None = None,
        _lapse_condition: dict[str, Any] | None = None,
    ) -> None:
        self._frame = frame
        self._track_increments = track_increments
        self._steps = _steps
        self._lapse_condition = _lapse_condition

        if states is not None:
            self._initial = None
            self._states = states
            self._current_target = _current_target or next(iter(states))
        elif initial is not None:
            self._initial = initial
            self._states = None
            self._current_target = _current_target or "__default__"
        else:
            msg = "Must provide either 'initial' (single-state) or 'states' (multi-state)."
            raise ValueError(msg)

    @property
    def is_multi_state(self) -> bool:
        """Return True if this builder operates in multi-state mode."""
        return self._states is not None

    @property
    def steps(self) -> tuple[StepDef, ...]:
        """Return the current step sequence (read-only)."""
        return self._steps

    @property
    def labels(self) -> tuple[str, ...]:
        """Return all step labels in order."""
        return tuple(s.label for s in self._steps)

    # ── Internal helpers ───────────────────────────────────────────

    def _new(
        self,
        *,
        steps: tuple[StepDef, ...] | None = None,
        current_target: str | None = None,
        lapse_condition: dict[str, Any] | None = None,
    ) -> RollforwardBuilder:
        """Return a new builder preserving all fields except those overridden."""
        return RollforwardBuilder(
            frame=self._frame,
            initial=self._initial,
            states=self._states,
            track_increments=self._track_increments,
            _steps=steps if steps is not None else self._steps,
            _current_target=current_target or self._current_target,
            _lapse_condition=lapse_condition if lapse_condition is not None else self._lapse_condition,
        )

    def _check_unique_label(self, label: str) -> None:
        for i, s in enumerate(self._steps):
            if s.label == label:
                msg = (
                    f"Duplicate label {label!r} in rollforward. "
                    f"Already used at step {i + 1}."
                )
                raise ValueError(msg)

    def _find_label(self, label: str) -> int:
        for i, s in enumerate(self._steps):
            if s.label == label:
                return i
        available = [s.label for s in self._steps]
        msg = (
            f"No step with label {label!r} in rollforward. "
            f"Available labels: {available}"
        )
        raise KeyError(msg)

    def _append_step(self, step: StepDef) -> RollforwardBuilder:
        self._check_unique_label(step.label)
        return self._new(steps=(*self._steps, step))

    def _make_step(
        self,
        operation: str,
        label: str | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any] | None = None,
        *,
        auto_label_prefix: str | None = None,
        auto_label_ref: Any = None,  # noqa: ANN401
    ) -> StepDef:
        if label is None and auto_label_prefix is not None:
            label = f"{auto_label_prefix}({_col_name(auto_label_ref)})"
        elif label is None:
            label = operation
        kw = dict(kwargs) if kwargs else {}
        if self.is_multi_state:
            kw["_target"] = self._current_target
        return StepDef(operation=operation, label=label, args=args, kwargs=kw)

    # ── State targeting (multi-state) ──────────────────────────────

    def on(self, state_name: str) -> RollforwardBuilder:
        """Switch target state for subsequent steps (sticky)."""
        if self._states is None:
            msg = ".on() is only valid in multi-state mode."
            raise ValueError(msg)
        if state_name not in self._states:
            msg = f"Unknown state {state_name!r}. Available: {list(self._states)}"
            raise ValueError(msg)
        if state_name == self._current_target:
            return self  # no-op
        return self._new(current_target=state_name)

    # ── Step methods ───────────────────────────────────────────────

    def add(
        self,
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Add amount to current state: av += amount[t]."""
        step = self._make_step(
            "add", label, (amount,), auto_label_prefix="Add", auto_label_ref=amount,
        )
        return self._append_step(step)

    def subtract(
        self,
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Subtract amount from current state: av -= amount[t]."""
        step = self._make_step(
            "subtract", label, (amount,),
            auto_label_prefix="Subtract", auto_label_ref=amount,
        )
        return self._append_step(step)

    def charge(
        self,
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Charge proportional rate: av *= (1 - rate[t])."""
        step = self._make_step(
            "charge", label, (rate,), auto_label_prefix="Charge", auto_label_ref=rate,
        )
        return self._append_step(step)

    def grow(
        self,
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Grow by rate: av *= (1 + rate[t])."""
        step = self._make_step(
            "grow", label, (rate,), auto_label_prefix="Grow", auto_label_ref=rate,
        )
        return self._append_step(step)

    def grow_capped(
        self,
        rate: Any,  # noqa: ANN401
        *,
        floor: float,
        cap: float,
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Grow by clamped rate: av *= (1 + clamp(rate[t], floor, cap))."""
        step = self._make_step(
            "grow_capped", label, (rate,),
            kwargs={"floor": floor, "cap": cap},
            auto_label_prefix="GrowCapped", auto_label_ref=rate,
        )
        return self._append_step(step)

    def deduct_nar(
        self,
        rate: Any,  # noqa: ANN401
        *,
        death_benefit: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Deduct net amount at risk: av -= rate[t] * max(0, db[t] - av)."""
        step = self._make_step(
            "deduct_nar", label, (rate,),
            kwargs={"death_benefit": death_benefit},
            auto_label_prefix="DeductNAR", auto_label_ref=rate,
        )
        return self._append_step(step)

    def floor(self, value: float, label: str | None = None) -> RollforwardBuilder:
        """Apply floor: av = max(av, value)."""
        label = label or f"Floor({value})"
        kw = {"_target": self._current_target} if self.is_multi_state else {}
        step = StepDef(operation="floor", label=label, args=(value,), kwargs=kw)
        return self._append_step(step)

    def cap(self, value: float, label: str | None = None) -> RollforwardBuilder:
        """Apply cap: av = min(av, value)."""
        label = label or f"Cap({value})"
        kw = {"_target": self._current_target} if self.is_multi_state else {}
        step = StepDef(operation="cap", label=label, args=(value,), kwargs=kw)
        return self._append_step(step)

    def lapse_if_zero(self) -> RollforwardBuilder:
        """Single-state lapse: if av <= 0, zero remaining periods."""
        kw = {"_target": self._current_target} if self.is_multi_state else {}
        step = StepDef(operation="lapse_if_zero", label="LapseIfZero", args=(), kwargs=kw)
        return self._append_step(step)

    def add_if(
        self,
        condition: Any,  # noqa: ANN401
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Conditional add: if condition[t]: av += amount[t]."""
        step = self._make_step(
            "add_if", label, (condition, amount),
            auto_label_prefix="AddIf", auto_label_ref=amount,
        )
        return self._append_step(step)

    def charge_if(
        self,
        condition: Any,  # noqa: ANN401
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Conditional charge: if condition[t]: av *= (1 - rate[t])."""
        step = self._make_step(
            "charge_if", label, (condition, rate),
            auto_label_prefix="ChargeIf", auto_label_ref=rate,
        )
        return self._append_step(step)

    def capture(self, name: str) -> RollforwardBuilder:
        """Snapshot current state value for downstream use or cross-state reference."""
        kw = {"_target": self._current_target} if self.is_multi_state else {}
        step = StepDef(operation="capture", label=f"Capture({name})", args=(name,), kwargs=kw)
        return self._append_step(step)

    # ── Multi-state operations ─────────────────────────────────────

    def ratchet_to(
        self, other_state: str, label: str | None = None,
    ) -> RollforwardBuilder:
        """Ratchet current state to max of self and other: av = max(av, other)."""
        if not self.is_multi_state:
            msg = ".ratchet_to() is only valid in multi-state mode."
            raise ValueError(msg)
        label = label or f"RatchetTo({other_state})"
        kw: dict[str, Any] = {"_target": self._current_target, "other_state": other_state}
        step = StepDef(operation="ratchet_to", label=label, args=(other_state,), kwargs=kw)
        return self._append_step(step)

    def pro_rata_with(
        self,
        capture_ref: str,
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Pro-rata reduction: state *= (1 - amount[t] / capture_ref_value)."""
        label = label or f"ProRata({capture_ref})"
        kw: dict[str, Any] = {"_target": self._current_target, "capture_ref": capture_ref}
        step = StepDef(operation="pro_rata_with", label=label, args=(capture_ref, amount), kwargs=kw)
        return self._append_step(step)

    # ── Cross-state lapse ──────────────────────────────────────────

    def lapse_when(
        self, *, all_non_positive: list[str],
    ) -> RollforwardBuilder:
        """Cross-state lapse: when all named states <= 0, zero all remaining."""
        if not self.is_multi_state:
            msg = ".lapse_when() is only valid in multi-state mode."
            raise ValueError(msg)
        if self._lapse_condition is not None:
            msg = "Only one lapse_when per rollforward is allowed."
            raise ValueError(msg)
        return self._new(
            lapse_condition={"all_non_positive": all_non_positive},
        )

    # ── Composition methods ────────────────────────────────────────

    def insert_before(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Insert a step before the step with the given label."""
        idx = self._find_label(label)
        self._check_unique_label(step.label)
        new_steps = (*self._steps[:idx], step, *self._steps[idx:])
        return self._new(steps=new_steps)

    def insert_after(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Insert a step after the step with the given label."""
        idx = self._find_label(label)
        self._check_unique_label(step.label)
        new_steps = (*self._steps[:idx + 1], step, *self._steps[idx + 1:])
        return self._new(steps=new_steps)

    def remove(self, label: str) -> RollforwardBuilder:
        """Remove the step with the given label."""
        idx = self._find_label(label)
        new_steps = (*self._steps[:idx], *self._steps[idx + 1:])
        return self._new(steps=new_steps)

    def replace(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Replace the step with the given label."""
        idx = self._find_label(label)
        if step.label != label:
            self._check_unique_label(step.label)
        new_steps = (*self._steps[:idx], step, *self._steps[idx + 1:])
        return self._new(steps=new_steps)

    def prepend(self, step: StepDef) -> RollforwardBuilder:
        """Add a step at the beginning."""
        self._check_unique_label(step.label)
        return self._new(steps=(step, *self._steps))

    def append(self, step: StepDef) -> RollforwardBuilder:
        """Add a step at the end."""
        self._check_unique_label(step.label)
        return self._new(steps=(*self._steps, step))
```

Update `__init__.py`:
```python
# bindings/python/gaspatchio_core/rollforward/__init__.py
"""Rollforward API for non-linear account value projections."""

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._step import Step, StepDef

__all__ = ["RollforwardBuilder", "Step", "StepDef"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_builder.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward/ bindings/python/tests/rollforward/
git commit -m "feat(rollforward): add RollforwardBuilder with step methods and label validation"
```

---

### Task 3: Builder Composition Methods

**Files:**
- Create: `bindings/python/tests/rollforward/test_composition.py`
- (Composition methods already implemented in Task 2's `_builder.py`)

Tests verify insert_before/after, remove, replace, prepend, append, and immutability.

- [ ] **Step 1: Write composition tests**

```python
# tests/rollforward/test_composition.py
from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._step import Step


@pytest.fixture
def base_ul() -> RollforwardBuilder:
    return (
        RollforwardBuilder(frame=None, initial="av_init")
        .add("premium", "Premium")
        .charge("admin_rate", "Admin")
        .grow("interest_rate", "Interest")
        .floor(0)
    )


class TestInsertBefore:
    def test_insert_before(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.insert_before("Interest", Step.charge("rider_rate", "Rider"))
        assert b.labels == ("Premium", "Admin", "Rider", "Interest", "Floor(0)")

    def test_insert_before_missing_label(self, base_ul: RollforwardBuilder) -> None:
        with pytest.raises(KeyError, match="No step with label"):
            base_ul.insert_before("Missing", Step.charge("x", "X"))

    def test_insert_before_duplicate_label(self, base_ul: RollforwardBuilder) -> None:
        with pytest.raises(ValueError, match="Duplicate label"):
            base_ul.insert_before("Interest", Step.charge("x", "Premium"))


class TestInsertAfter:
    def test_insert_after(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.insert_after("Admin", Step.charge("rider_rate", "Rider"))
        assert b.labels == ("Premium", "Admin", "Rider", "Interest", "Floor(0)")

    def test_insert_after_last(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.insert_after("Floor(0)", Step.cap(1e6, "MaxAV"))
        assert b.labels[-1] == "MaxAV"


class TestRemove:
    def test_remove(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.remove("Admin")
        assert b.labels == ("Premium", "Interest", "Floor(0)")

    def test_remove_missing(self, base_ul: RollforwardBuilder) -> None:
        with pytest.raises(KeyError, match="No step with label"):
            base_ul.remove("Missing")


class TestReplace:
    def test_replace(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.replace("Admin", Step.subtract("admin_dollar", "Admin ($)"))
        assert b.labels == ("Premium", "Admin ($)", "Interest", "Floor(0)")
        assert b.steps[1].operation == "subtract"

    def test_replace_same_label(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.replace("Admin", Step.charge("new_rate", "Admin"))
        assert b.labels == ("Premium", "Admin", "Interest", "Floor(0)")


class TestPrependAppend:
    def test_prepend(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.prepend(Step.add("bonus", "Sign-on Bonus"))
        assert b.labels[0] == "Sign-on Bonus"

    def test_append(self, base_ul: RollforwardBuilder) -> None:
        b = base_ul.append(Step.charge("surrender_rate", "Surrender"))
        assert b.labels[-1] == "Surrender"


class TestImmutabilityPreserved:
    def test_original_unchanged(self, base_ul: RollforwardBuilder) -> None:
        original_labels = base_ul.labels
        _ = base_ul.insert_before("Interest", Step.charge("x", "X"))
        _ = base_ul.remove("Admin")
        _ = base_ul.append(Step.cap(1e6, "Cap"))
        assert base_ul.labels == original_labels

    def test_multiple_variants_from_same_base(self, base_ul: RollforwardBuilder) -> None:
        v1 = base_ul.insert_before("Interest", Step.charge("rider", "Rider"))
        v2 = base_ul.remove("Admin")
        v3 = base_ul.replace("Interest", Step.grow_capped("idx", floor=0.0, cap=0.12, label="Index"))
        assert len(v1.steps) == 5
        assert len(v2.steps) == 3
        assert len(v3.steps) == 4
        assert len(base_ul.steps) == 4  # unchanged
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_composition.py -v`
Expected: All PASS (composition methods were implemented in Task 2)

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/rollforward/test_composition.py
git commit -m "test(rollforward): add composition method tests"
```

---

### Task 4: Rust Kwargs Types and Module Registration

**Files:**
- Create: `core/src/polars_functions/rollforward.rs`
- Modify: `core/src/polars_functions/mod.rs`
- Modify: `core/src/lib.rs`

Define all Serde-deserializable types that the Rust kernel will receive from Python. No kernel logic yet — just types and a stub function that compiles.

- [ ] **Step 1: Write the Rust types and stub function**

Create `core/src/polars_functions/rollforward.rs`:

```rust
// ABOUTME: Rollforward kernel for non-linear account value projections
// ABOUTME: Step-dispatch inner loop with single-state and multi-state support

use polars::prelude::*;
use serde::Deserialize;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kwargs_deserialization() {
        let json = r#"{
            "states": [{"name": "__default__", "initial_col_index": 0}],
            "steps": [
                {"Add": {"target_index": 0, "input_index": 1, "label": "Premium", "expected_input_index": null}}
            ],
            "track_increments": false,
            "assertion_mode": null,
            "num_captures": 0,
            "lapse_condition": null
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(json).unwrap();
        assert_eq!(kwargs.states.len(), 1);
        assert_eq!(kwargs.steps.len(), 1);
        assert!(!kwargs.track_increments);
    }

    #[test]
    fn test_multi_state_kwargs() {
        let json = r#"{
            "states": [
                {"name": "av", "initial_col_index": 0},
                {"name": "guarantee", "initial_col_index": 1}
            ],
            "steps": [
                {"Add": {"target_index": 0, "input_index": 2, "label": "Premium", "expected_input_index": null}},
                {"RatchetTo": {"target_index": 1, "other_state_index": 0, "label": "GMDB Ratchet"}}
            ],
            "track_increments": true,
            "assertion_mode": null,
            "num_captures": 0,
            "lapse_condition": {"AllNonPositive": {"state_indices": [0, 1]}}
        }"#;
        let kwargs: RollforwardKwargs = serde_json::from_str(json).unwrap();
        assert_eq!(kwargs.states.len(), 2);
        assert_eq!(kwargs.steps.len(), 2);
        assert!(kwargs.track_increments);
        assert!(kwargs.lapse_condition.is_some());
    }
}

/// Top-level kwargs received from Python's `_compile()`.
#[derive(Deserialize)]
pub struct RollforwardKwargs {
    pub states: Vec<StateSpec>,
    pub steps: Vec<StepSpec>,
    pub track_increments: bool,
    pub assertion_mode: Option<AssertionMode>,
    pub num_captures: usize,
    pub lapse_condition: Option<LapseCondition>,
}

#[derive(Deserialize)]
pub enum AssertionMode {
    Flag,
    Warn,
    Error,
}

#[derive(Deserialize)]
pub struct StateSpec {
    pub name: String,
    pub initial_col_index: usize,
}

/// Each variant carries pre-resolved indices (no string lookups in hot loop).
#[derive(Deserialize)]
pub enum StepSpec {
    Add {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Subtract {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Charge {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Grow {
        target_index: usize,
        input_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    GrowCapped {
        target_index: usize,
        input_index: usize,
        rate_floor: f64,
        rate_cap: f64,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    DeductNar {
        target_index: usize,
        rate_index: usize,
        db_index: usize,
        label: Option<String>,
        expected_input_index: Option<usize>,
    },
    Floor {
        target_index: usize,
        value: f64,
        label: Option<String>,
    },
    Cap {
        target_index: usize,
        value: f64,
        label: Option<String>,
    },
    RatchetTo {
        target_index: usize,
        other_state_index: usize,
        label: Option<String>,
    },
    ProRataWith {
        target_index: usize,
        capture_index: usize,
        amount_index: usize,
        label: Option<String>,
    },
    Capture {
        target_index: usize,
        capture_index: usize,
    },
    LapseIfZero {
        target_index: usize,
    },
    AddIf {
        target_index: usize,
        condition_index: usize,
        amount_index: usize,
        label: Option<String>,
    },
    ChargeIf {
        target_index: usize,
        condition_index: usize,
        rate_index: usize,
        label: Option<String>,
    },
}

#[derive(Deserialize)]
pub enum LapseCondition {
    AllNonPositive { state_indices: Vec<usize> },
}

impl StepSpec {
    /// Returns the target state index for this step.
    pub fn target_index(&self) -> usize {
        match self {
            Self::Add { target_index, .. }
            | Self::Subtract { target_index, .. }
            | Self::Charge { target_index, .. }
            | Self::Grow { target_index, .. }
            | Self::GrowCapped { target_index, .. }
            | Self::DeductNar { target_index, .. }
            | Self::Floor { target_index, .. }
            | Self::Cap { target_index, .. }
            | Self::RatchetTo { target_index, .. }
            | Self::ProRataWith { target_index, .. }
            | Self::Capture { target_index, .. }
            | Self::LapseIfZero { target_index }
            | Self::AddIf { target_index, .. }
            | Self::ChargeIf { target_index, .. } => *target_index,
        }
    }

    /// Returns the label for this step, if any.
    pub fn label(&self) -> Option<&str> {
        match self {
            Self::Add { label, .. }
            | Self::Subtract { label, .. }
            | Self::Charge { label, .. }
            | Self::Grow { label, .. }
            | Self::GrowCapped { label, .. }
            | Self::DeductNar { label, .. }
            | Self::Floor { label, .. }
            | Self::Cap { label, .. }
            | Self::RatchetTo { label, .. }
            | Self::ProRataWith { label, .. }
            | Self::AddIf { label, .. }
            | Self::ChargeIf { label, .. } => label.as_deref(),
            Self::Capture { .. } | Self::LapseIfZero { .. } => None,
        }
    }
}

/// Public entry point for the rollforward Polars plugin.
///
/// # Arguments
/// * `inputs` - Series array: initial value columns followed by input columns
///              (premiums, rates, etc.), ordered by `_compile()` index assignment.
/// * `kwargs` - Deserialized `RollforwardKwargs` specifying states, steps, and options.
///
/// # Returns
/// Always returns a Struct column. Fields depend on configuration:
/// - Single-state, no tracking: `Struct { "result": List<Float64> }`
/// - Single-state, with tracking: `Struct { "result": ..., "label1": ..., ... }`
/// - Multi-state: `Struct { "state1": ..., "state2": ..., [increments...] }`
pub fn rollforward(inputs: &[Series], kwargs: &RollforwardKwargs) -> PolarsResult<Series> {
    // TODO: Implement in Task 5
    let _ = (inputs, kwargs);
    Err(PolarsError::ComputeError("rollforward not yet implemented".into()))
}
```

- [ ] **Step 2: Register the module**

In `core/src/polars_functions/mod.rs`, add:
```rust
pub mod rollforward;
pub use rollforward::{rollforward, RollforwardKwargs};
```

In `core/src/lib.rs`, add to the exports:
```rust
pub use polars_functions::RollforwardKwargs;
```

- [ ] **Step 3: Run Rust tests**

Run: `cd core && cargo test`
Expected: `test_kwargs_deserialization` and `test_multi_state_kwargs` PASS. Other existing tests still pass.

Note: You may need to add `serde_json` as a dev-dependency in `core/Cargo.toml`:
```toml
[dev-dependencies]
serde_json = "1.0"
```

- [ ] **Step 4: Commit**

```bash
git add core/src/polars_functions/rollforward.rs core/src/polars_functions/mod.rs core/src/lib.rs core/Cargo.toml
git commit -m "feat(rollforward): add Rust kwargs types and module registration"
```

---

### Task 5: Rust Kernel — Single-State Fast Path (Core Steps)

**Files:**
- Modify: `core/src/polars_functions/rollforward.rs`

Implement the fast-path kernel for single-state rollforward with core steps: Add, Subtract, Charge, Grow, Floor, Cap. Follow `accumulate.rs` patterns for array access and output construction.

- [ ] **Step 1: Write Rust tests for single-state core steps**

Add to the `tests` module in `rollforward.rs`:

```rust
#[test]
fn test_single_state_add_only() {
    // initial=1000, premium=[100, 100, 100]
    // out[0] = 1000 + 100 = 1100
    // out[1] = 1100 + 100 = 1200
    // out[2] = 1200 + 100 = 1300
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let premium = ListChunked::from_iter([Some(Series::new(
        "".into(),
        vec![100.0, 100.0, 100.0],
    ))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::Add {
            target_index: 0,
            input_index: 1,
            label: Some("Premium".to_string()),
            expected_input_index: None,
        }],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let av_list = av.list().unwrap();
    let row0 = av_list.get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - 1100.0).abs() < 1e-10);
    assert!((vals.get(1).unwrap() - 1200.0).abs() < 1e-10);
    assert!((vals.get(2).unwrap() - 1300.0).abs() < 1e-10);
}

#[test]
fn test_single_state_charge_and_grow() {
    // initial=1000, admin_rate=[0.01], interest_rate=[0.05]
    // Step 1: charge: 1000 * (1 - 0.01) = 990
    // Step 2: grow: 990 * (1 + 0.05) = 1039.5
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let admin = ListChunked::from_iter([Some(Series::new("".into(), vec![0.01]))]);
    let interest = ListChunked::from_iter([Some(Series::new("".into(), vec![0.05]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![
            StepSpec::Charge {
                target_index: 0, input_index: 1,
                label: Some("Admin".to_string()), expected_input_index: None,
            },
            StepSpec::Grow {
                target_index: 0, input_index: 2,
                label: Some("Interest".to_string()), expected_input_index: None,
            },
        ],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(
        &[initial, admin.into_series(), interest.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - 1039.5).abs() < 1e-10);
}

#[test]
fn test_floor_clamps_negative() {
    // initial=100, subtract=[150] → -50 → floor(0) → 0
    let initial = Series::new("initial".into(), vec![100.0_f64]);
    let amount = ListChunked::from_iter([Some(Series::new("".into(), vec![150.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![
            StepSpec::Subtract {
                target_index: 0, input_index: 1,
                label: Some("Withdrawal".to_string()), expected_input_index: None,
            },
            StepSpec::Floor { target_index: 0, value: 0.0, label: Some("Floor".to_string()) },
        ],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(&[initial, amount.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    assert_eq!(row0.f64().unwrap().get(0), Some(0.0));
}

#[test]
fn test_multiple_policies() {
    // 2 policies with different initials, same add
    let initial = Series::new("initial".into(), vec![1000.0_f64, 2000.0]);
    let premium = ListChunked::from_iter([
        Some(Series::new("".into(), vec![100.0, 100.0])),
        Some(Series::new("".into(), vec![200.0, 200.0])),
    ]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::Add {
            target_index: 0, input_index: 1,
            label: Some("Premium".to_string()), expected_input_index: None,
        }],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let av_list = av.list().unwrap();

    // Policy 0: 1000+100=1100, 1100+100=1200
    let r0 = av_list.get_as_series(0).unwrap();
    assert!((r0.f64().unwrap().get(0).unwrap() - 1100.0).abs() < 1e-10);
    assert!((r0.f64().unwrap().get(1).unwrap() - 1200.0).abs() < 1e-10);

    // Policy 1: 2000+200=2200, 2200+200=2400
    let r1 = av_list.get_as_series(1).unwrap();
    assert!((r1.f64().unwrap().get(0).unwrap() - 2200.0).abs() < 1e-10);
    assert!((r1.f64().unwrap().get(1).unwrap() - 2400.0).abs() < 1e-10);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && cargo test rollforward`
Expected: FAIL — `rollforward not yet implemented`

- [ ] **Step 3: Implement single-state fast path**

Replace the `rollforward()` stub in `rollforward.rs` with the full implementation. Follow `accumulate.rs` patterns:
1. Extract initial values, cast to Float64
2. Extract all input list columns, rechunk, get contiguous slices
3. Check for nulls → route to fast/slow path
4. Fast path: iterate rows, run step-dispatch inner loop per timestep
5. Build Struct output with `StructChunked::from_series`

Key implementation details:
- Pre-allocate `output_values: Vec<f64>` and `output_offsets: Vec<i64>`
- Use the same offset/values pattern as `accumulate_fast()`
- Step dispatch is a `match` on `StepSpec` variants
- For single-state (states.len() == 1), use a bare `f64 state` variable
- Always return Struct with at least a `"result"` field

Reference: `accumulate.rs:269-395` for the fast-path array access pattern.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && cargo test rollforward`
Expected: All 4 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward.rs
git commit -m "feat(rollforward): implement single-state fast path with core steps"
```

---

### Task 6: Rust Kernel — Advanced Single-State Steps

**Files:**
- Modify: `core/src/polars_functions/rollforward.rs`

Add: GrowCapped, DeductNar, AddIf, ChargeIf, LapseIfZero, Capture.

- [ ] **Step 1: Write Rust tests for advanced steps**

```rust
#[test]
fn test_grow_capped() {
    // initial=1000, rate=[0.15, -0.05, 0.20]
    // floor=0.0, cap=0.12
    // clamped: [0.12, 0.0, 0.12] (note: -0.05 clamped to floor 0.0)
    // t0: 1000 * 1.12 = 1120
    // t1: 1120 * 1.0 = 1120
    // t2: 1120 * 1.12 = 1254.4
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.15, -0.05, 0.20]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::GrowCapped {
            target_index: 0, input_index: 1,
            rate_floor: 0.0, rate_cap: 0.12,
            label: Some("Index Credit".to_string()), expected_input_index: None,
        }],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(&[initial, rate.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - 1120.0).abs() < 1e-10);
    assert!((vals.get(1).unwrap() - 1120.0).abs() < 1e-10);
    assert!((vals.get(2).unwrap() - 1254.4).abs() < 1e-10);
}

#[test]
fn test_deduct_nar() {
    // initial=1000, coi_rate=[0.001], death_benefit=[5000]
    // NAR = max(0, 5000 - 1000) = 4000
    // COI = 0.001 * 4000 = 4.0
    // AV = 1000 - 4 = 996
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let rate = ListChunked::from_iter([Some(Series::new("".into(), vec![0.001]))]);
    let db = ListChunked::from_iter([Some(Series::new("".into(), vec![5000.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::DeductNar {
            target_index: 0, rate_index: 1, db_index: 2,
            label: Some("COI".to_string()), expected_input_index: None,
        }],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(
        &[initial, rate.into_series(), db.into_series()], &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    assert!((row0.f64().unwrap().get(0).unwrap() - 996.0).abs() < 1e-10);
}

#[test]
fn test_lapse_if_zero() {
    // initial=50, subtract=[100, 100]
    // t0: 50 - 100 = -50 → lapse_if_zero fires → remaining = 0
    // t1: 0 (zeroed)
    let initial = Series::new("initial".into(), vec![50.0_f64]);
    let amount = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0, 100.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![
            StepSpec::Subtract {
                target_index: 0, input_index: 1,
                label: Some("Withdrawal".to_string()), expected_input_index: None,
            },
            StepSpec::LapseIfZero { target_index: 0 },
        ],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(&[initial, amount.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - (-50.0)).abs() < 1e-10); // lapse fires AFTER step
    assert_eq!(vals.get(1).unwrap(), 0.0); // zeroed
}

#[test]
fn test_add_if() {
    // initial=1000, condition=[1.0, 0.0, 1.0], amount=[100, 100, 100]
    // t0: condition=1.0 → 1000 + 100 = 1100
    // t1: condition=0.0 → 1100 (no add)
    // t2: condition=1.0 → 1100 + 100 = 1200
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let condition = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 0.0, 1.0]))]);
    let amount = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0, 100.0, 100.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::AddIf {
            target_index: 0, condition_index: 1, amount_index: 2,
            label: Some("Conditional Premium".to_string()),
        }],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(
        &[initial, condition.into_series(), amount.into_series()], &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - 1100.0).abs() < 1e-10);
    assert!((vals.get(1).unwrap() - 1100.0).abs() < 1e-10);
    assert!((vals.get(2).unwrap() - 1200.0).abs() < 1e-10);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && cargo test rollforward`
Expected: New tests FAIL (unimplemented match arms)

- [ ] **Step 3: Implement the match arms**

Add `GrowCapped`, `DeductNar`, `LapseIfZero`, `AddIf`, `ChargeIf`, `Capture` match arms to the step dispatch loop. Key formulas:

- `GrowCapped`: `state *= 1.0 + rate.clamp(rate_floor, rate_cap)`
- `DeductNar`: `let nar = f64::max(0.0, db - state); state -= rate * nar`
- `LapseIfZero`: `if state <= 0.0 { zero remaining periods; break }`
- `AddIf`: `if condition > 0.0 { state += amount }`
- `ChargeIf`: `if condition > 0.0 { state *= 1.0 - rate }`
- `Capture`: `captures[capture_index] = state` (no-op on state value). When `track_increments=True`, also record capture value to a `Capture(<name>)` field in the Struct output. The capture buffer is a per-capture `Vec<f64>` that gets pushed with the captured value at each timestep (for timesteps before the capture executes, push 0.0 or NaN — implementer to decide based on what's most useful for downstream access).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && cargo test rollforward`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward.rs
git commit -m "feat(rollforward): add GrowCapped, DeductNar, AddIf, ChargeIf, LapseIfZero, Capture"
```

---

### Task 7: Rust Kernel — Increment Tracking

**Files:**
- Modify: `core/src/polars_functions/rollforward.rs`

When `track_increments=True`, record `value_after - value_before` for each labeled step. Add these as additional fields in the Struct output.

- [ ] **Step 1: Write Rust tests for increment tracking**

```rust
#[test]
fn test_increment_tracking_single_state() {
    // initial=1000, premium=[100], admin_rate=[0.01], interest=[0.05]
    // After Add: 1100. Increment: 100
    // After Charge: 1100 * 0.99 = 1089. Increment: -11
    // After Grow: 1089 * 1.05 = 1143.45. Increment: 54.45
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0]))]);
    let admin = ListChunked::from_iter([Some(Series::new("".into(), vec![0.01]))]);
    let interest = ListChunked::from_iter([Some(Series::new("".into(), vec![0.05]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![
            StepSpec::Add { target_index: 0, input_index: 1, label: Some("Premium".to_string()), expected_input_index: None },
            StepSpec::Charge { target_index: 0, input_index: 2, label: Some("Admin".to_string()), expected_input_index: None },
            StepSpec::Grow { target_index: 0, input_index: 3, label: Some("Interest".to_string()), expected_input_index: None },
        ],
        track_increments: true,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(
        &[initial, premium.into_series(), admin.into_series(), interest.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();

    // Check result
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    assert!((row0.f64().unwrap().get(0).unwrap() - 1143.45).abs() < 1e-10);

    // Check increments
    let prem_inc = s.field_by_name("Premium").unwrap();
    let prem_row0 = prem_inc.list().unwrap().get_as_series(0).unwrap();
    assert!((prem_row0.f64().unwrap().get(0).unwrap() - 100.0).abs() < 1e-10);

    let admin_inc = s.field_by_name("Admin").unwrap();
    let admin_row0 = admin_inc.list().unwrap().get_as_series(0).unwrap();
    assert!((admin_row0.f64().unwrap().get(0).unwrap() - (-11.0)).abs() < 1e-10);

    let int_inc = s.field_by_name("Interest").unwrap();
    let int_row0 = int_inc.list().unwrap().get_as_series(0).unwrap();
    assert!((int_row0.f64().unwrap().get(0).unwrap() - 54.45).abs() < 1e-10);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && cargo test test_increment_tracking`
Expected: FAIL — Struct missing increment fields

- [ ] **Step 3: Implement increment tracking**

Modify the fast-path inner loop:
1. Before stepping: `let av_before = state;`
2. After stepping: if `track_increments && step.label().is_some()` → `increment_buffers[label_idx].push(state - av_before)`
3. Pre-compute a `label_to_buffer_index` mapping from step labels to buffer indices
4. Build output Struct with "result" field + one field per label

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && cargo test rollforward`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward.rs
git commit -m "feat(rollforward): add increment tracking with Struct output"
```

---

### Task 8: Rust Kernel — Multi-State Support

**Files:**
- Modify: `core/src/polars_functions/rollforward.rs`

When `states.len() > 1`, use `Vec<f64>` for state storage. Add RatchetTo, ProRataWith, cross-state captures, LapseWhen.

- [ ] **Step 1: Write Rust tests for multi-state**

```rust
#[test]
fn test_multi_state_va_gmdb() {
    // Two states: av (idx 0), guarantee (idx 1)
    // initial av=1000, guarantee=1000
    // Steps:
    //   Add premium to av: 1000+100 = 1100
    //   Grow av by fund_return: 1100 * 1.10 = 1210
    //   Ratchet guarantee to av: max(1000, 1210) = 1210
    let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
    let initial_g = Series::new("g_init".into(), vec![1000.0_f64]);
    let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0]))]);
    let fund_ret = ListChunked::from_iter([Some(Series::new("".into(), vec![0.10]))]);

    let kwargs = RollforwardKwargs {
        states: vec![
            StateSpec { name: "av".to_string(), initial_col_index: 0 },
            StateSpec { name: "guarantee".to_string(), initial_col_index: 1 },
        ],
        steps: vec![
            StepSpec::Add { target_index: 0, input_index: 2, label: Some("Premium".to_string()), expected_input_index: None },
            StepSpec::Grow { target_index: 0, input_index: 3, label: Some("Fund Return".to_string()), expected_input_index: None },
            StepSpec::RatchetTo { target_index: 1, other_state_index: 0, label: Some("GMDB Ratchet".to_string()) },
        ],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(
        &[initial_av, initial_g, premium.into_series(), fund_ret.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();

    let av = s.field_by_name("av").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    assert!((row0.f64().unwrap().get(0).unwrap() - 1210.0).abs() < 1e-10);

    let g = s.field_by_name("guarantee").unwrap();
    let row0g = g.list().unwrap().get_as_series(0).unwrap();
    assert!((row0g.f64().unwrap().get(0).unwrap() - 1210.0).abs() < 1e-10);
}

#[test]
fn test_lapse_when_all_non_positive() {
    // av starts at 50, subtract 100 each period. guarantee starts at 50, subtract 100.
    // t0: av = -50, guarantee = -50 → all non-positive → zero remaining
    // t1: av = 0, guarantee = 0
    let initial_av = Series::new("av_init".into(), vec![50.0_f64]);
    let initial_g = Series::new("g_init".into(), vec![50.0_f64]);
    let sub_av = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0, 100.0]))]);
    let sub_g = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0, 100.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![
            StateSpec { name: "av".to_string(), initial_col_index: 0 },
            StateSpec { name: "guarantee".to_string(), initial_col_index: 1 },
        ],
        steps: vec![
            StepSpec::Subtract { target_index: 0, input_index: 2, label: Some("WithdrawAV".to_string()), expected_input_index: None },
            StepSpec::Subtract { target_index: 1, input_index: 3, label: Some("WithdrawG".to_string()), expected_input_index: None },
        ],
        track_increments: false,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: Some(LapseCondition::AllNonPositive { state_indices: vec![0, 1] }),
    };

    let result = rollforward(
        &[initial_av, initial_g, sub_av.into_series(), sub_g.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();

    let av = s.field_by_name("av").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    let vals = row0.f64().unwrap();
    assert!((vals.get(0).unwrap() - (-50.0)).abs() < 1e-10);
    assert_eq!(vals.get(1).unwrap(), 0.0); // zeroed after lapse
}

#[test]
fn test_pro_rata_with_capture() {
    // av=1000, benefit_base=500
    // Step 1: Capture av as "av_pre_wd"
    // Step 2: Subtract withdrawal(200) from av: 1000-200 = 800
    // Step 3: ProRataWith on benefit_base: 500 * (1 - 200/1000) = 500 * 0.8 = 400
    let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
    let initial_bb = Series::new("bb_init".into(), vec![500.0_f64]);
    let withdrawal = ListChunked::from_iter([Some(Series::new("".into(), vec![200.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![
            StateSpec { name: "av".to_string(), initial_col_index: 0 },
            StateSpec { name: "benefit_base".to_string(), initial_col_index: 1 },
        ],
        steps: vec![
            StepSpec::Capture { target_index: 0, capture_index: 0 },
            StepSpec::Subtract { target_index: 0, input_index: 2, label: Some("Withdrawal".to_string()), expected_input_index: None },
            StepSpec::ProRataWith { target_index: 1, capture_index: 0, amount_index: 2, label: Some("ProRata".to_string()) },
        ],
        track_increments: false,
        assertion_mode: None,
        num_captures: 1,
        lapse_condition: None,
    };

    let result = rollforward(
        &[initial_av, initial_bb, withdrawal.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();

    let av = s.field_by_name("av").unwrap();
    assert!((av.list().unwrap().get_as_series(0).unwrap().f64().unwrap().get(0).unwrap() - 800.0).abs() < 1e-10);

    let bb = s.field_by_name("benefit_base").unwrap();
    assert!((bb.list().unwrap().get_as_series(0).unwrap().f64().unwrap().get(0).unwrap() - 400.0).abs() < 1e-10);
}
```

Also add a combined multi-state + tracking test:

```rust
#[test]
fn test_multi_state_with_increment_tracking() {
    // Two states: av, guarantee. Track increments.
    // Verify Struct output has state fields AND increment fields.
    let initial_av = Series::new("av_init".into(), vec![1000.0_f64]);
    let initial_g = Series::new("g_init".into(), vec![1000.0_f64]);
    let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0]))]);
    let fund_ret = ListChunked::from_iter([Some(Series::new("".into(), vec![0.10]))]);

    let kwargs = RollforwardKwargs {
        states: vec![
            StateSpec { name: "av".to_string(), initial_col_index: 0 },
            StateSpec { name: "guarantee".to_string(), initial_col_index: 1 },
        ],
        steps: vec![
            StepSpec::Add { target_index: 0, input_index: 2, label: Some("Premium".to_string()), expected_input_index: None },
            StepSpec::Grow { target_index: 0, input_index: 3, label: Some("Fund Return".to_string()), expected_input_index: None },
            StepSpec::RatchetTo { target_index: 1, other_state_index: 0, label: Some("GMDB Ratchet".to_string()) },
        ],
        track_increments: true,
        assertion_mode: None,
        num_captures: 0,
        lapse_condition: None,
    };

    let result = rollforward(
        &[initial_av, initial_g, premium.into_series(), fund_ret.into_series()],
        &kwargs,
    ).unwrap();
    let s = result.struct_().unwrap();

    // Struct should have: "av", "guarantee", "Premium", "Fund Return", "GMDB Ratchet"
    assert!(s.field_by_name("av").is_ok());
    assert!(s.field_by_name("guarantee").is_ok());
    assert!(s.field_by_name("Premium").is_ok());
    assert!(s.field_by_name("Fund Return").is_ok());
    assert!(s.field_by_name("GMDB Ratchet").is_ok());

    // Verify Premium increment = 100
    let prem_inc = s.field_by_name("Premium").unwrap();
    let prem_val = prem_inc.list().unwrap().get_as_series(0).unwrap();
    assert!((prem_val.f64().unwrap().get(0).unwrap() - 100.0).abs() < 1e-10);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && cargo test rollforward`
Expected: New multi-state tests FAIL

- [ ] **Step 3: Implement multi-state kernel path**

When `states.len() > 1`, change from `f64 state` to `Vec<f64> states`. Each step indexes into `states[target_index]`. At each timestep, push all state values to per-state output buffers. Add LapseWhen check at end of each timestep.

Key changes:
- `let mut states: Vec<f64>` initialized from `initial_values[s.initial_col_index]`
- `let mut captures: Vec<f64> = vec![0.0; kwargs.num_captures]`
- `RatchetTo`: `states[ti] = f64::max(states[ti], states[other_state_index])`
- `ProRataWith`: `if captures[ci] > 0.0 { states[ti] *= 1.0 - inputs[ai][t] / captures[ci] }`
- Output: one `List<Float64>` per state name, plus increments if tracked

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && cargo test rollforward`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward.rs
git commit -m "feat(rollforward): add multi-state support with RatchetTo, ProRataWith, LapseWhen"
```

---

### Task 9: Rust Kernel — Null Handling (Slow Path)

**Files:**
- Modify: `core/src/polars_functions/rollforward.rs`

Follow `accumulate_with_nulls()` pattern: use `amortized_iter()` for rows with null lists or null initial values.

- [ ] **Step 1: Write Rust tests for null handling**

```rust
#[test]
fn test_null_initial_produces_null_output() {
    let initial = Series::new("initial".into(), &[None::<f64>]);
    let premium = ListChunked::from_iter([Some(Series::new("".into(), vec![100.0]))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::Add {
            target_index: 0, input_index: 1,
            label: Some("Premium".to_string()), expected_input_index: None,
        }],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    // All null
    assert_eq!(row0.f64().unwrap().get(0), None);
}

#[test]
fn test_empty_projection() {
    let initial = Series::new("initial".into(), vec![1000.0_f64]);
    let premium = ListChunked::from_iter([Some(Series::new_empty("".into(), &DataType::Float64))]);

    let kwargs = RollforwardKwargs {
        states: vec![StateSpec { name: "__default__".to_string(), initial_col_index: 0 }],
        steps: vec![StepSpec::Add {
            target_index: 0, input_index: 1,
            label: Some("Premium".to_string()), expected_input_index: None,
        }],
        track_increments: false, assertion_mode: None,
        num_captures: 0, lapse_condition: None,
    };

    let result = rollforward(&[initial, premium.into_series()], &kwargs).unwrap();
    let s = result.struct_().unwrap();
    let av = s.field_by_name("result").unwrap();
    let row0 = av.list().unwrap().get_as_series(0).unwrap();
    assert_eq!(row0.len(), 0); // empty projection
}
```

- [ ] **Step 2: Implement slow path**

Add `rollforward_with_nulls()` function following `accumulate_with_nulls()` pattern. Route to it when nulls detected in initial values or inner lists.

- [ ] **Step 3: Run all Rust tests**

Run: `cd core && cargo test rollforward`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add core/src/polars_functions/rollforward.rs
git commit -m "feat(rollforward): add null handling slow path"
```

---

### Task 10: PyO3 Wrapper and Python Plugin Function

**Files:**
- Modify: `bindings/python/src/vector.rs`
- Modify: `bindings/python/gaspatchio_core/functions/vector.py`

Bridge the Rust kernel to Python via Polars plugin registration.

- [ ] **Step 1: Add PyO3 wrapper in vector.rs**

Add to `bindings/python/src/vector.rs`:

```rust
/// Output type for rollforward: always Struct (fields determined at runtime)
fn rollforward_output(_: &[Field]) -> PolarsResult<Field> {
    // Return a placeholder Struct type. The actual fields are determined
    // at runtime by the kernel based on kwargs. Polars handles the
    // runtime type correctly even if the plan-time type is approximate.
    Ok(Field::new(
        PlSmallStr::from_static("rollforward"),
        DataType::Struct(vec![
            Field::new(PlSmallStr::from_static("result"), DataType::List(Box::new(DataType::Float64))),
        ]),
    ))
}

/// PyO3 wrapper for rollforward — non-linear account value projection
#[polars_expr(output_type_func = rollforward_output)]
pub fn rollforward(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::RollforwardKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::rollforward::rollforward(inputs, &kwargs)
}
```

- [ ] **Step 2: Add Python wrapper in vector.py**

Add to `bindings/python/gaspatchio_core/functions/vector.py`:

```python
def rollforward_plugin(args: list[pl.Expr], kwargs: dict[str, Any]) -> pl.Expr:
    """Register the rollforward Polars plugin function.

    Parameters
    ----------
    args
        Polars expressions for initial values and input columns,
        ordered by _compile() index assignment.
    kwargs
        Serialized RollforwardKwargs dict.

    Returns
    -------
    pl.Expr
        Expression that evaluates to a Struct column.
    """
    return register_plugin_function(
        plugin_path=LIB,
        function_name="rollforward",
        args=args,
        kwargs=kwargs,
        is_elementwise=True,
    )
```

- [ ] **Step 3: Build the Rust extension**

Run: `cd bindings/python && maturin develop --release`
Expected: Build succeeds

- [ ] **Step 4: Verify the plugin loads**

Run: `cd bindings/python && uv run python -c "from gaspatchio_core.functions.vector import rollforward_plugin; print('OK')"`
Expected: Prints "OK"

- [ ] **Step 5: Commit**

```bash
git add bindings/python/src/vector.rs bindings/python/gaspatchio_core/functions/vector.py
git commit -m "feat(rollforward): add PyO3 wrapper and Python plugin function"
```

---

### Task 11: Python _compile() — Builder to Plugin Args/Kwargs

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward/_compile.py`
- Create: `bindings/python/tests/rollforward/test_compile.py`

The `_compile()` function resolves column references to positional indices, deduplicates expressions, and produces the `(args, kwargs)` tuple for `register_plugin_function`.

- [ ] **Step 1: Write failing tests for _compile()**

```python
# tests/rollforward/test_compile.py
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._compile import compile_rollforward


class TestCompileSingleState:
    def test_basic_structure(self) -> None:
        builder = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
        )
        args, kwargs = compile_rollforward(builder)

        # args should contain pl.Expr for: av_init, premium, admin_rate
        assert len(args) == 3
        assert kwargs["states"] == [{"name": "__default__", "initial_col_index": 0}]
        assert len(kwargs["steps"]) == 2
        assert kwargs["track_increments"] is False

    def test_column_deduplication(self) -> None:
        builder = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .subtract("premium", "Premium Refund")  # same column
        )
        args, kwargs = compile_rollforward(builder)

        # "premium" should be registered once, both steps reference same index
        assert len(args) == 2  # av_init + premium (deduplicated)
        step0 = kwargs["steps"][0]
        step1 = kwargs["steps"][1]
        assert step0["Add"]["input_index"] == step1["Subtract"]["input_index"]

    def test_deduct_nar_kwargs(self) -> None:
        builder = (
            RollforwardBuilder(frame=None, initial="av_init")
            .deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
        )
        args, kwargs = compile_rollforward(builder)

        step = kwargs["steps"][0]
        assert "DeductNar" in step
        assert step["DeductNar"]["rate_index"] != step["DeductNar"]["db_index"]

    def test_grow_capped_kwargs(self) -> None:
        builder = (
            RollforwardBuilder(frame=None, initial="av_init")
            .grow_capped("index_return", floor=0.0, cap=0.12, label="Index")
        )
        args, kwargs = compile_rollforward(builder)

        step = kwargs["steps"][0]
        assert step["GrowCapped"]["rate_floor"] == 0.0
        assert step["GrowCapped"]["rate_cap"] == 0.12


class TestCompileMultiState:
    def test_multi_state_structure(self) -> None:
        builder = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av").add("premium", "Premium")
            .on("guarantee").ratchet_to("av", "Ratchet")
        )
        args, kwargs = compile_rollforward(builder)

        assert len(kwargs["states"]) == 2
        assert kwargs["states"][0]["name"] == "av"
        assert kwargs["states"][1]["name"] == "guarantee"

        # RatchetTo should have other_state_index pointing to av (0)
        ratchet = kwargs["steps"][1]
        assert ratchet["RatchetTo"]["other_state_index"] == 0

    def test_capture_and_pro_rata(self) -> None:
        builder = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "bb": "bb_init"},
            )
            .on("av").capture("av_pre_wd")
            .on("av").subtract("withdrawal", "Withdrawal")
            .on("bb").pro_rata_with("av_pre_wd", "withdrawal", "ProRata")
        )
        args, kwargs = compile_rollforward(builder)

        assert kwargs["num_captures"] == 1
        # Capture step should have capture_index=0
        cap_step = kwargs["steps"][0]
        assert cap_step["Capture"]["capture_index"] == 0

    def test_lapse_condition(self) -> None:
        builder = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av").add("premium", "Premium")
            .lapse_when(all_non_positive=["av", "guarantee"])
        )
        args, kwargs = compile_rollforward(builder)

        assert kwargs["lapse_condition"] == {
            "AllNonPositive": {"state_indices": [0, 1]},
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_compile.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement compile_rollforward()**

```python
# bindings/python/gaspatchio_core/rollforward/_compile.py
"""Compile a RollforwardBuilder into (args, kwargs) for register_plugin_function."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._builder import RollforwardBuilder


def _to_expr(ref: Any) -> pl.Expr:  # noqa: ANN401
    """Convert a column reference to a Polars expression."""
    if isinstance(ref, str):
        return pl.col(ref)
    if hasattr(ref, "_expr"):
        return ref._expr  # noqa: SLF001
    if hasattr(ref, "name"):
        return pl.col(ref.name)
    if isinstance(ref, pl.Expr):
        return ref
    return pl.lit(ref)


def _ref_key(ref: Any) -> str:  # noqa: ANN401
    """Extract a deduplication key from a column reference."""
    if isinstance(ref, str):
        return ref
    if hasattr(ref, "name"):
        return ref.name
    return str(_to_expr(ref))


def compile_rollforward(
    builder: RollforwardBuilder,
) -> tuple[list[pl.Expr], dict[str, Any]]:
    """Compile builder to (args, kwargs) for register_plugin_function.

    Resolves all column references to positional indices in the args list.
    Deduplicates columns that appear multiple times.
    """
    args: list[pl.Expr] = []
    expr_index: dict[str, int] = {}

    def _register(column_ref: Any) -> int:  # noqa: ANN401
        expr = _to_expr(column_ref)
        key = _ref_key(column_ref)
        if key not in expr_index:
            expr_index[key] = len(args)
            args.append(expr)
        return expr_index[key]

    # ── States ─────────────────────────────────────────────────────
    state_name_to_index: dict[str, int] = {}
    state_specs: list[dict[str, Any]] = []

    if builder._states is not None:
        for i, (name, initial_ref) in enumerate(builder._states.items()):
            state_name_to_index[name] = i
            state_specs.append({
                "name": name,
                "initial_col_index": _register(initial_ref),
            })
    else:
        state_name_to_index["__default__"] = 0
        state_specs.append({
            "name": "__default__",
            "initial_col_index": _register(builder._initial),
        })

    # ── Captures: pre-assign indices ───────────────────────────────
    capture_name_to_index: dict[str, int] = {}
    capture_count = 0
    for step in builder._steps:
        if step.operation == "capture":
            cap_name = step.args[0]
            if cap_name not in capture_name_to_index:
                capture_name_to_index[cap_name] = capture_count
                capture_count += 1

    # ── Steps: resolve all references to indices ───────────────────
    step_specs: list[dict[str, Any]] = []
    for step in builder._steps:
        target = step.kwargs.get("_target", "__default__")
        target_idx = state_name_to_index[target]

        spec: dict[str, Any]
        match step.operation:
            case "add":
                spec = {"Add": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "subtract":
                spec = {"Subtract": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "charge":
                spec = {"Charge": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "grow":
                spec = {"Grow": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "grow_capped":
                spec = {"GrowCapped": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "rate_floor": step.kwargs["floor"],
                    "rate_cap": step.kwargs["cap"],
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "deduct_nar":
                spec = {"DeductNar": {
                    "target_index": target_idx,
                    "rate_index": _register(step.args[0]),
                    "db_index": _register(step.kwargs["death_benefit"]),
                    "label": step.label,
                    "expected_input_index": (
                        _register(step.kwargs["expected"])
                        if "expected" in step.kwargs else None
                    ),
                }}
            case "floor":
                spec = {"Floor": {
                    "target_index": target_idx,
                    "value": float(step.args[0]),
                    "label": step.label,
                }}
            case "cap":
                spec = {"Cap": {
                    "target_index": target_idx,
                    "value": float(step.args[0]),
                    "label": step.label,
                }}
            case "ratchet_to":
                other_state = step.args[0]
                spec = {"RatchetTo": {
                    "target_index": target_idx,
                    "other_state_index": state_name_to_index[other_state],
                    "label": step.label,
                }}
            case "pro_rata_with":
                spec = {"ProRataWith": {
                    "target_index": target_idx,
                    "capture_index": capture_name_to_index[step.args[0]],
                    "amount_index": _register(step.args[1]),
                    "label": step.label,
                }}
            case "capture":
                spec = {"Capture": {
                    "target_index": target_idx,
                    "capture_index": capture_name_to_index[step.args[0]],
                }}
            case "lapse_if_zero":
                spec = {"LapseIfZero": {
                    "target_index": target_idx,
                }}
            case "add_if":
                spec = {"AddIf": {
                    "target_index": target_idx,
                    "condition_index": _register(step.args[0]),
                    "amount_index": _register(step.args[1]),
                    "label": step.label,
                }}
            case "charge_if":
                spec = {"ChargeIf": {
                    "target_index": target_idx,
                    "condition_index": _register(step.args[0]),
                    "rate_index": _register(step.args[1]),
                    "label": step.label,
                }}
            case _:
                msg = f"Unknown operation: {step.operation}"
                raise ValueError(msg)

        step_specs.append(spec)

    # ── Lapse condition ────────────────────────────────────────────
    lapse = None
    if builder._lapse_condition is not None:
        states_list = builder._lapse_condition["all_non_positive"]
        lapse = {
            "AllNonPositive": {
                "state_indices": [state_name_to_index[n] for n in states_list],
            },
        }

    kwargs: dict[str, Any] = {
        "states": state_specs,
        "steps": step_specs,
        "track_increments": builder._track_increments,
        "assertion_mode": None,  # Phase 2
        "num_captures": capture_count,
        "lapse_condition": lapse,
    }

    return args, kwargs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_compile.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward/_compile.py bindings/python/tests/rollforward/test_compile.py
git commit -m "feat(rollforward): implement _compile() for builder-to-kwargs resolution"
```

---

### Task 12: Frame-Level Projection Accessor

**Files:**
- Create: `bindings/python/gaspatchio_core/accessors/projection_frame.py`
- Modify: `bindings/python/gaspatchio_core/accessors/__init__.py`

Register a frame-level `ProjectionFrameAccessor` alongside the existing column-level one. Both use `name="projection"` but different `kind=`.

- [ ] **Step 1: Create the frame-level accessor**

```python
# bindings/python/gaspatchio_core/accessors/projection_frame.py
"""Frame-level projection accessor for rollforward operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame
    from gaspatchio_core.rollforward._builder import RollforwardBuilder


@register_accessor("projection", kind="frame")
class ProjectionFrameAccessor(BaseFrameAccessor):
    """Frame-level projection operations.

    Provides ``af.projection.rollforward()`` for non-linear account
    value projections. Coexists with the column-level projection
    accessor (``af.col.projection.cumulative_survival()``).
    """

    def __init__(self, frame: ActuarialFrame) -> None:
        super().__init__(frame)

    def rollforward(
        self,
        *,
        initial: Any = None,  # noqa: ANN401
        track_increments: bool = False,
        **state_initials: Any,  # noqa: ANN401
    ) -> RollforwardBuilder:
        """Create a rollforward builder for account value projections.

        Parameters
        ----------
        initial
            Initial value column (single-state mode).
        track_increments
            Whether to record per-step dollar increments.
        **state_initials
            Named initial value columns (multi-state mode).
            Example: ``rollforward(av=af.av_init, guarantee=af.g_init)``

        Returns
        -------
        RollforwardBuilder
            An immutable builder for defining rollforward steps.

        Examples
        --------
        Single-state UL rollforward:

        ```python
        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
            .floor(0)
        )
        ```
        """
        from gaspatchio_core.rollforward._builder import RollforwardBuilder  # noqa: PLC0415

        if initial is not None and state_initials:
            msg = "Cannot mix 'initial' with named state kwargs."
            raise ValueError(msg)

        if state_initials:
            return RollforwardBuilder(
                frame=self._frame,
                states=state_initials,
                track_increments=track_increments,
            )
        if initial is not None:
            return RollforwardBuilder(
                frame=self._frame,
                initial=initial,
                track_increments=track_increments,
            )
        msg = "Must provide either 'initial' (single-state) or named state kwargs (multi-state)."
        raise ValueError(msg)
```

- [ ] **Step 2: Register the import**

Add to `bindings/python/gaspatchio_core/accessors/__init__.py`:
```python
from gaspatchio_core.accessors import projection_frame  # noqa: F401
```

- [ ] **Step 3: Verify accessor resolves**

The `ActuarialFrame.__getattr__` must route `af.projection` to the frame-level accessor when called on the frame itself. Check how the existing accessor dispatch works in `base.py` and ensure frame-level accessors are resolved.

Run: `cd bindings/python && uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'av_init': [1000.0], 'premium': [[100.0]]})
b = af.projection.rollforward(initial=af.av_init)
print(type(b).__name__)
"`
Expected: Prints "RollforwardBuilder"

Note: This step may require modifying `ActuarialFrame.__getattr__` to check for frame-level accessors. If `__getattr__` currently only checks column-level, add frame-level lookup:

In `base.py`, find the `__getattr__` method and add frame-level accessor resolution. The pattern should be:
1. Check if `name` is a registered frame-level accessor → return `accessor_cls(self)`
2. Otherwise, fall through to existing column proxy behavior

- [ ] **Step 4: Add top-level re-export**

Add to `bindings/python/gaspatchio_core/__init__.py`:
```python
from gaspatchio_core.rollforward import RollforwardBuilder, Step, StepDef
```

And add to `__all__`:
```python
"RollforwardBuilder", "Step", "StepDef"
```

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/accessors/projection_frame.py bindings/python/gaspatchio_core/accessors/__init__.py bindings/python/gaspatchio_core/__init__.py
git commit -m "feat(rollforward): add frame-level projection accessor for af.projection.rollforward()"
```

---

### Task 13: ActuarialFrame __setitem__ Integration

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`

When `af.av = builder`, detect `RollforwardBuilder`, call `_compile()` + `rollforward_plugin()`, store the Struct as a hidden column, and extract the result field as the user-facing column.

- [ ] **Step 1: Modify __setitem__ to handle RollforwardBuilder**

In `base.py`, at the top of `__setitem__` (around line 266), add detection:

```python
# Inside __setitem__, before the existing try block:
from gaspatchio_core.rollforward._builder import RollforwardBuilder  # noqa: PLC0415

if isinstance(value, RollforwardBuilder):
    self._assign_rollforward(key, value)
    return
```

Then add the new method:

```python
def _assign_rollforward(self, key: str, builder: RollforwardBuilder) -> None:
    """Compile and assign a rollforward builder as a lazy expression."""
    from gaspatchio_core.rollforward._compile import compile_rollforward  # noqa: PLC0415
    from gaspatchio_core.functions.vector import rollforward_plugin  # noqa: PLC0415

    args, kwargs = compile_rollforward(builder)
    struct_expr = rollforward_plugin(args, kwargs)

    # Store the Struct as a hidden column
    hidden_name = f"__rollforward_{key}"
    self._df = self._df.with_columns(struct_expr.alias(hidden_name))

    # Extract the result field as the user-facing column
    if builder.is_multi_state:
        # Multi-state: don't auto-assign — user accesses via rf["av"]
        # Store the builder reference for later field extraction
        # NOTE: Use object.__setattr__ to bypass ActuarialFrame's __setattr__ guard
        if not hasattr(self, "_rollforward_builders"):
            object.__setattr__(self, "_rollforward_builders", {})
        self._rollforward_builders[key] = (builder, hidden_name)
    else:
        # Single-state: extract "result" field
        result_expr = pl.col(hidden_name).struct.field("result")
        self._df = self._df.with_columns(result_expr.alias(key))

    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()
```

- [ ] **Step 2: Modify collect() to strip hidden columns**

In the `collect()` method (around line 365), before the final `final_df.collect()`, add:

```python
# Strip hidden rollforward columns before collecting
columns_to_drop = [c for c in final_df.columns if c.startswith("__rollforward_")]
if columns_to_drop:
    final_df = final_df.drop(columns_to_drop)
```

- [ ] **Step 3: Write a basic end-to-end test**

```python
# tests/rollforward/test_kernel_single.py (initial test)
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def test_single_state_add_e2e() -> None:
    """End-to-end: single add step through full pipeline."""
    af = ActuarialFrame({
        "av_init": [1000.0, 2000.0],
        "premium": [[100.0, 100.0, 100.0], [200.0, 200.0, 200.0]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init)
        .add(af.premium, "Premium")
    )
    result = af.collect()

    av = result["av"].to_list()
    assert len(av) == 2
    # Policy 0: 1000+100=1100, 1100+100=1200, 1200+100=1300
    assert abs(av[0][0] - 1100.0) < 1e-10
    assert abs(av[0][1] - 1200.0) < 1e-10
    assert abs(av[0][2] - 1300.0) < 1e-10
    # Policy 1: 2000+200=2200, ...
    assert abs(av[1][0] - 2200.0) < 1e-10

    # Hidden columns should be stripped
    assert "__rollforward_av" not in result.columns
```

- [ ] **Step 4: Build and run tests**

Run: `cd bindings/python && maturin develop --release && uv run pytest tests/rollforward/test_kernel_single.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/base.py bindings/python/tests/rollforward/test_kernel_single.py
git commit -m "feat(rollforward): integrate builder with ActuarialFrame __setitem__ and collect()"
```

---

### Task 14: Increment and Capture Access

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward/_builder.py` (or add to frame/base.py)
- Create: `bindings/python/tests/rollforward/test_increments.py`

Implement `af.av.increments["COI"]` and `af.av.captures["av_after_premium"]` as lazy Struct field extractions.

- [ ] **Step 1: Write failing tests**

```python
# tests/rollforward/test_increments.py
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def test_increment_access() -> None:
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "admin_rate": [[0.01]],
        "interest_rate": [[0.05]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .charge(af.admin_rate, "Admin")
        .grow(af.interest_rate, "Interest")
    )

    # Extract increments
    af.premium_inc = af.av.increments["Premium"]
    af.admin_inc = af.av.increments["Admin"]
    af.interest_inc = af.av.increments["Interest"]

    result = af.collect()

    # Premium increment should be exactly 100
    assert abs(result["premium_inc"].to_list()[0][0] - 100.0) < 1e-10

    # Admin increment should be negative (charge)
    assert result["admin_inc"].to_list()[0][0] < 0

    # Interest increment should be positive (growth)
    assert result["interest_inc"].to_list()[0][0] > 0


def test_capture_access() -> None:
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "coi_rate": [[0.001]],
        "sum_assured": [[5000.0]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .capture("av_after_premium")
        .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    )

    af.av_post_prem = af.av.captures["av_after_premium"]
    result = af.collect()

    # Capture should be 1000 + 100 = 1100
    assert abs(result["av_post_prem"].to_list()[0][0] - 1100.0) < 1e-10
```

- [ ] **Step 2: Implement increment/capture access**

The approach: When `track_increments=True`, the hidden `__rollforward_*` Struct column has fields for each labeled step. The `.increments` and `.captures` properties on a `ColumnProxy` need to extract fields from this Struct.

Options:
- A: Add `increments` and `captures` properties to `ColumnProxy` that check for the hidden Struct column
- B: Return a special proxy from `__setitem__` that wraps the hidden column name

Recommended: Option A — add properties to `ColumnProxy`. When accessed, they look up the hidden `__rollforward_<column_name>` column and return a dict-like accessor that extracts struct fields.

Implementation sketch — add to `ColumnProxy`:
```python
@property
def increments(self) -> _StructFieldAccessor:
    hidden = f"__rollforward_{self.name}"
    return _StructFieldAccessor(self._parent, hidden, prefix="")

@property
def captures(self) -> _StructFieldAccessor:
    hidden = f"__rollforward_{self.name}"
    return _StructFieldAccessor(self._parent, hidden, prefix="Capture(", suffix=")")
```

Where `_StructFieldAccessor.__getitem__` returns an `ExpressionProxy` wrapping `pl.col(hidden).struct.field(name)`.

- [ ] **Step 3: Run tests**

Run: `cd bindings/python && maturin develop --release && uv run pytest tests/rollforward/test_increments.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/column/column_proxy.py bindings/python/tests/rollforward/test_increments.py
git commit -m "feat(rollforward): add .increments and .captures lazy struct field access"
```

---

### Task 15: Multi-State Python Integration

**Files:**
- Create: `bindings/python/tests/rollforward/test_kernel_multi.py`
- Modify: `bindings/python/gaspatchio_core/frame/base.py` (if needed for multi-state __getitem__)

Multi-state rollforward returns a builder; accessing `rf["av"]` extracts the state from the Struct. Assignment via `af.av = rf["av"]` extracts lazily.

- [ ] **Step 1: Write failing tests**

```python
# tests/rollforward/test_kernel_multi.py
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def test_multi_state_va_gmdb() -> None:
    af = ActuarialFrame({
        "av_init": [1000.0],
        "g_init": [1000.0],
        "premium": [[100.0, 100.0]],
        "fund_return": [[0.10, -0.05]],
        "roll_up_rate": [[0.03, 0.03]],
    })

    rf = (
        af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
        .on("av")
        .add(af.premium, "Premium")
        .grow(af.fund_return, "Fund Return")
        .floor(0)
        .on("guarantee")
        .ratchet_to("av", "GMDB Ratchet")
        .grow(af.roll_up_rate, "Roll-up")
        .lapse_when(all_non_positive=["av", "guarantee"])
    )

    af.av = rf["av"]
    af.guarantee = rf["guarantee"]

    result = af.collect()

    av = result["av"].to_list()[0]
    g = result["guarantee"].to_list()[0]

    # t0: av = (1000+100)*1.10 = 1210, floor(0)=1210
    #     guarantee = max(1000, 1210)=1210 * 1.03 = 1246.3
    assert abs(av[0] - 1210.0) < 1e-10
    assert abs(g[0] - 1246.3) < 1e-10


def test_multi_state_pro_rata_gmwb() -> None:
    af = ActuarialFrame({
        "av_init": [1000.0],
        "bb_init": [500.0],
        "withdrawal": [[200.0]],
        "fund_return": [[0.05]],
    })

    rf = (
        af.projection.rollforward(av=af.av_init, benefit_base=af.bb_init)
        .on("av")
        .capture("av_pre_wd")
        .subtract(af.withdrawal, "Withdrawal")
        .on("benefit_base")
        .pro_rata_with("av_pre_wd", af.withdrawal, "ProRata Reduction")
        .on("av")
        .grow(af.fund_return, "Fund Return")
    )

    af.av = rf["av"]
    af.bb = rf["benefit_base"]

    result = af.collect()
    av = result["av"].to_list()[0]
    bb = result["bb"].to_list()[0]

    # t0: capture av=1000
    #     av = 1000 - 200 = 800
    #     bb = 500 * (1 - 200/1000) = 500 * 0.8 = 400
    #     av = 800 * 1.05 = 840
    assert abs(av[0] - 840.0) < 1e-10
    assert abs(bb[0] - 400.0) < 1e-10
```

- [ ] **Step 2: Implement RollforwardStateProxy and rf["state_name"] accessor**

Add to `bindings/python/gaspatchio_core/rollforward/_builder.py`:

```python
class RollforwardStateProxy:
    """Proxy for extracting a single state from a multi-state rollforward.

    Created by RollforwardBuilder.__getitem__. When assigned to an
    ActuarialFrame column, triggers compilation and state field extraction.
    """

    __slots__ = ("_builder", "_state_name", "_compiled")

    def __init__(self, builder: RollforwardBuilder, state_name: str) -> None:
        self._builder = builder
        self._state_name = state_name
        self._compiled: tuple[list[pl.Expr], dict[str, Any]] | None = None
```

Add `__getitem__` to `RollforwardBuilder`:

```python
def __getitem__(self, state_name: str) -> RollforwardStateProxy:
    """Extract a single state from a multi-state rollforward."""
    if not self.is_multi_state:
        msg = "Indexing with [] is only valid for multi-state rollforwards."
        raise TypeError(msg)
    if state_name not in self._states:
        msg = f"Unknown state {state_name!r}. Available: {list(self._states)}"
        raise KeyError(msg)
    return RollforwardStateProxy(self, state_name)
```

Add to `ActuarialFrame.__setitem__` (at the top, alongside the RollforwardBuilder check):

```python
from gaspatchio_core.rollforward._builder import RollforwardStateProxy  # noqa: PLC0415

if isinstance(value, RollforwardStateProxy):
    self._assign_rollforward_state(key, value)
    return
```

Then add the new method to `ActuarialFrame`:

```python
def _assign_rollforward_state(self, key: str, proxy: RollforwardStateProxy) -> None:
    """Compile a multi-state rollforward and extract one state field."""
    from gaspatchio_core.rollforward._compile import compile_rollforward  # noqa: PLC0415
    from gaspatchio_core.functions.vector import rollforward_plugin  # noqa: PLC0415

    builder = proxy._builder  # noqa: SLF001
    state_name = proxy._state_name  # noqa: SLF001

    # Use a shared hidden column name keyed by builder identity
    hidden_name = f"__rollforward_{id(builder)}"

    # Compile once — check if this builder's hidden column already exists
    if hidden_name not in self._df.columns:
        args, kwargs = compile_rollforward(builder)
        struct_expr = rollforward_plugin(args, kwargs)
        self._df = self._df.with_columns(struct_expr.alias(hidden_name))

    # Extract the named state field
    result_expr = pl.col(hidden_name).struct.field(state_name)
    self._df = self._df.with_columns(result_expr.alias(key))

    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()
```

- [ ] **Step 3: Run tests**

Run: `cd bindings/python && maturin develop --release && uv run pytest tests/rollforward/test_kernel_multi.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward/ bindings/python/gaspatchio_core/frame/base.py bindings/python/tests/rollforward/test_kernel_multi.py
git commit -m "feat(rollforward): add multi-state Python integration with rf[state] accessor"
```

---

### Task 16: explain() and fingerprint()

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward/_explain.py`
- Create: `bindings/python/tests/rollforward/test_explain.py`
- Modify: `bindings/python/gaspatchio_core/rollforward/_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/rollforward/test_explain.py
from __future__ import annotations

from gaspatchio_core.rollforward._builder import RollforwardBuilder


class TestExplain:
    def test_explain_basic(self) -> None:
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
            .grow("interest_rate", "Interest")
            .floor(0)
        )
        output = b.explain()
        assert "Premium" in output
        assert "Admin" in output
        assert "Interest" in output
        assert "Floor" in output
        assert "av[t]" in output  # formula column

    def test_explain_multi_state(self) -> None:
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av").add("premium", "Premium")
            .on("guarantee").ratchet_to("av", "Ratchet")
        )
        output = b.explain()
        assert "av" in output
        assert "guarantee" in output


class TestCanonical:
    def test_canonical_dict(self) -> None:
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .grow("interest_rate", "Interest")
        )
        canon = b.canonical()
        assert isinstance(canon, dict)
        assert "steps" in canon
        assert len(canon["steps"]) == 2

    def test_canonical_excludes_column_names_and_labels(self) -> None:
        b1 = RollforwardBuilder(frame=None, initial="av_init").add("premium", "P")
        b2 = RollforwardBuilder(frame=None, initial="av_init_other").add("gross_prem", "Q")
        # Same structure, different column names AND labels → same canonical form
        assert b1.canonical()["steps"] == b2.canonical()["steps"]


class TestFingerprint:
    def test_fingerprint_format(self) -> None:
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
        )
        fp = b.fingerprint()
        assert fp.startswith("sha256:")
        assert len(fp) == 7 + 64  # "sha256:" + 64 hex chars

    def test_fingerprint_deterministic(self) -> None:
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "A").grow("b", "B")
        b2 = RollforwardBuilder(frame=None, initial="y").add("c", "A").grow("d", "B")
        assert b1.fingerprint() == b2.fingerprint()

    def test_fingerprint_changes_with_steps(self) -> None:
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "A")
        b2 = RollforwardBuilder(frame=None, initial="x").add("a", "A").grow("b", "B")
        assert b1.fingerprint() != b2.fingerprint()
```

- [ ] **Step 2: Implement explain, canonical, fingerprint**

```python
# bindings/python/gaspatchio_core/rollforward/_explain.py
"""Explain, canonical form, and fingerprint for rollforward builders."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from gaspatchio_core.rollforward._step import _col_name

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._builder import RollforwardBuilder

# Formula templates per operation
_FORMULAS: dict[str, str] = {
    "add": "av[t] = av[t] + {col}[t]",
    "subtract": "av[t] = av[t] - {col}[t]",
    "charge": "av[t] = av[t] * (1 - {col}[t])",
    "grow": "av[t] = av[t] * (1 + {col}[t])",
    "grow_capped": "av[t] = av[t] * (1 + clamp({col}[t], {floor}, {cap}))",
    "deduct_nar": "av[t] = av[t] - {col}[t] * max(0, {db}[t] - av[t])",
    "floor": "av[t] = max(av[t], {value})",
    "cap": "av[t] = min(av[t], {value})",
    "ratchet_to": "av[t] = max(av[t], {other}[t])",
    "pro_rata_with": "av[t] = av[t] * (1 - {amount}[t] / {ref})",
    "capture": "(capture {name})",
    "lapse_if_zero": "if av[t] <= 0: zero remaining",
    "add_if": "if {cond}[t]: av[t] += {col}[t]",
    "charge_if": "if {cond}[t]: av[t] *= (1 - {col}[t])",
}


def _step_formula(step) -> str:  # noqa: ANN001
    """Generate the formula string for a step."""
    op = step.operation
    template = _FORMULAS.get(op, op)
    col = _col_name(step.args[0]) if step.args else ""
    match op:
        case "grow_capped":
            return template.format(
                col=col, floor=step.kwargs.get("floor", "?"), cap=step.kwargs.get("cap", "?"),
            )
        case "deduct_nar":
            return template.format(col=col, db=_col_name(step.kwargs.get("death_benefit", "?")))
        case "floor" | "cap":
            return template.format(value=step.args[0])
        case "ratchet_to":
            return template.format(other=step.args[0])
        case "pro_rata_with":
            return template.format(ref=step.args[0], amount=_col_name(step.args[1]))
        case "capture":
            return template.format(name=step.args[0])
        case "add_if" | "charge_if":
            return template.format(cond=_col_name(step.args[0]), col=_col_name(step.args[1]))
        case _:
            return template.format(col=col)


def explain(builder: RollforwardBuilder) -> str:
    """Generate a human-readable formula table for the rollforward."""
    lines = []
    num_steps = len(builder.steps)
    initial_name = (
        _col_name(builder._initial)
        if builder._initial is not None
        else ", ".join(builder._states or {})
    )
    lines.append(f"Rollforward: initial={initial_name}, {num_steps} steps")
    lines.append("")
    lines.append(f"  {'Step':<6}{'Operation':<30}{'Label':<25}{'Formula'}")
    lines.append(f"  {'────':<6}{'─' * 28:<30}{'─' * 23:<25}{'─' * 40}")

    for i, step in enumerate(builder.steps, 1):
        op_display = step.operation
        if step.args:
            op_display = f"{step.operation.title().replace('_', '')}({_col_name(step.args[0])})"
        formula = _step_formula(step)
        target = step.kwargs.get("_target", "")
        if target and target != "__default__":
            formula = formula.replace("av[t]", f"{target}[t]")
        lines.append(f"  {i:<6}{op_display:<30}{step.label:<25}{formula}")

    return "\n".join(lines)


def canonical(builder: RollforwardBuilder) -> dict[str, Any]:
    """Generate the canonical structural form.

    Excludes column names, labels, and input indices (per spec Section 15).
    Includes only operation type, structural parameters, and step ordering.
    """
    steps = []
    for step in builder.steps:
        entry: dict[str, Any] = {
            "operation": step.operation,
        }
        # Include ONLY structural kwargs (floor, cap, value) — NOT column refs or labels
        for k, v in step.kwargs.items():
            if k.startswith("_"):
                continue
            if k in ("death_benefit", "capture_ref", "expected"):
                continue  # column references
            if isinstance(v, (int, float, bool)):
                entry[k] = v
            elif isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
                entry[k] = v  # breakpoints/rates for tiered ops
        steps.append(entry)

    return {
        "num_states": len(builder._states) if builder._states else 1,
        "steps": steps,
        "track_increments": builder._track_increments,
    }


def fingerprint(builder: RollforwardBuilder) -> str:
    """Compute a SHA-256 fingerprint of the canonical form."""
    canon = canonical(builder)
    canonical_json = json.dumps(canon, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode()).hexdigest()
    return f"sha256:{digest}"
```

Add methods to `RollforwardBuilder`:
```python
def explain(self) -> str:
    from gaspatchio_core.rollforward._explain import explain as _explain
    return _explain(self)

def canonical(self) -> dict[str, Any]:
    from gaspatchio_core.rollforward._explain import canonical as _canonical
    return _canonical(self)

def fingerprint(self) -> str:
    from gaspatchio_core.rollforward._explain import fingerprint as _fingerprint
    return _fingerprint(self)
```

- [ ] **Step 3: Run tests**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_explain.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward/_explain.py bindings/python/gaspatchio_core/rollforward/_builder.py bindings/python/tests/rollforward/test_explain.py
git commit -m "feat(rollforward): add explain(), canonical(), and fingerprint()"
```

---

### Task 17: End-to-End Integration Tests

**Files:**
- Create: `bindings/python/tests/rollforward/test_integration.py`

Full product rollforwards testing the complete pipeline from builder → compile → Rust kernel → result extraction.

- [ ] **Step 1: Write integration tests**

```python
# tests/rollforward/test_integration.py
from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward import Step


class TestULRollforward:
    """Full UL product: add, deduct_nar, charge, grow, floor."""

    def test_ul_basic(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0, 100.0]],
            "coi_rate": [[0.001, 0.001]],
            "sum_assured": [[5000.0, 5000.0]],
            "admin_rate": [[0.01, 0.01]],
            "interest_rate": [[0.05, 0.05]],
        })

        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
            .floor(0)
        )

        result = af.collect()
        av = result["av"].to_list()[0]

        # Verify each period manually
        # t0: start=1000
        #   +premium: 1100
        #   -COI: 1100 - 0.001 * max(0, 5000-1100) = 1100 - 3.9 = 1096.1
        #   *charge: 1096.1 * 0.99 = 1085.139
        #   *grow: 1085.139 * 1.05 = 1139.39595
        #   floor: no-op
        assert abs(av[0] - 1139.39595) < 1e-4


class TestCompositionVariants:
    def test_ul_with_rider(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "admin_rate": [[0.01]],
            "interest_rate": [[0.05]],
            "rider_rate": [[0.005]],
        })

        base = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
            .floor(0)
        )

        with_rider = base.insert_before(
            "Interest", Step.charge(af.rider_rate, "Rider Fee"),
        )

        af.av_base = base
        af.av_rider = with_rider

        result = af.collect()

        # Base: (1000+100)*0.99*1.05 = 1089*1.05 = 1143.45
        # Rider: (1000+100)*0.99*0.995*1.05 = 1089*0.995*1.05 = 1137.63...
        assert result["av_base"].to_list()[0][0] > result["av_rider"].to_list()[0][0]


class TestIncrementReconciliation:
    def test_increments_sum_to_total_change(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "admin_rate": [[0.01]],
            "interest_rate": [[0.05]],
        })

        af.av = (
            af.projection.rollforward(initial=af.av_init, track_increments=True)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
        )

        af.prem_inc = af.av.increments["Premium"]
        af.admin_inc = af.av.increments["Admin"]
        af.int_inc = af.av.increments["Interest"]

        result = af.collect()

        av_final = result["av"].to_list()[0][0]
        prem = result["prem_inc"].to_list()[0][0]
        admin = result["admin_inc"].to_list()[0][0]
        interest = result["int_inc"].to_list()[0][0]

        # Increments should sum to total change from initial
        total_change = av_final - 1000.0
        increment_sum = prem + admin + interest
        assert abs(total_change - increment_sum) < 1e-10


class TestExplainOutput:
    def test_explain_prints(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
        })
        b = af.projection.rollforward(initial=af.av_init).add(af.premium, "Premium")
        output = b.explain()
        assert "Rollforward:" in output
        assert "Premium" in output


class TestFingerprintStability:
    def test_same_structure_same_fingerprint(self) -> None:
        af1 = ActuarialFrame({"a": [1.0], "b": [[1.0]]})
        af2 = ActuarialFrame({"x": [2.0], "y": [[2.0]]})

        b1 = af1.projection.rollforward(initial=af1.a).add(af1.b, "P")
        b2 = af2.projection.rollforward(initial=af2.x).add(af2.y, "P")

        assert b1.fingerprint() == b2.fingerprint()
```

- [ ] **Step 2: Build and run all tests**

Run: `cd bindings/python && maturin develop --release && uv run pytest tests/rollforward/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/rollforward/test_integration.py
git commit -m "test(rollforward): add end-to-end integration tests for UL, composition, increments"
```

---

### Task 18: Full Build and Verification

**Files:** None (verification only)

Run the complete test suite to ensure nothing is broken.

- [ ] **Step 1: Run Rust tests**

Run: `cd core && cargo test`
Expected: All tests PASS (existing + new rollforward tests)

- [ ] **Step 2: Build Python extension**

Run: `cd bindings/python && maturin develop --release`
Expected: Build succeeds

- [ ] **Step 3: Run full Python test suite**

Run: `cd bindings/python && uv run pytest -v`
Expected: All tests PASS (existing + new rollforward tests)

- [ ] **Step 4: Run linting**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/rollforward/`
Expected: No errors

- [ ] **Step 5: Commit any fixes and tag**

```bash
git add -A
git commit -m "chore(rollforward): fix any lint/test issues from final verification"
```

---

## Implementation Notes

### Output Type Strategy

The Rust kernel **always** returns a Struct column, even for single-state no-tracking mode (`Struct { "result": List<Float64> }`). This simplifies the PyO3 output type function (always Struct) and keeps a single code path. The overhead of the Struct wrapper is negligible (pointer indirection only). Python always extracts the field it needs.

### Parallel Development

Tasks 1-3 (Python builder) and Tasks 4-9 (Rust kernel) have no dependencies on each other and **can be developed in parallel** by separate agents or in separate worktrees. They converge at Task 10-11 (PyO3 wrapper + _compile + frame integration).

### Key Patterns to Follow

- **accumulate.rs** (lines 269-395): Fast-path array access pattern with offsets, contiguous slices, and pre-allocated output buffers
- **vector.rs** (lines 78-81): PyO3 wrapper with `#[polars_expr]` and kwargs
- **vector.py** (lines 181-186): `register_plugin_function` call pattern
- **registry.py** (lines 15-53): `register_accessor` with `kind="frame"` support
- **base.py** (lines 266-309): `__setitem__` with `_convert_to_expr` pattern

### Phase 2 Hooks

The implementation leaves explicit hooks for Phase 2 features:
- `assertion_mode: Option<AssertionMode>` in kwargs (always `None` in Phase 1)
- `expected_input_index: Option<usize>` on rate/amount steps (always `None` in Phase 1)
- `RollforwardTemplate` can be added later without changing the builder or kernel
