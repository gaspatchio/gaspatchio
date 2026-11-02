# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The sole producer of Polars expressions from the semantic op-tree.

``lower_polars`` turns one ``OpNode`` (see ``gaspatchio._semantic.ir``)
into the ``pl.Expr`` that computes it. Every place elsewhere in the package
that today builds a Polars expression directly -- accessor methods, the
rollforward compiler -- is a candidate to relocate its expression-building
body here; this module is where ``tests/graph/census.py`` stops looking for
new raw ``pl.col``/``pl.when`` call sites, because this is the one place
they are expected to live. The proxy operator dunders and the
``when``/``then``/``otherwise`` chain have already made that move: they
build nodes, and everything about *how* those nodes become Polars is here.

Dispatch is a structural ``match`` over the seven-member ``OpNode`` union,
terminated by ``assert_never`` so that an eighth node type added to the
union without a matching case here fails type-checking rather than
silently falling through at run time -- the same discipline ``ir.walk``
uses. ``Col``, ``Lit``, ``BinOp``, and ``WhenThen`` always lower; the
remaining three kinds either dispatch further or refuse outright:

- ``Call`` looks its ``name`` up in ``LOWERINGS``, the registry the rule
  modules in ``frame/lowering/rules/`` populate as accessor
  expression-building bodies relocate here. A rule receives the ``Call``
  node *and* the ``LoweringContext``, because an accessor's body is
  routinely shape-dependent -- ``cumulative_survival`` cumulates inside
  each policy's list when the column is per-period and down the column
  when it is per-policy, and that question can only be answered against
  the frame.
- ``EngineNative`` with ``engine="polars"`` looks its held runtime
  expression up in ``NATIVE_REFS`` by node identity; the other two
  declared engines have no Polars lowering at all.
- ``State`` always refuses: a rollforward state name only means
  something inside a compiled rollforward, never as a bare expression.

Refusal is always a loud ``LoweringError`` naming the operation and the
fix -- never a silent fallback to a guessed value.

## Shape is a lowering concern, not a node concern

The op-tree records what a formula *means*. It does not record whether
``af.month`` is one value per policy or one per projection period, because
that is a fact about the frame, not about the subtraction. Polars, though,
refuses several of the mixed-shape combinations actuarial projections are
made of: a list column compared against a scalar column, a ``pl.when()``
over a ``list[bool]`` predicate, an ``.otherwise()`` unifying a list branch
with a scalar one, and ``**`` with a list base at all.

So every shape-dependent decision the framework makes lives in this
module, consulting the ``LoweringContext`` for the frame's own dtypes:

- **add/sub** pre-broadcast a *compound* scalar operand with ``repeat_by``
  when the other side is a list, because Polars derives a supertype for a
  bare column or literal against a list but not for a computed scalar.
- **Element-wise arithmetic on a list receiver** runs inside
  ``list.eval`` when the other operand carries no column references, and
  falls back to Polars' own list-vs-scalar broadcast when it does.
- **``/``, ``//`` and ``%`` over numbers** route to the ``ieee_quotient``
  kernel on every shape, because Polars' float kernels multiply by a single
  divisor's reciprocal rather than divide by it -- and which kernel a
  divisor meets depends on the engine and on how it splits the rows.
  Integer ``//`` and ``%`` are exact natively and stay there.
- **``**``** routes to the ``list_pow`` kernel whenever either side is a
  list, a per-row base with a per-period exponent included.
- **Comparisons, ``&``/``|``, and ``when``/``then``/``otherwise``** route
  through the ``list_conditional`` kernel whenever any operand is
  list-shaped, and stay on native Polars when none is.

