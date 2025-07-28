# Excel Function Scalar/Vector Patterns in Python Layer

## Overview

This document captures key learnings from implementing YEARFRAC function regarding how Excel functions should handle scalar/vector input combinations in the Python bindings layer. These patterns will inform the design of other Excel functions.

## Background Context

During YEARFRAC implementation, we discovered that:
1. **Excel 365 supports dynamic arrays** - functions like YEARFRAC can work with ranges/arrays using spill functionality
2. **Python tests were incorrectly verifying Excel calculation logic** instead of focusing on Python API plumbing
3. **Scalar/vector combinations require careful design** to balance Excel compatibility with Polars implementation practicality

## Excel 365 Dynamic Array Behavior

### What Excel Supports
- **YEARFRAC with ranges**: `=YEARFRAC(A1:A5, B1:B5)` works in Excel 365
- **Vector/scalar combinations**: `=YEARFRAC(A1:A5, B1)` works (array of start dates, single end date)
- **Spill operator workaround**: Some functions "resist spilling" but work with `+` operator: `=YEARFRAC(+A1:A5, +B1:B5)`
- **Dynamic behavior**: Results automatically expand/contract as source data changes

### Excel Function Categories
Based on research, Excel functions fall into categories regarding dynamic array support:
- **Native spill functions**: Designed for arrays (new Excel 365 functions)
- **Spill-resistant functions**: Older functions like YEARFRAC, EOMONTH that need `+` workaround
- **Non-spill functions**: Don't work with arrays at all

## Current Python Implementation Status

### YEARFRAC Implementation

#### Supported Combinations ✅
1. **scalar, scalar** (column to column)
   ```python
   af["start_date"].excel.yearfrac(af["end_date"])
   ```

2. **scalar, literal** (column to literal date)  
   ```python
   af["start_date"].excel.yearfrac(datetime.date(2021, 1, 1))
   ```

3. **vector, vector** (column arrays to column arrays)
   ```python
   af["start_dates"].excel.yearfrac(af["end_dates"])  # Same length arrays
   ```

#### Not Yet Supported ⚠️
4. **vector, scalar** (list column to scalar/column)
   ```python
   af["start_list"].excel.yearfrac(af["end_date"])  # Raises NotImplementedError
   ```

5. **scalar, vector** (scalar/column to list column)
   ```python
   af["start_date"].excel.yearfrac(af["end_list"])  # Raises NotImplementedError
   ```

6. **vector, vector** (both list columns)
   ```python
   af["start_list"].excel.yearfrac(af["end_list"])  # Raises NotImplementedError
   ```

### Implementation Challenges

#### Why List Support Is Complex
1. **Plugin Function Limitations**: Polars plugin functions don't work well with `list.eval()`
2. **State Management**: Explode/group_by patterns require modifying DataFrame state
3. **Expression API Mismatch**: List operations don't fit cleanly with expression-based API design
4. **Performance Concerns**: Explode/group_by is less efficient than vectorized operations

#### Attempted Solutions
- **`list.eval()` approach**: Failed due to plugin function incompatibility
- **Explode/group_by pattern**: Works but requires complex state management that doesn't fit expression API
- **Current approach**: Clear error message with user guidance

## Testing Philosophy Evolution

### Previous Approach (Incorrect) ❌
- Tests verified Excel calculation correctness in Python
- Attempted to replicate Excel mathematical algorithms
- Mixed Python API testing with Excel logic verification

### Current Approach (Correct) ✅
- **Python tests focus on API plumbing only**:
  - Data type handling (string→date conversion)
  - Parameter validation (basis string→int conversion)
  - Error handling (invalid inputs, null values)
  - Return type verification (ExpressionProxy, float results)
  - Method chaining capability
- **Rust tests handle Excel calculation correctness**
- **Python layer responsibility**: Be a good courier between user and Rust implementation

### Test Categories That Should Exist
1. **Input/Output Type Handling**
   - Different date column types (string dates, datetime, etc.)
   - Null value propagation
   - Return type verification

2. **Parameter Processing**
   - String basis → integer conversion
   - Case-insensitive string handling
   - Invalid parameter error handling

3. **API Behavior**
   - Method chaining works
   - ExpressionProxy return values
   - Integration with ActuarialFrame workflow

4. **Combination Testing**
   - All supported scalar/vector combinations execute without error
   - Appropriate error messages for unsupported combinations

## Design Patterns for Future Excel Functions

### Function Implementation Template

