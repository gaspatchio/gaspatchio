# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Base classes for ActuarialFrame accessors."""

from abc import ABC
from difflib import get_close_matches
from typing import TYPE_CHECKING, Final, NoReturn

import polars as pl

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode

    # Updated imports to point to new locations
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame  # Adjusted path

# How many of the frame's own column names a refusal lists before it stops
# and says how many more there are.
_NAMES_IN_REFUSAL: Final[int] = 8

# What the value half of an operand refusal offers when the parameter takes
# the ordinary spread of value forms. A parameter that takes something
# narrower passes its own phrase instead, so the message stays true of the
# argument it names rather than sending the actuary to a remedy that fails
# on the next line.
_VALUE_FORMS: Final[str] = "a number or a datetime.date"


def column_expr(
    frame: "ActuarialFrame",
    designator: "str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series",
    *,
    parameter: str,
) -> pl.Expr:
    """Resolve a frame-level column designator, a bare string being a NAME.

    The frame-level half of the rule the accessors share: at frame level a
    string names a column on ``frame``, so it is checked and turned into a
    reference to it -- the way ``rename``, ``drop`` and
    ``projection.set(issue_age_column=...)`` already read one. Everything
    else -- a proxy, an expression, a Series -- goes through the frame's own
    conversion unchanged.

    The check is what makes the string safe to accept. Without it the name
    falls through to the generic conversion, becomes ``pl.lit("issue_date")``,
    and the model fails much later with a Polars type error about a String
    where a Date or a number was wanted.

    Args:
        frame: The frame the name is resolved against.
        designator: A column name, or the column/expression itself.
        parameter: The parameter's name, so a refusal names the argument the
            caller actually wrote.

    Returns:
        A Polars expression for the designated column.

    Raises:
        pl.exceptions.ColumnNotFoundError: If ``designator`` is a string the
            frame does not carry.

    """
    if isinstance(designator, str):
        if designator not in frame.columns:
            refuse_missing_column(frame, parameter=parameter, name=designator)

        from gaspatchio.frame.lowering.columns import (  # noqa: PLC0415 -- frame imports this accessor base
            column_reference,
        )

        return column_reference(designator)
    return frame._convert_to_expr(designator)  # noqa: SLF001 -- the caller's own frame


def column_node(
    frame: "ActuarialFrame",
    designator: "str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series",
    *,
    parameter: str,
) -> "OpNode":
    """Resolve the same designator to the op-tree node that stands for it.

    ``column_expr`` one step earlier, for a frame verb that *builds a node*
    rather than an expression. A frame-level string is the name of a column,
    and what an operation's tree records for a column is a reference to it.
    Lowering the name to the engine's own rendering first and handing that
    over made the operand an engine fragment, so an offset written as
    ``af.date.add_duration("issue_date", "1y")`` -- an operation the
    artifact format's own vocabulary names -- exported as an engine escape.
    The only engine-bound thing in the calculation was the framework's own
    wrap of a name the actuary had given it.

    An operand that is not a name goes through ``column_expr`` unchanged,
    for the frame-side work that call does -- materialising the hidden
    struct column a rollforward extraction reads. What is *recorded* for it
    is then whatever it is: a proxy carries the tree it was built from, and
    a raw expression is an engine fragment and is declared as one.

    Args:
        frame: The frame the name is resolved against.
        designator: A column name, or the column/expression itself.
        parameter: The parameter's name, so a refusal names the argument the
            caller actually wrote.

    Returns:
        The node an operation's tree records this operand as.

    Raises:
        pl.exceptions.ColumnNotFoundError: If ``designator`` is a string the
            frame does not carry.

    """
    from gaspatchio._semantic.ir import Col  # noqa: PLC0415 -- import cycle
    from gaspatchio.frame.lowering.ingress import to_node  # noqa: PLC0415 -- cycle

    if isinstance(designator, str):
        if designator not in frame.columns:
            refuse_missing_column(frame, parameter=parameter, name=designator)
        return Col(designator)
    expr = column_expr(frame, designator, parameter=parameter)
    # A proxy already holds its own tree, and the expression above is that
    # tree lowered -- so the tree is what goes over, and the conversion is
    # kept for the frame-side work it did rather than for its answer.
    if getattr(designator, "_node", None) is not None:
        return to_node(designator)
    return to_node(expr)


def refuse_missing_column(
    frame: "ActuarialFrame", *, parameter: str, name: str
) -> NoReturn:
    """Refuse a column name ``frame`` does not carry, and say what it does.

    A misspelled column name is the mistake this catches, so the nearest
    names the frame actually holds are the useful next move -- and when
    nothing is near, the columns themselves are.

    Args:
        frame: The frame whose columns the refusal reports.
        parameter: The parameter's name, so the message names the argument
            the caller actually wrote.
        name: The name that is not on the frame.

    Raises:
        pl.exceptions.ColumnNotFoundError: Always.

    """
    known = list(frame.columns)
    near = get_close_matches(name, known, n=3, cutoff=0.6)
    if near:
        suggestion = "Did you mean " + ", ".join(repr(n) for n in near) + "?"
    elif len(known) <= _NAMES_IN_REFUSAL:
        suggestion = f"The frame holds: {', '.join(known)}."
    else:
        listed = ", ".join(known[:_NAMES_IN_REFUSAL])
        suggestion = (
            f"The frame holds {len(known)} columns, among them: {listed}, "
            f"and {len(known) - _NAMES_IN_REFUSAL} more."
        )
    msg = f"{parameter}={name!r} names a column this frame does not carry. {suggestion}"
    raise pl.exceptions.ColumnNotFoundError(msg)


