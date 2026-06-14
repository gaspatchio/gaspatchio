# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Subprocess entry point for memory-bounded ScenarioRun benchmarks.
# ABOUTME: Run as a child process and let the parent measure peak RSS via getrusage.

"""Inner runner for ScenarioRun scaling benchmarks (called by subprocess)."""

from __future__ import annotations

import json
import sys
import time

import polars as pl

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario


def main() -> None:
    """Run a single ScenarioRun loop based on JSON spec from argv[1]."""
    spec = json.loads(sys.argv[1])
    n_policies = spec["n_policies"]
    n_scenarios = spec["n_scenarios"]
    batch_size = spec["batch_size"]

    af = ActuarialFrame(
        {
            "policy_id": list(range(n_policies)),
            "premium": [100.0 + i for i in range(n_policies)],
        },
    )

    def model_fn(af, *, tables, drivers):  # noqa: ANN202, ARG001
        return af.with_columns(pl.col("premium").alias("value"))

    started = time.perf_counter()
    result = for_each_scenario(
        af,
        scenarios=list(range(n_scenarios)),
        model_fn=model_fn,
        aggregations=(Sum("value").alias("total"),),
        batch_size=batch_size,
    )
    elapsed = time.perf_counter() - started

    sys.stdout.write(
        json.dumps(
            {
                "wall_time_s": elapsed,
                "n_scenarios": result.n_scenarios,
                "batch_size": result.batch_size,
                "aggregations": result.aggregations,
            },
        ),
    )


if __name__ == "__main__":
    main()
