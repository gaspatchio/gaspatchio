# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for the for_each_scenario bounded-memory loop primitive.
# ABOUTME: Phase 1 covers the list[ScenarioID] shape only (no shocks / drivers).
"""Test for_each_scenario core loop (Phase 1: list[ID] shape)."""

from __future__ import annotations

import warnings

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import Mean, Sum, for_each_scenario


@pytest.fixture
def af() -> ActuarialFrame:
    """Three-policy ActuarialFrame used across the suite."""
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _identity_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a ``value`` column equal to ``premium`` (per-scenario, identical)."""
    return af.with_columns(pl.col("premium").alias("value"))


def test_list_of_ids_sum_one_batch(af: ActuarialFrame) -> None:
    """Sum aggregator over per-scenario sums: 3 scenarios x 600 = 1800."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_identity_model,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
    )
    assert result.aggregations["total"] == pytest.approx(1800.0)
    assert result.n_scenarios == 3
    assert result.batch_size == 1
    assert result.batch_size_resolution == "manual"


def test_list_of_ids_batched(af: ActuarialFrame) -> None:
    """Mean aggregator with batch_size=2 over 5 scenarios stays bit-equivalent."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C", "D", "E"],
        model_fn=_identity_model,
        aggregations=(Mean("value").alias("avg"),),
        batch_size=2,
    )
    assert result.aggregations["avg"] == pytest.approx(600.0)
    assert result.batch_size == 2


def test_empty_scenarios_raises(af: ActuarialFrame) -> None:
    """Empty scenario list is rejected with the shared validator message."""
    with pytest.raises(ValueError, match="at least one"):
        for_each_scenario(
            af,
            scenarios=[],
            model_fn=_identity_model,
            aggregations=(Sum("value").alias("total"),),
        )


def test_auto_search_does_not_warn(af: ActuarialFrame) -> None:
    """The measured streaming-batch search resolves silently (no spurious warnings)."""
    scenarios = [f"S{i}" for i in range(8)]
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # any UserWarning would fail
        result = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=_identity_model,
            aggregations=(Sum("value").alias("total"),),
            batch_size="auto",
        )
    assert result.batch_size_resolution == "auto_search"


def test_fold_batch_helper_exists() -> None:
    from gaspatchio_core.scenarios import _for_each

    assert hasattr(_for_each, "_fold_batch")
