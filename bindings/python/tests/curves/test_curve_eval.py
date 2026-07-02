# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the curve_eval Polars expression plugin (GSP-116, Task 2)."""

import math

import numpy as np
import polars as pl
import pytest
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.curves import Curve
from gaspatchio_core.functions.vector import curve_eval


def test_curve_eval_linear_plugin() -> None:
    df = pl.DataFrame({"t": [[0.5, 1.0, 7.5, 11.0]]})
    out = df.select(
        curve_eval(pl.col("t"), method="linear", xs=[1.0, 5.0, 10.0], ys=[0.03, 0.04, 0.05]).alias(
            "r"
        )
    )
    r = out["r"].to_list()[0]
    assert r[0] == pytest.approx(0.03, abs=1e-12)  # flat below xs[0]
    assert r[2] == pytest.approx(0.045, abs=1e-12)  # midpoint 5..10
    assert r[3] == pytest.approx(0.05, abs=1e-12)  # flat above xs[-1]


def _linear_curve() -> Curve:
    return Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])


def test_linear_cross_path_equivalence() -> None:
    c = _linear_curve()
    ts = [0.5, 1.0, 3.0, 7.5, 11.0]
    scalar = [c.spot_rate(t) for t in ts]
    listout = c.spot_rate(ts)
    series = c.spot_rate(pl.Series("t", ts)).to_list()
    # Expr path through an ActuarialFrame list column
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    expr_out = af.collect()["r"].to_list()[0]
    for a, b, s, e in zip(scalar, listout, series, expr_out, strict=True):
        assert a == pytest.approx(b, abs=1e-12)
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(e, abs=1e-12)


def test_discount_factor_expr_no_map_elements() -> None:
    c = _linear_curve()
    af = ActuarialFrame(pl.DataFrame({"t": [[1.0, 2.0, 5.0]]}))
    af.df = c.discount_factor(af["t"])
    out = af.collect()["df"].to_list()[0]
    # DF = (1+r)^(-t); r(1)=0.03, r(2)=0.0325 (interp 1..5), r(5)=0.04
    assert out[0] == pytest.approx((1.03) ** -1, abs=1e-9)
    assert out[1] == pytest.approx((1.0325) ** -2, abs=1e-9)
    assert out[2] == pytest.approx((1.04) ** -5, abs=1e-9)


def test_curve_expr_paths_are_native_streaming() -> None:
    """GSP-116: spot_rate/discount_factor Expr paths must be native plugin
    expressions (no python_udf streaming barrier) for both scalar and list cols."""
    c = _linear_curve()
    plans = [
        pl.LazyFrame({"t": [[0.5, 1.0, 7.5]]})
        .with_columns(r=c.spot_rate(pl.col("t")))
        .explain(engine="streaming"),
        pl.LazyFrame({"t": [0.5, 1.0, 7.5]})
        .with_columns(r=c.spot_rate(pl.col("t")))
        .explain(engine="streaming"),
        pl.LazyFrame({"t": [[1.0, 2.0, 5.0]]})
        .with_columns(d=c.discount_factor(pl.col("t")))
        .explain(engine="streaming"),
    ]
    for plan in plans:
        assert "python_udf" not in plan.lower(), plan


def test_spot_rate_scalar_column_expr() -> None:
    """Scalar Float64 column Expr returns one rate per row (the common user pattern)."""
    c = _linear_curve()
    frame = pl.DataFrame({"t": [0.5, 1.0, 3.0, 7.5, 11.0]})
    out = frame.with_columns(r=c.spot_rate(pl.col("t")))
    # below xs[0]->0.03; at 1->0.03; interp 1..5 at 3 ->0.035; interp 5..10 at 7.5 ->0.045; above ->0.05
    assert out["r"].to_list() == pytest.approx([0.03, 0.03, 0.035, 0.045, 0.05])


def test_discount_factor_cross_path_equivalence() -> None:
    """DF(t) = (1+r)^(-t) must agree across scalar / list / numpy / Series /
    scalar-col Expr / list-col Expr (spec section 9, one curve one answer)."""
    c = _linear_curve()
    ts = [0.5, 1.0, 3.0, 7.5, 11.0]
    scalar = [c.discount_factor(t) for t in ts]
    listout = c.discount_factor(ts)
    numpy_out = list(c.discount_factor(np.array(ts)))
    series = c.discount_factor(pl.Series("t", ts)).to_list()
    scalar_expr = (
        pl.DataFrame({"t": ts}).with_columns(d=c.discount_factor(pl.col("t")))["d"].to_list()
    )
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.d = c.discount_factor(af["t"])
    list_expr = af.collect()["d"].to_list()[0]
    for a, b, n, s, se, le in zip(
        scalar, listout, numpy_out, series, scalar_expr, list_expr, strict=True
    ):
        assert a == pytest.approx(b, abs=1e-12)
        assert a == pytest.approx(n, abs=1e-12)
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(se, abs=1e-12)
        assert a == pytest.approx(le, abs=1e-12)


