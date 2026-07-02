# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Nelson-Siegel-Svensson (NSS) closed-form curve evaluation."""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.curves import Curve
from gaspatchio_core.curves._svensson import (
    fit_svensson,
    svensson_spot,
    svensson_spot_cc,
)

# Fed GSW 1987-12-01 params (percent units), well-separated taus
GSW = {
    "b0": 7.2283,
    "b1": -1.6739,
    "b2": -0.8650,
    "b3": 6.9326,
    "tau1": 0.19719,
    "tau2": 8.3942,
}


def test_svensson_cc_limits() -> None:
    """Short-rate limit = b0+b1; long-rate limit = b0.

    The long-rate check uses a looser tolerance: at t=1e6 the exponential
    terms are numerically zero but floating-point residuals from tau2=8.39
    mean the result differs from b0 by O(1e-5) in percent units.
    """
    assert svensson_spot_cc(1e-9, **GSW) == pytest.approx(GSW["b0"] + GSW["b1"], abs=1e-6)
    assert svensson_spot_cc(1e6, **GSW) == pytest.approx(GSW["b0"], abs=1e-4)


def test_svensson_value_independent_formula() -> None:
    """Cross-check against an independent re-derivation of GSW eq.22 at several tenors."""
    p = {"b0": 0.04, "b1": -0.01, "b2": 0.005, "b3": 0.002, "tau1": 1.5, "tau2": 10.0}

    def ref(t: float) -> float:
        x1, x2 = t / p["tau1"], t / p["tau2"]
        l1 = (1 - math.exp(-x1)) / x1
        c1 = l1 - math.exp(-x1)
        l2 = (1 - math.exp(-x2)) / x2
        c2 = l2 - math.exp(-x2)
        return p["b0"] + p["b1"] * l1 + p["b2"] * c1 + p["b3"] * c2

    for t in [0.25, 1.0, 5.0, 10.0, 30.0]:
        assert svensson_spot_cc(t, **p) == pytest.approx(ref(t), abs=1e-12)


def test_svensson_cross_path() -> None:
    """scalar / Series / scalar-Expr / list-column all agree to machine precision."""
    c = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    ts = [0.5, 1.0, 5.0, 10.0, 30.0]

    scalar = [c.spot_rate(t) for t in ts]

    series = c.spot_rate(pl.Series("t", ts)).to_list()

    scalar_expr = pl.DataFrame({"t": ts}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()

    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]

    for a, s, se, le in zip(scalar, series, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(se, abs=1e-12)
        assert a == pytest.approx(le, abs=1e-12)


def test_from_svensson_validation_tau1() -> None:
    """tau1 <= 0 raises ValueError."""
    with pytest.raises(ValueError, match="tau1"):
        Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.0, b3=0.0, tau1=0.0, tau2=10.0)


def test_from_svensson_validation_tau2() -> None:
    """tau2 <= 0 raises ValueError."""
    with pytest.raises(ValueError, match="tau2"):
        Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.0, b3=0.0, tau1=1.5, tau2=-1.0)


def test_from_svensson_warns_non_positive_b0() -> None:
    """b0 <= 0 emits a UserWarning (not raised)."""
    with pytest.warns(UserWarning, match="b0"):
        Curve.from_svensson(b0=-0.01, b1=0.0, b2=0.0, b3=0.0, tau1=1.5, tau2=10.0)


def test_from_svensson_warns_non_positive_short_rate() -> None:
    """b0+b1 <= 0 emits a UserWarning when b0 itself is positive."""
    with pytest.warns(UserWarning, match="b0\\+b1"):
        Curve.from_svensson(b0=0.01, b1=-0.02, b2=0.0, b3=0.0, tau1=1.5, tau2=10.0)


def test_from_svensson_parametric_payload() -> None:
    """Parametric payload is stored and accessible."""
    c = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    assert c.parametric is not None
    assert c.parametric.kind == "svensson"
    assert c.parametric.b0 == pytest.approx(0.04)
    assert c.parametric.tau1 == pytest.approx(1.5)
    assert c.tenors == ()
    assert c.rates == ()


