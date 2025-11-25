# Task 4 TDD Implementation Plan

**Date:** 2025-01-10
**Approach:** Test-Driven Development with Red-Green-Refactor
**Execution:** Subagent-Driven Development

---

## Overview

This plan breaks down Task 4 (list broadcasting) into TDD cycles. Each cycle follows:
1. **RED** - Write failing test
2. **GREEN** - Minimal code to pass
3. **REFACTOR** - Clean up while keeping tests green

---

## Task 4.1: Add Metadata to ConditionalProxy

### Cycle 4.1.1: Add needs_list_broadcasting() method

**RED - Write failing test:**

File: `tests/functions/test_conditional.py`

```python
class TestConditionalProxyMetadata:
    """Tests for ConditionalProxy list broadcasting metadata."""

    def test_needs_list_broadcasting_returns_false_for_scalar(self) -> None:
        """Test needs_list_broadcasting returns False for scalar conditionals."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        conditional = when(af.age > 65).then(0.05)

        # Should be False - no list columns involved
        assert not conditional.needs_list_broadcasting()

    def test_needs_list_broadcasting_returns_true_for_list(self) -> None:
        """Test needs_list_broadcasting returns True for list conditionals."""
        af = ActuarialFrame({
            "month": [[0, 1, 2, 3, 4, 5]],
            "policy_term": [2],
        })

        conditional = when(af.month == af.policy_term * 12).then(1)

        # Should be True - month is a list column
        assert conditional.needs_list_broadcasting()
```

**Run test:** Should FAIL with AttributeError: 'ConditionalProxy' object has no attribute 'needs_list_broadcasting'

**GREEN - Minimal implementation:**

File: `gaspatchio_core/functions/conditional.py`

```python
class ConditionalProxy:
    """Represents an in-progress conditional expression chain."""

    def __init__(self, condition_expr: pl.Expr, parent: ActuarialFrame | None):
        self._conditions: list[pl.Expr] = [condition_expr]
        self._values: list[pl.Expr] = []
        self._parent = parent
        self._list_columns: set[str] | None = None  # NEW

    # ... existing methods ...

    def needs_list_broadcasting(self) -> bool:
        """Check if this conditional requires list broadcasting.

        Returns:
            True if any columns involved are list columns, False otherwise
        """
        if self._parent is None:
            return False

        # Detection hasn't happened yet - return False for now
        # Will be populated during otherwise()
        if self._list_columns is None:
            return False

        return len(self._list_columns) > 0
```

**Run test:** Should still FAIL - needs otherwise() to be called first

**Update test to call otherwise():**

```python
def test_needs_list_broadcasting_returns_true_for_list(self) -> None:
    """Test needs_list_broadcasting returns True for list conditionals."""
    af = ActuarialFrame({
        "month": [[0, 1, 2, 3, 4, 5]],
        "policy_term": [2],
    })

    # Call otherwise() to trigger detection
    conditional = when(af.month == af.policy_term * 12).then(1).otherwise(0)

    # Now check the original ConditionalProxy (need to store reference)
    # Actually, we need to check BEFORE otherwise() is called...
    # Let me rethink this test...
```

**REFACTOR - Fix test design:**

The issue is that `otherwise()` returns `ExpressionProxy`, not `ConditionalProxy`. We need to check the state differently.

**Better approach - test via side effects:**

```python
def test_list_broadcasting_detected_for_list_columns(self) -> None:
    """Test that list columns are detected during otherwise()."""
    af = ActuarialFrame({
        "month": [[0, 1, 2, 3, 4, 5]],
        "policy_term": [2],
    })

    # This should complete without raising NotImplementedError
    # (We'll remove the NotImplementedError in this task)
    try:
        af.result = when(af.month == af.policy_term * 12).then(1).otherwise(0)
        # For now, this will raise NotImplementedError - that's OK
        # We'll fix it in Task 4.2
    except NotImplementedError as e:
        # Verify the error message mentions the correct list columns
        assert "month" in str(e)
```

---

