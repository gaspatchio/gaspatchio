# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A Git LFS pointer is recognised exactly, and nothing else is taken for one.

A checkout made without Git LFS leaves a pointer where a file should be, and
the refusal that names it has to be right both ways: a pointer is never read
as a broken file, and a file is never refused as a pointer because it begins
like one.
"""

from __future__ import annotations

import doctest
import io

import pytest

from gaspatchio import _lfs
from gaspatchio._lfs import LfsPointer, parse_lfs_pointer

_OID = "4d7a" * 16
_VERSION = "version https://git-lfs.github.com/spec/v1"


def _pointer(*lines: str, newline: str = "\n") -> bytes:
    return "".join(f"{line}{newline}" for line in lines).encode("ascii")


def test_a_pointer_is_read_with_lf_and_with_crlf() -> None:
    lines = (_VERSION, f"oid sha256:{_OID}", "size 38826")

    with_lf = parse_lfs_pointer(_pointer(*lines))
    with_crlf = parse_lfs_pointer(_pointer(*lines, newline="\r\n"))

    assert with_lf == with_crlf == LfsPointer(oid=_OID, size=38826)


def test_the_hawser_pointer_is_a_pointer() -> None:
    """The version line git-lfs wrote before its public launch, which it still reads."""
    data = _pointer(
        "version https://hawser.github.com/spec/v1", f"oid sha256:{_OID}", "size 12"
    )

    assert parse_lfs_pointer(data) == LfsPointer(oid=_OID, size=12)


def test_a_pointer_with_an_extension_line_is_a_pointer() -> None:
    data = _pointer(
        _VERSION, f"ext-0-foo sha256:{'ab' * 32}", f"oid sha256:{_OID}", "size 7"
    )

    assert parse_lfs_pointer(data) == LfsPointer(oid=_OID, size=7)


def test_a_csv_whose_header_begins_like_the_version_line_is_not_a_pointer() -> None:
    data = f"{_VERSION}x,notes\n1,a reserve note\n".encode("ascii")

    assert parse_lfs_pointer(data) is None


def test_a_file_over_1024_bytes_that_begins_with_the_version_line_is_not_one() -> None:
    """The shape of a pointer, grown past the size a pointer is held to."""
    extensions = [f"ext-{n % 10}-name{n} sha256:{'ab' * 32}" for n in range(14)]
    data = _pointer(_VERSION, *extensions, f"oid sha256:{_OID}", "size 7")

    assert len(data) > 1024
    assert parse_lfs_pointer(data) is None
    assert parse_lfs_pointer(
        _pointer(_VERSION, *extensions[:2], f"oid sha256:{_OID}", "size 7")
    ) == LfsPointer(oid=_OID, size=7)


def test_a_pointer_with_no_size_line_is_not_a_pointer() -> None:
    assert parse_lfs_pointer(_pointer(_VERSION, f"oid sha256:{_OID}")) is None


@pytest.mark.parametrize(
    "data",
    [
        _pointer(_VERSION, "", f"oid sha256:{_OID}", "size 7"),
        _pointer(_VERSION, f"oid sha256:{_OID}", f"ext-0-foo sha256:{_OID}", "size 7"),
        _pointer(_VERSION, f"oid sha256:{_OID}", "size +12"),
        _pointer(_VERSION, f"oid sha256:{_OID}", "size 7 "),
        _pointer(_VERSION, f"oid sha256:{_OID}", "size 7").ljust(1024, b"\n"),
        b"",
    ],
    ids=[
        "blank line",
        "extension after the oid",
        "signed size",
        "trailing space",
        "1024 bytes",
        "empty",
    ],
)
def test_forms_git_lfs_reads_too_are_not_taken_for_pointers(data: bytes) -> None:
    """The module is stricter than git-lfs, as its docstring says."""
    assert parse_lfs_pointer(data) is None


def test_the_documented_examples_run() -> None:
    """Every example in the module is executed, not merely displayed."""
    found = [test for test in doctest.DocTestFinder().find(_lfs) if test.examples]
    assert found, "the module's examples were not found"
    report = io.StringIO()
    doctest_runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in found:
        doctest_runner.run(test, out=report.write)

    assert doctest_runner.failures == 0, report.getvalue()


# Every spelling git-lfs writes or reads, and the near misses, as one table.
_HEX = "4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393"


def _spelled(version: str = "https://git-lfs.github.com/spec/v1", *lines: str) -> str:
    return (
        "\n".join([f"version {version}", *lines, f"oid sha256:{_HEX}", "size 12345"])
        + "\n"
    )


@pytest.mark.parametrize(
    "data",
    [
        _spelled().encode(),
        _spelled().replace("\n", "\r\n").encode(),
        _spelled("https://hawser.github.com/spec/v1").encode(),
        _spelled("http://git-media.io/v/2").encode(),
        _spelled(
            "https://git-lfs.github.com/spec/v1", f"ext-0-foo sha256:{_HEX}"
        ).encode(),
        _spelled().rstrip("\n").encode(),
    ],
    ids=["lf", "crlf", "hawser", "git-media", "extension", "no-final-newline"],
)
def test_a_pointer_is_recognised(data: bytes) -> None:
    """Every spelling git-lfs writes or reads gives the object and its size."""
    assert parse_lfs_pointer(data) == LfsPointer(oid=_HEX, size=12345)


@pytest.mark.parametrize(
    "data",
    [
        # A CSV whose first header merely starts like a version line.
        b"version https://git-lfs.github.com/spec/v1x,notes\n1,2\n",
        # Over the size limit, though it begins like a pointer.
        _spelled().encode() + b"#" * 1024,
        # No size line.
        f"version https://git-lfs.github.com/spec/v1\noid sha256:{_HEX}\n".encode(),
        # A version git-lfs does not know.
        _spelled("https://example.com/spec/v9").encode(),
        # An oid that is not 64 lowercase hex digits.
        _spelled().replace(_HEX, _HEX.upper()).encode(),
        # Anything after the size but a final newline.
        _spelled().encode() + b"\n",
        _spelled().encode() + b"extra 1\n",
        # Not ASCII.
        _spelled().encode().replace(b"version", "versión".encode()),
        # A Parquet file's opening bytes.
        b"PAR1\x15\x04\x15\x80",
    ],
    ids=[
        "near-miss-csv",
        "over-1024-bytes",
        "no-size",
        "unknown-version",
        "upper-case-oid",
        "blank-line-after",
        "key-after-size",
        "not-ascii",
        "parquet",
    ],
)
def test_anything_else_is_not_a_pointer(data: bytes) -> None:
    """A near miss is not a pointer: the file is read as what it says it is."""
    assert parse_lfs_pointer(data) is None
