"""
Tests for duplicate table name handling.

This module tests the detection and handling of duplicate table names,
overwriting scenarios, and concurrent loading scenarios.
"""

import time

# Use new top-level imports instead of submodule imports
import gaspatchio_core as gs
import polars as pl
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


class TestDuplicateTableNames:
    """Test duplicate table name handling."""

    def test_duplicate_table_name_error(self):
        """Test that loading the same table name twice raises an error."""
        df1 = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        df2 = pl.DataFrame({"Age": [32, 33], "qx": [0.002, 0.0021]})

        # Use timestamp to ensure unique table name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"mortality_duplicate_test_{unique_suffix}"

        # First registration should succeed
        gs.load_assumptions(table_name, df1)

        # Second registration with same name should raise error
        with pytest.raises(
            RuntimeError, match=f"assumption table '{table_name}' already exists"
        ):
            gs.load_assumptions(table_name, df2)

    def test_duplicate_table_name_wide_vs_curve(self):
        """Test duplicate names between different table types."""
        curve_df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        wide_df = pl.DataFrame(
            {"Age": [30, 31], "1": [0.001, 0.0011], "2": [0.0008, 0.0009]}
        )

        # Use timestamp to ensure unique table name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"mixed_type_duplicate_{unique_suffix}"

        # Load curve first
        gs.load_assumptions(table_name, curve_df, value="qx")

        # Try to load wide table with same name - should fail
        with pytest.raises(
            RuntimeError, match=f"assumption table '{table_name}' already exists"
        ):
            gs.load_assumptions(table_name, wide_df)

    def test_duplicate_with_overflow_table(self):
        """Test duplicate names with overflow tables."""
        overflow_df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [0.001, 0.0011],
                "2": [0.0008, 0.0009],
                "Ult.": [0.0005, 0.0006],
            }
        )

        simple_df = pl.DataFrame({"Age": [30, 31], "rate": [0.001, 0.0011]})

        # Use timestamp to ensure unique table name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"overflow_duplicate_test_{unique_suffix}"

        # Load overflow table first
        gs.load_assumptions(table_name, overflow_df, overflow="Ult.")

        # Try to load simple table with same name - should fail
        with pytest.raises(
            RuntimeError, match=f"assumption table '{table_name}' already exists"
        ):
            gs.load_assumptions(table_name, simple_df)

    def test_case_sensitive_table_names(self):
        """Test that table names are case sensitive."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Use timestamp to ensure unique base name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        base_name = f"mortality_case_test_{unique_suffix}"

        # These should all work as they're different names
        names = [
            base_name,
            base_name.upper(),
            base_name.capitalize(),
            f"{base_name}_MIXED",
        ]

        for name in names:
            gs.load_assumptions(name, df, value="qx")

        # Verify all are registered and accessible
        test_df = pl.DataFrame({"Age": [30]})

        for table_name in names:
            result = test_df.with_columns(
                gs.assumption_lookup("Age", table_name=table_name).alias("qx")
            )
            assert result["qx"].item() == 0.001

    def test_empty_table_name_error(self):
        """Test that empty or whitespace-only table names are rejected."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            gs.load_assumptions("", df)

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            gs.load_assumptions("   ", df)

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            gs.load_assumptions("\t\n", df)

    def test_none_table_name_error(self):
        """Test that None table name is rejected."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            gs.load_assumptions(None, df)

    def test_numeric_string_table_names_allowed(self):
        """Test that numeric string table names are allowed and case sensitive."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Use timestamp for uniqueness
        unique_suffix = str(int(time.time() * 1000000))[-8:]

        # These should all work (they're all different strings)
        valid_names = [
            f"123_{unique_suffix}",
            f"2024_{unique_suffix}",
            f"1.5_{unique_suffix}",
        ]

        for name in valid_names:
            gs.load_assumptions(name, df, value="qx")

            # Verify accessibility
            test_df = pl.DataFrame({"Age": [30]})
            result = test_df.with_columns(
                gs.assumption_lookup("Age", table_name=name).alias("qx")
            )
            assert result["qx"].item() == 0.001


