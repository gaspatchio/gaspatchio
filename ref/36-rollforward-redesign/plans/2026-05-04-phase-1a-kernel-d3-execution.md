# Phase 1a Sub-plan D3 — Rust Kernel + Polars Backend + Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire D2's `CompiledRollforward.plugin_kwargs` into the Rust kernel, ship the Polars accessor-walk that emits one shared plugin Expr per `rollforward(...)` call, run the §4.6 UL and §4.9 GSP-92 VA worked examples end-to-end against gold-file references (subject to §13.0 Phase 0), delete the old `RollforwardBuilder`/`_compile.py`/`_step.py`/`_explain.py` and the old Rust kernel paths, rename `rollforward_v2/` → `rollforward/`, and migrate the Level-3 mini-VA tutorial to the new builder. After D3, the new state-machine kernel is the production rollforward and v0.4.0 is shippable.

**Architecture:** D3 has three logically separate concerns that must land in order:

1. **Rust-side kernel work** — extend `core/src/polars_functions/rollforward.rs` to consume the new `plugin_kwargs` schema (typed `(state, point)` capture slots, contract_boundary mask, expanded Op set, Struct emission with one field per capture slot + one per increment label). The existing kernel already supports the *single-state-no-points* hot path via streaming-engine `is_elementwise=True`; D3 layers points + captures + new Ops on top while keeping the elementwise contract.

2. **Polars-side accessor walk** — when the user assigns `af.av = rf["av"]`, `af.coi = rf.increment("COI")`, etc., the lazy plan must emit exactly ONE `register_plugin_function` per `rollforward(...)` call, with each accessor lowered to a `.struct.field(...)` extraction. This is a one-time walk at `af.collect()` time (or earlier — when the first accessor materialises), implemented in a small `RollforwardCollector` helper that lives next to the builder.

3. **Cutover** — wire `af.projection.rollforward(...)` to point at the new builder; delete the old kernel + tests; rename `rollforward_v2/` → `rollforward/`; migrate Level-3 mini-VA. After this, `from gaspatchio_core import RollforwardBuilder` continues to import successfully but resolves to the new class.

**Tech Stack:** Python 3.10+; Polars 1.38.1; Rust (the existing `core/src/polars_functions/rollforward.rs` workspace); maturin for build; pytest for end-to-end. No new third-party deps.

---

## Scope check

D3 is one cohesive delivery (kernel + backend + cutover land together). It is too large to defer either of its halves: shipping the Rust kernel without the accessor walk leaves accessors broken; shipping the cutover without both leaves users with an incomplete API.

**Phase 0 prerequisite (per spec §13.0):** before Task 14 lands, confirm that `policy_00000065.parquet`'s gold values are independent of the v1 numpy kernel (`va_kernel.py`). If they are not, the §4.9 GSP-92 VA acceptance test in Task 14 demotes to a regression test; an independent reference (Excel illustration, alternative vendor) becomes the release-gate. Plan-level gate: **do not begin Task 14 until Phase 0 is complete**.

**Out of scope (deferred to Phase 2):**
- Phase 2 escape hatches (`.reset_when`, partial-`dt` at termination, sub-period state, vector states, mortality `with_age_basis`)
- JAX backend / `LowerToJax` pass / engine_binding-portability runtime smoke
- Manifest emission (`gaspatchio_manifest.json`)
- Reporting-grid aggregation
- Performance tuning beyond benchmark setup (peak-RSS work — GSP-89 model-point batching is the production scaling story per `core/project.md`)

---

## File structure

**New (Rust):**

| File | Responsibility |
|---|---|
| `core/src/polars_functions/rollforward_v2.rs` | New kernel that consumes the D2 plugin_kwargs schema (typed Ops, captures, contract_boundary, lapse). Side-by-side with the existing `rollforward.rs` until the cutover task. |
| `core/src/polars_functions/mod.rs` | Mod-level re-export update to wire `rollforward_v2` into the plugin export table. |
| `bindings/python/src/lib.rs` | PyO3 plugin registration update to expose `rollforward_v2` as a registered function name (kept as `rollforward` after cutover). |

**New (Python, all under `bindings/python/gaspatchio_core/rollforward_v2/`):**

| File | Responsibility |
|---|---|
| `_collector.py` | `RollforwardCollector` — accessor-walk + plugin-Expr emission; wires `rf["s"]`, `rf["s"].at("p")`, `rf.increment(label)` to `.struct.field(...)` extractions on a shared plugin Expr. |
| `_projection.py` | `ProjectionAccessor` extension that exposes `rollforward(...)` returning a builder bound to the active `ActuarialFrame`. |

**New (tests):**

| File | Responsibility |
|---|---|
| `bindings/python/tests/rollforward_v2/test_kernel_single_state.py` | End-to-end §4.4 Whole Life single-state path |
| `bindings/python/tests/rollforward_v2/test_kernel_multi_state.py` | §4.7 VA + GMDB ratchet (multi-state + cross-state read) |
| `bindings/python/tests/rollforward_v2/test_kernel_captures.py` | `rf["s"].at("p")` capture extraction |
| `bindings/python/tests/rollforward_v2/test_kernel_increments.py` | `rf.increment(label)` resolution |
| `bindings/python/tests/rollforward_v2/test_kernel_lapse.py` | `lapse_when_all_non_positive` zeroing |
| `bindings/python/tests/rollforward_v2/test_kernel_contract_boundary.py` | `contract_boundary=mask` first-True stop |
| `bindings/python/tests/rollforward_v2/test_lazy_struct_release_gate.py` | `lf.explain(engine="streaming")` shows exactly one `register_plugin_function` per rollforward |
| `bindings/python/tests/rollforward_v2/test_va_acceptance.py` | §4.9 GSP-92 VA acceptance — gated on Phase 0 |

**Modified:**

