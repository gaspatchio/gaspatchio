# Phase 1a Sub-plan A — Typed Time Primitive (Schedule + Calendar + DayCount) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a typed `Schedule` / `Calendar` / `DayCount` primitive — 5 day-counts, 4 calendars, 4 business-day conventions, two named constructors (`from_inception` per-policy and `from_calendar_grid` shared), default `OneTwelfth + NullCalendar` matching US/UK/EU production practice, with month-end anchoring on `from_calendar_grid` and context-dependent BD-convention default. The primitive is independently shippable: it exposes `pl.Expr` accessors (`year_fractions`, `period_dates`, `anniversary_mask`) that can be added to any `ActuarialFrame` today, plus a JSON-serialisable canonical form and `source_sha()` so Sub-plan D's kernel can fingerprint it later.

**Architecture:** Frozen-dataclass typed inputs (DayCount, Calendar, BusinessDayConvention, Schedule) under `gaspatchio_core/schedule/`. Date arithmetic stays vectorised — Polars' `dt` namespace for offsets, `python-holidays` for the three real calendars (TARGET, UK, US), pure structural rules for `NullCalendar` and `OneTwelfth`. Schedule accessors return `pl.Expr` so they fit the existing lazy-frame composition story. Canonical form is a deterministic JSON dict (sorted keys, no Python object refs); `source_sha = sha256(canonical_form_bytes)`. No kernel work, no IR work, no `rollforward()` rewiring — those are Sub-plan D.

**Tech Stack:** Python 3.10+; Polars 1.38.1 (pinned); `python-holidays` (new dep, MIT, ~150 KB); `python-dateutil` (already in deps); `pydantic` v2 (already in deps); pytest + hypothesis (dev deps). No new Rust code in this sub-plan — the day-count year-fraction maths is small enough to ship in Python and can be lowered into Rust later if benchmarks demand it.

---

## Scope check

This sub-plan is one independently-testable subsystem (typed time inputs). No further decomposition needed. Sub-plans B (Curve), C (MortalityTable), D (kernel) are separate plans.

**Out of scope (deferred / other sub-plans):**
- IR field for `schedule` and `rollforward(schedule=...)` kwarg wiring → Sub-plan D
- `spec_fingerprint()` integration → Sub-plan D
- `action_key()` integration → Sub-plan D
- Partial-period `dt` at termination → Phase 2
- Reporting-grid aggregation (`Schedule.aggregate_to(...)`) → Phase 2
- Stub-period handling beyond `Backward` rule → not Phase 1

---

## File structure

**New (Python, all under `bindings/python/gaspatchio_core/schedule/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Public re-exports: `Schedule`, `Calendar`, `DayCount`, `BusinessDayConvention` |
| `__init__.pyi` | Type stubs mirroring `__init__.py` |
| `_day_count.py` | `DayCount` ABC + 5 concrete subclasses (`OneTwelfth`, `Actual365Fixed`, `Actual360`, `Thirty360`, `ActualActualISDA`); `year_fraction()` and `name()` methods |
| `_business_day.py` | `BusinessDayConvention` enum (`Following`, `ModifiedFollowing`, `Preceding`, `Unadjusted`); `adjust(date_expr, calendar)` method |
| `_calendar.py` | `Calendar` ABC + `NullCalendar`, `TARGET`, `UnitedKingdom`, `UnitedStates`, `JointCalendar`, `BespokeCalendar`; `is_business_day(date_expr)`, `holidays_in(start, end)`, `name()` |
| `_schedule.py` | `Schedule` frozen-dataclass + `from_inception` and `from_calendar_grid` classmethods; `year_fractions()`, `period_dates()`, `anniversary_mask()`, `dt` accessors; `source_sha()` |
| `_canonical.py` | `canonical_form(obj) -> dict` + `canonical_bytes(obj) -> bytes` deterministic serialisation; one entry point shared across DayCount/Calendar/BD/Schedule |

**New (tests, all under `bindings/python/tests/schedule/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Empty marker |
| `conftest.py` | Shared fixtures: `monthly_dates`, `leap_year_dates`, sample policy frames |
| `test_day_count.py` | Per-convention `year_fraction` tests, including QuantLib reference values |
| `test_business_day.py` | Each of 4 BD conventions adjusts correctly across NullCalendar / real-calendar |
| `test_calendar.py` | Each of 4 calendars correctly identifies known holidays (e.g., Good Friday 2025, MLK Day 2025) |
| `test_schedule_constructors.py` | `from_inception` per-policy; `from_calendar_grid` shared + month-end anchoring |
| `test_schedule_year_fractions.py` | Schedule × DayCount cross-product → correct `dt[t]` columns |
| `test_schedule_period_dates.py` | Period date generation for both constructors, leap-year crossings |
| `test_schedule_anniversary_mask.py` | Mask correctness across BD conventions; leap-day inception |
| `test_schedule_canonical.py` | Canonical-form determinism; structural-change → SHA change; cosmetic-equiv → SHA stable |
| `test_smoke_gsp92.py` | 1200-period `from_inception` smoke test mirroring §4.9 schedule shape |

**Modified:**

- `bindings/python/pyproject.toml` — add `python-holidays>=0.50` to `dependencies`
- `bindings/python/gaspatchio_core/__init__.py` — re-export `Schedule`, `Calendar`, `DayCount`, `BusinessDayConvention`
- `bindings/python/gaspatchio_core/__init__.py` `__all__` list — append the four new exports

**Untouched (so we don't accidentally break Sub-plan D's surface):**
- `gaspatchio_core/rollforward/` — old kernel stays running until Sub-plan D
- `gaspatchio_core/polars_backend/plugins.py` — kernel stub stays as-is
- `core/src/polars_functions/rollforward.rs` — Rust kernel stays as-is

---

## Tasks

### Task 1: Package scaffolding + dependency

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/__init__.py`
- Create: `bindings/python/gaspatchio_core/schedule/__init__.pyi`
- Create: `bindings/python/tests/schedule/__init__.py`
- Modify: `bindings/python/pyproject.toml` (one line added to `dependencies`)

- [ ] **Step 1: Add the dependency**

In `bindings/python/pyproject.toml`, locate the `dependencies = [...]` block and insert `"holidays>=0.50",` immediately after `"python-dateutil>=2.9.0.post0",` (alphabetical and adjacent topic). Then run `cd bindings/python && uv sync` to lock and install.

- [ ] **Step 2: Verify the dep imports**

Run: `cd bindings/python && uv run python -c "import holidays; print(holidays.__version__); print(holidays.US(years=2025).get('2025-01-01'))"`
Expected: a version string + `"New Year's Day"`.

- [ ] **Step 3: Create empty package files**

Write the three files with minimal content:

```python
# bindings/python/gaspatchio_core/schedule/__init__.py
"""Typed time primitives — Schedule, Calendar, DayCount, BusinessDayConvention."""

from __future__ import annotations

__all__: list[str] = []
```

```python
# bindings/python/gaspatchio_core/schedule/__init__.pyi
# (no docstring — ruff PYI021 forbids docstrings in .pyi stubs)
__all__: list[str] = []
```

```python
# bindings/python/tests/schedule/__init__.py
"""Tests for gaspatchio_core.schedule."""
```

- [ ] **Step 4: Verify package imports**

Run: `cd bindings/python && uv run python -c "import gaspatchio_core.schedule"`
Expected: no error, no output.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/pyproject.toml bindings/python/gaspatchio_core/schedule/ bindings/python/tests/schedule/__init__.py
# (note: uv.lock lives at the workspace root ../uv.lock — outside this repo — so it is not committed here)
git commit -m "feat(schedule): scaffold typed-time package + add holidays dep"
```

---

### Task 2: `DayCount` ABC + `OneTwelfth` (the default)

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Create: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_day_count.py
"""Per-convention year-fraction tests."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._day_count import DayCount, OneTwelfth


class TestOneTwelfth:
    def test_name(self) -> None:
        assert OneTwelfth().name() == "OneTwelfth"

    def test_year_fraction_is_constant_one_twelfth(self) -> None:
        dc = OneTwelfth()
        # OneTwelfth ignores the actual dates — it's structural, not date-driven
        assert dc.year_fraction(date(2025, 1, 31), date(2025, 2, 28)) == pytest.approx(1 / 12)
        assert dc.year_fraction(date(2025, 2, 28), date(2025, 3, 31)) == pytest.approx(1 / 12)
        assert dc.year_fraction(date(2024, 2, 29), date(2024, 3, 31)) == pytest.approx(1 / 12)

    def test_year_fraction_year_aware_for_annual_step(self) -> None:
        dc = OneTwelfth()
        # 12 months apart → 1.0
        assert dc.year_fraction(date(2025, 1, 31), date(2026, 1, 31)) == pytest.approx(1.0)

    def test_is_frozen_dataclass(self) -> None:
        dc = OneTwelfth()
        with pytest.raises(Exception):
            dc.something = 42  # type: ignore[attr-defined]

    def test_equal_instances_hash_equal(self) -> None:
        assert OneTwelfth() == OneTwelfth()
        assert hash(OneTwelfth()) == hash(OneTwelfth())

    def test_subclass_of_day_count(self) -> None:
        assert isinstance(OneTwelfth(), DayCount)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestOneTwelfth -v`
Expected: FAIL with `ImportError: cannot import name 'DayCount'` or similar.

- [ ] **Step 3: Implement minimal code**

```python
# bindings/python/gaspatchio_core/schedule/_day_count.py
"""DayCount conventions for typed Schedule.

Each DayCount converts a (start_date, end_date) pair to a year fraction.
Used by Schedule to populate the per-period dt[t] series consumed by
time-aware rollforward operations like .grow(rate).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class DayCount(ABC):
    """Abstract day-count convention.

    Concrete subclasses are frozen dataclasses (so equality and hashing
    work out of the box) implementing :meth:`year_fraction` and :meth:`name`.
    """

    @abstractmethod
    def year_fraction(self, start: date, end: date) -> float:
        """Return the year fraction between two dates under this convention."""

    @abstractmethod
    def name(self) -> str:
        """Return a stable short name used in canonical form / fingerprint."""


@dataclass(frozen=True)
class OneTwelfth(DayCount):
    """Constant 1/12 per month — actuarial default.

    Ignores varying month length. Matches US VM-20/VM-21, UK/EU SII, and
    IFRS 17 production practice (~80% of life-insurance models).
    """

    def year_fraction(self, start: date, end: date) -> float:
        # Whole-month count from start to end, signed
        months = (end.year - start.year) * 12 + (end.month - start.month)
        # Treat day-of-month as a continuous interpolation within the month
        # so cross-month-boundary calls (rare) still produce a meaningful fraction.
        # (The kernel calls year_fraction at exact period boundaries, where the
        # day-of-month adjustment is zero — so this is a defensive default.)
        return months / 12.0

    def name(self) -> str:
        return "OneTwelfth"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestOneTwelfth -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add DayCount ABC + OneTwelfth (actuarial default)"
```

---

### Task 3: `Actual365Fixed` day-count

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Modify: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/schedule/test_day_count.py`:

```python
from gaspatchio_core.schedule._day_count import Actual365Fixed


class TestActual365Fixed:
    def test_name(self) -> None:
        assert Actual365Fixed().name() == "Actual365Fixed"

    def test_one_calendar_year_in_non_leap(self) -> None:
        # 365 days / 365 fixed = 1.0
        dc = Actual365Fixed()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(1.0)

    def test_one_calendar_year_crossing_leap(self) -> None:
        # 366 days / 365 fixed > 1.0 — Act/365F is *fixed*, ignores leap years
        dc = Actual365Fixed()
        result = dc.year_fraction(date(2024, 1, 1), date(2025, 1, 1))
        assert result == pytest.approx(366 / 365)

    def test_one_month_january_to_february(self) -> None:
        dc = Actual365Fixed()
        # 31 days / 365
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(31 / 365)

    def test_eq_and_hash(self) -> None:
        assert Actual365Fixed() == Actual365Fixed()
        assert hash(Actual365Fixed()) == hash(Actual365Fixed())
        assert Actual365Fixed() != OneTwelfth()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActual365Fixed -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `gaspatchio_core/schedule/_day_count.py`:

```python
@dataclass(frozen=True)
class Actual365Fixed(DayCount):
    """Act/365F — actual days numerator, 365-day fixed denominator.

    UK / sterling and EIOPA-aligned sub-annual interpolation convention.
    Note: 'fixed' means the denominator is *always* 365, even across leap years —
    so a leap-year span of 366 days returns 366/365 > 1.0.
    """

    def year_fraction(self, start: date, end: date) -> float:
        return (end - start).days / 365.0

    def name(self) -> str:
        return "Actual365Fixed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActual365Fixed -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add Actual365Fixed day-count"
```

---

### Task 4: `Actual360` day-count

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Modify: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

```python
from gaspatchio_core.schedule._day_count import Actual360


class TestActual360:
    def test_name(self) -> None:
        assert Actual360().name() == "Actual360"

    def test_one_calendar_year_non_leap(self) -> None:
        # 365 days / 360 > 1.0 — money-market convention overstates the year
        dc = Actual360()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(365 / 360)

    def test_30_day_month(self) -> None:
        dc = Actual360()
        assert dc.year_fraction(date(2025, 4, 1), date(2025, 5, 1)) == pytest.approx(30 / 360)

    def test_31_day_month(self) -> None:
        dc = Actual360()
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(31 / 360)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActual360 -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_day_count.py`:

```python
@dataclass(frozen=True)
class Actual360(DayCount):
    """Act/360 — actual days numerator, 360-day fixed denominator.

    USD money-market convention; commonly used on the asset side
    (interest-rate swaps, money-market discount curves).
    """

    def year_fraction(self, start: date, end: date) -> float:
        return (end - start).days / 360.0

    def name(self) -> str:
        return "Actual360"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActual360 -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add Actual360 day-count"
```

---

### Task 5: `Thirty360` (BondBasis) day-count

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Modify: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

```python
from gaspatchio_core.schedule._day_count import Thirty360


class TestThirty360:
    def test_name(self) -> None:
        assert Thirty360().name() == "Thirty360"

    def test_full_year(self) -> None:
        # Bond basis: each month is 30 days; year is 360 days
        dc = Thirty360()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(1.0)

    def test_one_month_31day(self) -> None:
        # Even a 31-day calendar month counts as 30 days under bond basis
        dc = Thirty360()
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(30 / 360)

    def test_end_of_month_normalisation_d1_31(self) -> None:
        # Per ISDA Bond basis: if D1 = 31, set D1 = 30
        dc = Thirty360()
        # Jan 31 -> Feb 28: D1=31->30, D2=28; days = (28 - 30) + 30*(2-1) + 360*0 = 28
        assert dc.year_fraction(date(2025, 1, 31), date(2025, 2, 28)) == pytest.approx(28 / 360)

    def test_end_of_month_normalisation_d2_31_when_d1_30(self) -> None:
        # If D1 = 30 or 31, and D2 = 31, set D2 = 30
        dc = Thirty360()
        # Jan 30 -> Mar 31: D1=30, D2=31->30, days = (30 - 30) + 30*(3-1) + 0 = 60
        assert dc.year_fraction(date(2025, 1, 30), date(2025, 3, 31)) == pytest.approx(60 / 360)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestThirty360 -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_day_count.py`:

```python
@dataclass(frozen=True)
class Thirty360(DayCount):
    """30/360 ISDA Bond Basis.

    Each month is treated as 30 days, year as 360 days. Two end-of-month
    normalisations:
      - If D1 = 31, set D1 = 30
      - If D2 = 31 and D1 in {30, 31}, set D2 = 30

    Used for legacy bond / mortgage assets and some corporate-debt cashflows.
    """

    def year_fraction(self, start: date, end: date) -> float:
        d1 = 30 if start.day == 31 else start.day
        d2 = end.day
        if d2 == 31 and d1 in (30, 31):
            d2 = 30
        days = (
            (end.year - start.year) * 360
            + (end.month - start.month) * 30
            + (d2 - d1)
        )
        return days / 360.0

    def name(self) -> str:
        return "Thirty360"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestThirty360 -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add Thirty360 (ISDA Bond Basis) day-count"
```

---

### Task 6: `ActualActualISDA` day-count

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Modify: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

```python
from gaspatchio_core.schedule._day_count import ActualActualISDA


class TestActualActualISDA:
    def test_name(self) -> None:
        assert ActualActualISDA().name() == "ActualActualISDA"

    def test_full_non_leap_year(self) -> None:
        # 365 days entirely in a non-leap year -> 1.0
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(1.0)

    def test_full_leap_year(self) -> None:
        # 366 days entirely in a leap year (2024) -> 1.0
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2024, 1, 1), date(2025, 1, 1)) == pytest.approx(1.0)

    def test_crossing_leap_boundary(self) -> None:
        # ISDA splits the period at the year boundary:
        # 2024-06-01 to 2025-06-01 -> portion in 2024 / 366 + portion in 2025 / 365
        dc = ActualActualISDA()
        days_in_2024 = (date(2025, 1, 1) - date(2024, 6, 1)).days  # 214
        days_in_2025 = (date(2025, 6, 1) - date(2025, 1, 1)).days  # 151
        expected = days_in_2024 / 366 + days_in_2025 / 365
        assert dc.year_fraction(date(2024, 6, 1), date(2025, 6, 1)) == pytest.approx(expected)

    def test_one_month_in_leap_february(self) -> None:
        # Feb 1 2024 to Mar 1 2024 -> 29 days, all in leap year -> 29/366
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2024, 2, 1), date(2024, 3, 1)) == pytest.approx(29 / 366)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActualActualISDA -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_day_count.py`:

```python
def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass(frozen=True)
class ActualActualISDA(DayCount):
    """Act/Act ISDA — actual days, split at year boundaries.

    For a period crossing a year boundary, the year fraction is the sum of:
      - days in the start year / (366 if start year is leap else 365)
      - days in the end year / (366 if end year is leap else 365)

    Precise leap-year handling — preferred for IFRS 17 / general use.
    """

    def year_fraction(self, start: date, end: date) -> float:
        if start.year == end.year:
            denom = 366.0 if _is_leap_year(start.year) else 365.0
            return (end - start).days / denom

        # Cross-year period: split at Jan 1 of end.year
        boundary = date(end.year, 1, 1)
        first_part_days = (boundary - start).days
        first_part_denom = 366.0 if _is_leap_year(start.year) else 365.0
        second_part_days = (end - boundary).days
        second_part_denom = 366.0 if _is_leap_year(end.year) else 365.0

        # Multi-year periods: contribute full whole years between
        whole_years = end.year - start.year - 1
        return (
            first_part_days / first_part_denom
            + whole_years
            + second_part_days / second_part_denom
        )

    def name(self) -> str:
        return "ActualActualISDA"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestActualActualISDA -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add ActualActualISDA day-count"
