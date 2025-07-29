# Step 5: Implement Rust Function

Write the actual Rust implementation following the two-function pattern.

## Input
- Implementation plan from Step 4
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Create the Rust file**:
   ```bash
   touch src/excel/{{function_name}}.rs
   ```

2. **Write the implementation**:
   - Start with imports and constants
   - Define Kwargs structure
   - Implement calculation function
   - Implement Polars interface function
   - Add documentation

3. **Follow the two-function pattern**:
   - Polars interface handles Series/type extraction
   - Calculation function uses pure Rust types

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/05-rust-implementation.rs`:

```rust
// ABOUTME: This file implements the Excel {{FUNCTION_NAME}} function for Polars DataFrames
// ABOUTME: It provides exact compatibility with Excel's {{FUNCTION_NAME}} behavior including edge cases

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

/// Excel {{FUNCTION_NAME}} implementation for Polars
/// 
/// {{Function description from Excel docs}}
/// 
/// # Parameters
/// - `inputs`: Array of Series containing the function parameters
/// - `kwargs`: Optional parameters structure
/// 
/// # Returns
/// Series containing the calculated results
pub fn {{function_name}}(inputs: &[Series], kwargs: &{{FunctionName}}Kwargs) -> PolarsResult<Series> {
    // Implementation here
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

// Helper functions if needed
fn helper_function() -> ReturnType {
    // Helper implementation
}
```

## Implementation Template

Here's a complete template following the pattern:

```rust
// ABOUTME: This file implements the Excel {{FUNCTION_NAME}} function for Polars DataFrames
// ABOUTME: It provides exact compatibility with Excel's {{FUNCTION_NAME}} behavior including edge cases

use polars::prelude::*;
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

/// Excel {{FUNCTION_NAME}} implementation for Polars
/// 
/// {{Detailed function description from Excel documentation}}
/// 
/// # Parameters
/// - `inputs`: Array of Series where:
///   - inputs[0]: {{param1_description}} 
///   - inputs[1]: {{param2_description}}
/// - `kwargs`: Optional parameters including {{optional_params}}
/// 
/// # Returns
/// Series containing {{return_description}}
/// 
/// # Errors
/// Returns PolarsError::ComputeError for:
/// - Invalid parameter count
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

    // Extract typed arrays
    let param1_array = param1_series.{{type_method}}()?;  // e.g., .f64()?, .date()?
    let param2_array = param2_series.{{type_method}}()?;

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

    // Use iterator pattern for performance
    #[allow(clippy::useless_conversion)]
    let result_ca = param1_array
        .into_iter()
        .zip(param2_array.into_iter())
        .map(|(p1_opt, p2_opt)| {
            match (p1_opt, p2_opt) {
                (Some(p1), Some(p2)) => {
                    // Convert types if needed
                    // Call calculation function
                    Some(calculate_{{function_name}}(p1, p2, optional_value))
                }
                _ => None, // Null propagation
            }
        })
        .collect::<Float64Chunked>();  // Adjust type as needed

    Ok(result_ca.with_name("{{function_name}}".into()).into_series())
}

/// Calculate {{FUNCTION_NAME}} for scalar values
/// 
/// This implements Excel's exact {{FUNCTION_NAME}} algorithm
/// 
/// # Special Excel behaviors
/// - {{Document any quirks}}
/// - {{Document edge cases}}
fn calculate_{{function_name}}(
    param1: Type1,
    param2: Type2, 
    optional_param: Type3,
) -> ReturnType {
    // Handle special cases first
    if param1 == 0 {
        return 0.0;  // Example special case
    }

    // Main calculation logic
    let result = match optional_param {
        0 => {
            // Implementation for case 0
        }
        1 => {
            // Implementation for case 1
        }
        _ => unreachable!("Invalid optional_param validated earlier"),
    };

    result
}

// Helper functions as needed
#[inline]
fn helper_function(param: Type) -> ReturnType {
    // Helper implementation
}
```

## Common Patterns

### Date Handling
```rust
use chrono::NaiveDate;

// Convert from Polars date (days since epoch) to NaiveDate
let date = NaiveDate::from_num_days_from_ce_opt(days_value + 719163)
    .ok_or_else(|| PolarsError::ComputeError("Invalid date".into()))?;
```

### Error Handling
```rust
// For mathematical errors
if denominator == 0.0 {
    return Err(PolarsError::ComputeError(
        "Division by zero in {{function_name}}".into(),
    ));
}

// For invalid parameters  
match basis {
    0..=4 => basis,
    _ => return Err(PolarsError::ComputeError(
        format!("Invalid basis: {}. Must be 0-4", basis).into(),
    )),
}
```

### Null Propagation
```rust
// Standard pattern for two parameters
match (p1_opt, p2_opt) {
    (Some(p1), Some(p2)) => Some(calculate_function(p1, p2)),
    _ => None,
}

// For three parameters
match (p1_opt, p2_opt, p3_opt) {
    (Some(p1), Some(p2), Some(p3)) => Some(calculate_function(p1, p2, p3)),
    _ => None,
}
```

### Performance Optimizations
```rust
// Use #[inline] for small functions
#[inline]
fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
}

// Pre-calculate expensive values
const EPOCH_DATE: NaiveDate = NaiveDate::from_ymd_opt(1899, 12, 30).unwrap();
```

## Documentation Standards

1. **File header**: Two ABOUTME lines explaining the file
2. **Function docs**: Full description with parameters and returns
3. **Special behaviors**: Document Excel quirks inline
4. **Error conditions**: List all error cases in function docs

## Next Step

Use the implementation to write comprehensive tests in Step 6.