# Step 5: Implement Rust Function

Write the actual Rust implementation following the extended pattern with list support.

## Input
- Implementation plan from Step 4
- Function name: `{{FUNCTION_NAME}}`
- Reference implementation: yearfrac.rs for list patterns

## Process

1. **Create the Rust file**:
   ```bash
   touch src/excel/{{function_name}}.rs
   ```

2. **Write the implementation**:
   - Start with imports and constants
   - Define Kwargs structure
   - Implement output type function
   - Implement calculation function
   - Implement Polars interface with branching
   - Implement list handler functions
   - Add documentation

3. **Follow the extended pattern**:
   - Output type detection for scalar/list inputs
   - Main interface branches on input types
   - Separate handlers for each scenario
   - Broadcasting support for mixed inputs

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/05-rust-implementation.rs`:

```rust
// ABOUTME: This file implements the Excel {{FUNCTION_NAME}} function for Polars DataFrames
// ABOUTME: It provides exact compatibility with Excel's {{FUNCTION_NAME}} behavior including edge cases and list support

use chrono::NaiveDate;
use polars::prelude::*;
use serde::Deserialize;

// Constants
const CONSTANT_NAME: f64 = 365.25;

/// Kwargs structure for optional parameters
#[derive(Deserialize, Clone)]
pub struct {{FunctionName}}Kwargs {
    pub optional_param: Option<i32>,
}

/// Determine output type based on input types for {{FUNCTION_NAME}}
/// 
/// Handles scalar and list column inputs with appropriate output types
pub fn {{function_name}}_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    // Implementation here
}

/// Excel {{FUNCTION_NAME}} implementation for Polars
/// 
/// {{Function description from Excel docs}}
/// 
/// Supports both scalar and list column operations for actuarial projections.
/// 
/// # Parameters
/// - `inputs`: Array of Series containing the function parameters
/// - `kwargs`: Optional parameters structure
/// 
/// # Returns
/// Series containing the calculated results (scalar or list)
pub fn {{function_name}}(inputs: &[Series], kwargs: &{{FunctionName}}Kwargs) -> PolarsResult<Series> {
    // Implementation with type branching
}

/// Calculate {{FUNCTION_NAME}} for scalar values
/// 
/// This implements Excel's exact algorithm for {{FUNCTION_NAME}}
fn calculate_{{function_name}}(
    param1: Type1,
    param2: Type2,
    optional: Type3,
) -> ReturnType {
    // Pure calculation logic
}
```

## Complete Implementation Template with List Support

Here's a comprehensive template following the yearfrac pattern:

```rust
// ABOUTME: This file implements the Excel {{FUNCTION_NAME}} function for Polars DataFrames
// ABOUTME: It provides exact compatibility with Excel's {{FUNCTION_NAME}} behavior including edge cases and list support

use polars::prelude::*;
use polars_core::prelude::{DataType, Field};
use serde::Deserialize;
// Add other imports as needed (chrono::NaiveDate, etc.)

// Define constants at module level
const CONSTANT_NAME: f64 = 365.25;

/// Kwargs structure for {{FUNCTION_NAME}} optional parameters
#[derive(Deserialize, Clone)]
pub struct {{FunctionName}}Kwargs {
    /// Optional parameter description
    pub optional_param: Option<i32>,
}

