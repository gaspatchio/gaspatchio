# Cgroup-Aware Batch Sizing Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `for_each_scenario`'s batch sizer RAM-safe inside containers/cgroups by routing every memory budget through a cgroup-aware effective limit, subtracting resident base RSS, failing loud on an irreducible cell, and never reusing a cache entry learned under a different cap.

**Architecture:** Add one new pure module `scenarios/_memory.py` that answers "how many bytes may a batch use, honestly?" — reading the cgroup v1/v2 limit from an *injectable* `/sys/fs/cgroup` root + `/proc/self/cgroup` text (so it is unit-testable without containers), subtracting measured base RSS, and failing open to host RAM on any error. Then re-point the three cgroup-blind call sites (`_auto_batch.py:91`, `_for_each.py:493`, `_batch_profile.py:88`) at it. No behaviour changes on a roomy un-cgrouped box; on a capped box the picker now sees the real limit instead of host RAM.

**Tech Stack:** Python 3.12, `psutil` (host RAM only), `pytest` + `unittest.mock`, `dataclasses`, `pathlib`. Run tests with `uv run pytest` from `bindings/python/`.

**Plan series (context, not in this plan):** This is the safety-first lead the spec's §9 sequencing mandates. The follow-on plans are: **Plan 2** — `VectorAggregator` + `batch_reduce` seam + rank-free `Period*` family + `run_aggregated` driver + `AggregatedResult` + the axis-neutral `working_set_cap` + first-batch ramp on the thin policy axis; **Plan 3** — the policy-axis parquet **spill** sink (fix `_for_each.py:693`, tmpfs refusal, disk preflight, atomic rename) for C1-tight/C2; **Plan 4** — rank-based `PeriodQuantile/Median/CTE` via `SignedSketch.from_binned` + the dual-build correctness gate. Spec: `ref/42-scenario-auto-sizing/specs/2026-06-01-unified-aggregation-surface-design.md`.

---

## File Structure

- **Create** `bindings/python/gaspatchio_core/scenarios/_memory.py` — cgroup-aware effective limit, base-RSS, `memory_budget()`, the `SizingDefaults` constants dataclass, and `IrreducibleCellError`. One responsibility: the honest memory budget.
- **Create** `bindings/python/tests/scenarios/test_memory.py` — pure unit tests with faked cgroup roots (`tmp_path`) + injected `/proc/self/cgroup` text.
- **Modify** `bindings/python/gaspatchio_core/scenarios/_auto_batch.py` — replace `psutil.virtual_memory().available * fraction` (line 91-92) with `_memory.memory_budget(...)`; raise `IrreducibleCellError` when the picker clamps to `B==1` but one cell still exceeds the budget.
- **Modify** `bindings/python/gaspatchio_core/scenarios/_for_each.py` — route the calibration budget (line 493) through `_memory`; pass the effective cap into the cache env.
- **Modify** `bindings/python/gaspatchio_core/scenarios/_batch_profile.py` — add `effective_cap_bytes` to the cache env + `CacheEntry`, validate on it, bump `SCHEMA_VERSION` (so a `B` learned under host RAM is never reused under a 2 GB cap).
- **Modify** `bindings/python/tests/scenarios/test_auto_batch.py` — the existing tests mock `_auto_batch.psutil`; update them to also stub the cgroup read (fail-open path) so they keep asserting host-RAM behaviour, and add the `IrreducibleCellError` test.

---

## Task 1: `_memory.py` skeleton — constants dataclass + error type

**Files:**
- Create: `bindings/python/gaspatchio_core/scenarios/_memory.py`
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/scenarios/test_memory.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the cgroup-aware memory budget."""

from __future__ import annotations

from gaspatchio_core.scenarios._memory import DEFAULTS, IrreducibleCellError, SizingDefaults


def test_defaults_are_frozen_and_sane():
    assert isinstance(DEFAULTS, SizingDefaults)
    assert 0.0 < DEFAULTS.target_memory_fraction <= 1.0
    assert 0.0 < DEFAULTS.safety <= 1.0
    assert DEFAULTS.min_floor_bytes > 0
    assert DEFAULTS.abs_first_batch_bytes > 0


def test_irreducible_cell_error_is_runtime_error():
    assert issubclass(IrreducibleCellError, RuntimeError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaspatchio_core.scenarios._memory'`

- [ ] **Step 3: Write minimal implementation**

```python
# bindings/python/gaspatchio_core/scenarios/_memory.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Cgroup-aware memory budget for batch sizing (fail-open to host RAM).
# ABOUTME: All sizing constants live here in one auditable dataclass.

"""Honest memory budget for batch sizing.

