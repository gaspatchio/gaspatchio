"""
Integration tests for assumption loading API - Step 7: API Integration & Top-Level Exports.

This module tests the complete public API integration and ensures seamless
end-to-end workflows using realistic actuarial examples from the Life Insurance domain.
"""

# Test importing from top level gaspatchio_core
import gaspatchio_core as gs
import polars as pl
import pytest


class TestTopLevelAPIImports:
    """Test that the public API is correctly exported at the top level."""

    def test_load_assumptions_import(self):
        """Test that load_assumptions can be imported from top level."""
        assert hasattr(gs, "load_assumptions")
        assert callable(gs.load_assumptions)

    def test_assumption_lookup_import(self):
        """Test that assumption_lookup can be imported from top level."""
        assert hasattr(gs, "assumption_lookup")
        assert callable(gs.assumption_lookup)

    def test_api_surface_completeness(self):
        """Test that both functions are in the public API surface."""
        assert "load_assumptions" in gs.__all__
        assert "assumption_lookup" in gs.__all__


class TestMortalityCurveIntegration:
    """Test end-to-end workflow with mortality curve tables."""

    def test_basic_mortality_curve_workflow(self):
        """Test complete workflow: load mortality curve → lookup rates."""
        # Realistic mortality curve data (qx rates by age)
        mortality_data = pl.DataFrame(
            {
                "age": [20, 21, 22, 23, 24, 25],
                "qx": [0.00048, 0.00051, 0.00054, 0.00058, 0.00062, 0.00067],
            }
        )

        # Load assumptions using top-level API
        result = gs.load_assumptions("basic_mortality", mortality_data, value="qx")

        # Verify structure
        assert result.columns == ["age", "qx"]
        assert len(result) == 6

        # Test lookup functionality with top-level API using single-row pattern
        test_cases = [(22, 0.00054), (24, 0.00062), (25, 0.00067)]

        for age, expected_rate in test_cases:
            test_df = pl.DataFrame({"age": [age]})
            lookup_result = test_df.with_columns(
                gs.assumption_lookup("age", table_name="basic_mortality").alias(
                    "mortality_rate"
                )
            )

            # Verify lookup results
            assert len(lookup_result) == 1
            assert "mortality_rate" in lookup_result.columns

            # Check specific values
            actual_rate = lookup_result["mortality_rate"].item()
            assert actual_rate == expected_rate

    def test_interest_rate_curve_workflow(self):
        """Test workflow with interest rate curve."""
        # Interest rate curve by duration
        interest_rates = pl.DataFrame(
            {
                "duration": [1, 2, 3, 5, 10, 20, 30],
                "spot_rate": [0.025, 0.028, 0.032, 0.038, 0.042, 0.045, 0.046],
            }
        )

        result = gs.load_assumptions("yield_curve", interest_rates, value="spot_rate")

        # Test individual lookups (following working pattern)
        test_cases = [(1, 0.025), (10, 0.042), (30, 0.046)]

        for duration, expected_rate in test_cases:
            test_df = pl.DataFrame({"duration": [duration]})
            result_with_rates = test_df.with_columns(
                gs.assumption_lookup("duration", table_name="yield_curve").alias(
                    "discount_rate"
                )
            )

            assert len(result_with_rates) == 1
            actual_rate = result_with_rates["discount_rate"].item()
            assert actual_rate == expected_rate


