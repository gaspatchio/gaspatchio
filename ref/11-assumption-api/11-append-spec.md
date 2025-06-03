# Assumption Table Append Functionality Specification

## Overview

Enable appending multiple data sources to a single assumption table with additional keys for multi-dimensional lookups, replacing the current pattern of multiple separate tables.

## Current vs Proposed Architecture

### Current (4 separate tables)
```python
gs.load_assumptions("mortality_cso_fsm", "2017-CSO-FSM-ANB.csv")
gs.load_assumptions("mortality_cso_msm", "2017-CSO-MSM-ANB.csv") 
gs.load_assumptions("mortality_cso_fns", "2017-CSO-FNS-ANB.csv")
gs.load_assumptions("mortality_cso_mns", "2017-CSO-MNS-ANB.csv")

# Complex lookup with table name logic
table_name = f"mortality_cso_{sex}{smoking}"
rate = gs.assumption_lookup("issue_age", "year", table_name=table_name)
```

### Proposed (single appended table)
```python
gs.load_assumptions("mortality_cso", "2017-CSO-FSM-ANB.csv", 
                   additional_keys={"sex": "F", "smoking": "SM"})
gs.append_assumptions("mortality_cso", "2017-CSO-MSM-ANB.csv",
                     additional_keys={"sex": "M", "smoking": "SM"})
gs.append_assumptions("mortality_cso", "2017-CSO-FNS-ANB.csv", 
                     additional_keys={"sex": "F", "smoking": "NS"})
gs.append_assumptions("mortality_cso", "2017-CSO-MNS-ANB.csv",
                     additional_keys={"sex": "M", "smoking": "NS"})

# Clean single lookup
rate = gs.assumption_lookup("sex", "smoking", "issue_age", "year",
                          table_name="mortality_cso")
```

## Core Requirements

### 1. Extended load_assumptions Function
- Add `additional_keys: dict[str, Any] | None = None` parameter
- Additional keys become columns in the processed DataFrame
- Store table configuration for append compatibility validation

### 2. New append_assumptions Function
- Signature: `append_assumptions(name, source, *, additional_keys, **kwargs)`
- Validate compatibility with existing table configuration
- Process new data through same transformation pipeline
- Use direct hashmap insertion approach for optimal performance

### 3. Validation System
- **Table existence**: Verify table exists before append/lookup
- **Schema compatibility**: Ensure append data matches existing table structure
- **Key validation**: Validate lookup keys match table schema
- **Model column validation**: Ensure ActuarialFrame has required columns
- **Duplicate key prevention**: Prevent conflicting additional_keys values

### 4. Enhanced assumption_lookup Function
- Add comprehensive validation with clear error messages
- Validate table exists, key count/names match, model columns present
- Optional `validate: bool = True` parameter for performance scenarios

## Implementation Strategy

### Python Module Structure
```
gaspatchio_core/assumptions/
├── api.py              # Enhanced with append_assumptions (existing)
├── _config.py          # Table configuration management (NEW)
├── _validation.py      # Validation logic (NEW)
├── _source.py          # Data materialization (existing, unchanged)
├── _analysis.py        # DataFrame analysis (existing, unchanged)
├── _transform.py       # Data transformation (existing, unchanged)
└── _overflow.py        # Overflow handling (existing, unchanged)
```

### Rust Changes
- Add `append_to_table` method to AssumptionTableRegistry
- Add `append_entries` method to AssumptionTable for direct hashmap insertion
- Add table metadata methods: `get_key_count()`, `get_key_columns()`, `get_key_name()`
- Enhanced validation in lookup functions

### Storage Architecture
- **Python**: Store table configurations (small dictionaries) for validation
- **Rust**: Store only lookup structures (hashmaps) - no DataFrame storage
- **Direct insertion**: New entries inserted directly into existing hashmap
- **Optimal memory**: Most memory-efficient approach with no data duplication

## Error Handling

