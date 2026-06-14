# bindings/python/tests/scenarios/test_run_aggregated.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for run_aggregated + AggregatedResult."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import (
    ArgMax,
    Count,
    PeriodMedian,
    PeriodQuantile,
    PeriodSum,
    Sum,
)
from gaspatchio_core.scenarios._aggregated import AggregatedResult, run_aggregated


def test_aggregated_result_attribute_access() -> None:
    """Alias keys in aggregations are accessible as attributes."""
    res = AggregatedResult(
        aggregations={"net_cf": np.array([1.0, 2.0]), "pv": 7.0},
        n_policies=10,
        n_periods=2,
        batch_size=10,
        wall_time_s=0.1,
        peak_rss_mb=12.0,
    )
    assert res.net_cf.tolist() == [1.0, 2.0]
    assert res.pv == 7.0
    assert res.n_policies == 10


def test_aggregated_result_missing_alias_raises_attributeerror() -> None:
    """Accessing a name not in aggregations raises AttributeError."""
    res = AggregatedResult(
        aggregations={},
        n_policies=1,
        n_periods=1,
        batch_size=1,
        wall_time_s=0.0,
        peak_rss_mb=None,
    )
    with pytest.raises(AttributeError):
        _ = res.does_not_exist


# ---------------------------------------------------------------------------
# Task 6: run_aggregated — single-batch path (dispatch + fold)
# ---------------------------------------------------------------------------


def _toy_model(af: ActuarialFrame) -> ActuarialFrame:
    """Toy model: cf[t] = value * (t+1) for t in 0..2; pv = value (scalar)."""
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.concat_list(
            [pl.col("value"), pl.col("value") * 2, pl.col("value") * 3],
        ).alias("cf"),
        pl.col("value").alias("pv"),
    )
    return ActuarialFrame(lazy)


def _null_list_model(af: ActuarialFrame) -> ActuarialFrame:
    """Yield a List(Float64) column that is entirely null (no real periods)."""
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.lit(None).cast(pl.List(pl.Float64)).alias("cf"),
    )
    return ActuarialFrame(lazy)


def _toy_model_with_product(af: ActuarialFrame) -> ActuarialFrame:
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.concat_list([pl.col("value"), pl.col("value") * 2]).alias("cf"),
    )
    return ActuarialFrame(lazy)


def test_run_aggregated_accepts_scalar_over() -> None:
    """run_aggregated accepts a scalar .over() and partitions the result (#over)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})

    def model(af: ActuarialFrame) -> ActuarialFrame:
        return ActuarialFrame(af._df.with_columns(pl.col("value").alias("pv")))  # noqa: SLF001

    res = run_aggregated(model, mp, [Sum("pv").alias("pv").over("product")])
    out = res.pv.sort("product")
    assert out["product"].to_list() == ["A", "B"]
    assert out["pv"].to_list() == [3.0, 7.0]  # A: 1+2, B: 3+4


def test_run_aggregated_vector_over_partitions_per_period() -> None:
    """PeriodSum.over() runs end-to-end producing a per-partition result."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})
    res = run_aggregated(
        _toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")]
    )
    assert res.cf is not None  # produced a result without raising


