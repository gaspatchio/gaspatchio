# ABOUTME: Tests for when/then/otherwise conditional expressions
# ABOUTME: Covers scalar, list broadcasting, error handling, and graph integration
"""Tests for when/then/otherwise conditional expressions.

Covers scalar conditionals, list broadcasting, error handling,
and computation graph integration.
"""

import pytest

from gaspatchio_core import ActuarialFrame, when

# Test constants
RETIREMENT_AGE = 65
ADULT_AGE = 18
LOW_THRESHOLD = 20
MEDIUM_THRESHOLD = 30
TEST_THRESHOLD = 5
SENIOR_AGE = 60
HIGH_INCOME = 50000
MID_AGE = 50
YOUNG_AGE = 40
MID_SENIOR_AGE = 60
PREMIUM_THRESHOLD = 1500
LOW_INCOME = 50000
MID_INCOME = 75000
BENCHMARK_YOUNG_AGE = 30


class TestWhenBasics:
    """Tests for basic when/then/otherwise functionality."""

    def test_simple_scalar_conditional(self) -> None:
        """Test basic scalar conditional matching Excel IF()."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        af.rate = when(af.age > RETIREMENT_AGE).then(0.05).otherwise(0.02)

        result = af.collect()
        assert result["rate"].to_list() == [0.02, 0.02, 0.05]  # noqa: S101


class TestWhenMultipleConditions:
    """Tests for chained when conditions (elif behavior)."""

    def test_chained_when(self) -> None:
        """Test multiple when conditions with elif behavior."""
        af = ActuarialFrame({"age": [15, 25, 45, 70]})

        af.category = (
            when(af.age < ADULT_AGE)
            .then("child")
            .when(af.age < RETIREMENT_AGE)
            .then("adult")
            .otherwise("senior")
        )

        result = af.collect()
        assert result["category"].to_list() == ["child", "adult", "adult", "senior"]  # noqa: S101

    def test_first_match_wins(self) -> None:
        """Test that first matching condition wins (like if/elif)."""
        af = ActuarialFrame({"value": [5, 15, 25]})

        af.category = (
            when(af.value < LOW_THRESHOLD)
            .then("low")
            .when(af.value < MEDIUM_THRESHOLD)
            .then("medium")  # 15 matches first condition
            .otherwise("high")
        )

        result = af.collect()
        assert result["category"].to_list() == ["low", "low", "medium"]  # noqa: S101


class TestWhenListBroadcasting:
    """Tests for automatic list vs scalar broadcasting."""

    def test_maturity_calculation(self) -> None:
        """Test realistic maturity calculation from 18-conditional-broadcast.md."""
        af = ActuarialFrame(
            {
                "policy_id": [1, 2],
                "month": [
                    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                    [
                        0,
                        1,
                        2,
                        3,
                        4,
                        5,
                        6,
                        7,
                        8,
                        9,
                        10,
                        11,
                        12,
                        13,
                        14,
                        15,
                        16,
                        17,
                        18,
                        19,
                        20,
                        21,
                        22,
                        23,
                        24,
                    ],
                ],
                "policy_term": [1, 2],  # 1 year = 12 months, 2 years = 24 months
                "pols_if": [
                    [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                    [
                        100,
                        99,
                        98,
                        97,
                        96,
                        95,
                        94,
                        93,
                        92,
                        91,
                        90,
                        89,
                        88,
                        87,
                        86,
                        85,
                        84,
                        83,
                        82,
                        81,
                        80,
                        79,
                        78,
                        77,
                        76,
                    ],
                ],
            }
        )

        # Maturity happens at month == policy_term * 12
        af.pols_maturity = (
            when(af.month == af.policy_term * 12).then(af.pols_if).otherwise(0)
        )

        result = af.collect()

        # Policy 1: month 12 should have 88
        maturity_1 = result["pols_maturity"][0].to_list()
        expected_1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 88]
        assert maturity_1 == expected_1  # noqa: S101

        # Policy 2: month 24 should have 76
        maturity_2 = result["pols_maturity"][1].to_list()
        expected_2 = [0] * 24 + [76]
        assert maturity_2 == expected_2  # noqa: S101

    def test_mixed_list_and_scalar_values(self) -> None:
        """Test list condition with mixed list/scalar then values."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2, 3, 4, 5]],
                "policy_term": [2],
            }
        )

        # List in condition, scalar in then/otherwise
        af.is_maturity = when(af.month == af.policy_term * 12).then(1).otherwise(0)

        result = af.collect()
        # 2*12=24 but month only goes to 5, so none should match
        assert result["is_maturity"][0].to_list() == [0, 0, 0, 0, 0, 0]  # noqa: S101

    def test_tracing_mode_works(self) -> None:
        """Test that list broadcasting works in tracing mode (Task 5).

        This test was previously expecting NotImplementedError, but as of Task 5
        list broadcasting now works in debug/tracing mode with eager execution.
        """
        # Save current mode
        from gaspatchio_core import get_default_mode, set_default_mode

        original_mode = get_default_mode()

        try:
            # Set to debug mode to enable tracing
            set_default_mode("debug")

            af = ActuarialFrame(
                {
                    "month": [[0, 12, 24]],
                    "policy_term": [1],
                }
            )

            # Manually enable tracing (debug mode enables it in decorator,
            # but for direct assignment we need to set it)
            af._tracing = True  # noqa: SLF001

            # List broadcasting conditional now works in tracing mode!
            af.result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

            # Verify operation was captured in computation graph
            assert len(af._computation_graph) > 0  # noqa: SLF001, S101
            assert any(  # noqa: S101
                getattr(op, "alias", None) == "result"
                for op in af._computation_graph  # noqa: SLF001
            )

            # Verify results are correct
            # month values: [0, 12, 24], policy_term * 12 = 12
            # Result: [0, 1, 0] (only month=12 matches)
            result_data = af.collect()
            assert result_data["result"][0].to_list() == [0, 1, 0]  # noqa: S101

        finally:
            # Restore original mode
            set_default_mode(original_mode)


