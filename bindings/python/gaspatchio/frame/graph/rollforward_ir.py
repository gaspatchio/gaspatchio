# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compiled state machine itself, projected into the op-tree's terms.

A compiled rollforward is one node in the artifact: its identity, the columns
and running states it reads, the states it declares, and every line that read
it. That is what a reviewer needs in order to *follow* the model, and it is
all the audit profile carries. What it does not carry is the machine -- which
operation is applied to which balance, in what order, on what rate, under
what rounding.

That is the one calculation in an actuarial model a reader most wants in front
of them. The framework escalates from a closed form to a state machine exactly
when a within-period charge depends on the running balance, so the escalation
is never incidental: a cost of insurance struck on the net amount at risk, a
credited rate held between a floor and a cap, a benefit base ratcheting to a
fund's high-water mark. It is also the one part of a model a second
implementation cannot execute from the node alone -- the node carries the
compiler's fingerprint, and a fingerprint is an identity rather than a recipe.
So the file carries the recipe too (*No vendor lock-in, by construction*).

**It travels as a facet, and that is a deliberate limit on what it claims.**
The base record's meaning does not change by a byte: a consumer that has never
heard of this facet reads exactly the artifact it read before, which is why it
is announced in ``facets_used`` and never in ``facets_required`` (§6).

**The body is the machine's identity, not a reading beside it (spec 12.1).** The
compiled fingerprint is the section 12.3 recipe-grammar hash of this body
exactly as published, less its ``schedule`` member
(:func:`gaspatchio.rollforward._canonical.compiled_identity`), so a reader
holding the facet recomputes the identity of the machine it is about to run
and refuses a body that does not hash to its key. Every field the machine
runs on has a place here: the states and their opening values, the
operations in declared order with their operands and their configuration,
the stopping conditions, the batch axes, and the engine binding that says
whether the machine is portable or reaches into one engine. The schedule the
machine runs on is here too, by its own ``source_sha()``, and is the one
member the identity leaves out: a reader re-running the machine needs its
period count, and the node's own call names the same schedule beside the
fingerprint (spec 16).

One consequence of that split is worth stating for the reader recovering which
operand is which: an optional expression the operation *was* given travels as
an operand, in the order the operation's own fields declare it, and one it was
not given leaves only its ``settings`` key holding null -- so the field order
that matches an operand to the parameter it fills is the facet schema's to
publish, not this payload's.

A compilation this process cannot reach is left out of ``compilations``
altogether rather than named with an empty body. The graph still carries its
node, its identity, and everything the record said it reads; what is missing
is the compiled artefact, and this facet is nothing but a reading of that.

Being a reading rather than a third representation is what places this file
against the other two modules named for an intermediate representation, which
``spec/graph-artifact/README.md`` separates under "Three modules named for an
intermediate representation": what it answers is what the artifact says about
a compiled machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from loguru import logger

from gaspatchio._semantic.ir import Call

from .graph_models import (
    ROLLFORWARD_FINGERPRINT_ATTR,
    ROLLFORWARD_SCHEDULE_ATTR,
    NodeType,
)
from .op_json import op_node_to_json

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio.rollforward._data import CompiledData
    from gaspatchio.rollforward._ir import IR

    from .graph_builder import CalcGraph

__all__ = [
    "FACET_NAME",
    "compilation_disagreements",
    "compilations_in",
    "machine_body",
    "rollforward_ir_facet",
    "rollforward_ir_for",
]

# What the node's own movement summary restates of each increment the body
# applies, and so what the two are held to agree on.
_SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "label",
    "operation",
    "target",
    "reads_running_balance",
)

# The facet's name, in the prefix this package's own facets use.
FACET_NAME: Final[str] = "gaspatchio_rollforward_ir"


def rollforward_ir_facet(compiled: CompiledData) -> dict[str, Any]:
    """Project a compiled rollforward into op-tree terms, for the artifact.

    Args:
        compiled: The compiled rollforward to read.

    Returns:
        The machine: its structural points, its states and their opening
        values, every operation it applies in declared order, and the
        configuration the compiled identity is taken over.

    """
    return machine_body(compiled.ir)


