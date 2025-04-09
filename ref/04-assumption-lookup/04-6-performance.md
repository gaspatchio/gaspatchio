# Performance Optimization: Pre-Hashed Key Lookups

This document outlines the specification and implementation plan for optimizing the assumption lookup functionality in `gaspatchio_core_lib::index`.

## 1. Problem Definition

Initial benchmarking and profiling (using `cargo bench` and `cargo flamegraph`) revealed that the current lookup implementation (`perform_lookup` and its children, particularly `execute_vector_lookup`) is significantly slower than expected for hashmap-based lookups (~4400 lookups/sec instead of millions/sec).

The primary bottleneck identified is the **row-by-row processing** performed within Rust loops when handling lookups, especially for vector (Polars `List`) key inputs. This involves:

1.  **Repeated Value Extraction:** Calling `extract_value_from_series` or `extract_value_from_list_series` for *each key column* within *each row/element* iteration.
2.  **Repeated Value Conversion:** Converting extracted Polars `AnyValue`s to the internal `Value` enum via `any_value_to_value`, which includes potentially expensive operations like **string cloning/allocation** for every string key component.
3.  **Repeated Key Vector Creation:** Allocating and populating a `Vec<Value>` for every single lookup operation inside the loops.
4.  **Manual Iteration:** Bypassing Polars' optimized, vectorized iteration capabilities.

The core hashmap lookup (`HashMap::get`) itself is fast, but the overhead surrounding its invocation in the current implementation dominates the execution time.

## 2. Proposed Solution: Pre-Hashing Keys

To address the bottleneck, we will refactor the lookup mechanism to pre-compute hashes for key combinations and use these hashes directly as keys in the lookup index. This leverages Polars' highly optimized hashing functions and avoids row-by-row processing in Rust for key preparation.

The core changes involve:

1.  **Modifying `LookupIndex`:** Store the index as `HashMap<u64, Value>` where the `u64` key represents the hash of the original key combination (`Vec<Value>`).
2.  **Modifying `build_lookup_index`:** Instead of building `Vec<Value>` keys row-by-row, use Polars' multi-column hashing capabilities (e.g., `df.columns_to_hashes`) on the source DataFrame *once* to generate a `UInt64Chunked` series of hashes. Populate the `HashMap<u64, Value>` using these hashes and the corresponding values.
3.  **Refactoring Lookup Execution (`execute_scalar_lookup`, `execute_vector_lookup`):**
    *   Calculate the hash(es) for the *input* key Series using the *same* Polars hashing function used during index building.
    *   Use the resulting hash(es) (`u64` or `UInt64Chunked` or `ListChunked<UInt64Type>`) to perform lookups in the `HashMap<u64, Value>`.
    *   Leverage Polars' `apply` or `apply_amortized` methods on the hash Series to perform the lookups efficiently, passing a simple closure that captures the `LookupIndex` and performs the `HashMap::get`.
    *   Eliminate the manual Rust loops for key extraction/conversion.

This approach shifts the iteration logic to Polars and reduces the work done per lookup to a single hash calculation (amortized over the input Series) and a fast `HashMap::get`.

## 3. Implementation Plan

We will implement this refactoring iteratively, ensuring each step is testable.

**Iteration 1: Core Hashing Setup**

*   **Step 1.1: Modify `LookupIndex` Structure**
    *   Change `LookupIndex.index` field from `HashMap<Vec<Value>, Value>` to `HashMap<u64, Value>`.
    *   Update `LookupIndex::new`.
    *   Update `LookupIndex::lookup` to accept `&u64` as the key.
    *   Update existing tests for `LookupIndex` to reflect the new key type (using placeholder u64 values initially).
*   **Step 1.2: Implement DataFrame Hashing Helper**
    *   Create a private helper function `hash_key_columns(df: &DataFrame, key_columns: &[String], build_hasher: PlRandomState) -> PolarsResult<UInt64Chunked>`.
    *   This function uses Polars' `df.columns_to_hashes()` or similar.
    *   Write unit tests for this helper function with various key types (numeric, string, nulls).
