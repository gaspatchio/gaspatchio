# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared oracle types and the code-extraction helper."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = re.compile(r"```[ \t]*python[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class OracleResult:
    """The outcome of grading one artifact: a [0,1] score and a reason."""

    score: float
    detail: str


def extract_code(artifact: str) -> str:
    """Return the largest ```python fenced block in the artifact, or ''.

    Agents wrap emitted model code in a python fence; the largest block is the
    model (smaller blocks are usually illustrative snippets).
    """
    blocks = _FENCE.findall(artifact)
    if not blocks:
        return ""
    return max(blocks, key=len).strip()
