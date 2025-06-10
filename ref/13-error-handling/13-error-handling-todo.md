# Gaspatchio Error Handling v1 Implementation TODO List

## Overview
Implement friendly error surfacing for ActuarialFrame as specified in `13-error-handling-spec.md` - Zero-cost abstraction with actionable error messages.

## Phase 1: Core Infrastructure (Days 1-3)

### 1.1 Create New Module Structure
- [ ] Create new Python files in `gaspatchio-core/bindings/python/gaspatchio_core/errors/`:
  - [ ] `metadata.py` - Data classes for operation metadata
  - [ ] `boundary.py` - Binary search error boundary finder
  - [ ] `formatter.py` - Error formatting and display
  - [ ] `suggestions.py` - Error suggestion engine
  - [ ] Update `__init__.py` to export new error handling

### 1.2 Implement Metadata Capture (`metadata.py`)
- [ ] Define data classes:
  - [ ] `OperationMetadata` dataclass with source location
  - [ ] `TracedOperation` dataclass combining alias, expr, metadata
- [ ] Implement `capture_source_context()` function:
  - [ ] Use `inspect` module to get stack frame
  - [ ] Extract filename, line number, function name
  - [ ] Use `linecache` to get source code line
  - [ ] Handle edge cases (compiled code, interactive sessions)
- [ ] Write tests in `tests/errors/test_metadata.py`:
  - [ ] Test source capture from different contexts
  - [ ] Test with nested function calls
  - [ ] Test with lambda expressions
  - [ ] Test in Jupyter notebook context

### 1.3 Update Tracing System (`tracing.py`)
- [ ] Backup existing `tracing.py` implementation
- [ ] Modify `append_operation_to_graph()`:
  - [ ] Import `TracedOperation` and `capture_source_context` from errors module
  - [ ] Change to capture metadata by default when tracing enabled
  - [ ] Replace tuple append with `TracedOperation` object creation
  - [ ] Adjust stack depth for `capture_source_context` (likely depth=3)
  - [ ] Update logger.trace to include source location
- [ ] Add fast path optimization:
  - [ ] Check `_tracing` flag early to avoid any overhead when disabled
  - [ ] Consider caching imports for performance
- [ ] Write tests in `tests/frame/test_tracing_metadata.py`:
  - [ ] Test metadata capture during operations
  - [ ] Test performance with/without tracing
  - [ ] Test graph storage and retrieval
  - [ ] Test backward compatibility with existing code

### 1.4 Update Base Frame (`base.py`)
- [ ] Update type hints and imports:
  - [ ] Add `from typing import List, Union`
  - [ ] Add conditional import for `TracedOperation` to avoid circular deps
  - [ ] Change `_computation_graph` type to `List[Union[Tuple[str, Any], TracedOperation]]`
- [ ] Enhance `_handle_execution_error()` in errors module:
  - [ ] Add check for error mode (tracing/debug/enhanced)
  - [ ] Implement fast path for production mode (just re-raise)
  - [ ] Add error boundary finding logic
  - [ ] Add suggestion generation
  - [ ] Add error formatting
  - [ ] Create enhanced exception with LLM context
  - [ ] Add fallback for formatting failures
- [ ] Update `collect()` and `profile()` methods:
  - [ ] Modify graph processing loop to handle both tuple and TracedOperation
  - [ ] Use isinstance() checks for backward compatibility
  - [ ] Extract alias/expression appropriately based on type
- [ ] Add configuration helpers:
  - [ ] Create `get_error_mode()` function in util.py
  - [ ] Create `set_error_mode()` function
  - [ ] Add environment variable support (`AF_ERROR_MODE`)
- [ ] Write integration tests:
  - [ ] Test mixed graph formats (tuples and TracedOperations)
  - [ ] Test error handling in collect()
  - [ ] Test error handling in profile()

