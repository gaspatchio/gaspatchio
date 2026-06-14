# Validation Pass — Research Summary (2026-05-02)

This file is the durable summary of the 18-agent parallel validation-pass investigation that informed the spec revision committed 2026-05-02. Individual agent transcripts are machine-local at `/private/tmp/claude-501/.../tasks/*.output`; key findings are inlined below.

## Methodology

Three streams, run in parallel, each preceded by a Phase 0 scoping agent.

- **Phase 0** (3 agents, ~8 min wall): roles inventory → 7-persona shortlist; use-case taxonomy → coverage-probe matrix; library shortlist → SOTA deep-dive targets.
- **Stream 1 — Persona simulations** (7 agents, ~10 min wall): cold-read of the spec by each persona, attempting to model their canonical product.
- **Stream 2 — Coverage probes** (5 agents, ~10 min wall): comparison of the spec against the use-case taxonomy.
- **Stream 3 — SOTA deep-dives** (6 agents, ~10 min wall): pattern extraction from JAX, MLIR, dbt, CVXPY, Bazel, Substrait.

Total ~1.2M tokens, ~30 minutes wall time.

## Stream 1 — Persona findings

### Priya — Senior Pricing Actuary (12 yrs, VA/GMxB, Indexed UL)

**Verdict:** Deterministic profit-test yes. VA pricing committee work no.

**Headline blockers:**
- No stochastic overlay — VA rider charges only make sense under risk-neutral
- No M&E charge on average AV — standard US VA mechanic, no primitive fits
- No dynamic lapse / utilisation hooks — needs cross-period reads spec disallows in transition bodies
- No `is_anniversary` helper documented

**Strongest thing the spec gets right:** the typed `.at(point)` reads solve a real audit problem.

### Marcus — Model Validation (15 yrs, SR 11-7)

**Verdict:** Conditional sign-off, not production-ready as written.

**Headline blockers (all addressed in revised spec):**
- Phase 0 gold-file provenance gate identified but unresolved
- Determinism unstated — same code/data/threads → same bytes? Not contracted
- `track_increments`-conditional fingerprint is a footgun (label changes pass silently when off)
- No floating-point tolerance policy with derivation
- No schema-version field on canonical IR

### Hannah — IFRS 17 Implementation Lead (10 yrs, UK)

**Verdict:** No as platform. Yes as kernel underneath an `gaspatchio-ifrs17` sibling.

**Headline blockers:**
- Cohorts not first-class (IFRS 17.22 mandates annual cohorts)
- Locked-in vs current rate parallelism (VFA OCI option) — no native construct, would need duplicated states
- Loss-component routing on negative CSM — `floor(0)` discards the breach silently
- Coverage unit allocation — no primitive
- Movement analysis is per-step delta, not per-driver attribution

**Action:** Build sibling package `gaspatchio-ifrs17` on top of the kernel.

### Daniel — Stochastic Modeller (8 yrs, VA Hedging, AG 43)

**Verdict:** No for nightly hedging greeks. No for nested stochastic. Brutal yes for AG 43 via cross-join workaround.

**Headline blockers:**
- No scenario axis first-class — cross-join blows row count to billions
- No common-random-numbers reuse
- No shock-channel for pathwise sensitivities (delta requires brute rerun)
- No nested stochastic
- Streaming / out-of-core unaddressed

**Action:** Phase 3+ sibling primitive `stochastic_rollforward(scenarios=N)` with `batch_axes=("scenario","policy")`.

### Aisha — Junior Reserving (2 yrs, exam-tracking)

**Verdict:** Not unsupervised. Improvements wanted on pedagogy.

**Headline blockers:**
- "State" overload (Markov state vs accumulator) confuses textbook readers
- "Semantic IR / closed subset / DSL surface" googles to React tutorials, not actuarial
- No FAM textbook → API mapping
- Rate frequency (monthly vs annual) undocumented
- `.charge(rate)` semantics unclear — textbook expense is usually a $ amount
- No error-message gallery, no debugging story

**Action:** Improved error messages from per-Op `verify()`. Sibling docs page mapping FAM notation to the API.

### Robert — Big-4 External Auditor (18 yrs)

**Verdict:** Would NOT accept for unqualified opinion in current form. Increase substantive testing.

**Headline blockers (all addressed in revised spec):**
- No run manifest binding fingerprint to inputs/version/execution
- No determinism contract across architectures/threads
- Lapse boundary at `≤ 0.0` is an assumption-perturbation attack surface
- No change-control posture (release process, code-signing, fingerprint registry)
- `apply()` escape hatch is unbounded — no whitelist of permitted operations

### Elena — Solvency II Pillar 1 (7 yrs, EU)

**Verdict:** Not for QRT submissions today.