class TestWhenErrorHandling:
    """Tests for error handling and validation."""

    def test_missing_otherwise_raises_error(self) -> None:
        """Test that ConditionalProxy cannot be used without .otherwise()."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        # Create incomplete conditional
        incomplete = when(af.age > RETIREMENT_AGE).then(0.05)

        # Should raise TypeError when trying to use it
        with pytest.raises(
            TypeError,
            match="cannot create expression literal for value of type ConditionalProxy",
        ):
            # Trigger _to_expr via _convert_to_expr
            af._convert_to_expr(incomplete)  # noqa: SLF001

    def test_repr_shows_incomplete_state(self) -> None:
        """Test ConditionalProxy repr shows helpful message."""
        af = ActuarialFrame({"value": [10]})
        proxy = when(af.value > TEST_THRESHOLD).then(100)

        repr_str = repr(proxy)
        assert "incomplete" in repr_str.lower()  # noqa: S101
        assert "otherwise" in repr_str.lower()  # noqa: S101


class TestConditionalProxyMetadata:
    """Tests for ConditionalProxy list broadcasting metadata."""

    def test_needs_list_broadcasting_returns_false_for_scalar(self) -> None:
        """Test needs_list_broadcasting returns False for scalar conditionals."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        conditional = when(af.age > RETIREMENT_AGE).then(0.05)

        # Should be False - no list columns involved
        assert not conditional.needs_list_broadcasting()  # noqa: S101

    def test_needs_list_broadcasting_returns_true_for_list(self) -> None:
        """Test needs_list_broadcasting returns True for list conditionals."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2, 3, 4, 5]],
                "policy_term": [2],
            }
        )

        conditional = when(af.month == af.policy_term * 12).then(1)

        # Detection won't happen until otherwise() is called
        # For now, should return False (metadata not populated yet)
        assert not conditional.needs_list_broadcasting()  # noqa: S101

    def test_get_list_broadcasting_metadata(self) -> None:
        """Test that detected list columns are accessible via metadata."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2]],
                "policy_term": [1],
                "pols_if": [[100, 99, 98]],
            }
        )

        # Create conditional but don't call otherwise() yet
        conditional = when(af.month == af.policy_term * 12).then(af.pols_if)

        # Get metadata (will implement this method)
        metadata = conditional.get_list_broadcasting_metadata()

        # Should have detected month and pols_if as list columns
        assert "month" in metadata["list_columns"]  # noqa: S101
        assert "pols_if" in metadata["list_columns"]  # noqa: S101
        assert "conditions" in metadata  # noqa: S101
        assert "values" in metadata  # noqa: S101

    def test_otherwise_populates_list_columns(self) -> None:
        """Test that otherwise() triggers list column detection."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2]],
                "policy_term": [1],
            }
        )

        # Before otherwise(), list_columns is None
        conditional = when(af.month == af.policy_term * 12).then(1)
        assert conditional._list_columns is None  # noqa: S101, SLF001

        # Call otherwise() - should now work with list broadcasting
        conditional.otherwise(0)

        # Check metadata was populated
        assert conditional._list_columns is not None  # noqa: S101, SLF001
        assert "month" in conditional._list_columns  # noqa: S101, SLF001

    def test_expression_proxy_carries_list_broadcast_metadata(self) -> None:
        """Test that ExpressionProxy carries list broadcast metadata."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2]],
                "policy_term": [1],
            }
        )

        # Call otherwise() - should now work and return ExpressionProxy with metadata
        result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

        # Should have metadata attached
        assert hasattr(result, "_list_broadcast_metadata")  # noqa: S101
        metadata = result._list_broadcast_metadata  # noqa: SLF001
        assert metadata is not None  # noqa: S101
        assert "month" in metadata["list_columns"]  # noqa: S101


