# Mortality Tables (`MortalityTable`)

`MortalityTable` is the typed mortality primitive in gaspatchio. It wraps a
`gaspatchio_core.assumptions.Table` and adds three actuarial-convention fields —
`age_basis`, `structure`, and `select_period` — that the underlying `Table` does not
carry. Its `.at()` method routes calls through structure-aware dispatch, handling the
select-period clamp automatically.

Use `MortalityTable` whenever the table has an age-basis convention or a select/ultimate
structure. For flat dimensional tables (lapse rates, expense loadings, policyholder
benefit rates) with no age-basis semantics, use `Table.lookup` directly.

---

## Import

```python
from gaspatchio_core import MortalityTable
from gaspatchio_core.assumptions import Table, TableBuilder
```

`MortalityTable` is exported from the top-level package; the underlying `Table` is
imported from `gaspatchio_core.assumptions`.

---

## Construction

```python
MortalityTable(
    table=<Table>,            # gaspatchio_core.assumptions.Table
    age_basis=<AgeBasis>,     # "age_last_birthday" | "age_nearest_birthday"
    structure=<Structure>,    # "aggregate" | "select_ultimate" | "joint"
    select_period=<int|None>, # required for "select_ultimate"; omit/None otherwise
)
```

`MortalityTable` is a frozen dataclass. Construction validates all four fields
immediately — a `ValueError` is raised if `structure="select_ultimate"` is used without
`select_period`, or if `select_period` is supplied with `"aggregate"` or `"joint"`.

### Age-basis literals

| Value | Meaning |
|---|---|
| `"age_last_birthday"` | Age at most recent birthday (ALB / curtate age) |
| `"age_nearest_birthday"` | Age at nearest birthday (ANB) |

The table stores whichever basis its underlying data uses. `.at()` validates that the
`age_basis` kwarg (if passed) matches — cross-basis conversion is not yet supported.

---

## The three structures

### 1. Aggregate (`structure="aggregate"`)

Age-only lookup. Used for valuation-basis tables that aggregate over duration — standard
annuity tables, population mortality, UN life tables.

```python
import polars as pl
from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.assumptions import Table

# Build the underlying Table (age-only dimension)
agg_df = pl.DataFrame({
    "age":  [30,   35,   40,   45,   50,   55,   60,   65,   70],
    "rate": [0.001,0.002,0.003,0.004,0.006,0.009,0.013,0.020,0.030],
})
agg_table = Table(
    name="annuity_a00",
    source=agg_df,
    dimensions={"age": "age"},
    value="rate",
)

m = MortalityTable(
    table=agg_table,
    age_basis="age_last_birthday",
    structure="aggregate",
    # select_period is omitted — aggregate has no select window
)

# Usage in a model:
af.qx = m.at(age=af["attained_age"])
```

`m.at(age=...)` accepts a `pl.Expr` or any `ColumnProxy` / `ExpressionProxy` from an
`ActuarialFrame`. Passing `duration=` raises `ValueError` with a clear message directing
you to use `"select_ultimate"` instead.

---

### 2. Select-ultimate (`structure="select_ultimate"`) — the headline structure

Select-ultimate tables grade from select rates (high during the first `select_period`
policy years) to ultimate rates (flat thereafter). The standard North American actuarial
presentation encodes this as a 2-D table indexed by `(age, duration)` where
`duration ∈ {1, 2, …, select_period}`.

**Key behaviour:** When `duration > select_period`, `MortalityTable` automatically
clamps the duration to `select_period` before the lookup, returning the ultimate rate.
Without this clamping you would need a hand-rolled `pl.Expr.clip(upper_bound=…)` at
every call site, and you risk silent wrong results if you forget it.

Verified behaviour (from `tests/mortality/test_at_select_ultimate.py`):
- `select_period=4`, policy in year 1: looks up the `duration=1` select rate
- `select_period=4`, policy in year 10: clamps to `duration=4`, returns the ultimate rate
- `select_period=4`, policy in year 25: same clamp to `duration=4`

