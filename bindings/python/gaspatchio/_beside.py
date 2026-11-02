# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Imports a model file as `python model.py` would, its directory importable.
# ABOUTME: Shared by every gspio command that loads a model or a run script by path.
"""A model file imported with the files beside it importable.

A modeller who keeps a helper beside the model -- ``norm_accessors.py``
registering an accessor, ``assumptions.py`` building the tables, the
``model.py`` a run script imports -- writes ``import norm_accessors`` at the
top of the model, and ``python model.py`` runs it, because Python puts a
script's own directory first on ``sys.path``. A command that loads the file
by path gets no such entry, so the same line fails with
``ModuleNotFoundError`` on a model that has always worked. Every command that
loads a model file by path therefore imports it inside
:func:`importable_beside`, and the file resolves its siblings exactly as it
does when it is run.

**Nothing of it outlives the import.** The directory goes on the path for the
import and comes off afterwards, so the next model loaded in the same process
does not find this one's files by accident. Python keeps every module it
imported, though, under its bare name: a second model whose own
``helpers.py`` sits beside it would be handed the first model's ``helpers``
from that cache, and would run the first model's code without a word. So
each module brought in from beside a model is remembered with the directory
it came from, and when a model in another directory holds a file of the same
name, the remembered one is let go before that model imports. **A model
loaded again from its own directory lets go of its own modules too**, so they
run again with it: a helper edited between two runs in one notebook answers
as the file now reads, as the model file itself does, and as the record --
which stamps the files on disk -- says it does. An accessor the helper
declares is declared again by the same class statement in the same module,
and takes the earlier definition's place.

What the import does not cover is an import made later, inside ``main()``,
of a sibling the module never imported at its top: by then the directory is
off the path again. Import helpers at the top of the model file, as the
skills show.

**Which of those files the model imports is read off its text.** An audit
record names the model file by the hash of its bytes, and a helper the model
imports is as much the model as the file is: an edited ``norm_accessors.py``
moves every figure the accessor computes and no byte of ``model.py``.
:func:`local_modules` is the list the record stamps -- every file beside the
model, or in a package beside it, that the model's import statements resolve
to, and those files' own, followed until nothing new is reached. It is read
off the source rather than off what this process happens to have imported,
because a model is exported from Python as often as from ``gspio``, and the
two routes must write one account of one model: a process that imported the
model itself, without :func:`importable_beside`, has recorded nothing, and
two models sharing a directory share its cache. A name resolves the way
:func:`importable_beside` makes it resolve, against the model's own directory
and nowhere else, so an installed package or the standard library is never
listed.

**What it imports from outside its directory is the other half of that
walk.** An installed package the model imports -- an in-house
``acme_actuarial`` as much as ``numpy`` -- moves figures exactly as a helper
does, and is no file beside the model to stamp. :func:`imported_from_outside`
names each such top-level module, off the same import statements of the
model and of every local module it reaches, the standard library and
Python's own built-in and frozen modules left out; the record states the
installed distribution behind each name, and its version.
"""

from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from importlib.machinery import (
    BYTECODE_SUFFIXES,
    EXTENSION_SUFFIXES,
    SOURCE_SUFFIXES,
    FrozenImporter,
    PathFinder,
)
from importlib.util import cache_from_source
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

__all__ = [
    "importable_beside",
    "imported_from_outside",
    "loads_by_path",
    "local_modules",
]

# Each module a model's import brought in from beside it, by the name Python
# caches it under, with the directory it came from.
_IMPORTED_BESIDE: Final[dict[str, Path]] = {}


@contextmanager
def importable_beside(source: Path) -> Iterator[None]:
    """Make the files beside ``source`` importable for the duration of the block.

    Args:
        source: The model file, or run script, about to be imported.

    Yields:
        Nothing; the block is where the file is imported.

    """
    directory = Path(source).resolve().parent
    _forget_what_this_directory_shadows(directory)
    _forget_this_directory_s_own(directory)
    _forget_the_bytecode(Path(source))
    entry = str(directory)
    already = set(sys.modules)
    added = entry not in sys.path
    if added:
        sys.path.insert(0, entry)
    try:
        yield
    finally:
        if added and entry in sys.path:
            sys.path.remove(entry)
        for name in set(sys.modules) - already:
            module = sys.modules.get(name)
            if module is not None and _came_from(directory, name, module):
                _IMPORTED_BESIDE[name] = directory