Every batch-size budget routes through :func:`memory_budget`, which reads the
container/cgroup limit (v1/v2) from an *injectable* ``/sys/fs/cgroup`` root and
``/proc/self/cgroup`` text — so it is unit-testable without containers — subtracts
measured resident base RSS, and **fails open to host RAM** on any error. The sizer
must never be cgroup-blind: ``psutil.virtual_memory().available`` reports *host*
RAM, which OOM-kills inside a capped cgroup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SizingDefaults:
    """All batch-sizing constants in one auditable place (no scattered literals)."""

    target_memory_fraction: float = 0.5
    safety: float = 0.8
    min_floor_bytes: int = 1_000_000  # 1 MB noise floor for a measured per-cell cost
    abs_first_batch_bytes: int = 384 * 1024**2  # first-batch list-data ceiling (Plan 2)


DEFAULTS = SizingDefaults()


class IrreducibleCellError(RuntimeError):
    """A single batch cell (one scenario, or one policy) exceeds the memory budget.

    Raised instead of warn-and-collect so the run fails loudly with actionable
    guidance rather than being OOM-killed by the kernel mid-``.collect()``.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_memory.py bindings/python/tests/scenarios/test_memory.py
git commit -m "feat(scenarios): add SizingDefaults + IrreducibleCellError skeleton"
```

---

## Task 2: parse `/proc/self/cgroup` + read the cgroup memory limit (v1/v2)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_memory.py`
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
import pytest

from gaspatchio_core.scenarios._memory import read_cgroup_limit

_HOST = 64 * 1024**3  # 64 GB host


def _write(root, rel_files: dict[str, str]):
    for rel, content in rel_files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_v2_finite_limit_read(tmp_path):
    _write(tmp_path, {"mypod/memory.max": "1610612736"})  # 1.5 GB
    proc = "0::/mypod\n"
    assert read_cgroup_limit(tmp_path, proc, host_physical=_HOST) == 1_610_612_736


def test_v2_max_means_unlimited(tmp_path):
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    assert read_cgroup_limit(tmp_path, "0::/mypod\n", host_physical=_HOST) is None


def test_v2_walks_to_nearest_finite_parent(tmp_path):
    # leaf is 'max', parent slice sets 2 GB -> use the parent's 2 GB
    _write(tmp_path, {"slice/pod/memory.max": "max\n", "slice/memory.max": "2147483648\n"})
    assert read_cgroup_limit(tmp_path, "0::/slice/pod\n", host_physical=_HOST) == 2_147_483_648


def test_v1_sentinel_means_unlimited(tmp_path):
    _write(tmp_path, {"memory/mypod/memory.limit_in_bytes": "9223372036854771712\n"})
    proc = "5:memory:/mypod\n"
    assert read_cgroup_limit(tmp_path, proc, host_physical=_HOST) is None


def test_limit_at_or_above_host_is_unlimited(tmp_path):
    _write(tmp_path, {"mypod/memory.max": str(_HOST + 1)})
    assert read_cgroup_limit(tmp_path, "0::/mypod\n", host_physical=_HOST) is None


def test_no_cgroup_line_returns_none(tmp_path):
    assert read_cgroup_limit(tmp_path, "", host_physical=_HOST) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k cgroup_limit -v`
Expected: FAIL — `ImportError: cannot import name 'read_cgroup_limit'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_memory.py
from pathlib import Path

_V1_UNLIMITED = 0x7FFF_FFFF_FFFF_F000  # ~9.2 EB sentinel cgroup v1 uses for "unlimited"


def _parse_limit(raw: str, *, host_physical: int) -> int | None:
    """Parse one cgroup limit file value; None means 'unlimited / not a real cap'."""
    raw = raw.strip()
    if raw == "max":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value >= _V1_UNLIMITED or value >= host_physical:
        return None  # sentinel, or a limit at/above host RAM -> effectively unlimited
    return value


def _cgroup_rel(proc_cgroup_text: str) -> tuple[str, str] | None:
    """Return ('v2'|'v1', relpath) from /proc/self/cgroup, or None if absent."""
    v1: tuple[str, str] | None = None
    for line in proc_cgroup_text.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        hid, controllers, path = parts
        if hid == "0" and controllers == "":
            return ("v2", path)  # unified hierarchy
        if "memory" in controllers.split(","):
            v1 = ("v1", path)
    return v1


def read_cgroup_limit(
    root: Path, proc_cgroup_text: str, *, host_physical: int
) -> int | None:
    """Nearest finite cgroup memory limit (walking leaf->root), or None if unlimited.

    ``root`` is the ``/sys/fs/cgroup`` mount (injected for tests). ``proc_cgroup_text``
    is the contents of ``/proc/self/cgroup`` (injected for tests).
    """
    info = _cgroup_rel(proc_cgroup_text)
    if info is None:
        return None
    kind, rel = info
    parts = [p for p in rel.split("/") if p]
    if kind == "v2":
        base, fname = root, "memory.max"
    else:
        base, fname = root / "memory", "memory.limit_in_bytes"
    best: int | None = None
    for depth in range(len(parts), -1, -1):  # leaf first, then each parent slice
        directory = base.joinpath(*parts[:depth])
        try:
            value = _parse_limit(
                (directory / fname).read_text(), host_physical=host_physical
            )
        except OSError:
            value = None
        if value is not None:
            best = value if best is None else min(best, value)
    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k cgroup_limit -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_memory.py bindings/python/tests/scenarios/test_memory.py
git commit -m "feat(scenarios): read cgroup v1/v2 memory limit (walk slices, sentinels)"
```

---

## Task 3: cgroup usage + `effective_limit` (own-usage headroom, fail-open)

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_memory.py`
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
from gaspatchio_core.scenarios._memory import effective_limit, read_cgroup_usage


def test_usage_v2_read(tmp_path):
    _write(tmp_path, {"mypod/memory.current": "500000000\n"})
    assert read_cgroup_usage(tmp_path, "0::/mypod\n") == 500_000_000


def test_usage_missing_is_zero(tmp_path):
    assert read_cgroup_usage(tmp_path, "0::/mypod\n") == 0


def test_effective_limit_uses_cgroup_headroom(tmp_path):
    # 1.5 GB limit, 0.5 GB used -> 1.0 GB headroom; host has 64 GB -> min = 1.0 GB
    _write(tmp_path, {"mypod/memory.max": "1610612736", "mypod/memory.current": "536870912"})
    eff = effective_limit(
        host_available=64 * 1024**3, host_physical=64 * 1024**3,
        root=tmp_path, proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 1_610_612_736 - 536_870_912


def test_effective_limit_unlimited_falls_back_to_host(tmp_path):
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    eff = effective_limit(
        host_available=8 * 1024**3, host_physical=64 * 1024**3,
        root=tmp_path, proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 8 * 1024**3


def test_effective_limit_failopen_on_garbage(tmp_path):
    _write(tmp_path, {"mypod/memory.max": "not-a-number\n"})
    eff = effective_limit(
        host_available=8 * 1024**3, host_physical=64 * 1024**3,
        root=tmp_path, proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 8 * 1024**3  # parse failure -> host
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k "usage or effective_limit" -v`
Expected: FAIL — `ImportError: cannot import name 'effective_limit'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_memory.py
def read_cgroup_usage(root: Path, proc_cgroup_text: str) -> int:
    """Current usage of the process's own memory cgroup (0 if unreadable)."""
    info = _cgroup_rel(proc_cgroup_text)
    if info is None:
        return 0
    kind, rel = info
    parts = [p for p in rel.split("/") if p]
    if kind == "v2":
        base, fname = root, "memory.current"
    else:
        base, fname = root / "memory", "memory.usage_in_bytes"
    try:
        return int((base.joinpath(*parts) / fname).read_text().strip())
    except (OSError, ValueError):
        return 0


