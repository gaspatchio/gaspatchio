# Step 9: Update Learnings

Document universal insights from this implementation for future Excel functions.

## Input
- Implementation experience from all previous steps
- Function name: `{{FUNCTION_NAME}}`

## Process

1. **Reflect on the implementation**:
   - What patterns emerged?
   - What challenges were faced?
   - What would help future implementations?

2. **Focus on universal learnings**:
   - NOT specific to this function
   - Applicable to many Excel functions
   - Implementation techniques
   - Testing strategies
   - Performance insights

3. **Update or refine existing learnings**:
   - Can existing learnings be improved?
   - Should any be removed or merged?

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/09-learnings-update.yaml`:

```yaml
function_name: {{FUNCTION_NAME}}
new_learnings:
  - title: "Learning Title"
    content: |
      Detailed explanation of a universal principle that applies 
      to implementing any Excel function. This should be actionable
      and help future implementers avoid pitfalls or work more
      efficiently.
    category: "implementation|testing|performance|compatibility|architecture"
    
updated_learnings:
  - existing_title: "Existing Learning Title"
    update_type: "refine|merge|remove"
    new_content: |
      If refining, provide the improved version.
      If merging, indicate which learnings to combine.
      If removing, explain why it's no longer relevant.
      
insights_not_documented:
  - "Observation that might become a learning with more evidence"
  - "Pattern noticed but needs validation across more functions"
```

## Categories of Universal Learnings

### Implementation Patterns
- Two-function architecture insights
- Type conversion strategies
- Error handling patterns
- Null propagation techniques

### Testing Strategies
- Test data generation
- Excel verification approaches
- Edge case discovery methods
- Performance testing patterns

### Performance Optimization
- Iterator pattern benefits
- Constant extraction strategies
- Memory allocation patterns
- Parallelization opportunities

### Excel Compatibility
- Undocumented behaviors
- Cross-version differences
- Platform-specific quirks
- Type coercion rules

### Architecture Decisions
- When to use helper functions
- Kwargs structure patterns
- Module organization
- Code reuse strategies

## Example Learnings Update

```yaml
function_name: PMT
new_learnings:
  - title: "Financial Function Sign Conventions"
    content: |
      Excel financial functions use negative values for cash outflows 
      (payments) and positive for inflows (receipts). This is opposite
      to what many developers expect. Always check Excel's examples to
      verify sign conventions, and document them clearly in the function
      implementation. This affects PV, FV, PMT, and all TVM functions.
    category: "compatibility"
    
  - title: "Optional Parameter Validation Pattern"
    content: |
      When optional parameters have valid ranges (like basis 0-4), 
      validate them immediately after unwrapping in the Polars interface
      function, not in the calculation function. This provides better
      error messages and prevents invalid values from propagating into
      the calculation logic. Use early returns with descriptive errors.
    category: "implementation"
    
updated_learnings:
  - existing_title: "Iterator Performance Pattern"
    update_type: "refine"
    new_content: |
      The #[allow(clippy::useless_conversion)] attribute is almost always
      needed when using .into_iter() on Polars arrays due to how the
      trait system works. This is not actually a useless conversion -
      it's required for the iterator protocol. Add this attribute 
      preemptively to avoid clippy warnings. The pattern should be:
      
      #[allow(clippy::useless_conversion)]
      let result_ca = array.into_iter()
          .map(|val| ...)
          .collect::<Float64Chunked>();
          
insights_not_documented:
  - "Helper functions for date calculations could be shared across functions"
  - "Financial functions might benefit from a shared TVM calculation module"
```

## Guidelines for Good Learnings

### DO Write Learnings That Are:
- **Universal**: Apply to many functions, not just one
- **Actionable**: Provide clear guidance
- **Specific**: Include examples or patterns
- **Validated**: Based on actual implementation experience

### DON'T Write Learnings That Are:
- **Function-specific**: "YEARFRAC needs special February handling"
- **Obvious**: "Functions should have tests"  
- **Vague**: "Be careful with edge cases"
- **Temporary**: "Currently Rust version X has a bug"

## Example Good vs Bad Learnings

### ❌ Bad: Too Specific
"The YEARFRAC function's basis 1 (actual/actual) calculation is complex and requires careful handling of leap years."

### ✅ Good: Universal Pattern  
"Excel date functions that use day count conventions often require separate helper functions for each convention. Implement each as a pure function that can be tested independently, then dispatch to the appropriate helper based on the parameter value."

### ❌ Bad: Too Vague
"Make sure to handle errors properly in Excel functions."

### ✅ Good: Specific Guidance
"Excel functions use specific error codes (#NUM!, #VALUE!, #DIV/0!). Map these to PolarsError::ComputeError with messages that include both the Excel error code and a description: `format!("#NUM! Invalid basis: {}. Must be 0-4", basis)`"

## Review Existing Learnings

Before adding new learnings:
1. Check if a similar learning exists
2. Consider if learnings can be combined
3. Remove outdated or superseded learnings
4. Refine learnings that could be clearer

## Next Step

This completes the implementation workflow. The function is now:
- Implemented in Rust
- Thoroughly tested
- Quality checked
- Exported properly
- Documented with learnings

For parallel processing, collect all learning updates and apply them in batch after all functions are complete.