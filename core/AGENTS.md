# gaspatchio-core / core — Rust development rules

Canonical contributor rules for the Rust core crate (`gaspatchio_core_lib`). Read natively
by AI coding agents (Codex, Amp, Cursor, Gemini CLI, Copilot) and by Claude Code via the
sibling `CLAUDE.md` import shim. Applies to all `*.rs` files under `core/`.

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

---

## Rust Development Standards

### Cargo and Dependency Management

This rule enforces best practices for Cargo and dependency management in Rust projects.

#### Rule Details

- **Pattern**: `Cargo.toml`
- **Severity**: Warning
- **Category**: Dependencies

#### Checks

1. **Dependency Management**
   - Use specific version constraints
   - Avoid using `*` or `>=` for versions
   - Use workspace dependencies when appropriate
   - Document dependency purposes

2. **Feature Flags**
   - Use feature flags for optional functionality
   - Document feature requirements
   - Use `default-features = false` when appropriate
   - Group related features

3. **Workspace Organization**
   - Use workspaces for related crates
   - Share common dependencies
   - Use path dependencies for local crates
   - Organize crates logically

4. **Build Configuration**
   - Use appropriate profiles
   - Configure build scripts properly
   - Use conditional compilation
   - Document build requirements

#### Examples

##### Good
```toml
[package]
name = "my-project"
version = "0.1.0"
edition = "2021"
authors = ["Your Name <your.email@example.com>"]
description = "A well-documented project"
license = "MIT"

[dependencies]
# Use specific versions with caret
tokio = { version = "1.28", features = ["full"] }
serde = { version = "1.0", features = ["derive"] }
log = "0.4"
env_logger = "0.10"

# Optional features
my-crate = { version = "0.5", optional = true }

[features]
default = ["my-crate"]
# Group related features
async = ["tokio/async"]
json = ["serde/json"]

[workspace]
members = [
    "core",
    "cli",
    "web"
]

[profile.release]
lto = true
codegen-units = 1
panic = "abort"

[build-dependencies]
cc = "1.0"
```

##### Bad
```toml
[package]
name = "bad-project"
version = "0.1.0"

[dependencies]
# Bad: Using wildcard version
tokio = "*"
# Bad: Using >= for version
serde = ">=1.0"
# Bad: Missing feature specification
log = "0.4"

# Bad: Unorganized features
[features]
feature1 = []
feature2 = []
feature3 = []

# Bad: Missing workspace organization
[workspace]
members = ["*"]
```

### Documentation

This rule enforces best practices for documentation in Rust code.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Warning
- **Category**: Documentation

#### Checks

1. **Public API Documentation**
   - Document all public items (types, functions, methods)
   - Include examples in documentation
   - Use `rustdoc` features appropriately
   - Document panics and safety requirements

2. **Documentation Style**
   - Use complete sentences
   - Start with a verb
   - Include parameter and return value descriptions
   - Document error conditions

3. **Code Examples**
   - Include runnable examples
   - Use `no_run` or `compile_fail` when appropriate
   - Show common usage patterns
   - Include error handling examples

4. **Module Documentation**
   - Document module purpose and contents
   - Include usage examples
   - Document re-exports
   - Include module-level examples

#### Examples

##### Good
```rust
/// Creates a new `Database` instance with the specified configuration.
///
/// # Arguments
///
/// * `config` - The database configuration to use
///
/// # Returns
///
/// A `Result` containing either the new `Database` instance or a `DatabaseError`
///
/// # Examples
///
/// ```
/// use my_crate::Database;
///
/// let config = DatabaseConfig::default();
/// let db = Database::new(config)?;
/// ```
///
/// # Errors
///
/// Returns `DatabaseError::ConnectionFailed` if the database connection cannot be established
pub fn new(config: DatabaseConfig) -> Result<Database, DatabaseError> {
    // Implementation
}

/// A thread-safe reference-counted pointer to shared data.
///
/// This type provides interior mutability with runtime borrow checking.
/// It is useful when you need to share mutable state between multiple owners.
///
/// # Examples
///
/// ```
/// use std::cell::RefCell;
///
/// let data = RefCell::new(vec![1, 2, 3]);
/// {
///     let mut vec = data.borrow_mut();
///     vec.push(4);
/// }
/// ```
pub struct SharedData<T> {
    // Implementation
}
```

##### Bad
```rust
// Missing documentation
pub fn process(data: Vec<u8>) -> Result<(), Error> {
    // Implementation
}

