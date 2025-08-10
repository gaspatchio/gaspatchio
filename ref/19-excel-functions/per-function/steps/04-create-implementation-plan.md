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
   # Check yearfrac.rs for list handling reference
   ```

2. **Determine data types**:
   - Map Excel types to Rust types
   - Consider Polars Series types
   - Plan type conversions for both scalar and list variants
   - Identify which parameters support list operations

3. **Design the implementation**:
   - Output type detection function
   - Kwargs structure for optional parameters
   - Function signatures (main + list handlers)
   - Helper functions needed
   - Constants to define

4. **Plan list support**:
   - Determine if function benefits from array operations
   - Design branching logic for scalar/list combinations
   - Plan broadcasting behavior for mixed inputs
   - Consider memory pre-allocation strategies

5. **Plan error handling**:
   - Map Excel errors to Rust errors
   - Validation strategy for both scalar and list inputs
   - Null handling approach at element and list levels

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/04-implementation-plan.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
implementation_file: "src/excel/{{function_name}}.rs"  # Implementation ONLY
test_file: "src/excel/{{function_name}}_tests.rs"      # Tests ONLY

# File organization
file_organization:
  implementation_contains:
    - "Implementation functions only"
    - "No #[cfg(test)] modules"
    - "Documentation and examples"
  test_file_contains:
    - "All test functions and modules"
    - "#[cfg(test)] at module level"
    - "Imports from implementation: use super::super::{function_name}::*;"

# List support configuration
list_support:
  enabled: true  # Most financial functions should support lists
  supports_broadcasting: true  # Can mix scalar and list inputs
  list_parameters:  # Which parameters can be lists
    - param1
    - param2
  scalar_only_parameters:  # Parameters that must remain scalar
    - basis  # Example: options/flags typically scalar

rust_types:
  # Map each parameter to Rust types (both scalar and list)
  param1:
    excel_type: "number|date|text|logical"
    rust_type: "f64|NaiveDate|String|bool"
    polars_scalar_type: "Float64Chunked|Int32Chunked|StringChunked|BooleanChunked"
    polars_list_type: "ListChunked"  # When used in lists
    extraction_scalar: ".f64()?|.date()?|.str()?|.bool()?"
    extraction_list: ".list()?"
    
return_type:
  rust_type: "f64|String|bool|NaiveDate"
  polars_scalar_type: "Float64Chunked|StringChunked|BooleanChunked|Int32Chunked"
  polars_list_type: "ListChunked"  # When returning lists
  
output_type_function:
  name: "{{function_name}}_output_type"
  logic: |
    - Check input field types
    - If any inputs are lists, determine output list type
    - Handle broadcasting scenarios
    - Return appropriate Field with correct DataType
  
kwargs_structure:
  name: "{{FunctionName}}Kwargs"
  fields:
    - name: "optional_param1"
      type: "Option<i32>"
      default: "None"
      validation: "Must be between 0 and 4"
      list_behavior: "Applied to all elements"  # How it works with lists
      
constants:
  - name: "CONSTANT_NAME"
    type: "f64"
    value: "365.25"
    purpose: "Days in average year"
    
helper_functions:
  - name: "helper_function_name"
    signature: "fn helper_function_name(param: Type) -> ReturnType"
    purpose: "What this helper does"
  - name: "process_{{function_name}}_list_pair"
    signature: "fn process_{{function_name}}_list_pair(list1: &Series, list2: &Series) -> PolarsResult<Series>"
    purpose: "Process paired elements from two lists"
    
implementation_functions:
  - name: "{{function_name}}"
    type: "main_interface"
    purpose: "Entry point with type branching"
    logic:
      - "Validate inputs"
      - "Branch based on input types"
      - "Call appropriate handler"
      
  - name: "{{function_name}}_scalar_columns"
    type: "scalar_handler"
    purpose: "Handle traditional scalar operations"
    
  - name: "{{function_name}}_list_columns"
    type: "list_handler"
    purpose: "Handle list×list operations"
    
  - name: "{{function_name}}_broadcast_first"
    type: "broadcast_handler"
    purpose: "Broadcast scalar first parameter with list second"
    
  - name: "{{function_name}}_broadcast_second"
    type: "broadcast_handler"
    purpose: "Broadcast scalar second parameter with list first"
    
implementation_steps:
  - step: "Output type detection"
    details:
      - "Implement output_type function"
      - "Handle all input type combinations"
      - "Ensure correct list output types"
      
  - step: "Main function branching"
    details:
      - "Check input types"
      - "Route to appropriate handler"
      - "Preserve backward compatibility"
      
  - step: "Scalar implementation"
    details:
      - "Extract existing logic if refactoring"
      - "Maintain exact Excel behavior"
      
  - step: "List implementation"
    details:
      - "Use ListChunked builders"
      - "Process row by row"
      - "Handle nested nulls properly"
      
  - step: "Broadcasting implementation"
    details:
      - "Use first value for scalar broadcasting"
      - "Apply to each list element"
      - "Handle Polars DataFrame scalar behavior"
      
error_mapping:
  "#VALUE!": "PolarsError::ComputeError for type mismatches"
  "#NUM!": "PolarsError::ComputeError for out of range values"
  "#DIV/0!": "PolarsError::ComputeError for division by zero"
  "List length mismatch": "PolarsError::ComputeError when list×list have different lengths"
  
challenges:
  - challenge: "Complex algorithm with lists"
    approach: "Separate list processing logic clearly"
  - challenge: "Memory efficiency with large lists"
    approach: "Pre-allocate builders, avoid intermediate allocations"
  - challenge: "Null handling at multiple levels"
    approach: "Handle list-level nulls and element-level nulls separately"
    
similar_functions:
  - function: "yearfrac"
    reusable_patterns:
      - "Output type detection pattern"
      - "List builder usage"
      - "Broadcasting implementation"
      - "Type branching structure"
      
test_categories:
  - "Normal scalar use cases"
  - "List×list operations"
  - "Broadcasting (scalar×list)"
  - "Null handling (list and element level)"
  - "Edge cases (empty lists, single element)"
  - "Error conditions"
  - "Excel compatibility"
  - "Performance with large lists"
  - "Property-based tests for list operations"
```

