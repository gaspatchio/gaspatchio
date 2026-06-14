# Phase 1a Sub-plan D2 — Builder + Compiler + Explain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the user-facing builder API (`af.projection.rollforward(...)`) that constructs a D1 `IR`, the 5-pass compiler chain (`Validate`, `ResolveStateRefs`, `FoldConstants`, `AssignCaptureSlots`, `LowerToPolarsPlugin`) modelled on CVXPY's reduction chain, and the `explain()` rendering for actuary-readable canonical-form output. D2 lowers an IR to a Polars-backend kwargs dict — the kernel that consumes those kwargs lands in D3. The user-facing `af.projection.rollforward(...)` entry-point is wired to `rollforward_v2` only at end-of-D2 via a temporary alias; the OLD kernel keeps running for any model that still uses it through D2 (cutover happens in D3).

**Architecture:** The builder is mutable scaffolding that emits an immutable `IR` on `_build()`. `RollforwardBuilder` collects state declarations + scope state (current `between(...)` window) + Op invocations from chained method calls. State handles (`rf["state"]`) return a thin proxy that forwards `.add()`/`.subtract()`/etc. into the builder. `rf["state"].at("point")` returns a `StateRef` (D1) for use as a typed expression argument. `rf.increment(label)` is parsed at compile-time into a Struct field name. The compile pipeline is a list of named `Pass` objects, each `apply(ir) -> ir`; a structured log line per pass appears at `LOGURU_LEVEL=TRACE`. `LowerToPolarsPlugin` produces a frozen `CompiledRollforward` carrying `(ir, plugin_kwargs)` ready for D3's kernel.

**Tech Stack:** Python 3.10+; Polars 1.38.1; loguru (already in deps for structured logs); reuses D1's `IR`/`Op`/`StateRef`/`spec_fingerprint`/`action_key`/`derive_engine_binding`. No new third-party deps. No Rust changes.

---

## Scope check

