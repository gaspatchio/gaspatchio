# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Inspect the calculations and declared data an artifact can supply.

Validity, available operation trees and available data are different claims.
This inspection makes each visible without executing formulas, consulting a
producer registry or treating a ``core`` label as backend certification.
Exact operation semantics, runtime inputs and backend support remain unchecked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    State,
    WhenThen,
    walk,
)

from .assumptions import _ARTEFACT_ATTRIBUTES
from .edges import extraction_of, join_keys
from .facets import SCHEMA_URL_TEMPLATE
from .graph_models import ROLLFORWARD_FINGERPRINT_ATTR, ROLLFORWARD_SCHEDULE_ATTR
from .op_json import op_node_from_json
from .rollforward_ir import FACET_NAME
from .tiers import tier_of
from .validate import (
    REPORT_VERSION,
    Finding,
    ValidationReport,
    _document,
    _not_an_envelope,
    _objects,
    _payload_digest,
    validate_artifact,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

    from gaspatchio._semantic.ir import OpNode

__all__ = [
    "ExecutionFinding",
    "ExecutionInspection",
    "InputRequirement",
    "inspect_execution",
]

_Check = Literal["portable_structure", "declared_payloads"]
_Status = Literal["passed", "failed", "blocked", "not_checked"]
_PayloadKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ExecutionFinding:
    """An unavailable calculation or basis, with its location and next move.

    The move ends ``message``, except where the finding names one of the
    model's own -- the line to write a column through, the constructor
    argument that keeps a calculation -- which ``move`` holds apart, so that
    a consumer stating its own general move can state this one instead.
    """

    check: _Check
    code: str
    where: str
    message: str
    move: str | None = None


@dataclass(frozen=True, slots=True)
class InputRequirement:
    """A required arriving definition; historical types can remain unknown."""

    node_id: str
    column: str
    dtype: str
    shape: str
    provenance: str


@dataclass(frozen=True, slots=True)
class ExecutionInspection:
    """Artifact-side evidence, with no aggregate execution-ready verdict.

    ``validation`` covers the whole document. Other checks cover ``roots``
    and their transitive reads only. A passing structure check means trees
    are present and classified as core, not that their signatures or data
    domains are supported. Payload checks cover declared dependencies only.
    The four unassessed checks in ``checks`` still require a consumer and
    actual input values, including row counts and period lengths.
    """

    validation: ValidationReport
    roots: tuple[str, ...]
    reachable: tuple[str, ...]
    required_inputs: tuple[InputRequirement, ...]
    findings: tuple[ExecutionFinding, ...]

    @property
    def checks(self) -> dict[str, _Status]:
        """Keep unchecked claims visible even when the artifact is complete."""
        statuses: dict[str, _Status] = {
            "artifact_validity": "passed" if self.validation.ok else "failed",
            "operation_semantics": "not_checked",
            "input_values": "not_checked",
            "backend_support": "not_checked",
            "numerical_conformance": "not_checked",
        }
        for check in ("portable_structure", "declared_payloads"):
            statuses[check] = (
                "blocked"
                if not self.validation.ok
                else "failed"
                if any(finding.check == check for finding in self.findings)
                else "passed"
            )
        if any(finding.code == "unknown_root" for finding in self.findings) or (
            statuses["portable_structure"] != "passed"
            and statuses["declared_payloads"] == "passed"
        ):
            statuses["declared_payloads"] = "blocked"
        return statuses

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible evidence without implying execution success."""
        return {
            "validation": self.validation.to_dict(),
            "checks": self.checks,
            "roots": list(self.roots),
            "reachable": list(self.reachable),
            "required_inputs": [asdict(item) for item in self.required_inputs],
            "findings": [asdict(item) for item in self.findings],
        }


def inspect_execution(
    artifact: dict[str, Any] | str | Path,
    *,
    roots: Sequence[str] | None = None,
    payloads: Mapping[_PayloadKey, dict[str, Any]] | None = None,
) -> ExecutionInspection:
    """Inspect portable structure and declared payloads without running a model.

    Args:
        artifact: The same document, JSON text or path accepted by
            :func:`validate_artifact`. Deep validation always runs first.
        roots: Exact node IDs, including version suffixes. By default inspect
            every node in the final schema. An empty sequence selects nothing.
        payloads: Explicit external payloads keyed by ``(kind, name,
            fingerprint)`` from the assumptions directory. Each is re-hashed
            using that kind's grammar. They may fill omissions; they cannot
            repair a corrupt inline payload or change the artifact's seal.

    Returns:
        Separate validation, structure and payload results; an inventory of
        required arriving definitions; and explicit unchecked consumer claims.
        No backend is selected, no data is fetched and nothing is executed.

    Raises:
        OSError: If a supplied path cannot be read, as in deep validation.
        ValueError: If a supplied path contains invalid JSON.

    """
    document = _document(artifact)
    if not isinstance(document, dict):
        finding = (
            document if isinstance(document, Finding) else _not_an_envelope(document)
        )
        validation = ValidationReport(REPORT_VERSION, "", (), (finding,))
        return ExecutionInspection(validation, (), (), (), ())
    validation = validate_artifact(document, deep=True)
    if not validation.ok:
        return ExecutionInspection(validation, (), (), (), ())
    nodes = _objects(document["nodes"])
    by_id = {node["id"]: node for node in nodes}
    selected = (
        tuple(dict.fromkeys(roots))
        if roots is not None
        else tuple(node["id"] for node in nodes if node["in_final_schema"])
    )
    # The columns a recorded selection reads are read by every run of the
    # document, whichever nodes it asks for: a replay applies the selection
    # to the book first (section 7.6), so they are required inputs too.
    chosen_on = tuple(
        read
        for step in _objects(document.get("selection"))
        for read in step.get("reads") or ()
        if read in by_id and read not in selected
    )
    reachable, findings = _reachable(by_id, (*selected, *chosen_on))
    entries = _objects(document.get("assumptions"))
    for node in reachable:
        findings.extend(_inspect_node(node, document, entries, payloads or {}, by_id))
    inputs = tuple(
        InputRequirement(
            node["id"], node["column"], node["dtype"], node["shape"], node["provenance"]
        )
        for node in reachable
        if node["kind"] == "input"
    )
    return ExecutionInspection(
        validation,
        selected,
        tuple(node["id"] for node in reachable),
        inputs,
        tuple(findings),
    )


def _reachable(
    by_id: Mapping[str, dict[str, Any]], roots: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[ExecutionFinding]]:
    """Follow versioned reads, retaining document order in the inventory."""
    findings = [
        ExecutionFinding(
            "portable_structure",
            "unknown_root",
            "/nodes",
            f"Root {root!r} is absent. Supply an exact node ID.",
        )
        for root in roots
        if root not in by_id
    ]
    pending = [root for root in roots if root in by_id]
    findings.extend(
        ExecutionFinding(
            "portable_structure",
            "internal_state_root",
            "/nodes",
            f"{root!r} is an internal balance. Select a rollforward output.",
        )
        for root in pending
        if by_id[root]["kind"] == "state"
    )
    seen: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id not in seen:
            seen.add(node_id)
            pending.extend(by_id[node_id]["reads"])
    return [node for node_id, node in by_id.items() if node_id in seen], findings


def _inspect_node(
    node: dict[str, Any],
    document: dict[str, Any],
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
    by_id: Mapping[str, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Separate a node's executable account from the bases it declares."""
    where = f"/nodes/{node['id']}"
    kind = node["kind"]
    if kind == "hole":
        message, move = _no_calculation_behind(node, document)
        yield ExecutionFinding(
            "portable_structure", "unavailable_calculation", where, message, move
        )
        return
    if kind in {"state_graph", "nested_valuation"}:
        yield ExecutionFinding(
            "portable_structure",
            "unavailable_calculation",
            where,
            f"{kind!r} supplies no executable calculation here.",
        )
        return
    if kind == "input":
        for field in ("dtype", "shape"):
            if node[field] == "unknown":
                yield ExecutionFinding(
                    "portable_structure",
                    f"input_{field}_unknown",
                    where,
                    f"The input's {field} is unknown. Supply an artifact "
                    "that records its input interface.",
                )
        return
    if kind == "state":
        return
    if document["profile"] != "executable" or "expr" not in node:
        yield ExecutionFinding(
            "portable_structure",
            "missing_expression",
            where,
            "Export with profile='executable' to carry this tree.",
        )
        return
    yield from _inspect_tree(node["expr"], where + "/expr", entries, payloads)
    yield from _named_payloads(node, where, entries, payloads)
    if kind == "rollforward":
        yield from _inspect_compilation(node, document, entries, payloads, by_id)
    else:
        yield from _binding_findings(node, [node["expr"]], by_id)


def _no_calculation_behind(
    node: dict[str, Any], document: dict[str, Any]
) -> tuple[str, str]:
    """Return why a hole has nothing to run, and the move that gives it something.

    The reason is the document's own, from its holes section. A column
    written straight into the query plan names the line of the write, which
    is where the calculation belongs; a column the frame was built holding
    from another frame's values names the constructor argument that carries
    the calculation across. A column nothing recorded at all is told to be
    assigned through the frame or loaded with the model points, and a name
    the model may never have held, to be spelt as the column it means:
    exporting the same model again would record nothing more.
    """
    column = node.get("column")
    reasons = {
        hole.get("column"): hole.get("reason")
        for hole in document.get("holes") or ()
        if isinstance(hole, dict)
    }
    reason = reasons.get(column)
    if reason == "overwritten":
        location = node.get("source_location")
        at = f" at {location}" if location else ""
        written = (
            f"{column!r} was written straight into the query plan{at}, outside "
            "the frame's own operations, so this document carries no "
            "calculation for it."
        )
        through = (
            "Write the change through the frame at that line -- "
            f"af[{column!r}] = ... -- and export again."
        )
        return written, through
    if reason == "rebuilt":
        made = (
            f"{column!r} holds values a calculation on another frame produced, "
            "and the frame was built over them without that calculation, so "
            "this document carries none for it."
        )
        kept = (
            "Build the frame with ActuarialFrame(df, continue_from=af), where "
            "af is the frame that calculated it, and export again."
        )
        return made, kept
    return _nothing_recorded(column, held=node.get("in_final_schema") is True)


def _nothing_recorded(column: object, *, held: bool) -> tuple[str, str]:
    """Return why a column nothing recorded has nothing to run, and the move."""
    through = (
        f"Assign it through the frame -- af[{column!r}] = ... -- so its "
        "calculation is recorded, or load it with the model points so it "
        "arrives as an input, and export again."
    )
    if held:
        made = (
            f"{column!r} is on the frame and nothing recorded how it was made, "
            "so this document carries no calculation for it."
        )
        return made, through
    read = (
        f"{column!r} is read by a calculation, and nothing recorded what it "
        "holds, so this document carries no calculation for it."
    )
    misspelt = (
        "If the model never held a column by that name, correct the name the "
        "calculation reads instead."
    )
    return read, f"{through} {misspelt}"


def _named_payloads(
    node: dict[str, Any],
    where: str,
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Verify declared dependencies even when no recognized call exposes them."""
    for name in node["reads_assumptions"]:
        matches = [entry for entry in entries if entry["name"] == name]
        if len(matches) != 1:
            yield ExecutionFinding(
                "declared_payloads",
                "unresolved_assumption_name",
                where,
                f"Assumption {name!r} names {len(matches)} entries; "
                "supply one unambiguous dependency.",
            )
            continue
        entry = matches[0]
        yield from _require_payload(
            (entry["kind"], name, entry["fingerprint"]), where, entries, payloads
        )


def _inspect_tree(
    value: object,
    where: str,
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Decode using the existing vocabulary, never an engine's expression text."""
    if not isinstance(value, dict):
        yield ExecutionFinding(
            "portable_structure",
            "unreadable_expression",
            where,
            "Supply an operation tree object.",
        )
        return
    try:
        tree = op_node_from_json(value)
    except (KeyError, TypeError, ValueError) as error:
        yield ExecutionFinding(
            "portable_structure",
            "unreadable_expression",
            where,
            f"Supply a supported operation tree: {error}",
        )
        return
    tier = tier_of(tree)
    if tier != "core":
        yield ExecutionFinding(
            "portable_structure",
            "nonportable_expression",
            where,
            f"This tree is {tier}; supply a core calculation.",
        )
    yield from _tree_payloads(tree, where, entries, payloads)


def _tree_payloads(
    tree: OpNode,
    where: str,
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Read the producer's identity attributes without its object registry.

    A ``join`` node's ``right_fingerprint`` resolves through the assumptions
    directory like any other identity: the right side is an entry of kind
    ``join`` (section 11.1.2), so the loop below finds it, reports it missing or
    ambiguous where it does not resolve, and re-hashes the payload where it
    does. The one case the loop cannot reach is a right side handed over
    lazily, where the attribute is null and the producer took no identity at
    all -- and that is not a missing payload but a record that never claimed
    one.
    """
    for operation in walk(tree):
        if not isinstance(operation, Call):
            continue
        attrs = dict(operation.attrs)
        if operation.name == "join" and not isinstance(
            attrs.get("right_fingerprint"), str
        ):
            yield ExecutionFinding(
                "declared_payloads",
                "join_data_unavailable",
                where,
                "This join's right-hand table was handed over lazily, so the "
                "producer took no content identity for it and the artifact "
                "carries no entry. Nothing here says which table the column "
                "arrived from. Export from a run that joins a collected "
                "frame, or supply and verify the right-hand data in the "
                "consumer.",
            )
        for kind, identity, name_key in _ARTEFACT_ATTRIBUTES:
            fingerprint = attrs.get(identity)
            if isinstance(fingerprint, str):
                name = attrs.get(name_key) if name_key is not None else None
                yield from _require_payload(
                    (kind, name, fingerprint), where, entries, payloads
                )


def _require_payload(
    reference: tuple[str, object, str],
    where: str,
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Resolve the full identity, then verify both inline and supplied values."""
    kind, name, fingerprint = reference
    matches = [
        entry
        for entry in entries
        if entry["kind"] == kind
        and entry["fingerprint"] == fingerprint
        and (name is None or entry["name"] == name)
    ]
    # A join reference carries no name -- a right side is a frame handed to
    # one call rather than a base anybody named -- so naming it would read as
    # "join None (sha256:...)", which looks like a lost name instead of a kind
    # that has none. Its digest is the whole of its identity, so that is what
    # the label carries.
    label = (
        f"{kind} ({fingerprint})"
        if name is None
        else f"{kind} {name!r} ({fingerprint})"
    )
    if len(matches) != 1:
        code = "missing_assumption" if not matches else "ambiguous_assumption"
        yield ExecutionFinding(
            "declared_payloads",
            code,
            where,
            f"Resolve {label} to one assumptions entry; found {len(matches)}.",
        )
        return
    entry = matches[0]
    key = (kind, entry["name"], fingerprint)
    inline = entry.get("payload")
    candidates = (
        [inline] if isinstance(inline, dict) and "omitted" not in inline else []
    )
    if key in payloads:
        candidates.append(payloads[key])
    if not candidates:
        yield ExecutionFinding(
            "declared_payloads",
            "missing_payload",
            where,
            f"Supply the payload for {(kind, entry['name'], fingerprint)!r}.",
        )
    for payload in candidates:
        digest, reason = _payload_digest(kind, payload)
        if digest != fingerprint:
            yield ExecutionFinding(
                "declared_payloads",
                "unverified_payload",
                where,
                f"Payload for {label} cannot be verified: "
                f"{reason or f'content hashes to {digest}'}.",
            )


def _inspect_compilation(
    node: dict[str, Any],
    document: dict[str, Any],
    entries: list[dict[str, Any]],
    payloads: Mapping[_PayloadKey, dict[str, Any]],
    by_id: Mapping[str, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Follow the machine's own schedule and operand trees in its IR facet."""
    fingerprint = node["expr"].get("attrs", {}).get(ROLLFORWARD_FINGERPRINT_ATTR)
    where = f"/facets/{FACET_NAME}/compilations/{fingerprint}"
    facet = document["facets"].get(FACET_NAME, {})
    schema_url = SCHEMA_URL_TEMPLATE.format(name=FACET_NAME)
    if facet.get("_schemaURL") != schema_url:
        yield ExecutionFinding(
            "portable_structure",
            "unknown_compilation_format" if facet else "missing_compilation_facet",
            where,
            f"Supply the compilation facet under {schema_url!r}.",
        )
        yield ExecutionFinding(
            "declared_payloads",
            "unknown_compilation_dependencies",
            where,
            "An unknown facet format cannot establish its dependencies.",
        )
        return
    body = _compilation_body(document, fingerprint)
    if body is None:
        yield ExecutionFinding(
            "portable_structure",
            "missing_compilation",
            where,
            f"Supply the compiled operation trees for {node['id']!r}.",
        )
        yield ExecutionFinding(
            "declared_payloads",
            "unknown_compilation_dependencies",
            where,
            "The missing compilation prevents discovering its schedule.",
        )
        return
    malformed = _compilation_fields(body)
    if malformed:
        yield ExecutionFinding(
            "portable_structure",
            "incomplete_compilation",
            where,
            "Supply the complete compilation fields: " + ", ".join(malformed),
        )
    if body.get("engine_binding") != "portable":
        yield ExecutionFinding(
            "portable_structure",
            "nonportable_compilation",
            where,
            "The compilation does not declare a portable engine binding.",
        )
    schedule = body.get("schedule")
    if not isinstance(schedule, str):
        yield ExecutionFinding(
            "declared_payloads",
            "missing_schedule_identity",
            where,
            "Supply the compilation's schedule fingerprint.",
        )
    else:
        yield from _require_payload(
            ("schedule", None, schedule), where + "/schedule", entries, payloads
        )
    stated = node["expr"].get("attrs", {}).get(ROLLFORWARD_SCHEDULE_ATTR)
    if isinstance(stated, str) and isinstance(schedule, str) and stated != schedule:
        # The fingerprint is the machine alone, so the schedule the node's
        # call states and the one its machine runs on are one fact read
        # twice; a document carrying two answers has no period count.
        yield ExecutionFinding(
            "declared_payloads",
            "compilation_schedule_disagrees",
            where + "/schedule",
            f"The compilation node {node['id']!r} states the schedule {stated!r} "
            f"and its compiled machine runs on {schedule!r}. Export the node "
            "and the machine from one compilation.",
        )
    trees = list(_compilation_trees(body))
    for location, tree in trees:
        yield from _inspect_tree(tree, where + location, entries, payloads)
    yield from _binding_findings(node, [tree for _, tree in trees], by_id)


def _compilation_fields(body: dict[str, Any]) -> list[str]:
    """Check the recorded containers, leaving operation settings semantics unchecked."""
    fields = {
        "points": list,
        "states": list,
        "increments": list,
        "track_increments": bool,
        "lapse_when_all_non_positive": list,
        "engine_binding": str,
        "batch_axes": list,
        "schedule": str,
    }
    missing = [
        name
        for name, expected in fields.items()
        if not isinstance(body.get(name), expected)
    ]
    if "contract_boundary" not in body:
        missing.append("contract_boundary")
    missing.extend(
        name
        for name in ("points", "lapse_when_all_non_positive", "batch_axes")
        if isinstance(body.get(name), list)
        and not all(isinstance(value, str) for value in body[name])
    )
    missing.extend(
        _record_fields(body.get("states"), {"name": str, "init": dict}, "states")
    )
    missing.extend(
        _record_fields(
            body.get("increments"),
            {
                # A label is a name the model reads a movement back by, and a
                # structural step has none: section 16.2 says a `Floor` and a
                # `Round` carry no label field, because a floor is a
                # constraint on the balance rather than a movement anyone
                # booked, and names such a step by the reserved
                # `{kind}@{ordinal}` instead. The published schema admits the
                # null and so does the producer, so a reading that required a
                # string here called every floored rollforward incomplete.
                "label": (str, type(None)),
                "operation": str,
                "target": str,
                "operands": list,
                "settings": dict,
            },
            "increments",
        )
    )
    return missing


def _record_fields(
    value: object, fields: dict[str, type | tuple[type, ...]], name: str
) -> list[str]:
    """Name malformed records without interpreting their domain settings."""
    if not isinstance(value, list):
        return []
    return [
        f"{name}/{index}"
        for index, item in enumerate(value)
        if not isinstance(item, dict)
        or any(
            not isinstance(item.get(field), expected)
            for field, expected in fields.items()
        )
    ]


def _binding_findings(
    node: dict[str, Any],
    trees: list[object],
    by_id: Mapping[str, dict[str, Any]],
) -> Iterator[ExecutionFinding]:
    """Require the trees and versioned read inventory to name the same sources."""
    try:
        expected = {
            reference
            for tree in trees
            if isinstance(tree, dict)
            for reference in _tree_reads(op_node_from_json(tree))
        }
    except (KeyError, TypeError, ValueError):
        return  # The tree inspection reports the malformed expression.
    bindings = [_read_identity(by_id[node_id]) for node_id in node["reads"]]
    actual = set(bindings)
    if expected != actual or len(bindings) != len(actual):
        yield ExecutionFinding(
            "portable_structure",
            "read_binding_mismatch",
            f"/nodes/{node['id']}/reads",
            f"The trees read {sorted(expected)!r}, but versioned reads "
            f"bind {sorted(actual)!r}. Export the matching calculation record.",
        )


def _read_identity(node: dict[str, Any]) -> tuple[str, str]:
    """Read a column, running balance or compilation through its exact node ID."""
    if node["kind"] == "rollforward":
        return "compilation", node.get("expr", {}).get("attrs", {}).get(
            "fingerprint", ""
        )
    if node["kind"] == "state":
        return "state", node["id"].removeprefix("state:")
    return "column", node["column"]


def _tree_reads(tree: OpNode) -> Iterator[tuple[str, str]]:
    """Stop at a rollforward extraction; its embedded operands belong to the machine.

    A join's key is a read the tree names in its ``on`` attribute rather than
    as an operand (section 11.1.2), and the node's ``reads`` bind it like any
    other column.
    """
    if (extraction := extraction_of(tree)) is not None:
        identity = dict(extraction.attrs).get(ROLLFORWARD_FINGERPRINT_ATTR)
        yield "compilation", identity if isinstance(identity, str) else ""
        return
    yield from (("column", key) for key in join_keys(tree))
    match tree:
        case Col(name=name):
            yield "column", name
        case State(name=name):
            yield "state", name
        case EngineNative(deps=deps):
            yield from (("column", name) for name in deps)
        case Call(args=args):
            for argument in args:
                yield from _tree_reads(argument)
        case BinOp(left=left, right=right):
            yield from _tree_reads(left)
            yield from _tree_reads(right)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            yield from _tree_reads(cond)
            yield from _tree_reads(then)
            yield from _tree_reads(otherwise)


def _compilation_body(
    document: dict[str, Any], fingerprint: str
) -> dict[str, Any] | None:
    """Read an optional compilation only when its containers are understood."""
    facet = document["facets"].get(FACET_NAME)
    if not isinstance(facet, dict):
        return None
    compilations = facet.get("compilations")
    if not isinstance(compilations, dict):
        return None
    body = compilations.get(fingerprint)
    return body if isinstance(body, dict) else None


def _compilation_trees(body: dict[str, Any]) -> Iterator[tuple[str, object]]:
    """Name the tree-bearing fields; settings are not operation trees."""
    states = body.get("states")
    increments = body.get("increments")
    if not isinstance(states, list) or not isinstance(increments, list):
        yield "", None
        return
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            yield f"/states/{index}", None
            continue
        yield f"/states/{index}/init", state.get("init", {})
    for index, increment in enumerate(increments):
        if not isinstance(increment, dict) or not isinstance(
            increment.get("operands"), list
        ):
            yield f"/increments/{index}", None
            continue
        for operand, tree in enumerate(increment["operands"]):
            yield f"/increments/{index}/operands/{operand}", tree
    boundary = body.get("contract_boundary", {})
    if boundary is not None:
        yield "/contract_boundary", boundary
