Below is a revised **developer specification** for creating and maintaining a Rust-based "Table Registry" that uses **ArcSwap** for near lock-free concurrency. The specification focuses on a design where tables (Polars DataFrames) are loaded once into memory and remain globally available for high-speed joins. Key columns for joins are tracked via **KeySpec**. We'll integrate with Python using [PyO3](https://pyo3.rs/) and optionally [pyo3-polars](https://github.com/pola-rs/pyo3-polars).

---

# Developer Specification: In-Memory Polars Table Registry Using ArcSwap

## 1. Purpose

- **High Performance**: Load assumption tables (e.g. mortality, lapse, premium) into memory as Polars `DataFrame`s.  
- **Batch Lookups**: Provide equi-join–based lookups for large query DataFrames without re-reading Parquet.  
- **Dynamic Registration**: Infrequently register or update new tables during runtime.  
- **Near Lock-Free Reads**: Achieve minimal read contention using [`ArcSwap`](https://crates.io/crates/arc-swap).
- **Support Various Table Formats**: Handle different table structures including wide and long formats.

## 2. Requirements

1. **In-Memory Storage**: All tables must fit in memory.  
2. **Rare Updates**: Table registrations or updates should be relatively infrequent compared to the volume of lookups.  
3. **Batch Joins**: We rely on Polars's parallel join for performance. A single table can contain millions of rows; queries can contain millions of rows.  
4. **Concurrency**: Multiple threads or Python calls can read (i.e., join) concurrently. Registration must not block ongoing reads.  
5. **Dynamic Key Columns**: Each table can define different sets of key columns (e.g. `(year, sex, smoking)` vs `(year, age, duration)`) for equi-joins.
6. **Table Format Transformation**: Support for transforming wide-format tables to long-format before registration when needed.

## 3. Core Data Structures

### 3.1 `KeySpec`

```rust
#[derive(Debug, Clone)]
pub struct KeySpec {
    /// The columns in the query DataFrame (the "left side").
    pub source_cols: Vec<String>,
    /// The corresponding columns in the registered table (the "right side").
    pub table_cols: Vec<String>,
}
```

- Allows the system to handle variable column names for each table's join.
- For advanced range-joins or transformations (e.g. "bmi" vs "bmi_range"), additional logic or preprocessing might be required.

### 3.2 `TableRegistry`

```rust
#[derive(Default, Clone)]
pub struct TableRegistry {
    pub tables: std::collections::HashMap<String, polars::prelude::DataFrame>,
    pub keyspecs: std::collections::HashMap<String, KeySpec>,
}
```

- Maps a table name (e.g. `"mortality"`) to:
  - The **in-memory** Polars `DataFrame`.
  - A **KeySpec** describing how to join query DataFrames with that table.
- `Clone` is used for copying the entire registry when we need to register a new table.

### 3.3 Global Registry Reference Using ArcSwap

```rust
use arc_swap::ArcSwap;
use once_cell::sync::Lazy;

static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    ArcSwap::from_pointee(TableRegistry::default())
});
```

- **`ArcSwap`** allows near lock-free reads:
  - Reading threads just do `REGISTRY.load()` to get an `Arc<TableRegistry>`.
  - Writing (registration) requires creating a new `TableRegistry` from the old, then `store()`ing it.

## 4. Operations

### 4.1 Register a Table

1. **Python or Rust** calls a function `py_register_table(table_name, df, source_cols, table_cols)`.  
2. For tables in wide format (e.g., mortality tables), transform to long format before registration.
3. We do the following:

   ```rust
   let old_registry = REGISTRY.load().clone();
   let mut new_registry = (*old_registry).clone();
   new_registry.tables.insert(table_name.to_string(), df);
   new_registry.keyspecs.insert(table_name.to_string(), KeySpec {
       source_cols,
       table_cols
   });
   REGISTRY.store(std::sync::Arc::new(new_registry));
   ```

4. Readers already using the old registry keep using it. New readers see the newly registered table.

### 4.2 Lookup (Join)

Given a `table_name` and a `DataFrame` (the "query DF"):

1. Get the current registry:

   ```rust
   let registry_arc = REGISTRY.load().clone();
   ```

2. Fetch the appropriate `DataFrame` and `KeySpec`:

   ```rust
   let table_df = registry_arc.tables.get(table_name).ok_or(...)?;
   let key_spec = registry_arc.keyspecs.get(table_name).ok_or(...)?;
   ```

3. Perform the Polars join:

   ```rust
   let joined = query_df.lazy()
       .join(
           table_df.clone().lazy(),
           key_spec.source_cols.clone(),
           key_spec.table_cols.clone(),
           polars::prelude::JoinType::Left,
       )
       .collect()?;
   ```

4. Return the joined result (as a Polars `DataFrame` or `PyDataFrame`).

### 4.3 Table Format Transformation

For tables that require transformation before registration (e.g., wide-format mortality tables), we need an additional preprocessing step:

```rust
fn transform_wide_to_long(df: &DataFrame, id_vars: &[&str], value_vars: &[&str], 
                         var_name: &str, value_name: &str) -> PolarsResult<DataFrame> {
    // Use Polars' melt operation to transform from wide to long format
    df.lazy()
        .melt(
            id_vars.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            value_vars.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            Some(var_name.to_string()),
            Some(value_name.to_string()),
        )
        .collect()
}

// Example usage for mortality tables
let mortality_long = transform_wide_to_long(
    &mortality_wide, 
    &["age-last"], 
    &["MNS", "FNS", "MS", "FS"],
    "gender_smoking",
    "mortality_rate"
)?;
```

**Example**: Transforming a wide-format mortality table to long format:

**Wide Format (Original):**
```
┌──────────┬──────┬──────┬──────┬──────┐
│ age-last │ MNS  │ FNS  │ MS   │ FS   │
│ ---      │ ---  │ ---  │ ---  │ ---  │
│ i64      │ f64  │ f64  │ f64  │ f64  │
╞══════════╪══════╪══════╪══════╪══════╡
│ 9        │ 0.0001│0.000097│0.00012│0.0001164│
│ 10       │ 0.0001│0.000097│0.00012│0.0001164│
│ 11       │ 0.0001│0.000097│0.00012│0.0001164│
└──────────┴──────┴──────┴──────┴──────┘
```

**Long Format (Transformed for Registry):**
```
┌──────────┬───────────────┬───────────────┐
│ age-last │ gender_smoking │ mortality_rate │
│ ---      │ ---           │ ---           │
│ i64      │ str           │ f64           │
╞══════════╪═══════════════╪═══════════════╡
│ 9        │ MNS           │ 0.0001        │
│ 9        │ FNS           │ 0.000097      │
│ 9        │ MS            │ 0.00012       │
│ 9        │ FS            │ 0.0001164     │
│ 10       │ MNS           │ 0.0001        │
│ 10       │ FNS           │ 0.000097      │
│ 10       │ MS            │ 0.00012       │
│ 10       │ FS            │ 0.0001164     │
│ 11       │ MNS           │ 0.0001        │
│ 11       │ FNS           │ 0.000097      │
│ 11       │ MS            │ 0.00012       │
│ 11       │ FS            │ 0.0001164     │
└──────────┴───────────────┴───────────────┘
```

## 5. Sample Implementation

<details>
<summary><b>Code Example</b></summary>

```rust
use std::collections::HashMap;
use std::sync::Arc;

use pyo3::prelude::*;
use pyo3::wrap_pyfunction;
use pyo3_polars::PyDataFrame;
use polars::prelude::*;
use arc_swap::ArcSwap;
use once_cell::sync::Lazy;

#[derive(Debug, Clone)]
pub struct KeySpec {
    pub source_cols: Vec<String>,
    pub table_cols: Vec<String>,
}

#[derive(Default, Clone)]
pub struct TableRegistry {
    pub tables: HashMap<String, DataFrame>,
    pub keyspecs: HashMap<String, KeySpec>,
}

impl TableRegistry {
    pub fn register_table(&mut self, table_name: &str, df: DataFrame, key_spec: KeySpec) {
        self.tables.insert(table_name.to_string(), df);
        self.keyspecs.insert(table_name.to_string(), key_spec);
    }
}

// Global registry with ArcSwap
static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    ArcSwap::from_pointee(TableRegistry::default())
});

fn get_registry() -> Arc<TableRegistry> {
    REGISTRY.load().clone()
}

/// Replaces the entire registry
fn set_registry(new_reg: TableRegistry) {
    REGISTRY.store(Arc::new(new_reg));
}

/// Transform a wide DataFrame to long format
fn transform_wide_to_long(
    df: &DataFrame,
    id_vars: &[&str],
    value_vars: &[&str],
    var_name: &str,
    value_name: &str,
) -> PolarsResult<DataFrame> {
    df.lazy()
        .melt(
            id_vars.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            value_vars.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            Some(var_name.to_string()),
            Some(value_name.to_string()),
        )
        .collect()
}

#[pyfunction]
fn py_register_table(
    table_name: &str,
    py_df: PyDataFrame,
    source_cols: Vec<String>,
    table_cols: Vec<String>,
    transform_spec: Option<HashMap<String, Vec<String>>>,
) -> PyResult<()> {
    // Convert from PyDataFrame -> Polars DataFrame
    let mut df = py_df.df.clone();

    // Apply transformations if specified
    if let Some(spec) = transform_spec {
        if let (Some(id_vars), Some(value_vars), Some(var_name), Some(value_name)) = (
            spec.get("id_vars"),
            spec.get("value_vars"),
            spec.get("var_name"),
            spec.get("value_name"),
        ) {
            df = transform_wide_to_long(
                &df,
                &id_vars.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
                &value_vars.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
                var_name[0].as_str(),
                value_name[0].as_str(),
            )?;
        }
    }

    let ks = KeySpec {
        source_cols,
        table_cols,
    };

    // Create new registry from old
    let old = get_registry();
    let mut new_registry = (*old).clone();

    // Register table
    new_registry.register_table(table_name, df, ks);

    // Atomically swap
    set_registry(new_registry);

    Ok(())
}

/// Perform a Polars join in Rust, returning the joined DataFrame
#[pyfunction]
fn py_lookup(
    table_name: &str,
    py_queries: PyDataFrame,
) -> PyResult<PyDataFrame> {
    // Grab the current registry
    let registry = get_registry();

    // Retrieve the DataFrame and KeySpec
    let table_df = registry.tables.get(table_name)
        .ok_or_else(|| PolarsError::ComputeError(format!("No table: {table_name}").into()))?;
    let ks = registry.keyspecs.get(table_name)
        .ok_or_else(|| PolarsError::ComputeError(format!("No KeySpec: {table_name}").into()))?;

    // Convert from PyDataFrame -> Polars DataFrame
    let queries = py_queries.df.clone();

    // Do a join
    let joined = queries
        .lazy()
        .join(
            table_df.clone().lazy(),
            ks.source_cols.clone(),
            ks.table_cols.clone(),
            JoinType::Left,
        )
        .collect()
        .map_err(|e| PolarsError::ComputeError(format!("Join error: {e}").into()))?;

    // Convert back to PyDataFrame
    Ok(PyDataFrame::from(joined))
}

// Expose via a PyO3 module
#[pymodule]
fn myrustmod(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_register_table, m)?)?;
    m.add_function(wrap_pyfunction!(py_lookup, m)?)?;
    Ok(())
}
```
</details>

**Notes**:  
- **ArcSwap** provides near lock-free reads (just an atomic pointer read), suitable for read-heavy scenarios with rare writes.  
- **Copying the Registry**: Each time you register a table, you clone the entire `HashMap`. For many large tables, this could be expensive. However, given the "rare updates" assumption, it's typically acceptable.
- **Table Transformation**: Wide-format tables like mortality tables require transformation to long format before registration to enable effective equi-joins.

## 6. Testing & Validation

### 6.1 Unit Tests

- **Register Single Table**: Confirm it appears in the registry.  
- **Lookup**: Provide a small "queries" DataFrame, ensure the joined results are correct (including handling of unmatched keys).  
- **Multiple Registrations**: Register "mortality," then "lapse," confirm both exist.  
- **Format Transformation**: Test wide-to-long transformation for tables like mortality tables.

### 6.2 Integration Tests

- **Python**: Write tests that call `py_register_table` and `py_lookup` in Python, verifying correct merges.  
- **Concurrency**: Possibly spawn threads that repeatedly call `py_lookup` while another thread registers new tables. Ensure no panics or data races.

### 6.3 Performance & Monitoring

- **Benchmark**: 
  - **Large Joins**: 1 million rows in the table × 1 million queries.  
  - **Frequent vs Rare Registration**: If we do repeated registrations, measure overhead of `HashMap::clone()`.  
- **Profiling**: 
  - Use `cargo flamegraph` or `perf` to see time spent in Polars join or ArcSwap pointer reads.  
- **Logging**:
  - Log table sizes, column names, and registration times to quickly detect large overheads.  

### 6.4 Specific Table Type Tests

#### 6.4.1 Mortality Table Tests

1. **Wide Format Registration and Lookup**:
   - Register a wide-format mortality table with columns: `age-last`, `MNS`, `FNS`, `MS`, `FS`
   - Transform to long format during registration
   - Test lookup with various age/gender/smoking combinations
   - Verify correct rates are returned

2. **Compound Key Lookup**:
   - Create a query with `age_last` and `gender_smoking` columns
   - Verify that a compound key lookup returns correct rates
   - Test edge cases (e.g., ages outside the table range)

3. **Performance Test**:
   - Test with 100+ ages and 4+ gender/smoking combinations
   - Benchmark lookup performance for 1 million policy records

#### 6.4.2 Lapse Table Tests

1. **Year-Based Lapse Rates**:
   - Register a lapse table with `policy_year` and `lapse_rate` columns
   - Test lookups based on policy year
   - Verify correct rates for different policy years

2. **Multiple Factor Lapses**:
   - Register a lapse table with multiple factors: `policy_year`, `premium_band`, `distribution_channel`
   - Test lookups with combinations of these factors
   - Verify correct rates for various combinations

#### 6.4.3 Premium Rate Tests

1. **Multi-Factor Premium Lookup**:
   - Register a premium table with factors like `age`, `gender`, `smoker_status`, `coverage_amount`
   - Test lookups with various combinations
   - Verify correct premium rates

2. **Banded Factor Lookup**:
   - Test with coverage bands instead of exact amounts
   - Verify that the correct band is selected for a given coverage amount

#### 6.4.4 Benefit Factor Tests

1. **Interpolation Tests** (if implemented):
   - Register a table with discrete values
   - Test lookups with values between the discrete points
   - Verify interpolation results match expectations

2. **Multi-Dimensional Factors**:
   - Register a table with interacting factors (e.g., age and duration)
   - Test lookups with various combinations
   - Verify correct factors are returned

## 7. Trade-offs & Alternatives

1. **ArcSwap vs `RwLock`**  
   - ArcSwap: Lock-free reads, but entire registry is cloned on each update.  
   - `RwLock`: Partial updates in place, but read operations share a lock (though typically an RwLock allows concurrent reads).  

2. **Range Joins**  
   - Polars only supports equi-joins. Range-based logic (e.g., "bmi in [low, high)") requires custom transformations or discrete "bmi_bucket" columns.  

3. **Multiple KeySpecs**  
   - If a single table can be joined in different ways, store a vector of `KeySpec`s or a map keyed by a "join type" string.  

4. **Direct HashMap**  
   - For truly single-row lookups in a loop, building a `(key) -> (record)` in Rust might be even faster. But for large, batch column-based queries, Polars is optimal.

5. **Table Format Storage**
   - **Wide Format**: More compact for storage, but requires transformation for equi-joins.
   - **Long Format**: Larger storage footprint, but directly usable for equi-joins.
   - **Hybrid Approach**: Store in wide format on disk, transform to long format during registration.

---

## 8. Conclusion

This **ArcSwap-based** solution provides a robust, thread-safe approach for:

- **Registering** in-memory DataFrames,
- Storing **KeySpec** metadata,
- **Performing** high-throughput Polars joins for batch lookups,
- **Transforming** table formats as needed before registration,
- Minimizing read contention thanks to ArcSwap's atomic pointer swapping.

Next steps for the developer:

1. **Implement** or adapt the provided sample code.  
2. **Add** unit, integration, and performance tests for your domain data.  
3. **Monitor** memory usage and concurrency overhead, adjust if table registration becomes frequent.  

With this architecture in place, you'll have an easily extensible system for domain-specific data lookups using Polars's efficient in-memory joins, capable of handling various table structures and lookup patterns commonly found in actuarial calculations.