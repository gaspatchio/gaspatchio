# Step 8: Update Module Exports

Add the new function to the Excel module exports.

## Input
- Function name: `{{FUNCTION_NAME}}`
- Implementation file created in Step 5

## Process

1. **Update src/excel/mod.rs**:
   - Add implementation module declaration
   - Add test module declaration (with #[cfg(test)])
   - Add public exports
   - Maintain alphabetical order

2. **Verify the exports**:
   - Check compilation
   - Ensure function is accessible
   - Ensure tests can be run

## Implementation Steps

1. **Add implementation module declaration**:
   ```rust
   // In src/excel/mod.rs - add to module declarations section
   pub mod {{function_name}};
   ```

2. **Add test module declaration**:
   ```rust
   // In src/excel/mod.rs - add after implementation module
   #[cfg(test)]
   mod {{function_name}}_tests;
   ```

3. **Add public exports**:
   ```rust
   // In the public exports section
   pub use {{function_name}}::{{{function_name}}, {{function_name}}_output_type};
   ```

4. **Export Kwargs if needed**:
   ```rust
   // If function has kwargs
   pub use {{function_name}}::{{FunctionName}}Kwargs;
   ```

## Output Format

Create `rust-functions-outputs/{{FUNCTION_NAME}}-output/08-module-updates.md`:

```markdown
# Module Export Updates for {{FUNCTION_NAME}}

## Added to src/excel/mod.rs:

### Implementation module declaration:
```rust
pub mod {{function_name}};
```

### Test module declaration:
```rust
#[cfg(test)]
mod {{function_name}}_tests;
```

### Public exports:
```rust
pub use {{function_name}}::{{{function_name}}, {{function_name}}_output_type};
pub use {{function_name}}::{{FunctionName}}Kwargs;
```

## Verification:
- [ ] Implementation module compiles successfully
- [ ] Test module compiles successfully
- [ ] Function and output type are exported
- [ ] Kwargs struct is exported (if applicable)
- [ ] Tests can be run with `cargo test {{function_name}}`
- [ ] Alphabetical order maintained
```

## Example mod.rs Structure

```rust
// ABOUTME: This module contains Excel function implementations for Polars
// ABOUTME: Each function provides exact Excel compatibility including edge cases

// Implementation module declarations (alphabetical)
pub mod abs;
pub mod average;
pub mod {{function_name}};  // New addition
pub mod sum;
pub mod yearfrac;

// Public exports (alphabetical)
pub use abs::{abs, abs_output_type};
pub use average::{average, average_output_type, AverageKwargs};
pub use {{function_name}}::{{{function_name}}, {{function_name}}_output_type, {{FunctionName}}Kwargs};  // New addition
pub use sum::{sum, sum_output_type};
pub use yearfrac::{yearfrac, yearfrac_output_type, YearFracKwargs};

// Test module declarations (alphabetical)
#[cfg(test)]
mod abs_tests;
#[cfg(test)]
mod average_tests;
#[cfg(test)]
mod {{function_name}}_tests;  // New addition
#[cfg(test)]
mod sum_tests;
#[cfg(test)]
mod yearfrac_tests;
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
// Add to implementation module declarations section:
pub mod {{function_name}};

// Add to public exports section:
pub use {{function_name}}::{{{function_name}}, {{function_name}}_output_type, {{FunctionName}}Kwargs};

// Add to test module declarations section:
#[cfg(test)]
mod {{function_name}}_tests;
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

# Run the function's tests
cargo test {{function_name}} --lib

# Run tests in the specific test module
cargo test {{function_name}}_tests --lib
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