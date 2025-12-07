# ABOUTME: Implementation of with_scenarios() for scenario expansion.
# ABOUTME: Cross-joins ActuarialFrame with scenario IDs to enable multi-scenario runs.
# ruff: noqa: FBT001, FBT002, SLF001

"""Implementation of with_scenarios() for scenario expansion."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.frame import ActuarialFrame


def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    *,
    categorical: bool = False,
) -> ActuarialFrame:
    """
    Expand ActuarialFrame across scenarios via cross-join.

    Creates a new ActuarialFrame with len(af) x len(scenario_ids) rows,
    preserving all original columns and adding a scenario_id column.

    This is the fundamental operation for running actuarial models across
    multiple economic scenarios in a single vectorized execution.

    Args:
        af: Input ActuarialFrame to expand
        scenario_ids: List of scenario identifiers (strings or integers)
        scenario_column: Name for the scenario ID column (default: "scenario_id")
        categorical: If True and scenario_ids are strings, use Categorical dtype
                    for better join/groupby performance (default: False)

    Returns:
        ActuarialFrame with expanded rows and scenario_column added.

    Examples:
    --------
    **Basic scenario expansion:**

    ```python
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios import with_scenarios

    # 2 policies
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})

    # Expand to 3 scenarios → 6 rows
    af = with_scenarios(af, ["BASE", "UP", "DOWN"])
    print(af.collect())
    ```

    **Single deterministic scenario (scenario-ready-by-default):**

    ```python
    # Even single-scenario models should use with_scenarios
    af = with_scenarios(af, ["DETERMINISTIC"])
    ```

    **Integer scenarios for stochastic runs:**

    ```python
    # For 10K stochastic scenarios, use integers for performance
    af = with_scenarios(af, list(range(1, 10001)))
    ```

    **Categorical encoding for named scenarios:**

    ```python
    # Use categorical=True for better groupby/join performance with string IDs
    af = with_scenarios(af, ["BASE", "UP", "DOWN"], categorical=True)
    ```

    """
    # Import here to avoid circular dependency
    from gaspatchio_core.frame import ActuarialFrame

    # Create scenarios DataFrame
    scenarios_df = pl.DataFrame({scenario_column: scenario_ids})

    # Apply categorical encoding if requested
    if categorical and scenarios_df[scenario_column].dtype == pl.Utf8:
        scenarios_df = scenarios_df.with_columns(
            pl.col(scenario_column).cast(pl.Categorical)
        )

    # Collect the ActuarialFrame to DataFrame for cross-join
    af_df = af.collect()

    # Perform cross-join to expand rows
    expanded = af_df.join(scenarios_df, how="cross")

    # Return as ActuarialFrame, preserving mode
    return ActuarialFrame(expanded, mode=af._mode, verbose=af._verbose)
