# gaspatchio-core / core — Rust development rules

Canonical contributor rules for the Rust core crate (`gaspatchio_core_lib`). Read natively
by AI coding agents (Codex, Amp, Cursor, Gemini CLI, Copilot) and by Claude Code via the
sibling `CLAUDE.md` import shim. Applies to all `*.rs` files under `core/`.

**General Rust practice lives in [`core/docs/rust-standards.md`](docs/rust-standards.md)** —
Cargo hygiene, documentation, error handling, observability, ownership, performance, safety,
testing, the type system, and the full Polars plugin walk-through. It moved there so that
this file plus the root `AGENTS.md` fit the 32 KiB window a Codex session merges them into;
what stays below is what is specific to this crate and must not be missed.

## Commands

```bash
cargo build                  # or --release for the optimized build
cargo check                  # quick validation
cargo test                   # all tests; `cargo test <name>` for one
cargo bench                  # all benchmarks; `--bench <suite>` for one
cargo fmt && cargo clippy    # before committing
```

Workflow: edit, `cargo check`, `cargo test`, `cargo bench` if the change is on a hot path,
`cargo fmt` and `cargo clippy` last.

### What is in the crate

Three parts. **`assumptions/`** — `table.rs` holds `AssumptionTable` (multikey lookups and
interpolation), `registry.rs` a global registry using Arc-swap for lock-free concurrent
access. **`excel/`** — `date_time.rs` carries `YEARFRAC` and `yearfrac_excel_verification.rs`
its compatibility tests; exact Excel behaviour is the contract, because that is what an
actuary reconciles against. **`polars_functions/`** — `vector.rs` carries the projection
vector operations such as `fill_series`.

Patterns that recur: the Arc-swap registry, Polars DataFrames for every data operation,
`thiserror` for structured errors, `#[cfg(test)]` unit tests beside the code, and Criterion
benchmarks tracking performance across releases.

## Performance Considerations

- Benchmarks in `/benches` track performance with different data sizes
- Performance results documented in `benches/perf_results.md`

### Benchmark Suites

1. **`assumption_table_lookup_benchmark`** — Original lookup benchmarks (scalar path, hash vs array storage)
2. **`realistic_vector_lookup`** — Matches the actual L4 model's code path: list-column keys (10K policies × 120 months), tests mortality_select (3 keys), lapse_rates (2 keys), surrender_charges (2 keys), risk_free_rates (3 keys), and a combined model benchmark. **This is the authoritative benchmark for lookup performance.**
3. **`vector_plugin_benchmark`** — Vector/list operations (fill_series, etc.)

The real model passes List columns (one list per policy, ~120 elements per month) to `lookup_series`. The Rust code path is: explode lists → encode keys → compute linear index → gather values → rebuild ListChunked from flat array + arrow offsets.

### Polars Streaming Engine

**CRITICAL: All plugins MUST be marked `is_elementwise=True` when they are stateless.**

A plugin is elementwise if each row's output depends only on that row's inputs — no cross-row dependencies. Assumption table lookups are elementwise: given key values for row N, the result depends only on row N's keys and the immutable lookup table.

Marking `is_elementwise=False` forces the **entire query plan** into in-memory execution, preventing the Polars streaming engine from processing data in chunks. This was the single largest performance bottleneck in v0.2.1 — fixing it delivered **6x speedup** at 100K model points.

When adding new plugins:
- If the plugin reads from global/shared state but each row is independent → `is_elementwise=True`
- If the plugin needs to see other rows to compute a result (e.g., cumulative operations) → `is_elementwise=False`
- When in doubt, test with `lf.explain(engine='streaming')` and `POLARS_VERBOSE=1` to verify the streaming engine doesn't fall back

**`ActuarialFrame.collect()` defaults to `engine="streaming"`**. The `auto` engine now also correctly selects streaming when all plugins are elementwise.

### Polars Plugin Performance Guidelines

