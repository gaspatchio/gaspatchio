# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Ask an exported audit file what ``af.graph`` asks of a live frame.

A reviewer is usually handed the file, not the model: the audit document a
run wrote, with no model code, no data and no environment to run either in.
The file already holds the model's whole account of itself -- every
definition, what each read, which running balance a column materialises --
so the questions ``af.graph`` answers on a live frame have answers here too,
and they are the same answers. :func:`read_artifact` reads the file and
returns a :class:`GraphDocument` with ``af.graph``'s own questions under their
own names, each answered by the walk that answers it on the frame
(:class:`~gaspatchio.frame.graph.lineage.Lineage`). ``gspio graph`` asks the
same questions from a shell.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from gaspatchio._lfs import parse_lfs_pointer
from gaspatchio.frame.graph.holes import Hole
from gaspatchio.frame.graph.lineage import Lineage
from gaspatchio.frame.graph.tiers import _census_of_document

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from os import PathLike

    from gaspatchio.frame.graph.graph_models import NodeId
    from gaspatchio.frame.graph.lineage import Unused
    from gaspatchio.frame.graph.tiers import TierCensus

__all__ = ["GraphDocument", "read_artifact"]

_CHECK_IT = "Check it with gspio validate, which names every field out of place."


class GraphDocument:
    """One audit file, answering the lineage questions ``af.graph`` answers.

    Every method here is the one ``af.graph`` has, under the same name, with
    the same arguments, and returns the same answer for the frame the file
    was exported from -- node ids in the order the model defined them. Both
    are walked by one implementation, so the two cannot drift.

    What a file cannot answer is anything about the frame that is not in it:
    there is no ``last_run``, and a column name resolves against the
    definitions the document records.

    Attributes:
        document: The document as read, a JSON object.
        path: Where it was read from, or ``None`` for one handed over in
            memory.

    """

    __slots__ = ("_lineage", "document", "path")

    def __init__(
        self, document: Mapping[str, Any], *, path: Path | None = None
    ) -> None:
        """Read the lineage out of ``document``'s nodes.

        Raises:
            ValueError: If the document carries no ``nodes`` array a lineage
                can be read from: a node with no id, a ``reads`` that is not
                a list of ids, or a read naming a node the document lacks.

        """
        self.document = document
        self.path = path
        self._lineage = Lineage.of_document(_nodes_of(document, path))

    def __repr__(self) -> str:
        """Return what the document is and where it came from."""
        named = "in memory" if self.path is None else str(self.path)
        return f"<GraphDocument {named}: {len(self._lineage.order)} nodes>"

    # --- the questions, as af.graph asks them -------------------------------

    def precedents(self, column: str) -> tuple[NodeId, ...]:
        """Return the definitions ``column``'s own formula read.

        See :meth:`GraphFrameAccessor.precedents`.

        Raises:
            ValueError: If the document holds no such column and no such node.

        """
        return self._lineage.precedents(column)

    def dependents(self, column: str) -> tuple[NodeId, ...]:
        """Return the definitions that read ``column``, or a balance it materialises.

        See :meth:`GraphFrameAccessor.dependents`.

        Raises:
            ValueError: If the document holds no such column and no such node.

        """
        return self._lineage.dependents(column)

    def trace(self, column: str, *, depth: int | None = None) -> tuple[NodeId, ...]:
        """Return everything behind ``column``, ending with ``column``'s own node.

        See :meth:`GraphFrameAccessor.trace`.

        Raises:
            ValueError: If the document holds no such column and no such node,
                or if ``depth`` is not a whole number of reads.

        """
        return self._lineage.trace(column, depth=depth)

    def affected(
        self,
        column: str | None = None,
        *,
        assumption: str | None = None,
        depth: int | None = None,
    ) -> tuple[NodeId, ...]:
        """Return everything ahead of ``column``, or of every reader of ``assumption``.

        See :meth:`GraphFrameAccessor.affected`.

        Raises:
            ValueError: If the column or the assumption is not in the document,
                if both or neither is named, or if ``depth`` is not a whole
                number of reads.

        """
        return self._lineage.affected(column, assumption=assumption, depth=depth)

    def versions(self, column: str) -> tuple[NodeId, ...]:
        """Return every definition of ``column``, oldest first.

        See :meth:`GraphFrameAccessor.versions`.

        Raises:
            ValueError: If the document holds no such column and no such node.

        """
        return self._lineage.versions_of(self._lineage.column_of(column))

    def latest(self, column: str) -> NodeId:
        """Return the node holding ``column``'s value at the end of the log.

        See :meth:`GraphFrameAccessor.latest`.

        Raises:
            ValueError: If the document holds no such column and no such node.

        """
        return self._lineage.resolve(self._lineage.column_of(column))

    def unused(self, keep: Iterable[str] = ()) -> Unused:
        """Return every calculation nothing reads, each under the one class it is.

        See :meth:`GraphFrameAccessor.unused`.

        Raises:
            ValueError: If a name in ``keep`` is not in the document.

        """
        return self._lineage.unused(keep)

    def holes(self) -> list[Hole]:
        """Return the columns the document says its model cannot account for.

        Read off the document's ``holes`` section: one per column, with the
        reason the producer saw and, for a column the frame arrived holding,
        the stamp of its values. The hint names the page the section points
        at for what closes the hole, since a file carries the page rather
        than the sentence ``af.graph.holes()`` writes from the live frame.
        """
        section = self.document.get("holes") or ()
        return [
            Hole(
                column=entry["column"],
                reason=entry["reason"],
                hint=f"What closes it: {entry.get('closes_with', '')}",
                content=entry.get("content"),
            )
            for entry in section
        ]

    def tiers(self) -> TierCensus:
        """Return which of the model's calculations sit at each tier.

        Each calculation is counted at the tier its node carries in the file,
        which is the tier ``af.graph.tiers()`` reads off the same operation
        tree. See :meth:`GraphFrameAccessor.tiers`.

        Raises:
            ValueError: If a calculation carries no tier, or one the format
                does not define.

        """
        return _census_of_document(self.document["nodes"])

    def fingerprint(self) -> str:
        """Return the model's content-addressed stamp, as the file records it.

        The ``graph_fingerprint`` the producer wrote, which is the value
        :meth:`GraphFrameAccessor.fingerprint` returns on the frame it was
        exported from, read rather than recomputed --
        ``gspio validate --deep`` recomputes it.

        Raises:
            ValueError: If the document records none.

        """
        stamp = self.document.get("graph_fingerprint")
        if isinstance(stamp, str):
            return stamp
        msg = f"The document records no graph_fingerprint. {_CHECK_IT}"
        raise ValueError(msg)


