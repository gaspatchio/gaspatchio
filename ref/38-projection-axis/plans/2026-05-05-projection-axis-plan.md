# Projection Axis API Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `af.date.create_projection_timeline(...)` and direct user-facing use of `Schedule.from_*(...)` constructors with a single unified `af.projection.set(...)` verb that both the actuary and the rollforward kernel read from.

**Architecture:** Add a private `_projection: Schedule | None` slot to `ActuarialFrame`, plumbed through frame operations. Add `set(...)` and lazy accessor methods (`period_dates`, `year_fractions`, `t_years`, `anniversary_mask`, `is_in_force`, `contract_boundary`, `canonical_form`, `source_sha`) to the existing `ProjectionFrameAccessor`. Modify the user-facing `af.projection.rollforward(...)` to read the schedule from the frame; `RollforwardBuilder`'s internal `schedule=` kwarg stays unchanged (only ~2 tests use the user-facing path; the internal API tests stay untouched). Delete `af.date.create_projection_timeline(...)` outright (pre-release, no shim).

**Tech Stack:** Python 3.12, Polars (LazyFrame + expressions), PyO3 + Rust core, pytest, ruff, maturin.

**Spec:** `ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md`
**Migration companion:** `ref/38-projection-axis/migration.md`
**Branch:** `gsp-92-rollforward-redesign` (continuation)

---

## File structure overview

**Files created:**
- `bindings/python/tests/schedule/test_next_anniversary.py` — tests for `Schedule.next_anniversary_date()` helper
- `bindings/python/tests/schedule/test_is_in_force_expr.py` — tests for `Schedule.is_in_force_expr()`
- `bindings/python/tests/frame/test_projection_slot.py` — tests for `ActuarialFrame._projection` slot preservation
- `bindings/python/tests/accessors/test_projection_set.py` — tests for `af.projection.set(...)`
- `bindings/python/tests/accessors/test_projection_lazy_methods.py` — tests for the five lazy accessor methods + governance hooks
- `bindings/python/tests/accessors/test_projection_rollforward_integration.py` — tests for accessor reading schedule from frame
- `bindings/python/tests/migration/__init__.py` — empty init
- `bindings/python/tests/migration/test_create_projection_timeline_removed.py` — locks in the breakage of the deleted method

**Files modified:**
- `bindings/python/gaspatchio_core/schedule/_schedule.py` — add `next_anniversary_date()`, `is_in_force_expr()`
- `bindings/python/gaspatchio_core/schedule/__init__.pyi` — sync stubs
- `bindings/python/gaspatchio_core/frame/base.py` — add `_projection` slot + clone helper
- `bindings/python/gaspatchio_core/accessors/projection_frame.py` — add `set()`, lazy methods, modify `rollforward()`
- `bindings/python/gaspatchio_core/accessors/projection_frame.pyi` — sync stubs (or add new file if not present)
- `bindings/python/gaspatchio_core/accessors/date.py` — delete `create_projection_timeline`
- `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/01-projections/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/02-survival/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/03-time-shifting/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/steps/*/model.py` — migrate (all six steps)
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/base/model.py` — migrate (typed path)
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/steps/*/model.py` — migrate (typed path)
- `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/*/model.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/**/*.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/01_single_state_fund.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/02_multistate_ratchet.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/03_lapse_stop.py` — migrate
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/README.md` — drop the off-by-one footgun bullet
- `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/README.md` — update examples
- `bindings/python/tests/accessors/test_dates.py` — remove `create_projection_timeline` tests
- `bindings/python/tests/integration/test_variable_projection.py` — migrate
- `bindings/python/tests/rollforward/test_va_acceptance.py` — migrate to use `af.projection.set()` + explicit `contract_boundary=`
- `bindings/python/tests/rollforward/test_projection_accessor.py` — migrate

**Files NOT modified (intentional):**
- `bindings/python/gaspatchio_core/rollforward/_builder.py` — `RollforwardBuilder` constructor stays as-is. The 24 test files that use `RollforwardBuilder(schedule=...)` directly continue to work unchanged.
- `bindings/python/gaspatchio_core/rollforward/_ir.py` — IR still holds `Schedule`, no change.
- `core/src/polars_functions/rollforward.rs` — kernel unchanged.

---

## Pre-flight: branch confirmation

- [ ] **Step 0.1: Confirm branch and clean working tree**

```bash
cd .
git status --short
git branch --show-current
```

Expected: branch is `gsp-92-rollforward-redesign`. Working tree may have stray report regenerations under `tutorials/level-5-scenarios/` (those are not from this work and should be left alone OR stashed before starting).

If working tree is dirty with non-related files, stash them:

```bash
git stash push -m "pre-projection-axis-stash" -- bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/report \
    bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/01-parameter-shocks/report \
    bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/02-conditional-shocks/report \
    bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/03-sensitivity/report \
    bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/04-scenario-comparison/report
```

---

## Phase 1: Schedule extensions (additive, no API breakage)

These steps add new helpers to `Schedule` without changing any existing behaviour. Tests pass after each task.

### Task 1: `Schedule.next_anniversary_date(valuation_date, n=1)`

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Test: `bindings/python/tests/schedule/test_next_anniversary.py` (new)

- [ ] **Step 1.1: Write the failing test**

Create file `bindings/python/tests/schedule/test_next_anniversary.py`:

```python
"""Tests for Schedule.next_anniversary_date()."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule import Schedule


class TestNextAnniversaryDate:
    """next_anniversary_date(valuation_date, n) returns the Nth anniversary on/after valuation."""

    def test_n_equals_one_returns_next_anniversary(self) -> None:
        # Inception 2020-06-15; valuation 2025-01-01; n=1 → 2025-06-15
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 1, 1),
            n=1,
        )
        assert result == date(2025, 6, 15)

    def test_valuation_on_anniversary_returns_same_date(self) -> None:
        # Inception 2020-06-15; valuation 2025-06-15; n=1 → 2025-06-15 (on/after)
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 6, 15),
            n=1,
        )
        assert result == date(2025, 6, 15)

    def test_n_equals_two_returns_anniversary_after_next(self) -> None:
        # Inception 2020-06-15; valuation 2025-01-01; n=2 → 2026-06-15
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 6, 15),
            valuation_date=date(2025, 1, 1),
            n=2,
        )
        assert result == date(2026, 6, 15)

    def test_leap_year_inception(self) -> None:
        # Feb 29 inception; year 2025 has no Feb 29 → falls to Feb 28
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        result = sched.next_anniversary_date(
            inception=date(2020, 2, 29),
            valuation_date=date(2024, 12, 1),
            n=1,
        )
        assert result == date(2025, 2, 28)

    def test_n_zero_raises(self) -> None:
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=120,
            frequency="1M",
        )
        with pytest.raises(ValueError, match="n must be >= 1"):
            sched.next_anniversary_date(
                inception=date(2020, 6, 15),
                valuation_date=date(2025, 1, 1),
                n=0,
            )

    def test_only_valid_for_from_inception(self) -> None:
        # from_calendar_grid schedules don't have an inception anchor
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(ValueError, match="from_inception"):
            sched.next_anniversary_date(
                inception=date(2020, 6, 15),
                valuation_date=date(2025, 1, 1),
                n=1,
            )
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd .
uv run pytest bindings/python/tests/schedule/test_next_anniversary.py -v
```

Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'next_anniversary_date'`

- [ ] **Step 1.3: Add the helper to Schedule**

Edit `bindings/python/gaspatchio_core/schedule/_schedule.py`. Add this method to the `Schedule` class (place it after `anniversary_mask_expr` at line 555 to group with anniversary helpers):

```python
def next_anniversary_date(
    self,
    *,
    inception: date,
    valuation_date: date,
    n: int = 1,
) -> date:
    """Return the Nth contract anniversary on/after ``valuation_date``.

    Anchored on ``inception``. Anniversaries are calendar-month-day matches.
    Feb 29 inceptions in non-leap target years fall to Feb 28.

    Only valid for ``from_inception`` schedules — ``from_calendar_grid`` has
    no per-policy anchor.

    Args:
        inception: The contract inception date for one policy.
        valuation_date: The reference date; the returned anniversary is
            on or after this date.
        n: 1 = next anniversary on/after valuation; 2 = anniversary after
            that; etc. Must be >= 1.

    Returns:
        The anniversary date. May equal ``valuation_date`` if that day is
        itself an anniversary.

    Raises:
        ValueError: If ``n < 1`` or if the schedule is not ``from_inception``.

    """
    if self._kind != "from_inception":
        msg = (
            "next_anniversary_date is only valid for from_inception schedules"
        )
        raise ValueError(msg)
    if n < 1:
        msg = f"n must be >= 1, got {n}"
        raise ValueError(msg)

    # Find the most recent anniversary on/before valuation_date,
    # then add (n) full years on top.
    val_year = valuation_date.year
    incep_month = inception.month
    incep_day = inception.day

    # Candidate anniversary in val_year:
    candidate = _safe_anniversary(val_year, incep_month, incep_day)
    if candidate >= valuation_date:
        # Anniversary in val_year is the "next" one — add (n-1) years.
        years_to_add = n - 1
    else:
        # Anniversary in val_year already passed — add n years.
        years_to_add = n
    return _safe_anniversary(
        val_year + years_to_add, incep_month, incep_day,
    )
```

Then add this private helper near the top of the file (after `_last_day_of_year` at line 84):

```python
def _safe_anniversary(year: int, month: int, day: int) -> date:
    """Return ``date(year, month, day)``, or Feb 28 if Feb 29 in a non-leap year."""
    if month == 2 and day == 29 and not _stdlib_calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/schedule/test_next_anniversary.py -v
```

Expected: 6 PASS.

- [ ] **Step 1.5: Run full schedule test suite for regression check**

```bash
cd .
uv run pytest bindings/python/tests/schedule/ -v
```

Expected: all schedule tests PASS (no regression in the existing 50+ schedule tests).

- [ ] **Step 1.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_next_anniversary.py
git commit -m "feat(schedule): add next_anniversary_date(valuation_date, n) helper

Returns the Nth contract anniversary on/after a reference valuation date,
anchored on inception. Feb 29 inceptions in non-leap target years fall to
Feb 28 (standard actuarial convention).

Backs the upcoming until=\"next_anniversary\" path on af.projection.set().
Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §3.2"
```

---

### Task 2: `Schedule.is_in_force_expr()`

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Test: `bindings/python/tests/schedule/test_is_in_force_expr.py` (new)

- [ ] **Step 2.1: Write the failing test**

Create file `bindings/python/tests/schedule/test_is_in_force_expr.py`:

```python
"""Tests for Schedule.is_in_force_expr() — the per-period boundary mask."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.schedule import Schedule


