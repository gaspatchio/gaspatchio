# Polars streaming + gaspatchio `with_scenarios` — empirical memory-scaling test

Date: 2026-05-09
Repo: `.` @ `docs/security-plan` (HEAD `d1b09e4`)
Polars: `1.38.1`
Python: `3.12` (`uv run python`)
Hardware: macOS Darwin 24.6.0 (15.7.3), x86_64, **16 GB physical RAM** (16384 MB)
Total experiment wall time: **~21 minutes** (setup + sweep + standalone N=500 retry).

---

## TL;DR — verdict

**Polars streaming does NOT keep memory bounded for `with_scenarios` cross-join expansion in the L5 typed model. Peak RSS grows roughly proportionally with `n_policies × n_scenarios` until the machine runs out of RAM and starts swapping. The break point on a 16 GB Mac sits between N≈200 and N=500 scenarios at 1k policies × 240 months, i.e. between 200k and 500k output rows.**

Three structural reasons (in priority order):

1. **`with_scenarios` is fundamentally eager.** `bindings/python/gaspatchio_core/scenarios/_with_scenarios.py:126-129` calls `af.collect()` to materialise the input frame, then does `pl.DataFrame.join(..., how="cross")` — both eager `DataFrame` operations. The full `n_policies × n_scenarios` row frame is produced in RAM before any model expression runs. Polars streaming can do nothing about this — the row replication is upstream of any lazy plan.
2. **The L5 typed model carries large list columns through its lazy pipeline.** Each row holds ~10 list-of-f64 columns each of length up to `projection_months + 1 = 241` (the per-policy time series). At ~50–60 KB per row of intermediate state, 100k rows already consumes 5–6 GB of RSS just for the live pipeline state.
3. **The streaming sink is `in-memory-sink`.** Polars' new streaming engine (verified engaged via `POLARS_VERBOSE=1` — see "Streaming-engine engagement" below) processes the lazy plan in chunks, but `LazyFrame.collect(engine="streaming")` writes the result back into a fully materialised `DataFrame`. So even where streaming chunking does help during pipeline execution, the final output gets re-materialised. With per-row final-state size still containing list columns, that final DataFrame alone is large.

The "streaming keeps memory bounded" hypothesis is **false** for this workload as currently implemented. To get bounded memory you would need to (a) replace the eager cross-join with a lazy/streaming-friendly equivalent (e.g. `LazyFrame.join(..., how="cross")` then sink to disk via `sink_parquet`/`sink_ipc`), and (b) avoid materialising per-policy list columns in the lazy pipeline (or sink chunked outputs by scenario).

---

## Methodology

- **Workload:** `1000 policies × N scenarios × 240 monthly periods` using the L5 typed VA model at `bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/base/model.py`. Model points: `level-5-scenarios/base/model_points_1k.parquet`.
- **Scenario IDs:** integers `1..N` (so the model takes the `is_string_scenario=False` branch in Section 16, broadcasting a single BASE discount-factor list rather than three. This isolates the cost of cross-join row replication from the per-scenario list-column cost.)
- **Scenario returns:** the parquet has `t = 0..179` so I tile the last 12-month cycle out to `t = 240` (steady-state proxy; perf-only, not actuarially valid). The returns table has no `scenario_id` column, so per-row return varies only with `t` and `fund_index`, not with scenario — i.e. all N scenarios use identical returns. This is a clean "what does the cross-join itself cost" experiment.
- **Subprocess isolation:** master harness `/tmp/scenario_scaling_master.py` spawns `/tmp/scenario_scaling_runner.py` per tier with `subprocess.run(..., timeout=360)`. Failure of one tier doesn't kill the master.
- **RSS measurement:** master uses `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` (macOS bytes) tracked as a high-water mark across children — for the first child it equals that child's peak; subsequent children only register a new peak if they exceed prior. Since each tier was strictly larger and successful tiers each set a new peak, the master values are accurate. The runner cross-checks via `RUSAGE_SELF` reported in `RESULT_JSON`; both agreed exactly across all successful tiers (e.g. N=200: master 8925.6 MB, child self 8925.6 MB).
- **Stop conditions** (revised after the first sweep showed N=1000 swap-thrashing):
  - Stop on first non-`ok` tier.
  - Stop if any tier wall time exceeds 180 s.
  - Stop if peak RSS exceeds 80% of system RAM (13107 MB).
  - Per-tier subprocess timeout 360 s.
- **N=500 fail capture:** the master sweep recorded N=500 as `killed_or_crash` because I had manually `kill -9`'d a runner during the prior tier's swap thrash; my SIGKILL landed on the N=500 child during data load. I retried N=500 standalone under `/usr/bin/time -l` to capture clean memory numbers; the standalone run completed (exit 0) but with 56.5 GB peak memory footprint vs 9.2 GB max RSS — i.e. heavy swap thrash. Wall time was not captured (~9–12 min observed). The retry value replaces the kill artefact in the results JSON; the row is labelled `thrash_completed_standalone` to flag the substitution.
- **N=1000 fail capture:** the original sweep reached N=1000 and I killed it after ~7 min of swap-thrash with no progress (CPU dropped from 800% to 91%, swap used 19.4 GB on a 16 GB-RAM machine). Recorded as `killed_swap_thrash`. I did **not** retry N=1000 standalone — the swap-thrash signal was clear and continued running risked rendering the host unusable.

