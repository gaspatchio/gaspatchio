# Finance Accessor Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `to_monthly()` and `discount_factor()` methods to `.finance` accessor, remove `cumulative_discount()` from `.projection` accessor.

**Architecture:** TDD approach - tests first, then minimal implementation. Column-level accessor methods using native Polars expressions for 6-8x performance improvement over map_elements.

**Tech Stack:** Polars expressions, Python type hints, pytest with docstring validation

---

## Task 1: Remove cumulative_discount() from projection accessor

**Files:**
- Modify: `gaspatchio_core/accessors/projection.py` (remove lines 320-515)
- Modify: `tests/accessors/test_projection.py` (remove cumulative_discount tests)

**Step 1: Identify and remove cumulative_discount() tests**

Check what tests exist for cumulative_discount:

Run: `grep -n "cumulative_discount" tests/accessors/test_projection.py`

**Step 2: Remove cumulative_discount() tests**

Remove all test methods related to `cumulative_discount()` from `tests/accessors/test_projection.py`.

**Step 3: Run remaining projection tests to verify**

Run: `uv run pytest tests/accessors/test_projection.py -v`
Expected: All remaining tests PASS (no cumulative_discount tests)

**Step 4: Remove cumulative_discount() method from projection.py**

Remove lines 320-515 (the entire `cumulative_discount()` method) from `gaspatchio_core/accessors/projection.py`.

**Step 5: Update projection accessor class docstring**

Remove any references to discounting or `cumulative_discount()` from the class docstring in `projection.py`.

**Step 6: Verify projection accessor still works**