*   **Step 1.3: Rewrite `build_lookup_index`**
    *   Modify `build_lookup_index` to call `hash_key_columns` on the input `df`.
    *   Iterate through the resulting `hashes: UInt64Chunked` and the `value_col: Series` simultaneously.
    *   Populate the `HashMap<u64, Value>`, converting values using `any_value_to_value`.
    *   Update tests for `build_lookup_index` to verify the correct `HashMap<u64, Value>` is created based on input DataFrames.

**Iteration 2: Scalar Lookup Refactor**

*   **Step 2.1: Implement Scalar Input Hashing Helper**
    *   Create a private helper function `hash_scalar_keys(keys: &[&Series], build_hasher: PlRandomState) -> PolarsResult<u64>`.
    *   This function ensures all input Series have length 1, extracts the values, creates a temporary 1-row DataFrame (or equivalent structure Polars can hash), and uses the same Polars hashing logic as `hash_key_columns` to produce a single `u64` hash.
    *   Write unit tests for this helper.
*   **Step 2.2: Rewrite `execute_scalar_lookup`**
    *   Replace the old logic with a call to `hash_scalar_keys`.
    *   Use the resulting `u64` hash to perform `lookup_index.lookup(&hash)` (which now internally does `index.get(&hash)`).
    *   Create the 1-element result Series as before.
    *   Update tests for scalar lookups.

**Iteration 3: Vector Lookup Refactor (Core Logic)**

*   **Step 3.1: Implement Vector Input Hashing Helper**
    *   Create a private helper function `hash_vector_keys(keys: &[&Series], build_hasher: PlRandomState) -> PolarsResult<Series>`.
    *   This function needs to handle mixed scalar and List inputs:
        *   Identify List columns and scalar columns.
        *   If List columns exist, determine the output length.
        *   Broadcast scalar columns to match the List length if necessary (e.g., using `extend_constant` or checking length).
        *   Explode all List columns.
        *   Combine the (potentially broadcasted) scalar columns and exploded List columns into a flat DataFrame.
        *   Hash this flat DataFrame using `hash_key_columns` -> `flat_hashes: UInt64Chunked`.
        *   Group/implode `flat_hashes` back into a `ListChunked<UInt64Type>` Series based on the original List structure.
        *   If *no* List columns exist, hash the input `keys` directly using `hash_key_columns` -> `UInt64Chunked` Series.
    *   The function returns the resulting hash Series (`UInt64Chunked` or `ListChunked<UInt64Type>`).
    *   Write extensive unit tests covering scalar-only, list-only, and mixed scalar/list inputs with different lengths and nulls.
*   **Step 3.2: Implement `apply` Lookup Closure**
    *   Create a private helper function or define the closure logic inline.
    *   **For scalar hashes (`UInt64Chunked`):** The closure passed to `.apply()` takes `Option<u64>`, captures `Arc<LookupIndex>` (or just `&LookupIndex` if lifetime allows), performs `lookup_index.lookup(&hash).cloned().unwrap_or(Value::Null)`, and maps this `Value` to the appropriate physical type (`Option<f64>`, `Option<String>`, etc.) based on `lookup_index.value_dtype` for the output Series builder.
    *   **For list hashes (`ListChunked<UInt64Type>`):** The closure passed to `.apply_amortized()` takes `Series` (the inner `UInt64Chunked`), captures `Arc<LookupIndex>`, iterates through the inner hashes, performs the lookup for each, collects the results into a new inner `Series` of the correct `value_dtype`, and returns it.
    *   Write unit tests specifically for this mapping logic (Value -> physical type Option based on dtype).
*   **Step 3.3: Rewrite `execute_vector_lookup`**
    *   Remove the old looping logic entirely.
    *   Call `hash_vector_keys` to get the `hash_series`.
    *   Match on the `hash_series` type:
        *   If `UInt64Chunked`, use `hash_series.apply()` with the scalar hash closure.
        *   If `ListChunked<UInt64Type>`, use `hash_series.apply_amortized()` with the list hash closure.
    *   Return the Series produced by the `apply` call.
    *   Update tests for vector lookups, including mixed types and lists.

