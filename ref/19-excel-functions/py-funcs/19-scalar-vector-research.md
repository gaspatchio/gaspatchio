# Scalar vs Vector Operations: Research Document

## Executive Summary

This document clarifies the terminology and implementation patterns for scalar, vector, and list operations in data processing libraries, with a focus on how they relate to Excel 365's dynamic array functionality. The research covers Polars, NumPy, pandas, and Excel's approaches to array operations and broadcasting.

## Terminology Clarification

### Scalar
- **Definition**: A single value (e.g., integer, float, string)
- **Mathematical Context**: Distinguishes a single number from a vector or matrix
- **In Code**: A variable that holds one individual value
- **Examples**: `42`, `3.14`, `"hello"`, `True`

### Vector
- **Definition**: A one-dimensional array of homogeneous values
- **Key Characteristics**:
  - Fixed data type for all elements
  - Can be operated on element-wise
  - Supports SIMD (Single Instruction, Multiple Data) operations
- **Examples**: `[1, 2, 3, 4]`, `np.array([1.0, 2.0, 3.0])`

### List Column
- **Definition**: A column where each cell contains a collection (list/array) of values
- **Key Characteristics**:
  - Variable length per row (unlike fixed-size arrays)
  - Can contain nested data structures
  - More flexible but less performant than vector operations
- **Examples**: Words in sentences, tags per item, time series per entity

### Array Column (Fixed-Size)
- **Definition**: A column where each cell contains an array of fixed dimensions
- **Key Characteristics**:
  - Same shape/size across all rows
  - More memory-efficient than list columns
  - Better performance for vectorized operations
- **Examples**: Embeddings, coordinates, fixed-size matrices

## Excel 365 Dynamic Arrays

### Core Concepts

1. **Dynamic Arrays**: Formulas that return multiple values automatically "spill" into neighboring cells
2. **Spill Range**: The area where array results are displayed
3. **No CSE Required**: Unlike legacy array formulas, no Ctrl+Shift+Enter needed

### Key Operators

1. **# (Spill Range Operator)**
   - References entire spill range: `A2#` refers to all spilled values from A2
   - Dynamic: Adjusts automatically as spill range changes
   
2. **@ (Implicit Intersection Operator)**
   - Forces single value return from array formula
   - Prevents spilling behavior
   - Used for backward compatibility

### Example Behaviors

```excel
# Dynamic array that spills
=SEQUENCE(5,3)  # Creates 5x3 grid of sequential numbers

# Reference entire spill range
=SUM(A1#)       # Sums all values in spill range starting at A1

# Force single value (no spill)
=@FILTER(A:A, B:B="Active")  # Returns only first match
```

### Element-wise Operations

Excel 365 supports element-wise operations on arrays:
- `{1,2,3} * {4,5,6}` → `{4,10,18}`
- Scalar broadcasting: `{1,2,3} * 2` → `{2,4,6}`
- Mixed dimensions follow broadcasting rules

## Library-Specific Implementations

### Polars

#### List vs Array Columns

**List Columns (`pl.List`)**:
- Variable length per row
- Each row is a `pl.Series` internally
- More flexible but less performant
- Use when: Varying lengths needed (e.g., words per sentence)

**Array Columns (`pl.Array`)**:
- Fixed shape across all rows
- More memory-efficient
- Faster operations via `arr` namespace
- Use when: Fixed dimensions (e.g., 3D coordinates, embeddings)

#### Key Differences
```python
# List column - variable length OK
df = pl.DataFrame({
    "words": [["hello", "world"], ["foo"], ["bar", "baz", "qux"]]
})

# Array column - must specify shape
df = pl.DataFrame({
    "coords": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
}, schema={"coords": pl.Array(pl.Float64, shape=(3,))})
```

#### Broadcasting Limitations
- As of 2024, Polars lacks full NumPy-style broadcasting
- Cannot directly multiply DataFrame by list/array
- Feature requested but not yet implemented

### NumPy Broadcasting

#### Rules
1. Arrays are right-aligned by shape
2. Dimensions match if equal or one is 1
3. Size-1 dimensions are "stretched" to match

