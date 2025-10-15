# Step 3: Research Excel Behavior

Analyze the Excel function's behavior in different scenarios, including edge cases and error conditions.

## Input
- Function specification from Step 2
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Search for test cases and edge cases**:
   - HyperFormula test suite: `https://github.com/handsontable/hyperformula/blob/master/test/interpreter/function-{{FUNCTION_NAME}}.spec.ts`
   - Stack Overflow discussions
   - Excel forums for quirks and bugs
   - Financial/domain-specific calculators for verification

2. **Identify behavior patterns**:
   - Normal use cases
   - Boundary conditions
   - Error conditions
   - Platform-specific differences
   - Version-specific quirks

3. **Research additional sources**:
   - Financial textbooks (for financial functions)
   - Statistical references (for statistical functions)
   - Other spreadsheet implementations (LibreOffice, Google Sheets)
   - Online calculators for verification

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/03-excel-behavior.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
normal_cases:
  - description: "Standard positive values"
    inputs:
      param1: value1
      param2: value2
    expected: result
    verified_in: "Excel 365|Excel Online|HyperFormula"
    
edge_cases:
  - description: "Zero value handling"
    inputs:
      param1: 0
      param2: 100
    expected: result
    notes: "Special handling required"
    
  - description: "Negative value handling"
    inputs:
      param1: -100
      param2: 50
    expected: result
    behavior: "Returns negative result"
    
error_conditions:
  - description: "Invalid parameter type"
    inputs:
      param1: "text"
      param2: 100
    expected_error: "#VALUE!"
    excel_behavior: "Attempts type coercion first"
    
  - description: "Division by zero"
    inputs:
      param1: 100
      param2: 0
    expected_error: "#DIV/0!"
    
quirks_and_bugs:
  - description: "1900 leap year bug"
    affected_versions: "All Excel versions"
    behavior: "Treats 1900 as leap year"
    workaround: "Document the behavior"
    
type_coercion:
  - from_type: "text"
    to_type: "number"
    examples:
      - input: "\"123\""
        converts_to: 123
      - input: "\"abc\""
        converts_to: "#VALUE!"
        
performance_notes:
  - scenario: "Large date ranges"
    consideration: "Cache date calculations"
  - scenario: "Repeated calculations"
    consideration: "Memoize results"
    
test_values:
  # Actual values from HyperFormula or Excel testing
  - inputs: {param1: val1, param2: val2}
    expected: result
    source: "HyperFormula test suite"
```

## Example Output

For YEARFRAC function:

```yaml
function_name: YEARFRAC
normal_cases:
  - description: "Standard date range within same year"
    inputs:
      start_date: "2012-01-01"
      end_date: "2012-07-30"
      basis: 0
    expected: 0.58055556
    verified_in: "Excel 365, HyperFormula"
    
  - description: "Date range across years"
    inputs:
      start_date: "2011-01-01"
      end_date: "2013-09-15"
      basis: 1
    expected: 2.7068493
    verified_in: "Excel Online"
    
edge_cases:
  - description: "Start date after end date"
    inputs:
      start_date: "2012-12-31"
      end_date: "2012-01-01"
      basis: 0
    expected: -0.99722222
    notes: "Returns negative value, not error"
    
  - description: "Same start and end date"
    inputs:
      start_date: "2012-06-15"
      end_date: "2012-06-15"
      basis: 0
    expected: 0
    behavior: "Returns exactly 0"
    
  - description: "Leap year handling"
    inputs:
      start_date: "2012-02-28"
      end_date: "2012-03-01"
      basis: 1
    expected: 0.00546448
    notes: "Actual/actual basis accounts for leap year"
    
error_conditions:
  - description: "Invalid date value"
    inputs:
      start_date: "invalid"
      end_date: "2012-01-01"
      basis: 0
    expected_error: "#VALUE!"
    
  - description: "Basis out of range"
    inputs:
      start_date: "2012-01-01"
      end_date: "2012-12-31"
      basis: 5
    expected_error: "#NUM!"
    excel_behavior: "Only accepts 0-4 for basis"
    
quirks_and_bugs:
  - description: "1900 leap year bug affects basis 1"
    affected_versions: "All Excel versions"
    behavior: "Incorrectly treats 1900 as leap year"
    impact: "Affects actual/actual calculations for dates before March 1900"
    
  - description: "Basis 0 (30/360) month-end handling"
    behavior: "Special rules for last day of month"
    example: "Feb 28 to Mar 31 counts as 30 + 30 days"
    
type_coercion:
  - from_type: "number"
    to_type: "date"
    examples:
      - input: 41640
        converts_to: "2014-01-01"
        note: "Excel serial date number"
        
test_values:
  - inputs: {start_date: "2012-01-01", end_date: "2012-07-30", basis: 0}
    expected: 0.58055556
    source: "HyperFormula test suite"
  - inputs: {start_date: "2012-01-01", end_date: "2012-07-30", basis: 3}
    expected: 0.57808219
    source: "Excel verification"
    
performance_notes:
  - scenario: "Multiple calculations with same dates"
    consideration: "Cache day difference calculations"
  - scenario: "Basis 1 (actual/actual)"
    consideration: "Most complex calculation, may need optimization"
```

## Research Tips

1. **HyperFormula Tests**: Best source for comprehensive test cases
2. **Excel Forums**: Search for "Excel [FUNCTION_NAME] wrong result" or "unexpected behavior"
3. **Financial Sources**: For financial functions, check against HP-12C or similar
4. **Cross-verification**: Test in Excel Online when possible
5. **Edge Case Keywords**: Search for "[FUNCTION_NAME] negative", "zero", "error", "bug"

## Common Edge Cases to Check

1. **Numeric functions**:
   - Zero, negative, very large/small values
   - Infinity, NaN
   - Integer overflow

2. **Date functions**:
   - 1900 leap year bug
   - Date serial number boundaries
   - Different calendar systems

3. **Text functions**:
   - Empty strings
   - Unicode handling
   - Maximum string length

4. **Financial functions**:
   - Sign conventions (positive/negative)
   - Zero interest rate
   - Zero periods

## Next Step

Use this behavior analysis to create a detailed implementation plan in Step 4.