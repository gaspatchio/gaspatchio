# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio describe`` says in one sentence why it cannot read a file.

The file used to be read outside any error handling, so a truncated
download, a corrupt export or a Git LFS pointer printed a whole framed
traceback -- 99 lines for a Parquet file -- with the cause on the last line,
and exited 1. A missing file, a directory and an extension with no reader
each printed a usage panel instead. Each now prints one sentence on stderr
naming the file, with the status the artifact commands give a file they
cannot read.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import _EXIT_UNREADABLE, app

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

runner = CliRunner()

# What a clone made without Git LFS holds in place of the data.
_LFS_POINTER = (
    "version https://git-lfs.github.com/spec/v1\n"
    "oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393\n"
    "size 12345\n"
)


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "missing.parquet"


def _directory(tmp_path: Path) -> Path:
    path = tmp_path / "tables"
    path.mkdir()
    return path


def _corrupt_parquet(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt.parquet"
    path.write_bytes(b"PAR1 and then nothing a reader can use")
    return path


def _unsupported_extension(tmp_path: Path) -> Path:
    path = tmp_path / "rates.txt"
    path.write_text("age,rate\n40,0.001\n")
    return path


def _parquet_lfs_pointer(tmp_path: Path) -> Path:
    path = tmp_path / "mortality.parquet"
    path.write_text(_LFS_POINTER)
    return path


def _csv_lfs_pointer(tmp_path: Path) -> Path:
    path = tmp_path / "lapse.csv"
    path.write_text(_LFS_POINTER)
    return path


@pytest.mark.parametrize(
    ("make", "says"),
    [
        (_missing, "does not exist"),
        (_directory, "is a directory"),
        (_corrupt_parquet, "could not be read as Parquet"),
        (_unsupported_extension, "describe reads .parquet, .csv, .xlsx and .xls"),
        (_parquet_lfs_pointer, "is a Git LFS pointer"),
        # A pointer reads as a two-row CSV without complaint, so it is
        # recognised before any reader is chosen.
        (_csv_lfs_pointer, "is a Git LFS pointer"),
    ],
)
def test_an_unreadable_file_is_one_sentence_and_status_2(
    tmp_path: Path, make: Callable[[Path], Path], says: str
) -> None:
    """One line on stderr, naming the file and why, and nothing on stdout."""
    path = make(tmp_path)

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == _EXIT_UNREADABLE == 2
    assert result.stdout == ""
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1, result.stderr
    assert path.name in lines[0]
    assert says in lines[0]
    assert "Traceback" not in result.output
    assert "Usage:" not in result.output


def test_a_corrupt_file_carries_the_readers_own_reason(tmp_path: Path) -> None:
    """The sentence ends with what Polars said, which is the diagnosis."""
    result = runner.invoke(app, ["describe", str(_corrupt_parquet(tmp_path))])

    assert "PAR1" in result.stderr


def test_the_readers_advice_about_its_own_arguments_is_left_out(
    tmp_path: Path,
) -> None:
    """Polars' first paragraph is the diagnosis; what follows names its arguments."""
    path = tmp_path / "ragged.csv"
    path.write_text("age,rate\n40,0.001\n41,0.0011,extra\n")

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == _EXIT_UNREADABLE
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1, result.stderr
    assert "could not be read as CSV" in lines[0]
    assert "found more fields than defined" in lines[0]
    assert "truncate_ragged_lines" not in lines[0]


def test_a_missing_reader_keeps_the_command_that_installs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install command is the second line of Polars' paragraph, and it stays."""

    def _no_engine(*_args: object, **_kwargs: object) -> None:
        # Polars' own wording when a workbook reader is not installed.
        msg = (
            "required package 'fastexcel' not found.\n"
            "Please install using the command `pip install fastexcel`."
        )
        raise ModuleNotFoundError(msg)

    monkeypatch.setattr(pl, "read_excel", _no_engine)
    path = tmp_path / "assumptions.xlsx"
    path.write_bytes(b"PK not opened")

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == _EXIT_UNREADABLE
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1, result.stderr
    assert "could not be read as an Excel workbook" in lines[0]
    assert "pip install fastexcel" in lines[0]


def test_a_pointer_names_the_command_that_fetches_the_data(tmp_path: Path) -> None:
    """The next move for a pointer is to fetch what it points at."""
    result = runner.invoke(app, ["describe", str(_parquet_lfs_pointer(tmp_path))])

    assert "git lfs pull" in result.stderr


def test_json_mode_leaves_stdout_empty(tmp_path: Path) -> None:
    """An agent parsing --json gets no prose where the document would be."""
    result = runner.invoke(app, ["describe", "--json", str(_corrupt_parquet(tmp_path))])

    assert result.exit_code == _EXIT_UNREADABLE
    assert result.stdout == ""
    assert len(result.stderr.strip().splitlines()) == 1


# --- a pointer is recognised exactly, and a near miss is read as data --------

_OID = "4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("crlf.parquet", _LFS_POINTER.replace("\n", "\r\n")),
        (
            "hawser.parquet",
            _LFS_POINTER.replace("git-lfs.github.com", "hawser.github.com"),
        ),
        (
            "extension.csv",
            _LFS_POINTER.replace("oid ", f"ext-0-foo sha256:{_OID}\noid "),
        ),
    ],
)
def test_every_spelling_of_a_pointer_is_named_as_one(
    tmp_path: Path, name: str, text: str
) -> None:
    """CRLF line ends, the older version URL and an extension line are pointers."""
    path = tmp_path / name
    path.write_bytes(text.encode())

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == _EXIT_UNREADABLE
    assert "is a Git LFS pointer to 12,345 bytes" in result.stderr


