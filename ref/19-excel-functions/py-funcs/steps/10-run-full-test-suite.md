# Step 10: Run Full Test Suite


## Input
- All implementation from Steps 1-11
- Tests created in Step 11

## Task
Verify complete integration with no regressions.

### Actions

Run the following test commands in sequence:

```bash
# 0. Rebuild Python bindings in develop mode (fastest during iteration)
uvx maturin develop -m gaspatchio-core/bindings/python/Cargo.toml && uv sync

# 1. Run all tests
uv run pytest

# 2. Run specific function tests (adjust path if tests live per-function)
uv run pytest tests/accessors -k {{function_name}} -v

# 3. CRITICAL: Test docstring examples are valid and executable
uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -v

# 4. Test that type stubs have valid docstring examples
uv run pytest --doctest-modules --doctest-glob="*.pyi" -v

# 5. Run focused docstring test for your function
uv run pytest --doctest-modules -k "{{function_name}}" -v

# 6. Type checking (if enabled)
# uv run mypy gaspatchio_core

# 7. Stub validation
uv run python -m mypy.stubtest gaspatchio_core
```

## Output
Save test results summary to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/10-test-results.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
test_results:
  all_tests:
    command: "uv run pytest"
    status: pass/fail
    failures: []
  function_specific:
    command: "uv run pytest tests/accessors/test_excel.py -k {{function_name}} -v"
    status: pass/fail
    test_count: 4
    failures: []
  docstring_validation:
    command: "uv run pytest --doctest-modules gaspatchio_core/accessors/excel.py -v"
    status: pass/fail
    failures: []
  type_stubs:
    command: "uv run pytest --doctest-modules --doctest-glob='*.pyi' -v"
    status: pass/fail
    failures: []
  stub_validation:
    command: "uv run python -m mypy.stubtest gaspatchio_core"
    status: pass/fail
    issues: []
integration_status: complete/has_issues
issues_to_fix:
  - "Issue 1 description"
  - "Issue 2 description"
```

### Success Criteria
- All tests pass
- No regressions in existing tests
- Docstring examples execute correctly
- Type stubs are valid

## Next Step
This output feeds into Step 11: Update Documentation
