# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Invoke a frame-only model once, preserving its declared diagnostic mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .base import ActuarialFrame


def run_model(
    model_func: Callable[[ActuarialFrame], ActuarialFrame | None],
    df: ActuarialFrame,
) -> ActuarialFrame:
    """Build a model once; a None return keeps the input frame.

    Debug mode adds tracing. Both modes leave collection to the caller,
    preserve a returned successor frame, and propagate the original exception.
    """
    mode = df._mode  # noqa: SLF001 -- frame.execution reads ActuarialFrame._mode beside it in gaspatchio.frame; the frame has no public accessor for its mode
    if mode not in {"debug", "optimize"}:
        msg = f"Unknown execution mode: {mode}"
        raise ValueError(msg)
    invoke = df.trace(model_func) if mode == "debug" else model_func
    result = invoke(df)
    return df if result is None else result
