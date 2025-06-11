# Enhanced Compilation Error Handling - TODO List

## Overview
This document tracks the implementation tasks for enhanced compilation error handling as specified in `13-compilation-spec-v2.md`.

**Key Decisions**:
- No feature flags - compilation error replay is always enabled in enhanced/debug modes
- `AF_ERROR_MODE=enhanced` becomes the default (was `basic`)
- Leverages existing error handling components with minimal new code

**Status**: 🔴 Not Started | 🟡 In Progress | 🟢 Completed | ⏸️ Blocked

---

## Phase 1: Core Infrastructure (Day 1)

### 1.1 Error Detection and Routing
- [ ] 🔴 Add `_is_compilation_error()` function to `formatting_errors.py`
  - [ ] Detect "FAILED HERE RESOLVING" pattern
  - [ ] Detect "got invalid or ambiguous dtypes" pattern
  - [ ] Detect `pl.exceptions.ComputeError` type
  - [ ] Detect `ColumnNotFoundError` with compilation context
  - [ ] Write unit tests for detection logic

- [ ] 🔴 Modify `_handle_execution_error()` to route compilation errors
  - [ ] Add compilation error detection check
  - [ ] Route to new handler when detected
  - [ ] Preserve existing execution error path
  - [ ] Add logging for routing decisions

- [ ] 🔴 Create `_handle_compilation_error_enhanced()` function
  - [ ] Check for computation graph existence
  - [ ] Convert operations to TracedOperation format
  - [ ] Call CompilationErrorFinder
  - [ ] Handle fallback scenarios

### 1.2 CompilationErrorFinder Implementation
- [ ] 🔴 Create new file `gaspatchio_core/errors/compilation_finder.py`
  - [ ] Define `CompilationErrorFinder` class
  - [ ] Implement `__init__` method
  - [ ] Add error type checking logic
  - [ ] Add logging throughout

- [ ] 🔴 Implement `find_failing_operation()` method
  - [ ] Extract operations from computation graph
  - [ ] Handle empty graph case
  - [ ] Implement main search loop
  - [ ] Return tuple of (index, operation, last_good_df)

- [ ] 🔴 Implement `_apply_single_operation()` method
  - [ ] Apply operation to dataframe
  - [ ] Handle operation application errors
  - [ ] Add operation context to errors

- [ ] 🔴 Implement `_safe_collect()` method
  - [ ] Implement limited row collection
  - [ ] Add fallback to schema-only collection
  - [ ] Handle collection failures gracefully
  - [ ] Add configurable row limit

---

## Phase 2: Enhanced Context and Formatting (Day 1-2)

### 2.1 Context Collection
- [ ] 🔴 Implement `_get_original_dataframe()` method
  - [ ] Handle LazyFrame conversion
  - [ ] Handle empty/None dataframes
  - [ ] Preserve original schema

- [ ] 🔴 Implement `_is_same_compilation_error()` method
  - [ ] Compare error types
  - [ ] Compare error messages intelligently
  - [ ] Handle error message variations

- [ ] 🔴 Add intermediate state collection
  - [ ] Collect schema at each step
  - [ ] Store column type information
  - [ ] Track shape changes

### 2.2 Error Formatting
- [ ] 🔴 Create `_format_compilation_error_with_context()` function
  - [ ] Extract error details from exception
  - [ ] Build structured error message
  - [ ] Add emoji indicators
  - [ ] Format for console display

- [ ] 🔴 Implement `_extract_compilation_error_details()` function
  - [ ] Parse missing column names
  - [ ] Extract type mismatch information
  - [ ] Identify error category
  - [ ] Handle various error formats

- [ ] 🔴 Implement `_format_dataframe_preview()` function
  - [ ] Format dataframe for display
  - [ ] Handle empty dataframes
  - [ ] Limit column width
  - [ ] Add proper indentation

- [ ] 🔴 Implement `_format_operation_chain()` function
  - [ ] Show successful operations with ✓
  - [ ] Highlight failing operation with ❌
  - [ ] Show unreached operations with ⚠️
  - [ ] Truncate long expressions

- [ ] 🔴 Implement `_format_column_list()` function
  - [ ] Group columns by type
  - [ ] Show column data types
  - [ ] Handle many columns gracefully
  - [ ] Add search hints

### 2.3 Suggestion Engine
- [ ] 🔴 Enhance `_find_similar_columns()` for compilation errors
  - [ ] Use operation context for better matches
  - [ ] Consider column types in similarity
  - [ ] Adjust similarity thresholds

- [ ] 🔴 Create `_get_structured_suggestions()` function
  - [ ] Analyze error type
  - [ ] Provide specific fixes
  - [ ] Reference relevant operations
  - [ ] Add code examples

- [ ] 🔴 Implement `_format_suggestions()` function
  - [ ] Format suggestions clearly
  - [ ] Prioritize by relevance
  - [ ] Include actionable steps
  - [ ] Add documentation links

---

## Phase 3: Edge Cases and Optimization (Day 2-3)

