# Phase 1a Sub-plan B — Typed Curve Primitive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a typed `Curve` term-structure primitive — `from_zero_rates` and `from_par_rates` constructors, accessors (`spot_rate`, `discount_factor`, `forward_rate`), parallel and key-rate shifts (`shift_parallel`, `key_rate_shift`), `source_sha()` for fingerprint identity, and a `DayCount` association so two curves differing only in day-count produce different fingerprints. Accessors accept `float`, `list[float]`, `np.ndarray`, `pl.Series`, and `pl.Expr` inputs and return matching shapes — so Curve composes naturally with Schedule's `year_fractions()` (Sub-plan A) and with the rollforward kernel's transition-body Expr surface (Sub-plan D). Independently shippable: the typed Curve coexists with the existing column-of-rates surface; nothing in the kernel or in user models needs to migrate to use it.

**Architecture:** Frozen-dataclass typed input under `gaspatchio_core/curves/`. Static curves only in Phase 1 (knots are Python lists at construction time) — per-row Curve columns (where each policy carries its own rate list) are deferred to a follow-up plan. Linear interpolation on rates is the Phase 1 default; log-linear-on-discount-factors, monotone cubic, etc. are deferred. Accessors dispatch on input type so a Python-list `t` returns a Python list, a `pl.Expr` returns a `pl.Expr`. Canonical form is a deterministic JSON dict reused via `gaspatchio_core.schedule._canonical.canonical_bytes` (the helper is generic; no schedule-specific behaviour). `source_sha = sha256(canonical_form_bytes)` matches Plan A's pattern by construction.

**Tech Stack:** Python 3.10+; Polars 1.38.1 (pinned); NumPy (already in deps); `hypothesis` (dev dep) for property-based tests; reuse `gaspatchio_core.schedule.DayCount` directly — no new DayCount work in this sub-plan. No new third-party deps.

---

## Scope check

This sub-plan is one independently-testable subsystem (typed term-structure primitive). No further decomposition needed.

**Out of scope (deferred):**
- Per-row Curve columns (`Curve.from_zero_rates(rates=af.col)` where each row has its own knot list) — deferred to a follow-up plan; the spec examples in §4.4/§4.12/§4.13 that use `rates=af.col` work today via the existing column-of-rates surface and gain typed-Curve treatment in Phase 1.5. Spec wording will note this.
- Regulatory loaders (EIOPA RFR with Smith-Wilson reconstruction + VA/MA hooks, NAIC tables, Fed term-structure publications) — deferred per spec §13.1a / §13.4
- Log-linear-on-discount-factors interpolation — Phase 2 quality lift
- Monotone cubic, Nelson-Siegel, Svensson — Phase 3 SOTA
- Curve-curve operations beyond `shift_parallel` and `key_rate_shift` (e.g., curve subtraction, OAS spread overlay) — Phase 2
- IR / kernel / fingerprint integration → Sub-plan D

---

## File structure

