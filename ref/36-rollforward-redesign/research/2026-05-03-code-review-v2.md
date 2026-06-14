---
title: Code Review of v2 Rollforward Redesign Spec
date: 2026-05-03
reviewer: superpowers:code-reviewer (Sonnet, dispatched via Task)
branch: gsp-92-rollforward-redesign
diff_range: 16bc12d..1f9946e
target: ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md (1,293 lines)
verdict: not ready for walkthrough — land C1 and C2 first
---

# Spec Review: Rollforward v2 Design

`ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md`

## Strengths (what to preserve)

- **§1–§3 single coherent story.** Five-line abstract → eight principles → state-machine model. The `(states, points, transitions, schedule, batch_axes)` tuple is named consistently across §3, §6, §7, §8, §9.1, §13.1. No redefinition drift.
- **§4 climb is genuinely progressive.** Each example introduces exactly one concept: §4.3 (negation — *not* a rollforward) → §4.4 (Schedule + Curve) → §4.5 (Table + MortalityTable) → §4.6 (mid-period points) → §4.7 (multi-state ratchet) → §4.8 (cross-state-with-capture in expression body) → §4.9 (the GSP-92 driver) → §4.10/§4.11 (non-VA components) → §4.12/§4.13 (regulatory parallelism via curve substitution) → §4.14–§4.17 (typed-input deep dives). The §4.3 "this is *not* a rollforward case" is a particularly strong move — it pre-empts the "every problem looks like a rollforward" critique without flinching.
- **§9.4 + §17 epistemic honesty is real, not performative.** The "synthetic verdict / real-evidence verdict" table at §17.2 is the single most defensible part of this spec. The column "WEAK / WEAK-NEGATIVE / STRONG-but-not-as-claimed" labels are accurate. §17.5's "what is real / synthetic / pending" three-bucket split is the right framing.
- **§13.0 Phase 0 (gold-file provenance) is correctly elevated.** This is exactly the kind of prerequisite that tends to get smuggled into Phase 1 and then bite. Promoting it to a blocking pre-Phase-1 step is right.
- **Schedule (§4.16) lands clean against the research.** The 5×4×4 matrix in the spec is identical to `research/2026-05-03-schedule-design.md` §"Phase 1 design commitments". Defaults match. Leap-year convention named explicitly. `from_inception` vs `from_calendar_grid` constructor split tracks.
- **§9.5 contract validation collapses cleanly into the per-Op `verify()` discipline.** The choice to drop `manifest.json` and keep contracts as a state-declaration field is internally consistent — the contract lives where it's read, not in a separate artefact.

## Issues — Critical (must fix before walkthrough)

### C1. The lazy/Struct/CSE claim at §7 + §4.2 + §8.3 is plausible but currently unverified, and the spec presents it as load-bearing fact.

The §1f9946e clarification commit added three coupled claims:

1. (§4.2 / line 121, §7 / line 712): "Multiple references to the same rollforward share the underlying plugin call — Polars CSE invokes the kernel once per chunk and emits all requested fields together."
2. (§7 / line 704): "Fields cover every state's eop value, every (state, point) capture, and — when `track_increments=True` — every labelled Op's per-period delta."
3. (§8.3 / line 869): "CSE recognizes the two field extractions share the same plugin sub-tree. The streaming engine sees `is_elementwise=True` on the plugin, processes the LazyFrame in chunks, and invokes the plugin once per chunk."

Two structural problems:

**(a) CSE-folding of plugin calls is plausible behaviour but NOT a Polars stability contract.** Polars CSE is best-effort; it folds identical sub-trees by structural hash, but plugin calls with non-trivial `kwargs` dicts are a known soft spot — particularly when kwargs contain JSON-encoded payloads (which §7 explicitly says they will: `"ir": <serialised IR canonical form>`). The spec asserts CSE-folding as guaranteed behaviour the actuary can rely on. If two references resolve to plugin calls with structurally-equal JSON-encoded `ir` and `captures` kwargs, they *should* fold. But the spec needs to either (i) verify with `lf.explain(engine='streaming')` and document the verification contract, or (ii) explicitly take responsibility for de-duplication on the gaspatchio side rather than relying on Polars CSE.

