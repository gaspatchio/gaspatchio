# Refactoring Proxy Delegation and Structure (`08-dispatch.md`)

**Goal:** Reintegrate the dynamic method/attribute delegation logic (including the critical list operation shimming for unary functions) into the `ColumnProxy` and `ExpressionProxy` classes within the refactored `gaspatchio_core` structure. Simultaneously, improve modularity by splitting the proxy classes into separate files and centralizing the shared dispatch logic.

**Problem:** The initial refactor (`08-spec.md`) successfully separated major components like the frame, utilities, and errors, but it overlooked the detailed migration of the sophisticated delegation mechanism previously used in `dsl/core.py`. This mechanism, involving `_autopatch`, descriptors, and importantly, the logic to handle operations like `.abs()` on `List` types via `list.eval`, was replaced with a simpler `__getattr__`, leading to failures like `test_vector_shim_unary_ops`.

**Solution:** Reintroduce the descriptor-based `_autopatch` system and the list shimming logic, while also splitting the proxy classes for better organization.

---

## Implementation Plan

**Target File Structure:**

```
gaspatchio_core/
└── column/
    ├── __init__.py         # Exports proxies, applies autopatch
    ├── __init__.pyi
    ├── column_proxy.py     # Contains ColumnProxy class
    ├── column_proxy.pyi
    ├── expression_proxy.py # Contains ExpressionProxy class
    ├── expression_proxy.pyi
    └── dispatch.py         # Contains _autopatch, descriptors, wrappers, shimming logic
    └── dispatch.pyi
```

**Steps:**

### 1. Create `dispatch.py` and Move Shared Logic

*   **Action:** Create `gaspatchio_core/column/dispatch.py`.
*   **Details:**
    *   Move shared delegation components into `dispatch.py`.
    *   Integrate the critical list shimming logic within `_make_wrapper`.
*   **Stub:** Create `dispatch.pyi`.

**LLM Prompt 1:**

```text
Context: We are fixing the delegation logic in `gaspatchio_core.column` which was incompletely refactored. We need to centralize the shared dispatch mechanism, including the critical shim for list operations.

Task:
1.  Create the file `gaspatchio_core/column/dispatch.py`.
2.  Implement the following components within `dispatch.py`, taking logic from the previous implementation (user-provided snippet) or implementing anew:
    *   Constants: `_NUMERIC_UNARY` (set of unary op names like 'abs', 'floor', etc.), `_NAMESPACES` (set of namespace names like 'dt', 'str', 'list').
    *   Helper functions: `_unwrap(arg)` and `_wrap(parent, result)` for converting between proxies and Polars objects.
    *   Descriptor class: `DelegatorDescriptor(name)` which holds the operation name.
    *   Wrapper factory: `_make_wrapper(name)`: This is the core. It should return a callable (`method_caller`) that handles the actual proxy call.
        *   Inside `method_caller`:
            *   Determine the base Polars expression (`inner_base_expr`) and parent frame (`inner_parent_af`) from the proxy `self_proxy`.
            *   **List Shimming Logic:**
                *   Check if `name` is in `_NUMERIC_UNARY` and no positional/keyword args were passed to the proxied call (`*a`, `**kw`).
                *   If so, *safely* attempt to get the `inner_base_expr`'s output type using `inner_base_expr.meta.output_type(inner_parent_af._df.schema if inner_parent_af else None)`. Handle potential `AttributeError` or `pl.ComputeError` gracefully (assume not List if check fails).
                *   If the type *is* `polars.List`, construct the shimmeed expression: `inner_base_expr.list.eval(getattr(pl.element(), name)())`. Set a flag `vectorized = True`.
            *   **Standard Polars Call:** If `vectorized` is `False`, unwrap arguments (`_unwrap(arg) for arg in a`, etc.) and call the corresponding method on the `inner_base_expr` (e.g., `polars_attr(*unwrapped_args, **unwrapped_kwargs)` where `polars_attr = getattr(inner_base_expr, name)`).
            *   Wrap the result (either the shimmeed expression or the standard call result) using `_wrap(inner_parent_af, result)`.
    *   Autopatching function: `_autopatch(proxy_cls)`: This function iterates through attributes of `pl.Expr` and `_NAMESPACES`. For each valid attribute name, it sets an instance of `DelegatorDescriptor(attr_name)` on the `proxy_cls`. It should also add a `__dir__` method to the `proxy_cls` that includes the patched attributes.
3.  Ensure correct imports (`polars`, `functools`, `typing`). Use `TYPE_CHECKING` blocks and forward references (`"ColumnProxy"`, `"ExpressionProxy"`, `"ActuarialFrame"`) where necessary to prevent circular imports at runtime.
4.  Create `gaspatchio_core/column/dispatch.pyi` with accurate type hints for all public/internal functions and classes in `dispatch.py`. Pay close attention to callables and generic types.

Goal: Centralize the dispatch logic, including constants, helpers, the descriptor, the wrapper factory (with list shimming), and the autopatcher, into `dispatch.py` with corresponding stubs.
```

### 2. Create `column_proxy.py`

