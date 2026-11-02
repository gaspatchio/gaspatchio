# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for calculation graph operations."""

from __future__ import annotations

import os.path
import re
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Final

from gaspatchio._source import display_filename
from gaspatchio.frame.lowering._polars.rendering import (
    kernels_as_operations,
    nan_guards_as_written,
    quotients_as_operators,
    read_once_as_written,
    without_plugin_library_paths,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.frame.calculations import SourceSpan

# A plugin call once its library path has been scrubbed: the method dot, the
# placeholder standing where the library was, and the colon before the
# symbol. A walk-through writes the call as the method it is, so the three
# become the dot alone.
_PLUGIN_STANDIN = ".<plugin>:"


# What stands in a document for the directories above a file that lies
# outside the model's root and shares no directory with it below the
# filesystem's root. The file's own name follows it, after a slash, so the
# record still says which file it was.
OUTSIDE_THE_ROOT: Final[str] = "<outside the model's root>"


def relative_to_root(path: str | Path, root: Path) -> str:
    """Return ``path`` as an artifact rooted at ``root`` writes it.

    A real relative path, in the sense :func:`os.path.relpath` gives it,
    wherever that path names no directory of the machine: a file under
    ``root``, and a file beside it -- a model reading its policy data out of
    a sibling directory is a fact the artifact keeps, and ``..`` is how it
    keeps it, so a reader holding the artifact and the root resolves that
    path exactly as the run did.

    **A file whose only climb from the root reaches the filesystem's root is
    written as its name under** :data:`OUTSIDE_THE_ROOT` --
    ``<outside the model's root>/inforce_2026Q3.parquet`` -- and so is a file
    on another Windows drive, which no climb reaches at all. A climb of
    ``..`` to ``/`` and back down is an absolute path spelled relatively: it
    would carry a home directory, a shared volume's name or a temporary
    directory into a document the author sends to a reviewer, which is what
    the root exists to keep out. It is the rule the git detail writer
    applies to the paths git names (``_without_the_machine``), with the
    file's name kept, because the name is what tells a reviewer which file
    the run read.

    Forward slashes on every platform. Which separator a document carries is
    a property of the format rather than of the machine that wrote it, and
    two runs of one model on two operating systems should not differ in it.

    Args:
        path: The file to write.
        root: The directory it is written relative to.

    Returns:
        ``path`` relative to ``root``, forward-slashed, or its name under
        :data:`OUTSIDE_THE_ROOT` where the climb would leave the machine's
        directories in the document.

    """
    resolved = Path(path).resolve()
    try:
        below = os.path.relpath(resolved, root)
    except ValueError:
        return f"{OUTSIDE_THE_ROOT}/{resolved.name}"
    climbs = PurePath(below).parts[:1] == ("..",)
    if climbs and _shares_only_the_filesystem_root(resolved, Path(root).resolve()):
        return f"{OUTSIDE_THE_ROOT}/{resolved.name}"
    return PurePath(below).as_posix()


def _shares_only_the_filesystem_root(path: Path, root: Path) -> bool:
    """Return whether two absolute paths part company straight below ``/``."""
    shared = 0
    for own, theirs in zip(path.parts, root.parts, strict=False):
        if own != theirs:
            break
        shared += 1
    return shared <= 1


def lies_outside_the_root(written: str) -> bool:
    """Return whether a path a document carries was written as outside its root.

    Either form :func:`relative_to_root` writes for a file the root does not
    hold: a climb of ``..`` segments, or a name under
    :data:`OUTSIDE_THE_ROOT`. An absolute string is outside too, as an
    artifact written before the placeholder carried one for a second drive.
    """
    return (
        written.startswith(f"{OUTSIDE_THE_ROOT}/")
        or PurePosixPath(written).is_absolute()
        or PureWindowsPath(written).is_absolute()
        or written.split("/", 1)[0] == ".."
    )


def source_location(span: SourceSpan | None) -> str | None:
    """Return the ``file:line`` a captured span names, or None where it names none.

    The one place the graph turns a span into the string a reader is given,
    so that a definition's location and the location of the point a model
    froze its plan are the same shape rather than two spellings of it.
    ``display_filename`` is what turns a notebook cell's machine-generated
    filename into the cell number its author can actually look at.

    None wherever capture found nothing -- an unresolvable frame, a source
    the interpreter cannot read. A null says the producer looked and there
    was nothing to find, which is a smaller loss than a location that
    points somewhere the calculation was not written.

    Args:
        span: The captured span to render, or None where there is none.

    Returns:
        ``"<file>:<line>"``, or None.

    """
    if span is None:
        return None
    return f"{display_filename(span.file)}:{span.line}"


def clean_expression_string(
    expr_str: str, *, comparisons: Sequence[str] | None = None
) -> str:
    """
    Clean up expression strings by removing file paths.

    The framework's quotient kernels are written back as the operators they
    compute (``[(col("x")) / (dyn int: 12)]``), as Polars writes the operator
    itself: the walk-through shows the formula, not the kernel that computed
    it exactly. See
    :func:`~gaspatchio.frame.lowering._polars.rendering.quotients_as_operators`.

    **The text does not depend on where the package is installed.** A
    plugin call renders with the path of the library it lives in, rooted
    for a checkout and relative to the interpreter's prefix for a wheel in
    a virtual environment, and the path goes through the same scrub the
    fingerprint's own text goes through
    (:func:`~gaspatchio.frame.lowering._polars.rendering.without_plugin_library_paths`)
    before the symbol is written as the method it is:
    ``col("duration").list_conditional(...)`` from either install.

    **A list kernel is written as the operation it computes**, so that the
    walk-through names something the reader wrote or can look up rather
    than a Rust symbol: ``list_pow`` as ``.pow(...)``, ``list_clip`` as
    ``.clip(...)``, and ``list_conditional`` as the ``.when(...).then(...)
    .otherwise(...)`` it evaluates -- given its comparisons, which the
    rendering does not print
    (:func:`~gaspatchio.frame.lowering._polars.rendering.conditional_comparisons`).
    Without them a conditional keeps the kernel's name.

    Args:
        expr_str: Raw expression string
        comparisons: The conditional kernel's comparisons, in the order the
            rendering writes its calls, or None where they were not read.

    Returns:
        Cleaned expression string

    Examples:
        >>> clean_expression_string(
        ...     'col("x").lib/python3.13/site-packages/gaspatchio'
        ...     "/_internal.cpython-313-darwin.so:list_pow([])"
        ... )
        'col("x").pow([])'

    """
    scrubbed = without_plugin_library_paths(
        nan_guards_as_written(read_once_as_written(expr_str))
    )

    # Clean up internal function patterns
    scrubbed = re.sub(r"\.gaspatchio\._internal[^:]+:", ".", scrubbed)
    # The kernels first, which read the placeholder where the library was;
    # then every other plugin's symbol, written as the method it is called as.
    operations = kernels_as_operations(quotients_as_operators(scrubbed), comparisons)
    return operations.replace(_PLUGIN_STANDIN, ".")
