# Excel Function Rust Implementation Workflow Orchestrator

This workflow chains together all the steps needed to implement an Excel function in Rust with comprehensive tests and documentation.

## Prerequisites
- The Excel function name to implement
- Access to Excel documentation and test sources
- Rust development environment set up

## Architecture Overview

The Rust Excel function implementation follows this architecture:
1. **Pure Calculation Function**: Core logic using Rust primitives
2. **Polars Interface Function**: Handles Series/DataFrame integration
3. **Kwargs Structure**: Manages optional parameters
4. **Comprehensive Tests**: Unit, integration, and Excel compatibility tests
5. **Module Integration**: Export in `src/excel/mod.rs`

## Workflow Steps

Each step takes input from previous steps and produces output for the next:

1. **[01-study-past-learnings.md](01-study-past-learnings.md)**
   - Input: Function name
   - Output: Relevant insights and tips

2. **[02-analyze-excel-documentation.md](02-analyze-excel-documentation.md)**
   - Input: Function name
   - Output: Structured function specification (YAML)

3. **[03-research-excel-behavior.md](03-research-excel-behavior.md)**
   - Input: Function specification from Step 2
   - Output: Edge cases and behavior patterns (YAML)

4. **[04-create-implementation-plan.md](04-create-implementation-plan.md)**
   - Input: Analysis from Steps 1-3
   - Output: Detailed implementation plan (YAML)

5. **[05-implement-rust-function.md](05-implement-rust-function.md)**
   - Input: Implementation plan from Step 4
   - Output: Rust implementation code

6. **[06-write-comprehensive-tests.md](06-write-comprehensive-tests.md)**
   - Input: Implementation and behavior analysis
   - Output: Test implementation code

7. **[07-verify-build-quality.md](07-verify-build-quality.md)**
   - Input: Implementation and tests
   - Output: Quality check report

8. **[08-update-module-exports.md](08-update-module-exports.md)**
   - Input: Function name
   - Output: Updated mod.rs

9. **[09-update-learnings.md](09-update-learnings.md)**
   - Input: Implementation experience
   - Output: Universal learnings for future implementations

## Performance Considerations

Throughout the workflow, keep in mind:
- Define constants for magic numbers at module level
- Create expensive objects once outside loops
- Use `#[inline]` for small helper functions
- Use iterator patterns with `collect::<Float64Chunked>()`
- Add benchmarks for functions used in actuarial projections
- Test with large datasets (1M+ rows)

## Two-Function Design Pattern

All implementations MUST follow this pattern:
1. **Polars Interface**: `pub fn function_name(inputs: &[Series], kwargs: &KwargsType) -> PolarsResult<Series>`
2. **Pure Calculation**: `fn calculate_function_name(params...) -> ReturnType`

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

## Multithreading Considerations

Since we'll be processing multiple functions in parallel:
- Each function gets its own output directory
- Use thread-safe file operations
- Avoid modifying shared files (like mod.rs) concurrently
- Batch module export updates at the end

## Quality Checklist

Before considering the implementation complete:

- [ ] All 9 steps completed successfully
- [ ] cargo fmt passes
- [ ] cargo clippy --pedantic passes
- [ ] All tests pass
- [ ] Excel compatibility verified
- [ ] Documentation complete
- [ ] Performance benchmarked (if applicable)
- [ ] Learnings documented