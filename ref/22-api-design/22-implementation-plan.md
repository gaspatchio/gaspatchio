# Projection API Implementation Plan
**Date:** 2025-11-10
**Status:** Architecture Analysis Complete - Ready for Implementation
**Related:** `22-brainstorm.md`, `22-intro.md`

## Executive Summary

This document provides a comprehensive implementation plan for the projection API design described in `22-brainstorm.md`. After analyzing the current codebase, we've determined that **the infrastructure is complete and ready** - we only need to create new accessor classes following the existing patterns.

**Key Finding:** The proxy system, delegation mechanism, list column shimming, and accessor registry are all fully implemented and tested. The path forward is straightforward: create `ProjectionColumnAccessor`, `MortalityColumnAccessor`, and `AssumptionsColumnAccessor` classes following the patterns established in the existing `DateColumnAccessor`, `FinanceColumnAccessor`, and `ExcelColumnAccessor`.

---

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [What Currently Exists](#what-currently-exists)
3. [What's Proposed (from 22-brainstorm.md)](#whats-proposed-from-22-brainstormmd)
4. [Gap Analysis](#gap-analysis)
5. [Implementation Roadmap](#implementation-roadmap)
6. [Code Examples and Patterns](#code-examples-and-patterns)
7. [Testing Strategy](#testing-strategy)

---

## Current Architecture

### Overview: The Proxy Pattern System

Gaspatchio uses a sophisticated two-tier proxy pattern that wraps Polars expressions while adding actuarial-specific functionality:

```
ActuarialFrame
    └─> ColumnProxy (represents a column reference: af["mortality_rate"])
            └─> ExpressionProxy (represents computed expressions: af.rate * af.adjustment)
                    └─> Polars Expr (the actual computation graph)
```

### Core Components

#### 1. ColumnProxy (`gaspatchio_core/column/column_proxy.py`)

**Purpose:** Represents a column identifier within an ActuarialFrame

**Key Characteristics:**
- Acts as the starting point for column-based expressions
- Wraps a column name and parent frame reference
- Provides accessor properties (`.date`, `.finance`, `.excel`)
- Converts to Polars expressions via `_to_expr()` → `pl.col(name)`

**Example Usage:**
```python
# When you write:
af["mortality_rate"]

# You get a ColumnProxy instance with:
# - name = "mortality_rate"
# - _parent = <ActuarialFrame instance>
# - Access to .date, .finance, .excel accessors
```

**Implementation Pattern:**
```python
class ColumnProxy:
    def __init__(self, name: str, parent: "ActuarialFrame"):
        self.name = name
        self._parent = parent
        self._dynamic_accessor_cache: dict[str, Any] = {}

    def _to_expr(self) -> pl.Expr:
        return pl.col(self.name)

    @property
    def date(self) -> "DateColumnAccessor":
        if self._date_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("column")
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance
```

#### 2. ExpressionProxy (`gaspatchio_core/column/expression_proxy.py`)

**Purpose:** Represents computed Polars expressions with enhanced functionality

**Key Characteristics:**
- Wraps a `pl.Expr` object
- Provides the same accessor interface as ColumnProxy
- Handles operator overloading (arithmetic, comparison)
- Supports method chaining

**Example Usage:**
```python
# When you write:
af.death_benefit = af.face_amount * af.qx * af.survival_to_t

# The computation creates ExpressionProxy objects:
# af.face_amount → ColumnProxy → _to_expr() → pl.col("face_amount")
# af.qx → ColumnProxy → _to_expr() → pl.col("qx")
# * operator creates ExpressionProxy wrapping the multiplication expression
```

#### 3. DelegatorDescriptor (`gaspatchio_core/column/dispatch.py`)

**Purpose:** Core delegation mechanism enabling transparent Polars method access

**How It Works:**
```python
class DelegatorDescriptor:
    def __init__(self, name: str):
        self.name = name
        self.wrapper_logic = _make_wrapper(self.name)

    def __get__(self, instance, owner=None):
        if instance is None:
            return self.wrapper_logic

        # Handle specialized namespaces (dt, str)
        if self.name in SPECIALIZED_NAMESPACES:
            parent_af = getattr(instance, "_parent", None)
            return SPECIALIZED_NAMESPACES[self.name](instance, parent_af)

        # For all other attributes, use wrapper logic
        return self.wrapper_logic(instance)
```

**Key Innovation:** The descriptor intercepts attribute access and delegates to Polars while adding:
- List column shimming (automatic element-wise operations)
- Error enhancement with context information
- Wrapping results back into proxy objects

#### 4. List Column Shimming (`gaspatchio_core/column/dispatch.py`)

**Purpose:** Automatically handle element-wise operations on columns containing lists/vectors

**The Problem:**
```python
# Column structure: "projected_cashflows" contains lists
# [
#   [100.2, -50.5, 75.8],    # First policy's cashflows
#   [-25.3, 60.4, -10.9],    # Second policy's cashflows
# ]

# Without shimming: abs() would fail (can't take abs of a list)
# With shimming: abs() applies to each element
af["projected_cashflows"].abs()
# Result:
# [
#   [100.2, 50.5, 75.8],     # Absolute values element-wise
#   [25.3, 60.4, 10.9],
# ]
```

**Implementation:**
```python
def _should_use_list_shim(name, self_proxy, parent_af, base_expr) -> bool:
    """Determine if list shimming should be used."""
    # Only for numeric operations
    if name not in _NUMERIC_UNARY and name not in _NUMERIC_ELEMENTWISE:
        return False

    detector = ColumnTypeDetector(parent_af)

    # For ColumnProxy: check schema directly
    if isinstance(self_proxy, ColumnProxy):
        return detector.is_list_column(self_proxy.name)

    # For ExpressionProxy: use heuristics (check expression string)
    if isinstance(self_proxy, ExpressionProxy):
        expr_str = str(base_expr)
        list_columns = detector.get_all_list_columns()
        return _expr_references_list_column(expr_str, list_columns)

    return False

def _execute_list_shim(name, base_expr, args, kwargs, is_unary):
    """Execute using list.eval for element-wise operations."""
    element_method = getattr(pl.element(), name)

    if is_unary:
        return base_expr.list.eval(element_method())

    # For operations with arguments
    unwrapped_args = [_unwrap_for_list_eval(arg) for arg in args]
    unwrapped_kwargs = {k: _unwrap_for_list_eval(v) for k, v in kwargs.items()}
    return base_expr.list.eval(element_method(*unwrapped_args, **unwrapped_kwargs))
```

**Supported Operations:**
- **Unary:** `abs`, `sign`, `floor`, `ceil`, `round`, `exp`, `log`, `sqrt`, `is_nan`, etc.
- **Binary:** `add`, `sub`, `mul`, `truediv`, `pow`, `clip`, `cast`, `cum_prod`, etc.

#### 5. Accessor Registry (`gaspatchio_core/frame/registry.py`)

**Purpose:** Centralized registry for frame and column accessors

**How It Works:**
```python
_ACCESSOR_REGISTRY: Dict[str, Dict[str, AccessorClass]] = {}

@register_accessor("date", kind="column")
class DateColumnAccessor(BaseColumnAccessor):
    def to_period(self, freq: str = "M") -> ExpressionProxy:
        expr = self._proxy._to_expr()
        period_expr = expr.dt.truncate(polars_freq).cast(pl.Date)
        return ExpressionProxy(period_expr, self._proxy._parent)
```

**Registry Structure:**
```python
{
    "date": {
        "frame": DateFrameAccessor,
        "column": DateColumnAccessor
    },
    "finance": {
        "frame": FinanceFrameAccessor,
        "column": FinanceColumnAccessor
    },
    "excel": {
        "column": ExcelColumnAccessor
    }
}
```

**Access Pattern:**
```python
# Frame-level access:
af.date.create_timeline(...)  # Uses DateFrameAccessor

# Column-level access:
af["event_date"].date.to_period("M")  # Uses DateColumnAccessor
```

#### 6. Autopatching (`gaspatchio_core/column/dispatch.py`)

**Purpose:** Dynamically add Polars expression methods to proxy classes

**How It Works:**
```python
def _autopatch(proxy_cls: Type["ProxyType"]) -> None:
    """Add Polars methods to proxy classes."""
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)

    for attr_name in set(attrs_to_process):
        # Skip internal attributes and existing methods
        if attr_name.startswith("_") or hasattr(proxy_cls, attr_name):
            continue

        # Add descriptor for dynamic delegation
        setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
```

**Result:** Proxy classes can call any Polars method transparently:
```python
# All of these work through autopatching:
af["age"].sum()
af["premium"].mean()
af["date"].dt.year()
af["values"].cum_prod()
```

---

## What Currently Exists

### 1. Complete Proxy Infrastructure

✅ **ColumnProxy** - Fully implemented with:
- Operator overloading (`__add__`, `__mul__`, etc.)
- Accessor properties (`.date`, `.finance`, `.excel`)
- Dynamic accessor lookup via `__getattr__`
- Conversion to Polars expressions via `_to_expr()`

✅ **ExpressionProxy** - Fully implemented with:
- Same interface as ColumnProxy (can be used interchangeably)
- Wraps computed Polars expressions
- Supports chaining and composition

✅ **DelegatorDescriptor** - Core delegation system working:
- Transparent forwarding to Polars methods
- Namespace handling (`.dt`, `.str`, `.list`, etc.)
- Error enhancement with source context

✅ **List Column Shimming** - Production-ready:
- Automatic detection of list columns
- Element-wise operation translation
- Fallback to regular execution if shimming fails

### 2. Accessor Registry and Base Classes

✅ **Registry System** (`gaspatchio_core/frame/registry.py`):
```python
@register_accessor("projection", kind="column")
class ProjectionColumnAccessor(BaseColumnAccessor):
    # Your implementation here
    pass
```

✅ **Base Classes** (`gaspatchio_core/accessors/base.py`):
- `BaseFrameAccessor` - For frame-level operations
- `BaseColumnAccessor` - For column-level operations

### 3. Existing Accessor Implementations

#### DateColumnAccessor (`gaspatchio_core/accessors/date.py`)

**Pattern to Follow:**
```python
@register_accessor("date", kind="column")
class DateColumnAccessor(BaseColumnAccessor):
    def to_period(self, freq: str = "M") -> ExpressionProxy:
        """Convert date to period representation."""
        expr = self._proxy._to_expr()
        period_expr = expr.dt.truncate(polars_freq).cast(pl.Date)
        return ExpressionProxy(period_expr, self._proxy._parent)
```

**Key Lessons:**
1. Access underlying expression via `self._proxy._to_expr()`
2. Get parent frame via `self._proxy._parent`
3. Return `ExpressionProxy` wrapping result
4. Use Polars expressions directly

#### FinanceColumnAccessor (`gaspatchio_core/accessors/finance.py`)

**Pattern for Methods with Parameters:**
```python
@register_accessor("finance", kind="column")
class FinanceColumnAccessor(BaseColumnAccessor):
    def discount(self, rate_expr, n_periods_expr) -> ExpressionProxy:
        """Discount value using rate and periods."""
        base_expr = self._proxy._to_expr()
        parent_frame = self._proxy._parent

        # Convert arguments using parent frame's context
        pl_rate_expr = parent_frame._convert_to_expr(rate_expr)
        pl_n_periods_expr = parent_frame._convert_to_expr(n_periods_expr)

        # Calculate discount factor
        discount_factor = (1 + pl_rate_expr).pow(pl_n_periods_expr)

        # Apply discount
        discounted_expr = pl.when(discount_factor != 0).then(
            base_expr / discount_factor
        ).otherwise(pl.lit(None))

        return ExpressionProxy(discounted_expr, parent_frame)
```

**Key Lessons:**
1. Methods can accept column references, expressions, or literals
2. Use `parent_frame._convert_to_expr()` to handle all input types
3. Build Polars expressions using standard Polars API
4. Handle edge cases (division by zero, nulls, etc.)

#### ExcelColumnAccessor (`gaspatchio_core/accessors/excel.py`)

**Pattern for Excel-Like Functions:**
```python
@register_accessor("excel", kind="column")
class ExcelColumnAccessor(BaseColumnAccessor):
    def vlookup(self, lookup_table, lookup_col, return_col):
        """Excel VLOOKUP equivalent."""
        # Implementation using Polars joins
        pass
```

### 4. Testing Infrastructure

✅ **Docstring Testing** - Examples in docstrings validated by pytest:
```python
def cumulative_survival(self) -> ExpressionProxy:
    """Calculate cumulative survival.

    Examples:
        ```python
        import polars as pl
        from gaspatchio_core import ActuarialFrame

        data = {"qx": [[0.001, 0.0011, 0.0012]]}
        af = ActuarialFrame(data)
        af.survival = af.qx.projection.cumulative_survival()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌─────────────────────────┬─────────────────────────┐
        │ qx                      ┆ survival                │
        │ ---                     ┆ ---                     │
        │ list[f64]               ┆ list[f64]               │
        ╞═════════════════════════╪═════════════════════════╡
        │ [0.001, 0.0011, 0.0012] ┆ [0.999, 0.9979, 0.9967] │
        └─────────────────────────┴─────────────────────────┘
        ```
    """
    # Implementation
```

✅ **Test Patterns** - Existing tests show the pattern:
- `tests/accessors/test_dates.py`
- `tests/accessors/test_finance.py`
- `tests/accessors/test_excel.py`

---

## What's Proposed (from 22-brainstorm.md)

### Core Design Philosophy

**"Code IS the Formula"** - The fundamental principle:

| Formula Type | Code Pattern | Example |
|--------------|--------------|---------|
| **Simple math** (multiply, add, subtract) | Use operators directly | `af.death_benefit = af.face_amount * af.qx * af.survival_to_t` |
| **Complex operations** (cumulative product, discounting) | Use named methods | `af.survival_to_t = af.qx.projection.cumulative_survival()` |
| **Lookups** (assumptions, tables) | Use domain accessors | `af.qx = af.issue_age.mortality.qx(table="BaseMortality")` |

### Proposed Accessors

#### 1. `.projection` Accessor

**Purpose:** Methods for actuarial projection operations

**Proposed Methods:**

```python
@register_accessor("projection", kind="column")
class ProjectionColumnAccessor(BaseColumnAccessor):

    def cumulative_survival(self) -> ExpressionProxy:
        """Calculate cumulative survival: (1-q₀)×(1-q₁)×...×(1-qₜ)

        Converts mortality rates to cumulative survival probabilities.
        For list columns, applies element-wise within each list.
        For scalar columns, applies across rows (user should add .over() for grouping).
        """
        pass

    def on_decrement(self, inforce: IntoExprColumn) -> ExpressionProxy:
        """Calculate cashflows that occur when a decrement happens.

        Formula: cashflow × inforce × decrement_rate
        Used for death benefits, surrender benefits, etc.
        """
        pass

    def while_inforce(self, inforce: IntoExprColumn) -> ExpressionProxy:
        """Calculate cashflows while policies are active.

        Formula: cashflow × inforce
        Used for premiums, maintenance expenses, etc.
        """
        pass

    def cumulative_discount(self, rate: IntoExprColumn) -> ExpressionProxy:
        """Calculate cumulative discount factors: 1/(1+r₀) × 1/(1+r₁) × ... × 1/(1+rₜ)

        Converts periodic discount rates to cumulative discount factors.
        """
        pass

    def set_at_period(self, period: int, value: Any) -> ExpressionProxy:
        """Override value at a specific period.

        Used for premium holidays, benefit changes, etc.
        Works with list columns to modify specific elements.
        """
        pass

    def at_maturity(self) -> ExpressionProxy:
        """Extract value at the last period.

        For list columns: returns list.last()
        Used for maturity benefits, terminal values, etc.
        """
        pass
```

**Example Usage (from 22-brainstorm.md):**
```python
# Calculate cumulative survival: (1-q₀)×(1-q₁)×...×(1-qₜ)
af.survival_to_t = af.qx.projection.cumulative_survival()

# Death benefits = Face Amount × qₜ × Survival to t
af.death_benefit = af.face_amount * af.qx * af.survival_to_t

# Premiums while inforce = Annual Premium × Survival to t
af.premium = af.annual_premium * af.survival_to_t

# Maturity benefit = Face Amount × Survival to end
af.maturity_benefit = af.face_amount * af.survival_to_t.list.last()

# Net cashflow
af.net_cashflow = af.premium - af.death_benefit - af.expenses

# Present value
af.pv_cashflow = af.net_cashflow * af.discount_factors
```

#### 2. `.mortality` Accessor

**Purpose:** Mortality table lookups and mortality calculations

**Proposed Methods:**

```python
@register_accessor("mortality", kind="column")
class MortalityColumnAccessor(BaseColumnAccessor):

    def qx(self, table: str = "BaseMortality") -> ExpressionProxy:
        """Lookup mortality rate from table.

        Looks up qx based on the column value (typically age or duration).
        """
        pass

    def tpx(self, t: IntoExprColumn, table: str = "BaseMortality") -> ExpressionProxy:
        """Calculate t-year survival probability.

        Formula: (1-qₓ) × (1-qₓ₊₁) × ... × (1-qₓ₊ₜ₋₁)
        """
        pass

    def lx(self, radix: int = 100000, table: str = "BaseMortality") -> ExpressionProxy:
        """Calculate lives at age x from radix.

        Formula: radix × tpx
        """
        pass
```

**Example Usage:**
```python
# Lookup mortality rates
af.qx = af.issue_age.mortality.qx(table="BaseMortality")

# Calculate t-year survival
af.survival_10y = af.issue_age.mortality.tpx(t=10, table="BaseMortality")

# Lives from radix
af.lx = af.attained_age.mortality.lx(radix=100000)
```

#### 3. `.assumptions` Accessor

**Purpose:** General assumption table lookups

**Proposed Methods:**

```python
@register_accessor("assumptions", kind="column")
class AssumptionsColumnAccessor(BaseColumnAccessor):

    def lookup(self, table: str, **filters) -> ExpressionProxy:
        """Generic assumption table lookup.

        Args:
            table: Name of the assumption table
            **filters: Additional filtering criteria (e.g., product_code="TERM")

        Returns:
            Expression with looked-up values
        """
        pass

    def lookup_series(self, table: str, length: IntoExprColumn, **filters) -> ExpressionProxy:
        """Lookup a series of values (returns list).

        Used for assumption vectors that vary by duration.
        """
        pass
```

**Example Usage:**
```python
# Lookup lapse rates by duration
af.lapse_rate = af.duration.assumptions.lookup(table="LapseRates")

# Lookup expense assumptions
af.per_policy_expense = af.product_code.assumptions.lookup(
    table="Expenses",
    expense_type="per_policy"
)

# Lookup vector of values
af.lapse_rate_vector = af.product_code.assumptions.lookup_series(
    table="LapseRates",
    length=af.policy_term
)
```

---

## Gap Analysis

### What We Have ✅

1. **Infrastructure (100% Complete)**
   - ✅ Proxy pattern (ColumnProxy, ExpressionProxy)
   - ✅ Delegation system (DelegatorDescriptor, _autopatch)
   - ✅ List column shimming
   - ✅ Accessor registry
   - ✅ Base accessor classes

2. **Existing Accessors (Reference Implementations)**
   - ✅ `.date` accessor (frame + column level)
   - ✅ `.finance` accessor (frame + column level)
   - ✅ `.excel` accessor (column level)

3. **Testing Infrastructure**
   - ✅ Docstring testing framework
   - ✅ Test patterns in `tests/accessors/`
   - ✅ Integration with pytest

### What We Need to Build 📝

1. **New Accessor Classes**
   - 📝 `ProjectionColumnAccessor` with methods:
     - `cumulative_survival()`
     - `on_decrement()`
     - `while_inforce()`
     - `cumulative_discount()`
     - `set_at_period()`
     - `at_maturity()`

   - 📝 `MortalityColumnAccessor` with methods:
     - `qx()`
     - `tpx()`
     - `lx()`

   - 📝 `AssumptionsColumnAccessor` with methods:
     - `lookup()`
     - `lookup_series()`

2. **Supporting Infrastructure**
   - 📝 Assumption table storage and access system
   - 📝 Mortality table storage and access system
   - 📝 Helper methods for table lookups

3. **Documentation and Tests**
   - 📝 Comprehensive docstrings with examples
   - 📝 Unit tests for each method
   - 📝 Integration tests showing real-world usage

### Critical Success Factors

**The infrastructure is ready.** We just need to:
1. Follow the existing accessor pattern
2. Implement domain-specific methods
3. Write comprehensive tests
4. Document with executable examples

**Key Insight:** No changes to the core proxy system are needed. The list shimming will automatically work for projection methods operating on list columns.

---

## Implementation Roadmap

### Phase 1: ProjectionColumnAccessor (Priority: HIGH)

**Goal:** Implement the core projection methods needed for basic cashflow modeling

**Tasks:**

1. **Create accessor file** (`gaspatchio_core/accessors/projection.py`)
   ```python
   @register_accessor("projection", kind="column")
   class ProjectionColumnAccessor(BaseColumnAccessor):
       """Actuarial projection operations."""
       pass
   ```

2. **Implement `cumulative_survival()`** (FIRST - this is the working example)
   ```python
   def cumulative_survival(self) -> ExpressionProxy:
       """Calculate cumulative survival: (1-q₀)×(1-q₁)×...×(1-qₜ)"""
       base_expr = self._proxy._to_expr()
       parent_af = getattr(self._proxy, "_parent", None)

       # Check if list column
       detector = ColumnTypeDetector(parent_af)
       is_list = detector.is_list_column(self._proxy.name) if isinstance(self._proxy, ColumnProxy) else False

       if is_list:
           # For list columns: apply cumulative product within each list
           survival_expr = base_expr.list.eval((1 - pl.element()).cum_prod())
       else:
           # For scalar columns: apply cumulative product across rows
           # User should chain with .over() if grouping is needed
           survival_expr = (1 - base_expr).cum_prod()

       return ExpressionProxy(survival_expr, parent_af)
   ```

3. **Implement `on_decrement()`**
   - Follow pattern from `cumulative_survival()`
   - Handle list column shimming
   - Write tests

4. **Implement `while_inforce()`**
   - Similar to `on_decrement()` but simpler (just multiplication)
   - Handle list column shimming
   - Write tests

5. **Implement `cumulative_discount()`**
   - Similar pattern to `cumulative_survival()` but with discount logic
   - Formula: cumulative product of 1/(1+r)
   - Write tests

6. **Implement `at_maturity()`**
   - For list columns: `.list.last()`
   - For scalar columns: consider grouping context
   - Write tests

7. **Implement `set_at_period()`**
   - More complex: requires list manipulation
   - Use `.list.eval()` with conditional logic
   - Write tests

**Acceptance Criteria:**
- All methods implemented
- Docstrings with working examples
- Tests pass
- Works with both list and scalar columns
- Integration test showing complete projection workflow

**Estimated Effort:** 2-3 days

### Phase 2: MortalityColumnAccessor (Priority: MEDIUM)

**Goal:** Implement mortality table lookups and calculations

**Prerequisites:**
- Assumption table system (see Phase 4)

**Tasks:**

1. **Create accessor file** (`gaspatchio_core/accessors/mortality.py`)

2. **Implement `qx()`**
   - Table lookup based on column value
   - Return mortality rate
   - Handle table not found errors

3. **Implement `tpx()`**
   - Multi-period survival calculation
   - May require series of lookups
   - Return cumulative survival probability

4. **Implement `lx()`**
   - Lives from radix calculation
   - Use `tpx()` internally
   - Return life counts

**Acceptance Criteria:**
- All methods implemented
- Docstrings with examples
- Tests with sample mortality tables
- Integration test showing mortality calculations

**Estimated Effort:** 2-3 days (depends on table system)

### Phase 3: AssumptionsColumnAccessor (Priority: MEDIUM)

**Goal:** Generic assumption table lookup system

**Prerequisites:**
- Assumption table system (see Phase 4)

**Tasks:**

1. **Create accessor file** (`gaspatchio_core/accessors/assumptions.py`)

2. **Implement `lookup()`**
   - Generic table lookup with filters
   - Return scalar values
   - Handle missing values

3. **Implement `lookup_series()`**
   - Return list/vector of values
   - Support duration-based series
   - Handle variable lengths

**Acceptance Criteria:**
- Both methods implemented
- Docstrings with examples
- Tests with sample assumption tables
- Integration test showing multiple assumption lookups

**Estimated Effort:** 2-3 days (depends on table system)

### Phase 4: Assumption Table System (Priority: HIGH - Prerequisite)

**Goal:** Storage and access system for assumption and mortality tables

**Tasks:**

1. **Design table storage format**
   - Consider: Parquet files, SQLite, in-memory dicts
   - Support multiple table types
   - Version control for tables

2. **Implement table registry**
   - Load tables from storage
   - Cache loaded tables
   - Handle table updates

3. **Implement lookup logic**
   - Join-based lookups using Polars
   - Handle multi-dimensional lookups
   - Optimize for performance

4. **Create sample tables**
   - Sample mortality table (e.g., 2015 VBT)
   - Sample lapse assumption table
   - Sample expense assumption table

**Acceptance Criteria:**
- Table system designed and implemented
- Sample tables created
- Lookup performance acceptable
- Documentation for adding new tables

**Estimated Effort:** 3-5 days

### Phase 5: Integration and Testing (Priority: HIGH)

**Goal:** End-to-end validation of the projection API

**Tasks:**

1. **Create comprehensive examples**
   - Complete term life insurance projection
   - Complete whole life insurance projection
   - Annuity certain projection

2. **Write integration tests**
   - Test combinations of accessors
   - Test with both list and scalar columns
   - Test with real-world data volumes

3. **Performance testing**
   - Benchmark projection performance
   - Compare to pure Polars implementation
   - Optimize hotspots

4. **Documentation**
   - Update API documentation
   - Create tutorial notebooks
   - Add to gaspatchio-docs

**Acceptance Criteria:**
- All integration tests pass
- Performance meets targets
- Documentation complete
- Examples working

**Estimated Effort:** 3-5 days

### Total Estimated Effort

**Minimum:** 12-18 days (if done sequentially)
**Realistic:** 3-4 weeks (with iteration and refinement)

### Recommended Implementation Order

1. **Week 1:** ProjectionColumnAccessor (Phase 1)
   - Core projection methods
   - Essential for any actuarial work

2. **Week 2:** Assumption Table System (Phase 4)
   - Prerequisite for mortality and assumptions accessors
   - Foundational infrastructure

3. **Week 3:** MortalityColumnAccessor + AssumptionsColumnAccessor (Phases 2 & 3)
   - Can be done in parallel once table system exists
   - Complete the accessor set

4. **Week 4:** Integration and Testing (Phase 5)
   - End-to-end validation
   - Documentation and examples

---

## Code Examples and Patterns

### Pattern 1: Simple Method (No Arguments)

**Example: `cumulative_survival()`**

```python
@register_accessor("projection", kind="column")
class ProjectionColumnAccessor(BaseColumnAccessor):

    def cumulative_survival(self) -> ExpressionProxy:
        """Calculate cumulative survival probabilities from mortality rates.

        Converts a series of mortality rates (qx) into cumulative survival
        probabilities using the formula: survival[t] = (1-qx[0]) × (1-qx[1]) × ... × (1-qx[t])

        For list columns (projected values), applies the calculation element-wise
        within each list. For scalar columns, applies across rows (user should
        add .over() for grouping by policy).

        Returns:
            ExpressionProxy: Cumulative survival probabilities

        Examples:
            ```python
            import polars as pl
            from gaspatchio_core import ActuarialFrame

            # Example with list column (projected values per policy)
            data = {
                "policy_id": [1, 2],
                "qx": [
                    [0.001, 0.0011, 0.0012],  # Policy 1 mortality rates
                    [0.002, 0.0022, 0.0024],  # Policy 2 mortality rates
                ]
            }
            af = ActuarialFrame(data)

            af.survival_to_t = af.qx.projection.cumulative_survival()

            print(af.collect())
            ```

            ```text
            shape: (2, 3)
            ┌───────────┬─────────────────────────┬─────────────────────────┐
            │ policy_id ┆ qx                      ┆ survival_to_t           │
            │ ---       ┆ ---                     ┆ ---                     │
            │ i64       ┆ list[f64]               ┆ list[f64]               │
            ╞═══════════╪═════════════════════════╪═════════════════════════╡
            │ 1         ┆ [0.001, 0.0011, 0.0012] ┆ [0.999, 0.997901, ...]  │
            │ 2         ┆ [0.002, 0.0022, 0.0024] ┆ [0.998, 0.995804, ...]  │
            └───────────┴─────────────────────────┴─────────────────────────┘
            ```
        """
        from ..column.column_proxy import ColumnProxy
        from ..column.expression_proxy import ExpressionProxy
        from ..column.dispatch import ColumnTypeDetector

        # Get base expression
        base_expr = self._proxy._to_expr()
        parent_af = getattr(self._proxy, "_parent", None)

        # Determine if this is a list column
        detector = ColumnTypeDetector(parent_af)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        # Apply appropriate calculation
        if is_list:
            # For list columns: element-wise cumulative product within each list
            # Formula: [px[0], px[0]×px[1], px[0]×px[1]×px[2], ...]
            # where px[i] = 1 - qx[i]
            survival_expr = base_expr.list.eval((1 - pl.element()).cum_prod())
        else:
            # For scalar columns: cumulative product across rows
            # User should add .over("policy_id") if grouping is needed
            survival_expr = (1 - base_expr).cum_prod()

        return ExpressionProxy(survival_expr, parent_af)
```

**Key Elements:**
1. Import types within function to avoid circular imports
2. Get base expression via `self._proxy._to_expr()`
3. Get parent frame reference
4. Use `ColumnTypeDetector` to check if list column
5. Apply different logic for list vs scalar columns
6. Return `ExpressionProxy` wrapping result

### Pattern 2: Method with Arguments

**Example: `on_decrement()`**

```python
def on_decrement(self, inforce: "IntoExprColumn") -> ExpressionProxy:
    """Calculate cashflows that occur when a decrement happens.

    Common decrements: death, surrender, maturity
    Formula: cashflow × inforce × decrement_rate

    Args:
        inforce: Column/expression representing lives inforce at the start of period

    Returns:
        ExpressionProxy: Cashflows when decrement occurs

    Examples:
        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "face_amount": [100000, 150000],
            "qx": [[0.001, 0.0011], [0.002, 0.0022]],
            "survival_to_t": [[0.999, 0.997901], [0.998, 0.995804]]
        }
        af = ActuarialFrame(data)

        # Death benefit = Face × qx × survival_to_t
        af.death_benefit = af.face_amount.projection.on_decrement(af.survival_to_t) * af.qx

        print(af.collect())
        ```
    """
    from ..column.expression_proxy import ExpressionProxy

    # Get base expression (the cashflow amount)
    base_expr = self._proxy._to_expr()
    parent_af = getattr(self._proxy, "_parent", None)

    if parent_af is None:
        raise RuntimeError(
            "on_decrement requires the expression to be part of an ActuarialFrame context"
        )

    # Convert inforce argument to expression
    inforce_expr = parent_af._convert_to_expr(inforce)

    # Calculate: cashflow × inforce
    # (caller will multiply by decrement rate)
    result_expr = base_expr * inforce_expr

    return ExpressionProxy(result_expr, parent_af)
```

**Key Elements:**
1. Accept arguments that can be columns, expressions, or literals
2. Use `parent_af._convert_to_expr()` to handle all input types
3. Build expression using standard Polars operations
4. Return wrapped result

### Pattern 3: Table Lookup Method

**Example: `qx()` (mortality lookup)**

```python
def qx(self, table: str = "BaseMortality") -> ExpressionProxy:
    """Lookup mortality rate from assumption table.

    Args:
        table: Name of the mortality table to use

    Returns:
        ExpressionProxy: Mortality rates (qx) for each age

    Examples:
        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "issue_age": [30, 45, 60],
            "duration": [1, 5, 10]
        }
        af = ActuarialFrame(data)

        # Lookup mortality rates
        af.qx = af.issue_age.mortality.qx(table="2015VBT")

        print(af.collect())
        ```
    """
    from ..column.expression_proxy import ExpressionProxy
    from ..tables import get_mortality_table  # To be implemented

    # Get base expression (the age or duration to lookup)
    base_expr = self._proxy._to_expr()
    parent_af = getattr(self._proxy, "_parent", None)

    if parent_af is None:
        raise RuntimeError(
            "Mortality lookup requires ActuarialFrame context"
        )

    # Get the mortality table
    mortality_table_df = get_mortality_table(table)

    # Join to lookup values
    # Assume table has columns: age, qx
    # This is a simplified example - real implementation needs more sophistication
    lookup_expr = (
        pl.col(self._proxy.name)  # The age column
        .map_elements(
            lambda age: mortality_table_df.filter(pl.col("age") == age)["qx"][0],
            return_dtype=pl.Float64
        )
    )

    return ExpressionProxy(lookup_expr, parent_af)
```

**Note:** The actual table lookup implementation will be more sophisticated, likely using joins rather than `map_elements` for better performance.

### Pattern 4: List Column Manipulation

**Example: `set_at_period()`**

```python
def set_at_period(self, period: int, value: Any) -> ExpressionProxy:
    """Override value at a specific period (list element).

    Used for modeling discontinuities like premium holidays, benefit changes, etc.

    Args:
        period: Zero-based index of period to modify
        value: Value to set at that period

    Returns:
        ExpressionProxy: Modified list with value changed at specified period

    Examples:
        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "premium": [[1000, 1000, 1000, 1000, 1000]]  # 5 periods
        }
        af = ActuarialFrame(data)

        # Premium holiday in period 3 (4th element)
        af.premium_adjusted = af.premium.projection.set_at_period(period=3, value=0)

        print(af.collect())
        # premium_adjusted: [1000, 1000, 1000, 0, 1000]
        ```
    """
    from ..column.expression_proxy import ExpressionProxy

    base_expr = self._proxy._to_expr()
    parent_af = getattr(self._proxy, "_parent", None)

    # Use list.eval to modify element at index
    # This is complex - Polars doesn't have direct "set at index"
    # Alternative: use list slicing and concatenation

    # Approach: split list into before/after, insert new value, concat
    modified_expr = pl.concat_list([
        base_expr.list.slice(0, period),  # Elements before period
        pl.lit([value]),  # New value as single-element list
        base_expr.list.slice(period + 1)  # Elements after period
    ])

    return ExpressionProxy(modified_expr, parent_af)
```

**Key Challenge:** Polars list operations are powerful but require careful construction. Test thoroughly.

---

## Testing Strategy

### 1. Unit Tests

**Location:** `tests/accessors/test_projection.py`, `test_mortality.py`, `test_assumptions.py`

**Pattern:**
```python
import polars as pl
import pytest
from gaspatchio_core import ActuarialFrame

class TestProjectionAccessor:
    def test_cumulative_survival_list_column(self):
        """Test cumulative survival with list column."""
        data = {
            "qx": [[0.001, 0.0011, 0.0012], [0.002, 0.0022, 0.0024]]
        }
        af = ActuarialFrame(data)

        af.survival = af.qx.projection.cumulative_survival()
        result = af.collect()

        # Verify shape
        assert result.shape == (2, 2)

        # Verify values
        expected_survival_1 = [0.999, 0.997901, 0.996704]
        assert result["survival"][0] == pytest.approx(expected_survival_1, rel=1e-5)

    def test_cumulative_survival_scalar_column(self):
        """Test cumulative survival with scalar column."""
        data = {
            "policy_id": [1, 1, 1, 2, 2, 2],
            "qx": [0.001, 0.0011, 0.0012, 0.002, 0.0022, 0.0024]
        }
        af = ActuarialFrame(data)

        af.survival = af.qx.projection.cumulative_survival().over("policy_id")
        result = af.collect()

        # Verify grouped cumulative product
        # ... assertions

    def test_on_decrement(self):
        """Test on_decrement cashflow calculation."""
        # ... test implementation

    # More tests for each method
```

### 2. Docstring Tests

**Embedded in Docstrings:**
```python
def cumulative_survival(self) -> ExpressionProxy:
    """Calculate cumulative survival.

    Examples:
        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"qx": [[0.001, 0.0011, 0.0012]]}
        af = ActuarialFrame(data)
        af.survival = af.qx.projection.cumulative_survival()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌─────────────────────────┬─────────────────────────┐
        │ qx                      ┆ survival                │
        │ ---                     ┆ ---                     │
        │ list[f64]               ┆ list[f64]               │
        ╞═════════════════════════╪═════════════════════════╡
        │ [0.001, 0.0011, 0.0012] ┆ [0.999, 0.9979, 0.9967] │
        └─────────────────────────┴─────────────────────────┘
        ```
    """
```

**Run via:**
```bash
cd gaspatchio-core/bindings/python
uv run pytest --doctest-modules --doctest-glob="*.py"
```

### 3. Integration Tests

**Location:** `tests/integration/test_projection_workflow.py`

**Example:**
```python
def test_term_life_projection():
    """End-to-end test of term life insurance projection."""
    # Setup policy data
    data = {
        "policy_id": [1, 2],
        "issue_age": [30, 45],
        "face_amount": [100000, 250000],
        "annual_premium": [500, 1250],
        "policy_term": [20, 15]
    }
    af = ActuarialFrame(data)

    # Create projection timeline
    import datetime
    af = af.date.create_projection_timeline(
        valuation_date=datetime.date(2024, 1, 1),
        projection_end_type="term_years",
        projection_end_value=20,
        projection_frequency="annual"
    )

    # Lookup mortality
    af.qx = af.issue_age.mortality.qx(table="2015VBT")

    # Calculate survival
    af.survival_to_t = af.qx.projection.cumulative_survival()

    # Calculate cashflows
    af.death_benefit = af.face_amount * af.qx * af.survival_to_t
    af.premium = af.annual_premium * af.survival_to_t
    af.net_cashflow = af.premium - af.death_benefit

    # Discount
    af.discount_factors = (1.05 ** af.duration).projection.cumulative_discount()
    af.pv_cashflow = af.net_cashflow * af.discount_factors

    # Aggregate
    result = af.collect()

    # Assertions
    assert "pv_cashflow" in result.columns
    assert result.shape[0] > 0
    # More detailed assertions...
```

### 4. Performance Tests

**Benchmark Critical Methods:**
```python
import pytest
from gaspatchio_core import ActuarialFrame

@pytest.mark.benchmark
def test_cumulative_survival_performance(benchmark):
    """Benchmark cumulative survival calculation."""
    # Large dataset
    n_policies = 100000
    n_periods = 360  # 30 years monthly

    data = {
        "qx": [[0.001] * n_periods for _ in range(n_policies)]
    }
    af = ActuarialFrame(data)

    def run_calculation():
        af.survival = af.qx.projection.cumulative_survival()
        return af.collect()

    result = benchmark(run_calculation)

    # Performance assertion
    assert benchmark.stats.mean < 1.0  # Should complete in < 1 second
```

---

## Next Steps

### Immediate Actions

1. **Review and Approve This Plan**
   - Confirm approach is sound
   - Adjust priorities if needed
   - Identify any missing requirements

2. **Set Up Development Environment**
   - Create feature branch: `feature/projection-api`
   - Set up test data (sample mortality tables, etc.)

3. **Start with Phase 1**
   - Create `gaspatchio_core/accessors/projection.py`
   - Implement `cumulative_survival()` first
   - Write tests
   - Get it working end-to-end

4. **Iterate**
   - Add methods one at a time
   - Test each thoroughly
   - Document as you go

### Questions to Resolve

1. **Assumption Table System**
   - What storage format? (Parquet, SQLite, in-memory dicts)
   - How should tables be versioned?
   - What's the lookup API?

2. **Naming Conventions**
   - `.cumulative_survival()` vs `.survival_curve()` vs `.tpx()`?
   - Use actuarial notation or English?
   - Consistency across accessors?

3. **Edge Cases**
   - How to handle missing table values?
   - How to handle division by zero in discount calculations?
   - How to handle negative periods or out-of-bounds indices?

4. **Performance Targets**
   - What's acceptable latency for large projections?
   - Should we implement caching?
   - Any optimizations needed for list operations?

---

## Appendix: Complete File Structure

```
gaspatchio-core/bindings/python/
├── gaspatchio_core/
│   ├── column/
│   │   ├── column_proxy.py        ✅ Exists
│   │   ├── expression_proxy.py    ✅ Exists
│   │   └── dispatch.py            ✅ Exists (delegation + shimming)
│   ├── frame/
│   │   ├── base.py                ✅ Exists (ActuarialFrame)
│   │   └── registry.py            ✅ Exists
│   ├── accessors/
│   │   ├── base.py                ✅ Exists
│   │   ├── date.py                ✅ Exists
│   │   ├── finance.py             ✅ Exists
│   │   ├── excel.py               ✅ Exists
│   │   ├── projection.py          📝 To Create
│   │   ├── mortality.py           📝 To Create
│   │   └── assumptions.py         📝 To Create
│   └── tables/                    📝 To Create
│       ├── __init__.py
│       ├── registry.py            📝 Table registry
│       ├── loader.py              📝 Table loading
│       └── sample_tables/         📝 Sample data
│           ├── 2015_vbt.parquet
│           ├── lapse_rates.parquet
│           └── expenses.parquet
├── tests/
│   ├── accessors/
│   │   ├── test_dates.py          ✅ Exists
│   │   ├── test_finance.py        ✅ Exists
│   │   ├── test_excel.py          ✅ Exists
│   │   ├── test_projection.py     📝 To Create
│   │   ├── test_mortality.py      📝 To Create
│   │   └── test_assumptions.py    📝 To Create
│   └── integration/
│       └── test_projection_workflow.py  📝 To Create
└── ref/
    └── 22-api-design/
        ├── 22-intro.md            ✅ Exists
        ├── 22-brainstorm.md       ✅ Exists
        └── 22-implementation-plan.md  ✅ This Document
```

---

## Conclusion

The Gaspatchio projection API infrastructure is **complete and production-ready**. The proxy pattern, delegation system, list column shimming, and accessor registry provide a solid foundation for implementing domain-specific actuarial operations.

**The path forward is clear:**
1. Create new accessor classes (`ProjectionColumnAccessor`, `MortalityColumnAccessor`, `AssumptionsColumnAccessor`)
2. Follow the established patterns from existing accessors
3. Implement methods one at a time with comprehensive tests
4. Build supporting infrastructure (table system) as needed

**Estimated timeline:** 3-4 weeks for full implementation

**Key insight:** No changes to core infrastructure needed. We're building on a solid, tested foundation.

**Next action:** Implement `ProjectionColumnAccessor.cumulative_survival()` as the first working example, following the pattern established in this document.
