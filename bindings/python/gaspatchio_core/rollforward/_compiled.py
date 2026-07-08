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

    from gaspatchio_core.rollforward._ir import IR
    from gaspatchio_core.rollforward._refs import StateRef


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
        from gaspatchio_core.rollforward._registry import hidden_column_name

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

        from gaspatchio_core import _internal

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

        from gaspatchio_core.rollforward import _registry

        _registry.register(self._hidden_column, self._cached_plugin_expr)
        return pl.col(self._hidden_column).struct.field(field_name)

    def expr_for(self, state: str, *, point: str = "eop") -> pl.Expr:
        """Return a Polars Expr selecting the per-period values for (state, point).

        All extractions from one compiled rollforward share a single kernel
        call when assigned to an ``ActuarialFrame``::

            af.fund = compiled.expr_for("fund")
            af.gmdb = compiled.expr_for("gmdb")  # no second kernel run
        """
        from gaspatchio_core.rollforward._refs import StateRef

        ref = StateRef(state=state, point=point)
        if ref not in self.capture_slots:
            msg = (
                f"({state!r}, {point!r}) not in capture slots — declare "
                f"the point or use a state's eop"
            )
            raise KeyError(msg)
        return self._field_expr(f"{state}@{point}")

    def increment_for(self, label: str) -> pl.Expr:
        """Return a Polars Expr selecting the per-period delta for a labelled Op."""
        if not self.ir.track_increments:
            msg = (
                "rf.increment(...) requires the rollforward to be built with "
                "track_increments=True"
            )
            raise ValueError(msg)
        return self._field_expr(f"increment_{label}")

    def canonical_form(self) -> dict[str, Any]:
        """Return a stable, deterministic dict describing the model structure.

        Two compiled rollforwards with the same Op chain (in the same order),
        same states, same Schedule canonical-form, and same configuration
        produce equal canonical-form dicts. Column-name aliases inside Op
        expressions are reduced to ``str(expr)``, so renaming a column does
        not change the canonical form.
        """
        from gaspatchio_core.rollforward._canonical import canonical_form

        return canonical_form(self.ir)

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint of the canonical form.

        Stable across runs and across machines for an unchanged model.
        Suitable for governance metadata and run logs.
        """
        from gaspatchio_core.rollforward._fingerprint import spec_fingerprint

        return spec_fingerprint(self.ir)

    def explain(self) -> str:
        """Return a multi-line human-readable summary of the model.

        Lists states, points, schedule, transitions in order, and the
        cross-cutting configuration (lapse, contract boundary, increment
        tracking). Plain text — fits in audit reports and TRACE logs.
        """
        from gaspatchio_core.rollforward._explain import explain

        return explain(self.ir)


__all__ = ["CompiledRollforward"]
