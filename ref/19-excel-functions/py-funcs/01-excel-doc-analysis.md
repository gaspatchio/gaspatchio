# Step 1: Excel Documentation Analysis

You are analyzing Excel function documentation to extract key information needed for implementation.

## Input

```
FUNCTION_NAME: {{FUNCTION_NAME}}
```

## Task

1. Look at the Excel documentation for {{FUNCTION_NAME}}:
   - FUNCTION LIST: https://support.microsoft.com/en-us/office/excel-functions-alphabetical-b3944572-255d-4efb-bb96-c6d90033e188
   - Find the specific function documentation page

2. Extract and structure the following information:
   - Function purpose (one paragraph)
   - Parameters (name, type, required/optional, description)
   - Return value type and description
   - Special cases or notes
   - Common use cases

3. Pay special attention to:
   - Whether parameters can be scalars, vectors, or both
   - Default values for optional parameters
   - Error conditions

## Output Format

```yaml
function_name: {{FUNCTION_NAME}}
purpose: |
  [Clear description of what the function does]

parameters:
  - name: param1
    type: [number/date/boolean/text]
    required: [true/false]
    accepts: [scalar/vector/both]
    description: |
      [What this parameter represents]
    
  - name: param2
    type: [number/date/boolean/text]
    required: [true/false]
    accepts: [scalar/vector/both]
    default: [default value if optional]
    description: |
      [What this parameter represents]

return_value:
  type: [number/date/boolean/text]
  description: |
    [What the function returns]

special_cases:
  - [Any special behavior or edge cases]
  - [Error conditions]

use_cases:
  - [Common scenario 1]
  - [Common scenario 2]

excel_doc_url: [URL to the specific function documentation]
```

## Example Output

```yaml
function_name: YEARFRAC
purpose: |
  Calculates the fraction of a year between two dates based on different day count conventions.

parameters:
  - name: start_date
    type: date
    required: true
    accepts: both
    description: |
      The starting date for the calculation
    
  - name: end_date
    type: date
    required: true
    accepts: both
    description: |
      The ending date for the calculation
      
  - name: basis
    type: number
    required: false
    accepts: both
    default: 0
    description: |
      Day count basis to use (0-4)

return_value:
  type: number
  description: |
    The year fraction between the two dates

special_cases:
  - If start_date > end_date, returns negative value
  - Invalid basis values cause #NUM! error

use_cases:
  - Calculating accrued interest
  - Determining fractional periods for financial calculations

excel_doc_url: https://support.microsoft.com/en-us/office/yearfrac-function-3844141e-c76d-4143-82b6-208454ddc6a8
```