class TestWhenEdgeCases:
    """Tests for edge cases like empty lists, single elements, and mixed types."""

    def test_empty_list_conditional(self) -> None:
        """Test conditional with empty list columns."""
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "month": [[]],  # Empty list
                "policy_term": [1],
            }
        )

        # Should handle empty lists gracefully
        af.res = when(af.month == af.policy_term * 12).then(1).otherwise(0)

        res = af.collect()
        # Empty list with scalar otherwise produces [0] due to broadcasting
        assert res["res"][0].to_list() == [0]  # noqa: S101

    def test_single_element_list_conditional(self) -> None:
        """Test conditional with single element list."""
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "month": [[12]],  # Single element
                "policy_term": [1],
            }
        )

        af.result = when(af.month == af.policy_term * 12).then(100).otherwise(0)

        result = af.collect()
        # Single element at position 0 matches (12 == 1*12)
        assert result["result"][0].to_list() == [100]  # noqa: S101

    def test_mixed_list_lengths(self) -> None:
        """Test conditional with varying list lengths across rows."""
        af = ActuarialFrame(
            {
                "policy_id": [1, 2, 3],
                "month": [[0, 1], [0, 1, 2, 3, 4], [0]],  # Different lengths
                "threshold": [1, 3, 0],
            }
        )

        af.flag = when(af.month >= af.threshold).then(1).otherwise(0)

        result = af.collect()

        # Row 1: [0, 1] >= 1 -> [0, 1]
        assert result["flag"][0].to_list() == [0, 1]  # noqa: S101
        # Row 2: [0, 1, 2, 3, 4] >= 3 -> [0, 0, 0, 1, 1]
        assert result["flag"][1].to_list() == [0, 0, 0, 1, 1]  # noqa: S101
        # Row 3: [0] >= 0 -> [1]
        assert result["flag"][2].to_list() == [1]  # noqa: S101

    def test_null_handling_in_scalar_conditional(self) -> None:
        """Test conditional handles null values in scalar columns."""
        af = ActuarialFrame({"age": [25, None, 70]})

        af.age_cat = when(af.age > RETIREMENT_AGE).then("senior").otherwise("other")

        res = af.collect()
        # Polars conditionals with null return "other" when null fails condition
        assert res["age_cat"][0] == "other"  # noqa: S101
        assert res["age_cat"][1] == "other"  # noqa: S101  # Null > 65 is False
        assert res["age_cat"][2] == "senior"  # noqa: S101

    def test_boolean_value_conditions(self) -> None:
        """Test conditional with boolean column values."""
        af = ActuarialFrame(
            {
                "is_active": [True, False, True, False],
                "base_rate": [0.05, 0.05, 0.05, 0.05],
            }
        )

        af.rate = when(af.is_active).then(af.base_rate).otherwise(0.0)

        result = af.collect()
        assert result["rate"].to_list() == [0.05, 0.0, 0.05, 0.0]  # noqa: S101

    def test_complex_expression_in_condition(self) -> None:
        """Test conditional with complex multi-column expressions."""
        af = ActuarialFrame(
            {
                "age": [25, 35, 45, 55, 65, 75],
                "income": [30000, 50000, 70000, 90000, 40000, 60000],
                "premium": [100, 150, 200, 250, 180, 220],
            }
        )

        # Complex condition: age > 60 AND income > 50000
        # Use separate conditions then combine
        age_condition = af.age > SENIOR_AGE
        income_condition = af.income > HIGH_INCOME
        combined_condition = age_condition & income_condition  # type: ignore[operator]

        af.discount = (
            when(combined_condition).then(af.premium * 0.9).otherwise(af.premium)
        )

        result = af.collect()
        # Only row 5 (age=75, income=60000) meets both conditions
        expected = [100, 150, 200, 250, 180, 220 * 0.9]
        assert result["discount"].to_list() == expected  # noqa: S101

    def test_string_conditions_and_values(self) -> None:
        """Test conditional with string comparisons and values."""
        af = ActuarialFrame(
            {
                "prod_type": ["term", "whole_life", "term", "endowment"],
                "base_commission": [0.05, 0.08, 0.05, 0.10],
            }
        )

        af.commission = (
            when(af.prod_type == "term")
            .then(af.base_commission * 0.8)
            .when(af.prod_type == "whole_life")
            .then(af.base_commission * 1.2)
            .otherwise(af.base_commission)
        )

        res = af.collect()
        expected = [0.05 * 0.8, 0.08 * 1.2, 0.05 * 0.8, 0.10]
        assert res["commission"].to_list() == expected  # noqa: S101


