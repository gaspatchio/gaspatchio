# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for lift computation."""

import pytest

from evals.comparator import lift


def test_lift_is_with_minus_without_per_model() -> None:
    """Lift = mean(with) - mean(without), computed per model, never pooled."""
    out = lift(
        {"sonnet": [1.0, 0.5], "haiku": [0.5, 0.5]},
        {"sonnet": [0.5, 0.5], "haiku": [0.5, 0.5]},
    )
    assert out["sonnet"] == pytest.approx(0.25)
    assert out["haiku"] == pytest.approx(0.0)
