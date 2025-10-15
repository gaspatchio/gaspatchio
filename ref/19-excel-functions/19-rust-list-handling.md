# Rust-Level List Handling for Excel Functions

## Executive Summary

This document outlines the implementation plan for adding native Rust support for list columns in Excel functions, starting with `yearfrac`. The goal is to enable Excel functions to process actuarial projections stored as list columns (e.g., monthly cashflows over 10 years) with native Rust performance, avoiding Python-level workarounds.

## Background and Context

### The Actuarial Use Case

In actuarial modeling with gaspatchio, projections are commonly stored as list columns where:
- Each row represents a policy or model point
- Each list contains projection values (typically 120 monthly values for 10-year projections)
- Examples include: monthly cashflows, mortality rates, premium patterns, reserves

Current data structure example:
```python
# Projection data with list columns
{
    "policy_id": ["P001", "P002"],
    "projection_dates": [
        [date(2024, 1, 1), date(2024, 2, 1), ...],  # 120 dates
        [date(2024, 1, 1), date(2024, 2, 1), ...]   # 120 dates
    ],
    "maturity_date": [date(2034, 1, 1), date(2034, 1, 1)]
}
```

### Current Limitations

1. **Plugin Functions Don't Support Lists**: The current `yearfrac` implementation only handles scalar date columns
2. **Workaround Required**: Users must use explode/group_by patterns, which is cumbersome and inefficient
3. **Excel 365 Parity**: Excel 365's dynamic arrays naturally handle array operations; we should too

### Excel 365 Behavior

Excel 365's YEARFRAC function supports three patterns with dynamic arrays:

1. **Scalar vs Scalar**: `=YEARFRAC(A1, B1)` → Single value
2. **Array vs Array**: `=YEARFRAC(A1:A10, B1:B10)` → Pairwise calculation, 10 values
3. **Scalar vs Array (Broadcasting)**: `=YEARFRAC($A$1, B1:B10)` → A1 broadcast to each B value

The broadcasting behavior is critical for actuarial calculations:
- Calculate time from a single valuation date to multiple projection dates
- Calculate time from multiple issue dates to a single maturity date
- Excel automatically "lifts" the scalar to match the array dimension

### Existing Infrastructure

The gaspatchio framework already has sophisticated list column support:
- `dispatch.py` provides automatic shimming for basic operations (abs, round, etc.)
- List operations are detected via `ColumnTypeDetector`
- Shimming converts `col.abs()` to `col.list.eval(pl.element().abs())`
- **Critical limitation**: Plugin functions don't work with `list.eval()`

## Technical Analysis

### Polars Plugin Architecture

1. **Plugin Functions**: Rust functions exposed to Polars via `pyo3-polars`
2. **Type System**: Plugins declare output types via `output_type_func`
3. **Elementwise Flag**: `is_elementwise=True` indicates row-independent operations
4. **Current Pattern**: Iterate over series elements, apply function, collect results

### List Column Memory Layout

Polars stores list columns efficiently:
- Lists are backed by chunks
- All rows' lists stored as one contiguous array
- Metadata tracks start positions and lengths
- Enables efficient iteration and processing

### Why Rust-Level Support?

1. **Performance**: Native Rust processing without Python GIL overhead
2. **Memory Efficiency**: Direct access to Polars' internal representations
3. **Type Safety**: Compile-time guarantees for list operations
4. **Maintainability**: Single implementation instead of dual Python/Rust paths

## Implementation Plan

### Phase 1: Yearfrac Prototype

#### 1.1 Output Type Detection

Modify `yearfrac_output_type` to handle list inputs:

```rust
fn yearfrac_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    // Inspect input types
    let start_dtype = &input_fields[0].dtype();
    let end_dtype = &input_fields[1].dtype();
    
    match (start_dtype, end_dtype) {
        // Both inputs are list columns
        (DataType::List(inner1), DataType::List(inner2)) => {
            // Validate inner types are dates
            if !matches!(**inner1, DataType::Date) || !matches!(**inner2, DataType::Date) {
                return Err(PolarsError::ComputeError(
                    "List columns must contain Date type".into()
                ));
            }
            Ok(Field::new("year_frac", DataType::List(Box::new(DataType::Float64))))
        }
        // Standard scalar case
        (DataType::Date, DataType::Date) => {
            Ok(Field::new("year_frac", DataType::Float64))
        }
        // Mixed scalar/list case - broadcast scalar to match list
        (DataType::Date, DataType::List(inner)) if matches!(**inner, DataType::Date) => {
            // Scalar start, list end -> broadcast start
            Ok(Field::new("year_frac", DataType::List(Box::new(DataType::Float64))))
        }
        (DataType::List(inner), DataType::Date) if matches!(**inner, DataType::Date) => {
            // List start, scalar end -> broadcast end
            Ok(Field::new("year_frac", DataType::List(Box::new(DataType::Float64))))
        }
        // Error cases
        _ => Err(PolarsError::ComputeError(
            "yearfrac requires Date or List<Date> types".into()
        ))
    }
}
```

