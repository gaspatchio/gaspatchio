# 41 — Backend portability research

Research spike (May 2026) investigating how feasible it is to swap or augment the current Polars backend with JAX or Mojo, what the next gaspatchio-internal step would be to make alternative backends more achievable, and where the highest-leverage point is for stochastic / nested-stochastic actuarial workloads.

Linear: GSP-99

## Headline findings

1. **The rollforward IR is the only existing portable seam.** `ActuarialFrame` is hardcoded `pl.LazyFrame` (`frame/base.py:218`); `ColumnProxy._to_expr` returns `pl.col(...)` directly (`column/column_proxy.py:114`); `_dispatch_autopatch.py` walks `dir(pl.Expr)`. Only the rollforward IR (`rollforward/_ir.py`, `_ops.py`, `_engine_binding.py`) is structurally portable today.

2. **"Swap the backend" is the wrong framing.** Polars is a lazy execution engine + ETL layer; JAX is a tracing + autodiff library; Mojo is a kernel language. The realistic move is kernel-level acceleration plugged into the IR, not a wholesale backend swap.

3. **The leverage point for stochastic workloads is the rollforward kernel itself, with scenarios as a tensor axis instead of replicated rows.** Today's `with_scenarios()` cross-joins to `(n_policies × n_scenarios, k+1)` rows. The IR already reserves `batch_axes` for this (`_ir.py:11`).

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