### 3.1 Complex Expression Handling
- [ ] 🔴 Implement `_handle_complex_expressions()` method
  - [ ] Detect multi-column expressions
  - [ ] Try expression decomposition
  - [ ] Handle nested operations
  - [ ] Add fallback strategies

- [ ] 🔴 Handle type coercion errors
  - [ ] Detect list/scalar mismatches
  - [ ] Provide type-specific suggestions
  - [ ] Show type conversion examples

- [ ] 🔴 Handle lazy evaluation issues
  - [ ] Detect deferred failures
  - [ ] Try alternative evaluation strategies
  - [ ] Add diagnostic information

### 3.2 Performance Optimization
- [ ] 🔴 Implement schema caching
  - [ ] Cache collected schemas
  - [ ] Invalidate on operation changes
  - [ ] Monitor cache effectiveness

- [ ] 🔴 Implement progressive replay
  - [ ] Reuse intermediate results
  - [ ] Implement checkpointing
  - [ ] Add memory management

- [ ] 🔴 Add early termination optimizations
  - [ ] Stop on first failure
  - [ ] Skip obviously safe operations
  - [ ] Use heuristics for search

### 3.3 Error Recovery
- [ ] 🔴 Handle replay failures gracefully
  - [ ] Catch replay exceptions
  - [ ] Provide partial context
  - [ ] Log diagnostic information

- [ ] 🔴 Add timeout protection
  - [ ] Limit replay time
  - [ ] Handle infinite loops
  - [ ] Provide timeout messages

---

## Phase 4: Integration and Testing (Day 3)

### 4.1 Integration Points
- [ ] 🔴 Update `mix.py` error handling
  - [ ] Detect enhanced compilation errors
  - [ ] Display formatted output properly
  - [ ] Handle LLM context
  - [ ] Update exit codes

- [ ] 🔴 Update error handling documentation
  - [ ] Document new error modes
  - [ ] Add examples
  - [ ] Update configuration guide

- [ ] 🔴 Add telemetry for error handling
  - [ ] Track error types
  - [ ] Measure replay performance
  - [ ] Monitor success rates

### 4.2 Testing
- [ ] 🔴 Create `test_compilation_errors.py`
  - [ ] Test missing column errors
  - [ ] Test type mismatch errors
  - [ ] Test complex expressions
  - [ ] Test edge cases

- [ ] 🔴 Add integration tests
  - [ ] Test with real models
  - [ ] Test with large dataframes
  - [ ] Test performance impact
  - [ ] Test error mode interactions

- [ ] 🔴 Add regression tests
  - [ ] Ensure existing errors work
  - [ ] Test fallback behavior
  - [ ] Test configuration options

### 4.3 Documentation
- [ ] 🔴 Create user documentation
  - [ ] Explain compilation vs execution errors
  - [ ] Show example error messages
  - [ ] Document configuration options

- [ ] 🔴 Create developer documentation
  - [ ] Document architecture
  - [ ] Explain extension points
  - [ ] Add debugging guide

---

## Phase 5: Default Mode Change and Monitoring

### 5.1 Make Enhanced Mode Default
- [ ] 🔴 Update `_DEFAULT_ERROR_MODE` in `util/__init__.py`
  - [ ] Change line 26 from `"basic"` to `"enhanced"`
  - [ ] Update docstring for `get_error_mode()` to reflect new default
  - [ ] Verify `get_error_mode()` already handles invalid modes gracefully

- [ ] 🔴 Update documentation
  - [ ] Document that enhanced is now default
  - [ ] Explain how to opt-out with AF_ERROR_MODE=basic
  - [ ] Update all examples to show new default

### 5.2 Monitoring
- [ ] 🔴 Add performance metrics
  - [ ] Measure replay time
  - [ ] Track memory usage
  - [ ] Monitor success rate

- [ ] 🔴 Add error analytics
  - [ ] Track error patterns
  - [ ] Identify common issues
  - [ ] Generate reports

---

## Success Criteria

### Performance
- [ ] Replay completes in <100ms for typical errors
- [ ] Memory overhead <10MB for context collection
- [ ] No impact on successful execution path

### Quality
- [ ] All compilation errors show dataframe context
- [ ] Suggestions are relevant and actionable
- [ ] Error messages are clear and helpful

### Testing
- [ ] 100% code coverage for new code
- [ ] All edge cases have tests
- [ ] Integration tests pass with real models

---

## Notes and Considerations

### Dependencies
- Requires TracedOperation in computation graph (✅ already implemented)
- Automatically enabled when AF_ERROR_MODE is "enhanced" (default) or "debug"
- No feature flags - always available in enhanced/debug modes
- Works best with debug mode's computation graph

### Risks
- Performance impact on large computation graphs
- Memory usage for dataframe previews
- Complexity of replay logic

### Future Work
- IDE integration for error display
- Machine learning for better suggestions
- Interactive debugging mode
- Automatic fix generation

---

## Review Checklist

Before marking complete:
- [ ] Code review completed
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Performance benchmarked
- [ ] Error messages reviewed for clarity
- [ ] Integration tested with real models