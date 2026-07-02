# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve shift / stress operations.

Each shift returns a NEW Curve (immutability invariant). Parallel shift
and key-rate shift are supported; non-parallel principal-component
shifts are not yet implemented.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.curves._curve import Curve


def shift_parallel(curve: Curve, bps: float) -> Curve:
    """Return a new Curve with every knot rate shifted by ``bps`` basis points.

    Args:
        curve: The source curve whose rates are shifted.
        bps: Basis points to add to every knot rate. One basis point is
            ``0.0001`` (i.e. 100 bps == 1 percentage point).

    Returns:
        A new frozen :class:`~gaspatchio_core.curves._curve.Curve` with the
        same tenors, day-count, and interpolation method, but every knot rate
        incremented by ``bps / 10_000``.

    Examples:
        >>> from gaspatchio_core.curves._curve import Curve
        >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        >>> up = shift_parallel(c, bps=100)
        >>> tuple(round(r, 4) for r in up.rates)
        (0.04, 0.05, 0.06)

    """
    delta = bps / 10_000.0
    shifted_rates = tuple(r + delta for r in curve.rates)
    return type(curve)(
        tenors=curve.tenors,
        rates=shifted_rates,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
    )


def key_rate_shift(curve: Curve, tenor: float, bps: float) -> Curve:
    """Shift the rate at exactly one knot tenor by ``bps`` basis points.

    Raises ``ValueError`` if ``tenor`` is not an exact knot. Fractional
    or interpolated key-rate shifts are not yet supported.

    Args:
        curve: The source curve whose single knot rate is shifted.
        tenor: The knot tenor (in years) at which to apply the shift. Must
            be an exact member of ``curve.tenors``.
        bps: Basis points to add to the single knot rate. One basis point
            is ``0.0001`` (i.e. 100 bps == 1 percentage point).

    Returns:
        A new frozen :class:`~gaspatchio_core.curves._curve.Curve` with the
        same tenors, day-count, and interpolation method, but the rate at
        ``tenor`` incremented by ``bps / 10_000``.

    Raises:
        ValueError: If ``tenor`` is not found in ``curve.tenors``.

    Examples:
        >>> from gaspatchio_core.curves._curve import Curve
        >>> c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        >>> bumped = key_rate_shift(c, tenor=5.0, bps=25)
        >>> bumped.rates
        (0.03, 0.0425, 0.05)

    """
    if tenor not in curve.tenors:
        msg = f"tenor {tenor} not in curve; got knots {list(curve.tenors)}"
        raise ValueError(msg)
    delta = bps / 10_000.0
    idx = curve.tenors.index(tenor)
    shifted_rates = tuple(
        r + delta if i == idx else r for i, r in enumerate(curve.rates)
    )
    return type(curve)(
        tenors=curve.tenors,
        rates=shifted_rates,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
    )


__all__ = ["key_rate_shift", "shift_parallel"]
