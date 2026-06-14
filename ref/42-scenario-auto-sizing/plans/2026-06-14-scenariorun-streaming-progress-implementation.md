# ScenarioRun Streaming + Progress Type — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `for_each_scenario`'s `on_batch`/`progress` hooks on `ScenarioRun.run()` (live observation only), enrich the shared `BatchSnapshot` into a progress type (`elapsed_s` + `fraction_done`/`eta_s`/`throughput`), and add `n_batches` to `ScenarioResult`.

**Architecture:** `ScenarioRun.run()` already delegates to `for_each_scenario`; the change is a parameter forward plus a small enrichment of the shared `BatchSnapshot` and `ScenarioResult`. No new modules. Streaming/timing are telemetry — excluded from the plan SHA (the SHA hashes the plan inputs, not the result).

**Tech Stack:** Python 3.12+, Polars, loguru, pytest. These are pure-Python changes — **no Rust/maturin rebuild**. The built extension already exists; run everything via `uv run --no-sync`.

**Spec:** `ref/42-scenario-auto-sizing/specs/2026-06-14-scenariorun-streaming-progress-design.md`

**Working dir:** `bindings/python` (all commands assume this cwd).

**Commit convention:** signed, conventional commits, **no AI/Co-Authored-By trailer**.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `gaspatchio_core/scenarios/_for_each.py` | `_fmt_duration` helper; `BatchSnapshot.elapsed_s` + 3 properties; populate `elapsed_s`; upgrade default progress hook; set `n_batches` at result construction | 1, 2, 3, 4 |
| `gaspatchio_core/scenarios/_result.py` | Add `n_batches` field | 4 |
| `gaspatchio_core/scenarios/_run.py` | Forward `progress`/`on_batch`; import `BatchSnapshot`; docstring | 5 |
| `tests/scenarios/test_result.py` | Add `n_batches=` to its 4 `ScenarioResult(...)` sites | 4 |
| `tests/scenarios/test_run_streaming.py` (new) | All new tests | 1–5 |
| `gaspatchio-docs/docs/concepts/scenarios/streaming-convergence.md` (separate repo) | Correct the sentence + table; show progress/ETA | 7 |

---

## Task 1: `_fmt_duration` helper

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (add module-level helper after line 77, before `@dataclass ... class BatchSnapshot`)
- Create: `tests/scenarios/test_run_streaming.py`

- [ ] **Step 1: Write the failing test** (creates the new test file)

```python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Streaming/progress tests for ScenarioRun.run and the BatchSnapshot progress type.
# ABOUTME: Covers _fmt_duration, snapshot properties, the progress hook, n_batches, live-channel.
"""Tests for ScenarioRun streaming + the BatchSnapshot progress type."""

from __future__ import annotations

import math
import sys

import polars as pl
import pytest
from loguru import logger

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    BatchSnapshot,
    ScenarioRun,
    Sum,
    for_each_scenario,
)
from gaspatchio_core.scenarios._for_each import _fmt_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (5.0, "5s"),
        (45.0, "45s"),
        (90.0, "1m30s"),
        (192.0, "3m12s"),
        (3840.0, "1h04m"),
    ],
)
def test_fmt_duration(seconds: float, expected: str) -> None:
    assert _fmt_duration(seconds) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_fmt_duration -q`
Expected: FAIL — `ImportError: cannot import name '_fmt_duration'`.

- [ ] **Step 3: Write minimal implementation**

In `gaspatchio_core/scenarios/_for_each.py`, add this module-level function immediately after the `ScenarioID = str | int` line (line 77), before the `@dataclass(frozen=True, slots=True)` decorator on `BatchSnapshot`:

```python
def _fmt_duration(seconds: float) -> str:
    """Render a wall-clock duration compactly: '45s', '3m12s', '1h04m'."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        minutes, secs = divmod(total, 60)
        return f"{minutes}m{secs:02d}s"
    hours, remainder = divmod(total, 3600)
    return f"{hours}h{remainder // 60:02d}m"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_fmt_duration -q`
