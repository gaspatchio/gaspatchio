# Step 2: Analyze Excel Behavior

## Input
- Output from Step 1: Structured function analysis (YAML format)

## Task
Analyze the Excel function's behavior in different scenarios, focusing on scalar/vector combinations.

### Actions
1. Research edge cases and special behaviors:
   - Search web for "{{FUNCTION_NAME}} Excel edge cases"
   - Check StackOverflow for common issues
   - Look for financial/actuarial specific usage

2. Document scalar/vector behavior patterns:
   - Can param1 be scalar, vector, or both?
   - Can param2 be scalar, vector, or both?
   - etc with the other params
   - What combinations are valid?
   - How does Excel handle mismatched lengths?

3. Test cases to investigate:
   - Normal use cases
   - Edge cases (zeros, negatives, nulls)
   - Error conditions
   - Date/time handling specifics
   - Rounding behavior

## Output
Save the behavior analysis to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/02-behavior-analysis.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
scalar_vector_patterns:
  param1:
    accepts_scalar: true/false
    accepts_vector: true/false
  param2:
    accepts_scalar: true/false
    accepts_vector: true/false
  valid_combinations:
    - [scalar, scalar]
    - [vector, scalar]
    - [vector, vector]
    # etc.
edge_cases:
  - description: "Null handling"
    behavior: "Returns null if any input is null"
  - description: "Zero values"
    behavior: "Returns X when param1 is 0"
  - description: "Negative values"
    behavior: "Throws error/returns specific value"
error_conditions:
  - condition: "Invalid date"
    excel_behavior: "#VALUE!"
    rust_behavior: "Should return null"
test_scenarios:
  - inputs: {param1: 0, param2: 1}
    expected_output: 0
  - inputs: {param1: null, param2: 1}
    expected_output: null
```

## Next Step
This output feeds into Step 3: Review Past Learnings