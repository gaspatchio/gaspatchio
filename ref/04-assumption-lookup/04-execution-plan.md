# Execution Plan: High-Performance Vector Lookup Registry

This document outlines the step-by-step execution plan for implementing the high-performance vector lookup registry as described in `04-spec.md`. The implementation follows a modular architecture with clear separation between the core Rust implementation, PyO3 bindings, and Python interface.

## Implementation Phases Overview

1. **Foundation** - Core Rust structures and HashMap implementation
2. **Registry Management** - Thread-safe global registry with ArcSwap
3. **Lookup Engine** - HashMap-based lookup implementation
4. **Polars Integration** - Plugin expression for direct lookups
5. **Python Bindings** - PyO3 interface and Python wrappers
6. **Testing & Optimization** - Comprehensive testing and performance tuning

## Iterative Implementation Plan

We'll implement the system through a series of small, manageable iterations that build upon each other. Each iteration should be testable and provide incremental value.

### Iteration 1: Minimal Working Core

#### Step 1.1: Value Enum Implementation
- Create `Value` enum with Int, Float, and String variants
- Implement `Display`, `PartialEq`, and `Hash` traits
- Add conversion functions for common types
- Write tests for Value conversions and comparisons

#### Step 1.2: Basic Table Registry
- Create `TableRegistry` struct with tables HashMap
- Add basic methods for getting and setting tables
- Implement simple register and lookup methods
- Write tests for basic registry operations

#### Step 1.3: HashMap Key Building
- Implement function to extract keys from DataFrame rows
- Create utility for building composite keys
- Add tests with different key combinations
- Ensure proper handling of null values

#### Step 1.4: Simple Lookup Index
- Create `LookupIndex` struct with keys and HashMap
- Implement basic index building from DataFrame
- Add function to look up values in the index
- Write tests for index building and lookup

### Iteration 2: Thread-safe Registry

#### Step 2.1: ArcSwap Setup
- Add arc-swap and once_cell dependencies
- Implement static REGISTRY with ArcSwap
- Create `get_registry` function
- Create tests for basic registry access
- Verify thread-safe reads

#### Step 2.2: Thread-safe Updates
- Implement `set_registry` function
- Add clone-update-replace pattern for registry changes
- Create tests for atomic updates
- Verify concurrent read safety

#### Step 2.3: Enhanced Registry Operations
- Update `register_table` to use thread-safe pattern
- Add utility functions for registry manipulation
- Create tests for registering multiple tables
- Ensure proper cleanup in tests

#### Step 2.4: Error Handling
- Add proper error types and Result returns
- Implement graceful handling of missing tables
- Add tests for error conditions
- Ensure errors propagate correctly

### Iteration 3: Lookup and Transform

#### Step 3.1: Enhanced Lookup Index
- Update `LookupIndex` to support multiple key columns
- Add better type handling for composite keys
- Implement optimized HashMap building
- Write tests for complex key scenarios

#### Step 3.2: Transform Specification
- Create `TransformType` enum
- Implement basic transformation interface
- Add wide-to-long transform using Polars melt
- Write tests for transformation functions

#### Step 3.3: Transform Integration
- Update `register_table` to support transforms
- Add `transform_spec` parameter
- Apply transformations before building index
- Create tests with transformation examples

#### Step 3.4: Optimized Lookups
- Benchmark and optimize HashMap building
- Improve key extraction performance
- Add bulk lookup capabilities
- Test with large datasets

### Iteration 4: Vector Support

#### Step 4.1: Vector Input Detection
- Add function to detect vector columns
- Implement support for List data types
- Create tests with vector inputs
- Ensure correct handling of mixed types

#### Step 4.2: Vector Key Extraction
- Implement efficient vector key extraction
- Add support for zipping vector keys
- Handle mixed scalar/vector inputs
- Write tests for key extraction

#### Step 4.3: Vector Result Collection
- Implement vector result collection
- Ensure proper alignment of results
- Add support for returning vector results
- Create tests for vector outputs

#### Step 4.4: Complete Vector Lookup
- Integrate vector handling into main lookup
- Add optimizations for vector operations
- Benchmark vector vs scalar performance
- Test with realistic vector scenarios