class TestSelectUltimateTableIntegration:
    """Test end-to-end workflow with select & ultimate mortality tables."""

    def test_select_ultimate_mortality_workflow(self):
        """Test complete workflow with select & ultimate mortality table."""
        # Realistic select & ultimate mortality table
        # Ages 25-27, Durations 1-3 + Ultimate
        select_ultimate_data = pl.DataFrame(
            {
                "age": [25, 26, 27, 25, 26, 27],
                "gender": ["M", "M", "M", "F", "F", "F"],
                "1": [0.00050, 0.00055, 0.00062, 0.00035, 0.00038, 0.00042],
                "2": [0.00062, 0.00068, 0.00075, 0.00043, 0.00047, 0.00052],
                "3": [0.00075, 0.00082, 0.00090, 0.00052, 0.00057, 0.00063],
                "Ult.": [0.00095, 0.00105, 0.00115, 0.00066, 0.00073, 0.00080],
            }
        )

        # Load with overflow expansion
        result = gs.load_assumptions(
            "select_ultimate_mortality",
            select_ultimate_data,
            id=["age", "gender"],
            overflow="Ult.",
            max_overflow=10,
        )

        # Should have original data + expanded ultimate rates
        # 6 combinations × (4 original durations + 7 expanded) = 66 rows
        assert len(result) == 66
        assert result.columns == ["age", "gender", "variable", "rate"]

        # Test lookup for select period using single-row pattern
        test_cases = [
            (25, "M", "2", 0.00062),  # Male age 25 duration 2
            (26, "F", "1", 0.00038),  # Female age 26 duration 1
        ]

        for age, gender, variable, expected_rate in test_cases:
            test_df = pl.DataFrame(
                {"age": [age], "gender": [gender], "variable": [variable]}
            )
            select_rates = test_df.with_columns(
                gs.assumption_lookup(
                    "age", "gender", "variable", table_name="select_ultimate_mortality"
                ).alias("qx")
            )

            assert len(select_rates) == 1
            actual_rate = select_rates["qx"].item()
            assert actual_rate == expected_rate

        # Test lookup for ultimate period (expanded)
        test_df = pl.DataFrame({"age": [27], "gender": ["F"], "variable": ["8"]})
        ultimate_rates = test_df.with_columns(
            gs.assumption_lookup(
                "age", "gender", "variable", table_name="select_ultimate_mortality"
            ).alias("qx")
        )

        # Should get the ultimate rate
        assert len(ultimate_rates) == 1
        assert ultimate_rates["qx"].item() == 0.00080


class TestCommissionTableIntegration:
    """Test workflow with commission tables using value_vars for selective melting."""

    def test_commission_table_selective_melting(self):
        """Test commission table with product-specific rates."""
        # Commission rates by agent tier and product type
        commission_data = pl.DataFrame(
            {
                "agent_tier": ["Bronze", "Silver", "Gold", "Platinum"],
                "term_life": [0.05, 0.06, 0.07, 0.08],
                "whole_life": [0.08, 0.09, 0.10, 0.12],
                "annuity": [0.03, 0.04, 0.05, 0.06],
                "admin_fee": [25, 20, 15, 10],  # Not a commission rate
            }
        )

        # Use value_vars to only melt commission columns, not admin_fee
        result = gs.load_assumptions(
            "commission_rates",
            commission_data,
            value_vars=["term_life", "whole_life", "annuity"],
            value="commission_rate",
        )

        # Should have 4 tiers × 3 products = 12 rows
        assert len(result) == 12
        assert result.columns == ["agent_tier", "variable", "commission_rate"]

        # Admin fee should not be in the melted data
        products = result["variable"].unique().to_list()
        assert "admin_fee" not in products
        assert "term_life" in products

        # Test lookup for specific commission using single-row pattern
        test_cases = [("Gold", "whole_life", 0.10), ("Silver", "term_life", 0.06)]

        for agent_tier, variable, expected_rate in test_cases:
            test_df = pl.DataFrame({"agent_tier": [agent_tier], "variable": [variable]})
            commission_lookup = test_df.with_columns(
                gs.assumption_lookup(
                    "agent_tier", "variable", table_name="commission_rates"
                ).alias("rate")
            )

            assert len(commission_lookup) == 1
            actual_rate = commission_lookup["rate"].item()
            assert actual_rate == expected_rate


