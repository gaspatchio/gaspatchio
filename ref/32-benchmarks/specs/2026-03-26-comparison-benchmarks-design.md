# Gaspatchio vs Lifelib Comparison Benchmark — Design Spec

**Date**: 2026-03-26
**Status**: Draft
**Branch**: gsp-eval-refinement

## Problem

Gaspatchio claims to be significantly faster than existing actuarial frameworks. We need reproducible, fair, head-to-head performance numbers comparing gaspatchio against lifelib's IntegratedLife model on the same calculations, same data, same hardware.

## Model Under Test

**IntegratedLife** — a variable annuity model with GMDB/GMAB guarantees from lifelib's `appliedlife` library. This is the model used in gaspatchio's Level 4 tutorial, already reconciled to 0.0000% against lifelib across ~9 million data points.

Both engines compute full monthly projections including:
- Select/ultimate mortality with scalar adjustments
- GMDB and GMAB guarantee mechanics
- Dynamic lapse based on ITM ratio
- Risk-free rate curve discounting
- Account value rollforward with investment returns
- Death, lapse, maturity claims
- Premiums, expenses, commissions
- Present values of all cashflows

## What We Measure

**Question**: "How long does it take to get valuation PV results from model points?"

Both engines internally compute full timestep projections to arrive at PVs — the measurement captures the complete computation graph.

### Measurement Phases

Each run reports two phases plus a total:

| Phase | Gaspatchio | Lifelib |
|-------|-----------|---------|
| **Setup** | Import gaspatchio + load model.py + register assumption tables | Import modelx + `mx.read_model("IntegratedLife")` |
| **Projection** | Load model points + `model.main(af)` + `collect()` → extract PV columns | `run.GMXB.result_pv()` (triggers all upstream cell computation) |
| **Total** | Sum of setup + projection | Sum of setup + projection |

Setup is measured once per engine (amortized). Projection is measured per scale.

### Output Equivalence

- Gaspatchio: `model.main(af).collect()` → PV columns (pv_net_cf, pv_claims, etc.)
- Lifelib: `run.GMXB.result_pv()` → equivalent PV DataFrame

Both produce the same 10 PV aggregates per model point. Numerical equivalence is already proven by the L4 reconciliation (0.0000% tolerance).

### Scales

| Scale | Model Points | Expected Gaspatchio | Expected Lifelib |
|-------|-------------|--------------------|-----------------|
| 8 | Original reconciled set | <1s | ~10-15s |
| 1K | Generated (sampled + varied) | ~1-2s | ~minutes |
| 10K | Generated | ~5-10s | ~tens of minutes |
| 100K | Generated | ~30-60s | ~hours (with 64GB may complete) |

Per-scale timeout: 45 minutes. If exceeded, record `timeout` rather than block.

## Hardware

**All benchmarks run on `ubuntu-latest-m`** (16 cores, 64GB RAM). This applies to:
- Criterion Rust benchmarks (moved from `ubuntu-latest`)
- Gaspatchio model benchmarks (moved from `ubuntu-latest`)
- Comparison benchmarks (new)

Every result carries hardware metadata. The dashboard displays: "All benchmarks on ubuntu-latest-m (16 cores, 64GB RAM)".

## Architecture

### File Layout

```
evals/benchmarks/
  run_comparison_benchmarks.py    # NEW — head-to-head runner
  lifelib_runner.py               # NEW — isolated lifelib invocation
  lifelib_ref/                    # NEW — copy of IntegratedLife model + data
    IntegratedLife/                #   modelx model directory
    model_point_data/             #   lifelib-format model points
    input_tables/                 #   assumption tables
    economic_data/                #   scenario data
    model_parameters.xlsx         #   run parameters
  run_model_benchmarks.py         # existing, unchanged
  generate_model_points.py        # existing, needs lifelib-format generation
  model_points/                   # existing generated data
```

### lifelib_ref Directory

Copied from `gaspatchio-models/appliedlife/ref/appliedlife/`. Self-contained — no cross-repo CI dependency. The modelx model, all input data, and configuration files. ~2-5MB total.

### run_comparison_benchmarks.py

Main orchestrator. Flow:

1. Record hardware metadata (cores, RAM, runner name from env)
2. Generate model points at all scales if not present (reuse existing generator, plus lifelib-format conversion)
3. **Gaspatchio setup**: Import + load model module + register assumptions (timed)
4. **Lifelib setup**: Import modelx + `mx.read_model()` (timed)
5. For each scale (8, 1K, 10K, 100K):
   a. Run gaspatchio: load MPs → `model.main(af)` → `collect()` → extract PVs (timed)
   b. Run lifelib: load MPs → `result_pv()` (timed)
   c. Record both timings + peak memory
6. Output JSON for benchmark-action + comparison JSON for dashboard

### lifelib_runner.py

Isolated module for lifelib invocation. Handles:
- `os.chdir()` to model directory (modelx requirement)
- Patching `scen_size()` for deterministic mode (`num_scenarios=1`)
- Feeding model points (lifelib uses its own CSV/Excel format internally via `model_point_data/`)
- Restoring working directory after run
- Per-scale timeout with subprocess isolation if needed

### Model Point Translation