def machine_body(ir: IR) -> dict[str, Any]:
    """Return the compilation body the facet publishes for one machine.

    The one place the body is built: the producer hashes it, less its
    ``schedule``, for the compiled fingerprint, and writes it into the facet
    under that fingerprint, so the two can never come apart.

    Args:
        ir: The machine's IR.

    Returns:
        The body, plain JSON.

    """
    from gaspatchio.rollforward._engine_binding import (  # noqa: PLC0415 — cycle
        derive_engine_binding,
    )

    return {
        "points": list(ir.points),
        "states": _states(ir),
        "increments": _increments(ir),
        "track_increments": ir.track_increments,
        # A set of states, so written in one order: two machines naming the
        # same states in two orders are one machine and one identity.
        "lapse_when_all_non_positive": sorted(ir.lapse_when_all_non_positive),
        "contract_boundary": _contract_boundary(ir),
        "engine_binding": derive_engine_binding(ir),
        "batch_axes": list(ir.batch_axes),
        "schedule": ir.schedule.source_sha(),
    }


def rollforward_ir_for(graph: CalcGraph) -> dict[str, Any] | None:
    """Return the facet's payload for every compilation ``graph`` holds.

    Keyed by the compilation's own published fingerprint -- the same string
    its node carries -- so that a reader holding a node reaches the machine
    behind it without a second index, and two extractions from one
    compilation reach one entry.

    Args:
        graph: The folded calculation graph.

    Returns:
        The payload, or None where the graph holds no compilation this
        process can reach. None is not an empty machine: it is nothing to
        say, and a facet with nothing to say is a facet the artifact does
        not carry and does not announce.

    """
    compilations = {
        fingerprint: rollforward_ir_facet(compiled)
        for _node_id, fingerprint, compiled in compilations_in(graph)
    }
    if not compilations:
        return None
    return {"compilations": compilations}


def compilations_in(graph: CalcGraph) -> list[tuple[str, str, CompiledData]]:
    """Return each compilation the graph holds, in the order it minted them.

    One entry per compilation: the id of the node standing for it, the
    identity that node carries, and the compiled artefact behind it. The
    node id travels with the other two rather than being rebuilt by a
    caller: a compilation is identified by its fingerprint, and its id is
    the one thing about it that is positional within an artifact (section
    8.1), so two callers spelling it two ways is a disagreement waiting to
    be found.

    A node whose compiled artefact this process cannot reach is passed over
    with a line in the log rather than a refusal. The alternative is losing
    the whole facet -- every other compilation in the model with it --
    because one was compiled somewhere else.
    """
    # The lowering package imports the op-tree, so a module-scope import
    # here would close a cycle.
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        rollforward_for,
    )

    found: list[tuple[str, str, CompiledData]] = []
    for node in graph.nodes.values():
        if node.kind is not NodeType.ROLLFORWARD:
            continue
        fingerprint, schedule = _run_of(graph, node.id)
        try:
            found.append((node.id, fingerprint, rollforward_for(fingerprint, schedule)))
        except KeyError:
            logger.debug(
                f"No compiled rollforward is registered for {fingerprint!r} in "
                "this process, so the artifact carries that compilation's node "
                "and identity and says nothing about the machine behind it."
            )
    return found


def _run_of(graph: CalcGraph, node_id: str) -> tuple[str, str]:
    """Return the identity a compilation's node carries, and its schedule's.

    Both off the node's own tree: the machine's fingerprint, which is what
    identifies the compilation, and the schedule it runs on, which is what
    tells two runs of one machine apart in this process.
    """
    tree = graph.op_trees.get(node_id)
    if isinstance(tree, Call):
        attrs = dict(tree.attrs)
        fingerprint = attrs.get(ROLLFORWARD_FINGERPRINT_ATTR)
        schedule = attrs.get(ROLLFORWARD_SCHEDULE_ATTR)
        if isinstance(fingerprint, str) and isinstance(schedule, str):
            return fingerprint, schedule
    msg = (
        f"The node {node_id!r} gives a compiled rollforward's account of "
        f"itself, but its operation tree is {tree!r} rather than the one "
        f"call carrying a {ROLLFORWARD_FINGERPRINT_ATTR!r} and a "
        f"{ROLLFORWARD_SCHEDULE_ATTR!r}. A compilation is identified by the "
        "first and run on the second, so there is no other way to reach the "
        "machine behind this node."
    )
    raise ValueError(msg)


def _states(ir: IR) -> list[dict[str, Any]]:
    """Return each declared state and the opening value it starts from."""
    # The lowering package imports the op-tree; see ``_compilations_in``.
    from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — cycle
        classify_operand_expression,
    )

    state_names = {state.name for state in ir.states}
    point_names = set(ir.points)
    return [
        {
            "name": state.name,
            "init": op_node_to_json(
                classify_operand_expression(state.init, state_names, point_names)
            ),
        }
        for state in ir.states
    ]


