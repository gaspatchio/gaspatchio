# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fitted Svensson curve is sane between its knots and beyond them.

The fit used to search the decay parameters from 0.05 years, far below the
shortest knot of an ordinary curve. There the hump and decay loadings are
nearly collinear at the knots, the betas reach about 1e9, and the curve hits
every knot while reading 125% a year between two of them. The fit now admits only
the decay pairs the knots can pin: tau1 at or above the shortest tenor, and a
design whose columns, scaled to unit length, have a condition number of at
most 100.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from gaspatchio.curves import Curve
from gaspatchio.curves._svensson import fit_svensson, svensson_spot_cc

GSP_253_TENORS = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
GSP_253_RATES = [0.030, 0.032, 0.035, 0.040, 0.042, 0.043]

# The tenor sets of the GSP-253 sweep.
SWEEP_TENORS = {
    "six to 30y": [1, 2, 5, 10, 20, 30],
    "six to 10y": [1, 2, 3, 5, 7, 10],
    "ten from 3m": [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30],
    "twelve to 30y": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30],
    "nine to 30y": [1, 2, 3, 5, 7, 10, 15, 20, 30],
}


def test_the_issue_curve_stays_near_its_rates_at_every_month() -> None:
    """GSP-253's six knots: each monthly spot to 30y is within 50 bp of the rates."""
    curve = Curve.fit_svensson(tenors=GSP_253_TENORS, rates=GSP_253_RATES)
    low, high = min(GSP_253_RATES) - 0.005, max(GSP_253_RATES) + 0.005
    for month in range(1, 361):
        spot = curve.spot_rate(month / 12)
        assert low <= spot <= high, f"month {month}: spot {spot}"


def test_the_issue_curve_has_a_plausible_long_run_rate() -> None:
    """b0, the rate the curve tends to, lands between 0 and 10%."""
    curve = Curve.fit_svensson(tenors=GSP_253_TENORS, rates=GSP_253_RATES)
    assert 0.0 < curve.spot_rate(100.0) < 0.10


def test_a_one_ulp_change_of_input_gives_the_same_fit() -> None:
    """``log1p(r)`` and ``log(1 + r)`` differ by an ulp; the fit must not care."""
    by_log1p = fit_svensson(GSP_253_TENORS, [math.log1p(r) for r in GSP_253_RATES])
    by_log = fit_svensson(GSP_253_TENORS, [math.log(1.0 + r) for r in GSP_253_RATES])
    assert by_log1p == pytest.approx(by_log, rel=1e-9)


@pytest.mark.parametrize("name", list(SWEEP_TENORS))
def test_no_ordinary_upward_curve_fits_wild(name: str) -> None:
    """Twelve random upward curves per tenor set: sane spots, small betas.

    Wild is the sweep's own test: a spot outside [-10%, +20%] anywhere from
    0.05 years to the last knot. Before the bounds, 85 of 300 such curves were.
    """
    tenors = np.array(SWEEP_TENORS[name], dtype=float)
    rng = np.random.default_rng(20261111)
    grid = np.arange(0.05, tenors[-1] + 1e-9, 0.05)
    for _ in range(12):
        level, slope, k = (
            rng.uniform(0.01, 0.05),
            rng.uniform(0, 0.02),
            rng.uniform(2, 8),
        )
        rates = (
            level
            + slope * (1 - np.exp(-tenors / k))
            + rng.normal(0, 0.0005, tenors.size)
        )
        fit = fit_svensson(list(tenors), list(np.log1p(rates)))
        spots = [svensson_spot_cc(float(x), **fit) for x in grid]
        assert all(math.log(0.90) <= s <= math.log(1.20) for s in spots)
        assert max(abs(fit[b]) for b in ("b0", "b1", "b2", "b3")) < 1.0


def test_a_flat_curve_still_fits_exactly() -> None:
    """Flat 3% at six knots reads 3% everywhere, as before."""
    curve = Curve.fit_svensson(tenors=GSP_253_TENORS, rates=[0.03] * 6)
    for t in (0.25, 1.5, 7.5, 25.0, 60.0):
        assert curve.spot_rate(t) == pytest.approx(0.03, abs=1e-12)


def test_tenors_that_cannot_pin_the_decay_parameters_are_refused_by_name() -> None:
    """Knots from 5 to 10 years leave no admissible pair: refuse, naming the moves."""
    tenors = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    rates = [0.030, 0.031, 0.032, 0.033, 0.034, 0.035]
    with pytest.raises(ValueError, match="5 to 10 years") as raised:
        Curve.fit_svensson(tenors=tenors, rates=rates)
    message = str(raised.value)
    assert "fit_smith_wilson" in message
    assert "from_svensson" in message
