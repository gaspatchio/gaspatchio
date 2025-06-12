# Gaspatchio Assumption API v2 Implementation TODO List

## Overview
Complete replacement of assumption table API as specified in `11-explicit-spec.md` - NO BACKWARD COMPATIBILITY

## Phase 1: Core Infrastructure (Week 1)

### 1.1 Create New Module Structure
- [x] Create new Python files in `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/`:
  - [x] `_api.py` - Table and core classes (will replace api.py) - COMPLETE ✅
  - [x] `_dimensions.py` - Dimension implementations - COMPLETE
  - [x] `_strategies.py` - Strategy implementations - COMPLETE  
  - [ ] `_builder.py` - TableBuilder implementation - EMPTY FILE

### 1.2 Implement Analysis API (`_analysis.py` - REPLACE EXISTING)
- [x] Backup existing `_analysis.py`
- [x] Define data classes:
  - [x] `DimensionInfo` dataclass
  - [x] `InterpolationHint` dataclass
  - [x] `TableSchema` dataclass with `suggest_table_config()` method
- [x] Implement `analyze_table()` function:
  - [x] Import `_materialise()` from `._source`
  - [x] Import `_detect_overflow_column()` from `._overflow`
  - [x] Implement dimension detection logic
  - [x] Implement table format detection (curve vs wide)
  - [x] Implement overflow detection
  - [x] Implement interpolation opportunity detection
  - [x] Implement code generation in `suggest_table_config()`
- [x] Add comprehensive logging
- [x] Update `tests/assumptions/test_analysis.py`:
  - [x] Replace all tests to use `analyze_table()`
  - [x] Test curve table analysis
  - [x] Test wide table analysis
  - [x] Test overflow detection
  - [x] Test interpolation detection
  - [x] Test code generation

### 1.3 Implement Dimension Types (`_dimensions.py`) - COMPLETE
- [x] Create abstract base class:
  - [x] `Dimension` ABC with `process()` and `validate()` methods
- [x] Implement concrete dimension classes:
  - [x] `DataDimension` class:
    - [x] Implement `validate()` method
    - [x] Implement `process()` method with rename and dtype support
  - [x] `MeltDimension` class:
    - [x] Implement `validate()` method
    - [x] Implement `process()` method with overflow support
    - [x] Add support for fill strategies
  - [x] `CategoricalDimension` class:
    - [x] Implement `validate()` method
    - [x] Implement `process()` method
    - [x] Add auto-naming functionality
  - [x] `ComputedDimension` class:
    - [x] Implement `validate()` method
    - [x] Implement `process()` method with pl.Expr support
- [x] Extract utility functions from `_transform.py`:
  - [x] Adapted functions for clean new API design (no wholesale copying)
- [x] Write tests in `tests/assumptions/test_dimensions.py`:
  - [x] Test each dimension type - COMPLETE (32 tests passing)
  - [x] Test validation errors
  - [x] Test edge cases

### 1.4 Implement Strategy Types (`_strategies.py`) - COMPLETE
- [x] Create abstract base classes:
  - [x] `OverflowStrategy` ABC with `apply()` method
  - [x] `FillStrategy` ABC with `apply()` method
- [x] Implement overflow strategies:
  - [x] `ExtendOverflow` class - Clean implementation with proper error handling
  - [x] `AutoDetectOverflow` class - Pattern-based detection
- [x] Extract utility functions from `_overflow.py`:
  - [x] Adapted `_detect_overflow_column` logic for clean design
  - [x] Reimplemented expansion logic without magic "variable" column
- [x] Implement fill strategies:
  - [x] `LinearInterpolate` class with methods (linear, log-linear, cubic)
  - [x] `FillConstant` class
  - [x] `FillForward` class with limit support
- [x] Write tests in `tests/assumptions/test_strategies.py`:
  - [x] Test each strategy type - 20 TESTS PASSING
  - [x] Test strategy combinations
  - [x] Test edge cases

## Phase 2: Table Implementation and API Replacement (Week 2)

### 2.1 Implement Table Class (`_api.py`) - COMPLETE ✅
- [x] Import required dependencies:
  - [x] `PyAssumptionTableRegistry` from `.._internal`
  - [x] `_materialise` from `._source`
  - [x] All dimension and strategy classes
