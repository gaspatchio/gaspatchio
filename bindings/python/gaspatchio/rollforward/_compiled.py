# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""CompiledRollforward — frozen output of compile_rollforward()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gaspatchio._authoring import emit
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.lowering.artefacts import register_rollforward
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.rollforward._data import CompiledData
from gaspatchio.rollforward._ops import increment_keys
from gaspatchio.rollforward._refs import StateRef

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.rollforward._ir import IR


def capture_slot_error(
    state: str,
    point: str,
    ir: IR,
    capture_slots: tuple[StateRef, ...],
) -> KeyError:
    """Build the error for an unreadable ``(state, point)`` extraction.

    Capture slots exist for each state's ``eop`` and for points an Op
    targets — declaring a point in ``points=(...)`` alone does not capture
    it. The message names whichever precondition actually failed.

    Parameters
    ----------
    state : str
        The state name the extraction asked for.
    point : str
        The point name the extraction asked for.
    ir : IR
        The compiled IR, for the declared states and points.
    capture_slots : tuple[StateRef, ...]
        The slots the kernel actually emits.

    Returns
    -------
    KeyError
        An error whose message states the failed precondition and the
        next move.

    """
    state_names = [s.name for s in ir.states]
    if state not in state_names:
        msg = f"Unknown state {state!r}. States on this rollforward: {state_names}."
        return KeyError(msg)
    if point not in ir.points:
        msg = (
            f"Point {point!r} is not declared on this rollforward. Declared "
            f"points: {list(ir.points)}. A point must be declared in "
            f"points=(...) and targeted by an Op before it can be read."
        )
        return KeyError(msg)
    captured = [s.point for s in capture_slots if s.state == state]
    msg = (
        f"({state!r}, {point!r}) is not a capture slot: {point!r} is declared, "
        f"but no Op targets it for state {state!r}. Slots exist for each "
        f"state's 'eop' and for points an Op targets — declaring a point "
        f"alone does not capture it. Captured for {state!r}: {captured}. "
        f"To read {point!r}, target it with an Op; for an opening balance, "
        f"read the prior period's close: the eop column's "
        f".projection.previous_period()."
    )
    return KeyError(msg)


