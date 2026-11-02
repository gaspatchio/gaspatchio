# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compiled state machine, as one scan over section 16.1's own subset.

Everything else this engine lowers has a closed form. A rollforward does not,
and that is the whole reason it exists: a model escalates to a state machine
when a within-period charge depends on the running balance -- a cost of
insurance struck on the net amount at risk, a credited rate held between a
floor and a cap, a benefit base ratcheting to a fund's high-water mark. So
this family is one ``lax.scan`` down the periods, with the states as the
carry, and the operations applied inside a period in the order the compilation
serialized them.

**The order inside a period is the calculation.** 16.1 fixes it: seed each
state's end-of-period from its beginning-of-period, then apply the increments
in array order, each one reading the balance the one before it left. A
``State`` operand at ``@bop`` reads the value fixed at the start of the
period and one at ``@eop`` reads what the earlier increments of that period
left -- which is what makes a ratchet to a fund's within-period close a
different number from a ratchet to its opening, and why the two points are
carried apart rather than folded into one balance.

**Extraction is at end of period and nowhere else.** 16.1 admits
``point: "eop"``, states outright that extraction at ``bop`` does not acquire
portable value semantics from it, and this engine refuses a ``bop`` read by
name rather than answering the balance that happens to be lying in the carry.
A beginning-of-period balance is a real quantity and a second implementation
answering one would be answering a contract nobody has written.

**The subset is a gate, not a best effort.** A compilation whose body is
outside 16.1 -- tracked increments, a lapse condition, a contract boundary, a
non-portable binding, an operation the list does not name, a rounded charge,
an ungated ratchet -- refuses by name with the clause, and refuses at
*inspection* where the document carries the compilation's own node, so the
reader is told before the book is read. 16.2's tracked movement and 16.3's raw
Struct are not here at all: they are refused by name in
:data:`gaspatchio_jax.lowerings.REFUSED`, which is where this engine states
what it will not do rather than what it has not got round to.

**What makes two rollforward programs different shapes.** The step count and
the state count, and both are fixed by the document rather than by the book:
the count comes off the schedule payload the body names and the states off the
body's own list, so two batches of one model compile one program. The
compilation's identity is inside the node's tree bytes and therefore inside
``graph_fingerprint``, which is what ``cache.report_key`` keys on -- so a
machine with another step count or another state count is another key already,
and the axis the balances stand on travels in that key's ``buckets`` beside
the projection's own. The axis is minted here from the schedule's period
count, which is a host number the document carries and never a traced one, so
nothing about a *shape* is read out of an argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

import jax.numpy as jnp
import numpy as np
from jax import lax

from gaspatchio_jax.capability import Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import Horizon, bucket_of
from gaspatchio_jax.ieee import multiplied
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import DomainRefused, Value

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext

__all__ = [
    "FACET",
    "MACHINE",
    "MACHINE_DOORS",
    "PRODUCER_URL",
    "ROLLFORWARD_KIND",
    "STATE_KIND",
    "body_of",
    "declares",
    "fingerprint_of",
    "machine_tree",
    "outside_the_subset",
    "outside_the_types",
    "state_map",
]

# Where the machine travels, and the one reading of it this subsection is
# stated over.
FACET: Final = "gaspatchio_rollforward_ir"
SCHEMA_URL: Final = (
    "https://gaspatchio.dev/schemas/facets/gaspatchio_rollforward_ir-v0-preview.1.json"
)

# What a facet says it was written under (§6). A facet carries both, and the
# published schema requires both, so an adapter writing one and not the other
# builds a document no second reader accepts.
PRODUCER_URL: Final = "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3"

_SUBSET: Final = "16.1"

# The node kinds section 16 mints, in the two reserved namespaces of 8.1.
STATE_KIND: Final = "state"
ROLLFORWARD_KIND: Final = "rollforward"

# The identifier a compilation's own node carries as its whole tree.
MACHINE: Final = "rollforward"

# The three doors onto a compilation, whose arguments are the *machine's*
# operand run and never the call's own (§12.1) -- so a running state stands
# among them, and nothing walking an operation tree may read them as operands.
MACHINE_DOORS: Final[frozenset[str]] = frozenset(
    {"rollforward.state", "rollforward.increment", "rollforward.struct"}
)

# The two declared points, and the one extraction 16.1 admits.
_BOP: Final = "bop"
_EOP: Final = "eop"
_POINTS: Final = [_BOP, _EOP]