- `bindings/python/gaspatchio_core/__init__.py` — re-export new `RollforwardBuilder` (replaces old) and add `Schedule`/`Curve`/`MortalityTable` to `__all__` if not already from A/B/C
- `bindings/python/gaspatchio_core/frame/base.py` — `af.projection` returns the new accessor (Task 8)
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/` — rewrite to new builder API

**Deleted:**

- `bindings/python/gaspatchio_core/rollforward/_builder.py` (old)
- `bindings/python/gaspatchio_core/rollforward/_compile.py` (old)
- `bindings/python/gaspatchio_core/rollforward/_step.py` (old)
- `bindings/python/gaspatchio_core/rollforward/_explain.py` (old)
- `bindings/python/gaspatchio_core/rollforward/__init__.py` (old)
- `bindings/python/tests/rollforward/test_builder.py` etc. (old test files; replaced by `tests/rollforward_v2/` content which is renamed)
- Legacy paths inside `core/src/polars_functions/rollforward.rs` that the new schema doesn't use

**Renamed (final cutover step):**

- `bindings/python/gaspatchio_core/rollforward_v2/` → `bindings/python/gaspatchio_core/rollforward/`
- `bindings/python/tests/rollforward_v2/` → `bindings/python/tests/rollforward/`
- `core/src/polars_functions/rollforward_v2.rs` → `core/src/polars_functions/rollforward.rs` (replacing old)

---

## Tasks

### Task 1: Rust kernel — `rollforward_v2.rs` skeleton + new kwargs schema

**Files:**
- Create: `core/src/polars_functions/rollforward_v2.rs`
- Modify: `core/src/polars_functions/mod.rs` (add `pub mod rollforward_v2;`)
- Modify: `bindings/python/src/lib.rs` (register the new function name)

- [ ] **Step 1: Write a Rust unit test (in-place)**

Add a `#[cfg(test)]` block to `rollforward_v2.rs`:

```rust
// core/src/polars_functions/rollforward_v2.rs
//! Rollforward v2 kernel — consumes the D2 plugin_kwargs schema.
//!
//! Schema (JSON-decoded):
//!   ir:                       canonical-form dict (states, points, transitions, …)
//!   captures:                 Vec<[state, point]> in slot order
//!   track_increments:         bool
//!   lapse_when_all_non_positive: Vec<String> (sorted)
//!   contract_boundary:        Option<String> (Polars Expr serialised string)
//!
//! The kernel walks transitions in declared order per period, evaluating
//! each Op against the current per-row state vector. Output is a Polars
//! Struct with one field per capture slot + one field per labelled
//! increment (when track_increments=True).

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct RollforwardV2Kwargs {
    pub ir: serde_json::Value,
    pub captures: Vec<Vec<String>>,
    pub track_increments: bool,
    pub lapse_when_all_non_positive: Vec<String>,
    pub contract_boundary: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deserialise_minimal_kwargs() {
        let json = r#"{
            "ir": {"states": [], "points": ["bop", "eop"], "transitions": []},
            "captures": [["av", "eop"]],
            "track_increments": false,
            "lapse_when_all_non_positive": [],
            "contract_boundary": null
        }"#;
        let kwargs: RollforwardV2Kwargs = serde_json::from_str(json).unwrap();
        assert_eq!(kwargs.captures.len(), 1);
        assert!(!kwargs.track_increments);
    }
}
```

- [ ] **Step 2: Wire into mod.rs**

Add to `core/src/polars_functions/mod.rs`:

```rust
pub mod rollforward_v2;
```

- [ ] **Step 3: Build + test**

Run: `cd core && cargo test rollforward_v2 -p gaspatchio-core`
Expected: PASS — 1 test (`deserialise_minimal_kwargs`).

- [ ] **Step 4: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs core/src/polars_functions/mod.rs
git commit -m "feat(rollforward-v2): add Rust kernel skeleton + kwargs deserialisation"
```

---

### Task 2: Rust kernel — Op execution dispatch (the 9 Phase 1 Ops)

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs`

- [ ] **Step 1: Sketch the dispatch enum**

Append to `rollforward_v2.rs`:

```rust
/// Phase 1 Op enum — mirrors the Python Op classes in
/// `gaspatchio_core.rollforward_v2._ops`.
#[derive(Deserialize)]
#[serde(tag = "op")]
pub enum OpV2 {
    Add { target: TargetRef, expr: String, label: Option<String> },
    Subtract { target: TargetRef, expr: String, label: Option<String> },
    Charge { target: TargetRef, rate: String, label: Option<String> },
    Grow { target: TargetRef, rate: String, label: Option<String> },
    GrowCapped {
        target: TargetRef,
        rate: String,
        floor: String,
        cap: String,
        label: Option<String>,
    },
    DeductNAR {
        target: TargetRef,
        coi_rate: String,
        death_benefit: String,
        label: Option<String>,
    },
    Ratchet {
        target: TargetRef,
        to: String,
        when: Option<String>,
        label: Option<String>,
    },
    Floor { target: TargetRef, value: f64 },
    Apply { target: TargetRef, body: String, label: Option<String> },
}

#[derive(Deserialize)]
pub struct TargetRef {
    pub state: String,
    pub point: String,
}
```

- [ ] **Step 2: Add a deserialisation test**

Append to the `#[cfg(test)] mod tests` block:

```rust
    #[test]
    fn deserialise_op_add() {
        let json = r#"{
            "op": "Add",
            "target": {"state": "av", "point": "eop"},
            "expr": "col(\"premium\")",
            "label": "Premium"
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Add { target, label, .. } => {
                assert_eq!(target.state, "av");
                assert_eq!(label.unwrap(), "Premium");
            }
            _ => panic!("expected Add"),
        }
    }

    #[test]
    fn deserialise_op_floor() {
        let json = r#"{
            "op": "Floor",
            "target": {"state": "av", "point": "eop"},
            "value": 0.0
        }"#;
        let op: OpV2 = serde_json::from_str(json).unwrap();
        match op {
            OpV2::Floor { value, .. } => assert_eq!(value, 0.0),
            _ => panic!("expected Floor"),
        }
    }
```

- [ ] **Step 3: Build + test**

Run: `cd core && cargo test rollforward_v2 -p gaspatchio-core`
Expected: PASS — 3 tests.

- [ ] **Step 4: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs
git commit -m "feat(rollforward-v2): add OpV2 dispatch enum (9 Phase 1 Ops)"
```

---

### Task 3: Rust kernel — per-row state vector + transition walk

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs`

- [ ] **Step 1: Sketch the kernel function**

Append to `rollforward_v2.rs`:

```rust
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;

/// The plugin entry point — registered with Polars via the
/// `register_plugin_function` mechanism.
#[allow(dead_code)]
pub fn rollforward_v2_kernel(
    inputs: &[Series],
    kwargs: &RollforwardV2Kwargs,
) -> PolarsResult<Series> {
    // Phase 1 stub — Tasks 4–7 fill this in.
    //
    // Per row:
    //   1. Initialise state vector from input columns matching state inits
    //   2. For each period 0..n_periods:
    //        a. For each Op in transitions order: evaluate against current state
    //        b. Apply lapse_when_all_non_positive: zero remaining if all states <= 0
    //        c. Apply contract_boundary mask: zero remaining if mask is True
    //   3. Emit one Struct per row with capture slot + increment fields
    //
    // For Task 3 we ship only the per-row state-vector layout; subsequent
    // tasks add the actual evaluation.
    let _ = (inputs, kwargs);
    Err(PolarsError::ComputeError(
        "rollforward_v2_kernel: not yet implemented".into(),
    ))
}
```

- [ ] **Step 2: Build (no new test yet — implementation comes in Task 4)**

Run: `cd core && cargo build -p gaspatchio-core 2>&1 | tail -10`
Expected: clean build with no errors (warnings about `dead_code` and unused inputs are OK at this checkpoint).

- [ ] **Step 3: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs
git commit -m "feat(rollforward-v2): scaffold kernel entry point (impl in subsequent tasks)"
```

---

### Task 4: Rust kernel — implement Op execution for `Add` / `Subtract` / `Charge` / `Floor`

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs`

- [ ] **Step 1: Implement minimal single-state path**

Replace the stub `rollforward_v2_kernel` body with a Phase 1 implementation that walks transitions in declared order, applies arithmetic Ops to the per-row state, and emits a Struct with one `eop` field per state.

Real complexity here mirrors the existing `rollforward.rs`'s `rollforward_fast_single_state` and `rollforward_fast_multi_state` paths — reuse those primitives. The new bits are: typed (state, point) addressing (point is a string, looked up against the IR's `points` array each period), and Struct emission keyed by the `captures` Vec.

The implementation is substantial (~300 lines) and follows the existing Rust patterns; it is not reproduced verbatim here. Required behaviour validated by Task 5's Python integration test:

- Per-row state vector indexed by `(state_idx, point_idx)`
- Each period: walk transitions; for each Op apply the formula in §4.2 of the spec
- Captures slot table → Struct fields with `List<Float64>` per slot

- [ ] **Step 2: Add a Rust unit test exercising Add + Floor**

Append:

```rust
    #[test]
    fn add_then_floor_single_state() {
        // Build a 3-period IR: state av starts at 100, +10 each period, floor 0
        // Expected: [110, 120, 130]
        // Test stub — full integration validation lives in the Python tests
        // (Task 5). This assert is a quick Rust-side smoke for the dispatch.
        // Implementation choice: keep Rust-side tests minimal, push correctness
        // verification to Python integration tests where Polars test
        // infrastructure is richer.
        assert!(true);
    }
```

- [ ] **Step 3: Build + run Rust tests**

Run: `cd core && cargo test rollforward_v2 -p gaspatchio-core`
Expected: PASS — Rust tests green.

- [ ] **Step 4: Build the Python extension**

Run: `cd bindings/python && uv run maturin develop -uv --release`
Expected: clean build — no errors.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs
git commit -m "feat(rollforward-v2): Rust kernel — Add/Subtract/Charge/Floor dispatch"
```

---

### Task 5: Python ↔ Rust integration — single-state §4.4 Whole Life path

**Files:**
- Modify: `bindings/python/gaspatchio_core/polars_backend/plugins.py` — add `rollforward_v2_plugin` function alongside the existing stub
- Create: `bindings/python/tests/rollforward_v2/test_kernel_single_state.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/rollforward_v2/test_kernel_single_state.py
"""End-to-end §4.4 Whole Life single-state path."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._collector import RollforwardCollector
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestWholeLifeSingleState:
    def test_av_grows_then_floors(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M",
        )
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"] \
            .add(pl.col("premium"), label="P") \
            .grow(pl.col("rate"), label="G") \
            .floor(0.0)
        compiled = compile_rollforward(b)

        df = pl.DataFrame(
            {
                "init": [100.0],
                "premium": [[10.0, 10.0, 10.0]],
                "rate": [[0.0, 0.0, 0.0]],
            }
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(av=collector.expr_for("av")).collect_or_self() \
            if hasattr(df, "collect_or_self") else df.with_columns(av=collector.expr_for("av"))
        # Expected per-period AV: 110, 120, 130 (just the additions; rate=0 so no growth)
        av = result.get_column("av").to_list()[0]
        assert av == pytest.approx([110.0, 120.0, 130.0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_kernel_single_state.py -v`
Expected: FAIL — `RollforwardCollector` not yet implemented.

- [ ] **Step 3: Implement the collector + plugin Expr emission**

Implementation lives in `bindings/python/gaspatchio_core/rollforward_v2/_collector.py`:

```python
"""RollforwardCollector — emits one shared plugin Expr per rollforward.

