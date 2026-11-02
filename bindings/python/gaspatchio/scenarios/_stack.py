# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: stack_shocked_table - scenario-stacked Tables for batched runs.
# ABOUTME: Built for a run's reads of a table a shock names, stacked or alone.

"""Helper for batched per-scenario shock composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio.scenarios._targets import check_conditions_select

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.assumptions import Table
    from gaspatchio.assumptions._dimensions import Dimension
    from gaspatchio.scenarios.shocks import Shock


def stack_shocked_table(
    base: Table,
    per_scenario_shocks: dict[str, list[Shock]],
) -> Table:
    """Stack a base Table with ``scenario_id`` as an extra dimension.

    For each scenario, applies the per-scenario shock list (possibly empty)
    to the value column, then concatenates with a ``scenario_id`` column.
    The resulting Table has dimensions = {scenario_id, **base._dimensions}.

    Args:
        base: Source assumption table.
        per_scenario_shocks: Maps scenario_id -> list of Shocks to apply.
            Empty list = base case (no shock).

    Returns:
        New Table with the additional scenario_id dimension, built with the
        base table's ``storage_mode``, ``on_missing`` and metadata.

    """
    # At module scope this is a cycle: gaspatchio.assumptions._api imports
    # gaspatchio.scenarios.shocks, whose package __init__ loads _for_each and
    # then this module while gaspatchio.assumptions is still initialising.
    from gaspatchio.assumptions import Table  # noqa: PLC0415 -- cycle, above
    from gaspatchio.assumptions._processing import (  # noqa: PLC0415 -- cycle, above
        _in_its_kinds,
    )

    base_dimensions = base._dimensions  # noqa: SLF001
    if "scenario_id" in base_dimensions:
        base_name = base._name  # noqa: SLF001
        msg = (
            f"Table '{base_name}' already carries 'scenario_id' as a "
            f"dimension — stacking would stamp one batch key over every "
            f"original scenario's rows, silently collapsing the axis.\n\n"
            f"A shocks-dict ScenarioRun stacks each base table per scenario, "
            f"so base tables must be scenario-invariant. Either:\n"
            f"  - keep the table scenario-invariant and express the "
            f"per-scenario differences as shocks, or\n"
            f"  - pass the scenario-keyed table through the id-list or "
            f"drivers shapes, where base_tables reach the model untouched."
        )
        raise ValueError(msg)

    base_df = base._materialised_df()  # noqa: SLF001
    value_col = base._value  # noqa: SLF001

    parts: list[pl.DataFrame] = []
    for sid, shocks in per_scenario_shocks.items():
        value_expr = pl.col(value_col)
        for shock in shocks:
            check_conditions_select(f"Scenario {sid!r}", shock, base.name, base_df)
            value_expr = shock.to_expression(value_expr)
        scen_df = base_df.with_columns(
            value_expr.alias(value_col),
            pl.lit(sid).alias("scenario_id"),
        )
        parts.append(scen_df)

    stacked_df = pl.concat(parts, how="vertical_relaxed")

    # The stacked frame is the processed one, already renamed to the
    # dimension names; rebuild from it the way a shocked copy is rebuilt, so
    # a key declared text stays text in every scenario's slice.
    new_dims: dict[str, str | Dimension] = {
        "scenario_id": "scenario_id",
        **base._rebuild_dimensions(),  # noqa: SLF001
    }
    # Built the way the user built the base: its storage_mode, on_missing
    # policy and metadata. A one-row String key the user built under
    # storage_mode="hash" is a one-row String key again at batch_size=1.
    stacked = Table(
        name=f"{base._name}_stacked",  # noqa: SLF001
        source=_in_its_kinds(stacked_df, base._key_kinds),  # noqa: SLF001
        dimensions=new_dims,
        value=value_col,
        validate=False,
        **base._rebuild_arguments(),  # noqa: SLF001
    )
    stacked._carry_the_source_of(  # noqa: SLF001
        base,
        {
            "step": "shocked",
            "column": value_col,
            "by": _per_scenario(per_scenario_shocks),
        },
        {"step": "stacked", "column": "scenario_id"},
    )
    return stacked


def shocked_table(
    base: Table, shocks: Sequence[Shock], *, scenario: object = None
) -> Table:
    """Return ``base`` with ``shocks`` applied in order, as one scenario reads it alone.

    The table a single scenario's own composition reads: the same rows, the
    value column moved, no scenario axis. It is built under
    ``<name>_shocked`` so the base it came from stays registered under its
    own name for every other read, and with the base's ``storage_mode``,
    ``on_missing`` and metadata, as a stacked table is. ``scenario`` is the
    scenario it is shocked for, as a refusal names it.
    """
    from gaspatchio.assumptions import Table  # noqa: PLC0415 -- cycle, above
    from gaspatchio.assumptions._processing import (  # noqa: PLC0415 -- cycle, above
        _in_its_kinds,
    )

    value_col = base._value  # noqa: SLF001
    base_df = base._materialised_df()  # noqa: SLF001
    who = "A shock" if scenario is None else f"Scenario {scenario!r}"
    value_expr = pl.col(value_col)
    for shock in shocks:
        check_conditions_select(who, shock, base.name, base_df)
        value_expr = shock.to_expression(value_expr)
    shocked = Table(
        name=f"{base._name}_shocked",  # noqa: SLF001
        source=_in_its_kinds(
            base_df.with_columns(value_expr.alias(value_col)),
            base._key_kinds,  # noqa: SLF001
        ),
        dimensions=base._rebuild_dimensions(),  # noqa: SLF001
        value=value_col,
        validate=False,
        **base._rebuild_arguments(),  # noqa: SLF001
    )
    shocked._carry_the_source_of(  # noqa: SLF001
        base,
        {
            "step": "shocked",
            "column": value_col,
            "by": "; ".join(shock.describe() for shock in shocks) or "no shock",
        },
    )
    return shocked


def _per_scenario(per_scenario_shocks: dict[str, list[Shock]]) -> str:
    """Say each scenario's shocks in words, one scenario after another."""
    return "; ".join(
        f"{scenario}: "
        + (", ".join(shock.describe() for shock in shocks) or "no shock")
        for scenario, shocks in per_scenario_shocks.items()
    )


__all__ = ["shocked_table", "stack_shocked_table"]
