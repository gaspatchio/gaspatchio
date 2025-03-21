# Integrating Table Registry with ActuarialFrame

## Overview

This document outlines a detailed plan for integrating the `TableRegistry` functionality with the `ActuarialFrame` class to enable seamless lookups of tabular data (like mortality rates) within actuarial models. The integration will preserve the lazy evaluation benefits of Polars while providing an intuitive API for table lookups.

## Current State

Currently, the `TableRegistry` offers lookup functionality through direct calls to `table_registry.py_lookup()`, which requires materializing dataframes. The `ActuarialFrame` class provides a wrapper around Polars DataFrames that captures operations in a computation graph, enabling optimization and tracing.

To integrate these components, we need to extend `ActuarialFrame` with methods that work with the table registry while maintaining the benefits of operation tracing and lazy evaluation where possible.

## Implementation Plan

We'll break this down into small, iterative steps that build on each other:

### Phase 1: Basic Integration

#### Step 1.1: Add Basic Lookup Method to ActuarialFrame

Add a simple method to `ActuarialFrame` that supports looking up values from a registered table.

```python
# Prompt 1.1: Add a basic lookup_table method to ActuarialFrame

I need to add a basic lookup_table method to the ActuarialFrame class that will allow looking up values from a registered table in the TableRegistry. The method should:

1. Take a table_name parameter
2. Support both direct execution and traced execution (within the computation graph)
3. Return a new ActuarialFrame with the looked-up values

Here's the signature and context:

```python
def lookup_table(self, table_name: str) -> 'ActuarialFrame':
    """
    Lookup values from a registered table using the table registry.
    
    Args:
        table_name: Name of the registered table to lookup against current frame
        
    Returns:
        ActuarialFrame with looked up values merged in
    """
    # Implementation here
```

The implementation should check if we're in tracing mode (_tracing attribute) and either:
1. Register the operation in the computation graph if tracing
2. Perform the lookup directly using table_registry.py_lookup if not tracing

Important context:
- The ActuarialFrame has a _df attribute containing the wrapped Polars LazyFrame
- The _tracing attribute indicates if we're capturing operations
- The _computation_graph attribute stores captured operations
- We need to import table_registry from gaspatchio_core.assumptions
```

#### Step 1.2: Write Unit Tests for Basic Lookup

Create unit tests to verify the basic lookup functionality works correctly.

```python
# Prompt 1.2: Write unit tests for the ActuarialFrame lookup_table method

I need to write comprehensive unit tests for the new lookup_table method added to ActuarialFrame. The tests should verify:

1. Direct execution mode (when _tracing is False)
2. Traced execution mode (when _tracing is True)
3. Proper integration with the table_registry
4. Error handling for invalid table names

Create a new test file at gaspatchio-core/tests/test_actuarial_frame_lookup.py.

Use the existing test patterns from test_table_registry.py as a reference for how to set up test tables and verify lookup results.

Key test cases should include:
- Looking up values from a simple test table
- Testing the lookup when in traced mode (inside a model function)
- Testing lookup with composite keys
- Testing lookup with transformations (wide-to-long)
- Error cases (non-existent table, missing key columns)

Make sure to verify that the returned ActuarialFrame contains the expected data after lookup.
```

### Phase 2: Enhanced Registry Integration

#### Step 2.1: Add Registration Methods to ActuarialFrame

Add methods to register the current frame as a lookup table.

```python
# Prompt 2.1: Add table registration methods to ActuarialFrame

I need to add two methods to ActuarialFrame for registering tables with the TableRegistry:

1. `register_table` - Register the current frame as a lookup table
2. `register_table_with_transform` - Register with wide-to-long transformation

Here are the signatures:

```python
def register_table(self, table_name: str, key_spec: table_registry.KeySpec) -> 'ActuarialFrame':
    """
    Register the current frame as a lookup table.
    
    Args:
        table_name: Name to register the table as
        key_spec: KeySpec defining the key columns
        
    Returns:
        Self for method chaining
    """
    # Implementation here

def register_table_with_transform(
    self, 
    table_name: str, 
    key_spec: table_registry.KeySpec,
    transform_spec: table_registry.TransformSpec
) -> 'ActuarialFrame':
    """
    Register the current frame as a lookup table with transformation.
    
    Args:
        table_name: Name to register the table as
        key_spec: KeySpec defining the key columns
        transform_spec: TransformSpec defining how to transform the table
        
    Returns:
        Self for method chaining
    """
    # Implementation here
