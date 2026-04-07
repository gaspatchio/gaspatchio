"""Structured output types for skill evaluation agents.

Each skill gets a Pydantic model so the agent returns typed data
we can assert on, rather than parsing raw text.
"""

from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    """Structured output from model-review skill."""

    critical_issues: list[str] = Field(
        default_factory=list,
        description="Issues that will produce wrong numbers (map_elements, for-loops, etc.)",
    )
    important_issues: list[str] = Field(
        default_factory=list,
        description="Methodology deviations or code quality issues",
    )
    minor_issues: list[str] = Field(
        default_factory=list,
        description="Documentation gaps, style issues",
    )
    positive_observations: list[str] = Field(
        default_factory=list,
        description="Things the model does well",
    )
    files_reviewed: list[str] = Field(
        default_factory=list,
        description="File paths that were reviewed",
    )


class DiscoveryResult(BaseModel):
    """Structured output from model-discovery skill."""

    questions_asked: list[str] = Field(
        default_factory=list,
        description="Clarifying questions asked before any code",
    )
    tutorial_level_suggested: str | None = Field(
        default=None,
        description="Tutorial level recommended (e.g. 'Level 3')",
    )
    spec_written: bool = Field(
        description="Whether a model specification was produced"
    )
    code_written: bool = Field(
        description="Whether any model code was written (should be False)"
    )


class QuickstartResult(BaseModel):
    """Structured output from quickstart skill."""

    tutorial_level_routed: str = Field(
        description="Tutorial level the user was routed to (e.g. 'Level 1')"
    )
    describe_json_used: bool = Field(
        description="Whether gspio describe --json was recommended"
    )
    reasoning: str = Field(
        description="Why this tutorial level was chosen"
    )


class BuildingResult(BaseModel):
    """Structured output from model-building skill."""

    gspio_docs_consulted: bool = Field(
        description="Whether gspio docs was used before writing code"
    )
    methods_looked_up: list[str] = Field(
        default_factory=list,
        description="API methods verified via gspio docs",
    )
    antipatterns_avoided: list[str] = Field(
        default_factory=list,
        description="Anti-patterns explicitly avoided",
    )


class ReconciliationResult(BaseModel):
    """Structured output from model-reconciliation skill."""

    reference_identified: str = Field(
        description="What reference was identified (e.g. 'lifelib IntegratedLife')"
    )
    variables_compared: list[str] = Field(
        default_factory=list,
        description="Variables that were compared",
    )
    tolerance_stated: bool = Field(
        description="Whether a numeric tolerance was stated"
    )
    build_log_created: bool = Field(
        description="Whether a build log was created/referenced"
    )


class ExtendingResult(BaseModel):
    """Structured output from extending-gaspatchio skill."""

    placement_level: int = Field(
        description=(
            "Performance ladder level: 1=already exists, 2=inline/too simple, "
            "3=setup utility, 4=needs Rust, 5=column accessor, 6=frame accessor"
        ),
    )
    placement_reasoning: str = Field(
        description="Why this level was chosen",
    )
    is_accessor: bool = Field(
        description="Whether the agent decided to build an accessor (Level 5 or 6)",
    )
    uses_antipattern: bool = Field(
        description=(
            "Whether the proposed code uses map_elements, apply, iter_rows, "
            "or Python for-loops over policies/timesteps"
        ),
    )
    handles_list_columns: bool = Field(
        description=(
            "If accessor: whether it handles both scalar and list columns. "
            "Set True if not an accessor (not applicable)."
        ),
    )
    existing_method_checked: bool = Field(
        description="Whether gspio docs or grep was used to check for existing methods",
    )


class ScenarioResult(BaseModel):
    """Structured output from model-scenarios skill."""

    model_py_modified: bool = Field(
        description="Whether model.py was modified (should be False)"
    )
    run_scenarios_created: bool = Field(
        description="Whether a run_scenarios.py was created"
    )
    report_generated: bool = Field(
        description="Whether a report was generated"
    )
    chart_types: list[str] = Field(
        default_factory=list,
        description="Types of charts produced (tornado, waterfall, etc.)",
    )
    audit_trail_included: bool = Field(
        description="Whether describe_scenarios() audit trail was included"
    )