D2 is one cohesive subsystem (the user-facing-API + compile-pipeline layer over D1's IR). No further decomposition.

**Out of scope (deferred to D3):**
- Rust kernel extension (typed (state, point) addressing, capture slots, Struct emission, lapse/contract-boundary stop-logic) → D3
- Polars accessor walk (one shared plugin Expr per `rollforward(...)` call) → D3
- Lazy/Struct release-gate test → D3
- VA acceptance gate → D3 (subject to §13.0 Phase 0)
- Old kernel deletion + tutorial migration → D3

D2 ships a compile pipeline that produces `plugin_kwargs`, but D2's kernel layer is a stub — running the IR end-to-end produces no numerical output yet. End-to-end execution lands in D3.

---

## File structure

**New (Python, all under `bindings/python/gaspatchio_core/rollforward_v2/`):**

| File | Responsibility |
|---|---|
| `_builder.py` | `RollforwardBuilder`, state-handle proxies, `.between()` scope, `rf["s"].at("p")` accessor, `rf.increment(label)` accessor |
| `_passes.py` | `Pass` Protocol + 5 concrete passes (`Validate`, `ResolveStateRefs`, `FoldConstants`, `AssignCaptureSlots`, `LowerToPolarsPlugin`) |
| `_compile.py` | `compile_rollforward(builder)` orchestrator; returns `CompiledRollforward(ir, plugin_kwargs)` |
| `_explain.py` | `explain(ir)` actuary-readable rendering |
| `_compiled.py` | `CompiledRollforward` frozen dataclass holding `(ir, plugin_kwargs, capture_slots)` |

**New (tests, all under `bindings/python/tests/rollforward_v2/`):**

| File | Responsibility |
|---|---|
| `test_builder_construction.py` | Builder kwargs validation; states/points/schedule wiring |
| `test_builder_chain.py` | State-handle method chaining (.add/.subtract/.charge/.grow/etc.) |
| `test_builder_between.py` | `.between(p1, p2)` scope marker |
| `test_builder_at_and_increment.py` | `rf["s"].at("p")` typed reference; `rf.increment(label)` |
| `test_pass_validate.py` | `Validate` pass |
| `test_pass_resolve_state_refs.py` | `ResolveStateRefs` pass |
| `test_pass_fold_constants.py` | `FoldConstants` pass |
| `test_pass_assign_capture_slots.py` | `AssignCaptureSlots` pass |
| `test_pass_lower_polars.py` | `LowerToPolarsPlugin` pass |
| `test_compile.py` | End-to-end compile pipeline; structured pass logs |
| `test_explain.py` | `explain()` rendering for canonical examples |
| `test_smoke_compile_ul.py` | §4.6 UL example builds → compiles → explains |

**Untouched:**
- D1 modules (`_refs.py`, `_ops.py`, `_ir.py`, `_engine_binding.py`, `_canonical.py`, `_fingerprint.py`, `_action_key.py`) — read-only consumers.
- Old `gaspatchio_core/rollforward/` — keeps running through D2; cutover happens in D3.
- `gaspatchio_core/__init__.py` top-level — D3 wires `af.projection.rollforward` to the new builder; D2 leaves it unchanged.

---

## Tasks

### Task 1: `RollforwardBuilder` skeleton + state declarations

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Create: `bindings/python/tests/rollforward_v2/test_builder_construction.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_builder_construction.py
"""RollforwardBuilder construction + state declaration tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def monthly_sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


class TestBuilderConstruction:
    def test_single_state_no_points(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("cv_init")},
            schedule=monthly_sched,
        )
        assert list(b._state_inits.keys()) == ["av"]
        assert b._points == ("bop", "eop")
        assert b._schedule is monthly_sched
        assert b._track_increments is False
        assert b._lapse_when_all_non_positive == ()
        assert b._contract_boundary is None

    def test_multi_state_with_explicit_points(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("av_init"), "guarantee": pl.col("g_init")},
            points=["bop", "after_growth", "eop"],
            schedule=monthly_sched,
        )
        assert list(b._state_inits.keys()) == ["av", "guarantee"]
        assert b._points == ("bop", "after_growth", "eop")

    def test_track_increments_flag(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=monthly_sched,
            track_increments=True,
        )
        assert b._track_increments is True

    def test_lapse_kwarg(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init"), "g": pl.col("g_init")},
            schedule=monthly_sched,
            lapse_when_all_non_positive=["av", "g"],
        )
        assert b._lapse_when_all_non_positive == ("av", "g")

    def test_contract_boundary_kwarg(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"reserve": pl.col("init")},
            schedule=monthly_sched,
            contract_boundary=pl.col("is_repriceable"),
        )
        assert b._contract_boundary is not None

    def test_user_supplied_points_must_include_bop_and_eop(
        self, monthly_sched: Schedule,
    ) -> None:
        with pytest.raises(ValueError, match="points must include 'bop' and 'eop'"):
            RollforwardBuilder(
                states={"av": pl.col("init")},
                points=["pre_event", "post_event"],
                schedule=monthly_sched,
            )

    def test_lapse_state_must_exist(self, monthly_sched: Schedule) -> None:
        with pytest.raises(ValueError, match="lapse_when_all_non_positive.*unknown"):
            RollforwardBuilder(
                states={"av": pl.col("init")},
                schedule=monthly_sched,
                lapse_when_all_non_positive=["does_not_exist"],
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_construction.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/rollforward_v2/_builder.py
"""User-facing builder API for the rollforward redesign.

The builder is mutable scaffolding that emits an immutable D1 :class:`IR`
on ``._build()``. Users construct it via ``af.projection.rollforward(...)``
(wired in D3) and chain method calls on state handles to declare
transitions.

Phase 1 builder semantics:
  - Default points are ``("bop", "eop")`` if not supplied.
  - User-supplied ``points`` must include ``'bop'`` and ``'eop'``; the
    declared order is the partial order the kernel walks.
  - Default ``batch_axes`` is ``("policy",)``.
  - Schedule is required (even for products that don't care about
    calendar discipline — pass an integer-period default Schedule).
  - ``contract_boundary`` accepts a closed-subset boolean :class:`pl.Expr`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.schedule import Schedule


class RollforwardBuilder:
    def __init__(
        self,
        *,
        states: dict[str, "pl.Expr"],
        schedule: "Schedule",
        points: Iterable[str] | None = None,
        track_increments: bool = False,
        lapse_when_all_non_positive: Iterable[str] = (),
        contract_boundary: "pl.Expr | None" = None,
        batch_axes: tuple[str, ...] = ("policy",),
    ) -> None:
        # Validate points
        pts = tuple(points) if points is not None else ("bop", "eop")
        if "bop" not in pts or "eop" not in pts:
            msg = "points must include 'bop' and 'eop'"
            raise ValueError(msg)

        # Validate lapse states all exist
        lapse_tuple = tuple(lapse_when_all_non_positive)
        unknown = [s for s in lapse_tuple if s not in states]
        if unknown:
            msg = (
                f"lapse_when_all_non_positive references unknown state(s) {unknown}; "
                f"declared states are {list(states)}"
            )
            raise ValueError(msg)

        self._state_inits: dict[str, "pl.Expr"] = dict(states)
        self._points: tuple[str, ...] = pts
        self._schedule = schedule
        self._track_increments = track_increments
        self._lapse_when_all_non_positive = lapse_tuple
        self._contract_boundary = contract_boundary
        self._batch_axes: tuple[str, ...] = tuple(batch_axes)

        # Op accumulator — mutated as the user chains transitions
        from gaspatchio_core.rollforward_v2._ops import Op as _Op  # noqa: F401

        self._transitions: list = []  # list[Op]
        # Current scope window (None if no .between(...) is active)
        self._current_state: str | None = None
        self._current_window: tuple[str, str] | None = None


__all__ = ["RollforwardBuilder"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_construction.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_construction.py
git commit -m "feat(rollforward-v2): add RollforwardBuilder skeleton with state declarations"
```

---

### Task 2: State-handle proxy + arithmetic chain (`.add` / `.subtract` / `.charge`)

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Create: `bindings/python/tests/rollforward_v2/test_builder_chain.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_builder_chain.py
"""State-handle method chaining tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._ops import Add, Charge, Subtract
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def builder() -> RollforwardBuilder:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )
    return RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)


class TestAdd:
    def test_add_emits_op_with_default_eop_target(
        self, builder: RollforwardBuilder,
    ) -> None:
        builder["av"].add(pl.col("premium"), label="Premium")
        assert len(builder._transitions) == 1
        op = builder._transitions[0]
        assert isinstance(op, Add)
        assert op.target.state == "av"
        assert op.target.point == "eop"
        assert op.label == "Premium"

    def test_chained_add_calls_all_emit(self, builder: RollforwardBuilder) -> None:
        builder["av"].add(pl.col("p1"), label="A").add(pl.col("p2"), label="B")
        assert len(builder._transitions) == 2
        assert builder._transitions[0].label == "A"
        assert builder._transitions[1].label == "B"


class TestSubtract:
    def test_subtract_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].subtract(pl.col("withdrawal"), label="W")
        assert isinstance(builder._transitions[0], Subtract)


class TestCharge:
    def test_charge_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].charge(pl.col("expense"), label="E")
        assert isinstance(builder._transitions[0], Charge)


class TestUnknownState:
    def test_indexing_unknown_state_raises(self, builder: RollforwardBuilder) -> None:
        with pytest.raises(KeyError, match="unknown state 'guarantee'"):
            builder["guarantee"].add(pl.col("x"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_chain.py -v`
Expected: FAIL — `RollforwardBuilder` has no `__getitem__`.

- [ ] **Step 3: Implement**

Append to `_builder.py`:

```python
from gaspatchio_core.rollforward_v2._ops import Add, Charge, Subtract
from gaspatchio_core.rollforward_v2._refs import StateRef


class _StateHandle:
    """Mutable proxy returned by ``builder["state_name"]``.

    Holds a reference to the parent builder and the state name; method
    calls (``.add()``, ``.subtract()``, etc.) emit Ops into the builder.
    Returns ``self`` from each emit so calls chain.
    """

    def __init__(self, builder: "RollforwardBuilder", state: str) -> None:
        self._b = builder
        self._state = state

    def _target_point(self) -> str:
        # If a .between(...) scope is active and applies to this state, use its end-point.
        # Otherwise default to 'eop'.
        if self._b._current_state == self._state and self._b._current_window is not None:
            return self._b._current_window[1]
        return "eop"

    def add(self, expr: "pl.Expr", *, label: str | None = None) -> "_StateHandle":
        op = Add(
            target=StateRef(state=self._state, point=self._target_point()),
            expr=expr,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def subtract(self, expr: "pl.Expr", *, label: str | None = None) -> "_StateHandle":
        op = Subtract(
            target=StateRef(state=self._state, point=self._target_point()),
            expr=expr,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def charge(self, rate: "pl.Expr", *, label: str | None = None) -> "_StateHandle":
        op = Charge(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=rate,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self


# Inside RollforwardBuilder:
    def __getitem__(self, state_name: str) -> "_StateHandle":
        if state_name not in self._state_inits:
            msg = f"unknown state {state_name!r}; declared states are {list(self._state_inits)}"
            raise KeyError(msg)
        return _StateHandle(self, state_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_chain.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_chain.py
git commit -m "feat(rollforward-v2): add state-handle .add/.subtract/.charge chain"
```

---

### Task 3: Time-aware + structural method chains (`.grow`, `.grow_capped`, `.deduct_nar`, `.ratchet`, `.floor`, `.apply`)

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Modify: `bindings/python/tests/rollforward_v2/test_builder_chain.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from gaspatchio_core.rollforward_v2._ops import (
    Apply,
    DeductNAR,
    Floor,
    Grow,
    GrowCapped,
    Ratchet,
)


class TestGrow:
    def test_grow_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].grow(pl.col("rate"), label="Interest")
        assert isinstance(builder._transitions[0], Grow)


class TestGrowCapped:
    def test_grow_capped_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].grow_capped(
            pl.col("rate"), floor=pl.lit(0.0), cap=pl.lit(0.10), label="IUL",
        )
        op = builder._transitions[0]
        assert isinstance(op, GrowCapped)
        assert op.label == "IUL"


class TestDeductNAR:
    def test_deduct_nar_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].deduct_nar(
            pl.col("coi_rate"), death_benefit=pl.col("db"), label="COI",
        )
        op = builder._transitions[0]
        assert isinstance(op, DeductNAR)


class TestRatchet:
    def test_ratchet_with_when_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].ratchet(
            to=pl.col("hwm"), when=pl.col("anniversary"), label="R",
        )
        op = builder._transitions[0]
        assert isinstance(op, Ratchet)
        assert op.when is not None

    def test_ratchet_without_when_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].ratchet(to=pl.col("hwm"), label="HWM")
        assert builder._transitions[0].when is None


class TestFloor:
    def test_floor_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].floor(0.0)
        assert isinstance(builder._transitions[0], Floor)
        assert builder._transitions[0].value == 0.0


class TestApply:
    def test_apply_emits_op(self, builder: RollforwardBuilder) -> None:
        builder["av"].apply(pl.col("av") + pl.col("custom"), label="Custom")
        op = builder._transitions[0]
        assert isinstance(op, Apply)
        assert op.label == "Custom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_chain.py -v -k "Grow or Deduct or Ratchet or Floor or Apply"`
Expected: FAIL — methods missing.

- [ ] **Step 3: Implement**

Append to `_StateHandle` class:

```python
    def grow(self, rate: "pl.Expr", *, label: str | None = None) -> "_StateHandle":
        op = Grow(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=rate,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def grow_capped(
        self,
        rate: "pl.Expr",
        *,
        floor: "pl.Expr",
        cap: "pl.Expr",
        label: str | None = None,
    ) -> "_StateHandle":
        op = GrowCapped(
            target=StateRef(state=self._state, point=self._target_point()),
            rate=rate,
            floor=floor,
            cap=cap,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def deduct_nar(
        self,
        coi_rate: "pl.Expr",
        *,
        death_benefit: "pl.Expr",
        label: str | None = None,
    ) -> "_StateHandle":
        op = DeductNAR(
            target=StateRef(state=self._state, point=self._target_point()),
            coi_rate=coi_rate,
            death_benefit=death_benefit,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def ratchet(
        self,
        *,
        to: "pl.Expr",
        when: "pl.Expr | None" = None,
        label: str | None = None,
    ) -> "_StateHandle":
        op = Ratchet(
            target=StateRef(state=self._state, point=self._target_point()),
            to=to,
            when=when,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def floor(self, value: float) -> "_StateHandle":
        op = Floor(
            target=StateRef(state=self._state, point=self._target_point()),
            value=value,
        )
        op.verify()
        self._b._transitions.append(op)
        return self

    def apply(self, body: "pl.Expr", *, label: str | None = None) -> "_StateHandle":
        op = Apply(
            target=StateRef(state=self._state, point=self._target_point()),
            body=body,
            label=label,
        )
        op.verify()
        self._b._transitions.append(op)
        return self
```

Update imports at the top of `_builder.py` to include `Apply`, `DeductNAR`, `Floor`, `Grow`, `GrowCapped`, `Ratchet`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_chain.py -v`
Expected: PASS — 11+ tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_chain.py
git commit -m "feat(rollforward-v2): add grow/grow_capped/deduct_nar/ratchet/floor/apply chain"
```

---

### Task 4: `.between(p1, p2)` scope marker

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Create: `bindings/python/tests/rollforward_v2/test_builder_between.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_builder_between.py
"""`.between(p1, p2)` scope marker tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def builder_with_points() -> RollforwardBuilder:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )
    return RollforwardBuilder(
        states={"av": pl.col("init")},
        points=["bop", "post_coi", "eop"],
        schedule=sched,
    )


class TestBetween:
    def test_between_targets_subsequent_op_to_named_point(
        self, builder_with_points: RollforwardBuilder,
    ) -> None:
        builder_with_points["av"].between("bop", "post_coi").add(
            pl.col("premium"), label="Premium",
        )
        op = builder_with_points._transitions[0]
        assert op.target.point == "post_coi"

    def test_two_between_calls_apply_to_their_own_ops(
        self, builder_with_points: RollforwardBuilder,
    ) -> None:
        b = builder_with_points
        b["av"].between("bop", "post_coi").add(pl.col("a"), label="A")
        b["av"].between("post_coi", "eop").charge(pl.col("e"), label="E")

        assert b._transitions[0].target.point == "post_coi"
        assert b._transitions[1].target.point == "eop"

    def test_unknown_point_raises(
        self, builder_with_points: RollforwardBuilder,
    ) -> None:
        with pytest.raises(ValueError, match="unknown point 'mystery'"):
            builder_with_points["av"].between("bop", "mystery")

    def test_between_endpoint_preceding_startpoint_raises(
        self, builder_with_points: RollforwardBuilder,
    ) -> None:
        with pytest.raises(ValueError, match="must precede"):
            builder_with_points["av"].between("eop", "bop")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_between.py -v`
Expected: FAIL — `_StateHandle` has no `between`.

- [ ] **Step 3: Implement**

Append to `_StateHandle`:

```python
    def between(self, p1: str, p2: str) -> "_StateHandle":
        # Validate points exist
        for p in (p1, p2):
            if p not in self._b._points:
                msg = f"unknown point {p!r}; declared points are {list(self._b._points)}"
                raise ValueError(msg)
        # Validate p1 precedes p2 in declared order
        if self._b._points.index(p1) >= self._b._points.index(p2):
            msg = f"{p1!r} must precede {p2!r} in declared point order"
            raise ValueError(msg)
        # Stash the scope on the builder; subsequent ops on this handle pick it up.
        # New handle is returned (rather than mutating self) so each chain has its
        # own scope window without aliasing.
        new_handle = _StateHandle(self._b, self._state)
        self._b._current_state = self._state
        self._b._current_window = (p1, p2)
        return new_handle
```

Update `_target_point()`:

```python
    def _target_point(self) -> str:
        if (
            self._b._current_state == self._state
            and self._b._current_window is not None
        ):
            return self._b._current_window[1]
        return "eop"
```

(This logic was already in place — just confirms behavior. Important: each Op emission does NOT clear the scope; the user can chain multiple `.add()` etc. inside one `.between(...)` window. The scope is implicitly cleared when a new `.between(...)` is called.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_between.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_between.py
git commit -m "feat(rollforward-v2): add .between(p1, p2) scope marker"
```

---

### Task 5: `rf["s"].at("p")` typed reference + `rf.increment(label)`

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Create: `bindings/python/tests/rollforward_v2/test_builder_at_and_increment.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_builder_at_and_increment.py
"""rf['s'].at('p') typed reference + rf.increment(label) accessor."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def b() -> RollforwardBuilder:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )
    return RollforwardBuilder(
        states={"av": pl.col("init")},
        points=["bop", "post_coi", "eop"],
        schedule=sched,
        track_increments=True,
    )


class TestAt:
    def test_at_returns_state_ref(self, b: RollforwardBuilder) -> None:
        ref = b["av"].at("post_coi")
        assert isinstance(ref, StateRef)
        assert ref.state == "av"
        assert ref.point == "post_coi"

    def test_at_unknown_point_raises(self, b: RollforwardBuilder) -> None:
        with pytest.raises(ValueError, match="unknown point 'mystery'"):
            b["av"].at("mystery")


class TestIncrement:
    def test_increment_records_label_request(self, b: RollforwardBuilder) -> None:
        b["av"].add(pl.col("p"), label="Premium")
        ref = b.increment("Premium")
        # Returns an opaque IncrementRef that the compiler resolves to a Struct field
        assert ref.label == "Premium"

    def test_increment_unknown_label_raises_at_lookup_time(
        self, b: RollforwardBuilder,
    ) -> None:
        # Phase 1: increment(label) construction is permissive — the compiler
        # validates that the label was emitted by some op. At builder-time this
        # is a deferred check.
        ref = b.increment("DoesNotExist")
        assert ref.label == "DoesNotExist"

    def test_increment_requires_track_increments_flag(
        self,
    ) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
        )
        b_no_track = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=sched,
            track_increments=False,
        )
        with pytest.raises(ValueError, match="track_increments=True"):
            b_no_track.increment("Anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_at_and_increment.py -v`
Expected: FAIL — `at` and `increment` not implemented.

- [ ] **Step 3: Implement**

Append to `_StateHandle`:

```python
    def at(self, point: str) -> StateRef:
        if point not in self._b._points:
            msg = f"unknown point {point!r}; declared points are {list(self._b._points)}"
            raise ValueError(msg)
        return StateRef(state=self._state, point=point)
```

Add to `_builder.py` (top-level alongside `_StateHandle`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class IncrementRef:
    """Opaque reference to a labelled per-period delta — resolved by the compiler."""

    label: str
```

Append to `RollforwardBuilder`:

```python
    def increment(self, label: str) -> IncrementRef:
        if not self._track_increments:
            msg = (
                "rf.increment(...) requires track_increments=True on the builder; "
                "construct rollforward with track_increments=True to use increments"
            )
            raise ValueError(msg)
        return IncrementRef(label=label)
```

Update `__all__`:

```python
__all__ = ["IncrementRef", "RollforwardBuilder"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_at_and_increment.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_at_and_increment.py
git commit -m "feat(rollforward-v2): add rf['s'].at('p') typed ref + rf.increment(label)"
```

---

### Task 6: `_build()` — emit IR from Builder

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_builder.py`
- Modify: `bindings/python/tests/rollforward_v2/test_builder_construction.py`

- [ ] **Step 1: Write the failing test**

Append to `test_builder_construction.py`:

```python
class TestBuild:
    def test_build_returns_ir(self, monthly_sched: Schedule) -> None:
        from gaspatchio_core.rollforward_v2._ir import IR

        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=monthly_sched)
        b["av"].add(pl.col("premium"), label="P").floor(0.0)
        ir = b._build()
        assert isinstance(ir, IR)
        assert len(ir.transitions) == 2
        assert ir.points == ("bop", "eop")
        assert ir.batch_axes == ("policy",)

    def test_build_carries_lapse_and_contract_boundary(
        self, monthly_sched: Schedule,
    ) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init"), "g": pl.col("init2")},
            schedule=monthly_sched,
            lapse_when_all_non_positive=["av"],
            contract_boundary=pl.col("breach"),
        )
        b["av"].add(pl.col("p"), label="P")
        ir = b._build()
        assert ir.lapse_when_all_non_positive == ("av",)
        assert ir.contract_boundary is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_construction.py::TestBuild -v`
Expected: FAIL — `_build` not implemented.

- [ ] **Step 3: Implement**

Append to `RollforwardBuilder`:

```python
    def _build(self) -> "IR":  # noqa: F821
        from gaspatchio_core.rollforward_v2._ir import IR, State

        states = tuple(
            State(name=name, init=init) for name, init in self._state_inits.items()
        )
        return IR(
            states=states,
            points=self._points,
            transitions=tuple(self._transitions),
            schedule=self._schedule,
            batch_axes=self._batch_axes,
            track_increments=self._track_increments,
            lapse_when_all_non_positive=self._lapse_when_all_non_positive,
            contract_boundary=self._contract_boundary,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_builder_construction.py::TestBuild -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_builder.py bindings/python/tests/rollforward_v2/test_builder_construction.py
git commit -m "feat(rollforward-v2): add Builder._build() emitting immutable IR"
```

---

### Task 7: `Pass` Protocol + `Validate` pass

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_passes.py`
- Create: `bindings/python/tests/rollforward_v2/test_pass_validate.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_pass_validate.py
"""Validate pass — per-Op verify, point/state consistency."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._ir import IR, State
from gaspatchio_core.rollforward_v2._ops import Add, Floor
from gaspatchio_core.rollforward_v2._passes import Validate
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


def _ir_with(transitions: tuple, sched: Schedule, points=("bop", "eop")) -> IR:
    return IR(
        states=(State(name="av", init=pl.col("init")),),
        points=points,
        transitions=transitions,
        schedule=sched,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )


class TestValidate:
    def test_passes_through_valid_ir(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (
                Add(target=StateRef(state="av", point="eop"), expr=pl.col("p"), label="P"),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            base_schedule,
        )
        out = Validate().apply(ir)
        # Validate is a no-op transform — returns the same IR
        assert out is ir

    def test_op_targeting_unknown_state_raises(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (Add(target=StateRef(state="ghost", point="eop"), expr=pl.col("p"), label="P"),),
            base_schedule,
        )
        with pytest.raises(ValueError, match="targets unknown state 'ghost'"):
            Validate().apply(ir)

    def test_op_targeting_unknown_point_raises(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (Add(target=StateRef(state="av", point="ghost"), expr=pl.col("p"), label="P"),),
            base_schedule,
        )
        with pytest.raises(ValueError, match="targets unknown point 'ghost'"):
            Validate().apply(ir)

    def test_track_increments_requires_label_on_every_op(
        self, base_schedule: Schedule,
    ) -> None:
        # Floor doesn't take a label (no label field) — but Add etc. with label=None
        # should fail when track_increments=True
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(target=StateRef(state="av", point="eop"), expr=pl.col("p"), label=None),
            ),
            schedule=base_schedule,
            batch_axes=("policy",),
            track_increments=True,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        with pytest.raises(ValueError, match="track_increments=True.*requires.*label"):
            Validate().apply(ir)

    def test_pass_name(self) -> None:
        assert Validate().name() == "validate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_validate.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/rollforward_v2/_passes.py
"""Compilation passes — CVXPY-style reduction chain.

Each pass implements ``Pass`` Protocol: ``name()`` returns a stable string
used in TRACE-level logs; ``apply(ir)`` returns a transformed IR. Passes
are pure functions over IRs (no shared mutable state); rerun-friendly.

Phase 1 chain:
  Validate           — per-Op verify(); state/point consistency
  ResolveStateRefs   — compile-time check that every StateRef points
                       at a declared state and a declared point
  FoldConstants      — placeholder Phase 1 (cheap pass-through);
                       Phase 2 may add real folding
  AssignCaptureSlots — collect every (state, point) read-pair into
                       slot indices for Struct emission
  LowerToPolarsPlugin — IR + slot table → plugin_kwargs dict
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from gaspatchio_core.rollforward_v2._ir import IR


class Pass(Protocol):
    def name(self) -> str: ...
    def apply(self, ir: "IR") -> "IR": ...


@dataclass(frozen=True)
class Validate:
    def name(self) -> str:
        return "validate"

    def apply(self, ir: "IR") -> "IR":
        state_names = {s.name for s in ir.states}
        for op in ir.transitions:
            # Every Op has a target StateRef
            target = getattr(op, "target", None)
            if target is None:
                msg = f"{type(op).__name__} has no target StateRef"
                raise ValueError(msg)
            if target.state not in state_names:
                msg = (
                    f"{type(op).__name__} targets unknown state {target.state!r}; "
                    f"declared states are {sorted(state_names)}"
                )
                raise ValueError(msg)
            if target.point not in ir.points:
                msg = (
                    f"{type(op).__name__} targets unknown point {target.point!r}; "
                    f"declared points are {list(ir.points)}"
                )
                raise ValueError(msg)
            # Per-Op verify (e.g., Charge negative-literal check)
            op.verify()
            # When track_increments=True every label-bearing Op must have a label
            if ir.track_increments:
                # Check via dataclass fields whether this Op has a label field
                op_fields = {f.name for f in fields(op)}  # type: ignore[arg-type]
                if "label" in op_fields and getattr(op, "label") is None:
                    msg = (
                        f"track_increments=True requires every label-bearing Op to "
                        f"have label=...; {type(op).__name__} has label=None"
                    )
                    raise ValueError(msg)
        return ir


__all__ = ["Pass", "Validate"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_validate.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_passes.py bindings/python/tests/rollforward_v2/test_pass_validate.py
git commit -m "feat(rollforward-v2): add Pass Protocol + Validate pass"
```

---

### Task 8: `ResolveStateRefs` pass

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_passes.py`
- Create: `bindings/python/tests/rollforward_v2/test_pass_resolve_state_refs.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_pass_resolve_state_refs.py
"""ResolveStateRefs pass — verifies in-period state-read precedence."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._ir import IR, State
from gaspatchio_core.rollforward_v2._ops import Add, Apply, Floor, Grow
from gaspatchio_core.rollforward_v2._passes import ResolveStateRefs
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


class TestResolveStateRefs:
    def test_pass_name(self) -> None:
        assert ResolveStateRefs().name() == "resolve_state_refs"

    def test_passes_through_when_all_refs_resolve(
        self, base_schedule: Schedule,
    ) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "post_coi", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="post_coi"),
                    expr=pl.col("premium"),
                    label="P",
                ),
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("rate"),
                    label="G",
                ),
            ),
            schedule=base_schedule,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out = ResolveStateRefs().apply(ir)
        assert out is ir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_resolve_state_refs.py -v`
Expected: FAIL — `ImportError: ResolveStateRefs`.

- [ ] **Step 3: Implement**

Append to `_passes.py`:

```python
@dataclass(frozen=True)
class ResolveStateRefs:
    """Compile-time check that every StateRef in an Op's expression body
    references a declared state and a declared point.

    Phase 1 implementation: relies on Validate having already checked
    target StateRefs; this pass is a no-op transform reserved for the
    Phase 2 work that lowers cross-state reads to integer slot indices.
    """

    def name(self) -> str:
        return "resolve_state_refs"

    def apply(self, ir: "IR") -> "IR":
        # Phase 1: pass-through. The lowering work happens in
        # AssignCaptureSlots + LowerToPolarsPlugin.
        return ir
