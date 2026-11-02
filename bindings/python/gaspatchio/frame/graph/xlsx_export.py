# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One policy of an audit record, laid out as a spreadsheet a reviewer opens.

A reviewer who does not read Python still has to follow a number: what the
reserve was at period 84, what it was rolled from, which line of the model
wrote it. The audit record holds every one of those facts, and this module
lays them out as a workbook -- the policy's timeline with periods as rows and
the model's columns in calculation order, its single values, every node, every
edge with the periods it reads, and every assumption base -- so the record can
be read in the tool the reviewer already has.

**Every cell holds the record's own value.** A number is written as the
shortest decimal that reads back to the double the record carries, which is
the text the record itself writes. The common Python spreadsheet writers keep
sixteen significant digits, and about a quarter of all doubles need a
seventeenth, so a sheet written through one of them shows ``0.3`` where the
record holds ``0.30000000000000004``. This writer is small and owns its OOXML
for that reason and no other.

**Nothing recalculates.** No cell holds a spreadsheet formula. The formula
row of the timeline is the model's own line as text, quoted from the record,
because a recalculating sheet is a second implementation of the model that
nobody reconciled -- and its answers would sit beside the record's under the
same column names.

**The bytes are a function of the record.** The archive is stored rather than
compressed, every member is written in one order with one timestamp, and the
workbook's created date is the record's own ``created_at``: one record lays
out to one file, byte for byte, on any machine. Compression would make the
bytes depend on which zlib the interpreter was built with.
"""

from __future__ import annotations

import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .verify import _audit_document, _shaped_by, verify_artifact

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from .verify import Check

__all__ = ["render_xlsx"]

# Excel's own ceilings. A sheet past either is not a sheet Excel opens, so the
# layout refuses rather than writes one that only looks finished.
_MAX_ROWS: Final = 1_048_576
_MAX_COLUMNS: Final = 16_384
# The longest text a cell holds. Past it Excel calls the file damaged.
_MAX_CELL_TEXT: Final = 32_767
# The largest whole number a double holds exactly. Excel stores every number
# as a double, so a wider integer is written as its digits in text rather
# than as a number Excel would round.
_EXACT_INTEGER: Final = 2**53

# The cell styles, by their index in the stylesheet below.
_PLAIN: Final = 0
_HEADER: Final = 1
_ANNOTATION: Final = 2

# One timestamp for every member of the archive: the earliest a zip can state.
_ZIP_TIME: Final = (1980, 1, 1, 0, 0, 0)

_MAIN_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_SHEET_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)

# Characters XML 1.0 cannot carry at all, and the escape OOXML defines for
# them. An underscore that already reads as an escape is escaped itself, so a
# model's text that happens to spell one comes back as it was written. A
# carriage return is legal XML but a parser reads a bare one as a line feed,
# so it travels as a character reference, which every XML reader keeps.
_UNWRITABLE: Final = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]"
)
_LOOKS_ESCAPED: Final = re.compile(r"_(x[0-9A-Fa-f]{4}_)")
# What a sheet name may not hold.
_NOT_IN_A_SHEET_NAME: Final = re.compile(r"[\[\]:*?/\\]")
_SHEET_NAME_LENGTH: Final = 31

_TEXT_CUT: Final = (
    " ... [cut at Excel's 32,767-character limit; the record holds the whole text]"
)

_SHEETS_EXPLAINED: Final = (
    (
        "Timeline",
        (
            "One row per projection period and one column per per-period node, in "
            "the order the model calculated them. Row 1 names the node, row 2 is "
            "its formula as the model wrote it, row 3 its tier. A blank formula is "
            "a column that arrived with the data, or one the record gives no "
            "formula for: the Nodes sheet says which."
        ),
    ),
    (
        "Scalars",
        "Every node holding one value per policy: its formula, its tier and its value.",
    ),
    (
        "Nodes",
        (
            "Every node the record carries, history included: what it is, what it "
            "reads, its fingerprint and the line of the model that wrote it."
        ),
    ),
    (
        "Edges",
        (
            "Every read: which node read which, whether the value flows into the "
            "answer, and the periods it reads. offset is a fixed distance from the "
            "period being computed, negative before it; periods from/to bound an "
            "aggregation's run, first and last being the policy's own first and "
            "last period; position is a literal list position."
        ),
    ),
    (
        "Assumptions",
        (
            "Every assumption base the model read: its fingerprint, the file it "
            "was read from and how it was reshaped on the way in."
        ),
    ),
)

_READING_THE_NUMBERS: Final = (
    (
        "Precision",
        (
            "Every number is the double the record holds, written as the shortest "
            "decimal that reads back to it -- up to 17 significant digits. Excel "
            "shows at most 15, so a cell can display fewer digits than it holds; "
            "the digits are in the file."
        ),
    ),
    (
        "Not a number, infinity",
        (
            "Written as the record writes them, as the text NaN, Infinity or "
            "-Infinity: a spreadsheet number has no form for either."
        ),
    ),
    (
        "Large whole numbers",
        (
            "A whole number past 2^53 (9,007,199,254,740,992) is written as its "
            "digits in text, because Excel would round it as a number."
        ),
    ),
    (
        "Dates and text",
        (
            "A date is the record's ISO text, 2025-01-01, never a date serial. A "
            "value holding a list of its own is written as its JSON text."
        ),
    ),
    (
        "Blank cells",
        (
            "A blank value is a null in the record, or a period past the end of "
            "the policy's own timeline."
        ),
    ),
    (
        "Nothing recalculates",
        (
            "No cell holds a spreadsheet formula. A formula shown here is the "
            "model's line as text; the values beside it are the run's."
        ),
    ),
)


class _NotOnTheAxisError(ValueError):
    """The policy asked for is not one entry of the record's policy axis.

    A ``ValueError`` like every refusal here, and its own type so the command
    can say it with the status it keeps for a selection that named nothing.
    """


@dataclass(frozen=True, slots=True)
class _Cell:
    """One cell's content and style, before it is given a reference."""

    value: object
    style: int = _PLAIN


