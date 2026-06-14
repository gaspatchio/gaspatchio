# Period Time-Shifting API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add actuarial-friendly methods for accessing previous/next period values using `t-1` notation instead of confusing `.shift()` calls.

**Architecture:** Extend `ProjectionColumnAccessor` with three new methods:
- `previous_period()` - shorthand for `t-1` (most common case)
- `next_period()` - shorthand for `t+1` (rare but useful)
- `at_period(relative_period)` - flexible for arbitrary offsets using mathematical notation

**Tech Stack:** Polars expressions, PyO3 bindings, pytest with docstring validation

**Design Philosophy:** Following the "code IS the formula" pattern from `ref/22-api-design/22-brainstorm.md`, these methods make time-shifting transparent and auditable for actuaries while using mathematical `t-1` notation they're familiar with.

---

## Task 1: Add `previous_period()` Method

**Files:**
- Modify: `gaspatchio_core/accessors/projection.py:670` (add method after `with_period()`)
- Test: `tests/accessors/test_projection.py:~300` (new test class)

### Step 1: Write the failing test

Add to `tests/accessors/test_projection.py` after existing test classes:

```python
class TestPreviousPeriod:
    """Tests for previous_period() method."""

    def test_list_column_basic(self):
        """Test previous_period with list column and default fill."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_prev = af.value.projection.previous_period()

        result = af.collect()
        value_prev = result["value_prev"][0]

        # Should shift back one period with fill_value=0
        # [100, 110, 120] -> [0, 100, 110]
        assert len(value_prev) == 3
        assert value_prev[0] == 0
        assert value_prev[1] == 100
        assert value_prev[2] == 110

    def test_custom_fill_value(self):
        """Test previous_period with custom fill value."""
        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        af.reserve_prev = af.reserve.projection.previous_period(fill_value=500)

        result = af.collect()
        reserve_prev = result["reserve_prev"][0]

        # [1000, 1100, 1200] -> [500, 1000, 1100]
        assert reserve_prev[0] == 500
        assert reserve_prev[1] == 1000
        assert reserve_prev[2] == 1100

    def test_multiple_policies(self):
        """Test previous_period with multiple policies."""
        data = {
            "policy_id": [1, 2],
            "pols_death": [[10, 15, 20], [5, 8, 12]],
        }
        af = ActuarialFrame(data)

        af.pols_death_prev = af.pols_death.projection.previous_period()

        result = af.collect()

        # Policy 1: [10, 15, 20] -> [0, 10, 15]
        prev_1 = result["pols_death_prev"][0]
        assert prev_1[0] == 0
        assert prev_1[1] == 10
        assert prev_1[2] == 15

        # Policy 2: [5, 8, 12] -> [0, 5, 8]
        prev_2 = result["pols_death_prev"][1]
        assert prev_2[0] == 0
        assert prev_2[1] == 5
        assert prev_2[2] == 8
```

### Step 2: Run test to verify it fails

Run: `uv run pytest tests/accessors/test_projection.py::TestPreviousPeriod -v`

Expected: FAIL with `AttributeError: 'ProjectionColumnAccessor' object has no attribute 'previous_period'`

### Step 3: Write minimal implementation

Add to `gaspatchio_core/accessors/projection.py` after the `with_period()` method (around line 670):

