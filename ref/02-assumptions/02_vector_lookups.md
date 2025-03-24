# Vector-Based Lookups in Actuarial Models

## Problem Statement

Actuarial projections often require time-based calculations that generate vector results (e.g., cash flows over time). Current lookup functionality in the `gaspatchio-core` framework only supports scalar (single value) lookups, which becomes problematic when dealing with these vector columns. This document outlines a plan to enhance the framework with vector-aware lookup capabilities.

### Example Use Case: Mortality Rates Lookup

A common scenario involves the creation of projection vectors for variables like age and then looking up mortality rates for each projected age:

```python
# Current model with scalar lookups
def life_model(df):
    # Create projection vectors
    df["age"] = df["age"] + (df["proj_months"] / 12)  # Creates vectors of ages
    df["age_last"] = floor(df["age"])  # Also vectors
    df["gender_smoking"] = df["gender"] + df["smoking_status"]
    
    # Current approach has issues with vector columns
    # We need to extract just the first element for lookup
    current_df = df.collect()
    
    # ERROR: Can't cast list column to scalar
    lookup_frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policyholder_nr": current_df["policyholder_nr"],
                "age_last": current_df["age_last"].cast(pl.Float64),  # FAILS: list[f64] → Float64
                "gender_smoking": current_df["gender_smoking"],
            }
        )
    )
    
    # Desired behavior: We want to lookup mortality rates for EACH age in the vector
```

## Solution Architecture

We will implement vector-aware lookups that can efficiently process vector columns by:

1. Detecting vector columns in the input data
2. Performing lookups for each element in these vectors
3. Returning results as vectors aligned with the input

## Implementation Plan

### Phase 1: Core Rust Vector Lookup Implementation

The core implementation will leverage Polars' native functionality for handling list/vector columns, particularly using the built-in `explode()` method and efficient window operations.

**Step 1.1: Implement Vector Column Detection**

```rust
/// Detects list/vector columns in a DataFrame
/// 
/// # Arguments
/// * `df` - The DataFrame to examine
/// * `column_names` - Column names to check
/// 
/// # Returns
/// A vector of column names that contain list data
pub fn detect_vector_columns(df: &DataFrame, column_names: &[String]) -> PolarsResult<Vec<String>> {
    let mut vector_cols = Vec::new();
    
    for col_name in column_names {
        if let Ok(col) = df.column(col_name) {
            if matches!(col.dtype(), DataType::List(_)) {
                vector_cols.push(col_name.clone());
            }
        }
    }
    
    Ok(vector_cols)
}
```

**Step 1.2: Implement Vector Explode Function**

```rust
/// Explodes vector columns in a DataFrame using Polars' native explode functionality
/// 
/// # Arguments
/// * `df` - DataFrame containing vector columns
/// * `vector_columns` - Names of columns containing vectors to explode
/// 
/// # Returns
/// A new DataFrame with vector columns expanded and tracking columns
pub fn explode_vector_columns(df: &DataFrame, vector_columns: &[String]) -> PolarsResult<DataFrame> {
    // Create row tracking column before explosion
    let with_index = df.with_row_count("__row_idx", None)?;
    
    // Use Polars' native explode - handles nulls and different length vectors automatically
    let exploded = with_index.explode(vector_columns)?;
    
    // Add projection index using window functions
    let result = exploded.lazy()
        .with_column(
            col("__row_idx")
                .rank(RankOptions {
                    method: RankMethod::Dense,
                    descending: false,
                    over: vec![col("__row_idx")],
                })
                .sub(lit(1))  // Convert to 0-based indexing
                .alias("__proj_idx")
        )
        .collect()?;

    Ok(result)
}
```

**Step 1.3: Implement Vector Result Collection**

