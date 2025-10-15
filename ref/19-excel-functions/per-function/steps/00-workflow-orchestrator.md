# Excel Function Rust Implementation Workflow Orchestrator

This workflow chains together all the steps needed to implement an Excel function in Rust with comprehensive tests and documentation.

## Prerequisites
- The Excel function name to implement
- Access to Excel documentation and test sources
- Rust development environment set up

## Architecture Overview

The Rust Excel function implementation follows this architecture:
1. **Output Type Detection Function**: Determines output type based on input types (scalar/list)
2. **Pure Calculation Function**: Core logic using Rust primitives
3. **Polars Interface Function**: Handles Series/DataFrame integration with type branching
4. **List Processing Functions**: Separate handlers for list×list, scalar×list scenarios
5. **Kwargs Structure**: Manages optional parameters
6. **Comprehensive Tests**: Unit, integration, Excel compatibility, and list operation tests
7. **Module Integration**: Export in `src/excel/mod.rs`

## File Organization Pattern

**CRITICAL**: Follow clean separation of concerns with these file types:

- **Implementation File**: `src/excel/{function_name}.rs`
  - Contains ONLY implementation code
  - No `#[cfg(test)]` modules or test functions
  - Example: `yearfrac.rs`

- **Test File**: `src/excel/{function_name}_tests.rs`
  - Contains ALL tests for the function
  - Uses `#[cfg(test)]` at the module level
  - Imports implementation via `use super::super::{function_name}::*;`
  - Example: `yearfrac_tests.rs`

- **Module Export**: `src/excel/mod.rs`
  - `pub mod {function_name};` for implementation
  - `#[cfg(test)] mod {function_name}_tests;` for tests
  - Public exports for both function and output type

## Key Architectural Change: Native List Support

Excel functions now support native list column processing to handle actuarial projections:
- **List columns**: Contains vectors of values (e.g., 120 monthly projection values)
- **Broadcasting**: Scalar values broadcast to match list dimensions (Excel dynamic array behavior)
- **Type detection**: Functions determine output type based on input types
- **Performance**: Native Rust processing without Python overhead

## Workflow Steps

Each step takes input from previous steps and produces output for the next:

1. **[01-study-past-learnings.md](01-study-past-learnings.md)**
   - Input: Function name
   - Output: Relevant insights and tips (including list handling patterns)

2. **[02-analyze-excel-documentation.md](02-analyze-excel-documentation.md)**
   - Input: Function name
   - Output: Structured function specification (YAML)
   - Note: Include Excel 365 dynamic array behavior

3. **[03-research-excel-behavior.md](03-research-excel-behavior.md)**
   - Input: Function specification from Step 2
   - Output: Edge cases and behavior patterns (including array operations)

4. **[04-create-implementation-plan.md](04-create-implementation-plan.md)**
   - Input: Analysis from Steps 1-3
   - Output: Detailed implementation plan with list support strategy

5. **[05-implement-rust-function.md](05-implement-rust-function.md)**
   - Input: Implementation plan from Step 4
   - Output: Rust implementation file with list column support (implementation only)

6. **[06-write-comprehensive-tests.md](06-write-comprehensive-tests.md)**
   - Input: Implementation and behavior analysis
   - Output: Separate test file with comprehensive coverage including list operations and broadcasting

7. **[07-verify-build-quality.md](07-verify-build-quality.md)**
   - Input: Implementation and tests
   - Output: Quality check report

8. **[08-update-module-exports.md](08-update-module-exports.md)**
   - Input: Function name and implementation file
   - Output: Updated mod.rs with both implementation and test module references

9. **[09-update-learnings.md](09-update-learnings.md)**
   - Input: Implementation experience
   - Output: Universal learnings including list patterns

## Performance Considerations

Throughout the workflow, keep in mind:
- Define constants for magic numbers at module level
- Create expensive objects once outside loops
- Use `#[inline]` for small helper functions
- Use iterator patterns with `collect::<Float64Chunked>()`
- Pre-allocate list builders with capacity hints
- Avoid unnecessary array conversions in list processing
- Test with large datasets (1M+ rows) and deep lists (120+ elements)

## Function Design Pattern

All implementations MUST follow this pattern:

1. **Output Type Function**: `pub fn function_name_output_type(input_fields: &[Field]) -> PolarsResult<Field>`
2. **Polars Interface**: `pub fn function_name(inputs: &[Series], kwargs: &KwargsType) -> PolarsResult<Series>`
3. **Pure Calculation**: `fn calculate_function_name(params...) -> ReturnType`
4. **List Handlers**: 
   - `fn function_name_list_columns(start: &Series, end: &Series, ...) -> PolarsResult<Series>`
   - `fn function_name_broadcast_start(start: &Series, end: &Series, ...) -> PolarsResult<Series>`
   - `fn function_name_broadcast_end(start: &Series, end: &Series, ...) -> PolarsResult<Series>`

## How to Use This Workflow

1. Start with the Excel function name you want to implement
2. Work through each step in order
3. Each step produces output that feeds into the next
4. Save intermediate outputs for debugging/review
   - Create a folder unique to this workflow: `rust-functions-outputs/{FUNCTION_NAME}-output/`
   - The `rust-functions-outputs` directory should be git ignored
5. If a step fails, fix issues before proceeding

## Example Usage

```bash
# Set your function name
export FUNCTION_NAME="pmt"

# Create output directory (inside git-ignored rust-functions-outputs)
mkdir -p rust-functions-outputs/${FUNCTION_NAME}-output

# Work through each step, saving outputs
# Step 1: Study past learnings
# ... follow instructions in 01-study-past-learnings.md
# Save output to: rust-functions-outputs/${FUNCTION_NAME}-output/01-learnings.yaml

# Continue through all steps...
```

## Git Ignore Setup

Add to `.gitignore`:
```
# Rust function implementation outputs
rust-functions-outputs/
```

## List Column Considerations

When implementing functions with list support:
- Check if the function makes sense with array operations (most financial functions do)
- Design output type detection to handle all combinations: scalar×scalar, list×list, scalar×list, list×scalar
- Use Polars' broadcasting behavior (first value used for repeated scalars)
- Ensure backward compatibility for scalar operations
- Add comprehensive tests for list operations

## Quality Checklist

Before considering the implementation complete:

- [ ] All 9 steps completed successfully
- [ ] Output type function correctly detects scalar/list combinations
- [ ] List processing functions handle all scenarios
- [ ] Broadcasting behavior matches Excel 365
- [ ] cargo fmt passes
- [ ] cargo clippy --pedantic passes
- [ ] All tests pass (including list tests)
- [ ] Excel compatibility verified
- [ ] Documentation complete
- [ ] Performance benchmarked with list columns
- [ ] Learnings documented (including list patterns)