# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Map each skill to the oracle that grades its artifact.

Oracles share the uniform signature::

    grade(artifact: str, case: dict, workdir: Path) -> OracleResult

Text oracles ignore ``workdir``; execution oracles use it. The dataset case carries
the ground truth (expected_columns / reference / planted_defects / expected_level).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.oracles.accessor import grade_accessor
from evals.oracles.execute import grade_execution
from evals.oracles.ground_truth import (
    grade_no_code,
    grade_routing,
    grade_seeded_defects,
)
from evals.oracles.numeric import grade_numeric

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from evals.oracles.base import OracleResult


def _text(
    fn: Callable[[str, dict], OracleResult],
) -> Callable[[str, dict, Path], OracleResult]:
    """Adapt a text oracle (artifact, case) to the uniform (artifact, case, workdir)."""
    def wrapped(artifact: str, case: dict, workdir: Path) -> OracleResult:  # noqa: ARG001
        return fn(artifact, case)
    return wrapped


ORACLES: dict[str, Callable[[str, dict, Path], OracleResult]] = {
    "execute": grade_execution,
    "numeric": grade_numeric,
    "ground_truth_defects": _text(grade_seeded_defects),
    "ground_truth_no_code": _text(grade_no_code),
    "ground_truth_routing": _text(grade_routing),
    "accessor": _text(grade_accessor),
}

SKILL_ORACLE: dict[str, str] = {
    "building": "execute",
    "reconciliation": "numeric",
    "scenarios": "execute",
    "extending": "accessor",
    "review": "ground_truth_defects",
    "discovery": "ground_truth_no_code",
    "quickstart": "ground_truth_routing",
}


def oracle_for(skill: str) -> Callable[[str, dict, Path], OracleResult]:
    """Return the oracle callable for a skill."""
    return ORACLES[SKILL_ORACLE[skill]]
