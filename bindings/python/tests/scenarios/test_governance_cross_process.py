# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Cross-process YAML round-trip governance test for ScenarioRun.
# ABOUTME: Proves bit-exact aggregations + source_sha across fresh interpreters,
# ABOUTME: including custom user-registered aggregators (Welford-Chan Skewness).
# ruff: noqa: S603, S607, PLR0913
"""Cross-process governance test: process A builds + saves; process B reloads + runs."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import Sum
from gaspatchio_core.scenarios._aggregators import (
    _AGGREGATOR_REGISTRY,
    _BaseAggregator,
    scenario_aggregator,
)
from gaspatchio_core.scenarios._run import ScenarioRun

if TYPE_CHECKING:
    from pathlib import Path


# Define the custom Skewness aggregator at module import time so process A
# can reference it. Process B defines an identical copy via the inline script
# we write to tmp_path.
# Guard against duplicate registration in case the module is re-imported.
if "Skewness" not in _AGGREGATOR_REGISTRY:

    @scenario_aggregator("Skewness")
    @dataclass(frozen=True)
    class Skewness(_BaseAggregator):
        """Welford-Chan streaming skewness across scenarios."""

        def create_accumulator(self) -> dict[str, float]:
            """Return the empty Welford accumulator."""
            return {"n": 0.0, "mean": 0.0, "m2": 0.0, "m3": 0.0}

        def add_input(
            self,
            state: dict[str, float],
            value: float,
        ) -> dict[str, float]:
            """Incorporate one observation via Welford online update."""
            v = float(value) if value is not None else 0.0
            n1 = state["n"] + 1.0
            delta = v - state["mean"]
            delta_n = delta / n1
            term1 = delta * delta_n * state["n"]
            new_mean = state["mean"] + delta_n
            new_m3 = (
                state["m3"]
                + term1 * delta_n * (n1 - 2.0)
                - 3.0 * delta_n * state["m2"]
            )
            new_m2 = state["m2"] + term1
            return {"n": n1, "mean": new_mean, "m2": new_m2, "m3": new_m3}

        def merge_accumulators(
            self,
            a: dict[str, float],
            b: dict[str, float],
        ) -> dict[str, float]:
            """Chan-style parallel merge of two Welford accumulators."""
            na, nb = a["n"], b["n"]
            if na == 0:
                return b
            if nb == 0:
                return a
            n = na + nb
            delta = b["mean"] - a["mean"]
            mean = (na * a["mean"] + nb * b["mean"]) / n
            m2 = a["m2"] + b["m2"] + delta * delta * na * nb / n
            m3 = (
                a["m3"]
                + b["m3"]
                + delta**3 * na * nb * (na - nb) / (n * n)
                + 3.0 * delta * (na * b["m2"] - nb * a["m2"]) / n
            )
            return {"n": n, "mean": mean, "m2": m2, "m3": m3}

        def extract_output(self, state: dict[str, float]) -> float:
            """Return population skewness; NaN when n<3 or variance is zero."""
            n, m2, m3 = state["n"], state["m2"], state["m3"]
            if n < 3 or m2 == 0.0:
                return float("nan")
            std = (m2 / n) ** 0.5
            return (m3 / n) / (std**3)

        def canonical_form(self) -> dict[str, Any]:
            """Return the YAML-serialisable descriptor for this aggregator."""
            return {"kind": "Skewness", "column": self.column, "within": self.within}

else:
    # Already registered (e.g., module re-import): retrieve from registry.
    Skewness = _AGGREGATOR_REGISTRY["Skewness"]  # type: ignore[assignment,misc]


# This source string is written to tmp_path and executed by subprocess B.
# It defines the same Skewness aggregator (so the registry has the "Skewness"
# kind), reloads the plan from YAML, and runs it against identical input.
_SUBPROCESS_SCRIPT = """\
from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import (
    _BaseAggregator,
    scenario_aggregator,
)
from gaspatchio_core.scenarios._run import ScenarioRun


@scenario_aggregator("Skewness")
@dataclass(frozen=True)
class Skewness(_BaseAggregator):
    def create_accumulator(self):
        return {"n": 0.0, "mean": 0.0, "m2": 0.0, "m3": 0.0}

    def add_input(self, state, value):
        v = float(value) if value is not None else 0.0
        n1 = state["n"] + 1.0
        delta = v - state["mean"]
        delta_n = delta / n1
        term1 = delta * delta_n * state["n"]
        new_mean = state["mean"] + delta_n
        new_m3 = (
            state["m3"]
            + term1 * delta_n * (n1 - 2.0)
            - 3.0 * delta_n * state["m2"]
        )
        new_m2 = state["m2"] + term1
        return {"n": n1, "mean": new_mean, "m2": new_m2, "m3": new_m3}

    def merge_accumulators(self, a, b):
        na, nb = a["n"], b["n"]
        if na == 0:
            return b
        if nb == 0:
            return a
        n = na + nb
        delta = b["mean"] - a["mean"]
        mean = (na * a["mean"] + nb * b["mean"]) / n
        m2 = a["m2"] + b["m2"] + delta * delta * na * nb / n
        m3 = (
            a["m3"]
            + b["m3"]
            + delta**3 * na * nb * (na - nb) / (n * n)
            + 3.0 * delta * (na * b["m2"] - nb * a["m2"]) / n
        )
        return {"n": n, "mean": mean, "m2": m2, "m3": m3}

    def extract_output(self, state):
        n, m2, m3 = state["n"], state["m2"], state["m3"]
        if n < 3 or m2 == 0.0:
            return float("nan")
        std = (m2 / n) ** 0.5
        return (m3 / n) / (std**3)

    def canonical_form(self):
        return {"kind": "Skewness", "column": self.column, "within": self.within}