def test_int_column_expr_accepted() -> None:
    """Integer time columns (Int64) must work through the Expr path (regression)."""
    c = _linear_curve()
    r = pl.DataFrame({"t": [1, 5, 10]}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()
    assert r == pytest.approx([0.03, 0.04, 0.05])
    d = pl.DataFrame({"t": [1, 5, 10]}).with_columns(d=c.discount_factor(pl.col("t")))["d"].to_list()
    assert d == pytest.approx([(1.03) ** -1, (1.04) ** -5, (1.05) ** -10])


def test_log_linear_flat_curve_is_flat() -> None:
    c = Curve.from_zero_rates(
        tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03], interpolation="log_linear"
    )
    assert c.spot_rate(3.0) == pytest.approx(0.03, abs=1e-12)
    af = ActuarialFrame(pl.DataFrame({"t": [[2.0, 3.0, 7.0]]}))
    af.r = c.spot_rate(af["t"])
    for v in af.collect()["r"].to_list()[0]:
        assert v == pytest.approx(0.03, abs=1e-9)


def test_log_linear_sloped_cross_path_equivalence() -> None:
    """A SLOPED log_linear curve must agree across scalar / list / Series / scalar-Expr / list-Expr."""
    c = Curve.from_zero_rates(
        tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05], interpolation="log_linear"
    )
    ts = [0.5, 1.0, 3.0, 7.5, 11.0]
    scalar = [c.spot_rate(t) for t in ts]
    listout = c.spot_rate(ts)
    series = c.spot_rate(pl.Series("t", ts)).to_list()
    scalar_expr = pl.DataFrame({"t": ts}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]
    # log_linear is NOT the same as linear on a sloped curve -> confirm it actually differs from linear
    lin = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
    assert abs(c.spot_rate(3.0) - lin.spot_rate(3.0)) > 1e-6
    for a, b, s, se, le in zip(scalar, listout, series, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(b, abs=1e-12)
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(se, abs=1e-12)
        assert a == pytest.approx(le, abs=1e-12)


def test_pchip_monotone_no_overshoot() -> None:
    """Fritsch-Carlson slopes prevent overshoot on a monotone non-decreasing curve."""
    from gaspatchio_core.curves._interpolation import hermite_eval, pchip_slopes

    xs = [1.0, 2.0, 3.0, 10.0, 15.0]
    ys = [0.01, 0.02, 0.025, 0.05, 0.05]  # monotone non-decreasing
    m = pchip_slopes(xs, ys)
    prev = -1.0
    for i in range(1400):
        t = 1.0 + i * 0.01
        v = hermite_eval(t, xs, ys, m)
        assert 0.01 - 1e-9 <= v <= 0.05 + 1e-9  # no overshoot beyond knot range
        assert v >= prev - 1e-9  # monotonicity preserved
        prev = v


def test_pchip_reproduces_knots() -> None:
    """pchip spot_rate must reproduce exact knot values at each tenor."""
    c = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 5.0, 10.0], rates=[0.01, 0.02, 0.03, 0.035], interpolation="pchip"
    )
    for u, r in zip([1.0, 2.0, 5.0, 10.0], [0.01, 0.02, 0.03, 0.035], strict=True):
        assert c.spot_rate(u) == pytest.approx(r, abs=1e-12)


def test_pchip_cross_path() -> None:
    """pchip must agree across scalar / list / Series / scalar-Expr / list-Expr paths."""
    c = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 5.0, 10.0], rates=[0.01, 0.02, 0.03, 0.035], interpolation="pchip"
    )
    ts = [1.0, 1.5, 3.0, 7.0, 12.0]
    scalar = [c.spot_rate(t) for t in ts]
    series = c.spot_rate(pl.Series("t", ts)).to_list()
    scalar_expr = pl.DataFrame({"t": ts}).with_columns(r=c.spot_rate(pl.col("t")))["r"].to_list()
    af = ActuarialFrame(pl.DataFrame({"t": [ts]}))
    af.r = c.spot_rate(af["t"])
    list_expr = af.collect()["r"].to_list()[0]
    # pchip must differ from linear on a curved region
    lin = Curve.from_zero_rates(tenors=[1.0, 2.0, 5.0, 10.0], rates=[0.01, 0.02, 0.03, 0.035])
    assert abs(c.spot_rate(3.0) - lin.spot_rate(3.0)) > 1e-9
    for a, s, se, le in zip(scalar, series, scalar_expr, list_expr, strict=True):
        assert a == pytest.approx(s, abs=1e-12)
        assert a == pytest.approx(se, abs=1e-12)
        assert a == pytest.approx(le, abs=1e-12)


