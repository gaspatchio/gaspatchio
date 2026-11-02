# 41 — Backend portability research

> **Superseded in part — 2026-09-08. Read this before the findings below.**
>
> This research is dated **2026-05-11**. Three of its load-bearing premises have since become
> false, and a reader who takes them at face value will reach the wrong conclusion about what
> this codebase can and cannot do. The text below is kept exactly as written — it is the record
> of a position held at a time, and most of its judgement still stands. This note marks what is
> now false and points at what replaced it. **Nothing beneath this note has been edited.**
>
> ### 1. "Rectangular by construction" is false — the kernel has a first-class ragged path
>
> `41-jax-backend-assessment.md` §3 says the Rust kernel "asserts every input list column has
> `len == n_periods` for every row (`rollforward.rs:305-312`); it is rectangular by
> construction", and `41-mojo-backend-assessment.md` §3 repeats it ("currently enforced by
> `rollforward.rs:305-312`").
>
> Re-derived 2026-09-08 in `core/src/polars_functions/rollforward.rs`:
> `per_policy_lengths_arg: Option<usize>` (:60) carries each policy's authoritative horizon —
> read at :411, and used at :563 as the first-priority source of that row's period count. The
> uniform-length check at :466 is conditional on `require_uniform` (:69), which
> `bindings/python/gaspatchio/rollforward/_passes.py:378` sets only when the schedule is **not**
> a `per_policy_grid`; :389 threads the per-policy lengths in when it is. The kernel's own
> refusal message (:492) **recommends** the ragged path: *"If policies genuinely have different
> horizons, use a per-policy grid (`af.projection.set(..., per_policy=True)`, or
> `Schedule.from_per_policy_grid`) so each policy carries its own length."* Raggedness is a
> declared, supported shape — not an absent pattern. Jagged per-policy timelines became the
> **default** projection shape in v0.4.0 (merged 2026-06-14), a month after these documents were written.
>
> ### 2. "That pattern doesn't exist in this codebase" is false
>
> Same document, same section, on per-policy variable `n_periods`. Measured 2026-09-08 on a
> two-policy frame differing only in `term_years` (10 and 20), annual frequency:
>
> ```
> until='maximum_age'  until_value=60            len(month) per policy: [21, 21]   n_periods: [20, 20]
> until='term_years'   until_value='term_years'  len(month) per policy: [11, 21]   n_periods: [10, 20]
> ```
>
> The second row is a jagged frame built through the ordinary author-facing API. The jax
> assessment's own §6 asks exactly the right question — *"Is `Schedule` always rectangular in
> practice, or do users build per-policy schedules with different `n_periods`?"* — and its §3
> answers it the wrong way.
>
> **What this costs a second engine is open, and is not settled here.** A ragged timeline does
> not fit a rectangular array, and the 2026-09 JAX spike ran three policies on one shared
> 120-period grid and explicitly did not exercise per-policy jagged timelines. The evidence
> above is an input to that decision, not the decision.
>
> ### 3. The architecture these documents reason about has been replaced
>
> Both assessments rest on there being no neutral AST: *"the expression tree the user builds is
> literally a Polars expression tree… There is no neutral AST to retarget"*
> (`41-jax-backend-assessment.md` §3), and the same picture underwrites headline finding 1 below
> and `41-compatibility-next-step.md` §1.
>
> An op-tree now exists, one layer above the rollforward IR, at the column layer these documents
> ranked hardest and last. The `OpNode` union in
> `bindings/python/gaspatchio/frame/graph/ir.py` closes over **seven** node types — `Col`,
> `Lit`, `BinOp`, `Call`, `WhenThen`, `State`, `EngineNative` — and the `assert_never` that
> ends `walk`'s `match` in the same module fails type-check on an eighth. Every
> `ColumnProxy` operator emits a semantic node (`column/column_proxy.py:114`, `_binary`); the
> Polars expression is derived later, by lowering. `frame/lowering/polars.py` registers **55**
> lowerings after `ensure_rules_loaded()` (verified 2026-09-08, polars 1.42.1). A JAX spike in
> 2026-09 lowered five ops — and two more it added — bit-exactly against Polars in a process
> where `polars` and `gaspatchio` were both unimportable (the assumption table was supplied
> out of band; the tree names artefacts and does not carry them).
>
> Note precisely what did **not** change: `ColumnProxy._to_expr` still returns
> `pl.col(self.name)` (`column_proxy.py:156`) and `ActuarialFrame` still stores a
> `pl.LazyFrame` (`frame/base.py:619`). The documents' *observations* about those two lines
> remain true; the conclusion drawn from them — that there is therefore nothing but a Polars
> expression tree to retarget — does not.
>
> ### What still stands, and must not be discarded
>
> - **`41-compatibility-next-step.md`'s anti-recommendations.** *"Don't break the user-facing
>   `pl.Expr` ergonomic"* is still the position. *"Don't try to make `pl.Expr` itself the neutral
>   IR"* is **vindicated**: the op-tree *consumes* `pl.Expr` through
>   `frame/lowering/ingress.py:119` `to_node`, which turns it into an `EngineNative` node — the
>   tree never *is* a `pl.Expr`. *"Removing autopatch before there's a second backend just
>   deletes ergonomics for no portability gain"* is a warning whose **condition has moved**, not
>   one that has been struck: a second-engine path is now demonstrated, though no second engine
>   ships. Read it as conditional, not as void.
> - **The diagnosis of the rollforward IR itself.** Op fields are still `pl.Expr`
>   (`rollforward/_ops.py:73` and following) and `derive_engine_binding` still defends the
>   boundary by string-matching `str(expr)` (`rollforward/_engine_binding.py`). That section of
>   `41-compatibility-next-step.md` describes today's code accurately.
> - **"Swap the backend is the wrong framing"** (headline finding 2) and the Mojo document's
>   ecosystem caveats. Nothing here tests them; nothing here refutes them.
>
> ### What happened instead of the recommended sequence
>
> The typed `LeafExpr` IR (sequence item 1, `41-compatibility-next-step.md` Option B) was
> **never built** — there is no `LeafExpr` anywhere in the package. The op-tree was built
> instead, at the column layer that document ranked *last*, and it kept the shape of Option B's
> best idea: a type-tagged escape hatch. `OpaqueExpr(body, reason)` as proposed is
> `EngineNative(engine, text, deps)` as shipped. Sequence item 6 — `for_each_scenario` plus a
> bounded aggregator API — shipped in v0.4.0.
>
> ### Where the current position is written down
>
> - `spec/graph-artifact/` — the shipped, normative account of the op-tree artifact.
> - `bindings/python/gaspatchio/frame/graph/ir.py` — the seven node types and their contract.
> - Two decisions of 2026-09-07: the op set is the single source of truth, and the proxy
>   surface is generated from it, not from `dir(pl.Expr)`; and an op's cross-engine contract
>   asserts *value* to a stated tolerance, not bitwise identity.
>
> The four files under `specs/` and `plans/` (GSP-100 / GSP-101) are **not** superseded by any of
> the three points above: they concern the scenario and aggregation layers, not the expression
> layer, and both designs shipped — GSP-101's aggregator layer as the v0.2 surface,
> `ScenarioRun` / `for_each_scenario` by v0.4.0.

