# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# functions/__init__.pyi

# Import and re-export types from submodules
from .conditional import when as when
from .vector import fill_series as fill_series

__all__ = [
    "fill_series",
    "when",
]
