# Step 7: Create Python Implementation

## Input
- Function analysis from Steps 1-4
- Rust binding name from Step 5
- Docstring requirements from guidelines

## Task
Create both the Python function implementation and the Excel accessor method. The Python layer is now a simple passthrough - Rust handles all scalar/vector/list logic.

### Pre-requisites
⚠️ **CRITICAL**: Read these files first:
- `ref/12-docstring-and-examples/12-docstring-README.md`
- `ref/19-excel-functions/py-funcs/19-docstring-guidelines.md`

### Part A: Create Function Implementation

Save the function implementation to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/07a-function-implementation.py`

This will eventually be created as `gaspatchio_core/accessors/excel_functions/{{function_name}}.py`:

```python
# File: gaspatchio_core/accessors/excel_functions/{{function_name}}.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)


def {{function_name}}(
    param1: IntoExprColumn,
    param2: IntoExprColumn,
    # Add optional parameters based on kwargs analysis
    optional_param: type = default_value,
) -> pl.Expr:
    """{{Brief description from Step 1 analysis}}.
    
    This function provides Excel {{FUNCTION_NAME}} functionality through a Rust implementation.
    It supports scalar dates, list columns of dates, and broadcasting between scalar
    and list columns (matching Excel 365's dynamic array behavior).
    
    Args:
        param1: {{Description from analysis}} (Date or List[Date])
        param2: {{Description from analysis}} (Date or List[Date])
        optional_param: {{Description from analysis}}
        
    Returns:
        pl.Expr: Expression evaluating to the {{return description}} (Float64)
    """
    param1 = to_polars_expression(param1)
    param2 = to_polars_expression(param2)
    
    # Validate optional parameters if needed
    # Example: validate optional_param is within valid range
    # if optional_param not in valid_range:
    #     raise ValueError(f"Invalid optional_param: {optional_param}")
    
    # Don't cast if already the right type (Date or List[Date])
    # The Rust function handles both scalar and list types
    # Only cast if you need to ensure the type
    # param1_expr = param1.cast(pl.Date, strict=False) if needed
    # param2_expr = param2.cast(pl.Date, strict=False) if needed

    return register_plugin_function(
        args=[param1, param2],
        plugin_path=LIB,
        function_name="{{function_name}}",  # Must match Rust binding name exactly
        is_elementwise=True,
        kwargs={"optional_param": optional_param},
    )
```

### Part B: Add Accessor Method

Save the accessor method to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/07b-accessor-method.py`

This will be added to `ExcelColumnAccessor` class in `gaspatchio_core/accessors/excel.py`:

```python
def {{function_name}}(
    self, 
    param2: "IntoExprColumn", 
    optional_param: OptionalType = default_value
) -> "ExpressionProxy":
    """{{One-line description}} using Excel's {{FUNCTION_NAME}} behavior.
    
    {{Detailed explanation paragraph with actuarial context}}
    
    Supports Excel 365's dynamic array behavior:
    - ✅ scalar, scalar (column to column)
    - ✅ scalar, literal (column to literal value)  
    - ✅ vector, vector (element-wise operations on columns)
    - ✅ scalar broadcasting (column * 2, literal * column)
    - ✅ list column operations (pl.List type) - native Rust support
    - ✅ scalar/list broadcasting (scalar date to list of dates)
    
    !!! note "When to use"
        *   **{{Use Case 1}}**: {{Specific actuarial scenario}}
        *   **{{Use Case 2}}**: {{How this helps with specific calculation}}
        *   **{{Use Case 3}}**: {{Application in projections/valuations}}
        *   **{{Use Case 4}}**: {{Additional actuarial application}}
    
    Parameters
    ----------
    param2 : IntoExprColumn
        {{Description in actuarial terms}}
    optional_param : OptionalType, optional
        {{Description with actuarial meaning}}. Defaults to {{default}}.
        
    Returns
    -------
    ExpressionProxy
        {{What this represents actuarially}}
        
    Raises
    ------
    TypeError
        If the underlying proxy is not a ColumnProxy or ExpressionProxy.
    RuntimeError
        If the operation requires an ActuarialFrame context that is not available.
    ValueError
        If invalid parameters are provided to the Excel function.
    ValueError
        If invalid parameters are provided to the Excel function.
        
    Examples
    --------
    **Scalar Example: {{Single Policy Use Case}}**::

        {{Brief scenario description}}

        ```python
        {{Complete, executable example with imports}}
        ```
        
        ```
        {{EXACT output from execution}}
        ```

    **Vector Example: {{Portfolio Use Case}}**::

        {{Brief portfolio scenario}}

        ```python
        {{Complete, executable example with imports}}
        ```
        
        ```
        {{EXACT output from execution}}
        ```
        
    **List Column Example: {{Projection Use Case}}**::
    
        Excel-like dynamic array behavior with list columns:
        
        ```python
        {{Complete example with list columns}}
        ```
        
        ```
        {{EXACT output from execution}}
        ```
    """
    # Import the function from the excel_functions module
    from .excel_functions.{{function_name}} import {{function_name}}
    
    # Get the start expression from the proxy (self is the first parameter)
    start_expr = self._get_polars_expr()
    parent_frame = self._get_parent_frame()
    
    # No need to check for list columns - Rust handles all type combinations
    # including scalar/scalar, list/list, and scalar/list broadcasting
    
    # Delegate to the function, passing all parameters
    result_expr = {{function_name}}(start_expr, param2, optional_param=optional_param)
    
    # Return wrapped in ExpressionProxy
    from ..column.expression_proxy import ExpressionProxy
    
    return ExpressionProxy(result_expr, parent_frame)
```

## Scalar/Vector/List Handling Guidelines

### Important Terminology
- **Scalar**: Single value (e.g., 42, "hello", date(2024,1,1))
- **Vector**: Regular column with one value per row (standard DataFrame column)
- **List Column**: Column where each cell contains a list of values (pl.List type)
- **Array Column**: Column where each cell contains a fixed-size array (pl.Array type)

Regular column operations are "vectorized" - they operate element-wise on all rows.
This is different from list/array columns where each cell contains multiple values.

### 1. **Type Combination Handling**
Rust core handles scalar/column broadcasting. If list columns are not supported for a given function by the plugin API, document a recommended DataFrame-level pattern (e.g., explode/group_by) here.

### 2. **Current Support Matrix**
Your implementation automatically supports:
- ✅ **scalar, scalar**: Regular column operations (e.g., `col1.yearfrac(col2)`)
- ✅ **scalar, literal**: Column with literal values (e.g., `col.yearfrac(date(2024,1,1))`)
- ✅ **vector operations**: Element-wise operations on regular columns
- ✅ **broadcasting**: Scalar values broadcast across columns automatically
- ✅ **pl.List columns**: Variable-length lists per row - handled by Rust
- ✅ **scalar/list broadcasting**: Excel-like broadcasting behavior

### 3. **No List Detection Needed**
The Python layer no longer needs to detect or handle list columns specially.
The Rust implementation uses the Polars type system to determine the appropriate
processing path.

### 4. **Parameter Validation Order**
1. Convert inputs to expressions using `to_polars_expression`
2. Validate parameter ranges/types if needed
3. Call Rust implementation (it handles all type combinations)
4. Return the result expression

## Architecture Summary

1. **Function Implementation** (`excel_functions/{{function_name}}.py`):
   - Simple passthrough to Rust implementation
   - Handles parameter validation for Python-specific constraints
   - Handles the Rust plugin registration
   - Self-contained module
   - Rust handles all type detection and processing

2. **Accessor Method** (`excel.py`):
   - Thin shim that delegates to the function
   - No list detection needed (Rust handles it)
   - Contains comprehensive documentation
   - Provides the fluent API

## Key Requirements
- Function file handles Python-specific parameter validation
- Rust handles all type detection and list/scalar logic
- Documentation should mention Excel 365 dynamic array support
- Examples must be executable and produce shown output
- Use realistic actuarial data (policies, premiums, dates)
- Include examples with list columns to showcase native support

## Next Step
This output feeds into Step 8: Validate Docstring Examples