The current §7.704 line claims: "the compiler walks the user's accessor set before kernel invocation and computes the requested-fields list (the `captures` kwarg) so the kernel emits exactly what's used". This *partially* solves it — but the per-call kwargs construction and the de-dup are conflated. **Two separate questions:** (1) does the compiler build one `captures` list per ActuarialFrame containing the union of every accessor used? Or one `captures` list per `rollforward(...)` call? (2) After lowering, are there N separate `register_plugin_function` calls with N different kwargs, or one call returning a Struct that's then field-extracted N times?

§8.3's plan diagram (line 858–867) implies (2) — a single `plugin_call` Expr that's field-extracted. But §4.2 line 121 talks about "Multiple references … share the underlying plugin call — Polars CSE invokes the kernel once per chunk", which describes (1) with CSE as the deduplicator. **These are different mechanisms, and the spec uses both interchangeably.** Decide: is dedup compile-side (gaspatchio compiler emits one `register_plugin_function` per `rollforward(...)` builder) or runtime-side (multiple emissions, Polars CSE folds them)?

The architecturally cleaner option is compile-side. The compiler holds the builder state, knows every accessor, and emits exactly one `rollforward_plugin(args, kwargs={ir, captures, ...})` call. The user-side `rf["av"]`, `rf["av"].at("post_coi")`, `rf.increment("COI")` are field-extraction Exprs against the *same Python-level Expr object*. Polars CSE then has nothing to do — there's structurally one plugin call by construction. This is what §8.3 implies. But §4.2 line 121 and §7 line 712 lean on "Polars CSE folds". Pick one and rewrite the other.

**(b) `is_elementwise=True` for the rollforward plugin is the right call but its boundary is non-obvious.** Per `core/project.md`, `is_elementwise=True` means "each row's output depends only on that row's inputs". The rollforward kernel takes `(n_periods, n_states)`-worth of inputs *per row* and emits `(n_periods, n_states)`-worth of outputs *per row*. Within a row, there is per-period state-carrying. Polars's elementwise contract is at the row level, not the period level — so this is fine. But the spec should say so explicitly. §7 line 702 says "each row's output depends only on that row's inputs" but doesn't note the per-period state-carrying happens *inside* the row, which is exactly the Polars-streaming-correctness thing the senior implementer needs to know to avoid panicking at the contract.

**Recommendation.** §7's "Struct emission and lazy composition" paragraph needs to:
- Pick compile-side dedup OR runtime CSE, document the chosen mechanism, and remove the other framing from §4.2 and §8.3.
- Add one sentence: "Per-row state-carrying inside the kernel is invisible to Polars; the plugin presents row-elementwise externally."
- Note the verification step (`lf.explain(engine='streaming')` + `POLARS_VERBOSE=1`) as a release gate, per `core/project.md` line 95.

This is the critical structural finding because it's the kind of thing that, if wrong at implementation time, forces a kernel re-architect — exactly what Phase 1 needs to avoid.

### C2. `track_increments`-conditional fingerprinting (§9.1, §12.1) is a known footgun the v1 Codex review flagged, and the v2 framing keeps the trap.

§9.1 line 888: "Labels (when `track_increments=True`; cosmetic-only when `track_increments=False`)". §12.1 line 1056: "changing a label changes the fingerprint when `track_increments=True`; doesn't change when `False`."

The acknowledgement at §16 says the Codex review caught four issues including "fingerprint vs labels" — but the resolution chosen (label hashing depends on `track_increments`) is the same trap, just documented. **Concrete failure mode:** an actuary develops a model with `track_increments=False`, ships it, the IFRS 17 reviewer requests increment attribution, the actuary flips `track_increments=True` to satisfy the review — *and the fingerprint changes*, so the same business logic now has two different `spec_fingerprint`s and the audit chain breaks.

The defensible options are:
- (a) Always hash labels, regardless of `track_increments`. Cost: cosmetic label changes touch the fingerprint. Benefit: deterministic.
- (b) Never hash labels. Cost: increment-attribution changes invisible. Benefit: deterministic.
- (c) Make `track_increments` a separate fingerprintable scope — `spec_fingerprint(track_increments=True)` and `spec_fingerprint(track_increments=False)` are two sibling identities of the same recipe; flipping the flag picks one over the other rather than mutating the hash domain.

(a) is the right answer for an audit-anchored framework. (c) is more flexible if "the increment view of the model is a different artefact" is the framing the user wants. Whichever is chosen, the current "depends on a runtime flag" is exactly the kind of footgun that surfaces 18 months in when an auditor asks why the same code has two fingerprints.

