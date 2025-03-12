# Debuggable Actuarial Modeling DSL: Implementation Plan

## Overview

This plan outlines the approach for implementing a Python-native DSL for actuarial modeling that combines excellent debugging capabilities with high-performance execution. The DSL will allow actuaries to write and debug pure Python code while leveraging Polars optimizations for performance.

## High-Level Architecture

```
┌─────────────────────────────┐
│    User Python Code         │
│    (Actuarial Models)       │
└───────────────┬─────────────┘
                │
                ▼
┌─────────────────────────────┐
│    ActuarialFrame           │◄───┐
│    (DataFrame Wrapper)      │    │
└───────────────┬─────────────┘    │
                │                   │
                ▼                   │
┌─────────────────────────────┐    │
│    Execution Context        │    │
│    (Debug/Optimize Modes)   │    │
└───────────────┬─────────────┘    │
                │                   │
        ┌───────┴────────┐         │
        ▼              ▼           │
┌─────────────┐  ┌──────────────┐  │
│ Debug Mode  │  │ Optimize Mode│  │
│ (Python)    │  │ (Polars/Rust)│  │
└─────────────┘  └──────────────┘  │
                        │          │
                        ▼          │
                ┌──────────────┐   │
                │ Polars       │   │
                │ Execution    │───┘
                └──────────────┘
```

## Implementation Steps

### Phase 1: Core Infrastructure

#### 1.1: Project Setup
- Create package structure with `pyproject.toml`
- Set up test infrastructure
- Create basic documentation structure

#### 1.2: Execution Context
- Implement `ExecutionContext` as global state manager
- Add mode control (debug/optimize)
- Create context manager for temporary mode changes

#### 1.3: Basic ActuarialFrame
- Create class wrapping Polars LazyFrame
- Implement data loading from various sources
- Add basic collect/materialize functionality

#### 1.4: Column Access
- Implement `ColumnProxy` for column operations
- Support basic column access via `df['column']`
- Add basic property inspection

### Phase 2: Operation Capturing

#### 2.1: Column Assignment
- Implement `__setitem__` to capture `df['col'] = value`
- Support assignment from literal values
- Handle assignment from other columns

#### 2.2: Function Tracing
- Create tracing decorator for functions
- Implement mechanism to enable/disable tracing
- Store function call context

#### 2.3: Computation Graph
- Define computation graph structure
- Implement methods to add operations to graph
- Create visualization of computation graph

#### 2.4: Basic Arithmetic
- Support column + column operations
- Implement column + scalar operations
- Support other arithmetic operations (-, *, /, etc.)

### Phase 3: Execution Modes

#### 3.1: Debug Mode
- Implement direct Python execution pathway
- Support local variable access
- Enable print statement and logging in user code

#### 3.2: Optimize Mode
- Create Polars expression compilation
- Implement lazy execution of operations
- Add batch processing of operations

#### 3.3: Mode Switching
- Implement environment variable control
- Add configuration parameter support
- Create context manager for temporary mode switching

#### 3.4: Metrics & Logging
- Add performance metrics collection
- Implement execution statistics
- Create debug logging for operation tracking

### Phase 4: Function Integration

#### 4.1: Numba JIT Support
- Add basic Numba vectorization
- Implement njit compilation for functions
- Create fallback pathway for non-compilable functions

#### 4.2: Vectorized Operations
- Support element-wise operations
- Implement broadcasting behavior
- Create map/apply functions for columns

#### 4.3: Function Fallbacks
- Implement Python fallback for non-compilable functions
- Add warnings when falling back to slower execution
- Support arbitrary Python code execution

#### 4.4: Plugin Integration
- Create plugin registry system
- Implement plugin function calling
- Support for existing plugins

### Phase 5: Error Handling & Debugging

#### 5.1: Enhanced Errors
- Improve error messages with context
- Implement source line tracking
- Add operation history to error messages

