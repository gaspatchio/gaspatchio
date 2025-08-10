# Step 5: Create PyO3 Rust Binding

## Input
- Rust analysis from Step 4
- Function name and kwargs structure

## Task
Create the Python-Rust bridge file.

### Actions
1. Create `src/excel/{{function_name}}.rs` with the PyO3 binding
2. Follow the standard pattern for Excel function bindings

## Output
Save the complete Rust binding to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/05-rust-binding.rs`

```rust
// File: src/excel/{{function_name}}.rs
#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

// For functions that don't support lists, use same_output_type:
fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

// For functions that support lists, import from core:
use gaspatchio_core_lib::excel::{{function_name}}_output_type;

// Use the appropriate output type function based on list support:
// For simple functions without list support:
#[polars_expr(output_type_func = same_output_type)]
// For functions with list support:
// #[polars_expr(output_type_func = {{function_name}}_output_type)]
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
- [ ] Output type function appropriate for this function:
  - Use `same_output_type` for simple scalar functions
  - Use `{{function_name}}_output_type` if Rust handles lists
- [ ] No additional logic (thin wrapper only)

## Next Step
This output feeds into Step 6: Update Rust Exports