```rust
/// Collects lookup results back into vector format using Polars' list operations
/// 
/// # Arguments
/// * `df` - Exploded DataFrame with lookup results
/// * `group_column` - Column to group by (usually __row_idx)
/// * `value_columns` - Columns to collect into vectors
/// 
/// # Returns
/// A DataFrame with vector results
pub fn collect_vector_results(
    df: &DataFrame,
    group_column: &str,
    value_columns: &[String]
) -> PolarsResult<DataFrame> {
    // Create expressions for grouping value columns into lists
    let mut agg_exprs = vec![];
    
    for col_name in value_columns {
        agg_exprs.push(
            col(col_name)
                .list()
                .alias(col_name)
        );
    }
    
    // Group by row index and aggregate values into lists
    df.lazy()
        .group_by([col(group_column)])
        .agg(agg_exprs)
        .sort(group_column, SortOptions::default())  // Maintain original order
        .collect()
}
```

**Step 1.4: Implement Main Vector Lookup Function**

```rust
/// Performs lookups with vector column support using Polars' optimized operations
/// 
/// # Arguments
/// * `table_name` - Name of the registered table to lookup
/// * `query_df` - DataFrame that may contain vector columns
/// 
/// # Returns
/// A DataFrame with lookup results as vectors
pub fn lookup_vector(table_name: &str, query_df: DataFrame) -> PolarsResult<DataFrame> {
    // Get the registered table
    let registry = get_registry();
    let table_df = registry.get_table(table_name)
        .ok_or_else(|| PolarsError::ComputeError(
            format!("Table '{}' not found", table_name).into()
        ))?;
    
    let key_spec = registry.keyspecs.get(table_name)
        .ok_or_else(|| PolarsError::ComputeError(
            format!("KeySpec for table '{}' not found", table_name).into()
        ))?;
    
    // Detect vector columns in query DataFrame
    let vector_cols = detect_vector_columns(&query_df, &key_spec.source_cols)?;
    
    if vector_cols.is_empty() {
        // No vector columns - use standard lookup
        return lookup(table_name, query_df);
    }
    
    // Explode vector columns
    let exploded = explode_vector_columns(&query_df, &vector_cols)?;
    
    // Perform lookup using standard mechanism
    let lookup_result = lookup(table_name, exploded)?;
    
    // Determine which columns to collect as vectors
    let value_columns: Vec<String> = lookup_result
        .get_column_names()
        .iter()
        .filter(|&name| !name.starts_with("__"))
        .map(|s| s.to_string())
        .collect();
    
    // Collect results back into vectors
    collect_vector_results(&lookup_result, "__row_idx", &value_columns)
}
```

This implementation:

1. Uses Polars' native `explode()` method for optimal performance
2. Leverages Polars' window functions for tracking indices
3. Uses Polars' grouping and list aggregation for collecting results
4. Handles nulls and different length vectors automatically
5. Maintains original row order in results
6. Uses Polars' lazy evaluation for better performance
7. Minimizes memory usage by avoiding unnecessary intermediate collections

The approach is more idiomatic to Polars and should provide better performance than the original manual implementation. It also handles edge cases like null values and different length vectors more robustly by using Polars' built-in functionality.

**Step 1.5: Update Module Initialization**

```rust
/// Python wrapper for vector lookup
#[pyfunction]
pub fn py_lookup_vector(table_name: String, query_df: PyDataFrame) -> PyResult<PyDataFrame> {
    // Convert PyDataFrame to Polars DataFrame
    let df = query_df.0;
    
    // Perform vector lookup
    match lookup_vector(&table_name, df) {
        Ok(result) => Ok(PyDataFrame(result)),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())),
    }
}

/// Initializes the module with vector lookup support
pub fn init_module(m: &Bound<PyModule>) -> PyResult<()> {
    // Existing registrations
    m.add_class::<KeySpec>()?;
    m.add_class::<TransformSpec>()?;
    m.add_class::<TableRegistry>()?;
    
    // Add vector lookup functionality
    m.add_function(wrap_pyfunction!(py_lookup_vector, m)?)?;
    
    Ok(())
}
```

The updated implementation provides several key advantages:

1. **Native Polars Integration**
   - Uses Polars' built-in `explode()` for list/vector handling
   - Leverages Polars' window functions for efficient indexing
   - Uses Polars' lazy evaluation for better performance