/// Process the data
/// 
/// Bad: Too vague, missing parameters, return value, and examples
pub fn bad_doc(data: Vec<u8>) -> Result<(), Error> {
    // Implementation
}
```

### Error Handling

This rule enforces best practices for error handling in Rust code.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Error Handling

#### Checks

1. **Result Type Usage**
   - Use `Result<T, E>` for recoverable errors
   - Avoid using `Option` for error cases
   - Prefer custom error types over `String` or `Box<dyn Error>`

2. **Error Propagation**
   - Use `?` operator for error propagation
   - Avoid excessive error mapping
   - Implement `From` trait for error type conversions

3. **Error Types**
   - Create custom error types using `thiserror` or `anyhow`
   - Implement `std::error::Error` trait
   - Use meaningful error variants

4. **Panic Handling**
   - Avoid using `unwrap()` and `expect()` in production code
   - Use `panic!` only for unrecoverable errors
   - Document panic conditions

#### Examples

##### Good
```rust
#[derive(Debug, thiserror::Error)]
enum DatabaseError {
    #[error("Connection failed: {0}")]
    ConnectionError(String),
    #[error("Query failed: {0}")]
    QueryError(String),
}

fn query_database() -> Result<Data, DatabaseError> {
    // Proper error handling with custom type
    if connection_failed() {
        return Err(DatabaseError::ConnectionError("Failed to connect".into()));
    }
    Ok(data)
}
```

##### Bad
```rust
fn query_database() -> Option<Data> {
    // Using Option for error cases
    if connection_failed() {
        return None;
    }
    Some(data)
}

fn process_data() -> Result<(), Box<dyn Error>> {
    // Using generic error type
    data.unwrap() // Using unwrap in production code
}
```

### Observability and Logging

This rule enforces best practices for logging, tracing, and metrics in Rust applications.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Warning
- **Category**: Observability

#### Checks

1. **Structured Logging**
   - Use `tracing` instead of `log`
   - Include contextual information
   - Use appropriate log levels
   - Add structured fields to events

2. **Span Usage**
   - Create spans for significant operations
   - Use `#[instrument]` for function tracing
   - Record important events within spans
   - Use span relationships appropriately

3. **Metrics Collection**
   - Use `metrics` crate for metrics
   - Record meaningful metrics
   - Use appropriate metric types
   - Include relevant labels

4. **Error Tracking**
   - Record errors with context
   - Use error spans for debugging
   - Include error details in events
   - Track error frequencies

#### Examples

##### Good
```rust
use tracing::{info, error, instrument, Level};
use metrics::{counter, gauge};

#[instrument(level = Level::INFO, skip(input))]
pub async fn process_data(input: &[u8]) -> Result<(), Error> {
    // Record metric for input size
    gauge!("data.input.size", input.len() as f64);
    
    // Create a span for the processing operation
    let span = tracing::info_span!("processing_data");
    let _guard = span.enter();
    
    // Record structured event
    info!(
        input_size = input.len(),
        "Starting data processing"
    );
    
    match process(input).await {
        Ok(result) => {
            // Record success metric
            counter!("data.process.success", 1);
            info!(
                result_size = result.len(),
                "Data processing completed"
            );
            Ok(())
        }
        Err(e) => {
            // Record error metric
            counter!("data.process.error", 1);
            error!(
                error = %e,
                error_type = std::any::type_name_of_val(&e),
                "Data processing failed"
            );
            Err(e)
        }
    }
}

/// A service that uses tracing for observability
#[derive(Debug)]
pub struct Service {
    name: String,
}

impl Service {
    #[instrument(level = Level::DEBUG)]
    pub fn new(name: String) -> Self {
        info!(name = %name, "Creating new service");
        Self { name }
    }

    #[instrument(level = Level::INFO, skip(self))]
    pub async fn handle_request(&self, request: Request) -> Result<Response, Error> {
        // Record request metric
        counter!("service.requests", 1, "service" => self.name.clone());
        
        let span = tracing::info_span!(
            "handle_request",
            service = %self.name,
            request_id = %request.id
        );
        
        let _guard = span.enter();
        
        info!(
            method = %request.method,
            path = %request.path,
            "Processing request"
        );
        
        // Implementation
    }
}
```

##### Bad
```rust
// Bad: Using println! instead of structured logging
fn process_data(data: &[u8]) {
    println!("Processing data of size {}", data.len());
}

// Bad: Missing context in error logging
fn handle_error(e: Error) {
    error!("Error occurred: {}", e);
}

// Bad: Not using spans for operation tracking
async fn process_request(req: Request) -> Result<Response, Error> {
    // No span tracking
    let result = process(req).await;
    // No metrics
    result
}
```

