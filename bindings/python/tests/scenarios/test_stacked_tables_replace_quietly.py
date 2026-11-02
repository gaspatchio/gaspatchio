# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario run's own stacked tables replace themselves without a warning.

A shocked scenario run stacks each base table across one batch's scenarios,
under the base table's name with ``_stacked`` on the end, collects the batch,
and stacks the next batch under the same name. Each batch's table holds other
scenarios, so its data differs, and an assumption table re-registered with
different data warns -- rightly, for a user who may still hold a lookup built
against the old data. Here nothing outlives its batch, and a warning on every
batch of the documented scenario path tells the user they did something they
did not do. A user's own re-registration still warns, after a run as before.
"""

from __future__ import annotations

import warnings

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._warning import GaspatchioWarning
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum


def _mortality(name: str, scale: float = 1.0) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [40, 41, 42], "rate": [0.01 * scale, 0.02, 0.03]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _model_over(base_name: str):  # noqa: ANN202 -- a model function
    """Return the reconciled model reading its own mortality table."""

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.q = _mortality(base_name).lookup(age=af.age)
        af.claim = af.q * af.sum_assured
        return af

    return model


def _run(base_name: str) -> dict:
    run = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=1.5, table=base_name)],
            "DOWN": [MultiplicativeShock(factor=0.5, table=base_name)],
        },
        aggregations=(Sum("claim").alias("claim").over("scenario_id"),),
    )
    book = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "age": [40, 42], "sum_assured": [1e5, 2e5]})
    )
    # One scenario per batch: every batch after the first stacks the table again.
    result = run.run(book, _model_over(base_name), batch_size=1)
    totals = result.aggregations["claim"]
    return dict(zip(totals["scenario_id"], totals["claim"], strict=True))


def test_a_batched_shocked_run_raises_no_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", GaspatchioWarning)
        claims = _run("mortality_quiet_run")
    # Each batch's numbers are its own scenario's: the replaced table was in hand.
    assert claims["BASE"] == pytest.approx(0.01 * 1e5 + 0.03 * 2e5)
    assert claims["UP"] == pytest.approx(1.5 * claims["BASE"])
    assert claims["DOWN"] == pytest.approx(0.5 * claims["BASE"])


def test_a_users_own_re_registration_still_warns_after_a_run() -> None:
    _run("mortality_after_run")
    _mortality("users_own_table")
    with pytest.warns(GaspatchioWarning, match="re-registered with different data"):
        _mortality("users_own_table", scale=2.0)
