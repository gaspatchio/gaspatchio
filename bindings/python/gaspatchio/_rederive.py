# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Rebuilds a model's graph from the files in hand, in a process of its own.
# ABOUTME: Run by `gspio verify --model` as `python -m gaspatchio._rederive`; no import.
"""The graph a model's files build here, taken in a fresh process.

``gspio verify --model`` decides the model by rebuilding its graph: the model
file is imported, its ``main`` is run over the policy data given -- or the
scenario plan given is composed over it -- exactly as ``gspio calc-graph``
builds the frame it exports, and the graph is fingerprinted. Nothing is
collected, so no value is computed and the cost does not grow with the book.

**Why a process of its own.** A model's import runs its helpers, registers
its assumption tables and declares its accessors under their names, all in
state that outlives the call: run in the verifier's own process, the rebuild
would supersede the caller's tables and would be handed whatever module an
earlier import left in Python's cache -- a library reached through
``sys.path`` and since edited would be read as it was. A fresh interpreter,
started from this one's executable with this process's environment, reads
each file as it is now and leaves the caller's state as it was.

The answer is written as JSON to the path the caller names: the graph's
fingerprint and, for each node, its own and its whole fingerprint, the
formula and the line it was written at, and -- where its calculation hands a
Python function or a compiled plugin to the engine -- what that is, since no
fingerprint reads inside one. A model that cannot be rebuilt is answered with
the error, by its type and its message.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gaspatchio.frame.base import ActuarialFrame

__all__: list[str] = []

# The function a model file declares its calculation in, as calc-graph reads it.
_MODEL_FUNCTION = "main"

# What a calculation that hands the engine a Python function is called, and
# one that hands it a compiled plugin.
_PYTHON_FUNCTION = "a Python function (map_batches, map_elements or rolling_map)"


def _frame_of(
    model: Path, book_path: Path, scenarios: Path | None
) -> tuple[ActuarialFrame, list[str]]:
    """Return the frame calc-graph exports for these files, built and not collected.

    With the book's own columns, which the export is handed beside the frame:
    they are what tells a column the data arrived with from one nothing
    accounts for, and that difference is in the graph's fingerprint.
    """
    from gaspatchio.frame import run_model  # noqa: PLC0415 - a process of its own
    from gaspatchio.frame.base import _frame_over_the_book  # noqa: PLC0415
    from gaspatchio.frame.graph._model_files import book_from_file  # noqa: PLC0415
    from gaspatchio.frame.graph.row_identity import stamp_the_book  # noqa: PLC0415
    from gaspatchio.runner import load_model_from_path  # noqa: PLC0415

    book = book_from_file(book_path)
    stamped = stamp_the_book(book)
    if scenarios is not None:
        from gaspatchio.scenarios._graph_export import (  # noqa: PLC0415
            _composed,
            open_the_script,
        )

        declared = open_the_script(scenarios)
        frame = _composed(declared, _frame_over_the_book(stamped, mode="debug"))
        return frame, book.columns
    function = load_model_from_path(model, _MODEL_FUNCTION)
    return run_model(
        function, _frame_over_the_book(stamped, mode="debug")
    ), book.columns


def _opaque(tree: object) -> str | None:
    """Name what in an operation tree hands the engine code no fingerprint reads."""
    from gaspatchio._semantic.ir import EngineNative, walk  # noqa: PLC0415
    from gaspatchio.frame.lowering.ingress import NATIVE_REFS  # noqa: PLC0415

    if tree is None:
        return None
    for leaf in walk(tree):  # type: ignore[arg-type]
        if not isinstance(leaf, EngineNative):
            continue
        held = NATIVE_REFS.get(id(leaf))
        if held is None or held[0] is not leaf:
            continue
        found = _opaque_in_expression(held[1])
        if found is not None:
            return found
    return None


def _opaque_in_expression(expr: Any) -> str | None:  # noqa: ANN401 - a pl.Expr
    """Name a Python function or a plugin inside a Polars expression, or None."""
    try:
        plan = json.loads(expr.meta.serialize(format="json"))
    except Exception:  # noqa: BLE001 - only a Python function will not be written out
        return _PYTHON_FUNCTION
    return _opaque_in_plan(plan)


def _opaque_in_plan(node: object) -> str | None:
    """Walk a serialised Polars plan for a Python function or a plugin call."""
    children: list[object]
    if isinstance(node, list):
        children = list(node)
    elif isinstance(node, dict):
        found = next(
            (named for kind, body in node.items() if (named := _named(kind, body))),
            None,
        )
        if found is not None:
            return found
        children = list(node.values())
    else:
        return None
    return next(
        (found for child in children if (found := _opaque_in_plan(child))), None
    )


def _named(kind: str, body: object) -> str | None:
    """Name one plan node a fingerprint cannot read inside, or None."""
    if kind == "AnonymousFunction":
        return _PYTHON_FUNCTION
    if kind != "Function" or not isinstance(body, dict):
        return None
    function = body.get("function")
    plugin = function.get("FfiPlugin") if isinstance(function, dict) else None
    if isinstance(plugin, dict):
        return f"the compiled plugin function {plugin.get('symbol')!r}"
    return None


def rebuilt(model: Path, book_path: Path, scenarios: Path | None) -> dict[str, Any]:
    """Return the graph these files build here, as the JSON the caller reads.

    The graph is the one an export of the frame writes -- folded with the
    book's columns, by the exporter calc-graph uses -- with no values: the
    frame is never collected, so nothing is computed, and the document's
    fingerprints are the answer.
    """
    from gaspatchio.frame.graph import GraphExporter  # noqa: PLC0415

    af, columns = _frame_of(model, book_path, scenarios)
    document = json.loads(
        GraphExporter(af, data_columns=columns).export(
            include_source=False,
            include_tables=False,
            versions="withheld",
            seal=False,
        )
    )
    trees = af.graph._graph.op_trees  # noqa: SLF001 - the trees the nodes were folded from
    nodes: dict[str, dict[str, Any]] = {}
    for node in document.get("nodes", ()):
        node_id = str(node.get("id"))
        nodes[node_id] = {
            "local_fingerprint": node.get("local_fingerprint"),
            "fingerprint": node.get("fingerprint"),
            "formula": node.get("formula"),
            "source_location": node.get("source_location"),
            "opaque": _opaque(trees.get(node_id)),
        }
    return {"graph_fingerprint": document.get("graph_fingerprint"), "nodes": nodes}


def main(argv: list[str]) -> int:
    """Answer one request: ``<request.json> <answer.json>``."""
    request = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    answer_path = Path(argv[1])
    try:
        answer = rebuilt(
            Path(request["model"]),
            Path(request["model_points"]),
            None if request.get("scenarios") is None else Path(request["scenarios"]),
        )
    except BaseException as failure:  # noqa: BLE001 - every way a model fails to build is the answer
        first = str(failure).strip().splitlines()
        answer = {"error": f"{type(failure).__name__}: {first[0] if first else ''}"}
    answer_path.write_text(json.dumps(answer), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