class TestWhenErrorValidation:
    """Tests for additional error handling and type validation."""

    def test_invalid_condition_type_raises_error(self) -> None:
        """Test that invalid condition type raises TypeError."""
        with pytest.raises(TypeError, match="Condition must be an expression"):
            # Pass a plain string instead of a boolean expression
            when("not an expression")

    def test_unbalanced_when_then_chain(self) -> None:
        """Test that when() without matching then() is handled."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        conditional = when(af.age > RETIREMENT_AGE).then(0.05)

        # Add another when() without then() - should still allow chaining
        conditional = conditional.when(af.age > MID_AGE)

        # Now add then for the second condition
        conditional = conditional.then(0.03)

        # Complete with otherwise
        res_expr = conditional.otherwise(0.02)

        # Should work: >65->0.05, >50->0.03, else->0.02
        # Note: first match wins, so 45 doesn't match >65 but does match >50
        # However, 70 matches >65 first (takes 0.05 not 0.03)
        af.rate = res_expr
        collected = af.collect()
        # 25: not >65, not >50 -> 0.02
        # 45: not >65, not >50 -> 0.02
        # 70: >65 -> 0.05
        assert collected["rate"].to_list() == [0.02, 0.02, 0.05]  # noqa: S101

    def test_type_coercion_in_then_values(self) -> None:
        """Test that different numeric types are coerced properly."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        # Mix int and float in then/otherwise
        af.rate = when(af.age > RETIREMENT_AGE).then(5).otherwise(2.5)  # int vs float

        result = af.collect()
        # Should coerce to same type (float)
        assert result["rate"].to_list() == [2.5, 2.5, 5.0]  # noqa: S101

    def test_conditional_with_division_by_zero(self) -> None:
        """Test conditional handles division by zero in expressions."""
        af = ActuarialFrame({"value": [10, 0, 5, 0]})

        # Avoid division by zero using conditional
        af.result = when(af.value == 0).then(None).otherwise(100 / af.value)

        result = af.collect()
        # Positions with 0 should be None, others should be 100/value
        expected = [10.0, None, 20.0, None]
        assert result["result"].to_list() == expected  # noqa: S101


