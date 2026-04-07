# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Build and Test
- How to build and test the Rust library
   ```bash
   # Build the Rust library
   cargo build

   # Run all tests
   cargo test

   # Run benchmarks
   cargo bench

   # Build optimized release version
   cargo build --release

   # Quick compilation check
   cargo check

   # Format code
   cargo fmt

   # Run linter
   cargo clippy

   # Run specific benchmark
   cargo bench --bench vector_plugin_benchmark
   cargo bench --bench assumption_table_lookup_benchmark
   cargo bench --bench realistic_vector_lookup

   # Run specific test
   cargo test test_name
   ```

- Development Workflow
   1. Make changes to source files
   2. Run `cargo check` for quick validation
   3. Run `cargo test` to ensure tests pass
   4. Run `cargo bench` to verify performance
   5. Use `cargo fmt` and `cargo clippy` before committing


- This is a high-performance Rust library (`gaspatchio_core_lib`) for actuarial computations with three main components:
   1. **assumptions/** - Actuarial assumption table management
      - `table.rs`: AssumptionTable struct for storing and querying actuarial tables
      - `registry.rs`: Global concurrent registry using Arc-swap for lock-free access
      - Tables support multikey lookups and interpolation

   2. **excel/** - Excel-compatible financial functions
      - `date_time.rs`: Date functions including YEARFRAC implementation
      - `yearfrac_excel_verification.rs`: Comprehensive Excel compatibility tests
      - Maintains exact Excel behavior for actuarial users

   3. **polars_functions/** - Custom DataFrame operations
      - `vector.rs`: Specialized vector operations for actuarial projections
      - Functions like `fill_series` for efficient list column manipulation

- Key Design Patterns
   1. **Global Registry**: Uses Arc-swap for lock-free concurrent access to assumption tables
   2. **Polars Integration**: All data operations use Polars DataFrames for performance
   3. **Error Handling**: Uses `thiserror` for structured error types
   4. **Testing**: Unit tests embedded in source files using `#[cfg(test)]` modules
   5. **Benchmarking**: Criterion benchmarks track performance across releases

### Performance Considerations

- Benchmarks in `/benches` track performance with different data sizes
- Performance results documented in `benches/perf_results.md`
- CI benchmark dashboard: https://opioinc.github.io/gaspatchio-core/dev/model-bench/

#### Benchmark Suites

1. **`assumption_table_lookup_benchmark`** — Original lookup benchmarks (scalar path, hash vs array storage)
2. **`realistic_vector_lookup`** — Matches the actual L4 model's code path: list-column keys (10K policies × 120 months), tests mortality_select (3 keys), lapse_rates (2 keys), surrender_charges (2 keys), risk_free_rates (3 keys), and a combined model benchmark. **This is the authoritative benchmark for lookup performance.**
3. **`vector_plugin_benchmark`** — Vector/list operations (fill_series, etc.)

The real model passes List columns (one list per policy, ~120 elements per month) to `lookup_series`. The Rust code path is: explode lists → encode keys → compute linear index → gather values → rebuild ListChunked from flat array + arrow offsets.

#### Polars Streaming Engine

**CRITICAL: All plugins MUST be marked `is_elementwise=True` when they are stateless.**

A plugin is elementwise if each row's output depends only on that row's inputs — no cross-row dependencies. Assumption table lookups are elementwise: given key values for row N, the result depends only on row N's keys and the immutable lookup table.

Marking `is_elementwise=False` forces the **entire query plan** into in-memory execution, preventing the Polars streaming engine from processing data in chunks. This was the single largest performance bottleneck in v0.2.1 — fixing it delivered **6x speedup** at 100K model points.

When adding new plugins:
- If the plugin reads from global/shared state but each row is independent → `is_elementwise=True`
- If the plugin needs to see other rows to compute a result (e.g., cumulative operations) → `is_elementwise=False`
- When in doubt, test with `lf.explain(engine='streaming')` and `POLARS_VERBOSE=1` to verify the streaming engine doesn't fall back

**`ActuarialFrame.collect()` defaults to `engine="streaming"`**. The `auto` engine now also correctly selects streaming when all plugins are elementwise.

#### Polars Plugin Performance Guidelines

**CRITICAL: Do NOT Add Internal Parallelization to Plugins**

Polars expressions are **automatically parallelized at the engine level**. Adding Rayon or other parallelization inside plugin functions causes:
- Double parallelization (competing thread pools)
- Severe performance degradation in `group_by` operations
- Window function (`.over()`) bottlenecks
- Thread contention and resource competition

**Polars Maintainer Guidance:** "Expressions should not do their own parallelism, but polars engine should."

**Verified in v0.2.2:** Removing rayon from assumption lookups made isolated benchmarks ~1.6x slower but is the correct architectural decision. The streaming engine saturates 16 cores at scale — internal rayon would compete for those same cores. Isolated benchmarks don't reflect real model performance where Polars parallelizes across expressions.

**Best Practices for Plugin Implementation:**

1. **Use High-Level Apply Functions** (preferred over iterators)
   - `apply_generic` - Generic transformation with type preservation
   - `binary_elementwise` - Binary operations on primitive types
   - `binary_elementwise_values` - Binary operations with automatic null handling
   - These functions monomorphize for optimal iteration and computation

2. **For List Operations: Use `amortized_iter()`**
   - Reduces allocations by reusing Series containers
   - Example: `list_chunked.amortized_iter()` for efficient list traversal
   - Recent Polars optimizations (PR #20964) improved `amortized_iter()` by 9%
   - Your plugins automatically benefit from future Polars performance improvements

3. **Let Polars Handle Configuration**
   - Users control parallelism via `pl.Config.set_num_threads()`
   - Engine automatically adjusts chunk sizes for optimal throughput
   - Plugins remain simple and work correctly in all execution contexts

4. **When Rayon IS Appropriate** (rare cases only)
   - Standalone utilities that don't integrate with Polars expressions
   - Single-element transformations that are extremely CPU-intensive (e.g., complex set operations)
   - When plugin documentation explicitly recommends it

5. **Micro-Optimizations to Avoid**
   - Pre-allocating with `Vec::with_capacity()` often slower than `.collect()` due to compiler optimizations
   - Manual loop unrolling (LLVM already does this)
   - Custom SIMD implementations (use Polars' vectorized operations instead)

**Benchmarking Notes:**
- Isolated plugin benchmarks don't reflect real-world performance
- Test plugins in realistic query contexts: `group_by`, `over`, multiple concurrent expressions
- Linear scaling across data sizes indicates correct implementation
- Performance regressions in composed queries indicate parallelization conflicts
- The `realistic_vector_lookup` benchmark is the most representative of real model performance

**Reference Implementation:** See `polars_functions/list_pow.rs` for example of optimal plugin pattern

#### Memory at Scale

Peak RSS during model execution is dominated by intermediate columns in the lazy query plan. At 100K model points, the L4 model uses ~5 GB RSS. The 54 chained `with_columns` nodes prevent the streaming engine from reducing peak memory — all intermediates must coexist in memory.

Key findings:
- **`tracemalloc` is useless** — it only tracks Python heap allocations, missing all Rust/Polars arrow buffers. CI uses process RSS via `psutil` instead.
- **`sink_parquet` doesn't help** — the query plan isn't streamable for memory purposes (streaming helps speed, not peak memory for dependent column chains)
- **Model-point batching** (GSP-89) is the proven approach: split policies into chunks, run each through the model independently, write to parquet. Caps peak memory at ~1.5 GB regardless of total scale.
- **Column pruning** (GSP-90) reduces final output size (124 cols → ~12 needed) but doesn't reduce peak RSS during computation
- **Array storage** is 20-40x faster than hash storage for vector lookups. `Auto` mode already picks array for all L4 assumption tables.


## Documentation Audience

Gaspatchio documentation targets two audiences:

1. **Actuaries** — They know the products and actuarial concepts. They need to see their workflow in the code.
2. **LLMs** — They need complete examples with realistic actuarial data so they can generate correct code.

Every documentation section should follow: **business problem** → **Gaspatchio solution** → **code example**. Lead with the actuarial problem being solved, not the computer science architecture. Skip internal implementation details (Rust kernels, Struct columns, kwargs serialization) unless directly relevant to how the user calls the API.

## Design Documents and Plans

Design specs and implementation plans live in `ref/<topic>/` alongside the relevant reference material. The `ref/` directory uses numbered prefixes (e.g., `ref/30-llm-helpers/`).

- **Specs**: `ref/<topic>/specs/YYYY-MM-DD-<name>-design.md`
- **Plans**: `ref/<topic>/plans/YYYY-MM-DD-<name>.md`

When using Superpowers skills (brainstorming, writing-plans), save output to the relevant `ref/` subdirectory. If unsure which `ref/` folder applies, ask the user. Do NOT use `docs/superpowers/` — that directory does not exist in this project.

Current active topic: `ref/30-llm-helpers/` (LLM skills, tutorial, CLI improvements).

### Rust rules for this project - apply to all rust (*rs) files

@prompts/rust/core.md
@prompts/rust/cargo.md
@prompts/rust/documentation.md
@prompts/rust/error-handling.md
@prompts/rust/observability.md
@prompts/rust/ownership.md
@prompts/rust/performance.md
@prompts/rust/polars.md
@prompts/rust/safety.md
@prompts/rust/testing.md
@prompts/rust/type-system.md
