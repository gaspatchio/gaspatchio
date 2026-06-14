# Phase 1a Sub-plan C — Typed MortalityTable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `MortalityTable` — a thin actuarial-convention wrapper over the existing `gaspatchio_core.assumptions.Table` that captures three audit-relevant pieces of metadata (`age_basis`, `structure`, `select_period`) and routes lookups through structure-aware `.at(...)` calls. Phase 1 supports the three production-relevant structures (`aggregate`, `select_ultimate`, `joint`); the convention-aware lookup makes auditor-checkable that two tables differing in age basis or select period produce different `spec_fingerprint`s. The wrapper does NOT add table-conversion utilities (`with_age_basis(...)`, etc.) — those require sub-annual mortality assumptions (UDD / Balducci / constant-force) and are deferred to Phase 2 per spec §4.15.

**Architecture:** Frozen-dataclass typed input under `gaspatchio_core/mortality/`. Wraps an existing `Table` instance — does not duplicate its file-loading, dimension-handling, or lookup-execution machinery. The structure-aware `.at(...)` method dispatches based on `structure`: aggregate is a thin pass-through to `Table.lookup(...)`; select-ultimate clamps `duration` at `select_period` (a documented Phase 1 simplification — most production CSO/SOA select-ultimate tables are organised so this works correctly); joint takes both lives' ages. `source_sha` is `sha256` over a canonical form that includes `Table.name`, the mortality metadata, and dimension keys. Adds a small `name` property to existing `Table` for clean access (no private-attribute reads).

**Tech Stack:** Python 3.10+; Polars 1.38.1 (pinned); reuses `gaspatchio_core.assumptions.Table` directly; reuses `gaspatchio_core.schedule._canonical.canonical_bytes`. No new third-party deps. No new Rust code.

---

## Scope check

This sub-plan is one independently-testable subsystem (typed mortality wrapper). No further decomposition.

**Out of scope (deferred):**
- `MortalityTable.with_age_basis(...)` table conversion — requires UDD / Balducci / constant-force assumption choice. Phase 2.
- Multi-decrement tables (mortality + lapse + disability composite) — Phase 3 if customer demand surfaces.
- Mortality improvement scales (MP-2014, MP-2021) — Phase 2 follow-up; addressable as a `Table` shock today.
- Dynamic select-ultimate dispatch where the underlying `Table` separates select and ultimate into different sub-tables — Phase 2. Phase 1 commits to the single-table-with-duration-axis convention.
- IR / kernel / fingerprint integration → Sub-plan D.

---

## File structure

