# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What each operation means, in one sentence, for the walk-through to speak.

A substitution shows the arithmetic of a line and nothing else. For
``a * b - c`` that is the whole of the meaning: a reader sees the numbers
go in, does the sum, and is done. For a named operation it is not. A trace
reading ``(0.0012).cumulative_survival()`` shows a number and a method name
and says nothing about the calculation between them -- which is a running
product across eighty-four periods, of one minus each period's decrement,
opening at one. That sentence is what an actuary needs to check the line,
and it is what this module holds.

**The specification is the authority and this is a rendering of it.** Nine
of the sections of 11.1 state semantics a consumer may rely on; the
sentences for those operations say the same thing in the same voice and
add nothing the section does not support. For every other identifier the
sentence describes what this implementation computes -- which is what the
lowering rule's own docstring says, read off the code that runs -- and a
reader is told that the format has not yet fixed the meaning by the tier
and the specification, not by this table going quiet.

**Every identifier the format owns is answered here.** Either it has a
sentence, or it is named in :data:`SPOKEN_BY_SUBSTITUTION`: the fifteen
binary operators a formula is *written* with rather than called, whose
meaning the substituted arithmetic already is. A census test holds the two
together against ``TIERS``, so an operation added to the vocabulary without
a decision about how it speaks fails rather than arriving voiceless.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
    col_refs,
)
from gaspatchio._semantic.vocabulary import VOCABULARY

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio._semantic.ir import AttrValue, OpNode

__all__ = [
    "OVER_A_GROUP",
    "SENTENCES",
    "SPOKEN_BY_SUBSTITUTION",
    "folded_down_the_model_points",
    "over_the_model_points",
    "sentence_for",
    "why_a_folded_operand_is_not_substituted",
    "why_no_substitution",
]

# What a group- or window-scoped aggregate folded. **Not the model points**:
# ``.sum().over("product")`` totals the policies of one product and answers
# once per policy, so a walk-through that named the whole export's rows
# would be naming rows the aggregate never read. Named separately from the
# population for exactly that reason.
OVER_A_GROUP: Final[str] = "the rows of each group"

# What a field renders as where the call carries no such attribute. Said
# rather than left blank: a sentence with a hole in it reads as a producer
# that lost the value, and a sentence that quietly dropped the clause reads
# as an operation that has no such configuration.
_NOT_RECORDED: Final[str] = "not recorded"

# How many members of a sequence literal a sentence prints before it stops.
# Enough to recognise a band of age boundaries; the whole sequence is in
# the node's own tree, which is where a reader checking it should look.
_MEMBERS_SHOWN: Final[int] = 4

# What a flag's value *means*, for the flags whose raw spelling means
# nothing to a reader. ``reverse=False`` is not a sentence; "from the start
# of the projection" is. Every entry is one attribute of one or more
# operations, and an attribute absent from here renders as its own value --
# a rate, a number of places, a table name and a day-count basis all say
# what they are already.
_PHRASES: Final[dict[str, dict[Any, str]]] = {
    # A projection axis with no cadence is the fixed-step form, which records
    # its step in place of a frequency; "not recorded" would read as a gap.
    "frequency": {None: "fixed-step"},
    "reverse": {
        False: "from the start of the projection",
        True: "backwards from the end of the projection",
    },
    "from_survival": {
        False: "one minus each period's decrement",
        True: "each period's survival probability as given",
    },
    "mode": {
        "half_to_even": "going to whichever neighbour is even",
        "half_away_from_zero": "going to the neighbour further from zero",
    },
    "strict": {
        True: "refusing a string the format does not fit",
        False: "a string the format does not fit becoming null",
    },
    "bounds": {
        "both": "a lower and an upper bound",
        "lower": "a lower bound, with nothing excluded above",
        "upper": "an upper bound, with nothing excluded below",
    },
    # What a mortality basis's own shape means, and how its ages are read.
    # ``structure`` carries the clamp rather than the select period doing
    # it, because a sentence has to be fillable for all three structures
    # and only one of them has a select period at all -- the number itself
    # is the ``select_period`` attribute on the node beside it.
    "structure": {
        "aggregate": "an aggregate basis, one rate for an attained age",
        "select_ultimate": (
            "a select and ultimate basis, a duration past the select period "
            "clamped back to it"
        ),
        "joint": "a joint-life basis, one rate for a pair of ages",
    },
    "age_basis": {
        "age_last_birthday": "age last birthday",
        "age_nearest_birthday": "age nearest birthday",
    },
    "on_missing": {
        "raise": "a key the base does not carry stopping the run",
        "nan": "a key the base does not carry giving NaN",
        "fill": "a key the base does not carry taking the fill value",
    },
    "timing": {
        "beginning_of_period": "each period's cashflow falling at its start",
        "end_of_period": "each period's cashflow falling at its end",
    },
    "left_closed": {
        False: "a value on a breakpoint belonging to the interval below it",
        True: "a value on a breakpoint belonging to the interval above it",
    },
    "nulls_equal": {
        False: "a null equal to nothing and answering null",
        True: "a null compared as a value like any other",
    },
    # A parse with no format on the record is one the producer inferred
    # from the text the run happened to hold, which 11.1.7 says a second
    # implementation cannot reproduce. "Not recorded" would read as a lost
    # value rather than as the absence that carries that meaning.
    "format": {None: "a format the producer inferred rather than was given"},
    "point": {
        "bop": "the beginning of each period",
        "eop": "the end of each period",
    },
}