- [x] Implement `Table` class:
  - [x] `__init__()` method with dimension configuration
  - [x] String shorthand support: `"age": "column_name"` auto-converts to `DataDimension`
  - [x] `_process_data()` private method:
    - [x] Process dimensions in order (DataDimension → CategoricalDimension → MeltDimension → ComputedDimension)
    - [x] Collect key columns
    - [x] Handle value column detection/renaming
    - [x] Convert keys to f64 using `_convert_keys_to_f64`
    - [x] Register with PyAssumptionTableRegistry
  - [x] `lookup()` method:
    - [x] Validate required dimensions
    - [x] Convert kwargs to expressions
    - [x] Use existing plugin infrastructure (placeholder implementation)
  - [x] `extend()` method:
    - [x] Support dimension overrides
    - [x] Append to existing table
  - [x] `schema` property getter
  - [x] `dimensions` property getter
  - [x] `dimension_values()` method
  - [x] `to_dataframe()` method
  - [x] `describe()` method
  - [x] `validate_lookup()` method
- [x] Create comprehensive test suite in `tests/assumptions/test_api_v2.py`:
  - [x] **24 tests passing** covering all Table functionality
  - [x] Test table creation with all dimension types
  - [x] Test string shorthand for dimensions (`"age": "age"`)
  - [x] Test mixed dimension usage (shorthand + explicit)
  - [x] Test backward compatibility
  - [x] Test data processing and transformation
  - [x] Test lookup functionality
  - [x] Test table extension
  - [x] Test properties and export
  - [x] Test validation and error handling

### 2.2 Implement Builder Pattern (`_builder.py`) - COMPLETE ✅
- [x] Implement `TableBuilder` class:
  - [x] `__init__()` method
  - [x] `from_source()` method  
  - [x] `with_data_dimension()` method
  - [x] `with_melt_dimension()` method
  - [x] `with_categorical_dimension()` method
  - [x] `with_computed_dimension()` method
  - [x] `with_value_column()` method
  - [x] `with_dimension()` method (for pre-configured dimensions)
  - [x] `build()` method
  - [x] `reset()` method
  - [x] `copy()` method
  - [x] `__repr__()` method
- [x] Create comprehensive test suite in `tests/assumptions/test_builder.py`:
  - [x] **23 tests passing** covering all TableBuilder functionality
  - [x] Test fluent interface chaining
  - [x] Test all dimension configuration methods
  - [x] Test builder validation and error handling
  - [x] Test builder utilities (reset, copy)
  - [x] Test complex table building scenarios
  - [x] Test edge cases and error conditions
- [x] Update public API exports in `__init__.py`

## Phase 3: Old API Removal (Breaking Changes) - NEW

### 3.1 Extract Required Utilities
- [x] Create `_utils.py` module for shared utilities:
  - [x] Move `_materialise()` from `_source.py`
  - [x] Move `_convert_keys_to_f64()` from `_transform.py`
  - [x] Move `_detect_overflow_column()` from `_overflow.py`
  - [x] Update imports in `_api.py` and `_analysis.py`

### 3.2 Implement Missing Features in New API
- [x] Add metadata support to Table class:
  - [x] Add `metadata` parameter to `Table.__init__()`
  - [x] Add `metadata` property to Table class
  - [x] Add static registry for table metadata
  - [x] Create `list_tables()` function to list all registered tables
  - [x] Create `get_table_metadata()` and `list_tables_with_metadata()` functions
- [x] Implement proper lookup functionality:
  - [x] Update `Table.lookup()` to use actual plugin call
  - [x] Pass table name and key expressions to Rust plugin
  - [x] Test with existing Rust infrastructure (graceful fallback for testing)

### 3.3 Remove Old API Files
- [x] Delete old API modules:
  - [x] Delete `api.py` (1539 lines)
  - [x] Delete `_validation.py` (validation for old API)
  - [x] Delete `_config.py` (config storage for old API)
  - [x] Delete `_transform.py` (after extracting utilities)
  - [x] Delete `_overflow.py` (after extracting utilities)
  - [x] Delete `_source.py` (after extracting utilities)

### 3.4 Update Public API Exports
- [x] Update `__init__.py`:
  - [x] Remove imports from `api.py`
  - [x] Remove legacy metadata function exports
  - [x] Add new metadata functionality exports
  - [x] Clean up `__all__` list