# Everything the subsection fixes about the body, read as a whole rather than
# field by field: a body carrying anything else is outside it.
_BODY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "points",
        "states",
        "increments",
        "track_increments",
        "lapse_when_all_non_positive",
        "contract_boundary",
        "engine_binding",
        "batch_axes",
        "schedule",
    }
)
_PORTABLE: Final = "portable"
_BATCH_AXES: Final[list[str]] = ["policy"]

# The schedule form the subsection states, and the field the period count is
# read from. No model source, sidecar count or list operand supplies a
# fallback, so a body whose schedule is any other form is outside the subset
# rather than sized from something else.
_SCHEDULE_FORM: Final[dict[str, object]] = {
    "kind": "from_calendar_grid",
    "frequency": "1M",
    "calendar": "NullCalendar",
    "convention": "Unadjusted",
    "day_count": "OneTwelfth",
    "anchor": "month_end",
}
_PERIOD_COUNT: Final = "n_periods"

# The second form the subsection states: a fixed-step axis, which has no
# calendar at all and supplies only its step count. Its recipe is exactly the
# kind, the count and one of the two ways a step is written.
_FIXED_STEP: Final = "fixed_step"
_FIXED_STEP_FIELDS: Final[tuple[frozenset[str], ...]] = (
    frozenset({"kind", _PERIOD_COUNT, "step_years"}),
    frozenset({"kind", _PERIOD_COUNT, "steps_per_year"}),
)

# The six operations the list admits, each with the operand counts and the
# settings the subsection states for it. The list is closed: an unrecognized
# operation, an admitted one with another arity, or another settings shape
# refuses.
_ADMITTED: Final[dict[str, tuple[int, tuple[str, ...]]]] = {
    "Add": (1, ()),
    "Subtract": (1, ()),
    "Charge": (2, ("round_charge",)),
    "Grow": (2, ("round_charge",)),
    "Floor": (1, ("value",)),
    "Ratchet": (3, ()),
}

# The two whose trailing operand documents the running balance they change,
# and whose one setting must be absent rather than a rounding.
_ROUNDED: Final = "round_charge"
_BOUND: Final = "value"


@dataclass(frozen=True, slots=True)
class _Source:
    """Where one operand of one step gets its numbers from.

    Either a column the compilation's versioned reads bind, already laid out
    as ``[T, B]`` and sliced by the scan, or a running state read at one of
    the two declared points -- which has no array of its own because it is
    whatever the carry holds at that moment.
    """

    kind: Literal["column", "state"]
    at: int | None = None
    state: int | None = None
    point: str = _EOP


@dataclass(frozen=True, slots=True)
class _Step:
    """One increment, with its operands resolved and its place in the chain."""

    ordinal: int
    operation: str
    target: int
    named: str
    amount: _Source | None = None
    gate: _Source | None = None
    lift: _Source | None = None
    bound: float = 0.0


def outside_the_subset(body: Mapping[str, Any]) -> str | None:  # noqa: C901, PLR0911 -- one return per condition 16.1 states, and the subsection states them as a list
    """Return why one compilation body is outside 16.1, or None where it is not.

    Read once and used twice: by the plan, on a document that carries the
    compilation's own node, so a machine this engine will not run is refused
    before the book is opened; and by :func:`state_map`, on every document,
    because a vector case carries the body and no node to hang it on.
    """
    unknown = sorted(set(body) - _BODY_FIELDS)
    if unknown:
        return (
            f"this compilation's record carries {', '.join(unknown)}, which "
            "this subsection's executable subset does not state"
        )
    absent = sorted(_BODY_FIELDS - set(body))
    if absent:
        return (
            f"this compilation's record states no {', '.join(absent)}, and "
            "this subset is stated over a machine that declares all nine"
        )
    if not isinstance(body.get("schedule"), str):
        return (
            f"this compilation names its schedule as {body.get('schedule')!r}, "
            "and a schedule is identified by the digest of its own payload"
        )
    if list(body.get("points") or ()) != _POINTS:
        return (
            f"this compilation declares the points {list(body.get('points') or ())}, "
            "and this subset is stated over a beginning and an end of period"
        )
    if body.get("engine_binding") != _PORTABLE:
        return (
            f"this compilation is bound to {body.get('engine_binding')!r} rather "
            "than to the portable machine, so its numbers are one engine's own"
        )
    if list(body.get("batch_axes") or ()) != _BATCH_AXES:
        return (
            f"this compilation runs over the axes "
            f"{list(body.get('batch_axes') or ())}, and this subset is stated "
            "over the policy axis alone"
        )
    # The chain before the switches, so a reader is told the sharpest thing
    # that is wrong with the machine. A rounded charge is a rounded charge
    # whether or not the machine also tracks what its steps moved, and it is
    # the sentence that sends them to the line they have to change.
    outside = _outside_the_states(body) or _outside_the_increments(body)
    if outside is not None:
        return outside
    if body.get("track_increments"):
        return (
            "this compilation tracks what each step moved, which is section "
            "16.2's door and not this subset: 16.1 is stated over a machine "
            "carrying track_increments false"
        )
    if list(body.get("lapse_when_all_non_positive") or ()):
        return (
            "this compilation stops when its balances go non-positive, and a "
            "lapse condition does not acquire portable value semantics here"
        )
    if body.get("contract_boundary") is not None:
        return (
            "this compilation carries a contract boundary, and a stopping "
            "test does not acquire portable value semantics here"
        )
    return None


