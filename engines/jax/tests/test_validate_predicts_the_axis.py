# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``validate --engine jax`` names the axis refusals ``run-artifact`` meets.

A projection axis whose length the record does not fix (11.1.1) -- every
``projection.set(schedule=...)`` model -- and a calendar grid anchored on a
month end, whose boundary dates this engine does not lay (11.1.37), are
refused by the run before it computes anything. The inspection lowered both,
so the level-2 and level-3 tutorials validated with "0 refused" and then
failed to run. The inspection now runs each axis-laying call's sizing from
the record, as the run sizes it: the same nodes, the same sentence, the same
clause.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.schedule import Schedule
from gaspatchio_jax.engine import JaxEngine

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"policy_id": [1, 2], "sa": [1000.0, 2000.0], "term": [12, 6]})
_START = datetime.date(2025, 1, 1)


def _period_dates(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=_START, until="term_months", until_value=12, frequency="monthly"
    )
    af.pdate = af.projection.period_dates()
    af.cf = af.sa * 0.01 + af.month * 0.0
    return af


def _a_schedule(af: ActuarialFrame) -> ActuarialFrame:
    grid = Schedule.from_calendar_grid(start_date=_START, n_periods=12, frequency="1M")
    af = af.projection.set(schedule=grid)
    af.cf = af.sa * 0.01 + af.month * 1.0
    return af


def _a_column_horizon(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=_START,
        until="term_months",
        until_value="term",
        frequency="monthly",
    )
    af.cf = af.sa * 0.01 + af.month * 0.0
    return af


_MODELS: dict[str, tuple[Callable[[ActuarialFrame], ActuarialFrame], set[str]]] = {
    "period dates on a month-end grid": (_period_dates, {"pdate@1"}),
    "a schedule object": (
        _a_schedule,
        {
            "projection_start_date@1",
            "projection_end_date@1",
            "num_proj_months@1",
            "month@1",
        },
    ),
    "a column horizon": (_a_column_horizon, set()),
}


def _document(model: Callable[[ActuarialFrame], ActuarialFrame]) -> dict[str, Any]:
    exported = GraphExporter(model(ActuarialFrame(_BOOK))).export(profile="executable")
    document: dict[str, Any] = json.loads(exported)
    return document


@pytest.mark.parametrize("name", sorted(_MODELS))
def test_validate_refuses_the_axis_the_run_refuses(name: str) -> None:
    model, expected = _MODELS[name]
    document = _document(model)

    inspected = {
        one.node_id: (one.condition, one.clause)
        for one in JaxEngine().validate_tree(document)
        if one.status == "refused"
    }
    try:
        JaxEngine().run(document, _BOOK, FrameSink())
    except EngineRefusal as refused:
        run = {one.where: (one.what, one.clause) for one in refused.report.refusals}
    else:
        run = {}

    assert set(run) == expected
    assert inspected == run
