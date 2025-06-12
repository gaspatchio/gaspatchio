# Gaspatchio Error Handling v1 Implementation TODO List

## Overview
Implement friendly error surfacing for ActuarialFrame as specified in `13-error-handling-spec.md` - Zero-cost abstraction with actionable error messages.

## Current Progress ✅
- **Section 1.1**: Module structure created with metadata.py, boundary.py, formatter.py, suggestions.py
- **Section 1.2**: Metadata capture implemented with comprehensive test suite (24 tests)
- **Section 1.3**: Tracing system updated with TracedOperation support and comprehensive tests (21 tests)
- **Section 1.4**: Base Frame updated with type hints, error handling integration, and backward compatibility (45 tests)
- **Section 1.5**: Error Boundary Finder implemented with binary search algorithm and comprehensive tests (21 tests)
- **Section 1.6**: Dispatch System enhanced with contextual error information and proxy method error handling
- **Section 2.1**: Error Formatter implemented with comprehensive test suite (22 tests)
- **Section 2.2**: Error Suggestion Engine implemented with comprehensive test suite (39 tests)
- **Next**: Phase 2.3 Complete Error Handler Integration

## Phase 1: Core Infrastructure (Days 1-3) - ✅ COMPLETE (6/6 Complete)

### 1.1 Create New Module Structure
- [x] Create new Python files in `gaspatchio-core/bindings/python/gaspatchio_core/errors/`:
  - [x] `metadata.py` - Data classes for operation metadata
  - [x] `boundary.py` - Binary search error boundary finder
  - [x] `formatter.py` - Error formatting and display
  - [x] `suggestions.py` - Error suggestion engine
  - [x] Update `__init__.py` to export new error handling

### 1.2 Implement Metadata Capture (`metadata.py`)
- [x] Define data classes:
  - [x] `OperationMetadata` dataclass with source location
  - [x] `TracedOperation` dataclass combining alias, expr, metadata
- [x] Implement `capture_source_context()` function:
  - [x] Use `inspect` module to get stack frame
  - [x] Extract filename, line number, function name
  - [x] Use `linecache` to get source code line
  - [x] Handle edge cases (compiled code, interactive sessions)
- [x] Write tests in `tests/errors/test_metadata.py`:
  - [x] Test source capture from different contexts
  - [x] Test with nested function calls
  - [x] Test with lambda expressions
  - [x] Test in Jupyter notebook context

### 1.3 Update Tracing System (`tracing.py`)
- [x] Backup existing `tracing.py` implementation
- [x] Modify `append_operation_to_graph()`:
  - [x] Import `TracedOperation` and `capture_source_context` from errors module
  - [x] Change to capture metadata by default when tracing enabled
  - [x] Replace tuple append with `TracedOperation` object creation
  - [x] Adjust stack depth for `capture_source_context` (depth=2)
  - [x] Update logger.trace to include source location
- [x] Add fast path optimization:
  - [x] Check `_tracing` flag early to avoid any overhead when disabled
  - [x] Consider caching imports for performance
- [x] Write tests in `tests/frame/test_tracing_metadata.py`:
  - [x] Test metadata capture during operations
  - [x] Test performance with/without tracing
  - [x] Test graph storage and retrieval
  - [x] Test backward compatibility with existing code

### 1.4 Update Base Frame (`base.py`)
- [x] Update type hints and imports:
  - [x] Add `from typing import List, Union`
  - [x] Add conditional import for `TracedOperation` to avoid circular deps
  - [x] Change `_computation_graph` type to `List[Union[Tuple[str, Any], TracedOperation]]`
- [x] Enhance `_handle_execution_error()` in errors module:
  - [x] Add check for error mode (tracing/debug/enhanced)
  - [x] Implement fast path for production mode (just re-raise)
  - [x] Add error boundary finding logic
  - [x] Add suggestion generation
  - [x] Add error formatting
  - [x] Create enhanced exception with LLM context
  - [x] Add fallback for formatting failures
- [x] Update `collect()` and `profile()` methods:
  - [x] Modify graph processing loop to handle both tuple and TracedOperation
  - [x] Use isinstance() checks for backward compatibility
  - [x] Extract alias/expression appropriately based on type
- [x] Add configuration helpers:
  - [x] Create `get_error_mode()` function in util.py
  - [x] Create `set_error_mode()` function
  - [x] Add environment variable support (`AF_ERROR_MODE`)
- [x] Write integration tests:
  - [x] Test mixed graph formats (tuples and TracedOperations)
  - [x] Test error handling in collect()
  - [x] Test error handling in profile()

### 1.5 Implement Error Boundary Finder (`boundary.py`)
- [x] Create `ErrorBoundaryFinder` class:
  - [x] `__init__()` with ActuarialFrame and exception
  - [x] `_apply_operations_up_to()` helper method:
    - [x] Handle both tuple and TracedOperation formats
    - [x] Efficiently apply operations without side effects
    - [x] Return resulting DataFrame
  - [x] `find_failing_operation()` with binary search:
    - [x] Implement binary search algorithm
    - [x] Track last good DataFrame
    - [x] Handle edge cases (empty graph, all fail, none fail)
