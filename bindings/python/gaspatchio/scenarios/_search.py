# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Pure selector for batch_size="auto" -- coarse streaming-batch search +
# ABOUTME: in-mem floor.  Operates over already-measured rungs (ProbeResult); the
# ABOUTME: measurement loop lives in the caller.

"""Streaming-batch search and selection (shape-aware driver).

The optimum streaming batch is U-shaped in batch size and moves with the model,
so it is measured per run on real folded passes. The selector is pure; the
search requests real batches through a callback owned by the execution driver.
Memory gates and engine selection live here, independent of graph capture,
folding, output files and progress reporting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from gaspatchio.scenarios._auto_batch import _SAFETY_CEILING
from gaspatchio.scenarios._memory import DEFAULTS, IrreducibleCellError
from gaspatchio.scenarios._result import ProbeResult, SelectionDecision

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    _Measure = Callable[[int, Literal["streaming", "in-memory"]], tuple[int, float]]


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


def _probe(
    measure: _Measure,
    batch: int,
    engine: Literal["streaming", "in-memory"],
    budget_mb: float,
) -> ProbeResult:
    """Measure real work once; express time per scenario and memory in MiB."""
    peak, wall = measure(batch, engine)
    peak_mb = peak / 1024**2
    return ProbeResult(
        batch,
        engine,
        wall / batch,
        peak_mb,
        fits=_fits(peak_mb, budget_mb, DEFAULTS.safety_margin),
    )


def _search_engines(
    n_scenarios: int,
    measure: _Measure,
    budget_mb: float,
) -> SelectionDecision:
    """Compare engines at batch one for seeded or driver-based scenarios."""
    engines: tuple[Literal["streaming", "in-memory"], ...] = ("streaming", "in-memory")
    probed = [_probe(measure, 1, engine, budget_mb) for engine in engines[:n_scenarios]]
    fitting = [p for p in probed if p.fits]
    # Completed probes need no remaining-work memory protection.
    eligible = fitting or (probed if len(probed) == n_scenarios else [])
    if not eligible:
        msg = (
            "Forced batch_size=1 (master_seed / drivers-dict): neither the streaming "
            "nor the in-memory engine fits the memory budget at batch_size=1. Reduce "
            "policies, shorten the horizon, raise target_memory_fraction, or run on a "
            "box with more memory."
        )
        raise IrreducibleCellError(msg)
    winner = min(eligible, key=lambda p: p.per_sc_s)
    return SelectionDecision(winner.engine, 1, "forced_b1", probed)


def _predicted_to_fit(last: ProbeResult, batch: int, budget_mb: float) -> bool:
    """Gate larger probes before allocation, allowing for streaming inflation.

    The cross-join peak grows faster than linearly at high policy counts. The
    inflation factor protects against a probe that would die before reporting RSS.
    A missing reading retains the existing no-prediction behavior; a measured
    non-fitting rung already terminates the ladder.
    """
    if last.peak_mb is None:
        return True
    predicted = last.peak_mb * (batch / last.batch) * DEFAULTS.streaming_batch_inflation
    return _fits(predicted, budget_mb, DEFAULTS.safety_margin)


def _search_batches(
    n_scenarios: int,
    measure: _Measure,
    *,
    forced_one: bool,
    budget_mb: float,
) -> SelectionDecision:
    """Select a batch/engine by consuming real, consecutive batches exactly once.

    ``measure`` executes and folds the next requested number of scenarios. The
    caller owns execution and keeps the unconsumed suffix for the winning engine.
    The first streaming probe has no prior memory estimate; larger probes are gated.
    """
    if forced_one:
        return _search_engines(n_scenarios, measure, budget_mb)
    if n_scenarios == 1:
        return SelectionDecision("in-memory", 1, "single_scenario", [])
    probed: list[ProbeResult] = []
    remaining = n_scenarios
    for batch in build_ladder(
        n_scenarios=n_scenarios,
        ladder=DEFAULTS.ladder,
        ceiling=_SAFETY_CEILING,
    ):
        if batch > remaining or (
            probed and not _predicted_to_fit(probed[-1], batch, budget_mb)
        ):
            break
        result = _probe(measure, batch, "streaming", budget_mb)
        probed.append(result)
        remaining -= batch
        if not result.fits:
            break
    if not remaining:
        best = min(probed, key=lambda p: p.per_sc_s)
        return SelectionDecision("streaming", best.batch, "fastest_fitting", probed)
    floor = (
        None
        if any(p.fits for p in probed)
        else _probe(measure, 1, "in-memory", budget_mb)
    )
    return decide_winner(
        probed,
        budget_mb=budget_mb,
        safety_margin=DEFAULTS.safety_margin,
        floor=floor,
    )


__all__ = ["build_ladder", "decide_winner"]
