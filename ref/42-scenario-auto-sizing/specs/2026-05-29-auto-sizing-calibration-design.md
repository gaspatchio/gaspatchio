# Scenario auto-sizing + learned memory calibration — design

**Date:** 2026-05-29
**Status:** implemented on `gsp-100-post-merge` (fixes #1, #2, #3 + `auto` default)
**Scope:** one branch carrying fix #1 (jagged timelines, done), fix #3 (`auto`
peak-correct + fast, done), and **fix #2 — the learned calibration cache (the
new build in this spec)**.

---

## 1. Goal

Make `ScenarioRun.run(...)` / `for_each_scenario(...)` with `batch_size="auto"`
reliably achieve **maximum throughput within the box's RAM budget**, robustly
across (a) heterogeneous machines, (b) different models, and (c) repeated runs of
the same model — which are common (same model, many valuation dates / scenario
sets). "Auto" must walk the line between over-sizing (OOM) and under-sizing
(wasted throughput) without the user hand-tuning `batch_size`.

## 2. Settled positions (and the dead ends we ruled out)

Grounded in the research in `../42-auto-sizing-research-findings.md`:

- **Budget = a fraction of *detected physical RAM*** (`target_memory_fraction ×
  psutil.virtual_memory().available`, already in place). Adapts to the box. Never
  key sizing on a fixed byte count.
