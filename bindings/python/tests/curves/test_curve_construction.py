# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve construction + validation tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gaspatchio_core.curves._curve import Curve
from gaspatchio_core.schedule._day_count import (
    Actual365Fixed,
    ActualActualISDA,
    OneTwelfth,
)


class TestFromZeroRates:
    """Tests for Curve.from_zero_rates construction and validation."""

    def test_basic_construction(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Store tenors/rates as tuples with correct day_count and interpolation."""
        c = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=ActualActualISDA(),
        )
        assert c.tenors == tuple(flat_3pct_tenors)
        assert c.rates == tuple(flat_3pct_rates)
        assert c.day_count == ActualActualISDA()
        assert c.interpolation == "linear"

    def test_default_day_count_is_actual_actual_isda(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Omitting day_count defaults to ActualActualISDA."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.day_count == ActualActualISDA()

    def test_default_interpolation_is_linear(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Omitting interpolation defaults to 'linear'."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.interpolation == "linear"

    def test_tenors_and_rates_must_match_length(self) -> None:
        """Mismatched tenor/rate lengths raise ValueError mentioning 'length'."""
        with pytest.raises(ValueError, match="length"):
            Curve.from_zero_rates(tenors=[1.0, 2.0], rates=[0.03])

    def test_tenors_must_be_strictly_increasing(self) -> None:
        """Raise ValueError mentioning 'strictly increasing' for non-monotone tenors."""
        with pytest.raises(ValueError, match="strictly increasing"):
            Curve.from_zero_rates(tenors=[1.0, 1.0, 2.0], rates=[0.03, 0.03, 0.04])
        with pytest.raises(ValueError, match="strictly increasing"):
            Curve.from_zero_rates(tenors=[1.0, 0.5, 2.0], rates=[0.03, 0.03, 0.04])

    def test_at_least_two_knots_required(self) -> None:
        """A single knot raises ValueError mentioning 'at least 2'."""
        with pytest.raises(ValueError, match="at least 2"):
            Curve.from_zero_rates(tenors=[1.0], rates=[0.03])

    def test_unknown_interpolation_raises(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Raise ValueError mentioning 'interpolation' for unsupported method."""
        with pytest.raises(ValueError, match="interpolation"):
            Curve.from_zero_rates(
                tenors=flat_3pct_tenors,
                rates=flat_3pct_rates,
                interpolation="cubic",  # type: ignore[arg-type]
            )

    def test_equal_curves_compare_equal_and_hash_equal(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Two curves with identical inputs are equal and hash-equal."""
        a = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        b = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert a == b
        assert hash(a) == hash(b)

    def test_different_day_count_makes_curves_unequal(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Curves with different day_count conventions are not equal."""
        a = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=Actual365Fixed(),
        )
        b = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=OneTwelfth(),
        )
        assert a != b
        assert hash(a) != hash(b)

    def test_is_frozen(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """Raise FrozenInstanceError on attribute assignment — Curve is immutable."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        with pytest.raises(FrozenInstanceError):
            c.something = 42  # type: ignore[misc]


class TestPublicAPI:
    """Curve is reachable via gaspatchio_core.Curve and gaspatchio_core.curves.Curve."""

    def test_curve_importable_from_subpackage(self) -> None:
        """gaspatchio_core.curves.Curve is the same object as the private one."""
        from gaspatchio_core.curves import Curve
        from gaspatchio_core.curves._curve import Curve as PrivateCurve

        assert Curve is PrivateCurve

    def test_top_level_import(self) -> None:
        """gaspatchio_core has a Curve attribute."""
        import gaspatchio_core

        assert hasattr(gaspatchio_core, "Curve")

    def test_top_level___all___includes_curve(self) -> None:
        """gaspatchio_core.__all__ includes 'Curve'."""
        import gaspatchio_core

        assert "Curve" in gaspatchio_core.__all__