def _forget_what_this_directory_shadows(directory: Path) -> None:
    """Let go of an earlier model's module where this directory holds its own."""
    for name, came_from in list(_IMPORTED_BESIDE.items()):
        if came_from == directory:
            continue
        top = name.partition(".")[0]
        if PathFinder.find_spec(top, [str(directory)]) is None:
            continue
        sys.modules.pop(name, None)
        del _IMPORTED_BESIDE[name]


def _forget_this_directory_s_own(directory: Path) -> None:
    """Let go of every module imported from ``directory``, so the import runs it again.

    Whichever way it was imported -- by an earlier load of a model here, or by
    the caller's own ``import helpers`` in a notebook whose working directory
    this is -- a module cached from a file beside the model is that file as it
    read when it was first imported, and the model about to run reads it as
    it reads now. Only names this directory holds a file or a package for are
    looked at, so the walk over the cache is a set lookup per module.
    """
    held = _names_held_in(directory)
    if not held:
        return
    for name, module in list(sys.modules.items()):
        if name.partition(".")[0] not in held or module is None:
            continue
        if _came_from(directory, name, module):
            sys.modules.pop(name, None)
            _IMPORTED_BESIDE.pop(name, None)
            origin = getattr(module, "__file__", None)
            if isinstance(origin, str):
                _forget_the_bytecode(Path(origin))


def _forget_the_bytecode(source: Path) -> None:
    """Remove the cached bytecode of a source file about to be imported again.

    Python reuses ``__pycache__/<name>.pyc`` while the source's modification
    time, in whole seconds, and its size are what the cache recorded -- so an
    edit that keeps the file's length, saved within the second of the last
    import (``RATE = 0.01`` to ``0.02``), is run as the old code. The cache
    is only a cache: removing it costs one compile and makes the import read
    the file as it is now.
    """
    if source.suffix != ".py":
        return
    try:
        Path(cache_from_source(str(source))).unlink(missing_ok=True)
    except (OSError, NotImplementedError, ValueError):
        return


def _names_held_in(directory: Path) -> frozenset[str]:
    """Return the top-level module names held by the files in ``directory``."""
    suffixes = (*SOURCE_SUFFIXES, *BYTECODE_SUFFIXES, *EXTENSION_SUFFIXES)
    try:
        entries = list(directory.iterdir())
    except OSError:
        return frozenset()
    names: set[str] = set()
    for entry in entries:
        if entry.is_dir():
            names.add(entry.name)
        elif entry.name.endswith(suffixes):
            names.add(entry.name.partition(".")[0])
    return frozenset(names)


def _came_from(directory: Path, name: str, module: ModuleType) -> bool:
    """Return whether ``module`` is a file, or a package, sitting in ``directory``."""
    top = name.partition(".")[0]
    spec = getattr(module, "__spec__", None)
    origins = [
        getattr(module, "__file__", None),
        *(getattr(spec, "submodule_search_locations", None) or ()),
    ]
    for origin in origins:
        if not isinstance(origin, str):
            continue
        path = Path(origin).resolve()
        if path.parent == directory and path.name.partition(".")[0] == top:
            return True
        if path.is_relative_to(directory / top):
            return True
    return False