**New (Python, all under `bindings/python/gaspatchio_core/mortality/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Public re-exports: `MortalityTable` |
| `__init__.pyi` | Type stubs |
| `_mortality_table.py` | `MortalityTable` frozen-dataclass + `.at()` dispatch + `source_sha()` |
| `_conventions.py` | `AgeBasis` and `Structure` Literal types + validation helpers |

**New (tests, all under `bindings/python/tests/mortality/`):**

| File | Responsibility |
|---|---|
| `__init__.py` | Empty marker |
| `conftest.py` | Sample mortality tables (aggregate, select-ultimate, joint) |
| `test_construction.py` | `MortalityTable` construction + validation |
| `test_at_aggregate.py` | Aggregate-structure lookup |
| `test_at_select_ultimate.py` | Select-ultimate dispatch with `select_period` |
| `test_at_joint.py` | Joint-life lookup |
| `test_canonical.py` | Canonical-form determinism + `source_sha` |
| `test_polars_integration.py` | End-to-end `.at()` in a `with_columns` pipeline |

**Modified:**

- `bindings/python/gaspatchio_core/assumptions/_api.py` — small additive change: add a public `name` property on `Table` so `MortalityTable` doesn't read the private `_name` attribute. One method, ~5 lines.
- `bindings/python/gaspatchio_core/__init__.py` — re-export `MortalityTable`
- `bindings/python/gaspatchio_core/__init__.py` `__all__` list — add `"MortalityTable"`

**Untouched:**
- `gaspatchio_core/assumptions/_api.py` Table mechanics — `MortalityTable` is purely additive.
- `gaspatchio_core/schedule/`, `gaspatchio_core/curves/` — Plan C imports the shared canonical-form helper from schedule but does not modify it.
- `gaspatchio_core/rollforward/` — old kernel stays running until Sub-plan D.

---

## Tasks

### Task 1: Package scaffolding + `Table.name` property

**Files:**
- Create: `bindings/python/gaspatchio_core/mortality/__init__.py`
- Create: `bindings/python/gaspatchio_core/mortality/__init__.pyi`
- Create: `bindings/python/tests/mortality/__init__.py`
- Modify: `bindings/python/gaspatchio_core/assumptions/_api.py` — add a `name` property
- Create: `bindings/python/tests/assumptions/test_name_property.py`

- [ ] **Step 1: Write the failing test for `Table.name`**

```python
# bindings/python/tests/assumptions/test_name_property.py
"""Verify Table.name public property — needed by MortalityTable wrapper."""

from __future__ import annotations

import polars as pl

from gaspatchio_core.assumptions import Table


class TestTableNameProperty:
    def test_name_returns_constructor_argument(self) -> None:
        df = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t = Table(name="test_mortality", source=df, dimensions={"age": "age"}, value="qx")
        assert t.name == "test_mortality"

    def test_name_is_read_only(self) -> None:
        df = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t = Table(name="test_mortality", source=df, dimensions={"age": "age"}, value="qx")
        # Property has no setter — assigning should raise AttributeError
        try:
            t.name = "renamed"  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            msg = "expected AttributeError on assigning to name"
            raise AssertionError(msg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/assumptions/test_name_property.py -v`
Expected: FAIL — `AttributeError: 'Table' object has no attribute 'name'`.

- [ ] **Step 3: Add the property**

In `bindings/python/gaspatchio_core/assumptions/_api.py`, find the existing `@property` blocks (around line 1055 for `schema`, 1094 for `dimensions`) and add a `name` property in the same style:

```python
    @property
    def name(self) -> str:
        """The table name supplied at construction.

        Used by the registry, the typed-input audit trail (e.g.
        :class:`gaspatchio_core.MortalityTable.source_sha`), and any external
        consumer that needs a stable identifier for this table.
        """
        return self._name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/assumptions/test_name_property.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Verify existing assumptions tests still pass**

Run: `cd bindings/python && uv run pytest tests/assumptions/ -q 2>&1 | tail -5`
Expected: prior pass-count unchanged (no regressions).

- [ ] **Step 6: Create empty mortality package files**

```python
# bindings/python/gaspatchio_core/mortality/__init__.py
"""Typed mortality wrapper — MortalityTable."""

from __future__ import annotations

__all__: list[str] = []
```

```python
# bindings/python/gaspatchio_core/mortality/__init__.pyi
"""Type stubs for gaspatchio_core.mortality."""
__all__: list[str] = []
```

```python
# bindings/python/tests/mortality/__init__.py
```

- [ ] **Step 7: Verify package imports cleanly**

Run: `cd bindings/python && uv run python -c "import gaspatchio_core.mortality"`
Expected: no error, no output.

- [ ] **Step 8: Commit**

```bash
git add bindings/python/gaspatchio_core/assumptions/_api.py bindings/python/tests/assumptions/test_name_property.py bindings/python/gaspatchio_core/mortality/ bindings/python/tests/mortality/__init__.py
git commit -m "feat(mortality): scaffold package + add Table.name public property"
```

---

### Task 2: `MortalityTable` frozen-dataclass + constructor + validation

**Files:**
- Create: `bindings/python/gaspatchio_core/mortality/_conventions.py`
- Create: `bindings/python/gaspatchio_core/mortality/_mortality_table.py`
- Create: `bindings/python/tests/mortality/conftest.py`
- Create: `bindings/python/tests/mortality/test_construction.py`

- [ ] **Step 1: Write the conftest**

```python
# bindings/python/tests/mortality/conftest.py
"""Shared fixtures for MortalityTable tests."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


@pytest.fixture
def aggregate_table() -> Table:
    """A simple aggregate mortality table indexed by age."""
    df = pl.DataFrame(
        {
            "age": [30, 35, 40, 45, 50, 55, 60, 65, 70],
            "qx": [0.001, 0.0015, 0.002, 0.003, 0.005, 0.008, 0.013, 0.020, 0.030],
        }
    )
    return Table(name="cso_2017_male_aggregate", source=df, dimensions={"age": "age"}, value="qx")


@pytest.fixture
def select_ultimate_table() -> Table:
    """A select-ultimate mortality table indexed by age × duration.

    For a select_period of 5: durations 1..5 contain select rates;
    durations 6..N contain the ultimate rate (constant per age) so a
    'duration clamped at select_period' lookup yields the ultimate rate.
    """
    rows = []
    for age in [30, 40, 50]:
        # Select rates: lower than ultimate (select effect)
        for duration in range(1, 6):
            rows.append(
                {"age": age, "duration": duration, "qx": 0.001 * age * (1 + 0.1 * duration)}
            )
        # Duration 5 (clamped value) and beyond should yield the ultimate rate.
        # We pre-fill duration=5 with the ultimate value so 'clamped' lookup works.
        # Rows for duration=5 above are select_5; we'd need a separate ultimate column
        # in production. For Phase 1 simplicity, this fixture uses duration=5 as the
        # ultimate-rate pivot (covered by select_period=4 in tests).
    df = pl.DataFrame(rows)
    return Table(
        name="select_ultimate_demo",
        source=df,
        dimensions={"age": "age", "duration": "duration"},
        value="qx",
    )


@pytest.fixture
def joint_life_table() -> Table:
    """A simple joint-life mortality table indexed by both ages."""
    rows = []
    for a1 in [60, 65, 70]:
        for a2 in [60, 65, 70]:
            rows.append({"age_1": a1, "age_2": a2, "qx": 0.0001 * a1 * a2})
    df = pl.DataFrame(rows)
    return Table(
        name="joint_life_demo",
        source=df,
        dimensions={"age_1": "age_1", "age_2": "age_2"},
        value="qx",
    )
```

- [ ] **Step 2: Write the failing test**

```python
# bindings/python/tests/mortality/test_construction.py
"""MortalityTable construction + validation tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.mortality._mortality_table import MortalityTable


class TestMortalityTableConstruction:
    def test_aggregate_basic_construction(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        assert m.table is aggregate_table
        assert m.age_basis == "age_last_birthday"
        assert m.structure == "aggregate"
        assert m.select_period is None

    def test_select_ultimate_requires_select_period(self, select_ultimate_table: Table) -> None:
        # Constructing select_ultimate without select_period raises
        with pytest.raises(ValueError, match="select_period"):
            MortalityTable(
                table=select_ultimate_table,
                age_basis="age_last_birthday",
                structure="select_ultimate",
            )

    def test_select_ultimate_with_select_period_constructs(
        self, select_ultimate_table: Table,
    ) -> None:
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        assert m.structure == "select_ultimate"
        assert m.select_period == 10

    def test_aggregate_rejects_select_period(self, aggregate_table: Table) -> None:
        # select_period only valid for select_ultimate
        with pytest.raises(ValueError, match="select_period"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_last_birthday",
                structure="aggregate",
                select_period=10,
            )

    def test_joint_basic_construction(self, joint_life_table: Table) -> None:
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        assert m.structure == "joint"
        assert m.select_period is None

    def test_invalid_age_basis_raises(self, aggregate_table: Table) -> None:
        with pytest.raises(ValueError, match="age_basis"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_curtate",  # type: ignore[arg-type]
                structure="aggregate",
            )

    def test_invalid_structure_raises(self, aggregate_table: Table) -> None:
        with pytest.raises(ValueError, match="structure"):
            MortalityTable(
                table=aggregate_table,
                age_basis="age_last_birthday",
                structure="multi_decrement",  # type: ignore[arg-type]
            )

    def test_age_nearest_birthday_accepted(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        assert m.age_basis == "age_nearest_birthday"

    def test_is_frozen(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        with pytest.raises(Exception):
            m.something = 42  # type: ignore[attr-defined]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_construction.py -v`
Expected: FAIL — `ImportError: cannot import name 'MortalityTable'`.

- [ ] **Step 4: Implement conventions module**

```python
# bindings/python/gaspatchio_core/mortality/_conventions.py
"""Mortality-specific Literal types + validation helpers."""

from __future__ import annotations

from typing import Literal

AgeBasis = Literal["age_last_birthday", "age_nearest_birthday"]
Structure = Literal["aggregate", "select_ultimate", "joint"]

_VALID_AGE_BASES: frozenset[str] = frozenset({"age_last_birthday", "age_nearest_birthday"})
_VALID_STRUCTURES: frozenset[str] = frozenset({"aggregate", "select_ultimate", "joint"})


def validate_age_basis(value: str) -> None:
    if value not in _VALID_AGE_BASES:
        msg = (
            f"unknown age_basis {value!r}; expected one of "
            f"{sorted(_VALID_AGE_BASES)}"
        )
        raise ValueError(msg)


def validate_structure(value: str) -> None:
    if value not in _VALID_STRUCTURES:
        msg = (
            f"unknown structure {value!r}; expected one of "
            f"{sorted(_VALID_STRUCTURES)}"
        )
        raise ValueError(msg)


def validate_select_period(structure: str, select_period: int | None) -> None:
    if structure == "select_ultimate":
        if select_period is None:
            msg = "select_period is required when structure='select_ultimate'"
            raise ValueError(msg)
        if select_period < 1:
            msg = f"select_period must be a positive integer; got {select_period}"
            raise ValueError(msg)
    elif select_period is not None:
        msg = (
            f"select_period only valid for structure='select_ultimate'; "
            f"got structure={structure!r}"
        )
        raise ValueError(msg)


__all__ = [
    "AgeBasis",
    "Structure",
    "validate_age_basis",
    "validate_select_period",
    "validate_structure",
]
```

- [ ] **Step 5: Implement MortalityTable**

```python
# bindings/python/gaspatchio_core/mortality/_mortality_table.py
"""Typed mortality wrapper — MortalityTable.

A thin actuarial-convention wrapper over the existing
:class:`gaspatchio_core.assumptions.Table`. It does not duplicate Table's
file-loading or lookup mechanics; it adds three audit-relevant pieces of
metadata (``age_basis``, ``structure``, ``select_period``) and routes
``.at(...)`` calls through structure-aware dispatch.

Phase 1 commitments:
  - Three structures: ``aggregate``, ``select_ultimate``, ``joint``.
  - ``select_ultimate`` clamps ``duration`` at ``select_period`` (a documented
    Phase 1 simplification — the underlying Table is expected to be organised
    so that the rate at ``duration = select_period`` is the ultimate rate for
    that age).
  - Convention-aware ``.at(...)`` accepts an ``age_basis`` keyword override
    that is validated and recorded for audit but does NOT perform table
    conversion (deferred to Phase 2's ``with_age_basis`` utility).
  - ``source_sha()`` over a canonical form including ``Table.name`` plus the
    metadata.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gaspatchio_core.mortality._conventions import (
    AgeBasis,
    Structure,
    validate_age_basis,
    validate_select_period,
    validate_structure,
)
from gaspatchio_core.schedule._canonical import canonical_bytes

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.assumptions import Table


@dataclass(frozen=True)
class MortalityTable:
    """Convention-aware wrapper over an existing :class:`Table`."""

    table: "Table"
    age_basis: AgeBasis
    structure: Structure
    select_period: int | None = None

    def __post_init__(self) -> None:
        validate_age_basis(self.age_basis)
        validate_structure(self.structure)
        validate_select_period(self.structure, self.select_period)


__all__ = ["MortalityTable"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_construction.py -v`
Expected: PASS — 9 tests.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/_conventions.py bindings/python/gaspatchio_core/mortality/_mortality_table.py bindings/python/tests/mortality/conftest.py bindings/python/tests/mortality/test_construction.py
git commit -m "feat(mortality): add MortalityTable frozen dataclass + validation"
```

---

### Task 3: `.at()` for `aggregate` structure

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/_mortality_table.py`
- Create: `bindings/python/tests/mortality/test_at_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/mortality/test_at_aggregate.py
"""Aggregate-structure .at() lookup."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.mortality._mortality_table import MortalityTable


class TestAggregateAt:
    def test_lookup_by_age_returns_expr(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        result = m.at(age=pl.col("attained_age"))
        assert isinstance(result, pl.Expr)

    def test_lookup_in_with_columns_returns_correct_rates(
        self, aggregate_table: Table,
    ) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        df = pl.DataFrame({"attained_age": [30, 40, 50, 60, 70]})
        result = df.with_columns(qx=m.at(age=pl.col("attained_age")))
        assert result.get_column("qx").to_list() == pytest.approx(
            [0.001, 0.002, 0.005, 0.013, 0.030]
        )

    def test_aggregate_rejects_duration_kwarg(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        # Aggregate tables don't accept duration — would cause Table.lookup to fail
        # with an unhelpful error; MortalityTable.at gives a clearer one.
        with pytest.raises(ValueError, match="aggregate.*duration"):
            m.at(age=pl.col("attained_age"), duration=pl.col("policy_year"))

    def test_age_basis_kwarg_documented_only(self, aggregate_table: Table) -> None:
        # Phase 1 accepts age_basis kwarg but does NOT perform conversion;
        # supplying a value matching the table's basis is a no-op.
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        # Same basis: works
        df = pl.DataFrame({"attained_age": [40]})
        df_same = df.with_columns(
            qx=m.at(age=pl.col("attained_age"), age_basis="age_last_birthday"),
        )
        assert df_same.get_column("qx").to_list() == pytest.approx([0.002])

    def test_age_basis_kwarg_mismatch_raises(self, aggregate_table: Table) -> None:
        # Different basis: Phase 1 raises (because we don't convert).
        # Phase 2's with_age_basis would handle this.
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        with pytest.raises(ValueError, match="age_basis.*conversion.*Phase 2"):
            m.at(age=pl.col("attained_age"), age_basis="age_nearest_birthday")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_aggregate.py -v`
Expected: FAIL — `AttributeError: 'MortalityTable' object has no attribute 'at'`.

- [ ] **Step 3: Implement**

Append to `_mortality_table.py`:

```python
import polars as pl  # noqa: TCH002 — used at runtime in dispatch

# inside MortalityTable:

    def at(
        self,
        *,
        age: pl.Expr | None = None,
        age_1: pl.Expr | None = None,
        age_2: pl.Expr | None = None,
        duration: pl.Expr | None = None,
        age_basis: AgeBasis | None = None,
        **other: pl.Expr,
    ) -> pl.Expr:
        """Convention-aware lookup.

        The accepted kwargs depend on ``self.structure``:
          - ``aggregate``: ``age`` (required), plus any extra dimensions
            on the underlying Table (gender, smoker, etc.) via ``**other``.
          - ``select_ultimate``: ``age`` and ``duration`` both required.
          - ``joint``: ``age_1`` and ``age_2`` both required.

        ``age_basis`` is validated against ``self.age_basis``; supplying a
        different basis raises (Phase 1 has no automatic conversion — see
        Phase 2's ``with_age_basis(...)``).
        """
        if age_basis is not None:
            validate_age_basis(age_basis)
            if age_basis != self.age_basis:
                msg = (
                    f"requested age_basis={age_basis!r} but table's age_basis "
                    f"is {self.age_basis!r}; cross-basis conversion is a Phase 2 "
                    f"feature (with_age_basis)"
                )
                raise ValueError(msg)

        if self.structure == "aggregate":
            if age is None:
                msg = "aggregate structure requires age=..."
                raise ValueError(msg)
            if duration is not None:
                msg = (
                    "aggregate structure does not accept duration=...; "
                    "use structure='select_ultimate' if duration is meaningful"
                )
                raise ValueError(msg)
            return self.table.lookup(age=age, **other)

        if self.structure == "select_ultimate":
            return self._at_select_ultimate(
                age=age,
                duration=duration,
                **other,
            )

        if self.structure == "joint":
            return self._at_joint(age_1=age_1, age_2=age_2, **other)

        msg = f"unhandled structure {self.structure!r}"
        raise AssertionError(msg)

    def _at_select_ultimate(
        self,
        *,
        age: pl.Expr | None,
        duration: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        # Implemented in Task 4
        msg = "select_ultimate dispatch not yet implemented"
        raise NotImplementedError(msg)

    def _at_joint(
        self,
        *,
        age_1: pl.Expr | None,
        age_2: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        # Implemented in Task 5
        msg = "joint dispatch not yet implemented"
        raise NotImplementedError(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_aggregate.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/_mortality_table.py bindings/python/tests/mortality/test_at_aggregate.py
git commit -m "feat(mortality): add MortalityTable.at for aggregate structure"
```

---

### Task 4: `.at()` for `select_ultimate` structure

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/_mortality_table.py`
- Create: `bindings/python/tests/mortality/test_at_select_ultimate.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/mortality/test_at_select_ultimate.py
"""Select-ultimate dispatch with select_period clamping."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.mortality._mortality_table import MortalityTable


class TestSelectUltimateAt:
    def test_duration_within_select_period_uses_select_rate(
        self, select_ultimate_table: Table,
    ) -> None:
        # Fixture rates: 0.001 * age * (1 + 0.1 * duration), durations 1..5
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        df = pl.DataFrame({"age": [30, 40], "duration": [1, 3]})
        result = df.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Age 30, duration 1 -> 0.001 * 30 * 1.1 = 0.033
        # Age 40, duration 3 -> 0.001 * 40 * 1.3 = 0.052
        assert result.get_column("qx").to_list() == pytest.approx([0.033, 0.052])

    def test_duration_above_select_period_clamps_to_select_period(
        self, select_ultimate_table: Table,
    ) -> None:
        # select_period=4 -> durations >= 5 should clamp to 5 in the lookup
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        df = pl.DataFrame({"age": [30, 40], "duration": [10, 25]})
        result = df.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Both clamped to duration=5: 0.001 * age * (1 + 0.1 * 5) = 0.0015 * age
        # Age 30 -> 0.045, Age 40 -> 0.060
        assert result.get_column("qx").to_list() == pytest.approx([0.045, 0.060])

    def test_select_ultimate_requires_age_and_duration(
        self, select_ultimate_table: Table,
    ) -> None:
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        with pytest.raises(ValueError, match="select_ultimate.*requires.*age.*duration"):
            m.at(age=pl.col("age"))
        with pytest.raises(ValueError, match="select_ultimate.*requires.*age.*duration"):
            m.at(duration=pl.col("duration"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_select_ultimate.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement**

Replace the `_at_select_ultimate` stub with:

```python
    def _at_select_ultimate(
        self,
        *,
        age: pl.Expr | None,
        duration: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        if age is None or duration is None:
            msg = "structure='select_ultimate' requires both age=... and duration=..."
            raise ValueError(msg)
        # select_period is guaranteed non-None by the constructor's validate_select_period.
        assert self.select_period is not None
        clamped_duration = pl.when(duration > self.select_period).then(
            pl.lit(self.select_period)
        ).otherwise(duration)
        return self.table.lookup(age=age, duration=clamped_duration, **other)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_select_ultimate.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/_mortality_table.py bindings/python/tests/mortality/test_at_select_ultimate.py
git commit -m "feat(mortality): add select_ultimate dispatch with duration clamping"
```

---

### Task 5: `.at()` for `joint` structure

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/_mortality_table.py`
- Create: `bindings/python/tests/mortality/test_at_joint.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/mortality/test_at_joint.py
"""Joint-life .at() lookup."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.mortality._mortality_table import MortalityTable


class TestJointAt:
    def test_lookup_by_age_1_age_2_returns_expr(self, joint_life_table: Table) -> None:
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "age_1": [60, 65, 70],
                "age_2": [60, 70, 65],
            }
        )
        result = df.with_columns(
            qx=m.at(age_1=pl.col("age_1"), age_2=pl.col("age_2")),
        )
        # Fixture: 0.0001 * age_1 * age_2
        assert result.get_column("qx").to_list() == pytest.approx(
            [0.0001 * 60 * 60, 0.0001 * 65 * 70, 0.0001 * 70 * 65]
        )

    def test_joint_requires_both_ages(self, joint_life_table: Table) -> None:
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        with pytest.raises(ValueError, match="joint.*requires.*age_1.*age_2"):
            m.at(age_1=pl.col("age_1"))
        with pytest.raises(ValueError, match="joint.*requires.*age_1.*age_2"):
            m.at(age_2=pl.col("age_2"))

    def test_joint_rejects_single_age_kwarg(self, joint_life_table: Table) -> None:
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        with pytest.raises(ValueError, match="joint.*age_1.*age_2"):
            m.at(age=pl.col("age_1"), age_2=pl.col("age_2"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_joint.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement**

Replace the `_at_joint` stub:

```python
    def _at_joint(
        self,
        *,
        age_1: pl.Expr | None,
        age_2: pl.Expr | None,
        **other: pl.Expr,
    ) -> pl.Expr:
        if age_1 is None or age_2 is None:
            msg = "structure='joint' requires both age_1=... and age_2=..."
            raise ValueError(msg)
        return self.table.lookup(age_1=age_1, age_2=age_2, **other)
```

Also update the public `at(...)` method to reject the single-age `age=` kwarg when structure is joint:

```python
        if self.structure == "joint":
            if age is not None:
                msg = (
                    "structure='joint' uses age_1=... and age_2=..., not age=..."
                )
                raise ValueError(msg)
            return self._at_joint(age_1=age_1, age_2=age_2, **other)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_at_joint.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/_mortality_table.py bindings/python/tests/mortality/test_at_joint.py
git commit -m "feat(mortality): add joint-life dispatch (age_1, age_2)"
```

---

### Task 6: Canonical form + `source_sha()`

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/_mortality_table.py`
- Create: `bindings/python/tests/mortality/test_canonical.py`

- [ ] **Step 1: Write the failing test**

```python
# bindings/python/tests/mortality/test_canonical.py
"""MortalityTable canonical-form + source_sha tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.mortality._mortality_table import MortalityTable


class TestCanonicalForm:
    def test_aggregate_canonical_shape(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        cf = m.canonical_form()
        assert cf == {
            "kind": "MortalityTable",
            "table_name": "cso_2017_male_aggregate",
            "table_dimensions": ["age"],
            "age_basis": "age_last_birthday",
            "structure": "aggregate",
            "select_period": None,
        }

    def test_select_ultimate_canonical_shape(
        self, select_ultimate_table: Table,
    ) -> None:
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        cf = m.canonical_form()
        assert cf == {
            "kind": "MortalityTable",
            "table_name": "select_ultimate_demo",
            "table_dimensions": ["age", "duration"],
            "age_basis": "age_last_birthday",
            "structure": "select_ultimate",
            "select_period": 10,
        }

    def test_canonical_dimensions_are_sorted(self, joint_life_table: Table) -> None:
        # Dimensions list is sorted alphabetically for determinism
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        cf = m.canonical_form()
        assert cf["table_dimensions"] == ["age_1", "age_2"]


class TestSourceSha:
    def test_identical_mortality_tables_have_identical_sha(
        self, aggregate_table: Table,
    ) -> None:
        a = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        b = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        assert a.source_sha() == b.source_sha()

    def test_different_age_basis_changes_sha(self, aggregate_table: Table) -> None:
        a = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        b = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        assert a.source_sha() != b.source_sha()

    def test_different_select_period_changes_sha(
        self, select_ultimate_table: Table,
    ) -> None:
        a = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        b = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=15,
        )
        assert a.source_sha() != b.source_sha()

    def test_different_table_name_changes_sha(self) -> None:
        import polars as pl
        df = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t1 = Table(name="cso_2017_male", source=df, dimensions={"age": "age"}, value="qx")
        t2 = Table(name="cso_2017_female", source=df, dimensions={"age": "age"}, value="qx")
        a = MortalityTable(
            table=t1, age_basis="age_last_birthday", structure="aggregate",
        )
        b = MortalityTable(
            table=t2, age_basis="age_last_birthday", structure="aggregate",
        )
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self, aggregate_table: Table) -> None:
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        sha = m.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_canonical.py -v`
Expected: FAIL — `AttributeError: 'MortalityTable' object has no attribute 'canonical_form'`.

- [ ] **Step 3: Implement**

Append to `MortalityTable`:

```python
    def canonical_form(self) -> dict[str, object]:
        """Return the JSON-encodable canonical form of this MortalityTable.

        Includes the underlying Table's name and sorted dimension list, plus
        the mortality-specific metadata. Two MortalityTables differing only
        in age_basis, structure, or select_period produce different forms
        and therefore different ``source_sha()`` values.
        """
        return {
            "kind": "MortalityTable",
            "table_name": self.table.name,
            "table_dimensions": sorted(self.table.dimensions.keys()),
            "age_basis": self.age_basis,
            "structure": self.structure,
            "select_period": self.select_period,
        }

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        Note: Phase 1 ``source_sha`` does NOT hash the underlying Table's
        data payload (file content / DataFrame rows). Two runs with the same
        Table.name but different file contents produce identical SHAs in
        Phase 1 — close this gap by either (a) supplying distinct Table
        names per data revision, or (b) waiting for Phase 2's Table-side
        ``content_sha()`` work.
        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_canonical.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/_mortality_table.py bindings/python/tests/mortality/test_canonical.py
git commit -m "feat(mortality): add canonical_form + source_sha"
```

---

### Task 7: Public API exposure

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/__init__.py`
- Modify: `bindings/python/gaspatchio_core/__init__.py`
- Modify: `bindings/python/tests/mortality/test_construction.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/mortality/test_construction.py`:

```python
class TestPublicAPI:
    def test_mortality_table_importable_from_subpackage(self) -> None:
        from gaspatchio_core.mortality import MortalityTable
        from gaspatchio_core.mortality._mortality_table import MortalityTable as Private
        assert MortalityTable is Private

    def test_top_level_import(self) -> None:
        import gaspatchio_core
        assert hasattr(gaspatchio_core, "MortalityTable")

    def test_top_level___all___includes_mortality_table(self) -> None:
        import gaspatchio_core
        assert "MortalityTable" in gaspatchio_core.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd bindings/python && uv run pytest tests/mortality/test_construction.py::TestPublicAPI -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Update mortality package __init__**

Replace `gaspatchio_core/mortality/__init__.py`:

```python
"""Typed mortality wrapper — MortalityTable.

A thin actuarial-convention wrapper over
:class:`gaspatchio_core.assumptions.Table`. Phase 1 typed input for the
rollforward redesign; the existing untyped Table continues to work for
non-mortality assumptions (lapse, expense, surrender charges).
"""

from __future__ import annotations

from gaspatchio_core.mortality._conventions import AgeBasis, Structure
from gaspatchio_core.mortality._mortality_table import MortalityTable

__all__ = ["AgeBasis", "MortalityTable", "Structure"]
```

- [ ] **Step 4: Wire into top-level**

In `bindings/python/gaspatchio_core/__init__.py`, add:

```python
from .mortality import MortalityTable
```

Add `"MortalityTable"` to the `__all__` list.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd bindings/python && uv run pytest tests/mortality/test_construction.py::TestPublicAPI -v`
Expected: PASS — 3 tests.

- [ ] **Step 6: Verify the full test suite still imports**

Run: `cd bindings/python && uv run pytest tests/ -x --co -q 2>&1 | tail -20`
Expected: collection succeeds with no `ImportError`.

- [ ] **Step 7: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/__init__.py bindings/python/gaspatchio_core/__init__.py bindings/python/tests/mortality/test_construction.py
git commit -m "feat(mortality): wire MortalityTable into public API"
```

---

### Task 8: Polars integration smoke test (UL with COI scenario)

**Files:**
- Create: `bindings/python/tests/mortality/test_polars_integration.py`

- [ ] **Step 1: Write the smoke test**

```python
# bindings/python/tests/mortality/test_polars_integration.py
"""End-to-end smoke — MortalityTable in a Universal-Life-style pipeline.

Mirrors the spec §4.5 worked example shape:
    coi = mortality.at(age=af.attained_age) * (death_benefit - av)
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import MortalityTable
from gaspatchio_core.assumptions import Table


class TestUlWithCoiPattern:
    def test_aggregate_lookup_in_with_columns_pipeline(
        self, aggregate_table: Table,
    ) -> None:
        mortality = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "attained_age": [40, 50, 60],
                "av": [10_000.0, 25_000.0, 50_000.0],
                "death_benefit": [100_000.0, 100_000.0, 100_000.0],
            }
        )
        result = (
            df
            .with_columns(qx=mortality.at(age=pl.col("attained_age")))
            .with_columns(coi=pl.col("qx") * (pl.col("death_benefit") - pl.col("av")))
        )
        # qx: age 40 -> 0.002, age 50 -> 0.005, age 60 -> 0.013
        # coi:   0.002 * 90_000 = 180.0
        #        0.005 * 75_000 = 375.0
        #        0.013 * 50_000 = 650.0
        assert result.get_column("qx").to_list() == pytest.approx([0.002, 0.005, 0.013])
        assert result.get_column("coi").to_list() == pytest.approx([180.0, 375.0, 650.0])

    def test_select_ultimate_in_with_columns_pipeline(
        self, select_ultimate_table: Table,
    ) -> None:
        mortality = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        df = pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "age": [30, 40, 50],
                "policy_year": [1, 6, 100],   # Y1 select, Y6 + Y100 -> clamped
            }
        )
        result = df.with_columns(
            qx=mortality.at(age=pl.col("age"), duration=pl.col("policy_year")),
        )
        # Age 30, policy_year 1: select rate = 0.001 * 30 * 1.1 = 0.033
        # Age 40, policy_year 6: clamped to 5 -> 0.001 * 40 * 1.5 = 0.060
        # Age 50, policy_year 100: clamped to 5 -> 0.001 * 50 * 1.5 = 0.075
        assert result.get_column("qx").to_list() == pytest.approx([0.033, 0.060, 0.075])
