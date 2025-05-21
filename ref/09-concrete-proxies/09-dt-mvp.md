# MVP Plan: `{NamespaceName}NamespaceProxy` Implementation

This document outlines a step-by-step plan for implementing a `{NamespaceName}NamespaceProxy` (e.g., `DtNamespaceProxy`, `StrNamespaceProxy`) as an MVP (Minimum Viable Product). The goal is to enhance IDE intellisense and type safety for {namespace_description} operations (e.g., datetime, string) within `ActuarialFrame` while preserving existing functionality, including relevant shimming for vector operations (like list shimming for `dt` or `str` methods on list columns) and a dynamic fallback for methods not explicitly proxied.

## Guiding Principles (from gs-spec-draft)

*   **Iterative Chunks:** Break down the work into manageable, self-contained chunks.
*   **Small Steps:** Each chunk consists of small, incremental steps.
*   **Test-Driven:** Prioritize testing at each step (unit tests, integration tests, doctests, static analysis checks).
*   **Incremental Progress:** Each step should build upon the previous one.
*   **Early Testing & Validation:** Ensure no big jumps in complexity without validation.
*   **Best Practices:** Adhere to good coding standards and design.

## Target Files

*   `gaspatchio_core/column/namespaces/{namespace_name}_proxy.py`: **New file** for the implementation of `{NamespaceName}NamespaceProxy`.
*   `gaspatchio_core/column/dispatch.py`: Integration of `{NamespaceName}NamespaceProxy` (will import from `namespaces/{namespace_name}_proxy.py`).
*   `gaspatchio_core/column/proxy.pyi`: Type stubs for `{NamespaceName}NamespaceProxy` and updates to existing proxy stubs. (Alternatively, `namespaces/{namespace_name}_proxy.pyi` could be considered).

## MVP Chunks and Steps

---

### Chunk 1: Basic `{NamespaceName}NamespaceProxy` Structure and Core Logic

**Objective:** Establish the fundamental `{NamespaceName}NamespaceProxy` class in its own file (`namespaces/{namespace_name}_proxy.py`) and its core method-calling logic (initially without specific shimming, if applicable).

*   **Step 1.1: Define `{NamespaceName}NamespaceProxy` Class Shell in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   Create a **new file**: `gaspatchio_core/column/namespaces/{namespace_name}_proxy.py`.
        *   In `namespaces/{namespace_name}_proxy.py`, create the `{NamespaceName}NamespaceProxy` class.
        *   Implement `__init__(self, parent_proxy: "ProxyType", parent_af: Optional["ActuarialFrame"])` to store `parent_proxy` and `parent_af`.
        *   Add a private helper method `_get_base_expr(self) -> pl.Expr` to retrieve the underlying Polars expression from `self._parent_proxy` (handling both `ColumnProxy` and `ExpressionProxy`).
        *   Ensure necessary imports in `namespaces/{namespace_name}_proxy.py` (e.g., `typing.Optional, typing.Any, typing.TYPE_CHECKING`, `polars as pl`). It will also need `ExpressionProxy`, `ColumnProxy` (likely via `if TYPE_CHECKING:` block or careful relative imports from `..expression_proxy` and `..column_proxy`), and utilities like `_unwrap` and `_wrap` (which might need to be imported from `dispatch.py` or a shared util file).
    *   **Testing:**
        *   Write a simple unit test to instantiate `{NamespaceName}NamespaceProxy` from `namespaces/{namespace_name}_proxy.py`.

*   **Step 1.2: Implement `_call_{namespace_name}_method` (Initial Scalar Version) in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   In `{NamespaceName}NamespaceProxy` (in `namespaces/{namespace_name}_proxy.py`), implement `_call_{namespace_name}_method(self, method_name: str, *args: Any, **kwargs: Any) -> "ExpressionProxy"`.
        *   Inside, get `base_expr` using `_get_base_expr()`.
        *   Unwrap arguments (e.g., `from ..dispatch import _unwrap`).
        *   Access the Polars `{namespace_name}` namespace: `polars_namespace = getattr(base_expr, "{namespace_name}")`.
        *   Get the actual Polars method: `actual_polars_method = getattr(polars_namespace, method_name)`.
        *   Call the Polars method.
        *   Wrap the `result_expr` (e.g., `from ..dispatch import _wrap`).
        *   Add basic `try...except AttributeError`.
    *   **Testing:**
        *   Unit test `_call_{namespace_name}_method` in `namespaces/{namespace_name}_proxy.py`.