```

---

### Task 7: DayCount registry + `from_name()` lookup

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_day_count.py`
- Modify: `bindings/python/tests/schedule/test_day_count.py`

- [ ] **Step 1: Write the failing test**

```python
class TestDayCountRegistry:
    def test_resolve_by_name_returns_instance(self) -> None:
        from gaspatchio_core.schedule._day_count import day_count_from_name

        assert day_count_from_name("OneTwelfth") == OneTwelfth()
        assert day_count_from_name("Actual365Fixed") == Actual365Fixed()
        assert day_count_from_name("Actual360") == Actual360()
        assert day_count_from_name("Thirty360") == Thirty360()
        assert day_count_from_name("ActualActualISDA") == ActualActualISDA()

    def test_unknown_name_raises_with_suggestions(self) -> None:
        from gaspatchio_core.schedule._day_count import day_count_from_name

        # difflib.get_close_matches('Act365', ...) actually returns Actual360
        # (ratio 0.667) over Actual365Fixed (ratio 0.6) at n=1. The test verifies
        # the suggestion *mechanism* fires; the exact name returned is secondary.
        # If/when we improve UX (e.g., n=2 or token-aware), update this assertion.
        with pytest.raises(ValueError, match="unknown day-count 'Act365' — did you mean 'Actual360'"):
            day_count_from_name("Act365")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py::TestDayCountRegistry -v`
Expected: FAIL — `ImportError: cannot import name 'day_count_from_name'`.

- [ ] **Step 3: Implement**

Append to `_day_count.py`:

```python
from difflib import get_close_matches

_DAY_COUNT_BY_NAME: dict[str, type[DayCount]] = {
    "OneTwelfth": OneTwelfth,
    "Actual365Fixed": Actual365Fixed,
    "Actual360": Actual360,
    "Thirty360": Thirty360,
    "ActualActualISDA": ActualActualISDA,
}


def day_count_from_name(name: str) -> DayCount:
    """Resolve a day-count by canonical name. Used by canonical-form deserialisation."""
    cls = _DAY_COUNT_BY_NAME.get(name)
    if cls is None:
        suggestions = get_close_matches(name, list(_DAY_COUNT_BY_NAME), n=1, cutoff=0.5)
        hint = f" — did you mean '{suggestions[0]}'?" if suggestions else ""
        raise ValueError(f"unknown day-count '{name}'{hint}")
    return cls()


__all__ = [
    "DayCount",
    "OneTwelfth",
    "Actual365Fixed",
    "Actual360",
    "Thirty360",
    "ActualActualISDA",
    "day_count_from_name",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_day_count.py -v`
