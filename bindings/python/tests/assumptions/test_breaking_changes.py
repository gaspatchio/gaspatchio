"""
Tests for the top-level only assumptions API.

This module verifies that:
1. Top-level imports work correctly
2. Package-level imports for main functions correctly fail (restricted)
3. Package-level metadata imports still work
4. The API enforces the intended usage pattern
"""

import pytest


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the global assumption registry before each test."""
    from gaspatchio_core._internal import PyAssumptionTableRegistry

    registry = PyAssumptionTableRegistry()
    registry.reset()
    yield
    # Optionally reset after test too for extra safety
    registry.reset()


class TestTopLevelOnlyImports:
    """Test that the top-level only import restriction works as expected."""

    def test_assumption_lookup_import_from_package_fails(self):
        """Test that importing assumption_lookup from assumptions package fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import assumption_lookup  # noqa: F401

    def test_load_assumptions_import_from_package_fails(self):
        """Test that importing load_assumptions from assumptions package fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import load_assumptions  # noqa: F401

    def test_combined_import_from_package_fails(self):
        """Test that importing both functions from assumptions package fails."""
        with pytest.raises(ImportError):
            from gaspatchio_core.assumptions import (  # noqa: F401
                assumption_lookup,
                load_assumptions,
            )

    def test_top_level_imports_work(self):
        """Test that top-level imports work correctly."""
        import gaspatchio_core as gs

        # These should all work
        assert hasattr(gs, "assumption_lookup")
        assert hasattr(gs, "load_assumptions")
        assert hasattr(gs, "ActuarialFrame")

        # Verify they are callable
        assert callable(gs.assumption_lookup)
        assert callable(gs.load_assumptions)

    def test_metadata_functions_available_in_package(self):
        """Test that metadata functions are available in the assumptions package."""
        from gaspatchio_core.assumptions import (
            get_table_metadata,
            list_tables_with_metadata,
        )

        # These should work
        assert callable(get_table_metadata)
        assert callable(list_tables_with_metadata)

    def test_top_level_api_surface(self):
        """Test that only the planned symbols are available at top-level."""
        import gaspatchio_core as gs

        # These symbols should be available
        required_symbols = [
            "load_assumptions",
            "assumption_lookup",
            "ActuarialFrame",
        ]

        for symbol in required_symbols:
            assert hasattr(gs, symbol), f"Missing required symbol: {symbol}"
            assert symbol in gs.__all__, f"Symbol {symbol} not in __all__"

    def test_package_level_api_surface_metadata_only(self):
        """Test that the assumptions package exports only metadata functions."""
        from gaspatchio_core import assumptions

        # Should have metadata functions
        metadata_functions = [
            "get_table_metadata",
            "list_tables_with_metadata",
        ]

        for func in metadata_functions:
            assert hasattr(assumptions, func), f"Missing metadata function: {func}"
            assert func in assumptions.__all__, f"Function {func} not in __all__"

        # Should NOT have main functions
        main_functions = ["assumption_lookup", "load_assumptions"]
        for func in main_functions:
            # hasattr() triggers __getattr__ which should raise ImportError
            try:
                hasattr(assumptions, func)
                assert False, (
                    f"Main function {func} should not be accessible in package"
                )
            except ImportError:
                pass  # This is expected
            assert func not in assumptions.__all__, (
                f"Function {func} should not be in __all__"
            )


class TestTopLevelAPIWorkflow:
    """Test that the API workflow functions correctly with top-level imports only."""

    def test_complete_workflow_with_top_level_api(self):
        """Test complete assumption loading and lookup workflow using top-level API."""
        import gaspatchio_core as gs
        import polars as pl

        # Create test data
        df = pl.DataFrame({"Age": [30, 31, 32], "qx": [0.001, 0.0011, 0.0012]})

        # Load using top-level API
        result = gs.load_assumptions("top_level_test", df, value="qx")

        # Verify structure
        assert result.columns == ["Age", "qx"]
        assert len(result) == 3

        # Test lookup using top-level API
        test_df = pl.DataFrame({"Age": [31.0]})
        lookup_result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name="top_level_test").alias("qx")
        )

        assert lookup_result["qx"].item() == 0.0011

    def test_complete_workflow_with_direct_imports(self):
        """Test complete assumption loading and lookup workflow using direct imports from top level."""
        import polars as pl
        from gaspatchio_core import assumption_lookup, load_assumptions

        # Create test data
        df = pl.DataFrame({"Age": [30, 31, 32], "qx": [0.001, 0.0011, 0.0012]})

        # Load using direct import
        result = load_assumptions("direct_import_test", df, value="qx")

        # Verify structure
        assert result.columns == ["Age", "qx"]
        assert len(result) == 3

        # Test lookup using direct import
        test_df = pl.DataFrame({"Age": [31.0]})  # age now f64
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", table_name="direct_import_test").alias("qx")
        )

        assert lookup_result["qx"].item() == 0.0011

    def test_wide_table_workflow_top_level_only(self):
        """Test wide table workflow using top-level imports only."""
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

        # Load using top-level API
        result = gs.load_assumptions("wide_top_level_test", df, value="rate")

        # Verify structure
        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 6  # 2 ages × 3 durations

        # Test lookup using top-level API
        test_df = pl.DataFrame({"Age": [30.0], "variable": [2.0]})  # both now f64
        lookup_result = test_df.with_columns(
            gs.assumption_lookup(
                "Age", "variable", table_name="wide_top_level_test"
            ).alias("rate")
        )

        assert lookup_result["rate"].item() == 0.0008


class TestRestrictedAPIBehavior:
    """Test that the restricted API provides clear guidance."""

    def test_import_error_messages_are_helpful(self):
        """Test that ImportError provides helpful guidance about the top-level API."""
        try:
            from gaspatchio_core.assumptions import assumption_lookup  # noqa: F401

            pytest.fail("Expected ImportError was not raised")
        except ImportError as e:
            # The error message should mention the function name
            assert "assumption_lookup" in str(e)

        try:
            from gaspatchio_core.assumptions import load_assumptions  # noqa: F401

            pytest.fail("Expected ImportError was not raised")
        except ImportError as e:
            # The error message should mention the function name
            assert "load_assumptions" in str(e)

    def test_package_module_docstring_describes_restriction(self):
        """Test that module docstrings describe the top-level only API."""
        from gaspatchio_core import assumptions

        # The module should exist and have documentation
        assert hasattr(assumptions, "__doc__")
        assert assumptions.__doc__ is not None

        # Should only have metadata functions, not main functions
        assert hasattr(assumptions, "get_table_metadata")
        assert hasattr(assumptions, "list_tables_with_metadata")

        # Main functions should trigger ImportError when accessed
        try:
            hasattr(assumptions, "assumption_lookup")
            assert False, "assumption_lookup should not be accessible"
        except ImportError:
            pass  # Expected

        try:
            hasattr(assumptions, "load_assumptions")
            assert False, "load_assumptions should not be accessible"
        except ImportError:
            pass  # Expected

    def test_top_level_direct_imports_work(self):
        """Test that users can import functions directly from top level."""
        # This is the recommended import pattern
        from gaspatchio_core import assumption_lookup, load_assumptions

        assert callable(assumption_lookup)
        assert callable(load_assumptions)