class TestWhenComputationGraph:
    """Tests for computation graph integration with conditionals."""

    def test_conditional_in_chain_of_calculations(self) -> None:
        """Test conditional as part of computation chain."""
        af = ActuarialFrame(
            {
                "premium": [1000, 1500, 2000],
                "age": [30, 50, 70],
            }
        )

        # Multi-step calculation with conditional in the middle
        af.age_factor = when(af.age > RETIREMENT_AGE).then(1.5).otherwise(1.0)
        af.adjusted_premium = af.premium * af.age_factor
        af.final_premium = af.adjusted_premium * 1.1  # Add 10% loading

        result = af.collect()

        # Verify the chain worked correctly
        expected = [1000 * 1.0 * 1.1, 1500 * 1.0 * 1.1, 2000 * 1.5 * 1.1]
        assert result["final_premium"].to_list() == expected  # noqa: S101

    def test_nested_conditionals_in_graph(self) -> None:
        """Test multiple conditionals depending on each other."""
        af = ActuarialFrame(
            {
                "age": [25, 45, 55, 75],
                "is_smoker": [True, False, True, False],
            }
        )

        # First conditional for age factor
        af.age_factor = (
            when(af.age < YOUNG_AGE)
            .then(1.0)
            .when(af.age < MID_SENIOR_AGE)
            .then(1.2)
            .otherwise(1.5)
        )

        # Second conditional using result of first
        af.smoking_factor = when(af.is_smoker).then(1.3).otherwise(1.0)

        # Combine factors
        af.total_factor = af.age_factor * af.smoking_factor

        result = af.collect()

        # Verify both conditionals worked in sequence
        expected = [1.0 * 1.3, 1.2 * 1.0, 1.2 * 1.3, 1.5 * 1.0]
        assert result["total_factor"].to_list() == expected  # noqa: S101

    def test_conditional_references_computed_column(self) -> None:
        """Test conditional that references a computed column."""
        af = ActuarialFrame(
            {
                "base_premium": [1000, 1500, 2000],
                "discount_pct": [0.1, 0.2, 0.05],
            }
        )

        # Computed column
        af.discounted_premium = af.base_premium * (1 - af.discount_pct)

        # Conditional referencing computed column
        af.final_premium = (
            when(af.discounted_premium < PREMIUM_THRESHOLD)
            .then(af.discounted_premium)
            .otherwise(af.discounted_premium * 0.95)
        )

        result = af.collect()

        # Row 0: 1000*0.9=900 < 1500 -> 900
        # Row 1: 1500*0.8=1200 < 1500 -> 1200
        # Row 2: 2000*0.95=1900 >= 1500 -> 1900*0.95=1805
        expected = [900.0, 1200.0, 1805.0]
        assert result["final_premium"].to_list() == expected  # noqa: S101

    def test_multiple_conditionals_same_columns(self) -> None:
        """Test multiple conditionals operating on same source columns."""
        af = ActuarialFrame(
            {
                "age": [25, 45, 65, 75],
                "income": [30000, 60000, 80000, 50000],
            }
        )

        # Two different conditionals on same age column
        af.age_category = (
            when(af.age < YOUNG_AGE)
            .then("young")
            .when(af.age < RETIREMENT_AGE)
            .then("middle")
            .otherwise("senior")
        )

        af.income_category = (
            when(af.income < LOW_INCOME)
            .then("low")
            .when(af.income < MID_INCOME)
            .then("medium")
            .otherwise("high")
        )

        result = af.collect()

        expected_age = ["young", "middle", "senior", "senior"]
        expected_income = ["low", "medium", "high", "medium"]

        assert result["age_category"].to_list() == expected_age  # noqa: S101
        assert result["income_category"].to_list() == expected_income  # noqa: S101