class TestIsInForceExpr:
    """is_in_force_expr() returns a List<Boolean> of length n_periods."""

    def test_from_calendar_grid_all_true_when_no_end(self) -> None:
        """With no end_date, every period is in-force."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=4,
            frequency="1M",
        )
        df = pl.DataFrame({"id": ["P1"]}).lazy()
        df = df.with_columns(in_force=sched.is_in_force_expr())
        result = df.collect()["in_force"].to_list()
        assert result == [[True, True, True, True]]

    def test_from_inception_truncates_at_end_date(self) -> None:
        """Per-policy: each row's mask reflects its end_date column."""
        sched = Schedule.from_inception(
            inception_column="incep",
            n_periods=6,
            frequency="1M",
        )
        df = pl.DataFrame({
            "incep": [date(2025, 1, 31), date(2025, 1, 31)],
            "end_date": [date(2025, 4, 30), date(2025, 6, 30)],
        }).lazy()
        df = df.with_columns(in_force=sched.is_in_force_expr(end_date_column="end_date"))
        result = df.collect()["in_force"].to_list()
        # First policy ends 2025-04-30: periods covering Feb, Mar, Apr in-force; May, Jun, Jul out
        # Second policy ends 2025-06-30: Feb-Jun in-force; Jul out
        assert result[0] == [True, True, True, False, False, False]
        assert result[1] == [True, True, True, True, True, False]

    def test_length_matches_n_periods(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=10,
            frequency="1M",
        )
        df = pl.DataFrame({"id": ["P1"]}).lazy()
        df = df.with_columns(in_force=sched.is_in_force_expr())
        result = df.collect()["in_force"].to_list()
        assert len(result[0]) == 10
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd .
uv run pytest bindings/python/tests/schedule/test_is_in_force_expr.py -v
```

Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'is_in_force_expr'`

- [ ] **Step 2.3: Add the method to Schedule**

Edit `bindings/python/gaspatchio_core/schedule/_schedule.py`. Add this method to the `Schedule` class (place it after `anniversary_mask_expr`, after the `next_anniversary_date` from Task 1):

```python
def is_in_force_expr(
    self,
    *,
    end_date_column: str | None = None,
) -> pl.Expr:
    """Return a per-row boolean list expression marking in-force periods.

    Length per row: ``n_periods``. ``True`` at index ``t`` means period ``t``
    is in force (the contract has not yet terminated).

    Args:
        end_date_column: For ``from_inception`` schedules, optional column
            name holding each policy's end date. If provided, periods whose
            end-of-period date falls strictly after this date are False.
            If omitted, all periods are True.
            Ignored for ``from_calendar_grid`` schedules (which have no
            per-policy boundary).

    Returns:
        A Polars expression of type ``List<Boolean>`` with length
        ``n_periods`` per row.

    """
    n = self.n_periods

    if self._kind == "from_calendar_grid":
        # No per-policy end — broadcast a uniform True mask
        mask = [True] * n
        return pl.lit(mask, dtype=pl.List(pl.Boolean))

    # from_inception path
    if end_date_column is None:
        # No end specified — uniform True mask
        mask = [True] * n
        return pl.lit(mask, dtype=pl.List(pl.Boolean))

    if self.inception_column is None:
        msg = "from_inception Schedule has no inception_column"
        raise RuntimeError(msg)  # unreachable given _kind invariant

    # Compute per-period end dates: incep + offset_str(frequency, t+1)
    # for t in 0..n-1, then compare each to the policy's end_date.
    period_end_exprs = [
        pl.col(self.inception_column).dt.offset_by(_offset_str(self.frequency, t + 1))
        for t in range(n)
    ]
    end_col = pl.col(end_date_column)
    # For each period: True if its end-of-period date <= policy end_date
    mask_exprs = [pe <= end_col for pe in period_end_exprs]
    return pl.concat_list(mask_exprs)
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/schedule/test_is_in_force_expr.py -v
```

Expected: 3 PASS.

- [ ] **Step 2.5: Run full schedule test suite**

```bash
cd .
uv run pytest bindings/python/tests/schedule/ -v
```

Expected: all PASS.

- [ ] **Step 2.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_is_in_force_expr.py
git commit -m "feat(schedule): add is_in_force_expr(end_date_column) boundary mask helper

Returns a per-row List<Boolean> of length n_periods marking periods where
the contract is still in force, derived from an optional end_date column.
Used as the contract_boundary mask the rollforward kernel reads.

Backs the upcoming af.projection.is_in_force() accessor method.
Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §4.2"
```

---

### Task 3: Sync Schedule pyi stubs

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/__init__.pyi`

- [ ] **Step 3.1: Read the existing stub**

```bash
cd .
cat bindings/python/gaspatchio_core/schedule/__init__.pyi
```

- [ ] **Step 3.2: Add stubs for the two new methods**

Edit `bindings/python/gaspatchio_core/schedule/__init__.pyi`. Locate the `class Schedule:` block and add these stubs (place after `anniversary_mask_expr` to keep grouping):

```python
    def next_anniversary_date(
        self,
        *,
        inception: date,
        valuation_date: date,
        n: int = ...,
    ) -> date: ...
    def is_in_force_expr(
        self,
        *,
        end_date_column: str | None = ...,
    ) -> pl.Expr: ...
```

- [ ] **Step 3.3: Run stub-sync test**

```bash
cd .
uv run pytest bindings/python/tests/test_stub_sync.py -v
```

Expected: PASS (stubs match implementation).

- [ ] **Step 3.4: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/schedule/__init__.pyi
git commit -m "chore(schedule): sync pyi stubs for next_anniversary_date + is_in_force_expr"
```

---

## Phase 2: ActuarialFrame `_projection` slot

### Task 4: Add `_projection` slot to ActuarialFrame

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`
- Test: `bindings/python/tests/frame/test_projection_slot.py` (new)

- [ ] **Step 4.1: Write the failing test**

Create file `bindings/python/tests/frame/test_projection_slot.py`:

```python
"""Tests for ActuarialFrame._projection slot — preservation through frame operations."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


def _make_sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestProjectionSlot:
    """The _projection slot exists on every ActuarialFrame and starts as None."""

    def test_default_is_none(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        assert af._projection is None

    def test_set_via_helper(self) -> None:
        """The internal _set_projection helper updates the slot and returns a new frame."""
        af = ActuarialFrame({"id": ["P1"]})
        sched = _make_sched()
        new_af = af._set_projection(sched)
        # New frame has the slot; original unchanged
        assert new_af._projection is sched
        assert af._projection is None

    def test_preserved_through_with_columns(self) -> None:
        """with_columns returns a new frame that preserves the projection slot."""
        af = ActuarialFrame({"id": ["P1"], "x": [1.0]})
        sched = _make_sched()
        af = af._set_projection(sched)
        af2 = af.with_columns(pl.col("x").alias("y"))
        assert af2._projection is sched
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd .
uv run pytest bindings/python/tests/frame/test_projection_slot.py -v
```

Expected: FAIL — `_projection` attribute and `_set_projection` method don't exist.

- [ ] **Step 4.3: Add the slot and helper to ActuarialFrame**

Edit `bindings/python/gaspatchio_core/frame/base.py`. In the `ActuarialFrame.__init__` method (around line 216), add to the initialization list. Place this after the existing tracing attribute initialisation (around line 234, after `self._tracing: bool = False`):

```python
        # Projection metadata — populated by af.projection.set(...)
        self._projection: object | None = None
```