class TestTableOverwriting:
    """Test table overwriting scenarios."""

    def test_explicit_overwrite_not_supported(self):
        """Test that explicit overwriting is not currently supported."""
        # Note: This test documents current behavior.
        # If overwrite functionality is added later, this test should be updated.

        df1 = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        df2 = pl.DataFrame({"Age": [30, 31], "qx": [0.002, 0.0021]})

        # Use timestamp to ensure unique table name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"overwrite_test_{unique_suffix}"

        # First load
        gs.load_assumptions(table_name, df1)

        # Second load should fail (no overwrite parameter supported)
        with pytest.raises(
            RuntimeError, match=f"assumption table '{table_name}' already exists"
        ):
            gs.load_assumptions(table_name, df2)

    def test_registry_state_after_failed_duplicate(self):
        """Test that registry state is consistent after failed duplicate registration."""
        df1 = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        df2 = pl.DataFrame({"Age": [30, 31], "qx": [0.002, 0.0021]})

        # Use timestamp to ensure unique table name
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"registry_state_test_{unique_suffix}"

        # First registration
        result1 = gs.load_assumptions(table_name, df1, value="qx")

        # Failed second registration
        with pytest.raises(RuntimeError):
            gs.load_assumptions(table_name, df2, value="qx")

        # Original table should still be accessible and unchanged
        test_df = pl.DataFrame({"Age": [30]})
        result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name=table_name).alias("qx")
        )
        assert result["qx"].item() == 0.001  # Should still be original value

    def test_unique_names_across_sessions(self):
        """Test that each test gets unique table names to avoid conflicts."""
        # This is more of a test hygiene check to ensure our test design is sound

        # Use timestamp or random suffix for uniqueness in real scenarios
        unique_suffix = str(int(time.time() * 1000000))[
            -8:
        ]  # Last 8 digits of microsecond timestamp

        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        table_name = f"unique_test_{unique_suffix}"
        result = gs.load_assumptions(table_name, df, value="qx")

        assert len(result) == 2
        assert result.columns == ["Age", "qx"]


class TestTableNameValidation:
    """Test table name validation beyond basic empty checks."""

    def test_special_character_table_names(self):
        """Test table names with special characters."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Use timestamp for uniqueness
        unique_suffix = str(int(time.time() * 1000000))[-8:]

        # These should work (valid string names)
        valid_names = [
            f"table_with_underscores_{unique_suffix}",
            f"table-with-hyphens-{unique_suffix}",
            f"table.with.dots.{unique_suffix}",
            f"table with spaces {unique_suffix}",
            f"table@with#special$chars%{unique_suffix}",
            f"table/with/slashes/{unique_suffix}",
            f"αβγ_unicode_test_{unique_suffix}",  # Unicode characters
            f"table_with_numbers_123_{unique_suffix}",
        ]

        for name in valid_names:
            try:
                result = gs.load_assumptions(name, df, value="qx")
                assert len(result) == 2

                # Verify accessibility
                test_df = pl.DataFrame({"Age": [30]})
                lookup_result = test_df.with_columns(
                    gs.assumption_lookup("Age", table_name=name).alias("qx")
                )
                assert lookup_result["qx"].item() == 0.001
            except Exception as e:
                pytest.fail(f"Table name '{name}' should be valid but raised: {e}")

    def test_very_long_table_names(self):
        """Test very long table names."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Use timestamp for uniqueness
        unique_suffix = str(int(time.time() * 1000000))[-8:]

        # Very long name (500 characters + unique suffix)
        long_name = f"{'a' * 500}_{unique_suffix}"

        # Should work (no artificial length limit imposed)
        result = gs.load_assumptions(long_name, df, value="qx")
        assert len(result) == 2

        # Verify accessibility
        test_df = pl.DataFrame({"Age": [30]})
        lookup_result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name=long_name).alias("qx")
        )
        assert lookup_result["qx"].item() == 0.001


