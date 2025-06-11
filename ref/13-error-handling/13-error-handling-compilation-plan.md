# Compilation Error Enhanced Handling Plan

## Current Execution Modes

Gaspatchio has two independent mode systems that interact to determine execution behavior and error handling:

### Execution Modes (GASPATCHIO_MODE)

| Mode | Environment Variable | Behavior | Operation Execution | Computation Graph | Tracing | Performance |
|------|---------------------|----------|-------------------|------------------|---------|-------------|
| **debug** (default) | `GASPATCHIO_MODE=debug` | Operations execute immediately when assigned | `af["col"] = expr` → executed instantly | Empty (`_computation_graph = []`) | `_tracing = False` | Fast execution, no optimization |
| **optimize** | `GASPATCHIO_MODE=optimize` | Operations captured and deferred until collection | `af["col"] = expr` → stored for later | Populated with `TracedOperation` objects | `_tracing = True` | Slower setup, optimized execution |

### Error Handling Modes (AF_ERROR_MODE)

| Mode | Environment Variable | Error Messages | Column Suggestions | Dataframe Context | Operation Replay | Source Location | Performance |
|------|---------------------|----------------|-------------------|-------------------|------------------|----------------|-------------|
| **basic** (default) | `AF_ERROR_MODE=basic` | Simple error text | Basic similarity for "not found" | None | None | None | Fastest |
| **enhanced** | `AF_ERROR_MODE=enhanced` | Rich contextual messages | Fuzzy matching with similarity scores | Preview at failure point | Binary search through operations | When available | Moderate overhead |
| **debug** | `AF_ERROR_MODE=debug` | Same as enhanced + verbose logging | Same as enhanced | Same as enhanced + debug info | Same as enhanced + logging | Same as enhanced | Higher overhead |
| **off** | `AF_ERROR_MODE=off` | Raw Polars errors only | None | None | None | None | Minimal overhead |

### Mode Combinations and Their Effects

| Execution Mode | Error Mode | Enhanced Error Handling Available? | Dataframe Context Available? | Notes |
|----------------|------------|-----------------------------------|------------------------------|-------|
| **debug** | basic | ❌ No | ❌ No | Default configuration - fast but minimal error info |
| **debug** | enhanced | ⚠️ Limited | ❌ No | Basic column suggestions only, no operation replay |
| **debug** | debug | ⚠️ Limited | ❌ No | Same as enhanced with verbose logging |
| **optimize** | basic | ❌ No | ❌ No | Operations captured but errors not enhanced |
| **optimize** | enhanced | ✅ **Yes** | ✅ **Yes** | **Full enhanced error handling with context** |
| **optimize** | debug | ✅ **Yes** | ✅ **Yes** | Same as enhanced with detailed logging |

### Configuration Methods

**Environment Variables:**
```bash
GASPATCHIO_MODE=optimize          # Set execution mode
AF_ERROR_MODE=enhanced           # Set error handling mode
GASPATCHIO_VERBOSE=true          # Enable verbose logging
```

**CLI Arguments (mix.py):**
```bash
uv run mix.py --mode optimize    # Sets execution mode for this run
```

**Programmatic:**
```python
from gaspatchio_core.util import set_default_mode, set_error_mode
set_default_mode("optimize")
set_error_mode("enhanced")
```

### Known Issues

1. **Mode Override Bug**: The tracing system uses `get_default_mode()` (global environment) instead of `frame._mode` (frame-specific), causing CLI `--mode` arguments to be ignored if environment variables are set differently.

2. **Compilation vs Execution Errors**: Enhanced error handling only works for execution-time errors. Compilation-time errors (like non-existent column references) bypass the operation replay system and show raw Polars query plans.

3. **Debug Mode Limitation**: In debug mode, operations execute immediately so there's no computation graph to replay for enhanced error context.

### To Get Full Enhanced Error Handling

**Required combination:**
```bash
GASPATCHIO_MODE=optimize AF_ERROR_MODE=enhanced uv run mix.py --mode optimize
```

**What you get:**
- Operations captured with source metadata
- Binary search replay to find exact failure point  
- Dataframe preview showing available columns at failure
- Fuzzy column name suggestions
- Source code location of failing operation

## Problem Statement

Currently, the enhanced error handling system works well for **execution-time errors** but provides limited context for **compilation-time errors**. When users reference non-existent columns, they get a raw Polars query plan instead of the enhanced error handling with dataframe context that shows where the error occurred and what data was available.

### Example Issue

When running a model with a bad column reference:
```python
af["claims cashflow"] = af["P[WHAT IS DEAD WILL NEVER DIE]"] * af["sum_assured"]
```

**Current behavior:**
- Shows Polars compilation error with full query plan
- No dataframe context showing what columns were available
- No source code location information
- Error occurs during `df.profile()` collection, not during model execution