#### 5.2: Operation Logging
- Create detailed operation log
- Implement query plan visualization
- Add execution timeline

#### 5.3: Debugging Support
- Ensure compatibility with pdb and IDE debuggers
- Support for print statements in user code
- Add introspection capabilities

#### 5.4: Visualization Tools
- Create graph visualization for computation
- Implement execution plan visualization
- Add performance profiling view

### Phase 6: Testing & Examples

#### 6.1: Unit Testing
- Implement tests for each component
- Add property-based testing for operations
- Create regression test suite

#### 6.2: Integration Testing
- Test with real actuarial models
- Verify compatibility with third-party libraries
- Ensure identical results between modes

#### 6.3: Performance Testing
- Create benchmarks for common operations
- Compare with pure Polars implementation
- Test with various dataset sizes

#### 6.4: Documentation & Examples
- Create comprehensive API documentation
- Build example notebooks
- Write user guide with best practices

## LLM Implementation Prompts

The following prompts can be used with a code-generation LLM to implement each step in a test-driven manner:

### Prompt 1: Project Setup and Structure

```
We're building a Python-native DSL for actuarial modeling that supports both debugging (for development) and optimization (for production). Let's start by setting up the project structure.

Create a Python package called `gaspatchio_core` with a subpackage `dsl` and module `debuggable`. The project should use Poetry for dependency management.

The key dependencies are:
- polars (for DataFrame operations)
- numba (for JIT compilation)
- pytest (for testing)

Create a basic directory structure including:
- A main package module
- A test directory
- Basic documentation files

Implement a minimal `__init__.py` that exports the main classes we'll implement later.

Also, create a basic README.md with an overview of the project based on the debuggable DSL concept: A Python-native DSL for actuarial modeling that allows debugging while maintaining performance.

Output all necessary files with their content.
```

### Prompt 2: ExecutionContext Implementation

```
Now, let's implement the ExecutionContext class which will control the execution mode (debug or optimize) for our DSL.

Create a new module `execution.py` within the `gaspatchio_core.dsl` package with:

1. An `ExecutionMode` enum with two values: DEBUG and OPTIMIZE
2. An `ExecutionContext` class with:
   - A mode property (default: DEBUG)
   - Verbose flag (default: True)
   - Methods to get/set the mode
   - A context manager protocol implementation for temporary mode changes
   
3. A global default execution context
4. Helper functions:
   - `get_default_mode()`
   - `set_default_mode(mode)`
   - A context manager function `execution_mode(mode)` that temporarily changes the mode

Create corresponding unit tests that verify:
- Default mode is DEBUG
- Mode can be changed
- Context manager properly restores previous mode
- Verbose setting works correctly

Please include both the implementation and test code.
```

### Prompt 3: Column Proxy Basic Implementation

```
Let's implement the ColumnProxy class that will handle column operations for our ActuarialFrame.

Create a new module `column.py` within the `gaspatchio_core.dsl` package. 

The ColumnProxy class should:
1. Initialize with a column name and a reference to its parent ActuarialFrame
2. Implement __repr__ and __str__ for easy inspection
3. Include basic properties to access column metadata
4. Prepare for later implementation of arithmetic operations

Also create a test file that verifies:
- ColumnProxy can be created with a name and parent
- String representation works correctly
- Basic properties function as expected

For now, we'll just implement the class structure and properties - we'll add arithmetic operations in a later step. Focus on making the API clean and intuitive.

Please include both the implementation and test code.
```

### Prompt 4: ActuarialFrame Basic Implementation

