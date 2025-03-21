# Table Registry Implementation Checklist

This checklist tracks implementation progress for the in-memory Polars Table Registry, following the plan in `02_execution_plan.md`.

## Phase 1: Setup and Skeleton ✅

- [x] Create `table_registry.rs` module
- [x] Implement minimal `KeySpec` struct with `source_cols` and `table_cols`
- [x] Implement minimal `TableRegistry` struct with `tables` and `keyspecs` HashMaps
- [x] Add unit tests in the same file
- [x] Add to `lib.rs` module
- [x] Verify compilation works with `maturin develop --uv`
- [x] Add Python tests for basic functionality
- [x] Confirm Python import structure is correct

## Phase 2: Core Registry & Atomic Storage ✅

- [x] Add `arc-swap` dependency
- [x] Create static `REGISTRY` using `ArcSwap` initialized with a default `TableRegistry`
- [x] Add `get_registry()` function returning an `Arc<TableRegistry>`
- [x] Add `set_registry()` function that copies the old, modifies it, then stores in `ArcSwap`
- [x] Add tests verifying that a `TableRegistry` update is seen by subsequent calls

## Phase 3: Registering Tables ✅

- [x] Implement `register_table(table_name, df, key_spec)` method to `TableRegistry`
- [x] Implement `register_table_global(table_name, df, key_spec)` function that:
  - [x] Clones the old registry
  - [x] Calls `register_table` on the clone
  - [x] Stores the new registry using `ArcSwap`
- [x] Add tests verifying table registration works as expected
- [x] Add tests verifying tables persist in the global registry

## Phase 4: Polars Joins (Lookup Process) ✅

- [x] Implement `lookup(table_name, query_df)` function that:
  - [x] Acquires the current registry
  - [x] Finds the table's DataFrame and KeySpec
  - [x] Joins (lazy) with the query DataFrame on `source_cols` vs `table_cols`
  - [x] Returns the joined result
- [x] Add tests verifying joining works as expected
- [x] Test with different column sets and data types

## Phase 5: Wide-to-Long Transformation ⬜

- [ ] Implement `transform_wide_to_long(df, id_vars, value_vars, var_name, value_name)` function using Polars "melt"
- [ ] Enhance `register_table_global` to accept an optional `transform_spec` object
- [ ] Add functionality to transform DataFrame before registering if transform_spec is provided
- [ ] Add tests verifying wide→long transformation works properly

## Phase 6: Python Bindings (Partially Complete) ✅

- [x] Create PyO3 bindings for `KeySpec` and `TableRegistry`
- [x] Expose table registry classes to Python
- [x] Add additional PyO3 wrappers for:
  - [x] `register_table` as `py_register_table`
  - [x] `lookup` as `py_lookup`
- [x] Update Python tests for these new functions

## Phase 7: Testing & Final Integration ⬜

- [x] Add comprehensive integration tests
  - [x] Tests with multiple tables registered
  - [x] Complex queries with different key column sets
  - [x] Tests handling edge cases (invalid tables, missing columns)
  - [ ] Concurrent access tests
- [x] Test all functionality through Python interface
- [ ] Verify thread safety and concurrency behavior
- [ ] Add documentation with examples

## Phase 8: Performance Benchmarks (Optional) ⬜

- [ ] Create benchmarks directory
- [ ] Add benchmark for large DataFrame lookups
- [ ] Measure join performance with `criterion`
- [ ] Optimize if necessary based on benchmark results
