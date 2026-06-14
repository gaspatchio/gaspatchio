# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the per-period (vector) aggregator family."""

from __future__ import annotations

import numpy as np
import polars as pl

from gaspatchio_core.scenarios._period_aggregators import (
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    VectorAggregator,
    _pad_add,
    _pad_combine,
    _reduce_by_period_over,
    _welford_merge_vec,
)


def _with_period(rows: list[list[float | None]]) -> pl.DataFrame:
    """Build a List(Float64) frame with the __period index _fold_batch would add."""
    return pl.DataFrame({"cf": rows}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period"),
    )


def test_period_sum_empty_list_no_phantom_period() -> None:
    """An empty [] projection must not insert a phantom leading period (#2)."""
    frame = _with_period([[], [10.0, 20.0]])
    vec = PeriodSum(column="cf").batch_reduce(frame, "__period")
    assert vec.tolist() == [10.0, 20.0]  # not [0.0, 10.0, 20.0]


def test_welford_merge_empty_period_no_nan_poison() -> None:
    """A period with zero samples in one operand must not NaN-poison the merge (#1)."""
    a = (np.array([2.0]), np.array([5.0]), np.array([2.0]))  # 2 samples, mean 5, m2 2
    b = (np.array([0.0]), np.array([np.nan]), np.array([0.0]))  # empty in this batch
    n, mean, m2 = _welford_merge_vec(a, b)
    assert n[0] == 2.0
    assert mean[0] == 5.0  # currently NaN
    assert m2[0] == 2.0  # currently NaN


def test_period_variance_period_null_in_one_batch() -> None:
    """PeriodVariance stays correct when a period is all-null in one batch (#1)."""
    agg = PeriodVariance(column="cf")
    b1 = _with_period([[1.0, None], [2.0, None], [3.0, None]])  # period 1 all-null
    b2 = _with_period([[None, 4.0], [None, 5.0], [None, 6.0]])  # period 0 all-null
    acc = agg.create_accumulator()
    acc = agg.add_input(acc, agg.batch_reduce(b1, "__period"))
    acc = agg.add_input(acc, agg.batch_reduce(b2, "__period"))
    out = agg.extract_output(acc)
    assert out[0] == 1.0  # var([1,2,3], ddof=1)
    assert out[1] == 1.0  # var([4,5,6]); was NaN (poisoned by b1's empty period 1)


def test_pad_add_unequal_lengths() -> None:
    """Shorter vector is zero-padded; tail of the longer vector survives unchanged."""
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([10.0, 20.0])
    out = _pad_add(a, b)
    assert out.tolist() == [11.0, 22.0, 3.0]  # tail of a survives


def test_pad_combine_min_keeps_single_batch_tail() -> None:
    """Periods in only one operand keep that operand's value (+inf identity pad)."""
    a = np.array([5.0, 5.0, 5.0])
    b = np.array([2.0, 9.0])
    out = _pad_combine(a, b, np.minimum, np.inf)
    assert out.tolist() == [2.0, 5.0, 5.0]  # period 2 only in a -> a's value


def _frame_with_lists(lists: list[list[float]]) -> pl.DataFrame:
    """Build a DataFrame with a single List[Float64] column named 'cf'."""
    return pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)})


def test_period_sum_equal_lengths() -> None:
    """batch_reduce sums each period index across equal-length policy vectors."""
    raw = _frame_with_lists([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]])
    agg = PeriodSum("cf")
    period = "__period"
    frame = raw.with_columns(pl.int_ranges(pl.col("cf").list.len()).alias(period))
    vec = agg.batch_reduce(frame, period)
    assert vec.tolist() == [11.0, 22.0, 33.0]


def test_period_sum_jagged_aligns_by_index() -> None:
    """batch_reduce aligns by list index; shorter-policy tail survives unmodified."""
    raw = _frame_with_lists([[1.0, 2.0, 3.0], [10.0, 20.0]])
    agg = PeriodSum("cf")
    frame = raw.with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    vec = agg.batch_reduce(frame, "__period")
    assert vec.tolist() == [11.0, 22.0, 3.0]


def test_period_sum_merge_is_pad_add() -> None:
    """merge_accumulators pad-and-adds two per-period vectors of different length."""
    agg = PeriodSum("cf")
    acc_a = agg.add_input(agg.create_accumulator(), np.array([1.0, 2.0, 3.0]))
    acc_b = agg.add_input(agg.create_accumulator(), np.array([10.0, 20.0]))
    merged = agg.merge_accumulators(acc_a, acc_b)
    assert agg.extract_output(merged).tolist() == [11.0, 22.0, 3.0]


def _reduced(
    agg: VectorAggregator,
    lists: list[list[float]],
) -> list[object]:
    """Build a frame, attach period ranges, call batch_reduce, and return as list."""
    from typing import cast

    frame = _frame_with_lists(lists).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    raw = agg.batch_reduce(frame, "__period")
    arr: np.ndarray[tuple[int], np.dtype[np.float64]] = np.asarray(
        raw, dtype=np.float64
    )
    return cast("list[object]", arr.tolist())


def test_period_count_counts_per_period() -> None:
    """PeriodCount counts non-null values per period index, handling jagged lists."""
    assert _reduced(PeriodCount("cf"), [[1.0, 2.0, 3.0], [10.0, 20.0]]) == [2, 2, 1]