```
Now, let's implement the basic ActuarialFrame class that will be the main entry point for our DSL.

Create a new module `frame.py` within the `gaspatchio_core.dsl` package.

The ActuarialFrame class should:
1. Initialize with optional data (None, Polars DataFrame, Polars LazyFrame, or compatible data)
2. Import and use the ExecutionContext we created earlier
3. Implement __getitem__ to access columns (returning a ColumnProxy)
4. Add basic methods:
   - collect() - materialize the LazyFrame
   - head() and tail() - for previewing data
   - Add a _df property to store the underlying LazyFrame

Create corresponding tests that verify:
- ActuarialFrame can be created from different data sources
- Column access via __getitem__ returns a ColumnProxy
- collect(), head(), and tail() methods work correctly
- Integration with ExecutionContext (mode setting)

For now, focus on the basic structure and data access - we'll add computation capabilities in subsequent steps.

Please include both the implementation and test code.
```

### Prompt 5: Operation Capturing - Column Assignment

```
In this step, we'll implement column assignment to capture operations for our computation graph.

Enhance the ActuarialFrame class in `frame.py` to:
1. Add a _computation_graph list to store operations
2. Implement __setitem__ to capture df['column'] = value operations
3. Add _convert_to_expr method to convert Python values to Polars expressions
4. Support different types of values:
   - Scalars (converted to pl.lit)
   - ColumnProxy (extract the column name)
   - Polars expressions (pass through)
   - NumPy arrays (convert to literals)

Update the existing tests and add new ones that verify:
- Column assignment with scalars works
- Column assignment with other columns works
- Assignment operations are captured in the computation graph
- _convert_to_expr correctly handles different value types

This should allow basic column assignments like df['new_column'] = df['existing_column'] * 2 to be captured for later execution.

Please include both the implementation changes and updated test code.
```

### Prompt 6: Function Tracing Decorator

```
Let's implement function tracing to capture operations inside user-defined functions.

Enhance the ActuarialFrame class to:
1. Add a _tracing flag (default: False)
2. Implement a trace decorator method that:
   - Accepts a function
   - Sets _tracing to True before execution
   - Captures operations during function execution
   - Restores _tracing after completion
   - Returns the function result

The trace decorator should behave differently based on the execution mode:
- In debug mode: execute the function directly
- In optimize mode: capture operations to the computation graph and apply them in batch

Create tests that verify:
- The trace decorator can be applied to functions
- Operations inside traced functions are captured
- Different behavior in debug vs optimize mode
- The function's return value is preserved

Example usage:
```python
@df.trace
def my_calculation(df):
    df['result'] = df['input'] * 2
    return df['result']

result = my_calculation(df)
```

Please update the implementation and tests accordingly.
```

### Prompt 7: Basic Arithmetic Operations

```
Now, let's implement basic arithmetic operations for our ColumnProxy class to enable expressions like df['a'] + df['b'].

Enhance the ColumnProxy class to:
1. Implement basic arithmetic dunder methods:
   - __add__, __radd__
   - __sub__, __rsub__
   - __mul__, __rmul__
   - __truediv__, __rtruediv__
   - __pow__, __rpow__
2. Add an ExpressionProxy class that wraps Polars expressions from these operations
3. Ensure operations work with:
   - Column + Column
   - Column + scalar
   - scalar + Column

The operations should:
- Convert the operands to Polars expressions using ActuarialFrame._convert_to_expr
- Return an ExpressionProxy that wraps the resulting Polars expression
- Support chaining of operations (e.g., (df['a'] + 1) * df['b'])

Add tests that verify:
- All arithmetic operations work correctly
- Operations with scalars work
- Chained operations produce the expected results
- Operations are consistent with Polars behavior

Please update the implementation and tests accordingly.
```

### Prompt 8: Debug Mode Execution

```
Let's implement the debug mode execution pathway to allow direct Python execution for debugging.

Enhance the ActuarialFrame class to:
1. Update the trace decorator to handle debug mode:
   - When in debug mode, execute operations directly
   - Add support for print statements and breakpoints in user code
   - Store local variables in a _context dictionary for introspection
2. Update __setitem__ to execute immediately in debug mode
3. Implement direct execution of captured operations

Add tests that verify:
- Debug mode executes operations immediately
- Local variables are accessible during execution
- Print statements in user code work as expected
- Results are identical to what Polars would produce

Example usage to test:
```python
# Should execute immediately in debug mode
df = ActuarialFrame(data, mode="debug")

