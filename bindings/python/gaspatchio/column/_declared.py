# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Execution and author-source errors for the declared proxy vocabulary."""

from __future__ import annotations

import inspect
import math
from functools import wraps
from typing import TYPE_CHECKING, Any, Final, NoReturn

from loguru import logger

from gaspatchio._source import display_filename
from gaspatchio.frame.calculations import capture_source_span
from gaspatchio.util import get_error_mode

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.operations import CoreCall
    from gaspatchio.column.condition_expression import ConditionExpression
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame


def _refuse_a_truth_value() -> NoReturn:
    """Refuse ``and``, ``or``, ``not`` and a bare ``if`` on a column.

    A column carries one answer per policy, and on a projection one per
    period as well. Python's Boolean keywords read a *single* true or false,
    so they cannot combine those: ``af.a and af.b`` evaluates ``af.a``,
    finds an object rather than a flag, and hands back ``af.b`` whole. The
    first test drops out of the model, every policy it excluded is carried
    anyway, and nothing raises -- the exported record even shows a
    well-formed one-column predicate, so the audit trail reads correctly
    while the number is wrong. Refusing here is what turns that into a line
    the author can fix.
    """
    msg = (
        "A column has no single true-or-false value -- it holds one answer per "
        "policy, and on a projection one per period -- so `and`, `or`, `not`, "
        "`if` and `assert` cannot read a truth value from it. Written that way "
        "the test silently collapses to one of its sides, and the policies the "
        "other side excluded are carried through the model. Combine the tests "
        "element by element instead, bracketing each comparison: "
        "(af.age > 60) & (af.sum_assured > 1000000) for and, | for or, ~ for "
        "not. For a value that depends on the test, write "
        "when(<test>).then(<value>).otherwise(<other value>)."
    )
    raise TypeError(msg)


def _refuse_an_exclusive_or() -> NoReturn:
    """Refuse ``^`` on a column, a comparison or a mask.

    The vocabulary's logical operations are ``&``, ``|`` and ``~`` (section
    11.1.27), and ``^`` is none of them. Python offers it to a column only
    as Polars' bitwise exclusive-or of whole numbers, which a model reading
    two tests does not mean, so it raised Python's own "unsupported operand
    type(s) for ^" on a column and Polars' words about a literal beside a
    lookup. The test it usually stands for -- one or the other, not both --
    is the two tests compared, which the vocabulary does hold.
    """
    msg = (
        "^ is not an operation in gaspatchio's vocabulary: the logical "
        "operations are & (and), | (or) and ~ (not). For one test or the "
        "other but not both, compare the two tests: (af.age > 60) != "
        "(af.sum_assured > 1000000), each in brackets, or af.smoker != "
        "af.rider for two stored flags. For the bitwise exclusive-or of whole "
        f"numbers, write af.<column>.polars_native().xor(...).{_ESCAPE_COST}"
    )
    raise TypeError(msg)


def _accessor_attribute(proxy: Any, name: str) -> Any:  # noqa: ANN401 -- any proxy, any accessor
    """Return the column accessor registered under ``name``, built once.

    A proxy's ``__getattr__``, for a column and an expression alike, so it
    runs only for a name the proxy does not hold itself. A name with no
    accessor registered is refused as an undeclared name, worded by
    :func:`_undeclared_name`. The accessor's constructor raises its own
    error, with a note naming the accessor it was building: rewrapped as an
    ``AttributeError`` it read to ``hasattr()`` as an accessor that does not
    exist, which hid the bug. An ``AttributeError`` the constructor raised
    itself is raised as a ``TypeError`` naming the accessor, from the
    original, for the same reason.
    """
    from gaspatchio.frame.registry import _ACCESSOR_REGISTRY  # noqa: PLC0415 -- cycle

    # object.__getattribute__, so a missing cache cannot recurse back here.
    cache = object.__getattribute__(proxy, "_dynamic_accessor_cache")
    if name in cache:
        return cache[name]
    accessor_class = _ACCESSOR_REGISTRY.get(name, {}).get("column")
    if accessor_class is None:
        raise AttributeError(_undeclared_name(name, proxy))
    try:
        accessor = accessor_class(proxy)
    except AttributeError as error:
        # hasattr() and getattr(..., default) would read this one as an
        # accessor that does not exist, so it is said as what it is.
        said = str(error).rstrip(".")
        msg = (
            f"The '{name}' column accessor could not be built: its constructor "
            f"raised AttributeError: {said}. Fix the constructor; the accessor "
            f"is registered."
        )
        raise TypeError(msg) from error
    except Exception as error:
        error.add_note(f"Raised while building the '{name}' column accessor.")
        raise
    cache[name] = accessor
    return accessor


