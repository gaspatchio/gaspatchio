# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Accessor oracle (extending skill): static scan for vectorisation anti-patterns.

v1 grades the emitted code statically (the anti-patterns the skill forbids are
syntactic). A future tier can import + apply the accessor to scalar/list columns;
the seam is the same ``grade(artifact, case)`` signature.
"""

from __future__ import annotations

import re

from evals.oracles.base import OracleResult, extract_code

_ANTIPATTERNS = (
    re.compile(r"\.map_elements\b"),
    re.compile(r"\.apply\b"),
    re.compile(r"\.iter_rows\b"),
    re.compile(r"\bfor\s+\w+\s+in\s+.*\.(iter_rows|rows)\b"),
)


def grade_accessor(artifact: str, case: dict) -> OracleResult:  # noqa: ARG001
    """Score 1.0 if emitted code is anti-pattern-free, 0.0 if not (or no code)."""
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    hits = [p.pattern for p in _ANTIPATTERNS if p.search(code)]
    if hits:
        return OracleResult(0.0, f"anti-patterns: {hits}")
    return OracleResult(1.0, "vectorised, clean")
