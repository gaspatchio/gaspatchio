# Excel Function Integration Workflow Orchestrator

This workflow chains together all the steps needed to integrate an Excel function from Rust into Python.

## Prerequisites
- The Rust function must already be implemented in `gaspatchio_core_lib::excel`
- You have the function name to integrate

## Architecture Overview

The Python Excel function integration follows this architecture:
1. **Function Implementation**: Created in `gaspatchio_core/accessors/excel_functions/{{function_name}}.py`
   - Contains ALL business logic (parameter validation, type conversion)
   - Handles the Rust plugin hookup via `register_plugin_function`
2. **Accessor Method**: Added to `gaspatchio_core/accessors/excel.py`
   - Acts as a thin shim that delegates to the function implementation
   - Provides the fluent API (e.g., `af["col"].excel.function_name()`)
3. **No Module Exports**: Functions are NOT exported at the module level
   - Only accessible through the Excel accessor API
   - Keeps the namespace clean and organized

## Workflow Steps

Each step takes input from previous steps and produces output for the next:

1. **[01-analyze-excel-docs.md](01-analyze-excel-docs.md)**
   - Input: Function name
   - Output: Structured function analysis (YAML)

2. **[02-analyze-excel-behavior.md](02-analyze-excel-behavior.md)**
   - Input: Function analysis from Step 1
   - Output: Behavior patterns and edge cases (YAML)

3. **[03-review-past-learnings.md](03-review-past-learnings.md)**
   - Input: Function name and behavior
   - Output: Relevant insights and tips

4. **[04-analyze-rust-implementation.md](04-analyze-rust-implementation.md)**
   - Input: Analysis from Steps 1-3
   - Output: Rust interface details (YAML)

5. **[05-create-pyo3-binding.md](05-create-pyo3-binding.md)**
   - Input: Rust analysis
   - Output: PyO3 binding code (Rust)

6. **[06-update-rust-exports.md](06-update-rust-exports.md)**
   - Input: Function name
   - Output: Module export line

7. **[07-create-python-implementation.md](07-create-python-implementation.md)**
   - Input: Function analysis and Rust details
   - Output: Python function implementation AND accessor method

8. **[08-validate-docstring-examples.md](08-validate-docstring-examples.md)**
   - Input: Accessor method from Step 7
   - Output: Validation report

9. **[09-create-python-tests.md](09-create-python-tests.md)**
   - Input: Function behavior and examples
   - Output: Test implementations

10. **[10-run-full-test-suite.md](10-run-full-test-suite.md)**
    - Input: All implementation
    - Output: Test results summary

11. **[11-update-documentation.md](11-update-documentation.md)**
    - Input: Completed implementation
    - Output: Documentation updates

## Changes from Previous Version

This workflow has been streamlined from 13 steps to 11 steps:
- **Merged Steps 7 & 9**: Creating the function implementation and accessor method are now done together in Step 7
- **Removed Step 8**: Module export updates are no longer needed with the new architecture
- **Renumbered Steps**: Subsequent steps have been renumbered accordingly

## How to Use This Workflow

1. Start with the function name you want to integrate
2. Work through each step in order
3. Each step produces output that feeds into the next
4. Save intermediate outputs for debugging/review
   - we're going to be multithreading so you'll need to create a folder UNIQUE to this workflow
   - All outputs should go to: `pyfuncs-outputs/{function_name}_output/`
   - This allows safe git ignore of the entire `pyfuncs-outputs` folder
5. If a step fails, fix issues before proceeding

## Example Usage

```bash
# Set your function name
export FUNCTION_NAME="yearfrac"

# Create output directory
mkdir -p pyfuncs-outputs/${FUNCTION_NAME}_output

# Work through each step, saving outputs
# Step 1: Analyze Excel docs
# ... follow instructions in 01-analyze-excel-docs.md
# Save output to: pyfuncs-outputs/${FUNCTION_NAME}_output/01-excel-analysis.yaml

# Step 2: Analyze behavior  
# ... use output from step 1
# Save output to: pyfuncs-outputs/${FUNCTION_NAME}_output/02-behavior-analysis.yaml

# Continue through all steps...
```

## Troubleshooting Common Issues

### Symbol Not Found Errors
- Ensure function name matches exactly between Rust and Python
- Reinstall bindings in develop mode after Rust changes:
  - `uvx maturin develop -m gaspatchio-core/bindings/python/Cargo.toml && uv sync`

### Docstring Test Failures
- Use exact output from execution
- Run with `--accept` to update expected output
- Ensure all imports are included

### Type Errors
- Check kwargs mapping between Rust and Python
- Verify parameter types match
- For Polars plugin output types, prefer a local output_type shim in the bindings crate that delegates to the core implementation (the macro requires a local function item)

## Quality Checklist

Before considering the integration complete:

- [ ] All 11 steps completed successfully
- [ ] Tests pass without warnings
- [ ] Docstring examples execute correctly
- [ ] Type stubs are accurate
- [ ] No regressions in existing tests
- [ ] Documentation includes actuarial context
- [ ] Code follows project conventions