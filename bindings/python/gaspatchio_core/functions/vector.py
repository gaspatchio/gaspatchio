# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Backwards-compatible re-exports of plugin wrappers.

The actual implementations live in ``gaspatchio_core.polars_backend.plugins``.
This module exists to preserve the public import path
``from gaspatchio_core.functions.vector import accumulate`` (et al.) for
external code that depends on it.
"""

from gaspatchio_core.polars_backend.plugins import (
    accumulate,
    curve_eval,
    fill_series,
    floor,
    list_clip,
    list_conditional,
    list_pow,
    round,
    round_to_int,
)

__all__ = [
    "accumulate",
    "curve_eval",
    "fill_series",
    "floor",
    "list_clip",
    "list_conditional",
    "list_pow",
    "round",
    "round_to_int",
]
