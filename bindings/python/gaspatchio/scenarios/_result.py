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
    written by :mod:`gaspatchio.scenarios._audit`.

    ``graph_fingerprint`` names the calculation the run folded -- the stamp
    the executed frame's own ``af.graph.fingerprint()`` carries -- so the run
    record and the calculation graph read as one chain from either end. It is
    populated only where the run was asked for an audit record, and it is
    ``None`` where the *scenarios* folded more than one graph, which is what
    a run that shocks an assumption table its model reads does by design: an
    assumption table's content hash is a section of that stamp. Asking the
    question of the scenarios rather than of the batches is what keeps the
    answer off the batch size the memory search settled on. See
    :func:`gaspatchio.scenarios._for_each.agreed_graph`.

    ``graph_fingerprint_by_scenario`` is that same question answered one
    scenario at a time -- each scenario identifier against the calculation
    that scenario folded -- which is a shocked run's real shape: one graph
    per basis, rather than one graph the run does not have. Each entry is
    what that scenario folds when it runs alone, so it reads the same
    however the run was batched, and an entry is ``None`` only where the
    stamp could not be taken. Populated only where the run was asked for an
    audit record.

    ``bases`` names, on a shocks plan, every assumption table a shock moved:
    the content fingerprint of the table the model read, which is the one
    the shock was applied to, and the file it was read from. ``None`` on the
    ids and drivers shapes, which shock nothing.

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
    graph_fingerprint: str | None = None
    graph_fingerprint_by_scenario: dict[str | int, str | None] | None = None
    bases: dict[str, dict[str, Any]] | None = None

    def fingerprint(self, scenario_id: str | int) -> str | None:
        """Return the calculation ``scenario_id`` folded, as it folds alone.

        On a shocks plan this is the scenario composed on its own -- the
        reconciled model over the book, reading only that scenario's shocked
        tables and columns -- so BASE's is the standalone model's own
        ``af.graph.fingerprint()``: a reviewer checks that BASE is the
        reconciled model rather than measuring it.

        Raises:
            ValueError: The run was not asked for an audit record, so no
                per-scenario fingerprint was taken.
            KeyError: ``scenario_id`` is not a scenario of this run.

        """
        if self.graph_fingerprint_by_scenario is None:
            msg = (
                "This run took no per-scenario fingerprints: they are taken "
                "where the run writes its audit record. Run with audit=True "
                "(or audit=<path>)."
            )
            raise ValueError(msg)
        if scenario_id not in self.graph_fingerprint_by_scenario:
            held = ", ".join(repr(s) for s in self.graph_fingerprint_by_scenario)
            msg = f"{scenario_id!r} is not a scenario of this run; it ran {held}."
            raise KeyError(msg)
        return self.graph_fingerprint_by_scenario[scenario_id]


__all__ = ["ProbeResult", "ScenarioResult", "SelectionDecision"]
