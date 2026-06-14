# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for enhanced shock system (GSP-71): clip, pipeline, where, when.
# ABOUTME: Verifies Solvency II SCR scenarios can be expressed declaratively.

"""Tests for enhanced shock system (GSP-71).

This module tests the full range of actuarial stress testing capabilities:
- GSP-72: clip operation (value constraints)
- GSP-65: where clause (dimension-filtered shocks)
- GSP-74: when clause (time-conditional shocks)
- GSP-75: pipeline (composable operations)
"""

import polars as pl
import pytest

from gaspatchio_core.scenarios import ScenarioRun, parse_shock_config
from gaspatchio_core.scenarios._aggregators import Sum
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    ParameterShock,
    PipelineShock,
    Shock,
    TimeConditionalShock,
)


class TestClipShock:
    """Tests for ClipShock - GSP-72."""

    def test_clip_max_only(self):
        """ClipShock with max_value only caps values above."""
        shock = ClipShock(max_value=1.0)
        values = pl.Series("rate", [0.5, 0.8, 1.2, 1.5])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("clipped"))

        assert result["clipped"].to_list() == [0.5, 0.8, 1.0, 1.0]

    def test_clip_min_only(self):
        """ClipShock with min_value only floors values below."""
        shock = ClipShock(min_value=0.001)
        values = pl.Series("rate", [0.0001, 0.0005, 0.001, 0.01])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("clipped"))

        assert result["clipped"].to_list() == [0.001, 0.001, 0.001, 0.01]

    def test_clip_both_bounds(self):
        """ClipShock with both min and max values."""
        shock = ClipShock(min_value=0.0, max_value=1.0)
        values = pl.Series("rate", [-0.1, 0.5, 1.5])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("clipped"))

        assert result["clipped"].to_list() == [0.0, 0.5, 1.0]

    def test_clip_requires_at_least_one_bound(self):
        """ClipShock must have at least one of min_value or max_value."""
        with pytest.raises(ValueError, match="at least one of min_value or max_value"):
            ClipShock()

    def test_clip_min_cannot_exceed_max(self):
        """ClipShock min_value cannot be greater than max_value."""
        with pytest.raises(ValueError, match="cannot exceed"):
            ClipShock(min_value=1.0, max_value=0.5)

    def test_clip_describe(self):
        """ClipShock has descriptive string representation."""
        shock = ClipShock(max_value=1.0, table="lapse")
        desc = shock.describe()
        assert "clip" in desc.lower()
        assert "1.0" in desc

    def test_clip_is_shock(self):
        """ClipShock is a Shock subclass."""
        shock = ClipShock(max_value=1.0)
        assert isinstance(shock, Shock)


class TestPipelineShock:
    """Tests for PipelineShock - GSP-75."""

    def test_pipeline_multiply_then_clip(self):
        """Pipeline: multiply by 1.5 then cap at 1.0 (Solvency II lapse up)."""
        shock = PipelineShock(
            shocks=(
                MultiplicativeShock(factor=1.5),
                ClipShock(max_value=1.0),
            )
        )
        values = pl.Series("rate", [0.5, 0.7, 0.9])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # 0.5 * 1.5 = 0.75 (no cap)
        # 0.7 * 1.5 = 1.05 → 1.0 (capped)
        # 0.9 * 1.5 = 1.35 → 1.0 (capped)
        assert result["shocked"].to_list() == pytest.approx([0.75, 1.0, 1.0])

    def test_pipeline_add_then_clip(self):
        """Pipeline: add 0.05 then floor at 0."""
        shock = PipelineShock(
            shocks=(
                AdditiveShock(delta=-0.05),
                ClipShock(min_value=0.0),
            )
        )
        values = pl.Series("rate", [0.02, 0.05, 0.10])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # 0.02 - 0.05 = -0.03 → 0.0 (floored)
        # 0.05 - 0.05 = 0.0 (no floor needed)
        # 0.10 - 0.05 = 0.05 (no floor needed)
        assert result["shocked"].to_list() == pytest.approx([0.0, 0.0, 0.05])

    def test_pipeline_requires_at_least_one_shock(self):
        """PipelineShock requires at least one shock."""
        with pytest.raises(ValueError, match="at least one shock"):
            PipelineShock(shocks=())

    def test_pipeline_describe(self):
        """PipelineShock has descriptive string representation."""
        shock = PipelineShock(
            shocks=(
                MultiplicativeShock(factor=1.5),
                ClipShock(max_value=1.0),
            ),
            table="lapse",
        )
        desc = shock.describe()
        assert "pipeline" in desc.lower()
        assert "→" in desc  # Arrow between steps


