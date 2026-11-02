# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Declared example-collection paths must continue to select real source files."""

import tomllib
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((PROJECT / "pyproject.toml").read_text())
PREFIX = "--gp-docstring-paths="
PATHS = [
    option.removeprefix(PREFIX)
    for option in CONFIG["tool"]["pytest"]["ini_options"]["addopts"]
    if option.startswith(PREFIX)
]


@pytest.mark.parametrize("pattern", PATHS)
def test_declared_docstring_collection_path_exists(pattern: str) -> None:
    """A moved example must not silently vanish from ordinary test runs."""
    assert any(path.is_file() for path in PROJECT.glob(pattern)), (
        f"The configured example path {pattern!r} selects no source files. "
        "Update its declared location when moving the examples."
    )


# Modules whose docstrings carry fenced examples that the example plugin has
# never collected. Recorded, not endorsed: each predates the 2026-09-23
# simplification (``_semantic/operations.py`` is ``frame/operations.py``,
# whose fenced blocks are the specifications ``_generated_proxy.py`` is built
# from, and that file IS collected). Shrink this list; never grow it to make
# a moved example pass.
NEVER_COLLECTED = frozenset(
    {
        "gaspatchio/_semantic/operations.py",
        "gaspatchio/accessors/projection_frame.py",
        "gaspatchio/cli.py",
        "gaspatchio/errors/models.py",
        "gaspatchio/examples/docstrings/formatting.py",
        "gaspatchio/examples/docstrings/models.py",
        "gaspatchio/frame/base.py",
        "gaspatchio/frame/lowering/_polars/expressions.py",
        "gaspatchio/functions/conditional.py",
        "gaspatchio/scenarios/_config.py",
        "gaspatchio/scenarios/_sensitivity.py",
        "gaspatchio/scenarios/_with_scenarios.py",
        "gaspatchio/scenarios/shocks.py",
    }
)


def _modules_with_fenced_examples() -> set[str]:
    """Return every package module whose source carries a fenced Python block."""
    return {
        path.relative_to(PROJECT).as_posix()
        for path in (PROJECT / "gaspatchio").rglob("*.py")
        if "__pycache__" not in path.parts
        and "tutorials" not in path.parts
        and "```python" in path.read_text(encoding="utf-8")
    }


def test_no_module_with_examples_escapes_collection() -> None:
    """Moving documented members into a new file must move its examples too.

    When ``assumptions/_api.py`` was split, the documented ``Table.name``,
    ``Table.to_dataframe`` and ``Table.validate_lookup`` went to ``_data.py``,
    which no configured path selected: 16 example and structure checks stopped
    running while the path test above still passed, because the old path
    still matched a file.
    """
    collected = {
        path.relative_to(PROJECT).as_posix()
        for pattern in PATHS
        for path in PROJECT.glob(pattern)
    }
    escaped = _modules_with_fenced_examples() - collected - NEVER_COLLECTED
    assert escaped == set(), (
        f"{sorted(escaped)} carry fenced examples no configured "
        "--gp-docstring-paths selects. Add each to pyproject.toml."
    )


def test_the_never_collected_list_names_only_real_uncollected_modules() -> None:
    stale = NEVER_COLLECTED - _modules_with_fenced_examples()
    assert stale == set(), f"{sorted(stale)} no longer carry examples; drop them."
