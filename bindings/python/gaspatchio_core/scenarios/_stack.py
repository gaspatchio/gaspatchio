# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: stack_shocked_table - scenario-stacked Tables for batched runs.
# ABOUTME: Used by for_each_scenario when batch_size > 1 with shock-dict shape.

"""Helper for batched per-scenario shock composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.scenarios.shocks import Shock


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
        New Table with the additional scenario_id dimension.

    """
    from gaspatchio_core.assumptions import Table

    base_dimensions = base._dimensions  # type: ignore[attr-defined]  # noqa: SLF001
    if "scenario_id" in base_dimensions:
        base_name = base._name  # type: ignore[attr-defined]  # noqa: SLF001
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

    base_df = base._materialised_df()  # type: ignore[attr-defined]  # noqa: SLF001
    value_col = base._value  # type: ignore[attr-defined]  # noqa: SLF001

    parts: list[pl.DataFrame] = []
    for sid, shocks in per_scenario_shocks.items():
        value_expr = pl.col(value_col)
        for shock in shocks:
            value_expr = shock.to_expression(value_expr)
        scen_df = base_df.with_columns(
            value_expr.alias(value_col),
            pl.lit(sid).alias("scenario_id"),
        )
        parts.append(scen_df)

    stacked_df = pl.concat(parts, how="vertical_relaxed")

    new_dims: dict[str, str] = {
        "scenario_id": "scenario_id",
        **{name: name for name in base._dimensions},  # type: ignore[attr-defined]  # noqa: SLF001
    }
    return Table(
        name=f"{base._name}_stacked",  # type: ignore[attr-defined]  # noqa: SLF001
        source=stacked_df,
        dimensions=new_dims,  # type: ignore[arg-type]
        value=value_col,
        validate=False,
    )


__all__ = ["stack_shocked_table"]