```python
def excel_function(self, param1, param2=None, basis: BasisType = "default"):
    """Excel-compatible function with proper parameter handling."""
    
    # 1. Get parent frame and base expressions
    parent_frame = self._get_parent_frame()
    base_expr = self._get_polars_expr()
    param_expr = parent_frame._convert_to_expr(param1)
    
    # 2. Check for list columns (optional - depends on function)
    schema = parent_frame._df.collect_schema()
    base_is_list = self._check_if_list_column(schema)
    param_is_list = self._check_if_param_is_list(param_expr, schema)
    
    # 3. Handle list operations
    if base_is_list or param_is_list:
        raise NotImplementedError(
            f"{function_name} with list columns is not yet supported. "
            f"Excel 365 supports this via dynamic arrays, but Polars implementation "
            f"requires explode/group_by patterns. Use explode() workaround."
        )
    
    # 4. Process parameters (basis conversion, validation)
    processed_basis = self._process_basis_parameter(basis)
    
    # 5. Cast to appropriate types
    base_expr_typed = base_expr.cast(target_type, strict=False)
    param_expr_typed = param_expr.cast(target_type, strict=False)
    
    # 6. Call Rust implementation
    from ..functions.excel import excel_function_impl
    result_expr = excel_function_impl(base_expr_typed, param_expr_typed, basis=processed_basis)
    
    # 7. Return wrapped expression
    from ..column.expression_proxy import ExpressionProxy
    return ExpressionProxy(result_expr, parent_frame)
```

### Parameter Processing Patterns

#### Basis Parameter Handling
Many Excel functions use similar basis parameters. Standardize this:

```python
def _process_basis_parameter(self, basis: BasisType) -> int:
    """Convert string basis to integer, with validation."""
    if isinstance(basis, str):
        basis_map = {
            "us_nasd_30_360": 0, "30/360": 0,
            "act/act": 1, "actual/actual": 1,
            "actual/360": 2, "actual_360": 2,
            "actual/365": 3, "actual_365": 3,
            "european_30_360": 4, "30e/360": 4,
        }
        basis_lower = basis.lower()
        if basis_lower not in basis_map:
            raise ValueError(f"Invalid basis '{basis}'. Valid values: {list(basis_map.keys())}")
        return basis_map[basis_lower]
    else:
        basis_int = int(basis)
        if basis_int not in range(5):  # Adjust range per function
            raise ValueError(f"Invalid basis {basis_int}. Must be 0-4.")
        return basis_int
```

#### Date Parameter Handling
```python
def _ensure_date_expr(self, expr: pl.Expr) -> pl.Expr:
    """Ensure expression is cast to Date type with error handling."""
    return expr.cast(pl.Date, strict=False)
```

## Generalization Guidelines

### When to Support List Operations
Consider implementing list support for functions where:
1. **High user demand** for dynamic array behavior
2. **Simple list operations** that don't require complex state management
3. **Performance-critical** scenarios where explode/group_by workaround is too slow
4. **Core functionality** that's fundamental to Excel compatibility

### When to Skip List Operations Initially
Skip list support for functions where:
1. **Complex implementation** requiring significant DataFrame state changes
2. **Edge case usage** that most users won't need
3. **Workaround is reasonable** (explode/group_by pattern)
4. **Rust implementation constraints** make it technically difficult

### Error Message Standards
For unsupported list operations, use consistent messaging:
```python
raise NotImplementedError(
    f"{function_name} with list columns is not yet supported. "
    f"Excel 365 supports this via dynamic arrays, but the Polars implementation "
    f"requires explode/group_by patterns. "
    f"As a workaround, use explode() to flatten the list, calculate {function_name}, "
    f"then group_by().agg() to re-create the list structure."
)
```

## Future Implementation Strategy

### Phase 1: Core Functions (Current)
- Implement scalar/scalar, scalar/literal, vector/vector combinations
- Focus on API correctness and Excel calculation compatibility
- Provide clear error messages for unsupported combinations

### Phase 2: High-Priority List Support
- Identify most-requested functions needing list support
- Develop reusable patterns for explode/group_by operations
- Consider helper utilities for common list operation patterns

### Phase 3: Advanced Dynamic Array Features
- Investigate deeper Polars integration for list operations
- Consider custom plugin functions designed for list operations
- Evaluate performance optimizations for complex scenarios

## Key Takeaways

1. **Separation of Concerns**: Python tests verify API plumbing, Rust tests verify Excel correctness
2. **Excel Compatibility**: Know what Excel 365 supports, document what we don't support yet
3. **Pragmatic Implementation**: Start with core functionality, add list support where it matters most
4. **Clear Communication**: Provide helpful error messages that acknowledge Excel capabilities
5. **Consistent Patterns**: Use standardized approaches for parameter processing and error handling
6. **Performance Awareness**: Understand when list operations are complex and communicate alternatives

This approach balances Excel compatibility aspirations with practical Polars implementation constraints, while maintaining a clear path for future enhancement.