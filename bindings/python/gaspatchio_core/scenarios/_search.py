# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Pure selector for batch_size="auto" -- coarse streaming-batch search +
# ABOUTME: in-mem floor.  Operates over already-measured rungs (ProbeResult); the
# ABOUTME: measurement loop lives in the caller.

"""Streaming-batch search selector (shape-aware driver).

The optimum streaming batch is U-shaped in batch size and moves with the model,
so it is measured per run on real folded passes. This module is the *pure*
decision layer: given the measured ladder rungs and the memory budget, choose
the fastest rung whose peak fits, falling to the in-memory floor, or raising
when nothing fits.
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
    """Return True when the rung's peak inflated by safety_margin fits the budget.

    A missing reading (``None``) is treated conservatively as NOT fitting — never risk
    OOM on a rung we could not measure.
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
        safety_margin: multiplier applied to a measured peak before the budget
            comparison.
        floor: the measured in-mem@b1 fallback, or ``None`` if it was not
            measured (because a streaming rung already fit).

    Raises:
        IrreducibleCellError: when neither any streaming rung nor the floor fits.

    """
    annotated = [
        ProbeResult(
            p.batch,
            p.engine,
            p.per_sc_s,
            p.peak_mb,
            fits=_fits(p.peak_mb, budget_mb, safety_margin),
        )
        for p in probed
    ]
    fitting = [p for p in annotated if p.fits]
    if fitting:
        winner = min(fitting, key=lambda p: p.per_sc_s)
        return SelectionDecision(
            engine="streaming",
            batch=winner.batch,
            reason="fastest_fitting",
            probed=annotated,
        )
    if floor is not None and _fits(floor.peak_mb, budget_mb, safety_margin):
        annotated.append(
            ProbeResult(
                floor.batch, "in-memory", floor.per_sc_s, floor.peak_mb, fits=True
            )
        )
        return SelectionDecision(
            engine="in-memory", batch=floor.batch, reason="floor", probed=annotated
        )
    msg = (
        "No batch fits the memory budget: even in-memory batch_size=1 exceeds it. "
        "Reduce policies, shorten the horizon, raise target_memory_fraction, or run "
        "on a box/cgroup with more memory."
    )
    raise IrreducibleCellError(msg)


__all__ = ["build_ladder", "decide_winner"]
