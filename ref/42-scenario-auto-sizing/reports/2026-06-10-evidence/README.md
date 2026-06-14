# Evidence artifacts — shape-aware `for_each_scenario` driver (2026-06-10)

Reproduction bundle for the strategy matrix in
[`../2026-06-10-shape-aware-driver-evidence.md`](../2026-06-10-shape-aware-driver-evidence.md).

## Files
- `evidence_grid.py` — the 14-cell sweep. Per cell, measures **Point A** (`batch_size="auto"`,
  in-memory) and **Point B** (`batch_size=1`, projection collect forced to `engine="streaming"`)
  independently, plus a correctness checksum. Sequential (timing integrity). Writes
  `evidence_results.jsonl` next to itself (one JSON line per cell; re-running overwrites it).
- `evidence_results.jsonl` — canonical raw output of the run.

The Point-B streaming is applied by monkeypatching `gaspatchio_core.scenarios._for_each._collect_with_peak`
to pass `engine="streaming"` — **no source edits**. (The scenario collect is in-memory in
`main` today; this models the candidate change.)

## Environment of the canonical run
| | |
|---|---|
| machine | macOS 15.7.7, x86_64, 16 cores, **16 GB RAM** |
| python / polars | 3.12.9 / **1.38.1** |
| gaspatchio-core | commit `6870e144` (branch `design/unified-aggregation-surface`) |
| memory budget at run time | ≈ 3.6 GB (from the 100K Point-A refusal message) |

**Numbers are machine/RAM-dependent.** The 100K Point-A budget refusal in particular depends on
available RAM at run time (16 GB box → ~3.6 GB budget). On a larger box Point A may become
feasible at 100K; the *relative* A-vs-B verdict per cell is the portable signal, not the absolute
seconds.

## Reproduce
```bash
# from the repo root
cd bindings/python
uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/evidence_grid.py
# ~15 min on a 16-core/16 GB box; heavy cells (1000sc, 100K) are the long poles.
# results land in ../../ref/42-.../2026-06-10-evidence/evidence_results.jsonl
```
Requires the model-point parquets: `tutorial/level-5-scenarios/base/model_points_{1k,10k}.parquet`
(in git) and `evals/benchmarks/model_points/l5_100k.parquet` (generated artifact — if absent, the
100K cell records a file error; the 1K/10K cells still run).

## Caveats
- `peak=-1.0` means the RSS-delta sampler returned no reading (transient peak below baseline noise).
  Wall is the robust signal; peak is noisier.
- Floating-point checksums can differ at the last ulp (~1e-15 relative) between batch sizes —
  Polars parallel-sum order, benign.
- This is a scratch evidence harness. The spec phase should promote it to a proper
  `evals/benchmarks` job (dedicated-runner numbers, CI regression guard).