``lower_polars(node)`` without a context cannot resolve a column's shape or
dtype. Ordinary arithmetic takes the plain-engine branch; typed operations
such as ``list.get`` and ``to_integer`` refuse because they cannot check
their operands. A caller holding a frame must pass its context.
"""

from __future__ import annotations

import math
from contextvars import ContextVar
from typing import TYPE_CHECKING, Final, Literal, TypeVar, assert_never, cast

import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN, integers_as_i64, wider_than_i64_at
from gaspatchio._semantic.calls import register_engine_calls
from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
)
from gaspatchio._semantic.operations import BINARY_OPERATIONS
from gaspatchio.frame.lowering._polars.comparisons import (
    per_period_operands,
    per_policy_operands,
    wide_literal,
    wide_literal_dtype,
)
from gaspatchio.frame.lowering._polars.expressions import literal_expression
from gaspatchio.frame.lowering._polars.list_eval import unwrap_for_list_eval
from gaspatchio.frame.lowering._polars.once import read_once
from gaspatchio.frame.lowering._polars.operators import dispatch_list_op
from gaspatchio.frame.lowering._polars.plugins import ieee_quotient, list_conditional
from gaspatchio.frame.lowering._polars.unknown import (
    POISON_MARK,
    holds_a_nan,
    nan_as_null,
    nan_literal,
    nan_poison,
    unknown_guard,
)
from gaspatchio.frame.lowering._polars.validation import (
    WIDE_ARITHMETIC_RULE,
    WIDE_CARRY_RULE,
    checked_numeric_predicate,
    read_as_i64_where_it_fits,
    read_in_the_finer_unit,
    read_in_the_shared_decimal,
    require_valid_rows,
    tagged_refusal,
)
from gaspatchio.frame.lowering.columns import column_reference
from gaspatchio.frame.lowering.context import LoweringContext
from gaspatchio.frame.lowering.ingress import NATIVE_REFS
from gaspatchio.frame.lowering.kinds import (
    apart,
    arithmetic_refusal,
    comparison_refusal,
    describe,
    flag_arithmetic_refusal,
    is_flag,
    kind_of,
    literal_dtype,
    operand_dtype,
    refusal,
    refuse_unless_a_number,
    shown,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio._shape import Shape

    # What a registered lowering is: the Call node it was registered for,
    # plus the frame context whose dtypes decide the shape-dependent half
    # of nearly every accessor body. The context is optional for the same
    # reason lower_polars's is -- a detached proxy has no frame to ask.
    # Type-checking only, and privately named: a module-level alias that
    # exists at run time trips stubtest.
    _LoweringRule = Callable[[Call, LoweringContext | None], pl.Expr]

    # The two types a comparison's operands resolve to, each None where it
    # could not be read without data. Type-checking only, as above.
    _OperandTypes = tuple[pl.DataType | None, pl.DataType | None]

    # BinOp.op's fifteen members, grouped by family purely so each match
    # below stays small enough to read at a glance and to keep McCabe
    # complexity low on any one function. The grouping has no bearing on how
    # a formula author writes a BinOp -- BinOp.op itself is one flat Literal
    # in ir.py. Type-checking only: nothing reads these at run time, and a
    # module-level Literal alias that exists at run time trips stubtest.
    _ArithmeticOp = Literal["add", "sub", "mul", "div", "floordiv", "mod", "pow"]
    _QuotientOp = Literal["div", "floordiv", "mod"]
    _ComparisonOp = Literal["lt", "le", "gt", "ge", "eq", "ne"]
    _LogicalOp = Literal["and", "or"]

    # The units a date and time or a duration is counted in, as Polars names them.
    _TimeUnit = Literal["ns", "us", "ms"]

__all__ = [
    "LOWERINGS",
    "NATIVE_REFS",
    "LoweringContext",
    "LoweringError",
    "a_flag_read_as_a_number",
    "ensure_rules_loaded",
    "lower_arg",
    "lower_binop_operands",
    "lower_mask",
    "lower_polars",
    "lower_predicate",
    "lower_predicate_mask",
    "on_codes_where_labelled",
    "register_elementwise",
    "register_lowering",
    "shape_of",
]


def _describe(node: OpNode) -> str:
    """Name the operation at ``node`` for use in a ``LoweringError`` message.

    Covers every node kind, not only the three that can actually raise,
    so ``LoweringError`` reads sensibly no matter which node it is ever
    constructed with; the trailing ``assert_never`` gives that completeness
    the same type-checked guarantee ``ir.walk`` relies on.
    """
    match node:
        case Col(name=name):
            description = f"column reference {name!r}"
        case Lit(value=value):
            description = f"literal {value!r}"
        case BinOp(op=op):
            description = f"binary operator {op!r}"
        case Call(name=name):
            description = f"call {name!r}"
        case WhenThen():
            description = "when/then/otherwise conditional"
        case State(name=name):
            description = f"rollforward state {name!r}"
        case EngineNative(engine=engine):
            description = f"engine-native expression (engine={engine!r})"
        case _ as unreachable:
            assert_never(unreachable)
    return description


class LoweringError(ValueError):
    """No Polars lowering rule exists for a node -- loud refusal, never a fallback.

    Carries the refusing ``node`` and a plain-English ``reason`` as
    attributes (in addition to folding both into ``str(self)``) so a
    caller that wants to inspect what failed programmatically can, rather
    than having to re-parse the message.
    """

    def __init__(self, node: OpNode, reason: str) -> None:
        """Build the error from the refusing ``node`` and the ``reason`` why."""
        self.node = node
        self.reason = reason
        message = f"No Polars lowering exists for {_describe(node)}: {reason}"
        super().__init__(message)


# Call.name -> the function that lowers a Call node with that name to a
# Polars expression. The rule modules under frame/lowering/rules/ populate
# it at import; ensure_rules_loaded() below is what guarantees they have
# been imported before anyone reads it. A name absent from this dict at
# lowering time raises LoweringError naming it -- an unregistered call has
# no fallback interpretation.
LOWERINGS: dict[str, _LoweringRule] = {}
register_engine_calls("polars", LOWERINGS)

# Bound loosely rather than to _LoweringRule itself: the decorator has to
# hand back the very function it was given, parameter names and all, or
# stubtest sees a rule module's functions as untyped callables.
_RuleT = TypeVar("_RuleT", bound="Callable[..., pl.Expr]")

# Two flags, not one. _RULES_LOADED is set only after load() returns, so a
# rule module that fails to import leaves the registry half-populated AND
# the door open -- the next call retries and raises the same ImportError at
# the same place, instead of the flag latching a broken registry into a
# silent "operation not registered" for the rest of the process.
# _RULES_LOADING is the re-entrancy guard that job otherwise did: a rules
# module that lowered something at import time would re-enter here and
# import the package a second time.
_RULES_LOADED = False
_RULES_LOADING = False


# The package composition root supplies the rule loader. Rules depend on this
# dispatcher; the dispatcher must not import its concrete implementations.
def _load_rules() -> None:
    """Refuse execution before the package installs its concrete loader."""
    msg = "Polars rule loader is not configured. Import gaspatchio.frame.lowering."
    raise RuntimeError(msg)


def ensure_rules_loaded() -> None:
    """Import the rule modules that populate ``LOWERINGS``, exactly once.

    Registration has to survive import order. A model that happens to touch
    ``lower_polars`` before it ever touches an accessor module would
    otherwise see an empty registry and refuse a ``Call`` that is perfectly
    well defined. Lowering calls this before dispatch; emission recognizes
    names from the engine-neutral call registry without loading rules. The
    package initializer supplies the loader so rule modules depend on this
    dispatcher without a reverse import, including function-local imports.
    """
    global _RULES_LOADED, _RULES_LOADING  # noqa: PLW0603
    if _RULES_LOADED or _RULES_LOADING:
        return
    _RULES_LOADING = True
    try:
        _load_rules()
    finally:
        _RULES_LOADING = False
    _RULES_LOADED = True


def register_lowering(name: str) -> Callable[[_RuleT], _RuleT]:
    """Register the Polars lowering for ``Call`` nodes named ``name``.

    Used as a decorator on the relocated body of an accessor method. The
    name is the one emission stamps on the ``Call``; registering the same
    name twice is refused rather than silently overwritten, because two
    rules for one operation means one of them is dead and nobody can tell
    which from the outside.
    """

    def decorator(rule: _RuleT) -> _RuleT:
        if name in LOWERINGS:
            msg = (
                f"{name!r} already has a registered Polars lowering -- two "
                "rules for one operation leaves one of them unreachable. "
                "Rename the operation or remove the duplicate registration."
            )
            raise ValueError(msg)
        LOWERINGS[name] = rule
        return rule

    return decorator


def register_elementwise(name: str, *, reads_a_number: bool = False) -> None:
    """Register the lowering for an operation that answers one value at a time.

    Fourteen operations share a body to the character: the value is
    lowered, and where the tree resolved it to a per-period column the
    engine's own method runs inside each row's list instead of on the
    column. Written once here rather than once per operation, because
    fourteen copies of five lines is fourteen places for the shape decision
    to drift, and the shape decision is the whole of what the body does.

    Applies where the identifier and the engine's method name are the same
    string, which is every operation reaching it today. An operation whose
    two names part company writes its own rule and says why in it.

    Args:
        name: The operation identifier, as emission stamps it on the
            ``Call``, and the engine method it lowers to.
        reads_a_number: Whether the operation reads a number, so that a flag
            operand is read as its 0.0/1.0 first (:func:`a_flag_read_as_a_number`).

    """

    def rule(node: Call, ctx: LoweringContext | None) -> pl.Expr:
        """Answer one value at a time, on the shape the tree resolved."""
        # A call that reads a number carries a whole number into a double, so
        # one past i64 is refused by name, as arithmetic on it is (section
        # 10): ``af.polno.log()`` over a UInt64 of 2**63 was answered.
        value_expr, shape = (
            lower_arg_read_as_i64(node.args[0], ctx, rule=WIDE_CARRY_RULE)
            if reads_a_number
            else lower_arg(node.args[0], ctx)
        )
        if reads_a_number:
            value_expr = a_flag_read_as_a_number(
                node.args[0], value_expr, shape, ctx, call=f"{name}()"
            )
        if shape == "list":
            element_method: Callable[[], pl.Expr] = getattr(pl.element(), name)
            return value_expr.list.eval(element_method())
        column_method: Callable[[], pl.Expr] = getattr(value_expr, name)
        return column_method()

    rule.__name__ = f"_lower_{name}"
    rule.__qualname__ = f"register_elementwise.{name}"
    register_lowering(name)(rule)


class _Lowered:
    """One node's Polars expression paired with the shape it resolves to.

    The shape travels with the expression so a parent rule never has to
    re-probe a child it just built: ``BinOp`` over two list operands knows
    its own result is list-shaped without asking the frame again.

    Two node kinds -- ``Call`` and ``EngineNative`` -- have no structural
    answer and can only find out by probing the frame's dtypes. For those
    the shape is resolved on first read and cached, so a formula that
    never asks (``af.reserve = af.value.projection.previous_period()``,
    assigned straight to a column) does not pay for a probe nobody wanted.
    """

    __slots__ = ("_ctx", "_shape", "expr")

    expr: pl.Expr
    _shape: Shape | None
    _ctx: LoweringContext | None

    def __init__(
        self,
        expr: pl.Expr,
        shape: Shape | None = None,
        ctx: LoweringContext | None = None,
    ) -> None:
        """Carry ``expr`` with either a known ``shape`` or the ``ctx`` to probe."""
        self.expr = expr
        self._shape = shape
        self._ctx = ctx

    @property
    def shape(self) -> Shape:
        """The shape this expression resolves to, probing the frame if needed."""
        resolved = self._shape
        if resolved is None:
            resolved = _expr_shape(self.expr, self._ctx)
            self._shape = resolved
        return resolved


def lower_polars(node: OpNode, ctx: LoweringContext | None = None) -> pl.Expr:
    """Turn one semantic op-tree node into the Polars expression that computes it.

    Pass ``ctx`` (see ``LoweringContext``) whenever the formula belongs to a
    frame: it is what lets the shape-dependent rules above pick the
    list-correct form. Without it every shape reads ``"unknown"`` and the
    plain-engine branch is taken throughout.

    Raises ``LoweringError`` -- never falls back to a guess -- for any node
    this module has no rule for.
    """
    return _lower(node, ctx).expr


def shape_of(node: OpNode, ctx: LoweringContext | None) -> Shape:
    """Return the shape the expression for ``node`` will have.

    Resolving a shape means lowering, because a node's shape is a fact
    about the expression it produces against a particular frame -- there is
    no cheaper honest answer for a ``Call`` or an ``EngineNative``.
    """
    return _lower(node, ctx).shape


def lower_arg(node: OpNode, ctx: LoweringContext | None) -> tuple[pl.Expr, Shape]:
    """Lower one argument of a registered ``Call``, with its resolved shape.

    This is the entry a rule module in ``frame/lowering/rules/`` uses to
    turn its own ``Call.args`` into expressions. It returns the shape
    alongside the expression because an accessor body that has to know
    whether it is looking at a per-period column or a per-policy one
    should read the answer the tree already resolved rather than probing
    the frame again.
    """
    lowered = _lower(node, ctx)
    if _CARRIED_BY.get() and isinstance(node, Col) and ctx is not None:
        dtype = _column_dtype(node.name, ctx)
        lowered = _a_wide_integer_read_where_it_fits(
            node, lowered, dtype, WIDE_CARRY_RULE
        )
    return lowered.expr, lowered.shape


# The calls whose answer carries their operand's own integer type: a least or
# greatest value, a bound, a rounding, a sign, a fill, a substitution, a
# period's value or a shift. Over a column wider than ``i64`` their answer
# kept that width on a LazyFrame's door, where a DataFrame's door had already
# read the column as the ``Int64`` its values fit, so one book answered two
# types. Each reads such a column as arithmetic does (section 10): as
# ``Int64`` where every value fits, refused by name where one does not. A
# conversion, a test of presence, a comparison and a membership test read the
# value by its digits and are not here.
_CARRYING_CALLS: frozenset[str] = frozenset(
    {
        "abs",
        "ceil",
        "clip",
        "fill_nan",
        "fill_null",
        "floor",
        "list.get",
        "list.reverse",
        "max",
        "min",
        "projection.at_period",
        "projection.broadcast_to_periods",
        "projection.next_period",
        "projection.previous_period",
        "projection.with_period",
        "replace",
        "round",
        "sign",
        "to_list",
    }
)

# Whether the call being lowered carries its operand's type (``_CARRYING_CALLS``),
# so that ``lower_arg`` reads a wide column operand of it through the checked
# narrowing. Set for the call's own operands and cleared for any call nested
# inside them, which sets its own.
_CARRIED_BY: ContextVar[bool] = ContextVar("_CARRIED_BY", default=False)


def lower_arg_read_as_i64(
    node: OpNode,
    ctx: LoweringContext | None,
    *,
    rule: str,
    signed_only: bool = False,
) -> tuple[pl.Expr, Shape]:
    """Lower the operand of a fold that would wrap in a width past ``i64``.

    A sum, a running sum or product and an absolute value compute in their
    operand's own type, as arithmetic does, so an operand still wider than
    ``i64`` is read as arithmetic reads one: as the ``Int64`` its values fit
    when the plan runs, and refused by name under ``rule`` where one does
    not (section 10). Any other operand is lowered as :func:`lower_arg`
    lowers it, its type asked only where a column or a call could be wide.
    ``signed_only`` leaves an unsigned width as it is, for a read that
    cannot wrap one.
    """
    lowered = _lower(node, ctx)
    dtype = _operand_type(node, lowered, ctx)
    if signed_only and isinstance(dtype, pl.DataType) and _unsigned_at_heart(dtype):
        # An unsigned value is its own absolute value and cannot wrap, so it
        # is read as any operation carrying its type reads one.
        rule = WIDE_CARRY_RULE
    lowered = _a_wide_integer_read_where_it_fits(node, lowered, dtype, rule)
    return lowered.expr, lowered.shape


def whole_numbers_folded_exactly(  # noqa: PLR0913 - the operand, its node, the frame, the fold, its answer's shape, its rule, and whether it multiplies
    value: pl.Expr,
    node: OpNode,
    ctx: LoweringContext | None,
    fold: Callable[[pl.Expr], pl.Expr],
    *,
    per_period: bool,
    rule: str,
    product: bool = False,
) -> pl.Expr | None:
    """Fold a run of whole numbers exactly, refusing an answer past ``i64``.

    A sum or a running fold of an ``i64`` run in its own width wraps:
    ``[2**63 - 1, 1].list.sum()`` answered ``-2**63`` and its ``cum_sum``
    the same in its second period. ``fold`` takes the run as a list
    expression and answers the fold's own value -- a list per period with
    ``per_period``, one number otherwise.

    The fold is taken in the run's own width, whose arithmetic is modular:
    where the exact answer lies inside ``i64`` -- the total, or every period
    of a running fold -- the wrapped one is that answer, digit for digit. So
    only the exact answer's range is checked, and a policy whose is not
    inside ``i64`` refuses the run by name under ``rule`` (section 10). A
    policy whose greatest value times its count of periods is under
    ``2**62`` -- for a product, whose greatest value raised to that count is
    -- cannot reach past ``i64`` in any period, and is cleared by two
    reductions: every real model's run. Any other policy's run is folded
    again in ``Int128``, where a total of ``i64`` values cannot wrap and a
    running product cannot before its first period past ``i64``, to read the
    exact answer's range; the cleared policies hand that fold an empty run,
    so it costs what the others' values cost and no more.

    Returns None where the operand is not a run of whole numbers, or its
    type cannot be read, for the caller to fold as it always did.
    """
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    element = dtype.inner if isinstance(dtype, pl.List) else None
    if element == pl.Boolean:
        # A run of flags folds as the whole numbers it indicates, a count, in
        # the i64 the record names: Polars answered a total UInt64 and a
        # running one List(UInt32).
        value, dtype, element = (
            value.cast(pl.List(pl.Int64)),
            pl.List(pl.Int64),
            pl.Int64(),
        )
    if not isinstance(element, pl.DataType) or not element.is_integer():
        return None
    greatest = pl.max_horizontal(
        value.list.max().cast(pl.Float64).abs(),
        value.list.min().cast(pl.Float64).abs(),
    )
    periods = value.list.len().cast(pl.Float64)
    # Half of 2**63 is the margin the doubles' own rounding is taken from.
    bound = greatest.log(2) * periods if product else greatest * periods
    reach = 62.0 if product else 2.0**62
    in_width = ((greatest <= 1) | (bound < reach)) if product else (bound < reach)
    in_width = in_width.fill_null(value=True)
    run = pl.when(in_width).then(pl.lit([], dtype=dtype)).otherwise(value)
    folded = fold(run.cast(pl.List(pl.Int128)))
    least, most = (
        (folded.list.min(), folded.list.max()) if per_period else (folded, folded)
    )
    fits = ((least >= I64_MIN) & (most <= I64_MAX)).fill_null(value=True)
    column = node.name if isinstance(node, Col) else None
    refused = require_valid_rows(fits, message=tagged_refusal(rule, column))
    return pl.when(refused == 0).then(fold(value))


def _unsigned_at_heart(dtype: pl.DataType) -> bool:
    """Say whether ``dtype``, or the element its lists hold, is an unsigned integer."""
    element = getattr(dtype, "inner", None)
    if isinstance(element, pl.DataType):
        return _unsigned_at_heart(element)
    return dtype.is_unsigned_integer()


def lower_mask(node: OpNode, ctx: LoweringContext | None) -> pl.Expr:
    """Lower a predicate node to the Float64 0/1 mask form.

    A comparison becomes its indicator (list-aware); anything else lowers
    normally. This is the same coercion an arithmetic parent applies to a
    comparison child, exposed for rules whose operation takes a predicate.
    """
    return _lower_mask(node, ctx)


def a_flag_read_as_a_number(
    node: OpNode,
    value: pl.Expr,
    shape: Shape,
    ctx: LoweringContext | None,
    *,
    call: str = "this call",
) -> pl.Expr:
    """Return the operand of a call that reads a number, a flag read as its 0/1.

    ``abs``, ``sign``, ``sqrt``, ``cbrt``, ``exp``, ``log``, ``log10``,
    ``log1p``, ``norm_cdf`` and ``round_sig_figs`` (11.1.12), and ``round``,
    ``floor`` and ``ceil`` (11.1.8), read a number, and a flag is the 0.0 or
    1.0 it indicates (11.1.25): a stored True/False, a comparison, or a test
    combined with ``&``, ``|`` or ``~``, per policy as per period, its answer
    a double. Left to Polars, six of them failed on a flag in its words
    (``sign operation not supported for dtype bool``) while the other seven
    cast it, and every one failed on a per-period comparison, so the flag is
    read as its double here, before the call's own rule, and a null stays
    null. ``value`` is the operand as the rule lowered it; a comparison is
    lowered again as the indicator an arithmetic operand reads, which is the
    same truth value in the type the call needs.

    Text, a date, a date and time and a time of day are not numbers, and
    each was read as one or refused in Polars' words: ``af.code.exp()``
    parsed the text ("2.0" answered 7.389, "A" a null), ``af.issue.log()``
    took the logarithm of the day count, ``af.issue.abs()`` failed as
    ```abs` operation not supported for dtype `date```. Each is refused
    where the line is written, naming ``call``.
    """
    if isinstance(node, BinOp) and node.op in _COMPARISON_OPS:
        return _lower_indicator(node, ctx).expr
    if isinstance(node, Lit):
        return value
    if ctx is None or (isinstance(node, BinOp) and node.op not in {"and", "or"}):
        return value
    dtype = (
        _column_dtype(node.name, ctx)
        if isinstance(node, Col)
        else ctx.dtype_of_expr(value)
    )
    # ``abs`` of a duration is a duration, and Polars answers it; every other
    # call here reads a number out of one, which no type of the vocabulary is.
    refuse_unless_a_number(
        line=call, operand=node, dtype=dtype, duration=call != "abs()"
    )
    if dtype == pl.Boolean:
        return value.cast(pl.Float64)
    if shape == "list" and dtype == pl.List(pl.Boolean):
        return value.cast(pl.List(pl.Float64))
    return value


def lower_predicate(node: OpNode, ctx: LoweringContext | None) -> tuple[pl.Expr, Shape]:
    """Lower one operand of ``&``, ``|`` or ``~`` in its predicate form.

    A direct reference to a stored ``f64`` or ``list[f64]`` column is a flag
    the model stored, and reads as one under the same checked exact 0/1
    contract a ``when`` condition applies to it (§11.1.18): a per-policy one
    becomes its Boolean, a per-period one stays its checked 0/1 run. Every
    other operand lowers as it always has.
    """
    lowered = _lower_stored_predicate(node, ctx)
    return lowered.expr, lowered.shape


def lower_predicate_mask(node: OpNode, ctx: LoweringContext | None) -> pl.Expr:
    """Lower one operand of a per-period ``&``, ``|`` or ``~`` to its 0/1 mask.

    ``lower_mask`` with the stored-predicate check of ``lower_predicate``
    applied first, so a stored indicator holding 2.0 refuses rather than
    entering the arithmetic that combines per-period predicates.
    """
    return _lower_mask(node, ctx, check_stored=True)


def unknown_of(node: OpNode, ctx: LoweringContext | None) -> pl.Expr | None:
    """Return where a per-policy test has no truth value (a NaN operand), or None.

    The public face of :func:`_unknown_of`, for a rule whose operation takes a
    predicate (``~``).
    """
    return _unknown_of(node, ctx)


def lower_binop_operands(
    node: BinOp, ctx: LoweringContext | None
) -> tuple[pl.Expr, Shape, pl.Expr, Shape]:
    """Lower both operands of ``node``, returning each with its shape.

    The predicate wrapper (``ConditionExpression``) needs the two sides
    separately -- the ``list_conditional`` kernel takes them as separate
    arguments and requires the list-typed one on the left -- so this is the
    one shape of lowered output that is not a single expression.
    """
    left, right = _comparison_operands(node, ctx)
    return left.expr, left.shape, right.expr, right.shape


def _lower(node: OpNode, ctx: LoweringContext | None) -> _Lowered:
    """Lower one node, carrying its resolved shape alongside the expression."""
    match node:
        case Col(name=name):
            return _Lowered(column_reference(name), _column_shape(name, ctx))
        case Lit(value=value):
            # A whole number is an Int64 wherever it was written, and a
            # sequence reaches Polars as the list it always did (see
            # literal_expression).
            return _Lowered(literal_expression(value), "scalar")
        case BinOp() as binop:
            return _lower_binop(binop, ctx)
        case Call() as call:
            return _Lowered(_lower_call(call, ctx), ctx=ctx)
        case WhenThen() as when_then:
            return _lower_when_then(when_then, ctx)
        case State() as state:
            reason = (
                "a rollforward state reference only means something inside "
                "a compiled rollforward -- it cannot be lowered as a bare "
                "Polars expression."
            )
            raise LoweringError(state, reason)
        case EngineNative() as native:
            return _Lowered(_lower_engine_native(native), ctx=ctx)
        case _ as unreachable:
            assert_never(unreachable)


# --- shape helpers ----------------------------------------------------------


def _column_shape(name: str, ctx: LoweringContext | None) -> Shape:
    """Resolve a column's shape from the context's schema, or ``unknown``."""
    if ctx is None:
        return "unknown"
    return ctx.shape_of_column(name)


def _expr_shape(expr: pl.Expr, ctx: LoweringContext | None) -> Shape:
    """Resolve an already-built expression's shape, or ``unknown``."""
    if ctx is None:
        return "unknown"
    return ctx.shape_of_expr(expr)


def _combine(left: Shape, right: Shape) -> Shape:
    """Combine two operand shapes per binary-op semantics (the shape SOT's rule)."""
    from gaspatchio._shape import _max_shape  # noqa: PLC0415

    return _max_shape(left, right)


# --- BinOp ------------------------------------------------------------------

_ARITHMETIC_OPS: frozenset[str] = frozenset(
    {"add", "sub", "mul", "div", "floordiv", "mod", "pow"}
)
_COMPARISON_OPS: frozenset[str] = frozenset({"lt", "le", "gt", "ge", "eq", "ne"})

# BinOp.op -> the pl.Expr method that applies it. Spelled as a method name
# rather than a Python operator so the same name also selects the
# pl.element() method inside a list.eval shim.
_ARITHMETIC_METHOD: dict[str, str] = {
    operation.identifier: operation.method
    for operation in BINARY_OPERATIONS
    if operation.family == "arithmetic"
}

# Ops whose Polars kernels reject a COMPOUND scalar against a list operand
# (supertype derivation fails); mul/div/floordiv/mod broadcast fine.
_ADDSUB_OPS: frozenset[str] = frozenset({"add", "sub"})

