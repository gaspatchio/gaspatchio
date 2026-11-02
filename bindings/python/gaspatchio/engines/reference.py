# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The producer's own answers, bound to node ids so a comparison can use them.

A comparison is between two engines' answers for the same *node*, and a
frame hands its columns back under the model's own *names*. Those part
company the moment a model writes a column twice: one name, two
definitions, and only the last of them is in the schema at the end. The
frame already carries the earlier one -- it rides through the collect under
a hidden name, which is how an export says what a column held before it was
written over -- and this module is where that machinery is read out under
node ids.

**Test tooling and the commands, never an engine.** ``gspio run-model
--every-node`` writes this; the agreement runs compare against it. An engine
reads the artifact and nothing else, which is the whole claim a second
implementation makes, and an engine that reached in here for a value would
be reading the producer's answer rather than computing its own.

**A modeller's results file keeps the modeller's names.** ``gspio run-model
--results`` and ``gspio calc-graph --results`` write the finished frame under
the columns the model wrote, and :func:`_final_schema_manifest` says what those
columns are and what produced them. It is the reference's final-schema scope
without the renaming: the node ids live in the manifest, not in the file.

**Three routes to a node's values**, and each is somebody else's machinery
rather than a fourth reading invented here:

- a column no calculation defines is the values it arrived with;
- a definition the frame still holds is the column itself, and one it
  replaced is the column the frame carried aside for it;
- a compiled rollforward's running balance is the exporter's own re-track
  over the finished frame, because no column of the model holds it.

A bare rollforward node is not a value at all -- it is one whole compilation
that every extraction from it reads -- so it earns no column, which is what
the ``every-node`` scope means by *value-bearing*.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.artifact import _first_sentence, book_columns

from ._versions import versions_in_this_process
from .protocol import VALUE_BEARING, ResultManifest, digest_of_inputs

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from gaspatchio.frame.base import ActuarialFrame

__all__ = ["polars_reference"]


class _ManifestWithheldError(ValueError):
    """Raised where a results manifest would claim what the run cannot vouch for.

    Its message is the one line a command prints beside results written without
    a manifest: which fact the run cannot vouch for, the refusal that said so,
    and the refusal's own next move where it has one.
    """


def polars_reference(
    af: ActuarialFrame,
    *,
    every_node: bool = False,
    row_identity: str | Sequence[str] | None = None,
) -> tuple[pl.DataFrame, ResultManifest]:
    """Run the frame on Polars and return its answers keyed by node id.

    Args:
        af: The finished frame -- the model has run and nothing has been
            collected off it that would move its plan.
        every_node: Carry every value-bearing node, rather than the model's
            final schema. The agreement runs use this, because the scale a
            line is judged against needs the values of what it reads.
        row_identity: The column carrying a policy's identity, or the
            columns that together name each row -- the policy's, then the
            scenario's on a scenario run -- where the caller knows them. Not
            inferred here: a frame in memory does not say which of its
            columns is a policy's identity. The commands resolve it from the
            book they read, as they resolve the policy a selection names.

    Returns:
        The frame, with one column per node named by node id, and the
        manifest saying what those columns are.

    """
    af.collect()
    return _reference_from_collection(
        af, every_node=every_node, row_identity=row_identity
    )