```python
    def previous_period(self, fill_value=0) -> ExpressionProxy:
        """Get value from previous period (t-1).

        Equivalent to shifting back one period. Most common case for
        actuarial projections when referencing prior period values.

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        Parameters
        ----------
        fill_value : scalar, optional
            Value to use for first period where no previous value exists.
            Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values shifted from previous period

        Examples
        --------
        **Basic Usage: Previous Period Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"pols_death": [[10, 15, 20]]}
        af = ActuarialFrame(data)

        af.pols_death_prev = af.pols_death.projection.previous_period()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────┬──────────────────┐
        │ pols_death   ┆ pols_death_prev  │
        │ ---          ┆ ---              │
        │ list[i64]    ┆ list[i64]        │
        ╞══════════════╪══════════════════╡
        │ [10, 15, 20] ┆ [0, 10, 15]      │
        └──────────────┴──────────────────┘
        ```

        **Custom Fill Value: Reserve Calculations**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # Use None to get null for missing values
        af.reserve_prev = af.reserve.projection.previous_period(fill_value=None)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬──────────────────┐
        │ reserve          ┆ reserve_prev     │
        │ ---              ┆ ---              │
        │ list[i64]        ┆ list[i64]        │
        ╞══════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [null, 1000, ...] │
        └──────────────────┴──────────────────┘
        ```

        **Actuarial Formula: Inforce Rollforward**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "pols_if_after_death": [[1000, 990, 975]],
            "pols_lapse": [[5, 8, 10]],
        }
        af = ActuarialFrame(data)

        # Calculate beginning-of-period inforce using previous period values
        # pols_if_bop(t) = pols_if_after_death(t-1) - pols_lapse(t-1)
        af.pols_if_prev = af.pols_if_after_death.projection.previous_period(
            fill_value=1000
        )
        af.pols_lapse_prev = af.pols_lapse.projection.previous_period()
        af.pols_if_bop = af.pols_if_prev - af.pols_lapse_prev

        print(af.collect())
        ```

        ```text
        shape: (1, 4)
        ┌─────────────────────┬─────────────┬────────────────┬─────────────┐
        │ pols_if_after_death ┆ pols_lapse  ┆ pols_if_prev   ┆ pols_if_bop │
        │ ---                 ┆ ---         ┆ ---            ┆ ---         │
        │ list[i64]           ┆ list[i64]   ┆ list[i64]      ┆ list[i64]   │
        ╞═════════════════════╪═════════════╪════════════════╪═════════════╡
        │ [1000, 990, 975]    ┆ [5, 8, 10]  ┆ [1000, 1000... ┆ [1000, 995..│
        └─────────────────────┴─────────────┴────────────────┴─────────────┘
        ```

        See Also
        --------
        next_period : Get value from next period (t+1)
        at_period : Get value at arbitrary period offset

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        shifted_expr = base_expr.shift(1, fill_value=fill_value)

        parent_af = self._get_parent_frame()
        return ExpressionProxy(shifted_expr, parent_af)
```

### Step 4: Run test to verify it passes

Run: `uv run pytest tests/accessors/test_projection.py::TestPreviousPeriod -v`

Expected: All 3 tests PASS

### Step 5: Commit

```bash
git add tests/accessors/test_projection.py gaspatchio_core/accessors/projection.py
git commit -m "feat: add previous_period() method for t-1 time-shifting

Add actuarial-friendly method for accessing previous period values using
t-1 notation. Wraps Polars shift() with default fill_value=0 for common
actuarial patterns like inforce rollforward and reserve calculations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Add `next_period()` Method

**Files:**
- Modify: `gaspatchio_core/accessors/projection.py:~800` (add after `previous_period()`)
- Test: `tests/accessors/test_projection.py:~340` (add to test file)

### Step 1: Write the failing test

Add to `tests/accessors/test_projection.py` after `TestPreviousPeriod`:

```python
class TestNextPeriod:
    """Tests for next_period() method."""

    def test_list_column_basic(self):
        """Test next_period with list column and default fill."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_next = af.value.projection.next_period()

        result = af.collect()
        value_next = result["value_next"][0]

        # Should shift forward one period with fill_value=0
        # [100, 110, 120] -> [110, 120, 0]
        assert len(value_next) == 3
        assert value_next[0] == 110
        assert value_next[1] == 120
        assert value_next[2] == 0

    def test_custom_fill_value(self):
        """Test next_period with custom fill value."""
        data = {"projected": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        af.projected_next = af.projected.projection.next_period(fill_value=None)

        result = af.collect()
        projected_next = result["projected_next"][0]

        # [1000, 1100, 1200] -> [1100, 1200, None]
        assert projected_next[0] == 1100
        assert projected_next[1] == 1200
        assert projected_next[2] is None
```

### Step 2: Run test to verify it fails

Run: `uv run pytest tests/accessors/test_projection.py::TestNextPeriod -v`

Expected: FAIL with `AttributeError: 'ProjectionColumnAccessor' object has no attribute 'next_period'`

### Step 3: Write minimal implementation

Add to `gaspatchio_core/accessors/projection.py` after `previous_period()`:

```python
    def next_period(self, fill_value=0) -> ExpressionProxy:
        """Get value from next period (t+1).

        Equivalent to shifting forward one period. Less common than
        `previous_period()` but useful for certain actuarial calculations
        requiring forward-looking values.

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        Parameters
        ----------
        fill_value : scalar, optional
            Value to use for last period where no next value exists.
            Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values shifted from next period

        Examples
        --------
        **Basic Usage: Next Period Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"interest_rate": [[0.05, 0.06, 0.07]]}
        af = ActuarialFrame(data)

        af.rate_next = af.interest_rate.projection.next_period()

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌────────────────────┬───────────────────┐
        │ interest_rate      ┆ rate_next         │
        │ ---                ┆ ---               │
        │ list[f64]          ┆ list[f64]         │
        ╞════════════════════╪═══════════════════╡
        │ [0.05, 0.06, 0.07] ┆ [0.06, 0.07, 0.0] │
        └────────────────────┴───────────────────┘
        ```

        **Forward-Looking Calculation Example**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"cashflow": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # Compare current period to next period
        af.cf_next = af.cashflow.projection.next_period()
        af.cf_growth = af.cf_next - af.cashflow

        print(af.collect())
        ```

        ```text
        shape: (1, 3)
        ┌──────────────────┬─────────────────┬──────────────────┐
        │ cashflow         ┆ cf_next         ┆ cf_growth        │
        │ ---              ┆ ---             ┆ ---              │
        │ list[i64]        ┆ list[i64]       ┆ list[i64]        │
        ╞══════════════════╪═════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [1100, 1200, 0] ┆ [100, 100, -...] │
        └──────────────────┴─────────────────┴──────────────────┘
        ```

        See Also
        --------
        previous_period : Get value from previous period (t-1)
        at_period : Get value at arbitrary period offset

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        # Negative shift for forward direction
        shifted_expr = base_expr.shift(-1, fill_value=fill_value)

        parent_af = self._get_parent_frame()
        return ExpressionProxy(shifted_expr, parent_af)
```

### Step 4: Run test to verify it passes

Run: `uv run pytest tests/accessors/test_projection.py::TestNextPeriod -v`

Expected: All 2 tests PASS

### Step 5: Commit

