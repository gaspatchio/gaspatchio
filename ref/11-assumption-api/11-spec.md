# Gaspatchio-Core Assumption API Implementation Specification

**Implementation Blueprint for Assumption Loading & Lookup Revamp**  
**Based on:** [11-plan.md](./11-plan.md)  
**Target Files:** 
- `bindings/python/gaspatchio_core/assumptions/_loader.py`
- `bindings/python/tests/assumptions/test_curve.py`

---

## Overview

This specification breaks down the implementation of the new assumption loading API into small, iterative steps. Each step builds on the previous one, using test-driven development to ensure robust, incremental progress.

**Key Design Principles:**
- Start with simplest case (curves) and build complexity gradually
- Each step must have comprehensive tests before moving forward
- No orphaned code - everything gets integrated
- Maintain backward compatibility throughout

---

## Implementation Steps

### Step 1: Package Structure & Basic Infrastructure

**Objective:** Set up the foundational package structure and create the skeleton for curve loading.

**Files to Create:**
- `bindings/python/gaspatchio_core/assumptions/__init__.py`
- `bindings/python/gaspatchio_core/assumptions/_loader.py` 
- `bindings/python/tests/assumptions/test_curve.py`

**Prompt 1:**

```
Create the basic package structure for the new assumptions loading API. 

Create these files:

1. `bindings/python/gaspatchio_core/assumptions/__init__.py` - Package init that will eventually re-export load_assumptions and assumption_lookup

2. `bindings/python/gaspatchio_core/assumptions/_loader.py` - Main loader module with:
   - Stub `load_assumptions()` function that accepts (name, source, *, id=None, value="rate", overflow="auto", max_overflow=200, metadata=None)
   - For now, just validate parameters and raise NotImplementedError with a clear message
   - Include comprehensive docstring with examples from the plan
   - Add proper type hints using polars types

3. `bindings/python/tests/assumptions/test_curve.py` - Test file with:
   - Basic test infrastructure setup
   - One failing test `test_load_curve_basic()` that tries to load a simple 2-column CSV curve
   - Test should create a minimal polars DataFrame and call load_assumptions()
   - Test should expect the function to work (it will fail initially)

Use polars for all DataFrame operations. Follow the project's python coding standards with type hints, proper imports, and clear error messages.

Make sure all imports are correctly structured and the package can be imported without errors.
```

---

### Step 2: Core Data Materialization

**Objective:** Implement the foundation for loading data from files or DataFrames.

**Prompt 2:**

```
Implement the core data materialization logic in `_loader.py`. 

Add these helper functions:

1. `_materialise(source: str | pl.DataFrame) -> pl.DataFrame`:
   - If source is string, detect file type (.csv/.parquet) and read with polars
   - If source is DataFrame, return as-is
   - Use polars best practices (infer_schema_length=10000 for CSV)
   - Handle file not found and invalid format errors with clear messages

2. `_analyse_shape(df: pl.DataFrame, id: str | list[str] | None) -> tuple[list[str], list[str]]`:
   - Return (id_columns, numeric_columns)
   - If id is None, auto-detect first non-numeric column(s) as id
   - If id is string, split on comma/whitespace into list
   - Validate that id columns exist in DataFrame
   - Return numeric columns as potential value columns

3. Update `load_assumptions()` to use these helpers:
   - Call _materialise() first
   - Call _analyse_shape() second  
   - For now, still raise NotImplementedError but with more specific message about what was detected

Update the test in `test_curve.py`:
- Create a test DataFrame with Age (int) and qx (float) columns
- Test that _materialise() works with DataFrames
- Test that _analyse_shape() correctly identifies Age as id and qx as numeric
- Test error cases (missing file, invalid id column)

Make sure all functions have comprehensive type hints and handle edge cases gracefully.
```

---

### Step 3: Basic Curve Loading Implementation

**Objective:** Complete the curve loading functionality for the simplest case (no overflow handling).

**Prompt 3:**

