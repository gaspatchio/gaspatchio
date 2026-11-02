# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The shipped tutorials and the skills import gaspatchio only by public names.

``gspio tutorial init`` copies the tutorials into a user's own directory, and
the skills' code examples are what an assistant writes into a user's model.
Whatever they import, a user's model ends up importing. An underscore module
(``gaspatchio.rollforward._compile``, ``gaspatchio.assumptions._dimensions``)
is internal and may move without notice; every name the tutorials need is
published by a public module (``gaspatchio.compile_rollforward``,
``gaspatchio.assumptions.DataDimension``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import gaspatchio

TUTORIALS = Path(gaspatchio.__file__).parent / "tutorials"
# bindings/python/tests/ -> the repository root, where the skills live.
SKILLS = Path(__file__).resolve().parents[3] / "skills"

# `from gaspatchio.x import a, b as c`, including the parenthesised form that
# spans several lines.
_FROM = re.compile(
    r"^[ \t]*from[ \t]+(gaspatchio(?:\.\w+)*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)",
    re.MULTILINE,
)
# `import gaspatchio.x`, alone or in a list: `import polars, gaspatchio.x as y`.
_IMPORT = re.compile(r"^[ \t]*import[ \t]+([^\n]+)", re.MULTILINE)
_COMMENT = re.compile(r"#[^\n]*")


def _entries(listing: str) -> list[str]:
    """Return the dotted names an import list names, without aliases or comments."""
    listing = _COMMENT.sub("", listing).strip().strip("()")
    return [
        entry.split()[0]
        for entry in listing.replace("\\", " ").split(",")
        if entry.strip()
    ]


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _private_imports(text: str) -> list[str]:
    """Return every gaspatchio import in the text that reaches past a public name."""
    found = [
        f"{match.group(1)}.{name}"
        for match in _FROM.finditer(text)
        for name in _entries(match.group(2))
        if any(_is_private(part) for part in [*match.group(1).split(".")[1:], name])
    ]
    found.extend(
        module
        for match in _IMPORT.finditer(text)
        for module in _entries(match.group(1))
        if module.split(".")[0] == "gaspatchio"
        and any(_is_private(part) for part in module.split(".")[1:])
    )
    return found


def _sources() -> list[Path]:
    files = sorted(TUTORIALS.rglob("*.py")) + sorted(TUTORIALS.rglob("*.md"))
    files += sorted(SKILLS.rglob("*.py")) + sorted(SKILLS.rglob("*.md"))
    return [path for path in files if "__pycache__" not in path.parts]


def test_the_walk_reaches_the_tutorials_and_the_skills() -> None:
    sources = _sources()
    assert any(TUTORIALS in path.parents for path in sources)
    assert any(SKILLS in path.parents for path in sources)


@pytest.mark.parametrize(
    "text",
    [
        "from gaspatchio.rollforward._compile import compile_rollforward\n",
        "    from gaspatchio.assumptions._dimensions import DataDimension\n",
        "from gaspatchio.assumptions import (\n    Table,\n    _api,  # internal\n)\n",
        "import gaspatchio._internal\n",
        "import polars as pl, gaspatchio.scenarios._audit as audit\n",
    ],
)
def test_an_underscore_import_is_caught(text: str) -> None:
    assert _private_imports(text)


def test_a_public_import_passes() -> None:
    text = (
        "from gaspatchio import ActuarialFrame, compile_rollforward, __version__\n"
        "from gaspatchio.assumptions import (\n"
        "    DataDimension,  # the default\n"
        "    Table,\n"
        ")\n"
        "import gaspatchio.scenarios as scenarios, polars\n"
        "import _thread\n"
    )
    assert _private_imports(text) == []


def test_tutorials_and_skills_import_only_public_names() -> None:
    found = {
        str(path): imports
        for path in _sources()
        if (imports := _private_imports(path.read_text(encoding="utf-8")))
    }
    assert not found, (
        "These files import gaspatchio through an underscore name; import the "
        f"public name instead: {found}"
    )
