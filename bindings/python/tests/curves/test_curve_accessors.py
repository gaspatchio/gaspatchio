# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve accessor tests — spot_rate, discount_factor, forward_rate."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio_core.curves._curve import Curve


class TestSpotRateScalar:
    """Scalar input → scalar output."""

    def test_returns_knot_value_at_knot(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """At a knot, spot_rate returns the knot value."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.spot_rate(1.0) == pytest.approx(0.03)
        assert c.spot_rate(5.0) == pytest.approx(0.03)
        assert c.spot_rate(30.0) == pytest.approx(0.03)

    def test_interpolates_between_knots(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Halfway between two knots returns the midpoint rate."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.spot_rate(2.5) == pytest.approx(0.0305)

    def test_extrapolates_below_first_knot(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Below first knot, flat-extrapolates to first rate."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.spot_rate(0.0) == pytest.approx(0.025)
        assert c.spot_rate(0.1) == pytest.approx(0.025)

    def test_extrapolates_above_last_knot(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """Above last knot, flat-extrapolates to last rate."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.spot_rate(50.0) == pytest.approx(0.038)


class TestSpotRateList:
    """list[float] input → list[float] output."""

    def test_returns_python_list_for_list_input(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """List input returns a Python list of rates."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        result = c.spot_rate([1.0, 2.5, 7.0, 30.0])
        assert isinstance(result, list)
        assert all(r == pytest.approx(0.03) for r in result)

    def test_preserves_input_length(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """List output length matches list input length."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        result = c.spot_rate([0.5, 1.0, 2.0, 5.0])
        assert len(result) == 4


class TestSpotRatePolars:
    """Polars Series / Expr / numpy inputs return matching shapes."""

    def test_series_input_returns_series(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """A Polars Series in returns a Polars Series with matching name."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        s = pl.Series(name="t", values=[1.0, 2.0, 5.0, 30.0])
        result = c.spot_rate(s)
        assert isinstance(result, pl.Series)
        assert result.name == "t"
        assert result.to_list() == pytest.approx([0.03, 0.03, 0.03, 0.03])

    def test_expr_input_returns_expr(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        """A Polars Expr in is consumable by with_columns()."""
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        frame = pl.DataFrame({"t": [0.5, 1.0, 2.0, 5.0]})
        result = frame.with_columns(rate=c.spot_rate(pl.col("t")))
        assert result.get_column("rate").to_list() == pytest.approx(
            [0.025, 0.028, 0.030, 0.032],
        )

    def test_numpy_input_returns_numpy(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """A numpy ndarray in returns an ndarray of the same length."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        arr = np.array([1.0, 2.0, 5.0])
        result = c.spot_rate(arr)
        assert isinstance(result, np.ndarray)
        assert result.tolist() == pytest.approx([0.03, 0.03, 0.03])


class TestDiscountFactor:
    """Annually compounded discount factor: DF(t) = (1 + r(t))^(-t)."""

    def test_at_zero_tenor_is_one(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        """DF(0) = 1 by definition."""
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.discount_factor(0.0) == pytest.approx(1.0)

    def test_at_one_year_is_one_over_one_plus_rate(self) -> None:
        """DF(1) = 1 / (1 + r) annually compounded."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.03])
        assert c.discount_factor(1.0) == pytest.approx(1 / 1.03)

    def test_at_t_years_is_one_over_one_plus_rate_to_t(self) -> None:
        """DF(t) = (1 + r(t))^(-t) — interpolated rate raised to -t."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        rate_at_2 = c.spot_rate(2.0)
        assert c.discount_factor(2.0) == pytest.approx((1 + rate_at_2) ** -2)

    def test_list_input(self) -> None:
        """List input returns list of DFs."""
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.03])
        result = c.discount_factor([0.0, 1.0, 2.0])
        assert isinstance(result, list)
        assert result == pytest.approx([1.0, 1 / 1.03, 1 / (1.03**2)])

    def test_expr_input(self) -> None:
        """Polars Expr in is consumable by with_columns()."""
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.03])
        frame = pl.DataFrame({"t": [0.0, 1.0, 2.0]})
        result = frame.with_columns(df_=c.discount_factor(pl.col("t")))
        assert result.get_column("df_").to_list() == pytest.approx(
            [1.0, 1 / 1.03, 1 / (1.03**2)],
        )


class TestForwardRate:
    """Annually compounded forward rate F(t1, t2).

    Defining identity: DF(t1)/DF(t2) = (1+F)^(t2-t1).
    """

    def test_forward_equals_spot_when_t1_is_zero(self) -> None:
        """F(0, t) = r(t) when DF(0) = 1."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        f = c.forward_rate(t1=0.0, t2=1.0)
        assert f == pytest.approx(0.03)

    def test_forward_via_discount_factor_ratio(self) -> None:
        """DF(t1) / DF(t2) = (1 + F)^(t2 - t1) — the defining identity."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        df_1 = c.discount_factor(1.0)
        df_3 = c.discount_factor(3.0)
        f = c.forward_rate(t1=1.0, t2=3.0)
        assert (df_1 / df_3) == pytest.approx((1 + f) ** 2)

    def test_flat_curve_gives_flat_forward(self) -> None:
        """On a flat curve, every forward rate equals the spot rate."""
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])
        assert c.forward_rate(t1=2.0, t2=5.0) == pytest.approx(0.04)
        assert c.forward_rate(t1=10.0, t2=20.0) == pytest.approx(0.04)

    def test_t1_must_be_strictly_less_than_t2(self) -> None:
        """t1 >= t2 raises ValueError."""
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.04])
        with pytest.raises(ValueError, match="t1.*t2"):
            c.forward_rate(t1=5.0, t2=5.0)
        with pytest.raises(ValueError, match="t1.*t2"):
            c.forward_rate(t1=10.0, t2=5.0)