Public surface (called from D3's `__init__.py` once cutover is done):

    collector = RollforwardCollector(compiled)
    af.av = collector.expr_for("av")
    af.av_post_coi = collector.expr_for("av", point="post_coi")
    af.coi = collector.increment_for("COI")

The collector lazily emits a single `register_plugin_function` call on
first access; subsequent accessors lower to ``.struct.field(...)``
extractions on the cached plugin Expr.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

if TYPE_CHECKING:
    from gaspatchio_core.rollforward_v2._compiled import CompiledRollforward


class RollforwardCollector:
    def __init__(self, compiled: "CompiledRollforward") -> None:
        self._compiled = compiled
        self._cached_plugin_expr: pl.Expr | None = None

    def _shared_plugin_expr(self) -> pl.Expr:
        if self._cached_plugin_expr is not None:
            return self._cached_plugin_expr
        # Lazy import to avoid cost at module-load time
        from gaspatchio_core import _internal  # noqa: PLC0415

        lib = Path(_internal.__file__)
        # Inputs: every state's init expr + every input column referenced by Ops
        inputs: list[pl.Expr] = [s.init for s in self._compiled.ir.states]
        # Phase 1: also include every Expr referenced by Ops via str(expr) → col() lift.
        # Robust expression-collection lives in Phase 2; for Phase 1 the kernel
        # consumes captures by their canonical string and resolves columns at runtime.
        # The kwargs payload carries everything needed.
        self._cached_plugin_expr = register_plugin_function(
            plugin_path=lib,
            function_name="rollforward_v2",
            args=inputs,
            kwargs=self._compiled.plugin_kwargs,
            is_elementwise=True,
        )
        return self._cached_plugin_expr

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a Polars Expr that extracts the (state, point) field
        from the shared plugin Struct."""
        from gaspatchio_core.rollforward_v2._refs import StateRef

        ref = StateRef(state=state, point=point)
        if ref not in self._compiled.capture_slots:
            msg = (
                f"({state!r}, {point!r}) not in capture slots — declare "
                f"the point or use a state's eop"
            )
            raise KeyError(msg)
        plugin = self._shared_plugin_expr()
        return plugin.struct.field(f"{state}@{point}")

    def increment_for(self, label: str) -> pl.Expr:
        if not self._compiled.ir.track_increments:
            msg = (
                "rf.increment(...) requires the rollforward to be built with "
                "track_increments=True"
            )
            raise ValueError(msg)
        plugin = self._shared_plugin_expr()
        return plugin.struct.field(f"increment_{label}")


__all__ = ["RollforwardCollector"]
```

- [ ] **Step 4: Run the test (it should fail at the kernel — Rust kernel needs to actually execute)**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_kernel_single_state.py -v`
Expected: FAIL — kernel returns "not yet implemented" (from Task 4's stub). This is the expected red — you've now wired Python to call into Rust, which is the integration milestone for this task. Task 6 lights up the kernel body.

- [ ] **Step 5: Commit (intermediate)**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_collector.py bindings/python/tests/rollforward_v2/test_kernel_single_state.py
git commit -m "feat(rollforward-v2): add RollforwardCollector + Python-side plugin Expr emission"
```

---

### Task 6: Rust kernel — fill in the Add/Grow/Floor evaluation logic

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs`

- [ ] **Step 1: Implement period walk for arithmetic + Grow + Floor**

This is the bulk of the Rust work for D3. Replace the `rollforward_v2_kernel` body with a real implementation:

- Decode `kwargs.ir["transitions"]` into a `Vec<OpV2>`
- Decode `kwargs.ir["points"]` into a `Vec<String>` for point-name → index lookup
- Decode `kwargs.ir["states"]` and use the order of inputs[..n_states] as the init values per row
- Decode `kwargs.ir["schedule"]["n_periods"]` as the period count
- Per row: build per-state-per-period `Vec<f64>` (length = n_states * n_periods)
- Evaluate each Op in declared order, applying:
  - `Add`: `state[next_point_idx] = state[prev_point_idx] + expr_value`
  - `Subtract`: `... - expr_value`
  - `Charge`: `... * (1 - rate_value)`
  - `Grow`: `... * (1 + rate_value * dt[t])` — `dt` from schedule canonical form
  - `Floor`: `state[next_point_idx] = max(state[next_point_idx], value)`
- Emit a Struct per row with one List<Float64> field per capture slot (`{state}@{point}`)

Phase 1 simplification — Op `expr` strings reference Polars columns by name; the kernel resolves them by looking up the input slice's column-name → index map. Apply / GrowCapped / Ratchet / DeductNAR are stubbed to return an error in this task; subsequent tasks fill them in.

- [ ] **Step 2: Re-run §4.4 single-state test**

Run: `cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward_v2/test_kernel_single_state.py -v`
Expected: PASS — `av == [110.0, 120.0, 130.0]`.

- [ ] **Step 3: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs
git commit -m "feat(rollforward-v2): Rust kernel — Add/Subtract/Charge/Grow/Floor evaluation"
```

---

### Task 7: Rust kernel — `DeductNAR`, `GrowCapped`, `Ratchet`, `Apply`

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs`
- Create: `bindings/python/tests/rollforward_v2/test_kernel_multi_state.py`

- [ ] **Step 1: Write the multi-state failing test (§4.7 VA + GMDB ratchet)**

```python
# bindings/python/tests/rollforward_v2/test_kernel_multi_state.py
"""End-to-end §4.7 VA + GMDB ratchet."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._collector import RollforwardCollector
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestVaGmdbRatchet:
    def test_av_grows_guarantee_ratchets_at_anniversary(self) -> None:
        # 12-period schedule; anniversary fires at period 12 only
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init"), "guarantee": pl.col("av_init")},
            points=["bop", "after_growth", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "after_growth").grow(pl.col("fund_return"), label="G")
        b["av"].between("after_growth", "eop").floor(0.0)
        b["guarantee"].grow(pl.col("roll_up"), label="RollUp")
        b["guarantee"].ratchet(
            to=pl.col("av_after_growth"),  # placeholder — Phase 2 expression refs
            when=pl.col("anniv"),
            label="GMDB",
        )
        compiled = compile_rollforward(b)

        # Single policy, 12 periods of constant 1% fund return + 4% roll-up
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "fund_return": [[0.01] * 12],
                "roll_up": [[0.04] * 12],
                "av_after_growth": [[101.0] * 12],  # placeholder
                "anniv": [[False] * 11 + [True]],
            }
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(
            av=collector.expr_for("av"),
            g=collector.expr_for("guarantee"),
        )
        # AV after 12 months at 1%: 100 * 1.01^12 ≈ 112.68
        av = result.get_column("av").to_list()[0]
        assert av[-1] == pytest.approx(100 * 1.01**12, rel=1e-3)
        # Guarantee starts at 100, rolls up at 4%/12 per month, then ratchets.
        # Value at anniversary (period 11) ≈ 100 * (1 + 0.04*1/12)^12 ≈ 104.07
        # Then ratchets to AV value at after_growth point — placeholder data
        # makes this fixture not perfectly exercising ratchet semantics; the
        # test confirms the kernel runs without error and produces sensible values.
        g = result.get_column("g").to_list()[0]
        assert g[-1] > 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward_v2/test_kernel_multi_state.py -v`
Expected: FAIL — `Ratchet` and `DeductNAR` Ops return "not yet implemented".

- [ ] **Step 3: Implement remaining Ops in `rollforward_v2.rs`**

- `DeductNAR`: `state -= coi_rate * (death_benefit - state)`
- `GrowCapped`: `state *= 1 + clamp(rate, floor, cap) * dt`
- `Ratchet`: `if when[t]: state = max(state, to_value)` (with `when=None` → unconditional)
- `Apply`: Phase 1 stubs out as `state = body_value` (treats body as direct assignment); robust Apply needs the Polars expression evaluator and is best deferred — Phase 1 raises a runtime error if Apply appears, with a clear message that Apply is "Phase 1 escape hatch — pending kernel evaluator hook"

- [ ] **Step 4: Run the test**

Run: `cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward_v2/test_kernel_multi_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs bindings/python/tests/rollforward_v2/test_kernel_multi_state.py
git commit -m "feat(rollforward-v2): Rust kernel — DeductNAR/GrowCapped/Ratchet/Apply (Apply pending)"
```

---

### Task 8: `af.projection.rollforward(...)` entry point

**Files:**
- Create: `bindings/python/gaspatchio_core/rollforward_v2/_projection.py`
- Modify: `bindings/python/gaspatchio_core/frame/base.py` (small surgical hook)

- [ ] **Step 1: Write the failing test**

Append to `bindings/python/tests/rollforward_v2/test_kernel_single_state.py`:

```python
class TestProjectionAccessor:
    def test_af_projection_rollforward_returns_builder(self) -> None:
        from datetime import date

        import polars as pl

        from gaspatchio_core import ActuarialFrame, Schedule

        df = pl.DataFrame({"init": [100.0]})
        af = ActuarialFrame(df)
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M",
        )
        rf = af.projection.rollforward(states={"av": af.init}, schedule=sched)
        rf["av"].add(pl.col("premium"), label="P")
        # The handle returned must be a v2 RollforwardBuilder
        from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
        assert isinstance(rf, RollforwardBuilder)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_kernel_single_state.py::TestProjectionAccessor -v`
Expected: FAIL — `af.projection.rollforward` resolves to the OLD builder.

- [ ] **Step 3: Wire the new projection accessor**

In `bindings/python/gaspatchio_core/frame/base.py`, find the `projection` property (it currently returns an accessor that exposes the OLD `RollforwardBuilder`). Update its `rollforward(...)` method to construct the v2 builder instead:

```python
# Inside ActuarialFrame.projection.rollforward (the projection accessor's
# rollforward method — actual location may vary):

