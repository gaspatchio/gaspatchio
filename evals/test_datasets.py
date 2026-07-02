# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101, PT018
"""Every dataset is well-formed for the new oracle-driven runner."""

from pathlib import Path

import yaml

DATASETS = Path(__file__).resolve().parent / "datasets"
SKILLS = ["review", "discovery", "quickstart", "building",
          "reconciliation", "scenarios", "extending"]


def test_every_skill_has_a_dataset_with_cases() -> None:
    """Each skill has a YAML dataset with at least one case carrying a prompt."""
    for skill in SKILLS:
        data = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())
        assert data["cases"], skill
        for case in data["cases"]:
            assert case["name"] and case["prompt"], (skill, case.get("name"))
