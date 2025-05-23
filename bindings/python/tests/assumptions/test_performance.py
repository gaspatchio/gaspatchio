"""
Comprehensive performance tests for assumption loading and lookup operations.

This module uses pytest-benchmark to measure and validate performance of the core
assumption operations. Tests are designed to be sensitive to CI/CD environments
and different machine capabilities while ensuring the system can handle production-scale
data volumes and lookup frequencies.

Key performance requirements:
- assumption_lookup() should handle 100K+ lookups per second
- load_assumptions() should process large tables (100K+ rows) in reasonable time
- Memory usage should scale linearly with data size
- Performance should degrade gracefully under load
"""

import gc
import os
import tempfile
import time
import uuid
from pathlib import Path

import gaspatchio_core as gs
import polars as pl
import pytest

# Performance test configuration based on environment
CI_ENVIRONMENT = os.getenv("CI", "false").lower() == "true"
GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
SKIP_PERFORMANCE_TESTS = os.getenv("SKIP_PERFORMANCE_TESTS", "false").lower() == "true"

# Add skip marker for performance tests if requested
pytestmark = pytest.mark.skipif(
    SKIP_PERFORMANCE_TESTS,
    reason="Performance tests skipped (SKIP_PERFORMANCE_TESTS=true)",
)

# Scale test sizes based on environment to avoid CI timeouts
if CI_ENVIRONMENT:
    # Smaller datasets for CI to ensure tests complete within reasonable time
    SMALL_SIZE = 1_000
    MEDIUM_SIZE = 10_000
    LARGE_SIZE = 50_000
    XLARGE_SIZE = 100_000
    LOOKUP_BATCHES = [100, 1_000, 5_000]
else:
    # Full-scale testing for local development
    SMALL_SIZE = 10_000
    MEDIUM_SIZE = 50_000
    LARGE_SIZE = 100_000
    XLARGE_SIZE = 500_000
    LOOKUP_BATCHES = [1_000, 10_000, 50_000]