Gaspatchio uses parquet, lifelib uses CSV/Excel in a specific directory structure. The comparison script needs to:
1. Use the existing gaspatchio model points (parquet) for gaspatchio runs
2. Convert/generate equivalent lifelib-format model points for lifelib runs
3. Ensure both get the same policies at each scale

The 8-point set already exists in both formats. For generated sets (1K, 10K, 100K), we extend `generate_model_points.py` to also write lifelib-format CSVs.

### Output Format

```json
[
  {"name": "gaspatchio-setup", "unit": "seconds", "value": 0.8},
  {"name": "lifelib-setup", "unit": "seconds", "value": 8.2},
  {"name": "gaspatchio/8-points", "unit": "seconds", "value": 0.12},
  {"name": "lifelib/8-points", "unit": "seconds", "value": 14.5},
  {"name": "speedup/8", "unit": "x", "value": 120.8},
  {"name": "gaspatchio/1K-points", "unit": "seconds", "value": 0.9},
  {"name": "lifelib/1K-points", "unit": "seconds", "value": 95.0},
  {"name": "speedup/1K", "unit": "x", "value": 105.6}
]
```

## CI Integration

### Workflow Changes (evals.yml)

All three benchmark jobs move to `ubuntu-latest-m`:

```yaml
rust-benchmarks:
  runs-on: ubuntu-latest-m
  # ... unchanged steps

model-benchmarks:
  runs-on: ubuntu-latest-m
  # ... unchanged steps

comparison-benchmarks:           # NEW
  name: Gaspatchio vs Lifelib
  runs-on: ubuntu-latest-m
  timeout-minutes: 120
  steps:
    - checkout with LFS
    - setup-uv
    - uv sync (with lifelib extras)
    - generate model points (both formats)
    - run comparison benchmarks
    - store results via benchmark-action
```

### Dependencies

Add as dev dependencies in `pyproject.toml`:

```toml
[dependency-groups]
benchmark = ["lifelib>=0.11.0", "modelx>=0.28.1", "openpyxl>=3.1.5"]
```

Installed only for the comparison job: `uv sync --group benchmark`

### Dashboard

New prominent card: **"Gaspatchio vs Lifelib"**

- **Grouped bar chart**: gaspatchio (blue) vs lifelib (red) at each scale
- **Stacked bars**: setup (light shade) + projection (dark shade)
- **Speedup callout**: "Xx faster" badge derived from latest run
- **Hardware label**: "ubuntu-latest-m — 16 cores, 64GB RAM" in card header
- **Table below chart**: scale, gaspatchio time, lifelib time, speedup, gaspatchio memory, lifelib memory

All existing benchmark cards also get the hardware label since they're moving to the same runner.

## Fairness Guarantees

1. **Same model**: IntegratedLife VA with GMDB, reconciled to 0.0000%
2. **Same data**: Identical model points at each scale (generated from same source)
3. **Same hardware**: Both run sequentially on the same `ubuntu-latest-m` runner
4. **Same measurement**: Wall-clock time from "model points available" to "PV results in memory"
5. **Deterministic mode**: Lifelib patched to `scen_size=1` for single-scenario parity
6. **No cherry-picking**: Full end-to-end timing reported, broken down into setup + projection
7. **Reproducible**: All code, data, and runner config checked into repo; anyone can re-run

## Framing and Presentation

These tools have different design goals. The benchmark must respect both.

**Gaspatchio** is purpose-built for high-throughput production valuation — vectorized Rust/Polars execution optimized for processing millions of policies.

**lifelib** is designed for transparent, auditable model development — cell-based formulas (via modelx) that read like spreadsheets, with dependency tracing, interactive debugging, and formula-level auditability. Its tagline is "Use Python like a spreadsheet!" Speed is a secondary concern; the primary value is accessibility and transparency for actuaries.

There is no vectorized `_ME` variant of IntegratedLife — this is the only version. The comparison is against lifelib's actual production model, not a deliberately slow configuration.

### Dashboard Framing

The "Gaspatchio vs Lifelib" dashboard card must include:

- **Header subtitle**: "Both produce identical results (0.0000% reconciliation) — different design goals, different performance profiles"
- **Context note**: "lifelib prioritizes formula transparency and auditability via modelx's cell-based execution. Gaspatchio prioritizes throughput via vectorized Rust/Polars computation. This benchmark measures execution speed only."
- **Link to lifelib**: Prominent link to https://lifelib.io — credit the project and let readers explore it
- **What lifelib offers that gaspatchio doesn't**: Formula-level dependency tracing, interactive cell debugging, spreadsheet-like model authoring. These are real features that come at a performance cost.

### What This Benchmark Shows

This benchmark answers ONE question: "How long does each tool take to compute the same VA model results?" It does NOT claim that gaspatchio is "better" — speed is one axis, and lifelib optimizes for others.

## Open Questions

1. **Model point format for lifelib at scale**: How does lifelib's `model_point_data/` directory handle 100K points? Need to verify the CSV format and whether modelx can handle it.
2. **Lifelib memory at 100K**: May need >64GB. If so, we cap at 10K for lifelib and note it.
3. **Warm-up runs**: Should we do a warm-up run before timing? Gaspatchio's first run includes JIT-like Polars optimization; lifelib's modelx caches cell results.
