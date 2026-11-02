# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One table, keyed by vocabulary identifier, with its capability beside it.

The engine's whole account of what it can do is this dictionary. A family
module registers each identifier it answers for, with the capability that
says on what condition -- and the coverage manifest is that table read out, so
there is no second list of claims to keep true.

``load()`` is the single import point, as the producer's own rule registry
has: registration is a side effect of importing a family module, and calling
it once from the engine's import makes the table independent of the order
anything else happens to import in.

**A second registration of one identifier is refused rather than allowed to
win.** Two lowerings for one operation means the answer depends on import
order, which is a difference between two runs of one model that nothing in
the model accounts for.

**An identifier this engine refuses on purpose says so, and says why.**
:data:`REFUSED` is the other half of the table: an operation whose clause
states no portable value, or whose operand is a type the document grammar has
no name for, is refused *by name* with the sentence the reader needs and the
clause it rests on. An identifier in neither table is one nobody has got to
yet, which is a different thing and reads differently.

**The operators a line chains are written in steps.** A lowering ordinarily
lowers its operands by calling back into the plan, so a tree is lowered one
Python call inside the next and a line summing a few hundred terms ran out of
Python's call depth. The families a model chains -- the arithmetic operators,
the comparisons, the three logical operators and ``when_then`` -- are written
instead as :data:`Steps`: a generator that yields each operand tree in the
order it needs it and is sent that operand's value back. The plan drives a
chain of them from one explicit stack (:func:`stepwise` is the same steps
driven one operand at a time, for anything that calls the lowering itself),
so every operand is lowered, and every check raised, in the order the
recursive form lowered and raised them.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import replace
from functools import wraps
from typing import TYPE_CHECKING

from gaspatchio.engines.format import VOCABULARY

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.capability import Capability
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Value

__all__ = [
    "LOWERINGS",
    "REFUSED",
    "SIZINGS",
    "STEPS",
    "Lowering",
    "Sizing",
    "Steps",
    "load",
    "refused_by_name",
    "register",
    "register_sizing",
    "stepwise",
]

type Lowering = Callable[["Call", "LoweringContext"], "Value"]

# A lowering written in steps: it yields each operand tree it needs, in the
# order it needs them, is sent each one's value back, and returns its answer.
type Steps = Callable[
    ["Call", "LoweringContext"], Generator["OpNode", "Value", "Value"]
]

# How many cells one axis-sizing operation lays down per policy -- the widest
# of the arrays it answers over, which is the boundary sequence where it lays
# one. Asked on its own, and before anything is compiled, because it is the
# *width* of the answer rather than any of the answer's values.
type Sizing = Callable[["Call", "LoweringContext"], "jax.Array"]

LOWERINGS: dict[str, tuple[Lowering, Capability]] = {}

SIZINGS: dict[str, Sizing] = {}

# The steps each lowering written in steps stands for, keyed by the lowering
# itself rather than by identifier: a table entry swapped for another
# lowering is then lowered as that lowering, never as the steps it replaced.
STEPS: dict[Lowering, Steps] = {}

# The identifiers this engine refuses on purpose, each with the sentence a
# reader can act on and the clause that sentence rests on. Three rows, and
# every one of them is a refusal the *format* states rather than a corner
# nobody has reached: two of them have no portable value contract at all in
# this preview, and the third takes an operand section 10 names no type for,
# so no document this engine can be handed carries one.
REFUSED: dict[str, tuple[str, str]] = {
    "rollforward.increment": (
        (
            "reading back what one step of a compiled rollforward moved needs "
            "a machine that tracks its increments, which section 16.1's "
            "executable subset excludes; this engine runs that subset and no "
            "more"
        ),
        "16.2",
    ),
    "rollforward.struct": (
        (
            "a compiled rollforward run whole answers a Struct of named list "
            "fields, and section 10 has no Struct type: this clause states no "
            "portable output for it in this preview"
        ),
        "16.3",
    ),
    "to_list": (
        (
            "the operand is a column of a fixed-width array, and section 10 "
            "names no array type: no document this engine can be handed "
            "carries one"
        ),
        "11.1.40",
    ),
}

# The clause the vocabulary states for each identifier, so a registration that
# names none still publishes one. ``when_then`` is not an identifier -- section
# 11.1.28 calls it a tree form -- and carries its clause on its registration.
_CLAUSE_OF: dict[str, str] = {
    operation.identifier: operation.clause for operation in VOCABULARY
}


def register(capability: Capability) -> Callable[[Lowering], Lowering]:
    """Put one lowering in the table under its identifier, with what it claims.

    Raises:
        ValueError: If the identifier is already registered.

    """

    def bind(lowering: Lowering) -> Lowering:
        name = capability.identifier
        if name in LOWERINGS:
            message = (
                f"{name!r} already has a lowering in this engine. Two lowerings "
                "for one operation make the answer depend on import order, "
                "which is a difference between two runs of one model that "
                "nothing in the model accounts for."
            )
            raise ValueError(message)
        stated = capability
        if not stated.clause:
            stated = replace(stated, clause=_CLAUSE_OF.get(name, ""))
        LOWERINGS[name] = (lowering, stated)
        return lowering

    return bind


def stepwise(steps: Steps) -> Lowering:
    """Return the lowering one set of steps stands for, and remember the steps.

    The lowering asks the context for each operand as the steps yield it, so
    called on its own it is exactly the recursive form. The plan reads
    :data:`STEPS` to drive a chain of them without recursion instead. It
    carries the steps' own module and name, so a reader of the table -- the
    coverage manifest, the test that finds each check's declaration beside
    the module that raises it -- reads the family it was written in.
    """

    @wraps(steps)
    def lowering(call: Call, ctx: LoweringContext) -> Value:
        walk = steps(call, ctx)
        try:
            tree = next(walk)
            while True:
                tree = walk.send(ctx.lower(tree))
        except StopIteration as done:
            answer: Value = done.value
            return answer

    STEPS[lowering] = steps
    return lowering


def refused_by_name(identifier: str) -> tuple[str, str] | None:
    """Return the sentence and the clause one refused identifier carries, or None.

    None for an identifier this engine simply has no lowering for, which is a
    statement about this edition rather than about the operation -- and the
    two must not read the same, because one of them is a thing to wait for and
    the other is a thing to stop waiting for.
    """
    return REFUSED.get(identifier)


def register_sizing(identifier: str) -> Callable[[Sizing], Sizing]:
    """Bind one identifier's cell count, asked before any array is built.

    Raises:
        ValueError: If the identifier already has one.

    """

    def bind(sizing: Sizing) -> Sizing:
        if identifier in SIZINGS:
            message = f"{identifier!r} already has a sizing in this engine."
            raise ValueError(message)
        SIZINGS[identifier] = sizing
        return sizing

    return bind


def load() -> None:
    """Import every family module, registering its lowerings as a side effect."""
    from gaspatchio_jax.lowerings import (  # noqa: F401, PLC0415 -- the import is the registration
        banding,
        comparisons,
        conditional,
        conversion,
        curves,
        dates,
        excel,
        finance,
        logic,
        maths,
        missing,
        projection,
        reduction,
        rollforward,
        rounding,
        schedule,
        selection,
        tables,
    )
