# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A shock handed straight to one table moves that table only as it was written.

``Table.with_shock()`` and ``Table.from_shocks()`` ignored ``shock.table`` and
``shock.column``: a lapse shock applied to mortality moved mortality, and
``column="no_such_column"`` still moved the value column. The table a shock is
applied to is its target, so an untargeted shock is fine; one written for
another table is refused. ``column=`` names a model-point column, which no
table holds, so a shock naming one is refused too, and rows of a table are
confined with ``FilteredShock(where=...)``.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.assumptions import MeltDimension, Table
from gaspatchio.scenarios import FilteredShock, MultiplicativeShock, PipelineShock


@pytest.fixture
def mort() -> Table:
    return Table(
        name="w2i_ws_mort",
        source=pl.DataFrame({"age": [30, 31], "q": [0.01, 0.02]}),
        dimensions={"age": "age"},
        value="q",
    )


def _q(table: Table) -> list[float]:
    return table.to_dataframe().sort("age")["q"].to_list()


def test_a_shock_for_another_table_is_refused_naming_both(mort: Table) -> None:
    shock = MultiplicativeShock(factor=2.0, table="w2i_ws_lapse")
    with pytest.raises(ValueError, match="names table 'w2i_ws_lapse'") as info:
        mort.with_shock(shock)
    assert "applied to table 'w2i_ws_mort'" in str(info.value)


def test_from_shocks_refuses_a_shock_for_another_table(mort: Table) -> None:
    with pytest.raises(ValueError, match="names table 'lapse'"):
        Table.from_shocks(
            mort,
            {"X": [MultiplicativeShock(factor=2.0, table="lapse")]},
            value_column="q",
        )


def test_an_inner_shock_for_another_table_is_refused(mort: Table) -> None:
    shock = PipelineShock(shocks=(MultiplicativeShock(factor=2.0, table="lapse"),))
    with pytest.raises(ValueError, match="names table 'lapse'"):
        mort.with_shock(shock)


def test_an_untargeted_or_self_named_shock_moves_the_table(mort: Table) -> None:
    assert _q(mort.with_shock(MultiplicativeShock(factor=2.0))) == pytest.approx(
        [0.02, 0.04]
    )
    named = MultiplicativeShock(factor=2.0, table="w2i_ws_mort")
    assert _q(mort.with_shock(named)) == pytest.approx([0.02, 0.04])


def test_a_chain_may_keep_naming_the_original_table(mort: Table) -> None:
    shock = MultiplicativeShock(factor=2.0, table="w2i_ws_mort")
    assert _q(mort.with_shock(shock).with_shock(shock)) == pytest.approx([0.04, 0.08])
    tables = Table.from_shocks(mort, {"X": [shock, shock]}, value_column="q")
    assert _q(tables["X"]) == pytest.approx([0.04, 0.08])


@pytest.mark.parametrize("column", ["no_such_column", "q", "age", "female"])
def test_a_column_is_refused_as_a_model_point_target(mort: Table, column: str) -> None:
    """column= names a model-point column; a table holds none, value column or not."""
    with pytest.raises(ValueError, match="column= names a model-point column"):
        mort.with_shock(MultiplicativeShock(factor=2.0, column=column))


def test_a_filter_confines_a_shock_to_some_rows_of_a_wide_table() -> None:
    wide = Table(
        name="w2i_ws_wide",
        source=pl.DataFrame(
            {"age": [30, 31], "male": [0.01, 0.02], "female": [0.005, 0.006]}
        ),
        dimensions={"age": "age", "sex": MeltDimension(["male", "female"], name="sex")},
        value="q",
    )
    confined = wide.with_shock(
        FilteredShock(shock=MultiplicativeShock(factor=2.0), where={"sex": "female"})
    )
    rates = dict(
        confined.to_dataframe()
        .filter(pl.col("age") == 30)
        .select("sex", "q")
        .iter_rows()
    )
    assert rates == pytest.approx({"male": 0.01, "female": 0.01})
