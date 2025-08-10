# Step 10: Validate Docstring Examples

## Input
- Excel accessor method with docstring from Step 9
- Function implementation from previous steps

## Task
Create and validate executable docstring examples.

### Actions

#### 1. Create Test File
Create test file at: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/08-test-examples.py`:

```python
# Test file for developing docstring examples
import datetime
from gaspatchio_core import ActuarialFrame

# Scalar example test
def test_scalar_example():
    # Copy exact code from docstring scalar example
    # Run and capture output
    pass

# Vector example test  
def test_vector_example():
    # Copy exact code from docstring vector example
    # Run and capture output
    pass

if __name__ == "__main__":
    test_scalar_example()
    print("="*50)
    test_vector_example()
```

#### 2. Build and Test
```bash
# Rebuild Rust extensions  
maturin build && uv sync

# Test examples work
uv run python test_{{function_name}}_examples.py

# Verify linting
uv run ruff check test_{{function_name}}_examples.py
uv run ruff format test_{{function_name}}_examples.py --check
```

#### 3. Capture Exact Output
Run examples and copy EXACT output to docstring, including:
- Column headers
- Data types
- Formatting
- All rows

#### 4. Test Docstring
```bash
# Test docstring examples execute
uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -k "{{function_name}}" -v

# If output needs updating (after manual verification)
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept
```

## Output
Save validation report to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/08-validation-report.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
test_file_created: true
examples_execute: true/false
linting_passes: true/false
exact_outputs_captured: true/false
doctest_results:
  scalar_example: pass/fail
  vector_example: pass/fail
issues_found:
  - "Issue description if any"
final_status: ready/needs_fixes
```

### Cleanup
```bash
rm test_{{function_name}}_examples.py
```

## Next Step
This output feeds into Step 11: Create Python Tests