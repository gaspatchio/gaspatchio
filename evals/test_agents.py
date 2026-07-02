# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""Tests for the executor's prompt composition (no LLM calls)."""

from evals.agents import build_system_prompt


def test_with_skill_includes_skill_content() -> None:
    """The with-skill prompt contains the skill's SKILL.md text."""
    p = build_system_prompt("building", with_skill=True)
    assert "Building Gaspatchio Models" in p  # SKILL.md H1


def test_without_skill_omits_skill_content() -> None:
    """The baseline prompt omits skill content but keeps the task framing."""
    p = build_system_prompt("building", with_skill=False)
    assert "Building Gaspatchio Models" not in p
    assert "gaspatchio" in p.lower()  # generic framing remains
