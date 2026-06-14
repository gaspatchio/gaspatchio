# Finance Accessor Enhancement: Discount Rate API Design

**Date:** 2025-01-11
**Status:** Design Complete - Ready for Implementation
**Authors:** Matt Wright, Claude

## Executive Summary

Enhance the `.finance` accessor to eliminate `map_elements` performance bottlenecks in discount rate calculations. Add two new methods (`to_monthly()` and `discount_factor()`) that provide transparent, auditable financial calculations following Gaspatchio's "code IS the formula" philosophy.

**Impact:** Replace ~30 lines of Python UDF code with 4 lines of native Polars expressions, achieving 6-8x performance improvement while improving readability and auditability.

## Problem Statement

### Current Pain Point

Actuarial models require discount rate calculations that currently use `map_elements` with Python UDFs:

```python
# Current approach: 30 lines, slow Python loops
def calc_disc_rate_mth(row):
    months = row["month"]
    disc_rates_mth = []
    for m in months:
        year = m // 12
        annual_rate = disc_rate_dict.get(year, 0.0)
        monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
        disc_rates_mth.append(monthly_rate)
    return disc_rates_mth

af.disc_rate_mth = pl.struct([pl.col("month")]).map_elements(
    calc_disc_rate_mth, return_dtype=pl.List(pl.Float64)
)

def calc_disc_factors(row):
    disc_rates = row["disc_rate_mth"]
    disc_factors = []
    for t in range(len(disc_rates)):
        rate = disc_rates[t]
        factor = (1 + rate) ** (-t) if t > 0 else 1.0
        disc_factors.append(factor)
    return disc_factors

af.disc_factors = pl.struct([pl.col("disc_rate_mth")]).map_elements(
    calc_disc_factors, return_dtype=pl.List(pl.Float64)
)
```

**Issues:**
- Python UDF overhead (6-8x slower than native Polars)
- Obscures actuarial intent with implementation details
- Difficult to audit calculations
- Breaks the Gaspatchio flow of readable formulas

### What We Need

Gaspatchio-style API that:
1. **Reads like mathematical formulas** in English
2. **Shows transparent calculations** actuaries can verify
3. **Is discoverable** via autocomplete and LLMs
4. **Performs at native Polars speed**

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Namespace** | `.finance` accessor (enhance existing) | Already exists, familiar pattern, LLM-discoverable |
| **Method style** | Column-level accessors | Consistent with `.projection`, better autocomplete |
| **Number of methods** | Three separate methods | Transparency over convenience - explicit steps |
| **Yield curve lookups** | Keep using `Table` class | Separation of concerns, existing pattern works |
| **Rate conversion** | `to_monthly(method)` | Single responsibility, explicit formula |
| **Discount factors** | `discount_factor(periods, method)` | Supports both spot and forward discounting |

## API Design

### Overview

Enhance existing `/gaspatchio_core/accessors/finance.py` with two new column-level methods:

1. **`to_monthly(method="compound")`** - Convert annual rates to monthly rates
2. **`discount_factor(periods, method="spot")`** - Calculate discount factors v^t

### Design Principles Applied

✅ **Transparent calculations**: Each step is explicit and auditable
✅ **Poetic formulas**: Reads like actuarial specifications
✅ **LLM-discoverable**: Clear method names match domain terminology
✅ **Escape hatches**: Users can still use `map_elements` for custom logic
✅ **Consistency**: Matches `.projection` and `.excel` accessor patterns

## Method 1: Rate Frequency Conversion

### Signature

