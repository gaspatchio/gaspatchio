# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The way out of gaspatchio's vocabulary, with the price written on the door.

``af.reserve = af.claims.projection.prospective_value(...)`` is an operation
the framework names: it becomes a ``Call`` node, any engine holding the
operation can evaluate it, and the exported record says what was computed.
Polars can do a great deal the vocabulary does not name, and an actuary who
needs one of those things should be able to reach it -- in the open, saying
so, rather than by a wiring accident.

``af.<column>.polars_native().<method>(...)`` is that reach. What comes back
is an ordinary ``ExpressionProxy`` carrying an ``EngineNative`` node: the
calculation runs, the columns it reads stay declared, and every reader of
the record -- the calculation graph, the exported artifact, the fingerprint
-- sees a fragment written in Polars' own language rather than an operation
the framework can account for.

**What it costs, which is the whole reason it is spelled out loud.** An
``EngineNative`` node holds the engine's *rendering* of an expression, not a
program anything can parse back. Lowering resolves it through the live
Python object it was minted from (``ingress.NATIVE_REFS``), so the formula
runs in the process that wrote it and nowhere else: exported and read back
somewhere else, it is a record of a calculation, not a calculation. It also
takes the model off the portable subset -- a second engine has no lowering
for one engine's own text, by construction.

**What it refuses**, and each refusal is the same principle from a different
side -- the vocabulary is the source of truth, and the record is not allowed
to be vaguer than the calculation:

- a method the vocabulary already covers **in the form it was written**, so
  that ``af.x.round(2)`` and ``af.x.polars_native().round(2)`` can never both
  work and disagree about what the model did. The test is the recogniser the
  ordinary surface uses, not the method's name, which is what keeps the door
  open for a shape the vocabulary declines -- a per-policy ``cum_sum``, say,
  which is a fold down the model points rather than along the periods;
- a **per-period column** handed to one of the few names whose meaning is
  the axis they run along and which the vocabulary does not name -- ``shift``,
  ``diff`` and the three fills. Polars reads such a column as one value per
  policy, so the escape would run the calculation down the model points and
  hand back a right-shaped answer with nothing to say which axis it used. The
  refusal gives the per-period spelling, which is ``list.eval``;
- an expression that will not say which columns it reads, unless the author
  declares them with ``deps=``. A node with no precedents is a lineage claim
  the artifact cannot support;
- an engine nothing here can lower.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Final

import polars as pl

from gaspatchio._authoring._native_docs import (
    _DocumentedPolarsDateTimeMethods,
    _DocumentedPolarsNativeMethods,
    _DocumentedPolarsStringMethods,
)
from gaspatchio.frame.lowering.ingress import native_node

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Sequence

    from gaspatchio._semantic.ir import EngineName
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.column.expression_proxy import ExpressionProxy

    # The two receivers an escape can be opened on: a column of the frame,
    # and an unfinished expression over it.
    type ProxyType = ColumnProxy | ExpressionProxy

# The engines this package can lower an ``EngineNative`` node for. One,
# today: ``polars._lower_engine_native`` is the only rule that resolves one,
# and it refuses any other engine at lowering. The escape refuses the same
# thing one step earlier, at the line the author wrote, because a formula
# that cannot run is better refused where it was written than three phases
# later inside ``collect()``.
_LOWERABLE_ENGINES: Final[tuple[EngineName, ...]] = ("polars",)


def _refuse_a_bare_string(deps: Sequence[str]) -> None:
    """Refuse ``deps="account_value"``, which iterates into single letters."""
    if isinstance(deps, str):
        msg = (
            f"deps={deps!r} is one string, and a string of column names read "
            "letter by letter is not a read-set. Pass the names in a list, "
            f"even when there is one of them: deps=[{deps!r}]."
        )
        raise TypeError(msg)


def _declared_deps(deps: Sequence[str] | None) -> tuple[str, ...] | None:
    """Return ``deps`` as the read-set a node can carry, or ``None``.

    De-duplicated first-occurrence-first, the same order ``ir.col_refs``
    reports a tree's reads in, so a name written twice is declared once.
    """
    if deps is None:
        return None
    _refuse_a_bare_string(deps)
    declared: dict[str, None] = {}
    for name in deps:
        if not isinstance(name, str) or not name:
            msg = (
                f"deps holds {name!r}, which is not a column name. Every "
                "entry names a column this expression reads, spelled the way "
                "the frame spells it -- deps=['account_value', 'month']."
            )
            raise TypeError(msg)
        declared.setdefault(name, None)
    return tuple(declared)


def _reported_deps(expr: pl.Expr) -> tuple[str, ...] | None:
    """Return the columns ``expr`` says it reads, or ``None`` if it will not."""
    try:
        return tuple(expr.meta.root_names())
    except (AttributeError, RuntimeError):
        return None


