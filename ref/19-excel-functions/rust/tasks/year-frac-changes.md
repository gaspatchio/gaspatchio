# Yearfrac Function Enhancement Specification

## Problem Statement

The `yearfrac` function in the Rust plugin currently fails when receiving datetime inputs, even though Excel's YEARFRAC naturally handles datetime values by extracting the date portion. This causes test failures when Python code passes datetime values to the function.

## Current Behavior

1. The plugin validation (`yearfrac_output_type`) rejects datetime inputs before execution
2. Error message: `"yearfrac requires Date or List[Date] inputs, got datetime[μs] and datetime[μs]"`
3. The type validation happens at the Polars plugin planning stage, preventing the actual function from running

## Required Changes

### 1. Update Type Validation in `yearfrac_output_type`

**File**: `core/src/excel/yearfrac.rs`

**Current Code**:
```rust
pub fn yearfrac_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let start_type = &input_fields[0].dtype;
    let end_type = &input_fields[1].dtype;

    match (start_type, end_type) {
        (DataType::Date, DataType::Date) => Ok(Field::new("year_frac".into(), DataType::Float64)),
        (DataType::List(_), _) | (_, DataType::List(_)) => Ok(Field::new(
            "year_frac".into(),
            DataType::List(Box::new(DataType::Float64)),
        )),
        _ => Ok(Field::new("year_frac".into(), DataType::Float64)),
    }
}
```

**Required Change**:
```rust
pub fn yearfrac_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let start_type = &input_fields[0].dtype;
    let end_type = &input_fields[1].dtype;

    // Determine if output should be a list based on input types
    let is_list = matches!(start_type, DataType::List(_)) || matches!(end_type, DataType::List(_));
    
    // Accept Date, Datetime, and their List variants
    let is_valid = match (start_type, end_type) {
        // Scalar types
        (DataType::Date, DataType::Date) |
        (DataType::Date, DataType::Datetime(_, _)) |
        (DataType::Datetime(_, _), DataType::Date) |
        (DataType::Datetime(_, _), DataType::Datetime(_, _)) => true,
        
        // List types - check inner types
        (DataType::List(inner1), DataType::List(inner2)) => {
            matches!(inner1.as_ref(), DataType::Date | DataType::Datetime(_, _)) &&
            matches!(inner2.as_ref(), DataType::Date | DataType::Datetime(_, _))
        }
        (DataType::List(inner), DataType::Date) |
        (DataType::Date, DataType::List(inner)) |
        (DataType::List(inner), DataType::Datetime(_, _)) |
        (DataType::Datetime(_, _), DataType::List(inner)) => {
            matches!(inner.as_ref(), DataType::Date | DataType::Datetime(_, _))
        }
        
        _ => false,
    };
    
    if !is_valid {
        return Err(PolarsError::ComputeError(
            format!(
                "yearfrac requires Date/Datetime or List[Date/Datetime] inputs, got {} and {}",
                start_type, end_type
            )
            .into(),
        ));
    }
    
    let output_type = if is_list {
        DataType::List(Box::new(DataType::Float64))
    } else {
        DataType::Float64
    };
    
    Ok(Field::new("year_frac".into(), output_type))
}
```

### 2. Improve Type Conversion in Main Function

**File**: `core/src/excel/yearfrac.rs`

**Current Issue**: The conversion logic exists but has borrowing issues and doesn't handle all cases properly.

**Required Changes**:

```rust
pub fn yearfrac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    let basis = kwargs.basis.unwrap_or(BASIS_30_360_US);

    // Validate basis
    if !(BASIS_30_360_US..=BASIS_30_360_EU).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Must be 0, 1, 2, 3, or 4").into(),
        ));
    }

    // Convert inputs to appropriate date types
    let start_date_series = convert_to_date_series(&inputs[0])?;
    let end_date_series = convert_to_date_series(&inputs[1])?;

    // Handle different input type combinations
    match (start_date_series.dtype(), end_date_series.dtype()) {
        (DataType::Date, DataType::Date) => {
            let start_dates = start_date_series.date()?;
            let end_dates = end_date_series.date()?;
            yearfrac_scalar(start_dates, end_dates, basis)
        }
        (DataType::List(_), DataType::Date) => {
            yearfrac_list_scalar(&start_date_series, &end_date_series, basis, false)
        }
        (DataType::Date, DataType::List(_)) => {
            yearfrac_list_scalar(&end_date_series, &start_date_series, basis, true)
        }
        (DataType::List(_), DataType::List(_)) => {
            yearfrac_list_list(&start_date_series, &end_date_series, basis)
        }
        _ => unreachable!("convert_to_date_series should ensure valid types"),
    }
}

/// Convert a Series to Date type, handling Datetime and List variants
fn convert_to_date_series(series: &Series) -> PolarsResult<Series> {
    match series.dtype() {
        DataType::Date => Ok(series.clone()),
        DataType::Datetime(_, _) => series.cast(&DataType::Date),
        DataType::List(inner) => {
            match inner.as_ref() {
                DataType::Date => Ok(series.clone()),
                DataType::Datetime(_, _) => {
                    // Convert List[Datetime] to List[Date]
                    let list_ca = series.list()?;
                    let converted = list_ca.apply_amortized(|s| {
                        s.as_ref()
                            .cast(&DataType::Date)
                            .unwrap_or_else(|_| s.as_ref().clone())
                    });
                    Ok(converted.into_series())
                }
                _ => Err(PolarsError::ComputeError(
                    format!("Expected Date or Datetime in list, got {}", inner).into(),
                ))
            }
        }
        _ => Err(PolarsError::ComputeError(
            format!("Cannot convert {} to Date type", series.dtype()).into(),
        ))
    }
}
```

### 3. Fix List Length Mismatch Handling

**Current Behavior**: The function silently handles mismatched list lengths (possibly by recycling or truncating).

**Required Behavior**: Should return an error when list lengths don't match.

**Add to `yearfrac_list_list` function**:
```rust
fn yearfrac_list_list(
    start_series: &Series,
    end_series: &Series,
    basis: i32,
) -> PolarsResult<Series> {
    let start_list = start_series.list()?;
    let end_list = end_series.list()?;
    
    // Validate that list lengths match for each row
    for (idx, (start_arr, end_arr)) in start_list.into_iter().zip(end_list.into_iter()).enumerate() {
        if let (Some(s), Some(e)) = (start_arr, end_arr) {
            if s.len() != e.len() {
                return Err(PolarsError::ComputeError(
                    format!(
                        "List length mismatch at row {}: start has {} elements, end has {} elements. Lists must have the same length",
                        idx, s.len(), e.len()
                    ).into(),
                ));
            }
        }
    }
    
    // ... rest of the function
}
```

## Testing Requirements

The following test cases must pass after implementation:

1. **Datetime to Date conversion**: 
   - Input: `datetime(2020, 1, 1, 10, 30)` and `datetime(2020, 7, 1, 15, 45)`
   - Expected: Should work as if dates were `date(2020, 1, 1)` and `date(2020, 7, 1)`

2. **List[Datetime] handling**:
   - Input: Lists containing datetime values
   - Expected: Should convert to List[Date] internally and calculate correctly

3. **Mismatched list lengths**:
   - Input: `List[Date]` with 2 elements and `List[Date]` with 1 element
   - Expected: Should raise error with message containing "must have the same length"

4. **String to Date conversion** (if applicable):
   - Input: String dates in ISO format
   - Expected: Should either convert or provide clear error message

## Implementation Notes

1. The plugin validation happens before the main function runs, so `yearfrac_output_type` MUST accept datetime types
2. Type conversion should be transparent to users - they shouldn't need to manually cast datetime to date
3. Error messages should be clear and actionable
4. Performance impact should be minimal - conversions should only happen when necessary
5. Maintain backward compatibility - existing Date inputs must continue to work

## Definition of Done

- [ ] All datetime input tests pass
- [ ] List[Datetime] inputs are handled correctly  
- [ ] Mismatched list length error is raised appropriately
- [ ] No regression in existing Date-based tests
- [ ] Performance benchmarks show minimal impact
- [ ] Error messages are clear and helpful