---

## Streaming-engine engagement (verification)

`bindings/python/gaspatchio_core/frame/base.py:369` defaults `LazyFrame.collect()` to `engine="streaming"`. The runner explicitly passes `engine="streaming"` to confirm. With `POLARS_VERBOSE=1`, a sample collect emits:

```
polars-stream: running multi-scan[parquet] in subgraph
polars-stream: running in-memory-source in subgraph
polars-stream: running with-columns in subgraph
polars-stream: running in-memory-sink in subgraph
polars-stream: done running graph phase
```

Streaming **is** engaged. The sink is `in-memory-sink` — Polars produces a fully-materialised `DataFrame` at the end. There is no `sink_parquet` or other disk-spill path in `ActuarialFrame.collect()` or in the L5 model. There are no `pl.Config.set_streaming_chunk_size` calls in the gaspatchio-core codebase, and `POLARS_STREAMING_CHUNK_SIZE` is unset in the environment — defaults are in effect.

---

## Results

| n_scenarios | n_output_rows | status                       | wall (s) | peak RSS (MB) | peak mem footprint (MB) | RSS / scenario (KB) |
|------------:|--------------:|------------------------------|---------:|--------------:|-------------------------:|--------------------:|
| 1           | 1,000         | ok                           | 0.34     | 243.5         | (not captured)           | 249,304             |
| 10          | 10,000        | ok                           | 0.67     | 1,344.7       | (not captured)           | 137,694             |
| 50          | 50,000        | ok                           | 3.53     | 6,213.6       | (not captured)           | 127,254             |
| 100         | 100,000       | ok                           | 9.60     | 8,796.4       | (not captured)           |  90,075             |
| 200         | 200,000       | ok (+ swap pressure)         | 43.92    | 8,925.6       | (not captured)           |  45,699             |
| 500         | 500,000       | thrash_completed_standalone  | ~9–12 min* | 9,177.4     | **56,561**              |  18,795             |
| 1,000       | 1,000,000     | killed_swap_thrash           | killed @ ~7 min | (n/a)  | (n/a — VSZ peaked >65 GB) | n/a              |

\* N=500 standalone wall time was not captured by the time-l run (filtered grep dropped the line); observed elapsed before completion was ~9 min, with a second retry I aborted at 11 min still running.

Notes on RSS / scenario:
- The drop from 249 KB/scenario at N=1 to 18.8 KB/scenario at N=500 is **dominated by Python + module/extension load fixed cost** (the runner imports the gaspatchio core, builds typed assumption tables etc. — visible at N=1 as ~243 MB for 1000 rows). Subtract the N=1 fixed cost as a rough baseline: **marginal cost** ≈ (peak_rss − 243) / (n_rows − 1000) and you get a steadier picture.

| n_scenarios | marginal MB above N=1 baseline | marginal KB/row     |
|------------:|-------------------------------:|--------------------:|
| 10          | 1,101                          | 122                 |
| 50          | 5,970                          | 122                 |
| 100         | 8,553                          | 86                  |
| 200         | 8,682                          | 43                  |
| 500         | 8,934 (RSS-only) / 56,318 (incl. swap) | 17.9 (RSS) / 113 (incl. swap) |

The RSS-only marginal cost looks like it falls (122 → 43 KB/row), which would suggest streaming kicks in around 100k rows. **But the swap-thrash signal at N≥200 says otherwise:** RSS is capped by the OS pushing pages to swap, not by the application using less memory. Including swap, marginal cost at N=500 is back to ~113 KB/row, very close to the unconstrained 122 KB/row at N=10–50. **The "memory" at high N is just hidden in swap, not avoided.**

---

## Curve shape

- **n_scenarios → n_output_rows:** exact linear (cross-join is `n_policies × n_scenarios`).
- **n_output_rows → resident memory (RAM-only):** **linear up to physical-RAM saturation, then capped by paging** (i.e. memory keeps growing in *virtual size*, but RSS plateaus near 9 GB on this 16 GB box once swap takes over).
- **n_output_rows → total memory footprint (incl. swap):** **linear**, slope ~110–125 KB per output row.
- **Wall time vs n_scenarios:** super-linear once swap kicks in. N=100 took 9.6 s, N=200 took 43.9 s (4.6× slower for 2× more rows) — the swap-thrash inflection.

This is **not** "streaming bounded memory" curve shape. A streaming-bounded workload would show RSS plateauing at some chunk-related level (e.g. a few hundred MB) regardless of N. We see neither: RSS climbs steadily up to physical-RAM exhaustion, after which the OS starts paging.

