"""
Integration tests for assumption table append functionality.

Tests cover complete workflows from load through append to lookup, error scenarios,
performance characteristics, and real-world usage patterns.
"""

import tempfile
from pathlib import Path

import gaspatchio_core as gs
import polars as pl
import pytest
from gaspatchio_core.assumptions._config import _clear_table_configs


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the global assumption registry before each test."""
    from gaspatchio_core._internal import PyAssumptionTableRegistry

    registry = PyAssumptionTableRegistry()
    registry.reset()
    _clear_table_configs()
    yield
    # Reset after test too for extra safety
    registry.reset()
    _clear_table_configs()


class TestFullMultiDimensionalWorkflow:
    """Test complete multi-dimensional table workflows."""

    def test_four_table_mortality_consolidation(self):
        """Test the classic 4-table mortality scenario from the spec."""
        # This replicates the exact workflow described in the specification
        # Load FSM (Female Smoker) - base table
        fsm_data = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.00074, 0.00081, 0.00089]}
        )
        gs.load_assumptions(
            "mortality_cso",
            fsm_data,
            additional_keys={"sex": "F", "smoking": "SM"},
            value="qx",
        )

        # Append MSM (Male Smoker)
        msm_data = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.00095, 0.00103, 0.00112]}
        )
        gs.append_assumptions(
            "mortality_cso", msm_data, additional_keys={"sex": "M", "smoking": "SM"}
        )

        # Append FNS (Female Non-Smoker)
        fns_data = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.00049, 0.00053, 0.00058]}
        )
        gs.append_assumptions(
            "mortality_cso", fns_data, additional_keys={"sex": "F", "smoking": "NS"}
        )

        # Append MNS (Male Non-Smoker)
        mns_data = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.00063, 0.00068, 0.00074]}
        )
        gs.append_assumptions(
            "mortality_cso", mns_data, additional_keys={"sex": "M", "smoking": "NS"}
        )

        # Now test multi-dimensional lookups
        model_points = pl.DataFrame(
            {
                "policy_id": [1, 2, 3, 4],
                "sex": ["F", "M", "F", "M"],
                "smoking": ["SM", "SM", "NS", "NS"],
                "age": [30, 31, 32, 30],
            }
        )

        # Perform the clean single lookup that replaces complex table name logic
        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "age", "sex", "smoking", table_name="mortality_cso"
                ).alias("mortality_rate")
            ]
        )

        # Validate results
        assert "mortality_rate" in result.columns
        assert len(result) == 4

        # Check specific expected rates
        rates = result["mortality_rate"].to_list()
        assert rates[0] == 0.00074  # F, SM, 30
        assert rates[1] == 0.00103  # M, SM, 31
        assert rates[2] == 0.00058  # F, NS, 32
        assert rates[3] == 0.00063  # M, NS, 30

    def test_wide_table_multi_product_scenario(self):
        """Test multi-product wide table consolidation."""
        # Product A morbidity rates
        product_a_data = pl.DataFrame(
            {
                "age": [40, 41, 42],
                "1": [0.0120, 0.0135, 0.0150],
                "2": [0.0110, 0.0125, 0.0140],
                "Ultimate": [0.0095, 0.0105, 0.0115],
            }
        )
        assumptions = gs.load_assumptions(
            "morbidity_table",
            product_a_data,
            overflow="Ultimate",
            max_overflow=10,
            lookup_keys=["age", "product", "duration"],
            additional_keys={"product": "A"},
        )

        print(assumptions)
        # Product B morbidity rates
        product_b_data = pl.DataFrame(
            {
                "age": [40, 41, 42],
                "1": [0.0140, 0.0155, 0.0170],
                "2": [0.0130, 0.0145, 0.0160],
                "Ultimate": [0.0115, 0.0125, 0.0135],
            }
        )
        gs.append_assumptions(
            "morbidity_table",
            product_b_data,
            lookup_keys=["age", "product", "duration"],
            additional_keys={"product": "B"},
        )

        # Test lookup across products
        model_points = pl.DataFrame(
            {
                "policy_id": [1, 2, 3, 4],
                "product": ["A", "B", "A", "B"],
                "age": [40, 41, 42, 40],
                "duration": [1, 2, 5, 10],  # 5 and 10 should get Ultimate rates
            }
        )

        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "age", "product", "duration", table_name="morbidity_table"
                ).alias("morbidity_rate")
            ]
        )
        print(result)
        # Validate results
        assert "morbidity_rate" in result.columns
        assert len(result) == 4

        rates = result["morbidity_rate"].to_list()
        assert rates[0] == 0.0120  # Product A, age 40, duration 1
        assert rates[1] == 0.0145  # Product B, age 41, duration 2
        assert (
            rates[2] == 0.0115
        )  # Product A, age 42, Ultimate (duration 5 -> Ultimate)
        assert (
            rates[3] == 0.0115
        )  # Product B, age 40, Ultimate (duration 10 -> Ultimate)

    def test_multi_stage_append_workflow(self):
        """Test a complex multi-stage append workflow."""
        # Start with basic mortality for one region
        base_data = pl.DataFrame(
            {"age": [25, 30, 35], "duration": [1, 1, 1], "qx": [0.001, 0.0015, 0.002]}
        )
        gs.load_assumptions(
            "global_mortality",
            base_data,
            id=["region", "product", "age", "duration"],
            additional_keys={"region": "US", "product": "Term"},
            value="qx",
        )

        # Add different product in same region
        append_data_1 = pl.DataFrame(
            {"age": [25, 30, 35], "duration": [1, 1, 1], "qx": [0.0012, 0.0018, 0.0024]}
        )
        gs.append_assumptions(
            "global_mortality",
            append_data_1,
            additional_keys={"region": "US", "product": "Whole"},
        )

        # Add different region, same products
        for product in ["Term", "Whole"]:
            append_data = pl.DataFrame(
                {
                    "age": [25, 30, 35],
                    "duration": [1, 1, 1],
                    "qx": [
                        x * 1.1
                        for x in (
                            [0.001, 0.0015, 0.002]
                            if product == "Term"
                            else [0.0012, 0.0018, 0.0024]
                        )
                    ],
                }
            )
            gs.append_assumptions(
                "global_mortality",
                append_data,
                additional_keys={"region": "EU", "product": product},
            )

        # Test comprehensive lookup
        test_points = pl.DataFrame(
            {
                "region": ["US", "US", "EU", "EU"],
                "product": ["Term", "Whole", "Term", "Whole"],
                "age": [30, 30, 30, 30],
                "duration": [1, 1, 1, 1],
            }
        )

        result = test_points.with_columns(
            [
                gs.assumption_lookup(
                    "region",
                    "product",
                    "age",
                    "duration",
                    table_name="global_mortality",
                ).alias("mortality_rate")
            ]
        )

        assert len(result) == 4
        rates = result["mortality_rate"].to_list()
        assert rates[0] == 0.0015  # US, Term
        assert rates[1] == 0.0018  # US, Whole
        assert abs(rates[2] - 0.00165) < 0.0001  # EU, Term (1.1x factor)
        assert abs(rates[3] - 0.00198) < 0.0001  # EU, Whole (1.1x factor)


class TestErrorScenarioEndToEnd:
    """Test complete error scenarios from start to finish."""

    def test_complete_table_not_found_workflow(self):
        """Test complete workflow when table doesn't exist."""
        # Try to lookup from non-existent table
        model_points = pl.DataFrame({"age": [30, 31]})

        with pytest.raises(
            ValueError, match="Assumption table 'missing_table' not found"
        ):
            model_points.with_columns(
                [gs.assumption_lookup("age", table_name="missing_table").alias("rate")]
            ).collect()

    def test_complete_key_mismatch_workflow(self):
        """Test complete workflow with key mismatches."""
        # Load a multi-key table
        data = pl.DataFrame(
            {
                "sex": ["M", "F"],
                "smoking": ["SM", "NS"],
                "age": [30, 30],
                "qx": [0.001, 0.0008],
            }
        )
        gs.load_assumptions("multi_key", data, id=["sex", "smoking", "age"], value="qx")

        # Try lookup with wrong number of keys
        model_points = pl.DataFrame({"age": [30, 31]})

        with pytest.raises(ValueError, match="Key count mismatch"):
            model_points.with_columns(
                [gs.assumption_lookup("age", table_name="multi_key").alias("rate")]
            ).collect()

    def test_complete_append_compatibility_workflow(self):
        """Test complete append compatibility error workflow."""
        # Load base table
        base_data = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        gs.load_assumptions(
            "compatibility_test",
            base_data,
            additional_keys={"product": "A"},
            value="rate",
        )

        # Try to append with incompatible value column
        append_data = pl.DataFrame({"age": [32, 33], "different_value": [0.003, 0.004]})

        with pytest.raises(ValueError, match="Value column name must match"):
            gs.append_assumptions(
                "compatibility_test",
                append_data,
                additional_keys={"product": "B"},
                value="different_value",
            )

    def test_duplicate_key_error_workflow(self):
        """Test duplicate key error in complete workflow."""
        # Load base table
        base_data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})
        gs.load_assumptions(
            "duplicate_test", base_data, additional_keys={"segment": "A"}, value="qx"
        )

        # Try to append with same additional_keys
        append_data = pl.DataFrame({"age": [32, 33], "qx": [0.003, 0.004]})

        with pytest.raises(ValueError, match="identical additional_keys values"):
            gs.append_assumptions(
                "duplicate_test", append_data, additional_keys={"segment": "A"}
            )


