# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""compile_rollforward orchestrator — runs the 5-pass chain.

Accepts either a RollforwardBuilder (calling its ._build() to obtain an IR)
or an IR directly (useful for tests that bypass the builder).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio.rollforward._compiled import CompiledRollforward
from gaspatchio.rollforward._ir import IR
from gaspatchio.rollforward._passes import _compile_ir

if TYPE_CHECKING:
    from gaspatchio.rollforward._builder import RollforwardBuilder


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
    ir: IR = target if isinstance(target, IR) else target._build()

    compiled = _compile_ir(ir, CompiledRollforward)
    if not isinstance(target, IR):
        # Not a field: the frame is no part of what was compiled, and two
        # compilations of one chain stay equal whichever frame they read.
        object.__setattr__(compiled, "_frame_ref", target._frame_ref)
    return compiled


__all__ = ["compile_rollforward"]
