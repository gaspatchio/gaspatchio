# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Reads that select a row: ``lookup``, ``mortality.at`` and ``join``.

One gather under three clauses. What the three do not share is worth more
than what they do:

**How an operand finds the column it keys on.** A ``lookup`` binds by
*position*, in the processed basis's own ``columns`` order with the answer
removed -- and 11.1.24 says outright why the obvious alternative is worse
than useless: ``dimensions`` is a *set* of names, commonly alphabetical, and
an engine binding to it mis-keys any basis whose columns stand in another
order **silently**. The key families still line up, the gather still answers,
and the rate is wrong. ``mortality.at`` takes the other rule, by name, because
its ``dimensions`` attribute is written in operand order (11.1.11). A ``join``
takes neither: its key is named in its ``on`` attribute, and bound through the
node's own ``reads`` to the definition the key held when the join ran.

**What a key with no row means.** A lookup's miss policy says -- refuse and
name the key, the canonical NaN, or a finite fill -- and 11.1.24 makes a blank
answer cell at a reached key one of those misses rather than a defect in the
basis. A join has no such policy: 11.1.2 gives an unmatched left key a null
for every arriving column, and a null is a value this engine cannot hold or
answer over, so an unmatched key refuses and names the keys.

**When a refusal became knowable.** A key every one of whose columns arrived
with the book was checkable before anything was compiled, and the report says
so; a key a calculation produced was not, and the finding waits at completion
with its count and the first row -- outputs withheld either way.

**Only a right side with unique keys is a join this engine answers.** 11.1.2:
"a right side with repeated key values multiplies rows", under a left join
too, and one gathered answer per left row cannot say that. So a repeated key
refuses by name rather than being answered from whichever row the payload
happened to write first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import jax.numpy as jnp
import numpy as np

from gaspatchio.engines.format import join_key_sides
from gaspatchio_jax.capability import Capability
from gaspatchio_jax.checks import flag, spelled_position
from gaspatchio_jax.horizon import Horizon, aligned
from gaspatchio_jax.interning import ABSENT
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.tables import (
    Basis,
    answer_at,
    build,
    positions_of,
    validated_payload,
)
from gaspatchio_jax.typed import DomainRefused, Value, require_carrier

if TYPE_CHECKING:
    from gaspatchio.engines.format import Call
    from gaspatchio.engines.report import Group
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.tables import Landing, Storage
    from gaspatchio_jax.typed import Carrier, Shape

_LOOKUP: Final = "11.1.24"
_MORTALITY: Final = "11.1.10"
_JOIN: Final = "11.1.2"

# 11.1.24's key domain: text against text, a finite number against a number.
# A Boolean and a calendar day are payload cells (section 15) and are not
# keys, and the clause names every other pairing outside itself.
KEY_CARRIERS: Final[frozenset[Carrier]] = frozenset({"i64", "f64", "code"})

# The three miss policies, and the one a read that states none takes.
_RAISE: Final = "raise"
_NAN: Final = "nan"
_FILL: Final = "fill"
_POLICIES: Final[tuple[str, ...]] = (_RAISE, _NAN, _FILL)

# A left join's other meaning of a key with no row (11.1.2): the policy keeps
# a null in every arriving column, which this engine holds beside the value
# as an absence and publishes as the null it is.
_NULL: Final = "null"

# The join type this engine answers for. Every other one changes the row
# count, which an arriving column cannot.
_LEFT: Final = "left"

# How a mortality read's dimensions are listed in its one attribute. A
# join's keys are read by the format's own reader, ``join_key_sides``, as
# every other reader of the ``on`` attribute reads them (11.1.2).
_KEYS: Final = ","

# What a repeated key tuple means on a right side, in the clause's own words.
_MULTIPLIES = (
    "11.1.2 says a right side with repeated key values multiplies rows, and "
    "one gathered answer for each left row cannot say that"
)


