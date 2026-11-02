# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whether two engines agree on a model, line by line and policy by policy.

The specification's agreement rule (section 11.1.12), and nothing else: two
finite results agree when their difference is within 1e-12 of the line's
scale, where the scale is the largest
magnitude among the node's own values and the values of every node it reads,
over **that policy's** whole timeline, on both sides. Per policy before any
maximum, so that no policy lends another its allowance -- a book whose
largest reserve is nine figures would otherwise forgive a rounding error on
a policy whose reserve is four.

**Why a scale rather than a fixed floor.** The cancellation case is the
argument. Eleven closing balances computed from operands near 17,000 differ
by 7e-10 between two engines; a fixed floor of 1e-10 calls that a difference
in the model, and it is not one -- it is the last place of a double, 4e-14
of the line. Against operands of 1 the same 7e-10 is the whole of the
answer. One number cannot serve both, and the scale is what tells them
apart. The fixed floor is still printed beside every verdict, as the strict
floor: ``|a - b| <= 1e-10 + 1e-12 * |reference|``, one allowance for every
line whatever it was computed from. It stays fixed so that it means the same
in every report, and a reviewer who has compared runs by it before can read
this one against theirs; it decides no verdict, because it cannot see the
cancellation above.

**What is exact.** Integers, booleans, dates and strings; the length of
every list; where the nulls are; whether a value is a NaN; which way an
infinity points. The sign of a zero is not compared. A zero budget is a
value check, and identity already tells the two zeros apart, because section
12.1's byte grammar writes each with its own sign.

**Three verdicts, because a final-schema file does not carry the reads.**
The scale needs them. Over a file that has them, the rule is the rule. Over
one that does not, the scale is taken from the values in hand, which can
only be smaller than the true scale -- so a line that *passes* the reduced
test would pass the full one too and is *agree*, while a line that fails it
might not have failed the full one and is *indeterminate*, printed with the
scale the absent reads would have to supply. *Disagree* is reserved for the
full rule. A required result a file does not carry is never agreement.

