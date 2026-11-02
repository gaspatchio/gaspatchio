# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every path the architecture map names resolves in the tree it describes.

``docs/architecture.md`` is loaded into every Claude Code session at the
repository root and is the first thing an agent reads before changing the
package. Nothing in CI reads a path out of a markdown file, so when a
simplification of the package retired ``functions/vector.py`` the map went on
routing new vector work to it, and cited a ``tests/test_performance.py`` that
had never existed. Neither is a slow failure: an agent that starts from a false
map of the package writes the change in the wrong place.

This is the check that was missing. It reads the map, takes every backticked
token that names a path, and asserts the file or directory is there.

**Which tokens are paths.** The map states its own convention -- a path is
written from ``bindings/python/``, or from the repository root when it lies
outside it -- so each candidate is resolved against those two roots in that
order and has to exist under one of them. A token is a candidate when it
contains ``/`` or ends in one of the suffixes below. Everything else in
backticks is a symbol rather than a path and is skipped: ``ActuarialFrame``,
``emit.call_node``, ``Table.lookup``, ``mypy.stubtest``, ``gaspatchio._internal``
and ``run_model(model_func, df)`` all name something in the code, and a module
path written with dots is not a file path however much it looks like one.

The rule cuts both ways, and that is deliberate. A module named with dots is
unchecked here, so the map spells a file as a path when it wants the check --
``gaspatchio/_authoring/emit.py``, not ``gaspatchio._authoring.emit``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

BINDINGS_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT: Final[Path] = BINDINGS_ROOT.parents[1]
MAP_PATH: Final[Path] = BINDINGS_ROOT / "docs" / "architecture.md"

# A backticked token ending in one of these names a file even with no
# directory in front of it, so it is checked rather than taken for a symbol.
PATH_SUFFIXES: Final[tuple[str, ...]] = (
    ".py",
    ".pyi",
    ".md",
    ".rs",
    ".json",
    ".ts",
    ".toml",
    ".yml",
    ".ini",
    ".txt",
)

_BACKTICKED: Final[re.Pattern[str]] = re.compile(r"`([^`\n]+)`")


def _is_path_token(token: str) -> bool:
    """Whether a backticked token names a path rather than a symbol."""
    return "/" in token or token.endswith(PATH_SUFFIXES)


def _path_tokens(text: str) -> list[str]:
    """Every backticked path token in the map, in the order it is written."""
    return [token for token in _BACKTICKED.findall(text) if _is_path_token(token)]


def _resolves(token: str) -> bool:
    """Whether the token exists under `bindings/python/` or the repository root."""
    return (BINDINGS_ROOT / token).exists() or (REPOSITORY_ROOT / token).exists()


def test_every_path_the_architecture_map_names_exists() -> None:
    """A path the map names but the tree does not hold fails here, not in review."""
    tokens = _path_tokens(MAP_PATH.read_text(encoding="utf-8"))

    assert tokens, (
        f"{MAP_PATH} names no paths at all, which means either the map was "
        "emptied or the token rule in this module stopped matching it."
    )

    missing = sorted({token for token in tokens if not _resolves(token)})

    assert not missing, (
        "The architecture map names paths that are not in the tree:\n"
        + "\n".join(f"  - {token}" for token in missing)
        + f"\n\nEach was resolved against {BINDINGS_ROOT} and then "
        f"{REPOSITORY_ROOT}. Correct the map rather than restoring a retired "
        "module to make its sentence true."
    )
