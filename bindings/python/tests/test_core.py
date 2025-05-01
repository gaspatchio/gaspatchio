import math
import unittest
from unittest import mock

import numpy as np
import polars as pl
import pytest

# Try to import numba, but make it optional
try:
    import numba

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    # Define empty functions as placeholders
    class numba:
        @staticmethod
        def vectorize(func):
            return func

        @staticmethod
        def njit(func):
            return func


from gaspatchio_core.dsl.core import (
    ActuarialFrame,
    ColumnProxy,
    ExpressionProxy,
    execution_mode,
    get_default_mode,
    run_model,
    set_default_mode,
)


# Define test plugin functions that work with the debuggable DSL
def fill_series_debuggable(expr, start, step):
    """Create a series from start with step increments."""
    # For the debuggable DSL, we need to return a Polars expression
    return expr + pl.lit(0)  # Just return the expression for testing


def floor_debuggable(expr, base=None):
    """Floor function for the debuggable DSL."""
    # For the debuggable DSL, we need to return a Polars expression
    if base is not None:
        return (expr / base).floor() * base
    return expr.floor()


# Register plugin functions
fill_series = fill_series_debuggable
floor = floor_debuggable


# Define risk factor outside of complex_model to avoid Numba issues
def _risk_factor(age):
    return math.log(max(age, 1)) * 0.01


