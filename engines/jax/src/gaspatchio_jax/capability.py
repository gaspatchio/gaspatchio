# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a registration says about the invocations it can answer.

One predicate, read twice. The runtime reads it to decide what to do with a
node, and the coverage manifest reads it to say what this engine claims about
an identifier -- so the table cannot say *lowered* of a form the runtime
refuses, which is the failure a hand-kept coverage table always eventually
has. A review of this plan asked for exactly this, and it is why a
capability is a description rather than a Boolean.

**A status is about an invocation, never about an identifier.** ``to_text``
is lowered where its operand is a column that arrived and refused where its
operand is a calculation; ``round`` is lowered under either tie rule and
refused with a negative ``decimals``, which section 11.1.8 leaves undefined.
An engine that answered "lowered: to_text" would be telling a reader they can
port a model they cannot port.

**Three statuses and no fourth.** In the trace; on the host, from the node's
own attributes and operands that arrived rather than were computed; or
refused by name. The condition travels with the second and with the third,
because the bare word says nothing a reader can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from gaspatchio.engines.protocol import NodeStatus

from .typed import cell_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .typed import Carrier

__all__ = [
    "BOOLEAN",
    "CROSSING_CLASSES",
    "DATE",
    "EITHER_SHAPE",
    "NUMERIC",
    "PER_PERIOD",
    "PER_POLICY",
    "TEXT",
    "Capability",
    "HorizonClass",
    "NodeRecord",
    "Operands",
]

# How an operation stands to the projection's period axis. Seven classes, and
# the class decides what a lowering owes the padding beyond a policy's own
# horizon: nothing, for an operation whose every position is a function of
# that position alone, and the operation's own neutral element for the four
# that can read a later or an aggregate position.
HorizonClass = Literal[
    "local",
    "forward-fold",
    "recurrence",
    "reverse-fold",
    "reduction",
    "shift-or-select",
    "generator",
]

# The four that cross: an identifier in one of these has a padding witness in
# the suite, because its answer at a position it *does* have can be changed by
# a cell it does not.
CROSSING_CLASSES: frozenset[str] = frozenset(
    {"reverse-fold", "reduction", "shift-or-select", "generator"}
)

# The operand shapes section 11.1.18 names, as a declared domain beside the
# carrier. A carrier says what a cell is held in; a shape says whether there
# is one cell per policy or one per period, and the two are independent
# questions -- ``sum`` takes a number per period and answers one per policy,
# ``excel.pv`` takes numbers per policy and no list at all.
PER_POLICY: frozenset[str] = frozenset({"scalar"})
PER_PERIOD: frozenset[str] = frozenset({"list"})
EITHER_SHAPE: frozenset[str] = frozenset({"scalar", "list"})

# The operand condition, in the two forms a registration states it in: every
# operand arrived with the book or is a literal, or any operand at all. Text is
# what binds it: this engine makes text on the host, from values it was handed,
# and refuses by name a text operation over a calculation.
Operands = Literal["inputs-or-literals", "any"]

# The three semantic families section 11.1.26 keeps apart: no ordering between
# them is inferred, and a comparison whose two operands fall in different ones
# is not a comparison this vocabulary states. Named here because four
# registrations state a domain in terms of them.
NUMERIC: frozenset[Carrier] = frozenset({"i64", "f64", "bool"})
# Narrower than NUMERIC: a truth value and nothing else. 11.1.27's operands
# also admit a stored f64 indicator column, which its own lowering checks.
BOOLEAN: frozenset[Carrier] = frozenset({"bool"})
DATE: frozenset[Carrier] = frozenset({"date"})
TEXT: frozenset[Carrier] = frozenset({"code"})

# Every carrier, for an operation that answers over any of them.
ANY_CARRIER: frozenset[Carrier] = NUMERIC | DATE | TEXT

# The family each carrier belongs to, for the matched-operand rule.
_FAMILY: dict[Carrier, str] = {
    **dict.fromkeys(NUMERIC, "a number"),
    "date": "a calendar date",
    "code": "text",
}

# What a reader calls each of the two shapes.
_SPELLED_SHAPE: dict[str, str] = {
    "scalar": "one value per policy",
    "list": "one value per period",
}