```python
def to_monthly(
    self,
    method: Literal["compound", "simple"] = "compound"
) -> ExpressionProxy:
    """Convert annual interest rate to monthly rate.

    Transforms annual effective interest rates to equivalent monthly rates
    using either compound or simple interest conventions. Essential for
    actuarial projections with monthly timesteps when assumptions are
    provided annually.

    For list columns, applies conversion element-wise within each list.
    For scalar columns, applies conversion to each row value.

    Parameters
    ----------
    method : {"compound", "simple"}, default "compound"
        Conversion method:
        - "compound": (1 + r_annual)^(1/12) - 1 (standard actuarial practice)
        - "simple": r_annual / 12 (linear approximation)

    Returns
    -------
    ExpressionProxy
        Monthly interest rate with same structure as input (scalar or list)

    Examples
    --------
    **Compound conversion (standard actuarial)**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {"annual_rate": [0.05, 0.06, 0.04]}
    af = ActuarialFrame(data)

    af["monthly_rate"] = af["annual_rate"].finance.to_monthly()

    print(af.collect())
    # Result: [0.004074, 0.004868, 0.003274]
    # Formula: (1 + 0.05)^(1/12) - 1 = 0.004074
    ```

    **Simple conversion (approximation)**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {"annual_rate": [0.05, 0.06, 0.04]}
    af = ActuarialFrame(data)

    af["monthly_rate"] = af["annual_rate"].finance.to_monthly(method="simple")

    print(af.collect())
    # Result: [0.004167, 0.005, 0.003333]
    # Formula: 0.05 / 12 = 0.004167
    ```

    **List column (projection timeline)**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {"annual_rates": [[0.05, 0.05, 0.06, 0.06]]}
    af = ActuarialFrame(data)

    af["monthly_rates"] = af["annual_rates"].finance.to_monthly()

    print(af.collect())
    # Result: [[0.004074, 0.004074, 0.004868, 0.004868]]
    # Applied element-wise within list
    ```

    Notes
    -----
    - Compound method is standard actuarial practice (maintains equivalence)
    - Simple method provides linear approximation (less accurate but faster)
    - For list columns, conversion is applied to each element
    - Formula is transparent and auditable in the method implementation

    See Also
    --------
    discount_factor : Calculate discount factors from interest rates
    """
```

### Implementation Formulas

**Compound method** (default):
```
monthly_rate = (1 + annual_rate)^(1/12) - 1
```

**Simple method**:
```
monthly_rate = annual_rate / 12
```

### List Column Handling

Uses Polars' automatic broadcasting:
- List columns: Apply element-wise within each list
- Scalar columns: Apply to each row value

## Method 2: Discount Factor Calculation

### Signature

```python
def discount_factor(
    self,
    periods: str | ExpressionProxy,
    method: Literal["spot", "forward"] = "spot"
) -> ExpressionProxy:
    """Calculate discount factors from interest rates.

    Converts interest rates to discount factors (v^t) using spot or forward
    rate methodology. Discount factors are essential for calculating present
    values of future cashflows in actuarial projections, reserve calculations,
    and pricing models.

    The rate column (self) and periods parameter can both be scalar or list
    columns, with automatic broadcasting applied.

    Parameters
    ----------
    periods : str or ExpressionProxy
        Time periods for discounting (column name or expression).
        Typically represents t in months or years.
    method : {"spot", "forward"}, default "spot"
        Discounting method:
        - "spot": v[t] = (1 + rate)^(-t) - Single rate applied to all periods
        - "forward": v[t] = cumulative product of (1 + r[i])^(-1) for varying rates

    Returns
    -------
    ExpressionProxy
        Discount factors v^t

    Examples
    --------
    **Spot discounting (constant rate)**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "monthly_rate": [[0.004, 0.004, 0.004, 0.004]],
        "month": [[0, 1, 2, 3]]
    }
    af = ActuarialFrame(data)

    af["v"] = af["monthly_rate"].finance.discount_factor(
        periods=af["month"],
        method="spot"
    )

    print(af.collect())
    # Result v: [[1.0, 0.996016, 0.992048, 0.988095]]
    # Formula: (1 + 0.004)^(-t) for t in [0, 1, 2, 3]
    ```

    **Forward discounting (varying rates)**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "forward_rates": [[0.003, 0.004, 0.005, 0.006]],
        "month": [[0, 1, 2, 3]]
    }
    af = ActuarialFrame(data)

    af["v"] = af["forward_rates"].finance.discount_factor(
        periods=af["month"],
        method="forward"
    )

    print(af.collect())
    # Result v: [[1.0, 0.996016, 0.992048, 0.987095]]
    # Formula: v[0]=1, v[1]=(1+r[0])^(-1), v[2]=v[1]*(1+r[1])^(-1), ...
    ```

    **Scalar columns**:

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "rate": [0.05, 0.06, 0.04],
        "years": [1, 2, 3]
    }
    af = ActuarialFrame(data)

    af["discount_factor"] = af["rate"].finance.discount_factor(
        periods=af["years"],
        method="spot"
    )

    print(af.collect())
    # Result: [0.952381, 0.889996, 0.888996]
    # Formula: (1 + rate)^(-years) for each row
    ```

    Notes
    -----
    - Spot method uses a single rate for all periods (standard for zero curves)
    - Forward method uses period-specific rates (cumulative product)
    - Period 0 always returns discount factor of 1.0
    - Handles both scalar and list columns automatically

    See Also
    --------
    to_monthly : Convert annual rates to monthly rates
    present_value : Calculate present value of cashflows (existing method)
    """
```