```

- [ ] **Step 2: Run smoke test**

Run: `cd bindings/python && uv run pytest tests/mortality/test_polars_integration.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/mortality/test_polars_integration.py
git commit -m "test(mortality): UL+COI Polars-pipeline smoke test"
```

---

### Task 9: pyi stubs

**Files:**
- Modify: `bindings/python/gaspatchio_core/mortality/__init__.pyi`

- [ ] **Step 1: Write the stubs**

Replace `bindings/python/gaspatchio_core/mortality/__init__.pyi`:

```python
"""Type stubs for gaspatchio_core.mortality."""

from __future__ import annotations

from typing import Literal

import polars as pl

from gaspatchio_core.assumptions import Table

AgeBasis = Literal["age_last_birthday", "age_nearest_birthday"]
Structure = Literal["aggregate", "select_ultimate", "joint"]

class MortalityTable:
    table: Table
    age_basis: AgeBasis
    structure: Structure
    select_period: int | None

    def __init__(
        self,
        *,
        table: Table,
        age_basis: AgeBasis,
        structure: Structure,
        select_period: int | None = ...,
    ) -> None: ...
    def at(
        self,
        *,
        age: pl.Expr | None = ...,
        age_1: pl.Expr | None = ...,
        age_2: pl.Expr | None = ...,
        duration: pl.Expr | None = ...,
        age_basis: AgeBasis | None = ...,
        **other: pl.Expr,
    ) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, object]: ...
    def source_sha(self) -> str: ...

