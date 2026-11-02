# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``pl.Expr`` that cooperates with gaspatchio proxies in either operand order.

``pl.Expr``'s binary operators raise on a ``ColumnProxy``/``ExpressionProxy``
operand instead of returning ``NotImplemented``, so Python never offers the
proxy its reflected method — ``lookup(...) * af.col`` raised while
``af.col * lookup(...)`` worked (gh#67). Frame-independent expressions the
framework hands to users (``Table.lookup``, ``CompiledRollforward.expr_for``,
the ``Schedule.*_expr`` family) are therefore wrapped in this subclass.

When the other operand **is a proxy**, the operation is handed to the proxy's
reflected operator, because the proxy layer owns operator semantics the raw
polars operators lack (list arithmetic shims such as ``**`` on list columns).
The result is then the proxy layer's ``ExpressionProxy`` — the frame-native
currency, with the full accessor surface. When the other operand is anything
else, the operator delegates to polars unchanged and re-wraps, so the property
survives operator chains and ``isinstance(x, pl.Expr)`` stays true.

**The op-tree node travels with it.** An expression built here knows what it
is — an assumption-table lookup, a schedule's in-force mask, a compiled
rollforward read — and an operator standing after it does not make it stop
knowing. ``mortality.lookup(age=af.age) / 12`` is a division over a lookup,
so that is the node it carries: the lookup's own ``call``, with the table's
name and content identity on it, as a subtree of the operation around it.
Dropping the node here was how a monthly rate came to be recorded as one
opaque engine fragment with the basis it read nowhere in the file.

**The frame travels with it too, where there is one.** A producer that knows
which frame it is reading -- ``af.projection.year_fractions()`` does,
``table.lookup(age=af.age)`` borrows it from its operands, a rollforward
compiled from ``af.projection.rollforward(...)`` remembers it -- binds the
expression to that frame. A method chained straight on then means what it
means on the column the expression would be assigned to: every name the
declared vocabulary holds (the methods and the ``list``/``str`` namespaces
generated from the operation set), every operator the vocabulary declares,
the unary operators, the registered column accessors and ``polars_native()``
are answered by the frame's own expression proxy over the same node, and the
answer comes back as another bound ``ProxyAwareExpr`` -- a comparison held
once per policy as one marked a comparison, so that ``&`` and ``|`` read it
as the test it is, and one held per period as the predicate a column's
comparison is. So ``year_fractions().cum_sum()`` folds each
policy's periods, ``lookup(...).list.get(0)`` reads a period, an undeclared
``list.head`` is refused in the column's own words, and the five Polars
names whose meaning is the axis they run along (``shift``, ``diff``, the
fills, ``interpolate``) are refused as a column refuses them, instead of
moving values between policies. So are the Polars names that fold, order
or select among the rows (``sum``, ``mean``, ``max``, ``first``, ``sort``,
``rank``, ``filter``, ``rolling_*`` and the rest of ``DOWN_THE_ROWS``):
``lookup(age=af.age).sum()`` handed every policy the total of the whole
book's rates. Before this, every such method was Polars' own, and the same
formula meant two things depending on whether it was written on one line
or two.

An expression with no frame in sight -- a ``Schedule.*_expr`` read, built
for a raw Polars frame and taking none, or a lookup keyed only by literals --
is a Polars expression until it meets a frame, exactly as ``pl.col(...)`` is,
and its methods stay Polars' own: there is no column whose meaning it could
take, and guessing an axis would be the magic this module exists to remove.
It still carries its node, through operators and through ``-`` and ``abs``.
On a bound expression, any other name outside the vocabulary (``meta``,
``over``) keeps its Polars meaning too, which is what raw Polars interop
needs; ``polars_native()`` is the door to a row-reading name's Polars
meaning, as it is on a column. ``alias`` renames as Polars does and keeps
the node, because a name is not a calculation.

**A read of a table, a mortality basis, a curve or a schedule never hides
inside a Polars method's answer.** A Polars method returns a plain
expression that has lost the node, and the frame would record it as an
engine fragment identified by Polars' text, which names the lookup plugin
and not the table -- two models reading two tables would carry one
fingerprint. So ``wrap`` registers each such read's plan
(``frame/lowering/value_reads.py``), and a frame refuses an assignment
whose fragment holds one, naming the read and the two ways to keep it a
node. A plain Polars frame never meets that rule.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, cast

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import BinOpKind, OpNode
    from gaspatchio._shape import Kind
    from gaspatchio.column.condition_expression import ConditionExpression
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame

# A binary op with a proxy operand is handed to the proxy's method for the
# mirrored operand order: ``self OP other`` == ``other REFLECTED_OP self``.
_REFLECTED = {
    "__add__": "__radd__",
    "__radd__": "__add__",
    "__sub__": "__rsub__",
    "__rsub__": "__sub__",
    "__mul__": "__rmul__",
    "__rmul__": "__mul__",
    "__truediv__": "__rtruediv__",
    "__rtruediv__": "__truediv__",
    "__floordiv__": "__rfloordiv__",
    "__rfloordiv__": "__floordiv__",
    "__mod__": "__rmod__",
    "__rmod__": "__mod__",
    "__pow__": "__rpow__",
    "__rpow__": "__pow__",
    "__and__": "__rand__",
    "__rand__": "__and__",
    "__or__": "__ror__",
    "__ror__": "__or__",
    "__xor__": "__rxor__",
    "__rxor__": "__xor__",
    "__eq__": "__eq__",
    "__ne__": "__ne__",
    "__lt__": "__gt__",
    "__gt__": "__lt__",
    "__le__": "__ge__",
    "__ge__": "__le__",
}


# Each dunder this class defines, as the op-tree operator it means and
# whether the author wrote this expression on the right of it. Python
# offers a reflected dunder only for the arithmetic and boolean operators;
# for a comparison it calls the mirrored one instead (``1 < lookup(...)``
# reaches ``__gt__``), which is why the comparisons appear once each and
# unreflected -- the mirror has already been taken by the time the call
# arrives, exactly as it is for the proxy classes' own comparisons.
#
# ``__xor__``/``__rxor__`` are deliberately absent: the closed operator
# vocabulary of section 11.1 has no exclusive-or, so a line written with
# one has no node to carry and keeps the engine fragment it always was.
_BINOP: dict[str, tuple[BinOpKind, bool]] = {
    "__add__": ("add", False),
    "__radd__": ("add", True),
    "__sub__": ("sub", False),
    "__rsub__": ("sub", True),
    "__mul__": ("mul", False),
    "__rmul__": ("mul", True),
    "__truediv__": ("div", False),
    "__rtruediv__": ("div", True),
    "__floordiv__": ("floordiv", False),
    "__rfloordiv__": ("floordiv", True),
    "__mod__": ("mod", False),
    "__rmod__": ("mod", True),
    "__pow__": ("pow", False),
    "__rpow__": ("pow", True),
    "__and__": ("and", False),
    "__rand__": ("and", True),
    "__or__": ("or", False),
    "__ror__": ("or", True),
    "__eq__": ("eq", False),
    "__ne__": ("ne", False),
    "__lt__": ("lt", False),
    "__le__": ("le", False),
    "__gt__": ("gt", False),
    "__ge__": ("ge", False),
}


class ProxyAwareExpr(pl.Expr):
    """``pl.Expr`` whose operators accept proxies on either side."""

    # The op-tree node this expression was lowered from, set by `wrap` when
    # the producer had one. Left unset otherwise, so `to_node` falls back to
    # recording an engine-native expression -- which is the honest answer for
    # an expression nothing in the framework can describe semantically.
    _node: OpNode

    # The frame this expression was read from or borrowed from its operands,
    # where the producer had one; ``None`` for a frame-independent one.
    _parent: ActuarialFrame | None = None

    # The kind the proxy layer asserted for the expression this one re-wraps
    # (a mask built by ``~``, say), so that re-wrapping does not forget it.
    _kind_explicit: Kind | None = None

    @classmethod
    def wrap(
        cls,
        expr: pl.Expr,
        node: OpNode | None = None,
        parent: object | None = None,
    ) -> ProxyAwareExpr:
        """Rebuild ``expr`` as a ``ProxyAwareExpr`` (shares the same plan).

        ``node`` is the semantic op-tree node ``expr`` was lowered from,
        when the caller has one. Carrying it means an operand that meets
        this expression later sees what it *is* -- an assumption-table
        lookup, a compiled rollforward read -- rather than an opaque
        engine expression it can only record as engine-native.

        ``parent`` is the frame the expression belongs to, when the
        producer knows it. Bound, the declared vocabulary chained on the
        expression answers as the frame's column would (see the module
        docstring).
        """
        wrapped = cast("ProxyAwareExpr", cls._from_pyexpr(expr._pyexpr))  # noqa: SLF001
        if node is not None:
            wrapped._node = node  # noqa: SLF001
            # A table, mortality, curve or schedule read is remembered by
            # its plan, so a frame can refuse it where it has been inlined
            # into an engine fragment that would hide it (spec Annex A.2).
            from gaspatchio.frame.lowering.value_reads import (  # noqa: PLC0415 -- import cycle
                register_value_read,
            )

            register_value_read(expr, node, framed=parent is not None)
        if parent is not None:
            # Whatever frame the producer read, or borrowed from an operand's
            # own ``_parent`` -- the frame a proxy belongs to.
            wrapped._parent = cast("ActuarialFrame", parent)  # noqa: SLF001
        return wrapped

    @classmethod
    def _from_proxy(cls, proxy: ExpressionProxy) -> ProxyAwareExpr:
        """Re-wrap a frame proxy's answer as a bound ``ProxyAwareExpr``."""
        wrapped = cls.wrap(proxy._expr, node=proxy._node, parent=proxy._parent)  # noqa: SLF001
        explicit = proxy._kind_explicit  # noqa: SLF001
        if explicit is not None:
            wrapped._kind_explicit = explicit  # noqa: SLF001
        return wrapped

    def _as_proxy(self) -> ExpressionProxy:
        """Return the frame's expression proxy over this expression's node.

        Detached (``parent=None``) where the producer had no frame, which is
        the existing contract for a proxy with no schema to read: no period
        axis is known, and what needs one says so.
        """
        from gaspatchio.column.expression_proxy import (  # noqa: PLC0415 -- import cycle
            ExpressionProxy,
        )

        return ExpressionProxy._from_node(  # noqa: SLF001
            self._node, self._parent, kind=self._kind_explicit
        )

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 -- an accessor of any kind
        """Answer a name ``pl.Expr`` does not hold as the frame's column would.

        That is the column's ``shape`` and ``kind``, its ``polars_native()``
        door, and every registered column accessor (``.finance``,
        ``.projection``, ...). Runs only for a name ``pl.Expr`` does not hold
        itself, so nothing Polars defines is shadowed. A private or dunder
        name, or an expression with no frame to answer for it, is absent.
        """
        if name.startswith("_") or not _is_bound(self):
            raise AttributeError(name)
        return getattr(self._as_proxy(), name)

    def alias(self, name: str) -> ProxyAwareExpr:
        """Rename the expression; what it computes, and the node, are unchanged.

        A name is not a calculation (the graph's identity of a computed
        column leaves its name out), so ``af.with_columns(
        table.lookup(age=af.age).alias("q"))`` records the lookup it is
        rather than an engine fragment that hides the table.
        """
        renamed = pl.Expr.alias(self, name)
        if "_node" not in self.__dict__:
            return ProxyAwareExpr.wrap(renamed)
        wrapped = ProxyAwareExpr.wrap(renamed, node=self._node, parent=self._parent)
        if self._kind_explicit is not None:
            wrapped._kind_explicit = self._kind_explicit  # noqa: SLF001
        return wrapped

    def _composed(self, op: str, other: object) -> OpNode | None:
        """Return the node ``self op other`` is, or ``None`` where there is none.

        There is one exactly when this expression knows what it is. A raw
        expression somebody built and handed over does not, and an operator
        standing after it cannot invent one: the result is an engine
        fragment either way, and saying so is the honest answer. Where the
        node exists, the other operand walks through the same door every
        other operand does -- a literal enters as a literal, a raw
        expression as the engine fragment it is -- so one escape hatch
        still makes the whole node engine-native, with the lookup beside it
        still readable.
        """
        node = getattr(self, "_node", None)
        if node is None:
            return None
        composed = _BINOP.get(op)
        if composed is None:
            return None
        from gaspatchio._semantic.ir import BinOp  # noqa: PLC0415 -- import cycle
        from gaspatchio.frame.lowering.ingress import to_node  # noqa: PLC0415 -- cycle

        kind, reflected = composed
        operand = to_node(other)
        left, right = (operand, node) if reflected else (node, operand)
        return BinOp(op=kind, left=left, right=right)

    def _answers_as_the_frame(self, op: str) -> bool:
        """Return whether ``op`` is answered by the frame's proxy over this node.

        For an expression bound to a frame, and an operator the proxy layer
        declares, per policy as per period. Polars' own operator on a
        per-policy expression did not mean what the column's does: ``lookup &
        1`` and ``lookup ** True`` failed in Polars' words where a column
        refuses the first by name and answers the second, ``True ** lookup``
        was recorded as a Boolean, and the expression's own quotient by a
        literal was Polars' product by the reciprocal, a last bit away from
        the column's.
        """
        if self._parent is None or "_node" not in self.__dict__:
            return False
        from gaspatchio.column._generated_proxy import (  # noqa: PLC0415 -- import cycle
            _GeneratedProxySurface,
        )

        return op in vars(_GeneratedProxySurface)

    def _operated(self, op: str, other: object) -> ProxyAwareExpr | ExpressionProxy:
        """Apply an arithmetic or boolean operator: never a predicate."""
        return cast("ProxyAwareExpr | ExpressionProxy", self._binary(op, other))

    def _binary(
        self, op: str, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        # The operand is a proxy exactly when it can turn itself into an
        # expression, so the bound method is what the test asks for and what
        # the fallback below calls -- fetched once rather than probed and
        # then fetched again.
        to_expr = getattr(other, "_to_expr", None)
        if to_expr is not None or _is_condition(other):
            reflected = getattr(other, _REFLECTED[op], None)
            if reflected is not None:
                # The proxy layer owns operator semantics polars lacks
                # (list-column shims); hand it the whole operation. A
                # predicate (``af.dur > 0``) is a proxy-layer operand too,
                # though it has no ``_to_expr``: polars cannot make a literal
                # of one, so ``mask & (af.dur > 0)`` raised.
                return cast("ExpressionProxy | ConditionExpression", reflected(self))
            if to_expr is not None:
                other = to_expr()
        elif self._answers_as_the_frame(op):
            # An expression read from a frame: answer as the column does.
            # Arithmetic comes back as a bound expression; a comparison per
            # period as the predicate a column's comparison is, since Polars
            # cannot compare a list with a number; and one per policy as a
            # bound expression marked a comparison, which stays the Polars
            # expression raw interop reads.
            answer = getattr(self._as_proxy(), op)(other)
            if _is_condition(answer) and answer.shape != "list":
                return _a_bound_comparison(answer)
            return cast(
                "ProxyAwareExpr | ExpressionProxy | ConditionExpression",
                _rewrapped(answer),
            )
        # Built before the operator runs, so that the node is taken over the
        # operand the author wrote rather than over whatever the branch
        # above turned it into.
        composed = self._composed(op, other)
        parent = self._parent or getattr(other, "_parent", None)
        # Polars' operator runs on a plain expression: its reflected operators
        # apply the forward one with this expression on the right, and on this
        # subclass Python hands that straight back here -- ``1.05 **
        # table.lookup(...)`` recursed until the interpreter gave up.
        plain = pl.Expr._from_pyexpr(self._pyexpr)  # noqa: SLF001
        return ProxyAwareExpr.wrap(
            getattr(plain, op)(other), node=composed, parent=parent
        )

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__add__``."""
        return self._operated("__add__", other)

    def __radd__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__radd__``."""
        return self._operated("__radd__", other)

    def __sub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__sub__``."""
        return self._operated("__sub__", other)

    def __rsub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rsub__``."""
        return self._operated("__rsub__", other)

    def __mul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__mul__``."""
        return self._operated("__mul__", other)

    def __rmul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rmul__``."""
        return self._operated("__rmul__", other)

    def __truediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__truediv__``."""
        return self._operated("__truediv__", other)

    def __rtruediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rtruediv__``."""
        return self._operated("__rtruediv__", other)

    def __floordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__floordiv__``."""
        return self._operated("__floordiv__", other)

    def __rfloordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rfloordiv__``."""
        return self._operated("__rfloordiv__", other)

    def __mod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__mod__``."""
        return self._operated("__mod__", other)

    def __rmod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rmod__``."""
        return self._operated("__rmod__", other)

    def __pow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__pow__``."""
        return self._operated("__pow__", other)

    def __rpow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rpow__``."""
        return self._operated("__rpow__", other)

    # -- comparisons ------------------------------------------------------
    def __eq__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__eq__``: a predicate where a proxy layer answers it."""
        return self._binary("__eq__", other)

    def __ne__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__ne__``: a predicate where a proxy layer answers it."""
        return self._binary("__ne__", other)

    def __lt__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__lt__``: a predicate where a proxy layer answers it."""
        return self._binary("__lt__", other)

    def __le__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__le__``: a predicate where a proxy layer answers it."""
        return self._binary("__le__", other)

    def __gt__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__gt__``: a predicate where a proxy layer answers it."""
        return self._binary("__gt__", other)

    def __ge__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression:
        """Proxy-aware ``__ge__``: a predicate where a proxy layer answers it."""
        return self._binary("__ge__", other)

    __hash__ = pl.Expr.__hash__

    # -- boolean ----------------------------------------------------------
    def __and__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__and__``."""
        return self._operated("__and__", other)

    def __rand__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rand__``."""
        return self._operated("__rand__", other)

    def __or__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__or__``."""
        return self._operated("__or__", other)

    def __ror__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__ror__``."""
        return self._operated("__ror__", other)

    def __xor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__xor__``."""
        return self._operated("__xor__", other)

    def __rxor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rxor__``."""
        return self._operated("__rxor__", other)

    # -- unary ------------------------------------------------------------
    # A unary operator is an operation like any other: with a node it is the
    # node the proxy layer builds for it (``mul`` by -1, ``abs``, ``not_``),
    # lowered against the frame where there is one -- so ``~`` over a
    # per-period mask negates each period rather than being refused by
    # Polars as an operation on a list -- and it keeps the frame. Without a
    # node there is nothing to carry, and Polars' own operator stands.
    #
    # With no frame, Polars' operator is the value it has always computed and
    # the node is built here, as the proxy layer builds it, for ``-`` and
    # ``abs``. ``~`` is left as engine text there: without a frame to type
    # the operand it may be Polars' bitwise not of an integer, which the
    # logical ``not_`` would misrecord.
    def _unary(self, op: str) -> ProxyAwareExpr:
        native = getattr(super(), op)()
        if "_node" not in self.__dict__:
            return ProxyAwareExpr.wrap(native)
        if self._parent is not None:
            return ProxyAwareExpr._from_proxy(getattr(self._as_proxy(), op)())
        from gaspatchio._semantic.ir import BinOp, Call, Lit  # noqa: PLC0415 -- cycle

        node = self._node
        detached = {
            "__neg__": BinOp(op="mul", left=node, right=Lit(-1)),
            "__abs__": Call("abs", args=(node,), attrs=()),
        }.get(op)
        return ProxyAwareExpr.wrap(native, node=cast("OpNode | None", detached))

    def __neg__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__neg__``: the node and the frame survive."""
        return self._unary("__neg__")

    def __pos__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__pos__``: the expression itself."""
        return self

    def __abs__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__abs__``: the node and the frame survive."""
        return self._unary("__abs__")

    def __invert__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__invert__``: the node and the frame survive."""
        return self._unary("__invert__")


def _is_condition(value: object) -> bool:
    """Return whether ``value`` is a proxy-layer predicate (no ``_to_expr``)."""
    from gaspatchio.column.condition_expression import (  # noqa: PLC0415 -- import cycle
        ConditionExpression,
    )

    return isinstance(value, ConditionExpression)


def _a_bound_comparison(test: ConditionExpression) -> ProxyAwareExpr:
    """Hand a per-policy comparison back as a bound expression marked a comparison.

    The mark is what ``&``, ``|`` and ``~`` read: without it, a comparison
    over a value whose type the frame cannot read before it runs -- a
    rollforward state's period -- was refused as no test at all.
    """
    wrapped = ProxyAwareExpr.wrap(test._expr, node=test._node, parent=test._parent)  # noqa: SLF001
    wrapped._kind_explicit = "comparison"  # noqa: SLF001
    return wrapped


def _rewrapped(answer: object) -> object:
    """Hand a frame proxy's answer back as a bound ``ProxyAwareExpr``.

    An ``ExpressionProxy`` answer is re-wrapped so the chain stays a
    ``pl.Expr`` with the declared surface; a predicate or anything else is
    returned as the proxy layer gave it.
    """
    from gaspatchio.column.expression_proxy import (  # noqa: PLC0415 -- import cycle
        ExpressionProxy,
    )

    if isinstance(answer, ExpressionProxy):
        return ProxyAwareExpr._from_proxy(answer)  # noqa: SLF001
    return answer


class _AnsweredNamespace:
    """A declared namespace whose answers come back as bound expressions."""

    def __init__(self, namespace: object) -> None:
        self._namespace = namespace

    def __getattr__(self, name: str) -> object:
        attribute = getattr(self._namespace, name)
        if not callable(attribute):
            return attribute

        @wraps(attribute)
        def _answered(*args: object, **kwargs: object) -> object:
            return _rewrapped(attribute(*args, **kwargs))

        return _answered


def _answered_by_the_frame(name: str, declared: object) -> object:
    """Return the ``ProxyAwareExpr`` attribute that hands ``name`` to the frame.

    An expression with no node falls back to Polars' own attribute: there
    is no operation to hand on.
    """
    native = getattr(pl.Expr, name, None)
    if isinstance(declared, property):

        def _namespace(self: ProxyAwareExpr) -> object:
            if not _is_bound(self) and isinstance(native, property):
                return native.__get__(self)
            return _AnsweredNamespace(getattr(self._as_proxy(), name))

        return property(_namespace, doc=declared.__doc__)

    @wraps(cast("Callable[..., object]", declared))
    def _method(self: ProxyAwareExpr, *args: object, **kwargs: object) -> object:
        if not _is_bound(self) and callable(native):
            return native(self, *args, **kwargs)
        return _rewrapped(getattr(self._as_proxy(), name)(*args, **kwargs))

    return _method


def _is_bound(expr: ProxyAwareExpr) -> bool:
    """Return whether ``expr`` answers as a frame's column: a node and a frame.

    An expression with no frame in sight -- a ``Schedule.*_expr`` read, a
    lookup keyed only by literals -- is a Polars expression until it meets
    one, exactly as ``pl.col(...)`` is, and keeps Polars' own methods: there
    is no column whose meaning it could take, and the Polars meaning is the
    one raw Polars interop relies on.
    """
    return "_node" in expr.__dict__ and expr._parent is not None  # noqa: SLF001


def _install_the_declared_surface() -> None:
    """Answer the declared vocabulary, and the row-reading names, through the frame.

    The vocabulary is the operation set's, read off the surface it
    generates, so a producer's expression can neither gain nor miss a name
    a column has. The axis names are the Polars names whose meaning *is*
    the axis they run along: Polars' ``shift`` on a per-period expression
    moves values between policies, and a column refuses it, naming the
    per-period spelling; so does this. The row-reading names
    (``DOWN_THE_ROWS``) are the folds, orders and selections Polars runs
    down the rows: ``sum`` on a per-policy lookup handed every policy the
    total over the book, and a column refuses it, naming the escape; so
    does this.
    """
    from gaspatchio.column._generated_proxy import (  # noqa: PLC0415 -- import cycle
        _GeneratedProxySurface,
    )
    from gaspatchio.frame.lowering.methods import (  # noqa: PLC0415 -- import cycle
        ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE,
        DOWN_THE_ROWS,
    )

    for name, declared in vars(_GeneratedProxySurface).items():
        if not name.startswith("_"):
            setattr(ProxyAwareExpr, name, _answered_by_the_frame(name, declared))
    for name in sorted(ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE | DOWN_THE_ROWS):
        setattr(
            ProxyAwareExpr, name, _answered_by_the_frame(name, getattr(pl.Expr, name))
        )


_install_the_declared_surface()