def _increments(ir: IR) -> list[dict[str, Any]]:
    """Return every operation the machine applies, in the order it applies them.

    ``reads_running_balance`` is the framework's own escalation criterion,
    read off the operation rather than guessed: it says whether this
    operation's amount depends on the balance it is changing, which is the
    question that decides whether a rollforward was the right tool at all.
    """
    from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — cycle
        increments_of,
    )

    return [
        {
            "label": increment.label,
            "operation": increment.operation,
            "target": increment.target.name,
            "reads_running_balance": increment.reads_running_balance,
            "operands": [op_node_to_json(node) for node in increment.operands],
            "settings": dict(increment.settings),
        }
        for increment in increments_of(ir)
    ]


def _contract_boundary(ir: IR) -> dict[str, Any] | None:
    """Return the test that stops the machine, or None where none was set."""
    from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — cycle
        classify_operand_expression,
    )

    if ir.contract_boundary is None:
        return None
    return op_node_to_json(
        classify_operand_expression(
            ir.contract_boundary,
            {state.name for state in ir.states},
            set(ir.points),
        )
    )


def compilation_disagreements(
    node: Mapping[str, Any], fingerprint: str, body: Mapping[str, Any]
) -> list[tuple[str, str]]:
    """Return where a published compilation is not the machine its identity names.

    Two readings, both from the file alone (spec 12.1). **The identity**: the
    compiled fingerprint is the section 12.3 recipe-grammar hash of the body
    as published, less its ``schedule``, so a body that does not hash to its
    key is a machine nobody compiled under that name -- a floor, an opening
    value, an operation or a rounding edited after export. **The summary**:
    the node's ``increments`` restate, in order, each operation's label,
    kind, target and whether it reads the running balance, and the body
    applies them; a summary that says one thing while the body runs another
    tells a reader a movement that is not the one computed.

    ``validate --deep`` reports each as an error, and so refuses the run: the
    execution reading behind ``run-artifact`` validates deeply before it
    inspects anything.

    Args:
        node: The compilation's node, as the document holds it.
        fingerprint: The identity the node names its compilation by.
        body: The compilation body the facet publishes under that identity.

    Returns:
        ``(where, message)`` pairs, ``where`` relative to the body; empty
        where the body is the machine its identity names.

    """
    from gaspatchio.rollforward._canonical import (  # noqa: PLC0415 — import cycle
        compiled_identity,
    )

    found: list[tuple[str, str]] = []
    try:
        taken: str | None = compiled_identity(body)
    except (TypeError, ValueError) as error:
        taken = None
        message = (
            f"The compilation published under {fingerprint!r} holds a value "
            f"the recipe grammar cannot write ({error}), so its identity "
            "cannot be taken again and the machine cannot be checked "
            "against the name it runs under. Export the model again."
        )
        found.append(("", message))
    if taken is not None and taken != fingerprint:
        message = (
            f"The compilation published under {fingerprint!r} hashes to "
            f"{taken!r}: the machine this file would run is not the one "
            f"its identity names, which every digest of {node.get('id')!r} "
            "and every line reading it is taken over. The body was edited "
            "after export, or written by a producer whose compiler "
            "disagrees with section 12.1. Export the model again from its "
            "source rather than running this body."
        )
        found.append(("", message))
    found.extend(_summary_disagreements(node, body))
    return found


def _summary_disagreements(
    node: Mapping[str, Any], body: Mapping[str, Any]
) -> list[tuple[str, str]]:
    """Return where the node's movement summary and the body's operations differ."""
    summary = node.get("increments")
    applied = body.get("increments")
    if not isinstance(summary, list) or not isinstance(applied, list):
        return []
    if len(summary) != len(applied):
        message = (
            f"The node {node.get('id')!r} summarises {len(summary)} "
            f"movements and its compilation applies {len(applied)}. The "
            "summary is a restatement of the machine, so the two cannot "
            "differ in a file its producer wrote; export the model again."
        )
        return [("/increments", message)]
    found: list[tuple[str, str]] = []
    for index, (said, done) in enumerate(zip(summary, applied, strict=True)):
        if not isinstance(said, dict) or not isinstance(done, dict):
            continue
        differ = [
            field for field in _SUMMARY_FIELDS if said.get(field) != done.get(field)
        ]
        if said.get("ordinal") != index + 1:
            differ.append("ordinal")
        if differ:
            stated = {field: said.get(field) for field in differ}
            ran = {
                field: (index + 1 if field == "ordinal" else done.get(field))
                for field in differ
            }
            message = (
                f"Movement {index + 1} of {node.get('id')!r} is summarised "
                f"as {stated} and its compilation applies {ran}. The "
                "summary restates the machine, so a reader of the movements "
                "would be told one thing while the machine runs another; "
                "export the model again."
            )
            found.append((f"/increments/{index}", message))
    return found