def _outside_the_states(body: Mapping[str, Any]) -> str | None:
    """Return why the declared states are outside 16.1, or None."""
    states = list(body.get("states") or ())
    names = [str(one.get("name") or "") for one in states]
    if not names or any(not name for name in names):
        return "this compilation declares a state with no name"
    if len(set(names)) != len(names):
        return (
            "this compilation declares two states of one name, so a read of "
            "that name selects neither of them"
        )
    outside = [
        name
        for name, one in zip(names, states, strict=True)
        if not _is_column(one.get("init"))
    ]
    if outside:
        return (
            f"the opening value of {', '.join(outside)} is an expression, and "
            "this subset opens each state at one column the compilation reads"
        )
    return None


def _outside_the_increments(body: Mapping[str, Any]) -> str | None:
    """Return why the chain of increments is outside 16.1, or None."""
    names = [str(one.get("name") or "") for one in body.get("states") or ()]
    for position, increment in enumerate(body.get("increments") or (), start=1):
        operation = str(increment.get("operation") or "")
        admitted = _ADMITTED.get(operation)
        if admitted is None:
            return (
                f"step {position} of this compilation is {operation!r}, which "
                "is outside the operations this subset admits"
            )
        arity, settings = admitted
        operands = list(increment.get("operands") or ())
        if len(operands) != arity:
            return (
                f"step {position} of this compilation is a {operation} over "
                f"{len(operands)} operands, and this subset states {arity}"
            )
        if sorted(increment.get("settings") or {}) != sorted(settings):
            return (
                f"step {position} of this compilation is a {operation} "
                f"configured with {sorted(increment.get('settings') or {})}, and "
                f"this subset states {list(settings)}"
            )
        target = str(increment.get("target") or "")
        if not target.endswith(f"@{_EOP}") or target.partition("@")[0] not in names:
            return (
                f"step {position} of this compilation lands on {target!r}, and "
                "every step of this subset lands on a declared state at its "
                "end of period"
            )
        refused = _outside_this_operation(position, operation, increment, names, target)
        if refused is not None:
            return refused
    return None


def _outside_this_operation(  # noqa: C901, PLR0911 -- one return per way one operation's own shape leaves the subsection
    position: int,
    operation: str,
    increment: Mapping[str, Any],
    names: Sequence[str],
    target: str,
) -> str | None:
    """Return why one admitted operation's own shape is outside 16.1, or None."""
    operands = list(increment.get("operands") or ())
    settings = dict(increment.get("settings") or {})
    if operation in ("Charge", "Grow"):
        if settings.get(_ROUNDED) is not None:
            return (
                f"step {position} of this compilation rounds its {operation.lower()}, "
                "and a rounded charge is outside this subset"
            )
        if operands[1] != {"op": "state", "name": target}:
            return (
                f"step {position} of this compilation is a {operation} whose "
                f"running balance is {operands[1]!r} rather than the {target} "
                "it changes"
            )
        return None
    if operation == "Floor":
        bound = settings.get(_BOUND)
        if not isinstance(bound, (int, float)) or isinstance(bound, bool):
            return (
                f"step {position} of this compilation is a floor whose lower "
                f"bound is {bound!r}, and this subset states a finite number"
            )
        if not np.isfinite(float(bound)):
            return (
                f"step {position} of this compilation is a floor whose lower "
                f"bound is {bound!r}, and this subset states a finite number"
            )
        if operands[0] != {"op": "state", "name": target}:
            return (
                f"step {position} of this compilation is a floor on "
                f"{operands[0]!r} rather than on the {target} it changes"
            )
        return None
    if operation == "Ratchet":
        lifts = operands[0]
        if not _is_state(lifts, names):
            return (
                f"step {position} of this compilation ratchets to {lifts!r}, "
                "and this subset lifts to a declared state at a declared point"
            )
        if not _is_column(operands[1]):
            return (
                f"step {position} of this compilation is gated on {operands[1]!r}, "
                "and this subset gates a ratchet on one column of truth values"
            )
        if operands[2] != {"op": "state", "name": target}:
            return (
                f"step {position} of this compilation is a ratchet whose "
                f"running balance is {operands[2]!r} rather than the {target} "
                "it changes"
            )
        return None
    return _outside_an_operand(position, operands[0], names)