class TestFilteredShock:
    """Tests for FilteredShock - GSP-65 (where clause)."""

    def test_filtered_by_equality(self):
        """FilteredShock applies only to rows matching equality filter."""
        shock = FilteredShock(
            shock=MultiplicativeShock(factor=1.5),
            where={"product": "TERM"},
        )

        rates = pl.DataFrame({
            "product": ["TERM", "WL", "TERM", "WL"],
            "rate": [0.10, 0.05, 0.08, 0.04],
        })

        result = rates.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # Only TERM products should be shocked
        expected = [0.15, 0.05, 0.12, 0.04]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_filtered_by_comparison(self):
        """FilteredShock with comparison operator (lte)."""
        shock = FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"duration": {"lte": 3}},
        )

        lapse_by_duration = pl.DataFrame({
            "duration": [1, 2, 3, 4, 5],
            "rate": [0.10, 0.08, 0.06, 0.05, 0.04],
        })

        result = lapse_by_duration.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # Only durations <= 3 should be shocked
        expected = [0.10 * 1.25, 0.08 * 1.25, 0.06 * 1.25, 0.05, 0.04]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_filtered_by_between(self):
        """FilteredShock with between operator."""
        shock = FilteredShock(
            shock=AdditiveShock(delta=0.01),
            where={"age": {"between": [30, 50]}},
        )

        mortality_by_age = pl.DataFrame({
            "age": [25, 30, 40, 50, 60],
            "rate": [0.001, 0.002, 0.004, 0.008, 0.015],
        })

        result = mortality_by_age.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # Only ages 30-50 should be shocked
        expected = [0.001, 0.012, 0.014, 0.018, 0.015]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_filtered_multiple_conditions(self):
        """FilteredShock with multiple conditions (AND)."""
        shock = FilteredShock(
            shock=MultiplicativeShock(factor=1.20),
            where={"sex": "F", "smoker": "NS"},
        )

        segment_rates = pl.DataFrame({
            "sex": ["M", "F", "F", "M"],
            "smoker": ["NS", "S", "NS", "NS"],
            "rate": [0.01, 0.02, 0.015, 0.012],
        })

        result = segment_rates.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # Only female non-smokers should be shocked
        expected = [0.01, 0.02, 0.015 * 1.20, 0.012]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_filtered_describe(self):
        """FilteredShock has descriptive string representation."""
        shock = FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"duration": {"lte": 3}},
            table="lapse",
        )
        desc = shock.describe()
        assert "WHERE" in desc
        assert "duration" in desc


