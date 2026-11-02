# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every statistic of whole numbers is read from exact totals, at every batch size.

``PeriodMean`` totalled each batch's periods of a ``list[i64]`` column in
``Int64``, so 2**62 and 2**62 averaged 4.6e18 one policy a batch and -4.6e18
two a batch. ``Mean``, ``Variance`` and ``Std`` -- and ``PeriodVariance`` and
``PeriodStd`` -- folded whole numbers as doubles, so 2**63 - 1, -2**63 and 5
averaged 1.67 at most batch sizes and 0.0 under ``"auto"`` where the mean is
4/3, and 2**53 + 1, + 2, + 3 and + 5, whose variance is 35/12, answered 5.22,
6.67 or 3.67 by batch. The per-period quantile kinds binned the least ``i64``
in its own width, whose absolute value wrapped, and answered its median as
+9.2e18. Each now answers the double nearest its exact value, the same at
every batch size and on both axes.
"""

from __future__ import annotations

import datetime
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.scenarios import (
    Mean,
    PeriodCTE,
    PeriodMean,
    PeriodMedian,
    PeriodQuantile,
    PeriodStd,
    PeriodVariance,
    Std,
    Variance,
    for_each_scenario,
    run_aggregated,
)

_H = 2**62
_P = 2**53
_MAX = 2**63 - 1
_MIN = -(2**63)

# Hand values.
# [2**62, 2**62]: mean 2**62.
_PAIR_MEAN = 4.611686018427388e18
# [2**63 - 1, -2**63, 5]: total 4, mean 4/3.
_MIXED_MEAN = 1.3333333333333333
# [2**63 - 1, 2**63 - 2, 2**63 - 3]: mean 2**63 - 2, whose nearest double is
# 2**63; deviations 1, 0, -1, so the sample variance is 2 / 2 = 1.
_NEAR_MEAN = 9.223372036854776e18
# [2**53 + 1, + 2, + 3, + 5]: deviations from the mean 2**53 + 11/4 are
# -7/4, -3/4, 1/4 and 9/4, whose squares total 140/16 = 35/4; over n - 1 = 3
# the variance is 35/12, and its root 1.70782512765993...
_FINE_MEAN = 9007199254740994.0
_FINE_VARIANCE = 35 / 12
_FINE_STD = 1.707825127659933

_DATA = {
    "pair": [_H, _H],
    "mixed": [_MAX, _MIN, 5],
    "near": [_MAX, _MAX - 1, _MAX - 2],
    "fine": [_P + 1, _P + 2, _P + 3, _P + 5],
}


def _book(values: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": list(range(len(values))),
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


def _run(data: str, aggregation: object, batch_size: int | str) -> object:
    return run_aggregated(
        _model,
        _book(_DATA[data]),
        aggregations=[aggregation],
        batch_size=batch_size,  # type: ignore[arg-type]
    ).aggregations["t"]


_SIZES = [1, 2, 3, "auto"]


@pytest.mark.parametrize("batch_size", _SIZES)
@pytest.mark.parametrize(
    ("data", "mean"),
    [("pair", _PAIR_MEAN), ("mixed", _MIXED_MEAN), ("near", _NEAR_MEAN)],
    ids=["2**62 twice", "both ends and 5", "the top three"],
)
def test_a_period_mean_of_whole_numbers_is_exact_at_every_batch_size(
    data: str, mean: float, batch_size: int | str
) -> None:
    """Was -4.6e18, 1.67 / 0.0 and 3.07e18 at some batch sizes."""
    answer = _run(data, PeriodMean("vv").alias("t"), batch_size)

    assert answer.tolist() == [mean, mean]  # type: ignore[attr-defined]


@pytest.mark.parametrize("batch_size", _SIZES)
def test_a_mean_of_whole_numbers_is_exact_at_every_batch_size(
    batch_size: int | str,
) -> None:
    """Hand value 4/3 (was 1.6666666666666667, and 0.0 under "auto")."""
    assert _run("mixed", Mean("v").alias("t"), batch_size) == _MIXED_MEAN


@pytest.mark.parametrize("batch_size", _SIZES)
def test_a_variance_and_its_root_of_whole_numbers_are_exact_at_every_batch_size(
    batch_size: int | str,
) -> None:
    """Hand values 35/12 and its root (was 5.22, 6.67, 3.67 and 5.33 by batch)."""
    assert _run("fine", Variance("v").alias("t"), batch_size) == _FINE_VARIANCE
    assert _run("fine", Std("v").alias("t"), batch_size) == _FINE_STD
    assert _run("fine", Mean("v").alias("t"), batch_size) == _FINE_MEAN


@pytest.mark.parametrize("batch_size", _SIZES)
def test_a_period_variance_of_whole_numbers_is_exact_at_every_batch_size(
    batch_size: int | str,
) -> None:
    """Hand values 35/12 and its root (was 5.22, 6.67, 5.0 and 1.0 by batch)."""
    variance = _run("fine", PeriodVariance("vv").alias("t"), batch_size)
    std = _run("fine", PeriodStd("vv").alias("t"), batch_size)

    assert variance.tolist() == [_FINE_VARIANCE] * 2  # type: ignore[attr-defined]
    assert std.tolist() == [_FINE_STD] * 2  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "aggregation",
    [Variance("v").alias("t"), PeriodVariance("vv").alias("t")],
    ids=["Variance", "PeriodVariance"],
)
def test_a_variance_at_the_top_of_the_range_is_one(aggregation: object) -> None:
    """Hand value 1 for 2**63 - 1, - 2, - 3 (was 0.0: as doubles all are 2**63)."""
    answer = _run("near", aggregation, 1)

    assert (answer.tolist() if hasattr(answer, "tolist") else [answer])[0] == 1.0  # type: ignore[attr-defined]


def test_a_partitioned_period_mean_and_variance_are_exact() -> None:
    mean = _run("pair", PeriodMean("vv").alias("t").over("g"), 2)
    variance = _run("fine", PeriodVariance("vv").alias("t").over("g"), 2)

    assert mean["t"].to_list() == [_PAIR_MEAN] * 2  # type: ignore[index]
    assert variance["t"].to_list() == [_FINE_VARIANCE] * 2  # type: ignore[index]


def test_a_period_mean_of_whole_numbers_skips_a_null_period() -> None:
    """A period whose every value is null is still masked; the others are exact."""

    def nulls(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
        )
        # A typed null keeps the run list[i64], and so now does a bare None.
        no_value = pl.lit(None, dtype=pl.Int64)
        af.k = when(af.month == 1).then(no_value).otherwise(af.v + af.month * 0)
        af.ff = af.amt + af.month * 0.0
        return af

    for batch_size in (1, 2):
        result = run_aggregated(
            nulls,
            _book([_H, _H]),
            aggregations=[
                PeriodMean("k").alias("m"),
                PeriodVariance("k").alias("s"),
            ],
            batch_size=batch_size,
        )
        assert result.aggregations["m"].tolist() == [_PAIR_MEAN, None, _PAIR_MEAN]
        assert result.aggregations["s"].tolist() == [0.0, None, 0.0]


def test_decimal_statistics_are_unchanged() -> None:
    assert _run("pair", PeriodMean("ff").alias("t"), 1).tolist() == [1.5, 1.5]  # type: ignore[attr-defined]
    assert _run("fine", PeriodVariance("ff").alias("t"), 2).tolist() == [0.0, 0.0]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "aggregation",
    [
        PeriodMedian("vv").alias("t"),
        PeriodCTE("vv", level=0.5).alias("t"),
    ],
    ids=["PeriodMedian", "PeriodCTE"],
)
def test_a_period_sketch_reads_the_least_i64_as_itself(aggregation: object) -> None:
    """Three policies of -2**63: the answer is -9.22e18 within the sketch's 1e-4.

    Binned in Int64, the least i64's absolute value wrapped to itself, and
    the answer was +9.2236e18.
    """
    answer = run_aggregated(
        _model,
        _book([_MIN, _MIN, _MIN]),
        aggregations=[aggregation],
        batch_size=2,
    ).aggregations["t"]

    for value in answer.tolist():
        assert value < 0
        assert math.isclose(value, float(_MIN), rel_tol=1e-4)


def test_a_period_quantile_reads_the_least_i64_as_the_scalar_kinds_do() -> None:
    """The per-period sketch answers what the per-policy ``Median`` answers."""
    from gaspatchio.scenarios import Median

    book = _book([_MIN, _MIN, _MIN + 1])
    period = run_aggregated(
        _model, book, aggregations=[PeriodQuantile("vv").alias("t")], batch_size=1
    ).aggregations["t"]
    scalar = run_aggregated(
        _model, book, aggregations=[Median("v").alias("t")], batch_size=1
    ).aggregations["t"]

    assert period[0.5].tolist() == [scalar, scalar]


def _scenario_model_for(values: list[int]) -> object:
    names = [f"S{index}" for index in range(len(values))]

    def model(
        af: ActuarialFrame,
        *,
        tables: object,  # noqa: ARG001 -- the scenario runner's signature
        drivers: object,  # noqa: ARG001 -- as above
    ) -> ActuarialFrame:
        af = af.projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=1, frequency="monthly"
        )
        chosen = when(af.scenario_id == names[0]).then(values[0])
        for name, value in zip(names[1:], values[1:], strict=True):
            chosen = chosen.when(af.scenario_id == name).then(value)
        af.v = chosen.otherwise(0)
        af.vv = af.v + af.month * 0
        return af

    return names, model


def _across_scenarios(data: str, aggregation: object, batch_size: int) -> object:
    names, model = _scenario_model_for(_DATA[data])  # type: ignore[misc]
    return for_each_scenario(
        ActuarialFrame(pl.DataFrame({"pid": [1], "amt": [1.0]})),
        names,
        model,  # type: ignore[arg-type]
        aggregations=(aggregation,),  # type: ignore[arg-type]
        batch_size=batch_size,
    ).aggregations["t"]


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_statistics_across_scenarios_of_whole_numbers_are_exact(
    batch_size: int,
) -> None:
    """Was 1.6666666666666667 for the mean, and 0.0 for the top three's variance."""
    assert _across_scenarios("mixed", Mean("v").alias("t"), batch_size) == _MIXED_MEAN
    assert _across_scenarios("near", Variance("v").alias("t"), batch_size) == 1.0
    assert _across_scenarios("fine", Std("v").alias("t"), batch_size) == _FINE_STD
    period = _across_scenarios("mixed", PeriodMean("vv").alias("t"), batch_size)
    assert period.tolist() == [_MIXED_MEAN] * 2  # type: ignore[attr-defined]
    period = _across_scenarios("near", PeriodStd("vv").alias("t"), batch_size)
    assert period.tolist() == [1.0] * 2  # type: ignore[attr-defined]


