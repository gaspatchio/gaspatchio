# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowerings for the ``projection`` column accessor.

``af.pols_if = af.combined_decrement.projection.cumulative_survival()``
builds ``Call("projection.cumulative_survival", ...)`` and stops there.
The cumulative product, the timing shift, the ``list.eval`` versus
down-the-column choice -- everything about *how* that becomes Polars --
is the rule below. The bodies are the accessor's own former bodies,
moved rather than rewritten: same calls, same order, same comments where
they explained an actuarial decision.

The one thing that changed in the move is where shape comes from. The
accessor used to read ``self._proxy.shape``; a rule reads the shape the
tree resolved for its own argument. Same question, asked of the frame
either way, but now asked in the one place that is allowed to ask.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.ir import Col, Lit
from gaspatchio._shape import frame_has_a_timeline
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.plugins import accumulate as _accumulate
from gaspatchio.frame.lowering._polars.plugins import ieee_quotient
from gaspatchio.frame.lowering._polars.validation import (
    REMAINING_SUM_PAST_I64_RULE,
    WIDE_REMAINING_SUM_RULE,
)
from gaspatchio.frame.lowering.polars import (
    lower_arg,
    lower_arg_read_as_i64,
    register_lowering,
    whole_numbers_folded_exactly,
)

if TYPE_CHECKING:
    from polars.datatypes import DataTypeClass

    from gaspatchio._semantic.ir import AttrValue, Call, OpNode
    from gaspatchio._shape import Shape
    from gaspatchio.frame.lowering.context import LoweringContext


def _frame_has_a_timeline(ctx: LoweringContext | None) -> bool:
    """Whether the frame's rows are policies laid along a projection timeline.

    Read as ``_shape.frame_has_a_timeline`` reads it, the one reading the
    row-operation guard shares: the schedule ``projection.set()`` keeps, or,
    on a frame rebuilt from a collected projection, the per-period ``month``
    column or the ``num_proj_months`` every axis stamps.
    """
    return ctx is not None and frame_has_a_timeline(ctx.frame)


def _per_period_key(ctx: LoweringContext | None) -> str:
    """Return the per-period key a refusal suggests, in this frame's own index.

    A calendar axis counts months; a fixed-step axis counts steps, and on one
    written as ``step_years`` there is no ``month`` to count at all.
    """
    frame = ctx.frame if ctx is not None else None
    projection = getattr(frame, "_projection", None)
    if getattr(projection, "_kind", None) == "fixed_step":
        return "af.issue_age + af.projection.t_years()"
    schema = getattr(frame, "_schema", None) or {}
    if "month" not in schema and isinstance(schema.get("step"), pl.List):
        return "af.step"
    return "af.issue_age + af.month // 12"


def _refuse_a_policy_column(method: str, ctx: LoweringContext | None) -> None:
    """Refuse a period method handed one value per policy instead of one per period."""
    msg = (
        f"{method} works period by period, but this column has one value per "
        "policy, not one per period. On a frame with a projection timeline the "
        "rows are policies, so taking it down the rows would hand each policy "
        "the previous policy's value. Make the column per-period first: look "
        f"it up with a per-period key ({_per_period_key(ctx)}), or "
        "repeat it across the timeline with .projection.broadcast_to_periods()."
    )
    raise ValueError(msg)


def _needs_periods_on_a_timeline(
    method: str, shape: Shape, ctx: LoweringContext | None
) -> None:
    """Refuse a non-list column where the rows are policies, not periods.

    Without a timeline the rows are the periods (a long-format frame, grouped
    with ``.over()``) and running down them is the documented calculation, so
    the column is left to it. With one, the same fold crosses from one policy
    into the next: a different calculation, and one that changes with which
    other policies share the file and in what order.
    """
    if shape != "list" and _frame_has_a_timeline(ctx):
        _refuse_a_policy_column(method, ctx)


def _needs_periods(method: str, shape: Shape, ctx: LoweringContext | None) -> None:
    """Refuse a non-list column for a method that has no down-the-rows form.

    ``remaining_sum`` and ``prospective_value`` only ever fold within a
    period list. A per-policy column is refused on any frame; a column whose
    shape could not be resolved is refused where the frame has a timeline.
    """
    if shape == "scalar" or (shape != "list" and _frame_has_a_timeline(ctx)):
        _refuse_a_policy_column(method, ctx)