Expected: PASS — 5 classes' worth of tests + the registry tests, ~25 total.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_day_count.py bindings/python/tests/schedule/test_day_count.py
git commit -m "feat(schedule): add day_count_from_name registry"
```

---

### Task 8: `BusinessDayConvention` enum + `adjust()`

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/_business_day.py`
- Create: `bindings/python/tests/schedule/test_business_day.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_business_day.py
"""BusinessDayConvention adjustment tests."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._business_day import BusinessDayConvention


class TestBusinessDayConventionEnum:
    def test_four_values(self) -> None:
        assert {c.name for c in BusinessDayConvention} == {
            "FOLLOWING",
            "MODIFIED_FOLLOWING",
            "PRECEDING",
            "UNADJUSTED",
        }

    def test_canonical_names(self) -> None:
        assert BusinessDayConvention.FOLLOWING.canonical_name() == "Following"
        assert BusinessDayConvention.MODIFIED_FOLLOWING.canonical_name() == "ModifiedFollowing"
        assert BusinessDayConvention.PRECEDING.canonical_name() == "Preceding"
        assert BusinessDayConvention.UNADJUSTED.canonical_name() == "Unadjusted"


class TestAdjustWithoutCalendar:
    """Adjustment with no calendar input — pure weekend handling."""

    def test_unadjusted_returns_input(self) -> None:
        # 2025-03-15 is a Saturday
        d = date(2025, 3, 15)
        # No calendar -> no adjustment expected for any convention but Unadjusted always identity
        assert BusinessDayConvention.UNADJUSTED.adjust(d, calendar=None) == d


class TestAdjustWithWeekendOnlyRules:
    """Without a calendar, only weekend rules apply for non-Unadjusted."""

    def test_following_pushes_saturday_to_monday(self) -> None:
        # 2025-03-15 (Sat) -> following business day with weekend-only rule: 2025-03-17 (Mon)
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 17)

    def test_preceding_pulls_saturday_to_friday(self) -> None:
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.PRECEDING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 14)

    def test_modified_following_stays_in_month(self) -> None:
        # 2025-05-31 (Sat); following would push to Jun 2, but mod-following pulls back to May 30 (Fri)
        d = date(2025, 5, 31)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 5, 30)

    def test_modified_following_uses_following_when_within_month(self) -> None:
        # 2025-03-15 (Sat); mod-following pushes to Mon Mar 17 (still in March)
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 17)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_business_day.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/schedule/_business_day.py
"""BusinessDayConvention — anniversary / period-boundary roll rules."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.schedule._calendar import Calendar


class BusinessDayConvention(Enum):
    """How to roll a date that falls on a non-business day.

    Four conventions cover real actuarial use; all others (e.g.
    ``HalfMonthModifiedFollowing``, ``Nearest``) are fixed-income edge
    cases not in the curated set.
    """

    UNADJUSTED = "Unadjusted"
    FOLLOWING = "Following"
    MODIFIED_FOLLOWING = "ModifiedFollowing"
    PRECEDING = "Preceding"

    def canonical_name(self) -> str:
        """Stable string name used in canonical-form fingerprinting."""
        return self.value

    def adjust(self, d: date, calendar: Calendar | None) -> date:
        """Return ``d`` rolled to a business day under this convention.

        ``calendar`` may be ``None``, in which case only weekend rules apply.
        """
        if self is BusinessDayConvention.UNADJUSTED:
            return d

        if self is BusinessDayConvention.FOLLOWING:
            return _roll_forward(d, calendar)

        if self is BusinessDayConvention.PRECEDING:
            return _roll_back(d, calendar)

        if self is BusinessDayConvention.MODIFIED_FOLLOWING:
            forward = _roll_forward(d, calendar)
            if forward.month == d.month:
                return forward
            return _roll_back(d, calendar)

        # Exhaustive — but mypy doesn't know that
        msg = f"unhandled convention {self!r}"
        raise AssertionError(msg)


def _is_business_day(d: date, calendar: Calendar | None) -> bool:
    if d.weekday() >= 5:  # Saturday / Sunday
        return False
    if calendar is None:
        return True
    return calendar.is_business_day(d)


def _roll_forward(d: date, calendar: Calendar | None) -> date:
    while not _is_business_day(d, calendar):
        d = d + timedelta(days=1)
    return d


def _roll_back(d: date, calendar: Calendar | None) -> date:
    while not _is_business_day(d, calendar):
        d = d - timedelta(days=1)
    return d


__all__ = ["BusinessDayConvention"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_business_day.py -v`
Expected: PASS — ~7 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_business_day.py bindings/python/tests/schedule/test_business_day.py
git commit -m "feat(schedule): add BusinessDayConvention with adjust()"
```

---

### Task 9: `Calendar` ABC + `NullCalendar` (the default)

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/_calendar.py`
- Create: `bindings/python/tests/schedule/test_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_calendar.py
"""Calendar tests — holiday membership and business-day identification."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._calendar import Calendar, NullCalendar


class TestNullCalendar:
    def test_name(self) -> None:
        assert NullCalendar().name() == "NullCalendar"

    def test_every_weekday_is_business_day(self) -> None:
        cal = NullCalendar()
        assert cal.is_business_day(date(2025, 3, 17))  # Mon
        assert cal.is_business_day(date(2025, 3, 21))  # Fri

    def test_weekends_are_business_days_too(self) -> None:
        # NullCalendar is "every day is a business day" — even weekends
        # (Weekend rolling is handled by BusinessDayConvention with calendar=None.)
        cal = NullCalendar()
        assert cal.is_business_day(date(2025, 3, 15))  # Sat
        assert cal.is_business_day(date(2025, 3, 16))  # Sun

    def test_eq_and_hash(self) -> None:
        assert NullCalendar() == NullCalendar()
        assert hash(NullCalendar()) == hash(NullCalendar())

    def test_subclass_of_calendar(self) -> None:
        assert isinstance(NullCalendar(), Calendar)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py::TestNullCalendar -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/schedule/_calendar.py
"""Calendar typed primitive — holiday-aware business-day predicate.

Phase 1 ships four calendars: NullCalendar (default — every day is a
business day, matches VM-20/VM-21/IFRS 17 production practice), TARGET
(Eurozone), UnitedKingdom, and UnitedStates. JointCalendar and
BespokeCalendar are escape hatches for non-curated cases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class Calendar(ABC):
    """Abstract calendar. Concrete subclasses define holiday membership."""

    @abstractmethod
    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a business day under this calendar."""

    @abstractmethod
    def name(self) -> str:
        """Stable short name used in canonical-form fingerprinting."""


@dataclass(frozen=True)
class NullCalendar(Calendar):
    """Every day is a business day.

    Matches US VM-20/VM-21, UK/EU SII, and IFRS 17 production practice
    where premium-due, lapse, and death dates are *not* adjusted for
    weekends or holidays. Default in :class:`Schedule`.
    """

    def is_business_day(self, d: date) -> bool:  # noqa: ARG002 — every day is a business day
        return True

    def name(self) -> str:
        return "NullCalendar"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py::TestNullCalendar -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_calendar.py bindings/python/tests/schedule/test_calendar.py
git commit -m "feat(schedule): add Calendar ABC + NullCalendar (default)"
```

---

### Task 10: Real calendars — TARGET, UnitedKingdom, UnitedStates

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_calendar.py`
- Modify: `bindings/python/tests/schedule/test_calendar.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/schedule/test_calendar.py`:

```python
from gaspatchio_core.schedule._calendar import (
    TARGET,
    UnitedKingdom,
    UnitedStates,
)


class TestTARGET:
    def test_name(self) -> None:
        assert TARGET().name() == "TARGET"

    def test_good_friday_2025_is_holiday(self) -> None:
        # 2025-04-18 is Good Friday; TARGET2 is closed
        assert not TARGET().is_business_day(date(2025, 4, 18))

    def test_easter_monday_2025_is_holiday(self) -> None:
        # 2025-04-21 is Easter Monday
        assert not TARGET().is_business_day(date(2025, 4, 21))

    def test_normal_weekday_is_business(self) -> None:
        assert TARGET().is_business_day(date(2025, 3, 17))  # Mon

    def test_christmas_is_holiday(self) -> None:
        assert not TARGET().is_business_day(date(2025, 12, 25))


class TestUnitedKingdom:
    def test_name(self) -> None:
        assert UnitedKingdom().name() == "UnitedKingdom"

    def test_good_friday_2025_is_holiday(self) -> None:
        assert not UnitedKingdom().is_business_day(date(2025, 4, 18))

    def test_early_may_bank_holiday_2025(self) -> None:
        # 2025-05-05 is the early May bank holiday in the UK
        assert not UnitedKingdom().is_business_day(date(2025, 5, 5))

    def test_normal_weekday_is_business(self) -> None:
        assert UnitedKingdom().is_business_day(date(2025, 3, 17))


class TestUnitedStates:
    def test_name(self) -> None:
        assert UnitedStates().name() == "UnitedStates"

    def test_mlk_day_2025(self) -> None:
        # 2025-01-20 — MLK Day
        assert not UnitedStates().is_business_day(date(2025, 1, 20))

    def test_thanksgiving_2025(self) -> None:
        # 2025-11-27 — Thanksgiving (4th Thursday of November)
        assert not UnitedStates().is_business_day(date(2025, 11, 27))

    def test_normal_weekday_is_business(self) -> None:
        assert UnitedStates().is_business_day(date(2025, 3, 17))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py -v -k "TARGET or UnitedKingdom or UnitedStates"`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_calendar.py`:

```python
import functools

import holidays as _hols  # python-holidays


@functools.lru_cache(maxsize=4)
def _ecb_holidays_for_years(start_year: int, end_year: int) -> set[date]:
    """TARGET2 closing days. Cached — building the holiday set is non-trivial."""
    h: set[date] = set()
    for year in range(start_year, end_year + 1):
        # python-holidays exposes the ECB / TARGET2 list under financial.EuropeanCentralBank
        for d in _hols.financial_holidays("ECB", years=year):
            h.add(d)
    return h


@dataclass(frozen=True)
class TARGET(Calendar):
    """TARGET2 / Eurozone settlement calendar.

    Uses the python-holidays ECB / TARGET2 closing-day list:
    Jan 1, Good Friday, Easter Monday, May 1 (Labour Day),
    Dec 25 (Christmas), Dec 26 (Boxing Day).
    """

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        return d not in _ecb_holidays_for_years(d.year, d.year)

    def name(self) -> str:
        return "TARGET"


@functools.lru_cache(maxsize=64)
def _uk_holidays_for_year(year: int) -> set[date]:
    return set(_hols.country_holidays("GB", subdiv="ENG", years=year).keys())


@dataclass(frozen=True)
class UnitedKingdom(Calendar):
    """UK calendar — England-and-Wales bank holidays."""

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        return d not in _uk_holidays_for_year(d.year)

    def name(self) -> str:
        return "UnitedKingdom"


@functools.lru_cache(maxsize=64)
def _us_holidays_for_year(year: int) -> set[date]:
    return set(_hols.country_holidays("US", years=year).keys())


@dataclass(frozen=True)
class UnitedStates(Calendar):
    """US federal holiday calendar.

    Used for asset-side cashflow modelling. Liability-side projections
    typically use NullCalendar (no business-day adjustment).
    """

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        return d not in _us_holidays_for_year(d.year)

    def name(self) -> str:
        return "UnitedStates"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py -v`
