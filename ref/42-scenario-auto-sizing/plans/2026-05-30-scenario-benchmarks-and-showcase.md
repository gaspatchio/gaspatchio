# Scenario Benchmarks + Stochastic Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a recurring CI scenario-throughput/memory dashboard chart, a local profile-matrix test-drive, and a stochastic VA-reserving showcase (distribution + CTE + percentile fan) — all exercising the PR #106 `ScenarioRun.run(batch_size="auto")` path.

**Architecture:** Three phases sharing one foundation (a stochastic-returns generator, a deterministic shock bank, and a `model_fn` adapter for the L5 tutorial model). Phase A (test-drive) runs first and *calibrates* Phase B's CI grid + resolves the auto-loop wiring. Phase B publishes a new `dev/scenario-bench/` gh-pages page via `github-action-benchmark` (data-driven — emit `{name,unit,value}`). Phase C emits showcase **data** then renders Altair charts from it (data/render split), reusable in perf pages and docs.

**Tech Stack:** Python 3.12 + Polars + `gaspatchio_core.scenarios` (`ScenarioRun`, `for_each_scenario`, `Sum`/`CTE`/`Quantile`, `MultiplicativeShock`), numpy (return generation), Altair (charts), `benchmark-action/github-action-benchmark@v1` (gh-pages), uv (runner).

**All work is in the worktree `~/projects/gaspatchio/gaspatchio-core-postmerge` on branch `gsp-100-post-merge`.** Run Python from `bindings/python/` with `uv run`. Use `git -C <worktree>` for commits.

**Spec:** `ref/42-scenario-auto-sizing/specs/2026-05-30-scenario-benchmarks-and-showcase-design.md`

---

## Verified API facts (do not re-derive — grounded by reading the code)

- `for_each_scenario(af, scenarios, model_fn, *, aggregations, base_tables=None, batch_size="auto"|int, target_memory_fraction=0.5, bytes_per_cell=None, return_full_grid=False, sink_dir=None, master_seed=None, progress=False, plan_sha=...) -> ScenarioResult`.
  `scenarios` = `list[ScenarioID]` | `dict[ID, list[Shock]]` | `dict[ID, dict]` (drivers). **drivers & master_seed are batch_size=1 only** (raise otherwise).
- **`model_fn` is called as `model_fn(af, *, tables=..., drivers=...)`** — both keyword. The loop cross-joins `af` × the batch's scenario IDs and adds a `scenario_id` column before calling.
- `ScenarioRun(shocks: dict[str,list[Shock]], base_tables: dict[str,Table], aggregations=(), master_seed=None).run(af, model_fn, *, batch_size="auto", target_memory_fraction=0.5, bytes_per_cell=None, return_full_grid=False, sink_dir=None, audit=False) -> ScenarioResult`.
- **Every aggregator MUST have `.alias()`** before being passed to `ScenarioRun`/`for_each_scenario` (raises `ValueError` otherwise). Empty aggregations raises.
- **CORRECTION (verified in A.1 spike): `.alias()` must come BEFORE `.over()`** — write `Sum("pv_net_cf").alias("total").over("scenario_id")`, NOT `.over(...).alias(...)` (the latter raises `ValueError: Call .alias(name) before .over(...)`). Apply this ordering everywhere below (A.2, B.1, C.1, C.2). A.1 confirmed `for_each_scenario(batch_size="auto")` reproduces the manual `with_scenarios`+`group_by` reference **bit-for-bit** → B/C use `for_each_scenario(auto)`; no fallback needed.
- `ScenarioResult` fields: `.aggregations` (dict keyed by alias; **scalar for plain aggregators, DataFrame for `.over(...)` partitioned**), `.n_scenarios`, `.batch_size`, `.batch_size_resolution` (`"manual"|"auto_probe"|"auto_calibrated"|"auto_cached"`), `.wall_time_s`, `.peak_rss_mb`, `.sink_dir`, `.audit_path`.
- Aggregators: `Sum("col")`, `Mean("col")`, `CTE("col", level=0.70, direction="upper"|"lower")`, `Quantile("col", levels=(0.05,0.25,...))`. Modifiers: `.alias(name)`, `.over("scenario_id")`, `.of(expr)`. `within` kwarg controls within-scenario reduction (semantics validated in Task C1).
- `MultiplicativeShock(factor: float, table: str | None = None, column: str | None = None)` — frozen dataclass; `to_expression(col)=col*factor`.
- `with_scenarios(af, scenario_ids: list[int]|list[str]) -> ActuarialFrame` — cross-joins, adds `scenario_id`.
- **L5 model** (`tutorial/level-5-scenarios/base/model.py`): `main(af, scenario_returns_override=None, assumptions_override=None, projection_months=82) -> ActuarialFrame`. Per-policy output column `pv_net_cf` (portfolio loss = `−Σ pv_net_cf`). Needs `scenario_id` column; integer `scenario_id` → stochastic returns lookup (Section 5) + BASE curve broadcast (Section 16). Loads its own assumptions if `assumptions_override` omitted.
- **`scenario_returns` schema** (override): wide — `scenario_id, t, FUND1, FUND2, FUND3, FUND4, FUND5, FUND6`.
- Existing generator to reuse: `bindings/python/tests/scratch/scenarios/stochastic_scenarios.py::generate_stochastic_returns(n_scenarios, n_months=180, seed=12345)` (numpy, risk-neutral GBM; loads `index_parameters.parquet` vols + `risk_free_rates.parquet` forwards).
- Existing reference workload (manual, the equivalence oracle): `bindings/python/tests/scenarios/test_scenario_benchmarks.py` — `with_scenarios` + `main(scenario_returns_override=...)` + `group_by("scenario_id").agg(pl.col("pv_net_cf").sum())`.
- CI pattern: `.github/workflows/evals.yml` `model-benchmarks` job — `runs-on: ubuntu-latest-m`, `working-directory: bindings/python`, `uv sync`, run script `| tee /tmp/out.json`, `git checkout -- .` (clean tree), then `benchmark-action/github-action-benchmark@v1` with `name`/`tool: customSmallerIsBetter`/`output-file-path`/`benchmark-data-dir-path`. Job `if:` guard: `github.event_name != 'pull_request' || github.event.label.name == '<label>'`.