```bash
git add tests/accessors/test_projection.py gaspatchio_core/accessors/projection.py
git commit -m "feat: add next_period() method for t+1 time-shifting

Add method for accessing next period values using t+1 notation. Less common
than previous_period() but useful for forward-looking calculations and
period-over-period comparisons.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Add `at_period()` Method

**Files:**
- Modify: `gaspatchio_core/accessors/projection.py:~900` (add after `next_period()`)
- Test: `tests/accessors/test_projection.py:~370` (add to test file)

### Step 1: Write the failing test

Add to `tests/accessors/test_projection.py` after `TestNextPeriod`:

```python
class TestAtPeriod:
    """Tests for at_period() method."""

    def test_negative_offset_t_minus_1(self):
        """Test at_period(-1) equivalent to previous_period()."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_t1 = af.value.projection.at_period(-1)

        result = af.collect()
        value_t1 = result["value_t1"][0]

        # at_period(-1) should match previous_period()
        # [100, 110, 120] -> [0, 100, 110]
        assert value_t1[0] == 0
        assert value_t1[1] == 100
        assert value_t1[2] == 110

    def test_negative_offset_t_minus_2(self):
        """Test at_period(-2) for two periods back."""
        data = {"reserve": [[1000, 1100, 1200, 1300]]}
        af = ActuarialFrame(data)

        af.reserve_t2 = af.reserve.projection.at_period(-2)

        result = af.collect()
        reserve_t2 = result["reserve_t2"][0]

        # [1000, 1100, 1200, 1300] -> [0, 0, 1000, 1100]
        assert reserve_t2[0] == 0
        assert reserve_t2[1] == 0
        assert reserve_t2[2] == 1000
        assert reserve_t2[3] == 1100

    def test_positive_offset_t_plus_1(self):
        """Test at_period(1) equivalent to next_period()."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_tp1 = af.value.projection.at_period(1)

        result = af.collect()
        value_tp1 = result["value_tp1"][0]

        # at_period(1) should match next_period()
        # [100, 110, 120] -> [110, 120, 0]
        assert value_tp1[0] == 110
        assert value_tp1[1] == 120
        assert value_tp1[2] == 0

    def test_positive_offset_t_plus_2(self):
        """Test at_period(2) for two periods ahead."""
        data = {"cashflow": [[1000, 1100, 1200, 1300]]}
        af = ActuarialFrame(data)

        af.cf_tp2 = af.cashflow.projection.at_period(2)

        result = af.collect()
        cf_tp2 = result["cf_tp2"][0]

        # [1000, 1100, 1200, 1300] -> [1200, 1300, 0, 0]
        assert cf_tp2[0] == 1200
        assert cf_tp2[1] == 1300
        assert cf_tp2[2] == 0
        assert cf_tp2[3] == 0

    def test_custom_fill_value(self):
        """Test at_period with custom fill value."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_t1 = af.value.projection.at_period(-1, fill_value=999)

        result = af.collect()
        value_t1 = result["value_t1"][0]

        # [100, 110, 120] -> [999, 100, 110]
        assert value_t1[0] == 999
        assert value_t1[1] == 100
        assert value_t1[2] == 110
```

### Step 2: Run test to verify it fails

Run: `uv run pytest tests/accessors/test_projection.py::TestAtPeriod -v`

Expected: FAIL with `AttributeError: 'ProjectionColumnAccessor' object has no attribute 'at_period'`

### Step 3: Write minimal implementation

Add to `gaspatchio_core/accessors/projection.py` after `next_period()`:

```python
    def at_period(self, relative_period: int, fill_value=0) -> ExpressionProxy:
        """Get value at relative period offset.

        Access values from other time periods using mathematical t notation.
        Negative values reference prior periods (t-1, t-2), positive values
        reference future periods (t+1, t+2).

        This method provides flexible time-shifting for arbitrary period offsets,
        complementing the convenience methods `previous_period()` (t-1) and
        `next_period()` (t+1).

        For list columns, shifts values within each list. For scalar columns,
        shifts across rows (use `.over()` for grouping).

        Parameters
        ----------
        relative_period : int
            Period offset from current time using mathematical notation:
            - Negative values: prior periods (e.g., -1 for t-1, -2 for t-2)
            - Positive values: future periods (e.g., 1 for t+1, 2 for t+2)
            - Zero: current period (no shift)
        fill_value : scalar, optional
            Value to use for missing entries at boundaries. Default is 0.

        Returns
        -------
        ExpressionProxy
            Expression with values from specified relative period

        Examples
        --------
        **Previous Period: t-1**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # at_period(-1) is equivalent to previous_period()
        af.reserve_t1 = af.reserve.projection.at_period(-1)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬──────────────────┐
        │ reserve          ┆ reserve_t1       │
        │ ---              ┆ ---              │
        │ list[i64]        ┆ list[i64]        │
        ╞══════════════════╪══════════════════╡
        │ [1000, 1100, ...] ┆ [0, 1000, 1100]  │
        └──────────────────┴──────────────────┘
        ```

        **Two Periods Back: t-2**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"value": [[100, 110, 120, 130, 140]]}
        af = ActuarialFrame(data)

        af.value_t2 = af.value.projection.at_period(-2)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────┬──────────────────────┐
        │ value                 ┆ value_t2             │
        │ ---                   ┆ ---                  │
        │ list[i64]             ┆ list[i64]            │
        ╞═══════════════════════╪══════════════════════╡
        │ [100, 110, 120, 13... ┆ [0, 0, 100, 110, 120]│
        └───────────────────────┴──────────────────────┘
        ```

        **Next Period: t+1**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"cashflow": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        # at_period(1) is equivalent to next_period()
        af.cf_tp1 = af.cashflow.projection.at_period(1)

        print(af.collect())
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬─────────────────┐
        │ cashflow         ┆ cf_tp1          │
        │ ---              ┆ ---             │
        │ list[i64]        ┆ list[i64]       │
        ╞══════════════════╪═════════════════╡
        │ [1000, 1100, ...] ┆ [1100, 1200, 0] │
        └──────────────────┴─────────────────┘
        ```

        **Reserve Rollforward Formula**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "reserve": [[0, 950, 1900, 2850]],
            "premium": [[1000, 1000, 1000, 1000]],
            "interest": [[50, 52, 55, 58]],
            "benefit": [[100, 102, 105, 108]],
        }
        af = ActuarialFrame(data)

        # Reserve rollforward: Reserve(t) = Reserve(t-1) + Premium(t) + Interest(t) - Benefit(t)
        af.reserve_t1 = af.reserve.projection.at_period(-1)
        af.reserve_calc = af.reserve_t1 + af.premium + af.interest - af.benefit

        print(af.collect())
        ```

        ```text
        shape: (1, 6)
        ┌─────────────────┬─────────────┬─────────┬─────────┬──────────┬──────────────┐
        │ reserve         ┆ premium     ┆ intere.. ┆ benefit ┆ reserve..┆ reserve_calc │
        │ ---             ┆ ---         ┆ ---     ┆ ---     ┆ ---      ┆ ---          │
        │ list[i64]       ┆ list[i64]   ┆ list..  ┆ list..  ┆ list[i64]┆ list[i64]    │
        ╞═════════════════╪═════════════╪═════════╪═════════╪══════════╪══════════════╡
        │ [0, 950, 1900...┆ [1000, 100..┆ [50, 52..┆ [100, ..┆ [0, 0, 9..┆ [950, 1900...│
        └─────────────────┴─────────────┴─────────┴─────────┴──────────┴──────────────┘
        ```

        See Also
        --------
        previous_period : Convenience method for t-1
        next_period : Convenience method for t+1

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        # Negate the period because Polars shift() uses opposite convention:
        # - shift(1) moves values back (lag/prior)
        # - shift(-1) moves values forward (lead/future)
        # We want at_period(-1) to mean "t-1" (prior), which is shift(1)
        shifted_expr = base_expr.shift(-relative_period, fill_value=fill_value)

        parent_af = self._get_parent_frame()
        return ExpressionProxy(shifted_expr, parent_af)
