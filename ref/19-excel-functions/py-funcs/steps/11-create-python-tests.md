# Step 11: Create Python Tests

## Input
- Function behavior analysis from Steps 1-2
- Validated examples from Step 10
- Edge cases and error conditions identified

## Task
Create comprehensive Python tests for the Excel function.

### Actions

#### 1. Add to `tests/accessors/test_excel.py`

Basic functionality test:
```python
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
Test implementation summary:

```yaml
function_name: {{FUNCTION_NAME}}
tests_created:
  basic_functionality:
    file: "tests/accessors/test_excel.py"
    test_name: "test_{{function_name}}_basic"
    covers: "Normal use cases"
  edge_cases:
    file: "tests/accessors/test_excel.py"
    test_name: "test_{{function_name}}_edge_cases"
    covers: "Edge cases from behavior analysis"
  null_handling:
    file: "tests/accessors/test_excel.py"
    test_name: "test_{{function_name}}_null_handling"
    covers: "Null propagation"
  docstring_example:
    file: "tests/examples/test_accessors.py"
    test_name: "test_{{function_name}}_example"
    covers: "Docstring example validation"
test_cases_count: 4
coverage_areas:
  - "Basic calculations"
  - "Edge cases"
  - "Null handling"
  - "Documentation examples"
```

## Next Step
This output feeds into Step 12: Run Full Test Suite