**Headline blockers:**
- No yield curves as first-class objects (now addressed via `Curve` type in §4.12)
- No Volatility Adjustment / Matching Adjustment hooks (addressed via `Curve` constructor)
- No stress-overlay composition — `rf.diff(other)` deferred
- No contract boundary (Solvency II Article 18) — addressed via `contract_boundary` primitive in §4.13
- No Risk Margin / CoC machinery (deferred to `gaspatchio-solvency` sibling)

## Stream 2 — Coverage probes

### Probe A: IFRS 17 mechanics

| Use case | Verdict |
|---|---|
| CSM rollforward (BBA / VFA) | EXPRESSIBLE-NOT-SHOWN (sibling territory) |
| Locked-in vs current discount rate parallel | EXPRESSIBLE-NOT-SHOWN via two states |
| Risk adjustment release pattern | EXPRESSIBLE-NOT-SHOWN |
| Coverage unit allocation | **GAP (upstream)** — needs cohort-aware aggregation |
| Cohort granularity | **GAP (upstream)** — sibling package |
| PAA | COVERED (trivially via `accumulate()`) |
| Onerous contracts / loss component | **GAP** — needs `route_to(states, condition)` primitive |
| Movement analysis disclosure | COVERED via increments |

### Probe B: Living-benefit & exotic riders

