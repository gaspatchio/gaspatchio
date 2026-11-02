# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Decides a model by the graph its files rebuild, for `gspio verify --model`.
# ABOUTME: Runs the rebuild in a fresh interpreter and names each line that moved.
"""Whether the files in hand rebuild the graph an audit file records.

A file's sha256 says whether the file moved. It cannot say whether the
numbers did: a model reads values from places no stamp holds -- a scalar
taken out of a parameter file with ``.item()``, a JSON config, an environment
variable, a module imported through ``sys.path`` from outside the model's
folder, a scenario plan's shock factor -- and each of those moves a formula
while every recorded file still agrees. What does hold all of them is the
graph: a value read at build time is a literal in the formula that reads it,
and the formula's fingerprint moves with it.

So ``verify --model`` builds the graph again. The model is imported and run
over the policy data given -- or, for a scenario plan's record, the plan
given is composed over it -- exactly as ``gspio calc-graph`` builds the frame
it exports, without collecting it, and the graph is fingerprinted. Where the
fingerprint is the one recorded, the files given build the model the record
is an account of; where it is not, each node whose own fingerprint moved is
named with its formula and its line, since that line is where the moved
input entered.

**The rebuild runs the model's own code, in this environment.** It needs the
files the model reads where the model reads them, it reads this process's
environment variables and installed packages, and it runs in a fresh
interpreter so that nothing an earlier import left in this one -- a cached
module, a registered table -- is read in place of the files. A model that
cannot be rebuilt here leaves the question open, naming the error. **A
calculation that hands the engine a Python function** (``map_batches``,
``map_elements``) **or a compiled plugin** is fingerprinted by what it calls,
not by what the function does, so a value read inside one moves numbers with
the graph unmoved: such a line holds the question open, named, even where
the graph agrees.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio.engines.compare import Verdict

__all__ = ["rebuilt_decision"]


# How many moved lines a sentence names before it counts the rest.
_NAMED: Final[int] = 6

# What the verdict is relative to, said on every line the rebuild decides.
_HERE: Final[str] = (
    "in this environment -- this Python, its installed packages and this "
    "process's environment variables, and the files the model reads where "
    "it reads them"
)


@dataclass(frozen=True, slots=True)
class _Line:
    """One node of a graph, as the rebuild and the record each state it."""

    node_id: str
    formula: str | None
    location: str | None


def rebuilt_decision(
    document: Mapping[str, Any],
    *,
    model: Path,
    model_points: Path | None,
    scenarios: Path | None,
) -> tuple[Verdict, str]:
    """Return what the graph the files build says of the recorded one.

    Args:
        document: The audit file.
        model: The model source file given.
        model_points: The policy data file given, or None.
        scenarios: The scenario plan's run script given, or None.

    Returns:
        The outcome and the sentence saying why.

    """
    stated = document.get("graph_fingerprint")
    if not isinstance(stated, str):
        return _held_open(
            "The audit file states no graph_fingerprint, so there is no graph "
            "to rebuild against.",
        )
    if model_points is None:
        return _held_open(
            f"{model.name}'s graph is rebuilt by running the model over the "
            "policy data it was run over, and none was given. Give the policy "
            "data with --model-points (model_points=) and the graph is rebuilt "
            "and decides.",
        )
    planned = _a_plan_is_recorded(document)
    if planned and scenarios is None:
        return _held_open(
            "The audit file is a scenario plan's record (model.scenarios names "
            "the plan's run script), and its graph is the plan composed over "
            "the policy data, so the model alone does not rebuild it. Give the "
            "run script with --scenarios (scenarios=) and the graph is rebuilt "
            "through the plan.",
        )
    answer = _rebuild(model, model_points, scenarios)
    error = answer.get("error")
    if isinstance(error, str) or not isinstance(answer.get("nodes"), dict):
        said = error if isinstance(error, str) else "it answered nothing"
        return _held_open(
            f"{model.name} could not be rebuilt here ({said}), so whether these "
            "files build the graph the audit file records could not be checked. "
            "The rebuild runs the model's own code over the policy data given, "
            f"{_HERE}.",
        )
    return _compared(document, stated, answer, model=model, scenarios=scenarios)


def _held_open(detail: str) -> tuple[Verdict, str]:
    """Return a line the rebuild could not decide, and why."""
    return "indeterminate", detail


def _agreed(detail: str) -> tuple[Verdict, str]:
    """Return a line the rebuild decided in the record's favour, and how."""
    return "agree", detail