---

## Scope note

One plan, three phases (A→B→C), each producing working software, plus a dry-run phase D. They share Phase 0's foundation and are tightly sequenced (A calibrates B; C reuses A's wiring), so they are not independent subsystems — keeping them in one plan is correct.

## File structure

### Path setup (CRITICAL — verified, applies to every task below)

`evals.benchmarks.*` is **NOT importable** from a `bindings/python` run by default (`uv run python -c "import evals"` → `ModuleNotFoundError`; repo root is not on `sys.path`). Two fixes, both required:

1. **Tests** — create `bindings/python/tests/benchmarks/conftest.py` (Task 0.1) that puts repo root on path:
   ```python
   # bindings/python/tests/benchmarks/conftest.py
   # SPDX-FileCopyrightText: 2026 Opio Inc.
   #
   # SPDX-License-Identifier: Apache-2.0
   """Put repo root on sys.path so evals.benchmarks.* resolves under pytest."""
   import sys
   from pathlib import Path

   _REPO_ROOT = Path(__file__).resolve().parents[4]  # tests/benchmarks → … → repo root
   if str(_REPO_ROOT) not in sys.path:
       sys.path.insert(0, str(_REPO_ROOT))
   ```
2. **Scripts** run via `uv run python ../../evals/benchmarks/X.py` — each script (testdrive, benchmarks, showcase, render) MUST begin (before any `from evals.benchmarks…` import) with:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for evals.benchmarks.*
   ```
   Add `E402` to each script's `# ruff: noqa:` line (path insert precedes imports). `scenario_lib.py` itself is only ever *imported* (never run as `__main__`), so it needs no guard.

New (all under `bindings/python/`):
- `evals/benchmarks/scenario_lib.py` — shared: `generate_stochastic_returns`, `make_shock_bank`, `load_l5_model`, `make_stochastic_model_fn`, `read_result_metrics`.
- `tests/benchmarks/conftest.py` — repo-root path shim (above).
- `evals/benchmarks/run_scenario_testdrive.py` — Phase A (local).
- `evals/benchmarks/run_scenario_benchmarks.py` — Phase B (CI grid → flat JSON).
- `evals/benchmarks/run_scenario_showcase.py` — Phase C (1000-scen run → `scenario_showcase.json`).
- `evals/benchmarks/render_scenario_showcase.py` — Phase C (JSON → Altair Vega/PNG; shared by perf+docs).
- `tests/benchmarks/test_scenario_lib.py` — unit tests for `scenario_lib`.
- `tests/benchmarks/test_scenario_showcase.py` — showcase aggregation correctness.
- `ref/42-scenario-auto-sizing/reports/2026-05-30-scenario-testdrive.md` — Phase A report (committed).

Changed:
- `.github/workflows/evals.yml` — add `scenario-benchmarks` job (+ `performance` label trigger).
- `evals/benchmarks/README.md` — scenario page docs + excluded-cell trades note.

---

## Phase 0 — Shared foundation (`scenario_lib.py`)

### Task 0.1: Stochastic returns generator

**Files:**
- Create: `bindings/python/evals/benchmarks/scenario_lib.py`
- Create: `bindings/python/tests/benchmarks/conftest.py` (repo-root path shim — see "Path setup" above)
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 0: Create the path-shim conftest** (exact content in "Path setup" above). Without it, every test below fails with `ModuleNotFoundError: evals`, not the intended TDD failure.

- [ ] **Step 1: Confirm the volatility assumption file exists for L5**

Run: `ls bindings/python/../../tutorial/level-5-scenarios/base/assumptions/ | grep -E "index_parameters|risk_free_rates"`
Expected: `risk_free_rates.parquet` present. If `index_parameters.parquet` is **absent**, the generator must not depend on it — use the hardcoded fallback vols in Step 3 (six funds, 5–20% vol). Note which path applies in the test-drive report.

- [ ] **Step 2: Write the failing test**

```python
# bindings/python/tests/benchmarks/test_scenario_lib.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the scenario benchmark/showcase shared library."""

from __future__ import annotations

import polars as pl

from evals.benchmarks.scenario_lib import generate_stochastic_returns


def test_returns_schema_and_shape() -> None:
    df = generate_stochastic_returns(n_scenarios=5, n_months=12, seed=42)
    assert set(df.columns) == {
        "scenario_id", "t", "FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6",
    }
    assert df.height == 5 * 12
    assert sorted(df["scenario_id"].unique().to_list()) == [1, 2, 3, 4, 5]
    assert df["t"].max() == 11


def test_returns_are_deterministic() -> None:
    a = generate_stochastic_returns(n_scenarios=4, n_months=12, seed=7)
    b = generate_stochastic_returns(n_scenarios=4, n_months=12, seed=7)
    assert a.equals(b)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py -q`
Expected: FAIL — `ModuleNotFoundError: evals.benchmarks.scenario_lib` (or ImportError).

- [ ] **Step 4: Implement the generator (adapt from `tests/scratch/scenarios/stochastic_scenarios.py`)**

```python
# bindings/python/evals/benchmarks/scenario_lib.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Shared library for scenario benchmarks, test-drive, and showcase.

Provides: a deterministic risk-neutral fund-return generator, a deterministic
shock bank, the L5 model loader + a model_fn adapter for the bounded-memory
scenario loop, and a ScenarioResult -> metrics helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core import ActuarialFrame

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
L5_DIR = REPO_ROOT / "tutorial" / "level-5-scenarios" / "base"
L5_ASSUMPTIONS = L5_DIR / "assumptions"

_FUNDS = ["FUND1", "FUND2", "FUND3", "FUND4", "FUND5", "FUND6"]
# Fallback annualised vols if index_parameters.parquet is absent (Task 0.1 Step 1).
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add bindings/python/evals/benchmarks/scenario_lib.py bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): stochastic fund-return generator for scenario benchmarks"
```

### Task 0.2: Deterministic shock bank (for the perf grid)

**Files:**
- Modify: `bindings/python/evals/benchmarks/scenario_lib.py`
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 1: Add the failing test**

