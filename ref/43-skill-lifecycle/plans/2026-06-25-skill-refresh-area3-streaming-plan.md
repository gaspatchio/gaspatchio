# Area 3 — Streaming / scale: refresh plan

> **For agentic workers:** execute via the `skill-update` loop. PURE DRAFT (new
> runners; nothing removed). Grounded against develop — still cross-check every
> signature against the source.

**Goal:** Teach memory-bounded execution of a single model at portfolio scale —
`run_aggregated` (fold to aggregates) and `run_to_parquet` (spill full output) —
in the `model-building` skill. Currently the skills only mention `batch_size` in
the *scenario* context (`model-scenarios`); the standalone scale runners are
untaught.

**Fix vs draft:** DRAFT. Nothing removed. The existing single-run path
(`gspio run-model`, `af.collect()`) stays valid for small portfolios; these
runners are the scale-out path.

---

## Grounded API (verified: `scenarios/_aggregated.py`, `scenarios/_spill.py`)

Both are top-level: `from gaspatchio_core import run_aggregated, run_to_parquet`
(also under `gaspatchio_core.scenarios`). **Verify the import path before writing.**

### `run_aggregated` — fold each batch to aggregates (no full materialization)

```python
run_aggregated(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,          # a DataFrame, NOT an ActuarialFrame
    aggregations: Sequence[Aggregator],  # Sum(...).alias(...), PeriodSum(...).alias(...), ...
    *,
    batch_size: int | "auto" = "auto",
    align: "calendar" | "duration" | None = None,
) -> AggregatedResult
```

`AggregatedResult` fields: `aggregations` (dict), `n_policies`, `n_periods`,
`batch_size`, `wall_time_s`, `peak_rss_mb`. **Aliases are attribute-accessible**
(`res.pv_net_cf` ≡ `res.aggregations["pv_net_cf"]`). It is **not a frame** — read
by attribute / telemetry; never call `.collect()` on it.

```python
from gaspatchio_core import run_aggregated
from gaspatchio_core.scenarios import Sum, PeriodSum

aggregations = [
    Sum("pv_net_cf").alias("pv_net_cf"),     # scalar: one number for the portfolio
    PeriodSum("net_cf").alias("net_cf"),     # per-period vector (term structure)
]
res = run_aggregated(model_fn, model_points_df, aggregations)   # batch_size="auto"
res.pv_net_cf        # scalar aggregate
res.net_cf           # per-period list
res.peak_rss_mb      # telemetry — peak RSS was ~one batch, not the whole portfolio
res.wall_time_s
```

Use `run_aggregated` whenever the deliverable is **totals / per-period aggregates /
tail metrics** — it never holds the whole portfolio in memory (peak RSS ≈ one
batch's working set).

### `run_to_parquet` — spill full per-policy output in memory-safe batches

```python
run_to_parquet(
    model_fn, model_points: pl.DataFrame, output_dir: Path,
    *, batch_size: int | "auto" = "auto", mounts_text: str | None = None,
) -> SpillResult
```

`SpillResult` fields: `output_dir`, `n_policies`, `n_batches`, `wall_time_s`,
`peak_rss_mb`. Writes `batch_NNNN.parquet` into `output_dir`. Use when you need the
**full per-policy result** (cannot fold to aggregates). Read it back with
`pl.scan_parquet(output_dir / "*.parquet")`.

```python
from pathlib import Path
from gaspatchio_core import run_to_parquet

spill = run_to_parquet(model_fn, model_points_df, output_dir=Path("out/"))
spill.n_batches            # number of batch_NNNN.parquet files
full = pl.scan_parquet("out/*.parquet")   # lazy-scan the spilled output
```

### Choosing

| Deliverable | Runner |
|---|---|
| Totals / per-period aggregates / CTE / quantiles | `run_aggregated` → `AggregatedResult` |
| Full per-policy cashflows (audit, downstream join) | `run_to_parquet` → parquet shards |
| Small portfolio, interactive | `af.collect()` / `gspio run-model` (existing) |

---

## Gotchas to teach (grounded)

- **`AggregatedResult` is not a frame** — read aliases as attributes (`res.x`) +
  telemetry (`res.peak_rss_mb`); do **not** `.collect()` it.
- **`batch_size="auto"` is cgroup-blind** — the sizer reads *host* RAM, so in a
  container / CI with a memory cap it can over-size and OOM. Pass an explicit
  `batch_size=<int>` in constrained environments.
- **Every aggregator needs `.alias(name)`** — `run_aggregated` raises without it.
- **`PeriodQuantile.over()` is not supported on `run_aggregated`** (its multi-level
  output has no tidy column form) — use `PeriodMedian`/`PeriodCTE` with `.over()`,
  or `PeriodQuantile` without `.over()`. (Same boundary noted in Area 2.)
- **`model_points` is a `pl.DataFrame`**, not an `ActuarialFrame` — `model_fn`
  receives the `ActuarialFrame` per batch.

## What to edit

1. **Create `skills/model-building/references/running-at-scale.md`** — the deep
   dive: the two runners, the choosing table, the gotchas, telemetry, and a note
   that the aggregators are the Area 2 family (cross-link `model-scenarios` /
   `references/...` for the aggregator catalogue). Realistic columns, ≤600 lines.
2. **`skills/model-building/SKILL.md`** — a short pointer near the "Environment" /
   running section: small portfolios use `gspio run-model` / `collect()`; for
   portfolio scale use `run_aggregated` (aggregates) or `run_to_parquet` (full
   output) — see the new reference. A few lines.
3. **Check `model-scenarios`** — it already mentions `run_aggregated` under the
   hood; add at most a one-line cross-link to the new scale reference if natural.
   Do not duplicate.

## Verification

1. **Source cross-check:** every `run_aggregated`/`run_to_parquet` example uses
   only real params (signatures above) and the real `AggregatedResult`/`SpillResult`
   fields; verify the top-level import path.
2. **Grep gate:** `grep -rn "run_aggregated\|run_to_parquet\|AggregatedResult" skills/model-building/`
   shows the new content.
3. **Structural gate** (worktree env — lancedb): `uv run --no-project --with pytest
   --with pyyaml python -m pytest tests/skills/ -q` → all pass; new reference ≤600 lines.
4. **Deferred:** L3 lift spot-check once #138 lands.

## REVIEW

Report the diff + grep/structural results. Commit on `feat/skill-refresh`
(conventional, no AI trailer). Do not push. `AGENTS.md` out of scope. Add any
tutorial issues found to `ref/45-tutorial-refresh/2026-06-25-tutorial-refresh-findings.md`.
