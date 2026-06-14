# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test .alias() / .over() / .of() modifier behaviour."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import CTE, ArgMax, Mean, Sum
from gaspatchio_core.scenarios._metric import _Partitioned


def test_alias_returns_new_instance() -> None:
    """.alias() returns a new aggregator with alias_ set; original unchanged."""
    a = Sum("v")
    b = a.alias("total")
    assert a.alias_ is None
    assert b.alias_ == "total"


def test_alias_preserves_other_fields() -> None:
    """.alias() doesn't change column, within, or within_expr_override."""
    a = Sum("loss", within="mean")
    b = a.alias("y")
    assert b.column == "loss"
    assert b.within == "mean"


def test_over_returns_partitioned() -> None:
    """.over() wraps the aggregator in _Partitioned with normalised by tuple."""
    a = Sum("v").alias("by_lob")
    p = a.over("lob")
    assert isinstance(p, _Partitioned)
    assert p.by == ("lob",)
    assert p.alias == "by_lob"


def test_over_tuple_normalisation() -> None:
    """.over('lob') and .over(('lob',)) produce identical wrappers."""
    a = Sum("v").alias("by_lob")
    p1 = a.over("lob")
    p2 = a.over(("lob",))
    assert p1.by == p2.by == ("lob",)


def test_over_multi_key() -> None:
    """Multi-column partitioning via tuple."""
    a = Sum("v").alias("by_region_peril")
    p = a.over(("region", "peril"))
    assert p.by == ("region", "peril")


def test_over_without_alias_raises() -> None:
    """Calling .over() before .alias() raises ValueError."""
    a = Sum("v")
    with pytest.raises(ValueError, match="alias"):
        a.over("lob")


def test_of_polars_escape() -> None:
    """Sum.of(pl_expr) builds an aggregator with within_expr_override set."""
    a = Sum.of(pl.col("a") + pl.col("b"))
    assert a.within_expr_override is not None
    expr = a.within_expr()
    assert isinstance(expr, pl.Expr)


def test_of_classmethod_works_per_aggregator() -> None:
    """Each concrete aggregator's .of() returns the right class."""
    sum_agg = Sum.of(pl.col("x").mean())
    mean_agg = Mean.of(pl.col("x").max())
    assert isinstance(sum_agg, Sum)
    assert isinstance(mean_agg, Mean)


def test_chain_alias_then_over_then_of() -> None:
    """Modifier chaining: alias + over composes; of is a constructor alternative."""
    a = Sum("v").alias("total").over("lob")
    assert isinstance(a, _Partitioned)
    assert a.alias == "total"
    assert a.by == ("lob",)


def test_argmax_with_over() -> None:
    """ArgMax (tuple-input aggregator) also supports .over()."""
    a = ArgMax("loss").alias("worst").over("lob")
    assert isinstance(a, _Partitioned)


def test_cte_carries_level_and_direction_through_alias() -> None:
    """CTE level/direction are preserved across .alias()."""
    a = CTE("v", level=0.005, direction="lower").alias("scr_lower")
    assert a.level == 0.005
    assert a.direction == "lower"
    assert a.alias_ == "scr_lower"