### Ownership and Borrowing

This rule enforces best practices related to Rust's ownership and borrowing system.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Ownership

#### Checks

1. **Unnecessary Clone Usage**
   - Avoid using `.clone()` when ownership can be transferred
   - Prefer references when possible
   - Use `&str` instead of `String` for string literals

2. **Mutable References**
   - Ensure only one mutable reference exists at a time
   - Avoid unnecessary mutability
   - Use `&mut` only when data needs to be modified

3. **Lifetime Annotations**
   - Add explicit lifetime annotations when compiler cannot infer them
   - Use descriptive lifetime names (e.g., `'a`, `'static`)
   - Ensure lifetime parameters are properly constrained

4. **Reference Counting**
   - Use `Arc` for shared ownership across threads
   - Use `Rc` for shared ownership within a single thread
   - Consider using `Weak` references to break reference cycles

#### Examples

##### Good
```rust
fn process_string(s: &str) {
    // Using string slice instead of owned String
}

fn modify_data(data: &mut Vec<i32>) {
    // Clear mutable reference usage
}
```

##### Bad
```rust
fn process_string(s: String) {
    // Unnecessary ownership transfer
}

fn modify_data(data: &mut Vec<i32>, other: &mut Vec<i32>) {
    // Multiple mutable references to same data
}
```

### Performance and Optimization

This rule enforces best practices for performance optimization in Rust code.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Warning
- **Category**: Performance

#### Checks

1. **Memory Management**
   - Use stack allocation when possible
   - Avoid unnecessary heap allocations
   - Use appropriate collection types (e.g., `Vec` vs `LinkedList`)
   - Implement proper memory reuse

2. **Zero-Cost Abstractions**
   - Leverage compile-time optimizations
   - Use generics for zero-cost abstractions
   - Avoid runtime overhead in hot paths
   - Use const generics where appropriate

3. **Iterator Usage**
   - Use iterator combinators instead of loops
   - Chain iterator operations efficiently
   - Avoid collecting into intermediate collections
   - Use appropriate iterator adapters

4. **Benchmarking**
   - Use `criterion` for benchmarking
   - Profile code with `perf` or `flamegraph`
   - Measure before optimizing
   - Track performance regressions

#### Examples

##### Good
```rust
// Efficient iterator usage
let sum: i32 = numbers
    .iter()
    .filter(|&x| x > &0)
    .map(|x| x * x)
    .sum();

// Zero-cost abstraction
fn process<T: AsRef<str>>(input: T) {
    // Generic function with no runtime overhead
    let s = input.as_ref();
}

// Efficient memory usage
struct EfficientBuffer {
    data: Vec<u8>,
    capacity: usize,
}

impl EfficientBuffer {
    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            data: Vec::with_capacity(capacity),
            capacity,
        }
    }

    pub fn reuse(&mut self) {
        // Reuse the buffer instead of reallocating
        self.data.clear();
    }
}
```

##### Bad
```rust
// Inefficient memory usage
let mut vec = Vec::new();
for i in 0..1000 {
    vec.push(i.to_string()); // Unnecessary heap allocations
}

// Inefficient iterator usage
let result: Vec<_> = numbers
    .iter()
    .filter(|&x| x > &0)
    .collect(); // Unnecessary intermediate collection
let sum: i32 = result.iter().sum();

// Runtime overhead in hot path
fn process_dynamic(input: &dyn AsRef<str>) {
    // Dynamic dispatch in hot path
    let s = input.as_ref();
}
```

### Rust Polars Integration

Polars is a fast, multi-threaded DataFrame library designed for Rust. One of the powerful features of Polars is its 
plugin system, which allows developers to write custom expressions for specialized use cases. This document 
focuses on how to specify output data types in expression plugins, ensuring that Polars understands and properly 
handles the data returned by your custom function.

#### Output Data Types in Polars Plugins

When building a plugin function, you must define the function's signature, including specifying the expected input 
data type and the function return type. Within Polars, if the output data type isn't specified, Polars tries to 
infer the type from the function return signature. This works fine for well-known types. For advanced or custom 
types, it might be necessary to explicitly specify the function's output data type.

To define the output data type, Polars allows you to set the attribute `#[polars_expr(output_type_func = function_name)]` 
above your function. This attribute points to a helper function returning the `DataType` the plugin will produce.

#### Documentation : 

Always refernce @polarsRust when writing polars rust code. 

#### Examples:

When creating a dataframe with vectors ensure you call .into()
##### Good : Creating a dataframe with vectors ✅

```rust
        let df = df! {
            "id" => [1, 2],
            "scalar" => ["a", "b"],
            "vector" => ListChunked::from_iter([
                Some(Series::new("".into() vec![10, 20])),
                Some(Series::new("".into(), vec![30, 40, 50]))
            ]).into_series()
```

##### Bad : Creating a dataframe with vectors ❌

```rust
        let df = df! {
            "id" => [1, 2],
            "scalar" => ["a", "b"],
            "vector" => ListChunked::from_iter([
                Some(Series::new("", vec![10, 20])),
                Some(Series::new("", vec![30, 40, 50]))
            ]).into_series()
```

##### Good : filling a series ✅

```rust
fn list_int64_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("list_int64"),
        DataType::List(Box::new(DataType::Int64)),
    ))
}

#[polars_expr(output_type_func = list_int64_output)]
fn fill_series(inputs: &[Series], kwargs: FillSeriesKwargs) -> PolarsResult<Series> {
    // Log the inputs for debugging.
    info!("fill_series called with inputs: {:?}", inputs);
    let length = &inputs[0];
    let start = kwargs.start;
    let increment = kwargs.increment;

    // Get the Int64Chunked view of the input series.
    let ca = length.i64()?;

    // Create a builder for a list of i64 values.
    // The builder is pre-allocated to hold one list per element in the input.
    let builder = ListChunked::from_iter(ca.iter().map(|opt_len| match opt_len {
        Some(len) if len >= 0 => {
            let values: Vec<i64> = (0..len).map(|i| start + i * increment).collect();
            Series::new("".into(), values)
        }
        _ => Series::new("".into(), vec![None::<i64>]),
    }));
    // Finish building the ListChunked and convert it into a Series.
    Ok(builder.into_series())
}

#[derive(Deserialize)]
struct FillSeriesKwargs {
    start: i64,
    increment: i64,
}
```

### Safety and Unsafe Code

This rule enforces best practices for safe and unsafe code in Rust.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Safety

#### Checks

1. **Unsafe Code Organization**
   - Minimize unsafe code blocks
   - Document unsafe invariants
   - Use safe abstractions over unsafe code
   - Implement safe public APIs

2. **FFI Safety**
   - Use `#[repr(C)]` for C-compatible types
   - Document FFI safety requirements
   - Handle null pointers safely
   - Use `extern "C"` for C ABI functions

3. **Memory Safety**
   - Document memory ownership
   - Use `ManuallyDrop` when needed
   - Implement `Drop` for cleanup
   - Handle uninitialized memory safely

4. **Thread Safety**
   - Document thread safety guarantees
   - Use `Send` and `Sync` appropriately
   - Handle concurrent access safely
   - Use atomic operations when needed

#### Examples

##### Good
```rust
/// A safe wrapper around an unsafe FFI type.
///
/// # Safety
///
/// This type maintains the following invariants:
/// - The inner pointer is always valid
/// - The inner pointer is never null
/// - The inner pointer is properly aligned
pub struct SafeWrapper {
    inner: *mut ffi::UnsafeType,
}

impl SafeWrapper {
    /// Creates a new safe wrapper.
    ///
    /// # Safety
    ///
    /// The caller must ensure that:
    /// - The pointer is valid and properly aligned
    /// - The pointer is not null
    /// - The pointer will remain valid for the lifetime of the wrapper
    pub unsafe fn new(ptr: *mut ffi::UnsafeType) -> Self {
        assert!(!ptr.is_null(), "Pointer must not be null");
        Self { inner: ptr }
    }

    /// Safely accesses the inner value.
    pub fn get_value(&self) -> u32 {
        unsafe {
            // Safety: We maintain the invariant that inner is valid
            ffi::get_value(self.inner)
        }
    }
}

impl Drop for SafeWrapper {
    fn drop(&mut self) {
        unsafe {
            // Safety: We maintain the invariant that inner is valid
            ffi::destroy(self.inner);
        }
    }
}

/// A thread-safe counter using atomic operations.
pub struct AtomicCounter {
    count: AtomicU64,
}

impl AtomicCounter {
    pub fn new() -> Self {
        Self {
            count: AtomicU64::new(0),
        }
    }

    pub fn increment(&self) -> u64 {
        self.count.fetch_add(1, Ordering::SeqCst)
    }
}
```

