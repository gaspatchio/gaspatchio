# JAX Backend Feasibility for gaspatchio-core

> **Superseded in part — 2026-09-08.** This assessment is dated **2026-05-11** and is kept
> exactly as written; nothing beneath this note has been edited. Three of its claims are now
> false. Full evidence in [`README.md`](README.md); the short form:
>
> - **§3, "Ragged lists": *"it is rectangular by construction"* is false.** The kernel has a
>   first-class ragged path. `core/src/polars_functions/rollforward.rs` carries
>   `per_policy_lengths_arg` (:60) as each policy's authoritative horizon, and the uniform-length
>   check (:466) is conditional on `require_uniform` (:69), set only for calendar-grid / inception
>   schedules (`rollforward/_passes.py:378`). The kernel's refusal message (:492) *recommends*
>   the per-policy grid.
> - **§3: *"that pattern doesn't exist in this codebase"* is false.** Per-policy variable
>   `n_periods` is the ordinary case, and has been the **default** projection shape since v0.4.0
>   (merged 2026-06-14). Measured 2026-09-08 on two policies differing only in `term_years` (10, 20):
>   `until='maximum_age'` gives `month` lengths `[21, 21]`; `until='term_years'` gives
>   `[11, 21]`. §6's open question — *"do users build per-policy schedules with different
>   `n_periods`?"* — is the right question, and §3 answers it the wrong way. **What raggedness
>   costs a second engine is open and is not settled here.**
> - **§3, "Column proxy generates `pl.Expr`, not an IR": *"There is no neutral AST to
>   retarget"* is false.** The `OpNode` union in `frame/graph/ir.py` closes over seven node
>   types, `walk`'s `match` in the same module ends on `assert_never`, and
>   `frame/lowering/polars.py` holds 55 registered lowerings. The
>   observation the sentence rests on is still true — `ColumnProxy._to_expr` does still return
>   `pl.col(...)` (`column_proxy.py:156`) — but every operator now emits a semantic node
>   (`column_proxy.py:114`) and the Polars expression is derived by lowering afterwards.
>
> **What stands.** The three-layer architecture map, the effort buckets for the kernels, the
> `Apply`-escape-hatch analysis, and the string-key / `map_batches` friction are all still
> accurate descriptions of the rollforward path — Op fields are still `pl.Expr`
> (`rollforward/_ops.py`) and `derive_engine_binding` still string-matches. §5's judgement that
> unifying backends needs a neutral expression IR, and that it is the largest refactor in the
> codebase, is what actually happened.

## 1. Architecture map

The codebase already has a deliberate "portable vs polars" split. That seam is the most important fact for this assessment — the authors have anticipated alternative backends, but only at one of three layers, not all three.

The three layers where Polars is hardcoded, from top down:

**Layer A — `ActuarialFrame` storage.** `bindings/python/gaspatchio_core/frame/base.py:218` types `self.__df: pl.LazyFrame | None`, and `with_columns` (line 496+) and `collect()` round-trip through `pl.LazyFrame` directly. The frame *is* a Polars LazyFrame; there is no abstract `Frame` interface.

**Layer B — column proxy / expression dispatch.** `bindings/python/gaspatchio_core/column/column_proxy.py:114` defines `_to_expr -> pl.Expr` returning `pl.col(self.name)`. Operator overloads (`__add__`, `__mul__`, etc.) all go through `column/_dispatch_execution.py`, which produces `pl.Expr` trees. The dispatch layer is *aware* of Polars-specific concerns (list shape, list-eval shimming, list_pow/list_clip routing) — it is not a backend-agnostic IR. Auto-patching at `column/_dispatch_autopatch.py` walks `pl.Expr`'s methods directly. This layer is fundamentally Polars-shaped.