### Validation Errors
```python
# Invalid additional_keys format
ValueError: "additional_keys must be a dictionary"

# Configuration mismatch
ValueError: "Value column name must match existing table: original='rate', new='value'"

# Duplicate keys
ValueError: "Cannot append data with identical additional_keys values"

# Table not found
ValueError: "Assumption table 'missing_table' not found. Available tables: ['mortality_cso']"

# Key count mismatch
ValueError: "Key count mismatch for table 'mortality_cso'. Expected 4 keys: ['sex', 'smoking', 'issue_age', 'year'], got 1: ['age']"

# Missing model columns
ValueError: "Model points data missing required columns for lookup: ['issue_age']. Available columns: ['age', 'sex']"
```

## Performance Characteristics

- **Append Performance**: O(n) where n = new entries, direct hashmap insertion
- **Lookup Performance**: Identical to current implementation, no degradation
- **Memory Usage**: Minimal increase, stores only configurations and lookup structures
- **Validation Performance**: O(n) duplicate key checking, early failure on conflicts

## Testing Strategy

### Unit Tests
- `additional_keys` parameter functionality
- Compatibility validation logic
- Error handling and messages
- Direct hashmap insertion

### Integration Tests
- Full multi-dimensional table workflow
- Model points integration with validation
- Performance benchmarking
- Migration from existing patterns

## Migration Path

1. **Phase 1**: Add core functionality with backward compatibility
2. **Phase 2**: Enhance validation and error messages
3. **Phase 3**: Performance optimizations and advanced features
4. **Phase 4**: Migration utilities for existing code

## Success Criteria

- [ ] Single table replaces multiple related tables
- [ ] Clean, intuitive API for multi-dimensional lookups
- [ ] Comprehensive validation with clear error messages
- [ ] No performance degradation for lookups
- [ ] Full backward compatibility with existing code
- [ ] Robust error handling prevents runtime failures in models

---

# Implementation Plan and LLM Prompts

## Implementation Breakdown

The implementation is broken down into 8 incremental steps, each building on the previous step with comprehensive testing:

### Step 1: Configuration Management Foundation
Create the `_config.py` module for table configuration storage and management.

### Step 2: Basic Validation Framework
Create the `_validation.py` module with core validation functions.

### Step 3: Enhanced load_assumptions with additional_keys
Extend the existing `load_assumptions` function to support `additional_keys` parameter.

### Step 4: Basic append_assumptions Function
Implement the core `append_assumptions` function with compatibility validation.

### Step 5: Rust Table Metadata Extensions
Add metadata methods to Rust AssumptionTable for validation support.

### Step 6: Enhanced Lookup Validation
Add comprehensive validation to `assumption_lookup` function.

### Step 7: Rust Append Implementation
Implement direct hashmap insertion for append functionality in Rust.

### Step 8: Integration and Testing
Wire everything together with comprehensive integration tests.

---

## LLM Implementation Prompts

### Prompt 1: Configuration Management Foundation

```
Create the `_config.py` module for table configuration management in gaspatchio_core.assumptions.

Context: This is part of implementing append functionality for assumption tables. We need a module to store and manage table configurations for compatibility validation.

Requirements:
1. Create `gaspatchio_core/assumptions/_config.py` module
2. Implement global storage for table configurations using a dictionary
3. Add functions for storing, retrieving, and checking table configurations
4. Include proper type hints and docstrings
5. Add debug logging using loguru

Functions needed:
- `_store_table_config(name: str, config: dict) -> None`
- `_get_table_config(name: str) -> dict` 
- `_table_exists(name: str) -> bool`
- `_list_configured_tables() -> list[str]`

Implementation details:
- Use global `_TABLE_CONFIGS: Dict[str, Dict[str, Any]] = {}` for storage
- Store copies of configurations to prevent mutation
- Raise ValueError with helpful message if table not found
- Include debug logging for configuration operations

Write comprehensive unit tests in `tests/assumptions/test_config.py`:
- Test storing and retrieving configurations
- Test table existence checking
- Test error handling for missing tables
- Test configuration immutability (copies not references)
- Test listing configured tables

The module should follow the existing code style and patterns from the assumptions module.
```

### Prompt 2: Basic Validation Framework

