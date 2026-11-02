# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowerings for the ``finance`` accessor, column and frame.

``af.disc_rate_mth = af.disc_rate_ann.finance.to_monthly(method="compound")``
builds ``Call("finance.to_monthly", ...)``; the compounding identity
``(1 + r)^(1/12) - 1`` and the choice between applying it element-wise
inside each policy's list or straight down the column live here. As with
the projection rules, the bodies are the accessor's own, moved: the
conversion an actuary can audit reads the same, it is just no longer
built at the line that asked for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.plugins import ieee_quotient, list_pow
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import AttrValue, Call
    from gaspatchio.frame.lowering.context import LoweringContext


def _attrs(node: Call) -> dict[str, AttrValue]:
    """Read a call's typed configuration back as a dict."""
    return dict(node.attrs)


@register_lowering("finance.to_monthly")
def _lower_to_monthly(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Convert an annual rate to its monthly equivalent.

    Compound is ``(1 + r_annual)^(1/12) - 1``; simple is ``r_annual / 12``.
    Which one applies is the actuary's stated convention, not a default
    the framework picks, and it is on the node.
    """
    method = _attrs(node)["method"]
    base_expr, shape = lower_arg(node.args[0], ctx)

    if method == "compound":
        if shape == "list":
            return base_expr.list.eval(((1 + pl.element()).pow(1 / 12)) - 1)
        return ((1 + base_expr).pow(1 / 12)) - 1

    # One IEEE division per element on either shape: Polars' own `/ 12`
    # multiplies by a rounded 1/12 instead.
    return ieee_quotient(base_expr, pl.lit(12))


@register_lowering("finance.compound")
def _lower_compound(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Grow by ``(1 + rate) ** (period / periods_per_year)``."""
    attrs = _attrs(node)
    rate = attrs["rate"]
    periods_per_year = attrs["periods_per_year"]
    if isinstance(rate, (bool, str, type(None))) or isinstance(
        periods_per_year, (bool, str, type(None))
    ):
        msg = (  # pragma: no cover - emission validates
            "compound() takes a numeric rate and periods_per_year, got "
            f"{rate!r} and {periods_per_year!r}"
        )
        raise TypeError(msg)
    base_expr, shape = lower_arg(node.args[0], ctx)

    years = ieee_quotient(base_expr, pl.lit(periods_per_year))
    if shape == "list":
        return years.list.eval((1 + rate) ** pl.element())
    return pl.lit(1 + rate) ** years


# The move a per-period operand of the two scalar valuations is refused with.
_PER_PERIOD_VALUATION = (
    "Write the per-period valuation as projection.prospective_value (11.1.21), "
    "which is the operation 11.1.29 names for it."
)


def _per_policy_valuation(node: Call, ctx: LoweringContext | None) -> list[pl.Expr]:
    """Return a scalar valuation's three operands, refusing one held per period.

    Section 11.1.29 states ``finance.discount`` and ``finance.present_value``
    over scalar operands only, and names the per-period valuation beside them.
    A rate or a period count held per period failed when the frame ran, in
    Polars' words (```pow` operation not supported for dtype list[f64]``); a
    value held per period was answered as a list no clause states. Each is
    refused where the line is written.
    """
    lowered = [lower_arg(argument, ctx) for argument in node.args]
    for operand, (_expr, shape) in zip(node.args, lowered, strict=True):
        if shape == "list":
            raise kinds.shape_refusal(
                line=f"{node.name}()",
                does="values one amount for each policy",
                clause="11.1.29",
                operand=operand,
                holds=kinds.PER_PERIOD,
                move=_PER_PERIOD_VALUATION,
            )
    return [expr for expr, _shape in lowered]


@register_lowering("finance.discount")
def _lower_discount(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Divide by ``(1 + rate) ** n_periods``, refusing a zero factor.

    A rate of exactly -100% makes the factor zero; the result is null
    there rather than an infinity propagating into a reserve.
    """
    base_expr, rate_expr, periods_expr = _per_policy_valuation(node, ctx)

    discount_factor = (1 + rate_expr).pow(periods_expr)
    return (
        pl.when(discount_factor != 0)
        .then(ieee_quotient(base_expr, discount_factor))
        .otherwise(pl.lit(None))
    )


@register_lowering("finance.present_value")
def _lower_present_value(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Discount one cashflow: ``PV = CF / (1 + rate)^period``.

    Cashflows are assumed to fall at the end of each period, so period 0
    has no present-value meaning here and comes back null.
    """
    cashflow_expr, rate_expr, period_expr = _per_policy_valuation(node, ctx)

    return (
        pl.when(period_expr >= 1)
        .then(ieee_quotient(cashflow_expr, (1 + rate_expr).pow(period_expr)))
        .otherwise(pl.lit(None))
    )


@register_lowering("finance.discount_factor")
def _lower_discount_factor(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Build ``v^t`` across a whole projection timeline.

    The spot method raises ``(1 + rate)`` to minus the period directly,
    through the ``list_pow`` kernel -- one pass over the list column, no
    explode-and-regroup. The forward method takes the per-period
    reciprocal ``1 / (1 + rate)``, one IEEE division per element, and
    cumulates it, prepending 1.0 so period 0 is
    undiscounted and trimming back to the rate column's own length.
    """
    method = _attrs(node)["method"]
    rate_expr, rate_shape = lower_arg(node.args[0], ctx)

    if method == "spot":
        period_expr, period_shape = lower_arg(node.args[1], ctx)
        if rate_shape == "scalar" and period_shape == "list":
            # The native power kernel requires a list on its base side.
            rate_expr = rate_expr.repeat_by(period_expr.list.len())
        return list_pow(rate_expr + 1.0, period_expr * -1.0)

    # One over one plus the rate, as section 11.1.30 states it: one IEEE
    # division per element. ``(1 + r) ** -1`` through the power kernel is a
    # libm ``pow``, and darwin's is not correctly rounded there -- one rate in
    # six hundred came back a unit in the last place off ``1 / (1 + r)``.
    reciprocal = ieee_quotient(pl.lit(1.0), rate_expr + 1.0)
    return (
        pl.concat_list([pl.lit([1.0]), reciprocal])
        # Trim the extra terminal factor inside the list evaluation. An outer
        # variable-length list.head infers List(Null) on zero-policy input.
        .list.eval(pl.element().cum_prod().head(pl.len() - 1))
    )
