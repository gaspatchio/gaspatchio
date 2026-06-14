# Policy-Axis Parquet Spill Sink Implementation Plan (Plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the full per-policy-output path (cases C1-tight / C2: 100K–1M policies that genuinely need all 126 output columns) memory-safe by batching policies and **spilling each batch to parquet** — never co-resident — with a sink that refuses RAM-backed targets, preflights disk, and renames atomically.

**Architecture:** A new `run_to_parquet` driver reuses Plan 1's cgroup-aware sizer (with the working-set cap **off** — full output can't fold, so we batch purely for memory) and writes each batch's collected projection to `output_dir/batch_NNNN.parquet` via a hardened `safe_write_parquet`. A shared spill-safety module also fixes the existing scenario sink (`_for_each.py:693` hard-codes `sort("scenario_id")`, which `KeyError`s on a single run).

**Tech Stack:** Python 3.12, Polars `write_parquet`, `pathlib`, `os`/`shutil` (statvfs, disk_usage, atomic rename), `pytest`. **Depends on Plan 1** (`_memory.memory_budget`, `IrreducibleCellError`).

**Plan series:** Plan 1 ✅, Plan 2 ✅ (run_aggregated + Period*). Plan 4 = rank-based aggregates. Spec: `ref/42-scenario-auto-sizing/specs/2026-06-01-unified-aggregation-surface-design.md` (§2.2 C1/C2, §7).

---

## File Structure

- **Create** `bindings/python/gaspatchio_core/scenarios/_spill.py` — `fstype_for_path`, `check_spill_target`, `safe_write_parquet`, `preflight_disk`, and the `run_to_parquet` driver.
- **Modify** `bindings/python/gaspatchio_core/scenarios/_for_each.py` (lines ~692-695) — guard the `sort("scenario_id")` and route through `safe_write_parquet`.
- **Modify** `bindings/python/gaspatchio_core/scenarios/__init__.py`, `bindings/python/gaspatchio_core/__init__.py` — export `run_to_parquet`.
- **Test** `bindings/python/tests/scenarios/test_spill.py`.

---