*   **Action:** Create `gaspatchio_core/column/column_proxy.py`.
*   **Details:** Move `ColumnProxy` class, remove old `__getattr__`/`__dir__`.
*   **Stub:** Create `column_proxy.pyi`.

**LLM Prompt 2:**

```text
Context: The core dispatch logic is now centralized in `gaspatchio_core/column/dispatch.py`. We will now isolate the `ColumnProxy` class definition.

Task:
1.  Create the file `gaspatchio_core/column/column_proxy.py`.
2.  Move the complete `ColumnProxy` class definition from its current location (likely `gaspatchio_core/column/proxy.py`) into this new file.
3.  **Critically:** Remove the `__getattr__` and `__dir__` methods from the `ColumnProxy` class definition. These will be implicitly handled by the `_autopatch` function applied later in `__init__.py`.
4.  Keep the other essential methods and properties: `__init__`, `_to_expr`, `__repr__`, operator overloads (`__add__`, `__eq__`, etc.), the `apply` method, and any explicitly defined accessor properties (like `@property def date(...)`).
5.  Review and update imports within `column_proxy.py`. Ensure it imports necessary types like `ActuarialFrame` (likely using `TYPE_CHECKING` or `from ..frame.base import ActuarialFrame`) and potentially accessor types for property hints. Use forward references (`"ExpressionProxy"`) for types defined in other proxy files.
6.  Create `gaspatchio_core/column/column_proxy.pyi`. This stub file should:
    *   Declare the `ColumnProxy` class.
    *   Include type hints for `__init__`, `_to_expr`, `__repr__`, `apply`.
    *   Include *all* operator overload signatures (e.g., `def __add__(self, other: Any) -> ExpressionProxy:`).
    *   Explicitly declare known built-in accessor properties (e.g., `date: DateColumnAccessor`, `finance: FinanceColumnAccessor`). Import these accessor types.
    *   Explicitly declare signatures for *commonly used* Polars methods that will be added by `_autopatch` (e.g., `alias(self, name: str) -> ExpressionProxy: ...`, `cast(self, dtype: pl.DataType, strict: bool = True) -> ExpressionProxy: ...`, `sum(self) -> ExpressionProxy: ...`, `mean(self) -> ExpressionProxy: ...`). This improves static analysis.

Goal: Isolate the `ColumnProxy` class definition into its own file, remove the old delegation methods, and create a comprehensive stub file declaring core methods, operators, known accessors, and common proxied methods.
```

### 3. Create `expression_proxy.py`

*   **Action:** Create `gaspatchio_core/column/expression_proxy.py`.
*   **Details:** Move `ExpressionProxy` class, remove old `__getattr__`/`__dir__`.
*   **Stub:** Create `expression_proxy.pyi`.

**LLM Prompt 3:**

```text
Context: The core dispatch logic is in `dispatch.py` and `ColumnProxy` is in `column_proxy.py`. Now, isolate the `ExpressionProxy` class.

Task:
1.  Create the file `gaspatchio_core/column/expression_proxy.py`.
2.  Move the complete `ExpressionProxy` class definition from its current location (likely `gaspatchio_core/column/proxy.py`) into this new file.
3.  **Critically:** Remove the `__getattr__` and `__dir__` methods from the `ExpressionProxy` class definition.
4.  Keep the other essential methods: `__init__`, `_to_expr`, `__repr__`, and operator overloads.
5.  Review and update imports within `expression_proxy.py`, using `TYPE_CHECKING` or forward references (`"ColumnProxy"`, `"ActuarialFrame"`) as needed.
6.  Create `gaspatchio_core/column/expression_proxy.pyi`. This stub file should:
    *   Declare the `ExpressionProxy` class.
    *   Include type hints for `__init__`, `_to_expr`, `__repr__`.
    *   Include *all* operator overload signatures (e.g., `def __add__(self, other: Any) -> ExpressionProxy:`).
    *   Explicitly declare known built-in accessor properties (e.g., `date: DateColumnAccessor`).
    *   Explicitly declare signatures for *commonly used* Polars methods/namespaces added by `_autopatch` (e.g., `alias(...)`, `cast(...)`, `sum()`, `mean()`, `dt() -> ExprDT`, `str() -> ExprString`, `list() -> ExprList`). This helps static analysis.

Goal: Isolate the `ExpressionProxy` class definition, remove old delegation methods, and create a comprehensive stub file mirroring the structure for `ColumnProxy`.
```

### 4. Update `column/__init__.py`

*   **Action:** Modify `gaspatchio_core/column/__init__.py`.
*   **Details:** Import proxies and apply `_autopatch`.
*   **Stub:** Update `column/__init__.pyi`.

**LLM Prompt 4:**