#### 1.2 Main Function Refactor

Update the main `yearfrac` function to branch based on input types:

```rust
pub fn yearfrac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    let start_series = &inputs[0];
    let end_series = &inputs[1];
    let basis = kwargs.basis.unwrap_or(BASIS_30_360_US);
    
    // Validate basis
    if !(BASIS_30_360_US..=BASIS_30_360_EU).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Must be 0, 1, 2, 3, or 4").into(),
        ));
    }
    
    // Branch based on input types
    match (start_series.dtype(), end_series.dtype()) {
        (DataType::List(_), DataType::List(_)) => {
            yearfrac_list_columns(start_series, end_series, basis)
        }
        (DataType::Date, DataType::Date) => {
            yearfrac_scalar_columns(start_series, end_series, basis)
        }
        (DataType::Date, DataType::List(_)) => {
            // Broadcast scalar start date to match list end dates
            yearfrac_broadcast_start(start_series, end_series, basis)
        }
        (DataType::List(_), DataType::Date) => {
            // Broadcast scalar end date to match list start dates
            yearfrac_broadcast_end(start_series, end_series, basis)
        }
        _ => Err(PolarsError::ComputeError(
            "Invalid input types for yearfrac".into()
        ))
    }
}
```

#### 1.3 Scalar Implementation (Existing Logic)

Extract current logic into a dedicated function:

```rust
fn yearfrac_scalar_columns(
    start_series: &Series,
    end_series: &Series,
    basis: i32
) -> PolarsResult<Series> {
    // Current implementation - extract existing code
    let start_dates = start_series.date()?;
    let end_dates = end_series.date()?;
    
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    let result_ca = start_dates
        .into_iter()
        .zip(end_dates.into_iter())
        .map(|(start_opt, end_opt)| {
            match (start_opt, end_opt) {
                (Some(start_days), Some(end_days)) => {
                    let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                    let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                    Some(calculate_yearfrac(start_date, end_date, basis))
                }
                _ => None,
            }
        })
        .collect::<Float64Chunked>();
    
    Ok(result_ca.with_name("year_frac").into_series())
}
```

#### 1.4 List Implementation (New Logic)

Implement list column processing:

```rust
fn yearfrac_list_columns(
    start_series: &Series,
    end_series: &Series,
    basis: i32
) -> PolarsResult<Series> {
    let start_lists = start_series.list()?;
    let end_lists = end_series.list()?;
    
    // Ensure both series have the same length
    if start_lists.len() != end_lists.len() {
        return Err(PolarsError::ComputeError(
            "Input series must have the same length".into()
        ));
    }
    
    // Process each row (list pair)
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "year_frac",
        start_lists.len(),
        start_lists.len() * 10, // Estimate capacity
        DataType::Float64
    );
    
    for (start_list_opt, end_list_opt) in start_lists.into_iter().zip(end_lists.into_iter()) {
        match (start_list_opt, end_list_opt) {
            (Some(start_arr), Some(end_arr)) => {
                // Convert arrays to series for easier processing
                let start_series = Series::from_any_values("", &[start_arr], false)?;
                let end_series = Series::from_any_values("", &[end_arr], false)?;
                
                // Process this list pair
                let result_values = process_date_list_pair(&start_series, &end_series, basis)?;
                
                // Append to builder
                builder.append_slice(result_values.f64()?.cont_slice()?);
            }
            _ => {
                // One or both lists are null
                builder.append_null();
            }
        }
    }
    
    Ok(builder.finish().into_series())
}

fn process_date_list_pair(
    start_list: &Series,
    end_list: &Series,
    basis: i32
) -> PolarsResult<Series> {
    // Ensure lists have same length
    if start_list.len() != end_list.len() {
        return Err(PolarsError::ComputeError(
            "Date lists must have the same length".into()
        ));
    }
    
    let start_dates = start_list.date()?;
    let end_dates = end_list.date()?;
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    // Process each date pair in the lists
    let results: Float64Chunked = start_dates
        .into_iter()
        .zip(end_dates.into_iter())
        .map(|(start_opt, end_opt)| {
            match (start_opt, end_opt) {
                (Some(start_days), Some(end_days)) => {
                    let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                    let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                    Some(calculate_yearfrac(start_date, end_date, basis))
                }
                _ => None,
            }
        })
        .collect();
    
    Ok(results.into_series())
}
```