```

### Step 4: Run test to verify it passes

Run: `uv run pytest tests/accessors/test_projection.py::TestAtPeriod -v`

Expected: All 5 tests PASS

### Step 5: Commit

```bash
git add tests/accessors/test_projection.py gaspatchio_core/accessors/projection.py
git commit -m "feat: add at_period() method for flexible time-shifting

Add flexible time-shifting method using mathematical t notation. Supports
arbitrary period offsets where negative values mean prior periods (t-1, t-2)
and positive values mean future periods (t+1, t+2).

Complements previous_period() and next_period() for multi-period shifts.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Run Full Test Suite

**Files:**
- Test: All projection accessor tests

### Step 1: Run all projection tests

Run: `uv run pytest tests/accessors/test_projection.py -v`

Expected: All tests PASS (including new time-shifting tests)

### Step 2: Run docstring validation tests

Run: `uv run pytest gaspatchio_core/accessors/projection.py --doctest-modules -v`

Expected: All docstring examples execute and produce expected output

### Step 3: If docstring tests fail, update expectations

If Step 2 fails due to output formatting differences (not logic errors):

Run: `uv run pytest gaspatchio_core/accessors/projection.py --doctest-modules --accept`

This updates the expected outputs in docstrings to match actual output.

Then re-run Step 2 to verify.

### Step 4: Run type checking

Run both type checkers to ensure no type issues:

```bash
uv run mypy gaspatchio_core/accessors/projection.py
uv run pyright gaspatchio_core/accessors/projection.py
```

Expected: No type errors

### Step 5: Commit if docstrings were updated

If Step 3 was needed:

```bash
git add gaspatchio_core/accessors/projection.py
git commit -m "docs: update docstring test expectations for time-shifting methods

Update expected outputs from docstring examples to match actual formatting.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Update Type Stubs (if needed)

**Files:**
- Check: `gaspatchio_core/column/proxy.pyi` (may need updates)

### Step 1: Check if type stubs need updates

The new methods are on `ProjectionColumnAccessor`, which is accessed via the `.projection` accessor. Check if type hints are properly exposed:

Run: `uv run python -m mypy.stubtest gaspatchio_core --allowlist stubtest-allowlist.txt`

Expected: No errors related to `previous_period`, `next_period`, or `at_period`

### Step 2: If stubtest fails, update type stubs

If Step 1 shows missing type hints, update the relevant `.pyi` file to include the new methods.

**Note:** Based on the current codebase structure, the type stubs should auto-generate from the implementation, but verify this.

### Step 3: Re-run stubtest

Run: `uv run python -m mypy.stubtest gaspatchio_core --allowlist stubtest-allowlist.txt`

Expected: All checks PASS

### Step 4: Commit if stubs were updated

If Step 2 was needed:

```bash
git add gaspatchio_core/column/proxy.pyi
git commit -m "types: add type stubs for time-shifting methods

Add type hints for previous_period(), next_period(), and at_period() methods
in projection accessor.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Integration Test with Real Model Pattern

**Files:**
- Test: Create `tests/scratch/time_shifting_demo.py`

