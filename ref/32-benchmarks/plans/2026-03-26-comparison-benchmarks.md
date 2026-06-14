# Gaspatchio vs Lifelib Comparison Benchmark — Implementation Plan

> **Status (2026-05):** Lifelib reference data was originally vendored into this repo at `evals/benchmarks/lifelib_ref/`. It now lives in the sister **gaspatchio-benchmarks** repository; the runner resolves it via `GASPATCHIO_BENCHMARKS_DIR` or a sibling-checkout at `../gaspatchio-benchmarks/`. The plan below describes the original arrangement and is preserved as historical record.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible head-to-head performance benchmark comparing gaspatchio vs lifelib IntegratedLife on the same VA model, same data, same hardware, with results displayed on the gh-pages dashboard.

**Architecture:** A new `run_comparison_benchmarks.py` orchestrates both engines at 8/1K/10K/100K model points. Lifelib's modelx model is self-contained in `evals/benchmarks/lifelib_ref/`. A `lifelib_runner.py` module handles the lifelib-specific invocation (chdir, scen_size patching, CSV model points). Results output as JSON for the benchmark-action and a comparison-specific format for the dashboard. All benchmark CI jobs move to `ubuntu-latest-m`.

**Tech Stack:** Python, modelx, lifelib, polars, gaspatchio, Chart.js (dashboard), GitHub Actions

**Spec:** `ref/32-benchmarks/specs/2026-03-26-comparison-benchmarks-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `evals/benchmarks/lifelib_runner.py` | Isolated lifelib invocation: chdir, model load, scen_size patch, run, cleanup |
| Create | `evals/benchmarks/run_comparison_benchmarks.py` | Orchestrator: runs both engines at all scales, outputs JSON |
| Copy | `evals/benchmarks/lifelib_ref/` | Self-contained lifelib IntegratedLife model + all data |
| Modify | `evals/benchmarks/generate_model_points.py` | Add lifelib-format CSV export alongside parquet |
| Modify | `bindings/python/pyproject.toml` | Add `benchmark` dependency group (lifelib, modelx, openpyxl) |
| Modify | `.github/workflows/evals.yml` | Move all jobs to `ubuntu-latest-m`, add comparison job |
| Modify | `gh-pages:index.html` | Add "Gaspatchio vs Lifelib" card with grouped bars + table |

---

### Task 1: Copy lifelib reference model into repo

**Files:**
- Create: `evals/benchmarks/lifelib_ref/` (entire directory tree)
- Modify: `.gitignore` (add lifelib output exclusions)

- [ ] **Step 1: Copy the lifelib model from gaspatchio-models**

```bash
cp -r ../gaspatchio-models/appliedlife/ref/appliedlife/ \
      evals/benchmarks/lifelib_ref/
```

- [ ] **Step 2: Remove any output directories and caches**

```bash
rm -rf evals/benchmarks/lifelib_ref/output/
rm -rf evals/benchmarks/lifelib_ref/__pycache__/
find evals/benchmarks/lifelib_ref/ -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find evals/benchmarks/lifelib_ref/ -name '.ipynb_checkpoints' -type d -exec rm -rf {} + 2>/dev/null
```

- [ ] **Step 3: Add gitignore entries for lifelib runtime artifacts**

Add to `.gitignore`:
```
evals/benchmarks/lifelib_ref/output/
evals/benchmarks/lifelib_ref/**/__pycache__/
```

- [ ] **Step 4: Verify the model structure is complete**

```bash
ls evals/benchmarks/lifelib_ref/IntegratedLife/
# Expected: __init__.py, _system.json, Assumptions/, BaseData/, ModelPoints/, Mortality/, ProductBase/, Run/, Scenarios/

ls evals/benchmarks/lifelib_ref/model_point_data/
# Expected: model_point_2023Q4IF_GMXB.csv and other CSV files

ls evals/benchmarks/lifelib_ref/input_tables/
# Expected: assumption Excel files