@dataclass(frozen=True, slots=True)
class _Sheet:
    """One worksheet: its name, its rows, its column widths and its frozen panes."""

    name: str
    rows: list[list[_Cell | None]]
    widths: tuple[float, ...]
    frozen_rows: int
    frozen_columns: int = 0


@dataclass(frozen=True, slots=True)
class _Entry:
    """One entry of the policy axis being laid out, and where its values sit."""

    position: int
    entry: Mapping[str, Any]
    label: str
    sheet_name: str


def render_xlsx(
    artifact: dict[str, Any] | str | Path,
    *,
    policy: str | None = None,
    results: Path | str | None = None,
) -> bytes:
    """Return a workbook laying the record's policies out, every cell exact.

    The audit record a model export writes holds, for each policy it sampled,
    every value every column held at every period, at full precision. This
    lays that out as an ``.xlsx`` workbook a reviewer opens in Excel or
    LibreOffice without Python: the timeline, the single values, the nodes,
    the edges and the assumption bases, under a README naming the record by
    its digests. Every number is the record's own double, written as the
    shortest decimal that reads back to it, and nothing in the workbook
    recalculates.

    Six sheets: **README** (the record's ``document_digest``,
    ``graph_fingerprint``, ``formulas_fingerprint``, ``source_sha``, the book's
    digest, the policy and why it is in the record, the versions that
    produced it), **Timeline** (periods as rows, the per-period columns in
    calculation order, each headed by its node, its formula and its tier),
    **Scalars**, **Nodes**, **Edges** (with each read's offset and period
    window) and **Assumptions** (each base's fingerprint, ``source_file``
    and ``shaped_by``). A record carrying several policies lays each out on
    a Timeline sheet of its own, named for the policy, and gives each a
    value column on Scalars.

    The workbook's bytes are a function of the record alone: the same record
    lays out to the same file on any machine, and its created date is the
    record's ``created_at``.

    Args:
        artifact: The audit record, as the parsed document, the text of it,
            or the path of the stored file.
        policy: The one policy to lay out, by the id the record names it
            under. None lays out every entry of the record's policy axis.
        results: The results file the run wrote, to check against the record
            before laying it out. The README states whether it is the file
            the record names; the values are always the record's own.

    Returns:
        The workbook, as the bytes of an ``.xlsx`` file.

    Raises:
        ValueError: If ``artifact`` is not a calculation-graph record, if its
            seal does not hold -- it has changed since it was written, so the
            digests the README would quote are not the content's -- if
            ``policy`` is not on its axis or names more than one entry, or if
            a sheet would pass Excel's own limits of 1,048,576 rows or 16,384
            columns.
        OSError: If ``results`` cannot be read.

    Examples:
        Lay a one-policy record out and read a cell back -- the double the
        record holds, digit for digit:

        >>> import io
        >>> import json
        >>> import zipfile
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import GraphExporter, render_xlsx
        >>> af = ActuarialFrame(pl.DataFrame({"premium": [0.1]}))
        >>> af.loaded = af.premium + 0.2
        >>> record = GraphExporter(af).export(af.collect())
        >>> workbook = render_xlsx(record)
        >>> names = zipfile.ZipFile(io.BytesIO(workbook)).namelist()
        >>> "xl/worksheets/sheet3.xml" in names
        True
        >>> scalars = zipfile.ZipFile(io.BytesIO(workbook)).read(
        ...     "xl/worksheets/sheet3.xml"
        ... )
        >>> b"<v>0.30000000000000004</v>" in scalars
        True

    """
    document = _audit_document(artifact)
    report = verify_artifact(document, results=results)
    checks = {check.name: check for check in report.checks}
    seal = checks["seal"]
    if seal.outcome == "disagree":
        msg = (
            "The record's seal does not hold, so a workbook would quote digests "
            f"its content no longer carries: {seal.detail} Lay out the file the "
            "export wrote, or export the model again."
        )
        raise ValueError(msg)

    entries = _entries_to_lay_out(document, policy)
    nodes = [node for node in document.get("nodes", []) if isinstance(node, dict)]
    width = len(_axis(document))
    stated = [seal, checks["results"], checks["results_manifest"]]
    sheets = [
        _readme(document, entries, stated),
        *(_timeline(nodes, entry, width) for entry in entries),
        *([_scalars(nodes, entries, width)] if entries else []),
        _nodes_sheet(nodes),
        _edges_sheet(document, nodes),
        _assumptions_sheet(document),
    ]
    for sheet in sheets:
        _refuse_past_excel(sheet)
    created = document.get("created_at")
    return _package(sheets, created if isinstance(created, str) else None)