#### Step 4.5: Vector-to-Scalar Support

##### Step 4.5.1: Mixed Inputs Handling
- Add special handling for mixed scalar/vector inputs
- Ensure scalar inputs are properly broadcast to match vector lengths
- Add efficient implementation for common case (one vector, rest scalar)
- Write tests for mixed input scenarios

##### Step 4.5.2: Vector Length Validation
- Implement validation to ensure vector lengths are compatible
- Add proper error handling for mismatched vector lengths
- Create utility for determining result vector length
- Test with different vector length combinations

### Iteration 5: Polars Plugin

#### Step 5.1: Plugin Boilerplate
- Create plugin expression scaffold
- Add output type determination function
- Implement parameter handling
- Write tests for basic plugin structure

#### Step 5.2: Plugin Implementation
- Implement `assumption_lookup` expression
- Add support for different input types
- Handle scalar and vector inputs
- Create tests for plugin functionality

#### Step 5.3: Plugin Registration
- Implement function to register plugin with Polars
- Add proper error handling
- Ensure compatibility with Polars lazy evaluation
- Test plugin in lazy evaluation context

#### Step 5.4: Plugin Optimization
- Profile plugin performance
- Optimize critical paths
- Add special handling for common cases
- Benchmark against join-based approach

#### Step 5.5: ActuarialFrame Integration

##### Step 5.5.1: ActuarialFrame Lookup Method
- Create `lookup_assumption` method for ActuarialFrame
- Support both scalar and vector inputs
- Ensure proper column naming in result
- Write tests for ActuarialFrame integration

##### Step 5.5.2: Tracing Support
- Add support for tracing lookup operations
- Implement execution of traced lookups
- Ensure lookup operations can be serialized/deserialized
- Test tracing functionality with vector lookups

### Iteration 6: Python Bridge

#### Step 6.1: PyO3 Module Setup
- Create basic PyO3 module
- Add Python module initialization
- Implement simple function bindings
- Write tests for Python-Rust interop

#### Step 6.2: Core Type Bindings
- Create PyO3 bindings for Value enum
- Add bindings for LookupIndex
- Implement conversion between Python and Rust types
- Write tests for type conversions

#### Step 6.3: Registry Interface
- Create Python interface for TableRegistry
- Add bindings for registry operations
- Implement Python-specific error handling
- Write tests for registry operations from Python

#### Step 6.4: Python Transform Models
- Implement Pydantic models for transforms
- Create conversion functions for Rust types
- Add Python convenience functions
- Write tests for transform models

#### Step 6.5: Plugin Python Interface
- Create Python wrappers for plugins
- Add type hints and documentation
- Implement user-friendly interface
- Write tests for plugin usage in Python

### Iteration 7: Integration and Optimization

#### Step 7.1: End-to-End Tests
- Create integration tests for full workflow
- Test with realistic data scenarios
- Verify correct behavior across languages
- Test error handling and edge cases

#### Step 7.2: Performance Benchmarks
- Implement benchmarks for common use cases
- Compare with existing approaches
- Profile memory usage and CPU time
- Document performance characteristics

#### Step 7.3: Final Optimization
- Address performance bottlenecks
- Optimize memory usage
- Improve error messages
- Add logging for debugging

#### Step 7.4: Documentation
- Add inline documentation for all functions
- Create user guide and examples
- Document API and usage patterns
- Add performance best practices

## Implementation Prompts for Code Generation

The following prompts can be used with a code-generation LLM to implement each step of the plan in a test-driven manner:

### Prompt 1: Core Data Structures

```
We're implementing a high-performance vector lookup registry for an actuarial modeling system. Let's start with the core data structures.

First, create a Value enum in Rust that can represent:
- Int (i64)
- Float (f64)
- String (String)

Implement the necessary traits:
- Debug and Display for printing
- PartialEq and Eq for comparison
- Hash for using in HashMaps
- Clone and Copy where feasible

Then, implement a LookupIndex struct that contains:
- keys: Vec<String> for column names
- value_column: String for the result column name
- index: HashMap<Vec<Value>, Value> for the actual lookup table

Write unit tests for both the Value enum and LookupIndex struct. Include tests for:
- Creating and comparing Values
- Hashing Values consistently
- Creating a LookupIndex and performing basic lookups

Don't worry about building the HashMap from a DataFrame yet - we'll tackle that next.
```