def effective_limit(
    *,
    host_available: int,
    host_physical: int,
    root: Path = Path("/sys/fs/cgroup"),
    proc_cgroup_text: str | None = None,
) -> int:
    """Bytes a batch may safely target: ``min(host_available, cgroup_headroom)``.

    Headroom is the cgroup's OWN limit minus its OWN usage (counts sidecars and
    page cache), NOT ``limit - own_process_rss``. Fails open to ``host_available``
    on any error so it is never worse than today.
    """
    try:
        if proc_cgroup_text is None:
            proc_cgroup_text = Path("/proc/self/cgroup").read_text()
        limit = read_cgroup_limit(root, proc_cgroup_text, host_physical=host_physical)
        if limit is None:
            return host_available
        usage = read_cgroup_usage(root, proc_cgroup_text)
        headroom = max(0, limit - usage)
        return min(host_available, headroom)
    except Exception:  # noqa: BLE001 — fail-open: never worse than host RAM
        return host_available
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k "usage or effective_limit" -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_memory.py bindings/python/tests/scenarios/test_memory.py
git commit -m "feat(scenarios): effective_limit via cgroup own-usage headroom, fail-open"
```

---

## Task 4: `memory_budget` — effective limit minus base RSS, times fraction

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_memory.py`
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
from gaspatchio_core.scenarios._memory import memory_budget


