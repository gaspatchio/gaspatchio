# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Declared output dtype of the lookup plugin must match the runtime dtype.

Regression tests for the ``List(Float64)`` mislabel: ``lookup_output_type``
unconditionally declared a list dtype, while scalar-key lookups return a flat
``Float64`` at runtime. The stale declaration poisoned the schema cache and
misrouted shape-dependent operations (``when().otherwise()`` lowering and
scalar-last arithmetic both raised SchemaError naming innocent columns).
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table


@pytest.fixture(scope="module")
def age_table() -> Table:
    return Table(
        name="dtype_age_rates",
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )


def test_scalar_key_lookup_declared_dtype_matches_runtime(age_table: Table) -> None:
    lf = pl.LazyFrame({"age": [30, 40]})
    expr = age_table.lookup(age=pl.col("age")).alias("rate")
    declared = lf.with_columns(expr).collect_schema()["rate"]
    collected = lf.with_columns(expr).collect()
    assert collected["rate"].dtype == pl.Float64
    assert declared == pl.Float64
    assert collected["rate"].to_list() == pytest.approx([0.001, 0.002])


def test_list_key_lookup_declared_dtype_stays_list(age_table: Table) -> None:
    lf = pl.LazyFrame({"ages": [[30, 40], [40, 50]]})
    expr = age_table.lookup(age=pl.col("ages")).alias("rates")
    declared = lf.with_columns(expr).collect_schema()["rates"]
    collected = lf.with_columns(expr).collect()
    assert collected["rates"].dtype == pl.List(pl.Float64)
    assert declared == pl.List(pl.Float64)
    assert collected["rates"].to_list()[0] == pytest.approx([0.001, 0.002])


def test_when_otherwise_with_scalar_key_lookup() -> None:
    # MPI F-04: scalar `then` + scalar-key lookup `otherwise` raised
    # SchemaError ("expected List, got f64") because the mislabelled dtype
    # routed the conditional through the list kernel.
    scenario_table = Table(
        name="dtype_rate_by_scenario",
        source=pl.DataFrame({"scenario_num": [1, 2, 3], "rate": [0.10, 0.20, 0.30]}),
        dimensions={"scenario_num": "scenario_num"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "scenario_num": [-1, 1, 2]})
    )
    af.overlay = (
        when(af.scenario_num == -1)
        .then(0.0)
        .otherwise(scenario_table.lookup(scenario_num=af.scenario_num))
    )
    out = af.collect()
    assert out["overlay"].to_list() == pytest.approx([0.0, 0.10, 0.20])


def test_scalar_last_arithmetic_after_scalar_key_lookup(age_table: Table) -> None:
    # F13: `(af.col * lookup) * 0.97` raised SchemaError naming an innocent
    # column; only the scalar-first ordering worked.
    af = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100.0, 200.0, 300.0], "age": [30, 40, 50]})
    )
    af.premium = (af.sum_assured * age_table.lookup(age=af.age)) * 0.97
    out = af.collect()
    assert out["premium"].to_list() == pytest.approx(
        [100.0 * 0.001 * 0.97, 200.0 * 0.002 * 0.97, 300.0 * 0.003 * 0.97]
    )