The rule itself is :mod:`gaspatchio.engines._agreement`'s, read one line at a
time in one Polars pass; this module decides which lines a comparison asks
for, which rows are which policy, and what the readings come to as verdicts.
"""

from __future__ import annotations

import calendar
import datetime
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import polars as pl

from gaspatchio._dtypes import neutral_dtype

from ._agreement import TOLERANCE, policy_magnitude, read_line, read_scale
from .protocol import VALUE_BEARING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from ._agreement import LineReading
    from .protocol import ResultManifest, Scope

__all__ = [
    "CompareReport",
    "LineComparison",
    "Verdict",
    "compare_results",
]

Verdict = Literal["agree", "disagree", "indeterminate"]

REPORT_VERSION = "gaspatchio-graph-compare/v0-preview.2"

# The scalar types whose values are compared exactly rather than to a band.
# ``f64`` is the only one that is not, which is what makes the band a
# statement about binary floating point rather than about the model.
_EXACT_SCALARS = frozenset({"bool", "i64", "str", "date", "datetime"})


@dataclass(frozen=True, slots=True)
class LineComparison:
    """What one node's two columns came to.

    Attributes:
        node_id: The node compared.
        max_abs: The largest absolute difference, over every policy. None on
            a line decided exactly -- an integer, a date, a length, a null
            position, the class of a NaN. Those part or they do not, and how
            far apart they were is not a magnitude question; a zero there
            would read as "identical to the last place", which is the one
            thing it does not mean.
        max_ratio: That difference as a fraction of its own policy's scale,
            maximised over policies; None where the scale was 0 and the line
            compared exactly.
        scale: The scale the verdict was decided against -- the scale of the
            policy whose ratio was the largest, or the largest scale seen
            where no ratio applied.
        reads_absent: Node ids this line reads whose values were absent from
            either file. A read on one side cannot supply the other's
            magnitude, so it is out of the scale for both.
        verdict: Agreement under the full rule, under the reduced one, or
            not decidable from the values in hand.
        lower_bound: For an indeterminate line, the scale the absent reads
            would have to supply for the difference to pass.
        strict_floor: Whether the fixed floor held as well -- a difference
            within 1e-10 plus 1e-12 of the reference value, the same on every
            line. Printed beside the verdict; it decides nothing.
        exact_class: What was compared exactly, where that is what decided
            the line -- the declared type for an exact type, or the aspect
            that parted them for a float line.

    """

    node_id: str
    max_abs: float | None
    max_ratio: float | None
    scale: float
    reads_absent: tuple[str, ...]
    verdict: Verdict
    lower_bound: float | None
    strict_floor: bool
    exact_class: str | None

    def to_dict(self) -> dict[str, object]:
        """Return this line as JSON carries it."""
        return {
            "node_id": self.node_id,
            "max_abs": self.max_abs,
            "max_ratio": self.max_ratio,
            "scale": self.scale,
            "reads_absent": list(self.reads_absent),
            "verdict": self.verdict,
            "lower_bound": self.lower_bound,
            "strict_floor": self.strict_floor,
            "exact_class": self.exact_class,
        }


@dataclass(frozen=True, slots=True)
class CompareReport:
    """What two result files came to, and what the comparison rested on.

    Attributes:
        report_version: The grammar this report is written in.
        artifact_fingerprint: The graph both files claim to be results of.
        document_digest: The seal of the written document the comparison was
            handed, or None where it carries none. Recorded beside the
            fingerprint as every citation of a document is (§13.1), never
            compared: two exports of one model carry two seals and one
            fingerprint, and the comparison under either is the same.
        scope: What both manifests state -- the two must agree.
        before: The earlier side's manifest.
        after: The later side's manifest.
        same_inputs: Whether both sides read the same book. A conformance
            claim needs True, and the report says which it is either way: a
            comparison over two books is still a comparison, and calling it
            one over one book would be the untruth.
        rows_matched_by: Identity or position.
        rows_matched_on: The columns rows were paired on, by identity; or,
            by position, the columns that showed both files' rows in one
            order. Empty where position was shown by both sides having read
            one book, which ``same_inputs`` then states.
        missing: Results the scope requires that a file does not carry.
        lines: One entry per node compared.
        verdict: Disagree if any line does; else indeterminate if any line
            is, or any required result is missing, or nothing was compared;
            else agree.

    """

    report_version: str
    artifact_fingerprint: str
    document_digest: str | None
    scope: Scope
    before: ResultManifest
    after: ResultManifest
    same_inputs: bool
    rows_matched_by: Literal["identity", "position"]
    rows_matched_on: tuple[str, ...]
    missing: tuple[tuple[str, Literal["before", "after"]], ...]
    lines: tuple[LineComparison, ...]
    verdict: Verdict

    def to_dict(self) -> dict[str, object]:
        """Return the whole report as JSON carries it."""
        return {
            "report_version": self.report_version,
            "artifact_fingerprint": self.artifact_fingerprint,
            "document_digest": self.document_digest,
            "scope": self.scope,
            "before": {
                "producer": self.before.producer,
                "inputs_digest": self.before.inputs_digest,
                "versions": self.before.versions,
            },
            "after": {
                "producer": self.after.producer,
                "inputs_digest": self.after.inputs_digest,
                "versions": self.after.versions,
            },
            "same_inputs": self.same_inputs,
            "rows_matched_by": self.rows_matched_by,
            "rows_matched_on": list(self.rows_matched_on),
            "missing": [[node, side] for node, side in self.missing],
            "lines": [one.to_dict() for one in self.lines],
            "verdict": self.verdict,
        }


def _nodes_by_id(artifact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return the artifact's nodes, keyed by id."""
    nodes = artifact.get("nodes") or []
    return {str(node["id"]): node for node in nodes}


def _required(
    artifact: Mapping[str, Any],
    scope: Scope,
) -> tuple[str, ...]:
    """Return the node ids this scope says both files ought to carry.

    Under ``final-schema`` the artifact is the authority: the model's own
    schema is a property of the graph, not of what either file happened to
    be written with. Under ``every-node`` all value-bearing definitions are
    required, including historical definitions and extracted states.
    """
    if scope == "final-schema":
        return tuple(
            sorted(
                node_id
                for node_id, node in _nodes_by_id(artifact).items()
                if node.get("in_final_schema")
            )
        )
    return tuple(
        sorted(
            node_id
            for node_id, node in _nodes_by_id(artifact).items()
            if node.get("kind") in VALUE_BEARING
        )
    )