def test_budget_subtracts_base_rss_before_fraction(tmp_path):
    # unlimited cgroup -> host 8 GB; base 2 GB resident; fraction 0.5
    # (8 - 2) * 0.5 = 3 GB
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    b = memory_budget(
        0.5, host_available=8 * 1024**3, host_physical=64 * 1024**3,
        base_rss_bytes=2 * 1024**3, root=tmp_path, proc_cgroup_text="0::/mypod\n",
    )
    assert b == 3 * 1024**3


def test_budget_never_negative(tmp_path):
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    b = memory_budget(
        0.5, host_available=1 * 1024**3, host_physical=64 * 1024**3,
        base_rss_bytes=4 * 1024**3, root=tmp_path, proc_cgroup_text="0::/mypod\n",
    )
    assert b == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k budget -v`
Expected: FAIL — `ImportError: cannot import name 'memory_budget'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to gaspatchio_core/scenarios/_memory.py
import psutil


def base_rss_bytes() -> int:
    """Resident size of this process right now (interpreter + loaded tables)."""
    return int(psutil.Process().memory_info().rss)


def memory_budget(
    fraction: float,
    *,
    host_available: int | None = None,
    host_physical: int | None = None,
    base_rss_bytes: int | None = None,
    root: Path = Path("/sys/fs/cgroup"),
    proc_cgroup_text: str | None = None,
) -> int:
    """Bytes one batch may target. Cgroup-aware, base-RSS-subtracted, never negative.

    Defaults read live host RAM + base RSS; tests inject all three for determinism.
    """
    vm = psutil.virtual_memory()
    ha = host_available if host_available is not None else int(vm.available)
    hp = host_physical if host_physical is not None else int(vm.total)
    base = base_rss_bytes if base_rss_bytes is not None else globals()["base_rss_bytes"]()
    eff = effective_limit(
        host_available=ha, host_physical=hp, root=root, proc_cgroup_text=proc_cgroup_text
    )
    return max(0, int(fraction * (eff - base)))
```

> **Note for the implementer:** the local parameter `base_rss_bytes` shadows the function `base_rss_bytes`; the `globals()[...]()` call is deliberate so the default still calls the function. If you prefer, rename the parameter to `base` and call `base_rss_bytes()` directly — keep the public default behaviour identical and update the test kwarg name to match.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k budget -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_memory.py bindings/python/tests/scenarios/test_memory.py
git commit -m "feat(scenarios): memory_budget = fraction*(effective_limit - base_rss)"
```

---

## Task 5: route `resolve_batch_size` through the cgroup-aware budget

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_auto_batch.py:91-92`
- Test: `bindings/python/tests/scenarios/test_memory.py`, `bindings/python/tests/scenarios/test_auto_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
from unittest.mock import patch

from gaspatchio_core.scenarios._auto_batch import resolve_batch_size