### Cycle 4.1.2: Populate _list_columns during otherwise()

**RED - Write test:**

```python
def test_list_columns_stored_in_metadata(self) -> None:
    """Test that detected list columns are accessible via metadata."""
    af = ActuarialFrame({
        "month": [[0, 1, 2]],
        "policy_term": [1],
        "pols_if": [[100, 99, 98]],
    })

    # Create conditional but don't call otherwise() yet
    conditional = when(af.month == af.policy_term * 12).then(af.pols_if)

    # Get metadata (will implement this method)
    metadata = conditional.get_list_broadcasting_metadata()

    # Should have detected month and pols_if as list columns
    assert "month" in metadata["list_columns"]
    assert "pols_if" in metadata["list_columns"]
```

**GREEN - Implement get_list_broadcasting_metadata():**

```python
def get_list_broadcasting_metadata(self) -> dict[str, Any]:
    """Get metadata needed for DataFrame-level list broadcasting.

    Returns:
        Dictionary containing:
        - conditions: List of condition expressions
        - values: List of then-value expressions
        - otherwise_expr: The otherwise value expression (if set)
        - list_columns: Set of detected list column names
    """
    # Need to build otherwise_expr if not done yet
    # For testing, we'll detect on-demand
    if self._list_columns is None:
        # Detection logic moved here
        self._list_columns = self._detect_list_columns_from_current_state()

    return {
        "conditions": self._conditions,
        "values": self._values,
        "otherwise_expr": None,  # Not set yet
        "list_columns": self._list_columns,
    }

def _detect_list_columns_from_current_state(self) -> set[str]:
    """Detect list columns from conditions and values so far."""
    if self._parent is None:
        return set()

    from gaspatchio_core.column import dispatch
    detector = dispatch.ColumnTypeDetector(self._parent)

    list_columns = set()

    # Check all expressions so far
    all_exprs = self._conditions + self._values

    for expr in all_exprs:
        col_names = self._extract_column_names(expr)
        for col_name in col_names:
            if detector.is_list_column(col_name):
                list_columns.add(col_name)

    return list_columns
```

**Run test:** Should PASS

---

### Cycle 4.1.3: Update otherwise() to populate metadata

**RED - Write test:**

```python
def test_otherwise_populates_list_columns(self) -> None:
    """Test that otherwise() triggers list column detection."""
    af = ActuarialFrame({
        "month": [[0, 1, 2]],
        "policy_term": [1],
    })

    # Before otherwise(), list_columns is None
    conditional = when(af.month == af.policy_term * 12).then(1)
    assert conditional._list_columns is None

    # After otherwise(), should be populated
    # (will still raise NotImplementedError, but metadata should be set)
    try:
        conditional.otherwise(0)
    except NotImplementedError:
        pass

    # Check metadata was populated
    assert conditional._list_columns is not None
    assert "month" in conditional._list_columns
```

**GREEN - Update otherwise():**

```python
def otherwise(self, value: Any) -> ExpressionProxy:
    """Complete chain with default value."""
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    # Convert otherwise value
    otherwise_expr = self._convert_value_to_expr(value)
    self._otherwise_expr = otherwise_expr  # NEW: Store it

    # Detect list columns INCLUDING otherwise value
    self._list_columns = self._detect_list_columns(otherwise_expr)

    # Build expression based on detection
    if self._list_columns:
        # List broadcasting needed
        expr = self._build_list_broadcasting_expr(otherwise_expr, self._list_columns)
    else:
        # Scalar path
        expr = self._build_scalar_conditional(otherwise_expr)

    return ExpressionProxy(expr, self._parent)
```

**Update _detect_list_columns to include otherwise:**

```python
def _detect_list_columns(self, otherwise_expr: pl.Expr) -> set[str]:
    """Detect list columns from all expressions including otherwise.

    Args:
        otherwise_expr: The otherwise value expression

    Returns:
        Set of list column names
    """
    if self._parent is None:
        return set()

    from gaspatchio_core.column import dispatch
    detector = dispatch.ColumnTypeDetector(self._parent)  # type: ignore[attr-defined]

    list_columns = set()

    # Check ALL expressions: conditions + values + otherwise
    all_exprs = self._conditions + self._values + [otherwise_expr]

    for expr in all_exprs:
        col_names = self._extract_column_names(expr)
        for col_name in col_names:
            if detector.is_list_column(col_name):
                list_columns.add(col_name)

    return list_columns
```

