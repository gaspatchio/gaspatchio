# Execution Plan: Polars Delegation & Vector‑Aware Unary Ops

This document outlines the step-by-step implementation plan for the features described in `05-spec.md`, including prompts for a code-generation LLM.

## Phase 1: Core Delegation Infrastructure

### Step 1.1: Create Delegation Helpers Module

**Goal:** Set up the foundational helper functions for unwrapping proxy objects, wrapping results, and handling the vectorization shim.

**File:** `gaspatchio_core/dsl/core/_delegation.py` (New file)

**Key Code Snippets (from spec):**

```python
import functools, polars as pl
from typing import Any, TYPE_CHECKING

# Avoid circular imports at runtime but allow type checking
if TYPE_CHECKING:
    from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy, ActuarialFrame

# Verify comprehensive list - Start with a smaller, critical set for initial tests
_NUMERIC_UNARY = {"floor", "ceil", "round", "abs", "sqrt", "log", "log10", "exp"}

def _unwrap(arg: Any) -> Any:
    # Defer import until needed to avoid circular dependency
    from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy
    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    return arg

def _wrap(parent: 'ActuarialFrame' | None, result: Any) -> Any:
    # Defer import
    from gaspatchio_core.dsl.core import ExpressionProxy # Potentially other proxy types needed
    if isinstance(result, pl.Expr):
        # Ensure the parent context is passed along
        return ExpressionProxy(result, parent)
    # Placeholder for future namespace proxy handling
    # elif isinstance(result, SomePolarsNamespaceType):
    #     return NamespaceProxy(result, parent)
    return result # Return other types (like scalars) directly

def _vectorise_if_list(expr: pl.Expr, op_name: str) -> pl.Expr:
    # Initial basic check - needs refinement based on schema or type hints later
    # This is a simplification for the first step; robust type checking comes later.
    # For now, we rely on Polars to raise errors if list.eval is used inappropriately.
    if op_name in _NUMERIC_UNARY:
        # Attempt list evaluation, let Polars handle errors if not a list
        # or if the operation is invalid for the list's inner type.
        try:
            # Use getattr for dynamic op lookup on pl.element()
            list_op_func = getattr(pl.element(), op_name)
            # Only call if it's a callable attribute (method)
            if callable(list_op_func):
                 return expr.list.eval(list_op_func())
            # else: handle non-callable attributes if necessary later
        except (pl.ComputeError, AttributeError, TypeError) as e:
            # Log warning or handle error? For now, just return original expr
            # print(f"Info: list.eval skipped or failed for {op_name}: {e}") # Optional logging
            return expr # Return original expression on failure or if op not callable
    return expr

def _make_wrapper(name: str) -> Callable:
    """Factory to create proxied methods/attributes for Polars Expr."""
    # Note: 'target' argument removed as getattr handles it dynamically.
    # functools.wraps is tricky here as the target isn't fixed.
    # We'll handle docstrings later if needed.
    def method(self: 'ColumnProxy' | 'ExpressionProxy', *args: Any, **kwargs: Any) -> Any:
        # Determine base expression (Column or Expression)
        base_expr: pl.Expr
        if hasattr(self, "name"): # ColumnProxy duck typing
            base_expr = pl.col(self.name)
        elif hasattr(self, "_expr"): # ExpressionProxy duck typing
            base_expr = self._expr
        else:
            raise TypeError("Wrapper called on incompatible object")

        parent_af = getattr(self, "_parent", None) # Get the ActuarialFrame context

        # Handle attribute access (methods and namespaces)
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError:
             # Provide a more informative error message
             proxy_type = type(self).__name__
             base_type = type(base_expr).__name__
             raise AttributeError(f"Polars object '{base_type}' (accessed via '{proxy_type}') has no attribute '{name}'")

        result: Any
        if callable(polars_attr):
             # It's a method call
             unwrapped_args = [_unwrap(a) for a in args]
             unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
             try:
                 res_intermediate = polars_attr(*unwrapped_args, **unwrapped_kwargs)
             except Exception as e:
                 # Add context to the Polars error
                 raise type(e)(f"Error calling Polars method '{name}' via proxy: {e}") from e
        else:
             # Assume namespace access or property get
             if args or kwargs:
                 raise TypeError(f"Attribute '{name}' accessed as method (with args/kwargs) but is not callable on Polars object")
             res_intermediate = polars_attr # Get the namespace object or property value

        # Apply vector shim ONLY to callable methods returning an Expr
        if isinstance(res_intermediate, pl.Expr) and callable(polars_attr):
            result = _vectorise_if_list(res_intermediate, name)
        else:
            result = res_intermediate

        # Wrap the result (Expr, namespace, or scalar)
        return _wrap(parent_af, result)

    # Set a dynamic name for better debugging/repr
    method.__name__ = f"proxied_{name}"
    # Docstring handling can be added here if needed, potentially fetching from Polars
    # method.__doc__ = getattr(target, "__doc__", f"Proxied Polars attribute: {name}")
    return method
```