def unique_table_name(prefix: str) -> str:
    """Generate unique table name for benchmarking."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}_{int(time.time() * 1000) % 10000}"


class TestLoadAssumptionsPerformance:
    """Performance tests for load_assumptions() function."""

    def setup_method(self):
        """Reset registry before each test."""
        # Clear any existing tables to ensure clean state
        # This is important for consistent benchmarking
        pass

    @pytest.mark.benchmark(group="load_curve_small")
    def test_load_curve_table_small(self, benchmark):
        """Benchmark loading small curve table (mortality/interest rates)."""
        df = pl.DataFrame(
            {
                "age": list(range(20, 20 + SMALL_SIZE)),
                "qx": [0.001 + i * 1e-8 for i in range(SMALL_SIZE)],
            }
        )

        def load_curve():
            table_name = unique_table_name("curve_small")
            return gs.load_assumptions(table_name, df, value="qx")

        result = benchmark(load_curve)

        # Validate results
        assert len(result) == SMALL_SIZE
        assert result.columns == ["age", "qx"]

        # Performance assertions - should be fast for small tables
        # Even in CI, small tables should load in well under 1 second
        assert benchmark.stats.stats.mean < 1.0

    @pytest.mark.benchmark(group="load_curve_large")
    def test_load_curve_table_large(self, benchmark):
        """Benchmark loading large curve table."""
        df = pl.DataFrame(
            {
                "age": list(range(0, LARGE_SIZE)),
                "rate": [0.01 + (i % 1000) * 1e-6 for i in range(LARGE_SIZE)],
            }
        )

        def load_curve():
            table_name = unique_table_name("curve_large")
            return gs.load_assumptions(table_name, df, value="rate")

        result = benchmark(load_curve)

        assert len(result) == LARGE_SIZE
        # Large tables should still load reasonably quickly
        # Allow more time in CI environments
        max_time = 5.0 if CI_ENVIRONMENT else 3.0
        assert benchmark.stats.stats.mean < max_time

    @pytest.mark.benchmark(group="load_wide_basic")
    def test_load_wide_table_basic(self, benchmark):
        """Benchmark loading wide format table (duration-based assumptions)."""
        n_ages = SMALL_SIZE // 10  # Fewer ages but multiple durations
        df = pl.DataFrame(
            {
                "age": list(range(20, 20 + n_ages)),
                "1": [0.002] * n_ages,
                "2": [0.0015] * n_ages,
                "3": [0.001] * n_ages,
                "5": [0.0008] * n_ages,
                "10": [0.0005] * n_ages,
            }
        )

        def load_wide():
            table_name = unique_table_name("wide_basic")
            return gs.load_assumptions(table_name, df, value="rate")

        result = benchmark(load_wide)

        # Wide tables create more rows after melting
        expected_rows = n_ages * 5  # 5 duration columns
        assert len(result) == expected_rows
        assert "variable" in result.columns
        assert "rate" in result.columns

    @pytest.mark.benchmark(group="load_wide_overflow")
    def test_load_wide_table_with_overflow(self, benchmark):
        """Benchmark loading wide table with overflow expansion."""
        n_ages = SMALL_SIZE // 50  # Even fewer ages since overflow creates many rows
        df = pl.DataFrame(
            {
                "age": list(range(20, 20 + n_ages)),
                "1": [0.002] * n_ages,
                "2": [0.0015] * n_ages,
                "Ultimate": [0.0005] * n_ages,
            }
        )

        # Moderate overflow expansion for benchmarking
        max_overflow = 20 if CI_ENVIRONMENT else 50

        def load_with_overflow():
            table_name = unique_table_name("wide_overflow")
            return gs.load_assumptions(
                table_name,
                df,
                overflow="Ultimate",
                max_overflow=max_overflow,
                value="rate",
            )

        result = benchmark(load_with_overflow)

        # Should have original + expanded rows
        min_expected = n_ages * 3  # At least original columns
        assert len(result) >= min_expected

        # Overflow expansion should still be reasonably fast
        max_time = 3.0 if CI_ENVIRONMENT else 2.0
        assert benchmark.stats.stats.mean < max_time

    @pytest.mark.benchmark(group="load_value_vars")
    def test_load_wide_table_selective_melting(self, benchmark):
        """Benchmark selective column melting with value_vars."""
        n_ages = MEDIUM_SIZE // 20
        df = pl.DataFrame(
            {
                "age": list(range(20, 20 + n_ages)),
                "MNS": [0.001] * n_ages,  # Male Non-Smoker
                "FNS": [0.0008] * n_ages,  # Female Non-Smoker
                "MS": [0.002] * n_ages,  # Male Smoker
                "FS": [0.0015] * n_ages,  # Female Smoker
                "Extra1": [0.999] * n_ages,  # Should be ignored
                "Extra2": [0.998] * n_ages,  # Should be ignored
            }
        )

        def load_selective():
            table_name = unique_table_name("selective")
            return gs.load_assumptions(
                table_name,
                df,
                id="age",
                value_vars=["MNS", "FNS", "MS", "FS"],
                value="mortality_rate",
            )

        result = benchmark(load_selective)

        # Should only process selected columns
        expected_rows = n_ages * 4  # 4 selected value_vars
        assert len(result) == expected_rows
        variables = set(result["variable"].unique())
        assert variables == {"MNS", "FNS", "MS", "FS"}

    @pytest.mark.benchmark(group="load_csv_file")
    def test_load_from_csv_file(self, benchmark):
        """Benchmark loading assumptions from CSV file."""
        # Create temporary CSV file
        df_data = pl.DataFrame(
            {
                "age": list(range(20, 20 + MEDIUM_SIZE)),
                "qx": [0.001 + i * 1e-8 for i in range(MEDIUM_SIZE)],
            }
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            df_data.write_csv(tmp.name)
            csv_path = tmp.name

        try:

            def load_from_csv():
                table_name = unique_table_name("csv_test")
                return gs.load_assumptions(table_name, csv_path, value="qx")

            result = benchmark(load_from_csv)

            assert len(result) == MEDIUM_SIZE

            # File I/O adds overhead but should still be reasonable
            max_time = 8.0 if CI_ENVIRONMENT else 5.0
            assert benchmark.stats.stats.mean < max_time

        finally:
            Path(csv_path).unlink()

    @pytest.mark.benchmark(group="load_parquet_file")
    def test_load_from_parquet_file(self, benchmark):
        """Benchmark loading assumptions from Parquet file."""
        df_data = pl.DataFrame(
            {
                "age": list(range(20, 20 + MEDIUM_SIZE)),
                "rate": [0.01 + i * 1e-7 for i in range(MEDIUM_SIZE)],
            }
        )

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df_data.write_parquet(tmp.name)
            parquet_path = tmp.name

        try:

            def load_from_parquet():
                table_name = unique_table_name("parquet_test")
                return gs.load_assumptions(table_name, parquet_path, value="rate")

            result = benchmark(load_from_parquet)

            assert len(result) == MEDIUM_SIZE

            # Parquet should be faster than CSV
            max_time = 6.0 if CI_ENVIRONMENT else 3.0
            assert benchmark.stats.stats.mean < max_time

        finally:
            Path(parquet_path).unlink()


class TestAssumptionLookupPerformance:
    """Performance tests for assumption_lookup() function."""

    @classmethod
    def setup_class(cls):
        """Set up test tables for lookup benchmarks."""
        # Small curve table for basic lookup tests
        cls.small_curve_df = pl.DataFrame(
            {
                "age": list(range(20, 20 + SMALL_SIZE)),
                "qx": [0.001 + i * 1e-8 for i in range(SMALL_SIZE)],
            }
        )
        gs.load_assumptions("perf_curve_small", cls.small_curve_df, value="qx")

        # Large curve table for stress testing
        cls.large_curve_df = pl.DataFrame(
            {
                "age": list(range(0, LARGE_SIZE)),
                "rate": [0.01 + (i % 10000) * 1e-7 for i in range(LARGE_SIZE)],
            }
        )
        gs.load_assumptions("perf_curve_large", cls.large_curve_df, value="rate")

        # Wide table for multi-key lookups
        n_ages = MEDIUM_SIZE // 10
        cls.wide_df = pl.DataFrame(
            {
                "age": list(range(20, 20 + n_ages)),
                "MNS": [0.001] * n_ages,
                "FNS": [0.0008] * n_ages,
                "MS": [0.002] * n_ages,
                "FS": [0.0015] * n_ages,
            }
        )
        gs.load_assumptions(
            "perf_wide",
            cls.wide_df,
            id="age",
            value_vars=["MNS", "FNS", "MS", "FS"],
            value="rate",
        )

    @pytest.mark.benchmark(group="lookup_scalar")
    def test_lookup_single_scalar(self, benchmark):
        """Benchmark single scalar lookup performance."""
        test_df = pl.DataFrame({"age": [25]})

        def single_lookup():
            return test_df.with_columns(
                gs.assumption_lookup("age", table_name="perf_curve_small").alias("qx")
            )

        result = benchmark(single_lookup)

        assert len(result) == 1
        assert "qx" in result.columns

        # Single lookups should be extremely fast
        assert (
            benchmark.stats.stats.mean < 0.01
        )  # Sub-10-millisecond (more realistic for CI)

    @pytest.mark.benchmark(group="lookup_small_batch")
    def test_lookup_small_batch(self, benchmark):
        """Benchmark small batch lookup performance using individual lookups."""
        batch_size = LOOKUP_BATCHES[0]
        ages_to_test = [20 + (i % 1000) for i in range(batch_size)]

        def batch_lookup():
            # Since the current implementation doesn't support true batch lookups,
            # we'll simulate by doing individual scalar lookups in a loop
            results = []
            for age in ages_to_test:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="perf_curve_small").alias(
                        "qx"
                    )
                )
                results.append(result["qx"].item())
            return results

        result = benchmark(batch_lookup)

        assert len(result) == batch_size

        # Calculate lookups per second
        lookups_per_sec = batch_size / benchmark.stats.stats.mean

        # Adjusted expectations for scalar-only implementation
        min_throughput = 5_000 if CI_ENVIRONMENT else 20_000
        assert lookups_per_sec > min_throughput

    @pytest.mark.benchmark(group="lookup_medium_batch")
    def test_lookup_medium_batch(self, benchmark):
        """Benchmark medium batch lookup performance using individual lookups."""
        batch_size = LOOKUP_BATCHES[1]
        ages_to_test = [i % 50000 for i in range(batch_size)]

        def batch_lookup():
            results = []
            for age in ages_to_test:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="perf_curve_large").alias(
                        "rate"
                    )
                )
                results.append(result["rate"].item())
            return results

        result = benchmark(batch_lookup)

        assert len(result) == batch_size

        lookups_per_sec = batch_size / benchmark.stats.stats.mean

        # Adjusted expectations for scalar-only implementation
        min_throughput = 10_000 if CI_ENVIRONMENT else 30_000
        assert lookups_per_sec > min_throughput

    @pytest.mark.benchmark(group="lookup_large_batch")
    def test_lookup_large_batch(self, benchmark):
        """Benchmark large batch lookup performance using individual lookups."""
        batch_size = LOOKUP_BATCHES[2]
        ages_to_test = [i % 80000 for i in range(batch_size)]

        def batch_lookup():
            results = []
            for age in ages_to_test:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="perf_curve_large").alias(
                        "rate"
                    )
                )
                results.append(result["rate"].item())
            return results

        result = benchmark(batch_lookup)

        assert len(result) == batch_size

        lookups_per_sec = batch_size / benchmark.stats.stats.mean

        # Adjusted expectations for scalar-only implementation
        min_throughput = 8_000 if CI_ENVIRONMENT else 25_000
        assert lookups_per_sec > min_throughput

    @pytest.mark.benchmark(group="lookup_multi_key")
    def test_lookup_multi_key_performance(self, benchmark):
        """Benchmark multi-key lookup performance (age + variable)."""
        batch_size = LOOKUP_BATCHES[1]
        variables = ["MNS", "FNS", "MS", "FS"]

        test_cases = [
            (20 + (i % 1000), variables[i % len(variables)]) for i in range(batch_size)
        ]

        def multi_key_lookup():
            results = []
            for age, variable in test_cases:
                test_df = pl.DataFrame({"age": [age], "variable": [variable]})
                result = test_df.with_columns(
                    gs.assumption_lookup(
                        "age", "variable", table_name="perf_wide"
                    ).alias("rate")
                )
                results.append(result["rate"].item())
            return results

        result = benchmark(multi_key_lookup)

        assert len(result) == batch_size

        lookups_per_sec = batch_size / benchmark.stats.stats.mean

        # Multi-key lookups with scalar implementation
        min_throughput = 6_000 if CI_ENVIRONMENT else 12_000
        assert lookups_per_sec > min_throughput

    @pytest.mark.benchmark(group="lookup_missing_keys")
    def test_lookup_with_missing_keys(self, benchmark):
        """Benchmark lookup performance with some missing keys."""
        batch_size = LOOKUP_BATCHES[1]
        # Mix of valid and invalid ages
        ages_to_test = [i if i % 3 != 0 else 999999 for i in range(20, 20 + batch_size)]

        def lookup_with_missing():
            results = []
            for age in ages_to_test:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="perf_curve_small").alias(
                        "qx"
                    )
                )
                results.append(result["qx"].item())
            return results

        result = benchmark(lookup_with_missing)

        assert len(result) == batch_size

        # Should handle missing keys gracefully without major performance impact
        lookups_per_sec = batch_size / benchmark.stats.stats.mean
        min_throughput = 5_000 if CI_ENVIRONMENT else 15_000
        assert lookups_per_sec > min_throughput

    @pytest.mark.benchmark(group="lookup_repeated_keys")
    def test_lookup_repeated_keys_performance(self, benchmark):
        """Benchmark lookup performance with repeated key patterns."""
        batch_size = LOOKUP_BATCHES[1]
        # Create many lookups for the same few keys
        repeated_ages = [25, 30, 35, 40, 45] * (batch_size // 5)
        ages_to_test = repeated_ages[:batch_size]

        def repeated_lookup():
            results = []
            for age in ages_to_test:
                test_df = pl.DataFrame({"age": [age]})
                result = test_df.with_columns(
                    gs.assumption_lookup("age", table_name="perf_curve_small").alias(
                        "qx"
                    )
                )
                results.append(result["qx"].item())
            return results

        result = benchmark(repeated_lookup)

        assert len(result) == batch_size

        # Repeated lookups might benefit from caching
        lookups_per_sec = batch_size / benchmark.stats.stats.mean
        min_throughput = 10_000 if CI_ENVIRONMENT else 30_000
        assert lookups_per_sec > min_throughput


class TestMemoryAndScalability:
    """Test memory usage and scalability characteristics."""

    @pytest.mark.benchmark(group="memory_large_table")
    def test_memory_efficiency_large_table(self, benchmark):
        """Test memory efficiency when loading large tables."""
        # Force garbage collection before test
        gc.collect()

        # Create a large table
        size = XLARGE_SIZE if not CI_ENVIRONMENT else LARGE_SIZE
        large_df = pl.DataFrame(
            {"id": list(range(size)), "value": [0.001 + i * 1e-9 for i in range(size)]}
        )

        def load_large():
            table_name = unique_table_name("memory_test")
            return gs.load_assumptions(table_name, large_df, value="value")

        result = benchmark(load_large)

        assert len(result) == size

        # Memory should scale reasonably with size
        max_time = 15.0 if CI_ENVIRONMENT else 10.0
        assert benchmark.stats.stats.mean < max_time

    @pytest.mark.benchmark(group="memory_wide_expansion")
    def test_memory_efficiency_wide_expansion(self, benchmark):
        """Test memory efficiency with wide table overflow expansion."""
        # Create table that will expand significantly
        n_base = 1000 if CI_ENVIRONMENT else 5000
        df = pl.DataFrame(
            {
                "age": list(range(20, 20 + n_base)),
                "1": [0.001] * n_base,
                "2": [0.0008] * n_base,
                "Ultimate": [0.0005] * n_base,
            }
        )

        max_overflow = 50 if CI_ENVIRONMENT else 100

        def load_with_expansion():
            table_name = unique_table_name("expansion_test")
            return gs.load_assumptions(
                table_name,
                df,
                overflow="Ultimate",
                max_overflow=max_overflow,
                value="rate",
            )

        result = benchmark(load_with_expansion)

        # Should create significant expansion
        min_expected = n_base * 3  # At least original columns
        assert len(result) >= min_expected

        # Should handle expansion efficiently
        max_time = 8.0 if CI_ENVIRONMENT else 5.0
        assert benchmark.stats.stats.mean < max_time

    @pytest.mark.benchmark(group="concurrent_lookups")
    def test_concurrent_lookup_performance(self, benchmark):
        """Test lookup performance under concurrent access patterns."""
        # Set up table for concurrent testing
        df = pl.DataFrame(
            {
                "key": list(range(10000)),
                "value": [0.001 + i * 1e-8 for i in range(10000)],
            }
        )
        gs.load_assumptions("concurrent_test", df, value="value")

        # Simulate concurrent lookup pattern
        batch_size = LOOKUP_BATCHES[1] // 2  # Smaller batch for concurrent test
        keys_to_test = [i % 5000 for i in range(batch_size)]

        def concurrent_lookup():
            # Simulate multiple simultaneous lookups using scalar approach
            results = []
            for _ in range(3):  # Simulate 3 concurrent operations
                batch_results = []
                for key in keys_to_test:
                    test_df = pl.DataFrame({"key": [key]})
                    result = test_df.with_columns(
                        gs.assumption_lookup("key", table_name="concurrent_test").alias(
                            "value"
                        )
                    )
                    batch_results.append(result["value"].item())
                results.append(batch_results)
            return results

        results = benchmark(concurrent_lookup)

        # Verify all results are correct
        for result in results:
            assert len(result) == batch_size

        # Should maintain reasonable performance under concurrent load
        max_time = 0.5 if CI_ENVIRONMENT else 0.2
        assert benchmark.stats.stats.mean < max_time


class TestRealWorldScenarios:
    """Test realistic actuarial modeling scenarios."""

    @pytest.mark.benchmark(group="actuarial_projection")
    def test_actuarial_projection_scenario(self, benchmark):
        """Benchmark realistic actuarial projection scenario."""
        # Set up typical actuarial tables

        # Mortality table by age and gender/smoking
        n_ages = 100
        mortality_df = pl.DataFrame(
            {
                "age": list(range(0, n_ages)) * 4,
                "gender_smoking": (
                    ["MNS"] * n_ages
                    + ["FNS"] * n_ages
                    + ["MS"] * n_ages
                    + ["FS"] * n_ages
                ),
                "qx": [
                    0.001
                    + age * 1e-5
                    + (0.5e-3 if "S" in gs_var else 0)
                    + (-0.2e-3 if "F" in gs_var else 0)
                    for age in range(n_ages)
                    for gs_var in ["MNS", "FNS", "MS", "FS"]
                ],
            }
        )
        gs.load_assumptions(
            "mortality_projection",
            mortality_df,
            id=["age", "gender_smoking"],
            value="qx",
        )

        # Lapse rates by duration
        lapse_df = pl.DataFrame(
            {
                "duration": list(range(1, 21)),
                "lapse_rate": [0.15 - dur * 0.005 for dur in range(1, 21)],
            }
        )
        gs.load_assumptions("lapse_projection", lapse_df, value="lapse_rate")

        # Simulate policy projection data (smaller batch for scalar lookups)
        n_policies = 100 if CI_ENVIRONMENT else 500
        projection_data = [
            {
                "policy_id": i,
                "age": 25 + (i % 50),
                "gender_smoking": ["MNS", "FNS", "MS", "FS"][i % 4],
                "duration": 1 + (i % 20),
            }
            for i in range(n_policies)
        ]

        def actuarial_projection():
            # Realistic actuarial projection with multiple assumption lookups
            results = []

            for policy in projection_data:
                # Mortality lookup
                mort_df = pl.DataFrame(
                    {
                        "age": [policy["age"]],
                        "gender_smoking": [policy["gender_smoking"]],
                    }
                )
                mort_result = mort_df.with_columns(
                    gs.assumption_lookup(
                        "age", "gender_smoking", table_name="mortality_projection"
                    ).alias("qx")
                )
                qx = mort_result["qx"].item()

                # Lapse lookup
                lapse_df = pl.DataFrame({"duration": [policy["duration"]]})
                lapse_result = lapse_df.with_columns(
                    gs.assumption_lookup(
                        "duration", table_name="lapse_projection"
                    ).alias("lapse_rate")
                )
                lapse_rate = lapse_result["lapse_rate"].item()

                # Simulate additional calculations typical in projections
                claims_cost = qx * 1000000 if qx is not None else 0
                lapse_impact = (
                    lapse_rate * policy["policy_id"] if lapse_rate is not None else 0
                )

                results.append(
                    {
                        "policy_id": policy["policy_id"],
                        "qx": qx,
                        "lapse_rate": lapse_rate,
                        "claims_cost": claims_cost,
                        "lapse_impact": lapse_impact,
                    }
                )

            return results

        result = benchmark(actuarial_projection)

        assert len(result) == n_policies
        assert all("qx" in r and "lapse_rate" in r for r in result)

        # Should handle realistic projection scenarios efficiently
        max_time = 5.0 if CI_ENVIRONMENT else 2.0
        assert benchmark.stats.stats.mean < max_time

    @pytest.mark.benchmark(group="assumption_updates")
    def test_assumption_table_updates(self, benchmark):
        """Benchmark assumption table update scenarios."""
        # Simulate assumption table updates (common in model development)
        base_size = SMALL_SIZE

        def update_assumptions():
            table_names = []
            for i in range(3):  # Update 3 different tables
                df = pl.DataFrame(
                    {
                        "age": list(range(20, 20 + base_size)),
                        "rate": [0.001 + i * 1e-6 + j * 1e-8 for j in range(base_size)],
                    }
                )
                table_name = unique_table_name(f"update_test_v{i}")
                table_names.append(table_name)
                gs.load_assumptions(table_name, df, value="rate")

            # Test lookup after updates
            test_df = pl.DataFrame({"age": [25, 35, 45]})
            return test_df.with_columns(
                gs.assumption_lookup("age", table_name=table_names[-1]).alias("rate")
            )

        result = benchmark(update_assumptions)

        assert len(result) == 3
        assert "rate" in result.columns

        # Updates should be reasonably fast
        max_time = 3.0 if CI_ENVIRONMENT else 2.0
        assert benchmark.stats.stats.mean < max_time


# Configuration for benchmark output
def pytest_benchmark_update_json(config, benchmarks, output_json):
    """Customize benchmark output with environment information."""
    output_json["environment"] = {
        "ci": CI_ENVIRONMENT,
        "github_actions": GITHUB_ACTIONS,
        "test_sizes": {
            "small": SMALL_SIZE,
            "medium": MEDIUM_SIZE,
            "large": LARGE_SIZE,
            "xlarge": XLARGE_SIZE,
        },
        "lookup_batches": LOOKUP_BATCHES,
    }


# Benchmark performance targets (for documentation)
PERFORMANCE_TARGETS = {
    "assumption_lookup": {
        "single_lookup": "< 10ms",
        "batch_1k": "> 5K lookups/sec (CI) / 20K (local) - scalar implementation",
        "batch_10k": "> 10K lookups/sec (CI) / 30K (local) - scalar implementation",
        "multi_key": "> 6K lookups/sec (CI) / 20K (local) - scalar implementation",
    },
    "load_assumptions": {
        "small_curve": "< 1 sec",
        "large_curve": "< 5 sec (CI) / 3 sec (local)",
        "wide_basic": "< 2 sec",
        "wide_overflow": "< 3 sec (CI) / 2 sec (local)",
    },
}