Expected: PASS (5 parametrised cases).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_run_streaming.py
git commit -m "feat(scenarios): add _fmt_duration helper for progress/ETA rendering"
```

---

## Task 2: Enrich `BatchSnapshot` into a progress type

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (dataclass at lines 80–108; construction at lines 695–703)
- Modify: `tests/scenarios/test_run_streaming.py`

- [ ] **Step 1: Write the failing test** (append to `test_run_streaming.py`)

```python
def _snap(done: int, total: int, elapsed: float) -> BatchSnapshot:
    return BatchSnapshot(
        batch_idx=0,
        scenarios_done=done,
        total_scenarios=total,
        outputs={},
        peak_rss_mb=None,
        elapsed_s=elapsed,
    )


def test_snapshot_fraction_done() -> None:
    assert _snap(25, 100, 1.0).fraction_done == 0.25
    assert _snap(0, 0, 1.0).fraction_done == 0.0  # guard: empty run


def test_snapshot_eta_s() -> None:
    assert _snap(25, 100, 1.0).eta_s == pytest.approx(3.0)  # 1s for 25% -> 3s left
    assert _snap(0, 100, 1.0).eta_s is None  # no progress yet -> unknown
    assert _snap(100, 100, 5.0).eta_s == 0.0  # done -> nothing remaining


def test_snapshot_throughput() -> None:
    assert _snap(50, 100, 2.0).throughput == pytest.approx(25.0)
    assert _snap(10, 100, 0.0).throughput is None  # no elapsed time -> unknown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py -k snapshot -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'elapsed_s'`.

- [ ] **Step 3: Write minimal implementation** (two edits)

**Edit A** — in `gaspatchio_core/scenarios/_for_each.py`, the `BatchSnapshot` body. After the existing `peak_rss_mb: float | None` field (line 108), add the new field and three properties:

```python
    peak_rss_mb: float | None
    elapsed_s: float

    @property
    def fraction_done(self) -> float:
        """Fraction of real scenarios folded so far, in [0, 1]."""
        if self.total_scenarios == 0:
            return 0.0
        return self.scenarios_done / self.total_scenarios

    @property
    def eta_s(self) -> float | None:
        """Rough estimated seconds remaining; None before any progress.

        Linear extrapolation from elapsed wall time and fraction done. A guide
        only: under ``batch_size='auto'`` batch sizes vary (and the streaming
        search probes deliberately differ), so this is approximate. ``elapsed_s``
        includes probe time while ``scenarios_done`` excludes probe scenarios.
        """
        if self.scenarios_done >= self.total_scenarios:
            return 0.0
        if self.scenarios_done <= 0:
            return None
        return self.elapsed_s * (self.total_scenarios / self.scenarios_done - 1.0)

    @property
    def throughput(self) -> float | None:
        """Real scenarios folded per second so far; None if no time elapsed."""
        if self.elapsed_s <= 0:
            return None
        return self.scenarios_done / self.elapsed_s
```

Also add to the class docstring's `Attributes:` block (after the `peak_rss_mb` line):

```
        elapsed_s: Wall seconds since the run started, at the end of this
            batch. Combined with ``scenarios_done``/``total_scenarios`` it
            drives ``fraction_done``, ``eta_s`` and ``throughput``.
```

**Edit B** — in the same file, the `BatchSnapshot(...)` construction inside `_process_one` (lines 696–702). Add `elapsed_s` using the existing `started` closure variable (defined at line 623):

```python
                    BatchSnapshot(
                        batch_idx=batch_idx,
                        scenarios_done=len(folded),
                        total_scenarios=len(sids),
                        outputs=_snap_outputs,
                        peak_rss_mb=_snap_peak_mb,
                        elapsed_s=time.perf_counter() - started,
                    )
```

- [ ] **Step 4: Run tests to verify they pass** (new + regression)

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py -k snapshot -q && uv run --no-sync pytest tests/scenarios/test_for_each_streaming.py -q`
Expected: new snapshot tests PASS; `test_for_each_streaming.py` still PASS (every `on_batch` snapshot now carries `elapsed_s`).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_run_streaming.py
git commit -m "feat(scenarios): enrich BatchSnapshot with elapsed_s + fraction_done/eta_s/throughput"
```

---

## Task 3: Upgrade the default `progress=True` hook to %+ETA

