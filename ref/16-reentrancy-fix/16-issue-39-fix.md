# Issue #39: load_assumptions Reentrancy Fix

GitHub Issue: https://github.com/gaspatchio/gaspatchio/issues/39

## Problem
The `load_assumptions` function (now replaced by the `Table` API) was not reentrant - it failed when called multiple times within the same Python process. This caused issues in:
- Interactive notebooks (Jupyter, Marimo) where cells are re-executed
- Testing environments where multiple test cases run models
- Development workflows where models are run repeatedly
- Production scenarios with model reloading

## Root Cause
The global assumption table registry in Rust (`register_assumption_table_global`) would return an error if a table with the same name already existed. This prevented re-registration of tables.

## Solution
Added a new idempotent registration function `register_or_replace_assumption_table_global` that:
1. Checks if a table already exists
2. If `force_replace=true`, removes the existing table and registers the new one
3. If `force_replace=false`, silently skips registration if table exists
4. Uses proper locking to ensure thread-safe atomic updates

## Implementation Details

### Rust Core Changes
1. Added `register_or_replace_assumption_table_global` in `core/src/assumptions/registry.rs`
2. Function uses the existing `REGISTRATION_LOCK` mutex for thread safety
3. Performs atomic check-and-replace operation using ArcSwap
4. Added comprehensive tests for idempotent behavior

### Python Binding Changes
1. Exposed the new function in Python bindings via `PyAssumptionTableRegistry.register_or_replace_table`
2. Updated the `Table` class to use `register_or_replace_table` with `force_replace=True`
3. This ensures all table registrations are now idempotent by default

### Testing
Added comprehensive tests in `test_issue_39_reentrancy.py` that verify:
- Tables can be re-registered without errors
- Re-registration properly replaces existing data
- Multiple model runs work correctly
- Registry state remains consistent after multiple registrations

## Usage
No changes required for end users. The `Table` API now automatically handles re-registration:

```python
# This now works without errors when run multiple times
table = Table(
    name="mortality",
    source=data,
    dimensions={"age": "age"},
    value="rate"
)

# Running again with same name is fine
table2 = Table(
    name="mortality",  # Same name - no error!
    source=new_data,
    dimensions={"age": "age"},
    value="rate"
)
```

## Performance Impact
Minimal - the additional check for existing tables is O(1) using HashMap lookup, and only happens during table registration (not during lookups).

## Future Considerations
- Could add an optional `replace` parameter to `Table` constructor for explicit control
- Could add warnings when tables are replaced (currently silent)
- Registry could track replacement history for debugging