**Run test:** Should PASS

---

### Cycle 4.1.4: Remove NotImplementedError for now

**RED - Write test:**

```python
def test_list_broadcasting_returns_expression_proxy(self) -> None:
    """Test that list broadcasting returns ExpressionProxy (doesn't raise)."""
    af = ActuarialFrame({
        "month": [[0, 1, 2]],
        "policy_term": [1],
    })

    # Should return ExpressionProxy, not raise
    result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    assert isinstance(result, ExpressionProxy)
```

**GREEN - Update _build_list_broadcasting_expr:**

```python
def _build_list_broadcasting_expr(
    self, otherwise_expr: pl.Expr, list_columns: set[str]
) -> pl.Expr:
    """Build expression for list broadcasting.

    For now, return a marker expression that __setitem__ will detect.
    The actual explode/re-aggregate happens in ActuarialFrame.__setitem__.

    Args:
        otherwise_expr: The otherwise value expression
        list_columns: Set of list column names detected

    Returns:
        A struct expression containing metadata for __setitem__
    """
    # Build the standard scalar conditional expression
    # This will be used after explode
    base_expr = self._build_scalar_conditional(otherwise_expr)

    # Wrap in a struct with marker for __setitem__ to detect
    # Use a special marker field that __setitem__ can check
    return pl.struct(
        pl.lit("__list_broadcast_conditional__").alias("__marker__"),
        base_expr.alias("__conditional_expr__"),
        pl.lit(list(list_columns)).alias("__list_columns__"),
    )
```

**Run test:** Should PASS

**REFACTOR:**
- Clean up docstrings
- Remove old NotImplementedError code
- Ensure all tests still pass

---

## Task 4.2: Modify ActuarialFrame.__setitem__

### Cycle 4.2.1: Detect ConditionalProxy in __setitem__

**RED - Write test:**

File: `tests/frame/test_list_broadcasting.py` (new file)

```python
"""Tests for list broadcasting in ActuarialFrame.__setitem__."""

import pytest
from gaspatchio_core import ActuarialFrame, when


class TestListBroadcastingDetection:
    """Tests for detecting list broadcasting in __setitem__."""

    def test_setitem_detects_list_broadcasting_marker(self) -> None:
        """Test that __setitem__ detects list broadcasting marker struct."""
        af = ActuarialFrame({
            "month": [[0, 1, 2]],
            "policy_term": [1],
        })

        # This should NOT raise an error anymore
        af.result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

        # Result should be created
        assert "result" in af.collect().columns
```

**GREEN - Modify __setitem__:**

File: `gaspatchio_core/frame/base.py`

```python
def __setitem__(self, key: str, value: Any):
    """Handle column assignment using df['column'] = value."""
    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()

    try:
        expr = self._convert_to_expr(value)

        # NEW: Check if this is a list broadcasting conditional
        if self._is_list_broadcast_conditional(expr):
            self._apply_list_broadcasting(key, expr)
            return

        # Existing path for normal expressions
        if self._tracing:
            append_operation_to_graph(self, key, expr)
        else:
            self._df = self._df.with_columns(expr.alias(key))

    except Exception as e:
        # ... existing error handling

def _is_list_broadcast_conditional(self, expr: pl.Expr) -> bool:
    """Check if expression is a list broadcasting conditional.

    Args:
        expr: Expression to check

    Returns:
        True if this is a list broadcasting conditional marker
    """
    try:
        # Check if expr is a struct with our marker field
        # We'll need to inspect the expression metadata
        # For now, simple check - if it's a struct with specific fields

        # Try to get field names
        # This is tricky - we might need to actually execute to check
        # For MVP, we can check the expression's serialization

        expr_str = str(expr)
        return "__list_broadcast_conditional__" in expr_str
    except Exception:
        return False

def _apply_list_broadcasting(self, key: str, expr: pl.Expr) -> None:
    """Apply list broadcasting using explode/re-aggregate.

    Args:
        key: Column name to create
        expr: Marker struct expression containing conditional metadata
    """
    # For now, just raise NotImplementedError with better message
    raise NotImplementedError(
        f"List broadcasting for column '{key}' detected but not yet implemented. "
        "This will be implemented in cycle 4.2.2-4.2.4."
    )
```

