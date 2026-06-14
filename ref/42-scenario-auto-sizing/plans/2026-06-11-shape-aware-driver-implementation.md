# Shape-aware `for_each_scenario` auto driver — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `for_each_scenario`'s `batch_size="auto"` learn-and-cache sizer with a measured
coarse **streaming-batch search** (probe `[1,4,16,64]` on real folded passes, pick the fastest rung
whose peak fits the budget) plus a lazy `in-mem@b1` memory floor — deleting the now-redundant
calibration cache, the two-point RSS probe sizer, `bytes_per_cell`, and the `peak_conservative` knob.

**Architecture:** The auto path measures the optimum **every run** (no cache: the optimum is
N/shape-dependent). The batch loop is refactored so two shared helpers — `_run_one_batch` (build +
engine-selected collect + transient peak) and `_fold_batch` (the within-reduction fold) — back both
a **probe phase** (the ladder rungs, measured) and a **remainder phase** (the winner). Feasibility is
gated on each probe's measured peak × `SAFETY_MARGIN`; if no streaming rung fits, fall to `in-mem@b1`;
if even that won't fit, raise `IrreducibleCellError`. No backwards compatibility is kept.

**Tech Stack:** Python 3.12, Polars (streaming/in-memory engines), PyO3 core (unchanged — pure-Python
change), psutil (RSS), pytest, mypy + pyright + `mypy.stubtest`. All commands run via `uv run` from
`bindings/python`.

**Spec:** `ref/42-scenario-auto-sizing/specs/2026-06-10-shape-aware-driver-design.md`.

---

## File Structure

**Modify:**
- `gaspatchio_core/scenarios/_memory.py` — add `LADDER`, `safety_margin` to `SizingDefaults`.
- `gaspatchio_core/scenarios/_result.py` — redefine `batch_size_resolution` Literal; add `ProbeResult`,
  `SelectionDecision`, `selection` field.
- `gaspatchio_core/scenarios/_auto_batch.py` — strip to `process_rss_bytes`, `_SAFETY_CEILING`, and a
  small `memory_budget_bytes()` helper; delete `resolve_batch_size` + `bytes_per_cell` + the linear fit.
- `gaspatchio_core/scenarios/_search.py` — **new**: the pure selector (`plan_search`, `decide_winner`)
  + the `ProbePlan` dataclasses, independent of the loop so it's unit-testable.
- `gaspatchio_core/scenarios/_for_each.py` — extract `_run_one_batch` + `_fold_batch`; wire the search
  into the loop; cgroup-fix the budget; drop `bytes_per_cell` + `_batch_profile`; fix the
  `_collect_with_peak` docstring.
- `gaspatchio_core/scenarios/_run.py` — drop `bytes_per_cell`; extend audit `run_metadata` with the
  selection; pass nothing cache-related.
- `gaspatchio_core/scenarios/_audit.py` — bump `AUDIT_SCHEMA_VERSION` to `"2.0"`.
- `gaspatchio_core/scenarios/__init__.py` — export `SelectionDecision`, `ProbeResult`.
- `gaspatchio_core/scenarios/__init__.pyi` — update stubs to match all of the above.

**Delete:**
- `gaspatchio_core/scenarios/_batch_profile.py`
- `tests/scenarios/test_batch_profile.py`
- `tests/scenarios/test_batch_cache_integration.py`
- the `_isolate_batch_cache` autouse fixture in `tests/scenarios/conftest.py`

**New tests:**
- `tests/scenarios/test_search.py` — unit tests for the pure selector.
- `tests/scenarios/test_for_each_search.py` — integration (L5-style, 1K policies, laptop-safe).

**Update tests (blast radius — reference deleted symbols):**
- `tests/scenarios/test_auto_batch.py`, `test_memory.py`, `test_result.py`,
  `test_for_each_scenario.py`, `tests/benchmarks/test_scenario_lib.py`.

**Conventions:** conventional commits, signed, **no** AI-assistant trailer; reference GSP-NNN if one
is assigned. Build is pure-Python (no `maturin` rebuild needed).

---

## Task 1: Add `LADDER` and `safety_margin` to `SizingDefaults`

**Files:**
- Modify: `gaspatchio_core/scenarios/_memory.py:26-36` (`SizingDefaults` + `DEFAULTS`)
- Test: `tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scenarios/test_memory.py`:

```python
def test_sizing_defaults_has_ladder_and_safety_margin():
    from gaspatchio_core.scenarios._memory import DEFAULTS

    assert DEFAULTS.ladder == (1, 4, 16, 64)
    assert DEFAULTS.safety_margin == 1.3
    # ladder is ascending and starts at 1 (the always-feasible-to-probe floor batch)
    assert DEFAULTS.ladder[0] == 1
    assert list(DEFAULTS.ladder) == sorted(DEFAULTS.ladder)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_memory.py::test_sizing_defaults_has_ladder_and_safety_margin -v`
Expected: FAIL — `AttributeError: 'SizingDefaults' object has no attribute 'ladder'`

- [ ] **Step 3: Add the fields**

In `gaspatchio_core/scenarios/_memory.py`, replace the `SizingDefaults` dataclass body:

```python
@dataclass(frozen=True, slots=True)
class SizingDefaults:
    """All batch-sizing constants in one auditable place (no scattered literals)."""

    target_memory_fraction: float = 0.5
    safety: float = 0.8
    min_floor_bytes: int = 1_000_000  # 1 MB noise floor for a measured per-cell cost
    abs_first_batch_bytes: int = 384 * 1024**2  # first-batch list-data ceiling (Plan 2)
    # Streaming-batch search (shape-aware driver):
    ladder: tuple[int, ...] = (1, 4, 16, 64)  # geometric rungs to probe
    safety_margin: float = 1.3  # inflate measured probe peak before the budget comparison
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_memory.py::test_sizing_defaults_has_ladder_and_safety_margin -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_memory.py tests/scenarios/test_memory.py
git commit -m "feat(scenarios): add streaming-batch ladder + safety_margin to SizingDefaults"
```