**CRITICAL: Do NOT Add Internal Parallelization to Plugins**

Polars expressions are **automatically parallelized at the engine level**. Adding Rayon or other parallelization inside plugin functions causes:
- Double parallelization (competing thread pools)
- Severe performance degradation in `group_by` operations
- Window function (`.over()`) bottlenecks
- Thread contention and resource competition

**Polars Maintainer Guidance:** "Expressions should not do their own parallelism, but polars engine should."

**Verified in v0.2.2:** Removing rayon from assumption lookups made isolated benchmarks ~1.6x slower but is the correct architectural decision. The streaming engine saturates 16 cores at scale — internal rayon would compete for those same cores. Isolated benchmarks don't reflect real model performance where Polars parallelizes across expressions.

**Best Practices for Plugin Implementation:**

1. **Use high-level apply functions** (preferred over iterators) — `apply_generic` for a
   generic transformation with type preservation, `binary_elementwise` for binary operations
   on primitive types, `binary_elementwise_values` for the same with automatic null handling.
   These monomorphize for optimal iteration and computation.
2. **For list operations, use `amortized_iter()`** — it reduces allocations by reusing Series
   containers, and your plugins inherit future Polars improvements to it for free.
3. **Let Polars handle configuration** — users control parallelism via
   `pl.Config.set_num_threads()` and the engine adjusts chunk sizes itself.
4. **When Rayon IS appropriate** (rare) — standalone utilities outside Polars expressions,
   extremely CPU-intensive single-element transformations, or where the plugin documentation
   explicitly recommends it.
5. **Micro-optimizations to avoid** — `Vec::with_capacity()` is often slower than
   `.collect()`, LLVM already unrolls loops, and Polars' vectorized operations beat custom
   SIMD.

**Benchmarking notes:** isolated plugin benchmarks do not reflect real-world performance.
Test in realistic query contexts (`group_by`, `over`, multiple concurrent expressions); linear
scaling across data sizes indicates a correct implementation, and a regression in a composed
query indicates a parallelization conflict. **Reference implementation:**
`polars_functions/list_pow.rs`.

### Memory at Scale

Peak RSS during model execution is dominated by intermediate columns in the lazy query plan. At 100K model points, the L4 model uses ~5 GB RSS. The 54 chained `with_columns` nodes prevent the streaming engine from reducing peak memory — all intermediates must coexist in memory.

Key findings:
- **`tracemalloc` is useless** — it only tracks Python heap allocations, missing all Rust/Polars arrow buffers. CI uses process RSS via `psutil` instead.
- **`sink_parquet` doesn't help** — the query plan isn't streamable for memory purposes (streaming helps speed, not peak memory for dependent column chains)
- **Model-point batching** (GSP-89) is the proven approach: split policies into chunks, run each through the model independently, write to parquet. Caps peak memory at ~1.5 GB regardless of total scale.
- **Column pruning** (GSP-90) reduces final output size (124 cols → ~12 needed) but doesn't reduce peak RSS during computation
- **Array storage** is 20-40x faster than hash storage for vector lookups. `Auto` mode already picks array for all L4 assumption tables.

## Writing a Polars plugin

Declare the output type. Polars infers it from the return signature for well-known types and
cannot for the rest, so point `#[polars_expr(output_type_func = ...)]` at a helper returning
the `DataType` the plugin produces. The worked `fill_series` implementation is in
[`docs/rust-standards.md`](docs/rust-standards.md).

When creating a DataFrame with vectors, call `.into()` on the name:

```rust
// Good ✅
"vector" => ListChunked::from_iter([
    Some(Series::new("".into(), vec![10, 20])),
    Some(Series::new("".into(), vec![30, 40, 50])),
]).into_series()

// Bad ❌ — the bare &str does not coerce to PlSmallStr
"vector" => ListChunked::from_iter([
    Some(Series::new("", vec![10, 20])),
    Some(Series::new("", vec![30, 40, 50])),
]).into_series()
```