@dataclass(frozen=True)
class CompiledRollforward(CompiledData):
    """Frozen artefact carrying the compiled IR and inspection surface.

    Returned by :func:`compile_rollforward`. Carries everything the kernel
    needs to execute (``plugin_kwargs``, ``plugin_args``, ``capture_slots``),
    the expression surface (``expr_for``, ``increment_for``), and three
    inspection helpers for governance and audit.
    """

    def plugin_expr(self) -> pl.Expr:
        """Return the raw kernel call as a self-contained Polars expression.

        The escape hatch for use outside ``ActuarialFrame``: alias the struct
        onto a plain LazyFrame yourself, then extract fields from that column::

            df = df.with_columns(compiled.plugin_expr().alias("rf"))
            df = df.with_columns(av=pl.col("rf").struct.field("av@eop"))

        Inside ``ActuarialFrame`` prefer :meth:`expr_for`, which shares one
        kernel call across every extraction automatically.

        Emitted like the two extraction methods, so the escape hatch is not
        the one public rollforward expression with no semantic record behind
        it. Still a real ``pl.Expr``, so the usage above is unchanged.
        """
        return self._emit("rollforward.struct", ())

    def _emit(self, name: str, attrs: tuple[tuple[str, Any], ...]) -> pl.Expr:
        """Emit a rollforward ``Call`` and hand back the expression it lowers to.

        The node records what this rollforward reads, in the op-tree's own
        vocabulary — each state's opening value, each operation's operand,
        and a running-state read as a ``State`` child rather than a string
        inside a plugin keyword argument. The call carries the machine's
        published ``fingerprint`` and, beside it, the ``schedule`` the
        machine runs on, by that schedule's own ``source_sha()``: the
        fingerprint leaves the schedule out, so the schedule is
        stated as the data it is, and the pair is what the lowering resolves
        this compiled artefact by before calling the same kernel path as
        before, so the plan is unchanged. The engine
        expressions live in ``frame/lowering/rules/rollforward.py``; the
        compiler and this per-instance cache keep their existing ownership.
        """
        # `rules.rollforward` loads with its siblings the first time anything
        # reads ``LOWERINGS``; importing one rule module at module scope would
        # populate the registry while ``_RULES_LOADED`` is still False.
        from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — rules load lazily
            operand_nodes,
        )

        fingerprint, schedule = register_rollforward(self)
        node = emit.call_node(
            name,
            operand_nodes(self.ir),
            (("fingerprint", fingerprint), ("schedule", schedule), *attrs),
        )
        # Bound to the frame the rollforward was built from, where it was
        # built from one, so ``expr_for("av").cum_sum()`` or ``.shift(1)``
        # means what it means on the column it would be assigned to.
        frame_ref = self.__dict__.get("_frame_ref")
        parent = None if frame_ref is None else frame_ref()
        return ProxyAwareExpr.wrap(lower_polars(node), node=node, parent=parent)

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a Polars Expr selecting the per-period values for (state, point).

        All extractions from one compiled rollforward share a single kernel
        call when assigned to an ``ActuarialFrame``::

            af.fund = compiled.expr_for("fund")
            af.gmdb = compiled.expr_for("gmdb")  # no second kernel run

        That one run is over the inputs as they stood where the frame first
        read the rollforward, so an extraction written after one of them
        was written again is refused at its assignment, naming the input:
        give the later values a column of their own, read by a rollforward
        of their own.
        """
        ref = StateRef(state=state, point=point)
        if ref not in self.capture_slots:
            raise capture_slot_error(state, point, self.ir, self.capture_slots)
        return self._emit(
            "rollforward.state",
            (("state", state), ("point", point), ("shared", True)),
        )

    def increment_for(self, label: str) -> pl.Expr:
        """Return a Polars Expr selecting the per-period delta for one Op.

        The delta is signed — the movement the op made in its target:
        negative for charges, positive for credits, zero after a stop or
        lapse (the kernel applied nothing, where a source sheet may keep
        computing a notional charge against the full face amount).

        It is the target's value after the op minus its value before, in
        binary64 (graph-artifact spec section 16.2), not the operand the op
        computed. The two agree to floating point, and the difference is
        visible: interest of 151.62 credited with ``round_charge=2`` onto a
        balance of 4738.22 reads ``151.6199999999999``, because that is what
        the balance moved by. This is what makes a period's increments sum to
        that period's change in the balance. Round the column when you
        display it; the identity holds on the values as reported.

        ``label`` is the name the model's author gave the step, or — for the
        two structural steps that have no label to give — the key the kernel
        names their movement under, ``floor@3`` for a ``Floor`` declared
        third. Every step of a tracked rollforward has one, which is what
        lets a waterfall quote the amount a floor absorbed rather than
        deriving it.

        Read from the frame's one run of the rollforward, like
        :meth:`expr_for`, and refused on the same terms once one of its
        inputs has been written again since the frame first read it.
        """
        self._validate_increment_label(label)
        return self._emit("rollforward.increment", (("label", label), ("shared", True)))

    def _validate_increment_label(self, label: str) -> None:
        """Refuse an unknown/untracked increment label at the call that asks.

        ``increment_for`` refuses here rather than letting an unknown label
        reach collect time as a missing struct field, far from the call that
        asked for it.
        """
        if not self.ir.track_increments:
            msg = (
                "increment_for(): this rollforward was built without "
                "track_increments=True, so the kernel emits no increment "
                "fields. Pass track_increments=True to the builder."
            )
            raise ValueError(msg)
        keys = list(increment_keys(self.ir.transitions))
        if label not in keys:
            msg = (
                f"increment_for({label!r}): no step of this rollforward emits "
                f"that increment. The steps it emits: {keys}."
            )
            raise KeyError(msg)


__all__ = ["CompiledRollforward"]