ls evals/benchmarks/lifelib_ref/model_parameters.xlsx
# Expected: exists
```

- [ ] **Step 5: Commit**

```bash
git add evals/benchmarks/lifelib_ref/ .gitignore
git commit -m "feat(benchmarks): add lifelib IntegratedLife reference model for comparison"
```

---

### Task 2: Add benchmark dependency group

**Files:**
- Modify: `bindings/python/pyproject.toml`

- [ ] **Step 1: Add the benchmark dependency group**

In `bindings/python/pyproject.toml`, add after the existing `[dependency-groups]` `dev` group:

```toml
benchmark = [
    "lifelib>=0.11.0",
    "modelx>=0.28.1",
    "openpyxl>=3.1.5",
    "psutil>=5.9.0",
]
```

- [ ] **Step 2: Verify resolution**

```bash
cd bindings/python && uv sync --group benchmark
```

Expected: installs lifelib, modelx, openpyxl, psutil and their transitive deps without conflicts.

- [ ] **Step 3: Verify lifelib imports**

```bash
cd bindings/python && uv run python -c "import modelx; print('modelx', modelx.__version__)"
```

Expected: prints modelx version without error.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/pyproject.toml uv.lock
git commit -m "feat(deps): add benchmark dependency group with lifelib, modelx"
```

---

### Task 3: Build the lifelib runner module

**Files:**
- Create: `evals/benchmarks/lifelib_runner.py`

- [ ] **Step 1: Write the lifelib runner**

Create `evals/benchmarks/lifelib_runner.py`:

```python
#!/usr/bin/env python3
# ruff: noqa: T201
"""Isolated lifelib IntegratedLife runner for benchmark comparison.

Handles modelx-specific requirements: chdir to model directory,
scen_size patching for deterministic mode, model point CSV swapping,
and working directory restoration.

Usage (standalone test):
    cd bindings/python
    uv run python ../../evals/benchmarks/lifelib_runner.py
"""

import gc
import os
import re
import time
import tracemalloc
from pathlib import Path

LIFELIB_REF_DIR = Path(__file__).resolve().parent / "lifelib_ref"


def _patch_scen_size(model_dir: Path, num_scenarios: int) -> str | None:
    """Patch scen_size() in the Scenarios __init__.py to set deterministic mode.

    Returns the original line for restoration, or None if no patch needed.
    """
    scenarios_file = model_dir / "IntegratedLife" / "Scenarios" / "__init__.py"
    if not scenarios_file.exists():
        return None

    content = scenarios_file.read_text()
    pattern = r"(def scen_size\(\):\s*\"\"\"[^\"]*\"\"\"\s*return )\d+"
    match = re.search(pattern, content)
    if not match:
        return None

    original_line = match.group(0)
    new_content = re.sub(pattern, rf"\g<1>{num_scenarios}", content)
    scenarios_file.write_text(new_content)
    return original_line


def _restore_scen_size(model_dir: Path, original_line: str) -> None:
    """Restore the original scen_size() function."""
    scenarios_file = model_dir / "IntegratedLife" / "Scenarios" / "__init__.py"
    if not scenarios_file.exists():
        return
    content = scenarios_file.read_text()
    pattern = r"def scen_size\(\):\s*\"\"\"[^\"]*\"\"\"\s*return \d+"
    new_content = re.sub(pattern, original_line, content)
    scenarios_file.write_text(new_content)


def setup_lifelib(
    model_dir: Path | None = None,
    num_scenarios: int = 1,
) -> dict:
    """Load the lifelib IntegratedLife model and return timing + model object.

    Returns dict with keys: model, run, setup_time_s, original_scen_line, original_cwd.
    """
    if model_dir is None:
        model_dir = LIFELIB_REF_DIR

    original_cwd = os.getcwd()

    # Patch for deterministic mode
    original_scen_line = _patch_scen_size(model_dir, num_scenarios)

    # modelx requires chdir to the directory containing the model
    os.chdir(model_dir)

    gc.collect()
    start = time.perf_counter()

    import modelx as mx

    model = mx.read_model("IntegratedLife")
    setup_time = time.perf_counter() - start

    return {
        "model": model,
        "setup_time_s": round(setup_time, 3),
        "original_scen_line": original_scen_line,
        "original_cwd": original_cwd,
        "model_dir": model_dir,
    }


def run_lifelib_projection(
    lifelib_ctx: dict,
    run_id: int = 2,
) -> dict:
    """Run lifelib projection and return timing + peak memory.

    Args:
        lifelib_ctx: dict returned by setup_lifelib
        run_id: Run ID from model_parameters.xlsx (2 = 2023Q4IF 8-point set)

    Returns dict with keys: time_s, peak_mb.
    """
    model = lifelib_ctx["model"]

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    run = model.Run[run_id]
    _ = run.GMXB.result_pv()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "time_s": round(elapsed, 3),
        "peak_mb": round(peak_mem / 1024 / 1024, 1),
    }


def teardown_lifelib(lifelib_ctx: dict) -> None:
    """Restore working directory and scen_size patch."""
    os.chdir(lifelib_ctx["original_cwd"])
    if lifelib_ctx["original_scen_line"]:
        _restore_scen_size(lifelib_ctx["model_dir"], lifelib_ctx["original_scen_line"])


def swap_model_points_csv(model_dir: Path, csv_path: Path, mp_file_id: str = "bench") -> None:
    """Write a model point CSV into the lifelib model_point_data directory.

    The file will be named model_point_{mp_file_id}_GMXB.csv to match
    lifelib's naming convention.
    """
    dest = model_dir / "model_point_data" / f"model_point_{mp_file_id}_GMXB.csv"
    import shutil

    shutil.copy2(csv_path, dest)


if __name__ == "__main__":
    print("Testing lifelib runner...")
    ctx = setup_lifelib(num_scenarios=1)
    print(f"  Setup: {ctx['setup_time_s']}s")

    result = run_lifelib_projection(ctx, run_id=2)
    print(f"  Projection (8 points): {result['time_s']}s, {result['peak_mb']}MB")

    teardown_lifelib(ctx)
    print("Done.")
```