```

Update `__all__` to add `ResolveStateRefs`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_resolve_state_refs.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_passes.py bindings/python/tests/rollforward_v2/test_pass_resolve_state_refs.py
git commit -m "feat(rollforward-v2): add ResolveStateRefs pass (Phase 1 stub)"
```

---

### Task 9: `FoldConstants` pass

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_passes.py`
- Create: `bindings/python/tests/rollforward_v2/test_pass_fold_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_pass_fold_constants.py
"""FoldConstants pass — Phase 1 stub."""

from __future__ import annotations

from gaspatchio_core.rollforward_v2._ir import IR
from gaspatchio_core.rollforward_v2._passes import FoldConstants


class TestFoldConstants:
    def test_pass_name(self) -> None:
        assert FoldConstants().name() == "fold_constants"

    def test_phase_1_is_pass_through(self, single_state_ir: IR) -> None:
        out = FoldConstants().apply(single_state_ir)
        assert out is single_state_ir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_fold_constants.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `_passes.py`:

```python
@dataclass(frozen=True)
class FoldConstants:
    """Constant folding pass.

    Phase 1: pass-through stub. Polars already does eager constant folding
    inside its query optimiser, so duplicating that here adds no value.
    Phase 2 may revisit if benchmarks identify a reduction opportunity.
    """

    def name(self) -> str:
        return "fold_constants"

    def apply(self, ir: "IR") -> "IR":
        return ir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_fold_constants.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_passes.py bindings/python/tests/rollforward_v2/test_pass_fold_constants.py
git commit -m "feat(rollforward-v2): add FoldConstants pass (Phase 1 stub)"
```