- [x] Optimize binary search:
  - [x] Early termination for obvious cases
  - [x] Efficient DataFrame copying
  - [x] Memory-efficient replay
- [x] Write tests in `tests/errors/test_boundary.py`:
  - [x] Test with various error positions (first, middle, last)
  - [x] Test with different error types
  - [x] Test performance on large graphs (100+ operations)
  - [x] Test edge cases
  - [x] Test with mixed operation formats

### 1.6 Enhance Dispatch System (`dispatch.py`)
- [x] Identify error handling points in `_method_caller`:
  - [x] Locate the exception handling in proxy method calls
  - [x] Plan enhanced error messages without breaking existing behavior
- [x] Add contextual error information:
  - [x] Check if parent frame is in tracing mode
  - [x] Capture source context for proxy method calls
  - [x] Add file/line information to error messages
  - [x] Attach proxy metadata to exceptions
- [x] Test proxy error enhancements:
  - [x] Test error messages from column operations
  - [x] Test error messages from expression operations
  - [x] Ensure no performance impact when not tracing

## Phase 2: Error Formatting & Suggestions (Days 4-5)

### 2.1 Implement Error Formatter (`formatter.py`) - ✅ COMPLETE
- [x] Create `FriendlyErrorFormatter` class:
  - [x] `__init__()` with operation, exception, last_good_df
  - [x] `format_error()` for human-readable output
  - [x] `format_for_llm()` for structured JSON output
  - [x] `_format_dataframe_preview()` helper
  - [x] `_truncate_wide_tables()` for display
- [x] Implement formatting features:
  - [x] Table truncation for large DataFrames (8 columns max with ellipsis)
  - [x] Smart column width adjustment (terminal width detection)
  - [x] LazyFrame and DataFrame support
  - [x] Unicode/ASCII fallback for different terminals
- [x] Write tests in `tests/errors/test_formatter.py`:
  - [x] Test various error types and messages (6 comprehensive tests)
  - [x] Test DataFrame preview formatting
  - [x] Test LLM output structure
  - [x] Test edge cases (LazyFrame, very wide tables, row truncation)

### 2.2 Implement Suggestion Engine (`suggestions.py`) - ✅ COMPLETE
- [x] Create `ErrorSuggestionEngine` class:
  - [x] `suggest_fixes()` main method
  - [x] `_extract_column_name()` from error messages
  - [x] `_find_similar_columns()` using edit distance
  - [x] Pattern matching for common error types
- [x] Implement suggestion patterns:
  - [x] Column not found → similar column suggestions
  - [x] Type mismatches → casting suggestions
  - [x] Schema mismatches → join key alignment
  - [x] Division by zero → null handling suggestions
  - [x] Index out of bounds → data validation suggestions
- [x] Add domain-specific suggestions:
  - [x] Common actuarial typos (premiun → premium)
  - [x] Date format issues
  - [x] Assumption lookup errors
- [x] Write tests in `tests/errors/test_suggestions.py`:
  - [x] Test each suggestion pattern (39 tests total)
  - [x] Test similarity algorithm
  - [x] Test with real-world error messages

### 2.3 Complete Error Handler Integration
- [ ] Finalize `_handle_execution_error()` implementation:
  - [ ] Import all error handling components
  - [ ] Wire up boundary finder, suggestions, and formatter
  - [ ] Test end-to-end flow
- [ ] Add feature flags:
  - [ ] Environment variable support
  - [ ] Runtime configuration
  - [ ] Gradual rollout capability
- [ ] Write integration tests in `tests/frame/test_error_handling.py`:
  - [ ] Test end-to-end error flow
  - [ ] Test with model_test.py scenarios
  - [ ] Test performance impact
  - [ ] Test feature flag behavior

## Phase 3: Testing & Integration (Days 6-7)

### 3.1 Create Comprehensive Test Suite
- [ ] Unit tests for each component:
  - [x] `test_metadata.py` - 24 tests ✅
  - [x] `test_boundary.py` - 21 tests ✅
  - [x] `test_formatter.py` - 22 tests ✅
  - [ ] `test_suggestions.py` - 20+ tests
- [ ] Integration tests:
  - [ ] `test_error_scenarios.py` - Real model errors
  - [ ] `test_performance.py` - Overhead measurements
  - [ ] `test_edge_cases.py` - Unusual situations
- [ ] Model-based tests:
  - [ ] Port errors from `model_test.py`
  - [ ] Test with large models (1000+ operations)
  - [ ] Test with complex expressions

### 3.2 Performance Optimization
- [ ] Benchmark metadata capture:
  - [ ] Measure overhead per operation
  - [ ] Profile memory usage
  - [ ] Optimize hot paths