@register(
    Capability(
        identifier="lookup",
        carriers=(KEY_CARRIERS,),
        attrs={"on_missing": _POLICIES},
        attrs_required=("table", "table_fingerprint", "on_missing"),
        checks=("lookup.miss_raise", "lookup.blank_answer", "lookup.key_range"),
        note=(
            "one operand per key column of the basis, bound in the basis's "
            "own column order; a scalar text key column whose every read is a key may "
            "carry a value that is not there, which is a miss under this "
            "read's own policy and not a refusal at the door"
        ),
        clause=_LOOKUP,
    )
)
def _lookup(call: Call, ctx: LoweringContext) -> Value:
    """Return the answer each key tuple selects from the basis this call names."""
    attrs = dict(call.attrs)
    storage = _basis_of(
        ctx,
        "table",
        str(attrs["table"]),
        str(attrs["table_fingerprint"]),
        Basis(name=f"the basis {attrs['table']!r}", clause=_LOOKUP),
    )
    keys = [
        require_carrier(ctx.lower(argument), KEY_CARRIERS, "lookup", _LOOKUP)
        for argument in call.args
    ]
    group: Group = "inputs" if _every_key_arrived(call, ctx) else "completion"
    return _selected(
        ctx,
        storage,
        keys,
        Miss(str(attrs["on_missing"]), attrs.get("fill_value"), group, _LOOKUP),
        answers_f64=True,
    )


@register(
    Capability(
        identifier="mortality.at",
        carriers=(KEY_CARRIERS,),
        attrs={
            "structure": ("aggregate", "select_ultimate", "joint"),
            "on_missing": _POLICIES,
        },
        attrs_required=("structure", "dimensions", "table", "table_fingerprint"),
        # 11.1.10: a select and ultimate basis is defined by the period its
        # durations are held at, and an aggregate or joint one has none.
        attrs_required_when={"select_period": ("structure", ("select_ultimate",))},
        # And a whole number where it is there: 11.1.10 calls it an integer
        # number of durations and states no interval, which is exactly what
        # the clamp holds a duration at. Both ends open says the type.
        attr_bounds={"select_period": (None, None)},
        checks=("lookup.miss_raise", "lookup.blank_answer", "lookup.key_range"),
        note=(
            "one operand per dimension the read names, bound to the basis by "
            "name; a miss policy the node does not state is raise (11.1.10); "
            "a scalar text key column whose every read is a key may carry a value "
            "that is "
            "not there, which is a miss under this read's own policy "
            "and not a refusal at the door"
        ),
        clause=_MORTALITY,
    )
)
def _mortality_at(call: Call, ctx: LoweringContext) -> Value:
    """Return one rate per row from a base, under the convention it is held on."""
    attrs = dict(call.attrs)
    storage = _basis_of(
        ctx,
        "table",
        str(attrs["table"]),
        str(attrs["table_fingerprint"]),
        Basis(name=f"the base {attrs['table']!r}", clause=_MORTALITY),
    )
    stated = [name.strip() for name in str(attrs["dimensions"]).split(_KEYS)]
    if len(stated) != len(call.args):
        raise DomainRefused(
            what=(
                f"this read names {len(stated)} dimensions and is written "
                f"with {len(call.args)} operands"
            ),
            move=(
                "write one operand per dimension the read names: this read "
                "binds by name, in the order it states them"
            ),
            clause=_MORTALITY,
        )
    named = dict(
        zip(
            stated,
            [
                require_carrier(
                    ctx.lower(argument), KEY_CARRIERS, "mortality.at", _MORTALITY
                )
                for argument in call.args
            ],
            strict=True,
        )
    )
    _names_are_the_bases(named, storage, attrs)
    held = _clamped(named, attrs)
    keys = [held[axis.name] for axis in storage.axes]
    group: Group = "inputs" if _every_key_arrived(call, ctx) else "completion"
    return _selected(
        ctx,
        storage,
        keys,
        # The base's miss policy is not on the record, and 11.1.10 states the
        # default a consumer applies where the node says nothing.
        Miss(
            str(attrs.get("on_missing") or _RAISE),
            attrs.get("fill_value"),
            group,
            _MORTALITY,
        ),
        answers_f64=True,
    )


