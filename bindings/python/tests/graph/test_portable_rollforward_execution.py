# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the bounded portable BOP/EOP rollforward form."""

from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.rollforward import (
    CompiledRollforward,
    RollforwardBuilder,
    compile_rollforward,
)
from gaspatchio.schedule import Schedule
from tests.rollforward.conftest import _standalone_state_expr


def _schedule(periods: int) -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=periods, frequency="1M"
    )


def _machine(frame: ActuarialFrame, periods: int) -> CompiledRollforward:
    builder = RollforwardBuilder(
        states={"alpha": frame.alpha_init, "beta": frame.beta_init},
        schedule=_schedule(periods),
    )
    builder["alpha"].add(frame.scalar_add, label="alpha_add")
    builder["alpha"].subtract(frame.list_subtract, label="alpha_subtract")
    builder["alpha"].charge(frame.list_rate, label="alpha_charge")
    builder["beta"].add(pl.col("alpha@bop"), label="beta_bop")
    builder["beta"].subtract(frame.scalar_subtract, label="beta_subtract")
    builder["beta"].add(pl.col("alpha@eop"), label="beta_eop")
    builder["beta"].charge(frame.scalar_rate, label="beta_charge")
    return compile_rollforward(builder)


def _points(periods: int, *, rows: int = 1) -> pl.DataFrame:
    schema = {
        "alpha_init": pl.Float64,
        "beta_init": pl.Float64,
        "scalar_add": pl.Float64,
        "list_subtract": pl.List(pl.Float64),
        "list_rate": pl.List(pl.Float64),
        "scalar_subtract": pl.Float64,
        "scalar_rate": pl.Float64,
    }
    if rows == 0:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(
        {
            "alpha_init": [100.0],
            "beta_init": [10.0],
            "scalar_add": [10.0],
            "list_subtract": [[1.0, 2.0, 3.0][:periods]],
            "list_rate": [[0.1, 0.0, -0.2][:periods]],
            "scalar_subtract": [3.0],
            "scalar_rate": [0.02],
        },
        schema=schema,
    )


def test_scalar_list_and_ordered_bop_eop_reads_are_observable() -> None:
    frame = ActuarialFrame(_points(3))
    compiled = _machine(frame, 3)
    frame.alpha_shared = compiled.expr_for("alpha")
    frame.beta_shared = compiled.expr_for("beta")
    frame.alpha_unshared = _standalone_state_expr(compiled, "alpha")
    frame.beta_unshared = _standalone_state_expr(compiled, "beta")

    values = frame.collect()
    alpha = [98.1, 106.1, 135.72]
    beta = [200.998, 394.15404, 620.3145592]
    assert values["alpha_shared"].to_list()[0] == pytest.approx(alpha)
    assert values["beta_shared"].to_list()[0] == pytest.approx(beta)
    assert values["alpha_unshared"].to_list() == values["alpha_shared"].to_list()
    assert values["beta_unshared"].to_list() == values["beta_shared"].to_list()


@pytest.mark.parametrize(("periods", "rows", "expected"), [(0, 1, [[]]), (3, 0, [])])
def test_zero_axis_preserves_list_float_output(
    periods: int, rows: int, expected: list[list[float]]
) -> None:
    frame = ActuarialFrame(_points(periods, rows=rows))
    frame.alpha_eop = _machine(frame, periods).expr_for("alpha")
    values = frame.collect()
    assert values.schema["alpha_eop"] == pl.List(pl.Float64)
    assert values["alpha_eop"].to_list() == expected