#### Examples
```python
# Scalar-vector broadcasting
np.array([1, 2, 3]) * 2  # → [2, 4, 6]

# Vector-vector (same shape)
np.array([1, 2, 3]) * np.array([4, 5, 6])  # → [4, 10, 18]

# Matrix-vector broadcasting
matrix = np.array([[1, 2], [3, 4]])
vector = np.array([10, 20])
matrix * vector  # → [[10, 40], [30, 80]] (row-wise)
```

### pandas Broadcasting

#### Built-in Support
- Automatic index alignment
- Methods like `.multiply()` with axis control
- Preserves labels and metadata

#### Best Practices
```python
# Explicit multiplication with axis control
df.multiply(series, axis=0)  # Along rows
df.multiply(series, axis=1)  # Along columns

# Scalar broadcasting
df * 2  # Multiplies all values by 2

# Array broadcasting (must match dimensions)
df * np.array([1, 2, 3])  # If df has 3 columns
```

## Implementation Patterns

### Pattern 1: Scalar-Vector Operations
```python
# All libraries support scalar broadcasting
scalar * vector → element-wise multiplication

# Excel: =A1:A10 * 2
# NumPy: arr * 2
# pandas: df['col'] * 2
# Polars: df['col'] * 2
```

### Pattern 2: Vector-Vector (Same Size)
```python
# Element-wise operations on same-sized vectors
vector1 * vector2 → [v1[0]*v2[0], v1[1]*v2[1], ...]

# Excel: =A1:A10 * B1:B10
# NumPy: arr1 * arr2
# pandas: series1 * series2
# Polars: col1 * col2
```

### Pattern 3: Broadcasting Different Shapes
```python
# Smaller dimension expanded to match larger
matrix * row_vector → broadcast row to each matrix row
matrix * col_vector → broadcast column to each matrix column

# NumPy/pandas: Full support
# Excel: Supports via array formulas
# Polars: Limited support (in development)
```

### Pattern 4: List/Array Column Operations
```python
# Operations on nested data structures

# Polars List: Variable length
df.with_columns(
    pl.col("list_col").list.sum()  # Sum each list
)

# Polars Array: Fixed size, faster
df.with_columns(
    pl.col("array_col").arr.sum()  # Sum each array
)
```

## Best Practices and Recommendations

### 1. Choose the Right Data Structure
- **Scalar**: Single values, constants
- **Vector**: Homogeneous sequences for batch operations
- **List Column**: Variable-length or heterogeneous data per row
- **Array Column**: Fixed-size homogeneous data (prefer over lists when possible)

### 2. Performance Optimization
- Use array columns over list columns when shape is fixed
- Leverage vectorized operations instead of loops
- Enable SIMD where possible (automatic in NumPy/Polars arrays)
- Avoid unnecessary copies during broadcasting

### 3. Broadcasting Guidelines
- Understand dimension alignment rules
- Use explicit axis parameters in pandas
- Check shape compatibility before operations
- Be aware of memory implications for large arrays

### 4. Excel Compatibility
- Dynamic arrays in Excel 365 behave similarly to NumPy broadcasting
- Use `#` for dynamic spill ranges
- Use `@` to prevent spilling when needed
- Element-wise operations work as expected

### 5. Library-Specific Tips

**Polars**:
- Prefer `pl.Array` over `pl.List` for performance
- Use namespace functions (`arr.*`, `list.*`) for operations
- Wait for full broadcasting support or use workarounds

**NumPy/pandas**:
- Leverage automatic broadcasting
- Use `.multiply()` in pandas for explicit control
- Let pandas handle index alignment

**Excel**:
- Embrace dynamic arrays (no more CSE!)
- Use structured references with tables
- Leverage new array functions (FILTER, SORT, etc.)

## Common Pitfalls

1. **Mixing List and Array Operations**: Different performance characteristics and APIs
2. **Assuming Broadcasting Works Everywhere**: Polars has limitations
3. **Ignoring Memory Implications**: Broadcasting can create large temporary arrays
4. **Not Checking Shape Compatibility**: Leads to runtime errors
5. **Overusing List Columns**: When fixed-size arrays would be more efficient

## Conclusion

Understanding the distinction between scalars, vectors, lists, and arrays is crucial for efficient data processing. While terminology varies slightly between systems, the core concepts remain:

- **Scalars** are single values
- **Vectors** are 1D arrays for efficient batch operations  
- **List columns** provide flexibility for variable-length data
- **Array columns** offer performance for fixed-size data
- **Broadcasting** enables efficient operations across different shapes