def _attrs(node: Call) -> dict[str, AttrValue]:
    """Read a call's typed configuration back as a dict."""
    return dict(node.attrs)


@register_lowering("projection.cumulative_survival")
def _lower_cumulative_survival(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Cumulate survival across the projection, per period or down the column.

    For a per-period column this is the within-list cumulative product
    ``survival[t] = px[0] * px[1] * ... * px[t]``, where ``px[i]`` is
    ``1 - qx[i]`` for a rate input, or the element itself when the column
    already holds survival factors (``from_survival``) -- inverting twice
    would lose bits below ``px = 0.5``. For a per-policy column it is the
    cumulative product down the rows; add ``.over()`` yourself if that
    needs grouping.

    ``start_at`` prepends an initial value and drops the last element, so
    the result is beginning-of-period: ``[start_at, tpx[0], tpx[1], ...]``.

    A null decrement ends the running survival's knowledge of itself, and a
    period carrying no decrement is not a period carrying no decrement to
    apply: the fold answers null at that period and at every later one.
    That is a fact about the fold rather than about which factor it folds,
    so it holds for a survival-factor column (``from_survival``) exactly as
    it does for a rate one. The mask goes on before ``start_at`` shifts the
    sequence along -- the opening value is the boundary the projection
    starts from and is never the thing that went missing.
    """
    attrs = _attrs(node)
    start_at = attrs["start_at"]
    from_survival = attrs["from_survival"]
    base_expr, shape = lower_arg(node.args[0], ctx)
    kinds.refuse_unless_a_number(
        line="cumulative_survival()",
        operand=node.args[0],
        dtype=kinds.operand_dtype(node.args[0], base_expr, ctx),
        decimal=True,
        duration=True,
    )

    if shape == "list":
        factor = pl.element() if from_survival else 1 - pl.element()
        lost_a_period = pl.element().is_null().cum_sum() > 0
        survival = pl.when(lost_a_period).then(None).otherwise(factor.cum_prod())
        if start_at is not None:
            # Shifted along inside each policy's own run: prepending the
            # opening value with concat_list and cutting the run back to its
            # length panicked the streaming engine over a batch whose every
            # policy had no run ("type Float64 is incompatible with expected
            # type Null"), and the shift is the same sequence.
            survival = survival.shift(1, fill_value=start_at)
        return base_expr.list.eval(survival)

    _needs_periods_on_a_timeline("cumulative_survival()", shape, ctx)
    scalar_factor = base_expr if from_survival else 1 - base_expr
    survival_expr = scalar_factor.cum_prod()
    if start_at is not None:
        survival_expr = survival_expr.shift(1, fill_value=start_at)
    return survival_expr


@register_lowering("projection.with_period")
def _lower_with_period(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Replace one period's value in a per-period column.

    Splices the list around the target index. Polars' ``list.slice`` does
    not take a negative length the way Python does, so a negative period
    (counting from the end) computes its own lengths from the row's list
    size.
    """
    attrs = _attrs(node)
    period = attrs["period"]
    value = attrs["value"]
    if not isinstance(period, int):  # pragma: no cover - emission validates
        msg = f"with_period expects an integer period, got {period!r}"
        raise TypeError(msg)
    base_expr, shape = lower_arg(node.args[0], ctx)
    if shape == "scalar":
        raise kinds.shape_refusal(
            line="projection.with_period()",
            does="replaces one period of one policy's own timeline",
            clause="11.1.32",
            operand=node.args[0],
            holds=kinds.PER_POLICY,
            move=(
                "Write the per-period column this line means; repeat a "
                "per-policy value across the timeline first with "
                ".projection.broadcast_to_periods()."
            ),
        )

    if period < 0:
        # Both branches are evaluated by Polars. Keep slice offsets valid
        # even for a null/short row that the final guard leaves unchanged.
        list_len = base_expr.list.len().cast(pl.Int64).fill_null(0)
        before_length = (list_len + period).clip(lower_bound=0)
        before_slice = base_expr.list.slice(0, before_length)
        if period == -1:
            after_slice = base_expr.list.slice(0, 0)
        else:
            after_start = (list_len + period + 1).clip(lower_bound=0)
            after_slice = base_expr.list.slice(after_start, None)
    else:
        before_slice = base_expr.list.slice(0, period)
        after_slice = base_expr.list.slice(period + 1, None)

    replacement = pl.lit([[value]])
    modified_expr = pl.concat_list(
        [before_slice, replacement.list.first(), after_slice]
    )

    # A fixed period index may be out of range for shorter (jagged)
    # policies. list.slice clamps silently, so the naive concat would
    # APPEND the replacement and grow such rows -- a phantom value at a
    # period the policy never reaches. Apply the replacement only where the
    # index exists; leave out-of-range (already-matured) rows unchanged.
    # Positive t is in-bounds when len > t; negative t (from the end) when
    # len >= -t.
    list_len = base_expr.list.len()
    in_bounds = list_len > period if period >= 0 else list_len >= -period
    return pl.when(in_bounds).then(modified_expr).otherwise(base_expr)


def _shift_by(
    node: Call, ctx: LoweringContext | None, periods: int, method: str
) -> pl.Expr:
    """Shift a column ``periods`` steps, element-wise inside a per-period list.

    Polars' shift convention is the opposite sign of the actuarial ``t``
    notation, and the caller has already applied that flip: ``t-1`` (the
    prior period) arrives here as ``periods=1``.
    """
    base_expr, shape = lower_arg(node.args[0], ctx)
    fill_expr, _ = lower_arg(node.args[1], ctx)
    if shape != "list":
        _needs_periods_on_a_timeline(method, shape, ctx)
    else:
        _refuse_a_number_filling_a_flag(method, node.args[1], base_expr, fill_expr, ctx)
    _refuse_a_fill_value_of_another_kind(
        method=method,
        value=node.args[0],
        base_expr=base_expr,
        fill=node.args[1],
        fill_expr=fill_expr,
        ctx=ctx,
    )
    if periods == 0:
        return base_expr
    if shape == "list":
        return base_expr.list.eval(pl.element().shift(periods, fill_value=fill_expr))
    return base_expr.shift(periods, fill_value=fill_expr)


def _refuse_a_number_filling_a_flag(
    method: str,
    fill: OpNode,
    base_expr: pl.Expr,
    fill_expr: pl.Expr,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a number filling a per-period Boolean run, naming the flag to pass.

    A shift fills the period it runs off the timeline with ``fill_value``,
    whose default is ``0.0`` -- right for an amount and meaningless for a
    flag. Over a Boolean run that default reached the engine as a float
    inside ``list.eval`` and failed with "failed to materialize unknown
    type", which names neither the column nor the move. Reading ``0.0`` as
    ``False`` would be a meaning nobody wrote, so the shift says what it
    needs: a Boolean fill, or null. A fill this lowering cannot type is left
    to the engine.
    """
    if ctx is None or ctx.dtype_of_expr(base_expr) != pl.List(pl.Boolean):
        return
    if isinstance(fill, Lit):
        if fill.value is None or isinstance(fill.value, bool):
            return
    elif ctx.dtype_of_expr(fill_expr) in (pl.Boolean, pl.Null, None):
        return
    shown = fill.value if isinstance(fill, Lit) else "a number"
    msg = (
        f"{method} shifts a run of flags (True/False per period), and its "
        f"fill_value -- {shown!r} -- is a number. The fill stands in the "
        "period the shift runs off the projection, so it has to be a flag "
        "too: pass fill_value=False (or True, or None for no value there). "
        "If the flag is meant as an amount, make it one first -- "
        "when(af.flag).then(1.0).otherwise(0.0) -- and shift that."
    )
    raise TypeError(msg)


def _refuse_a_fill_value_of_another_kind(  # noqa: PLR0913 -- the value and the fill, each as written and as lowered
    *,
    method: str,
    value: OpNode,
    base_expr: pl.Expr,
    fill: OpNode,
    fill_expr: pl.Expr,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a ``fill_value`` that would convert the column the shift moves.

    The fill stands in the period the shift runs off the projection, and
    Polars makes it fit by finding a type both can be written in: a run of
    rates shifted with ``fill_value="n/a"`` came back as text, and a run of
    product codes shifted with the default ``0.0`` came back with ``'0.0'``
    at period zero. Section 11.1.19 states the shift over decimals with a
    numeric fill and nothing else, so a fill of another kind is refused here,
    naming the fill the column can take. A run of flags is
    :func:`_refuse_a_number_filling_a_flag`'s, with its own sentence.
    """
    receiver = kinds.operand_dtype(value, base_expr, ctx)
    filled = kinds.operand_dtype(fill, fill_expr, ctx)
    if receiver is None or not kinds.apart(receiver, filled) or filled is None:
        return
    raise kinds.refusal(
        line=method,
        role="fill_value",
        operand=fill,
        fill=filled,
        beside="the column it shifts",
        receiver=receiver,
        move=(
            f"Pass a fill_value that is {kinds.describe(receiver)}"
            + (
                " -- the default, 0.0, is for amounts --"
                if kinds.kind_of(receiver) != "number"
                else ""
            )
            + " or fill_value=None for no value there."
        ),
    )


@register_lowering("projection.previous_period")
def _lower_previous_period(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read each period's prior value -- the ``t-1`` of a reserve rollforward."""
    return _shift_by(node, ctx, 1, "previous_period()")


@register_lowering("projection.next_period")
def _lower_next_period(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read each period's following value -- ``t+1``, for forward-looking terms."""
    return _shift_by(node, ctx, -1, "next_period()")


@register_lowering("projection.at_period")
def _lower_at_period(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read the value an arbitrary offset away: negative is prior, positive future."""
    relative_period = _attrs(node)["relative_period"]
    if not isinstance(relative_period, int):  # pragma: no cover - emission validates
        msg = f"at_period expects an integer offset, got {relative_period!r}"
        raise TypeError(msg)
    return _shift_by(node, ctx, -relative_period, "at_period()")


@register_lowering("projection.broadcast_to_periods")
def _lower_broadcast_to_periods(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Repeat a per-policy value once per projection period.

    The period count comes from the ``like`` column when one was given and
    from the frame's own ``month`` axis otherwise. Either way it is
    per-row, so a jagged timeline keeps each policy's own length.
    """
    base_expr, _ = lower_arg(node.args[0], ctx)
    if len(node.args) > 1:
        like_expr, like_shape = lower_arg(node.args[1], ctx)
        if like_shape == "scalar":
            raise kinds.shape_refusal(
                line="projection.broadcast_to_periods()",
                does=(
                    "repeats a value once per cell of its axis, a list whose "
                    "length is each policy's period count"
                ),
                clause="11.1.32",
                operand=node.args[1],
                holds=kinds.PER_POLICY,
                move=(
                    "Write the axis column whose length the model means -- "
                    "like=af.month, or another per-period column."
                ),
            )
        length_expr = like_expr.list.len()
    else:
        length_expr = pl.col("month").list.len()
    return base_expr.repeat_by(length_expr)


@register_lowering("projection.remaining_sum")
def _lower_remaining_sum(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Sum each period's value and every period after it.

    A null period makes that position and every earlier position null: this
    is a running fold that starts at the last period, so the periods it has
    lost run from the hole back toward period zero -- the fold's own
    direction, and the direction the missing value would have travelled. The
    mask goes on inside the reversed order, before the second reverse puts
    the periods back the way round the model reads them. A run wider than
    ``i64`` is summed as the ``Int64`` its values fit, and refused by name
    where one does not, as ``cum_sum`` is (section 10). A run of whole
    numbers is summed exactly, and a period whose remaining sum is past
    ``i64`` is refused by name rather than wrapped, as ``cum_sum`` is.
    """
    base_expr, shape = lower_arg_read_as_i64(
        node.args[0], ctx, rule=WIDE_REMAINING_SUM_RULE
    )
    _needs_periods("remaining_sum()", shape, ctx)
    kinds.refuse_unless_a_number(
        line="remaining_sum()",
        operand=node.args[0],
        dtype=kinds.operand_dtype(node.args[0], base_expr, ctx),
    )
    from_the_end = pl.element().reverse()
    lost_a_period = from_the_end.is_null().cum_sum() > 0
    folded = (
        pl.when(lost_a_period).then(None).otherwise(from_the_end.cum_sum()).reverse()
    )
    exact = whole_numbers_folded_exactly(
        base_expr,
        node.args[0],
        ctx,
        lambda run: run.list.eval(folded),
        per_period=True,
        rule=REMAINING_SUM_PAST_I64_RULE,
    )
    return base_expr.list.eval(folded) if exact is None else exact


def _periods_the_total_still_has(cashflow_expr: pl.Expr) -> pl.Expr:
    """One per position a reverse fold reached, null from the hole back.

    The lost periods are the cashflow's own. A null in the discount operand
    is outside the form 11.1.21 states and is left exactly where it was, so
    the mask is taken from the cashflows rather than from the discounted
    series the fold actually sums. Multiplying by one is exact, so the
    positions the fold still has keep the value they had to the last bit.
    """
    lost_a_period = pl.element().is_null().cum_sum(reverse=True) > 0
    return cashflow_expr.list.eval(pl.when(lost_a_period).then(None).otherwise(1.0))


def _discount_factors(
    cashflow_expr: pl.Expr,
    discount_node: OpNode,
    discount_kind: AttrValue,
    ctx: LoweringContext | None,
) -> pl.Expr:
    """Build the ``v(t)`` factors from either a rate or ready-made factors."""
    if discount_kind == "factor":
        factor_expr, _ = lower_arg(discount_node, ctx)
        return factor_expr

    if isinstance(discount_node, Lit):
        # A constant rate: v^t for each period t.
        rate = discount_node.value
        # A positive test and not an exclusion list. A literal may hold a
        # date, and a date is neither a bool, a str nor a tuple -- so a list
        # of what a rate is *not* would let one through to the arithmetic
        # below, which would raise somewhere with nothing to say about
        # discount_rate. What a rate is, is a number that is not a flag.
        if isinstance(rate, bool) or not isinstance(
            rate, (int, float)
        ):  # pragma: no cover - validated
            msg = f"discount_rate must be a number, got {rate!r}"
            raise TypeError(msg)
        v = 1.0 / (1.0 + rate)
        return cashflow_expr.list.eval(
            pl.lit(v).pow(pl.int_range(0, pl.element().len()))
        )

    rate_expr = _discount_rate_over_periods(cashflow_expr, discount_node, ctx)
    # Per-period rates: cumulative product of 1/(1+r), shifted to
    # beginning-of-period: [1, v[0], v[0]*v[1], ...]
    v_expr = ieee_quotient(pl.lit(1.0), rate_expr + 1.0).list.eval(
        pl.element().cum_prod()
    )
    list_len = v_expr.list.len()
    return pl.concat_list([pl.lit([1.0]), v_expr]).list.slice(0, list_len)


def _discount_rate_over_periods(
    cashflow_expr: pl.Expr,
    discount_node: OpNode,
    ctx: LoweringContext | None,
) -> pl.Expr:
    """Give a scalar rate column the cashflow's per-row projection lengths."""
    rate_expr, rate_shape = lower_arg(discount_node, ctx)
    if rate_shape == "scalar":
        return rate_expr.repeat_by(cashflow_expr.list.len())
    return rate_expr


def _per_period_discount(
    cashflow_expr: pl.Expr,
    discount_node: OpNode,
    ctx: LoweringContext | None,
) -> pl.Expr | float:
    """Return the single-period discount ``v[t]`` implied by the rate input."""
    if isinstance(discount_node, Lit):
        rate = discount_node.value
        # A positive test and not an exclusion list. A literal may hold a
        # date, and a date is neither a bool, a str nor a tuple -- so a list
        # of what a rate is *not* would let one through to the arithmetic
        # below, which would raise somewhere with nothing to say about
        # discount_rate. What a rate is, is a number that is not a flag.
        if isinstance(rate, bool) or not isinstance(
            rate, (int, float)
        ):  # pragma: no cover - validated
            msg = f"discount_rate must be a number, got {rate!r}"
            raise TypeError(msg)
        return 1.0 / (1.0 + rate)
    rate_expr = _discount_rate_over_periods(cashflow_expr, discount_node, ctx)
    return ieee_quotient(pl.lit(1.0), rate_expr + 1.0)


@register_lowering("projection.prospective_value")
def _lower_prospective_value(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Present value of this period's cashflow and every one after it.

    Discounted cashflows are accumulated with the reverse -> cumulative
    sum -> reverse pattern, giving "the sum from t to the end" in one pass.
    NaN cashflows propagate: a NaN here means an upstream defect (a lookup
    miss under ``on_missing="nan"``, say) and zeroing it would silently
    understate the reserve. A period carrying no cashflow at all propagates
    the same way and in the fold's own direction: that position and every
    earlier one answer null, because a present value that lost a period does
    not know its own total from there back.

    Timing, as Excel's annuity convention has it. ``remaining_pv / v_expr`` leaves the
    cashflow at time t undiscounted, so it is the annuity-DUE value: the
    cashflow at t is paid at the START of the period, worth its full face
    value at the valuation point t, and only later cashflows are
    discounted. Excel's convention: type=1 / beginning_of_period ->
    annuity-DUE (LARGER, first cashflow undiscounted); type=0 /
    end_of_period -> ordinary (SMALLER, each cashflow discounted a full
    period).
    """
    attrs = _attrs(node)
    timing = attrs["timing"]
    discount_kind = attrs["discount_kind"]
    cashflow_expr, shape = lower_arg(node.args[0], ctx)
    _needs_periods("prospective_value()", shape, ctx)
    discount_node = node.args[1]

    v_expr = _discount_factors(cashflow_expr, discount_node, discount_kind, ctx)
    still_has = _periods_the_total_still_has(cashflow_expr)
    discounted_cf = cashflow_expr * v_expr
    remaining_pv = (
        discounted_cf.list.reverse().list.eval(pl.element().cum_sum()).list.reverse()
    )
    if timing == "beginning_of_period":
        return ieee_quotient(remaining_pv, v_expr) * still_has

    # Ordinary (end_of_period) value. Each cashflow slides one period into
    # the future and must carry ITS OWN period's discount v[s]:
    #   ord(t) = sum_{s>=t} CF[s] * prod_{u=t..s} v[u]
    # A single per-position multiplier on the due value (due(t) * v[t]) is
    # only exact for constant rates -- with varying rates it discounts the
    # whole tail by position t's factor instead of each cashflow's.
    if discount_kind == "rate":
        # Rate inputs: v_expr is the start-anchored cumulative
        # (prod_{u=0..t-1} v[u]); multiply elementwise by v[t] to get the
        # end-anchored cumulative prod_{u=0..t}.
        v_end = v_expr * _per_period_discount(cashflow_expr, discount_node, ctx)
        ordinary_divisor = v_expr
    else:
        # A discount_factor input is END-anchored by contract (df[0]
        # already includes one period's discounting), so it IS the
        # end-anchored cumulative; divide by its shift (df[-1] := 1).
        v_end = v_expr
        ordinary_divisor = v_expr.list.eval(pl.element().shift(1, fill_value=1.0))

    tail_value = (
        (cashflow_expr * v_end)
        .list.reverse()
        .list.eval(pl.element().cum_sum())
        .list.reverse()
    )
    return ieee_quotient(tail_value, ordinary_divisor) * still_has


# What each operand of the recurrence holds, in the words its refusal uses.
_RECURRENCE_ROLES: dict[str, str] = {
    "initial": "the opening balance",
    "multiplier": "the growth factor for each period",
    "addend": "the amount added each period",
}


def _as_a_number(
    parameter: str, operand: OpNode, expr: pl.Expr, ctx: LoweringContext | None
) -> pl.Expr:
    """Return one operand as the number the recurrence reads, or refuse it.

    The kernel casts every operand to a float, and a cast reads what the
    engine stores rather than what the column means. A ``Date`` opened the
    balance at its count of days since 1970-01-01 -- 2025-01-01 at 20,089 --
    a list of Decimals was read as its unscaled integers, 5.00 as 500, text
    that spelled a number was parsed while any other text failed without a
    reason, and a category was read as the code it is filed under.

    So the operand's type decides, scalar or list alike, and the question is
    asked here, at the assignment, where ``to_float`` asks it too:

    - a number or a null is read as it is;
    - a Decimal is cast to a float first, which is its value, so a list of
      them agrees with one of them;
    - a Boolean is refused. It used to be read as 1 or 0, which is a meaning
      the recurrence's own clause does not give it (section 11.1.20 states
      the operands over Float64, and 11.1.38's ``to_float`` refuses a
      Boolean by name), so the exported record carried an operand a second
      reader had to refuse, and no conversion the format defines could have
      recorded the reading -- the one spelling it has,
      ``when(flag).then(1.0).otherwise(0.0)``, answers a missing flag with
      0.0 where the cast answered null. Writing that line is the move: the
      author says what an in-force flag means as an amount, including where
      it is missing, and the record carries it;
    - text, a category, a date, a time, a duration and anything else is
      refused, naming the operand, its type and the move that makes it a
      number.

    A numeric literal is answered from the node and costs no probe. Without
    a context nothing can be resolved, and nothing is refused: the check
    refuses a type it has seen, never one it could not see.
    """
    if ctx is None or (
        isinstance(operand, Lit) and isinstance(operand.value, (int, float))
    ):
        return expr
    dtype = ctx.dtype_of_expr(expr)
    element: pl.DataType | DataTypeClass | None = (
        dtype.inner if isinstance(dtype, pl.List) else dtype
    )
    if element is None:
        return expr
    base = element.base_type()
    if base is pl.Decimal:
        return expr.cast(
            pl.List(pl.Float64) if isinstance(dtype, pl.List) else pl.Float64
        )
    if base in (pl.Null, pl.Unknown) or element.is_numeric():
        return expr
    raise TypeError(_not_a_number(parameter, operand, dtype, element))


def _not_a_number(
    parameter: str,
    operand: OpNode,
    dtype: pl.DataType | None,
    element: pl.DataType | DataTypeClass,
) -> str:
    """Say why one operand is not a number, and the move that makes it one."""
    role = _RECURRENCE_ROLES[parameter]
    opening = (
        "accumulate() runs state[t] = state[t-1] * multiplier[t] + addend[t] "
        f"over numbers, and {parameter} -- {role} -- resolved to {dtype}. "
    )
    base = element.base_type()
    if element.is_temporal():
        return opening + (
            "A date, a time or a duration is not an amount: the recurrence "
            "would read it as the integer it is stored as (a date as its count "
            "of days since 1970-01-01) and run on a plausible number that "
            f"means nothing. Pass the numeric column that holds {role}. If a "
            "length of time is what you meant, measure it into a column first "
            "and pass that: af.valuation_date.excel.days(af.issue_date) gives "
            "the days between two dates, and "
            "af.issue_date.excel.yearfrac(af.valuation_date) the years."
        )
    if base is pl.String:
        column = f'af["{operand.name}"]' if isinstance(operand, Col) else "af[...]"
        target = "pl.List(pl.Float64)" if isinstance(dtype, pl.List) else "pl.Float64"
        return opening + (
            "Text is not an amount, even when it spells one: the kernel would "
            "parse text that reads as a number and fail, without saying why, "
            "on text that does not. If it holds numbers, convert it first -- "
            f"{column}.polars_native().cast({target}), or cast it in the data "
            "before the frame is built -- and pass that."
        )
    if base is pl.Boolean:
        column = f"af.{operand.name}" if isinstance(operand, Col) else "the flag"
        return opening + (
            "A Boolean is a selection, not an amount: the recurrence would "
            "have to decide that True is 1.0 and False is 0.0, and what a "
            "missing flag is, and the record could not say so. Write the "
            f"amount it stands for -- when({column}).then(1.0).otherwise(0.0) "
            "-- and pass that, choosing a different otherwise where a missing "
            "flag should not count as zero."
        )
    if base in (pl.Categorical, pl.Enum):
        return opening + (
            "A category is a label, not an amount: the kernel would read each "
            "label as the code the engine files it under. Map the categories "
            "to numbers first -- a Table lookup keyed on the category, or "
            "when(...).then(...).otherwise(...) -- and pass that."
        )
    return opening + (
        f"{element} is not an amount the recurrence can read. Pass the numeric "
        f"column that holds {role}."
    )


def _accumulate_operand(
    operand: OpNode, ctx: LoweringContext | None
) -> tuple[pl.Expr, Shape]:
    """Lower one ``multiplier``/``addend`` operand, with the shape it resolves to.

    Only a literal that is one number takes the scalar path. A literal
    holding a sequence is one value per period, so it lowers the ordinary
    way and keeps whatever shape that resolves to.
    """
    # A positive test, for the reason the two discount-rate guards above give:
    # a literal may hold a date, and ``float()`` of one raises with nothing to
    # say about the operand it was handed.
    value = operand.value if isinstance(operand, Lit) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return pl.lit(float(value)), "scalar"
    return lower_arg(operand, ctx)


@register_lowering("projection.accumulate")
def _lower_accumulate(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Run the linear recurrence ``state[t] = state[t-1] * multiplier[t] + addend[t]``.

    A scalar ``multiplier`` or ``addend`` has no period axis of its own, so it
    borrows the sibling list's per-row lengths -- jagged-safe, since each
    policy's own timeline sets its repetition count (gh#128).
    Two scalars leave no axis to infer at all, which is refused rather
    than guessed. Each operand is read as a number or refused by its type
    (see ``_as_a_number``).

    Under ``reverse`` the same recurrence runs from each policy's own last
    period back to its first, ``state[t] = state[t+1] * multiplier[t] +
    addend[t]``. It is the forward kernel with both step operands reversed
    within each policy's own list and the answer reversed back, so the two
    directions share one stepped loop and neither divides by a cumulative
    product (section 11.1.20). A null step then loses every position the
    reversed run reaches after it, which is every earlier period. A node
    with no ``reverse`` at all was written before the attribute existed,
    when the recurrence had one direction, and runs forward.
    """
    reverse = dict(node.attrs).get("reverse", False)
    if not isinstance(reverse, bool):
        msg = (
            f"accumulate() carries reverse={reverse!r}, and the direction is "
            "True or False: section 11.1.11 records it as a flag."
        )
        raise TypeError(msg)
    initial_expr, initial_shape = lower_arg(node.args[0], ctx)
    if initial_shape == "list":
        raise kinds.shape_refusal(
            line="projection.accumulate()",
            does="starts one recurrence for each policy from one initial value",
            clause="11.1.20",
            operand=node.args[0],
            holds=kinds.PER_PERIOD,
            move=(
                "Write the initial value once per policy: the recurrence starts "
                "from it and runs over the per-period multiplier and addend."
            ),
        )
    multiplier_expr, multiplier_shape = _accumulate_operand(node.args[1], ctx)
    addend_expr, addend_shape = _accumulate_operand(node.args[2], ctx)
    initial_expr = _as_a_number("initial", node.args[0], initial_expr, ctx)
    multiplier_expr = _as_a_number("multiplier", node.args[1], multiplier_expr, ctx)
    addend_expr = _as_a_number("addend", node.args[2], addend_expr, ctx)

    if multiplier_shape == "scalar" and addend_shape == "list":
        multiplier_expr = multiplier_expr.cast(pl.Float64).repeat_by(
            addend_expr.list.len()
        )
    elif addend_shape == "scalar" and multiplier_shape == "list":
        addend_expr = addend_expr.cast(pl.Float64).repeat_by(multiplier_expr.list.len())
    elif multiplier_shape == "scalar" and addend_shape == "scalar":
        msg = (
            "accumulate() needs a per-period axis: multiplier and addend are "
            "both scalar, so there is no timeline to broadcast onto. "
            "Pass at least one list column (one value per period) -- or, "
            "for growth-free accumulation, use the closed form: "
            "initial + flow.cum_sum()."
        )
        raise ValueError(msg)

    if not reverse:
        return _accumulate(initial_expr, multiplier_expr, addend_expr)
    return _accumulate(
        initial_expr, multiplier_expr.list.reverse(), addend_expr.list.reverse()
    ).list.reverse()
