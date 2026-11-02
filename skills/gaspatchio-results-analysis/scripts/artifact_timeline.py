# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: INP001 - standalone utilities inside a skill payload, not a
# package. The skill directory is copied verbatim into an editor's plugin
# cache, where an __init__.py would claim a package that nothing imports.

"""Read one declared policy's timeline out of a calculation-graph artifact.

The artifact carries values for the policies on its ``policies`` axis, and
this reads a file carrying one of them: ``enrichment.policy_id`` names it, and
every node whose ``shape`` is ``list`` carries that policy's whole projection
in ``value_sample``, each value the full double the run held. Laid side by
side those samples are a frame -- one row per point of the time axis, one
column per list node -- and that frame is what a chart or a table of a single
policy is drawn from. A node holding one value per period beside an axis of
``n_periods + 1`` boundaries is blank in the last row, and is named in a
warning rather than read as a period it did not reach.

**A file carrying several policies is refused rather than read.** Each
enrichment field is then an array along that axis, one entry per policy, and
reading the first of them as a timeline would lay a run of policies out under
the period numbers and call it a projection.

Nothing here computes a model number. Every value in the frame is a value the
file already states, read across instead of down.

**The CSV is safe to open in a spreadsheet.** A text cell or a header that
begins with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return -- a
formula, to Excel and its kin -- is written with a leading ``'``, the standard
neutralisation, so a column named ``=HYPERLINK(...)`` in a book someone else
exported is shown as text rather than run. Numbers are written as they are,
negative ones included; the table and JSON forms are unchanged.

Run it::

    bindings/python/.venv/bin/python artifact_timeline.py graph.json
    bindings/python/.venv/bin/python artifact_timeline.py graph.json --what nodes
    bindings/python/.venv/bin/python artifact_timeline.py graph.json --format csv

Import it::

    from artifact_timeline import read_artifact, timeline, nodes_table
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

PERIOD_COLUMN = "period"
"""The projection-period label the timeline frame is indexed by."""

TIME_AXIS_COLUMN = "month"
"""The column the framework stamps for elapsed whole months, placed first."""


FORMULA_LEAD = r"^[=+\-@\t\r]"
"""The leading characters a spreadsheet reads as the start of a formula."""


def spreadsheet_safe(frame: pl.DataFrame) -> pl.DataFrame:
    """Return ``frame`` with each cell and header a spreadsheet would run made inert.

    A cell or a header that begins with ``=``, ``+``, ``-``, ``@``, a tab or
    a carriage return is a formula to Excel and its kin: a column named
    ``=HYPERLINK("https://...")`` in a book someone else exported becomes a
    live link the moment the CSV opens. Each such text value, and each such
    header, gets a leading ``'`` -- the standard neutralisation, which a
    spreadsheet shows as text and drops from the cell. Numbers are never
    touched: ``-0.25`` in a numeric column is a number, and stays one.

    Args:
        frame: What the CSV is written from.

    Returns:
        The same frame, its text columns and headers neutralised.

    """
    text = [name for name, dtype in frame.schema.items() if dtype == pl.String]
    safe = frame.with_columns(
        pl.when(pl.col(name).str.contains(FORMULA_LEAD))
        .then(pl.concat_str([pl.lit("'"), pl.col(name)]))
        .otherwise(pl.col(name))
        .alias(name)
        for name in text
    )
    lead = re.compile(FORMULA_LEAD)
    return safe.rename({name: f"'{name}" for name in safe.columns if lead.match(name)})


def read_artifact(path: Path) -> dict[str, Any]:
    """Return the artifact document at ``path``.

    Args:
        path: The JSON file ``gspio calc-graph -o`` wrote.

    Returns:
        The parsed document.

    Raises:
        TypeError: If the file does not hold a JSON object.

    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        message = f"{path} does not hold a calculation-graph artifact"
        raise TypeError(message)
    return document