**Layer C — rollforward IR.** This is the only genuine portability seam. `bindings/python/gaspatchio_core/rollforward/_ir.py` defines a frozen dataclass IR with typed Ops (`_ops.py`: nine Ops — `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`, `DeductNAR`, `Ratchet`, `Floor`, `Apply`). `_engine_binding.py:9-22` declares an explicit closed-subset whitelist of Polars expressions safe to lower to "portable backends (JAX, future engines)" — the comment names JAX. `derive_engine_binding(ir)` returns `'portable'` only when every Expr passes the whitelist. The Rust kernel (`core/src/polars_functions/rollforward.rs:145`) consumes `RollforwardKwargs` (a JSON-decoded payload), and `_canonical.py:54` produces a `json.dumps`-able dict — meaning *the rollforward IR is already engine-agnostic by design*, with the Rust kernel being one consumer.

**PyO3 entry points** are six `#[polars_expr]` functions in `bindings/python/src/vector.rs`: `fill_series`, `floor`, `round`, `accumulate`, `list_pow`, `list_clip`, `list_conditional`, `rollforward`. Each one is a leaf — none of them recursively calls back into Polars. So they are individually portable as pure-Rust callables; what binds them to Polars is the registration mechanism, not the kernels.

The seam, then, is asymmetric: rollforward already has a portable IR; everything else (assignments, conditionals, list operations, assumption lookups) is a Polars-expression tree with no IR layer.

## 2. Mappable

**Trivially mappable to JAX.** Layer C transitions modulo Apply: each Op is essentially a small typed AST node. `Add` → `s = s + amount`, `Charge` → `s = s * (1 - rate)`, `Grow` → `s = s * (1 + rate * dt)`, `Floor` → `s = jnp.maximum(s, value)`, `Ratchet` → `jnp.where(when, jnp.maximum(s, to), s)`, `DeductNAR` → `s = s - coi * (db - s)`. The per-period Op walk maps cleanly onto a `jax.lax.scan` body where the carry is the per-row state vector and the per-period inputs come from rectangular `[n_rows, n_periods]` arrays.

**Accumulate** (`core/src/polars_functions/accumulate.rs`) is a textbook linear recurrence and ports to `lax.scan` in ~10 lines.

**Elementwise list ops** — `list_pow`, `list_clip`, `list_conditional` (`vector.rs:47-95`) are dense `[n_rows, n_periods]` arithmetic. JAX wins here: these are exactly the kernels JAX vectorises and JIT-fuses well.

**`af.av * af.qx`-style assignments** translate directly if you treat each per-row list column as a 2D `jnp.ndarray`. Boolean masks via `to_boolean_expr` (`polars_backend/masks.py`) become `jnp.where`.

**`Schedule.year_fractions_expr`, `Curve.spot_rate / discount_factor / forward_rate`, `MortalityTable.at`** are all on the closed-subset whitelist (`_engine_binding.py:9-22`). Their methods produce `pl.Expr`, but the data they encode (year fractions, discount factor curves, mortality rates) is numeric and table-shaped — straightforward to expose as raw arrays/interpolators in JAX.

**Assumption lookups, pre-encoded path.** `core/src/assumptions/key_encoder.rs` already encodes string categorical dimensions to integer indices; `array_storage.rs` is a flat-array indexing backend. That maps to `jnp.take` / fancy indexing on a precomputed table tensor.

## 3. Friction

**`ActuarialFrame` is a `pl.LazyFrame`, not an abstraction.** Layer A is the biggest mechanical obstacle. There is no `Frame` Protocol — every method body either calls `self._df.with_columns(...)` or `self._df.collect()`. A JAX backend cannot share `ActuarialFrame`; you'd either need (a) a parallel `JaxActuarialFrame` class with the same method surface, or (b) a refactor introducing a `FrameBackend` Protocol that both Polars and JAX implement. Neither is small.