def _outside_an_operand(
    position: int, operand: Mapping[str, Any], names: Sequence[str]
) -> str | None:
    """Return why one add's or subtract's operand is outside 16.1, or None."""
    if _is_column(operand) or _is_state(operand, names):
        return None
    return (
        f"step {position} of this compilation moves {operand!r}, and every "
        "operand of this subset is a column the compilation reads or one of "
        "its own running states"
    )


def _is_column(operand: object) -> bool:
    """Return whether one operand is a bare column read."""
    return isinstance(operand, dict) and operand.get("op") == "col"


def _is_state(operand: object, names: Sequence[str]) -> bool:
    """Return whether one operand reads a declared state at a declared point."""
    if not isinstance(operand, dict) or operand.get("op") != "state":
        return False
    state, _, point = str(operand.get("name") or "").partition("@")
    return state in names and point in _POINTS


def machine_tree(fingerprint: str) -> dict[str, Any]:
    """Return the one-call tree a compilation's own node carries, for an identity.

    A running state has no operation tree of its own -- nothing on the model
    defines it and it reads nothing (§8.1) -- so the call its value comes out
    of is the one its compilation's node carries, and this is where that call
    is written rather than at each of the places that need it.
    """
    return {
        "op": "call",
        "name": MACHINE,
        "args": [],
        "attrs": {"fingerprint": fingerprint},
    }


def fingerprint_of(tree: Mapping[str, Any] | None) -> str:
    """Return the identity one compilation node's tree carries, or the empty string.

    The node's whole tree is the identifier and one attribute (§12.1), and a
    fingerprint is the only thing that reaches the machine behind it -- so the
    reading of those bytes is written once here rather than at each of the
    three places that need it.
    """
    if not isinstance(tree, dict):
        return ""
    attrs = tree.get("attrs")
    if not isinstance(attrs, dict):
        return ""
    stated = attrs.get("fingerprint")
    return stated if isinstance(stated, str) else ""


def declares(document: Mapping[str, Any], fingerprint: str, reference: str) -> bool:
    """Return whether one machine declares the running state a reference names."""
    body = body_of(document, fingerprint)
    if body is None:
        return False
    state, _, point = reference.partition("@")
    if point not in body.get("points", ()):
        return False
    return any(str(one.get("name")) == state for one in body.get("states") or ())


def body_of(document: Mapping[str, Any], fingerprint: str) -> Mapping[str, Any] | None:
    """Return the machine one identity names, or None where the file carries none."""
    facet = (document.get("facets") or {}).get(FACET)
    if not isinstance(facet, dict):
        return None
    stated = facet.get("_schemaURL")
    if isinstance(stated, str) and stated != SCHEMA_URL:
        return None
    body = (facet.get("compilations") or {}).get(fingerprint)
    return body if isinstance(body, dict) else None


def outside_the_types(body: Mapping[str, Any], dtypes: Mapping[str, str]) -> str | None:
    """Check the compilation's versioned carriers before generic widening."""
    for state in body.get("states") or ():
        name = str(state["init"]["name"])
        if dtypes.get(name) != "f64":
            return (
                f"state {state['name']!r} opens at {name!r}, carried as "
                f"{dtypes.get(name, 'unbound')}; open it at a scalar f64 column"
            )
    for increment in body.get("increments") or ():
        for position, operand in enumerate(increment["operands"]):
            if operand.get("op") != "col":
                continue
            name = str(operand["name"])
            carrier = (
                "bool"
                if increment["operation"] == "Ratchet" and position == 1
                else "f64"
            )
            if dtypes.get(name) not in (carrier, f"list[{carrier}]"):
                return (
                    f"{increment['operation']} reads {name!r}, carried as "
                    f"{dtypes.get(name, 'unbound')}; supply a scalar or list "
                    f"{carrier} column for this operand"
                )
    return None