def _names_with_accessors(proxy: object) -> list[str]:
    """Return what ``dir()`` lists for a proxy: its own names and the accessors.

    A proxy's ``__dir__``, for a column and an expression alike.
    """
    from gaspatchio.frame.registry import _ACCESSOR_REGISTRY  # noqa: PLC0415 -- cycle

    names = set(object.__dir__(proxy))
    names.update(
        name for name, kinds in _ACCESSOR_REGISTRY.items() if "column" in kinds
    )
    return sorted(names)


# Names held for an operation this release does not have, each with the
# answer to give in its place. A reserved name is refused in its own words
# rather than routed to the Polars door: the door names a method Polars does
# not have, and the reader asked for a calculation, not an engine method.
_RESERVED_NAMES: Final[dict[str, str]] = {
    "norm_inv": (
        "norm_inv is reserved for the inverse of the standard normal "
        "distribution function -- Excel's NORM.S.INV and NORM.INV -- and is "
        "not in 1.0: no workbook in evidence uses it, and an operation nothing "
        "writes is one nobody can check. For a constant fixed before the "
        "projection, such as the 99.5% point of a capital shock, compute it in "
        "setup with the standard library, statistics.NormalDist().inv_cdf(0.995), "
        "and use the number. The distribution function itself is .norm_cdf()."
    ),
}

# What the escape costs, said wherever a message advises it. The line runs, and
# its answer is right on Polars; what the reader is not told by the escape
# itself is that the record now marks it, and everything downstream of it, as
# one engine's own -- which only ``validate --engine`` would otherwise show.
_ESCAPE_COST: Final = (
    " A line written through .polars_native() records as engine_native: it "
    "runs only on Polars, and so does every calculation that reads it -- "
    "af.graph.tiers() (or gspio graph tiers) names the line, and gspio "
    "validate --engine jax names it and every calculation that reads it."
)

# Undeclared names whose calculation the vocabulary does declare under another
# spelling: the refusal names that spelling before the escape, since it records
# as the framework's own operations and runs on every engine.
_DECLARED_SPELLING: Final[dict[str, str]] = {
    "is_between": (
        "is_between is the two comparisons it stands for, which are declared: "
        "(af.<column> >= lower) & (af.<column> <= upper), both bounds included "
        "as Polars' default includes them."
    ),
}


