# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Backend implementations for shape-aware named operations.

These handlers implement the retained backend helpers for list power and
clipping. This module is where they are written and the only place they are
published from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from gaspatchio.frame.lowering._polars._shared import _unwrap_proxy
from gaspatchio.frame.lowering._polars.plugins import list_clip, list_pow

if TYPE_CHECKING:
    from collections.abc import Mapping


def execute_list_pow(
    base_expr: pl.Expr,
    args: tuple[object, ...],
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Execute pow using Rust list_pow plugin for list columns with column exponents.

    Handles three cases:
    - list ** list: direct list_pow call
    - list ** scalar: direct list_pow call (plugin handles broadcasting)
    - scalar ** list: direct list_pow call (the kernel raises the row's base
      to each period's exponent) -- an IEEE ``pow`` per element, as ``**`` means
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

    # scalar ** list: `10 ** [14.0]` is 1e14 exactly, where the exp/log
    # identity this replaced (exp(14 * ln 10)) read 100000000000000.12.
    # The domain guard is the one that identity needed and the graph-artifact
    # contract states for this shape: a positive base raises; a zero base
    # gives 0 for a positive exponent, 1 for 0**0 and NaN for a negative one;
    # a negative base is null (outside the contract for a list exponent).
    logger.trace("Using list_pow plugin for scalar**list pow")
    exact_result = list_pow(base_expr, exp_expr)
    powered = (
        pl.when(base_expr > 0)
        .then(exact_result)
        .when(base_expr.eq(0))
        .then(
            exp_expr.list.eval(
                # A null period stays null (11.1.25), before any test of its
                # sign could send it to the NaN branch below.
                pl.when(pl.element().is_null())
                .then(None)
                .when(pl.element() > 0)
                .then(0.0)
                .when(pl.element().eq(0))
                .then(1.0)  # 0^0 = 1 by convention
                .otherwise(pl.lit(float("nan")))
            )
        )
        .otherwise(pl.lit(None))  # negative base: undefined for fractional exponents
    )
    if base_expr.meta.is_literal():
        return powered
    # A null base is a null in each of the policy's periods, as it is under
    # the other four operators and with the null on the exponent's side
    # (11.1.25, 11.1.18): ``b ** L`` answered a null outer list -- a policy
    # with no periods -- where ``b * L`` answers ``[null, null]``.
    nulls = exp_expr.list.eval(
        pl.element().cast(pl.Float64) * pl.lit(None, dtype=pl.Float64)
    )
    return pl.when(base_expr.is_null()).then(nulls).otherwise(powered)


def execute_list_clip(
    base_expr: pl.Expr,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> pl.Expr:
    """Execute clip using Rust list_clip plugin for list columns with column bounds."""
    lower_arg = args[0] if args else None
    upper_arg = args[1] if len(args) > 1 else None

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
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Single entry point for backend-specific list operations.

    Routes the operation name to its list power or clipping handler. The
    ``pow`` lowering in ``frame/lowering/polars.py`` reaches the handlers
    through here rather than naming one.
    """
    if name == "pow":
        return execute_list_pow(base_expr, args, base_is_list=base_is_list)
    if name == "clip":
        return execute_list_clip(base_expr, args, kwargs)
    msg = f"No backend handler for list op: {name}"
    raise NotImplementedError(msg)
