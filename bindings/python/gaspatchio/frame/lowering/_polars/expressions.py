# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""ABOUTME: Utility functions for Excel and other function implementations.

ABOUTME: Provides proxy unwrapping and common patterns for plugin functions.
"""

from __future__ import annotations

import numbers

import numpy as np
import polars as pl

from gaspatchio._dtypes import with_integers_as_i64
from gaspatchio.frame.lowering.columns import column_reference


def literal_expression(value: object) -> pl.Expr:
    """Return the Polars literal a value written into a formula stands for.

    A whole number is stated as an ``Int64``. Polars gives an integer literal
    no width of its own, and where nothing beside it sets the type it settles
    on ``Int32``: ``af.c = 5`` stored an ``Int32`` column,
    ``when(...).then(70000).otherwise(0)`` answered one, and ``* 70000``
    downstream wrapped to 605,032,704 where the hand value is 4,900,000,000
    -- while the record, and the JAX engine, carried each as the ``i64``
    section 10 names every whole number. Beside a decimal it still widens to
    the decimal, as two numbers of different widths do. A NumPy integer is
    the whole number it holds, whatever its width.

    A sequence reaches Polars as the list it always was, its whole numbers
    already ``Int64``. A Series or NumPy array of integers enters as a column
    of the book does, read as the ``Int64`` its values fit (section 10), so a
    narrow one handed in as a column does not wrap where its record says
    ``i64``. Every other value is Polars' own literal of it.

    Examples:
        >>> pl.select(literal_expression(5)).dtypes
        [Int64]
        >>> pl.select(literal_expression(70000) * 70000).item()
        4900000000
        >>> pl.select(literal_expression(2) * 1.5).item()
        3.0

    """
    if isinstance(value, tuple):
        return pl.lit(list(value))
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return pl.lit(int(value), dtype=pl.Int64)
    if isinstance(value, np.ndarray) and value.dtype.kind in "iu":
        value = pl.Series(value)
    if isinstance(value, pl.Series):
        # Named for the cast, which addresses a column by its name, and given
        # its own name back: an array's series has none.
        read = with_integers_as_i64(value.rename("values").to_frame())
        return pl.lit(read.to_series().rename(value.name))
    return pl.lit(value)


def to_polars_expression(arg: object) -> pl.Expr:
    """Convert any proxy or expression to a Polars expression.

    This function handles the common pattern of unwrapping proxy objects
    to get the underlying Polars expressions that plugin functions expect.

    Its operand contract differs from ``_shared._unwrap_proxy``: it reads
    an expression before a column name, and requires a string name before
    constructing a column reference. Both implementations live with the
    Polars lowerings.

    Anything that is not a proxy or an expression is read the way Polars
    reads an operand: a string names a column, and any other value (a
    ``pl.Series``, a date, a number) is a literal.

    Args:
        arg: A ColumnProxy, an ExpressionProxy, a pl.Expr, a column name, or
            a literal value

    Returns:
        A Polars expression ready for use in plugin functions

    Examples:
        ```python
        # With ColumnProxy
        expr = to_polars_expression(af["column_name"])

        # With ExpressionProxy
        expr = to_polars_expression(af["col"].polars_native().cast(pl.Date))

        # With raw Polars expression
        expr = to_polars_expression(pl.col("column_name"))
        ```

    """
    # A proxy is recognised by what it carries, since this layer does not
    # import the proxy classes: an ExpressionProxy holds its expression, and
    # a ColumnProxy names its column (the name must be a string).
    if hasattr(arg, "_parent"):
        expression = getattr(arg, "_expr", None)
        if isinstance(expression, pl.Expr):
            return expression
        name = getattr(arg, "name", None)
        if isinstance(name, str):
            return column_reference(name)

    if isinstance(arg, pl.Expr):
        return arg
    if isinstance(arg, str):
        return column_reference(arg)
    return pl.lit(arg)