```
Create the `_validation.py` module for validation logic in gaspatchio_core.assumptions.

Context: Building on the _config.py module from the previous step, we need validation functions for append compatibility and parameter validation.

Requirements:
1. Create `gaspatchio_core/assumptions/_validation.py` module
2. Import necessary dependencies including _config functions
3. Implement validation functions with comprehensive error messages
4. Use proper type hints and docstrings
5. Add appropriate logging

Functions needed:
- `_validate_additional_keys(additional_keys: dict[str, Any] | None) -> None`
- `_validate_append_compatibility(original_config: dict, new_config: dict) -> None`

Implementation details:
- `_validate_additional_keys`: Check format, non-empty keys, proper types
- `_validate_append_compatibility`: Compare critical parameters (value, overflow, max_overflow), validate additional_keys structure, check for duplicate key combinations
- Include detailed error messages explaining what went wrong and what's expected
- Use the _config module functions for table existence checks

Write comprehensive unit tests in `tests/assumptions/test_validation.py`:
- Test additional_keys validation with various invalid inputs
- Test compatibility validation with matching configs (should pass)
- Test compatibility validation with mismatched parameters (should fail)  
- Test duplicate additional_keys detection
- Test error message quality and clarity
- Test edge cases (None values, empty dictionaries, etc.)

Make sure the validation logic is thorough and provides actionable error messages.
```

### Prompt 3: Enhanced load_assumptions with additional_keys

```
Enhance the existing `load_assumptions` function in `api.py` to support the `additional_keys` parameter.

Context: Building on _config.py and _validation.py modules, we need to extend the current load_assumptions function to support additional keys and store configurations.

Requirements:
1. Add `additional_keys: dict[str, Any] | None = None` parameter to existing `load_assumptions` function
2. Import and use the new _config and _validation modules
3. Maintain full backward compatibility
4. Add configuration storage for future append operations
5. Process additional_keys as new columns in the DataFrame

Implementation details:
- Import: `from ._config import _store_table_config` and `from ._validation import _validate_additional_keys`
- Add parameter validation early in the function
- After `_materialise(source)`, add additional_keys as literal columns using `df.with_columns(pl.lit(value).alias(key))`
- After successful table registration, store the configuration using `_store_table_config`
- Store all relevant parameters: id, value, value_vars, overflow, max_overflow, lookup_keys, additional_keys

Configuration storage format:
```python
config = {
    'id': id,
    'value': value, 
    'value_vars': value_vars,
    'overflow': overflow,
    'max_overflow': max_overflow,
    'lookup_keys': lookup_keys,
    'additional_keys': additional_keys
}
```

Write comprehensive unit tests in `tests/assumptions/test_api_load.py`:
- Test load_assumptions with additional_keys creates correct columns
- Test configuration is stored correctly
- Test backward compatibility (existing code still works)
- Test additional_keys validation integration
- Test various additional_keys formats (different types, multiple keys)
- Test that literal values are applied correctly to all rows
- Test integration with existing transformation pipeline

Ensure all existing load_assumptions functionality remains unchanged and working.
```

### Prompt 4: Basic append_assumptions Function

```
Implement the `append_assumptions` function in `api.py` with full compatibility validation.

Context: Building on the enhanced load_assumptions with configuration storage, implement the append functionality that validates compatibility and processes data through the same pipeline.

Requirements:
1. Add `append_assumptions` function to `api.py`
2. Use existing transformation pipeline from load_assumptions
3. Implement comprehensive compatibility validation
4. Maintain the same function signature pattern as load_assumptions
5. Register appended data with the existing Rust registry

Function signature:
```python
def append_assumptions(
    name: str,
    source: Union[str, Path, pl.DataFrame],
    *,
    additional_keys: dict[str, Any],  # REQUIRED for append
    id: Union[str, list[str], None] = None,
    value: str = "rate",
    value_vars: Union[list[str], None] = None,
    overflow: Union[Literal["auto"], str, None] = "auto",
    max_overflow: int = 200,
    metadata: dict[str, Any] | None = None,
    lookup_keys: Union[list[str], None] = None,
) -> pl.DataFrame:
```

Implementation details:
- Validate table exists using `_table_exists`
- Get original configuration using `_get_table_config`
- Build new configuration and validate compatibility using `_validate_append_compatibility`
- Process data through same pipeline as load_assumptions (_materialise, add additional_keys, transform, etc.)
- For now, use the existing `register_table` function (we'll enhance this in later steps)
- Include comprehensive error handling and logging

Write comprehensive unit tests in `tests/assumptions/test_api_append.py`:
- Test basic append functionality with compatible data
- Test compatibility validation errors (mismatched parameters)
- Test duplicate additional_keys detection
- Test that data goes through same transformation pipeline
- Test error handling for non-existent tables
- Test various parameter combinations
- Test that appended data is accessible through existing lookup mechanisms
- Test required additional_keys parameter

Focus on getting the validation and data processing pipeline working correctly.
```