# Ops whose Polars float kernels, given ONE divisor for a whole array,
# multiply by its reciprocal instead of dividing: `x * (1/c)` is not `x / c`
# (135.021 / 1000 is 0.13502099999999997; 135.021 * 0.001 is 0.135021), and
# floor/mod inherit the error. Whether a divisor arrives as one value depends
# on the engine and on how it splits the rows, so these lower to the
# ieee_quotient kernel whenever both operands are numbers.
_QUOTIENT_OPS: frozenset[str] = frozenset({"div", "floordiv", "mod"})

# BinOp.op -> the operator name the list_conditional kernel expects.
_PLUGIN_OPERATOR: dict[str, str] = {
    "eq": "eq",
    "ne": "ne",
    "lt": "lt",
    "le": "lte",
    "gt": "gt",
    "ge": "gte",
}

# Operator inverse, applied when the list-typed operand ends up on the
# right and has to be commuted onto the kernel's `left` (which must be List
# dtype). Keyed by the kernel's own operator names.
_INVERSE_PLUGIN_OPERATOR: dict[str, str] = {
    "eq": "eq",
    "ne": "ne",
    "lt": "gt",
    "gt": "lt",
    "lte": "gte",
    "gte": "lte",
}


def _lower_binop(node: BinOp, ctx: LoweringContext | None) -> _Lowered:
    """Lower a binary operation, routing by operator family.

    The ``assert_never`` fallback still covers all fifteen members of
    ``BinOp.op`` -- the three ``case`` patterns are an exhaustive partition
    of that Literal, not a narrowing of it, so a sixteenth operator added
    without a home in one of the three families fails type-checking here.
    """
    match node.op:
        case "add" | "sub" | "mul" | "div" | "floordiv" | "mod" | "pow" as op:
            return _lower_arithmetic(op, node, ctx)
        case "lt" | "le" | "gt" | "ge" | "eq" | "ne" as op:
            return _lower_comparison(op, node, ctx)
        case "and" | "or" as op:
            return _lower_logical(op, node, ctx)
        case _ as unreachable:
            assert_never(unreachable)


def _lower_value(node: OpNode, ctx: LoweringContext | None) -> _Lowered:
    """Lower a node used as a *value* rather than as a predicate.

    A comparison in value position is an actuarial indicator -- "1.0 in the
    months this policy is in force" -- so it lowers to a Float64 0/1 mask,
    the same coercion the frame applies when a comparison is assigned to a
    column. In predicate position (a ``when`` condition) it stays a
    predicate; that path never comes through here.
    """
    if isinstance(node, BinOp) and node.op in _COMPARISON_OPS:
        return _lower_indicator(node, ctx)
    return _lower(node, ctx)


def _lower_arithmetic(
    op: _ArithmeticOp, node: BinOp, ctx: LoweringContext | None
) -> _Lowered:
    """Lower one of the seven arithmetic operators, shape-correctly.

    Each operand's type is asked once, and only where it can say something
    the rules below act on: a column off the frame's cached schema, and a
    call, a conditional or engine text by probing. An operand wider than
    ``i64`` is read through the checked narrowing first
    (:func:`_a_wide_integer_read_where_it_fits`), and the flag rules then
    read the same answer rather than probing again.
    """
    left = _lower_value(node.left, ctx)
    right = _lower_value(node.right, ctx)
    left_dtype = _operand_type(node.left, left, ctx)
    right_dtype = _operand_type(node.right, right, ctx)
    _refuse_arithmetic_polars_refuses(
        op, node, (left, left_dtype), (right, right_dtype), ctx
    )
    left = _a_wide_integer_read_where_it_fits(node.left, left, left_dtype)
    right = _a_wide_integer_read_where_it_fits(node.right, right, right_dtype)
    left = _a_flag_read_as_its_value(node.left, left, ctx, left_dtype)
    right = _a_flag_read_as_its_value(node.right, right, ctx, right_dtype)
    left, right = _flags_per_policy(
        op, node, (left, left_dtype), (right, right_dtype), ctx
    )
    method = _ARITHMETIC_METHOD[op]

    broadcast = _broadcast_side(op, node, left.shape, right.shape)
    if broadcast is not None:
        return _apply_with_broadcast(broadcast, method, left, right)

    if op in _QUOTIENT_OPS:
        quotient = _lower_ieee_quotient(op, node, left, right, ctx)
        if quotient is not None:
            return quotient

    base_is_list = left.shape == "list"
    if op == "pow" and (base_is_list or right.shape == "list"):
        return _Lowered(_lower_list_pow(left.expr, right.expr, base_is_list), "list")
    if op == "pow":
        left, right = _a_power_past_the_integer_promise(node, left, right, ctx)
    if base_is_list:
        return _Lowered(_lower_list_elementwise(method, left.expr, right.expr), "list")
    return _Lowered(
        getattr(left.expr, method)(right.expr), _combine(left.shape, right.shape)
    )


def _refuse_arithmetic_polars_refuses(
    op: _ArithmeticOp,
    node: BinOp,
    left: tuple[_Lowered, pl.DataType | str | None],
    right: tuple[_Lowered, pl.DataType | str | None],
    ctx: LoweringContext | None = None,
) -> None:
    """Refuse at the line arithmetic Polars would refuse in its own words.

    A literal answers from its value. An operand that is itself arithmetic
    -- ``af.issue + (af.term * 365)`` -- is typed by probing it, as a call is,
    so the line is refused as the simple ``af.issue + af.term`` is; a
    comparison or a logic is not asked (it is read as its indicator), and
    neither is an operand whose type could not be read.
    """

    def typed(side: OpNode, dtype: pl.DataType | str | None) -> pl.DataType | None:
        if isinstance(side, Lit):
            return literal_dtype(side.value)
        if (
            dtype == _NOT_ASKED
            and isinstance(side, BinOp)
            and side.op in _ARITHMETIC_OPS
            and ctx is not None
        ):
            lowered = left[0] if side is node.left else right[0]
            try:
                return ctx.dtype_of_expr(lowered.expr)
            except Exception:  # noqa: BLE001 -- an operand nothing can type is not asked
                return None
        return dtype if isinstance(dtype, pl.DataType) else None

    refused = arithmetic_refusal(
        op=op,
        left=node.left,
        left_dtype=typed(node.left, left[1]),
        right=node.right,
        right_dtype=typed(node.right, right[1]),
        per_period="list" in (left[0].shape, right[0].shape),
    )
    if refused is not None:
        raise refused


# What an operand's type was found to be before the rules below read it: a
# type, None where nothing could say, and this where nobody asked -- a
# literal, which answers from its value, and an arithmetic, comparison or
# logical sub-expression, which each rule judges for itself.
_NOT_ASKED: Final = "not asked"


def _operand_type(
    node: OpNode, lowered: _Lowered, ctx: LoweringContext | None
) -> pl.DataType | str | None:
    """Return one arithmetic operand's type, asked once for every rule that reads it."""
    if ctx is None or isinstance(node, (Lit, BinOp)):
        return _NOT_ASKED
    if isinstance(node, Col):
        return _column_dtype(node.name, ctx)
    return ctx.dtype_of_expr(lowered.expr)


def _a_wide_integer_read_where_it_fits(
    node: OpNode,
    lowered: _Lowered,
    dtype: pl.DataType | str | None,
    rule: str = WIDE_ARITHMETIC_RULE,
) -> _Lowered:
    """Return an operand wider than ``i64`` read as ``Int64``, refusing a value past it.

    A ``UInt64``, ``Int128`` or ``UInt128`` column whose every value fits an
    ``i64`` is read as one where its values are in hand (section 10). One
    still that wide here either arrived lazily, with no values to judge, or
    holds a value no ``i64`` carries, and arithmetic in its own width wraps:
    ``7 - 10`` on a ``UInt64`` answered 18,446,744,073,709,551,613. So the
    operand is read as ``Int64`` at run time, and a value that does not fit
    refuses the run by name rather than wrapping (11.1.25: an ``i64``
    operand, an ``i64`` answer).
    """
    if not isinstance(dtype, pl.DataType):
        return lowered
    depth = wider_than_i64_at(dtype)
    if depth is None:
        return lowered
    column = node.name if isinstance(node, Col) else None
    read = read_as_i64_where_it_fits(
        lowered.expr,
        integers_as_i64(dtype, wide=True),
        depth=depth,
        column=column,
        rule=rule,
    )
    return _Lowered(read, lowered.shape)


def _a_flag_read_as_its_value(
    node: OpNode,
    lowered: _Lowered,
    ctx: LoweringContext | None,
    dtype: pl.DataType | str | None = _NOT_ASKED,
) -> _Lowered:
    """Return a per-period Boolean operand of arithmetic as its 0/1 Float64 run.

    A per-policy flag already reads as 1 or 0 in arithmetic -- Polars widens a
    Boolean scalar itself -- and a per-period one did not: inside
    ``list.eval`` a Boolean element met by a float literal fails with "failed
    to materialize unknown type", so ``af.in_force * 1.0`` and
    ``af.in_force - 0.5`` refused while ``1.0 * af.in_force`` worked, and the
    forms that worked disagreed about the type (``+ 1`` an Int32 run,
    ``flag * flag`` a UInt64 one). Every per-period flag is now read the one
    way a per-policy flag is, as 0.0 or 1.0, before any route is chosen, so
    the answer does not depend on operand order or on the operator -- the
    quotient kernel included.

    Only an operand that can hold a Boolean run is asked: a column, by the
    frame's cached schema, and a call, a conditional or engine text by
    probing. An arithmetic, comparison or logical sub-expression is already
    a number here, and a scalar is left to Polars.
    """
    if ctx is None or lowered.shape != "list" or isinstance(node, BinOp):
        return lowered
    if dtype == _NOT_ASKED:
        dtype = _operand_type(node, lowered, ctx)
    if dtype != pl.List(pl.Boolean):
        return lowered
    return _Lowered(lowered.expr.cast(pl.List(pl.Float64)), "list")


def _flags_per_policy(
    op: _ArithmeticOp,
    node: BinOp,
    left_operand: tuple[_Lowered, pl.DataType | str | None],
    right_operand: tuple[_Lowered, pl.DataType | str | None],
    ctx: LoweringContext | None,
) -> tuple[_Lowered, _Lowered]:
    """Refuse two per-policy flags in one operation; read one as its 0/1 double.

    A per-policy flag beside a number reads as 0.0 or 1.0 (11.1.25), the way
    a per-period flag (:func:`_a_flag_read_as_its_value`), a stored
    comparison and the JAX engine already read one. Left to Polars the
    widening depended on the other operand: ``af.smoker + 1`` answered an
    Int32 the record called ``i64`` while every other reader answered
    ``f64``, ``2 // af.smoker`` answered null where the per-period form
    answers infinity, and ``af.smoker ** 2.0`` failed inside Polars, which
    raises no Boolean to a power. So the flag is cast to Float64 before any
    route is chosen, and every operator answers ``f64`` either side of it.
    A decimal literal beside it is held as the Float64 it was written as,
    so the frame's schema states the answer's type before the frame runs.

    Two per-policy flags in one operation are not admitted (11.1.25): Polars
    failed on ``af.smoker * af.rider`` only when the frame ran, in its own
    words, and the line is refused where it is written, naming the move.

    Each operand is asked only as far as it can answer cheaply first: a
    literal by its value and a column off the frame's cached schema, and an
    arithmetic or comparison sub-expression -- a number already -- not at
    all. A per-policy call, conditional or engine text is probed once, as a
    per-period one already is.
    """
    (left, left_dtype), (right, right_dtype) = left_operand, right_operand
    if ctx is None:
        return left, right
    left_flag = _may_hold_a_flag(node.left) and _a_flag_per_policy(
        node.left, left, ctx, left_dtype
    )
    right_flag = _may_hold_a_flag(node.right) and _a_flag_per_policy(
        node.right, right, ctx, right_dtype
    )
    if left_flag and right_flag:
        raise flag_arithmetic_refusal(op=op, left=node.left, right=node.right)
    if left_flag:
        return _a_flag_as_its_double(left), _a_decimal_held_as_one(node.right, right)
    if right_flag:
        return _a_decimal_held_as_one(node.left, left), _a_flag_as_its_double(right)
    return left, right


# 11.1.25's integer power promise: two integers answer an integer only for an
# exponent in [0, 2**32 - 1].
_INTEGER_EXPONENTS: range = range(2**32)


def _a_power_past_the_integer_promise(
    node: BinOp, left: _Lowered, right: _Lowered, ctx: LoweringContext | None
) -> tuple[_Lowered, _Lowered]:
    """Return an integer raised to a written exponent past the promise, as doubles.

    Two integers keep an integer power only for an exponent in ``[0,
    2**32 - 1]`` (11.1.25), and ``af.a ** -1`` is ``1 / a``, a double. Left
    to Polars it failed when the frame ran -- ``conversion from `i32` to
    `u32` failed in column 'literal'``, Polars' integer power taking its
    exponent as unsigned -- while the frame's schema said the answer was an
    integer. A literal exponent is in the record, so the type is decided
    where the line is written: the base and the exponent are read as their
    doubles and the power is one binary64 ``pow``, as every list-shaped power
    already is. An exponent that is a column keeps the integer rule, whose
    values only the run can see.
    """
    exponent = node.right
    if (
        ctx is None
        or not isinstance(exponent, Lit)
        or type(exponent.value) is not int
        or exponent.value in _INTEGER_EXPONENTS
    ):
        return left, right
    base = (
        _column_dtype(node.left.name, ctx)
        if isinstance(node.left, Col)
        else ctx.dtype_of_expr(left.expr)
    )
    if base is None or not base.is_integer():
        return left, right
    return (
        _Lowered(left.expr.cast(pl.Float64), left.shape),
        _Lowered(pl.lit(float(exponent.value), dtype=pl.Float64), "scalar"),
    )


def _a_flag_as_its_double(lowered: _Lowered) -> _Lowered:
    """Return a per-policy flag operand as its 0.0/1.0 Float64, null kept null."""
    return _Lowered(lowered.expr.cast(pl.Float64), lowered.shape)


def _may_hold_a_flag(node: OpNode) -> bool:
    """Say whether an operand can be a Boolean at all, before asking its type.

    An arithmetic sub-expression is a number, and a comparison in value
    position is its 0/1 indicator; ``&`` and ``|``, a column, a call, a
    conditional and engine text can each be a flag.
    """
    if isinstance(node, Lit):
        return isinstance(node.value, bool)
    if isinstance(node, BinOp):
        return node.op in {"and", "or"}
    return True


def _a_decimal_literal(node: OpNode) -> bool:
    """Say whether an operand is a decimal written into the formula."""
    return isinstance(node, Lit) and type(node.value) is float


def _a_flag_per_policy(
    node: OpNode,
    lowered: _Lowered,
    ctx: LoweringContext,
    dtype: pl.DataType | str | None = _NOT_ASKED,
) -> bool:
    """Say whether an operand holds one flag per policy (a per-period one is read).

    A per-period flag has been read as its 0/1 run already, so only a
    per-policy Boolean answers yes.
    """
    if isinstance(node, Lit):
        return isinstance(node.value, bool)
    if lowered.shape == "list":
        return False
    if dtype == _NOT_ASKED:
        dtype = (
            _column_dtype(node.name, ctx)
            if isinstance(node, Col)
            else ctx.dtype_of_expr(lowered.expr)
        )
    return dtype == pl.Boolean


def _a_decimal_held_as_one(node: OpNode, lowered: _Lowered) -> _Lowered:
    """Return a decimal literal as a typed Float64, and any other operand as is."""
    if not _a_decimal_literal(node):
        return lowered
    value = cast("Lit", node).value
    return _Lowered(pl.lit(value, dtype=pl.Float64), "scalar")


