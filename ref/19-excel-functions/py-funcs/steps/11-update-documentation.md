# Step 13: Update Documentation

## Input
- Completed implementation from Steps 1-12
- All tests passing

## Task
Update documentation and type stubs.

### Actions

#### 1. Update Type Stubs
If needed, add type hints to `gaspatchio_core/accessors/excel.pyi`:

```python
def {{function_name}}(
    self,
    param2: IntoExprColumn,
    optional_param: OptionalType = ...,
) -> ExpressionProxy: ...
```

#### 2. Update Function Inventory
Add to any function list documentation:
- Function name
- Category (Financial, Date, Math, etc.)
- Brief description
- Status: Implemented

#### 3. Verify Documentation Quality
Check that docstring includes:
- [ ] Actuarial context and use cases
- [ ] Excel compatibility notes
- [ ] Complete parameter descriptions
- [ ] Executable examples with output
- [ ] "When to use" section with 2-4 cases

## Output
Save documentation updates summary to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/11-documentation-summary.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
documentation_updates:
  type_stubs:
    file: "gaspatchio_core/accessors/excel.pyi"
    added: true/false
    signature_matches: true/false
  function_inventory:
    updated: true/false
    location: "path/to/inventory.md"
  docstring_quality:
    has_actuarial_context: true/false
    has_excel_compatibility: true/false
    has_when_to_use: true/false
    when_to_use_count: 4
    examples_executable: true/false
final_checklist:
  - [x] Implementation complete
  - [x] Tests passing
  - [x] Documentation updated
  - [x] Type stubs accurate
  - [x] Examples validated
  - [x] No regressions
```

## Next Step
Integration complete! The function is ready for use.