def test_executable_record_closes_exact_operations_and_schedule() -> None:
    frame = ActuarialFrame(_points(3))
    frame.alpha_eop = _machine(frame, 3).expr_for("alpha")
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    assert validate_artifact(artifact, deep=True).ok
    node = next(item for item in artifact["nodes"] if item["kind"] == "rollforward")
    body = artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"][
        node["expr"]["attrs"]["fingerprint"]
    ]
    assert body["points"] == ["bop", "eop"]
    assert [item["operation"] for item in body["increments"]] == [
        "Add",
        "Subtract",
        "Charge",
        "Add",
        "Subtract",
        "Add",
        "Charge",
    ]
    assert body["increments"][2]["settings"] == {"round_charge": None}
    assert body["increments"][2]["operands"][1] == {"op": "state", "name": "alpha@eop"}
    schedule = next(
        item
        for item in artifact["assumptions"]
        if item["kind"] == "schedule" and item["fingerprint"] == body["schedule"]
    )
    assert schedule["payload"] == {
        "kind": "from_calendar_grid",
        "n_periods": 3,
        "frequency": "1M",
        "calendar": "NullCalendar",
        "convention": "Unadjusted",
        "day_count": "OneTwelfth",
        "anchor": "month_end",
        "start_date": "2025-01-31",
    }


def _structural_machine(frame: ActuarialFrame) -> CompiledRollforward:
    """Grow a balance, floor it, and ratchet a second one to it when told."""
    builder = RollforwardBuilder(
        states={"alpha": frame.alpha_init, "beta": frame.beta_init},
        schedule=_schedule(3),
    )
    builder["alpha"].grow(frame.rate, label="alpha_grow")
    builder["alpha"].floor(value=20.0)
    builder["beta"].ratchet(
        to=pl.col("alpha@eop"), when=frame.mask, label="beta_ratchet"
    )
    return compile_rollforward(builder)


def _structural_points() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "alpha_init": [100.0],
            "beta_init": [105.0],
            "rate": [[0.1, -0.9, 0.5]],
            "mask": [[True, False, True]],
        },
        schema={
            "alpha_init": pl.Float64,
            "beta_init": pl.Float64,
            "rate": pl.List(pl.Float64),
            "mask": pl.List(pl.Boolean),
        },
    )


def test_grow_floor_and_ratchet_move_the_balances_the_subsection_says() -> None:
    """The three operations section 16.1 admits, each observably doing its own thing.

    Read off the numbers rather than the record: ``alpha`` grows by a tenth,
    loses nine tenths, and is caught by its floor at 20 rather than 11 --
    which is the one period the floor bites in, and the one an auditor asks
    about. ``beta`` ratchets to ``alpha``'s within-period close where its
    gate is on and holds where the gate is off, including at the last
    period, where the gate is on and the value it would lift to is lower.
    """
    frame = ActuarialFrame(_structural_points())
    compiled = _structural_machine(frame)
    frame.alpha_eop = compiled.expr_for("alpha")
    frame.beta_eop = compiled.expr_for("beta")

    values = frame.collect()
    assert values["alpha_eop"].to_list()[0] == pytest.approx([110.0, 20.0, 30.0])
    assert values["beta_eop"].to_list()[0] == pytest.approx([110.0, 110.0, 110.0])


def test_executable_record_writes_the_three_structural_shapes() -> None:
    """The operand and setting shapes section 16.1 states, as the producer writes them.

    A second implementation reads those shapes off this record and off no
    other source, so a producer free to move them without a test here would
    take the published vectors with it and leave the subsection alone in
    claiming the old one.
    """
    frame = ActuarialFrame(_structural_points())
    frame.alpha_eop = _structural_machine(frame).expr_for("alpha")
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    assert validate_artifact(artifact, deep=True).ok
    node = next(item for item in artifact["nodes"] if item["kind"] == "rollforward")
    body = artifact["facets"]["gaspatchio_rollforward_ir"]["compilations"][
        node["expr"]["attrs"]["fingerprint"]
    ]
    grow, floor, ratchet = body["increments"]
    assert [item["operation"] for item in body["increments"]] == [
        "Grow",
        "Floor",
        "Ratchet",
    ]
    assert grow["settings"] == {"round_charge": None}
    assert grow["operands"] == [
        {"op": "col", "name": "rate"},
        {"op": "state", "name": "alpha@eop"},
    ]
    assert floor["label"] is None
    assert floor["settings"] == {"value": 20.0}
    assert floor["operands"] == [{"op": "state", "name": "alpha@eop"}]
    assert ratchet["settings"] == {}
    assert ratchet["operands"] == [
        {"op": "state", "name": "alpha@eop"},
        {"op": "col", "name": "mask"},
        {"op": "state", "name": "beta@eop"},
    ]
