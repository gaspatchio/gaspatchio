# Python-Native DSL: Debuggable Actuarial Modeling

## Background & Motivation

Our current DSL approach provides excellent performance by translating Python-like code into Polars operations. However, the AST-based translation presents significant challenges for actuaries when debugging and developing models. We need a complementary approach that:

1. Allows actuaries to write and debug pure Python code
2. Maintains high performance through Polars optimizations
3. Supports familiar debugging tools (breakpoints, print statements)
4. Seamlessly integrates with our existing plugins and model framework

## Proposed Solution

Implement a Python-native DSL that allows actuaries to write code in regular Python while capturing operations for optimization. This approach will:

- Execute regular Python code directly (including imports, functions, loops)
- Capture dataframe operations in a computation graph
- Optimize by converting Python operations to Polars expressions where possible
- Support our existing plugin functions

### Pros

- **Debuggability**: Standard Python debugging tools (breakpoints, print statements) work
- **Familiarity**: Actuaries write standard Python code without special syntax
- **Flexibility**: Supports all Python libraries (numpy, scipy, etc.)
- **Integration**: Works with existing plugin functions
- **Transparency**: Operations are visible as regular Python code

### Cons

- **Performance Gap**: Some pure Python functions will be slower than native Polars ops
- **Memory Overhead**: Converting between Python and Polars has memory cost
- **Limited Optimization**: The optimizer can't see through all Python operations
- **Implementation Complexity**: More complex to implement than pure AST parsing

## Dual Execution Model

A key design principle of our approach is the clear separation between the development experience and the execution engine. This creates a duality that provides both excellent UX and high performance.

### Development Mode (Debug Mode)

In development mode, we prioritize debuggability and transparency:

- Execute operations step-by-step in the Python interpreter
- Support for native Python debugging tools (breakpoints, pdb, IDE debuggers)
- Allow print statements and logging within the model logic
- Support introspection of intermediate results
- Provide clear, detailed error messages with context
- Allow execution of any Python code, including third-party libraries
- Maintain a more relaxed execution environment that prioritizes correctness over speed

### Production Mode (Optimize Mode)

In production mode, we prioritize performance and efficiency:

- Batch operations into optimized Polars/Rust execution plans
- Employ Numba JIT compilation for custom functions
- Utilize multithreading and vectorization via Polars
- Minimize Python interpreter overhead
- Optimize memory usage by avoiding unnecessary conversions
- Apply domain-specific optimization rules based on actuarial patterns
- Provide performance metrics and execution statistics

### Mode Switching

The system will offer several ways to switch between modes:

```python
# Method 1: Environment variable
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

## Implementation Requirements

### 1. Core Classes

The implementation should include at minimum:

- `ActuarialFrame`: A wrapper around Polars LazyFrame that captures operations
- `ColumnProxy`: A proxy for column operations that translates to Polars expressions
- Decorator(s) for tracing Python functions and capturing operations
- `ExecutionContext`: A context manager to control execution mode and settings

### 2. Numba Integration for Performance

To bridge the performance gap between Python and compiled code, we'll integrate Numba JIT compilation:

```python
class ActuarialFrame:
    # ... existing code ...
    
    def _vectorize_function(self, func):
        """Convert a Python function to a vectorized Polars expression"""
        # Use signature to determine inputs and outputs
        sig = inspect.signature(func)
        
        if self._mode == "optimize":
            # Try to compile with Numba for speed in optimize mode
            try:
                # For vectorized operations
                jit_func = numba.vectorize(func)
                return pl.map_expr(lambda s: jit_func(s))
            except Exception as e:
                # If Numba vectorize fails, try njit
                try:
                    jit_func = numba.njit(func)
                    return pl.map_expr(lambda s: jit_func(s))
                except Exception as e2:
                    # Log that we're falling back to Python
                    self._log_fallback(func, e2)
                    # Fall back to Python UDF
                    return pl.map_expr(func)
        else:
            # In debug mode, use the original Python function
            return pl.map_expr(func)
    
    def _log_fallback(self, func, exception):
        """Log when we fall back to Python execution"""
        if self._verbose:
            log.warn(f"Function {func.__name__} couldn't be compiled with Numba. "
                    f"Falling back to Python execution. Reason: {str(exception)}")
            log.warn(f"For better performance, consider rewriting this function "
                    f"to use Numba-compatible operations.")