```text
Context: The dispatch logic and proxy classes (`ColumnProxy`, `ExpressionProxy`) are now in separate files within `gaspatchio_core/column/`. We need to connect them in the submodule's `__init__.py`.

Task:
1.  Modify `gaspatchio_core/column/__init__.py`:
    *   Clear any previous content related to the old `proxy.py`.
    *   Import `ColumnProxy` from `.column_proxy`.
    *   Import `ExpressionProxy` from `.expression_proxy`.
    *   Import `_autopatch` from `.dispatch`.
    *   **Apply Autopatching:** Add the following lines *after* the class imports:
        ```python
        _autopatch(ColumnProxy)
        _autopatch(ExpressionProxy)
        ```
    *   Define the public API for this submodule: `__all__ = ["ColumnProxy", "ExpressionProxy"]`.
2.  Modify `gaspatchio_core/column/__init__.pyi`:
    *   Ensure it correctly declares the re-exported `ColumnProxy` and `ExpressionProxy` by importing them from their respective modules (`.column_proxy`, `.expression_proxy`).

Goal: Connect the components within the `column` submodule, apply the dynamic method patching, define the submodule's public API, and update the corresponding stub file.
```

### 5. Delete Old `proxy.py`

*   **Action:** Delete the now-empty `gaspatchio_core/column/proxy.py` file (and its corresponding `.pyi` file).

**LLM Prompt 5:**

```text
Context: `ColumnProxy` and `ExpressionProxy` have been moved to their own files, and the dispatch logic is in `dispatch.py`. The old combined file `proxy.py` is no longer needed.

Task:
1.  Delete the file `gaspatchio-core/bindings/python/gaspatchio_core/column/proxy.py`.
2.  Delete the corresponding stub file `gaspatchio-core/bindings/python/gaspatchio_core/column/proxy.pyi`.

Goal: Remove the obsolete combined proxy file.
```

### 6. Testing Strategy

*   **Update Existing:** Modify tests in `tests/column/` to import from `gaspatchio_core.column`.
*   **New Tests:** Create `tests/column/test_dispatch.py` (or similar) for detailed verification of `_autopatch` and the list shimming logic.
*   **Integration Test:** Ensure `test_vector_shim_unary_ops` passes.
*   **CI:** Ensure `mypy` and `stubtest` pass.

**LLM Prompt 6:**

```text
Context: The refactoring of the proxy and dispatch logic is structurally complete. Now, we must ensure thorough testing.

Task:
1.  **Update Existing Tests:** Review files in `tests/column/` (e.g., `test_proxy.py` if it exists). Update any imports of `ColumnProxy` or `ExpressionProxy` to come from the public submodule API: `from gaspatchio_core.column import ColumnProxy, ExpressionProxy`.
2.  **Create New Dispatch Tests:** Create a new file, e.g., `tests/column/test_dispatch.py` (or add to an existing relevant file like `test_proxy.py`). Write comprehensive tests specifically targeting the dynamic delegation and shimming:
    *   **Setup:** Use a fixture or helper to create a sample `ActuarialFrame` with diverse column types (scalar int/float, list int/float, date, string).
    *   **Standard Delegation:** Verify common Polars methods work correctly via the proxy (e.g., `af['int_col'].sum()._expr` produces `pl.col('int_col').sum()`, `af['float_col'].mean()`).
    *   **Namespace Delegation:** Verify access to and methods within namespaces work (e.g., `af['date_col'].dt.year()`, `af['str_col'].str.contains('x')`, `af['list_col'].list.len()`).
    *   **List Shimming (Unary Ops):**
        *   Test methods from `_NUMERIC_UNARY` on a *list* column (e.g., `af['list_int'].abs()`). Assert that the resulting `_expr` involves `list.eval(pl.element().abs())`.
        *   Test methods from `_NUMERIC_UNARY` on a *scalar* column (e.g., `af['scalar_int'].abs()`). Assert the result is the standard Polars expression (`pl.col('scalar_int').abs()`).
        *   Test methods *not* in `_NUMERIC_UNARY` on a list column (e.g., `af['list_int'].sum()`). Assert it does *not* use the `list.eval` shim.
    *   **Operators:** Briefly verify standard operators still work (`af['a'] + af['b']`).
    *   **Error Handling:** Test that accessing a non-existent attribute raises an `AttributeError`.
    *   **`__dir__`:** Test that `dir(af['some_col'])` and `dir(af['some_col'] + 1)` include expected proxied method names (like 'sum', 'mean', 'dt', 'str', 'list').
3.  **Run Integration Test:** Execute `pytest tests/test_core_delegation.py::test_vector_shim_unary_ops`. Ensure this specific test now PASSES.
4.  **Run Full Suite & CI Checks:** Run the complete test suite (`uv run pytest`). Run `mypy --strict gaspatchio_core tests` and `stubtest gaspatchio_core` locally to catch issues early. Fix any reported errors.

Goal: Implement comprehensive tests covering standard delegation, namespace access, the crucial list shimming logic (positive and negative cases), error conditions, and ensure the original failing integration test passes, along with static analysis checks.
```

---

**Conclusion:** This plan reintegrates the necessary dynamic delegation and list operation shimming logic by centralizing it in `dispatch.py` and applying it via `_autopatch`. It also improves code organization by splitting `ColumnProxy` and `ExpressionProxy` into their own files. This should restore the intended functionality and fix the observed test failures related to list operations, validated by thorough testing.