Run: `uv run pytest tests/accessors/test_projection.py -v`
Expected: All tests PASS (confirms removal didn't break anything)

**Step 7: Commit**

```bash
git add gaspatchio_core/accessors/projection.py tests/accessors/test_projection.py
git commit -m "refactor: remove cumulative_discount from projection accessor

Move all discounting operations to .finance for clear namespace separation.
.projection now focuses solely on time-shifting operations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Add to_monthly() method - Compound conversion for scalar columns

**Files:**
- Modify: `gaspatchio_core/accessors/finance.py`
- Create: `tests/accessors/test_finance.py` (if doesn't exist)
- Modify: `tests/accessors/test_finance.py` (if exists)

**Step 1: Write failing test for compound conversion on scalar column**

Add to `tests/accessors/test_finance.py`:

```python
# ABOUTME: Tests for finance accessor methods (rate conversion, discounting)
# ABOUTME: Covers to_monthly() and discount_factor() with scalar and list columns

import pytest
from gaspatchio_core import ActuarialFrame


class TestToMonthlyScalar:
    """Tests for to_monthly() rate conversion on scalar columns."""

    def test_compound_conversion_scalar(self) -> None:
        """Test compound conversion on scalar column."""
        af = ActuarialFrame({"annual_rate": [0.05, 0.06, 0.04]})

        af["monthly_rate"] = af["annual_rate"].finance.to_monthly()

        result = af.collect()
        monthly_rates = result["monthly_rate"].to_list()

        # Formula: (1 + annual)^(1/12) - 1
        # 0.05 -> (1.05)^(1/12) - 1 ≈ 0.004074124
        # 0.06 -> (1.06)^(1/12) - 1 ≈ 0.004867551
        # 0.04 -> (1.04)^(1/12) - 1 ≈ 0.003273964
        assert monthly_rates[0] == pytest.approx(0.004074124, rel=1e-6)
        assert monthly_rates[1] == pytest.approx(0.004867551, rel=1e-6)
        assert monthly_rates[2] == pytest.approx(0.003273964, rel=1e-6)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accessors/test_finance.py::TestToMonthlyScalar::test_compound_conversion_scalar -v`
Expected: FAIL with AttributeError: 'FinanceColumnAccessor' object has no attribute 'to_monthly'

**Step 3: Implement minimal to_monthly() method**

Add to `FinanceColumnAccessor` class in `gaspatchio_core/accessors/finance.py`:

```python
from typing import Literal

def to_monthly(
    self,
    method: Literal["compound", "simple"] = "compound"
) -> "ExpressionProxy":
    """Convert annual interest rate to monthly rate.

    Transforms annual effective interest rates to equivalent monthly rates
    using either compound or simple interest conventions.

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
    """
    from ..column.proxy import ExpressionProxy

    base_expr = self._get_polars_expr()
    parent_frame = self._proxy._parent

    if parent_frame is None:
        raise RuntimeError(
            "to_monthly() requires the expression to be part of an ActuarialFrame context."
        )

    # Compound conversion: (1 + annual)^(1/12) - 1
    if method == "compound":
        monthly_expr = ((1 + base_expr).pow(1 / 12)) - 1
    elif method == "simple":
        # Simple conversion: annual / 12
        monthly_expr = base_expr / 12
    else:
        raise ValueError(f"method must be 'compound' or 'simple', got '{method}'")

    return ExpressionProxy(monthly_expr, parent_frame)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestToMonthlyScalar::test_compound_conversion_scalar -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/accessors/finance.py tests/accessors/test_finance.py
git commit -m "feat: add to_monthly() compound conversion for scalar columns

Implements (1 + annual)^(1/12) - 1 formula for compound conversion.
Provides foundation for rate frequency conversion.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Add to_monthly() simple conversion for scalar columns

**Files:**
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write failing test for simple conversion**

Add to `TestToMonthlyScalar` class:

```python
def test_simple_conversion_scalar(self) -> None:
    """Test simple conversion on scalar column."""
    af = ActuarialFrame({"annual_rate": [0.05, 0.06, 0.04]})

    af["monthly_rate"] = af["annual_rate"].finance.to_monthly(method="simple")

    result = af.collect()
    monthly_rates = result["monthly_rate"].to_list()

    # Formula: annual / 12
    # 0.05 / 12 ≈ 0.004166667
    # 0.06 / 12 = 0.005
    # 0.04 / 12 ≈ 0.003333333
    assert monthly_rates[0] == pytest.approx(0.004166667, rel=1e-6)
    assert monthly_rates[1] == pytest.approx(0.005, rel=1e-6)
    assert monthly_rates[2] == pytest.approx(0.003333333, rel=1e-6)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestToMonthlyScalar::test_simple_conversion_scalar -v`
Expected: PASS (implementation already supports this via method parameter)

**Step 3: Commit**

```bash
git add tests/accessors/test_finance.py
git commit -m "test: add simple conversion test for to_monthly()

Validates annual / 12 formula for simple interest conversion.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Add to_monthly() for list columns

**Files:**
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write failing test for list column conversion**

Add new test class:

```python
class TestToMonthlyList:
    """Tests for to_monthly() rate conversion on list columns."""

    def test_compound_conversion_list(self) -> None:
        """Test compound conversion on list column."""
        af = ActuarialFrame({"annual_rates": [[0.05, 0.05, 0.06, 0.06]]})

        af["monthly_rates"] = af["annual_rates"].finance.to_monthly()

        result = af.collect()
        monthly_rates = result["monthly_rates"][0]

        # Each element should be converted independently
        assert monthly_rates[0] == pytest.approx(0.004074124, rel=1e-6)
        assert monthly_rates[1] == pytest.approx(0.004074124, rel=1e-6)
        assert monthly_rates[2] == pytest.approx(0.004867551, rel=1e-6)
        assert monthly_rates[3] == pytest.approx(0.004867551, rel=1e-6)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestToMonthlyList::test_compound_conversion_list -v`
Expected: PASS (Polars automatically broadcasts element-wise for list columns)

**Step 3: Commit**

```bash
git add tests/accessors/test_finance.py
git commit -m "test: add list column test for to_monthly()

Validates element-wise conversion within list columns.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Add discount_factor() method - Spot discounting for scalar columns

**Files:**
- Modify: `gaspatchio_core/accessors/finance.py`
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write failing test for spot discounting on scalar columns**

Add new test class:

```python
class TestDiscountFactorScalar:
    """Tests for discount_factor() calculation on scalar columns."""

    def test_spot_discounting_scalar(self) -> None:
        """Test spot method on scalar columns."""
        af = ActuarialFrame({
            "rate": [0.05, 0.06, 0.04],
            "years": [1, 2, 3]
        })

        af["discount_factor"] = af["rate"].finance.discount_factor(
            periods=af["years"],
            method="spot"
        )

        result = af.collect()
        factors = result["discount_factor"].to_list()

        # Formula: (1 + rate)^(-periods)
        # (1.05)^(-1) ≈ 0.952380952
        # (1.06)^(-2) ≈ 0.889996441
        # (1.04)^(-3) ≈ 0.888996359
        assert factors[0] == pytest.approx(0.952380952, rel=1e-6)
        assert factors[1] == pytest.approx(0.889996441, rel=1e-6)
        assert factors[2] == pytest.approx(0.888996359, rel=1e-6)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorScalar::test_spot_discounting_scalar -v`
Expected: FAIL with AttributeError: 'FinanceColumnAccessor' object has no attribute 'discount_factor'

**Step 3: Implement minimal discount_factor() method**

Add to `FinanceColumnAccessor` class:

```python
def discount_factor(
    self,
    periods: "IntoExprColumn | str",
    method: Literal["spot", "forward"] = "spot"
) -> "ExpressionProxy":
    """Calculate discount factors from interest rates.

    Converts interest rates to discount factors (v^t) using spot or forward
    rate methodology.

    Parameters
    ----------
    periods : str or ExpressionProxy
        Time periods for discounting (column name or expression).
    method : {"spot", "forward"}, default "spot"
        Discounting method:
        - "spot": v[t] = (1 + rate)^(-t) - Single rate applied to all periods
        - "forward": v[t] = cumulative product of (1 + r[i])^(-1) for varying rates

    Returns
    -------
    ExpressionProxy
        Discount factors v^t
    """
    from ..column.proxy import ExpressionProxy

    base_expr = self._get_polars_expr()
    parent_frame = self._proxy._parent

    if parent_frame is None:
        raise RuntimeError(
            "discount_factor() requires the expression to be part of an ActuarialFrame context."
        )

    # Convert periods to expression
    periods_expr = parent_frame._convert_to_expr(periods)

    if method == "spot":
        # Spot discounting: (1 + rate)^(-periods)
        discount_expr = (1 + base_expr).pow(-periods_expr)
    elif method == "forward":
        # Forward discounting - implement in next task
        raise NotImplementedError("Forward discounting not yet implemented")
    else:
        raise ValueError(f"method must be 'spot' or 'forward', got '{method}'")

    return ExpressionProxy(discount_expr, parent_frame)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorScalar::test_spot_discounting_scalar -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/accessors/finance.py tests/accessors/test_finance.py
git commit -m "feat: add discount_factor() spot method for scalar columns

Implements (1 + rate)^(-periods) formula for spot discounting.
Foundation for discount factor calculations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Add discount_factor() spot method for list columns

**Files:**
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write test for spot discounting on list columns**

Add to test file:

```python
class TestDiscountFactorList:
    """Tests for discount_factor() calculation on list columns."""

    def test_spot_discounting_list(self) -> None:
        """Test spot method on list columns."""
        af = ActuarialFrame({
            "monthly_rate": [[0.004, 0.004, 0.004, 0.004]],
            "month": [[0, 1, 2, 3]]
        })

        af["v"] = af["monthly_rate"].finance.discount_factor(
            periods=af["month"],
            method="spot"
        )

        result = af.collect()
        factors = result["v"][0]

        # Formula: (1 + 0.004)^(-t)
        # t=0: (1.004)^0 = 1.0
        # t=1: (1.004)^(-1) ≈ 0.996015936
        # t=2: (1.004)^(-2) ≈ 0.992047748
        # t=3: (1.004)^(-3) ≈ 0.988095425
        assert factors[0] == pytest.approx(1.0, rel=1e-6)
        assert factors[1] == pytest.approx(0.996015936, rel=1e-6)
        assert factors[2] == pytest.approx(0.992047748, rel=1e-6)
        assert factors[3] == pytest.approx(0.988095425, rel=1e-6)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorList::test_spot_discounting_list -v`
Expected: PASS (Polars handles list columns automatically)

**Step 3: Commit**

```bash
git add tests/accessors/test_finance.py
git commit -m "test: add list column test for discount_factor() spot method

Validates element-wise spot discounting within list columns.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Add discount_factor() forward method for list columns

**Files:**
- Modify: `gaspatchio_core/accessors/finance.py`
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write failing test for forward discounting**

Add to `TestDiscountFactorList` class:

```python
def test_forward_discounting_list(self) -> None:
    """Test forward method with period-specific rates."""
    af = ActuarialFrame({
        "forward_rates": [[0.003, 0.004, 0.005, 0.006]],
        "month": [[0, 1, 2, 3]]
    })

    af["v"] = af["forward_rates"].finance.discount_factor(
        periods=af["month"],
        method="forward"
    )

    result = af.collect()
    factors = result["v"][0]

    # Formula: v[0]=1, v[t]=v[t-1]*(1+r[t-1])^(-1)
    # v[0] = 1.0
    # v[1] = 1.0 * (1.003)^(-1) ≈ 0.997009
    # v[2] = 0.997009 * (1.004)^(-1) ≈ 0.993036
    # v[3] = 0.993036 * (1.005)^(-1) ≈ 0.988095
    assert factors[0] == pytest.approx(1.0, rel=1e-6)
    assert factors[1] == pytest.approx(0.997009, rel=1e-4)
    assert factors[2] == pytest.approx(0.993036, rel=1e-4)
    assert factors[3] == pytest.approx(0.988095, rel=1e-4)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorList::test_forward_discounting_list -v`
Expected: FAIL with NotImplementedError: Forward discounting not yet implemented

**Step 3: Implement forward discounting**

Update `discount_factor()` method in `finance.py`:

```python
def discount_factor(
    self,
    periods: "IntoExprColumn | str",
    method: Literal["spot", "forward"] = "spot"
) -> "ExpressionProxy":
    """Calculate discount factors from interest rates.

    [Keep existing docstring]
    """
    from ..column.proxy import ExpressionProxy
    from ..column.column_proxy import ColumnProxy
    from ..column.dispatch import ColumnTypeDetector

    base_expr = self._get_polars_expr()
    parent_frame = self._proxy._parent

    if parent_frame is None:
        raise RuntimeError(
            "discount_factor() requires the expression to be part of an ActuarialFrame context."
        )

    # Convert periods to expression
    periods_expr = parent_frame._convert_to_expr(periods)

    if method == "spot":
        # Spot discounting: (1 + rate)^(-periods)
        discount_expr = (1 + base_expr).pow(-periods_expr)
    elif method == "forward":
        # Forward discounting: cumulative product of (1+r[i])^(-1)
        # Detect if this is a list column
        detector = ColumnTypeDetector(parent_frame)
        is_list = False

        if isinstance(self._proxy, ColumnProxy):
            is_list = detector.is_list_column(self._proxy.name)

        if is_list:
            # For list columns: v[t] = cumulative product of (1+r[i])^(-1)
            # Use list.eval with cumulative product
            discount_expr = base_expr.list.eval(
                (1 / (1 + pl.element())).cum_prod()
            )
        else:
            # For scalar columns: cumulative product across rows
            discount_expr = (1 / (1 + base_expr)).cum_prod()
    else:
        raise ValueError(f"method must be 'spot' or 'forward', got '{method}'")

    return ExpressionProxy(discount_expr, parent_frame)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorList::test_forward_discounting_list -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/accessors/finance.py tests/accessors/test_finance.py
git commit -m "feat: add discount_factor() forward method for list columns

Implements cumulative product formula for period-varying rates.
Uses Polars list.eval for efficient element-wise calculation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Add period zero edge case test

**Files:**
- Modify: `tests/accessors/test_finance.py`

**Step 1: Write test for period 0 returning v=1.0**

Add to `TestDiscountFactorList` class:

```python
def test_period_zero_returns_one(self) -> None:
    """Test that period 0 always returns v=1.0."""
    af = ActuarialFrame({
        "rate": [[0.05, 0.06, 0.04]],
        "period": [[0, 0, 0]]
    })

    af["v"] = af["rate"].finance.discount_factor(periods=af["period"], method="spot")

    result = af.collect()
    factors = result["v"][0]

    # (1 + rate)^(-0) = 1.0 for any rate
    assert factors[0] == pytest.approx(1.0, rel=1e-6)
    assert factors[1] == pytest.approx(1.0, rel=1e-6)
    assert factors[2] == pytest.approx(1.0, rel=1e-6)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/accessors/test_finance.py::TestDiscountFactorList::test_period_zero_returns_one -v`
Expected: PASS (formula naturally handles this: anything^0 = 1)

**Step 3: Commit**

```bash
git add tests/accessors/test_finance.py
git commit -m "test: add edge case for period 0 in discount_factor()

Validates that v^0 = 1.0 regardless of rate.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Add comprehensive docstrings with examples

**Files:**
- Modify: `gaspatchio_core/accessors/finance.py`

**Step 1: Add full docstring to to_monthly() with examples**

Replace minimal docstring with complete version from design doc (lines 96-179 of design.md).

Run examples to get exact output:

```bash
uv run python -c "
from gaspatchio_core import ActuarialFrame

data = {'annual_rate': [0.05, 0.06, 0.04]}
af = ActuarialFrame(data)
af['monthly_rate'] = af['annual_rate'].finance.to_monthly()
print(af.collect())
"
```

Copy exact output into docstring example.

**Step 2: Add full docstring to discount_factor() with examples**

Replace minimal docstring with complete version from design doc (lines 205-311 of design.md).

Run examples to get exact output for each example.

**Step 3: Run docstring tests**

Run: `uv run pytest --doctest-modules gaspatchio_core/accessors/finance.py -v`
Expected: All docstring examples PASS

**Step 4: Commit**

```bash
git add gaspatchio_core/accessors/finance.py
git commit -m "docs: add comprehensive docstrings to finance accessor

Include actuarial examples, formulas, and use cases.
All examples validated with actual output.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Update finance accessor class docstring

**Files:**
- Modify: `gaspatchio_core/accessors/finance.py`

**Step 1: Update FinanceColumnAccessor class docstring**

Replace class docstring at line 78-83:

```python
@register_accessor("finance", kind="column")
class FinanceColumnAccessor(BaseColumnAccessor):
    """Financial mathematics and valuation operations.

    Provides methods for rate conversion, discount factor calculation,
    and present value computations on columns or expressions.

    Accessed via `.finance` on an ActuarialFrame column or expression proxy,
    e.g., `af["annual_rate"].finance.to_monthly()`.

    Methods
    -------
    to_monthly(method="compound")
        Convert annual interest rates to monthly rates
    discount_factor(periods, method="spot")
        Calculate discount factors v^t from interest rates
    discount(rate_expr, n_periods_expr)
        Discount values using specified rate and periods
    """
```

**Step 2: Commit**

```bash
git add gaspatchio_core/accessors/finance.py
git commit -m "docs: update finance accessor class docstring

Document new methods and financial mathematics focus.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Run full test suite and validate

**Files:**
- N/A (validation only)

**Step 1: Run all finance accessor tests**

Run: `uv run pytest tests/accessors/test_finance.py -v`
Expected: All tests PASS

**Step 2: Run all projection accessor tests**

Run: `uv run pytest tests/accessors/test_projection.py -v`
Expected: All tests PASS (no cumulative_discount tests remain)

**Step 3: Run type checking**

Run: `uv run mypy gaspatchio_core/accessors/finance.py`
Expected: No errors

Run: `uv run pyright gaspatchio_core/accessors/finance.py`
Expected: No errors

**Step 4: Run docstring tests**

Run: `uv run pytest --doctest-modules gaspatchio_core/accessors/finance.py -v`
Expected: All docstring examples PASS

**Step 5: Validation complete - no commit needed**

---

## Task 12: Integration test with basic_term model (optional)

**Files:**
- Reference: `~/Projects/gaspatchio-models/basic_term/model_projection.py`

**Step 1: Create test script to compare old vs new approach**

Create temporary test file to validate the new API produces same results as old map_elements approach.

**Step 2: Run comparison**

Verify numerical results match between:
- Old: map_elements with Python UDF
- New: .finance.to_monthly() and .discount_factor()

**Step 3: Benchmark performance**

Measure execution time difference (should be 6-8x faster).

**Step 4: Document results**

Add performance findings to design document or create benchmark report.

---

## Success Criteria

**Functional:**
- ✅ `to_monthly()` converts annual→monthly (compound and simple)
- ✅ `discount_factor()` calculates v^t (spot and forward)
- ✅ Works on scalar and list columns
- ✅ `cumulative_discount()` removed from `.projection`

**Testing:**
- ✅ Unit tests PASS for all methods
- ✅ Docstring examples PASS
- ✅ Type checking PASS (mypy and pyright)
- ✅ No regressions in projection tests

**Documentation:**
- ✅ Comprehensive docstrings with formulas
- ✅ Actuarial use case examples
- ✅ Class docstrings updated

---

## Execution Notes

**Testing patterns to follow:**
- Look at `tests/accessors/test_projection.py` for test structure
- Use `pytest.approx()` for floating point comparisons
- Test both scalar and list columns for each method
- Include edge cases (period 0, negative rates if relevant)

**Type hints:**
- Follow existing patterns in `finance.py`
- Use `Literal` for method parameters
- Use `IntoExprColumn` for flexible input types

**Polars patterns:**
- List columns use `.list.eval()` for element-wise operations
- Scalar columns use direct expression operations
- Use `.pow()` for exponentiation
- Use `.cum_prod()` for cumulative products
