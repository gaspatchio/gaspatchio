# Mojo Backend Feasibility Assessment for gaspatchio-core

## 1. Architecture map — where is Polars actually nailed in?

The codebase has *three* distinct seams, not one. Any "Mojo backend" conversation must pick which seam it's targeting; they have very different effort profiles.

**Seam A — User-facing column algebra (the proxy layer).**
`bindings/python/gaspatchio_core/column/column_proxy.py` and `expression_proxy.py` translate `af.av * af.qx` into a `pl.Expr` tree. The dispatch layer (`column/_dispatch_execution.py:88-93`) routes named ops (`pow`, `clip`, `cum_prod`, etc.) either to vanilla Polars, to `list.eval(pl.element().<op>())` shims for List columns, or to the gaspatchio plugin functions in `polars_backend/operators.py` and `polars_backend/plugins.py`. Every `__add__`/`__mul__`/`__lt__` on `ColumnProxy` builds a `pl.Expr` (`column_proxy.py:124-200`). This seam is *thoroughly* Polars-bound: shape is queried from `pl.LazyFrame.collect_schema()`, conditional builders return `pl.when().then().otherwise()` trees, and even ConditionExpression carries `pl.Expr`.

**Seam B — The PyO3 plugin entry points.**
`bindings/python/src/vector.rs` and `bindings/python/src/assumptions.rs` expose six kernels via `#[polars_expr]`: `fill_series`, `accumulate`, `list_pow`, `list_clip`, `list_conditional`, `rollforward`, plus the `lookup_by_table_and_hash` for assumption tables. Each receives `&[Series]` plus a deserialised kwargs struct. The kernels themselves (in `core/src/polars_functions/`) operate on Polars `Series`/`ListChunked` types — they consume Polars' Arrow buffers but the *math* is plain Rust loops over `&[f64]`/`&[i64]` slices.

**Seam C — The rollforward IR.**
This is the cleanest layer in the codebase. `bindings/python/gaspatchio_core/rollforward/_ir.py` defines an immutable IR with typed Ops (`_ops.py`: `Add`, `Subtract`, `Charge`, `Grow`, `GrowCapped`, `DeductNAR`, `Ratchet`, `Floor`, `Apply`). `_engine_binding.py` already declares `EngineBinding = Literal["portable", "polars"]` and walks the IR statically to determine if it's lowerable to alternative backends. The pass chain in `_passes.py` (Validate → ResolveStateRefs → FoldConstants → AssignCaptureSlots → LowerToPolarsPlugin) ends with a deliberately backend-specific lowering pass. **A "LowerToMojo" pass would slot in here.** The kernel kwargs schema (`rollforward.rs:30-48`) uses pre-resolved arg-indices and integer state/point indices — no Polars-specific types in the contract.

Note that Op `expr` fields are still typed `pl.Expr` (`_ops.py:43`) and `LowerToPolarsPlugin._single_column_name()` (`_passes.py:160-184`) restricts them to bare `pl.col("name")`. So the IR's *operator* vocabulary is portable; the *expression* vocabulary inside Ops is "single column ref", which means Mojo only needs a way to take a per-row List<Float64> input, not interpret arbitrary expression trees.

## 2. Mappable — what ports cleanly

The *kernels themselves* are nearly trivial Mojo targets if you accept ownership of the Arrow buffer in/out:

- **`accumulate`** (`core/src/polars_functions/accumulate.rs`): `out[t] = out[t-1]*m[t] + a[t]`. Per-row sequential scan over flat f64 slices. Mojo `algorithm.parallelize` over rows + scalar inner loop is a direct port. SIMD doesn't help the inner loop (data dependency); Mojo wins, if at all, only via better row-level parallelism — but Polars already parallelises across rows.
- **`list_pow`, `list_clip`, `list_conditional`**: pure element-wise. These are the obvious candidates for SIMD/GPU wins. Mojo's vectorised loops are at least as good as Rust+autovec; on GPU these become trivial dispatches if data is already on-device.
- **`fill_series`**: a sequence builder. Trivial.
- **Rollforward inner kernel** (`rollforward.rs:299-405`): per-row state walk, period loop, op-tag dispatch on `OpV2`, flat `state: Vec<f64>` indexed by `s*stride_state + p*stride_point + t`. The op set is fixed and small (9 variants). This is the canonical use case for Mojo's parameterised structs — you could specialise the period loop on the op chain at compile time and inline every op into a fused kernel. **This is the single highest-value port.**
- **Assumption-table array storage** (`core/src/assumptions/array_storage.rs`): once dictionary-encoded, lookup is `data[stride · key_indices]`. Plain integer-indexed gather; trivial in Mojo. The hash-storage path is harder (see below).

## 3. Friction — what doesn't, and why