def test_run_aggregated_vector_over_is_tidy_and_reconciles() -> None:
    """Vector .over() is tidy {by, period, alias}; partition sums equal the total."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]})
    parted = run_aggregated(
        _toy_model_with_product, mp, [PeriodSum("cf").alias("cf").over("product")]
    )
    total = run_aggregated(_toy_model_with_product, mp, [PeriodSum("cf").alias("cf")])
    tidy = parted.cf
    assert tidy.columns == ["product", "period", "cf"]
    # sum over partitions, per period, equals the unpartitioned total vector
    recon = tidy.group_by("period").agg(pl.col("cf").sum()).sort("period")
    # [1+2+3+4, (1+2+3+4)*2] = [10, 20]
    assert recon["cf"].to_list() == total.cf.tolist()


def test_run_aggregated_rejects_count() -> None:
    """run_aggregated rejects Count (counts scenarios, not policy rows) (#8)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="Count"):
        run_aggregated(_toy_model, mp, [Count("pv").alias("n")])


def test_run_aggregated_rejects_argmax() -> None:
    """run_aggregated rejects ArgMax (needs a scenario axis), not a TypeError (#11)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="scenario"):
        run_aggregated(_toy_model, mp, [ArgMax("pv").alias("worst")])


def test_run_aggregated_all_null_list_column() -> None:
    """An entirely-null List(Float64) column must not crash n_periods (#10)."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(_null_list_model, mp, [PeriodSum("cf").alias("s")])
    assert res.n_periods == 0
    assert res.s.tolist() == []


def test_run_aggregated_single_batch_matches_full() -> None:
    """Single batch: PeriodSum cf=[10,20,30], Sum pv=10, n_policies=4, n_periods=3."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]})  # 4 policies
    res = run_aggregated(
        _toy_model,
        mp,
        aggregations=[PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")],
        batch_size=4,  # one batch
    )
    # cf totals per period: sum(value)*[1,2,3] = 10 * [1,2,3]
    assert res.cf.tolist() == [10.0, 20.0, 30.0]
    assert res.pv == 10.0
    assert res.n_policies == 4
    assert res.n_periods == 3


# ---------------------------------------------------------------------------
# Task 7: multi-batch equivalence + per-batch peak-RSS capture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_batched_equals_full(k: int) -> None:
    """Batched run with batch_size=k equals full single-batch run for all k."""
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    aggs_full = [PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")]
    aggs_batched = [PeriodSum("cf").alias("cf"), Sum("pv").alias("pv")]
    full = run_aggregated(_toy_model, mp, aggs_full, batch_size=10)
    batched = run_aggregated(_toy_model, mp, aggs_batched, batch_size=k)
    assert np.allclose(batched.cf, full.cf, atol=1e-6)
    assert abs(batched.pv - full.pv) < 1e-6
    assert batched.n_periods == 3


def test_peak_rss_recorded() -> None:
    """peak_rss_mb is either None (zero delta) or a non-negative float."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size=1)
    assert res.peak_rss_mb is None or res.peak_rss_mb >= 0.0


# ---------------------------------------------------------------------------
# FIX A: vector aggregator on a list-free model raises a clear ValueError
# ---------------------------------------------------------------------------


def _scalar_only_model(af: ActuarialFrame) -> ActuarialFrame:
    """Model that produces only scalar (non-list) columns."""
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.col("value").alias("pv"),
    )
    return ActuarialFrame(lazy)


def test_vector_agg_on_scalar_model_raises_valueerror() -> None:
    """PeriodSum on a scalar-only model raises ValueError with clear message."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Period\\*.*vector.*aggregator"):
        run_aggregated(
            _scalar_only_model, mp, [PeriodSum("pv").alias("pv")], batch_size=2
        )


def test_scalar_agg_on_scalar_model_works() -> None:
    """Scalar aggregators on a list-free model succeed (no List column required)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
    res = run_aggregated(_scalar_only_model, mp, [Sum("pv").alias("pv")], batch_size=3)
    assert abs(res.pv - 6.0) < 1e-9


# ---------------------------------------------------------------------------
# FIX B: n_periods = max list length across ALL List(Float64) columns
# ---------------------------------------------------------------------------


def _jagged_list_model(af: ActuarialFrame) -> ActuarialFrame:
    """Model producing two list columns of DIFFERENT lengths: cf (3), rider (5)."""
    lazy = af._df.with_columns(  # noqa: SLF001
        pl.concat_list(
            [pl.col("value"), pl.col("value") * 2, pl.col("value") * 3],
        ).alias("cf"),
        pl.concat_list(
            [
                pl.col("value"),
                pl.col("value") * 2,
                pl.col("value") * 3,
                pl.col("value") * 4,
                pl.col("value") * 5,
            ],
        ).alias("rider"),
    )
    return ActuarialFrame(lazy)


def test_n_periods_is_max_across_all_list_columns() -> None:
    """n_periods == 5 when cf has length 3 and rider has length 5."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(
        _jagged_list_model,
        mp,
        [PeriodSum("cf").alias("cf"), PeriodSum("rider").alias("rider")],
        batch_size=2,
    )
    assert res.n_periods == 5


# ---------------------------------------------------------------------------
# Task 8: jagged origin guard (align)
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc  # noqa: E402


@_dc
class _StubSchedule:
    _kind: str
    n_periods: int


def _inception_model(af: ActuarialFrame) -> ActuarialFrame:
    """Toy model with a from_inception projection schedule attached."""
    out = _toy_model(af)
    object.__setattr__(
        out, "_projection", _StubSchedule(_kind="from_inception", n_periods=3)
    )
    return out


def test_inception_aligned_requires_align_duration() -> None:
    """from_inception without align='duration' raises ValueError with 'DURATION'."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    with pytest.raises(ValueError, match="DURATION"):
        run_aggregated(
            _inception_model, mp, [PeriodSum("cf").alias("cf")], batch_size=2
        )


def test_inception_aligned_proceeds_with_align_duration() -> None:
    """from_inception with align='duration' succeeds and produces correct cf totals."""
    mp = pl.DataFrame({"value": [1.0, 2.0]})
    res = run_aggregated(
        _inception_model,
        mp,
        [PeriodSum("cf").alias("cf")],
        batch_size=2,
        align="duration",
    )
    assert res.cf.tolist() == [3.0, 6.0, 9.0]


# ---------------------------------------------------------------------------
# batch_size="auto" — sized to the cgroup memory budget (no working-set cap)
# ---------------------------------------------------------------------------


def test_auto_single_batch_when_budget_is_generous(monkeypatch) -> None:
    """Cap removed: a generous budget resolves 'auto' to a single batch (B == n)."""
    from gaspatchio_core.scenarios import _auto_batch

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 21)]})  # 20 policies
    monkeypatch.setattr(_auto_batch, "memory_budget_bytes", lambda _f: 10_000_000_000)
    res = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert res.batch_size == 20  # whole portfolio fits -> one batch