class TestConcurrentLoading:
    """Test concurrent/simultaneous loading scenarios."""

    def test_sequential_loading_different_names(self):
        """Test loading multiple tables sequentially with different names."""
        # This is the normal, expected usage pattern

        # Use timestamp for uniqueness
        unique_suffix = str(int(time.time() * 1000000))[-8:]

        tables_data = [
            (
                f"mortality_2020_{unique_suffix}",
                pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]}),
            ),
            (
                f"mortality_2021_{unique_suffix}",
                pl.DataFrame({"Age": [30, 31], "qx": [0.0009, 0.001]}),
            ),
            (
                f"interest_rates_{unique_suffix}",
                pl.DataFrame({"Year": [1, 2], "rate": [0.03, 0.035]}),
            ),
            (
                f"lapse_rates_{unique_suffix}",
                pl.DataFrame(
                    {
                        "Duration": [1, 2, 3],
                        "Male": [0.05, 0.04, 0.03],
                        "Female": [0.04, 0.035, 0.025],
                    }
                ),
            ),
        ]

        # Load all tables
        results = []
        for name, df in tables_data:
            if "lapse_rates" in name:
                result = gs.load_assumptions(
                    name, df, id="Duration", value_vars=["Male", "Female"]
                )
            else:
                result = gs.load_assumptions(name, df)
            results.append((name, result))

        # Verify all are accessible
        for name, expected_result in results:
            if "lapse_rates" in name:
                # Test wide table lookup
                test_df = pl.DataFrame({"Duration": [1], "variable": ["Male"]})
                result = test_df.with_columns(
                    gs.assumption_lookup("Duration", "variable", table_name=name).alias(
                        "rate"
                    )
                )
                assert result["rate"].item() == 0.05
            elif "interest_rates" in name:
                # Test different id column
                test_df = pl.DataFrame({"Year": [1]})
                result = test_df.with_columns(
                    gs.assumption_lookup("Year", table_name=name).alias("rate")
                )
                assert result["rate"].item() == 0.03
            else:
                # Test mortality tables
                test_df = pl.DataFrame({"Age": [30]})
                result = test_df.with_columns(
                    gs.assumption_lookup("Age", table_name=name).alias("qx")
                )
                assert result["qx"].item() in [0.001, 0.0009]  # Either table value

    def test_registry_isolation_between_tests(self):
        """Test that tests don't interfere with each other."""
        # This is important for test reliability

        # Each test should be able to use the same logical names
        # without conflicts, achieved through unique naming strategies

        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Use a test-specific prefix to avoid conflicts
        unique_suffix = str(int(time.time() * 1000000))[-8:]
        table_name = f"isolation_test_mortality_{unique_suffix}"

        result = gs.load_assumptions(table_name, df, value="qx")
        assert len(result) == 2

        # Verify accessibility
        test_df = pl.DataFrame({"Age": [30]})
        lookup_result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name=table_name).alias("qx")
        )
        assert lookup_result["qx"].item() == 0.001

    def test_multiple_table_types_coexistence(self):
        """Test that different table types can coexist in the registry."""
        # Use timestamp for uniqueness
        unique_suffix = str(int(time.time() * 1000000))[-8:]

        # Create different types of tables
        curve_df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        wide_df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [0.002, 0.0021],
                "2": [0.0015, 0.0016],
            }
        )
        overflow_df = pl.DataFrame(
            {
                "Duration": [1, 2],
                "1": [0.05, 0.04],
                "2": [0.04, 0.035],
                "Ult.": [0.03, 0.025],
            }
        )

        # Load all different types
        curve_name = f"curve_table_{unique_suffix}"
        wide_name = f"wide_table_{unique_suffix}"
        overflow_name = f"overflow_table_{unique_suffix}"

        gs.load_assumptions(curve_name, curve_df, value="qx")
        gs.load_assumptions(wide_name, wide_df)
        gs.load_assumptions(
            overflow_name, overflow_df, id="Duration", overflow="Ult.", max_overflow=5
        )

        # Verify all are accessible with their respective schemas
        # Curve table test
        test_df = pl.DataFrame({"Age": [30]})
        curve_result = test_df.with_columns(
            gs.assumption_lookup("Age", table_name=curve_name).alias("qx")
        )
        assert curve_result["qx"].item() == 0.001

        # Wide table test
        test_df = pl.DataFrame({"Age": [30], "variable": ["1"]})
        wide_result = test_df.with_columns(
            gs.assumption_lookup("Age", "variable", table_name=wide_name).alias("rate")
        )
        assert wide_result["rate"].item() == 0.002

        # Overflow table test (including expanded durations)
        test_df = pl.DataFrame(
            {"Duration": [1], "variable": ["4"]}
        )  # Expanded duration
        overflow_result = test_df.with_columns(
            gs.assumption_lookup(
                "Duration", "variable", table_name=overflow_name
            ).alias("rate")
        )
        assert overflow_result["rate"].item() == 0.03  # Should match Ult. value
