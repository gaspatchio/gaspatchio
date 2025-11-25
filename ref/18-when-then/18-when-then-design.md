# When/Then/Otherwise Conditional Expression Design

**Date:** 2025-01-10
**Status:** Design Complete - Ready for Implementation
**Authors:** Claude (Brainstorming), Mr Gaz Wright (Decisions)

## Executive Summary

Add `when().then().otherwise()` conditional expressions to Gaspatchio that:
- Match Excel's IF() mental model with method chaining
- Automatically handle list vs scalar broadcasting (solving the 6-8x performance issue)
- Integrate seamlessly with computation graph and tracing
- Follow the "code IS the formula" philosophy

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Syntax keywords** | `when/then/otherwise` | Avoids Python `if` confusion, matches Polars/SQL |
| **Import style** | Module-level `when()` | Cleaner, matches Polars pattern |
| **List broadcasting** | Automatic detection | Consistent with existing arithmetic shimming |
| **Return types** | `ConditionalProxy` → `ExpressionProxy` | Type-safe, matches existing proxy pattern |
| **Multiple conditions** | Chain `.when()` (no `.elif_()`) | Simple, matches Polars exactly |
| **Missing .otherwise()** | **Required** - raise error | Match Excel philosophy, force explicit edge cases |
| **Scalar-to-list conversion** | `repeat_by(list.len())` | Polars-recommended, proven performance |
| **Validation** | Smart - catch common issues | Balance safety with simplicity |

## API Overview

### Basic Usage

```python
from gaspatchio_core import when

# Simple conditional
af["rate"] = when(af["age"] > 65).then(0.05).otherwise(0.02)

# Multiple conditions
af["category"] = (
    when(af["age"] < 18).then("child")
    .when(af["age"] < 65).then("adult")
    .otherwise("senior")
)

# Automatic list broadcasting (THE KEY FEATURE)
af["pols_maturity"] = (
    when(af["month"] == af["policy_term"] * 12)  # month=list, policy_term=scalar
    .then(af["surviving_at_t"])                   # list
    .otherwise(0.0)                               # scalar
)
```

### Design Philosophy

Aligns with Gaspatchio's "code IS the formula" principle:
- ✅ Reads like Excel's `IF()` but with method chaining
- ✅ Formula is visible and auditable
- ✅ No hidden magic - broadcasting is automatic but predictable
- ✅ Works seamlessly with computation graph
- ✅ Requires explicit `.otherwise()` - no silent nulls

## Architecture

### Core Classes

**ConditionalProxy** (new class in `gaspatchio_core/functions/conditional.py`)

```python
class ConditionalProxy:
    """Represents an in-progress conditional expression chain."""

    def __init__(self, condition_expr: pl.Expr, parent: ActuarialFrame):
        self._conditions: list[pl.Expr] = [condition_expr]
        self._values: list[pl.Expr] = []
        self._parent = parent
        self._finalized = False

    def then(self, value) -> ConditionalProxy:
        """Add value for current condition. Returns self for chaining."""
        pass

    def when(self, condition) -> ConditionalProxy:
        """Add another condition (elif behavior)."""
        pass

    def otherwise(self, value) -> ExpressionProxy:
        """Complete the chain and return final expression.

        This is where list broadcasting detection and implementation happens.
        """
        pass
```

**Module-level entry point:**

```python
def when(condition) -> ConditionalProxy:
    """Start a conditional expression chain.

    Automatically handles list vs scalar broadcasting for actuarial projections.
    """
    pass
```

### List Broadcasting Implementation

**Detection Strategy (at `.otherwise()` call):**

1. Inspect all expressions (conditions, then values, otherwise value) for list columns
2. If any list columns detected:
   - Use `then()` value as driver (preferred list column)
   - Broadcast scalar columns using `repeat_by(list.len())`
   - Build `list.eval(when(...).then(...).otherwise(...))` expression
3. Otherwise, build simple scalar `when/then/otherwise`

**Broadcasting Mechanism:**

```python
# For scalar columns that need to match list length:
scalar_expr.repeat_by(list_col.list.len())

# Converts:
# [120, 240] (scalars)
# → [[120,120,...120], [240,240,...240]] (lists)
```

**Schema Lookup:**

