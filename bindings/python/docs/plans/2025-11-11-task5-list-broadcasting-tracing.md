# ABOUTME: Implementation plan for Task 5 - List Broadcasting in Debug/Tracing Mode
# ABOUTME: Enables when-then conditionals with list columns to work in debug mode using eager execution

# Task 5: List Broadcasting in Debug/Tracing Mode

**Date:** 2025-11-11
**Estimated Duration:** 8 hours
**Approach:** Option A - Eager Execution with Tracing

## Overview

Currently, when-then conditional expressions using list broadcasting fail in debug/tracing mode with:
```
NotImplementedError: List broadcasting for column 'pols_maturity' not yet supported in tracing mode.
Use optimize mode (.optimize()) instead. Full tracing support coming in Task 5.
```

This task implements eager execution of the explode/re-aggregate pattern in debug mode while capturing each step as TracedOperations for visibility and debugging.

## Problem Statement

The issue is in `gaspatchio_core/frame/base.py:1906-1912`:

```python
def _apply_conditional_list_broadcasting(self, key: str, metadata: dict[str, Any]) -> None:
    if self._tracing:
        msg = (
            f"List broadcasting for column '{key}' not yet supported in tracing mode. "
            "Use optimize mode (.optimize()) instead. "
            "Full tracing support coming in Task 5."
        )
        raise NotImplementedError(msg)
```

When `self._tracing` is True (debug mode), the method raises an error instead of executing the list broadcasting logic.

## Solution Design

Instead of raising NotImplementedError in tracing mode, we will:

1. Execute the explode/re-aggregate pattern immediately (eager execution)
2. Capture intermediate steps as TracedOperations with special metadata
3. Apply the result to `self._df` just like in optimize mode
4. Store pattern metadata for visualization/debugging

This maintains the tracing/debugging benefits while enabling the feature to work.

## Implementation Tasks

### Task 5.1: Create List Broadcasting Metadata Model

**Goal:** Add data model to represent list broadcasting operations in the computation graph

**Files to Modify:**
- `gaspatchio_core/frame/graph/graph_models.py`

**Implementation Steps:**

1. Add a new `ListBroadcastMetadata` model to capture list broadcasting pattern details:

```python
class ListBroadcastMetadata(BaseModel):
    """Metadata for list broadcasting operations using explode/re-aggregate pattern."""

    result_column: str = Field(description="Name of the result column being created")
    list_columns: list[str] = Field(description="List columns that were exploded")
    conditional_expr: str = Field(description="String representation of conditional expression")
    pattern_steps: list[str] = Field(
        default_factory=list,
        description="Steps in the pattern: with_row_index, explode, with_columns, group_by, agg, drop"
    )
```

2. Update `NodeData` to include optional list broadcasting metadata:

```python
class NodeData(BaseModel):
    # ... existing fields ...
    list_broadcast: ListBroadcastMetadata | None = Field(
        default=None,
        description="Metadata for list broadcasting operations"
    )
```

**Verification:**
- Import the module and verify the new classes exist
- No runtime behavior changes yet

**Commit Message:**
```
feat(task-5.1): add list broadcasting metadata model

Add ListBroadcastMetadata to capture explode/re-aggregate pattern
details in computation graph for debug mode tracing.

Task 5.1 of enabling list broadcasting in tracing mode.
```

---

### Task 5.2: Add Helper to Create List Broadcasting TracedOperations

**Goal:** Create a helper function to generate TracedOperation objects for list broadcasting steps

**Files to Modify:**
- `gaspatchio_core/frame/tracing.py`

**Implementation Steps:**

1. Add new function `create_list_broadcast_traced_operations` after line 165:

```python
def create_list_broadcast_traced_operations(
    frame_instance: ActuarialFrame,
    result_col: str,
    list_columns: set[str],
    conditional_expr: pl.Expr,
    metadata: OperationMetadata | None = None,
) -> list[TracedOperation]:
    """Create TracedOperation objects for a list broadcasting operation.

    Args:
        frame_instance: The ActuarialFrame being operated on
        result_col: Name of the result column
        list_columns: Set of list columns being broadcast
        conditional_expr: The conditional expression being applied
        metadata: Optional source metadata (captured from user code)

    Returns:
        List of TracedOperation objects representing the pattern steps
    """
    from ..errors.metadata import TracedOperation, capture_source_context
    from .graph.graph_models import ListBroadcastMetadata

    # Capture metadata if not provided
    if metadata is None:
        # Try to find user code in stack (skip internal frames)
        for depth in range(2, 8):
            temp_metadata = capture_source_context(depth=depth)
            if not any(internal in temp_metadata.file_name for internal in [
                "gaspatchio_core/frame/",
                "gaspatchio_core/column/",
                "gaspatchio_core/functions/",
                "<frozen",
                "site-packages/"
            ]):
                metadata = temp_metadata
                break
        if metadata is None:
            metadata = capture_source_context(depth=2)

    # Create list broadcasting metadata
    list_broadcast_meta = ListBroadcastMetadata(
        result_column=result_col,
        list_columns=sorted(list(list_columns)),  # Convert set to sorted list for consistency
        conditional_expr=str(conditional_expr),
        pattern_steps=[
            "with_row_index('_row_id')",
            f"explode({sorted(list(list_columns))})",
            f"with_columns({result_col}=<conditional>)",
            "group_by('_row_id', maintain_order=True)",
            "agg(<list columns + result>)",
            "drop('_row_id')"
        ]
    )

    # Infer result type (should be List[inner_type])
    result_dtype = _infer_expression_type(conditional_expr, frame_instance)
    if result_dtype is not None:
        # Wrap in List type if not already
        import polars as pl
        if not isinstance(result_dtype, pl.List):
            result_dtype = pl.List(result_dtype)

    # Extract dependencies from the conditional expression
    from .graph import extract_dependencies
    dependencies = extract_dependencies(conditional_expr)

    # Create a single TracedOperation representing the entire pattern
    # We could create one per step, but that would clutter the graph
    # A single operation with detailed metadata is clearer
    operation = TracedOperation(
        alias=result_col,
        expression=f"when(...).then(...).otherwise(...) [list broadcast: {', '.join(sorted(list(list_columns)))}]",
        metadata=metadata,
        expected_dtype=result_dtype,
        dependencies=dependencies,
    )

    logger.trace(
        f"Graph: Added list broadcasting operation '{result_col}' "
        f"(list_cols={sorted(list(list_columns))}, deps={dependencies}) "
        f"at {metadata.display_filename}:{metadata.line_number}"
    )

    return [operation]
```

