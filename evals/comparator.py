# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Comparator: per-model lift = mean(with-skill) - mean(without-skill)."""

from __future__ import annotations


def lift(
    with_scores: dict[str, list[float]],
    without_scores: dict[str, list[float]],
) -> dict[str, float]:
    """Return per-model lift.

    Never pools across models (effects are model-conditional).
    """
    out: dict[str, float] = {}
    for model, ws in with_scores.items():
        bs = without_scores.get(model, [])
        w = sum(ws) / len(ws) if ws else 0.0
        b = sum(bs) / len(bs) if bs else 0.0
        out[model] = w - b
    return out