def test_auto_batches_when_sizer_returns_small_b(monkeypatch) -> None:
    """When the sizer returns a small B, 'auto' batches and stays equivalent to full."""
    import gaspatchio_core.scenarios._aggregated as agg

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 21)]})  # 20 policies
    full = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size=20)
    monkeypatch.setattr(agg, "size_to_budget", lambda *a, **k: 5)
    auto = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert auto.batch_size == 5  # uses the sizer's result
    assert np.allclose(auto.cf, full.cf, atol=1e-6)  # 4 batches == full


def test_auto_seed_peak_zero_uses_frame_size(monkeypatch) -> None:
    """A missed RSS sample (seed_peak==0) must not collapse per_cell to 1 byte (#7)."""
    import gaspatchio_core.scenarios._aggregated as agg

    captured: dict[str, int] = {}
    real_collect = agg._collect_with_peak  # noqa: SLF001

    def _zero_peak(lazy: object, *, engine: str | None = None) -> object:
        frame, _peak = real_collect(lazy, engine=engine)
        return frame, 0  # simulate the sampler missing the transient peak

    def _spy_size(per_cell: int, _n: int, **_kw: object) -> int:
        captured["per_cell"] = per_cell
        return 1  # tiny batch keeps the run cheap

    monkeypatch.setattr(agg, "_collect_with_peak", _zero_peak)
    monkeypatch.setattr(agg, "size_to_budget", _spy_size)
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert captured["per_cell"] > 1  # frame size used as the floor, not the bogus 1


# ---------------------------------------------------------------------------
# Task 10: public exports + shared-surface smoke + small-N gate
# ---------------------------------------------------------------------------


def test_top_level_exports() -> None:
    """run_aggregated and all Period* classes are accessible from gaspatchio_core."""
    import gaspatchio_core as gsp

    assert hasattr(gsp, "run_aggregated")
    for name in ("PeriodSum", "PeriodCount", "PeriodMean", "PeriodMin", "PeriodMax"):
        assert hasattr(gsp, name), f"gaspatchio_core.{name} missing"


def test_small_n_single_batch_is_no_op() -> None:
    """With 3 policies and batch_size='auto', resolved batch_size == 3 (one batch)."""
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
    res = run_aggregated(_toy_model, mp, [PeriodSum("cf").alias("cf")], batch_size="auto")
    assert res.batch_size == 3  # everything fits in one batch


