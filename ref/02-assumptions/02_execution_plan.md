```markdown
# Step-by-Step Blueprint & Prompt Series for Building the In-Memory Polars Table Registry

Below is a stepwise plan for implementing the project described in the attached markdown (`gaspatchio-core/ref/02-assumptions/02_table_registry_specification.md`). Each step is broken down into small, iterative chunks. For each chunk, there's a corresponding code-generation prompt for a hypothetical LLM. This ensures incremental development, continuous testing, and steady integration without orphaned code.

---

## Phase 1: Setup and Skeleton

### Step 1: Initialize Basic Project Structure
1. Ensure we have a Rust workspace (or single crate) aligned with our existing structure.
2. Create a new module or file for "table_registry" (e.g. `src/table_registry.rs`).
3. Start with minimal definitions for `TableRegistry` and `KeySpec` (no logic yet).
4. Add a placeholder test file.
5. Confirm everything compiles and passes an empty test suite.

**Prompt**:
```text
Implement a new file named "table_registry.rs" with:
- A minimal `KeySpec` struct holding `source_cols` and `table_cols`
- A minimal `TableRegistry` struct holding `tables` (HashMap<String, DataFrame>) and `keyspecs` (HashMap<String, KeySpec>)
- A single unit test in "table_registry.rs" or "tests/table_registry_tests.rs" verifying the structs can be created

Don't add any real logic; just placeholders. Make sure it compiles and the tests pass.
```

---

## Phase 2: Core Registry & Atomic Storage

### Step 2: Introduce ArcSwap
1. Add `arc-swap` dependency.
2. Create a static `REGISTRY` using `ArcSwap` and initialize it with a default `TableRegistry`.
3. Write a function `get_registry()` returning an `Arc<TableRegistry>`.
4. Write a function `set_registry()` that copies the old, modifies it, and then stores it in `ArcSwap`.

**Prompt**:
```text
Add an `ArcSwap<TableRegistry>` static named `REGISTRY`. Provide:
- `get_registry()` returning an Arc of the current registry
- `set_registry()` that clones the old registry, modifies it, and stores it
- A test verifying that a `TableRegistry` update is seen by subsequent `get_registry()` calls
```

---

## Phase 3: Registering Tables

### Step 3: Implement `register_table`
1. Add method `register_table(table_name, df, key_spec)` to `TableRegistry`.
2. In `set_registry()`, demonstrate how to clone the old registry, call `register_table()`, then store the new registry using ArcSwap.
3. Test that after registration, the table is retrievable from the global registry.

**Prompt**:
```text
Implement `register_table` in `TableRegistry` with:
- `pub fn register_table(&mut self, table_name: &str, df: DataFrame, key_spec: KeySpec)`
- A top-level function `register_table_global(table_name, df, key_spec)` that:
   1. Clones the old registry
   2. Calls `register_table`
   3. Stores the new registry
Add a test that registers a table and verifies it persists in the global registry.
```

---

## Phase 4: Polars Joins (Lookup Process)

### Step 4: Implement Basic Lookup
1. Write a function `lookup(table_name, query_df)`:
   - Acquire the current registry
   - Find the table’s DataFrame and KeySpec
   - Join (lazy) with the query DataFrame on `source_cols` vs `table_cols`
2. Return the joined result.

**Prompt**:
```text
Create a function `lookup(table_name: &str, query_df: DataFrame) -> PolarsResult<DataFrame>` in "table_registry.rs":
- Retrieve the table DataFrame & KeySpec from the registry
- Perform a lazy left join on `source_cols` vs `table_cols`
- Return the joined DataFrame
Write a test verifying that joining an in-memory table with a small query returns expected columns.
```

---

## Phase 5: Wide-to-Long Transformation

### Step 5: Add Optional Table Transformation
1. Write a helper function `transform_wide_to_long(df, id_vars, value_vars, var_name, value_name)` returning a new DataFrame.
2. Integrate this into `register_table_global` so that we can optionally transform before storing.

**Prompt**:
```text
Add a function `transform_wide_to_long(...)` that uses Polars “melt”.
Then enhance `register_table_global` to accept an optional `transform_spec` object.
If present, transform the DataFrame before registering.
Include tests verifying wide→long transformation.
```

---

## Phase 6: Python Bindings (Optional, if needed)

### Step 6: PyO3 Integration
1. Expose `py_register_table` and `py_lookup` that wrap the Rust functions.
2. Confirm everything builds and tests out in Python.

**Prompt**:
```text
Use PyO3 to create:
- `#[pyfunction] fn py_register_table(...)` that calls `register_table_global`
- `#[pyfunction] fn py_lookup(...)` that calls `lookup`
Expose them in a `[pymodule] fn mod_name(_py, m) -> PyResult<()>`.
Add Python integration tests verifying registration and lookup from Python.
```

---

## Phase 7: Testing & Final Integration

### Step 7: Comprehensive Testing
1. Write integration tests ensuring multi-step usage:
   - Register multiple tables
   - Perform lookups
   - Confirm concurrency safety
2. If concurrency testing is desired, add a simple concurrency test (spawn threads for lookups during table registration).

**Prompt**:
```text
Add comprehensive tests:
- Multi-table registration
- Complex queries with different key column sets
- Concurrency tests where multiple threads do parallel lookups
Ensure tests pass. No orphan code; all integrated properly.
```

---

## Phase 8: Performance Benchmarks (Optional)

### Step 8: Benchmark & Future Enhancements
1. Include optional benchmarks (using `cargo bench` or similar).
2. Tweak if needed based on memory or concurrency requirements.

**Prompt**:
```text
Add a `benches/` directory with a simple benchmark for large DataFrame lookups.
Use `criterion` to measure join performance.
No major code changes, just performance instrumentation.
```

---

## Final Note
At this stage, each phase should build on the previous, ensuring no major leaps. Tests are expanding as we go. By the end, we have a functional, well-tested Polars-based, ArcSwap-backed in-memory registry with optional table transformations and Python bridging.

```