@df.trace
def my_function(df):
    # Breakpoints and prints should work here
    print("Processing data...")
    df['result'] = df['input'] * 2
    return df

result = my_function(df)
```

Please update the implementation and tests accordingly.
```

### Prompt 9: Optimize Mode Execution

```
Now, let's implement the optimize mode execution pathway that batches operations for performance.

Enhance the ActuarialFrame class to:
1. Update the trace decorator to handle optimize mode:
   - Capture operations to the computation graph
   - Don't execute immediately
   - Apply operations in batch at the end
2. Implement a method to apply the computation graph to the LazyFrame
3. Add an optimize() method that applies Polars optimizations
4. Create a get_execution_stats() method for performance metrics

Add tests that verify:
- Optimize mode defers execution to batch processing
- The computation graph correctly captures all operations
- The same results are produced in optimize mode as debug mode
- Execution statistics provide useful information

Example usage:
```python
# Should defer execution in optimize mode
df = ActuarialFrame(data, mode="optimize")

@df.trace
def my_function(df):
    df['result'] = df['input'] * 2
    return df

# This should capture operations without executing
df = my_function(df)

# This triggers actual execution
result = df.collect()

# Get performance metrics
stats = df.get_execution_stats()
```

Please update the implementation and tests to support optimize mode.
```

### Prompt 10: Numba JIT Integration

```
Let's add Numba JIT support to accelerate user-defined functions in optimize mode.

Enhance the ActuarialFrame class to:
1. Add a _vectorize_function method that:
   - Takes a Python function
   - Attempts to compile it with Numba in optimize mode
   - Falls back to Python execution if compilation fails
   - Uses the original function in debug mode
2. Update _convert_to_expr to handle callable functions:
   - If the value is a callable, use _vectorize_function
   - Apply the function to the appropriate column(s)
3. Add a _log_fallback method to warn when falling back to Python

Also implement a utility method in ColumnProxy:
- add an apply(func) method that applies a function to the column

Add tests that verify:
- Numba compilation works for compatible functions
- Fallback works for functions that can't be compiled
- Application of functions to columns produces correct results
- Performance improvement in optimize mode

Example usage:
```python
def calculate_risk(age):
    return math.log(max(age, 1)) * 0.01

# In optimize mode, this should compile with Numba
df['risk_factor'] = df['age'].apply(calculate_risk)
```

Please update the implementation and tests accordingly.
```

### Prompt 11: Error Handling and Debugging Support

```
Let's enhance error handling and add debugging support to make the DSL more user-friendly.

Modify the ActuarialFrame class to:
1. Add an _operation_log list to track operations for debugging
2. Enhance error messages with context:
   - Capture the source of errors
   - Provide line information when possible
   - Include details about the operation that failed
3. Implement a get_operation_log() method to retrieve the log
4. Create an _expr_to_str utility to convert expressions to readable strings

Also improve the ColumnProxy class:
- Better error messages for invalid operations
- Type checking for operations

Add tests that verify:
- Error messages include helpful context
- The operation log correctly records operations
- Debugging information is accessible
- Type errors are reported clearly

Example test scenario:
```python
try:
    # Intentionally cause an error
    df['result'] = df['non_existent_column'] * 2
except Exception as e:
    # Verify the error message contains helpful context
    assert "non_existent_column" in str(e)
    
# Check operation log
log = df.get_operation_log()
assert len(log) > 0
```

Please update the implementation and tests to improve error handling.
```

### Prompt 12: Plugin Function Integration

