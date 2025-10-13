## Goal

1. When actuary reads this documentation they'll understand how to use this function for their domain (life insurance)
2. They'll think "gosh this is absolutely the best documentation i've read"
3. An LLM using RAG, especially in the when_to_use admonition, will be able to use this documentation when an actuary types I would like to $ACHIEVE_A_THING where $ACHIEVE_A_THING is some operation on an actuarial model.  

## Instructions

When you write an docstring you're aiming to educate an experienced life insurance actuary, so use dedicated domain specific examples. 

As much as possible we want to us ActuarialFrame examples showing off our DSL, and not just polars examples.  

You're also laying down the groundwork for an LLM to RAG this information, so we want to explain "When to use..."
again tying that back to when you're building an actuarial model you'd use this function to do what?  

You can search the web for good domain examples if you want to. 

The examples are going to get parsed into this object GaspatchioDocstring in @models.py so make sure that conform to that schema, pay special attention to `examples` and DocstringCodeExample which is where the lintable, executable examples are. 

Your examples are going to be linted using ruff and executed so they must be self contained. 

You need to provide a scalar and vector example if that makes sense in relation to the function. 

## Guidelines and tips 
- No need to mention "(List Shimming)" at all. 
- Prefer attribute access by default: use `af.column_name`.
- Avoid `pl.col(...)` and avoid `af["column_name"]` unless attribute access is impossible (dynamic names, special chars).

❌ BAD:
```python
pl.col("policy_id")
```

❌ ALSO BAD (unless you truly need dynamic access):
```python
af["policy_id"]
```

✅ GOOD (default style):
```python
af.policy_id
```
- Favor assignment-style examples that add or replace columns, e.g. `af.new_col = af.old_col.method(...)`.
- Use `.select(...)` only when you must produce multiple outputs at once or limit displayed columns; otherwise show `print(af.collect())`.
- Keep examples minimal and domain-relevant; avoid unnecessary plumbing.
- Don't bother explaining that behavior mirrors Polars.
- Keep "When to use" highly practical and domain specific for actuaries. 
- "When to use" can have 1-4 items, depending on how many actuarial use cases there are.
- "When to use" - don't overly explain obvious cases like dates, strings. 
- "When to use" - go into detail for financial functions.
- "When to use" - no preamble. Just the heading and the list.

### Style rules for examples
- Always show a tiny `ActuarialFrame` with realistic insurance data.
- Default to attribute access: `af.column`.
- Default to assignment: `af.new = af.old.method(...)`.
- End with a single `print(af.collect())` to display results.
- For list operations, prefer vectorized list APIs (e.g., `list.eval`, `list.*`) over row-wise maps.

### Templates
Scalar template
```python
from gaspatchio_core.frame.base import ActuarialFrame

data = {"policy_id": ["P1"], "x": [42]}
af = ActuarialFrame(data)

af.y = af.x.METHOD_HERE(...)

print(af.collect())
```

Vector (list) template
```python
from gaspatchio_core.frame.base import ActuarialFrame

data = {"policy_id": ["P1"], "xs": [[1, 2, 3]]}
af = ActuarialFrame(data)

af.ys = af.xs.list.METHOD_HERE(...)

print(af.collect())
```


### Exmaple

```python
def floor(self) -> "ExpressionProxy":
    """Round numeric values down to the nearest integer.

    Applies floor function to each value, returning the largest integer less than
    or equal to the input. Essential for actuarial calculations requiring conservative
    rounding, age calculations, and regulatory computations with specific rounding rules.

    !!! note "When to use"
        * **Age Calculations:** Convert decimal ages to completed years for
            underwriting, pricing tables, and regulatory age classifications.
        * **Conservative Estimates:** Apply conservative rounding for reserve
            calculations, capital requirements, or risk assessments.
        * **Regulatory Compliance:** Implement specific rounding rules required
            by insurance regulations or accounting standards.
        * **Policy Duration:** Calculate completed policy years or months for
            persistency analysis and commission calculations.
        * **Rate Table Lookups:** Round continuous values to discrete table
            entries for mortality tables, lapse rates, or premium factors.
        * **Financial Calculations:** Apply floor rounding for guaranteed minimum
            benefits, surrender values, or dividend calculations.

    Returns
    -------
    ExpressionProxy
        An expression containing values rounded down to the nearest integer.

    Examples
    --------
    **Scalar Example: Age Calculation**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "age_decimal": [35.8, 42.2, 58.9, 67.1],
    }
    af = ActuarialFrame(data)

    af.completed_age = af.age_decimal.floor()

    print(af.collect())
    ```

    ```text
    shape: (4, 2)
    ┌───────────┬───────────────┐
    │ policy_id ┆ completed_age │
    │ ---       ┆ ---           │
    │ str       ┆ f64           │
    ╞═══════════╪═══════════════╡
    │ P001      ┆ 35.0          │
    │ P002      ┆ 42.0          │
    │ P003      ┆ 58.0          │
    │ P004      ┆ 67.0          │
    └───────────┴───────────────┘
    ```

    **Vector Example: Policy Year Calculation**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "age": [55, 38],
        "month": [
            [1, 2, 3, 4],
            [1, 2, 3, 4]
        ],
        "policy_duration": [
            [9.0, 9.08, 9.16, 9.25],
            [5.0, 5.08, 5.16, 5.25]
        ]
    }
    af = ActuarialFrame(data)

    af.completed_years = af.policy_duration.floor()

    print(af.collect())
    ```

    ```text
        shape: (2, 5)
        ┌───────────┬─────┬──────────────┬───────────────────────────┬─────────────────────┐
        │ policy_id ┆ age ┆ month        ┆ policy_duration           ┆ completed_years     │
        │ ---       ┆ --- ┆ ---          ┆ ---                       ┆ ---                 │
        │ str       ┆ i64 ┆ list[i64]    ┆ list[f64]                 ┆ list[f64]           │
        ╞═══════════╪═════╪══════════════╪═══════════════════════════╪═════════════════════╡
        │ P001      ┆ 55  ┆ [1, 2, 3, 4] ┆ [9.0, 9.08, 9.16, 9.25]   ┆ [9.0, 9.0, 9.0, 9.0]│
        │ P002      ┆ 38  ┆ [1, 2, 3, 4] ┆ [5.0, 5.08, 5.16, 5.25]   ┆ [5.0, 5.0, 5.0, 5.0]│
        └───────────┴─────┴──────────────┴───────────────────────────┴─────────────────────┘
    ```
    """
```