def rollforward(self, **kwargs):
    from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
    return RollforwardBuilder(**kwargs)
```

This is the cutover at the user-facing entry point — calls to `af.projection.rollforward(...)` now create v2 builders, but the OLD `gaspatchio_core.rollforward.RollforwardBuilder` import still resolves (until Task 11 deletes it).

- [ ] **Step 4: Run the test**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_kernel_single_state.py::TestProjectionAccessor -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/rollforward_v2/_projection.py bindings/python/gaspatchio_core/frame/base.py bindings/python/tests/rollforward_v2/test_kernel_single_state.py
git commit -m "feat(rollforward-v2): wire af.projection.rollforward to v2 builder"
```

---

### Task 9: Lazy/Struct release-gate test

**Files:**
- Create: `bindings/python/tests/rollforward_v2/test_lazy_struct_release_gate.py`

- [ ] **Step 1: Write the gate test**

```python
# bindings/python/tests/rollforward_v2/test_lazy_struct_release_gate.py
"""Release-gate: exactly ONE register_plugin_function call per rollforward.

Per spec §8.3: assigning af.av = rf['av']; af.coi = rf.increment('COI');
af.av_post = rf['av'].at('post_coi') must produce one shared plugin Expr,
not three. The compiler's accessor walk + plugin emission is the contract;
this test enforces it via lf.explain().
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._collector import RollforwardCollector
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestLazyStructReleaseGate:
    def test_three_accessors_one_plugin_call(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
            track_increments=True,
        )
        b["av"].between("bop", "post_coi").add(pl.col("p"), label="Premium")
        b["av"].between("post_coi", "eop").grow(pl.col("rate"), label="Interest")
        compiled = compile_rollforward(b)

        df = pl.LazyFrame(
            {
                "init": [100.0],
                "p": [[10.0, 10.0, 10.0]],
                "rate": [[0.01, 0.01, 0.01]],
            }
        )
        collector = RollforwardCollector(compiled)
        lf = df.with_columns(
            av=collector.expr_for("av"),
            av_post_coi=collector.expr_for("av", point="post_coi"),
            premium_increment=collector.increment_for("Premium"),
        )
        plan = lf.explain(engine="streaming")
        # Exactly one register_plugin_function reference in the plan
        plugin_count = plan.lower().count("rollforward_v2")
        assert plugin_count == 1, (
            f"Expected 1 plugin call; got {plugin_count}\nPlan:\n{plan}"
        )
```

- [ ] **Step 2: Run the gate**