**Column proxy generates `pl.Expr`, not an IR.** Layer B is the second-biggest issue. `ColumnProxy._to_expr` returns `pl.col(...)`. `__add__` produces `ExpressionProxy(pl.Expr)`. The "expression tree" the user builds when they write `af.av = af.av_init * (1 - af.qx)` is *literally* a Polars expression tree. There is no neutral AST to retarget. Options:
- Replace the proxy's output type with a small DSL AST that lowers to either Polars or JAX (significant refactor).
- Build a parallel `JaxColumnProxy` (duplication).
- Use the closed-subset rule from `_engine_binding.py` and write a Polars-Expr-string parser that re-emits JAX (fragile — the whitelist comment notes string-form parsing has known false-positive risk).

**Apply.body is an unbounded `pl.Expr`.** `_ops.py:134-145` documents this as the escape hatch: `engine_binding` flips to `'polars'` whenever a model uses `Apply`, `pl.max_horizontal`, `pl.min_horizontal`, autopatched extension methods, or any non-closed-subset Expr. Real models will use the escape hatch — the question is how often. Without a corpus survey we can't say what percentage of existing models stay in the portable subset; tutorials in `tutorials/level-4-lifelib/` and `tutorials/rollforward-patterns/` are the place to measure.

**Cross-state references.** `ArgRef::State { state, point }` (`rollforward.rs:70-73`) lets one Op read another state's just-written value within the same period. JAX `lax.scan` handles this fine *within* a scan step (carry includes the full state vector), but only if the Op walk order is preserved as Python-level sequential code inside the scan body — i.e., you unroll the Op walk at trace time. The IR's `transitions` is already a fixed-length tuple at trace time, so this works. No fundamental obstacle.

**Ragged lists.** Mostly a non-problem. The Rust rollforward kernel asserts every input list column has `len == n_periods` for every row (`rollforward.rs:305-312`); it is rectangular by construction. `lapse_when_all_non_positive` and `contract_boundary` produce per-row early termination, but the kernel still allocates `n_periods` per row and just stops writing. JAX can mirror this with `jnp.where(t < contract_end, value, sentinel)` plus a tail-mask. Per-policy variable `n_periods` would be a problem, but that pattern doesn't exist in this codebase — `Schedule` produces a single `n_periods` per ActuarialFrame.

**String-fallback assumption lookups.** `array_storage.rs:36-51` and `key_encoder.rs` support `CategoricalWithStringFallback`, which receives raw strings at lookup time and resolves them via an `AHashMap<String, u32>`. JAX cannot trace string operations. Mitigation: require all string columns to be pre-encoded to `u32` *before* entering the JAX path. That is already half the design (the categorical storage path), so this is a constraint on the user, not a fundamental limit. Document that JAX backend rejects string keys and force pre-encoding.

**Python-level conditionals on data.** `condition_expression.py` and `polars_backend/masks.py` build `pl.when().then().otherwise()` trees. These map to `jnp.where`. But anything where users write Python `if` against a column value is untraceable in JIT — this is a JAX user-education item, not a porting blocker, and the framework already encourages mask-style writing.

**`map_batches` escape hatches.** `column_proxy.py:67` uses `pl.col(...).map_batches(...)` for rollforward struct-field extraction. This pattern doesn't translate; a JAX backend would surface those captures as a dict of `jnp.ndarray` directly rather than via Polars struct dereference.

## 4. Subset proposal — JAX backend v0.1

Scope this aggressively. v0.1 should be a **separate execution path** that consumes the rollforward IR + a constrained subset of column expressions, *not* a drop-in `ActuarialFrame` replacement.

In scope:
- Rollforward IR with `engine_binding == 'portable'` only — explicit error otherwise.
- The eight non-`Apply` Ops. Reject `Apply` (or implement a narrow allowlist of bodies).
- Schedule (rectangular `n_periods`, fixed across rows), `Curve`, `MortalityTable.at` aggregate + select_ultimate.
- Assumption lookups with pre-encoded integer keys only — string fallback rejected.
- Accumulate, list_pow, list_clip, list_conditional, fill_series — straightforward JAX ports.
- Inputs: caller supplies a dict of `jnp.ndarray` (shape `[n_rows, n_periods]` for list cols, `[n_rows]` for scalar cols). Outputs: same shape.
- `vmap` over a scenario axis (the `batch_axes` field on `IR` in `rollforward/_ir.py` is
  forward-compatible).

