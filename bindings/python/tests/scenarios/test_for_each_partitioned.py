# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for .over(by) partitioning semantics on v0.2 aggregators.
# ABOUTME: Covers tuple normalisation, multi-key partitions, batch-equivalence, errors.
# ruff: noqa: PD901, ERA001
"""Partitioned-aggregator semantics for for_each_scenario."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario


@pytest.fixture
def af() -> ActuarialFrame:
    """Six-policy frame with cycling partition keys for deterministic test math."""
    return ActuarialFrame({
        "policy_id": [1, 2, 3, 4, 5, 6],
        "premium": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
    })


def _lob_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a deterministic ``lob`` column and a ``loss`` column.

    Derives LOB from ``policy_id`` so the mapping is stable across
    batch sizes regardless of the interleaved row order produced by
    ``with_scenarios``.
    """
    # policy_id is 1-based; odd→motor, even→home.
    return af.with_columns(
        pl.when(pl.col("policy_id") % 2 == 1)
        .then(pl.lit("motor"))
        .otherwise(pl.lit("home"))
        .alias("lob"),
        pl.col("premium").alias("loss"),
    )


def _region_peril_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add deterministic ``region`` and ``peril`` columns plus a ``loss`` column.

    Derives keys from ``(policy_id - 1) % 4`` so the mapping is stable
    across batch sizes and produces all four (region, peril) combinations:
    - bucket 0 (p1,p5) → (uk, fire)
    - bucket 1 (p2,p6) → (uk, flood)
    - bucket 2 (p3)    → (eu, fire)
    - bucket 3 (p4)    → (eu, flood)
    Unique (region, peril) tuples: (uk,fire), (uk,flood), (eu,fire), (eu,flood).
    """
    bucket = (pl.col("policy_id") - 1) % 4
    return af.with_columns(
        pl.when(bucket < 2).then(pl.lit("uk")).otherwise(pl.lit("eu")).alias("region"),
        pl.when(bucket % 2 == 0)
        .then(pl.lit("fire"))
        .otherwise(pl.lit("flood"))
        .alias("peril"),
        pl.col("premium").alias("loss"),
    )


def test_over_string_equals_over_tuple(af: ActuarialFrame) -> None:
    """`.over("lob")` and `.over(("lob",))` produce identical results."""
    bare = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=_lob_model,
        aggregations=(Sum("loss").alias("by_lob").over("lob"),),
        batch_size=1,
    )
    tup = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=_lob_model,
        aggregations=(Sum("loss").alias("by_lob").over(("lob",)),),
        batch_size=1,
    )
    df_bare = bare.aggregations["by_lob"].sort("lob")
    df_tup = tup.aggregations["by_lob"].sort("lob")
    assert df_bare.equals(df_tup)


def test_multi_key_partition_yields_dataframe(af: ActuarialFrame) -> None:
    """`.over(("region", "peril"))` keys output by both columns."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=_region_peril_model,
        aggregations=(Sum("loss").alias("by_region_peril").over(("region", "peril")),),
        batch_size=1,
    )
    df = result.aggregations["by_region_peril"]
    assert isinstance(df, pl.DataFrame)
    assert set(df.columns) == {"region", "peril", "by_region_peril"}
    # 6 policies, partition keys cycle to 4 unique (region, peril) tuples:
    # (uk, fire), (uk, flood), (eu, fire), (eu, flood)
    assert df.height == 4
    # Across 2 scenarios, total loss = 2 * (100+200+300+400+500+600) = 4200
    assert df["by_region_peril"].sum() == pytest.approx(4200.0)


def test_batch_equivalence_partitioned(af: ActuarialFrame) -> None:
    """Partitioned aggregator output is bit-equivalent across batch sizes."""
    plan = (Sum("loss").alias("by_lob").over("lob"),)
    one = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_lob_model,
        aggregations=plan,
        batch_size=1,
    )
    two = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_lob_model,
        aggregations=plan,
        batch_size=2,
    )
    three = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_lob_model,
        aggregations=plan,
        batch_size=3,
    )
    df1 = one.aggregations["by_lob"].sort("lob")
    df2 = two.aggregations["by_lob"].sort("lob")
    df3 = three.aggregations["by_lob"].sort("lob")
    assert df1.equals(df2)
    assert df1.equals(df3)


def test_over_without_alias_raises() -> None:
    """`.over(...)` before `.alias(...)` is a usage error."""
    with pytest.raises(ValueError, match="alias"):
        Sum("loss").over("lob")


def test_partition_with_int_keys_sorts_numerically(af: ActuarialFrame) -> None:
    """.over() with int keys must sort 1, 2, ..., 10, 11, NOT '1', '10', '11', '2'."""

    def model_with_int_band(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        # Spread 6 policies across age bands 9..14 to force lex-vs-numeric distinction.
        return af.with_columns(
            ((pl.col("policy_id") - 1) % 6 + 9).alias("age_band"),
            pl.col("premium").alias("loss"),
        )

    result = for_each_scenario(
        af,
        scenarios=["A", "B"],
        model_fn=model_with_int_band,
        aggregations=(Sum("loss").alias("by_band").over("age_band"),),
        batch_size=1,
    )
    bands = result.aggregations["by_band"]["age_band"].to_list()
    assert bands == sorted(bands), (
        f"Partition row order is not numeric: got {bands}; "
        f"expected sorted numerically."
    )
    # Specifically, 9 must come BEFORE 10 (lex order would put '10' before '9').
    assert bands.index(9) < bands.index(10)