def refuse_bare_string_operand(
    value: object, *, parameter: str, value_hint: str | None = None
) -> None:
    """Refuse a bare string where an operand belongs, naming both spellings.

    **On a column accessor -- excel, date, finance, projection -- a bare
    string operand is refused: write the operand as ``af.column`` or
    ``af["column"]``.** A string names a column at *frame* level, and
    only there: ``rename``, ``drop``,
    ``projection.set(issue_age_column=...)``,
    ``af.date.create_timeline``, ``af.date.add_duration("issue_date",
    "1y")``, ``af.finance.present_value``. The other half of a
    column-level formula is not a name:
    ``af.issue_date.excel.edate("months")`` could mean the ``months``
    column or the literal text, and the framework has no way to know
    which. It used to guess -- the string became a literal, the
    arithmetic ran against text, and the column came back full of nulls
    that surfaced pages later as a reserve nobody could trace. It is
    refused at the call instead.

    This docstring is where that rule is stated; the accessors point here
    rather than each restating it.

    Args:
        value: The operand as the caller passed it. Anything that is not a
            ``str`` passes through untouched.
        parameter: The parameter's name, so the message names the argument
            the caller actually wrote.
        value_hint: What the value half of the message offers, for a
            parameter that takes something narrower than the usual number
            or date. A discount *factor* is one value per period, so
            offering it a number would send the actuary to a remedy the
            very next check refuses.

    Raises:
        TypeError: If ``value`` is a ``str``.

    """
    if not isinstance(value, str):
        return
    column = f'af["{value}"]'
    attribute = f" (or af.{value})" if value.isidentifier() else ""
    msg = (
        f"{parameter}={value!r} is a bare string, which could be a column "
        f"name or a value. For the column, pass {column}{attribute}; for a "
        f"value, pass {value_hint or _VALUE_FORMS}. Naming a column by "
        "string is the frame-level idiom (af.date.add_duration("
        "'issue_date', '1y')); on a column accessor it is the operand, and "
        "the framework cannot tell a name from a value there."
    )
    raise TypeError(msg)


def refuse_bare_string_override(value: object, *, parameter: str) -> None:
    """Refuse a bare string where a period override belongs.

    ``with_period`` and ``with_periods`` fall under the same rule as
    ``refuse_bare_string_operand`` -- a column-level argument is never a
    column name -- but half of that message's remedy would be false here,
    so they have their own. An override replaces one period's value with
    one number; a column is a whole timeline, and splicing one into a
    single period is not an operation these two verbs have. A replacement
    that varies by policy is a conditional, and that is what this message
    points at instead.

    Args:
        value: The override as the caller passed it. Anything that is not
            a ``str`` passes through untouched.
        parameter: The parameter's name -- ``value``, or ``updates[3]``
            for one entry of a multi-period override -- so the message
            names the argument the caller actually wrote.

    Raises:
        TypeError: If ``value`` is a ``str``.

    """
    if not isinstance(value, str):
        return
    msg = (
        f"{parameter}={value!r} is a bare string, and an override is a "
        "number: pass an int or a float. A column cannot be an override "
        "here -- an override replaces one period's value with a single "
        "number. When the replacement is itself a column, write the "
        "conditional that says so: when(af.month == 3).then(af.other)"
        ".otherwise(af.premium)."
    )
    raise TypeError(msg)


class BaseFrameAccessor(ABC):  # noqa: B024 -- abstract only for register()
    """Base class for Frame-level accessors.

    Provides a structure for accessors that operate on the entire
    ActuarialFrame. Subclasses should implement domain-specific methods.
    The constructor below binds the frame, so a subclass that only adds
    methods needs none of its own; one that does define its own calls
    ``super().__init__(frame)``.

    It is an ``ABC`` with no abstract methods so that a class can be
    registered as a virtual subclass with ``BaseFrameAccessor.register``,
    which is how the graph accessor passes the registry's check.
    """

    def __init__(self, frame: "ActuarialFrame") -> None:
        """Initialize the accessor with the parent frame.

        Args:
            frame: The ActuarialFrame instance this accessor is bound to.

        """
        self._frame = frame


class BaseColumnAccessor(ABC):  # noqa: B024 -- abstract only for register()
    """Base class for Column/Expression-level accessors.

    Provides a structure for accessors that operate on a specific
    column or expression within an ActuarialFrame. Subclasses should
    implement domain-specific methods operating on `self._proxy`.
    The constructor below binds the proxy, so a subclass that only adds
    methods needs none of its own; one that does define its own calls
    ``super().__init__(proxy)``.

    It is an ``ABC`` with no abstract methods for the reason
    ``BaseFrameAccessor`` is: a class can be registered as a virtual
    subclass of it.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None:
        """Initialize the accessor with the parent proxy object.

        Args:
            proxy: The ColumnProxy or ExpressionProxy instance this
                   accessor is bound to -- the only two kinds of object a
                   column accessor is ever built on.

        """
        self._proxy = proxy


# The bases a custom accessor subclasses, as the extending skill documents them.
__all__ = ["BaseColumnAccessor", "BaseFrameAccessor"]