```
Complete the curve loading implementation in `_loader.py`.

Add these functions:

1. `_tidy_curve(df: pl.DataFrame, id_cols: list[str], value: str) -> pl.DataFrame`:
   - Validate that there's exactly one numeric column remaining after removing id columns
   - Rename the numeric column to the specified `value` parameter name
   - Return the DataFrame with id columns + renamed value column
   - Raise clear errors if multiple numeric columns found (should be wide table) or no numeric columns

2. Update `load_assumptions()` to handle curves:
   - After _analyse_shape(), detect if it's a curve (only one numeric column)
   - If curve, call _tidy_curve() and return the result
   - If wide table, raise NotImplementedError("Wide tables not yet supported")
   - Import and use the existing TableRegistry from gaspatchio_core.registry
   - Call registry.register_table() with the tidy DataFrame
   - Return the tidy DataFrame for inspection

3. Update `bindings/python/gaspatchio_core/assumptions/__init__.py`:
   - Import and re-export load_assumptions from ._loader
   - Import assumption_lookup from ..assumptions (existing module)
   - Re-export assumption_lookup

Complete the test in `test_curve.py`:
- Test successful curve loading with Age -> qx mapping
- Test the returned DataFrame has correct shape and column names
- Test that assumption_lookup works after loading (integration test)
- Test error cases: multiple numeric columns, no numeric columns
- Test with both DataFrame input and mock CSV file path

Ensure the curve workflow is fully functional before proceeding to wide tables.
```

---

### Step 4: Wide Table Detection & Basic Melting

**Objective:** Add support for wide tables without overflow handling.

**Files to Create:**
- `bindings/python/tests/assumptions/test_wide_basic.py`

**Prompt 4:**

```
Add support for wide tables (age × duration grids) without overflow logic.

Update `_loader.py`:

1. Enhance `_analyse_shape()` to detect wide vs curve tables:
   - If more than one numeric column found, it's a wide table
   - Return the numeric column names as wide_cols
   - Update return type to `tuple[list[str], list[str], bool]` where bool indicates is_wide

2. Add `_tidy_wide_basic(df: pl.DataFrame, id_cols: list[str], wide_cols: list[str], value: str) -> pl.DataFrame`:
   - Use polars melt() to convert wide to long format
   - id_vars = id_cols, value_vars = wide_cols
   - variable_name = "variable", value_name = value parameter
   - Convert variable column to string type
   - Return tidy DataFrame with id_cols + ["variable"] + [value]

3. Update `load_assumptions()`:
   - Handle both curve and wide table cases
   - For wide tables, call _tidy_wide_basic()
   - Pass correct keys to registry.register_table(): id_cols + ["variable"] for wide tables

Create `bindings/python/tests/assumptions/test_wide_basic.py`:
- Test loading a wide mortality table (Age × Duration 1,2,3,4,5)
- Verify the melted output has correct structure
- Test that lookups work correctly: assumption_lookup("table", age=30, variable="3")
- Test with different id column names and value column names
- Test error cases

Update existing tests to handle the changed return type from _analyse_shape().

Focus on getting basic wide table functionality working reliably before adding overflow complexity.
```

---

### Step 5: Overflow Detection Logic

**Objective:** Add the ability to detect and handle overflow columns in wide tables.

**Prompt 5:**

```
Implement overflow column detection for wide tables.

Update `_loader.py`:

1. Add `_detect_overflow_column(wide_cols: list[str], overflow: str | None) -> str | None`:
   - If overflow is None, return None (no overflow handling)
   - If overflow is "auto", detect non-numeric columns in wide_cols
   - Common patterns: "Ult.", "Ultimate", "Term", "999", "", etc.
   - If overflow is a string, verify it exists in wide_cols
   - Return the overflow column name or None
   - Raise clear errors if explicit overflow column not found

2. Add `_get_max_numeric_duration(wide_cols: list[str], exclude_overflow: str | None = None) -> int | None`:
   - Find the maximum integer value among wide_cols (excluding overflow column)
   - Return None if no numeric columns found
   - Handle mixed formats gracefully

3. Update `_analyse_shape()` to separate numeric and non-numeric wide columns:
   - Return tuple: (id_cols, numeric_wide_cols, text_wide_cols, is_wide)
   - This helps distinguish duration columns from overflow columns

Update `test_wide_basic.py`:
- Add test cases with overflow columns: Age, 1, 2, 3, Ult.
- Test overflow="auto" detection
- Test overflow="Ult." explicit specification  
- Test overflow=None (no overflow handling)
- Test error cases: invalid overflow column name

The goal is to reliably detect overflow columns before implementing the expansion logic in the next step.
```

---

### Step 6: Overflow Expansion Implementation

**Objective:** Implement the pre-computation of overflow entries for maximum lookup performance.

**Files to Create:**
- `bindings/python/tests/assumptions/test_overflow.py`

**Prompt 6:**