def _refuse_unbound(artifact: Mapping[str, Any], *manifests: ResultManifest) -> str:
    """Return the artifact's fingerprint, or say which manifest is not of it."""
    stated = str(artifact.get("graph_fingerprint") or "")
    for manifest in manifests:
        if manifest.graph_fingerprint != stated:
            message = (
                f"The results are not of this artifact: the artifact states "
                f"{stated} and a result file states "
                f"{manifest.graph_fingerprint}. Comparing them would put one "
                "model's numbers under another model's node names. Export the "
                "artifact the results were produced from, or produce the "
                "results again from this one. If the two results are of two "
                "versions of a model, gspio diff on the two versions' audit "
                "files with --results and the two results files, earlier "
                "first, says which numbers moved between them and by how much."
            )
            raise ValueError(message)
    return stated


class _Alignment(NamedTuple):
    """Which row of each file is which policy, and how that was decided."""

    before: list[int]
    after: list[int]
    by: Literal["identity", "position"]
    on: tuple[str, ...]


# The move a refusal to pair rows names, in the command's own spelling.
_NAME_THE_IDENTITY = (
    "Name the column that identifies a policy with --policy-id-column "
    "<column> (once more for a scenario column), or produce both files again "
    "with a gspio command that records it."
)


def _alignment(
    before: pl.DataFrame,
    after: pl.DataFrame,
    before_manifest: ResultManifest,
    after_manifest: ResultManifest,
    told: Sequence[str] | None = None,
) -> _Alignment:
    """Return which row of each file is which policy, and how that was decided.

    **By identity** where the caller names the columns, or where both
    manifests record the same ones: a model is free to hand its rows back in
    another order, and a book is free to arrive in one, so the identity is
    what says which row is which policy.

    **By position only where the order is shown**, because a pairing by
    position that is wrong still produces a verdict -- the same policies in
    another order "disagree", and two books whose values happen to line up
    "agree". The order is shown where the column one side records as its
    identity holds the same values in the same order on the other, or where
    the two sides read one book: ``inputs_digest`` is taken over the rows in
    the book's order, and both files are results of one artifact. Anything
    else is refused, naming the columns to pair on. The counts are checked
    first, for every route.
    """
    if before.height != after.height:
        message = (
            f"The before results hold {before.height} rows and the after "
            f"results hold {after.height}, so no pairing of their rows can "
            "put every policy beside itself. Compare two runs over the same "
            "policies; their rows are then paired on the identity the files "
            "record, or on the columns --policy-id-column names (once more "
            "for a scenario column)."
        )
        raise ValueError(message)

    if told:
        return _paired_by(before, after, tuple(told), "named on the command line")
    recorded = before_manifest.row_identity
    if recorded is not None and recorded == after_manifest.row_identity:
        return _paired_by(before, after, recorded, "the manifests record")
    return _shown_in_one_order(before, after, before_manifest, after_manifest)


def _paired_by(
    before: pl.DataFrame, after: pl.DataFrame, identity: tuple[str, ...], said: str
) -> _Alignment:
    """Pair the rows on the identity columns, or say why they cannot be."""
    for side, frame in (("before", before), ("after", after)):
        absent = [column for column in identity if column not in frame.columns]
        if absent:
            message = (
                f"The {side} results carry no {_listed(absent)} column, which "
                f"is the row identity {said}, so its rows cannot be paired "
                f"with the other file's. Its columns are {_listed(frame.columns)}."
                f" {_NAME_THE_IDENTITY}"
            )
            raise ValueError(message)

    left = _keys(before, identity)
    right = _keys(after, identity)
    shown = _shown(identity)
    _refuse_duplicates(left, shown, "before")
    _refuse_duplicates(right, shown, "after")

    where = {value: index for index, value in enumerate(right)}
    # Built once. Rebuilt inside the comprehension it would be one pass over
    # the whole book per row of it, which is a book-sized cost on the one
    # path a comparison of a real run always takes.
    left_set = set(left)
    absent_keys = [value for value in left if value not in where]
    extra = [value for value in right if value not in left_set]
    if absent_keys or extra:
        message = (
            f"The two files hold different policies under {shown}: "
            f"{_listed(map(_key_text, absent_keys)) or 'none'} in the before "
            "results and not the after ones, "
            f"{_listed(map(_key_text, extra)) or 'none'} the other way round. A "
            "comparison of two books is a comparison of two models' inputs "
            "rather than of two engines."
        )
        raise ValueError(message)

    order = [where[value] for value in left]
    return _Alignment(list(range(before.height)), order, "identity", identity)


