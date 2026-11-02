# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The six comparisons, and what a truth value is where it lands.

Section 11.1.26's bounded domain is finite numbers, or two operands of one
semantic family -- two Booleans, two strings, two dates. There is no ordering
between families and none is inferred: a date is not a number here even
though the trace holds it as one.

**Text is ordered by its code points, and never by its codes.** The trace
holds text as this run's interned codes, minted in the order the run met each
string, so a code says which string and nothing about where it sorts. Equality
reads the codes as they are. An ordering reads each code's *rank* -- where its
string stands among every string the run has interned, sorted by code point,
which is the order section 11.1.26 states for text of either shape and the
order the producer's UTF-8 comparison gives -- through one table built on the
host from the strings themselves when the comparison is lowered. Every code an
operand can carry is minted before its comparison is lowered, so the table
holds each of them.

**A NaN operand leaves the comparison without a truth value.** A NaN is no
number, so it is neither above 1.0 nor below it nor equal to anything, and
section 11.1.26 answers it as an unknown on every side and both shapes: the
cells are carried beside the answer (``Value.unknown``), a stored indicator
is NaN there, a ``when`` over it answers NaN, and ``&``, ``|`` and ``~``
over it have none either. ±infinity is a number and is ordered as IEEE
orders it.

**A predicate and a stored indicator are the same truth value in two
representations.** The comparison answers a Boolean here; whether it is stored
as ``1.0`` and ``0.0`` is decided where it lands -- by the node record if it
is assigned, by promotion if it is an arithmetic operand -- and never by this
module choosing for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp
import numpy as np

from gaspatchio.engines.format import Call as CallNode
from gaspatchio_jax.capability import DATE, NUMERIC, TEXT, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned, unknown_on
from gaspatchio_jax.lowerings import register, stepwise
from gaspatchio_jax.typed import (
    DomainRefused,
    Value,
    promote,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    import jax

    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.interning import Dictionary
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext

_COMPARISONS: Final = "11.1.26"

_ORDERED = {
    "lt": jnp.less,
    "le": jnp.less_equal,
    "gt": jnp.greater,
    "ge": jnp.greater_equal,
    "eq": jnp.equal,
    "ne": jnp.not_equal,
}

# The two that read text's codes as they are; the four orderings read ranks.
_EQUALITY: Final[frozenset[str]] = frozenset({"eq", "ne"})


def _refuse_a_band_ordered(call: Call, name: str) -> None:
    """Refuse an ordering of a band from ``cut`` against anything (11.1.26).

    A band is an ordered category, whose order is its categories' and not
    its text's, and the vocabulary holds no ordered category: the record
    can say only the text's order, which is not what the model meant. Its
    equality with a label has one meaning, and answers.
    """
    if name in _EQUALITY:
        return
    for operand in call.args:
        if isinstance(operand, CallNode) and operand.name == "cut":
            raise DomainRefused(
                what=(
                    f"{name} orders a band from cut, an ordered category, "
                    "which this vocabulary holds no order for: a band's order "
                    "is its categories' and the record can say only its text's"
                ),
                move=(
                    "compare the number the band was cut from for the band's "
                    "order, or the band's text for the letters'"
                ),
                clause=_COMPARISONS,
            )


def _comparable(left: Value, right: Value, name: str) -> tuple[Value, Value]:
    """Return the two operands ready to compare, or say why they are not.

    Text and dates compare only with their own kind; numbers promote under
    11.1.25's rule, which is where the ±2⁵³ check fires when a wide integer
    meets a double.
    """
    if left.carrier == "code" or right.carrier == "code":
        if left.carrier != right.carrier:
            other = right.carrier if left.carrier == "code" else left.carrier
            raise DomainRefused(
                what=f"{name} compared text with a {other} value",
                move="compare the text with text, or convert one side first",
                clause=_COMPARISONS,
            )
        return left, right
    if left.carrier == "date" or right.carrier == "date":
        if left.carrier != right.carrier:
            other = right.carrier if left.carrier == "date" else left.carrier
            raise DomainRefused(
                what=f"{name} compared a date with a {other} value",
                move="compare the date with a date, or convert one side first",
                clause=_COMPARISONS,
            )
        return left, right
    return promote(left, right, clause=_COMPARISONS)


def code_point_ranks(dictionary: Dictionary) -> np.ndarray:
    """Return where each interned string stands in code-point order, by code.

    Indexed by code plus one, so the code an absent key takes (``-1``) reads
    the first slot, which no string holds: it ranks below every string, and
    no operand of a comparison carries it, because a text column the model
    reads as a value refuses a null at the door. Python orders ``str`` by code
    point, and UTF-8's byte order -- the producer's -- is the same order.
    """
    texts = dictionary.texts
    ranks = np.full(len(texts) + 1, -1, dtype=np.int32)
    by_text = sorted(range(len(texts)), key=texts.__getitem__)
    ranks[np.asarray(by_text, dtype=np.int64) + 1] = np.arange(
        len(texts), dtype=np.int32
    )
    return ranks


def _ordered_text(
    arrays: tuple[jax.Array, ...], ctx: LoweringContext
) -> tuple[jax.Array, ...]:
    """Return two arrays of codes as their strings' code-point ranks."""
    ranks = jnp.asarray(code_point_ranks(ctx.dictionary))
    return tuple(ranks[array + 1] for array in arrays)


def _one(name: str) -> Lowering:
    """Return the lowering for one of the six, in steps: operands, then the test."""

    def steps(call: Call, ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
        _refuse_a_band_ordered(call, name)
        left = yield call.args[0]
        right = yield call.args[1]
        left, right = _comparable(left, right, name)
        axis = aligned(left, right)
        arrays = axis.arrays
        if left.carrier == "code" and name not in _EQUALITY:
            arrays = _ordered_text(arrays, ctx)
        # 11.1.26: two whole numbers compare exactly over the whole of i64,
        # per period as per policy; only a whole number meeting a decimal is
        # bounded, and promotion above is where that check fires. A NaN on
        # either side leaves no truth value, and neither does a compared test
        # that had none.
        # A per-policy logical result compared is a null where it is one
        # (11.1.27), and so is the comparison -- a null this engine does not
        # carry, so it refuses those cells by name.
        nulls = unknown_on((left, right), axis, nulls=True)
        if nulls is not None:
            flag("comparison.unknown", nulls)
        unknown = unknown_on((left, right), axis, nulls=False)
        if left.carrier == "f64":
            nan = jnp.isnan(axis.arrays[0]) | jnp.isnan(axis.arrays[1])
            unknown = nan if unknown is None else unknown | nan
        return Value(
            _ORDERED[name](*arrays),
            "bool",
            axis.shape,
            "bool",
            axis.horizon,
            unknown,
        )

    return stepwise(steps)


for _name in _ORDERED:
    register(
        Capability(
            identifier=_name,
            arity=(2,),
            # All six answer over numbers, dates and text, as 11.1.26 states
            # them; both operands must fall in one family.
            carriers=(NUMERIC | DATE | TEXT, NUMERIC | DATE | TEXT),
            matched_carriers=True,
            checks=("comparison.unknown", "mixed.2p53"),
            clause=_COMPARISONS,
        )
    )(_one(_name))