```

Similar to lookup_table, these methods should:
1. Check if we're in tracing mode
2. Either register the operation in the computation graph or perform the registration directly
3. Return self for method chaining

Make sure to import the necessary types from table_registry.
```

#### Step 2.2: Write Unit Tests for Registration Methods

Create unit tests for the table registration methods.

```python
# Prompt 2.2: Write unit tests for ActuarialFrame table registration methods

I need to write unit tests for the new registration methods added to ActuarialFrame:
1. register_table
2. register_table_with_transform

The tests should verify:
1. Direct execution (when _tracing is False)
2. Traced execution (when _tracing is True)
3. Proper registration with the table_registry
4. Method chaining works correctly

Add these tests to the existing test file at gaspatchio-core/tests/test_actuarial_frame_lookup.py.

Test cases should include:
- Registering a simple table and then looking it up
- Registering a table with transformation and verifying the transformation works
- Verifying that method chaining works (e.g., df.register_table(...).some_other_method())
- Testing registration within a traced model function
```

### Phase 3: Update Tracing Mechanism

#### Step 3.1: Update Trace Method to Handle Table Registry Operations

Update the `trace` method to handle table registry operations.

```python
# Prompt 3.1: Update the ActuarialFrame trace method for table registry operations

I need to update the existing `trace` method in ActuarialFrame to handle table registry operations that were captured in the computation graph. The current trace method only handles column operations ("column" type in the computation graph).

The updated method should handle these additional operation types:
1. "table_lookup" - For lookup_table operations
2. "register_table" - For register_table operations
3. "register_table_transform" - For register_table_with_transform operations

Here's the current trace method:

```python
def trace(self, func):
    """Decorator to trace a function's dataframe operations"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Enable tracing for wrapped function calls
        original_tracing = self._tracing
        self._tracing = True

        # Debug mode: execute directly
        if self._mode == "debug":
            try:
                result = func(*args, **kwargs)
            finally:
                self._tracing = original_tracing
            return result

        # Optimize mode: capture operations
        old_graph = self._computation_graph
        self._computation_graph = []

        try:
            result = func(*args, **kwargs)
        except Exception as e:
            self._computation_graph = old_graph
            self._tracing = original_tracing
            raise e

        operations = self._computation_graph
        self._computation_graph = old_graph
        self._tracing = original_tracing

        # Apply captured operations
        df = self._df
        for op_type, *op_args in operations:
            if op_type == "column":
                col_name, expr = op_args
                df = df.with_columns(expr.alias(col_name))

        self._df = df
        return result

    return wrapper
```

The updated method should handle each operation type appropriately, especially for table_lookup which requires materializing the DataFrame, performing the lookup, and then converting back to lazy.

Keep in mind that table lookups break the lazy evaluation chain, but we should preserve laziness as much as possible.
```

#### Step 3.2: Write Unit Tests for Updated Trace Method

Create unit tests to verify the updated trace method works correctly with table registry operations.

```python
# Prompt 3.2: Write unit tests for the updated ActuarialFrame trace method

I need to write unit tests for the updated trace method in ActuarialFrame that now handles table registry operations. The tests should verify:

1. Trace captures and correctly applies "table_lookup" operations
2. Trace captures and correctly applies "register_table" operations
3. Trace captures and correctly applies "register_table_transform" operations
4. Operations are applied in the correct order
5. Lazy evaluation is preserved where possible

Add these tests to gaspatchio-core/tests/test_actuarial_frame_lookup.py.

Key test cases should include:
- A model function that performs a lookup inside a traced function
- A model function that registers a table and then looks it up
- A model function that does multiple operations (column operations + table operations)
- Verify that operations are applied in the correct order

Here's an example model function to test:

```python
def test_model(df):
    # Column operation
    df["age_squared"] = df["age"] * df["age"]
    
    # Table lookup
    df = df.lookup_table("mortality_rates")
    
    # Column operation after lookup
    df["mortality_cost"] = df["sum_assured"] * df["mortality_rate"]
    
    return df
```
```

### Phase 4: Helper Methods and Optimization

#### Step 4.1: Add Helper Methods for Creating Key and Transform Specs

Add static methods to create KeySpec and TransformSpec objects.

```python
# Prompt 4.1: Add helper methods for creating KeySpec and TransformSpec objects

I need to add static helper methods to ActuarialFrame to simplify the creation of KeySpec and TransformSpec objects for table registry operations. These methods will make it easier for users to work with the table registry.

Here are the signatures:

```python
@staticmethod
def create_key_spec(source_cols: List[str], table_cols: Optional[List[str]] = None) -> table_registry.KeySpec:
    """
    Create a KeySpec for table registry operations.
    
    Args:
        source_cols: Column names in the source dataframe
        table_cols: Column names in the table dataframe (defaults to source_cols if None)
        
    Returns:
        KeySpec object ready for registry operations
    """
    # Implementation here

@staticmethod
def create_transform_spec(
    id_vars: List[str],
    value_vars: List[str],
    var_name: str,
    value_name: str
) -> table_registry.TransformSpec:
    """
    Create a TransformSpec for wide-to-long transformations.
    
    Args:
        id_vars: Columns to keep as identifiers
        value_vars: Columns to unpivot (wide format columns)
        var_name: Name for the column that will contain the unpivoted column names
        value_name: Name for the column that will contain the values
        
    Returns:
        TransformSpec object ready for registry operations
    """
    # Implementation here
```

These methods should be simple wrappers around the table_registry.KeySpec and table_registry.TransformSpec constructors but provide a more convenient interface that's integrated with ActuarialFrame.

Make sure to:
1. Import the necessary types
2. Document the methods well
3. Provide sensible defaults where appropriate
```

#### Step 4.2: Add Batch Processing for Large Datasets

Add batching support for large datasets to reduce memory usage.

```python
# Prompt 4.2: Add batch processing support for large datasets

I need to add batch processing support to ActuarialFrame to handle large datasets more efficiently when performing table lookups. This will help reduce memory usage when lookups require materializing the dataframe.

Add the following methods:

```python
def batch_operations(self, batch_size=10000):
    """
    Enable batch processing for large datasets.
    For operations like table lookups that require materialization,
    this will process the data in smaller chunks to reduce memory usage.
    
    Args:
        batch_size: Number of rows to process in each batch
        
    Returns:
        Self for method chaining
    """
    # Implementation here

def _batch_lookup(self, table_name, df_materialized):
    """
    Perform table lookup in batches to reduce memory usage.
    
    Args:
        table_name: Name of the table to lookup
        df_materialized: Materialized dataframe to process
        
    Returns:
        Result dataframe with looked up values
    """
    # Implementation here
```

The batch_operations method should enable batching by setting attributes on the ActuarialFrame instance.

The _batch_lookup method should:
1. Check if batching is enabled
2. Slice the materialized dataframe into chunks of batch_size
3. Perform lookup on each chunk
4. Concatenate the results

This method should be called by lookup_table when batching is enabled.

Update the lookup_table method to use _batch_lookup when appropriate.
```

#### Step 4.3: Write Unit Tests for Helper Methods and Batching

Create unit tests for the helper methods and batching functionality.

```python
# Prompt 4.3: Write unit tests for helper methods and batching support

I need to write unit tests for the helper methods and batching support added to ActuarialFrame. The tests should verify:

1. create_key_spec works correctly
2. create_transform_spec works correctly
3. batch_operations enables batching
4. _batch_lookup processes data in batches
5. Batching produces the same results as non-batched processing

Add these tests to gaspatchio-core/tests/test_actuarial_frame_lookup.py.

Key test cases should include:
- Creating KeySpec with and without table_cols
- Creating TransformSpec with various configurations
- Enabling batching with different batch sizes
- Looking up data with batching enabled vs. disabled
- Testing with a large dataset to verify batching works correctly

For the large dataset test, create a synthetic dataset with enough rows to require multiple batches:

```python
def test_batched_lookup():
    # Create a large synthetic dataset
    large_df = pl.DataFrame({
        "id": range(25000),
        "value": [f"value_{i}" for i in range(25000)]
    })
    
    # Create a smaller lookup table
    lookup_table = pl.DataFrame({
        "table_id": range(100),
        "table_value": [f"lookup_{i}" for i in range(100)]
    })
    
    # Register the lookup table
    key_spec = ActuarialFrame.create_key_spec(
        source_cols=["id"], 
        table_cols=["table_id"]
    )
    
    table_registry.py_register_table("test_batch_table", lookup_table, key_spec)
    
    # Create an ActuarialFrame with the large dataset
    frame = ActuarialFrame(large_df)
    
    # Test without batching
    result1 = frame.lookup_table("test_batch_table").collect()
    
    # Test with batching
    result2 = frame.batch_operations(batch_size=5000).lookup_table("test_batch_table").collect()
    
    # Results should be identical
    assert result1.equals(result2)
```
```

### Phase 5: Integration with Life Model

#### Step 5.1: Create a Helper Function for Setting up Mortality Tables

Create a helper function to set up mortality tables for use in life models.

```python
# Prompt 5.1: Create a helper function for setting up mortality tables

I need to create a helper function that sets up mortality tables for use in life models. This function should:

1. Load a mortality table from a parquet file
2. Create a KeySpec and TransformSpec for the table
3. Register the table with the TableRegistry using the ActuarialFrame methods

Here's the signature:

```python
def setup_mortality_table(mortality_file_path: str) -> None:
    """
    Setup the mortality table for lookup.
    This function loads a mortality table from a parquet file and registers it
    with the TableRegistry using appropriate transformations.
    
    Args:
        mortality_file_path: Path to the mortality table file
    """
    # Implementation here
```

The implementation should:
1. Load the mortality table using polars.read_parquet
2. Create an ActuarialFrame from the table
3. Use ActuarialFrame.create_key_spec to create a KeySpec for age-last and sex_smoking
4. Use ActuarialFrame.create_transform_spec to transform from wide format (MNS, FNS, MS, FS columns) to long format
5. Register the table with a name like "mortality_rates"

This function should be added to gaspatchio-core/src/gaspatchio_core/assumptions/setup.py (create this file if it doesn't exist).
```

#### Step 5.2: Update the Life Model to Use ActuarialFrame Lookup

Update the life model to use the new ActuarialFrame lookup methods.

```python
# Prompt 5.2: Update the life model to use ActuarialFrame lookup methods

I need to update the life model in gaspatchio-core/jobs/example/model.py to use the new ActuarialFrame lookup methods for mortality rates. The current model doesn't actually perform the lookup (it's commented out).

Here's the current model:

```python
def life_model(df):
    """Simple model function that works with the actual model points columns"""
    # Add age squared calculation
    max_age = 100
    df["num_proj_months"] = (max_age - df["age"]) * 12 + 1

    # Using custom plugin functions
    df["proj_months"] = fill_series(df["num_proj_months"], 0, 1)
    df["proj_years"] = floor((df["proj_months"] - 1) / 12) + 1

    # Update age with monthly increment
    df["age"] = df["age"] + (df["proj_months"] / 12)

    # Use floor to get age last
    df["age_last"] = floor(df["age"])

    df["gender_smoking"] = df["gender"] + df["smoking_status"]

    # df["mortality_rate"] = lookup(
    #    df["age_last"], df["gender_smoking"], table_name="mortality"
    # )

    # df["mortality_rate"] =
    # df["lapse_rate"] =

    return df
```

The updated model should:
1. Create a combined "sex_smoking" field from gender and smoking_status
2. Use the lookup_table method to get mortality rates from the "mortality_rates" table
3. Calculate mortality cost as sum_assured * mortality_rate

Also add a main function that:
1. Takes a model_size parameter ("small", "medium", "large")
2. Sets up file paths based on the model size
3. Calls setup_mortality_table to register the mortality table
4. Loads model points and creates an ActuarialFrame
5. Runs the model and saves the results
6. Prints some basic statistics

Make sure to import the necessary modules and functions.
```

#### Step 5.3: Write End-to-End Tests for the Life Model

Create end-to-end tests to verify the integration works correctly in a real model.

```python
# Prompt 5.3: Write end-to-end tests for the life model with ActuarialFrame lookup

I need to write end-to-end tests for the life model that uses ActuarialFrame lookup for mortality rates. These tests should verify that the whole integration works correctly in a realistic scenario.

Create a new test file at gaspatchio-core/tests/test_life_model_integration.py.

The tests should:
1. Set up a test mortality table
2. Create test model points
3. Run the life model
4. Verify the results contain expected mortality rates and calculations

Key test cases:
- Basic model with a few model points and mortality rates
- Test with different ages and gender/smoking combinations
- Test with run_model function to verify tracing works correctly

Example test structure:

```python
def setup_test_mortality_table():
    """Create a test mortality table and register it"""
    # Create a simple mortality table with rates by age and sex_smoking
    mortality_df = pl.DataFrame({
        "age-last": list(range(18, 101)),
        "MNS": [0.001 * (1 + age/100) for age in range(18, 101)],  # Male Non-Smoker
        "FNS": [0.0008 * (1 + age/100) for age in range(18, 101)],  # Female Non-Smoker
        "MS": [0.0015 * (1 + age/100) for age in range(18, 101)],   # Male Smoker
        "FS": [0.0012 * (1 + age/100) for age in range(18, 101)],   # Female Smoker
    })
    
    # Use the helper functions to register the table
    # ... implementation ...

def create_test_model_points():
    """Create test model points for testing"""
    # Create model points with different age, gender, smoking status combinations
    # ... implementation ...

def test_life_model_mortality_lookup():
    """Test that the life model correctly looks up mortality rates"""
    # Setup
    setup_test_mortality_table()
    model_points = create_test_model_points()
    
    # Create an ActuarialFrame from the model points
    frame = ActuarialFrame(model_points)
    
    # Run the model
    result = life_model(frame)
    
    # Verify results
    result_df = result.collect()
    
    # Check specific values for different combinations
    # ... implementation ...
```

Make sure to test both direct execution and traced execution with run_model.
```

### Phase 6: Documentation and Finalization

#### Step 6.1: Create Usage Documentation

Create comprehensive documentation for the new functionality.

```python
# Prompt 6.1: Create comprehensive documentation for the ActuarialFrame table registry integration

I need to create comprehensive documentation for the ActuarialFrame table registry integration. This documentation should explain:

1. The overall architecture and how the components fit together
2. How to use the new methods in ActuarialFrame
3. Best practices for working with table lookups in models
4. Performance considerations and optimization techniques

The documentation should be added to gaspatchio-core/docs/actuarial_frame.md.

Include code examples for common use cases:
- Setting up mortality tables
- Looking up rates in a model
- Using batch processing for large datasets
- Advanced usage patterns

Structure the documentation with clear sections and subsections, with a table of contents at the beginning.

Example structure:
1. Introduction
2. Architecture Overview
3. Basic Usage
4. Advanced Features
5. Performance Optimization
6. API Reference
7. Examples
8. Troubleshooting
```

#### Step 6.2: Create a Comprehensive Example Notebook

Create a Jupyter notebook with an end-to-end example.

```python
# Prompt 6.2: Create a comprehensive example notebook for ActuarialFrame table registry integration

I need to create a Jupyter notebook that demonstrates the ActuarialFrame table registry integration with an end-to-end example. This notebook should serve as both documentation and a tutorial.

The notebook should be placed at gaspatchio-core/examples/table_registry_integration.ipynb.

It should cover:
1. Loading and preparing mortality tables
2. Setting up model points
3. Registering tables with the registry
4. Running a life model with lookup
5. Analyzing the results
6. Performance comparisons and optimizations

Include explanatory text cells between code cells to guide the reader through the example.

Include visualizations where appropriate (e.g., mortality curves, model results).

The notebook should be self-contained and runnable, with all necessary imports and setup.

Example structure:
- Introduction and setup
- Loading and exploring mortality data
- Transforming tables for lookups
- Setting up model points
- Running the model
- Analyzing results
- Performance optimization techniques
- Conclusion and next steps
```

## Testing Strategy

Each phase of implementation should be thoroughly tested with both unit tests and integration tests. The testing strategy should:

1. Test each new method in isolation
2. Test the integration of methods in realistic scenarios
3. Test both direct execution and traced execution modes
4. Test performance with large datasets
5. Test edge cases and error handling

## Conclusion

This implementation plan provides a clear, step-by-step approach to integrating the TableRegistry with ActuarialFrame. By following these steps, you will create a powerful, flexible, and efficient system for actuarial modeling with lookup tables.

The integration maintains the benefits of both systems:
- Lazy evaluation and operation tracing from ActuarialFrame
- Efficient table lookups and transformations from TableRegistry

The result will be a cohesive, performant system that makes it easy to build complex actuarial models with lookup tables.
