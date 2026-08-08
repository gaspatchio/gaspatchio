# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""RollforwardCollector — deprecated facade over CompiledRollforward.

Deprecated since v0.6: use ``compiled.expr_for(...)`` / ``compiled
.increment_for(...)`` directly. The collector returns SELF-CONTAINED plugin
expressions — each extraction embeds its own kernel call, so K extractions
cost K kernel runs. It exists so pre-0.6 call sites (and raw-Polars usage,
where the exprs work standalone on any LazyFrame) keep their exact old
behaviour. ``CompiledRollforward.expr_for`` instead references one shared
hidden struct column that ``ActuarialFrame`` materialises once, making the
one-kernel-call guarantee structural.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.rollforward._compiled import CompiledRollforward


class RollforwardCollector:
    """Deprecated: use :meth:`CompiledRollforward.expr_for` instead.

    Emits self-contained per-state / per-increment plugin exprs (one kernel
    call EACH — no sharing). Retained for backwards compatibility and for raw
    Polars frames, where a self-contained expr is the only thing that works.
    """

    def __init__(self, compiled: CompiledRollforward) -> None:
        self._compiled = compiled
        self._cached_plugin_expr: pl.Expr | None = None

    def _shared_plugin_expr(self) -> pl.Expr:
        if self._cached_plugin_expr is None:
            self._cached_plugin_expr = self._compiled.plugin_expr()
        return self._cached_plugin_expr

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a self-contained Expr for (state, point) — one kernel call each."""
        from gaspatchio_core.rollforward._compiled import capture_slot_error
        from gaspatchio_core.rollforward._refs import StateRef

        ref = StateRef(state=state, point=point)
        if ref not in self._compiled.capture_slots:
            raise capture_slot_error(
                state, point, self._compiled.ir, self._compiled.capture_slots
            )
        from gaspatchio_core.column.proxy_aware_expr import ProxyAwareExpr

        return ProxyAwareExpr.wrap(
            self._shared_plugin_expr().struct.field(f"{state}@{point}"),
        )

    def increment_for(self, label: str) -> pl.Expr:
        """Return a self-contained Expr for a labelled Op's per-period delta.

        The delta is signed — what the op actually applied to its target:
        negative for charges, positive for credits, zero after a stop or
        lapse (the kernel applied nothing, where a source sheet may keep
        computing a notional charge).
        """
        if not self._compiled.ir.track_increments:
            msg = (
                "increment_for(): this rollforward was built without "
                "track_increments=True, so the kernel emits no increment "
                "fields. Pass track_increments=True to the builder."
            )
            raise ValueError(msg)
        from gaspatchio_core.column.proxy_aware_expr import ProxyAwareExpr

        return ProxyAwareExpr.wrap(
            self._shared_plugin_expr().struct.field(f"increment_{label}"),
        )


__all__ = ["RollforwardCollector"]
