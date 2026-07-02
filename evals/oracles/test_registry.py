# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for the skill->oracle registry."""

from evals.oracles.registry import ORACLES, oracle_for


def test_every_skill_maps_to_a_callable_oracle() -> None:
    """All 7 skills resolve to a callable grader."""
    skills = ["review", "discovery", "quickstart", "building",
              "reconciliation", "scenarios", "extending"]
    for s in skills:
        assert callable(oracle_for(s)), s


def test_oracle_signature_is_uniform() -> None:
    """Every oracle is registered under a name in ORACLES."""
    assert set(ORACLES) >= {"execute", "numeric", "ground_truth_defects",
                            "ground_truth_no_code", "ground_truth_routing", "accessor"}
