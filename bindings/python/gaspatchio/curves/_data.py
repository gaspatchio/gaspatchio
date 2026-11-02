# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only Curve data and calculations shared by authoring and execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from gaspatchio._identity import SHA256_PREFIX, canonical_bytes
from gaspatchio.curves._interpolation import log_df_knots, pchip_slopes

if TYPE_CHECKING:
    from gaspatchio.schedule._day_count import DayCount

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

    Svensson fields (``b0``-``b3``, ``tau1``, ``tau2``) are ``None`` for
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


def _validate_extrapolation(interpolation: str, extrapolation: str) -> None:
    """Reject invalid interpolation/extrapolation combinations at construction.

    ``"forward"`` extends a forward rate, which only exists for the log-DF
    representation — for rate-space knots (``linear``/``pchip``) "flat" is
    already a spot clamp and "forward" has no meaning. Raising here puts the
    error at the call site rather than at ``collect()``.
    """
    if extrapolation not in ("flat", "forward"):
        msg = (
            f"extrapolation {extrapolation!r} is not supported; "
            f"expected 'flat' or 'forward'"
        )
        raise ValueError(msg)
    if extrapolation == "forward" and interpolation != "log_linear":
        msg = (
            "extrapolation='forward' requires interpolation='log_linear'; "
            f"rate-space knots ({interpolation!r}) support only 'flat'"
        )
        raise ValueError(msg)


@dataclass(frozen=True)
class CurveData:
    """Immutable values shared by lowering and audit, independent of authoring."""

    tenors: tuple[float, ...]
    rates: tuple[float, ...]
    day_count: DayCount
    interpolation: InterpolationMethod = field(default="linear")
    parametric: ParametricPayload | None = field(default=None)
    extrapolation: str = field(default="flat")

    def __post_init__(self) -> None:
        """Validate field combinations on every construction path.

        Classmethods, direct ``Curve(...)`` calls, and reconstruction sites
        such as ``dataclasses.replace`` all funnel through here — an invalid
        interpolation/extrapolation pair can never produce a live curve that
        would otherwise fail (or silently evaluate flat) at collect time.
        """
        _validate_extrapolation(self.interpolation, self.extrapolation)

    def _kernel_kwargs(self) -> _KernelKwargs:
        """Return ``curve_eval`` kwargs matching this curve's method.

        Handles both parametric (svensson) and knot-based (linear, log_linear,
        pchip) curves.  Used by both the ``spot_rate`` and ``discount_factor``
        column branches so a single change here propagates to both.
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
                "extrapolation": self.extrapolation,
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
            >>> from gaspatchio import Curve
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
        # Included only when non-default so every existing curve keeps its
        # sha; a "forward" curve MUST hash differently — Audit by default
        # requires the identity stamp to change when behaviour changes.
        if self.extrapolation != "flat":
            base["extrapolation"] = self.extrapolation
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
        :func:`gaspatchio._identity.canonical_bytes` (sorted
        keys, no extra whitespace). Identical curves produce identical SHAs;
        any knot, day-count, or interpolation difference changes the SHA.

        Returns:
            A string of the form ``sha256:<64-hex-chars>``.

        Examples:
            >>> from gaspatchio import Curve
            >>> a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
            >>> a.source_sha() == b.source_sha()
            True
            >>> a.source_sha().startswith("sha256:")
            True

        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"{SHA256_PREFIX}{digest}"
