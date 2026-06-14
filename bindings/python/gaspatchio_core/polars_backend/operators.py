# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Backend implementations for shape-aware named operations.

Each operation here corresponds to an entry in dispatch.py's _BACKEND_LIST_OPS
registry. Dispatch resolves the proxy's shape, decides the op needs backend
routing, and calls dispatch_list_op(name, ...).
"""

from __future__ import annotations

import polars as pl
from loguru import logger

from gaspatchio_core.polars_backend._shared import _unwrap_proxy
from gaspatchio_core.polars_backend.plugins import list_clip, list_pow


def execute_list_pow(
    base_expr: pl.Expr,
    args: tuple,
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Execute pow using Rust list_pow plugin for list columns with column exponents.

    Handles three cases:
    - list ** list: direct list_pow call
    - list ** scalar: direct list_pow call (plugin handles broadcasting)
    - scalar ** list: uses exp/log identity since list_pow requires list base
    """
    if not args:
        msg = "pow requires an exponent argument"
        raise ValueError(msg)

    exp_arg = args[0]
    exp_expr = _unwrap_proxy(exp_arg)

    if not isinstance(exp_expr, pl.Expr):
        exp_expr = pl.lit(exp_expr)

    if base_is_list:
        logger.trace(f"Using list_pow plugin: base={base_expr}, exp={exp_expr}")
        return list_pow(base_expr, exp_expr)

    # scalar ** list: use exp/log identity (scalar^list = exp(list * log(scalar))).
    # The identity only holds for strictly positive bases. For zero or negative
    # bases, log() produces -inf/NaN which corrupts the result silently.
    # Guard: use when/then to handle base > 0 (exp/log), base == 0 (zero result
    # for positive exp, 1.0 for zero exp, NaN for negative exp), and base < 0
    # (NaN — negative bases with fractional exponents are undefined in real
    # numbers).
    logger.trace("Using guarded exp/log identity for scalar**list pow")
    exp_log_result = (exp_expr * base_expr.log()).list.eval(pl.element().exp())
    return (
        pl.when(base_expr > 0)
        .then(exp_log_result)
        .when(base_expr.eq(0))
        .then(
            exp_expr.list.eval(
                pl.when(pl.element() > 0)
                .then(0.0)
                .when(pl.element().eq(0))
                .then(1.0)  # 0^0 = 1 by convention
                .otherwise(pl.lit(float("nan")))
            )
        )
        .otherwise(pl.lit(None))  # negative base: undefined for fractional exponents
    )


_CLIP_UPPER_ARG_INDEX = 2


def execute_list_clip(
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
) -> pl.Expr:
    """Execute clip using Rust list_clip plugin for list columns with column bounds."""
    lower_arg = None
    upper_arg = None

    if len(args) >= 1:
        lower_arg = args[0]
    if len(args) >= _CLIP_UPPER_ARG_INDEX:
        upper_arg = args[1]

    if "lower_bound" in kwargs:
        lower_arg = kwargs["lower_bound"]
    if "upper_bound" in kwargs:
        upper_arg = kwargs["upper_bound"]

    lower_expr = (
        _unwrap_proxy(lower_arg) if lower_arg is not None else pl.lit(float("-inf"))
    )
    upper_expr = (
        _unwrap_proxy(upper_arg) if upper_arg is not None else pl.lit(float("inf"))
    )

    if not isinstance(lower_expr, pl.Expr):
        lower_expr = pl.lit(lower_expr)
    if not isinstance(upper_expr, pl.Expr):
        upper_expr = pl.lit(upper_expr)

    logger.trace(
        f"Using list_clip plugin: values={base_expr}, "
        f"lower={lower_expr}, upper={upper_expr}"
    )
    return list_clip(base_expr, lower_expr, upper_expr)


def dispatch_list_op(
    name: str,
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Single entry point for backend-specific list operations.

    Dispatch in column/dispatch.py decides whether to call this based on
    _BACKEND_LIST_OPS. The router itself stays minimal: name -> handler.
    """
    if name == "pow":
        return execute_list_pow(base_expr, args, base_is_list=base_is_list)
    if name == "clip":
        return execute_list_clip(base_expr, args, kwargs)
    msg = f"No backend handler for list op: {name}"
    raise NotImplementedError(msg)
