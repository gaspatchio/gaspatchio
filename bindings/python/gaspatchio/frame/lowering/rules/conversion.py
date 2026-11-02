# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Checked conversion between the value types this vocabulary names.

One named door per type rather than one generic cast. A cast taking a type
argument puts the conversions that lose nothing behind the same identifier as
the ones that lose digits, and a reader of the trace then has to know the pair
of types before they know whether anything was given up. Each door here states
what it accepts, what it answers and what it refuses, so the node a reviewer
reads off the trace means one thing.

The accepted set is written in *storage* widths rather than in the artifact's
six names, because a column arrives in the width the warehouse wrote it in and
the artifact's name for it is the thing being computed, not a precondition. An
``Int8`` duration and an ``Int64`` one are one type as far as ``to_integer`` is
concerned, and a ``UInt64`` policy number is an integer whose digits
``to_text`` keeps -- which is the door the export's own refusal now sends an
author to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio._semantic.ir import Col
from gaspatchio.frame.lowering._polars.validation import (
    checked_float_refusal,
    checked_integer_refusal,
    integer_range_refusal,
    require_valid_rows,
)
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering
from gaspatchio.frame.lowering.rules import _SPEC_PATH, _counted

if TYPE_CHECKING:
    from polars.datatypes import DataTypeClass

    from gaspatchio._semantic.ir import Call, OpNode
    from gaspatchio.frame.lowering.context import LoweringContext

_I64_MIN_AS_F64 = float(-(2**63))
_I64_UPPER_EXCLUSIVE_AS_F64 = float(2**63)

# Where an integer stops having an ``i64`` name for itself. The half-open
# float interval above is the same boundary asked of a double, which cannot
# name 2**63 - 1 and so is asked for the interval rather than the endpoint.
_I64_MIN: Final[int] = -(2**63)
_I64_MAX: Final[int] = 2**63 - 1

# Where a double stops naming every whole number: above 2**53 the doubles are
# further apart than one, so two neighbouring integers share a double and a
# conversion that went through would hand one number's value to another.
_EXACT_IN_F64: Final[int] = 2**53

# The integer widths that can hold a number no ``i64`` carries. Everything
# narrower fits by construction and is not asked.
_WIDER_THAN_I64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.UInt64, pl.Int128, pl.UInt128}
)

# The types whose text is the value itself rather than a rendering decision:
# a boolean prints true or false, a date prints its ISO calendar day, a
# category is a string with a dictionary in front of it, and text is already
# text. Numbers join them by predicate, so a width polars adds later is
# carried without this set having to learn its name.
# The scalar types section 10 names. An array of one of these has a list
# this vocabulary can already describe; an array of anything else has a
# shape with no element type to put inside it.
_NAMED_ELEMENTS: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Boolean, pl.String, pl.Date, pl.Datetime}
)

_TEXT_READY: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Boolean, pl.String, pl.Date, pl.Datetime, pl.Categorical, pl.Enum}
)

_INTEGER_SIGNATURE: Final = f"§11.1.23 of {_SPEC_PATH} states the signature."
_FLOAT_SIGNATURE: Final = f"§11.1.38 of {_SPEC_PATH} states the signature."
_TEXT_SIGNATURE: Final = f"§11.1.39 of {_SPEC_PATH} states the signature."
_LIST_SIGNATURE: Final = f"§11.1.40 of {_SPEC_PATH} states the signature."

_NO_INTEGER_ATTRIBUTE: Final = (
    "the conversion is exact or it refuses, so there is no truncating, "
    "saturating, wrapping or nullable form for an attribute to select. Drop "
    "it, and round the value first if rounding is what the calculation means."
)
_NO_FLOAT_ATTRIBUTE: Final = (
    "the conversion is exact or it refuses, so there is no rounding, "
    "nearest-double or saturating form for an attribute to select. Drop it, "
    "and say what the value should become before the conversion if a number "
    "too large for a double has to travel as one."
)
_NO_LIST_ATTRIBUTE: Final = (
    "an array is already the shape a list describes, so there is no length, "
    "padding or truncating form for an attribute to select. Drop it."
)
_NO_TEXT_ATTRIBUTE: Final = (
    "the text is the value and nothing else, so there is no format, locale, "
    "padding or separator for an attribute to select. Drop it, and build the "
    "wording you want from the text this answers."
)


