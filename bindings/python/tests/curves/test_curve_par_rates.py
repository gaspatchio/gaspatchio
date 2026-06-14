# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve.from_par_rates bootstrap tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._bootstrap import zero_to_par_rates
from gaspatchio_core.curves._curve import Curve
from gaspatchio_core.schedule._day_count import Actual360


class TestFromParRates:
    """Annually compounded par-to-zero bootstrap."""

    def test_flat_par_curve_gives_flat_zero_curve(self) -> None:
        """A flat par curve at 4% gives a flat zero curve at 4%."""
        tenors = [1.0, 2.0, 3.0, 4.0, 5.0]
        par_rates = [0.04] * 5
        c = Curve.from_par_rates(tenors=tenors, par_rates=par_rates)
        for r in c.rates:
            assert r == pytest.approx(0.04, abs=1e-9)

    def test_zero_to_par_round_trip(self) -> None:
        """zero_rates → par_rates → from_par_rates recovers the original zero curve."""
        zero_tenors = [1.0, 2.0, 3.0, 4.0, 5.0]
        zero_rates = [0.03, 0.035, 0.04, 0.0425, 0.045]
        original = Curve.from_zero_rates(tenors=zero_tenors, rates=zero_rates)
        par_rates = zero_to_par_rates(zero_tenors, zero_rates)
        rebuilt = Curve.from_par_rates(tenors=zero_tenors, par_rates=par_rates)
        for orig, rec in zip(original.rates, rebuilt.rates, strict=True):
            assert rec == pytest.approx(orig, abs=1e-9)

    def test_tenor_validation(self) -> None:
        """Bootstrap requires integer-year-spaced tenors starting at year 1."""
        with pytest.raises(ValueError, match="annual.*starting at 1"):
            Curve.from_par_rates(tenors=[0.5, 1.5, 2.5], par_rates=[0.03, 0.035, 0.04])
        with pytest.raises(ValueError, match="annual.*starting at 1"):
            Curve.from_par_rates(tenors=[2.0, 3.0, 4.0], par_rates=[0.03, 0.035, 0.04])

    def test_carries_day_count(self) -> None:
        """day_count override is honoured."""
        c = Curve.from_par_rates(
            tenors=[1.0, 2.0, 3.0],
            par_rates=[0.03, 0.035, 0.04],
            day_count=Actual360(),
        )
        assert c.day_count == Actual360()