__all__ = ["AgeBasis", "MortalityTable", "Structure"]
```

- [ ] **Step 2: Verify stubtest is clean**

Run: `cd bindings/python && uv run python -m mypy.stubtest gaspatchio_core.mortality --allowlist stubtest-allowlist.txt 2>&1 | tail -20`
Expected: zero errors. If errors appear, fix the stub inline.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/mortality/__init__.pyi
git commit -m "feat(mortality): full pyi stubs for MortalityTable public surface"
```

---

### Task 10: Lint + format + type check + final pass

**Files:**
- (verification-only)

- [ ] **Step 1: Lint clean**

Run: `cd bindings/python && uv run ruff check gaspatchio_core/mortality tests/mortality`
Expected: no errors.

- [ ] **Step 2: Format check**

Run: `cd bindings/python && uv run ruff format --check gaspatchio_core/mortality tests/mortality`
Expected: no diffs.

- [ ] **Step 3: Type check**

Run: `cd bindings/python && uv run mypy gaspatchio_core/mortality 2>&1 | tail -20`
Expected: zero errors.

- [ ] **Step 4: Full mortality test suite**

Run: `cd bindings/python && uv run pytest tests/mortality -v`
Expected: PASS — ~30 tests across 7 test files.

- [ ] **Step 5: Verify rest of repo is green**