Then add a private helper method on `ActuarialFrame` (place near `with_columns` at line 475, BEFORE the `with_columns` method definition):

```python
    def _set_projection(self, schedule):  # type: ignore[no-untyped-def]
        """Internal: return a new frame carrying ``schedule`` in ``_projection``.

        Used by ``ProjectionFrameAccessor.set(...)``. Not part of the public API.
        """
        # Construct a new frame from the same lazy plan, copy state.
        new_af = ActuarialFrame(self._df)
        new_af._projection = schedule  # noqa: SLF001
        new_af._mode = self._mode  # noqa: SLF001
        new_af._verbose = self._verbose  # noqa: SLF001
        new_af._threads = self._threads  # noqa: SLF001
        return new_af
```

**Note on `with_columns` preservation:** `ActuarialFrame.with_columns` (line 475) mutates `self._df` in place and returns `self` — see line 517: `return self`. So `_projection` is preserved trivially through `with_columns` *without any modification needed*. No edit to `with_columns` is required.

Other operations that construct new ActuarialFrame instances (e.g., `af.date.create_timeline`, `af.date.add_duration`) currently do NOT preserve `_projection`. Spec §4.4 documents this as TBD-conservative-clear; we accept the lossy behaviour for those operations under this spec since they are not part of the standard projection→rollforward flow. The test below verifies the headline `with_columns` case.

- [ ] **Step 4.4: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/frame/test_projection_slot.py -v
```

Expected: 3 PASS.

- [ ] **Step 4.5: Run full frame test suite**

```bash
cd .
uv run pytest bindings/python/tests/frame/ -v
```

Expected: all PASS (no regression).

- [ ] **Step 4.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/frame/base.py bindings/python/tests/frame/test_projection_slot.py
git commit -m "feat(frame): add _projection slot to ActuarialFrame

Private slot holding a Schedule | None for projection metadata.
Preserved through frame operations like with_columns.

Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §4.4"
```

---

## Phase 3: `af.projection.set(...)` and lazy methods

### Task 5: `af.projection.set(...)` — the kwargs path

**Files:**
- Modify: `bindings/python/gaspatchio_core/accessors/projection_frame.py`
- Test: `bindings/python/tests/accessors/test_projection_set.py` (new)

- [ ] **Step 5.1: Write the failing tests**

Create file `bindings/python/tests/accessors/test_projection_set.py`:

```python
"""Tests for af.projection.set(...) — kwargs and Schedule paths."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


class TestSetKwargsPath:
    """set() with valuation_date + until + until_value + frequency."""

    def test_maximum_age_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="maximum_age",
            until_value=100,
            frequency="monthly",
        )
        # Eager stamps present
        result = af.collect()
        assert "projection_start_date" in result.columns
        assert "projection_end_date" in result.columns
        assert "num_proj_months" in result.columns
        # Frame carries projection metadata
        assert af._projection is not None
        # 70 years × 12 months
        assert result["num_proj_months"][0] == 70 * 12 + 1  # +1 for start boundary

    def test_term_years_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 10 * 12 + 1

    def test_term_months_uniform(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value=24,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 24 + 1

    def test_term_months_per_policy_via_column(self) -> None:
        """Per-policy until_value: n_periods is uniform max across rows.

        Per spec §3 settled position 3 (deferred to GSP-97), the kernel
        uses uniform max n_periods + boundary mask. So num_proj_months
        column is uniform max+1 = 37 for both policies. Per-policy
        boundaries are expressed via af.projection.is_in_force(...).
        """
        af = ActuarialFrame({
            "policy_id": ["P1", "P2"],
            "remaining": [12, 36],
        })
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_months",
            until_value="remaining",
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"].to_list() == [37, 37]

    def test_fixed_date(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="fixed_date",
            until_value=date(2026, 1, 1),
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 13


class TestSetSchedulePath:
    """set(schedule=Schedule.from_*(...)) accepts a pre-built Schedule."""

    def test_from_calendar_grid(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame({"policy_id": ["P1"]})
        af = af.projection.set(schedule=sched)
        assert af._projection is sched
        result = af.collect()
        assert "projection_start_date" in result.columns

    def test_from_inception(self) -> None:
        sched = Schedule.from_inception(
            inception_column="policy_inception",
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame({
            "policy_id": ["P1"],
            "policy_inception": [date(2020, 6, 15)],
        })
        af = af.projection.set(schedule=sched)
        assert af._projection is sched


class TestSetMutualExclusion:
    """schedule= cannot be combined with kwargs."""

    def test_schedule_with_kwargs_raises(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af = ActuarialFrame({"policy_id": ["P1"]})
        with pytest.raises(ValueError, match="schedule= cannot be combined"):
            af.projection.set(
                schedule=sched,
                valuation_date=date(2025, 1, 1),
                until="term_years",
                until_value=10,
                frequency="monthly",
            )


class TestSetReturnsBehaviour:
    """set() returns a new frame; original is unchanged."""

    def test_returns_new_frame_original_untouched(self) -> None:
        af1 = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af2 = af1.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        assert af1 is not af2
        assert af1._projection is None
        assert af2._projection is not None

    def test_recall_replaces_projection(self) -> None:
        af = ActuarialFrame({"policy_id": ["P1"], "issue_age": [30]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=10,
            frequency="monthly",
        )
        sched1 = af._projection
        af = af.projection.set(
            valuation_date=date(2025, 1, 1),
            until="term_years",
            until_value=20,
            frequency="monthly",
        )
        assert af._projection is not sched1
        assert af.collect()["num_proj_months"][0] == 20 * 12 + 1


class TestSetSyntheticPath:
    """set() with start_date + n_periods + frequency for no-policy use."""

    def test_synthetic(self) -> None:
        af = ActuarialFrame({"id": ["demo"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=10,
            frequency="monthly",
        )
        result = af.collect()
        assert result["num_proj_months"][0] == 11


class TestSetFrequencyVocab:
    """Both English and Schedule-shorthand vocabs accepted."""

    def test_english_monthly(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        assert af._projection.frequency == "1M"

    def test_shorthand_1M(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        assert af._projection.frequency == "1M"

    def test_english_annual(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        af = af.projection.set(
            start_date=date(2025, 1, 1),
            n_periods=10,
            frequency="annual",
        )
        assert af._projection.frequency == "1Y"
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
cd .
uv run pytest bindings/python/tests/accessors/test_projection_set.py -v
```

Expected: FAIL — `AttributeError: 'ProjectionFrameAccessor' object has no attribute 'set'`

- [ ] **Step 5.3: Implement `set()`**

Edit `bindings/python/gaspatchio_core/accessors/projection_frame.py`. Replace the file contents with:

```python
# ABOUTME: Frame-level projection accessor — set() unifies projection axis setup.
# ABOUTME: rollforward() reads schedule from frame; both go through this accessor.

"""Frame-level projection accessor for actuarial projection setup."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Literal, Union

import polars as pl

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame


# English-frequency → Schedule frequency mapping.
_ENGLISH_TO_SCHED_FREQ: dict[str, str] = {
    "monthly": "1M",
    "quarterly": "3M",
    "semi-annual": "6M",
    "annual": "1Y",
    "weekly": "1W",
    "daily": "1D",
}
_VALID_SCHED_FREQ: frozenset[str] = frozenset({"1M", "3M", "6M", "1Y", "1W", "1D"})


def _normalise_frequency(freq: str) -> str:
    """Map English vocab to Schedule shorthand, or pass shorthand through."""
    if freq in _ENGLISH_TO_SCHED_FREQ:
        return _ENGLISH_TO_SCHED_FREQ[freq]
    if freq in _VALID_SCHED_FREQ:
        return freq
    valid = sorted(set(_ENGLISH_TO_SCHED_FREQ) | _VALID_SCHED_FREQ)
    msg = f"unsupported frequency {freq!r}; expected one of {valid}"
    raise ValueError(msg)


@register_accessor("projection", kind="frame")
class ProjectionFrameAccessor(BaseFrameAccessor):
    """Frame-level accessor for actuarial projection operations.

    Two verbs:
      - ``set(...)`` — declare the projection time axis on the frame
      - ``rollforward(...)`` — construct a state-machine rollforward
        builder that reads the projection from this frame
    """

    def __init__(self, frame: ActuarialFrame) -> None:
        super().__init__(frame)

    def set(  # noqa: PLR0913
        self,
        *,
        # Schedule path (mutually exclusive with the rest)
        schedule: Schedule | None = None,
        # Kwargs path — policy-anchored
        valuation_date: dt.date | None = None,
        until: Literal["maximum_age", "term_years", "term_months", "fixed_date", "next_anniversary"] | None = None,
        until_value: int | dt.date | str | pl.Expr | None = None,
        issue_age_column: str = "issue_age",
        inception_column: str = "policy_inception",
        # Kwargs path — synthetic
        start_date: dt.date | None = None,
        n_periods: int | None = None,
        # Common
        frequency: str | None = None,
    ) -> ActuarialFrame:
        """Declare the projection time axis on this frame.

        See ref/38-projection-axis/specs for full semantics.
        """
        # Mutual exclusion check
        kwargs_provided = any(
            v is not None
            for v in (valuation_date, until, until_value, start_date, n_periods)
        )
        if schedule is not None and kwargs_provided:
            msg = (
                "schedule= cannot be combined with valuation_date / until / "
                "start_date / n_periods. Pass either a Schedule object OR "
                "construction kwargs, not both."
            )
            raise ValueError(msg)

        if schedule is None:
            schedule = self._build_schedule(
                valuation_date=valuation_date,
                until=until,
                until_value=until_value,
                issue_age_column=issue_age_column,
                inception_column=inception_column,
                start_date=start_date,
                n_periods=n_periods,
                frequency=frequency,
            )

        return self._stamp_eager_columns(schedule)

    def _build_schedule(  # noqa: PLR0913
        self,
        *,
        valuation_date: dt.date | None,
        until: str | None,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        inception_column: str,
        start_date: dt.date | None,
        n_periods: int | None,
        frequency: str | None,
    ) -> Schedule:
        """Construct a Schedule from the kwargs path."""
        if frequency is None:
            msg = "frequency is required"
            raise ValueError(msg)
        sched_freq = _normalise_frequency(frequency)

        # Synthetic case: start_date + n_periods
        if start_date is not None and n_periods is not None:
            return Schedule.from_calendar_grid(
                start_date=start_date,
                n_periods=n_periods,
                frequency=sched_freq,  # type: ignore[arg-type]
            )

        # Policy-anchored case: valuation_date + until + until_value
        if valuation_date is None or until is None or until_value is None:
            msg = (
                "Either provide schedule=, "
                "OR start_date+n_periods+frequency (synthetic), "
                "OR valuation_date+until+until_value+frequency (policy-anchored)."
            )
            raise ValueError(msg)

        # Compute n_periods from the until specification.
        # Anchor: valuation_date is the schedule start.
        n_per = self._compute_n_periods(
            valuation_date=valuation_date,
            until=until,
            until_value=until_value,
            issue_age_column=issue_age_column,
            inception_column=inception_column,
            sched_freq=sched_freq,
        )
        return Schedule.from_calendar_grid(
            start_date=valuation_date,
            n_periods=n_per,
            frequency=sched_freq,  # type: ignore[arg-type]
        )

    def _compute_n_periods(  # noqa: PLR0913
        self,
        *,
        valuation_date: dt.date,
        until: str,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        inception_column: str,  # noqa: ARG002 — used in next_anniversary path
        sched_freq: str,
    ) -> int:
        """Compute uniform n_periods. Per-policy until_value resolved at frame stamp time."""
        # Periods-per-year by frequency
        periods_per_year = {"1M": 12, "3M": 4, "6M": 2, "1Y": 1, "1W": 52, "1D": 365}
        ppy = periods_per_year[sched_freq]

        if until == "term_months":
            if isinstance(until_value, int):
                # uniform months → months / (12/ppy) periods
                months = until_value
                if sched_freq == "1M":
                    return months
                if sched_freq == "1Y":
                    return months // 12
                # for 3M/6M, months must align
                step_months = {"3M": 3, "6M": 6}.get(sched_freq, 1)
                return months // step_months
            # per-policy: use the maximum across the column for the uniform schedule;
            # is_in_force masks each policy to its own length.
            af_df = self._frame._df  # noqa: SLF001
            if isinstance(until_value, str):
                series = af_df.select(pl.col(until_value).max()).collect()[0, 0]
            else:  # pl.Expr
                series = af_df.select(until_value.max()).collect()[0, 0]
            months = int(series)
            if sched_freq == "1M":
                return months
            if sched_freq == "1Y":
                return months // 12
            step_months = {"3M": 3, "6M": 6}.get(sched_freq, 1)
            return months // step_months
        if until == "term_years":
            if isinstance(until_value, int):
                return until_value * ppy
            af_df = self._frame._df  # noqa: SLF001
            if isinstance(until_value, str):
                series = af_df.select(pl.col(until_value).max()).collect()[0, 0]
            else:
                series = af_df.select(until_value.max()).collect()[0, 0]
            return int(series) * ppy
        if until == "fixed_date":
            if not isinstance(until_value, dt.date):
                msg = "until_value must be datetime.date for until='fixed_date'"
                raise TypeError(msg)
            # Months between
            months = (until_value.year - valuation_date.year) * 12 + (
                until_value.month - valuation_date.month
            )
            if sched_freq == "1M":
                return months
            if sched_freq == "1Y":
                return months // 12
            step_months = {"3M": 3, "6M": 6}.get(sched_freq, 1)
            return months // step_months
        if until == "maximum_age":
            # Need (max_age - issue_age) years; resolve from frame.
            af_df = self._frame._df  # noqa: SLF001
            if isinstance(until_value, int):
                # uniform max age — read max issue_age, compute tail years
                max_issue = af_df.select(pl.col(issue_age_column).max()).collect()[0, 0]
                years = until_value - int(max_issue)
            elif isinstance(until_value, str):
                # per-policy max-age column — compute max(target - issue)
                expr = pl.col(until_value) - pl.col(issue_age_column)
                years = int(af_df.select(expr.max()).collect()[0, 0])
            else:  # pl.Expr
                expr = until_value - pl.col(issue_age_column)
                years = int(af_df.select(expr.max()).collect()[0, 0])
            return years * ppy
        if until == "next_anniversary":
            # n_value = the integer "next anniversary" count (1, 2, ...)
            # n_periods = n_value years × periods-per-year (uniform max).
            if isinstance(until_value, int):
                n_value = until_value
            else:
                # per-policy: read max for uniform schedule
                af_df = self._frame._df  # noqa: SLF001
                if isinstance(until_value, str):
                    n_value = int(af_df.select(pl.col(until_value).max()).collect()[0, 0])
                else:  # pl.Expr
                    n_value = int(af_df.select(until_value.max()).collect()[0, 0])
            return n_value * ppy
        valid = ["maximum_age", "term_years", "term_months", "fixed_date", "next_anniversary"]
        msg = f"invalid until={until!r}; expected one of {valid}"
        raise ValueError(msg)

    def _stamp_eager_columns(self, schedule: Schedule) -> ActuarialFrame:
        """Stamp projection_start_date / projection_end_date / num_proj_months."""
        # period_dates_expr or boundaries — get start and end per row
        if schedule._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = schedule.period_dates()  # list[date], length n_periods+1
            start_date = boundaries[0]
            end_date = boundaries[-1]
            stamped_df = self._frame._df.with_columns(  # noqa: SLF001
                projection_start_date=pl.lit(start_date),
                projection_end_date=pl.lit(end_date),
                num_proj_months=pl.lit(len(boundaries)),
            )
        else:
            # from_inception: per-policy boundaries
            period_dates_e = schedule.period_dates_expr()
            stamped_df = self._frame._df.with_columns(  # noqa: SLF001
                projection_start_date=period_dates_e.list.first(),
                projection_end_date=period_dates_e.list.last(),
                num_proj_months=period_dates_e.list.len(),
            )

        new_af = self._frame.__class__(stamped_df)
        new_af._projection = schedule  # noqa: SLF001
        new_af._mode = self._frame._mode  # noqa: SLF001
        new_af._verbose = self._frame._verbose  # noqa: SLF001
        new_af._threads = self._frame._threads  # noqa: SLF001
        return new_af

    def rollforward(self, **kwargs: Any) -> RollforwardBuilder:  # noqa: ANN401
        """Construct a :class:`RollforwardBuilder` that reads schedule from this frame.

        ``schedule=`` is no longer accepted on this method — call
        ``af.projection.set(...)`` first.
        """
        if "schedule" in kwargs:
            msg = (
                "schedule= is no longer accepted on rollforward(). "
                "Call af.projection.set(...) before rollforward(); the schedule "
                "is read from the frame."
            )
            raise TypeError(msg)
        if self._frame._projection is None:  # noqa: SLF001
            msg = (
                "This frame has no projection. "
                "Call af.projection.set(...) before rollforward()."
            )
            raise ValueError(msg)
        kwargs["schedule"] = self._frame._projection  # noqa: SLF001
        return RollforwardBuilder(**kwargs)
```

- [ ] **Step 5.4: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/accessors/test_projection_set.py -v
```

Expected: all PASS.

- [ ] **Step 5.5: Run accessor + frame tests for regression**

```bash
cd .
uv run pytest bindings/python/tests/accessors/ bindings/python/tests/frame/ -v
```

Expected: all PASS (new tests + existing accessor/frame tests).

- [ ] **Step 5.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/accessors/projection_frame.py bindings/python/tests/accessors/test_projection_set.py
git commit -m "feat(projection): add af.projection.set() — kwargs and Schedule paths

Unifies projection-axis setup. Accepts either:
  - schedule=Schedule.from_*(...) (typed input)
  - valuation_date+until+until_value+frequency (kwargs, policy-anchored)
  - start_date+n_periods+frequency (kwargs, synthetic)

Returns a new frame; eagerly stamps projection_start_date,
projection_end_date, num_proj_months. Frequency vocab accepts both
'monthly' and '1M' families.

af.projection.rollforward() now reads the schedule from the frame;
schedule= is rejected on the rollforward call with a migration message.

Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §3, §5"
```

