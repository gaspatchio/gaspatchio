# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve interpolation primitives.

Provides ``linear_interpolate`` (linear-on-rates), ``log_linear_spot``
(linear interpolation in log-discount-factor space), and ``hermite_eval``
/ ``pchip_slopes`` (Fritsch-Carlson monotone cubic Hermite) with flat
extrapolation outside the knot grid.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence


def linear_interpolate(
    x: float,
    knots_x: Sequence[float],
    knots_y: Sequence[float],
) -> float:
    """Linear interpolation over a sorted knot grid with flat extrapolation.

    ``knots_x`` must be strictly increasing and the same length as ``knots_y``;
    these invariants are guaranteed by :class:`Curve` at construction time and
    are not re-checked here on the hot path.

    A non-finite ``x`` (NaN or +-inf) is out of domain and yields ``nan``
    (the uniform cross-path sentinel). Finite ``x <= knots_x[0]`` is in domain
    and flat-extrapolates to ``knots_y[0]``.
    """
    if not math.isfinite(x):
        return math.nan
    if x <= knots_x[0]:
        return knots_y[0]
    if x >= knots_x[-1]:
        return knots_y[-1]
    i = bisect_right(knots_x, x)
    x0, x1 = knots_x[i - 1], knots_x[i]
    y0, y1 = knots_y[i - 1], knots_y[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def log_df_knots(tenors: Sequence[float], rates: Sequence[float]) -> list[float]:
    """Log discount factor at each knot: ``-u * ln(1 + r)``.

    Converts (tenor, zero_rate) knots into log-DF knots suitable for
    log-linear interpolation.  The result fed back through
    :func:`log_linear_spot` recovers the original rate exactly at each knot.

    Args:
        tenors: Tenor knot points in years, same length as ``rates``.
        rates: Zero rates at each knot point, same length as ``tenors``.

    Returns:
        List of log-discount-factor values, one per knot.
    """
    return [-u * math.log(1.0 + r) for u, r in zip(tenors, rates, strict=True)]


def log_linear_spot(t: float, tenors: Sequence[float], log_df: Sequence[float]) -> float:
    """Spot rate at ``t`` from log-DF knots (linear in log-DF, flat extrapolation).

    Interpolates linearly in log-discount-factor space and converts back to
    an annually-compounded spot rate:
    ``r(t) = exp(linear_interp(t, tenors, log_df))^(-1/t) - 1``

    The spot rate ``P(t)^(-1/t) - 1`` is undefined at ``t = 0`` and meaningless
    for ``t < 0``; any non-finite ``t`` (NaN or +-inf) or ``t <= 0`` is out of
    domain and yields ``nan`` (the uniform cross-path sentinel).

    Args:
        t: Year fraction at which to evaluate the spot rate. Must be ``> 0``.
        tenors: Tenor knot points in years, strictly increasing.
        log_df: Log-discount-factor values at each knot (from :func:`log_df_knots`).

    Returns:
        The annually-compounded spot rate at ``t``, or ``nan`` when ``t`` is
        non-finite or ``t <= 0``.
    """
    if not math.isfinite(t) or t <= 0.0:
        return math.nan
    ld = linear_interpolate(t, tenors, log_df)
    return math.exp(ld) ** (-1.0 / t) - 1.0


def pchip_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    """Fritsch-Carlson monotonicity-preserving Hermite tangents.

    Computes per-knot slopes for a C1 cubic Hermite interpolant that
    preserves local monotonicity (no overshoot between monotone segments).

    Args:
        xs: Strictly increasing knot x-coordinates, same length as ``ys``.
        ys: Knot y-values, same length as ``xs``.

    Returns:
        A list of slope values ``m[i]`` at each knot, ready for use in
        :func:`hermite_eval`.
    """
    n = len(xs)
    if n < 2:  # noqa: PLR2004
        return [0.0] * n
    delta = [(ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k]) for k in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = delta[0], delta[-1]
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0:  # extremum or flat -> zero slope
            m[k] = 0.0
        else:
            m[k] = (delta[k - 1] + delta[k]) / 2.0
    # Fritsch-Carlson limiter (circle rule)
    for k in range(n - 1):
        if delta[k] == 0.0:
            m[k] = 0.0
            m[k + 1] = 0.0
            continue
        a = m[k] / delta[k]
        b = m[k + 1] / delta[k]
        s = a * a + b * b
        if s > 9.0:  # noqa: PLR2004
            tau = 3.0 / (s**0.5)
            m[k] = tau * a * delta[k]
            m[k + 1] = tau * b * delta[k]
    return m


def hermite_eval(
    t: float, xs: Sequence[float], ys: Sequence[float], slopes: Sequence[float]
) -> float:
    """C1 cubic Hermite evaluation with flat extrapolation.

    Evaluates the cubic Hermite spline defined by knots ``(xs, ys)`` and
    tangent slopes ``slopes`` at the point ``t``.  Flat extrapolation is
    applied outside ``[xs[0], xs[-1]]``.

    A non-finite ``t`` (NaN or +-inf) is out of domain and yields ``nan``
    (the uniform cross-path sentinel). Finite ``t <= xs[0]`` is in domain and
    flat-extrapolates to ``ys[0]``.

    Args:
        t: Point at which to evaluate.
        xs: Strictly increasing knot x-coordinates.
        ys: Knot y-values, same length as ``xs``.
        slopes: Per-knot tangent slopes (e.g. from :func:`pchip_slopes`),
            same length as ``xs``.

    Returns:
        The interpolated (or extrapolated) value at ``t``.
    """
    if not math.isfinite(t):
        return math.nan
    if t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    k = bisect_right(xs, t) - 1
    h = xs[k + 1] - xs[k]
    s = (t - xs[k]) / h
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    return ys[k] * h00 + h * slopes[k] * h10 + ys[k + 1] * h01 + h * slopes[k + 1] * h11


__all__ = ["hermite_eval", "linear_interpolate", "log_df_knots", "log_linear_spot", "pchip_slopes"]
