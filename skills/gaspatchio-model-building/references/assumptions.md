# Assumption Tables

## Before You Start

Always analyze the assumption file first:

```bash
uv run gspio describe assumptions/mortality.parquet
```

This shows detected dimensions, value columns, sample data, and suggests Table configuration. Then look up the Table API:

```bash
uv run gspio docs "Table" -n 20
uv run gspio docs "TableBuilder" -t code_example
```

## Table API

### Basic Pattern

```python
from gaspatchio.assumptions import Table

mort = Table(
    name="mortality",
    source="assumptions/mortality.parquet",   # the file path, not a frame you read
    dimensions={"age": "age", "duration": "duration"},
    value="rate",
)

# Lookup returns a column matching the projection shape
af.mort_rate = mort.lookup(age=af.attained_age, duration=af.duration)
```

### Hand `Table` the file path

`gspio verify` holds the files you have against the audit file that records them — results,
policy data, the model file and every local module it imports, and each assumption table read
back from its file — and exits 0 only when every check asked for agrees; library versions and
git are evidence and move no exit status. Hand `Table` the file path (not a frame you built) so
`--assumptions` can decide it:

| How the table was built | `gspio verify … --assumptions DIR` against a file with other rates |
|---|---|
| `Table(source="assumptions/mortality.parquet", …)` | `✗ assumptions differs`, exit 1 — the table was a plain read of that file |
| `Table(source=pl.read_parquet(…).filter(…), …)` | `? assumptions could not be checked`, exit 4 — nothing records that the frame was the file as it stands |

A table built from a frame in code still verifies `agrees` against a file with the same
values, and `not asked` when no file is named for it. Keep a frame source for a table that
really is built in code — a grid computed in setup — and give everything read from a file its
path. Once `--assumptions` is given, every recorded table must be found among the files and
directories named (by the path recorded, `NAME.parquet`/`NAME.csv`, or `NAME=FILE`).

### Dimension Mapping

The `dimensions` dict maps **your dimension name** → **the source file's column name**:

```python
# Your model uses 'attained_age'; the CSV column is called 'Age'
dimensions={"attained_age": "Age", "policy_dur": "Duration"}

# Lookup uses YOUR dimension names
af.rate = table.lookup(attained_age=af.attained_age, policy_dur=af.duration)
```

### TableBuilder API

For complex or programmatically-constructed tables:

```python
from gaspatchio.assumptions import TableBuilder

mortality_table = (
    TableBuilder("mortality_vbt")
    .with_data_dimension("age", "age")
    .with_data_dimension("sex", "sex")
    .with_data_dimension("smoking_status", "smoking_status")
    .with_data_dimension("year", "year")
    .with_value_column("mortality_rate")
    .from_source(combined_data)
    .build()
)

af.cso_rate = mortality_table.lookup(
    age=af.age_mort_lookup,
    sex=af.sex,
    smoking_status=af.smoking_status,
    year=af.year_capped,
)
```

### Dimension Types

Look these up for your specific need:

```bash
uv run gspio docs "MeltDimension" -t code_example
uv run gspio docs "CategoricalDimension"
uv run gspio docs "ComputedDimension"
uv run gspio docs "ExtendOverflow"
```

| Type | Use Case |
|------|----------|
| `DataDimension` | Maps a column directly (default) |
| `MeltDimension` | Wide-to-long transform (e.g., columns `MNS`, `FNS`, `MS`, `FS` → `variable` dimension) |
| `CategoricalDimension` | Adds a constant value for all rows |
| `ComputedDimension` | Creates dimension from an expression |

The overflow strategy (`ExtendOverflow`) and the fill strategies (`FillForward`, `FillConstant`, `LinearInterpolate`) act on a `MeltDimension` when the table is built, not when it is looked up: `ExtendOverflow` copies a melted column such as `Ult.` to every later key up to `to_value`, and a fill strategy fills the empty cells of the melted grid. A lookup key the built table does not hold is still a miss, and is refused. `ExtendOverflow` copies a row's own value, so it is wrong for a select table keyed by issue age, whose `Ult.` column is the rate at attained age issue age + N: `gspio describe` suggests the select-and-ultimate reading for that layout.

### storage_mode Parameter

For large tables, the `storage_mode` parameter affects performance:

```python
table = Table(
    name="big_table",
    source=df,
    dimensions={...},
    value="rate",
    storage_mode="auto",  # "auto" | "hash" | "array"
)
```

`"auto"` (default) selects the best mode based on dimension cardinality.

### Useful Table Methods

```python
table.describe()                    # Human-readable summary
table.dimension_values("age")       # List unique values in a dimension
table.validate_lookup(age=45)       # Validate dimensions without executing
table.with_shock(shock, name)       # Create a shocked copy
table.to_dataframe()                # Convert back to Polars DataFrame
table.fingerprint()                 # Content identity -- the hash the run record carries
table.source_sha()                  # Recipe identity -- name, dimensions, value + fingerprint
```

### Table identity: which hash is which

A `Table` carries two stamps, and they answer different questions.

| Stamp | Identifies | Moves when |
|-------|-----------|------------|
| `table.fingerprint()` | the **content** -- the values a lookup answers from | any value changes |
| `table.source_sha()` | the **table object** -- name, dimensions, value column and the fingerprint | values change, or the table is renamed or re-keyed |

`fingerprint()` is what the calculation graph records: the `fingerprint` of the table's
`assumptions` entry and the `table_fingerprint` on every lookup node, so it is the hash
`gspio diff` and the viewer compare, and it feeds the graph fingerprint `gspio verify`
checks. It is taken over
the table in canonical form (keys by name, value column last, rows sorted), so reordering
the source's columns or rows, or re-saving parquet as CSV, does not move it; a changed rate
does. Use it to check "is this the basis the run used?". Use `source_sha()` to pin the
whole configured table, name included.

```python
mort = Table(name="mortality", source="assumptions/mortality.parquet",
             dimensions={"age": "age"}, value="rate")
mort.fingerprint()   # 'sha256:…' -- equals the run record's assumptions[].fingerprint
```

## Guidelines

- Load **all assumptions at module level or in helper functions** — not inline in the calculation phase
- **Alias string columns before projection**: `pl.col("Policyholder sex").alias("sex")`
- Always verify lookups by spot-checking one policy: does the rate at age 45, duration 3 match the source table?
- For scenario-varying tables, look up: `uv run gspio docs "Table.from_scenario_files" -t code_example`
