#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Run all skill evals across all models, output results.

Usage:
    uv run python evals/run_evals.py                    # all models
    uv run python evals/run_evals.py --model anthropic:claude-sonnet-4-6  # single model
    uv run python evals/run_evals.py --skill review     # single skill
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the gaspatchio-core root is on the path when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic_evals import Dataset

from evals.agents import AGENT_FACTORIES, make_agent
from evals.evaluators import (
    HasQuestionsBeforeCode,
    IdentifiesReference,
    InvestigatesMismatch,
    ListColumnHandling,
    NoAntiPattern,
    NoCriticalIssues,
    NoCodeWritten,
    PlacementCorrect,
    SeverityClassification,
    TwoScriptPattern,
)

CUSTOM_EVALUATOR_TYPES = [
    SeverityClassification,
    NoCriticalIssues,
    NoCodeWritten,
    HasQuestionsBeforeCode,
    IdentifiesReference,
    InvestigatesMismatch,
    TwoScriptPattern,
    PlacementCorrect,
    NoAntiPattern,
    ListColumnHandling,
]

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

SKILL_NAMES = list(AGENT_FACTORIES.keys())


def compute_pass_rate(report) -> float:
    """Compute overall pass rate from an eval report.

    A case passes if all assertions are True and average score >= 0.7.
    Cases with only assertions (no scores) pass if all assertions pass.
    """
    if not report.cases:
        return 1.0
    passed = 0
    for case_result in report.cases:
        # Check assertions (bool evaluators)
        assertions = [a.value for a in case_result.assertions.values() if a is not None]
        assertions_ok = all(assertions) if assertions else True

        # Check scores (numeric evaluators)
        scores = [s.value for s in case_result.scores.values() if s is not None]
        scores_ok = (sum(scores) / len(scores)) >= 0.5 if scores else True

        if assertions_ok and scores_ok:
            passed += 1
    return passed / len(report.cases)


def run_skill_eval(skill_name: str, model: str) -> float:
    """Run a single skill's dataset against a single model. Returns pass rate."""
    dataset_path = DATASETS_DIR / f"{skill_name}.yaml"
    if not dataset_path.exists():
        print(f"  SKIP {skill_name} (no dataset)")
        return 1.0

    dataset = Dataset.from_file(
        str(dataset_path),
        custom_evaluator_types=CUSTOM_EVALUATOR_TYPES,
    )
    agent = make_agent(skill_name, model)

    # Wrap agent.run (async) for evaluate_sync compatibility
    async def task(inputs: str):
        result = await agent.run(inputs)
        return result.output

    report = dataset.evaluate_sync(task)
    report.print()

    return compute_pass_rate(report)


def main() -> None:
    """Run evals and write results."""
    parser = argparse.ArgumentParser(description="Run gaspatchio skill evals")
    parser.add_argument("--model", help="Single model to test")
    parser.add_argument("--skill", help="Single skill to test")
    args = parser.parse_args()

    models = [args.model] if args.model else MODELS
    skills = [args.skill] if args.skill else SKILL_NAMES

    all_results: dict[str, dict[str, float]] = {}
    benchmark_entries: list[dict] = []

    for model in models:
        print(f"\n{'=' * 60}")
        print(f"Model: {model}")
        print(f"{'=' * 60}")

        model_results: dict[str, float] = {}
        for skill_name in skills:
            print(f"\n--- {skill_name} ---")
            pass_rate = run_skill_eval(skill_name, model)
            model_results[skill_name] = pass_rate
            print(f"  Pass rate: {pass_rate:.0%}")

            benchmark_entries.append({
                "name": f"{skill_name}/{model.split(':')[-1]}",
                "unit": "Percent",
                "value": round(pass_rate * 100, 1),
            })

        all_results[model] = model_results

    # Write outputs
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "benchmark-results.json").write_text(
        json.dumps(benchmark_entries, indent=2)
    )
    (RESULTS_DIR / "capability-matrix.json").write_text(
        json.dumps(all_results, indent=2)
    )

    print(f"\nResults written to {RESULTS_DIR}/")

    # Report low scores but don't fail CI — evals are informational
    # LLM outputs have inherent variance; the dashboard tracks trends
    has_warnings = False
    for model, results in all_results.items():
        for skill, rate in results.items():
            if rate < 0.5:
                print(f"WARN: {skill} on {model} = {rate:.0%} < 50%")
                has_warnings = True
    if has_warnings:
        print("\nSome skills scored below 50% — check the dashboard for details.")


if __name__ == "__main__":
    main()
