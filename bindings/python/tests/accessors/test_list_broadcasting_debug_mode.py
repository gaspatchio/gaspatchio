# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Test list broadcasting conditionals work in debug mode
# ABOUTME: Verifies when-then-otherwise with list columns traces operations correctly
# ruff: noqa: SLF001

"""Test that list broadcasting conditionals work in debug mode with tracing."""

import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.calculations import CalculationRecord


class TestListBroadcastingDebugMode:
    """Test list broadcasting in debug/tracing mode."""

    def test_simple_conditional_debug_mode(self) -> None:
        """A scalar branch broadcasts over a list while retaining the calculation."""
        data = {
            "policy_id": [1, 2],
            "months": [[0, 1, 2], [0, 1, 2]],
            "values": [[100.0, 200.0, 300.0], [150.0, 250.0, 350.0]],
        }
        af = ActuarialFrame(data)

        # Enable debug mode (tracing)
        af._traced_run = True

        # Apply conditional with list broadcasting
        af.adjusted = when(af.months == 0).then(0.0).otherwise(af.values)

        # Should record the calculation
        assert [
            record.column
            for record in af._calculations
            if isinstance(record, CalculationRecord)
        ] == ["adjusted"]

        # Collect and verify results
        result = af.collect()

        # Policy 1: month 0 should be 0.0, others should be original values
        assert result["adjusted"][0].to_list() == [0.0, 200.0, 300.0]
        # Policy 2: month 0 should be 0.0, others should be original values
        assert result["adjusted"][1].to_list() == [0.0, 250.0, 350.0]

    def test_multiple_conditionals_debug_mode(self) -> None:
        """Sequential list conditionals compose lazily and retain both records."""
        data = {
            "policy_id": [1],
            "month": [[0, 1, 2, 3, 4, 5]],
            "amount": [[1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0]],
        }
        af = ActuarialFrame(data)
        af._traced_run = True

        # First conditional: zero out first month
        af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)

        # Second conditional: double values in months 2-3
        af.doubled = (
            when((af.month >= 2) & (af.month <= 3))
            .then(af.adjusted * 2)
            .otherwise(af.adjusted)
        )

        # Should have recorded both calculations
        assert [
            record.column
            for record in af._calculations
            if isinstance(record, CalculationRecord)
        ] == [
            "adjusted",
            "doubled",
        ]

        result = af.collect()

        #           month 0: 0.0 (zeroed)
        #           month 1: 1100.0 (unchanged)
        #           months 2-3: doubled (1200*2, 1300*2)
        #           months 4-5: unchanged
        expected = [0.0, 1100.0, 2400.0, 2600.0, 1400.0, 1500.0]
        actual = result["doubled"][0].to_list()
        assert actual == pytest.approx(expected, abs=1e-6)

    def test_actuarial_pattern_debug_mode(self) -> None:
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
        af._traced_run = True

        # Maturity: surviving policies mature when month == policy_term * 12
        af.pols_maturity = (
            when(af.month == af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )

        # Zero out policies at and after maturity
        af.pols_if = (
            when(af.month < af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )

        # Should record both calculations
        assert [
            record.column
            for record in af._calculations
            if isinstance(record, CalculationRecord)
        ] == [
            "pols_maturity",
            "pols_if",
        ]

        result = af.collect()

        # Policy 1 (term=2, matures at month 24):
        assert result["pols_maturity"][0].to_list() == [0.0, 0.0, 900.0, 0.0]
        assert result["pols_if"][0].to_list() == [1000.0, 950.0, 0.0, 0.0]

        # Policy 2 (term=3, matures at month 36):
        assert result["pols_maturity"][1].to_list() == [0.0, 0.0, 0.0, 1700.0]
        assert result["pols_if"][1].to_list() == [2000.0, 1900.0, 1800.0, 0.0]

    def test_calculation_record_metadata(self) -> None:
        """Test that list broadcasting calculations record proper metadata."""
        data = {
            "policy_id": [1],
            "duration": [[0, 1, 2]],
            "premium": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)
        af._traced_run = True

        # Apply conditional
        af.commission = when(af.duration == 0).then(af.premium).otherwise(0.0)

        # Find the calculation record
        commission_record = None
        for record in af._calculations:
            if isinstance(record, CalculationRecord) and record.column == "commission":
                commission_record = record
                break

        assert commission_record is not None, "commission not in the calculation log"

        # The record's lowered expression names the columns it reads
        dependencies = commission_record.expr.meta.root_names()
        assert "duration" in dependencies
        assert "premium" in dependencies

        # The record carries the source span of the line that wrote it
        assert commission_record.source is not None
        assert commission_record.source.line > 0
        assert "af.commission" in commission_record.source.statement