# What a reader calls each carrier. A refusal names what the model wrote, not
# what this engine holds it in: "code" is an implementation of text equality
# and nobody wrote one.
_SPELLED: dict[Carrier, str] = {
    "i64": "a whole number",
    "f64": "a floating-point value",
    "bool": "a Boolean",
    "date": "a calendar date",
    "code": "text",
}

# The same table under a wider key, for the one place a carrier arrives as
# whatever a registration wrote rather than as one of the five.
_SPELLED_ANY: dict[str, str] = dict(_SPELLED.items())

# The condition an off-trace lowering carries, written once because the
# manifest, the node status and the spec's own words all quote it.
OFF_TRACE_CONDITION = "operands are inputs or literals"


@dataclass(frozen=True, slots=True)
class NodeRecord:
    """One graph node as the artifact records it, and what it stands among.

    Attributes:
        node_id: The node's own identifier.
        column: The column it is an account of, or None for a node that is
            not a column of the model.
        version: Which account of that column, or None for an arrival.
        kind: ``input``, ``computed``, ``state``, ``rollforward`` or ``hole``.
        dtype: The type the producer resolved, in section 10's vocabulary.
        shape: ``scalar`` or ``list``.
        reads: The node identifiers this node's tree reads.
        expr: The operation tree, as the executable profile writes it.
        in_final_schema: Whether this account is the one the frame ended on.
        arriving_columns: Every column the document's input nodes name. On the
            record because the operand condition is asked of an operand and answered
            about the document, and a capability is handed one record.
        read_dtypes: Column name to the type the node standing under it
            declares, for every node this one reads. This is what lets a
            status be a statement about an *invocation* rather than about an
            identifier: a comparison's operand carriers are readable from the
            records alone, so ``validate_tree`` refuses a date against a
            number without a book and without lowering anything.
        read_kinds: Column name to the *kind* of the node standing under it,
            for every node this one reads. The operand condition is about where an
            operand's values came from, and a name is not an answer to that:
            an overwritten column has an input node and a computed one under
            one name, and only the record's own reads say which the formula
            was written against.

    """

    node_id: str
    column: str | None
    version: int | None
    kind: str
    dtype: str
    shape: str
    reads: tuple[str, ...]
    expr: Mapping[str, object] | None
    in_final_schema: bool
    arriving_columns: frozenset[str] = frozenset()
    read_dtypes: Mapping[str, str] = field(default_factory=dict)
    read_kinds: Mapping[str, str] = field(default_factory=dict)


def _per_operand(
    admitted: tuple[frozenset[str], ...], spelled: Mapping[str, str]
) -> str:
    """Return what a per-operand domain reads as, in one phrase.

    One phrase where every operand admits the same set, and the sets in order
    where they do not -- which is the difference between "operands carried as
    a whole number" and "a whole number then a floating-point value".
    """
    written = [", ".join(sorted(spelled[one] for one in each)) for each in admitted]
    return written[0] if len(set(written)) == 1 else " then ".join(written)


def _a_wider_bound(carried: dict[Carrier, int]) -> bool:
    """Return whether a later operand is held in a wider carrier than the first.

    ``carried`` maps each carrier to the first position it was read at. The
    first operand is the value; a whole-number bound beside a decimal value
    is read as its double, and only a decimal bound beside a whole-number
    value is a second answer.
    """
    first = next((carrier for carrier, at in carried.items() if at == 0), None)
    return first == "i64" and "f64" in carried


