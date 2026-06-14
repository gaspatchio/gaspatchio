# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""RollforwardCollector — emits one shared plugin Expr per rollforward."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from polars.plugins import register_plugin_function

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.rollforward._compiled import CompiledRollforward


class RollforwardCollector:
    """Per-rollforward facade that exposes per-state / per-increment Polars Exprs.

    The collector caches a single ``register_plugin_function`` result so the
    Polars optimiser can deduplicate the kernel call across multiple
    ``.struct.field(...)`` accesses within a single ``with_columns`` call.
    """

    def __init__(self, compiled: CompiledRollforward) -> None:
        self._compiled = compiled
        self._cached_plugin_expr: pl.Expr | None = None

    def _shared_plugin_expr(self) -> pl.Expr:
        if self._cached_plugin_expr is not None:
            return self._cached_plugin_expr
        from gaspatchio_core import _internal

        lib = Path(_internal.__file__)  # type: ignore[arg-type]
        self._cached_plugin_expr = register_plugin_function(
            plugin_path=lib,
            function_name="rollforward",
            args=list(self._compiled.plugin_args),
            kwargs=self._compiled.plugin_kwargs,
            is_elementwise=True,
        )
        return self._cached_plugin_expr

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a Polars Expr selecting the per-period values for (state, point)."""
        from gaspatchio_core.rollforward._refs import StateRef

        ref = StateRef(state=state, point=point)
        if ref not in self._compiled.capture_slots:
            msg = (
                f"({state!r}, {point!r}) not in capture slots — declare "
                f"the point or use a state's eop"
            )
            raise KeyError(msg)
        plugin = self._shared_plugin_expr()
        return plugin.struct.field(f"{state}@{point}")

    def increment_for(self, label: str) -> pl.Expr:
        """Return a Polars Expr selecting the per-period delta for a labelled Op."""
        if not self._compiled.ir.track_increments:
            msg = (
                "rf.increment(...) requires the rollforward to be built with "
                "track_increments=True"
            )
            raise ValueError(msg)
        plugin = self._shared_plugin_expr()
        return plugin.struct.field(f"increment_{label}")


__all__ = ["RollforwardCollector"]
