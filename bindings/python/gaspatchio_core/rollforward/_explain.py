# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Actuary-readable rendering of an IR.

Output is plain text (not Markdown) — fits in audit reports and TRACE logs.
Mirrors the format from spec §9.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.rollforward._engine_binding import derive_engine_binding
from gaspatchio_core.rollforward._fingerprint import spec_fingerprint

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR


def explain(ir: IR) -> str:
    """Return a multi-line human-readable summary of an IR."""
    lines: list[str] = []

    fp = spec_fingerprint(ir)
    lines.append(f"Rollforward (spec_fingerprint = {fp})")
    lines.append("")

    lines.append("States:")
    lines.extend(f"  {s.name}:  init={s.init}" for s in ir.states)
    lines.append("")

    lines.append(f"Points:  {', '.join(ir.points)}")
    lines.append("")

    sched_cf = ir.schedule.canonical_form()
    lines.append(f"Schedule: {sched_cf['kind']}({sched_cf})")
    lines.append("")

    lines.append("Transitions (in order):")
    for op in ir.transitions:
        op_name = type(op).__name__
        target = getattr(op, "target", None)
        target_str = target.canonical_name() if target is not None else "<no target>"
        label = getattr(op, "label", None)
        label_str = f"  [label={label!r}]" if label else ""
        lines.append(f"  {target_str}  {op_name}{label_str}")
    lines.append("")

    lines.append(f"batch_axes: {ir.batch_axes}")
    lines.append(f"track_increments: {ir.track_increments}")
    lines.append(
        f"lapse_when_all_non_positive: {sorted(ir.lapse_when_all_non_positive)}",
    )
    lines.append(
        f"contract_boundary: {'<set>' if ir.contract_boundary is not None else 'None'}",
    )
    lines.append(f"engine_binding: {derive_engine_binding(ir)}")

    return "\n".join(lines)


__all__ = ["explain"]
