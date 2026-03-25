# ABOUTME: Tests for LLM-friendly scenario config parsing.
# ABOUTME: Validates conversion of dict/JSON configs to Shock objects.
"""Tests for LLM-friendly scenario config parsing."""

import pytest

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
)


class TestParseShockConfig:
    """Tests for parsing individual shock configurations."""

    def test_parse_multiplicative_shock(self):
        """Parse multiply shock from dict."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "mortality", "multiply": 1.2}
        shock = parse_shock_config(config)

        assert isinstance(shock, MultiplicativeShock)
        assert shock.factor == 1.2
        assert shock.table == "mortality"

    def test_parse_additive_shock(self):
        """Parse add shock from dict."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "discount_rates", "add": 0.005}
        shock = parse_shock_config(config)

        assert isinstance(shock, AdditiveShock)
        assert shock.delta == 0.005
        assert shock.table == "discount_rates"

    def test_parse_override_shock(self):
        """Parse set/override shock from dict."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "lapse", "set": 0.0}
        shock = parse_shock_config(config)

        assert isinstance(shock, OverrideShock)
        assert shock.value == 0.0
        assert shock.table == "lapse"

    def test_parse_shock_with_column(self):
        """Parse shock targeting specific column."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "mortality", "column": "qx", "multiply": 1.2}
        shock = parse_shock_config(config)

        assert isinstance(shock, MultiplicativeShock)
        assert shock.table == "mortality"
        assert shock.column == "qx"

    def test_parse_shock_missing_table(self):
        """Shock config without table should raise error."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"multiply": 1.2}  # Missing table

        with pytest.raises(ValueError, match="table"):
            parse_shock_config(config)

    def test_parse_shock_no_operation(self):
        """Shock config without operation should raise error."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "mortality"}  # No multiply/add/set

        with pytest.raises(ValueError, match="operation"):
            parse_shock_config(config)

    def test_parse_shock_multiple_operations(self):
        """Shock config with multiple operations should raise error."""
        from gaspatchio_core.scenarios import parse_shock_config

        config = {"table": "mortality", "multiply": 1.2, "add": 0.01}

        with pytest.raises(ValueError, match="multiple"):
            parse_shock_config(config)


class TestParseScenarioConfig:
    """Tests for parsing full scenario configurations."""

    def test_parse_string_scenario(self):
        """Parse simple string scenario ID (no shocks)."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = ["BASE"]
        result = parse_scenario_config(config)

        assert "BASE" in result
        assert result["BASE"] == []

    def test_parse_dict_scenario_no_shocks(self):
        """Parse dict scenario with no shocks."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = [{"id": "BASE"}]
        result = parse_scenario_config(config)

        assert "BASE" in result
        assert result["BASE"] == []

    def test_parse_dict_scenario_with_shocks(self):
        """Parse dict scenario with shock list."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = [
            {"id": "BASE"},
            {
                "id": "STRESS",
                "shocks": [{"table": "mortality", "multiply": 1.2}],
            },
        ]
        result = parse_scenario_config(config)

        assert "BASE" in result
        assert result["BASE"] == []
        assert "STRESS" in result
        assert len(result["STRESS"]) == 1
        assert isinstance(result["STRESS"][0], MultiplicativeShock)
        assert result["STRESS"][0].factor == 1.2

    def test_parse_multiple_shocks(self):
        """Parse scenario with multiple shocks."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = [
            {
                "id": "ADVERSE",
                "shocks": [
                    {"table": "mortality", "multiply": 1.2},
                    {"table": "lapse", "multiply": 0.8},
                    {"table": "interest", "add": -0.01},
                ],
            },
        ]
        result = parse_scenario_config(config)

        assert len(result["ADVERSE"]) == 3
        assert isinstance(result["ADVERSE"][0], MultiplicativeShock)
        assert isinstance(result["ADVERSE"][1], MultiplicativeShock)
        assert isinstance(result["ADVERSE"][2], AdditiveShock)

    def test_parse_mixed_string_and_dict(self):
        """Parse config with mix of string and dict scenarios."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = [
            "BASE",
            {"id": "UP", "shocks": [{"table": "rates", "add": 0.01}]},
            "DOWN_MANUAL",
        ]
        result = parse_scenario_config(config)

        assert len(result) == 3
        assert result["BASE"] == []
        assert len(result["UP"]) == 1
        assert result["DOWN_MANUAL"] == []

    def test_parse_empty_config(self):
        """Empty config should raise error."""
        from gaspatchio_core.scenarios import parse_scenario_config

        with pytest.raises(ValueError, match="empty"):
            parse_scenario_config([])

    def test_parse_duplicate_scenario_ids(self):
        """Duplicate scenario IDs should raise error."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = ["BASE", {"id": "BASE"}]

        with pytest.raises(ValueError, match="[Dd]uplicate"):
            parse_scenario_config(config)

    def test_parse_dict_missing_id(self):
        """Dict scenario without id should raise error."""
        from gaspatchio_core.scenarios import parse_scenario_config

        config = [{"shocks": [{"table": "mortality", "multiply": 1.2}]}]

        with pytest.raises(ValueError, match="id"):
            parse_scenario_config(config)


class TestLLMWorkflowIntegration:
    """Integration tests for LLM-generated scenario workflow."""

    def test_llm_generated_config_to_describe(self):
        """LLM config can be parsed and described."""
        from gaspatchio_core.scenarios import (
            describe_scenarios,
            parse_scenario_config,
        )

        # LLM generates this JSON-like config
        config = [
            {"id": "BASE"},
            {
                "id": "RATES_UP_50BPS",
                "shocks": [{"table": "discount_rates", "add": 0.005}],
            },
        ]

        # Parse and describe
        scenarios = parse_scenario_config(config)
        description = describe_scenarios(scenarios)

        assert "BASE" in description
        assert "RATES_UP_50BPS" in description
        assert "0.005" in description

    def test_llm_config_with_sensitivity_analysis(self):
        """Combine LLM config with sensitivity_analysis output."""
        from gaspatchio_core.scenarios import (
            parse_scenario_config,
            sensitivity_analysis,
        )

        # LLM can generate a sweep using sensitivity_analysis
        sweep_shocks = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=[0.9, 1.0, 1.1],
        )

        # Or parse a manual config
        manual_config = [
            {"id": "LAPSE_STRESS", "shocks": [{"table": "lapse", "set": 0}]}
        ]
        manual_scenarios = parse_scenario_config(manual_config)

        # Both produce dict[str, list[Shock]]
        assert isinstance(sweep_shocks, dict)
        assert isinstance(manual_scenarios, dict)