def _model_fn(af, *, tables=None, drivers=None):  # noqa: ARG001
    return af.with_columns(pl.col("premium").alias("loss"))


def main():
    yaml_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    mortality = Table(
        name="mortality",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )

    plan = ScenarioRun.from_yaml(yaml_path, base_tables={"mortality": mortality})

    af = ActuarialFrame({
        "policy_id": [1, 2, 3, 4, 5],
        "premium": [100.0, 200.0, 300.0, 400.0, 500.0],
        "age": [30, 31, 30, 31, 30],
    })

    result = plan.run(af, _model_fn, batch_size=1)

    out = {
        "source_sha": plan.source_sha(),
        "aggregations": {k: v for k, v in result.aggregations.items()},
    }
    out_path.write_text(json.dumps(out))


if __name__ == "__main__":
    main()
"""


@pytest.fixture
def mortality_table() -> Table:
    """Two-row mortality assumption table keyed by age."""
    return Table(
        name="mortality",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )


@pytest.fixture
def af() -> ActuarialFrame:
    """Five-policy frame: enough rows for skewness to be non-NaN (n=5 >= 3)."""
    return ActuarialFrame({
        "policy_id": [1, 2, 3, 4, 5],
        "premium": [100.0, 200.0, 300.0, 400.0, 500.0],
        "age": [30, 31, 30, 31, 30],
    })


def _model_fn(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Model function: alias 'premium' as 'loss' for aggregation."""
    return af.with_columns(pl.col("premium").alias("loss"))


def test_cross_process_yaml_round_trip_bit_exact(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Plan saved in process A reloads and runs identically in subprocess B.

    Asserts:
    - ``source_sha()`` is identical across processes.
    - Every scalar aggregation is bit-exact (or both NaN) between process A
      and the subprocess.
    - The subprocess is a real fresh interpreter invocation, not an in-process
      simulation.
    """
    from gaspatchio_core.scenarios.shocks import MultiplicativeShock

    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "STRESS_A": [MultiplicativeShock(factor=1.1, table="mortality")],
            "STRESS_B": [MultiplicativeShock(factor=1.2, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("loss").alias("total"),
            Skewness("loss").alias("skew"),
        ),
        master_seed=42,
    )

    yaml_path = tmp_path / "plan.yaml"
    plan.to_yaml(yaml_path)

    # Process A: run locally for ground truth.
    result_a = plan.run(af, _model_fn, batch_size=1)
    expected_sha = plan.source_sha()
    expected = dict(result_a.aggregations)

    # Process B: subprocess with fresh interpreter (real cross-process test).
    script_path = tmp_path / "subprocess_runner.py"
    script_path.write_text(_SUBPROCESS_SCRIPT)
    out_path = tmp_path / "subprocess_out.json"

    proc = subprocess.run(
        [sys.executable, str(script_path), str(yaml_path), str(out_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            "Subprocess (process B) failed:"
            f"\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    subprocess_result = json.loads(out_path.read_text())

    # SHA identity: both processes must agree on the plan's canonical identity.
    b_sha = subprocess_result["source_sha"]
    assert b_sha == expected_sha, (
        f"source_sha mismatch: A={expected_sha!r}, B={b_sha!r}"
    )

    # Bit-exact aggregation match across process boundary.
    for alias, expected_value in expected.items():
        actual_value = subprocess_result["aggregations"][alias]
        if isinstance(expected_value, float) and math.isnan(expected_value):
            assert isinstance(actual_value, float), (
                f"Aggregation '{alias}': A=NaN but B is not float: {actual_value!r}"
            )
            assert math.isnan(actual_value), (
                f"Aggregation '{alias}': A=NaN but B={actual_value!r}"
            )
        elif isinstance(expected_value, float):
            assert actual_value == expected_value, (
                f"Aggregation '{alias}' diverged: "
                f"A={expected_value!r} vs B={actual_value!r}"
            )
        else:
            # Partitioned (DataFrame) outputs: not included in this scalar-only
            # fixture. If added later, JSON-serialise and compare structurally.
            assert actual_value == expected_value