---

### Task 6: Lazy accessor methods + governance hooks

**Files:**
- Modify: `bindings/python/gaspatchio_core/accessors/projection_frame.py`
- Test: `bindings/python/tests/accessors/test_projection_lazy_methods.py` (new)

- [ ] **Step 6.1: Write the failing tests**

Create file `bindings/python/tests/accessors/test_projection_lazy_methods.py`:

```python
"""Tests for af.projection.{period_dates, year_fractions, t_years, ...} lazy methods."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.schedule import Schedule


def _af_with_synthetic_projection(n: int = 12) -> ActuarialFrame:
    af = ActuarialFrame({"id": ["P1"]})
    return af.projection.set(
        start_date=date(2025, 1, 31),
        n_periods=n,
        frequency="monthly",
    )


class TestPeriodDates:
    def test_returns_list_of_n_plus_one_dates(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(period_dates=af.projection.period_dates())
        result = af.collect()
        assert len(result["period_dates"][0]) == 13


class TestYearFractions:
    def test_length_n_for_monthly(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(year_fractions=af.projection.year_fractions())
        result = af.collect()
        assert len(result["year_fractions"][0]) == 12

    def test_each_value_is_one_twelfth(self) -> None:
        af = _af_with_synthetic_projection(n=3)
        af = af.with_columns(year_fractions=af.projection.year_fractions())
        result = af.collect()
        values = result["year_fractions"][0]
        for v in values:
            assert v == pytest.approx(1.0 / 12.0)


class TestTYears:
    def test_starts_at_zero_length_n_plus_one(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(t_years=af.projection.t_years())
        result = af.collect()
        ty = result["t_years"][0]
        assert len(ty) == 13
        assert ty[0] == pytest.approx(0.0)
        assert ty[-1] == pytest.approx(1.0)

    def test_monotonically_increasing(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(t_years=af.projection.t_years())
        result = af.collect()
        ty = result["t_years"][0]
        for i in range(len(ty) - 1):
            assert ty[i + 1] > ty[i]


class TestAnniversaryMask:
    def test_length_n_for_monthly(self) -> None:
        af = _af_with_synthetic_projection(n=24)
        af = af.with_columns(mask=af.projection.anniversary_mask())
        result = af.collect()
        assert len(result["mask"][0]) == 24

    def test_anniversary_at_period_11_and_23(self) -> None:
        af = _af_with_synthetic_projection(n=24)
        af = af.with_columns(mask=af.projection.anniversary_mask())
        result = af.collect()
        mask = result["mask"][0]
        # Every 12th period closes an anniversary
        assert mask[11] is True
        assert mask[23] is True
        assert mask[0] is False
        assert mask[10] is False


class TestIsInForce:
    def test_uniform_true_when_no_end(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(in_force=af.projection.is_in_force())
        result = af.collect()
        assert result["in_force"][0] == [True] * 12


class TestContractBoundary:
    def test_uniform_false_when_no_end(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        af = af.with_columns(af.projection.contract_boundary().alias("boundary"))
        result = af.collect()
        assert result["boundary"][0].to_list() == [False] * 12


class TestGovernanceHooks:
    def test_canonical_form_returns_dict(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        cf = af.projection.canonical_form()
        assert isinstance(cf, dict)
        assert cf["n_periods"] == 12
        assert cf["frequency"] == "1M"

    def test_source_sha_starts_with_sha256(self) -> None:
        af = _af_with_synthetic_projection(n=12)
        sha = af.projection.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64

    def test_source_sha_matches_kwargs_and_schedule_paths(self) -> None:
        """Both paths produce identical canonical bytes for equivalent inputs."""
        af1 = ActuarialFrame({"id": ["P1"]})
        af1 = af1.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        af2 = ActuarialFrame({"id": ["P1"]})
        af2 = af2.projection.set(schedule=sched)
        assert af1.projection.source_sha() == af2.projection.source_sha()


class TestErrorWhenNoProjection:
    def test_period_dates_without_set_raises(self) -> None:
        af = ActuarialFrame({"id": ["P1"]})
        with pytest.raises(ValueError, match="no projection"):
            af.projection.period_dates()
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
cd .
uv run pytest bindings/python/tests/accessors/test_projection_lazy_methods.py -v
```

Expected: all FAIL — methods don't exist yet.

- [ ] **Step 6.3: Add the lazy methods to ProjectionFrameAccessor**

Edit `bindings/python/gaspatchio_core/accessors/projection_frame.py`. Add these methods at the end of the `ProjectionFrameAccessor` class (after `rollforward`):

```python
    def _require_projection(self) -> Schedule:
        """Helper: return the frame's Schedule or raise."""
        proj = self._frame._projection  # noqa: SLF001
        if proj is None:
            msg = (
                "This frame has no projection. "
                "Call af.projection.set(...) first."
            )
            raise ValueError(msg)
        return proj

    def period_dates(self) -> pl.Expr:
        """Return per-row List<Date> of length n_periods+1."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = sched.period_dates()
            return pl.lit(boundaries, dtype=pl.List(pl.Date))
        return sched.period_dates_expr()

    def year_fractions(self) -> pl.Expr:
        """Return per-row List<Float64> of length n_periods (per-period dt[t])."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            yfs = sched.year_fractions()
            return pl.lit(yfs, dtype=pl.List(pl.Float64))
        return sched.year_fractions_expr()

    def t_years(self) -> pl.Expr:
        """Return per-row List<Float64> of length n_periods+1 (cumulative year fractions from 0).

        Feeds Curve.discount_factor(t) directly.
        """
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            ty = sched.cumulative_year_fractions()
            return pl.lit(ty, dtype=pl.List(pl.Float64))
        # from_inception: cumsum the year_fractions_expr with leading 0
        yfs_expr = sched.year_fractions_expr()
        # Prepend 0.0 then cumulative-sum
        zeros = pl.lit([0.0], dtype=pl.List(pl.Float64))
        return pl.concat_list([zeros, yfs_expr.list.cum_sum()])

    def anniversary_mask(self) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods marking anniversaries."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            mask = sched.anniversary_mask()
            return pl.lit(mask, dtype=pl.List(pl.Boolean))
        return sched.anniversary_mask_expr()

    def is_in_force(self, *, end_date_column: str | None = None) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods — boundary mask.

        Pass ``end_date_column`` for from_inception schedules where each
        policy has its own end date. Without it, the mask is uniform True
        for all periods.
        """
        sched = self._require_projection()
        return sched.is_in_force_expr(end_date_column=end_date_column)

    def contract_boundary(self, *, end_date_column: str | None = None) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods — termination mask for rollforward.

        True at period t means the contract has terminated by period t. Pass to
        ``af.projection.rollforward(..., contract_boundary=af.projection.contract_boundary(...))``.
        This is the negation of :meth:`is_in_force` — kernel uses True = terminate.
        """
        sched = self._require_projection()
        return sched.contract_boundary_expr(end_date_column=end_date_column)

    def canonical_form(self) -> dict[str, Any]:
        """Return the structural recipe — same shape as Schedule.canonical_form()."""
        sched = self._require_projection()
        return sched.canonical_form()

    def source_sha(self) -> str:
        """Return sha256:<hex> over the canonical form bytes (audit identifier)."""
        sched = self._require_projection()
        return sched.source_sha()
```

- [ ] **Step 6.4: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/accessors/test_projection_lazy_methods.py -v
```

Expected: all PASS.

- [ ] **Step 6.5: Run full accessor + frame test suite**

```bash
cd .
uv run pytest bindings/python/tests/accessors/ bindings/python/tests/frame/ -v
```

Expected: all PASS.

- [ ] **Step 6.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/accessors/projection_frame.py bindings/python/tests/accessors/test_projection_lazy_methods.py
git commit -m "feat(projection): add lazy methods + governance hooks

period_dates, year_fractions, t_years, anniversary_mask, is_in_force,
contract_boundary — all return Polars expressions that compute from the
frame's _projection. canonical_form() and source_sha() delegate to the
underlying Schedule.

is_in_force (True = active) and contract_boundary (True = terminate) are
exact negations; the kernel-facing mask is contract_boundary, while
is_in_force is natural for non-kernel uses (expected lives, exposure).

Both kwargs and Schedule paths produce identical source_sha bytes for
equivalent inputs (audit-chain promise).

Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §4.2, §4.3"
```

---

### Task 7: Rollforward integration test

**Files:**
- Test: `bindings/python/tests/accessors/test_projection_rollforward_integration.py` (new)

- [ ] **Step 7.1: Write the integration test**

Create file `bindings/python/tests/accessors/test_projection_rollforward_integration.py`:

```python
"""Tests for af.projection.rollforward() reading schedule from the frame."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, RollforwardCollector, compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestRollforwardReadsFromFrame:
    def test_basic_single_state(self) -> None:
        af = ActuarialFrame({
            "id": ["P1"],
            "av_init": [1000.0],
            "fund_return": [[0.01] * 12],
        })
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        b = af.projection.rollforward(states={"av": pl.col("av_init")})
        b["av"].grow(pl.col("fund_return"))
        compiled = compile_rollforward(b)
        collector = RollforwardCollector(compiled)
        af.av = collector.expr_for("av")
        result = af.collect()
        assert "av" in result.columns


class TestRollforwardErrorPaths:
    def test_schedule_kwarg_raises_typeerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(TypeError, match="schedule= is no longer accepted"):
            af.projection.rollforward(
                states={"av": pl.col("av_init")},
                schedule=sched,
            )

    def test_no_projection_raises_valueerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        with pytest.raises(ValueError, match="no projection"):
            af.projection.rollforward(states={"av": pl.col("av_init")})
```

- [ ] **Step 7.2: Run test to verify it passes**

```bash
cd .
uv run pytest bindings/python/tests/accessors/test_projection_rollforward_integration.py -v
```

Expected: all PASS (the implementation from Task 5 already covers this).

- [ ] **Step 7.3: Commit**

```bash
cd .
git add bindings/python/tests/accessors/test_projection_rollforward_integration.py
git commit -m "test(projection): integration tests for rollforward reading from frame

Locks in the contract that af.projection.rollforward() reads the schedule
from af._projection, rejects schedule= kwarg with a migration message,
and raises clearly when called on a frame with no projection."
```

---

### Task 8: Sync projection_frame pyi stubs

**Files:**
- Modify: `bindings/python/gaspatchio_core/accessors/projection_frame.pyi` (create if absent)

- [ ] **Step 8.1: Check if stub exists**

```bash
cd .
ls bindings/python/gaspatchio_core/accessors/projection_frame.pyi 2>&1
```

If the file does not exist, skip to step 8.3 and create it. If it exists, modify it.

- [ ] **Step 8.2: Run stub-sync test to see what's missing**

```bash
cd .
uv run pytest bindings/python/tests/test_stub_sync.py -v
```

If the test passes, `.pyi` autogeneration may be in effect — skip to step 8.4.

- [ ] **Step 8.3: Create or update the stub file**

If creating, use this content:

```python
"""Type stubs for ProjectionFrameAccessor."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import polars as pl

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.base import ActuarialFrame
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


class ProjectionFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: ActuarialFrame) -> None: ...
    def set(
        self,
        *,
        schedule: Schedule | None = ...,
        valuation_date: dt.date | None = ...,
        until: Literal[
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
            "next_anniversary",
        ] | None = ...,
        until_value: int | dt.date | str | pl.Expr | None = ...,
        issue_age_column: str = ...,
        inception_column: str = ...,
        start_date: dt.date | None = ...,
        n_periods: int | None = ...,
        frequency: str | None = ...,
    ) -> ActuarialFrame: ...
    def rollforward(self, **kwargs: Any) -> RollforwardBuilder: ...
    def period_dates(self) -> pl.Expr: ...
    def year_fractions(self) -> pl.Expr: ...
    def t_years(self) -> pl.Expr: ...
    def anniversary_mask(self) -> pl.Expr: ...
    def is_in_force(self, *, end_date_column: str | None = ...) -> pl.Expr: ...
    def contract_boundary(self, *, end_date_column: str | None = ...) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
```

- [ ] **Step 8.4: Run stub-sync test**

```bash
cd .
uv run pytest bindings/python/tests/test_stub_sync.py -v
```

Expected: PASS.

- [ ] **Step 8.5: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/accessors/projection_frame.pyi
git commit -m "chore(projection): sync pyi stubs for new accessor methods"
```

---

## Phase 4: Delete `create_projection_timeline`

### Task 9: Lock in the breakage with a migration smoke test

**Files:**
- Test: `bindings/python/tests/migration/__init__.py` (new)
- Test: `bindings/python/tests/migration/test_create_projection_timeline_removed.py` (new)

- [ ] **Step 9.1: Create the migration test**

Create file `bindings/python/tests/migration/__init__.py`:

```python
```

(Empty file.)

Create file `bindings/python/tests/migration/test_create_projection_timeline_removed.py`:

```python
"""Locks in the deletion of af.date.create_projection_timeline().

If this test fails (i.e. the method is still present), the migration
has been silently regressed.
"""

from __future__ import annotations

import pytest

from gaspatchio_core import ActuarialFrame


def test_create_projection_timeline_attribute_error() -> None:
    af = ActuarialFrame({"id": ["P1"], "issue_age": [30]})
    with pytest.raises(AttributeError):
        af.date.create_projection_timeline  # noqa: B018
```

- [ ] **Step 9.2: Run test (expect it to fail because method still exists)**

```bash
cd .
uv run pytest bindings/python/tests/migration/ -v
```

Expected: FAIL — `create_projection_timeline` still exists on `DateFrameAccessor`.

### Task 10: Delete `create_projection_timeline`

**Files:**
- Modify: `bindings/python/gaspatchio_core/accessors/date.py`
- Modify: `bindings/python/tests/accessors/test_dates.py`
- Modify: `bindings/python/tests/integration/test_variable_projection.py`

- [ ] **Step 10.1: Delete the method from date.py**

Edit `bindings/python/gaspatchio_core/accessors/date.py`. Delete the entire `create_projection_timeline` method (currently spans roughly lines 271-577 — search for `def create_projection_timeline` and delete from there through the end of that method, before the `class DateColumnAccessor` block).

Also delete the now-unused imports if they were only used by this method:

```python
# Check if these are still used after deletion; remove if orphaned:
import datetime
from typing import Literal, Union
from ..errors.validation import capture_validation_context, raise_validation_error
```

- [ ] **Step 10.2: Run lint to find broken imports**

```bash
cd .
uv run ruff check bindings/python/gaspatchio_core/accessors/date.py
```

Fix any unused imports the lint flags.

- [ ] **Step 10.3: Run the migration test**

```bash
cd .
uv run pytest bindings/python/tests/migration/ -v
```

Expected: PASS — `AttributeError` confirmed.

- [ ] **Step 10.4: Update test_dates.py — remove create_projection_timeline tests**

```bash
cd .
grep -n "create_projection_timeline" bindings/python/tests/accessors/test_dates.py
```

For each test case that exercises `create_projection_timeline`, delete it. The file should still test `create_timeline` and `add_duration` — those are separate verbs and stay.

- [ ] **Step 10.5: Update test_variable_projection.py**

```bash
cd .
grep -n "create_projection_timeline" bindings/python/tests/integration/test_variable_projection.py
```

Replace each `af.date.create_projection_timeline(...)` call with the equivalent `af.projection.set(...)` per the migration mapping in `ref/38-projection-axis/migration.md` §1.

Specifically:
- `projection_end_type="X"` → `until="X"`
- `projection_end_value=V` → `until_value=V`
- `projection_frequency="monthly"` → `frequency="monthly"`
- Remove `output_column=` and `store_start_date=`/`store_end_date=` (always-on now)
- Rebind: `af = af.projection.set(...)` (was: `af.date.create_projection_timeline(...)` mutating)

- [ ] **Step 10.6: Run accessor + integration tests**

```bash
cd .
uv run pytest bindings/python/tests/accessors/ bindings/python/tests/integration/ bindings/python/tests/migration/ -v
```

Expected: all PASS.

- [ ] **Step 10.7: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/accessors/date.py \
        bindings/python/tests/accessors/test_dates.py \
        bindings/python/tests/integration/test_variable_projection.py \
        bindings/python/tests/migration/
git commit -m "refactor(accessors): delete af.date.create_projection_timeline()

Replaced by af.projection.set(...). Pre-release breaking change with no
shim. Migration test in tests/migration/ locks in the breakage.

Existing test_dates.py and test_variable_projection.py rewritten to use
the new verb. The four other test files in tests/accessors/ are
unaffected (they test create_timeline / add_duration — different verbs).

Spec: ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md §6"
```

---

## Phase 5: Migrate user-facing rollforward tests

### Task 11: Migrate `test_va_acceptance.py`

**Files:**
- Modify: `bindings/python/tests/rollforward/test_va_acceptance.py`

- [ ] **Step 11.1: Read the existing test**

```bash
cd .
cat bindings/python/tests/rollforward/test_va_acceptance.py
```

- [ ] **Step 11.2: Apply the migration**

For each call of the form:
```python
b = af.projection.rollforward(
    states=...,
    schedule=sched,
    contract_boundary=mask,  # if present
)
```

Rewrite to:
```python
af = af.projection.set(schedule=sched)
b = af.projection.rollforward(
    states=...,
    contract_boundary=af.projection.contract_boundary(end_date_column="end_col"),  # or pre-existing mask
)
```

Adapt `end_date_column=` based on the test fixture's column names. If the original `contract_boundary` was a hand-built expression rather than from `contract_boundary()`, keep it as-is — the migration only requires moving `schedule=` off the rollforward call. Note that `contract_boundary()` (True = terminate) is the kernel-shaped mask; `is_in_force()` (True = active) is the negation, used for non-kernel calculations such as expected lives in-force.

- [ ] **Step 11.3: Run the test**

```bash
cd .
uv run pytest bindings/python/tests/rollforward/test_va_acceptance.py -v
```

Expected: PASS.

- [ ] **Step 11.4: Commit**