class TestDebugableBasics(unittest.TestCase):
    def setUp(self):
        # Create a simple test dataframe
        self.data = pl.DataFrame(
            {
                "age": [35, 40, 45, 50, 55],
                "sex": ["M", "F", "M", "F", "M"],
                "premium": [100.0, 150.0, 200.0, 250.0, 300.0],
            }
        )

    def test_initialization(self):
        # Test initialization with explicit mode
        df = ActuarialFrame(self.data, mode="debug")
        self.assertEqual(df._mode, "debug")

        df = ActuarialFrame(self.data, mode="optimize")
        self.assertEqual(df._mode, "optimize")

        # Test initialization with default mode
        original_mode = get_default_mode()
        try:
            set_default_mode("debug")
            df = ActuarialFrame(self.data)
            self.assertEqual(df._mode, "debug")

            set_default_mode("optimize")
            df = ActuarialFrame(self.data)
            self.assertEqual(df._mode, "optimize")
        finally:
            set_default_mode(original_mode)

    def test_column_access(self):
        df = ActuarialFrame(self.data)

        # Test column access returns a ColumnProxy
        column = df["age"]
        self.assertIsInstance(column, ColumnProxy)
        self.assertEqual(column.name, "age")

    def test_column_assignment(self):
        df = ActuarialFrame(self.data, mode="debug")

        # Test basic assignment
        df["new_column"] = 42
        result = df.collect()
        self.assertTrue("new_column" in result.columns)
        self.assertTrue(all(result["new_column"] == 42))

        # Test assignment with column expression
        df["double_age"] = df["age"] * 2
        result = df.collect()
        self.assertTrue("double_age" in result.columns)
        for i, age in enumerate(self.data["age"]):
            self.assertEqual(result["double_age"][i], age * 2)

    def test_arithmetic_operations(self):
        df = ActuarialFrame(self.data, mode="debug")

        # Test basic arithmetic
        expr = df["age"] + 10
        self.assertIsInstance(expr, ExpressionProxy)

        df["age_plus_10"] = expr
        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            self.assertEqual(result["age_plus_10"][i], age + 10)

        # Test more complex arithmetic
        expr = (df["age"] * 2 - 5) / 3
        df["complex_calc"] = expr
        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            self.assertAlmostEqual(result["complex_calc"][i], (age * 2 - 5) / 3)

    def test_function_application(self):
        df = ActuarialFrame(self.data, mode="debug")

        # Test simple function application
        def square(x):
            return float(x * x)  # Return float to match Float64 return type

        df["age_squared"] = df["age"].apply(square)
        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            self.assertAlmostEqual(result["age_squared"][i], age * age)

        # Test with numpy functions
        df["age_sqrt"] = df["age"].apply(lambda x: np.sqrt(x), return_dtype=pl.Float64)
        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            self.assertAlmostEqual(result["age_sqrt"][i], np.sqrt(age))

    def test_plugin_functions(self):
        df = ActuarialFrame(self.data, mode="debug")

        # Test with plugin function - convert to expression first
        df["proj_months"] = fill_series(pl.col("age"), 0, 1)
        result = df.collect()
        self.assertTrue("proj_months" in result.columns)

        # Test with another plugin function
        df["age_floored"] = floor(pl.col("age"), 10)
        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            expected = (age // 10) * 10
            self.assertEqual(result["age_floored"][i], expected)

    def test_execution_mode_context_manager(self):
        original_mode = get_default_mode()
        try:
            # Set to opposite of original mode
            opposite_mode = "optimize" if original_mode == "debug" else "debug"
            set_default_mode(opposite_mode)

            # Check that context manager changes mode temporarily
            with execution_mode("debug"):
                self.assertEqual(get_default_mode(), "debug")
                df = ActuarialFrame(self.data)
                self.assertEqual(df._mode, "debug")

            # Check that mode is restored
            self.assertEqual(get_default_mode(), opposite_mode)

            with execution_mode("optimize"):
                self.assertEqual(get_default_mode(), "optimize")
                df = ActuarialFrame(self.data)
                self.assertEqual(df._mode, "optimize")

            # Check that mode is restored again
            self.assertEqual(get_default_mode(), opposite_mode)
        finally:
            set_default_mode(original_mode)


class TestModelCalculations(unittest.TestCase):
    def setUp(self):
        # Create a more complex test dataframe for model calculations
        self.data = pl.DataFrame(
            {
                "age": [35, 40, 45, 50, 55, 60, 65],
                "sex": ["M", "F", "M", "F", "M", "F", "M"],
                "premium": [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0],
                "sum_assured": [10000, 15000, 20000, 25000, 30000, 35000, 40000],
            }
        )

    def test_simple_model_debug_mode(self):
        def simple_model(df):
            # Constants
            max_age = 100

            # Basic calculations
            df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
            # Use direct expressions for plugin functions
            df["proj_months"] = fill_series(pl.col("age"), 0, 1)
            df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1

            # Additional calculations
            df["age_last"] = df["age"] + df["proj_years"] - 1

            return df

        # Run in debug mode
        df = ActuarialFrame(self.data, mode="debug")
        result = run_model(simple_model, df).collect()

        # Verify results
        self.assertTrue("num_proj_months" in result.columns)
        self.assertTrue("proj_months" in result.columns)
        self.assertTrue("proj_years" in result.columns)
        self.assertTrue("age_last" in result.columns)

        # Check specific calculations for the first row
        max_age = 100
        first_age = self.data["age"][0]
        num_proj_months = (max_age - first_age) * 12 + 1

        self.assertEqual(result["num_proj_months"][0], num_proj_months)

    def test_simple_model_optimize_mode(self):
        def simple_model(df):
            # Constants
            max_age = 100

            # Basic calculations
            df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
            # Use direct expressions for plugin functions
            df["proj_months"] = fill_series(pl.col("age"), 0, 1)
            df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1

            # Additional calculations
            df["age_last"] = df["age"] + df["proj_years"] - 1

            return df

        # Run in optimize mode
        df = ActuarialFrame(self.data, mode="optimize")
        result = run_model(simple_model, df).collect()

        # Verify results
        self.assertTrue("num_proj_months" in result.columns)
        self.assertTrue("proj_months" in result.columns)
        self.assertTrue("proj_years" in result.columns)
        self.assertTrue("age_last" in result.columns)

        # Check specific calculations for the first row
        max_age = 100
        first_age = self.data["age"][0]
        num_proj_months = (max_age - first_age) * 12 + 1

        self.assertEqual(result["num_proj_months"][0], num_proj_months)

    def test_compare_debug_and_optimize_results(self):
        def complex_model(df):
            # Constants
            max_age = 100
            premium_factor = 0.05
            interest_rate = 0.03

            # Basic projections
            df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
            # Use direct expressions for plugin functions
            df["proj_months"] = fill_series(pl.col("age"), 0, 1)
            df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1

            # Financial calculations
            df["future_premium"] = (
                df["premium"] * (1 + premium_factor) ** df["proj_years"]
            )
            df["future_sum_assured"] = (
                df["sum_assured"] * (1 + interest_rate) ** df["proj_years"]
            )

            # Use the global risk factor function instead of a local one
            df["risk_factor"] = df["age"].apply(_risk_factor)
            df["mortality_cost"] = df["future_sum_assured"] * df["risk_factor"]

            return df

        # Run in debug mode
        df_debug = ActuarialFrame(self.data, mode="debug")
        result_debug = run_model(complex_model, df_debug).collect()

        # Run in optimize mode
        df_optimize = ActuarialFrame(self.data, mode="optimize")
        result_optimize = run_model(complex_model, df_optimize).collect()

        # Compare results to ensure they're identical
        for column in result_debug.columns:
            for i in range(len(result_debug)):
                # Use almost equal for floating point comparisons
                if isinstance(result_debug[column][i], (float, np.float64)):
                    self.assertAlmostEqual(
                        result_debug[column][i], result_optimize[column][i], places=10
                    )
                else:
                    self.assertEqual(
                        result_debug[column][i], result_optimize[column][i]
                    )

    def test_model_with_numpy_functions(self):
        def model_with_numpy(df):
            # Use numpy functions
            df["log_age"] = df["age"].apply(lambda x: np.log(x))
            df["exp_premium"] = df["premium"].apply(lambda x: np.exp(x / 1000))
            df["sin_age"] = df["age"].apply(
                lambda x: np.sin(x * np.pi / 180)
            )  # age in degrees

            return df

        # Run in debug mode
        df = ActuarialFrame(self.data, mode="debug")
        result = run_model(model_with_numpy, df).collect()

        # Check results
        for i, age in enumerate(self.data["age"]):
            self.assertAlmostEqual(result["log_age"][i], np.log(age))
            self.assertAlmostEqual(
                result["exp_premium"][i], np.exp(self.data["premium"][i] / 1000)
            )
            self.assertAlmostEqual(result["sin_age"][i], np.sin(age * np.pi / 180))


class TestNumbaOptimization(unittest.TestCase):
    def setUp(self):
        self.data = pl.DataFrame(
            {
                "age": [35, 40, 45, 50, 55],
                "premium": [100.0, 150.0, 200.0, 250.0, 300.0],
            }
        )

    @pytest.mark.skipif(not HAS_NUMBA, reason="Numba not installed")
    def test_numba_optimization(self):
        # Define a function that Numba can optimize
        def calculate_mortality(age):
            base_rate = 0.001
            for i in range(10):  # Some iteration to make it slower in Python
                base_rate *= 1 + 0.03 * age / 100
            return base_rate

        # Run in optimize mode with mocking to verify Numba is used
        df = ActuarialFrame(self.data, mode="optimize")

        # We need to mock both vectorize and njit since our code now tries both
        with (
            mock.patch("numba.vectorize") as mock_vectorize,
            mock.patch("numba.njit") as mock_njit,
        ):
            # Make both mocks just return the function (no real compilation)
            mock_vectorize.side_effect = lambda f: f
            mock_njit.side_effect = lambda f: f

            # Perform the calculation that should use Numba
            df["mortality"] = df["age"].apply(calculate_mortality)

            # Check that either vectorize or njit was called
            self.assertTrue(
                mock_vectorize.called or mock_njit.called,
                "Neither numba.vectorize nor numba.njit was called",
            )


class TestPerformance(unittest.TestCase):
    def setUp(self):
        """Set up test data"""
        # Create test data
        ages = np.random.randint(20, 70, 10000)
        premiums = np.random.uniform(100, 500, 10000)
        sum_assured = np.random.uniform(10000, 50000, 10000)
        self.data = pl.DataFrame(
            {
                "age": ages,
                "premium": premiums,
                "sum_assured": sum_assured,
            }
        )

        # Create mortality rates table
        ages = list(range(20, 100))
        genders = ["M"] * len(ages) + ["F"] * len(ages)
        ages = ages * 2  # Duplicate for both genders
        rates = [0.001 * (1.05**i) for i in range(len(ages))]

        mortality_rates = pl.DataFrame(
            {
                "age_last": ages,
                "gender": genders,
                "mortality_rate": rates,
            }
        )

    def test_performance_comparison(self):
        import time

        def complex_model(df):
            # Constants
            max_age = 100
            premium_factor = 0.05
            interest_rate = 0.03

            # Basic projections
            df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
            # Use direct expressions for plugin functions
            df["proj_months"] = fill_series(pl.col("age"), 0, 1)
            df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1

            # Financial calculations
            df["future_premium"] = (
                df["premium"] * (1 + premium_factor) ** df["proj_years"]
            )
            df["future_sum_assured"] = (
                df["sum_assured"] * (1 + interest_rate) ** df["proj_years"]
            )

            # Complex calculations with custom functions - use global function
            df["risk_factor"] = df["age"].apply(_risk_factor)
            df["mortality_cost"] = df["future_sum_assured"] * df["risk_factor"]

            # More calculations to stress test
            for i in range(5):
                df[f"premium_{i}"] = df["premium"] * (i + 1)
                df[f"sum_assured_{i}"] = df["sum_assured"] / (i + 1)
                df[f"combined_{i}"] = df[f"premium_{i}"] * df[f"sum_assured_{i}"]

            return df

        # Measure debug mode performance
        start_time = time.time()
        df_debug = ActuarialFrame(self.data, mode="debug")
        result_debug = run_model(complex_model, df_debug).collect()
        debug_time = time.time() - start_time

        # Measure optimize mode performance
        start_time = time.time()
        df_optimize = ActuarialFrame(self.data, mode="optimize")
        result_optimize = run_model(complex_model, df_optimize).collect()
        optimize_time = time.time() - start_time

        # Print performance results
        print("\nPerformance comparison:")
        print(f"Debug mode: {debug_time:.4f} seconds")
        print(f"Optimize mode: {optimize_time:.4f} seconds")
        print(f"Speedup: {debug_time / optimize_time:.2f}x")

        # We expect optimize mode to be faster, but this might not always be true
        # in automated tests due to various factors. Just check they both ran.
        self.assertEqual(len(result_debug), len(self.data))
        self.assertEqual(len(result_optimize), len(self.data))


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        # Create a test dataframe with some columns
        self.data = pl.DataFrame(
            {
                "age": [35, 40, 45],
                "sex": ["M", "F", "M"],
                "premium": [100.0, 150.0, 200.0],
                "policy_duration": [1, 2, 3],
                "policy_start_date": ["2020-01-01", "2019-05-15", "2021-03-30"],
            }
        )
        self.df = ActuarialFrame(self.data)  # Create instance for tests

    def test_missing_column_extraction(self):
        """Test extraction of missing column names from different error formats using _extract_missing_column_robust"""

        # Test direct format
        error_msg_direct = "ColumnNotFoundError: policy_duration_as_int"
        self.assertEqual(
            self.df._extract_missing_column_robust(error_msg_direct),
            "policy_duration_as_int",
        )

        # Test quoted format
        error_msg_quoted = "Column 'policy_duration_as_int' not found"
        self.assertEqual(
            self.df._extract_missing_column_robust(error_msg_quoted),
            "policy_duration_as_int",
        )

        # Test complex Polars format
        error_msg_complex = (
            "policy_duration_as_int\n\n"
            "Resolved plan until failure:\n\n"
            "\t---> FAILED HERE RESOLVING 'with_columns' <---\n"
            "... rest of plan ..."
        )
        self.assertEqual(
            self.df._extract_missing_column_robust(error_msg_complex),
            "policy_duration_as_int",
        )

        # Test fallback format
        self.df._column_order.append("missing_but_assigned")  # Add to tracked columns
        error_msg_fallback = "Some other error FAILED HERE RESOLVING involving missing_but_assigned maybe"
        self.assertEqual(
            self.df._extract_missing_column_robust(error_msg_fallback),
            "missing_but_assigned",
        )
        # Clean up for other tests
        if "missing_but_assigned" in self.df._column_order:
            self.df._column_order.remove("missing_but_assigned")

    def test_levenshtein_distance(self):
        """Test the fuzzy matching fallback (_find_similar_columns with Levenshtein)"""
        # Temporarily disable thefuzz import to test fallback
        original_import = __builtins__["__import__"]

        def import_mock(name, *args):
            if name == "thefuzz":
                raise ImportError("Mock ImportError for thefuzz")
            return original_import(name, *args)

        __builtins__["__import__"] = import_mock

        try:
            # Test close match using Levenshtein fallback
            similar_cols = self.df._find_similar_columns(
                "police_duration", ["policy_duration", "age", "sex"]
            )
            self.assertIn("policy_duration", similar_cols)

            # Test substring match fallback
            similar = self.df._find_similar_columns(
                "premium_rate", ["premium", "rate", "age"]
            )
            self.assertIn(
                "premium", similar
            )  # Substring should still be preferred if calculated

        finally:
            # Restore the original import function
            __builtins__["__import__"] = original_import

    def test_collect_error_handling(self):
        """Test that _handle_execution_error formats column errors from collect() correctly"""
        # Use a real Polars error this time if possible, otherwise mock
        try:
            # Create a scenario that will likely cause a ColumnNotFoundError
            lazy_df = self.df._df.with_columns(pl.col("non_existent_col") * 2)
            # Manually trigger the error collection part
            lazy_df.collect()
        except Exception as e:
            # Check if the error is the type we expect
            if "ColumnNotFoundError" in str(type(e)) or "not found" in str(e):
                # Now test our handler with this real error
                with self.assertRaises(Exception) as context:
                    self.df._handle_execution_error(e)

                formatted_error_message = str(context.exception)
                self.assertIn(
                    "Column 'non_existent_col' not found", formatted_error_message
                )
                self.assertIn("Available columns are:", formatted_error_message)
                self.assertIn("age", formatted_error_message)
            else:
                # If the setup didn't raise the expected error, we can't test the handler directly
                # Fallback to mocking if necessary, but prefer testing with real errors
                self.skipTest(
                    "Could not trigger a real ColumnNotFoundError for testing _handle_execution_error"
                )

    def test_profile_error_handling(self):
        """Test that _handle_execution_error formats column errors from profile() correctly"""
        try:
            lazy_df = self.df._df.with_columns(pl.col("another_missing_col") + 1)
            lazy_df.profile()
        except Exception as e:
            if "ColumnNotFoundError" in str(type(e)) or "not found" in str(e):
                with self.assertRaises(Exception) as context:
                    self.df._handle_execution_error(e)

                formatted_error_message = str(context.exception)
                self.assertIn(
                    "Column 'another_missing_col' not found", formatted_error_message
                )
                self.assertIn("Available columns are:", formatted_error_message)
            else:
                self.skipTest(
                    "Could not trigger a real ColumnNotFoundError for testing _handle_execution_error in profile"
                )

    def test_thefuzz_integration(self):
        """Test that _find_similar_columns uses thefuzz correctly"""
        try:
            from thefuzz import process  # Check if available

            # Test fuzzy matches using the refactored method
            similar_cols = self.df._find_similar_columns(
                "police_duration", ["policy_duration", "age", "sex"]
            )
            self.assertIn("policy_duration", similar_cols)

            similar_cols = self.df._find_similar_columns(
                "policyy_duration", ["policy_duration", "premium", "age"]
            )
            self.assertIn("policy_duration", similar_cols)

            similar_cols = self.df._find_similar_columns(
                "duration_policy", ["policy_duration", "premium", "age"]
            )
            self.assertIn("policy_duration", similar_cols)

        except ImportError:
            self.skipTest("thefuzz is not installed, skipping test_thefuzz_integration")

    def test_polars_complex_error_extraction(self):
        """Test _extract_missing_column_robust for complex Polars error message with plan"""
        error_message = (
            "policy_duration_as_int\n\n"
            "Resolved plan until failure:\n\n"
            "\t---> FAILED HERE RESOLVING 'with_columns' <---\n"
            "... some plan details ..."
        )
        # Test extraction directly using the helper method
        missing_col = self.df._extract_missing_column_robust(error_message)
        self.assertEqual(missing_col, "policy_duration_as_int")

    def test_fallback_extraction_logic(self):
        """Test the _extract_missing_column_robust fallback logic"""
        self.df._column_order.append("missing_but_assigned")  # Simulate assigned column
        error_message = "Some other error FAILED HERE RESOLVING involving missing_but_assigned maybe"

        # Test extraction directly using the helper method
        missing_col = self.df._extract_missing_column_robust(error_message)
        self.assertEqual(missing_col, "missing_but_assigned")
        # Clean up
        if "missing_but_assigned" in self.df._column_order:
            self.df._column_order.remove("missing_but_assigned")


if __name__ == "__main__":
    unittest.main()