def _undeclared_name(name: str, receiver: object) -> str:
    """Name the explicit engine door for a name the vocabulary does not hold.

    The door is ``polars_native()``, and for most names the Polars meaning
    behind it is the meaning the author wanted. For the handful whose
    meaning *is* the axis they run along it is not: Polars reads a
    per-period column as one value per policy, so the escape runs the
    calculation down the model points while the author is reading a
    timeline. Those names carry the axis and the per-period spelling beside
    the door, because a refusal that routes the reader into a wrong number
    is worse than no refusal at all.

    The names that fold, order or select among the rows (``DOWN_THE_ROWS``)
    say the same of a per-policy value on a frame with a projection
    timeline: through the door they answer each policy from the rows in the
    frame, which is portfolio-level work and only that -- and only the
    book's where the frame is the book, which a batch runner's batch and a
    scenario axis are not (``frame/_across_rows.py`` refuses it there). Of the
    folds whose per-period form the list namespace declares, the message
    names ``.list.<name>()`` too.
    """
    from gaspatchio._shape import frame_has_a_timeline  # noqa: PLC0415
    from gaspatchio.frame.lowering.methods import (  # noqa: PLC0415
        ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE,
        DOWN_THE_ROWS,
        FOLDS_WITH_A_PERIOD_FORM,
    )
    from gaspatchio.frame.lowering.value_reads import (  # noqa: PLC0415 -- cycle
        value_read_held_by,
    )

    reserved = _RESERVED_NAMES.get(name)
    if reserved is not None:
        return reserved
    read = value_read_held_by(receiver)
    if read is not None:
        # The door on the read itself puts the read inside a Polars
        # expression, which the frame refuses at the assignment: the move
        # that works is to store the read first and open the door there.
        message = (
            f"No '{name}' column accessor registered or declared operation "
            f"found. This value is {read.described()}, and written on the read "
            f"itself .polars_native().{name} would put the read inside a Polars "
            "expression the framework cannot see into, which the frame refuses: "
            "the model's fingerprint would not change when the table, curve or "
            "schedule did. Store the read as its own column first -- "
            "af.<column>_read = <the read> -- and write "
            f"af.<column>_read.polars_native().{name} on that column."
        )
    elif name in _DECLARED_SPELLING:
        message = (
            f"No '{name}' column accessor registered or declared operation "
            f"found. {_DECLARED_SPELLING[name]} For the Polars method itself, "
            f"write .polars_native().{name}."
        )
    else:
        message = (
            f"No '{name}' column accessor registered or declared operation "
            f"found. For a Polars method or namespace, write "
            f".polars_native().{name}."
        )
    # The cost comes straight after the door it prices, so the axis notes
    # below extend one sentence the shapes share rather than follow it.
    message += _ESCAPE_COST
    shape = getattr(receiver, "shape", None) if name in DOWN_THE_ROWS else None
    if shape == "scalar" and frame_has_a_timeline(getattr(receiver, "_parent", None)):
        message += (
            " On this value that runs down the model points: it holds one "
            "value per policy, and on a frame with a projection timeline the "
            f"rows are policies, so .polars_native().{name} answers each policy "
            "from the rows in the frame -- in a batch runner, the batch; on a "
            "scenario axis, every scenario -- a number that changes with which "
            "other policies share the run, and so it is refused there. Write it "
            "only where a figure across the model points is what is meant, and "
            "only where the frame is the whole book; otherwise compute the "
            "figure before the run, as a model-point column the model reads, or "
            "run the book in one batch."
        )
        if name in FOLDS_WITH_A_PERIOD_FORM:
            message += (
                " For one policy's own periods, apply the per-period fold, "
                f".list.{name}(), to a value with one entry per period."
            )
    elif shape == "list" and name in FOLDS_WITH_A_PERIOD_FORM:
        message += (
            " This value holds one entry per projection period; for the fold "
            f"over each policy's own periods, write .list.{name}()."
        )
    if (
        name in ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE
        and getattr(receiver, "shape", None) == "list"
    ):
        message += (
            " On this column that is not the same calculation: it holds one "
            f"value per projection period, and .polars_native().{name} runs "
            "down the model points, moving values between policies rather than "
            "between periods. For the per-period form, evaluate it inside each "
            "policy's own list -- "
            f".polars_native().list.eval(pl.element().{name}(...))."
        )
    return message


# The forms each operation is declared in, where its signature -- the
# engine's own, kept so that a call binds as it always did -- admits a call
# the declaration then declines. Printing the signature there named
# ``fill_nan(value: object | None)`` as the form ``fill_nan(None)`` broke.
_DECLARED_FORMS: Final[dict[str, str]] = {
    "fill_nan": (
        "fill_nan(value), the value a number -- fill_nan(0.0) -- or a column "
        "or expression, fill_nan(af.default_rate)"
    ),
    "fill_null": (
        "fill_null(value), the value a number, text, flag or date of the "
        "column's own kind, or a column or expression -- fill_null(0.0), "
        "fill_null(af.default_premium)"
    ),
    "replace": (
        "replace({old: new, ...}), replace([old, ...], [new, ...]), "
        "replace([old, ...], new) or replace(old, new), each value a number, "
        "text or flag"
    ),
    "clip": (
        "clip(lower_bound), clip(upper_bound=...) or clip(lower_bound, "
        "upper_bound), at least one bound, each a value or a column"
    ),
    "cut": (
        "cut(breaks) or cut(breaks, labels=[...]), the breaks a list of "
        "numbers rising along the line and the labels one text per interval, "
        "with left_closed= and include_breaks= as True or False"
    ),
    "round": (
        "round(decimals), the decimals a whole number, with "
        "mode='half_to_even' (the default) or mode='half_away_from_zero'"
    ),
    "round_sig_figs": (
        "round_sig_figs(digits), the digits a whole number of at least one -- "
        "the count of leading figures kept"
    ),
}

