# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""CompiledRollforward — frozen output of compile_rollforward()."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.rollforward._ir import IR
    from gaspatchio.rollforward._refs import StateRef


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
class CompiledRollforward:
    """Frozen artefact carrying the compiled IR and inspection surface.

    Returned by :func:`compile_rollforward`. Carries everything the kernel
    needs to execute (``plugin_kwargs``, ``plugin_args``, ``capture_slots``),
    the expression surface (``expr_for``, ``increment_for``), and three
    inspection helpers for governance and audit.
    """

    ir: IR
    plugin_kwargs: dict[str, Any]
    capture_slots: tuple[StateRef, ...]
    plugin_args: tuple[pl.Expr, ...] = field(default_factory=tuple)

    @cached_property
    def _hidden_column(self) -> str:
        """Name of the hidden struct column this rollforward materialises as."""
        from gaspatchio.rollforward._registry import hidden_column_name

        return hidden_column_name(self.fingerprint())

    def plugin_expr(self) -> pl.Expr:
        """Return the raw kernel call as a self-contained Polars expression.

        The escape hatch for use outside ``ActuarialFrame``: alias the struct
        onto a plain LazyFrame yourself, then extract fields from that column::

            df = df.with_columns(compiled.plugin_expr().alias("rf"))
            df = df.with_columns(av=pl.col("rf").struct.field("av@eop"))

        Inside ``ActuarialFrame`` prefer :meth:`expr_for`, which shares one
        kernel call across every extraction automatically.
        """
        from polars.plugins import register_plugin_function

        from gaspatchio import _internal

        return register_plugin_function(
            plugin_path=_internal.__file__,
            function_name="rollforward",
            args=list(self.plugin_args),
            kwargs=self.plugin_kwargs,
            is_elementwise=True,
        )

    @cached_property
    def _cached_plugin_expr(self) -> pl.Expr:
        """The plugin expr built once per instance (exprs are immutable, shareable)."""
        return self.plugin_expr()

    def _field_expr(self, field_name: str) -> pl.Expr:
        """Return a field extraction from the shared hidden struct column.

        Registers the plugin expr under the fingerprint-derived hidden name so
        ``ActuarialFrame`` can materialise the struct ONCE on first reference;
        every extraction is then a cheap ``.struct.field`` on that column.
        This is what makes the one-kernel-call guarantee structural, rather
        than dependent on the Polars optimiser deduplicating plugin calls
        (which Polars stopped doing in 1.42).
        """
        import polars as pl

        from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
        from gaspatchio.rollforward import _registry

        _registry.register(self._hidden_column, self._cached_plugin_expr)
        # Wrapped so extractions cooperate with af-column operands in either
        # operand order (gh#67) — same contract as Table.lookup.
        return ProxyAwareExpr.wrap(
            pl.col(self._hidden_column).struct.field(field_name),
        )

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a Polars Expr selecting the per-period values for (state, point).

        All extractions from one compiled rollforward share a single kernel
        call when assigned to an ``ActuarialFrame``::

            af.fund = compiled.expr_for("fund")
            af.gmdb = compiled.expr_for("gmdb")  # no second kernel run
        """
        from gaspatchio.rollforward._refs import StateRef

        ref = StateRef(state=state, point=point)
        if ref not in self.capture_slots:
            raise capture_slot_error(state, point, self.ir, self.capture_slots)
        return self._field_expr(f"{state}@{point}")

    def increment_for(self, label: str) -> pl.Expr:
        """Return a Polars Expr selecting the per-period delta for a labelled Op.

        The delta is signed — what the op actually applied to its target:
        negative for charges, positive for credits, zero after a stop or
        lapse (the kernel applied nothing, where a source sheet may keep
        computing a notional charge against the full face amount).
        """
        self._validate_increment_label(label)
        return self._field_expr(f"increment_{label}")

    def _validate_increment_label(self, label: str) -> None:
        """Refuse an unknown/untracked increment label at the call that asks.

        Shared with the deprecated ``RollforwardCollector`` facade so both
        paths refuse immediately with identical wording, rather than letting
        an unknown label die at collect time as a missing struct field.
        """
        if not self.ir.track_increments:
            msg = (
                "increment_for(): this rollforward was built without "
                "track_increments=True, so the kernel emits no increment "
                "fields. Pass track_increments=True to the builder."
            )
            raise ValueError(msg)
        labels = [
            found
            for op in self.ir.transitions
            if (found := getattr(op, "label", None)) is not None
        ]
        if label not in labels:
            msg = (
                f"increment_for({label!r}): no op carries that label. "
                f"Labelled ops in this rollforward: {labels}."
            )
            raise KeyError(msg)

    def canonical_form(self) -> dict[str, Any]:
        """Return a stable, deterministic dict describing the model structure.

        Two compiled rollforwards with the same Op chain (in the same order),
        same states, same Schedule canonical-form, and same configuration
        produce equal canonical-form dicts. Column-name aliases inside Op
        expressions are reduced to ``str(expr)``, so renaming a column does
        not change the canonical form.
        """
        from gaspatchio.rollforward._canonical import canonical_form

        return canonical_form(self.ir)

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint of the canonical form.

        Stable across runs and across machines for an unchanged model.
        Suitable for governance metadata and run logs.
        """
        from gaspatchio.rollforward._fingerprint import spec_fingerprint

        return spec_fingerprint(self.ir)

    def explain(self) -> str:
        """Return a multi-line human-readable summary of the model.

        Lists states, points, schedule, transitions in order, and the
        cross-cutting configuration (lapse, contract boundary, increment
        tracking). Plain text — fits in audit reports and TRACE logs.
        """
        from gaspatchio.rollforward._explain import explain

        return explain(self.ir)


__all__ = ["CompiledRollforward"]