def _reference_from_collection(
    af: ActuarialFrame,
    *,
    every_node: bool = False,
    row_identity: str | Sequence[str] | None = None,
) -> tuple[pl.DataFrame, ResultManifest]:
    """Bind one completed Polars run to node ids without collecting it again.

    Read the frame's defensive snapshot, never a caller-supplied DataFrame.
    The plan setter invalidates it, and the summary proves which engine
    completed it. Neither a stale completion nor JAX output can be presented
    as a fresh Polars reference.
    """
    summary = af.graph.last_run
    result = af._collected_values  # noqa: SLF001 -- the completed run's own snapshot
    if result is None or summary is None or summary.engine != "polars":
        msg = (
            "This frame has no completed Polars collection of its current plan. "
            "Collect or profile it on Polars before reading its reference values."
        )
        raise ValueError(msg)
    document = json.loads(
        GraphExporter(af).export(result, profile="executable", include_source=False)
    )
    # A second exporter over the same frame and the same values. ``export``
    # walks the same three routes internally and hands back a document rather
    # than the pairing, and reaching into the first one half way through its
    # own run would be reading a graph mid-build.
    in_reach = GraphExporter(af).node_values(result)

    nodes = {str(node["id"]): node for node in document["nodes"]}
    wanted = _wanted(nodes, every_node=every_node)

    columns: dict[str, str] = {}
    dtypes: dict[str, str] = {}
    series: list[pl.Series] = []
    for node_id in wanted:
        values = in_reach.get(node_id)
        if values is None:
            continue
        columns[node_id] = node_id
        dtypes[node_id] = str(nodes[node_id].get("dtype") or "unknown")
        series.append(values.rename(node_id))

    identity = _as_columns(row_identity)
    frame = pl.DataFrame(series)
    for column in identity or ():
        if column not in frame.columns:
            frame = frame.hstack([result.get_column(column)])

    manifest = ResultManifest(
        scope="every-node" if every_node else "final-schema",
        columns=columns,
        dtypes=dtypes,
        row_identity=identity,
        graph_fingerprint=str(document["graph_fingerprint"]),
        inputs_digest=_the_book_it_ran_over(document, result),
        producer="polars",
        versions=versions_in_this_process(),
    )
    return frame, manifest


def _as_columns(row_identity: str | Sequence[str] | None) -> tuple[str, ...] | None:
    """Return a row identity as the columns it names, one name being one column."""
    if row_identity is None:
        return None
    if isinstance(row_identity, str):
        return (row_identity,)
    return tuple(row_identity) or None


def _final_schema_manifest(
    exporter: GraphExporter,
    written: pl.DataFrame,
    *,
    row_identity: Sequence[str] | None = None,
) -> ResultManifest:
    """Return the manifest of results written under the model's own column names.

    Same model, same data: would the library this ran on give the same
    answer? A results file can only take that question if it names all
    three, so the manifest carries the model's fingerprint, the digest of the
    book it ran over and the versions that produced it -- and, for each node
    the model's final schema holds, the column carrying it and the type the
    node declares. The file keeps the modeller's own column names; the node
    ids are in the manifest, which is what lets ``gspio compare`` read it
    beside an engine's results of the same model.

    The fingerprint and the digest are read off one values-free export
    through ``exporter``, the route an audit file takes, so they are the ones
    an audit file of the same frame states. An exporter that goes on to write
    that audit file reuses the book's digest rather than taking it twice. A
    column whose type is named only from its values -- an unsigned 64-bit
    integer is an i64 exactly where every value fits one -- is named from the
    values ``written`` holds, as ``calc-graph`` names it in its audit file.

    Args:
        exporter: The exporter over the frame the run finished on, holding the
            columns the book arrived with where the caller read the book.
        written: The results as they are written: which final-schema columns
            it carries decides which nodes the manifest names.
        row_identity: The columns that name each row of ``written`` once,
            as the command resolved them, or None where none does.

    Returns:
        The manifest, ready for
        :func:`~gaspatchio.engines.protocol.write_with_manifest`.

    Raises:
        _ManifestWithheldError: Where no honest manifest exists, saying
            exactly which fact cannot be vouched for: the model's
            fingerprint, where no reading of the model can state one, or the
            book it ran over, where the export could not digest it. The
            message carries the opening sentence of the refusal and that
            refusal's own next move, so one console line says what to do.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import GraphExporter
        >>> af = ActuarialFrame(pl.DataFrame({"premium": [1200.0, 900.0]}))
        >>> af.commission = af.premium * 0.05
        >>> values = af.collect()
        >>> manifest = _final_schema_manifest(GraphExporter(af), values)
        >>> manifest.columns
        {'premium': 'premium', 'commission@1': 'commission'}
        >>> manifest.graph_fingerprint == af.graph.fingerprint()
        True

    """
    document, refused = _the_audit_document(exporter, written)
    digest = _stated_book_digest(document)
    if digest is None:
        raise _ManifestWithheldError(_the_book_unvouched(document, refused))
    carried = set(written.columns)
    schema = [
        node
        for node in document["nodes"]
        if node.get("in_final_schema") and node.get("column") in carried
    ]
    return ResultManifest(
        scope="final-schema",
        columns={str(node["id"]): str(node["column"]) for node in schema},
        dtypes={
            str(node["id"]): str(node.get("dtype") or "unknown") for node in schema
        },
        row_identity=_as_columns(row_identity),
        graph_fingerprint=str(document["graph_fingerprint"]),
        inputs_digest=digest,
        producer="polars",
        versions=versions_in_this_process(),
    )