def _signature_refusal(
    node: Call, *, name: str, operand: str, no_attribute: str, clause: str
) -> str:
    """Say which half of a one-operand conversion's signature this node missed.

    Operand count first, then the attribute: a node short or long of its
    one operand is the wrong shape whatever else it carries, and saying
    so is the move a reader can make before anything else.
    """
    if len(node.args) != 1:
        return (
            f"{name} carries {_counted(len(node.args), 'operand')} and "
            f"takes exactly one -- {operand}, and nothing beside "
            f"it. {clause}"
        )
    key, value = node.attrs[0]
    return (
        f"{name} does not carry the attribute {key!r}, which arrived here "
        f"as {value!r}: {no_attribute} {clause}"
    )


def _element_dtype(
    dtype: pl.DataType | None,
) -> pl.DataType | DataTypeClass | None:
    """Return a list column's element type, or the column's own type."""
    return dtype.inner if isinstance(dtype, pl.List) else dtype


def _named_column(node: OpNode) -> str | None:
    """Return the column name a refusal can carry, where the operand is one.

    The name travels with the check because this is the last place that knows
    it: by the time the refusal reaches a reader it is a string inside a
    Polars cast failure, and a conversion that names no column is a hunt
    through the model for the one value that would not go.
    """
    return node.name if isinstance(node, Col) else None


def _float_is_convertible(value: pl.Expr) -> pl.Expr:
    """Test the exact finite, integral, half-open Int64 conversion domain."""
    return (
        value.is_not_null()
        & value.is_finite()
        & (value == value.floor())
        & (value >= pl.lit(_I64_MIN_AS_F64))
        & (value < pl.lit(_I64_UPPER_EXCLUSIVE_AS_F64))
    ).fill_null(value=False)


def _integer_in_i64_range(value: pl.Expr) -> pl.Expr:
    """Test the closed signed 64-bit interval, leaving absence to its own check.

    A comparison between an over-wide unsigned value and a signed bound
    answers null rather than false, because the value has no place in the
    type the two are compared in. That is the same fact as being out of
    range, and ``fill_null`` reads it that way. An absent value passes here
    and is caught by the presence check beside this one, so the two refusals
    stay disjoint: a null is never reported as a number too wide, and a
    number too wide is never reported as a fraction.
    """
    return (
        value.is_null() | ((value >= pl.lit(_I64_MIN)) & (value <= pl.lit(_I64_MAX)))
    ).fill_null(value=False)


def _every_period(value: pl.Expr, element_test: pl.Expr) -> pl.Expr:
    """Return whether a list is present and every element of it passes."""
    return (
        value.is_not_null()
        & value.list.eval(element_test).list.all().fill_null(value=False)
    ).fill_null(value=False)


def _scalar_conversion(
    value: pl.Expr, *, floating: bool, measured: bool, column: str | None = None
) -> pl.Expr:
    """Convert one scalar value per row after a vectorized validity check."""
    present = _float_is_convertible(value) if floating else value.is_not_null()
    if not measured:
        safe = pl.when(present).then(value).otherwise(pl.lit(0)).cast(pl.Int64)
        return safe + require_valid_rows(
            present, message=checked_integer_refusal(column)
        )
    in_range = _integer_in_i64_range(value)
    safe = pl.when(present & in_range).then(value).otherwise(pl.lit(0)).cast(pl.Int64)
    return (
        safe
        + require_valid_rows(present, message=checked_integer_refusal(column))
        + require_valid_rows(in_range, message=integer_range_refusal(column))
    )