def test_period_aggregator_runs_in_for_each_scenario() -> None:
    """Shared-surface: PeriodSum works unchanged on the scenario axis via for_each_scenario."""
    from gaspatchio_core.scenarios import for_each_scenario

    # Build the frame once: 2 policies, cf=[value*(t+1)] for t in 0..2
    # value=[1,2] -> cf_0=[1,2,3], cf_1=[2,4,6] -> portfolio sum=[3,6,9]
    base_af = ActuarialFrame(
        _toy_model(ActuarialFrame(pl.DataFrame({"value": [1.0, 2.0]})))._df.collect()  # noqa: SLF001
    )
    result = for_each_scenario(
        base_af,
        [1],
        model_fn=lambda a, **_: a,
        aggregations=[PeriodSum("cf").alias("cf")],
    )
    assert np.asarray(result.aggregations["cf"]).tolist() == [3.0, 6.0, 9.0]


# ---------------------------------------------------------------------------
# Task 7 (continued): multi-col .over(), batch-size invariance, PeriodMedian.over(),
#                     and PeriodQuantile.over() deferred with clear error
# ---------------------------------------------------------------------------


def test_run_aggregated_over_multi_column() -> None:
    """.over(('product','cohort')) keys partitions by both columns (#over)."""
    mp = pl.DataFrame(
        {
            "value": [1.0, 2.0, 3.0],
            "product": ["A", "A", "B"],
            "cohort": [2020, 2021, 2020],
        }
    )

    def model(af: ActuarialFrame) -> ActuarialFrame:
        return ActuarialFrame(af._df.with_columns(pl.col("value").alias("pv")))  # noqa: SLF001

    res = run_aggregated(model, mp, [Sum("pv").alias("pv").over(("product", "cohort"))])
    out = res.pv.sort(["product", "cohort"])
    assert out["product"].to_list() == ["A", "A", "B"]
    assert out["cohort"].to_list() == [2020, 2021, 2020]
    assert out["pv"].to_list() == [1.0, 2.0, 3.0]


def test_run_aggregated_over_batched_equals_single_batch() -> None:
    """Partitioned output is batch-size-invariant (#over)."""
    mp = pl.DataFrame(
        {"value": [float(i) for i in range(1, 9)], "product": ["A", "B"] * 4}
    )
    full = run_aggregated(
        _toy_model_with_product,
        mp,
        [PeriodSum("cf").alias("cf").over("product")],
        batch_size=8,
    )
    batched = run_aggregated(
        _toy_model_with_product,
        mp,
        [PeriodSum("cf").alias("cf").over("product")],
        batch_size=3,
    )
    full_sorted = full.cf.sort(["product", "period"])
    batched_sorted = batched.cf.sort(["product", "period"])
    assert full_sorted.equals(batched_sorted)


def test_run_aggregated_period_median_over() -> None:
    """PeriodMedian.over() produces per-partition medians, tidy (#over)."""
    mp = pl.DataFrame(
        {"value": [1.0, 5.0, 100.0, 300.0], "product": ["A", "A", "B", "B"]}
    )
    res = run_aggregated(
        _toy_model_with_product, mp, [PeriodMedian("cf").alias("med").over("product")]
    )
    med = res.med.filter(pl.col("period") == 0).sort("product")
    # median(1,5)=3 ; median(100,300)=200  (DDSketch: bounded rel error)
    assert np.isclose(med["med"].to_list()[0], 3.0, rtol=1e-2)
    assert np.isclose(med["med"].to_list()[1], 200.0, rtol=1e-2)


def test_run_aggregated_period_quantile_over_not_supported() -> None:
    """PeriodQuantile.over() (multi-level) is deferred with a clear error (#over)."""
    mp = pl.DataFrame({"value": [1.0, 2.0], "product": ["A", "B"]})
    with pytest.raises(NotImplementedError, match="PeriodQuantile"):
        run_aggregated(
            _toy_model_with_product,
            mp,
            [PeriodQuantile("cf").alias("q").over("product")],
        )
