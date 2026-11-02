# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowering for a convention-aware read of a mortality basis.

``mortality.at(age=..., duration=...)`` is one operation with three
readings, and which one it is depends on the wrapper's ``structure``. On
an aggregate or a joint basis it is the underlying table's own lookup. On
a select and ultimate basis the duration is first held at the select
period, so that every duration past the select period reads the select
period's own row -- which is what a select table means by an ultimate
rate.

What the node does *not* carry is the clamp: the clamp is what
``structure`` and ``select_period`` mean, and writing it into the tree
instead is how a select period came to be unreadable from an artifact of
a model that applied one. Both are flat values on the node, so this rule
rebuilds the clamp from them and reaches nothing for it.

**The base underneath is resolved by the name the node carries, and the
content hash beside it verifies the answer.** Those two attributes are
the pair every lookup carries, and this rule hands both to
``table_named``. The name has to be what selects, because the expression
this rule returns is built by ``Table.lookup`` and the kernel resolves
that lookup by the table's *name* again at execution time: a base picked
out by its values alone can be a table called something else that happens
to hold the same rates today, and the model then reads whatever that
other name comes to hold -- a wrong number, with every attribute on the
node still naming the right base. The hash has to be what verifies,
because a name is not an identity: a scenario sweep rebuilds one name per
batch, and a base that has moved since this read was written is refused
rather than answered from. Neither half is allowed to stand in for the
other, and a mismatch never falls back to the content-keyed directory.

It does *not* resolve the wrapper by the ``mortality`` digest also on the
node, and ``frame/lowering/artefacts.py`` sets out why it cannot: that
digest covers the convention and the table's name, never its rates, so
every batch of a scenario sweep publishes the same one over different
rates.

**The clamp is chosen on the duration column's own dtype.** A per-policy
duration is an ordinary numeric column and clips through Polars' own
``clip``; a per-period one is a list column and clips inside each row,
through ``list.eval(element().clip(...))``. That is the same form
``frame/lowering/rules/bounds.py`` routes a value-bounded list clip
through, and it is the right one here for that module's own reason: a
select period is a literal, never a column, so nothing has to be reached
from inside the eval. It is also the cheaper of the two on a model's own
path, measured end to end against the ``list_clip`` kernel on a select
and ultimate read at ten and fifty thousand policies over 120 monthly
periods; and it leaves an Int64 duration Int64 and a null timeline null,
where the kernel widened to Float64 and turned a null list into an empty
one. This rule reads which shape it has off the shape the lowering
already resolved against the frame's schema. The recording door used to
decide it by asking whether the caller had passed a proxy, and
proxy-ness is not shape: a pricing-at-issue read -- one point in time, no
projection, so scalar age and scalar duration -- passes proxies too, took
the list branch, and came back as ``ComputeError: values must be List
dtype for list_clip`` instead of a rate. *Meet you where you are*: one
point in time is a shape an actuary already has.

A shape that genuinely cannot be resolved -- a raw ``pl.Expr`` handed in
with no frame anywhere in the call -- reads ``unknown``, and the scalar
form is the answer for it, which is what such a read already did.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio.frame.lowering.artefacts import table_named
from gaspatchio.frame.lowering.lookup import lookup_node
from gaspatchio.frame.lowering.polars import lower_arg, lower_polars, register_lowering

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio._shape import Shape
    from gaspatchio.assumptions._data import TableData
    from gaspatchio.frame.lowering.context import LoweringContext

# The dimension a select and ultimate basis holds at its select period.
_DURATION = "duration"

# What ``MortalityTable._emit`` joined the dimension names with. One
# convention, written down in specification 11.1.10 and spelled at both
# ends of it -- the emitter cannot import this module (the rule modules
# are loaded lazily, by name, and only by the registry).
_NAME_SEPARATOR = ","


def _basis(node: Call) -> TableData:
    """Resolve the base this read names, verified against the rates it read."""
    attrs = dict(node.attrs)
    name = attrs["table"]
    fingerprint = attrs["table_fingerprint"]
    if not isinstance(name, str):  # pragma: no cover - emission sets it
        msg = f"{node.name}: 'table' must be an assumption table name, got {name!r}"
        raise TypeError(msg)
    if not isinstance(fingerprint, str):  # pragma: no cover - emission sets it
        msg = (
            f"{node.name}: 'table_fingerprint' must be a content hash, "
            f"got {fingerprint!r}"
        )
        raise TypeError(msg)
    return table_named(name, fingerprint)


def _clamped(duration: pl.Expr, shape: Shape, select_period: int) -> pl.Expr:
    """Hold ``duration`` at ``select_period``, in the form its shape takes.

    Bounded above only: a select and ultimate table's early durations are
    its select rates, and nothing about the convention raises a duration
    that has not reached the select period yet.

    **A NaN duration stays NaN, where it used to become ``-inf``.** Both
    forms here are Polars' own ``clip``, which leaves a NaN alone, and the
    ``list_clip`` kernel the list branch used to take mapped it to the
    lower bound instead -- so a projection carrying a NaN duration reads a
    different rate than it did, or misses. That is a behaviour difference
    worth knowing before bisecting for it, and the direction is towards
    agreement rather than away: the per-policy and per-period branches now
    answer the same way for the same duration, which they did not while
    one of them was a kernel. The kernel has since been aligned to that
    same rule for the callers it does still have, so nothing in the
    framework answers a NaN with a bound any more.
    """
    if shape != "list":
        return duration.clip(upper_bound=select_period)
    return duration.list.eval(pl.element().clip(upper_bound=select_period))


@register_lowering("mortality.at")
def _lower_mortality_at(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read one rate per row off the basis, under the convention recorded here.

    The read itself is the underlying table's lookup, built through
    the same lookup preparation as ``Table.lookup``: the key ordering, the
    dimension-name translation and the miss policy are that method's, and
    two places deciding them would be two places to disagree.
    """
    basis = _basis(node)
    attrs = dict(node.attrs)
    names = str(attrs["dimensions"]).split(_NAME_SEPARATOR)
    select_period = attrs.get("select_period")

    keys: dict[str, pl.Expr] = {}
    for name, arg in zip(names, node.args, strict=True):
        expr, shape = lower_arg(arg, ctx)
        if name == _DURATION and isinstance(select_period, int):
            keys[name] = _clamped(expr, shape, select_period)
        else:
            keys[name] = expr
    return lower_polars(lookup_node(basis, keys))
