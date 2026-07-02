# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Classic Solvency II Smith-Wilson zero-coupon extrapolation."""

from __future__ import annotations

import math

import numpy as np
from loguru import logger


def sw_heart(u: np.ndarray, v: np.ndarray, alpha: float) -> np.ndarray:
    """Wilson 'heart' H(u,v) (min/max-free vectorised form, matches lifelib).

    Args:
        u: First tenor array (shape ``(m,)``). Broadcasted to ``(m, 1)``.
        v: Second tenor array (shape ``(n,)``). Broadcasted to ``(1, n)``.
        alpha: Mean-reversion speed (> 0).

    Returns:
        Matrix of shape ``(m, n)`` with ``H(u_i, v_j)`` entries.
    """
    u = u[:, None]
    v = v[None, :]
    return 0.5 * (
        alpha * (u + v)
        + np.exp(-alpha * (u + v))
        - alpha * np.abs(u - v)
        - np.exp(-alpha * np.abs(u - v))
    )


def solve_zeta(u: np.ndarray, r: np.ndarray, ufr: float, alpha: float) -> np.ndarray:
    """Solve W @ zeta = m - mu for the Wilson weights (zero-coupon inputs).

    The linear system is:
    ``W @ zeta = m - mu``
    where ``mu_i = exp(-omega * u_i)``, ``m_i = (1 + r_i)^{-u_i}``,
    and ``W_{ij} = mu_i * H(u_i, u_j) * mu_j``.

    Args:
        u: Tenor knots in years (shape ``(n,)``). Must be positive.
        r: Annually-compounded zero rates at each knot (shape ``(n,)``).
        ufr: Ultimate forward rate (annual, e.g. ``0.04`` for 4 %). Must be > -1.
        alpha: Mean-reversion speed. Must be > 0.

    Returns:
        Weight vector ``zeta`` of shape ``(n,)`` to pass to :func:`sw_price` /
        :func:`sw_spot`.
    """
    omega = np.log(1.0 + ufr)
    mu = np.exp(-omega * u)
    m = (1.0 + r) ** (-u)
    h = sw_heart(u, u, alpha)
    w = mu[:, None] * h * mu[None, :]
    cond = float(np.linalg.cond(w))
    if cond > 1e10:  # noqa: PLR2004
        logger.warning(
            "smith_wilson: W is ill-conditioned (cond={:.2e}); knots too close?", cond
        )
    return np.linalg.solve(w, m - mu)


def sw_price(
    t: np.ndarray, u: np.ndarray, zeta: np.ndarray, omega: float, alpha: float
) -> np.ndarray:
    """Zero-coupon price P(t) = e^{-omega t} + sum_j zeta_j W(t,u_j).

    Args:
        t: Evaluation tenors in years (shape ``(k,)``). Must be positive.
        u: Tenor knots used when solving for ``zeta`` (shape ``(n,)``).
        zeta: Wilson weights from :func:`solve_zeta` (shape ``(n,)``).
        omega: Log of (1 + UFR) — must equal ``log(1 + ufr)`` used in the solve.
        alpha: Mean-reversion speed (same value as in the solve).

    Returns:
        Zero-coupon prices at ``t``, shape ``(k,)``.
    """
    t = np.atleast_1d(np.asarray(t, dtype=float))
    h = sw_heart(t, u, alpha)
    w = np.exp(-omega * (t[:, None] + u[None, :])) * h
    return np.exp(-omega * t) + w @ zeta