def _list_conversion(
    value: pl.Expr, *, floating: bool, measured: bool, column: str | None = None
) -> pl.Expr:
    """Convert each list element, refusing a null list or invalid element."""
    element = pl.element()
    element_present = (
        _float_is_convertible(element) if floating else element.is_not_null()
    )
    element_valid = element_present
    if measured:
        element_valid = element_present & _integer_in_i64_range(element)
    safe = value.list.eval(
        pl.when(element_valid).then(element).otherwise(pl.lit(0)).cast(pl.Int64)
    )
    converted = safe + require_valid_rows(
        _every_period(value, element_present),
        message=checked_integer_refusal(column),
    )
    if not measured:
        return converted
    return converted + require_valid_rows(
        _every_period(value, _integer_in_i64_range(element)),
        message=integer_range_refusal(column),
    )


@register_lowering("to_integer")
def _lower_to_integer(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Lower strict numeric conversion without truncating or filling absence."""
    match node.args, node.attrs:
        case (value_node,), ():
            value, shape = lower_arg(value_node, ctx)
        case _:
            msg = _signature_refusal(
                node,
                name="to_integer",
                operand="the value to convert",
                no_attribute=_NO_INTEGER_ATTRIBUTE,
                clause=_INTEGER_SIGNATURE,
            )
            raise TypeError(msg)
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    inner = _element_dtype(dtype)
    if inner is None or not (inner.is_integer() or inner.is_float()):
        reason = (
            "to_integer accepts only integer or floating-point values; "
            f"the receiver resolved to {dtype!s}."
        )
        raise TypeError(reason)
    floating = inner.is_float()
    measured = inner.base_type() in _WIDER_THAN_I64
    column = _named_column(value_node)
    if shape == "list":
        return _list_conversion(
            value, floating=floating, measured=measured, column=column
        )
    return _scalar_conversion(
        value, floating=floating, measured=measured, column=column
    )


def _double_is_exact(value: pl.Expr) -> pl.Expr:
    """Test the closed interval in which every whole number has its own double.

    A null is carried rather than refused: nothing about an absent value is
    too large for a double, so there is no loss for the conversion to refuse.
    """
    return (
        value.is_null()
        | ((value >= pl.lit(-_EXACT_IN_F64)) & (value <= pl.lit(_EXACT_IN_F64)))
    ).fill_null(value=False)


@register_lowering("to_float")
def _lower_to_float(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Lower widening to a double, refusing an integer no double names."""
    match node.args, node.attrs:
        case (value_node,), ():
            value, shape = lower_arg(value_node, ctx)
        case _:
            msg = _signature_refusal(
                node,
                name="to_float",
                operand="the value to convert",
                no_attribute=_NO_FLOAT_ATTRIBUTE,
                clause=_FLOAT_SIGNATURE,
            )
            raise TypeError(msg)
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    inner = _element_dtype(dtype)
    if inner is None or not (inner.is_integer() or inner.is_float()):
        reason = (
            "to_float accepts only integer or floating-point values; "
            f"the receiver resolved to {dtype!s}. A boolean is the answer a "
            "comparison gives rather than a number, and text and a date are "
            "not quantities, so none of them is widened here."
        )
        raise TypeError(reason)
    if inner.is_float():
        # Already the type the artifact calls f64. Every float width widens
        # into a double exactly, so there is no value to measure and nothing
        # to refuse.
        return value.cast(pl.List(pl.Float64) if shape == "list" else pl.Float64)
    column = _named_column(value_node)
    if shape == "list":
        return _list_widening(value, column=column)
    return _scalar_widening(value, column=column)


def _scalar_widening(value: pl.Expr, *, column: str | None) -> pl.Expr:
    """Widen one integer per row, refusing the row a double cannot name."""
    valid = _double_is_exact(value)
    safe = pl.when(valid).then(value).otherwise(pl.lit(0)).cast(pl.Float64)
    return safe + require_valid_rows(valid, message=checked_float_refusal(column))


def _list_widening(value: pl.Expr, *, column: str | None) -> pl.Expr:
    """Widen each integer element, refusing the row that holds an unnameable one.

    A null outer list carries as null for the same reason a null element
    does: there is no value in it for a double to fail to name.
    """
    element_valid = _double_is_exact(pl.element())
    row_valid = value.list.eval(element_valid).list.all().fill_null(value=True)
    safe = value.list.eval(
        pl.when(element_valid).then(pl.element()).otherwise(pl.lit(0)).cast(pl.Float64)
    )
    return safe + require_valid_rows(row_valid, message=checked_float_refusal(column))


def _carries_into_text(dtype: pl.DataType | DataTypeClass) -> bool:
    """Return whether this vocabulary has a text form for ``dtype``."""
    if isinstance(dtype, pl.List):
        inner = getattr(dtype, "inner", None)
        return inner is not None and _carries_into_text(inner)
    return dtype.base_type() in _TEXT_READY or dtype.is_integer() or dtype.is_float()


def _text_dtype(dtype: pl.DataType | DataTypeClass) -> pl.DataType:
    """Return ``dtype`` with its value type replaced by text, nesting kept."""
    if isinstance(dtype, pl.List):
        return pl.List(_text_dtype(dtype.inner))
    return pl.String()


@register_lowering("to_text")
def _lower_to_text(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Lower the conversion that keeps every digit and gives up no value."""
    match node.args, node.attrs:
        case (value_node,), ():
            value, _shape = lower_arg(value_node, ctx)
        case _:
            msg = _signature_refusal(
                node,
                name="to_text",
                operand="the value to convert",
                no_attribute=_NO_TEXT_ATTRIBUTE,
                clause=_TEXT_SIGNATURE,
            )
            raise TypeError(msg)
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    if dtype is None or not _carries_into_text(dtype):
        reason = (
            f"to_text has no text form for {dtype!s}. It accepts a boolean, "
            "an integer of any width, a floating-point value, text, a date, "
            "a datetime, a category, and a list of any of those -- every "
            "type whose text is the value itself. A duration, a decimal, a "
            "time of day, a binary blob and a fixed-width array are not "
            "among them: each would have to be rendered under a convention "
            "the model never wrote down, and a text nobody can read back is "
            "not a conversion."
        )
        raise TypeError(reason)
    return value.cast(_text_dtype(dtype))


def _named_element(dtype: pl.DataType | DataTypeClass) -> bool:
    """Return whether section 10 has a scalar name for this element type."""
    return (
        dtype.base_type() in _NAMED_ELEMENTS or dtype.is_integer() or dtype.is_float()
    )


@register_lowering("to_list")
def _lower_to_list(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Lower the conversion that unpins an array's length, keeping its elements.

    An array is the ``list[...]`` this vocabulary already has with its length
    fixed, and the length is the only thing given up. A column that is
    already a list is refused rather than passed through: a node that
    sometimes converts and sometimes does nothing means two things, and a
    reviewer reading it off the trace could not tell which one happened.
    """
    match node.args, node.attrs:
        case (value_node,), ():
            value, _shape = lower_arg(value_node, ctx)
        case _:
            msg = _signature_refusal(
                node,
                name="to_list",
                operand="the array to convert",
                no_attribute=_NO_LIST_ATTRIBUTE,
                clause=_LIST_SIGNATURE,
            )
            raise TypeError(msg)
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    if not isinstance(dtype, pl.Array):
        reason = (
            "to_list converts a fixed-width array into a list of the same "
            f"elements, and the receiver resolved to {dtype!s}. A column "
            "that is already a list is one this operation would leave "
            "exactly as it found it, and a value that is neither is not a "
            "run of elements at all -- so both are refused rather than "
            "carried, and the node means one thing wherever it is read."
        )
        raise TypeError(reason)
    inner = dtype.inner
    if inner is None or not _named_element(inner):
        reason = (
            f"to_list has no element name for {inner!s}, so the list it "
            f"would answer -- {dtype!s} unpinned -- is one this vocabulary "
            "cannot describe. It converts an array of a boolean, an "
            "integer, a floating-point value, text, a date or a datetime."
        )
        raise TypeError(reason)
    return value.cast(pl.List(inner))