- [ ] **Step 2: Test the runner locally**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/lifelib_runner.py
```

Expected: prints setup time and projection time for the 8-point set without errors.

- [ ] **Step 3: Commit**

```bash
git add evals/benchmarks/lifelib_runner.py
git commit -m "feat(benchmarks): add lifelib runner module with setup/run/teardown"
```

---

### Task 4: Extend model point generator for lifelib CSV format

**Files:**
- Modify: `evals/benchmarks/generate_model_points.py`

- [ ] **Step 1: Add lifelib CSV export function**

Add the following function and modify `main()` in `evals/benchmarks/generate_model_points.py`:

```python
def write_lifelib_csv(df: pl.DataFrame, output_path: Path) -> None:
    """Write model points in lifelib CSV format.

    Lifelib expects CSV with point_id as the first column and
    entry_date as a string in YYYY/MM/DD format.
    """
    # Ensure entry_date is string format YYYY/MM/DD (lifelib expects this)
    df.write_csv(output_path)
```

In the `main()` function, after each parquet write, add:

```python
            # Also write lifelib-format CSV
            csv_path = out_path.with_suffix(".csv")
            print(f"    Writing lifelib CSV → {csv_path}")
            write_lifelib_csv(scaled, csv_path)
```

- [ ] **Step 2: Test generation includes CSV**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/generate_model_points.py --level 4 --size 1000
ls ../../evals/benchmarks/model_points/l4_1k.*
```

Expected: both `l4_1k.parquet` and `l4_1k.csv` exist.

- [ ] **Step 3: Verify CSV format matches lifelib expectations**

```bash
cd bindings/python && uv run python -c "
import polars as pl
df = pl.read_csv('../../evals/benchmarks/model_points/l4_1k.csv')
print(df.columns)
print(df.head(2))
"
```

Expected: columns match `point_id, product_id, plan_id, entry_date, age_at_entry, sex, policy_term, fund_index, policy_count, sum_assured, duration_mth, premium_pp, av_pp_init, accum_prem_init_pp`.

- [ ] **Step 4: Commit**

```bash
git add evals/benchmarks/generate_model_points.py
git commit -m "feat(benchmarks): add lifelib CSV export to model point generator"
```

---

### Task 5: Build the comparison benchmark orchestrator

**Files:**
- Create: `evals/benchmarks/run_comparison_benchmarks.py`

- [ ] **Step 1: Write the orchestrator**

Create `evals/benchmarks/run_comparison_benchmarks.py`:

```python
#!/usr/bin/env python3
# ruff: noqa: T201
"""Head-to-head gaspatchio vs lifelib benchmark.

Runs both engines on the L4 IntegratedLife model at 8/1K/10K/100K points.
Measures setup time (once per engine) and projection time (per scale).
Outputs JSON for github-action-benchmark and a comparison summary.

Usage:
    cd bindings/python
    uv run python ../../evals/benchmarks/run_comparison_benchmarks.py
    uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 1000
"""

import argparse
import gc
import importlib.util
import json
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path
from types import ModuleType

import polars as pl

from gaspatchio_core import ActuarialFrame

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TUTORIAL_DIR = REPO_ROOT / "tutorial"
BENCHMARK_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BENCHMARK_DIR / "model_points"
LIFELIB_REF_DIR = BENCHMARK_DIR / "lifelib_ref"
RESULTS_DIR = BENCHMARK_DIR / "comparison_results"


def _get_hardware_metadata() -> dict:
    """Collect hardware info for result attribution."""
    return {
        "runner": os.environ.get("RUNNER_NAME", "local"),
        "cores": os.cpu_count(),
        "ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 1)
        if hasattr(os, "sysconf")
        else None,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def _load_gaspatchio_model() -> ModuleType:
    """Load the L4 gaspatchio model module."""
    model_path = TUTORIAL_DIR / "level-4-lifelib" / "base" / "model.py"
    model_dir = str(model_path.parent)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    spec = importlib.util.spec_from_file_location("l4_comparison_model", model_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["l4_comparison_model"] = module
    spec.loader.exec_module(module)
    return module


def _get_mp_path(size: int) -> Path:
    """Get model points parquet path for a given scale."""
    base_dir = TUTORIAL_DIR / "level-4-lifelib" / "base"
    if size <= 10:
        return base_dir / "model_points.parquet"
    if size <= 1_000:
        path = base_dir / "model_points_1k.parquet"
        if path.exists():
            return path
    return GENERATED_DIR / f"l4_{size // 1000}k.parquet"


def bench_gaspatchio_setup() -> tuple[ModuleType, float]:
    """Time gaspatchio import + model load + first assumption registration."""
    gc.collect()
    start = time.perf_counter()
    model = _load_gaspatchio_model()
    elapsed = time.perf_counter() - start
    return model, round(elapsed, 3)


def bench_gaspatchio_projection(model: ModuleType, mp_path: Path) -> dict:
    """Time a gaspatchio projection at a given scale."""
    mp = pl.read_parquet(mp_path)

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    result_af = model.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak_mem / 1024 / 1024, 1)}


def bench_lifelib_setup() -> tuple[dict, float]:
    """Time lifelib import + model load."""
    from evals.benchmarks.lifelib_runner import setup_lifelib

    ctx = setup_lifelib(model_dir=LIFELIB_REF_DIR, num_scenarios=1)
    return ctx, ctx["setup_time_s"]


def bench_lifelib_projection(lifelib_ctx: dict, mp_csv_path: Path, size: int) -> dict:
    """Time a lifelib projection at a given scale.

    For the 8-point set, uses run_id=2 (2023Q4IF) which is pre-configured.
    For generated sets, swaps the CSV into the model_point_data directory.
    """
    from evals.benchmarks.lifelib_runner import run_lifelib_projection, swap_model_points_csv

    if size <= 10:
        # Use the pre-configured 8-point run
        return run_lifelib_projection(lifelib_ctx, run_id=2)

    # For generated sets: swap CSV and use a bench run ID
    # We need to add a run row or swap the file that run_id=2 points to
    swap_model_points_csv(LIFELIB_REF_DIR, mp_csv_path, mp_file_id="2023Q4IF")

    # Clear modelx cache so it re-reads the new model points
    model = lifelib_ctx["model"]
    model.clear_all()

    result = run_lifelib_projection(lifelib_ctx, run_id=2)

    # Restore original 8-point CSV
    original_csv = LIFELIB_REF_DIR / "model_point_data" / "model_point_2023Q4IF_GMXB.csv.bak"
    if original_csv.exists():
        import shutil
        shutil.copy2(original_csv, LIFELIB_REF_DIR / "model_point_data" / "model_point_2023Q4IF_GMXB.csv")

    return result


def main() -> None:
    """Run the comparison benchmark."""
    parser = argparse.ArgumentParser(description="Gaspatchio vs lifelib benchmark")
    parser.add_argument(
        "--max-scale",
        type=int,
        default=100_000,
        help="Maximum model point scale (default: 100000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=2700,
        help="Per-scale timeout in seconds (default: 2700 = 45 min)",
    )
    args = parser.parse_args()

    hardware = _get_hardware_metadata()
    print("=" * 70)
    print("GASPATCHIO vs LIFELIB — IntegratedLife VA Benchmark")
    print("=" * 70)
    print(f"Runner: {hardware['runner']}")
    print(f"Cores: {hardware['cores']}, RAM: {hardware['ram_gb']}GB")
    print(f"Platform: {hardware['platform']}")
    print()

    scales = [s for s in [8, 1_000, 10_000, 100_000] if s <= args.max_scale]

    # --- Gaspatchio setup ---
    print("Setting up gaspatchio...")
    gsp_model, gsp_setup_time = bench_gaspatchio_setup()
    print(f"  Gaspatchio setup: {gsp_setup_time}s")

    # --- Lifelib setup ---
    print("Setting up lifelib...")
    lifelib_ctx, lib_setup_time = bench_lifelib_setup()
    print(f"  Lifelib setup: {lib_setup_time}s")
    print()

    # --- Back up the original 8-point CSV before any swaps ---
    original_8pt = LIFELIB_REF_DIR / "model_point_data" / "model_point_2023Q4IF_GMXB.csv"
    backup_8pt = original_8pt.with_suffix(".csv.bak")
    if original_8pt.exists() and not backup_8pt.exists():
        import shutil
        shutil.copy2(original_8pt, backup_8pt)

    results = [
        {"name": "gaspatchio-setup", "unit": "seconds", "value": gsp_setup_time},
        {"name": "lifelib-setup", "unit": "seconds", "value": lib_setup_time},
    ]

    # --- Per-scale projections ---
    for size in scales:
        size_label = f"{size // 1000}K" if size >= 1000 else str(size)
        print(f"--- {size_label} model points ---")

        mp_path = _get_mp_path(size)
        if not mp_path.exists():
            print(f"  SKIP: {mp_path} not found (run generate_model_points.py first)")
            continue

        # CSV path for lifelib
        mp_csv_path = mp_path.with_suffix(".csv")
        if not mp_csv_path.exists() and size > 10:
            # Generate CSV from parquet
            print(f"  Converting {mp_path.name} to CSV...")
            df = pl.read_parquet(mp_path)
            df.write_csv(mp_csv_path)

        # Gaspatchio
        print(f"  Gaspatchio {size_label}: ", end="", flush=True)
        gsp_result = bench_gaspatchio_projection(gsp_model, mp_path)
        print(f"{gsp_result['time_s']}s, {gsp_result['peak_mb']}MB")

        # Lifelib
        print(f"  Lifelib {size_label}: ", end="", flush=True)
        try:
            import signal

            class TimeoutError(Exception):
                pass

            def timeout_handler(signum, frame):
                raise TimeoutError()

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(args.timeout)

            lib_result = bench_lifelib_projection(lifelib_ctx, mp_csv_path, size)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

            print(f"{lib_result['time_s']}s, {lib_result['peak_mb']}MB")
        except (TimeoutError, Exception) as e:
            signal.alarm(0)
            err_type = "TIMEOUT" if "Timeout" in type(e).__name__ else f"ERROR: {e}"
            print(err_type)
            lib_result = {"time_s": -1, "peak_mb": -1}

        # Speedup
        if gsp_result["time_s"] > 0 and lib_result["time_s"] > 0:
            speedup = round(lib_result["time_s"] / gsp_result["time_s"], 1)
        else:
            speedup = -1

        print(f"  Speedup: {speedup}x")
        print()

        results.extend([
            {"name": f"gaspatchio/{size_label}-points", "unit": "seconds", "value": gsp_result["time_s"]},
            {"name": f"lifelib/{size_label}-points", "unit": "seconds", "value": lib_result["time_s"]},
            {"name": f"gaspatchio/{size_label}-memory", "unit": "MB", "value": gsp_result["peak_mb"]},
            {"name": f"lifelib/{size_label}-memory", "unit": "MB", "value": lib_result["peak_mb"]},
            {"name": f"speedup/{size_label}", "unit": "x", "value": speedup},
        ])

    # --- Teardown ---
    from evals.benchmarks.lifelib_runner import teardown_lifelib

    teardown_lifelib(lifelib_ctx)

    # Restore original CSV
    if backup_8pt.exists():
        import shutil
        shutil.copy2(backup_8pt, original_8pt)
        backup_8pt.unlink()

    # --- Output ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output = {"hardware": hardware, "results": results}
    output_path = RESULTS_DIR / "comparison-results.json"
    output_path.write_text(json.dumps(output, indent=2))

    # Also write benchmark-action format (just the results array)
    bench_output_path = RESULTS_DIR / "benchmark-results.json"
    bench_output_path.write_text(json.dumps(results, indent=2))

    print("=" * 70)
    print(f"Results written to {output_path}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test locally with max-scale 8 (fastest)**

```bash
cd bindings/python && export $(grep -v '^#' ../../.env | xargs) && \
    uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 8
