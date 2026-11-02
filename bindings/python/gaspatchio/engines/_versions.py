# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What produced a set of values, stated so that a number that moves can be placed.

One mapping with two readers: the result manifest a results file carries, and
the summary a frame keeps of its last run. Both answer the question a reviewer
puts to any number they are handed -- same model, same data, would the library
this ran on give the same answer? -- and that question can only be put to a
result that names what produced it.

**What was loaded is noted as it is loaded; what it costs to read is paid
when first asked for.** The version compiled into the extension this process
loaded, and the extension's place on disk -- device, inode, size and
modification time -- are taken as this module is imported, alongside the
package's own load: microseconds, and neither can drift from what is running.

**Two versions, because they are two things.** ``core_version`` is the core
package's own version, read from its installed metadata the first time anybody
asks -- that first read takes milliseconds, which is why it is not taken at
import -- and it names the Python code, which is most of the logic a result
rests on. ``extension_version`` is the version compiled into the extension. In
a release wheel the two are one number; outside one -- an editable install over
an extension built earlier, say -- they can differ, and each is stated as it
is rather than one standing in for the other.

The digest is taken the first time anybody asks, because it reads thirty
megabytes off the disk, and it is taken only over the file this process loaded:
where the file on disk is no longer that one -- a rebuild or an upgrade landed
mid-session, as it does in a notebook -- the digest says so instead of naming a
binary that computed nothing here.

**What a model imports from outside itself is stated by distribution and
version.** A model that imports an installed in-house package -- an
``acme_actuarial`` holding the company's own accessors -- rests on that
package's code as much as on its own, and :func:`installed_versions` names
each installed distribution such an import reaches, with the version
installed, as Polars is named: by version and never by hash, because a
distribution is identified by its version.

It imports nothing of the frame, and not the package root either, which
imports everything: the engine protocol and the run summary can both state
it without reaching the model-building stack.
"""

from __future__ import annotations

import hashlib
import os
import platform
from functools import cache
from importlib.metadata import (
    PackageNotFoundError,
    distribution,
    packages_distributions,
    version,
)
from pathlib import Path
from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio._identity import SHA256_PREFIX
from gaspatchio._internal import __file__ as extension_path
from gaspatchio._internal import __version__ as compiled_version

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from importlib.metadata import Distribution
    from typing import BinaryIO

__all__ = ["installed_versions", "versions_in_this_process"]

# The distribution this package is. Never listed among what a model imports:
# the mapping beside that list already states it, twice over.
_THIS_DISTRIBUTION: Final = "gaspatchio"

# What stands in the digest's place where it cannot honestly be taken: the
# specification's word for a digest a producer could not vouch for, and the
# reason after it. Never a ``sha256:`` string, so nothing reading the mapping
# can mistake it for a digest -- or find it equal to one.
_UNAVAILABLE: Final = "unavailable: "
_CHANGED: Final = (
    f"{_UNAVAILABLE}the extension file changed after this process loaded it"
)
_UNREADABLE: Final = f"{_UNAVAILABLE}the extension file could not be read"

# Device, inode, size and modification time in nanoseconds: what says a file
# on disk is still the one that was there, without reading it.
Placed = tuple[int, int, int, int]


class _Loaded:
    """The extension this process loaded, as it stood when it was loaded.

    A plain class rather than a dataclass, because it is built as the package
    imports and a dataclass costs most of a millisecond to define: all it
    holds is a stat and a constant, and it costs microseconds.

    Attributes:
        path: Where it was loaded from.
        placed: Where it sat on disk then, or None where it could not be
            found even at load.
        extension_version: The version compiled into it.

    """

    __slots__ = ("extension_version", "path", "placed")

    def __init__(
        self, path: Path, placed: Placed | None, extension_version: str
    ) -> None:
        """Hold what was loaded, from where, and where it sat on disk then."""
        self.path = path
        self.placed = placed
        self.extension_version = extension_version


def _placed(found: os.stat_result) -> Placed:
    """Return the four facts that say which file this is, from one stat."""
    return (found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns)


def _as_loaded(path: Path, extension_version: str) -> _Loaded:
    """Return what the process loaded, stat taken now, at import."""
    try:
        placed: Placed | None = _placed(path.stat())
    except OSError:
        placed = None
    return _Loaded(path, placed, extension_version)


# Taken as this module is imported, which is as the package loads the
# extension: the one moment the file on disk is known to be the one running.
_LOADED: Final = _as_loaded(Path(extension_path), compiled_version)


def versions_in_this_process() -> dict[str, str]:
    """Return what produces values in this process, in a result manifest's keys.

    The core package's version, as installed; the version compiled into the
    extension this process loaded; the Polars version; the platform; the
    Python version; and the digest of that extension -- or, where the file on
    disk is no longer the one loaded, a statement that it changed. A mapping
    of the caller's own on every call, so a caller that keeps one and edits it
    edits nobody else's.
    """
    return dict(_taken_once())


@cache
def _taken_once() -> tuple[tuple[str, str], ...]:
    """Return the mapping's items, read the first time anybody asks."""
    try:
        core = version("gaspatchio")
    except PackageNotFoundError:  # pragma: no cover -- a source checkout
        core = "unknown"
    return (
        ("core_version", core),
        ("extension_version", _LOADED.extension_version),
        ("polars_version", pl.__version__),
        ("platform", platform.platform()),
        ("python_version", platform.python_version()),
        ("extension_sha256", _extension_sha256(_LOADED)),
    )