def _require_carrier(value: Value, name: str, carrier: str) -> None:
    """Refuse a carrier outside this family's narrower domain before widening.

    Raises:
        DomainRefused: When an amount and a mask would change places.

    """
    if value.carrier != carrier:
        raise DomainRefused(
            what=(
                f"this compilation reads {name!r} as {value.dtype}, requiring {carrier}"
            ),
            move=f"supply a {carrier} column explicitly for this operand",
            clause=_SUBSET,
        )


def _the_body(ctx: LoweringContext, fingerprint: str) -> Mapping[str, Any]:
    """Return the machine this call names, refusing a file that does not carry it.

    Raises:
        DomainRefused: If the file carries no body for this identity, or the
            body it carries is outside the subset.

    """
    body = body_of(ctx.document, fingerprint)
    if body is None:
        raise DomainRefused(
            what=(
                f"this line reads the compiled rollforward {fingerprint}, and "
                "this artifact carries no machine under that identity"
            ),
            move=(
                'export the artifact again with profile="executable" from the '
                "process the rollforward was compiled in, so the machine "
                "travels with the node that names it"
            ),
            clause=_SUBSET,
        )
    outside = outside_the_subset(body)
    if outside is not None:
        raise DomainRefused(what=outside, move=_RUN_IT_ON_POLARS, clause=_SUBSET)
    return body


_RUN_IT_ON_POLARS: Final = (
    "run this model on Polars: this engine runs the bounded portable machine "
    "this subsection states and refuses every other one by name"
)


def _periods(ctx: LoweringContext, body: Mapping[str, Any]) -> int:
    """Return the step count the body's schedule supplies.

    The schedule and nothing else: the subsection says outright that no model
    source, sidecar period count or list operand may supply a fallback, so a
    schedule outside the form it states leaves the count unknown rather than
    guessed.

    Raises:
        DomainRefused: If the schedule is outside the two forms 16.1 states,
            or its period count is not a non-negative whole number.

    """
    payload = ctx.assumption("schedule", None, str(body["schedule"]))
    outside = [
        f"{field}={payload.get(field)!r}"
        for field, stated in _SCHEDULE_FORM.items()
        if payload.get(field) != stated
    ]
    if payload.get("kind") == _FIXED_STEP:
        outside = (
            []
            if frozenset(payload) in _FIXED_STEP_FIELDS
            else [f"fields {sorted(payload)!r}"]
        )
    if outside:
        return _refuse_schedule(
            f"this compilation runs on a schedule of {', '.join(outside)}, and "
            "this subset states a month-end calendar grid at a monthly cadence "
            "or a fixed step"
        )
    count = payload.get(_PERIOD_COUNT)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return _refuse_schedule(
            f"this compilation's schedule states {count!r} periods, and a "
            "machine runs a non-negative whole number of them"
        )
    return count


def _refuse_schedule(what: str) -> int:
    """Refuse one schedule by name.

    Raises:
        DomainRefused: Always -- the caller has already decided.

    """
    raise DomainRefused(what=what, move=_RUN_IT_ON_POLARS, clause=_SUBSET)


