# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Nelson-Siegel-Svensson (NSS) closed-form spot-rate evaluation (GSW eq. 22)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from gaspatchio._warning import warn

if TYPE_CHECKING:
    from collections.abc import Sequence

_EPS = 1e-8


def _loadings(x: float) -> tuple[float, float]:
    """Return the NSS loading pair for x = t/tau.

    Returns ``((1-e^-x)/x, that - e^-x)``.  Limits as x->0: ``(1, 0)``.
    """
    if x < _EPS:
        return 1.0, 0.0
    e = math.exp(-x)
    load = (1.0 - e) / x
    return load, load - e


def svensson_spot_cc(
    t: float,
    b0: float,
    b1: float,
    b2: float,
    b3: float,
    tau1: float,
    tau2: float,
) -> float:
    """Continuously-compounded NSS spot rate (GSW eq. 22).

    Implements the Nelson-Siegel-Svensson model:

    .. code-block:: text

        r_cc(t) = b0
                + b1 * L(t/tau1)
                + b2 * C(t/tau1)
                + b3 * C(t/tau2)

    where ``L(x) = (1-e^-x)/x`` and ``C(x) = L(x) - e^-x``.

    Limits:

    - ``t → 0``: ``r_cc → b0 + b1`` (short-rate)
    - ``t → ∞``: ``r_cc → b0`` (long-rate / level)

    Args:
        t: Year fraction.  Must be ``>= 0``.
        b0: Level parameter (long-run mean rate, c.c.).
        b1: Slope parameter.
        b2: First curvature parameter.
        b3: Second curvature parameter.
        tau1: First decay factor (> 0).
        tau2: Second decay factor (> 0).

    Returns:
        Continuously-compounded spot rate at ``t``.

    """
    l1, c1 = _loadings(t / tau1)
    _, c2 = _loadings(t / tau2)
    return b0 + b1 * l1 + b2 * c1 + b3 * c2


def svensson_spot(
    t: float,
    b0: float,
    b1: float,
    b2: float,
    b3: float,
    tau1: float,
    tau2: float,
) -> float:
    """Annually-compounded NSS spot rate: ``exp(r_cc(t)) - 1``.

    Wraps :func:`svensson_spot_cc` and converts from continuously-compounded
    to annually-compounded convention used throughout gaspatchio.

    A non-finite ``t`` (NaN or +-inf) is out of domain and yields ``nan``
    (the uniform cross-path sentinel); the guard runs BEFORE the closed form,
    so ``t = +inf`` does not silently return the long-rate level. Finite
    ``t <= 0`` keeps the closed form (e.g. the short-rate limit at ``t = 0``).

    Args:
        t: Year fraction.  Must be ``>= 0`` for a meaningful spot rate.
        b0: Level parameter.
        b1: Slope parameter.
        b2: First curvature parameter.
        b3: Second curvature parameter.
        tau1: First decay factor (> 0).
        tau2: Second decay factor (> 0).

    Returns:
        Annually-compounded spot rate at ``t``, or ``nan`` when ``t`` is
        non-finite.

    """
    if not math.isfinite(t):
        return math.nan
    return math.exp(svensson_spot_cc(t, b0, b1, b2, b3, tau1, tau2)) - 1.0


def _design(tenors: np.ndarray, tau1: float, tau2: float) -> np.ndarray:
    """NSS design matrix columns [1, L1, C1, C2] with vectorised t->0 limits."""

    def cols(tau: float) -> tuple[np.ndarray, np.ndarray]:
        x = tenors / tau
        small = x < _EPS
        safe_x = np.where(small, 1.0, x)
        e = np.exp(-safe_x)
        load = np.where(small, 1.0, (1.0 - e) / safe_x)
        c = np.where(small, 0.0, load - e)
        return load, c

    l1, c1 = cols(tau1)
    _, c2 = cols(tau2)
    return np.column_stack([np.ones_like(tenors), l1, c1, c2])


def _sse(t: np.ndarray, y: np.ndarray, tau1: float, tau2: float) -> float:
    phi = _design(t, tau1, tau2)
    beta, *_ = np.linalg.lstsq(phi, y, rcond=1e-12)
    return float(np.sum((y - phi @ beta) ** 2))


# The decay pairs a fit may score. Below the shortest knot, or
# where the loadings are nearly collinear at the knots, the betas are not pinned
# by the data: the curve hits every knot and reads nonsense between them.
_MIN_TAU = 0.05
_MAX_SCALED_CONDITION = 100.0


def _scaled_condition(t: np.ndarray, tau1: float, tau2: float) -> float:
    """Return the condition number of the design with unit-length columns.

    Scaling the columns first makes the number measure collinearity of the
    loadings at these knots, not the units the columns happen to be in.
    """
    phi = _design(t, tau1, tau2)
    norms = np.linalg.norm(phi, axis=0)
    if not np.all(norms > 0):
        return math.inf
    singular = np.linalg.svd(phi / norms, compute_uv=False)
    if singular[-1] <= 0:
        return math.inf
    return float(singular[0] / singular[-1])


@dataclass(frozen=True, slots=True)
class _Admissible:
    """The decay pairs a fit may score: in bounds, apart, and identifiable."""

    t: np.ndarray
    lo: float
    hi: float
    min_ratio: float
    max_condition: float

    def __call__(self, tau1: float, tau2: float) -> bool:
        """Return whether the pair ``(tau1, tau2)`` may be scored."""
        if not (self.lo <= tau1 and tau2 <= self.hi and tau2 >= tau1 * self.min_ratio):
            return False
        return _scaled_condition(self.t, tau1, tau2) <= self.max_condition


