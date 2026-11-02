# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: A Table whose source cannot be read says why on lines of their own.
# ABOUTME: Pins the rendered refusal text: line breaks, never a printed backslash-n.
"""The refusals for an unreadable ``Table`` source break onto separate lines.

Each refusal states what went wrong and then lists what to check, one
suggestion to a line. The breaks were once written with the backslash
escaped, so they reached the actuary as a backslash and an ``n`` in the
middle of one long line, which is what these tests hold against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from pathlib import Path


def _refusal(source: Path, expected: type[Exception]) -> str:
    """Build a Table from ``source`` and return the refusal it raises."""
    with pytest.raises(expected) as caught:
        Table(name="unreadable", source=source, dimensions={"age": "age"}, value="q")
    return str(caught.value)


def _assert_one_suggestion_per_line(message: str, first_line: str) -> None:
    # A reader's own error text (quoted after the first line's colon) may run
    # to several lines, so the suggestions are found by their heading.
    assert "\\n" not in message
    lines = message.splitlines()
    assert lines[0].startswith(first_line)
    suggestions = lines[lines.index("Suggestions:") + 1 :]
    assert len(suggestions) >= 3
    assert all(line.startswith("  • ") for line in suggestions)


def test_a_missing_file_lists_its_suggestions_on_their_own_lines(
    tmp_path: Path,
) -> None:
    message = _refusal(tmp_path / "missing.csv", FileNotFoundError)

    _assert_one_suggestion_per_line(message, "Source file not found: ")
    assert message.splitlines()[-1] == "  • Check file permissions"


def test_an_unreadable_csv_lists_its_suggestions_on_their_own_lines(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ragged.csv"
    source.write_text("age,q\n1,0.1\n2,0.2,9\n")

    message = _refusal(source, ValueError)

    _assert_one_suggestion_per_line(message, "Failed to read CSV file ")


def test_an_unreadable_parquet_lists_its_suggestions_on_their_own_lines(
    tmp_path: Path,
) -> None:
    source = tmp_path / "corrupt.parquet"
    source.write_bytes(b"these bytes are not a parquet file")

    message = _refusal(source, ValueError)

    _assert_one_suggestion_per_line(message, "Failed to read Parquet file ")


def test_an_unsupported_format_lists_its_suggestions_on_their_own_lines(
    tmp_path: Path,
) -> None:
    source = tmp_path / "rates.txt"
    source.write_text("age,q\n1,0.1\n")

    message = _refusal(source, ValueError)

    _assert_one_suggestion_per_line(message, "Unsupported file format: .txt.")