def _bound_column(
    ctx: LoweringContext,
    bound: Mapping[str, Value],
    name: str,
    periods: int,
    *,
    gate: bool = False,
) -> jax.Array:
    """Return one bound column laid out as ``[T, B]``, for the scan to slice.

    16.1's operand rule, enforced here rather than declared on the
    registration: the operand run of a rollforward call is the compilation's
    and not the call's argument list, so what an operand may be is a fact
    about the body and is checked against the columns the compilation's
    versioned reads bind.

    Raises:
        DomainRefused: If the run holds no column of that name, if a gate is
            not a column of truth values, or if a per-period operand is not
            exactly this machine's own number of periods for every policy.

    """
    value = bound.get(name)
    if value is None:
        raise DomainRefused(
            what=(
                f"this compilation reads {name!r} and the run holds no value "
                "standing under that name"
            ),
            move=(
                "export the artifact again from the run that compiled the "
                "rollforward, so every column its machine reads is a node the "
                "run computes"
            ),
            clause=_SUBSET,
        )
    _require_carrier(value, name, "bool" if gate else "f64")
    if value.shape == "scalar":
        return jnp.broadcast_to(value.array[None, :], (periods, ctx.rows))
    horizon = value.horizon
    lengths = np.asarray(horizon.lengths) if horizon is not None else np.zeros(0)
    if lengths.size and (
        int(lengths.min()) != periods or int(lengths.max()) != periods
    ):
        raise DomainRefused(
            what=(
                f"this compilation reads {name!r} over "
                f"{int(lengths.min())} to {int(lengths.max())} periods and its "
                f"schedule states {periods}"
            ),
            move=(
                "bring the column onto the machine's own schedule: this subset "
                "neither pads a shorter operand nor truncates a longer one"
            ),
            clause=_SUBSET,
        )
    return value.array[:, :periods].T


def _opening(
    bound: Mapping[str, Value],
    name: str,
    state: str,
    fingerprint: str,
) -> jax.Array:
    """Return one state's opening balance, checked finite where it stands.

    Raises:
        DomainRefused: If the column is missing or is one value per period.
            16.1 opens a state at a scalar column, and a per-period opening
            would be a different machine at every period.

    """
    value = bound.get(name)
    if value is None or value.shape != "scalar":
        raise DomainRefused(
            what=(
                f"the state {state!r} opens at {name!r}, which this run holds "
                + ("nothing for" if value is None else "one value per period of")
            ),
            move=(
                "open the state at the per-policy column the model means: a "
                "machine has one opening balance and not one per period"
            ),
            clause=_SUBSET,
        )
    _require_carrier(value, name, "f64")
    flag(
        "rollforward.finite",
        ~jnp.isfinite(value.array),
        where=f"{fingerprint}, the opening value of {state}",
    )
    return value.array


def _steps(
    ctx: LoweringContext,
    body: Mapping[str, Any],
    bound: Mapping[str, Value],
    periods: int,
) -> tuple[tuple[_Step, ...], list[jax.Array]]:
    """Return the chain with every operand resolved, and the arrays it slices.

    The columns are laid out once, before the scan, because a column read by
    two steps is one array: what the scan slices per period is a tuple of
    rows, and building one per mention would put the same numbers in the
    program twice.
    """
    names = [str(one["name"]) for one in body["states"]]
    columns: list[jax.Array] = []
    laid: dict[tuple[str, bool], int] = {}

    def column(name: str, *, gate: bool = False) -> _Source:
        key = (name, gate)
        if key not in laid:
            laid[key] = len(columns)
            columns.append(_bound_column(ctx, bound, name, periods, gate=gate))
        return _Source("column", at=laid[key])

    def source(operand: Mapping[str, Any], *, gate: bool = False) -> _Source:
        if operand.get("op") == "col":
            return column(str(operand["name"]), gate=gate)
        state, _, point = str(operand["name"]).partition("@")
        return _Source("state", state=names.index(state), point=point)

    steps: list[_Step] = []
    for ordinal, increment in enumerate(body["increments"], start=1):
        operation = str(increment["operation"])
        target = str(increment["target"])
        operands = list(increment["operands"])
        built = _Step(
            ordinal=ordinal,
            operation=operation,
            target=names.index(target.partition("@")[0]),
            named=target,
            amount=(source(operands[0]) if operation in _TAKES_AN_AMOUNT else None),
            lift=source(operands[0]) if operation == "Ratchet" else None,
            gate=source(operands[1], gate=True) if operation == "Ratchet" else None,
            bound=(
                float(increment["settings"][_BOUND]) if operation == "Floor" else 0.0
            ),
        )
        steps.append(built)
    return tuple(steps), columns


# The four whose first operand is the amount or the rate they move by. A floor
# takes its bound from its configuration and a ratchet from a state it lifts
# to, so neither reads one.
_TAKES_AN_AMOUNT: Final[frozenset[str]] = frozenset(
    {"Add", "Subtract", "Charge", "Grow"}
)