### Prompt 5: Rust Table Metadata Extensions

```
Extend the Rust AssumptionTable with metadata methods for validation support.

Context: The validation system needs to query table metadata (key count, key names) from Rust. Add these methods to support the validation framework.

Requirements:
1. Add metadata methods to `AssumptionTable` struct in Rust
2. Expose methods through PyO3 bindings for Python access
3. Maintain existing functionality and performance
4. Add proper error handling

Methods needed in `AssumptionTable`:
- `get_key_count() -> usize`
- `get_key_columns() -> Vec<String>`  
- `get_key_name(index: usize) -> PolarsResult<String>`

Methods needed in `AssumptionTableRegistry`:
- `list_tables() -> Vec<String>`
- `table_exists(name: &str) -> bool`

Implementation details:
- Store key information in AssumptionTable during build() 
- `get_key_count`: Return length of keys vector
- `get_key_columns`: Return clone of keys vector
- `get_key_name`: Return key at index with bounds checking
- `list_tables`: Return all registered table names
- `table_exists`: Check if table name exists in registry

Python binding updates:
- Expose new methods through PyO3 in the Python wrapper classes
- Add proper error handling for out-of-bounds access
- Maintain existing naming conventions

Write unit tests in Rust:
- Test metadata methods return correct information
- Test error handling for invalid indices
- Test registry methods work correctly
- Test integration with existing table building process

Write Python integration tests in `tests/assumptions/test_rust_metadata.py`:
- Test metadata methods accessible from Python
- Test error handling translates correctly
- Test integration with table registration process

The goal is to provide the metadata needed for validation without impacting performance.
```

### Prompt 6: Enhanced Lookup Validation

```
Add comprehensive validation to the `assumption_lookup` function in `api.py`.

Context: Building on the Rust metadata extensions, implement full validation for assumption lookups to provide clear error messages and prevent runtime failures.

Requirements:
1. Enhance existing `assumption_lookup` function with validation
2. Add `validate: bool = True` parameter for optional validation
3. Implement table existence, key validation, and clear error messages
4. Maintain existing lookup performance when validation disabled
5. Use the new Rust metadata methods

Validation needed:
- Table existence validation
- Key count and name validation  
- Clear, actionable error messages
- Support for both string and expression keys

Implementation details:
- Add validation parameter: `validate: bool = True`
- When validation enabled, extract column names from keys (strings and simple expressions)
- Use registry methods to validate table exists and get metadata
- Validate key count matches table schema
- Validate key names match table schema (order-sensitive)
- Provide helpful error messages with available tables/keys
- Skip validation for complex expressions (with clear documentation)

Enhanced function signature:
```python
def assumption_lookup(
    *keys: IntoExpr, 
    table_name: str, 
    validate: bool = True
) -> pl.Expr:
```

Error message examples:
- "Assumption table 'missing_table' not found. Available tables: ['mortality_cso', ...]"
- "Key count mismatch for table 'mortality_cso'. Expected 4 keys: ['sex', 'smoking', 'issue_age', 'year'], got 1: ['age']"
- "Key name mismatch at position 1 for table 'mortality_cso'. Expected 'smoking', got 'gender'"

Write comprehensive unit tests in `tests/assumptions/test_api_lookup.py`:
- Test validation with correct table and keys (should pass)
- Test table not found error
- Test key count mismatch error  
- Test key name mismatch error
- Test validation disabled works correctly
- Test complex expressions skip validation appropriately
- Test error message quality and helpfulness
- Test backward compatibility (existing code works)

Focus on providing excellent developer experience through clear validation errors.
```

### Prompt 7: Rust Append Implementation

