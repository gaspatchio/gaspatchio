# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Standalone worker: one assignment-path microbench measurement.

Runs as a plain script — not a `tests.probe` import — so it can be executed
with any target environment's own interpreter, the same way `_engine_check.py`
is:

    <env>/bin/python _microbench_worker.py

Builds a synthetic frame and assigns a mix of columns across the known
operation families (binary-operator chains, `when`/`then`/`otherwise`,
`previous_period`, `cumulative_survival`, `to_monthly`, an assumption-table
`lookup`), timing each assignment. Prints one JSON object to stdout: the
median per-assignment wall time, the total time to build the whole mix, and
how many times the rollforward compiler's `lower_polars` pass ran.

The op mix (`OP_MIX_FAMILIES`) is derived from the framework's own op
census (the expression-producing-definition-site inventory run for the
emission-graph work) rather than seeded evenly — see the constant's own
comment for the derivation and the counts it cites.

Mix parity across sides of a comparison: this file is invoked by absolute
path (`MICROBENCH_WORKER_SCRIPT` in `probe_emission.py`, resolved from
*this* checkout), never copied into or re-read from a `--baseline-worktree`.
A baseline run executes this exact file under the baseline venv's
interpreter — only the installed `gaspatchio` package differs between the
two sides, never the op mix or the measurement code that drives it.

`lower_polars_calls` is a real spy on `gaspatchio.rollforward._passes
.LowerToPolarsPlugin.lower` — today's only code path with that name. None of
the families below drive a `rollforward()`/`accumulate()` compilation, so
this legitimately reads 0 for every run; it is wired now (rather than
omitted) so it starts reporting real numbers without further changes if
ordinary assignments are ever routed through the same pass.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Final

import polars as pl
from loguru import logger

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from collections.abc import Iterator

# Op-mix proportions, derived from the framework's own op census (the
# expression-producing-definition-site inventory taken for the emission-graph
# work: 193 sites across the package, counted by family). Counts per
# family exercised here: 77 operator dunders (BinOp — the arithmetic/
# comparison surface defined independently across ColumnProxy/
# ExpressionProxy/ConditionExpression/ProxyAwareExpr), 9 when/then/
# otherwise sites (WhenThen — the chain-building entry points plus its 5
# branch shapes), 10 projection column-accessor methods, 5 finance
# column+frame-accessor methods, 1 Table.lookup() site.
#
# This microbench exercises one representative method per family. Where a
# family has more distinct methods than are exercised here, its count is
# split evenly across the ones that are, rather than guessing a finer
# split the census does not itself provide: projection's 10 splits 5/5
# across `previous_period` (standing in for the time-shift methods —
# previous_period, next_period, at_period, with_period, with_periods,
# broadcast_to_periods) and `cumulative_survival` (standing in for the
# reduction methods — cumulative_survival, remaining_sum, prospective_value,
# accumulate); finance's 5 goes entirely to `to_monthly`, the only finance
# method exercised here. The weights below are these counts directly, not
# rescaled, so the relative proportions match the census exactly.
OP_MIX_FAMILIES: Final[dict[str, int]] = {
    "binary_operator_chain": 77,
    "when_then_otherwise": 9,
    "previous_period": 5,
    "cumulative_survival": 5,
    "lookup": 1,
    "to_monthly": 5,
}

# Realistic width: close to the ifrs17 reference model's 158 output columns,
# pending the real census.
PERIOD_COUNT: Final[int] = 20
ROW_COUNT: Final[int] = 500


@dataclass(slots=True)
class MicrobenchMeasurement:
    """One environment's assignment-path microbench result."""

    median_assignment_s: float
    plan_build_s: float
    lower_polars_calls: int


@contextmanager
def _spy_lower_polars() -> Iterator[list[int]]:
    """Count real invocations of the rollforward compiler's `lower_polars` pass.

    Yields a single-element list acting as a mutable counter (`calls[0]`),
    restoring the original method on exit regardless of how the `with` block
    ends.
    """
    from gaspatchio.rollforward import _passes

    calls = [0]
    original = _passes.LowerToPolarsPlugin.lower

    def _counting_lower(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        calls[0] += 1
        return original(self, *args, **kwargs)

    _passes.LowerToPolarsPlugin.lower = _counting_lower  # type: ignore[method-assign]
    try:
        yield calls
    finally:
        _passes.LowerToPolarsPlugin.lower = original  # type: ignore[method-assign]


def _build_base_frame(
    row_count: int, period_count: int
) -> tuple[ActuarialFrame, Table]:
    """Build a synthetic frame plus a small assumption table for `lookup`."""
    policy_duration_years = list(range(1, period_count + 1))
    policies_in_force = [
        1000.0 * (0.98**duration) for duration in policy_duration_years
    ]
    mortality_rate = [0.001 + 0.0002 * duration for duration in policy_duration_years]
    lapse_rate = [0.05 for _ in policy_duration_years]
    disc_rate_ann = [0.04 for _ in policy_duration_years]

    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [f"SYNTHETIC_{i:06d}" for i in range(row_count)],
                "policies_in_force": [policies_in_force] * row_count,
                "mortality_rate": [mortality_rate] * row_count,
                "lapse_rate": [lapse_rate] * row_count,
                "disc_rate_ann": [disc_rate_ann] * row_count,
                "policy_duration_years": [policy_duration_years] * row_count,
                "sum_insured": [200_000.0] * row_count,
            }
        )
    )

    mortality_multiplier_source = pl.DataFrame(
        {
            "policy_duration_years": policy_duration_years,
            "mortality_multiplier": [
                1.0 + 0.01 * duration for duration in policy_duration_years
            ],
        }
    )
    mortality_multiplier_table = Table(
        name="synthetic_mortality_multiplier",
        source=mortality_multiplier_source,
        dimensions={"policy_duration_years": "policy_duration_years"},
        value="mortality_multiplier",
    )
    return frame, mortality_multiplier_table


