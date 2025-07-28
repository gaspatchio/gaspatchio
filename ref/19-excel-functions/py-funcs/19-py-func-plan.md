You are a skilled Python developer tasked with integrating Excel functions from Rust into Python, creating comprehensive tests, and documenting the process.

# Goal
Your goal is to create a complete Python integration for an Excel function that already exists in the Rust core, including proper accessors, comprehensive tests, and documentation.

**Prerequisites:** The Rust function must already be implemented in `gaspatchio_core_lib::excel` with proper kwargs structure.

Here is the name of the Excel function you need to integrate:

<function_name>
{{FUNCTION_NAME}}
</function_name>

# Steps

### Step 1: Break down the Excel documentation into key components:

Look at the Excel documentation for {{FUNCTION_NAME}}:
FUNCTION LIST: https://support.microsoft.com/en-us/office/excel-functions-alphabetical-b3944572-255d-4efb-bb96-c6d90033e188 

SPECIFIC FUNCTION: https://support.microsoft.com/en-us/office/yearfrac-function-3844141e-c76d-4143-82b6-208454ddc6a8


Break down the Excel documentation into key components:
   - Function purpose
   - Parameters
   - Return value
   - Special cases


### Step 2: Analyze the Excel function's behavior in different scenarios:
   - Normal use cases
   - Edge cases
   - Error conditions

**Research Sources (in order of priority):**
1. Microsoft Excel documentation (primary)
2. Excel help forums and StackOverflow for edge cases
3. Financial textbooks for formula verification
4. Other Excel-compatible software documentation
5. Financial calculator manuals for cross-verification

**Search the web** for any information you need to implement the function, especially regarding edge cases and special cases.

In particular in the section we're looking for how the function can be called with scalars and vectors and the combinations. Many paramaters can be called as a scalar AND/OR vectors, the job of the python code is to marshall that data into the right format so the rust bindings (which are always vector / vector) will work. 

### Step 3: Study past learnings

Look at the file "ref/19-excel-functions/py-funcs/19-pylearnings.md" to see if there are any insights or tips for this function.

### Step 4: Analyze the Rust implementation

1. **Locate the Rust function**: Check `gaspatchio_core_lib::excel::function_name` exists
2. **Identify the kwargs structure**: Look for `gaspatchio_core_lib::excel::FunctionNameKwargs` 
3. **Understand the signature**: Note the expected input types and return type
4. **Check existing patterns**: Look at similar functions like `yearfrac.rs` in `src/excel/`

### Step 5: Create the PyO3 Rust binding

Create the Python-Rust bridge in `src/excel/function_name.rs`:

```rust
#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

#[polars_expr(output_type_func = same_output_type)]
pub fn function_name(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::FunctionNameKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::function_name(inputs, &kwargs)
}
```

**Key Points:**
- Function name in Rust binding must match the name used in Python registration
- Import the correct kwargs type from `gaspatchio_core_lib::excel::`
- The binding is just a thin wrapper that calls the core Rust function

### Step 6: Update Rust module exports

Add to `src/excel/mod.rs`:
```rust
pub mod function_name;
```

### Step 7: Create Python function wrapper

Create `gaspatchio_core/functions/excel/function_name.py`:

```python
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


def function_name(
    param1: IntoExprColumn,
    param2: IntoExprColumn,
    optional_param: SomeType = default_value,
) -> pl.Expr:
    """Brief description of the Excel function.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter  
        optional_param: Description of optional parameter
        
    Returns:
        A Polars expression representing the function result
    """
    param1 = to_polars_expression(param1)
    param2 = to_polars_expression(param2)

    return register_plugin_function(
        args=[param1, param2],
        plugin_path=LIB,
        function_name="function_name",  # Must match Rust binding name exactly
        is_elementwise=True,
        kwargs={"optional_param": optional_param},
    )
```

**Critical Naming Rule**: The `function_name` in `register_plugin_function` must match the Rust binding function name exactly.

### Step 8: Update Python module exports

Add to `gaspatchio_core/functions/excel/__init__.py`:
```python
from .function_name import function_name

__all__ = ["function_name", "existing_functions..."]
```

Add to `gaspatchio_core/functions/__init__.py`:
```python
from .excel import function_name

__all__ = [
    "function_name",
    "existing_functions...",
]
```

### Step 9: Create Excel accessor method with comprehensive docstring

⚠️ **CRITICAL**: Read `ref/19-excel-functions/py-funcs/19-docstring-guidelines.md` for complete docstring requirements before writing the accessor method.