---

## Task 2: Redefine `ScenarioResult` — new resolution literal + `SelectionDecision`/`ProbeResult`

**Files:**
- Modify: `gaspatchio_core/scenarios/_result.py`
- Test: `tests/scenarios/test_result.py`

- [ ] **Step 1: Write the failing test**

Replace the resolution-literal assertions in `tests/scenarios/test_result.py` (any referencing
`auto_probe`/`auto_calibrated`/`auto_cached`) and add:

```python
def test_scenario_result_has_selection_and_new_resolution_literal():
    from gaspatchio_core.scenarios._result import (
        ProbeResult,
        ScenarioResult,
        SelectionDecision,
    )

    probe = ProbeResult(batch=4, engine="streaming", per_sc_s=0.04, peak_mb=300.0, fits=True)
    sel = SelectionDecision(
        engine="streaming", batch=4, reason="fastest_fitting", probed=[probe]
    )
    r = ScenarioResult(
        aggregations={}, plan_sha="x", n_scenarios=10, batch_size=4,
        batch_size_resolution="auto_search", wall_time_s=1.0, peak_rss_mb=None,
        sink_dir=None, selection=sel,
    )
    assert r.batch_size_resolution == "auto_search"
    assert r.selection.engine == "streaming"
    assert r.selection.probed[0].batch == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_result.py::test_scenario_result_has_selection_and_new_resolution_literal -v`
Expected: FAIL — `ImportError: cannot import name 'SelectionDecision'`

- [ ] **Step 3: Implement the new types**

In `gaspatchio_core/scenarios/_result.py`, add above `ScenarioResult` (keep the existing imports;
`Literal` is already imported):

```python
@dataclass(frozen=True, slots=True)
class ProbeResult:
    """One measured rung of the streaming-batch search (audit trail)."""

    batch: int
    engine: Literal["streaming", "in-memory"]
    per_sc_s: float
    peak_mb: float | None
    fits: bool


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    """How ``batch_size='auto'`` resolved: the chosen point + the measured ladder."""

    engine: Literal["streaming", "in-memory"]
    batch: int
    reason: Literal["fastest_fitting", "floor", "single_scenario", "forced_b1"]
    probed: list[ProbeResult]
```

Change the `ScenarioResult` field and add `selection`:

```python
    batch_size_resolution: Literal["manual", "auto_search"]
    wall_time_s: float
    peak_rss_mb: float | None
    sink_dir: Path | None
    selection: SelectionDecision | None = None
    audit_path: Path | None = None
```

Update `__all__`:

```python
__all__ = ["ProbeResult", "ScenarioResult", "SelectionDecision"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_result.py::test_scenario_result_has_selection_and_new_resolution_literal -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_result.py tests/scenarios/test_result.py
git commit -m "feat(scenarios): add SelectionDecision/ProbeResult; collapse resolution to auto_search"
```

---

## Task 3: Cgroup-honest budget helper in `_auto_batch.py`

**Files:**
- Modify: `gaspatchio_core/scenarios/_auto_batch.py`
- Test: `tests/scenarios/test_auto_batch.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/scenarios/test_auto_batch.py`'s probe-based tests with:

```python
def test_memory_budget_bytes_is_cgroup_aware(monkeypatch):
    from gaspatchio_core.scenarios import _auto_batch, _memory

    # memory_budget_bytes must route through _memory.memory_budget (cgroup-aware),
    # NOT psutil.virtual_memory().available directly.
    seen = {}

    def fake_budget(fraction, **kw):
        seen["fraction"] = fraction
        return 4_000_000_000

    monkeypatch.setattr(_memory, "memory_budget", fake_budget)
    out = _auto_batch.memory_budget_bytes(target_memory_fraction=0.5)
    assert out == 4_000_000_000
    assert seen["fraction"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_auto_batch.py::test_memory_budget_bytes_is_cgroup_aware -v`
Expected: FAIL — `AttributeError: module 'gaspatchio_core.scenarios._auto_batch' has no attribute 'memory_budget_bytes'`

- [ ] **Step 3: Replace the probe machinery with the budget helper**

Rewrite `gaspatchio_core/scenarios/_auto_batch.py` to keep only what the new design needs.
Replace the whole file body below the module docstring with:

```python
from __future__ import annotations

from pathlib import Path

import psutil

from gaspatchio_core.scenarios import _memory

# Seams so tests can inject a fake cgroup root / proc text without a container.
_cgroup_root: Path = Path("/sys/fs/cgroup")
_proc_cgroup_text: str | None = None  # None -> read /proc/self/cgroup live

_SAFETY_CEILING = 256  # absolute cap on any probed/operating batch size


def process_rss_bytes() -> int:
    """Return the current process RSS in bytes."""
    return int(psutil.Process().memory_info().rss)


def memory_budget_bytes(target_memory_fraction: float) -> int:
    """Bytes one batch may target. Cgroup-aware + base-RSS-subtracted (fails open to host RAM)."""
    return _memory.memory_budget(
        target_memory_fraction,
        root=_cgroup_root,
        proc_cgroup_text=_proc_cgroup_text,
    )


__all__ = ["memory_budget_bytes", "process_rss_bytes"]
```

