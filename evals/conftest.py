# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for skill evals."""

import pytest

EVAL_MODELS = [
    "anthropic:claude-sonnet-4-6",
    "anthropic:claude-haiku-4-5",
    "openai:gpt-5.4",
    "openai:gpt-5.4-mini",
]

SKILL_NAMES = [
    "review",
    "discovery",
    "building",
    "reconciliation",
    "scenarios",
    "quickstart",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --eval-model option to select which LLM to test."""
    parser.addoption(
        "--eval-model",
        action="store",
        default=None,
        help="Run evals for a specific model only (e.g. 'anthropic:claude-sonnet-4-6')",
    )


@pytest.fixture
def eval_model(request: pytest.FixtureRequest) -> str | None:
    """Return the --eval-model CLI option value."""
    return request.config.getoption("--eval-model")
