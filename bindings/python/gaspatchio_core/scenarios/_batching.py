# ABOUTME: Implementation of batch_scenarios() for memory-efficient processing.
# ABOUTME: Yields batches of scenario IDs for iterative large stochastic runs.

"""Implementation of batch_scenarios() for memory-efficient scenario processing."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterator

T = TypeVar("T", str, int)


def batch_scenarios(
    scenario_ids: list[T],
    batch_size: int = 1000,
) -> Iterator[list[T]]:
    """
    Yield batches of scenario IDs for memory-efficient processing.

    For large stochastic runs (e.g., 10,000+ scenarios), processing all scenarios
    at once may exceed available memory. This generator yields chunks of scenario
    IDs that can be processed iteratively and aggregated.

    Args:
        scenario_ids: Complete list of scenario identifiers to batch
        batch_size: Number of scenarios per batch (default: 1000)

    Yields:
        Lists of scenario IDs, each containing up to batch_size elements.
        The last batch may contain fewer elements.

    Raises:
        ValueError: If batch_size is not positive

    !!! note "When to use"
        - Processing 1000+ stochastic scenarios
        - Memory-constrained environments
        - Parallel processing with worker pools
        - Progress reporting during long runs

    Examples:
    --------
    **Basic batching for large stochastic runs:**

    ```python no_output_check
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios import batch_scenarios, with_scenarios

    model_points = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
    scenario_ids = list(range(1, 10001))  # 10K scenarios

    all_results = []
    for batch in batch_scenarios(scenario_ids, batch_size=1000):
        af = with_scenarios(model_points, batch)
        # Run model and collect results
        all_results.append(af.collect())
    ```

    **With progress reporting:**

    ```python no_output_check
    total_scenarios = 5000
    scenario_ids = list(range(1, total_scenarios + 1))

    for i, batch in enumerate(batch_scenarios(scenario_ids, batch_size=500)):
        print(f"Processing batch {i + 1}/10: scenarios {batch[0]}-{batch[-1]}")
        # Process batch...
    ```

    """
    if batch_size <= 0:
        msg = f"batch_size must be positive, got {batch_size}"
        raise ValueError(msg)

    for i in range(0, len(scenario_ids), batch_size):
        yield scenario_ids[i : i + batch_size]