```
Implement overflow expansion logic to pre-compute all overflow entries at registration time.

Update `_loader.py`:

1. Add `_create_overflow_expansion(df: pl.DataFrame, id_cols: list[str], overflow_col: str, value: str, start_value: int, max_value: int) -> pl.DataFrame`:
   - Create new rows for each id combination 
   - For each row in original df, create copies with variable = start_value, start_value+1, ..., max_value
   - All these rows get the same rate value as the overflow_col
   - Return DataFrame with same schema as melted wide table

2. Replace `_tidy_wide_basic()` with `_tidy_wide_with_overflow_expansion()`:
   - Handle overflow logic: detect overflow column, find max numeric duration
   - Melt the wide table as before  
   - If overflow detected, call _create_overflow_expansion() and concat the results
   - Return the complete expanded table

3. Update `load_assumptions()` to use the new function:
   - Pass the overflow and max_overflow parameters through
   - No changes needed to the registry calls

Create `bindings/python/tests/assumptions/test_overflow.py`:
- Test overflow expansion with Age × [1,2,3,Ult.] → expanded to [1,2,3,4,5,...,200]
- Verify lookup performance: assumption_lookup("table", age=30, variable="150") works instantly
- Test different overflow column names and max_overflow values
- Test memory usage is reasonable (warn if expansion is very large)
- Performance test: time the lookup operations vs theoretical maximum

The expansion happens once at load time, giving us O(1) lookups forever after.
```

---

### Step 7: API Integration & Top-Level Exports

**Objective:** Wire everything into the public API and ensure seamless integration.

**Prompt 7:**

```
Complete the public API integration and update all top-level exports.

Update these files:

1. `bindings/python/gaspatchio_core/__init__.py`:
   - Add import: `from .assumptions import load_assumptions, assumption_lookup`
   - Ensure these are included in __all__ if it exists
   - Verify no breaking changes to existing exports

2. `bindings/python/gaspatchio_core/assumptions/__init__.py`:
   - Import `load_assumptions` from `._loader`
   - Import `assumption_lookup` from `..assumptions` (existing module)
   - Re-export both functions
   - Add __all__ = ["load_assumptions", "assumption_lookup"]

3. Update `_loader.py`:
   - Add comprehensive docstring examples to load_assumptions()
   - Include examples for both curve and wide table usage
   - Add doctest examples that can be run with pytest --doctest-modules

Create `bindings/python/tests/assumptions/test_integration.py`:
- Test importing from top level: `import gaspatchio_core as gs`
- Test the complete workflow: `gs.load_assumptions()` → `gs.assumption_lookup()`
- Test both curve and wide table scenarios end-to-end
- Test that existing TableRegistry workflows still work (backward compatibility)
- Test with realistic data sizes and formats

Verify that the public API matches exactly what's described in the plan:
- gs.load_assumptions() with all parameters
- gs.assumption_lookup() unchanged from before
- No breaking changes to existing functionality
```

---

### Step 8: Advanced Features & Parameter Support

**Objective:** Add support for value_vars (selective melting) and comprehensive validation.

**Prompt 8:**

```
Add advanced features and comprehensive parameter validation.

Update `_loader.py`:

1. Add support for `value_vars` parameter in `_tidy_wide_with_overflow_expansion()`:
   - If value_vars is provided, use those columns instead of auto-detected wide_cols
   - Validate that all value_vars exist in the DataFrame
   - Allow selective melting of only certain duration columns
   - Update overflow detection to work with the subset

2. Add comprehensive parameter validation to `load_assumptions()`:
   - Validate name is non-empty string and doesn't conflict with existing tables
   - Validate source is valid path or DataFrame
   - Validate value column name is valid identifier
   - Validate max_overflow is reasonable (1-1000)
   - Provide helpful error messages for common mistakes

3. Add `metadata` parameter support:
   - Store metadata in a way that can be retrieved later
   - May require extending TableRegistry or storing separately
   - Document the intended use cases

Create `bindings/python/tests/assumptions/test_advanced.py`:
- Test value_vars with selective column melting
- Test metadata storage and retrieval
- Test parameter validation with various invalid inputs
- Test edge cases: empty DataFrames, single-row tables, Unicode column names
- Test performance with large tables (1M+ rows)

Create `bindings/python/tests/assumptions/test_duplicates.py`:
- Test duplicate table name handling
- Test overwriting existing tables
- Test concurrent loading scenarios if relevant

Ensure all edge cases are handled gracefully with clear error messages.
```

---

### Step 9: Legacy Compatibility & Error Handling

**Objective:** Ensure backward compatibility and robust error handling.

**Files to Create:**
- `bindings/python/tests/assumptions/test_legacy.py`

**Prompt 9:**