Expected: PASS — ~17 tests across all four calendars.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_calendar.py bindings/python/tests/schedule/test_calendar.py
git commit -m "feat(schedule): add TARGET / UnitedKingdom / UnitedStates calendars"
```

---

### Task 11: Calendar escape hatches — `JointCalendar` + `BespokeCalendar`

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_calendar.py`
- Modify: `bindings/python/tests/schedule/test_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
from gaspatchio_core.schedule._calendar import BespokeCalendar, JointCalendar


class TestJointCalendar:
    def test_name(self) -> None:
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        assert c.name() == "Joint(UnitedStates,UnitedKingdom)"

    def test_holiday_in_either_is_holiday(self) -> None:
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        # 2025-01-20 is MLK Day (US, not UK) — joint should call it a holiday
        assert not c.is_business_day(date(2025, 1, 20))
        # 2025-05-05 is UK May bank holiday (not US) — joint should still call it a holiday
        assert not c.is_business_day(date(2025, 5, 5))

    def test_business_day_only_when_business_in_both(self) -> None:
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        assert c.is_business_day(date(2025, 3, 17))  # Mon, not a holiday in either


class TestBespokeCalendar:
    def test_name_default(self) -> None:
        c = BespokeCalendar(holidays=frozenset())
        assert c.name() == "Bespoke"

    def test_name_with_label(self) -> None:
        c = BespokeCalendar(holidays=frozenset(), label="MyCorp2025")
        assert c.name() == "Bespoke[MyCorp2025]"

    def test_supplied_holiday_blocks_business_day(self) -> None:
        c = BespokeCalendar(holidays=frozenset({date(2025, 7, 15)}))
        assert not c.is_business_day(date(2025, 7, 15))
        assert c.is_business_day(date(2025, 7, 16))

    def test_weekend_still_excluded(self) -> None:
        c = BespokeCalendar(holidays=frozenset())
        assert not c.is_business_day(date(2025, 3, 15))  # Sat
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py -v -k "JointCalendar or BespokeCalendar"`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_calendar.py`:

```python
@dataclass(frozen=True)
class JointCalendar(Calendar):
    """Two-calendar union — a date is a holiday if it's a holiday in *either*."""

    left: Calendar
    right: Calendar

    def is_business_day(self, d: date) -> bool:
        return self.left.is_business_day(d) and self.right.is_business_day(d)

    def name(self) -> str:
        return f"Joint({self.left.name()},{self.right.name()})"


@dataclass(frozen=True)
class BespokeCalendar(Calendar):
    """User-defined holiday set. Use ``label`` to give canonical-form a stable name."""

    holidays: frozenset[date]
    label: str | None = None

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        return d not in self.holidays

    def name(self) -> str:
        return f"Bespoke[{self.label}]" if self.label else "Bespoke"


__all__ = [
    "Calendar",
    "NullCalendar",
    "TARGET",
    "UnitedKingdom",
    "UnitedStates",
    "JointCalendar",
    "BespokeCalendar",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py -v`
Expected: PASS — ~24 tests total.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_calendar.py bindings/python/tests/schedule/test_calendar.py
git commit -m "feat(schedule): add JointCalendar + BespokeCalendar escape hatches"
```

---

### Task 12: BusinessDayConvention adjust with real calendars (regression)

**Files:**
- Modify: `bindings/python/tests/schedule/test_business_day.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from gaspatchio_core.schedule._calendar import UnitedStates


class TestAdjustWithRealCalendar:
    def test_following_skips_us_holiday(self) -> None:
        # 2025-01-20 (Mon) is MLK Day in US -> Following should advance to Tue Jan 21
        d = date(2025, 1, 20)
        adjusted = BusinessDayConvention.FOLLOWING.adjust(d, calendar=UnitedStates())
        assert adjusted == date(2025, 1, 21)

    def test_preceding_skips_us_holiday(self) -> None:
        d = date(2025, 1, 20)
        adjusted = BusinessDayConvention.PRECEDING.adjust(d, calendar=UnitedStates())
        # Friday Jan 17 (preceding business day, since Jan 18-19 are weekend)
        assert adjusted == date(2025, 1, 17)

    def test_modified_following_with_us_calendar_stays_in_month(self) -> None:
        # 2025-12-25 (Thu) — Christmas — and Dec 26 is Friday, also a holiday in some catalogs
        # 2025-12-25 is Christmas, holiday in US; 2025-12-26 is also a US federal holiday in 2025? Actually no — only Christmas Day.
        # So Following pushes 2025-12-25 -> 2025-12-26 (Friday, not holiday). Stays in month.
        d = date(2025, 12, 25)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(d, calendar=UnitedStates())
        assert adjusted == date(2025, 12, 26)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_business_day.py::TestAdjustWithRealCalendar -v`
Expected: PASS — 3 tests. (No new code needed; Task 8's adjust already accepts a Calendar.)

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/schedule/test_business_day.py
git commit -m "test(schedule): regression — BD adjust composes with real calendars"
```

---

### Task 13: `Calendar.from_name()` registry

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_calendar.py`
- Modify: `bindings/python/tests/schedule/test_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
class TestCalendarRegistry:
    def test_resolve_curated_names(self) -> None:
        from gaspatchio_core.schedule._calendar import calendar_from_name

        assert calendar_from_name("NullCalendar") == NullCalendar()
        assert calendar_from_name("TARGET") == TARGET()
        assert calendar_from_name("UnitedKingdom") == UnitedKingdom()
        assert calendar_from_name("UnitedStates") == UnitedStates()

    def test_unknown_name_raises_with_suggestions(self) -> None:
        from gaspatchio_core.schedule._calendar import calendar_from_name

        with pytest.raises(ValueError, match="unknown calendar 'US'"):
            calendar_from_name("US")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py::TestCalendarRegistry -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `_calendar.py`:

```python
from difflib import get_close_matches

_CALENDAR_BY_NAME: dict[str, type[Calendar]] = {
    "NullCalendar": NullCalendar,
    "TARGET": TARGET,
    "UnitedKingdom": UnitedKingdom,
    "UnitedStates": UnitedStates,
}


def calendar_from_name(name: str) -> Calendar:
    """Resolve a curated calendar by canonical name.

    Joint and Bespoke calendars are not in the curated set — they must be
    reconstructed from their structural args, which is the canonical form's job.
    """
    cls = _CALENDAR_BY_NAME.get(name)
    if cls is None:
        suggestions = get_close_matches(name, list(_CALENDAR_BY_NAME), n=1, cutoff=0.5)
        hint = f" — did you mean '{suggestions[0]}'?" if suggestions else ""
        raise ValueError(f"unknown calendar '{name}'{hint}")
    return cls()
```

Update the `__all__` to add `calendar_from_name`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_calendar.py -v`
Expected: PASS — full file passes.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_calendar.py bindings/python/tests/schedule/test_calendar.py
git commit -m "feat(schedule): add calendar_from_name registry (curated only)"
```

---

### Task 14: `Schedule.from_calendar_grid` — shared grid + month-end anchor

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Create: `bindings/python/tests/schedule/test_schedule_constructors.py`
- Create: `bindings/python/tests/schedule/conftest.py`

- [ ] **Step 1: Write the conftest**

```python
# bindings/python/tests/schedule/conftest.py
"""Shared fixtures for schedule tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest


@pytest.fixture
def sample_policies() -> pl.DataFrame:
    """Three policies with varying inception dates spanning a leap year."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "contract_inception": [
                date(2024, 2, 29),  # leap-day inception
                date(2024, 3, 15),  # mid-month inception
                date(2025, 6, 1),   # month-start inception in non-leap year
            ],
        }
    )
```

- [ ] **Step 2: Write the failing test**

```python
# bindings/python/tests/schedule/test_schedule_constructors.py
"""Schedule constructor tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._day_count import OneTwelfth
from gaspatchio_core.schedule._schedule import Schedule


class TestFromCalendarGrid:
    def test_default_anchor_normalises_start_to_month_end(self) -> None:
        # Mid-month start_date with default anchor='month_end' -> Mar 31, 2025
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
        )
        assert sched.start_date == date(2025, 3, 31)
        assert sched.n_periods == 12
        assert sched.frequency == "1M"
        assert sched.anchor == "month_end"
        assert sched.calendar == NullCalendar()
        assert sched.day_count == OneTwelfth()
        assert sched.convention == BusinessDayConvention.UNADJUSTED

    def test_anchor_exact_date_does_not_normalise(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
            anchor="exact_date",
        )
        assert sched.start_date == date(2025, 3, 15)

    def test_real_calendar_changes_default_convention_to_modified_following(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=12,
            frequency="1M",
            calendar=UnitedStates(),
        )
        assert sched.convention == BusinessDayConvention.MODIFIED_FOLLOWING

    def test_explicit_convention_overrides_context_default(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=12,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.UNADJUSTED,
        )
        assert sched.convention == BusinessDayConvention.UNADJUSTED

    def test_unsupported_frequency_raises(self) -> None:
        with pytest.raises(ValueError, match="frequency"):
            Schedule.from_calendar_grid(
                start_date=date(2025, 3, 31),
                n_periods=12,
                frequency="2.5W",  # not in supported set
            )

    def test_anchor_month_start(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
            anchor="month_start",
        )
        assert sched.start_date == date(2025, 3, 1)

    def test_anchor_year_end(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1Y",
            anchor="year_end",
        )
        assert sched.start_date == date(2025, 12, 31)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py::TestFromCalendarGrid -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 4: Implement**

```python
# bindings/python/gaspatchio_core/schedule/_schedule.py
"""Schedule typed primitive — period boundaries + day-count + calendar.

Two named constructors:
  - ``from_calendar_grid`` — shared grid for all policies; useful for cohort
    aggregation and SII reporting. Mid-month starts normalise to month-end by
    default to match US/UK/EU production practice.
  - ``from_inception`` — per-policy grid anchored on a column of inception
    dates. Anniversary semantics intrinsic.

Phase 1 commitments:
  - Default convention: ``OneTwelfth + NullCalendar`` (matches ~80% of life
    insurance production).
  - Business-day default: ``Unadjusted`` with ``NullCalendar``,
    ``ModifiedFollowing`` with any real calendar.
  - Termination semantics: full-period; no partial-dt at lapse / contract
    boundary (deferred to Phase 2).
  - Reporting-grid aggregation deferred to Phase 2.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import Calendar, NullCalendar
from gaspatchio_core.schedule._day_count import DayCount, OneTwelfth

Anchor = Literal["month_end", "exact_date", "month_start", "year_end"]
Frequency = Literal["1M", "3M", "6M", "1Y", "1D", "1W"]

