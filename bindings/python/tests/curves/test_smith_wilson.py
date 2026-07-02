# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Smith-Wilson zero-coupon curve evaluation and ζ-solve.

lifelib worked example (MIT, (c) 2022 lifelib Developers).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.curves import Curve
from gaspatchio_core.curves._smith_wilson import solve_zeta, sw_price, sw_spot

# lifelib worked example (MIT, (c) 2022 lifelib Developers) - see REFERENCES.md (Task 11)
U = np.array([1.0, 2.0, 4.0, 5.0, 6.0, 7.0])
R = np.array([0.01, 0.02, 0.03, 0.032, 0.035, 0.04])
UFR, ALPHA = 0.04, 0.15


def test_sw_matches_lifelib_example() -> None:
    omega = float(np.log(1.0 + UFR))
    zeta = solve_zeta(U, R, UFR, ALPHA)
    assert sw_spot(3.0, U, zeta, omega, ALPHA) == pytest.approx(0.0264236322, abs=1e-9)
    assert sw_spot(10.0, U, zeta, omega, ALPHA) == pytest.approx(0.0485040138, abs=1e-9)
    assert sw_spot(20.0, U, zeta, omega, ALPHA) == pytest.approx(0.0506997613, abs=1e-9)


def test_sw_reproduces_inputs_at_knots() -> None:
    omega = float(np.log(1.0 + UFR))
    zeta = solve_zeta(U, R, UFR, ALPHA)
    for u, r in zip(U, R, strict=True):
        assert sw_spot(float(u), U, zeta, omega, ALPHA) == pytest.approx(float(r), abs=1e-9)


def test_sw_alpha_none_calibrates() -> None:
    c = Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=None)
    # a calibrated curve still reproduces its input knots
    for u, r in zip(U, R, strict=True):
        assert c.spot_rate(float(u)) == pytest.approx(float(r), abs=1e-9)
    # supplied alpha below the floor is rejected
    with pytest.raises(ValueError, match="0.05"):
        Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=0.01)


def test_calibrate_alpha_meets_gap_and_floor() -> None:
    from gaspatchio_core.curves._smith_wilson import calibrate_alpha

    llp = float(U.max())
    cp = max(llp + 40.0, 60.0)
    alpha = calibrate_alpha(U, R, ufr=UFR, llp=llp)
    assert alpha >= 0.05 - 1e-12
    omega = float(np.log(1.0 + UFR))
    zeta = solve_zeta(U, R, UFR, alpha)
    eps = 1e-4
    p1 = float(sw_price(np.array([cp]), U, zeta, omega, alpha)[0])
    p2 = float(sw_price(np.array([cp + eps]), U, zeta, omega, alpha)[0])
    fwd = -(np.log(p2) - np.log(p1)) / eps
    assert abs(fwd - omega) <= 1e-4 + 1e-6


def test_sw_curve_matches_lifelib_and_cross_path() -> None:
    c = Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=ALPHA)
    assert c.spot_rate(3.0) == pytest.approx(0.0264236322, abs=1e-9)
    assert c.spot_rate(20.0) == pytest.approx(0.0506997613, abs=1e-9)
    ts = [1.0, 3.0, 7.0, 20.0]
    scalar = [c.spot_rate(t) for t in ts]
    scalar_expr = pl.DataFrame({"t": ts}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]
    for a, se, le in zip(scalar, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(se, abs=1e-9)
        assert a == pytest.approx(le, abs=1e-9)
