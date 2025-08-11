# Step 9: Create Python Tests


## Input
- Function behavior analysis from Steps 1-2
- Validated examples from Step 8
- Edge cases and error conditions identified

## Task
Create comprehensive Python tests for the Excel function.

### Testing Philosophy
Focus on testing the Python-Rust interface, NOT the Excel calculation logic:
- **Type marshalling**: Ensure dates, strings, integers work correctly
- **Parameter validation**: Test invalid inputs raise appropriate errors
- **Null handling**: Verify null propagation works
- **Integration**: Test with ActuarialFrame
- **List columns**: If not supported by the plugin, ensure docs/tests show the recommended workaround pattern (e.g., explode/group_by) instead of direct list inputs
- **Broadcasting**: Test scalar/column broadcasting works as expected
- **DO NOT** test the actual Excel calculation logic (that's tested in Rust)

### Actions

#### 1. Create Test Implementation

Save test implementation to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/09-test-implementation.py`

This will eventually be created as `tests/accessors/excel_functions/test_{{function_name}}.py`

**Important**: Tests now go in their own file in the `excel_functions` subdirectory to match the source structure.

Basic functionality test:
```python
"""ABOUTME: Tests for {{function_name}} Python-Rust interface - type marshalling and parameter validation.
ABOUTME: Does not test Excel calculation logic which is handled by Rust tests."""

import datetime
from typing import Any

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.accessors.excel_functions.{{function_name}} import {{function_name}}


def test_{{function_name}}_basic():
    """Test basic {{function_name}} functionality."""
    af = ActuarialFrame({
        "param1": [{{test_values}}],
        "param2": [{{test_values}}],
    })
    
    result_af = af.with_columns(
        af["param1"].excel.{{function_name}}(af["param2"]).alias("result")
    )
    result = result_af.collect()["result"]
    
    # Verify results match expected Excel behavior
    expected = [{{expected_values}}]
    for i, expected_val in enumerate(expected):
        if expected_val is None:
            assert result[i] is None
        else:
            assert abs(result[i] - expected_val) < 1e-10


def test_{{function_name}}_with_list_columns():
    """Test {{function_name}} with list columns (Rust handles the logic)."""
    # For date functions, use list of dates
    # For numeric functions, use list of numbers
    af = ActuarialFrame({
        "param1_list": [
            [{{list_values1}}],  # List for row 1
            [{{list_values2}}],  # List for row 2
        ],
        "param2_list": [
            [{{list_values3}}],  # List for row 1
            [{{list_values4}}],  # List for row 2
        ],
    })
    
    # If list columns are not supported directly by the plugin, use explode/group_by pattern
    lf = (
        af.lazy()
        .with_row_index("_idx")
        .explode(["param1_list", "param2_list"])
        .with_columns(
            pl.col("param1_list").excel.{{function_name}}(pl.col("param2_list")).alias("result")
        )
        .group_by("_idx")
        .agg(pl.col("result"))
        .drop("_idx")
    )
    result_af = lf.collect()
    result = result_af["result"]
    assert isinstance(result[0], list)


def test_{{function_name}}_broadcasting():
    """Test {{function_name}} with scalar/list broadcasting."""
    # Test scalar param1 with list param2
    af = ActuarialFrame({
        "scalar_param": {{scalar_value}},  # Will be broadcast to match DataFrame rows
        "list_param": [
            [{{list_values1}}],
            [{{list_values2}}],
        ],
    })
    
    result_af = af.with_columns(
        af["scalar_param"].excel.{{function_name}}(af["list_param"]).alias("result")
    )
    result = result_af.collect()["result"]
    
    # Result should be a list column (scalar broadcast to each element)
    assert isinstance(result[0], list)
    assert len(result[0]) == len(af.collect()["list_param"][0])
```

Edge cases test:

```python
def test_{{function_name}}_edge_cases():
    """Test edge cases and error conditions."""
    # Test various edge cases from behavior analysis
    # - Zero values
    # - Negative values  
    # - Boundary conditions
    # - Date edge cases
    pass
```

Null handling test:

```python
def test_{{function_name}}_null_handling():
    """Test null value propagation."""
    af = ActuarialFrame({
        "param1": [1.0, None, 3.0],
        "param2": [2.0, 4.0, None],
    })
    
    result_af = af.with_columns(
        af["param1"].excel.{{function_name}}(af["param2"]).alias("result")
    )
    result = result_af.collect()["result"]
    
    # When any input is null, output should be null
    assert result[0] is not None  # Both inputs present
    assert result[1] is None      # First input null  
    assert result[2] is None      # Second input null
```

#### 2. Add to `tests/examples/test_accessors.py`

```python
@pytest.mark.example(ns="excel.{{function_name}}")
def test_{{function_name}}_example():
    """Test the docstring example for {{function_name}}."""
    # Copy exact example from docstring
    # Verify it produces expected output
    pass
```

## Output
Save test summary to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/09-test-summary.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
tests_created:
  basic_functionality:
    file: "tests/accessors/excel_functions/test_{{function_name}}.py"
    test_name: "test_{{function_name}}_basic"
    covers: "Normal use cases"
  list_columns:
    file: "tests/accessors/excel_functions/test_{{function_name}}.py"
    test_name: "test_{{function_name}}_with_list_columns"
    covers: "List column support (Rust handles logic)"
  broadcasting:
    file: "tests/accessors/excel_functions/test_{{function_name}}.py"
    test_name: "test_{{function_name}}_broadcasting"
    covers: "Scalar/list broadcasting behavior"
  edge_cases:
    file: "tests/accessors/excel_functions/test_{{function_name}}.py"
    test_name: "test_{{function_name}}_edge_cases"
    covers: "Edge cases from behavior analysis"
  null_handling:
    file: "tests/accessors/excel_functions/test_{{function_name}}.py"
    test_name: "test_{{function_name}}_null_handling"
    covers: "Null propagation"
  docstring_example:
    file: "tests/examples/test_accessors.py"
    test_name: "test_{{function_name}}_example"
    covers: "Docstring example validation"
test_cases_count: 6
coverage_areas:
  - "Basic calculations"
  - "List column operations"
  - "Broadcasting behavior"
  - "Edge cases"
  - "Null handling"
  - "Documentation examples"
```

## Next Step
This output feeds into Step 12: Run Full Test Suite