def read_artifact(path: str | PathLike[str]) -> GraphDocument:
    """Read an exported audit file, ready to answer what ``af.graph`` answers.

    A reviewer holding only the file asks it what is behind a reserve, what
    moves if the mortality table moves, and which calculations nothing uses,
    and gets the answers ``af.graph`` would give on the frame the file was
    exported from -- one implementation answers both. Nothing is run.

    Args:
        path: The audit file ``gspio calc-graph`` or
            :meth:`GraphExporter.export` wrote. Either profile reads.

    Returns:
        The document, with ``precedents``, ``dependents``, ``trace``,
        ``affected``, ``unused``, ``versions``, ``latest``, ``holes``,
        ``tiers`` and ``fingerprint``.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If it is a Git LFS pointer, is not UTF-8 text, is not
            JSON, is not a JSON object, or carries no nodes to read.

    Examples:
        >>> import tempfile
        >>> from pathlib import Path
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import GraphExporter
        >>> from gaspatchio.graph import read_artifact
        >>> af = ActuarialFrame(
        ...     pl.DataFrame({"sum_assured": [100_000.0], "mortality_rate": [0.01]})
        ... )
        >>> af.death_claims = af.sum_assured * af.mortality_rate
        >>> af.reinsured = af.death_claims * 0.5
        >>> folder = Path(tempfile.mkdtemp())
        >>> _ = (folder / "audit.json").write_text(GraphExporter(af).export())
        >>> audit = read_artifact(folder / "audit.json")
        >>> audit.trace("reinsured")
        ('sum_assured', 'mortality_rate', 'death_claims@1', 'reinsured@1')
        >>> audit.trace("reinsured") == af.graph.trace("reinsured")
        True
        >>> audit.unused().terminal
        ('reinsured@1',)

    """
    where = Path(path)
    data = where.read_bytes()
    pointer = parse_lfs_pointer(data)
    if pointer is not None:
        msg = (
            f"{where} is a Git LFS pointer, not the file it stands for (sha256 "
            f"{pointer.oid}, {pointer.size} bytes): it was checked out without "
            "Git LFS, and git lfs pull fetches it."
        )
        raise ValueError(msg)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        msg = f"{where} holds bytes rather than text, so it is no audit file: {error}"
        raise ValueError(msg) from None
    try:
        document = json.loads(text)
    except ValueError as error:
        msg = f"{where} could not be read as an audit file: {error}"
        raise ValueError(msg) from None
    is_an_object = isinstance(document, dict)
    if not is_an_object:
        msg = (
            f"{where} holds JSON that is not an object, and an audit file is a "
            "JSON object."
        )
        raise ValueError(msg)
    return GraphDocument(cast("dict[str, Any]", document), path=where)


def _nodes_of(
    document: Mapping[str, Any], path: Path | None
) -> Sequence[Mapping[str, Any]]:
    """Return the document's nodes, once each is a node a lineage can read.

    Raises:
        ValueError: If ``nodes`` is missing or not an array of objects, if a
            node has no string id or a ``reads`` that is not a list of ids,
            or if a read names a node the document does not carry.

    """
    named = "The document" if path is None else str(path)
    nodes = document.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(n, dict) for n in nodes):
        msg = f"{named} carries no nodes array, so it is no audit file. {_CHECK_IT}"
        raise ValueError(msg)
    ids = {node.get("id") for node in nodes}
    for node in cast("list[dict[str, Any]]", nodes):
        reads = node.get("reads")
        readable = isinstance(node.get("id"), str) and isinstance(reads, list)
        if not readable:
            msg = (
                f"{named} has a node without a string id and a reads list "
                f"({node.get('id')!r}). {_CHECK_IT}"
            )
            raise ValueError(msg)
        missing = [read for read in cast("list[str]", reads) if read not in ids]
        if missing:
            msg = (
                f"{named}: {node['id']!r} reads {missing[0]!r}, which is no node "
                f"of the document. {_CHECK_IT}"
            )
            raise ValueError(msg)
    return cast("list[dict[str, Any]]", nodes)
