# ABOUTME: Tests for list column operations with column operands (GSP-10)
# ABOUTME: Verifies list ** scalar_col and list.clip(col, col) work correctly
"""Tests for list column operations with column bounds/exponents.

These tests verify that list columns can use other columns as operands,
not just scalar literals. This is GSP-10.
"""

import pytest

from gaspatchio_core import ActuarialFrame


class TestListPowWithColumnExponent:
    """Tests for list ** column_exponent operations."""

    def test_list_pow_with_scalar_column_exponent(self) -> None:
        """Test that list ** scalar_column works via operator syntax.

        This is the core use case from GSP-10:
        af.itm ** af.Power where itm is list[f64] and Power is f64
        """
        data = {
            "policy_id": [1, 2],
            # List column: in-the-money ratio per projection period
            "itm": [[2.0, 3.0, 4.0], [5.0, 6.0]],
            # Scalar column: power exponent per policy (from assumption table)
            "power": [2.0, 3.0],
        }
        af = ActuarialFrame(data)

        # This should work: list ** scalar_column
        af.result = af.itm**af.power

        result = af.collect()

        # Verify results
        # Row 1: [2^2, 3^2, 4^2] = [4.0, 9.0, 16.0]
        # Row 2: [5^3, 6^3] = [125.0, 216.0]
        result_list = result["result"].to_list()

        assert len(result_list[0]) == 3
        assert result_list[0][0] == pytest.approx(4.0)
        assert result_list[0][1] == pytest.approx(9.0)
        assert result_list[0][2] == pytest.approx(16.0)

        assert len(result_list[1]) == 2
        assert result_list[1][0] == pytest.approx(125.0)
        assert result_list[1][1] == pytest.approx(216.0)

    def test_list_pow_with_expression_exponent(self) -> None:
        """Test that list ** (column expression) works."""
        data = {
            "policy_id": [1, 2],
            "itm": [[2.0, 3.0], [4.0, 5.0]],
            "base_power": [1.0, 2.0],
        }
        af = ActuarialFrame(data)

        # Exponent is an expression: base_power + 1
        af.result = af.itm ** (af.base_power + 1)

        result = af.collect()

        # Row 1: power = 1 + 1 = 2, so [2^2, 3^2] = [4.0, 9.0]
        # Row 2: power = 2 + 1 = 3, so [4^3, 5^3] = [64.0, 125.0]
        result_list = result["result"].to_list()

        assert result_list[0][0] == pytest.approx(4.0)
        assert result_list[0][1] == pytest.approx(9.0)
        assert result_list[1][0] == pytest.approx(64.0)
        assert result_list[1][1] == pytest.approx(125.0)