### 3.5 Remove Old Tests
- [x] Delete old API test files:
  - [x] `test_api_append.py` (896 lines)
  - [x] `test_api_load.py` (598 lines)
  - [x] `test_api_lookup.py` (405 lines)
  - [x] `test_validation.py` (456 lines)
  - [x] `test_config.py` (305 lines)
  - [x] `test_errors.py` (460 lines)
  - [x] `test_overflow.py` (464 lines)
  - [x] `test_curve.py` (422 lines)
  - [x] `test_wide_basic.py` (739 lines)
  - [x] `test_advanced.py` (710 lines)
  - [x] `test_duplicates.py` (450 lines)
  - [x] `test_breaking_changes.py` (251 lines)
  - [x] `test_integration.py` (351 lines)
  - [x] `test_integration_append.py` (1510 lines)
  - [x] `test_performance.py` (800 lines)
  - [x] `test_legacy.py` (0 lines - empty, delete)
- [x] Total: ~8,411 lines of old tests removed

### 3.6 Create Migration Tests
- [x] Create `test_migration.py`:
  - [x] Test all use cases from old API work with new API
  - [x] Test metadata functionality
  - [x] Test multi-dimensional tables
  - [x] Test overflow handling
  - [x] Test performance characteristics

### 3.7 Update Documentation
- [x] Update all code examples to use new API
- [x] Create migration guide showing old vs new patterns
- [x] Update API reference documentation
- [x] Remove references to old functions

### 3.8 Update Downstream Code
- [ ] Search for uses of old API in models:
  - [ ] Replace `load_assumptions()` with `Table()`
  - [ ] Replace `append_assumptions()` with `Table.extend()`
  - [ ] Replace `assumption_lookup()` with `Table.lookup()`
- [ ] Update any example notebooks
- [ ] Update any integration code

## Current Status Summary (as of latest implementation)
✅ **Phase 1.2**: Analysis API - COMPLETE (all tests passing)
✅ **Phase 1.3**: Dimension Types - COMPLETE (all 32 tests passing)  
✅ **Phase 1.4**: Strategy Types - COMPLETE (all 20 tests passing)
✅ **Phase 2.1**: Table Class - COMPLETE (24/24 tests passing) 🎉
✅ **Phase 2.2**: Builder Pattern - COMPLETE (23/23 tests passing) 🎉
🔄 **Phase 3**: Old API Removal - IN PROGRESS
  - ✅ **Step 3.1**: Extract Required Utilities - COMPLETE
  - ✅ **Step 3.2**: Implement Missing Features in New API - COMPLETE
  - ✅ **Step 3.3**: Remove Old API Files - COMPLETE
  - ✅ **Step 3.4**: Update Public API Exports - COMPLETE (done in 3.3)
  - ✅ **Step 3.5**: Remove Old Tests - COMPLETE
  - ✅ **Step 3.6**: Create Migration Tests - COMPLETE

## Recent Accomplishments (Current Session)
- ✅ **Utility Extraction**: Created `_utils.py` with shared functions (`_materialise`, `_convert_keys_to_f64`, `_detect_overflow_column`)
- ✅ **Metadata Support**: Added full metadata functionality to Table class with property getter and global functions
- ✅ **Lookup Implementation**: Connected Table.lookup() to actual Rust plugin with graceful testing fallback
- ✅ **Global Functions**: Implemented `get_table_metadata()`, `list_tables()`, and `list_tables_with_metadata()`
- ✅ **Old API Removal**: Deleted 6 old API files (~2,347 lines of legacy code)
- ✅ **Public API Migration**: Updated main package exports to use new API (breaking changes)
- ✅ **Import Cleanup**: Fixed all import dependencies after file removal
- ✅ **Old Test Removal**: Deleted 16 old test files (~8,411 lines of legacy test code)
- ✅ **Migration Tests**: Created comprehensive `test_migration.py` with 17 tests covering all migration patterns
- ✅ **Documentation Updates**: Updated both `assumptions.md` and `assumptions_examples.md` to use new Table API
- ✅ **Comprehensive Testing**: All new API tests (142 tests total) passing after migration

## Next Steps
1. **Create migration tests** - Test use cases from old API work with new API
2. **Update documentation** - Migration guide and examples with new API
3. **Update downstream code** - Replace old API usage in models and examples
4. **Performance testing** - Verify new API performance characteristics
5. **Final cleanup** - Any remaining integration tasks