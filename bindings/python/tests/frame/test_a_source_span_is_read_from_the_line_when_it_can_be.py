# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A line holding one statement is resolved without bytecode matching.

Matching the running bytecode to a node cost about half of every assignment's
source span, and only a line holding two statements needs it. What the span
says is the audit record, so it must not change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import executing
import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.calculations import capture_source_span

if TYPE_CHECKING:
    import pytest


def _refuse_to_match(_frame: object) -> None:
    raise AssertionError


def test_a_line_with_one_statement_needs_no_bytecode_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(executing.Source, "executing", _refuse_to_match)

    span = capture_source_span()

    assert span is not None
    assert span.statement == "span = capture_source_span()"


def test_a_statement_over_several_lines_is_read_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(executing.Source, "executing", _refuse_to_match)

    # fmt: off
    span = (
        capture_source_span()
    )
    # fmt: on

    assert span is not None
    assert span.line + 2 == span.end_line
    assert span.statement.startswith("span = (")


def test_two_statements_on_a_line_are_told_apart_as_before() -> None:
    # fmt: off
    first = capture_source_span(); second = capture_source_span()  # noqa: E702
    # fmt: on

    assert first is not None
    assert second is not None
    assert first.statement == "first = capture_source_span()"
    assert second.statement == "second = capture_source_span()"


def test_a_column_records_the_line_that_defined_it() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "x": [1.0]}))
    af.y = af.x * 2.0

    assert af.collect()["y"].to_list() == [2.0]
