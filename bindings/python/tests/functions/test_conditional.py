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