class TestPerformanceCharacteristics:
    """Test performance characteristics and scalability."""

    def test_append_performance_with_large_data(self):
        """Test append performance with larger datasets."""
        # Create larger base dataset
        base_ages = list(range(18, 100))  # 82 ages
        base_data = pl.DataFrame(
            {"age": base_ages, "qx": [0.001 + (age * 0.0001) for age in base_ages]}
        )

        gs.load_assumptions(
            "large_table", base_data, additional_keys={"product": "base"}, value="qx"
        )

        # Append multiple segments
        for i in range(5):  # 5 additional segments
            append_data = pl.DataFrame(
                {
                    "age": base_ages,
                    "qx": [0.001 + (age * 0.0001) + (i * 0.0005) for age in base_ages],
                }
            )

            gs.append_assumptions(
                "large_table", append_data, additional_keys={"product": f"segment_{i}"}
            )

        # Test lookup performance
        test_ages = [25, 35, 45, 55, 65, 75, 85, 95]
        products = ["base", "segment_0", "segment_2", "segment_4"]

        model_points = pl.DataFrame(
            {
                "age": test_ages * len(products),
                "product": [p for p in products for _ in test_ages],
            }
        )

        result = model_points.with_columns(
            [
                gs.assumption_lookup("product", "age", table_name="large_table").alias(
                    "mortality_rate"
                )
            ]
        )

        # Validate all lookups succeeded
        assert "mortality_rate" in result.columns
        assert len(result) == len(test_ages) * len(products)
        assert not result["mortality_rate"].is_null().any()

    def test_lookup_performance_unaffected(self):
        """Test that lookup performance is unaffected by append operations."""
        # Load base table
        base_data = pl.DataFrame(
            {"age": list(range(20, 100)), "qx": [0.001 + i * 0.0001 for i in range(80)]}
        )
        gs.load_assumptions("perf_test", base_data, additional_keys={"segment": "A"})

        # Time initial lookup (baseline)
        test_model_points = pl.DataFrame(
            {"age": [30, 40, 50, 60, 70], "segment": ["A"] * 5}
        )

        # Perform baseline lookup
        baseline_result = test_model_points.with_columns(
            [
                gs.assumption_lookup("segment", "age", table_name="perf_test").alias(
                    "rate"
                )
            ]
        )
        baseline_values = baseline_result["rate"].to_list()

        # Append several more segments
        for segment in ["B", "C", "D", "E"]:
            append_data = pl.DataFrame(
                {
                    "age": list(range(20, 100)),
                    "qx": [0.002 + i * 0.0001 for i in range(80)],
                }
            )
            gs.append_assumptions(
                "perf_test", append_data, additional_keys={"segment": segment}
            )

        # Test that original lookups still work and performance is maintained
        post_append_result = test_model_points.with_columns(
            [
                gs.assumption_lookup("segment", "age", table_name="perf_test").alias(
                    "rate"
                )
            ]
        )
        post_append_values = post_append_result["rate"].to_list()

        # Values should be identical (same segment A data)
        assert baseline_values == post_append_values

        # Test new segments work too
        new_test_points = pl.DataFrame({"age": [30, 40], "segment": ["C", "E"]})
        new_result = new_test_points.with_columns(
            [
                gs.assumption_lookup("segment", "age", table_name="perf_test").alias(
                    "rate"
                )
            ]
        )
        assert len(new_result) == 2
        assert not new_result["rate"].is_null().any()

    def test_sequential_append_performance(self):
        """Test performance of sequential append operations."""
        # Load base table
        base_data = pl.DataFrame({"factor": [1, 2, 3], "rate": [0.01, 0.02, 0.03]})
        gs.load_assumptions("sequential_perf", base_data, additional_keys={"batch": 0})

        # Perform many sequential appends
        for i in range(10):  # 10 sequential appends
            append_data = pl.DataFrame(
                {
                    "factor": [1, 2, 3],
                    "rate": [0.01 + i * 0.001, 0.02 + i * 0.001, 0.03 + i * 0.001],
                }
            )
            gs.append_assumptions(
                "sequential_perf", append_data, additional_keys={"batch": i + 1}
            )

        # Test that all batches are accessible efficiently
        for batch_id in [0, 5, 10]:
            test_point = pl.DataFrame({"batch": [batch_id], "factor": [2]})
            result = test_point.with_columns(
                [
                    gs.assumption_lookup(
                        "batch", "factor", table_name="sequential_perf"
                    ).alias("rate")
                ]
            )
            expected_rate = 0.02 + batch_id * 0.001
            actual_rate = result["rate"][0]
            assert abs(actual_rate - expected_rate) < 0.0001