**LLM Prompt 1.1:**
```text
Create a new file named `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core/_delegation.py`.

Populate this file with the following Python code:
- Import `functools`, `polars as pl`, `typing.Any`, `typing.Callable`, and `typing.TYPE_CHECKING`.
- Add a `TYPE_CHECKING` block to import `ColumnProxy`, `ExpressionProxy`, and `ActuarialFrame` from `gaspatchio_core.dsl.core`.
- Define a set `_NUMERIC_UNARY` containing initial unary numeric operations: "floor", "ceil", "round", "abs", "sqrt", "log", "log10", "exp".
- Implement the `_unwrap` function as defined in the spec, using deferred imports for `ColumnProxy` and `ExpressionProxy`.
- Implement the `_wrap` function as defined in the spec, using deferred imports for `ExpressionProxy` and passing the parent `ActuarialFrame`. Add a comment placeholder for future namespace proxy handling.
- Implement the `_vectorise_if_list` function. It should take a `pl.Expr` and `op_name` string. Check if `op_name` is in `_NUMERIC_UNARY`. If yes, try to dynamically get the corresponding method from `pl.element()`, check if it's callable, and if so, return `expr.list.eval(method())`. Use a try-except block around the `list.eval` call to catch `pl.ComputeError`, `AttributeError`, and `TypeError`, returning the original `expr` if an exception occurs or if the attribute is not callable. If `op_name` is not in the set, return the original `expr`.
- Implement the `_make_wrapper` function factory. It takes `name` (string) and returns a callable (`method`). Inside `method`, which takes `self` (`ColumnProxy` or `ExpressionProxy`), `*args`, `**kwargs`:
    - Determine the `base_expr` (either `pl.col(self.name)` or `self._expr`) using `hasattr`. Raise `TypeError` if neither fits.
    - Get the parent `ActuarialFrame` using `getattr(self, "_parent", None)`.
    - Use `getattr(base_expr, name)` to get the `polars_attr`. Catch `AttributeError` and raise a more informative one.
    - Check if `polars_attr` is callable.
        - If yes: unwrap args/kwargs using `_unwrap`, call `polars_attr`, and store in `res_intermediate`. Catch exceptions and re-raise with context.
        - If no: check if `args` or `kwargs` were passed; if so, raise `TypeError`. Otherwise, assign `polars_attr` to `res_intermediate`.
    - Check if `res_intermediate` is a `pl.Expr` AND `polars_attr` was callable. If yes, apply `_vectorise_if_list` to it, storing the result in `result`. Otherwise, assign `res_intermediate` to `result`.
    - Wrap the final `result` using `_wrap(parent_af, result)` and return it.
    - Set `method.__name__` to `f"proxied_{name}"`.
- Add type hints to all functions.
```

### Step 1.2: Initial Autopatching Mechanism

**Goal:** Implement the basic `_autopatch` function to dynamically add wrapped methods to proxy classes at import time. Start with `pl.Expr` attributes only.

**File:** `gaspatchio_core/dsl/core/_delegation.py` (Modify)

**Key Code Snippets (from spec):**

```python
# (Inside _delegation.py)
def _autopatch(proxy_cls: type) -> None:
    """Dynamically add proxied Polars Expr methods to a proxy class."""
    # Iterate over Expr attributes
    processed_attrs: set[str] = set()
    # Include attributes inherited from BaseExpr if necessary
    attrs_to_process = dir(pl.Expr) # Potentially add dir(pl.internals.expr.expr.BaseExpr) if needed

    for attr_name in attrs_to_process:
        # Skip private/dunder attributes and already processed ones
        if attr_name.startswith("_") or attr_name in processed_attrs:
            continue

        # Check if it's a standard Expr attribute (method or property)
        try:
            # No need to get the actual attribute here, _make_wrapper does it.
            # We just need the name.
            # We assume _make_wrapper will correctly handle both methods and properties.
            setattr(proxy_cls, attr_name, _make_wrapper(attr_name))
            processed_attrs.add(attr_name)
        except Exception as e:
            # Log or print warnings for skipped attributes during development
            print(f"Warning: Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}")

    # Add __dir__ method to include patched attributes for better introspection
    original_dir = getattr(proxy_cls, '__dir__', object.__dir__)
    def __dir__(self):
        return sorted(list(set(original_dir(self)) | processed_attrs))
    proxy_cls.__dir__ = __dir__

```

**LLM Prompt 1.2:**
```text
Modify the file `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core/_delegation.py`.

Add a function `_autopatch(proxy_cls: type) -> None`.
- Inside the function:
    - Initialize an empty set `processed_attrs`.
    - Get attributes to process using `attrs_to_process = dir(pl.Expr)`.
    - Iterate through `attr_name` in `attrs_to_process`.
    - Skip if `attr_name` starts with `_` or is already in `processed_attrs`.
    - Inside a `try...except Exception as e` block:
        - Call `setattr(proxy_cls, attr_name, _make_wrapper(attr_name))` to attach the wrapped method/property.
        - Add `attr_name` to `processed_attrs`.
    - In the `except` block, print a warning message including the attribute name, class name, and the exception `e`.
- After the loop, define a `__dir__(self)` method. It should:
    - Get the original `__dir__` of the class or `object.__dir__` as a fallback.
    - Call the original `__dir__` on `self`.
    - Return a sorted list containing the unique union of the original dir result and `processed_attrs`.
- Assign this new `__dir__` method to `proxy_cls.__dir__`.
- Add type hints.
```

