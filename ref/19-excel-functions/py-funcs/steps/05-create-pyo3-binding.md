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
The complete Rust binding file:

```rust
// File: src/excel/{{function_name}}.rs
#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

#[polars_expr(output_type_func = same_output_type)]
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
- [ ] Output type function appropriate for this function
- [ ] No additional logic (thin wrapper only)

## Next Step
This output feeds into Step 6: Update Rust Exports