**Run test:** Should FAIL with new NotImplementedError (but detection works!)

---

### Cycle 4.2.2: Extract metadata from marker struct

**RED - Write test:**

```python
def test_extract_list_broadcasting_metadata(self) -> None:
    """Test extracting metadata from list broadcasting marker."""
    af = ActuarialFrame({
        "month": [[0, 1, 2]],
        "policy_term": [1],
    })

    # Create marker expression
    expr = when(af.month == af.policy_term * 12).then(1).otherwise(0)
    marker_expr = af._convert_to_expr(expr)

    # Extract metadata
    metadata = af._extract_list_broadcast_metadata(marker_expr)

    # Should have list_columns
    assert "month" in metadata["list_columns"]
    assert "conditional_expr" in metadata
```

**GREEN - Implement extraction:**

```python
def _extract_list_broadcast_metadata(self, expr: pl.Expr) -> dict[str, Any]:
    """Extract metadata from list broadcasting marker struct.

    Args:
        expr: Marker struct expression

    Returns:
        Dictionary with conditional_expr and list_columns
    """
    # Execute the marker struct to get the metadata
    # Create a temporary single-row DataFrame to evaluate the struct
    temp_df = pl.DataFrame({"_dummy": [1]})
    result = temp_df.select(expr.alias("_marker")).row(0, named=True)

    marker_struct = result["_marker"]

    return {
        "conditional_expr": marker_struct["__conditional_expr__"],
        "list_columns": marker_struct["__list_columns__"],
    }
```

**Run test:** Should PASS

---

### Cycle 4.2.3: Implement explode/re-aggregate builder

**RED - Write test:**

```python
def test_build_list_broadcasting_df_simple(self) -> None:
    """Test building DataFrame with explode/re-aggregate for simple case."""
    af = ActuarialFrame({
        "month": [[0, 1, 2, 3]],
        "policy_term": [0],  # Maturity at month 0
        "pols_if": [[100, 99, 98, 97]],
    })

    # Build conditional expression (scalar version)
    conditional_expr = (
        pl.when(pl.col("month") == pl.col("policy_term") * 12)
        .then(pl.col("pols_if"))
        .otherwise(0)
    )

    # Apply list broadcasting
    result_df = af._build_list_broadcasting_df(
        result_col="pols_maturity",
        conditional_expr=conditional_expr,
        list_columns={"month", "pols_if"},
    )

    # Check result
    assert "pols_maturity" in result_df.columns
    maturity = result_df["pols_maturity"][0]
    assert maturity[0] == 100  # month 0 matches
    assert maturity[1] == 0    # month 1 doesn't match
```

**GREEN - Implement builder:**

```python
def _build_list_broadcasting_df(
    self,
    result_col: str,
    conditional_expr: pl.Expr,
    list_columns: set[str],
) -> pl.DataFrame:
    """Build DataFrame with list broadcasting using explode/re-aggregate.

    Args:
        result_col: Name of output column
        conditional_expr: Scalar conditional expression to apply after explode
        list_columns: Set of list column names to explode

    Returns:
        DataFrame with result_col added
    """
    # Get all column names
    all_columns = set(self._df.columns)
    scalar_columns = all_columns - list_columns

    # Apply explode/re-aggregate pattern
    return (
        self._df
        .with_row_index("_row_id")
        .explode(list(list_columns))
        .with_columns(**{result_col: conditional_expr})
        .group_by("_row_id", maintain_order=True)
        .agg([
            # Aggregate list columns back
            *[pl.col(col) for col in list_columns],
            # Keep scalar columns (take first)
            *[pl.col(col).first() for col in scalar_columns],
            # Aggregate result column
            pl.col(result_col),
        ])
        .drop("_row_id")
    )
```