def test_resolve_batch_size_respects_cgroup_cap(tmp_path):
    # Host says 64 GB, but the cgroup caps at 1 GB. per-cell 100 MB.
    # Pre-fix this would budget against 64 GB; now it must budget against ~1 GB.
    (tmp_path / "pod").mkdir()
    (tmp_path / "pod" / "memory.max").write_text("1073741824")   # 1 GB
    (tmp_path / "pod" / "memory.current").write_text("0")
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 64 * 1024**3
        mock_psutil.virtual_memory.return_value.total = 64 * 1024**3
        with patch(
            "gaspatchio_core.scenarios._auto_batch._cgroup_root", tmp_path
        ), patch(
            "gaspatchio_core.scenarios._auto_batch._proc_cgroup_text", "0::/pod\n"
        ), patch(
            "gaspatchio_core.scenarios._auto_batch._memory.base_rss_bytes", return_value=0
        ):
            size, resolution = resolve_batch_size(
                batch_size="auto", n_policies=1000, n_periods=240, n_scenarios=500,
                target_memory_fraction=0.5, bytes_per_cell=None,
                probe_fn=lambda k: 100 * 1024**2 * k,
            )
    assert resolution == "auto_probe"
    # ~1 GB * 0.5 * 0.8 / 100 MB ~= 4; certainly far below the ~256 a 64 GB budget gives
    assert size <= 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k cgroup_cap -v`
Expected: FAIL — `AttributeError` on `_cgroup_root` (not yet defined) or the budget still uses 64 GB (size too large).

- [ ] **Step 3: Write minimal implementation**

In `_auto_batch.py`, add module-level seams + replace the budget line. Near the imports:

```python
from pathlib import Path

from gaspatchio_core.scenarios import _memory

# Seams so tests can inject a fake cgroup root / proc text without a container.
_cgroup_root: Path = Path("/sys/fs/cgroup")
_proc_cgroup_text: str | None = None  # None -> read /proc/self/cgroup live
```

Replace lines 91-92:

```python
    available = psutil.virtual_memory().available
    target_bytes = int(available * target_memory_fraction)