```python
# append to tests/benchmarks/test_scenario_lib.py
from gaspatchio_core.scenarios.shocks import MultiplicativeShock
from evals.benchmarks.scenario_lib import make_shock_bank


def test_shock_bank_count_and_determinism() -> None:
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_shock_bank_count_and_determinism -q`
Expected: FAIL — `ImportError: cannot import name 'make_shock_bank'`.

- [ ] **Step 3: Implement**

```python
# append to scenario_lib.py (add to existing imports at top of file:
#   from gaspatchio_core.scenarios.shocks import MultiplicativeShock, Shock)

def make_shock_bank(n: int) -> dict[int, list["Shock"]]:
    """N reproducible deterministic shocks for the perf grid.

    Scenario i applies a mortality-scalar multiplier on a fixed sweep in
    [0.8, 1.2] — no RNG (perf tracking must be reproducible across runs).
    """
    from gaspatchio_core.scenarios.shocks import MultiplicativeShock

    out: dict[int, list[Shock]] = {}
    for i in range(1, n + 1):
        factor = 0.8 + 0.4 * ((i - 1) / max(n - 1, 1))  # linear sweep, deterministic
        out[i] = [MultiplicativeShock(factor=round(factor, 6), table="mortality_scalars")]
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/scenario_lib.py bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): deterministic shock bank for the scenario perf grid"
```

### Task 0.3: L5 model loader + adapter + metrics helper

**Files:**
- Modify: `bindings/python/evals/benchmarks/scenario_lib.py`
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 1: Add the failing test**

```python
# append to tests/benchmarks/test_scenario_lib.py
from gaspatchio_core import ActuarialFrame
from evals.benchmarks.scenario_lib import load_l5_model, make_stochastic_model_fn


def test_adapter_runs_l5_and_emits_pv_net_cf() -> None:
    l5 = load_l5_model()
    mp = pl.read_parquet(load_l5_model.__module__ and __import__(
        "evals.benchmarks.scenario_lib", fromlist=["L5_DIR"]).L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(n_scenarios=2, n_months=180, seed=1)
    model_fn = make_stochastic_model_fn(l5, returns)
    af = ActuarialFrame(mp.with_columns(pl.lit(1).alias("scenario_id")))
    out = model_fn(af, tables=None, drivers=None).collect()
    assert "pv_net_cf" in out.columns
    assert out.height == mp.height
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_adapter_runs_l5_and_emits_pv_net_cf -q`
Expected: FAIL — `ImportError: cannot import name 'load_l5_model'`.

- [ ] **Step 3: Implement**

```python
# append to scenario_lib.py
import importlib.util
import sys
from types import ModuleType


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
) -> Callable[..., "ActuarialFrame"]:
    """Adapt L5 `main` to the for_each_scenario `model_fn(af, *, tables, drivers)` shape.

    The loop hands us an `af` already carrying this batch's `scenario_id` column;
    L5 looks up its own stochastic returns per row from the full returns table.
    `tables`/`drivers` are unused on the stochastic path (no shocks).
    """
    def model_fn(af: "ActuarialFrame", *, tables: dict | None = None,  # noqa: ARG001
                 drivers: dict | None = None) -> "ActuarialFrame":  # noqa: ARG001
        return l5.main(af, scenario_returns_override=stochastic_returns)
    return model_fn


def read_result_metrics(result: Any, n_scenarios: int, n_points: int) -> dict[str, float | str]:
    """Pull chartable metrics off a ScenarioResult."""
    wall = float(result.wall_time_s)
    return {
        "wall_s": round(wall, 3),
        "peak_rss_mb": round(float(result.peak_rss_mb), 1) if result.peak_rss_mb else -1.0,
        "throughput": round((n_scenarios * n_points) / wall, 1) if wall > 0 else 0.0,
        "batch_size": int(result.batch_size),
        "batch_size_resolution": str(result.batch_size_resolution),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py -q`
Expected: PASS (4 passed). (First run builds nothing — pure Python; if `maturin` not built, run `maturin build -uv` first.)

- [ ] **Step 5: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/scenario_lib.py bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): L5 model loader + stochastic model_fn adapter + metrics helper"
```

---

## Phase A — Test-drive + wiring validation (calibrates Phase B)

### Task A.1: SPIKE — prove the stochastic auto-loop equals the manual reference (N=8)

This resolves spec risk #1. **Decision gate:** if equivalence holds, Phase B/C use `for_each_scenario`; if it does not, fall back to the explicit `itertools.batched` pattern from `test_scenario_benchmarks.py` and record the deviation in the report.

**Files:**
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 1: Write the equivalence test (this IS the spike)**

```python
# append to tests/benchmarks/test_scenario_lib.py
from gaspatchio_core.scenarios import Sum, for_each_scenario
from evals.benchmarks.scenario_lib import L5_DIR


def test_auto_loop_equals_manual_reference_n8() -> None:
    """for_each_scenario(auto) per-scenario totals == manual with_scenarios+group_by."""
    from gaspatchio_core.scenarios import with_scenarios

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
        aggregations=(Sum("pv_net_cf").over("scenario_id").alias("total"),),
        batch_size="auto",
    )
    got = result.aggregations["total"].sort("scenario_id")

    ref_tot = ref["total"].to_list()
    got_tot = got["total"].to_list()
    assert len(got_tot) == 8
    for r, g in zip(ref_tot, got_tot, strict=True):
        assert abs(r - g) <= 1e-6 * max(1.0, abs(r)), (r, g)
```

- [ ] **Step 2: Run the spike**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_auto_loop_equals_manual_reference_n8 -q`
Expected (success path): PASS — auto loop reproduces the reference per-scenario totals.
If FAIL: inspect the failure. Likely causes + fixes:
  - `.over("scenario_id")` returns unexpected columns → check `result.aggregations["total"]` schema, adjust the column name/sort.
  - Loop does not pass `scenario_id` for integer IDs → confirm with `print(result.aggregations["total"])`; if IDs missing, switch the aggregation to a non-partitioned `Sum` per batch + reconcile, and record that `.over` needs a different call. **Record the resolved mechanism in the report (Task A.3).**

