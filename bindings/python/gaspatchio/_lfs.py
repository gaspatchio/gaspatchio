# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: A Git LFS pointer, recognised as the specification writes one.
# ABOUTME: What a checkout made without Git LFS leaves where a file should be.
"""A Git LFS pointer, recognised as the git-lfs specification writes one.

A repository that keeps large files in Git LFS commits a short pointer in
each one's place, and a checkout made without Git LFS leaves that pointer on
disk where the file should be. Read as data it is neither JSON nor Parquet,
and a refusal that said so would name the wrong problem: the file is in LFS
storage, and the pointer says which file it is.

What is recognised is a pointer as the specification writes one. The data is
under 1024 bytes and decodes as ASCII. Split on LF, with one trailing CR taken
off each line, its lines are:

- the version line, ``version`` and one of the three specification URLs
  git-lfs accepts;
- any number of extension lines, ``ext-<n>-<name> <value>``;
- the oid line, ``oid sha256:`` and 64 lower-case hex digits;
- the size line, ``size`` and a decimal number;

and nothing else but a final newline. A file that only begins like one -- a
CSV whose header starts with the version line -- is read as the file it is.

This is stricter than git-lfs, which also reads as a pointer: blank lines, an
extension line between the oid and the size, a size written ``+12``, a
trailing space, a pointer of exactly 1024 bytes, and an empty file. None of
those is taken for a pointer here, so a command expecting a document refuses
it as no document rather than as a pointer -- a less exact refusal, and never
a wrong answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ["LfsPointer", "parse_lfs_pointer"]

# A pointer is smaller than this, by the specification.
_MAX_BYTES: Final[int] = 1024

# The version lines git-lfs accepts: the public launch's, and the two that
# came before it.
_VERSIONS: Final[frozenset[str]] = frozenset(
    {
        "version https://git-lfs.github.com/spec/v1",
        "version https://hawser.github.com/spec/v1",
        "version http://git-media.io/v/2",
    }
)

_EXTENSION: Final[re.Pattern[str]] = re.compile(r"ext-[0-9]-\w+ .+")
_OID: Final[re.Pattern[str]] = re.compile(r"oid sha256:([0-9a-f]{64})")
_SIZE: Final[re.Pattern[str]] = re.compile(r"size ([0-9]+)")


@dataclass(frozen=True, slots=True)
class LfsPointer:
    """A Git LFS pointer: what a repository commits in place of a file in LFS.

    Attributes:
        oid: The sha256 of the file it stands for, as 64 hex digits.
        size: The size of that file, in bytes.

    """

    oid: str
    size: int


def parse_lfs_pointer(data: bytes) -> LfsPointer | None:
    r"""Return the Git LFS pointer ``data`` is, or None where it is not one.

    Args:
        data: A file's bytes, as they were read.

    Returns:
        The pointer, with the oid and size of the file it stands for, or None
        where ``data`` is anything but a pointer.

    Examples:
        >>> pointer = parse_lfs_pointer(
        ...     b"version https://git-lfs.github.com/spec/v1\n"
        ...     b"oid sha256:" + b"4d7a" * 16 + b"\n"
        ...     b"size 38826\n"
        ... )
        >>> pointer.size
        38826
        >>> parse_lfs_pointer(b'{"schema": "gaspatchio-graph/v0-preview.3"}') is None
        True

    """
    if len(data) >= _MAX_BYTES:
        return None
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # the final newline
    lines = [line.removesuffix("\r") for line in lines]
    if len(lines) < len(("version", "oid", "size")):
        return None
    version, *extensions, oid_line, size_line = lines
    oid = _OID.fullmatch(oid_line)
    size = _SIZE.fullmatch(size_line)
    if (
        version not in _VERSIONS
        or oid is None
        or size is None
        or not all(_EXTENSION.fullmatch(line) for line in extensions)
    ):
        return None
    return LfsPointer(oid=oid.group(1), size=int(size.group(1)))