### Implementation Formulas

**Spot method** (default):
```
v[t] = (1 + rate)^(-t)
```
- Single rate applied to all periods
- Use case: Constant discount rate from a zero curve

**Forward method**:
```
v[0] = 1.0
v[t] = v[t-1] * (1 + r[t-1])^(-1)
```
- Cumulative product of period-specific discount factors
- Use case: Time-varying rates in a projection

### Why Column-Level (Not Frame-Level)

**Decision:** Make this a column accessor method (called on the rate column) rather than a frame-level method.

**Rationale:**
1. **Consistency**: Matches existing `.projection` and `.excel` patterns (e.g., `af["rate"].excel.pv(...)`)
2. **Discoverability**: Autocomplete shows `af["rate"].finance.<TAB>` → all finance methods
3. **LLM-friendly**: All pandas/Polars accessors are column-level
4. **Semantic clarity**: The rate is the "primary" column being operated on, periods is a parameter

## Complete Usage Example

### Before: map_elements (Current)

```python
# ~30 lines of Python UDF code
disc_rate_dict = dict(zip(df["year"], df["zero_spot"]))

def calc_disc_rate_mth(row):
    months = row["month"]
    disc_rates_mth = []
    for m in months:
        year = m // 12
        annual_rate = disc_rate_dict.get(year, 0.0)
        monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
        disc_rates_mth.append(monthly_rate)
    return disc_rates_mth

af.disc_rate_mth = pl.struct([pl.col("month")]).map_elements(
    calc_disc_rate_mth, return_dtype=pl.List(pl.Float64)
)

def calc_disc_factors(row):
    disc_rates = row["disc_rate_mth"]
    disc_factors = []
    for t in range(len(disc_rates)):
        rate = disc_rates[t]
        factor = (1 + rate) ** (-t) if t > 0 else 1.0
        disc_factors.append(factor)
    return disc_factors

af.disc_factors = pl.struct([pl.col("disc_rate_mth")]).map_elements(
    calc_disc_factors, return_dtype=pl.List(pl.Float64)
)
```

### After: .finance accessor (4 lines)

```python
# Step 1: Lookup annual rate by year (existing Table pattern)
af["year"] = af["month"] // 12
af["annual_rate"] = disc_rate_table.lookup(year=af["year"])

# Step 2: Convert to monthly rate (NEW)
af["monthly_rate"] = af["annual_rate"].finance.to_monthly(method="compound")

# Step 3: Calculate discount factors (NEW)
af["disc_factors"] = af["monthly_rate"].finance.discount_factor(
    periods=af["month"],
    method="spot"
)
```

### Benefits

✅ **Performance**: 6-8x faster (native Polars vs Python UDFs)
✅ **Readability**: 4 lines vs 30 lines
✅ **Auditability**: Each formula is explicit in method docstrings
✅ **Discoverability**: Autocomplete shows available methods
✅ **Consistency**: Matches existing `.projection` and `.excel` patterns

## Integration with Existing Code

### Existing .finance Methods

The `.finance` accessor already exists with these methods:
- `present_value()` - Calculate PV of cashflows
- `discount()` - Apply discount to values

### New Methods Add