def _extension_sha256(loaded: _Loaded) -> str:
    """Return the digest of the extension ``loaded`` names, or say why there is none.

    The file is opened and asked, through the open handle, whether it is the
    one that was loaded -- before it is read and again after -- so a file
    replaced after the check, or written over while it is read, is caught
    rather than digested. A replaced file the process still has mapped is not
    reachable by its path any more, and a digest of whatever now sits there
    would name a binary that computed nothing here.
    """
    if loaded.placed is None:
        return _UNREADABLE
    try:
        with loaded.path.open("rb") as handle:
            if not _still_the_loaded(handle, loaded.placed):
                return _CHANGED
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if not _still_the_loaded(handle, loaded.placed):
                return _CHANGED
    except OSError:
        return _CHANGED
    return f"{SHA256_PREFIX}{digest}"


def _still_the_loaded(handle: BinaryIO, placed: Placed) -> bool:
    """Return whether the open file is the one that sat there at load."""
    return _placed(os.fstat(handle.fileno())) == placed


def installed_versions(modules: Iterable[str]) -> dict[str, str]:
    """Return each installed distribution ``modules`` reach, with its version.

    Each name is a top-level module a model imports. The distribution that
    provides it is the one of the same name where there is one -- ``numpy``,
    ``polars``, ``openpyxl`` -- and otherwise the one the installed metadata
    says provides it, as ``PyYAML`` provides ``yaml``. A name no installed
    distribution provides is not listed: there is no version to state for
    it. This package's own distribution is never listed.

    Args:
        modules: Top-level module names, as the model's import statements
            spell them.

    Returns:
        ``{distribution: version}``, the distribution named as its own
        metadata names it, ordered by name.

    Examples:
        >>> import polars as pl
        >>> installed_versions(["polars", "gaspatchio"]) == {"polars": pl.__version__}
        True

    """
    found: dict[str, str] = {}
    for module in modules:
        for provider in _providers_of(module):
            name = provider.metadata["Name"] or module
            if _canonical(name) == _THIS_DISTRIBUTION:
                continue
            found[name] = provider.version
    return dict(sorted(found.items()))


def _providers_of(module: str) -> list[Distribution]:
    """Return the installed distributions that provide one top-level module."""
    try:
        return [distribution(module)]
    except PackageNotFoundError:
        pass
    providers: list[Distribution] = []
    for name in _import_names().get(module, ()):
        try:
            providers.append(distribution(name))
        except PackageNotFoundError:  # pragma: no cover -- metadata naming nothing
            continue
    return providers


@cache
def _import_names() -> Mapping[str, list[str]]:
    """Return which distributions provide each top-level module, read once.

    Reading it walks every installed distribution's metadata, a few hundred
    milliseconds, so it is read only for a name no distribution shares, and
    only once a process.
    """
    return packages_distributions()


def _canonical(name: str) -> str:
    """Return a distribution name as the packaging standard compares names."""
    return name.lower().replace("_", "-").replace(".", "-")