class TestRealWorldUsagePatterns:
    """Test real-world usage patterns and complex scenarios."""

    def test_actuarial_model_integration(self):
        """Test integration with realistic actuarial model structure."""
        # Setup multi-dimensional mortality assumption (realistic scenario)
        mortality_segments = [
            {"sex": "M", "smoking": "SM", "table": "2017-CSO-MSM"},
            {"sex": "F", "smoking": "SM", "table": "2017-CSO-FSM"},
            {"sex": "M", "smoking": "NS", "table": "2017-CSO-MNS"},
            {"sex": "F", "smoking": "NS", "table": "2017-CSO-FNS"},
        ]

        # Load first segment
        first_segment = mortality_segments[0]
        mortality_data = pl.DataFrame(
            {
                "issue_age": [35, 40, 45, 50, 55, 60],
                "year": [1, 1, 1, 1, 1, 1],
                "qx": [0.00095, 0.00123, 0.00168, 0.00234, 0.00342, 0.00521],
            }
        )

        gs.load_assumptions(
            "mortality_2017_cso",
            mortality_data,
            id=["sex", "smoking", "issue_age", "year"],
            additional_keys={
                "sex": first_segment["sex"],
                "smoking": first_segment["smoking"],
            },
            value="qx",
        )

        # Append remaining segments
        for segment in mortality_segments[1:]:
            # Simulate different mortality by sex/smoking
            mortality_factor = {
                ("M", "SM"): 1.2,
                ("F", "SM"): 0.8,
                ("M", "NS"): 0.7,
                ("F", "NS"): 0.5,
            }
            factor = mortality_factor[(segment["sex"], segment["smoking"])]

            segment_data = pl.DataFrame(
                {
                    "issue_age": [35, 40, 45, 50, 55, 60],
                    "year": [1, 1, 1, 1, 1, 1],
                    "qx": [
                        rate * factor
                        for rate in [
                            0.00095,
                            0.00123,
                            0.00168,
                            0.00234,
                            0.00342,
                            0.00521,
                        ]
                    ],
                }
            )

            gs.append_assumptions(
                "mortality_2017_cso",
                segment_data,
                additional_keys={"sex": segment["sex"], "smoking": segment["smoking"]},
            )

        # Create realistic model points (like model-points.csv)
        model_points = pl.DataFrame(
            {
                "policy_number": [1, 2, 3, 4, 5, 6],
                "issue_age": [35, 40, 45, 50, 55, 60],
                "sex": ["M", "F", "M", "F", "M", "F"],
                "smoking_status": ["SM", "SM", "NS", "NS", "SM", "NS"],
                "year_lookup": [1, 1, 1, 1, 1, 1],
            }
        )

        # Perform realistic actuarial lookup
        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "sex",
                    "smoking_status",
                    "issue_age",
                    "year_lookup",
                    table_name="mortality_2017_cso",
                ).alias("base_mortality_rate")
            ]
        )

        # Validate realistic results
        assert "base_mortality_rate" in result.columns
        assert len(result) == 6
        assert not result["base_mortality_rate"].is_null().any()

        # Check that rates vary appropriately by sex/smoking
        rates = result["base_mortality_rate"].to_list()
        # Males should generally have higher rates than females for same age/smoking
        # Smokers should have higher rates than non-smokers
        assert all(rate > 0 for rate in rates)
        assert all(rate < 0.01 for rate in rates)  # Reasonable mortality range

    def test_file_based_workflow(self):
        """Test workflow with file-based data sources."""
        # Create temporary CSV files simulating real assumption files
        csv_files = []

        try:
            # Create base mortality file
            base_csv = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            )
            base_csv.write("age,duration,qx\n30,1,0.001\n31,1,0.0011\n32,1,0.0012\n")
            base_csv.close()
            csv_files.append(base_csv.name)

            # Load from file
            gs.load_assumptions(
                "file_based_table",
                base_csv.name,
                id=["product", "age", "duration"],
                additional_keys={"product": "Term_Life"},
                value="qx",
            )

            # Create append file
            append_csv = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            )
            append_csv.write("age,duration,qx\n30,1,0.0008\n31,1,0.0009\n32,1,0.0010\n")
            append_csv.close()
            csv_files.append(append_csv.name)

            # Append from file
            gs.append_assumptions(
                "file_based_table",
                append_csv.name,
                additional_keys={"product": "Whole_Life"},
            )

            # Test lookups work
            model_points = pl.DataFrame(
                {
                    "product": ["Term_Life", "Whole_Life", "Term_Life"],
                    "age": [30, 31, 32],
                    "duration": [1, 1, 1],
                }
            )

            result = model_points.with_columns(
                [
                    gs.assumption_lookup(
                        "product", "age", "duration", table_name="file_based_table"
                    ).alias("mortality_rate")
                ]
            )

            assert "mortality_rate" in result.columns
            assert len(result) == 3

            # Check expected values
            rates = result["mortality_rate"].to_list()
            assert rates[0] == 0.001  # Term_Life, age 30
            assert rates[1] == 0.0009  # Whole_Life, age 31
            assert rates[2] == 0.0012  # Term_Life, age 32

        finally:
            # Clean up temporary files
            for csv_file in csv_files:
                Path(csv_file).unlink(missing_ok=True)

    def test_my_model_model_pattern(self):
        """Test the pattern used in the My Model model for mortality setup."""
        # Replicate the pattern from model_calculation.py where multiple
        # mortality tables are loaded separately and then used with complex logic

        # Current pattern in My Model (multiple separate tables)
        mortality_tables = {
            "mortality_vbt_fsm": {"sex": "F", "smoking": "SM"},
            "mortality_vbt_msm": {"sex": "M", "smoking": "SM"},
            "mortality_vbt_fns": {"sex": "F", "smoking": "NS"},
            "mortality_vbt_mns": {"sex": "M", "smoking": "NS"},
        }

        # New consolidated pattern using append
        base_mortality_data = pl.DataFrame(
            {
                "issue_age": [35, 40, 45, 50],
                "year_lookup": ["1", "1", "1", "1"],
                "qx": [0.00074, 0.00098, 0.00142, 0.00218],
            }
        )

        # Load first table with additional keys
        first_key = list(mortality_tables.keys())[0]
        first_attrs = mortality_tables[first_key]

        gs.load_assumptions(
            "mortality_vbt_consolidated",
            base_mortality_data,
            additional_keys=first_attrs,
            lookup_keys=["sex", "smoking", "issue_age", "year_lookup"],
            value="qx",
        )

        # Append remaining tables
        for table_name, attributes in list(mortality_tables.items())[1:]:
            # Simulate slightly different mortality by segment
            factor = 1.0 + (hash(table_name) % 10) * 0.1  # Deterministic variation
            segment_data = pl.DataFrame(
                {
                    "issue_age": [35, 40, 45, 50],
                    "year_lookup": ["1", "1", "1", "1"],
                    "qx": [
                        rate * factor for rate in [0.00074, 0.00098, 0.00142, 0.00218]
                    ],
                }
            )

            gs.append_assumptions(
                "mortality_vbt_consolidated", segment_data, additional_keys=attributes
            )

        # Test the lookup that would replace complex table name logic
        model_points = pl.DataFrame(
            {
                "Policyholder sex": ["F", "M", "F", "M"],
                "Policyholder smoking status": ["SM", "SM", "NS", "NS"],
                "issue_age": [35, 40, 45, 50],
                "year_lookup": ["1", "1", "1", "1"],
            }
        )

        # Clean lookup instead of: mortality_table = mortality_base + sex + smoking
        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "Policyholder sex",
                    "Policyholder smoking status",
                    "issue_age",
                    "year_lookup",
                    table_name="mortality_vbt_consolidated",
                ).alias("CSO table")
            ]
        )

        assert "CSO table" in result.columns
        assert len(result) == 4
        assert not result["CSO table"].is_null().any()


