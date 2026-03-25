"""Tier 2: Run skill evals as pytest tests.

These tests call real LLM APIs and cost money (~$0.50-1.00 per full run).
They are marked @pytest.mark.slow and only run in nightly CI or when
explicitly requested: uv run pytest evals/ -m slow

Usage:
    uv run pytest evals/test_evals.py -m slow                    # all models × skills
    uv run pytest evals/test_evals.py -m slow -k "review"        # single skill
    uv run pytest evals/test_evals.py -m slow -k "claude-sonnet" # single model
"""

from pathlib import Path

import pytest

from evals.agents import AGENT_FACTORIES, make_agent
from evals.evaluators import (
    HasQuestionsBeforeCode,
    NoCodeWritten,
    SeverityClassification,
    TwoScriptPattern,
)
from evals.run_evals import compute_pass_rate
from pydantic_evals import Dataset

CUSTOM_EVALUATOR_TYPES = [
    SeverityClassification,
    NoCodeWritten,
    HasQuestionsBeforeCode,
    TwoScriptPattern,
]

MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
SKILL_NAMES = list(AGENT_FACTORIES.keys())


@pytest.mark.slow
@pytest.mark.parametrize("model", MODELS, ids=[m.split(":")[-1] for m in MODELS])
@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_eval(model: str, skill_name: str) -> None:
    """Run a skill eval dataset against a model and assert pass rate >= 70%."""
    dataset_path = DATASETS_DIR / f"{skill_name}.yaml"
    if not dataset_path.exists():
        pytest.skip(f"No dataset for {skill_name}")

    dataset = Dataset.from_file(
        str(dataset_path),
        custom_evaluator_types=CUSTOM_EVALUATOR_TYPES,
    )
    agent = make_agent(skill_name, model)

    async def task(inputs: str):
        result = await agent.run(inputs)
        return result.output

    report = dataset.evaluate_sync(task)
    pass_rate = compute_pass_rate(report)

    assert pass_rate >= 0.7, (
        f"{skill_name} on {model}: {pass_rate:.0%} < 70% threshold"
    )
