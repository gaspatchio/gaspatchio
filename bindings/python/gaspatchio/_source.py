# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How a captured filename is rendered for someone to read.

A source location is only useful if the reader can go and look at it. Most
of the time that is a path, and it is printed as written. In a notebook it
is not: the interpreter names a cell something like
``<ipython-input-3-a1b2c3>``, which identifies the cell to the machine and
tells the person nothing. ``display_filename`` turns that into ``Jupyter
Cell 3`` -- the label the notebook itself shows on the cell.

Every reader of a calculation's source span goes through here: the
query-plan log, the calculation-graph export, and the location line on an
enriched method error.

So does every walk that looks for the line a model author wrote, for a
source span or for an error's location: :func:`is_framework_or_interpreter_file`
is the one answer to whose code a frame is running.
"""

import os
import site
import sysconfig
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

# This package's own directory, as it was imported and as it resolves, each
# ending in the platform's separator. Frame filenames come from code objects,
# which do not resolve symlinks, so both are kept. A warning the package
# raises is located past these too (``gaspatchio._warning``).
PACKAGE_DIRECTORIES: Final[tuple[str, ...]] = tuple(
    sorted(
        {
            f"{Path(__file__).parent}{os.sep}",
            f"{Path(__file__).resolve().parent}{os.sep}",
        }
    )
)

# A directory with one of these names holds installed packages wherever it
# sits, including in an interpreter this process is not running from.
_INSTALLED_PACKAGE_DIRECTORY_NAMES: Final = frozenset(
    {"site-packages", "dist-packages"}
)


def _interpreter_directories() -> list[str]:
    """Return where this interpreter keeps code that no model author wrote.

    Its standard library, both halves of it, and every directory it
    installs packages into, the user's own included. Not ``sys.prefix`` as
    a whole: on a system Python that is ``/usr``, and ``/usr/src/app`` is
    somebody's model.
    """
    paths = sysconfig.get_paths()
    found = [
        paths[key]
        for key in ("stdlib", "platstdlib", "purelib", "platlib")
        if key in paths
    ]
    getsitepackages = getattr(site, "getsitepackages", None)
    if getsitepackages is not None:
        found.extend(getsitepackages())
    getusersitepackages = getattr(site, "getusersitepackages", None)
    if getusersitepackages is not None:
        found.append(getusersitepackages())
    return found


def _containment_prefix(path: ModuleType, directory: str) -> str:
    """Return ``directory`` on ``path``'s rules, case-folded, ending in a separator."""
    normalised = str(path.normcase(path.normpath(directory)))
    separator = str(path.sep)
    return normalised if normalised.endswith(separator) else normalised + separator


@dataclass(frozen=True, slots=True)
class CodeLocations:
    """Where code that no model author wrote lives, on one platform's path rules.

    One is built for this process, for :func:`is_framework_or_interpreter_file`.
    A test builds one over ``ntpath`` to ask the same question of Windows
    paths on any machine.
    """

    # The path module whose rules apply: ``os.path``, or ``ntpath`` or
    # ``posixpath`` in a test.
    path: ModuleType
    # The framework's directories and the interpreter's, as prefixes.
    installed: tuple[str, ...]
    # The worked examples shipped under the framework's own directory.
    model_code: tuple[str, ...]

    @classmethod
    def of(
        cls,
        path: ModuleType,
        *,
        package: Iterable[str],
        interpreter: Iterable[str],
    ) -> "CodeLocations":
        """Return where ``package`` and ``interpreter`` lie, on ``path``'s rules."""
        package = list(package)
        return cls(
            path=path,
            installed=tuple(
                _containment_prefix(path, directory)
                for directory in [*package, *interpreter]
                if directory
            ),
            model_code=tuple(
                _containment_prefix(path, path.join(directory, "tutorials"))
                for directory in package
            ),
        )

    def holds_framework_or_interpreter_code(self, filename: str) -> bool:
        """Return whether code from ``filename`` is framework or interpreter code."""
        if filename.startswith("<frozen"):
            return True
        if filename.startswith("<"):
            return False
        normalised = str(self.path.normcase(filename))
        if normalised.startswith(self.model_code):
            return False
        if normalised.startswith(self.installed):
            return True
        if self.path.altsep:
            normalised = normalised.replace(self.path.altsep, self.path.sep)
        return not _INSTALLED_PACKAGE_DIRECTORY_NAMES.isdisjoint(
            normalised.split(self.path.sep)
        )


