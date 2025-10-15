# Step 2: Excel Function Behavior Analysis

You are researching and documenting the detailed behavior of an Excel function, including edge cases and special scenarios.

## Input

From previous step (01-excel-doc-analysis.md output):
```yaml
{{EXCEL_DOC_ANALYSIS_OUTPUT}}
```

## Task

1. Research the function's behavior in various scenarios:
   - Normal use cases with typical values
   - Edge cases (zeros, negatives, extremely large/small values)
   - Error conditions and how Excel handles them
   - Null/empty cell handling

2. Search for additional information:
   - Excel help forums and StackOverflow for edge cases
   - Financial textbooks for formula verification
   - Other Excel-compatible software documentation
   - Test the function in Excel if possible

3. Document scalar vs vector behavior:
   - How the function handles single values
   - How it handles arrays/ranges
   - Mixed scalar/vector parameter combinations

## Output Format

```yaml
function_name: {{FUNCTION_NAME}}

behavior_scenarios:
  normal_cases:
    - description: [Scenario description]
      inputs: [Example inputs]
      expected_output: [Expected result]
      
  edge_cases:
    - description: [Edge case description]
      inputs: [Example inputs]
      expected_output: [Expected result]
      excel_behavior: [How Excel specifically handles this]
      
  error_conditions:
    - description: [Error scenario]
      inputs: [Example inputs]
      excel_error: [#NUM!, #VALUE!, etc.]
      cause: [Why this error occurs]
      
  null_handling:
    description: [How nulls/empty cells are handled]
    propagation: [true/false - do nulls propagate?]
    special_behavior: [Any special null handling]
    
vectorization:
  scalar_scalar: 
    description: [How it works with all scalar inputs]
    example: [Example]
    
  vector_vector:
    description: [How it works with all vector inputs]
    example: [Example]
    
  mixed_combinations:
    - params: [param1: scalar, param2: vector]
      behavior: [Broadcasting behavior]
      example: [Example]
      
actuarial_context:
  - use_case: [Premium calculation scenario]
    description: [How this function helps]
    
  - use_case: [Reserve valuation scenario]
    description: [How this function helps]
    
additional_notes:
  - [Any other important behavioral notes]
  - [Performance considerations]
  - [Common mistakes to avoid]
```

## Example Output

```yaml
function_name: YEARFRAC

behavior_scenarios:
  normal_cases:
    - description: Standard year fraction calculation
      inputs: start_date=2023-01-01, end_date=2023-07-01, basis=0
      expected_output: 0.5
      
  edge_cases:
    - description: Start date after end date
      inputs: start_date=2023-07-01, end_date=2023-01-01, basis=0
      expected_output: -0.5
      excel_behavior: Returns negative value, no error
      
    - description: Same start and end date
      inputs: start_date=2023-01-01, end_date=2023-01-01, basis=0
      expected_output: 0
      excel_behavior: Returns exactly 0
      
  error_conditions:
    - description: Invalid basis value
      inputs: start_date=2023-01-01, end_date=2023-07-01, basis=5
      excel_error: #NUM!
      cause: Basis must be 0-4
      
  null_handling:
    description: Null dates cause errors
    propagation: false
    special_behavior: Returns #VALUE! error if any date is null/empty
    
vectorization:
  scalar_scalar: 
    description: Single date pair calculation
    example: YEARFRAC(A1, B1, 0) where A1 and B1 contain single dates
    
  vector_vector:
    description: Element-wise calculation on date arrays
    example: YEARFRAC(A1:A10, B1:B10, 0) calculates 10 year fractions
    
  mixed_combinations:
    - params: [start_date: vector, end_date: scalar, basis: scalar]
      behavior: Broadcasts end_date to match start_date length
      example: YEARFRAC(A1:A10, B1, 0) uses B1 for all calculations
      
actuarial_context:
  - use_case: Premium pro-rating
    description: Calculate exact fraction of policy year for premium calculations
    
  - use_case: Reserve valuation timing
    description: Determine fractional periods for time value calculations
    
additional_notes:
  - Different basis values represent different day count conventions
  - Basis 0 (30/360 US) is most common in US financial calculations
  - Results may differ slightly from manual calculations due to leap year handling
```