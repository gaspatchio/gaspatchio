# Scenario Scripts

Utility scripts for running and analyzing actuarial model scenarios.

## Benchmarks

`benchmarks.py` measures assumption lookup vs calculation performance for RFC 29 optimization planning.

### Usage

```bash
# From gaspatchio-core/bindings/python directory:

# Default: 100k policies x 3 scenarios (full benchmark)
uv run python tests/scratch/scenarios/scripts/benchmarks.py

# Quick test run
uv run python tests/scratch/scenarios/scripts/benchmarks.py --policies 1k --scenarios 1

# Medium scale
uv run python tests/scratch/scenarios/scripts/benchmarks.py --policies 10k --scenarios 3

# Custom configuration
uv run python tests/scratch/scenarios/scripts/benchmarks.py \
    --policies 100k \
    --scenarios 3 \
    --seed 12345
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--policies` | `100k` | Model points size: `small`, `1k`, `10k`, `100k` |
| `--scenarios` | `3` | Number of stochastic scenarios |
| `--seed` | `12345` | Random seed for reproducibility |
| `--output`, `-o` | None | Output file for results (JSONL format, appends)

### Output

The benchmark reports:
- **Collection time**: Wall-clock time to execute the model
- **Timing by Category**: Breakdown of LOOKUP vs CALCULATION time
- **Top Operations**: Most expensive operations by time
- **Lookup Throughput**: Estimated lookups per second

### How it Works

1. Loads model points and generates stochastic returns
2. Runs the `applied_life` model with `ActuarialFrame.profile()`
3. Categorizes profile nodes by output column names:
   - LOOKUP: `base_mort_rate`, `mort_scalar`, `base_lapse_rate`, `inv_return_mth`, `surr_charge_rate`, `disc_rate`
   - CALCULATION: All other `with_column` operations
   - OTHER: Projections, scans, filters
4. Extrapolates profile ratios to wall-clock time for realistic absolute timings

### Example Output

```
======================================================================
BENCHMARK RESULTS
======================================================================

Configuration:
  Policies:    100k
  Scenarios:   3
  Total rows:  300,000

Timing Summary:
  Model execution:  0.22s
  Collection time:  47.37s

Timing by Category (extrapolated from profile ratios):
-------------------------------------------------------
Category        Time (s)     % of Total
-------------------------------------------------------
LOOKUP          29.28        61.8        %
CALCULATION     17.10        36.1        %
OTHER           0.99         2.1         %
-------------------------------------------------------
TOTAL           47.37        100.0       %
```

### Saving Results for Comparison

Use `--output` to save results in JSONL format (one JSON object per line):

```bash
# Run benchmark and save results
uv run python tests/scratch/scenarios/scripts/benchmarks.py \
    --policies 100k --scenarios 3 \
    -o benchmark_history.jsonl

# Results are appended, so you can track across runs
uv run python tests/scratch/scenarios/scripts/benchmarks.py \
    --policies 100k --scenarios 3 \
    -o benchmark_history.jsonl
```

Each line contains:
```json
{
  "timestamp": "2025-12-10T21:23:26.814317+00:00",
  "git": {"commit": "5eb33c6", "branch": "main"},
  "config": {"policies": "100k", "scenarios": 3, "total_rows": 300000},
  "timing": {"model_execution_s": 0.22, "collection_s": 47.37},
  "categories": {
    "LOOKUP": {"time_s": 29.28, "pct": 61.8},
    "CALCULATION": {"time_s": 17.10, "pct": 36.1}
  },
  "throughput": {"estimated_lookups": 324000000, "lookups_per_sec": 6869591720}
}
```

## Other Scripts

- `compare_models.py` - Compare outputs between model implementations
- `convert_assumptions.py` - Convert assumption tables to parquet format
- `reconcile_models.py` - Reconcile gaspatchio vs lifelib outputs
- `run_integratedlife.py` - Run the IntegratedLife lifelib model
- `verify_reconciliation.py` - Verify reconciliation results
