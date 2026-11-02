# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio graph``: the questions ``af.graph`` answers, asked of an audit file.

A reviewer handed the audit file a run wrote asks it four things: what is
behind this reserve, what moves if this input moves, which calculations does
nothing use, and, for each arrow, which period does it read. Each subcommand
is one of ``af.graph``'s questions under its own name, answered by the same
walk over the file (:func:`gaspatchio.graph.read_artifact`), so a reviewer
who knows ``af.graph.trace`` already knows ``gspio graph trace``.

Text by default, ``--json`` for the same answer as JSON on stdout, and
``--output-file`` to store that JSON. The exit status is ``2`` where the file
cannot be read or the column is not in it, and ``1`` only where ``unused
--fail-on`` names a class that is not empty.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path  # noqa: TC003 -- typer reads the annotations at runtime
from typing import TYPE_CHECKING, Annotated, Any, Final, NoReturn

import typer

from ._output_target import no_place_for_a_file
from ._shown import shown, spelled, terminal_console
from .frame.graph.lineage import UNUSED_CLASSES
from .graph import GraphDocument, read_artifact

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from .frame.graph.lineage import Unused

_EXIT_FOUND: Final = 1
_EXIT_UNREADABLE: Final = 2
_FACET: Final = "gaspatchio_column_transformation"
_MINUS: Final = "\u2212"
_ELLIPSIS: Final = "\u2026"

# Every name these print came out of a file someone else may have written, so
# both consoles spell any control character it holds rather than obey it.
console = terminal_console()
err_console = terminal_console(stderr=True)

graph_app = typer.Typer(
    name="graph",
    help=(
        "Ask an audit file what af.graph answers on a frame: what is behind a "
        "column, what it reaches, and what nothing uses"
    ),
    no_args_is_help=True,
)

# Each parameter's help, held once and shared by every subcommand that takes
# it. A parameter object rather than an annotated alias, because what typer
# reads off the annotation is this object, and an alias of one is a type to
# the checkers and a call to the interpreter.
_ARTIFACT = typer.Argument(
    help="The audit file gspio calc-graph wrote", show_default=False
)
_COLUMN = typer.Argument(
    help="A column name (its live definition) or an explicit column@ordinal",
    show_default=False,
)
_JSON = typer.Option("--json", "-j", help="Print the answer as JSON instead of text")
_OUTPUT = typer.Option("--output-file", "-o", help="Also store the answer as JSON here")
_DEPTH = typer.Option(
    "--depth",
    min=0,
    help="Follow at most this many reads (0 is the column alone); every read "
    "by default",
)


# --- the subcommands ----------------------------------------------------------