def _refine_taus(  # noqa: PLR0913
    t: np.ndarray,
    y: np.ndarray,
    tau1: float,
    tau2: float,
    admissible: _Admissible,
    *,
    rounds: int = 8,
    span: float = 0.5,
    n: int = 15,
) -> tuple[float, float]:
    """Deterministic successive log-space local-grid refinement around (tau1,tau2).

    Each round samples an n x n log-spaced window of half-width `span` around the
    current best, scores only the admissible cells, keeps the lowest-SSE one, and
    halves `span`. The start is admissible, so the result is too.
    """
    best = (_sse(t, y, tau1, tau2), tau1, tau2)
    for _ in range(rounds):
        g1 = np.exp(np.linspace(np.log(best[1]) - span, np.log(best[1]) + span, n))
        g2 = np.exp(np.linspace(np.log(best[2]) - span, np.log(best[2]) + span, n))
        for a in g1:
            for b in g2:
                if not admissible(float(a), float(b)):
                    continue
                s = _sse(t, y, float(a), float(b))
                if s < best[0]:
                    best = (s, float(a), float(b))
        span *= 0.5
    return best[1], best[2]


def fit_svensson(  # noqa: PLR0913
    tenors: Sequence[float],
    rates: Sequence[float],
    *,
    tau_lo: float | None = None,
    tau_hi: float = 30.0,
    n_grid: int = 50,
    min_ratio: float = 1.5,
    max_condition: float = _MAX_SCALED_CONDITION,
) -> dict[str, float]:
    """Fit NSS to observed continuously-compounded zero rates; return the 6 params.

    Separable NLS: a 2-D log-spaced grid over the admissible decay pairs with an
    inner OLS for the betas, scored by residual SSE, then a deterministic local
    refine over the same pairs. A pair is admissible when tau1 is at or
    above the shortest tenor, tau2 is at most ``tau_hi`` and at least
    ``min_ratio`` times tau1, and the design with unit-length columns has a
    condition number of at most ``max_condition``. Params are non-unique, so the
    fit targets CURVE VALUES, not specific betas.

    Args:
        tenors: Tenor knot points in years (>= 6 required).
        rates: Continuously-compounded zero rates at each tenor.
        tau_lo: Lower bound for tau1; the shortest tenor when not given.
        tau_hi: Upper bound for the tau grid search.
        n_grid: Number of grid points per tau dimension.
        min_ratio: Minimum ratio tau2/tau1 to enforce separation.
        max_condition: Largest condition number of the column-scaled design a
            scored pair may have.

    Returns:
        Dict with keys ``b0``, ``b1``, ``b2``, ``b3``, ``tau1``, ``tau2``.

    Raises:
        ValueError: If fewer than 6 observations are supplied, or if no decay
            pair is admissible for these tenors.

    """
    t = np.asarray(tenors, dtype=float)
    y = np.asarray(rates, dtype=float)
    _min_obs = 6
    if t.size < _min_obs:
        msg = f"fit_svensson needs >=6 observations; got {t.size}"
        raise ValueError(msg)
    lo = max(float(t.min()), _MIN_TAU) if tau_lo is None else tau_lo
    admissible = _Admissible(
        t=t, lo=lo, hi=tau_hi, min_ratio=min_ratio, max_condition=max_condition
    )
    best: tuple[float, float, float] | None = None
    if lo < tau_hi:
        grid = np.geomspace(lo, tau_hi, n_grid)
        for cand1 in grid:
            for cand2 in grid[grid > cand1 * min_ratio]:
                if not admissible(float(cand1), float(cand2)):
                    continue
                s = _sse(t, y, float(cand1), float(cand2))
                if best is None or s < best[0]:
                    best = (s, float(cand1), float(cand2))
    if best is None:
        msg = (
            f"Curve.fit_svensson cannot pin the curve's decay parameters from "
            f"knots spanning {float(t.min()):g} to {float(t.max()):g} years: "
            "with decay parameters no shorter than the shortest knot, every pair "
            "leaves the curve's loadings nearly collinear at these knots, so the "
            "fitted rates between them would not be reliable. Add knots over a "
            "wider span of tenors, fit the knots exactly with "
            "Curve.fit_smith_wilson, or build the curve from published parameters "
            "with Curve.from_svensson."
        )
        raise ValueError(msg)
    tau1, tau2 = _refine_taus(t, y, best[1], best[2], admissible)
    phi = _design(t, tau1, tau2)
    beta, *_ = np.linalg.lstsq(phi, y, rcond=1e-12)
    b0, b1, b2, b3 = (float(v) for v in beta)
    if b0 <= 0 or b0 + b1 <= 0:
        warn(
            f"The Svensson fit gave b0={b0} and b0+b1={b0 + b1}; at least one "
            "is not positive, so the curve's long-run rate or its short-rate "
            "limit is not positive. Check the input rates (a negative-rate "
            "regime?)."
        )
    return {
        "b0": b0,
        "b1": b1,
        "b2": b2,
        "b3": b3,
        "tau1": float(tau1),
        "tau2": float(tau2),
    }