*   **Step 1.3: Add One Explicit Method (e.g., a common one for the namespace) to `{NamespaceName}NamespaceProxy` in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   In `{NamespaceName}NamespaceProxy` (in `namespaces/{namespace_name}_proxy.py`), define an explicit method (e.g., `year()` for `dt`, `contains()` for `str`).
        *   `def example_method(self, *args, **kwargs) -> "ExpressionProxy": return self._call_{namespace_name}_method("example_method", *args, **kwargs)`.
    *   **Testing:**
        *   Unit test the explicit method in `namespaces/{namespace_name}_proxy.py`.

---

### Chunk 2: Integrating `{NamespaceName}NamespaceProxy` and Basic Type Stubs

**Objective:** Wire `{NamespaceName}NamespaceProxy` (from `namespaces/{namespace_name}_proxy.py`) into the main dispatch mechanism in `dispatch.py` and provide initial type stubs.

*   **Step 2.1: Modify `DelegatorDescriptor` and `_make_wrapper` in `dispatch.py`**
    *   **Action:**
        *   In `gaspatchio_core/column/dispatch.py`, **add import**: `from .namespaces.{namespace_name}_proxy import {NamespaceName}NamespaceProxy`.
        *   In `DelegatorDescriptor.__get__`, add/update condition: if `instance is not None and self.name == "{namespace_name}"`, instantiate and return `{NamespaceName}NamespaceProxy(...)` (imported from `namespaces/{namespace_name}_proxy.py`).
        *   In `_make_wrapper`, ensure the namespace handling correctly excludes this `{namespace_name}` if it now has a dedicated proxy, or adjust logic as needed.
    *   **Testing:**
        *   Integration test using `ActuarialFrame`: Access `af["some_col"].{namespace_name}` (should be `{NamespaceName}NamespaceProxy` from `namespaces/{namespace_name}_proxy.py`), call an explicit or dynamic method.

*   **Step 2.2: Create Basic `{NamespaceName}NamespaceProxy` Stub in `proxy.pyi`**
    *   **Action:**
        *   In `gaspatchio_core/column/proxy.pyi`, define/update the class stub for `{NamespaceName}NamespaceProxy`.
        *   Ensure the stub correctly refers to the class now in `namespaces/{namespace_name}_proxy.py`.
        *   Add `__init__` and stubs for any explicit methods.
        *   In `_BaseProxy` stub, change the `{namespace_name}` property return type to `-> "{NamespaceName}NamespaceProxy": ...`.
    *   **Testing:**
        *   IDE inspection for intellisense. Static analysis (Mypy/Pyright).

---

### Chunk 3: Implementing Specific Shimming for Vector Operations (If Applicable)

**Objective:** Ensure that `{namespace_name}` operations in `{NamespaceName}NamespaceProxy` (from `namespaces/{namespace_name}_proxy.py`) correctly apply element-wise or handle specific shimming needs (e.g., list shimming for `dt` on `List[Date]`, or for `str` methods on `List[String]`). This chunk might be more or less complex depending on the namespace.

*   **Step 3.1: Implement Helper for Shimming Condition (e.g., `_is_list_of_relevant_type`) in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   In `{NamespaceName}NamespaceProxy` (in `namespaces/{namespace_name}_proxy.py`), define a helper like `_is_list_of_relevant_type(self) -> bool` if shimming is type-dependent.
        *   Ensure all necessary type imports are correctly handled within `namespaces/{namespace_name}_proxy.py`.
        *   Implement logic specific to the namespace (e.g., for `dt`, check for `List[Temporal]`; for `str`, check for `List[String]`).
    *   **Testing:**
        *   Unit test the helper method in `namespaces/{namespace_name}_proxy.py`.