**Iteration 4: Integration, Cleanup, and Verification**

*   **Step 4.1: Integrate Execution Paths**
    *   Review `perform_vector_lookup` to ensure it correctly identifies the scalar vs. vector input case and calls either `execute_scalar_lookup` or `execute_vector_lookup` appropriately (the `validate_lookup_inputs` function might still be useful here).
*   **Step 4.2: Finalize `perform_lookup`**
    *   Ensure `perform_lookup` correctly acquires the registry and calls `perform_vector_lookup`, handling errors.
*   **Step 4.3: Code Cleanup**
    *   Remove the now-unused functions like `extract_value_from_series`, `extract_value_from_list_series`, `any_value_to_value` (unless kept for value conversion during index build), and the old looping logic.
*   **Step 4.4: Performance Verification**
    *   Run `cargo bench` comparing results to the previous baseline.
    *   Generate `cargo flamegraph` again and verify that the primary bottleneck has shifted away from the lookup execution functions.

## 4. LLM Implementation Prompts

The following prompts can guide a code-generation LLM to implement the refactoring step-by-step.

**(Prompt 1: Modify LookupIndex and Basic Tests)**


Refactor the `gaspatchio_core_lib::index` module for performance. We will switch from using `Vec<Value>` as HashMap keys to using pre-computed `u64` hashes.

**Task:**

1.  Modify the `LookupIndex` struct:
    *   Change the `index` field type from `HashMap<Vec<Value>, Value>` to `HashMap<u64, Value>`.
2.  Update the `LookupIndex::new` constructor accordingly.
3.  Modify the `LookupIndex::lookup` method:
    *   It should now accept `key: &u64` as input.
    *   It should perform `self.index.get(key)`.
    *   Remove the key length check.
4.  Update the existing unit tests for `LookupIndex` (e.g., `test_lookup_index_basic`) to work with `u64` keys. Use arbitrary but distinct `u64` values like `1000`, `2000` etc., for keys in the tests for now.

**File:** `gaspatchio-core/core/src/index.rs`


**(Prompt 2: Implement DataFrame Hashing Helper)**


Building on the previous step, we need a function to generate the `u64` hash keys from a DataFrame's key columns using Polars' built-in hashing.

**Task:**

1.  Import necessary items: `use polars::prelude::{DataFrame, PolarsResult, UInt64Chunked};` and potentially hashing functions/traits from `polars::frame::hash_join` or `polars::functions` if needed, and `polars_core::hashing::hash_to_buckets::PlRandomState`. Ensure `PlRandomState` is available.
2.  Create a private helper function:
    ```rust
    use polars_core::hashing::hash_to_buckets::PlRandomState;
    // ... other imports

    fn hash_key_columns(
        df: &DataFrame,
        key_columns: &[String],
        build_hasher: PlRandomState,
    ) -> PolarsResult<UInt64Chunked> {
        // Implementation needed
    }
    ```
3.  Implement the function using `df.columns_to_hashes(build_hasher, Some(key_columns))?`. Handle potential errors.
4.  Write unit tests for `hash_key_columns`:
    *   Test with single and multiple key columns.
    *   Test with different data types (Int64, Float64, String).
    *   Test with null values in keys.
    *   Ensure the output is a `UInt64Chunked` of the correct length.
    *   Use a fixed seed for `PlRandomState` in tests for reproducible hashes, e.g., `PlRandomState::with_seed(0)`.

**File:** `gaspatchio-core/core/src/index.rs` (add the function and tests within the `tests` module).


**(Prompt 3: Rewrite `build_lookup_index`)**


Now, rewrite `build_lookup_index` to use the new `hash_key_columns` helper and populate the `LookupIndex` with `u64` keys.

**Task:**

1.  Modify the signature and implementation of `build_lookup_index`:
    ```rust
    use polars_core::hashing::hash_to_buckets::PlRandomState;
    // ... other imports

    fn build_lookup_index(
        df: &DataFrame,
        key_columns: &[String],
        value_column: &str,
    ) -> PolarsResult<(HashMap<u64, Value>, DataType)> {
        // Implementation needed
    }
    ```
