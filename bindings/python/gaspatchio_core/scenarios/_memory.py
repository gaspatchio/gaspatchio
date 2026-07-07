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
from pathlib import Path

import psutil


@dataclass(frozen=True, slots=True)
class SizingDefaults:
    """All batch-sizing constants in one auditable place (no scattered literals)."""

    target_memory_fraction: float = 0.5
    # Streaming-batch search (shape-aware driver) + policy-axis budget sizer:
    ladder: tuple[int, ...] = (1, 4, 16, 64)  # geometric rungs to probe
    safety_margin: float = 1.3  # inflate measured/predicted peak before the budget comparison
    # Probe-gate inflation for the scenario cross-join under the STREAMING engine:
    # peak is NOT linear-in-batch at high policy counts (Polars #20786) -- a CI cell
    # measured the b=4 rung at ~8.6x the b=1 rung (2.2x above linear extrapolation).
    # The gate multiplies its linear prediction by this factor so it errs toward
    # skipping a rung (costing at most a smaller batch) rather than launching a
    # probe that exceeds physical memory (costing the process a kernel OOM-kill).
    streaming_batch_inflation: float = 3.0
    # Bounds the per-item-cost measurement sample so the seed never OOMs at large n
    # (per-item cost is linear -> a few thousand items estimate it as well as 10% of n).
    seed_sample_cap: int = 4096


DEFAULTS = SizingDefaults()


class IrreducibleCellError(RuntimeError):
    """A single batch cell (one scenario, or one policy) exceeds the memory budget.

    Raised instead of warn-and-collect so the run fails loudly with actionable
    guidance rather than being OOM-killed by the kernel mid-``.collect()``.
    """


_V1_UNLIMITED = 0x7FFF_FFFF_FFFF_F000  # ~9.2 EB sentinel cgroup v1 uses for "unlimited"
_CGROUP_LINE_PARTS = 3  # hierarchy-id:controllers:path


def _parse_limit(raw: str, *, host_physical: int) -> int | None:
    """Parse one cgroup limit file value; None means 'unlimited / not a real cap'."""
    raw = raw.strip()
    if raw == "max":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0 or value >= _V1_UNLIMITED or value >= host_physical:
        # non-positive (e.g. v1 '-1' / '0' for unlimited), the v1 sentinel, or a limit
        # at/above host RAM -> effectively unlimited. Returning <=0 verbatim would
        # collapse the budget to 0 and raise IrreducibleCellError on an unlimited box.
        return None
    return value


def _cgroup_rel(proc_cgroup_text: str) -> tuple[str, str] | None:
    """Return ('v2'|'v1', relpath) from /proc/self/cgroup, or None if absent."""
    v1: tuple[str, str] | None = None
    for line in proc_cgroup_text.splitlines():
        parts = line.split(":", 2)
        if len(parts) != _CGROUP_LINE_PARTS:
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
    """Tightest (minimum) finite cgroup memory limit walking all levels leaf to root.

    Returns None if every level is unlimited.

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


def read_cgroup_usage(root: Path, proc_cgroup_text: str) -> int:
    """Read current memory usage for the process's cgroup (returns 0 if unreadable)."""
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


def _tightest_headroom(
    root: Path, proc_cgroup_text: str, *, host_physical: int
) -> int | None:
    """Tightest finite ``limit - usage`` across all cgroup levels (leaf to root).

    Usage is read at the SAME level as its limit: ``memory.current`` /
    ``memory.usage_in_bytes`` at a parent counts ALL descendants, so
    ``parent_limit - leaf_usage`` would overstate headroom (sibling cgroups under the
    same parent limit are uncounted). Returns None if every level is unlimited.
    """
    info = _cgroup_rel(proc_cgroup_text)
    if info is None:
        return None
    kind, rel = info
    parts = [p for p in rel.split("/") if p]
    if kind == "v2":
        base, lim_f, use_f = root, "memory.max", "memory.current"
    else:
        base = root / "memory"
        lim_f, use_f = "memory.limit_in_bytes", "memory.usage_in_bytes"
    best: int | None = None
    for depth in range(len(parts), -1, -1):  # leaf first, then each parent slice
        directory = base.joinpath(*parts[:depth])
        try:
            limit = _parse_limit(
                (directory / lim_f).read_text(), host_physical=host_physical
            )
        except OSError:
            limit = None
        if limit is None:
            continue
        try:
            usage = int((directory / use_f).read_text().strip())
        except (OSError, ValueError):
            usage = 0
        headroom = max(0, limit - usage)
        best = headroom if best is None else min(best, headroom)
    return best


def effective_limit(
    *,
    host_available: int,
    host_physical: int,
    root: Path = Path("/sys/fs/cgroup"),
    proc_cgroup_text: str | None = None,
) -> int:
    """Bytes a batch may safely target: ``min(host_available, cgroup_headroom)``.

    Headroom is the BINDING level's own limit minus that SAME level's own usage
    (counts sidecars and page cache), NOT ``parent_limit - leaf_usage`` (which would
    overstate it). Fails open to ``host_available`` on any error so it is never worse
    than today.
    """
    try:
        if proc_cgroup_text is None:
            proc_cgroup_text = Path("/proc/self/cgroup").read_text()
        # read_cgroup_limit is called first so a monkeypatched failure (and the
        # all-unlimited case) fails open before the per-level headroom walk.
        limit = read_cgroup_limit(root, proc_cgroup_text, host_physical=host_physical)
        if limit is None:
            return host_available
        headroom = _tightest_headroom(
            root, proc_cgroup_text, host_physical=host_physical
        )
        if headroom is None:
            return host_available
        return min(host_available, headroom)
    except Exception:  # noqa: BLE001 — fail-open: never worse than host RAM
        return host_available


def current_base_rss() -> int:
    """Resident size of this process right now (interpreter + loaded tables)."""
    return int(psutil.Process().memory_info().rss)


def memory_budget(  # noqa: PLR0913
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
    base = base_rss_bytes if base_rss_bytes is not None else current_base_rss()
    eff = effective_limit(
        host_available=ha,
        host_physical=hp,
        root=root,
        proc_cgroup_text=proc_cgroup_text,
    )
    return max(0, int(fraction * (eff - base)))
