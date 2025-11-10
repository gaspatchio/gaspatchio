# ABOUTME: Tests for when/then/otherwise conditional expressions
# ABOUTME: Covers scalar, list broadcasting, error handling, and graph integration
"""Tests for when/then/otherwise conditional expressions.

Covers scalar conditionals, list broadcasting, error handling,
and computation graph integration.
"""

from gaspatchio_core import ActuarialFrame, when

# Test constants
RETIREMENT_AGE = 65
ADULT_AGE = 18
LOW_THRESHOLD = 20
MEDIUM_THRESHOLD = 30


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
        maturity_1 = result["pols_maturity"][0]
        expected_1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 88]
        assert maturity_1 == expected_1  # noqa: S101

        # Policy 2: month 24 should have 76
        maturity_2 = result["pols_maturity"][1]
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
        assert result["is_maturity"][0] == [0, 0, 0, 0, 0, 0]  # noqa: S101