### Prompt 2: HashMap Building from DataFrame

```
Now let's implement the functionality to build a lookup HashMap from a Polars DataFrame.

Create a function `build_lookup_index` with this signature:
```rust
fn build_lookup_index(
    df: &DataFrame,
    key_columns: &[String],
    value_column: &str
) -> Result<HashMap<Vec<Value>, Value>, PolarsError>
```

The function should:
1. Verify that all columns exist in the DataFrame
2. Extract the key columns and value column from each row
3. Convert the values to our custom Value enum
4. Build a HashMap that maps from key combinations to values

Also, implement utility functions to:
- Extract a single Value from a Series at a given index
- Convert multiple column values into a Vec<Value> key
- Convert between Polars data types and our Value enum

Write comprehensive tests using a sample DataFrame with:
- Different key combinations (single key, multiple keys)
- Different data types (integers, floats, strings)
- Edge cases like duplicate keys and null values

Ensure the function properly handles errors like missing columns and returns appropriate Result types.
```

### Prompt 3: Basic TableRegistry Implementation

```
Let's implement the TableRegistry struct that will store our lookup tables and indices.

Create a TableRegistry struct that contains:
- tables: HashMap<String, DataFrame> - stores the original tables
- lookup_indices: HashMap<String, LookupIndex> - stores the pre-built lookup indices

Implement these methods:
- new() - create an empty registry
- register_table(&mut self, name: &str, df: DataFrame, keys: Vec<String>, value_column: &str) -> Result<()>
- get_table(&self, name: &str) -> Option<&DataFrame>
- get_lookup_index(&self, name: &str) -> Option<&LookupIndex>
- lookup(&self, name: &str, key: Vec<Value>) -> Result<Option<Value>, Error>

For the register_table method, use the build_lookup_index function from the previous step to create the LookupIndex.

Write unit tests that:
- Create a registry and register a table
- Look up values with both existing and non-existing keys
- Handle registration of multiple tables
- Test error conditions (missing columns, invalid tables)

Don't worry about thread safety or global state yet - we'll add that next.
```

### Prompt 4: Thread-Safe Global Registry

```
Now let's make our TableRegistry globally accessible and thread-safe using the arc-swap crate.

Add these dependencies to Cargo.toml:
- arc-swap = "1.6"
- once_cell = "1.17"

Create a global registry with:
```rust
static REGISTRY: Lazy<ArcSwap<TableRegistry>> = Lazy::new(|| {
    ArcSwap::from_pointee(TableRegistry::default())
});
```

Implement these functions:
- get_registry() -> Arc<TableRegistry> - returns a clone of the current registry Arc
- set_registry(new_reg: TableRegistry) - atomically replaces the global registry

Update the register_table function to use this pattern:
```rust
pub fn register_table(name: &str, df: DataFrame, keys: Vec<String>, value_column: &str) -> Result<()> {
    // Get current registry
    let old_registry = get_registry();
    let mut new_registry = (*old_registry).clone();
    
    // Update new registry
    new_registry.register_table(name, df, keys, value_column)?;
    
    // Replace global registry
    set_registry(new_registry);
    Ok(())
}
```

Write tests that verify:
- The global registry is properly initialized
- Updates to the registry are atomic and visible to all readers
- Concurrent reads work correctly
- Memory is properly managed (no leaks)

Use std::thread to create multiple threads that access the registry concurrently.
```

### Prompt 5: Vector Lookup Support