class TestBackwardCompatibility:
    """Test that existing code continues to work unchanged."""

    def test_existing_load_assumptions_unchanged(self):
        """Test that existing load_assumptions patterns still work."""
        # Old pattern without additional_keys
        data = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        result = gs.load_assumptions("old_pattern", data, value="rate")

        assert "age" in result.columns
        assert "rate" in result.columns
        assert len(result) == 2

    def test_existing_lookup_patterns_unchanged(self):
        """Test that existing lookup patterns still work."""
        # Load table old way
        data = pl.DataFrame({"age": [30, 31, 32], "qx": [0.001, 0.002, 0.003]})
        gs.load_assumptions("backward_compat", data, value="qx")

        # Old lookup pattern
        model_points = pl.DataFrame({"age": [30, 31, 32]})
        result = model_points.with_columns(
            [
                gs.assumption_lookup("age", table_name="backward_compat").alias(
                    "mortality"
                )
            ]
        )

        assert "mortality" in result.columns
        assert len(result) == 3
        expected_rates = [0.001, 0.002, 0.003]
        actual_rates = result["mortality"].to_list()
        assert actual_rates == expected_rates

    def test_no_regressions_in_performance(self):
        """Test that performance hasn't regressed for existing patterns."""
        # This is a basic smoke test - full performance testing would require benchmarks
        data = pl.DataFrame(
            {"age": list(range(20, 100)), "qx": [0.001 + i * 0.0001 for i in range(80)]}
        )

        # Should work quickly even with larger datasets
        gs.load_assumptions("performance_test", data, value="qx")

        # Large lookup should work
        large_model_points = pl.DataFrame(
            {
                "age": list(range(20, 100)) * 10  # 800 lookups
            }
        )

        result = large_model_points.with_columns(
            [gs.assumption_lookup("age", table_name="performance_test").alias("rate")]
        )

        assert len(result) == 800
        assert not result["rate"].is_null().any()

    def test_wide_table_patterns_still_work(self):
        """Test that existing wide table patterns continue to work."""
        # Old wide table pattern
        wide_data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "male": [0.001, 0.002, 0.003],
                "female": [0.0008, 0.0016, 0.0024],
            }
        )

        gs.load_assumptions("wide_backward_compat", wide_data)

        # Test lookups work
        model_points = pl.DataFrame(
            {"age": [30, 31, 32], "variable": ["male", "female", "male"]}
        )

        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "age", "variable", table_name="wide_backward_compat"
                ).alias("rate")
            ]
        )

        assert "rate" in result.columns
        assert len(result) == 3
        rates = result["rate"].to_list()
        assert rates[0] == 0.001  # age 30, male
        assert rates[1] == 0.0016  # age 31, female
        assert rates[2] == 0.002  # age 32, male