def _read(
    source: _Source | None,
    sliced: Sequence[jax.Array],
    opening: Sequence[jax.Array],
    running: Sequence[jax.Array],
) -> jax.Array:
    """Return what one operand stands for at one period, inside the scan."""
    if source is None:  # pragma: no cover -- a defect in _steps, not a refusal
        message = "a step of this chain reached the scan with no operand"
        raise AssertionError(message)
    if source.kind == "column":
        return sliced[source.at or 0]
    held = opening if source.point == _BOP else running
    return held[source.state or 0]


def _one_period(
    steps: Sequence[_Step],
) -> Any:  # noqa: ANN401 -- a scan body's type is the carry and the slice, which vary per machine
    """Return the body 16.1 states, closed over one compilation's own chain."""

    def period(
        carry: tuple[jax.Array, ...], sliced: tuple[jax.Array, ...]
    ) -> tuple[tuple[jax.Array, ...], tuple[Any, ...]]:
        # Every state's end of period opens at its beginning of period, and
        # the beginning stays readable while the chain runs: a ``@bop`` read
        # is the value fixed at the start of the period whatever the earlier
        # steps have done to the balance.
        opening = carry
        running = list(carry)
        caught: list[jax.Array] = []
        for step in steps:
            at = step.target
            if step.operation == "Add":
                running[at] = running[at] + _read(step.amount, sliced, opening, running)
            elif step.operation == "Subtract":
                running[at] = running[at] - _read(step.amount, sliced, opening, running)
            elif step.operation == "Charge":
                # Each product rounded before the next step adds to it: a
                # growth followed by a premium would otherwise fuse.
                running[at] = multiplied(
                    running[at], 1.0 - _read(step.amount, sliced, opening, running)
                )
            elif step.operation == "Grow":
                running[at] = multiplied(
                    running[at], 1.0 + _read(step.amount, sliced, opening, running)
                )
            elif step.operation == "Floor":
                running[at] = jnp.maximum(running[at], step.bound)
            else:
                lift = _read(step.lift, sliced, opening, running)
                gate = _read(step.gate, sliced, opening, running)
                running[at] = jnp.where(
                    gate, jnp.maximum(running[at], lift), running[at]
                )
            caught.append(~jnp.isfinite(running[at]))
        return tuple(running), (tuple(running), tuple(caught))

    return period


def inspect_machine(fingerprint: str, ctx: LoweringContext) -> None:
    """Hold one compilation to what the file alone can say about it, reading nothing.

    The two checks :func:`state_map` makes before it runs anything and that
    need no book: the file carries a body under this identity and the body is
    inside 16.1, and the body's schedule is one of the two forms the
    subsection states and supplies a period count. Asked at inspection, so
    ``gspio validate --engine jax`` reports the refusal ``run-artifact`` would
    meet, under the same sentence and clause, before any book is opened.

    Raises:
        DomainRefused: If the machine or its schedule is outside 16.1.

    """
    _periods(ctx, _the_body(ctx, fingerprint))


def state_map(fingerprint: str, ctx: LoweringContext) -> dict[str, Value]:
    """Run one compilation once, and return its internal BOP and EOP balances.

    Once, and memoised for the batch: 16.1 says the compilation is evaluated
    once as a state map, and a model extracting a fund and a benefit base from
    one machine is one kernel run rather than two. The memo is the batch's --
    a balance is an array of this batch's policies -- and it is the reason the
    ``shared`` attribute changes nothing about the numbers.

    Raises:
        DomainRefused: If the machine is outside 16.1, if its schedule does
            not supply the period count, or if an operand it reads is not
            bound to a column of the shape and type the subsection states.

    """
    held = ctx.machines.get(fingerprint)
    if held is not None:
        return held
    body = _the_body(ctx, fingerprint)
    periods = _periods(ctx, body)
    bound = ctx.bound_columns(fingerprint)
    names = [str(one["name"]) for one in body["states"]]
    opening = tuple(
        _opening(bound, str(one["init"]["name"]), str(one["name"]), fingerprint)
        for one in body["states"]
    )
    steps, columns = _steps(ctx, body, bound, periods)
    _last, (balances, caught) = lax.scan(
        _one_period(steps), opening, tuple(columns), length=periods
    )
    for step, mask in zip(steps, caught, strict=True):
        flag(
            "rollforward.finite",
            mask.T,
            where=(
                f"{fingerprint}, step {step.ordinal} of {len(steps)} "
                f"({step.operation} on {step.named})"
            ),
        )
    horizon = _axis(periods, ctx.rows)
    answered = {}
    for name, initial, balance in zip(names, opening, balances, strict=True):
        # BOP is the initializer followed by prior closes; no second scan.
        beginnings = jnp.concatenate((initial[None, :], balance), axis=0)[:periods]
        for point, values in ((_BOP, beginnings), (_EOP, balance)):
            answered[f"{name}@{point}"] = Value(
                _to_the_bucket(values.T, horizon.bucket),
                "f64",
                "list",
                "list[f64]",
                horizon,
            )
    ctx.machines[fingerprint] = answered
    return answered


