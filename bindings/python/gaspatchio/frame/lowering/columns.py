# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Small Polars column-reference primitive shared by lowering clients."""

from __future__ import annotations

import polars as pl


def column_reference(name: str) -> pl.Expr:
    """Return Polars' expression for the column named ``name``."""
    return pl.col(name)