#### 1.5 Broadcasting Implementations

Implement broadcasting for scalar/list combinations:

```rust
fn yearfrac_broadcast_start(
    start_series: &Series,  // Scalar Date
    end_series: &Series,    // List<Date>
    basis: i32
) -> PolarsResult<Series> {
    // Get the single start date
    let start_date_ca = start_series.date()?;
    if start_date_ca.len() != 1 {
        return Err(PolarsError::ComputeError(
            "Scalar start date must have exactly one value".into()
        ));
    }
    let start_date_opt = start_date_ca.get(0);
    
    // Get the list of end dates
    let end_lists = end_series.list()?;
    
    // Process each list of end dates with the single start date
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "year_frac",
        end_lists.len(),
        end_lists.len() * 10,
        DataType::Float64
    );
    
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    for end_list_opt in end_lists.into_iter() {
        match (start_date_opt, end_list_opt) {
            (Some(start_days), Some(end_arr)) => {
                // Convert start date once
                let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                
                // Process all end dates in this list
                let end_series = Series::from_any_values("", &[end_arr], false)?;
                let end_dates = end_series.date()?;
                
                let results: Vec<f64> = end_dates
                    .into_iter()
                    .map(|end_opt| {
                        match end_opt {
                            Some(end_days) => {
                                let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                                calculate_yearfrac(start_date, end_date, basis)
                            }
                            None => f64::NAN,
                        }
                    })
                    .collect();
                
                builder.append_slice(&results);
            }
            _ => {
                builder.append_null();
            }
        }
    }
    
    Ok(builder.finish().into_series())
}

fn yearfrac_broadcast_end(
    start_series: &Series,  // List<Date>
    end_series: &Series,    // Scalar Date
    basis: i32
) -> PolarsResult<Series> {
    // Get the list of start dates
    let start_lists = start_series.list()?;
    
    // Get the single end date
    let end_date_ca = end_series.date()?;
    if end_date_ca.len() != 1 {
        return Err(PolarsError::ComputeError(
            "Scalar end date must have exactly one value".into()
        ));
    }
    let end_date_opt = end_date_ca.get(0);
    
    // Process each list of start dates with the single end date
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "year_frac",
        start_lists.len(),
        start_lists.len() * 10,
        DataType::Float64
    );
    
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    for start_list_opt in start_lists.into_iter() {
        match (start_list_opt, end_date_opt) {
            (Some(start_arr), Some(end_days)) => {
                // Convert end date once
                let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                
                // Process all start dates in this list
                let start_series = Series::from_any_values("", &[start_arr], false)?;
                let start_dates = start_series.date()?;
                
                let results: Vec<f64> = start_dates
                    .into_iter()
                    .map(|start_opt| {
                        match start_opt {
                            Some(start_days) => {
                                let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                                calculate_yearfrac(start_date, end_date, basis)
                            }
                            None => f64::NAN,
                        }
                    })
                    .collect();
                
                builder.append_slice(&results);
            }
            _ => {
                builder.append_null();
            }
        }
    }
    
    Ok(builder.finish().into_series())
}
```

### Phase 2: Testing Strategy

#### 2.1 Rust Unit Tests

Add comprehensive tests in `yearfrac.rs`:

```rust
#[cfg(test)]
mod list_tests {
    use super::*;
    
    #[test]
    fn test_yearfrac_with_list_columns() {
        // Create list columns of dates
        let dates_2023 = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
        ];
        let dates_2024 = vec![
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 12, 31).unwrap(),
        ];
        
        // Convert to Series format
        let start_lists = create_list_series(vec![dates_2023.clone(), dates_2023]);
        let end_lists = create_list_series(vec![dates_2024.clone(), dates_2024]);
        
        // Test with different bases
        for basis in 0..=4 {
            let kwargs = YearFracKwargs { basis: Some(basis) };
            let result = yearfrac(&[start_lists.clone(), end_lists.clone()], &kwargs).unwrap();
            
            // Verify result is a list column
            assert!(matches!(result.dtype(), DataType::List(_)));
            
            // Verify values
            let list_ca = result.list().unwrap();
            assert_eq!(list_ca.len(), 2); // Two rows
            
            // Each row should have 3 values
            for row in list_ca.into_iter() {
                if let Some(arr) = row {
                    let series = Series::from_any_values("", &[arr], false).unwrap();
                    assert_eq!(series.len(), 3);
                }
            }
        }
    }
    
    #[test]
    fn test_mixed_null_handling() {
        // Test with nulls at different levels
        // ... implementation ...
    }
    
    #[test]
    fn test_empty_lists() {
        // Test with empty lists
        // ... implementation ...
    }
    
    #[test]
    fn test_broadcasting_scalar_start() {
        // Test scalar start date with list of end dates
        let start_date = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let end_dates = vec![
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
            NaiveDate::from_ymd_opt(2024, 6, 1).unwrap(),
        ];
        
        // Create scalar start and list end
        let start_series = create_date_series(vec![start_date]);
        let end_lists = create_list_series(vec![end_dates.clone(), end_dates]);
        
        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = yearfrac(&[start_series, end_lists], &kwargs).unwrap();
        
        // Verify result is a list column
        assert!(matches!(result.dtype(), DataType::List(_)));
        
        let list_ca = result.list().unwrap();
        assert_eq!(list_ca.len(), 2); // Two rows of lists
        
        // Each list should have 3 values (broadcast scalar to each element)
        for row in list_ca.into_iter() {
            if let Some(arr) = row {
                let series = Series::from_any_values("", &[arr], false).unwrap();
                assert_eq!(series.len(), 3);
                
                // Verify all values are calculated from the same start date
                let values = series.f64().unwrap();
                assert!(values.get(0).unwrap() < values.get(1).unwrap());
                assert!(values.get(1).unwrap() < values.get(2).unwrap());
            }
        }
    }
    
    #[test]
    fn test_broadcasting_scalar_end() {
        // Test list of start dates with scalar end date
        let start_dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
        ];
        let end_date = NaiveDate::from_ymd_opt(2024, 1, 1).unwrap();
        
        // Create list start and scalar end
        let start_lists = create_list_series(vec![start_dates.clone(), start_dates]);
        let end_series = create_date_series(vec![end_date]);
        
        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = yearfrac(&[start_lists, end_series], &kwargs).unwrap();
        
        // Verify result structure
        assert!(matches!(result.dtype(), DataType::List(_)));
        
        let list_ca = result.list().unwrap();
        assert_eq!(list_ca.len(), 2);
        
        // Verify values decrease (same end, increasing start dates)
        for row in list_ca.into_iter() {
            if let Some(arr) = row {
                let series = Series::from_any_values("", &[arr], false).unwrap();
                let values = series.f64().unwrap();
                assert!(values.get(0).unwrap() > values.get(1).unwrap());
                assert!(values.get(1).unwrap() > values.get(2).unwrap());
            }
        }
    }
}
```

#### 2.2 Python Integration Tests

Create tests that verify the actuarial use case:

```python
def test_yearfrac_with_projection_dates():
    """Test yearfrac with typical actuarial projection structure."""
    # Create 120 monthly dates for 10-year projection
    base_date = datetime.date(2024, 1, 1)
    projection_dates = [
        [base_date + relativedelta(months=i) for i in range(120)]
        for _ in range(1000)  # 1000 policies
    ]
    
    # Maturity dates
    maturity_dates = [
        [datetime.date(2034, 1, 1)] * 120  # Same maturity for all months
        for _ in range(1000)
    ]
    
    af = ActuarialFrame({
        "policy_id": list(range(1000)),
        "projection_dates": projection_dates,
        "maturity_dates": maturity_dates
    })
    
    # Calculate time to maturity for each projection month
    result = af.with_columns(
        time_to_maturity=af["projection_dates"].excel.yearfrac(
            af["maturity_dates"], 
            basis="act/act"
        )
    )
    
    # Verify shape and values
    assert result["time_to_maturity"].dtype == pl.List(pl.Float64)
    # ... more assertions ...

def test_yearfrac_broadcasting():
    """Test yearfrac with broadcasting - matching Excel behavior."""
    # Example 1: Single valuation date vs multiple projection dates
    valuation_date = datetime.date(2024, 1, 1)
    projection_dates = [
        [datetime.date(2024, i, 1) for i in range(1, 13)]  # Monthly dates
        for _ in range(100)  # 100 policies
    ]
    
    af = ActuarialFrame({
        "policy_id": list(range(100)),
        "valuation_date": valuation_date,  # Scalar - will be broadcast
        "projection_dates": projection_dates
    })
    
    # Calculate time from valuation to each projection date
    # This mimics Excel's =YEARFRAC($A$1, B1:B12)
    result = af.with_columns(
        time_from_valuation=af["valuation_date"].excel.yearfrac(
            af["projection_dates"], 
            basis="30/360"
        )
    )
    
    # Result should be List[Float64] with increasing values
    assert result["time_from_valuation"].dtype == pl.List(pl.Float64)
    
    # Example 2: Multiple dates vs single maturity
    issue_dates = [
        [datetime.date(2020 + i//12, (i%12)+1, 1) for i in range(48)]  # 4 years of monthly issues
        for _ in range(50)
    ]
    maturity_date = datetime.date(2030, 1, 1)  # Single maturity for all
    
    af2 = ActuarialFrame({
        "policy_id": list(range(50)),
        "issue_dates": issue_dates,
        "maturity_date": maturity_date  # Scalar - will be broadcast
    })
    
    # Calculate time to maturity for each issue date
    # This mimics Excel's =YEARFRAC(A1:A48, $B$1)
    result2 = af2.with_columns(
        time_to_maturity=af2["issue_dates"].excel.yearfrac(
            af2["maturity_date"], 
            basis="act/365"
        )
    )
    
    # Result should show decreasing time to maturity for later issue dates
    assert result2["time_to_maturity"].dtype == pl.List(pl.Float64)
```

### Phase 3: Performance Optimization

#### 3.1 Memory Pre-allocation

- Estimate output size based on input list lengths
- Pre-allocate builders to avoid reallocations
- Use capacity hints from input data

### Phase 4: Generalization

Once yearfrac is working, create a pattern for other Excel functions:

1. **Template Trait**: Define a trait for list-aware Excel functions
2. **Macro Generation**: Create macros to reduce boilerplate
3. **Documentation**: Establish patterns for future implementations

## Implementation Considerations

### Error Handling

1. **Type Mismatches**: Clear error messages when types don't match
2. **Length Mismatches**: Handle lists of different lengths gracefully
3. **Null Propagation**: Consistent null handling at all levels

### Backward Compatibility

1. **No Breaking Changes**: Existing scalar operations must work unchanged
2. **Python API**: No changes required to Python wrapper
3. **Performance**: Scalar path should not be slower

### Future Extensions

1. **Mixed Types**: Support scalar + list combinations (broadcasting)
2. **Nested Lists**: Handle List<List<Date>> for multi-dimensional data
3. **Other Functions**: Apply pattern to PV, FV, RATE, etc.

## Success Criteria

1. **Functionality**: yearfrac works seamlessly with list columns
2. **Performance**: Native Rust speed, faster than explode/group_by
3. **Compatibility**: No breaking changes to existing code
4. **Maintainability**: Clear, documented code that serves as a template

## References