_SUPPORTED_FREQUENCIES: frozenset[str] = frozenset({"1M", "3M", "6M", "1Y", "1D", "1W"})


def _last_day_of_month(d: date) -> date:
    last = _stdlib_calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)


def _last_day_of_year(d: date) -> date:
    return date(d.year, 12, 31)


def _normalise_anchor(d: date, anchor: Anchor) -> date:
    if anchor == "exact_date":
        return d
    if anchor == "month_end":
        return _last_day_of_month(d)
    if anchor == "month_start":
        return date(d.year, d.month, 1)
    if anchor == "year_end":
        return _last_day_of_year(d)
    msg = f"unsupported anchor {anchor!r}"
    raise ValueError(msg)


def _default_convention(calendar: Calendar) -> BusinessDayConvention:
    if isinstance(calendar, NullCalendar):
        return BusinessDayConvention.UNADJUSTED
    return BusinessDayConvention.MODIFIED_FOLLOWING


@dataclass(frozen=True)
class Schedule:
    """Typed schedule — periods, day-count, calendar, BD convention.

    Construct via :meth:`from_calendar_grid` (shared grid) or
    :meth:`from_inception` (per-policy column-anchored). Direct construction
    is intentionally awkward — use the classmethods.
    """

    n_periods: int
    frequency: Frequency
    calendar: Calendar
    convention: BusinessDayConvention
    day_count: DayCount
    anchor: Anchor
    # One of the next two is set; the other is None depending on constructor.
    start_date: date | None
    inception_column: str | None
    # Internal flag — distinguishes "from_calendar_grid" vs "from_inception"
    # in canonical form without inferring from None-ness alone.
    _kind: Literal["from_calendar_grid", "from_inception"] = field(default="from_calendar_grid")

    @classmethod
    def from_calendar_grid(
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Frequency,
        anchor: Anchor = "month_end",
        calendar: Calendar | None = None,
        convention: BusinessDayConvention | None = None,
        day_count: DayCount | None = None,
    ) -> Schedule:
        """Shared grid for all policies. Mid-month start_date is normalised
        per ``anchor`` (default: month-end) to match production practice.
        """
        if frequency not in _SUPPORTED_FREQUENCIES:
            msg = f"unsupported frequency {frequency!r}; expected one of {sorted(_SUPPORTED_FREQUENCIES)}"
            raise ValueError(msg)

        cal: Calendar = calendar or NullCalendar()
        conv: BusinessDayConvention = convention or _default_convention(cal)
        dc: DayCount = day_count or OneTwelfth()
        normalised = _normalise_anchor(start_date, anchor)
        return cls(
            n_periods=n_periods,
            frequency=frequency,
            calendar=cal,
            convention=conv,
            day_count=dc,
            anchor=anchor,
            start_date=normalised,
            inception_column=None,
            _kind="from_calendar_grid",
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py::TestFromCalendarGrid -v`
Expected: PASS — 7 tests.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_constructors.py bindings/python/tests/schedule/conftest.py
git commit -m "feat(schedule): add Schedule.from_calendar_grid with anchor + context-dependent convention default"
```

---

### Task 15: `Schedule.from_inception` — per-policy anchored

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Modify: `bindings/python/tests/schedule/test_schedule_constructors.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestFromInception:
    def test_basic_construction_with_column_name(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
        )
        assert sched.inception_column == "contract_inception"
        assert sched.start_date is None
        assert sched.n_periods == 240
        assert sched.frequency == "1M"
        assert sched.calendar == NullCalendar()
        assert sched.convention == BusinessDayConvention.UNADJUSTED
        assert sched.day_count == OneTwelfth()
        assert sched._kind == "from_inception"

    def test_no_anchor_param_for_from_inception(self) -> None:
        # from_inception's anchor IS the inception column — no anchor param accepted
        with pytest.raises(TypeError, match="anchor"):
            Schedule.from_inception(  # type: ignore[call-arg]
                inception_column="contract_inception",
                n_periods=240,
                frequency="1M",
                anchor="month_end",
            )

    def test_real_calendar_changes_default_convention(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
            calendar=UnitedStates(),
        )
        assert sched.convention == BusinessDayConvention.MODIFIED_FOLLOWING

    def test_unsupported_frequency_raises(self) -> None:
        with pytest.raises(ValueError, match="frequency"):
            Schedule.from_inception(
                inception_column="contract_inception",
                n_periods=240,
                frequency="2.5W",
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py::TestFromInception -v`
Expected: FAIL — `AttributeError: type object 'Schedule' has no attribute 'from_inception'`.

- [ ] **Step 3: Implement**

Append the classmethod to `Schedule` in `_schedule.py`:

```python
    @classmethod
    def from_inception(
        cls,
        *,
        inception_column: str,
        n_periods: int,
        frequency: Frequency,
        calendar: Calendar | None = None,
        convention: BusinessDayConvention | None = None,
        day_count: DayCount | None = None,
    ) -> Schedule:
        """Per-policy schedule anchored on a column of inception dates.

        Each row gets its own period grid starting at ``inception_column[row]``.
        Anniversary semantics are intrinsic — the inception date IS the anchor,
        so no ``anchor`` parameter is accepted here.
        """
        if frequency not in _SUPPORTED_FREQUENCIES:
            msg = f"unsupported frequency {frequency!r}; expected one of {sorted(_SUPPORTED_FREQUENCIES)}"
            raise ValueError(msg)

        cal: Calendar = calendar or NullCalendar()
        conv: BusinessDayConvention = convention or _default_convention(cal)
        dc: DayCount = day_count or OneTwelfth()
        return cls(
            n_periods=n_periods,
            frequency=frequency,
            calendar=cal,
            convention=conv,
            day_count=dc,
            anchor="exact_date",  # placeholder — irrelevant for from_inception
            start_date=None,
            inception_column=inception_column,
            _kind="from_inception",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py -v`
Expected: PASS — both `TestFromCalendarGrid` and `TestFromInception` (~11 tests total).

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_constructors.py
git commit -m "feat(schedule): add Schedule.from_inception (per-policy column-anchored)"
```

---

### Task 16: Frequency → month-step helper + `period_dates()` for `from_calendar_grid`

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Create: `bindings/python/tests/schedule/test_schedule_period_dates.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_schedule_period_dates.py
"""Schedule period_dates output tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._day_count import OneTwelfth
from gaspatchio_core.schedule._schedule import Schedule


class TestFromCalendarGridPeriodDates:
    def test_monthly_12_periods_from_jan_31(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        dates = sched.period_dates()
        assert isinstance(dates, list)
        assert len(dates) == 13  # 12 periods -> 13 boundaries (bop[0] .. eop[11])
        assert dates[0] == date(2025, 1, 31)
        # Month-end propagated forward through Feb (month-end of Feb in non-leap = 28th)
        assert dates[1] == date(2025, 2, 28)
        assert dates[12] == date(2026, 1, 31)

    def test_quarterly_4_periods(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=4,
            frequency="3M",
        )
        dates = sched.period_dates()
        assert dates == [
            date(2025, 3, 31),
            date(2025, 6, 30),
            date(2025, 9, 30),
            date(2025, 12, 31),
            date(2026, 3, 31),
        ]

    def test_annual_3_periods(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 12, 31),
            n_periods=3,
            frequency="1Y",
        )
        dates = sched.period_dates()
        assert dates == [
            date(2025, 12, 31),
            date(2026, 12, 31),
            date(2027, 12, 31),
            date(2028, 12, 31),
        ]

    def test_business_day_convention_following_skips_us_holiday(self) -> None:
        # Start Jan 1 2025 (US holiday — New Year's). Following convention rolls to Jan 2.
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 1),
            n_periods=2,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.FOLLOWING,
            anchor="exact_date",  # don't normalise to month-end for this test
        )
        dates = sched.period_dates()
        # Jan 1 2025 -> Following -> Jan 2 (Thu, business day)
        assert dates[0] == date(2025, 1, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_period_dates.py::TestFromCalendarGridPeriodDates -v`
Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'period_dates'`.

- [ ] **Step 3: Implement**

Append to `_schedule.py`:

```python
from dateutil.relativedelta import relativedelta


def _period_step_kwargs(frequency: Frequency) -> dict[str, int]:
    """Translate a frequency string into a ``relativedelta`` kwargs dict."""
    return {
        "1M": {"months": 1},
        "3M": {"months": 3},
        "6M": {"months": 6},
        "1Y": {"years": 1},
        "1D": {"days": 1},
        "1W": {"weeks": 1},
    }[frequency]


def _step_date(d: date, frequency: Frequency, anchor: Anchor) -> date:
    """Advance ``d`` by one period under ``frequency``.

    For monthly/yearly frequencies and a month-end / year-end anchor, the
    natural ``relativedelta`` rule already preserves the convention because
    Feb 28 + 1M = Mar 28, Mar 31 + 1M = Apr 30 (capped) — but to keep
    month-end stickiness we explicitly re-normalise to month-end after each
    step when the anchor demands it.
    """
    next_d = d + relativedelta(**_period_step_kwargs(frequency))
    if anchor == "month_end" and frequency in ("1M", "3M", "6M"):
        next_d = _last_day_of_month(next_d)
    if anchor == "year_end" and frequency == "1Y":
        next_d = _last_day_of_year(next_d)
    return next_d
```

Then add the method on `Schedule`:

```python
    def period_dates(self) -> list[date]:
        """Return the period boundary dates (length n_periods + 1).

        Only valid for ``from_calendar_grid`` schedules — per-policy grids
        produce a Polars expression, not a Python list (see :meth:`period_dates_expr`).
        """
        if self._kind != "from_calendar_grid":
            msg = "period_dates() is only valid for from_calendar_grid schedules; use period_dates_expr() for from_inception"
            raise ValueError(msg)
        assert self.start_date is not None
        out: list[date] = [self.start_date]
        d = self.start_date
        for _ in range(self.n_periods):
            d = _step_date(d, self.frequency, self.anchor)
            d = self.convention.adjust(d, self.calendar)
            out.append(d)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_period_dates.py::TestFromCalendarGridPeriodDates -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_period_dates.py
git commit -m "feat(schedule): add period_dates() for from_calendar_grid"
```

---

### Task 17: `period_dates_expr()` for `from_inception` (per-row Polars Expr)

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Modify: `bindings/python/tests/schedule/test_schedule_period_dates.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestFromInceptionPeriodDatesExpr:
    def test_basic_per_row_dates(self, sample_policies: pl.DataFrame) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
        )
        df = sample_policies.with_columns(period_dates=sched.period_dates_expr())
        result = df.get_column("period_dates").to_list()

        # Three rows: leap-day inception, mid-month inception, month-start inception
        # Row 0: 2024-02-29 → +1M → 2024-03-29 → +1M → 2024-04-29 → +1M → 2024-05-29 (4 boundaries for 3 periods)
        assert result[0] == [date(2024, 2, 29), date(2024, 3, 29), date(2024, 4, 29), date(2024, 5, 29)]
        # Row 1: 2024-03-15 (Friday, NullCalendar so unadjusted)
        assert result[1] == [date(2024, 3, 15), date(2024, 4, 15), date(2024, 5, 15), date(2024, 6, 15)]
        # Row 2: 2025-06-01 (Sunday, NullCalendar so unadjusted)
        assert result[2] == [date(2025, 6, 1), date(2025, 7, 1), date(2025, 8, 1), date(2025, 9, 1)]

    def test_period_dates_count_matches_n_periods_plus_one(self, sample_policies: pl.DataFrame) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=12,
            frequency="1M",
        )
        df = sample_policies.with_columns(period_dates=sched.period_dates_expr())
        for row_dates in df.get_column("period_dates").to_list():
            assert len(row_dates) == 13  # 12 periods → 13 boundaries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_period_dates.py::TestFromInceptionPeriodDatesExpr -v`
Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'period_dates_expr'`.

- [ ] **Step 3: Implement**

Append to `_schedule.py`:

```python
import polars as pl


def _build_period_offsets(
    frequency: Frequency,
    n_periods: int,
) -> list[relativedelta]:
    """Pre-compute the ``relativedelta`` offsets for each period boundary."""
    step = _period_step_kwargs(frequency)
    return [relativedelta(**{k: v * t for k, v in step.items()}) for t in range(n_periods + 1)]
```

Add to `Schedule`:

```python
    def period_dates_expr(self) -> pl.Expr:
        """Return a Polars expression yielding a List<Date> per row.

        Each row's list has length ``n_periods + 1`` (boundaries from bop[0]
        to eop[n_periods-1]).

        Phase 1: business-day adjustment is applied per element via a
        post-materialise pass. For the OneTwelfth + NullCalendar default
        path this is effectively a no-op; for real calendars + non-Unadjusted
        conventions, the row-element loop is python-side under
        ``map_elements``. Promotion to a vectorised path is a Phase 2 perf task.
        """
        if self._kind != "from_inception":
            msg = "period_dates_expr() is only valid for from_inception schedules; use period_dates() for from_calendar_grid"
            raise ValueError(msg)
        assert self.inception_column is not None
        offsets = _build_period_offsets(self.frequency, self.n_periods)

        def _expand_row(d: date | None) -> list[date]:
            if d is None:
                return []
            out = [d + off for off in offsets]
            if (
                self.convention is not BusinessDayConvention.UNADJUSTED
                or not isinstance(self.calendar, NullCalendar)
            ):
                out = [self.convention.adjust(x, self.calendar) for x in out]
            return out

        return (
            pl.col(self.inception_column)
            .map_elements(_expand_row, return_dtype=pl.List(pl.Date))
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_period_dates.py -v`
Expected: PASS — 6 tests across both classes.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_period_dates.py
git commit -m "feat(schedule): add period_dates_expr() for from_inception"
```

---

### Task 18: `year_fractions()` (the dt[t] series consumed by `.grow`)

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Create: `bindings/python/tests/schedule/test_schedule_year_fractions.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_schedule_year_fractions.py
"""Schedule.year_fractions() — dt[t] series consumed by .grow."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._calendar import NullCalendar
from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    OneTwelfth,
)
from gaspatchio_core.schedule._schedule import Schedule