Research spike (May 2026) investigating how feasible it is to swap or augment the current Polars backend with JAX or Mojo, what the next gaspatchio-internal step would be to make alternative backends more achievable, and where the highest-leverage point is for stochastic / nested-stochastic actuarial workloads.

Linear: GSP-99

## Headline findings

1. **The rollforward IR is the only existing portable seam.** `ActuarialFrame` is hardcoded `pl.LazyFrame` (`frame/base.py:218`); `ColumnProxy._to_expr` returns `pl.col(...)` directly (`column/column_proxy.py:114`); `_dispatch_autopatch.py` walks `dir(pl.Expr)`. Only the rollforward IR (`rollforward/_ir.py`, `_ops.py`, `_engine_binding.py`) is structurally portable today.

2. **"Swap the backend" is the wrong framing.** Polars is a lazy execution engine + ETL layer; JAX is a tracing + autodiff library; Mojo is a kernel language. The realistic move is kernel-level acceleration plugged into the IR, not a wholesale backend swap.

3. **The leverage point for stochastic workloads is the rollforward kernel itself, with scenarios as a tensor axis instead of replicated rows.** Today's `with_scenarios()` cross-joins to `(n_policies × n_scenarios, k+1)` rows. The IR already reserves `batch_axes` for this (the `batch_axes` field on `IR` in `rollforward/_ir.py`).