def test_a_period_median_across_scenarios_reads_the_least_i64_as_itself() -> None:
    """Three scenarios of -2**63: the median is -9.22e18 (was +9.2236e18)."""
    names, model = _scenario_model_for([_MIN, _MIN, _MIN])  # type: ignore[misc]
    answer = for_each_scenario(
        ActuarialFrame(pl.DataFrame({"pid": [1], "amt": [1.0]})),
        names,
        model,  # type: ignore[arg-type]
        aggregations=(PeriodMedian("vv").alias("t"),),
        batch_size=2,
    ).aggregations["t"]

    for value in answer.tolist():
        assert value < 0
        assert math.isclose(value, float(_MIN), rel_tol=1e-4)


def test_a_period_mean_partitioned_by_scenario_is_each_scenarios_own() -> None:
    """Each scenario holds the book [2**62, 2**62]: each mean is 2**62."""

    def model(
        af: ActuarialFrame,
        *,
        tables: object,  # noqa: ARG001 -- the scenario runner's signature
        drivers: object,  # noqa: ARG001 -- as above
    ) -> ActuarialFrame:
        return _model(af)

    answer = for_each_scenario(
        ActuarialFrame(_book([_H, _H])),
        ["A", "B"],
        model,
        aggregations=(PeriodMean("vv").alias("t").over("scenario_id"),),
        batch_size=1,
    ).aggregations["t"]

    assert answer["t"].to_list() == [_PAIR_MEAN] * 4