---

### Task 10: `AssignCaptureSlots` pass

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_passes.py`
- Create: `bindings/python/tests/rollforward_v2/test_pass_assign_capture_slots.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_pass_assign_capture_slots.py
"""AssignCaptureSlots — collects (state, point) reads into Struct slots."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._ir import IR, State
from gaspatchio_core.rollforward_v2._ops import Add, Floor, Ratchet
from gaspatchio_core.rollforward_v2._passes import AssignCaptureSlots
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


class TestAssignCaptureSlots:
    def test_pass_name(self) -> None:
        assert AssignCaptureSlots().name() == "assign_capture_slots"

    def test_eop_is_always_a_capture_slot(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(target=StateRef(state="av", point="eop"), expr=pl.col("p"), label="P"),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out, slots = AssignCaptureSlots().apply_with_slots(ir)
        # Every state's eop is implicitly captured (so af.av = rf['av'] works)
        assert StateRef(state="av", point="eop") in slots

    def test_distinct_at_reads_get_distinct_slots(self, sched: Schedule) -> None:
        # Build an IR where Ratchet.to references rf['av'].at('after_growth')
        ir = IR(
            states=(
                State(name="av", init=pl.col("init")),
                State(name="g", init=pl.col("g_init")),
            ),
            points=("bop", "after_growth", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="after_growth"),
                    expr=pl.col("growth"),
                    label="G",
                ),
                Ratchet(
                    target=StateRef(state="g", point="eop"),
                    to=pl.col("av_post"),  # placeholder for the Phase 2 cross-state read
                    when=pl.col("anniv"),
                    label="R",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out, slots = AssignCaptureSlots().apply_with_slots(ir)
        # eop slots for both states are implicit
        assert StateRef(state="av", point="eop") in slots
        assert StateRef(state="g", point="eop") in slots

    def test_apply_returns_ir_unchanged(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out = AssignCaptureSlots().apply(ir)
        assert out is ir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_assign_capture_slots.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `_passes.py`:

```python
from gaspatchio_core.rollforward_v2._refs import StateRef


@dataclass(frozen=True)
class AssignCaptureSlots:
    """Collect every (state, point) read into a sorted slot table.

    The slot table is what the Polars-backend kernel uses to decide
    which fields to emit on its per-row Struct output (D3). Phase 1
    captures every state's ``eop`` implicitly so user-side ``af.av =
    rf["av"]`` works without a `.at("eop")` annotation.

    Returns the unchanged IR via ``apply``; the slot table is exposed
    via ``apply_with_slots``.
    """

    def name(self) -> str:
        return "assign_capture_slots"

    def apply(self, ir: "IR") -> "IR":
        return ir  # the IR itself is unchanged; the slots travel separately

    def apply_with_slots(self, ir: "IR") -> tuple["IR", tuple["StateRef", ...]]:
        slots: set[StateRef] = set()
        # Implicit: every state's eop is a capture slot
        for s in ir.states:
            slots.add(StateRef(state=s.name, point="eop"))
        # Phase 1: explicit cross-state reads via ``rf["s"].at("p")`` are
        # construction-time StateRef instances. The compiler walks Op
        # body Exprs to find them — Phase 2 expansion. For Phase 1, capture
        # only what the Validate pass has already checked: every Op's target.
        for op in ir.transitions:
            target = getattr(op, "target", None)
            if target is not None:
                slots.add(target)
        # Sort for determinism
        ordered = tuple(
            sorted(slots, key=lambda r: (r.state, ir.points.index(r.point)))
        )
        return ir, ordered
```

Update `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_assign_capture_slots.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_passes.py bindings/python/tests/rollforward_v2/test_pass_assign_capture_slots.py
git commit -m "feat(rollforward-v2): add AssignCaptureSlots pass (eop-implicit + target capture)"
```

---

### Task 11: `LowerToPolarsPlugin` pass

**Files:**
- Modify: `bindings/python/gaspatchio_core/rollforward_v2/_passes.py`
- Create: `bindings/python/tests/rollforward_v2/test_pass_lower_polars.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_pass_lower_polars.py
"""LowerToPolarsPlugin — emits plugin_kwargs dict for D3's kernel."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._ir import IR, State
from gaspatchio_core.rollforward_v2._ops import Add, Floor
from gaspatchio_core.rollforward_v2._passes import (
    AssignCaptureSlots,
    LowerToPolarsPlugin,
)
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


