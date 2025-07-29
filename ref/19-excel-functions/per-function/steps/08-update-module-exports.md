# Step 8: Update Module Exports

Add the new function to the Excel module exports.

## Input
- Function name: `{{FUNCTION_NAME}}`
- Implementation file created in Step 5

## Process

1. **Update src/excel/mod.rs**:
   - Add module declaration
   - Add public export
   - Maintain alphabetical order

2. **Verify the export**:
   - Check compilation
   - Ensure function is accessible

## Implementation Steps

1. **Add module declaration**:
   ```rust
   // In src/excel/mod.rs
   mod {{function_name}};
   ```

2. **Add public export**:
   ```rust
   // In the public exports section
   pub use {{function_name}}::{{function_name}};
   ```

3. **Export Kwargs if needed**:
   ```rust
   // If function has kwargs
   pub use {{function_name}}::{{FunctionName}}Kwargs;
   ```

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/08-module-updates.md`:

```markdown
# Module Export Updates for {{FUNCTION_NAME}}

## Added to src/excel/mod.rs:

### Module declaration:
```rust
mod {{function_name}};
```

### Public exports:
```rust
pub use {{function_name}}::{{function_name}};
pub use {{function_name}}::{{FunctionName}}Kwargs;
```

## Verification:
- [ ] Module compiles successfully
- [ ] Function is exported
- [ ] Kwargs struct is exported (if applicable)
- [ ] Alphabetical order maintained
```

## Example mod.rs Structure

```rust
// ABOUTME: This module contains Excel function implementations for Polars
// ABOUTME: Each function provides exact Excel compatibility including edge cases

// Module declarations (alphabetical)
mod abs;
mod average;
mod {{function_name}};  // New addition
mod sum;
mod yearfrac;

// Public exports (alphabetical)
pub use abs::abs;
pub use average::{average, AverageKwargs};
pub use {{function_name}}::{{{function_name}}, {{FunctionName}}Kwargs};  // New addition
pub use sum::sum;
pub use yearfrac::{yearfrac, YearFracKwargs};
```

## Multithreading Considerations

Since multiple functions may be implemented in parallel:

1. **Avoid direct edits**: Don't edit mod.rs directly during parallel processing
2. **Collect updates**: Save the required changes to add later
3. **Batch updates**: Apply all module updates at once after all functions are complete
4. **Use markers**: Add TODO markers if immediate update is needed

## Alternative for Parallel Processing

Instead of editing mod.rs directly, create a batch file:

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/08-mod-rs-additions.txt`:

```
// Add to module declarations section:
mod {{function_name}};

// Add to public exports section:
pub use {{function_name}}::{{{function_name}}, {{FunctionName}}Kwargs};
```

Then batch process all additions at once:
```bash
# After all functions are implemented
cat rust-functions-outputs/*-output/08-mod-rs-additions.txt | sort | uniq >> mod.rs.updates
```

## Verification Commands

```bash
# Check that the module compiles
cargo check

# Verify the function is exported
cargo doc --no-deps --open
# Look for your function in the documentation

# Run a quick test
cargo test {{function_name}}::tests::test --lib
```

## Common Issues

### 1. Module Not Found
```
error[E0583]: file not found for module `{{function_name}}`
```
**Fix**: Ensure the file exists at `src/excel/{{function_name}}.rs`

### 2. Function Not Exported
```
error[E0432]: unresolved import `gaspatchio_core_lib::excel::{{function_name}}`
```
**Fix**: Add the public export in mod.rs

### 3. Kwargs Not Found
```
error[E0412]: cannot find type `{{FunctionName}}Kwargs` in this scope
```
**Fix**: Export the Kwargs struct if the function uses one

## Next Step

Document any universal learnings in Step 9.