##### Bad
```rust
// Bad: Unsafe code without documentation
pub unsafe fn process(ptr: *mut u8) {
    *ptr = 42;
}

// Bad: Missing safety invariants
pub struct UnsafeWrapper {
    inner: *mut ffi::UnsafeType,
}

// Bad: Unsafe FFI without proper null checks
pub extern "C" fn bad_ffi(ptr: *const u8) -> u32 {
    unsafe { *ptr }
}
```

### Testing

This rule enforces best practices for testing in Rust code.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Testing

#### Checks

1. **Test Organization**
   - Place unit tests in the same file as the code being tested
   - Use integration tests for testing public APIs
   - Follow the AAA (Arrange-Act-Assert) pattern

2. **Test Coverage**
   - Test both success and error cases
   - Include edge cases and boundary conditions
   - Use property-based testing where appropriate

3. **Test Isolation**
   - Use test-specific types and mocks
   - Avoid shared mutable state between tests
   - Clean up resources after tests

4. **Async Testing**
   - Use `tokio::test` for async tests
   - Test cancellation scenarios
   - Use proper timeouts in async tests

#### Examples

##### Good
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_success_case() {
        // Arrange
        let input = "test";
        
        // Act
        let result = process(input);
        
        // Assert
        assert_eq!(result, expected);
    }

    #[tokio::test]
    async fn test_async_operation() {
        // Arrange
        let service = TestService::new();
        
        // Act
        let result = service.process().await;
        
        // Assert
        assert!(result.is_ok());
    }
}
```

##### Bad
```rust
#[test]
fn test_with_shared_state() {
    // Bad: Using shared mutable state
    static mut COUNTER: i32 = 0;
    unsafe { COUNTER += 1; }
}

#[test]
fn test_without_cleanup() {
    // Bad: Not cleaning up resources
    let file = File::create("test.txt").unwrap();
    // No cleanup after test

    // avoid unwrap()
    let first_list = value1_lists.get(0).unwrap().i32()?;
    let second_list = value1_lists.get(1).unwrap().i32()?;

}

```

### Type System and Generics

This rule enforces best practices for using Rust's type system and generics.

#### Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Type System

#### Checks

1. **Trait Bounds**
   - Use appropriate trait bounds
   - Prefer `where` clauses for complex bounds
   - Use `+` for multiple trait bounds
   - Consider using `trait_alias` for common bound combinations

2. **Associated Types**
   - Use associated types for type relationships
   - Implement `Default` for associated types
   - Document associated type constraints
   - Use `type` aliases for complex associated types

3. **Generic Constraints**
   - Use `Sized` bound when needed
   - Consider `?Sized` for dynamic dispatch
   - Use `Copy` and `Clone` bounds appropriately
   - Implement `Send` and `Sync` for thread safety

4. **Type Parameters**
   - Use meaningful type parameter names
   - Document type parameter constraints
   - Consider using `const` generics where appropriate
   - Use `PhantomData` for type-level programming

#### Examples

##### Good
```rust
/// A generic container that can hold any type implementing `Display`
/// and can be cloned.
///
/// # Type Parameters
///
/// * `T` - The type of value stored in the container
///   - Must implement `Display` for string representation
///   - Must implement `Clone` for value duplication
pub struct Container<T>
where
    T: Display + Clone,
{
    value: T,
}

/// A trait for types that can be converted to a specific format
pub trait Format {
    /// The type that this format can be converted to
    type Output;
    
    /// Convert the value to the output format
    fn format(&self) -> Self::Output;
}

/// A generic function with complex bounds
pub fn process<T, U>(input: T) -> Result<U, Error>
where
    T: AsRef<str> + Send + Sync,
    U: FromStr<Err = Error> + Send + Sync,
{
    // Implementation
}

/// A type-level programming example using PhantomData
pub struct Length<const N: usize> {
    _phantom: PhantomData<[(); N]>,
}

impl<const N: usize> Length<N> {
    pub fn new() -> Self {
        Self {
            _phantom: PhantomData,
        }
    }
}

/// A trait alias for common bound combinations
pub trait Sendable = Send + Sync + 'static;
```

##### Bad
```rust
// Bad: Unclear type parameter name and missing bounds
pub struct Data<T> {
    value: T,
}

// Bad: Complex bounds without where clause
pub fn bad_generic<T: Display + Clone + Send + Sync + 'static>(input: T) {
    // Implementation
}

// Bad: Missing associated type documentation
pub trait BadFormat {
    type Output;
    fn format(&self) -> Self::Output;
}

// Bad: Unnecessary trait bounds
pub struct UnnecessaryBounds<T: Clone + Copy + Send + Sync + 'static> {
    value: T,
}
```
