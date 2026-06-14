# 42 — Scenario auto-sizing: jagged timelines + learned memory calibration

**Topic:** Recover the per-policy projection throughput lost in #104, and make
`ScenarioRun` / `for_each_scenario` `batch_size="auto"` reliably hit **maximum
throughput within the box's RAM** — across heterogeneous machines and repeated
runs of the same model.

**Branch:** single branch carrying all three fixes below (continuation of the
GSP-100 ScenarioRun bounded-memory work and the #38 projection-axis unification).

**Related prior work:** [#38 projection-axis](../38-projection-axis/README.md)
(unified `af.projection.set(...)`), [#41 backend-portability](../41-backend-portability/README.md)
(`for_each_scenario` bounded-memory design), [#28 scenario-runs](../28-scenario-runs/28-scenario-runs-rfc.md).
GSP-97 ("native per-policy `n_periods`", deferred from #38 as high-regression-risk)
is partially delivered here at the *projection* layer (jagged timelines) without
touching the rollforward kernel.

## Why this exists

The #104 "projection-axis API unification" replaced the old **per-policy,
variable-length** projection timeline with a single **uniform, max-length** grid
broadcast to every policy. A policy with 12 months left began carrying the
longest-lived policy's full horizon. Measured on the L4/L5 tutorial models this
was a ~1.5× list-element inflation → a real, commit-located throughput
regression (dashboard `dev/model-bench`: VA-100K 5.96s → 7.62s at `66141051`),
distinct from and on top of the deliberate #102 `when/then` trade.

Separately, the `ScenarioRun` `batch_size="auto"` path mis-sized: it measured
*retained* RSS (not transient peak) and always ran a costly second probe, so
`auto` degenerated to "one giant batch + probe overhead" — the worst of both
throughput and memory.

## The three fixes (all on one branch)

| # | Fix | Status |
|---|---|---|
| 1 | **Jagged per-policy timelines** — `af.projection.set(..., per_policy=True)` builds a variable-length (`per_policy_grid`) schedule so each policy projects only its own horizon. Adaptive: keeps the new API, adds a third schedule kind; guarded so `rollforward()` rejects jagged loudly. | ✅ implemented (opt-in) |
| 3 | **`auto` peak-correct + fast** — the probe now measures the *transient peak* working set (`_measure_peak_delta` sampler), and `resolve_batch_size` short-circuits to one batch when the whole set fits the RAM budget (skips the wasteful second probe). Goal: max throughput within RAM. | ✅ implemented |
| 2 | **Learned memory calibration cache** — record observed peak per (plan, model, shape) in a per-user, per-model cache so repeated runs of the same model skip the cold probe and size from the empirically-observed cost. | ✅ implemented (`_batch_profile.py` + `for_each_scenario` integration) |

(Numbering follows the order they were investigated; all three are now implemented on `gsp-100-post-merge`.)

## Verified findings that shaped the design

A 6-agent research workflow (4 investigators + 2 adversarial verifiers) grounded
the design in the actual code and Polars internals. Two strong claims were
**refuted (high confidence)** and steered us away from tempting dead ends:

1. **"Size from the Polars plan before `.collect()`" — NO.** Polars exposes no
   cardinality/cost estimator (`explain()`'s `ESTIMATED ROWS` is a parquet-leaf
   figure that does not propagate through the cross-join). An analytic estimate
   `n_policies × n_periods × n_list × 8` is buildable from `collect_schema()` +
   the `Schedule`, and matches `estimated_size()` to ~2% — **but it measures
   steady-state output, not the transient peak that OOMs**, and the inputs
   (`n_periods`, a `Schedule`) are not cleanly available at the sizing point. So
   the analytic estimate is at best an optional cross-check, **not** a
   replacement for the peak probe. → We keep the probe as the cold-start authority.

2. **"Auto-detect pure-projection and flip jagged on by default" — NO.**
   "No-rollforward" is only knowable *at* collect (after every list column is
   already materialised on the chosen grid; there is no safe late rewrite), and
   a cross-column list-length mismatch is statically undetectable (a
   `List(Float64)` dtype carries no length). The L5-*typed* model joins a uniform
   external list, so a blanket default-flip risks breaking it. → **`per_policy`
   stays opt-in**; the system fails *closed* (rollforward guardrail + loud
   `ShapeError`, never a silent wrong number).

3. **"Learned calibration cache" — YES, feasible and well-precedented** (SQL
   Server CE Feedback, DB2 LEO, Spark AQORA). The cache supplies `bytes_per_cell`
   automatically, turning the existing `auto_calibrated` path into a self-fitting
   one. It keys on `plan_sha` + an **output-shape fingerprint** (List columns +
   horizon, read via `collect_schema()`) — not a source hash — so it survives a
   model's line-by-line evolution and re-learns only when the memory profile
   actually changes.

## Documents

- `specs/2026-05-29-auto-sizing-calibration-design.md` — the design spec (the
  settled positions + the learned-cache architecture). Feeds `writing-plans`.
- `42-auto-sizing-research-findings.md` — provenance: what's knowable
  pre-collect, the two adversarial verdicts, prior-art mechanisms, file:line map.

## Out of scope (deliberately)

- **Analytic plan-based sizing as a probe replacement** — refuted (peak ≠
  steady-state). May return later only as an optional cross-check warning.
- **Jagged-by-default / auto-detection** — refuted; `per_policy` stays opt-in.
- **Spill-to-disk safety net** — a larger piece (Polars streaming doesn't bound
  the cross-join); noted as a future direction in #41, not built here.
- **Native per-policy `n_periods` in the rollforward kernel** — still GSP-97,
  still deferred (high regression risk); the jagged work here is projection-only.