# One sentence per operation the format names, read out of the one row per
# identifier that holds it and therefore keyed by the identifier of
# specification 11.1 and in that table's own order. A field in braces is
# filled from the node itself: ``operand``, ``second`` and ``third`` are
# its first three arguments named, ``operands`` every column it reads, and
# every other field is one of the call's own attributes.
SENTENCES: Final[dict[str, str]] = {
    entry.identifier: entry.voice for entry in VOCABULARY if entry.voice is not None
}

# The operations whose meaning the substitution already is: the rows the
# table leaves without a sentence. A formula *writes* these rather than
# calling them, and a reader who can see ``(100000) * (0.00123)`` needs no
# sentence saying that one number was multiplied by another: it would be
# the arithmetic restated in words, and a walk-through that says
# everything twice is one nobody finishes reading.
#
# Every one of them is a binary operator of specification 11, and the two
# lists together are exactly the vocabulary, which a census test holds.
SPOKEN_BY_SUBSTITUTION: Final[frozenset[str]] = frozenset(
    entry.identifier for entry in VOCABULARY if entry.voice is None
)


def over_the_model_points(population: str) -> str:
    """Return how a fold over the whole export names what it folded over.

    Written once because three sentences say it -- what a folding line
    computed, why it shows no numbers, and why one operand inside an
    ordinary line was left standing as its name -- and a reader meeting two
    spellings of one population would be right to wonder whether they were
    two populations.
    """
    return f"all {population} in this export"


def folded_down_the_model_points(operands: Sequence[str], population: str) -> str:
    """Return what a line that folds down the model-point file computed.

    The first sentence this mechanism ever spoke, and the one it exists
    for: a fold over every policy has no single value to substitute, so
    the walk-through names what was folded and the population it was
    folded over instead of putting one policy's number inside it.

    ``operands`` is what actually folded -- the columns the folding
    sub-expressions read -- and not the line's whole dependency list. A
    line reading four columns of which one was summed has three operands
    this sentence would otherwise be naming as folded when they were not.
    """
    folded = ", ".join(operands) if operands else "this line's operand"
    return f"{folded} over {over_the_model_points(population)}"


def why_no_substitution() -> str:
    """Return why a fold down the model points shows no numbers.

    A step that simply went quiet reads as a producer that ran out of
    things to write rather than one that declined to write something
    untrue, so the reason is on the record beside the sentence.
    """
    return (
        "This line folds down the model points, so its result is the "
        "population's and not the sampled policy's. No one policy's value "
        "stands inside a fold that ran over every policy, so none is "
        "substituted here."
    )


def why_a_folded_operand_is_not_substituted(
    operands: Sequence[str], over: str | None
) -> str:
    """Return why one operand of an ordinary line carries no number.

    **A fold inside a line is not the line being a fold.**
    ``af.share = af.claims / af.claims.polars_native().sum()`` answers once per policy
    and
    the sampled policy's own share is what it reached; only the denominator
    ran over the book. So the line keeps its walk-through, and the operand
    that folded keeps its name where a number would have been a value the
    fold never saw.

    ``over`` names what that operand was folded over -- the export's model
    points, or :data:`OVER_A_GROUP` for an aggregate scoped to a group --
    because the two are different populations and calling either by the
    other's name is the falsehood this sentence exists to avoid.

    **None is the population the caller could not read**, and the sentence
    then says less rather than guessing wider: the operand folded, no number
    stands for it, and whose rows it folded over goes unsaid. Naming the
    export's rows there would be a claim about which policies a total ran
    over, made by a caller that had just failed to find out.
    """
    named = ", ".join(operands) if operands else "this line's operand"
    population = f" over {over}" if over is not None else ""
    return (
        f"{named}: folded{population} inside this line, so no one policy's "
        "value is substituted for it here. Every value this step does show "
        "is the sampled policy's own."
    )