class TestYearFractionsCalendarGrid:
    def test_one_twelfth_default_returns_constant_one_twelfth(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        yfs = sched.year_fractions()
        assert len(yfs) == 12
        for yf in yfs:
            assert yf == pytest.approx(1 / 12)

    def test_actual365fixed_varies_by_month(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        yfs = sched.year_fractions()
        # Period 0: 2025-01-31 → 2025-02-28 = 28 days / 365
        # Period 1: 2025-02-28 → 2025-03-31 = 31 days / 365
        # Period 2: 2025-03-31 → 2025-04-30 = 30 days / 365
        assert yfs == pytest.approx([28 / 365, 31 / 365, 30 / 365])

    def test_actual_actual_isda_handles_leap_crossing(self) -> None:
        # Jan 31 2024 (leap) -> Feb 29 (29 days, leap year): 29/366
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 1, 31),
            n_periods=2,
            frequency="1M",
            day_count=ActualActualISDA(),
        )
        yfs = sched.year_fractions()
        # Period 0: 2024-01-31 → 2024-02-29 = 29 days, all in leap → 29/366
        assert yfs[0] == pytest.approx(29 / 366)


class TestYearFractionsFromInception:
    def test_returns_polars_expr_yielding_list(self, sample_policies: pl.DataFrame) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
        )
        df = sample_policies.with_columns(yfs=sched.year_fractions_expr())
        result = df.get_column("yfs").to_list()
        # OneTwelfth default → all entries are 1/12
        for row in result:
            assert len(row) == 3
            for yf in row:
                assert yf == pytest.approx(1 / 12)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_year_fractions.py -v`
Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'year_fractions'`.

- [ ] **Step 3: Implement**

Add to `Schedule`:

```python
    def year_fractions(self) -> list[float]:
        """Return the per-period year-fraction series under this Schedule's day-count.

        Length: ``n_periods``. Only valid for ``from_calendar_grid`` schedules.
        """
        if self._kind != "from_calendar_grid":
            msg = "year_fractions() is only valid for from_calendar_grid schedules; use year_fractions_expr() for from_inception"
            raise ValueError(msg)
        boundaries = self.period_dates()
        return [
            self.day_count.year_fraction(boundaries[t], boundaries[t + 1])
            for t in range(self.n_periods)
        ]

    def year_fractions_expr(self) -> pl.Expr:
        """Return a Polars expression yielding a List<Float64> dt[t] series per row.

        Length per row: ``n_periods``. Only valid for ``from_inception`` schedules.
        """
        if self._kind != "from_inception":
            msg = "year_fractions_expr() is only valid for from_inception schedules; use year_fractions() for from_calendar_grid"
            raise ValueError(msg)
        # Reuse the period_dates_expr work, then map dates -> day-count fractions.
        period_dates = self.period_dates_expr()
        dc = self.day_count

        def _list_to_yfs(boundaries: list[date]) -> list[float]:
            return [dc.year_fraction(boundaries[t], boundaries[t + 1]) for t in range(len(boundaries) - 1)]

        return period_dates.map_elements(_list_to_yfs, return_dtype=pl.List(pl.Float64))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_year_fractions.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_year_fractions.py
git commit -m "feat(schedule): add year_fractions() and year_fractions_expr()"
```

---

### Task 19: `anniversary_mask()` — derived per-period boolean

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Create: `bindings/python/tests/schedule/test_schedule_anniversary_mask.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_schedule_anniversary_mask.py
"""Schedule.anniversary_mask() — true at policy / contract anniversaries."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._schedule import Schedule


class TestAnniversaryMaskFromInception:
    def test_monthly_24_periods_anniversary_at_index_11(self, sample_policies: pl.DataFrame) -> None:
        # Monthly periods, 24 of them. Anniversary every 12 months → mask[11] and mask[23] true.
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=24,
            frequency="1M",
        )
        df = sample_policies.with_columns(mask=sched.anniversary_mask_expr())
        for row_mask in df.get_column("mask").to_list():
            expected = [False] * 24
            expected[11] = True  # end of period 12 = first anniversary
            expected[23] = True  # end of period 24 = second anniversary
            assert row_mask == expected

    def test_quarterly_8_periods_anniversary_at_index_3(self, sample_policies: pl.DataFrame) -> None:
        # Quarterly periods, 8 of them. Anniversary every 4 quarters → mask[3] and mask[7] true.
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=8,
            frequency="3M",
        )
        df = sample_policies.with_columns(mask=sched.anniversary_mask_expr())
        for row_mask in df.get_column("mask").to_list():
            expected = [False] * 8
            expected[3] = True
            expected[7] = True
            assert row_mask == expected


class TestAnniversaryMaskFromCalendarGrid:
    def test_monthly_returns_python_list(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=24,
            frequency="1M",
        )
        mask = sched.anniversary_mask()
        assert len(mask) == 24
        expected = [False] * 24
        expected[11] = True
        expected[23] = True
        assert mask == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_anniversary_mask.py -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Add to `Schedule`:

```python
    def _anniversary_period_count(self) -> int:
        """How many periods constitute one anniversary."""
        if self.frequency == "1Y":
            return 1
        if self.frequency == "6M":
            return 2
        if self.frequency == "3M":
            return 4
        if self.frequency == "1M":
            return 12
        if self.frequency == "1W":
            return 52
        if self.frequency == "1D":
            return 365
        msg = f"unhandled frequency {self.frequency!r}"
        raise AssertionError(msg)

    def anniversary_mask(self) -> list[bool]:
        """True at end-of-period whenever the period closes a contract anniversary.

        ``from_calendar_grid`` only — for ``from_inception`` use :meth:`anniversary_mask_expr`.
        """
        if self._kind != "from_calendar_grid":
            msg = "anniversary_mask() is only valid for from_calendar_grid schedules; use anniversary_mask_expr() for from_inception"
            raise ValueError(msg)
        step = self._anniversary_period_count()
        return [(t + 1) % step == 0 for t in range(self.n_periods)]

    def anniversary_mask_expr(self) -> pl.Expr:
        """Per-row boolean list expression for ``from_inception`` schedules."""
        if self._kind != "from_inception":
            msg = "anniversary_mask_expr() is only valid for from_inception schedules; use anniversary_mask() for from_calendar_grid"
            raise ValueError(msg)
        step = self._anniversary_period_count()
        n = self.n_periods
        # Anniversary mask is purely structural — it depends on n_periods + frequency,
        # not on the inception date — so it's the same per row.
        mask = [(t + 1) % step == 0 for t in range(n)]
        return pl.lit(pl.Series(values=[mask], dtype=pl.List(pl.Boolean))).first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_anniversary_mask.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_anniversary_mask.py
