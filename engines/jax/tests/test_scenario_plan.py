# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario plan's artifact runs on this engine: bound reads and column shocks.

A plan runs the reconciled model unchanged and shocks its targets itself. A
read of a table a shock names is lowered against that table stacked per
scenario, the injected axis bound as a key. An affine shock on a model-point
column reads per-scenario factors keyed by the axis, and any other column
shock is a ``when`` chain over it. All of it is ``lookup``, ``mul``, ``add``,
``when_then`` and ``eq``, so the composed run's executable artifact must run
here and agree with Polars.

The engine is handed what the run was handed: the book crossed with the
axis, before any shock. The column shocks are assignments the artifact
carries, so they are computed here, not read off a frame that already holds
them.
"""

from __future__ import annotations

import json
from datetime import date

import polars as pl

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.assumptions import Table
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.frame.graph import GraphExporter, inspect_execution
from gaspatchio.scenarios import (
    AdditiveShock,
    FilteredShock,
    MultiplicativeShock,
    with_scenarios,
)
from gaspatchio.scenarios._for_each import _BatchRecipe

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4],
        "age": [40, 41, 42, 43],
        "sa": [1000.0, 2000.0, 1500.0, 500.0],
        "valuation_rate": [0.03, 0.04, 0.035, 0.05],
    }
)

SHOCKS = {
    "BASE": [],
    "MORT_UP": [MultiplicativeShock(1.2, table="jax_plan_mortality")],
    "RATE_UP": [AdditiveShock(0.01, column="valuation_rate")],
    "OLD_SA_UP": [
        FilteredShock(MultiplicativeShock(2.0), where={"age": {"gte": 42}}, column="sa")
    ],
}


def _mortality() -> Table:
    return Table(
        name="jax_plan_mortality",
        source=pl.DataFrame({"age": [40, 41, 42, 43], "q": [0.01, 0.02, 0.03, 0.04]}),
        dimensions={"age": "age"},
        value="q",
    )


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Run the reconciled model: its own table, its own read, no door."""
    af.q = _mortality().lookup(age=af.age)
    af.v = 1.0 / (1.0 + af.valuation_rate)
    af.loss = af.sa * af.q * af.v
    return af


def test_a_composed_plan_runs_on_the_engine_and_agrees_with_polars() -> None:
    recipe = _BatchRecipe(
        scenarios=SHOCKS,
        shape="shocks",
        base_tables=None,
        master_seed=None,
        axis=tuple(SHOCKS),
    )
    frame = recipe.compose(ActuarialFrame(BOOK), list(SHOCKS), main)
    document = json.loads(GraphExporter(frame).export(profile="executable"))

    # The plan's own reads are in the artifact: the stacked table bound by
    # the axis, and the per-scenario factors of the affine column shock.
    read = {entry["name"] for entry in document["assumptions"]}
    assert read == {"jax_plan_mortality_stacked", "scenario_shocks__valuation_rate"}

    required = [one.column for one in inspect_execution(document).required_inputs]
    crossed = with_scenarios(ActuarialFrame(BOOK), list(SHOCKS)).collect()
    result = engine_named("jax").run(document, crossed.select(required), FrameSink())

    expected = frame.collect().select("scenario_id", "policy_id", "loss")
    answered = result.columns.select("loss")
    assert answered["loss"].to_list() == expected["loss"].to_list()
    totals = dict(
        expected.group_by("scenario_id").agg(pl.col("loss").sum()).iter_rows()
    )
    assert totals["MORT_UP"] > totals["BASE"] > totals["RATE_UP"]
    assert totals["OLD_SA_UP"] > totals["BASE"]


# --- a compiled rollforward reading a shocked table ---------------------------

PERIODS = 24
RF_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "av_init": [1000.0, 2000.0, 1500.0],
        "attained": [[a + m // 12 for m in range(PERIODS)] for a in (40, 45, 50)],
        "growth": [[0.004] * PERIODS] * 3,
        "db": [[5000.0] * PERIODS] * 3,
    }
)
RF_SHOCKS = {"BASE": [], "COI_UP": [MultiplicativeShock(1.5, table="jax_plan_coi")]}


def _coi(scale: float = 1.0) -> Table:
    return Table(
        name="jax_plan_coi",
        source=pl.DataFrame(
            {
                "age": list(range(40, 60)),
                "c": [scale * (0.01 + 0.001 * i) for i in range(20)],
            }
        ),
        dimensions={"age": "age"},
        value="c",
    )


def _rollforward_model(coi: Table) -> ActuarialFrame:
    """Build the model over ``coi``: the rates are a column the rollforward reads."""

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=PERIODS, frequency="monthly"
        )
        af.coi = coi.lookup(age=af.attained)
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].grow(af["growth"], label="growth").charge(af["coi"], label="coi")
        af.av = compile_rollforward(b).expr_for("av")
        return af

    return model  # type: ignore[return-value]


def test_a_rollforward_reading_a_shocked_table_runs_each_scenario_alone() -> None:
    """The shocked rates reach the kernel per scenario, on both engines.

    A rollforward reads a table through a column of the frame (an operand is
    a bare column), so the plan binds that column's lookup like any other.
    Each scenario's balances equal that scenario run alone over the table
    shocked by hand, on Polars and on this engine.
    """
    recipe = _BatchRecipe(
        scenarios=RF_SHOCKS,
        shape="shocks",
        base_tables=None,
        master_seed=None,
        axis=tuple(RF_SHOCKS),
    )
    frame = recipe.compose(
        ActuarialFrame(RF_BOOK), list(RF_SHOCKS), _rollforward_model(_coi())
    )
    document = json.loads(GraphExporter(frame).export(profile="executable"))
    required = [one.column for one in inspect_execution(document).required_inputs]
    crossed = with_scenarios(ActuarialFrame(RF_BOOK), list(RF_SHOCKS)).collect()
    on_engine = engine_named("jax").run(document, crossed.select(required), FrameSink())

    polars = frame.collect().select("scenario_id", "policy_id", "av")
    assert on_engine.columns["av"].to_list() == polars["av"].to_list()
    for sid, scale in (("BASE", 1.0), ("COI_UP", 1.5)):
        alone = _rollforward_model(_coi(scale))(ActuarialFrame(RF_BOOK)).collect()
        ran = polars.filter(pl.col("scenario_id") == sid)
        assert ran["av"].to_list() == alone["av"].to_list(), sid