Run: `cd bindings/python && uv run pytest tests/ -q 2>&1 | tail -5`
Expected: prior pass-count plus new mortality tests; no regressions.

- [ ] **Step 6: Commit any cleanup**

```bash
git add bindings/python/gaspatchio_core/mortality
git commit -m "chore(mortality): lint + format + type-check fixups"
```

If nothing changed, skip.

---

### Task 11: README + spec status update

**Files:**
- Modify: `ref/36-rollforward-redesign/README.md`

- [ ] **Step 1: Update sub-plan README**

Update the implementation status block:

```markdown
## Implementation status

- **Phase 1a Sub-plan A — Typed Time** (Schedule + Calendar + DayCount): ✅ shipped
- **Phase 1a Sub-plan B — Curve**: ✅ shipped
- **Phase 1a Sub-plan C — MortalityTable**: ✅ shipped (this branch)
- **Phase 1a Sub-plan D — State-machine kernel**: not started

Plans:
- [`plans/2026-05-04-phase-1a-schedule.md`](plans/2026-05-04-phase-1a-schedule.md)
- [`plans/2026-05-04-phase-1a-curve.md`](plans/2026-05-04-phase-1a-curve.md)
- [`plans/2026-05-04-phase-1a-mortality.md`](plans/2026-05-04-phase-1a-mortality.md)
```