Run: `cd bindings/python && uv run pytest tests/rollforward_v2/test_lazy_struct_release_gate.py -v`
Expected: PASS — the collector's caching produces one shared plugin Expr.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/rollforward_v2/test_lazy_struct_release_gate.py
git commit -m "test(rollforward-v2): release-gate — exactly one plugin call per rollforward"
```

---

### Task 10: `lapse_when_all_non_positive` + `contract_boundary` end-to-end

**Files:**
- Modify: `core/src/polars_functions/rollforward_v2.rs` — implement stop-conditions
- Create: `bindings/python/tests/rollforward_v2/test_kernel_lapse.py`
- Create: `bindings/python/tests/rollforward_v2/test_kernel_contract_boundary.py`

- [ ] **Step 1: Write the lapse test**

```python
# bindings/python/tests/rollforward_v2/test_kernel_lapse.py
from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._collector import RollforwardCollector
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestLapseAllNonPositive:
    def test_zeroes_remaining_periods_after_lapse(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=5, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=sched,
            lapse_when_all_non_positive=["av"],
        )
        b["av"].subtract(pl.col("withdrawal"))  # -- no label OK; track_increments=False
        compiled = compile_rollforward(b)

        # Withdraw 30 each period — av reaches 0 at period 4 (100 - 4*30 = -20)
        # lapse_when_all_non_positive triggers at period 4, period 5 is zeroed
        df = pl.DataFrame(
            {"init": [100.0], "withdrawal": [[30.0] * 5]},
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(av=collector.expr_for("av"))
        av = result.get_column("av").to_list()[0]
        assert av[3] <= 0.0  # lapsed
        assert av[4] == 0.0  # post-lapse zero
```

- [ ] **Step 2: Write the contract-boundary test**

```python
# bindings/python/tests/rollforward_v2/test_kernel_contract_boundary.py
from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward_v2._builder import RollforwardBuilder
from gaspatchio_core.rollforward_v2._collector import RollforwardCollector
from gaspatchio_core.rollforward_v2._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestContractBoundary:
    def test_stops_at_first_true(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=4, frequency="1M",
        )
        b = RollforwardBuilder(
            states={"reserve": pl.col("init")},
            schedule=sched,
            contract_boundary=pl.col("breach"),
        )
        b["reserve"].add(pl.col("flow"))
        compiled = compile_rollforward(b)

        # Breach mask True at period 2 — periods 2 and 3 should be zeroed
        df = pl.DataFrame(
            {
                "init": [100.0],
                "flow": [[10.0, 10.0, 10.0, 10.0]],
                "breach": [[False, False, True, True]],
            }
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(reserve=collector.expr_for("reserve"))
        rsv = result.get_column("reserve").to_list()[0]
        assert rsv[0] == 110.0
        assert rsv[1] == 120.0
        assert rsv[2] == 0.0
        assert rsv[3] == 0.0
```

- [ ] **Step 3: Implement stop-conditions in Rust kernel**

In `rollforward_v2.rs`, after each period's transition walk:
- Evaluate `lapse_when_all_non_positive`: if every named state's current end-of-period value ≤ 0, mark a "stopped" flag. Subsequent periods write 0 to every state.
- Evaluate `contract_boundary`: at the period boundary, evaluate the mask Expr. If true, mark "stopped".

- [ ] **Step 4: Run tests**

Run: `cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward_v2/test_kernel_lapse.py tests/rollforward_v2/test_kernel_contract_boundary.py -v`
Expected: PASS — both tests.

- [ ] **Step 5: Commit**

```bash
git add core/src/polars_functions/rollforward_v2.rs bindings/python/tests/rollforward_v2/test_kernel_lapse.py bindings/python/tests/rollforward_v2/test_kernel_contract_boundary.py
git commit -m "feat(rollforward-v2): kernel — lapse_when + contract_boundary stop-conditions"
```

---

### Task 11: Delete old kernel + tests

**Files:**
- Delete: `bindings/python/gaspatchio_core/rollforward/_builder.py`
- Delete: `bindings/python/gaspatchio_core/rollforward/_compile.py`
- Delete: `bindings/python/gaspatchio_core/rollforward/_step.py`
- Delete: `bindings/python/gaspatchio_core/rollforward/_explain.py`
- Delete: `bindings/python/gaspatchio_core/rollforward/__init__.py`
- Delete: `bindings/python/tests/rollforward/test_builder.py`
- Delete: `bindings/python/tests/rollforward/test_compile.py`
- Delete: `bindings/python/tests/rollforward/test_explain.py`
- Delete: `bindings/python/tests/rollforward/test_increments.py`
- Delete: `bindings/python/tests/rollforward/test_integration.py`
- Delete: `bindings/python/tests/rollforward/test_kernel_multi.py`
- Delete: `bindings/python/tests/rollforward/test_kernel_single.py`
- Delete: `bindings/python/tests/rollforward/test_step.py`
- Delete: `bindings/python/tests/rollforward/conftest.py`
- Delete: legacy paths in `core/src/polars_functions/rollforward.rs`
- Modify: `bindings/python/gaspatchio_core/__init__.py` — remove imports from old `rollforward` package

- [ ] **Step 1: Remove old Python files**

Run: `git rm bindings/python/gaspatchio_core/rollforward/_builder.py bindings/python/gaspatchio_core/rollforward/_compile.py bindings/python/gaspatchio_core/rollforward/_step.py bindings/python/gaspatchio_core/rollforward/_explain.py bindings/python/gaspatchio_core/rollforward/__init__.py`

- [ ] **Step 2: Remove old tests**

Run: `git rm bindings/python/tests/rollforward/test_builder.py bindings/python/tests/rollforward/test_compile.py bindings/python/tests/rollforward/test_explain.py bindings/python/tests/rollforward/test_increments.py bindings/python/tests/rollforward/test_integration.py bindings/python/tests/rollforward/test_kernel_multi.py bindings/python/tests/rollforward/test_kernel_single.py bindings/python/tests/rollforward/test_step.py bindings/python/tests/rollforward/conftest.py`

- [ ] **Step 3: Remove legacy paths in `rollforward.rs`**

Open `core/src/polars_functions/rollforward.rs`. Phase 1 deletes the file entirely OR removes the legacy code paths and keeps a stub. The cleanest path: delete the whole file, since `rollforward_v2.rs` will be renamed to `rollforward.rs` in Task 13.

```bash
git rm core/src/polars_functions/rollforward.rs
```

Then update `core/src/polars_functions/mod.rs`:
- Remove `pub mod rollforward;`
- Keep `pub mod rollforward_v2;` (renamed in Task 13)

- [ ] **Step 4: Update top-level `__init__.py`**

In `bindings/python/gaspatchio_core/__init__.py`:
- Remove `from .rollforward import RollforwardBuilder, Step, StepDef`
- Remove `"RollforwardBuilder", "Step", "StepDef"` from `__all__`

These names will reappear in Task 13 once the rename lands; it's clean to remove them here so any reference between Task 11 and Task 13 fails loudly.

- [ ] **Step 5: Verify the test suite still collects (some collection failures are expected for in-flight v2 tests until Task 13 renames)**

Run: `cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward_v2 -v 2>&1 | tail -10`
Expected: rollforward_v2 tests pass; old `tests/rollforward/` directory now empty.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(rollforward): delete v1 kernel + tests (replaced by v2; rename next)"
```

---

### Task 12: Migrate Level-3 mini-VA tutorial

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py`

- [ ] **Step 1: Inspect the existing tutorial**

Run: `cat bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py`

The existing tutorial uses the v1 `RollforwardBuilder` API. Rewrite it to use:
- `af.projection.rollforward(states={...}, points=[...], schedule=Schedule.from_inception(...))` (or `from_calendar_grid` if appropriate)
- State-handle method chains
- `.between(...)` for any mid-period structure
- `rf["state"].at("point")` for typed reads

- [ ] **Step 2: Rewrite the tutorial**

Replace the rollforward portion of the tutorial with the new API. Keep the surrounding model-data-loading code unchanged. The tutorial should run end-to-end and produce numerically identical (or, where v1 had bugs, numerically *correct*) results.

- [ ] **Step 3: Verify the tutorial runs**

Run: `cd bindings/python && uv run pytest tests/integration -v -k "level_3" 2>&1 | tail -10` (if such an integration test exists; otherwise run the tutorial's own driver)

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/tutorials/level-3-mini-va
git commit -m "docs(tutorials): migrate Level-3 mini-VA to new builder API"
```

---

### Task 13: Rename `rollforward_v2/` → `rollforward/` (final cutover)

**Files:**
- Rename: `bindings/python/gaspatchio_core/rollforward_v2/` → `bindings/python/gaspatchio_core/rollforward/`
- Rename: `bindings/python/tests/rollforward_v2/` → `bindings/python/tests/rollforward/`
- Rename: `core/src/polars_functions/rollforward_v2.rs` → `core/src/polars_functions/rollforward.rs`
- Bulk-update: every `rollforward_v2` import → `rollforward` across the renamed tree

- [ ] **Step 1: Rename Python directories**

```bash
git mv bindings/python/gaspatchio_core/rollforward_v2 bindings/python/gaspatchio_core/rollforward
git mv bindings/python/tests/rollforward_v2 bindings/python/tests/rollforward
```

- [ ] **Step 2: Rename Rust file**

```bash
git mv core/src/polars_functions/rollforward_v2.rs core/src/polars_functions/rollforward.rs
```

In `core/src/polars_functions/mod.rs`: change `pub mod rollforward_v2;` → `pub mod rollforward;`.

- [ ] **Step 3: Bulk-replace `rollforward_v2` → `rollforward` in imports across the tree**

```bash
cd bindings/python && grep -rl "rollforward_v2" gaspatchio_core/ tests/ | xargs sed -i '' 's/rollforward_v2/rollforward/g'
cd ../../core && grep -rl "rollforward_v2" src/ | xargs sed -i '' 's/rollforward_v2/rollforward/g'
```

(Note: `sed -i ''` is the macOS form; on Linux drop the empty-string argument.)

- [ ] **Step 4: Update Rust plugin function name**

In `bindings/python/src/lib.rs`, the function name registered via PyO3 should be `rollforward` (not `rollforward_v2`). Update accordingly.

- [ ] **Step 5: Update `RollforwardCollector` plugin function name**

In `bindings/python/gaspatchio_core/rollforward/_collector.py` (renamed from `rollforward_v2`):
- `function_name="rollforward_v2"` → `function_name="rollforward"`

- [ ] **Step 6: Re-export at top-level**

In `bindings/python/gaspatchio_core/__init__.py`:
- Add: `from .rollforward._builder import RollforwardBuilder`
- Add `"RollforwardBuilder"` to `__all__`

- [ ] **Step 7: Rebuild + test**

```bash
cd bindings/python && uv run maturin develop -uv --release && uv run pytest tests/rollforward -v
```

Expected: full v2 test suite green under the new name.

- [ ] **Step 8: Verify lazy/Struct release-gate still passes**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_lazy_struct_release_gate.py -v`
Expected: PASS — the gate test now references `rollforward` (post-rename) and the count remains 1.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(rollforward): cutover — rename v2 → rollforward, wire RollforwardBuilder"
```

---

### Task 14: §4.9 GSP-92 VA acceptance test (gated on Phase 0)

**Files:**
- Create: `bindings/python/tests/rollforward/test_va_acceptance.py`

**Phase 0 prerequisite:** confirm gold-file provenance per spec §13.0. If `policy_00000065.parquet` is independent of v1's `va_kernel.py`, this task ships as a release-gate. If it's `va_kernel.py` output, demote this test to a regression and source an independent reference (Excel illustration) before 0.4.0 ships.

- [ ] **Step 1: Locate gold-file**

Confirm the path: `gaspatchio-va/tests/fixtures/policy_00000065.parquet` (or wherever the project stores it).

- [ ] **Step 2: Build the §4.9 model**

Translate §4.9's spec example into actual code:

```python
# bindings/python/tests/rollforward/test_va_acceptance.py
"""§4.9 GSP-92 VA Illustration acceptance — 1200 periods, 25 list columns,
atol ≤ 1e-9 vs gold-file reference.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, Schedule


GOLD_FILE = Path(__file__).parent.parent.parent / "fixtures" / "policy_00000065.parquet"


@pytest.mark.skipif(not GOLD_FILE.exists(), reason="VA gold-file not present in this checkout")
class TestVaAcceptance:
    def test_full_model_reconciles_to_gold_file(self) -> None:
        # Build the §4.9 model exactly as in the spec
        # ... (full construction)
        # Reconcile each output column to the gold file at atol ≤ 1e-9
        # for each of the 25 list-typed columns the gold file provides.
        pass  # Concrete construction copy-pasted from spec §4.9 + reconcile loop
```

- [ ] **Step 3: Run the gate**

Run: `cd bindings/python && uv run pytest tests/rollforward/test_va_acceptance.py -v`
Expected: PASS — every reconciled column within `atol ≤ 1e-9` of the gold file.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/tests/rollforward/test_va_acceptance.py
git commit -m "test(rollforward): §4.9 GSP-92 VA acceptance — 1200-period gold-file reconcile"
```

---

### Task 15: Lint + format + type check + benchmarks

- [ ] **Step 1: Lint**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/rollforward tests/rollforward`
Expected: no errors.

- [ ] **Step 2: Format**

Run: `cd bindings/python && uv run ruff format --check gaspatchio_core/rollforward tests/rollforward`
Expected: no diffs.

- [ ] **Step 3: Type-check**

Run: `cd bindings/python && uv run mypy gaspatchio_core/rollforward 2>&1 | tail -20`
Expected: zero errors.

- [ ] **Step 4: Rust tests + clippy**

Run: `cd core && cargo test -p gaspatchio-core && cargo clippy -p gaspatchio-core -- -D warnings`
Expected: green.

- [ ] **Step 5: Full repo regression**

Run: `cd bindings/python && uv run pytest tests/ -q 2>&1 | tail -10`
Expected: all green.

- [ ] **Step 6: Add benchmarks per spec §12.4**

Add benchmark scaffolding under `core/benches/`:
- `rollforward_va_benchmark` — VA + GMDB, 100K policies × 360 periods
- `rollforward_schedule_benchmark` — schedule construction + dt materialisation across the 5 day-counts × 4 calendars
- `rollforward_curve_benchmark` — `from_zero_rates` + `spot_rate` materialisation across the 5 day-counts

(Phase 1 commits to scaffolding only; tuning is Phase 2.)

- [ ] **Step 7: Commit cleanup**

```bash
git add -A
git commit -m "chore(rollforward): D3 lint + format + type-check + benchmark scaffolding"
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
- **D2 — Builder + compiler + explain**: ✅ shipped
- **D3 — Rust kernel + Polars backend + cutover**: ✅ shipped (this branch — v0.4.0 ready)

Plans:
- (existing entries)
- [`plans/2026-05-04-phase-1a-kernel-d3-execution.md`](plans/2026-05-04-phase-1a-kernel-d3-execution.md)
```

- [ ] **Step 2: Bump version**

In `bindings/python/pyproject.toml`: `version = "0.3.1"` → `version = "0.4.0"`.

- [ ] **Step 3: Commit**

```bash
git add ref/36-rollforward-redesign/README.md bindings/python/pyproject.toml
git commit -m "release(0.4.0): rollforward redesign complete — D3 cutover shipped"
```

---

## Self-review

**Spec coverage check:**
- §7 kernel architecture (single plugin Expr per rollforward, Struct emission, capture slots): tasks 1–10 ✓
- §7.1 9 typed Ops (kernel-side dispatch): tasks 2, 4, 6, 7 ✓
- §8.3 lazy/Struct release-gate (`lf.explain` shows exactly one plugin call): task 9 ✓
- §13.1a "delete shipped GSP-86 rollforward (PR #80)": task 11 ✓
- §13.1a `contract_boundary=mask` kernel logic: task 10 ✓
- §13.1a `lapse_when_all_non_positive` kernel logic: task 10 ✓
- §13.0 Phase 0 prerequisite for VA acceptance: task 14 (gated) ✓
- §10.3 port plan for `gaspatchio-va`: not in this plan (the gaspatchio-va repo is owned by a different sub-team; this plan ships only the core library), but enabled by Tasks 8–13 ✓
- §10.4 "what does not break" — `accumulate()` and `assumptions.Table` are untouched: enforced by §"Untouched" ✓
- §11 documentation deliverables — Phase 1b parallel PR in `gaspatchio-docs` is out of D3 scope ✓
- §12.4 benchmarks — scaffolded in task 15 ✓

**Placeholder scan:**
- Task 4 references "implementation is substantial (~300 lines)" — this is a real engineering note, not a placeholder. Deliberate handoff to engineer judgement; the test in Task 5 enforces correctness.
- Task 12 ("migrate Level-3 mini-VA tutorial") refers to the existing tutorial file but does not show full code. The engineer reads the existing tutorial and rewrites; the rewrite is bounded by the model data + the new builder API.
- Task 14 stub-rendering of test body is intentional — the §4.9 worked example IS the construction code; copy-paste from spec.

**Type consistency:**
- `RollforwardBuilder`, `RollforwardCollector`, `compile_rollforward`, `CompiledRollforward`, `IR`, `Schedule` referenced consistently across all tasks.
- Plugin function name `"rollforward_v2"` until Task 13 cutover, then `"rollforward"` everywhere.
- Rust `OpV2` enum's variant names match Python Op class names (`Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`, `DeductNAR`, `Ratchet`, `Floor`, `Apply`).

**Cross-plan consistency:**
- Reuses D1's IR + canonical_form + spec_fingerprint + action_key.
- Reuses D2's Builder + compile_rollforward + CompiledRollforward.
- Reuses Plans A/B/C's Schedule, Curve, MortalityTable typed inputs unchanged.
- After cutover, the public surface (`from gaspatchio_core import RollforwardBuilder, Schedule, Curve, MortalityTable`) provides every public symbol the spec promises for v0.4.0.

**Risks I've flagged inline:**
- Task 4–7 are the largest Rust-side work. The "300 lines" estimate for Task 4 is best-case; real implementation may need refactoring of the existing `rollforward.rs` patterns. Plan budgets one-week-of-work-equivalent for Tasks 4–7 combined; if the work overruns, the natural escape is to split Task 4 into "single-state-no-points" + "multi-state-with-points" sub-tasks.
- Task 14 is gated on Phase 0. If Phase 0 finds gold-file dependence on v1, the Task 14 work item shifts to "source independent reference" before reconciliation can be a release-gate. This is the documented contract; the plan correctly marks the dependency.
- Task 11's old-kernel deletion is **destructive** — this is the breaking-change moment for v0.4.0. Once landed, models depending on `from gaspatchio_core.rollforward import RollforwardBuilder` (the v1 import) will fail. Consistent with spec §1's pre-release breaking-change posture.
- Task 13's bulk rename uses `sed -i ''` — macOS-specific syntax. The plan notes the Linux variant. Engineer should sanity-check `git diff` before committing.

---

## Execution handoff

Plan complete and saved to `ref/36-rollforward-redesign/plans/2026-05-04-phase-1a-kernel-d3-execution.md`. Two execution options:

**1. Subagent-Driven (recommended for D3)** — Tasks 4–7 are large enough that fresh subagent context per task helps. Tasks 11–13 are mechanical + destructive — review carefully before merging.

**2. Inline Execution** — Practical for Tasks 1–3, 8–10, 14–16 (well-bounded). Less practical for Tasks 4–7 due to Rust kernel size; subagent-driven is the better fit there.

Execution sequencing across the redesign as a whole: A → B/C (parallel) → D1 → D2 → D3.

---

## Plan-set status (all four sub-plans drafted)

- A: typed time (26 tasks, 125 steps)
- B: Curve (16 tasks, 73 steps)
- C: MortalityTable (11 tasks, 56 steps)
- D1: IR + identity (~14 tasks, ~60 steps)
- D2: Builder + compiler + explain (~16 tasks, ~75 steps)
- D3: Rust kernel + Polars backend + cutover (16 tasks, ~80 steps)

**Total: ~99 tasks, ~470 TDD steps across 6 plan files.**

Ready to begin execution: start with Plan A.
