# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period mean or spread of whole numbers folded here is the producer's exact one.

This engine totalled a ``list[i64]`` column's periods for ``PeriodMean`` in one
``int64``, which wrapped: 2**62 and 2**62 averaged 4.6e18 one policy a batch
and -4.6e18 two a batch, here as on Polars. ``PeriodVariance`` and
``PeriodStd`` worked in doubles, so 2**53 + 1, + 2, + 3 and + 5, whose
variance is 35/12, answered 5.22, 6.67 or 3.67 by batch. The device now takes
a mean's total in halves, and a spread's count, total and total of squares as
exact integer sums, and the host joins them, so both engines answer the
double nearest each exact figure at every batch size.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import (
    Mean,
    PeriodMean,
    PeriodStd,
    PeriodVariance,
    Std,
    Variance,
    run_aggregated,
)

if TYPE_CHECKING:
    from gaspatchio import ActuarialFrame

_H = 2**62
_P = 2**53
_MAX = 2**63 - 1
_MIN = -(2**63)

# Hand values: [2**62, 2**62] averages 2**62; [2**63 - 1, -2**63, 5] totals 4
# and averages 4/3; [2**53 + 1, + 2, + 3, + 5] has deviations -7/4, -3/4, 1/4
# and 9/4 from its mean, whose squares total 35/4, so its sample variance is
# 35/12 and its root 1.70782512765993...; [2**63 - 1, - 2, - 3] has variance 1.
_DATA = {
    "pair": [_H, _H],
    "mixed": [_MAX, _MIN, 5],
    "fine": [_P + 1, _P + 2, _P + 3, _P + 5],
    "near": [_MAX, _MAX - 1, _MAX - 2],
}


def _book(values: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "amt": [1.5] * len(values),
            "v": pl.Series(values, dtype=pl.Int64),
            "g": ["a"] * len(values),
        }
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )
    af.vv = af.v + af.month * 0
    af.ff = af.amt + af.month * 0.0
    return af


def _answers(data: str, aggregation: object, batch_size: int) -> list[object]:
    answers: list[object] = []
    for engine in (None, "jax"):
        result = run_aggregated(
            _model,
            _book(_DATA[data]),
            aggregations=[aggregation],
            batch_size=batch_size,
            engine=engine,
        ).aggregations["t"]
        answers.append(result.tolist() if hasattr(result, "tolist") else result)
    return answers


@pytest.mark.parametrize("batch_size", [1, 2, 3])
@pytest.mark.parametrize(
    ("data", "mean"),
    [("pair", 4.611686018427388e18), ("mixed", 1.3333333333333333)],
    ids=["2**62 twice", "both ends and 5"],
)
def test_a_period_mean_of_whole_numbers_is_exact_on_both_engines(
    data: str, mean: float, batch_size: int
) -> None:
    """Was -4.6e18 two a batch, and 1.67 one a batch, on both engines."""
    assert _answers(data, PeriodMean("vv").alias("t"), batch_size) == [[mean] * 2] * 2


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_period_spread_of_whole_numbers_is_exact_on_both_engines(
    batch_size: int,
) -> None:
    """Was 5.22, 6.67 or 3.67 for the variance by batch, on both engines."""
    variance = _answers("fine", PeriodVariance("vv").alias("t"), batch_size)
    std = _answers("fine", PeriodStd("vv").alias("t"), batch_size)
    near = _answers("near", PeriodVariance("vv").alias("t"), batch_size)

    assert variance == [[35 / 12] * 2] * 2
    assert std == [[1.707825127659933] * 2] * 2
    assert near == [[1.0] * 2] * 2


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_per_policy_statistic_of_whole_numbers_is_exact_on_both_engines(
    batch_size: int,
) -> None:
    """The per-policy kinds fold through the core's own exact state here too."""
    assert (
        _answers("mixed", Mean("v").alias("t"), batch_size) == [1.3333333333333333] * 2
    )
    assert _answers("fine", Variance("v").alias("t"), batch_size) == [35 / 12] * 2
    assert _answers("fine", Std("v").alias("t"), batch_size) == [1.707825127659933] * 2


def test_a_partitioned_period_mean_and_spread_are_exact_on_both_engines() -> None:
    for aggregation, data, value in (
        (PeriodMean("vv").alias("t").over("g"), "pair", 4.611686018427388e18),
        (PeriodVariance("vv").alias("t").over("g"), "fine", 35 / 12),
    ):
        for engine in (None, "jax"):
            result = run_aggregated(
                _model,
                _book(_DATA[data]),
                aggregations=[aggregation],
                batch_size=2,
                engine=engine,
            ).aggregations["t"]
            assert result["t"].to_list() == [value] * 2


def test_a_decimal_period_mean_and_spread_are_unchanged() -> None:
    assert _answers("pair", PeriodMean("ff").alias("t"), 1) == [[1.5, 1.5]] * 2
    assert _answers("fine", PeriodStd("ff").alias("t"), 2) == [[0.0, 0.0]] * 2