def _shown_in_one_order(
    before: pl.DataFrame,
    after: pl.DataFrame,
    before_manifest: ResultManifest,
    after_manifest: ResultManifest,
) -> _Alignment:
    """Pair by position where the two files show one order, or refuse.

    Reached where the manifests do not record one identity between them: a
    file written before a results file recorded its row identity, an engine's
    file whose book named no policy column, or two files recording two
    different identities.
    """
    position = list(range(before.height))
    recorded = [
        identity
        for identity in (before_manifest.row_identity, after_manifest.row_identity)
        if identity is not None
    ]
    if len(recorded) == 2:  # noqa: PLR2004 -- one per side
        message = (
            f"The before results record their rows by {_shown(recorded[0])} and "
            f"the after results by {_shown(recorded[1])}, so neither says which "
            f"of the other's rows is which policy. {_NAME_THE_IDENTITY}"
        )
        raise ValueError(message)

    for identity in recorded:
        carried = all(
            column in before.columns and column in after.columns for column in identity
        )
        if not carried:
            continue
        if before.select(identity).equals(after.select(identity)):
            return _Alignment(position, list(position), "position", identity)
        moved = _first_moved(before, after, identity)
        message = (
            f"One file records {_shown(identity)} as its row identity and the "
            f"other records none, and the two hold {_shown(identity)} in "
            f"different orders ({moved}). Pairing the rows by position would "
            "compare one policy's results with another's. Pair them by it with "
            f"{_flags(identity)}."
        )
        raise ValueError(message)

    if before_manifest.inputs_digest == after_manifest.inputs_digest:
        return _Alignment(position, list(position), "position", ())

    message = (
        "Neither file records which columns name its rows, and the two read "
        "different books, so nothing shows that row 1 of one is row 1 of the "
        "other. Pairing them by position would compare one policy's results "
        f"with another's wherever the two books' orders part. {_NAME_THE_IDENTITY}"
    )
    raise ValueError(message)


def _keys(frame: pl.DataFrame, identity: tuple[str, ...]) -> list[object]:
    """Return each row's identity: the value of one column, or a tuple of several."""
    if len(identity) == 1:
        return frame.get_column(identity[0]).to_list()
    return list(
        zip(*(frame.get_column(one).to_list() for one in identity), strict=True)
    )


def _key_text(key: object) -> str:
    """Return one row's identity as a refusal names it."""
    if isinstance(key, tuple):
        return "(" + ", ".join(str(one) for one in key) + ")"
    return str(key)


def _shown(identity: Sequence[str]) -> str:
    """Return the identity columns as a sentence names them."""
    return " and ".join(repr(column) for column in identity)


def _flags(identity: Sequence[str]) -> str:
    """Return the command-line options that name these identity columns."""
    return " ".join(f"--policy-id-column {column}" for column in identity)


def _first_moved(
    before: pl.DataFrame, after: pl.DataFrame, identity: tuple[str, ...]
) -> str:
    """Return the first row whose identity parts, as a refusal states it."""
    left = _keys(before, identity)
    right = _keys(after, identity)
    for row, (one, other) in enumerate(zip(left, right, strict=True)):
        if one != other:
            return (
                f"row {row + 1} is {_key_text(one)} in one and "
                f"{_key_text(other)} in the other"
            )
    return "their types differ"  # pragma: no cover -- equal keys, unequal frames