def _run_op_mix(
    frame: ActuarialFrame, table: Table
) -> tuple[ActuarialFrame, list[float]]:
    """Assign the op mix onto `frame`, timing each individual assignment."""
    list_columns = ["policies_in_force", "mortality_rate", "lapse_rate"]
    durations: list[float] = []

    for i in range(OP_MIX_FAMILIES["binary_operator_chain"]):
        source_column = list_columns[i % len(list_columns)]
        column_name = f"synthetic_binary_operator_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = frame[source_column] * 1.05 + frame["sum_insured"] * 0.0001
        durations.append(time.perf_counter() - start)
        list_columns.append(column_name)

    for i in range(OP_MIX_FAMILIES["when_then_otherwise"]):
        source_column = list_columns[i % len(list_columns)]
        column_name = f"synthetic_when_then_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = (
            when(frame[source_column] > 0.5).then(frame[source_column]).otherwise(0.0)
        )
        durations.append(time.perf_counter() - start)
        list_columns.append(column_name)

    for i in range(OP_MIX_FAMILIES["previous_period"]):
        source_column = list_columns[i % len(list_columns)]
        column_name = f"synthetic_previous_period_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = frame[source_column].projection.previous_period()
        durations.append(time.perf_counter() - start)
        list_columns.append(column_name)

    for i in range(OP_MIX_FAMILIES["cumulative_survival"]):
        column_name = f"synthetic_cumulative_survival_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = frame["mortality_rate"].projection.cumulative_survival()
        durations.append(time.perf_counter() - start)
        list_columns.append(column_name)

    for i in range(OP_MIX_FAMILIES["lookup"]):
        column_name = f"synthetic_lookup_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = table.lookup(
            policy_duration_years=frame["policy_duration_years"]
        )
        durations.append(time.perf_counter() - start)

    for i in range(OP_MIX_FAMILIES["to_monthly"]):
        column_name = f"synthetic_to_monthly_column_{i:03d}"
        start = time.perf_counter()
        frame[column_name] = frame["disc_rate_ann"].finance.to_monthly(
            method="compound"
        )
        durations.append(time.perf_counter() - start)

    return frame, durations


def measure_once(
    *, row_count: int = ROW_COUNT, period_count: int = PERIOD_COUNT
) -> MicrobenchMeasurement:
    """Build the synthetic frame, run the op mix once, return the measurement."""
    frame, table = _build_base_frame(row_count, period_count)
    with _spy_lower_polars() as calls:
        start = time.perf_counter()
        _frame, durations = _run_op_mix(frame, table)
        plan_build_s = time.perf_counter() - start

    return MicrobenchMeasurement(
        median_assignment_s=statistics.median(durations),
        plan_build_s=plan_build_s,
        lower_polars_calls=calls[0],
    )


def _configure_result_channel() -> None:
    """Route this worker's JSON result to stdout via loguru, and nothing else there.

    ``logger.remove()`` drops loguru's default (stderr) sink — loguru is a
    process-wide singleton, and gaspatchio's own library code (`Table`,
    `ActuarialFrame`) logs through this same `logger`, so without removing
    the default first, its ordinary DEBUG/INFO chatter could end up
    interleaved with the result. Two sinks replace it, partitioned by the
    same filter in opposite directions: stderr gets everything *except* the
    result record (so ordinary logging keeps working), stdout gets *only*
    the one record this script explicitly binds with ``result_channel=True``,
    formatted as the bare message — so the result is never duplicated onto
    stderr either.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        filter=lambda record: not record["extra"].get("result_channel", False),
    )
    logger.add(
        sys.stdout,
        format="{message}",
        colorize=False,
        filter=lambda record: record["extra"].get("result_channel", False),
    )


def main() -> None:
    """Run one measurement and print it as JSON."""
    _configure_result_channel()
    measurement = measure_once()
    # stdout is this worker's result channel (subprocess-JSON contract with
    # the orchestrator in probe_emission.py); the filtered sink above is what
    # keeps it JSON-only despite sharing loguru with gaspatchio's own logging.
    logger.bind(result_channel=True).info(json.dumps(asdict(measurement)))


if __name__ == "__main__":
    main()
