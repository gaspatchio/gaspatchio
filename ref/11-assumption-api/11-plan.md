## Gaspatchio-Core ― Assumption Loading & Lookup Revamp

**Product / Technical Specification (v 1.0-draft)**
**Date:** 2025-05-23  **Author:** *Gaspatchio team*

---

### 0 · Purpose

Provide a **single, intuitive entry-point** for reading actuarial assumption tables (curves *and* wide age × duration grids) and a robust lookup that:

* can be discovered and emitted by LLMs with minimal context,
* hides all data-wrangling boiler-plate from actuaries,
* gracefully handles "overflow/ultimate/terminal" duration columns,
* remains backward-compatible with existing `register_table()` + `assumption_lookup()` code.

---

## 1 · Glossary

| Term                | Meaning                                                                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Curve**           | 1-D table: one or more key columns + exactly one numeric value column (e.g. `Age → Lapse Rate`).                                                                                  |
| **Wide rate table** | Age in rows, multiple duration columns (1…N + an optional overflow column).                                                                                                       |
| **Overflow column** | A single header that is *not* an integer and acts as the rate for all durations beyond the largest explicitly numbered column. May be `"Ult."`, `"Ultimate"`, `"999"`, `""`, etc. |

---

## 2 · Public API Changes

### 2.1 · Current API (what exists today)
```py
from gaspatchio_core.registry import TableRegistry
from gaspatchio_core.assumptions import assumption_lookup  # WILL BE REMOVED

# Current workflow - verbose and LLM-unfriendly
registry = TableRegistry()
registry.register_table(name="mort_table", df=processed_df, keys=["age"], value_column="qx")
result = assumption_lookup("age", table_name="mort_table")
```

### 2.2 · New API (what we're adding)
```py
import gaspatchio_core as gs

# ──────────────────────────────────────────────────────────────────────────────
gs.load_assumptions(name, source, *,
                    id=None,
                    value="rate",
                    overflow="auto",
                    max_overflow=200,
                    metadata=None)

gs.assumption_lookup(table_name, **key_values)

gs.read_csv(path, **kw)  → ActuarialFrame
gs.ActuarialFrame
```

**Key Changes:**
- **NEW**: `gs.load_assumptions()` - replaces the verbose `TableRegistry().register_table()` workflow
- **BREAKING**: `gs.assumption_lookup()` - ONLY available at top-level, deep import `from gaspatchio_core.assumptions import assumption_lookup` **REMOVED**
- **UNCHANGED**: `gs.ActuarialFrame` and `gs.read_csv()` - already top-level exports

**Migration Required:**
```python
# OLD (will break)
from gaspatchio_core.assumptions import assumption_lookup

# NEW (required)
import gaspatchio_core as gs
result = gs.assumption_lookup(...)
```

These four symbols will be re-exported by `gaspatchio_core.__init__`.

### 2.1 · `load_assumptions()`

