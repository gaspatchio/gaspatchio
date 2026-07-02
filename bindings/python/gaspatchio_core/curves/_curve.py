# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed Curve term-structure primitive.

A Curve carries a discrete grid of (tenor, zero_rate) knots plus a day-count
convention. Accessors (:meth:`spot_rate`, :meth:`discount_factor`,
:meth:`forward_rate`) interpolate over the grid and accept ``float``,
``list[float]``, ``np.ndarray``, ``pl.Series``, or ``pl.Expr`` inputs,
returning matching shapes.

Capabilities:
  - Static curves only (literal Python list knots at construction).
    Per-row column curves are not yet implemented.
  - Linear interpolation on rates (``'linear'``) or linear interpolation in
    log-discount-factor space (``'log_linear'``); flat extrapolation outside
    the knot range.
  - Default day-count: ``ActualActualISDA``.
  - Constructors: ``from_zero_rates``, ``from_par_rates`` (bootstrap).
  - Stress: ``shift_parallel(bps)``, ``key_rate_shift(tenor, bps)``.
"""

from __future__ import annotations

import hashlib
import math
import warnings
from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict

import numpy as np
import numpy.typing as npt
import polars as pl

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.curves._interpolation import (
    hermite_eval,
    linear_interpolate,
    log_df_knots,
    log_linear_spot,
    pchip_slopes,
)
from gaspatchio_core.curves._smith_wilson import calibrate_alpha, solve_zeta, sw_spot
from gaspatchio_core.curves._svensson import fit_svensson, svensson_spot
from gaspatchio_core.schedule._day_count import ActualActualISDA, DayCount

# Input/output type union for accessors. Implementation dispatches on
# the concrete type at call time and returns a matching shape.
TimeInput = float | int | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr

InterpolationMethod = Literal["linear", "log_linear", "pchip"]


class _KernelKwargs(TypedDict):
    """Typed keyword payload for the ``curve_eval`` plugin.

    ``method`` is always present; every other key is method-specific and
    optional, mirroring ``curve_eval``'s keyword-with-default signature so the
    ``**self._kernel_kwargs()`` splat type-checks.
    """

    method: str
    xs: NotRequired[list[float] | None]
    ys: NotRequired[list[float] | None]
    slopes: NotRequired[list[float] | None]
    extrapolation: NotRequired[str]
    b0: NotRequired[float | None]
    b1: NotRequired[float | None]
    b2: NotRequired[float | None]
    b3: NotRequired[float | None]
    tau1: NotRequired[float | None]
    tau2: NotRequired[float | None]
    u: NotRequired[list[float] | None]
    zeta: NotRequired[list[float] | None]
    omega: NotRequired[float | None]
    alpha: NotRequired[float | None]


@dataclass(frozen=True, slots=True)
class ParametricPayload:
    """Closed-form parametric curve payload.

    Supports ``kind="svensson"`` (Nelson-Siegel-Svensson, GSW eq. 22) and
    ``kind="smith_wilson"`` (classic Solvency II Smith-Wilson extrapolation).

    Svensson fields (``b0``–``b3``, ``tau1``, ``tau2``) are ``None`` for
    Smith-Wilson curves; Smith-Wilson fields (``u``, ``zeta``, ``omega``,
    ``alpha``) are ``None`` for Svensson curves.

    Attributes:
        kind: Parametric model identifier.
        b0: NSS level parameter (Svensson only).
        b1: NSS slope parameter (Svensson only).
        b2: NSS first curvature parameter (Svensson only).
        b3: NSS second curvature parameter (Svensson only).
        tau1: NSS first decay factor > 0 (Svensson only).
        tau2: NSS second decay factor > 0 (Svensson only).
        u: Tenor knots used in the Wilson solve (Smith-Wilson only).
        zeta: Wilson weight vector from ``solve_zeta`` (Smith-Wilson only).
        omega: ``log(1 + UFR)`` — the continuously-compounded UFR (Smith-Wilson only).
        alpha: Mean-reversion speed (Smith-Wilson only).
    """

    kind: Literal["svensson", "smith_wilson"]
    # Svensson / NSS fields
    b0: float = 0.0
    b1: float = 0.0
    b2: float = 0.0
    b3: float = 0.0
    tau1: float = 1.0
    tau2: float = 1.0
    # Smith-Wilson fields
    u: tuple[float, ...] | None = None
    zeta: tuple[float, ...] | None = None
    omega: float | None = None
    alpha: float | None = None


@dataclass(frozen=True)
class Curve:
    """Typed term-structure curve.

    Construct via :meth:`from_zero_rates` or :meth:`from_par_rates`. Direct
    construction is intentionally awkward — use the classmethods.
    """

    tenors: tuple[float, ...]
    rates: tuple[float, ...]
    day_count: DayCount
    interpolation: InterpolationMethod = field(default="linear")
    parametric: ParametricPayload | None = field(default=None)

    @classmethod
    def from_zero_rates(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        day_count: DayCount | None = None,
        interpolation: InterpolationMethod = "linear",
    ) -> Curve:
        """Build a Curve from zero (spot) rates indexed by tenor in years.

        The standard entry point for knot-based discount curves. Supply market
        zero rates at a set of liquid tenor points and choose an interpolation
        method; the curve fills in rates at any intermediate tenor on demand.

        When to use: whenever you have a published zero-rate curve (e.g. a
        government bond spot curve or swap zero curve) and need to discount
        projected cashflows at each projection step. For parametric curves from
        central-bank model outputs, use :meth:`from_svensson` instead.

        ``tenors`` and ``rates`` must have the same length, with ``tenors``
        strictly increasing and at least two knots present.

        Args:
            tenors: Tenor knot points in years, strictly increasing.
            rates: Annually-compounded zero rates at each knot point, same
                length as ``tenors``.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
                Recorded for identity / ``source_sha`` only — it does not affect
                rate evaluation.
            interpolation: Interpolation method; ``'linear'`` (default),
                ``'log_linear'`` (linear in log-discount-factor space, better
                for preserving positivity of discount factors), or ``'pchip'``
                (shape-preserving cubic Hermite, smoother forward rates).

        Returns:
            A frozen :class:`Curve` instance.

        Raises:
            ValueError: If ``tenors`` and ``rates`` differ in length, fewer
                than 2 knots are supplied, tenors are not strictly increasing,
                or an unsupported interpolation method is requested.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03]
            ... )
            >>> c.tenors
            (1.0, 5.0, 10.0)
            >>> c.interpolation
            'linear'

            PCHIP interpolation produces smoother forward rates between knots:

            >>> c_pchip = Curve.from_zero_rates(
            ...     tenors=[1, 2, 5, 10], rates=[0.01, 0.02, 0.03, 0.035],
            ...     interpolation="pchip",
            ... )
            >>> c_pchip.spot_rate(3.5)  # doctest: +ELLIPSIS
            0.0266...
            >>> c_pchip.discount_factor([1.0, 5.0])  # doctest: +ELLIPSIS
            [0.990..., 0.862...]

        """
        if len(tenors) != len(rates):
            msg = (
                f"tenors and rates must have the same length; "
                f"got {len(tenors)} and {len(rates)}"
            )
            raise ValueError(msg)
        _min_knots = 2
        if len(tenors) < _min_knots:
            msg = f"at least 2 knots required; got {len(tenors)}"
            raise ValueError(msg)
        for i in range(1, len(tenors)):
            if tenors[i] <= tenors[i - 1]:
                msg = f"tenors must be strictly increasing; got {tenors}"
                raise ValueError(msg)
        _supported = {"linear", "log_linear", "pchip"}
        if interpolation not in _supported:
            msg = (
                f"unsupported interpolation {interpolation!r}; "
                f"supported methods are {sorted(_supported)}"
            )
            raise ValueError(msg)
        return cls(
            tenors=tuple(tenors),
            rates=tuple(rates),
            day_count=day_count or ActualActualISDA(),
            interpolation=interpolation,
        )

    @classmethod
    def from_svensson(
        cls,
        *,
        b0: float,
        b1: float,
        b2: float,
        b3: float,
        tau1: float,
        tau2: float,
        day_count: DayCount | None = None,
    ) -> Curve:
        """Build a Curve from Nelson-Siegel-Svensson (NSS) parameters.

        Implements GSW eq. 22. The curve is closed-form and does not require
        knot points — the parametric model is evaluated directly at any tenor.

        When to use: when you have published Nelson-Siegel-Svensson parameters
        (e.g. from the US Federal Reserve GSW model, ECB, or central bank
        yield-curve publication) and want to build a smooth closed-form curve
        without supplying individual knot rates.  The curve evaluates the NSS
        formula directly at any tenor — no interpolation is performed and no
        knot boundary is encountered, so extrapolation to very long tenors
        (50+ years) is well-behaved.

        Args:
            b0: Level parameter (long-run continuously-compounded rate). Must
                satisfy ``b0 > 0`` for a positive long-run rate in most
                regimes (a warning is emitted if not, but not raised — negative
                rate regimes are valid in ZIRP/NIRP environments).
            b1: Slope parameter. ``b0 + b1`` is the short-rate limit.
            b2: First curvature parameter.
            b3: Second curvature parameter.
            tau1: First decay factor in years. Must be strictly positive.
            tau2: Second decay factor in years. Must be strictly positive.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
                Recorded for identity / ``source_sha`` only — it does not affect
                rate evaluation.

        Returns:
            A frozen :class:`Curve` with parametric dispatch enabled.

        Raises:
            ValueError: If ``tau1 <= 0`` or ``tau2 <= 0``.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> nss = Curve.from_svensson(
            ...     b0=0.040, b1=-0.010, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0
            ... )
            >>> nss.parametric is not None
            True
            >>> nss.parametric.kind
            'svensson'
            >>> nss.spot_rate(7.5)  # doctest: +ELLIPSIS
            0.0402...
            >>> nss.spot_rate(50)  # doctest: +ELLIPSIS
            0.0410...

        """
        if tau1 <= 0.0:
            msg = f"tau1 must be strictly positive; got {tau1}"
            raise ValueError(msg)
        if tau2 <= 0.0:
            msg = f"tau2 must be strictly positive; got {tau2}"
            raise ValueError(msg)
        if b0 <= 0.0:
            warnings.warn(
                f"Svensson b0={b0} is non-positive; long-run rate will be non-positive.",
                UserWarning,
                stacklevel=2,
            )
        elif b0 + b1 <= 0.0:
            warnings.warn(
                f"Svensson b0+b1={b0 + b1} is non-positive; short-rate limit will be"
                " non-positive.",
                UserWarning,
                stacklevel=2,
            )
        payload = ParametricPayload(
            kind="svensson",
            b0=b0,
            b1=b1,
            b2=b2,
            b3=b3,
            tau1=tau1,
            tau2=tau2,
        )
        return cls(
            tenors=(),
            rates=(),
            day_count=day_count or ActualActualISDA(),
            interpolation="linear",  # unused for parametric; kept for dataclass compat
            parametric=payload,
        )

    @classmethod
    def fit_svensson(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        day_count: DayCount | None = None,
    ) -> Curve:
        """Fit an NSS curve to observed annually-compounded zero rates.

        Uses separable nonlinear least squares (inner OLS over betas for each
        candidate tau pair, scored by residual SSE) to recover NSS parameters
        from market data. The fit is performed in continuously-compounded space
        (linear in the betas), so annual rates are converted to CC before
        fitting and the stored params are CC params consistent with
        :func:`~gaspatchio_core.curves._svensson.svensson_spot_cc`.

        The source ``tenors`` and ``rates`` (annual inputs) are stored on the
        curve for provenance so that :meth:`canonical_form` / :meth:`source_sha`
        reflect the actual fitted data. Evaluation always dispatches through the
        NSS parametric payload, not the stored knots.

        When to use: when you have a set of observed zero rates from market data
        (e.g. treasury strips, swap zero rates, or bootstrapped par-rate data)
        and want a smooth parametric curve rather than a piecewise interpolation.
        Requires at least 6 observations to identify all 6 NSS parameters. For
        curves where you already have official published NSS parameters (e.g.
        central-bank fitted curves), use :meth:`from_svensson` directly.

        Args:
            tenors: Tenor knot points in years. Must have ``>= 6`` elements.
            rates: Annually-compounded zero rates at each tenor. Same length
                as ``tenors``.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
                Recorded for identity / ``source_sha`` only — it does not affect
                rate evaluation.

        Returns:
            A frozen :class:`Curve` with parametric dispatch enabled. The
            curve's ``tenors`` and ``rates`` fields hold the source annual
            observations for provenance; ``parametric`` holds the fitted CC
            NSS parameters.

        Raises:
            ValueError: If ``tenors`` and ``rates`` differ in length, or
                fewer than 6 observations are supplied.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> nss = Curve.fit_svensson(
            ...     tenors=[1, 2, 5, 10, 20, 30],
            ...     rates=[0.030, 0.032, 0.035, 0.038, 0.040, 0.041],
            ... )
            >>> nss.parametric is not None
            True
            >>> nss.spot_rate(10.0)  # doctest: +ELLIPSIS
            0.037...

        """
        if len(tenors) != len(rates):
            msg = (
                f"tenors and rates must have the same length; "
                f"got {len(tenors)} and {len(rates)}"
            )
            raise ValueError(msg)
        _min_obs = 6
        if len(tenors) < _min_obs:
            msg = f"fit_svensson needs >=6 observations; got {len(tenors)}"
            raise ValueError(msg)
        # Convert annually-compounded rates to continuously-compounded for the fit.
        # CC space is linear in the NSS betas — makes the inner OLS exact.
        cc = [math.log(1.0 + r) for r in rates]
        params = fit_svensson(tenors, cc)
        payload = ParametricPayload(
            kind="svensson",
            b0=params["b0"],
            b1=params["b1"],
            b2=params["b2"],
            b3=params["b3"],
            tau1=params["tau1"],
            tau2=params["tau2"],
        )
        # Store source annual tenors/rates for provenance (canonical_form/source_sha).
        # Eval dispatches on parametric (not knots) because parametric is not None.
        return cls(
            tenors=tuple(tenors),
            rates=tuple(rates),
            day_count=day_count or ActualActualISDA(),
            interpolation="linear",  # unused for parametric; kept for dataclass compat
            parametric=payload,
        )

    @classmethod
    def fit_smith_wilson(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        ufr: float = 0.033,
        llp: float | None = None,
        alpha: float | None = None,
        day_count: DayCount | None = None,
    ) -> Curve:
        """Fit a classic Solvency II Smith-Wilson curve to zero-coupon market rates.

        Solves the linear system ``W @ zeta = m - mu`` (see
        :mod:`~gaspatchio_core.curves._smith_wilson`) for the Wilson weights
        ``zeta`` and stores the result as a ``ParametricPayload``.  Subsequent
        evaluation via :meth:`spot_rate` dispatches to either the Rust kernel
        (for ``pl.Expr`` / list-column inputs) or the Python closed form (for
        scalar / array inputs), both using the same precomputed
        ``(u, zeta, omega, alpha)``.

        The ``omega = log(1 + ufr)`` is computed once here and carried in the
        payload to guarantee that the value used during the solve and the value
        used during evaluation are identical.

        Near-duplicate tenors within 1/12 year (~1 month) of the previously-
        kept tenor are dropped (first of the pair wins) after sorting.

        When to use: the standard EIOPA-mandated Solvency II extrapolation
        method for EUR, GBP, and other major currencies where the risk-free
        term structure must be extended beyond the Last Liquid Point (LLP)
        toward the Ultimate Forward Rate (UFR). Pass your liquid market zero
        rates (up to and including the LLP) and let alpha auto-calibrate to
        the EIOPA convergence criterion. The 2026 EIOPA FSP/LLFR alternative
        extrapolation is a planned future method (see roadmap).

        Args:
            tenors: Tenor knot points in years. Must be > 0 and contain at
                least 1 unique tenor after de-duplication.
            rates: Annually-compounded zero rates at each tenor. Same length
                as ``tenors``.
            ufr: Ultimate forward rate (annual, e.g. ``0.04`` for 4 %).
                Must satisfy ``ufr > -1``. Defaults to ``0.033`` (EIOPA 2026
                long-term average).
            llp: Last Liquid Point in years. Used as the anchor for the EIOPA
                convergence-point ``CP = max(llp + 40, 60)`` when
                ``alpha=None``. Defaults to ``max(tenors)`` when ``None``.
            alpha: Mean-reversion speed. Must be ``>= 0.05``. If ``None``,
                alpha is calibrated automatically using the EIOPA convergence
                criterion: smallest alpha in [0.05, 1.0] such that the
                instantaneous forward rate at the convergence point is within
                1 bp of omega.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
                Recorded for identity / ``source_sha`` only — it does not affect
                rate evaluation.

        Returns:
            A frozen :class:`Curve` with parametric Smith-Wilson dispatch
            enabled. The ``tenors`` and ``rates`` fields hold the
            de-duplicated source observations for provenance.

        Raises:
            ValueError: If ``ufr <= -1``, ``alpha < 0.05``, or ``tenors``
                and ``rates`` differ in length.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> sw = Curve.fit_smith_wilson(
            ...     tenors=[1, 2, 3, 5, 7, 10, 15, 20],
            ...     rates=[0.031, 0.033, 0.034, 0.036, 0.038, 0.040, 0.041, 0.042],
            ... )
            >>> sw.spot_rate(20.0)  # doctest: +ELLIPSIS
            0.042...
            >>> sw.spot_rate(60.0)  # doctest: +ELLIPSIS
            0.037...

        """
        if ufr <= -1.0:
            msg = f"ufr must be > -1; got {ufr}"
            raise ValueError(msg)
        if len(tenors) != len(rates):
            msg = (
                f"tenors and rates must have the same length; "
                f"got {len(tenors)} and {len(rates)}"
            )
            raise ValueError(msg)

        # Sort by tenor then de-duplicate: drop any tenor within 1/12 year of
        # the previously-kept tenor (keep the first of a near-duplicate pair).
        _dedup_gap = 1.0 / 12.0
        pairs = sorted(zip(tenors, rates, strict=True), key=lambda p: p[0])
        deduped: list[tuple[float, float]] = []
        for tenor, rate in pairs:
            if deduped and (tenor - deduped[-1][0]) < _dedup_gap:
                continue
            deduped.append((tenor, rate))

        u_arr = np.array([p[0] for p in deduped], dtype=float)
        r_arr = np.array([p[1] for p in deduped], dtype=float)

        _alpha_min = 0.05
        if alpha is None:
            effective_llp = llp if llp is not None else float(u_arr.max())
            alpha = calibrate_alpha(u_arr, r_arr, ufr=ufr, llp=effective_llp)
        elif alpha < _alpha_min:
            msg = f"alpha must be >= {_alpha_min}; got {alpha}"
            raise ValueError(msg)

        omega = float(np.log(1.0 + ufr))
        zeta_arr = solve_zeta(u_arr, r_arr, ufr, alpha)

        payload = ParametricPayload(
            kind="smith_wilson",
            u=tuple(float(v) for v in u_arr),
            zeta=tuple(float(v) for v in zeta_arr),
            omega=omega,
            alpha=float(alpha),
        )
        return cls(
            tenors=tuple(float(v) for v in u_arr),
            rates=tuple(float(v) for v in r_arr),
            day_count=day_count or ActualActualISDA(),
            interpolation="linear",  # unused for parametric; kept for dataclass compat
            parametric=payload,
        )

    def spot_rate(
        self,
        t: TimeInput,
    ) -> float | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr:
        """Spot zero rate at year fraction(s) ``t``.

        Dispatches on the concrete type of ``t`` and returns a matching shape:
        scalar in → scalar out, list in → list out, ndarray in → ndarray out,
        Series in → Series out, Expr in → Expr out.

        Supported domain is ``t > 0`` for ``log_linear`` and ``smith_wilson``
        (the spot rate ``P(t)^(-1/t) - 1`` is undefined at ``t = 0``); for those
        methods an out-of-domain ``t <= 0`` yields ``NaN``. For any method, a
        non-finite ``t`` (NaN or ±inf) yields ``NaN``. The same ``NaN`` sentinel
        is returned identically across every path and container (scalar / list /
        ndarray / Series / Expr).

        Args:
            t: Year fraction(s) at which to evaluate the spot rate. Accepts
                ``float``, ``int``, ``list[float]``, ``np.ndarray``,
                ``pl.Series``, or ``pl.Expr``.

        Returns:
            The interpolated spot zero rate(s). Return type matches input type.

        Raises:
            TypeError: If ``t`` is not one of the supported types.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03]
            ... )
            >>> c.spot_rate(1.0)
            0.03
            >>> c.spot_rate([1.0, 5.0])
            [0.03, 0.03]

            For list-column projection data use the ``pl.Expr`` path — the Rust
            kernel evaluates all tenors in one pass, with no Python-level loop:

            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> from gaspatchio_core.curves import Curve
            >>> c2 = Curve.from_zero_rates(tenors=[1, 5, 10], rates=[0.01, 0.02, 0.03])
            >>> af = ActuarialFrame(pl.DataFrame({"t": [[1.0, 5.0, 10.0]]}))
            >>> af.r = c2.spot_rate(af["t"])
            >>> af.collect()["r"].to_list()[0]  # doctest: +ELLIPSIS
            [0.01..., 0.02..., 0.03...]

        """
        # Duck-type ColumnProxy / ExpressionProxy (af["t"], af["a"] + af["b"]) →
        # treat as a pl.Expr. Lets actuary-facing `af["t"]` flow into curve calls.
        to_expr = getattr(t, "_to_expr", None)
        if callable(to_expr):
            return self.spot_rate(to_expr())
        if isinstance(t, (int, float)):
            return self._eager_spot(float(t))
        if isinstance(t, list):
            return [self._eager_spot(float(x)) for x in t]
        if isinstance(t, np.ndarray):
            return np.array([self._eager_spot(float(x)) for x in t])
        if isinstance(t, pl.Series):
            return pl.Series(
                name=t.name,
                values=[self._eager_spot(float(x)) for x in t.to_list()],
                dtype=pl.Float64,
            )
        if isinstance(t, pl.Expr):
            from gaspatchio_core.functions.vector import curve_eval

            return curve_eval(t, **self._kernel_kwargs())

        msg = f"unsupported t type: {type(t).__name__}"
        raise TypeError(msg)

    def _kernel_kwargs(self) -> _KernelKwargs:
        """Return ``curve_eval`` kwargs matching this curve's method.

        Handles both parametric (svensson) and knot-based (linear, log_linear,
        pchip) curves.  Used by both the ``spot_rate`` and ``discount_factor``
        Expr branches so a single change here propagates to all Expr paths.
        """
        if self.parametric is not None and self.parametric.kind == "svensson":
            p = self.parametric
            return {
                "method": "svensson",
                "b0": p.b0,
                "b1": p.b1,
                "b2": p.b2,
                "b3": p.b3,
                "tau1": p.tau1,
                "tau2": p.tau2,
            }
        if self.parametric is not None and self.parametric.kind == "smith_wilson":
            p = self.parametric
            return {
                "method": "smith_wilson",
                "u": list(p.u) if p.u is not None else [],
                "zeta": list(p.zeta) if p.zeta is not None else [],
                "omega": p.omega,
                "alpha": p.alpha,
            }
        if self.interpolation == "linear":
            return {
                "method": "linear",
                "xs": list(self.tenors),
                "ys": list(self.rates),
                "extrapolation": "flat",
            }
        if self.interpolation == "log_linear":
            return {
                "method": "log_linear",
                "xs": list(self.tenors),
                "ys": log_df_knots(self.tenors, self.rates),
                "extrapolation": "flat",
            }
        if self.interpolation == "pchip":
            return {
                "method": "pchip",
                "xs": list(self.tenors),
                "ys": list(self.rates),
                "slopes": pchip_slopes(self.tenors, self.rates),
                "extrapolation": "flat",
            }
        msg = f"unsupported curve method for kernel: {self.interpolation}"
        raise ValueError(msg)

    def _eager_spot(self, t: float) -> float:
        """Spot rate as a scalar float, dispatching on curve type and method."""
        if self.parametric is not None and self.parametric.kind == "svensson":
            p = self.parametric
            return svensson_spot(t, p.b0, p.b1, p.b2, p.b3, p.tau1, p.tau2)
        if self.parametric is not None and self.parametric.kind == "smith_wilson":
            p = self.parametric
            return sw_spot(
                t,
                np.asarray(p.u, dtype=float),
                np.asarray(p.zeta, dtype=float),
                float(p.omega),  # type: ignore[arg-type]
                float(p.alpha),  # type: ignore[arg-type]
            )
        if self.interpolation == "log_linear":
            return log_linear_spot(t, self.tenors, log_df_knots(self.tenors, self.rates))
        if self.interpolation == "pchip":
            return hermite_eval(t, self.tenors, self.rates, pchip_slopes(self.tenors, self.rates))
        return linear_interpolate(t, self.tenors, self.rates)

    def _scalar_spot(self, t: float) -> float:
        """Spot rate as a scalar float, bypassing dispatch (public compatibility alias)."""
        return self._eager_spot(t)

    def discount_factor(
        self,
        t: TimeInput,
    ) -> float | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr:
        """Annually compounded discount factor: ``DF(t) = (1 + r(t))^(-t)``.

        Discounting is annually compounded; continuously compounded
        (``exp(-r*t)``) is not yet supported. Two curves with identical
        rate grids but different compounding frequencies would produce
        meaningfully different DFs — the choice is canonical and not
        user-configurable.

        Supported domain is ``t > 0`` for ``log_linear`` and ``smith_wilson``;
        for those methods an out-of-domain ``t <= 0`` yields ``NaN``. For any
        method, a non-finite ``t`` (NaN or ±inf) yields ``NaN`` — the out-of-domain
        rate propagates through ``(1 + NaN)^(-t) = NaN``.

        Args:
            t: Year fraction(s) at which to evaluate the discount factor.
                Accepts ``float``, ``int``, ``list[float]``, ``np.ndarray``,
                ``pl.Series``, or ``pl.Expr``.

        Returns:
            The discount factor(s). Return type matches input type.

        Raises:
            TypeError: If ``t`` is not one of the supported types.

        Examples:
            >>> from gaspatchio_core.curves import Curve
            >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.03])
            >>> c.discount_factor(1.0)  # doctest: +ELLIPSIS
            0.970873...
            >>> c.discount_factor([1.0, 2.0])  # doctest: +ELLIPSIS
            [0.970873..., 0.942595...]

            For list-column projection data use the ``pl.Expr`` path — the Rust
            kernel evaluates all tenors in one pass, with no Python-level loop:

            >>> import polars as pl
            >>> from gaspatchio_core import ActuarialFrame
            >>> from gaspatchio_core.curves import Curve
            >>> c2 = Curve.from_zero_rates(tenors=[1, 5, 10], rates=[0.01, 0.02, 0.03])
            >>> af = ActuarialFrame(pl.DataFrame({"t": [[1.0, 5.0, 10.0]]}))
            >>> af.df = c2.discount_factor(af["t"])
            >>> af.collect()["df"].to_list()[0]  # doctest: +ELLIPSIS
            [0.990..., 0.905..., 0.7...]

        """
        # Duck-type ColumnProxy / ExpressionProxy → treat as a pl.Expr.
        to_expr = getattr(t, "_to_expr", None)
        if callable(to_expr):
            return self.discount_factor(to_expr())
        if isinstance(t, (int, float)):
            r = self._scalar_spot(float(t))
            return float((1.0 + r) ** (-float(t)))

        if isinstance(t, list):
            return [float((1.0 + self._scalar_spot(x)) ** (-x)) for x in t]

        if isinstance(t, np.ndarray):
            spots = np.array([self._scalar_spot(float(x)) for x in t])
            return np.asarray((1.0 + spots) ** (-t.astype(float)), dtype=np.float64)

        if isinstance(t, pl.Series):
            return pl.Series(
                name=t.name,
                values=[
                    (1.0 + self._scalar_spot(float(x))) ** (-float(x))
                    for x in t.to_list()
                ],
                dtype=pl.Float64,
            )

        if isinstance(t, pl.Expr):
            from gaspatchio_core.functions.vector import curve_eval, list_pow

            spot = curve_eval(t, **self._kernel_kwargs())
            return list_pow(spot + 1.0, t * -1.0)

        msg = f"unsupported t type: {type(t).__name__}"
        raise TypeError(msg)

    def forward_rate(self, *, t1: float, t2: float) -> float:
        """Annually compounded forward rate between ``t1`` and ``t2``.

        Derived from the discount factors:
        ``DF(t1) / DF(t2) = (1 + F(t1, t2))^(t2 - t1)``

        Args:
            t1: Start year fraction. Must be strictly less than ``t2``.
            t2: End year fraction. Must be strictly greater than ``t1``.

        Returns:
            The annually compounded forward rate as a scalar float.

        Raises:
            ValueError: If ``t1 >= t2``.

        Examples:
            >>> c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])
            >>> c.forward_rate(t1=2.0, t2=5.0)  # doctest: +ELLIPSIS
            0.04...

        """
        if t1 >= t2:
            msg = f"t1 ({t1}) must be strictly less than t2 ({t2})"
            raise ValueError(msg)
        r1 = self._scalar_spot(t1)
        r2 = self._scalar_spot(t2)
        df1_factor = (1.0 + r1) ** (-t1)
        df2_factor = (1.0 + r2) ** (-t2)
        return float((df1_factor / df2_factor) ** (1.0 / (t2 - t1)) - 1.0)

    def key_rate_shift(self, *, tenor: float, bps: float) -> Curve:
        """Return a new Curve with the rate at the given knot tenor shifted by ``bps``.

        Args:
            tenor: The knot tenor (in years) at which to apply the shift. Must
                be an exact member of the curve's tenors.
            bps: Basis points to add to the single knot rate. One basis point
                is ``0.0001`` (i.e. 100 bps == 1 percentage point).

        Returns:
            A new frozen :class:`Curve` with all rates identical except at
            ``tenor``, which is incremented by ``bps / 10_000``.

        Raises:
            ValueError: If ``tenor`` is not an exact knot in this curve.

        Examples:
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05]
            ... )
            >>> bumped = c.key_rate_shift(tenor=5.0, bps=25)
            >>> bumped.rates
            (0.03, 0.0425, 0.05)
            >>> c.key_rate_shift(tenor=10.0, bps=0) == c
            True

        """
        from gaspatchio_core.curves._shift import key_rate_shift

        return key_rate_shift(self, tenor, bps)

    @classmethod
    def from_par_rates(
        cls,
        *,
        tenors: list[float],
        par_rates: list[float],
        day_count: DayCount | None = None,
        interpolation: InterpolationMethod = "linear",
    ) -> Curve:
        """Build a Curve via bootstrap from annual par coupon rates.

        Currently supports integer-year tenors starting at year 1 only,
        contiguous. Returns a Curve whose ``rates`` are zero rates derived
        via the bootstrap recursion.

        Args:
            tenors: Integer-year tenors starting at 1, contiguous (e.g.
                ``[1.0, 2.0, 3.0]``).
            par_rates: Par coupon rates at each tenor.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
                Recorded for identity / ``source_sha`` only — it does not affect
                rate evaluation.
            interpolation: Interpolation method; ``'linear'`` (default) or
                ``'log_linear'``.

        Returns:
            A frozen :class:`Curve` whose ``rates`` are bootstrapped zero rates.

        Raises:
            ValueError: If tenors are not contiguous annual integers starting at
                1, or if the underlying :meth:`from_zero_rates` validation
                fails.

        Examples:
            >>> c = Curve.from_par_rates(
            ...     tenors=[1.0, 2.0, 3.0], par_rates=[0.04, 0.04, 0.04]
            ... )
            >>> c.rates  # doctest: +ELLIPSIS
            (0.04..., 0.04..., 0.04...)

        """
        from gaspatchio_core.curves._bootstrap import par_to_zero_rates

        zero_rates = par_to_zero_rates(tenors, par_rates)
        return cls.from_zero_rates(
            tenors=tenors,
            rates=zero_rates,
            day_count=day_count,
            interpolation=interpolation,
        )

    def shift_parallel(self, *, bps: float) -> Curve:
        """Return a new Curve with every knot rate shifted by ``bps`` basis points.

        Args:
            bps: Basis points to add to every knot rate. One basis point is
                ``0.0001`` (i.e. 100 bps == 1 percentage point).

        Returns:
            A new frozen :class:`Curve` with the same tenors, day-count, and
            interpolation method, but every knot rate incremented by
            ``bps / 10_000``.

        Examples:
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05]
            ... )
            >>> up = c.shift_parallel(bps=100)
            >>> up.rates  # doctest: +ELLIPSIS
            (0.04, 0.05, 0.06...)
            >>> c.shift_parallel(bps=0) == c
            True

        """
        from gaspatchio_core.curves._shift import shift_parallel

        return shift_parallel(self, bps)

    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this Curve.

        For knot-based curves the form is identical to previous versions
        (keys: ``kind``, ``tenors``, ``rates``, ``day_count``,
        ``interpolation``).  For parametric curves an additional
        ``parametric`` sub-dict is included with ``kind`` and all parameters,
        while ``tenors`` and ``rates`` are empty lists (backward-compatible:
        knot curves with no ``parametric`` field produce the exact same bytes
        as before this change).

        Returns:
            A JSON-serialisable dict uniquely identifying this curve.

        Examples:
            >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> c.canonical_form()["kind"]
            'Curve'
            >>> isinstance(c.canonical_form()["tenors"], list)
            True
            >>> c2 = Curve.from_svensson(
            ...     b0=0.04, b1=-0.01, b2=0.005, b3=0.002, tau1=1.5, tau2=10.0
            ... )
            >>> c2.canonical_form()["parametric"]["kind"]
            'svensson'

        """
        base: dict[str, object] = {
            "kind": "Curve",
            "tenors": list(self.tenors),
            "rates": list(self.rates),
            "day_count": self.day_count.name(),
            "interpolation": self.interpolation,
        }
        if self.parametric is not None:
            p = self.parametric
            if p.kind == "svensson":
                base["parametric"] = {
                    "kind": p.kind,
                    "b0": p.b0,
                    "b1": p.b1,
                    "b2": p.b2,
                    "b3": p.b3,
                    "tau1": p.tau1,
                    "tau2": p.tau2,
                }
            elif p.kind == "smith_wilson":
                base["parametric"] = {
                    "kind": p.kind,
                    "u": list(p.u) if p.u is not None else [],
                    "zeta": list(p.zeta) if p.zeta is not None else [],
                    "omega": p.omega,
                    "alpha": p.alpha,
                }
        return base

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        The digest is computed over :meth:`canonical_form` serialised by
        :func:`gaspatchio_core._identity.canonical_bytes` (sorted
        keys, no extra whitespace). Identical curves produce identical SHAs;
        any knot, day-count, or interpolation difference changes the SHA.

        Returns:
            A string of the form ``sha256:<64-hex-chars>``.

        Examples:
            >>> a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> a.source_sha() == b.source_sha()
            True
            >>> a.source_sha().startswith("sha256:")
            True

        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"


__all__ = ["Curve", "ParametricPayload", "TimeInput"]
