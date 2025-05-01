# ActuarialFrame Accessor Plugins

The `ActuarialFrame` DSL is extensible through custom "accessor" plugins. These allow developers to add domain-specific namespaces (like `.risk`, `.mortality`, `.geo`) to `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy` objects, providing a clean way to organize and reuse custom logic.

There are two ways to register custom accessors:

1.  **Decorator Registration:** For accessors defined within the same project or application.
2.  **Entry Point Discovery:** For accessors distributed as separate installable packages.

## 1. Decorator Registration

You can define an accessor class and register it directly using the `@register_accessor` decorator provided in `gaspatchio_core.dsl.plugins`.

### Defining an Accessor Class

An accessor class should:
*   Accept a single argument in its `__init__` method: the object it's attached to (either an `ActuarialFrame`, `ColumnProxy`, or `ExpressionProxy`).
*   Store this object, typically as `self._obj`, to interact with the underlying data or expression.
*   Define methods that implement the desired logic. These methods can return values, new `ExpressionProxy` objects, or even modified `ActuarialFrame` instances (though modifying the frame directly within an accessor method is less common).

```python
# Example: my_project/accessors.py
import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame, ColumnProxy, ExpressionProxy
from gaspatchio_core.dsl.plugins import register_accessor

class BaseAccessor:
    """Optional base class for convenience."""
    def __init__(self, obj):
        self._obj = obj

@register_accessor("risk", kind="column")
class RiskColumnAccessor(BaseAccessor):
    """Accessor for risk metrics on column/expression proxies."""
    def calculate_var(self, percentile: float) -> ExpressionProxy:
        # Example: Calculate Value at Risk (dummy logic)
        # Assumes self._obj is a ColumnProxy or ExpressionProxy for returns
        if isinstance(self._obj, (ColumnProxy, ExpressionProxy)):
             # Assuming lower tail, calculate quantile
             quantile_expr = self._obj.quantile(1.0 - percentile)
             # VaR is typically positive loss
             return -quantile_expr
        else:
             raise TypeError("Expected ColumnProxy or ExpressionProxy")

    def expected_shortfall(self, percentile: float) -> ExpressionProxy:
         # Dummy implementation
         return self._obj.mean() * (1 + percentile) # Placeholder

@register_accessor("risk", kind="frame")
class RiskFrameAccessor(BaseAccessor):
    """Accessor for frame-level risk analysis."""
    def portfolio_var(self, portfolio_col: str, percentile: float) -> float:
        # Example: Calculate portfolio VaR (dummy logic)
        # Assumes self._obj is an ActuarialFrame
        if isinstance(self._obj, ActuarialFrame):
            # This would involve collecting data, which should be used carefully
            try:
                 df = self._obj.collect() # Collect might be expensive
                 # Use the column accessor logic on the collected series
                 # Note: This mixes frame/column logic, maybe better ways exist
                 return df[portfolio_col].quantile(1.0 - percentile) * -1
            except Exception as e:
                 # Handle cases where column doesn't exist or collect fails
                 print(f"Error calculating portfolio VaR: {e}")
                 return float('nan')
        else:
            raise TypeError("Expected ActuarialFrame")

# IMPORTANT: Ensure this module (my_project/accessors.py) is imported somewhere
# in your application *after* gaspatchio_core.dsl.core is defined,
# usually near your main application entry point or where ActuarialFrame is used.
# e.g., in __init__.py or main.py:
# import my_project.accessors
```

### Decorator Arguments

*   `name` (str): The name used to access the namespace (e.g., `"risk"` results in `.risk`).
*   `kind` (str): Specifies where the accessor should be attached:
    *   `"column"` (default): Attaches to `ColumnProxy` and `ExpressionProxy`.
    *   `"frame"`: Attaches to `ActuarialFrame`.

### Usage

Once the module containing the registered accessor is imported, the accessor becomes available:

```python
import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame
import my_project.accessors # Import the module to trigger registration

data = {"portfolio_returns": [-0.01, 0.02, 0.01, -0.03, 0.005]}
af = ActuarialFrame(data)

# Using the frame accessor
port_var = af.risk.portfolio_var("portfolio_returns", 0.95)
print(f"Portfolio VaR (95%): {port_var:.4f}")

# Using the column/expression accessor
af["col_var"] = af["portfolio_returns"].risk.calculate_var(0.95)
af["expr_es"] = (af["portfolio_returns"] * 100).risk.expected_shortfall(0.95)

result = af.collect()
print(result)
```

## 2. Entry Point Discovery

For accessors intended to be shared and installed as separate packages, use Python's entry point mechanism. This allows `gaspatchio-core` to automatically discover and register accessors from installed packages without requiring explicit imports.

### Defining Entry Points

In the `pyproject.toml` (or `setup.cfg`/`setup.py`) of the package providing the accessor, define an entry point under the group `"gaspatchio.accessors"`.

**Convention:**

*   **Group:** `gaspatchio.accessors`
*   **Name:** `{kind}.{accessor_name}`
    *   `{kind}` must be `frame` or `column`.
    *   `{accessor_name}` is the desired attribute name (e.g., `risk`).
*   **Value:** The full import path to the accessor class (e.g., `my_plugin_package.accessors:RiskColumnAccessor`).

**Example (`pyproject.toml`):**

```toml
[project.entry-points."gaspatchio.accessors"]
# Registers .risk on ColumnProxy/ExpressionProxy
column.risk = "my_plugin_package.accessors:RiskColumnAccessor"
# Registers .reporting on ActuarialFrame
frame.reporting = "my_plugin_package.reporting:ReportingAccessor"
```

### Accessor Class Requirements

The class specified in the entry point value must meet the same requirements as for decorator registration (accept a single object in `__init__`). It should *not* be decorated with `@register_accessor` itself if it's intended only for entry point discovery.

### Automatic Discovery

When the `gaspatchio_core.dsl.plugins` module is first imported (which typically happens when `gaspatchio_core.dsl.core` is imported), it automatically scans for entry points in the `gaspatchio.accessors` group. Found accessors are loaded and registered using the `kind` and `name` derived from the entry point name.

### Usage

If a package containing entry points (like `my-plugin-package` above) is installed in the Python environment, its accessors become available automatically:

```python
# No explicit import of my_plugin_package.accessors needed!
import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame

af = ActuarialFrame({...})

# Accessor from entry point is available
af["risk_metric"] = af["some_col"].risk.calculate_var(0.99)
report_df = af.reporting.generate_summary()
```

This mechanism provides seamless integration for third-party extensions to the `ActuarialFrame` DSL.