```

### 3. Enhanced Error Messages and Logging

Improve debugging by providing clear, contextual error messages:

```python
class ActuarialFrame:
    # ... existing code ...
    
    def __init__(self, data=None, mode="debug", verbose=True):
        self._df = data.lazy() if hasattr(data, 'lazy') else (data or pl.LazyFrame())
        self._computation_graph = []
        self._tracing = False
        self._context = {}  # Store local variables
        self._mode = mode
        self._verbose = verbose
        self._operation_log = []  # Track operations for debugging
    
    def __setitem__(self, key, value):
        """Capture df['column'] = value operations"""
        try:
            if self._tracing:
                # When inside a traced function, register operation
                expr = self._convert_to_expr(value)
                self._computation_graph.append(('column', key, expr))
                if self._verbose:
                    self._operation_log.append(f"Set column '{key}' = {self._expr_to_str(value)}")
            else:
                # Direct execution when not tracing
                expr = self._convert_to_expr(value)
                self._df = self._df.with_column(expr.alias(key))
                if self._verbose:
                    self._operation_log.append(f"Set column '{key}' = {self._expr_to_str(value)}")
        except Exception as e:
            # Enhance the error with context
            raise type(e)(f"Error setting column '{key}': {str(e)}. "
                         f"Value type: {type(value).__name__}") from e
        return self
    
    def _expr_to_str(self, value):
        """Convert an expression to a readable string for logging"""
        if isinstance(value, ColumnProxy):
            return f"Column[{value.name}]"
        elif isinstance(value, pl.Expr):
            return str(value)
        elif callable(value):
            return f"Function[{value.__name__}]"
        else:
            return repr(value)
    
    def get_operation_log(self):
        """Return the operation log for debugging"""
        return self._operation_log
```

### 4. Support for Third-Party Libraries

Our design explicitly supports integration with third-party libraries and user-defined functions:

```python
class ActuarialFrame:
    # ... existing code ...
    
    def apply_function(self, func, *columns):
        """Apply a function to one or more columns"""
        try:
            # In debug mode, execute the Python function directly
            if self._mode == "debug":
                args = [self[col] for col in columns]
                result = func(*args)
                return result
            
            # In optimize mode, try to convert to Polars expression
            column_exprs = [pl.col(col) if isinstance(col, str) else col for col in columns]
            
            # Check if function is already optimized for Polars
            if hasattr(func, 'to_polars_expr'):
                return func.to_polars_expr(*column_exprs)
            
            # Try to use Numba for optimization
            try:
                jit_func = numba.njit(func)
                return pl.map_multiple(column_exprs, jit_func)
            except:
                # Fall back to Python UDF with a warning
                if self._verbose:
                    log.warn(f"Function {func.__name__} running in Python mode (slower). "
                           f"Consider optimizing this function for better performance.")
                return pl.map_multiple(column_exprs, func)
                
        except Exception as e:
            raise type(e)(f"Error applying function '{func.__name__}': {str(e)}") from e
```

### 5. Example Implementation

```python
import polars as pl
import numpy as np
import inspect
from functools import wraps
import numba
import logging as log
from contextlib import contextmanager

# Execution mode context manager
@contextmanager
def execution_mode(mode):
    old_mode = gaspatchio.get_default_mode()
    try:
        gaspatchio.set_default_mode(mode)
        yield
    finally:
        gaspatchio.set_default_mode(old_mode)