- [ ] **Step 2: Commit**

```bash
git add ref/36-rollforward-redesign/README.md
git commit -m "docs(rollforward-redesign): mark Sub-plan C (MortalityTable) shipped"
```

---

## Self-review

**Spec coverage check:**
- §4.15 thin wrapper over existing Table: tasks 1–7 ✓
- §4.15 `age_basis` ("age_last_birthday" | "age_nearest_birthday"): task 2 ✓
- §4.15 `structure` ("aggregate" | "select_ultimate" | "joint"): tasks 3, 4, 5 ✓
- §4.15 `select_period` (Phase 1 — open question §14.1 resolved here as Phase 1 with duration-clamping): task 4 ✓
- §4.15 convention-aware `at(...)`: tasks 3, 4, 5 ✓
- §4.15 `at(age_basis="...")` accepted but no conversion (deferred): task 3 ✓
- §13.1a `source_sha()` method: task 6 ✓
- §13.1a public-API exposure: task 7 ✓
- §14.1 open question on `select_period` resolved: select_period IS Phase 1 (with documented clamping behavior) ✓

**Placeholder scan:**
- No "TBD", "implement later", "fill in details" anywhere.
- All step-3 implementations show actual code.
- All test code is concrete.

**Type consistency:**
- `MortalityTable` references consistent across all tasks.
- `age_basis: AgeBasis`, `structure: Structure`, `select_period: int | None` — same field names everywhere.
- `.at(age=, age_1=, age_2=, duration=, age_basis=, **other)` signature consistent across tasks 3–5 and pyi stub.
- Helper-method names (`_at_select_ultimate`, `_at_joint`) consistent.

