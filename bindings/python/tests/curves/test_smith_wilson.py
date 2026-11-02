# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Smith-Wilson zero-coupon curve evaluation and ζ-solve.

lifelib worked example (MIT, (c) 2022 lifelib Developers).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, _internal
from gaspatchio.curves import Curve
from gaspatchio.curves._smith_wilson import solve_zeta, sw_price, sw_spot

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
        assert sw_spot(float(u), U, zeta, omega, ALPHA) == pytest.approx(
            float(r), abs=1e-9
        )


def test_sw_alpha_none_calibrates() -> None:
    c = Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=None)
    # a calibrated curve still reproduces its input knots
    for u, r in zip(U, R, strict=True):
        assert c.spot_rate(float(u)) == pytest.approx(float(r), abs=1e-9)
    # supplied alpha below the floor is rejected
    with pytest.raises(ValueError, match="0.05"):
        Curve.fit_smith_wilson(tenors=list(U), rates=list(R), ufr=UFR, alpha=0.01)


def test_calibrate_alpha_meets_gap_and_floor() -> None:
    from gaspatchio.curves._smith_wilson import calibrate_alpha

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
    scalar_expr = (
        pl.DataFrame({"t": ts}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()
    )
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]
    for a, se, le in zip(scalar, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(se, abs=1e-9)
        assert a == pytest.approx(le, abs=1e-9)


def test_spot_is_nan_where_the_discount_factor_is_negative() -> None:
    """A fit whose discount factor goes negative has no spot rate there.

    At the smallest alpha the fit accepts, these rates price a 30-year
    zero-coupon bond below zero. The column path (the Rust kernel) reads that
    point as nan. The scalar path returned a complex number instead, so
    ``discount_factor(30.0)`` raised TypeError and ``spot_rate`` over a Series
    raised converting it.
    """
    curve = Curve.fit_smith_wilson(
        tenors=[1.0, 2.0, 5.0, 10.0, 20.0],
        rates=[0.3, 0.01, 0.4, -0.05, 0.25],
        ufr=0.0,
        alpha=0.05,
    )
    t = 30.0
    p = curve.parametric
    assert p is not None
    price = sw_price(
        np.array([t]),
        np.asarray(p.u, dtype=float),
        np.asarray(p.zeta, dtype=float),
        float(p.omega),
        float(p.alpha),
    )[0]
    assert price < 0.0

    assert np.isnan(curve.spot_rate(t))
    assert np.isnan(curve.discount_factor(t))
    assert curve.spot_rate(pl.Series([t])).is_nan().all()
    on_a_column = pl.DataFrame({"t": [t]}).select(curve.spot_rate(pl.col("t")))
    assert np.isnan(on_a_column.item())


# The column path runs the Rust kernel in the extension, which answers only for
# the source it was built from. Built from this tree -- as CI builds it -- it is
# never older than curve_eval.rs; an extension built before that file last
# changed has not been given the guard this test is about.
_KERNEL_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "core"
    / "src"
    / "polars_functions"
    / "curve_eval.rs"
)


def _extension_predates_the_kernel() -> bool:
    if not _KERNEL_SOURCE.is_file():
        return False
    built = Path(_internal.__file__).stat().st_mtime
    return built < _KERNEL_SOURCE.stat().st_mtime


@pytest.mark.skipif(
    _extension_predates_the_kernel(),
    reason="the loaded extension was built before curve_eval.rs last changed",
)
@pytest.mark.parametrize("t", [0.5, 0.75, 1.0])
def test_both_paths_refuse_a_negative_price(t: float) -> None:
    """The scalar path and the column path agree where the fit prices below zero.

    The kernel took the power of the price whatever its sign. A fractional power
    of a negative number is NaN in Rust, but a whole one is real, so at t = 1/2
    and t = 1 the column path answered a rate -- and at t = 1/2 a positive
    discount factor from a negative price -- where the scalar path answers nan.
    """
    curve = Curve.fit_smith_wilson(
        tenors=[1.5, 2.0], rates=[1.271, -0.381], ufr=0.0, alpha=0.05
    )
    times = pl.DataFrame({"t": [t]})

    assert np.isnan(curve.spot_rate(t))
    assert np.isnan(times.select(curve.spot_rate(pl.col("t"))).item())
    assert np.isnan(curve.discount_factor(t))
    assert np.isnan(times.select(curve.discount_factor(pl.col("t"))).item())