### Step 1.3: Integrate Autopatching and Initial Test

**Goal:** Call `_autopatch` for `ColumnProxy` and `ExpressionProxy` and write a basic test to verify a few core `pl.Expr` methods are now available and work.

**Files:**
- `gaspatchio_core/dsl/core.py` (Modify)
- `gaspatchio_core/dsl/core/__init__.py` (Modify or Create)
- `tests/test_core_delegation.py` (New file)

**Integration:**

```python
# --- In gaspatchio_core/dsl/core.py (or __init__.py) ---
from ._delegation import _autopatch

# ... (Existing ColumnProxy and ExpressionProxy class definitions) ...

# Apply the patching after the classes are defined
_autopatch(ColumnProxy)
_autopatch(ExpressionProxy)

# --- Example Test ---
# In tests/test_core_delegation.py
import polars as pl
from polars.testing import assert_frame_equal
from gaspatchio_core.dsl.core import ActuarialFrame

def test_basic_delegation_arithmetic():
    data = {"a": [1, 2, 3], "b": [4, 5, 6]}
    af = ActuarialFrame(data)

    # Test proxied arithmetic (already worked, but good baseline)
    af["c"] = af["a"] + af["b"]
    af["d"] = af["a"] * 2

    # Test newly autopatched method (e.g., abs)
    af["a_abs"] = af["a"].abs() # Assuming 'a' could be negative

    # Test newly autopatched property/attribute (e.g., meta.output_name())
    # This requires _make_wrapper and _wrap to handle non-Expr results
    output_name = af["a"].meta.output_name() # Need to ensure .meta works
    assert output_name == "a"

    # Test chaining
    af["b_chain"] = af["b"].abs().cast(pl.Float32) * 3


    expected_data = {
        "a": [1, 2, 3],
        "b": [4, 5, 6],
        "c": [5, 7, 9],
        "d": [2, 4, 6],
        "a_abs": [1, 2, 3],
        "b_chain": [12.0, 15.0, 18.0] # Note float type
    }
    expected_lf = pl.LazyFrame(expected_data).with_columns(
        pl.col("b_chain").cast(pl.Float32) # Ensure correct type in expected
    )

    # Need to select columns in the same order for comparison
    result_lf = af._df.select(expected_lf.columns)

    assert_frame_equal(result_lf.collect(), expected_lf.collect())

def test_delegation_agg():
    data = {"group": ["x", "x", "y"], "value": [10, 20, 30]}
    af = ActuarialFrame(data)

    # Test aggregation method via proxy
    agg_af = af._df.group_by("group").agg(
        mean_val = af["value"].mean(), # Use proxy within agg
        sum_val = af["value"].sum()
    ).sort("group")

    expected = pl.LazyFrame({
        "group": ["x", "y"],
        "mean_val": [15.0, 30.0],
        "sum_val": [30, 30]
    })

    assert_frame_equal(agg_af.collect(), expected.collect())
```

**LLM Prompt 1.3:**
```text
1.  **Modify `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core.py`:**
    - At the top, add `from ._delegation import _autopatch`.
    - At the very bottom of the file (after the `ColumnProxy` and `ExpressionProxy` class definitions), add the lines:
      ```python
      # Apply the patching after the classes are defined
      _autopatch(ColumnProxy)
      _autopatch(ExpressionProxy)
      ```

2.  **Create `gaspatchio-core/bindings/python/tests/test_core_delegation.py`:**
    - Import `polars as pl`, `assert_frame_equal` from `polars.testing`, and `ActuarialFrame` from `gaspatchio_core.dsl.core`.
    - Create a test function `test_basic_delegation_arithmetic()`:
        - Initialize `data = {"a": [1, 2, 3], "b": [4, 5, 6]}` and `af = ActuarialFrame(data)`.
        - Add columns using standard arithmetic: `af["c"] = af["a"] + af["b"]`, `af["d"] = af["a"] * 2`.
        - Add a column using a newly delegated method: `af["a_abs"] = af["a"].abs()`.
        - Add a column testing chaining: `af["b_chain"] = af["b"].abs().cast(pl.Float32) * 3`.
        - Define the `expected_data` dictionary including columns "a", "b", "c", "d", "a_abs", "b_chain" with correct values and types (note "b_chain" is float).
        - Create `expected_lf = pl.LazyFrame(expected_data).with_columns(pl.col("b_chain").cast(pl.Float32))`.
        - Create `result_lf = af._df.select(expected_lf.columns)` to ensure column order.
        - Use `assert_frame_equal(result_lf.collect(), expected_lf.collect())`.
    - Create a test function `test_delegation_agg()`:
        - Initialize `data = {"group": ["x", "x", "y"], "value": [10, 20, 30]}` and `af = ActuarialFrame(data)`.
        - Perform a group-by aggregation using the proxy methods within `agg`:
          ```python
          agg_af = af._df.group_by("group").agg(
              mean_val = af["value"].mean(),
              sum_val = af["value"].sum()
          ).sort("group")
          ```
        - Define the `expected` LazyFrame with columns "group", "mean_val", "sum_val" and sorted values.
        - Use `assert_frame_equal(agg_af.collect(), expected.collect())`.

3.  **Run tests:** Ensure the new tests pass. You might need to adjust the `_make_wrapper` or `_wrap` function if properties like `.meta` or methods returning non-Expr objects cause issues initially. Focus on getting `abs()` and `mean()`/`sum()` working first.
```