class ActuarialFrame:
    """A DataFrame wrapper that captures operations while allowing direct Python execution"""
    
    def __init__(self, data=None, mode=None, verbose=None):
        self._df = data.lazy() if hasattr(data, 'lazy') else (data or pl.LazyFrame())
        self._computation_graph = []
        self._tracing = False
        self._context = {}  # Store local variables
        
        # Use global defaults if not specified
        self._mode = mode if mode is not None else gaspatchio.get_default_mode()
        self._verbose = verbose if verbose is not None else gaspatchio.get_default_verbose()
        self._operation_log = []
        
    def __getitem__(self, key):
        """Allow df['column'] access"""
        if isinstance(key, str):
            return ColumnProxy(key, self)
        return self
        
    def __setitem__(self, key, value):
        """Capture df['column'] = value operations"""
        if self._tracing:
            # When inside a traced function, register operation
            expr = self._convert_to_expr(value)
            self._computation_graph.append(('column', key, expr))
        else:
            # Direct execution when not tracing
            self._df = self._df.with_column(self._convert_to_expr(value).alias(key))
        return self
    
    def _convert_to_expr(self, value):
        """Convert Python values to Polars expressions"""
        if isinstance(value, ColumnProxy):
            return pl.col(value.name)
        elif isinstance(value, np.ndarray):
            return pl.lit(value)
        elif isinstance(value, pl.Expr):
            # Direct Polars expressions (including plugin functions)
            return value
        elif callable(value) and not isinstance(value, pl.Expr):
            # Function that needs to be vectorized
            return self._vectorize_function(value)
        elif hasattr(value, '_expr'):
            return value._expr
        else:
            return pl.lit(value)
    
    def _vectorize_function(self, func):
        """Convert a Python function to a vectorized Polars expression"""
        # Implementation varies by mode (debug vs optimize)
        if self._mode == "optimize":
            try:
                # Try to use Numba in optimize mode
                jit_func = numba.vectorize(func)
                return pl.map_expr(lambda s: jit_func(s))
            except Exception as e:
                if self._verbose:
                    log.warn(f"Function {func.__name__} couldn't be compiled with Numba. "
                           f"Falling back to Python execution.")
                # Fall back to Python UDF
                return pl.map_expr(func)
        else:
            # In debug mode, use the original Python function
            return pl.map_expr(func)
    
    def trace(self, func):
        """Decorator to trace a function's dataframe operations"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Enable tracing for wrapped function calls
            self._tracing = True
            
            # Debug mode: execute directly
            if self._mode == "debug":
                result = func(*args, **kwargs)
                self._tracing = False
                return result
            
            # Optimize mode: capture operations
            old_graph = self._computation_graph
            self._computation_graph = []
            
            result = func(*args, **kwargs)
            
            operations = self._computation_graph
            self._computation_graph = old_graph
            self._tracing = False
            
            # Apply captured operations
            df = self._df
            for op_type, *op_args in operations:
                if op_type == "column":
                    col_name, expr = op_args
                    df = df.with_column(expr.alias(col_name))
            
            self._df = df
            return result
        return wrapper
    
    def collect(self):
        """Execute and materialize the dataframe"""
        return self._df.collect()
    
    def optimize(self):
        """Apply Polars optimizations to the computation graph"""
        # Polars already does this, but we could add domain-specific optimizations
        return self
    
    def get_execution_stats(self):
        """Return execution statistics (for optimize mode)"""
        if self._mode == "optimize":
            # Get statistics from Polars execution
            return {
                "operations": len(self._operation_log),
                "optimized_ops": sum(1 for op in self._operation_log if "optimized" in op),
                "python_fallbacks": sum(1 for op in self._operation_log if "fallback" in op),
                # Add more statistics as needed
            }
        return None


class ColumnProxy:
    """Proxy for column operations that captures arithmetic and functions"""
    def __init__(self, name, parent):
        self.name = name
        self._parent = parent
        
    def __add__(self, other):
        return ExpressionProxy(pl.col(self.name) + self._parent._convert_to_expr(other))
    
    def __mul__(self, other):
        return ExpressionProxy(pl.col(self.name) * self._parent._convert_to_expr(other))
    
    # Add other arithmetic operations...
    
    def apply(self, func):
        """Apply a Python function to this column"""
        return ExpressionProxy(pl.col(self.name).map(func))


class ExpressionProxy:
    """Proxy for polars expressions that captures operations"""
    def __init__(self, expr):
        self._expr = expr
        
    def __add__(self, other):
        if hasattr(other, '_expr'):
            return ExpressionProxy(self._expr + other._expr)
        return ExpressionProxy(self._expr + other)
    
    # Add other arithmetic operations...
```

### 6. Plugin Integration

Ensure seamless integration with our existing plugin functions:

```python
from gaspatchio_core.plugin import fill_series, floor, abs_i64

def actuarial_model(df):
    # Regular imports work
    import math
    from scipy import stats
    
    # Constants and Python calculations
    max_age = 100
    z_score = stats.norm.ppf(0.95)
    
    # Pure Python function
    def calculate_risk_factor(age):
        return math.log(max(age, 1)) * 0.01
    
    # Dataframe operations are captured and optimized
    df['num_proj_months'] = (max_age - df['age']) * 12 + 1
    
    # Using custom plugin functions
    df['proj_months'] = fill_series(df['num_proj_months'], 0, 1)
    df['proj_years'] = floor((df['proj_months'] - 1) / 12) + 1
    
    # Numpy operations are translated to Polars
    df['exp_factor'] = np.exp(-0.01 * df['age'])
    
    # Using more plugin functions
    df['abs_age'] = abs_i64(df['age'] - 50)
    
    # Custom functions are vectorized
    df['risk_factor'] = df['age'].apply(calculate_risk_factor)
    
    return df
```

## Performance Optimization Strategies

Based on our research, we'll implement several strategies to maximize performance in optimize mode:

### 1. Batch Operations

Combine related operations into single Polars queries when possible:

```python
# User writes:
df['a'] = df['x'] + 1
df['b'] = df['a'] * 2
df['c'] = df['a'] + df['b']

# In optimize mode, we batch into a single Polars operation:
df._df = df._df.with_columns([
    (pl.col('x') + 1).alias('a'),
    ((pl.col('x') + 1) * 2).alias('b'),
    ((pl.col('x') + 1) + ((pl.col('x') + 1) * 2)).alias('c')
])
```

### 2. Numba JIT Compilation

When a user defines Python functions, we'll use Numba to compile them:

```python
# User writes a Python function
def calculate_mortality(age, duration):
    base_rate = 0.001
    for i in range(duration):
        base_rate *= (1 + 0.03 * age / 100)
    return base_rate

# In debug mode: runs as regular Python
df['mortality'] = df.apply_function(calculate_mortality, 'age', 'policy_duration')

# In optimize mode: compiles with Numba
# Internally, we do something like:
compiled_func = numba.njit(calculate_mortality)
df['mortality'] = df._df.with_column(
    pl.map_multiple([pl.col('age'), pl.col('policy_duration')], compiled_func)
    .alias('mortality')
)
```

### 3. Parallel Execution via Polars

Leverage Polars' parallel execution capabilities:

```python
# Optimize mode automatically uses all available threads
# No changes needed to user code
df = ActuarialFrame(data, mode="optimize")
result = run_model(model_calculation, df).collect()

# Can also specify thread count
df = ActuarialFrame(data, mode="optimize", threads=8)
```

### 4. Operation Fusion

Detect and optimize patterns common in actuarial calculations:

```python
# Special case optimizations for common actuarial patterns
# Example: Recognizing and optimizing projection year calculations
# User writes:
df['proj_year'] = floor((df['proj_month'] - 1) / 12) + 1

# We recognize this pattern and optimize it:
df._df = df._df.with_column(
    ((pl.col('proj_month') - 1) / 12).floor().add(1).alias('proj_year')
)
```

## Testing Requirements

### 1. Unit Tests

- Test capturing of basic operations (arithmetic, assignments)
- Test integration with plugin functions
- Test Python function vectorization
- Test tracing and computation graph building
- Test optimizer and execution
- **Test mode switching** between debug and optimize modes
- **Verify identical results** between modes

### 2. Performance Tests

- Compare execution speed against our existing DSL implementation
- Measure memory usage during execution
- Benchmark performance with various dataset sizes
- Profile bottlenecks, especially in Python UDFs
- **Compare debug vs optimize** mode performance

### 3. Integration Tests

- Test compatibility with existing models
- Verify plugin functions work identically
- Ensure compatibility with our model framework
- **Test third-party library integration**

## Sample Test Script

```python
# model_debuggable.py
import time
import polars as pl
import typer
from gaspatchio_core.dsl.debuggable import ActuarialFrame, run_model, execution_mode
from gaspatchio_core.plugin import fill_series, floor
from gaspatchio_core.utils import read_model_points
from loguru import logger
import numpy as np


def debuggable_model_calculation(df):
    """Define the model calculation using regular Python."""
    # Constants
    max_age = 100

    # Add a breakpoint here to demonstrate debugging
    # import pdb; pdb.set_trace()
    
    # Calculations in simple Python syntax
    df['num_proj_months'] = (max_age - df['age']) * 12 + 1
    df['proj_months'] = fill_series(df['num_proj_months'], 0, 1)
    df['proj_years'] = floor((df['proj_months'] - 1) / 12) + 1

    df['policy_duration'] = df['proj_months'] / 12
    df['policy_duration_start_month'] = floor((df['proj_months'] - 1) / 12, 0)
    df['policy_expiry_month'] = (max_age - df['age']) * 12
    df['age_last'] = df['age'] + df['proj_years'] - 1
    
    # Add print statement to demonstrate debugging
    print(f"First 5 rows of proj_months: {df['proj_months'].collect().head(5)}")
    
    return df


def main(
    size: str = "smol",
    mode: str = "debug"  # Default to debug mode for development
):
    logger.info("Reading model points data...")
    file_path = f"jobs/basic/model-points-{size}.parquet"

    start = time.time()
    logger.info("Starting model run with {} model points in {} mode...", size, mode)
    data = read_model_points(file_path)
    
    # Use our dual-mode approach
    df = ActuarialFrame(data, mode=mode)
    
    # Can also use context manager for temporary mode override
    # with execution_mode("optimize"):
    #     result = run_model(debuggable_model_calculation, df).collect()
    
    result = run_model(debuggable_model_calculation, df).collect()

    end = time.time()
    total_time = end - start
    records = len(result)
    time_per_record_s = total_time / records
    time_per_record_ms = (total_time * 1e3) / records
    time_per_record_ns = (total_time * 1e9) / records
    logger.info(
        "Model run completed in {:.2f} seconds ({:.3f} s | {:.3f} ms | {:.3f} ns per record)",
        total_time,
        time_per_record_s,
        time_per_record_ms,
        time_per_record_ns,
    )

    # If in optimize mode, show performance statistics
    if mode == "optimize" and hasattr(df, "get_execution_stats"):
        stats = df.get_execution_stats()
        if stats:
            logger.info("Execution statistics: {}", stats)

    print(result)


if __name__ == "__main__":
    app = typer.Typer()
    app.command()(main)
    app()
```

## Run-Time Mode Selection

The system will support both debug mode and optimize mode, with clear ways to switch between them:

1. **Environment Variables**: `GASPATCHIO_MODE=debug` or `GASPATCHIO_MODE=optimize`
2. **Configuration Parameters**: Create an ActuarialFrame with explicit mode
3. **Context Managers**: Temporarily change modes for specific blocks of code
4. **Command Line Arguments**: Pass mode as an argument to scripts

Users should be able to:

1. Use debug mode during development and debugging
2. Switch to optimize mode for production runs
3. Verify that both approaches produce identical results

## Performance Expectations

The performance characteristics will vary by mode:

### Debug Mode

- Slower execution, especially for complex calculations
- Higher memory usage due to Python objects
- Less efficient for large datasets
- Excellent for debugging and development
- Quick iteration and immediate feedback

### Optimize Mode

- Near-native performance for optimized operations
- Efficient memory usage leveraging Polars/Rust
- Highly parallel execution
- Slight overhead compared to pure AST approach
- Performance within 80-90% of our current DSL implementation for most workloads

For many common actuarial calculations, the performance gap should remain acceptable, especially during the development and debugging phase.

## LLM Integration Considerations

To support integration with LLM assistants, we will:

1. Use standard Python patterns for maximum compatibility
2. Provide clear error messages that LLMs can interpret
3. Include extensive documentation and examples
4. Support iterative refinement through clear feedback

These enhancements will make the DSL both powerful for expert actuaries and accessible to AI assistants.
