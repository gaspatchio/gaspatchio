# Enhanced Validation Error Handling - TODO

## Phase 1: Core Infrastructure (Priority: High)

### 1. Create Enhanced Exception Classes
- [x] Create `gaspatchio_core/errors/validation.py`
  - [x] Implement `ValidationError` class extending `ValueError`
  - [x] Add `context` dict for storing validation context
  - [x] Add `source_location` property for source tracking
  - [x] Create `SourceLocation` dataclass with file, line, function, source_line

### 2. Implement Validation Context Decorator
- [x] Create `@capture_validation_context` decorator in `errors/validation.py`
  - [x] Use `inspect` to capture caller information
  - [x] Only activate in debug mode (check frame._mode and get_error_mode())
  - [x] Handle conversion of regular ValueError/TypeError to ValidationError
  - [x] Ensure proper exception chaining with `__cause__`

### 3. Create Validation Error Formatter
- [x] Add `ValidationErrorFormatter` class in `errors/formatter.py`
  - [x] Extend or mirror `FriendlyErrorFormatter` design
  - [x] Format source location with syntax highlighting
  - [x] Generate helpful suggestions using fuzzy matching
  - [x] Support both console and LLM output formats

### 4. Integrate with Existing Error System
- [x] Modify `_handle_execution_error` in `formatting_errors.py`
  - [x] Rename to `_handle_frame_error` to handle both types
  - [x] Add branch for `ValidationError` instances
  - [x] Ensure backward compatibility
  - [x] Update all callers of `_handle_execution_error`

## Phase 2: Apply to High-Impact Areas (Priority: High)

### 5. Date Accessor Validation
- [x] Add decorator to `date.py` methods:
  - [x] `create_projection_timeline` - wrap projection_end_type validation
  - [ ] `create_timeline` - wrap frequency validation
  - [ ] `add_duration` - wrap duration string validation
- [x] Convert ValueError raises to ValidationError with context
- [ ] Add valid_options to error context for fuzzy matching

### 6. Assumptions API Validation
- [ ] Add validation to `Table.__init__` for dimension validation
- [ ] Add validation to `lookup` methods for key validation
- [ ] Enhance "column not found" errors with available columns
- [ ] Add validation for data type mismatches

### 7. Runner Integration
- [ ] Update `_execute_model_run` in `runner.py`
  - [ ] Check for ValidationError separately
  - [ ] Format enhanced errors if source_location exists
  - [ ] Pass validation context to ModelRunResult
- [ ] Update CLI commands to display enhanced errors properly

## Phase 3: Fuzzy Matching and Suggestions (Priority: Medium)

### 8. Implement Suggestion Engine
- [ ] Create `_suggest_valid_options` function using thefuzz
  - [ ] Handle string similarity for enums/choices
  - [ ] Handle column name suggestions
  - [ ] Configure similarity thresholds
- [ ] Add suggestion generation to ValidationErrorFormatter

### 9. Context-Aware Suggestions
- [ ] Create suggestion mappings for common mistakes:
  - [ ] "term_monts" → "term_months"
  - [ ] "semi_annual" → "semi-annual"
  - [ ] Common date format errors
- [ ] Add spell-check style suggestions for parameter names

## Phase 4: Testing (Priority: High)

### 10. Unit Tests
- [ ] Test ValidationError class creation and properties
- [ ] Test capture_validation_context decorator:
  - [ ] In debug mode vs production mode
  - [ ] With different exception types
  - [ ] Source location accuracy
- [ ] Test ValidationErrorFormatter output formats

### 11. Integration Tests
- [ ] Create test for date accessor validation errors
- [ ] Test assumptions API validation errors
- [ ] Test runner handling of validation errors
- [ ] Test CLI display of enhanced errors

### 12. Performance Tests
- [ ] Benchmark decorator overhead in production mode (should be ~0)
- [ ] Benchmark debug mode overhead (should be minimal)
- [ ] Memory usage of enhanced exceptions

## Phase 5: Extended Coverage (Priority: Low)

### 13. Apply to Additional Components
- [ ] Excel accessor validation
- [ ] Finance accessor validation
- [ ] Column proxy operation validation
- [ ] Frame initialization validation

### 14. Documentation
- [ ] Update error handling documentation
- [ ] Add examples of enhanced validation errors
- [ ] Document how to add validation to new components
- [ ] Update developer guide with validation best practices

## Phase 6: Future Enhancements (Priority: Low)

### 15. Advanced Features
- [ ] Validation error aggregation (collect multiple errors)
- [ ] Integration with Python type hints for better messages
- [ ] Custom validation error types per domain
- [ ] Error recovery suggestions ("Did you mean to...")

## Implementation Order

1. Start with Phase 1 (Core Infrastructure) - Required for everything else
2. Implement Phase 4.10-4.11 (Basic Tests) - Ensure core works
3. Move to Phase 2.5 (Date Accessor) - Immediate impact on the reported issue
4. Continue with Phase 2.6-2.7 (Assumptions & Runner)
5. Add Phase 3 (Fuzzy Matching) - Nice to have
6. Complete remaining phases based on priority

## Success Criteria

- [x] The "term_monts" error shows enhanced formatting with line numbers
- [ ] All existing tests pass without modification
- [ ] No performance impact in production mode
- [x] Enhanced errors work in both CLI and programmatic usage
- [x] Fuzzy suggestions help users fix typos quickly