## Phase 2: Namespace Delegation and Vector Shim

### Step 2.1: Extend Autopatch for Namespaces

**Goal:** Modify `_autopatch` to recognize and proxy common Polars namespaces (`dt`, `str`, `list`, `arr`, `struct`).

**File:** `gaspatchio_core/dsl/core/_delegation.py` (Modify)

**Key Code Snippets (from spec):**

```python
# (Inside _delegation.py)

# Define common namespaces
_NAMESPACES = {"dt", "str", "list", "arr", "struct", "cat", "bin"} # Add others if needed

# ... (Existing _make_wrapper, _unwrap, _wrap, _vectorise_if_list) ...

def _autopatch(proxy_cls: type) -> None:
    """Dynamically add proxied Polars Expr methods AND namespaces to a proxy class."""
    processed_attrs: set[str] = set()
    # Include common namespaces in the attributes to consider
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES) # Combine Expr attrs and namespaces

    for attr_name in set(attrs_to_process): # Use set to avoid duplicates
        # Skip private/dunder attributes and already processed ones
        if attr_name.startswith("_") or attr_name in processed_attrs:
            continue

        # Check if it's a known namespace or a standard Expr attribute
        try:
            # _make_wrapper handles both method calls and attribute/namespace access
            setattr(proxy_cls, attr_name, _make_wrapper(attr_name))
            processed_attrs.add(attr_name)
        except Exception as e:
            # Log or print warnings for skipped attributes during development
            print(f"Warning: Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}")

    # Update __dir__ method (already added in previous step)
    # No changes needed here as processed_attrs now includes namespaces

```
*Self-Correction:* The original spec suggested complex logic for namespaces. However, the `_make_wrapper` design handles attribute access (`getattr(base_expr, name)`) generically. If the attribute is a namespace object (like `ExprDT`), `getattr` returns it, `callable()` is false, and `_make_wrapper` returns it. The subsequent call (e.g., `.dt.year()`) triggers another `__getattr__` or proxied call on that namespace object *if* we wrap namespace objects in their own proxies. For simplicity *initially*, we won't wrap namespaces explicitly; `_wrap` will return the raw Polars namespace object. This means `af["date_col"].dt` returns a Polars `ExprDT`, and `af["date_col"].dt.year()` works because Polars handles `ExprDT.year()`. We only need `_wrap` to return a custom `NamespaceProxy` if we want to intercept calls *within* a namespace (e.g., add logging to `dt.year()`). We will defer creating `NamespaceProxy` until needed.

**LLM Prompt 2.1:**
```text
Modify the file `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core/_delegation.py`.

1.  **Add Namespace Constant:** Above the `_autopatch` function, define the set:
    ```python
    _NAMESPACES = {"dt", "str", "list", "arr", "struct", "cat", "bin"}
    ```
2.  **Modify `_autopatch`:**
    - Change the line defining `attrs_to_process` to combine `dir(pl.Expr)` and the namespaces:
      ```python
      attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)
      ```
    - Change the loop definition to iterate over unique names:
      ```python
      for attr_name in set(attrs_to_process):
      ```
    - No other changes are needed inside `_autopatch` for this step. The existing `_make_wrapper` logic should handle namespace access correctly by returning the raw Polars namespace object via `_wrap`.

3.  Ensure type hints are still correct.
```

### Step 2.2: Test Namespace Access

**Goal:** Add tests verifying that namespace methods (like `dt.year`, `str.contains`, `list.eval`) work through the proxy.

**File:** `tests/test_core_delegation.py` (Modify)

**Example Tests:**

