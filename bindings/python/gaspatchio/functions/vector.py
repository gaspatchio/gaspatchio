# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Backwards-compatible re-exports of plugin wrappers.

The actual implementations live in ``gaspatchio.polars_backend.plugins``.
This module exists to preserve the public import path
``from gaspatchio.functions.vector import accumulate`` (et al.) for
external code that depends on it.
"""

from gaspatchio.polars_backend.plugins import (
    accumulate,
    curve_eval,
    fill_series,
    list_clip,
    list_conditional,
    list_pow,
)

__all__ = [
    "accumulate",
    "curve_eval",
    "fill_series",
    "list_clip",
    "list_conditional",
    "list_pow",
]
