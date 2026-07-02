# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101, PLR2004
"""Tests for oracle base types + code extraction."""

from evals.oracles.base import OracleResult, extract_code


def test_oracle_result_holds_score_and_detail() -> None:
    """An OracleResult carries a [0,1] score and a human detail string."""
    r = OracleResult(score=0.5, detail="2/4 columns")
    assert r.score == 0.5
    assert "2/4" in r.detail


def test_extract_code_takes_largest_python_fence() -> None:
    """extract_code returns the largest ```python fenced block, dedented."""
    md = (
        "Intro.\n\n```python\nx = 1\n```\n\n"
        "More.\n\n```python\nfrom gaspatchio_core import ActuarialFrame\n\n"
        "def main(af):\n    af.y = af.x * 2\n    return af\n```\n"
    )
    code = extract_code(md)
    assert "def main(af)" in code
    assert "x = 1" not in code  # the larger block wins


def test_extract_code_returns_empty_when_no_fence() -> None:
    """No python fence yields an empty string."""
    assert extract_code("just prose, no code") == ""


def test_extract_code_is_case_insensitive() -> None:
    """A capitalised ```Python fence is still extracted."""
    assert "x = 1" in extract_code("```Python\nx = 1\n```")


def test_extract_code_tolerates_trailing_space_after_lang() -> None:
    """A trailing space after the language tag is tolerated."""
    assert "x = 1" in extract_code("```python \nx = 1\n```")
