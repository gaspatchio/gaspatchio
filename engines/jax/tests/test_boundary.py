# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The engine reads the artifact, and never the producer that wrote it.

Two readings of one boundary, because the boundary has two halves and each
half is invisible to the other's test. What the source *names* is the first:
an engine that imported the frame, the column proxies or the Polars lowering
would be reading the model rather than the document, and the import is where
that starts. What the run *calls* is the second: an import the source never
made could still be reached through a chain of them, and the only proof
against that is to break the producer's lowering and watch a run finish.

Polars itself is not forbidden. The doors take a DataFrame in and hand one
back, which is the frame the caller is holding and the format the file door
writes; what is forbidden is computing with it -- ``pl.col`` and ``pl.Expr``
are the expression API, and an engine reaching for those is an engine asking
Polars for the answer.

Importing any of the core entry points the engine does use loads the
package initialiser, and with it the frame, column and lowering modules.
That is the interpreter's doing and not a breach: the boundary is what this
source names and what this run calls, which is what the two tests below read.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import SOURCE

# The core modules the engine's own source may name, each with the reason it
# is a reading of the document rather than of the producer. An allow-list and
# not a deny-list: a deny-list of prefixes is silently outrun by a move -- the
# formula-authoring helpers left ``gaspatchio.frame.lowering`` for
# ``gaspatchio._authoring`` and the old prefix stopped covering them. Here a
# core module the engine starts naming fails until someone adds it below and
# says why. ``from gaspatchio import x`` counts as naming ``gaspatchio.x``.
ALLOWED_CORE = {
    # The public seam every engine is written against: discovery, the protocol,
    # the report, and the format an engine reads a document through.
    "gaspatchio.engines": "engine registration",
    "gaspatchio.engines.protocol": "the engine protocol, sinks and results",
    "gaspatchio.engines.report": "refusals and the run report",
    "gaspatchio.engines.format": "nodes, vocabulary, reader, identity checks",
    # The aggregators a fold on the device answers into: the core's
    # own result type, batch fold and accumulators, so the totals are the
    # Polars path's arithmetic over this engine's values rather than a copy.
    "gaspatchio.engines.aggregation": "the aggregators a fold answers into",
    # The native kernels shared with the producer (Excel-compatible functions).
    "gaspatchio._internal": "the release native extension",
}

# The producer's side, named so the self-test below can prove the allow-list
# refuses each of them -- including the ones that moved out of old prefixes.
PRODUCER = (
    "gaspatchio.frame.base",
    "gaspatchio.frame.lowering.polars",
    "gaspatchio.column",
    "gaspatchio._authoring.emit",
    "gaspatchio._authoring.escape",
    "gaspatchio.scenarios",
    # The format's private homes: an engine reads them through
    # gaspatchio.engines.format, never directly, so that this engine stands
    # where an engine written outside this repository would.
    "gaspatchio._semantic.ir",
    "gaspatchio.frame.graph.op_json",
    "gaspatchio.frame.graph.fingerprint",
)

# The two spellings that make a Polars import into a Polars calculation.
EXPRESSION_API = ("pl.col(", "pl.Expr")


def _named_modules(tree: ast.Module) -> set[str]:
    """Return every module name an import statement in ``tree`` names."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "gaspatchio":
                found.update(f"gaspatchio.{alias.name}" for alias in node.names)
            else:
                found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _unlisted_core(names: set[str]) -> list[str]:
    """Return the core modules in ``names`` the allow-list does not name."""
    return sorted(
        name
        for name in names
        if (name == "gaspatchio" or name.startswith("gaspatchio."))
        and name not in ALLOWED_CORE
    )


def test_the_engine_s_source_names_only_listed_core_modules() -> None:
    walked = 0
    for path in sorted(Path(SOURCE).rglob("*.py")):
        walked += 1
        text = path.read_text(encoding="utf-8")
        offending = _unlisted_core(_named_modules(ast.parse(text)))
        assert not offending, (path, offending)
        for spelling in EXPRESSION_API:
            assert spelling not in text, (path, spelling)
    assert walked >= 1


def test_the_allow_list_refuses_the_producer_wherever_it_lives() -> None:
    for name in PRODUCER:
        assert _unlisted_core({name}) == [name], name
    tree = ast.parse("from gaspatchio import ActuarialFrame\nimport gaspatchio\n")
    assert _unlisted_core(_named_modules(tree)) == [
        "gaspatchio",
        "gaspatchio.ActuarialFrame",
    ]


def test_every_listed_core_module_is_still_named() -> None:
    named: set[str] = set()
    for path in Path(SOURCE).rglob("*.py"):
        named |= _named_modules(ast.parse(path.read_text(encoding="utf-8")))
    assert set(ALLOWED_CORE) <= named, sorted(set(ALLOWED_CORE) - named)


def test_producer_lowering_is_never_called_during_artifact_execution(
    monkeypatch,
    tiny_document,
) -> None:
    import gaspatchio.frame.lowering.polars as producer
    from gaspatchio.engines import engine_named
    from gaspatchio.engines.protocol import FrameSink

    def trip(*_args: object, **_kwargs: object) -> None:
        message = "the engine reached the producer's lowering"
        raise AssertionError(message)

    monkeypatch.setattr(producer, "lower_polars", trip)
    result = engine_named("jax").run(
        tiny_document.document, tiny_document.inputs, FrameSink()
    )
    assert result.columns.height == tiny_document.inputs.height
