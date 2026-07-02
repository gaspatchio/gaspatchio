#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201, E402
"""Run skill effectiveness evals: with/without-skill, per-model lift.

uv run python evals/run_evals.py                          # all skills, all models
uv run python evals/run_evals.py --skill building          # one skill
uv run python evals/run_evals.py --model anthropic:claude-haiku-4-5 --trials 1
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.agents import SKILL_DIRS, make_agent
from evals.comparator import lift
from evals.oracles.registry import oracle_for

DATASETS = _REPO_ROOT / "evals" / "datasets"
FIXTURES = _REPO_ROOT / "evals" / "fixtures"
RESULTS = _REPO_ROOT / "evals" / "results"

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]


def _score_arm(skill: str, model: str, *, with_skill: bool, trials: int) -> float:
    """Mean oracle score for one skill/model/arm over its dataset cases x trials."""
    cases = yaml.safe_load((DATASETS / f"{skill}.yaml").read_text())["cases"]
    agent = make_agent(skill, model, with_skill=with_skill)
    grade = oracle_for(skill)
    scores: list[float] = []
    for case in cases:
        for _ in range(trials):
            with tempfile.TemporaryDirectory() as td:
                workdir = Path(td)
                # Build a fresh per-trial case from the original (never mutate
                # `case` in place — trial 2 would then see a basename path).
                run_case = dict(case)
                if case.get("fixture_data"):
                    name = Path(case["fixture_data"]).name
                    shutil.copy(FIXTURES / case["fixture_data"], workdir / name)
                    run_case["fixture_data"] = name
                if case.get("reference"):
                    name = Path(case["reference"]).name
                    shutil.copy(FIXTURES / case["reference"], workdir / name)
                    run_case["reference"] = name
                artifact = agent.run_sync(run_case["prompt"]).output
                scores.append(grade(artifact, run_case, workdir).score)
    return sum(scores) / len(scores) if scores else 0.0


def main() -> None:
    """Run evals, write capability + lift matrices."""
    ap = argparse.ArgumentParser(description="Skill effectiveness evals")
    ap.add_argument("--model")
    ap.add_argument("--skill")
    ap.add_argument("--trials", type=int, default=1)
    args = ap.parse_args()

    models = [args.model] if args.model else MODELS
    skills = [args.skill] if args.skill else list(SKILL_DIRS)

    capability: dict[str, dict[str, float]] = {}
    with_by_model: dict[str, dict[str, list[float]]] = {}
    without_by_model: dict[str, dict[str, list[float]]] = {}

    for model in models:
        capability[model] = {}
        for skill in skills:
            w = _score_arm(skill, model, with_skill=True, trials=args.trials)
            b = _score_arm(skill, model, with_skill=False, trials=args.trials)
            capability[model][skill] = w
            with_by_model.setdefault(skill, {})[model] = [w]
            without_by_model.setdefault(skill, {})[model] = [b]
            print(f"{model} / {skill}: with={w:.2f} without={b:.2f} lift={w - b:+.2f}")

    lift_matrix = {
        skill: lift(with_by_model[skill], without_by_model[skill]) for skill in skills
    }

    benchmark_entries = [
        {
            "name": f"{skill}/{model.split(':')[-1]}",
            "unit": "Percent",
            "value": round(capability[model][skill] * 100, 1),
        }
        for model in capability
        for skill in capability[model]
    ]

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "capability-matrix.json").write_text(json.dumps(capability, indent=2))
    (RESULTS / "lift-matrix.json").write_text(json.dumps(lift_matrix, indent=2))
    (RESULTS / "benchmark-results.json").write_text(
        json.dumps(benchmark_entries, indent=2)
    )
    print(
        f"\nWrote capability-matrix.json + lift-matrix.json"
        f" + benchmark-results.json to {RESULTS}/"
    )


if __name__ == "__main__":
    main()
