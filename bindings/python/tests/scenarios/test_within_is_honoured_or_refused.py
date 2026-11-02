# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An aggregator's ``within=`` is honoured where it has a meaning, refused where not.

``within=`` reduces each scenario's policies before a statistic is taken
across scenarios. Every ``Period*`` kind accepted it and then summed the
policies anyway, so ``PeriodMax("claims", within="max")`` -- the largest
single policy per period -- answered the largest scenario *total*, and
``canonical_form()`` left ``within`` out, so the record could not say what was
asked. On the policy axis (``run_aggregated``) there are no scenarios to
reduce within, and a scalar ``Sum("pv", within="mean")`` answered the policy
total. Now a ``Period*`` kind on the scenario axis reduces each scenario's
policies by ``within`` first, the canonical form carries ``within`` where it
is not the default, and the policy axis refuses it by name.
"""

from __future__ import annotations

import datetime as dt
import statistics

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import (
    AdditiveShock,
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    ScenarioRun,
    Sum,
    run_aggregated,
)
from gaspatchio.scenarios._config import parse_aggregations

SA = [7.0, 2.0, 11.0, 4.0]


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=dt.date(2025, 12, 31),
        until="term_years",
        until_value=2,
        frequency="annual",
    )
    af.claims = af.sa * (af.month + 12) / 12.0  # policy i: sa_i * [1, 2, 3]
    af.pv = af.claims.list.sum()
    return af


BOOK = pl.DataFrame({"pid": [1, 2, 3, 4], "sa": SA})
SHOCKS = {
    "BASE": [],
    "UP": [AdditiveShock(1.0, column="sa")],
    "DOWN": [AdditiveShock(-1.0, column="sa")],
}

_WITHIN = {
    "sum": sum,
    "mean": statistics.fmean,
    "max": max,
    "min": min,
    "count": len,
}
_ACROSS = {
    PeriodSum: sum,
    PeriodMean: statistics.fmean,
    PeriodMax: max,
    PeriodMin: min,
    PeriodCount: len,
    PeriodVariance: statistics.variance,
    PeriodStd: statistics.stdev,
}


def _hand(kind: type, within: str) -> list[float]:
    """Reduce each scenario's policies by ``within``, then ``kind`` across them."""
    books = {"BASE": SA, "UP": [s + 1 for s in SA], "DOWN": [s - 1 for s in SA]}
    out = []
    for k in (1, 2, 3):
        per_scenario = [_WITHIN[within]([s * k for s in sa]) for sa in books.values()]
        out.append(float(_ACROSS[kind](per_scenario)))
    return out


@pytest.mark.parametrize("batch_size", [1, 2])
@pytest.mark.parametrize("within", ["mean", "max", "min", "count", "sum"])
@pytest.mark.parametrize("kind", list(_ACROSS))
def test_a_period_kind_reduces_each_scenario_by_within_first(
    kind: type, within: str, batch_size: int
) -> None:
    plan = ScenarioRun(
        shocks=SHOCKS, aggregations=(kind("claims", within=within).alias("a"),)
    )
    got = plan.run(ActuarialFrame(BOOK), _model, batch_size=batch_size)
    assert [float(v) for v in got.aggregations["a"]] == pytest.approx(
        _hand(kind, within), rel=1e-12
    )


def test_canonical_form_carries_within_only_where_it_is_not_the_default() -> None:
    assert PeriodMax("claims").canonical_form() == {
        "kind": "PeriodMax",
        "column": "claims",
    }
    assert PeriodMax("claims", within="max").canonical_form() == {
        "kind": "PeriodMax",
        "column": "claims",
        "within": "max",
    }
    entry = {**PeriodMax("claims", within="max").canonical_form(), "alias": "a"}
    (back,) = parse_aggregations([entry])
    assert back.within == "max"


@pytest.mark.parametrize(
    "agg",
    [
        Sum("pv", within="mean"),
        Sum("pv", within="max"),
        PeriodMax("claims", within="max"),
        PeriodSum("claims", within="mean"),
    ],
)
def test_the_policy_axis_refuses_within_by_name(agg: object) -> None:
    with pytest.raises(ValueError, match=r"is not supported on the policy axis"):
        run_aggregated(_model, BOOK, [agg.alias("a")], batch_size=2)  # type: ignore[attr-defined]


def test_the_policy_axis_default_still_answers_the_hand_value() -> None:
    got = run_aggregated(_model, BOOK, [Sum("pv").alias("a")], batch_size=2)
    assert got.aggregations["a"] == pytest.approx(6 * sum(SA))


def test_within_over_a_scenario_partition_is_refused() -> None:
    plan = ScenarioRun(
        shocks=SHOCKS,
        aggregations=(
            PeriodMax("claims", within="max").alias("a").over("scenario_id"),
        ),
    )
    with pytest.raises(ValueError, match=r"within= would be dropped"):
        plan.run(ActuarialFrame(BOOK), _model, batch_size=2)


@pytest.mark.parametrize("batch_size", [1, 2])
def test_a_sketch_kind_reduces_each_scenario_by_within_first(batch_size: int) -> None:
    from gaspatchio.scenarios import PeriodMedian

    plan = ScenarioRun(
        shocks=SHOCKS, aggregations=(PeriodMedian("claims", within="max").alias("a"),)
    )
    got = plan.run(ActuarialFrame(BOOK), _model, batch_size=batch_size)
    books = ([*SA], [s + 1 for s in SA], [s - 1 for s in SA])
    hand = [
        statistics.median(max(s * k for s in sa) for sa in books) for k in (1, 2, 3)
    ]
    assert [float(v) for v in got.aggregations["a"]] == pytest.approx(hand, rel=1e-3)
