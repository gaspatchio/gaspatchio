# Step 2: Analyze Excel Documentation

Break down the Excel documentation into key components for implementation.

## Input
- Function name: `{{FUNCTION_NAME}}`
- Learnings from Step 1

## Process

1. **Access Excel documentation**:
   - Function list: https://support.microsoft.com/en-us/office/excel-functions-alphabetical-b3944572-255d-4efb-bb96-c6d90033e188
   - Specific function: Search for your function's documentation
   - Example for YEARFRAC: https://support.microsoft.com/en-us/office/yearfrac-function-3844141e-c76d-4143-82b6-208454ddc6a8

2. **Extract key information**:
   - Function purpose and description
   - Syntax and parameters
   - Return value type
   - Examples from documentation
   - Related functions

3. **Parameter analysis**:
   - Required vs optional parameters
   - Parameter types and constraints
   - Default values for optional parameters
   - Parameter validation rules

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/02-excel-documentation.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
excel_category: "Financial|Date & Time|Math & Trig|Statistical|Text|Logical|Lookup & Reference|Information"
purpose: |
  Brief description of what the function does
syntax: "FUNCTION_NAME(required1, required2, [optional1], [optional2])"
parameters:
  - name: required1
    type: number|text|date|logical|any
    required: true
    description: "What this parameter represents"
    constraints:
      - "Must be positive"
      - "Cannot be zero"
  - name: optional1
    type: number|text|date|logical|any
    required: false
    default: "default value"
    description: "What this parameter represents"
    valid_values: [0, 1, 2, 3, 4]  # If limited set
return_value:
  type: number|text|date|logical|array
  description: "What the function returns"
  special_cases:
    - condition: "When X happens"
      result: "Returns Y"
examples:
  - formula: "=FUNCTION_NAME(A1, B1)"
    description: "Basic usage"
    expected_result: "42"
  - formula: "=FUNCTION_NAME(100, 0.05, 12)"
    description: "With optional parameter"
    expected_result: "5.127"
related_functions:
  - "RELATED1: How it's related"
  - "RELATED2: How it's related"
notes: |
  Any special notes or warnings from the documentation
excel_version_notes: |
  If the function behavior changed across Excel versions
```

## Example Output

For YEARFRAC function:

```yaml
function_name: YEARFRAC
excel_category: "Date & Time"
purpose: |
  Calculates the year fraction representing the number of whole days between
  start_date and end_date based on different day count conventions
syntax: "YEARFRAC(start_date, end_date, [basis])"
parameters:
  - name: start_date
    type: date
    required: true
    description: "The starting date"
    constraints:
      - "Must be a valid Excel date"
  - name: end_date
    type: date
    required: true
    description: "The ending date"
    constraints:
      - "Must be a valid Excel date"
  - name: basis
    type: number
    required: false
    default: 0
    description: "The day count basis to use"
    valid_values: [0, 1, 2, 3, 4]
    value_meanings:
      0: "US (NASD) 30/360"
      1: "Actual/actual"
      2: "Actual/360"
      3: "Actual/365"
      4: "European 30/360"
return_value:
  type: number
  description: "The year fraction between the two dates"
  special_cases:
    - condition: "When start_date > end_date"
      result: "Returns negative value"
    - condition: "When dates are equal"
      result: "Returns 0"
examples:
  - formula: "=YEARFRAC(DATE(2012,1,1),DATE(2012,7,30))"
    description: "Basic usage with default basis"
    expected_result: "0.58055556"
  - formula: "=YEARFRAC(DATE(2012,1,1),DATE(2012,7,30),3)"
    description: "Using Actual/365 basis"
    expected_result: "0.57808219"
related_functions:
  - "DATEDIF: Calculates date differences in years, months, or days"
  - "DAYS360: Calculates days between dates using 360-day year"
notes: |
  The basis parameter significantly affects the calculation result.
  Different basis values are used in different financial contexts.
excel_version_notes: |
  Available in all modern Excel versions. Basis parameter behavior
  is consistent across versions.
```

## Documentation Sources Priority

1. **Official Microsoft documentation** (primary source)
2. **Excel function reference guides**
3. **Financial/domain-specific documentation** (for context)
4. **Excel community forums** (for undocumented behavior)

## Key Questions to Answer

1. What is the exact formula/algorithm used?
2. Are there any undocumented behaviors?
3. How does Excel handle edge cases?
4. What are the performance characteristics?
5. Are there platform-specific differences?

## Next Step

Use this documentation analysis to research actual Excel behavior in Step 3.