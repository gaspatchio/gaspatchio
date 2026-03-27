# Step 01: Multi-Dimension Table

## What changed from base

The mortality table gains a second dimension: `sex`. The lookup now passes
both `age` and `sex` as keyword arguments.

## Key pattern

```python
mort_table = Table(
    name="mortality",
    source=mort_data,
    dimensions={"age": "age", "sex": "sex"},   # two lookup keys
    value="qx",
)

af.qx_annual = mort_table.lookup(age=af.attained_age, sex=af.sex)
```

`af.sex` is a scalar string per policy (`"M"` or `"F"`). `af.attained_age` is
a list column (one value per month). gaspatchio broadcasts the scalar to match
the list length automatically — you don't need to do anything special.

## Why it matters

Female mortality rates are typically 10–30% lower than male rates at the same
age. A single-dimension table by age alone would over-price female policies and
under-price male ones. The two-dimension lookup ensures each policy gets the
correct rate.

## Observable difference

Compare `pv_net_cf` for POL002 (female, age 45) between base and this step:

- **Base** (age only): POL002 uses the unisex rate → lower profit
- **Step 01** (age × sex): POL002 uses the female rate → slightly higher profit
  because lower mortality means lower expected death claims

This is a small effect over 12 months but compounds significantly over longer
projections.
