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
from gaspatchio_core.assumptions import Table
import polars as pl

df = pl.read_parquet("assumptions/mortality.parquet")
mort = Table(
    name="mortality",
    source=df,
    dimensions={"age": "age", "duration": "duration"},
    value="rate",
)

# Lookup returns a column matching the projection shape
af.mort_rate = mort.lookup(age=af.attained_age, duration=af.duration)
```

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
from gaspatchio_core.assumptions import TableBuilder

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

Overflow strategies (`ExtendOverflow`, `FillForward`, `FillConstant`, `LinearInterpolate`) control what happens when a lookup key falls outside the table's range.

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
```

## Guidelines

- Load **all assumptions at module level or in helper functions** — not inline in the calculation phase
- **Alias string columns before projection**: `pl.col("Policyholder sex").alias("sex")`
- Always verify lookups by spot-checking one policy: does the rate at age 45, duration 3 match the source table?
- For scenario-varying tables, look up: `uv run gspio docs "Table.from_scenario_files" -t code_example`
