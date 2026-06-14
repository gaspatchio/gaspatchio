# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve stress / shift tests."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gaspatchio_core.curves._curve import Curve


class TestShiftParallel:
    """Parallel shift adds the same delta to every knot rate."""

    def test_shifts_every_rate_by_bps(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """+100 bps shifts every rate up by 0.01."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        up = c.shift_parallel(bps=100)
        assert up.rates == tuple(r + 0.01 for r in eiopa_eur_2026q2_zero_rates)

    def test_negative_bps_shifts_down(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """-100 bps shifts every rate down by 0.01."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        down = c.shift_parallel(bps=-100)
        assert down.rates == tuple(r - 0.01 for r in eiopa_eur_2026q2_zero_rates)

    def test_zero_bps_returns_equal_curve(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Shift by 0 produces an equal curve."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.shift_parallel(bps=0) == c

    def test_shift_preserves_tenors_and_day_count(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Shift only changes rates, not tenors / day_count / interpolation."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        up = c.shift_parallel(bps=50)
        assert up.tenors == c.tenors
        assert up.day_count == c.day_count
        assert up.interpolation == c.interpolation

    def test_shifts_compose(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Shift +100 then +50 == shift +150 (additivity)."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        a = c.shift_parallel(bps=100).shift_parallel(bps=50)
        b = c.shift_parallel(bps=150)
        assert a == b

    @given(bps=st.integers(min_value=-500, max_value=500))
    def test_shift_then_unshift_recovers_original(self, bps: int) -> None:
        """shift(bps).shift(-bps) == identity."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        recovered = c.shift_parallel(bps=bps).shift_parallel(bps=-bps)
        for orig, rec in zip(c.rates, recovered.rates, strict=True):
            assert rec == pytest.approx(orig, abs=1e-12)


class TestKeyRateShift:
    """Single-knot bump: shifts ONE rate, leaves the rest untouched."""

    def test_shifts_only_named_tenor(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """+25bps at 10y shifts only the 10y knot."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        shifted = c.key_rate_shift(tenor=10.0, bps=25)
        idx = eiopa_eur_2026q2_tenors.index(10.0)
        for i, (orig, new) in enumerate(zip(c.rates, shifted.rates, strict=True)):
            if i == idx:
                assert new == pytest.approx(orig + 0.0025)
            else:
                assert new == pytest.approx(orig)

    def test_unknown_tenor_raises(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Non-knot tenor raises ValueError."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        with pytest.raises(ValueError, match="tenor 12.5 not in curve"):
            c.key_rate_shift(tenor=12.5, bps=25)

    def test_zero_bps_returns_equal_curve(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Zero shift produces an equal curve."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.key_rate_shift(tenor=10.0, bps=0) == c

    def test_two_key_rate_shifts_compose(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Two distinct knot bumps commute."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        a = c.key_rate_shift(tenor=5.0, bps=25).key_rate_shift(tenor=10.0, bps=50)
        b = c.key_rate_shift(tenor=10.0, bps=50).key_rate_shift(tenor=5.0, bps=25)
        assert a == b