**New (Python, all under `bindings/python/gaspatchio_core/curves/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Public re-exports: `Curve` |
| `__init__.pyi` | Type stubs |
| `_curve.py` | `Curve` frozen-dataclass + `from_zero_rates` / `from_par_rates` classmethods + accessors (`spot_rate`, `discount_factor`, `forward_rate`) |
| `_interpolation.py` | Linear interpolation over knot grid; flat extrapolation outside |
| `_shift.py` | `shift_parallel(bps)` and `key_rate_shift(tenor, bps)` (own file because shifts produce new Curve instances and have property-test discipline) |
| `_bootstrap.py` | Par-to-zero bootstrap math for `from_par_rates` |

**New (tests, all under `bindings/python/tests/curves/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Empty marker |
| `conftest.py` | Shared fixtures: tenor grids, reference EIOPA-style rate sets |
| `test_curve_construction.py` | `from_zero_rates` validation, equality, hashing |
| `test_curve_accessors.py` | `spot_rate`, `discount_factor`, `forward_rate` for all input shapes |
| `test_curve_interpolation.py` | Linear interp; boundary extrapolation; knot-aligned exact recovery |
| `test_curve_shifts.py` | `shift_parallel` + `key_rate_shift`; commutativity; idempotency |
| `test_curve_par_rates.py` | `from_par_rates` bootstrap recovers reference zero curve |
| `test_curve_canonical.py` | Canonical-form determinism; SHA collisions = identical curves |
| `test_curve_polars_integration.py` | Accessors emit valid `pl.Expr`s consumable by `.grow()` and friends |

**Modified:**

- `bindings/python/gaspatchio_core/__init__.py` — re-export `Curve`
- `bindings/python/gaspatchio_core/__init__.py` `__all__` list — add `"Curve"`

**Untouched (so we don't break Sub-plan A's surface or Sub-plan D's planning):**
- `gaspatchio_core/schedule/` — used as a read-only import for `DayCount`
- `gaspatchio_core/rollforward/` — old kernel stays running until Sub-plan D
- The existing column-of-rates surface — Curve is additive, not a replacement

---

## Tasks

### Task 1: Package scaffolding

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/__init__.py`
- Create: `bindings/python/gaspatchio_core/curves/__init__.pyi`
- Create: `bindings/python/tests/curves/__init__.py`

- [ ] **Step 1: Create the empty package files**

```python
# bindings/python/gaspatchio_core/curves/__init__.py
"""Typed term-structure primitive — Curve."""

from __future__ import annotations

__all__: list[str] = []
```

```python
# bindings/python/gaspatchio_core/curves/__init__.pyi
"""Type stubs for gaspatchio_core.curves."""
__all__: list[str] = []
```

```python
# bindings/python/tests/curves/__init__.py
```

- [ ] **Step 2: Verify package imports cleanly**

Run: `cd bindings/python && uv run python -c "import gaspatchio_core.curves"`
Expected: no error, no output.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/ bindings/python/tests/curves/__init__.py
git commit -m "feat(curves): scaffold typed Curve package"
```

---

### Task 2: `Curve` frozen-dataclass + `from_zero_rates` constructor

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_curve.py`
- Create: `bindings/python/tests/curves/conftest.py`
- Create: `bindings/python/tests/curves/test_curve_construction.py`

- [ ] **Step 1: Write the conftest**

```python
# bindings/python/tests/curves/conftest.py
"""Shared fixtures for Curve tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def eiopa_eur_2026q2_tenors() -> list[float]:
    """Representative EIOPA-style EUR tenor grid (years)."""
    return [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0]


@pytest.fixture
def eiopa_eur_2026q2_zero_rates() -> list[float]:
    """Representative EUR zero-rate curve (illustrative, not actual EIOPA data)."""
    return [0.025, 0.028, 0.030, 0.031, 0.032, 0.033, 0.035, 0.036, 0.037, 0.038]


@pytest.fixture
def flat_3pct_tenors() -> list[float]:
    """Knot grid for a flat 3% curve."""
    return [1.0, 5.0, 10.0, 30.0]


@pytest.fixture
def flat_3pct_rates() -> list[float]:
    return [0.03, 0.03, 0.03, 0.03]
```

- [ ] **Step 2: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_construction.py
"""Curve construction + validation tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._curve import Curve
from gaspatchio_core.schedule._day_count import (
    Actual365Fixed,
    ActualActualISDA,
    OneTwelfth,
)


class TestFromZeroRates:
    def test_basic_construction(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=ActualActualISDA(),
        )
        assert c.tenors == tuple(flat_3pct_tenors)
        assert c.rates == tuple(flat_3pct_rates)
        assert c.day_count == ActualActualISDA()
        assert c.interpolation == "linear"

    def test_default_day_count_is_actual_actual_isda(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.day_count == ActualActualISDA()

    def test_default_interpolation_is_linear(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.interpolation == "linear"

    def test_tenors_and_rates_must_match_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            Curve.from_zero_rates(tenors=[1.0, 2.0], rates=[0.03])

    def test_tenors_must_be_strictly_increasing(self) -> None:
        with pytest.raises(ValueError, match="strictly increasing"):
            Curve.from_zero_rates(tenors=[1.0, 1.0, 2.0], rates=[0.03, 0.03, 0.04])
        with pytest.raises(ValueError, match="strictly increasing"):
            Curve.from_zero_rates(tenors=[1.0, 0.5, 2.0], rates=[0.03, 0.03, 0.04])

    def test_at_least_two_knots_required(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            Curve.from_zero_rates(tenors=[1.0], rates=[0.03])

    def test_unknown_interpolation_raises(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        with pytest.raises(ValueError, match="interpolation"):
            Curve.from_zero_rates(
                tenors=flat_3pct_tenors,
                rates=flat_3pct_rates,
                interpolation="cubic",  # type: ignore[arg-type]
            )

    def test_equal_curves_compare_equal_and_hash_equal(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        a = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        b = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert a == b
        assert hash(a) == hash(b)

    def test_different_day_count_makes_curves_unequal(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        a = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=Actual365Fixed(),
        )
        b = Curve.from_zero_rates(
            tenors=flat_3pct_tenors,
            rates=flat_3pct_rates,
            day_count=OneTwelfth(),
        )
        assert a != b
        assert hash(a) != hash(b)

    def test_is_frozen(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        with pytest.raises(Exception):
            c.something = 42  # type: ignore[attr-defined]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_construction.py::TestFromZeroRates -v`
Expected: FAIL — `ImportError: cannot import name 'Curve'`.

- [ ] **Step 4: Implement**

```python
# bindings/python/gaspatchio_core/curves/_curve.py
"""Typed Curve term-structure primitive.

A Curve carries a discrete grid of (tenor, zero_rate) knots plus a day-count
convention. Accessors (:meth:`spot_rate`, :meth:`discount_factor`,
:meth:`forward_rate`) interpolate over the grid and accept ``float``,
``list[float]``, ``np.ndarray``, ``pl.Series``, or ``pl.Expr`` inputs,
returning matching shapes.

Phase 1 commitments:
  - Static curves only (literal Python list knots at construction).
    Per-row column curves deferred.
  - Linear interpolation on rates; flat extrapolation outside the knot range.
  - Default day-count: ``ActualActualISDA``.
  - Constructors: ``from_zero_rates``, ``from_par_rates`` (bootstrap).
  - Stress: ``shift_parallel(bps)``, ``key_rate_shift(tenor, bps)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gaspatchio_core.schedule._day_count import ActualActualISDA, DayCount

InterpolationMethod = Literal["linear"]


@dataclass(frozen=True)
class Curve:
    """Typed term-structure curve.

    Construct via :meth:`from_zero_rates` or :meth:`from_par_rates`. Direct
    construction is intentionally awkward — use the classmethods.
    """

    tenors: tuple[float, ...]
    rates: tuple[float, ...]
    day_count: DayCount
    interpolation: InterpolationMethod = field(default="linear")

    @classmethod
    def from_zero_rates(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        day_count: DayCount | None = None,
        interpolation: InterpolationMethod = "linear",
    ) -> Curve:
        """Build a Curve from zero (spot) rates indexed by tenor in years.

        ``tenors`` and ``rates`` must have the same length, with ``tenors``
        strictly increasing and at least two knots present.
        """
        if len(tenors) != len(rates):
            msg = f"tenors and rates must have the same length; got {len(tenors)} and {len(rates)}"
            raise ValueError(msg)
        if len(tenors) < 2:
            msg = f"at least 2 knots required; got {len(tenors)}"
            raise ValueError(msg)
        for i in range(1, len(tenors)):
            if tenors[i] <= tenors[i - 1]:
                msg = f"tenors must be strictly increasing; got {tenors}"
                raise ValueError(msg)
        if interpolation != "linear":
            msg = f"unsupported interpolation {interpolation!r}; Phase 1 supports 'linear' only"
            raise ValueError(msg)
        return cls(
            tenors=tuple(tenors),
            rates=tuple(rates),
            day_count=day_count or ActualActualISDA(),
            interpolation=interpolation,
        )


__all__ = ["Curve"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_construction.py::TestFromZeroRates -v`
Expected: PASS — 10 tests.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/conftest.py bindings/python/tests/curves/test_curve_construction.py
git commit -m "feat(curves): add Curve.from_zero_rates with validation"
```

---

### Task 3: Linear interpolation helper

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_interpolation.py`
- Create: `bindings/python/tests/curves/test_curve_interpolation.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_interpolation.py
"""Linear interpolation + flat extrapolation tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._interpolation import linear_interpolate


class TestLinearInterpolate:
    def test_exact_knot_recovery(self) -> None:
        knots_x = [1.0, 2.0, 5.0, 10.0]
        knots_y = [0.03, 0.04, 0.05, 0.06]
        # At each knot, the interpolated value equals the knot value
        for x, expected in zip(knots_x, knots_y):
            assert linear_interpolate(x, knots_x, knots_y) == pytest.approx(expected)

    def test_midpoint(self) -> None:
        knots_x = [1.0, 2.0]
        knots_y = [0.03, 0.05]
        # Midpoint of [1, 2] -> midpoint of [0.03, 0.05] = 0.04
        assert linear_interpolate(1.5, knots_x, knots_y) == pytest.approx(0.04)

    def test_quarter_point(self) -> None:
        knots_x = [0.0, 1.0]
        knots_y = [0.0, 1.0]
        assert linear_interpolate(0.25, knots_x, knots_y) == pytest.approx(0.25)

    def test_extrapolate_below_first_knot_returns_first_value(self) -> None:
        # Flat extrapolation below the first knot
        knots_x = [1.0, 5.0]
        knots_y = [0.03, 0.05]
        assert linear_interpolate(0.0, knots_x, knots_y) == pytest.approx(0.03)
        assert linear_interpolate(0.5, knots_x, knots_y) == pytest.approx(0.03)

    def test_extrapolate_above_last_knot_returns_last_value(self) -> None:
        # Flat extrapolation above the last knot
        knots_x = [1.0, 5.0]
        knots_y = [0.03, 0.05]
        assert linear_interpolate(10.0, knots_x, knots_y) == pytest.approx(0.05)
        assert linear_interpolate(50.0, knots_x, knots_y) == pytest.approx(0.05)

    def test_handles_non_uniform_grid(self) -> None:
        knots_x = [1.0, 2.0, 5.0, 10.0]
        knots_y = [0.03, 0.04, 0.05, 0.06]
        # Halfway between (5, 0.05) and (10, 0.06) is (7.5, 0.055)
        assert linear_interpolate(7.5, knots_x, knots_y) == pytest.approx(0.055)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_interpolation.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/curves/_interpolation.py
"""Curve interpolation primitives.

Phase 1 ships ``linear_interpolate`` only — linear-on-rates interpolation
with flat extrapolation outside the knot grid. Log-linear-on-discount-factor
and monotone cubic are deferred to later phases.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Sequence


def linear_interpolate(
    x: float,
    knots_x: Sequence[float],
    knots_y: Sequence[float],
) -> float:
    """Linear interpolation over a sorted knot grid with flat extrapolation.

    ``knots_x`` must be strictly increasing and the same length as ``knots_y``;
    these invariants are guaranteed by :class:`Curve` at construction time and
    are not re-checked here on the hot path.
    """
    if x <= knots_x[0]:
        return knots_y[0]
    if x >= knots_x[-1]:
        return knots_y[-1]
    # Find the interval [knots_x[i-1], knots_x[i]) containing x
    i = bisect_right(knots_x, x)
    x0, x1 = knots_x[i - 1], knots_x[i]
    y0, y1 = knots_y[i - 1], knots_y[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


__all__ = ["linear_interpolate"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_interpolation.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_interpolation.py bindings/python/tests/curves/test_curve_interpolation.py
git commit -m "feat(curves): add linear_interpolate helper"
```

---

### Task 4: `Curve.spot_rate(t)` — float and list inputs

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Create: `bindings/python/tests/curves/test_curve_accessors.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_accessors.py
"""Curve accessor tests — spot_rate, discount_factor, forward_rate."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio_core.curves._curve import Curve


class TestSpotRateScalar:
    def test_returns_knot_value_at_knot(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.spot_rate(1.0) == pytest.approx(0.03)
        assert c.spot_rate(5.0) == pytest.approx(0.03)
        assert c.spot_rate(30.0) == pytest.approx(0.03)

    def test_interpolates_between_knots(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # Halfway between (2.0, 0.030) and (3.0, 0.031) -> 0.0305
        assert c.spot_rate(2.5) == pytest.approx(0.0305)

    def test_extrapolates_below_first_knot(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # First tenor is 0.5; below that flat-extrapolates to first rate (0.025)
        assert c.spot_rate(0.0) == pytest.approx(0.025)
        assert c.spot_rate(0.1) == pytest.approx(0.025)

    def test_extrapolates_above_last_knot(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # Last tenor is 30; above that flat-extrapolates to last rate (0.038)
        assert c.spot_rate(50.0) == pytest.approx(0.038)


class TestSpotRateList:
    def test_returns_python_list_for_list_input(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        result = c.spot_rate([1.0, 2.5, 7.0, 30.0])
        assert isinstance(result, list)
        assert all(r == pytest.approx(0.03) for r in result)

    def test_preserves_input_length(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        result = c.spot_rate([0.5, 1.0, 2.0, 5.0])
        assert len(result) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestSpotRateScalar tests/curves/test_curve_accessors.py::TestSpotRateList -v`
Expected: FAIL — `AttributeError: 'Curve' object has no attribute 'spot_rate'`.

- [ ] **Step 3: Implement**

Append to `_curve.py`:

```python
from typing import Sequence, Union, overload

import numpy as np
import polars as pl

from gaspatchio_core.curves._interpolation import linear_interpolate

# Phase 1 input/output type union for accessors. The implementation dispatches
# on the concrete type at call time and returns a matching shape.
TimeInput = Union[float, int, list[float], np.ndarray, pl.Series, pl.Expr]


# inside class Curve:

    def spot_rate(self, t: TimeInput) -> float | list[float] | np.ndarray | pl.Series | pl.Expr:
        """Spot zero rate at year fraction(s) ``t``.

        Returns a scalar for a scalar input, a Python list for a list input,
        a NumPy array for an ndarray input, a Polars Series for a Series input,
        and a Polars Expr for an Expr input.
        """
        if isinstance(t, (int, float)):
            return linear_interpolate(float(t), self.tenors, self.rates)
        if isinstance(t, list):
            return [linear_interpolate(float(x), self.tenors, self.rates) for x in t]
        if isinstance(t, np.ndarray):
            return np.array([linear_interpolate(float(x), self.tenors, self.rates) for x in t])
        if isinstance(t, pl.Series):
            return pl.Series(
                name=t.name,
                values=[linear_interpolate(float(x), self.tenors, self.rates) for x in t.to_list()],
                dtype=pl.Float64,
            )
        if isinstance(t, pl.Expr):
            tenors = self.tenors
            rates = self.rates

            def _interp(x: float) -> float:
                return linear_interpolate(x, tenors, rates)

            return t.map_elements(_interp, return_dtype=pl.Float64)
        msg = f"unsupported t type: {type(t).__name__}"
        raise TypeError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestSpotRateScalar tests/curves/test_curve_accessors.py::TestSpotRateList -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_accessors.py
git commit -m "feat(curves): add Curve.spot_rate (scalar + list inputs)"
```

---

### Task 5: `spot_rate(t)` — Polars Series and Expr inputs (regression)

**Files:**
- Modify: `bindings/python/tests/curves/test_curve_accessors.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestSpotRatePolars:
    def test_series_input_returns_series(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        s = pl.Series(name="t", values=[1.0, 2.0, 5.0, 30.0])
        result = c.spot_rate(s)
        assert isinstance(result, pl.Series)
        assert result.name == "t"
        assert result.to_list() == pytest.approx([0.03, 0.03, 0.03, 0.03])

    def test_expr_input_returns_expr(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        df = pl.DataFrame({"t": [0.5, 1.0, 2.0, 5.0]})
        result = df.with_columns(rate=c.spot_rate(pl.col("t")))
        assert result.get_column("rate").to_list() == pytest.approx(
            [0.025, 0.028, 0.030, 0.032]
        )

    def test_numpy_input_returns_numpy(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        arr = np.array([1.0, 2.0, 5.0])
        result = c.spot_rate(arr)
        assert isinstance(result, np.ndarray)
        assert result.tolist() == pytest.approx([0.03, 0.03, 0.03])
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestSpotRatePolars -v`
Expected: PASS — 3 tests. (The implementation from Task 4 already handles these.)

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/curves/test_curve_accessors.py
git commit -m "test(curves): regression — spot_rate handles Series/Expr/ndarray"
```

---

### Task 6: `discount_factor(t)`

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Modify: `bindings/python/tests/curves/test_curve_accessors.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestDiscountFactor:
    def test_at_zero_tenor_is_one(
        self,
        flat_3pct_tenors: list[float],
        flat_3pct_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(tenors=flat_3pct_tenors, rates=flat_3pct_rates)
        assert c.discount_factor(0.0) == pytest.approx(1.0)

    def test_at_one_year_is_one_over_one_plus_rate(self) -> None:
        # Annually compounded: DF(1) = 1 / (1 + r)
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.03])
        assert c.discount_factor(1.0) == pytest.approx(1 / 1.03)

    def test_at_t_years_is_one_over_one_plus_rate_to_t(self) -> None:
        # DF(t) = (1 + r(t))^-t  (annually compounded)
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        # At t=2 the rate is interp(2) between (1, 0.03) and (5, 0.04) = 0.0325
        rate_at_2 = c.spot_rate(2.0)
        assert c.discount_factor(2.0) == pytest.approx((1 + rate_at_2) ** -2)

    def test_list_input(self) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.03])
        result = c.discount_factor([0.0, 1.0, 2.0])
        assert isinstance(result, list)
        assert result == pytest.approx([1.0, 1 / 1.03, 1 / (1.03 ** 2)])

    def test_expr_input(self) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.03])
        df = pl.DataFrame({"t": [0.0, 1.0, 2.0]})
        result = df.with_columns(df_=c.discount_factor(pl.col("t")))
        assert result.get_column("df_").to_list() == pytest.approx(
            [1.0, 1 / 1.03, 1 / (1.03 ** 2)]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestDiscountFactor -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Append to `Curve` in `_curve.py`:

```python
    def discount_factor(self, t: TimeInput) -> float | list[float] | np.ndarray | pl.Series | pl.Expr:
        """Annually compounded discount factor: ``DF(t) = (1 + r(t))^(-t)``.

        Phase 1 commits to annually compounded discounting; continuously
        compounded (``exp(-r*t)``) is deferred. Two curves with identical
        rate grids but different compounding frequencies would produce
        meaningfully different DFs — the choice is documented as Phase 1
        canonical, not user-configurable.
        """
        if isinstance(t, (int, float)):
            r = self.spot_rate(float(t))
            assert isinstance(r, float)
            return (1.0 + r) ** (-float(t))

        if isinstance(t, list):
            return [(1.0 + self._scalar_spot(x)) ** (-x) for x in t]

        if isinstance(t, np.ndarray):
            spots = np.array([self._scalar_spot(float(x)) for x in t])
            return (1.0 + spots) ** (-t.astype(float))

        if isinstance(t, pl.Series):
            return pl.Series(
                name=t.name,
                values=[(1.0 + self._scalar_spot(float(x))) ** (-float(x)) for x in t.to_list()],
                dtype=pl.Float64,
            )

        if isinstance(t, pl.Expr):
            tenors = self.tenors
            rates = self.rates

            def _df(x: float) -> float:
                r = linear_interpolate(x, tenors, rates)
                return (1.0 + r) ** (-x)

            return t.map_elements(_df, return_dtype=pl.Float64)

        msg = f"unsupported t type: {type(t).__name__}"
        raise TypeError(msg)

    def _scalar_spot(self, t: float) -> float:
        """Internal helper — spot rate as a scalar float, no dispatch."""
        return linear_interpolate(t, self.tenors, self.rates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestDiscountFactor -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_accessors.py
git commit -m "feat(curves): add Curve.discount_factor (annually compounded)"
```

---

### Task 7: `forward_rate(t1, t2)`

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Modify: `bindings/python/tests/curves/test_curve_accessors.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestForwardRate:
    def test_forward_equals_spot_when_t1_is_zero(self) -> None:
        # F(0, t) = r(t) when DF(0) = 1
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        f = c.forward_rate(t1=0.0, t2=1.0)
        assert f == pytest.approx(0.03)

    def test_forward_via_discount_factor_ratio(self) -> None:
        # F(t1, t2) such that DF(t1) / DF(t2) = (1 + F)^(t2 - t1)
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        df_1 = c.discount_factor(1.0)
        df_3 = c.discount_factor(3.0)
        f = c.forward_rate(t1=1.0, t2=3.0)
        assert (df_1 / df_3) == pytest.approx((1 + f) ** 2)

    def test_flat_curve_gives_flat_forward(self) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])
        # On a flat curve, every forward rate equals the spot rate
        assert c.forward_rate(t1=2.0, t2=5.0) == pytest.approx(0.04)
        assert c.forward_rate(t1=10.0, t2=20.0) == pytest.approx(0.04)

    def test_t1_must_be_strictly_less_than_t2(self) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.04])
        with pytest.raises(ValueError, match="t1.*t2"):
            c.forward_rate(t1=5.0, t2=5.0)
        with pytest.raises(ValueError, match="t1.*t2"):
            c.forward_rate(t1=10.0, t2=5.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestForwardRate -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Append to `Curve`:

```python
    def forward_rate(self, *, t1: float, t2: float) -> float:
        """Annually compounded forward rate between ``t1`` and ``t2``.

        Derived from the discount factors:
        ``DF(t1) / DF(t2) = (1 + F(t1, t2))^(t2 - t1)``
        """
        if t1 >= t2:
            msg = f"t1 ({t1}) must be strictly less than t2 ({t2})"
            raise ValueError(msg)
        df1 = self._scalar_spot(t1)
        df2 = self._scalar_spot(t2)
        # Annually compounded DFs
        df1_factor = (1.0 + df1) ** (-t1)
        df2_factor = (1.0 + df2) ** (-t2)
        return (df1_factor / df2_factor) ** (1.0 / (t2 - t1)) - 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_accessors.py::TestForwardRate -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_accessors.py
git commit -m "feat(curves): add Curve.forward_rate (scalar t1, t2)"
```

---

### Task 8: `shift_parallel(bps)`

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_shift.py`
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Create: `bindings/python/tests/curves/test_curve_shifts.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_shifts.py
"""Curve stress / shift tests."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gaspatchio_core.curves._curve import Curve


class TestShiftParallel:
    def test_shifts_every_rate_by_bps(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        up = c.shift_parallel(bps=100)
        assert up.rates == tuple(r + 0.01 for r in eiopa_eur_2026q2_zero_rates)

    def test_negative_bps_shifts_down(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        down = c.shift_parallel(bps=-100)
        assert down.rates == tuple(r - 0.01 for r in eiopa_eur_2026q2_zero_rates)

    def test_zero_bps_returns_equal_curve(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.shift_parallel(bps=0) == c

    def test_shift_preserves_tenors_and_day_count(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        up = c.shift_parallel(bps=50)
        assert up.tenors == c.tenors
        assert up.day_count == c.day_count
        assert up.interpolation == c.interpolation

    def test_shifts_compose(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # shift +100 then +50 == shift +150
        a = c.shift_parallel(bps=100).shift_parallel(bps=50)
        b = c.shift_parallel(bps=150)
        assert a == b

    @given(bps=st.integers(min_value=-500, max_value=500))
    def test_shift_then_unshift_recovers_original(self, bps: int) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        recovered = c.shift_parallel(bps=bps).shift_parallel(bps=-bps)
        for orig, rec in zip(c.rates, recovered.rates):
            assert rec == pytest.approx(orig, abs=1e-12)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_shifts.py::TestShiftParallel -v`
Expected: FAIL — `AttributeError: 'Curve' object has no attribute 'shift_parallel'`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/curves/_shift.py
"""Curve shift / stress operations.

Each shift returns a NEW Curve (immutability invariant). Phase 1 ships
parallel shift and key-rate shift; non-parallel principal-component
shifts are deferred.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.curves._curve import Curve


def shift_parallel(curve: Curve, bps: float) -> Curve:
    """Return a new Curve with every knot rate shifted by ``bps`` basis points."""
    delta = bps / 10_000.0
    shifted_rates = tuple(r + delta for r in curve.rates)
    # Reuse the constructor so validation runs (in this case, length and
    # strictly-increasing tenors are unchanged).
    return type(curve)(
        tenors=curve.tenors,
        rates=shifted_rates,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
    )
```

Append to `Curve` in `_curve.py`:

```python
    def shift_parallel(self, *, bps: float) -> Curve:
        """Return a new Curve with every knot rate shifted by ``bps`` basis points."""
        from gaspatchio_core.curves._shift import shift_parallel
        return shift_parallel(self, bps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_shifts.py::TestShiftParallel -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_shift.py bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_shifts.py
git commit -m "feat(curves): add Curve.shift_parallel + property tests"
```

---

### Task 9: `key_rate_shift(tenor, bps)`

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_shift.py`
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Modify: `bindings/python/tests/curves/test_curve_shifts.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
class TestKeyRateShift:
    def test_shifts_only_named_tenor(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        shifted = c.key_rate_shift(tenor=10.0, bps=25)
        # The 10y knot is at index 6 (eiopa fixture)
        idx = eiopa_eur_2026q2_tenors.index(10.0)
        for i, (orig, new) in enumerate(zip(c.rates, shifted.rates)):
            if i == idx:
                assert new == pytest.approx(orig + 0.0025)
            else:
                assert new == pytest.approx(orig)

    def test_unknown_tenor_raises(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # Tenor 12.5 is not a knot
        with pytest.raises(ValueError, match="tenor 12.5 not in curve"):
            c.key_rate_shift(tenor=12.5, bps=25)

    def test_zero_bps_returns_equal_curve(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        assert c.key_rate_shift(tenor=10.0, bps=0) == c

    def test_two_key_rate_shifts_compose(
        self,
        eiopa_eur_2026q2_tenors: list[float],
        eiopa_eur_2026q2_zero_rates: list[float],
    ) -> None:
        c = Curve.from_zero_rates(
            tenors=eiopa_eur_2026q2_tenors,
            rates=eiopa_eur_2026q2_zero_rates,
        )
        # Shift 5y by +25 and 10y by +50 — order shouldn't matter
        a = c.key_rate_shift(tenor=5.0, bps=25).key_rate_shift(tenor=10.0, bps=50)
        b = c.key_rate_shift(tenor=10.0, bps=50).key_rate_shift(tenor=5.0, bps=25)
        assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_shifts.py::TestKeyRateShift -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Append to `_shift.py`:

```python
def key_rate_shift(curve: Curve, tenor: float, bps: float) -> Curve:
    """Shift the rate at exactly one knot tenor by ``bps`` basis points.

    Raises ``ValueError`` if ``tenor`` is not an exact knot. Phase 1 does
    not support fractional / interpolated key-rate shifts (Phase 2 if a
    customer needs it).
    """
    if tenor not in curve.tenors:
        msg = f"tenor {tenor} not in curve; got knots {list(curve.tenors)}"
        raise ValueError(msg)
    delta = bps / 10_000.0
    idx = curve.tenors.index(tenor)
    shifted_rates = tuple(
        r + delta if i == idx else r for i, r in enumerate(curve.rates)
    )
    return type(curve)(
        tenors=curve.tenors,
        rates=shifted_rates,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
    )
```

Append to `Curve`:

```python
    def key_rate_shift(self, *, tenor: float, bps: float) -> Curve:
        """Return a new Curve with the rate at the given knot tenor shifted by ``bps``."""
        from gaspatchio_core.curves._shift import key_rate_shift
        return key_rate_shift(self, tenor, bps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_shifts.py::TestKeyRateShift -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_shift.py bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_shifts.py
git commit -m "feat(curves): add Curve.key_rate_shift"
```

---

### Task 10: `Curve.from_par_rates` — par-to-zero bootstrap

**Files:**
- Create: `bindings/python/gaspatchio_core/curves/_bootstrap.py`
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Create: `bindings/python/tests/curves/test_curve_par_rates.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_par_rates.py
"""Curve.from_par_rates bootstrap tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._curve import Curve


class TestFromParRates:
    def test_flat_par_curve_gives_flat_zero_curve(self) -> None:
        # If par rate is constant p at every annual maturity, the zero curve
        # is also constant p (annually compounded coupon bond at par)
        tenors = [1.0, 2.0, 3.0, 5.0, 10.0]
        par_rates = [0.04] * 5
        c = Curve.from_par_rates(tenors=tenors, par_rates=par_rates)
        for r in c.rates:
            assert r == pytest.approx(0.04, abs=1e-9)

    def test_zero_to_par_round_trip(self) -> None:
        # Build a curve from zeros, derive its par rates, rebuild from par,
        # confirm the original zero curve is recovered.
        zero_tenors = [1.0, 2.0, 3.0, 5.0]
        zero_rates = [0.03, 0.035, 0.04, 0.045]
        original = Curve.from_zero_rates(tenors=zero_tenors, rates=zero_rates)
        from gaspatchio_core.curves._bootstrap import zero_to_par_rates
        par_rates = zero_to_par_rates(zero_tenors, zero_rates)
        rebuilt = Curve.from_par_rates(tenors=zero_tenors, par_rates=par_rates)
        for orig, rec in zip(original.rates, rebuilt.rates):
            assert rec == pytest.approx(orig, abs=1e-9)

    def test_tenor_validation(self) -> None:
        # Bootstrap requires integer-year-spaced tenors starting at year 1
        with pytest.raises(ValueError, match="annual.*starting at 1"):
            Curve.from_par_rates(tenors=[0.5, 1.5, 2.5], par_rates=[0.03, 0.035, 0.04])
        with pytest.raises(ValueError, match="annual.*starting at 1"):
            Curve.from_par_rates(tenors=[2.0, 3.0, 4.0], par_rates=[0.03, 0.035, 0.04])

    def test_carries_day_count(self) -> None:
        from gaspatchio_core.schedule._day_count import Actual360

        c = Curve.from_par_rates(
            tenors=[1.0, 2.0, 3.0],
            par_rates=[0.03, 0.035, 0.04],
            day_count=Actual360(),
        )
        assert c.day_count == Actual360()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_par_rates.py::TestFromParRates -v`
Expected: FAIL — `AttributeError: type object 'Curve' has no attribute 'from_par_rates'`.

- [ ] **Step 3: Implement**

```python
# bindings/python/gaspatchio_core/curves/_bootstrap.py
"""Par-to-zero bootstrap and zero-to-par derivation.

Phase 1 commits to annually compounded par bonds at integer-year tenors
starting at year 1. The bootstrap pattern:

    DF(t) = (1 - p_t * sum_{i<t} DF(i)) / (1 + p_t)

where ``p_t`` is the par coupon rate at maturity ``t`` and DF(0) = 1.
The zero rate at tenor ``t`` is then ``r_t = DF(t)^(-1/t) - 1``.
"""

from __future__ import annotations

from typing import Sequence


def _validate_annual_tenors(tenors: Sequence[float]) -> None:
    if not tenors or tenors[0] != 1.0:
        msg = f"par-rate tenors must be annual (1, 2, 3, ...) starting at 1; got {list(tenors)}"
        raise ValueError(msg)
    for i in range(1, len(tenors)):
        if tenors[i] - tenors[i - 1] != 1.0:
            msg = f"par-rate tenors must be annual (1, 2, 3, ...) starting at 1; got {list(tenors)}"
            raise ValueError(msg)


def par_to_zero_rates(tenors: Sequence[float], par_rates: Sequence[float]) -> list[float]:
    """Bootstrap zero rates from annual par rates."""
    _validate_annual_tenors(tenors)
    discount_factors: list[float] = []
    for i, (t, p) in enumerate(zip(tenors, par_rates)):
        if i == 0:
            df = 1.0 / (1.0 + p)
        else:
            df = (1.0 - p * sum(discount_factors)) / (1.0 + p)
        discount_factors.append(df)
    # Convert DFs to zero rates: r = DF^(-1/t) - 1
    zero_rates = [df ** (-1.0 / t) - 1.0 for t, df in zip(tenors, discount_factors)]
    return zero_rates


def zero_to_par_rates(tenors: Sequence[float], zero_rates: Sequence[float]) -> list[float]:
    """Derive annual par coupon rates from a zero curve.

    Inverse of :func:`par_to_zero_rates`. ``p_t = (1 - DF(t)) / sum_{i<=t} DF(i)``.
    """
    _validate_annual_tenors(tenors)
    discount_factors = [(1.0 + r) ** (-t) for t, r in zip(tenors, zero_rates)]
    par_rates: list[float] = []
    for i in range(len(tenors)):
        cumulative_df = sum(discount_factors[: i + 1])
        p = (1.0 - discount_factors[i]) / cumulative_df
        par_rates.append(p)
    return par_rates


__all__ = ["par_to_zero_rates", "zero_to_par_rates"]
```

Append to `Curve`:

```python
    @classmethod
    def from_par_rates(
        cls,
        *,
        tenors: list[float],
        par_rates: list[float],
        day_count: DayCount | None = None,
        interpolation: InterpolationMethod = "linear",
    ) -> Curve:
        """Build a Curve via bootstrap from annual par coupon rates.

        Phase 1 supports integer-year tenors starting at year 1 only.
        Returns a Curve whose ``rates`` are zero rates derived via the
        bootstrap recursion.
        """
        from gaspatchio_core.curves._bootstrap import par_to_zero_rates
        zero_rates = par_to_zero_rates(tenors, par_rates)
        return cls.from_zero_rates(
            tenors=tenors,
            rates=zero_rates,
            day_count=day_count,
            interpolation=interpolation,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_par_rates.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_bootstrap.py bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_par_rates.py
git commit -m "feat(curves): add Curve.from_par_rates with bootstrap"
```

---

### Task 11: Canonical form + `source_sha()`

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/_curve.py`
- Create: `bindings/python/tests/curves/test_curve_canonical.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/curves/test_curve_canonical.py
"""Curve canonical-form + source_sha tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._curve import Curve
from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
)


class TestCanonicalForm:
    def test_canonical_shape(self) -> None:
        c = Curve.from_zero_rates(
            tenors=[1.0, 5.0, 10.0],
            rates=[0.03, 0.04, 0.05],
            day_count=ActualActualISDA(),
        )
        cf = c.canonical_form()
        assert cf == {
            "kind": "Curve",
            "tenors": [1.0, 5.0, 10.0],
            "rates": [0.03, 0.04, 0.05],
            "day_count": "ActualActualISDA",
            "interpolation": "linear",
        }

    def test_lists_not_tuples_in_canonical(self) -> None:
        # Canonical form must be JSON-serialisable — tuples become lists
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        cf = c.canonical_form()
        assert isinstance(cf["tenors"], list)
        assert isinstance(cf["rates"], list)


class TestSourceSha:
    def test_identical_curves_have_identical_sha(self) -> None:
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        assert a.source_sha() == b.source_sha()

    def test_different_rate_changes_sha(self) -> None:
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.041])
        assert a.source_sha() != b.source_sha()

    def test_different_day_count_changes_sha(self) -> None:
        a = Curve.from_zero_rates(
            tenors=[1.0, 5.0], rates=[0.03, 0.04], day_count=Actual365Fixed(),
        )
        b = Curve.from_zero_rates(
            tenors=[1.0, 5.0], rates=[0.03, 0.04], day_count=Actual360(),
        )
        assert a.source_sha() != b.source_sha()

    def test_shifted_curve_has_different_sha(self) -> None:
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = a.shift_parallel(bps=100)
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self) -> None:
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        sha = c.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_canonical.py -v`
Expected: FAIL — `AttributeError: 'Curve' object has no attribute 'canonical_form'`.

- [ ] **Step 3: Implement**

Append to `Curve`:

```python
import hashlib

from gaspatchio_core.schedule._canonical import canonical_bytes


# inside Curve:
    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this Curve."""
        return {
            "kind": "Curve",
            "tenors": list(self.tenors),
            "rates": list(self.rates),
            "day_count": self.day_count.name(),
            "interpolation": self.interpolation,
        }

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes."""
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_canonical.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/_curve.py bindings/python/tests/curves/test_curve_canonical.py
git commit -m "feat(curves): add canonical_form + source_sha for fingerprint"
```

---

### Task 12: Public API exposure

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/__init__.py`
- Modify: `bindings/python/gaspatchio_core/curves/__init__.pyi` (full stubs in Task 14)
- Modify: `bindings/python/gaspatchio_core/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/curves/test_curve_construction.py`:

```python
class TestPublicAPI:
    def test_curve_importable_from_subpackage(self) -> None:
        from gaspatchio_core.curves import Curve
        from gaspatchio_core.curves._curve import Curve as PrivateCurve
        assert Curve is PrivateCurve

    def test_top_level_import(self) -> None:
        import gaspatchio_core
        assert hasattr(gaspatchio_core, "Curve")

    def test_top_level___all___includes_curve(self) -> None:
        import gaspatchio_core
        assert "Curve" in gaspatchio_core.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_construction.py::TestPublicAPI -v`
Expected: FAIL — `ImportError: cannot import name 'Curve' from 'gaspatchio_core.curves'`.

- [ ] **Step 3: Update curves package __init__**

Replace `gaspatchio_core/curves/__init__.py`:

```python
"""Typed term-structure primitive — Curve.

Phase 1 typed input for the rollforward redesign. Coexists with the
existing column-of-rates surface; nothing is forced to migrate.
"""

from __future__ import annotations

from gaspatchio_core.curves._curve import Curve

__all__ = ["Curve"]
```

- [ ] **Step 4: Wire into top-level**

In `bindings/python/gaspatchio_core/__init__.py`, add to imports (alphabetical, with the other typed inputs):

```python
from .curves import Curve
```

Add `"Curve"` to the `__all__` list.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_construction.py::TestPublicAPI -v`
Expected: PASS — 3 tests.

- [ ] **Step 6: Verify the full test suite still imports**

Run: `cd bindings/python && uv run pytest tests/ -x --co -q 2>&1 | tail -20`
Expected: collection succeeds with no `ImportError`.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/__init__.py bindings/python/gaspatchio_core/__init__.py bindings/python/tests/curves/test_curve_construction.py
git commit -m "feat(curves): wire Curve into public API"
```

---

### Task 13: Polars integration smoke test

**Files:**
- Create: `bindings/python/tests/curves/test_curve_polars_integration.py`

- [ ] **Step 1: Write the smoke test**

```python
# bindings/python/tests/curves/test_curve_polars_integration.py
"""End-to-end smoke test — Curve composes with Polars LazyFrames + Schedule."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import Curve, Schedule


class TestCurveSchedulePolarsIntegration:
    def test_spot_rate_from_schedule_year_fractions(self) -> None:
        # Schedule produces a list of year fractions; Curve maps each to a rate
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        yfs = sched.year_fractions()  # list[float] of length 12, each = 1/12

        curve = Curve.from_zero_rates(
            tenors=[0.5, 1.0, 5.0, 10.0],
            rates=[0.025, 0.030, 0.035, 0.040],
        )
        rates = curve.spot_rate(yfs)
        assert isinstance(rates, list)
        assert len(rates) == 12
        # Every year fraction is 1/12 ≈ 0.083 → curve flat-extrapolates to first knot rate (0.025)
        for r in rates:
            assert r == pytest.approx(0.025)

    def test_spot_rate_from_per_row_year_fractions_expr(self) -> None:
        sched = Schedule.from_inception(
            inception_column="inception",
            n_periods=3,
            frequency="1Y",  # annual periods so year fractions hit the curve's interesting region
        )
        df = pl.DataFrame({"inception": [date(2025, 1, 1)]})
        df2 = df.with_columns(yfs=sched.year_fractions_expr())
        # Sanity: each row's yfs is List<Float64> of length 3, all = 1.0
        for row in df2.get_column("yfs").to_list():
            for yf in row:
                assert yf == pytest.approx(1.0)

    def test_curve_spot_rate_in_with_columns_pipeline(self) -> None:
        # User-style: af.col(t) -> curve.spot_rate(t) -> column expression
        curve = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.04, 0.05])
        df = pl.DataFrame({"t": [1.0, 3.0, 5.0, 10.0]})
        result = df.with_columns(rate=curve.spot_rate(pl.col("t")))
        # Linear interp between knots:
        #   t=1 -> 0.03, t=3 -> 0.035, t=5 -> 0.04, t=10 -> 0.05
        assert result.get_column("rate").to_list() == pytest.approx(
            [0.03, 0.035, 0.04, 0.05]
        )

    def test_curve_grow_pattern_user_facing(self) -> None:
        # Pattern from spec §4.4: the rate column feeds a growth multiplier
        curve = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])
        df = pl.DataFrame(
            {
                "av": [100.0, 200.0, 300.0],
                "t": [1.0, 5.0, 10.0],
            }
        )
        result = df.with_columns(
            rate=curve.spot_rate(pl.col("t")),
        ).with_columns(
            grown=pl.col("av") * (1 + pl.col("rate") * (1 / 12)),
        )
        # Each av gets multiplied by 1 + 0.04 * 1/12 ≈ 1.003333
        expected = [v * (1 + 0.04 / 12) for v in [100.0, 200.0, 300.0]]
        assert result.get_column("grown").to_list() == pytest.approx(expected)
```

- [ ] **Step 2: Run smoke test**

Run: `cd bindings/python && uv run pytest tests/curves/test_curve_polars_integration.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/curves/test_curve_polars_integration.py
git commit -m "test(curves): smoke — Curve composes with Schedule + Polars LazyFrame"
```

---

### Task 14: pyi stubs

**Files:**
- Modify: `bindings/python/gaspatchio_core/curves/__init__.pyi`

- [ ] **Step 1: Write the stubs**

Replace `bindings/python/gaspatchio_core/curves/__init__.pyi`:

```python
"""Type stubs for gaspatchio_core.curves."""

from __future__ import annotations

from typing import Literal, Union

import numpy as np
import polars as pl

from gaspatchio_core.schedule import DayCount

InterpolationMethod = Literal["linear"]
TimeInput = Union[float, int, list[float], np.ndarray, pl.Series, pl.Expr]

class Curve:
    tenors: tuple[float, ...]
    rates: tuple[float, ...]
    day_count: DayCount
    interpolation: InterpolationMethod

    @classmethod
    def from_zero_rates(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        day_count: DayCount | None = ...,
        interpolation: InterpolationMethod = ...,
    ) -> Curve: ...
    @classmethod
    def from_par_rates(
        cls,
        *,
        tenors: list[float],
        par_rates: list[float],
        day_count: DayCount | None = ...,
        interpolation: InterpolationMethod = ...,
    ) -> Curve: ...
    def spot_rate(self, t: TimeInput) -> float | list[float] | np.ndarray | pl.Series | pl.Expr: ...
    def discount_factor(self, t: TimeInput) -> float | list[float] | np.ndarray | pl.Series | pl.Expr: ...
    def forward_rate(self, *, t1: float, t2: float) -> float: ...
    def shift_parallel(self, *, bps: float) -> Curve: ...
    def key_rate_shift(self, *, tenor: float, bps: float) -> Curve: ...
    def canonical_form(self) -> dict[str, object]: ...
    def source_sha(self) -> str: ...

__all__ = ["Curve"]
```

- [ ] **Step 2: Verify stubtest is clean**

Run: `cd bindings/python && uv run python -m mypy.stubtest gaspatchio_core.curves --allowlist stubtest-allowlist.txt 2>&1 | tail -20`
Expected: zero errors. If any errors surface, fix the stub inline.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/curves/__init__.pyi
git commit -m "feat(curves): full pyi stubs for Curve public surface"
```

---

### Task 15: Lint + format + type check + final pass

**Files:**
- (verification-only)

- [ ] **Step 1: Lint clean**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/curves tests/curves`
Expected: no errors. If issues surface, address them inline (match existing per-file-ignores patterns; do NOT introduce blanket `# noqa`).

- [ ] **Step 2: Format check**

Run: `cd bindings/python && uv run ruff format --check gaspatchio_core/curves tests/curves`
Expected: no diffs. If reformatting is needed, run `uv run ruff format gaspatchio_core/curves tests/curves` and stage.

- [ ] **Step 3: Type check**

Run: `cd bindings/python && uv run mypy gaspatchio_core/curves 2>&1 | tail -20`
Expected: zero errors.

- [ ] **Step 4: Full curves test suite**

Run: `cd bindings/python && uv run pytest tests/curves -v`
Expected: PASS — ~50 tests across 8 test files.

- [ ] **Step 5: Verify rest of repo is green**

Run: `cd bindings/python && uv run pytest tests/ -q 2>&1 | tail -5`
Expected: prior pass-count plus the new curves tests.

- [ ] **Step 6: Commit any cleanup**

```bash
git add bindings/python/gaspatchio_core/curves
git commit -m "chore(curves): lint + format + type-check fixups"
```

If nothing changed, skip the commit.

---

### Task 16: README + spec status update

**Files:**
- Modify: `ref/36-rollforward-redesign/README.md`

- [ ] **Step 1: Update sub-plan README**

Update the implementation status block to mark Sub-plan B shipped:

```markdown
## Implementation status

- **Phase 1a Sub-plan A — Typed Time** (Schedule + Calendar + DayCount): ✅ shipped
- **Phase 1a Sub-plan B — Curve**: ✅ shipped (this branch)
- **Phase 1a Sub-plan C — MortalityTable**: not started
- **Phase 1a Sub-plan D — State-machine kernel**: not started

Plans:
- [`plans/2026-05-04-phase-1a-schedule.md`](plans/2026-05-04-phase-1a-schedule.md)
- [`plans/2026-05-04-phase-1a-curve.md`](plans/2026-05-04-phase-1a-curve.md)
```

- [ ] **Step 2: Commit**

```bash
git add ref/36-rollforward-redesign/README.md
git commit -m "docs(rollforward-redesign): mark Sub-plan B (Curve) shipped"
```

---

## Self-review

Re-reading the plan against the spec and the gates above:

**Spec coverage check:**
- §4.14 `Curve.from_zero_rates`: tasks 2–7 ✓
- §4.14 `Curve.from_par_rates`: task 10 ✓
- §4.14 `spot_rate`, `discount_factor`, `forward_rate`: tasks 4, 5, 6, 7 ✓
- §4.14 `shift_parallel`, `key_rate_shift`: tasks 8, 9 ✓
- §13.1a `source_sha()`: task 11 ✓
- §13.1a both surfaces preserved (typed + column-of-rates): out-of-scope-by-construction; the existing column-of-rates surface is untouched and Curve is additive. Documented in §"Architecture" + §"Untouched". ✓
- §13.1a public-API exposure: task 12 ✓
- §17.4 explicit Phase 1 constructors only (regulatory loaders deferred): tasks 1–10 cover the Phase 1 constructors; loaders are explicitly listed in §"Out of scope" ✓

**Placeholder scan:**
- No "TBD", "implement later", "fill in details" anywhere.
- No "add appropriate error handling".
- All step-3 implementations show actual code.
- All test code is concrete.

**Type consistency:**
- `Curve` references consistent across all tasks.
- `tenors` is always `list[float]` at the API and stored as `tuple[float, ...]` internally — consistent.
- `rates` similarly.
- `day_count` is always a `DayCount` instance imported from `gaspatchio_core.schedule._day_count` — same module Plan A defines.
- Method signatures (`spot_rate`, `discount_factor`, `forward_rate`, `shift_parallel`, `key_rate_shift`, `canonical_form`, `source_sha`) match between tests, impl, and pyi stubs.
- `TimeInput` type alias used consistently in stubs to communicate the dispatch rule.

**Cross-plan consistency check (for upcoming Plans C and D):**
- `source_sha()` returns the same string format as Plan A's Schedule (`"sha256:<hex>"`) — Plan D's `action_key()` will sort-concat across all typed inputs and these will compose by string ✓
- `canonical_form()` returns a JSON-serialisable dict reusing Plan A's `canonical_bytes()` helper ✓
- Frozen-dataclass pattern matches Plan A's day-counts and calendars ✓
- Public-API exposure pattern matches Plan A (subpackage `__init__.py` exports + top-level re-export) ✓

**Risks I've flagged inline:**
- Task 4's `pl.Expr` accessor uses `map_elements` per-row Python interpolation. For Phase 1 production scale (1200 periods × 100K policies = 120M `map_elements` calls) this is 5–20× slower than a vectorised path but still tolerable. If benchmarks in Sub-plan D demand a vectorised lower, the natural promotion is to a Polars `pl.Expr.list.eval()` or to a small Rust plugin. Documented but not prioritised.
- Per-row Curve columns (where rates are a `pl.Expr` at construction time, not at call time) are explicitly deferred. This affects spec §4.4/§4.12/§4.13 examples that use `rates=af.col` — those examples will require a docs note. Not a Phase 1 blocker.
- `from_par_rates` is restricted to integer-year tenors starting at year 1. Real-world par curves include 0.5y / 1.5y / etc. Documented as a Phase 1 limitation.

---

## Execution handoff

Plan complete and saved to `ref/36-rollforward-redesign/plans/2026-05-04-phase-1a-curve.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Each task is small enough (3–7 steps, ~10–40 lines of new production code) that a focused subagent can land it cleanly.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

This plan is meant to be drafted alongside Plans C and D before any execution begins (per the staged sequencing decision). Execution sequencing: A first (foundation), then B and C in parallel (independent), then D (depends on A).