class TestTimeConditionalShock:
    """Tests for TimeConditionalShock - GSP-74 (when clause)."""

    def test_time_conditional_at_t0(self):
        """TimeConditionalShock applies only at t=0."""
        shock = TimeConditionalShock(
            shock=AdditiveShock(delta=0.40),  # 40% mass lapse
            when={"t": {"eq": 0}},
        )

        lapse_proj = pl.DataFrame({
            "t": [0, 1, 2, 3],
            "rate": [0.05, 0.05, 0.05, 0.05],
        })

        result = lapse_proj.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # Only t=0 should have the 40% mass lapse
        expected = [0.45, 0.05, 0.05, 0.05]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_time_conditional_range(self):
        """TimeConditionalShock applies during a time range."""
        shock = TimeConditionalShock(
            shock=MultiplicativeShock(factor=1.10),
            when={"t": {"lte": 5}},
        )

        lapse_proj = pl.DataFrame({
            "t": [1, 3, 5, 7, 10],
            "rate": [0.10, 0.10, 0.10, 0.10, 0.10],
        })

        result = lapse_proj.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked_rate")
        )

        # t <= 5 should be shocked
        expected = [0.11, 0.11, 0.11, 0.10, 0.10]
        assert result["shocked_rate"].to_list() == pytest.approx(expected)

    def test_time_conditional_describe(self):
        """TimeConditionalShock has descriptive string representation."""
        shock = TimeConditionalShock(
            shock=AdditiveShock(delta=0.40),
            when={"t": {"eq": 0}},
            table="lapse",
        )
        desc = shock.describe()
        assert "WHEN" in desc
        assert "t" in desc


class TestMaxMinShock:
    """Tests for MaxShock and MinShock."""

    def test_max_shock_lapse_down(self):
        """MaxShock for Solvency II lapse down: max(x0.5, -0.2)."""
        shock = MaxShock(
            shock_a=MultiplicativeShock(factor=0.5),
            shock_b=AdditiveShock(delta=-0.2),
        )

        # Test cases:
        # rate=0.60: max(0.60*0.5=0.30, 0.60-0.2=0.40) = 0.40
        # rate=0.30: max(0.30*0.5=0.15, 0.30-0.2=0.10) = 0.15
        # rate=0.10: max(0.10*0.5=0.05, 0.10-0.2=-0.10) = 0.05
        values = pl.Series("rate", [0.60, 0.30, 0.10])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        expected = [0.40, 0.15, 0.05]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_min_shock(self):
        """MinShock takes the smaller of two transformations."""
        shock = MinShock(
            shock_a=MultiplicativeShock(factor=1.5),
            shock_b=OverrideShock(value=0.1),
        )

        values = pl.Series("rate", [0.05, 0.07, 0.10])

        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # 0.05 * 1.5 = 0.075 < 0.1 → 0.075
        # 0.07 * 1.5 = 0.105 > 0.1 → 0.1
        # 0.10 * 1.5 = 0.15 > 0.1 → 0.1
        expected = [0.075, 0.1, 0.1]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_max_shock_describe(self):
        """MaxShock has descriptive string representation."""
        shock = MaxShock(
            shock_a=MultiplicativeShock(factor=0.5),
            shock_b=AdditiveShock(delta=-0.2),
            table="lapse",
        )
        desc = shock.describe()
        assert "max" in desc.lower()