class TestEdgeCasesAndRobustness:
    """Test edge cases and system robustness."""

    def test_empty_additional_keys_handling(self):
        """Test handling of empty additional_keys scenarios."""
        # Load with empty additional_keys
        data = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        gs.load_assumptions("empty_keys", data, additional_keys={})

        # Should not be able to append with non-empty additional_keys
        append_data = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        with pytest.raises(ValueError, match="Additional keys must match"):
            gs.append_assumptions(
                "empty_keys", append_data, additional_keys={"product": "A"}
            )

        # But should be able to append with no additional_keys (simple extension)
        append_data2 = pl.DataFrame({"age": [34, 35], "rate": [0.005, 0.006]})
        result = gs.append_assumptions("empty_keys", append_data2)
        assert len(result) == 2

    def test_complex_additional_key_values(self):
        """Test with complex additional key values."""
        data = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        # Test with various value types
        complex_keys = {
            "text": "Multi-Word Product Name",
            "number": 12345,
            "float": 3.14159,
            "boolean": True,
            "with_special": "Rate@2024-Q1",
        }

        gs.load_assumptions("complex_keys", data, additional_keys=complex_keys)

        # Append with different values
        append_data = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        append_keys = {
            "text": "Another Product Name",
            "number": 67890,
            "float": 2.71828,
            "boolean": False,
            "with_special": "Rate@2024-Q2",
        }

        gs.append_assumptions("complex_keys", append_data, additional_keys=append_keys)

        # Test lookup works
        model_points = pl.DataFrame(
            {
                "text": ["Multi-Word Product Name", "Another Product Name"],
                "number": [12345, 67890],
                "float": [3.14159, 2.71828],
                "boolean": [True, False],
                "with_special": ["Rate@2024-Q1", "Rate@2024-Q2"],
                "age": [30, 32],
            }
        )

        result = model_points.with_columns(
            [
                gs.assumption_lookup(
                    "text",
                    "number",
                    "float",
                    "boolean",
                    "with_special",
                    "age",
                    table_name="complex_keys",
                ).alias("rate")
            ]
        )

        assert "rate" in result.columns
        assert len(result) == 2
        rates = result["rate"].to_list()
        assert rates[0] == 0.001  # First record
        assert rates[1] == 0.003  # Second record

    def test_sequential_operations_robustness(self):
        """Test robustness of sequential operations."""
        # Multiple load and append operations
        data1 = pl.DataFrame({"age": [30], "rate": [0.001]})
        gs.load_assumptions("sequential", data1, additional_keys={"batch": 1})

        # Multiple appends
        for i in range(2, 6):  # batches 2-5
            data = pl.DataFrame({"age": [30], "rate": [0.001 * i]})
            gs.append_assumptions("sequential", data, additional_keys={"batch": i})

        # Test all batches are accessible
        for batch in range(1, 6):
            model_point = pl.DataFrame({"batch": [batch], "age": [30]})
            result = model_point.with_columns(
                [
                    gs.assumption_lookup("batch", "age", table_name="sequential").alias(
                        "rate"
                    )
                ]
            )
            expected_rate = 0.001 * batch
            actual_rate = result["rate"][0]
            assert actual_rate == expected_rate

    def test_large_table_append_robustness(self):
        """Test robustness with large table operations."""
        # Create a reasonably large base table
        large_ages = list(range(18, 99))  # 81 ages
        large_durations = list(range(1, 51))  # 50 durations

        # Create base data (this will be quite large: 81 * 50 = 4,050 rows)
        base_data = []
        for age in large_ages[:20]:  # Limit to keep test reasonable
            for duration in large_durations[:10]:
                base_data.append(
                    {
                        "age": age,
                        "duration": duration,
                        "rate": 0.001 + age * 0.0001 + duration * 0.00001,
                    }
                )

        base_df = pl.DataFrame(base_data)
        gs.load_assumptions(
            "large_robust",
            base_df,
            id=["segment", "age", "duration"],
            additional_keys={"segment": "base"},
        )

        # Append additional segments
        for segment_id in range(3):
            append_data = []
            for age in large_ages[:20]:
                for duration in large_durations[:10]:
                    append_data.append(
                        {
                            "age": age,
                            "duration": duration,
                            "rate": 0.001
                            + age * 0.0001
                            + duration * 0.00001
                            + segment_id * 0.0001,
                        }
                    )

            append_df = pl.DataFrame(append_data)
            gs.append_assumptions(
                "large_robust",
                append_df,
                additional_keys={"segment": f"seg_{segment_id}"},
            )

        # Test random lookups work
        test_points = pl.DataFrame(
            {
                "segment": ["base", "seg_0", "seg_1", "seg_2"],
                "age": [25, 30, 35, 40],
                "duration": [5, 10, 15, 20],
            }
        )

        result = test_points.with_columns(
            [
                gs.assumption_lookup(
                    "segment", "age", "duration", table_name="large_robust"
                ).alias("rate")
            ]
        )

        assert len(result) == 4
        assert not result["rate"].is_null().any()

        # Test specific values are correct
        rates = result["rate"].to_list()
        # Base segment, age 25, duration 5
        expected_base = 0.001 + 25 * 0.0001 + 5 * 0.00001
        assert abs(rates[0] - expected_base) < 0.000001