```

with:

```python
    vm = psutil.virtual_memory()
    target_bytes = _memory.memory_budget(
        target_memory_fraction,
        host_available=int(vm.available),
        host_physical=int(vm.total),
        root=_cgroup_root,
        proc_cgroup_text=_proc_cgroup_text,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k cgroup_cap tests/scenarios/test_auto_batch.py -v`
Expected: PASS — the cgroup test passes; the existing `test_auto_batch.py` tests still pass (no cgroup files in `/sys/fs/cgroup` under the live root during those tests means fail-open to the mocked host `available`, so their numbers are unchanged). If any legacy test now reads a real cgroup on the CI box, pin it by also patching `_auto_batch._proc_cgroup_text=""` (no cgroup line -> host).

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_auto_batch.py bindings/python/tests/scenarios/test_memory.py bindings/python/tests/scenarios/test_auto_batch.py
git commit -m "fix(scenarios): route batch-size budget through cgroup-aware effective limit"
```

---

## Task 6: fail loud on an irreducible cell

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_auto_batch.py` (end of the probe path, before `return min(raw, n_scenarios, _SAFETY_CEILING)`)
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
import pytest

from gaspatchio_core.scenarios._memory import IrreducibleCellError


def test_irreducible_cell_raises_loud():
    # One cell needs 10 GB; budget is ~0.4 GB -> B would be 1 AND still over budget.
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 1 * 1024**3
        mock_psutil.virtual_memory.return_value.total = 1 * 1024**3
        with patch("gaspatchio_core.scenarios._auto_batch._proc_cgroup_text", ""), patch(
            "gaspatchio_core.scenarios._auto_batch._memory.base_rss_bytes", return_value=0
        ), pytest.raises(IrreducibleCellError, match="one batch cell"):
            resolve_batch_size(
                batch_size="auto", n_policies=100000, n_periods=240, n_scenarios=100,
                target_memory_fraction=0.5, bytes_per_cell=None,
                probe_fn=lambda k: 10 * 1024**3 * k,  # 10 GB per cell
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k irreducible_cell_raises -v`
Expected: FAIL — no exception raised (current code silently returns 1).

- [ ] **Step 3: Write minimal implementation**

In `_auto_batch.py`, add the import and the guard. At the top:

```python
from gaspatchio_core.scenarios._memory import IrreducibleCellError
```

Just before the final `return min(raw, n_scenarios, _SAFETY_CEILING), "auto_probe"` (after `raw` is computed from `per_cell`):

```python
    if raw < 1 or (target_bytes - fixed_overhead) < per_cell:
        msg = (
            "one batch cell needs more memory than the budget allows "
            f"(~{per_cell / 1024**2:.0f} MB/cell vs ~{target_bytes / 1024**2:.0f} MB budget). "
            "Reduce the per-cell footprint (fewer policies per scenario, shorter horizon, "
            "or column pruning), raise target_memory_fraction, or run on a box/cgroup with "
            "more memory."
        )
        raise IrreducibleCellError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py tests/scenarios/test_auto_batch.py -v`
Expected: PASS — the new test passes; `test_probe_path_clamps_to_one_when_tight` still passes (its per-cell 10 GB vs 0.5 GB budget now *raises*, so that legacy test must be updated to expect `IrreducibleCellError` — update it in this step).

Update `tests/scenarios/test_auto_batch.py::test_probe_path_clamps_to_one_when_tight` to assert the raise:

```python
def test_probe_path_clamps_to_one_when_tight():
    """A cell larger than the whole budget now fails loud, not silently to 1."""
    from gaspatchio_core.scenarios._memory import IrreducibleCellError
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 1 * 1024**3
        mock_psutil.virtual_memory.return_value.total = 1 * 1024**3
        with patch("gaspatchio_core.scenarios._auto_batch._proc_cgroup_text", ""), pytest.raises(
            IrreducibleCellError
        ):
            resolve_batch_size(
                batch_size="auto", n_policies=1000, n_periods=240, n_scenarios=500,
                target_memory_fraction=0.5, bytes_per_cell=None,
                probe_fn=lambda k: 10 * 1024**3 * k,
            )
```

Run again: `cd bindings/python && uv run pytest tests/scenarios/test_auto_batch.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_auto_batch.py bindings/python/tests/scenarios/test_memory.py bindings/python/tests/scenarios/test_auto_batch.py
git commit -m "feat(scenarios): IrreducibleCellError instead of silent clamp-to-1"
```

---

## Task 7: re-key the calibration cache on the effective cap

**Files:**
- Modify: `bindings/python/gaspatchio_core/scenarios/_batch_profile.py` (`SCHEMA_VERSION`, `CacheEntry`, `current_env`, `valid`)
- Test: `bindings/python/tests/scenarios/test_batch_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_batch_profile.py
from gaspatchio_core.scenarios import _batch_profile


def test_cache_invalid_when_effective_cap_changed():
    env_big = {**_batch_profile.current_env(), "effective_cap_bytes": 32 * 1024**3}
    env_small = {**_batch_profile.current_env(), "effective_cap_bytes": 2 * 1024**3}
    entry = _batch_profile.CacheEntry(
        plan_sha="p", shape_fp="s", cost_per_policy_per_scenario_bytes=1.0,
        recent_costs=[1.0], observed_peak_bytes=1, batch_used=1, n_policies=1,
        n_scenarios=1, box_total_ram_bytes=env_big["box_total_ram_bytes"],
        node=env_big["node"], polars_version=env_big["polars_version"],
        gaspatchio_version=env_big["gaspatchio_version"],
        effective_cap_bytes=32 * 1024**3,
    )
    assert _batch_profile.valid(entry, env=env_big) is True
    assert _batch_profile.valid(entry, env=env_small) is False  # B learned under 32G != 2G


def test_current_env_includes_effective_cap():
    assert "effective_cap_bytes" in _batch_profile.current_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_batch_profile.py -k effective_cap -v`
Expected: FAIL — `CacheEntry` has no `effective_cap_bytes`; `current_env` has no such key.

- [ ] **Step 3: Write minimal implementation**

In `_batch_profile.py`:

1. Bump the schema: `SCHEMA_VERSION = 2`.
2. Add a field to `CacheEntry` (after `box_total_ram_bytes`): `effective_cap_bytes: int = 0`.
3. In `current_env`, add the effective cap:

```python
    from gaspatchio_core.scenarios import _memory

    vm = psutil.virtual_memory()
    eff = _memory.effective_limit(host_available=int(vm.available), host_physical=int(vm.total))
    return {
        "polars_version": pl.__version__,
        "gaspatchio_version": gsp_version,
        "node": platform.node(),
        "box_total_ram_bytes": int(vm.total),
        "effective_cap_bytes": int(eff),
    }
```

4. In `valid`, add (before the final RAM check), with a 5% tolerance:

```python
    cap = env.get("effective_cap_bytes", 0)
    if cap > 0 and entry.effective_cap_bytes > 0:
        if abs(entry.effective_cap_bytes - cap) / cap > _RAM_TOLERANCE:
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_batch_profile.py -v`
Expected: PASS — new tests pass; existing ones pass (old-schema entries on disk fail `schema_version` and are treated as misses — fail-open, correct).

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/scenarios/_batch_profile.py bindings/python/tests/scenarios/test_batch_profile.py
git commit -m "feat(scenarios): re-key calibration cache on the effective (cgroup) cap"
```

---

## Task 8: integration gate — a simulated cgroup cap is never exceeded

**Files:**
- Test: `bindings/python/tests/scenarios/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scenarios/test_memory.py
def test_cgroup_cap_forces_small_batch_and_is_never_exceeded(tmp_path):
    """End-to-end: a 1 GB cgroup cap on a 64 GB host yields a small B sized to ~1 GB."""
    (tmp_path / "pod").mkdir()
    (tmp_path / "pod" / "memory.max").write_text(str(1 * 1024**3))
    (tmp_path / "pod" / "memory.current").write_text("0")
    per_cell = 100 * 1024**2  # 100 MB/scenario
    with patch("gaspatchio_core.scenarios._auto_batch.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.available = 64 * 1024**3
        mock_psutil.virtual_memory.return_value.total = 64 * 1024**3
        with patch("gaspatchio_core.scenarios._auto_batch._cgroup_root", tmp_path), patch(
            "gaspatchio_core.scenarios._auto_batch._proc_cgroup_text", "0::/pod\n"
        ), patch("gaspatchio_core.scenarios._auto_batch._memory.base_rss_bytes", return_value=0):
            size, _ = resolve_batch_size(
                batch_size="auto", n_policies=1000, n_periods=240, n_scenarios=500,
                target_memory_fraction=0.5, bytes_per_cell=None,
                probe_fn=lambda k: per_cell * k,
            )
    # The chosen batch's projected peak must fit the 1 GB cgroup budget, not host RAM.
    assert size * per_cell <= 1 * 1024**3
    assert size < 64  # nowhere near the ~256 a host-RAM budget would have allowed
```

- [ ] **Step 2: Run test to verify it fails... or passes**

Run: `cd bindings/python && uv run pytest tests/scenarios/test_memory.py -k never_exceeded -v`
Expected: PASS already (Tasks 5-6 implemented the behaviour). This task is the **standing gate** that locks it in; if it FAILS, a regression in Tasks 5-6 is present — fix there.

- [ ] **Step 3: (no new implementation — gate only)**

- [ ] **Step 4: Run the full scenarios suite**

Run: `cd bindings/python && uv run pytest tests/scenarios/ -q`
Expected: PASS (all green). Then type-check the new module:
Run: `cd bindings/python && uv run mypy gaspatchio_core/scenarios/_memory.py && uv run ruff check gaspatchio_core/scenarios/_memory.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/tests/scenarios/test_memory.py
git commit -m "test(scenarios): standing gate — cgroup cap forces small B, never exceeded"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** This plan implements spec §2.0 (effective limit, base-RSS subtraction), the cache re-key (§7 item 7), and `IrreducibleCellError` (§2.1). The first-batch ceiling + ramp, `working_set_cap`, axis-neutral generalization, `run_aggregated`, the `Period*` family, the parquet sink, and the rank-based sketch path are **Plans 2-4** (out of scope here, by design — safety-first sequencing).
- **Constants:** every new constant lives in `SizingDefaults` (Task 1) — do not scatter literals; the `abs_first_batch_bytes` default is defined here but only *consumed* in Plan 2.
- **Fail-open everywhere:** any cgroup read error must degrade to host RAM — never raise out of `_memory` except the deliberate `IrreducibleCellError` from the sizer.
- **No behaviour change off-cgroup:** on a box with no finite cgroup limit, `effective_limit` returns `host_available` and every existing test's numbers are unchanged.