**Run test:** Should PASS

---

### Cycle 4.2.4: Wire up full pipeline in __setitem__

**RED - Write test:**

```python
def test_list_broadcasting_end_to_end(self) -> None:
    """Test complete list broadcasting from when() to result."""
    af = ActuarialFrame({
        "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
        "policy_term": [1],
        "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
    })

    # This should now WORK!
    af.pols_maturity = (
        when(af.month == af.policy_term * 12)
        .then(af.pols_if)
        .otherwise(0)
    )

    result = af.collect()

    # Verify result
    maturity = result["pols_maturity"][0]
    assert len(maturity) == 13

    # All zeros except position 12
    for i in range(12):
        assert maturity[i] == 0
    assert maturity[12] == 88  # Surviving at maturity
```

**GREEN - Complete implementation:**

Actually, need to rethink the marker struct approach. It's getting complex.

**REFACTOR - Simpler approach:**

Instead of marker struct, check if value is ConditionalProxy directly in __setitem__:

```python
def __setitem__(self, key: str, value: Any):
    """Handle column assignment using df['column'] = value."""
    # Import here to avoid circular import
    from gaspatchio_core.functions.conditional import ConditionalProxy

    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()

    # NEW: Check if value is ConditionalProxy needing list broadcasting
    if isinstance(value, ConditionalProxy):
        if value.needs_list_broadcasting():
            self._apply_conditional_list_broadcasting(key, value)
            return
        else:
            # Scalar conditional - call otherwise() hasn't been called yet
            # This shouldn't happen in normal usage
            raise TypeError(
                f"ConditionalProxy for column '{key}' is incomplete. "
                "Did you forget to call .otherwise()?"
            )

    # Standard path
    try:
        expr = self._convert_to_expr(value)

        if self._tracing:
            append_operation_to_graph(self, key, expr)
        else:
            self._df = self._df.with_columns(expr.alias(key))
```

Wait, that won't work either - `otherwise()` returns `ExpressionProxy`, not `ConditionalProxy`.

**Better approach - Store reference in ExpressionProxy:**

```python
# In ConditionalProxy.otherwise():
def otherwise(self, value: Any) -> ExpressionProxy:
    # ... existing code ...

    result = ExpressionProxy(expr, self._parent)

    # NEW: Attach metadata if list broadcasting
    if self._list_columns:
        result._list_broadcast_metadata = {
            "conditional_proxy": self,
            "list_columns": self._list_columns,
        }

    return result
```

Then in __setitem__:

```python
def __setitem__(self, key: str, value: Any):
    # ... setup ...

    try:
        expr = self._convert_to_expr(value)

        # NEW: Check for list broadcast metadata
        if hasattr(value, "_list_broadcast_metadata"):
            metadata = value._list_broadcast_metadata
            self._apply_conditional_list_broadcasting(key, metadata)
            return

        # Standard path
        # ...
```

This is cleaner! Let me write that up properly.

---

## Simplified Task 4.2 Approach

**Strategy:** Attach metadata to ExpressionProxy when list broadcasting detected.

### Cycle 4.2.1: Attach metadata to ExpressionProxy

**RED - Test:**

```python
def test_expression_proxy_carries_list_broadcast_metadata(self) -> None:
    """Test that ExpressionProxy carries list broadcast metadata."""
    af = ActuarialFrame({
        "month": [[0, 1, 2]],
        "policy_term": [1],
    })

    result = when(af.month == af.policy_term * 12).then(1).otherwise(0)

    # Should have metadata attached
    assert hasattr(result, "_list_broadcast_metadata")
    assert "month" in result._list_broadcast_metadata["list_columns"]
```

**GREEN - Implementation:**

In `conditional.py`:

```python
def otherwise(self, value: Any) -> ExpressionProxy:
    """Complete chain with default value."""
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    otherwise_expr = self._convert_value_to_expr(value)
    self._list_columns = self._detect_list_columns(otherwise_expr)

    if self._list_columns:
        # Build scalar conditional (will be used after explode)
        expr = self._build_scalar_conditional(otherwise_expr)

        # Create ExpressionProxy with metadata
        result = ExpressionProxy(expr, self._parent)
        result._list_broadcast_metadata = {
            "list_columns": self._list_columns,
            "conditional_expr": expr,
        }
        return result
    else:
        # Scalar path - no metadata needed
        expr = self._build_scalar_conditional(otherwise_expr)
        return ExpressionProxy(expr, self._parent)
```

### Cycle 4.2.2-4: Implement __setitem__ detection and execution

**Tests and implementation as shown above in earlier cycles, but using the metadata approach.**

---

## Task 4.3: Update Tests

**Simply remove the NotImplementedError expectations:**

```python
# OLD:
def test_maturity_calculation(self) -> None:
    """Test realistic maturity calculation."""
    af = ActuarialFrame({...})

    with pytest.raises(NotImplementedError):
        af.pols_maturity = when(...).then(...).otherwise(0)

# NEW:
def test_maturity_calculation(self) -> None:
    """Test realistic maturity calculation."""
    af = ActuarialFrame({...})

    af.pols_maturity = when(...).then(...).otherwise(0)

    result = af.collect()
    assert result["pols_maturity"][0] == [0, 0, ..., 88]
```

---

## Task 4.4: Handle Computation Graph

**For now, just disable:**

```python
def _apply_conditional_list_broadcasting(self, key: str, metadata: dict) -> None:
    """Apply list broadcasting."""
    if self._tracing:
        raise NotImplementedError(
            f"List broadcasting for column '{key}' not yet supported in tracing mode. "
            "Use optimize mode (.optimize()) instead. "
            "Full tracing support coming in Task 5."
        )

    # Build and execute
    list_columns = metadata["list_columns"]
    conditional_expr = metadata["conditional_expr"]

    self._df = self._build_list_broadcasting_df(key, conditional_expr, list_columns)
```

---

## Summary of TDD Cycles

| Cycle | Test | Implementation | Time |
|-------|------|----------------|------|
| 4.1.1 | needs_list_broadcasting() exists | Add method returning False | 20min |
| 4.1.2 | get_list_broadcasting_metadata() | Add metadata method | 20min |
| 4.1.3 | otherwise() populates metadata | Update otherwise() | 20min |
| 4.1.4 | Returns ExpressionProxy with metadata | Attach metadata to ExpressionProxy | 20min |
| 4.2.1 | __setitem__ detects metadata | Add detection logic | 30min |
| 4.2.2 | _build_list_broadcasting_df() works | Implement explode/re-aggregate | 1hr |
| 4.2.3 | _apply_conditional_list_broadcasting() | Wire up pipeline | 30min |
| 4.2.4 | End-to-end test passes | Integration fixes | 1hr |
| 4.3 | Remove NotImplementedError | Update test expectations | 30min |
| 4.4 | Computation graph handling | Add tracing check | 20min |

**Total:** ~5 hours

---

## Execution Plan

Use subagent-driven development:

1. Dispatch subagent for Cycle 4.1 (all subcycles)
2. Code review
3. Dispatch subagent for Cycle 4.2 (all subcycles)
4. Code review
5. Dispatch subagent for Cycle 4.3
6. Code review
7. Dispatch subagent for Cycle 4.4
8. Code review
9. Final integration test
10. Run scratch examples - should see "✅ SUCCESS!"

---

## Success Criteria

- ✅ All TDD tests pass
- ✅ Existing scalar tests still pass
- ✅ List broadcasting tests (previously failing) now pass
- ✅ Scratch examples show "✅ SUCCESS!"
- ✅ No regressions in test suite
- ✅ Works in optimize mode
- ⚠️ Raises clear error in tracing mode (Task 5)
