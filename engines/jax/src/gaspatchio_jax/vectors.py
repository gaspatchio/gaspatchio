# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The published vectors through this engine, as a second consumer would run them.

The kit's bundles are read through the kit's own envelope schema and never
through the producer: a conformance claim taken by asking the producer to set
the case up is a claim about the producer. Each case becomes a minimal
executable document -- the inputs as input nodes, the case's own ``expr`` as
one computed node -- sealed with the format's own digests so that the engine's
first stage validates it exactly as it validates a model's artifact.

**Every case gets an outcome, and no case is skipped silently.** A case whose
identifiers this engine has not lowered yet is *not-yet-lowered*, which is a
statement about this engine rather than about the case; the expectation file
beside this module records what this engine expects, so a case moving from
*not-yet-lowered* to *value-pass* is a deliberate edit somebody made and not
a number that drifted.

**The ratios are the agreement rule's, per identifier.** For a one-node
document the line's scale is the largest magnitude among the node's own values
and its operands' values, taken per policy, on both sides -- which is the rule
the whole-model comparison uses, read at the size of one case.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final, Literal

import jsonschema
import polars as pl

from gaspatchio.engines.format import (
    SHA256_PREFIX,
    Col,
    State,
    book_of,
    canonical_bytes,
    document_digest_of,
    encode_sequence,
    encode_text,
    join_key_sides,
    op_node_from_json,
    selection_local,
    selection_section,
)
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal

from .engine import JaxEngine
from .lowerings import LOWERINGS, load
from .lowerings.rollforward import FACET, PRODUCER_URL, SCHEMA_URL

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from gaspatchio.engines.report import RunReport

__all__ = [
    "Invocation",
    "Outcome",
    "VectorRun",
    "normalise",
    "run_vectors",
]

Outcome = Literal[
    "value-pass",
    "value-fail",
    "capability-refusal-expected",
    "capability-refusal-unexpected",
    "domain-refusal-matched",
    "domain-refusal-mismatched",
    "integrity-refusal-matched",
    "not-yet-lowered",
    "adapter-gap",
]

# The document identifier this engine reads, and the digest token beside it.
_SCHEMA: Final = "gaspatchio-graph/v0-preview.3"
_ALGORITHM: Final = "gspv0-preview-3"

# Section 10's scalar names. A case whose inputs or answer are outside these
# is outside what this engine reaches, and says so rather than failing.
_SCALAR: Final[frozenset[str]] = frozenset({"i64", "f64", "bool", "str", "date"})

# The envelope's input-only names: a type a book can carry and section 10
# cannot name, so no document holds one. A duration is stated as whole
# microseconds. The book hands the engine the column as the duration it is;
# the document records it as the whole number section 10's rule says a
# producer must cast it to, and the engine's door refuses the book's column
# by name and names that cast -- the refusal section 10 asks of whoever meets
# a time delta, which is the producer's and the reader's too.
_INPUT_ONLY: Final[dict[str, str]] = {"duration": "i64"}

_EPOCH: Final = datetime.date(1970, 1, 1)

# How many digits of a digest a value object with no name of its own wears
# (section 15).
_NAME_DIGITS: Final = 8

# The case kinds that state a refusal rather than an answer.
_REFUSAL_KINDS: Final[frozenset[str]] = frozenset(
    {"portable-domain-refusal", "backend-capability-refusal", "artifact-type-refusal"}
)