| Parameter      | Type              | Req'd          | Description                                               |
| -------------- | ----------------- | -------------- | --------------------------------------------------------- |
| `name`         | `str`             | ✔              | Registry key (must be unique).                            |
| `source`       | \`str             | pl.DataFrame\` | ✔                                                         | CSV/Parquet path **or** in-memory Polars DataFrame.                                            |
| `id`           | \`str             | list\[str]     | None\`                                                    | Key columns. Comma-separated string or list. If `None`, auto-detect first non-numeric column(s). |
| `value`        | `str`             | ·              | Name of numeric column in tidy output (default `"rate"`). |
| `value_vars`   | \`list\[str]      | None\`         | ·                                                         | Columns to melt into long format. If `None`, auto-detect all numeric columns. For selective melting of wide tables. |
| `overflow`     | \`"auto"          | str            | None\`                                                    | `"auto"` → detect one textual column; `str` → explicit label; `None` → disable overflow logic. |
| `max_overflow` | `int`             | ·              | Maximum value for overflow expansion (default `200`).    |
| `metadata`     | \`dict\[str, Any] | None\`         | ·                                                         | Optional JSON persisted with the table.                                                        |

**Return** `pl.DataFrame` in tidy form
*(facilitates immediate `.head()` calls in notebooks).*

---

### 2.2 · `assumption_lookup()`

Unchanged signature and implementation. Overflow handling is now transparent via pre-expanded lookup tables (see § 4.3).

---

## 3 · User Workflows

### 3.1 · Loading a wide mortality table (ultimate column auto-detected)

```python
gs.load_assumptions(
    "mortality_vbt_2015_f_ns",
    "2015-VBT-FNS.csv",
    id="Age",              # column A
    value="qx",            # actuarial notation for mortality rate
    max_overflow=120       # expand overflow up to duration 120
)   # overflow="auto" by default → finds "Ult."
```

### 3.2 · Loading a lapse curve (no overflow)

```python
gs.load_assumptions(
    "lapse_2025",
    "lapse_curve.csv",
    id="age",
    value="lx",
    overflow=None          # explicitly disable
)
```

### 3.2a · Loading a salary scale table (non-duration overflow)

```python
gs.load_assumptions(
    "salary_scale_2025",
    "salary_by_service_years.csv", 
    id="grade",
    value="scale_factor",
    overflow="auto",       # detects "20+" column for service years 20+
    max_overflow=50        # expand up to 50 service years
)
```

### 3.2b · Loading a mortality table with selective columns

```python
# Mortality table with gender/smoking combinations
gs.load_assumptions(
    "mortality_vbt_2015",
    "mortality.parquet",
    id="age-last",
    value="mortality_rate",
    value_vars=["MNS", "FNS", "MS", "FS"],  # Only melt these 4 columns
    overflow=None          # No overflow for this table
)
```

**Input DataFrame:**
```
age-last │ MNS          │ FNS          │ MS           │ FS           
─────────┼──────────────┼──────────────┼──────────────┼──────────────
1        │ 0.000100000  │ 0.000097000  │ 0.000120000  │ 0.000116400  
2        │ 0.000100000  │ 0.000097000  │ 0.000120000  │ 0.000116400  
3        │ 0.000100000  │ 0.000097000  │ 0.000120000  │ 0.000116400  
```

**Output (Tidy) DataFrame:**
```
age-last │ variable │ mortality_rate 
─────────┼──────────┼────────────────
1        │ MNS      │ 0.000100000    
1        │ FNS      │ 0.000097000    
1        │ MS       │ 0.000120000    
1        │ FS       │ 0.000116400    
2        │ MNS      │ 0.000100000    
2        │ FNS      │ 0.000097000    
2        │ MS       │ 0.000120000    
2        │ FS       │ 0.000116400    
```

*Replaces complex `WideToLongTransformSpec` with simple parameter. Variable column name defaults to `"variable"` but can be customized via melting logic.*

### 3.3 · Lookup inside a projection

```python
df["qx"] = gs.assumption_lookup("mortality_vbt_2015_f_ns",
                                Age=df["age_last"],
                                duration=df["duration"])

df["lx"] = gs.assumption_lookup("lapse_2025", age=df["age_last"])
```

*If `duration` > 25 the mortality lookup uses the pre-expanded overflow entries (duration 26, 27, ... 120 all map to "Ult." rates).*

---

## 4 · Internal Design

### 4.1 · Directory layout

```
bindings/python/gaspatchio_core/
│
├─ __init__.py          # NEEDS UPDATE - add load_assumptions to re-exports
│
├─ assumptions.py       # EXISTING - contains assumption_lookup() Polars plugin binding (UNCHANGED)
├─ registry.py          # EXISTING - contains TableRegistry class with register_table() (UNCHANGED)
│
├─ assumptions/         # NEW PACKAGE - assumption loading & preprocessing logic
│   ├─ _loader.py       # NEW - load_assumptions() + all overflow expansion logic
│   └─ __init__.py      # re-exports load_assumptions (from _loader) + assumption_lookup (from ../assumptions.py)
│
└─ frame/
    └─ base.py          # EXISTING - contains ActuarialFrame class (UNCHANGED)