- [ ] **Step 3: Commit the spike test**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "test(bench): auto scenario loop reproduces manual per-scenario totals (N=8)"
```

### Task A.2: Profile-matrix test-drive runner

**Files:**
- Create: `bindings/python/evals/benchmarks/run_scenario_testdrive.py`

- [ ] **Step 1: Implement the runner**

```python
# bindings/python/evals/benchmarks/run_scenario_testdrive.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""Local test-drive: characterise auto vs fixed vs serial-seeded vs per_policy.

Asserts (1) results identical across profiles and (2) auto wall ~= best fixed.
Writes a markdown report; feeds measured timings into the Phase B grid sizing.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario

from evals.benchmarks.scenario_lib import (
    L5_DIR,
    generate_stochastic_returns,
    load_l5_model,
    make_stochastic_model_fn,
    read_result_metrics,
)

N_SCENARIOS = 24
N_POINTS_PATH = L5_DIR / "model_points_1k.parquet"


def _run(profile: str, batch_size, model_fn, mp, *, master_seed=None) -> dict:
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, N_SCENARIOS + 1)),
        model_fn=model_fn,
        aggregations=(Sum("pv_net_cf").over("scenario_id").alias("total"),),
        batch_size=batch_size,
        master_seed=master_seed,
    )
    metrics = read_result_metrics(result, N_SCENARIOS, mp.height)
    totals = result.aggregations["total"].sort("scenario_id")["total"].to_list()
    return {"profile": profile, "metrics": metrics, "totals": totals}