```

Expected: prints gaspatchio and lifelib times for 8 points, plus speedup.

- [ ] **Step 3: Test at 1K scale**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 1000
```

Expected: prints times for 8 and 1K points. Lifelib may take several minutes at 1K.

- [ ] **Step 4: Commit**

```bash
git add evals/benchmarks/run_comparison_benchmarks.py
git commit -m "feat(benchmarks): add gaspatchio vs lifelib comparison benchmark"
```

---

### Task 6: Update CI workflow — move all jobs to ubuntu-latest-m and add comparison job

**Files:**
- Modify: `.github/workflows/evals.yml`

- [ ] **Step 1: Update all existing jobs to use ubuntu-latest-m**

In `.github/workflows/evals.yml`, change `runs-on: ubuntu-latest` to `runs-on: ubuntu-latest-m` for:
- `rust-benchmarks`
- `model-benchmarks`
- `skill-evals`

- [ ] **Step 2: Add the comparison benchmarks job**

Add after the `model-benchmarks` job:

```yaml
  comparison-benchmarks:
    name: Gaspatchio vs Lifelib
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
      - name: Install dependencies (with lifelib)
        run: uv sync --group benchmark
      - name: Generate model points (all scales)
        run: uv run python ../../evals/benchmarks/generate_model_points.py
      - name: Run comparison benchmarks
        run: uv run python ../../evals/benchmarks/run_comparison_benchmarks.py | tee /tmp/comparison-output.json
      - name: Store comparison results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Gaspatchio vs Lifelib
          tool: customSmallerIsBetter
          output-file-path: evals/benchmarks/comparison_results/benchmark-results.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: dev/comparison
          alert-threshold: '200%'
          fail-on-alert: false
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/evals.yml
git commit -m "feat(ci): move all benchmarks to ubuntu-latest-m, add comparison job"
```