def _a_plan_is_recorded(document: Mapping[str, Any]) -> bool:
    """Return whether the audit file's model block names a scenario plan."""
    block = document.get("model")
    return isinstance(block, dict) and isinstance(block.get("scenarios"), dict)


def _rebuild(model: Path, model_points: Path, scenarios: Path | None) -> dict[str, Any]:
    """Return the graph these files build, from a fresh interpreter.

    Started from this process's own executable and environment, with the
    directory this package was imported from put first on its path, so the
    rebuild runs the same gaspatchio over the same packages and reads the
    same environment variables -- and none of this process's state.
    """
    # The directory holding the gaspatchio package this module was loaded
    # from: frame/graph/<this file> sits three packages down.
    root = str(Path(__file__).resolve().parents[3])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (root, env.get("PYTHONPATH")) if part
    )
    with tempfile.TemporaryDirectory(prefix="gaspatchio-rebuild-") as folder:
        # Bytecode is read from and written to a cache of the rebuild's own:
        # a ``__pycache__`` beside the model is valid while a file keeps its
        # size and its modification second, so an edit that kept both would
        # be rebuilt as the code it replaced.
        env["PYTHONPYCACHEPREFIX"] = str(Path(folder) / "bytecode")
        request = Path(folder) / "request.json"
        answer = Path(folder) / "answer.json"
        request.write_text(
            json.dumps(
                {
                    "model": str(model.resolve()),
                    "model_points": str(model_points.resolve()),
                    "scenarios": None
                    if scenarios is None
                    else str(scenarios.resolve()),
                }
            ),
            encoding="utf-8",
        )
        done = subprocess.run(  # noqa: S603 — a fixed argument list, run without a shell
            [sys.executable, "-m", "gaspatchio._rederive", str(request), str(answer)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if answer.is_file():
            read: dict[str, Any] = json.loads(answer.read_text(encoding="utf-8"))
            return read
    said = (done.stderr or "").strip().splitlines()
    return {
        "error": said[-1]
        if said
        else f"the rebuild exited {done.returncode} and said nothing"
    }


def _compared(
    document: Mapping[str, Any],
    stated: str,
    answer: dict[str, Any],
    *,
    model: Path,
    scenarios: Path | None,
) -> tuple[Verdict, str]:
    """Return the outcome of the rebuilt graph held against the recorded one."""
    built = str(answer.get("graph_fingerprint"))
    rebuilt_nodes: dict[str, dict[str, Any]] = answer["nodes"]
    recorded = {
        str(node.get("id")): node
        for node in document.get("nodes") or ()
        if isinstance(node, dict)
    }
    through = (
        f"composed through {scenarios.name} over the policy data given"
        if scenarios is not None
        else "run over the policy data given"
    )
    if built != stated:
        return "disagree", _moved(
            recorded,
            rebuilt_nodes,
            stated=stated,
            built=built,
            model=model,
            through=through,
        )
    opaque = [
        (
            _line_of(recorded.get(node_id), rebuilt, node_id, model),
            str(rebuilt["opaque"]),
        )
        for node_id, rebuilt in rebuilt_nodes.items()
        if rebuilt.get("opaque")
    ]
    if opaque:
        named = "; ".join(
            f"{_said(line)} hands the engine {what}" for line, what in opaque
        )
        return _held_open(
            f"{model.name}, {through}, rebuilds {stated}, the graph the audit "
            f"file records, {_HERE}. But {named}: a fingerprint reads what such "
            "a line calls, not what the function does, so a value read inside "
            "it moves figures with the graph unmoved. Write the line in the "
            "framework's own expressions and it is held.",
        )
    return _agreed(
        f"{model.name}, {through}, rebuilds {stated}, the graph the audit file "
        f"records, {_HERE}.",
    )


def _moved(  # noqa: PLR0913 -- the two graphs, and the three things a sentence names
    recorded: Mapping[str, Mapping[str, Any]],
    rebuilt: dict[str, dict[str, Any]],
    *,
    stated: str,
    built: str,
    model: Path,
    through: str,
) -> str:
    """Say which lines moved between the recorded graph and the rebuilt one."""
    own = [
        node_id
        for node_id, node in recorded.items()
        if node_id in rebuilt
        and node.get("local_fingerprint") != rebuilt[node_id].get("local_fingerprint")
    ]
    added = [node_id for node_id in rebuilt if node_id not in recorded]
    dropped = [node_id for node_id in recorded if node_id not in rebuilt]
    inherited = sum(
        1
        for node_id, node in recorded.items()
        if node_id in rebuilt
        and node_id not in own
        and node.get("fingerprint") != rebuilt[node_id].get("fingerprint")
    )
    parts = [
        (
            f"{model.name}, {through}, builds {built}, and the audit file "
            f"records {stated}: these files do not build the model the audit "
            f"file is an account of, {_HERE}."
        )
    ]
    if own:
        parts.append(
            "The calculation moved at "
            + _listed(
                [
                    _said(_line_of(recorded[node_id], rebuilt[node_id], node_id, model))
                    for node_id in own
                ]
            )
            + ", which is where an input that moved entered"
            + (
                f"; {inherited} more moved only through what they read."
                if inherited
                else "."
            )
        )
    if added:
        parts.append(
            "These files write "
            + _listed(
                [
                    _said(_line_of(None, rebuilt[node_id], node_id, model))
                    for node_id in added
                ]
            )
            + ", which the audit file does not hold."
        )
    if dropped:
        parts.append(
            "The audit file holds "
            + _listed(
                [
                    _said(_line_of(recorded[node_id], None, node_id, model))
                    for node_id in dropped
                ]
            )
            + ", which these files no longer write."
        )
    if not (own or added or dropped):
        parts.append(
            "No line's own calculation moved: what differs is an assumption, a "
            "column of handed-over values or a hole the graph's fingerprint "
            "folds in beside its lines."
        )
    return " ".join(parts)


def _line_of(
    recorded: Mapping[str, Any] | None,
    rebuilt: Mapping[str, Any] | None,
    node_id: str,
    model: Path,
) -> _Line:
    """Return a node as a reader finds it: the record's words, else the rebuild's."""
    for source in (recorded, rebuilt):
        if source is None:
            continue
        formula = source.get("formula")
        location = source.get("source_location")
        if isinstance(location, str) or isinstance(formula, str):
            return _Line(
                node_id,
                formula if isinstance(formula, str) else None,
                _where(location, model) if isinstance(location, str) else None,
            )
    return _Line(node_id, None, None)


def _where(location: str, model: Path) -> str:
    """Write a location the way the record writes one: never as an absolute path."""
    if not PurePosixPath(location).is_absolute() and not Path(location).is_absolute():
        return location
    path, _, line = location.rpartition(":")
    try:
        relative = Path(path).resolve().relative_to(model.resolve().parent)
    except ValueError:
        return f"{Path(path).name}:{line}"
    return f"{relative.as_posix()}:{line}"


def _said(line: _Line) -> str:
    """Name one line: its node, where it was written and what it says."""
    where = f" ({line.location})" if line.location else ""
    formula = " ".join(line.formula.split()) if line.formula else None
    if formula and len(formula) > 80:  # noqa: PLR2004 - a quotation, not the whole formula
        formula = formula[:77] + "..."
    said = f": {formula}" if formula else ""
    return f"{line.node_id}{where}{said}"


def _listed(lines: list[str]) -> str:
    """Join named lines, naming the first few and counting the rest."""
    shown = lines[:_NAMED]
    rest = len(lines) - len(shown)
    joined = "; ".join(shown)
    return f"{joined}; and {rest} more" if rest else joined
