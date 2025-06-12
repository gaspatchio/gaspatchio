# Gaspatchio Error Handling v1 Specification

## Executive Summary

This specification defines a comprehensive error handling system for ActuarialFrame that replaces opaque Polars stack traces with contextual, actionable error messages. The system captures source location, provides visual context, and suggests remedies - all without impacting performance in production mode.

**Core Innovation**: Binary search replay mechanism that pinpoints exact failing operations with zero runtime overhead in normal execution.

## Design Principles

1. **Zero-Cost Abstraction**: No performance impact when not in debug mode
2. **Actionable Errors**: Every error includes file location, line number, and suggested fixes
3. **Progressive Context**: Show just enough information to diagnose without overwhelming
4. **LLM-Friendly**: Structured output that AI assistants can parse and fix automatically
5. **Fail-Fast Debugging**: Quickly identify the exact operation that failed

## Architecture Overview

### Component Interaction

```mermaid
flowchart TD
    A[Model Code] -->|af["col"] = expr| B[ActuarialFrame.__setitem__]
    B -->|if tracing| C[append_operation_to_graph]
    C --> D[Store with metadata]
    D --> E[computation_graph]
    
    F[af.collect()] --> G{Error?}
    G -->|Yes| H[_handle_execution_error]
    G -->|No| I[Return DataFrame]
    
    H --> J[_find_failing_operation]
    J --> K[Binary search replay]
    K --> L[Format friendly error]
    L --> M[Raise enhanced exception]
```

### Source Location Capture

```python
@dataclass
class OperationMetadata:
    """Metadata for a traced operation"""
    filename: str
    lineno: int
    source_line: str
    function_name: Optional[str] = None
    timestamp: Optional[float] = None  # For performance debugging
    
@dataclass
class TracedOperation:
    """Complete operation with metadata"""
    alias: str
    expression: pl.Expr
    metadata: OperationMetadata
```

## API Components

### 1. Enhanced Tracing API

```python
def capture_source_context(depth: int = 2) -> OperationMetadata:
    """
    Capture source context from the call stack.
    
    Args:
        depth: How many frames up to look (2 = caller of caller)
        
    Returns:
        OperationMetadata with file, line, and source information
    """
    frame = inspect.currentframe()
    for _ in range(depth):
        frame = frame.f_back
    
    filename = frame.f_code.co_filename
    lineno = frame.f_lineno
    
    # Get source line
    try:
        source_line = linecache.getline(filename, lineno).strip()
    except:
        source_line = "<source unavailable>"
    
    return OperationMetadata(
        filename=filename,
        lineno=lineno,
        source_line=source_line,
        function_name=frame.f_code.co_name
    )

def append_operation_with_context(
    frame_instance: ActuarialFrame,
    name: str,
    expr: Any,
    metadata: Optional[OperationMetadata] = None
) -> None:
    """Enhanced operation tracking with source context"""
    if frame_instance._tracing:
        if metadata is None:
            metadata = capture_source_context()
        
        operation = TracedOperation(
            alias=name,
            expression=expr,
            metadata=metadata
        )
        frame_instance._computation_graph.append(operation)
```

### 2. Error Detection API

```python
class ErrorBoundaryFinder:
    """Efficiently find the failing operation using binary search"""
    
    def __init__(self, af: ActuarialFrame, exception: Exception):
        self.af = af
        self.exception = exception
        self.original_df = af._df
        
    def find_failing_operation(self) -> Tuple[int, TracedOperation, pl.DataFrame]:
        """
        Find the first operation that fails using binary search.
        
        Returns:
            Tuple of (failing_index, failing_operation, last_good_dataframe)
        """
        operations = self.af._computation_graph
        if not operations:
            return -1, None, self.original_df
            
        # Binary search for efficiency on large computation graphs
        left, right = 0, len(operations) - 1
        last_good_df = self.original_df
        
        while left <= right:
            mid = (left + right) // 2
            
            try:
                test_df = self._apply_operations_up_to(mid)
                # This point succeeded, error is later
                last_good_df = test_df
                left = mid + 1
            except type(self.exception):
                # Error at or before this point
                right = mid - 1
            except Exception:
                # Different error type, keep searching
                left = mid + 1
                
        # left now points to first failing operation
        return left, operations[left] if left < len(operations) else None, last_good_df
```

### 3. Error Formatting API