**Verification:**
- Add a docstring test showing usage (won't execute yet since tracing path not implemented)
- Import the function successfully

**Commit Message:**
```
feat(task-5.2): add helper for list broadcast traced operations

Create helper function to generate TracedOperation objects that
represent list broadcasting patterns in the computation graph.

Task 5.2 of enabling list broadcasting in tracing mode.
```

---

### Task 5.3: Write Failing Test for List Broadcasting in Debug Mode

**Goal:** Write test that demonstrates the current failure and will pass after implementation

**Files to Create:**
- `tests/accessors/test_list_broadcasting_debug_mode.py`

**Implementation Steps:**

1. Create comprehensive test file:

```python
# ABOUTME: Test list broadcasting conditionals work in debug mode
# ABOUTME: Verifies when-then-otherwise with list columns traces operations correctly
# ruff: noqa: S101, PLR2004, ANN201
# type: ignore[attr-defined]

"""Test that list broadcasting conditionals work in debug mode with tracing."""

import pytest

from gaspatchio_core import ActuarialFrame, when


class TestListBroadcastingDebugMode:
    """Test list broadcasting in debug/tracing mode (Task 5)."""

    def test_simple_conditional_debug_mode(self):
        """Test simple when-then-otherwise with list columns in debug mode.

        This test currently fails with NotImplementedError.
        After Task 5, it should pass and capture traced operations.
        """
        data = {
            "policy_id": [1, 2],
            "months": [[0, 1, 2], [0, 1, 2]],
            "values": [[100.0, 200.0, 300.0], [150.0, 250.0, 350.0]]
        }
        af = ActuarialFrame(data)

        # Enable debug mode (tracing)
        af = af.debug()

        # Apply conditional with list broadcasting
        # Currently raises: NotImplementedError: List broadcasting for column 'adjusted'
        # not yet supported in tracing mode
        af.adjusted = when(af.months == 0).then(0.0).otherwise(af.values)

        # Should capture the operation in computation graph
        assert len(af._computation_graph) > 0
        assert any(op.alias == "adjusted" for op in af._computation_graph)

        # Collect and verify results
        result = af.collect()

        # Policy 1: month 0 should be 0.0, others should be original values
        assert result["adjusted"][0] == [0.0, 200.0, 300.0]
        # Policy 2: month 0 should be 0.0, others should be original values
        assert result["adjusted"][1] == [0.0, 250.0, 350.0]

    def test_multiple_conditionals_debug_mode(self):
        """Test multiple when-then-otherwise operations in debug mode."""
        data = {
            "policy_id": [1],
            "month": [[0, 1, 2, 3, 4, 5]],
            "amount": [[1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0]]
        }
        af = ActuarialFrame(data)
        af = af.debug()

        # First conditional: zero out first month
        af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)

        # Second conditional: double values in months 2-3
        af.doubled = when((af.month >= 2) & (af.month <= 3)).then(af.adjusted * 2).otherwise(af.adjusted)

        # Should have two operations in graph
        assert len(af._computation_graph) >= 2
        assert any(op.alias == "adjusted" for op in af._computation_graph)
        assert any(op.alias == "doubled" for op in af._computation_graph)

        result = af.collect()

        # Expected: [0.0, 1100.0, 2400.0, 2600.0, 1400.0, 1500.0]
        #           month 0: 0.0 (zeroed)
        #           month 1: 1100.0 (unchanged)
        #           months 2-3: doubled (1200*2, 1300*2)
        #           months 4-5: unchanged
        expected = [0.0, 1100.0, 2400.0, 2600.0, 1400.0, 1500.0]
        assert result["doubled"][0] == pytest.approx(expected, abs=1e-6)

    def test_actuarial_pattern_debug_mode(self):
        """Test realistic actuarial pattern: maturity and zeroing after maturity."""
        data = {
            "policy_id": [1, 2],
            "policy_term": [2, 3],  # 2 years = 24 months, 3 years = 36 months
            "month": [[0, 12, 24, 36], [0, 12, 24, 36]],
            "pols_if_raw": [[1000.0, 950.0, 900.0, 850.0], [2000.0, 1900.0, 1800.0, 1700.0]]
        }
        af = ActuarialFrame(data)
        af = af.debug()

        # Maturity: surviving policies mature when month == policy_term * 12
        af.pols_maturity = (
            when(af.month == af.policy_term * 12)
            .then(af.pols_if_raw)
            .otherwise(0.0)
        )

        # Zero out policies at and after maturity
        af.pols_if = (
            when(af.month < af.policy_term * 12)
            .then(af.pols_if_raw)
            .otherwise(0.0)
        )

        # Should trace both operations
        assert len(af._computation_graph) >= 2

        result = af.collect()

        # Policy 1 (term=2, matures at month 24):
        # pols_maturity: [0, 0, 900.0, 0]
        # pols_if: [1000.0, 950.0, 0, 0]
        assert result["pols_maturity"][0] == [0.0, 0.0, 900.0, 0.0]
        assert result["pols_if"][0] == [1000.0, 950.0, 0.0, 0.0]

        # Policy 2 (term=3, matures at month 36):
        # pols_maturity: [0, 0, 0, 1700.0]
        # pols_if: [2000.0, 1900.0, 1800.0, 0]
        assert result["pols_maturity"][1] == [0.0, 0.0, 0.0, 1700.0]
        assert result["pols_if"][1] == [2000.0, 1900.0, 1800.0, 0.0]

    def test_computation_graph_metadata(self):
        """Test that list broadcasting operations include proper metadata."""
        data = {
            "policy_id": [1],
            "duration": [[0, 1, 2]],
            "premium": [[100.0, 100.0, 100.0]]
        }
        af = ActuarialFrame(data)
        af = af.debug()

        # Apply conditional
        af.commission = when(af.duration == 0).then(af.premium).otherwise(0.0)

        # Find the traced operation
        commission_op = None
        for op in af._computation_graph:
            if op.alias == "commission":
                commission_op = op
                break

        assert commission_op is not None, "commission operation not in graph"
        assert commission_op.expected_dtype is not None, "expected_dtype should be inferred"
        assert commission_op.dependencies is not None, "dependencies should be extracted"
        assert "duration" in commission_op.dependencies
        assert "premium" in commission_op.dependencies

        # Check metadata has source location
        assert commission_op.metadata is not None
        assert commission_op.metadata.line_number > 0
```

2. Run the test to confirm it fails:

```bash
cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python
uv run pytest tests/accessors/test_list_broadcasting_debug_mode.py -v
```

**Expected Outcome:** All 4 tests should fail with `NotImplementedError: List broadcasting for column '...' not yet supported in tracing mode.`

**Verification:**
- Tests fail with expected error message
- Test file follows project conventions (ruff, type: ignore, pytest patterns)

**Commit Message:**
```
test(task-5.3): add failing tests for list broadcasting in debug mode

Add comprehensive tests for when-then conditionals with list columns
in debug/tracing mode. Tests currently fail with NotImplementedError.

Tests cover:
- Simple conditionals
- Multiple sequential conditionals
- Actuarial patterns (maturity, zeroing)
- Computation graph metadata

Task 5.3 of enabling list broadcasting in tracing mode.
```

---

### Task 5.4: Implement Eager Execution Path in _apply_conditional_list_broadcasting

**Goal:** Remove NotImplementedError and implement eager execution with tracing

**Files to Modify:**
- `gaspatchio_core/frame/base.py`

**Implementation Steps:**

1. Replace the NotImplementedError block (lines 1906-1912) with eager execution logic:

```python
def _apply_conditional_list_broadcasting(
    self, key: str, metadata: dict[str, Any]
) -> None:
    """Apply list broadcasting for conditional expressions.

    Args:
        key: Name of the column to create
        metadata: Metadata dictionary with list_columns and conditional_expr

    In tracing mode (debug), this executes the pattern eagerly and captures
    the operation in the computation graph. In optimize mode, it just applies
    the transformation directly.
    """
    # Extract metadata
    list_columns = metadata["list_columns"]
    conditional_expr = metadata["conditional_expr"]

    # In tracing mode: execute eagerly AND capture operation
    if self._tracing:
        from .tracing import create_list_broadcast_traced_operations
        from ..errors.metadata import capture_source_context

        # Capture source location from user code
        source_metadata = None
        for depth in range(2, 10):
            temp_metadata = capture_source_context(depth=depth)
            if not any(internal in temp_metadata.file_name for internal in [
                "gaspatchio_core/frame/",
                "gaspatchio_core/column/",
                "gaspatchio_core/functions/",
                "<frozen",
                "site-packages/"
            ]):
                source_metadata = temp_metadata
                break

        # Create traced operations for this list broadcasting
        traced_ops = create_list_broadcast_traced_operations(
            frame_instance=self,
            result_col=key,
            list_columns=list_columns,
            conditional_expr=conditional_expr,
            metadata=source_metadata
        )

        # Append to computation graph
        self._computation_graph.extend(traced_ops)

        logger.trace(
            f"Debug mode: Executing list broadcasting for '{key}' eagerly "
            f"and captured {len(traced_ops)} operation(s)"
        )

    # Execute the pattern (both modes reach here now)
    self._df = self._build_list_broadcasting_df(key, conditional_expr, list_columns)
```

**Verification:**
- Code compiles without errors
- Logic is clear: tracing mode captures operations THEN executes, optimize mode just executes

**Commit Message:**
```
feat(task-5.4): implement eager execution for list broadcasting in debug mode

Replace NotImplementedError with eager execution path that:
1. Captures traced operations with metadata
2. Executes explode/re-aggregate pattern immediately
3. Adds operations to computation graph for debugging

Both debug and optimize modes now execute the pattern, but debug mode
also captures the operation for tracing/visualization.

Task 5.4 of enabling list broadcasting in tracing mode.
```

---

### Task 5.5: Run Tests and Fix Any Issues

**Goal:** Verify all tests pass and fix any issues discovered

**Implementation Steps:**

1. Run the new test file:

```bash
cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python
uv run pytest tests/accessors/test_list_broadcasting_debug_mode.py -v
```

2. If tests fail, analyze failures:
   - Check if operations are being captured in computation graph
   - Verify eager execution produces correct results
   - Check metadata is properly attached
   - Ensure dependencies are extracted correctly

3. Common issues and fixes:

   **Issue A:** Dependencies not extracted correctly from conditional expressions

   **Fix:** Update `gaspatchio_core/frame/graph/__init__.py` `extract_dependencies()` to handle conditional metadata structures.

   **Issue B:** Type inference fails for list-wrapped conditional results

   **Fix:** Update `_infer_expression_type()` in `tracing.py` to handle list wrapping explicitly.

   **Issue C:** Source metadata captures internal frame code instead of user code

   **Fix:** Adjust depth range or internal file filters in the metadata capture loop.

4. Run full test suite to ensure no regressions:

```bash
uv run pytest tests/ -v -k "projection or conditional or list_broadcast"
```

**Verification:**
- All 4 new tests pass
- No regressions in existing tests
- Computation graph properly captures operations

**Commit Message:**
```
fix(task-5.5): resolve issues in list broadcasting debug mode

Fix [describe specific issues found and resolved]:
- [Issue 1 description and fix]
- [Issue 2 description and fix]

All tests now pass. List broadcasting works in both debug and optimize modes.

Task 5.5 of enabling list broadcasting in tracing mode.
```

---

### Task 5.6: Integration Test with Real Actuarial Model

**Goal:** Verify the feature works with the user's actual model in debug mode

**Implementation Steps:**

1. Test with the user's model that originally failed:

```bash
cd ~/projects/gaspatchio-models/basic_term
uv run mix.py run-model-code model_projection.py ../data/model_points.parquet --mode debug
```

2. Verify:
   - Model runs without NotImplementedError
   - Conditional operations (`pols_maturity`, `pols_if`) execute correctly
   - Results match optimize mode output
   - Computation graph shows traced operations

3. Compare debug vs optimize mode outputs:

```bash
# Run in optimize mode
uv run mix.py run-model-code model_projection.py ../data/model_points.parquet --mode optimize > optimize_output.txt

# Run in debug mode
uv run mix.py run-model-code model_projection.py ../data/model_points.parquet --mode debug > debug_output.txt

# Compare outputs (should be identical except for tracing logs)
diff optimize_output.txt debug_output.txt
```

4. If issues are found:
   - Add test case to `test_list_broadcasting_debug_mode.py` that reproduces the issue
   - Fix the issue
   - Re-run tests

**Verification:**
- User's model runs successfully in debug mode
- Output matches optimize mode
- No performance degradation (debug mode expected to be slower, but not excessively)
- Tracing output shows useful debugging information

**Commit Message:**
```
test(task-5.6): verify list broadcasting works with real actuarial model

Tested with basic_term model using debug mode. Confirmed:
- pols_maturity conditional executes correctly
- pols_if zeroing pattern works
- Results match optimize mode output
- Computation graph captures operations properly

Task 5.6 of enabling list broadcasting in tracing mode.
```

---

### Task 5.7: Update Documentation and Type Stubs

**Goal:** Document the feature and update any relevant docstrings

**Files to Modify:**
- `gaspatchio_core/frame/base.py` (docstrings)
- `gaspatchio_core/functions/conditional.py` (docstring)
- `docs/plans/2025-11-10-period-time-shifting-api.md` (update Task 5 status)
- `ref/18-when-then/task-4-list-broadcasting-plan.md` (mark Task 5 complete)

**Implementation Steps:**

1. Update `_apply_conditional_list_broadcasting` docstring in `base.py`:

```python
def _apply_conditional_list_broadcasting(
    self, key: str, metadata: dict[str, Any]
) -> None:
    """Apply list broadcasting for conditional expressions.

    This method handles when-then-otherwise conditionals that involve list columns.
    It uses the explode/re-aggregate pattern to apply element-wise conditionals.

    Behavior by mode:
    - **Debug mode**: Executes the pattern eagerly and captures a TracedOperation
      in the computation graph for debugging and visualization. The operation
      includes metadata about the list columns, conditional expression, and
      source location.
    - **Optimize mode**: Executes the pattern directly without tracing overhead.

    Args:
        key: Name of the column to create
        metadata: Dictionary with:
            - list_columns (set[str]): List columns to explode
            - conditional_expr (pl.Expr): Conditional expression to apply

    Example:
        >>> af = ActuarialFrame({"month": [[0, 1, 2]], "amt": [[100, 200, 300]]})
        >>> af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amt)
        >>> # In debug mode: captures operation + executes
        >>> # In optimize mode: just executes
    """
```

2. Update `when()` function docstring in `conditional.py` to mention debug mode support:

```python
def when(condition: Any) -> ConditionalProxy:
    """Create a conditional expression (if-then-else logic).

    This function enables familiar if-then-else logic for ActuarialFrame columns.
    It automatically handles list broadcasting for projection columns, applying
    conditionals element-wise across time periods.

    **Supported in both debug and optimize modes** - conditionals with list columns
    work seamlessly in either execution mode.

    Args:
        condition: Boolean expression (typically column comparison)

    Returns:
        ConditionalProxy: Chainable proxy for building the full conditional

    Example:
        >>> af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)
        >>> # Works in both af.debug() and af.optimize() modes

    See Also:
        - :class:`ConditionalProxy` - The proxy object for chaining .then() and .otherwise()
        - List broadcasting documentation for performance details
    """
```

3. Update task status in `ref/18-when-then/task-4-list-broadcasting-plan.md` (lines 491-500):

```markdown
### Task 5: Computation Graph Integration ✅ COMPLETED

**Goal:** Make list broadcasting work with tracing/debug mode

**Implementation:** Eager execution with tracing
- Executes explode/re-aggregate pattern immediately in debug mode
- Captures TracedOperation with list broadcasting metadata
- Shows operation in computation graph for debugging
- No changes needed to optimize mode (already working)

**Completed:** 2025-11-11
**Duration:** 8 hours
```

4. Add entry to `docs/plans/2025-11-10-period-time-shifting-api.md` changelog:

```markdown
## Related Work

### Task 5: List Broadcasting in Debug Mode (Completed 2025-11-11)

After implementing the time-shifting API, we completed Task 5 to enable list broadcasting
conditionals in debug/tracing mode. Previously, when-then-otherwise expressions with list
columns would fail with NotImplementedError in debug mode.

The solution uses eager execution: the explode/re-aggregate pattern executes immediately
in debug mode and captures a TracedOperation for the computation graph. This enables
step-by-step debugging of actuarial models with projection periods.

See: `docs/plans/2025-11-11-task5-list-broadcasting-tracing.md`
```

**Verification:**
- Docstrings render correctly
- Examples in docstrings are accurate
- Plan documents updated with completion status

**Commit Message:**
```
docs(task-5.7): update documentation for list broadcasting in debug mode

Update docstrings and documentation to reflect that list broadcasting
conditionals now work in both debug and optimize modes.

Changes:
- Updated _apply_conditional_list_broadcasting docstring
- Updated when() function docstring
- Marked Task 5 as complete in plan documents
- Added changelog entry to time-shifting API plan

Task 5.7 of enabling list broadcasting in tracing mode.
```

---

### Task 5.8: Performance Validation

**Goal:** Ensure debug mode performance is acceptable and document overhead

**Implementation Steps:**

1. Create a simple benchmark script `tests/performance/bench_list_broadcasting_modes.py`:

```python
# ABOUTME: Benchmark list broadcasting performance in debug vs optimize mode
# ABOUTME: Measures overhead of tracing in debug mode for list broadcasting operations

"""Performance comparison of list broadcasting in debug vs optimize modes."""

import time
import polars as pl
from gaspatchio_core import ActuarialFrame, when


def benchmark_mode(mode: str, num_policies: int = 1000, num_periods: int = 120) -> float:
    """Benchmark list broadcasting in a specific mode.

    Args:
        mode: "debug" or "optimize"
        num_policies: Number of policies to simulate
        num_periods: Number of time periods per policy

    Returns:
        Execution time in seconds
    """
    # Create test data
    data = {
        "policy_id": list(range(num_policies)),
        "month": [[i for i in range(num_periods)] for _ in range(num_policies)],
        "amount": [[100.0 + i for i in range(num_periods)] for _ in range(num_policies)],
        "term_months": [120] * num_policies
    }

    af = ActuarialFrame(data)

    # Set mode
    if mode == "debug":
        af = af.debug()
    else:
        af = af.optimize()

    start = time.time()

    # Apply multiple conditionals (typical actuarial pattern)
    af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amount)
    af.maturity = when(af.month == af.term_months).then(af.adjusted).otherwise(0.0)
    af.active = when(af.month < af.term_months).then(af.adjusted).otherwise(0.0)

    # Collect to force execution
    _ = af.collect()

    elapsed = time.time() - start
    return elapsed


def main():
    """Run benchmarks and report results."""
    print("List Broadcasting Performance Benchmark")
    print("=" * 60)

    configs = [
        (100, 120),    # Small: 100 policies, 10 years
        (1000, 120),   # Medium: 1000 policies, 10 years
        (10000, 60),   # Large: 10000 policies, 5 years
    ]

    for num_policies, num_periods in configs:
        print(f"\nConfiguration: {num_policies} policies x {num_periods} periods")
        print("-" * 60)

        # Run optimize mode
        opt_time = benchmark_mode("optimize", num_policies, num_periods)
        print(f"Optimize mode: {opt_time:.3f}s")

        # Run debug mode
        debug_time = benchmark_mode("debug", num_policies, num_periods)
        print(f"Debug mode:    {debug_time:.3f}s")

        # Calculate overhead
        overhead_pct = ((debug_time - opt_time) / opt_time) * 100
        print(f"Overhead:      {overhead_pct:.1f}%")

        # Acceptable if overhead < 50%
        if overhead_pct < 50:
            print("✓ Acceptable overhead")
        else:
            print("⚠ High overhead - consider optimization")


if __name__ == "__main__":
    main()
```

2. Run the benchmark:

```bash
cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python
uv run python tests/performance/bench_list_broadcasting_modes.py
```

3. Acceptable performance criteria:
   - Debug mode overhead should be < 50% vs optimize mode
   - Both modes should scale linearly with policies × periods
   - No memory leaks or excessive allocations

4. If performance is unacceptable:
   - Profile with `py-spy` to find bottlenecks
   - Consider lazy tracing (append to graph without immediate metadata capture)
   - Consider batch tracing (collect operations, trace at end)

**Verification:**
- Debug mode overhead is reasonable (< 50%)
- No performance regressions in optimize mode
- Both modes scale acceptably

**Commit Message:**
```
perf(task-5.8): validate list broadcasting performance in debug mode

Add benchmark comparing debug vs optimize mode performance.
Results: [insert actual numbers]

Debug mode overhead: [X]% (acceptable < 50%)
Both modes scale linearly with data size.

Task 5.8 of enabling list broadcasting in tracing mode.
```

---

## Summary

This plan implements eager execution with tracing for list broadcasting in debug mode:

1. **Task 5.1**: Add metadata model for list broadcasting operations
2. **Task 5.2**: Create helper to generate TracedOperations
3. **Task 5.3**: Write comprehensive failing tests
4. **Task 5.4**: Implement eager execution path (core feature)
5. **Task 5.5**: Fix issues and verify tests pass
6. **Task 5.6**: Integration test with real model
7. **Task 5.7**: Update documentation
8. **Task 5.8**: Validate performance

**Key Design Principles:**
- Eager execution in debug mode (execute immediately + trace)
- Minimal changes to optimize mode (already working)
- Single TracedOperation per list broadcast (not one per pattern step)
- Comprehensive metadata for debugging and visualization

**Estimated Duration:** 8 hours total
- Tasks 5.1-5.3: 2 hours (setup and tests)
- Task 5.4: 2 hours (core implementation)
- Tasks 5.5-5.6: 2 hours (testing and debugging)
- Tasks 5.7-5.8: 2 hours (docs and performance)

**Success Criteria:**
- All tests pass in debug and optimize modes
- User's basic_term model runs in debug mode without errors
- Computation graph captures list broadcasting operations
- Debug mode overhead < 50% vs optimize mode
- Documentation updated and complete