```python
# (Inside tests/test_core_delegation.py)
import datetime

# ... (existing imports) ...

def test_namespace_delegation_dt():
    data = {"dates": [datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)]}
    af = ActuarialFrame(data)
    af["year"] = af["dates"].dt.year()
    af["month"] = af["dates"].dt.month()

    expected = pl.LazyFrame({
        "dates": [datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)],
        "year": [2023, 2024],
        "month": [1, 12]
    })
    result_lf = af._df.select(expected.columns)
    assert_frame_equal(result_lf.collect(), expected.collect())

def test_namespace_delegation_str():
    data = {"text": ["apple", "banana", "orange"]}
    af = ActuarialFrame(data)
    af["contains_a"] = af["text"].str.contains("a")
    af["len"] = af["text"].str.len_bytes() # Example method

    expected = pl.LazyFrame({
        "text": ["apple", "banana", "orange"],
        "contains_a": [True, True, True],
        "len": [5, 6, 6] # Length in bytes
    })
    result_lf = af._df.select(expected.columns)
    assert_frame_equal(result_lf.collect(), expected.collect())

def test_namespace_delegation_list():
    data = {"lists": [[1, 2], [3, 4, 5], []]}
    af = ActuarialFrame(data)
    af["list_sum"] = af["lists"].list.sum()
    af["list_len"] = af["lists"].list.len()

    expected = pl.LazyFrame({
        "lists": [[1, 2], [3, 4, 5], []],
        "list_sum": [3, 12, 0],
        "list_len": [2, 3, 0]
    })
    result_lf = af._df.select(expected.columns)
    assert_frame_equal(result_lf.collect(), expected.collect(), check_dtype=False) # list type can be tricky
```

**LLM Prompt 2.2:**
```text
Modify the file `gaspatchio-core/bindings/python/tests/test_core_delegation.py`.

1.  Add `import datetime` at the top.
2.  Add a test function `test_namespace_delegation_dt()`:
    - Create `data = {"dates": [datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)]}` and `af = ActuarialFrame(data)`.
    - Add columns using proxied `dt` namespace methods: `af["year"] = af["dates"].dt.year()`, `af["month"] = af["dates"].dt.month()`.
    - Define the `expected` LazyFrame with "dates", "year", and "month" columns and corresponding values.
    - Select columns from `af._df` to match `expected` and use `assert_frame_equal` to compare the collected results.
3.  Add a test function `test_namespace_delegation_str()`:
    - Create `data = {"text": ["apple", "banana", "orange"]}` and `af = ActuarialFrame(data)`.
    - Add columns using proxied `str` namespace methods: `af["contains_a"] = af["text"].str.contains("a")`, `af["len"] = af["text"].str.len_bytes()`.
    - Define the `expected` LazyFrame with "text", "contains_a", and "len" columns and corresponding values.
    - Select columns from `af._df` and use `assert_frame_equal` to compare collected results.
4.  Add a test function `test_namespace_delegation_list()`:
    - Create `data = {"lists": [[1, 2], [3, 4, 5], []]}` and `af = ActuarialFrame(data)`.
    - Add columns using proxied `list` namespace methods: `af["list_sum"] = af["lists"].list.sum()`, `af["list_len"] = af["lists"].list.len()`.
    - Define the `expected` LazyFrame with "lists", "list_sum", and "list_len" columns and corresponding values.
    - Select columns from `af._df` and use `assert_frame_equal(..., check_dtype=False)` to compare collected results (list types can sometimes differ).
5.  Run tests to ensure namespace methods are working correctly.
```

### Step 2.3: Integrate and Test Vector Shim

**Goal:** Ensure the `_vectorise_if_list` function within `_make_wrapper` correctly applies `list.eval` for unary numeric operations on list columns.

**File:** `tests/test_core_delegation.py` (Modify)

**Example Tests:**

```python
# (Inside tests/test_core_delegation.py)

# ... (existing imports) ...

def test_vector_shim_unary_ops():
    data = {
        "list_float": [[1.1, 2.9], [-3.5, 0.0], [100.2]],
        "list_int": [[1, 2], [-3, 0], [100]],
        "scalar_float": [1.1, -3.5, 100.2]
    }
    af = ActuarialFrame(data)

    # Test floor on list<float> -> should use list.eval via shim
    af["list_float_floor"] = af["list_float"].floor()

    # Test abs on list<int> -> should use list.eval via shim
    af["list_int_abs"] = af["list_int"].abs()

    # Test sqrt on list<float> (ensure positive input or handle errors)
    # Make list positive first for sqrt
    af["list_float_pos"] = af["list_float"].list.eval(pl.element().filter(pl.element() > 0))
    af["list_float_pos_sqrt"] = af["list_float_pos"].sqrt() # Shim applies here

    # Test on scalar -> shim should NOT apply list.eval
    af["scalar_float_floor"] = af["scalar_float"].floor()

    # Test non-unary op on list -> shim should NOT apply list.eval (Polars handles it)
    af["list_float_plus_1"] = af["list_float"] + 1 # Relies on Polars broadcasting

    expected = pl.LazyFrame({
        "list_float": [[1.1, 2.9], [-3.5, 0.0], [100.2]],
        "list_int": [[1, 2], [-3, 0], [100]],
        "scalar_float": [1.1, -3.5, 100.2],
        "list_float_floor": [[1.0, 2.0], [-4.0, 0.0], [100.0]], # Note: floor result is float
        "list_int_abs": [[1, 2], [3, 0], [100]],
        "list_float_pos": [[1.1, 2.9], [], [100.2]], # After filter
        # Sqrt result needs careful type checking, Polars usually returns float
        "list_float_pos_sqrt": [[1.0488088, 1.7029386], [], [10.009995]],
        "scalar_float_floor": [1.0, -4.0, 100.0], # Scalar floor
         # Polars >= 0.19.12 might broadcast differently, adjust if needed
        "list_float_plus_1": [[2.1, 3.9], [-2.5, 1.0], [101.2]]
    })

    # Adjust expected types if necessary based on Polars version
    expected = expected.with_columns(
        pl.col("list_float_pos_sqrt").cast(pl.List(pl.Float64)),
        pl.col("list_float_plus_1").cast(pl.List(pl.Float64))
    )


    result_lf = af._df.select(expected.columns)
    # Use check_exact=False due to potential float precision issues with sqrt
    assert_frame_equal(result_lf.collect(), expected.collect(), check_dtype=False, rtol=1e-5)

```

