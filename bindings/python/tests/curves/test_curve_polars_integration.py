# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end smoke test — Curve composes with Polars LazyFrames + Schedule."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import Curve, Schedule


class TestCurveSchedulePolarsIntegration:
    """Curve + Schedule + Polars compose end-to-end."""

    def test_spot_rate_from_schedule_year_fractions(self) -> None:
        """Schedule.year_fractions() feeds Curve.spot_rate() yielding rates per period.

        Each year fraction from the monthly grid is ≈ 1/12, which is below the
        first curve knot at 0.5 — the interpolator flat-extrapolates to 0.025.
        """
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        yfs = sched.year_fractions()  # list[float] of length 12, each = 1/12

        curve = Curve.from_zero_rates(
            tenors=[0.5, 1.0, 5.0, 10.0],
            rates=[0.025, 0.030, 0.035, 0.040],
        )
        rates = curve.spot_rate(yfs)
        assert isinstance(rates, list)
        assert len(rates) == 12
        # Every year fraction is 1/12 ≈ 0.083 — below first knot 0.5
        # → flat-extrapolates to 0.025
        for r in rates:
            assert r == pytest.approx(0.025)

    def test_spot_rate_from_per_row_year_fractions_expr(self) -> None:
        """Schedule.year_fractions_expr() yields a per-row list column."""
        sched = Schedule.from_inception(
            inception_column="inception",
            n_periods=3,
            frequency="1Y",
        )
        frame = pl.DataFrame({"inception": [date(2025, 1, 1)]})
        frame2 = frame.with_columns(yfs=sched.year_fractions_expr())
        for row in frame2.get_column("yfs").to_list():
            for yf in row:
                assert yf == pytest.approx(1.0)

    def test_curve_spot_rate_in_with_columns_pipeline(self) -> None:
        """User-style: pl.col('t') → curve.spot_rate(t) is a valid column expression."""
        curve = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        frame = pl.DataFrame({"t": [1.0, 3.0, 5.0, 10.0]})
        result = frame.with_columns(rate=curve.spot_rate(pl.col("t")))
        # Linear interp between knots:
        #   t=1 -> 0.03, t=3 -> 0.035, t=5 -> 0.04, t=10 -> 0.05
        assert result.get_column("rate").to_list() == pytest.approx(
            [0.03, 0.035, 0.04, 0.05],
        )

    def test_curve_grow_pattern_user_facing(self) -> None:
        """Spec §4.4 pattern — rate column feeds a growth multiplier."""
        curve = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])
        frame = pl.DataFrame(
            {
                "av": [100.0, 200.0, 300.0],
                "t": [1.0, 5.0, 10.0],
            },
        )
        result = frame.with_columns(
            rate=curve.spot_rate(pl.col("t")),
        ).with_columns(
            grown=pl.col("av") * (1 + pl.col("rate") * (1 / 12)),
        )
        expected = [v * (1 + 0.04 / 12) for v in [100.0, 200.0, 300.0]]
        assert result.get_column("grown").to_list() == pytest.approx(expected)
