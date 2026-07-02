# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101, PLR2004
"""Tests for the text ground-truth oracles."""

from evals.oracles.ground_truth import (
    grade_no_code,
    grade_routing,
    grade_seeded_defects,
)


def test_seeded_defects_scores_recall() -> None:
    """Score = fraction of planted defect terms named in the findings text."""
    findings = "Critical: this uses map_elements which defeats vectorisation."
    case = {"planted_defects": ["map_elements", "for-loop"]}
    r = grade_seeded_defects(findings, case)
    assert r.score == 0.5, r.detail


def test_seeded_defects_clean_case_rewards_no_false_alarm() -> None:
    """A clean case (no planted defects) scores 1.0 only if no critical raised."""
    case = {"planted_defects": [], "forbidden_terms": ["critical", "bug"]}
    assert grade_seeded_defects("Looks correct; no issues found.", case).score == 1.0
    assert grade_seeded_defects("Critical bug here!", case).score == 0.0


def test_no_code_detects_python_fence() -> None:
    """grade_no_code scores 1.0 only when the artifact contains no python code."""
    assert grade_no_code("What is your valuation date?", {}).score == 1.0
    assert grade_no_code("```python\nx=1\n```", {}).score == 0.0


def test_routing_matches_expected_level() -> None:
    """grade_routing scores 1.0 when the expected level string appears."""
    case = {"expected_level": "Level 3"}
    assert grade_routing("I'd route you to Level 3 (Mini VA).", case).score == 1.0
    assert grade_routing("Start at Level 1.", case).score == 0.0