4. **JAX wins for the scenario-axis surface.** `vmap`-over-`scan` is exactly the operators needed; autodiff is the path to LSMC and Greeks (Mojo has no autodiff in May 2026).

5. **The next gaspatchio-internal step is a typed leaf-expression IR — NOT a Frame Protocol.** Replace `pl.Expr` fields on rollforward Ops with a closed `LeafExpr` ADT.

6. **Polars streaming does NOT bound memory for the cross-join scenario pattern** (empirically verified). Per-row footprint is ~110-125 KB; on a 16 GB Mac the practical limit is ~200 scenarios at 1k policies × 240 months. The lazy-`with_scenarios` fix (commit `9824f2d`) gives a 10-21% RSS reduction but doesn't change the linear-growth shape — the in-memory streaming sink dominates.

## Reports

| File | What it covers |
|---|---|
| [`41-jax-backend-assessment.md`](41-jax-backend-assessment.md) | Three-layer architecture map (ActuarialFrame, ColumnProxy, rollforward IR); per-component effort buckets for a JAX backend; subset proposal for v0.1 as a rollforward accelerator |
| [`41-mojo-backend-assessment.md`](41-mojo-backend-assessment.md) | Mojo's plugin-extension story for Polars (May 2026); ecosystem-maturity caveats; recommendation to plug Mojo kernels into the existing Rust+Polars stack rather than swap the backend |
| [`41-compatibility-next-step.md`](41-compatibility-next-step.md) | Where to spend internal engineering effort to make ANY future backend cheaper to integrate; the typed `LeafExpr` IR recommendation; what NOT to do (don't write a Frame Protocol first) |
| [`41-scenario-memory-design.md`](41-scenario-memory-design.md) | Audit of `with_scenarios` and `batch_scenarios`; analysis of why streaming can't bound memory; alternative patterns; recommendation for `for_each_scenario(af, scenarios, model_fn, agg=...)` API with break-glass full-grid mode |
| [`41-scenario-scaling-empirical.md`](41-scenario-scaling-empirical.md) | Subprocess-isolated memory-scaling test on the L5 typed VA model; matched-pair before/after for the lazy-`with_scenarios` fix; verdict on Polars streaming |
| [`41-scenariorun-rollforward-composition.md`](41-scenariorun-rollforward-composition.md) | How the proposed `ScenarioRun` plan composes with the rollforward kernel — outer-loop / model-logic / inner-kernel layering, audit chain, compile reuse, JAX-backend forward compatibility |
| `41-scenario-scaling-results-eager.json` | Raw per-tier results, eager `with_scenarios` (pre-fix) |
| `41-scenario-scaling-results-lazy.json` | Raw per-tier results, lazy `with_scenarios` (commit 9824f2d) |

## Recommended sequence (status as of May 2026)

1. **Land the typed `LeafExpr` IR.** Confined to `rollforward/_ir.py`, `_ops.py`, `_engine_binding.py`, `_passes.py`, `_builder.py` + new `_leaf.py`. Backwards compatible.
2. **Add `LowerToNumPy` as the smallest possible second consumer** to prove the IR is genuinely portable.
3. **Per-backend `Apply.bodies`** once a second lowering exists.
4. **Corpus survey** of `tutorials/` and `gaspatchio-models/` for portable-subset coverage.
5. **`LowerToJax` for `batch_axes=('scenario','policy')`** — the leverage point for stochastic workloads.
6. **`for_each_scenario` + bounded aggregator API** — independent of the backend work; the cure for the cross-join memory problem on the existing Polars stack.
7. **Frame Protocol — only if a non-Polars consumer demands it.** Designing without a consumer locks in Polars assumptions.

## Anti-recommendations

- Don't write a `Frame` Protocol first.
- Don't replace auto-patching before there's a second backend.
- Don't try to make `pl.Expr` itself the neutral IR.
- Don't pursue full nested Monte Carlo wholesale GPU dispatch — memory math doesn't work; LSMC is what production uses.

## Status

Research complete. Two follow-up Linear tickets:
- GSP-99 — backend portability synthesis (this directory)
- [TBD] — `for_each_scenario` API design + implementation

No work-in-flight from this research; commit `9824f2d` is the only code change directly produced (lazy `with_scenarios`).