2.  Inside the function:
    *   Get the `value_col` Series and its `value_dtype`.
    *   Create a `PlRandomState` (e.g., `PlRandomState::default()` or with a fixed seed if consistency across runs is desired, though default is usually fine here).
    *   Call `hash_key_columns(df, key_columns, build_hasher)` to get `hashes: UInt64Chunked`.
    *   Initialize `index: HashMap<u64, Value>`.
    *   Iterate through `hashes` and `value_col` simultaneously (e.g., using `hashes.into_iter().zip(value_col.into_iter())`).
    *   For each `(Some(hash), Some(value_any))`, convert `value_any` to `value_enum` using `any_value_to_value`.
    *   Insert `(hash, value_enum)` into the `index` HashMap. Handle potential nulls in hash or value appropriately (e.g., skip rows with null hashes, convert null values to `Value::Null`).
    *   Return the populated `index` HashMap and the `value_dtype`.
3.  Update the unit tests for `build_lookup_index` (e.g., `test_build_lookup_index_single_key`, `test_build_lookup_index_multi_key`, etc.):
    *   Verify the returned `HashMap` contains the expected number of entries.
    *   To check specific entries, you'll need to manually hash the expected key combinations using the *same* hashing logic/seed as the function *or* verify based on known non-collision inputs for simplicity in the test.

**File:** `gaspatchio-core/core/src/index.rs`

**(Prompt 4: Implement Scalar Input Hashing Helper)**


We need a way to hash the input keys when they are all scalar (length 1 Series) for the `execute_scalar_lookup` function.

**Task:**

1.  Create a private helper function:
    ```rust
    use polars_core::hashing::hash_to_buckets::PlRandomState;
    // ... other imports

    fn hash_scalar_keys(
        keys: &[&Series],
        build_hasher: PlRandomState,
    ) -> PolarsResult<u64> {
        // Implementation needed
    }
    ```
2.  Implement the function:
    *   Check that all Series in `keys` have `len() == 1`.
    *   Extract the first value (`AnyValue`) from each Series.
    *   Create a temporary 1-row `DataFrame` from these scalar values (this might be tricky, consider creating Series from the single values first: `Series::new(name, &[value])`). Use placeholder names.
    *   Call `hash_key_columns` on this temporary DataFrame with the hasher.
    *   Extract the single `u64` hash value from the resulting `UInt64Chunked`. Handle potential nulls/errors.
3.  Write unit tests for `hash_scalar_keys` using various scalar inputs (numeric, string, nulls) and a fixed seed hasher. Verify the output hash.

**File:** `gaspatchio-core/core/src/index.rs` (add function and tests).


**(Prompt 5: Rewrite `execute_scalar_lookup`)**


Rewrite `execute_scalar_lookup` to use the new `hash_scalar_keys` helper and the `u64`-keyed `LookupIndex`.

**Task:**

1.  Modify `execute_scalar_lookup`:
    ```rust
    fn execute_scalar_lookup(
        lookup_index: &LookupIndex,
        keys: &[&Series],
    ) -> PolarsResult<Series> {
        // Implementation needed
    }
    ```
2.  Implement the function:
    *   Create a `PlRandomState` (use the same seed/method as in `build_lookup_index` if a fixed seed was chosen, otherwise `default()` is likely fine).
    *   Call `hash_scalar_keys(keys, build_hasher)` to get the `input_hash: u64`.
    *   Perform the lookup: `let value_option = lookup_index.lookup(&input_hash);`
    *   Get the `result_value = value_option.cloned().unwrap_or(Value::Null);`
    *   Create the 1-element result Series using `create_series_from_values(&[result_value], ..., lookup_index.value_dtype)`.
3.  Update unit tests for scalar lookups to ensure they still pass with the refactored logic.

**File:** `gaspatchio-core/core/src/index.rs`

**(Prompt 6: Implement Vector Input Hashing Helper)**