def test_period_min_max() -> None:
    """PeriodMin/PeriodMax pick the element-wise minimum/maximum across policies."""
    assert _reduced(PeriodMin("cf"), [[1.0, 8.0], [5.0, 2.0]]) == [1.0, 2.0]
    assert _reduced(PeriodMax("cf"), [[1.0, 8.0], [5.0, 2.0]]) == [5.0, 8.0]


def test_period_min_merge_keeps_tail() -> None:
    """Merging a 3-period acc with a 2-period acc keeps period 2 from the longer one."""
    agg = PeriodMin("cf")
    acc_a = agg.add_input(agg.create_accumulator(), np.array([5.0, 5.0, 5.0]))
    acc_b = agg.add_input(agg.create_accumulator(), np.array([2.0, 9.0]))
    assert agg.extract_output(agg.merge_accumulators(acc_a, acc_b)).tolist() == [
        2.0,
        5.0,
        5.0,
    ]


def test_period_mean_equals_sum_over_count() -> None:
    """PeriodMean extracts sum/count giving the correct per-period mean."""
    frame = _frame_with_lists([[2.0, 4.0], [4.0, 8.0]]).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    agg = PeriodMean("cf")
    acc = agg.add_input(agg.create_accumulator(), agg.batch_reduce(frame, "__period"))
    assert agg.extract_output(acc).tolist() == [3.0, 6.0]


def test_period_mean_exact_across_batch_split() -> None:
    """Mean of all rows == mean computed by merging two row-batches (exactly)."""
    rows = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
    agg = PeriodMean("cf")

    def reduce(subset: list[list[float]]) -> object:
        frame = _frame_with_lists(subset).with_columns(
            pl.int_ranges(pl.col("cf").list.len()).alias("__period")
        )
        return agg.batch_reduce(frame, "__period")

    whole = agg.add_input(agg.create_accumulator(), reduce(rows))
    split = agg.merge_accumulators(
        agg.add_input(agg.create_accumulator(), reduce(rows[:1])),
        agg.add_input(agg.create_accumulator(), reduce(rows[1:])),
    )
    assert agg.extract_output(whole).tolist() == agg.extract_output(split).tolist()


# ---------------------------------------------------------------------------
# Task 11: PeriodVariance / PeriodStd
# ---------------------------------------------------------------------------


def test_period_variance_matches_numpy() -> None:
    """PeriodVariance matches numpy sample variance (ddof=1) per period."""
    rows = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]]
    frame = _frame_with_lists(rows).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    agg = PeriodVariance("cf")
    got = agg.extract_output(
        agg.add_input(agg.create_accumulator(), agg.batch_reduce(frame, "__period"))
    )
    col0 = np.array([1.0, 2.0, 3.0, 4.0])
    col1 = np.array([10.0, 20.0, 30.0, 40.0])
    assert np.allclose(got, [np.var(col0, ddof=1), np.var(col1, ddof=1)])


def test_period_variance_merge_matches_full() -> None:
    """Welford-Chan merge of two batches equals variance computed on the full set."""
    rows = [[1.0], [2.0], [3.0], [4.0], [5.0]]
    agg = PeriodVariance("cf")

    def reduce(sub: list[list[float]]) -> object:
        frame = _frame_with_lists(sub).with_columns(
            pl.int_ranges(pl.col("cf").list.len()).alias("__period")
        )
        return agg.batch_reduce(frame, "__period")

    whole = agg.add_input(agg.create_accumulator(), reduce(rows))
    split = agg.merge_accumulators(
        agg.add_input(agg.create_accumulator(), reduce(rows[:2])),
        agg.add_input(agg.create_accumulator(), reduce(rows[2:])),
    )
    assert np.allclose(agg.extract_output(whole), agg.extract_output(split))


def test_period_std_is_sqrt_variance() -> None:
    """PeriodStd equals sqrt(PeriodVariance) for the same data."""
    rows = [[1.0], [2.0], [3.0], [4.0]]
    frame = _frame_with_lists(rows).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    v, s = PeriodVariance("cf"), PeriodStd("cf")
    av = v.extract_output(
        v.add_input(v.create_accumulator(), v.batch_reduce(frame, "__period"))
    )
    asd = s.extract_output(
        s.add_input(s.create_accumulator(), s.batch_reduce(frame, "__period"))
    )
    assert np.allclose(asd, np.sqrt(av))


def test_reduce_by_period_over_groups_by_partition_and_period() -> None:
    """One pass returns {partition_tuple: per-period frame}, sorted by period (#over).

    Verifies that _reduce_by_period_over partitions the result by the ``by`` key and
    that each sub-frame contains correct per-period aggregates.
    """
    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 2.0], [3.0, 4.0], [10.0, 20.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    parts = _reduce_by_period_over(
        frame, "__period", "cf", ("product",), pl.col("cf").sum()
    )
    assert set(parts.keys()) == {("A",), ("B",)}
    assert parts[("A",)]["cf"].to_list() == [4.0, 6.0]  # period 0: 1+3, period 1: 2+4
    assert parts[("B",)]["cf"].to_list() == [10.0, 20.0]


def test_batch_reduce_over_returns_partition_partials() -> None:
    """batch_reduce_over returns {partition: partial} for each partition key.

    Verifies PeriodSum.batch_reduce_over partitions and assembles partials matching
    what per-partition batch_reduce would produce.
    """
    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 2.0], [3.0, 4.0], [10.0, 20.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    agg = PeriodSum(column="cf")
    parts = agg.batch_reduce_over(frame, "__period", ("product",))
    assert parts[("A",)].tolist() == [4.0, 6.0]
    assert parts[("B",)].tolist() == [10.0, 20.0]
