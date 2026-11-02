# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table rebuilt for a shock keeps every argument the user built it with.

profit-testing-r3 built a one-row String-keyed table with
``storage_mode="hash"`` (the ``auto`` layout cannot encode it). A scenario
run stacked it as ``<name>_stacked`` with ``storage_mode`` left at ``auto``,
so the table that built fine failed inside the framework; ``with_shock`` and
``Table.from_shocks`` rebuilt the same way. They also dropped the table's
``on_missing`` policy (so a table declared ``on_missing="nan"`` raised on a
miss once shocked) and stacking dropped its metadata.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio.assumptions import Table
from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum
from gaspatchio.scenarios._stack import stack_shocked_table
from gaspatchio.scenarios.shocks import MultiplicativeShock

_META = {"source": "reserving basis 2026"}


def _one_row_hash_table(name: str) -> Table:
    """One row, a String key: builds only under storage_mode='hash'."""
    return Table(
        name=name,
        source=pl.DataFrame({"item": ["zeroize_reserves"], "flag": [1.0]}),
        dimensions={"item": "item"},
        value="flag",
        storage_mode="hash",
        on_missing="nan",
        metadata=_META,
    )


def _miss_is_nan(table: Table, **keys: object) -> bool:
    """Look up a key the table does not hold; True where the miss reads NaN."""
    frame = pl.DataFrame({k: [v] for k, v in keys.items()})
    exprs = {k: pl.col(k) for k in keys}
    out = frame.select(table.lookup(**exprs).alias("r"))["r"][0]
    return out is not None and math.isnan(out)


def test_with_shock_keeps_storage_mode_on_missing_and_metadata() -> None:
    """with_shock rebuilds under the user's storage_mode and miss policy."""
    shocked = _one_row_hash_table("rebuilt_args_ws").with_shock(
        MultiplicativeShock(factor=2.0)
    )
    assert shocked.to_dataframe()["flag"].to_list() == [2.0]
    assert _miss_is_nan(shocked, item="no_such_item")
    assert shocked.metadata == _META


def test_from_shocks_keeps_storage_mode_on_missing_and_metadata() -> None:
    """Table.from_shocks rebuilds every scenario's table the same way."""
    tables = Table.from_shocks(
        _one_row_hash_table("rebuilt_args_fs"),
        {"BASE": [], "UP": [MultiplicativeShock(factor=2.0)]},
        value_column="flag",
    )
    for table in tables.values():
        assert _miss_is_nan(table, item="no_such_item")
        assert table.metadata == _META


def test_stacking_keeps_storage_mode_on_missing_and_metadata() -> None:
    """The scenario-stacked table keeps the user's arguments."""
    stacked = stack_shocked_table(
        _one_row_hash_table("rebuilt_args_st"),
        {"BASE": [], "UP": [MultiplicativeShock(factor=2.0)]},
    )
    assert sorted(stacked.to_dataframe()["flag"].to_list()) == [1.0, 2.0]
    assert _miss_is_nan(stacked, scenario_id="BASE", item="no_such_item")
    assert stacked.metadata == _META


@pytest.mark.parametrize("batch_size", [1, 2])
def test_scenario_run_over_a_one_row_hash_table(batch_size: int) -> None:
    """The profit-testing-r3 shape runs end to end at any batch size."""
    table = _one_row_hash_table("rebuilt_args_run")

    def model_fn(af):  # noqa: ANN202
        af.flag = table.lookup(item=af.item)
        return af

    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=2.0, table="rebuilt_args_run")],
        },
        base_tables={"rebuilt_args_run": table},
        aggregations=(Sum("flag").alias("total").over("scenario_id"),),
    )
    result = plan.run(
        ActuarialFrame({"policy_id": [1], "item": ["zeroize_reserves"]}),
        model_fn,
        batch_size=batch_size,
    )
    totals = dict(result.aggregations["total"].iter_rows())
    assert totals == {"BASE": 1.0, "UP": 2.0}