```
Implement direct hashmap insertion for append functionality in Rust.

Context: Building on all previous steps, implement the core append logic in Rust using direct hashmap insertion for optimal performance.

Requirements:
1. Add `append_entries` method to `AssumptionTable`
2. Add `append_to_table` method to `AssumptionTableRegistry`
3. Add global `append_to_assumption_table_global` function
4. Implement duplicate key validation
5. Use direct hashmap insertion for optimal performance

Methods needed:

`AssumptionTable::append_entries`:
- Convert DataFrame to hashmap entries using existing build logic
- Validate no duplicate keys exist
- Insert entries directly into existing lookup_map
- Update metadata (entry count, etc.)

`AssumptionTableRegistry::append_to_table`:
- Get existing table by name
- Call append_entries on the table
- Handle errors appropriately

Global function:
- `append_to_assumption_table_global(name, df, keys, value_column)` 
- Use same locking pattern as existing registration
- Update global registry atomically

Implementation details:
- Extract hashmap building logic from existing `build()` method into reusable function
- Validate duplicate keys before any insertion (fail fast)
- Use `HashMap::extend` for efficient insertion
- Provide detailed error messages for duplicate keys
- Maintain thread safety with existing locking mechanisms

Python integration:
- Update Python bindings to expose new append function
- Update `append_assumptions` in `api.py` to use new Rust function instead of register_table
- Maintain same error handling patterns

Write Rust unit tests:
- Test append_entries with valid data
- Test duplicate key detection and error handling
- Test hashmap insertion correctness
- Test metadata updates
- Test thread safety

Write Python integration tests in `tests/assumptions/test_rust_append.py`:
- Test Python to Rust append integration
- Test error propagation from Rust to Python
- Test performance compared to rebuild approach
- Test data correctness after append

The goal is efficient append operations with robust duplicate detection.
```

### Prompt 8: Integration and Testing

```
Wire everything together and create comprehensive integration tests for the complete append functionality.

Context: All individual components are now implemented. Create integration tests and ensure everything works together seamlessly.

Requirements:
1. Update Python module exports in `__init__.py`
2. Create comprehensive integration tests
3. Test complete workflows from load through append to lookup
4. Test error scenarios end-to-end
5. Validate performance characteristics
6. Create usage examples and documentation

Integration tasks:
- Export `append_assumptions` from `__init__.py`
- Ensure all error paths work correctly
- Test memory usage and performance
- Validate thread safety
- Test with real-world data patterns

Create integration test file `tests/assumptions/test_integration_append.py`:

Test scenarios:
1. **Complete multi-dimensional workflow**:
   - Load base table with additional_keys
   - Append multiple datasets with different additional_keys
   - Perform lookups and validate results
   - Test all combinations work correctly

2. **Error handling workflows**:
   - Test complete error scenarios (table not found, compatibility errors, etc.)
   - Verify error messages are helpful and actionable
   - Test error recovery and retry scenarios

3. **Real-world usage patterns**:
   - Replicate the 4-table mortality scenario from the spec
   - Test large datasets and performance
   - Test memory usage patterns
   - Test concurrent access if applicable

4. **Backward compatibility**:
   - Ensure existing code continues to work
   - Test migration from old patterns to new patterns
   - Verify no regressions in performance

5. **Edge cases**:
   - Empty datasets
   - Single-row appends
   - Large number of appends
   - Complex additional_keys values

Create example usage documentation:
- Show complete workflow examples
- Document best practices
- Show migration from old patterns
- Include performance tips

Performance benchmarks:
- Compare append vs rebuild approaches
- Memory usage analysis
- Lookup performance validation
- Scalability testing

The goal is a fully integrated, tested, and documented append functionality that enhances the assumption system while maintaining all existing capabilities.
```

---

## Summary

This implementation plan breaks down the append functionality into 8 manageable steps:

1. **Foundation** (Steps 1-2): Core infrastructure with configuration and validation
2. **API Enhancement** (Steps 3-4): Python API extensions with full compatibility 
3. **Rust Extensions** (Steps 5-7): Metadata support and efficient append implementation
4. **Integration** (Step 8): Complete testing and documentation

Each step builds incrementally on the previous steps with comprehensive testing, ensuring:
- No big jumps in complexity
- Strong test coverage at each stage
- Early validation of architectural decisions
- Continuous integration and working functionality
- Clear error handling and user experience

The prompts are designed to be self-contained but build on each other, providing the context and specific requirements needed for successful implementation.