def test_a_whole_number_state_meets_a_decimal_as_doubles() -> None:
    """A decimal anywhere in the fold reads the exact totals once, as doubles."""
    mean = Mean("v")
    state = mean.create_accumulator()
    for value in (1, 2, 3):
        state = mean.add_input(state, value)
    state = mean.add_input(state, 4.5)
    variance = Variance("v")
    merged = variance.merge_accumulators(
        variance.add_input(variance.create_accumulator(), 2),
        variance.add_input(variance.add_input(variance.create_accumulator(), 4.0), 6.0),
    )

    assert mean.extract_output(state) == 2.625
    assert variance.extract_output(merged) == 4.0


@pytest.mark.parametrize(
    ("numerator", "denominator", "root"),
    [
        (9, 1, 3.0),
        (2, 1, math.sqrt(2)),
        (35, 12, _FINE_STD),
        (0, 7, 0.0),
        # sqrt((2 * (2**52 + 1) + 1)**2 / 4) lies exactly halfway between
        # 2**52 + 1 and 2**52 + 2; the tie goes to the even one.
        ((2 * (2**52 + 1) + 1) ** 2, 4, float(2**52 + 2)),
    ],
    ids=["a square", "two", "35/12", "nought", "a tie"],
)
def test_a_root_is_rounded_once_from_the_exact_ratio(
    numerator: int, denominator: int, root: float
) -> None:
    from gaspatchio.scenarios._aggregators import nearest_root

    assert nearest_root(numerator, denominator) == root
