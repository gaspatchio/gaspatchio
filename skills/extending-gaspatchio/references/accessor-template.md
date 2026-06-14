## Column Accessor Template

This is the most common extension type. A column accessor adds methods to individual columns or expressions, accessed as `af.column_name.namespace.method()`.

### Minimal Example

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core.accessors.base import BaseColumnAccessor
from gaspatchio_core.frame.registry import register_accessor

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy


@register_accessor("risk", kind="column")
class RiskColumnAccessor(BaseColumnAccessor):
    """Risk calculation methods for column-level operations.

    Accessed via ``.risk`` on an ActuarialFrame column or expression proxy,
    e.g., ``af.age.risk.hazard_rate(a=0.0001, b=0.085)``.

    Methods
    -------
    hazard_rate(a, b)
        Compute Gompertz hazard rate.

    """

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None:
        super().__init__(proxy)

    def _get_polars_expr(self) -> pl.Expr:
        """Extract the underlying Polars expression from the proxy.

        Handles both ColumnProxy (uses pl.col) and ExpressionProxy
        (accesses _expr directly).
        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if isinstance(self._proxy, ExpressionProxy):
            return self._proxy._expr  # noqa: SLF001
        if isinstance(self._proxy, ColumnProxy):
            return pl.col(self._proxy.name)
        msg = f"Expected ColumnProxy or ExpressionProxy, got {type(self._proxy).__name__}"
        raise TypeError(msg)

    def hazard_rate(self, a: float, b: float) -> ExpressionProxy:
        """Compute Gompertz hazard rate: ``a * exp(b * age)``.

        Parameters
        ----------
        a : float
            Baseline mortality parameter.
        b : float
            Age sensitivity parameter.

        Returns
        -------
        ExpressionProxy
            Hazard rates with same structure as input (scalar or list).

        Examples
        --------
        ```python
        from gaspatchio_core import ActuarialFrame

        data = {"age": [30, 40, 50]}
        af = ActuarialFrame(data)

        af.hazard = af.age.risk.hazard_rate(a=0.0001, b=0.08)
        ```

        """
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        base_expr = self._get_polars_expr()
        parent_frame = self._proxy._parent  # noqa: SLF001

        if parent_frame is None:
            msg = "hazard_rate() requires the expression to be part of an ActuarialFrame context."
            raise RuntimeError(msg)

        # Detect list vs scalar via the proxy's cached shape (the SOT).
        is_list = (
            isinstance(self._proxy, ColumnProxy) and self._proxy.shape == "list"
        )

        if is_list:
            result_expr = base_expr.list.eval(
                pl.lit(a) * (pl.lit(b) * pl.element()).exp()
            )
        else:
            result_expr = pl.lit(a) * (pl.lit(b) * base_expr).exp()

        return ExpressionProxy(result_expr, parent_frame)
```

### Key Points

1. **Inherit from `BaseColumnAccessor`** — enforced at registration time.
2. **Define `_get_polars_expr()`** — handles both `ColumnProxy` (uses `pl.col(name)`) and `ExpressionProxy` (accesses `._expr`). The existing `finance.py` accessor uses this pattern. Copy it.
3. **`self._proxy._parent`** gives you the parent ActuarialFrame — needed to construct the return `ExpressionProxy`. Requires `# noqa: SLF001`.
4. **Guard against `parent_frame is None`** — raise `RuntimeError` with a clear message.
5. **Return `ExpressionProxy(expr, parent_frame)`** — never return a raw Polars expression, Series, or Python value.
6. **Docstrings use NumPy style** — `Parameters`, `Returns`, `Examples` with `--------` underlines. Include `!!! note "When to use"` admonitions for MkDocs rendering.

### Handling List Columns

Most Gaspatchio columns are list columns (each policy has a vector of monthly values). Your accessor must handle both scalar and list columns.

**The standard pattern** (from `finance.py:522-524`):

```python
from gaspatchio_core.column.column_proxy import ColumnProxy

# Get the underlying expression
base_expr = self._get_polars_expr()
parent_frame = self._proxy._parent  # noqa: SLF001

# Detect list vs scalar via the proxy's cached shape (the SOT).
is_list = (
    isinstance(self._proxy, ColumnProxy) and self._proxy.shape == "list"
)

if is_list:
    # List column: apply element-wise inside each list
    result_expr = base_expr.list.eval((1.0 + pl.element()).log())
else:
    # Scalar column: direct operation
    result_expr = (1.0 + base_expr).log()
```

**Important notes:**
- Read `proxy.shape` directly — it's the source of truth set when the proxy is constructed and cached per schema generation. No detector class, no per-call probe.
- List detection only works for `ColumnProxy` (which carries `.name` / `.shape`). For an `ExpressionProxy`, `is_list` defaults to `False` here — if you need shape-aware routing for a derived expression, read `expr_proxy.shape` instead. This matches the pattern in the existing codebase.

### When to Use `list.eval()` vs Direct Operations

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Direct expression** | Scalar column, simple arithmetic | `(1.0 + expr).log()` |
| **`list.eval()`** | List column, element-wise transform | `expr.list.eval((1.0 + pl.element()).log())` |
| **`list.eval()` with `.sum().list.first()`** | List-to-scalar reduction (duration, PV) | `expr.list.eval((pl.element() * weights).sum()).list.first()` |
| **`list.eval(pl.element().shift())`** | Adjacent element access (forward rates) | `expr.list.eval(pl.element().shift(1, fill_value=1.0))` |
| **`list.eval(pl.element().cum_count())`** | 1-indexed position (t=1,2,...,n) for Macaulay duration, annuity timing | `expr.list.eval(pl.element() * pl.element().cum_count().cast(pl.Float64))` |
| **`list.eval(pl.int_range(0, pl.element().len()))`** | 0-indexed position (t=0,1,...,n-1) for decay factors, zero-start formulas | `expr.list.eval((pl.lit(rate) * pl.int_range(0, pl.element().len()).cast(pl.Float64)).exp())` |
| **List column arithmetic** | Two list columns, element-wise — **preferred over `list.eval` when possible** | `list_a * list_b`, `list_a / list_b`, `list_a - list_b` (no `list.eval` needed) |

**0-indexed vs 1-indexed period indices:**
- Use `pl.element().cum_count()` for **1-indexed** positions (first element = 1). Correct for Macaulay duration where the first cashflow is at t=1.
- Use `pl.int_range(0, pl.element().len())` for **0-indexed** positions (first element = 0). Correct for decay factors, discount factors, or any formula where the first period has no effect (factor = 1.0 at t=0).
- Getting this wrong causes a silent off-by-one error. Choose deliberately.

### Direct List Column Arithmetic

For element-wise operations between two list columns, use direct Polars operators — no `list.eval` needed:

```python
# Good: direct list arithmetic (preferred)
profit_expr = af[premiums_col] - af[claims_col] - af[expenses_col]
ratio_expr = df_prev / base_expr  # two list columns, element-wise division

# Unnecessary: wrapping in list.eval when both sides are already list columns
# Don't do this — it adds overhead for no benefit
```

Direct list arithmetic is cleaner, faster, and more readable than `list.eval`. Use `list.eval` only when you need to operate on `pl.element()` within a single list (transforms, reductions, position indices).

### Scalar Pre-Computation for `list.eval`

When a method takes a Python scalar parameter that feeds into a `list.eval` expression, pre-compute the constant in Python before building the expression:

```python
# Good: pre-compute the multiplier, use as pl.lit() inside list.eval
deterioration = 1.0 + k * lapse_rate / (1.0 - lapse_rate)  # Python float
result_expr = base_expr.list.eval(pl.element() * pl.lit(deterioration))
```

This avoids the "`list.eval` cannot reference external columns" limitation entirely — Python literals are always safe inside `list.eval`.

### Limitation: `list.eval()` Cannot Reference External Columns

Inside `list.eval()`, you can only use `pl.element()` and Python literals. You **cannot** reference other columns or expressions. This means:

- Methods with **Python scalar parameters** (e.g., `to_monthly(method="compound")`) work fine in list.eval — the scalar is a Python literal.
- Methods that need **another column as a parameter** (e.g., `discount(rate_col, periods_col)`) cannot use `list.eval` for the list path. Options:
  1. Pre-compute the parameter as a Python scalar if possible (see above)
  2. Use direct list column arithmetic (`list_a * list_b`) when both inputs are lists with matching structure
  3. Use a Rust plugin (like `list_pow` in `discount_factor`) for complex cases
  4. Restrict the parameter to a scalar when the column is a list

---

## Frame Accessor Template

A frame accessor adds methods to the entire ActuarialFrame, accessed as `af.namespace.method()`.

### Minimal Example

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame


@register_accessor("reporting", kind="frame")
class ReportingFrameAccessor(BaseFrameAccessor):
    """Reporting utilities for ActuarialFrame.

    Access via: ``af.reporting.method()``

    Methods
    -------
    add_net_cashflow(premiums_col, claims_col, expenses_col, output_col)
        Add net cashflow column.

    """

    def __init__(self, frame: ActuarialFrame) -> None:
        super().__init__(frame)

    def add_net_cashflow(
        self,
        premiums_col: str = "premiums",
        claims_col: str = "claims",
        expenses_col: str = "expenses",
        output_col: str = "net_cf",
    ) -> ActuarialFrame:
        """Add net cashflow column: premiums - claims - expenses.

        Parameters
        ----------
        premiums_col : str
            Name of premiums column.
        claims_col : str
            Name of claims column.
        expenses_col : str
            Name of expenses column.
        output_col : str
            Name for the output column.

        Returns
        -------
        ActuarialFrame
            Frame with the new column added.

        """
        af = self._frame
        af[output_col] = af[premiums_col] - af[claims_col] - af[expenses_col]
        return af
```

### Key Points

1. **Inherit from `BaseFrameAccessor`** — enforced at registration.
2. **`self._frame`** gives you the ActuarialFrame.
3. **Return `ActuarialFrame`** from methods that add or transform columns.
4. **Use column names as string parameters** — the frame accessor operates on named columns, not on a specific expression.

---

## Adding Methods to an Existing Accessor

If you want to add methods to an existing namespace (e.g., adding `duration_macaulay` to `finance`), add the method directly to the existing accessor class file. Do NOT create a second accessor with the same name — this will raise a `ValueError`.

**Read the existing file first.** Match its patterns exactly: `_get_polars_expr()`, the `proxy.shape == "list"` check for list/scalar branching, `_parent is None` guard, NumPy-style docstrings.

Location of existing accessors:

| Namespace | File |
|-----------|------|
| `finance` | `gaspatchio_core/accessors/finance.py` |
| `projection` | `gaspatchio_core/accessors/projection.py` |
| `projection` (frame) | `gaspatchio_core/accessors/projection_frame.py` |
| `date` | `gaspatchio_core/accessors/date.py` |
| `excel` | `gaspatchio_core/accessors/excel.py` |

---

## Registration and Import

The accessor is registered when the module containing the `@register_accessor` decorator is imported.

### For new namespaces in gaspatchio-core:

1. Create your accessor file in `gaspatchio_core/accessors/your_accessor.py`
2. Add the import to `gaspatchio_core/accessors/__init__.py`:
   ```python
   from . import your_accessor
   ```
   This is an import-for-side-effects — ruff keeps `from . import` forms.

### For user-local accessors (not modifying gaspatchio source):

This is the most common case for agents extending Gaspatchio in a user's project.

1. Create your accessor file in the user's project directory:

```
my_project/
    model.py
    my_accessors.py    # Your accessor file
    data.parquet
```

2. Write the accessor following the templates above. The file is self-contained — it imports from `gaspatchio_core` and registers itself.

3. Import it at the top of the model file **before** using the accessor:

```python
import my_accessors  # noqa: F401  # registers custom accessors

from gaspatchio_core import ActuarialFrame

def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    # Custom accessor is now available
    af.hazard = af.age.risk.hazard_rate(a=0.0001, b=0.085)
    return af
```

**Important notes for local accessors:**
- The `# noqa: F401` comment prevents ruff from stripping the "unused" import. The import IS used — it triggers registration as a side effect.
- The accessor file must be importable from the model file's location. If running with `uv run gspio run-model model.py ...`, the model's directory is on `sys.path`.
- If two local accessor files register the same namespace name, the second import will raise `ValueError`. Use unique namespace names.
- Test with `uv run python3 -c "import my_accessors; print('OK')"` to verify importability.

### Testing local accessors

For docstring example validation:
```bash
uv run pytest --doctest-modules my_accessors.py
```

For a quick smoke test:
```bash
uv run python3 -c "
import my_accessors  # noqa: F401
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'age': [30, 50, 70]})
af.hazard = af.age.risk.hazard_rate(a=0.0001, b=0.085)
print(af.collect())
"
```
