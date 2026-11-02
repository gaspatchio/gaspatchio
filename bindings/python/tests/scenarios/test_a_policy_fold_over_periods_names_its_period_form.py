# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An aggregator of one value per policy on a per-period column names its Period form.

``Sum("net_cf")`` over a column holding one value per period failed inside
Polars' grouped sum -- "`sum` operation not supported for dtype `list[f64]`"
-- with no sentence of gaspatchio's, on both axes; under ``within="max"`` it
answered null for every scenario without a word. The fold now refuses it
before anything is folded, naming ``PeriodSum``. ``within="count"`` counts
the policies, which a per-period column answers as well as any, and runs.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.scenarios import Max, Mean, PeriodSum, ScenarioRun, Sum


def _main(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=2, frequency="annual"
    )
    af.net_cf = af.premium + af.month * 0.0
    af.pv = af.premium * 2.0
    return af


def _book() -> pl.DataFrame:
    return pl.DataFrame({"policy_id": [1, 2], "premium": [10.0, 20.0]})


def _plan(*aggregations: object) -> ScenarioRun:
    return ScenarioRun(shocks={"BASE": [], "AGAIN": []}, aggregations=aggregations)


@pytest.mark.parametrize(
    ("aggregator", "kind"),
    [
        (Sum("net_cf").alias("a"), "Sum"),
        (Mean("net_cf").alias("a"), "Mean"),
        (Sum("net_cf").alias("a").over("scenario_id"), "Sum"),
        (Max("net_cf", within="max").alias("a"), "Max"),
    ],
    ids=["sum", "mean", "sum-over", "max-within-max"],
)
def test_a_scenario_plan_refuses_it_naming_the_period_form(
    aggregator: object, kind: str
) -> None:
    with pytest.raises(ValueError, match="holds one value per period") as refused:
        _plan(aggregator).run(ActuarialFrame(_book()), _main, batch_size=1)

    message = str(refused.value)
    assert message.startswith(
        f"{kind}('net_cf') folds one value per policy, and 'net_cf' holds one "
        "value per period"
    )
    assert f"Period{kind}('net_cf')" in message


def test_run_aggregated_refuses_it_naming_the_period_form() -> None:
    with pytest.raises(ValueError, match=r"PeriodSum\('net_cf'\)"):
        run_aggregated(_main, _book(), [Sum("net_cf").alias("a")])


def test_the_kinds_it_names_fold_the_same_columns() -> None:
    result = _plan(PeriodSum("net_cf").alias("p"), Sum("pv").alias("s")).run(
        ActuarialFrame(_book()), _main, batch_size=1
    )
    assert result.aggregations["p"].tolist() == [60.0, 60.0, 60.0]
    assert result.aggregations["s"] == 120.0


def test_a_count_of_the_policies_holding_a_per_period_column_runs() -> None:
    result = _plan(Sum("net_cf", within="count").alias("n")).run(
        ActuarialFrame(_book()), _main, batch_size=1
    )
    assert result.aggregations["n"] == 4.0
