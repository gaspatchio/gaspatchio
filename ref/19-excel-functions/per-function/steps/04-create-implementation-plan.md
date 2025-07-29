# Step 4: Create Implementation Plan

Make a detailed plan for the Rust implementation based on all previous analysis.

## Input
- Learnings from Step 1
- Documentation from Step 2
- Behavior analysis from Step 3
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Review existing implementations**:
   ```bash
   ls src/excel/
   # Look at similar functions for patterns
   ```

2. **Determine data types**:
   - Map Excel types to Rust types
   - Consider Polars Series types
   - Plan type conversions

3. **Design the implementation**:
   - Kwargs structure for optional parameters
   - Function signatures
   - Helper functions needed
   - Constants to define

4. **Plan error handling**:
   - Map Excel errors to Rust errors
   - Validation strategy
   - Null handling approach

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/04-implementation-plan.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
file_path: "src/excel/{{function_name}}.rs"

rust_types:
  # Map each parameter to Rust types
  param1:
    excel_type: "number|date|text|logical"
    rust_type: "f64|NaiveDate|String|bool"
    polars_type: "Float64Chunked|Int32Chunked|StringChunked|BooleanChunked"
    extraction: ".f64()?|.date()?|.str()?|.bool()?"
    
return_type:
  rust_type: "f64|String|bool|NaiveDate"
  polars_type: "Float64Chunked|StringChunked|BooleanChunked|Int32Chunked"
  
kwargs_structure:
  name: "{{FunctionName}}Kwargs"
  fields:
    - name: "optional_param1"
      type: "Option<i32>"
      default: "None"
      validation: "Must be between 0 and 4"
      
constants:
  - name: "CONSTANT_NAME"
    type: "f64"
    value: "365.25"
    purpose: "Days in average year"
    
helper_functions:
  - name: "helper_function_name"
    signature: "fn helper_function_name(param: Type) -> ReturnType"
    purpose: "What this helper does"
    
implementation_steps:
  - step: "Validate inputs"
    details:
      - "Check parameter count"
      - "Validate optional parameter range"
  - step: "Extract and convert parameters"
    details:
      - "Get typed arrays from Series"
      - "Handle type conversions"
  - step: "Implement core algorithm"
    details:
      - "Specific calculation steps"
      - "Handle special cases"
  - step: "Handle edge cases"
    details:
      - "Zero handling"
      - "Negative handling"
      - "Error conditions"
      
error_mapping:
  "#VALUE!": "PolarsError::ComputeError for type mismatches"
  "#NUM!": "PolarsError::ComputeError for out of range values"
  "#DIV/0!": "PolarsError::ComputeError for division by zero"
  
challenges:
  - challenge: "Complex algorithm"
    approach: "Break into smaller functions"
  - challenge: "Performance with large datasets"
    approach: "Use iterator pattern, avoid allocations"
    
similar_functions:
  - function: "existing_function"
    reusable_code:
      - "Date conversion logic"
      - "Error handling pattern"
      
test_categories:
  - "Normal use cases"
  - "Edge cases (zero, negative)"
  - "Error conditions"
  - "Excel compatibility"
  - "Performance benchmarks"
```

## Example Output

For YEARFRAC:

```yaml
function_name: YEARFRAC
file_path: "src/excel/yearfrac.rs"

rust_types:
  start_date:
    excel_type: "date"
    rust_type: "NaiveDate"
    polars_type: "Int32Chunked"
    extraction: ".date()?"
  end_date:
    excel_type: "date"
    rust_type: "NaiveDate"
    polars_type: "Int32Chunked"
    extraction: ".date()?"
  basis:
    excel_type: "number"
    rust_type: "i32"
    polars_type: "Int32Chunked"
    extraction: ".i32()?"
    
return_type:
  rust_type: "f64"
  polars_type: "Float64Chunked"
  
kwargs_structure:
  name: "YearFracKwargs"
  fields:
    - name: "basis"
      type: "Option<i32>"
      default: "None"
      validation: "Must be 0, 1, 2, 3, or 4"
      
constants:
  - name: "DAYS_PER_YEAR_360"
    type: "f64"
    value: "360.0"
    purpose: "Days in 360-day year"
  - name: "DAYS_PER_YEAR_365"
    type: "f64"
    value: "365.0"
    purpose: "Days in 365-day year"
    
helper_functions:
  - name: "days_360_us"
    signature: "fn days_360_us(start: NaiveDate, end: NaiveDate) -> i32"
    purpose: "Calculate days using US 30/360 convention"
  - name: "days_360_eu"
    signature: "fn days_360_eu(start: NaiveDate, end: NaiveDate) -> i32"
    purpose: "Calculate days using European 30/360 convention"
    
implementation_steps:
  - step: "Extract and validate parameters"
    details:
      - "Get date arrays from first two Series"
      - "Get basis from kwargs, default to 0"
      - "Validate basis is 0-4"
  - step: "Handle date ordering"
    details:
      - "Check if start > end for negative result"
      - "Normalize dates for calculation"
  - step: "Calculate based on basis"
    details:
      - "Switch on basis value"
      - "Apply appropriate day count convention"
      - "Divide by year basis"
  - step: "Apply sign based on date order"
    details:
      - "Negate if original start > end"
      
error_mapping:
  "#NUM!": "Basis value not in range 0-4"
  "#VALUE!": "Invalid date values"
  
challenges:
  - challenge: "Complex day count conventions"
    approach: "Implement separate helper for each convention"
  - challenge: "1900 leap year bug"
    approach: "Document behavior, match Excel exactly"
  - challenge: "Month-end handling for 30/360"
    approach: "Implement Excel's specific rules"
    
similar_functions:
  - function: "DAYS360"
    reusable_code:
      - "30/360 day count logic"
      - "Month-end adjustment rules"
      
test_categories:
  - "All 5 basis values"
  - "Same year vs different years"
  - "Leap year handling"
  - "Start > end (negative results)"
  - "Month-end special cases"
  - "1900 dates (leap year bug)"
  - "Large date ranges"
```

## Implementation Patterns

1. **Two-function pattern**: Always separate Polars interface from calculation
2. **Iterator pattern**: Use `.into_iter()` with `.collect::<ChunkedArray>()`
3. **Null propagation**: Match on `(Some(a), Some(b))` pattern
4. **Constants**: Define at module level for performance
5. **Helper functions**: Keep pure and testable

## Performance Checklist

- [ ] Constants defined outside functions
- [ ] No unnecessary allocations in loops
- [ ] `#[inline]` on small helpers
- [ ] Iterator chains instead of loops where possible
- [ ] Appropriate chunked array types

## Next Step

Use this plan to implement the Rust function in Step 5.