```bash
cd .
git add bindings/python/tests/rollforward/test_va_acceptance.py
git commit -m "test(va): migrate to af.projection.set() + explicit contract_boundary"
```

### Task 12: Migrate `test_projection_accessor.py`

**Files:**
- Modify: `bindings/python/tests/rollforward/test_projection_accessor.py`

- [ ] **Step 12.1: Read the existing test**

```bash
cd .
cat bindings/python/tests/rollforward/test_projection_accessor.py
```

- [ ] **Step 12.2: Apply the same migration as Task 11**

Same pattern: move `schedule=` off the rollforward call into a preceding `af.projection.set(schedule=sched)`.

- [ ] **Step 12.3: Run the test**

```bash
cd .
uv run pytest bindings/python/tests/rollforward/test_projection_accessor.py -v
```

Expected: PASS.

- [ ] **Step 12.4: Run the full rollforward test suite**

```bash
cd .
uv run pytest bindings/python/tests/rollforward/ -v
```

Expected: all PASS. The 24 internal tests using `RollforwardBuilder(schedule=...)` directly should pass unchanged.

- [ ] **Step 12.5: Commit**

```bash
cd .
git add bindings/python/tests/rollforward/test_projection_accessor.py
git commit -m "test(projection-accessor): migrate to af.projection.set() + explicit contract_boundary"
```

---

## Phase 6: Migrate tutorials

For each tutorial below, the migration is mechanical — apply the pattern from `ref/38-projection-axis/migration.md`. Each tutorial gets its own commit.

### Task 13: Migrate level-1-hello-world tutorials

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/01-projections/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/02-survival/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/03-time-shifting/model.py`

- [ ] **Step 13.1: Find each `create_projection_timeline` call**

```bash
cd .
grep -n "create_projection_timeline" bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/*/model.py
```

- [ ] **Step 13.2: Apply migration pattern §2 from migration.md**

For each call, rewrite per the mapping:
- `valuation_date=` → `valuation_date=`
- `projection_end_type=` → `until=`
- `projection_end_value=` → `until_value=`
- `projection_frequency=` → `frequency=`
- Drop `output_column=`, `store_start_date=`, `store_end_date=`
- Rebind `af = af.projection.set(...)`
- If the model used the proj_dates output column, add: `af.projection_date = af.projection.period_dates()` (or whatever the column was called)

- [ ] **Step 13.3: Run each model end-to-end**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/01-projections/model.py
uv run python bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/02-survival/model.py
uv run python bindings/python/gaspatchio_core/tutorials/level-1-hello-world/steps/03-time-shifting/model.py
```

Each should run without error and produce the same output as before (compared against the step's `expected_output.txt` if present).

- [ ] **Step 13.4: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/tutorials/level-1-hello-world/
git commit -m "refactor(tutorial-l1): migrate to af.projection.set()"
```

### Task 14: Migrate level-3-mini-va (untyped)

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/steps/*/model.py` (six steps)

- [ ] **Step 14.1: Apply the same migration pattern to each model.py**

```bash
cd .
grep -rn "create_projection_timeline" bindings/python/gaspatchio_core/tutorials/level-3-mini-va/
```

- [ ] **Step 14.2: For each file, rewrite the call**

Same pattern as Task 13. The migration.md §2 example is taken from this tutorial.

- [ ] **Step 14.3: Run base model**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py
diff <(uv run python bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py 2>&1) bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/expected_output.txt
```

Expected: no diff (output unchanged).

- [ ] **Step 14.4: Run each step model**

For each of the six step models, run and compare against `expected_output.txt`.

- [ ] **Step 14.5: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/tutorials/level-3-mini-va/
git commit -m "refactor(tutorial-l3-untyped): migrate to af.projection.set()"
```

### Task 15: Migrate level-3-mini-va-typed (typed Schedule path)

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/base/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/steps/*/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/README.md`

- [ ] **Step 15.1: For base/model.py — apply pattern §4 from migration.md**

The typed tutorial constructs Schedule directly. Migration:

Old:
```python
schedule = Schedule.from_calendar_grid(...)
period_widths = schedule.year_fractions()
t_years_list = [0.0, *list(itertools.accumulate(period_widths))]
# ... later:
b = af.projection.rollforward(states=..., schedule=schedule)
```

New:
```python
schedule = Schedule.from_calendar_grid(...)
af = af.projection.set(schedule=schedule)
# year_fractions / t_years now via accessor:
period_widths = af.projection.year_fractions()  # ExpressionProxy — keep .collect() if needed
# ... later:
b = af.projection.rollforward(
    states=...,
    contract_boundary=af.projection.contract_boundary(),
)
```

The `itertools.accumulate` line goes away — `af.projection.t_years()` returns the cumulative vector directly.

- [ ] **Step 15.2: Apply the same pattern to each step**

```bash
cd .
grep -rn "Schedule.from_\|schedule=schedule\|schedule=sched" bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/
```

For each file, apply the migration. For step `07-anniversary-aware`, also consider switching to `until="next_anniversary"` if natural — but if the existing logic uses `anniversary_mask` directly, leave it (still works).

- [ ] **Step 15.3: Update the README.md "Findings worth reading the docs about" section**

Open `bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/README.md` and remove the bullet about the off-by-one `n_periods = PROJECTION_MONTHS + 1` alignment trap. That footgun is gone now.

Search for: "anniversary_mask_expr() returns n_periods elements" — delete that bullet point.

Search for: "Schedule.year_fractions() returns per-period widths" — this is now solved by `af.projection.t_years()`. Update bullet accordingly.

- [ ] **Step 15.4: Run base model**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/base/model.py
```

- [ ] **Step 15.5: Run reconcile script**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/steps/06-reconcile/reconcile.py
```

Expected: parity with level-3-mini-va untyped at ~1e-9 relative.

- [ ] **Step 15.6: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/
git commit -m "refactor(tutorial-l3-typed): migrate to af.projection.set(schedule=sched)

Schedule object stays — it's the typed input audit anchor. Now passed
via af.projection.set(schedule=...) instead of via the rollforward call.
Drops the off-by-one alignment footgun from the README findings list:
af.projection.t_years() returns the cumulative vector directly."
```

### Task 16: Migrate level-5-scenarios (both untyped and typed)

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-5-scenarios/steps/*/model.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/**/*.py`

- [ ] **Step 16.1: Find all old-API usages**

```bash
cd .
grep -rn "create_projection_timeline\|schedule=" bindings/python/gaspatchio_core/tutorials/level-5-scenarios/ bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/
```

- [ ] **Step 16.2: Apply migration patterns**

Untyped models use pattern §2; typed models use pattern §4.

- [ ] **Step 16.3: Run each base model**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-5-scenarios/base/model.py
uv run python bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/base/model.py 2>&1 | head -20
```

- [ ] **Step 16.4: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/tutorials/level-5-scenarios/ bindings/python/gaspatchio_core/tutorials/level-5-scenarios-typed/
git commit -m "refactor(tutorial-l5): migrate to af.projection.set()"
```

### Task 17: Migrate rollforward-patterns tutorials (synthetic)

**Files:**
- Modify: `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/01_single_state_fund.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/02_multistate_ratchet.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/03_lapse_stop.py`
- Modify: `bindings/python/gaspatchio_core/tutorials/rollforward-patterns/README.md`

- [ ] **Step 17.1: Apply migration pattern §6 (option 1 — kwargs)**

For each pattern file, rewrite the synthetic projection setup:

Old:
```python
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31),
    n_periods=12,
    frequency="1M",
)
af = ActuarialFrame({...})
b = af.projection.rollforward(states={...}, schedule=sched)
```

New:
```python
af = ActuarialFrame({...})
af = af.projection.set(
    start_date=date(2025, 1, 31),
    n_periods=12,
    frequency="monthly",
)
b = af.projection.rollforward(
    states={...},
    # Synthetic / unbounded — omit contract_boundary entirely, OR pass an
    # explicit no-op mask via af.projection.contract_boundary() for symmetry
    # with non-synthetic call sites.
)
```

- [ ] **Step 17.2: Run each tutorial**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/rollforward-patterns/01_single_state_fund.py
uv run python bindings/python/gaspatchio_core/tutorials/rollforward-patterns/02_multistate_ratchet.py
uv run python bindings/python/gaspatchio_core/tutorials/rollforward-patterns/03_lapse_stop.py
```

Each should run cleanly and produce comparable output.

- [ ] **Step 17.3: Update rollforward-patterns/README.md**

Update any code blocks in the README to use the new pattern.

- [ ] **Step 17.4: Commit**

```bash
cd .
git add bindings/python/gaspatchio_core/tutorials/rollforward-patterns/
git commit -m "refactor(tutorial-rollforward-patterns): migrate to af.projection.set() kwargs path

