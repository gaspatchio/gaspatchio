# Step 1: Analyze Excel Documentation

## Input
- `FUNCTION_NAME`: The name of the Excel function to integrate

## Task
Break down the Excel documentation for {{FUNCTION_NAME}} into key components.

### Actions
1. Look at the Excel documentation:
   - FUNCTION LIST: https://support.microsoft.com/en-us/office/excel-functions-alphabetical-b3944572-255d-4efb-bb96-c6d90033e188
   - SPECIFIC FUNCTION: Search for the function in the list above

2. Extract and document:
   - Function purpose
   - Parameters (names, types, optional/required)
   - Return value type
   - Special cases
   - Default values for optional parameters

## Output
Save the structured analysis to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/01-excel-analysis.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
purpose: |
  Brief description of what the function does
parameters:
  - name: param1
    type: number/date/text/etc
    required: true/false
    description: What this parameter represents
    default: null or specific value
  - name: param2
    type: number/date/text/etc
    required: true/false
    description: What this parameter represents
    default: null or specific value
return_value:
  type: number/date/text/etc
  description: What the function returns
special_cases:
  - Case description 1
  - Case description 2
excel_reference_url: https://support.microsoft.com/...
```

## Next Step
This output feeds into Step 2: Analyze Excel Behavior