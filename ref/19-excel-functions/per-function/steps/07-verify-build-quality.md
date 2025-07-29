# Step 7: Verify Build and Quality

Run quality checks to ensure the implementation meets standards.

## Input
- Implementation from Step 5
- Tests from Step 6
- Function name: `{{FUNCTION_NAME}}`

## Process

Run the following commands and fix any issues:

1. **Format the code**:
   ```bash
   cargo fmt
   ```

2. **Run clippy with pedantic lints**:
   ```bash
   cargo clippy --pedantic
   ```

3. **Run tests for your function**:
   ```bash
   cargo test {{function_name}} --lib
   ```

4. **Check for common issues**:
   - Unused imports
   - Missing documentation
   - Inefficient patterns
   - Missing error handling

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/07-quality-report.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
quality_checks:
  cargo_fmt:
    status: "pass|fail"
    changes_made: []
    
  cargo_clippy:
    status: "pass|fail" 
    warnings: []
    errors: []
    fixed: []
    
  cargo_test:
    status: "pass|fail"
    tests_run: 15
    tests_passed: 15
    failures: []
    
  documentation:
    file_header: "present|missing"
    function_docs: "complete|incomplete"
    parameter_docs: "complete|incomplete"
    example_docs: "present|missing"
    
  code_patterns:
    two_function_pattern: "followed|not followed"
    iterator_usage: "optimal|suboptimal"
    error_handling: "complete|incomplete"
    null_propagation: "correct|incorrect"
    
issues_fixed:
  - "Added #[allow(clippy::useless_conversion)] for iterator"
  - "Fixed missing documentation on helper function"
  - "Improved error message clarity"
  
remaining_issues:
  - "None"
```

## Common Clippy Warnings and Fixes

### 1. Useless Conversion
```rust
// Warning: useless conversion to the same type
#[allow(clippy::useless_conversion)]
let result_ca = param1_array
    .into_iter()  // This is actually needed for Polars
```

### 2. Missing Documentation
```rust
// Fix: Add documentation
/// Helper function to calculate day difference using 30/360 convention
fn days_360_us(start: NaiveDate, end: NaiveDate) -> i32 {
```

### 3. Too Many Arguments
```rust
// Consider using a struct for many parameters
struct CalculationParams {
    value: f64,
    rate: f64,
    periods: i32,
}
```

### 4. Floating Point Comparisons
```rust
// Use epsilon comparison for floats
if (value - 0.0).abs() < f64::EPSILON {
    // Handle zero case
}
```

## Documentation Checklist

### File Header
```rust
// ABOUTME: This file implements the Excel {{FUNCTION_NAME}} function for Polars DataFrames
// ABOUTME: It provides exact compatibility with Excel's {{FUNCTION_NAME}} behavior including edge cases
```

### Function Documentation
```rust
/// Excel {{FUNCTION_NAME}} implementation for Polars
/// 
/// Calculates {{what it calculates}}
/// 
/// # Parameters
/// - `inputs`: Array of Series where:
///   - inputs[0]: {{description}} (required)
///   - inputs[1]: {{description}} (required)
/// - `kwargs`: Optional parameters:
///   - `param_name`: {{description}} (default: {{default}})
/// 
/// # Returns
/// Series containing {{description of results}}
/// 
/// # Errors
/// Returns `PolarsError::ComputeError` when:
/// - Insufficient parameters provided
/// - {{Other error conditions}}
/// 
/// # Excel Compatibility
/// Matches Excel's {{FUNCTION_NAME}} behavior including:
/// - {{Quirk 1}}
/// - {{Quirk 2}}
```

### Test Documentation
```rust
#[test]
fn test_excel_known_outputs() {
    // Test against actual Excel outputs
    // These values were verified in Excel 365
```

## Performance Review

Check for:
1. **Constants defined at module level**
2. **No allocations in hot loops**
3. **Appropriate use of `#[inline]`**
4. **Iterator chains instead of manual loops**
5. **Efficient null checking patterns**

## Final Quality Checklist

- [ ] Code is formatted with `cargo fmt`
- [ ] No clippy warnings (or justified with `#[allow()]`)
- [ ] All tests pass
- [ ] Documentation is complete
- [ ] Error messages are descriptive
- [ ] Performance considerations addressed
- [ ] Excel compatibility documented
- [ ] Two-function pattern followed

## Example Quality Report

```yaml
function_name: YEARFRAC
quality_checks:
  cargo_fmt:
    status: "pass"
    changes_made: []
    
  cargo_clippy:
    status: "pass"
    warnings: []
    errors: []
    fixed:
      - "Added #[allow(clippy::useless_conversion)] for Polars iterator"
      - "Fixed missing docs on days_360_us helper"
    
  cargo_test:
    status: "pass"
    tests_run: 25
    tests_passed: 25
    failures: []
    
  documentation:
    file_header: "present"
    function_docs: "complete"
    parameter_docs: "complete"
    example_docs: "present"
    
  code_patterns:
    two_function_pattern: "followed"
    iterator_usage: "optimal"
    error_handling: "complete"
    null_propagation: "correct"
    
issues_fixed:
  - "Added allow directive for necessary type conversion"
  - "Documented all public functions"
  - "Improved basis validation error message"
  
remaining_issues:
  - "None"
```

## Next Step

Update module exports in Step 8.