---

## Break point

**First failure: N=500 (500k rows).** Mode: swap thrash. The process technically completes (exit 0) using 56.5 GB total memory footprint, of which only 9.2 GB is resident — the remaining 47 GB is in macOS encrypted swap. Wall time is ~9–12 minutes for a workload that on streaming-bounded semantics should take seconds. On Linux this would likely have been killed by the OOM killer; on macOS it staggers along via swap.

**Hard failure: N=1000.** Mode: swap-thrash with no measurable progress. After ~7 min of CPU-mostly-blocked-on-paging, I killed the process to free the host. macOS swap reached 19.4 GB used.

For practical purposes the limit on this 16 GB box is **N ≈ 200** (the largest tier that still completes under 60 s with bounded swap), and the failure regime begins at **N ≈ 500**. On a higher-memory box you would push the break-point up roughly proportionally to RAM — the underlying behaviour (linear scaling) doesn't change.

---

## Caveats

- **Sample of one model.** This is the L5 typed VA model with its specific list-column-heavy layout. A model that materialises only scalar columns per row would have a much smaller per-row cost and break later — but it would still scale linearly because `with_scenarios` itself is eager. The fundamental result (streaming does not bound the cross-join cost) does not depend on the model.
- **macOS swap masks the failure.** Reporting RSS-only would suggest N=500 "works" with 9.2 GB. Reporting *peak memory footprint* (which `getrusage` does not provide; I used `/usr/bin/time -l`) is necessary to see the truth. On Linux, `RUSAGE_CHILDREN.ru_maxrss` is closer to peak working-set anyway, and the OOM-killer would surface failures more cleanly. The numbers above were collected on macOS; recommend re-running on a Linux host of comparable RAM to remove the swap-masking confound before deciding on remediation.
- **`RUSAGE_CHILDREN.ru_maxrss` semantics.** macOS `ru_maxrss` is the high-water mark across all reaped children (monotonic). When subsequent children peak below the running maximum, the master can't isolate that child's RSS. In this sweep, every successful tier set a new high-water mark, so the master values ARE the per-child peaks. The runner-side `RUSAGE_SELF` cross-checks (within rounding to 4 KB pages) confirm this.
- **Streaming-engine version.** Polars 1.38.1, with the new streaming engine logging `polars-stream: ...` lines. Polars' streaming engine is under active development; on a future version with a default `sink_parquet` path or a streaming cross-join, this picture could change. As of 1.38.1, there is no streaming cross-join — `LazyFrame.join(how="cross")` is implemented but the materialisation pattern in `with_scenarios()` (`af.collect()` → `DataFrame.join(...)`) makes the discussion moot anyway.
- **No `streaming_chunk_size` knob is set in the gaspatchio codebase.** The default chunking applies. Setting it smaller would not help because the cross-join is materialised before any streaming path begins.
- **N=500 wall time is approximate.** I filtered the `time -l` output too aggressively and lost the wall line. Direct observation while running showed ~9 min in the first attempt and >11 min before I stopped a retry. The bottleneck is paging, so wall-time variability is high.

---

## Recommendations (out of scope for this experiment, captured for follow-up)

1. **Replace `af_df = af.collect(); af_df.join(scenarios_df, how="cross")` with a fully-lazy cross-join.** `LazyFrame.join(scenarios_lf, how="cross")` returns a `LazyFrame`. Then `with_scenarios` should *not* call `.collect()` — it should hand back an `ActuarialFrame` wrapping the lazy plan. The full row replication then happens during streaming execution, where Polars can chunk it.
2. **Provide a `sink_parquet` / `sink_ipc` path.** Currently `ActuarialFrame.collect()` always returns a fully-materialised `DataFrame`. For scenario-axis stress, exposing `sink_parquet(path)` lets the result spill chunked to disk and keeps RSS bounded by the streaming chunk size.
3. **Audit list-column intermediates in the L5 model.** Even if the cross-join becomes streaming-friendly, the per-row 241-element list columns dominate per-row state. For high-N stress runs, an explicit batch-by-scenario loop (call `main()` once per scenario or per scenario-batch and concatenate scalars only) sidesteps the worst of this — but at the cost of giving up the "scenarios as a column" abstraction.
4. **Re-run on Linux.** macOS swap-thrash is a noisy failure mode. A Linux re-run with `cgroups` memory caps (or just OOM-killer) would give cleaner break-point detection.

---

## Artefacts (kept in `/tmp`, not committed)

- `/tmp/scenario_scaling_master.py` — master sweep harness.
- `/tmp/scenario_scaling_runner.py` — single-tier subprocess runner.
- `/tmp/scenario_scaling_results.json` — raw per-tier results.
- `/tmp/scenario_scaling_master.log` — master stdout log.
- `/tmp/scenario_scaling_report.md` — this file.