2. **Robust Error Handling**
   - Proper error propagation using `PolarsResult`
   - Descriptive error messages for missing tables/specs
   - Graceful handling of null values and different length vectors

3. **Memory Efficiency**
   - Minimizes intermediate allocations
   - Uses lazy evaluation where possible
   - Efficient handling of large datasets

4. **Type Safety**
   - Proper handling of list column types
   - Safe conversion between Python and Rust types
   - Robust null value handling

5. **Performance Optimizations**
   - Uses Polars' vectorized operations
   - Minimizes data copying
   - Efficient grouping and aggregation

This implementation provides a more robust and performant solution for vector-based lookups in actuarial models, leveraging Polars' native capabilities for optimal performance.

### Phase 2: Python Interface Implementation

The Python interface will provide a clean, intuitive API that leverages Polars' capabilities while maintaining the ActuarialFrame abstraction.

**Step 2.1: Add Vector Lookup Method to ActuarialFrame**

```python
from typing import Optional, Union, List
import polars as pl
from polars.type_aliases import IntoExpr

class ActuarialFrame:
    def lookup_table_vector(
        self,
        table_name: str,
        batch_size: Optional[int] = None
    ) -> "ActuarialFrame":
        """
        Lookup values from a registered table with support for vector/list columns.
        
        This method automatically detects and handles vector columns, performing lookups
        for each element in the vectors and returning vector results. It uses Polars'
        native functionality for optimal performance.
        
        Args:
            table_name: Name of the registered table to lookup against
            batch_size: Optional batch size for processing large datasets
            
        Returns:
            ActuarialFrame with looked up vector values
            
        Example:
            ```python
            # Create projection vectors
            df["age"] = df["age"] + (df["proj_months"] / 12)
            df["age_last"] = pl.col("age").floor()
            
            # Lookup mortality rates for all projected ages
            result = df.lookup_table_vector("mortality_rates")
            # mortality_rate column will contain vectors of rates
            ```
        """
        if self._trace_mode:
            # Handle tracing mode
            self._operation_log.append({
                "operation": "table_lookup_vector",
                "args": [table_name],
                "kwargs": {"batch_size": batch_size}
            })
            return self
            
        # Get materialized DataFrame
        df_materialized = self.collect()
        
        if batch_size:
            return self._batch_lookup_vector(table_name, df_materialized, batch_size)
            
        # Perform vector lookup using Rust implementation
        result_df = py_lookup_vector(table_name, df_materialized)
        
        return ActuarialFrame(result_df)
```

**Step 2.2: Implement Batch Processing**

```python
def _batch_lookup_vector(
    self,
    table_name: str,
    df: pl.DataFrame,
    batch_size: int
) -> "ActuarialFrame":
    """
    Process vector lookups in batches for memory efficiency.
    
    Uses Polars' native functionality to split and combine DataFrames efficiently.
    
    Args:
        table_name: Name of the table to lookup
        df: Input DataFrame to process
        batch_size: Number of rows per batch
        
    Returns:
        ActuarialFrame with combined lookup results
    """
    total_rows = df.height
    
    # Process in batches using Polars' slice operations
    results = []
    for start_idx in range(0, total_rows, batch_size):
        end_idx = min(start_idx + batch_size, total_rows)
        
        # Extract batch using efficient Polars slicing
        batch_df = df.slice(start_idx, end_idx - start_idx)
        
        # Process batch
        batch_result = py_lookup_vector(table_name, batch_df)
        results.append(batch_result)
    
    # Combine results efficiently using Polars' vstack
    final_df = pl.concat(results, how="vertical")
    return ActuarialFrame(final_df)
```

**Step 2.3: Update Computation Graph Handling**