**LLM Prompt 2.3:**
```text
Modify the file `gaspatchio-core/bindings/python/tests/test_core_delegation.py`.

Add a test function `test_vector_shim_unary_ops()`:
- Create `data` dictionary with columns:
    - `"list_float"`: `[[1.1, 2.9], [-3.5, 0.0], [100.2]]`
    - `"list_int"`: `[[1, 2], [-3, 0], [100]]`
    - `"scalar_float"`: `[1.1, -3.5, 100.2]`
- Create `af = ActuarialFrame(data)`.
- Test unary ops on list columns (should trigger shim):
    - `af["list_float_floor"] = af["list_float"].floor()`
    - `af["list_int_abs"] = af["list_int"].abs()`
- Test sqrt on a list column (requires positive values):
    - `af["list_float_pos"] = af["list_float"].list.eval(pl.element().filter(pl.element() > 0))`
    - `af["list_float_pos_sqrt"] = af["list_float_pos"].sqrt()`
- Test unary op on scalar column (should NOT trigger shim's list.eval):
    - `af["scalar_float_floor"] = af["scalar_float"].floor()`
- Test non-unary op on list column (should NOT trigger shim):
    - `af["list_float_plus_1"] = af["list_float"] + 1`
- Define the `expected` LazyFrame containing all original and calculated columns with the correct expected values. Pay attention to data types (e.g., floor results are floats, sqrt results are floats). Use example values like:
    - `list_float_floor`: `[[1.0, 2.0], [-4.0, 0.0], [100.0]]`
    - `list_int_abs`: `[[1, 2], [3, 0], [100]]`
    - `list_float_pos_sqrt`: `[[1.0488088, 1.7029386], [], [10.009995]]` (approx)
    - `scalar_float_floor`: `[1.0, -4.0, 100.0]`
    - `list_float_plus_1`: `[[2.1, 3.9], [-2.5, 1.0], [101.2]]`
- Cast list columns in `expected` to appropriate `pl.List(pl.Float64)` or `pl.List(pl.Int64)` if needed.
- Select columns from `af._df` matching `expected.columns`.
- Use `assert_frame_equal(..., check_dtype=False, rtol=1e-5)` to compare collected results, allowing for float inaccuracies.
- Run tests. Debug `_vectorise_if_list` if necessary, potentially adding logging inside its `try...except` block to see why `list.eval` might fail or be skipped.
```

## Phase 3: API Refinement and Cleanup

### Step 3.1: Refactor ActuarialFrame Helpers

**Goal:** Update existing helper methods in `ActuarialFrame` (like the custom `floor`, `round`, etc.) to use the new delegated proxy methods. Deprecate the old helpers.

**File:** `gaspatchio_core/dsl/core.py` (Modify)

**Refactoring Example:**

```python
# (Inside ActuarialFrame class in core.py)

import warnings # Add import

# ... (Existing imports and methods) ...

    # --- DEPRECATE Old Custom Function Wrappers ---

    # Keep the old ones for a bit but add warnings
    # Remove the direct calls to core_floor, core_round etc.

    @property # Make it a property to discourage use with args
    def floor(self) -> None:
         """
        DEPRECATED: Use af['col_name'].floor() instead.
        This method no longer accepts arguments. Access the floor method
        directly on a column or expression proxy.
        Example: af['my_col'].floor()
        """
         warnings.warn(
             "Directly calling af.floor(...) is deprecated. Use af['col_name'].floor() instead.",
             DeprecationWarning,
             stacklevel=2
         )
         # Optionally raise error after deprecation period
         # raise AttributeError("af.floor is deprecated. Use af['col_name'].floor() instead.")
         # Return None or raise to prevent misuse
         return None

    @property
    def round(self) -> None:
         """
        DEPRECATED: Use af['col_name'].round(decimals=...) instead.
        This method no longer accepts arguments. Access the round method
        directly on a column or expression proxy.
        Example: af['my_col'].round(2)
        """
         warnings.warn(
             "Directly calling af.round(...) is deprecated. Use af['col_name'].round(decimals=...) instead.",
             DeprecationWarning,
             stacklevel=2
         )
         return None

    # Repeat for round_to_int, fill_series if they were ActuarialFrame methods

    # --- Remove Old Implementations if they existed ---
    # Search for any methods like floor, round, etc. that took an `expr` argument
    # and remove or deprecate them as shown above.

    # Ensure custom functions are still imported if needed elsewhere, but not wrapped here.
    # from gaspatchio_core.functions import fill_series as core_fill_series # Keep if used directly

    # ... (Rest of the ActuarialFrame class) ...

```