```python
import polars as pl
from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.assumptions import TableBuilder

# Build the underlying Table
# Column "select_dur" is the select-period duration (1..SELECT_PERIOD)
# In source data, durations beyond select_period are NOT stored — clamping handles that.
SELECT_PERIOD = 5
import itertools

ages = list(range(20, 71))
durations = list(range(1, SELECT_PERIOD + 1))
rows = [
    {
        "age": age,
        "select_dur": dur,
        "rate": round(0.001 * age * (1.0 + 0.05 * dur), 6),
    }
    for age, dur in itertools.product(ages, durations)
]
vbt_df = pl.DataFrame(rows)

vbt_table = Table(
    name="vbt_2021_alu",
    source=vbt_df,
    dimensions={"age": "age", "duration": "select_dur"},
    value="rate",
)

m = MortalityTable(
    table=vbt_table,
    age_basis="age_last_birthday",
    structure="select_ultimate",
    select_period=SELECT_PERIOD,
)

# In a model — duration is a list column after create_projection_timeline:
af.qx = m.at(age=af["attained_age"], duration=af["duration"])
```

`MortalityTable` resolves ColumnProxy / ExpressionProxy to `pl.Expr` internally before
building the clip expression. List-typed duration columns (post-timeline) use the
`list_clip` Rust plugin; scalar `pl.Expr` inputs use `pl.Expr.clip(upper_bound=…)`.
Either path then routes through `Table.lookup` which calls the Rust plugin
(`lookup_by_table_and_hash`, `is_elementwise=True`) — **not** `map_elements**. This
is the same vectorized path used by all other `Table.lookup` calls.

**Both ages required:** `m.at(age=…)` alone raises `ValueError`; so does
`m.at(duration=…)` alone.

---

### 3. Joint-life (`structure="joint"`) — teach lightly

Joint-life tables index on two ages (`age_1`, `age_2`) and are used for last-survivor
or joint-life products. The underlying `Table` must have two age-dimension columns.

```python
import polars as pl
from gaspatchio_core import MortalityTable
from gaspatchio_core.assumptions import Table

# Joint table: rate is a function of both lives' ages
pairs = [
    (60, 60), (60, 65), (65, 60), (65, 65),
    (65, 70), (70, 65), (70, 70),
]
joint_df = pl.DataFrame({
    "age_1": [p[0] for p in pairs],
    "age_2": [p[1] for p in pairs],
    "rate":  [round(0.0001 * p[0] * p[1], 6) for p in pairs],
})
joint_table = Table(
    name="joint_life_ls",
    source=joint_df,
    dimensions={"age_1": "age_1", "age_2": "age_2"},
    value="rate",
)

m = MortalityTable(
    table=joint_table,
    age_basis="age_last_birthday",
    structure="joint",
    # select_period omitted — joint has no select window
)

# Usage:
qx_joint = m.at(age_1=af["age_life_1"], age_2=af["age_life_2"])
```

Passing `age=` to a joint table raises `ValueError`; both `age_1=` and `age_2=` are
required.

---

## `.at()` full signature

```python
m.at(
    *,                              # keyword-only
    age: pl.Expr | None = None,     # aggregate + select_ultimate
    age_1: pl.Expr | None = None,   # joint
    age_2: pl.Expr | None = None,   # joint
    duration: pl.Expr | None = None,# select_ultimate
    age_basis: AgeBasis | None = None,  # validation only — must match m.age_basis
    **other: pl.Expr,               # extra dimensions on the underlying Table
) -> pl.Expr
```

`**other` passes additional dimensions through to `Table.lookup` unchanged. Use this
when the underlying `Table` has extra dimensions such as `sex`, `smoker_status`, or
`risk_class`:

```python
m_gender = MortalityTable(
    table=Table(
        name="vbt_by_sex",
        source=vbt_sex_df,
        dimensions={"age": "age", "duration": "duration", "sex": "sex"},
        value="rate",
    ),
    age_basis="age_last_birthday",
    structure="select_ultimate",
    select_period=5,
)

