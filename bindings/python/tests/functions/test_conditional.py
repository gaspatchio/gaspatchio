# ABOUTME: Tests for when/then/otherwise conditional expressions
# ABOUTME: Covers scalar, list broadcasting, error handling, and graph integration
"""Tests for when/then/otherwise conditional expressions.

Covers scalar conditionals, list broadcasting, error handling,
and computation graph integration.
"""

from gaspatchio_core import ActuarialFrame, when

# Test constants
RETIREMENT_AGE = 65


class TestWhenBasics:
    """Tests for basic when/then/otherwise functionality."""

    def test_simple_scalar_conditional(self) -> None:
        """Test basic scalar conditional matching Excel IF()."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        af.rate = when(af.age > RETIREMENT_AGE).then(0.05).otherwise(0.02)

        result = af.collect()
        assert result["rate"].to_list() == [0.02, 0.02, 0.05]  # noqa: S101