This is critical because §17.4 list of decisions taken does not include this one — so it appears to have been left as v1 wrote it.

## Issues — Important (should fix before walkthrough)

### I1. The §13.1 Phase 1 scope is wide; a senior engineer reading it cold cannot start without coming back for clarifications.

§13.1's "In" list bundles 13 distinct deliverables, including:
- 5 day-counts × 4 calendars × 4 BD conventions (`Schedule`/`Calendar`/`DayCount` typed primitives) — itself ~13 typed objects.
- `Curve` typed primitive with EIOPA RFR loader, parallel shifts, key-rate shifts, both surfaces (typed + column-of-rates).
- `MortalityTable` thin wrapper (committed) + age-basis conversion utilities (`with_age_basis`).
- `spec_fingerprint`, `action_key`, `HermeticContext` stub, `explain()` output.
- 9 Phase 1 Ops with `verify()`, 5-pass compilation chain.
- `ContractBoundary` optional kwarg + canonical-form serialization.
- `batch_axes` IR field + reservation + validation.
- §11 documentation deliverables — *full tutorial rewrite, error-message gallery, FAM-to-API mapping page*.

Two structural concerns:

(a) **`Curve.from_eiopa_rfr(currency="EUR", as_of=..., with_va=True)`** is named in §4.4 and §4.12 worked examples and listed as Phase 1. EIOPA RFR fetching is a non-trivial deliverable — the spec doesn't say whether this is bundled-static-data, live-fetch, file-loader, or all three. §13.1's "Curve typed primitive — both surfaces (typed + column-of-rates)" is too generic. A senior engineer will need to ask: which constructors are Phase 1? At minimum: `from_zero_rates`, `from_eiopa_rfr`, `from_par_rates`, `shift_parallel`, `key_rate_shift`, `spot_rate(t)`, `discount_factor(t)`, `forward_rate(t1, t2)`. That's 6+ public surfaces. EIOPA Smith-Wilson reconstruction (§Agent C in `schedule-design.md`) is specifically *non-trivial* — log-linear interpolation on discount factors, with VA/MA hooks. Either Phase 1 ships a reduced surface (`from_zero_rates` + `shift_parallel` only) and EIOPA loaders move to Phase 2 / a sibling, or §13.1 needs to enumerate which constructors land.

(b) **§11 documentation deliverables in Phase 1 includes** a new tutorial in `gaspatchio-docs` (separate repo), a FAM-to-API mapping page, and a cache-invalidation story page. §14.1 open-question 2 even names this: "Tutorial updates for the new typed-input narrative span this repo and `gaspatchio-docs`. PR coordination?". Cross-repo doc work is real-time-cost in a way Rust kernel work isn't. Leave Phase 1 as kernel + minimum API ref; promote tutorial-rewrite to a parallel PR sequenced after Phase 1 lands. The current bundling lets Phase 1 slip indefinitely on a docs gate.

**Recommendation.** Split §13.1 Phase 1 into:
- §13.1a "Phase 1a — Kernel + IR" (1 PR): typed Ops, pass chain, plugin extension, `spec_fingerprint`, minimal `action_key`, `Schedule`/`Calendar`/`DayCount`, `MortalityTable` wrapper.
- §13.1b "Phase 1b — Curve" (follow-up PR): typed `Curve` with the named constructors, parallel/key-rate shifts. EIOPA loader is its own scoped deliverable — possibly Phase 2 or sibling.
- §13.1c "Phase 1c — Docs" (parallel PR sequence): tutorial rewrites, error-message gallery.

This is "important" not "critical" because it's a phasing/sequencing concern, not an internal-consistency one. But unless it's split, Phase 1 ships in calendar quarters, not within the natural attention envelope of a single design.

### I2. §4.17 `ContractBoundary` is reduced in framing but not in surface.

§17.2's table says `contract_boundary` was reduced from "Pillar 1 blocker" to "convenience for disclosure-pack assembly" with the decision: "keep typed primitive, soften framing". §4.17 is duly softened in language — but the *typed surface* is unchanged. Still has `reason` (free-text) + `regulatory_anchor` (citation key) hashing into `spec_fingerprint`, still has `first_breach_period()`, still composes with `lapse_when_all_non_positive`, still fingerprintable canonical form, still has §7 plugin-kwargs slot and §9.1 canonical-form contribution.