@graph_app.command("precedents")
def precedents(
    artifact: Annotated[Path, _ARTIFACT],
    column: Annotated[str, _COLUMN],
    *,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Name what one column's own formula read, and how it read each.

    [bold green]Example:[/bold green]
        gspio graph precedents audit.json pv_net_cf
    """
    document, read = _read(artifact)
    node = _node_named(document, column)
    found = _answer(lambda: document.precedents(column))
    lines = [f"  {shown(one)}{_how(read, one, node)}" for one in found]
    _say(
        f"{node} read {_counted(len(found), 'node')}, first mention first:",
        lines,
        json_output=json_output,
    )
    _store(
        _payload(
            document, read, question="precedents", asked=column, node=node, found=found
        ),
        json_output=json_output,
        output_file=output_file,
    )


@graph_app.command("dependents")
def dependents(
    artifact: Annotated[Path, _ARTIFACT],
    column: Annotated[str, _COLUMN],
    *,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Name what reads one column, or a running balance it materialises.

    [bold green]Example:[/bold green]
        gspio graph dependents audit.json mort_rate
    """
    document, read = _read(artifact)
    node = _node_named(document, column)
    found = _answer(lambda: document.dependents(column))
    lines = [f"  {shown(reader)}{_how_read(read, reader, node)}" for reader in found]
    _say(
        f"{_counted(len(found), 'node')} read {node}, in the order the model "
        "defined them:",
        lines,
        json_output=json_output,
    )
    _store(
        _payload(
            document, read, question="dependents", asked=column, node=node, found=found
        ),
        json_output=json_output,
        output_file=output_file,
    )


@graph_app.command("trace")
def trace(
    artifact: Annotated[Path, _ARTIFACT],
    column: Annotated[str, _COLUMN],
    *,
    depth: Annotated[int | None, _DEPTH] = None,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Show everything behind one column, each node after everything it reads.

    Each line names what that node read inside the cone, and how: the period
    a shifted read took (t-1), the periods an aggregation read
    (first...t), a stored position, or a key or condition read.

    [bold green]Example:[/bold green]
        gspio graph trace audit.json pv_net_cf
        gspio graph trace audit.json pv_net_cf --depth 2 --json
    """
    document, read = _read(artifact)
    node = _node_named(document, column)
    found = _answer(lambda: document.trace(column, depth=depth))
    _say(
        f"{node}: {_counted(len(found), 'node')} behind it and itself, each "
        f"after everything it reads ({_depth_said(depth)}):",
        _cone_lines(read, found),
        json_output=json_output,
    )
    _store(
        _payload(
            document,
            read,
            question="trace",
            asked=column,
            node=node,
            found=found,
            depth=depth,
        ),
        json_output=json_output,
        output_file=output_file,
    )


@graph_app.command("affected")
def affected(  # noqa: PLR0913 -- a command's options are its arguments
    artifact: Annotated[Path, _ARTIFACT],
    column: Annotated[
        str | None,
        typer.Argument(
            help="A column name or column@ordinal; leave out with --assumption",
            show_default=False,
        ),
    ] = None,
    *,
    assumption: Annotated[
        str | None,
        typer.Option(
            "--assumption",
            help="Start from every calculation that looked this table up",
        ),
    ] = None,
    depth: Annotated[int | None, _DEPTH] = None,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Show everything that moves if one column, or one assumption table, moves.

    [bold green]Example:[/bold green]
        gspio graph affected audit.json mort_rate
        gspio graph affected audit.json --assumption mortality
    """
    document, read = _read(artifact)
    found = _answer(
        lambda: document.affected(column, assumption=assumption, depth=depth)
    )
    start = (
        f"the assumption {assumption!r}"
        if assumption is not None
        else _node_named(document, str(column))
    )
    _say(
        f"{_counted(len(found), 'node')} move with {start}, each after "
        f"everything that reaches it ({_depth_said(depth)}):",
        _cone_lines(read, found),
        json_output=json_output,
    )
    payload = _payload(
        document,
        read,
        question="affected",
        asked=column,
        node=None if assumption is not None else str(start),
        found=found,
        depth=depth,
    )
    payload["assumption"] = assumption
    _store(payload, json_output=json_output, output_file=output_file)


@graph_app.command("unused")
def unused(  # noqa: PLR0913 -- a command's options are its arguments
    artifact: Annotated[Path, _ARTIFACT],
    *,
    keep: Annotated[
        str | None,
        typer.Option(
            "--keep",
            help="Comma-separated columns that are results, set aside as kept",
        ),
    ] = None,
    keep_from: Annotated[
        Path | None,
        typer.Option(
            "--keep-from",
            help="A TOML file whose keep = [...] lists the columns that are results",
        ),
    ] = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help="Comma-separated classes that exit 1 when any node falls in them, "
            "e.g. superseded,terminal",
        ),
    ] = None,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """List every calculation nothing reads, each under the one class it is.

    superseded: a definition a later one replaced, never read.
    data: an arriving or joined column nothing reads.
    stamp: a column the projection set up that nothing reads.
    length_only: read only for its length.
    terminal: a live calculation nothing reads -- a result or dead code.
    Name the results with --keep or --keep-from and they move to kept.

    [bold green]Example:[/bold green]
        gspio graph unused audit.json
        gspio graph unused audit.json --keep pv_net_cf,reserve --fail-on superseded
    """
    document, _ = _read(artifact)
    failing = _classes(fail_on)
    kept = [*_names(keep), *_kept_in(keep_from)]
    found = _answer(lambda: document.unused(kept))
    counts = found.counts
    failed = [name for name in failing if counts[name]]
    _say(
        f"{_counted(sum(counts.values()), 'node')} nothing reads, of "
        f"{_counted(len(document.document['nodes']), 'node')}:",
        _unused_lines(found),
        json_output=json_output,
    )
    payload: dict[str, Any] = {
        "question": "unused",
        "artifact": str(artifact),
        "keep": kept,
        "classes": {name: list(found.of(name)) for name in counts},
        "counts": counts,
        "fail_on": failing,
        "failed": failed,
    }
    _store(payload, json_output=json_output, output_file=output_file)
    if failed:
        err_console.print(
            f"[red]--fail-on: {', '.join(f'{counts[n]} {n}' for n in failed)}.[/red]"
        )
        raise typer.Exit(_EXIT_FOUND)


@graph_app.command("holes")
def holes(
    artifact: Annotated[Path, _ARTIFACT],
    *,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Name the columns the audit file says its model cannot account for.

    [bold green]Example:[/bold green]
        gspio graph holes audit.json
    """
    document, _ = _read(artifact)
    found = document.holes()
    lines = [
        f"  {shown(hole.column)}: {shown(hole.reason)}. {shown(hole.hint)}"
        for hole in found
    ]
    headline = (
        f"{_counted(len(found), 'column')} the model cannot account for:"
        if found
        else "No holes: the model accounts for every column it holds."
    )
    _say(headline, lines, json_output=json_output)
    payload = {
        "question": "holes",
        "artifact": str(artifact),
        "holes": [dict(entry) for entry in document.document.get("holes") or ()],
    }
    _store(payload, json_output=json_output, output_file=output_file)


@graph_app.command("tiers")
def tiers(
    artifact: Annotated[Path, _ARTIFACT],
    *,
    json_output: Annotated[bool, _JSON] = False,
    output_file: Annotated[Path | None, _OUTPUT] = None,
) -> None:
    """Count the model's calculations at each tier, and name the ones not core.

    [bold green]Example:[/bold green]
        gspio graph tiers audit.json
    """
    document, _ = _read(artifact)
    census = _answer(document.tiers)
    counts = census.counts
    lines = [
        f"  {tier}: {', '.join(shown(node) for node in nodes)}"
        for tier, nodes in (
            ("engine_native", census.engine_native),
            ("opaque", census.opaque),
        )
        if nodes
    ]
    _say(
        f"{_counted(sum(counts.values()), 'calculation')}: "
        + ", ".join(f"{count} {tier}" for tier, count in counts.items()),
        lines,
        json_output=json_output,
    )
    payload = {
        "question": "tiers",
        "artifact": str(artifact),
        "core": list(census.core),
        "engine_native": list(census.engine_native),
        "opaque": list(census.opaque),
        "counts": counts,
    }
    _store(payload, json_output=json_output, output_file=output_file)


# --- reading, and refusing ----------------------------------------------------


def _read(artifact: Path) -> tuple[GraphDocument, _Read]:
    """Return the audit file read, or say why it could not be and exit 2."""
    try:
        document = read_artifact(artifact)
    except (OSError, ValueError) as error:
        _refuse(f"{artifact} could not be read: {error}")
    return document, _Read(document)


def _node_named(document: GraphDocument, column: str) -> str:
    """Return the node a column name or an explicit id stands for, or exit 2."""
    return _answer(lambda: document.trace(column, depth=0))[-1]


def _answer[T](question: Callable[[], T]) -> T:
    """Return the answer to ``question``, or print its refusal and exit 2."""
    try:
        return question()
    except ValueError as error:
        _refuse(str(error))


def _refuse(message: str) -> NoReturn:
    """Print ``message`` on stderr and exit with the unreadable status."""
    err_console.print(f"[red]{shown(message, lines=True)}[/red]")
    raise typer.Exit(_EXIT_UNREADABLE)


def _names(listed: str | None) -> list[str]:
    """Return the names a comma-separated option lists, blanks dropped."""
    return [name.strip() for name in (listed or "").split(",") if name.strip()]


def _classes(listed: str | None) -> list[str]:
    """Return the classes ``--fail-on`` names, or refuse an unknown one."""
    names = _names(listed)
    unknown = [name for name in names if name not in UNUSED_CLASSES]
    if unknown:
        _refuse(
            f"--fail-on names {', '.join(repr(n) for n in unknown)}, which is not "
            f"a class. The classes are {', '.join(UNUSED_CLASSES)}."
        )
    return names


def _kept_in(path: Path | None) -> list[str]:
    """Return the names a ``--keep-from`` file's ``keep`` array lists."""
    if path is None:
        return []
    try:
        listed = tomllib.loads(path.read_text("utf-8")).get("keep")
    except (OSError, ValueError) as error:
        _refuse(f"{path} could not be read as TOML: {error}")
    if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed):
        _refuse(
            f"{path} has no keep = [...] array of column names, which is what "
            "--keep-from reads."
        )
    return list(listed)


class _Read:
    """How each node of the file read each of its reads, as the file states it.

    ``af.graph`` answers with node ids; a reviewer reading one at a shell also
    wants to see, on each arrow, which period it read. That is the narrowing
    facet a node carries for its reads (section 9), read off the file as it
    is, never off a formula's text.
    """

    __slots__ = ("_reads", "_ways")

    def __init__(self, document: GraphDocument) -> None:
        """Index every node's reads and the narrowing of each."""
        self._reads: dict[str, tuple[str, ...]] = {}
        self._ways: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for node in document.document["nodes"]:
            self._reads[node["id"]] = tuple(node["reads"])
            facet = (node.get("facets") or {}).get(_FACET) or {}
            for read in facet.get("reads") or ():
                self._ways[(read["source"], node["id"])] = list(
                    read.get("transformations") or ()
                )

    def of(self, node_id: str) -> tuple[str, ...]:
        """Return what one node read, first mention first."""
        return self._reads[node_id]

    def ways(self, source: str, target: str) -> Sequence[Mapping[str, Any]]:
        """Return how ``target`` read ``source``: one entry per way it was read."""
        return self._ways.get((source, target), ())


# --- saying it ----------------------------------------------------------------


def _say(headline: str, lines: Iterable[str], *, json_output: bool) -> None:
    """Print the answer for a person, unless it is going out as JSON."""
    if json_output:
        return
    console.print(shown(headline), highlight=False)
    for line in lines:
        console.print(line, highlight=False, soft_wrap=True)


def _store(
    payload: Mapping[str, Any], *, json_output: bool, output_file: Path | None
) -> None:
    """Print the answer as JSON, store it, or both, as the caller asked."""
    text = json.dumps(payload, indent=2)
    if json_output:
        typer.echo(text)
    if output_file is None:
        return
    why = no_place_for_a_file("--output-file", output_file)
    if why is not None:
        _refuse(f"The answer was reached but not stored: {why}")
    try:
        output_file.write_text(text, "utf-8")
    except OSError as error:
        _refuse(f"The answer was reached but not stored at {output_file}: {error}")


def _payload(  # noqa: PLR0913 -- one answer, and everything it is stated with
    document: GraphDocument,
    read: _Read,
    *,
    question: str,
    asked: str | None,
    node: str | None,
    found: Sequence[str],
    depth: int | None = None,
) -> dict[str, Any]:
    """Return one lineage answer as JSON: the nodes, and the reads between them.

    ``reads`` holds every read whose two ends are both in the answer or are
    the node asked about, each with the narrowing the file states for it.
    """
    within = {*found, *([node] if node is not None else [])}
    targets = [*found, *([node] if node is not None and node not in found else [])]
    return {
        "question": question,
        "artifact": str(document.path),
        "column": asked,
        "node": node,
        "depth": depth,
        "nodes": list(found),
        "reads": [
            {
                "source": source,
                "target": target,
                "transformations": [dict(way) for way in read.ways(source, target)],
            }
            for target in targets
            for source in read.of(target)
            if source in within
        ],
    }


def _cone_lines(read: _Read, found: Sequence[str]) -> list[str]:
    """Return one line per node of a cone, naming what it read inside the cone."""
    within = set(found)
    width = max((len(spelled(node)) for node in found), default=0)
    lines = []
    for node in found:
        reads = [
            f"{shown(source)}{_how(read, source, node)}"
            for source in read.of(node)
            if source in within
        ]
        arrow = f"  \u2190 {', '.join(reads)}" if reads else ""
        lines.append(f"  {shown(spelled(node).ljust(width))}{arrow}".rstrip())
    return lines


def _how(read: _Read, source: str, target: str) -> str:
    """Return how ``target`` read ``source``, as a short label, or nothing."""
    parts = list(dict.fromkeys(_label(way) for way in read.ways(source, target)))
    said = [part for part in parts if part]
    # A narrowing's kind is text the file states, as much as an id is.
    return f" ({shown('; '.join(said))})" if said else ""


def _how_read(read: _Read, reader: str, node: str) -> str:
    """Return how ``reader`` read the node asked about, or nothing."""
    return _how(read, node, reader)


def _label(way: Mapping[str, Any]) -> str:
    """Return the period, window or position one narrowing states, and its kind."""
    parts: list[str] = []
    if isinstance(way.get("offset"), int):
        parts.append(_bound(way["offset"]))
    periods = way.get("periods")
    if isinstance(periods, dict):
        parts.append(
            f"{_bound(periods.get('from'))}{_ELLIPSIS}{_bound(periods.get('to'))}"
        )
    if isinstance(way.get("position"), int):
        parts.append(f"position {str(way['position']).replace('-', _MINUS)}")
    if way.get("type") == "INDIRECT" and isinstance(way.get("subtype"), str):
        parts.append(way["subtype"].lower())
    return ", ".join(parts)


def _bound(bound: object) -> str:
    """Return one end of a window, or an offset, the way the viewer writes it."""
    if bound in ("first", "last"):
        return str(bound)
    if not isinstance(bound, int) or bound == 0:
        return "t"
    return f"t{_MINUS}{abs(bound)}" if bound < 0 else f"t+{bound}"


def _unused_lines(found: Unused) -> list[str]:
    """Return one line per class: its count and its node ids."""
    meaning = {
        "superseded": "replaced by a later definition, never read",
        "data": "arrived and never read",
        "stamp": "set up by the projection, never read",
        "length_only": "read only for its length",
        "terminal": "a result, or dead code: the model does not say which",
        "kept": "named as results",
    }
    lines = []
    for name in (*UNUSED_CLASSES, "kept"):
        nodes = found.of(name)
        listed = f": {', '.join(shown(node) for node in nodes)}" if nodes else ""
        lines.append(f"  {name} ({len(nodes)}, {meaning[name]}){listed}")
    return lines


def _depth_said(depth: int | None) -> str:
    """Return how far the walk went, in words."""
    if depth is None:
        return "every read"
    return f"at most {_counted(depth, 'read')}"


def _counted(number: int, noun: str) -> str:
    """Return the number and the noun, pluralised the ordinary way."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"