def _broadcast_side(
    op: _ArithmeticOp, node: BinOp, left_shape: Shape, right_shape: Shape
) -> Literal["left", "right"] | None:
    """Name the ``+``/``-`` operand that needs an explicit broadcast (gh#53).

    Polars broadcasts a scalar into list arithmetic natively when the
    scalar side is a bare column or a literal, but a *compound* scalar
    expression (``col * col``, a lookup, a conditional) fails supertype
    derivation -- and only for add/sub, so the same formula lived or died
    on operand order. Returns the side to pre-broadcast with ``repeat_by``,
    or ``None`` to leave the native plan untouched (which is every shape
    Polars already handles, so working models keep their existing plans).

    ``Col`` on the left and ``Col``/a single-valued ``Lit`` on the right
    are the leaves Polars handles itself. A literal *on the left* is the
    reflected form (``1 - af.pols_if``), which the framework has always
    broadcast.
    """
    if op not in _ADDSUB_OPS:
        return None
    if (
        left_shape == "scalar"
        and right_shape == "list"
        and not isinstance(node.left, Col)
    ):
        return "left"
    if (
        right_shape == "scalar"
        and left_shape == "list"
        and (
            isinstance(node.right, (BinOp, Call, WhenThen, EngineNative))
            or _is_sequence_literal(node.right)
        )
    ):
        return "right"
    return None


def _is_sequence_literal(node: OpNode) -> bool:
    """Report whether a literal holds a sequence rather than one value.

    Polars broadcasts a *scalar* literal into list arithmetic itself, and
    that is the exemption above. A sequence literal is not one: to Polars
    it is a list-typed literal, so it needs the same explicit
    pre-broadcast a compound scalar expression does -- which is the path a
    sequence took when it reached lowering as engine-native text.
    """
    return isinstance(node, Lit) and isinstance(node.value, tuple)


def _apply_with_broadcast(
    side: Literal["left", "right"], method: str, left: _Lowered, right: _Lowered
) -> _Lowered:
    """Repeat the named scalar operand to the other side's per-row list lengths."""
    if side == "left":
        base = left.expr.repeat_by(right.expr.list.len())
        return _Lowered(getattr(base, method)(right.expr), "list")
    arg = right.expr.repeat_by(left.expr.list.len())
    return _Lowered(getattr(left.expr, method)(arg), "list")


def _lower_list_pow(base: pl.Expr, exponent: pl.Expr, base_is_list: bool) -> pl.Expr:  # noqa: FBT001
    """Raise to a power where either side is list-shaped.

    Both go to the ``list_pow`` kernel: a list base element by element, and a
    scalar base raised to each period's exponent of its row.
    """
    return dispatch_list_op("pow", base, (exponent,), {}, base_is_list=base_is_list)


def _lower_ieee_quotient(
    op: _ArithmeticOp,
    node: BinOp,
    left: _Lowered,
    right: _Lowered,
    ctx: LoweringContext | None,
) -> _Lowered | None:
    """Lower ``/``, ``//`` or ``%`` over two numbers to the IEEE kernel.

    ``/`` must mean IEEE division, and Polars' float kernels do not give it
    whenever the divisor reaches them as one value -- a literal, a column
    holding one constant, a value inside ``list.eval`` -- because they
    multiply by its reciprocal. ``ieee_quotient`` divides every element by
    its own divisor on either shape, so every numeric quotient goes there.

    Returns ``None`` -- the native operator -- when either operand is not a
    number this lowering can see (a duration, a decimal, an operand whose
    dtype a detached formula cannot resolve), and for ``//``/``%`` over two
    integers, which Polars computes exactly in integer arithmetic.
    """
    kinds = (_numeric_kind(node.left, left, ctx), _numeric_kind(node.right, right, ctx))
    if None in kinds:
        return None
    if op != "div" and "float" not in kinds:
        return None
    quotient = ieee_quotient(left.expr, right.expr, cast("_QuotientOp", op))
    return _Lowered(quotient, _combine(left.shape, right.shape))


def _numeric_kind(
    node: OpNode, lowered: _Lowered, ctx: LoweringContext | None
) -> Literal["int", "float"] | None:
    """Say whether an operand is an integer, a binary64 float, or neither.

    A literal answers from its own value; anything else asks the frame for
    its dtype (a list answers for its elements). ``Float32`` answers
    neither, so a single-precision quotient keeps Polars' own dtype.
    """
    if isinstance(node, Lit):
        dtype: pl.DataType | None = _LITERAL_DTYPE.get(type(node.value))
    elif ctx is None:
        return None
    elif isinstance(node, Col):
        dtype = _column_dtype(node.name, ctx)
    else:
        dtype = ctx.dtype_of_expr(lowered.expr)
    if isinstance(dtype, pl.List):
        dtype = cast("pl.DataType", dtype.inner)
    if dtype == pl.Float64:
        return "float"
    if dtype == pl.Boolean or (dtype is not None and dtype.is_integer()):
        return "int"
    return None


# What a Python literal divides as: its own type, and nothing else -- a date
# or a string literal is not a number, whatever Polars would make of it.
_LITERAL_DTYPE: dict[type, pl.DataType] = {
    float: pl.Float64(),
    int: pl.Int64(),
    bool: pl.Boolean(),
}


def _column_dtype(name: str, ctx: LoweringContext) -> pl.DataType | None:
    """Read a column's dtype from the frame's cached schema, probing if absent."""
    schema = getattr(ctx.frame, "_schema", None)
    if schema is not None and name in schema:
        return cast("pl.DataType", schema[name])
    return ctx.dtype_of_expr(column_reference(name))


def _lower_list_elementwise(method: str, base: pl.Expr, arg: pl.Expr) -> pl.Expr:
    """Apply ``method`` element-wise inside a list receiver's own lists.

    ``list.eval`` cannot see named columns, so an argument that references
    any column has to go through Polars' own list-vs-scalar broadcast
    instead -- which is what the refusal from ``unwrap_for_list_eval``
    signals.
    """
    try:
        element_method = getattr(pl.element(), method)
        return base.list.eval(element_method(unwrap_for_list_eval(arg)))
    except (TypeError, ValueError):
        return cast("pl.Expr", getattr(base, method)(arg))


def _lower_comparison(
    op: _ComparisonOp, node: BinOp, ctx: LoweringContext | None
) -> _Lowered:
    """Lower a comparison as a native Polars predicate.

    This is the predicate form: ``pl.col("age") >= pl.col("retirement_age")``.
    The indicator form (Float64 0/1, list-aware) is ``_lower_indicator``;
    which one applies is the caller's choice of position, not the node's.
    """
    left, right, dtypes = _typed_comparison_operands(node, ctx)
    return _Lowered(
        _compared_per_policy(op, left, right, dtypes),
        _combine(left.shape, right.shape),
    )


def _comparison_operands(
    node: BinOp, ctx: LoweringContext | None
) -> tuple[_Lowered, _Lowered]:
    """Lower a comparison's two operands, refusing two of different kinds.

    Every route a comparison takes -- a predicate, a stored indicator, a
    ``when`` condition, the predicate wrapper's own operands -- lowers its
    operands here, so the refusal holds in every position and in both
    operand orders.
    """
    left, right, _ = _typed_comparison_operands(node, ctx)
    return left, right


def _typed_comparison_operands(
    node: BinOp, ctx: LoweringContext | None
) -> tuple[_Lowered, _Lowered, _OperandTypes]:
    """Lower a comparison's two operands with the types they resolve to.

    A whole number past ``i64`` reaches a comparison only where the frame
    admitted it, against a column still wider than ``i64``; it is written as
    the narrowest type that holds it, since no ``Int64`` does.
    """
    left = _comparison_operand(node.left, ctx)
    right = _comparison_operand(node.right, ctx)
    dtypes = _refuse_a_comparison_across_kinds(node, left, right, ctx)
    return left, right, dtypes


def _comparison_operand(node: OpNode, ctx: LoweringContext | None) -> _Lowered:
    """Lower one comparison operand, a whole number past ``i64`` in its own type.

    A comparison that is itself an operand is its truth value per policy and
    its 0.0/1.0 indicator per period, as a stored one is (11.1.26): Polars
    has no per-period predicate to compare, and ``(af.month >= 1) == 1``
    failed when the frame ran, in Polars' words, where the JAX engine
    answered the indicator.
    """
    if isinstance(node, Lit) and _past_i64(node.value):
        return _Lowered(wide_literal(cast("int", node.value)), "scalar")
    if not (isinstance(node, BinOp) and node.op in _COMPARISON_OPS):
        return _lower(node, ctx)
    operands = _typed_comparison_operands(node, ctx)
    shape = _combine(operands[0].shape, operands[1].shape)
    sides = _sides_that_hold_a_nan(node, operands[0], operands[1], ctx)
    if shape == "list":
        indicator = _list_conditional_for(
            node, operands, pl.lit(1.0), pl.lit(0.0), ctx=ctx
        )
        return _Lowered(_poisoned(indicator, sides), "list")
    truth = _compared_per_policy(_comparison_op(node.op), *operands)
    if sides:
        # A NaN operand leaves no truth value to compare: the indicator,
        # NaN there, is what the outer comparison reads (11.1.26).
        return _Lowered(_poisoned(truth.cast(pl.Float64), sides), shape)
    return _Lowered(truth, shape)


