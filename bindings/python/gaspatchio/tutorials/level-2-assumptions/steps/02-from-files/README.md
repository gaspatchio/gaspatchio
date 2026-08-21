# Step 02: Load Data from Files

## What changed from Step 01

Model points and mortality table are loaded from parquet files in `data/`
instead of being defined as inline Python dicts/DataFrames.

## Key pattern

```python
from pathlib import Path
import polars as pl

DATA_DIR = Path(__file__).parent / "data"

# In load_assumptions()
mort_table = Table(
    name="mortality",
    source=pl.read_parquet(DATA_DIR / "mortality.parquet"),
    ...
)

# In __main__
mp = pl.read_parquet(DATA_DIR / "model_points.parquet")
af = ActuarialFrame(mp)
```

## Why parquet

- **Type safety**: parquet preserves integer/float/string types without CSV's
  coercion risks (e.g., a column of "01", "02" stays strings, not integers)
- **Performance**: parquet is columnar and compressed — reads are fast even
  for millions of rows
- **Compatibility**: Polars reads parquet natively with no configuration

## Data directory

```
data/
  model_points.parquet   — 3 policies
  mortality.parquet      — 92 rows (ages 25–70, M and F)
```

## Output

Identical to Step 01. The model logic is unchanged; only the data source
has moved from inline code to files.