# A form that is refused for a reason of its own, with what to write instead.
# The escape that writes the null depends on the column's shape: Polars'
# fill_nan reads a per-policy value, and on a column holding one list per
# policy it fails at collect ("is_not_nan ... not supported for dtype
# list[f64]"), where the per-period form evaluates it inside each list.
_NAN_TO_NULL_ESCAPE: Final[dict[str | None, str]] = {
    "scalar": "af.<column>.polars_native().fill_nan(None)",
    "list": (
        "af.<column>.polars_native().list.eval(pl.element().fill_nan(None)), "
        "the per-period form: this column holds one value per projection "
        "period, and the plain .polars_native().fill_nan(None) does not reach "
        "inside each policy's list"
    ),
    None: (
        "af.<column>.polars_native().fill_nan(None) on a column holding one "
        "value per policy, or af.<column>.polars_native().list.eval("
        "pl.element().fill_nan(None)) on one holding a value per projection "
        "period"
    ),
}


def _nan_to_null(receiver: object | None) -> str:
    """Say why ``fill_nan(None)`` is refused, and the escape that works here."""
    shape = getattr(receiver, "shape", None)
    escape = _NAN_TO_NULL_ESCAPE.get(shape, _NAN_TO_NULL_ESCAPE[None])
    return (
        " fill_nan(None) would turn a NaN into a missing value, and the "
        "vocabulary declares no fill that writes one: fill with "
        "the number the model means there. If a null is what is meant, write "
        f"{escape}.{_ESCAPE_COST}"
    )


def _a_nan_filled_with_null(
    name: str, args: tuple[object, ...], kwargs: dict[str, object]
) -> bool:
    """Report whether a call is ``fill_nan(None)``, positionally or by keyword."""
    if name != "fill_nan":
        return False
    written = args[0] if args else kwargs.get("value", ...)
    return written is None