### 1.5 Implement Error Boundary Finder (`boundary.py`)
- [ ] Create `ErrorBoundaryFinder` class:
  - [ ] `__init__()` with ActuarialFrame and exception
  - [ ] `_apply_operations_up_to()` helper method:
    - [ ] Handle both tuple and TracedOperation formats
    - [ ] Efficiently apply operations without side effects
    - [ ] Return resulting LazyFrame
  - [ ] `find_failing_operation()` with binary search:
    - [ ] Implement binary search algorithm
    - [ ] Track last good DataFrame
    - [ ] Handle edge cases (empty graph, all fail, none fail)
- [ ] Optimize binary search:
  - [ ] Early termination for obvious cases
  - [ ] Efficient DataFrame copying
  - [ ] Memory-efficient replay
- [ ] Write tests in `tests/errors/test_boundary.py`:
  - [ ] Test with various error positions (first, middle, last)
  - [ ] Test with different error types
  - [ ] Test performance on large graphs (100+ operations)
  - [ ] Test edge cases
  - [ ] Test with mixed operation formats

### 1.6 Optional: Enhance Dispatch System (`dispatch.py`)
- [ ] Identify error handling points in `_method_caller`:
  - [ ] Locate the exception handling in proxy method calls
  - [ ] Plan enhanced error messages without breaking existing behavior
- [ ] Add contextual error information:
  - [ ] Check if parent frame is in tracing mode
  - [ ] Capture source context for proxy method calls
  - [ ] Add file/line information to error messages
  - [ ] Attach proxy metadata to exceptions
- [ ] Test proxy error enhancements:
  - [ ] Test error messages from column operations
  - [ ] Test error messages from expression operations
  - [ ] Ensure no performance impact when not tracing

## Phase 2: Error Formatting & Suggestions (Days 4-5)

### 2.1 Implement Error Formatter (`formatter.py`)
- [ ] Create `FriendlyErrorFormatter` class:
  - [ ] `__init__()` with operation, exception, last_good_df
  - [ ] `format_error()` for human-readable output
  - [ ] `format_for_llm()` for structured JSON output
  - [ ] `_format_dataframe_preview()` helper
  - [ ] `_truncate_wide_tables()` for display
- [ ] Implement formatting features:
  - [ ] Syntax highlighting for source code (optional)
  - [ ] Table truncation for large DataFrames
  - [ ] Smart column width adjustment
  - [ ] Unicode/ASCII fallback for different terminals
- [ ] Write tests in `tests/errors/test_formatter.py`:
  - [ ] Test various error types and messages
  - [ ] Test DataFrame preview formatting
  - [ ] Test LLM output structure
  - [ ] Test edge cases (empty df, very wide tables)

### 2.2 Implement Suggestion Engine (`suggestions.py`)
- [ ] Create `ErrorSuggestionEngine` class:
  - [ ] `suggest_fixes()` main method
  - [ ] `_extract_column_name()` from error messages
  - [ ] `_find_similar_columns()` using edit distance
  - [ ] Pattern matching for common error types
- [ ] Implement suggestion patterns:
  - [ ] Column not found → similar column suggestions
  - [ ] Type mismatches → casting suggestions
  - [ ] Schema mismatches → join key alignment
  - [ ] Division by zero → null handling suggestions
  - [ ] Index out of bounds → data validation suggestions
- [ ] Add domain-specific suggestions:
  - [ ] Common actuarial typos (premiun → premium)
  - [ ] Date format issues
  - [ ] Assumption lookup errors
- [ ] Write tests in `tests/errors/test_suggestions.py`:
  - [ ] Test each suggestion pattern
  - [ ] Test similarity algorithm
  - [ ] Test with real-world error messages

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
  - [ ] `test_metadata.py` - 15+ tests
  - [ ] `test_boundary.py` - 12+ tests
  - [ ] `test_formatter.py` - 10+ tests
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

### Phase 1: Core Infrastructure ✓
- [ ] Metadata capture working with <5% overhead
- [ ] Binary search correctly finds failing operations
- [ ] All unit tests passing
- [ ] Backward compatibility maintained

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
