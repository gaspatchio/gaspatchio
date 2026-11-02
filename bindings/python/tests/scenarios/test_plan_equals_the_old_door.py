# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The plan binding its targets gives the numbers the scenario door gave, exactly.

Two model shapes, from independently built models. A vm20-shaped model: a valuation
rate the conversion skill keeps as a model-point column, mortality and lapse
tables, a monthly projection. A gmdb-shaped model: the Makeham parameters and
the risk-free rate, which gmdb-r3 moved into a ``param -> value`` table after
reconciling, so that a plan could shock them.

The door is today's explicit form, written out here: every base table stacked
per scenario, the axis passed to every lookup by the model. The plan's form is
the reconciled ``main(af)`` under ``plan.run``. They agree bit for bit at every
batch size, and the gmdb reshape is shown unnecessary: shocking the parameter
in its table and shocking it as a column give the same numbers.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._table_lifecycle import framework_owned_tables
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import (
    AdditiveShock,
    FilteredShock,
    MultiplicativeShock,
    ScenarioRun,
    Sum,
    for_each_scenario,
)
from gaspatchio.scenarios._stack import stack_shocked_table
from gaspatchio.scenarios.shocks import Shock

_AGG = (Sum("reserve").alias("reserve").over("scenario_id"),)


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "issue_age": [40, 45, 50, 55],
            "sum_assured": [1e5, 2e5, 1.5e5, 5e4],
            "term_months": [24, 36, 12, 30],
            "valuation_rate": [0.045, 0.045, 0.045, 0.045],
        }
    )


def _vm20_tables() -> dict[str, Table]:
    ages = list(range(40, 60))
    return {
        "door_vm20_mort": Table(
            name="door_vm20_mort",
            source=pl.DataFrame(
                {"age": ages, "q": [0.001 * (1.08 ** (a - 40)) for a in ages]}
            ),
            dimensions={"age": "age"},
            value="q",
        ),
        "door_vm20_lapse": Table(
            name="door_vm20_lapse",
            source=pl.DataFrame({"year": [0, 1, 2, 3], "w": [0.08, 0.06, 0.05, 0.04]}),
            dimensions={"year": "year"},
            value="w",
        ),
    }


def _vm20(af: ActuarialFrame, tables: dict[str, Table], axis: dict) -> ActuarialFrame:
    """The vm20-shaped calculation, reading ``tables`` with ``axis`` keys."""
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )
    af.year = af.month // 12
    af.age = af.issue_age + af.year
    af.q = tables["door_vm20_mort"].lookup(age=af.age, **axis)
    af.w = tables["door_vm20_lapse"].lookup(year=af.year, **axis)
    af.decrement = 1.0 - (1.0 - af.q / 12.0) * (1.0 - af.w / 12.0)
    af.in_force = af.decrement.projection.cumulative_survival()
    af.v = (1.0 + af.valuation_rate) ** (-(af.month + 1) / 12.0)
    af.claims = af.sum_assured * af.in_force * af.q / 12.0
    af.reserve = (af.claims * af.v).list.sum()
    return af


def vm20_main(af: ActuarialFrame) -> ActuarialFrame:
    """The reconciled model: its own tables, no axis anywhere."""
    return _vm20(af, _vm20_tables(), {})


def _door(
    af: ActuarialFrame,
    scenarios: dict[str, list[Shock]],
    calculation,  # noqa: ANN001 -- one of the shaped calculations above
    tables: dict[str, Table],
) -> dict[str, float]:
    """Run ``scenarios`` the old way: every table stacked, the axis passed by hand."""
    # Stacked under the run's own names, on the lifecycle the old run used.
    with framework_owned_tables():
        stacked = {
            name: stack_shocked_table(
                table,
                {
                    sid: [s for s in shocks if s.table == name]
                    for sid, shocks in scenarios.items()
                },
            )
            for name, table in tables.items()
        }

    def model_fn(frame, *, tables, drivers):  # noqa: ANN001, ANN202, ARG001
        return calculation(frame, stacked, {"scenario_id": frame.scenario_id})

    result = for_each_scenario(
        af,
        list(scenarios),
        model_fn,
        aggregations=_AGG,
        batch_size=len(scenarios),
    )
    return dict(result.aggregations["reserve"].iter_rows())