class TestAppendFunctionality:
    """Test the core append functionality works correctly."""

    def test_append_to_existing_table_succeeds(self):
        """Test that appending data to an existing table works."""
        # Load initial data
        initial_data = pl.DataFrame({"age": [30, 31, 32], "qx": [0.001, 0.002, 0.003]})
        result = gs.load_assumptions("mortality", initial_data, value="qx")
        assert len(result) == 3

        # Append additional data (simple table extension)
        append_data = pl.DataFrame({"age": [33, 34, 35], "qx": [0.004, 0.005, 0.006]})
        result = gs.append_assumptions(
            "mortality",
            append_data,
            value="qx",
        )
        assert len(result) == 3  # Returns just the appended data

        # Check registry has the table
        registry = gs._internal.PyAssumptionTableRegistry()
        assert registry.table_exists("mortality")

    def test_append_with_additional_keys_structure(self):
        """Test appending with a proper additional_keys workflow."""
        # Load initial data with additional_keys
        initial_data = pl.DataFrame({"age": [30, 31, 32], "qx": [0.001, 0.002, 0.003]})
        result = gs.load_assumptions(
            "mortality_versioned",
            initial_data,
            value="qx",
            additional_keys={"data_source": "base_table"},
        )

        # Append additional data with matching additional_keys structure
        append_data = pl.DataFrame({"age": [33, 34, 35], "qx": [0.004, 0.005, 0.006]})
        result = gs.append_assumptions(
            "mortality_versioned",
            append_data,
            additional_keys={"data_source": "extended_ages"},
            value="qx",
        )

        # Check registry has the table
        registry = gs._internal.PyAssumptionTableRegistry()
        assert registry.table_exists("mortality_versioned")

    def test_append_multikey_table(self):
        """Test appending to a multi-key table."""
        # Load initial data with additional_keys structure
        initial_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["M", "M"],
                "age": [30, 30],
                "qx": [0.001, 0.0012],
            }
        )
        result = gs.load_assumptions(
            "multi_mortality",
            initial_data,
            id=["product", "sex", "age"],
            additional_keys={"data_source": "male_rates"},
            value="qx",
        )
        assert len(result) == 2

        # Append additional data
        append_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["F", "F"],
                "age": [30, 30],
                "qx": [0.0008, 0.001],
            }
        )
        result = gs.append_assumptions(
            "multi_mortality",
            append_data,
            additional_keys={"data_source": "female_rates"},
            id=["product", "sex", "age"],
            value="qx",
        )
        assert len(result) == 2

    def test_append_wide_table(self):
        """Test appending to a wide table with value_vars."""
        # Load initial wide data with additional_keys structure
        initial_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["M", "M"],
                "q30": [0.001, 0.0012],
                "q31": [0.0015, 0.0018],
                "q32": [0.002, 0.0024],
            }
        )
        result = gs.load_assumptions(
            "wide_mortality",
            initial_data,
            id=["product", "sex"],
            value_vars=["q30", "q31", "q32"],
            additional_keys={"data_source": "male_rates"},
            value="qx",
        )
        assert len(result) == 6  # 2 products * 3 ages

        # Append additional wide data
        append_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["F", "F"],
                "q30": [0.0008, 0.001],
                "q31": [0.0012, 0.0015],
                "q32": [0.0016, 0.002],
            }
        )
        result = gs.append_assumptions(
            "wide_mortality",
            append_data,
            additional_keys={"data_source": "female_rates"},
            id=["product", "sex"],
            value_vars=["q30", "q31", "q32"],
            value="qx",
        )
        assert len(result) == 6  # 2 products * 3 ages