```python
class FriendlyErrorFormatter:
    """Format errors for human and LLM consumption"""
    
    def __init__(self, 
                 operation: TracedOperation,
                 exception: Exception,
                 last_good_df: pl.DataFrame,
                 suggestions: Optional[List[str]] = None):
        self.operation = operation
        self.exception = exception
        self.last_good_df = last_good_df
        self.suggestions = suggestions or []
        
    def format_error(self) -> str:
        """Create the friendly error message"""
        # Extract key information
        error_type = type(self.exception).__name__
        error_msg = str(self.exception)
        
        # Build formatted message
        lines = [
            f"❌ Calculation error in {self.operation.metadata.filename}:{self.operation.metadata.lineno}",
            f"{self.operation.metadata.source_line}",
            "",
            f"Polars raised → {error_type}: {error_msg}",
        ]
        
        # Add suggestions if available
        if self.suggestions:
            lines.extend(["", "💡 Suggestions:"])
            lines.extend(f"  • {suggestion}" for suggestion in self.suggestions)
        
        # Add data context
        if self.last_good_df is not None:
            lines.extend(["", "Last good rows (truncated):"])
            lines.append(self._format_dataframe_preview(self.last_good_df))
            
        return "\n".join(lines)
    
    def format_for_llm(self) -> Dict[str, Any]:
        """Structured format for LLM consumption"""
        return {
            "error_location": {
                "file": self.operation.metadata.filename,
                "line": self.operation.metadata.lineno,
                "code": self.operation.metadata.source_line
            },
            "error_details": {
                "type": type(self.exception).__name__,
                "message": str(self.exception),
                "column_alias": self.operation.alias
            },
            "suggestions": self.suggestions,
            "available_columns": list(self.last_good_df.columns) if self.last_good_df else []
        }
```

### 4. Suggestion Engine

```python
class ErrorSuggestionEngine:
    """Generate helpful suggestions based on error type"""
    
    def suggest_fixes(self, 
                     exception: Exception, 
                     operation: TracedOperation,
                     available_columns: List[str]) -> List[str]:
        """Generate context-aware suggestions"""
        
        suggestions = []
        error_msg = str(exception).lower()
        
        if "columnnotfound" in type(exception).__name__:
            # Extract the missing column name
            missing_col = self._extract_column_name(error_msg)
            if missing_col:
                # Find similar columns
                similar = self._find_similar_columns(missing_col, available_columns)
                if similar:
                    suggestions.append(f"Did you mean '{similar[0]}'? (similar column found)")
                    
                # Check if it's a common typo
                if missing_col == "data":
                    suggestions.append("'data' might be 'date' - check for typos")
                    
        elif "could not determine output type" in error_msg:
            suggestions.append("Ensure all expressions have consistent types")
            suggestions.append("Consider using .cast() to explicitly set types")
            
        elif "schema mismatch" in error_msg:
            suggestions.append("Check that join keys have matching types")
            suggestions.append("Use .cast() to align data types before joining")
            
        return suggestions
```

## Integration with Existing System

### 1. Modifications to `tracing.py`

The existing `append_operation_to_graph` function needs to be enhanced to capture metadata:

```python
# Current implementation in tracing.py
def append_operation_to_graph(
    frame_instance: ActuarialFrame, name: str, expr: Any
) -> None:
    """Appends an operation to the frame's computation graph if tracing is enabled."""
    if frame_instance._tracing:
        frame_instance._computation_graph.append((name, expr))  # OLD: Just tuple
        logger.trace(f"Graph: Added '{name}' = {expr}")

# Enhanced implementation
def append_operation_to_graph(
    frame_instance: ActuarialFrame, name: str, expr: Any
) -> None:
    """Appends an operation with metadata to the frame's computation graph if tracing is enabled."""
    if frame_instance._tracing:
        # Import locally to avoid circular dependencies
        from ..errors.metadata import TracedOperation, capture_source_context
        
        # Capture source context from the calling code
        metadata = capture_source_context(depth=3)  # Adjusted for call stack depth
        
        # Create TracedOperation instead of tuple
        operation = TracedOperation(
            alias=name,
            expression=expr,
            metadata=metadata
        )
        
        frame_instance._computation_graph.append(operation)
        logger.trace(f"Graph: Added '{name}' = {expr} at {metadata.filename}:{metadata.lineno}")
```

### 2. Modifications to `base.py`

Several changes are needed in ActuarialFrame:

#### 2.1 Update Type Hints
```python
# In imports section
from typing import List, Union
from ..errors.metadata import TracedOperation

class ActuarialFrame:
    def __init__(self, ...):
        # Change type from List[Tuple[str, Any]] to List[Union[Tuple[str, Any], TracedOperation]]
        # This allows backward compatibility during migration
        self._computation_graph: List[Union[Tuple[str, Any], TracedOperation]] = []
```