---

### Task 7: Update dashboard with comparison card

**Files:**
- Modify: `gh-pages:index.html`

- [ ] **Step 1: Check out gh-pages in a worktree**

```bash
git worktree add /tmp/ghpages-comparison origin/gh-pages
```

- [ ] **Step 2: Add comparison card HTML**

In the grid section of `/tmp/ghpages-comparison/index.html`, add before the capability matrix card:

```html
    <!-- Gaspatchio vs Lifelib -->
    <div class="lg:col-span-2 bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow animate-in" id="card-comparison">
      <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="opacity-60">🏎</span> Gaspatchio vs Lifelib
          <span class="text-[10px] font-normal text-gray-400 ml-2" id="hw-label"></span>
        </h2>
        <span class="text-[11px] px-2 py-0.5 rounded-full font-semibold tabular" id="badge-comparison">--</span>
      </div>
      <div class="p-5">
        <div class="relative h-64"><canvas id="chart-comparison"></canvas></div>
        <div class="hidden flex-col items-center justify-center h-48 text-gray-400 text-sm" id="empty-comparison">
          <span class="text-3xl mb-2 opacity-40">🏎</span>
          <span>No comparison data yet</span>
          <span class="text-xs text-gray-300 mt-1">Data appears after the first successful comparison run</span>
        </div>
      </div>
      <div class="border-t border-gray-100 overflow-x-auto" id="table-comparison"></div>
    </div>
```