@register(
    Capability(
        identifier="join",
        # No operands at all: 11.1.2 states a join's key in its ``on``
        # attribute rather than as an operand, and the node's ``reads`` bind
        # it. There is no operand domain to state.
        arity=(0,),
        attrs={"how": (_LEFT,), "on_missing": (_RAISE, _NULL)},
        attrs_required=("on", "right_fingerprint"),
        checks=("join.unmatched", "join.blank_arriving", "lookup.key_range"),
        note="a right side whose key tuples are unique",
        clause=_JOIN,
    )
)
def _join(call: Call, ctx: LoweringContext) -> Value:
    """Return the column the right side brings, for the row each key selects."""
    attrs = dict(call.attrs)
    fingerprint = str(attrs["right_fingerprint"])
    arriving = ctx.node.column or ""
    left, right = _sides(str(attrs["on"]))
    storage = _basis_of(
        ctx,
        "join",
        None,
        fingerprint,
        Basis(
            name=f"the right side of the join on {attrs['on']!r}",
            keys=right,
            answer=arriving,
            clause=_JOIN,
            duplicates_mean=_MULTIPLIES,
        ),
    )
    # 11.1.2: the node reads the key it was matched on, bound to the
    # definition the key held when the join ran, so the key resolves through
    # those reads -- never through whatever the run holds under the name.
    keys = [ctx.column(name) for name in left]
    group: Group = "inputs" if keys_all_arrived(call, ctx) else "completion"
    kept = str(attrs.get("on_missing") or _RAISE) == _NULL
    return _selected(
        ctx,
        storage,
        keys,
        Miss(
            _NULL if kept else _RAISE,
            None,
            group,
            _JOIN,
            check="join.unmatched",
            blank=None,
        ),
        answers_f64=False,
    )


