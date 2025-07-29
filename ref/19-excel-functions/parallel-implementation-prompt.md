# Parallel Excel Function Implementation Prompt

## Context
We have successfully implemented the YEARFRAC function with comprehensive list support for actuarial projections. This implementation serves as the reference pattern for all other Excel functions.

## Key Resources
- **Reference Implementation**: `/src/excel/yearfrac.rs` - Complete implementation with list support
- **Workflow Steps**: `/ref/19-excel-functions/per-function/steps/` - Detailed implementation process
- **Function List**: `/ref/19-excel-functions/19-functions-list.md` - Functions to implement
- **List Handling Guide**: `/ref/19-excel-functions/19-rust-list-handling.md` - Technical details

## Implementation Pattern Summary
Each Excel function implementation requires:
1. Output type detection function for scalar/list inputs
2. Main function with type branching
3. Scalar handler (traditional behavior)
4. List handler (element-wise operations)
5. Broadcasting handlers (scalar×list combinations)
6. Comprehensive tests including list operations

## Prompt Template for Multiple Claude Code Sessions

```
I need you to implement the Excel {{FUNCTION_NAME}} function in Rust following our established pattern.

## Context
- We're implementing Excel functions with native list column support for actuarial projections
- Each function must handle scalar operations (backward compatible) AND list operations (vectors of values)
- List columns enable processing entire projection arrays (e.g., 120 monthly values) efficiently

## Resources to Study
1. **Reference Implementation**: Read `~/Projects/gaspatchio/gaspatchio-core/core/src/excel/yearfrac.rs` to understand the complete pattern
2. **Workflow Steps**: Review `~/Projects/gaspatchio/gaspatchio-core/core/ref/19-excel-functions/per-function/steps/` (especially steps 04, 05, 06)
3. **Function Documentation**: Check the Microsoft documentation link for {{FUNCTION_NAME}} behavior

## Implementation Requirements
1. Follow the 9-step workflow in the steps directory
2. Create output directory: `rust-functions-outputs/{{FUNCTION_NAME}}-output/`
3. Implement all required functions:
   - `{{function_name}}_output_type()` - Type detection
   - `{{function_name}}()` - Main interface with branching
   - `{{function_name}}_scalar_columns()` - Traditional scalar operations
   - `{{function_name}}_list_columns()` - List×list operations
   - `{{function_name}}_broadcast_first()` - Scalar×list broadcasting
   - `{{function_name}}_broadcast_second()` - List×scalar broadcasting
   - `calculate_{{function_name}}()` - Pure calculation logic

## Key Patterns to Follow
- Use the exact same type branching pattern as yearfrac
- Handle Polars DataFrame scalar broadcasting (use first value)
- Pre-allocate list builders with capacity estimates
- Proper null handling at both list and element levels
- Match Excel behavior exactly (including quirks)

## Testing Requirements
Include tests for:
- Output type detection (all combinations)
- Scalar operations (backward compatibility)
- List operations (same length lists)
- Broadcasting (scalar×list both directions)
- Null handling (list and element level)
- Excel compatibility verification
- Property-based tests for list operations

## File Location
Create the implementation at: `~/Projects/gaspatchio/gaspatchio-core/core/src/excel/{{function_name}}.rs`

Please implement {{FUNCTION_NAME}} following this pattern exactly. Start by studying the yearfrac implementation thoroughly.
```

## Recommended Functions for Parallel Implementation

Based on complexity and similarity to yearfrac, here are good candidates for parallel implementation:

### Financial Functions (High Priority - Similar Pattern)
1. **PMT** - Payment calculation (already has tests, needs list support)
2. **PV** - Present value (similar to PMT)
3. **FV** - Future value (similar to PMT)
4. **RATE** - Interest rate (iterative, good list candidate)
5. **NPER** - Number of periods (similar pattern)
6. **NPV** - Net present value (variable arguments, interesting case)
7. **IRR** - Internal rate of return (iterative like RATE)

### Date Functions (Medium Priority - Similar to YEARFRAC)
1. **DAYS** - Days between dates (simpler than YEARFRAC)
2. **NETWORKDAYS** - Working days between dates
3. **WORKDAY** - Add working days to date

### Math Functions (Lower Priority - Simpler Pattern)
1. **POWER** - Power function (simple math)
2. **ROUND** - Rounding (already has dispatch support)
3. **CEILING** - Ceiling function
4. **FLOOR** - Floor function

## Example Parallel Session Prompts

### Session 1: PMT Function
```
I need you to implement the Excel PMT function in Rust following our established pattern.

## Context
- We're implementing Excel functions with native list column support for actuarial projections
- Each function must handle scalar operations (backward compatible) AND list operations (vectors of values)
- List columns enable processing entire projection arrays (e.g., 120 monthly values) efficiently

## Resources to Study
1. **Reference Implementation**: Read `~/Projects/gaspatchio/gaspatchio-core/core/src/excel/yearfrac.rs` to understand the complete pattern
2. **Existing PMT Tests**: Check `~/Projects/gaspatchio/gaspatchio-core/core/src/excel/pmt.rs` for current implementation
3. **Workflow Steps**: Review `~/Projects/gaspatchio/gaspatchio-core/core/ref/19-excel-functions/per-function/steps/` (especially steps 04, 05, 06)

[Continue with standard requirements...]
```

### Session 2: PV Function
```
I need you to implement the Excel PV function in Rust following our established pattern.

[Same structure as above, adapted for PV]
```

### Session 3: DAYS Function
```
I need you to implement the Excel DAYS function in Rust following our established pattern.

[Same structure as above, adapted for DAYS - note it's simpler than YEARFRAC]
```

## Important Notes

1. **Each session should be independent** - Provide full context in each prompt
2. **Reference yearfrac.rs explicitly** - It's the gold standard implementation
3. **Emphasize list support** - This is the key differentiator
4. **Test comprehensively** - Especially broadcasting and null handling
5. **Follow the workflow** - The 9 steps ensure consistency

## Verification Checklist

After each implementation:
- [ ] All tests pass including new list tests
- [ ] Backward compatibility maintained
- [ ] Broadcasting works like Excel 365
- [ ] Performance acceptable with large lists
- [ ] Documentation complete
- [ ] Module exports updated