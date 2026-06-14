# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed mortality wrapper -- MortalityTable.

A thin actuarial-convention wrapper over the existing
:class:`gaspatchio_core.assumptions.Table`. It does not duplicate Table's
file-loading or lookup mechanics; it adds three audit-relevant pieces of
metadata (``age_basis``, ``structure``, ``select_period``) and routes
``.at(...)`` calls through structure-aware dispatch.

Capabilities:
  - Three structures: ``aggregate``, ``select_ultimate``, ``joint``.
  - ``select_ultimate`` clamps ``duration`` at ``select_period``.
  - Convention-aware ``.at(...)`` validates ``age_basis`` overrides but does
    NOT perform table conversion (cross-basis conversion is not yet
    supported).
  - ``source_sha()`` over a canonical form including ``Table.name`` plus
    the metadata.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.mortality._conventions import (
    validate_age_basis,
    validate_select_period,
    validate_structure,
)

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.mortality._conventions import AgeBasis, Structure


@dataclass(frozen=True)
class MortalityTable:
    """Convention-aware wrapper over an existing :class:`Table`."""

    table: Table
    age_basis: AgeBasis
    structure: Structure
    select_period: int | None = None

    def __post_init__(self) -> None:
        """Validate metadata; raises ValueError on any inconsistency."""
        validate_age_basis(self.age_basis)
        validate_structure(self.structure)
        validate_select_period(self.structure, self.select_period)

    def at(
        self,
        *,
        age: pl.Expr | None = None,
        age_1: pl.Expr | None = None,
        age_2: pl.Expr | None = None,
        duration: pl.Expr | None = None,
        age_basis: AgeBasis | None = None,
        **other: pl.Expr,
    ) -> pl.Expr:
        """Convention-aware lookup.

        The accepted kwargs depend on ``self.structure``:
          - ``aggregate``: ``age`` (required), plus any extra dimensions
            on the underlying Table (gender, smoker, etc.) via ``**other``.
          - ``select_ultimate``: ``age`` and ``duration`` both required.
          - ``joint``: ``age_1`` and ``age_2`` both required.

        ``age_basis`` is validated against ``self.age_basis``; supplying a
        different basis raises ``ValueError`` (automatic cross-basis
        conversion is not yet supported).
        """
        if age_basis is not None:
            validate_age_basis(age_basis)
            if age_basis != self.age_basis:
                msg = (
                    f"requested age_basis={age_basis!r} but table's age_basis "
                    f"is {self.age_basis!r}; cross-basis conversion is not "
                    f"yet supported"
                )
                raise ValueError(msg)

        if self.structure == "aggregate":
            if age is None:
                msg = "aggregate structure requires age=..."
                raise ValueError(msg)
            if duration is not None:
                msg = (
                    "aggregate structure does not accept duration=...; "
                    "use structure='select_ultimate' if duration is meaningful"
                )
                raise ValueError(msg)
            return self.table.lookup(age=age, **other)

        if self.structure == "select_ultimate":
            return self._at_select_ultimate(
                age=age,
                duration=duration,
                **other,
            )

        if self.structure == "joint":
            if age is not None:
                msg = "structure='joint' uses age_1=... and age_2=..., not age=..."
                raise ValueError(msg)
            return self._at_joint(age_1=age_1, age_2=age_2, **other)

        msg = f"unhandled structure {self.structure!r}"
        raise AssertionError(msg)

    def _at_select_ultimate(
        self,
        *,
        age: pl.Expr | None,
        duration: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        """Look up via age + duration, clamping duration at select_period.

        Accepts both ``pl.Expr`` and gaspatchio ``ColumnProxy`` / ``ExpressionProxy``
        (any object with a ``_to_expr()`` method). ColumnProxy objects are
        resolved to ``pl.Expr`` before the clamping expression is built.

        After timeline creation, duration is a list column. The clamping uses
        the gaspatchio ``list_clip`` plugin (same backend used by
        ``ColumnProxy.clip()``), which handles list-typed columns correctly.
        For plain (non-list) ``pl.Expr`` inputs, ``list_clip`` also degrades
        gracefully — the plugin accepts scalar and list bounds uniformly.
        """
        if age is None or duration is None:
            msg = "structure='select_ultimate' requires both age=... and duration=..."
            raise ValueError(msg)
        if self.select_period is None:  # invariant from validate_select_period
            msg = (
                "internal invariant violation: select_period is None for "
                "structure='select_ultimate'"
            )
            raise RuntimeError(msg)
        # Resolve ColumnProxy / ExpressionProxy -> pl.Expr via the established
        # _to_expr() bridge — same idiom used throughout the column module.
        duration_expr: pl.Expr = (
            duration._to_expr() if hasattr(duration, "_to_expr") else duration  # noqa: SLF001
        )
        age_expr: pl.Expr = age._to_expr() if hasattr(age, "_to_expr") else age  # noqa: SLF001
        other_exprs: dict[str, pl.Expr] = {
            k: v._to_expr() if hasattr(v, "_to_expr") else v  # noqa: SLF001
            for k, v in other.items()
        }
        # Clamp duration at select_period.
        #
        # Two contexts arise:
        #   1. Scalar (non-list) columns — e.g., plain DataFrames in tests.
        #      Use pl.Expr.clip(upper_bound=N) which works on numeric scalars.
        #   2. List columns — after ActuarialFrame.date.create_timeline()
        #      each duration column is a list<i64>. pl.Expr.clip() raises
        #      "clip only supports physical numeric types" on list dtypes.
        #      Use list_clip (the Rust plugin that backs ColumnProxy.clip())
        #      which handles list-typed columns element-wise.
        #
        # We detect the list context by checking whether the resolved expression
        # is a ColumnProxy / ExpressionProxy originating from an ActuarialFrame
        # (its internal _expr will already be a list expression), OR whether the
        # caller passed a raw pl.col(...) into a DataFrame with list columns.
        # The lightweight heuristic: prefer list_clip when the caller passed a
        # ColumnProxy (i.e., had _to_expr), fall back to scalar clip otherwise.
        if hasattr(duration, "_to_expr"):
            # Came from an ActuarialFrame — post-timeline, list dtype expected.
            from gaspatchio_core.polars_backend.plugins import list_clip

            clamped_duration = list_clip(
                duration_expr,
                pl.lit(float("-inf")),
                pl.lit(float(self.select_period)),
            )
        else:
            # Scalar pl.Expr (e.g., pl.col("duration") on a plain DataFrame).
            clamped_duration = duration_expr.clip(upper_bound=self.select_period)
        return self.table.lookup(age=age_expr, duration=clamped_duration, **other_exprs)

    def _at_joint(
        self,
        *,
        age_1: pl.Expr | None,
        age_2: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        """Look up via age_1 and age_2."""
        if age_1 is None or age_2 is None:
            msg = "structure='joint' requires both age_1=... and age_2=..."
            raise ValueError(msg)
        return self.table.lookup(age_1=age_1, age_2=age_2, **other)

    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this MortalityTable.

        Includes the underlying Table's name and sorted dimension list, plus
        the mortality-specific metadata. Two MortalityTables differing only
        in age_basis, structure, or select_period produce different forms
        and therefore different ``source_sha()`` values.
        """
        return {
            "kind": "MortalityTable",
            "table_name": self.table.name,
            "table_dimensions": sorted(self.table.dimensions.keys()),
            "age_basis": self.age_basis,
            "structure": self.structure,
            "select_period": self.select_period,
        }

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        Note: ``source_sha`` does NOT hash the underlying Table's
        data payload (file content / DataFrame rows). Two runs with the same
        Table.name but different file contents produce identical SHAs —
        close this gap by supplying distinct Table names per data revision
        until a Table-side ``content_sha()`` is available.
        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"


__all__ = ["MortalityTable"]