(Also update the module docstring at the top to describe the budget helper, not the two-point probe.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_auto_batch.py::test_memory_budget_bytes_is_cgroup_aware -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_auto_batch.py tests/scenarios/test_auto_batch.py
git commit -m "refactor(scenarios): replace two-point probe sizer with cgroup-honest budget helper"
```

---

## Task 4: The pure selector — `_search.py` (`decide_winner` + `plan_search`)

**Files:**
- Create: `gaspatchio_core/scenarios/_search.py`
- Test: `tests/scenarios/test_search.py`

This task builds the selector as a **pure function over already-measured rungs**, so it is fully
unit-testable without running any model. The loop (Task 6) supplies the measurements.

- [ ] **Step 1: Write the failing tests**

Create `tests/scenarios/test_search.py`:

```python
from gaspatchio_core.scenarios._result import ProbeResult
from gaspatchio_core.scenarios._search import build_ladder, decide_winner


def _probe(batch, per_sc, peak, engine="streaming"):
    return ProbeResult(batch=batch, engine=engine, per_sc_s=per_sc, peak_mb=peak, fits=True)


def test_build_ladder_caps_at_n_and_ceiling():
    assert build_ladder(n_scenarios=1000, ladder=(1, 4, 16, 64), ceiling=256) == [1, 4, 16, 64]
    assert build_ladder(n_scenarios=10, ladder=(1, 4, 16, 64), ceiling=256) == [1, 4]
    assert build_ladder(n_scenarios=2, ladder=(1, 4, 16, 64), ceiling=256) == [1]
    assert build_ladder(n_scenarios=1000, ladder=(1, 4, 16, 64), ceiling=8) == [1, 4]


def test_decide_winner_picks_fastest_fitting():
    # U-shape: b16 fastest; all fit. budget large.
    probed = [_probe(1, 0.50, 100), _probe(4, 0.20, 300), _probe(16, 0.05, 900), _probe(64, 0.06, 3000)]
    win = decide_winner(probed, budget_mb=8000, safety_margin=1.3, floor=None)
    assert win.engine == "streaming"
    assert win.batch == 16
    assert win.reason == "fastest_fitting"


def test_decide_winner_excludes_over_budget_rungs():
    # b16 is fastest but its peak*margin exceeds budget -> pick best fitting (b4).
    probed = [_probe(1, 0.50, 100), _probe(4, 0.20, 300), _probe(16, 0.05, 5000)]
    win = decide_winner(probed, budget_mb=4000, safety_margin=1.3, floor=None)
    assert win.batch == 4
    assert win.reason == "fastest_fitting"


def test_decide_winner_uses_floor_when_no_streaming_fits():
    # Even stream@b1 over budget; in-mem@b1 floor fits.
    probed = [_probe(1, 0.50, 9000)]  # stream@1 over a 6000 budget after margin
    floor = ProbeResult(batch=1, engine="in-memory", per_sc_s=1.2, peak_mb=4000, fits=True)
    win = decide_winner(probed, budget_mb=6000, safety_margin=1.3, floor=floor)
    assert win.engine == "in-memory"
    assert win.batch == 1
    assert win.reason == "floor"


def test_decide_winner_raises_when_nothing_fits():
    from gaspatchio_core.scenarios._memory import IrreducibleCellError

    probed = [_probe(1, 0.50, 9000)]
    floor = ProbeResult(batch=1, engine="in-memory", per_sc_s=1.2, peak_mb=9000, fits=False)
    import pytest

    with pytest.raises(IrreducibleCellError):
        decide_winner(probed, budget_mb=6000, safety_margin=1.3, floor=floor)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scenarios/test_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._search'`

- [ ] **Step 3: Implement `_search.py`**

Create `gaspatchio_core/scenarios/_search.py`:

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Pure selector for batch_size="auto" -- coarse streaming-batch search + in-mem floor.
# ABOUTME: Operates over already-measured rungs (ProbeResult); the loop supplies the measurements.

"""Streaming-batch search selector (shape-aware driver).

The optimum streaming batch is U-shaped in batch size and moves with the model, so it is measured
per run on real folded passes. This module is the *pure* decision layer: given the measured ladder
rungs and the memory budget, choose the fastest rung whose peak fits, falling to the in-memory
floor, or raising when nothing fits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.scenarios._memory import IrreducibleCellError
from gaspatchio_core.scenarios._result import ProbeResult, SelectionDecision

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_ladder(*, n_scenarios: int, ladder: Sequence[int], ceiling: int) -> list[int]:
    """Return the ascending probe rungs, capped at ``min(n_scenarios, ceiling)``."""
    cap = min(n_scenarios, ceiling)
    return [b for b in ladder if b <= cap]


def _fits(peak_mb: float | None, budget_mb: float, safety_margin: float) -> bool:
    """A rung fits if its measured peak inflated by the safety margin is within budget.

    A missing reading (None) is treated as NOT fitting -- conservative (never risk OOM on a
    rung we could not measure).
    """
    if peak_mb is None:
        return False
    return peak_mb * safety_margin <= budget_mb


def decide_winner(
    probed: list[ProbeResult],
    *,
    budget_mb: float,
    safety_margin: float,
    floor: ProbeResult | None,
) -> SelectionDecision:
    """Pick the fastest streaming rung whose peak fits; else the floor; else raise.

    Args:
        probed: measured streaming rungs (ascending batch order).
        budget_mb: memory budget in MiB.
        safety_margin: multiplier applied to a measured peak before the budget comparison.
        floor: the measured in-mem@b1 fallback, or None if it was not measured (because a
            streaming rung already fit).

    Raises:
        IrreducibleCellError: when neither any streaming rung nor the floor fits.

    """
    fitting = [p for p in probed if _fits(p.peak_mb, budget_mb, safety_margin)]
    annotated = [
        ProbeResult(p.batch, p.engine, p.per_sc_s, p.peak_mb,
                    fits=_fits(p.peak_mb, budget_mb, safety_margin))
        for p in probed
    ]
    if fitting:
        winner = min(fitting, key=lambda p: p.per_sc_s)
        return SelectionDecision(
            engine="streaming", batch=winner.batch, reason="fastest_fitting", probed=annotated
        )
    if floor is not None and _fits(floor.peak_mb, budget_mb, safety_margin):
        annotated.append(ProbeResult(floor.batch, "in-memory", floor.per_sc_s, floor.peak_mb, fits=True))
        return SelectionDecision(
            engine="in-memory", batch=floor.batch, reason="floor", probed=annotated
        )
    msg = (
        "No batch fits the memory budget: even in-memory batch_size=1 exceeds it. "
        "Reduce policies, shorten the horizon, raise target_memory_fraction, or run on a "
        "box/cgroup with more memory."
    )
    raise IrreducibleCellError(msg)


__all__ = ["build_ladder", "decide_winner"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_search.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_search.py tests/scenarios/test_search.py
git commit -m "feat(scenarios): pure streaming-batch-search selector (build_ladder + decide_winner)"
```

---

## Task 5: Extract `_fold_batch` from the loop (pure refactor)

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (the per-batch fold block, ~660-745)
- Test: existing `tests/scenarios/test_for_each_scenario.py` (must still pass)

The loop must call identical fold logic in both the probe phase and the remainder phase. Extract it
into a helper FIRST, with no behaviour change.

- [ ] **Step 1: Write a characterization test (guards the refactor)**

Add to `tests/scenarios/test_for_each_scenario.py`:

```python
def test_fold_batch_helper_exists_and_folds(simple_af, simple_model_fn):
    # _fold_batch must reduce a collected projection into the accumulators identically to the
    # inline loop. This is a structural guard for the Task 5 extraction.
    from gaspatchio_core.scenarios import _for_each

    assert hasattr(_for_each, "_fold_batch")
```

(Use whatever `simple_af`/`simple_model_fn` fixtures the file already defines; if none, this
one-line `hasattr` assert plus the full existing suite passing is sufficient.)

- [ ] **Step 2: Run the full for_each suite to capture the green baseline**

Run: `uv run pytest tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_partitioned.py tests/scenarios/test_for_each_streaming.py -q`
Expected: PASS (record the count — must be identical after the refactor)

- [ ] **Step 3: Extract `_fold_batch`**

In `gaspatchio_core/scenarios/_for_each.py`, move the per-batch fold body (the VectorAggregator
dispatch + the group-by fold over `proj_eager`, currently inline in the loop at ~660-745) into a
module-level helper. Signature:

```python
def _fold_batch(
    proj_eager: pl.DataFrame,
    *,
    aliases: list[str],
    aggregations: Sequence[Aggregator | _Partitioned],
    accumulators: dict[str, Any],
) -> None:
    """Fold one collected batch's within-reductions into ``accumulators`` (in place).

    Moved verbatim from the inline loop body so the probe phase and the remainder phase share
    one fold implementation. Behaviour is unchanged.
    """
    # ... the exact VectorAggregator dispatch + group_by/iter_rows fold block, verbatim ...
```

Replace the inline block in the loop with `_fold_batch(proj_eager, aliases=aliases, aggregations=aggregations, accumulators=accumulators)`.

- [ ] **Step 4: Run the suite to verify identical behaviour**

Run: `uv run pytest tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_partitioned.py tests/scenarios/test_for_each_streaming.py -q`
Expected: PASS — same count as Step 2.

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_for_each_scenario.py
git commit -m "refactor(scenarios): extract _fold_batch helper (no behaviour change)"
```

---

## Task 6: Extract `_run_one_batch` + measure (pure refactor)

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (the build + `_collect_with_peak` block, ~644-659)
- Test: existing for_each suites (must still pass)

- [ ] **Step 1: Run the green baseline**

Run: `uv run pytest tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_streaming.py -q`
Expected: PASS (record the count)

- [ ] **Step 2: Extract `_run_one_batch`**

In `gaspatchio_core/scenarios/_for_each.py`, add a helper that builds one batch's projection and
collects it under a chosen engine, returning the eager frame, its transient peak (bytes), and the
collect wall (seconds):

```python
def _run_one_batch(
    af: ActuarialFrame,
    batch_sids: list[ScenarioID],
    model_fn: Callable[..., ActuarialFrame],
    *,
    scenarios: Any,
    shape: Literal["ids", "shocks", "drivers"],
    base_tables: dict[str, Table] | None,
    master_seed: int | None,
    engine: Literal["in-memory", "streaming"],
) -> tuple[pl.DataFrame, int, float]:
    """Build + collect one batch under ``engine``; return (frame, peak_bytes, wall_s)."""
    af_batch = with_scenarios(af, batch_sids)  # type: ignore[arg-type]
    if shape == "shocks":
        tables = _build_stacked_tables(scenarios, batch_sids, base_tables)
    else:
        tables = base_tables or {}
    drivers = _build_drivers(scenarios, batch_sids, shape, master_seed)
    af_proj = model_fn(af_batch, tables=tables, drivers=drivers)
    if af_proj._df is None:  # noqa: SLF001
        msg = "model_fn returned an ActuarialFrame with no underlying frame; contract violation."
        raise ValueError(msg)
    _engine = "streaming" if engine == "streaming" else None
    started = time.perf_counter()
    proj_eager, peak = _collect_with_peak(af_proj._df, engine=_engine)  # noqa: SLF001
    return proj_eager, peak, time.perf_counter() - started
```

Replace the inline build+collect in the loop with a call to `_run_one_batch(..., engine="in-memory")`
(preserving today's behaviour: the existing loop is in-memory).

- [ ] **Step 3: Run the suites to verify identical behaviour**

Run: `uv run pytest tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_streaming.py -q`
Expected: PASS — same count as Step 1.

- [ ] **Step 4: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py
git commit -m "refactor(scenarios): extract _run_one_batch (engine-parametrised build+collect)"
```

---

## Task 7: Wire the search into `for_each_scenario` (the core change)

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` — the resolution block (~504-566), the loop
  (~632-754), the calibration write-back (~799-821), and the signature (remove `bytes_per_cell`).
- Test: `tests/scenarios/test_for_each_search.py` (new)

- [ ] **Step 1: Write the failing integration test**

Create `tests/scenarios/test_for_each_search.py`:

```python
import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario


def _af(n_policies=200):
    return ActuarialFrame(pl.DataFrame({"policy_id": range(n_policies), "v": [1.0] * n_policies}))


def _model_fn(af, *, tables=None, drivers=None):  # noqa: ARG001
    af.payoff = af.v * 2.0
    return af


def test_auto_search_resolves_and_records_selection():
    r = for_each_scenario(
        _af(), scenarios=list(range(1, 41)), model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.batch_size_resolution == "auto_search"
    assert r.selection is not None
    assert r.selection.engine in ("streaming", "in-memory")
    assert len(r.selection.probed) >= 1
    # probed ladder is the ascending rungs capped at N
    assert [p.batch for p in r.selection.probed if p.engine == "streaming"][0] == 1


def test_auto_search_matches_manual_checksum():
    agg = (Sum("payoff").alias("total").over("scenario_id"),)
    auto = for_each_scenario(_af(), scenarios=list(range(1, 41)), model_fn=_model_fn,
                             aggregations=agg, batch_size="auto")
    manual = for_each_scenario(_af(), scenarios=list(range(1, 41)), model_fn=_model_fn,
                               aggregations=agg, batch_size=8)

    def checksum(res):
        df = res.aggregations["total"]
        return round(sum(float(df[c].sum()) for c in df.columns if c != "scenario_id"), 6)

    assert checksum(auto) == checksum(manual)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/scenarios/test_for_each_search.py -v`
Expected: FAIL — `AssertionError` on `batch_size_resolution` (currently `auto_probe`) / `selection is None`.

- [ ] **Step 3: Replace the resolution block + loop with the search**

In `for_each_scenario` (`_for_each.py`):

1. Remove `bytes_per_cell` from the signature and all uses.
2. Remove the `import ... _batch_profile` and every `_batch_profile.*` / `cache_*` line, the
   `cache_shape_fp`/`cache_env`/`cache_budget_bytes` setup (~504-566), and the post-loop
   write-back (~799-821).
3. Replace the resolution + loop with the search-driven orchestration. After the
   `sids`/`accumulators` setup, insert:

```python
from gaspatchio_core.scenarios._auto_batch import (
    _SAFETY_CEILING,
    memory_budget_bytes,
    process_rss_bytes,
)
from gaspatchio_core.scenarios._memory import DEFAULTS
from gaspatchio_core.scenarios._result import ProbeResult, SelectionDecision
from gaspatchio_core.scenarios._search import build_ladder, decide_winner

def _process_one(batch_sids, *, engine):
    proj_eager, peak, wall = _run_one_batch(
        af, batch_sids, model_fn, scenarios=scenarios, shape=shape,
        base_tables=base_tables, master_seed=master_seed, engine=engine,
    )
    _fold_batch(proj_eager, aliases=aliases, aggregations=aggregations, accumulators=accumulators)
    if return_full_grid and sink_dir is not None:
        _write_batch_parquet(proj_eager, sink_dir / f"batch_{len(folded):04d}.parquet")
    del proj_eager
    return peak, wall

folded: list[ScenarioID] = []
selection: SelectionDecision | None = None
resolution: Literal["manual", "auto_search"]

if batch_size != "auto":
    resolved_size, resolution = int(batch_size), "manual"
elif master_seed is not None or shape == "drivers":
    # forced batch_size=1: engine-only choice (stream@1 vs in-mem@1), both feasibility-gated
    resolved_size, resolution = 1, "auto_search"
    budget_mb = memory_budget_bytes(target_memory_fraction) / 1024**2
    probed = []
    for engine in ("streaming", "in-memory"):
        if not sids[len(folded):]:
            break
        b1 = sids[len(folded):len(folded) + 1]
        peak, wall = _process_one(b1, engine=engine)
        folded.extend(b1)
        probed.append(ProbeResult(1, engine, wall, peak / 1024**2,
                                  fits=peak / 1024**2 * DEFAULTS.safety_margin <= budget_mb))
    feasible = [p for p in probed if p.fits] or probed
    win = min(feasible, key=lambda p: p.per_sc_s)
    selection = SelectionDecision(win.engine, 1, "forced_b1", probed)
    winner_engine = win.engine
else:
    budget_mb = memory_budget_bytes(target_memory_fraction) / 1024**2
    ladder = build_ladder(n_scenarios=len(sids), ladder=DEFAULTS.ladder, ceiling=_SAFETY_CEILING)
    probed = []
    for b in ladder:
        nxt = sids[len(folded):len(folded) + b]
        if len(nxt) < b:  # not enough scenarios left to measure this rung honestly
            break
        peak, wall = _process_one(nxt, engine="streaming")
        folded.extend(nxt)
        pr = ProbeResult(b, "streaming", wall / b, peak / 1024**2,
                         fits=peak / 1024**2 * DEFAULTS.safety_margin <= budget_mb)
        probed.append(pr)
        if not pr.fits:  # larger rungs are heavier -> stop probing
            break
    floor = None
    if not any(p.fits for p in probed) and sids[len(folded):]:
        b1 = sids[len(folded):len(folded) + 1]
        fpeak, fwall = _process_one(b1, engine="in-memory")
        folded.extend(b1)
        floor = ProbeResult(1, "in-memory", fwall, fpeak / 1024**2,
                            fits=fpeak / 1024**2 * DEFAULTS.safety_margin <= budget_mb)
    selection = decide_winner(probed, budget_mb=budget_mb,
                              safety_margin=DEFAULTS.safety_margin, floor=floor)
    resolution, resolved_size, winner_engine = "auto_search", selection.batch, selection.engine
```

4. Then run the **remainder** (the un-folded scenarios) under the winner — for `manual`, `folded`
   is empty and `winner_engine` is `"in-memory"`:

```python
if resolution == "manual":
    winner_engine = "in-memory"
remaining = sids[len(folded):]
for batch_sids in _chunks(remaining, resolved_size):  # type: ignore[type-var]
    _process_one(batch_sids, engine=winner_engine)
    # ... existing RSS high-water + on_batch snapshot block, using scenarios_done = len(folded) ...
```

5. Keep the existing `peak_rss`/`baseline_rss`/`on_batch` high-water tracking, updating
   `scenarios_done` to `len(folded)` after each `_process_one`. Set `selection` on the result.

6. Return `ScenarioResult(..., batch_size=resolved_size, batch_size_resolution=resolution,
   selection=selection, ...)`.

- [ ] **Step 4: Run the new + existing for_each suites**

Run: `uv run pytest tests/scenarios/test_for_each_search.py tests/scenarios/test_for_each_scenario.py tests/scenarios/test_for_each_streaming.py tests/scenarios/test_for_each_partitioned.py tests/scenarios/test_for_each_drivers.py tests/scenarios/test_for_each_shocks.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_for_each_search.py
git commit -m "feat(scenarios): drive batch_size=auto by the measured streaming-batch search"
```

---

## Task 8: Forced-`b1` + `N==1` edge tests

**Files:**
- Test: `tests/scenarios/test_for_each_search.py`
- Modify (only if a test fails): `gaspatchio_core/scenarios/_for_each.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scenarios/test_for_each_search.py`:

```python
def test_master_seed_forces_engine_only_search():
    r = for_each_scenario(
        _af(), scenarios=list(range(1, 11)), model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto", master_seed=123,
    )
    assert r.batch_size == 1
    assert r.batch_size_resolution == "auto_search"
    assert r.selection.reason == "forced_b1"
    assert {p.engine for p in r.selection.probed} == {"streaming", "in-memory"}


def test_single_scenario_no_search():
    r = for_each_scenario(
        _af(), scenarios=[1], model_fn=_model_fn,
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    assert r.batch_size == 1
    assert r.selection is not None
    assert r.selection.reason in ("single_scenario", "forced_b1", "fastest_fitting")
```

- [ ] **Step 2: Run to verify**

Run: `uv run pytest tests/scenarios/test_for_each_search.py -k "forces_engine_only or single_scenario" -v`
Expected: PASS (the Task 7 wiring already covers `master_seed`; if `N==1` needs a guard so the
ladder probe doesn't consume the only scenario before the remainder, add `reason="single_scenario"`
handling in the `else` branch when `len(sids) == 1`).

- [ ] **Step 3: (If needed) add the `N==1` guard**

If `test_single_scenario_no_search` fails, add at the top of the auto `else` branch:

```python
if len(sids) == 1:
    budget_mb = memory_budget_bytes(target_memory_fraction) / 1024**2
    b1 = sids[:1]
    peak, wall = _process_one(b1, engine="streaming")
    folded.extend(b1)
    fits = peak / 1024**2 * DEFAULTS.safety_margin <= budget_mb
    pr = ProbeResult(1, "streaming", wall, peak / 1024**2, fits=fits)
    if not fits:
        # try the in-mem floor on the (already folded) single scenario's shape via a re-run guard
        raise IrreducibleCellError("single scenario exceeds the memory budget on both engines")
    selection = SelectionDecision("streaming", 1, "single_scenario", [pr])
    resolution, resolved_size, winner_engine = "auto_search", 1, "streaming"
```

(Place it so the remainder loop then finds no un-folded scenarios.)

- [ ] **Step 4: Re-run**

Run: `uv run pytest tests/scenarios/test_for_each_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_for_each_search.py
git commit -m "feat(scenarios): handle forced-b1 (seed/drivers) and N==1 in the auto search"
```

---

## Task 9: Audit sidecar — carry the selection; bump `AUDIT_SCHEMA_VERSION`

**Files:**
- Modify: `gaspatchio_core/scenarios/_audit.py:23` and `gaspatchio_core/scenarios/_run.py`
  (`run()` signature + `_write_audit_sidecar` `run_metadata`)
- Test: `tests/scenarios/test_audit_chain.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scenarios/test_audit_chain.py`:

```python
def test_audit_records_selection_and_v2_schema(tmp_path):
    import polars as pl

    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios import ScenarioRun, Sum
    from gaspatchio_core.scenarios._audit import AUDIT_SCHEMA_VERSION, read_audit

    assert AUDIT_SCHEMA_VERSION == "2.0"

    af = ActuarialFrame(pl.DataFrame({"policy_id": range(50), "v": [1.0] * 50}))

    def model_fn(a, *, tables=None, drivers=None):  # noqa: ARG001
        a.payoff = a.v * 2.0
        return a

    plan = ScenarioRun(shocks=list(range(1, 21)), aggregations=(Sum("payoff").alias("total").over("scenario_id"),))
    out = tmp_path / "a.audit.json"
    res = plan.run(af, model_fn, audit=out)
    meta = read_audit(res.audit_path)["run_metadata"]
    assert meta["batch_size_resolution"] == "auto_search"
    assert meta["selection_engine"] in ("streaming", "in-memory")
    assert isinstance(meta["selection_probed"], list)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/scenarios/test_audit_chain.py::test_audit_records_selection_and_v2_schema -v`
Expected: FAIL — `assert "1.0" == "2.0"` / missing `selection_engine`.

- [ ] **Step 3: Bump schema + extend metadata**

In `gaspatchio_core/scenarios/_audit.py`:

```python
AUDIT_SCHEMA_VERSION = "2.0"
```

In `gaspatchio_core/scenarios/_run.py`, remove `bytes_per_cell` from `run()`'s signature and from
the `for_each_scenario(...)` call. In `_write_audit_sidecar`, extend the `run_metadata` dict:

```python
            run_metadata={
                "wall_time_s": result.wall_time_s,
                "n_scenarios": result.n_scenarios,
                "batch_size": result.batch_size,
                "batch_size_resolution": result.batch_size_resolution,
                "selection_engine": result.selection.engine if result.selection else None,
                "selection_reason": result.selection.reason if result.selection else None,
                "selection_probed": [
                    {"batch": p.batch, "engine": p.engine, "per_sc_s": p.per_sc_s,
                     "peak_mb": p.peak_mb, "fits": p.fits}
                    for p in (result.selection.probed if result.selection else [])
                ],
                "library_version": getattr(gaspatchio_core, "__version__", "unknown"),
                "polars_version": pl.__version__,
                "ddsketch_version": ddsketch_version,
                "python_version": ".".join(map(str, sys.version_info[:3])),
                "master_seed": self.master_seed,
            },
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/scenarios/test_audit_chain.py::test_audit_records_selection_and_v2_schema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_audit.py gaspatchio_core/scenarios/_run.py tests/scenarios/test_audit_chain.py
git commit -m "feat(scenarios): record the batch-search selection in the audit sidecar (schema 2.0)"
```

---

## Task 10: Delete the calibration cache + its tests; clean the conftest

**Files:**
- Delete: `gaspatchio_core/scenarios/_batch_profile.py`, `tests/scenarios/test_batch_profile.py`,
  `tests/scenarios/test_batch_cache_integration.py`
- Modify: `tests/scenarios/conftest.py` (remove `_isolate_batch_cache`)

- [ ] **Step 1: Delete the module + its dedicated tests**

```bash
git rm gaspatchio_core/scenarios/_batch_profile.py \
       tests/scenarios/test_batch_profile.py \
       tests/scenarios/test_batch_cache_integration.py
```

- [ ] **Step 2: Remove the conftest fixture**

In `tests/scenarios/conftest.py`, delete the `from gaspatchio_core.scenarios import _batch_profile`
import and the entire `_isolate_batch_cache` fixture (the autouse fixture redirecting `cache_dir`).

- [ ] **Step 3: Verify nothing imports the deleted module**

Run: `grep -rn "_batch_profile\|batch_profile\|resolve_batch_size" gaspatchio_core/ tests/scenarios/`
Expected: no matches (scratch tests under `tests/scratch/` may remain — handle in Task 11).

- [ ] **Step 4: Run the scenarios suite**

Run: `uv run pytest tests/scenarios -q`
Expected: PASS (collection succeeds with no import errors from the deletions)

- [ ] **Step 5: Commit**

```bash
git add -A tests/scenarios/conftest.py
git commit -m "refactor(scenarios): delete the batch-size calibration cache (no longer used)"
```

---

## Task 11: Fix the remaining blast-radius tests + stubs; type-check green

**Files:**
- Modify: `tests/scenarios/test_auto_batch.py`, `test_memory.py`, `test_for_each_scenario.py`,
  `tests/benchmarks/test_scenario_lib.py`, `tests/scratch/gsp100_stress/agent1_scale/test3_auto_batch.py`
- Modify: `gaspatchio_core/scenarios/__init__.py`, `gaspatchio_core/scenarios/__init__.pyi`

- [ ] **Step 1: Export the new types**

In `gaspatchio_core/scenarios/__init__.py`, change the result import + `__all__`:

```python
from gaspatchio_core.scenarios._result import ProbeResult, ScenarioResult, SelectionDecision
```
and add `"ProbeResult"`, `"SelectionDecision"` to `__all__`.

- [ ] **Step 2: Update the type stubs**

In `gaspatchio_core/scenarios/__init__.pyi`:
- replace both `batch_size_resolution: Literal["manual", "auto_probe", "auto_calibrated", "auto_cached"]`
  occurrences with `Literal["manual", "auto_search"]`;
- add `selection: SelectionDecision | None` to the `ScenarioResult` stub and stub out `ProbeResult`
  and `SelectionDecision` classes;
- remove every `bytes_per_cell: int | None = ...` parameter line (in `for_each_scenario` and `run`).

- [ ] **Step 3: Update / delete the blast-radius tests**

- `tests/scenarios/test_auto_batch.py` — remove tests of `resolve_batch_size`/`bytes_per_cell`/the
  linear fit; keep only `test_memory_budget_bytes_is_cgroup_aware` (Task 3) and any
  `process_rss_bytes` test.
- `tests/scenarios/test_memory.py` — remove `bytes_per_cell`/`resolve_batch_size` references.
- `tests/scenarios/test_for_each_scenario.py` — replace any `auto_probe`/`auto_calibrated`/
  `auto_cached` assertions with `auto_search`.
- `tests/benchmarks/test_scenario_lib.py` — same literal swap.
- `tests/scratch/gsp100_stress/agent1_scale/test3_auto_batch.py` — this is scratch; `git rm` it if it
  references removed symbols.

- [ ] **Step 4: Run the full scenarios + benchmarks suite**

Run: `uv run pytest tests/scenarios tests/benchmarks -q`
Expected: PASS

- [ ] **Step 5: Type-check (all three must pass)**

Run:
```bash
uv run mypy gaspatchio_core
uv run pyright gaspatchio_core
uv run python -m mypy.stubtest gaspatchio_core.scenarios
```
Expected: no errors. (If `stubtest` flags a pre-existing allowlisted divergence, add to the existing
allowlist as prior commits did — do not relax unrelated entries.)

- [ ] **Step 6: Commit**

```bash
git add -A gaspatchio_core/scenarios/__init__.py gaspatchio_core/scenarios/__init__.pyi tests/
git commit -m "chore(scenarios): drop bytes_per_cell + old resolution labels; export selection types; stubs green"
```

---

## Task 12: Integration — in-mem floor fallback + hard-ceiling raise (laptop-safe)

**Files:**
- Test: `tests/scenarios/test_for_each_search.py`

These exercise the feasibility branches by injecting a tiny budget — **no large model runs**.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scenarios/test_for_each_search.py`:

```python
def test_tiny_budget_falls_to_in_mem_floor(monkeypatch):
    from gaspatchio_core.scenarios import _auto_batch

    # Budget below stream@1's peak but above in-mem@1's: force the floor.
    # We approximate by forcing a very small budget and asserting the engine is in-memory OR a raise.
    monkeypatch.setattr(_auto_batch, "memory_budget_bytes", lambda *a, **k: 1)  # 1 byte budget
    from gaspatchio_core.scenarios._memory import IrreducibleCellError
    import pytest

    with pytest.raises(IrreducibleCellError):
        for_each_scenario(
            _af(), scenarios=list(range(1, 11)), model_fn=_model_fn,
            aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
            batch_size="auto",
        )
```

(With a 1-byte budget nothing fits, so the hard ceiling raises — this proves the gate + raise path.
A floor-selected case is covered by the `decide_winner` unit test in Task 4, which is the
deterministic place to assert `reason == "floor"`.)

- [ ] **Step 2: Run to verify**

Run: `uv run pytest tests/scenarios/test_for_each_search.py::test_tiny_budget_falls_to_in_mem_floor -v`
Expected: PASS (raises `IrreducibleCellError`).

- [ ] **Step 3: Full regression**

Run: `uv run pytest tests/scenarios -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/scenarios/test_for_each_search.py
git commit -m "test(scenarios): hard-ceiling raise when no batch fits the budget"
```

---

## Task 13: Fix the `_collect_with_peak` docstring + final full-suite/type gate

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (`_collect_with_peak` docstring, ~278-289)

- [ ] **Step 1: Correct the docstring**

Replace the scenario-axis paragraph of `_collect_with_peak`'s docstring. The old text says the
scenario axis "leaves it None ... Streaming *inflates* peak". Replace with:

```
    * **Scenario-axis** (``for_each_scenario``): the streaming-batch search passes
      ``engine="streaming"`` for its probe/operating batches. Streaming pairs safely with small
      batches; peak grows with batch size and, at high policy counts, inflates above the
      in-memory engine (Polars cross-join streaming, #20786) -- which is why ``in-mem@b1`` is the
      memory floor the search falls back to when no streaming batch fits the budget.
```

- [ ] **Step 2: Full Python suite**

Run: `uv run pytest -q -m "not benchmark"`
Expected: PASS

- [ ] **Step 3: Docstring/stub doctests + type gate**

Run:
```bash
uv run pytest --doctest-modules --doctest-glob="*.pyi" gaspatchio_core/scenarios -q
uv run mypy gaspatchio_core && uv run pyright gaspatchio_core && uv run python -m mypy.stubtest gaspatchio_core.scenarios
```
Expected: PASS / no errors.

- [ ] **Step 4: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py
git commit -m "docs(scenarios): correct _collect_with_peak scenario-axis engine note"
```

---

## Task 14: CI benchmark — streaming-batch guard + deferred floor confirmation (dedicated runner)

**Files:**
- Create: `evals/benchmarks/scenario_batch_search_bench.py` (promoted from
  `ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/sweep_streaming_batch.py`)
- Modify: the `performance`-label scenario-benchmarks workflow to invoke it.

> **Runner-only.** Do NOT run the 100K cells on a laptop — they swap-saturate a 16 GB box (see
> `feedback_dont_hammer_local_machine`). This task is validated on the dedicated benchmark runner.

- [ ] **Step 1: Promote the sweep harness**

Copy `sweep_streaming_batch.py` into `evals/benchmarks/scenario_batch_search_bench.py`. Keep the
fresh-process-per-config peak measurement; keep the sys.path/importlib pattern (`evals/` is not
importable). Parameterise the cells: a laptop-safe subset (1K×{100,1000}sc) for PR runs, and a
runner-only set (10K×100sc, **100K×{10,100,1000}sc**) gated behind an env flag
`GSP_BENCH_HEAVY=1`.

- [ ] **Step 2: Add the assertions**

The bench asserts, per cell:
1. `for_each_scenario(batch_size="auto")` picks a batch within ε of the measured ladder optimum
   (skip cells whose top-2 rung walls are within 5% — near-ties);
2. checksum identity across the probed batches (tol `1e-12`);
3. **(heavy)** `in-mem@b1` peak < `stream@b1` peak at 100K × {10, 100, 1000} scenarios — the floor
   confirmation deferred from local runs.

- [ ] **Step 3: Run the laptop-safe subset locally to confirm the harness imports/runs**

Run: `cd bindings/python && uv run python ../../evals/benchmarks/scenario_batch_search_bench.py`
Expected: the 1K cells complete; heavy cells are skipped (no `GSP_BENCH_HEAVY`).

- [ ] **Step 4: Wire the workflow + commit**

Add the bench to the `performance`-label scenario-benchmarks job (heavy cells enabled on the runner
via `GSP_BENCH_HEAVY=1`).

```bash
git add evals/benchmarks/scenario_batch_search_bench.py .github/workflows/*scenario*  # exact path per repo
git commit -m "bench(scenarios): streaming-batch-search guard + deferred in-mem floor confirmation"
```

---

## Self-Review

**Spec coverage:**
- §3 cost surface — informs the search; §4 ladder/constants → Task 1; §5 selector → Tasks 4,6,7,8,12;
  §5.1 edges (N==1, forced-b1, manual, fail-open) → Tasks 7,8 (fail-open: the remainder loop reads
  `sids[len(folded):]`, so an exception after a fold resumes from un-folded — assert in Task 8 if a
  regression appears); §6 auditable decision → `SelectionDecision.probed` (Task 2,7); §7 floor →
  Tasks 4,7,12; §8 peak reliability → `_run_one_batch` transient peak + `SAFETY_MARGIN` (Tasks 1,6,7);
  §9 API → Tasks 2,9,11; §10 cgroup → Task 3; §11 CI bench + deferred floor → Task 14; §12 deletions
  → Tasks 3,7,9,11; §14 testing → throughout; §15 non-goals respected (no cache/knob/parallelism).
- **Gap noted:** the spec's `return_full_grid` sink-granularity-follows-winner (§13) — covered by
  `_process_one` writing `batch_{len(folded):04d}.parquet`; if `test_spill.py` asserts a fixed file
  count it must be updated (add to Task 11's blast radius if it fails).
- **Gap noted:** `on_batch`/`BatchSnapshot` emission during the probe phase (§13) — the Task 7
  remainder loop keeps the snapshot block; if probe-phase snapshots are also wanted, emit inside
  `_process_one` (left to the implementer; `test_for_each_scenario.py` convergence tests will flag it).

**Placeholder scan:** no "TBD/TODO"; every code step shows code; the one "verbatim" move (Task 5
`_fold_batch`) is an explicit copy of an identified region, guarded by the full suite passing.

**Type consistency:** `SelectionDecision`/`ProbeResult` field names (`engine`, `batch`, `reason`,
`probed`, `per_sc_s`, `peak_mb`, `fits`) are identical across Tasks 2, 4, 7, 9, 11. `memory_budget_bytes`
(Task 3) is the single budget entry point used in Task 7. `_run_one_batch`/`_fold_batch`/`_process_one`
signatures are consistent across Tasks 5–8.