**Cross-plan consistency check:**
- `source_sha()` returns the same `"sha256:<hex>"` string format as Plans A and B ✓
- `canonical_form()` reuses Plan A's `canonical_bytes()` helper ✓
- Frozen-dataclass + `__post_init__`-validation pattern matches Plans A and B ✓
- Public-API exposure pattern matches Plans A and B ✓
- Reuses `Table.name` (added as a small additive Task-1 change) — no private-attribute reads ✓

**Risks I've flagged inline:**
- Task 6's `source_sha()` does NOT hash the underlying Table's data payload (only `Table.name`). Two `Table`s with the same name but different file contents produce identical MortalityTable SHAs in Phase 1. Documented in the docstring; close in Phase 2 by adding a `content_sha()` to `Table`.
- Task 4's `select_ultimate` clamps duration at `select_period`; this assumes the underlying Table is organised so `(age, duration=select_period)` is the ultimate rate. Production CSO 2017 / SOA tables typically follow this convention but custom tables may not. Documented as a Phase 1 simplification.
- The `with_age_basis(...)` table-conversion utility is explicitly out-of-scope (Phase 2). Phase 1's `at(age_basis="...")` validates the supplied basis matches the table's basis but does NOT convert.

---

## Execution handoff

Plan complete and saved to `ref/36-rollforward-redesign/plans/2026-05-04-phase-1a-mortality.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks. Each task is small (3–7 steps, ~15–40 lines of new production code).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

This plan is meant to be drafted alongside Plan D before any execution begins. Execution sequencing: A first (foundation), then B and C in parallel (independent of each other and of D-prep), then D (depends on A).