/// Determine output type based on input types for {{FUNCTION_NAME}}
/// 
/// This function inspects the input field types and determines whether the output
/// should be a scalar or list type based on Excel 365 dynamic array behavior.
pub fn {{function_name}}_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    // Validate we have the minimum required inputs
    if input_fields.len() < 2 {
        return Err(PolarsError::ComputeError(
            "{{function_name}} requires at least 2 parameters".into()
        ));
    }

    let param1_dtype = &input_fields[0].dtype();
    let param2_dtype = &input_fields[1].dtype();
    
    match (param1_dtype, param2_dtype) {
        // Both inputs are list columns
        (DataType::List(inner1), DataType::List(inner2)) => {
            // Validate inner types
            if !matches!(**inner1, DataType::Float64) || !matches!(**inner2, DataType::Float64) {
                return Err(PolarsError::ComputeError(
                    "List columns must contain Float64 type for {{function_name}}".into()
                ));
            }
            Ok(Field::new("{{function_name}}".into(), DataType::List(Box::new(DataType::Float64))))
        }
        // Standard scalar case
        (DataType::Float64, DataType::Float64) => {
            Ok(Field::new("{{function_name}}".into(), DataType::Float64))
        }
        // Mixed scalar/list case - broadcast scalar to match list
        (DataType::Float64, DataType::List(inner)) if matches!(**inner, DataType::Float64) => {
            Ok(Field::new("{{function_name}}".into(), DataType::List(Box::new(DataType::Float64))))
        }
        (DataType::List(inner), DataType::Float64) if matches!(**inner, DataType::Float64) => {
            Ok(Field::new("{{function_name}}".into(), DataType::List(Box::new(DataType::Float64))))
        }
        // Error cases
        _ => Err(PolarsError::ComputeError(
            "{{function_name}} requires Float64 or List<Float64> types".into()
        ))
    }
}

/// Excel {{FUNCTION_NAME}} implementation for Polars
/// 
/// {{Detailed function description from Excel documentation}}
/// 
/// Supports both scalar and list column operations for actuarial projections:
/// - Scalar×Scalar: Traditional single-value calculation
/// - List×List: Element-wise calculation for projection arrays
/// - Scalar×List: Broadcasting scalar to all list elements
/// - List×Scalar: Broadcasting scalar to all list elements
/// 
/// # Parameters
/// - `inputs`: Array of Series where:
///   - inputs[0]: {{param1_description}} (Float64 or List<Float64>)
///   - inputs[1]: {{param2_description}} (Float64 or List<Float64>)
/// - `kwargs`: Optional parameters including {{optional_params}}
/// 
/// # Returns
/// Series containing {{return_description}} (Float64 or List<Float64>)
/// 
/// # Errors
/// Returns PolarsError::ComputeError for:
/// - Invalid parameter count
/// - Type mismatches
/// - {{Other error conditions}}
pub fn {{function_name}}(inputs: &[Series], kwargs: &{{FunctionName}}Kwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "{{function_name}} requires at least 2 parameters".into(),
        ));
    }

    // Extract input series
    let param1_series = &inputs[0];
    let param2_series = &inputs[1];

    // Process optional parameters
    let optional_value = kwargs.optional_param.unwrap_or(0);
    
    // Validate optional parameter
    if let Some(val) = kwargs.optional_param {
        if val < 0 || val > 4 {  // Adjust range as needed
            return Err(PolarsError::ComputeError(
                format!("Invalid optional_param value: {}. Must be 0-4", val).into(),
            ));
        }
    }

    // Branch based on input types
    match (param1_series.dtype(), param2_series.dtype()) {
        (DataType::List(_), DataType::List(_)) => {
            {{function_name}}_list_columns(param1_series, param2_series, optional_value)
        }
        (DataType::Float64, DataType::Float64) => {
            {{function_name}}_scalar_columns(param1_series, param2_series, optional_value)
        }
        (DataType::Float64, DataType::List(_)) => {
            // Broadcast scalar param1 to match list param2
            {{function_name}}_broadcast_first(param1_series, param2_series, optional_value)
        }
        (DataType::List(_), DataType::Float64) => {
            // Broadcast scalar param2 to match list param1
            {{function_name}}_broadcast_second(param1_series, param2_series, optional_value)
        }
        _ => Err(PolarsError::ComputeError(
            "Invalid input types for {{function_name}}".into()
        ))
    }
}

