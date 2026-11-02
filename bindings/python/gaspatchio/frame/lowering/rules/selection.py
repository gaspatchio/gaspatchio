# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Strict positional selection from, and reversal of, each policy's own list."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio.frame.lowering.polars import lower_arg, register_lowering
from gaspatchio.frame.lowering.rules import _SPEC_PATH, _counted

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext


_SIGNED_INDEX_DTYPES: Final = (pl.Int8, pl.Int16, pl.Int32, pl.Int64)

_OPERANDS: Final = 2

_SIGNATURE: Final = f"§11.1.22 of {_SPEC_PATH} states the signature."


def _signature_refusal(node: Call) -> str:
    """Say which half of ``list.get``'s signature this node missed.

    Operand count first, then the attribute, for the reason the sibling
    conversion rule gives: the shape is what a reader fixes first.
    """
    if len(node.args) != _OPERANDS:
        return (
            f"list.get carries {_counted(len(node.args), 'operand')} and "
            "takes exactly two -- the list value, then the position to "
            f"select from it. {_SIGNATURE}"
        )
    key, value = node.attrs[0]
    return (
        f"list.get does not carry the attribute {key!r}, which arrived here "
        f"as {value!r}: a position is selected strictly or the read refuses, "
        "so there is no nullable or fill-on-bounds mode for an attribute to "
        f"select. Drop it. {_SIGNATURE}"
    )


@register_lowering("list.get")
def _lower_list_get(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Select one strict signed position per policy without changing value dtype."""
    match node.args, node.attrs:
        case (values_node, index_node), ():
            values, values_shape = lower_arg(values_node, ctx)
            index, index_shape = lower_arg(index_node, ctx)
        case _:
            msg = _signature_refusal(node)
            raise TypeError(msg)
    if values_shape != "list":  # pragma: no cover - namespace door checks this
        msg = "list.get needs a list receiver"
        raise TypeError(msg)
    index_dtype = None if ctx is None else ctx.dtype_of_expr(index)
    if index_shape != "scalar" or index_dtype not in _SIGNED_INDEX_DTYPES:
        msg = (
            "list.get index must be a signed integer scalar; use to_integer() "
            "before selecting from a floating-point index"
        )
        raise TypeError(msg)

    # Polars accepts Float64/Boolean indices and silently truncates floats;
    # the dtype guard above closes that engine-specific meaning. It also
    # returns null for a null list or index even in strict bounds mode. Turn
    # either absence into an empty list so the same strict get that refuses
    # ordinary out-of-bounds positions refuses these cases as well. List[Null]
    # unifies with the receiver without moving its inner dtype through f64.
    absent = values.is_null() | index.is_null()
    checked_values = pl.when(absent).then(pl.lit([])).otherwise(values)
    checked_index = index.fill_null(0).cast(pl.Int64, strict=True)
    return checked_values.list.get(checked_index, null_on_oob=False)


_REVERSAL: Final = f"§11.1.41 of {_SPEC_PATH} states the signature."


@register_lowering("list.reverse")
def _lower_list_reverse(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Reverse each policy's own list, keeping its length and its element type.

    A permutation within the policy: position ``t`` of the answer is position
    ``T - 1 - t`` of the operand, where ``T`` is that policy's own length, so
    a null moves to its mirrored position and stays null, and nothing of one
    policy reaches another.
    """
    match node.args, node.attrs:
        case (values_node,), ():
            values, values_shape = lower_arg(values_node, ctx)
        case (_,), ((key, _value), *_):
            msg = (
                f"list.reverse does not carry the attribute {key!r}: it turns "
                "one list end for end and has nothing to configure. Drop it. "
                f"{_REVERSAL}"
            )
            raise TypeError(msg)
        case _:
            msg = (
                f"list.reverse carries {_counted(len(node.args), 'operand')} "
                f"and takes exactly one -- the list value. {_REVERSAL}"
            )
            raise TypeError(msg)
    if values_shape != "list":  # pragma: no cover - namespace door checks this
        msg = "list.reverse needs a list receiver"
        raise TypeError(msg)
    return values.list.reverse()