@pytest.mark.parametrize(
    "text",
    [
        "version https://git-lfs.github.com/spec/v1x,notes\n1,2\n3,4\n",
        "version https://git-lfs.github.com/spec/v1,notes\n"
        + "".join(f"{row},{row}\n" for row in range(200)),
    ],
    ids=["near-miss-header", "over-1024-bytes"],
)
def test_a_csv_that_only_starts_like_a_pointer_is_described(
    tmp_path: Path, text: str
) -> None:
    """A header that begins like a version line is a header, not a pointer."""
    path = tmp_path / "notes.csv"
    path.write_text(text)

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == 0, result.output
    assert "Git LFS" not in result.output


def test_a_pointer_with_no_size_is_read_as_the_file_it_claims_to_be(
    tmp_path: Path,
) -> None:
    """Not a pointer, so Parquet's reader says what is wrong with it."""
    path = tmp_path / "mortality.parquet"
    path.write_text(f"version https://git-lfs.github.com/spec/v1\noid sha256:{_OID}\n")

    result = runner.invoke(app, ["describe", str(path)])

    assert result.exit_code == _EXIT_UNREADABLE
    assert "could not be read as Parquet" in result.stderr
    assert "Git LFS" not in result.stderr


# --- the sentence names the next move ----------------------------------------


def test_a_file_that_cannot_be_opened_is_one_sentence(tmp_path: Path) -> None:
    """Permission denied is the reader's refusal, said once, with exit status 2."""
    path = tmp_path / "locked.parquet"
    path.write_bytes(b"PAR1")
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("this account reads a file whatever its permissions")
        result = runner.invoke(app, ["describe", str(path)])
    finally:
        path.chmod(0o600)

    assert result.exit_code == _EXIT_UNREADABLE
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1, result.stderr
    assert "locked.parquet could not be opened" in lines[0]
    assert "permission" in lines[0]
    assert "Usage:" not in result.output


def test_a_broken_link_names_the_link_and_what_it_points_at(tmp_path: Path) -> None:
    """The link is what the user typed; the missing file is what it names."""
    link = tmp_path / "current.parquet"
    link.symlink_to(tmp_path / "archive" / "2026q3.parquet")

    result = runner.invoke(app, ["describe", str(link)])

    assert result.exit_code == _EXIT_UNREADABLE
    (line,) = result.stderr.strip().splitlines()
    assert f"{link} is a symbolic link to" in line
    assert str(tmp_path / "archive" / "2026q3.parquet") in line
    assert "which does not exist" in line


def test_a_corrupt_file_names_the_next_move(tmp_path: Path) -> None:
    """A file the reader refuses was cut short or written wrongly: fetch it again."""
    result = runner.invoke(app, ["describe", str(_corrupt_parquet(tmp_path))])

    assert "re-export or re-download the file" in result.stderr
