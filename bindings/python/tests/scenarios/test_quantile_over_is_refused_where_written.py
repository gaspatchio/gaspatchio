# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A multi-level quantile under ``.over()`` is refused where ``.over()`` is written.

``Quantile(...).over(...)`` and ``PeriodQuantile(...).over(...)`` were
accepted when written and refused only when a run reached its first fold --
after the plan was built, the book cross-joined and a batch projected. No
driver folds one partitioned, so the refusal now comes at the call, in the
words the run used.
"""

from __future__ import annotations

import pytest

from gaspatchio.scenarios import (
    CTE,
    Median,
    PeriodCTE,
    PeriodMedian,
    PeriodQuantile,
    Quantile,
    QuantileRank,
)


def test_quantile_over_is_refused_at_the_call_naming_kinds_that_run() -> None:
    with pytest.raises(NotImplementedError) as refused:
        Quantile("pv", levels=(0.5, 0.9)).alias("q50").over("scenario_id")

    assert str(refused.value) == (
        "Quantile.over() ('q50') is not yet supported; use Median, CTE or "
        "QuantileRank with .over(), or Quantile without .over()."
    )


def test_period_quantile_over_is_refused_at_the_call_naming_kinds_that_run() -> None:
    with pytest.raises(NotImplementedError) as refused:
        PeriodQuantile("cf").alias("q").over("scenario_id")

    assert str(refused.value) == (
        "PeriodQuantile.over() ('q') is not yet supported; use PeriodMedian or "
        "PeriodCTE with .over(), or PeriodQuantile without .over()."
    )


def test_every_kind_the_refusals_name_is_accepted_under_over() -> None:
    for partitioned in (
        Median("pv").alias("m").over("scenario_id"),
        CTE("pv", level=0.9).alias("c").over("scenario_id"),
        QuantileRank("pv", at=1.0).alias("r").over("scenario_id"),
        PeriodMedian("cf").alias("pm").over("scenario_id"),
        PeriodCTE("cf", level=0.9).alias("pc").over("scenario_id"),
        Quantile("pv", levels=(0.5,)).alias("q"),
        PeriodQuantile("cf").alias("pq"),
    ):
        assert partitioned is not None