def _past_i64(value: object) -> bool:
    """Say whether ``value`` is a whole number no ``i64`` holds."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and not -(2**63) <= value <= 2**63 - 1
    )


def _refuse_a_comparison_across_kinds(
    node: BinOp, left: _Lowered, right: _Lowered, ctx: LoweringContext | None
) -> _OperandTypes:
    """Refuse a comparison whose operands are two kinds, naming the move.

    ``af.d < 3`` over a column of dates ran and answered false for every
    policy: Polars compared each date's day count with 3. 11.1.26 infers no
    ordering between two families, so two operands of different kinds
    (:mod:`gaspatchio.frame.lowering.kinds`) are refused at the line,
    scalar and per period alike. An operand whose type cannot be read
    without data, or a null, is left as it was. A date and time with a time
    zone against one without is refused the same way: one is an instant and
    the other a wall-clock reading, and Polars refused the pair only when
    the frame ran.

    Returns the two types read, for the routes that decide a comparison
    exactly; the right one is None where the left settled the question.
    """
    left_dtype = _comparison_operand_dtype(node.left, left, ctx)
    if left_dtype is None or kind_of(left_dtype) is None:
        return left_dtype, None
    right_dtype = _comparison_operand_dtype(node.right, right, ctx)
    if right_dtype is None:
        return left_dtype, None
    refused = comparison_refusal(
        op=node.op,
        left=node.left,
        left_dtype=left_dtype,
        right=node.right,
        right_dtype=right_dtype,
    ) or _a_zone_against_none(node, left_dtype, right_dtype)
    refused = refused or _a_band_ordered_against_text(node, left_dtype, right_dtype)
    if refused is not None:
        raise refused
    return left_dtype, right_dtype


# The four comparisons that order their operands, rather than test them equal.
_ORDERINGS: frozenset[str] = frozenset({"lt", "le", "gt", "ge"})


def _a_band_ordered_against_text(
    node: BinOp, left: pl.DataType, right: pl.DataType
) -> TypeError | None:
    """Return the refusal for a band ordered against text, or against another band.

    A band from ``cut`` is an ordered category (an ``Enum``), and its order is
    its categories', where text's is its letters' -- and the two disagree:
    ``"under 30"`` stands below ``"30 to 59"`` as a band and after it as
    text. ``band < "30 to 59"`` answered the band's order per policy and the
    letters' per period, on the JAX engine and in the reader, so one line
    meant two things by shape, and the record, which holds no ordered
    category, could say only the second (11.1.26). It is refused by name on
    both shapes, naming the two lines that each mean one thing. Equality and
    membership have one meaning and answer. Two bands of the same categories
    keep their categories' order; two of different categories have none.
    """
    if node.op not in _ORDERINGS:
        return None
    ours, theirs = _element_of(left), _element_of(right)
    bands = (isinstance(ours, pl.Enum), isinstance(theirs, pl.Enum))
    if not any(bands) or (all(bands) and ours == theirs):
        return None
    band = node.left if bands[0] else node.right
    other = node.right if bands[0] else node.left
    symbol = {"lt": "<", "le": "<=", "gt": ">", "ge": ">="}[node.op]
    if all(bands):
        msg = (
            f"{shown(node.left)} {symbol} {shown(node.right)}: the comparison "
            "orders two bands of different categories, and there is no order "
            "between them -- each band's order is its own categories'. Compare "
            "the numbers the two bands were cut from, which have one order."
        )
        return TypeError(msg)
    msg = (
        f"{shown(node.left)} {symbol} {shown(node.right)}: the comparison orders "
        f"{shown(band)}, a band -- an ordered category, as cut() makes one -- "
        f"against {shown(other)}, text. A band's order is its categories' and "
        "text's is its letters', and the two disagree (\"under 30\" comes "
        'before "30 to 59" as a band and after it as text), so the line has '
        "two meanings and is refused rather than answered by one of them. To "
        "mean the band's order, compare the number the band was cut from "
        "(af.issue_age < 30); to mean the letters' order, compare the band's "
        'text (.to_text() < "30 to 59"). Equality, inequality and is_in() '
        "answer as written."
    )
    return TypeError(msg)


def _a_zone_against_none(
    node: BinOp, left: pl.DataType, right: pl.DataType
) -> TypeError | None:
    """Return the refusal for a zoned date and time compared with a zone-naive one."""
    zones = [getattr(_element_of(dtype), "time_zone", None) for dtype in (left, right)]
    if kind_of(left) != "datetime" or (zones[0] is None) == (zones[1] is None):
        return None
    zoned = shown(node.left if zones[0] is not None else node.right)
    naive = shown(node.right if zones[0] is not None else node.left)
    msg = (
        f"A comparison sets {zoned}, a date and time in the time zone "
        f"{zones[0] or zones[1]!r}, against {naive}, a date and time with no "
        "time zone. The first is an instant and the second a reading of a "
        "clock with no place, so there is no order between them until one is "
        "given the other's footing; Polars would refuse the pair only when the "
        "frame runs, so the line is refused here. Give the zone-naive one its "
        "zone where the data is loaded, or convert the zoned one into "
        "zone-naive readings, and compare the two in one footing."
    )
    return TypeError(msg)


def _an_untyped_comparison(node: BinOp, left_dtype: pl.DataType | None) -> TypeError:
    """Return the refusal for a per-period comparison whose operand type is unread.

    The kernel a per-period comparison runs through reads both sides as
    doubles. Two whole numbers past ``2**53``, two dates and times and two
    durations are handed to it as their exact difference instead, and two
    decimals as a key -- which needs both types. An operand the frame could
    not type before the run would have been compared by its nearest double,
    neighbouring whole numbers answering equal, so the line is refused here.
    """
    unread = node.left if left_dtype is None else node.right
    msg = (
        f"A per-period comparison sets {shown(node.left)} against "
        f"{shown(node.right)}, and the type of {shown(unread)} could not be "
        "read before the run. A per-period comparison decides whole numbers "
        "past 2**53, dates and times, durations and decimals exactly only by "
        "their types; without one it would compare the nearest doubles, under "
        "which neighbouring whole numbers are equal, so the line is refused "
        "rather than answered that way. Give the operand a type the frame can "
        "read -- a column of the frame, a literal, or the expression cast to "
        "the type it holds -- and compare it again."
    )
    return TypeError(msg)


def _compared_per_policy(
    op: _ComparisonOp, left: _Lowered, right: _Lowered, dtypes: _OperandTypes
) -> pl.Expr:
    """Apply a comparison per policy, two whole numbers in a type holding both.

    Polars compares two values of one type exactly; ``UInt64`` ``2**64 - 1``
    against an ``Int64`` answered null, so a pair whose types differ and one
    of which is wider than ``i64`` is read in a type that holds both first.
    """
    left_dtype, right_dtype = dtypes
    exact = (
        None
        if left_dtype is None or right_dtype is None
        else per_policy_operands((left.expr, left_dtype), (right.expr, right_dtype))
    )
    if exact is None:
        return _apply_comparison(op, left.expr, right.expr)
    return _apply_comparison(op, *exact)


def _comparison_operand_dtype(
    node: OpNode, lowered: _Lowered, ctx: LoweringContext | None
) -> pl.DataType | None:
    """Return the type one comparison operand resolves to, or None.

    A literal answers from its own value and a column from the frame's
    cached schema; anything else is asked of the frame, and nothing is
    without one.
    """
    if isinstance(node, Lit):
        if _past_i64(node.value):
            return wide_literal_dtype(cast("int", node.value))
        if isinstance(node.value, tuple):
            return _sequence_type(lowered.expr)
        return literal_dtype(node.value)
    if ctx is None:
        return None
    if isinstance(node, Col):
        return _column_dtype(node.name, ctx)
    return ctx.dtype_of_expr(lowered.expr)


def _sequence_type(expr: pl.Expr) -> pl.DataType | None:
    """Return the type a sequence written into a formula is held in, or None.

    A sequence compared with a run is one timeline every policy shares --
    ``af.k > (2**53, 2**53)`` -- and reads no column, so an empty frame types
    it. Untyped, it was compared in the kernel's doubles, and ``2**53 + 1``
    against its ``2**53`` answered 0.0 in every period.
    """
    try:
        return pl.LazyFrame().select(expr.alias("_t")).collect_schema().get("_t")
    except pl.exceptions.PolarsError:
        return None


def _apply_comparison(op: _ComparisonOp, left: pl.Expr, right: pl.Expr) -> pl.Expr:
    """Apply one of the six comparison operators to two already-lowered operands."""
    match op:
        case "lt":
            return left < right
        case "le":
            return left <= right
        case "gt":
            return left > right
        case "ge":
            return left >= right
        case "eq":
            return left == right
        case "ne":
            return left != right
        case _ as unreachable:
            assert_never(unreachable)


def _lower_indicator(node: BinOp, ctx: LoweringContext | None) -> _Lowered:
    """Lower a comparison to a Float64 0/1 indicator.

    A list-shaped comparison cannot be expressed natively at all (Polars
    refuses list-vs-scalar comparison outright), so it routes through the
    ``list_conditional`` kernel with 1.0/0.0 branches; a scalar comparison
    is the native predicate cast to Float64.
    """
    left, right, dtypes = _typed_comparison_operands(node, ctx)
    shape = _combine(left.shape, right.shape)
    sides = _sides_that_hold_a_nan(node, left, right, ctx)
    if shape == "list":
        expr = _list_conditional_for(
            node, (left, right, dtypes), pl.lit(1.0), pl.lit(0.0), ctx=ctx
        )
        return _Lowered(_poisoned(expr, sides), "list")
    op = _comparison_op(node.op)
    indicator = _compared_per_policy(op, left, right, dtypes).cast(pl.Float64)
    return _Lowered(_poisoned(indicator, sides), shape)


# --- A NaN operand: the comparison's unknown ---------------------------------


def _sides_that_hold_a_nan(
    node: BinOp, left: _Lowered, right: _Lowered, ctx: LoweringContext | None
) -> tuple[_Lowered, ...]:
    """Return the operands of a comparison that can hold a NaN, in written order.

    A double column or expression can, and so can a comparison or a test
    combined with ``&``, ``|`` or ``~`` whose own operand can, read as its
    indicator. A literal can only where it was written as NaN. Nothing is
    asked without a frame. See :mod:`~gaspatchio.frame.lowering._polars.unknown`.
    """
    if ctx is None:
        return ()
    found: list[_Lowered] = []
    for side_node, side in ((node.left, left), (node.right, right)):
        if isinstance(side_node, Lit):
            value = side_node.value
            if isinstance(value, float) and math.isnan(value):
                found.append(side)
            continue
        if holds_a_nan(_comparison_operand_dtype(side_node, side, ctx)):
            found.append(side)
    return tuple(found)


def _poisoned(answer: pl.Expr, sides: tuple[_Lowered, ...]) -> pl.Expr:
    """Return a double ``answer`` made NaN wherever one of ``sides`` is NaN."""
    for side in sides:
        answer = answer + nan_poison(side.expr, side.shape)
    return answer


def _unknown_of(node: OpNode, ctx: LoweringContext | None) -> pl.Expr | None:
    """Return where a per-policy test has no truth value, or None if it always has.

    Only a comparison has none: where an operand is NaN and neither is null
    (a null wins over a NaN). A per-policy ``&``, ``|`` or ``~`` result is a
    Boolean wherever it is read, stored or inline -- a null where a side had
    no truth value (11.1.27, :func:`_lower_logical`) -- so whatever reads it,
    an enclosing ``&`` or a ``when`` alike, reads that null.
    """
    if isinstance(node, BinOp) and node.op in _COMPARISON_OPS:
        return _unknown_of_a_comparison(node, ctx)
    return None


def _unknown_of_a_comparison(
    node: BinOp, ctx: LoweringContext | None
) -> pl.Expr | None:
    """Return where a per-policy comparison has a NaN operand and no null one."""
    left, right, _ = _typed_comparison_operands(node, ctx)
    if _combine(left.shape, right.shape) == "list":
        return None
    sides = _sides_that_hold_a_nan(node, left, right, ctx)
    if not sides:
        return None
    nan = sides[0].expr.is_nan()
    for side in sides[1:]:
        nan = nan | side.expr.is_nan()
    # A null on a side that is not a literal wins over the NaN.
    for side_node, side in ((node.left, left), (node.right, right)):
        if not isinstance(side_node, Lit):
            nan = nan & side.expr.is_not_null()
    return nan


def _a_side_unknown(node: BinOp, ctx: LoweringContext | None) -> pl.Expr | None:
    """Return where either side of ``&`` or ``|`` has no truth value, or None.

    Wherever this holds the per-policy combination is a null (11.1.27): none
    where neither side is null, and the null beside it winning where one is
    (11.1.26) -- never the value Polars' own ``&``/``|`` gives over a NaN
    comparison it has ordered.
    """
    unknowns = [_unknown_of(child, ctx) for child in (node.left, node.right)]
    if all(unknown is None for unknown in unknowns):
        return None
    either = pl.lit(value=False)
    for unknown in unknowns:
        if unknown is not None:
            either = either | unknown
    return either


def _may_be_unknown(node: OpNode, ctx: LoweringContext | None) -> bool:
    """Say whether a test of either shape can have no truth value (a NaN operand)."""
    if isinstance(node, BinOp) and node.op in _COMPARISON_OPS:
        left, right, _ = _typed_comparison_operands(node, ctx)
        return bool(_sides_that_hold_a_nan(node, left, right, ctx))
    if isinstance(node, BinOp) and node.op in {"and", "or"}:
        return _may_be_unknown(node.left, ctx) or _may_be_unknown(node.right, ctx)
    if isinstance(node, Call) and node.name == "not_":
        return _may_be_unknown(node.args[0], ctx)
    return False


def _answered_in_doubles(
    then: _Lowered, otherwise: _Lowered, ctx: LoweringContext | None
) -> pl.DataType | None:
    """Return the double type a conditional answers in, or None if it is not one.

    Where its condition has no truth value a conditional answering a number
    in doubles answers NaN, and one answering anything else -- text, a whole
    number, a date -- answers a null, its type holding no NaN.
    """
    if ctx is None:
        return pl.Float64()
    for branch in (then, otherwise):
        dtype = ctx.dtype_of_expr(branch.expr)
        if holds_a_nan(dtype):
            return dtype
    return None


def _comparison_op(op: str) -> _ComparisonOp:
    """Narrow a ``BinOp.op`` string already known to be a comparison."""
    if op not in _COMPARISON_OPS:  # pragma: no cover - callers pre-filter
        msg = f"{op!r} is not a comparison operator"
        raise ValueError(msg)
    return op  # type: ignore[return-value]


def _list_conditional_for(  # noqa: PLR0913 -- the comparison, its operands, two branches, the frame, its NaN reading
    node: BinOp,
    operands: tuple[_Lowered, _Lowered, _OperandTypes],
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    *,
    ctx: LoweringContext | None,
    unknown_is_nan: bool = False,
) -> pl.Expr:
    """Run a comparison through ``list_conditional``, list operand on the left.

    The kernel requires the list-typed operand on ``left``. User code
    routinely writes the commuted form (``12 == af.duration_mth_t``), so a
    scalar-left/list-right predicate swaps its operands and inverts the
    operator rather than being refused. A per-period Categorical or Enum
    column compared for equality is then handed over as its codes
    (:func:`on_codes_where_labelled`).

    The kernel reads both sides as doubles, so a pair of whole numbers,
    dates and times or durations a double does not hold every value of is
    handed over as their exact difference against nought
    (:func:`~gaspatchio.frame.lowering._polars.comparisons.per_period_operands`):
    ``2**53 + 1 > 2**53`` is true in every period, as it is per policy. That
    needs both types, so an operand the frame could not type is refused by
    name (:func:`_an_untyped_comparison`) rather than compared by its double.
    """
    left, right, (left_dtype, right_dtype) = operands
    if left_dtype is None or (right_dtype is None and kind_of(left_dtype) is not None):
        raise _an_untyped_comparison(node, left_dtype)
    operator = _PLUGIN_OPERATOR[node.op]
    left_expr, right_expr, right_node = left.expr, right.expr, node.right
    if left.shape != "list" and right.shape == "list":
        left_expr, right_expr, right_node = right_expr, left_expr, node.left
        left_dtype, right_dtype = right_dtype, left_dtype
        operator = _INVERSE_PLUGIN_OPERATOR[operator]
    # Both sides per period: the run on the right is the one whose null
    # outer list the kernel does not see as one.
    right_run = right_expr if left.shape == right.shape == "list" else None
    if left_dtype is not None and right_dtype is not None:
        typed = (left_dtype, right_dtype)

        def exactly(ours: pl.Expr, theirs: pl.Expr) -> tuple[pl.Expr, pl.Expr] | None:
            return per_period_operands(
                (ours, typed[0]),
                (theirs, typed[1]),
                right_per_period=isinstance(typed[1], pl.List),
            )

        if exactly(pl.field("_"), pl.field("_")) is not None:
            # The exact route reads each side four or five times; held once,
            # a nested comparison's plan grows with the lines written rather
            # than geometrically with their depth (audit D1-H1's class).
            def answer(ours: pl.Expr, theirs: pl.Expr) -> pl.Expr:
                operands = cast("tuple[pl.Expr, pl.Expr]", exactly(ours, theirs))
                selected = list_conditional(
                    *operands,
                    then_val,
                    otherwise_val,
                    operator,
                    unknown_is_nan=unknown_is_nan,
                )
                run = None if right_run is None else theirs
                return _null_where_the_run_is_null(selected, run)

            return read_once(left_expr, right_expr, answer=answer, as_written=True)
    left_expr, right_expr = on_codes_where_labelled(
        left_expr, right_expr, right_node, operator, ctx
    )
    selected = list_conditional(
        left_expr,
        right_expr,
        then_val,
        otherwise_val,
        operator,
        unknown_is_nan=unknown_is_nan,
    )
    return _null_where_the_run_is_null(selected, right_run)


def _null_where_the_run_is_null(selected: pl.Expr, run: pl.Expr | None) -> pl.Expr:
    """Return a per-period comparison null for a policy whose right-hand run is.

    The kernel reads a null outer list on its left as the policy's null,
    and one on its right as a null in each period: ``av < gmdb`` with a
    policy's ``gmdb`` absent answered ``[None, None]`` where ``gmdb > av``
    answered null, so a ``fill_null(0.0)`` and a total moved with the order
    the comparison was written in. A null outer list is a policy with no
    periods (11.1.25, 11.1.26), so either side answers null.
    """
    if run is None:
        return selected
    return pl.when(run.is_null()).then(None).otherwise(selected)


# --- A Categorical or Enum condition, on its codes ---------------------------

# The two comparisons a per-period Categorical or Enum column answers by its
# codes. Two labels are equal exactly where their codes are, in one column's
# own categories; their order is not their codes' order, so the orderings
# stay on the labels.
_CODE_COMPARISONS: frozenset[str] = frozenset({"eq", "ne"})

# The code a value is given that names none of the column's categories -- a
# label an Enum does not hold. No category has it, so it equals none of them:
# `eq` answers 0 and `ne` 1, as the labels do.
_NO_SUCH_CATEGORY = -1


def on_codes_where_labelled(
    left: pl.Expr,
    right: pl.Expr,
    right_node: OpNode,
    operator: str,
    ctx: LoweringContext | None,
) -> tuple[pl.Expr, pl.Expr]:
    """Return a per-period Categorical or Enum equality as its codes.

    ``af.plan == "A"`` over a per-period Categorical column handed the
    kernel the column itself, and Polars re-entered every label into the
    category map for each block of rows it passed across the plugin
    boundary: about 5 s over 100,000 policies x 360 months streaming,
    where the same comparison over numbers takes 0.13 s. The codes cross
    as plain integers, so ``eq`` and ``ne`` are handed over as codes, and
    the kernel compares numbers.

    The right side is cast to **the left column's own dtype** and then read
    as its codes, inside the expression, so the codes are the ones this
    run's categories give and are never written into the plan. The answer
    is the one the labels give, value for value:

    - a value the column's categories do not hold (an Enum's unknown label)
      takes a code no category has, so ``eq`` is 0 and ``ne`` 1;
    - a null on either side is a null answer, and a null right-hand row a
      null in each of the policy's periods, as for the labels -- the kernel
      answers a null operand that way; and a null or empty policy is what
      it was.

    Everything else is returned as it came: the orderings, a ``String``
    left side (already a direct comparison), and a right side that is not
    text -- which the kernel refuses by name, as before. The record is
    untouched: the op-tree still says ``eq(plan, "A")``, and the rendering
    a reader sees writes these operands back as the model wrote them
    (``rendering.labels_for_codes``).
    """
    # The right side is asked first: it is nearly always a value or a column,
    # which answer without a probe, and a numeric one ends the question.
    if ctx is None or operator not in _CODE_COMPARISONS or _a_number(right_node):
        return left, right
    right_dtype = (
        pl.String() if _is_text_literal(right_node) else _operand_dtype(right, ctx)
    )
    right_is_list = isinstance(right_dtype, pl.List)
    values = right_dtype.inner if isinstance(right_dtype, pl.List) else right_dtype
    if not _is_text(values):
        return left, right
    left_dtype = _operand_dtype(left, ctx)
    if not isinstance(left_dtype, pl.List) or not _is_categorical(left_dtype.inner):
        return left, right
    labels = cast("pl.DataType", left_dtype.inner)
    codes = left.to_physical()
    if _is_text_literal(right_node):
        return codes, _code_of(right, labels)
    # A null right-hand value stays null -- it is not a label the categories
    # lack -- and the kernel answers a null operand, value or whole row, with
    # a null in each of the policy's periods, as the labels do.
    if not right_is_list:
        return codes, _null_or_code_of(right, labels)
    return codes, right.list.eval(_null_or_code_of(pl.element(), labels))


def _operand_dtype(expr: pl.Expr, ctx: LoweringContext) -> pl.DataType | None:
    """Return an operand's dtype: a column's from the frame's schema, else probed."""
    if expr.meta.is_column():
        return _column_dtype(expr.meta.output_name(), ctx)
    return ctx.dtype_of_expr(expr)