1. [Polars List Column Documentation](https://docs.pola.rs/user-guide/expressions/lists/)
2. [pyo3-polars Plugin Guide](https://github.com/pola-rs/pyo3-polars)
3. [Excel 365 Dynamic Arrays](https://support.microsoft.com/en-us/office/dynamic-array-formulas-and-spilled-array-behavior-205c6b06-03ba-4151-89a1-87a7eb36e531)
4. gaspatchio internal docs: `ref/19-excel-functions/py-funcs/19-scalar-vector-research.md`

## Issue: Broadcasting Behavior Mismatch Between Polars DataFrames and Rust Implementation

### Background

The current Rust implementation of `yearfrac` with list support assumes a distinction between "scalar" columns (length 1) and "vector" columns (length > 1) for broadcasting operations. However, this assumption conflicts with how Polars DataFrames handle scalar values.

### The Problem

When creating a DataFrame with scalar values, Polars automatically broadcasts them to match the DataFrame's row count:

```python
# Python code - what we write:
af = ActuarialFrame({
    "policy_id": [1, 2],
    "valuation_date": datetime.date(2024, 1, 1),  # Intended as scalar
    "projection_dates": [
        [date(2024, 1, 1), date(2024, 2, 1), ...],  # List for policy 1
        [date(2024, 1, 1), date(2024, 2, 1), ...]   # List for policy 2
    ]
})

# What Polars actually creates:
# valuation_date column: [date(2024, 1, 1), date(2024, 1, 1)]  # Length 2, not 1!
```

### Current Rust Implementation Expectation

The broadcasting functions in Rust explicitly check for scalar columns with exactly one value:

```rust
fn yearfrac_broadcast_start(
    start_series: &Series,  // Expected: Scalar Date with len() == 1
    end_series: &Series,    // List<Date>
    basis: i32
) -> PolarsResult<Series> {
    let start_date_ca = start_series.date()?;
    if start_date_ca.len() != 1 {
        return Err(PolarsError::ComputeError(
            "Scalar start date must have exactly one value".into()
        ));
    }
    // ... broadcasting logic
}
```

### The Excel Model We're Trying to Emulate

In Excel, broadcasting happens naturally with cell references:
- `=YEARFRAC($A$1, B1:B10)` - Single cell A1 broadcasts to each element in B1:B10
- `=YEARFRAC(A1:A10, $B$1)` - Each element in A1:A10 pairs with single cell B1

### Actuarial Use Cases Affected

This issue impacts common actuarial patterns:

1. **Valuation Date to Projection Dates**: Calculate time from a single valuation date to multiple monthly projection dates
2. **Issue Dates to Maturity Date**: Calculate time from various policy issue dates to a common maturity date
3. **Fixed Reference Date Calculations**: Any calculation involving a fixed reference date and varying dates

### Proposed Solution

The Rust implementation should recognize Polars' broadcasting behavior and handle "repeated scalar" columns appropriately. Options include:

1. **Detect Repeated Values**: Instead of checking `len() == 1`, check if all values in the column are identical:
   ```rust
   fn is_broadcasted_scalar(series: &Series) -> bool {
       if series.len() <= 1 {
           return true;
       }
       // Check if all values are the same
       let first = series.get(0);
       series.iter().all(|val| val == first)
   }
   ```

2. **Accept Any Length for Broadcasting**: Remove the length check entirely and use the first value for broadcasting:
   ```rust
   fn yearfrac_broadcast_start(
       start_series: &Series,  // Use first value for broadcasting
       end_series: &Series,    // List<Date>
       basis: i32
   ) -> PolarsResult<Series> {
       let start_date_ca = start_series.date()?;
       let start_date_opt = start_date_ca.get(0);  // Just use first value
       // ... rest of implementation
   }
   ```

3. **Support Both Patterns**: Check for either true scalars (len=1) OR repeated values:
   ```rust
   if start_date_ca.len() != 1 && !is_uniform_column(start_date_ca) {
       return Err(PolarsError::ComputeError(
           "Broadcasting requires either a scalar or uniform column".into()
       ));
   }
   ```

### Test Cases to Add

Once the Rust implementation is updated, these test patterns should work:

```python
# Test 1: DataFrame-created "scalar" (actually broadcasted)
af = ActuarialFrame({
    "id": [1, 2, 3],
    "val_date": date(2024, 1, 1),  # Creates [date, date, date]
    "proj_dates": [[date(2024, i, 1) for i in range(1, 13)] for _ in range(3)]
})
result = af["val_date"].excel.yearfrac(af["proj_dates"])  # Should broadcast

# Test 2: Explicit repeated values
af = ActuarialFrame({
    "id": [1, 2, 3],
    "val_date": [date(2024, 1, 1)] * 3,  # Explicitly repeated
    "proj_dates": [[date(2024, i, 1) for i in range(1, 13)] for _ in range(3)]
})
result = af["val_date"].excel.yearfrac(af["proj_dates"])  # Should broadcast

# Test 3: True varying values should not broadcast
af = ActuarialFrame({
    "id": [1, 2, 3],
    "val_date": [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)],  # Different values
    "proj_dates": [[date(2024, i, 1) for i in range(1, 13)] for _ in range(3)]
})
# This should NOT use broadcasting logic - each row uses its own val_date
```

### Impact on Other Excel Functions

This pattern will need to be applied consistently across all Excel functions that support broadcasting:
- PV, FV, NPV, XNPV (present/future value calculations with varying dates)
- PMT, PPMT, IPMT (payment calculations with varying periods)
- Any function where scalar/vector combinations make sense

### Recommendation

Implement Option 2 (Accept Any Length for Broadcasting) as it:
- Aligns with Polars' natural DataFrame behavior
- Simplifies the user experience (no need to worry about "true" scalars)
- Matches user intent when they provide a single value to the DataFrame constructor
- Is backwards compatible with any existing code