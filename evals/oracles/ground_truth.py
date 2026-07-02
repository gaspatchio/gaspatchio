# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Ground-truth oracles for non-code skills: defects, code-presence, routing."""

from __future__ import annotations

import re

from evals.oracles.base import OracleResult, extract_code


def grade_seeded_defects(artifact: str, case: dict) -> OracleResult:
    """Score a review against planted defects.

    With planted defects: score = recall (fraction named, case-insensitive).
    Clean case (no planted defects): 1.0 only if no `forbidden_terms` appear —
    rewarding the agent for not inventing criticals.
    """
    text = artifact.lower()
    planted = case.get("planted_defects", [])
    if planted:
        found = sum(1 for d in planted if d.lower() in text)
        return OracleResult(
            found / len(planted), f"named {found}/{len(planted)} planted defects"
        )
    forbidden = case.get("forbidden_terms", [])
    raised = [t for t in forbidden if t.lower() in text]
    if raised:
        return OracleResult(0.0, f"false-alarm terms: {raised}")
    return OracleResult(1.0, "clean, no false alarm")


def grade_no_code(artifact: str, case: dict) -> OracleResult:  # noqa: ARG001
    """Score 1.0 if the artifact contains no python code block (discovery gate)."""
    if extract_code(artifact):
        return OracleResult(0.0, "code emitted (should not)")
    return OracleResult(1.0, "no code, as required")


def grade_routing(artifact: str, case: dict) -> OracleResult:
    """Score 1.0 if the expected tutorial level appears as a whole phrase."""
    level = case["expected_level"]
    hit = re.search(rf"\b{re.escape(level)}\b", artifact) is not None
    return OracleResult(
        1.0 if hit else 0.0, f"expected '{level}': {'found' if hit else 'absent'}"
    )
