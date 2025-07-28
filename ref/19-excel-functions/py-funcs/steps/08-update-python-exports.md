# Step 8: Update Python Module Exports

## Input
- Function name from previous steps
- Python wrapper created in Step 7

## Task
Add the new function to Python module exports in two locations.

### Actions

#### 1. Update `gaspatchio_core/functions/excel/__init__.py`
Add import and update `__all__`:

```python
from .{{function_name}} import {{function_name}}

__all__ = [
    "{{function_name}}",
    # ... existing functions in alphabetical order
]
```

#### 2. Update `gaspatchio_core/functions/__init__.py`
Add to the excel imports and update `__all__`:

```python
from .excel import {{function_name}}

__all__ = [
    "{{function_name}}",
    # ... existing functions in alphabetical order
]
```

## Output
Two sets of changes:

```yaml
excel_init_changes:
  import_line: "from .{{function_name}} import {{function_name}}"
  __all___addition: '"{{function_name}}"'
  
functions_init_changes:
  import_line: "from .excel import {{function_name}}"
  __all___addition: '"{{function_name}}"'
```

### Validation
- [ ] Imports added in both files
- [ ] __all__ lists updated in alphabetical order
- [ ] No duplicate entries

## Next Step
This output completes the base function. Next is Step 9: Create Excel Accessor