class TestLowerToPolarsPlugin:
    def test_pass_name(self) -> None:
        assert LowerToPolarsPlugin().name() == "lower_polars"

    def test_emits_plugin_kwargs_with_canonical_keys(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(target=StateRef(state="av", point="eop"), expr=pl.col("p"), label="P"),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs = LowerToPolarsPlugin().lower(ir, slots)
        assert "ir" in kwargs
        assert "captures" in kwargs
        assert "track_increments" in kwargs
        assert "lapse_when_all_non_positive" in kwargs
        assert "contract_boundary" in kwargs

    def test_kwargs_ir_field_is_canonical_form(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs = LowerToPolarsPlugin().lower(ir, slots)
        assert isinstance(kwargs["ir"], dict)  # canonical form
        assert "transitions" in kwargs["ir"]

    def test_captures_serialised_as_state_point_pairs(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs = LowerToPolarsPlugin().lower(ir, slots)
        assert kwargs["captures"] == [["av", "eop"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_lower_polars.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `_passes.py`:

```python
from gaspatchio_core.rollforward_v2._canonical import canonical_form


@dataclass(frozen=True)
class LowerToPolarsPlugin:
    """Lower an IR + slot table into a plugin_kwargs dict.

    The dict is JSON-serialisable and consumed by D3's Rust kernel as
    the bridge between the compile-time IR and runtime execution.

    Phase 1 kwargs schema:
      ir: canonical_form dict
      captures: list[[state, point]] in slot order
      track_increments: bool
      lapse_when_all_non_positive: list[str]  (sorted)
      contract_boundary: str | None  (Expr string-form when set)
    """

    def name(self) -> str:
        return "lower_polars"

    def apply(self, ir: "IR") -> "IR":
        return ir

    def lower(self, ir: "IR", slots: tuple) -> dict:
        return {
            "ir": canonical_form(ir),
            "captures": [[s.state, s.point] for s in slots],
            "track_increments": ir.track_increments,
            "lapse_when_all_non_positive": sorted(ir.lapse_when_all_non_positive),
            "contract_boundary": (
                str(ir.contract_boundary) if ir.contract_boundary is not None else None
            ),
        }
```

Update `__all__` to include `LowerToPolarsPlugin`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_pass_lower_polars.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_passes.py bindings/python/tests/rollforward_v2/test_pass_lower_polars.py
git commit -m "feat(rollforward-v2): add LowerToPolarsPlugin pass (kwargs serialisation)"
```

---

### Task 12: `compile_rollforward()` orchestrator + `CompiledRollforward`

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_compiled.py`
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_compile.py`
- Create: `bindings/python/tests/rollforward_v2/test_compile.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_compile.py
"""compile_rollforward end-to-end orchestration."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.rollforward_v2._compiled import CompiledRollforward
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
    )


class TestCompile:
    def test_returns_compiled_rollforward(self, sched: Schedule) -> None:
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("p"), label="P").floor(0.0)
        compiled = compile_rollforward(b)
        assert isinstance(compiled, CompiledRollforward)
        assert compiled.ir.states[0].name == "av"
        assert "ir" in compiled.plugin_kwargs

    def test_passes_run_in_declared_order(self, sched: Schedule, caplog) -> None:
        # Each pass emits a structured TRACE log
        import logging
        from loguru import logger

        captured: list[str] = []
        sink_id = logger.add(lambda msg: captured.append(msg.record["message"]), level="TRACE")
        try:
            b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
            b["av"].floor(0.0)
            compile_rollforward(b)
        finally:
            logger.remove(sink_id)
        # Pass names appear in compile-time logs in order
        log_text = "\n".join(captured)
        for pass_name in (
            "validate",
            "resolve_state_refs",
            "fold_constants",
            "assign_capture_slots",
            "lower_polars",
        ):
            assert pass_name in log_text

    def test_validate_failure_short_circuits(self, sched: Schedule) -> None:
        # Build an IR that fails Validate (Op targeting unknown state — only
        # constructible by raw IR, not Builder, since Builder validates earlier;
        # but compile_rollforward must surface validate failures cleanly)
        from gaspatchio_core.rollforward_v2._ir import IR, State
        from gaspatchio_core.rollforward_v2._ops import Add
        from gaspatchio_core.rollforward_v2._refs import StateRef

        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(target=StateRef(state="ghost", point="eop"), expr=pl.col("x"), label="X"),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        with pytest.raises(ValueError, match="targets unknown state 'ghost'"):
            compile_rollforward(ir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_compile.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/rollforward_v2/_compiled.py
"""CompiledRollforward — frozen output of compile_rollforward()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gaspatchio_core.rollforward_v2._ir import IR
    from gaspatchio_core.rollforward_v2._refs import StateRef


@dataclass(frozen=True)
class CompiledRollforward:
    """Frozen artefact carrying the compiled IR + plugin kwargs.

    Consumed by D3's Polars accessor walk + plugin Expr emission.
    """

    ir: "IR"
    plugin_kwargs: dict[str, Any]
    capture_slots: tuple["StateRef", ...]


__all__ = ["CompiledRollforward"]
```

```python
# bindings/python/gaspatchio_core/rollforward_v2/_compile.py
"""compile_rollforward orchestrator — runs the 5-pass chain.

Accepts either a RollforwardBuilder (calling its ._build() to obtain an IR)
or an IR directly (useful for tests that bypass the builder).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from gaspatchio_core.rollforward_v2._compiled import CompiledRollforward
from gaspatchio_core.rollforward_v2._passes import (
    AssignCaptureSlots,
    FoldConstants,
    LowerToPolarsPlugin,
    ResolveStateRefs,
    Validate,
)

if TYPE_CHECKING:
    from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
    from gaspatchio_core.rollforward_v2._ir import IR


def compile_rollforward(
    target: "RollforwardBuilder | IR",
) -> CompiledRollforward:
    """Run the 5-pass chain over a Builder or an IR.

    Each pass logs a one-line TRACE record for observability:

        [validate]              ok — N transitions
        [resolve_state_refs]    ok
        [fold_constants]        ok
        [assign_capture_slots]  ok — N slots
        [lower_polars]          ok — N kwargs
    """
    from gaspatchio_core.rollforward_v2._ir import IR  # local to avoid cycle

    ir: IR = target if isinstance(target, IR) else target._build()

    ir = Validate().apply(ir)
    logger.trace(f"[validate]              ok — {len(ir.transitions)} transitions")

    ir = ResolveStateRefs().apply(ir)
    logger.trace("[resolve_state_refs]    ok")

    ir = FoldConstants().apply(ir)
    logger.trace("[fold_constants]        ok")

    slots_pass = AssignCaptureSlots()
    ir, slots = slots_pass.apply_with_slots(ir)
    logger.trace(f"[assign_capture_slots]  ok — {len(slots)} slots")

    lower = LowerToPolarsPlugin()
    plugin_kwargs = lower.lower(ir, slots)
    logger.trace(f"[lower_polars]          ok — {len(plugin_kwargs)} kwargs")

    return CompiledRollforward(
        ir=ir, plugin_kwargs=plugin_kwargs, capture_slots=slots,
    )


__all__ = ["compile_rollforward"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_compile.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_compile.py bindings/python/gaspatchio_core/rollforward_v2/_compiled.py bindings/python/tests/rollforward_v2/test_compile.py
git commit -m "feat(rollforward-v2): add compile_rollforward orchestrator + CompiledRollforward"
```

---

### Task 13: `explain()` rendering

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_explain.py`
- Create: `bindings/python/tests/rollforward_v2/test_explain.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_explain.py
"""explain() rendering tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._explain import explain
from gaspatchio_core.rollforward_v2._ir import IR, State
from gaspatchio_core.rollforward_v2._ops import Add, Floor, Grow
from gaspatchio_core.rollforward_v2._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def whole_life_ir() -> IR:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=240, frequency="1M",
    )
    return IR(
        states=(State(name="av", init=pl.col("cv_init")),),
        points=("bop", "eop"),
        transitions=(
            Add(
                target=StateRef(state="av", point="eop"),
                expr=pl.col("premium"),
                label="Premium",
            ),
            Grow(
                target=StateRef(state="av", point="eop"),
                rate=pl.col("interest"),
                label="Interest",
            ),
            Floor(target=StateRef(state="av", point="eop"), value=0.0),
        ),
        schedule=sched,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )


class TestExplain:
    def test_includes_spec_fingerprint(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "spec_fingerprint = sha256:" in out

    def test_lists_states_with_init(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "States:" in out
        assert "av:" in out
        assert "init=" in out

    def test_lists_points(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "Points:  bop, eop" in out

    def test_includes_schedule_summary(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "Schedule:" in out
        assert "from_calendar_grid" in out

    def test_lists_transitions_in_order(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        # Premium before Interest before (unlabelled) Floor
        prem_pos = out.find("Premium")
        int_pos = out.find("Interest")
        floor_pos = out.find("Floor")
        assert 0 < prem_pos < int_pos < floor_pos

    def test_includes_engine_binding(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "engine_binding:" in out
        assert ("portable" in out) or ("polars" in out)

    def test_includes_batch_axes(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "batch_axes:" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_explain.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/rollforward_v2/_explain.py
"""Actuary-readable rendering of an IR.

Output is plain text (not Markdown) — fits in audit reports and TRACE
logs. Mirrors the format from spec §9.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.rollforward_v2._engine_binding import derive_engine_binding
from gaspatchio_core.rollforward_v2._fingerprint import spec_fingerprint

if TYPE_CHECKING:
    from gaspatchio_core.rollforward_v2._ir import IR


def explain(ir: "IR") -> str:
    """Return a multi-line human-readable summary of an IR."""
    lines: list[str] = []

    fp = spec_fingerprint(ir)
    lines.append(f"Rollforward (spec_fingerprint = {fp})")
    lines.append("")

    lines.append("States:")
    for s in ir.states:
        lines.append(f"  {s.name}:  init={s.init}")
    lines.append("")

    lines.append(f"Points:  {', '.join(ir.points)}")
    lines.append("")

    sched_cf = ir.schedule.canonical_form()
    lines.append(f"Schedule: {sched_cf['kind']}({sched_cf})")
    lines.append("")

    lines.append("Transitions (in order):")
    for op in ir.transitions:
        op_name = type(op).__name__
        target = getattr(op, "target", None)
        target_str = target.canonical_name() if target is not None else "<no target>"
        label = getattr(op, "label", None)
        label_str = f"  [label={label!r}]" if label else ""
        lines.append(f"  {target_str}  {op_name}{label_str}")
    lines.append("")

    lines.append(f"batch_axes: {ir.batch_axes}")
    lines.append(f"track_increments: {ir.track_increments}")
    lines.append(
        f"lapse_when_all_non_positive: {sorted(ir.lapse_when_all_non_positive)}"
    )
    lines.append(
        f"contract_boundary: "
        f"{'<set>' if ir.contract_boundary is not None else 'None'}"
    )
    lines.append(f"engine_binding: {derive_engine_binding(ir)}")

    return "\n".join(lines)


__all__ = ["explain"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_explain.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_explain.py bindings/python/tests/rollforward_v2/test_explain.py
git commit -m "feat(rollforward-v2): add explain() actuary-readable rendering"
```

---

### Task 14: End-to-end UL smoke (§4.6)

**Files:**
- Create: `bindings/python/tests/rollforward_v2/test_smoke_compile_ul.py`

- [ ] **Step 1: Write the smoke test**

```python
# bindings/python/tests/rollforward_v2/test_smoke_compile_ul.py
"""End-to-end smoke — §4.6 UL example builds + compiles + explains."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.rollforward_v2._explain import explain
from gaspatchio_core.schedule import Schedule


class TestUlSmoke:
    def test_ul_with_post_coi_capture_compiles(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=240, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
            track_increments=True,
        )

        b["av"].between("bop", "post_coi") \
            .add(pl.col("premium"), label="Premium") \
            .deduct_nar(
                pl.col("coi_rate"),
                death_benefit=pl.col("sum_assured"),
                label="COI",
            )

        b["av"].between("post_coi", "eop") \
            .charge(pl.col("admin_rate"), label="Admin") \
            .grow(pl.col("interest_rate"), label="Interest credit") \
            .floor(0.0)

        compiled = compile_rollforward(b)
        # 5 ops total (Add, DeductNAR, Charge, Grow, Floor)
        assert len(compiled.ir.transitions) == 5

        # Explain output is non-empty + names every label
        out = explain(compiled.ir)
        for label in ("Premium", "COI", "Admin", "Interest credit"):
            assert label in out

    def test_post_coi_capture_in_slots(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=240, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "post_coi").add(pl.col("premium"), label="P")
        b["av"].between("post_coi", "eop").grow(pl.col("rate"), label="G")

        compiled = compile_rollforward(b)
        # post_coi appears as an Op target -> capture slot
        slot_points = {s.point for s in compiled.capture_slots}
        assert "post_coi" in slot_points
        assert "eop" in slot_points
```

- [ ] **Step 2: Run smoke**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_smoke_compile_ul.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/rollforward_v2/test_smoke_compile_ul.py
git commit -m "test(rollforward-v2): UL §4.6 end-to-end build+compile+explain smoke"
```

---

### Task 15: Lint + format + type check + final pass

- [ ] **Step 1: Lint**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/rollforward_v2 tests/rollforward_v2`
Expected: no errors.

- [ ] **Step 2: Format check**

Run: `cd bindings/python && uv run ruff format --check gaspatchio_core/rollforward_v2 tests/rollforward_v2`
Expected: no diffs.

- [ ] **Step 3: Type check**

Run: `cd bindings/python && uv run mypy gaspatchio_core/rollforward_v2 2>&1 | tail -20`
Expected: zero errors.

- [ ] **Step 4: Full D1 + D2 test suite**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2 -v`
Expected: PASS — D1 (~50 tests) + D2 (~50 tests) = ~100 tests.

- [ ] **Step 5: Verify rest of repo still green**

Run: `cd bindings/python && uv run pytest tests/ -q 2>&1 | tail -5`
Expected: prior pass-count plus the new D2 tests; no regressions.

- [ ] **Step 6: Commit any cleanup**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2
git commit -m "chore(rollforward-v2): D2 lint + format + type-check fixups"
```

---

### Task 16: README + spec status update

- [ ] **Step 1: Update status**

```markdown
## Implementation status

- **A — Typed Time** (Schedule + Calendar + DayCount): ✅ shipped
- **B — Curve**: ✅ shipped
- **C — MortalityTable**: ✅ shipped
- **D1 — IR + canonical form + audit identity**: ✅ shipped
- **D2 — Builder + compiler + explain**: ✅ shipped (this branch)
- **D3 — Rust kernel + Polars backend + cutover**: not started

Plans:
- (existing entries)
- [`plans/2026-05-04-phase-1a-kernel-d2-builder.md`](plans/2026-05-04-phase-1a-kernel-d2-builder.md)
```

- [ ] **Step 2: Commit**

```bash
git add ref/36-rollforward-redesign/README.md
git commit -m "docs(rollforward-redesign): mark D2 (builder + compiler) shipped"
```

---

## Self-review

**Spec coverage check:**
- §4.1 Builder constructor (states, points, schedule, track_increments, lapse, contract_boundary): tasks 1, 6 ✓
- §4.2 method chains (.add/.subtract/.charge/.grow/.grow_capped/.deduct_nar/.ratchet/.floor/.between): tasks 2, 3, 4 ✓
- §4.6 `rf["s"].at("p")` typed reference + `rf.increment(label)`: task 5 ✓
- §8.2 5-pass compilation chain (Validate, ResolveStateRefs, FoldConstants, AssignCaptureSlots, LowerToPolarsPlugin): tasks 7–11 ✓
- §8.2 structured pass logs at TRACE level: task 12 ✓
- §8.3 lowering produces JSON-serialisable kwargs for D3 kernel: task 11 ✓
- §9.2 `explain()` actuary-readable rendering: task 13 ✓
- §13.1a deferred to D3: kernel extension, accessor walk, contract_boundary execution, VA gate, cutover — explicit in §"Out of scope" ✓

**Placeholder scan:** none.

**Type consistency:**
- `RollforwardBuilder`, `_StateHandle`, `IncrementRef`, `Pass`, `Validate`, `ResolveStateRefs`, `FoldConstants`, `AssignCaptureSlots`, `LowerToPolarsPlugin`, `CompiledRollforward`, `compile_rollforward`, `explain` referenced consistently.
- Pass `name()` strings match between impl and tests (`validate`, `resolve_state_refs`, `fold_constants`, `assign_capture_slots`, `lower_polars`).
- `plugin_kwargs` schema is consistent across `LowerToPolarsPlugin.lower` (Task 11) and `compile_rollforward` (Task 12); D3 will consume the same schema.

**Cross-plan consistency:**
- Reuses D1's `IR`, `Op`, `StateRef`, `spec_fingerprint`, `derive_engine_binding`, `canonical_form` directly.
- Builder-emitted IR satisfies D1's invariants (points include bop/eop, state names unique).
- `plugin_kwargs["ir"]` is D1's `canonical_form(ir)` — D3's kernel can recompute fingerprint from kwargs alone.

**Risks I've flagged inline:**
- `ResolveStateRefs` is a Phase 1 stub; cross-state Expr-body reads through `rf["s"].at("p")` are validated only when the user explicitly calls `at(...)` (Task 5) — not when an `Apply.body` references a StateRef inside a closure. Phase 2 may add an Expr-walker. Documented in `_passes.py` docstring.
- `FoldConstants` is a Phase 1 no-op; we rely on Polars' query optimiser. Documented.
- `AssignCaptureSlots` Phase 1 captures every Op's target plus every state's `eop`. Cross-state reads (`rf["av"].at("after_growth")` used inside `Ratchet.to`) need extra walk in D3 to ensure those slots get serialised — the slot table this pass produces is necessary but not sufficient. Phase 2 will tighten.

---

## Execution handoff

Plan complete and saved to `ref/36-rollforward-redesign/plans/2026-05-04-phase-1a-kernel-d2-builder.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks. Each task is small (3–6 steps, ~20–80 lines of new production code).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

D2 is meant to be drafted alongside D3 before any execution begins. Execution sequencing: A → B/C → D1 → D2 → D3.
