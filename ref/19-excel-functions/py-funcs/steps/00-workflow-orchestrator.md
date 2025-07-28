# Excel Function Integration Workflow Orchestrator

This workflow chains together all the steps needed to integrate an Excel function from Rust into Python.

## Prerequisites
- The Rust function must already be implemented in `gaspatchio_core_lib::excel`
- You have the function name to integrate

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

7. **[07-create-python-wrapper.md](07-create-python-wrapper.md)**
   - Input: Function analysis and Rust details
   - Output: Python wrapper code

8. **[08-update-python-exports.md](08-update-python-exports.md)**
   - Input: Function name
   - Output: Python export updates

9. **[09-create-excel-accessor.md](09-create-excel-accessor.md)**
   - Input: All previous analysis
   - Output: Excel accessor method with docstring

10. **[10-validate-docstring-examples.md](10-validate-docstring-examples.md)**
    - Input: Accessor method from Step 9
    - Output: Validation report

11. **[11-create-python-tests.md](11-create-python-tests.md)**
    - Input: Function behavior and examples
    - Output: Test implementations

12. **[12-run-full-test-suite.md](12-run-full-test-suite.md)**
    - Input: All implementation
    - Output: Test results summary

13. **[13-update-documentation.md](13-update-documentation.md)**
    - Input: Completed implementation
    - Output: Documentation updates

## How to Use This Workflow

1. Start with the function name you want to integrate
2. Work through each step in order
3. Each step produces output that feeds into the next
4. Save intermediate outputs for debugging/review
5. If a step fails, fix issues before proceeding

## Example Usage

```bash
# Set your function name
export FUNCTION_NAME="yearfrac"

# Work through each step, saving outputs
# Step 1: Analyze Excel docs
# ... follow instructions in 01-analyze-excel-docs.md
# Save output to: outputs/01-excel-analysis.yaml

# Step 2: Analyze behavior  
# ... use output from step 1
# Save output to: outputs/02-behavior-analysis.yaml

# Continue through all steps...
```

## Troubleshooting Common Issues

### Symbol Not Found Errors
- Ensure function name matches exactly between Rust and Python
- Run `maturin build && uv sync` after Rust changes

### Docstring Test Failures
- Use exact output from execution
- Run with `--accept` to update expected output
- Ensure all imports are included

### Type Errors
- Check kwargs mapping between Rust and Python
- Verify parameter types match

## Quality Checklist

Before considering the integration complete:

- [ ] All 13 steps completed successfully
- [ ] Tests pass without warnings
- [ ] Docstring examples execute correctly
- [ ] Type stubs are accurate
- [ ] No regressions in existing tests
- [ ] Documentation includes actuarial context
- [ ] Code follows project conventions