class TestParseShockConfigExtended:
    """Tests for extended parse_shock_config functionality."""

    def test_parse_simple_multiply(self):
        """Parse simple multiplicative shock (backward compatible)."""
        config = {"table": "mortality", "multiply": 1.2}
        shock = parse_shock_config(config)
        assert isinstance(shock, MultiplicativeShock)
        assert shock.factor == 1.2

    def test_parse_pipeline(self):
        """Parse pipeline config."""
        config = {
            "table": "lapse",
            "pipeline": [
                {"multiply": 1.5},
                {"clip": {"max": 1.0}},
            ]
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, PipelineShock)
        assert len(shock.shocks) == 2

    def test_parse_syntactic_sugar_with_clip(self):
        """Parse multiply + clip as syntactic sugar."""
        config = {"table": "lapse", "multiply": 1.5, "clip": [None, 1.0]}
        shock = parse_shock_config(config)
        assert isinstance(shock, PipelineShock)
        assert len(shock.shocks) == 2

    def test_parse_max_operation(self):
        """Parse max operation for lapse down."""
        config = {
            "table": "lapse",
            "max": [
                {"multiply": 0.5},
                {"add": -0.2},
            ]
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, MaxShock)

    def test_parse_where_clause(self):
        """Parse shock with where clause."""
        config = {
            "table": "lapse",
            "multiply": 1.25,
            "where": {"duration": {"lte": 3}},
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, FilteredShock)

    def test_parse_when_clause(self):
        """Parse shock with when clause."""
        config = {
            "table": "lapse",
            "add": 0.40,
            "when": {"t": {"eq": 0}},
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, TimeConditionalShock)

    def test_parse_combined_where_and_when(self):
        """Parse shock with both where and when clauses."""
        config = {
            "table": "lapse",
            "multiply": 1.5,
            "where": {"product": "TERM"},
            "when": {"t": {"lte": 5}},
        }
        shock = parse_shock_config(config)
        # Should be TimeConditionalShock wrapping FilteredShock
        assert isinstance(shock, TimeConditionalShock)
        assert isinstance(shock.shock, FilteredShock)

    def test_parse_clip_dict_format(self):
        """Parse clip with dict format."""
        config = {
            "table": "rates",
            "clip": {"min": 0.0, "max": 1.0},
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, ClipShock)
        assert shock.min_value == 0.0
        assert shock.max_value == 1.0

    def test_parse_clip_array_format(self):
        """Parse clip with array format."""
        config = {
            "table": "rates",
            "clip": [0.01, 0.99],
        }
        shock = parse_shock_config(config)
        assert isinstance(shock, ClipShock)
        assert shock.min_value == 0.01
        assert shock.max_value == 0.99


class TestSolvency2SCRScenarios:
    """Integration tests for Solvency II SCR scenarios from the issue."""

    def test_lapse_up_scenario(self):
        """Solvency II lapse up: min(lapse * 1.5, 1.0)."""
        config = {
            "table": "lapse",
            "pipeline": [
                {"multiply": 1.5},
                {"clip": {"max": 1.0}},
            ]
        }
        shock = parse_shock_config(config)

        lapse_rates = pl.DataFrame({"rate": [0.5, 0.7, 0.9, 1.0]})
        result = lapse_rates.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked")
        )

        # 0.5 * 1.5 = 0.75 (no cap)
        # 0.7 * 1.5 = 1.05 -> 1.0 (capped)
        # 0.9 * 1.5 = 1.35 -> 1.0 (capped)
        # 1.0 * 1.5 = 1.50 -> 1.0 (capped)
        expected = [0.75, 1.0, 1.0, 1.0]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_lapse_down_scenario(self):
        """Solvency II lapse down: max(lapse * 0.5, lapse - 0.2)."""
        config = {
            "table": "lapse",
            "max": [
                {"multiply": 0.5},
                {"add": -0.2},
            ]
        }
        shock = parse_shock_config(config)

        # Test at various lapse levels
        lapse_rates = pl.DataFrame({"rate": [0.60, 0.30, 0.10, 0.05]})
        result = lapse_rates.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked")
        )

        # 0.60: max(0.30, 0.40) = 0.40
        # 0.30: max(0.15, 0.10) = 0.15
        # 0.10: max(0.05, -0.10) = 0.05
        # 0.05: max(0.025, -0.15) = 0.025
        expected = [0.40, 0.15, 0.05, 0.025]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_mass_lapse_scenario(self):
        """Solvency II mass lapse: 40% surrender at t=0 only."""
        config = {
            "table": "lapse",
            "add": 0.40,
            "when": {"t": {"eq": 0}},
        }
        shock = parse_shock_config(config)

        lapse_proj = pl.DataFrame({
            "t": [0, 1, 2, 3],
            "rate": [0.05, 0.05, 0.04, 0.04],
        })
        result = lapse_proj.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked")
        )

        # Only t=0 gets the mass lapse
        expected = [0.45, 0.05, 0.04, 0.04]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_expense_inflation_scenario(self):
        """Solvency II expense inflation: infl_rate + 1%."""
        config = {
            "table": "inflation",
            "add": 0.01,
        }
        shock = parse_shock_config(config)

        infl_rates = pl.DataFrame({"rate": [0.02, 0.025, 0.03]})
        result = infl_rates.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked")
        )

        expected = [0.03, 0.035, 0.04]
        assert result["shocked"].to_list() == pytest.approx(expected)

    def test_early_duration_lapse_stress(self):
        """Early duration lapse stress with where clause."""
        config = {
            "table": "lapse",
            "multiply": 1.25,
            "where": {"duration": {"lte": 3}},
        }
        shock = parse_shock_config(config)

        lapse_by_duration = pl.DataFrame({
            "duration": [1, 2, 3, 4, 5],
            "rate": [0.10, 0.08, 0.06, 0.05, 0.04],
        })
        result = lapse_by_duration.with_columns(
            shock.to_expression(pl.col("rate")).alias("shocked")
        )

        expected = [0.125, 0.10, 0.075, 0.05, 0.04]
        assert result["shocked"].to_list() == pytest.approx(expected)


