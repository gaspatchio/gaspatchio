# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Says why a path a gspio command was told to write cannot take what it writes.
# ABOUTME: Shared by the gspio commands that write a file and by its graph questions.
"""Whether a path named on the command line has a place to be written.

``gspio run-model ... -o report/results.parquet`` with no ``report/`` ended in
a traceback, after the whole model had run; ``-o`` naming a directory did the
same; and ``run-artifact --aggregate -o report/totals.json`` quietly created
``report/``. No gspio command creates a directory for its output file to go
in, so each command asks here, before it runs anything or writes a byte, and
refuses the path by the flag that named it. A file needs a directory that
exists above it and must not itself be a directory (:func:`no_place_for_a_file`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def no_place_for_a_file(flag: str, path: Path) -> str | None:
    """Return why ``path``, which ``flag`` named, cannot take a file; None where it can.

    Args:
        flag: The option the path was given to, as the refusal names it.
        path: The file the command would write.

    Returns:
        One sentence naming the flag, the path and the next move, or None
        where the path is a file, or nothing yet, in a directory that exists.

    """
    if path.is_dir():
        return (
            f"{flag} names {path}, which is a directory, so nothing was "
            "written. Name a file, inside it or in another directory that exists."
        )
    return no_directory_for(flag, path)


def no_directory_for(flag: str, path: Path) -> str | None:
    """Return why the directory ``path`` goes in is not one; None where it is.

    Args:
        flag: The option the path was given to, as the refusal names it.
        path: The file the command would write.

    Returns:
        One sentence naming the flag, the path and the next move, or None
        where the directory above ``path`` exists.

    """
    folder = path.parent
    if folder.is_dir():
        return None
    move = (
        "which is a file rather than a directory, so nothing was written. "
        "Name a file in a directory that exists."
        if folder.exists()
        else "which does not exist, so nothing was written. gspio creates "
        f"no directory for its output to go in: create it first (mkdir -p "
        f"{folder}), or name a file in a directory that exists."
    )
    return f"{flag} names {path.name} in {folder}, {move}"
