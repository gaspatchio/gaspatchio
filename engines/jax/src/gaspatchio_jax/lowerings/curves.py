# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``curve.spot_rate`` and ``curve.discount_factor``: one curve, read exactly.

The identity comes first. 11.1.31 resolves the **exact** source digest to one
recipe in the document's own directory, and a current curve of the same
display name is not a replacement for the one the model read -- so the digest
is what resolves and a name that matched nothing else is not consulted.
Matching a digest is not the same as reproducing an evaluated rate, and both
halves are done here: the entry is resolved by its whole digest and then the
interpolation is carried out from the knots it carries.

**One bounded recipe, and a reader must say so rather than substitute.** A
knot curve, linear between the knots, flat outside them -- the canonical
recipe omits ``extrapolation`` for flat. A nonlinear or forward-extrapolated
or parametric recipe is a perfectly valid identity and outside this evaluation
entry, and the clause is explicit that a reader must report the capability
limit rather than replace the modeller's interpolation with a linear one.

**No calendar conversion of the time operand.** The times are years as
numbers, on either side, and this operation does not turn a date into one.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final

import jax.numpy as jnp

from gaspatchio_jax.capability import NUMERIC, Capability
from gaspatchio_jax.ieee import divided
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import DomainRefused, Value, carried_to

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext

_CURVES: Final = "11.1.31"

# The one interpolation this entry evaluates, and the one extrapolation, which
# the canonical recipe writes by leaving the member out.
_LINEAR: Final = "linear"
_FLAT: Final = "flat"

# The floor a knot rate stands above.
_RATE_FLOOR: Final = -1.0

# The fewest knots a line can be drawn between.
_LEAST_KNOTS: Final = 2


def _named(carrier: str, like: Value) -> str:
    """Return the type name an answer stands under, in its operand's shape.

    A per-period answer's type is ``list[…]`` and a per-policy one's is the
    bare name. The two are one line apart and the value's own ``dtype`` is
    read where a nested call has no record to declare it.
    """
    return f"list[{carrier}]" if like.shape == "list" else carrier


def _recipe(call: Call, ctx: LoweringContext) -> tuple[jax.Array, jax.Array]:
    """Return the knots of the curve one call names, checked against the entry.

    Raises:
        DomainRefused: If the recipe is outside the bounded evaluation domain
            -- fewer than two knots, tenors that do not strictly increase, a
            rate at or below -1, or an interpolation or extrapolation this
            entry does not state.

    """
    digest = str(dict(call.attrs)["curve"])
    payload = ctx.assumption("curve", None, digest)
    _outside_the_domain(payload, digest)
    tenors = [float(one) for one in payload["tenors"]]
    rates = [float(one) for one in payload["rates"]]
    if len(tenors) != len(rates) or len(tenors) < _LEAST_KNOTS:
        raise DomainRefused(
            what=(
                f"the curve {digest} carries {len(tenors)} tenors and "
                f"{len(rates)} rates, and a line needs at least two of each"
            ),
            move="export the artifact again from the run that read the curve",
            clause=_CURVES,
        )
    if any(later <= earlier for earlier, later in pairwise(tenors)):
        raise DomainRefused(
            what=f"the tenors of the curve {digest} do not strictly increase",
            move="check the curve the model registered: a knot curve is "
            "stated on strictly increasing tenors",
            clause=_CURVES,
        )
    if any(one <= _RATE_FLOOR for one in rates):
        raise DomainRefused(
            what=f"the curve {digest} carries a knot rate at or below -1",
            move="check the rate basis the curve was built on",
            clause=_CURVES,
        )
    return jnp.asarray(tenors), jnp.asarray(rates)


def _outside_the_domain(payload: dict[str, Any], digest: str) -> None:
    """Refuse a recipe this entry states no evaluation for.

    Raises:
        DomainRefused: If the interpolation or the extrapolation is outside
            the bounded domain. The clause requires a reader to report this
            rather than evaluate it as though it were linear.

    """
    interpolation = str(payload.get("interpolation") or _LINEAR)
    extrapolation = payload.get("extrapolation")
    if interpolation != _LINEAR or (
        extrapolation is not None and str(extrapolation) != _FLAT
    ):
        raise DomainRefused(
            what=(
                f"the curve {digest} is {interpolation} with "
                f"{extrapolation or _FLAT} extrapolation, and this engine "
                "evaluates a linear knot curve with flat extrapolation"
            ),
            move=(
                "run this model on Polars: replacing the recipe's own "
                "interpolation with a linear one would answer a different "
                "curve under the same digest"
            ),
            clause=_CURVES,
        )


def _interpolated(times: jax.Array, tenors: jax.Array, rates: jax.Array) -> jax.Array:
    """Return the spot rate at each time: linear between knots, flat outside.

    Written as the reference producer writes it, ``y0 + (y1 - y0) * (t - x0)
    / (x1 - x0)``: the product, its quotient and then the sum, each rounded.
    ``jnp.interp`` groups the line the other way, ``(t - x0) / (x1 - x0)``
    first, and its product and sum fuse into one multiply-add, so it parted
    from the producer in the last place. A time at or before the first
    tenor is the first rate, at or past the last the last rate, a NaN a NaN.
    """
    # The first tenor past each time, kept inside the knots; the clamps
    # below answer the times outside them.
    upper = jnp.clip(
        jnp.searchsorted(tenors, times, side="right"), 1, tenors.shape[0] - 1
    )
    x0, x1 = tenors[upper - 1], tenors[upper]
    y0, y1 = rates[upper - 1], rates[upper]
    between = y0 + divided((y1 - y0) * (times - x0), x1 - x0)
    return jnp.where(
        times <= tenors[0],
        rates[0],
        jnp.where(times >= tenors[-1], rates[-1], between),
    )


def _reading(name: str) -> Lowering:
    """Return the lowering for one of the two readings of a curve."""

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        times = carried_to(ctx.lower(call.args[0]), "f64", clause=_CURVES)
        tenors, rates = _recipe(call, ctx)
        spot = _interpolated(times.array, tenors, rates)
        answered = (
            spot if name == "curve.spot_rate" else jnp.power(1.0 + spot, -times.array)
        )
        return Value(answered, "f64", times.shape, _named("f64", times), times.horizon)

    lowering.__name__ = name
    return lowering


for _name in ("curve.spot_rate", "curve.discount_factor"):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            carriers=(NUMERIC,),
            attrs_required=("curve",),
            clause=_CURVES,
            note=(
                "a knot curve, linear between the knots and flat outside "
                "them, resolved by the recipe's whole digest"
            ),
        )
    )(_reading(_name))