_VM20_SHOCKS: dict[str, list[Shock]] = {
    "BASE": [],
    "MORT_UP_15": [MultiplicativeShock(1.15, table="door_vm20_mort")],
    "EARLY_LAPSE_DOWN": [
        FilteredShock(
            MultiplicativeShock(0.5),
            where={"year": {"lte": 1}},
            table="door_vm20_lapse",
        )
    ],
    "BOTH": [
        MultiplicativeShock(1.15, table="door_vm20_mort"),
        MultiplicativeShock(0.8, table="door_vm20_lapse"),
    ],
}


@pytest.mark.parametrize("batch_size", [1, 2, "auto"])
def test_vm20_shaped_plan_equals_the_door_bit_for_bit(batch_size: int | str) -> None:
    door = _door(ActuarialFrame(_book()), _VM20_SHOCKS, _vm20, _vm20_tables())
    plan = ScenarioRun(shocks=_VM20_SHOCKS, aggregations=_AGG)
    bound = plan.run(ActuarialFrame(_book()), vm20_main, batch_size=batch_size)  # type: ignore[arg-type]
    assert dict(bound.aggregations["reserve"].iter_rows()) == door
    assert door["MORT_UP_15"] > door["BASE"]


# --- gmdb: the parameter table the room built was never needed --------------


def _params() -> Table:
    return Table(
        name="door_gmdb_params",
        source=pl.DataFrame(
            {"param": ["makeham_a", "makeham_b", "rfr"], "value": [5e-4, 7.5e-5, 0.03]}
        ),
        dimensions={"param": "param"},
        value="value",
    )


def _gmdb(af: ActuarialFrame, a, b, rfr) -> ActuarialFrame:  # noqa: ANN001 -- operands
    """A Makeham death rate and a risk-free discount, over one year."""
    af.q = a + b * 1.1**af.issue_age
    af.v = 1.0 / (1.0 + rfr)
    af.reserve = af.sum_assured * af.q * af.v
    return af


def gmdb_from_the_param_table(af: ActuarialFrame) -> ActuarialFrame:
    """gmdb-r3 after the reshape: every parameter read from a one-row-per-name table."""
    params = _params()
    return _gmdb(
        af,
        params.lookup(param="makeham_a"),
        params.lookup(param="makeham_b"),
        params.lookup(param="rfr"),
    )


def gmdb_reconciled(af: ActuarialFrame) -> ActuarialFrame:
    """gmdb as reconciled: the parameters are model-point columns."""
    return _gmdb(af, af.makeham_a, af.makeham_b, af.rfr)


def _gmdb_book() -> ActuarialFrame:
    return ActuarialFrame(
        _book().with_columns(
            pl.lit(5e-4).alias("makeham_a"),
            pl.lit(7.5e-5).alias("makeham_b"),
            pl.lit(0.03).alias("rfr"),
        )
    )


def _on(param: str, shock: Shock) -> Shock:
    return FilteredShock(shock, where={"param": param}, table="door_gmdb_params")


@pytest.mark.parametrize("batch_size", [1, 2, "auto"])
def test_a_param_table_shock_and_a_column_shock_agree_bit_for_bit(
    batch_size: int | str,
) -> None:
    by_table = ScenarioRun(
        shocks={
            "BASE": [],
            "RFR_UP": [_on("rfr", AdditiveShock(0.01))],
            "MAKEHAM_B_UP": [_on("makeham_b", MultiplicativeShock(1.1))],
        },
        aggregations=_AGG,
    )
    by_column = ScenarioRun(
        shocks={
            "BASE": [],
            "RFR_UP": [AdditiveShock(0.01, column="rfr")],
            "MAKEHAM_B_UP": [MultiplicativeShock(1.1, column="makeham_b")],
        },
        aggregations=_AGG,
    )
    tabled = by_table.run(
        _gmdb_book(), gmdb_from_the_param_table, batch_size=batch_size
    )  # type: ignore[arg-type]
    columned = by_column.run(_gmdb_book(), gmdb_reconciled, batch_size=batch_size)  # type: ignore[arg-type]
    totals = dict(tabled.aggregations["reserve"].iter_rows())
    assert totals == dict(columned.aggregations["reserve"].iter_rows())
    assert totals["RFR_UP"] < totals["BASE"] < totals["MAKEHAM_B_UP"]