# --- which policies ----------------------------------------------------------


def _axis(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the record's policy axis, its entries in their written order."""
    axis = document.get("policies")
    return (
        [entry for entry in axis if isinstance(entry, dict)]
        if isinstance(axis, list)
        else []
    )


def _entries_to_lay_out(
    document: Mapping[str, Any], policy: str | None
) -> list[_Entry]:
    """Return the axis entries the workbook lays out, each with its sheet's name."""
    axis = _axis(document)
    chosen = list(enumerate(axis))
    if policy is not None:
        chosen = [
            (at, entry) for at, entry in chosen if entry.get("policy_id") == policy
        ]
        if not chosen:
            msg = _not_on_the_axis(policy, axis)
            raise _NotOnTheAxisError(msg)
        if len(chosen) > 1:
            cuts = "; ".join(f"filter {entry.get('filter')!r}" for _, entry in chosen)
            msg = (
                f"Policy {policy!r} is on the record's axis {len(chosen)} times "
                f"({cuts}), so the name alone does not say which to lay out. "
                "Leave the policy out to lay out every entry, each on a Timeline "
                "sheet of its own."
            )
            raise _NotOnTheAxisError(msg)
    labels = [_label(entry, at) for at, entry in chosen]
    if len(chosen) == 1:
        names = ["Timeline"]
    else:
        names = _unique_sheet_names(f"Timeline {label}" for label in labels)
    return [
        _Entry(at, entry, label, name)
        for (at, entry), label, name in zip(chosen, labels, names, strict=True)
    ]


def _not_on_the_axis(policy: str, axis: Sequence[Mapping[str, Any]]) -> str:
    """Return the refusal for a policy the record carries no values for."""
    if not axis:
        return (
            f"The record carries no values, so there is no policy {policy!r} to "
            "lay out: it was exported without the frame its run produced. Export "
            "it with values -- gspio calc-graph does -- and lay that out."
        )
    named = ", ".join(repr(_label(entry, at)) for at, entry in enumerate(axis))
    return (
        f"Policy {policy!r} is not on the record's axis, which carries {named}. "
        "The record holds values only for the policies its export sampled: "
        f"export again with gspio calc-graph --policies id:{policy}, and lay "
        "that record out."
    )


def _label(entry: Mapping[str, Any], position: int) -> str:
    """Return what a reader calls one axis entry: its policy, or its fold.

    A policy the producer could not identify is called by its place on the
    axis, which its ``why`` sentence then explains.
    """
    policy_id = entry.get("policy_id")
    if policy_id is not None:
        return str(policy_id)
    aggregation = entry.get("aggregation")
    return str(aggregation) if aggregation is not None else f"entry {position + 1}"


def _unique_sheet_names(wanted: Iterable[str]) -> list[str]:
    """Return each name made legal for a sheet, and unique as Excel compares them."""
    taken: set[str] = {
        "readme",
        "scalars",
        "nodes",
        "edges",
        "assumptions",
    }
    names: list[str] = []
    for name in wanted:
        cleaned = _NOT_IN_A_SHEET_NAME.sub("_", name).strip("'") or "Timeline"
        candidate = cleaned[:_SHEET_NAME_LENGTH]
        count = 1
        while candidate.lower() in taken:
            count += 1
            suffix = f" ({count})"
            candidate = cleaned[: _SHEET_NAME_LENGTH - len(suffix)] + suffix
        taken.add(candidate.lower())
        names.append(candidate)
    return names


# --- the sheets ----------------------------------------------------------------


def _readme(
    document: Mapping[str, Any],
    entries: Sequence[_Entry],
    checks: Sequence[Check],
) -> _Sheet:
    """Return the README: which record, which policy, how to read the rest."""
    model = _member(document, "model")
    producer = _member(document, "producer")
    rows: list[tuple[str, object]] = [
        (
            "What this is",
            (
                "A gaspatchio audit record laid out as values: every number is the "
                "record's own, and nothing here recalculates."
            ),
        ),
        ("document_digest", document.get("document_digest")),
        ("graph_fingerprint", document.get("graph_fingerprint")),
        (
            "formulas_fingerprint",
            document.get("formulas_fingerprint")
            or "not stated: the record was written before the member",
        ),
        ("schema", document.get("schema")),
        ("profile", document.get("profile")),
        ("created_at", document.get("created_at")),
        ("model source", model.get("source_path")),
        ("source_sha", model.get("source_sha")),
        ("git", _git(model.get("git"))),
        *(
            ("module", f"{module.get('path')}  {module.get('fingerprint')}")
            for module in model.get("modules") or ()
            if isinstance(module, dict)
        ),
        ("model points", _stamped(model.get("model_points"), "not named")),
        ("results file", _stamped(model.get("results"), "the run wrote none")),
    ]
    if isinstance(model.get("audit"), dict):
        rows.append(("run record", _stamped(model.get("audit"), "")))
    book = _member(document, "book")
    rows += [
        ("book digest", _text_of(book.get("digest"))),
        (
            "book columns",
            ", ".join(str(column) for column in book.get("columns") or ()),
        ),
        ("producer", f"{producer.get('name')} {producer.get('version')}"),
        *_versions(producer.get("versions")),
    ]
    rows += [
        (f"check: {check.name}", f"{check.outcome}: {check.detail}")
        for check in checks
        if check.outcome != "not_asked"
    ]
    if not entries:
        rows.append(
            (
                "policies",
                (
                    "The record carries no values: it was exported without the frame "
                    "its run produced, so there is no Timeline and no Scalars sheet."
                ),
            )
        )
    for entry in entries:
        rows += [
            (_entry_kind(entry.entry), entry.label),
            ("  why", entry.entry.get("why")),
            ("  filter", entry.entry.get("filter")),
            ("  periods", _periods_text(entry.entry.get("periods"))),
            ("  sheet", entry.sheet_name),
        ]
    rows += list(_SHEETS_EXPLAINED)
    rows += list(_READING_THE_NUMBERS)
    return _Sheet(
        name="README",
        rows=[
            [_Cell("Item", _HEADER), _Cell("Value", _HEADER)],
            *([_Cell(item), _value_cell(value)] for item, value in rows),
        ],
        widths=(26, 120),
        frozen_rows=1,
    )


def _member(holder: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return an object member of a record object, or an empty one where it is not."""
    found = holder.get(key)
    return found if isinstance(found, dict) else {}


def _entry_kind(entry: Mapping[str, Any]) -> str:
    """Return whether an axis entry is a policy or a fold of the book."""
    return "policy" if entry.get("aggregation") is None else "fold of the book"


def _git(git: object) -> str:
    """Return the record's git member in words."""
    if git is None:
        return "no working tree beside the model"
    if isinstance(git, dict) and "commit" in git:
        dirty = " (uncommitted changes)" if git.get("dirty") else ""
        return f"{git.get('commit')}{dirty}"
    if isinstance(git, dict):
        return f"unavailable: {git.get('detail', '')}".rstrip(": ")
    return str(git)


def _stamped(member: object, absent: str) -> str:
    """Return a ``{path, fingerprint}`` member as one line, or why there is none."""
    if not isinstance(member, dict):
        return absent
    return f"{member.get('path')}  {member.get('fingerprint')}"


def _text_of(value: object) -> str:
    """Return a member as text: a string as it is, anything else as its JSON."""
    if value is None or isinstance(value, str):
        return value or ""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _versions(versions: object) -> list[tuple[str, object]]:
    """Return one README row per version the record states, or the one saying none."""
    if not isinstance(versions, dict) or "omitted" in versions:
        return [("versions", _text_of(versions) or "not stated")]
    rows: list[tuple[str, object]] = []
    for key, value in versions.items():
        if key == "imports" and isinstance(value, dict):
            rows += [(f"imports {name}", str(found)) for name, found in value.items()]
            continue
        rows.append((key, _text_of(value)))
    return rows


def _periods_text(periods: object) -> str:
    """Return an entry's periods as a reader reads them."""
    if periods is None:
        return "every period"
    return (
        ", ".join(str(period) for period in periods)
        if isinstance(periods, list)
        else str(periods)
    )


def _sample(node: Mapping[str, Any], entry: _Entry, width: int) -> object:
    """Return a node's value at one axis entry, or None where it holds none there.

    A record carrying one policy writes each sample as the value itself, and
    one carrying several writes an array as long as the axis. An array of any
    other length is enrichment the record does not hold to, and is read as
    no value rather than as some other policy's.
    """
    sample = node.get("value_sample")
    if width <= 1:
        return sample
    if not isinstance(sample, list) or len(sample) != width:
        return None
    return sample[entry.position]


def _per_period(node: Mapping[str, Any]) -> bool:
    """Return whether a node holds one value per period rather than per policy."""
    return node.get("shape") == "list"


def _timeline(nodes: Sequence[Mapping[str, Any]], entry: _Entry, width: int) -> _Sheet:
    """Return one entry's timeline: periods as rows, per-period nodes as columns."""
    columns = [
        node
        for node in nodes
        if _per_period(node) and _sample(node, entry, width) is not None
    ]
    pinned = entry.entry.get("periods")
    runs: list[list[object]] = []
    for node in columns:
        value = _sample(node, entry, width)
        if isinstance(pinned, list) and len(pinned) == 1:
            runs.append([value])
        else:
            runs.append(value if isinstance(value, list) else [value])
    length = max((len(run) for run in runs), default=0)
    labels: list[object] = (
        list(pinned)
        if isinstance(pinned, list) and len(pinned) == length
        else list(range(length))
    )
    rows: list[list[_Cell | None]] = [
        [
            _Cell("period", _HEADER),
            *(_Cell(node.get("id"), _HEADER) for node in columns),
        ],
        [
            _Cell("formula", _ANNOTATION),
            *(_Cell(node.get("formula"), _ANNOTATION) for node in columns),
        ],
        [
            _Cell("tier", _ANNOTATION),
            *(_Cell(node.get("tier"), _ANNOTATION) for node in columns),
        ],
    ]
    rows += [
        [
            _Cell(label),
            *(_value_cell(run[at]) if at < len(run) else None for run in runs),
        ]
        for at, label in enumerate(labels)
    ]
    return _Sheet(
        name=entry.sheet_name,
        rows=rows,
        widths=(8, *(20 for _ in columns)),
        frozen_rows=3,
        frozen_columns=1,
    )


def _scalars(
    nodes: Sequence[Mapping[str, Any]], entries: Sequence[_Entry], width: int
) -> _Sheet:
    """Return every per-policy node, one value column per axis entry."""
    held = [
        node
        for node in nodes
        if not _per_period(node)
        and any(_sample(node, entry, width) is not None for entry in entries)
    ]
    value_headers = (
        ["value"]
        if len(entries) == 1
        else [entry.sheet_name.removeprefix("Timeline ") for entry in entries]
    )
    header = ["node", "formula", "tier", "dtype", *value_headers]
    rows: list[list[_Cell | None]] = [[_Cell(text, _HEADER) for text in header]]
    rows += [
        [
            _Cell(node.get("id")),
            _Cell(node.get("formula")),
            _Cell(node.get("tier")),
            _Cell(node.get("dtype")),
            *(_value_cell(_sample(node, entry, width)) for entry in entries),
        ]
        for node in held
    ]
    return _Sheet(
        name="Scalars",
        rows=rows,
        widths=(30, 60, 14, 12, *(22 for _ in entries)),
        frozen_rows=1,
        frozen_columns=1,
    )


_NODE_MEMBERS: Final = (
    ("id", 30),
    ("column", 24),
    ("version", 8),
    ("kind", 12),
    ("dtype", 12),
    ("shape", 8),
    ("provenance", 14),
    ("formula", 60),
    ("tier", 14),
    ("reads", 40),
    ("reads_assumptions", 24),
    ("in_final_schema", 10),
    ("local_fingerprint", 74),
    ("source_location", 30),
)


def _nodes_sheet(nodes: Sequence[Mapping[str, Any]]) -> _Sheet:
    """Return every node of the record, one row each, in the record's order."""
    rows: list[list[_Cell | None]] = [
        [_Cell(member, _HEADER) for member, _ in _NODE_MEMBERS]
    ]
    for node in nodes:
        row: list[_Cell | None] = []
        for member, _ in _NODE_MEMBERS:
            value = node.get(member)
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            row.append(_value_cell(value))
        rows.append(row)
    return _Sheet(
        name="Nodes",
        rows=rows,
        widths=tuple(width for _, width in _NODE_MEMBERS),
        frozen_rows=1,
        frozen_columns=1,
    )


_TRANSFORMATION_FACET: Final = "gaspatchio_column_transformation"


def _edges_sheet(
    document: Mapping[str, Any], nodes: Sequence[Mapping[str, Any]]
) -> _Sheet:
    """Return every edge, one row per way it was read, with its periods.

    The narrowing of a read travels on the reading node's facet rather than
    on the edge, one entry per entry of its ``reads``; a read made through
    two windows carries two, and gets a row each.
    """
    narrowings: dict[tuple[object, object], list[Mapping[str, Any]]] = {}
    for node in nodes:
        facet = _member(_member(node, "facets"), _TRANSFORMATION_FACET)
        for read in facet.get("reads") or ():
            if isinstance(read, dict):
                narrowings[node.get("id"), read.get("source")] = [
                    way
                    for way in read.get("transformations") or ()
                    if isinstance(way, dict)
                ]
    header = (
        "source",
        "target",
        "relationship",
        "narrowing",
        "offset",
        "periods from",
        "periods to",
        "position",
    )
    rows: list[list[_Cell | None]] = [[_Cell(text, _HEADER) for text in header]]
    for edge in document.get("edges") or ():
        if not isinstance(edge, dict):
            continue
        ways = narrowings.get((edge.get("target"), edge.get("source"))) or [{}]
        for way in ways:
            periods = _member(way, "periods")
            rows.append(
                [
                    _value_cell(edge.get("source")),
                    _value_cell(edge.get("target")),
                    _value_cell(edge.get("relationship")),
                    _value_cell(way.get("subtype")),
                    _value_cell(way.get("offset")),
                    _value_cell(periods.get("from")),
                    _value_cell(periods.get("to")),
                    _value_cell(way.get("position")),
                ]
            )
    return _Sheet(
        name="Edges",
        rows=rows,
        widths=(30, 30, 12, 16, 8, 12, 12, 10),
        frozen_rows=1,
    )


def _assumptions_sheet(document: Mapping[str, Any]) -> _Sheet:
    """Return every assumption base the record names, without its values."""
    header = ("kind", "name", "fingerprint", "source_file", "shaped_by", "payload")
    rows: list[list[_Cell | None]] = [[_Cell(text, _HEADER) for text in header]]
    for entry in document.get("assumptions") or ():
        if not isinstance(entry, dict):
            continue
        rows.append(
            [
                _value_cell(entry.get("kind")),
                _value_cell(entry.get("name")),
                _value_cell(entry.get("fingerprint")),
                _value_cell(_source_file(entry)),
                _value_cell(
                    _shaped_by(entry)
                    or ("" if "shaped_by" not in entry else "a plain read")
                ),
                _value_cell(_payload(entry.get("payload"))),
            ]
        )
    return _Sheet(
        name="Assumptions",
        rows=rows,
        widths=(10, 24, 74, 36, 40, 40),
        frozen_rows=1,
    )


def _source_file(entry: Mapping[str, Any]) -> str:
    """Return where a table was read from, in the three ways the record says it."""
    if "source_file" not in entry:
        return ""
    found = entry["source_file"]
    return "built from a frame in the model's code" if found is None else str(found)


def _payload(payload: object) -> str:
    """Return what the record carries of a base's values, in a phrase."""
    if not isinstance(payload, dict):
        return ""
    if "omitted" in payload:
        detail = payload.get("detail")
        return f"omitted ({payload['omitted']})" + (f": {detail}" if detail else "")
    rows = payload.get("rows")
    if isinstance(rows, list):
        columns = payload.get("columns") or ()
        return f"inline: {len(rows)} rows of {len(columns)} columns"
    return "inline recipe: " + json.dumps(payload, sort_keys=True, ensure_ascii=False)


# --- cells -----------------------------------------------------------------------


def _value_cell(value: object) -> _Cell | None:
    """Return the cell holding one recorded value, or None for a null."""
    if value is None:
        return None
    return _Cell(value)


def _refuse_past_excel(sheet: _Sheet) -> None:
    """Refuse a sheet Excel could not open."""
    if len(sheet.rows) > _MAX_ROWS:
        msg = (
            f"The {sheet.name} sheet would hold {len(sheet.rows):,} rows, past "
            f"Excel's {_MAX_ROWS:,}. Lay out fewer policies, or read the record "
            "itself."
        )
        raise ValueError(msg)
    widest = max((len(row) for row in sheet.rows), default=0)
    if widest > _MAX_COLUMNS:
        msg = (
            f"The {sheet.name} sheet would hold {widest:,} columns, past Excel's "
            f"{_MAX_COLUMNS:,}: the model has more per-period columns than a "
            "sheet can carry. Read the record itself."
        )
        raise ValueError(msg)


def _column_letters(index: int) -> str:
    """Return the letters naming a zero-based column: 0 is A, 26 is AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _number_text(value: float) -> str | None:
    """Return a number's cell text, or None where it has to be written as text.

    A double is written as Python's ``repr``: the shortest decimal that reads
    back to the same double, which is the text the record writes. A whole
    number is its digits, while a double still holds it exactly.
    """
    if isinstance(value, int):
        return str(value) if abs(value) <= _EXACT_INTEGER else None
    if not math.isfinite(value):
        return None
    return repr(value)


def _non_finite_word(value: float) -> str:
    """Return the record's own word for a non-finite double."""
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def _escaped(text: str) -> str:
    """Return text made safe for an XML element or a double-quoted attribute."""
    text = _LOOKS_ESCAPED.sub(r"_x005F_\1", text)
    text = _UNWRITABLE.sub(lambda found: f"_x{ord(found.group()):04X}_", text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\r", "&#13;")
    )


def _within_a_cell(text: str) -> str:
    """Return text cut to what one cell holds, saying so where it was cut."""
    if len(text) <= _MAX_CELL_TEXT:
        return text
    return text[: _MAX_CELL_TEXT - len(_TEXT_CUT)] + _TEXT_CUT


def _cell_xml(reference: str, cell: _Cell) -> str:
    """Return one ``<c>`` element: a number, a Boolean, or inline text."""
    style = f' s="{cell.style}"' if cell.style else ""
    value = cell.value
    if isinstance(value, bool):
        return f'<c r="{reference}"{style} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, int | float):
        number = _number_text(value)
        if number is not None:
            return f'<c r="{reference}"{style}><v>{number}</v></c>'
        text = str(value) if isinstance(value, int) else _non_finite_word(value)
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False)
    return (
        f'<c r="{reference}"{style} t="inlineStr"><is><t xml:space="preserve">'
        f"{_escaped(_within_a_cell(text))}</t></is></c>"
    )


# --- the package -------------------------------------------------------------------


def _sheet_xml(sheet: _Sheet) -> str:
    """Return one worksheet part."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
        f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">',
        '<sheetViews><sheetView workbookViewId="0">',
        _pane(sheet),
        "</sheetView></sheetViews>",
    ]
    if sheet.widths:
        parts.append("<cols>")
        parts += [
            f'<col min="{at}" max="{at}" width="{width}" customWidth="1"/>'
            for at, width in enumerate(sheet.widths, start=1)
        ]
        parts.append("</cols>")
    parts.append("<sheetData>")
    for at, row in enumerate(sheet.rows, start=1):
        cells = [
            _cell_xml(f"{_column_letters(column)}{at}", cell)
            for column, cell in enumerate(row)
            if cell is not None and cell.value is not None
        ]
        parts.append(f'<row r="{at}">{"".join(cells)}</row>')
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def _pane(sheet: _Sheet) -> str:
    """Return the frozen pane keeping a sheet's headers in view."""
    rows, columns = sheet.frozen_rows, sheet.frozen_columns
    if not rows and not columns:
        return ""
    corner = f"{_column_letters(columns)}{rows + 1}"
    split = (f' xSplit="{columns}"' if columns else "") + (
        f' ySplit="{rows}"' if rows else ""
    )
    active = (
        "bottomRight" if rows and columns else ("bottomLeft" if rows else "topRight")
    )
    return (
        f'<pane{split} topLeftCell="{corner}" activePane="{active}" state="frozen"/>'
        f'<selection pane="{active}" activeCell="{corner}" sqref="{corner}"/>'
    )


_STYLES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<styleSheet xmlns="{_MAIN_NS}">'
    '<fonts count="3">'
    '<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><i/><sz val="11"/><color rgb="FF595959"/><name val="Calibri"/>'
    '<family val="2"/></font>'
    "</fonts>"
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
    "</cellStyleXfs>"
    '<cellXfs count="3">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
    "</cellStyles>"
    "</styleSheet>"
)