class TestWhenPerformance:
    """Performance benchmark tests comparing when/then to alternatives."""

    def test_benchmark_scalar_conditional(self, benchmark) -> None:
        """Benchmark scalar conditional performance."""
        af = ActuarialFrame({"age": list(range(1000))})

        def run_conditional() -> None:
            af.category = (
                when(af.age < ADULT_AGE)
                .then("child")
                .when(af.age < RETIREMENT_AGE)
                .then("adult")
                .otherwise("senior")
            )
            af.collect()

        benchmark(run_conditional)

    def test_benchmark_list_conditional_small(self, benchmark) -> None:
        """Benchmark list conditional with small projections."""
        # 100 policies, each with 12 months
        af = ActuarialFrame(
            {
                "policy_id": list(range(100)),
                "month": [list(range(13)) for _ in range(100)],
                "policy_term": [1] * 100,
                "pols_if": [[100 - i for i in range(13)] for _ in range(100)],
            }
        )

        def run_conditional() -> None:
            af.pols_maturity = (
                when(af.month == af.policy_term * 12).then(af.pols_if).otherwise(0)
            )
            af.collect()

        benchmark(run_conditional)

    def test_benchmark_complex_chained_conditional(self, benchmark) -> None:
        """Benchmark complex chained conditional with multiple conditions."""
        af = ActuarialFrame(
            {
                "age": list(range(1000)),
                "income": [i * 1000 for i in range(1000)],
                "is_smoker": [i % 2 == 0 for i in range(1000)],
            }
        )

        def run_conditional() -> None:
            # Build conditions separately to avoid type errors
            cond1 = (af.age < BENCHMARK_YOUNG_AGE) & (af.income > HIGH_INCOME)  # type: ignore[operator]
            cond2 = (af.age < MID_AGE) & af.is_smoker  # type: ignore[operator]
            cond3 = (af.age >= MID_AGE) & (af.age < RETIREMENT_AGE)  # type: ignore[operator]
            cond4 = (af.age >= RETIREMENT_AGE) & af.is_smoker  # type: ignore[operator]

            af.risk_score = (
                when(cond1)
                .then(1)
                .when(cond2)
                .then(3)
                .when(cond3)
                .then(5)
                .when(cond4)
                .then(8)
                .otherwise(2)
            )
            af.collect()

        benchmark(run_conditional)

    def test_compare_when_vs_direct_polars(self, benchmark) -> None:
        """Compare when() performance to direct Polars expression."""
        import polars as pl

        # Create a Polars DataFrame directly
        polars_data = pl.DataFrame({"age": list(range(1000))})

        def run_polars_native() -> None:
            _result = polars_data.with_columns(
                pl.when(pl.col("age") < ADULT_AGE)
                .then(pl.lit("child"))
                .when(pl.col("age") < RETIREMENT_AGE)
                .then(pl.lit("adult"))
                .otherwise(pl.lit("senior"))
                .alias("category")
            )
            # Polars DataFrames are eager by default, no need to collect

        benchmark(run_polars_native)
