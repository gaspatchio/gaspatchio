# Backend portability — what to do next in gaspatchio-core

## 1. Where we are

Two prior assessments (`/tmp/jax_backend_assessment.md`, `/tmp/mojo_backend_assessment.md`) converge on the same picture, and a quick re-verification confirms it:

- `ActuarialFrame.__init__` types its single store as `pl.LazyFrame | None` (`bindings/python/gaspatchio_core/frame/base.py:218`); every mutation goes through `with_columns(...)` on that LazyFrame (`base.py:313–316`, `base.py:496+ with_columns`, `base.py:540+ select`, `base.py:689 filter`, etc.). There is no `Frame` Protocol — the class *is* a Polars wrapper.
- `ColumnProxy._to_expr` returns `pl.col(...)` directly (`column/column_proxy.py:114–116`); arithmetic dunders dispatch into methods that compose `pl.Expr` and wrap the result in `ExpressionProxy(pl.Expr)`. The "expression tree" the user authors is, structurally, a Polars expression tree.
- `_dispatch_autopatch.py` walks `dir(pl.Expr)` at import time and installs `DelegatorDescriptor` for every public attribute (`column/_dispatch_autopatch.py:121–144`). Auto-patching is mechanically married to the Polars surface area.
- The rollforward IR is the one piece that is already portable. `_ir.IR` carries `engine_binding: Literal["portable", "polars"]` derived statically (`_engine_binding.py:66–82`), and `_passes.py` is structured CVXPY-style so a `LowerToJaxKernel` / `LowerToMojoKernel` pass is a sibling slot to `LowerToPolarsPlugin` — not a fork.

The catch: every transition Op (`_ops.py`) holds its arithmetic as raw `pl.Expr` fields (`expr: pl.Expr`, `rate: pl.Expr`, `body: pl.Expr` for `Apply`). The IR's *graph shape* is portable; the leaves of that graph are Polars. `derive_engine_binding` defends the boundary by grepping `str(expr)` for known non-portable signatures (`_engine_binding.py:37–47`) — a string-match defence, not a typed AST. Any second backend has to either accept Polars expression introspection as its input language, or replace those leaves.

## 2. What does "next step" actually mean?

It is *not* a Frame protocol. ActuarialFrame is the wrong place to start: it has many surface methods, broad test exposure, accessor caches, a tracing system, and a lazy-schema generation counter. Touching it first means paying for portability before any backend asks for it.

It is *not* a wholesale neutral expression IR for column algebra. That's the eventual goal but it is multi-PR work and disturbs `gsp-92-rollforward-redesign`.

The next step is the **smallest piece that makes every following piece cheaper**. Concretely: turn the IR's portability boundary from a *string-grep heuristic* into a *typed leaf-expression IR*, kept small enough to lower from Polars today and to lower to a second backend tomorrow. The Op vocabulary stays. What changes is what lives in the `expr` / `rate` / `body` slots.

## 3. Options

### Option A — Frame Protocol first

Extract `Frame` as a Protocol covering ~12 methods (`with_columns`, `select`, `filter`, `join`, `rename`, `drop`, `sort`, `collect`, `columns`, `schema`, `lazy`, `pipe`). Implement `PolarsFrame(Frame)` as today's behaviour; reroute `ActuarialFrame.__df` to a `Frame`.

- **Blast radius**: large. Every method in `frame/base.py:496–958` and the accessors in `accessors/`, `column/_dispatch_*` rely on the LazyFrame surface. The tracing path (`base.py:309–316`) and schema-generation counter both inspect `pl.LazyFrame` semantics directly.
- **Value**: low without a second backend implementation to validate the Protocol. You'd be designing against zero non-Polars consumers.
- **Risk**: high — touches the audit-relevant tracing path and `gsp-92`'s working tree.

### Option B — Typed leaf-expression IR (recommended starting shape)

Replace `pl.Expr` fields on Ops with a closed `LeafExpr` ADT — `Col`, `Lit`, `BinOp`, `UnaryOp`, `Where`, `Lookup`, `Cast`, `ScheduleRef`, `CurveRef`. Provide:

- `to_polars(leaf: LeafExpr) -> pl.Expr` (replaces what users are implicitly relying on today).
- `from_polars(expr: pl.Expr) -> LeafExpr | None` — best-effort lifter that returns `None` for non-portable expressions, replacing the string-match in `derive_engine_binding`.
- A tagged escape leaf — `OpaqueExpr(body: pl.Expr)` — that pins `engine_binding = 'polars'` by *type*, not by stringified inspection.