git commit -m "feat(schedule): add anniversary_mask() / anniversary_mask_expr()"
```

---

### Task 20: Canonical form + `source_sha()`

**Files:**
- Create: `bindings/python/gaspatchio_core/schedule/_canonical.py`
- Modify: `bindings/python/gaspatchio_core/schedule/_schedule.py`
- Create: `bindings/python/tests/schedule/test_schedule_canonical.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/schedule/test_schedule_canonical.py
"""Schedule canonical-form + source_sha tests."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._day_count import (
    Actual360,
    OneTwelfth,
)
from gaspatchio_core.schedule._schedule import Schedule


class TestCanonicalForm:
    def test_from_calendar_grid_canonical_shape(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=240,
            frequency="1M",
        )
        cf = sched.canonical_form()
        assert cf == {
            "kind": "from_calendar_grid",
            "n_periods": 240,
            "frequency": "1M",
            "anchor": "month_end",
            "start_date": "2025-01-31",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
        }

    def test_from_inception_canonical_shape(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
        )
        cf = sched.canonical_form()
        assert cf == {
            "kind": "from_inception",
            "n_periods": 240,
            "frequency": "1M",
            "inception_column": "contract_inception",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
        }


class TestSourceSha:
    def test_identical_schedules_have_identical_sha(self) -> None:
        a = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        b = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        assert a.source_sha() == b.source_sha()

    def test_different_day_count_changes_sha(self) -> None:
        a = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M", day_count=Actual360(),
        )
        assert a.source_sha() != b.source_sha()

    def test_different_calendar_changes_sha(self) -> None:
        a = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M", calendar=NullCalendar(),
        )
        b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M", calendar=UnitedStates(),
        )
        assert a.source_sha() != b.source_sha()

    def test_different_n_periods_changes_sha(self) -> None:
        a = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        b = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=24, frequency="1M")
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self) -> None:
        sched = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        sha = sched.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64  # 32-byte hex

    def test_constructor_kind_changes_sha_even_with_same_params(self) -> None:
        # from_inception with no inception_column would still differ from from_calendar_grid
        a = Schedule.from_calendar_grid(start_date=date(2025, 1, 31), n_periods=12, frequency="1M")
        b = Schedule.from_inception(inception_column="contract_inception", n_periods=12, frequency="1M")
        assert a.source_sha() != b.source_sha()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_canonical.py -v`
Expected: FAIL — `AttributeError: 'Schedule' object has no attribute 'canonical_form'`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/schedule/_canonical.py
"""Deterministic canonical-form serialisation for typed-time inputs.

Canonical form is a sorted-keys JSON-encodable dict. ``canonical_bytes(obj)``
produces the bytes used by ``source_sha()`` — the input to ``sha256``.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_bytes(form: dict[str, Any]) -> bytes:
    """Encode a canonical form dict as deterministic UTF-8 bytes.

    - Keys sorted lexically (``json.dumps(..., sort_keys=True)``).
    - Separators standardised (no trailing whitespace).
    - All values must be JSON-serialisable scalars (str, int, float, bool, None)
      or recursive dicts / lists thereof. Date values are stringified to ISO 8601
      *before* reaching this function.
    """
    return json.dumps(form, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

Add to `_schedule.py`:

```python
import hashlib

from gaspatchio_core.schedule._canonical import canonical_bytes


# inside Schedule:

    def canonical_form(self) -> dict[str, str | int]:
        """Return the JSON-encodable canonical form of this Schedule.

        This is the structural recipe identity — two Schedules with the same
        canonical form produce the same per-row dt[t] series for any row data.
        """
        common = {
            "kind": self._kind,
            "n_periods": self.n_periods,
            "frequency": self.frequency,
            "calendar": self.calendar.name(),
            "convention": self.convention.canonical_name(),
            "day_count": self.day_count.name(),
        }
        if self._kind == "from_calendar_grid":
            assert self.start_date is not None
            common["anchor"] = self.anchor
            common["start_date"] = self.start_date.isoformat()
            return common
        # from_inception
        assert self.inception_column is not None
        common["inception_column"] = self.inception_column
        return common

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        Used by :func:`action_key` (Sub-plan D) to fold typed-input identity
        into the run-identity envelope.
        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_canonical.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/_canonical.py bindings/python/gaspatchio_core/schedule/_schedule.py bindings/python/tests/schedule/test_schedule_canonical.py
git commit -m "feat(schedule): add canonical_form() + source_sha() for fingerprint integration"
```

---

### Task 21: Public package exports + top-level re-exports

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/__init__.py`
- Modify: `bindings/python/gaspatchio_core/schedule/__init__.pyi`
- Modify: `bindings/python/gaspatchio_core/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/schedule/test_schedule_constructors.py`:

```python
class TestPublicAPI:
    def test_schedule_calendar_daycount_bdc_importable_from_subpackage(self) -> None:
        from gaspatchio_core.schedule import (
            BusinessDayConvention,
            Calendar,
            DayCount,
            Schedule,
        )
        # Just verify these are the same classes the private modules export
        from gaspatchio_core.schedule._calendar import Calendar as PrivateCalendar
        assert Calendar is PrivateCalendar

    def test_top_level_imports(self) -> None:
        import gaspatchio_core

        assert hasattr(gaspatchio_core, "Schedule")
        assert hasattr(gaspatchio_core, "Calendar")
        assert hasattr(gaspatchio_core, "DayCount")
        assert hasattr(gaspatchio_core, "BusinessDayConvention")

    def test_top_level___all___includes_new_exports(self) -> None:
        import gaspatchio_core

        for name in ("Schedule", "Calendar", "DayCount", "BusinessDayConvention"):
            assert name in gaspatchio_core.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py::TestPublicAPI -v`
Expected: FAIL — `ImportError: cannot import name 'Schedule' from 'gaspatchio_core.schedule'`.

- [ ] **Step 3: Implement schedule subpackage exports**

Replace `gaspatchio_core/schedule/__init__.py`:

```python
"""Typed time primitives — Schedule, Calendar, DayCount, BusinessDayConvention.

Phase 1 typed inputs for the rollforward redesign. The kernel (Sub-plan D)
will consume :class:`Schedule` via the ``schedule=`` kwarg of
``rollforward(...)``; this sub-package can also be used standalone today.
"""

from __future__ import annotations

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import (
    BespokeCalendar,
    Calendar,
    JointCalendar,
    NullCalendar,
    TARGET,
    UnitedKingdom,
    UnitedStates,
    calendar_from_name,
)
from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    DayCount,
    OneTwelfth,
    Thirty360,
    day_count_from_name,
)
from gaspatchio_core.schedule._schedule import Schedule

__all__ = [
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "BespokeCalendar",
    "BusinessDayConvention",
    "Calendar",
    "DayCount",
    "JointCalendar",
    "NullCalendar",
    "OneTwelfth",
    "Schedule",
    "TARGET",
    "Thirty360",
    "UnitedKingdom",
    "UnitedStates",
    "calendar_from_name",
    "day_count_from_name",
]
```

Replace `gaspatchio_core/schedule/__init__.pyi` with the same `from … import …` lines and `__all__`.

- [ ] **Step 4: Wire into top-level `gaspatchio_core/__init__.py`**

In `bindings/python/gaspatchio_core/__init__.py`, find the existing imports block (just after `from .errors import PerformanceWarning`) and add:

```python
from .schedule import (
    BusinessDayConvention,
    Calendar,
    DayCount,
    Schedule,
)
```

Add `"Schedule"`, `"Calendar"`, `"DayCount"`, `"BusinessDayConvention"` to the `__all__` list (alphabetical sort).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/schedule/test_schedule_constructors.py::TestPublicAPI -v`
Expected: PASS — 3 tests.

- [ ] **Step 6: Verify the full test suite still imports**

Run: `cd bindings/python && uv run pytest tests/ -x --co -q 2>&1 | tail -20`
Expected: collection succeeds with no `ImportError`.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/__init__.py bindings/python/gaspatchio_core/schedule/__init__.pyi bindings/python/gaspatchio_core/__init__.py bindings/python/tests/schedule/test_schedule_constructors.py
git commit -m "feat(schedule): wire Schedule + Calendar + DayCount into public API"
```

---

### Task 22: Smoke test — 1200-period GSP-92-shape from_inception

**Files:**
- Create: `bindings/python/tests/schedule/test_smoke_gsp92.py`

- [ ] **Step 1: Write the smoke test**

```python
# bindings/python/tests/schedule/test_smoke_gsp92.py
"""End-to-end smoke test mirroring the GSP-92 VA Illustration schedule shape.

Validates that a 1200-period (100yr) per-policy schedule with the
OneTwelfth + NullCalendar default produces consistent dt[t] = 1/12 and
correctly-aligned anniversary masks across leap-year crossings.

This is the canonical 'hard case' the redesign exists to enable.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import Schedule


class TestGsp92ScheduleShape:
    def test_1200_period_schedule_constructs(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        assert sched.n_periods == 1200

    def test_1200_period_year_fractions_per_row(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        df2 = df.with_columns(yfs=sched.year_fractions_expr())
        for row in df2.get_column("yfs").to_list():
            assert len(row) == 1200
            for yf in row:
                assert yf == pytest.approx(1 / 12)

    def test_anniversary_mask_fires_at_every_12th_period(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        df2 = df.with_columns(mask=sched.anniversary_mask_expr())
        for row in df2.get_column("mask").to_list():
            assert sum(row) == 100  # 100 anniversaries over 1200 monthly periods
            for t in range(1200):
                assert row[t] == ((t + 1) % 12 == 0)

    def test_period_dates_per_policy_count(self) -> None:
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "contract_inception": [date(2024, 2, 29), date(2025, 6, 1)],
            }
        )
        df2 = df.with_columns(dates=sched.period_dates_expr())
        for row in df2.get_column("dates").to_list():
            assert len(row) == 1201  # 1200 periods → 1201 boundaries

    def test_source_sha_stable_across_runs(self) -> None:
        a = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        b = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=1200,
            frequency="1M",
        )
        assert a.source_sha() == b.source_sha()
```

- [ ] **Step 2: Run smoke**

Run: `cd bindings/python && uv run pytest tests/schedule/test_smoke_gsp92.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 3: Run full schedule test suite**

Run: `cd bindings/python && uv run pytest tests/schedule/ -v`
Expected: PASS — full schedule suite (~50–60 tests across 7 test files).

- [ ] **Step 4: Run full repo test suite to confirm nothing else broke**

Run: `cd bindings/python && uv run pytest tests/ -x -q 2>&1 | tail -10`
Expected: only previously-passing tests still pass; no schedule-related regressions elsewhere.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/tests/schedule/test_smoke_gsp92.py
git commit -m "test(schedule): GSP-92-shape 1200-period smoke test"
```

---

### Task 23: Leap-year regression — explicit Feb-29 inception coverage

**Files:**
- Create: `bindings/python/tests/schedule/test_leap_year.py`

- [ ] **Step 1: Write the test**

```python
# bindings/python/tests/schedule/test_leap_year.py
"""Leap-year regression tests.

Phase 1 commitment: Date(2020, 2, 29) + 1 year = Date(2021, 2, 28).
Tested explicitly because this is the single most common date-handling bug
in actuarial schedules.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._day_count import (
    Actual365Fixed,
    ActualActualISDA,
    OneTwelfth,
)
from gaspatchio_core.schedule._schedule import Schedule


class TestLeapDayInception:
    def test_feb_29_plus_one_year_is_feb_28(self) -> None:
        # Per Phase 1 commitment + Schedule design pass §"leap-year handling"
        sched = Schedule.from_inception(
            inception_column="inception",
            n_periods=12,
            frequency="1M",
        )
        df = pl.DataFrame({"inception": [date(2020, 2, 29)]})
        df2 = df.with_columns(dates=sched.period_dates_expr())
        dates = df2.get_column("dates").to_list()[0]
        # Period 0 starts Feb 29 2020; period 11 (last) ends Feb 28 2021 (one year later)
        assert dates[0] == date(2020, 2, 29)
        assert dates[12] == date(2021, 2, 28)


