# Step 6: Update Rust Module Exports

## Input
- Function name from previous steps
- PyO3 binding created in Step 5

## Task
Add the new module to Rust exports.

### Actions
1. Open `src/excel/mod.rs`
2. Add the module declaration in alphabetical order

## Output
The line to add to `src/excel/mod.rs`:

```rust
pub mod {{function_name}};
```

### Location Instructions
- Find the existing `pub mod` declarations
- Insert in alphabetical order
- Ensure consistent formatting

### Validation
- [ ] Module name matches file name exactly
- [ ] Inserted in alphabetical order
- [ ] No duplicate declarations

## Next Step
This output completes the Rust side. Next is Step 7: Create Python Wrapper