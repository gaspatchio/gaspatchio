# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Executor: build with/without-skill agents that emit free-form artifacts.

The agent's completion (model code or analysis text) is graded by an oracle —
there is no structured self-report output type. Each task runs twice: with the
skill content in the system prompt, and without (baseline), for lift.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_BASELINE = (
    "You are helping build actuarial models with gaspatchio, a Python "
    "framework. Answer the user's request directly and completely. When you "
    "write model code, return it in a single ```python code block."
)

SKILL_DIRS = {
    "review": "gaspatchio-model-review",
    "discovery": "gaspatchio-model-discovery",
    "quickstart": "gaspatchio-quickstart",
    "building": "gaspatchio-model-building",
    "reconciliation": "gaspatchio-model-reconciliation",
    "scenarios": "gaspatchio-model-scenarios",
    "extending": "gaspatchio-extending",
}


def _load_skill_content(skill_dir: str) -> str:
    """Load SKILL.md + reference files for a skill directory."""
    d = SKILLS_DIR / skill_dir
    parts = [(d / "SKILL.md").read_text()]
    refs = d / "references"
    if refs.exists():
        parts.extend(
            f"\n\n--- Reference: {ref.name} ---\n\n{ref.read_text()}"
            for ref in sorted(refs.glob("*.md"))
        )
    return "\n".join(parts)


def build_system_prompt(skill: str, *, with_skill: bool) -> str:
    """Compose the system prompt: baseline plus skill content iff with_skill."""
    if not with_skill:
        return _BASELINE
    return _load_skill_content(SKILL_DIRS[skill]) + "\n\n" + _BASELINE


def make_agent(skill: str, model: str, *, with_skill: bool) -> Agent[None, str]:
    """Create a plain-text agent for a skill/model, with or without the skill."""
    return Agent(model, system_prompt=build_system_prompt(skill, with_skill=with_skill))