def _code_of(value: pl.Expr, labels: pl.DataType) -> pl.Expr:
    """Return ``value`` as its code in ``labels``, or the code no category has."""
    return value.cast(labels, strict=False).to_physical().fill_null(_NO_SUCH_CATEGORY)


def _null_or_code_of(value: pl.Expr, labels: pl.DataType) -> pl.Expr:
    """Return ``value`` as its code in ``labels``, keeping a null a null."""
    return pl.when(value.is_null()).then(None).otherwise(_code_of(value, labels))


def _is_categorical(dtype: object) -> bool:
    """Report whether a dtype holds labels as codes: Categorical or Enum."""
    return isinstance(dtype, (pl.Categorical, pl.Enum))


def _is_text(dtype: object) -> bool:
    """Report whether a dtype holds text: String, Categorical or Enum."""
    return isinstance(dtype, pl.String) or _is_categorical(dtype)


def _a_number(node: OpNode) -> bool:
    """Report whether ``node`` is one value the model wrote that is not text."""
    return isinstance(node, Lit) and not isinstance(node.value, (str, tuple))


def _is_text_literal(node: OpNode) -> bool:
    """Report whether ``node`` is one text value the model wrote, ``"A"``."""
    return isinstance(node, Lit) and isinstance(node.value, str)


def _lower_logical(
    op: _LogicalOp, node: BinOp, ctx: LoweringContext | None
) -> _Lowered:
    """Combine two predicates with ``&`` or ``|``.

    With every operand scalar this is Polars' own boolean operator, which
    matters because the result may go on to feed ``pl.when()`` -- and that
    rejects a Float64 mask. With any operand list-shaped, Polars has no
    element-wise boolean operator that reaches inside a ``list``, so the
    combination is done arithmetically over Float64 0/1 masks:
    ``a * b`` for AND, ``1 - (1-a)(1-b)`` for OR.

    An operand that is a direct reference to a stored ``f64`` column is
    checked exactly as a ``when`` condition checks it (§11.1.27): the flag the
    model stored is a flag, and a 2.0 in it refuses rather than combining.
    """
    left = _lower_stored_predicate(node.left, ctx)
    right = _lower_stored_predicate(node.right, ctx)
    shape = _combine(left.shape, right.shape)
    if shape != "list":
        combined = left.expr & right.expr if op == "and" else left.expr | right.expr
        no_answer = _a_side_unknown(node, ctx)
        if no_answer is not None:
            # A test with no truth value makes the combination have none,
            # as the per-period arithmetic over a NaN indicator does, and a
            # null beside it wins (11.1.26-27): a Boolean holds no NaN, so
            # both are a null here. Polars' own operator would answer the
            # NaN comparison it ordered beside the null (true OR null).
            combined = unknown_guard(no_answer, pl.lit(None), combined)
        return _Lowered(combined, shape)
    left_mask = _lower_mask(node.left, ctx, check_stored=True)
    right_mask = _lower_mask(node.right, ctx, check_stored=True)
    if op == "and":
        return _Lowered(left_mask * right_mask, "list")
    one = pl.lit(1.0)
    return _Lowered(one - ((one - left_mask) * (one - right_mask)), "list")


def _lower_mask(
    node: OpNode, ctx: LoweringContext | None, *, check_stored: bool = False
) -> pl.Expr:
    """Lower one operand of a list-shaped ``&``/``|`` to a Float64 0/1 mask.

    A comparison becomes its indicator; every other operand is cast while
    preserving its shape. A Boolean list may come from a column, an absence
    predicate, or an explicit
    engine expression; each needs the same numeric mask before arithmetic.
    With ``check_stored``, a direct stored ``f64`` column is checked first
    under the exact 0/1 contract (``_lower_stored_predicate``).
    """
    if isinstance(node, BinOp) and node.op in _COMPARISON_OPS:
        return _lower_indicator(node, ctx).expr
    lowered = _lower_stored_predicate(node, ctx) if check_stored else _lower(node, ctx)
    dtype = pl.List(pl.Float64) if lowered.shape == "list" else pl.Float64
    return lowered.expr.cast(dtype)


# --- WhenThen ---------------------------------------------------------------


def _lower_stored_predicate(node: OpNode, ctx: LoweringContext | None) -> _Lowered:
    """Check direct stored f64 predicates; other predicate forms keep their rules."""
    lowered = _lower(node, ctx)
    if not isinstance(node, Col) or ctx is None:
        return lowered
    dtype = ctx.dtype_of_expr(lowered.expr)
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    if inner is None or not inner.is_float():
        return lowered
    per_period = lowered.shape == "list"
    # The name travels with the check because this is the only place that
    # still knows it: by the time the refusal reaches a reader it is a string
    # inside a Polars cast failure, and "some column was not an indicator" is
    # not an answer anybody can act on.
    checked = checked_numeric_predicate(
        lowered.expr, per_period=per_period, column=node.name
    )
    return _Lowered(checked if per_period else checked == 1.0, lowered.shape)


def _branches_read_as_i64(
    node: WhenThen, then: _Lowered, otherwise: _Lowered, ctx: LoweringContext | None
) -> tuple[_Lowered, _Lowered]:
    """Return a branch wider than ``i64`` beside a narrower one read as ``Int64``.

    A selection answers in the type its branches share, so a ``UInt64``
    branch holding a value no ``i64`` carries, beside an ``i64`` one, is
    refused by name, as arithmetic on it is (section 10):
    ``when(af.smoker).then(af.polno).otherwise(af.n)`` failed in Polars'
    words, ``conversion from `u64` to `i64` failed``. Two branches of one
    wide type keep it and are selected exactly, piece by piece (11.1.28).
    Only a column or a call is asked; a literal past ``i64`` is refused
    where it is written already.
    """
    if ctx is None:
        return then, otherwise

    def typed(branch: OpNode, lowered: _Lowered) -> pl.DataType | str | None:
        if isinstance(branch, (Lit, BinOp, WhenThen)):
            return None
        return _operand_type(branch, lowered, ctx)

    dtypes = (typed(node.then, then), typed(node.otherwise, otherwise))
    wide = [
        isinstance(dtype, pl.DataType) and wider_than_i64_at(dtype) is not None
        for dtype in dtypes
    ]
    if wide[0] == wide[1]:
        return then, otherwise
    return (
        _a_wide_integer_read_where_it_fits(node.then, then, dtypes[0], WIDE_CARRY_RULE),
        _a_wide_integer_read_where_it_fits(
            node.otherwise, otherwise, dtypes[1], WIDE_CARRY_RULE
        ),
    )


def _lower_when_then(node: WhenThen, ctx: LoweringContext | None) -> _Lowered:
    """Lower one ``when``/``then``/``otherwise`` case.

    A chain of ``.when()`` calls arrives here as nested ``WhenThen`` nodes
    -- the innermost ``otherwise`` is the chain's final default -- so the
    recursion below reproduces the reverse fold the chain builder used to
    do by hand, and each level sees the shape the level below resolved to.

    Four routes, in the order they are tried:

    1. a list-shaped *comparison* predicate -> ``list_conditional`` on the
       comparison's own operands;
    2. any other list-shaped predicate (a mask, a ``list[bool]`` column)
       -> ``list_conditional`` against 1.0;
    3. a scalar predicate over a list-shaped branch -> the predicate is
       repeated to the branch's per-row lengths first, because
       ``pl.when()`` cannot unify a scalar branch with a list one;
    4. everything scalar -> native ``pl.when().then().otherwise()``.
    """
    then, otherwise = _branches_read_as_i64(
        node,
        _lower_value(node.then, ctx),
        _lower_value(node.otherwise, ctx),
        ctx,
    )
    read = _refuse_branches_of_two_kinds(node, then.expr, otherwise.expr, ctx)
    then, otherwise = _branches_in_one_type(node, (then, otherwise), read, ctx)

    if isinstance(node.cond, BinOp) and node.cond.op in _COMPARISON_OPS:
        left, right, dtypes = _typed_comparison_operands(node.cond, ctx)
        if _combine(left.shape, right.shape) == "list":
            return _selected_by_a_comparison(
                node, (left, right, dtypes), (then, otherwise), ctx
            )
        cond = _Lowered(
            _compared_per_policy(_comparison_op(node.cond.op), left, right, dtypes),
            _combine(left.shape, right.shape),
        )
    else:
        cond = _lower_stored_predicate(node.cond, ctx)
        if cond.shape == "list":
            return _selected_by_a_mask(node, cond, (then, otherwise), ctx)

    # 11.1.28: where the condition has no truth value -- a NaN reached a
    # comparison in it -- the answer is NaN, or a null where it holds none.
    unknown = _unknown_of(node.cond, ctx)
    doubles = None if unknown is None else _answered_in_doubles(then, otherwise, ctx)
    if then.shape == "list" or otherwise.shape == "list":
        length_ref = (
            otherwise.expr.list.len()
            if otherwise.shape == "list"
            else then.expr.list.len()
        )
        held = cond.expr
        if unknown is not None and doubles is None:
            held = unknown_guard(unknown, pl.lit(None), held)
        held = held.cast(pl.Float64)
        # 11.1.28: in a double answer the policy's unknown selects neither
        # branch in any of its periods, a null in a branch's run included.
        neither = (
            unknown is not None
            and doubles is not None
            and not _no_branch_holds_a_null(node)
        )
        if neither and unknown is not None:
            held = unknown_guard(unknown, nan_literal(pl.Float64()), held)
        broadcast = held.repeat_by(length_ref)
        selected = _list_conditional_mask(
            broadcast, node, then.expr, otherwise.expr, ctx, unknown_is_nan=neither
        )
        if unknown is not None and doubles is not None and not neither:
            selected = selected + (
                pl.when(unknown)
                .then(nan_literal(doubles))
                .otherwise(pl.lit(-0.0))
                .alias(POISON_MARK)
            )
        return _Lowered(
            _null_where_a_branch_run_is_null(selected, then, otherwise), "list"
        )

    selected = pl.when(cond.expr).then(then.expr).otherwise(otherwise.expr)
    if unknown is not None:
        none = nan_literal(doubles) if doubles is not None else pl.lit(None)
        selected = unknown_guard(unknown, none, selected)
    return _Lowered(selected, _combine(then.shape, otherwise.shape))


def _selected_by_a_comparison(
    node: WhenThen,
    operands: tuple[_Lowered, _Lowered, _OperandTypes],
    branches: tuple[_Lowered, _Lowered],
    ctx: LoweringContext | None,
) -> _Lowered:
    """Select per period on a comparison, through the kernel on its own operands.

    Where an operand is NaN the comparison has no truth value: an answer in
    doubles is made NaN there afterwards, and any other answer is selected
    with the NaN read as a null, which the kernel answers with a null.
    """
    left, right, dtypes = operands
    then, otherwise = branches
    comparison = cast("BinOp", node.cond)
    sides = _sides_that_hold_a_nan(comparison, left, right, ctx)
    doubles = _answered_in_doubles(then, otherwise, ctx) if sides else None
    if sides and doubles is None:
        left, right = (
            _Lowered(nan_as_null(side.expr, side.shape), side.shape)
            if side in sides
            else side
            for side in (left, right)
        )

    # 11.1.28: in a double answer a period whose comparison has no truth
    # value selects neither branch, a null in either included -- answered
    # by the kernel itself. Two literal branches hold no null, and keep the
    # NaN term added afterwards.
    neither = doubles is not None and not _no_branch_holds_a_null(node)

    def compared(when_true: pl.Expr, when_false: pl.Expr) -> pl.Expr:
        return _list_conditional_for(
            comparison,
            (left, right, dtypes),
            when_true,
            when_false,
            ctx=ctx,
            unknown_is_nan=neither,
        )

    selected = _selected_per_period(
        compared, node, then.expr, otherwise.expr, ctx, anchored=False
    )
    if doubles is not None and not neither:
        selected = _poisoned(selected, sides)
    return _Lowered(_null_where_a_branch_run_is_null(selected, then, otherwise), "list")


def _selected_by_a_mask(
    node: WhenThen,
    cond: _Lowered,
    branches: tuple[_Lowered, _Lowered],
    ctx: LoweringContext | None,
) -> _Lowered:
    """Select per period on a 0/1 run, NaN where a test combined into it had none."""
    then, otherwise = branches
    mask = cond.expr
    unknown = _may_be_unknown(node.cond, ctx)
    doubles = _answered_in_doubles(then, otherwise, ctx) if unknown else None
    if unknown and doubles is None:
        mask = nan_as_null(mask, "list")
    # A NaN in the mask selects neither branch in a double answer (11.1.28).
    neither = doubles is not None and not _no_branch_holds_a_null(node)
    selected = _list_conditional_mask(
        mask, node, then.expr, otherwise.expr, ctx, unknown_is_nan=neither
    )
    if doubles is not None and not neither:
        selected = selected + nan_poison(cond.expr, "list")
    return _Lowered(_null_where_a_branch_run_is_null(selected, then, otherwise), "list")


def _no_branch_holds_a_null(node: WhenThen) -> bool:
    """Say whether both branches are literals with a value, so neither holds a null.

    Then the NaN term added to a double selection makes it NaN wherever the
    condition had no truth value, as it always did; a branch that can hold a
    null needs the kernel to answer the NaN, because a null plus a NaN is a
    null.
    """
    return all(
        isinstance(branch, Lit) and branch.value is not None
        for branch in (node.then, node.otherwise)
    )


def _null_where_a_branch_run_is_null(
    selected: pl.Expr, then: _Lowered, otherwise: _Lowered
) -> pl.Expr:
    """Return a per-period selection null for a policy either of whose branch runs is.

    A null outer list is a policy with no periods (11.1.18), and a line that
    reads one answers null for the policy wherever the run stands (11.1.28):
    in the condition, as a comparison or arithmetic operand already did, and
    in either branch, selected or not. The kernel read a null run in a
    branch as a null in each period, so ``when(af.in_force).then(af.gmdb)
    .otherwise(af.av)`` with one policy's ``gmdb`` absent answered the
    ``av`` values in the periods it did not select and nulls in those it
    did, and a null run on one side of the chain decided the answer by the
    route the line took. Each branch that holds one value per period is
    guarded as a comparison's right-hand run is, so the walk-through a record
    carries takes the guard off again; a chain's lower levels are guarded
    where they are lowered, so their null reaches the level above as a run.
    """
    for branch in (otherwise, then):
        if branch.shape == "list":
            selected = _null_where_the_run_is_null(selected, branch.expr)
    return selected