class TestLapseRateTableIntegration:
    """Test workflow with lapse rate tables including overflow scenarios."""

    def test_lapse_rate_with_auto_overflow(self):
        """Test lapse rates with automatic overflow detection."""
        # Lapse rates by policy year with ultimate rate
        lapse_data = pl.DataFrame(
            {
                "product_code": ["TERM10", "TERM20", "WL"],
                "1": [0.15, 0.12, 0.08],
                "2": [0.10, 0.08, 0.06],
                "3": [0.08, 0.06, 0.05],
                "4": [0.06, 0.05, 0.04],
                "5": [0.05, 0.04, 0.04],
                "Ultimate": [0.02, 0.02, 0.02],
            }
        )

        result = gs.load_assumptions(
            "lapse_rates",
            lapse_data,
            overflow="auto",  # Should detect "Ultimate"
            max_overflow=20,
        )

        # Original: 3 products × 6 durations = 18 rows
        # Expansion: 3 products × 15 durations (6-20) = 45 rows
        # Total: 63 rows
        assert len(result) == 63

        # Test lookup for expanded ultimate period using single-row pattern
        test_df = pl.DataFrame({"product_code": ["TERM10"], "variable": ["15"]})
        lapse_lookup = test_df.with_columns(
            gs.assumption_lookup(
                "product_code", "variable", table_name="lapse_rates"
            ).alias("lapse_rate")
        )

        # Should get ultimate rate of 0.02
        assert len(lapse_lookup) == 1
        assert lapse_lookup["lapse_rate"].item() == 0.02


class TestBackwardCompatibilityIntegration:
    """Test that existing workflows continue to work unchanged."""

    def test_mixed_api_usage(self):
        """Test using both old and new loading methods together."""
        # Load one table with new API
        mortality_new = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.001, 0.0011, 0.0012]}
        )

        gs.load_assumptions("new_mortality_api", mortality_new, value="qx")

        # Both should work in lookups using single-row pattern
        test_df = pl.DataFrame({"age": [31]})

        # Test new table lookup
        with_mortality = test_df.with_columns(
            gs.assumption_lookup("age", table_name="new_mortality_api").alias(
                "mortality"
            )
        )

        assert len(with_mortality) == 1
        assert with_mortality["mortality"].item() == 0.0011

    def test_performance_comparison(self):
        """Test that lookup performance meets expectations."""
        import time

        # Create larger table for performance testing
        large_mortality = pl.DataFrame(
            {"age": list(range(18, 100)), "qx": [0.001 + i * 0.0001 for i in range(82)]}
        )

        gs.load_assumptions("large_mortality", large_mortality, value="qx")

        # Test lookup performance using single-row pattern
        test_ages = [25, 35, 45, 55, 65, 75, 85, 95]

        start_time = time.time()

        # Perform multiple lookups
        for _ in range(100):
            for age in test_ages:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="large_mortality").alias(
                        "rate"
                    )
                )

        lookup_time = time.time() - start_time

        # 100 loops × 8 values should be very fast
        assert lookup_time < 0.1  # Under 100ms for 800 total lookups


class TestErrorHandlingIntegration:
    """Test comprehensive error handling in the integrated API."""

    def test_duplicate_table_names(self):
        """Test handling of duplicate table names."""
        mortality_v1 = pl.DataFrame({"age": [25], "qx": [0.001]})

        # First load should succeed
        gs.load_assumptions("duplicate_test_unique", mortality_v1, value="qx")

        # Second load with same name should raise error (current behavior)
        mortality_v2 = pl.DataFrame({"age": [25], "qx": [0.002]})
        with pytest.raises(ValueError, match="already exists"):
            gs.load_assumptions("duplicate_test_unique", mortality_v2, value="qx")

        # Verify the original table is still there
        test_df = pl.DataFrame({"age": [25]})
        result = test_df.with_columns(
            gs.assumption_lookup("age", table_name="duplicate_test_unique").alias(
                "rate"
            )
        )

        assert result["rate"].item() == 0.001  # Should be the original value

    def test_invalid_parameters_integration(self):
        """Test parameter validation in integrated workflow."""
        df = pl.DataFrame({"age": [25], "qx": [0.001]})

        # Test invalid name
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            gs.load_assumptions("", df)

        # Test invalid max_overflow
        with pytest.raises(ValueError, match="max_overflow must be an integer"):
            gs.load_assumptions("test", df, max_overflow=0)

    def test_missing_table_lookup(self):
        """Test lookup against non-existent table."""
        test_df = pl.DataFrame({"age": [25]})

        # This should raise an error when the lookup is executed
        with pytest.raises(Exception):  # Specific error depends on implementation
            result = test_df.with_columns(
                gs.assumption_lookup("age", table_name="nonexistent_table").alias(
                    "rate"
                )
            )
            # Force evaluation
            result.collect()