#### 2.2 Update `_handle_execution_error`
```python
# Current implementation
from ..errors import _handle_execution_error

# In collect() and profile() methods:
except Exception as e:
    _handle_execution_error(self, e)  # Will re-raise or format

# Enhanced implementation for _handle_execution_error
def _handle_execution_error(af: ActuarialFrame, exception: Exception) -> None:
    """Handle execution errors with friendly formatting when in debug/trace mode."""
    # Check if we should use enhanced error handling
    if not (af._tracing or af._mode == "debug" or get_error_mode() == "enhanced"):
        # Fast path: just re-raise in production mode
        raise exception
    
    # Import error handling components
    from ..errors.boundary import ErrorBoundaryFinder
    from ..errors.suggestions import ErrorSuggestionEngine
    from ..errors.formatter import FriendlyErrorFormatter
    
    try:
        # Find the failing operation
        finder = ErrorBoundaryFinder(af, exception)
        fail_idx, fail_op, last_good_df = finder.find_failing_operation()
        
        if fail_op is None:
            # Couldn't find the specific operation, fall back to original error
            raise exception
        
        # Generate suggestions
        engine = ErrorSuggestionEngine()
        suggestions = engine.suggest_fixes(
            exception, 
            fail_op,
            list(last_good_df.columns) if last_good_df is not None else []
        )
        
        # Format the error
        formatter = FriendlyErrorFormatter(
            operation=fail_op,
            exception=exception,
            last_good_df=last_good_df,
            suggestions=suggestions
        )
        
        # Create enhanced exception with same type as original
        enhanced_msg = formatter.format_error()
        
        # Also store LLM format in exception for programmatic access
        new_exception = type(exception)(enhanced_msg)
        new_exception.llm_context = formatter.format_for_llm()
        
        raise new_exception from exception
        
    except Exception as format_error:
        # If error handling itself fails, fall back to original
        logger.warning(f"Error formatting failed: {format_error}")
        raise exception
```

#### 2.3 Update Methods that Process Computation Graph
```python
# In collect() and profile() methods where computation graph is processed:
for operation in self._computation_graph:
    # Handle both old tuple format and new TracedOperation format
    if isinstance(operation, tuple):
        # Legacy format: (name, expr)
        name, expr_val = operation
        final_df = final_df.with_columns(expr_val.alias(name))
    else:
        # New format: TracedOperation
        final_df = final_df.with_columns(operation.expression.alias(operation.alias))
```

### 3. Modifications to `dispatch.py`

While not strictly necessary for basic error handling, we can enhance proxy error messages:

```python
# In _method_caller function, enhance error context:
except Exception as e:
    # Current:
    raise type(e)(f"Error calling proxied Polars method '{name}': {e}") from e
    
    # Enhanced with context:
    error_msg = f"Error calling proxied Polars method '{name}': {e}"
    
    # If we're in a traced context, add source information
    if hasattr(self_proxy, '_parent') and self_proxy._parent and self_proxy._parent._tracing:
        # Capture where this proxy method was called from
        from ..errors.metadata import capture_source_context
        context = capture_source_context(depth=2)
        error_msg += f"\n  Called from: {context.filename}:{context.lineno}"
        error_msg += f"\n  Source: {context.source_line}"
    
    new_error = type(e)(error_msg)
    # Preserve the column/expression info for error handling
    new_error.proxy_info = {
        'proxy_type': type(self_proxy).__name__,
        'method': name,
        'column': getattr(self_proxy, 'name', None)
    }
    raise new_error from e
```

### 4. Configuration and Feature Flags

Add global configuration for error handling mode:

```python
# In util.py or a new config module
import os

def get_error_mode() -> str:
    """Get the error handling mode from environment or config."""
    return os.environ.get("AF_ERROR_MODE", "standard")

def set_error_mode(mode: str) -> None:
    """Set the error handling mode."""
    if mode not in ["standard", "enhanced", "debug"]:
        raise ValueError(f"Invalid error mode: {mode}")
    os.environ["AF_ERROR_MODE"] = mode
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
1. **Update computation graph to store metadata**
   - Modify `append_operation_to_graph` to capture source context
   - Update graph storage to use `TracedOperation` objects
   
2. **Implement boundary finder**
   - Create `ErrorBoundaryFinder` class with binary search
   - Add replay mechanism for operation sequences
   
3. **Basic error formatting**
   - Implement `FriendlyErrorFormatter` with essential features
   - Integration with `_handle_execution_error`

### Phase 2: Enhanced Features (Week 2)
1. **Suggestion engine**
   - Implement `ErrorSuggestionEngine` with common patterns
   - Add column similarity detection (Levenshtein distance)
   
2. **LLM-friendly output**
   - Add structured JSON format for errors
   - Include repair hints in machine-readable format
   
3. **Performance optimizations**
   - Cache source line lookups
   - Optimize binary search for large graphs

### Phase 3: Testing & Polish (Week 3)
1. **Comprehensive test suite**
   - Unit tests for each component
   - Integration tests with real model scenarios
   - Performance benchmarks
   
2. **Documentation**
   - User guide for debugging with new errors
   - LLM integration examples
   - Performance tuning guide

## Design Decisions & Rationale

### 1. Binary Search vs Linear Replay
**Decision**: Use binary search for finding failing operations.

**Rationale**: 
- Models can have 100+ operations
- Binary search reduces worst-case from O(n) to O(log n)
- More important for large models where debugging is hardest

**Trade-off**: Slightly more complex implementation but massive speedup for large graphs.

### 2. Metadata Capture Timing
**Decision**: Capture metadata at operation creation time, not at error time.

**Rationale**:
- Stack frames are available when operation is created
- No need to preserve stack traces (memory intensive)
- Source location is immutable once captured

**Alternative considered**: Lazy metadata capture at error time - rejected due to stack frame availability issues.

### 3. Error Message Format
**Decision**: Multi-level format with emoji indicators and structured sections.

**Rationale**:
- Emojis provide quick visual scanning
- Structured sections allow progressive disclosure
- Both human and machine readable

**Alternative considered**: Plain text only - rejected as less scannable.

### 4. Conditional Compilation
**Decision**: Use runtime flag (`_tracing`) not compile-time flag.

**Rationale**:
- Python doesn't have true conditional compilation
- Runtime check is negligible overhead
- Allows dynamic enable/disable

### 5. Backward Compatibility
**Decision**: Support both tuple and TracedOperation formats in computation graph.

**Rationale**:
- Allows gradual migration
- Doesn't break existing code
- Can be removed in future version

**Trade-off**: Slightly more complex graph processing, but ensures smooth transition.

## Performance Considerations

### Zero-Cost in Production
```python
def __setitem__(self, key: str, value: Any):
    # Fast path when not tracing
    if not self._tracing:
        expr = self._convert_to_expr(value)
        self._df = self._df.with_columns(expr.alias(key))
        return
    
    # Slow path with metadata capture
    # ... full implementation ...
```

### Memory Usage
- Metadata adds ~200 bytes per operation
- 1000 operations = ~200KB overhead (acceptable)
- Consider pruning graph for very long-running models

## Example Error Output

### Scenario: Typo in Column Name
```python
# model_calculation.py
af["premium_total"] = af["premiun"] * 12  # Typo: "premiun"
```

**Error Output:**
```
❌ Calculation error in model_calculation.py:27
af["premium_total"] = af["premiun"] * 12

Polars raised → ColumnNotFoundError: column 'premiun' does not exist

💡 Suggestions:
  • Did you mean 'premium'? (similar column found)
  • Available columns: ['policy_id', 'premium', 'claims', 'age']

Last good rows (truncated):
┌───────────┬─────────┬────────┬─────┐
│ policy_id ┆ premium ┆ claims ┆ age │
│ ---       ┆ ---     ┆ ---    ┆ --- │
│ i64       ┆ f64     ┆ f64    ┆ i64 │
╞═══════════╪═════════╪════════╪═════╡
│ 1         ┆ 100.0   ┆ 0.0    ┆ 45  │
│ 2         ┆ 150.0   ┆ 50.0   ┆ 52  │
└───────────┴─────────┴────────┴─────┘
```

### LLM-Friendly Format
```json
{
  "error_location": {
    "file": "model_calculation.py",
    "line": 27,
    "code": "af[\"premium_total\"] = af[\"premiun\"] * 12"
  },
  "error_details": {
    "type": "ColumnNotFoundError",
    "message": "column 'premiun' does not exist",
    "column_alias": "premium_total"
  },
  "suggestions": ["Did you mean 'premium'? (similar column found)"],
  "available_columns": ["policy_id", "premium", "claims", "age"]
}
```

## Migration Path

1. **Phase 1**: Basic implementation behind feature flag
2. **Phase 2**: Opt-in beta for power users
3. **Phase 3**: Default on in debug mode
4. **Phase 4**: Deprecate raw Polars errors

## Open Questions & Considerations

### 1. Stack Depth for Source Capture
**Question**: How many stack frames to traverse for source location?

**Current thinking**: Make it configurable with sensible default (2).

### 2. Error Grouping
**Question**: Should we group similar errors in batch operations?

**Current thinking**: Start simple, add grouping if users request it.

### 3. Caching Strategy
**Question**: Should we cache source line lookups?

**Current thinking**: Yes, using `functools.lru_cache` on the lookup function.

### 4. Integration with Jupyter
**Question**: How to handle source location in Jupyter notebooks?

**Current thinking**: Special handling for `<ipython-input-*>` filenames.

## Success Metrics

1. **Error Resolution Time**: 80% reduction in time to fix errors
2. **User Satisfaction**: Positive feedback on error clarity
3. **LLM Success Rate**: 90%+ automated fixes for common errors
4. **Performance Impact**: <1% overhead in debug mode, 0% in production