**Files:**
- Modify: `gaspatchio_core/scenarios/_for_each.py` (lines 608–615)
- Modify: `tests/scenarios/test_run_streaming.py`

- [ ] **Step 1: Write the failing test** (append; also adds the shared fixture + model used by later tasks)

```python
@pytest.fixture
def af() -> ActuarialFrame:
    """Three-policy frame; _value_model adds `v` = premium."""
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _value_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    return af.with_columns(pl.col("premium").alias("v"))


def test_progress_logs_percent_and_eta(
    af: ActuarialFrame, capsys: pytest.CaptureFixture[str]
) -> None:
    sink_id = logger.add(sys.stderr, level="INFO", format="{message}")
    try:
        for_each_scenario(
            af,
            scenarios=[f"S{i}" for i in range(6)],
            model_fn=_value_model,
            aggregations=(Sum("v").alias("total"),),
            batch_size=2,
            progress=True,
        )
    finally:
        logger.remove(sink_id)
    err = capsys.readouterr().err
    assert "%" in err  # percent shown every batch
    assert "ETA" in err  # ETA shown on the non-final batches
    assert "6/6" in err  # final batch still reports counts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_progress_logs_percent_and_eta -q`
Expected: FAIL — current hook logs `"scenarios 2/6"` etc., so `"%"` / `"ETA"` are absent.

- [ ] **Step 3: Write minimal implementation**

In `gaspatchio_core/scenarios/_for_each.py`, replace the `_default_progress` definition (lines 608–615) with:

```python
    if progress and on_batch is None:
        # progress=True installs a built-in loguru-logging hook. If the user
        # ALSO passed an on_batch, their callback wins silently (no raise) and
        # progress is ignored — handled by the `and on_batch is None` guard.
        def _default_progress(snap: BatchSnapshot) -> None:
            eta = snap.eta_s
            tail = f" · ETA {_fmt_duration(eta)}" if eta else ""
            logger.info(
                "scenarios {}/{} ({:.0%}){}",
                snap.scenarios_done,
                snap.total_scenarios,
                snap.fraction_done,
                tail,
            )

        on_batch = _default_progress
```

- [ ] **Step 4: Run tests to verify they pass** (new + the existing progress regression)

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_progress_logs_percent_and_eta tests/scenarios/test_for_each_streaming.py::test_progress_installs_default_logging_hook -q`
Expected: both PASS (the line still contains `"scenarios"` and `"6/6"`, so the existing test holds).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_run_streaming.py
git commit -m "feat(scenarios): progress=True hook logs percent + ETA"
```

---

## Task 4: Add `n_batches` to `ScenarioResult`

**Files:**
- Modify: `gaspatchio_core/scenarios/_result.py` (fields at lines 78–82)
- Modify: `gaspatchio_core/scenarios/_for_each.py` (construction at line 845)
- Modify: `tests/scenarios/test_result.py` (4 `ScenarioResult(...)` sites at lines 21, 39, 54, 80)
- Modify: `tests/scenarios/test_run_streaming.py`

- [ ] **Step 1: Write the failing test** (append to `test_run_streaming.py`)

```python
def test_result_reports_n_batches(af: ActuarialFrame) -> None:
    res = for_each_scenario(
        af,
        scenarios=[f"S{i}" for i in range(7)],
        model_fn=_value_model,
        aggregations=(Sum("v").alias("total"),),
        batch_size=3,
    )
    assert res.n_batches == math.ceil(7 / 3)  # batches [3, 3, 1] -> 3
    assert res.wall_time_s > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_result_reports_n_batches -q`
Expected: FAIL — `AttributeError: 'ScenarioResult' object has no attribute 'n_batches'`.

- [ ] **Step 3: Write minimal implementation** (three edits)

**Edit A** — in `gaspatchio_core/scenarios/_result.py`, insert `n_batches: int` among the required fields (after `peak_rss_mb`, before `sink_dir`):

```python
    wall_time_s: float
    peak_rss_mb: float | None
    n_batches: int
    sink_dir: Path | None
    selection: SelectionDecision | None = None
    audit_path: Path | None = None
```

Add to the `ScenarioResult` docstring (near the `batch_size` note): `n_batches` is the number of folded batches — runtime metadata, **not** part of `plan_sha`.