def _the_audit_document(
    exporter: GraphExporter, written: pl.DataFrame
) -> tuple[dict[str, Any], UnmappedDtypeError | None]:
    """Return the document a manifest is read off, and what refused without values.

    Values-free first: it is the cheap reading, and for nearly every model the
    one the audit file's fingerprint and book come to as well. A type named
    only from its values sends the reading to the values the run wrote, the
    route ``calc-graph`` takes, and the refusal met without them is handed
    back beside the document: where the book cannot be digested either, its
    next move is the one the reader needs.

    Raises:
        _ManifestWithheldError: Where no reading states a fingerprint -- a
            value no i64 carries, or a type with no name at all.

    """
    try:
        return _exported(exporter), None
    except UnmappedDtypeError as refused:
        without_values = refused
    try:
        return _exported(exporter, written), without_values
    except UnmappedDtypeError as refused:
        move = f" {refused.move}" if refused.move else ""
        message = (
            f"the model's fingerprint cannot be taken: {_first_sentence(refused)}{move}"
        )
        raise _ManifestWithheldError(message) from refused


def _exported(
    exporter: GraphExporter, values: pl.DataFrame | None = None
) -> dict[str, Any]:
    """Return an audit document of the frame, unsealed and without payloads."""
    document: dict[str, Any] = json.loads(
        exporter.export(
            values,
            profile="audit",
            include_source=False,
            include_tables=False,
            seal=False,
        )
    )
    return document


def _the_book_unvouched(
    document: Mapping[str, Any], refused: UnmappedDtypeError | None
) -> str:
    """Return the line saying the book cannot be vouched for, and what to do.

    The document says why in its own words. The next move is the one the
    type refusal met without values gave, where that refusal is about a
    column the book's own refusal names -- the same column, refused for the
    same type -- and nothing is guessed where it is not.
    """
    book = document.get("book")
    stated = book.get("digest") if isinstance(book, dict) else None
    detail = stated.get("detail") if isinstance(stated, dict) else None
    said = f" {detail}" if isinstance(detail, str) else ""
    same_column = (
        refused is not None
        and refused.column is not None
        and repr(refused.column) in said
    )
    move = f" {refused.move}" if same_column and refused and refused.move else ""
    return f"the book this model ran over cannot be vouched for.{said}{move}"


def _the_book_it_ran_over(document: dict[str, Any], result: pl.DataFrame) -> str:
    """Return the digest of the book this Polars run was handed.

    The frame's own book, which the export has just digested over the columns
    the model's answers rest on (:func:`book_columns`) -- the same columns and
    the same function an engine handed that book records, taken once rather
    than twice, and counting an input the model read and then dropped, which
    the finished frame no longer holds. Where the document could not vouch
    for its book, the digest is taken over what the finished frame still
    holds of those columns, which is the most this run can say.
    """
    stated = _stated_book_digest(document)
    if stated is not None:
        return stated
    return digest_of_inputs(
        result, book_columns(document["nodes"], document.get("selection"))
    )


def _stated_book_digest(document: Mapping[str, Any]) -> str | None:
    """Return the book digest a document states, or None where it vouched for none."""
    book = document.get("book")
    stated = book.get("digest") if isinstance(book, dict) else None
    return stated if isinstance(stated, str) else None


def _wanted(nodes: dict[str, Any], *, every_node: bool) -> list[str]:
    """Return the node ids this scope asks for, in the document's own order."""
    if every_node:
        return [
            node_id
            for node_id, node in nodes.items()
            if node.get("kind") in VALUE_BEARING
        ]
    return [node_id for node_id, node in nodes.items() if node.get("in_final_schema")]