The "convenience for disclosure-pack assembly" framing implies this should live in `gaspatchio-ifrs17` / `gaspatchio-solvency` siblings, not core. §13.4 explicitly names disclosure-pack assembly as sibling territory. So why is `ContractBoundary` in core's Phase 1?

The defensible argument is: "core needs to stop the kernel at the boundary; the typed reason/anchor lets the disclosure pack be assembled siblings-side". Fine — but then the core surface should be just `contract_boundary=mask` (a boolean Expr), and `ContractBoundary(when=, reason=, regulatory_anchor=)` is the sibling-side wrapper. The current spec puts the wrapper in core.

**Concrete tension.** §4.17 hashes `reason` and `regulatory_anchor` strings into `spec_fingerprint`. Two specs with identical computation but different `regulatory_anchor` citation keys produce different fingerprints. Is that desired? If yes — the citation is part of recipe identity (why?) — say so explicitly. If no — the citation is metadata for the disclosure pack, not the recipe — then `reason`/`regulatory_anchor` should not hash into the *core* fingerprint, only the sibling's wrapper-fingerprint.

**Recommendation.** Either (a) move `ContractBoundary` typed wrapper to `gaspatchio-ifrs17` / `gaspatchio-solvency` siblings and keep core's API as `contract_boundary=mask` (boolean Expr only), or (b) explicitly justify why citation strings are part of core recipe identity. The current state is a halfway position the §17 review didn't actually resolve.

### I3. `batch_axes` is reserved as Option C, but the spec contains residual artefacts of the Option-A framing.

§3 line 63 commits to Option C: "Phase 1's Polars backend asserts `batch_axes == ("policy",)` and rejects others. The field exists in the IR today as cheap forward-compat for canonical-form stability when the JAX-backed stochastic primitive lands." Honest framing.

But §9.1 line 884 lists `batch_axes (the tuple)` as a canonical-form component without qualification — meaning a JSON-serialised `("policy",)` is part of the hash. If Phase 1 rejects every other value, the hash contribution is constant and adds noise to the canonical form. Two interpretations:

- **(a) Hash-by-value.** Always include `("policy",)` in the JSON. Then Phase 3's `("scenario", "policy")` will produce a *different* fingerprint for the same recipe — meaning a model authored in Phase 1 cannot have a Phase-3 stochastic re-run with stable identity. Bad.
- **(b) Hash-by-canonical-default.** Include `batch_axes` only if non-default. Then Phase 1 fingerprints don't carry the field, and Phase 3 stochastic runs with a non-default value get a different fingerprint — *which is the right behaviour*: stochastic projection is a different recipe.

§13.1 line 1102 says "hash-by-value (default produces stable hash)" which is option (a). But that's the worse choice for forward-compat: Phase 3 will have to either accept fingerprint churn at the moment of stochastic adoption, or re-author the canonical-form serialiser.

**Recommendation.** Switch to canonical-default hashing. `batch_axes=("policy",)` is the engine-default and produces no contribution to canonical form. Any other value contributes. This way Phase 1 deterministic fingerprints survive into Phase 3 for non-stochastic recipes. The field "exists in the IR today" remains true; the hash contract just becomes "if non-default, include".

### I4. §4.16 Schedule defaults conflict between two paragraphs.

§4.16 line 533: defaults are `convention="unadjusted"` (default), `calendar=Calendar.null()` (default), `day_count=DayCount.one_twelfth()` (default).

§4.16 line 588: "**The default convention (the actuarial reality).** `OneTwelfth` + `NullCalendar` + `Unadjusted` is what US VM-20/VM-21 practice does..."

`research/2026-05-03-schedule-design.md` line 188: "Anniversary roll convention default. Modified-Following when a calendar other than `NullCalendar` is supplied; Unadjusted otherwise."

The research file says the BD-convention default is *context-dependent* — Modified-Following when a real calendar is supplied, Unadjusted with `NullCalendar`. The spec says the default is unconditionally `Unadjusted`. Both are defensible, but the spec drifted from the research's resolution.

**Recommendation.** Either (a) honour the research's context-dependent default and say so in §4.16 ("default convention is `ModifiedFollowing` when a non-null calendar is supplied; `Unadjusted` otherwise — matches `NullCalendar`'s no-business-day premise"), or (b) explicitly reject that resolution with reasoning. The current state is silent drift.

### I5. `Curve` Phase 1 surface vs research evidence is overclaimed for `from_eiopa_rfr` and `with_va`.

