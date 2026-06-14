# Rollforward Redesign

**Driver:** GSP-92 (cross-state arithmetic with mid-period column derivation).
**Scope:** replaces the rollforward shipped in GSP-86 (PR #80) with a state-machine model and an engine-agnostic IR aligned with GSP-95.
**Branch:** `gsp-92-rollforward-redesign` (off `develop`).

## Documents

- `specs/2026-04-30-rollforward-redesign-design.md` — full design proposal. Revised 2026-05-02 with §17 validation-pass findings (action_key, manifest, pass-chain, per-Op verify, batch_axes, Curve, contract_boundary).
- `research/2026-05-02-validation-pass-summary.md` — durable summary of the 18-agent parallel validation-pass investigation (7 actuary personas, 5 coverage probes, 6 SOTA library deep-dives) that informed the revision.

## Why

The shipped rollforward cannot express VA living-benefit recurrences (the `gaspatchio-va` product escapes into a 244-line numpy kernel). Research confirmed this shape is the *canonical* GMxB kernel per Bauer/Kling/Russ — and that fixing it warrants a structural redesign, not just adding three primitives. See §1 of the design.

## Cross-references

- GSP-92 (Linear) — the driving issue.
- GSP-95 (Linear) — engine-agnostic IR direction. **Phases 1–3 shipped on develop** (PRs #99, #100, #101). The rollforward redesign builds on this shipped foundation.
- `ref/31-rollforward-api/` — the original GSP-86 design, now superseded.
- `ref/37-dispatch-engine-refactor/ARCHITECTURE.md` — post-implementation guide for the dispatch / Polars-backend surface this redesign relies on.

## Implementation status

- **Phase 1a Sub-plan A — Typed Time** (Schedule + Calendar + DayCount): ✅ shipped on this branch
- **Phase 1a Sub-plan B — Curve**: ✅ shipped on this branch
- **Phase 1a Sub-plan C — MortalityTable**: ✅ shipped on this branch
- **Phase 1a Sub-plan D1 — IR + canonical form + audit identity**: ✅ shipped on this branch
- **Phase 1a Sub-plan D2 — Builder + compiler passes + explain**: ✅ shipped on this branch
- **Phase 1a Sub-plan D3a — Additive Rust kernel + Python collector + tests** (T1–T7, T9, T10): ✅ shipped on this branch
- **Phase 1a Sub-plan D3b — Destructive cutover** (T8, T11, T13, T14-stub, T15, T16): ✅ shipped on this branch
- **D3b deferred items** (T12, T14-body): see _Deferred from D3b_ below

## Deferred from D3b

Two items the plan listed inside D3b are intentionally not shipped on this branch:

- **T14 body — §4.9 GSP-92 VA acceptance test.** The scaffold (`tests/rollforward/test_va_acceptance.py`) ships skipped behind a `skipif(not GOLD_FILE.exists())` guard. Per spec §13.0, the test cannot be a release-gate until Phase 0 confirms `policy_00000065.parquet`'s gold values are independent of v1's `va_kernel.py`. When the gold file lands at `tests/fixtures/policy_00000065.parquet`, wiring is one focused PR (translate spec §4.9 worked example + reconcile loop).
- **T12 — Level-3 mini-VA tutorial migration.** The plan's premise was wrong: the L3 base model uses `cum_prod()` + `previous_period()` shifting, not the v1 `RollforwardBuilder`, so there is nothing to "migrate". Introducing rollforward to L3 is a focused tutorial-design task best owned by Phase 1b alongside the docs PR — separating it keeps the destructive-cutover diff readable.

The new state-machine kernel is exercised by 134 unit tests (the §4.4 Whole Life integration test, multi-state §4.7-style ratchet, lapse/contract_boundary stop-conditions, lazy/Struct release-gate, etc.); the v0.4.0 release decision is the user's call once Phase 0 + tutorial work land.

Plans:
- Plan A: [`plans/2026-05-04-phase-1a-schedule.md`](plans/2026-05-04-phase-1a-schedule.md)
- Plan B: [`plans/2026-05-04-phase-1a-curve.md`](plans/2026-05-04-phase-1a-curve.md)
- Plan C: [`plans/2026-05-04-phase-1a-mortality.md`](plans/2026-05-04-phase-1a-mortality.md)
- Plan D1: [`plans/2026-05-04-phase-1a-kernel-d1-ir.md`](plans/2026-05-04-phase-1a-kernel-d1-ir.md)
- Plan D2: [`plans/2026-05-04-phase-1a-kernel-d2-builder.md`](plans/2026-05-04-phase-1a-kernel-d2-builder.md)
- Plan D3: [`plans/2026-05-04-phase-1a-kernel-d3-execution.md`](plans/2026-05-04-phase-1a-kernel-d3-execution.md)