Choose the appropriate structure based on your data characteristics and performance requirements. Modern tools like Excel 365, NumPy, and pandas make these operations intuitive, while newer libraries like Polars are still developing full broadcasting support.

## Actuarial Use Case: List Columns for Projections

### Context
In actuarial modeling, list columns are commonly used to store projection data:
- Each row represents a policy or model point
- Each list contains ~120 monthly values (10-year projections)
- Lists are typically the same size across the frame
- Examples: monthly cashflows, mortality rates, premium patterns

### Current Implementation: Sophisticated List Shimming

The gaspatchio framework includes a sophisticated shimming mechanism in `dispatch.py`:

1. **Automatic Detection**: `ColumnTypeDetector` identifies list columns from schema and computation graph
2. **Transparent Shimming**: Operations like `col.abs()` automatically convert to `col.list.eval(pl.element().abs())`
3. **Supported Operations**: Works for operations in `_NUMERIC_UNARY` and `_NUMERIC_ELEMENTWISE`
4. **Limitation**: Plugin functions (like yearfrac) don't work well with `list.eval()`

### Implementation Options for Excel Functions

Given the actuarial need for list column support in Excel functions, here are three approaches:

#### Option A: Extend the Shimming System
- **Approach**: Add Excel functions to the shimming lists in `dispatch.py`
- **Pros**: 
  - Consistent with existing architecture
  - Transparent to users
  - No API changes needed
- **Cons**: 
  - Plugin functions don't work with `list.eval()`
  - Would require Rust-level changes or Python reimplementation
  - May have performance implications

#### Option B: Dual Implementation (Recommended)
- **Approach**: 
  - Keep plugin function for regular columns
  - Add Python-based list column handler that uses explode/group_by
  - Detect list columns and route appropriately
- **Pros**:
  - Works with existing plugin architecture
  - Provides transparent list support
  - Can optimize performance case-by-case
- **Cons**:
  - More complex implementation
  - Two code paths to maintain

Example implementation pattern:
```python
def yearfrac(self, end_date, basis=1):
    if self._is_list_column():
        # Python-based explode/group_by implementation
        return self._yearfrac_list_impl(end_date, basis)
    else:
        # Existing plugin function path
        return self._yearfrac_regular_impl(end_date, basis)
```

#### Option C: Rust-Level List Support
- **Approach**: Implement list handling directly in Rust plugins
- **Pros**:
  - Best performance
  - Single implementation
  - Full control over behavior
- **Cons**:
  - Most complex to implement
  - Requires significant Rust work
  - May still have limitations with Polars plugin API

### Recommended Strategy

1. **Short Term**: Use Option B for high-priority functions
   - Start with frequently used functions (yearfrac, pv, fv)
   - Provide clear documentation about list support
   - Monitor performance implications

2. **Medium Term**: Investigate Option C feasibility
   - Work with Polars team on plugin improvements
   - Consider custom Rust implementations

3. **Long Term**: Standardize list column patterns
   - Create reusable utilities for list operations
   - Potentially contribute improvements back to Polars

### Performance Considerations

For typical actuarial use (120 monthly values × thousands of policies):
- Explode/group_by overhead is acceptable for most functions
- Memory usage scales linearly with projection length
- Consider chunking for very large portfolios
- Profile specific functions to identify bottlenecks

## References

1. [NumPy Broadcasting Documentation](https://numpy.org/doc/stable/user/basics.broadcasting.html)
2. [Polars User Guide - Lists and Arrays](https://docs.pola.rs/user-guide/expressions/lists-and-arrays/)
3. [Microsoft Support - Dynamic Arrays](https://support.microsoft.com/en-us/office/dynamic-array-formulas-and-spilled-array-behavior-205c6b06-03ba-4151-89a1-87a7eb36e531)
4. [Excel Arrays and Vectors](https://excelatfinance.com/xlf17/xlf-array-element-wise.php)
5. [Pandas Operations Documentation](https://jakevdp.github.io/PythonDataScienceHandbook/03.03-operations-in-pandas.html)
6. [Understanding Polars Nested Column Types](https://www.rhosignal.com/posts/nested-dtypes/)
7. [Vector Processing and SIMD](https://www.influxdata.com/glossary/vector-processing-SIMD/)