```
Ensure complete backward compatibility and add comprehensive error handling.

Update `_loader.py`:

1. Add robust error handling throughout:
   - File I/O errors with helpful messages and suggestions
   - DataFrame validation errors with specific column/type information  
   - Memory warnings for very large expansions
   - Clear errors for malformed wide tables or ambiguous formats

2. Add performance optimizations:
   - Lazy evaluation where possible
   - Memory-efficient overflow expansion for large tables
   - Progress indicators for large operations if needed

3. Add logging support using the project's logging framework:
   - Log successful table registrations with basic stats
   - Log warnings for large memory expansions
   - Debug logging for shape detection and overflow logic

Create `bindings/python/tests/assumptions/test_legacy.py`:
- Test that all existing TableRegistry + assumption_lookup workflows continue to work unchanged
- Test importing from old paths vs new paths
- Test mixed usage: some tables loaded via old API, some via new API
- Verify no performance regressions in existing lookup code

Create `bindings/python/tests/assumptions/test_errors.py`:
- Test all error conditions with representative data
- Test file not found, permission errors, corrupt files
- Test malformed DataFrames, missing columns, wrong data types
- Test memory limits and very large overflow expansions
- Verify error messages are actionable and user-friendly

Run the complete test suite and ensure all tests pass reliably.
```

---

### Step 10: Documentation & Final Integration

**Objective:** Complete the implementation with doctests, examples, and final validation.

**Prompt 10:**

```
Complete the implementation with comprehensive documentation and final validation.

Final updates to `_loader.py`:

1. Add complete docstring with doctests to `load_assumptions()`:
   - Include examples from the plan: curve loading, wide table loading, overflow scenarios
   - Add doctests that can be executed with pytest --doctest-modules
   - Ensure examples are under 88 characters per line for hover compatibility

2. Add doctests to all helper functions:
   - _materialise(), _analyse_shape(), _tidy_curve(), etc.
   - Use minimal examples (≤5 rows) that demonstrate the key functionality
   - Test both success and failure cases where appropriate

3. Add comprehensive type hints and ensure mypy compatibility:
   - All functions should have complete type annotations
   - Handle Optional types correctly
   - Use proper polars types (pl.DataFrame, pl.Series, etc.)

Create final validation:

1. `bindings/python/tests/test_doctests.py`:
   - Test runner for all doctests in the assumptions package
   - Ensure doctests work with the actual package environment

2. Update existing tests to ensure 100% code coverage:
   - Run coverage analysis and fill any gaps
   - Ensure all code paths are tested including error conditions

3. Performance benchmark:
   - Create a benchmark script that tests realistic workloads
   - Compare lookup performance before/after (should be identical)
   - Measure memory usage with large tables

Run complete validation:
- All tests pass on Python 3.10-3.12
- Doctests execute successfully  
- No mypy errors
- Performance benchmarks meet expectations
- Memory usage is reasonable
- Public API matches the plan exactly

The implementation should be ready for production use with comprehensive test coverage and documentation.
```

---

## Success Criteria

Each step must meet these criteria before proceeding:

✅ **All tests pass** for the current and previous steps  
✅ **No breaking changes** to existing functionality  
✅ **Type hints** are complete and mypy-clean  
✅ **Error handling** is comprehensive with clear messages  
✅ **Performance** meets or exceeds existing implementation  
✅ **Code coverage** is >95% for new code  
✅ **Integration** works seamlessly with existing codebase  

---

## File Structure Summary

**Final file structure after implementation:**

```
bindings/python/gaspatchio_core/
├─ __init__.py                      # UPDATED: exports load_assumptions, assumption_lookup  
├─ assumptions.py                   # EXISTING: assumption_lookup implementation
├─ registry.py                      # EXISTING: TableRegistry class
├─ assumptions/                     # NEW PACKAGE
│   ├─ __init__.py                 # NEW: re-exports load_assumptions + assumption_lookup
│   └─ _loader.py                  # NEW: complete implementation
└─ frame/base.py                    # EXISTING: ActuarialFrame class

bindings/python/tests/assumptions/  # NEW TEST PACKAGE
├─ test_curve.py                   # NEW: curve loading tests
├─ test_wide_basic.py              # NEW: wide table tests  
├─ test_overflow.py                # NEW: overflow expansion tests
├─ test_integration.py             # NEW: end-to-end integration tests
├─ test_advanced.py                # NEW: advanced features tests
├─ test_duplicates.py              # NEW: duplicate name handling tests
├─ test_legacy.py                  # NEW: backward compatibility tests
├─ test_errors.py                  # NEW: error handling tests
└─ test_doctests.py                # NEW: doctest runner
```

This specification ensures a methodical, test-driven implementation that builds complexity gradually while maintaining backward compatibility and robust error handling throughout.
