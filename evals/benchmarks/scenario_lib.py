# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Shared library for scenario benchmarks, test-drive, and showcase.

Provides: a deterministic risk-neutral fund-return generator, a deterministic
shock bank, the L5 model loader + a model_fn adapter for the bounded-memory
scenario loop, and a ScenarioResult -> metrics helper.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios.shocks import Shock

REPO_ROOT = Path(__file__).resolve().parents[2]
L5_DIR = REPO_ROOT / "tutorial" / "level-5-scenarios" / "base"
L5_ASSUMPTIONS = L5_DIR / "assumptions"

_FUNDS = ["FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6"]
# Fallback annualised vols if index_parameters.parquet is absent (Step 1).
_FALLBACK_VOLS = {"FUND1": 0.05, "FUND2": 0.08, "FUND3": 0.12,
                  "FUND4": 0.15, "FUND5": 0.18, "FUND6": 0.20}


def _load_vols() -> dict[str, float]:
    f = L5_ASSUMPTIONS / "index_parameters.parquet"
    if not f.exists():
        return dict(_FALLBACK_VOLS)
    ip = pl.read_parquet(f)
    return {r["fund_index"]: r["volatility"] for r in ip.iter_rows(named=True)}


def generate_stochastic_returns(
    n_scenarios: int = 1000, n_months: int = 180, seed: int = 12345,
) -> pl.DataFrame:
    """Risk-neutral GBM monthly fund returns: scenario_id, t, FUND1..FUND6.

    log_return = (f - 0.5*vol^2)*dt + vol*sqrt(dt)*Z ; monthly = exp(log_return)-1.
    """
    vols = _load_vols()
    rf = pl.read_parquet(L5_ASSUMPTIONS / "risk_free_rates.parquet").filter(
        (pl.col("scenario") == "BASE") & (pl.col("currency") == "USD")
    ).sort("year")
    rf_by_year = {r["year"]: r["forward_rate"] for r in rf.iter_rows(named=True)}
    max_year = max(rf_by_year)
    years = np.minimum(np.arange(n_months) // 12, max_year)
    f_arr = np.array([rf_by_year.get(int(y), rf_by_year[max_year]) for y in years])

    rng = np.random.default_rng(seed)
    dt, sqrt_dt = 1 / 12, np.sqrt(1 / 12)
    z = rng.standard_normal((n_scenarios, n_months, len(_FUNDS)))

    cols: dict[str, Any] = {
        "scenario_id": np.repeat(np.arange(1, n_scenarios + 1), n_months),
        "t": np.tile(np.arange(n_months), n_scenarios),
    }
    for fi, fund in enumerate(_FUNDS):
        vol = vols.get(fund, _FALLBACK_VOLS[fund])
        drift = (f_arr - 0.5 * vol**2) * dt  # (n_months,)
        log_r = drift[None, :] + vol * sqrt_dt * z[:, :, fi]  # (n_scen, n_months)
        cols[fund] = (np.exp(log_r) - 1.0).reshape(-1)
    return pl.DataFrame(cols)


def make_shock_bank(n: int) -> dict[int, list[Shock]]:
    """N reproducible deterministic shocks for the perf grid.

    Scenario i applies a mortality-scalar multiplier on a fixed sweep in
    [0.8, 1.2] -- no RNG (perf tracking must be reproducible across runs).
    """
    from gaspatchio_core.scenarios.shocks import MultiplicativeShock  # noqa: PLC0415

    out: dict[int, list[Shock]] = {}
    for i in range(1, n + 1):
        factor = 0.8 + 0.4 * ((i - 1) / max(n - 1, 1))  # linear sweep, deterministic
        out[i] = [
            MultiplicativeShock(factor=round(factor, 6), table="mortality_scalars"),
        ]
    return out


def load_l5_model() -> ModuleType:
    """Load the L5 tutorial model.py as a uniquely-named module."""
    model_path = L5_DIR / "model.py"
    if str(L5_DIR) not in sys.path:
        sys.path.insert(0, str(L5_DIR))
    spec = importlib.util.spec_from_file_location("bench_l5_model", model_path)
    if spec is None or spec.loader is None:
        msg = f"cannot load {model_path}"
        raise RuntimeError(msg)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bench_l5_model"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_stochastic_model_fn(
    l5: ModuleType, stochastic_returns: pl.DataFrame,
) -> Callable[..., ActuarialFrame]:
    """Adapt L5 ``main`` to the for_each_scenario ``model_fn(af, *, tables, drivers)``.

    The loop hands us an ``af`` already carrying this batch's ``scenario_id``
    column; L5 looks up its own stochastic returns per row from the full
    returns table. ``tables``/``drivers`` are unused on the stochastic path
    (no shocks).
    """
    def model_fn(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        return l5.main(af, scenario_returns_override=stochastic_returns)

    return model_fn


def read_result_metrics(
    result: Any,  # noqa: ANN401 -- duck-typed ScenarioResult
    n_scenarios: int,
    n_points: int,
) -> dict[str, float | str]:
    """Pull chartable metrics off a ScenarioResult."""
    wall = float(result.wall_time_s)
    return {
        "wall_s": round(wall, 3),
        "peak_rss_mb": (
            round(float(result.peak_rss_mb), 1) if result.peak_rss_mb else -1.0
        ),
        "throughput": (
            round((n_scenarios * n_points) / wall, 1) if wall > 0 else 0.0
        ),
        "batch_size": int(result.batch_size),
        "batch_size_resolution": str(result.batch_size_resolution),
    }


def portfolio_cte(losses: np.ndarray, level: float) -> float:
    """Conditional Tail Expectation (TVaR) at ``level``: mean of the worst losses.

    CTE_p = mean of losses at or above the ``level``-quantile of ``losses``. With
    ``losses = -portfolio_total``, CTE70 mirrors the VM-21 statutory reserve and
    CTE95 the economic-capital tail. Illustrative on tutorial data.
    """
    threshold = np.quantile(losses, level)
    tail = losses[losses >= threshold]
    return float(tail.mean())
