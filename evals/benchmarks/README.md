# End-to-end model benchmarks

What the `model-benchmarks` and `comparison-benchmarks` jobs in
`.github/workflows/evals.yml` measure, where the data lands, and which
historical jumps are deliberate trades rather than regressions.

## What runs

`run_model_benchmarks.py` executes the L4 (lifelib base) and L5
(scenarios) tutorial models at 8 / 1K / 10K / 100K model points and
records per-size:

- `points` — wall-clock seconds for one full projection
- `throughput` — points per second
- `data-mb` — sum of `List(Float64)` cell counts × 8 bytes (the actual
  per-policy column footprint, independent of Python/Polars overhead)
- `memory` — Python-allocated bytes around the run
- `rss` — peak process resident set size
- `cores`, `cpu-avg` — per-core utilisation sampled at 10 Hz

`run_comparison_benchmarks.py` runs gaspatchio against `lifelib` on the
same model-point sets so the two engines can be compared at matched
scale.

The lifelib reference (modelx project + assumption tables + model-point
CSVs) lives in the sibling **gaspatchio-benchmarks** repository. The
runner resolves it via the `GASPATCHIO_BENCHMARKS_DIR` environment
variable, falling back to `../gaspatchio-benchmarks/` (sister-checkout)
relative to this repo. CI clones it explicitly in the `Gaspatchio vs
Lifelib` job; local development needs a sibling clone or the env var
set. See `_benchmarks_dir.py` and the gaspatchio-benchmarks README for
detail.