**LLM Prompt 3.1:**
```text
Modify the file `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core.py`.

1.  Add `import warnings` at the top.
2.  **Locate Helper Methods:** Find the methods `fill_series`, `floor`, `round`, and `round_to_int` within the `ActuarialFrame` class definition.
3.  **Refactor/Deprecate `floor`:**
    - Change the method signature to `@property def floor(self) -> None:`.
    - Replace the entire method body with:
      ```python
      """
      DEPRECATED: Use af['col_name'].floor() instead.
      This method no longer accepts arguments. Access the floor method
      directly on a column or expression proxy.
      Example: af['my_col'].floor()
      """
      warnings.warn(
          "Directly calling af.floor(...) is deprecated. Use af['col_name'].floor() instead.",
          DeprecationWarning,
          stacklevel=2
      )
      return None
      ```
4.  **Refactor/Deprecate `round`:**
    - Change the method signature to `@property def round(self) -> None:`.
    - Replace the entire method body with:
      ```python
      """
      DEPRECATED: Use af['col_name'].round(decimals=...) instead.
      This method no longer accepts arguments. Access the round method
      directly on a column or expression proxy.
      Example: af['my_col'].round(2)
      """
      warnings.warn(
          "Directly calling af.round(...) is deprecated. Use af['col_name'].round(decimals=...) instead.",
          DeprecationWarning,
          stacklevel=2
      )
      return None
      ```
5.  **Refactor/Deprecate `round_to_int`:**
    - Change the method signature to `@property def round_to_int(self) -> None:`.
    - Replace the entire method body with:
      ```python
      """
      DEPRECATED: Use af['col_name'].round(0).cast(pl.Int64) or similar instead.
      This method no longer accepts arguments. Access the proxied methods directly.
      Example: af['my_col'].round(0).cast(pl.Int64)
      """
      warnings.warn(
          "Directly calling af.round_to_int(...) is deprecated. Use proxy methods like af['col'].round(0).cast(pl.Int64) instead.",
          DeprecationWarning,
          stacklevel=2
      )
      return None
      ```
6.  **Refactor/Deprecate `fill_series`:**
    - Change the method signature to `@property def fill_series(self) -> None:`.
    - Replace the entire method body with:
      ```python
      """
      DEPRECATED: Use direct polars expressions like pl.arange(...) instead.
      This method no longer accepts arguments. Construct ranges using standard Polars.
      Example: af['new_col'] = pl.arange(0, pl.count()) # or other Polars range functions
      """
      warnings.warn(
          "Directly calling af.fill_series(...) is deprecated. Use standard Polars functions like pl.arange instead.",
          DeprecationWarning,
          stacklevel=2
      )
      return None
      ```
7.  **Remove Old Imports (Optional but Recommended):** Search for the lines importing the custom functions (`core_floor`, `core_round`, etc.) from `gaspatchio_core.functions` *within* `core.py` and remove them, as they are no longer directly used by the deprecated wrappers.
8.  **Run Tests:** Execute the existing test suite (`tests/test_core.py` and `tests/test_core_delegation.py`). Some tests in `test_core.py` might now fail or issue deprecation warnings because they used the old `af.floor()`, `af.round()` etc. methods. Update these tests to use the new proxy style (`af["col"].floor()`, `af["col"].round(0)`).
```

### Step 3.2: Update Tests to Use New API

**Goal:** Modify existing tests (primarily in `test_core.py`) that used the old `ActuarialFrame` helper methods to use the new proxy-based syntax (`af["col"].method()`).

**File:** `tests/test_core.py` (Modify)

**Test Update Example:**