Synthetic projections now use af.projection.set(start_date=..., n_periods=..., frequency='monthly')
instead of constructing Schedule + passing via rollforward(schedule=...).
Cleaner for pattern demos."
```

---

## Phase 7: Final regression gate

### Task 18: Full test suite + VA reconciliation

**Files:** none modified

- [ ] **Step 18.1: Run the full Python test suite**

```bash
cd .
uv run pytest bindings/python/tests/ -v --tb=short 2>&1 | tail -50
```

Expected: all PASS. Any FAIL is a regression that must be investigated and fixed before proceeding.

- [ ] **Step 18.2: Run docstring tests**

```bash
cd .
uv run pytest --doctest-modules --doctest-glob="*.pyi" bindings/python/gaspatchio_core/ 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 18.3: Run lint**

```bash
cd .
uv run ruff check bindings/python/gaspatchio_core/ bindings/python/tests/
```

Expected: clean.

- [ ] **Step 18.4: Run formatter check**

```bash
cd .
uv run ruff format --check bindings/python/gaspatchio_core/ bindings/python/tests/
```

Expected: all formatted. If anything is unformatted, run `uv run ruff format` and re-run the check.

- [ ] **Step 18.5: Run the VA reconcile gate**

```bash
cd .
uv run python bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/steps/06-reconcile/reconcile.py 2>&1 | tail -10
```

Expected: parity with `level-3-mini-va` (untyped) at ~1e-9 relative. **This is the headline gate** — if reconciliation fails after migration, the migration introduced a numerical bug somewhere.

- [ ] **Step 18.6: Run benchmarks (sanity check, not perf gate)**

```bash
cd .
uv run pytest bindings/python/tests/benchmarks/ -v -m "not slow" 2>&1 | tail -20
```

Expected: PASS. Performance numbers should be in the same ballpark as before — this refactor is API-only and shouldn't change runtime.

- [ ] **Step 18.7: Commit any formatter/lint fixes if needed**

```bash
cd .
git status --short
# If anything changed:
git add -u
git commit -m "chore: lint and format pass after projection-axis migration"
```

---

## Phase 8: Documentation

The gaspatchio-docs repo is at `../gaspatchio-docs/`. It is on the `main` branch with 7 unpushed commits from the previous session.

### Task 19: Rewrite concepts/schedules.md

**Files:**
- Modify: `../gaspatchio-docs/docs/concepts/schedules.md`

- [ ] **Step 19.1: Read the current file**

```bash
cat ../gaspatchio-docs/docs/concepts/schedules.md
```

- [ ] **Step 19.2: Rewrite to lead with `af.projection.set()`**

Restructure the page so the first worked example is:

```python
import datetime as dt
from gaspatchio_core import ActuarialFrame

af = ActuarialFrame({
    "policy_id":  ["P001", "P002", "P003"],
    "issue_age":  [30, 45, 60],
    "policy_inception": [dt.date(2020, 6, 15), dt.date(2018, 3, 1), dt.date(2023, 1, 1)],
})

af = af.projection.set(
    valuation_date=dt.date(2025, 1, 1),
    until="maximum_age",
    until_value=100,
    frequency="monthly",
)
```

Then show the lazy methods:
```python
af.year_fractions = af.projection.year_fractions()
af.t_years = af.projection.t_years()
af.is_in_force = af.projection.is_in_force()
```

Then introduce Schedule as "the audit-anchor object that backs `af.projection`" with the `set(schedule=...)` path:
```python
sched = Schedule.from_calendar_grid(start_date=..., n_periods=240, frequency="1M")
af = af.projection.set(schedule=sched)
```

Position Schedule in a "Reaching for the typed object" section, not as the entry point.

- [ ] **Step 19.3: Verify code blocks copy-paste run**

For each code block in the file, paste into a Python REPL and verify it produces the documented output. Replace any that don't run with corrected versions.

- [ ] **Step 19.4: Commit**

```bash
cd ../gaspatchio-docs
git add docs/concepts/schedules.md
git commit -m "docs(concepts): rewrite schedules.md to lead with af.projection.set()

Schedule is now positioned as the typed audit-anchor object that backs
af.projection. The kwargs path is the documented primary; the typed path
is shown for sharing/audit/testing scenarios.

Spec: gaspatchio-core ref/38-projection-axis/specs/2026-05-05-projection-axis-design.md"
```

### Task 20: Update concepts/rollforward/*.md

**Files:**
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/index.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/steps.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/multi-state.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/products.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/inspection.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/composition.md`
- Modify: `../gaspatchio-docs/docs/concepts/rollforward/increments.md`

- [ ] **Step 20.1: Find all `schedule=` usages in concepts/rollforward/**

```bash
grep -rn "schedule=\|Schedule.from_" ../gaspatchio-docs/docs/concepts/rollforward/
```

- [ ] **Step 20.2: For each example, apply the migration**

Replace:
```python
sched = Schedule.from_*(...)
b = af.projection.rollforward(states=..., schedule=sched)
```

With:
```python
af = af.projection.set(...)  # or set(schedule=sched) for typed
b = af.projection.rollforward(
    states=...,
    contract_boundary=af.projection.contract_boundary(),
)
```

- [ ] **Step 20.3: Run each updated code block to verify it produces the documented output**

For each Python code block, paste into a REPL and verify.

- [ ] **Step 20.4: Commit**

```bash
cd ../gaspatchio-docs
git add docs/concepts/rollforward/
git commit -m "docs(rollforward): drop schedule= from examples; add explicit contract_boundary

Every rollforward example now uses af.projection.set(...) upstream and
contract_boundary=af.projection.contract_boundary() at the call site. No silent
defaults — explicit boundary is the standard pattern."
```

### Task 21: Update concepts/calculations.md

**Files:**
- Modify: `../gaspatchio-docs/docs/concepts/calculations.md`

- [ ] **Step 21.1: Find old-API usages**

```bash
grep -n "create_projection_timeline\|Schedule.from_\|schedule=" ../gaspatchio-docs/docs/concepts/calculations.md
```

- [ ] **Step 21.2: Apply the same migration pattern as Task 20**

- [ ] **Step 21.3: Verify code blocks**

- [ ] **Step 21.4: Commit**

```bash
cd ../gaspatchio-docs
git add docs/concepts/calculations.md
git commit -m "docs(calculations): migrate examples to af.projection.set()"
```

### Task 22: Update api/schedule.md tone

**Files:**
- Modify: `../gaspatchio-docs/docs/api/schedule.md`

- [ ] **Step 22.1: Read the current file**

```bash
cat ../gaspatchio-docs/docs/api/schedule.md
```

- [ ] **Step 22.2: Update intro paragraph**

Position Schedule as "the audit-anchor object backing `af.projection`" rather than the primary projection-setup entry point. The mkdocstrings autogeneration of method signatures stays unchanged (those come from the source docstrings).

- [ ] **Step 22.3: Commit**

```bash
cd ../gaspatchio-docs
git add docs/api/schedule.md
git commit -m "docs(api): reposition Schedule as audit-anchor backing af.projection"
```

---

## Phase 9: Cleanup

### Task 23: Restore stashed work + final sanity

- [ ] **Step 23.1: Pop the pre-flight stash if you used it**

```bash
cd .
git stash list
# If "pre-projection-axis-stash" is present:
git stash pop
```

- [ ] **Step 23.2: Run the full test suite one more time**

```bash
cd .
uv run pytest bindings/python/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 23.3: Confirm no `create_projection_timeline` references remain in core or tutorials**

```bash
cd .
grep -rn "create_projection_timeline" bindings/python/gaspatchio_core/ 2>&1 | grep -v __pycache__
```

Expected: empty (no matches).

- [ ] **Step 23.4: Confirm no `schedule=` on the user-facing rollforward path**

```bash
cd .
grep -rn "\.projection\.rollforward(.*schedule=" bindings/python/gaspatchio_core/ 2>&1 | grep -v __pycache__
```

Expected: empty (no matches in source/tutorials). The 24 internal `RollforwardBuilder(schedule=...)` usages in tests stay — those are intentional.

- [ ] **Step 23.5: Push branch (do NOT push without user confirmation)**

```bash
cd .
git log --oneline gsp-92-rollforward-redesign...origin/gsp-92-rollforward-redesign 2>&1 | head -30
```

Show this list to the user. **Wait for explicit user instruction before running `git push`.**

---

## Self-review checklist

Before declaring the plan complete, the executor verifies:

- [ ] All 23 tasks committed individually with clear commit messages
- [ ] All tests pass (`uv run pytest bindings/python/tests/`)
- [ ] All docstring tests pass (`uv run pytest --doctest-modules --doctest-glob="*.pyi"`)
- [ ] Lint clean (`uv run ruff check`)
- [ ] Format clean (`uv run ruff format --check`)
- [ ] VA reconciliation passes at ~1e-9 relative
- [ ] No `create_projection_timeline` remains in source / tutorials
- [ ] No `af.projection.rollforward(..., schedule=...)` calls remain in source / tutorials
- [ ] Migration smoke test in `tests/migration/` is GREEN (the deletion is locked in)
- [ ] gaspatchio-docs branch has the four documentation commits (Tasks 19-22)
- [ ] User has reviewed and approved before pushing

---

## Out of scope (separate Linear tickets)

- GSP-97 — Native per-policy n_periods in the rollforward kernel
- GSP-98 — Mid-period termination semantics

Both reference back to this spec. Do not pull either into this plan.
