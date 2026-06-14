# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the new for_each_scenario shape (per-aggregator within-reduction)."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import ArgMax, Mean, Sum
from gaspatchio_core.scenarios._for_each import for_each_scenario


def _identity_model(af, *, tables, drivers):  # noqa: ANN202, ARG001
    return af.with_columns(pl.col("premium").alias("value"))


def test_scalar_aggregators_new_shape() -> None:
    """Scalar aggregators fold per-scenario reductions into final scalars."""
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_identity_model,
        aggregations=(
            Sum(column="value").alias("total"),
            Mean(column="value").alias("avg"),
        ),
        batch_size=1,
    )
    assert result.aggregations["total"] == pytest.approx(900.0)
    assert result.aggregations["avg"] == pytest.approx(300.0)


def test_partitioned_aggregator_returns_dataframe() -> None:
    """A .over() aggregator yields a DataFrame keyed by the partition column."""
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "premium": [100.0, 200.0, 150.0, 250.0],
            "lob": ["term", "annuity", "term", "annuity"],
        },
    )
    result = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=lambda af, **kw: af.with_columns(  # noqa: ARG005
            pl.col("premium").alias("value"),
        ),
        aggregations=(Sum(column="value").alias("by_lob").over("lob"),),
        batch_size=1,
    )
    by_lob = result.aggregations["by_lob"]
    assert isinstance(by_lob, pl.DataFrame)
    assert set(by_lob.columns) == {"lob", "by_lob"}
    # term: 100+150 = 250 per scenario * 2 scenarios = 500
    # annuity: 200+250 = 450 per scenario * 2 scenarios = 900
    term_row = by_lob.filter(pl.col("lob") == "term").row(0, named=True)
    assert term_row["by_lob"] == pytest.approx(500.0)
    annuity_row = by_lob.filter(pl.col("lob") == "annuity").row(0, named=True)
    assert annuity_row["by_lob"] == pytest.approx(900.0)


def test_argmax_with_scenario_id_packing() -> None:
    """ArgMax sees (scenario_id, value) tuples and returns the winning sid."""
    af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=lambda af, **kw: af.with_columns(  # noqa: ARG005
            pl.col("premium").alias("value"),
        ),
        aggregations=(ArgMax(column="value").alias("worst"),),
        batch_size=1,
    )
    # All scenarios have value 100; lex tiebreak -> first wins -> "A"
    assert result.aggregations["worst"] == "A"


def test_batch_equivalence_scalar() -> None:
    """batch_size=1 and batch_size=4 give same result for scalar aggregator."""
    af = ActuarialFrame(
        {
            "policy_id": list(range(20)),
            "premium": [float(i + 1) for i in range(20)],
        },
    )
    scenarios = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    aggs = (Sum(column="value").alias("total"), Mean(column="value").alias("avg"))

    r1 = for_each_scenario(
        af,
        scenarios=scenarios,
        model_fn=_identity_model,
        aggregations=aggs,
        batch_size=1,
    )
    r4 = for_each_scenario(
        af,
        scenarios=scenarios,
        model_fn=_identity_model,
        aggregations=aggs,
        batch_size=4,
    )
    assert r1.aggregations["total"] == pytest.approx(r4.aggregations["total"])
    assert r1.aggregations["avg"] == pytest.approx(r4.aggregations["avg"])


def test_empty_aggregations_raises() -> None:
    """Empty aggregations tuple raises ValueError before any work."""
    af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})
    with pytest.raises(ValueError, match="aggregator"):
        for_each_scenario(
            af,
            scenarios=["A"],
            model_fn=_identity_model,
            aggregations=(),
            batch_size=1,
        )


def test_duplicate_aliases_raise() -> None:
    """Aliases must be unique across the aggregations tuple."""
    af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})
    with pytest.raises(ValueError, match="aliases"):
        for_each_scenario(
            af,
            scenarios=["A"],
            model_fn=_identity_model,
            aggregations=(
                Sum(column="value").alias("total"),
                Mean(column="value").alias("total"),
            ),
            batch_size=1,
        )


def test_aggregator_without_alias_raises() -> None:
    """Aggregators must carry an explicit .alias(...) - no implicit default."""
    af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})
    with pytest.raises(ValueError, match="alias"):
        for_each_scenario(
            af,
            scenarios=["A"],
            model_fn=_identity_model,
            aggregations=(Sum(column="value"),),
            batch_size=1,
        )


def test_mixed_scalar_and_partitioned() -> None:
    """A run with both scalar and partitioned aggregators produces both shapes."""
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3],
            "premium": [100.0, 200.0, 300.0],
            "lob": ["a", "b", "a"],
        },
    )
    result = for_each_scenario(
        af,
        scenarios=["S1", "S2"],
        model_fn=lambda af, **kw: af.with_columns(  # noqa: ARG005
            pl.col("premium").alias("value"),
        ),
        aggregations=(
            Sum(column="value").alias("total"),
            Sum(column="value").alias("by_lob").over("lob"),
        ),
        batch_size=1,
    )
    assert isinstance(result.aggregations["total"], float)
    assert isinstance(result.aggregations["by_lob"], pl.DataFrame)


def test_consolidated_group_by_for_scalar_aggregators() -> None:
    """8 scalar aggregators produce identical results under consolidated group_by."""
    af = ActuarialFrame(
        {
            "policy_id": list(range(10)),
            "premium": [float(i + 1) for i in range(10)],
        },
    )
    result = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=_identity_model,
        aggregations=(
            Sum(column="value").alias("a"),
            Sum(column="value").alias("b"),
            Sum(column="value").alias("c"),
            Mean(column="value").alias("d"),
            Mean(column="value").alias("e"),
            Mean(column="value").alias("f"),
            Sum(column="value").alias("g"),
            Mean(column="value").alias("h"),
        ),
        batch_size=1,
    )
    # All Sum aggregations equal; all Mean aggregations equal.
    sum_total = result.aggregations["a"]
    mean_total = result.aggregations["d"]
    for key in ("b", "c", "g"):
        assert result.aggregations[key] == pytest.approx(sum_total)
    for key in ("e", "f", "h"):
        assert result.aggregations[key] == pytest.approx(mean_total)
