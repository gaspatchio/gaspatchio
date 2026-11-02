# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Compiled kernel data shared by authoring, execution and audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

from gaspatchio.frame.lowering._polars.plugins import rollforward_kernel
from gaspatchio.rollforward import _registry
from gaspatchio.rollforward._canonical import identity_form
from gaspatchio.rollforward._explain import explain
from gaspatchio.rollforward._fingerprint import spec_fingerprint

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.rollforward._ir import IR
    from gaspatchio.rollforward._refs import StateRef


@dataclass(frozen=True)
class CompiledData:
    """Immutable values shared by lowering and audit, independent of authoring."""

    ir: IR
    plugin_kwargs: dict[str, Any]
    capture_slots: tuple[StateRef, ...]
    plugin_args: tuple[pl.Expr, ...] = field(default_factory=tuple)

    @cached_property
    def _hidden_column(self) -> str:
        """Name of the hidden struct column this rollforward materialises as.

        Named for the run -- the machine and the schedule it runs on -- and
        not for the machine alone, so one machine compiled on two schedules
        in one process materialises two kernel runs rather than sharing one.
        """
        return _registry.hidden_column_name(
            self.fingerprint(), self.ir.schedule.source_sha()
        )

    @cached_property
    def _cached_plugin_expr(self) -> pl.Expr:
        """The plugin expr built once per instance (exprs are immutable, shareable)."""
        return _raw_plugin_expr(self)

    def canonical_form(self) -> dict[str, Any]:
        """Return a stable, deterministic dict describing the model structure.

        This is the compilation body the artifact's
        ``gaspatchio_rollforward_ir`` facet publishes, less its ``schedule``:
        exactly what :meth:`fingerprint` is taken over. Two compiled
        rollforwards with the same Op chain (in the same order), same states,
        and same configuration produce equal canonical-form dicts, whatever
        schedule each was compiled on: the schedule is the data the machine
        runs over, not part of the machine. An operand is written as the
        operation tree the facet carries -- ``{"op": "col", "name":
        "premium"}`` -- so a rollforward reading ``prem`` where another reads
        ``premium`` has a different canonical form and, with it, a different
        fingerprint. An alias never reaches that tree: ``compile_rollforward``
        refuses ``pl.col("premium").alias("x")`` as an Op expression, because a
        compiled rollforward reads one named column of the frame at each
        period.
        """
        return identity_form(self.ir)

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint of the canonical form.

        Stable across runs and across machines for an unchanged model.
        Suitable for governance metadata and run logs. It identifies the
        machine -- every state, operation, operand, rounding and stopping
        rule -- and not the schedule it runs on, so re-sourcing the schedule
        leaves it where it was and editing the machine moves it. The run
        (machine and schedule together) is what the process resolves a
        compilation by; the schedule's own ``source_sha()`` names that half.
        A reader holding the artifact recomputes it from the published body
        (``gaspatchio.rollforward._canonical.compiled_identity``).
        """
        return self._fingerprint

    @cached_property
    def _fingerprint(self) -> str:
        """The fingerprint, taken once: building the body classifies every operand."""
        return spec_fingerprint(self.ir)

    def explain(self) -> str:
        """Return a multi-line human-readable summary of the model.

        Lists states, points, schedule, transitions in order, and the
        cross-cutting configuration (lapse, contract boundary, increment
        tracking). Plain text — fits in audit reports and TRACE logs.
        """
        return explain(self.ir)


def _raw_plugin_expr(compiled: CompiledData) -> pl.Expr:
    """Build the kernel call from its compiled argument payload."""
    return rollforward_kernel(compiled.plugin_args, compiled.plugin_kwargs)