def _axis(periods: int, rows: int) -> Horizon:
    """Return the axis a machine's balances stand on.

    Every policy runs the same number of steps: the count is the schedule's
    and the schedule is the document's, so this is a width known before the
    run started rather than an axis minted inside the trace from data. It is
    built here rather than sized on the host because there is nothing to
    measure -- the number is written in the file.
    """
    return Horizon.over(
        jnp.full((rows,), periods, dtype=jnp.int64),
        bucket=bucket_of(periods),
        host=np.full((rows,), periods, dtype=np.int64),
    )


def _to_the_bucket(balances: jax.Array, bucket: int) -> jax.Array:
    """Return one machine's balances padded out to the width they stand in."""
    if balances.shape[1] >= bucket:
        return balances
    return jnp.pad(balances, ((0, 0), (0, bucket - balances.shape[1])))


def _balance(
    ctx: LoweringContext, fingerprint: str, reference: str, *, internal: bool = False
) -> Value:
    """Return an internal balance or an admitted EOP extraction.

    Raises:
        DomainRefused: If an extraction asks for BOP, or the machine does
            not declare the requested state and point.

    """
    state, _, point = reference.partition("@")
    if point != _EOP and not internal:
        raise DomainRefused(
            what=(
                f"this line reads {state!r} at the {point or 'unstated'} of the "
                "period, and this subsection states a portable value for the "
                "end of period alone"
            ),
            move=(
                "read the balance at the end of the period, or run this model "
                "on Polars: a beginning-of-period balance is a real quantity "
                "and no portable contract states it yet"
            ),
            clause=_SUBSET,
        )
    answered = state_map(fingerprint, ctx)
    balance = answered.get(reference)
    if balance is None:
        raise DomainRefused(
            what=(
                f"this line reads the balance {state!r} and the compilation "
                f"{fingerprint} declares {', '.join(sorted(answered)) or 'none'}"
            ),
            move=(
                "read a state the machine declares, or export the artifact "
                "again from the run that compiled it"
            ),
            clause=_SUBSET,
        )
    return balance


@register(
    Capability(
        identifier=MACHINE,
        arity=(0,),
        attrs_required=("fingerprint",),
        checks=("rollforward.finite",),
        horizon="recurrence",
        clause=_SUBSET,
        note=(
            "the bounded portable machine this subsection states, run as one "
            "scan down the periods with the declared states as its carry; "
            "tracking, a lapse condition, a contract boundary, a non-portable "
            "binding, a rounded charge or an ungated ratchet are refused by "
            "name"
        ),
    )
)
def _machine(call: Call, ctx: LoweringContext) -> Value:
    """Return the balance the running state this node stands for carries.

    A compilation's node is the machine and not a column (§16), so the call it
    carries is answered *inside a running state's own node*: the plan reaches
    this through the state, and what comes back is that state's balance. The
    machine itself is run once for the batch whichever of its states asks
    first.
    """
    return _balance(
        ctx,
        str(dict(call.attrs)["fingerprint"]),
        ctx.node.node_id.partition(":")[2],
        internal=True,
    )


@register(
    Capability(
        identifier="rollforward.state",
        attrs={"point": (_EOP,)},
        attrs_required=("fingerprint", "state"),
        checks=("rollforward.finite",),
        horizon="recurrence",
        answers="list",
        answers_carrier="f64",
        clause=_SUBSET,
        note=(
            "one declared balance of the bounded portable machine, at the end "
            "of the period: the operand run of this call is the compilation's "
            "own and its operands are checked against the machine rather than "
            "against the argument list"
        ),
    )
)
def _state(call: Call, ctx: LoweringContext) -> Value:
    """Return one declared state's per-period balance, at the end of the period."""
    attrs = dict(call.attrs)
    return _balance(
        ctx,
        str(attrs["fingerprint"]),
        f"{attrs['state']}@{attrs.get('point', _EOP)}",
    )
