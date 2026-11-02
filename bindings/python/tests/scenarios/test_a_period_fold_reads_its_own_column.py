# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period aggregator folds its own column, whatever the model's other columns are.

``run_aggregated`` refused ``PeriodSum("claims_count")`` over a per-period
whole-number column -- "the model produced no List(Float64) column to reduce
over" -- unless some unrelated column of the model held decimals per period;
with one beside it the same fold answered, and the JAX engine answered either
way (audit S1c-F2). The test was of the whole output schema rather than of the
column folded. What it should refuse, a per-period aggregator named on a
column of one value per policy, is now refused by name on both doors, as the
JAX engine refuses it, rather than inside Polars' ``list.len``.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated, when
from gaspatchio.scenarios import PeriodMax, PeriodMean, PeriodSum, ScenarioRun

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"pid": [1, 2], "n_pols": [100, 40], "term_years": [3, 3]})

# Periods at months 0, 12, 24, 36; a count of n // 10 at month 12 only.
_HAND = {
    "PeriodSum": [0.0, 14.0, 0.0, 0.0],
    "PeriodMean": [0.0, 7.0, 0.0, 0.0],
    "PeriodMax": [0.0, 10.0, 0.0, 0.0],
}


def _model(*, with_decimals: bool) -> Callable[[ActuarialFrame], ActuarialFrame]:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            valuation_date=dt.date(2025, 1, 1),
            until="term_years",
            until_value=3,
            frequency="annual",
        )
        af.claims_count = when(af.month == 12).then(af.n_pols // 10).otherwise(0)
        if with_decimals:
            af.prem = af.n_pols * 1.5 + af.month * 0.0
        return af

    return model


@pytest.mark.parametrize("kind", [PeriodSum, PeriodMean, PeriodMax])
@pytest.mark.parametrize("with_decimals", [False, True], ids=["alone", "beside"])
@pytest.mark.parametrize("batch_size", [1, 2])
def test_a_whole_number_column_is_folded_with_or_without_a_decimal_beside_it(
    kind: type, *, with_decimals: bool, batch_size: int
) -> None:
    result = run_aggregated(
        _model(with_decimals=with_decimals),
        _BOOK,
        [kind("claims_count").alias("x")],
        batch_size=batch_size,
    )
    assert [float(v) for v in result.x.tolist()] == _HAND[kind.__name__]


def test_a_scenario_plan_folds_it_too() -> None:
    plan = ScenarioRun(
        shocks={"BASE": []}, aggregations=[PeriodSum("claims_count").alias("x")]
    )
    result = plan.run(ActuarialFrame(_BOOK), _model(with_decimals=False), batch_size=1)
    assert [float(v) for v in result.aggregations["x"].tolist()] == _HAND["PeriodSum"]


def test_a_period_fold_of_a_per_policy_column_is_refused_by_name() -> None:
    with pytest.raises(
        ValueError, match=r"^PeriodSum\('n_pols'\) folds one value per period"
    ) as refused:
        run_aggregated(
            _model(with_decimals=True), _BOOK, [PeriodSum("n_pols").alias("x")]
        )
    assert "Sum('n_pols')" in str(refused.value)


def test_a_scenario_plan_refuses_it_by_name_too() -> None:
    plan = ScenarioRun(
        shocks={"BASE": []}, aggregations=[PeriodSum("n_pols").alias("x")]
    )
    with pytest.raises(
        ValueError, match=r"PeriodSum\('n_pols'\) folds one value per period"
    ):
        plan.run(ActuarialFrame(_BOOK), _model(with_decimals=True), batch_size=1)