```
Now let's add support for vector (List) inputs in our lookup functionality. This will allow us to look up values for multiple keys at once.

First, implement a function to detect vector columns in a DataFrame:
```rust
fn detect_vector_columns(df: &DataFrame, columns: &[String]) -> Vec<String> {
    // Return a list of columns that contain List data types
}
```

Then, implement a vector lookup function:
```rust
fn lookup_vector(
    registry: &TableRegistry,
    table_name: &str,
    keys: &[&Series]
) -> Result<Series, PolarsError> {
    // Handle both scalar and vector inputs
    // Return a Series containing lookup results
    // If any input is a vector, return a vector of results
}
```

The function should:
1. Check if any key columns are List/vector types
2. If all inputs are scalar, perform a simple lookup
3. If any input is a vector:
   - Extract each element from the vectors
   - Zip corresponding elements together
   - Look up each combination
   - Return results as a List Series

Update the TableRegistry to add this method:
```rust
fn lookup_vector(&self, table_name: &str, keys: &[&Series]) -> Result<Series, PolarsError> {
    // Use the lookup_vector function
}
```

Write tests for:
- Pure scalar inputs
- Pure vector inputs
- Mixed scalar and vector inputs
- Different length vectors
- Handling null values in vectors
- Edge cases like empty vectors

Use realistic examples like age projections and mortality rates.
```

### Prompt 6: Polars Plugin Expression

```
Let's implement a Polars plugin expression for our lookup functionality. This will allow us to use our lookups directly in Polars expressions.

First, define the kwargs struct:
```rust
#[derive(Deserialize)]
pub struct AssumptionLookupKwargs {
    table_name: String,
}
```

Then implement the plugin function:
```rust
#[polars_expr(output_type_func=assumption_lookup_output)]
fn assumption_lookup(inputs: &[Series], kwargs: AssumptionLookupKwargs) -> PolarsResult<Series> {
    let registry = get_registry();
    registry.lookup_vector(&kwargs.table_name, inputs)
}
```

And the output type function:
```rust
fn assumption_lookup_output(inputs: &[DataType], kwargs: &AssumptionLookupKwargs) -> PolarsResult<DataType> {
    // Determine the output type based on table value column
    let registry = get_registry();
    let lookup_index = registry.get_lookup_index(&kwargs.table_name)
        .ok_or_else(|| PolarsError::ComputeError(
            format!("Table '{}' not found", kwargs.table_name).into()
        ))?;
    
    // Return List type if any input is a List
    let is_any_list = inputs.iter().any(|dt| matches!(dt, DataType::List(_)));
    let value_type = lookup_index.value_type();
    
    if is_any_list {
        Ok(DataType::List(Box::new(value_type)))
    } else {
        Ok(value_type)
    }
}
```

Write unit tests that:
- Register the plugin with Polars
- Use the expression in lazy operations
- Test with different input types
- Verify correct results for scalar and vector inputs
- Test error conditions

Use the Polars test utilities to validate the plugin behavior.
```

### Prompt 7: Transform Specification and Implementation

```
Let's implement transformation support for our registry. This will allow tables to be transformed (e.g., from wide to long format) during registration.

First, create a TransformType enum:
```rust
pub enum TransformType {
    WIDE_TO_LONG,
    // Add future transform types here
}
```

Create a TransformSpec struct:
```rust
pub struct TransformSpec {
    transform_type: TransformType,
    // Common fields
    id_vars: Vec<String>,
    value_vars: Vec<String>,
    var_name: String,
    value_name: String,
    // Add other fields for future transform types
}
```

Implement the wide-to-long transformation:
```rust
fn transform_wide_to_long(
    df: &DataFrame,
    id_vars: &[String],
    value_vars: &[String],
    var_name: &str,
    value_name: &str
) -> PolarsResult<DataFrame> {
    df.lazy()
        .melt(
            id_vars.iter().map(|s| s.to_string()).collect(),
            value_vars.iter().map(|s| s.to_string()).collect(),
            Some(var_name.to_string()),
            Some(value_name.to_string()),
        )
        .collect()
}
```

Update the register_table function to support transformations:
```rust
pub fn register_table(
    name: &str,
    df: DataFrame,
    keys: Vec<String>,
    value_column: &str,
    transform_spec: Option<&TransformSpec>
) -> Result<()> {
    // Apply transformation if specified
    let transformed_df = if let Some(spec) = transform_spec {
        match spec.transform_type {
            TransformType::WIDE_TO_LONG => transform_wide_to_long(
                &df,
                &spec.id_vars,
                &spec.value_vars,
                &spec.var_name,
                &spec.value_name
            )?
        }
    } else {
        df.clone()
    };
    
    // Continue with regular registration...
}
```

Write tests for:
- Transforming a wide-format table to long format
- Registering a transformed table
- Looking up values from a transformed table
- Error conditions in transformations

Use a realistic example like a mortality table with age rows and gender/smoking columns.
```