class TestListClipWithColumnBounds:
    """Tests for list.clip(column_lower, column_upper) operations."""

    def test_list_clip_with_scalar_column_bounds(self) -> None:
        """Test that list.clip(scalar_col, scalar_col) works.

        This is the core use case from GSP-10:
        af.itm.clip(af.L, af.U) where itm is list[f64] and L, U are f64
        """
        data = {
            "policy_id": [1, 2],
            # List column: values to clip
            "values": [[0.5, 1.5, 2.5, 3.5], [0.0, 5.0, 10.0]],
            # Scalar columns: bounds per policy
            "lower": [1.0, 2.0],
            "upper": [3.0, 8.0],
        }
        af = ActuarialFrame(data)

        # This should work: list.clip(scalar_col, scalar_col)
        # type: ignore because we're testing new functionality (GSP-10)
        af.clipped = af.values.clip(af.lower, af.upper)  # type: ignore[arg-type]

        result = af.collect()

        # Verify results
        # Row 1: clip to [1.0, 3.0]: [0.5->1.0, 1.5, 2.5, 3.5->3.0]
        # Row 2: clip to [2.0, 8.0]: [0.0->2.0, 5.0, 10.0->8.0]
        clipped_list = result["clipped"].to_list()

        assert len(clipped_list[0]) == 4
        assert clipped_list[0][0] == pytest.approx(1.0)
        assert clipped_list[0][1] == pytest.approx(1.5)
        assert clipped_list[0][2] == pytest.approx(2.5)
        assert clipped_list[0][3] == pytest.approx(3.0)

        assert len(clipped_list[1]) == 3
        assert clipped_list[1][0] == pytest.approx(2.0)
        assert clipped_list[1][1] == pytest.approx(5.0)
        assert clipped_list[1][2] == pytest.approx(8.0)

    def test_list_clip_with_only_lower_bound_column(self) -> None:
        """Test list.clip(lower_col, literal) works."""
        data = {
            "policy_id": [1, 2],
            "values": [[-1.0, 0.5, 2.0], [-5.0, 0.0, 5.0]],
            "lower": [0.0, -2.0],
        }
        af = ActuarialFrame(data)

        # Lower bound from column, upper bound literal
        af.clipped = af.values.clip(af.lower, 10.0)  # type: ignore[arg-type]

        result = af.collect()

        # Row 1: clip to [0.0, 10.0]: [-1.0->0.0, 0.5, 2.0]
        # Row 2: clip to [-2.0, 10.0]: [-5.0->-2.0, 0.0, 5.0]
        clipped_list = result["clipped"].to_list()

        assert clipped_list[0][0] == pytest.approx(0.0)
        assert clipped_list[0][1] == pytest.approx(0.5)
        assert clipped_list[0][2] == pytest.approx(2.0)

        assert clipped_list[1][0] == pytest.approx(-2.0)
        assert clipped_list[1][1] == pytest.approx(0.0)
        assert clipped_list[1][2] == pytest.approx(5.0)

    def test_list_clip_with_only_upper_bound_column(self) -> None:
        """Test list.clip(literal, upper_col) works."""
        data = {
            "policy_id": [1, 2],
            "values": [[1.0, 5.0, 10.0], [2.0, 8.0, 15.0]],
            "upper": [6.0, 10.0],
        }
        af = ActuarialFrame(data)

        # Lower bound literal, upper bound from column
        af.clipped = af.values.clip(0.0, af.upper)  # type: ignore[arg-type]

        result = af.collect()

        # Row 1: clip to [0.0, 6.0]: [1.0, 5.0, 10.0->6.0]
        # Row 2: clip to [0.0, 10.0]: [2.0, 8.0, 15.0->10.0]
        clipped_list = result["clipped"].to_list()

        assert clipped_list[0][0] == pytest.approx(1.0)
        assert clipped_list[0][1] == pytest.approx(5.0)
        assert clipped_list[0][2] == pytest.approx(6.0)

        assert clipped_list[1][0] == pytest.approx(2.0)
        assert clipped_list[1][1] == pytest.approx(8.0)
        assert clipped_list[1][2] == pytest.approx(10.0)


class TestCombinedOperations:
    """Tests combining pow and clip operations as in real actuarial formulas."""

    def test_dynamic_lapse_formula(self) -> None:
        """Test the full dynamic lapse formula from GSP-10.

        Formula: (1.0 - M * (1.0 / itm - D)).clip(L, U)
        Then: Y * itm ** Power
        """
        data = {
            "policy_id": [1],
            "itm": [[0.8, 1.0, 1.2]],  # In-the-money ratios
            "M": [0.5],
            "D": [0.1],
            "L": [0.5],
            "U": [2.0],
            "Y": [1.0],
            "power": [2.0],
        }
        af = ActuarialFrame(data)

        # Step 1: Calculate raw factor
        af.raw = 1.0 - af.M * (1.0 / af.itm - af.D)

        # Step 2: Clip with column bounds
        af.clipped = af.raw.clip(af.L, af.U)  # type: ignore[arg-type]

        # Step 3: Apply power with column exponent
        af.result = af.Y * af.itm**af.power

        result = af.collect()

        # Verify power calculation: [0.8^2, 1.0^2, 1.2^2] = [0.64, 1.0, 1.44]
        result_list = result["result"].to_list()
        assert result_list[0][0] == pytest.approx(0.64)
        assert result_list[0][1] == pytest.approx(1.0)
        assert result_list[0][2] == pytest.approx(1.44)