def list_nodes(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the nodes carrying a per-period value, the time axis first.

    Args:
        document: A parsed artifact.

    Returns:
        The ``shape == "list"`` nodes in artifact order, except that a node
        whose column is the framework's month axis is moved to the front so
        the frame reads left to right from its own time label.

    """
    found = [node for node in document.get("nodes", []) if node.get("shape") == "list"]
    axis = [node for node in found if node.get("column") == TIME_AXIS_COLUMN]
    rest = [node for node in found if node.get("column") != TIME_AXIS_COLUMN]
    return axis + rest


def _samples(node: dict[str, Any]) -> list[Any]:
    """Return a node's per-period values, a single-period read included.

    An export narrowed with ``--period`` states one value rather than a
    sequence. That is still a timeline; it is a timeline of one period, and
    it is normalised here rather than in three call sites.
    """
    sample = node.get("value_sample")
    if sample is None:
        return []
    if isinstance(sample, list):
        return sample
    return [sample]


def _periods(document: dict[str, Any], length: int) -> list[int]:
    """Return the period labels the values were read at.

    ``enrichment.periods`` states them where the export was narrowed to a
    subset, and null there means every period was taken -- so the labels are
    then the positions themselves.
    """
    enrichment = document.get("enrichment") or {}
    stated = enrichment.get("periods")
    if isinstance(stated, list) and len(stated) == length:
        return [int(period) for period in stated]
    return list(range(length))


def _name_the_short_nodes(columns: dict[str, list[Any]], height: int) -> None:
    """Warn of every node holding fewer values than the frame has rows.

    The frame keeps every value the file states, so it is as long as the
    longest node -- on a projection the time axis, whose ``n_periods + 1``
    values are its boundaries: the start, then the end of each period. A node
    holding one value per period instead, as a compiled rollforward's balances
    do, has one value fewer, and its last row is blank. That blank row is the
    axis's final boundary, not a period the policy reached, and a reader of the
    CSV or of a chart drawn from it cannot tell that from the file alone -- so
    the nodes and their lengths are named rather than left to be misread.
    """
    short = {
        name: len(values)
        for name, values in columns.items()
        if values and len(values) < height
    }
    if not short:
        return
    # The time axis leads the columns where the run stamped one, so the first
    # node of full length is the axis when there is one.
    longest = next(name for name, values in columns.items() if len(values) == height)
    logger.warning(
        "{count} list node(s) hold fewer values than the {height} of {longest}, "
        "so their last rows are blank: {names}. A node one value shorter than "
        "the time axis holds a value per period where the axis holds one per "
        "boundary (the start, then the end of each period): its blank last row "
        "is the axis's final boundary, not another period",
        count=len(short),
        height=height,
        longest=longest,
        names=", ".join(f"{name} ({length})" for name, length in sorted(short.items())),
    )


def timeline(document: dict[str, Any]) -> pl.DataFrame:
    """Return the declared policy's timeline as one frame.

    Args:
        document: A parsed artifact carrying an evaluation context.

    Returns:
        One row per position of the longest list node -- on a projection, the
        ``n_periods + 1`` boundaries ``month`` counts: ``period`` first, then
        one column per list node, named by the node's identifier so two
        versions of one column stay apart. A node the artifact left without
        values becomes a column of nulls rather than a missing column, and a
        node holding fewer values than the longest -- one per period beside
        an axis of boundaries -- is blank in its last rows; both are named in
        a warning.

    Raises:
        ValueError: If the artifact carries no values at all, which is what
            an export run without a policy produces, or if it carries more
            than one policy, whose enrichment is an array along the axis
            rather than one policy's run. The message says which command
            writes a file this can read.

    """
    if document.get("enrichment") is None:
        message = (
            "this artifact carries no values, so it has no timeline to read; "
            "export one with `gspio calc-graph model.py points.parquet "
            "--policy-id <id> -o graph.json`"
        )
        raise ValueError(message)
    axis = document.get("policies")
    if isinstance(axis, list) and len(axis) > 1:
        message = (
            f"this artifact carries {len(axis)} policies on its `policies` "
            "axis, and a timeline is one policy's run of periods. Each "
            "node's `value_sample` here is an array along that axis, so "
            "reading it as a projection would lay policies out under the "
            "period numbers. Export the one policy you want -- `gspio "
            "calc-graph model.py points.parquet --policies <id> -o "
            "graph.json` -- or read the axis yourself"
        )
        raise ValueError(message)
    nodes = list_nodes(document)
    columns: dict[str, list[Any]] = {node["id"]: _samples(node) for node in nodes}
    height = max((len(values) for values in columns.values()), default=0)
    empty = sorted(name for name, values in columns.items() if not values)
    if empty:
        logger.warning(
            "{count} list node(s) carry no values and are read as nulls: {names}",
            count=len(empty),
            names=", ".join(empty),
        )
    _name_the_short_nodes(columns, height)
    padded = {
        name: [*values, *([None] * (height - len(values)))]
        for name, values in columns.items()
    }
    return pl.DataFrame(
        {PERIOD_COLUMN: _periods(document, height), **padded},
        strict=False,
    )


def nodes_table(document: dict[str, Any]) -> pl.DataFrame:
    """Return one row per node: identifier, formula, shape and tier.

    Args:
        document: A parsed artifact.

    Returns:
        A frame with ``id``, ``formula``, ``shape`` and ``tier``. The formula
        is the line as the model wrote it; an input column has none, and the
        cell is null rather than an invented expression.

    """
    nodes = document.get("nodes", [])
    return pl.DataFrame(
        {
            "id": [node.get("id") for node in nodes],
            "formula": [node.get("formula") for node in nodes],
            "shape": [node.get("shape") for node in nodes],
            "tier": [node.get("tier") for node in nodes],
        },
        schema={
            "id": pl.String,
            "formula": pl.String,
            "shape": pl.String,
            "tier": pl.String,
        },
    )


def render(frame: pl.DataFrame, form: str) -> str:
    """Return the frame written in the form asked for.

    Args:
        frame: What to write.
        form: ``table`` for the readable grid, ``csv`` for a spreadsheet or a
            later read, ``json`` for a row-per-object document.

    Returns:
        The rendered text, newline-terminated.

    """
    if form == "csv":
        return spreadsheet_safe(frame).write_csv()
    if form == "json":
        return json.dumps(frame.to_dicts(), indent=2, default=str) + "\n"
    with pl.Config(tbl_rows=-1, tbl_cols=-1):
        return f"{frame}\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write a timeline or a nodes table read from an artifact.

    Args:
        argv: Command-line arguments, the program name excluded.

    Returns:
        The process exit status: 0 where the artifact could be read, 1 where
        it carries no values to read.

    """
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description=(
            "Read one declared policy's timeline, or the node list, out of a "
            "calculation-graph artifact. Reads values the file states; "
            "computes no model number."
        ),
    )
    parser.add_argument("artifact", type=Path, help="the artifact JSON to read")
    parser.add_argument(
        "--what",
        choices=("timeline", "nodes"),
        default="timeline",
        help="the declared policy's per-period frame, or the node list",
    )
    parser.add_argument(
        "--format",
        dest="form",
        choices=("table", "csv", "json"),
        default="table",
        help="how to write it (default: table)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write to this file instead of standard output",
    )
    args = parser.parse_args(argv)

    document = read_artifact(args.artifact)
    try:
        frame = timeline(document) if args.what == "timeline" else nodes_table(document)
    except ValueError as refusal:
        logger.error(str(refusal))
        return 1
    text = render(frame, args.form)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
        logger.info("wrote {rows} rows to {path}", rows=frame.height, path=args.output)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