## Task 1: refuse RAM-backed spill targets

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_spill.py`
- Test: `bindings/python/tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/scenarios/test_spill.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the policy-axis parquet spill sink."""

from __future__ import annotations

import pytest

from gaspatchio_core.scenarios._spill import check_spill_target, fstype_for_path

_MOUNTS = (
    "proc /proc proc rw 0 0\n"
    "/dev/disk1 / ext4 rw 0 0\n"
    "tmpfs /tmp tmpfs rw 0 0\n"
    "/dev/disk2 /data ext4 rw 0 0\n"
)


def test_fstype_picks_longest_matching_mount():
    assert fstype_for_path("/tmp/x/y", _MOUNTS) == "tmpfs"
    assert fstype_for_path("/data/out", _MOUNTS) == "ext4"
    assert fstype_for_path("/home/u", _MOUNTS) == "ext4"  # falls back to '/'


def test_check_spill_target_refuses_tmpfs(tmp_path):
    with pytest.raises(ValueError, match="RAM-backed"):
        check_spill_target(tmp_path, mounts_text=_MOUNTS, resolved="/tmp/run")


def test_check_spill_target_allows_real_disk(tmp_path):
    # ext4 mount -> OK (returns None)
    check_spill_target(tmp_path, mounts_text=_MOUNTS, resolved="/data/run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k "fstype or refuses or allows" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._spill'`

- [ ] **Step 3: Write minimal implementation**

```python
# bindings/python/gaspatchio_core/scenarios/_spill.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Policy-axis parquet spill: write each batch to disk, never co-resident.
# ABOUTME: Refuses RAM-backed targets, preflights disk, renames atomically.

"""Memory-safe full-output spill for run_to_parquet (and the scenario sink fix)."""

from __future__ import annotations

from pathlib import Path

_RAM_BACKED = frozenset({"tmpfs", "ramfs"})


def fstype_for_path(path: str, mounts_text: str) -> str | None:
    """Filesystem type of the longest mountpoint that is a prefix of ``path``.

    ``mounts_text`` is the contents of ``/proc/mounts`` (injected for tests).
    """
    best_len = -1
    best_fs: str | None = None
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint, fstype = parts[1], parts[2]
        mp = mountpoint.rstrip("/") or "/"
        if (path == mp or path.startswith(mp + "/") or mp == "/") and len(mp) > best_len:
            best_len, best_fs = len(mp), fstype
    return best_fs


def check_spill_target(
    directory: Path, *, mounts_text: str | None = None, resolved: str | None = None
) -> None:
    """Raise if ``directory`` is RAM-backed (tmpfs/ramfs) — spilling there re-OOMs."""
    resolved = resolved if resolved is not None else str(directory.resolve())
    if mounts_text is None:
        try:
            mounts_text = Path("/proc/mounts").read_text()
        except OSError:
            return  # non-Linux / unreadable -> can't check, allow (best effort)
    fstype = fstype_for_path(resolved, mounts_text)
    if fstype in _RAM_BACKED:
        msg = (
            f"Spill target {directory} is on a RAM-backed filesystem ({fstype}); "
            "writing batches there counts against the same memory cgroup and re-OOMs. "
            "Choose an output_dir on a real disk."
        )
        raise ValueError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k "fstype or refuses or allows" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_spill.py bindings/python/tests/scenarios/test_spill.py
git commit -m "feat(scenarios): refuse RAM-backed (tmpfs/ramfs) spill targets"
```

---

## Task 2: atomic same-dir parquet write

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_spill.py`
- Test: `bindings/python/tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_spill.py
import polars as pl

from gaspatchio_core.scenarios._spill import safe_write_parquet


def test_safe_write_creates_final_and_no_temp(tmp_path):
    df = pl.DataFrame({"a": [1, 2, 3]})
    final = tmp_path / "batch_0000.parquet"
    safe_write_parquet(df, final)
    assert final.exists()
    assert pl.read_parquet(final)["a"].to_list() == [1, 2, 3]
    # no leftover temp files in the directory
    assert list(tmp_path.glob("*.tmp")) == []


def test_safe_write_temp_is_same_directory(tmp_path, monkeypatch):
    seen: dict[str, Path] = {}
    real_replace = __import__("os").replace

    def spy(src, dst):
        seen["src_parent"] = Path(src).parent
        seen["dst_parent"] = Path(dst).parent
        real_replace(src, dst)

    monkeypatch.setattr("gaspatchio_core.scenarios._spill.os.replace", spy)
    safe_write_parquet(pl.DataFrame({"a": [1]}), tmp_path / "x.parquet")
    assert seen["src_parent"] == seen["dst_parent"]  # same FS -> atomic rename works
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k safe_write -v`
Expected: FAIL — `ImportError: cannot import name 'safe_write_parquet'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_spill.py
import os


def safe_write_parquet(frame: object, final_path: Path) -> None:
    """Write a Polars DataFrame to ``final_path`` atomically.

    Writes to a temp file in the SAME directory (so ``os.replace`` is a real atomic
    rename — cross-filesystem rename would raise ``EXDEV``), then renames.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = final_path.with_suffix(final_path.suffix + ".tmp")
    try:
        frame.write_parquet(tmp)  # type: ignore[attr-defined]
        os.replace(tmp, final_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k safe_write -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_spill.py bindings/python/tests/scenarios/test_spill.py
git commit -m "feat(scenarios): atomic same-dir parquet write (avoids EXDEV)"
```

---

## Task 3: disk-space preflight

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_spill.py`
- Test: `bindings/python/tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_spill.py
from gaspatchio_core.scenarios._spill import preflight_disk


def test_preflight_passes_when_room(tmp_path):
    preflight_disk(tmp_path, estimated_bytes=1)  # ~unlimited vs 1 byte -> OK


def test_preflight_fails_loud_when_insufficient(tmp_path, monkeypatch):
    import shutil

    monkeypatch.setattr(
        "gaspatchio_core.scenarios._spill.shutil.disk_usage",
        lambda _p: shutil._ntuple_diskusage(total=10, used=9, free=1),
    )
    with pytest.raises(OSError, match="insufficient disk"):
        preflight_disk(tmp_path, estimated_bytes=1_000_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k preflight -v`
Expected: FAIL — `ImportError: cannot import name 'preflight_disk'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_spill.py
import shutil

_DISK_HEADROOM = 1.10  # require 10% slack over the estimate


def preflight_disk(directory: Path, *, estimated_bytes: int) -> None:
    """Raise OSError before batch 1 if ``directory``'s filesystem lacks room."""
    free = shutil.disk_usage(directory).free
    needed = int(estimated_bytes * _DISK_HEADROOM)
    if free < needed:
        msg = (
            f"insufficient disk for spill at {directory}: need ~{needed / 1024**3:.1f} GB, "
            f"have {free / 1024**3:.1f} GB free."
        )
        raise OSError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k preflight -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_spill.py bindings/python/tests/scenarios/test_spill.py
git commit -m "feat(scenarios): disk-space preflight before spilling"
```

---

## Task 4: `run_to_parquet` driver

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_spill.py`
- Test: `bindings/python/tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_spill.py
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios._spill import run_to_parquet


def _toy_full_model(af: ActuarialFrame) -> ActuarialFrame:
    df = af._df.with_columns((pl.col("value") * 10).alias("scaled"))  # noqa: SLF001
    return ActuarialFrame(df)


def test_run_to_parquet_writes_all_policies(tmp_path):
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    out = run_to_parquet(_toy_full_model, mp, tmp_path / "out", batch_size=3)
    # 10 policies / 3 -> 4 batch files
    files = sorted((tmp_path / "out").glob("batch_*.parquet"))
    assert len(files) == 4
    combined = pl.concat([pl.read_parquet(f) for f in files]).sort("value")
    assert combined["scaled"].to_list() == [v * 10 for v in range(1, 11)]
    assert out.n_policies == 10
    assert out.n_batches == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k run_to_parquet -v`
Expected: FAIL — `ImportError: cannot import name 'run_to_parquet'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_spill.py
import time
from dataclasses import dataclass
from typing import Callable, Literal

import psutil

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import _memory
from gaspatchio_core.scenarios._for_each import _collect_with_peak


@dataclass(frozen=True)
class SpillResult:
    """Manifest of a run_to_parquet spill."""

    output_dir: Path
    n_policies: int
    n_batches: int
    wall_time_s: float
    peak_rss_mb: float | None


def run_to_parquet(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: object,
    output_dir: Path,
    *,
    batch_size: int | Literal["auto"] = "auto",
    mounts_text: str | None = None,
) -> SpillResult:
    """Project all policies in memory-safe batches, writing each batch to parquet.

    For the full per-policy output (C1-tight/C2) that cannot fold to aggregates.
    The working-set cap is OFF here — batching is purely for memory safety.
    """
    n_policies = model_points.height  # type: ignore[attr-defined]
    if n_policies == 0:
        msg = "model_points is empty."
        raise ValueError(msg)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    check_spill_target(output_dir, mounts_text=mounts_text)

    if batch_size == "auto":
        # Size to memory only (no working-set cap): one seed batch -> per_cell -> B.
        seed = min(n_policies, max(1, n_policies // 10))
        seed_lazy = model_fn(ActuarialFrame(model_points.slice(0, seed)))._df  # noqa: SLF001
        _seed_df, seed_peak = _collect_with_peak(seed_lazy)
        per_cell = max(1, seed_peak // max(1, seed))
        preflight_disk(output_dir, estimated_bytes=per_cell * n_policies)
        budget = _memory.memory_budget(0.5)
        resolved = max(1, budget // per_cell)
        if resolved < 1:
            raise _memory.IrreducibleCellError("one policy's full output exceeds the budget.")
        resolved = int(min(resolved, n_policies))
        del _seed_df
    else:
        resolved = int(batch_size)

    started = time.perf_counter()
    baseline = psutil.Process().memory_info().rss
    peak = baseline
    batch_idx = 0
    for start in range(0, n_policies, resolved):
        batch = model_points.slice(start, resolved)  # type: ignore[attr-defined]
        proj, _ = _collect_with_peak(model_fn(ActuarialFrame(batch))._df)  # noqa: SLF001
        safe_write_parquet(proj, output_dir / f"batch_{batch_idx:04d}.parquet")
        del proj
        peak = max(peak, psutil.Process().memory_info().rss)
        batch_idx += 1

    return SpillResult(
        output_dir=output_dir,
        n_policies=n_policies,
        n_batches=batch_idx,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=max(0, peak - baseline) / (1024 * 1024),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_spill.py bindings/python/tests/scenarios/test_spill.py
git commit -m "feat(scenarios): run_to_parquet — memory-safe full-output spill driver"
```

---

## Task 5: fix the scenario sink for the policy axis + export

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_for_each.py:692-695`
- Modify: `bindings/python/gaspatchio_core/scenarios/__init__.py`, `bindings/python/gaspatchio_core/__init__.py`
- Test: `bindings/python/tests/scenarios/test_spill.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_spill.py
def test_for_each_sink_does_not_require_scenario_id(tmp_path):
    """A frame with NO scenario_id column must spill without a KeyError."""
    df = pl.DataFrame({"policy": [1, 2, 3], "v": [1.0, 2.0, 3.0]})
    from gaspatchio_core.scenarios._for_each import _write_batch_parquet

    _write_batch_parquet(df, tmp_path / "b0.parquet")  # must not raise
    assert pl.read_parquet(tmp_path / "b0.parquet")["policy"].to_list() == [1, 2, 3]


def test_run_to_parquet_top_level_export():
    import gaspatchio_core as gsp

    assert hasattr(gsp, "run_to_parquet")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_spill.py -k "sink or top_level" -v`
Expected: FAIL — `ImportError: cannot import name '_write_batch_parquet'`; `gsp.run_to_parquet` missing.

- [ ] **Step 3: Write minimal implementation**

1. In `_for_each.py`, add a small helper and use it. Replace the existing block (lines ~692-695):

```python
        if return_full_grid and sink_dir is not None:
            proj_eager.sort("scenario_id").write_parquet(
                sink_dir / f"batch_{batch_idx:04d}.parquet",
            )
```

with:

```python
        if return_full_grid and sink_dir is not None:
            _write_batch_parquet(proj_eager, sink_dir / f"batch_{batch_idx:04d}.parquet")
```

and add the helper near the top of `_for_each.py` (after imports):

```python
from gaspatchio_core.scenarios._spill import safe_write_parquet


def _write_batch_parquet(frame: pl.DataFrame, path: Path) -> None:
    """Sort by scenario_id only if present (the policy axis has none), then write."""
    if "scenario_id" in frame.columns:
        frame = frame.sort("scenario_id")
    safe_write_parquet(frame, path)
```

2. In `scenarios/__init__.py` and `gaspatchio_core/__init__.py`, export `run_to_parquet` (and `SpillResult`); add to `__all__`:

```python
from gaspatchio_core.scenarios._spill import SpillResult, run_to_parquet
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/ -q`
Expected: PASS (all green). Then:
Run: `cd bindings/python && uv run mypy gaspatchio_core/scenarios/_spill.py && uv run ruff check gaspatchio_core/scenarios/_spill.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_for_each.py bindings/python/gaspatchio_core/scenarios/__init__.py bindings/python/gaspatchio_core/__init__.py bindings/python/tests/
git commit -m "fix(scenarios): policy-axis-safe parquet sink; export run_to_parquet"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** implements §2.2 C1-tight/C2 (full output made memory-safe by spill), §7 sink fixes (the `_for_each.py:693` `sort("scenario_id")` KeyError, tmpfs refusal, disk preflight, atomic rename), and the "policy-axis sink is NEW code, not reuse" correction.
- **Why `run_to_parquet` is separate from `run_aggregated`:** they answer different questions (full output vs aggregates). They share the sizer (`_memory`) and the spill helpers, not the driver. Keep them distinct (spec §5 "don't overload").
- **`_DISK_HEADROOM` / `_RAM_BACKED`:** module constants here; if Plan 1's `SizingDefaults` is the single defaults home, move them there in a later tidy-up.
- **Type note:** `model_points` is a `pl.DataFrame`; typed as `object` only to avoid importing polars types into the signature where the existing modules use the same pattern — keep consistent with `_aggregated.py`.