*   **Step 3.2: Enhance `_call_{namespace_name}_method` with Shimming Logic in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   Modify `_call_{namespace_name}_method` in `{NamespaceName}NamespaceProxy` (in `namespaces/{namespace_name}_proxy.py`) to include shimming logic relevant to the namespace.
        *   Example for list shimming: `base_expr.list.eval(getattr(pl.element(), "{namespace_name}").{method_name}(...))`.
    *   **Testing:**
        *   Integration tests with `ActuarialFrame` for relevant list and scalar column types.

---

### Chunk 4: Implementing Dynamic Fallback and Expanding Coverage

**Objective:** Allow `{NamespaceName}NamespaceProxy` (from `namespaces/{namespace_name}_proxy.py`) to handle any Polars `{namespace_name}` method dynamically and expand type stubs.

*   **Step 4.1: Implement `__getattr__` Fallback in `{NamespaceName}NamespaceProxy` (`namespaces/{namespace_name}_proxy.py`)**
    *   **Action:**
        *   In `{NamespaceName}NamespaceProxy` (in `namespaces/{namespace_name}_proxy.py`), define `__getattr__(self, name: str) -> Callable[..., "ExpressionProxy"]`.
        *   Implement as previously described, ensuring `functools.wraps` and `_call_{namespace_name}_method` are used.
    *   **Testing:**
        *   Integration test with less common `{namespace_name}` methods on relevant column types.

*   **Step 4.2: Add More Explicit Methods in `namespaces/{namespace_name}_proxy.py` and Stubs to `proxy.pyi`**
    *   **Action:**
        *   In `namespaces/{namespace_name}_proxy.py`, add more common `{namespace_name}` methods explicitly to `{NamespaceName}NamespaceProxy`.
        *   In `proxy.pyi`, add corresponding stubs to `{NamespaceName}NamespaceProxy` stub, and the `__getattr__` stub.
    *   **Testing:**
        *   IDE intellisense. Static analysis. Functional tests.

---

### Chunk 5: Doctests and Final Refinements

**Objective:** Ensure documentation is robust, examples are verifiable, and polish the `{NamespaceName}NamespaceProxy` in `namespaces/{namespace_name}_proxy.py`.

*   **Step 5.1: Add Doctests and Docstrings to `{NamespaceName}NamespaceProxy` Methods in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   Write comprehensive docstrings for the `{NamespaceName}NamespaceProxy` class itself and for all its explicitly defined methods within `gaspatchio_core/column/namespaces/{namespace_name}_proxy.py`.
        *   Embed doctests directly within these docstrings in the `.py` file to serve as examples and ensure they are verifiable.
        *   Ensure that `__init__`, `_get_base_expr`, `_call_{namespace_name}_method`, `__getattr__` (if applicable to the namespace), and any shimming helper methods (e.g., `_is_list_of_relevant_type`) also have clear docstrings explaining their purpose, arguments, and behavior, even if they don't have doctests.
    *   **Testing:**
        *   Run `uv run pytest --doctest-modules gaspatchio_core/column/namespaces/{namespace_name}_proxy.py`.
        *   Manually review generated documentation if a documentation builder is used.

*   **Step 5.2: Review and Refine Error Messages and Overall Code in `namespaces/{namespace_name}_proxy.py`**
    *   **Action:**
        *   Review all error messages raised by `{NamespaceName}NamespaceProxy` in `namespaces/{namespace_name}_proxy.py` for clarity, accuracy, and helpfulness.
        *   Perform a final review of the overall code structure, comments, and logic in `namespaces/{namespace_name}_proxy.py` for adherence to best practices and project conventions.
    *   **Testing:**
        *   Manually trigger error conditions to check messages. Code review.

---

This plan provides a structured approach to developing the `{NamespaceName}NamespaceProxy` MVP. Each step is designed to be relatively small and verifiable, reducing risk and allowing for continuous integration and testing.
Placeholders like `{NamespaceName}`, `{namespace_name}`, and `{namespace_description}` should be replaced with specific values when implementing a proxy for a particular namespace (e.g., `Dt`, `dt`, `datetime` or `Str`, `str`, `string`).