def _sides(written: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return a join's left and right key names, as 11.1.2 spells the attribute.

    Read by the format's own reader, which every reader of the attribute
    shares, so the key the engine binds is the key the document's lineage
    names -- spaces and all: a column called ``" code "`` is not ``"code"``.
    An attribute naming no key, or a different number on each side, is not
    one a producer writes, and is refused rather than guessed at.
    """
    names, other = join_key_sides(written)
    if not names or len(other) != len(names) or not all(names) or not all(other):
        raise DomainRefused(
            what=(
                f"this join states its key as {written!r}, which does not "
                "name the same number of columns on each side"
            ),
            move="export the artifact again from the run that made the join",
            clause=_JOIN,
        )
    return names, other


def inspect_payload(call: Call, ctx: LoweringContext) -> None:
    """Apply the runtime payload checks before any book is supplied."""
    attrs = dict(call.attrs)
    if call.name == "join":
        _, right = _sides(str(attrs["on"]))
        payload = ctx.assumption("join", None, str(attrs["right_fingerprint"]))
        basis = Basis(
            name=f"the right side of the join on {attrs['on']!r}",
            keys=right,
            answer=ctx.node.column or "",
            clause=_JOIN,
            duplicates_mean=_MULTIPLIES,
        )
    else:
        payload = ctx.assumption(
            "table", str(attrs["table"]), str(attrs["table_fingerprint"])
        )
        basis = Basis(
            name=f"the basis {attrs['table']!r}",
            clause=_LOOKUP if call.name == "lookup" else _MORTALITY,
        )
    validated_payload(payload, interning=ctx.dictionary, basis=basis)


def _basis_of(
    ctx: LoweringContext, kind: str, name: str | None, fingerprint: str, basis: Basis
) -> Storage:
    """Return the storage one basis takes, building it once per run.

    Once, because a model reads one basis from six lines and a grid built six
    times is five grids nobody asked for -- and because a grid holds interned
    codes, which are this run's and no other's.

    The key is everything that decides what is built: the digest says which
    values, and the answer column *and the key columns* say which of them
    are keys. One right side joined on two different keys is two different
    grids, and a key that named only the digest would hand the second read
    the first read's axes.
    """
    key = f"{kind}:{fingerprint}:{basis.answer or ''}:{','.join(basis.keys or ())}"
    held = ctx.bases.get(key)
    if held is None:
        held = build(
            ctx.assumption(kind, name, fingerprint),
            interning=ctx.dictionary,
            basis=basis,
        )
        ctx.bases[key] = held
        if held[1] is not None:
            ctx.note(held[1])
    return held[0]


def _clamped(named: dict[str, Value], attrs: dict[str, Any]) -> dict[str, Value]:
    """Return the dimensions with a select and ultimate duration held at its period.

    Bounded above only. Nothing is excluded below, because a duration below
    the first row of the base is a key the base does not carry and is
    answered by the miss policy, not by a floor this operation invents
    (11.1.10).
    """
    if str(attrs["structure"]) != "select_ultimate":
        return named
    period = attrs.get("select_period")
    duration = named.get("duration")
    if not isinstance(period, int) or isinstance(period, bool) or duration is None:
        raise DomainRefused(
            what=(
                "this read is on a select and ultimate base and states no "
                "whole select period beside a duration to hold at it"
            ),
            move=(
                "export the artifact again from the model that registered the "
                "base, so the select period travels with the convention"
            ),
            clause=_MORTALITY,
        )
    return named | {
        "duration": Value(
            jnp.minimum(duration.array, period),
            duration.carrier,
            duration.shape,
            duration.dtype,
            duration.horizon,
        )
    }


def _names_are_the_bases(
    named: dict[str, Value], storage: Storage, attrs: dict[str, Any]
) -> None:
    """Check that the names this read states are the basis's own key columns.

    Before the clamp rather than after it: which operand the select period
    holds is the one this read *calls* ``duration``, so a read whose names do
    not answer to the base has to be met here, where the sentence can name
    the dimension nobody could find.

    Raises:
        DomainRefused: If the names the read states are not the basis's key
            columns.

    """
    wanted = [axis.name for axis in storage.axes]
    if sorted(named) != sorted(wanted):
        raise DomainRefused(
            what=(
                f"this read names the dimensions {sorted(named)} and the base "
                f"{attrs['table']!r} is keyed on {wanted}"
            ),
            move=(
                "check the read's dimension names against the columns the "
                "base carries: this read binds by name, and a lookup binds by "
                "position"
            ),
            clause=_MORTALITY,
        )


# The three reads that select a row, and so can be answered before anything
# is compiled when every key of them came with the book.
KEYED_READS: Final[frozenset[str]] = frozenset({"lookup", "mortality.at", "join"})


def keys_all_arrived(call: Call, ctx: LoweringContext) -> bool:
    """Return whether every key of one row-selecting read came with the book."""
    if call.name == "join":
        left, _right = _sides(str(dict(call.attrs).get("on") or ""))
        return bool(left) and all(ctx.resolves_to_an_input(name) for name in left)
    return _every_key_arrived(call, ctx)


def _every_key_arrived(call: Call, ctx: LoweringContext) -> bool:
    """Return whether every key was a column that arrived or a value written out.

    The question is about the node each operand *resolves to*, never about
    the name it is written under. A model that writes over an arriving
    column -- ``duration = duration + 10``, which is an ordinary line -- has
    a document carrying both an input node and a computed one under that
    name, and the formula reads the computed one. Deciding on the name alone
    called that key an arrival, put its refusal in the inputs group, and
    closed with "Nothing was computed." about a run that had computed the
    key it was refusing over.
    """
    from gaspatchio.engines.format import Col, Lit  # noqa: PLC0415 -- one node test

    return all(
        isinstance(argument, Lit)
        or (isinstance(argument, Col) and ctx.resolves_to_an_input(argument.name))
        for argument in call.args
    )


@dataclass(frozen=True, slots=True)
class Miss:
    """What a key with no row means here, and when it became knowable.

    Attributes:
        policy: ``raise``, ``nan`` or ``fill``. A join has none of its own
            and takes ``raise``, because 11.1.2's null is not a value this
            engine states an answer over.
        fill: The finite decimal a fill answers with, where that is the
            policy, and None otherwise.
        group: Which group of the report the refusal belongs in -- decided
            by whether every key arrived with the book.
        clause: What the refusal rests on.
        check: The declared check the flag is raised under where the finding
            waits for completion and the key reaches no row at all.
        blank: The declared check for a key that reaches a row whose answer
            cell is blank, where that is a different finding, and **None**
            where a blank cell is not a miss at all. A join is the second
            case: 11.1.2 gives an *unmatched key* a null for every arriving
            column, and a matched row whose cell is empty is not an unmatched
            key -- it is an arriving column that is null there, which is what
            the right side says it is.

    """

    policy: str
    fill: object
    group: Group
    clause: str
    check: str = "lookup.miss_raise"
    blank: str | None = "lookup.blank_answer"


def _selected(
    ctx: LoweringContext,
    storage: Storage,
    keys: list[Value],
    miss: Miss,
    *,
    answers_f64: bool,
) -> Value:
    """Return the answer at each key tuple, with a miss decided as the read asks."""
    if len(keys) != len(storage.axes):
        raise DomainRefused(
            what=(
                f"this read is written with {len(keys)} keys and the basis is "
                f"keyed on {len(storage.axes)} columns"
            ),
            move="write one operand per key column the basis carries",
            clause=miss.clause,
        )
    if answers_f64 and storage.carrier != "f64":
        raise DomainRefused(
            what=(
                f"the basis answers {storage.carrier} and this clause states "
                "its answer domain as a floating-point column"
            ),
            move="read the basis through a join, or export it with f64 rates",
            clause=miss.clause,
        )
    axis = aligned(*keys)
    on_one_axis = [
        Value(array, key.carrier, axis.shape, key.dtype, axis.horizon)
        for array, key in zip(axis.arrays, keys, strict=True)
    ]
    if axis.horizon is not None:
        # A key that arrived per policy is repeated across the periods, so
        # every key of one query stands at one cell rather than one of them
        # standing at a row and the rest at cells of it.
        on_one_axis = [
            Value(
                jnp.broadcast_to(one.array, (one.array.shape[0], axis.horizon.bucket)),
                one.carrier,
                one.shape,
                one.dtype,
                axis.horizon,
            )
            for one in on_one_axis
        ]
    try:
        landing = positions_of(storage, tuple(on_one_axis), on_the_host=ctx.on_the_host)
    except DomainRefused as refused:
        raise _in_group(refused, miss.group) from refused
    missing = _missing_value(storage.carrier, miss)
    if miss.policy == _RAISE:
        _refuse_a_miss(ctx, storage, on_one_axis, landing, miss, axis.horizon)
    if miss.policy == _NULL:
        # 11.1.2's null for a key with no row, kept beside the answer rather
        # than standing in it: the cell holds a placeholder no reader sees.
        ctx.absent = ~landing.hit
    dtype = _answer_dtype(storage.carrier)
    return Value(
        answer_at(storage, landing.position, landing.hit, missing=missing),
        storage.carrier,
        axis.shape,
        f"list[{dtype}]" if axis.shape == "list" else dtype,
        axis.horizon,
    )


# The value a miss publishes where the policy does not name one, for the
# carriers that are not ``f64`` and so have no NaN to stand in.
_ABSENT_OF: Final[dict[str, int]] = {"code": ABSENT}


def _missing_value(carrier: Carrier, miss: Miss) -> float | bool:
    """Return what stands at a miss under this policy, refusing an unpaired fill."""
    fill, clause = miss.fill, miss.clause
    if miss.policy != _FILL:
        # What stands where there is no answer, per carrier. A text answer
        # takes the absent code rather than 0, which is the code of whatever
        # string this run interned first -- a miss would otherwise publish a
        # plan identifier nobody read.
        return math.nan if carrier == "f64" else _ABSENT_OF.get(carrier, 0)
    if not isinstance(fill, (int, float)) or isinstance(fill, bool):
        raise DomainRefused(
            what=(
                f"this read fills a miss with {fill!r}, and a fill is the "
                "finite decimal the clause pairs with that policy"
            ),
            move='state a finite fill_value, or read the miss as "nan"',
            clause=clause,
        )
    if not math.isfinite(float(fill)):
        raise DomainRefused(
            what=f"this read fills a miss with {fill!r}, which is not finite",
            move="state a finite fill_value",
            clause=clause,
        )
    return float(fill)


# The two ways a key fails to answer, each with the sentence it is and the
# move it takes. They are one refusal in the report and two different things
# to be told: a basis that has no row for a key is short a row, and a basis
# whose row is there with nothing in its answer cell is short a rate.
_NO_ROW = (
    "reach no row the basis carries",
    "extend the basis, or say in the model what a key it does not carry means",
)
_NO_RATE = (
    "reach a row whose answer cell is not there, or is not a finite number",
    (
        "fill the cells the model's own keys reach, or state a miss policy "
        "that says what a blank one means"
    ),
)


def _refuse_a_miss(  # noqa: PLR0913, PLR0917 -- one argument per thing a miss is about
    ctx: LoweringContext,
    storage: Storage,
    keys: list[Value],
    landing: Landing,
    miss: Miss,
    horizon: Horizon | None = None,
) -> None:
    """Refuse the keys the basis does not answer, at the moment they are knowable.

    Where every key arrived with the book this is decided here and now, and
    the report names the first tuple and counts the rest: a run that has not
    computed anything yet can say exactly which key it could not answer.
    Where a calculation produced a key it is a flag instead, read at
    completion with every output withheld.

    **The two causes are told apart.** 11.1.24 makes a blank answer cell at a
    reached key a miss, which is right -- and it is not the same finding as a
    key the basis has no row for at all. One says extend the basis; the other
    says fill the cell. A reader handed "no rate here" for both has to go and
    look at the payload to find out which.

    Raises:
        DomainRefused: If a key that arrived reaches no answer.

    """
    inside = (
        horizon.active
        if horizon is not None
        else jnp.ones(landing.reached.shape, dtype=bool)
    )
    if miss.group != "inputs" or not ctx.on_the_host:
        # Traced masks, not host reads: a check whose operands a calculation
        # produced is a flag the trace carries to completion, and reading it
        # back here would be reading it before the calculation that decides
        # it has run. Two flags rather than one, so the completion path tells
        # a key with no row from a row with no rate exactly as the pre-flight
        # path does.
        blank_cells = landing.reached & ~landing.hit & inside
        flag(miss.check, ~landing.reached & inside)
        if miss.blank is not None:
            flag(miss.blank, blank_cells)
        elif storage.carrier == "code":
            # A matched row whose arriving cell is empty is the arriving
            # column being null there, and text carries that honestly as the
            # absent code. Symmetry with the pre-flight path: what that one
            # notes, this one notes -- and it says it through the flag
            # protocol, because inside a program being built there is no count
            # to read. A noted flag withholds nothing; it is counted at
            # completion and reported in the run's own words.
            flag(
                "join.blank_arriving",
                blank_cells,
                note=_AN_ABSENT_COLUMN.format(column=ctx.node.column or "this column"),
            )
        else:
            flag("join.blank_arriving", blank_cells)
        return
    reached = np.asarray(landing.reached)
    hit = np.asarray(landing.hit)
    active = np.asarray(inside)
    empty_cells = reached & ~hit & active
    if miss.blank is None:
        _an_absent_arriving_column(ctx, storage, empty_cells, miss)
        empty_cells = np.zeros(reached.shape, dtype=bool)
    for caught, name, (what, move) in (
        (~reached & active, miss.check, _NO_ROW),
        (empty_cells, miss.blank or miss.check, _NO_RATE),
    ):
        found = np.flatnonzero(caught.reshape(-1))
        if not found.size:
            continue
        first = int(found[0])
        where = spelled_position(first, caught.shape)
        written = ", ".join(
            f"{axis.name}={_spelled(ctx, key, first)}"
            for axis, key in zip(storage.axes, keys, strict=True)
        )
        raise DomainRefused(
            what=(
                f"{found.size} of the keys this read was given {what} "
                f"({name}) -- the first at {where}, which is ({written})"
            ),
            move=move,
            clause=miss.clause,
            group=miss.group,
            count=int(found.size),
        )


# What a matched row with an empty arriving text cell is. One sentence, and
# one place it is said from: the flag every run raises for it, counted at
# completion. The pre-flight path meets the same cells and stays quiet about
# them for exactly that reason -- it refuses the carriers that have no absent
# value and leaves the note to the run.
_AN_ABSENT_COLUMN: Final = (
    "rows of this join match a right-side row whose {column!r} is not there; "
    "the column is null for them, and a read keyed on it is a miss"
)


def _an_absent_arriving_column(
    ctx: LoweringContext, storage: Storage, empty: np.ndarray, miss: Miss
) -> None:
    """Report -- or refuse -- a matched row whose arriving cell carries nothing.

    11.1.2's null is the answer for an *unmatched* key, and this is not one:
    the key matched and the right side has nothing in that column for it.
    Level 4's right side is the case, with a surrender-charge identifier that
    is null on the two plans that have no schedule at all.

    Text carries that honestly: the absent code is a code no string is ever
    minted onto, so the column publishes a null and a read keyed on it is the
    miss 11.1.24 makes of a null key. A number has no such code -- every
    value a number could take is a key some basis could legitimately hold --
    so a blank numeric cell refuses here and says so.

    Raises:
        DomainRefused: If a blank arriving cell is one this engine has no
            absent value for.

    """
    # A count read here rather than carried to completion: this is a note and
    # not a refusal, and nothing is withheld over it.
    found = int(np.count_nonzero(empty))
    if not found:
        return
    column = ctx.node.column or "this column"
    if storage.carrier == "code":
        # Said once, at completion, off the flag every run raises for it: a
        # note here as well would be one fact a reader met twice.
        return
    first = int(np.flatnonzero(empty.reshape(-1))[0])
    raise DomainRefused(
        what=(
            f"{found} rows of this join match a right-side row whose "
            f"{column!r} carries no value -- the first at row {first} -- and "
            "this engine holds no absent value for a column of that type"
        ),
        move=(
            "fill the right side's blank cells, or say in the model what an "
            "arriving column with nothing in it means"
        ),
        clause=miss.clause,
        group=miss.group,
        count=found,
    )


def _spelled(ctx: LoweringContext, key: Value, position: int) -> object:
    """Return one key's value at one row, as the model wrote it rather than held it."""
    held = np.asarray(key.array).reshape(-1)[position]
    if key.carrier == "code":
        return ctx.dictionary.text_of(int(held))
    if key.carrier == "i64":
        return int(held)
    return float(held)


def _shape_of(keys: list[Value]) -> Shape:
    """Return the shape the answer takes: per period where any key is (11.1.18)."""
    return "list" if any(key.shape == "list" for key in keys) else "scalar"


# What an answer column's carrier is called where a value carries its own
# type name (section 10).
_ANSWER_DTYPE: Final[dict[str, str]] = {
    "f64": "f64",
    "i64": "i64",
    "bool": "bool",
    "code": "str",
}


def _answer_dtype(carrier: Carrier) -> str:
    """Return the type name the answer column stands under."""
    return _ANSWER_DTYPE[carrier]


def _in_group(refused: DomainRefused, group: Group) -> DomainRefused:
    """Return the same refusal in the group the read knows it belongs to."""
    return DomainRefused(
        refused.what,
        refused.move,
        refused.clause,
        group=group,
        count=refused.count,
    )
