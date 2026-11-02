# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The named conversions, and the two of them that happen on the host.

``to_float`` and ``to_integer`` are checked widening and checked narrowing,
and both are in the trace: what they check is a property of a number, and a
number is what the trace holds. ``to_text`` and ``str.to_date`` are not. Text
in the trace is an interned code, and a code is an implementation of equality
rather than a string -- so an operation that *produces* text has to produce
it on the host, from operands that arrived with the book or were written into
the formula. A text-producing operation over a computed operand refuses
by name in this edition, and the capability says so rather than the engine
discovering it half way through a run.

**11.1.39's layout is the operation and not a rendering of it.** The shortest
decimal says which digits; the clause says how they are laid out, and the two
are separate questions. Python's ``repr`` answers the first and not the
second -- it pads a one-digit exponent and switches forms at other thresholds
-- so the digits are taken apart and laid out here.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import jax.numpy as jnp
import numpy as np
import polars as pl

from gaspatchio.engines.format import Call, Col, Lit, op_node_from_json
from gaspatchio_jax.capability import (
    ANY_CARRIER,
    NUMERIC,
    PER_POLICY,
    TEXT,
    Capability,
)
from gaspatchio_jax.checks import flag
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import (
    JNP_OF,
    DomainRefused,
    Value,
    outside_double_exact,
    outside_integer_conversion,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio_jax.capability import NodeRecord
    from gaspatchio_jax.interning import Dictionary
    from gaspatchio_jax.plan import LoweringContext, PreparedInputs

_TO_INTEGER: Final = "11.1.23"
_TO_FLOAT: Final = "11.1.38"
_TO_TEXT: Final = "11.1.39"
_TO_DATE: Final = "11.1.7"

# The two operations answered on the host, each with the clause it rests on.
# The capability refuses a computed operand under the operation's own clause,
# and the host stage's refusal of the same operand cites the same one.
_HOST_CLAUSES: Final[dict[str, str]] = {"to_text": _TO_TEXT, "str.to_date": _TO_DATE}

# 11.1.39's fixed-form window, in decimal exponents.
_FIXED_BETWEEN: Final = (-5, 15)

_EPOCH: Final = datetime.date(1970, 1, 1)


@register(
    Capability(
        identifier="to_float",
        arity=(1,),
        carriers=(NUMERIC - frozenset({"bool"}),),
        # The reference producer refuses a flag, text and a date too.
        refused_alike={
            "carrier@0": (
                "to_float takes a number: write a flag as "
                "when(flag).then(1.0).otherwise(0.0), and convert text or a "
                "date where it is loaded"
            )
        },
        checks=("to_float.exact",),
        clause=_TO_FLOAT,
    )
)
def _to_float(call: Call, ctx: LoweringContext) -> Value:
    """Return the value widened to a double, checked at ±2⁵³."""
    operand = ctx.lower(call.args[0])
    if operand.carrier == "f64":
        return Value(operand.array, "f64", operand.shape, "f64", operand.horizon)
    if operand.carrier != "i64":
        raise DomainRefused(
            what=f"to_float was written over a {operand.carrier} value",
            move="to_float takes a number; carry text or a date some other way",
            clause=_TO_FLOAT,
        )
    flag("to_float.exact", outside_double_exact(operand.array))
    return Value(
        operand.array.astype(JNP_OF["f64"]),
        "f64",
        operand.shape,
        "f64",
        operand.horizon,
    )


@register(
    Capability(
        identifier="to_integer",
        arity=(1,),
        carriers=(NUMERIC - frozenset({"bool"}),),
        checks=("to_integer.integral",),
        clause=_TO_INTEGER,
    )
)
def _to_integer(call: Call, ctx: LoweringContext) -> Value:
    """Return the value narrowed to a signed 64-bit integer, or refuse it."""
    operand = ctx.lower(call.args[0])
    if operand.carrier == "i64":
        return Value(operand.array, "i64", operand.shape, "i64", operand.horizon)
    if operand.carrier != "f64":
        raise DomainRefused(
            what=f"to_integer was written over a {operand.carrier} value",
            move=(
                "to_integer takes a number; every other type is refused by "
                "this clause, Boolean, text and date included"
            ),
            clause=_TO_INTEGER,
        )
    values = operand.array
    outside = outside_integer_conversion(values)
    flag("to_integer.integral", outside)
    safe = jnp.where(outside, jnp.zeros_like(values), values)
    return Value(
        safe.astype(JNP_OF["i64"]), "i64", operand.shape, "i64", operand.horizon
    )


@register(
    Capability(
        identifier="to_text",
        arity=(1,),
        carriers=(ANY_CARRIER,),
        shapes=(PER_POLICY,),
        operands="inputs-or-literals",
        off_trace=True,
        clause=_TO_TEXT,
    )
)
def _to_text(_call: Call, _ctx: LoweringContext) -> Value:  # pragma: no cover
    """Refuse in the trace: this operation is answered in the host stage.

    Reaching here means the plan sent an off-trace node down the trace, which
    is a disagreement between the capability and the runtime rather than
    anything a model did.
    """
    raise DomainRefused(
        what="to_text is answered on the host and was reached in the trace",
        move="report the disagreement against the engine's package",
        clause=_TO_TEXT,
    )


@register(
    Capability(
        identifier="str.to_date",
        arity=(1,),
        carriers=(TEXT,),
        shapes=(PER_POLICY,),
        checks=("str.to_date.strict",),
        operands="inputs-or-literals",
        off_trace=True,
        attrs={"strict": ("True",), "exact": ("True",)},
        # A null format is a parse the producer inferred from the text its own
        # run held, and 11.1.7 says a second reader cannot reproduce one.
        attrs_required=("format",),
        clause=_TO_DATE,
    )
)
def _str_to_date(_call: Call, _ctx: LoweringContext) -> Value:  # pragma: no cover
    """Refuse in the trace, as ``to_text`` does and for the same reason."""
    raise DomainRefused(
        what="str.to_date is answered on the host and was reached in the trace",
        move="report the disagreement against the engine's package",
        clause=_TO_DATE,
    )


def on_the_host(
    record: NodeRecord, prepared: PreparedInputs, dictionary: Dictionary
) -> Value:
    """Return the value one off-trace operation produces, computed on the host.

    Raises:
        DomainRefused: If the node is not one of the two host operations, or
            its configuration is outside what this engine reproduces.

    """
    tree = record.expr or {}
    node = op_node_from_json(tree)
    if not isinstance(node, Call):  # pragma: no cover -- the plan picked it by name
        message = f"{record.node_id} is not the call the host stage was given"
        raise TypeError(message)
    operand = _host_operand(
        node.args[0], record, prepared, clause=_HOST_CLAUSES.get(node.name, "11.1")
    )
    attrs = dict(node.attrs)
    if node.name == "to_text":
        # The distinct values in the order they first appear, so the codes
        # are minted in the order a pass over the rows would mint them.
        texts = [written_text(value) for value in operand.distinct]
        codes = dictionary.codes_for([text or "" for text in texts])
        return Value(jnp.asarray(codes[operand.index]), "code", "scalar", "str")
    if node.name == "str.to_date":
        return _parsed_dates(operand, attrs, record)
    raise DomainRefused(  # pragma: no cover -- only two are off the trace
        what=f"{node.name} is not answered on the host",
        move="report the disagreement against the engine's package",
        clause="11.1",
    )


def _parsed_dates(
    operand: _Operand, attrs: Mapping[str, object], record: NodeRecord
) -> Value:
    """Return text read as calendar dates, under the format the record carries."""
    stated = attrs.get("format")
    if not isinstance(stated, str):
        raise DomainRefused(
            what=(
                "this parse carries no format, so the producer inferred one "
                "from the text its own run held and no second reader can "
                "reproduce it"
            ),
            move="name the format the parse means, in the strftime vocabulary",
            clause=_TO_DATE,
        )
    # Each distinct string is parsed once and every row takes its answer by
    # position: a book of a million policies carries as many dates as it has
    # distinct issue days, not a million. The distinct values stand in the
    # order they first appear, so the first one that is not text is the first
    # row that is not, and the refusal is the one a row-by-row pass makes.
    answers: list[tuple[int, bool]] = []
    for value in operand.distinct:
        if not isinstance(value, str):
            message = (
                "str.to_date reads text as a calendar date, and this operand "
                f"carries {type(value).__name__}"
            )
            raise DomainRefused(
                what=message,
                move="parse the column the dates arrived in as text",
                clause=_TO_DATE,
            )
        answers.append(_parsed_day(value, stated))
    days = np.asarray([day for day, _failed in answers], dtype=np.int64)
    failed = np.asarray([failed for _day, failed in answers], dtype=bool)
    flag(
        "str.to_date.strict",
        jnp.asarray(failed[operand.index]),
        where=record.node_id,
    )
    return Value(jnp.asarray(days[operand.index]), "date", "scalar", "date")


def _parsed_day(value: str, stated: str) -> tuple[int, bool]:
    """Return one string's count of days and whether it failed to parse."""
    try:
        parsed = datetime.datetime.strptime(value, stated).date()  # noqa: DTZ007 -- a calendar day carries no zone
    except ValueError:
        return 0, True
    return (parsed - _EPOCH).days, False


@dataclass(frozen=True, slots=True)
class _Operand:
    """One host operand, as its distinct values and each row's place among them.

    A host operation answers per value, and a book repeats its values: a
    million policies carry a few hundred issue dates. So the operation is
    asked once per distinct value and every row reads its answer back by
    position, rather than a million Python objects being built and walked.

    Attributes:
        distinct: The distinct values, in the order they first appear in
            the book (a missing value among them as ``None``).
        index: For every row, the position of its value in ``distinct``.

    """

    distinct: list[object]
    index: np.ndarray


def _float_operand(column: pl.Series) -> _Operand:
    """Return a float column's distinct values told apart by their bits.

    Equality is the wrong sameness for text: ``-0.0 == 0.0``, and 11.1.39
    writes one as ``-0.0`` and the other as ``0.0``. So two doubles are one
    value here only when every bit agrees, and a missing value is never the
    same as a NaN.
    """
    missing = column.is_null().to_numpy()
    values = column.cast(pl.Float64).fill_null(0.0).to_numpy()
    bits = values.view(np.uint64)
    keys = np.stack([missing.astype(np.uint64), bits], axis=1)
    _found, first, inverse = np.unique(
        keys, axis=0, return_index=True, return_inverse=True
    )
    order = np.argsort(first)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    distinct: list[object] = [
        None if missing[row] else float(values[row]) for row in first[order]
    ]
    return _Operand(distinct, rank[np.asarray(inverse).reshape(-1)].astype(np.int64))


def _host_operand(
    node: object, record: NodeRecord, prepared: PreparedInputs, *, clause: str
) -> _Operand:
    """Return one operand's values on the host: a column that arrived, or a literal.

    **The column is resolved through the record's own reads before the book
    is touched.** The book holds what *arrived*, and a model that writes over
    an arriving column leaves an input node and a computed one under one
    name; reading the book by name there answers with the values the column
    held before the model wrote over it -- a wrong answer, published, with
    nothing in the report to say so. Where the account this node reads is a
    calculation, that is the computed-text refusal and it is stated here as well as by
    the capability, so the two halves cannot come apart.

    Raises:
        DomainRefused: If the operand is a calculation rather than a column
            that arrived or a value written into the formula.

    """
    if isinstance(node, Col):
        if record.read_kinds.get(node.name, "input") != "input":
            raise DomainRefused(
                what=(
                    f"this operation reads {node.name!r}, which a calculation "
                    "produced; this engine answers it on the host and only "
                    "from columns that arrived or values written into the "
                    "formula"
                ),
                move="write the calculation to a column of its own first",
                clause=clause,
            )
        column = prepared.frame[node.name]
        if column.dtype.is_float():
            return _float_operand(column)
        distinct = column.unique(maintain_order=True)
        positions = pl.Series(np.arange(distinct.len(), dtype=np.int64))
        index = column.replace_strict(distinct, positions, return_dtype=pl.Int64)
        return _Operand(distinct.to_list(), index.to_numpy().astype(np.int64))
    if isinstance(node, Lit) and not isinstance(node.value, tuple):
        return _Operand([node.value], np.zeros(prepared.rows, dtype=np.int64))
    raise DomainRefused(  # pragma: no cover -- the capability refuses first
        what="this operation is answered on the host from inputs and literals",
        move="write the calculation to a column of its own first",
        clause=clause,
    )


def written_float(value: float) -> str:
    """Return one double as 11.1.39 lays it out.

    Fixed form between the two exponents the clause names, with at least one
    digit after the point; exponent form outside them, with the exponent's
    sign always written and never padded.
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    sign = "-" if math.copysign(1.0, value) < 0 else ""
    if value == 0.0:
        return f"{sign}0.0"
    mantissa, _, written = repr(abs(value)).partition("e")
    exponent = int(written or 0)
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    exponent += len(whole) - 1 - (len(whole + fraction) - len(digits))
    digits = digits.rstrip("0") or "0"
    low, high = _FIXED_BETWEEN
    if low <= exponent <= high:
        if exponent < 0:
            return f"{sign}0.{'0' * (-exponent - 1)}{digits}"
        lead = digits[: exponent + 1].ljust(exponent + 1, "0")
        return f"{sign}{lead}.{digits[exponent + 1 :] or '0'}"
    first, rest = digits[0], digits[1:]
    mantissa = f"{first}.{rest}" if rest else first
    return f"{sign}{mantissa}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def written_text(value: object) -> str | None:
    """Return one value written out as text, giving none of it up."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return written_float(value)
    return str(value)
