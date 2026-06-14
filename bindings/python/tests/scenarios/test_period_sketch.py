# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for rank-based per-period aggregators (sketch-backed)."""

from __future__ import annotations

import math

import polars as pl

from gaspatchio_core.scenarios._period_sketch import build_period_sketches
from gaspatchio_core.scenarios._sketch import SignedSketch

_RA = 1e-4


def test_period_sketch_keeps_trailing_all_null_period() -> None:
    """A trailing all-null period stays in the sketch vector (#9)."""
    frame = pl.DataFrame(
        {"cf": [[1.0, 2.0, None], [3.0, 4.0, None]]},
        schema={"cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    sketches = build_period_sketches(frame, "__period", "cf", relative_accuracy=_RA)
    assert len(sketches) == 3  # period 2 (all-null) retained, not dropped
    assert math.isnan(sketches[2].quantile(0.5))  # no observations -> NaN


def test_from_binned_equals_per_value_build() -> None:
    """from_binned with grouped-key representatives is bit-exact vs per-value build."""
    # Deterministic mixed-sign data with repeats (so binning actually groups).
    values = [round(1000 + (i % 50) * 1.0, 1) for i in range(2000)]
    values += [-(200 + (i % 30) * 1.0) for i in range(500)]
    values += [0.0] * 17

    # (A) per-value build (the ground truth)
    a = SignedSketch(relative_accuracy=_RA)
    for v in values:
        a.add(v)

    # (B) group by exact ddsketch key, then from_binned with a real representative
    a_map = SignedSketch(relative_accuracy=_RA).pos._mapping  # noqa: SLF001
    pos: dict[int, tuple[float, int]] = {}
    neg: dict[int, tuple[float, int]] = {}
    zero_n = 0
    for v in values:
        if v == 0:
            zero_n += 1
        elif v > 0:
            k = a_map.key(v)
            cur = pos.get(k)
            pos[k] = (v, 1) if cur is None else (cur[0], cur[1] + 1)
        else:
            k = a_map.key(-v)
            cur = neg.get(k)
            neg[k] = (-v, 1) if cur is None else (cur[0], cur[1] + 1)

    b = SignedSketch.from_binned(
        pos=list(pos.values()),
        neg=list(neg.values()),
        zero_n=zero_n,
        relative_accuracy=_RA,
    )

    assert a.n == b.n
    for q in (0.01, 0.25, 0.5, 0.75, 0.99):
        assert a.quantile(q) == b.quantile(q)  # bit-exact: same keys, same weights


import numpy as np
import polars as pl

from gaspatchio_core.scenarios._period_sketch import (
    PeriodCTE,
    PeriodMedian,
    PeriodQuantile,
    build_period_sketches,
)


def test_build_period_sketches_matches_per_value() -> None:
    """build_period_sketches is bit-exact vs per-value adds for mixed-sign data."""
    # period 0 and period 1, mixed sign + a zero
    lists = [[1000.0, -200.0], [1000.0, 0.0], [1005.0, -205.0], [1010.0, -195.0]]
    df = pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )
    sketches = build_period_sketches(df, "__period", "cf", relative_accuracy=_RA)
    assert len(sketches) == 2

    # ground truth per period
    cols = [[1000.0, 1000.0, 1005.0, 1010.0], [-200.0, 0.0, -205.0, -195.0]]
    for t, vals in enumerate(cols):
        truth = SignedSketch(relative_accuracy=_RA)
        for v in vals:
            truth.add(v)
        assert sketches[t].n == truth.n
        for q in (0.25, 0.5, 0.75):
            assert sketches[t].quantile(q) == truth.quantile(q)


def _df(lists: list[list[float]]) -> pl.DataFrame:
    return pl.DataFrame({"cf": lists}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period")
    )


def test_period_quantile_per_period() -> None:
    # period 0: 1..100 ; period 1: 1001..1100
    lists = [[float(i), float(1000 + i)] for i in range(1, 101)]
    agg = PeriodQuantile("cf", levels=(0.5,))
    acc = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period"))
    out = agg.extract_output(acc)  # dict level -> ndarray[n_periods]
    assert np.isclose(out[0.5][0], 50.0, rtol=2e-2)
    assert np.isclose(out[0.5][1], 1050.0, rtol=2e-2)


def test_period_quantile_merge_equivalent() -> None:
    lists = [[float(i)] for i in range(1, 201)]
    agg = PeriodQuantile("cf", levels=(0.9,))
    whole = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period"))
    a = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists[:100]), "__period"))
    b = agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists[100:]), "__period"))
    merged = agg.merge_accumulators(a, b)
    assert np.isclose(agg.extract_output(whole)[0.9][0], agg.extract_output(merged)[0.9][0], rtol=1e-9)


def test_period_median() -> None:
    lists = [[float(i), float(1000 + i)] for i in range(1, 101)]
    agg = PeriodMedian("cf")
    out = agg.extract_output(agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period")))
    assert np.isclose(out[0], 50.0, rtol=2e-2)


def test_period_cte_upper_tail() -> None:
    # period 0: 1..1000 ; CTE upper at 0.1 ~ mean of top 10% ~ 950
    lists = [[float(i)] for i in range(1, 1001)]
    agg = PeriodCTE("cf", level=0.1, direction="upper")
    out = agg.extract_output(agg.add_input(agg.create_accumulator(), agg.batch_reduce(_df(lists), "__period")))
    assert 930.0 <= out[0] <= 970.0


def test_run_aggregated_with_period_quantile_matches_full() -> None:
    from gaspatchio_core import ActuarialFrame, run_aggregated

    def model(af: ActuarialFrame) -> ActuarialFrame:
        df = af._df.with_columns(  # noqa: SLF001
            pl.concat_list([pl.col("value"), pl.col("value") * 2]).alias("cf")
        )
        return ActuarialFrame(df)

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 201)]})
    full = run_aggregated(model, mp, [PeriodQuantile("cf", levels=(0.5,)).alias("q")], batch_size=200)
    batched = run_aggregated(model, mp, [PeriodQuantile("cf", levels=(0.5,)).alias("q")], batch_size=37)
    assert np.allclose(full.q[0.5], batched.q[0.5], rtol=1e-9)  # sketch merge is order-stable


def test_period_quantile_top_level_export() -> None:
    import gaspatchio_core as gsp

    for name in ("PeriodQuantile", "PeriodMedian", "PeriodCTE"):
        assert hasattr(gsp, name)


def test_period_sketch_batch_reduce_over_partitions() -> None:
    """Sketch reduce partitions into {partition: list[SignedSketch]} (#over)."""
    from gaspatchio_core.scenarios._period_sketch import PeriodMedian

    frame = pl.DataFrame(
        {"product": ["A", "A", "B"], "cf": [[1.0, 3.0], [5.0, 7.0], [100.0, 200.0]]},
        schema={"product": pl.Utf8, "cf": pl.List(pl.Float64)},
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__period"))
    parts = PeriodMedian(column="cf").batch_reduce_over(frame, "__period", ("product",))
    assert set(parts.keys()) == {("A",), ("B",)}
    # product A, period 0: median(1,5)=3; product B, period 0: median(100)=100
    # DDSketch has bounded relative error (ra=1e-4), so use np.isclose
    assert np.isclose(parts[("A",)][0].quantile(0.5), 3.0, rtol=1e-3)
    assert np.isclose(parts[("B",)][0].quantile(0.5), 100.0, rtol=1e-3)