/// Process scalar columns (traditional behavior)
fn {{function_name}}_scalar_columns(
    param1_series: &Series,
    param2_series: &Series,
    optional_param: i32
) -> PolarsResult<Series> {
    // Extract typed arrays
    let param1_array = param1_series.f64()?;
    let param2_array = param2_series.f64()?;

    // Use iterator pattern for performance
    #[allow(clippy::useless_conversion)]
    let result_ca = param1_array
        .into_iter()
        .zip(param2_array.into_iter())
        .map(|(p1_opt, p2_opt)| {
            match (p1_opt, p2_opt) {
                (Some(p1), Some(p2)) => {
                    Some(calculate_{{function_name}}(p1, p2, optional_param))
                }
                _ => None, // Null propagation
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("{{function_name}}".into()).into_series())
}

/// Process list columns (element-wise operations)
fn {{function_name}}_list_columns(
    param1_series: &Series,
    param2_series: &Series,
    optional_param: i32
) -> PolarsResult<Series> {
    let param1_lists = param1_series.list()?;
    let param2_lists = param2_series.list()?;
    
    // Ensure both series have the same length
    if param1_lists.len() != param2_lists.len() {
        return Err(PolarsError::ComputeError(
            "Input series must have the same length".into()
        ));
    }
    
    // Process each row (list pair)
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "{{function_name}}".into(),
        param1_lists.len(),
        param1_lists.len() * 10, // Estimate capacity
        DataType::Float64
    );
    
    for (list1_opt, list2_opt) in param1_lists.into_iter().zip(param2_lists.into_iter()) {
        match (list1_opt, list2_opt) {
            (Some(arr1), Some(arr2)) => {
                // Convert arrays to series for processing
                let series1 = Series::from_arrow("".into(), arr1).unwrap();
                let series2 = Series::from_arrow("".into(), arr2).unwrap();
                
                // Process this list pair
                let result_values = process_{{function_name}}_list_pair(
                    &series1, 
                    &series2, 
                    optional_param
                )?;
                
                // Append to builder
                if let Ok(values) = result_values.f64() {
                    if let Ok(slice) = values.cont_slice() {
                        builder.append_slice(slice);
                    } else {
                        // Handle non-contiguous case
                        for val in values.into_iter() {
                            builder.append_option(val);
                        }
                    }
                }
            }
            _ => {
                // One or both lists are null
                builder.append_null();
            }
        }
    }
    
    Ok(builder.finish().into_series())
}

/// Process paired elements from two lists
fn process_{{function_name}}_list_pair(
    list1: &Series,
    list2: &Series,
    optional_param: i32
) -> PolarsResult<Series> {
    // Ensure lists have same length
    if list1.len() != list2.len() {
        return Err(PolarsError::ComputeError(
            "Lists must have the same length".into()
        ));
    }
    
    let values1 = list1.f64()?;
    let values2 = list2.f64()?;
    
    // Process each value pair in the lists
    let results: Float64Chunked = values1
        .into_iter()
        .zip(values2.into_iter())
        .map(|(v1_opt, v2_opt)| {
            match (v1_opt, v2_opt) {
                (Some(v1), Some(v2)) => {
                    Some(calculate_{{function_name}}(v1, v2, optional_param))
                }
                _ => None,
            }
        })
        .collect();
    
    Ok(results.into_series())
}

/// Broadcast scalar first parameter to match list second parameter
fn {{function_name}}_broadcast_first(
    param1_series: &Series,  // Scalar Float64
    param2_series: &Series,  // List<Float64>
    optional_param: i32
) -> PolarsResult<Series> {
    // Get the scalar value (use first value for broadcasting)
    let param1_ca = param1_series.f64()?;
    let param1_opt = param1_ca.get(0);
    
    // Get the list of param2 values
    let param2_lists = param2_series.list()?;
    
    // Process each list with the scalar param1
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "{{function_name}}".into(),
        param2_lists.len(),
        param2_lists.len() * 10,
        DataType::Float64
    );
    
    for list2_opt in param2_lists.into_iter() {
        match (param1_opt, list2_opt) {
            (Some(p1), Some(arr2)) => {
                // Process all values in this list with scalar p1
                let series2 = Series::from_arrow("".into(), arr2).unwrap();
                let values2 = series2.f64()?;
                
                let results: Vec<f64> = values2
                    .into_iter()
                    .map(|v2_opt| {
                        match v2_opt {
                            Some(v2) => {
                                calculate_{{function_name}}(p1, v2, optional_param)
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

/// Broadcast scalar second parameter to match list first parameter
fn {{function_name}}_broadcast_second(
    param1_series: &Series,  // List<Float64>
    param2_series: &Series,  // Scalar Float64
    optional_param: i32
) -> PolarsResult<Series> {
    // Get the list of param1 values
    let param1_lists = param1_series.list()?;
    
    // Get the scalar value (use first value for broadcasting)
    let param2_ca = param2_series.f64()?;
    let param2_opt = param2_ca.get(0);
    
    // Process each list with the scalar param2
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        "{{function_name}}".into(),
        param1_lists.len(),
        param1_lists.len() * 10,
        DataType::Float64
    );
    
    for list1_opt in param1_lists.into_iter() {
        match (list1_opt, param2_opt) {
            (Some(arr1), Some(p2)) => {
                // Process all values in this list with scalar p2
                let series1 = Series::from_arrow("".into(), arr1).unwrap();
                let values1 = series1.f64()?;
                
                let results: Vec<f64> = values1
                    .into_iter()
                    .map(|v1_opt| {
                        match v1_opt {
                            Some(v1) => {
                                calculate_{{function_name}}(v1, p2, optional_param)
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

/// Calculate {{FUNCTION_NAME}} for scalar values
/// 
/// This implements Excel's exact {{FUNCTION_NAME}} algorithm
/// 
/// # Special Excel behaviors
/// - {{Document any quirks}}
/// - {{Document edge cases}}
fn calculate_{{function_name}}(
    param1: f64,
    param2: f64, 
    optional_param: i32,
) -> f64 {
    // Handle special cases first
    if param1 == 0.0 {
        return 0.0;  // Example special case
    }

    // Main calculation logic
    let result = match optional_param {
        0 => {
            // Implementation for case 0
            param1 * param2
        }
        1 => {
            // Implementation for case 1
            param1 + param2
        }
        _ => unreachable!("Invalid optional_param validated earlier"),
    };

    result
}

// Helper functions as needed
#[inline]
fn helper_function(param: f64) -> f64 {
    // Helper implementation
    param
}
```

## Common Patterns

### Date Handling with Lists
```rust
// For date-based functions, adapt the pattern:
use chrono::NaiveDate;

// In output type detection:
match (start_dtype, end_dtype) {
    (DataType::List(inner1), DataType::List(inner2)) => {
        if !matches!(**inner1, DataType::Date) || !matches!(**inner2, DataType::Date) {
            return Err(PolarsError::ComputeError(
                "List columns must contain Date type".into()
            ));
        }
        Ok(Field::new("result".into(), DataType::List(Box::new(DataType::Float64))))
    }
    // ...
}

// Convert days to dates in list processing:
let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
let date = epoch + chrono::Duration::days(i64::from(days));
```

### Error Handling
```rust
// For mathematical errors
if denominator == 0.0 {
    return Err(PolarsError::ComputeError(
        "Division by zero in {{function_name}}".into(),
    ));
}

// For list length mismatches
if list1.len() != list2.len() {
    return Err(PolarsError::ComputeError(
        format!("List length mismatch: {} vs {}", list1.len(), list2.len()).into()
    ));
}
```

### Performance Optimizations
```rust
// Pre-allocate builders with reasonable capacity
let estimated_capacity = lists.len() * average_list_length;
let mut builder = ListPrimitiveChunkedBuilder::new(
    "result".into(),
    lists.len(),
    estimated_capacity,
    DataType::Float64
);

// Use cont_slice() when possible to avoid iteration
if let Ok(slice) = values.cont_slice() {
    builder.append_slice(slice);
} else {
    // Fallback for non-contiguous data
    for val in values.into_iter() {
        builder.append_option(val);
    }
}
```

## Documentation Standards

1. **File header**: Two ABOUTME lines explaining the file
2. **Function docs**: Full description with list support details
3. **Output type function**: Document the type detection logic
4. **Special behaviors**: Document Excel quirks inline
5. **List operations**: Explain broadcasting behavior

## Testing Considerations

When implementing, consider these test scenarios:
1. Scalar operations (backward compatibility)
2. List×List with same lengths
3. List×List with different lengths (should error)
4. Scalar×List broadcasting
5. List×Scalar broadcasting
6. Empty lists
7. Lists with nulls
8. Single-element lists
9. Large lists (120+ elements for actuarial)

## Next Step

Use the implementation to write comprehensive tests in Step 6.