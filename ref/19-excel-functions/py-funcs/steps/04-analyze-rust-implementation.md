# Step 4: Analyze Rust Implementation

## Input
- Function analysis from Steps 1-3
- Access to Rust codebase

## Task
Analyze the existing Rust implementation to understand the interface.

### Actions
1. Locate the Rust function:
   - Check `gaspatchio_core_lib::excel::{{function_name}}`
   - Find the file in `src/excel/{{function_name}}.rs`

2. Identify the kwargs structure:
   - Look for `{{FunctionName}}Kwargs` struct
   - Note all fields and their types
   - Check for defaults

3. Understand the signature:
   - Input types expected
   - Return type
   - Error handling approach

4. Check existing patterns:
   - Compare with similar functions like `yearfrac.rs`
   - Note any special handling

## Output
Create a Rust analysis document:

```yaml
function_name: {{FUNCTION_NAME}}
rust_module_path: "gaspatchio_core_lib::excel::{{function_name}}"
rust_file_path: "src/excel/{{function_name}}.rs"
kwargs_struct:
  name: "{{FunctionName}}Kwargs"
  fields:
    - name: "field1"
      rust_type: "Option<i32>"
      default: "None"
    - name: "field2"
      rust_type: "bool"
      default: "false"
function_signature:
  inputs: "&[Series]"
  kwargs: "&{{FunctionName}}Kwargs"
  return_type: "PolarsResult<Series>"
implementation_notes:
  - "Uses pattern X for handling Y"
  - "Special case for null values"
similar_functions:
  - name: "yearfrac"
    pattern_to_copy: "Date handling approach"
```

## Next Step
This output feeds into Step 5: Create PyO3 Binding