§4.14 line 458: `Curve.from_eiopa_rfr(currency="EUR", as_of=date(2026, 5, 3), with_va=True)`.

Real-evidence basis: the Schedule research file confirms EIOPA publishes RFR as integer-year tabular spots, requires Smith-Wilson reconstruction, and that VA/MA mechanics are documented in EIOPA's October 2025 technical doc. **None of this evidence implies that gaspatchio-core ships a live EIOPA loader.** §17.2's `Curve` decision is "keep in core, both surfaces (typed + column-of-rates), reframe as ergonomic SOTA lead". Reframing as ergonomic doesn't itself include shipping live regulatory-data fetchers in core.

**Concrete tension.** `Curve.from_eiopa_rfr(with_va=True)` for the Volatility Adjustment requires applying EIOPA's published VA per currency per as-of date. That's:
- Live HTTP fetch of EIOPA's monthly publication — Phase 1 would gain a network dependency, which is poor production hygiene.
- Bundled-static-data — gaspatchio-core would ship a regulatory-data file with a Last-Updated SHA. Big maintenance cost.
- File-loader expecting the user to pass the EIOPA file — fine, but then `Curve.from_eiopa_rfr(currency="EUR", as_of=...)` is misleading; the call signature should be `Curve.from_eiopa_file(path)`.

**Recommendation.** Either (a) reduce Phase 1 `Curve` constructors to `from_zero_rates` + `from_par_rates` + `shift_parallel` + `key_rate_shift` (no live regulatory loaders); promote `from_eiopa_rfr` (and any equivalent NAIC/Fed loaders) to a `gaspatchio-curves` or `gaspatchio-solvency` sibling. Or (b) explicitly commit to the loader semantics in §13.1 (file-based, bundled-static, or live).

The §4.4 example has `Curve.from_eiopa_rfr(currency="EUR", as_of=af.valuation_date)` as the *first* introduction of the Curve type — making it look casual when it's actually the most production-loaded surface.

## Issues — Suggestions (nice to have)

### S1. §4.18 "Coverage gaps acknowledged but deferred" table omits the GMWB pro-rata gap from validation Probe B.

`research/2026-05-02-validation-pass-summary.md` Probe B identified `GMWB pro-rata` as a GAP "for excess-only branch with conditional gate" and `Highest Daily` as a GAP needing sub-period state. The spec's §4.18 table includes Highest Daily indirectly (sub-period state, Phase 3) but doesn't enumerate GMWB pro-rata. Senior actuaries reading the spec will check this list against their product mix. Add `GMWB pro-rata` as Phase 2 (composes with `.reset_when` + categorical guard).

### S2. The `accumulate()` linear-recurrence path is named in §4.3 and §10.4 but never positioned against `rollforward()` in a comparison table.

A reader new to the framework needs to know when to reach for `accumulate()` vs `rollforward()`. The decision matrix is currently scattered across §4.3 ("term life uses accumulate") and §10.4 ("accumulate is unaffected"). One sentence in §1 or §2 of "accumulate for linear recurrences without state-feedback; rollforward for state-machine recurrences with feedback at the period boundary" would be a small but high-leverage clarification. Also addresses the "every problem looks like a rollforward" concern preventatively.

### S3. The §15 reference list cites `research/2026-05-03-real-evidence-grounding.md`, but the file is not present on disk in the research directory.

`ls ref/36-rollforward-redesign/research/` shows only `2026-05-02-validation-pass-summary.md` and `2026-05-03-schedule-design.md` (both committed). The cited `2026-05-03-real-evidence-grounding.md` is referenced 6 times (lines 12, 1173, 1238, 1242 etc) but doesn't exist in the directory. Either commit the file (it appears to be the basis of §17's whole real-evidence pass), or change the references to point to wherever the real-evidence findings actually live (possibly `/private/tmp/claude-501/...` per §17.6, but those are machine-local). Right now §17's epistemic-honesty argument is grounded in a file the next reader cannot read.

### S4. §17.2 table naming inconsistency — "Yields.jl" vs "FinanceModels.jl".

§4.14 line 475: "Typed yield curves are an ergonomic improvement that the Julia actuarial ecosystem converged on (`Yields.jl` and `FinanceModels.jl`...". §17.2 line 1244: "Yields.jl/FinanceModels.jl validate the typed-curve pattern".

