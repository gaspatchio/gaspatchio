# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Pins the v0.2 public surface (GSP-101). Update __all__ if names change.
"""Public surface smoke test for the v0.2 scenarios module."""

from __future__ import annotations


def test_v02_surface_importable() -> None:
    """All v0.2 public names must import cleanly from gaspatchio_core.scenarios."""
    from gaspatchio_core.scenarios import (
        CTE,
        AdditiveShock,
        Aggregator,
        ArgMax,
        ArgMin,
        ClipShock,
        Count,
        FilteredShock,
        Max,
        MaxShock,
        Mean,
        Median,
        Min,
        MinShock,
        MultiplicativeShock,
        OverrideShock,
        ParameterShock,
        PipelineShock,
        Quantile,
        QuantileRank,
        RelativeFloorShock,
        ScenarioResult,
        ScenarioRun,
        Shock,
        Std,
        Sum,
        TimeConditionalShock,
        Variance,
        for_each_scenario,
        parse_aggregations,
        parse_scenario_config,
        parse_shock_config,
        register_aggregator,
        scenario_aggregator,
        with_scenarios,
    )

    for obj in (
        CTE,
        AdditiveShock,
        Aggregator,
        ArgMax,
        ArgMin,
        ClipShock,
        Count,
        FilteredShock,
        Max,
        MaxShock,
        Mean,
        Median,
        Min,
        MinShock,
        MultiplicativeShock,
        OverrideShock,
        ParameterShock,
        PipelineShock,
        Quantile,
        QuantileRank,
        RelativeFloorShock,
        ScenarioResult,
        ScenarioRun,
        Shock,
        Std,
        Sum,
        TimeConditionalShock,
        Variance,
        for_each_scenario,
        parse_aggregations,
        parse_scenario_config,
        parse_shock_config,
        register_aggregator,
        scenario_aggregator,
        with_scenarios,
    ):
        assert obj is not None


def test_baseaggregator_is_public() -> None:
    """Custom-aggregator authors can import BaseAggregator from the public namespace."""
    from gaspatchio_core.scenarios import BaseAggregator
    from gaspatchio_core.scenarios._aggregators import _BaseAggregator

    assert BaseAggregator is _BaseAggregator


def test_v01_names_removed() -> None:
    """v0.1 names must NOT be importable - clean break per GSP-101 §10."""
    import gaspatchio_core.scenarios as ns

    for retired in (
        "MultiAgg",
        "GroupedAgg",
        "metric",
        "ScenarioMetric",
        "ScenarioAggregator",
    ):
        assert not hasattr(ns, retired), f"{retired} should be removed in v0.2"