```python
# (Inside TestModelCalculations in test_core.py)

    def test_simple_model_debug_mode(self):
        def simple_model(df):
            max_age = 100
            df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
            # --- UPDATED CODE ---
            # Old: df["proj_months"] = fill_series(pl.col("age"), 0, 1) # Assuming fill_series was a global function/import
            # New: Requires rethinking how proj_months was created. If it was row-dependent,
            #      it needs a different approach. If it was a simple range based on frame length:
            df["proj_months"] = pl.arange(0, pl.count()) # Example: simple range
            # If it depended on 'age', the original logic needs mapping or a different Polars function.

            # Old: df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1
            # New: Use proxy method
            df["proj_years"] = ((df["proj_months"] - 1) / 12).floor() + 1
            # --- END UPDATED CODE ---
            df["age_last"] = df["age"] + df["proj_years"] - 1
            return df

        df = ActuarialFrame(self.data, mode="debug")
        # Expect deprecation warnings if old methods are still somehow called
        # with warnings.catch_warnings(record=True) as w:
        #     warnings.simplefilter("always")
        result = run_model(simple_model, df).collect()
            # Check w for DeprecationWarning if necessary

        # ... (rest of the test assertions) ...

# (Similarly update test_simple_model_optimize_mode, test_compare_debug_and_optimize_results, etc.)

# Update test_plugin_functions if it used af.floor etc.
    def test_plugin_functions_new_api(self):
        df = ActuarialFrame(self.data, mode="debug")

        # Test floor via proxy
        df["age_floored"] = df["age"].floor() # Simple floor
        # Test floor with divisor (less common, might need custom expr if not directly supported)
        df["age_floored_10"] = (df["age"] / 10).floor() * 10

        result = df.collect()
        for i, age in enumerate(self.data["age"]):
            self.assertEqual(result["age_floored"][i], math.floor(age))
            expected_10 = (age // 10) * 10
            self.assertEqual(result["age_floored_10"][i], expected_10)

```

**LLM Prompt 3.2:**
```text
Modify the file `gaspatchio-core/bindings/python/tests/test_core.py`.

The goal is to replace all usages of the deprecated `ActuarialFrame` helper methods (`af.floor(...)`, `af.round(...)`, `af.round_to_int(...)`, `af.fill_series(...)`) with the new proxy-based syntax (`af['column_name'].floor()`, `af['column_name'].round(...)`, etc.).

1.  **Search and Replace:** Systematically go through the test functions, especially within `TestModelCalculations` and `TestDebugableBasics` (specifically the old `test_plugin_functions`).
2.  **Example Replacements:**
    - Replace `df["age_floored"] = floor(pl.col("age"), 10)` with `df["age_floored_10"] = (df["age"] / 10).floor() * 10`.
    - Replace `df["proj_years"] = floor((pl.col("proj_months") - 1) / 12) + 1` with `df["proj_years"] = ((df["proj_months"] - 1) / 12).floor() + 1`.
    - Replace `df["some_col"] = round(pl.col("other_col"), 2)` with `df["some_col"] = df["other_col"].round(2)`.
    - Replace usages of `fill_series`. This requires careful consideration of what the original `fill_series` did. If it created a simple range (0, 1, 2,...), replace it with `pl.arange(0, pl.count())` or similar Polars functions. If its behavior was dependent on other columns, the logic needs to be translated into appropriate Polars expressions using proxied methods. **Assume for now `fill_series` was creating a simple 0-based index unless context clearly indicates otherwise.** Example: replace `df["proj_months"] = fill_series(pl.col("age"), 0, 1)` with `df["proj_months"] = pl.arange(0, pl.count())`. Adjust assertions accordingly.
3.  **Update Assertions:** Ensure the assertions still match the expected outcomes after using the proxy methods. Floor results might be floats, rounding might change types.
4.  **Rename Tests:** Rename `test_plugin_functions` to `test_plugin_functions_new_api` or similar to reflect the change.
5.  **Run Tests:** Execute the full test suite. Address any failures or deprecation warnings. Failures likely indicate the translation from the old function call to the new proxy method was incorrect. Deprecation warnings should disappear after all replacements are done.
```

### Step 3.3: Final Cleanup and Documentation

**Goal:** Remove the deprecated `ActuarialFrame` helper methods entirely (or leave them raising `NotImplementedError` after a deprecation period). Remove the old custom function imports (`core_floor`, etc.) if no longer needed anywhere. Update docstrings and examples to reflect the new preferred API.

**Files:**
- `gaspatchio_core/dsl/core.py` (Modify)
- Documentation files (e.g., README, usage examples) (Modify)

**LLM Prompt 3.3 (Conceptual - Manual Review Recommended):**
```text
1.  **Modify `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core.py`:**
    - **Remove Deprecated Methods:** Completely delete the deprecated property methods (`floor`, `round`, `round_to_int`, `fill_series`) from the `ActuarialFrame` class.
    - **Remove Unused Imports:** Double-check if the imports `core_fill_series`, `core_floor`, `core_round`, `core_round_to_int` from `gaspatchio_core.functions` are still used *anywhere* in `core.py`. If not, remove these import lines.
    - **Review Proxy Docstrings:** Add or enhance docstrings for `ColumnProxy` and `ExpressionProxy` explaining that they proxy Polars `Expr` methods and namespaces.

2.  **Review and Update Documentation:**
    - **Search Documentation:** Look through project documentation (READMEs, examples, tutorials) for any instances showing the old `af.floor(af["col"])` or similar patterns.
    - **Replace Examples:** Update these examples to use the new `af["col"].floor()` syntax. Emphasize the proxy approach as the standard way.

3.  **Run Full Test Suite:** Ensure all tests still pass after the final removal of deprecated code.
```

---

This plan breaks down the implementation into manageable, testable steps, starting with the core delegation and progressively adding namespaces and the vectorization shim, followed by refactoring and cleanup. Each step includes a specific LLM prompt designed to generate the required code modifications.
