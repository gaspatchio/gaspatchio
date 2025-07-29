# Step 1: Study Past Learnings

Review existing insights and tips from previous Excel function implementations.

## Input
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Read the learnings document**:
   ```bash
   cat ref/19-excel-functions/per-function/19-learnings.md
   ```

2. **Extract relevant insights**:
   - Look for patterns that might apply to your function
   - Note any warnings about common pitfalls
   - Identify similar functions that have been implemented

3. **Consider function category**:
   - Financial functions (PV, FV, PMT, etc.)
   - Date functions (YEARFRAC, DATEDIF, etc.)
   - Statistical functions (AVERAGE, STDEV, etc.)
   - Text functions (CONCATENATE, TRIM, etc.)
   - Logical functions (IF, AND, OR, etc.)

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/01-learnings.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
category: financial|date|statistical|text|logical|other
relevant_learnings:
  - learning: "Description of relevant insight"
    source: "Which function or general principle this came from"
  - learning: "Another relevant insight"
    source: "Source of this learning"
similar_functions:
  - name: "SIMILAR_FUNCTION1"
    similarity: "How it's similar"
    implementation_notes: "What to reuse or avoid"
warnings:
  - "Specific warning that applies to this function type"
  - "Another warning to keep in mind"
notes: |
  Any additional notes or observations that might be helpful
  during implementation.
```

## Example Output

For a function like PMT:

```yaml
function_name: PMT
category: financial
relevant_learnings:
  - learning: "Financial functions often need to handle both beginning and end of period calculations"
    source: "General financial function pattern"
  - learning: "Sign conventions in Excel financial functions can be counterintuitive"
    source: "PV/FV implementation experience"
similar_functions:
  - name: "PV"
    similarity: "Both calculate present/future values with similar parameters"
    implementation_notes: "Can reuse interest rate conversion logic"
  - name: "FV" 
    similarity: "Mirror function with opposite calculation"
    implementation_notes: "Consider implementing shared helper functions"
warnings:
  - "Excel uses negative values for payments (cash outflows)"
  - "Period count of 0 has special handling in financial functions"
notes: |
  PMT is part of the TVM (Time Value of Money) family of functions.
  Consider implementing shared TVM helpers that can be reused across
  PV, FV, PMT, IPMT, and PPMT functions.
```

## Common Patterns to Look For

1. **Date handling quirks**:
   - Excel's date epoch (1900-01-01 with leap year bug)
   - Different day count conventions

2. **Floating point precision**:
   - When to use epsilon comparisons
   - Rounding behavior

3. **Null/error propagation**:
   - How Excel handles missing values
   - Error value precedence

4. **Performance patterns**:
   - Iterator vs loop patterns
   - Constant extraction

5. **Type conversion**:
   - String to number coercion
   - Boolean to number conversion

## Next Step

Use these learnings to inform your analysis of the Excel documentation in Step 2.