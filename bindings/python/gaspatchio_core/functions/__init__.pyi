# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# functions/__init__.pyi
from __future__ import annotations

# Import and re-export types from submodules
from .conditional import when as when
from .vector import fill_series as fill_series
from .vector import floor as floor
from .vector import round as round
from .vector import round_to_int as round_to_int

__all__ = [
    "fill_series",
    "floor",
    "round",
    "round_to_int",
    "when",
]