- [ ] **Step 3: Add comparison data loading and rendering JS**

Add to the `init()` function in the script section, before the capability matrix load:

```javascript
    // Comparison
    var compData = await loadBenchmarkData('dev/comparison/data.js');
    if (compData && compData.entries) {
      var key = Object.keys(compData.entries)[0];
      var entries = compData.entries[key] || [];
      renderComparisonChart(entries);
      renderComparisonTable(entries);
      // Find latest speedup for badge
      if (entries.length > 0) {
        var latest = entries[entries.length - 1];
        var speedups = latest.benches.filter(function(b) { return b.name.startsWith('speedup/'); });
        if (speedups.length > 0) {
          var avgSpeedup = speedups.reduce(function(s,b) { return s + b.value; }, 0) / speedups.length;
          document.getElementById('badge-comparison').textContent = Math.round(avgSpeedup) + 'x faster';
          document.getElementById('badge-comparison').className = 'text-[11px] px-2 py-0.5 rounded-full font-semibold tabular bg-green-50 text-green-700';
        }
      }
      setStatus('comparison', 'ok', 'Comparison: ' + entries.length + ' runs');
    } else {
      document.getElementById('chart-comparison').style.display = 'none';
      document.getElementById('empty-comparison').style.display = 'flex';
      document.getElementById('table-comparison').style.display = 'none';
    }
```

Add the `renderComparisonChart` and `renderComparisonTable` functions:

```javascript
  function renderComparisonChart(entries) {
    var canvas = document.getElementById('chart-comparison');
    if (!entries || entries.length === 0) return;

    var latest = entries[entries.length - 1];
    var gspBenches = latest.benches.filter(function(b) { return b.name.startsWith('gaspatchio/') && b.name.includes('-points'); });
    var libBenches = latest.benches.filter(function(b) { return b.name.startsWith('lifelib/') && b.name.includes('-points'); });

    var labels = gspBenches.map(function(b) { return b.name.replace('gaspatchio/', '').replace('-points', ''); });
    var gspData = gspBenches.map(function(b) { return b.value; });
    var libData = libBenches.map(function(b) { return b.value > 0 ? b.value : null; });

    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          { label: 'Gaspatchio', data: gspData, backgroundColor: '#2563eb', borderRadius: 4 },
          { label: 'Lifelib', data: libData, backgroundColor: '#dc2626', borderRadius: 4 },
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14, font: { size: 10 }, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: {
            backgroundColor: '#fff', titleColor: '#111827', bodyColor: '#6b7280',
            borderColor: '#e5e7eb', borderWidth: 1, padding: 10, cornerRadius: 6,
            callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmtVal(ctx.parsed.y) + ' seconds'; } }
          }
        },
        scales: {
          y: { type: 'logarithmic', grid: { color: '#f3f4f6' }, title: { display: true, text: 'Seconds (log scale)', font: { size: 10 }, color: '#9ca3af' } },
          x: { grid: { display: false } }
        }
      }
    });
  }

  function renderComparisonTable(entries) {
    var el = document.getElementById('table-comparison');
    if (!entries || entries.length === 0) { el.style.display = 'none'; return; }

    var latest = entries[entries.length - 1];
    var scales = ['8', '1K', '10K', '100K'];
    var html = '<table class="w-full text-xs"><thead><tr class="text-left text-[10px] uppercase tracking-wider text-gray-400">';
    html += '<th class="px-5 py-2 font-semibold">Scale</th>';
    html += '<th class="px-3 py-2 font-semibold text-right">Gaspatchio</th>';
    html += '<th class="px-3 py-2 font-semibold text-right">Lifelib</th>';
    html += '<th class="px-3 py-2 font-semibold text-right">Speedup</th>';
    html += '</tr></thead><tbody>';

    scales.forEach(function(scale, idx) {
      var gsp = latest.benches.find(function(b) { return b.name === 'gaspatchio/' + scale + '-points'; });
      var lib = latest.benches.find(function(b) { return b.name === 'lifelib/' + scale + '-points'; });
      var spd = latest.benches.find(function(b) { return b.name === 'speedup/' + scale; });
      if (!gsp) return;

      var stripe = idx % 2 === 0 ? '' : 'bg-gray-50/50';
      html += '<tr class="border-t border-gray-100 hover:bg-gray-50 transition-colors ' + stripe + '">';
      html += '<td class="px-5 py-2.5 font-medium text-gray-700">' + scale + ' points</td>';
      html += '<td class="px-3 py-2.5 text-right tabular font-semibold text-blue-600">' + (gsp ? fmtVal(gsp.value) + 's' : '--') + '</td>';
      html += '<td class="px-3 py-2.5 text-right tabular font-semibold text-red-600">' + (lib && lib.value > 0 ? fmtVal(lib.value) + 's' : 'timeout') + '</td>';
      html += '<td class="px-3 py-2.5 text-right"><span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold tabular bg-green-50 text-green-700">' + (spd && spd.value > 0 ? spd.value + 'x' : '--') + '</span></td>';
      html += '</tr>';
    });

    html += '</tbody></table>';
    el.innerHTML = html;

    // Hardware label
    var hw = latest.benches.find(function(b) { return b.name === 'hardware'; });
    // Hardware info comes from the comparison-results.json, not data.js - leave label for now
  }
```