**Expected behavior:**
- Clean error message: "Column 'P[WHAT IS DEAD WILL NEVER DIE]' not found"
- Show dataframe state at the point where the error would occur
- List available columns with suggestions
- Source code location of the failing operation

## Root Cause Analysis

### Error Flow
1. **Model function runs successfully** - All operations execute (in debug mode) or are captured (in optimize mode)
2. **Error occurs during collection** - When `df.profile()` calls `final_df.profile()`, Polars attempts to compile the query
3. **Compilation fails** - Polars detects non-existent column during query optimization
4. **Enhanced error handling skipped** - Because this is a compilation error, not an execution error with traced operations

### Why Enhanced Error Handling Doesn't Trigger

```python
# In _handle_execution_error()
has_traced_operations = False
if frame._computation_graph:
    has_traced_operations = any(
        not isinstance(op, tuple) for op in frame._computation_graph
    )

# Enhanced handling only triggers if we have TracedOperation objects
if has_traced_operations and error_mode in ["enhanced", "debug"]:
    # Binary search through computation graph
    # But compilation errors happen before this step
```

**Debug mode**: `_computation_graph` is empty because operations execute immediately
**Optimize mode**: `_computation_graph` has operations, but compilation error occurs before we can replay them

## Proposed Solution

### Phase 1: Compilation Error Detection and Step-by-Step Replay

#### 1.1 Enhanced Compilation Error Detection

Modify `_handle_execution_error()` to detect compilation errors and trigger enhanced handling:

```python
def _handle_execution_error(frame: ActuarialFrame, e: Exception):
    error_mode = get_error_mode()
    
    # Check for compilation errors
    is_compilation_error = (
        "FAILED HERE RESOLVING" in str(e) or
        "got invalid or ambiguous dtypes" in str(e) or
        isinstance(e, pl.exceptions.ComputeError)
    )
    
    if is_compilation_error and error_mode in ["enhanced", "debug"]:
        # Try step-by-step replay to find exact failure point
        return _handle_compilation_error_with_replay(frame, e)
    
    # Existing logic continues...
```

#### 1.2 Step-by-Step Replay for Compilation Errors

Create new function `_handle_compilation_error_with_replay()`:

```python
def _handle_compilation_error_with_replay(frame: ActuarialFrame, original_error: Exception):
    """
    When compilation fails, replay operations step-by-step to find 
    the exact failure point and show dataframe context.
    """
    
    # Start with the original dataframe
    current_df = frame._df
    last_good_df = current_df.collect() if hasattr(current_df, 'collect') else current_df
    
    # Get operations from either computation graph or by reconstructing them
    operations = _reconstruct_operations_from_frame(frame)
    
    # Apply operations one by one until we hit the failure
    for i, operation in enumerate(operations):
        try:
            # Try to apply this single operation
            test_df = current_df.with_columns(operation.expression.alias(operation.alias))
            # Test compilation by trying to collect schema
            _ = test_df.collect_schema()
            
            # Success - update current state
            current_df = test_df
            last_good_df = current_df.collect()
            
        except Exception as step_error:
            # Found the failing operation!
            return _format_compilation_error_with_context(
                operation=operation,
                step_error=step_error,
                original_error=original_error,
                last_good_df=last_good_df,
                operation_index=i
            )
    
    # If we get here, couldn't isolate the error
    return _handle_basic_column_error(frame, original_error)
```

#### 1.3 Operation Reconstruction

For debug mode where `_computation_graph` is empty, reconstruct operations from the frame state:

```python
def _reconstruct_operations_from_frame(frame: ActuarialFrame) -> list[TracedOperation]:
    """
    Reconstruct the operations that were applied to get to the current state.
    In debug mode, operations execute immediately so we need to infer them.
    """
    
    if frame._computation_graph:
        # Optimize mode - use existing graph
        return [op for op in frame._computation_graph if not isinstance(op, tuple)]
    
    # Debug mode - try to reconstruct from frame state
    # This is challenging but possible for simple cases
    original_columns = set(frame._original_schema.names()) if frame._original_schema else set()
    current_columns = set(frame._column_order)
    added_columns = current_columns - original_columns
    
    # Create pseudo-operations for added columns
    # This won't capture the exact expressions, but helps with error location
    operations = []
    for col_name in added_columns:
        # Create a TracedOperation placeholder
        operation = TracedOperation(
            alias=col_name,
            expression=pl.col(col_name),  # Placeholder
            metadata=SourceMetadata(
                file_name="unknown",
                line_number=0,
                source_line=f"af['{col_name}'] = ...",
                function_name="unknown"
            )
        )
        operations.append(operation)
    
    return operations
```

### Phase 2: Enhanced Context Display

#### 2.1 Compilation Error Formatter

Create specialized formatter for compilation errors:

```python
def _format_compilation_error_with_context(
    operation: TracedOperation,
    step_error: Exception, 
    original_error: Exception,
    last_good_df: pl.DataFrame,
    operation_index: int
) -> None:
    """Format compilation error with rich context."""
    
    # Extract missing column name from error
    missing_column = _extract_missing_column_from_compilation_error(step_error)
    
    # Get available columns
    available_columns = list(last_good_df.columns)
    similar_columns = _find_similar_columns(missing_column, available_columns)
    
    # Create enhanced error message
    error_msg = f"""❌ Column reference error in operation {operation_index + 1}
    
🔍 Problem: Column '{missing_column}' not found
   Operation: {operation.alias} = {operation.expression}
   
📊 DataFrame state before this operation:
   Shape: {last_good_df.shape}
   Columns: {', '.join(available_columns)}
   
💡 Did you mean one of these?
   {chr(10).join(f'   • {col}' for col in similar_columns[:3])}
   
🛠️  To fix:
   • Check spelling of column name '{missing_column}'
   • Verify the column was created in a previous operation
   • Use df.columns to see all available columns
   
📍 Source: {operation.metadata.file_name}:{operation.metadata.line_number}
   Code: {operation.metadata.source_line}
"""
    
    # Create enhanced exception
    enhanced_exception = type(step_error)(error_msg)
    enhanced_exception.llm_context = {
        "error_type": "compilation_column_error",
        "missing_column": missing_column,
        "available_columns": available_columns,
        "similar_columns": similar_columns,
        "operation_index": operation_index,
        "dataframe_shape": list(last_good_df.shape),
        "source_location": {
            "file": operation.metadata.file_name,
            "line": operation.metadata.line_number,
            "code": operation.metadata.source_line
        }
    }
    
    raise enhanced_exception from original_error
```

### Phase 3: Integration with Existing Error Handling

#### 3.1 Update Error Mode Logic

Modify the error mode checking to handle compilation errors:

```python
# In _handle_execution_error()
if not (
    frame._tracing or 
    frame._mode == "debug" or 
    error_mode in ["enhanced", "debug"] or
    _is_compilation_error(e)  # Add this condition
):
    raise e
```

#### 3.2 Update mix.py Error Display

The mix.py wrapper should detect enhanced compilation errors and display them properly:

```python
except Exception as e:
    error_msg = str(e)
    
    # Check for enhanced compilation error
    if hasattr(e, 'llm_context') and e.llm_context.get('error_type') == 'compilation_column_error':
        # Display the enhanced error as-is
        logger.error(error_msg)
    elif "FAILED HERE RESOLVING" in error_msg:
        # Fallback compilation error handling (current implementation)
        # ...existing logic...
    else:
        logger.error(error_msg)
```

## Implementation Plan

### Priority 1: Core Infrastructure
- [ ] Add compilation error detection in `_handle_execution_error()`
- [ ] Implement `_handle_compilation_error_with_replay()`
- [ ] Create `_format_compilation_error_with_context()`
- [ ] Update error mode logic

### Priority 2: Operation Reconstruction
- [ ] Implement `_reconstruct_operations_from_frame()` for debug mode
- [ ] Add better metadata tracking for operations
- [ ] Handle edge cases where reconstruction isn't possible

### Priority 3: Enhanced Display
- [ ] Update mix.py error handling for enhanced compilation errors
- [ ] Add dataframe preview formatting
- [ ] Improve column similarity suggestions
- [ ] Add more contextual hints

### Priority 4: Testing and Polish
- [ ] Add comprehensive tests for compilation error scenarios
- [ ] Test with both debug and optimize modes
- [ ] Verify performance impact is minimal
- [ ] Update documentation

## Benefits

1. **Better Developer Experience**: Clear, actionable error messages with context
2. **Faster Debugging**: See exactly what data was available when error occurred
3. **Consistent Error Handling**: Same enhanced experience for both execution and compilation errors
4. **Educational**: Helps users understand the operation sequence and dataframe evolution

## Considerations

### Performance Impact
- Step-by-step replay adds overhead for compilation errors
- Only triggered in enhanced/debug modes
- Could cache reconstruction results

### Complexity
- Operation reconstruction for debug mode is non-trivial
- Need to handle edge cases gracefully
- Fallback to basic error handling when reconstruction fails

### Compatibility
- Maintains existing error handling for production mode
- Backwards compatible with current error messages
- Optional enhanced behavior based on error mode setting

## Alternative Approaches

### Approach 1: Eager Validation
Instead of step-by-step replay, validate column references before operations:
- Pro: Faster, simpler implementation
- Con: Doesn't show dataframe evolution, less contextual

### Approach 2: Enhanced Logging
Add detailed logging during operation application:
- Pro: Minimal performance impact
- Con: Requires log parsing, less integrated experience

### Approach 3: IDE Integration
Focus on tooling/IDE support for column validation:
- Pro: Prevents errors before runtime
- Con: Doesn't help with dynamic column scenarios