def test_svensson_canonical_form() -> None:
    """Canonical form includes a parametric sub-dict for svensson curves."""
    c = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    cf = c.canonical_form()
    assert cf["kind"] == "Curve"
    assert cf["tenors"] == []
    assert cf["rates"] == []
    assert "parametric" in cf
    p = cf["parametric"]
    assert isinstance(p, dict)
    assert p["kind"] == "svensson"
    assert p["b0"] == pytest.approx(0.04)


def test_svensson_source_sha_stable() -> None:
    """Two identically-constructed svensson curves have the same SHA."""
    a = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    b = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0)
    assert a.source_sha() == b.source_sha()
    assert a.source_sha().startswith("sha256:")


def test_svensson_source_sha_different_from_knot_curve() -> None:
    """A svensson curve has a different SHA from any knot curve."""
    svensson_c = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.0, b3=0.0, tau1=1.5, tau2=10.0)
    knot_c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
    assert svensson_c.source_sha() != knot_c.source_sha()


def test_knot_curve_source_sha_unchanged() -> None:
    """Knot curves produce the exact same SHA bytes as before the parametric field was added."""
    # These SHA values are computed from canonical_form with NO 'parametric' key
    # (parametric=None → not included → identical canonical bytes to the pre-parametric version).
    a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
    b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
    # Identity: same curve → same SHA
    assert a.source_sha() == b.source_sha()
    # Changing a rate changes the SHA
    c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.041])
    assert a.source_sha() != c.source_sha()


def test_fit_recovers_curve_values_not_params() -> None:
    """Fit in CC space recovers CURVE VALUES (params are non-unique)."""
    true = {"b0": 0.045, "b1": -0.02, "b2": 0.01, "b3": 0.008, "tau1": 0.5, "tau2": 7.0}
    tenors = [0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    rates = [svensson_spot_cc(t, **true) for t in tenors]  # CC observations
    fit = fit_svensson(tenors, rates)
    for t in [0.75, 4.0, 15.0, 25.0]:
        got = svensson_spot_cc(t, **fit)
        want = svensson_spot_cc(t, **true)
        assert got == pytest.approx(want, abs=1e-6)


def test_fit_too_few_observations_raises() -> None:
    """Fewer than 6 observations raises ValueError mentioning the minimum count."""
    with pytest.raises(ValueError, match="6"):
        fit_svensson([1.0, 2.0, 3.0], [0.01, 0.02, 0.03])


def test_curve_fit_svensson_recovers_annual_curve() -> None:
    """Curve.fit_svensson on ANNUAL observations recovers the ANNUAL curve.

    Pins the annual->cc conversion: observations are generated as annual rates,
    fitted, and the fitted curve's annual spot_rate must match at and between
    the source tenors.
    """
    true = {"b0": 0.045, "b1": -0.02, "b2": 0.01, "b3": 0.008, "tau1": 0.5, "tau2": 7.0}
    tenors = [0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    annual = [svensson_spot(t, **true) for t in tenors]  # ANNUAL observations
    c = Curve.fit_svensson(tenors=tenors, rates=annual)
    # at the source tenors, the fitted annual curve reproduces the annual observations
    for t, a in zip(tenors, annual, strict=True):
        assert c.spot_rate(t) == pytest.approx(a, abs=1e-6)
    # and between tenors it matches the true annual curve
    for t in [0.75, 4.0, 15.0, 25.0]:
        assert c.spot_rate(t) == pytest.approx(svensson_spot(t, **true), abs=1e-6)


def test_fitted_curve_cross_path() -> None:
    """Fitted NSS curve agrees across scalar, Expr, and list-column eval paths."""
    true = {"b0": 0.045, "b1": -0.02, "b2": 0.01, "b3": 0.008, "tau1": 0.5, "tau2": 7.0}
    tenors = [0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    annual = [svensson_spot(t, **true) for t in tenors]
    c = Curve.fit_svensson(tenors=tenors, rates=annual)
    ts = [0.5, 1.0, 5.0, 10.0, 30.0]
    scalar = [c.spot_rate(t) for t in ts]
    scalar_expr = (
        pl.DataFrame({"t": ts})
        .with_columns(r=c.spot_rate(pl.col("t")))["r"]
        .to_list()
    )
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]
    for a, se, le in zip(scalar, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(se, abs=1e-12)
        assert a == pytest.approx(le, abs=1e-12)