```python
# Leverage existing ColumnTypeDetector pattern
from gaspatchio_core.column.dispatch import ColumnTypeDetector

detector = ColumnTypeDetector(parent_frame)
is_list = detector.is_list_column(column_name)
```

**Performance:** Schema lookup is cheap (metadata only), already used throughout codebase.

### Integration with Computation Graph

**No special handling needed** (confirmed by investigation):

1. `ConditionalProxy.otherwise()` returns `ExpressionProxy`
2. `ExpressionProxy._expr` contains the `pl.when().then().otherwise()` expression
3. `_convert_to_expr()` unwraps to `pl.Expr`
4. `extract_dependencies()` handles conditional expressions via `meta.root_names()`
5. Works seamlessly with existing tracing infrastructure

**Dependency Extraction:** Polars' `meta.root_names()` automatically extracts all column references from all branches of conditionals.

## Error Handling and Validation

### Validation Points

**1. Incomplete chain** (critical - requires `.otherwise()`)
```python
# This should raise error:
af["rate"] = when(af["age"] > 65).then(0.05)
# Error: "Conditional expression requires .otherwise(). Use .otherwise(value) to complete the chain."
```

**2. Mismatched list lengths**
```python
# Check all list columns have same length
if len(set(list_lengths)) > 1:
    raise ValueError("List columns have mismatched lengths: ...")
```

**3. Missing columns**
```python
# Clear error if column doesn't exist
# (handled by existing ColumnProxy/ExpressionProxy validation)
```