```python
def _handle_vector_lookup_operation(self, op_data: dict) -> "ActuarialFrame":
    """Handle vector lookup operations in the computation graph."""
    table_name = op_data["args"][0]
    batch_size = op_data["kwargs"].get("batch_size")
    
    # Create optimized lazy computation
    df = self.collect()
    
    if self._optimize_mode:
        # In optimize mode, we can use Polars' lazy evaluation
        # to build an optimized computation plan
        result_df = (
            df.lazy()
            .pipe(lambda ldf: self._apply_vector_lookup(ldf, table_name))
            .collect()
        )
    else:
        # Standard execution
        result_df = py_lookup_vector(table_name, df)
    
    return ActuarialFrame(result_df)

def _apply_vector_lookup(self, ldf: pl.LazyFrame, table_name: str) -> pl.LazyFrame:
    """Apply vector lookup operation in lazy evaluation context."""
    # This method can be extended to optimize the computation plan
    # when we have multiple vector lookups or other operations
    return ldf.pipe(lambda df: py_lookup_vector(table_name, df))
```

This updated Python implementation:

1. **Leverages Polars Features**
   - Uses Polars' native types and operations
   - Supports lazy evaluation for optimization
   - Efficient batch processing using Polars' slicing

2. **Modern Python Practices**
   - Type hints for better IDE support
   - Comprehensive docstrings with examples
   - Clean, modular code structure

3. **Performance Optimizations**
   - Efficient batch processing for large datasets
   - Minimizes memory usage with lazy evaluation
   - Uses Polars' optimized concatenation

4. **Developer Experience**
   - Clear API with helpful examples
   - Proper error messages
   - Intuitive method names and parameters

The implementation maintains compatibility with the existing ActuarialFrame interface while providing optimized vector operations using Polars' native capabilities.

### Phase 3: Integration and Testing

**Step 3.1: Create Integration Tests**

```python
import pytest
import polars as pl
import numpy as np
from datetime import date

def test_vector_lookup_mortality():
    """Test vector lookup using mortality rates table."""
    # Setup test data
    mortality_data = pl.DataFrame({
        "age_last": range(18, 100),
        "gender_smoking": ["MNS", "MS", "FNS", "FS"] * 21,
        "mortality_rate": np.random.uniform(0.0001, 0.1, 82 * 4)
    })
    
    # Register mortality table
    register_table(
        "mortality_rates",
        mortality_data,
        KeySpec(
            source_cols=["age_last", "gender_smoking"],
            table_cols=["age_last", "gender_smoking"]
        )
    )
    
    # Create test policies with projection vectors
    policies = pl.DataFrame({
        "policy_id": range(1000),
        "age": np.random.uniform(20, 60, 1000),
        "gender": np.random.choice(["M", "F"], 1000),
        "smoking": np.random.choice(["S", "NS"], 1000)
    })
    
    # Create ActuarialFrame
    af = ActuarialFrame(policies)
    
    # Generate projection vectors
    with pl.Config(fmt_str_lengths=100):
        af = af.with_columns([
            # Create monthly projection for 40 years
            (pl.Series(name="proj_months", values=range(481))).cast(pl.Float64).alias("proj_months"),
            
            # Calculate projected age
            (pl.col("age") + pl.col("proj_months") / 12).alias("proj_age"),
            
            # Floor to get age_last
            pl.col("proj_age").floor().alias("age_last"),
            
            # Combine gender and smoking
            (pl.col("gender") + pl.col("smoking")).alias("gender_smoking")
        ])
    
    # Perform vector lookup
    result = af.lookup_table_vector("mortality_rates")
    
    # Verify results
    assert result.height == 1000  # One row per policy
    assert "mortality_rate" in result.columns
    
    # Check vector lengths
    mortality_rates = result.get_column("mortality_rate")
    assert all(len(rates) == 481 for rates in mortality_rates)  # Each policy has 481 months
    
    # Verify specific values
    first_policy = result.filter(pl.col("policy_id") == 0)
    rates = first_policy.get_column("mortality_rate")[0]
    
    # Rates should increase with age
    assert all(rates[i] <= rates[i+1] for i in range(len(rates)-1))

def test_vector_lookup_batched():
    """Test vector lookup with batch processing."""
    # Similar setup as above
    # ...
    
    # Test with different batch sizes
    batch_sizes = [100, 250, 500]
    results = []
    
    for batch_size in batch_sizes:
        result = af.lookup_table_vector("mortality_rates", batch_size=batch_size)
        results.append(result)
    
    # All results should be identical regardless of batch size
    for r1, r2 in zip(results[:-1], results[1:]):
        assert r1.frame_equal(r2)

def test_vector_lookup_edge_cases():
    """Test vector lookup edge cases and error handling."""
    # Test missing table
    with pytest.raises(RuntimeError, match="Table 'missing_table' not found"):
        af.lookup_table_vector("missing_table")
    
    # Test empty DataFrame
    empty_af = ActuarialFrame(pl.DataFrame())
    result = empty_af.lookup_table_vector("mortality_rates")
    assert result.height == 0
    
    # Test null values in vectors
    policies_with_nulls = pl.DataFrame({
        "policy_id": [1, 2],
        "age_last": [[20, None, 22], [25, 26, None]],
        "gender_smoking": [["MS", "MS", "MS"], ["FNS", None, "FNS"]]
    })
    
    af_nulls = ActuarialFrame(policies_with_nulls)
    result = af_nulls.lookup_table_vector("mortality_rates")
    
    # Verify null handling
    assert result.height == 2
    assert result.get_column("mortality_rate")[0][1] is None  # Null age
    assert result.get_column("mortality_rate")[1][1] is None  # Null gender_smoking
```