def _content_types(count: int) -> str:
    """Return ``[Content_Types].xml`` for a workbook of ``count`` sheets."""
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{at}.xml" '
        f'ContentType="{_SHEET_TYPE}"/>'
        for at in range(1, count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{sheets}"
        '<Override PartName="/xl/styles.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )


def _package_rels() -> str:
    """Return the package's own relationships: the workbook and its properties."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{_PKG_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/'
        '2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )


def _core_properties(created: str | None) -> str:
    """Return the document properties, dated by the record rather than the clock."""
    dated = (
        '<dcterms:created xsi:type="dcterms:W3CDTF">'
        f"{_escaped(created)}</dcterms:created>"
        if created
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
        'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>gaspatchio</dc:creator>"
        f"{dated}"
        "</cp:coreProperties>"
    )


def _workbook(sheets: Sequence[_Sheet]) -> str:
    """Return the workbook part, naming each sheet in order."""
    named = "".join(
        f'<sheet name="{_escaped(sheet.name)}" sheetId="{at}" r:id="rId{at}"/>'
        for at, sheet in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        '<bookViews><workbookView activeTab="0"/></bookViews>'
        f"<sheets>{named}</sheets></workbook>"
    )


def _workbook_rels(count: int) -> str:
    """Return the workbook's relationships: each sheet, then the stylesheet."""
    sheets = "".join(
        f'<Relationship Id="rId{at}" Type="{_REL_NS}/worksheet" '
        f'Target="worksheets/sheet{at}.xml"/>'
        for at in range(1, count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{_PKG_REL_NS}">{sheets}'
        f'<Relationship Id="rId{count + 1}" Type="{_REL_NS}/styles" '
        'Target="styles.xml"/></Relationships>'
    )


def _package(sheets: Sequence[_Sheet], created: str | None) -> bytes:
    """Return the archive: every part, in one order, stored, at one timestamp."""
    parts = [
        ("[Content_Types].xml", _content_types(len(sheets))),
        ("_rels/.rels", _package_rels()),
        ("docProps/core.xml", _core_properties(created)),
        ("xl/workbook.xml", _workbook(sheets)),
        ("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets))),
        ("xl/styles.xml", _STYLES),
        *(
            (f"xl/worksheets/sheet{at}.xml", _sheet_xml(sheet))
            for at, sheet in enumerate(sheets, start=1)
        ),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, text in parts:
            member = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            member.compress_type = zipfile.ZIP_STORED
            # The system a member says made it, fixed: the default is the
            # platform's own, and would put the machine into the bytes.
            member.create_system = 0
            member.external_attr = 0
            archive.writestr(member, text.encode("utf-8"))
    return buffer.getvalue()