def _branch_dtype(
    node: OpNode, expr: pl.Expr | None, ctx: LoweringContext | None
) -> pl.DataType | None:
    """Return the type one branch is written in, reading a chain by its head.

    A branch that is itself a conditional -- the rest of a ``when`` chain --
    was checked at its own level, so every branch in it is one kind, and the
    first that states a type is the chain's. Reading that one branch rather
    than resolving the whole chain below is what keeps a long chain linear:
    resolving it at every level made a 200-case chain thirty times slower to
    write. A null branch states nothing and the next is read.
    """
    if isinstance(node, WhenThen):
        head = _branch_dtype(node.then, None, ctx)
        if head is not None and head != pl.Null:
            return head
        return _branch_dtype(node.otherwise, None, ctx)
    if isinstance(node, Lit) or ctx is None:
        return operand_dtype(node, pl.lit(None), ctx)
    if expr is None:
        expr = _lower_value(node, ctx).expr
    return ctx.dtype_of_expr(expr)


def _refuse_branches_of_two_kinds(
    node: WhenThen,
    then_expr: pl.Expr,
    otherwise_expr: pl.Expr,
    ctx: LoweringContext | None,
) -> tuple[pl.DataType | None, pl.DataType | None]:
    """Refuse a conditional whose two branches are different kinds of value.

    ``when(...).then(af.rate).otherwise("n/a")`` ran and answered text for
    every policy, the rates included -- Polars' conditional finds a type
    both branches can be written in, and every number can be written as
    text. Section 11.1.28 states the matched pairs, and a producer that
    carries one branch into the other's type "is recording a conversion the
    model never wrote". A whole number opposite a decimal is the declared
    widening and stays one; a flag is a number to this framework (a
    comparison assigned as a value is stored as a 0/1 indicator), as it is
    to the second engine. A chain is checked a level at a time: each
    level's otherwise is the chain below, already one kind.

    Returns the two branch types it read, None for one it did not, so the
    step that writes the pair in one type asks nothing twice.
    """
    then_dtype = _branch_dtype(node.then, then_expr, ctx)
    if then_dtype is None or kind_of(then_dtype) is None:
        return then_dtype, None
    otherwise_dtype = _branch_dtype(node.otherwise, otherwise_expr, ctx)
    if otherwise_dtype is None:
        return then_dtype, None
    if not apart(then_dtype, otherwise_dtype):
        _refuse_one_kind_in_two_types(
            node, (then_expr, then_dtype), (otherwise_expr, otherwise_dtype), ctx
        )
        return then_dtype, otherwise_dtype
    text = "then" if kind_of(then_dtype) == "text" else "otherwise"
    other = "otherwise" if text == "then" else "then"
    move = (
        "Write both branches as one kind: if a label is meant, make the "
        f"{other} branch text too with .to_text(); if a value is meant, write "
        f"the {text} branch as one."
        if "text" in {kind_of(then_dtype), kind_of(otherwise_dtype)}
        else "Write both branches as one kind of value."
    )
    raise refusal(
        line="when/then/otherwise",
        role="otherwise branch",
        operand=node.otherwise,
        fill=otherwise_dtype,
        beside="its then branch",
        receiver=then_dtype,
        move=move,
    )


def _branches_in_one_type(
    node: WhenThen,
    branches: tuple[_Lowered, _Lowered],
    read: tuple[pl.DataType | None, pl.DataType | None],
    ctx: LoweringContext | None,
) -> tuple[_Lowered, _Lowered]:
    """Write a conditional's two branches in the one type the pair answers in.

    Two pairs answered a type that depended on the route the line took.

    **A flag beside a whole number answers a double.** ``when(af.x > 2)
    .then(True).otherwise(af.n)`` answered ``Int64`` per policy, where
    Polars reads the flag as 0 or 1, and ``list[f64]`` per period, where the
    selection kernel works in doubles; the second engine split the same
    way. Section 11.1.25 reads a flag beside a number as its 0.0/1.0
    indicator under every operator, so the flag is read as that double here
    too, before any route is chosen, and the pair answers ``f64`` on both.
    The whole number is read as arithmetic reads one: a column stored wider
    than ``i64`` as the ``Int64`` its values fit, refused by name where one
    does not, rather than rounded into the double.

    **A flag beside a fixed-point decimal answers a double** for the same
    reason: per period the selection kernel already answered ``f64``, and per
    policy Polars found no type for a flag and a ``Decimal`` and stopped the
    run in its own words. The flag is its 0.0/1.0 double, and Polars reads
    the pair as a double, as it reads a double beside a ``Decimal``.

    **Two time units answer in the finer.** A date and time in microseconds
    opposite one in milliseconds, or a Python ``datetime`` literal (held in
    microseconds) opposite a nanosecond column, answered Polars' coarser
    unit on both routes, and the finer branch lost its last digits without
    a word. Both branches are read in the finer unit, into which every
    value of the coarser converts exactly, and a value the finer unit
    cannot hold refuses the run by name rather than turning into a null.
    Two durations likewise.

    **Two fixed-point decimals answer in the decimal type Polars gives the
    pair**, and so do a decimal and a whole number: per policy ``pl.when``
    carried a branch into that type and failed in Polars' own words where a
    value did not fit it. Each branch is read into that type here, before
    any route is chosen, and a value it cannot hold refuses the run by name
    rather than turning into a null.

    ``read`` is the pair of types the kind check read, so an ordinary pair
    asks nothing more. A pair of time types is asked again as lowered,
    because a chain is read by its head and its head need not be in the
    chain's finest unit.
    """
    then, otherwise = branches
    then_dtype, otherwise_dtype = read
    if ctx is None or then_dtype is None or otherwise_dtype is None:
        return then, otherwise
    if kind_of(then_dtype) in {"datetime", "duration"}:
        return _in_the_finer_unit(node, then, otherwise, ctx)
    if _holds_fixed_point(then_dtype) or _holds_fixed_point(otherwise_dtype):
        return _in_one_decimal_type(node, branches, ctx)
    return _a_flag_beside_a_number(node, branches, (then_dtype, otherwise_dtype))


def _in_one_decimal_type(
    node: WhenThen, branches: tuple[_Lowered, _Lowered], ctx: LoweringContext
) -> tuple[_Lowered, _Lowered]:
    """Read a decimal branch and a decimal or whole-number one in one decimal type.

    The type is the one ``pl.when`` gives the pair, read off the branches as
    lowered, since a chain is read by its head. A decimal beside a double
    (a double, as Polars answers) and a flag beside a decimal (its 0.0/1.0
    double, :func:`_a_flag_beside_a_number`) are typed as they were.
    """
    then, otherwise = branches
    then_dtype = ctx.dtype_of_expr(then.expr)
    otherwise_dtype = ctx.dtype_of_expr(otherwise.expr)
    if then_dtype is None or otherwise_dtype is None:
        return then, otherwise
    elements = (_element_of(then_dtype), _element_of(otherwise_dtype))
    if not all(_whole_or_fixed_point(element) for element in elements):
        return _a_flag_beside_a_number(node, branches, (then_dtype, otherwise_dtype))
    shared = _polars_shared_type(*elements)
    if not isinstance(shared, pl.Decimal):
        return then, otherwise
    return (
        _read_in_decimal(node.then, then, then_dtype, shared),
        _read_in_decimal(node.otherwise, otherwise, otherwise_dtype, shared),
    )


def _whole_or_fixed_point(element: pl.DataType | None) -> bool:
    """Say whether a branch's element is a whole number or a fixed-point decimal."""
    return element is not None and (
        element.is_integer() or isinstance(element, pl.Decimal)
    )


def _read_in_decimal(
    node: OpNode, branch: _Lowered, dtype: pl.DataType | None, shared: pl.Decimal
) -> _Lowered:
    """Return one branch in the pair's decimal type, refusing a value it cannot hold."""
    if _element_of(dtype) == shared:
        return branch
    listed = isinstance(dtype, pl.List)
    read = read_in_the_shared_decimal(
        branch.expr,
        pl.List(shared) if listed else shared,
        element=shared,
        depth=int(listed),
        column=node.name if isinstance(node, Col) else None,
    )
    return _Lowered(read, branch.shape)


def _a_flag_beside_a_number(
    node: WhenThen,
    branches: tuple[_Lowered, _Lowered],
    read: tuple[pl.DataType, pl.DataType],
) -> tuple[_Lowered, _Lowered]:
    """Read a flag branch as its 0.0/1.0 double where the other is a number.

    Beside a whole number the whole number is read as arithmetic reads one
    (:func:`_branches_in_one_type`); beside a double or a fixed-point decimal
    the other branch is left to Polars, which reads a double beside a
    ``Decimal`` as a double. Any other pair is returned as it came.
    """
    then, otherwise = branches
    then_dtype, otherwise_dtype = read
    if is_flag(then_dtype) and _holds_whole_numbers(otherwise_dtype):
        return _a_flag_as_its_indicator(then), _a_wide_integer_read_where_it_fits(
            node.otherwise, otherwise, otherwise_dtype, WIDE_CARRY_RULE
        )
    if is_flag(otherwise_dtype) and _holds_whole_numbers(then_dtype):
        return _a_wide_integer_read_where_it_fits(
            node.then, then, then_dtype, WIDE_CARRY_RULE
        ), _a_flag_as_its_indicator(otherwise)
    if is_flag(then_dtype) and _holds_a_fraction(otherwise_dtype):
        return _a_flag_as_its_indicator(then), otherwise
    if is_flag(otherwise_dtype) and _holds_a_fraction(then_dtype):
        return then, _a_flag_as_its_indicator(otherwise)
    return then, otherwise


def _holds_a_fraction(dtype: pl.DataType) -> bool:
    """Say whether a type, or its per-period element, is a double or a decimal.

    A flag beside one reads as its 0.0/1.0 double. Beside a double that is
    what the run answered already, but the frame's schema did not say so:
    Polars types ``when(c).then(False).otherwise(3.25)`` as ``Unknown`` before
    it runs, so the frame recorded no type for a column it ran as ``Float64``
    and the export called it ``type Unknown``.
    """
    element = _element_of(dtype)
    return element is not None and (
        element.is_float() or isinstance(element, pl.Decimal)
    )


def _holds_whole_numbers(dtype: pl.DataType) -> bool:
    """Say whether a type, or its per-period element, is a whole number."""
    element = _element_of(dtype)
    return element is not None and element.is_integer()


def _holds_fixed_point(dtype: pl.DataType) -> bool:
    """Say whether a type, or its per-period element, is a fixed-point decimal."""
    return isinstance(_element_of(dtype), pl.Decimal)


def _a_flag_as_its_indicator(branch: _Lowered) -> _Lowered:
    """Return a flag branch as its 0.0/1.0 double, per period or per policy."""
    read = pl.List(pl.Float64) if branch.shape == "list" else pl.Float64
    return _Lowered(branch.expr.cast(read), branch.shape)


# The time units a date and time or a duration is counted in, finest first.
_UNITS_FINEST_FIRST: Final[tuple[_TimeUnit, ...]] = ("ns", "us", "ms")


def _in_the_finer_unit(
    node: WhenThen, then: _Lowered, otherwise: _Lowered, ctx: LoweringContext
) -> tuple[_Lowered, _Lowered]:
    """Read two time branches in the finer of their two units, losing nothing."""
    then_dtype = ctx.dtype_of_expr(then.expr)
    otherwise_dtype = ctx.dtype_of_expr(otherwise.expr)
    units = {_unit_of(then_dtype), _unit_of(otherwise_dtype)}
    if None in units or len(units) == 1:
        return then, otherwise
    finer: _TimeUnit = next(unit for unit in _UNITS_FINEST_FIRST if unit in units)
    return (
        _read_in_unit(node.then, then, then_dtype, finer),
        _read_in_unit(node.otherwise, otherwise, otherwise_dtype, finer),
    )


def _unit_of(dtype: pl.DataType | None) -> _TimeUnit | None:
    """Return the unit a date and time or a duration is counted in, or None."""
    element = _element_of(dtype)
    if isinstance(element, (pl.Datetime, pl.Duration)):
        return element.time_unit
    return None


def _read_in_unit(
    node: OpNode, branch: _Lowered, dtype: pl.DataType | None, unit: _TimeUnit
) -> _Lowered:
    """Return one time branch counted in ``unit``, refusing a value it cannot hold."""
    element = _element_of(dtype)
    if not isinstance(element, (pl.Datetime, pl.Duration)) or element.time_unit == unit:
        return branch
    finer = (
        pl.Datetime(unit, element.time_zone)
        if isinstance(element, pl.Datetime)
        else pl.Duration(unit)
    )
    listed = isinstance(dtype, pl.List)
    read = read_in_the_finer_unit(
        branch.expr,
        pl.List(finer) if listed else finer,
        element=finer,
        depth=int(listed),
        column=node.name if isinstance(node, Col) else None,
    )
    return _Lowered(read, branch.shape)


# What a model writes to put two branches of one kind in one type, by kind.
_ONE_TYPE_MOVE: Final[dict[str, str]] = {
    "datetime": (
        "Write both branches in one time zone where the data is loaded: give "
        "a zone-naive column its zone, or convert a zoned one into the "
        "other's."
    ),
    "text": (
        "Write both branches with one set of categories where the data is "
        "loaded, or read both as text with .to_text()."
    ),
}


def _refuse_one_kind_in_two_types(
    node: WhenThen,
    then: tuple[pl.Expr, pl.DataType],
    otherwise: tuple[pl.Expr, pl.DataType],
    ctx: LoweringContext | None,
) -> None:
    """Refuse two branches of one kind whose two types have nothing in common.

    A zone-naive date and time opposite a zoned one, or a Categorical
    opposite an Enum, are one kind of value in two types with no type both
    are written in: Polars refused the pair only when the frame ran, in its
    own words, on the per-policy route, and the per-period route answered
    their counts and labels in a type neither branch was. Section 11.1.28's
    pair is one type, so the line is refused where it is written. Asked
    only where the two branches' types differ, so the ordinary pair costs
    nothing.
    """
    kind = kind_of(then[1])
    if kind in {None, "number"} or _element_of(then[1]) == _element_of(otherwise[1]):
        return
    if ctx is not None and not isinstance(node.then, WhenThen):
        then = (then[0], ctx.dtype_of_expr(then[0]) or then[1])
    if ctx is not None and not isinstance(node.otherwise, WhenThen):
        otherwise = (otherwise[0], ctx.dtype_of_expr(otherwise[0]) or otherwise[1])
    if _polars_shared_type(_element_of(then[1]), _element_of(otherwise[1])) is not None:
        return
    move = _ONE_TYPE_MOVE.get(
        cast("str", kind), "Write both branches in one type where the data is loaded."
    )
    msg = (
        f"when/then/otherwise: its otherwise branch -- {shown(node.otherwise)} -- "
        f"holds {describe(otherwise[1])} as {_element_of(otherwise[1])}, and its "
        f"then branch holds {describe(then[1])} as {_element_of(then[1])}. The "
        "two types have nothing in common: Polars would refuse the pair only "
        "when the frame runs, and carrying one into the other's would be a "
        "conversion the formula never wrote, so the line is refused. "
        f"{move}"
    )
    raise TypeError(msg)


