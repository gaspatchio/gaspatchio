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


### Rust rules for this project - apply to all rust (*rs) files

@.claude/docs/cargo.md
@.claude/docs/documentation.md
@.claude/docs/error-handling.md
@.claude/docs/observability.md
@.claude/docs/ownership.md
@.claude/docs/performance.md
@.claude/docs/polars.md
@.claude/docs/safety.md
@.claude/docs/testing.md
@.claude/docs/type-system.md