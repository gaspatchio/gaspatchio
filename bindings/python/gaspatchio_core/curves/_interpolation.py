# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve interpolation primitives.

Currently provides ``linear_interpolate`` — linear-on-rates interpolation
with flat extrapolation outside the knot grid. Log-linear-on-discount-factor
and monotone cubic are not yet implemented.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    """
    if x <= knots_x[0]:
        return knots_y[0]
    if x >= knots_x[-1]:
        return knots_y[-1]
    i = bisect_right(knots_x, x)
    x0, x1 = knots_x[i - 1], knots_x[i]
    y0, y1 = knots_y[i - 1], knots_y[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


__all__ = ["linear_interpolate"]