### Prompt 8: PyO3 Bindings

```
Now let's create PyO3 bindings for our Rust implementation to make it accessible from Python.

Add these dependencies to Cargo.toml:
- pyo3 = { version = "0.18", features = ["extension-module"] }
- pyo3-polars = "0.3"

First, set up the PyO3 module:
```rust
#[pymodule]
fn gaspatchio_core(_py: Python, m: &PyModule) -> PyResult<()> {
    // Add submodule for assumptions
    let assumptions = PyModule::new(_py, "assumptions")?;
    
    // Register module components
    init_lookup_registry(assumptions)?;
    
    // Add submodule to main module
    m.add_submodule(assumptions)?;
    
    Ok(())
}
```

Create bindings for our core types:
```rust
#[pyclass]
#[derive(Clone)]
struct PyLookupIndex {
    inner: LookupIndex,
}

#[pymethods]
impl PyLookupIndex {
    #[new]
    fn new(keys: Vec<String>, value_column: String) -> Self {
        Self {
            inner: LookupIndex::new(keys, value_column)
        }
    }
    
    #[getter]
    fn keys(&self) -> Vec<String> {
        self.inner.keys.clone()
    }
    
    #[getter]
    fn value_column(&self) -> String {
        self.inner.value_column.clone()
    }
}
```

Implement Python functions for the table registry:
```rust
#[pyfunction]
fn py_register_table(
    table_name: &str,
    py_df: PyDataFrame,
    keys: Vec<String>,
    value_column: &str,
    py_transform_spec: Option<PyTransformSpec>
) -> PyResult<()> {
    // Convert from Python to Rust
    let df = py_df.df;
    
    // Convert transform spec if provided
    let transform_spec = py_transform_spec.map(|spec| spec.to_rust_spec());
    
    // Call the Rust function
    register_table(table_name, df, keys, value_column, transform_spec.as_ref())
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
}
```

Create a Python TransformSpec:
```rust
#[pyclass]
#[derive(Clone)]
struct PyTransformSpec {
    transform_type: String,
    id_vars: Vec<String>,
    value_vars: Vec<String>,
    var_name: String,
    value_name: String,
}

#[pymethods]
impl PyTransformSpec {
    #[new]
    fn new(
        transform_type: String,
        id_vars: Vec<String>,
        value_vars: Vec<String>,
        var_name: String,
        value_name: String
    ) -> Self {
        Self {
            transform_type,
            id_vars,
            value_vars,
            var_name,
            value_name,
        }
    }
    
    // Conversion methods
}
```

Write Python tests that:
- Register tables from Python
- Apply transformations
- Perform lookups
- Handle errors correctly

Create an end-to-end test with a realistic example.
```

### Prompt 9: Python Interface Enhancements

```
Let's enhance the Python interface with Pydantic models and more user-friendly wrappers.

First, create Pydantic models for transformation specifications:

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional, Union, Literal

class TransformType(str, Enum):
    WIDE_TO_LONG = "wide_to_long"
    # Future transform types can be added here

class WideToLongTransform(BaseModel):
    type: TransformType = TransformType.WIDE_TO_LONG
    id_vars: List[str] = Field(..., description="Columns to use as identifier variables")
    value_vars: List[str] = Field(..., description="Columns to unpivot")
    var_name: str = Field(..., description="Name to use for the variable column")
    value_name: str = Field(..., description="Name to use for the value column")

# Union type for all transformation types
TransformSpec = WideToLongTransform  # Will become Union[] when more types are added
```

Create high-level Python functions for registry operations:

```python
def register_table(
    name: str,
    df: pl.DataFrame,
    keys: List[str],
    value_column: str,
    transform_spec: Optional[TransformSpec] = None
) -> None:
    """
    Register a table in the global registry.
    
    Args:
        name: Name to register the table under
        df: Polars DataFrame containing the table data
        keys: List of column names to use as lookup keys
        value_column: Column name containing the values to return
        transform_spec: Optional specification for transforming the table
    """
    # Convert to Rust types and call Rust function
    
def assumption_lookup(*key_columns, table_name: str) -> pl.Expr:
    """
    Create a Polars expression for looking up values from a registered table.
    
    Args:
        *key_columns: Polars expressions for the key columns
        table_name: Name of the registered table
        
    Returns:
        A Polars expression that performs the lookup
    """
    # Create and return a Polars expression using our plugin
```

Write tests for the Python interface:
- Register a table using Pydantic models
- Use the assumption_lookup expression in Polars queries
- Test with vector and scalar inputs
- Verify correct results

Create a complete example showing:
- Loading a mortality table
- Transforming it from wide to long format
- Registering it in the registry
- Looking up mortality rates for different ages and gender/smoking combinations
- Handling vector inputs for age projections
```

### Prompt 10: Integration and ActuarialFrame Support

```
Let's integrate our new lookup functionality with the ActuarialFrame class for seamless usage in actuarial models.

First, add a method to ActuarialFrame for vector lookups:

```python
def lookup_assumption(
    self,
    *key_columns,
    table_name: str
) -> "ActuarialFrame":
    """
    Look up values from a registered assumption table.
    
    This method supports both scalar and vector inputs. If any input column
    contains vectors (lists), the lookup will be performed for each element
    and return vector results.
    
    Args:
        *key_columns: Names of columns to use as lookup keys
        table_name: Name of the registered table
        
    Returns:
        ActuarialFrame with looked up values
    """
    if self._tracing:
        # Record operation for later execution
        self._computation_graph.append(...)
        return self
        
    # Convert column names to expressions
    key_exprs = [pl.col(col) if isinstance(col, str) else col for col in key_columns]
    
    # Use assumption_lookup expression
    result_expr = assumption_lookup(*key_exprs, table_name=table_name)
    
    # Get value column name from registry
    value_column = get_value_column_name(table_name)
    
    # Add as a new column
    return self.with_column(result_expr.alias(value_column))
```

Update the traced execution to handle vector lookups:

```python
def _execute_traced_operations(self, operations):
    """Execute operations captured in the trace."""
    for op_type, *args in operations:
        if op_type == "lookup_assumption":
            key_cols, table_name = args
            # Handle lookup assumption operation
            key_exprs = [pl.col(col) if isinstance(col, str) else col for col in key_cols]
            result_expr = assumption_lookup(*key_exprs, table_name=table_name)
            value_column = get_value_column_name(table_name)
            self._df = self._df.with_column(result_expr.alias(value_column))
```

Create a comprehensive example model:

```python
def life_projection_model(df: ActuarialFrame) -> ActuarialFrame:
    # Constants
    max_age = 120
    
    # Create projection vectors
    df["num_proj_months"] = (max_age - df["issue_age"]) * 12
    df["proj_months"] = pl.Series(range(481)).cast(pl.Float64)  # 40 years monthly
    
    # Calculate projected ages
    df["proj_age"] = df["issue_age"] + df["proj_months"] / 12
    df["age_last"] = df["proj_age"].floor()
    
    # Create lookup keys
    df["gender_smoking"] = df["gender"] + df["smoking_status"]
    
    # Look up mortality rates for all projected ages
    df = df.lookup_assumption(
        "age_last",
        "gender_smoking",
        table_name="mortality_rates"
    )
    
    # Calculate mortality costs
    df["mortality_cost"] = df["sum_assured"] * df["mortality_rate"]
    
    return df
```

Write comprehensive tests for:
- Using vector lookups in models
- Tracing and executing vector lookups
- Performance comparison with previous approaches
- Edge cases and error handling

Create benchmarks to demonstrate the performance improvements over the previous explode-based approach.
```

### Prompt 11: Performance Optimization and Final Integration

```
Let's optimize the performance of our lookup functionality and finalize the integration with ActuarialFrame.

First, optimize the HashMap building process:

```rust
fn build_lookup_index_optimized(
    df: &DataFrame,
    key_columns: &[String],
    value_column: &str
) -> Result<HashMap<Vec<Value>, Value>, PolarsError> {
    // Pre-allocate HashMap with approximate capacity
    let capacity = df.height();
    let mut index = HashMap::with_capacity(capacity);
    
    // Extract columns once instead of repeatedly
    let key_series: Vec<&Series> = key_columns.iter()
        .map(|name| df.column(name))
        .collect::<Result<Vec<_>, _>>()?;
    
    let value_series = df.column(value_column)?;
    
    // Process in chunks for better cache locality
    const CHUNK_SIZE: usize = 1024;
    
    for chunk_start in (0..df.height()).step_by(CHUNK_SIZE) {
        let chunk_end = std::cmp::min(chunk_start + CHUNK_SIZE, df.height());
        
        for row_idx in chunk_start..chunk_end {
            // Extract key values
            let mut key = Vec::with_capacity(key_columns.len());
            for series in &key_series {
                key.push(extract_value_from_series(series, row_idx)?);
            }
            
            // Extract value
            let value = extract_value_from_series(value_series, row_idx)?;
            
            // Insert into HashMap
            index.insert(key, value);
        }
    }
    
    Ok(index)
}
```

Optimize the vector lookup process:

```rust
fn lookup_vector_optimized(
    registry: &TableRegistry,
    table_name: &str,
    keys: &[&Series]
) -> Result<Series, PolarsError> {
    let lookup_index = registry.get_lookup_index(table_name)
        .ok_or_else(|| PolarsError::ComputeError(
            format!("Table '{}' not found", table_name).into()
        ))?;
    
    // Determine if we're doing vector or scalar lookup
    let has_vectors = keys.iter().any(|s| matches!(s.dtype(), DataType::List(_)));
    
    if !has_vectors {
        // Fast path for scalar lookup
        return lookup_scalar(lookup_index, keys);
    }
    
    // Vector lookup path
    // Calculate result size based on vector lengths
    let (len, vector_idx) = keys.iter().enumerate()
        .find_map(|(i, s)| {
            if let DataType::List(_) = s.dtype() {
                let list = s.list()?;
                Some((list.len(), i))
            } else {
                None
            }
        })
        .ok_or_else(|| PolarsError::ComputeError(
            "Expected at least one vector column".into()
        ))?;
    
    // Preallocate result vector
    let mut results = Vec::with_capacity(len);
    
    // Process vector lookups in chunks
    const CHUNK_SIZE: usize = 1024;
    
    for chunk_start in (0..len).step_by(CHUNK_SIZE) {
        let chunk_end = std::cmp::min(chunk_start + CHUNK_SIZE, len);
        
        for i in chunk_start..chunk_end {
            // Extract key for this vector index
            let mut key = Vec::with_capacity(keys.len());
            
            for (j, series) in keys.iter().enumerate() {
                if j == vector_idx {
                    // Extract from vector at index i
                    let list = series.list()?;
                    key.push(extract_value_from_list(list, i)?);
                } else {
                    // Use scalar value
                    key.push(extract_value_from_series(series, 0)?);
                }
            }
            
            // Lookup in HashMap
            let result = lookup_index.index.get(&key).cloned();
            results.push(result.unwrap_or(Value::Null));
        }
    }
    
    // Convert results to Series
    create_series_from_values(&results, lookup_index.value_column.as_str())
}
```

Create a benchmark suite comparing our new approach with the explode-based approach.

Create end-to-end integration tests for ActuarialFrame that verify the complete functionality.

Finalize the Python interface documentation and publish comprehensive examples.
```

## Conclusion

This plan provides a detailed roadmap for implementing the high-performance vector lookup registry. By following these steps in order, we can build a robust, well-tested implementation that meets the performance and functionality requirements specified in the original document.

The implementation follows best practices:
- Incremental development with testing at each step
- Clear separation of core functionality, bindings, and interface
- Strong focus on performance optimization
- Robust error handling throughout
- Comprehensive documentation

Each step builds on the previous ones, ensuring that at each stage we have a working system that we can extend and refine.
