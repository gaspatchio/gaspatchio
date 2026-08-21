# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Internal helpers shared across polars_backend submodules.

Kept private (leading underscore) and small — anything that grows here
should justify its own module. Currently houses the proxy-unwrap helper
that plugins.py, operators.py, and masks.py all need.

The layering invariant for this subpackage: nothing in polars_backend/
imports from column/. Helpers that need to "see" frontend types use
duck-typing instead of isinstance.
"""

from __future__ import annotations

from typing import Any

import polars as pl


def _unwrap_proxy(expr: Any) -> pl.Expr | Any:  # noqa: ANN401
    """Unwrap ColumnProxy / ExpressionProxy to underlying pl.Expr.

    Backend equivalent of ``functions.utils.to_polars_expression``. Defined
    here (not imported from ``column/``) to keep the ``polars_backend →
    column/`` import direction empty. The two helpers cover the same
    operand shapes and are kept consistent by hand; the frontend version
    is typed against ``IntoExprColumn`` while this one is duck-typed for
    layering reasons.
    """
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        return pl.col(expr.name)
    if hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        return expr._expr  # noqa: SLF001
    return expr