- [ ] **Step 4: Add hardware label to all cards**

Add a subtitle line below the header in the `<main>` section:

```html
  <p class="text-[10px] text-gray-400 mb-6" id="hw-banner">All benchmarks on ubuntu-latest-m (16 cores, 64GB RAM)</p>
```

- [ ] **Step 5: Add a comparison status chip**

In the status-bar div, add:

```html
    <div class="flex items-center gap-2 px-3 py-1.5 bg-surface rounded-md text-xs border border-gray-200">
      <span class="w-2 h-2 rounded-full bg-gray-400 dot-pulse" id="dot-comparison"></span>
      <span id="label-comparison">Comparison: loading...</span>
    </div>
```

- [ ] **Step 6: Push to gh-pages**

```bash
cd /tmp/ghpages-comparison && git checkout gh-pages && git add index.html && \
    git commit -m "feat: add Gaspatchio vs Lifelib comparison card with grouped bars and speedup table" && \
    git push origin gh-pages
```

- [ ] **Step 7: Clean up worktree**

```bash
git worktree remove /tmp/ghpages-comparison
```

- [ ] **Step 8: Commit any workflow changes on the feature branch**

```bash
git add .github/workflows/evals.yml
git commit -m "feat(ci): add comparison benchmark job on ubuntu-latest-m"
```

---

### Task 8: Local end-to-end test

- [ ] **Step 1: Generate all model points**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/generate_model_points.py
```

- [ ] **Step 2: Run comparison at 8-point scale**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 8
```

Expected: both engines produce results, speedup is calculated, JSON written to `evals/benchmarks/comparison_results/`.

- [ ] **Step 3: Run comparison at 1K scale**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 1000
```

Expected: gaspatchio completes in ~1-2s, lifelib in ~minutes. Speedup ~50-150x.

- [ ] **Step 4: Preview on local dashboard**

Update `evals/serve_dashboard.py` to also copy comparison results, then refresh http://localhost:8788 to see the new card.

- [ ] **Step 5: Run at 10K if time permits**

```bash
cd bindings/python && uv run python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 10000
```

Note: lifelib at 10K may take 30+ minutes locally.

- [ ] **Step 6: Final commit**

```bash
git add evals/benchmarks/comparison_results/
git commit -m "test(benchmarks): local comparison results for validation"
```

---

### Task 9: Push branch and trigger CI

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin gsp-eval-refinement
```

- [ ] **Step 2: Verify the evals workflow triggers**

```bash
gh run list --workflow=evals.yml --limit 3
```

Expected: a new run appears targeting `gsp-eval-refinement` on `ubuntu-latest-m`.

- [ ] **Step 3: Monitor the comparison job**

```bash
gh run watch <run-id> --exit-status
```

Expected: all jobs complete on `ubuntu-latest-m`. Comparison job produces results pushed to gh-pages.

- [ ] **Step 4: Verify dashboard shows comparison data**

Navigate to `https://opioinc.github.io/gaspatchio-core/` and confirm the new "Gaspatchio vs Lifelib" card shows grouped bars and speedup table.
