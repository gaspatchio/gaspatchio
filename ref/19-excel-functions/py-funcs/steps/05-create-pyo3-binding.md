# Step 5: Create PyO3 Rust Binding


## Input
- Rust analysis from Step 4
- Function name and kwargs structure

## Task
Create the Python-Rust bridge file.

### Actions
1. Create `bindings/python/src/excel/{{function_name}}.rs` in the bindings crate
2. Follow the standard pattern for Excel function bindings

## Output
Save the complete Rust binding to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/05-rust-binding.rs`

```rust
// File: bindings/python/src/excel/{{function_name}}.rs
#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

// Use a local shim for the output type attribute.
// The macro requires a local function item; delegate to core for logic.
use gaspatchio_core_lib::excel::{{function_name}}::{{function_name}}_output_type as core_output_type;

fn {{function_name}}_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    core_output_type(input_fields)
}

#[polars_expr(output_type_func = {{function_name}}_output_type)]
pub fn {{function_name}}(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::{{FunctionName}}Kwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::{{function_name}}(inputs, &kwargs)
}
```

### Validation Checklist
- [ ] Function name matches exactly (snake_case)
- [ ] Kwargs type imported correctly
- [ ] Local shim delegates to core output type function
- [ ] No additional logic (thin wrapper only)

## Next Step
This output feeds into Step 6: Update Rust Exports