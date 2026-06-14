# Streaming convergence hook — implementation plan (approved)

Branch: `gsp-100-post-merge` (worktree `~/projects/gaspatchio/gaspatchio-core-postmerge`).
Design + adversarial critique: produced by workflow `wf_95e8bd8f-3c1`. Decisions below are FINAL.

## Decisions (settled by user)
1. **API: `on_batch` callback ONLY** (no framework `stream_path=`). JSONL/atomic-append/CTE all live in the caller.
2. **`progress=True` → built-in default `on_batch`** that logs `scenarios {done}/{total}` via loguru. Rule: the default is installed ONLY when the user passed no `on_batch`; if BOTH are set, the user's `on_batch` wins silently (no raise). Replaces the current NotImplemented warning (L546-552).
3. **`outputs` = materialised `extract_output` per alias** (NOT raw accumulators). Locked by critique: sketch aggregators mutate `SignedSketch` in place and return the same object, so raw state would retro-corrupt emitted snapshots.

## Framework change — `bindings/python/gaspatchio_core/scenarios/_for_each.py`

Add a public frozen dataclass (the only new public type):
```python
@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    batch_idx: int          # 0-based, == loop enumerate index
    scenarios_done: int     # cumulative real scenarios folded so far (this batch inclusive)
    total_scenarios: int    # == len(sids)
    outputs: dict[str, Any] # {alias: agg.extract_output(running_acc)} — running partials; scalar for plain aggs, pl.DataFrame for .over(...)
    peak_rss_mb: float | None
```

Add kwarg to `for_each_scenario` (next to `progress`/`plan_sha`):
`on_batch: Callable[[BatchSnapshot], None] | None = None`.