**Step 3.2: Update Example Models**

```python
def life_model_vector(df: ActuarialFrame) -> ActuarialFrame:
    """Example life model using vector lookups."""
    # Add projection vectors
    df = df.with_columns([
        # Create monthly projection vectors
        (pl.Series(name="proj_months", values=range(481))).cast(pl.Float64),
        
        # Calculate age progression
        (pl.col("age") + pl.col("proj_months") / 12).alias("proj_age"),
        pl.col("proj_age").floor().alias("age_last"),
        
        # Create lookup keys
        (pl.col("gender") + pl.col("smoking")).alias("gender_smoking"),
        
        # Calculate policy duration
        (pl.col("policy_duration") + pl.col("proj_months") / 12).alias("policy_duration")
    ])
    
    # Lookup mortality rates using vector operation
    mortality_result = df.lookup_table_vector("mortality_rates")
    df = df.with_column(mortality_result.get_column("mortality_rate"))
    
    # Calculate mortality cost vectors
    df = df.with_column(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("mortality_cost")
    )
    
    return df
```

**Step 3.3: Performance Benchmarking**

```python
import time
from typing import Callable
import pandas as pd

def benchmark_vector_lookup(
    df_sizes: list[int],
    batch_sizes: list[int],
    iterations: int = 3
) -> pd.DataFrame:
    """Benchmark vector lookup performance."""
    results = []
    
    for size in df_sizes:
        # Create test data
        policies = create_test_policies(size)
        af = ActuarialFrame(policies)
        
        for batch_size in batch_sizes:
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                _ = af.lookup_table_vector("mortality_rates", batch_size=batch_size)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            results.append({
                "df_size": size,
                "batch_size": batch_size,
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times)
            })
    
    return pd.DataFrame(results)

def profile_memory_usage(func: Callable, *args, **kwargs) -> dict:
    """Profile memory usage of a function."""
    import tracemalloc
    import gc
    
    # Force garbage collection
    gc.collect()
    
    # Start memory tracing
    tracemalloc.start()
    
    # Execute function
    start_time = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start_time
    
    # Get memory stats
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    return {
        "current_memory": current / 1024**2,  # MB
        "peak_memory": peak / 1024**2,  # MB
        "execution_time": elapsed
    }
```

The testing phase provides:

1. **Comprehensive Integration Tests**
   - End-to-end vector lookup testing
   - Edge case handling
   - Batch processing verification
   - Null value handling

2. **Real-world Example Models**
   - Updated life model using vector operations
   - Clear demonstration of vector lookup usage
   - Performance optimized implementation

