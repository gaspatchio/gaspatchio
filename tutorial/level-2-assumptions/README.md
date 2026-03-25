# Level 2: Assumptions

This level teaches assumption table lookups — the core mechanism for separating
business assumptions from model logic in gaspatchio.

## What you'll learn

| Step | Concept |
|------|---------|
| Base | Single-dimension `Table`, `.lookup()` by age |
| Step 01 | Multi-dimension lookup (age × sex) |
| Step 02 | Load model points and tables from parquet files |
| Step 03 | Second `Table` for lapse rates, combined decrements |
| Step 04 | `when/then/otherwise` on list columns, maturity zeroing |

## The `Table` class

```python
from gaspatchio_core.assumptions import Table

mort_table = Table(
    name="mortality",
    source=mort_data,            # polars DataFrame or Path to parquet
    dimensions={"age": "age"},   # {dimension_name: column_name_in_source}
    value="qx",                  # column to return on lookup
)

af.qx_annual = mort_table.lookup(age=af.attained_age)
```

`Table.lookup()` performs an exact-match join between the table and your
projection. For each (policy, month) cell, it finds the row in `source` where
all dimension columns match the provided arguments and returns the value column.

## Prerequisites

- Level 1 base: ActuarialFrame, column arithmetic, when/then/otherwise
- Level 1 Step 03: time-shifting with `.projection.previous_period()`

## How to run each step

```bash
uv run python tutorial/level-2-assumptions/base/model.py
uv run python tutorial/level-2-assumptions/steps/01-multi-dimension/model.py
uv run python tutorial/level-2-assumptions/steps/02-from-files/model.py
uv run python tutorial/level-2-assumptions/steps/03-lapse/model.py
uv run python tutorial/level-2-assumptions/steps/04-conditionals/model.py
```