def _element_of(dtype: pl.DataType | None) -> pl.DataType | None:
    """Return a per-period type's element type, or the type itself."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    return cast("pl.DataType | None", inner)


def _list_conditional_mask(  # noqa: PLR0913 -- the mask, its node, two branches, the frame, its NaN reading
    mask: pl.Expr,
    node: WhenThen,
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    ctx: LoweringContext | None,
    *,
    unknown_is_nan: bool = False,
) -> pl.Expr:
    """Select between two branches on a list-shaped 0/1 (or boolean) mask.

    With ``unknown_is_nan`` a NaN in the mask -- a test combined into it had
    no truth value -- answers NaN in that period, whichever branch holds a
    null there (11.1.28); only for an answer that is a double.
    """

    def masked(when_true: pl.Expr, when_false: pl.Expr) -> pl.Expr:
        return list_conditional(
            mask,
            pl.lit(1.0),
            when_true,
            when_false,
            "eq",
            unknown_is_nan=unknown_is_nan,
        )

    return _selected_per_period(
        masked, node, then_val, otherwise_val, ctx, anchored=True
    )


def _selected_per_period(  # noqa: PLR0913 - the selection, its node, its two branches, the frame, and whether to anchor
    select: Callable[[pl.Expr, pl.Expr], pl.Expr],
    node: WhenThen,
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    ctx: LoweringContext | None,
    *,
    anchored: bool,
) -> pl.Expr:
    """Return a per-period conditional in the type its two branches share.

    ``list_conditional`` selects in Float64 whatever it is handed, so two
    integer branches -- ``when(af.duration > 24).then(24).otherwise(
    af.duration)`` -- came back as a run of doubles. That is a conversion
    the model never wrote, and it put the frame at odds with its own
    record: section 11.1.28 types a conditional as the branches' shared
    type, so the exported tree typed ``list[i64]`` under a node the frame
    declared ``list[f64]``, the per-policy form of the same line kept its
    integers, and the second engine kept them too. So the answer is the
    type ``pl.when`` gives the same pair on the per-policy route, for every
    pair of one kind: two integers, two flags, two dates, two dates and
    times (in their unit and zone), two durations, two times of day, two
    decimals, and two labels (a Categorical or Enum pair stays one, where
    the kernel hands back text). Any other pair keeps the kernel's answer:
    an integer opposite a double is a double by the same clause, and a
    comparison written as a branch is the Float64 indicator the frame
    stores for any comparison assigned as a value.

    **A null branch carries no type, so the answer is the other branch's.**
    ``when(af.month > 0).then(None).otherwise(af.k)`` over a ``list[i64]``
    run answered ``list[f64]``, as the per-policy form of the line never
    did. The null is written in the other branch's type before the kernel
    sees it. Two null branches carry no type at all, so the answer is a run
    of nulls with none, as the per-policy form's is one null with none --
    which section 10 refuses at export rather than guessing a type for.

    **A selection keeps every bit of the value it selects.** Typing the
    answer does not undo the kernel's doubles: 2**53 + 1 selected as 2**53,
    a nanosecond date and time lost its last digits, and a 128-bit whole
    number past 2**85 lost its low ones. Every value is therefore selected
    as the whole number it is held as -- a date as its day count, a date
    and time or duration as its count of units, a decimal as its unscaled
    digits -- cut into 32-bit pieces, each of which a double holds exactly,
    and joined again. A pair whose every value is a literal a double holds
    -- ``.then(1).otherwise(0)``, a null -- and a type no value of which
    is past ``2**53`` are selected once, as before.
    """
    if ctx is None:
        return select(then_val, otherwise_val)
    then_dtype = ctx.dtype_of_expr(then_val)
    otherwise_dtype = ctx.dtype_of_expr(otherwise_val)
    if _states_no_type(then_dtype) and _states_no_type(otherwise_dtype):
        return select(then_val, otherwise_val).list.eval(pl.element().cast(pl.Null))
    exact = _states_no_type(then_dtype) or _a_double_holds_every_value(node.then)
    exact = exact and (
        _states_no_type(otherwise_dtype) or _a_double_holds_every_value(node.otherwise)
    )
    then_val, then_dtype = _typed_by_the_other(then_val, then_dtype, otherwise_dtype)
    otherwise_val, otherwise_dtype = _typed_by_the_other(
        otherwise_val, otherwise_dtype, then_dtype
    )
    shared = _shared_branch_type(then_dtype, otherwise_dtype)
    if shared is not None:
        return _selected_in(
            shared,
            select,
            (then_val, then_dtype),
            (otherwise_val, otherwise_dtype),
            exact=exact,
        )
    result = select(then_val, otherwise_val)
    if not anchored:
        return result
    dtype = ctx.dtype_of_expr(result)
    if isinstance(dtype, pl.List):
        # The plugin can return List(Null) for zero rows. Anchor its declared
        # branch dtype without a whole-column cast, which is optimized away.
        return result.list.eval(pl.element().cast(dtype.inner))
    return result


def _selected_in(
    shared: pl.DataType,
    select: Callable[[pl.Expr, pl.Expr], pl.Expr],
    then: tuple[pl.Expr, pl.DataType | None],
    otherwise: tuple[pl.Expr, pl.DataType | None],
    *,
    exact: bool,
) -> pl.Expr:
    """Select two branches of one kind, answering in the type they share.

    Text, flags and the two narrow kinds (a day count, a time of day's
    nanoseconds) go through the kernel once. Everything else is selected
    as the whole number it is held as, piece by piece, and read back.
    """
    if kind_of(shared) == "text" or shared == pl.Boolean:
        result = select(then[0], otherwise[0])
        if shared == pl.String:
            return result
        return result.list.eval(pl.element().cast(shared))
    held = _held_as(shared)
    then_held = _as_held(then[0], then[1], shared)
    otherwise_held = _as_held(otherwise[0], otherwise[1], shared)
    pieces = 1 if exact and shared.is_integer() else _pieces(shared, held)
    shapes = (isinstance(then[1], pl.List), isinstance(otherwise[1], pl.List))
    run = _selected_by_pieces(
        select, then_held, otherwise_held, held=held, pieces=pieces, shapes=shapes
    )
    return _read_back(run, shared)


def _states_no_type(dtype: pl.DataType | None) -> bool:
    """Say whether a branch is a null standing alone, with no type of its own."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    return inner == pl.Null


def _typed_by_the_other(
    branch: pl.Expr, dtype: pl.DataType | None, other: pl.DataType | None
) -> tuple[pl.Expr, pl.DataType | None]:
    """Write a null branch in the other branch's type, keeping its own shape."""
    if not _states_no_type(dtype) or other is None or _states_no_type(other):
        return branch, dtype
    element = other.inner if isinstance(other, pl.List) else other
    if element is None:
        return branch, dtype
    typed = pl.List(element) if isinstance(dtype, pl.List) else element
    return branch.cast(typed), cast("pl.DataType", typed)


# The largest whole number every smaller one of which a double holds exactly.
_DOUBLE_EXACT: Final = 2**53

# The whole-number types every value of which a double holds exactly.
_NARROW_INTEGERS: Final = (pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32)

# One more than the greatest piece but the first: a value is the sum of its
# pieces, the k-th scaled by _HALF ** k.
_HALF: Final = 2**32


def _a_double_holds_every_value(node: OpNode) -> bool:
    """Say whether a branch is written as literals a double holds exactly."""
    if isinstance(node, WhenThen):
        return _a_double_holds_every_value(node.then) and _a_double_holds_every_value(
            node.otherwise
        )
    if not isinstance(node, Lit) or isinstance(node.value, tuple):
        return False
    value = node.value
    return (
        not isinstance(value, int)
        or isinstance(value, bool)
        or abs(value) <= _DOUBLE_EXACT
    )


def _held_as(shared: pl.DataType) -> pl.DataType:
    """Return the whole-number type a value of ``shared`` is held as."""
    if isinstance(shared, pl.Decimal):
        return pl.Int128()
    if shared == pl.Date:
        return pl.Int32()
    if shared.is_temporal():
        return pl.Int64()
    return shared


def _pieces(shared: pl.DataType, held: pl.DataType) -> int:
    """Return how many 32-bit pieces select a value of ``shared`` exactly.

    One where no value is past what a double holds: a narrow whole number,
    a day count, and a time of day, whose nanoseconds stop short of 2**47.
    Two for a 64-bit whole number and four for a 128-bit one.
    """
    if shared == pl.Time or any(held == narrow for narrow in _NARROW_INTEGERS):
        return 1
    return 4 if held in (pl.Int128, pl.UInt128) else 2


def _as_held(
    branch: pl.Expr, dtype: pl.DataType | None, shared: pl.DataType
) -> pl.Expr:
    """Write one branch in the shared type, then as the whole number it is held as.

    The cast is strict, as ``pl.when``'s own is on the per-policy route: a
    ``UInt64`` value past ``i64`` beside an ``i64`` branch fails by its
    value rather than turning into a null.
    """
    target = pl.List(shared) if isinstance(dtype, pl.List) else shared
    if dtype != target:
        branch = branch.cast(target, strict=True)
    return branch.to_physical()


def _selected_by_pieces(  # noqa: PLR0913 - the selection, its two branches, the type they are held as, how many pieces, and the branches' shapes
    select: Callable[[pl.Expr, pl.Expr], pl.Expr],
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    *,
    held: pl.DataType,
    pieces: int,
    shapes: tuple[bool, bool],
) -> pl.Expr:
    """Select two whole-number branches 32 bits at a time, and join the pieces.

    The k-th piece of a value is ``(x // 2**(32k)) % 2**32``, and the last
    is ``x // 2**(32(n-1))`` with its sign: floor division and its remainder
    put every piece within ``[-2**31, 2**32)``, which a double holds
    exactly, so the kernel selects each without loss, and the sum of the
    pieces, each scaled back, is the value selected. A null stays null in
    every piece, so it stays null. Each piece is handed to the kernel as an
    ``Int64``, so the kernel never reads a 128-bit type itself.
    """
    run = pl.List(held)
    if pieces == 1:
        return select(then_val, otherwise_val).list.eval(pl.element().cast(held))
    joined: pl.Expr | None = None
    for k in reversed(range(pieces)):
        scale = pl.lit(_HALF**k, dtype=held)
        cut = [
            _piece(value, scale, k=k, last=k == pieces - 1, is_list=is_list, held=held)
            for value, is_list in zip((then_val, otherwise_val), shapes, strict=True)
        ]
        selected = select(*cut).cast(pl.List(pl.Int64)).cast(run)
        term = selected * scale if k else selected
        # The highest piece first: every partial sum then lies between the
        # value and its highest piece's share of it, inside the type.
        joined = term if joined is None else joined + term
    return cast("pl.Expr", joined)


def _piece(  # noqa: PLR0913 - the value, its scale, which piece, whether it is the last, its shape, and its type
    value: pl.Expr,
    scale: pl.Expr,
    *,
    k: int,
    last: bool,
    is_list: bool,
    held: pl.DataType,
) -> pl.Expr:
    """Return one 32-bit piece of a whole-number branch, as an ``Int64``."""
    shifted = value // scale if k else value
    if not last:
        shifted = shifted % pl.lit(_HALF, dtype=held)
    return shifted.cast(pl.List(pl.Int64) if is_list else pl.Int64)


def _read_back(run: pl.Expr, shared: pl.DataType) -> pl.Expr:
    """Read a run of whole numbers back as the shared type they were held for."""
    if shared.is_integer():
        return run
    if isinstance(shared, pl.Decimal):
        return run.list.eval(_decimal_of_units(pl.element(), shared))
    return run.cast(pl.List(shared))


def _decimal_of_units(units: pl.Expr, shared: pl.Decimal) -> pl.Expr:
    """Return a run of whole numbers read as the decimals they are the digits of.

    ``units`` is a decimal's unscaled digits, as ``to_physical`` hands them
    over: 125 for 1.25 at two places. Polars reads a whole number cast to a
    decimal as that many units, and a product by ``10**-scale`` is taken
    after carrying the whole number to that scale, where a value with more
    than ``38 - scale`` digits does not fit and answers a null -- every
    value at twenty places past 10**18. So the digits are written out as the
    decimal they spell, sign, whole part, point and places, and read back
    by Polars' own parsing, which every value of the type survives exactly.
    """
    if shared.scale == 0:
        return units.cast(shared)
    size = units.abs()
    step = pl.lit(10**shared.scale, dtype=pl.Int128)
    written = pl.concat_str(
        [
            pl.when(units < 0).then(pl.lit("-")).otherwise(pl.lit("")),
            (size // step).cast(pl.String),
            pl.lit("."),
            (size % step).cast(pl.String).str.zfill(shared.scale),
        ]
    )
    return written.cast(shared)


def _shared_branch_type(
    then: pl.DataType | None, otherwise: pl.DataType | None
) -> pl.DataType | None:
    """Return the type two branches of one kind share, or None.

    The element type where a branch is per-period, and the type itself
    where it is one value per policy -- a literal ``24`` opposite a run of
    durations is the ordinary case. The type is the one Polars' own
    conditional resolves the pair to, asked of an empty plan, so the
    per-period route and the per-policy route cannot disagree about it.
    None for two numbers of different families (a whole number opposite a
    double, a flag opposite either), which keeps the kernel's Float64, and
    for two kinds, which a conditional refuses before it gets here.
    """
    inner = [_element_of(then), _element_of(otherwise)]
    if any(dtype is None for dtype in inner):
        return None
    if all(dtype == pl.Boolean for dtype in inner):
        return pl.Boolean()
    kinds = {kind_of(dtype) for dtype in inner}
    if len(kinds) != 1 or None in kinds:
        return None
    if kinds == {"number"} and not all(
        dtype is not None and (dtype.is_integer() or isinstance(dtype, pl.Decimal))
        for dtype in inner
    ):
        return None
    shared = _polars_shared_type(inner[0], inner[1])
    if kinds == {"number"} and not (
        shared is None or shared.is_integer() or isinstance(shared, pl.Decimal)
    ):
        return None
    return shared


def _polars_shared_type(
    then: pl.DataType | None, otherwise: pl.DataType | None
) -> pl.DataType | None:
    """Return the type ``pl.when`` answers two branches in, or None if it has none."""
    try:
        return (
            pl.LazyFrame()
            .select(
                pl.when(pl.lit(value=True))
                .then(pl.lit(None, dtype=then))
                .otherwise(pl.lit(None, dtype=otherwise))
            )
            .collect_schema()
            .dtypes()[0]
        )
    except (pl.exceptions.SchemaError, pl.exceptions.InvalidOperationError):
        return None


# --- Call, EngineNative ------------------------------------------------------


def _lower_call(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Dispatch ``node`` to its registered lowering, by ``node.name``."""
    ensure_rules_loaded()
    lowering = LOWERINGS.get(node.name)
    if lowering is None:
        reason = (
            f"{node.name!r} has no entry in LOWERINGS -- register a lowering "
            "function for this call there before this formula can run."
        )
        raise LoweringError(node, reason)
    token = _CARRIED_BY.set(node.name in _CARRYING_CALLS)
    try:
        return lowering(node, ctx)
    finally:
        _CARRIED_BY.reset(token)


def _lower_engine_native(node: EngineNative) -> pl.Expr:
    """Resolve an ``EngineNative`` node to its held Polars expression, by identity."""
    if node.engine != "polars":
        reason = (
            f"native {node.engine!r} expressions cannot run on the Polars "
            "backend -- only engine='polars' nodes lower here."
        )
        raise LoweringError(node, reason)
    entry = NATIVE_REFS.get(id(node))
    if entry is None:
        reason = (
            "the runtime object behind this node is gone and must be "
            "re-supplied before this formula can run."
        )
        raise LoweringError(node, reason)
    _, expr = entry
    return expr
