# Polars Delegation & Vector‑Aware Unary Ops – PRD

## 0. Context & Motivation 📝
* We expose `ColumnProxy` / `ExpressionProxy` so model code can call `af["age"] + 1`, etc.
* Pain points today:
  * **Missing delegation** – only a few Polars `Expr` methods have wrappers.
  * **IDE blindness** – editors don't see dynamically added attributes.
  * **Vector pain** – unary numeric ops (`floor`, `ceil`, …) fail on `list[f64]` cols.
  * **API inconsistency** - Some ops are `ActuarialFrame` methods (e.g., `af.floor(col)`), others are proxy methods (`af[col].mean()`).
* Goal: zero‑boiler‑plate method access, better DX, consistent Polars-like API, retire custom Rust plugin for `floor`.

---

## 1. Objectives 🎯

| # | Requirement | Success criteria |
|---|-------------|------------------|
| 1 | Automatic delegation of *most* `pl.Expr` methods & namespaces | `af["age"].skew()`, `af["dt_col"].dt.year()` work after Polars upgrade. |
| 2 | IDE autocompletion & doc‑strings | Hover on `af["age"].mean` matches Polars docs. Explicit patching preferred over `__getattr__`. |
| 3 | Vector‑aware *unary* ops | `af["vec"].floor()` rewrites to list eval and passes tests. Scope clearly defined. |
| 4 | No scalar regression | Existing scalar ops unchanged. Ensure error handling (e.g., `ColumnNotFoundError`) remains effective. |
| 5 | Minimal overhead | Wrapper ≤ 3 % slower than raw Polars. |
| 6 | Consistent API | Existing `ActuarialFrame` helper methods (e.g., `floor`) refactored to use delegated proxy methods. |

---

## 2. High‑Level Design 🏗️

### 2.1 Dynamic wrapper factory
Single `_make_wrapper(name, target)`:

1. Resolve base expr (`pl.col(self.name)` or `self._expr`).
2. Unwrap proxy args.
3. Call Polars method/attribute access (`getattr`).
4. **Vector shim** for unary numeric methods (§2.3).
5. Wrap `pl.Expr` or namespace result back into `ExpressionProxy` or a specific namespace proxy if needed.
6. **Special Handling:** Allow specific methods (e.g., `cast` due to existing list logic) to bypass or augment this factory if their logic is too complex for the generic wrapper.

### 2.2 Import‑time auto‑patch

```python
def _autopatch(proxy_cls):
    # Include common namespaces
    namespaces = ["dt", "str", "list", "arr", "struct", "cat", "bin"]
    # Iterate over Expr attributes AND common namespaces
    processed_attrs = set()
    for attr_name in dir(pl.Expr) + namespaces:
        if attr_name.startswith("_") or attr_name in processed_attrs:
            continue
        try:
            attr = getattr(pl.Expr, attr_name, None) # Check Expr first
            if attr is None and attr_name in namespaces:
                 # Placeholder for namespace logic - may need specific handling
                 # For now, assume _make_wrapper can handle attribute access
                 attr = lambda self: getattr(self._expr, attr_name) # Example
            if callable(attr) or attr_name in namespaces: # Patch methods and known namespaces
                setattr(proxy_cls, attr_name, _make_wrapper(attr_name, attr))
                processed_attrs.add(attr_name)
        except Exception as e:
            print(f"Skipping autopatch for {attr_name}: {e}") # Add logging

```

Executed once for `ColumnProxy` and `ExpressionProxy`. **Prioritize this over `__getattr__` for discoverability.** Proxy `__dir__` methods should be updated to include patched attributes.

### 2.3 Vector shim

```python
_NUMERIC_UNARY = {"floor", "ceil", "round", "abs", "sqrt", "log", "log10", "exp",
                  "sin", "cos", "tan", ...} # Verify list is comprehensive

def _vectorise_if_list(expr, op):
    # Check if expr is likely a List type
    # Using try-except for schema access is safer than direct type check
    try:
        # Check output type without collecting data if possible
        schema = expr.meta.output_type(None) # Use provided schema context if available
        is_list = isinstance(schema, pl.List)
    except pl.ComputeError: # Fallback if schema inference fails without data
        # Cannot reliably determine type, assume not list or log warning
        return expr
    except AttributeError: # Handle cases where meta.output_type isn't available
        return expr

    if is_list and op in _NUMERIC_UNARY:
        # Check interaction with existing list logic (e.g. in manual cast wrapper)
        try:
            # Attempt list evaluation for the specific unary operation
            return expr.list.eval(getattr(pl.element(), op)())
        except Exception as e:
            # Log warning if list eval fails for a known unary op
            print(f"Warning: list.eval failed for {op}: {e}")
            return expr # Return original expression on failure
    # Note: Non-unary operations on lists (e.g., af["list"] + 1) are NOT handled
    # by this shim and rely on standard Polars broadcasting or require manual list.eval.
    return expr
```

Insert after Polars call in wrapper factory. **Scope:** Only applies to *unary* numeric methods listed in `_NUMERIC_UNARY`.

### 2.4 API Consistency & Deprecation
*   Refactor existing `ActuarialFrame` helper methods (e.g., `ActuarialFrame.floor()`) to use the delegated proxy method (`af["col"].floor()`).
*   Deprecate the direct `ActuarialFrame` methods.
*   Deprecate the Rust `floor` plugin, retaining only if essential for exotic divisor/default branch not covered by standard Polars `floor`. Remove after sufficient notice (e.g., 2 releases).
*   If custom functions in `gaspatchio_core.functions` become redundant due to delegation + shim, deprecate them.

