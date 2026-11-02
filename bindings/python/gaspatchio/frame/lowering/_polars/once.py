# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An operand written into a Polars plan once, however often a lowering reads it.

A Polars expression is a tree, so a lowering that reads its operand several
times writes the operand's whole expression out at each read. Over a column
that costs nothing. Over another call's answer it multiplies: an exact
rounding of a whole number reads its operand a few hundred times -- its
figures are counted against eighteen powers of ten -- so a rounding of a
rounding was 47.9 MB of plan, and "round each component, then the total"
93.2 MB, which never answered (audit D1-H1).

:func:`read_once` holds each operand as a field of one struct and builds the
answer over the fields, so each call adds its own steps and its operands
once, and a plan grows with the calls written rather than with how often
each reads the one before. The arithmetic is the same expression over a
field as over the operand, so every value is unchanged, bit for bit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable

# The field each operand is held under, numbered; and the answer's.
_OPERAND = "operand_{}"
_ANSWER = "answer"

# The answer's field where the record writes the operands back in place:
# the rendering reads a wrapper under this name as the answer over its
# operands, so the walk-through shows the line as it reads without one.
ANSWER_AS_WRITTEN = "answer_as_written"
OPERAND_FIELD = _OPERAND


def read_once(
    *operands: pl.Expr, answer: Callable[..., pl.Expr], as_written: bool = False
) -> pl.Expr:
    """Return ``answer`` over ``operands``, each written into the plan once.

    ``answer`` is called with one field expression per operand, in order,
    and may read each as often as it likes, and any column of the frame
    besides (``pl.col`` inside the struct still names the frame's columns).

    Args:
        operands: The expressions a lowering reads more than once.
        answer: Builds the lowering over the operands' fields.
        as_written: Whether a rendering for a reader writes the operands back
            where the answer reads them (``rendering.read_once_as_written``),
            for a lowering whose text a reader or a rewrite reads as the
            operation written. A lowering that reads its operand hundreds of
            times -- an exact rounding -- keeps the wrapper in its text, which
            would otherwise grow as the plan did.

    Returns:
        The answer, as one expression reading each operand once.

    Examples:
        >>> import polars as pl
        >>> df = pl.DataFrame({"x": [1.0, -2.0]})
        >>> twice = read_once(pl.col("x") * 3, answer=lambda v: v * v + v)
        >>> df.select(twice.alias("y"))["y"].to_list()
        [12.0, 30.0]

    """
    fields = [_OPERAND.format(place) for place in range(len(operands))]
    held = pl.struct(
        [operand.alias(name) for operand, name in zip(operands, fields, strict=True)]
    )
    built = answer(*(pl.field(name) for name in fields))
    name = ANSWER_AS_WRITTEN if as_written else _ANSWER
    return held.struct.with_fields(built.alias(name)).struct.field(name)


__all__ = ["ANSWER_AS_WRITTEN", "OPERAND_FIELD", "read_once"]
