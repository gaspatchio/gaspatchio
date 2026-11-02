# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed mortality wrapper -- MortalityTable.

A thin actuarial-convention wrapper over the existing
:class:`gaspatchio.assumptions.Table`. It does not duplicate Table's
file-loading or lookup mechanics; it adds three audit-relevant pieces of
metadata (``age_basis``, ``structure``, ``select_period``) and routes
``.at(...)`` calls through structure-aware dispatch.

Capabilities:
  - Three structures: ``aggregate``, ``select_ultimate``, ``joint``.
  - ``select_ultimate`` clamps ``duration`` at ``select_period``.
  - Convention-aware ``.at(...)`` validates ``age_basis`` overrides but does
    NOT perform table conversion (cross-basis conversion is not yet
    supported).
  - ``source_sha()`` over a canonical form including ``Table.name``, the
    table's content ``fingerprint()`` and the metadata.

**The convention is on the record, under its own name.** ``.at(...)``
emits one ``mortality.at`` call carrying the structure, the select period
where the structure has one, the age basis, this wrapper's own
``source_sha()`` and the underlying table's identity; the lowering in
``frame/lowering/rules/mortality.py`` rebuilds the clamp and the read from
it. None of that used to reach the record: the clamp arrived as one
engine's rendering of a bounded column, and the three pieces of metadata
arrived not at all -- so two models reading one grid, one on rates built
age last birthday and one age nearest birthday, exported as the same
calculation with the same digest (*Audit by default*).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from gaspatchio._authoring import emit
from gaspatchio._identity import SHA256_PREFIX, canonical_bytes
from gaspatchio._scenario_reads import rebound_read
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.lowering.artefacts import register_table
from gaspatchio.frame.lowering.context import context_for_operands
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.mortality._conventions import (
    validate_age_basis,
    validate_select_period,
    validate_structure,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    import polars as pl

    from gaspatchio._semantic.ir import AttrValue
    from gaspatchio.assumptions._api import Table
    from gaspatchio.mortality._conventions import AgeBasis, Structure

# How the dimension names travel on the node. A ``Call`` attribute is a
# flat typed value (see ``ir.AttrValue``), never a container, so several
# names are comma-joined -- the rendering a join's keys already take. The
# lowering reads them back to pair each argument with the dimension it
# answers for, which is what lets one identifier cover all three
# structures and whatever else the table is keyed by.
_NAME_SEPARATOR = ","


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

        The returned expression cooperates with ``af`` columns in either
        operand order -- the guarantee ``Table.lookup`` already gives, for
        the same reason (gh#67).
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

        return self._emit(
            self._keys(
                age=age,
                age_1=age_1,
                age_2=age_2,
                duration=duration,
                other=other,
            )
        )

    def _keys(
        self,
        *,
        age: pl.Expr | None,
        age_1: pl.Expr | None,
        age_2: pl.Expr | None,
        duration: pl.Expr | None,
        other: dict[str, pl.Expr],
    ) -> dict[str, object]:
        """Return the dimensions this structure reads, in the node's own order.

        The structure's own dimensions first, then whatever else the table
        is keyed by, in the order the caller wrote them. An actuary's
        mistake -- a duration on an aggregate basis, an ``age`` on a joint
        one -- is refused here, at the line they wrote it on.
        """
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
            return {"age": age, **other}

        if self.structure == "select_ultimate":
            if age is None or duration is None:
                msg = (
                    "structure='select_ultimate' requires both age=... and duration=..."
                )
                raise ValueError(msg)
            if self.select_period is None:  # invariant from validate_select_period
                msg = (
                    "internal invariant violation: select_period is None for "
                    "structure='select_ultimate'"
                )
                raise RuntimeError(msg)
            return {"age": age, "duration": duration, **other}

        if self.structure == "joint":
            if age is not None:
                msg = "structure='joint' uses age_1=... and age_2=..., not age=..."
                raise ValueError(msg)
            if age_1 is None or age_2 is None:
                msg = "structure='joint' requires both age_1=... and age_2=..."
                raise ValueError(msg)
            return {"age_1": age_1, "age_2": age_2, **other}

        msg = f"unhandled structure {self.structure!r}"
        raise AssertionError(msg)

    def _emit(self, keys: dict[str, object]) -> pl.Expr:
        """Emit the ``mortality.at`` call this read is, and lower it.

        The node carries the convention rather than the calculation the
        convention implies: the clamp a select and ultimate basis applies
        is stated by ``structure`` and ``select_period`` and rebuilt by the
        registered lowering, instead of standing in the tree as an engine
        fragment nobody can read a select period back out of.

        The underlying table's identity travels in the very attributes
        ``frame/lowering/rules/lookup.py`` sets out -- the name the kernel
        resolves by, and the content hash of the processed frame -- so the
        artifact's account of which bases a model read finds this node
        exactly as it found the lookup that used to stand here. That pair
        is also what the lowering resolves the base by: ``source_sha()``
        is on the node as this wrapper's published identity -- the rates
        and the convention together -- and is not resolved by, because a
        sweep's batches are carried back to their own table by the name and
        content hash a lookup resolves by too.

        Inside a scenario run that shocks the underlying table, the read is
        emitted from this same convention over the table shocked for the
        run's scenarios, keyed by the scenario axis -- the node a model
        handed that table by hand would have written.
        """
        rebound = rebound_read(self.table, keys)
        if rebound is not None:
            table, rebound_keys = rebound
            rebound_basis = replace(self, table=cast("Table", table))
            return rebound_basis._emit_read(rebound_keys)  # noqa: SLF001 -- same class
        return self._emit_read(keys)

    def _emit_read(self, keys: Mapping[str, object]) -> pl.Expr:
        """Emit and lower the ``mortality.at`` call over ``keys``, as written."""
        attrs: list[tuple[str, AttrValue]] = [
            ("mortality", self.source_sha()),
            ("structure", self.structure),
        ]
        if self.select_period is not None:
            attrs.append(("select_period", self.select_period))
        attrs += [
            ("age_basis", self.age_basis),
            ("dimensions", _NAME_SEPARATOR.join(keys)),
            ("table", self.table.name),
            ("table_fingerprint", register_table(self.table)),
        ]
        node = emit.call_node("mortality.at", tuple(keys.values()), tuple(attrs))
        ctx = context_for_operands(keys.values())
        return ProxyAwareExpr.wrap(
            lower_polars(node, ctx),
            node=node,
            parent=None if ctx is None else ctx.frame,
        )

    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this MortalityTable.

        Includes the underlying Table's name, its sorted dimension list and
        its content fingerprint, plus the mortality-specific metadata. Two
        MortalityTables differing in their rates, or only in age_basis,
        structure or select_period, produce different forms and therefore
        different ``source_sha()`` values.
        """
        return mortality_recipe(
            table_name=self.table.name,
            dimensions=self.table.dimensions.keys(),
            fingerprint=self.fingerprint(),
            age_basis=self.age_basis,
            structure=self.structure,
            select_period=self.select_period,
        )

    def fingerprint(self) -> str:
        """Return the content identity of the rates this wrapper reads.

        Exactly the underlying :meth:`Table.fingerprint` -- the hash the
        calculation graph records as the base's ``assumptions[].fingerprint``
        and as the ``table_fingerprint`` of every ``mortality.at`` read. It
        moves when a rate moves and for nothing else; the convention around
        the rates (age basis, structure, select period) is in
        :meth:`source_sha`, not here.
        """
        return self.table.fingerprint()

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        The wrapper's whole identity: the rates (through the underlying
        table's :meth:`fingerprint`), the table's name and dimensions, and the
        convention -- age basis, structure and select period. Two mortality
        tables under one name with different rates therefore never share it.
        It travels on every ``mortality.at`` read as the ``mortality``
        attribute; :meth:`fingerprint` is the rates alone.
        """
        return recipe_sha(self.canonical_form())


def mortality_recipe(  # noqa: PLR0913 -- one argument per member of the form
    *,
    table_name: str,
    dimensions: Iterable[str],
    fingerprint: str,
    age_basis: object,
    structure: object,
    select_period: object,
) -> dict[str, object]:
    """Return a mortality wrapper's canonical form from its members.

    The one place the form is spelled: :meth:`MortalityTable.canonical_form`
    writes it from a live wrapper, and a scenario run's record reads a
    shocked copy back under its base's name from the members a
    ``mortality.at`` read carries.
    """
    return {
        "kind": "MortalityTable",
        "table_name": table_name,
        "table_dimensions": sorted(dimensions),
        "table_fingerprint": fingerprint,
        "age_basis": age_basis,
        "structure": structure,
        "select_period": select_period,
    }


def recipe_sha(form: Mapping[str, object]) -> str:
    """Return ``sha256:<hex>`` over a mortality wrapper's canonical form."""
    digest = hashlib.sha256(canonical_bytes(dict(form))).hexdigest()
    return f"{SHA256_PREFIX}{digest}"


__all__ = ["MortalityTable", "mortality_recipe", "recipe_sha"]