class TestAppendValidation:
    """Test validation and error handling in append operations."""

    def test_append_to_nonexistent_table_fails(self):
        """Test that appending to a non-existent table fails."""
        append_data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})

        with pytest.raises(Exception):  # Should fail - table doesn't exist
            gs.append_assumptions(
                "nonexistent",
                append_data,
                additional_keys={"source": "test"},
                value="qx",
            )

    def test_append_without_additional_keys_succeeds(self):
        """Test that append_assumptions works without additional_keys (simple extension)."""
        # Load initial data first
        initial_data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})
        gs.load_assumptions("test_table", initial_data, value="qx")

        # Append without additional_keys - should work (simple table extension)
        append_data = pl.DataFrame({"age": [32, 33], "qx": [0.003, 0.004]})

        result = gs.append_assumptions("test_table", append_data, value="qx")
        assert len(result) == 2  # Returns just the appended data

    def test_append_schema_mismatch_validation(self):
        """Test that schema mismatches are caught during append."""
        # Load initial data
        initial_data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})
        gs.load_assumptions("schema_test", initial_data, value="qx")

        # Try to append data with different schema
        append_data = pl.DataFrame(
            {
                "age": [32, 33],
                "product": ["Term", "WL"],  # Extra column
                "qx": [0.003, 0.004],
            }
        )

        # This should raise an exception for additional_keys structure mismatch
        # (trying to add additional_keys to a table that was loaded without them)
        with pytest.raises(ValueError, match="Additional keys must match"):
            gs.append_assumptions(
                "schema_test",
                append_data,
                additional_keys={"source": "different_schema"},
                value="qx",
            )


class TestAppendWithLookupKeys:
    """Test append operations with custom lookup keys."""

    def test_append_with_matching_lookup_keys(self):
        """Test appending data with matching lookup_keys configuration."""
        # Load initial data with custom lookup keys
        initial_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["M", "M"],
                "age": [30, 30],
                "qx": [0.001, 0.0012],
            }
        )
        result = gs.load_assumptions(
            "custom_lookup",
            initial_data,
            id=["product", "sex", "age"],
            lookup_keys=["sex", "age"],  # Custom order
            value="qx",
        )
        assert len(result) == 2

        # Append with same lookup_keys
        append_data = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "sex": ["F", "F"],
                "age": [30, 30],
                "qx": [0.0008, 0.001],
            }
        )
        result = gs.append_assumptions(
            "custom_lookup",
            append_data,
            additional_keys={"data_source": "female_rates"},
            id=["product", "sex", "age"],
            lookup_keys=["sex", "age"],
            value="qx",
        )
        assert len(result) == 2


class TestAppendPerformance:
    """Test performance characteristics of append operations."""

    def test_append_large_dataset(self):
        """Test appending a reasonably large dataset."""
        # Load initial data with additional_keys structure
        ages = list(range(18, 66))  # 48 ages
        initial_data = pl.DataFrame(
            {"age": ages, "qx": [0.001 + (age - 18) * 0.0001 for age in ages]}
        )
        result = gs.load_assumptions(
            "large_table",
            initial_data,
            additional_keys={"data_source": "base_ages"},
            value="qx",
        )
        assert len(result) == 48

        # Append additional data
        append_ages = list(range(66, 101))  # 35 more ages
        append_data = pl.DataFrame(
            {
                "age": append_ages,
                "qx": [0.001 + (age - 18) * 0.0001 for age in append_ages],
            }
        )
        result = gs.append_assumptions(
            "large_table",
            append_data,
            additional_keys={"data_source": "extended_ages"},
            value="qx",
        )
        assert len(result) == 35

    def test_multiple_append_operations(self):
        """Test multiple sequential append operations."""
        # Load initial data with additional_keys structure
        initial_data = pl.DataFrame({"age": [30], "qx": [0.001]})
        gs.load_assumptions(
            "multi_append", initial_data, additional_keys={"batch": 0}, value="qx"
        )

        # Perform multiple appends
        for i in range(1, 6):  # Ages 31-35
            append_data = pl.DataFrame({"age": [30 + i], "qx": [0.001 + i * 0.0005]})
            result = gs.append_assumptions(
                "multi_append", append_data, additional_keys={"batch": i}, value="qx"
            )
            assert len(result) == 1


class TestAppendWithOverflow:
    """Test append operations with overflow handling."""

    def test_append_wide_table_with_overflow(self):
        """Test appending to wide table with overflow columns."""
        # Load initial data with overflow and additional_keys structure
        initial_data = pl.DataFrame(
            {
                "product": ["Term"],
                "q30": [0.001],
                "q31": [0.002],
                "q32": [0.003],
                "q33_plus": [0.004],  # Overflow column
            }
        )
        result = gs.load_assumptions(
            "overflow_table",
            initial_data,
            id=["product"],
            value_vars=["q30", "q31", "q32"],
            overflow="auto",  # Should detect q33_plus
            additional_keys={"product_type": "term_life"},
            value="qx",
        )
        assert len(result) >= 3

        # Append more data with overflow
        append_data = pl.DataFrame(
            {
                "product": ["WL"],
                "q30": [0.0012],
                "q31": [0.0024],
                "q32": [0.0036],
                "q33_plus": [0.0048],
            }
        )
        result = gs.append_assumptions(
            "overflow_table",
            append_data,
            additional_keys={"product_type": "whole_life"},
            id=["product"],
            value_vars=["q30", "q31", "q32"],
            overflow="auto",
            value="qx",
        )
        assert len(result) >= 3