def local_modules(source: Path) -> tuple[Path, ...]:
    r"""Return every file beside ``source`` that its imports resolve to.

    The model's import statements are read off its text -- wherever they
    stand, at the top or inside a function -- and each name is resolved as
    :func:`importable_beside` makes Python resolve it: against the model's own
    directory. A name that directory does not hold, the standard library's
    and an installed package's alike, is not the model's and is not listed;
    a name Python answers before it looks at any directory, a built-in or a
    frozen module, is not either. Each file reached is read the same way, so
    a helper's own helpers are listed too, and a package is listed by every
    file of it the import runs: its ``__init__.py`` and the submodule named.

    Args:
        source: The model file.

    Returns:
        The files, resolved and sorted, ``source`` itself never among them.
        Empty where the model imports nothing from beside itself.

    Examples:
        >>> import shutil
        >>> import tempfile
        >>> from pathlib import Path
        >>> folder = Path(tempfile.mkdtemp())
        >>> _ = (folder / "helpers.py").write_text("LOADING = 1.1")
        >>> _ = (folder / "model.py").write_text("import json\nimport helpers")
        >>> [path.name for path in local_modules(folder / "model.py")]
        ['helpers.py']
        >>> shutil.rmtree(folder)

    """
    model = Path(source).resolve()
    directory = model.parent
    found: set[Path] = set()
    pending = [model]
    while pending:
        current = pending.pop()
        for reached in _files_imported_by(current, directory):
            if reached == model or reached in found:
                continue
            found.add(reached)
            if reached.suffix == ".py":
                pending.append(reached)
    return tuple(sorted(found))


# The calls that load code a model's import statements do not name: by a
# file's path, or by a name computed as the model runs. ``local_modules``
# reads import statements, so what these load is never on its list.
_LOADS_BY_PATH: Final[frozenset[str]] = frozenset(
    {
        "spec_from_file_location",
        "SourceFileLoader",
        "SourcelessFileLoader",
        "exec_module",
        "load_module",
        "import_module",
        "__import__",
        "run_path",
        "run_module",
        "exec",
    }
)


def loads_by_path(source: Path) -> tuple[str, ...]:
    r"""Return where the model or a local module loads code no import names.

    ``importlib.util.spec_from_file_location`` -- the route a model directory
    that is not a package takes to a helper -- ``importlib.import_module``
    with a computed name, ``runpy.run_path`` and ``exec`` all run a file no
    import statement names, so :func:`local_modules` cannot list it, and an
    edit to that file moves figures no recorded module accounts for. Each
    such call is named as ``file:line call``, so a reader holding the model
    against its record is told what the record's list does not cover rather
    than that there is nothing to hold.

    Args:
        source: The model file.

    Returns:
        One ``name:line call`` per call, in file then line order. Empty where
        the model and its local modules load code by their imports alone.

    Examples:
        >>> import shutil
        >>> import tempfile
        >>> from pathlib import Path
        >>> folder = Path(tempfile.mkdtemp())
        >>> text = (
        ...     "import importlib.util\nspec = importlib.util.spec_from_file_location"
        ... )
        >>> _ = (folder / "model.py").write_text(text + "('h', 'h.py')")
        >>> loads_by_path(folder / "model.py")
        ('model.py:2 spec_from_file_location',)
        >>> shutil.rmtree(folder)

    """
    model = Path(source).resolve()
    found: list[str] = []
    for path in (model, *local_modules(model)):
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError, ValueError):
            continue
        found.extend(
            f"{path.name}:{node.lineno} {called}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (called := _called(node.func)) in _LOADS_BY_PATH
        )
    return tuple(found)


def _called(func: ast.expr) -> str | None:
    """Return the last name of what a call calls: ``a.b.c(...)`` is ``c``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def imported_from_outside(source: Path) -> tuple[str, ...]:
    r"""Return each top-level module the model imports from outside its directory.

    The import statements of the model and of every local module it reaches
    (:func:`local_modules`) are read off their text, and each absolute name's
    first part is kept where the model's own directory does not hold it --
    the names :func:`local_modules` passes over. The standard library's names
    and the modules Python answers before it looks at any directory are left
    out: what is left is what an installed distribution provides, or nothing
    does. A relative import is always the model's own, and is never listed.

    Args:
        source: The model file.

    Returns:
        The names, sorted. Empty where the model imports nothing from
        outside its directory but the standard library.

    Examples:
        >>> import shutil
        >>> import tempfile
        >>> from pathlib import Path
        >>> folder = Path(tempfile.mkdtemp())
        >>> _ = (folder / "helpers.py").write_text("import polars as pl")
        >>> _ = (folder / "model.py").write_text("import json\nimport helpers")
        >>> imported_from_outside(folder / "model.py")
        ('polars',)
        >>> shutil.rmtree(folder)

    """
    model = Path(source).resolve()
    directory = model.parent
    names: set[str] = set()
    for path in (model, *local_modules(model)):
        if path.suffix in SOURCE_SUFFIXES:
            names.update(_absolute_tops(path))
    return tuple(
        sorted(
            name
            for name in names
            if name not in sys.stdlib_module_names
            and name not in sys.builtin_module_names
            and FrozenImporter.find_spec(name) is None
            and _found_in(directory, name) is None
        )
    )


def _absolute_tops(path: Path) -> Iterator[str]:
    """Yield the first part of every absolute name one file's imports name."""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        # Unreadable or unparseable: it could not have been imported, so it
        # imports nothing, as ``_files_imported_by`` reads it.
        return
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                yield alias.name.partition(".")[0]
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module
        ):
            yield statement.module.partition(".")[0]