### Step 1: Write integration test showing real usage

Create `tests/scratch/time_shifting_demo.py`:

```python
# ABOUTME: Integration test demonstrating time-shifting API with real actuarial patterns.
# ABOUTME: Shows inforce rollforward, reserve calculations, and period comparisons.

"""Integration test for time-shifting methods in actuarial projections."""

from gaspatchio_core import ActuarialFrame


def test_inforce_rollforward_pattern():
    """Test complete inforce rollforward using previous_period."""
    data = {
        "policy_id": [1],
        "qx": [[0.001, 0.0011, 0.0012, 0.0013]],
        "lapse_rate": [[0.05, 0.05, 0.05, 0.05]],
    }
    af = ActuarialFrame(data)

    # Build survival and lapse decrements
    af.survival = af.qx.projection.cumulative_survival(start_at=1.0)
    af.pols_death = af.survival * af.qx

    # Calculate inforce using previous period pattern
    af.pols_if_prev = af.survival.projection.previous_period(fill_value=1.0)
    af.pols_lapse = af.pols_if_prev * af.lapse_rate

    result = af.collect()

    # Verify previous period shift worked correctly
    survival = result["survival"][0]
    pols_if_prev = result["pols_if_prev"][0]

    assert pols_if_prev[0] == 1.0  # Initial value
    assert pols_if_prev[1] == survival[0]  # Shifted from previous
    assert pols_if_prev[2] == survival[1]


def test_reserve_rollforward_formula():
    """Test reserve rollforward using at_period for t-1."""
    data = {
        "reserve": [[0, 950, 1900, 2850]],
        "premium": [[1000, 1000, 1000, 1000]],
        "interest_earned": [[50, 52, 55, 58]],
        "claims": [[100, 102, 105, 108]],
    }
    af = ActuarialFrame(data)

    # Reserve formula: Reserve(t) = Reserve(t-1) + Premium(t) + Interest(t) - Claims(t)
    af.reserve_t1 = af.reserve.projection.at_period(-1)
    af.reserve_calc = af.reserve_t1 + af.premium + af.interest_earned - af.claims

    result = af.collect()

    reserve_calc = result["reserve_calc"][0]
    reserve_actual = result["reserve"][0]

    # First period: Reserve(0) = 0 + 1000 + 50 - 100 = 950
    assert reserve_calc[0] == 950
    assert reserve_actual[1] == 950

    # Second period: Reserve(1) = 950 + 1000 + 52 - 102 = 1900
    assert reserve_calc[1] == 1900
    assert reserve_actual[2] == 1900


def test_period_over_period_comparison():
    """Test using at_period for multiple offset comparisons."""
    data = {
        "cashflow": [[1000, 1100, 1050, 1200, 1250]],
    }
    af = ActuarialFrame(data)

    # Calculate growth vs previous period
    af.cf_prev = af.cashflow.projection.previous_period()
    af.growth_1 = af.cashflow - af.cf_prev

    # Calculate growth vs two periods back
    af.cf_2_ago = af.cashflow.projection.at_period(-2)
    af.growth_2 = af.cashflow - af.cf_2_ago

    result = af.collect()

    growth_1 = result["growth_1"][0]
    growth_2 = result["growth_2"][0]

    # Period 1: 1100 - 1000 = 100
    assert growth_1[1] == 100

    # Period 2: 1050 - 1000 = 50 (comparing to 2 periods back)
    assert growth_2[2] == 50


if __name__ == "__main__":
    test_inforce_rollforward_pattern()
    test_reserve_rollforward_formula()
    test_period_over_period_comparison()
    print("All integration tests passed!")
```

### Step 2: Run integration test

Run: `uv run pytest tests/scratch/time_shifting_demo.py -v`

Expected: All 3 integration tests PASS

### Step 3: Commit integration test

```bash
git add tests/scratch/time_shifting_demo.py
git commit -m "test: add integration tests for time-shifting API

Add comprehensive integration tests showing real actuarial patterns:
- Inforce rollforward using previous_period()
- Reserve rollforward formula using at_period(-1)
- Period-over-period comparisons

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Update Documentation

**Files:**
- Modify: `project.md` (add time-shifting API to development workflow)

### Step 1: Add time-shifting API section to project.md

Add to `project.md` after the "Projection API" section (around line 74):

```markdown
### Time-Shifting Operations