# What each of the kit's refusal causes looks like in this engine's report.
# A cause with no row here is one this engine does not reach; a row is a claim
# that the engine refuses that case for that reason, checked case by case.
# Every marker in a row must be in one line of the report. A marker that is a
# tuple is met by any one of its alternatives: one cause can be stated by more
# than one operation, and each refusal names its own.
_CAUSES: Final[dict[str, tuple[str | tuple[str, ...], ...]]] = {
    "arithmetic-outside-exact-numeric-range": ("mixed.2p53",),
    "comparison-outside-exact-numeric-range": ("mixed.2p53",),
    "checked-float-conversion": ("to_float.exact",),
    "checked-integer-conversion": ("to_integer.integral",),
    "integer-range-conversion": ("to_integer.integral", "i64.range"),
    "integer-overflow": ("i64.range",),
    "ordered-category-comparison": ("an ordered category",),
    "calendar-months-kind": (
        ("excel.edate is written over", "excel.eomonth is written over"),
        ("a Boolean at operand 1", "text at operand 1"),
    ),
    # 11.1.33 states its operations but excel.yearfrac over one value per
    # policy: an operand held per period is refused by the declaration where
    # it is a column, and by the lowering where it is a calculation, and both
    # sentences say what the operation is written over.
    "calendar-operand-per-period": ("is written over one value per period", "11.1.33"),
    # A fold, an override, a guess, an initial value, an axis or a valuation
    # operand held at the shape its clause does not state: refused by the
    # declaration where the operand is a column, by the lowering where it is
    # a calculation, and both sentences say what it is written over.
    "fold-over-a-value-per-policy": (
        "is written over one value per policy",
        "fold the per-period column",
    ),
    "period-override-over-a-value-per-policy": (
        "with_period is written over one value per policy",
    ),
    "explicit-broadcast-axis-required": (
        (
            "broadcast_to_periods is written over one value per policy",
            "names no per-period axis",
        ),
    ),
    "irr-guess-per-period": (
        "excel.irr is written over one value per period",
        "write the guess once per policy",
    ),
    "accumulate-initial-per-period": (
        "projection.accumulate is written over one value per period",
        "write the initial value once per policy",
    ),
    "discount-scalar-domain": (
        (
            "finance.discount is written over one value per period",
            "finance.present_value is written over one value per period",
        ),
        "projection.prospective_value",
    ),
    "stored-numeric-predicate": ("predicate.stored_f64",),
    "invalid-date": ("str.to_date.strict",),
    # Either door the refusal can come out of: the capability, from the
    # record's own declared type, or the lowering, where the operand is a
    # nested expression the record says nothing about.
    "float-conversion-type": ("to_float",),
    "text-conversion-type": ("to_text",),
    "date-parser-capability": ("str.to_date",),
    "negative-scalar-base-list-power": ("per-period",),
    # Section 10 names no time delta, so no document holds one: the book
    # carries the duration and the door refuses it by name, naming the cast
    # that carries it as a whole number -- before any call reads a number
    # out of it, per policy and per period alike.
    "duration-read-as-a-number": ("this book carries it as", "Duration(time_unit="),
    # Both halves of a miss under ``raise`` rest on 11.1.24, and what tells
    # them apart -- a key with no row, or a row with a blank answer cell --
    # is the sentence rather than the clause. Each names the lookup check that
    # caught it, before the book is computed and at completion alike, and
    # that is what tells a miss from the door's refusal of a null numeric
    # key: it rests on 11.1.24 as well and is not this cause, since the door
    # refuses that key whatever the read's own policy says a miss means.
    "lookup-missing-key": ("11.1.24", "(lookup."),
    "lookup-duplicate-key": ("11.1.24",),
    "lookup-empty-table": ("11.1.24",),
    "lookup-key-answer-layout": ("11.1.24",),
    "lookup-key-range": ("11.1.24",),
    # A null outer key list is outside 11.1.24's bounded contract, and this
    # engine refuses a null anywhere in a numeric key column as a limit of its
    # own, citing no clause; its sentence is what names the cause.
    "lookup-null-key-list": ("read only as a key",),
    "list-get-bounds": ("list_get.bounds",),
    "list-get-position-type": ("11.1.22",),
    "period-count-mismatch": ("11.1.18",),
    "irr-multiple-sign-changes": ("11.1.36",),
    "yearfrac-basis": ("11.1.34",),
    "monthly-method-capability": ("11.1.29",),
    "compound-configuration": ("11.1.29",),
    "discount-factor-method-capability": ("11.1.30",),
    "prospective-factor-capability": ("11.1.21",),
    "date-period-capability": ("11.1.33",),
    "excel-epoch-capability": ("11.1.33",),
    "schedule-anchor-capability": ("11.1.37",),
    "schedule-calendar-capability": ("11.1.37",),
    "schedule-frequency-capability": ("11.1.37",),
    "curve-payload-missing-or-ambiguous": ("Resolve curve",),
    # Every way a compiled rollforward can be outside the executable subset
    # rests on 16.1, and what tells them apart is the sentence rather than
    # the clause -- exactly as the two halves of a miss under ``raise`` do.
    # Five causes and one clause, and each is here because this engine was
    # read against the cases that state it: the sentence it gives names the
    # same thing the cause does. The causes left out are the ones where it
    # does not -- an ambiguous label and a jagged operand are met, on those
    # cases' own machines, by the tracking switch that is in front of them.
    "rollforward-operation-capability": ("16.1",),
    "rollforward-column-type": ("16.1",),
    "rollforward-target-point": ("16.1",),
    "rollforward-duplicate-or-empty-state": ("16.1",),
    "rollforward-capability": ("16.1",),
}

# What a payload defect looks like: the inspection's own two check names.
_PAYLOAD_MARKERS: Final[tuple[str, ...]] = (
    "declared_payloads",
    "portable_structure",
    "semantic",
)


class AdapterGap(Exception):  # noqa: N818 -- named for what it is, as the outcome is
    """The runner could not build an invocation for a case.

    Its own defect and never the engine's: a case the adapter cannot set up
    says nothing about what the engine would have done with it, so it is
    reported as a gap in the runner rather than counted as a refusal.
    """


@dataclass(frozen=True, slots=True)
class Invocation:
    """One case, as a document and a book this engine can be handed."""

    case_id: str
    document: dict[str, Any]
    inputs: pl.DataFrame
    resources: dict[str, Any]
    expected_kind: str
    expected: dict[str, Any] | None
    refusal: str | None
    comparison: dict[str, float] | None


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """What happened to one case, and what to say about it."""

    case_id: str
    outcome: Outcome
    detail: str
    covers: tuple[str, ...]
    ratio: float | None


@dataclass(slots=True)
class VectorRun:
    """The whole run: one outcome per case, and the worst ratio per identifier."""

    total: int = 0
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    by_outcome: dict[str, int] = field(default_factory=dict)
    ratios: dict[str, float] = field(default_factory=dict)

    def record(self, found: CaseOutcome) -> None:
        """Take one case's outcome into the run."""
        self.total += 1
        self.outcomes[found.case_id] = found.outcome
        self.details[found.case_id] = found.detail
        self.by_outcome[found.outcome] = self.by_outcome.get(found.outcome, 0) + 1
        if found.ratio is None:
            return
        for identifier in found.covers:
            self.ratios[identifier] = max(self.ratios.get(identifier, 0.0), found.ratio)


def _envelope(schemas: Path) -> dict[str, Any]:
    """Return the kit's own envelope schema, which every bundle is read through."""
    source = schemas / "conformance/vector-envelope.schema.json"
    read: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return read


def _decoded(value: Any) -> Any:  # noqa: ANN401 -- a JSON value is Any-shaped, and narrowing it here would be a cast at every call site
    """Return a vector value with the kit's non-finite encoding read back."""
    if isinstance(value, list):
        return [_decoded(item) for item in value]
    if isinstance(value, dict) and set(value) == {"nonfinite"}:
        return {"nan": math.nan, "+inf": math.inf, "-inf": -math.inf}[
            str(value["nonfinite"])
        ]
    return value