This is a complex step. Implement the helper function to hash vector inputs, handling mixed scalar/list types and producing the correct shape of hash Series (`UInt64Chunked` or `ListChunked<UInt64Type>`).

**Task:**

1.  Create the private helper function:
    ```rust
    use polars_core::hashing::hash_to_buckets::PlRandomState;
    // ... other imports

    fn hash_vector_keys(
        keys: &[&Series],
        build_hasher: PlRandomState,
    ) -> PolarsResult<Series> {
        // Implementation needed
    }
    ```
2.  Implement the logic described in the plan (Step 3.1):
    *   Identify list columns and scalar columns using `series.dtype()`.
    *   **Case 1: No List columns:** Call `hash_key_columns` directly on a temporary DataFrame made from `keys`.
    *   **Case 2: List columns exist:**
        *   Determine output length from the first list column.
        *   Validate lengths of all list columns and scalar columns (scalar must be 1 or match list length).
        *   Create a Vec of Series to hash: clone scalar columns, explode list columns.
        *   Broadcast length-1 scalar columns if necessary (e.g., using `s.extend_constant(None, list_len - 1)?` after getting the first value, or building a new Series).
        *   Create a flat DataFrame from these potentially exploded/broadcasted Series.
        *   Hash the flat DataFrame using `hash_key_columns` -> `flat_hashes: UInt64Chunked`.
        *   Determine the grouping offsets based on the original list structure (e.g., lengths of inner lists).
        *   Implode `flat_hashes` back into a `ListChunked<UInt64Type>` using the offsets (this might require manual building or finding a suitable Polars function).
    *   Return the resulting hash Series (`UInt64Chunked` or `ListChunked<UInt64Type>`).
3.  Write comprehensive unit tests for `hash_vector_keys`:
    *   Scalar inputs only.
    *   List inputs only.
    *   Mixed scalar (len 1) and list inputs.
    *   Mixed scalar (len N) and list (len N) inputs.
    *   Inputs with nulls.
    *   Edge cases (empty lists, empty input Series).
    *   Use a fixed seed hasher.

**File:** `gaspatchio-core/core/src/index.rs` (add function and tests).


**(Prompt 7: Implement `apply` Lookup Closure Logic)**


Define the logic that will be used inside the `.apply()` or `.apply_amortized()` calls to perform the actual lookup using the pre-computed hash.

**Task:**

1.  Define a helper function (or prepare the closure logic) that takes `hash_option: Option<u64>`, `lookup_index: &LookupIndex`, and returns an `Option<PhysicalType>` (e.g., `Option<f64>`, `Option<String>`) suitable for the `.apply` builder, based on `lookup_index.value_dtype`.
    ```rust
    // Example helper signature (adapt as needed for closure capture)
    fn lookup_value_by_hash(
        hash_option: Option<u64>,
        lookup_index: &LookupIndex, // Or capture Arc<LookupIndex>
    ) -> Option<[PhysicalType]> { // Replace [PhysicalType] e.g. with f64
        match hash_option {
            Some(hash) => {
                match lookup_index.lookup(&hash) { // lookup now takes &u64
                    Some(Value::Float(f)) => Some(*f),
                    Some(Value::Int(i)) => Some(*i as [PhysicalType]), // Adjust type cast
                    Some(Value::String(s)) => Some(s.clone()), // Or handle String differently
                    Some(Value::Null) => None,
                    None => None, // Hash not found
                }
            }
            None => None, // Hash was null
        }
    }
    ```
2.  **Crucially:** Adapt the return type and logic within the `match lookup_index.lookup()` block to correctly extract/convert the `Value` enum into the specific `Option<PhysicalType>` expected by the `.apply` function based on `lookup_index.value_dtype`. You might need separate helper functions or a generic approach depending on how you structure the `apply` call later.
3.  **For `apply_amortized`:** Define similar logic, but the function/closure will receive a `Series` (inner list of hashes: `UInt64Chunked`) and must return a `Series` (inner list of results). It will iterate through the input inner hashes, call `lookup_index.lookup`, collect results, and build the output inner `Series` using `create_series_from_values` or typed builders.
4.  Write unit tests for this value mapping logic, ensuring correct conversion from `Value` to different physical types and handling of nulls/not found cases.