```

**File Responsibilities:**

| File | Responsibility | Status |
|------|---------------|--------|
| `__init__.py` | **Public API** - Re-export `load_assumptions` from `assumptions` package | **NEEDS UPDATE** |
| `assumptions.py` | **Lookup engine** - Contains `assumption_lookup()` Polars plugin for O(1) hash-based lookups | **UNCHANGED** |
| `registry.py` | **Table storage** - Contains `TableRegistry` class with `register_table()` method, wraps Rust registry | **UNCHANGED** |
| `frame/base.py` | **ActuarialFrame** - Main data structure, already exports `ActuarialFrame` and `read_csv()` | **UNCHANGED** |
| `assumptions/_loader.py` | **Data ingestion** - Contains `load_assumptions()` with CSV/DataFrame parsing, curve vs. wide detection, overflow expansion | **NEW** |
| `assumptions/__init__.py` | **Package API** - Re-exports `load_assumptions` + `assumption_lookup` for top-level access only | **NEW** |

**Required Changes:**

1. **`gaspatchio_core/__init__.py`** - Update imports:
   ```python
   from .assumptions import load_assumptions, assumption_lookup  # NEW: both from assumptions package
   ```

2. **`gaspatchio_core/assumptions.py`** - Remove `assumption_lookup` export (becomes internal-only)

3. **No changes needed** to `frame/base.py` or `registry.py`

**Integration Strategy:**
- `load_assumptions()` (new) processes raw data → calls `TableRegistry().register_table()` from existing `registry.py` → stores in existing Rust registry
- `assumption_lookup()` (existing) remains unchanged, reads from same Rust registry with zero performance impact
- **No breaking changes** - existing `TableRegistry().register_table()` + `assumption_lookup()` workflows continue to work
- New workflow: `load_assumptions()` → `assumption_lookup()` provides simplified end-to-end experience

### 4.2 · `_loader.py` (key functions)

```python
def load_assumptions(name, source, *, id=None, value="rate",
                     value_vars=None, overflow="auto", max_overflow=200, metadata=None):
    df = _materialise(source)                     # path → DataFrame

    id_cols, wide_cols = _analyse_shape(df, id)   # curve vs. wide

    if wide_cols:                                 # ── wide ──
        tidy = _tidy_wide_with_overflow_expansion(
            df, id_cols, wide_cols, value, value_vars, overflow, max_overflow
        )
    else:                                         # ── curve ──
        tidy = _tidy_curve(df, id_cols, value)

    # Import and use existing registry
    from gaspatchio_core.registry import TableRegistry
    registry = TableRegistry()
    
    registry.register_table(                      # existing API
        name=name,
        df=tidy,
        keys=id_cols + (["variable"] if wide_cols else []),
        value_column=value,
        # Note: metadata would need to be added to TableRegistry.register_table()
        # or handled separately if not yet supported
    )
    return tidy
```

#### Helper responsibilities

| Function                              | Tasks                                                                                                                                                                           |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_materialise`                        | `str` → `pl.read_csv/parquet`; else return DataFrame.                                                                                                                           |
| `_analyse_shape`                      | Decide curve vs. wide; auto-detect `id` if needed.                                                                                                                              |
| `_tidy_curve`                         | Validate single numeric column; rename → `value`; return tidy DataFrame.                                                                                                        |
| `_tidy_wide_with_overflow_expansion`  | **Selective melting**: Use `value_vars` if specified, else auto-detect columns. Melt to long form + pre-compute all overflow mappings at registration time. Expands table with overflow entries for values 1→MAX_OVERFLOW (e.g., 200). |

#### Overflow Expansion Strategy

For wide tables with overflow columns, we **pay the cost once at registration**:

1. **Detect overflow column** (`"Ult."`, `"Ultimate"`, etc.)
2. **Find max numeric value** in headers (e.g., 25)
3. **Pre-expand table** with overflow entries for values 26→MAX_OVERFLOW
4. **Result**: Complete lookup table with no runtime overflow logic needed

```python
def _tidy_wide_with_overflow_expansion(df, id_cols, wide_cols, value, value_vars, overflow, max_overflow):
    # Use value_vars if specified, otherwise use detected wide_cols
    melt_cols = value_vars if value_vars is not None else wide_cols
    
    # Standard melt operation
    tidy = df.melt(
        id_vars=id_cols,
        value_vars=melt_cols,  # Only melt specified columns
        variable_name="variable",
        value_name=value
    )
    
    # Detect and expand overflow if present
    overflow_col = _detect_overflow_column(melt_cols, overflow)
    if overflow_col:
        max_numeric_value = max(int(col) for col in melt_cols if col.isdigit())
        overflow_rows = _create_overflow_expansion(
            df, id_cols, overflow_col, value, 
            start_value=max_numeric_value + 1,
            max_value=max_overflow
        )
        tidy = pl.concat([tidy, overflow_rows])
    
    return tidy.with_columns(pl.col("variable").cast(pl.String))
```