class TestAppendErrorScenarios:
    """Test comprehensive error scenarios and edge cases."""

    def test_append_empty_dataframe(self):
        """Test appending an empty DataFrame."""
        # Load initial data with additional_keys to match append structure
        initial_data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})
        gs.load_assumptions(
            "empty_append", initial_data, additional_keys={"source": "base"}, value="qx"
        )

        # Try to append empty DataFrame - should raise an error for empty data
        empty_data = pl.DataFrame({"age": [], "qx": []})
        with pytest.raises(ValueError, match="DataFrame is empty"):
            gs.append_assumptions(
                "empty_append",
                empty_data,
                additional_keys={"source": "empty"},
                value="qx",
            )

    def test_append_duplicate_keys(self):
        """Test appending data with duplicate keys from existing data."""
        # Load initial data with additional_keys to match append structure
        initial_data = pl.DataFrame({"age": [30, 31, 32], "qx": [0.001, 0.002, 0.003]})
        gs.load_assumptions(
            "duplicate_test",
            initial_data,
            additional_keys={"source": "base"},
            value="qx",
        )

        # Append data with overlapping keys
        append_data = pl.DataFrame(
            {
                "age": [32, 33, 34],  # 32 overlaps
                "qx": [0.0035, 0.004, 0.005],  # Different value for age 32
            }
        )

        # This should work (append operation allows duplicates)
        result = gs.append_assumptions(
            "duplicate_test",
            append_data,
            additional_keys={"source": "overlapping"},
            value="qx",
        )
        assert len(result) == 3


class TestAppendIntegrationWorkflows:
    """Test complete end-to-end workflows with append."""

    def test_load_append_workflow(self):
        """Test complete load -> append workflow."""
        # Step 1: Load base mortality table with additional_keys structure
        base_mortality = pl.DataFrame(
            {"age": [30, 31, 32], "base_qx": [0.001, 0.002, 0.003]}
        )
        gs.load_assumptions(
            "base_mortality",
            base_mortality,
            additional_keys={"age_range": "base"},
            value="base_qx",
        )

        # Step 2: Append additional age ranges
        extended_mortality = pl.DataFrame(
            {"age": [33, 34, 35], "base_qx": [0.004, 0.005, 0.006]}
        )
        gs.append_assumptions(
            "base_mortality",
            extended_mortality,
            additional_keys={"age_range": "extended"},
            value="base_qx",
        )

        # Step 3: Verify table exists and is functional
        registry = gs._internal.PyAssumptionTableRegistry()
        assert registry.table_exists("base_mortality")

        # Get metadata if available
        metadata = registry.get_table_metadata("base_mortality")
        if metadata:
            key_count, key_names = metadata
            assert key_count >= 1
            assert "age" in key_names

    def test_multi_table_append_workflow(self):
        """Test workflow with multiple tables and cross-references."""
        # Load mortality table with additional_keys structure
        mortality_data = pl.DataFrame(
            {"age": [30, 31, 32], "qx": [0.001, 0.002, 0.003]}
        )
        gs.load_assumptions(
            "mortality", mortality_data, additional_keys={"source": "base"}, value="qx"
        )

        # Load lapse table with additional_keys structure
        lapse_data = pl.DataFrame(
            {"duration": [1, 2, 3], "lapse_rate": [0.05, 0.03, 0.02]}
        )
        gs.load_assumptions(
            "lapse",
            lapse_data,
            id="duration",
            additional_keys={"source": "base"},
            value="lapse_rate",
        )

        # Append to both tables
        gs.append_assumptions(
            "mortality",
            pl.DataFrame({"age": [33, 34], "qx": [0.004, 0.005]}),
            additional_keys={"source": "extended"},
            value="qx",
        )

        gs.append_assumptions(
            "lapse",
            pl.DataFrame({"duration": [4, 5], "lapse_rate": [0.015, 0.01]}),
            additional_keys={"source": "extended"},
            id="duration",
            value="lapse_rate",
        )

        # Verify both tables exist
        registry = gs._internal.PyAssumptionTableRegistry()
        assert registry.table_exists("mortality")
        assert registry.table_exists("lapse")


class TestAppendConfigurationPersistence:
    """Test that append operations preserve and use stored configurations."""

    def test_append_uses_stored_config(self):
        """Test that append automatically uses stored table configuration."""
        # Load with specific configuration including additional_keys structure
        data = pl.DataFrame(
            {"product": ["Term", "WL"], "age": [30, 30], "qx": [0.001, 0.0012]}
        )
        gs.load_assumptions(
            "config_persist",
            data,
            id=["product", "age"],
            additional_keys={"age_group": "30"},
            value="qx",
        )

        # Append without specifying id (should use stored config)
        append_data = pl.DataFrame(
            {"product": ["Term", "WL"], "age": [31, 31], "qx": [0.002, 0.0024]}
        )
        result = gs.append_assumptions(
            "config_persist",
            append_data,
            additional_keys={"age_group": "31"},
            # Note: not specifying id, should use stored config
            value="qx",
        )
        assert len(result) == 2

    def test_append_config_override(self):
        """Test that append can override stored configuration when needed."""
        # Load with one configuration including additional_keys structure
        data = pl.DataFrame({"age": [30, 31], "qx": [0.001, 0.002]})
        gs.load_assumptions(
            "config_override", data, additional_keys={"has_product": False}, value="qx"
        )

        # Append with explicit different configuration
        append_data = pl.DataFrame(
            {
                "age": [32, 33],
                "product": ["Term", "Term"],  # Adding a dimension
                "qx": [0.003, 0.004],
            }
        )

        # This should work with explicit id specification
        result = gs.append_assumptions(
            "config_override",
            append_data,
            additional_keys={"has_product": True},
            id=["age", "product"],  # Override stored config
            value="qx",
        )
        assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__])
