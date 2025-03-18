# Core DSL

This module provides the core DSL for Gaspatchio's actuarial modeling. It offers two modes of operation:

1. **Debug Mode**: Prioritizes ease of debugging and traceability, allowing for step-by-step inspection of model execution.
2. **Optimize Mode**: Prioritizes performance by leveraging Polars' lazy evaluation and optimizations.

## Features

- **Dual-mode operation**: Switch between debug and optimize modes without changing your model code.
- **Transparent API**: The API is designed to be similar to the original DSL, making it easy to migrate existing models.
- **Performance optimization**: The optimize mode can provide significant speedups for simple operations.
- **NumPy integration**: Supports NumPy functions and operations.
- **Tracing**: Built-in tracing capabilities to help debug complex models.

## Usage

### Basic Example

```python
import polars as pl
from gaspatchio_core.dsl import ActuarialFrame, run_model

# Create a DataFrame
data = pl.DataFrame({
    "age": [30, 40, 50],
    "premium": [100, 200, 300],
    "sum_assured": [10000, 20000, 30000]
})

# Define a model function
def simple_model(df):
    df["age_squared"] = df["age"] * df["age"]
    df["premium_factor"] = df["premium"] / 100.0
    df["mortality_cost"] = df["sum_assured"] * df["age"] / 1000.0
    return df

# Run in debug mode
df_debug = ActuarialFrame(data, mode="debug")
result_debug = run_model(simple_model, df_debug).collect()

# Run in optimize mode
df_optimize = ActuarialFrame(data, mode="optimize")
result_optimize = run_model(simple_model, df_optimize).collect()
```

### Setting Default Mode

You can set the default mode for all `ActuarialFrame` instances:

```python
from gaspatchio_core.dsl import set_default_mode

# Set default mode to debug
set_default_mode("debug")

# Now all ActuarialFrame instances will use debug mode by default
df = ActuarialFrame(data)  # Uses debug mode
```

### Tracing

The core DSL provides a `trace` function to help debug complex models:

```python
# The trace function is available as a method on ActuarialFrame instances
def complex_calculation(df):
    # Your complex calculation here
    return df

df = ActuarialFrame(data)
traced_function = df.trace(complex_calculation)
```

## Performance Benchmarks

The core DSL has been benchmarked against different types of models:

### Simple Model

A simple model with basic arithmetic operations shows a significant speedup in optimize mode:

- Average debug mode time: 0.0341 seconds
- Average optimize mode time: 0.0010 seconds
- **Speedup: 34.72x**

### Complex Model

A complex model with many operations, including function applications, shows a more modest speedup:

- Average debug mode time: 0.0411 seconds
- Average optimize mode time: 0.0237 seconds
- **Speedup: 1.73x**

The performance difference is less pronounced in complex models due to the overhead of function applications, which currently fall back to Python mode in the optimize mode. Future improvements may include better support for Numba-accelerated functions.

## Limitations

- Function applications in optimize mode may fall back to Python execution, which can limit performance gains for complex models.
- Some operations may behave slightly differently between debug and optimize modes due to differences in how Polars handles certain operations.
- The core DSL may have a small overhead in debug mode.

## Future Improvements

- Better support for Numba-accelerated functions in optimize mode.
- More comprehensive tracing and debugging tools.
- Performance optimizations for complex models. 