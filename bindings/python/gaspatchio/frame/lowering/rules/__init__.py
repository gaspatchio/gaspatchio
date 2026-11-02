# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where a relocated accessor body lives once it stops building expressions.

Each module here owns the Polars lowering for one family of ``Call``
names -- the predicate combinators, the ``projection`` accessor, the
``finance`` accessor, assumption-table lookup -- registered under the
name emission stamps on the node. The bodies are the accessors' own
former bodies, moved rather than rewritten: the same Polars calls, the
same shape decisions, reading the shape from the lowering context
instead of from a proxy.

``load()`` imports the concrete rule families. The parent lowering package
wires it into the dispatcher, which runs it on first use and retries after a
failed import. The rules depend on the dispatcher; the dispatcher does not
import its concrete implementations.

``_counted``, ``_listed`` and ``_SPEC_PATH`` are the shared spellings a
refusal reaches for when it names the defect it met: how many operands
arrived, which attributes were missing, and where in the format the
signature it missed is stated. The sentences themselves stay in the rule
that raises them -- what an operation is for is not something a shared
module can say -- and only the counting and the quoting live here, so two
refusals in two files cannot disagree about how many is one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from gaspatchio._semantic.ir import Call

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio._semantic.ir import AttrValue, OpNode

# Where a reader sent to check a node against the format has to go. Named
# once because three rules cite it and a path typed three times is a path
# that goes stale twice.
_SPEC_PATH: Final = "spec/graph-artifact/v0-preview.md"


def load() -> None:
    """Import every rule module, registering its lowerings as a side effect."""
    from gaspatchio.frame.lowering.rules import (  # noqa: F401, PLC0415
        accumulation,
        banding,
        bounds,
        conversion,
        curves,
        excel,
        finance,
        lookup,
        maths,
        missing,
        mortality,
        predicates,
        projection,
        reduction,
        rollforward,
        rounding,
        schedule,
        selection,
        strings,
    )


def _call(
    name: str,
    attrs: tuple[tuple[str, AttrValue], ...] = (),
    args: tuple[OpNode, ...] = (),
) -> Call:
    """Build a ``Call`` node from inside a rule, without the emission check.

    One rule sometimes needs another -- the frame accessor's ``t_years``
    cumulates the schedule's own year fractions -- and reaching for
    ``emit.call_node`` there would re-run the registry membership check on
    a name this module just registered itself. The author-facing check
    stays where it belongs, on the emission path.
    """
    return Call(name=name, args=args, attrs=attrs)


def _counted(number: int, noun: str) -> str:
    """Spell ``number`` of ``noun`` the way the sentence around it reads.

    A refusal that says how many operands it was handed is one a reader
    can act on without counting the node themselves, and ``0 operands``
    is not a thing anybody writes.
    """
    if number == 0:
        return f"no {noun}s"
    if number == 1:
        return f"one {noun}"
    return f"{number} {noun}s"


def _listed(names: Sequence[str]) -> str:
    """Quote ``names`` as an English list, however many of them there are."""
    quoted = [repr(name) for name in names]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"
