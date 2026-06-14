# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Integration gate — run_aggregated / run_to_parquet on the real L4 model.
# ABOUTME: Validates batched==full + spill round-trip on a production jagged model.

"""Integration tests for the unified aggregation surface on the real L4 model.

The L4 (reconciled-lifelib) VA model uses ``per_policy=True`` jagged timelines and
emits the per-period ``List(Float64)`` cashflow columns the surface aggregates over.
These tests prove the toy-model guarantees hold on a production model: batched ==
full single-pass, the full-materialise aggregate matches, the parquet spill writes
every policy, and rank-based quantiles are cross-K stable.

The module skips cleanly if the tutorial model or its (git-LFS) data is absent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio_core.scenarios import PeriodQuantile, PeriodSum, Sum

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

_L4_DIR = Path(__file__).resolve().parents[4] / "tutorial" / "level-4-lifelib" / "base"
_L4_MODEL_PY = _L4_DIR / "model.py"
_L4_POINTS = _L4_DIR / "model_points.parquet"
_LIFELIB_REF = _L4_DIR.parent / "reference" / "lifelib_reference.parquet"

# Present-value variables reconciled to lifelib (see tutorial/.../reconcile.py).
_PV_COLUMNS = (
    "pv_net_cf",
    "pv_claims",
    "pv_claims_death",
    "pv_claims_lapse",
    "pv_claims_maturity",
    "pv_expenses",
    "pv_commissions",
    "pv_premiums",
    "pv_inv_income",
    "pv_av_change",
)
_LIFELIB_TOLERANCE_PCT = 1e-4  # same threshold reconcile.py uses for 0.0000%

pytestmark = pytest.mark.skipif(
    not (_L4_MODEL_PY.exists() and _L4_POINTS.exists()),
    reason="L4 tutorial model/points not available",
)

def _load_l4_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("l4_itest_model", _L4_MODEL_PY)
    if spec is None or spec.loader is None:
        pytest.skip("L4 model not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def l4() -> tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame]:
    """Bound L4 model function (assumptions loaded once) + its 8 base model points."""
    try:
        model = _load_l4_module()
        mp = pl.read_parquet(_L4_POINTS)
        assumptions = model.load_assumptions()
    except (OSError, pl.exceptions.PolarsError, AttributeError) as exc:
        # git-LFS pointer not pulled, missing assumptions, etc. -> skip, don't fail.
        pytest.skip(f"L4 model data unavailable: {exc}")

    def model_fn(af: ActuarialFrame) -> ActuarialFrame:
        return cast("ActuarialFrame", model.main(af, assumptions_override=assumptions))

    return model_fn, mp


def _aggregations() -> list[Any]:
    return [
        PeriodSum("net_cf").alias("net_cf"),
        PeriodSum("claims").alias("claims"),
        Sum("pv_net_cf").alias("pv_net_cf"),
    ]


def test_batched_equals_full(
    l4: tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame],
) -> None:
    """Batched run == single-batch run, bit-exact, on the real jagged model."""
    model_fn, mp = l4
    full = run_aggregated(model_fn, mp, _aggregations(), batch_size=mp.height)
    batched = run_aggregated(model_fn, mp, _aggregations(), batch_size=3)

    assert full.n_periods == batched.n_periods
    assert np.allclose(np.asarray(full.net_cf), np.asarray(batched.net_cf), rtol=1e-9)
    assert np.allclose(np.asarray(full.claims), np.asarray(batched.claims), rtol=1e-9)
    pv_tol = 1e-6 * max(1.0, abs(full.pv_net_cf))
    assert abs(full.pv_net_cf - batched.pv_net_cf) <= pv_tol


def test_aggregated_equals_full_materialize(
    l4: tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame],
) -> None:
    """run_aggregated == materialise-then-aggregate (the baseline path)."""
    model_fn, mp = l4
    agg = run_aggregated(model_fn, mp, _aggregations(), batch_size=3)

    proj = model_fn(ActuarialFrame(mp)).collect()
    manual_net_cf = (
        proj.lazy()
        .select(pl.col("net_cf"))
        .with_columns(pl.int_ranges(pl.col("net_cf").list.len()).alias("p"))
        .explode(["net_cf", "p"])
        .group_by("p")
        .agg(pl.col("net_cf").sum())
        .sort("p")
        .collect()["net_cf"]
        .to_numpy()
    )
    assert np.allclose(manual_net_cf, np.asarray(agg.net_cf), rtol=1e-9)
    manual_pv = float(proj["pv_net_cf"].sum())
    assert abs(manual_pv - agg.pv_net_cf) <= 1e-6 * max(1.0, abs(manual_pv))


def test_run_to_parquet_round_trips_full_output(
    l4: tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame],
    tmp_path: Path,
) -> None:
    """Spill writes every policy's full projection exactly once, recoverable."""
    model_fn, mp = l4
    out_dir = tmp_path / "out"
    res = run_to_parquet(model_fn, mp, out_dir, batch_size=3)

    files = sorted(out_dir.glob("batch_*.parquet"))
    assert len(files) == res.n_batches
    assert res.n_policies == mp.height
    combined = pl.concat([pl.read_parquet(f) for f in files])
    assert combined.height == mp.height  # every policy written exactly once
    assert "net_cf" in combined.columns  # a full per-period output column survived


def test_period_quantile_cross_k_stable(
    l4: tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame],
) -> None:
    """Per-period median of net_cf: identical full vs batched (exact sketch merge)."""
    model_fn, mp = l4

    def quantile() -> list[Any]:
        return [PeriodQuantile("net_cf", levels=(0.5,)).alias("q")]

    full = run_aggregated(model_fn, mp, quantile(), batch_size=mp.height)
    batched = run_aggregated(model_fn, mp, quantile(), batch_size=3)
    assert np.allclose(full.q[0.5], batched.q[0.5], rtol=1e-9)


@pytest.mark.skipif(
    not _LIFELIB_REF.exists(), reason="lifelib reference parquet not available"
)
def test_run_aggregated_matches_lifelib_portfolio_pv(
    l4: tuple[Callable[[ActuarialFrame], ActuarialFrame], pl.DataFrame],
) -> None:
    """Batched portfolio PVs equal the aggregate of the lifelib reference (<=0.0001%).

    Closes the loop to actuarial truth. L4's per-policy PVs reconcile to lifelib at
    0.0000% (tutorial/.../reconcile.py); this asserts the *batched* portfolio total
    run_aggregated produces equals the aggregate of that same lifelib reference -- so
    the streamed aggregate is lifelib-correct, not merely self-consistent with the
    full projection.
    """
    model_fn, mp = l4
    aggs = [Sum(col).alias(col) for col in _PV_COLUMNS]
    res = run_aggregated(model_fn, mp, aggs, batch_size=3)

    ref = pl.read_parquet(_LIFELIB_REF).filter(pl.col("t") == 0)  # one row per point
    for col in _PV_COLUMNS:
        gsp_total = float(getattr(res, col))
        lifelib_total = float(ref[col].sum())
        denom = max(abs(lifelib_total), 1.0)
        diff_pct = abs(gsp_total - lifelib_total) / denom * 100.0
        assert diff_pct < _LIFELIB_TOLERANCE_PCT, (
            f"{col}: run_aggregated={gsp_total} lifelib={lifelib_total} "
            f"diff={diff_pct:.6f}%"
        )