# ---------------------------------------------------------------------------
# Out-of-domain / non-finite contract (GSP-116, launch defect)
#
# Single sentinel = NaN, uniformly, on EVERY path and container. The predicate:
#   - all 5 methods: non-finite t (NaN, +inf, -inf) -> NaN
#   - log_linear & smith_wilson only: additionally t <= 0.0 -> NaN
#   - linear & pchip: finite t <= 0 keeps flat-extrapolation to ys[0] (NOT NaN)
#   - svensson: finite t <= 0 keeps the closed form (svensson(0) = short-rate
#     limit exp(b0+b1)-1, NOT NaN — the x->0 loading is guarded to (1, 0))
# The eager scalar path and the Expr path must AGREE (both NaN, via isnan).
# Remember NaN != NaN, so compare via math.isnan / .is_nan(), never ==.
# ---------------------------------------------------------------------------

_NON_FINITE = [float("nan"), float("inf"), float("-inf")]


def _all_curves() -> dict[str, Curve]:
    """One curve per method, with a genuinely sloped grid where applicable."""
    return {
        "linear": Curve.from_zero_rates(
            tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05]
        ),
        "log_linear": Curve.from_zero_rates(
            tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05], interpolation="log_linear"
        ),
        "pchip": Curve.from_zero_rates(
            tenors=[1.0, 2.0, 5.0, 10.0], rates=[0.01, 0.02, 0.03, 0.035],
            interpolation="pchip",
        ),
        "svensson": Curve.from_svensson(
            b0=0.040, b1=-0.010, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0
        ),
        "smith_wilson": Curve.fit_smith_wilson(
            tenors=[1, 2, 3, 5, 7, 10, 15, 20],
            rates=[0.031, 0.033, 0.034, 0.036, 0.038, 0.040, 0.041, 0.042],
        ),
    }


def _expr_spot_scalar(c: Curve, t: float) -> float:
    """Evaluate spot_rate via the scalar-column Expr path (one rate per row)."""
    out = pl.DataFrame({"t": [t]}).with_columns(r=c.spot_rate(pl.col("t")))
    return out["r"].to_list()[0]


def _expr_spot_list(c: Curve, t: float) -> float:
    """Evaluate spot_rate via the list-column Expr path (the projection path)."""
    af = ActuarialFrame(pl.DataFrame({"t": [[t]]}))
    af.r = c.spot_rate(af["t"])
    return af.collect()["r"].to_list()[0][0]


@pytest.mark.parametrize("method", ["linear", "log_linear", "pchip", "svensson", "smith_wilson"])
@pytest.mark.parametrize("t", _NON_FINITE)
def test_non_finite_t_is_nan_all_methods(method: str, t: float) -> None:
    """Non-finite t (NaN, +inf, -inf) -> NaN on eager scalar AND both Expr paths."""
    c = _all_curves()[method]
    eager = c.spot_rate(t)
    assert math.isnan(eager), f"{method}: eager spot_rate({t}) = {eager}, expected NaN"
    assert math.isnan(_expr_spot_scalar(c, t)), f"{method}: scalar-Expr({t}) not NaN"
    assert math.isnan(_expr_spot_list(c, t)), f"{method}: list-Expr({t}) not NaN"


@pytest.mark.parametrize("method", ["log_linear", "smith_wilson"])
@pytest.mark.parametrize("t", [0.0, -1.0])
def test_nonpositive_t_is_nan_for_log_linear_and_smith_wilson(method: str, t: float) -> None:
    """t <= 0 -> NaN for log_linear & smith_wilson (replaces ZeroDivisionError / inf)."""
    c = _all_curves()[method]
    eager = c.spot_rate(t)
    assert math.isnan(eager), f"{method}: eager spot_rate({t}) = {eager}, expected NaN"
    assert math.isnan(_expr_spot_scalar(c, t)), f"{method}: scalar-Expr({t}) not NaN"
    assert math.isnan(_expr_spot_list(c, t)), f"{method}: list-Expr({t}) not NaN"