## Example Output

For PMT with list support:

```yaml
function_name: PMT
file_path: "src/excel/pmt.rs"

list_support:
  enabled: true
  supports_broadcasting: true
  list_parameters:
    - rate
    - nper
    - pv
    - fv
  scalar_only_parameters:
    - type  # Payment timing is typically consistent

rust_types:
  rate:
    excel_type: "number"
    rust_type: "f64"
    polars_scalar_type: "Float64Chunked"
    polars_list_type: "ListChunked"
    extraction_scalar: ".f64()?"
    extraction_list: ".list()?"
  nper:
    excel_type: "number"
    rust_type: "f64"
    polars_scalar_type: "Float64Chunked"
    polars_list_type: "ListChunked"
    extraction_scalar: ".f64()?"
    extraction_list: ".list()?"
  pv:
    excel_type: "number"
    rust_type: "f64"
    polars_scalar_type: "Float64Chunked"
    polars_list_type: "ListChunked"
    extraction_scalar: ".f64()?"
    extraction_list: ".list()?"
    
return_type:
  rust_type: "f64"
  polars_scalar_type: "Float64Chunked"
  polars_list_type: "ListChunked"
  
output_type_function:
  name: "pmt_output_type"
  logic: |
    - Check if any of rate, nper, pv, fv are lists
    - If yes, return List(Float64)
    - Otherwise return Float64
  
implementation_functions:
  - name: "pmt"
    type: "main_interface"
    logic:
      - "Extract rate, nper, pv series"
      - "Check optional fv, type parameters"
      - "Branch on input types"
      
  - name: "pmt_scalar_columns"
    type: "scalar_handler"
    purpose: "Original PMT logic for scalars"
    
  - name: "pmt_list_columns"
    type: "list_handler"
    purpose: "Process lists of payment parameters"
    note: "Common for projecting payment schedules"
    
  - name: "pmt_broadcast_rate"
    type: "broadcast_handler"
    purpose: "Fixed rate, varying terms/amounts"
    
# ... rest of plan
```

## Implementation Patterns for Lists

1. **Output Type Detection**: Always implement to handle all type combinations
2. **Main Function Pattern**: Type checking and branching to handlers
3. **List Builder Pattern**: Pre-allocate with estimated capacity
4. **Broadcasting Pattern**: Use first value, apply to all list elements
5. **Null Handling**: List-level (entire row) vs element-level (within list)

## Performance Checklist for Lists

- [ ] Pre-allocate list builders with reasonable capacity
- [ ] Avoid converting between Series and arrays repeatedly
- [ ] Use iterator chains where possible
- [ ] Consider chunking for very large lists
- [ ] Test with realistic actuarial data (120-element lists)

## Next Step

Use this plan to implement the Rust function with list support in Step 5.