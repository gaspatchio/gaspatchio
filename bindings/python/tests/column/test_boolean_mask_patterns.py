# ABOUTME: Tests for boolean mask patterns: list == scalar and list * bool (GSP-12)
# ABOUTME: Verifies that natural actuarial mask patterns work with list columns
"""Tests for boolean mask patterns: list == scalar and list * bool (GSP-12)."""


from gaspatchio_core import ActuarialFrame


class TestListComparisonToScalar:
    """Test list column compared to scalar column."""

    def test_direct_comparison_assignment(self):
        """af.mask = af.list_col == af.scalar_col should work."""
        af = ActuarialFrame(
            {
                "duration_mth_t": [[0, 1, 2, 3]],
                "maturity_month": [2],
            }
        )

        af.mask = af.duration_mth_t == af.maturity_month

        result = af.collect()
        # Should be [0.0, 0.0, 1.0, 0.0] for months 0,1,2,3 compared to maturity=2
        assert result["mask"].to_list() == [[0.0, 0.0, 1.0, 0.0]]

    def test_comparison_eq_operator(self):
        """Equal operator should work: ==."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.eq_mask = af.values == af.threshold

        result = af.collect()
        assert result["eq_mask"].to_list() == [[0.0, 0.0, 1.0, 0.0, 0.0]]

    def test_comparison_ne_operator(self):
        """Not equal operator should work: !=."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.ne_mask = af.values != af.threshold

        result = af.collect()
        assert result["ne_mask"].to_list() == [[1.0, 1.0, 0.0, 1.0, 1.0]]

    def test_comparison_lt_operator(self):
        """Less than operator should work: <."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.lt_mask = af.values < af.threshold

        result = af.collect()
        assert result["lt_mask"].to_list() == [[1.0, 1.0, 0.0, 0.0, 0.0]]

    def test_comparison_le_operator(self):
        """Less than or equal operator should work: <=."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.le_mask = af.values <= af.threshold

        result = af.collect()
        assert result["le_mask"].to_list() == [[1.0, 1.0, 1.0, 0.0, 0.0]]

    def test_comparison_gt_operator(self):
        """Greater than operator should work: >."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.gt_mask = af.values > af.threshold

        result = af.collect()
        assert result["gt_mask"].to_list() == [[0.0, 0.0, 0.0, 1.0, 1.0]]

    def test_comparison_ge_operator(self):
        """Greater than or equal operator should work: >=."""
        af = ActuarialFrame(
            {
                "values": [[0, 1, 2, 3, 4]],
                "threshold": [2],
            }
        )

        af.ge_mask = af.values >= af.threshold

        result = af.collect()
        assert result["ge_mask"].to_list() == [[0.0, 0.0, 1.0, 1.0, 1.0]]


class TestMultiplicationWithBooleanMask:
    """Test list * bool pattern."""

    def test_list_times_comparison_result(self):
        """af.pols_if * (af.month == af.maturity) should work."""
        af = ActuarialFrame(
            {
                "duration_mth_t": [[0, 1, 2, 3]],
                "maturity_month": [2],
                "pols_if": [[100.0, 100.0, 100.0, 100.0]],
            }
        )

        af.pols_maturity = af.pols_if * (af.duration_mth_t == af.maturity_month)

        result = af.collect()
        # pols_if * [0, 0, 1, 0] = [0, 0, 100, 0]
        assert result["pols_maturity"].to_list() == [[0.0, 0.0, 100.0, 0.0]]

    def test_ideal_actuarial_pattern(self):
        """The pattern from the Linear ticket should work."""
        af = ActuarialFrame(
            {
                "duration_mth_t": [[0, 1, 2, 3, 4, 5]],
                "maturity_month": [3],
                "pols_if_bef_mat": [[1000.0, 995.0, 990.0, 985.0, 980.0, 975.0]],
            }
        )

        # Natural actuarial formula
        af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)

        result = af.collect()
        # Only month 3 should have non-zero value
        expected = [0.0, 0.0, 0.0, 985.0, 0.0, 0.0]
        assert result["pols_maturity"].to_list() == [expected]

    def test_multiple_policies(self):
        """Pattern should work with multiple rows."""
        af = ActuarialFrame(
            {
                "duration_mth_t": [[0, 1, 2], [0, 1, 2, 3, 4]],
                "maturity_month": [1, 3],
                "pols_if": [[100.0, 100.0, 100.0], [200.0, 200.0, 200.0, 200.0, 200.0]],
            }
        )

        af.pols_maturity = af.pols_if * (af.duration_mth_t == af.maturity_month)

        result = af.collect()
        # Row 1: maturity at month 1 -> [0, 100, 0]
        # Row 2: maturity at month 3 -> [0, 0, 0, 200, 0]
        assert result["pols_maturity"].to_list() == [
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 0.0, 200.0, 0.0],
        ]


class TestScalarComparisonsUnaffected:
    """Ensure scalar-to-scalar comparisons still work normally."""

    def test_scalar_comparison_returns_float(self):
        """Scalar comparisons assigned directly now return Float64."""
        af = ActuarialFrame(
            {
                "age": [25, 45, 65, 75],
                "threshold": [65, 65, 65, 65],
            }
        )

        af.is_senior = af.age >= af.threshold

        result = af.collect()
        # Returns Float64 (0.0/1.0) for consistency with list pattern
        assert result["is_senior"].to_list() == [0.0, 0.0, 1.0, 1.0]

    def test_scalar_multiplication_with_mask(self):
        """Scalar multiplication with comparison should work."""
        af = ActuarialFrame(
            {
                "value": [100.0, 200.0, 300.0, 400.0],
                "threshold": [2, 2, 2, 2],
                "index": [1, 2, 3, 4],
            }
        )

        af.result = af.value * (af.index == af.threshold)

        result = af.collect()
        # Only index 2 matches threshold
        assert result["result"].to_list() == [0.0, 200.0, 0.0, 0.0]