- `to_monthly()` - Rate frequency conversion
- `discount_factor()` - Calculate v^t from rates

### Breaking Changes

**BREAKING:** Remove `cumulative_discount()` from `.projection` accessor

**Rationale:**
- Clear namespace separation: `.projection` = time-shifting, `.finance` = financial calculations
- Eliminates confusion between `.projection.cumulative_discount()` and `.finance.discount_factor()`
- All discounting operations in one discoverable location
- No backward compatibility needed (early development phase)

**Migration:**
```python
# Old (REMOVED):
af["v"] = af["rate"].projection.cumulative_discount(mode="compound", start_at=1.0)

# New:
af["v"] = af["rate"].finance.discount_factor(periods=af["month"], method="forward")
```

**Impact:** Any code using `.projection.cumulative_discount()` must be updated to use `.finance.discount_factor()` instead.

## Implementation Scope

### Files to Modify

1. **`/gaspatchio_core/accessors/finance.py`**
   - Add `to_monthly()` method
   - Add `discount_factor()` method
   - Update class docstring with new methods

2. **`/gaspatchio_core/accessors/projection.py`**
   - **REMOVE** `cumulative_discount()` method (lines 320-515)
   - Update class docstring to remove discount references
   - Rationale: All discounting moves to `.finance` for clear namespace separation

3. **`/tests/accessors/test_finance.py`**
   - Add unit tests for `to_monthly()` (compound and simple)
   - Add unit tests for `discount_factor()` (spot and forward)
   - Add tests for scalar and list columns
   - Add edge case tests (period 0, negative rates, etc.)

4. **`/tests/accessors/test_projection.py`**
   - **REMOVE** tests for `cumulative_discount()` method
   - Keep all other projection tests (time-shifting, survival, period overrides)

### Testing Strategy

**Unit Tests** (following patterns from `test_projection.py`):
```python
class TestToMonthly:
    """Tests for to_monthly() rate conversion."""

    def test_compound_conversion_scalar(self):
        """Test compound conversion on scalar column."""

    def test_simple_conversion_scalar(self):
        """Test simple conversion on scalar column."""

    def test_compound_conversion_list(self):
        """Test compound conversion on list column."""

class TestDiscountFactor:
    """Tests for discount_factor() calculation."""

    def test_spot_discounting_scalar(self):
        """Test spot method on scalar columns."""

    def test_spot_discounting_list(self):
        """Test spot method on list columns."""

    def test_forward_discounting_list(self):
        """Test forward method with period-specific rates."""

    def test_period_zero_returns_one(self):
        """Test that period 0 always returns v=1.0."""
```

**Docstring Examples**:
- Run examples to get exact Polars output
- Follow `ref/recipes/write-docstring.md` patterns
- Include "When to use" admonitions with actuarial use cases

**Integration Tests**:
- Modify `basic_term/model_projection.py` to use new API
- Verify results match original `map_elements` implementation
- Benchmark performance improvement

## Research Foundation

This design is informed by research into:

### Actuarial Libraries
- **JuliaActuary**: Uses `present_value()`, `discount()` top-level functions with `Rate` type system
- **QuantLib**: Uses `discount()`, `zeroRate()`, `forwardRate()` methods on curve objects
- **pyliferisk**: Uses International Actuarial Notation for method names
- **numpy-financial**: Simple `npv(rate, cashflows)` functional API

### Actuarial Notation
- **v** = universal symbol for discount factor
- **i** = effective interest rate
- **APV** = actuarial present value
- Standardized by International Actuarial Notation (1949/1950)

### Key Insights
1. All libraries converge on `discount()` and `present_value()` as primary names
2. Only Gaspatchio uses DataFrame `.accessor` pattern (unique advantage!)
3. Actuaries expect transparent formulas matching textbook notation
4. LLMs need clear, domain-standard terminology

**Research Sources:**
- JuliaActuary: https://juliaactuary.github.io/ActuarialUtilities.jl/dev/
- QuantLib: https://quantlib-python-docs.readthedocs.io/en/latest/termstructures/yield.html
- SOA Notation: https://www.soa.org/globalassets/assets/files/edu/edu-exam-fm-notation-term.pdf
- Actuarial Notation: https://en.wikipedia.org/wiki/Actuarial_notation