Per the schedule-design research file (line 46): "JuliaActuary — Most mature, but explicitly punts on dates. `FinanceCore.jl` / `FinanceModels.jl` operate on `Float64` time. ... Open tracking issue `FinanceModels.jl#155 — Allow handling of Dates`". The Yields.jl→FinanceModels.jl repository transition is real but means citing both as separate-current-libraries is slightly off; FinanceModels.jl is the successor and Yields.jl is the previous-name. Cosmetic, but external review will catch it.

### S5. `MortalityTable.with_age_basis` is named in §4.15 line 512 but the conversion semantics are not defined.

"`mortality_alb = mortality.with_age_basis("age_last_birthday")` — convert from ANB" — but ALB↔ANB conversion requires a half-year offset assumption (or a more precise actuarial convention; varying by industry/jurisdiction). The conversion is not unique. §4.15's claim "convention conversion utility" implies a single canonical conversion. Either (a) name the convention explicitly (e.g., "uniform-distribution-of-deaths" or "Balducci"), or (b) flag this as Phase 2 and replace with the lookup-only `at(age_basis="age_last_birthday")` form for Phase 1.

### S6. §7.1 `Apply` op is the "escape hatch" but is included in the Phase 1 §12.1 test list without bounding.

Validation pass §17.2 / Robert (Big-4 auditor) flagged `apply()` as "unbounded — no whitelist of permitted operations". §7.1 line 783 has `Apply(target, body, label)` with `body: Expr` — i.e., any semantic-IR expression. §12.1 lists Apply in the per-Op test list, but doesn't say what *boundary* the test enforces. If `Apply` is the escape hatch, what semantic-IR operations are permitted in `body`? The closed-subset framing in §6 (last paragraph, line 684) says "primitives outside it (raw `pl.Expr` calls, autopatched Polars methods, plugin escape hatches) are explicitly Polars-only." Does `Apply.body` accept raw `pl.Expr`? If yes, Apply breaks engine-portability per recipe (a model using `Apply` is no longer Phase-3-JAX-portable). If no, the closed subset needs to be enumerated.

**Recommendation.** §7.1 Apply spec needs one sentence: "`Apply.body` is restricted to the closed semantic subset; raw `pl.Expr` is rejected at compile time. Models using engine-only operators (`pl.max_horizontal`, etc.) per §6 are explicitly Polars-bound." Or alternatively: "`Apply` is Polars-only; using it forfeits Phase-3 portability — which §9.3 detects via the canonical form's engine-binding flag." Either is fine; current silence is the issue.

## Assessment

**Overall:** This is the strongest of the four review passes' output. The §4 climb is the right shape. The §17 epistemic split is honest. The Schedule story aligns with its research. The framing scope-discipline is real — `gaspatchio-ifrs17` / `gaspatchio-solvency` siblings as the right offload, not core bloat.

**The two critical findings (C1, C2) are exactly the kind of thing that won't surface in another LLM review pass.** C1 (lazy/Struct/CSE mechanism conflation) is what the user spotted in the first place that drove the 1f9946e clarification commit; the clarification is *better* than v1 but still has the runtime-CSE-vs-compile-side-dedup ambiguity unresolved. C2 (track_increments-conditional fingerprint) was flagged by Codex against v1, listed in §16 as "caught", and... preserved as-is in v2.

**Verdict on production readiness.** Not yet ready for the user's walkthrough. **Land C1 and C2 first.** They are short, surgical fixes:

- C1: 2 paragraphs in §7 to pick compile-side dedup, plus deletions in §4.2 and §8.3 of the residual CSE framing.
- C2: 1 sentence + 2 line-edits in §9.1 and §12.1 to either always-hash labels or scope-by-`track_increments`.

Importants (I1–I5) can land as a follow-up edit pass; they are real but not structural. Suggestions (S1–S6) are polish.

After C1 + C2 are addressed, this is genuinely walkthrough-ready. The user's framing — "Tight — but amazing" — is achievable with the current spec; it just needs the two structural fixes to be tight in the load-bearing places, not just in the easily-verifiable ones.

---

**Files referenced:**
- `ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md`
- `ref/36-rollforward-redesign/specs/2026-04-30-rollforward-redesign-design.md`
- `ref/36-rollforward-redesign/research/2026-05-02-validation-pass-summary.md`
- `ref/36-rollforward-redesign/research/2026-05-03-schedule-design.md`
- `core/project.md`
- `bindings/python/gaspatchio_core/polars_backend/plugins.py` (existing rollforward_plugin stub)