- **The transient-peak RSS probe (`_measure_peak_delta`, fix #3) is the
  cold-start authority.** It is the only signal that captures the materialisation
  spike that actually OOMs.
- **We do NOT size from the Polars plan.** Polars exposes no cardinality/cost
  estimator; the analytic `n_policies × n_periods × n_list × 8` estimate measures
  *steady-state output*, not the transient peak, and its inputs aren't cleanly
  available at the sizing point. (Refuted — high confidence.) It may return later
  only as an optional divergence-warning cross-check; not in this spec.
- **`per_policy` (jagged timelines) stays opt-in.** Auto-detecting
  "pure-projection, no rollforward" before collect is infeasible, and a blanket
  default-flip risks breaking models that join a uniform external list (e.g.
  L5-typed). The system fails *closed*: the `rollforward()` guardrail rejects a
  jagged schedule, and any cross-column length mismatch raises a loud
  `ShapeError` — never a silent wrong number. (Refuted — high confidence.)
- **New: a learned calibration cache** converts the cold probe into a one-time
  cost. Repeated runs of the same model read the empirically-observed peak and
  size from it directly — no probe.

## 3. Architecture

**`batch_size="auto"` is the DEFAULT** for `for_each_scenario` and
`ScenarioRun.run` (pre-release decision — the "it just works", max-throughput-
within-RAM path; no back-compat constraint). `batch_size=N` and `bytes_per_cell`
remain explicit opt-outs/overrides.

```
budget = target_memory_fraction × physical_RAM            # per-box, existing

batch_size == int            → "manual"        (explicit opt-out)
batch_size == "auto"  (DEFAULT):
    master_seed set OR drivers-dict shape?  → resolve to 1 (serial; these modes
                                              need per-scenario execution), no probe
    user passed bytes_per_cell?  → "auto_calibrated"  (explicit override)
    else cache HIT (valid)?      → "auto_cached"      (NEW: size from learned peak, NO probe)
    else                          → "auto_probe"       (fix #3 peak probe → size)
                                    └─ after the run: RECORD observed peak to cache
```

**Default-flip interaction:** `master_seed` and the drivers-dict shape currently
*raise* if `resolved_size > 1` (they only support serial execution). With `"auto"`
the default, those cases **resolve to 1** rather than raising; the existing guards
remain but now fire only when a user *explicitly* sets `batch_size>1` with a seed
or drivers (a genuine error). Batching never changes results, so flipping the
default changes only *how work is chunked*, never the numbers.

Precedence: serial-required (seed/drivers) > explicit `bytes_per_cell` > learned
cache > cold probe. The cache is
a thin, **fail-open** read/write wrapper around the existing
`resolve_batch_size` call site — `resolve_batch_size`'s signature does **not**
change. On a cache hit the wrapper sizes the batch directly (it has budget +
learned per-policy cost + `n_policies` + `n_scenarios`) and labels it
`auto_cached`; on a miss it calls the existing probe path and then writes the
observed peak back.

## 4. The learned calibration cache (the new component)

A new module `scenarios/_batch_profile.py` (sibling of `_audit.py`), plus
read/write hooks at the `for_each_scenario` sizing site.

### 4.1 Location & file layout — sharded, one file per model

**Multiple models run on the same machine** (and often concurrently), so the
cache is a **directory of per-model files**, not one shared JSON:

- **Per-user cache dir via `platformdirs`** (add as a dependency):
  `Path(platformdirs.user_cache_dir("gaspatchio")) / "batch_calibration"`.
  - Windows `%LOCALAPPDATA%\gaspatchio\Cache\batch_calibration\`,
    macOS `~/Library/Caches/gaspatchio/batch_calibration/`,
    Linux `~/.cache/gaspatchio/batch_calibration/`.
- **One JSON file per (model, output-shape)**, named by a filesystem-safe hash:
  `<sha256(plan_sha + shape_fp)>.json` (see §4.2 for `shape_fp`). Different
  models/shapes → different files → they **never contend on the same file**,
  which is the whole point of sharding (see §4.8). `host_id` is implicit in the
  per-user cache dir, but `box_total_ram` is still validated inside each entry
  (§4.6) in case the dir is on a synced/network home.
- Each file is tiny (one model's learned cost + short history). Multiple models
  coexist as independent files; no project-tree sidecars, so nothing is
  committed or carried to another box.
- **Pruning:** on write, if the directory exceeds a cap (e.g. 500 files), evict
  the oldest by mtime. Keeps the cache bounded as models come and go.

### 4.2 Cache key — output-shape fingerprint, not source text

The cache predicts **per-policy peak memory**, which is driven by the projection's
**output shape** (number/dtype of `List` columns × horizon), *not* by the source
text. So identity is keyed on a **shape fingerprint**, which makes the cache
robust to the evolutionary nature of models — an LLM adding reconciliation lines
one at a time, an actuary adding products over months:

- `shape_fp = sha256(sorted output List-column names+dtypes  [+ n_periods when the
  output frame carries a Schedule])`, combined with `plan_sha`. The filename is
  `sha256(plan_sha + shape_fp).json`; the per-policy-normalised cost rescales
  across `n_policies`/`n_scenarios` within the entry.
- **Cheaply computable pre-collect** via `collect_schema()` on a lazy `model_fn`
  build (no materialisation; `frame/base.py:284` already uses this path). This is
  the one valid use of "assess the expression tree before `.collect()`":
  fingerprinting the *shape*, not predicting the absolute size (which the schema
  cannot give — see findings).
- **Survives line-by-line evolution and renames.** Cosmetic edits, renames,
  reordered logic, or scalar intermediates that don't change the output
  `List`-column set leave `shape_fp` unchanged → the calibration still applies.
  The cache is most useful exactly during active model-building, which a source
  hash would defeat (it would invalidate on every keystroke).
- **Re-learns exactly when the profile changes.** Adding a cashflow `List` column
  or extending the horizon changes `shape_fp` → a new file → one re-probe, then
  warm again. The model is never "lost"; it accrues a shape entry per profile as
  it evolves — matching the actuary/LLM notion of "the same model, now bigger".
- `plan_sha` — `ScenarioRun.source_sha()` (`_run.py:109-111`); for the bare
  `for_each_scenario` path with no plan, derive a sha from the scenario shape.
- **Collisions** between two genuinely different models are unlikely (distinct
  cashflow column names → distinct `shape_fp`); if one ever occurred, the OOM
  ratchet (§4.7) corrects the mis-size on the next run.
- **Optional explicit `model_id`** escape hatch — a caller may pin a stable id to
  force a lineage or disambiguate same-shape models. Not required; `shape_fp` +
  ratchet covers the common case.
- **Host is implicit** in the per-user cache dir; each entry still validates
  `box_total_ram_bytes` + `platform.node()` (§4.6) for synced/network homes.

> We deliberately do **not** fingerprint `model_fn` source (`inspect.getsource`):
> it invalidates on every cosmetic edit (defeating the cache during active
> model-building) and conflates "the text changed" with "the memory profile
> changed". `shape_fp` captures only the latter — which is all the cache needs.
> The OOM ratchet backstops the rare case where a heavy *intermediate* spikes the
> transient peak without changing the output shape.

### 4.3 What is recorded (per entry)

- `cost_per_policy_per_scenario_bytes` — the learned normalised cost,
  `observed_peak_bytes / (batch_used × n_policies)`. This bypasses the unknown
  `n_periods` entirely (it folds the true horizon + per-cell footprint into one
  measured number) and rescales linearly with `n_policies`.
- `observed_peak_bytes`, `batch_used`, `n_policies`, `n_scenarios` — raw
  observation, for audit + rescale.
- `box_total_ram_bytes`, `polars_version`, `gaspatchio_version`,
  `schema_version`, `updated_at` (timestamp passed in, not `Date.now()` in any
  pure layer), `run_count`, and a short ring buffer `recent_costs` (last K).

### 4.4 Read path (cache hit → `auto_cached`)

1. Build the key; load + validate the entry (§4.6).
2. `per_scenario_bytes = cost_per_policy_per_scenario_bytes × n_policies`.
3. `resolved = clamp(1, ⌊budget × SAFETY / per_scenario_bytes⌋, n_scenarios, _SAFETY_CEILING)`.
4. Return `(resolved, "auto_cached")` — **no probe**.

### 4.5 Write path (after every `auto`/probe run)

Always record, even on the probe path, so the cache warms:
1. The per-batch `collect()` is wrapped in `_measure_peak_delta` (fix #3's
   sampler) — record the **transient peak**, never the steady-state
   `result.peak_rss_mb` (which under-reports → would over-size → OOM).
2. Compute `cost_per_policy_per_scenario_bytes` from the run's peak / batch /
   n_policies.
3. Update the entry with the **fit rule** (§4.7) and atomically persist (§4.8).

### 4.6 Invalidation vs. rescale

- A different `plan_sha`/`shape_fp` is a different *file*, so model+shape identity
  is handled by the filename — no in-file check needed for it.
- **Invalidate** (ignore the entry, fall back to probe) if any differ from the
  current environment: `polars_version`, `gaspatchio_version`, `schema_version`,
  `platform.node()`, or `box_total_ram_bytes` (beyond a small tolerance). The
  node + RAM checks defend the synced/network-home case where the per-user dir
  isn't truly per-machine.
- **Rescale, don't discard**, on `n_policies` / `n_scenarios` change — the cost
  is normalised per policy, so it transfers.

### 4.7 Fit rule (OOM-leaning ratchet)

Memory mis-estimates are asymmetric: under-budget → crash, over-budget → slower.
So the learned cost is **conservative**:

- `learned_cost = max(recent_costs)` over a window of K (e.g. 5) observations.
  Window-max never under-budgets below the recent worst, and naturally *deflates*
  as old high observations age out of the window.
- **Ratchet up** by a safety factor (e.g. ×1.5) if a run signals memory
  pressure: caught `MemoryError`, or observed peak ≥ budget (we hit the ceiling
  we were trying to stay under).
- A robust statistic (max over a short window) resists a single poisoned/outlier
  observation permanently inflating the estimate.

### 4.8 Concurrency, atomicity, Windows-safety, fail-open

- **Atomic writes:** write to a temp file in the same dir, then `os.replace(tmp,
  final)` — atomic on POSIX *and* Windows. No `fcntl`/POSIX-only locking.
- **Concurrency (multi-model):** sharding by model is the primary defence —
  different models write different files, so concurrent runs of *different*
  models never race or clobber each other (the failure mode a single shared JSON
  would have under read-modify-write). Two concurrent runs of the *same* model
  contend on one file; atomic `os.replace` keeps it uncorrupted and
  last-writer-wins is acceptable (both are learning the same cost). Reads
  tolerate a partial/corrupt file → treated as a miss.
- **Fail-open everywhere:** any IO error (read-only mount, missing dir,
  permission, corrupt JSON, `platformdirs` failure) is swallowed and degrades to
  the probe path. Calibration must never abort or slow a real run. Mirror the
  probe's "never abort a run" posture.
- All paths via `pathlib.Path`; `mkdir(parents=True, exist_ok=True)` guarded.

## 5. Integration points (file:line, on the ScenarioRun branch)

- `scenarios/_for_each.py:404-412` — `resolve_batch_size(...)` call site: cache
  READ goes immediately before (hit → size directly, skip probe); WRITE goes
  after the run with the recorded peak.
- `scenarios/_for_each.py:486-498` — per-batch `model_fn` build + `collect()`:
  wrap in `_measure_peak_delta` to capture the transient peak for the WRITE
  (the sampler from fix #3 already exists here for the probe).
- `scenarios/_auto_batch.py` — unchanged signature; gains awareness only of the
  new `"auto_cached"` resolution label for the audit trail.
- `scenarios/_run.py:109-111` — `source_sha()` is the `plan_sha`; thread it down
  into `for_each_scenario` (currently set to `""` at the loop and stamped later)
  so the cache key is available at sizing time.
- `scenarios/_run.py:264` (audit record) — add the resolution label
  (`auto_cached`/`auto_probe`/`auto_calibrated`/`manual`) + cache hit/miss + the
  learned cost, so a run's batch decision is fully auditable.
- New `scenarios/_batch_profile.py` — load/validate/update/atomic-persist; pure
  + fail-open; cloned write style from `_audit.py`.

## 6. Data flow

```
for_each_scenario(af, scenarios, model_fn, batch_size="auto"):
    n_policies = af.height ; n_scenarios = len(sids)            # pre-collect, cheap
    budget = target_fraction × physical_RAM
    af_proj  = model_fn(af1)                                     # lazy build, NO collect
    shape_fp = fingerprint(af_proj.collect_schema())            # List cols (+ n_periods)
    entry = batch_profile.read(plan_sha, shape_fp)               # fail-open
    if entry and valid(entry):
        batch = size_from_cost(entry.cost, n_policies, budget)   # "auto_cached", no probe
    else:
        batch, _ = resolve_batch_size("auto", ..., probe_fn)     # "auto_probe" (fix #3)
    run batches; per batch: peak = _measure_peak_delta(collect)  # transient peak
    batch_profile.write(plan_sha, shape_fp, peak, batch, n_policies, n_scenarios)  # atomic, ratchet
    audit.record(resolution, cache_hit, learned_cost)
```

## 7. Testing strategy (TDD; pure Python, no Rust)

Unit (deterministic, no real RSS/FS — inject readers/paths):
- `_batch_profile` round-trip: write→read returns the entry; corrupt/missing file
  → miss (fail-open); unwritable dir → no raise, returns miss.
- Key composition: different `shape_fp` (new List column / horizon) / `host_id` /
  version → miss; same → hit; `n_policies` change → rescaled cost.
- Fit rule: window-max conservatism; ratchet-up on `MemoryError`/peak≥budget;
  deflation as old observations age out; outlier resistance.
- `size_from_cost`: clamps to `[1, n_scenarios, _SAFETY_CEILING]`; fills budget.
- Atomicity: temp + `os.replace`; concurrent writers don't corrupt (last wins).

Integration (real model on the branch):
- Cold run probes + writes; warm run hits (`auto_cached`), **no probe**, and
  resolves to a batch within the budget — assert peak RSS stays under the budget
  and throughput ≥ the probe path.
- Cosmetic model edit (comment/rename; same output shape) → still a **hit** (no
  re-probe). Adding an output `List` column / extending the horizon (new
  `shape_fp`) → **miss** → re-probes, then warm again.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Model evolves (LLM/actuary edits lines) | `shape_fp` key: cosmetic edits keep the entry (cache stays warm); a new output `List` column / longer horizon mints a new entry (one re-probe) — never a stale-source OOM |
| Heavy intermediate spikes peak without changing output shape | `shape_fp` unchanged → at most one under-sized run → OOM ratchet (§4.7) bumps it; budget safety margin absorbs the single run |
| Steady-state peak under-reports → over-size → OOM | Record `_measure_peak_delta` transient peak, never `result.peak_rss_mb` |
| Read-only / shared / CI dirs | Per-user cache dir + fail-open swallow all IO errors |
| Multiple models per machine clobbering one shared file | Shard: one file per (model, shape) (`sha(plan_sha+shape_fp).json`) — different models/shapes never touch the same file; dir pruned to a cap |
| Concurrent runs of the *same* model | Atomic `os.replace`; advisory last-writer-wins (same learned cost); tolerant reads |
| Cache poisoning / outliers | Window-max over short history; conservative ratchet |
| Box RAM changed between runs | `box_total_ram_bytes` invalidation + `host_id` in key |

## 9. Implementation status — DONE

All of fixes #1, #2, #3 plus the `"auto"`-default flip are **implemented on
`gsp-100-post-merge`** (off develop) and validated:

- **Fix #1 (jagged timelines):** byte-identical reconciliation (0 in-force overlap
  mismatches across 58 list columns) on L4 and develop's rewritten typed L5 at
  10K — including the external uniform disc-factor list the typed L5 trims
  per-policy via `list.head(af.month.list.len())`.
- **Fix #3 (`auto` peak + short-circuit):** end-to-end −22%/−55% wall on the
  pathological cases.
- **Default flip:** `batch_size="auto"` is the default; `"auto"` resolves serial
  for seed/drivers (§3).
- **Fix #2 (learned cache):** `scenarios/_batch_profile.py` + integration in
  `for_each_scenario` (this §4). Real-model e2e: cold→`auto_probe` writes the
  entry, warm→`auto_cached` skips the probe (warm runs bit-identical; cold-vs-warm
  within 1 ULP — Polars parallel-sum non-determinism). Cache isolated per-test via
  `tests/scenarios/conftest.py`. Full scenarios suite 410 passed;
  projection/schedule/rollforward/per-policy green.

## 10. Out of scope

Analytic plan-based sizing as a probe replacement; jagged-by-default /
auto-detection; spill-to-disk safety net; native per-policy `n_periods` in the
rollforward kernel (GSP-97, still deferred).
