# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the scenario benchmark/showcase shared library."""

from __future__ import annotations

import polars as pl
from evals.benchmarks.run_scenario_benchmarks import cell_to_json_rows, run_cell
from evals.benchmarks.scenario_lib import (
    L5_DIR,
    generate_stochastic_returns,
    load_l5_model,
    make_shock_bank,
    make_stochastic_model_fn,
)

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario, with_scenarios
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


def test_returns_schema_and_shape() -> None:
    """Wide schema, row count, scenario ids and month index are correct."""
    df = generate_stochastic_returns(n_scenarios=5, n_months=12, seed=42)
    assert set(df.columns) == {
        "scenario_id", "t", "FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6",
    }
    assert df.height == 5 * 12
    assert sorted(df["scenario_id"].unique().to_list()) == [1, 2, 3, 4, 5]
    assert df["t"].max() == 11


def test_returns_are_deterministic() -> None:
    """Same seed yields identical output across calls."""
    a = generate_stochastic_returns(n_scenarios=4, n_months=12, seed=7)
    b = generate_stochastic_returns(n_scenarios=4, n_months=12, seed=7)
    assert a.equals(b)


def test_shock_bank_count_and_determinism() -> None:
    """Bank has N entries keyed 1..N and is reproducible across calls."""
    a = make_shock_bank(50)
    b = make_shock_bank(50)
    assert len(a) == 50
    assert set(a) == set(range(1, 51))
    # Reproducible: same id -> same factor.
    fa = a[7][0]
    fb = b[7][0]
    assert isinstance(fa, MultiplicativeShock)
    assert fa.factor == fb.factor
    assert fa.table == "mortality_scalars"


def test_adapter_runs_l5_and_emits_pv_net_cf() -> None:
    """The adapter runs the real L5 model and yields pv_net_cf."""
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(n_scenarios=2, n_months=180, seed=1)
    model_fn = make_stochastic_model_fn(l5, returns)
    af = ActuarialFrame(mp.with_columns(pl.lit(1).alias("scenario_id")))
    out = model_fn(af, tables=None, drivers=None).collect()
    assert "pv_net_cf" in out.columns
    assert out.height == mp.height


def test_auto_loop_equals_manual_reference_n8() -> None:
    """for_each_scenario(auto) per-scenario totals == manual with_scenarios+group_by."""
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(n_scenarios=8, n_months=180, seed=99)

    # Reference: the known-good manual path.
    ref_af = with_scenarios(ActuarialFrame(mp), list(range(1, 9)))
    ref = (
        l5.main(ref_af, scenario_returns_override=returns).collect()
        .group_by("scenario_id").agg(pl.col("pv_net_cf").sum().alias("total"))
        .sort("scenario_id")
    )

    # Under test: the bounded-memory auto loop.
    model_fn = make_stochastic_model_fn(l5, returns)
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, 9)),
        model_fn=model_fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    got = result.aggregations["total"].sort("scenario_id")

    ref_tot = ref["total"].to_list()
    got_tot = got["total"].to_list()
    assert len(got_tot) == 8
    for r, g in zip(ref_tot, got_tot, strict=True):
        assert abs(r - g) <= 1e-6 * max(1.0, abs(r)), (r, g)


def test_run_cell_emits_metrics_small() -> None:
    """A small cell returns the chartable metric dict."""
    res = run_cell(n_scenarios=4, points_path=L5_DIR / "model_points.parquet")
    assert res["n_scenarios"] == 4
    assert res["wall_s"] > 0
    assert res["batch_size"] >= 1
    assert res["batch_size_resolution"] in {"manual", "auto_search"}


def test_cell_to_json_rows_schema() -> None:
    """One cell maps to four {name,unit,value} rows with the expected names."""
    cell = {"wall_s": 1.5, "peak_rss_mb": 500.0, "throughput": 666.6,
            "batch_size": 4, "batch_size_resolution": "auto_search",
            "n_scenarios": 100, "n_points": 1000}
    rows = cell_to_json_rows("scen-scaling", cell)
    names = {r["name"] for r in rows}
    assert names == {
        "scen-scaling/1Kpts-0100sc-wall",
        "scen-scaling/1Kpts-0100sc-rss",
        "scen-scaling/1Kpts-0100sc-throughput",
        "scen-scaling/1Kpts-0100sc-batch",
    }
    for r in rows:
        assert set(r) == {"name", "unit", "value"}
