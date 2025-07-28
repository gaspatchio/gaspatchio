# Step 7: Create Python Function Wrapper

## Input
- Function analysis from Steps 1-4
- Rust binding name from Step 5

## Task
Create the Python wrapper function that calls the Rust binding.

### Actions
1. Create `gaspatchio_core/functions/excel/{{function_name}}.py`
2. Map Python types to Rust kwargs
3. Handle parameter conversion

## Output
The complete Python wrapper file:

```python
# File: gaspatchio_core/functions/excel/{{function_name}}.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)


def {{function_name}}(
    param1: IntoExprColumn,
    param2: IntoExprColumn,
    # Add optional parameters based on kwargs analysis
    optional_param: type = default_value,
) -> pl.Expr:
    """{{Brief description from Step 1 analysis}}.
    
    Args:
        param1: {{Description from analysis}}
        param2: {{Description from analysis}}
        optional_param: {{Description from analysis}}
        
    Returns:
        A Polars expression representing {{return description}}
    """
    param1 = to_polars_expression(param1)
    param2 = to_polars_expression(param2)

    return register_plugin_function(
        args=[param1, param2],
        plugin_path=LIB,
        function_name="{{function_name}}",  # Must match Rust binding name exactly
        is_elementwise=True,
        kwargs={"optional_param": optional_param},
    )
```

### Parameter Mapping Guide
Based on analysis from Step 4:
- Map each Rust kwargs field to a Python parameter
- Use appropriate Python types
- Set correct defaults

## Next Step
This output feeds into Step 8: Update Python Exports