**Edit B** — in `gaspatchio_core/scenarios/_for_each.py`, the result construction (line 845). After the loop, `batch_idx` equals the number of batches folded; add `n_batches=batch_idx`:

```python
    return ScenarioResult(
        aggregations=final,
        plan_sha=plan_sha,
        n_scenarios=len(sids),
        batch_size=resolved_size,
        batch_size_resolution=resolution,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=peak_rss_mb,
        n_batches=batch_idx,
        sink_dir=sink_dir if return_full_grid else None,
        selection=selection,
    )
```

**Edit C** — in `tests/scenarios/test_result.py`, each of the four `ScenarioResult(...)` constructions (lines ~21, 39, 54, 80) is missing the new required field. Add a `n_batches=8,` line immediately after the `peak_rss_mb=...,` line in **each** of the four calls. (The exact integer is irrelevant — those tests assert other fields; `8` is a placeholder value, not a placeholder instruction.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py::test_result_reports_n_batches tests/scenarios/test_result.py -q`
Expected: both PASS (the 4 `test_result.py` constructions now supply `n_batches`).

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_result.py gaspatchio_core/scenarios/_for_each.py tests/scenarios/test_result.py tests/scenarios/test_run_streaming.py
git commit -m "feat(scenarios): add n_batches run-summary to ScenarioResult"
```

---

## Task 5: Forward `progress`/`on_batch` on `ScenarioRun.run()`

**Files:**
- Modify: `gaspatchio_core/scenarios/_run.py` (TYPE_CHECKING block 18–25; signature 141–151; forward 190–202; docstring)
- Modify: `tests/scenarios/test_run_streaming.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_scenariorun_streams(af: ActuarialFrame) -> None:
    plan = ScenarioRun(
        shocks={f"S{i}": [] for i in range(6)},
        base_tables={},
        aggregations=(Sum("v").alias("total"),),
    )
    snaps: list[BatchSnapshot] = []
    plan.run(af, _value_model, batch_size=2, on_batch=snaps.append)
    assert len(snaps) == 3
    assert snaps[-1].scenarios_done == 6


def test_scenariorun_streaming_is_live_channel_only(af: ActuarialFrame) -> None:
    """on_batch must not change the run's identity (live channel only)."""
    plan = ScenarioRun(
        shocks={f"S{i}": [] for i in range(4)},
        base_tables={},
        aggregations=(Sum("v").alias("total"),),
    )
    quiet = plan.run(af, _value_model, batch_size=2)
    streamed = plan.run(af, _value_model, batch_size=2, on_batch=lambda _s: None)
    assert quiet.plan_sha == streamed.plan_sha == plan.source_sha()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py -k scenariorun -q`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'on_batch'`.

- [ ] **Step 3: Write minimal implementation** (four edits in `_run.py`)

**Edit A** — add `BatchSnapshot` to the TYPE_CHECKING block (lines 18–25):

```python
if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.frame import ActuarialFrame
    from gaspatchio_core.scenarios._for_each import BatchSnapshot
    from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned
    from gaspatchio_core.scenarios._result import ScenarioResult
    from gaspatchio_core.scenarios.shocks import Shock
```

**Edit B** — add the two params to `run()` (after `sink_dir`, before `audit`, lines 149–150):

```python
        sink_dir: Path | None = None,
        progress: bool = False,
        on_batch: Callable[[BatchSnapshot], None] | None = None,
        audit: bool | Path = False,
```

**Edit C** — forward them in the `for_each_scenario(...)` call (after `master_seed=self.master_seed,`, line 200):

```python
            master_seed=self.master_seed,
            progress=progress,
            on_batch=on_batch,
            plan_sha=plan_sha,
```

**Edit D** — add a paragraph to the `run()` docstring (before the closing `"""`, after the model-function contract):

```
        Streaming (``progress`` / ``on_batch``) is a **live observation
        channel** and does not change the run's identity: ``source_sha()``,
        ``canonical_form()``, and the audit sidecar are unaffected by
        ``on_batch``. To persist a convergence trace, write it from the
        callback. Under ``batch_size="auto"`` the batch boundaries (and thus
        the trace) are not reproducible.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/scenarios/test_run_streaming.py -k scenariorun -q`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_run.py tests/scenarios/test_run_streaming.py
git commit -m "feat(scenarios): surface on_batch/progress on ScenarioRun.run (live channel)"
```

---

## Task 6: Full-suite + type/lint gate

**Files:** none (verification only; commit only if a fixup is required).

- [ ] **Step 1: Full scenarios suite**

Run: `uv run --no-sync pytest tests/scenarios/ -q`
Expected: all PASS (no regressions; net new tests from `test_run_streaming.py`).

- [ ] **Step 2: Type check (both checkers, strict)**

Run: `uv run --no-sync mypy gaspatchio_core/scenarios/_for_each.py gaspatchio_core/scenarios/_result.py gaspatchio_core/scenarios/_run.py`
Then: `uv run --no-sync pyright gaspatchio_core/scenarios/_for_each.py gaspatchio_core/scenarios/_result.py gaspatchio_core/scenarios/_run.py`
Expected: both clean. (The `Callable[[BatchSnapshot], None]` annotation resolves via the TYPE_CHECKING import added in Task 5.)

- [ ] **Step 3: Lint**

Run: `uv run --no-sync ruff check gaspatchio_core/scenarios/_for_each.py gaspatchio_core/scenarios/_run.py gaspatchio_core/scenarios/_result.py tests/scenarios/test_run_streaming.py`
Expected: clean.

- [ ] **Step 4: Commit any fixups** (only if Steps 2–3 required edits)

```bash
git add -A
git commit -m "chore(scenarios): lint/type fixups for streaming progress type"
```

---

## Task 7: Docs (separate repo `gaspatchio-docs`)

**Files:**
- Modify: `../../../gaspatchio-docs/docs/concepts/scenarios/streaming-convergence.md`

This is a coupled change in a **separate repository** (its own branch/commit/PR). Do not commit it to `gaspatchio-core`.

- [ ] **Step 1: Read the current source** to locate the exact lines.

Run: `rg -n "in one piece|reproducible, hashable run|When to reach" ../../../gaspatchio-docs/docs/concepts/scenarios/streaming-convergence.md`

- [ ] **Step 2: Rewrite the positioning sentence.**

Replace:
> This is a feature of the raw scenario loop. The portfolio fold (`run_aggregated`) and the reproducible plan (`ScenarioRun`) return their results in one piece; `for_each_scenario` is the one that streams them as it goes.

With:
> `for_each_scenario` and the reproducible plan `ScenarioRun` both stream — pass `on_batch` (or `progress=True`) and you receive a `BatchSnapshot` after every batch. `ScenarioRun` simply forwards the hook to the same loop; the streamed partials are a live observation channel and do not affect the run's `source_sha()` or audit sidecar. The portfolio fold (`run_aggregated`) is the one that still returns its result in one piece.

- [ ] **Step 3: Update the "When to reach for `on_batch`" table.**

Change the `ScenarioRun` row from "A reproducible, hashable run → `ScenarioRun`" to note that `ScenarioRun(...).run(on_batch=...)` streams too (reproducible result **and** live observation). Keep the `run_aggregated` row as the non-streaming portfolio summary.

- [ ] **Step 4: Add progress%/ETA as a first-class use.**

Add a short subsection showing `snap.fraction_done`, `snap.eta_s`, and `snap.throughput`, and that `progress=True` logs `"47% · ETA 3m12s"`. Note ETA is approximate under `batch_size="auto"`.

- [ ] **Step 5: Build + commit in the docs repo.**

```bash
cd ../../../gaspatchio-docs && uv run mkdocs build 2>&1 | tail -5
git add docs/concepts/scenarios/streaming-convergence.md
git commit -m "docs(scenarios): ScenarioRun streams too; progress %/ETA as first-class on_batch uses"
```

---

## Notes for the executor

- **No maturin rebuild** — every change is pure Python; `uv run --no-sync` uses the existing built extension.
- **Out of scope** (do not implement here): `run_aggregated` streaming and convergence-based early-stop — both are captured follow-ups in the spec.
- **Determinism invariant** is pinned by `test_scenariorun_streaming_is_live_channel_only` (Task 5): timing/streaming must never enter `source_sha()`/`canonical_form()`.