def _refuse_duplicates(values: Sequence[object], column: str, side: str) -> None:
    """Refuse a side whose identity names one policy twice."""
    seen: set[object] = set()
    repeated: list[object] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    if repeated:
        message = (
            f"The {side} results carry {_listed(map(_key_text, repeated))} more "
            f"than once under {column}, so a policy's row cannot be told from "
            "another policy's. Compare results whose identity names each "
            "policy once -- on a scenario run, the policy column and the "
            "scenario column together, each named with --policy-id-column."
        )
        raise ValueError(message)


def _listed(values: Iterable[object], limit: int = 5) -> str:
    """Return a few values as text, so a message names them rather than counts."""
    shown = [str(value) for value in values]
    if not shown:
        return ""
    if len(shown) <= limit:
        return ", ".join(shown)
    return ", ".join(shown[:limit]) + f" and {len(shown) - limit} more"


def _base_of(dtype: str) -> str:
    """Return the scalar at the bottom of a possibly nested list type."""
    base = dtype
    while base.startswith("list[") and base.endswith("]"):
        base = base[len("list[") : -1]
    return base


def _logical_dtype(
    node: Mapping[str, Any],
    artifact: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    """Resolve §16's identity-preserving unknown state through its declaration."""
    dtype = str(node.get("dtype"))
    if dtype != "unknown" or node.get("kind") != "state":
        return dtype
    facet = (artifact.get("facets") or {}).get("gaspatchio_rollforward_ir", {})
    schema = "https://gaspatchio.dev/schemas/facets/gaspatchio_rollforward_ir-v0-preview.1.json"
    if facet.get("_schemaURL") != schema:
        return "unknown"
    owners = []
    for owner in nodes.values():
        if owner.get("kind") != "rollforward":
            continue
        fingerprint = (owner.get("expr") or {}).get("attrs", {}).get("fingerprint")
        body = facet.get("compilations", {}).get(fingerprint)
        if isinstance(body, dict) and any(
            node["id"] == f"state:{state.get('name')}@eop"
            for state in body.get("states", [])
        ):
            owners.append((owner, body))
    if (
        len(owners) == 1
        and _portable_state_types(owners[0][0], owners[0][1], nodes)
        and _portable_state_schedule(owners[0][1], artifact)
    ):
        return "list[f64]"
    return "unknown"


def _portable_state_schedule(
    body: Mapping[str, Any], artifact: Mapping[str, Any]
) -> bool:
    """Require the schedule form that gives §16.1's state array its periods."""
    entries = [
        entry
        for entry in artifact.get("assumptions", [])
        if entry.get("kind") == "schedule"
        and entry.get("fingerprint") == body.get("schedule")
    ]
    if len(entries) != 1:
        return False
    payload = entries[0].get("payload", {})
    expected = {
        "kind": "from_calendar_grid",
        "frequency": "1M",
        "calendar": "NullCalendar",
        "convention": "Unadjusted",
        "day_count": "OneTwelfth",
        "anchor": "month_end",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return False
    count = payload.get("n_periods")
    try:
        start = datetime.date.fromisoformat(payload.get("start_date", ""))
    except (TypeError, ValueError):
        return False
    return (
        type(count) is int
        and count >= 0
        and start.day == calendar.monthrange(start.year, start.month)[1]
    )


def _portable_state_types(
    owner: Mapping[str, Any],
    body: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Recognize the closed §16.1 amount types; never infer from result metadata."""
    fixed = {
        "points": ["bop", "eop"],
        "engine_binding": "portable",
        "batch_axes": ["policy"],
        "track_increments": False,
        "lapse_when_all_non_positive": [],
        "contract_boundary": None,
    }
    if set(body) != set(fixed) | {"states", "increments", "schedule"} or any(
        body.get(key) != expected for key, expected in fixed.items()
    ):
        return False
    reads = owner.get("reads", [])
    if any(read not in nodes for read in reads):
        return False
    columns = [nodes[read] for read in reads if nodes[read].get("column") is not None]
    bound = {read["column"]: read.get("dtype") for read in columns}
    if len(bound) != len(columns):
        return False
    states = body["states"]
    names = [state.get("name") for state in states]
    if (
        not names
        or not all(isinstance(name, str) and name for name in names)
        or len(set(names)) != len(names)
    ):
        return False
    if any(
        state.get("init", {}).get("op") != "col"
        or bound.get(state["init"].get("name")) != "f64"
        for state in states
    ):
        return False
    return all(
        _portable_increment_types(increment, bound, names)
        for increment in body["increments"]
    )


def _portable_increment_types(
    increment: Mapping[str, Any],
    bound: Mapping[str, Any],
    names: Sequence[str],
) -> bool:
    """Keep unsupported updates from assigning a guessed type to a state."""
    arities = {
        "Add": 1,
        "Subtract": 1,
        "Charge": 2,
        "Grow": 2,
        "Floor": 1,
        "Ratchet": 3,
    }
    operation = increment.get("operation")
    operands = increment.get("operands", [])
    target = increment.get("target")
    if (
        operation not in arities
        or len(operands) != arities[operation]
        or target not in {f"{name}@eop" for name in names}
    ):
        return False
    if operation in {"Charge", "Grow", "Floor", "Ratchet"} and operands[-1] != {
        "op": "state",
        "name": target,
    }:
        return False
    if (
        operation == "Ratchet" and operands[0].get("op") != "state"
    ) or not _portable_increment_settings(increment):
        return False
    for index, operand in enumerate(operands):
        gate = operation == "Ratchet" and index == 1
        if operand.get("op") == "col":
            admitted = {"bool", "list[bool]"} if gate else {"f64", "list[f64]"}
            if bound.get(operand.get("name")) not in admitted:
                return False
        elif (
            operand.get("op") != "state"
            or gate
            or operand.get("name")
            not in {f"{name}@{point}" for name in names for point in ("bop", "eop")}
        ):
            return False
    return True


def _portable_increment_settings(increment: Mapping[str, Any]) -> bool:
    """Recognize settings that preserve §16.1's amount domain."""
    operation = increment.get("operation")
    settings = increment.get("settings")
    ordinary_settings = {
        "Charge": {"round_charge": None},
        "Grow": {"round_charge": None},
        "Add": {},
        "Subtract": {},
        "Ratchet": {},
    }
    if operation in ordinary_settings:
        return settings == ordinary_settings[operation]
    return (
        operation == "Floor"
        and isinstance(settings, dict)
        and set(settings) == {"value"}
        and isinstance(settings["value"], float)
        and math.isfinite(settings["value"])
    )


@dataclass(frozen=True, slots=True)
class _Side:
    """One file, what it says it is, and which row of it is which policy.

    ``order`` is the file's row for each policy in the pairing, or None where
    the file's own order is the pairing. ``magnitudes`` keeps each column's
    per-policy magnitude once it is read, because one column is a read of
    many lines and its magnitude does not change between them.
    """

    frame: pl.DataFrame
    manifest: ResultManifest
    order: pl.Series | None
    magnitudes: dict[str, pl.Series] = field(default_factory=dict)

    def validate(
        self,
        nodes: Mapping[str, Mapping[str, Any]],
        side: str,
        artifact: Mapping[str, Any],
    ) -> None:
        """Check metadata and physical carriers against the artifact's meanings."""
        for node_id in self.manifest.columns.keys() | self.manifest.dtypes.keys():
            node = nodes.get(node_id)
            if node is None:
                message = f"The {side} manifest names absent artifact node {node_id}."
                raise ValueError(message)
            dtype = _logical_dtype(node, artifact, nodes)
            declared = self.manifest.dtypes.get(node_id)
            shape = "list" if dtype.startswith("list[") else "scalar"
            # Running states have no frame column from which the exporter can
            # state a shape. The same closed declaration that proves their
            # logical dtype above also proves its list shape; do not ask the
            # producer to change an identity-preserving unknown to compare it.
            derived_state = (
                node.get("kind") == "state"
                and node.get("dtype") == "unknown"
                and dtype != "unknown"
            )
            shape_agrees = node.get("shape") == shape or (
                derived_state and node.get("shape") == "unknown"
            )
            if declared != node.get("dtype") or not shape_agrees or dtype == "unknown":
                message = (
                    f"The {side} manifest for {node_id} states {declared}; "
                    f"the artifact requires {dtype} with shape {node.get('shape')}. "
                    "Produce the results again."
                )
                raise ValueError(message)
            column = self.column_for(node_id)
            if column is None:
                continue
            values = self.frame.get_column(column)
            physical = neutral_dtype(values.dtype, column=column, values=values)
            if physical != dtype:
                message = (
                    f"The {side} physical column for {node_id} carries {physical}; "
                    f"the artifact requires {dtype}. Produce the results again."
                )
                raise ValueError(message)

    def column_for(self, node_id: str) -> str | None:
        """Return the column carrying that node here, or None where it is absent."""
        name = self.manifest.columns.get(node_id)
        if name is None or name not in self.frame.columns:
            return None
        return name

    def values_for(self, node_id: str) -> pl.Series | None:
        """Return that node's column in the pairing's order, or None where absent."""
        name = self.column_for(node_id)
        if name is None:
            return None
        values = self.frame.get_column(name)
        return values if self.order is None else values.gather(self.order)

    def magnitude_for(self, node_id: str) -> pl.Series | None:
        """Return that node's per-policy magnitude in the pairing's order."""
        name = self.column_for(node_id)
        if name is None:
            return None
        kept = self.magnitudes.get(name)
        if kept is None:
            kept = policy_magnitude(self.frame.get_column(name))
            if self.order is not None:
                kept = kept.gather(self.order)
            self.magnitudes[name] = kept
        return kept


def _in_order(rows: Sequence[int]) -> pl.Series | None:
    """Return a pairing's rows to gather by; None where they are the file's own."""
    if all(row == index for index, row in enumerate(rows)):
        return None
    return pl.Series("row", rows, dtype=pl.Int64)


def _read_floor(
    node: Mapping[str, Any], before: _Side, after: _Side, rows: int
) -> tuple[pl.Series, tuple[str, ...]]:
    """Return each policy's largest read magnitude, and the reads not in reach.

    A read absent from either file is out of the scale for both, because a
    magnitude one side can see and the other cannot is not a magnitude the
    comparison may lean on.
    """
    left: list[pl.Series] = []
    right: list[pl.Series] = []
    absent: list[str] = []
    for read in node.get("reads") or []:
        name = str(read)
        one = before.magnitude_for(name)
        other = after.magnitude_for(name)
        if one is None or other is None:
            absent.append(name)
            continue
        left.append(one)
        right.append(other)
    return read_scale(left, right, rows), tuple(absent)


def _verdict_of(
    reading: LineReading, reads_absent: tuple[str, ...]
) -> tuple[Verdict, float | None]:
    """Return one line's verdict, and the bound an indeterminate one prints."""
    if reading.parted:
        return "disagree", None
    if reading.max_ratio is None or reading.max_ratio <= TOLERANCE:
        return "agree", None
    if reads_absent:
        # The scale in hand is a floor on the true one, so the difference
        # might yet pass. What the absent reads would have to supply is the
        # one number that says how far off the question is from decided.
        return "indeterminate", reading.max_abs / TOLERANCE
    return "disagree", None


def compare_results(  # noqa: PLR0913 -- the artifact, two files, their two manifests and the identity a caller names
    artifact: dict[str, object],
    before: pl.DataFrame,
    after: pl.DataFrame,
    *,
    before_manifest: ResultManifest,
    after_manifest: ResultManifest,
    row_identity: Sequence[str] | None = None,
) -> CompareReport:
    """Compare two runs of one artifact and say whether they agree.

    Args:
        artifact: The executable document both files are results of.
        before: The earlier results, columns as its manifest names them.
        after: The later results.
        before_manifest: What the earlier file is.
        after_manifest: What the later file is.
        row_identity: The columns to pair the two files' rows on, where the
            caller names them; they decide over whatever the manifests
            record. None pairs on the identity both manifests record, and
            by position only where the two files show one order.

    Returns:
        The comparison, line by line, with its verdict.

    Raises:
        ValueError: A manifest not bound to this artifact; two scopes; row
            counts that differ; an identity column naming a policy twice;
            two files holding different policies; rows that neither an
            identity nor a shown order can pair.

    """
    fingerprint = _refuse_unbound(artifact, before_manifest, after_manifest)
    if before_manifest.scope != after_manifest.scope:
        message = (
            f"The two results files were written under different scopes: "
            f"{before_manifest.scope} and {after_manifest.scope}. The scale a "
            "line is judged against depends on which values the file carries, "
            "so the two are not comparable. Produce both sides with "
            "--every-node, or both without it."
        )
        raise ValueError(message)
    scope = before_manifest.scope

    before_order, after_order, matched_by, matched_on = _alignment(
        before, after, before_manifest, after_manifest, row_identity
    )
    left_side = _Side(before, before_manifest, _in_order(before_order))
    right_side = _Side(after, after_manifest, _in_order(after_order))
    nodes = _nodes_by_id(artifact)
    left_side.validate(nodes, "before", artifact)
    right_side.validate(nodes, "after", artifact)
    required = _required(artifact, scope)

    missing: list[tuple[str, Literal["before", "after"]]] = []
    lines: list[LineComparison] = []
    for node_id in required:
        before_values = left_side.values_for(node_id)
        after_values = right_side.values_for(node_id)
        if before_values is None:
            missing.append((node_id, "before"))
        if after_values is None:
            missing.append((node_id, "after"))
        if before_values is None or after_values is None:
            continue

        node = nodes.get(node_id, {})
        dtype = _logical_dtype(node, artifact, nodes)
        exact = _base_of(dtype) in _EXACT_SCALARS
        reads_absent: tuple[str, ...] = ()
        exact_class: str | None
        if exact:
            reading = read_line(before_values, after_values, exact=True)
            exact_class = dtype
        else:
            floor, reads_absent = _read_floor(
                node, left_side, right_side, before_values.len()
            )
            reading = read_line(
                before_values, after_values, exact=False, read_scale=floor
            )
            exact_class = reading.parted_on
        verdict, bound = _verdict_of(reading, reads_absent)
        lines.append(
            LineComparison(
                node_id=node_id,
                # A line the exact classes decided reports no magnitude: see
                # the field's own note. The reading still carries one,
                # because an indeterminate line's lower bound is computed
                # from it, and that path is only ever a float line's.
                max_abs=None if exact_class is not None else reading.max_abs,
                max_ratio=reading.max_ratio,
                scale=reading.scale,
                reads_absent=reads_absent,
                verdict=verdict,
                lower_bound=bound,
                strict_floor=reading.strict and not reading.parted,
                exact_class=exact_class,
            )
        )

    return CompareReport(
        report_version=REPORT_VERSION,
        artifact_fingerprint=fingerprint,
        document_digest=_seal_of(artifact),
        scope=scope,
        before=before_manifest,
        after=after_manifest,
        same_inputs=before_manifest.inputs_digest == after_manifest.inputs_digest,
        rows_matched_by=matched_by,
        rows_matched_on=matched_on,
        missing=tuple(sorted(missing)),
        lines=tuple(lines),
        verdict=_overall(lines, tuple(missing)),
    )


def _seal_of(artifact: Mapping[str, Any]) -> str | None:
    """Return the document's seal as it states it, or None where it states none."""
    seal = artifact.get("document_digest")
    return seal if isinstance(seal, str) else None


def _overall(
    lines: Sequence[LineComparison],
    missing: Sequence[tuple[str, str]],
) -> Verdict:
    """Return the report's own verdict from its lines and what is absent.

    Never agreement with a required result missing, and never agreement over
    nothing: a comparison that compared no line has not found the two engines
    to agree, it has found nothing.
    """
    if any(one.verdict == "disagree" for one in lines):
        return "disagree"
    if missing or not lines:
        return "indeterminate"
    if any(one.verdict == "indeterminate" for one in lines):
        return "indeterminate"
    return "agree"