@dataclass(frozen=True, slots=True)
class Capability:
    """What one registration answers for, and on what condition.

    Attributes:
        identifier: The vocabulary identifier this is a registration for.
        operands: ``inputs-or-literals`` where the operand condition binds,
            ``any`` where the operands may be calculations.
        attrs: Attribute name to the values admitted, or None where every
            value the specification admits is admitted here.
        attr_bounds: Attribute name to the closed interval of whole numbers
            admitted, each end None where that end is open.
            ``round_sig_figs``'s ``digits`` is ``(1, None)``: section 11.1.12
            keeps at least one figure and the lowering refuses fewer, so the
            capability has to say so or the table claims a form the runtime
            will not run.
            **Both ends open states the type and nothing else** -- a whole
            number, wherever it lands -- which is what ``mortality.at``'s
            ``select_period`` is: 11.1.10 calls it an integer number of
            durations and states no interval, and the clamp holds a duration
            at it whatever it is.
        attrs_required: Attributes that must be present and not null. A
            ``str.to_date`` with a null ``format`` is a parse no second reader
            can reproduce, and the clause says as much.
        attrs_numeric: Attributes whose value is a number, where the clause
            states no interval for it. ``projection.with_period``'s
            replacement is one: 11.1.32 calls it a finite decimal and states
            no bound, and a declaration that said only "present" would claim
            a form whose replacement was written as text -- which the
            lowering refuses, because an attribute is a flat typed value
            (12.1) and text names no replacement at all.
        attrs_required_when: Attributes that must be present *under a
            setting of another attribute*, as ``{name: (deciding, values)}``.
            ``mortality.at``'s ``select_period`` is one: 11.1.10 requires it
            of a ``select_ultimate`` structure and says an aggregate basis
            has none at all rather than a null one. Without this the
            declaration says "any structure" while the lowering refuses one
            of them, which is a table claiming a form its engine will not
            run.
        arity: The operand counts admitted, or None where any count is.
        literal_operands: Operand positions that must be a sequence literal
            written into the formula, as 11.1.5 and 11.1.6 require.
        carriers: One admitted carrier set per operand position, the last
            repeating for any operand beyond it, or None where the operation
            answers over every carrier. Evaluated against the *declared* types
            of the nodes an operand reads, so a form outside the domain is
            refused before anything is lowered.
        alone_per_policy: A carrier at most one operand may be held in where
            it is one value per policy -- 11.1.25's "a per-policy Boolean on
            both sides of one operation is not admitted". Evaluated against
            the declared types and shapes of the operands the record states,
            as ``carriers`` is; the lowering refuses the same form where an
            operand is a nested expression.
        matched_carriers: Whether every operand must fall in one semantic
            family -- 11.1.26's rule that no ordering between a number, a date
            and text is inferred.
        shapes: One admitted shape set per operand position, the last
            repeating for any operand beyond it, or None where the operation
            answers over either. Evaluated against the *declared* shape of
            the nodes an operand reads, the same way ``carriers`` is, so a
            per-period operand handed to an operation that states one value
            per policy is refused before anything is lowered.
        answers: The shape of the answer, where the operation changes it --
            ``sum`` takes a list and answers a scalar (11.1.14) and the four
            folds say so per entry. None where the answer keeps the operands'
            own shape.
        answers_carrier: What the answer is held in, where that is fixed by
            the operation rather than taken from its operands -- a comparison
            answers a truth value, ``mean`` answers a decimal whatever it
            folded. None where the answer is in the operand's own carrier,
            which is what ``sum``, ``min`` and ``max`` are: a run of whole
            numbers has a whole total, and an engine that widened it would be
            answering a type the record does not declare.
        matched_exactly: Whether no later operand may be in a wider
            carrier than the first. ``clip`` is the case: a whole number held
            between decimal bounds has two answers -- the bound itself, and
            the bound cast into the value's own type, which is what the
            producer gives -- and 11.1.3 states neither, so the engine
            refuses rather than picking one. A decimal value held between
            whole-number bounds has one answer, the value or a bound as a
            double, and 11.1.3 states it: "a decimal value answers decimals"
            whatever its bound is.
        matched_operands: Which positions ``matched_carriers`` is about, or
            None for every non-literal one. ``when_then``'s rule is about its
            two *branches*: a condition is a truth value and stands in no
            family with either of them.
        matched_says: The verb a family mismatch is reported with, and the
            reason after it. "compares … infers no ordering between them" is
            11.1.26's own sentence and belongs to a comparison; an operation
            that *selects* between two branches infers no ordering either way,
            and what it has not got is a common type.
        attrs_folded: Attribute names matched without regard to case, as
            11.1.34's basis aliases are. The manifest states the admitted
            values and that they are matched this way.
        checks: The names in :data:`gaspatchio_jax.checks.CHECKS` this
            identifier owes.
        horizon: How it stands to the period axis.
        sizes_its_own_axis: Whether the width of the array it answers is read
            from its operands rather than taken from one of them. Such an
            operation is settled before the program that reads its answer is
            built, because a width is not something a compiled program can be
            handed -- see :mod:`gaspatchio_jax.plan`.
        off_trace: Whether it is answered on the host rather than in the trace.
        note: One sentence a manifest carries beside the status, where the
            registration has something to say that the condition does not.
        refused_alike: The move a refusal names where the reference producer
            refuses the same form too, keyed by what refused it --
            ``shape@<position>`` for an operand outside ``shapes``,
            ``carrier@<position>`` for one outside ``carriers`` and
            ``attr:<name>`` for an attribute outside ``attrs``. A refusal
            keyed here names that move; any other names running the model on
            Polars, which answers what this engine has no lowering for. A key
            is written only where the producer was seen refusing that form, so
            a reader is never sent to an engine that refuses it as well.

    """

    identifier: str
    operands: Operands = "any"
    attrs: dict[str, tuple[str, ...]] | None = None
    attr_bounds: dict[str, tuple[int | None, int | None]] | None = None
    attrs_required: tuple[str, ...] = ()
    attrs_numeric: tuple[str, ...] = ()
    attrs_required_when: dict[str, tuple[str, tuple[str, ...]]] | None = None
    arity: tuple[int, ...] | None = None
    literal_operands: tuple[int, ...] = ()
    carriers: tuple[frozenset[Carrier], ...] | None = None
    alone_per_policy: Carrier | None = None
    matched_carriers: bool = False
    matched_exactly: bool = False
    shapes: tuple[frozenset[str], ...] | None = None
    answers: str | None = None
    answers_carrier: str | None = None
    matched_operands: tuple[int, ...] | None = None
    matched_says: str = "compares"
    matched_because: str = "infers no ordering between them"
    attrs_folded: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    horizon: HorizonClass = "local"
    sizes_its_own_axis: bool = False
    off_trace: bool = False
    note: str | None = None
    refused_alike: dict[str, str] | None = None
    # The specification clause, filled in by the registry from the vocabulary
    # where a registration does not state one, so no registration has to
    # re-type a number the vocabulary already holds.
    clause: str = ""

    def status_of(self, node: Mapping[str, object], record: NodeRecord) -> NodeStatus:
        """Return what this engine does with one invocation, and why.

        Args:
            node: The call as the tree writes it -- its name, its arguments
                and its attributes.
            record: The graph node the call stands in.

        Returns:
            The status, with the condition it holds under and the clause it
            rests on.

        """
        refused, unread = self._refusal(node, record)
        if refused is not None:
            return NodeStatus(
                record.node_id, "refused", refused[1], self.clause or None
            )
        if self.operands == "inputs-or-literals":
            computed = _computed_operands(node, record)
            if computed:
                named = ", ".join(sorted(computed))
                return NodeStatus(
                    record.node_id,
                    "refused",
                    (
                        f"{self.identifier} reads {named}, which a calculation "
                        "produced; this engine answers it on the host and only "
                        "from columns that arrived or values written into the "
                        "formula"
                    ),
                    self.clause or None,
                )
        # An operand whose type the records do not state -- a nested
        # expression -- leaves the domain unchecked, and a status that read as
        # an unconditional "lowered" there would be claiming more than was
        # looked at. The condition says what the claim rests on.
        stated = self.stated_condition() if unread else None
        if self.off_trace:
            return NodeStatus(
                record.node_id,
                "lowered-off-trace",
                "; ".join(filter(None, (OFF_TRACE_CONDITION, stated))),
                self.clause or None,
            )
        return NodeStatus(record.node_id, "lowered", stated, self.clause or None)

    def move_of(self, node: Mapping[str, object], record: NodeRecord) -> str | None:
        """Return the move a refusal of one invocation names, where it is not Polars.

        None where the invocation is not refused by this declaration, or is
        refused for a form the reference producer answers -- which is where
        running the model on Polars is the move.
        """
        refused, _unread = self._refusal(node, record)
        if refused is None or self.refused_alike is None:
            return None
        return self.refused_alike.get(refused[0])

    def _refusal(
        self, node: Mapping[str, object], record: NodeRecord
    ) -> tuple[tuple[str, str] | None, bool]:
        """Return what refuses one invocation, keyed, and whether an operand was unread.

        The key names the declaration that refused -- ``arity``,
        ``attr:<name>``, ``carrier@<position>``, ``shape@<position>`` and the
        rest -- which is what :attr:`refused_alike` is read by.
        """
        arity = self._arity_outside(node)
        if arity is not None:
            return ("arity", arity), False
        refused_attribute = self._attribute_outside(node)
        if refused_attribute is not None:
            name, written = refused_attribute
            return (f"attr:{name}", written), False
        for key, refuse in (
            ("attr-absent", self._attribute_absent),
            ("attr-absent-under", self._attribute_absent_under),
            ("attr-bounds", self._attribute_out_of_bounds),
            ("attr-number", self._attribute_not_a_number),
            ("literal", self._operand_not_written_out),
        ):
            sentence = refuse(node)
            if sentence is not None:
                return (key, sentence), False
        outside, unread = self._carriers_outside(node, record)
        if outside is None:
            together = self._together_per_policy(node, record)
            outside = None if together is None else ("together", together)
        if outside is None:
            outside, shapes_unread = self._shapes_outside(node, record)
            unread = unread or shapes_unread
        return outside, unread

    def stated_condition(self) -> str | None:
        """Return everything this registration restricts, in one sentence.

        What the coverage manifest puts in a row's ``condition``, and what a
        status carries where an operand's type could not be read off the
        records. None where the registration restricts nothing, which is the
        only case a bare *lowered* is honest for.

        Three groups, in the order a reader meets them: what the operands
        are, what the answer is, and what the attributes say.
        """
        parts = [
            *self._operand_clauses(),
            *self._answer_clauses(),
            *self._attribute_clauses(),
        ]
        return "; ".join(parts) if parts else None

    def _operand_clauses(self) -> list[str]:
        """Return what this registration restricts about its own operands."""
        parts: list[str] = []
        if self.arity is not None:
            counts = " or ".join(str(count) for count in sorted(self.arity))
            parts.append(f"{counts} operand" + ("" if self.arity == (1,) else "s"))
        if self.carriers is not None:
            # The two spelling tables are keyed by their own ``Literal``
            # types; the helper reads both and neither key set is narrower
            # than ``str`` at the point it is read.
            parts.append(
                "operands carried as " + _per_operand(self.carriers, _SPELLED)  # type: ignore[arg-type]
            )
        if self.shapes is not None:
            parts.append(
                "operands carrying " + _per_operand(self.shapes, _SPELLED_SHAPE)
            )
        if self.matched_exactly:
            parts.append("no bound in a wider carrier than the value")
        if self.matched_carriers:
            named = (
                "both operands"
                if self.matched_operands is None
                else "operands " + ", ".join(str(one) for one in self.matched_operands)
            )
            parts.append(f"{named} in one of number, date, text")
        if self.literal_operands:
            written = ", ".join(str(position) for position in self.literal_operands)
            parts.append(f"operand {written} written out as a sequence literal")
        return parts

    def _answer_clauses(self) -> list[str]:
        """Return what this registration restricts about what it answers.

        Including *when*: an operation that reads the width of its own answer
        is settled before the program that reads it exists, and that is part
        of what this engine does with it rather than an implementation note.
        """
        parts: list[str] = []
        if self.answers is not None:
            parts.append(f"answering {_SPELLED_SHAPE[self.answers]}")
        if self.answers_carrier is not None:
            named = _SPELLED_ANY.get(self.answers_carrier, self.answers_carrier)
            parts.append(f"answering {named}")
        if self.attrs_folded:
            written = ", ".join(self.attrs_folded)
            parts.append(f"{written} matched without case")
        if self.sizes_its_own_axis:
            parts.append(
                "the width of its answer is read from its operands, on the "
                "host, before the program that reads it is built"
            )
        return parts

    def _attribute_clauses(self) -> list[str]:
        """Return what this registration restricts about its own attributes."""
        parts = [
            f"{name}={' or '.join(admitted)}"
            for name, admitted in (self.attrs or {}).items()
        ]
        for name, (low, high) in (self.attr_bounds or {}).items():
            if low is not None and high is not None:
                parts.append(f"{low} <= {name} <= {high}")
            elif low is not None:
                parts.append(f"{name} >= {low}")
            elif high is not None:
                parts.append(f"{name} <= {high}")
            else:
                # Both ends open is still a claim, and the claim is the type:
                # this attribute is a whole number, wherever it lands.
                parts.append(f"{name} a whole number")
        parts.extend(f"{name} stated" for name in self.attrs_required)
        parts.extend(f"{name} a number" for name in self.attrs_numeric)
        parts.extend(
            f"{name} stated where {deciding}={' or '.join(values)}"
            for name, (deciding, values) in (self.attrs_required_when or {}).items()
        )
        return parts

    def restricts(self) -> bool:
        """Return whether this registration narrows what it answers for at all."""
        return self.stated_condition() is not None

    def _arity_outside(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for an operand count this lowering does not take."""
        if self.arity is None:
            return None
        written = len(_arguments(node))
        if written in self.arity:
            return None
        counts = " or ".join(str(count) for count in sorted(self.arity))
        return (
            f"{self.identifier} is written with {written} operands, and this "
            f"engine answers it for {counts}"
        )

    def _attribute_outside(self, node: Mapping[str, object]) -> tuple[str, str] | None:
        """Return the attribute whose value is not admitted, and the sentence."""
        for name, admitted in (self.attrs or {}).items():
            value = _attribute(node, name)
            folded = name in self.attrs_folded
            if value is None or _admits(str(value), admitted, folded=folded):
                continue
            allowed = ", ".join(admitted)
            return name, (
                f"{self.identifier} is written with {name}={value!r}, and this "
                f"engine answers it for {allowed}"
            )
        return None

    def _attribute_absent(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for an attribute the operation cannot do without."""
        for name in self.attrs_required:
            if _attribute(node, name) is None:
                return (
                    f"{self.identifier} carries no {name}, and without one this "
                    "engine has no answer a second reader could reproduce"
                )
        return None

    def _attribute_absent_under(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for an attribute this setting of another requires."""
        for name, (deciding, values) in (self.attrs_required_when or {}).items():
            setting = _attribute(node, deciding)
            if setting is None or str(setting) not in values:
                continue
            if _attribute(node, name) is None:
                return (
                    f"{self.identifier} is written with {deciding}={setting!r} "
                    f"and carries no {name}, which that setting is defined by"
                )
        return None

    def _attribute_out_of_bounds(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for a whole-number attribute outside its interval.

        An attribute this registration bounds is a **whole number** first and
        inside the interval second, and both halves of that are refused here.
        Passing over a value that is not one left the narrower case open: a
        ``select_period`` written as text or as a decimal satisfied "is it
        present?", so the table read *lowered* while the lowering refused it
        for not being a number it could hold a duration at.

        Absence is not this rule's business and stays a pass --
        ``attrs_required`` and ``attrs_required_when`` are where an
        attribute's presence is stated.
        """
        for name, (low, high) in (self.attr_bounds or {}).items():
            value = _attribute(node, name)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                return (
                    f"{self.identifier} is written with {name}={value!r}, and "
                    "this engine answers it for a whole number"
                )
            if (low is not None and value < low) or (high is not None and value > high):
                floor = low if low is not None else "any"
                cap = high if high is not None else "any"
                stated = f"{floor}..{cap}"
                return (
                    f"{self.identifier} is written with {name}={value}, and this "
                    f"engine answers it for {stated}"
                )
        return None

    def _attribute_not_a_number(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for an attribute written as anything but a number.

        Absence is not this rule's business and stays a pass, the same way it
        does for an interval: ``attrs_required`` is where presence is stated.
        """
        for name in self.attrs_numeric:
            value = _attribute(node, name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return (
                    f"{self.identifier} is written with {name}={value!r}, and "
                    "this engine answers it for a number"
                )
        return None

    def _operand_not_written_out(self, node: Mapping[str, object]) -> str | None:
        """Return the sentence for a set or a band an expression produced."""
        written = _arguments(node)
        for position in self.literal_operands:
            if position >= len(written):
                continue
            operand = written[position]
            if operand.get("op") == "lit" and isinstance(operand.get("values"), list):
                continue
            return (
                f"{self.identifier} takes its operand {position} written into "
                "the formula, and here it is the answer of an expression"
            )
        return None

    def _shapes_outside(
        self, node: Mapping[str, object], record: NodeRecord
    ) -> tuple[tuple[str, str] | None, bool]:
        """Return the sentence for an operand of the wrong shape, and what went unread.

        The same two-part answer the carrier domain gives: an operand whose
        shape the records do not state leaves the domain unchecked and the
        caller says so rather than claiming it passed.
        """
        if self.shapes is None:
            return None, False
        unread = False
        for position, operand in enumerate(_arguments(node)):
            if position in self.literal_operands:
                continue
            shape = _shape_of(operand, record)
            if shape is None:
                unread = True
                continue
            admitted = self.shapes[min(position, len(self.shapes) - 1)]
            if shape not in admitted:
                named = ", ".join(sorted(_SPELLED_SHAPE[one] for one in admitted))
                return (
                    f"shape@{position}",
                    (
                        f"{self.identifier} is written over "
                        f"{_SPELLED_SHAPE[shape]} at operand {position}, and this "
                        f"engine answers it for {named}"
                    ),
                ), unread
        return None, unread

    def _carriers_outside(
        self, node: Mapping[str, object], record: NodeRecord
    ) -> tuple[tuple[str, str] | None, bool]:
        """Return the sentence for an operand outside the domain, and what went unread.

        The second half of the answer is what makes this honest: an operand
        whose carrier the records do not state -- a nested expression -- is
        neither admitted nor refused here, and the caller turns that into a
        condition rather than a silent pass.
        """
        if (
            self.carriers is None
            and not self.matched_carriers
            and not self.matched_exactly
        ):
            return None, False
        unread = False
        families: dict[str, int] = {}
        carried: dict[Carrier, int] = {}
        for position, operand in enumerate(_arguments(node)):
            if position in self.literal_operands:
                continue
            carrier = _carrier_of(operand, record)
            if carrier is None:
                unread = True
                continue
            if self.matched_operands is None or position in self.matched_operands:
                families.setdefault(_FAMILY[carrier], position)
            carried.setdefault(carrier, position)
            if self.carriers is None:
                continue
            admitted = self.carriers[min(position, len(self.carriers) - 1)]
            if carrier not in admitted:
                named = ", ".join(sorted(_SPELLED[one] for one in admitted))
                return (
                    f"carrier@{position}",
                    (
                        f"{self.identifier} is written over {_SPELLED[carrier]} at "
                        f"operand {position}, and this engine answers it for {named}"
                    ),
                ), unread
        if self.matched_exactly and _a_wider_bound(carried):
            named = " and ".join(sorted(_SPELLED[one] for one in carried))
            return (
                "matched-exactly",
                (
                    f"{self.identifier} is written over {named} together, a "
                    "decimal bound on a whole-number value, and the answer's own "
                    "type would not be on the record"
                ),
            ), unread
        if self.matched_carriers and len(families) > 1:
            named = " and ".join(sorted(families))
            return (
                "matched-families",
                (
                    f"{self.identifier} {self.matched_says} {named}, and this "
                    f"vocabulary {self.matched_because}"
                ),
            ), unread
        return None, unread

    def _together_per_policy(
        self, node: Mapping[str, object], record: NodeRecord
    ) -> str | None:
        """Return the sentence for two per-policy operands of the lone carrier."""
        if self.alone_per_policy is None:
            return None
        held = [
            position
            for position, operand in enumerate(_arguments(node))
            if _carrier_of(operand, record) == self.alone_per_policy
            and _shape_of(operand, record) == "scalar"
        ]
        if len(held) < 2:  # noqa: PLR2004 -- one may stand alone; two may not
            return None
        spelled = _SPELLED[self.alone_per_policy]
        return (
            f"{self.identifier} is written over {spelled} at operands "
            f"{held[0]} and {held[1]}, one value per policy each, and only one "
            "side of it may be: write one as the amount it stands for, "
            "when(flag).then(1.0).otherwise(0.0)"
        )


def _admits(written: str, admitted: tuple[str, ...], *, folded: bool) -> bool:
    """Return whether one attribute value is one this registration takes."""
    if not folded:
        return written in admitted
    return written.casefold() in {one.casefold() for one in admitted}


def _shape_of(tree: Mapping[str, object], record: NodeRecord) -> str | None:
    """Return the shape one operand stands in, or None where the record is silent.

    A column's shape is the shape the node standing under it declares, which
    the record carries; a scalar literal has neither axis until an operation
    combines it with a column (11.1.18), so it stands as one value per policy.
    A nested expression has no declared shape of its own and the answer is
    None, exactly as it is for a carrier.
    """
    kind = tree.get("op")
    if kind == "col":
        name = tree.get("name")
        declared = record.read_dtypes.get(name) if isinstance(name, str) else None
        if not isinstance(declared, str):
            return None
        return "list" if declared.startswith("list[") else "scalar"
    if kind == "lit":
        return None if isinstance(tree.get("values"), list) else "scalar"
    return None


def _is_computed(name: str, record: NodeRecord) -> bool:
    """Return whether the account this node reads under one name is a calculation.

    Through the record's own ``reads``, which carry the *version* the node
    was written against. Where the records say nothing about the name -- a
    tree naming a column its own node does not read, which a valid document
    does not carry -- the document's arriving columns are the fallback, which
    is what this test was before it knew about versions.
    """
    resolved = record.read_kinds.get(name)
    if resolved is None:
        return name not in record.arriving_columns
    return resolved != "input"


def _attribute(node: Mapping[str, object], name: str) -> object:
    """Return one attribute a call carries, or None where it carries none."""
    written = node.get("attrs")
    return written.get(name) if isinstance(written, dict) else None


# What a literal's JSON form says about the carrier it stands for. A date is
# written under its own key (12.1) and everything else under ``value``.
_LITERAL_CARRIER: dict[type, Carrier] = {
    bool: "bool",
    int: "i64",
    float: "f64",
    str: "code",
}


def _carrier_of(tree: Mapping[str, object], record: NodeRecord) -> Carrier | None:
    """Return the carrier one operand is held in, or None where the record is silent.

    A column's carrier is the type the node standing under it declares, which
    the record carries; a literal's is its own written form. A nested
    expression has no declared type of its own -- section 11.1.13 says as much,
    in the paragraph about ``is_nan(a / b)`` -- so the answer is None and the
    caller says the domain went unchecked rather than claiming it passed.
    """
    kind = tree.get("op")
    if kind == "col":
        name = tree.get("name")
        declared = record.read_dtypes.get(name) if isinstance(name, str) else None
        return cell_of(declared) if declared else None
    if kind == "lit":
        if "date" in tree:
            return "date"
        if isinstance(tree.get("values"), list):
            return None
        return _LITERAL_CARRIER.get(type(tree.get("value")))
    return None


def _computed_operands(node: Mapping[str, object], record: NodeRecord) -> set[str]:
    """Return the operand columns a calculation produced rather than supplied.

    A literal is written into the formula and an input arrived with the book;
    anything else is a calculation, and a text producer reading one refuses:
    this engine has no stage yet that makes text from a calculated value.
    """
    found: set[str] = set()
    for argument in _arguments(node):
        found |= _computed_inside(argument, record)
    return found


# Where each of the three operation node kinds keeps its operands. A call
# carries a run under ``args``; the fifteen operators written as formulas carry
# two named fields, and a conditional three. One definition, because "how many
# operands does this node have" is asked by the arity rule, by the operand
# domain and by the operand condition, and three readings of it would drift.
_NAMED_OPERANDS: tuple[str, ...] = ("left", "right", "cond", "then", "otherwise")


def _arguments(tree: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the operand trees one node names, in the order it writes them."""
    written = tree.get("args")
    found: list[Mapping[str, object]] = (
        [argument for argument in written if isinstance(argument, dict)]
        if isinstance(written, list)
        else []
    )
    found.extend(
        child for key in _NAMED_OPERANDS if isinstance(child := tree.get(key), dict)
    )
    return found


def _computed_inside(tree: Mapping[str, object], record: NodeRecord) -> set[str]:
    """Return the computed column names one operand tree reads.

    Decided by the node the operand **resolves to**, not by whether the
    document has an input node of that name somewhere. A model that writes
    over an arriving column -- ``duration = duration + 10`` -- leaves both
    accounts under one name, and a formula written after it reads the
    computed one. Answered by name, the operand condition read "operands are inputs
    or literals" of a calculation, and the host stage then published the text
    of the values the column held *before* the model wrote over it.
    """
    kind = tree.get("op")
    if kind == "lit":
        return set()
    if kind == "col":
        name = tree.get("name")
        if not isinstance(name, str):
            return set()
        return {name} if _is_computed(name, record) else set()
    found: set[str] = set()
    for argument in _arguments(tree):
        found |= _computed_inside(argument, record)
    if kind in ("call", "binop", "when_then") and not found:
        # An operand that is an operation over literals alone is still a
        # calculation this engine has not run on the host.
        found.add(str(tree.get("name") or tree.get("kind") or "an expression"))
    return found