_THIS_PROCESS: Final = CodeLocations.of(
    os.path, package=PACKAGE_DIRECTORIES, interpreter=_interpreter_directories()
)

# Each filename's answer, taken once: a process meets a few dozen files and
# the capture asks about them on every assignment.
_ANSWERED: dict[str, bool] = {}


def is_framework_or_interpreter_file(filename: str) -> bool:
    """Return whether code from ``filename`` is the framework's or the interpreter's.

    The one rule every walk that looks for the model author's line follows:
    the error locators, and the capture of each calculation's source line.
    Code is the framework's or the interpreter's when its file lies under
    this package's own directory, the interpreter's standard library, or a
    directory it installs packages into; when its path passes through a
    directory named ``site-packages`` or ``dist-packages``; or when it is a
    ``<frozen ...>`` module. Paths are compared whole, on the platform's own
    case and separator rules, and never by a file's name or a fragment of
    one.

    Everything else is the user's: a model kept in ``validation.py`` or under
    a directory named ``env``; the code a notebook cell or ``exec`` runs
    (``<ipython-input-...>``, ``<string>``); the worked examples shipped
    under this package's ``tutorials``, which are model code; and an
    editable package under a virtual environment's ``src``, which is code
    somebody is editing -- the honest reading, whoever wrote it first.

    Memoised for each filename: the capture asks it on every assignment.
    """
    answer = _ANSWERED.get(filename)
    if answer is None:
        answer = _THIS_PROCESS.holds_framework_or_interpreter_code(filename)
        _ANSWERED[filename] = answer
    return answer


@dataclass(slots=True, frozen=True)
class SourceSpan:
    """Where one calculation's defining statement lives in the caller's own source.

    Captured once, at assignment time, by ``capture_source_span`` -- never
    re-derived later, since the frame that called it may already have
    returned by the time anything reads this record.
    """

    file: str
    line: int
    end_line: int
    # The enclosing scope the statement was written in, qualified through
    # any nesting (`price_policy`, `Projection.run`, `main.<locals>.helper`),
    # or None when the statement sits at module level. Never the
    # interpreter's `"<module>"` sentinel: a reader told "Function: <module>"
    # learns nothing the file and line did not already say, and every
    # renderer here reports the scope only when it is genuinely known.
    function: str | None
    # The whole statement, AST-scoped: a multi-line conditional chain is
    # captured start to end, never truncated to one physical line.
    statement: str
    # The expression's own text, as the author wrote it, from either of the
    # two statements that write ONE column with one: a `target = value`
    # assignment whose every target names a column, and a
    # `setattr(af, name, value)` call, whose value argument is the same
    # expression written through the builtin. None for anything else -- an
    # augmented assignment, a tuple target or a rebound name (each of which
    # has a value that computes no single column), or a statement no such
    # shape was found for.
    rhs: str | None
    # True when the assignment target names its column literally
    # (`af.foo = ...`, `af["foo"] = ...`); False when the target is a
    # variable or other expression (`af[name] = ...` inside a loop).
    target_literal: bool


def is_jupyter_filename(file_name: str) -> bool:
    """Return whether a captured filename came from a Jupyter notebook cell."""
    return "<ipython-input-" in file_name or "ipython-input-" in file_name


def display_filename(file_name: str) -> str:
    """Render a captured filename the way a human should read it.

    A notebook cell's filename is machine noise (``<ipython-input-3-abc>``),
    so it becomes the cell number the user can actually look at. Everything
    else is a real path and is returned as written.
    """
    if not is_jupyter_filename(file_name):
        return file_name
    if "<ipython-input-" in file_name:
        try:
            cell_part = file_name.split("<ipython-input-")[1].split(">", maxsplit=1)[0]
            cell_num = cell_part.split("-")[0]
            # Raises unless the cell part really is a number.
            int(cell_num)
        except (IndexError, ValueError):
            return "Jupyter Notebook"
        return f"Jupyter Cell {cell_num}"
    return "Jupyter Notebook"