Add method to `gaspatchio_core/accessors/excel.py` in the `ExcelColumnAccessor` class:

```python
def function_name(
    self, 
    param2: "IntoExprColumn", 
    optional_param: OptionalType = default_value
) -> "ExpressionProxy":
    """Calculate function using Excel's FUNCTION_NAME behavior.
    
    [Detailed explanation of Excel function in actuarial context, including
    specific calculation method, Excel compatibility notes, and business value]
    
    !!! note "When to use"
        *   **Premium Calculations**: [Specific actuarial use case]
        *   **Reserve Valuations**: [How this helps with reserves]
        *   **Cash Flow Modeling**: [Application in projections]
        *   **[Other Domain Use]**: [Additional actuarial application]
    
    Parameters
    ----------
    param2 : IntoExprColumn
        [Description in actuarial terms - what this represents in insurance context]
    optional_param : OptionalType, optional
        [Description with actuarial meaning]. Defaults to default_value.
        
    Returns
    -------
    ExpressionProxy
        [What this represents actuarially - be specific about calculation result]
        
    Raises
    ------
    TypeError
        If the underlying proxy is not a ColumnProxy or ExpressionProxy.
    RuntimeError
        If the operation requires an ActuarialFrame context that is not available.
    ValueError
        If invalid parameters are provided to the Excel function.
        
    Examples
    --------
    **Scalar Example: [Single Policy Use Case]**::

        [Brief scenario description]

        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame
        
        # [Realistic actuarial data setup]
        af = ActuarialFrame({
            "policy_id": ["POL001"],
            "param1": [realistic_value],
            "param2": [realistic_value],
        })
        
        result = af.with_columns(
            af["param1"].excel.function_name(
                af["param2"], optional_param=value
            ).alias("result")
        )
        print(result.collect())
        ```
        
        ```
        [EXACT output from execution - copy/paste actual results]
        ```

    **Vector Example: [Portfolio Use Case]**::

        [Brief portfolio scenario]

        ```python
        import datetime  
        from gaspatchio_core import ActuarialFrame
        
        # [Realistic portfolio data]
        af = ActuarialFrame({
            "policy_id": ["POL001", "POL002", "POL003"],
            "product_type": ["TERM", "WHOLE", "UL"],
            "param1": [val1, val2, val3],
            "param2": [val1, val2, val3],
        })
        
        result = af.with_columns(
            af["param1"].excel.function_name(af["param2"]).alias("calculated")
        )
        print(result.collect())
        ```
        
        ```
        [EXACT output from execution - copy/paste actual results]
        ```
    """
    parent_frame = self._get_parent_frame()
    start_expr = self._get_polars_expr()
    param2_expr = parent_frame._convert_to_expr(param2)
    
    # Add any parameter validation or conversion logic
    
    # Import the function from the functions module
    from ..functions.excel import function_name
    
    # Call the Rust implementation via the plugin
    result_expr = function_name(start_expr, param2_expr, optional_param=optional_param)
    
    from ..column.expression_proxy import ExpressionProxy
    
    return ExpressionProxy(result_expr, parent_frame)
```

### Step 10: Create and validate docstring examples

**CRITICAL**: All docstring examples MUST be executable and produce exact output shown. This step ensures your documentation is accurate and tested.

#### 10.1: Write docstring examples locally

Create a temporary test file to develop your examples:

```bash
# Create a test file for developing examples
cat > test_function_examples.py << 'EOF'
# Test file for developing docstring examples
import datetime
from gaspatchio_core import ActuarialFrame

# Scalar example test
def test_scalar_example():
    af = ActuarialFrame({
        "policy_id": ["POL001"],
        "param1": [realistic_value],  # Replace with actual values
        "param2": [realistic_value],  # Replace with actual values
    })
    
    result = af.with_columns(
        af["param1"].excel.function_name(
            af["param2"], optional_param=value
        ).alias("result")
    )
    print("Scalar example output:")
    print(result.collect())

# Vector example test  
def test_vector_example():
    af = ActuarialFrame({
        "policy_id": ["POL001", "POL002", "POL003"],
        "product_type": ["TERM", "WHOLE", "UL"],
        "param1": [val1, val2, val3],  # Replace with actual values
        "param2": [val1, val2, val3],  # Replace with actual values
    })
    
    result = af.with_columns(
        af["param1"].excel.function_name(af["param2"]).alias("calculated")
    )
    print("Vector example output:")
    print(result.collect())

if __name__ == "__main__":
    test_scalar_example()
    test_vector_example()
EOF
```

#### 10.2: Build and test the integration

```bash
# Rebuild Rust extensions  
maturin build && uv sync

# Test that basic integration works
uv run python -c "
from gaspatchio_core import ActuarialFrame
import datetime

# Quick smoke test of the function
af = ActuarialFrame({'col1': [1, 2], 'col2': [3, 4]})
result = af.with_columns(af['col1'].excel.function_name(af['col2']).alias('result'))
print('Smoke test passed:', result.collect())
"
```

#### 10.3: Execute and capture example outputs

```bash
# Run your examples and capture exact output
uv run python test_function_examples.py

# Verify linting passes
uv run ruff check test_function_examples.py
uv run ruff format test_function_examples.py --check
```

#### 10.4: Test docstring examples with pytest

```bash
# Test that docstring examples are valid Python and execute correctly
# This validates the syntax and imports in your docstring examples
uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -v

# Test type stubs contain valid docstring examples  
uv run pytest --doctest-modules --doctest-glob="*.pyi" -v

# If you get failures, use --accept to update expected outputs
# (ONLY do this after manually verifying the output is correct)
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept

# Run specific docstring tests for your function
uv run pytest --doctest-modules -k "function_name" -v
```

#### 10.5: Validate docstring structure

Check that your docstring follows the required structure:

```bash
# Validate docstring can be parsed by the documentation system
uv run python -c "
import gaspatchio_core.accessors.excel
import inspect

# Get your function's docstring
func = getattr(gaspatchio_core.accessors.excel.ExcelColumnAccessor, 'function_name')
docstring = inspect.getdoc(func)

print('Docstring length:', len(docstring))
print('Has Examples section:', 'Examples' in docstring)
print('Has When to use section:', 'When to use' in docstring)
print('Has Parameters section:', 'Parameters' in docstring)
print('Has Returns section:', 'Returns' in docstring)

# Check for required actuarial terms
actuarial_terms = ['policy', 'premium', 'reserve', 'actuarial', 'insurance']
found_terms = [term for term in actuarial_terms if term.lower() in docstring.lower()]
print('Actuarial terms found:', found_terms)
"
```

#### 10.6: Final docstring checklist

Before proceeding, verify:

- [ ] **Executable examples**: Both scalar and vector examples run without errors
- [ ] **Exact output**: Output blocks show exactly what the code produces  
- [ ] **Ruff compliance**: All example code passes `ruff check` and `ruff format --check`
- [ ] **Actuarial context**: Examples use realistic life insurance data and terminology
- [ ] **Complete imports**: All necessary imports are included in examples
- [ ] **"When to use" section**: Contains 2-4 specific actuarial use cases
- [ ] **Excel compatibility**: Mentions that function follows Excel's behavior
- [ ] **Domain specificity**: Examples focus on actuarial modeling scenarios

```bash
# Clean up test file
rm test_function_examples.py
```

### Step 11: Create comprehensive Python tests

Create test files in `tests/accessors/`:

**Basic functionality tests** (`test_excel.py` additions):
```python
def test_function_name_basic():
    """Test basic function_name functionality."""
    af = ActuarialFrame({
        "param1": [test_values],
        "param2": [test_values],
    })
    
    result_af = af.with_columns(
        af["param1"].excel.function_name(af["param2"]).alias("result")
    )
    result = result_af.collect()["result"]
    
    # Verify results match expected Excel behavior
    expected = [expected_values]
    for i, expected_val in enumerate(expected):
        if expected_val is None:
            assert result[i] is None
        else:
            assert abs(result[i] - expected_val) < 1e-10

def test_function_name_edge_cases():
    """Test edge cases and error conditions."""
    # Test various edge cases that Excel handles specially
    pass

def test_function_name_null_handling():
    """Test null value propagation."""
    af = ActuarialFrame({
        "param1": [1.0, None, 3.0],
        "param2": [2.0, 4.0, None],
    })
    
    result_af = af.with_columns(
        af["param1"].excel.function_name(af["param2"]).alias("result")
    )
    result = result_af.collect()["result"]
    
    # When any input is null, output should be null
    assert result[0] is not None  # Both inputs present
    assert result[1] is None      # First input null  
    assert result[2] is None      # Second input null
```

**Docstring example tests** (`tests/examples/test_accessors.py` additions):
```python
@pytest.mark.example(ns="excel.function_name")
def test_function_name_example():
    """Test the docstring example for function_name."""
    # Copy the exact example from the docstring and verify it works
    pass
```

### Step 12: Verify complete integration

Run the full test suite to ensure no regressions:

```bash
# Run all tests
uv run pytest

# Run specific function tests
uv run pytest tests/accessors/test_excel.py -k function_name -v

# CRITICAL: Test docstring examples are valid and executable
uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -v

# Test that type stubs have valid docstring examples
uv run pytest --doctest-modules --doctest-glob="*.pyi" -v

# Run focused docstring test for your function
uv run pytest --doctest-modules -k "function_name" -v

# Type checking
#uv run mypy gaspatchio_core

# Stub validation
uv run python -m mypy.stubtest gaspatchio_core
```

### Step 13: Update documentation

1. **Type stubs**: If needed, add type hints to `gaspatchio_core/accessors/excel.pyi`
2. **Function list**: Update any function inventory documentation
3. **Examples**: Ensure docstring examples are comprehensive and tested

## Docstring Requirements and Testing

### Essential Reading
Before implementing any Excel function, you MUST read:
- `ref/12-docstring-and-examples/12-docstring-README.md` - Complete docstring standards
- `ref/19-excel-functions/py-funcs/19-docstring-guidelines.md` - Excel function specific guidelines

### Key Docstring Testing Commands

**Development workflow:**
```bash
# 1. Test your examples as you develop them
uv run python test_function_examples.py

# 2. Validate linting compliance
uv run ruff check test_function_examples.py
uv run ruff format test_function_examples.py --check

# 3. Test docstring examples execute correctly
uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -v

# 4. Test type stub docstrings
uv run pytest --doctest-modules --doctest-glob="*.pyi" -v

# 5. Update expected outputs if code is correct (use carefully)
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept
```

**Quality gates:**
- All docstring code examples MUST execute without errors
- All docstring code MUST pass ruff linting 
- Examples MUST use realistic actuarial data and terminology
- Output blocks MUST show exact results (copy/paste from execution)
- "When to use" section MUST contain 2-4 actuarial use cases

## Common Integration Patterns

### Parameter Mapping
- **Column/Expression (self)**: First parameter becomes the column the accessor is called on
- **Second+ parameters**: Passed as arguments to the accessor method
- **Optional parameters**: Handled via kwargs in both Rust and Python

### Error Handling
- **Python validation**: Handle type checking and basic validation in Python accessor
- **Rust errors**: Let Rust core handle mathematical/logical errors  
- **Null propagation**: Rust handles null values automatically

### Naming Consistency
- **Rust binding function name** = **Python register_plugin_function name**
- **Python function name** = **Python accessor method name** 
- Use consistent snake_case throughout Python, matching Excel function names

### Testing Strategy
1. **Unit tests**: Test accessor functionality and edge cases
2. **Integration tests**: Test with real data scenarios  
3. **Docstring tests**: Validate examples work as documented
4. **Excel compatibility**: Verify results match Excel behavior

## Troubleshooting Common Issues

### Symbol Not Found Errors
- Check that Rust binding function name matches Python registration
- Ensure `maturin build && uv sync` was run after Rust changes
- Verify the function is exported in `src/excel/mod.rs`

### Type Errors
- Ensure proper type conversion in Python wrapper
- Check that kwargs structure matches between Rust and Python
- Verify `to_polars_expression()` usage for input parameters

### Test Failures  
- Check that expected values match actual Excel behavior
- Consider floating-point precision in comparisons
- Verify null handling follows expected patterns

### Docstring and Example Issues
- **Doctest failures**: Ensure output blocks match EXACTLY what your code produces
- **Import errors in examples**: Test imports in isolation, ensure all required modules are imported
- **Ruff linting failures**: Run `ruff check` and `ruff format` on example code 
- **Execution errors**: Create temporary test files to debug example code before putting in docstrings
- **Output formatting mismatches**: Copy/paste actual Polars output, don't manually format
- **Missing actuarial context**: Examples must use realistic insurance data and terminology
- **Insufficient "When to use" cases**: Need 2-4 specific actuarial scenarios, not generic descriptions

### Common Docstring Error Messages and Solutions

**"Doctest failed"**:
```bash
# Debug by extracting and running the example separately
uv run python -c "
# Copy the exact code from your docstring example here
"
```

**"Expected output doesn't match actual"**:
```bash
# Re-run your example and copy/paste the EXACT output 
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept
```

**"Import errors in docstring examples"**:
- Verify all imports are included in the example
- Test imports work in isolation
- Ensure proper import order (stdlib, third-party, local)