@pytest.mark.parametrize("method", ["linear", "pchip"])
def test_finite_nonpositive_t_unchanged_for_linear_and_pchip(method: str) -> None:
    """Regression guard: linear & pchip at t=0 keep flat-extrapolation to ys[0] (NOT NaN)."""
    c = _all_curves()[method]
    expected = c.rates[0]  # first knot rate (flat extrapolation below xs[0])
    eager = c.spot_rate(0.0)
    assert eager == pytest.approx(expected, abs=1e-12), f"{method}: t=0 -> {eager}"
    assert _expr_spot_scalar(c, 0.0) == pytest.approx(expected, abs=1e-12)
    assert _expr_spot_list(c, 0.0) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("method", ["linear", "log_linear", "pchip", "svensson", "smith_wilson"])
def test_normal_positive_t_unaffected(method: str) -> None:
    """Regression guard: a normal positive t (5.0) is finite and identical across paths."""
    c = _all_curves()[method]
    eager = c.spot_rate(5.0)
    assert math.isfinite(eager), f"{method}: spot_rate(5.0) = {eager}, expected finite"
    assert _expr_spot_scalar(c, 5.0) == pytest.approx(eager, abs=1e-12)
    assert _expr_spot_list(c, 5.0) == pytest.approx(eager, abs=1e-12)


def test_svensson_t_zero_short_rate_limit() -> None:
    """svensson at finite t=0 keeps the closed form (short-rate limit), agreeing across paths.

    The contract says "finite t <= 0 keeps current behaviour" for svensson; only
    non-finite t -> NaN. Both the eager ``_loadings`` and the Rust ``svensson_load``
    guard the x->0 loading to ``(1, 0)``, so svensson(0) is the short-rate limit
    ``exp(b0 + b1) - 1`` (NOT NaN) and is identical on every path.
    """
    c = _all_curves()["svensson"]
    eager = c.spot_rate(0.0)
    assert math.isfinite(eager), f"svensson: eager spot_rate(0.0) = {eager}, expected finite"
    assert eager == pytest.approx(math.exp(0.040 - 0.010) - 1.0, abs=1e-12)
    assert _expr_spot_scalar(c, 0.0) == pytest.approx(eager, abs=1e-12)
    assert _expr_spot_list(c, 0.0) == pytest.approx(eager, abs=1e-12)


def _expr_df_scalar(c: Curve, t: float) -> float:
    """Evaluate discount_factor via the scalar-column Expr path."""
    return pl.DataFrame({"t": [t]}).with_columns(d=c.discount_factor(pl.col("t")))[
        "d"
    ].to_list()[0]


def _expr_df_list(c: Curve, t: float) -> float:
    """Evaluate discount_factor via the list-column Expr path (the projection path)."""
    af = ActuarialFrame(pl.DataFrame({"t": [[t]]}))
    af.d = c.discount_factor(af["t"])
    return af.collect()["d"].to_list()[0][0]


@pytest.mark.parametrize("method", ["log_linear", "smith_wilson"])
@pytest.mark.parametrize("t", [float("inf"), -1.0])
def test_discount_factor_out_of_domain_is_nan(method: str, t: float) -> None:
    """DF = (1 + NaN)^(-t) = NaN must propagate on eager AND both Expr paths.

    The out-of-domain spot rate is the NaN sentinel; for any ``t`` with a
    nonzero exponent the discount factor ``(1 + NaN)^(-t)`` is NaN and the
    failure stays loud through downstream arithmetic. (``t = 0`` is the lone
    IEEE exception — ``x ** 0 == 1`` for every ``x`` including NaN — pinned
    separately by ``test_discount_factor_t_zero_is_one_all_paths``.)
    """
    c = _all_curves()[method]
    eager = c.discount_factor(t)
    assert math.isnan(eager), f"{method}: eager discount_factor({t}) = {eager}, expected NaN"
    assert math.isnan(_expr_df_scalar(c, t)), f"{method}: scalar-Expr DF({t}) not NaN"
    assert math.isnan(_expr_df_list(c, t)), f"{method}: list-Expr DF({t}) not NaN"


@pytest.mark.parametrize("method", ["log_linear", "smith_wilson"])
def test_discount_factor_t_zero_is_one_all_paths(method: str) -> None:
    """At ``t = 0`` the discount factor degenerates to ``1.0`` on every path.

    The spot rate at ``t = 0`` is the NaN sentinel, but ``DF(0) = (1 + r)^(-0)``
    and ``x ** 0 == 1`` for every ``x`` (including NaN) under IEEE-754. The three
    paths therefore agree at ``1.0`` (one curve, one answer); ``discount_factor``
    is NOT special-cased — this is honest IEEE pow propagation.
    """
    c = _all_curves()[method]
    assert c.discount_factor(0.0) == pytest.approx(1.0, abs=1e-12)
    assert _expr_df_scalar(c, 0.0) == pytest.approx(1.0, abs=1e-12)
    assert _expr_df_list(c, 0.0) == pytest.approx(1.0, abs=1e-12)