**Exact edits (line refs from the current file):**
- **`progress` block (L546-552):** replace the `warnings.warn(...)` with: if `progress and on_batch is None`, set `on_batch` to a built-in handler `def _default(snap): logger.info("scenarios {}/{}", snap.scenarios_done, snap.total_scenarios)`. If `progress and on_batch is not None`, leave the user's `on_batch` (progress ignored). Needs `from loguru import logger` at top (add WITH its first use — the on-save ruff hook strips unused imports).
- **Before the loop (after L563 `max_batch_peak = 0`):** `scenarios_done = 0`.
- **First statement inside the loop body (right after `for batch_idx, batch_sids in enumerate(_chunks(...)):` L565):** `scenarios_done += len(batch_sids)`.
- **End of the loop body, AFTER the `current_rss`/`peak_rss` update block (after L672, before the loop iterates):** fire the hook, gated:
  ```python
  if on_batch is not None:
      # NEVER pass raw accumulators here: sketch add_input mutates SignedSketch
      # in place and returns the same object, so a later batch would retro-mutate
      # an already-emitted snapshot. extract_output returns fresh values -> safe.
      if peak_rss is not None and baseline_rss is not None:
          _snap_peak_mb = max(0, peak_rss - baseline_rss) / (1024 * 1024)
      else:
          _snap_peak_mb = None
      _snap_outputs = {
          alias: agg.extract_output(accumulators[alias])
          for alias, agg in zip(aliases, aggregations, strict=True)
      }
      with contextlib.suppress(Exception):
          on_batch(BatchSnapshot(batch_idx=batch_idx, scenarios_done=scenarios_done,
                                 total_scenarios=len(sids), outputs=_snap_outputs,
                                 peak_rss_mb=_snap_peak_mb))
  ```
  (`contextlib` is already imported — it's used at L684.) The `logger.debug` on hook failure is OPTIONAL; if added, put it inside an `except` instead of bare suppress. Simpler: keep `contextlib.suppress(Exception)` (fail-open) and skip the debug log to avoid the suppress/except mismatch.
- **`__all__` (L723):** add `"BatchSnapshot"`.

**Probe isolation (no double-count):** the hook lives only in the main loop (starts L565), strictly after all probe code (L397-503) and the lazy fingerprint build (L461). `accumulators` is created at L554-558, after every probe. `scenarios_done` starts at 0 and only the real loop increments it. No special handling needed.

## Stub — `bindings/python/gaspatchio_core/scenarios/__init__.pyi` (MUST, or stubtest CI breaks)
There is NO `_for_each.pyi`. The public signature is in `__init__.pyi` (the `def for_each_scenario(...)` around L208-225). Add `on_batch: Callable[[BatchSnapshot], None] | None = ...` to that stub, declare `class BatchSnapshot:` with the five fields + an `__init__`, and add `"BatchSnapshot"` to the stub `__all__`. Verify: `cd bindings/python && uv run python -m mypy.stubtest gaspatchio_core` (green).

## Runtime export — `bindings/python/gaspatchio_core/scenarios/__init__.py`
Import `BatchSnapshot` from `_for_each` and add to `__all__`.

## Framework tests — `bindings/python/tests/scenarios/test_for_each_streaming.py` (NEW, TDD)
1. **frame count** == `ceil(n / resolved_size)` and the final snapshot's `scenarios_done == n` (use an explicit `batch_size`).
2. **probe not streamed** — `batch_size="auto"`: number of `on_batch` calls == number of real batches; probe scenarios never appear (scenarios_done never exceeds n; first frame's scenarios_done == resolved_size, not more).
3. **bit-exact running partial** — the running `dist` (`Sum("v").alias("dist").over("scenario_id")`) after K batches equals a from-scratch K-scenario run's `dist` (order-independent for `.over`, so non-flaky).
4. **exception suppressed** — an `on_batch` that raises does NOT abort the run; the `ScenarioResult` is still returned and correct.
5. **serial path** — `master_seed=...`, `batch_size=1` (or auto→serial): hook fires once per scenario, `scenarios_done` = 1,2,3,...
6. **progress=True** installs a default logging hook (capture loguru INFO, assert a `scenarios .../...` line) and does NOT fire if a user `on_batch` is also passed (user wins).
7. **non-streaming pays nothing** — without `on_batch`/`progress`, behaviour/`ScenarioResult` unchanged (a couple existing tests already cover this; add an explicit "no on_batch → no extra extract" smoke if cheap).

## Demo — `evals/benchmarks/run_scenario_convergence.py` (NEW)
Mirrors `run_scenario_showcase.py`. Runs `for_each_scenario` with `Sum("pv_net_cf").alias("dist").over("scenario_id")` and an **explicit small `batch_size` (≈20-25 for ~1000 scenarios → ~40-50 frames)** — MUST NOT use `"auto"` (auto fast-paths to `min(n,256)` → ≤4 frames). The `on_batch`:
- `totals = np.array(snap.outputs["dist"].sort("scenario_id")["dist"].to_list())`; `loss = -totals`.
- `cte70 = portfolio_cte(loss, 0.70)`, `cte95 = portfolio_cte(loss, 0.95)` (reuse `scenario_lib.portfolio_cte`).
- quantiles `np.quantile(loss, [.05,.25,.5,.75,.95])`, `mean`.
- **histogram with a FROZEN range** — freeze `(lo, hi)` once (from the first frame that has ≥~30 scenarios, OR a cheap config) and write `hist_range:[lo,hi]` + `bins` into the meta header; thereafter `np.histogram(loss, bins=40, range=(lo,hi))`. Per-frame auto-range is a BUG (rescales every tick).
- **JSON sanitise**: convert NaN/inf → `None` before `json.dumps(rec, allow_nan=False)` (degenerate early frames, `peak_rss_mb=None`). Round floats to ~2dp.
- **atomic append**: open `stream.jsonl` once in append mode; write the meta header + `flush()` BEFORE the loop; one `json.dumps(rec)+"\n"` + `flush()` per frame.
- Document a header comment: the convergence trace assumes scenarios are exchangeable/iid in input order (frame K = exact figure over the first K·batch scenarios, a prefix subsample, not a bootstrap). The showcase's GBM draws are iid in id-order, so this holds; consider shuffling sids to be robust.
- `# ruff: noqa: T201` + repo-root sys.path guard like the other scripts.

### JSONL schema
- Line 0 meta: `{"type":"meta","total_scenarios":N,"n_points":P,"batch_size":B,"batch_size_resolution":R,"bins":40,"hist_range":[lo,hi],"schema_version":1}`.
- Frames: `{"type":"frame","batch_idx","scenarios_done","total_scenarios","cte70","cte95","p05","p25","p50","p75","p95","mean","hist_counts":[...40 ints],"peak_rss_mb","wall_s"}` (hist edges are fixed in meta, so frames carry only counts).

## Viewer — `evals/benchmarks/stream_viewer.html` (NEW, dependency-free)
CDN `vega@5`/`vega-lite@5`/`vega-embed@6`. `setInterval(tick, 300)` → `fetch('stream.jsonl', {cache:'no-store'})` → split lines, `try/catch` JSON.parse per line (drop a torn trailing line), cache the meta header. Stop polling when latest `scenarios_done === meta.total_scenarios`. Two panels: (A) convergence `mark_line` x=`scenarios_done` y=value color=series (fold CTE70/CTE95 into long form in JS); (B) filling histogram `mark_bar` from the LATEST frame's `hist_counts` + meta `hist_range` edges, plus two `mark_rule` at CTE70/CTE95 (color `#CD853F`, matching `render_scenario_showcase.py`). Header: `scenarios_done/total`, `batch_size_resolution`, `wall_s`, `peak_rss_mb`. Show "waiting…" if the file 404s.

## Docs
Mark `ref/42-scenario-auto-sizing/FOLLOWUPS.md` section 2 as implemented (link this plan).

## Must-fix checklist (verify before "done")
- [ ] Demo forces explicit small `batch_size` (NOT auto).
- [ ] Histogram range frozen + in meta header; frames carry counts only.
- [ ] `__init__.pyi` updated (on_batch param + BatchSnapshot class + __all__); `mypy.stubtest` green.
- [ ] NaN/inf → null + `json.dumps(allow_nan=False)`; 1-scenario batch yields valid parseable JSON (test).
- [ ] `outputs` is materialised `extract_output`; code comment forbids raw accumulators; bit-exact K-vs-scratch test passes.
- [ ] Whole snapshot/extract block gated behind `if on_batch is not None`.
- [ ] `peak_rss_mb` computed inline (NOT the post-loop variable, which is assigned after the loop).
- [ ] All 7 framework tests pass; full `tests/scenarios/` suite green; ruff clean (select=ALL); no AI signature in commits.