---

## 3. Implementation Tasks 🛠️
1. **`dsl/core/_delegation.py`** – implement helpers & refined autopatch (including namespace handling).
2. **Modify proxies** – Implement `_make_wrapper`, strip *most* bespoke wrappers (keep complex ones like `cast` if needed), add safety `__getattr__` as fallback *only*, update `__dir__`.
3. Hook autopatch in `dsl/core/__init__.py`.
4. **Refactor `ActuarialFrame` methods** (e.g., `floor`, `round`) to use delegated proxies.
5. Delete obsolete wrappers/functions after tests pass and deprecation period.
6. Update docs/examples to reflect the preferred proxy-based API.

---

## 4. Reference Code Snippet

```python
import functools, polars as pl

# Verify comprehensive list
_NUMERIC_UNARY = {"floor","ceil","round","abs","sqrt","log","log10","exp",
                  "sin","cos","tan"} # Add more as needed

def _unwrap(arg):
    from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy
    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    return arg

def _wrap(parent, result):
    from gaspatchio_core.dsl.core import ExpressionProxy # Potentially other proxy types needed
    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    # Add handling for namespace objects if needed, returning a wrapped namespace proxy
    # elif isinstance(result, PolarsNamespaceType):
    #     return NamespaceProxy(result, parent)
    return result # Return other types (like scalars) directly

def _vectorise_if_list(expr, op):
    try:
        schema = expr.meta.output_type(None)
        is_list = isinstance(schema, pl.List)
    except (pl.ComputeError, AttributeError):
        return expr
    if is_list and op in _NUMERIC_UNARY:
        try:
            return expr.list.eval(getattr(pl.element(), op)())
        except Exception: # Add logging
             return expr
    return expr

def _make_wrapper(name, target):
    @functools.wraps(target) # target might be None for namespaces initially
    def method(self, *a, **k):
        # Determine base (Column or Expression)
        base = pl.col(self.name) if hasattr(self, "name") else self._expr
        
        # Handle attribute access (methods and namespaces)
        try:
            polars_attr = getattr(base, name)
        except AttributeError:
             raise AttributeError(f"'{type(base).__name__}' object has no attribute '{name}' via proxy")

        if callable(polars_attr):
             # Call the Polars method
             unwrapped_args = [_unwrap(x) for x in a]
             unwrapped_kwargs = {k: _unwrap(v) for k, v in k.items()}
             res = polars_attr(*unwrapped_args, **unwrapped_kwargs)
        else:
             # Assume namespace access or property
             if a or k:
                 raise TypeError(f"Attribute '{name}' accessed as method but is not callable")
             res = polars_attr # Get the namespace object or property value

        # Apply vector shim ONLY to callable methods returning Expr
        if isinstance(res, pl.Expr) and callable(polars_attr):
            res = _vectorise_if_list(res, name)

        # Wrap the result (Expr, namespace, or scalar)
        return _wrap(self._parent, res) # Pass self._parent for context

    # Allow overriding __doc__ later if needed
    # method.__doc__ = getattr(target, "__doc__", f"Proxied Polars attribute: {name}")
    return method

# Example manual override for complex methods (if needed)
# class ExpressionProxy:
#     ...
#     def cast(self, dtype, strict=True):
#         # Custom logic here, possibly calling _make_wrapper internally
#         # or using _unwrap/_wrap directly
#         if _is_list_like(self._expr) and _is_scalar_type(dtype):
#              # Apply list.eval logic
#              pass
#         else:
#              # Standard cast
#              pass
#     ...
```

---

## 5. Testing & Acceptance ✅

### 5.1 Unit tests
*   `assert hasattr(ColumnProxy, "skew")`
*   `assert hasattr(ColumnProxy, "dt")` # Test namespace access
*   `assert "Return the mean" in af["x"].mean.__doc__`
*   **Namespace Functionality:** `af["dt_col"].dt.year().alias("year")` works.
*   **Vector Shim:** Vector `floor`, `abs` etc. correctness on `list[f64]` columns. Verify it *doesn't* trigger for non-list or non-unary ops.
*   **Scalar Path:** Scalar path unchanged.
*   **Complex Methods:** Test manually wrapped methods (e.g., `cast`) thoroughly, including list interactions.
*   **Error Handling:** Verify `ColumnNotFoundError` propagation and formatting.
*   **Autopatch Completeness:** Inject dummy `Expr.foo` → autopatch picks it up. Check a sample of standard Polars methods and namespaces.

### 5.2 IDE smoke test
Hover & autocomplete in VS Code / PyCharm reflects proxied methods/namespaces.

### 5.3 Performance bench
≤ 1.03 × raw Polars for 1 M‑row common operations (e.g., `.abs()`, `.mean()`, `.dt.year()`).

### 5.4 Regression
*   Run existing `model_test.py` in both modes; identical output within tolerance.
*   Verify models using previously refactored `ActuarialFrame` methods now work via proxy methods.

---

## 6. Roll‑out 🚀

1. Guard behind env flag `GASPATCHIO_POLARS_DELEGATE` during development/testing.
2. **Communicate API Change:** Clearly document the shift from `ActuarialFrame.method(col)` to `af[col].method()` as the preferred style.
3. Deprecate redundant `ActuarialFrame` methods, Rust `floor` plugin (if applicable), and custom functions in CHANGELOG; remove after 2 releases.
4. Bump minor version upon release.