`engine_binding` becomes a property of the IR's *type structure*: an IR is `'portable'` iff every leaf is non-`OpaqueExpr`. No grep, no false positives, no false negatives.

- **Blast radius**: contained to `rollforward/_ir.py`, `_ops.py`, `_engine_binding.py`, `_passes.py`, and the rollforward builder. ActuarialFrame and ColumnProxy don't change shape.
- **Value**: high. It (a) moves the audit invariant from "we grep strings" to "the type system enforces it"; (b) gives the next backend a typed AST to lower from; (c) makes mixed-binding IRs *representable* — an Op can carry a `LeafExpr` for the portable backends and an `OpaqueExpr` Polars fallback alongside it, when needed; (d) survives without changing user-facing code today, because users still write `pl.Expr` and the builder lifts via `from_polars`.

### Option C — Per-backend Apply bodies

Generalise `Apply.body: pl.Expr` to `Apply.bodies: dict[BackendName, Callable | pl.Expr]`. Backends pick the body that matches.

- **Blast radius**: small.
- **Value**: real, but only useful *after* there is a second backend. Today it adds optionality nobody consumes.
- **Recommendation**: defer until Option B is in. Then it falls out as a one-Op extension.

## 4. Recommendation — start with Option B

Ship a typed leaf-expression IR. Concrete API surface (illustrative, not final):

```python
# rollforward/_leaf.py — new file
@dataclass(frozen=True)
class Col: name: str
@dataclass(frozen=True)
class Lit: value: float | int | bool
@dataclass(frozen=True)
class BinOp: op: Literal["+", "-", "*", "/", "**", "==", "<", ">", "<=", ">=", "&", "|"]; lhs: LeafExpr; rhs: LeafExpr
@dataclass(frozen=True)
class UnaryOp: op: Literal["-", "~"]; operand: LeafExpr
@dataclass(frozen=True)
class Where: cond: LeafExpr; then_: LeafExpr; else_: LeafExpr
@dataclass(frozen=True)
class Lookup: table: TableRef; key: LeafExpr        # MortalityTable.at, Curve lookup
@dataclass(frozen=True)
class ScheduleRef: which: Literal["dt", "year_fractions"]
@dataclass(frozen=True)
class OpaqueExpr: body: pl.Expr; reason: str       # the type-tagged escape hatch

LeafExpr = Col | Lit | BinOp | UnaryOp | Where | Lookup | ScheduleRef | OpaqueExpr
```

Then in `_ops.py`, `Add.expr`, `Charge.rate`, `Grow.rate`, `Ratchet.to`/`when`, `DeductNAR.coi_rate`/`death_benefit`, `Apply.body` change from `pl.Expr` to `LeafExpr`. The builder (`_builder.py`) accepts `pl.Expr` from users (no API break) and runs `from_polars`. If the lift fails, the leaf is wrapped as `OpaqueExpr(body, reason="autopatched .gp namespace")` rather than rejected.

`derive_engine_binding(ir)` reduces to:

```python
def derive_engine_binding(ir: IR) -> EngineBinding:
    return "polars" if any_opaque(ir) else "portable"
```

Two pages of code, one type discriminant, no string matching.

### Why this is the right first step

- **Load-bearing for everything downstream.** Option C falls out trivially. A future Frame Protocol (Option A) can lean on the same `LeafExpr` for column-algebra ops once anyone wants it.
- **Auditor story strengthens.** The current security/audit posture relies on the rollforward IR being inspectable. Today, "is this rollforward portable?" is answered by `str(expr)` containing a known substring. After this change it's a constructive proof at the type level. That is *more* auditor-friendly, not less.
- **Backwards compatibility intact.** Users still write `af.av * (1 - af.qx)`. The builder lifts; nothing in `frame/`, `column/`, or the user's code moves.
- **Doesn't destabilise gsp-92.** Changes are confined to `rollforward/_ir.py`, `_ops.py`, `_engine_binding.py`, plus a new `_leaf.py`. The Polars lowering pass already exists; it changes from "consume `pl.Expr` directly" to "consume `LeafExpr` and call `to_polars`" — a thin adapter on the same path.

## 5. Sequence (post-Option-B)

In order of decreasing leverage / increasing blast radius:

1. **Per-Op backend lowerings as siblings.** Add `LowerToNumPyKernel` (cheapest non-Polars target — proves the IR is genuinely portable, no GPU, no new deps in CI). The point is not NumPy as a production backend; it's the smallest possible second consumer that *forces* `LeafExpr` to be honest. If NumPy lowering exposes a leaf the IR can't represent, the IR is wrong; better to discover that pre-JAX.
2. **Per-backend Apply bodies (Option C).** Now that there's a second lowering, `Apply.bodies: dict[Backend, LeafExpr | Callable]` becomes a concrete, useful generalisation rather than speculative optionality.
3. **Mixed-backend execution contract.** Define what it means for an IR to have some Ops portable and some `OpaqueExpr`. The probable answer is "the whole IR runs on Polars whenever any Op is opaque" — i.e. no per-Op dispatch. Document that explicitly; the alternative (run portable Ops on JAX, opaque Ops on Polars, hand state across) is a fanout of complexity the framework does not need.
4. **Frame Protocol (Option A) — only if a non-Polars consumer demands it.** Extract `Frame` when there's a concrete second implementer (a JAX `Frame`, a NumPy `Frame`). Designing it now without a consumer produces a Protocol shaped like the LazyFrame surface — the worst of both worlds.
5. **Column-algebra IR — last.** Extending `LeafExpr` upward into ColumnProxy / ExpressionProxy (`column/column_proxy.py`, `column/expression_proxy.py`) is the largest move. It only pays off after multiple backends are live and the rollforward IR's leaf vocabulary has stabilised under real lowering pressure.

## 6. Anti-recommendations

- **Don't write a "Frame" Protocol first.** Without a second implementer to constrain it, you'll mirror `pl.LazyFrame`'s surface and lock in Polars assumptions under a different name. Worse, you'll touch `frame/base.py:216–2293` and the tracing system before you need to.
- **Don't replace auto-patching with a hand-curated portable subset right now.** `_dispatch_autopatch.py` is structurally Polars-coupled, but its replacement is a multi-quarter ergonomics question. The audit story doesn't depend on it (the autopatch surface only touches user-authored expressions, which today already flip `engine_binding` to `'polars'`). Removing autopatch before there's a second backend just deletes ergonomics for no portability gain.
- **Don't try to make `pl.Expr` itself the neutral IR by writing a "JAX visitor over `pl.Expr`".** The `pl.Expr` AST is a private, version-coupled Polars internal. Using it as an interchange format ties gaspatchio's release cadence to Polars' internal refactors. The IR should *consume* `pl.Expr` (lift), never *be* `pl.Expr`.
- **Don't generalise `engine_binding` into a multi-backend enum (`'portable' | 'polars' | 'jax' | 'mojo'`) before a second backend exists.** Today the binary tells you "can this IR be lowered to anything other than Polars, yes/no". That's the only question worth answering. A multi-valued binding is premature commitment.
- **Don't introduce per-Op backend negotiation (every Op announces which backends it supports).** The rollforward kernel runs as a unit; mixed-backend execution buys you complexity without runtime wins. Keep the binding IR-wide.
- **Don't break the user-facing `pl.Expr` ergonomic.** "Vectorised Polars expressions for actuaries" is the selling point. The lift `from_polars` keeps it. Asking users to write `LeafExpr` directly would be a regression dressed up as portability.

## 7. Open questions

- **What does `Lookup` mean for `MortalityTable.at` and `Curve.spot_rate`?** Today these are typed inputs whitelisted in `_engine_binding.py`. They embed Polars-specific lookup semantics. Defining `Lookup` cleanly may require pulling those types' implementations through the same lift/lower split — bigger than just "leaf IR".
- **How wide is the autopatched `.gp.` namespace in real models?** If the codebases under `gaspatchio-models/` use it heavily, the `OpaqueExpr` rate in practice will be high and the "portable" binding will rarely fire — meaning the typed IR mostly serves the audit story, not actual second-backend execution. Worth measuring before committing to Option B's downstream sequence.
- **Does the rollforward audit story already commit to Polars `pl.Expr` introspectability as a load-bearing invariant?** If `docs/security-plan` (`d1b09e4`) names `pl.Expr` specifically, Option B *strengthens* the invariant (typed AST vs string match) but *changes* it — auditors should be told before the swap.
- **Do the PyO3 kernels (`bindings/python/src/vector.rs` — `fill_series`, `accumulate`, `list_pow`, `list_clip`, `list_conditional`, `rollforward`) need to be addressable from a non-Polars lowering?** They're individually portable but registered via `#[polars_expr]`. A cleaner answer is to expose them via a second registration (raw FFI fn) that any lowering can call, but that's a Rust-side question this report didn't dig into.