```
Let's implement support for plugin functions to ensure compatibility with the existing model framework.

Create a new module `plugin_support.py` within the `gaspatchio_core.dsl` package:
1. Implement a PluginRegistry class to store and manage plugin functions
2. Add a register_plugin decorator to register functions
3. Create a way to convert plugin functions to Polars expressions

Enhance the ActuarialFrame class to:
1. Add a method apply_function to apply a function to one or more columns
2. Update _convert_to_expr to handle plugin functions:
   - Check if the function is registered as a plugin
   - Use the plugin's to_polars_expr method if available
   - Fall back to Numba or Python otherwise

Add tests that simulate some typical plugin functions:
- A fill_series function (creates a series of values)
- A floor function (rounds down to integer)
- An abs_i64 function (absolute value for integers)

Verify that these plugin functions:
- Can be called on ActuarialFrame columns
- Produce the same results in both debug and optimize modes
- Integrate with the computation graph

Example usage:
```python
from gaspatchio_core.plugin import fill_series, floor

# Register plugins (this would normally be done at import time)
@register_plugin
def fill_series(count, start=0, step=1):
    # Implementation...
    pass

# Use in model
df['proj_months'] = fill_series(df['num_proj_months'], 0, 1)
df['proj_years'] = floor((df['proj_months'] - 1) / 12) + 1
```

Please implement the plugin support with tests.
```

### Prompt 13: Mode Switching and Context Management

```
Let's finalize the mode switching capabilities to make it easy to transition between debug and optimize modes.

Enhance the ExecutionContext and ActuarialFrame classes to:
1. Support environment variable control (GASPATCHIO_MODE)
2. Add mode configuration via ActuarialFrame parameters
3. Ensure the context manager properly handles nested contexts
4. Add methods to check the current mode

The ActuarialFrame should:
- Use the ExecutionContext at initialization
- Allow overriding the default mode per instance
- Sync mode changes with the global context when appropriate

Create tests that verify:
- Environment variable control works
- Configuration parameters override defaults
- Context managers properly handle mode changes
- Mode changes affect execution behavior

Example usage:
```python
# Method 1: Environment variable (set before script runs)
# GASPATCHIO_MODE=debug python run_model.py

# Method 2: Configuration parameter
from gaspatchio_core.dsl.debuggable import ActuarialFrame, run_model

# Debug mode (default during development)
df = ActuarialFrame(data, mode="debug")
result = run_model(model_calculation, df).collect()

# Optimize mode (for production)
df = ActuarialFrame(data, mode="optimize")
result = run_model(model_calculation, df).collect()

# Method 3: Context manager for temporary mode changes
with gaspatchio.execution_mode("debug"):
    # Run in debug mode, even if optimize is the default
    result = run_model(model_calculation, df).collect()
```

Please implement the mode switching capabilities with tests.
```

### Prompt 14: Performance Optimization Strategies

```
Let's implement performance optimization strategies for the optimize mode to make it as fast as possible.

Enhance the ActuarialFrame class to:
1. Add support for batching operations:
   - Combine sequential operations when possible
   - Detect patterns that can be optimized
   - Use Polars' optimization capabilities
2. Implement parallel execution control:
   - Add a threads parameter to control parallelism
   - Configure Polars to use the specified number of threads
3. Add method chaining support:
   - Return self from methods that modify the frame
   - Enable fluent API style

Create a benchmark module that tests performance:
- Compare execution times in different modes
- Measure the impact of batching operations
- Test with different dataset sizes
- Compare with pure Polars implementation

Example usage:
```python
# Configure thread count
df = ActuarialFrame(data, mode="optimize", threads=8)

# Batching operations (this should be optimized internally)
df['a'] = df['x'] + 1
df['b'] = df['a'] * 2
df['c'] = df['a'] + df['b']

# Method chaining
result = (df
    .with_column('a', df['x'] + 1)
    .with_column('b', lambda f: f['a'] * 2)
    .with_column('c', lambda f: f['a'] + f['b'])
    .collect())
```

Please implement the performance optimizations with benchmarks.
```

### Prompt 15: Integration Testing with a Complete Example

