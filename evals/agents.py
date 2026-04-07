"""Agent factories for skill evaluation.

Each factory loads a skill's SKILL.md and reference files as the system prompt,
then creates a pydantic-ai Agent with the appropriate output_type.

Important: pydantic-ai v1.71.0 uses `output_type` (not `result_type`)
and `output_retries` (not `result_tool_retries`).
"""

from pathlib import Path

from pydantic_ai import Agent

from evals.result_types import (
    BuildingResult,
    DiscoveryResult,
    ExtendingResult,
    QuickstartResult,
    ReconciliationResult,
    ReviewResult,
    ScenarioResult,
)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_skill_content(skill_name: str) -> str:
    """Load SKILL.md and all reference files for a skill."""
    skill_dir = SKILLS_DIR / skill_name
    parts = [(skill_dir / "SKILL.md").read_text()]

    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        for ref_file in sorted(refs_dir.glob("*.md")):
            parts.append(f"\n\n--- Reference: {ref_file.name} ---\n\n{ref_file.read_text()}")

    return "\n".join(parts)


def _output_instructions(model_name: str) -> str:
    """Common instructions appended to every agent."""
    return (
        "\n\nIMPORTANT: You must respond with structured data matching the output schema. "
        "Analyze the input and populate each field accurately based on what you observe."
    )


def make_review_agent(model: str) -> Agent[None, ReviewResult]:
    """Create a model-review agent."""
    content = _load_skill_content("model-review")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ReviewResult,
        output_retries=2,
    )


def make_discovery_agent(model: str) -> Agent[None, DiscoveryResult]:
    """Create a model-discovery agent."""
    content = _load_skill_content("model-discovery")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=DiscoveryResult,
        output_retries=2,
    )


def make_quickstart_agent(model: str) -> Agent[None, QuickstartResult]:
    """Create a quickstart agent."""
    content = _load_skill_content("quickstart")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=QuickstartResult,
        output_retries=2,
    )


def make_building_agent(model: str) -> Agent[None, BuildingResult]:
    """Create a model-building agent."""
    content = _load_skill_content("model-building")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=BuildingResult,
        output_retries=2,
    )


def make_reconciliation_agent(model: str) -> Agent[None, ReconciliationResult]:
    """Create a model-reconciliation agent."""
    content = _load_skill_content("model-reconciliation")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ReconciliationResult,
        output_retries=2,
    )


def make_scenarios_agent(model: str) -> Agent[None, ScenarioResult]:
    """Create a model-scenarios agent."""
    content = _load_skill_content("model-scenarios")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ScenarioResult,
        output_retries=2,
    )


def make_extending_agent(model: str) -> Agent[None, ExtendingResult]:
    """Create an extending-gaspatchio agent."""
    content = _load_skill_content("extending-gaspatchio")
    return Agent(
        model,
        system_prompt=content + _output_instructions(model),
        output_type=ExtendingResult,
        output_retries=2,
    )


AGENT_FACTORIES = {
    "review": make_review_agent,
    "discovery": make_discovery_agent,
    "quickstart": make_quickstart_agent,
    "building": make_building_agent,
    "reconciliation": make_reconciliation_agent,
    "scenarios": make_scenarios_agent,
    "extending": make_extending_agent,
}


def make_agent(skill_name: str, model: str) -> Agent:  # type: ignore[type-arg]
    """Create an agent for the given skill and model."""
    factory = AGENT_FACTORIES[skill_name]
    return factory(model)