**File:** `gaspatchio-core/core/src/index.rs` (add helper function/logic and tests).


**(Prompt 8: Rewrite `execute_vector_lookup`)**


Rewrite `execute_vector_lookup` to use the vector hashing helper and the `apply`/`apply_amortized` pattern with the lookup closure logic.

**Task:**

1.  Modify `execute_vector_lookup`:
    ```rust
    fn execute_vector_lookup(
        lookup_index: &LookupIndex,
        keys: &[&Series],
        _output_len: usize, // output_len might become redundant
        _vector_indices: &[usize], // vector_indices might become redundant
    ) -> PolarsResult<Series> {
        // Implementation needed
    }
    ```
2.  Implement the function:
    *   Create the `PlRandomState` hasher (consistent with build step).
    *   Call `hash_vector_keys(keys, build_hasher)` to get `hash_series: Series`.
    *   `let value_dtype = &lookup_index.value_dtype;`
    *   `let captured_index = Arc::new(lookup_index.clone()); // Clone index for capture if needed, or manage lifetime`
    *   Match on `hash_series.dtype()`:
        *   **Case `DataType::UInt64`:**
            *   `let ca = hash_series.u64()?;`
            *   Use `ca.apply(|hash_option: Option<u64>| { ... })`.
            *   The closure uses the logic from Prompt 7 (scalar hash version) capturing `captured_index` and using `value_dtype` to return the correct `Option<PhysicalType>`.
            *   Collect the results into the final output Series (the return type of `apply` depends on the closure's return).
        *   **Case `DataType::List(DataType::UInt64)`:**
            *   `let ca = hash_series.list()?;`
            *   Use `ca.apply_amortized(|inner_hash_series: Series| { ... })`.
            *   The closure uses the logic from Prompt 7 (list hash version) capturing `captured_index`.
            *   It takes the `inner_hash_series` (which is `UInt64Chunked`), iterates its hashes, performs lookups, and builds/returns a *new inner result Series* using `create_series_from_values` or typed builders based on `value_dtype`.
        *   **Case `_`:** Return an error.
    *   Return the Series generated by the `apply` or `apply_amortized` call.
3.  Remove the old looping code from this function.
4.  Update unit tests for vector lookups (`test_mixed_vector_scalar_lookup` etc.) to ensure they pass with the refactored `apply`-based logic.

**File:** `gaspatchio-core/core/src/index.rs`

**(Prompt 9: Integration, Cleanup, and Verification)**


Finalize the integration, clean up unused code, and prepare for performance verification.

**Task:**

1.  Review `perform_vector_lookup`:
    *   Ensure `validate_lookup_inputs` is still called if necessary (it might be less critical now, as hashing handles shape).
    *   Ensure it correctly determines whether to call `execute_scalar_lookup` or `execute_vector_lookup` based on the *input* `keys` structure (e.g., using `any_vectors` from validation).
2.  Review `perform_lookup`:
    *   Ensure it correctly calls `registry.lookup_vector(...)` which now delegates to the refactored `perform_vector_lookup`.
    *   Verify error handling (`map_err`) is still correct.
3.  **Cleanup:**
    *   Search for and remove the old helper functions that are no longer used: `extract_value_from_series`, `extract_value_from_list_series`.
    *   Remove the old `Value::String` conversion logic if string interning wasn't implemented and `any_value_to_value` is only used for non-string types during index build.
    *   Remove any other dead code related to the old loop-based implementation.
4.  Run `cargo check` and `cargo test` to ensure everything compiles and tests pass.
5.  **(Manual Step):** Run `cargo bench` and `cargo flamegraph` as described previously to verify the performance improvement. Document the results.

**File:** `gaspatchio-core/core/src/index.rs`
```

This detailed plan and set of prompts should guide the refactoring process effectively, resulting in a much faster lookup implementation.