def _gap(
    u: np.ndarray, r: np.ndarray, ufr: float, alpha: float, cp: float
) -> float | None:
    """Signed gap (forward intensity at CP minus omega). None if P(CP) <= 0 (a pole).

    Args:
        u: Tenor knots in years (shape ``(n,)``).
        r: Annually-compounded zero rates at each knot (shape ``(n,)``).
        ufr: Ultimate forward rate (annual).
        alpha: Mean-reversion speed candidate.
        cp: Convergence point in years.

    Returns:
        Signed gap ``fwd(CP) - omega``, or ``None`` if the discount factor at CP
        is non-positive (singularity / negative-DF pathology — reject this alpha).

    """
    omega = np.log(1.0 + ufr)
    zeta = solve_zeta(u, r, ufr, alpha)
    p_cp = float(sw_price(np.array([cp]), u, zeta, omega, alpha)[0])
    if p_cp <= 0:
        return None  # singularity / negative discount factor -> reject this alpha
    eps = 1e-4
    p2 = float(sw_price(np.array([cp + eps]), u, zeta, omega, alpha)[0])
    fwd = -(np.log(p2) - np.log(p_cp)) / eps  # instantaneous forward intensity at CP
    return fwd - omega


def calibrate_alpha(  # noqa: PLR0913
    u: np.ndarray,
    r: np.ndarray,
    *,
    ufr: float,
    llp: float,
    tol: float = 1e-4,
    lo: float = 0.05,
    hi: float = 1.0,
    steps: int = 96,
) -> float:
    """Smallest alpha >= 0.05 such that |forward(CP) - omega| <= 1bp (EIOPA).

    Convergence point: ``CP = max(LLP + 40, 60)``.

    Smallest-first scan over ``[lo, hi]``; skips alphas where ``P(CP) <= 0`` (the
    g(alpha) poles, which also reject the negative-DF pathology).  Falls back to the
    alpha with the smallest ``|gap|`` if none meets ``tol``.

    Args:
        u: Tenor knots in years (shape ``(n,)``).
        r: Annually-compounded zero rates at each knot (shape ``(n,)``).
        ufr: Ultimate forward rate (annual).
        llp: Last Liquid Point in years. Convergence point is ``max(llp + 40, 60)``.
        tol: Convergence tolerance in forward-intensity units (default 1e-4 = 1 bp).
        lo: Lower bound of the alpha search grid (inclusive, default 0.05).
        hi: Upper bound of the alpha search grid (inclusive, default 1.0).
        steps: Number of grid points to test (default 96).

    Returns:
        Calibrated alpha satisfying the EIOPA convergence criterion.

    Raises:
        ValueError: If all candidate alphas produce a singular / negative discount
            factor at the convergence point.

    """
    cp = max(llp + 40.0, 60.0)
    grid = np.linspace(lo, hi, steps)
    for a in grid:  # smallest-first
        g = _gap(u, r, ufr, float(a), cp)
        if g is not None and abs(g) <= tol:
            return float(a)
    cand = [
        (abs(g), float(a))
        for a in grid
        if (g := _gap(u, r, ufr, float(a), cp)) is not None
    ]
    if not cand:
        msg = "smith_wilson: alpha calibration failed (all candidates singular)"
        raise ValueError(msg)
    return min(cand)[1]


def sw_spot(t: float, u: np.ndarray, zeta: np.ndarray, omega: float, alpha: float) -> float:
    """Annually-compounded spot rate r(t) = P(t)^{-1/t} - 1 (requires t > 0).

    The spot rate ``P(t)^(-1/t) - 1`` is undefined at ``t = 0`` and meaningless
    for ``t < 0``; any non-finite ``t`` (NaN or +-inf) or ``t <= 0`` is out of
    domain and yields ``nan`` (the uniform cross-path sentinel). The guard runs
    BEFORE pricing, so ``t = +inf`` does not silently propagate through the
    Wilson heart.

    Args:
        t: Evaluation tenor in years. Must be strictly positive.
        u: Tenor knots used when solving for ``zeta`` (shape ``(n,)``).
        zeta: Wilson weights from :func:`solve_zeta` (shape ``(n,)``).
        omega: Log of (1 + UFR) — must equal ``log(1 + ufr)`` used in the solve.
        alpha: Mean-reversion speed (same value as in the solve).

    Returns:
        Annually-compounded spot rate at ``t``, or ``nan`` when ``t`` is
        non-finite or ``t <= 0``.
    """
    if not math.isfinite(t) or t <= 0.0:
        return math.nan
    p = float(sw_price(np.array([t]), u, zeta, omega, alpha)[0])
    return p ** (-1.0 / t) - 1.0
