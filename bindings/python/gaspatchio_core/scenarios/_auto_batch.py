# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Memory budget seams for the streaming-batch search (cgroup-aware RSS).

"""Memory budget helpers for for_each_scenario / ScenarioRun.run.

Exposes the cgroup-aware memory budget and process RSS readers used by the
streaming-batch search. The ``_cgroup_root`` / ``_proc_cgroup_text`` seams let
tests inject a fake cgroup root / proc text without a container.
"""

from __future__ import annotations

from pathlib import Path

import psutil
from loguru import logger

from gaspatchio_core.scenarios import _memory

# Seams so tests can inject a fake cgroup root / proc text without a container.
_cgroup_root: Path = Path("/sys/fs/cgroup")
_proc_cgroup_text: str | None = None  # None -> read /proc/self/cgroup live

_SAFETY_CEILING = 256


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


def bounded_seed_size(n_items: int) -> int:
    """Sample size for estimating per-item cost: ~10% of n, capped so it never OOMs.

    The seed is a *measurement*, and per-item cost is linear — so a few thousand items
    estimate it as well as a proportional sample, and (unlike ``n // 10``) the seed
    never grows unbounded. Without the cap, the seed for very large ``n`` is itself a
    huge single collect that OOMs before the budget sizer ever runs.
    """
    return min(n_items, max(1, n_items // 10), _memory.DEFAULTS.seed_sample_cap)


def size_to_budget(
    per_cell_bytes: int,
    n_items: int,
    *,
    target_memory_fraction: float = _memory.DEFAULTS.target_memory_fraction,
    safety_margin: float = _memory.DEFAULTS.safety_margin,
) -> int:
    """Largest batch size in ``[1, n_items]`` whose predicted peak fits the budget.

    The policy axis is linear (no cross-join): a batch of ``B`` items peaks at
    ~``per_cell_bytes * B``. We require ``predicted * safety_margin <= budget``, so
    ``B = budget // (per_cell_bytes * safety_margin)``, clamped to ``[1, n_items]``.

    The margin governs sizing above one item; a single item that fits the RAW budget
    always runs (nothing smaller exists). Raises :class:`IrreducibleCellError` only
    when one item exceeds even the raw budget.

    Logs the full sizing decision (budget, free RAM, per-item cost, resolved batch,
    batch count, predicted peak) at ``DEBUG`` so the choice is auditable from the run
    log rather than inferred — visible under ``LOGURU_LEVEL=DEBUG`` (or ``TRACE``).
    """
    budget = memory_budget_bytes(target_memory_fraction)
    per_cell = max(1, int(per_cell_bytes))
    denom = max(1, int(per_cell * safety_margin))
    b = budget // denom
    if b < 1 and budget // per_cell < 1:
        msg = (
            "one item's projection exceeds the memory budget: even "
            "batch_size=1 does not fit. Reduce the horizon/columns, raise "
            "target_memory_fraction, or run on a box/cgroup with more memory."
        )
        raise _memory.IrreducibleCellError(msg)
    # b >= 1 -> margin honoured; else one item fits the raw budget so run it singly.
    resolved = int(min(b, n_items)) if b >= 1 else 1
    n_batches = (n_items + resolved - 1) // resolved
    available = psutil.virtual_memory().available
    logger.debug(
        "policy-axis sizer: budget={}MB (~{:.0%} of {}MB free), per_cell={}KB/item, "
        "n={}, B={} ({} batch(es)), predicted peak~{}MB (= budget/{} margin)",
        round(budget / 1024**2),
        (budget / available) if available else 0.0,
        round(available / 1024**2),
        round(per_cell / 1024, 1),
        n_items,
        resolved,
        n_batches,
        round(resolved * per_cell / 1024**2),
        safety_margin,
    )
    return resolved


__all__ = [
    "bounded_seed_size",
    "memory_budget_bytes",
    "process_rss_bytes",
    "size_to_budget",
]