af.qx = m_gender.at(
    age=af["attained_age"],
    duration=af["duration"],
    sex=af["sex"],        # extra dimension — passed through to Table.lookup
)
```

---

## When to use `MortalityTable` vs `Table.lookup`

| Situation | Use |
|---|---|
| Table has `(age, duration)` with a select/ultimate structure | `MortalityTable(structure="select_ultimate", select_period=N)` |
| Age-basis is contractually significant (ALB vs ANB) | `MortalityTable` — documents the basis, validates overrides |
| Table is a joint-life probability indexed on two ages | `MortalityTable(structure="joint")` |
| Flat lapse rates, expense factors, benefit amounts (no age-basis semantics) | `Table.lookup` directly |
| Interest rate term structures | `Curve.discount_factor` (not a Table at all) |
| Programmatic construction with many slices | `TableBuilder` → `Table` → then optionally `MortalityTable` |

`Table.lookup` is the low-level building block. `MortalityTable` is the
convention-aware wrapper. For mortality specifically, prefer `MortalityTable` over
bare `Table.lookup` because it:

1. Carries the age basis so future scenario re-wrapping validates automatically.
2. Clamps duration at `select_period` without boilerplate at every call site.
3. Provides a `source_sha()` for audit fingerprinting (see below).

---

## Audit fingerprinting

`MortalityTable.source_sha()` returns a `"sha256:<hex>"` string over the table's
canonical form (name, dimensions, age_basis, structure, select_period). Use it for
model audit trails or caching:

```python
fingerprint = m.source_sha()
# "sha256:4a7f..." — changes if table name, dimensions, age_basis, structure,
#                    or select_period change.
```

Note: The SHA does **not** hash the underlying data rows. Use distinct `Table.name`
values per data revision to distinguish different data loads.

---

## Using `MortalityTable` with scenarios

`model-scenarios` re-wraps the shocked `Table` back into a `MortalityTable` inside the
`model_fn` bridge so that the mortality metadata (age_basis, structure, select_period) is
preserved across scenario runs:

```python
# Excerpt from model-scenarios pattern — see model-scenarios/SKILL.md
def model_fn(af, *, tables, drivers):
    overrides = dict(base_assumptions)
    if "mortality_select" in tables:
        overrides["mortality"] = MortalityTable(
            table=tables["mortality_select"],   # shocked Table from ScenarioRun
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=SELECT_PERIOD,
        )
    return model.main(af, assumptions_override=overrides)
```

The `table=` argument is replaced with the scenario-stacked `Table`; all other
`MortalityTable` metadata stays the same. `model.main` receives a fully typed
`MortalityTable` and calls `.at()` unchanged — no modification to the model file.

To unwrap a `MortalityTable` to its underlying `Table` (e.g., when stacking scenarios):

```python
raw_table = m_mortality.table   # the .table attribute
# or defensively:
raw_table = m_mortality.table if isinstance(m_mortality, MortalityTable) else m_mortality
```

---

## Common mistakes

| Mistake | What goes wrong | Fix |
|---|---|---|
| Passing `select_period=4` with `structure="aggregate"` | `ValueError` at construction | Omit `select_period` for aggregate |
| Omitting `select_period` with `structure="select_ultimate"` | `ValueError` at construction | Add `select_period=<N>` |
| Calling `m.at(age=…)` on a select-ultimate table without `duration=` | `ValueError` | Supply both `age=` and `duration=` |
| Calling `m.at(duration=…)` without `age=` | `ValueError` | Supply both |
| Calling `m.at(age=…)` on a joint table | `ValueError` | Use `age_1=` and `age_2=` |
| Guessing the `select_period` from data shape | Silent wrong results at duration > actual period | `uv run gspio describe <file>.parquet` then count duration values |
| Supplying mismatched `age_basis` override | `ValueError: cross-basis conversion not yet supported` | Use the same basis as the table's data, or convert the data beforehand |