**Mojo's Python-interop story (May 2026, honestly).**
I cannot verify Mojo's current production state from inside the repo; my background on Mojo runs through early-2025 releases. As of then: Mojo's Python interop went through `python.bind` / `Python.import_module` and was usable for calling Python *from* Mojo, but the inverse — exposing Mojo functions as Python C-extension symbols equivalently to PyO3 — was not as polished. There is **no published equivalent of `#[polars_expr]`** that registers a Mojo function as a Polars expression plugin via the FFI pickled-function protocol that `polars.plugins.register_plugin_function` expects. Without that, you cannot drop a Mojo kernel into a `pl.Expr` tree the way the current Rust kernels are dropped in. The way to ship would be: collect the relevant columns out of Polars to flat buffers, hand them to Mojo, take results back, materialise as a new Polars Series. That's a non-trivial cost on hot paths — and `core/src/polars_functions/rollforward.rs:175-263` already has to do exactly that copy on the Rust side, so it's not catastrophic, but the Mojo round-trip is from a *different process address space possibly involving DLPack*, not in-process Arrow.

**No DataFrame in the Mojo ecosystem.** As of my knowledge, there is no Polars-equivalent in Mojo. The MAX SDK provides graph-level ops over MAX `Tensor`s, but a lazy DataFrame engine with query optimisation, predicate pushdown, schema introspection, and the entire Arrow chunk story isn't there. So "swap Polars for Mojo" is a category error — Polars is the lazy execution engine + ETL layer, Mojo is a kernel language. The realistic question is "swap *Polars-as-kernel-host* for *Mojo-as-kernel-host*", with Polars retained for IO / schema / aggregation.

**Ragged List<Float64>.** The kernels already use offsets+flat-buffer (`OwnedListSlice` in `rollforward.rs:138`). Mojo has `Tensor` (rectangular) and could ship its own offsets+values structure — but you'd be *building* the ragged abstraction, not using one off the shelf. For models where every policy has the same `n_periods` (currently enforced by `rollforward.rs:305-312`), the data is rectangular `[num_rows, n_periods]` and maps directly to a Mojo `Tensor[DType.float64]`. This is the realistic GPU story: enforce rectangularity, dispatch to a 2D kernel.