**4. Let Polars handle:**
- Type compatibility (can't compare str to int)
- Complex expression errors
- Execution errors

### Implementation Strategy

Use try/except with clear error messages for common cases, re-raise Polars errors with added context.

## Module Structure

**New file:** `gaspatchio_core/functions/conditional.py`

```python
"""Conditional expressions (when/then/otherwise) for ActuarialFrame.

Provides Excel-style IF() functionality with automatic list broadcasting
for actuarial projections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame

class ConditionalProxy:
    """In-progress conditional expression chain."""
    pass

def when(condition) -> ConditionalProxy:
    """Start a conditional expression chain."""
    pass
```

**Export from main package** (`gaspatchio_core/__init__.py`):

```python
from gaspatchio_core.functions.conditional import when

__all__ = [
    "ActuarialFrame",
    "when",  # Add to exports
    # ... other exports
]
```

## Testing Strategy

### 1. Unit Tests (`tests/functions/test_conditional.py`)

Following patterns from `tests/accessors/test_projection.py`:

```python
class TestWhenBasics:
    """Tests for basic when/then/otherwise functionality."""

    def test_simple_scalar_conditional(self):
        """Test basic scalar conditional."""

    def test_requires_otherwise(self):
        """Test that missing .otherwise() raises error."""

    def test_type_conversions(self):
        """Test with literals, columns, expressions."""

class TestWhenMultipleConditions:
    """Tests for chained when conditions (elif behavior)."""

    def test_chained_when(self):
        """Test multiple when conditions."""

    def test_first_match_wins(self):
        """Test that first matching condition is used."""

class TestWhenListBroadcasting:
    """Tests for automatic list vs scalar broadcasting."""

    def test_list_condition_scalar_value(self):
        """Test list column in condition with scalar comparison."""

    def test_scalar_condition_list_result(self):
        """Test scalar condition with list result."""

    def test_mixed_list_and_scalar(self):
        """Test mix of list and scalar in all branches."""

    def test_repeat_by_used_correctly(self):
        """Verify repeat_by is used for broadcasting."""

class TestWhenErrorHandling:
    """Tests for validation and error messages."""

    def test_missing_otherwise_error(self):
        """Test clear error when .otherwise() not called."""

    def test_mismatched_list_lengths(self):
        """Test error for mismatched list column lengths."""

class TestWhenComputationGraph:
    """Tests for integration with tracing/graph."""

    def test_graph_capture(self):
        """Test conditionals captured in computation graph."""

    def test_dependency_extraction(self):
        """Test dependencies extracted from all branches."""

    def test_debug_and_optimize_modes(self):
        """Test works in both execution modes."""
```

### 2. Method Docstrings

Following `ref/recipes/write-docstring.md`:

**Focus on `when()` entry point:**
- "When to use" admonition with actuarial use cases:
  - Risk classification based on age/health
  - Premium adjustments and loading
  - Benefit determination logic
  - Maturity and policy event calculations
- Scalar example: age-based rate selection
- Vector example: maturity calculation (from 18-conditional-broadcast.md)
- Run examples to get EXACT output formatting

**Brief docstrings for methods:**
- `ConditionalProxy.then()` - references when()
- `ConditionalProxy.when()` - references chaining
- `ConditionalProxy.otherwise()` - emphasizes requirement

### 3. Scratch Tests (`tests/scratch/conditional.py`)

End-to-end actuarial scenarios from `18-conditional-broadcast.md`:

```python
# Scenario 1: Maturity calculation
af["pols_maturity"] = (
    when(af["month"] == (af["policy_term"] * 12))
    .then(af["surviving_at_t"])
    .otherwise(0.0)
)

# Scenario 2: Zeroing after maturity
af["pols_if"] = (
    when(af["month"] < (af["policy_term"] * 12))
    .then(af["pols_if_before_maturity"])
    .otherwise(0.0)
)

# Scenario 3: Commission schedules
af["commissions"] = (
    when(af["duration"] == 0)
    .then(af["premiums"])
    .otherwise(0.0)
)

# Scenario 4: Premium holidays
af["premium_adj"] = (
    when(af["month"] == 5)
    .then(0.0)
    .otherwise(af["premium"])
)
```

## Performance Considerations

### Expected Performance Gains

**Before (using `map_elements`):**
- 10 model points: ~177ms
- Performance penalty: 4-5x slower than native Polars

**After (using `when` with automatic broadcasting):**
- Expected: ~30-40ms (6-8x improvement)
- Performance: Match native Polars vectorized operations

### Why This is Fast

1. **No Python UDFs** - everything is native Polars expressions
2. **Query optimizer** - Polars can optimize the expression tree
3. **Vectorized execution** - SIMD and parallelization
4. **Lazy evaluation** - expressions built once, executed once at collect()

### Benchmarking

Include performance tests comparing:
- Old approach: `map_elements` with Python UDF
- New approach: `when()` with automatic broadcasting
- Target: 5-10x improvement for conditional operations

## Implementation Checklist

- [ ] Create `gaspatchio_core/functions/conditional.py`
  - [ ] `ConditionalProxy` class
  - [ ] `when()` function
  - [ ] List broadcasting detection logic
  - [ ] Error handling and validation
- [ ] Export from `gaspatchio_core/__init__.py`
- [ ] Unit tests in `tests/functions/test_conditional.py`
  - [ ] All test classes as outlined
  - [ ] Coverage for scalar, list, mixed cases
  - [ ] Error handling tests
  - [ ] Computation graph integration tests
- [ ] Docstrings following `write-docstring.md`
  - [ ] Rich `when()` docstring with actuarial examples
  - [ ] Run examples to get exact output
  - [ ] Brief docstrings for proxy methods
- [ ] Scratch tests in `tests/scratch/conditional.py`
  - [ ] All 4 actuarial scenarios from 18-conditional-broadcast.md
- [ ] Performance benchmarks
  - [ ] Compare map_elements vs when() performance
  - [ ] Document improvement metrics

## Success Criteria

1. ✅ API feels natural and Excel-like
2. ✅ Automatic list broadcasting eliminates performance issues
3. ✅ Clear error messages guide actuaries
4. ✅ Seamless computation graph integration
5. ✅ 5-10x performance improvement over `map_elements` approach
6. ✅ Comprehensive test coverage
7. ✅ Rich actuarial domain documentation

## References

- **18-conditional-broadcast.md** - Performance problem and use cases
- **18-when-then-plan.md** - Original proposal (updated by this design)
- **22-brainstorm.md** - "Code IS the formula" philosophy
- **Polars scalar-to-list research** - `repeat_by()` performance validation
- **Computation graph investigation** - Confirmed seamless integration

## Next Steps

Ready to proceed with implementation using:
- `superpowers:writing-plans` - Create detailed implementation plan
- `superpowers:using-git-worktrees` - Set up isolated workspace

Or proceed directly to implementation if preferred.