- [ ] Optimize error replay:
  - [ ] Minimize DataFrame copies
  - [ ] Cache intermediate results
  - [ ] Parallel search for very large graphs
- [ ] Add performance tests:
  - [ ] Baseline without error handling
  - [ ] With tracing enabled
  - [ ] During error replay

### 3.3 Documentation
- [ ] User documentation:
  - [ ] How to read enhanced errors
  - [ ] Debugging workflow guide
  - [ ] Common error patterns
- [ ] Developer documentation:
  - [ ] Architecture overview
  - [ ] Extension points
  - [ ] Performance considerations
- [ ] LLM integration guide:
  - [ ] How to parse JSON errors
  - [ ] Automated fix examples
  - [ ] Integration with AI tools

## Phase 4: Polish & Release (Days 8-9)

### 4.1 Edge Case Handling
- [ ] Jupyter notebook support:
  - [ ] Handle `<ipython-input-*>` filenames
  - [ ] Cell number extraction
  - [ ] Interactive mode detection
- [ ] Multi-threading considerations:
  - [ ] Thread-safe metadata capture
  - [ ] Concurrent error handling
- [ ] Large model support:
  - [ ] Graph size limits
  - [ ] Memory-efficient replay
  - [ ] Progress indicators for long replays

### 4.2 Feature Flags & Configuration
- [ ] Add configuration options:
  - [ ] `AF_ERROR_MODE` environment variable
  - [ ] `error_mode` parameter on ActuarialFrame
  - [ ] Global configuration API
- [ ] Implement gradual rollout:
  - [ ] Off by default initially
  - [ ] Opt-in for beta users
  - [ ] Default in debug mode later
- [ ] Add telemetry (optional):
  - [ ] Error frequency tracking
  - [ ] Suggestion effectiveness
  - [ ] Performance metrics

### 4.3 Final Integration
- [ ] Update all error paths in ActuarialFrame:
  - [ ] `__setitem__` errors
  - [ ] `with_columns` errors
  - [ ] `select` errors
  - [ ] `pipe` errors
- [ ] Add examples:
  - [ ] Common error scenarios
  - [ ] How to fix each error type
  - [ ] Best practices guide
- [ ] Release preparation:
  - [ ] Update changelog
  - [ ] Migration guide
  - [ ] Performance report

## Implementation Commands

```bash
# Start development
cd gaspatchio-core/bindings/python

# Create new error handling modules
mkdir -p gaspatchio_core/errors
touch gaspatchio_core/errors/__init__.py
touch gaspatchio_core/errors/metadata.py
touch gaspatchio_core/errors/boundary.py
touch gaspatchio_core/errors/formatter.py
touch gaspatchio_core/errors/suggestions.py

# Create test structure
mkdir -p tests/errors
touch tests/errors/test_metadata.py
touch tests/errors/test_boundary.py
touch tests/errors/test_formatter.py
touch tests/errors/test_suggestions.py
touch tests/errors/test_error_scenarios.py

# Run tests during development
pytest tests/errors/test_metadata.py -v
pytest tests/frame/test_tracing_metadata.py -v
pytest tests/frame/test_error_handling.py -v

# Run performance benchmarks
pytest tests/errors/test_performance.py -v --benchmark-only

# Full test suite
pytest tests/ -v
```

## Success Criteria

### Phase 1: Core Infrastructure ✅
- [x] Metadata capture working with <5% overhead
- [x] Binary search correctly finds failing operations
- [x] All unit tests passing (45 tests total: 24 metadata + 21 boundary)
- [x] Backward compatibility maintained

### Phase 2: Error Formatting ✓
- [ ] Human-readable errors with source location
- [ ] LLM-parseable JSON format
- [ ] 5+ suggestion patterns implemented

### Phase 3: Testing & Integration ✓
- [ ] 70+ tests passing
- [ ] <1% performance impact in production
- [ ] Works with model_test.py scenarios

### Phase 4: Polish & Release ✓
- [ ] Jupyter notebook support
- [ ] Feature flags working
- [ ] Documentation complete

## Risk Mitigation

### Technical Risks
1. **Stack frame inspection fails**
   - Mitigation: Fallback to no metadata
   - Test in various Python environments

2. **Binary search is too slow**
   - Mitigation: Add linear search option
   - Optimize DataFrame operations

3. **Memory usage too high**
   - Mitigation: Limit graph size
   - Add pruning for old operations

### User Experience Risks
1. **Error messages too verbose**
   - Mitigation: Progressive disclosure
   - Configuration options

2. **Suggestions not helpful**
   - Mitigation: Collect feedback
   - Iterative improvement

3. **Performance regression**
   - Mitigation: Feature flags
   - Extensive benchmarking

## Future Enhancements (Not in v1)

- [ ] IDE integration (clickable file paths)
- [ ] Web-based error viewer
- [ ] Historical error tracking
- [ ] Automated fix application
- [ ] Multi-language support
- [ ] Error grouping for batch operations
- [ ] Integration with observability platforms