The projection accessor provides actuarial-friendly methods for accessing values from other time periods:

```python
# Previous period (t-1) - most common case
af.reserve_prev = af.reserve.projection.previous_period()
af.pols_death_prev = af.pols_death.projection.previous_period(fill_value=0)

# Next period (t+1) - for forward-looking calculations
af.rate_next = af.interest_rate.projection.next_period()

# Arbitrary period offsets using mathematical t notation
af.reserve_t2 = af.reserve.projection.at_period(-2)  # t-2 (two periods ago)
af.projected = af.value.projection.at_period(3)      # t+3 (three periods ahead)
```

**Design Philosophy:**
- Use mathematical `t-1`, `t-2` notation (negative = prior, positive = future)
- Default `fill_value=0` for missing boundary values
- Methods make time-shifting transparent and auditable
- Replaces confusing `.shift()` with actuarial-friendly API
```

### Step 2: Verify documentation renders correctly

Read the updated file to ensure markdown formatting is correct:

Run: `cat project.md | grep -A 20 "Time-Shifting"`

Expected: Clean markdown with proper code blocks and formatting

### Step 3: Commit documentation update

```bash
git add project.md
git commit -m "docs: document time-shifting API in project.md

Add documentation for previous_period(), next_period(), and at_period()
methods with examples and design philosophy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Final Verification

**Files:**
- All project files

### Step 1: Run complete test suite

Run: `uv run pytest -v`

Expected: All tests PASS across entire codebase

### Step 2: Run type checking on entire package

```bash
uv run mypy gaspatchio_core
uv run pyright gaspatchio_core
```

Expected: No type errors

### Step 3: Verify git status is clean

Run: `git status`

Expected: Working tree clean, all changes committed

### Step 4: Review commit history

Run: `git log --oneline -8`

Expected: See 7 commits (or fewer if some were combined):
1. Add previous_period()
2. Add next_period()
3. Add at_period()
4. Update docstring expectations (if needed)
5. Update type stubs (if needed)
6. Add integration tests
7. Update documentation

---

## Success Criteria

- ✅ All three methods (`previous_period()`, `next_period()`, `at_period()`) implemented
- ✅ Comprehensive unit tests with edge cases
- ✅ Integration tests showing real actuarial patterns
- ✅ Complete docstrings with examples
- ✅ All docstring examples validated by pytest
- ✅ Type checking passes (mypy and pyright)
- ✅ Type stubs match implementation
- ✅ Documentation updated in project.md
- ✅ All tests pass
- ✅ Clean commit history with descriptive messages

---

## Notes for Implementation

**Key Design Decisions:**

1. **Sign Convention:** `at_period(-1)` means `t-1` (prior), which internally calls `.shift(1)` because Polars uses opposite convention

2. **Default fill_value=0:** Most actuarial calculations use 0 for missing boundary values (first period has no previous reserve, etc.)

3. **Placement:** All methods on `ProjectionColumnAccessor` for discoverability via `af.column.projection.<TAB>`

4. **Relationship to existing methods:** Complements `cumulative_survival(start_at=...)` which elegantly handles BOP/EOP without explicit shifts

5. **Testing Strategy:** Follow TDD strictly - failing test first, minimal implementation, then refine

**Common Pitfalls:**

- Remember to negate `relative_period` in `at_period()` due to Polars' opposite sign convention
- Ensure docstring examples use realistic actuarial patterns, not toy data
- Test both list columns (most common) and scalar columns (with `.over()` grouping)
- Verify fill_value works with None, 0, and custom numeric values

**References:**

- Design discussion: `bindings/python/ref/22-api-design/22-brainstorm.md`
- Existing projection accessor: `gaspatchio_core/accessors/projection.py`
- Existing tests: `tests/accessors/test_projection.py`

---

## Related Work

### Task 5: List Broadcasting in Debug Mode (Completed 2025-11-11)

After implementing the time-shifting API, we completed Task 5 to enable list broadcasting
conditionals in debug/tracing mode. Previously, when-then-otherwise expressions with list
columns would fail with NotImplementedError in debug mode.

The solution uses eager execution: the explode/re-aggregate pattern executes immediately
in debug mode and captures a TracedOperation for the computation graph. This enables
step-by-step debugging of actuarial models with projection periods.

See: `docs/plans/2025-11-11-task5-list-broadcasting-tracing.md`