def _polars_dtype(name: str) -> pl.DataType | type[pl.DataType]:
    """Return the Polars type a section 10 name, or an input-only one, stands for."""
    if name.startswith("list["):
        return pl.List(_polars_dtype(name[len("list[") : -1]))
    if name == "duration":
        return pl.Duration("us")
    return {
        "i64": pl.Int64,
        "f64": pl.Float64,
        "bool": pl.Boolean,
        "str": pl.String,
        "date": pl.Date,
    }[name]


def _column(name: str, item: dict[str, Any]) -> pl.Series:
    """Return one of a case's input columns as a Polars column."""
    values = _decoded(item["values"])
    if "date" in item["dtype"]:
        values = _dates(values)
    return pl.Series(name, values, dtype=_polars_dtype(item["dtype"]))


def _dates(value: Any) -> Any:  # noqa: ANN401 -- as above
    """Return a value with every ISO calendar day in it read as a date."""
    if isinstance(value, list):
        return [_dates(item) for item in value]
    return datetime.date.fromisoformat(value) if isinstance(value, str) else value


def _input_node(name: str, dtype: str) -> dict[str, Any]:
    """Return the record of one arriving column, an input-only name as its cast."""
    for held, recorded in _INPUT_ONLY.items():
        if dtype in {held, f"list[{held}]"}:
            dtype = dtype.replace(held, recorded)
    return {
        "id": name,
        "column": name,
        "version": None,
        "kind": "input",
        "dtype": dtype,
        "shape": "list" if dtype.startswith("list[") else "scalar",
        "provenance": "model_points",
        "formula": None,
        "reads": [],
        "reads_assumptions": [],
        "tier": None,
        "local_fingerprint": "",
        "fingerprint": "",
        "in_final_schema": True,
        "materialized_at": None,
        "source_location": None,
        "facets": {},
    }