def _resolved_deps(
    expr: pl.Expr, declared: tuple[str, ...] | None, method: str
) -> tuple[str, ...]:
    """Settle what the minted node declares it reads, or refuse to mint it.

    An expression that reports its own roots is believed, and a declaration
    beside it is an assertion that is checked rather than a second opinion
    that is trusted: the two must name the same columns, because a lineage
    declaration that is not the read-set is worse than no declaration at
    all -- it is wrong in a document whose whole purpose is that it can be
    checked.

    An expression that will not report its roots -- a compiled plugin can
    decline -- is refused unless the author declares them. The other door
    into ``EngineNative`` (an expression handed in as an operand) accepts
    that silence, because refusing there would refuse a line the author has
    already written. Here the author asked for the escape by name, so the
    refusal lands on a line they can fix.
    """
    reported = _reported_deps(expr)
    if declared is None:
        if reported is None:
            msg = (
                f"{method!r} produced an expression that will not say which "
                "columns it reads, so the calculation would be recorded with "
                "no inputs at all. Declare them where you open the escape: "
                f"af.<column>.polars_native(deps=['<column>']).{method}(...)."
            )
            raise ValueError(msg)
        return reported
    if reported is not None and set(declared) != set(reported):
        msg = (
            f"deps={list(declared)} is not what this expression reads, which "
            f"is {list(reported)}. The declaration is the model's lineage "
            "claim for a calculation nothing else can read, so it has to be "
            "the read-set exactly -- correct the list, or leave deps off and "
            "let the expression report its own."
        )
        raise ValueError(msg)
    return declared


def _refuse_an_axis_flip(
    receiver: ProxyType, method: str, namespace: str | None
) -> None:
    """Refuse a per-period column to a method the escape runs down the rows.

    The sibling refusal below keys on the recogniser, so it only reaches
    names the vocabulary holds. These names it does not hold at all, which
    is exactly why they need saying: the escape is the only route to them,
    Polars reads a per-period column as one value per policy, and the
    answer comes back the right shape with no error. Only a *list* receiver
    is refused -- on a per-policy column these are ordinary row semantics
    and the calculation the author wrote -- and only the bare method, since
    ``list.eval`` is the per-period spelling this points at.
    """
    from gaspatchio.frame.lowering.methods import (  # noqa: PLC0415 -- cycle
        ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE,
    )

    if (
        namespace is not None
        or method not in ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE
        or getattr(receiver, "shape", None) != "list"
    ):
        return
    msg = (
        f"{method!r} on a per-period column runs down the model points, not "
        "along each policy's projection periods. This column holds one value "
        "per period, and through the escape Polars reads the whole column as "
        "one value per policy: the calculation would move values between "
        "policies rather than between periods, and the answer comes back the "
        "right shape with no error to tell you which axis it used. For the "
        "per-period form, evaluate it inside each policy's own list -- "
        f"af.<column>.polars_native().list.eval(pl.element().{method}(...)). "
        "For a calculation that really does run down the model points, take "
        "it on a per-policy column."
    )
    raise ValueError(msg)


