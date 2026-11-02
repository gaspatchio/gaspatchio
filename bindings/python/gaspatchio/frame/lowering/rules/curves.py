# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowerings for reading a yield curve at a column of times.

``Curve.spot_rate(t)`` and ``Curve.discount_factor(t)`` answer four
different kinds of question depending on what ``t`` is -- a single number,
a list, a NumPy array, or a column. Only the last builds a Polars
expression, and only that branch is here; the eager branches stay on the
curve, where they are ordinary Python arithmetic and always were.

Like a schedule, a curve is a value object rather than a column plus a
setting, so the node carries its ``source_sha`` and the rule looks the
curve back up (see ``frame/lowering/artefacts.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio.frame.lowering._polars.plugins import curve_eval, list_pow
from gaspatchio.frame.lowering.artefacts import curve_for
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio._semantic.ir import Call
    from gaspatchio.curves._data import CurveData
    from gaspatchio.frame.lowering.context import LoweringContext


def _curve(node: Call) -> CurveData:
    """Resolve the curve this call was emitted against."""
    sha = dict(node.attrs)["curve"]
    if not isinstance(sha, str):  # pragma: no cover - emission always sets it
        msg = f"{node.name}: 'curve' must be a source SHA, got {sha!r}"
        raise TypeError(msg)
    return curve_for(sha)


@register_lowering("curve.spot_rate")
def _lower_spot_rate(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read the spot rate the curve gives at each time in ``t``."""
    curve = _curve(node)
    times, _ = lower_arg(node.args[0], ctx)
    return curve_eval(times, **curve._kernel_kwargs())  # noqa: SLF001


@register_lowering("curve.discount_factor")
def _lower_discount_factor(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Discount each time in ``t`` by its own spot rate: ``(1 + spot(t)) ** -t``.

    Each time carries its own spot rate, so the factors are not a single
    rate raised to a column of powers -- which is why this goes through
    the ``list_pow`` kernel rather than native ``**``.
    """
    curve = _curve(node)
    times, _ = lower_arg(node.args[0], ctx)
    spot = curve_eval(times, **curve._kernel_kwargs())  # noqa: SLF001
    return list_pow(spot + 1.0, times * -1.0)