def _machine_nodes(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the running-state and compilation nodes one case's machine needs.

    A case states its machine in ``compilations`` and its extraction in one
    tree, and section 16 says what a document holding those two looks like:
    one node per running balance, in the reserved ``state:`` namespace and
    reading nothing; one node for the compilation, reading the columns and
    the balances its operations consult, in the order the machine names them
    and each stated once; and the line that extracts a balance reading the
    compilation and nothing else. A one-node document would be a document no
    second reader accepts -- and the producer's own inspector says so, by
    name, before this engine is asked anything.
    """
    stated = case.get("compilations") or {}
    fingerprint = str((case["expr"].get("attrs") or {}).get("fingerprint") or "")
    body = stated.get(fingerprint)
    if not isinstance(body, dict):
        return []
    known = {*case["inputs"], *(f"{_STATE_PREFIX}{one}" for one in _states_of(body))}
    # A read the case gives the machine no column for is left out of the
    # inventory rather than written into it: a node's ``reads`` name nodes,
    # and a case whose whole point is a binding that is not there has no node
    # to name. The engine meets it where 16.1 states it -- at the operand.
    reads = [read for read in _machine_reads(body) if read in known]
    states = [read for read in reads if read.startswith(_STATE_PREFIX)]
    nodes = [_state_node(read) for read in states]
    nodes.append(
        {
            "id": _ROLLFORWARD_PREFIX
            + fingerprint.removeprefix(SHA256_PREFIX)[:_ID_DIGITS],
            "column": None,
            "version": None,
            "kind": "rollforward",
            "dtype": "unknown",
            "shape": "unknown",
            "provenance": "rollforward",
            "formula": None,
            "reads": reads,
            "reads_assumptions": [
                _labelled(entry)
                for entry in case.get("assumptions", [])
                if "payload" in entry and entry["kind"] != "join"
            ],
            "tier": "core",
            "local_fingerprint": "",
            "fingerprint": "",
            "in_final_schema": False,
            "materialized_at": None,
            "source_location": None,
            "facets": {},
            "expr": {
                "op": "call",
                "name": "rollforward",
                "args": [],
                "attrs": {"fingerprint": fingerprint},
            },
        }
    )
    return nodes


def _states_of(body: dict[str, Any]) -> list[str]:
    """Return every state reference one machine's own operands could name."""
    return [
        f"{one['name']}@{point}"
        for one in body.get("states") or ()
        if isinstance(one, dict) and isinstance(one.get("name"), str)
        for point in body.get("points") or ()
    ]


def _machine_reads(body: dict[str, Any]) -> list[str]:
    """Return what one machine consumes, in the order it names it, each once."""
    found: list[str] = []
    trees = [one.get("init") for one in body.get("states") or ()]
    trees.extend(
        operand
        for increment in body.get("increments") or ()
        for operand in increment.get("operands") or ()
    )
    for tree in trees:
        if not isinstance(tree, dict):
            continue
        if tree.get("op") == "col":
            read = str(tree["name"])
        elif tree.get("op") == "state":
            read = f"{_STATE_PREFIX}{tree['name']}"
        else:
            continue
        if read not in found:
            found.append(read)
    return found


def _state_node(node_id: str) -> dict[str, Any]:
    """Return the record of one running balance: not a column, and reading nothing."""
    return {
        "id": node_id,
        "column": None,
        "version": None,
        "kind": "state",
        "dtype": "unknown",
        "shape": "list",
        "provenance": None,
        "formula": None,
        "reads": [],
        "reads_assumptions": [],
        "tier": None,
        "local_fingerprint": "",
        "fingerprint": "",
        "in_final_schema": False,
        "materialized_at": None,
        "source_location": None,
        "facets": {},
    }


# The two namespaces section 8.1 reserves, and how many hex digits of a
# compilation's identity its node id wears.
_STATE_PREFIX: Final = "state:"
_ROLLFORWARD_PREFIX: Final = "rollforward:"
_ID_DIGITS: Final = 12


def _answer_node(case: dict[str, Any], dtype: str, reads: list[str]) -> dict[str, Any]:
    """Return the record of the one computed node a case stands for."""
    column = str(case.get("output_column") or "answer")
    return {
        "id": f"{column}@1",
        "column": column,
        "version": 1,
        "kind": "computed",
        "dtype": dtype,
        "shape": "list" if dtype.startswith("list[") else "scalar",
        "provenance": "assignment",
        "formula": None,
        "reads": reads,
        # The entry's *name*, which is what a node record carries (section 8)
        # and what a consumer resolves the dependency by; the digest is on
        # the call's own attributes. Writing the digest here instead names
        # zero entries, and every payload-bearing case then refuses for a
        # dependency it could not resolve rather than for anything the case
        # is about. A join is left out by section 11.1.2's own rule: an
        # arriving column reads the key it was matched on and not the right
        # side, so the directory carries the entry alone.
        "reads_assumptions": [
            _labelled(entry)
            for entry in case.get("assumptions", [])
            if "payload" in entry
            and entry["kind"] != "join"
            # What a machine consumes hangs off the machine (§16): a line
            # reading a compilation reads the node, and the schedule the
            # machine runs on is the compilation's dependency and not the
            # line's.
            and not case.get("compilations")
        ],
        "engines": [],
        "tier": "core",
        "local_fingerprint": "",
        "fingerprint": "",
        "in_final_schema": True,
        "materialized_at": None,
        "source_location": None,
        "facets": {},
        "expr": case["expr"],
        **_extracts(case, reads),
    }


def _extracts(case: dict[str, Any], reads: list[str]) -> dict[str, Any]:
    """Return the balance a line materialises, where its whole tree extracts one.

    Section 16 puts this on the *column* and on no other door: a line reading
    back a signed movement names no state on the call, and the raw Struct has
    no portable output at all.
    """
    attrs = case["expr"].get("attrs") or {}
    if case["expr"].get("name") != "rollforward.state" or not reads:
        return {}
    return {
        "extracts": {
            "compilation": reads[0],
            "state": f"{attrs.get('state')}@{attrs.get('point')}",
        }
    }


# What a refusal case's answer node is declared as, by the operation at the
# root of its tree. A refusal case states no expected answer -- there is none
# to have a type -- so the adapter writes the type the operation contract
# gives, which is what a producer would have recorded had the line run.
_ANSWER_TYPE_OF: Final[dict[str, str]] = {
    "lt": "bool",
    "le": "bool",
    "gt": "bool",
    "ge": "bool",
    "eq": "bool",
    "ne": "bool",
    "and": "bool",
    "or": "bool",
    "not_": "bool",
    "is_null": "bool",
    "is_not_null": "bool",
    "is_nan": "bool",
    "is_not_nan": "bool",
    "is_finite": "bool",
    "is_infinite": "bool",
    "is_in": "bool",
    "to_integer": "i64",
    "to_float": "f64",
    "to_text": "str",
    "cut": "str",
    "str.to_date": "date",
    "excel.edate": "date",
    "excel.eomonth": "date",
}


def _declared_dtype(case: dict[str, Any]) -> str:
    """Return the type the answer node declares, from the case's own statement."""
    expected = case.get("expected")
    if expected:
        return str(expected["dtype"])
    tree = case["expr"]
    root = str(tree.get("name") or tree.get("kind") or "")
    if root in _ANSWER_TYPE_OF:
        return _ANSWER_TYPE_OF[root]
    if root in ("add", "sub", "mul", "floordiv", "mod", "pow"):
        types = {item["dtype"] for item in case["inputs"].values()}
        return "i64" if types == {"i64"} else "f64"
    return "f64"


def _sealed(document: dict[str, Any]) -> dict[str, Any]:
    """Return the document with the digests the format's own grammar gives it.

    The digests are taken through the producer's own byte grammar, as
    :mod:`gaspatchio.engines.format` publishes it, rather than re-implemented
    here: a second reading of the byte grammar inside a second package is how
    two readings of one grammar end up disagreeing, and the one that disagrees
    is the one nobody was running when the corpus was taken. ``encode_text``
    and ``encode_sequence`` are the encoders the validator uses.
    """
    published: dict[str, bytes] = {}
    for node in document["nodes"]:
        if node.get("expr") is not None:
            tree = op_node_from_json(node["expr"])
        elif node["kind"] == "state":
            # A running state's identity is the reference it stands for
            # (§12.1), not a column name: it is not a column of the model.
            tree = State(str(node["id"]).removeprefix(_STATE_PREFIX))
        else:
            tree = Col(str(node["column"]))
        local = hashlib.sha256(canonical_bytes(tree)).digest()
        merkle = hashlib.sha256(
            local + b"".join(published[read] for read in node["reads"])
        ).digest()
        published[str(node["id"])] = merkle
        node["local_fingerprint"] = SHA256_PREFIX + local.hex()
        node["fingerprint"] = SHA256_PREFIX + merkle.hex()
    for step in document.get("selection") or []:
        local = selection_local(step["kind"], op_node_from_json(step["expr"]))
        merkle = hashlib.sha256(
            local + b"".join(published[read] for read in step["reads"])
        ).digest()
        step["local_fingerprint"] = SHA256_PREFIX + local.hex()
        step["fingerprint"] = SHA256_PREFIX + merkle.hex()
    document["graph_fingerprint"] = SHA256_PREFIX + _graph_fingerprint(
        document, published
    )
    document["document_digest"] = document_digest_of(document)
    return document


def _graph_fingerprint(document: dict[str, Any], published: dict[str, bytes]) -> str:
    """Return the one digest standing for the whole model, from the document.

    Section 12's three counted sections: every (node id, fingerprint) pair,
    every assumption table's content hash, and every unaccounted column --
    the last of which a synthetic document never has.
    """
    pairs = [encode_text(node_id) + published[node_id] for node_id in sorted(published)]
    tables = [
        encode_text(str(entry["fingerprint"]))
        for entry in sorted(
            (
                entry
                for entry in document.get("assumptions") or []
                if entry.get("kind") == "table"
            ),
            key=lambda entry: str(entry["fingerprint"]),
        )
    ]
    selected = [
        bytes.fromhex(str(step["fingerprint"]).removeprefix(SHA256_PREFIX))
        for step in document.get("selection") or []
    ]
    return hashlib.sha256(
        encode_sequence(pairs)
        + encode_sequence(tables)
        + encode_sequence([])
        + selection_section(selected)
    ).hexdigest()


def normalise(case: dict[str, Any], bundle: str) -> Invocation:
    """Return one case as a document and a book, or say the adapter cannot.

    Raises:
        AdapterGap: If the case's inputs or answer carry a type this document
            grammar has no name for -- the widths and dictionary encodings the
            envelope admits on an input and section 10 does not name.

    """
    for name, item in case["inputs"].items():
        if not _named_here(item["dtype"], arriving=True):
            message = f"{bundle}:{case['id']} carries {name} as {item['dtype']}"
            raise AdapterGap(message)
    inputs = pl.DataFrame(
        [_column(name, item) for name, item in case["inputs"].items()]
    )
    nodes = [_input_node(name, item["dtype"]) for name, item in case["inputs"].items()]
    reads = _reads_of(case["expr"], [node["id"] for node in nodes])
    machine = _machine_nodes(case)
    if machine:
        # A line reading a compilation reads the node and never the columns
        # behind it (§16), so the answer node's whole read inventory is the
        # compilation, and what the machine takes hangs off the machine.
        nodes.extend(machine)
        reads = [machine[-1]["id"]]
    nodes.append(_answer_node(case, _declared_dtype(case), reads))
    selection = _selection_of(case, nodes)
    document = _sealed(
        {
            "schema": _SCHEMA,
            "profile": "executable",
            "fingerprint_algorithm": _ALGORITHM,
            "producer": {"name": "gaspatchio-jax-vectors", "version": "0.1.0"},
            "created_at": "2026-09-21T00:00:00Z",
            "model": {
                "label": bundle,
                "source_path": None,
                "source_sha": None,
                "git": None,
                "model_points": None,
            },
            "graph_fingerprint": "",
            # The book this synthetic document stands over is the case's own
            # inputs, digested by the producer's rule so the document reads as
            # the producer would have written it.
            "book": book_of(nodes, inputs, selection=selection),
            "facets_used": [FACET] if case.get("compilations") else [],
            "facets_required": [],
            "nodes": nodes,
            # One edge per stated read, over every node rather than over the
            # answer alone: a compilation reads its columns and its balances
            # too, and the file records each dependency twice on purpose --
            # once as the lineage a reviewer reads down the page and once as
            # the graph an impact cone is drawn through.
            "edges": [
                {"source": read, "target": node["id"], "relationship": "DIRECT"}
                for node in nodes
                for read in node["reads"]
            ],
            "assumptions": [
                _assumption(entry)
                for entry in case.get("assumptions", [])
                if "payload" in entry
            ]
            + [entry for entry in (_right_side(case),) if entry is not None]
            + _selected_right_sides(case),
            "holes": [],
            "boundaries": [],
            "sources": [],
            "enrichment": None,
            "policies": [],
            # The machine, where the case carries one. A compiled rollforward
            # is not restated inside the node's own bytes (§12.1), so the one
            # place a second engine reads it is this facet -- and a case
            # handed over without it would be a case about a fingerprint with
            # nothing behind it.
            "facets": (
                {
                    FACET: {
                        "_producer": PRODUCER_URL,
                        "_schemaURL": SCHEMA_URL,
                        "compilations": case["compilations"],
                    }
                }
                if case.get("compilations")
                else {}
            ),
            # The rows the case's steps keep (section 7.6), where it states
            # any: the engine applies them to the book before it projects.
            **({"selection": selection} if selection else {}),
        }
    )
    return Invocation(
        case_id=str(case["id"]),
        document=document,
        inputs=inputs,
        resources={
            "assumptions": case.get("assumptions", []),
            "compilations": case.get("compilations", {}),
            "producer_setup": case.get("producer_setup"),
            "output_column": case.get("output_column", "answer"),
        },
        expected_kind=str(case["case_kind"]),
        expected=case.get("expected"),
        refusal=case.get("refusal"),
        comparison=case.get("comparison"),
    )


def _assumption(entry: dict[str, Any]) -> dict[str, Any]:
    """Return one of a case's assumption entries as the document records it.

    A table states a ``name`` and a content ``fingerprint``; a schedule and a
    curve state neither and carry a recipe digest under ``source_sha``. Section
    8's entry has one digest field and admits a null name, so the two shapes
    meet here rather than in two document grammars.
    """
    return {
        "kind": entry["kind"],
        "name": _labelled(entry),
        "fingerprint": entry.get("fingerprint") or entry["source_sha"],
        "payload": entry["payload"],
    }


def _labelled(entry: dict[str, Any]) -> str:
    """Return the name this entry stands under, minting section 15's where it has none.

    A value object nobody named -- a schedule, a curve, a join's right side --
    takes its kind and the first eight hex digits of its digest. That label is
    not the identity and nothing resolves by it alone; what it is for is that
    a node's ``reads_assumptions`` has something to name.
    """
    stated = entry.get("name")
    if isinstance(stated, str):
        return stated
    digest = str(entry.get("fingerprint") or entry["source_sha"])
    return f"{entry['kind']}:{digest.removeprefix(SHA256_PREFIX)[:_NAME_DIGITS]}"


def _right_side(case: dict[str, Any]) -> dict[str, Any] | None:
    """Return the join entry a recording door's right side stands in, or None.

    The kit states a join's right side as the frame the producer is to join
    on, because the case is about what the producer *records*. What a second
    engine needs is the same frame as the entry section 15 files it under,
    and the two are one thing written twice -- so the adapter writes the
    entry and the format's own digest is what says whether it got it right:
    the engine re-hashes every declared payload before it reads one, and a
    right side assembled any other way than the order the fingerprint was
    taken over refuses there rather than answering.
    """
    setup = case.get("producer_setup")
    if not isinstance(setup, dict) or setup.get("kind") != "join":
        return None
    right = setup["right"]
    fingerprint = str(case["expr"]["attrs"]["right_fingerprint"])
    columns = [
        {"name": name, "dtype": _neutral_of(values)} for name, values in right.items()
    ]
    rows = [list(row) for row in zip(*right.values(), strict=True)]
    entry = {"kind": "join", "fingerprint": fingerprint}
    return {
        "kind": "join",
        "name": _labelled(entry),
        "fingerprint": fingerprint,
        "payload": {"columns": columns, "rows": rows},
    }


def _selection_of(
    case: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a selection case's steps as section 7.6's entries, digests to follow.

    Each step reads the input columns its tree names; a semi or anti join
    reads its left key. The digests are taken where every other one is, in
    :func:`_sealed`, through the producer's own grammar.
    """
    inputs = [node["id"] for node in nodes if node["kind"] == "input"]
    entries: list[dict[str, Any]] = []
    for position, step in enumerate(case.get("selection") or [], start=1):
        tree = step["expr"]
        attrs = tree.get("attrs") or {}
        reads = (
            [key for key in join_key_sides(attrs["on"])[0] if key in inputs]
            if step["kind"] != "filter"
            else _reads_of(tree, inputs)
        )
        entry: dict[str, Any] = {
            "id": f"selection:{position}",
            "kind": step["kind"],
            "expr": tree,
            "tier": "core",
            "reads": reads,
            "local_fingerprint": "",
            "fingerprint": "",
            "source_location": None,
        }
        if step["kind"] != "filter":
            entry["right_fingerprint"] = attrs["right_fingerprint"]
        entries.append(entry)
    return entries


def _selected_right_sides(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the join entry each semi or anti step's right side stands in.

    The rows go in the canonical order the fingerprint was taken over --
    every column ascending by name, rows sorted by every column -- so the
    engine's re-hash of the declared payload is what says whether they were
    written right.
    """
    entries: list[dict[str, Any]] = []
    for step in case.get("selection") or []:
        if step["kind"] == "filter":
            continue
        right = step["right"]
        names = sorted(right)
        fingerprint = str(step["expr"]["attrs"]["right_fingerprint"])
        entry = {"kind": "join", "fingerprint": fingerprint}
        entries.append(
            {
                "kind": "join",
                "name": _labelled(entry),
                "fingerprint": fingerprint,
                "payload": {
                    "columns": [
                        {"name": name, "dtype": _neutral_of(right[name])}
                        for name in names
                    ],
                    "rows": sorted(
                        list(row)
                        for row in zip(*(right[n] for n in names), strict=True)
                    ),
                },
            }
        )
    return entries


def _neutral_of(values: list[Any]) -> str:
    """Return section 10's name for the type a column of cells is carried as."""
    for cell in values:
        if isinstance(cell, bool):
            return "bool"
        if isinstance(cell, str):
            return "str"
        if isinstance(cell, float):
            return "f64"
        if isinstance(cell, int):
            return "i64"
    return "f64"


def _reads_of(tree: dict[str, Any], available: list[str]) -> list[str]:
    """Return the input nodes one tree reads, in first-mention order."""
    found: list[str] = []
    for name in _columns_in(tree):
        if name in available and name not in found:
            found.append(name)
    return found


def _columns_in(tree: dict[str, Any]) -> Iterator[str]:
    """Yield every column name an operation tree names.

    A join names its key in its ``on`` attribute rather than as an operand,
    and section 11.1.2 has its node read that key: the left side's names,
    in the order the attribute lists them.
    """
    if tree.get("op") == "col":
        yield str(tree["name"])
    if tree.get("op") == "call" and tree.get("name") == "join":
        yield from join_key_sides((tree.get("attrs") or {}).get("on"))[0]
    for key in ("left", "right", "cond", "then", "otherwise"):
        child = tree.get(key)
        if isinstance(child, dict):
            yield from _columns_in(child)
    for argument in tree.get("args") or ():
        if isinstance(argument, dict):
            yield from _columns_in(argument)


def _reached_by_this_engine(case: dict[str, Any]) -> bool:
    """Return whether every identifier and shape the case names is lowered here.

    A per-period column is one of this engine's shapes now, so a case whose
    columns are lists of section 10's own scalars is reached; what is still
    outside is a width the document grammar has no name for -- a fixed-width
    array, a dictionary encoding -- which the adapter says so about.
    """
    covers = [*case.get("covers", []), *case.get("structural_covers", [])]
    if any(name not in LOWERINGS for name in covers):
        return False
    arriving = [item["dtype"] for item in case["inputs"].values()]
    expected = case.get("expected")
    answered = [str(expected["dtype"])] if expected else []
    return all(_named_here(name, arriving=True) for name in arriving) and all(
        _named_here(name) for name in answered
    )


def _named_here(dtype: str, *, arriving: bool = False) -> bool:
    """Return whether this document grammar has a name for one type.

    An arriving column may also carry one of the envelope's input-only names,
    which the adapter records as its cast and hands the engine as it is.
    """
    known = _SCALAR | set(_INPUT_ONLY) if arriving else _SCALAR
    if dtype.startswith("list[") and dtype.endswith("]"):
        return dtype[len("list[") : -1] in known
    return dtype in known


def run_vectors(
    vectors_dir: Path, *, expectations: Mapping[str, str] | None = None
) -> VectorRun:
    """Run every published case through this engine and report by outcome.

    Args:
        vectors_dir: The published bundles, as the core ships them.
        expectations: What this engine expects of each case, read from
            ``tests/expectations.json``. Its one effect is to promote a
            reviewed capability refusal from *unexpected* to *expected*: a
            case this engine refuses on a stated ground -- a null-bearing
            book at the door, a null an integer division would mint -- is a
            refusal somebody looked at, and looking at it is the edit.
            Nothing else is promoted, so a case that starts failing cannot be
            quietened by this file.

    Returns:
        One outcome per case, and the worst observed ratio per identifier.

    """
    load()
    schemas = vectors_dir.parent
    envelope = _envelope(schemas)
    engine = JaxEngine()
    run = VectorRun()
    reviewed = dict(expectations or {})
    for source in sorted(vectors_dir.glob("*.json")):
        bundle = json.loads(source.read_text(encoding="utf-8"))
        jsonschema.validate(bundle, envelope)
        for case in bundle["cases"]:
            found = _one_case(case, source.name, engine)
            run.record(_reviewed(found, reviewed.get(found.case_id)))
    return run


def _reviewed(found: CaseOutcome, expected: str | None) -> CaseOutcome:
    """Return the outcome with a reviewed capability refusal promoted."""
    if (
        found.outcome == "capability-refusal-unexpected"
        and expected == "capability-refusal-expected"
    ):
        return replace(found, outcome="capability-refusal-expected")
    return found


def _one_case(case: dict[str, Any], bundle: str, engine: JaxEngine) -> CaseOutcome:
    """Return what happened when this engine was handed one case."""
    covers = tuple(case.get("covers", []))
    reached = _reached_by_this_engine(case)
    try:
        invocation = normalise(case, bundle)
    except AdapterGap as gap:
        return CaseOutcome(
            str(case["id"]),
            "not-yet-lowered" if not reached else "adapter-gap",
            str(gap),
            covers,
            None,
        )
    except (ValueError, TypeError, KeyError) as broken:
        return CaseOutcome(
            str(case["id"]),
            "adapter-gap",
            f"{type(broken).__name__}: {broken}",
            covers,
            None,
        )
    try:
        result = engine.run(invocation.document, invocation.inputs, FrameSink())
    except EngineRefusal as refused:
        return _refused(case, invocation, refused, covers, reached=reached)
    except Exception as broken:  # noqa: BLE001 -- an engine defect is the runner's finding
        return CaseOutcome(
            str(case["id"]),
            "adapter-gap",
            f"{type(broken).__name__}: {broken}",
            covers,
            None,
        )
    return _answered(case, invocation, result.columns, covers, reached=reached)


def _refused(
    case: dict[str, Any],
    invocation: Invocation,
    refused: EngineRefusal,
    covers: tuple[str, ...],
    *,
    reached: bool,
) -> CaseOutcome:
    """Return the outcome for a case the engine refused."""
    rendered = refused.report.render()
    case_id = str(case["id"])
    if case["case_kind"] == "integrity-mutation":
        matched = any(marker in rendered for marker in _PAYLOAD_MARKERS)
        return CaseOutcome(
            case_id,
            "integrity-refusal-matched" if matched else "domain-refusal-mismatched",
            _first_line(rendered),
            covers,
            None,
        )
    if case["case_kind"] in _REFUSAL_KINDS:
        detail = _domain_refusal_detail(invocation.refusal, refused.report)
        if detail is not None:
            return CaseOutcome(case_id, "domain-refusal-matched", detail, covers, None)
        return CaseOutcome(
            case_id,
            "not-yet-lowered" if not reached else "domain-refusal-mismatched",
            _first_line(rendered),
            covers,
            None,
        )
    return CaseOutcome(
        case_id,
        "not-yet-lowered" if not reached else "capability-refusal-unexpected",
        _first_line(rendered),
        covers,
        None,
    )


def _domain_refusal_detail(cause: str | None, report: RunReport) -> str | None:
    """Return the evidence for a published refusal cause, if the report has it."""
    if cause == "raw-struct-outside-portable-output":
        return next(
            (
                finding.line()
                for finding in report.refusals
                if finding.group == "tree"
                and finding.clause == "16.3"
                and "Struct" in finding.what
                and "no portable output" in finding.what
            ),
            None,
        )
    rendered = report.render()
    markers = _CAUSES.get(str(cause), ())
    if not markers or not _marked(rendered, markers):
        return None
    return next(
        (line.strip() for line in rendered.splitlines() if _marked(line, markers)),
        _first_line(rendered),
    )


def _marked(text: str, markers: tuple[str | tuple[str, ...], ...]) -> bool:
    """Return whether every marker, or one alternative of each, is in the text."""
    return all(
        any(one in text for one in ((marker,) if isinstance(marker, str) else marker))
        for marker in markers
    )


def _first_line(rendered: str) -> str:
    """Return the first refusal a report carries, for the run's own detail line."""
    for line in rendered.splitlines():
        if line.startswith("  "):
            return line.strip()
    return rendered.splitlines()[0] if rendered else ""


def _answered(
    case: dict[str, Any],
    invocation: Invocation,
    frame: pl.DataFrame,
    covers: tuple[str, ...],
    *,
    reached: bool,
) -> CaseOutcome:
    """Return the outcome for a case the engine answered."""
    case_id = str(case["id"])
    if case["case_kind"] in _REFUSAL_KINDS or case["case_kind"] == "integrity-mutation":
        return CaseOutcome(
            case_id,
            "domain-refusal-mismatched",
            "the engine answered where the case states a refusal",
            covers,
            None,
        )
    if not reached:  # pragma: no cover -- an unreached case that answered anyway
        return CaseOutcome(
            case_id, "value-fail", "answered outside its claim", covers, None
        )
    column = str(invocation.resources["output_column"])
    if column not in frame.columns:
        return CaseOutcome(
            case_id, "value-fail", f"no column {column!r} in the result", covers, None
        )
    wanted = _decoded((invocation.expected or {})["values"])
    got = frame[column].to_list()
    comparison = invocation.comparison or {"atol": 0.0, "rtol": 0.0}
    failure = _compared(got, wanted, comparison)
    if failure is not None:
        return CaseOutcome(case_id, "value-fail", failure, covers, None)
    return CaseOutcome(
        case_id,
        "value-pass",
        _reference_precision(invocation, wanted),
        covers,
        _ratio(got, wanted, invocation),
    )


def _compared(
    got: list[object], wanted: list[object], comparison: dict[str, float]
) -> str | None:
    """Return the first disagreement between two answers, or None if there is none."""
    if len(got) != len(wanted):
        return f"{len(got)} values against {len(wanted)}"
    for position, (found, expected) in enumerate(zip(got, wanted, strict=True)):
        failure = _one_value(found, expected, comparison, position)
        if failure is not None:
            return failure
    return None


def _one_value(  # noqa: PLR0911 -- one return per way two values can part
    found: Any,  # noqa: ANN401 -- a JSON value, and a narrower type would be a cast here
    expected: Any,  # noqa: ANN401 -- as above
    comparison: dict[str, float],
    position: int,
) -> str | None:
    """Return why one value disagrees, or None where it does not."""
    if isinstance(expected, list):
        if not isinstance(found, list) or len(found) != len(expected):
            return f"row {position}: {found!r} is not {len(expected)} periods"
        for period, (cell, wanted) in enumerate(zip(found, expected, strict=True)):
            failure = _one_value(cell, wanted, comparison, period)
            if failure is not None:
                return f"row {position}, {failure}"
        return None
    if isinstance(found, datetime.date):
        found = found.isoformat()
    if expected is None or isinstance(expected, (bool, str)):
        return (
            None if found == expected else f"row {position}: {found!r} != {expected!r}"
        )
    if isinstance(expected, float) and math.isnan(expected):
        return (
            None
            if isinstance(found, float) and math.isnan(found)
            else f"row {position}: {found!r} is not NaN"
        )
    if not isinstance(found, (int, float)) or isinstance(found, bool):
        return f"row {position}: {found!r} is not a number"
    if not math.isfinite(float(expected)):
        return (
            None if found == expected else f"row {position}: {found!r} != {expected!r}"
        )
    within = abs(float(found) - float(expected)) <= comparison["atol"] + comparison[
        "rtol"
    ] * abs(float(expected))
    return None if within else f"row {position}: {found!r} != {expected!r}"


# Reviewed reference precision, bound to the expected dtype and every value.
# These two published arrays are rounded to six decimals. Acceptance budgets
# never establish reference precision; a changed expected dataset is measured
# until its precision is separately reviewed.
_ROUNDED_REFERENCES: Final[dict[str, str]] = {
    "rollforward-structural-floor-that-never-bites": (
        "72a058889f83ee36e70bc194724b12fa4f07170261be56d6bd36d19260988381"
    ),
    "rollforward-ratchet-at-the-anniversary": (
        "72c6ab34cf4628fed034b65b94b050d7e5dc5668e362bbb368e3723b86b0b4ff"
    ),
}


def _reference_precision(invocation: Invocation, wanted: list[object]) -> str:
    """Explain an explicitly reviewed rounded reference, or return no exclusion."""
    if invocation.case_id not in _ROUNDED_REFERENCES:
        return ""
    expected = {"dtype": (invocation.expected or {}).get("dtype"), "values": wanted}
    digest = hashlib.sha256(
        json.dumps(
            expected, sort_keys=True, separators=(",", ":"), allow_nan=True
        ).encode()
    ).hexdigest()
    if _ROUNDED_REFERENCES.get(invocation.case_id) != digest:
        return ""
    return (
        f"{invocation.case_id}: the agreement rule is not measurable from the "
        "published expected array rounded to six decimals; ordinary vector-budget "
        "comparison still runs "
        f"(expected sha256:{digest})"
    )


def _ratio(
    got: list[object], wanted: list[object], invocation: Invocation
) -> float | None:
    """Return the case's worst agreement ratio, or None where nothing is numeric.

    The scale is the line's and it is taken per policy: the largest magnitude
    among the node's own values and the values of every column it reads, on
    both sides. A policy whose scale is zero compared exactly and contributes
    no ratio.

    The two explicitly reviewed rounded reference datasets are excluded by
    their expected-data digests, never by their acceptance tolerances.
    """
    if _reference_precision(invocation, wanted):
        return None
    reads = [
        invocation.inputs[name].to_list()
        for name in invocation.inputs.columns
        if _numeric(invocation.inputs[name].dtype)
    ]
    worst: float | None = None
    for position, (found, expected) in enumerate(zip(got, wanted, strict=False)):
        read = [
            magnitude
            for column in reads
            if position < len(column)
            for magnitude in _magnitudes(column[position])
        ]
        for cell, want in zip(_cells_of(found), _cells_of(expected), strict=False):
            if not isinstance(want, (int, float)) or isinstance(want, bool):
                continue
            if not math.isfinite(float(want)):
                continue
            scale = max([abs(float(want)), *_magnitudes(cell), *read])
            if scale == 0.0:
                continue
            worst = max(worst or 0.0, abs(float(cell) - float(want)) / scale)  # type: ignore[arg-type]
    return worst


def _numeric(dtype: pl.DataType) -> bool:
    """Return whether a column's cells are numbers the agreement scale reads."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    return inner in (pl.Int64, pl.Float64)


def _cells_of(value: object) -> list[object]:
    """Return one policy's cells, a per-policy value standing as one cell."""
    return list(value) if isinstance(value, list) else [value]


def _magnitudes(value: object) -> list[float]:
    """Return the magnitudes one policy's own cells contribute to the line's scale."""
    return [
        abs(float(cell))
        for cell in _cells_of(value)
        if isinstance(cell, (int, float))
        and not isinstance(cell, bool)
        and math.isfinite(float(cell))
    ]