Out of scope for v0.1:
- `ActuarialFrame.with_columns` / `collect` parity. Users invoke the JAX backend explicitly: `compile_rollforward(ir).run_jax(inputs)`.
- Joint mortality structure, `Ratchet` with arbitrary Python-side `when`, the auto-patched extension namespace.
- Anything in `column/_dispatch_execution.py`'s list-shim path beyond what the IR already covers.
- `pl.max_horizontal`, contract_boundary expressions outside the closed subset.

This makes v0.1 a *rollforward accelerator*, not a backend. The honest framing.

## 5. Effort buckets

Trivial port:
- The eight non-Apply Ops as JAX scan bodies.
- `accumulate`, `list_pow`, `list_clip`, `list_conditional`, `fill_series`.
- `Curve.spot_rate / discount_factor / forward_rate` numeric path.
- `Schedule.year_fractions_expr` to a precomputed `[n_periods]` array.

Moderate refactor:
- Rollforward IR consumer that drives `lax.scan` over typed Ops. Work isn't algorithmic; it's mostly bookkeeping for `ArgRef::State` cross-references and capture slots.
- `MortalityTable.at` for `aggregate` and `select_ultimate` — reproduce `_at_select_ultimate`'s clamp logic in JAX.
- Assumption `Table.lookup` (integer-key path) — `jnp.take` over a precomputed table tensor; the encoder is already factored out.

Requires fundamental rethink:
- `ActuarialFrame` as a class. Either introduce a `FrameBackend` Protocol (cross-cutting refactor of `frame/base.py`, ~2350 lines) or accept that JAX is a separate execution path.
- `ColumnProxy` / `ExpressionProxy` returning `pl.Expr`. To unify backends you need a neutral expression IR that lowers to both. This is the largest refactor in the codebase and would touch every operator, every accessor, every namespace.
- Auto-patching from `pl.Expr` (`_dispatch_autopatch.py`). The "every method on `pl.Expr` automatically appears on the proxy" model is structurally Polars-coupled.

Not portable in v0.1:
- `Apply.body` as an arbitrary `pl.Expr`.
- String-key fallback in assumption lookups.
- `pl.max_horizontal`, `pl.min_horizontal`, autopatched `.gp.*` namespaces.
- `map_batches`-based escape hatches.

## 6. Open questions

- What fraction of existing models stay in `engine_binding == 'portable'`? The `_engine_binding.py:37-47` blocklist is small, but tutorial code uses `pl.max_horizontal` (likely — couldn't confirm without grepping each tutorial). A corpus survey across `tutorials/`, `models/`, and any internal models would tell us whether v0.1 covers 80% of cases or 20%.
- Is `Schedule` always rectangular in practice, or do users build per-policy schedules with different `n_periods`? The kernel asserts equal `n_periods` per chunk, but I don't know how chunks are formed across policies with different durations.
- How does the LazyFrame engine handle list-column results from the rollforward plugin downstream? If users routinely call `.list.eval(...)` on rollforward outputs in subsequent `with_columns`, those follow-on expressions are also Polars-bound and would need to be re-traced through JAX or computed eagerly on the host.
- Does `Curve` support arbitrary Python-defined interpolation (e.g., user-supplied callable)? `_curve.py` is 433 lines and I only read the closed-subset comment — a closer look would tell us whether `discount_factor` is genuinely a fixed numeric pipeline or has Python escape hatches.
- Is there an existing `rust-core.md` or `byo-python.md` extension story that already specifies a backend Protocol? Both files exist (`gaspatchio-docs/docs/concepts/extensions/`); they describe extension patterns but I did not read them in full. If a `Backend` Protocol is already specified there, the refactor scope shrinks considerably.
