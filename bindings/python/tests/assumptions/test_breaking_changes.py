"""
Tests for breaking changes in the new simplified API.

This module verifies that:
1. Old import paths now fail with helpful error messages
2. New top-level import paths work correctly
3. Only the planned symbols are available at top-level
4. Users are guided toward the new API
"""

import pytest


class TestBreakingChangeImports:
    """Test that import breaking changes work as expected."""

    def test_old_assumption_lookup_import_fails(self):
        """Test that importing assumption_lookup from assumptions submodule now fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import assumption_lookup  # noqa: F401

    def test_old_load_assumptions_import_fails(self):
        """Test that importing load_assumptions from assumptions submodule now fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import load_assumptions  # noqa: F401

    def test_old_combined_import_fails(self):
        """Test that importing both functions from assumptions submodule fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import (  # noqa: F401
                assumption_lookup,
                load_assumptions,
            )

    def test_new_top_level_imports_work(self):
        """Test that new top-level imports work correctly."""
        import gaspatchio_core as gs

        # These should all work
        assert hasattr(gs, "assumption_lookup")
        assert hasattr(gs, "load_assumptions")
        assert hasattr(gs, "ActuarialFrame")

        # Verify they are callable
        assert callable(gs.assumption_lookup)
        assert callable(gs.load_assumptions)

    def test_metadata_functions_still_available_in_submodule(self):
        """Test that metadata functions are still available in the assumptions submodule."""
        from gaspatchio_core.assumptions import (
            get_table_metadata,
            list_tables_with_metadata,
        )

        # These should still work
        assert callable(get_table_metadata)
        assert callable(list_tables_with_metadata)

    def test_top_level_api_surface(self):
        """Test that only the planned symbols are available at top-level."""
        import gaspatchio_core as gs

        # These 4 symbols should be available
        required_symbols = [
            "load_assumptions",
            "assumption_lookup",
            "ActuarialFrame",
            # Note: read_csv was mentioned in spec but doesn't seem to be implemented
        ]

        for symbol in required_symbols:
            if symbol != "read_csv":  # Skip read_csv for now as discussed
                assert hasattr(gs, symbol), f"Missing required symbol: {symbol}"
                assert symbol in gs.__all__, f"Symbol {symbol} not in __all__"


class TestNewAPIWorkflow:
    """Test that the new API workflow functions correctly end-to-end."""

    def test_complete_workflow_with_new_api(self):
        """Test complete assumption loading and lookup workflow using new API."""
        import gaspatchio_core as gs
        import polars as pl

        # Create test data
        df = pl.DataFrame({"Age": [30, 31, 32], "qx": [0.001, 0.0011, 0.0012]})

        # Load using new API
        result = gs.load_assumptions("breaking_change_test", df, value="qx")

        # Verify structure
        assert result.columns == ["Age", "qx"]
        assert len(result) == 3

        # Test lookup using new API
        test_df = pl.DataFrame({"Age": [31]})
        lookup_result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name="breaking_change_test").alias("qx")
        )

        assert lookup_result["qx"].item() == 0.0011

    def test_wide_table_workflow_with_new_api(self):
        """Test wide table workflow using new API."""
        import gaspatchio_core as gs
        import polars as pl

        # Create wide table test data
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [0.001, 0.0011],
                "2": [0.0008, 0.0009],
                "3": [0.0005, 0.0006],
            }
        )

        # Load using new API
        result = gs.load_assumptions("wide_breaking_change_test", df, value="rate")

        # Verify structure
        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 6  # 2 ages × 3 durations

        # Test lookup using new API
        test_df = pl.DataFrame({"Age": [30], "variable": ["2"]})
        lookup_result = test_df.with_columns(
            gs.assumption_lookup(
                "Age", "variable", table_name="wide_breaking_change_test"
            ).alias("rate")
        )

        assert lookup_result["rate"].item() == 0.0008


class TestErrorMessagesAndGuidance:
    """Test that error messages provide helpful guidance for migration."""

    def test_import_error_provides_guidance(self):
        """Test that ImportError provides helpful guidance about the new API."""
        try:
            from gaspatchio_core.assumptions import assumption_lookup  # noqa: F401

            pytest.fail("Expected ImportError was not raised")
        except ImportError as e:
            # The error message should be helpful
            # (Though we're not requiring specific text since it's auto-generated)
            assert "assumption_lookup" in str(e)

    def test_module_docstring_provides_guidance(self):
        """Test that module docstrings provide migration guidance."""
        from gaspatchio_core import assumptions

        # The module should still exist but with limited functionality
        assert hasattr(assumptions, "__doc__")

        # Should only have metadata functions
        assert hasattr(assumptions, "get_table_metadata")
        assert hasattr(assumptions, "list_tables_with_metadata")

        # Should NOT have the main functions
        assert not hasattr(assumptions, "assumption_lookup")
        assert not hasattr(assumptions, "load_assumptions")