```
Let's create a comprehensive integration test with a complete actuarial model example to verify that all components work together correctly.

Create a test module that:
1. Defines a realistic actuarial model calculation function
2. Tests it in both debug and optimize modes
3. Verifies identical results between modes
4. Measures and reports performance differences

The model should demonstrate:
- Basic column operations
- User-defined functions
- Plugin function calls
- Conditional logic
- Error handling

Also implement a run_model utility function that:
- Takes a model function and ActuarialFrame
- Runs the model with appropriate tracing
- Returns the result

Example model:
```python
def actuarial_model(df):
    # Constants
    max_age = 100
    
    # Basic calculations
    df['num_proj_months'] = (max_age - df['age']) * 12 + 1
    df['proj_months'] = fill_series(df['num_proj_months'], 0, 1)
    df['proj_years'] = floor((df['proj_months'] - 1) / 12) + 1
    
    # Custom function
    def calculate_risk_factor(age):
        return math.log(max(age, 1)) * 0.01
    
    # Apply the function
    df['risk_factor'] = df['age'].apply(calculate_risk_factor)
    
    # More calculations
    df['policy_duration'] = df['proj_months'] / 12
    df['policy_expiry_month'] = (max_age - df['age']) * 12
    
    return df
```

Create a test that runs this model in both modes and verifies the results are identical.

Please implement the integration test and any necessary utility functions.
```

### Prompt 16: Documentation and User Guide

```
Let's create comprehensive documentation and a user guide for the debuggable DSL.

Create the following documentation files:

1. A detailed API reference for:
   - ActuarialFrame class
   - ColumnProxy class
   - ExecutionContext
   - Plugin integration
   - Utility functions

2. A user guide with sections on:
   - Getting started
   - Debug vs optimize modes
   - Writing actuarial models
   - Performance optimization tips
   - Debugging techniques
   - Common patterns and best practices

3. Example notebooks that demonstrate:
   - Basic usage
   - Debugging workflows
   - Performance tuning
   - Integration with plugins
   - Real-world model examples

Also update the project README with:
- Installation instructions
- Quick start guide
- Links to documentation
- Performance benchmarks
- Contribution guidelines

The documentation should follow best practices for Python projects and include docstrings for all public API elements.

Please create the documentation files with appropriate content.
```

### Prompt 17: Final Package Assembly and CLI Tool

```
Let's finalize the package by creating a command-line tool for running models and ensuring all components are properly integrated.

Create a command-line interface that:
1. Accepts a model file path or module
2. Takes configuration parameters:
   - Execution mode (debug/optimize)
   - Input data path
   - Output path
   - Verbosity level
   - Number of threads
3. Provides useful output:
   - Execution statistics
   - Performance metrics
   - Error reporting

Also ensure all components are properly exported in the package's __init__.py and update the pyproject.toml with entry points.

Example CLI usage:
```bash
# Run a model in debug mode
gaspatchio run --mode debug --input data.parquet --output results.parquet model_file.py

# Run a model in optimize mode with 8 threads
gaspatchio run --mode optimize --threads 8 --input data.parquet --output results.parquet model_file.py
```

Please implement the CLI tool and finalize the package structure for deployment.
```

### Prompt 18: Create Complete Test Suite and CI Configuration

```
Let's create a comprehensive test suite and CI configuration to ensure code quality and reliability.

Set up:
1. A complete pytest suite covering:
   - Unit tests for all components
   - Integration tests for end-to-end functionality
   - Performance tests (marked as optional for CI)
   - Property-based tests for operation correctness

2. A GitHub Actions workflow that:
   - Runs tests on multiple Python versions
   - Checks code formatting with black and ruff
   - Verifies type hints with mypy
   - Builds and validates the package
   - Generates test coverage reports

3. A pre-commit configuration that checks:
   - Code style
   - Import ordering
   - Type hints
   - Documentation strings

The test suite should achieve high coverage (>90%) and verify all key functionality.

Please implement the test suite and CI configuration.
