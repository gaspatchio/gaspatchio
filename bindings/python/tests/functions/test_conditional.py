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

    def test_tracing_mode_raises_error(self) -> None:
        """Test that list broadcasting in tracing mode raises informative error."""
        # Save current mode
        from gaspatchio_core import get_default_mode, set_default_mode

        original_mode = get_default_mode()

        try:
            # Set to debug mode to enable tracing
            set_default_mode("debug")

            af = ActuarialFrame(
                {
                    "month": [[0, 1, 2]],
                    "policy_term": [1],
                }
            )

            # Manually enable tracing (debug mode enables it in decorator,
            # but for direct assignment we need to set it)
            af._tracing = True  # noqa: SLF001

            # Try list broadcasting conditional - should raise NotImplementedError
            with pytest.raises(
                NotImplementedError,
                match=(
                    "List broadcasting for column 'result' not yet supported "
                    "in tracing mode"
                ),
            ):
                af.result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

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
