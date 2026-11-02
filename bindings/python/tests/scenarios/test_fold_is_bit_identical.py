# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario fold answers the same bits on every run and at every batch size.

Two things moved the last bits of a statistic across scenarios. The fold took
a batch's scenarios in the order a ``group_by`` returned them, which Polars
does not fix, so a ``Mean`` across scenarios differed between two identical
runs at batch size 10. And each scenario's total over its policies was taken
on the whole batch frame, so the same scenario summed its policies to
different last bits at batch size 1 and 10 (a ``Min`` of those totals moved).
Now each scenario is reduced on its own rows and folded in the run's order.
"""

from __future__ import annotations

import datetime
import pickle

import numpy as np
import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import (
    CTE,
    Mean,
    Min,
    MultiplicativeShock,
    PeriodMean,
    PeriodSum,
    PeriodVariance,
    Quantile,
    ScenarioRun,
    Std,
    Sum,
    Variance,
)

N_POLICIES = 2000
SCENARIOS = [f"S{i:02d}" for i in range(12)]


def _book() -> ActuarialFrame:
    rng = np.random.default_rng(3)
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": list(range(N_POLICIES)),
                "age": rng.integers(30, 60, N_POLICIES).tolist(),
                "sa": (rng.random(N_POLICIES) * 1e5 + 1e3).tolist(),
                "band": [["A", "B", "C"][i % 3] for i in range(N_POLICIES)],
            }
        )
    )


def _main(af: ActuarialFrame) -> ActuarialFrame:
    mortality = Table(
        name="bit_identical_fold_mortality",
        source=pl.DataFrame(
            {"age": list(range(30, 80)), "q": [0.0007 * 1.0731**i for i in range(50)]}
        ),
        dimensions={"age": "age"},
        value="q",
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=24,
        frequency="monthly",
    )
    af.attained = af.age + af.month // 12
    af.q = mortality.lookup(age=af.attained)
    af.claim = af.sa * af.q / 12.0
    af.pv = af.claim.list.sum() * 1.000001
    return af


def _answers(batch_size: int | str) -> dict[str, bytes]:
    plan = ScenarioRun(
        shocks={
            sid: [
                MultiplicativeShock(
                    1.0 + 0.0137 * i, table="bit_identical_fold_mortality"
                )
            ]
            for i, sid in enumerate(SCENARIOS)
        },
        aggregations=(
            Sum("pv").alias("sum"),
            Mean("pv").alias("mean"),
            Variance("pv").alias("variance"),
            Std("pv").alias("std"),
            Min("pv").alias("min"),
            Quantile("pv", levels=(0.05, 0.5, 0.95)).alias("quantiles"),
            CTE("pv", level=0.1).alias("cte"),
            Mean("pv").alias("mean_by_band").over("band"),
            Sum("pv").alias("totals").over("scenario_id"),
            PeriodSum("claim").alias("period_sum"),
            PeriodMean("claim").alias("period_mean"),
            PeriodVariance("claim").alias("period_variance"),
        ),
    )
    result = plan.run(_book(), _main, batch_size=batch_size)  # type: ignore[arg-type]
    out = {}
    for alias, value in result.aggregations.items():
        if isinstance(value, pl.DataFrame):
            value = value.sort(value.columns[:-1]).to_dict(as_series=False)
        out[alias] = pickle.dumps(value)
    return out


def test_every_fold_is_the_same_bits_on_every_run_and_at_every_batch_size() -> None:
    runs = {f"{size}#{n}": _answers(size) for size in (1, 4, "auto") for n in range(2)}
    reference = runs["1#0"]
    moved = sorted(
        {
            f"{alias} (batch {name.split('#')[0]})"
            for name, answers in runs.items()
            for alias, blob in answers.items()
            if blob != reference[alias]
        }
    )
    assert moved == []
