# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""compile_rollforward orchestrator — runs the 5-pass chain.

Accepts either a RollforwardBuilder (calling its ._build() to obtain an IR)
or an IR directly (useful for tests that bypass the builder).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from gaspatchio_core.rollforward._compiled import CompiledRollforward
from gaspatchio_core.rollforward._passes import (
    AssignCaptureSlots,
    FoldConstants,
    LowerToPolarsPlugin,
    ResolveStateRefs,
    Validate,
)

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._builder import RollforwardBuilder
    from gaspatchio_core.rollforward._ir import IR


def compile_rollforward(
    target: RollforwardBuilder | IR,
) -> CompiledRollforward:
    """Run the 5-pass chain over a Builder or an IR.

    Each pass logs a one-line TRACE record for observability:

        [validate]              ok — N transitions
        [resolve_state_refs]    ok
        [fold_constants]        ok
        [assign_capture_slots]  ok — N slots
        [lower_polars]          ok — N kwargs
    """
    from gaspatchio_core.rollforward._ir import IR as _IR

    ir: _IR = target if isinstance(target, _IR) else target._build()

    ir = Validate().apply(ir)
    logger.trace(f"[validate]              ok — {len(ir.transitions)} transitions")

    ir = ResolveStateRefs().apply(ir)
    logger.trace("[resolve_state_refs]    ok")

    ir = FoldConstants().apply(ir)
    logger.trace("[fold_constants]        ok")

    slots_pass = AssignCaptureSlots()
    ir, slots = slots_pass.apply_with_slots(ir)
    logger.trace(f"[assign_capture_slots]  ok — {len(slots)} slots")

    lower = LowerToPolarsPlugin()
    plugin_kwargs, plugin_args = lower.lower(ir, slots)
    logger.trace(f"[lower_polars]          ok — {len(plugin_kwargs)} kwargs")

    return CompiledRollforward(
        ir=ir,
        plugin_kwargs=plugin_kwargs,
        capture_slots=slots,
        plugin_args=tuple(plugin_args),
    )


__all__ = ["compile_rollforward"]