def sentence_for(tree: OpNode | None, periods: int | None) -> str | None:
    """Return what this node's operation means, in one sentence, or None.

    Args:
        tree: The node's own operation tree. Only a tree whose outermost
            node is a call has a sentence: an expression built out of
            operators means what its substituted arithmetic shows, and
            saying it again in words would be noise on every line of a
            model.
        periods: How many projection periods the node's own value has, or
            None for a per-policy value. Sentences that fold along the
            period axis name the length they folded.

    Returns:
        The sentence, or None where this node is not a call, where its
        operation is one the format does not name, or where the sentence
        could not be filled in at all.

    """
    if not isinstance(tree, Call):
        return None
    template = SENTENCES.get(tree.name)
    if template is None:
        return None
    try:
        return template.format_map(_Fields(tree, periods))
    except (IndexError, KeyError, ValueError):  # pragma: no cover - a template guard
        return None


class _Fields(dict[str, str]):
    """The fields one sentence may name, resolved off the node itself.

    A dict rather than a prepared mapping so that a template naming a
    field this call has no value for gets a stated absence instead of an
    exception: a sentence is enrichment, and one clause of it going
    ``not recorded`` is a smaller loss than a whole walk-through failing.
    """

    def __init__(self, call: Call, periods: int | None) -> None:
        """Build the field map for one call."""
        super().__init__()
        args = call.args
        self["operand"] = _named(args[0]) if args else "this line's operand"
        # The second and third arguments, where the operation takes them.
        # Counted rather than unpacked: an operation's arity is its own
        # business and a sentence naming only the first two of three
        # operands should not fail on the third being there.
        self["second"] = _named(args[1]) if len(args) > 1 else _NOT_RECORDED
        self["third"] = (
            _named(args[2])
            if len(args) > 2  # noqa: PLR2004 -- the third argument, by its index
            else _NOT_RECORDED
        )
        self["operands"] = ", ".join(col_refs(call)) or "no column at all"
        self["periods"] = (
            f"{periods} periods" if periods is not None else "the projection's periods"
        )
        for name, value in call.attrs:
            self[name] = _attribute(name, value)

    def __missing__(self, key: str) -> str:
        """Return the stated absence for a field this call does not carry."""
        return _NOT_RECORDED


def _attribute(name: str, value: AttrValue) -> str:
    """Return what one attribute reads as inside a sentence.

    A flag whose raw spelling means nothing on its own reads as what it
    means; everything else reads as itself, because a rate, a table name,
    a number of places and a day-count basis all say what they are.
    """
    phrases = _PHRASES.get(name)
    if phrases is not None and value in phrases:
        return phrases[value]
    if value is None:
        return _NOT_RECORDED
    return str(value)


def _named(node: OpNode) -> str:
    """Return how one operand is named inside a sentence.

    A column is its name, which is what an actuary calls it. A literal is
    its value, a sequence literal the first few of its members, since what
    identifies a band is what is written into it. Anything with structure
    -- another call, an arithmetic expression, a conditional -- is named by
    the columns it reads: a sentence is one sentence, and the tree behind
    it is on the node for a reader who wants the whole of it.
    """
    match node:
        case Col(name=name):
            return name
        case State(name=name):
            return f"the {name} state"
        case Lit(value=value):
            return _literal(value)
        case EngineNative(deps=deps):
            return f"an engine fragment over {', '.join(deps) or 'no column'}"
        case Call() | BinOp() | WhenThen():
            reads = col_refs(node)
            return ", ".join(reads) if reads else "the expression above it"
        case _:  # pragma: no cover - the union is closed
            return "the expression above it"


def _literal(value: object) -> str:
    """Return how a literal reads inside a sentence."""
    if not isinstance(value, tuple):
        return str(value)
    shown = ", ".join(str(member) for member in value[:_MEMBERS_SHOWN])
    if len(value) > _MEMBERS_SHOWN:
        shown = f"{shown}, and {len(value) - _MEMBERS_SHOWN} more"
    return f"[{shown}]"