## Success Criteria

### Functional Requirements
- ✅ `to_monthly()` converts annual→monthly rates correctly (compound and simple)
- ✅ `discount_factor()` calculates v^t using spot and forward methods
- ✅ Works on both scalar and list columns
- ✅ Matches existing `map_elements` results numerically
- ✅ Integrates with existing `.finance` accessor

### Performance Requirements
- ✅ 6-8x faster than `map_elements` approach
- ✅ Native Polars execution (no Python UDF overhead)
- ✅ Lazy evaluation compatible

### Code Quality Requirements
- ✅ Comprehensive docstrings with actuarial examples
- ✅ Unit test coverage >90%
- ✅ Type-safe implementation with proper type hints
- ✅ Clear error messages for invalid inputs

### API Design Requirements
- ✅ Reads like mathematical formulas in English
- ✅ Transparent calculations (formulas visible in docstrings)
- ✅ LLM-discoverable (clear naming, patterns)
- ✅ Consistent with existing `.projection` and `.excel` patterns

## Alternative Approaches Considered

### Alternative 1: Chainable Operations (Rejected)

```python
af["pv"] = af["cashflow"].finance.present_value(
    rate=af["annual_rate"],
    rate_freq="annual",  # auto-converts
    payment_freq="monthly"
)
```

**Rejected because:**
- Hides conversion step (less transparent)
- More "magic" than explicit steps
- Harder to audit calculations
- Violates "code IS the formula" principle

### Alternative 2: Frame-Level Methods (Rejected)

```python
af["v"] = af.finance.discount_factor(
    rate=af["monthly_rate"],
    periods=af["month"]
)
```

**Rejected because:**
- Inconsistent with existing `.projection` and `.excel` patterns
- Less discoverable via autocomplete
- Breaks accessor pattern convention
- Harder for LLMs (expect column-level accessors)

### Alternative 3: Use .projection Accessor (Rejected)

Put discount methods in `.projection` instead of `.finance`.

**Rejected because:**
- `.projection` is for time-series operations (shifting, cumulative)
- `.finance` already exists for financial calculations
- Better separation of concerns
- Finance operations are broader than just projections

## Namespace Clarity After This Change

### `.projection` Accessor (Time-Series Operations)

**Purpose:** Operations on projection timelines and time-shifting

**Methods:**
- `previous_period()` - Get value from t-1
- `next_period()` - Get value from t+1
- `at_period()` - Get value at arbitrary offset
- `cumulative_survival()` - Calculate survival probabilities from mortality rates
- `with_period()` - Override value at specific period
- `with_periods()` - Override values at multiple periods

**Philosophy:** Time-domain operations - shifting, lagging, survival calculations

### `.finance` Accessor (Financial Calculations)

**Purpose:** Financial mathematics and valuation operations

**Methods (after this enhancement):**
- `to_monthly()` - Convert annual rates to monthly (NEW)
- `discount_factor()` - Calculate v^t from rates (NEW)
- `present_value()` - Calculate PV of cashflows (existing)
- `discount()` - Apply discount to values (existing)

**Philosophy:** Financial calculations - rates, discounting, present values, valuations

**Clear separation:** Time operations vs. financial mathematics

## Next Steps

### Implementation

1. Use `superpowers:using-git-worktrees` to create isolated workspace
2. Use `superpowers:writing-plans` to create detailed implementation plan
3. Follow TDD approach (tests first, then implementation)
4. Use `superpowers:requesting-code-review` when complete

### Documentation

1. Update existing `.finance` accessor docstring
2. Update `.projection` accessor docstring (remove discount references)
3. Add examples to user guide
4. Update migration guide for moving from `map_elements`

### Validation

1. Check for any existing code using `.projection.cumulative_discount()`
2. Run on `basic_term/model_projection.py` to validate results
3. Benchmark performance improvement
4. Get actuary feedback on API ergonomics

---

**Status:** Design validated and ready for implementation
**Next Action:** Proceed with implementation plan or iterate on design
