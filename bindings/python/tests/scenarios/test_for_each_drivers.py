# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for for_each_scenario with dict[ID, dict] (drivers) shape.
# ABOUTME: Also covers deterministic per-scenario seed derivation from master_seed.
"""Test for_each_scenario drivers-dict shape + master_seed plumbing."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario
from gaspatchio_core.scenarios._for_each import _per_scenario_seed


@pytest.fixture
def af() -> ActuarialFrame:
    """Two-policy frame for drivers / seed tests."""
    return ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})


def _driver_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict,
) -> ActuarialFrame:
    """Scale ``premium`` by a per-scenario ``factor`` driver."""
    factor = drivers.get("factor", 1.0)
    return af.with_columns((pl.col("premium") * factor).alias("value"))


def test_drivers_dict_shape(af: ActuarialFrame) -> None:
    """Per-scenario drivers forward to model_fn at batch_size=1."""
    drivers_per_scenario = {
        "A": {"factor": 1.0},
        "B": {"factor": 2.0},
        "C": {"factor": 3.0},
    }
    # Each scenario sum = factor x 300; total = (1+2+3) x 300 = 1800.
    result = for_each_scenario(
        af,
        scenarios=drivers_per_scenario,
        model_fn=_driver_model,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
    )
    assert result.aggregations["total"] == pytest.approx(1800.0)


def test_master_seed_derivation_deterministic() -> None:
    """Same (master_seed, scenario_id) -> same 32-bit derived seed."""
    s1 = _per_scenario_seed(master_seed=42, scenario_id="A")
    s2 = _per_scenario_seed(master_seed=42, scenario_id="A")
    assert s1 == s2
    assert 0 <= s1 < 2**32


def test_master_seed_differs_per_scenario() -> None:
    """Different scenario_ids derive different seeds from the same master_seed."""
    s1 = _per_scenario_seed(master_seed=42, scenario_id="A")
    s2 = _per_scenario_seed(master_seed=42, scenario_id="B")
    assert s1 != s2


def test_master_seed_passed_through(af: ActuarialFrame) -> None:
    """master_seed wires a derived rng_seed into drivers for each scenario."""
    received_seeds: dict[str, int | None] = {}

    def capture_model(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict,
    ) -> ActuarialFrame:
        sid = af._df.select("scenario_id").head(1).collect().item()  # noqa: SLF001
        received_seeds[sid] = drivers.get("rng_seed")
        return af.with_columns(pl.col("premium").alias("value"))

    for_each_scenario(
        af,
        scenarios=["X", "Y"],
        model_fn=capture_model,
        aggregations=(Sum("value").alias("total"),),
        master_seed=123,
        batch_size=1,
    )
    assert received_seeds["X"] == _per_scenario_seed(123, "X")
    assert received_seeds["Y"] == _per_scenario_seed(123, "Y")


def test_master_seed_at_batch_size_gt_1_raises(af: ActuarialFrame) -> None:
    """master_seed only injects seed at batch_size=1; >1 must raise."""

    def noop_model(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict,  # noqa: ARG001
    ) -> ActuarialFrame:
        return af.with_columns(pl.col("premium").alias("value"))

    with pytest.raises(ValueError, match="batch_size=1"):
        for_each_scenario(
            af,
            scenarios=["A", "B", "C", "D"],
            model_fn=noop_model,
            aggregations=(Sum("value").alias("total"),),
            master_seed=42,
            batch_size=2,
        )


def test_drivers_shape_at_batch_size_gt_1_raises(af: ActuarialFrame) -> None:
    """drivers-dict shape only flows at batch_size=1; >1 must raise."""

    def noop_model(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict,  # noqa: ARG001
    ) -> ActuarialFrame:
        return af.with_columns(pl.col("premium").alias("value"))

    with pytest.raises(ValueError, match="batch_size=1"):
        for_each_scenario(
            af,
            scenarios={
                "A": {"factor": 1.0},
                "B": {"factor": 2.0},
                "C": {"factor": 3.0},
                "D": {"factor": 4.0},
            },
            model_fn=noop_model,
            aggregations=(Sum("value").alias("total"),),
            batch_size=2,
        )