def _refuse_a_covered_method(
    receiver: ProxyType, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Refuse a call the vocabulary already names, and name the operation.

    Keyed on the recogniser the ordinary proxy surface uses rather than on
    the method's name, and the difference is the point: ``round(2)`` is the
    ``round`` operation and is refused here, while a call the recogniser
    declines -- a form of the arguments it cannot hold, or a receiver whose
    axis makes it a different calculation -- is exactly what the escape is
    for and is let through.
    """
    from gaspatchio.column._declared import (  # noqa: PLC0415
        _core_call_node,
        _operator_coverage,
    )

    operation = _operator_coverage(method, receiver, args, kwargs)
    if operation is None:
        covered = _core_call_node(method, receiver, args, kwargs)
        if covered is None:
            return
        operation = covered.name
    spelling = {
        "and_": "af.<column> & other",
        "or_": "af.<column> | other",
        "not_": "~af.<column>",
    }.get(method, f"af.<column>.{method}(...)")
    msg = (
        f"{method!r} as you have written it is already in gaspatchio's "
        f"vocabulary, as the operation {operation!r}. Written without the "
        f"escape -- {spelling} -- it records as that "
        "operation, which any engine holding the vocabulary can evaluate and "
        "any reader of the record can check. Through polars_native the same "
        "number would record as Polars text, so the two spellings of one "
        f"calculation would disagree. Drop .polars_native() from this line."
    )
    raise ValueError(msg)


class PolarsNative(_DocumentedPolarsNativeMethods):
    """One column or expression, opened up to Polars' own method surface.

    Built by ``af.<column>.polars_native()``; see that method for what the
    escape is for and what it costs. Every attribute reached on it is looked
    up on ``pl.Expr``: a method call mints an ``EngineNative`` node and hands
    back an ordinary ``ExpressionProxy``, and anything that is not a callable
    method of a Polars expression is refused by name.
    """

    __slots__ = ("_declared", "_receiver")

    # The engine the nodes minted here are written for. A class attribute
    # rather than a literal at the mint, so a second engine's escape is a
    # subclass with one line changed and the guard below still runs on it.
    engine: ClassVar[EngineName] = "polars"

    def __init__(
        self, receiver: ProxyType, deps: Sequence[builtins.str] | None = None
    ) -> None:
        """Open the escape on ``receiver``, optionally declaring what it reads.

        Parameters
        ----------
        receiver : ColumnProxy | ExpressionProxy
            The column or unfinished expression the Polars method is called
            on.
        deps : Sequence[str], optional
            The columns the resulting expression reads. Required only where
            the expression will not report them itself; checked against what
            it does report where it will.

        """
        if self.engine not in _LOWERABLE_ENGINES:
            msg = (
                f"nothing here can lower a {self.engine!r} expression: "
                f"{', '.join(_LOWERABLE_ENGINES)} is the only engine with a "
                "lowering, so a formula written in this one could be recorded "
                "but never run. Write the calculation with an operation from "
                "gaspatchio's own vocabulary, which every engine lowers."
            )
            raise ValueError(msg)
        self._receiver = receiver
        self._declared = _declared_deps(deps)

    def __repr__(self) -> builtins.str:
        """Name the receiver and say what an expression built here costs."""
        declared = "" if self._declared is None else f", deps={list(self._declared)}"
        return (
            f"PolarsNative({self._receiver!r}{declared}) -- "
            f"{self.engine} text, which this process can run and no export "
            "can re-run"
        )

    def __getattr__(self, name: builtins.str) -> Callable[..., ExpressionProxy]:
        """Return the caller for one Polars expression method, or refuse ``name``.

        Raises:
            AttributeError: If ``name`` is not a callable method of a Polars
                expression -- a misspelling or a private name.

        """
        if name.startswith("_"):
            msg = (
                f"{name!r} is not something to reach through the escape: "
                "polars_native reaches Polars' public expression methods, and "
                "an underscore-prefixed name is one library's internals."
            )
            raise AttributeError(msg)
        attribute = getattr(pl.Expr, name, None)
        if attribute is None:
            msg = (
                f"a Polars expression has no method named {name!r}. "
                "polars_native reaches Polars' own methods, spelled exactly "
                "as Polars spells them -- check the name, or use gaspatchio's "
                "vocabulary where it covers what you need."
            )
            raise AttributeError(msg)
        if not callable(attribute):
            msg = (
                f"{name!r} does not build an expression. Reach a public "
                "Polars method or namespace through polars_native()."
            )
            raise AttributeError(msg)  # noqa: TRY004 - attribute lookup contract

        def call_through_the_escape(
            *args: Any,  # noqa: ANN401
            **kwargs: Any,  # noqa: ANN401
        ) -> ExpressionProxy:
            """Call one Polars method and mint the node that stands for it."""
            return self._mint(name, args, kwargs)

        call_through_the_escape.__name__ = f"polars_native_{name}"
        call_through_the_escape.__qualname__ = f"PolarsNative.{name}"
        return call_through_the_escape

    def _build(
        self,
        method: builtins.str,
        args: tuple[Any, ...],
        kwargs: dict[builtins.str, Any],
        namespace: builtins.str | None = None,
    ) -> ExpressionProxy:
        """Build the Polars expression and the node that declares it.

        Parameters
        ----------
        method : str
            The Polars expression method the author reached for.
        namespace : str, optional
            The public Polars namespace containing the method.
        args, kwargs : Any
            The call's arguments as written; a proxy among them is unwrapped
            to the expression it stands for, exactly as it is on the
            ordinary method surface.

        Returns
        -------
        ExpressionProxy
            The expression, carried by an ``EngineNative`` node declaring the
            engine and the columns it reads.

        """
        from gaspatchio.column._dispatch_common import (  # noqa: PLC0415
            _get_proxy_base_expr,
            _unwrap,
        )
        from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

        qualified = method if namespace is None else f"{namespace}.{method}"
        _refuse_an_axis_flip(self._receiver, method, namespace)
        _refuse_a_covered_method(self._receiver, qualified, args, kwargs)
        base = _get_proxy_base_expr(self._receiver)
        owner = base if namespace is None else getattr(base, namespace)
        built = getattr(owner, method)(
            *(_unwrap(argument) for argument in args),
            **{name: _unwrap(value) for name, value in kwargs.items()},
        )
        if not isinstance(built, pl.Expr):
            msg = (
                f"{method!r} gave back a {type(built).__name__}, not a Polars "
                "expression, so there is no calculation here to record. "
                "polars_native is for the methods that build an expression."
            )
            raise TypeError(msg)
        node = native_node(built, _resolved_deps(built, self._declared, qualified))
        parent = getattr(self._receiver, "_parent", None)
        return ExpressionProxy._from_node(node, parent)  # noqa: SLF001

    def _mint(
        self,
        method: builtins.str,
        args: tuple[Any, ...],
        kwargs: dict[builtins.str, Any],
        namespace: builtins.str | None = None,
    ) -> ExpressionProxy:
        """Record one native operation and retain model-source error context."""
        from gaspatchio.column._declared import ErrorEnhancer  # noqa: PLC0415
        from gaspatchio.util import get_error_mode  # noqa: PLC0415

        try:
            return self._build(method, args, kwargs, namespace)
        except Exception as error:
            if get_error_mode() == "off":
                raise
            qualified = method if namespace is None else f"{namespace}.{method}"
            raise ErrorEnhancer(self._receiver).enhance_method_error(
                error, f"polars_native().{qualified}"
            ) from error

    @property
    def dt(self) -> PolarsNativeDate:
        """Reach Polars' dt namespace with its own expression semantics."""
        return PolarsNativeDate(self, "dt")

    @property
    def str(self) -> PolarsNativeString:
        """Reach Polars' str namespace with its own expression semantics."""
        return PolarsNativeString(self, "str")

    @property
    def list(self) -> PolarsNativeNamespace:
        """Reach Polars' list namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "list")

    @property
    def arr(self) -> PolarsNativeNamespace:
        """Reach Polars' arr namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "arr")

    @property
    def struct(self) -> PolarsNativeNamespace:
        """Reach Polars' struct namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "struct")

    @property
    def cat(self) -> PolarsNativeNamespace:
        """Reach Polars' cat namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "cat")

    @property
    def bin(self) -> PolarsNativeNamespace:
        """Reach Polars' bin namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "bin")

    @property
    def name(self) -> PolarsNativeNamespace:
        """Reach Polars' name namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "name")

    @property
    def meta(self) -> PolarsNativeNamespace:
        """Reach Polars' meta namespace with its own expression semantics."""
        return PolarsNativeNamespace(self, "meta")


class PolarsNativeNamespace:
    """A public Polars namespace reached through the explicit engine escape.

    Methods use Polars' own scalar, list and array meanings. For example,
    ``af.codes.polars_native().list.eval(pl.element().str.to_uppercase())``
    transforms strings inside each policy's list explicitly. There is no
    automatic list shimming on this surface. Returned expressions retain the
    same dependency checks and engine identity as native expression methods.
    """

    __slots__ = ("_escape", "_namespace")

    def __init__(self, escape: PolarsNative, namespace: str) -> None:
        """Remember the escape and namespace whose methods are being reached."""
        self._escape = escape
        self._namespace = namespace

    def __getattr__(self, name: str) -> Callable[..., ExpressionProxy]:
        """Reach a public callable method; expression results are checked at mint."""
        from gaspatchio.column._dispatch_common import (  # noqa: PLC0415
            _get_proxy_base_expr,
        )

        if name.startswith("_"):
            msg = f"{name!r} is private; polars_native reaches public Polars methods."
            raise AttributeError(msg)
        owner = getattr(_get_proxy_base_expr(self._escape._receiver), self._namespace)  # noqa: SLF001 - paired escape surface
        actual = getattr(owner, name, None)
        if not callable(actual):
            msg = f"Polars namespace {self._namespace!r} has no method named {name!r}."
            raise AttributeError(msg)  # noqa: TRY004 - attribute lookup contract

        def call(*args: Any, **kwargs: Any) -> ExpressionProxy:  # noqa: ANN401
            """Build and record one namespace expression."""
            return self._escape._mint(name, args, kwargs, self._namespace)  # noqa: SLF001 - paired escape surface

        return call


class PolarsNativeString(_DocumentedPolarsStringMethods, PolarsNativeNamespace):
    """Polars string methods reached through the explicit engine escape.

    Scalar string operations act on each row. For a policy's list of strings,
    use ``polars_native().list.eval(pl.element().str.<method>(...))``.
    """

    __slots__ = ()


class PolarsNativeDate(_DocumentedPolarsDateTimeMethods, PolarsNativeNamespace):
    """Polars calendar fields reached through the explicit engine escape.

    Scalar dates expose their year, month and day. For dates inside each
    policy's list use an explicit ``polars_native().list.eval(...)``.
    """

    __slots__ = ()
