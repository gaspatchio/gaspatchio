# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowering for the one string operation the format's vocabulary names.

A model point file that carries its entry dates as text is the ordinary
case, not the awkward one: extracts arrive from administration systems in
whatever the system prints, and the first line of a projection turns that
text into dates. ``str.to_date`` is that line.

The format string is the whole of what makes one parse different from
another -- ``"%Y/%m/%d"`` and ``"%d/%m/%Y"`` read the same characters into
two different dates -- and Polars' own rendering of the expression drops it
entirely, printing ``col("entry_date").str.strptime(["raise"])`` either
way. That is why this operation carries its format on the record and why
its lowering reads it back from there.

Where the text is per-period -- a list of strings per policy -- the parse
runs inside each row's list, because that is where the strings are. The
rule reads the shape the tree resolved rather than the kind of proxy the
call was written on, which is the shape rule every other lowering in this
package already uses.

What the record does not carry, this rule does not set: Polars' ``cache``
is a memoisation hint over repeated strings, it cannot change a date, and
an operation's identity is what it computes and nothing else, so the parse
runs under the engine's own default for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import polars as pl

from gaspatchio._semantic.operations import STRING_OPERATIONS
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext


@register_lowering(STRING_OPERATIONS[0].identifier)
def _lower_to_date(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read each string as a calendar date under the format on the record."""
    attrs = dict(node.attrs)
    date_format = cast("str | None", attrs["format"])
    settings = {
        "strict": bool(attrs["strict"]),
        "exact": bool(attrs["exact"]),
    }
    text_expr, shape = lower_arg(node.args[0], ctx)
    if shape == "list":
        return text_expr.list.eval(pl.element().str.to_date(date_format, **settings))
    return text_expr.str.to_date(date_format, **settings)