`run_scenario_benchmarks.py` exercises the **bounded-memory scenario loop**
(`for_each_scenario(batch_size="auto")` — the PR #106 default path) on the L5
variable-annuity model with stochastic fund returns. It runs an L-shaped grid and
records per cell `wall` (seconds), `rss` (peak MB), `throughput`
(scenario·points/sec), and `batch` (the batch size `auto` resolved to):

| Arm | Cells | Story |
|---|---|---|
| scenario-scaling | 1K points × {10, 100, 1000} scenarios | **peak RSS stays flat as scenarios climb** — `auto` packs scenarios into RAM-bounded batches |
| portfolio-scaling | 10 scenarios × {10K, 100K} points | big-book scenario runs at scale |

The grid is calibrated to fit the 120-min CI budget (see
`ref/42-scenario-auto-sizing/reports/2026-05-30-scenario-testdrive.md`). **`1000 × 100K`
is deliberately excluded** (~10 hr of compute — a 100M-projection cross-product); it is
not a gap. The portfolio arm's scenario count (10) is the conservative first-dry-run
value and may be raised once the runner's real timings are confirmed.

## Where the data lands

Each job uses `benchmark-action/github-action-benchmark` to push results
to the `gh-pages` branch. Linux keeps the historical paths; Windows uses
sibling paths so the baselines stay OS-specific:

- `dev/model-bench/` → https://opioinc.github.io/gaspatchio-core/dev/model-bench/
- `dev/model-bench-windows/` → https://opioinc.github.io/gaspatchio-core/dev/model-bench-windows/
- `dev/comparison/`  → https://opioinc.github.io/gaspatchio-core/dev/comparison/
- `dev/comparison-windows/` → https://opioinc.github.io/gaspatchio-core/dev/comparison-windows/
- `dev/bench/`       → https://opioinc.github.io/gaspatchio-core/dev/bench/ (Rust criterion)
- `dev/bench-windows/` → https://opioinc.github.io/gaspatchio-core/dev/bench-windows/ (Rust criterion on Windows)
- `dev/evals/`       → https://opioinc.github.io/gaspatchio-core/dev/evals/ (skill evals)
- `dev/scenario-bench/` → https://opioinc.github.io/gaspatchio-core/dev/scenario-bench/ (scenario throughput & memory)
- `dev/scenario-bench-windows/` → https://opioinc.github.io/gaspatchio-core/dev/scenario-bench-windows/ (scenario throughput & memory on Windows)

The dashboards are time-series charts keyed by commit SHA. The raw JSON
sits alongside in `data.js` on the `gh-pages` branch — useful for
scripted analysis.

## Windows larger runner

Windows benchmark lanes target the GitHub-hosted larger runner named
`windows-m` (16 cores / 64 GB RAM). GitHub assigns larger runners a workflow
label that matches the runner name, so the workflow uses `runs-on: windows-m`.

This is deliberately core- and RAM-matched to the Linux lane's
`ubuntu-latest-m` (16 cores / ~62.8 GB) so Linux-vs-Windows numbers are an
apples-to-apples OS comparison rather than a hardware-tier comparison. (The
earlier `windows-large`, 8 cores / 32 GB, made multi-core gaspatchio runs look
~2× slower purely from the core-count gap; single-threaded lifelib still showed
the true per-core OS penalty of ~1.2×.)

These jobs run directly on the Windows host, not in Docker. GitHub's
Windows images include Docker for Windows-container workloads, but they
do not provide the same Linux-container runtime used by Ubuntu runners.
Native execution is also the number we want: it measures the Windows
Rust/Python/Polars stack rather than a container boundary.

Benchmark jobs install with `uv sync --no-dev` because the `dev`
dependency group includes `memray`, which does not support Windows.

## Triggering

The full evals job runs:

- weekly on Monday at 03:00 UTC (cron),
- on every push to `main` and `develop`,
- on PRs labelled `benchmark`,
- on `workflow_dispatch`.

Manual `workflow_dispatch` runs accept:

- `platform=windows`, `suite=benchmarks` — Windows Rust/model/lifelib benchmarks only
- `platform=windows`, `suite=performance` — Windows scenario throughput/memory only
- `platform=all`, `suite=all` — full historical behavior

Add the `benchmark` label to a PR to compare its commit against develop
on the dashboard.

The heavier **`scenario-benchmarks`** job (`Scenario Throughput & Memory`, 120-min
timeout) runs on push to `main`/`develop`, weekly cron, `workflow_dispatch`, and on PRs
labelled **`performance`** (a distinct label, so a perf run doesn't drag in the 120-min
lifelib comparison). Add the `performance` label to a PR to dry-run the scenario grid on
the cloud runner before merge.

## Reading regressions

The dashboards alert when a metric exceeds the per-job threshold
(`alert-threshold` in `evals.yml`). A commit-over-commit jump is not
automatically a bug — sometimes it's a deliberate trade. The list below
records the intentional ones so they aren't "fixed" by future passes.

### 2026-05-02: boolean-mask → `when/then/otherwise` (PR #102, commit `e1d2597`)

Tutorial L4/L5/L3-step-06 model files rewrote 13 sites of the form

```python
af.x = af.value * (cond1) * (cond2)         # before
af.x = when(cond1 & cond2).then(af.value).otherwise(0.0)   # after
```

The two forms are semantically identical (output reconciled
byte-identical to develop baseline). They are not equivalent at the
Polars level: the multiply form lowers to a single SIMD-friendly
`cast(bool→f64) * value`, the `when/then` form invokes the branchy
`if_then_else` kernel.

Effect on `dev/model-bench/`:

| Bench | `04ed0ec12` | `d5dc1730c` | Δ |
|---|---|---|---|
| VA Model 100K-points | 5.094s | 6.031s | +18.4% |
| VA Model 10K-points | 0.750s | 0.831s | +10.8% |
| VA + Scen 100K-points | 14.642s | 17.069s | +16.6% |
| VA + Scen 10K-points | 1.681s | 1.994s | +18.6% |
| VA + Scen 100K data-mb | 7798 MB | 7353 MB | −5.7% |
| VA + Scen 100K rss | 10943 MB | 10365 MB | −5.3% |

Time goes up because the kernel changed; memory goes down because the
bool-cast intermediate column is no longer materialised.

The trade was deliberate: the `value * (cond)` shortcut is flagged in
`skills/gaspatchio-model-building/references/conditionals-and-lists.md` as
unfamiliar to actuaries reviewing models, and the L4/L5 tutorials are
the canonical lifelib reconciliation answer keys. The cost lives in the
benchmarks because the benchmarks run those exact files. Do not revert
to recover the speed without also moving the audit story back.

If we ever want both: lower `when(c).then(v).otherwise(0.0)` with
scalar branches to `v * c.cast(f64)` inside the gaspatchio frontend.
That's a real perf project, not a hotfix.
