# Enhanced Error Handling for Validation Errors

## Problem Statement

Currently, the enhanced error handling system only works for Polars execution errors that occur during `collect()` or `profile()`. Validation errors (e.g., invalid parameters, type mismatches) that occur before Polars operations are executed bypass the enhanced formatting and show basic error messages without context.

Example:
```python
# This typo produces a basic ValueError
af.date.create_projection_timeline(
    projection_end_type="term_monts",  # Typo: should be "term_months"
    ...
)
# Output: ValueError: Invalid projection end type: term_monts
```

## Goals

1. Provide the same rich error formatting for validation errors as we do for execution errors
2. Show source location (file, line number, function name)
3. Display the problematic source code with syntax highlighting
4. Provide helpful suggestions (e.g., "Did you mean 'term_months'?")
5. Maintain backward compatibility
6. Minimal performance impact in production mode

## Design Overview

### 1. Validation Error Capture System

Create a decorator that captures source location information when validation errors occur:

```python
@capture_validation_context
def create_projection_timeline(self, ...):
    # Validation happens here
    if projection_end_type not in valid_types:
        raise ValidationError(
            f"Invalid projection end type: {projection_end_type}",
            valid_options=valid_types,
            provided_value=projection_end_type
        )
```

### 2. Enhanced Exception Classes

Create specialized exception classes that carry metadata:

```python
class ValidationError(ValueError):
    """Enhanced validation error with source context."""
    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context
        self.source_location = None  # Set by decorator
```

### 3. Source Location Tracking

The `@capture_validation_context` decorator will:
- Use `inspect` to capture the caller's file, line number, and function
- Attach this information to raised exceptions
- Only activate in debug mode for performance

### 4. Integration with Error Formatting System

Extend `_handle_execution_error` to also handle validation errors:

```python
def _handle_frame_error(frame: ActuarialFrame, e: Exception):
    """Handle both execution and validation errors."""
    if isinstance(e, ValidationError):
        return _handle_validation_error(frame, e)
    else:
        return _handle_execution_error(frame, e)
```

### 5. Rich Formatting for Validation Errors

Format validation errors with the same style as execution errors:

```
────────────────────────────────────────────────────────────────────────────────
❌ Validation Error

📍 Location: gaspatchio-models/models/basic_term/model_projection.py:51
   Function: main
   
📝 Source Code:
   ```python
   af = af.date.create_projection_timeline(
       valuation_date=val_date,
       projection_end_type="term_monts",  # <-- Error here
       projection_end_value=max_projection_length,
       projection_frequency="monthly",
   ```

🔴 Error Details:
   Type: ValidationError
   Message: Invalid projection end type: term_monts

💡 Did you mean one of these?
   • term_months
   • term_years
   • maximum_age
   • fixed_date

────────────────────────────────────────────────────────────────────────────────
```

## Implementation Details

### 1. Decorator Implementation

```python
def capture_validation_context(func):
    """Decorator to capture source context for validation errors."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValueError, TypeError, KeyError) as e:
            # Only enhance in debug mode
            frame = _get_frame_from_args(args)
            if frame and (frame._mode == "debug" or get_error_mode() in ["enhanced", "debug"]):
                # Capture caller information
                caller_frame = inspect.currentframe().f_back
                source_info = inspect.getframeinfo(caller_frame)
                
                # Create enhanced exception
                if isinstance(e, ValidationError):
                    e.source_location = SourceLocation(
                        file_path=source_info.filename,
                        line_number=source_info.lineno,
                        function_name=caller_frame.f_code.co_name,
                        source_line=_get_source_line(source_info)
                    )
                else:
                    # Convert to ValidationError
                    enhanced = ValidationError(str(e))
                    enhanced.__cause__ = e
                    enhanced.source_location = SourceLocation(...)
                    raise enhanced
            raise
    return wrapper
```

### 2. Fuzzy Matching for Suggestions

For string validation errors (like typos), use fuzzy matching to suggest corrections:

```python
def _suggest_valid_options(invalid_value: str, valid_options: list[str]) -> list[str]:
    """Find similar valid options using fuzzy matching."""
    if not fuzz:
        return []
    
    scores = [(opt, fuzz.ratio(invalid_value, opt)) for opt in valid_options]
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Return top 3 matches with score > 70
    return [opt for opt, score in scores[:3] if score > 70]
```

### 3. Runner Integration

Modify the runner to respect enhanced validation errors:

```python
def _execute_model_run(...):
    try:
        dsl_run_model(model_func, df)
        result_df, profile_info = df.profile()
    except ValidationError as e:
        # Check if it has enhanced formatting
        if hasattr(e, 'source_location') and e.source_location:
            # Format as enhanced error
            formatter = ValidationErrorFormatter(e)
            error_message = formatter.format_error()
        else:
            error_message = str(e)
        
        return ModelRunResult(
            status="error",
            error_message=error_message,
            error_context={"validation_error": True, ...}
        )
```

### 4. Performance Considerations

- Decorators only capture context in debug mode
- Source location tracking uses lazy evaluation
- No impact on production performance
- Minimal overhead even in debug mode

### 5. Backward Compatibility

- Existing error handling continues to work
- ValidationError extends ValueError, so existing except clauses still work
- Enhanced formatting is opt-in via debug mode or error mode settings

## Testing Strategy

1. Unit tests for validation error capture
2. Integration tests with ActuarialFrame methods
3. Performance benchmarks to ensure minimal overhead
4. Test all validation points in the codebase
5. Ensure proper fallback when enhancement fails

## Migration Plan

1. Phase 1: Implement core ValidationError and decorator
2. Phase 2: Apply to high-impact validation points (date accessors, assumptions)
3. Phase 3: Extend to all validation throughout the codebase
4. Phase 4: Add fuzzy matching suggestions where applicable

## Future Extensions

1. Validation error aggregation (collect multiple validation errors)
2. Context-aware suggestions based on common mistakes
3. Integration with type checking for better error messages
4. Custom validation error types for specific domains (dates, finance, etc.)
