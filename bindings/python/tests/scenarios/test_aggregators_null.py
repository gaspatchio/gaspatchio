# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One rule for a null: it is a missing value, skipped, and never becomes a number.

An IRR that does not exist (Excel's ``#NUM!``) is null on the model frame. A
profit-testing model folded that column through ``ScenarioRun`` and every
aggregator answered as though a value were there: ``Sum``, ``Mean``, ``Min`` and
``Max`` reported ``0.0`` -- a finite, plausible rate -- and ``Count`` reported
one scenario contributing. The within-scenario ``sum`` turned the lone null into
``0.0`` (Polars' sum of nothing) before any aggregator saw it.

The rule each aggregator now follows: a null is skipped where the values are
read, and an aggregator that saw nothing but nulls answers null. ``Count``
counts the values it saw, so it answers ``0``.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import when
from gaspatchio.assumptions import Table
from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import (
    CTE,
    ArgMax,
    ArgMin,
    Count,
    Max,
    Mean,
    Median,
    Min,
    Quantile,
    QuantileRank,
    ScenarioRun,
    Std,
    Sum,
    Variance,
)
from gaspatchio.scenarios.shocks import MultiplicativeShock

_SCALAR_KINDS = (Sum, Mean, Min, Max, Variance, Std, Median, CTE, QuantileRank)


def _mortality() -> Table:
    """Two-row mortality table: age 30 gives an IRR, age 31 has none."""
    return Table(
        name="mortality",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )


@pytest.fixture
def mortality_table() -> Table:
    """The table the model reads, as the plan states it."""
    return _mortality()


def _model_fn(af):  # noqa: ANN202
    """IRR is null wherever the mortality rate is above 0.0011 (no IRR exists)."""
    af.rate = _mortality().lookup(age=af.age)
    af.irr = when(af.rate > 0.0011).then(None).otherwise(0.1)
    return af


def _run(mortality_table: Table, af: ActuarialFrame) -> dict:
    plan = ScenarioRun(
        shocks={
            # BASE: policy 1 has an IRR (0.1), policy 2 has none.
            "BASE": [],
            # UP: both rates exceed the threshold, so no policy has an IRR.
            "UP": [MultiplicativeShock(factor=2.0, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("irr").alias("sum").over("scenario_id"),
            Mean("irr").alias("mean").over("scenario_id"),
            Min("irr").alias("min").over("scenario_id"),
            Max("irr").alias("max").over("scenario_id"),
            Count("irr").alias("count").over("scenario_id"),
        ),
    )
    result = plan.run(af, _model_fn, batch_size=2)
    return {
        alias: dict(frame.select("scenario_id", alias).iter_rows())
        for alias, frame in result.aggregations.items()
    }


@pytest.mark.parametrize("policies", [[30], [30, 31]])
def test_a_scenario_with_no_value_folds_to_null_not_zero(
    mortality_table: Table, policies: list[int]
) -> None:
    """The profit-testing-r3 repro: a scenario whose IRR is null reports null."""
    af = ActuarialFrame({"policy_id": list(range(len(policies))), "age": policies})
    out = _run(mortality_table, af)
    for alias in ("sum", "mean", "min", "max"):
        assert out[alias]["UP"] is None, (alias, out[alias])
        # A null beside a value is skipped, as Polars skips it.
        assert out[alias]["BASE"] == pytest.approx(0.1), (alias, out[alias])
    assert out["count"] == {"BASE": 1, "UP": 0}


@pytest.mark.parametrize("kind", _SCALAR_KINDS)
def test_only_nulls_answers_null(kind: type) -> None:
    """Every scalar aggregator answers null when it saw nothing but nulls."""
    agg = kind("v")
    state = agg.add_input(agg.create_accumulator(), None)
    assert agg.extract_output(state) is None
    batched = agg.add_batch(
        agg.create_accumulator(), pl.Series([None], dtype=pl.Float64)
    )
    assert agg.extract_output(batched) is None


@pytest.mark.parametrize("kind", _SCALAR_KINDS)
def test_a_null_beside_values_is_skipped(kind: type) -> None:
    """A null among values leaves the answer the values alone would give."""
    agg = kind("v")
    with_null = agg.create_accumulator()
    without = agg.create_accumulator()
    for v in (1.0, None, 3.0, 2.0):
        with_null = agg.add_input(with_null, v)
        if v is not None:
            without = agg.add_input(without, v)
    assert agg.extract_output(with_null) == pytest.approx(agg.extract_output(without))


def test_quantile_of_only_nulls_is_null_at_every_level() -> None:
    """Quantile answers null at each level when it saw nothing but nulls."""
    agg = Quantile("v", levels=(0.5, 0.995))
    state = agg.add_input(agg.create_accumulator(), None)
    assert agg.extract_output(state) == {0.5: None, 0.995: None}


def test_count_counts_values_not_nulls() -> None:
    """Count is the number of values seen; a null is not one."""
    agg = Count("v")
    state = agg.create_accumulator()
    for v in (None, 1.0, None):
        state = agg.add_input(state, v)
    assert agg.extract_output(state) == 1


@pytest.mark.parametrize("kind", [ArgMax, ArgMin])
def test_arg_extremes_skip_a_null_scenario(kind: type) -> None:
    """ArgMax/ArgMin never name a scenario whose value is null."""
    agg = kind("v")
    state = agg.create_accumulator()
    for sid, v in (("A", 1.0), ("B", None), ("C", 2.0)):
        state = agg.add_input(state, (sid, v))
    assert agg.extract_output(state) == ("C" if kind is ArgMax else "A")
    only_null = agg.add_input(agg.create_accumulator(), ("B", None))
    assert agg.extract_output(only_null) is None


def test_policy_axis_sum_of_only_nulls_is_null() -> None:
    """run_aggregated's Sum over an all-null column answers null, not 0.0."""
    agg = Sum("v")
    state = agg.add_batch(
        agg.create_accumulator(), pl.Series([None, None], dtype=pl.Float64)
    )
    assert agg.extract_output(state) is None
