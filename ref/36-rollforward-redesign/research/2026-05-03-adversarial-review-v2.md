---
title: Codex Adversarial Review of v2 Rollforward Redesign Spec
date: 2026-05-03
reviewer: codex:adversarial-review (background task b8tz28pf9)
codex_thread: 019ded59-8fac-7741-b863-a88c758c263b
branch: gsp-92-rollforward-redesign
diff_range: 16bc12d..1f9946e
target: ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md (1,293 lines)
verdict: needs-attention — no-ship
---

# Codex Adversarial Review

Target: working tree diff
Verdict: needs-attention

No-ship. The v2 spec overclaims portability and audit identity while leaving core schedule semantics underspecified in places that change numbers, not just ergonomics.

## Findings

### [high] Engine-portable identity claim vs Polars-only escape hatches

`ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md:673-684`

The design says the rollforward IR is engine-agnostic and that the same `spec_fingerprint` survives a future Polars→JAX swap, but the same section immediately allows transition bodies to use `pl.max_horizontal(...)`, calls that are admitted to be outside the closed semantic subset. Later, Phase 1 also includes an `Apply` escape hatch and defers the only JAX portability proof to Phase 2. The result is a misleading audit boundary: a Phase 1 model can be valid, hashable, and documented as engine-portable while still depending on semantics that a future backend is not required to implement. That is a migration and reproducibility hazard, not a stylistic issue.

**Recommendation:** Tighten the contract now: either restrict Phase 1 transition bodies to the closed subset only and remove Polars-only examples/escape hatches from the canonical path, or explicitly scope `spec_fingerprint` portability to the Polars backend until a second backend exists and passes equivalence tests.

### [high] `action_key()` does not actually close over typed input changes

`ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md:941-946`

Phase 1 defines `action_key` as `spec_fingerprint || input_data_sha || gaspatchio_version || git_sha`, but the spec's own Curve examples claim separate runs differ by input-curve SHAs. That does not follow from the API shown here unless every external typed input (Curve payloads, Table files, MortalityTable sources, Schedule-derived data) is folded into `input_data_sha` by convention. The spec never defines that convention. In practice this means two runs can have identical `action_key`s while using different curve/table contents, which breaks cache safety, rerun traceability, and any audit story built on `action_key`.

**Recommendation:** Define `action_key` over an explicit hash set of all runtime inputs, not a single opaque `input_data_sha`. At minimum, specify and expose hashes for typed Curve/Table/MortalityTable/Schedule sources so the examples are mechanically true rather than aspirational.

### [high] Phase 1 ships first-class Schedule without specifying the two semantics the research itself says are required

`ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md:583-600`

The spec presents `from_inception` and `from_calendar_grid` as the Phase 1 answer to per-policy versus shared-grid scheduling, while also hard-coding full-period lapse/contract-boundary behavior. But the supporting schedule research identified two additional requirements as necessary for this design to be numerically safe: join semantics between per-policy schedules and a reporting calendar grid, and partial-period `dt` at the terminating period. Those are not minor extensions; they control when cash flows stop and how cohort aggregation lands on reporting dates. Shipping Schedule as a first-class Phase 1 primitive without those semantics means users can get plausible but wrong reserve timing with no schema or type error to warn them.

**Recommendation:** Either demote Schedule to the documented MVP fallback (precomputed `dt`/masks upstream) for Phase 1, or add explicit Phase 1 semantics for reporting-grid joins and terminating-period proration before treating Schedule as complete enough to fingerprint into the core model identity.

### [medium] Default schedule semantics do not encode month-end anchoring the research says is load-bearing

`ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md:527-534`

The Schedule section claims the default convention matches US/UK/EU production practice, but the example constructor uses `start_date=af.valuation_date` with monthly frequency and no month-end normalization. If `valuation_date` is mid-month, this produces a 3rd-of-month grid, not the calendar-month-end grid the supporting research identifies as the dominant actuarial default. That is a silent numerical drift vector: horizon dates, year fractions, anniversary alignment, and downstream reporting buckets all move even though the user followed the advertised default path.

**Recommendation:** Make anchoring explicit in the API and canonical form. Add an `anchor="month_end"|"exact_date"` concept (or equivalent constructor split), and do not describe the default as production-typical unless the default actually normalizes to month-end.

## Next steps

- Narrow the Phase 1 contract so portability, hashing, and schedule defaults describe behavior that is actually implementable now.
- Resolve whether Schedule is truly a Phase 1 primitive or an MVP helper until join and termination semantics are fully specified.
- Rework the audit-identity section so typed input provenance is explicit and mechanically derivable.