| Rider | Verdict |
|---|---|
| GMDB ROP | EXPRESSIBLE-NOT-SHOWN |
| GMDB ratchet | COVERED (§4.7) |
| GMIB step-up | EXPRESSIBLE-NOT-SHOWN |
| GMAB top-up | EXPRESSIBLE-NOT-SHOWN |
| GMWB pro-rata | **GAP** for excess-only branch with conditional gate |
| GLWB ratchet | COVERED with caveats (no-withdrawal bonus interaction with `.ratchet`'s `when=` not exercised) |
| Highest Daily | **GAP** — sub-period state needed |
| IUL P2P single segment | EXPRESSIBLE-NOT-SHOWN |
| IUL multi-segment | **GAP** — needs `.reset_when` |
| IUL monthly averaging | **GAP** — needs running-sum auxiliary state with reset |
| VUL multi-fund | **GAP** for dynamic-N; static-N expressible |
| ULSG shadow | COVERED (§4.11) |
| Joint-life GMDB | DEFERRED (joint decrements outside rollforward) |

### Probe C: Product mechanics

| Feature | Verdict |
|---|---|
| Premium holidays | EXPRESSIBLE-NOT-SHOWN |
| Fund switches / rebalancing | **GAP** — needs atomic multi-state write |
| Free vs chargeable partial withdrawals | EXPRESSIBLE-NOT-SHOWN |
| Surrender charge schedules | COVERED (input-side) |
| Dynamic lapse | EXPRESSIBLE-NOT-SHOWN with caveat (cross-period read needed) |
| Term-conversion option | **GAP** — needs structural product change |
| Joint-life mechanics | **GAP** — needs categorical/status states |
| Par WL dividend / bonus | EXPRESSIBLE-NOT-SHOWN |
| Policy loans | EXPRESSIBLE-NOT-SHOWN |
| Annuitisation election | DEFERRED (phase transition) |
| Maturity mechanics | EXPRESSIBLE-NOT-SHOWN |
| AV-zero-with-persistency | COVERED (§4.11 pattern) |

**Hidden assumptions surfaced:** states are numeric only; one transition writes one state; recurrence shape is fixed (no spliceable IR); lapse is the only termination; captures are this-period-only.

### Probe D: Stochastic & capital

| Workflow | Verdict |
|---|---|
| Multi-scenario projection (1K-10K paths) | EXPRESSIBLE-NOT-SHOWN (cross-join, wrong cost model) |
| Pathwise greeks | **GAP** |
| AG 43 stochastic reserve (CTE 70) | **GAP** — no tail aggregator |
| Solvency II SCR via internal model | **GAP** |
| MRB fair value (US LDTI) | **GAP** |
| EV with TVOG | **GAP** |
| Replicating portfolio fitting | DEFERRED (downstream consumer) |
| ORSA forward-looking | **GAP** — multi-year stepwise unsupported |
| Stress / scenario testing | COVERED (strongest existing area) |
| Dynamic hedging | **GAP** |
| Nested stochastic | **GAP** (explicit non-goal) |

**Architectural fit verdict:** rollforward-as-state-machine is right for one policy. Stochastic projection is `vmap(rollforward, axis=scenario)` plus a reduction. Phase 3 sibling primitive resolves this.

### Probe E: Reporting / audit / governance

| Workflow | Verdict |
|---|---|
| Quarterly close | EXPRESSIBLE-NOT-SHOWN |
| Year-end retrospective remeasurement | **GAP** — no "as-of" replay |
| Pricing-committee submission | EXPRESSIBLE-NOT-SHOWN via GSP-87 |
| Model versioning | COVERED (now via `spec_fingerprint`) |
| A/B model diff | COVERED via manifest-diff |
| Movement analysis by driver | **GAP** — needs `compare_runs(a, b, drivers=...)` |
| Sample test for audit | EXPRESSIBLE-NOT-SHOWN |
| Sensitivity matrix | EXPRESSIBLE-NOT-SHOWN |
| Regulatory submission packaging | **GAP → addressed by manifest in revised spec** |
| Cross-machine bit-reproducibility | **GAP → addressed by `action_key` in revised spec** |
| Audit log | **GAP → addressed by manifest + action_key in revised spec** |
| Approval workflow integration | DEFERRED |

## Stream 3 — SOTA deep-dives

### JAX `lax.scan`

Central pattern: `scan(f, init, xs) → (final_state, ys)` — the canonical functional formulation of state-machine recurrence.

Patterns adopted:
- **Carry vs ys discipline** → state-vs-emitted-output separation (`emit=` field on builder, future Phase 2)
- **vmap over scan** → batch-axis story (`batch_axes` IR field, Phase 1)
- **`lax.cond` / `lax.switch`** → already covered by chained `when()` (PR #99, shipped)
- **PyTrees** → typed `(state, point)` reads structure

Verdict: incremental evolution. Already-aligned IR shape.

### MLIR dialects

Central pattern: federated IR with progressive lowering passes; each "dialect" declares its own Ops, Types, Attributes.

Patterns adopted:
- **Dialect shape** for op vocabulary (typed Op classes with `verify()`) — §7.1
- **Op verifiers** at construction — §7.1, §8.2
- **Pattern rewrites for canonicalisation** — Phase 2

Don't copy: TableGen/C++ ceremony, dialect-explosion, region nesting if shallow.

Verdict: incremental. Borrow shape, not ceremony.

### dbt manifest + lineage

Central pattern: `manifest.json` as compile-time artefact carrying every node's `unique_id`, checksum, dependencies, contracts, exposures.

Patterns adopted:
- **`gaspatchio_manifest.json`** as fingerprint anchor — §9.5
- **`state:modified+`** for selective re-run — §9.5
- **Contracts** for transition-body schema validation — §9.5
- **Exposures** for impact analysis — §9.5

Don't copy: Jinja templating instability, manifest-mutation footguns, version-bump churn.

Verdict: high-leverage, low-risk. Phase 1 inclusion.

### CVXPY reduction chain

Central pattern: same Problem object threaded through a sequence of named, testable `Reduction` passes.

Patterns adopted:
- **Pass chain for `_compile()`** — §8.2 (`Validate → ResolveStateRefs → FoldConstants → AssignCaptureSlots → LowerToPolarsPlugin`)
- **DCP-style construction-time validation** — §7.1, §8.2 (per-Op verify)
- **Atom + escape-hatch tension awareness** — keep named primitives small, document expression bodies as the escape

Don't copy: cryptic DCP-style errors, operator-overload AST.

Verdict: pure internal restructuring; no user-facing change. Phase 1 inclusion.

### Bazel action cache

Central pattern: SHA-256 over the closure of everything that affects output (inputs, command, env, tools, platform).

Patterns adopted:
- **`spec_fingerprint()` / `action_key()` split** — §9.3, §9.4
- **Hermetic boundary at the kernel call** — Phase 1
- **Configuration transitions** for backend + stress overlays — Phase 2+

Don't copy: Starlark-style hermeticity on the user-authored layer; full sandboxing infrastructure.

Verdict: Phase 1 immediate (~50 LOC for action_key); cache infrastructure deferred to Phase 3+.

### Substrait

Central pattern: URI-keyed function identity; functions live in YAML registries with namespace + name + signature suffix.

Patterns adopted:
- **URI-keyed op identity (deferred to Phase 3)** — `gaspatchio.ops.v1.ratchet` survives Python API renames
- **Function registry as separate YAML** — Phase 2+ if op set grows

Don't copy: protobuf-first ergonomics, over-versioning.

Verdict: long-term concern. Reserve `op` slot in IR today; commit to URI later. Non-breaking change.

## Cross-cutting verdict

**Evolve, do not redesign.** All 6 SOTA agents agreed the existing IR shape is structurally sound. The validation pass surfaced specific additions (action_key, manifest, pass chain, per-Op verify, batch_axes, Curve, contract_boundary) and specific deferrals (stochastic sibling, sibling reg-tech packages). No fundamental restart was warranted.

## Scope decisions taken

1. **Stochastic projection** → Phase 3+ sibling primitive
2. **IFRS 17 / Solvency II** → mixed: `Curve` and `contract_boundary` in core, regulatory specifics in sibling packages
3. **Run manifest + action_key** → Phase 1 (the breaking 0.4.0 release)

## Files referenced

- Spec under review: `ref/36-rollforward-redesign/specs/2026-04-30-rollforward-redesign-design.md`
- GSP-95 architecture: `ref/37-dispatch-engine-refactor/ARCHITECTURE.md`
- Original GSP-86 design (superseded): `ref/31-rollforward-api/`
- Polars backend (shipped foundation): `bindings/python/gaspatchio_core/polars_backend/`
