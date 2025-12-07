# ABOUTME: Implementation of describe_scenarios() for audit trail generation.
# ABOUTME: Produces human-readable descriptions of scenario shock configurations.

"""Implementation of describe_scenarios() for audit trail generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from gaspatchio_core.scenarios.shocks import Shock


@overload
def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["text", "markdown"] = "markdown",
) -> str: ...


@overload
def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["dict"],
) -> dict[str, list[str]]: ...


def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["text", "markdown", "dict"] = "markdown",
) -> str | dict[str, list[str]]:
    """
    Generate human-readable descriptions of scenario configurations.

    Creates audit-trail-ready documentation of what shocks are applied
    in each scenario. Useful for governance, compliance, and model
    documentation requirements.

    !!! note "When to use"
        - Generating audit trails for regulatory compliance
        - Documenting scenario configurations in model reports
        - Creating change logs for assumption modifications
        - Building scenario comparison reports

    Args:
        scenarios: Mapping of scenario ID to list of shocks
        output_format: Output format - "markdown" (default), "text", or "dict"

    Returns:
        Formatted description string, or dict for programmatic access

    Examples:
    --------
    **Generate markdown documentation:**

    ```python no_output_check
    from gaspatchio_core.scenarios import describe_scenarios
    from gaspatchio_core.scenarios.shocks import MultiplicativeShock

    scenarios = {
        "BASE": [],
        "STRESSED": [MultiplicativeShock(factor=1.2, table="mortality")],
    }

    print(describe_scenarios(scenarios))
    ```

    **Get as dictionary for programmatic access:**

    ```python no_output_check
    result = describe_scenarios(scenarios, output_format="dict")
    for scenario_id, shocks in result.items():
        print(f"{scenario_id}: {len(shocks)} shocks")
    ```

    """
    if output_format == "dict":
        return _to_dict(scenarios)
    if output_format == "text":
        return _to_text(scenarios)
    # markdown
    return _to_markdown(scenarios)


def _to_dict(scenarios: dict[str, list[Shock]]) -> dict[str, list[str]]:
    """Convert scenarios to dictionary format."""
    result = {}
    for scenario_id, shocks in scenarios.items():
        if shocks:
            result[scenario_id] = [shock.describe() for shock in shocks]
        else:
            result[scenario_id] = ["No shocks (base case)"]
    return result


def _to_text(scenarios: dict[str, list[Shock]]) -> str:
    """Convert scenarios to plain text format."""
    if not scenarios:
        return "No scenarios defined."

    lines = ["Scenario Configuration", "=" * 22, ""]

    for scenario_id, shocks in scenarios.items():
        lines.append(f"Scenario: {scenario_id}")
        if shocks:
            lines.extend(f"  - {shock.describe()}" for shock in shocks)
        else:
            lines.append("  - No shocks (base case)")
        lines.append("")

    return "\n".join(lines)


def _to_markdown(scenarios: dict[str, list[Shock]]) -> str:
    """Convert scenarios to markdown format."""
    if not scenarios:
        return "# Scenario Configuration\n\n*No scenarios defined.*"

    lines = ["# Scenario Configuration", ""]

    for scenario_id, shocks in scenarios.items():
        lines.append(f"## {scenario_id}")
        lines.append("")
        if shocks:
            lines.extend(f"- {shock.describe()}" for shock in shocks)
        else:
            lines.append("- *No shocks (base case)*")
        lines.append("")

    return "\n".join(lines)


__all__ = ["describe_scenarios"]
