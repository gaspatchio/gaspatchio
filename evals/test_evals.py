# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101, PLC0415
"""Eval wiring tests. The structural test is free; the slow test calls LLM APIs.

uv run pytest evals/test_evals.py            # structural (free)
uv run pytest evals/test_evals.py -m slow    # real eval (costs API $)
"""

from pathlib import Path

import pytest
import yaml

from evals.agents import SKILL_DIRS
from evals.oracles.registry import oracle_for

DATASETS = Path(__file__).resolve().parent / "datasets"


def test_every_skill_wires_to_an_oracle_and_dataset() -> None:
    """Each skill has a dataset and a resolvable oracle (no LLM call)."""
    for skill in SKILL_DIRS:
        assert callable(oracle_for(skill)), skill
        cases = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())["cases"]
        assert cases, skill


@pytest.mark.slow
def test_building_lift_is_nonnegative() -> None:
    """With-skill should not underperform baseline on building (costs API $)."""
    from evals.run_evals import _score_arm

    model = "anthropic:claude-haiku-4-5"
    w = _score_arm("building", model, with_skill=True, trials=1)
    b = _score_arm("building", model, with_skill=False, trials=1)
    assert w >= b - 0.01, f"with={w} < without={b}"
