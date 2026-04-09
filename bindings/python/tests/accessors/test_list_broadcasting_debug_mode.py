# ABOUTME: Test list broadcasting conditionals work in debug mode
# ABOUTME: Verifies when-then-otherwise with list columns traces operations correctly
# ruff: noqa: S101, PLR2004, ANN201, SLF001, ERA001
# type: ignore[attr-defined]

"""Test that list broadcasting conditionals work in debug mode with tracing."""

import pytest

from gaspatchio_core import ActuarialFrame, when


class TestListBroadcastingDebugMode:
    """Test list broadcasting in debug/tracing mode (Task 5)."""

    @pytest.mark.xfail(
        reason="Rust list_conditional plugin does not yet support scalar-then-list-otherwise"
    )
    def test_simple_conditional_debug_mode(self):
        """Test simple when-then-otherwise with list columns in debug mode.

        This test currently fails with NotImplementedError.
        After Task 5, it should pass and capture traced operations.
        """
        data = {
            "policy_id": [1, 2],
            "months": [[0, 1, 2], [0, 1, 2]],
            "values": [[100.0, 200.0, 300.0], [150.0, 250.0, 350.0]],
        }
        af = ActuarialFrame(data)

        # Enable debug mode (tracing)
        af._tracing = True

        # Apply conditional with list broadcasting
        # Currently raises: NotImplementedError: List broadcasting for column 'adjusted'
        # not yet supported in tracing mode
        af.adjusted = when(af.months == 0).then(0.0).otherwise(af.values)

        # Should capture the operation in computation graph
        assert len(af._computation_graph) > 0
        assert any(op.alias == "adjusted" for op in af._computation_graph)

        # Collect and verify results
        result = af.collect()

        # Policy 1: month 0 should be 0.0, others should be original values
        assert result["adjusted"][0].to_list() == [0.0, 200.0, 300.0]
        # Policy 2: month 0 should be 0.0, others should be original values
        assert result["adjusted"][1].to_list() == [0.0, 250.0, 350.0]

    def test_multiple_conditionals_debug_mode(self):
        """Test multiple when-then-otherwise operations in debug mode.

        **KNOWN LIMITATION**: This test exposes a bug where sequential conditionals
        that reference list columns created by previous conditionals fail due to
        nested explode/re-aggregate patterns that Polars cannot resolve.

        The issue occurs in BOTH debug and optimize modes, not just debug mode.

        See Linear issue GSP-5 for details and possible solutions.

        Workaround:
        ```python
        af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)
        af = ActuarialFrame(af.collect())  # Materialize intermediate result
        af.doubled = when(...).then(af.adjusted * 2).otherwise(af.adjusted)
        ```
        """
        data = {
            "policy_id": [1],
            "month": [[0, 1, 2, 3, 4, 5]],
            "amount": [[1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0]],
        }
        af = ActuarialFrame(data)
        af._tracing = True

        # First conditional: zero out first month
        af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)

        # Second conditional: double values in months 2-3
        # THIS WILL FAIL - references list column created by previous conditional
        af.doubled = (
            when((af.month >= 2) & (af.month <= 3))
            .then(af.adjusted * 2)
            .otherwise(af.adjusted)
        )

        # Should have two operations in graph
        assert len(af._computation_graph) >= 2
        assert any(op.alias == "adjusted" for op in af._computation_graph)
        assert any(op.alias == "doubled" for op in af._computation_graph)

        result = af.collect()

        # Expected: [0.0, 1100.0, 2400.0, 2600.0, 1400.0, 1500.0]
        #           month 0: 0.0 (zeroed)
        #           month 1: 1100.0 (unchanged)
        #           months 2-3: doubled (1200*2, 1300*2)
        #           months 4-5: unchanged
        expected = [0.0, 1100.0, 2400.0, 2600.0, 1400.0, 1500.0]
        actual = result["doubled"][0].to_list()
        assert actual == pytest.approx(expected, abs=1e-6)

    def test_actuarial_pattern_debug_mode(self):
        """Test realistic actuarial pattern: maturity and zeroing after maturity."""
        data = {
            "policy_id": [1, 2],
            "policy_term": [2, 3],  # 2 years = 24 months, 3 years = 36 months
            "month": [[0, 12, 24, 36], [0, 12, 24, 36]],
            "pols_if_raw": [
                [1000.0, 950.0, 900.0, 850.0],
                [2000.0, 1900.0, 1800.0, 1700.0],
            ],
        }
        af = ActuarialFrame(data)
        af._tracing = True

        # Maturity: surviving policies mature when month == policy_term * 12
        af.pols_maturity = (
            when(af.month == af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )

        # Zero out policies at and after maturity
        af.pols_if = (
            when(af.month < af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )

        # Should trace both operations
        assert len(af._computation_graph) >= 2

        result = af.collect()

        # Policy 1 (term=2, matures at month 24):
        # pols_maturity: [0, 0, 900.0, 0]
        # pols_if: [1000.0, 950.0, 0, 0]
        assert result["pols_maturity"][0].to_list() == [0.0, 0.0, 900.0, 0.0]
        assert result["pols_if"][0].to_list() == [1000.0, 950.0, 0.0, 0.0]

        # Policy 2 (term=3, matures at month 36):
        # pols_maturity: [0, 0, 0, 1700.0]
        # pols_if: [2000.0, 1900.0, 1800.0, 0]
        assert result["pols_maturity"][1].to_list() == [0.0, 0.0, 0.0, 1700.0]
        assert result["pols_if"][1].to_list() == [2000.0, 1900.0, 1800.0, 0.0]

    def test_computation_graph_metadata(self):
        """Test that list broadcasting operations include proper metadata."""
        data = {
            "policy_id": [1],
            "duration": [[0, 1, 2]],
            "premium": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)
        af._tracing = True

        # Apply conditional
        af.commission = when(af.duration == 0).then(af.premium).otherwise(0.0)

        # Find the traced operation
        commission_op = None
        for op in af._computation_graph:
            if op.alias == "commission":
                commission_op = op
                break

        assert commission_op is not None, "commission operation not in graph"
        assert commission_op.expected_dtype is not None, (
            "expected_dtype should be inferred"
        )
        assert commission_op.dependencies is not None, (
            "dependencies should be extracted"
        )
        assert "duration" in commission_op.dependencies
        assert "premium" in commission_op.dependencies

        # Check metadata has source location
        assert commission_op.metadata is not None
        assert commission_op.metadata.line_number > 0