3. **Performance Benchmarking**
   - Execution time measurements
   - Memory usage profiling
   - Batch size optimization
   - Scalability testing

4. **Quality Assurance**
   - Proper error handling verification
   - Data consistency checks
   - Memory leak detection
   - Edge case coverage

This testing suite ensures the vector lookup functionality is robust, performant, and ready for production use.

## Worked Example: Mortality Table Lookup

To illustrate the functionality, let's walk through a complete example of using vector lookups with a mortality table:

### 1. Initial Setup: Mortality Table

```python
# Mortality table structure (from the assumptions/mortality_rates.parquet file):
# age-last | MNS   | MS     | FNS    | FS
# 18       | 0.0001| 0.00015| 0.00008| 0.00012
# 19       | 0.000105| 0.0001575| 0.000084| 0.000126
# ... and so on
```

### 2. Before: Current Scalar Approach

```python
def life_model_before(df):
    # Create projection vectors
    df["age"] = df["age"] + (df["proj_months"] / 12)  # Vector of ages
    df["age_last"] = floor(df["age"])  # Vector of age_last values
    df["gender_smoking"] = df["gender"] + df["smoking_status"]
    
    # PROBLEM: Need to extract scalar values for lookup
    current_df = df.collect()
    
    # Create a lookup frame with ONLY the first values (current values)
    # This loses all projection information!
    lookup_frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policyholder_nr": current_df["policyholder_nr"],
                # This fails with: cannot cast List type (inner: 'Float64', to: 'Float64')
                "age_last": current_df["age_last"].cast(pl.Float64),  
                "gender_smoking": current_df["gender_smoking"],
            }
        )
    )
    
    # Lookup only returns values for current age, not projected ages
    lookup_result = lookup_frame.lookup_table("mortality_rates")
    mortality_rate = lookup_result.collect()["mortality_rate"]
    
    # We'd need a separate way to generate mortality rates for all projection periods
    # ...complex and error-prone code here...
    
    return df
```

### 3. After: Vector Lookup Approach

```python
def life_model_after(df):
    # Create projection vectors - same as before
    df["age"] = df["age"] + (df["proj_months"] / 12)
    df["age_last"] = floor(df["age"])
    df["gender_smoking"] = df["gender"] + df["smoking_status"]
    
    # SOLUTION: Use vector lookup directly
    # This automatically handles lookup for EACH element in the vectors
    lookup_result = df.lookup_table_vector("mortality_rates")
    
    # mortality_rate is now a vector matching each projection period
    df["mortality_rate"] = lookup_result["mortality_rate"]
    
    # Calculate vector-based mortality costs
    df["mortality_cost"] = df["sum_assured"] * df["mortality_rate"]
    
    return df
```

### 4. What Happens Inside

1. The vector lookup function detects that `age_last` and `gender_smoking` contain vectors
2. It expands these into individual rows (one for each projection period)
3. It performs the lookup using the standard mechanism
4. It re-assembles the results back into vectors
5. The final result contains vector columns with mortality rates for each projection period

### 5. Benefits

- **Correctness**: Ensures that lookups are performed for each projection period
- **Performance**: Performs all lookups in a single operation
- **Simplicity**: Dramatically simplifies model code
- **Consistency**: Maintains the vector structure throughout the calculation

## Performance Considerations

The new approach provides substantial benefits:

1. **Reduced Memory Usage**: By operating directly on vectors, we avoid creating large intermediate DataFrames
2. **Fewer Operations**: Instead of multiple individual lookups, we perform a single vectorized operation
3. **Rust Implementation**: The core logic is implemented in Rust for maximum performance
4. **Batch Processing**: For very large datasets, batch processing further optimizes memory usage

## Implementation Summary

This implementation enhances the actuarial framework with vector-aware lookups that:

1. Automatically detect vector columns in the input data
2. Efficiently perform lookups for each element in these vectors
3. Return results as aligned vectors ready for further vector operations
4. Work seamlessly within the existing ActuarialFrame API

This capability is essential for building accurate and performant actuarial models that involve time-based projections.