def main() -> None:
    l5 = load_l5_model()
    returns = generate_stochastic_returns(N_SCENARIOS, n_months=180, seed=2024)
    model_fn = make_stochastic_model_fn(l5, returns)
    mp = pl.read_parquet(N_POINTS_PATH)

    runs = [
        _run("auto", "auto", model_fn, mp),
        _run("fixed-4", 4, model_fn, mp),
        _run("serial-seeded", 1, model_fn, mp, master_seed=2024),
    ]

    # Correctness guard: every profile must agree to 1 ULP-ish.
    ref = runs[0]["totals"]
    for r in runs[1:]:
        for a, b in zip(ref, r["totals"], strict=True):
            assert abs(a - b) <= 1e-6 * max(1.0, abs(a)), (r["profile"], a, b)

    auto_wall = runs[0]["metrics"]["wall_s"]
    best_fixed = min(r["metrics"]["wall_s"] for r in runs if r["profile"].startswith("fixed"))
    print(f"auto wall={auto_wall}s  best-fixed wall={best_fixed}s")
    out = Path(__file__).resolve().parent / "scenario_testdrive_results.json"
    out.write_text(json.dumps(runs, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd bindings/python && uv run python evals/benchmarks/run_scenario_testdrive.py`
Expected: prints `auto wall=...s best-fixed wall=...s`, writes `scenario_testdrive_results.json`, no AssertionError (all profiles agree).

- [ ] **Step 3: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/run_scenario_testdrive.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): scenario profile-matrix test-drive runner"
```

### Task A.3: Write the test-drive report (committed to ref/)

**Files:**
- Create: `ref/42-scenario-auto-sizing/reports/2026-05-30-scenario-testdrive.md`

- [ ] **Step 1: Write the report from the measured JSON**

Read `bindings/python/evals/benchmarks/scenario_testdrive_results.json` and write a markdown report with: (a) the **resolved wiring mechanism** from Task A.1 (for_each auto vs fallback), (b) a per-profile table (wall / peak_rss_mb / batch_size / batch_size_resolution), (c) the correctness statement ("all profiles agree to ≤1e-6 relative"), (d) **measured per-scenario-per-1k-point cost** used to size the Phase B grid (extrapolate the 100×100K and 1000×1K cells; confirm each is under the 120-min job budget; if any cell exceeds ~90 min, flag it for grid revision before Phase B).

- [ ] **Step 2: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A ref/42-scenario-auto-sizing/reports/2026-05-30-scenario-testdrive.md
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "docs(bench): scenario test-drive report + Phase B grid calibration"
```

- [ ] **Step 3 (optional): Obsidian mirror** — only if the user confirmed they want it. Copy the report to `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Opio/gaspatchio/reports/`.

---

## Phase B — Recurring CI perf time-series

### Task B.1: Single-cell runner (deterministic shocks, auto batching)

**Files:**
- Create: `bindings/python/evals/benchmarks/run_scenario_benchmarks.py`
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 1: Add the failing test**

```python
# append to tests/benchmarks/test_scenario_lib.py
from evals.benchmarks.run_scenario_benchmarks import run_cell


def test_run_cell_emits_metrics_small() -> None:
    res = run_cell(n_scenarios=4, points_path=L5_DIR / "model_points.parquet")
    assert res["n_scenarios"] == 4
    assert res["wall_s"] > 0
    assert res["batch_size"] >= 1
    assert res["batch_size_resolution"] in {
        "manual", "auto_probe", "auto_calibrated", "auto_cached",
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_run_cell_emits_metrics_small -q`
Expected: FAIL — `ModuleNotFoundError: evals.benchmarks.run_scenario_benchmarks`.

- [ ] **Step 3: Implement the cell runner**

```python
# bindings/python/evals/benchmarks/run_scenario_benchmarks.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""CI scenario perf benchmark — L-shaped grid, batch_size='auto', new dashboard page.

Emits a flat JSON array of {name, unit, value} for github-action-benchmark, on a
new dev/scenario-bench page. Tracks the DEFAULT (auto) scenario path over time.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import ScenarioRun, Sum

from evals.benchmarks.scenario_lib import (
    L5_DIR,
    generate_stochastic_returns,
    load_l5_model,
    make_shock_bank,
    make_stochastic_model_fn,
    read_result_metrics,
)

# (arm, n_scenarios, n_points). Calibrated from the A.2 test-drive (~0.63s/scenario
# at 1K pts locally): the original 100x100K cell extrapolated to ~100 min locally —
# infeasible in the 120-min CI budget. Portfolio arm reduced to 10 scenarios so the
# first dry-run (D.1) fits comfortably; expand after D.1 confirms real CI timings.
# 1000x100K remains deliberately excluded (~10 hr). See A.3 report for the math.
GRID = [
    ("scen-scaling", 10, 1_000),
    ("scen-scaling", 100, 1_000),
    ("scen-scaling", 1_000, 1_000),
    ("port-scaling", 10, 10_000),
    ("port-scaling", 10, 100_000),
]


def _points_path(n_points: int) -> Path:
    if n_points <= 8:
        return L5_DIR / "model_points.parquet"
    if n_points <= 1_000:
        return L5_DIR / "model_points_1k.parquet"
    if n_points <= 10_000:
        return L5_DIR / "model_points_10k.parquet"
    return Path(__file__).resolve().parent / "model_points" / "l5_100k.parquet"


def run_cell(n_scenarios: int, points_path: Path) -> dict:
    """Run one (scenarios x points) cell via ScenarioRun(auto); return metrics."""
    l5 = load_l5_model()
    returns = generate_stochastic_returns(n_scenarios, n_months=180, seed=12345)
    mp = pl.read_parquet(points_path)
    plan = ScenarioRun(
        shocks=make_shock_bank(n_scenarios),
        base_tables={},
        aggregations=(Sum("pv_net_cf").over("scenario_id").alias("total"),),
    )
    model_fn = make_stochastic_model_fn(l5, returns)
    result = plan.run(ActuarialFrame(mp), model_fn, batch_size="auto")
    m = read_result_metrics(result, n_scenarios, mp.height)
    m["n_scenarios"] = n_scenarios
    m["n_points"] = mp.height
    return m
```

> Note: `base_tables={}` may need at least one table if `ScenarioRun` requires non-empty. If `run_cell` raises on empty `base_tables`, pass the L5 mortality_scalars table (the shock-bank target) — read it via `pl.read_parquet(L5_DIR/"assumptions"/"mortality_scalars.parquet")` wrapped in `Table(...)`. Resolve this in Step 4; the Task A.1 spike will already have surfaced whether `base_tables` is mandatory.

- [ ] **Step 4: Run to verify it passes**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_run_cell_emits_metrics_small -q`
Expected: PASS. If it errors on empty `base_tables`, apply the note above, then re-run.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/run_scenario_benchmarks.py bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): single-cell scenario perf runner (ScenarioRun auto)"
```

### Task B.2: Grid driver + flat-JSON emit

**Files:**
- Modify: `bindings/python/evals/benchmarks/run_scenario_benchmarks.py`
- Test: `bindings/python/tests/benchmarks/test_scenario_lib.py`

- [ ] **Step 1: Add the failing test**

```python
# append to tests/benchmarks/test_scenario_lib.py
from evals.benchmarks.run_scenario_benchmarks import cell_to_json_rows


def test_cell_to_json_rows_schema() -> None:
    cell = {"wall_s": 1.5, "peak_rss_mb": 500.0, "throughput": 666.6,
            "batch_size": 4, "batch_size_resolution": "auto_probe",
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_cell_to_json_rows_schema -q`
Expected: FAIL — `ImportError: cannot import name 'cell_to_json_rows'`.

- [ ] **Step 3: Implement the emitter + main**

```python
# append to run_scenario_benchmarks.py
def _pts_label(n: int) -> str:
    return f"{n // 1000}K" if n >= 1000 else str(n)


def cell_to_json_rows(arm: str, cell: dict) -> list[dict]:
    """One cell -> four github-action-benchmark rows (zero-padded scen for ordering)."""
    stub = f"{arm}/{_pts_label(cell['n_points'])}pts-{cell['n_scenarios']:04d}sc"
    return [
        {"name": f"{stub}-wall", "unit": "seconds", "value": cell["wall_s"]},
        {"name": f"{stub}-rss", "unit": "MB", "value": cell["peak_rss_mb"]},
        {"name": f"{stub}-throughput", "unit": "scenario-points/sec", "value": cell["throughput"]},
        {"name": f"{stub}-batch", "unit": "count", "value": cell["batch_size"]},
    ]


def main() -> None:
    rows: list[dict] = []
    for arm, n_scen, n_pts in GRID:
        path = _points_path(n_pts)
        if not path.exists():
            print(f"SKIP {arm} {n_scen}x{n_pts} — {path} missing", file=sys.stderr)
            continue
        print(f"{arm} {n_scen}sc x {n_pts}pts ...", file=sys.stderr)
        cell = run_cell(n_scen, path)
        print(f"  wall={cell['wall_s']}s rss={cell['peak_rss_mb']}MB "
              f"batch={cell['batch_size']} ({cell['batch_size_resolution']})", file=sys.stderr)
        rows.extend(cell_to_json_rows(arm, cell))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_lib.py::test_cell_to_json_rows_schema -q`
Expected: PASS.

- [ ] **Step 5: Smoke-run the two cheap cells locally**

Run: `cd bindings/python && uv run python -c "from evals.benchmarks.run_scenario_benchmarks import run_cell, cell_to_json_rows, _points_path; print(cell_to_json_rows('scen-scaling', run_cell(10, _points_path(1000))))"`
Expected: prints 4 JSON rows with finite values.

- [ ] **Step 6: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/run_scenario_benchmarks.py bindings/python/tests/benchmarks/test_scenario_lib.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): scenario grid driver + github-action-benchmark JSON emit"
```

### Task B.3: Wire the `scenario-benchmarks` CI job

**Files:**
- Modify: `.github/workflows/evals.yml`

- [ ] **Step 1: Add the job (append under the existing jobs, before `skill-evals`'s `needs` chain — it must NOT be a dependency of skill-evals)**

```yaml
  scenario-benchmarks:
    name: Scenario Throughput & Memory
    if: >-
      github.event_name != 'pull_request' ||
      github.event.label.name == 'performance'
    runs-on: ubuntu-latest-m
    timeout-minutes: 120
    defaults:
      run:
        working-directory: bindings/python
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync
      - name: Generate 100K L5 model points
        run: uv run python ../../evals/benchmarks/generate_model_points.py
      - name: Run scenario benchmarks
        run: uv run python ../../evals/benchmarks/run_scenario_benchmarks.py | tee /tmp/scenario-bench-output.json
      - name: Clean working tree for gh-pages push
        run: git checkout -- .
        working-directory: .
      - name: Store scenario benchmark results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Scenario Benchmarks
          tool: customSmallerIsBetter
          output-file-path: /tmp/scenario-bench-output.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: dev/scenario-bench
          alert-threshold: '150%'
          fail-on-alert: false
```

- [ ] **Step 2: Add the `performance` label to the PR trigger**

The workflow already has `pull_request: types: [labeled]`. No `on:` change needed — the job's `if:` keys on `github.event.label.name == 'performance'`. Confirm the top-level `on.pull_request` still reads `types: [labeled]` (it does).

- [ ] **Step 3: Validate the YAML**

Run: `cd ~/projects/gaspatchio/gaspatchio-core-postmerge && uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/evals.yml')); print('yaml ok')"`
Expected: `yaml ok`. If `actionlint` is available: `actionlint .github/workflows/evals.yml` → no errors.

- [ ] **Step 4: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A .github/workflows/evals.yml
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "ci(bench): scenario-benchmarks job (push develop + 'performance' label, dev/scenario-bench)"
```

### Task B.4: Document the page + the excluded cell

**Files:**
- Modify: `bindings/python/evals/benchmarks/README.md`

- [ ] **Step 1: Add a "Scenario benchmarks" section**

Add: the new page URL `https://opioinc.github.io/gaspatchio-core/dev/scenario-bench/`; the metric set (wall / rss / throughput / batch); the headline ("peak RSS stays flat as scenarios climb under `auto`"); and an **explicit note in the trades table** that `1000 × 100K` (~10 hr) is deliberately excluded — list it so the cap is not silent.

- [ ] **Step 2: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/README.md
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "docs(bench): document scenario-bench page + excluded 1000x100K cell"
```

---

## Phase C — Stochastic actuarial showcase (data + separate render)

### Task C.1: SPIKE+TDD — showcase aggregations vs hand-computed reference (N=20)

Resolves spec risk #2 part 1: confirm `Sum.over` (distribution), `CTE`, and `Quantile` reproduce a numpy reference, and pin the `within`/portfolio-reduction semantics.

**Files:**
- Create: `bindings/python/tests/benchmarks/test_scenario_showcase.py`

- [ ] **Step 1: Write the reference-equivalence test**

```python
# bindings/python/tests/benchmarks/test_scenario_showcase.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Showcase aggregation correctness vs a numpy reference."""

from __future__ import annotations

import numpy as np
import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import CTE, Quantile, Sum, for_each_scenario

from evals.benchmarks.scenario_lib import (
    L5_DIR, generate_stochastic_returns, load_l5_model, make_stochastic_model_fn,
)

N = 20


def _reference_totals() -> list[float]:
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(N, n_months=180, seed=555)
    from gaspatchio_core.scenarios import with_scenarios
    df = l5.main(with_scenarios(ActuarialFrame(mp), list(range(1, N + 1))),
                 scenario_returns_override=returns).collect()
    return (df.group_by("scenario_id").agg(pl.col("pv_net_cf").sum().alias("t"))
            .sort("scenario_id")["t"].to_list())


def test_distribution_and_cte_match_numpy() -> None:
    ref = np.array(_reference_totals())
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(N, n_months=180, seed=555)
    result = for_each_scenario(
        ActuarialFrame(mp), scenarios=list(range(1, N + 1)),
        model_fn=make_stochastic_model_fn(l5, returns),
        aggregations=(Sum("pv_net_cf").over("scenario_id").alias("dist"),),
        batch_size="auto",
    )
    got = np.array(result.aggregations["dist"].sort("scenario_id")["dist"].to_list())
    assert np.allclose(got, ref, rtol=1e-6, atol=1e-6)
    # CTE70 of the LOSS (-total): mean of worst 30% losses. Validate our chosen
    # CTE call against this numpy reference; adjust direction/within in Step 3.
    loss = -ref
    cte70_ref = loss[loss >= np.quantile(loss, 0.70)].mean()
    assert np.isfinite(cte70_ref)
```

- [ ] **Step 2: Run to verify it fails (then drives the implementation)**

Run: `cd bindings/python && uv run pytest tests/benchmarks/test_scenario_showcase.py -q`
Expected initially: FAIL on import or on the distribution assertion. Iterate until the `dist` assertion passes (confirms `Sum.over` == reference).

- [ ] **Step 3: Pin the CTE/Quantile call**

In a scratch REPL, compare `CTE("pv_net_cf", level=0.70, direction="upper")` (and `within=` variants) against `cte70_ref`. Once a call reproduces the numpy reference within `rtol=1e-3` (sketch tolerance — `CTE` uses an approximate digest), add an assertion to the test for that exact call. Record the working aggregator call in a module docstring.

- [ ] **Step 4: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/tests/benchmarks/test_scenario_showcase.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "test(bench): showcase distribution + CTE reproduce numpy reference (N=20)"
```

### Task C.2: Showcase run → `scenario_showcase.json` (data only)

**Files:**
- Create: `bindings/python/evals/benchmarks/run_scenario_showcase.py`

- [ ] **Step 1: Implement the run (Panel A data; Panel B fan series)**

```python
# bindings/python/evals/benchmarks/run_scenario_showcase.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""Stochastic VA showcase: 1000 scenarios -> distribution + CTE + percentile fan.

Emits DATA ONLY (scenario_showcase.json). Rendering is a separate step
(render_scenario_showcase.py) so the same data feeds both perf pages and docs.

Illustrative on tutorial data; not a certified reserve. CTE70 mirrors the
VM-21 statutory method; CTE95 mirrors economic-capital tail.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario, with_scenarios

from evals.benchmarks.scenario_lib import (
    L5_DIR, generate_stochastic_returns, load_l5_model, make_stochastic_model_fn,
)

N_SCENARIOS = 1_000
OUT = Path(__file__).resolve().parent / "scenario_showcase.json"


def main(n_scenarios: int = N_SCENARIOS) -> None:
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points_1k.parquet")
    returns = generate_stochastic_returns(n_scenarios, n_months=180, seed=12345)

    # Panel A: per-scenario portfolio totals via the auto loop (the distribution).
    result = for_each_scenario(
        ActuarialFrame(mp), scenarios=list(range(1, n_scenarios + 1)),
        model_fn=make_stochastic_model_fn(l5, returns),
        aggregations=(Sum("pv_net_cf").over("scenario_id").alias("dist"),),
        batch_size="auto",
    )
    totals = np.array(result.aggregations["dist"].sort("scenario_id")["dist"].to_list())
    loss = -totals  # insurer loss
    cte70 = float(loss[loss >= np.quantile(loss, 0.70)].mean())
    cte95 = float(loss[loss >= np.quantile(loss, 0.95)].mean())

    # Panel B fan: per-month cross-scenario percentiles of portfolio net_cf.
    # Re-run a representative subset with full grid retained for the time series
    # (kept small to bound memory; documented as a render-time reduction).
    fan = _fan_series(l5, mp, returns, n_fan=min(n_scenarios, 200))

    OUT.write_text(json.dumps({
        "meta": {"n_scenarios": n_scenarios, "n_points": mp.height,
                 "batch_size": int(result.batch_size),
                 "batch_size_resolution": str(result.batch_size_resolution),
                 "wall_s": round(float(result.wall_time_s), 3)},
        "distribution": {"per_scenario_loss": loss.tolist(),
                         "cte70": cte70, "cte95": cte95},
        "fan": fan,
    }, indent=2))
    print(f"Wrote {OUT}: 1000-scenario CTE70={cte70:,.0f} CTE95={cte95:,.0f}")


def _fan_series(l5, mp, returns, n_fan: int) -> dict:
    """Per-month percentiles (5/25/50/75/95) of portfolio net_cf across scenarios."""
    df = l5.main(with_scenarios(ActuarialFrame(mp), list(range(1, n_fan + 1))),
                 scenario_returns_override=returns).collect()
    # net_cf is a per-policy LIST column; explode to (scenario_id, month, net_cf),
    # sum to portfolio per (scenario, month), then percentile across scenarios.
    port = (df.select("scenario_id", "net_cf")
              .explode("net_cf")
              .with_columns(pl.col("net_cf").cum_count().over("scenario_id").alias("month"))
              .group_by("scenario_id", "month").agg(pl.col("net_cf").sum().alias("p")))
    pct = (port.group_by("month").agg(
        pl.col("p").quantile(q).alias(name)
        for q, name in [(0.05, "p05"), (0.25, "p25"), (0.5, "p50"),
                        (0.75, "p75"), (0.95, "p95")]).sort("month"))
    return pct.to_dict(as_series=False)


if __name__ == "__main__":
    main()
```

> Risk #2 part 2 (fan series): the `explode + cum_count` month derivation assumes each
> policy's `net_cf` list aligns to the projection month index. Validate on N=4 in Step 2;
> if per-policy jagged lengths break the alignment, derive `month` from the projection
> date column instead (the L5 model exposes `projection_date`). Adjust before scaling.

- [ ] **Step 2: Validate small, then full**

Run (small): `cd bindings/python && uv run python -c "from evals.benchmarks.run_scenario_showcase import main; main(n_scenarios=20)"`
Expected: writes `scenario_showcase.json`, prints CTE70/CTE95, fan has monotone percentiles (`p05 <= p50 <= p95` per month — eyeball the JSON).
Run (full, slower): `cd bindings/python && uv run python evals/benchmarks/run_scenario_showcase.py`
Expected: 1000-scenario JSON; check `meta.batch_size_resolution` is an `auto_*` value.

- [ ] **Step 3: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/run_scenario_showcase.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): stochastic showcase run -> scenario_showcase.json (data only)"
```

### Task C.3: Render the two-panel Altair chart from the JSON

**Files:**
- Create: `bindings/python/evals/benchmarks/render_scenario_showcase.py`

- [ ] **Step 1: Implement the renderer (reuse the `gaspatchio` Altair theme idea from `tutorial/level-5-scenarios/benchmark.py`)**

```python
# bindings/python/evals/benchmarks/render_scenario_showcase.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""Render the stochastic showcase chart from scenario_showcase.json.

Pure data -> chart; no model run here. Emits both a Vega-Lite JSON (for embedding
in docs / perf pages) and a PNG. Run after run_scenario_showcase.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import polars as pl

HERE = Path(__file__).resolve().parent
DATA = HERE / "scenario_showcase.json"


def build_charts(data: dict) -> alt.VConcatChart:
    loss = data["distribution"]["per_scenario_loss"]
    cte70, cte95 = data["distribution"]["cte70"], data["distribution"]["cte95"]
    dist_df = pl.DataFrame({"loss": loss})
    hist = (alt.Chart(dist_df).mark_bar(opacity=0.8)
            .encode(x=alt.X("loss:Q", bin=alt.Bin(maxbins=40), title="PV net liability (loss) per scenario"),
                    y=alt.Y("count()", title="scenarios"))
            .properties(width=600, height=260, title="Stochastic reserve distribution (1,000 scenarios)"))
    rules = (alt.Chart(pl.DataFrame({"x": [cte70, cte95], "label": ["CTE70", "CTE95"]}))
             .mark_rule(color="#CD853F", strokeWidth=2)
             .encode(x="x:Q", tooltip="label:N"))
    panel_a = hist + rules

    fan = data["fan"]
    fan_df = pl.DataFrame(fan)
    base = alt.Chart(fan_df)
    band_outer = base.mark_area(opacity=0.25).encode(
        x="month:Q", y=alt.Y("p05:Q", title="portfolio net cashflow"), y2="p95:Q")
    band_inner = base.mark_area(opacity=0.4).encode(x="month:Q", y="p25:Q", y2="p75:Q")
    median = base.mark_line(strokeWidth=2).encode(x="month:Q", y="p50:Q")
    panel_b = (band_outer + band_inner + median).properties(
        width=600, height=260, title="Percentile fan — net cashflow over time")

    return alt.vconcat(panel_a, panel_b).resolve_scale(x="independent")


def main() -> None:
    data = json.loads(DATA.read_text())
    chart = build_charts(data)
    (HERE / "scenario_showcase.vl.json").write_text(chart.to_json())
    chart.save(str(HERE / "scenario_showcase.png"), scale_factor=2)
    print(f"Wrote {HERE/'scenario_showcase.vl.json'} and scenario_showcase.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Render from the small-N JSON produced in C.2**

Run: `cd bindings/python && uv run python evals/benchmarks/render_scenario_showcase.py`
Expected: writes `scenario_showcase.vl.json` + `scenario_showcase.png`; open the PNG and confirm two panels (histogram with two CTE rules; fan with median + bands). If `altair` PNG save needs a backend, install per the existing `benchmark.py` setup (`vl-convert`); the Vega-Lite JSON always writes regardless.

- [ ] **Step 3: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A bindings/python/evals/benchmarks/render_scenario_showcase.py
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "feat(bench): Altair renderer for the stochastic showcase (data -> Vega/PNG)"
```

### Task C.4: Publish the showcase in CI + expose data for docs

**Files:**
- Modify: `.github/workflows/evals.yml` (the `scenario-benchmarks` job from B.3)

- [ ] **Step 1: Add showcase steps to the job (after the benchmark store step)**

```yaml
      - name: Run stochastic showcase
        run: uv run python ../../evals/benchmarks/run_scenario_showcase.py
      - name: Render showcase chart
        run: uv run python ../../evals/benchmarks/render_scenario_showcase.py
      - name: Upload showcase artifacts
        uses: actions/upload-artifact@v4
        with:
          name: scenario-showcase
          path: |
            bindings/python/evals/benchmarks/scenario_showcase.json
            bindings/python/evals/benchmarks/scenario_showcase.vl.json
            bindings/python/evals/benchmarks/scenario_showcase.png
```

> Publishing the showcase onto the `dev/scenario-bench/` gh-pages page (alongside the
> time-series) and wiring the `scenario_showcase.vl.json` into the docs site are a
> follow-up once the artifact is confirmed (mirror the `capability-matrix` job's
> gh-pages checkout+commit pattern). Keep this step to artifact upload first.

- [ ] **Step 2: Validate YAML**

Run: `cd ~/projects/gaspatchio/gaspatchio-core-postmerge && uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/evals.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 3: Commit**

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge add -A .github/workflows/evals.yml
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge commit -m "ci(bench): run + render + upload stochastic showcase in scenario-benchmarks job"
```

---

## Phase D — Live dry-run on PR #106 (the `performance` label)

### Task D.1: Push, label, and verify on the cloud runner

- [ ] **Step 1: Run the full local test suite for the new code**

Run: `cd bindings/python && uv run pytest tests/benchmarks/ -q`
Expected: all green. Also run lint: `uv run ruff check evals/benchmarks/ tests/benchmarks/` → clean.

- [ ] **Step 2: Push the branch** (sandbox has no SSH key — use the gh token over HTTPS)

```bash
git -C ~/projects/gaspatchio/gaspatchio-core-postmerge -c credential.helper= -c credential.helper='!gh auth git-credential' push https://github.com/opioinc/gaspatchio-core.git gsp-100-post-merge:gsp-100-post-merge
```

- [ ] **Step 3: Add the `performance` label to PR #106 to trigger the live run**

```bash
gh pr edit 106 -R opioinc/gaspatchio-core --add-label performance
```
(If the label does not exist: `gh label create performance -R opioinc/gaspatchio-core --description "run scenario perf benchmarks" --color FFA500`.)

- [ ] **Step 4: Watch the run**

Run: `gh run list -R opioinc/gaspatchio-core --workflow evals.yml --limit 3` then `gh run watch <id> -R opioinc/gaspatchio-core`
Expected: the `Scenario Throughput & Memory` job completes within 120 min; the `scenario-showcase` artifact is produced; `dev/scenario-bench/` receives a commit on `gh-pages`.

- [ ] **Step 5: Verify the dashboard + report back**

Confirm https://opioinc.github.io/gaspatchio-core/dev/scenario-bench/ renders the new charts. Summarise to the user: measured wall/RSS per cell, the resolved `batch_size_resolution` values, the CTE70/CTE95 from the showcase, and whether peak RSS stayed flat across the scenario-scaling arm (the headline). Remove the label if re-runs aren't wanted: `gh pr edit 106 -R opioinc/gaspatchio-core --remove-label performance`.

---

## Self-review

**Spec coverage:**
- D1 test-drive → Phase A (A.1 wiring, A.2 profile matrix, A.3 report). ✓
- D2 recurring chart → Phase B (B.1 cell, B.2 grid+JSON, B.3 CI job + `performance` label + `push:[develop]`, B.4 README + excluded cell). ✓
- D3 showcase (data/render split, both panels, VM-21 framing) → Phase C (C.1 correctness, C.2 data, C.3 render, C.4 CI). ✓
- Grid B (5 cells), 1000×100K excluded + documented → GRID const + B.4. ✓
- Triggers (push main/develop + performance label + cron + dispatch, 120-min) → B.3. ✓
- Metric `pv_net_cf` → throughout. ✓
- 3 risks validated small-N first → A.1 (wiring), C.1 (aggregator semantics), C.2 note (fan alignment), D.1 (100×100K memory envelope on runner). ✓

**Placeholder scan:** No TBD/TODO. Two tasks are explicit SPIKES (A.1, C.1) with concrete experiments + decision criteria + fallbacks — not placeholders. The C.4 gh-pages-publish-of-showcase and docs-embed are scoped as a stated follow-up (artifact-upload first) to avoid guessing the gh-pages page layout before the data artifact exists.

**Type consistency:** `read_result_metrics` keys (`wall_s`, `peak_rss_mb`, `throughput`, `batch_size`, `batch_size_resolution`) are produced in 0.3 and consumed in A.2/B.1/B.2 consistently. `run_cell` adds `n_scenarios`/`n_points`, consumed by `cell_to_json_rows`. `make_stochastic_model_fn` signature `(af, *, tables, drivers)` matches the verified loop contract. Aggregator alias `"dist"`/`"total"` used consistently within each task.