Edge-case errors raised as `ValueError` with actionable messages.

### 4.3 · `assumption_lookup` changes

**No changes required** to the lookup function! 

The hybrid approach eliminates all runtime overflow logic:

```python
def assumption_lookup(table_name, **keys):
    # Same as existing implementation - pure hash-based lookup
    return _join_on_keys(_registry[table_name], **keys)
```

Since overflow entries are pre-computed and stored in the expanded lookup table during registration:
- **Value 26** → looks up row with `key=26` (from overflow expansion)  
- **Value 150** → looks up row with `key=150` (from overflow expansion)
- **No runtime checks** or fallback logic needed
- **Maximum lookup speed** preserved via our existing hash-based joins

The table expansion happens once at `load_assumptions()` time, not every lookup.

---

## 5 · Docstring & LLM Guidelines

* Every **public** function must include **one doctest** that:

  1. Constructs a mini DataFrame (≤ 5 rows).
  2. Calls the helper exactly as in § 3.
  3. Prints `.head()` or scalar lookup.
* Use **comma-string syntax** (`id="Age, Sex"`) in examples for brevity.
* Keep line length ≤ 88 chars to fit editor hovers.

---

## 6 · Testing Requirements


```
bindings/python/tests/
│
├─ assumptions/
│   ├─ test_curve.py
│   ├─ test_wide_auto.py
│   ├─ test_wide_explicit.py
│   ├─ test_lookup_overflow.py
│   ├─ test_duplicates.py
│   └─ test_legacy.py
```

| ID      | Scenario                              | File                            |
| ------- | ------------------------------------- | ------------------------------- |
| **T-1** | Curve, auto id, overflow =None        | `assumptions/test_curve.py`           |
| **T-2** | Wide table, overflow ="auto"          | `assumptions/test_wide_auto.py`       |
| **T-3** | Wide table, explicit overflow ="Term" | `assumptions/test_wide_explicit.py`   |
| **T-4** | Lookup duration > max uses overflow   | `assumptions/test_lookup_overflow.py` |
| **T-5** | Duplicate name raises                 | `assumptions/test_duplicates.py`      |
| **T-6** | Legacy register\_table still works    | `assumptions/test_legacy.py`          |
| **T-7** | All doctests pass                     | `pytest --doctest-glob="*.py"`  |

CI matrix: Python 3.10-3.12 on Ubuntu & macOS.

---

## 7 · Performance

* **Loader cost**: `pl.read_csv` + `melt` + overflow expansion; ~150 ms per 1M cells on M1.
  - Expansion adds ~3x more rows for tables with overflow (e.g., 25 values → 200 values)
  - **One-time cost** at registration, amortized over millions of lookups
* **Memory footprint**: Larger tidy DataFrames due to expansion (~3-8x for wide tables)
  - Trade memory for maximum lookup speed 
  - Configurable `max_overflow` parameter to control expansion size
* **Lookup performance**: **Zero regression** - same hash-based joins as before
  - No runtime overflow checks or fallback logic
  - Scales linearly with lookup volume, not table complexity

---

## 8 · Rationale ("Why")

| Problem                                                  | Design choice                                                                                            |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Boiler-plate `melt()` / key lists scare actuaries & LLMs | **One verb** (`load_assumptions`) with forgiving defaults hides transform.                               |
| "Ultimate" labelled inconsistently                       | Generic **`overflow` kwarg** with `"auto"` detection covers 90% of sheets and allows explicit override. |
| LLMs struggle with deep import paths                     | **Top-level façade** (`gs.load_assumptions`) mimics `pl.read_csv`; completion lists reveal all helpers.  |
| Need to keep old code running                            | New helper delegates to **existing registry**; no refactor downstream.                                   |
| Future extensions (Excel, HTTP)                          | Loader takes **DataFrame or path**; materialiser can be extended without API change.                     |

---

## 9 · Open Items / Next Sprint

* Excel sheet selection (`sheet="Rates"`).
* CLI mirror (`gs tables import …`).
* Formal JSON schema for `metadata` (sex, smoker flag enums).
* On-disk Parquet cache for large tables.

---

### End of Document ✔️