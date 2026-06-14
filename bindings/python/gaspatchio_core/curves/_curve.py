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
  - Linear interpolation on rates; flat extrapolation outside the knot range.
  - Default day-count: ``ActualActualISDA``.
  - Constructors: ``from_zero_rates``, ``from_par_rates`` (bootstrap).
  - Stress: ``shift_parallel(bps)``, ``key_rate_shift(tenor, bps)``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
import polars as pl

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.curves._interpolation import linear_interpolate
from gaspatchio_core.schedule._day_count import ActualActualISDA, DayCount

# Input/output type union for accessors. Implementation dispatches on
# the concrete type at call time and returns a matching shape.
TimeInput = float | int | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr

InterpolationMethod = Literal["linear"]


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

        ``tenors`` and ``rates`` must have the same length, with ``tenors``
        strictly increasing and at least two knots present.

        Args:
            tenors: Tenor knot points in years, strictly increasing.
            rates: Zero rates at each knot point, same length as ``tenors``.
            day_count: Day-count convention; defaults to ``ActualActualISDA``.
            interpolation: Interpolation method; only ``'linear'`` is
                currently supported.

        Returns:
            A frozen :class:`Curve` instance.

        Raises:
            ValueError: If ``tenors`` and ``rates`` differ in length, fewer
                than 2 knots are supplied, tenors are not strictly increasing,
                or an unsupported interpolation method is requested.

        Examples:
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03]
            ... )
            >>> c.tenors
            (1.0, 5.0, 10.0)
            >>> c.interpolation
            'linear'

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
        if interpolation != "linear":
            msg = (
                f"unsupported interpolation {interpolation!r}; "
                f"only 'linear' is currently supported"
            )
            raise ValueError(msg)
        return cls(
            tenors=tuple(tenors),
            rates=tuple(rates),
            day_count=day_count or ActualActualISDA(),
            interpolation=interpolation,
        )

    def spot_rate(
        self,
        t: TimeInput,
    ) -> float | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr:
        """Spot zero rate at year fraction(s) ``t``.

        Dispatches on the concrete type of ``t`` and returns a matching shape:
        scalar in → scalar out, list in → list out, ndarray in → ndarray out,
        Series in → Series out, Expr in → Expr out.

        Args:
            t: Year fraction(s) at which to evaluate the spot rate. Accepts
                ``float``, ``int``, ``list[float]``, ``np.ndarray``,
                ``pl.Series``, or ``pl.Expr``.

        Returns:
            The interpolated spot zero rate(s). Return type matches input type.

        Raises:
            TypeError: If ``t`` is not one of the supported types.

        Examples:
            >>> c = Curve.from_zero_rates(
            ...     tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.03, 0.03]
            ... )
            >>> c.spot_rate(1.0)
            0.03
            >>> c.spot_rate([1.0, 5.0])
            [0.03, 0.03]

        """
        # Duck-type ColumnProxy / ExpressionProxy (af["t"], af["a"] + af["b"]) →
        # treat as a pl.Expr. Lets actuary-facing `af["t"]` flow into curve calls.
        to_expr = getattr(t, "_to_expr", None)
        if callable(to_expr):
            return self.spot_rate(to_expr())
        if isinstance(t, (int, float)):
            return linear_interpolate(float(t), self.tenors, self.rates)
        if isinstance(t, list):
            return [linear_interpolate(float(x), self.tenors, self.rates) for x in t]
        if isinstance(t, np.ndarray):
            return np.array(
                [linear_interpolate(float(x), self.tenors, self.rates) for x in t],
            )
        if isinstance(t, pl.Series):
            return pl.Series(
                name=t.name,
                values=[
                    linear_interpolate(float(x), self.tenors, self.rates)
                    for x in t.to_list()
                ],
                dtype=pl.Float64,
            )
        if isinstance(t, pl.Expr):
            tenors = self.tenors
            rates = self.rates

            def _interp(x: float) -> float:
                return linear_interpolate(x, tenors, rates)

            return t.map_elements(_interp, return_dtype=pl.Float64)
        msg = f"unsupported t type: {type(t).__name__}"
        raise TypeError(msg)

    def _scalar_spot(self, t: float) -> float:
        """Spot rate as a scalar float, bypassing dispatch."""
        return linear_interpolate(t, self.tenors, self.rates)

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

        Args:
            t: Year fraction(s) at which to evaluate the discount factor.
                Accepts ``float``, ``int``, ``list[float]``, ``np.ndarray``,
                ``pl.Series``, or ``pl.Expr``.

        Returns:
            The discount factor(s). Return type matches input type.

        Raises:
            TypeError: If ``t`` is not one of the supported types.

        Examples:
            >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.03])
            >>> c.discount_factor(1.0)  # doctest: +ELLIPSIS
            0.970873...
            >>> c.discount_factor([1.0, 2.0])  # doctest: +ELLIPSIS
            [0.970873..., 0.942595...]

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
            tenors = self.tenors
            rates = self.rates

            def _df(x: float) -> float:
                r = linear_interpolate(x, tenors, rates)
                return float((1.0 + r) ** (-x))

            # Scalar (flat Float64) expression only. For per-period discounting
            # over a projection LIST column (e.g. af.projection.t_years()), use
            # af.finance.discount_factor(...) — a vectorised, optimize-safe Rust
            # path; this map_elements form is debug-mode only.
            return t.map_elements(_df, return_dtype=pl.Float64)

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
            interpolation: Interpolation method; only ``'linear'`` is
                currently supported.

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
            >>> up.rates
            (0.04, 0.05, 0.06)
            >>> c.shift_parallel(bps=0) == c
            True

        """
        from gaspatchio_core.curves._shift import shift_parallel

        return shift_parallel(self, bps)

    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this Curve.

        Returns:
            A flat dict with keys ``kind``, ``tenors``, ``rates``,
            ``day_count``, and ``interpolation``. Lists (not tuples) are used
            for ``tenors`` and ``rates`` so the dict is directly
            JSON-serialisable.

        Examples:
            >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> c.canonical_form()["kind"]
            'Curve'
            >>> isinstance(c.canonical_form()["tenors"], list)
            True

        """
        return {
            "kind": "Curve",
            "tenors": list(self.tenors),
            "rates": list(self.rates),
            "day_count": self.day_count.name(),
            "interpolation": self.interpolation,
        }

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


__all__ = ["Curve", "TimeInput"]