class TestLeapCrossingYearFractions:
    def test_actual_actual_isda_splits_at_year_boundary(self) -> None:
        # 12-period monthly schedule starting 2024-06-30 (in leap year)
        # Some periods entirely in 2024 (366), some entirely in 2025 (365),
        # one straddles the boundary
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 6, 30),
            n_periods=12,
            frequency="1M",
            day_count=ActualActualISDA(),
        )
        yfs = sched.year_fractions()
        assert sum(yfs) == pytest.approx(1.0, abs=1e-6)  # exactly one year

    def test_actual_365_fixed_does_not_round_trip_to_one(self) -> None:
        # 12-period monthly schedule that crosses a leap-year boundary at Act/365F
        # totals 366/365 ≠ 1.0 — by design
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 1, 31),
            n_periods=12,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        yfs = sched.year_fractions()
        # 2024-01-31 to 2025-01-31 is 366 days (because of Feb 29) / 365 = 366/365
        assert sum(yfs) == pytest.approx(366 / 365, abs=1e-9)
```

- [ ] **Step 2: Run test**

Run: `cd bindings/python && uv run pytest tests/schedule/test_leap_year.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/schedule/test_leap_year.py
git commit -m "test(schedule): leap-year regression — Feb-29 + Act/Act ISDA + Act/365F"
```

---

### Task 24: pyi stubs for IDE support

**Files:**
- Modify: `bindings/python/gaspatchio_core/schedule/__init__.pyi`
- Verify: `bindings/python/stubtest-allowlist.txt` (no new entries needed if exports match)

- [ ] **Step 1: Write the stub**

Replace `bindings/python/gaspatchio_core/schedule/__init__.pyi` with (no module docstring — ruff PYI021):

```python
from __future__ import annotations

from datetime import date
from typing import Literal

import polars as pl

class DayCount:
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

class OneTwelfth(DayCount): ...
class Actual365Fixed(DayCount): ...
class Actual360(DayCount): ...
class Thirty360(DayCount): ...
class ActualActualISDA(DayCount): ...

def day_count_from_name(name: str) -> DayCount: ...

class BusinessDayConvention:
    UNADJUSTED: BusinessDayConvention
    FOLLOWING: BusinessDayConvention
    MODIFIED_FOLLOWING: BusinessDayConvention
    PRECEDING: BusinessDayConvention
    def canonical_name(self) -> str: ...
    def adjust(self, d: date, calendar: Calendar | None) -> date: ...

class Calendar:
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class NullCalendar(Calendar): ...
class TARGET(Calendar): ...
class UnitedKingdom(Calendar): ...
class UnitedStates(Calendar): ...

class JointCalendar(Calendar):
    left: Calendar
    right: Calendar
    def __init__(self, left: Calendar, right: Calendar) -> None: ...

class BespokeCalendar(Calendar):
    holidays: frozenset[date]
    label: str | None
    def __init__(self, holidays: frozenset[date], label: str | None = ...) -> None: ...

def calendar_from_name(name: str) -> Calendar: ...

class Schedule:
    n_periods: int
    frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"]
    calendar: Calendar
    convention: BusinessDayConvention
    day_count: DayCount
    anchor: Literal["month_end", "exact_date", "month_start", "year_end"]
    start_date: date | None
    inception_column: str | None
    @classmethod
    def from_calendar_grid(
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        anchor: Literal["month_end", "exact_date", "month_start", "year_end"] = ...,
        calendar: Calendar | None = ...,
        convention: BusinessDayConvention | None = ...,
        day_count: DayCount | None = ...,
    ) -> Schedule: ...
    @classmethod
    def from_inception(
        cls,
        *,
        inception_column: str,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        calendar: Calendar | None = ...,
        convention: BusinessDayConvention | None = ...,
        day_count: DayCount | None = ...,
    ) -> Schedule: ...
    def period_dates(self) -> list[date]: ...
    def period_dates_expr(self) -> pl.Expr: ...
    def year_fractions(self) -> list[float]: ...
    def year_fractions_expr(self) -> pl.Expr: ...
    def anniversary_mask(self) -> list[bool]: ...
    def anniversary_mask_expr(self) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, str | int]: ...
    def source_sha(self) -> str: ...

__all__ = [
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "BespokeCalendar",
    "BusinessDayConvention",
    "Calendar",
    "DayCount",
    "JointCalendar",
    "NullCalendar",
    "OneTwelfth",
    "Schedule",
    "TARGET",
    "Thirty360",
    "UnitedKingdom",
    "UnitedStates",
    "calendar_from_name",
    "day_count_from_name",
]
```

- [ ] **Step 2: Verify stubtest is clean**

Run: `cd bindings/python && uv run python -m mypy.stubtest gaspatchio_core.schedule --allowlist stubtest-allowlist.txt 2>&1 | tail -20`
Expected: zero errors. If any errors surface (e.g., dataclass fields missing in stub), fix the stub inline.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/schedule/__init__.pyi
git commit -m "feat(schedule): full pyi stubs for typed-time public surface"
```

---

### Task 25: Lint + final-pass verification

**Files:**
- (verification-only)

- [ ] **Step 1: Lint clean**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/schedule tests/schedule`
Expected: no errors.

If errors surface, address them inline (do NOT add `# noqa` unless the rule is in the project-level ignore list — see the existing `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` section).

- [ ] **Step 2: Format check**

Run: `cd bindings/python && uv run ruff format --check gaspatchio_core/schedule tests/schedule`
Expected: no diffs.

If it suggests changes, run `uv run ruff format gaspatchio_core/schedule tests/schedule` and commit the format fixup.

- [ ] **Step 3: Type check**

Run: `cd bindings/python && uv run mypy gaspatchio_core/schedule 2>&1 | tail -20`
Expected: no errors.

- [ ] **Step 4: Final test run**

Run: `cd bindings/python && uv run pytest tests/schedule -v`
Expected: all schedule tests pass — should be ~60+ across 7 test files.

- [ ] **Step 5: Verify rest of repo still passes**

Run: `cd bindings/python && uv run pytest tests/ -q 2>&1 | tail -5`
Expected: prior pass-count unchanged or higher (only new schedule tests added).

- [ ] **Step 6: Commit any lint / format / type fixups**

If any cleanup landed:

```bash
git add bindings/python/gaspatchio_core/schedule
git commit -m "chore(schedule): lint + format + type-check fixups"
```

If nothing to commit, this step is a no-op.

---

### Task 26: README + spec status update

**Files:**
- Modify: `ref/36-rollforward-redesign/README.md`
- (Optional) Modify: `ref/36-rollforward-redesign/specs/2026-05-03-rollforward-redesign-v2-design.md` — frontmatter status line (only if tracking implementation status in spec)

- [ ] **Step 1: Update sub-plan README**

Add to `ref/36-rollforward-redesign/README.md` (or create if missing):

```markdown
## Implementation status

- **Phase 1a Sub-plan A — Typed Time** (Schedule + Calendar + DayCount): ✅ shipped (this branch)
- **Phase 1a Sub-plan B — Curve**: not started
- **Phase 1a Sub-plan C — MortalityTable**: not started
- **Phase 1a Sub-plan D — State-machine kernel**: not started

Plan: [`plans/2026-05-04-phase-1a-schedule.md`](plans/2026-05-04-phase-1a-schedule.md)
```

- [ ] **Step 2: Commit**

```bash
git add ref/36-rollforward-redesign/README.md
git commit -m "docs(rollforward-redesign): mark Sub-plan A (typed time) shipped"
```

---

## Self-review

The plan above has been re-read against the spec and the schedule research. Findings:

**Spec coverage check:**
- §4.16 5 day-counts: tasks 2–6 ✓
- §4.16 4 calendars + escape hatches: tasks 9–11 ✓
- §4.16 4 BD conventions: task 8 ✓
- §4.16 OneTwelfth + NullCalendar defaults: task 14 ✓ (`from_calendar_grid`), task 15 ✓ (`from_inception`)
- §4.16 month-end anchoring on `from_calendar_grid`: task 14 ✓
- §4.16 context-dependent BD-convention default: task 14 ✓ (test + impl); regression with real calendar: task 15 + 12
- §4.16 `from_inception` per-policy + `from_calendar_grid` shared: tasks 14, 15
- §4.16 `anniversary_mask`, `year_fractions`, `period_dates`: tasks 16–19
- §4.16 leap-year handling (Feb 29 + 1y → Feb 28): task 23 ✓
- §4.16 fingerprint canonical-form fields: task 20 ✓
- §13.1a `source_sha()` method on Schedule: task 20 ✓
- §13.1a public-API exposure: task 21 ✓
- Schedule research §"Phase 1 design commitments" coverage: ✓ all six (5 day-counts, 4 calendars, 4 BD conventions, two constructors, OneTwelfth default, leap-year)

**Placeholder scan:**
- No "TBD", "implement later", "fill in details" anywhere.
- No "add appropriate error handling" or similar.
- All step-3 implementations show actual code, not "implement Schedule.from_calendar_grid".
- All test code is concrete, not "write tests for the above".

**Type consistency:**
- `DayCount`, `Calendar`, `BusinessDayConvention`, `Schedule` referenced consistently across tasks.
- Method names match between tests and impl (`year_fraction` not `year_fractions` for the per-pair-of-dates method; `year_fractions` for the per-period-list method; `year_fractions_expr` for the per-row Polars Expr method).
- `_kind`, `start_date`, `inception_column`, `anchor` field names match between dataclass def, tests, and canonical-form output.

**Scope check:**
- Sub-plan A is one cohesive subsystem. No further decomposition.
- IR / kernel / fingerprint integration explicitly deferred to Sub-plan D (called out at top + in §"Out of scope").

**Risks I've flagged inline:**
- Task 17's `map_elements` per-row date arithmetic is python-side and not vectorised. For Phase 1's monthly + 1200-period scale this is fine (~1.2k Python calls per row, OK at policy-batch sizes). If this surfaces as a benchmark hot-spot in Sub-plan D, promote to a vectorised Polars `dt` path or to Rust. Documented in the impl docstring.
- Task 19's `anniversary_mask_expr` returns a `pl.lit(...)` constant per-row list. This is correct because anniversary is purely structural (depends on n_periods + frequency, not on inception). No per-row variation.
- The `python-holidays` dep is small (~150 KB) and well-maintained. If the team prefers zero-new-deps, hand-rolled holiday catalogs for TARGET / UK / US would work, but that's ~200 lines of date-math (Easter computation in particular) — not worth shipping in this sub-plan.

---

## Execution handoff

Plan complete and saved to `ref/36-rollforward-redesign/plans/2026-05-04-phase-1a-schedule.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Each task is small enough (4–7 steps, ~10–30 lines of new production code) that a focused subagent can land it cleanly.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Practical if you want to walk the plan with me.

**Which approach?**
