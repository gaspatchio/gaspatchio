# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: ScenarioResult - typed output of ScenarioRun.run / for_each_scenario.
# ABOUTME: Carries plan_sha plus runtime metadata (batch_size, peak_rss_mb).

"""Typed result envelope for stochastic runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path


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


@dataclass(frozen=True)
class ScenarioResult:
    """Output of ``ScenarioRun.run()`` or ``for_each_scenario``.

    Carries the aggregator outputs plus runtime metadata. ``plan_sha`` is
    the input identity (covers shocks, base_tables, aggregations, master_seed);
    ``batch_size`` is the resolved runtime value and **not** part of the SHA.
    ``n_batches`` is the number of batches folded during the run — runtime
    metadata, **not** part of ``plan_sha``; under ``batch_size='auto'`` this
    count **includes the streaming-search probe batches**, so it is telemetry
    only and will exceed the number of remainder batches.

    The ``aggregations`` mapping is keyed by the alias supplied to each
    aggregator via ``.alias(name)``. Values are scalars for non-partitioned
    aggregators (e.g. ``Sum``, ``Mean``, ``CTE``) and ``pl.DataFrame`` for
    partitioned aggregators created via ``.over(...)``.

    ``audit_path`` is set when ``ScenarioRun.run(..., audit=...)`` was
    truthy; otherwise it is ``None``. The path points to the JSON sidecar
    written by :mod:`gaspatchio_core.scenarios._audit`.

    ``selection`` is populated when ``batch_size='auto'`` was used; it
    carries the chosen engine/batch point and the full probe ladder for
    post-run inspection. ``None`` when ``batch_size`` was resolved manually.

    Notes:
        ``peak_rss_mb`` reports the **delta over the baseline RSS** sampled
        at loop entry, not absolute process RSS. The Python interpreter,
        loaded modules, and the base ``ActuarialFrame`` footprint are
        already paid for before ``for_each_scenario`` starts; the value
        you want when verifying the bounded-memory contract is the
        incremental cost of the scenario loop itself, which is what this
        field reports. ``None`` on platforms where psutil cannot read
        process RSS (sandboxes, restricted environments).

    """

    aggregations: dict[str, Any]
    plan_sha: str
    n_scenarios: int
    batch_size: int
    batch_size_resolution: Literal["manual", "auto_search"]
    wall_time_s: float
    peak_rss_mb: float | None
    n_batches: int
    sink_dir: Path | None
    selection: SelectionDecision | None = None
    audit_path: Path | None = None


__all__ = ["ProbeResult", "ScenarioResult", "SelectionDecision"]
