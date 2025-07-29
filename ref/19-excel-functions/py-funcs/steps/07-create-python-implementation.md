# Step 7: Create Python Implementation

## Input
- Function analysis from Steps 1-4
- Rust binding name from Step 5
- Docstring requirements from guidelines

## Task
Create both the Python function implementation and the Excel accessor method with proper scalar/vector/list handling.

### Pre-requisites
⚠️ **CRITICAL**: Read these files first:
- `ref/12-docstring-and-examples/12-docstring-README.md`
- `ref/19-excel-functions/py-funcs/19-docstring-guidelines.md`

### Part A: Create Function Implementation

Create `gaspatchio_core/accessors/excel_functions/{{function_name}}.py`:

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
    
    This is the low-level function that provides Excel {{FUNCTION_NAME}} functionality.
    It handles all business logic including parameter validation and type conversion,
    then calls the Rust implementation.
    
    Note: List columns are not yet supported. Excel 365 supports dynamic arrays
    with functions like {{FUNCTION_NAME}}, but Polars plugin functions have limitations
    with list operations. Use explode/group_by patterns as a workaround.
    
    Args:
        param1: {{Description from analysis}}
        param2: {{Description from analysis}}
        optional_param: {{Description from analysis}}
        
    Returns:
        A Polars expression representing {{return description}}
    """
    # Business logic: parameter validation and type conversion
    # Example: validate optional_param is within valid range
    # if optional_param not in valid_range:
    #     raise ValueError(f"Invalid optional_param: {optional_param}")
    
    param1 = to_polars_expression(param1)
    param2 = to_polars_expression(param2)
    
    # Cast to appropriate types for Rust function
    # Example for date functions:
    # param1 = param1.cast(pl.Date, strict=False)
    # param2 = param2.cast(pl.Date, strict=False)

    return register_plugin_function(
        args=[param1, param2],
        plugin_path=LIB,
        function_name="{{function_name}}",  # Must match Rust binding name exactly
        is_elementwise=True,
        kwargs={"optional_param": optional_param},
    )
```

### Part B: Add Accessor Method

Add to `ExcelColumnAccessor` class in `gaspatchio_core/accessors/excel.py`:

```python
def {{function_name}}(
    self, 
    param2: "IntoExprColumn", 
    optional_param: OptionalType = default_value
) -> "ExpressionProxy":
    """{{One-line description}} using Excel's {{FUNCTION_NAME}} behavior.
    
    {{Detailed explanation paragraph with actuarial context}}
    
    Supports Excel 365's dynamic array behavior with some limitations:
    - ✅ scalar, scalar (column to column)
    - ✅ scalar, literal (column to literal value)  
    - ✅ vector, vector (element-wise operations on columns)
    - ✅ scalar broadcasting (column * 2, literal * column)
    - ❌ list column operations (pl.List type) - use explode() workaround
    - ❌ array column operations (pl.Array type) - limited support
    
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
    NotImplementedError
        If list columns are provided. Excel 365 supports this via dynamic
        arrays, but the Polars implementation requires explode/group_by patterns.
        
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
        
    **List Column Workaround**::
    
        For Excel-like dynamic array behavior with list columns:
        
        ```python
        # Instead of: af["list_col"].excel.{{function_name}}(param2)
        # Use explode/group_by pattern:
        result = (
            af.explode("list_col")
            .with_columns(
                result=pl.col("list_col").excel.{{function_name}}(param2)
            )
            .group_by("id")
            .agg(pl.col("result"))
        )
        ```
    """
    # Import the function from the excel_functions module
    from .excel_functions.{{function_name}} import {{function_name}}
    
    # Get the start expression from the proxy (self is the first parameter)
    start_expr = self._get_polars_expr()
    
    # Check for list columns if relevant for this function
    # NOTE: Only add this check if the function could reasonably receive list inputs
    parent_frame = self._get_parent_frame()
    schema = parent_frame._df.collect_schema()
    
    # Check if self is a list column
    start_is_list = False
    if hasattr(self._proxy, "name") and self._proxy.name in schema:
        col_dtype = schema[self._proxy.name]
        if isinstance(col_dtype, pl.List):
            start_is_list = True
    
    # Check if param2 is a list column
    param2_expr = parent_frame._convert_to_expr(param2)
    param2_is_list = False
    if param2_expr.meta.is_column():
        param2_col_name = param2_expr.meta.output_name()
        if param2_col_name in schema:
            col_dtype = schema[param2_col_name]
            if isinstance(col_dtype, pl.List):
                param2_is_list = True
    
    # Raise helpful error for list columns
    if start_is_list or param2_is_list:
        raise NotImplementedError(
            f"{{function_name}} with list columns is not yet supported. "
            f"Excel 365 supports this via dynamic arrays (requires + operator: "
            f"={{FUNCTION_NAME}}(+A1:A5, +B1:B5)), but the Polars implementation "
            f"requires explode/group_by patterns. "
            f"As a workaround, use explode() to flatten the list, calculate {{function_name}}, "
            f"then group_by().agg() to re-create the list structure."
        )
    
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

### 1. **Understand Excel 365 Behavior**
- Excel 365 supports dynamic arrays that "spill" results
- Some functions like YEARFRAC are "spill-resistant" and need the `+` operator
- Example: `=YEARFRAC(+A1:A5, +B1:B5)` works with arrays

### 2. **Current Support Matrix**
Your implementation should support:
- ✅ **scalar, scalar**: Regular column operations (e.g., `col1.yearfrac(col2)`)
- ✅ **scalar, literal**: Column with literal values (e.g., `col.yearfrac(date(2024,1,1))`)
- ✅ **vector operations**: Element-wise operations on regular columns
- ✅ **broadcasting**: Scalar values broadcast across columns automatically
- ❌ **pl.List columns**: Variable-length lists per row - defer to explode() workaround
- ❌ **pl.Array columns**: Fixed-size arrays per row - limited Polars support

### 3. **List Detection Pattern**
Only include list detection if the function could reasonably receive list inputs:
```python
# Check schema for list columns
schema = parent_frame._df.collect_schema()
if isinstance(schema[col_name], pl.List):
    # Handle list column case
```

### 4. **Error Message Template**
For unsupported list operations:
```python
raise NotImplementedError(
    f"{{function_name}} with list columns is not yet supported. "
    f"Excel 365 supports this via dynamic arrays (requires + operator: "
    f"={{FUNCTION_NAME}}(+A1:A5, +B1:B5)), but the Polars implementation "
    f"requires explode/group_by patterns. "
    f"As a workaround, use explode() to flatten the list, calculate {{function_name}}, "
    f"then group_by().agg() to re-create the list structure."
)
```

### 5. **When to Skip List Checks**
Skip list detection for functions that:
- Only work with scalar values by definition
- Have no meaningful list interpretation
- Are purely element-wise with no aggregation

### 6. **Parameter Validation Order**
1. Convert inputs to expressions
2. Validate parameter ranges/types
3. Check for list columns (if applicable)
4. Cast to required types
5. Call Rust implementation

## Architecture Summary

1. **Function Implementation** (`excel_functions/{{function_name}}.py`):
   - Contains ALL business logic (validation, type conversion)
   - Handles the Rust plugin registration
   - Self-contained module
   - Does NOT handle list detection (leave to accessor)

2. **Accessor Method** (`excel.py`):
   - Thin shim that delegates to the function
   - Contains list detection logic (when applicable)
   - Provides helpful error messages
   - Contains comprehensive documentation
   - Provides the fluent API

## Key Requirements
- Function file must handle all parameter validation
- Accessor method handles list detection when relevant
- Error messages must mention Excel 365 dynamic arrays
- Provide explode/group_by workaround in error messages
- Examples must be executable and produce shown output
- Use realistic actuarial data (policies, premiums, dates)

## Next Step
This output feeds into Step 8: Validate Docstring Examples