class TestParameterShock:
    """Tests for ParameterShock - GSP-73."""

    def test_parameter_shock_multiply(self):
        """ParameterShock with multiply operation."""
        shock = ParameterShock(param="discount_spread", operation="multiply", value=1.5)

        result = shock.apply(0.02)
        assert result == pytest.approx(0.03)

    def test_parameter_shock_add(self):
        """ParameterShock with add operation."""
        shock = ParameterShock(param="expense_inflation", operation="add", value=0.01)

        result = shock.apply(0.02)
        assert result == pytest.approx(0.03)

    def test_parameter_shock_set(self):
        """ParameterShock with set operation."""
        shock = ParameterShock(
            param="mortality_improvement", operation="set", value=0.0
        )

        result = shock.apply(0.005)
        assert result == 0.0

    def test_parameter_shock_invalid_operation(self):
        """ParameterShock rejects invalid operations."""
        with pytest.raises(ValueError, match="operation must be one of"):
            ParameterShock(param="test", operation="invalid", value=1.0)

    def test_parameter_shock_describe(self):
        """ParameterShock has descriptive string representation."""
        shock = ParameterShock(param="expense_inflation", operation="add", value=0.01)
        desc = shock.describe()
        assert "param" in desc.lower()
        assert "expense_inflation" in desc

    def test_parse_parameter_shock_add(self):
        """Parse parameter shock with add operation."""
        config = {"param": "infl_rate", "add": 0.01}
        shock = parse_shock_config(config)
        assert isinstance(shock, ParameterShock)
        assert shock.param == "infl_rate"
        assert shock.operation == "add"
        assert shock.value == 0.01

    def test_parse_parameter_shock_multiply(self):
        """Parse parameter shock with multiply operation."""
        config = {"param": "discount_spread", "multiply": 1.5}
        shock = parse_shock_config(config)
        assert isinstance(shock, ParameterShock)
        assert shock.operation == "multiply"

    def test_parse_parameter_shock_set(self):
        """Parse parameter shock with set operation."""
        config = {"param": "mort_improvement", "set": 0.0}
        shock = parse_shock_config(config)
        assert isinstance(shock, ParameterShock)
        assert shock.operation == "set"


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with existing shock configs."""

    def test_simple_multiply_unchanged(self):
        """Simple multiply config works as before."""
        config = {"table": "mortality", "multiply": 1.15}
        shock = parse_shock_config(config)
        assert isinstance(shock, MultiplicativeShock)

    def test_simple_add_unchanged(self):
        """Simple add config works as before."""
        config = {"table": "rates", "add": 0.005}
        shock = parse_shock_config(config)
        assert isinstance(shock, AdditiveShock)

    def test_simple_set_unchanged(self):
        """Simple set config works as before."""
        config = {"table": "lapse", "set": 0.0}
        shock = parse_shock_config(config)
        assert isinstance(shock, OverrideShock)

    def test_table_required(self):
        """Table is still required."""
        with pytest.raises(ValueError, match="table"):
            parse_shock_config({"multiply": 1.2})

    def test_operation_required(self):
        """At least one operation is still required."""
        with pytest.raises(ValueError, match="operation"):
            parse_shock_config({"table": "test"})

    def test_table_or_param_required(self):
        """Config must have either 'table' or 'param'."""
        with pytest.raises(ValueError, match="table.*param"):
            parse_shock_config({"multiply": 1.2})


class TestShockDescribeWithNewShocks:
    """Tests that each enhanced shock type provides a human-readable describe()."""

    def test_describe_pipeline_shock(self):
        """PipelineShock.describe() shows composition."""
        shock = PipelineShock(
            shocks=(
                MultiplicativeShock(factor=1.5),
                ClipShock(max_value=1.0),
            ),
            table="lapse",
        )
        desc = shock.describe()
        assert "pipeline" in desc.lower()
        assert "→" in desc

    def test_describe_filtered_shock(self):
        """FilteredShock.describe() shows the WHERE clause."""
        shock = FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"duration": {"lte": 3}},
            table="lapse",
        )
        assert "WHERE" in shock.describe()

    def test_describe_time_conditional_shock(self):
        """TimeConditionalShock.describe() shows the WHEN clause."""
        shock = TimeConditionalShock(
            shock=AdditiveShock(delta=0.40),
            when={"t": {"eq": 0}},
            table="lapse",
        )
        assert "WHEN" in shock.describe()

    def test_describe_max_shock(self):
        """MaxShock.describe() shows the max combinator."""
        shock = MaxShock(
            shock_a=MultiplicativeShock(factor=0.5),
            shock_b=AdditiveShock(delta=-0.2),
            table="lapse",
        )
        assert "max" in shock.describe().lower()

    def test_scenario_run_summary_for_solvency2_config(self):
        """ScenarioRun summarises a complete Solvency II SCR config."""
        scenarios = {
            "BASE": [],
            "LAPSE_UP": [
                PipelineShock(
                    shocks=(
                        MultiplicativeShock(factor=1.5),
                        ClipShock(max_value=1.0),
                    ),
                    table="lapse",
                )
            ],
            "LAPSE_DOWN": [
                MaxShock(
                    shock_a=MultiplicativeShock(factor=0.5),
                    shock_b=AdditiveShock(delta=-0.2),
                    table="lapse",
                )
            ],
            "MASS_LAPSE": [
                TimeConditionalShock(
                    shock=AdditiveShock(delta=0.40),
                    when={"t": {"eq": 0}},
                    table="lapse",
                )
            ],
        }

        agg = Sum("dummy").alias("dummy")
        plan = ScenarioRun(shocks=scenarios, base_tables={}, aggregations=(agg,))
        summary = plan.describe()
        assert "scenarios=4" in summary
        assert "sha=sha256:" in summary

        canon_keys = set(plan.canonical_form()["shocks"].keys())
        assert canon_keys == {"BASE", "LAPSE_UP", "LAPSE_DOWN", "MASS_LAPSE"}


def test_all_shock_types_importable():
    """All new shock types are importable from scenarios module."""
    from gaspatchio_core.scenarios import (
        AdditiveShock,
        ClipShock,
        FilteredShock,
        MaxShock,
        MinShock,
        MultiplicativeShock,
        OverrideShock,
        ParameterShock,
        PipelineShock,
        Shock,
        TimeConditionalShock,
    )

    # Verify all types are present and non-None
    assert AdditiveShock is not None
    assert ClipShock is not None
    assert FilteredShock is not None
    assert MaxShock is not None
    assert MinShock is not None
    assert MultiplicativeShock is not None
    assert OverrideShock is not None
    assert ParameterShock is not None
    assert PipelineShock is not None
    assert Shock is not None
    assert TimeConditionalShock is not None