def _a_non_finite_argument(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> float | None:
    """Return the first NaN or infinity written as an argument or a member of one."""
    for value in (*args, *kwargs.values()):
        members = value if isinstance(value, (list, tuple)) else (value,)
        for member in members:
            if isinstance(member, float) and not math.isfinite(member):
                return member
    return None


def _a_non_finite_argument_refused(name: str, value: float) -> str:
    """Name the NaN or infinity an argument holds, and the move that works.

    The tree holds no non-finite literal, so the call declines. The form of
    the arguments is not what is wrong, so a signature mismatch's words
    would send the reader to the wrong fix. A membership set gets its own
    move: a NaN is a member of no set (11.1.5), so the question the author
    meant is asked of the value with ``is_nan`` beside the set.
    """
    from gaspatchio._semantic.ir import non_finite_literal_message  # noqa: PLC0415

    if name != "is_in":
        return non_finite_literal_message(value, f" in {name}()")
    if math.isnan(value):
        return (
            "is_in's set holds a NaN, and a set cannot hold one: membership "
            "is equality, and a NaN equals nothing, itself included, so a "
            "NaN is a member of no set and is_in of a NaN answers false. "
            "To ask whether a value is a NaN, ask it beside the set: "
            "af.<column>.is_in([...]) | af.<column>.is_nan()."
        )
    sign = ">" if value > 0 else "<"
    return (
        f"is_in's set holds {value!r}, and an infinity is not a formula "
        "literal. To ask whether a value is that infinity, ask it beside "
        "the set: af.<column>.is_in([...]) | (af.<column>.is_infinite() & "
        f"(af.<column> {sign} 0))."
    )


def _unsupported_method_form(
    name: str,
    receiver: object | None = None,
    args: tuple[object, ...] = (),
    kwargs: dict[str, object] | None = None,
) -> str:
    """Explain the declared forms and the explicit door for any other form."""
    from gaspatchio._semantic.operations import (  # noqa: PLC0415
        PROXY_NAMESPACE_OPERATIONS,
        PROXY_OPERATIONS,
        PROXY_OPERATORS,
    )
    from gaspatchio.frame.lowering.methods import ALONG_THE_PERIOD_AXIS  # noqa: PLC0415

    if (
        receiver is not None
        and name in ALONG_THE_PERIOD_AXIS
        and getattr(receiver, "shape", None) != "list"
    ):
        return (
            f"{name} folds projection periods within each policy and needs a "
            "list column. This receiver has no known period axis. To fold "
            "across model-point rows, write "
            f"af.<column>.polars_native().{name}(...).{_ESCAPE_COST}"
        )
    if (
        receiver is not None
        and name.startswith("list.")
        and getattr(receiver, "shape", None) != "list"
    ):
        # The namespace declines a receiver with no period axis before it
        # looks at the arguments, so the arguments are not what is wrong.
        held = (
            "holds one value per policy"
            if getattr(receiver, "shape", None) == "scalar"
            else "has no known period axis"
        )
        return (
            f"{name} reads within each policy's own projection periods and "
            f"needs a list column; this receiver {held}, so there is no "
            "period to read. Apply it to the per-period column it was meant "
            "to read; for the Polars form on a column that holds lists as "
            f"values, write af.<column>.polars_native().{name}(...).{_ESCAPE_COST}"
        )
    non_finite = _a_non_finite_argument(args, kwargs or {})
    if non_finite is not None:
        return _a_non_finite_argument_refused(name, non_finite)
    forms = _DECLARED_FORMS.get(name)
    if forms is not None:
        message = (
            f"{name}() is declared as {forms}, and the arguments supplied do "
            "not match any of these forms."
        )
        if _a_nan_filled_with_null(name, args, kwargs or {}):
            return message + _nan_to_null(receiver)
        return (
            f"{message} For a Polars-specific form, write "
            f"af.<column>.polars_native().{name}(...).{_ESCAPE_COST}"
        )
    if name in PROXY_OPERATORS:
        accepted = PROXY_OPERATORS[name].signature
    elif "." in name:
        namespace, method = name.split(".", 1)
        operation = next(
            item
            for item in PROXY_NAMESPACE_OPERATIONS[namespace]
            if item.identifier.rsplit(".", 1)[-1] == method
        )
        accepted = operation.surface_signature()
    else:
        accepted = PROXY_OPERATIONS[name].surface_signature()
    return (
        f"{name}{accepted} is the gaspatchio form of this operation, and the "
        "arguments supplied do not match it. For a Polars-specific form, "
        f"write af.<column>.polars_native().{name}(...).{_ESCAPE_COST}"
    )


def _refuse_unsupported_form[**P, R](
    name: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retain exact signatures and name the explicit door for rejected forms."""

    def decorate(method: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(method)

        @wraps(method)
        def checked(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                try:
                    signature.bind(*args, **kwargs)
                except TypeError as error:
                    raise TypeError(_unsupported_method_form(name)) from error
                return method(*args, **kwargs)
            except Exception as error:
                if get_error_mode() == "off":
                    raise
                receiver = args[0] if args else kwargs.get("self")
                receiver = getattr(receiver, "_parent_proxy", receiver)
                raise ErrorEnhancer(receiver).enhance_method_error(
                    error, name, engine_specific=False
                ) from error

        return checked

    return decorate


class ErrorEnhancer:
    """Centralized error handling and enhancement."""

    def __init__(self, self_proxy: object) -> None:
        self.proxy = self_proxy
        self.parent_af = getattr(self_proxy, "_parent", None)
        # `_traced_run` is the traced-run flag: the model function was
        # routed through the trace decorator by `--mode debug`, which is
        # when the user has asked to be told where in their own source a
        # failing method call came from. Reading the source costs a stack
        # walk per failure, so the default path does not pay it.
        traced = getattr(self.parent_af, "_traced_run", False)
        self.is_traced_run = bool(self.parent_af and traced)

    def enhance_method_error(
        self, e: Exception, method_name: str, *, engine_specific: bool = True
    ) -> Exception:
        """Enhance an error with proxy context information.

        Decorating an exception that is already in flight is the worst place
        in the framework to throw: whatever this method raises replaces the
        failure the model author actually needs to read. So every step below
        that could fail degrades to the un-enriched message instead. That
        includes the source location, which is absent whenever capture
        returns nothing -- an unresolvable frame, or a run with
        ``GASPATCHIO_SOURCE_SPANS=off``. That switch costs far more than this
        one line: it also nulls the as-written ``formula`` and the
        ``source_location`` on every computed node of an exported calculation
        graph, so turning it off costs that graph its whole audit surface and
        not only a location.
        """
        surface = "proxied Polars" if engine_specific else "gaspatchio"
        error_msg = f"Error calling {surface} method '{method_name}': {e}"

        if self.is_traced_run:
            error_msg += self._source_location()

        new_error = type(e)(error_msg)
        proxy_info = {
            "proxy_type": type(self.proxy).__name__,
            "method": method_name,
            "column": getattr(self.proxy, "name", None),
        }
        setattr(new_error, "proxy_info", proxy_info)  # noqa: B010
        setattr(new_error, "_dispatch_enhanced", True)  # noqa: B010
        return new_error

    def _source_location(self) -> str:
        """Return the lines naming where the failing call was written.

        The empty string whenever there is nothing truthful to say. The span
        comes from ``capture_source_span``, which walks past every frame the
        framework itself contributes -- the method wrapper, the caller, this
        class -- and resolves the first frame outside them to the statement
        it is executing. That is the model author's own line: the assignment
        that called the method, whole, rather than whichever physical line
        the interpreter happened to be on inside the framework.
        """
        try:
            span = capture_source_span()
            if span is None:
                return ""
            location = f"\n  Called from: {display_filename(span.file)}:{span.line}"
            if span.function is not None:
                location += f"\n  Function: {span.function}"
        except Exception as exc:  # noqa: BLE001 -- must not replace the error in flight
            logger.trace(f"Source capture failed for error enrichment ({exc!r})")
            return ""
        return f"{location}\n  Source: {span.statement}"


def _operator_coverage(
    name: str,
    receiver: object,
    a: tuple[Any, ...],
    kw: dict[str, Any],
) -> str | None:
    """Name a covered operator without registering any engine operands."""
    from gaspatchio._semantic.operations import PROXY_OPERATORS  # noqa: PLC0415
    from gaspatchio.frame.lowering.methods import _is_operand  # noqa: PLC0415

    logical_alias = {"and_": "__and__", "or_": "__or__", "not_": "__invert__"}.get(name)
    if logical_alias is not None:
        expected = 0 if name == "not_" else 1
        parent = getattr(receiver, "_parent", None)
        if (
            kw
            or len(a) != expected
            or not all(_is_logical_operand(value, parent) for value in (receiver, *a))
        ):
            return None
    spelling = PROXY_OPERATORS.get(logical_alias or name)
    if spelling is None:
        return None
    try:
        bound = spelling.signature.bind(*a, **kw)
    except TypeError:
        return None
    if not all(_is_operand(value) for value in bound.arguments.values()):
        return None
    if spelling.operation is not None:
        return spelling.operation.identifier
    return (
        "abs"
        if spelling.unary == "absolute"
        else "mul"
        if spelling.unary == "negative"
        else "not_"
    )


def _core_call_node(
    name: str,
    self_proxy: object,
    a: tuple[Any, ...],
    kw: dict[str, Any],
) -> CoreCall | None:
    """Return the core operation this method call means, or ``None``.

    Which operation a method name and its arguments mean lives in
    ``frame/lowering/methods.py``; what this adds is the receiver, which at
    this door is the proxy the method was reached on and therefore the node
    it already carries. Resolving it here rather than lowering it first is
    what keeps a bounded duration a bounded duration in the record instead
    of an engine fragment holding one.

    One question that module cannot answer for itself is settled here: an
    accumulation means the axis it folds along, and only a frame can say
    which axis a value has. A fold along a projection's periods is the
    operation the vocabulary names; the same method name on a per-policy
    column runs down the model points instead, which is a different
    calculation, so it is declined. The generated surface refuses it and
    names the explicit engine escape for a row accumulation. The
    shape is resolved only for the names that turn on it, since resolving
    one costs a schema read and every other name here is indifferent to it.
    """
    from gaspatchio.frame.lowering.ingress import to_node  # noqa: PLC0415 -- cycle
    from gaspatchio.frame.lowering.methods import (  # noqa: PLC0415 -- cycle
        ALONG_THE_PERIOD_AXIS,
        core_call,
        core_list_call,
        core_string_call,
    )

    if name.startswith("str."):
        return core_string_call(name[4:], to_node(self_proxy), a, kw)
    if name.startswith("list."):
        if getattr(self_proxy, "shape", None) != "list":
            return None
        return core_list_call(name[5:], to_node(self_proxy), a, kw)
    if name in ALONG_THE_PERIOD_AXIS and getattr(self_proxy, "shape", None) != "list":
        return None
    return core_call(name, to_node(self_proxy), a, kw)


def _call_declared_method(
    name: str,
    self_proxy: object,
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> ExpressionProxy:
    """Emit one generated method, refusing any form its declaration declines.

    A membership test is a comparison with each member, so against a column
    still wider than ``i64`` it admits a member past ``i64`` as a comparison
    does (``compared_against_a_wide_column``).
    """
    if name == "is_in" and _a_wide_receiver(self_proxy):
        from gaspatchio.frame.lowering.ingress import (  # noqa: PLC0415 -- cycle
            compared_against_a_wide_column,
        )

        with compared_against_a_wide_column():
            core = _core_call_node(name, self_proxy, args, kwargs)
    else:
        core = _core_call_node(name, self_proxy, args, kwargs)
    if core is None:
        raise TypeError(_unsupported_method_form(name, self_proxy, args, kwargs))

    from gaspatchio._authoring import emit  # noqa: PLC0415 -- import cycle

    parent_af = getattr(self_proxy, "_parent", None)
    return emit.call(core.name, core.args, parent_af, core.attrs)


def _a_wide_receiver(self_proxy: object) -> bool:
    """Say whether a method's receiver is a column still wider than ``i64``."""
    from gaspatchio._authoring.emit import is_a_column_wider_than_i64  # noqa: PLC0415
    from gaspatchio.frame.lowering.ingress import to_node  # noqa: PLC0415 -- cycle

    return is_a_column_wider_than_i64(
        to_node(self_proxy), getattr(self_proxy, "_parent", None)
    )


def _call_declared_comparison(
    name: str,
    receiver: object,
    other: object,
) -> ConditionExpression:
    """Emit the same predicate for a named comparison and its operator spelling."""
    from gaspatchio._authoring import emit  # noqa: PLC0415
    from gaspatchio._semantic.operations import PROXY_OPERATORS  # noqa: PLC0415

    operation = PROXY_OPERATORS[name].operation
    if operation is None:
        msg = f"{name} is not a binary comparison"
        raise ValueError(msg)
    return emit.comparison(
        operation.identifier, receiver, other, getattr(receiver, "_parent", None)
    )


def _is_boolean_operand(
    value: object,
    parent: ActuarialFrame | None = None,
) -> bool:
    """Recognise Boolean values and stamped predicates without guessing flags."""
    from gaspatchio.column.condition_expression import (  # noqa: PLC0415
        ConditionExpression,
    )
    from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

    if isinstance(value, (bool, ConditionExpression)):
        return True
    if isinstance(value, ExpressionProxy) and value.kind in {
        "comparison",
        "boolean_mask",
    }:
        return True
    # A comparison or mask a lookup, a schedule or a rollforward read hands
    # back per policy is a Polars expression marked with its kind, so a test
    # over a value whose type is read only when the frame runs is still one.
    if getattr(value, "_kind_explicit", None) in {"comparison", "boolean_mask"}:
        return True
    return _boolean_by_type(value, parent)


def _boolean_by_type(value: object, parent: ActuarialFrame | None = None) -> bool:
    """Say whether a column or expression is typed Boolean, per policy or per period."""
    import polars as pl  # noqa: PLC0415

    from gaspatchio.column.column_proxy import ColumnProxy  # noqa: PLC0415
    from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

    if isinstance(value, ExpressionProxy):
        parent = getattr(value, "_parent", parent)
        value = value._expr  # noqa: SLF001 - operand ingress
    if isinstance(value, pl.Expr):
        from gaspatchio._shape import _resolve_expr_output_dtype  # noqa: PLC0415

        dtype = _resolve_expr_output_dtype(parent, value)
        return dtype == pl.Boolean or dtype == pl.List(pl.Boolean)
    if isinstance(value, ColumnProxy):
        parent = getattr(value, "_parent", None)
        dtype = (getattr(parent, "_schema", None) or {}).get(value.name)
        return dtype == pl.Boolean or dtype == pl.List(pl.Boolean)
    return False


def _is_stored_numeric_predicate(
    value: object,
    parent: ActuarialFrame | None = None,
) -> bool:
    """Recognise a direct reference to a stored floating-point column.

    Such a column is the flag the model stored, so ``&``, ``|`` and ``~``
    read it (§11.1.27) under the checked exact 0/1 contract a ``when`` condition
    already applies (§11.1.18) -- the check itself runs at evaluation, in
    the lowering. Only a bare column reference qualifies: an integer column,
    a literal number and an arithmetic result are not stored predicates and
    are still refused while the formula is written.
    """
    import polars as pl  # noqa: PLC0415

    from gaspatchio._semantic.ir import Col  # noqa: PLC0415
    from gaspatchio.column.column_proxy import ColumnProxy  # noqa: PLC0415
    from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

    if not isinstance(value, (ColumnProxy, ExpressionProxy)):
        return False
    node = value._node  # noqa: SLF001 - operand ingress
    if not isinstance(node, Col):
        return False
    parent = getattr(value, "_parent", None) or parent
    dtype = (getattr(parent, "_schema", None) or {}).get(node.name)
    if isinstance(dtype, pl.List):
        dtype = dtype.inner
    return dtype is not None and dtype.is_float()


def _is_logical_operand(
    value: object,
    parent: ActuarialFrame | None = None,
) -> bool:
    """Return whether ``&``, ``|`` and ``~`` take ``value`` as an operand."""
    return _is_boolean_operand(value, parent) or _is_stored_numeric_predicate(
        value, parent
    )


def _call_declared_operator(
    name: str,
    receiver: object,
    other: object = None,
) -> ExpressionProxy:
    """Emit a declared operator using the existing semantic node vocabulary."""
    from gaspatchio._authoring import emit  # noqa: PLC0415
    from gaspatchio._semantic.operations import PROXY_OPERATORS  # noqa: PLC0415

    spelling = PROXY_OPERATORS[name]
    operation = spelling.operation
    parent = getattr(receiver, "_parent", None)
    logical = spelling.unary == "not" or (
        operation is not None and operation.family == "logical"
    )
    if logical and (
        not _is_logical_operand(receiver, parent)
        or (operation is not None and not _is_logical_operand(other, parent))
    ):
        msg = (
            f"{name} combines Boolean values, predicate masks, or a stored "
            "0.0/1.0 Float64 column. Compare numeric flags explicitly "
            "(af.flag == 1). For integer bit operations use "
            f"polars_native().and_(...), .or_(...), or .not_().{_ESCAPE_COST}"
        )
        raise TypeError(msg)
    if operation is not None:
        left, right = (other, receiver) if spelling.reflected else (receiver, other)
        return emit.binary(
            operation.identifier,
            left,
            right,
            parent,
            kind="boolean_mask" if logical else None,
        )
    if spelling.unary == "absolute":
        return emit.call("abs", (receiver,), parent)
    if spelling.unary == "negative":
        # Integer -1 preserves integer list dtypes; -1.0 silently widens them.
        return emit.binary("mul", receiver, -1, parent)
    return emit.call("not_", (receiver,), parent, kind="boolean_mask")
