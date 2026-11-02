# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which storage every basis in a directory of exported artifacts takes, and why.

A report rather than a test: the artifacts are models of your own, exported
with ``gspio``, and none of them is in this repository -- a suite that read
them would fail on a machine that has none. What this answers is an open
question -- the fallback's cost was priced, and nothing said
whether any basis an actuary has actually registered pays it.

```
.venv/bin/python -m tests.fixtures.storage_census DIRECTORY
```

``DIRECTORY`` holds one subdirectory per model, and each of those an
``artifacts/`` directory of ``*.executable.json`` exports. There is no
default: the census reads exactly the directory it is given. Each line names
the artifact, the entry, its key columns, the storage the decision gives it,
and the numbers the decision turned on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gaspatchio_jax.interning import Dictionary
from gaspatchio_jax.tables import Basis, Grid, build

__all__ = ["census", "report"]


def _join_keys(document: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    """Return each right side's key names and the columns it brings, by digest.

    A join's key is on the node rather than in the payload (11.1.2), so the
    payload alone does not say which of its columns select and which arrive.
    """
    found: dict[str, tuple[str, list[str]]] = {}
    for node in document.get("nodes") or []:
        tree = node.get("expr")
        if not isinstance(tree, dict) or tree.get("name") != "join":
            continue
        attrs = tree.get("attrs") or {}
        digest = str(attrs.get("right_fingerprint"))
        written = str(attrs.get("on") or "")
        held = found.setdefault(digest, (written, []))
        held[1].append(str(node.get("column")))
    return found


def _named(written: str) -> tuple[str, ...]:
    """Return the right side's key names out of a join's ``on`` attribute."""
    left, _, right = written.partition("=")
    return tuple(name.strip() for name in (right or left).split(",") if name.strip())


def census(artifact: Path) -> list[str]:
    """Return one line per basis in one artifact, or one line saying why none."""
    try:
        document = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError) as unreadable:
        return [f"{artifact.name}: unreadable ({unreadable})"]
    joins = _join_keys(document)
    lines: list[str] = []
    for entry in document.get("assumptions") or []:
        payload = entry.get("payload")
        if entry["kind"] not in ("table", "join") or not isinstance(payload, dict):
            continue
        if entry["kind"] == "join":
            written, brought = joins.get(str(entry["fingerprint"]), ("", []))
            basis = Basis(
                name=str(entry["name"]),
                keys=_named(written),
                answer=brought[0] if brought else "",
            )
        else:
            basis = Basis(name=str(entry["name"]))
        lines.append(_one(artifact, entry, payload, basis))
    return lines or [f"{artifact.name}: no inline table or join payloads"]


def _one(
    artifact: Path, entry: dict[str, Any], payload: dict[str, Any], basis: Basis
) -> str:
    """Return the line for one basis: its storage, and the numbers behind it."""
    try:
        storage, note = build(payload, interning=Dictionary(), basis=basis)
    except Exception as refused:  # noqa: BLE001 -- a refusal is a census finding
        return f"{artifact.name} · {entry['name']} · refused: {refused}"
    keys = ", ".join(axis.name for axis in storage.axes)
    cells = 1
    for axis in storage.axes:
        cells *= axis.size
    kind = "dense grid" if isinstance(storage, Grid) else "sorted rows"
    density = len(payload["rows"]) / cells
    return (
        f"{artifact.name} · {entry['name']} · keys ({keys}) · "
        f"{len(payload['rows'])} rows over {cells} cells ({density:.1%}) · "
        f"{kind}" + (f" · {note}" if note else "")
    )


def report(models: Path) -> list[str]:
    """Return the census over every executable artifact under ``models``."""
    artifacts = sorted(models.glob("*/artifacts/*.executable.json"))
    if not artifacts:
        return [f"no executable artifacts under {models}"]
    lines: list[str] = []
    for artifact in artifacts:
        lines.extend(census(artifact))
    return lines


if __name__ == "__main__":
    if len(sys.argv) != 2:  # the program's name, and one directory
        sys.exit("usage: python -m tests.fixtures.storage_census DIRECTORY")
    for line in report(Path(sys.argv[1])):
        print(line)  # noqa: T201 -- this module is a report and is run as one