**IR-driven dispatch on Ops.** Mojo's parameter system is genuinely well-suited to specialising the rollforward inner loop on the op chain — `@parameter for op in ops:` would let the compiler see the entire transition body as straight-line code per period. The hitch is *that compile-time specialisation requires the op chain to be known at compile time of the Mojo kernel*. The op chain comes from user models, evaluated at Python-runtime. So you'd need either: (a) a Mojo JIT tier that compiles per-IR, (b) a fixed dispatch interpreter in Mojo (matching today's Rust `match op { ... }` in `apply_op`, no specialisation gain), or (c) precompile the N most common op chains. Option (a) is the only one that beats Rust meaningfully, and it depends on how production-ready Mojo's runtime JIT is — which I cannot honestly assert.

**Hash-storage for sparse assumption tables** (`core/src/assumptions/hash_storage.rs`). Mojo stdlib has `Dict` but performance-tuned hashmap support comparable to `ahash` is not where the ecosystem is mature. ArrayStorage (the dense, dictionary-encoded fast path) ports trivially. HashStorage (the fallback for low-density tables) would either need a hand-rolled robin-hood map or a callback back into Rust/Python.

**User Python expressions inside Op fields.** The IR allows `pl.Expr` in places like `Apply.body`, `GrowCapped.cap`, `Ratchet.when` (`_ops.py`). The `LowerToPolarsPlugin._single_column_name` pass restricts these to `pl.col(...)` or precomputes them — so for the rollforward path the Mojo backend only ever needs to read a precomputed input column. Outside rollforward (the column-proxy seam), users *are* writing `pl.Expr`-valued things like `af.av = af.av * (1 - af.qx)` and Mojo would need an equivalent expression evaluator or a Polars→Mojo lowering — neither exists today.

**Schedule, Curve, MortalityTable.** These are typed Python objects that *generate* `pl.Expr` (`_engine_binding.py:5-13` lists `Schedule.year_fractions_expr`, `Curve.spot_rate / discount_factor`, `MortalityTable.at`). They're loosely coupled to Polars in the sense that they're already wrapped behind methods returning expressions; rewriting them to emit Mojo kernel calls (or to materialise to flat arrays consumable by Mojo) is mechanical refactoring, not redesign. Curves use bootstrap/interpolation logic in `curves/_curve.py` — these become Mojo functions producing flat arrays, with no Polars dependency in the math.

**PyO3 plugin equivalent in Mojo: there isn't one.** This is the biggest single ecosystem-maturity risk. The current `polars.plugins.register_plugin_function` machinery serialises the function name + a path to a compiled `.so` plus pickled kwargs and dispatches via Polars' internal plugin loader. To get equivalent Mojo integration you'd be writing a C-ABI Mojo `.so` that *imitates* the pyo3-polars FFI signature — which is shaped around `polars-arrow` types — and that's a contract Polars does not stabilise.

## 4. Subset proposal — what a viable v0.1 actually looks like

Don't swap the backend. Replace specific kernels with Mojo, keep Polars as the host. Concretely:

- **v0.1: Mojo rollforward kernel.** Add `LowerToMojoKernel` as a sibling pass to `LowerToPolarsPlugin`. The IR is already engine-binding-aware. Bind a single Mojo function that takes `(state_inits: Tensor, input_lists: List[Tensor], offsets: List[Tensor], op_table: Tensor[Int32], constants: Tensor)` and returns capture tensors. Wrap the call in a Polars `map_batches` so it lives inside the existing lazy plan. Don't try to specialise on op chain in v0.1 — ship the dispatch interpreter first, then add per-IR JIT once you have benchmarks justifying it.
- **v0.1 NOT supported.** Apply (escape hatch — already not supported by the Rust kernel, see `rollforward.rs:545-549`), ragged `n_periods` per row, contract_boundary with `pl.Expr` masks (only precomputed bool lists), HashStorage assumption tables, the entire column-proxy seam (af.av = af.av * (1-af.qx) stays on Polars).
- **Stretch: Mojo accumulate/list_pow/list_clip/list_conditional** behind a feature flag. These are the cleanest 1:1 ports and the easiest place to validate the FFI bridge round-trip cost. If round-trip cost exceeds the kernel speedup, the whole exercise fails — measure here first.
- **Out of scope:** GPU dispatch. Until rectangularity is enforced and the FFI bridge is solid, GPU is a distraction. Once shipped, the same kernels on rectangular data become single-line `@parameter`-spec'd MAX graph nodes.

## 5. Effort buckets

| Component | Effort | Notes |
|---|---|---|
| `accumulate`, `list_pow`, `list_clip`, `list_conditional` kernels | Trivial port (math) / Moderate (FFI plumbing) | Math is line-for-line; the cost is the Polars↔Mojo bridge |
| Rollforward inner kernel | Moderate refactor | IR already portable; need Mojo-side op-table interpreter; rectangular-data assumption needed |
| Compile-time op-chain specialisation | Requires fundamental rethink | Needs a Mojo JIT tier wired to user-model lifecycle |
| ArrayStorage assumption lookup | Trivial port | Pure integer-indexed gather |
| HashStorage assumption lookup | Moderate refactor | No mature ahash equivalent in Mojo stdlib |
| Schedule / Curve / MortalityTable input pre-materialisation | Moderate refactor | Methods need a "to flat array" path alongside their `to_expr` path |
| Column-proxy seam (`af.av * af.qx`) | Not portable as-is | User code is `pl.Expr` algebra; would need a Polars-Expr→Mojo-IR lowering that doesn't exist |
| `Apply.body` escape hatch | Not portable | By design — engine_binding flags it as `'polars'` |
| PyO3-equivalent Mojo plugin registration | Requires fundamental rethink | No upstream API; would be a custom C-ABI bridge with stability risk |

## 6. Open questions

- **Mojo's plugin-extension story for Polars (May 2026).** Has Mojo shipped a stable C ABI / DLPack bridge that survives Polars version bumps? My honest answer is: I don't know — last I checked, Mojo's FFI was advancing fast but not Polars-aware. This is the single load-bearing question; everything else is mechanical work.
- **Does the MAX SDK include a ragged-list / variable-length tensor primitive?** The current ragged story is offsets+values; if MAX has matured ragged-tensor support, the rollforward port gets significantly cleaner.
- **Per-IR Mojo JIT.** If Mojo's runtime supports compiling parameterised kernels at Python-call-time with reasonable latency (sub-second), the op-chain specialisation strategy is alive. If compilation is multi-second-per-IR, it's dead for interactive workflows.
- **Throughput parity for sequential scans.** The `accumulate` and rollforward inner loops are fundamentally serial within a row. Mojo wins only on cross-row parallelism / GPU dispatch. Question: at what row count does the FFI round-trip overhead amortise? A small benchmark on the existing 6 kernels — Rust-Polars vs Mojo-via-FFI — answers whether the architecture is even worth pursuing.
- **Engine-binding granularity.** Today the IR has `engine_binding ∈ {portable, polars}`. Adding `mojo` as a third value is a one-line change, but the *closed subset* whitelist (`_engine_binding.py:37-47`) needs review — any Op field expressions Mojo can't evaluate must flip the binding back to `polars`. This is not implementation; it's a small audit.
- **Maturity of Mojo's stdlib for hash-backed structures, error handling, and async.** The kernels themselves don't need much, but a production backend does. Worth validating before committing to scope beyond v0.1.

The defensible version of this work is: leave Polars alone as the host, target the rollforward kernel as the first Mojo plug-in (it's the highest-compute, most-isolated surface and the IR is already designed for backend swaps), measure the round-trip cost honestly, and *only then* decide whether broader kernel coverage or GPU dispatch is worth pursuing. The "swap the backend" framing is misleading — there is no Mojo Polars to swap to. There is, viably, a Mojo kernel inside the existing stack.