def _files_imported_by(path: Path, directory: Path) -> Iterator[Path]:
    """Yield each file beside the model that one file's imports resolve to."""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        # A file that cannot be read or parsed could not have been imported,
        # so it imports nothing; the hash the record takes of it says the rest.
        return
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                yield from _resolved(alias.name.split("."), directory)
        elif isinstance(statement, ast.ImportFrom):
            parts = statement.module.split(".") if statement.module else []
            search = _sought_in(statement.level, path, directory)
            if search is None:
                continue
            yield from _resolved(parts, search, absolute=statement.level == 0)
            for alias in statement.names:
                if alias.name != "*":
                    yield from _resolved(
                        [*parts, alias.name], search, absolute=statement.level == 0
                    )


def _sought_in(level: int, path: Path, directory: Path) -> Path | None:
    """Return the directory a ``from`` import's name is sought in, or None.

    An absolute import is sought in the model's directory; a relative one in
    the package the importing file sits in, climbed ``level - 1`` times, which
    must itself lie inside that directory. A relative import in the model
    file, which is no package, would fail as the model ran, and resolves to
    nothing here.
    """
    if level == 0:
        return directory
    package = path.parent
    for _ in range(level - 1):
        package = package.parent
    if package == directory or not package.is_relative_to(directory):
        return None
    return package


def _resolved(
    parts: list[str], search: Path, *, absolute: bool = True
) -> Iterator[Path]:
    """Yield the files a dotted name runs through, sought in ``search`` alone.

    An absolute name Python answers before it looks at any directory -- a
    built-in or a frozen module -- is not sought at all: no file beside the
    model can stand in for it. Each part is then looked for as Python's own
    file finder looks for it, in its order: a package directory holding an
    ``__init__``, then a module file, then a directory alone, which is a
    namespace package and has no file of its own to list.
    """
    if not parts:
        return
    if absolute and (
        parts[0] in sys.builtin_module_names
        or FrozenImporter.find_spec(parts[0]) is not None
    ):
        return
    place = search
    for part in parts:
        found = _found_in(place, part)
        if found is None:
            return
        file, package = found
        if file is not None:
            yield file
        if package is None:
            return
        place = package


# The suffixes Python's file finder tries, in the order it tries them.
_SUFFIXES: Final[tuple[str, ...]] = (
    *EXTENSION_SUFFIXES,
    *SOURCE_SUFFIXES,
    *BYTECODE_SUFFIXES,
)


def _found_in(place: Path, name: str) -> tuple[Path | None, Path | None] | None:
    """Return the file ``name`` is in ``place`` and the package directory it opens.

    None where ``place`` holds no module of that name. A module file opens no
    package; a namespace package has no file.
    """
    package = place / name
    if package.is_dir():
        for suffix in _SUFFIXES:
            init = package / f"__init__{suffix}"
            if init.is_file():
                return init.resolve(), package.resolve()
    for suffix in _SUFFIXES:
        module = place / f"{name}{suffix}"
        if module.is_file():
            return module.resolve(), None
    if package.is_dir():
        return None, package.resolve()
    return None
