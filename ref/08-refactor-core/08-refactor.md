# Gaspatchio‑Core Refactor Plan

This document is a self‑contained blueprint for splitting `core.py` into a clean, scalable package **and** shipping first‑class `.pyi` stubs with rich documentation—without bloating runtime size or import time, using collocated stub files.

---

## Table of Contents
1. [Target Package Layout](#1-target-package-layout)
2. [Carving Up *core.py*](#2-carving-up-corepy)
3. [Accessor & Namespace Plumbing](#3-accessor--namespace-plumbing)
4. [Shipping Rich `.pyi` Stubs via Collocation](#4-shipping-rich-pyi-stubs-via-collocation)
5. [Incremental Migration Path](#5-incremental-migration-path)
6. [Testing & Continuous Integration](#6-testing--continuous-integration)
7. [Future‑Proofing Notes](#7-futureproofing-notes)
8. [Deliverables Checklist](#8-deliverables-checklist)

---

## 1. Target Package Layout

```text
└── python
    ├── Cargo.lock
    ├── Cargo.toml
    ├── gaspatchio_core
        ├── __init__.py                # Re‑export public surface
        ├── __init__.pyi               # Stub for __init__.py
        ├── py.typed                   # PEP 561 marker file
        ├── frame/                     # Frame‑level concerns
        │   ├── __init__.py
        │   ├── __init__.pyi
        │   ├── base.py                # ActuarialFrame + ExecutionContext
        │   ├── base.pyi
        │   ├── tracing.py             # Tracer / computation‑graph helpers
        │   ├── tracing.pyi
        │   └── registry.py            # Accessor registration + plugin discovery
        │   └── registry.pyi
        ├── column/
        │   ├── __init__.py
        │   ├── __init__.pyi
        │   └── proxy.py               # ColumnProxy / ExpressionProxy
        │   └── proxy.pyi
        ├── accessors/
        │   ├── __init__.py            # Auto‑register built‑ins
        │   ├── __init__.pyi
        │   ├── date.py                # DateFrameAccessor / DateColumnAccessor
        │   ├── date.pyi
        │   ├── finance.py             # FinanceFrameAccessor / FinanceColumnAccessor
        │   ├── finance.pyi
        │   └── … (mortality, stats, etc.)
        ├── functions/                 # Wrappers for Rust core functions
        │   ├── __init__.py
        │   ├── __init__.pyi
        │   └── vector.py              # Mirrors core/src/polars_functions/vector.rs
        │   └── vector.pyi
        ├── errors/                    # Custom error handling/formatting
        │   ├── __init__.py
        │   ├── __init__.pyi
        │   └── formatting_errors.py   # Enhanced error message generation
        │   └── formatting_errors.pyi
        ├── plugins/                   # Optional built‑in plugins
        │   └── __init__.py
        │   └── __init__.pyi
        └── util/                      # Logging, typing helpers, misc utilities
            ├── __init__.py
            └── __init__.pyi
```

*Mirrors the multi‑layer architecture already outlined in `layout.md` and the accessor spec.*
*Includes dedicated `functions/` mirroring Rust source and `errors/` for specific handling.*
*Uses collocated `.pyi` stubs alongside `.py` implementation files (see §4).*

---

## 2. Carving Up *core.py*

| Responsibility in `core.py`                        | New Home                   | Notes |
|----------------------------------------------------|----------------------------|-------|
| `ActuarialFrame`, global mode flags                | `frame/base.py`            | Keep strictly frame‑level logic. |
| `ColumnProxy`, `ExpressionProxy` magic             | `column/proxy.py`          | Only column operations & operator overloads. |
| Tracing / computation‑graph capture                | `frame/tracing.py`         | Imported privately by `frame.base`. |
| Accessor registration decorators, plugin discovery | `frame/registry.py`        | Pure infra; no business logic. |
| Built‑in accessor classes                          | `accessors/*.py`           | One file per domain keeps growth isolated. |
| Wrapper functions for Rust core                    | `functions/*.py`           | Mirrors Rust structure (e.g., `vector.py`). |
| Error handling / formatting logic                  | `errors/formatting_errors.py`| Centralizes helpful error message generation. |
| Helper utilities / logging                         | `util/__init__.py`         | Thin wrappers only. |

> **Tip** – Create **façade modules** first, re‑exporting old names, then move code line‑for‑line to keep the build green throughout the refactor.

---

## 3. Accessor & Namespace Plumbing

### 3.1 Registry Skeleton

```python
# frame/registry.py
_ACCESSOR_REGISTRY: dict[str, tuple[type, str]] = {}

def register_accessor(name: str, *, kind: str = "column"):
    def decorator(cls):
        if name in _ACCESSOR_REGISTRY:
            raise ValueError(f"Accessor {name!r} already registered")
        _ACCESSOR_REGISTRY[name] = (cls, kind)
        return cls
    return decorator
```

* `ActuarialFrame.__getattr__` and `ColumnProxy.__getattr__` consult the registry to attach namespaces at runtime—mirroring Polars' approach.*

### 3.2 Example Accessor

```python
# accessors/date.py
from ..frame.registry import register_accessor

@register_accessor("date", kind="frame")
class DateFrameAccessor:
    """Frame-level date operations.""" # Short docstring
    def __init__(self, frame): self._f = frame
    def create_timeline(self, start_col: str, end_col: str, freq="M"):
        ...

@register_accessor("date", kind="column")
class DateColumnAccessor:
    """Column-level date operations.""" # Short docstring
    def __init__(self, col): self._c = col
    def from_excel_serial(self, epoch: str="1900"):
        ...
```

---

## 4. Shipping Rich `.pyi` Stubs via Collocation

We will use collocated `.pyi` stub files, placed directly next to their corresponding `.py` implementation files, to provide rich type hints and documentation without cluttering the runtime code or requiring a separate `‑stubs` package.

### 4.1 Rationale for Collocation

| Need                               | Collocated `.pyi` Stubs Solve It                                                              |
| :--------------------------------- | :-------------------------------------------------------------------------------------------- |
| **Override sparse Polars hints**   | Stub holds a precise `pl.Expr → pl.Expr` signature + narrative docs, even if upstream is `Any`. |
| **LLM / IDE‑ready docs**           | Pyright, Pylance, mypy load the sibling `.pyi` first → hover help & AI tools see full context.  |
| **One‑wheel simplicity**           | No separate `‑stubs` package; `pip install gaspatchio‑core` is all that's needed.             |
| **Compatible everywhere**          | PEP 561 + `py.typed` = works out‑of‑the‑box in mypy, Pyright, PyCharm, etc.                  |
| **Future Rust kernels**            | PyO3 can emit `.pyi` next to compiled `*.so` (like Polars, orjson), fitting this pattern.      |

*This approach keeps the runtime lean while maximizing discoverability for developers and tooling.*

### 4.2 Documentation Strategy

*   **`.pyi` Files (Primary Docs Source):**
    *   Contain detailed type hints (refined beyond basic `stubgen` output).
    *   Hold comprehensive prose documentation (purpose, parameters, returns, usage notes, examples).
    *   Serve as the input for API documentation generation (e.g., Sphinx `autodoc_typehints = "both"`) and potential RAG ingestion.
*   **`.py` Files (Implementation):**
    *   Contain the actual runtime logic.
    *   Docstrings are kept minimal (e.g., a one-liner and maybe a link to online docs) to reduce package size and import time.
    *   Testable examples (`doctest` or `pytest-examples`) can live here if needed, but detailed explanations belong in the `.pyi`.

### 4.3 Implementation Steps

1.  **Add `py.typed` Marker File:** Place an **empty** `py.typed` file at the root of the `gaspatchio_core` package (`gaspatchio_core/py.typed`). This signals to PEP 561 compliant type checkers (Mypy, Pyright) that the package provides its own inline type information via `.pyi` files.
2.  **Generate & Refine Stubs:**
    *   Use `stubgen` (part of `mypy`) to generate initial `.pyi` files alongside the `.py` files during development or release.
    *   Manually edit the generated `.pyi` files to:
        *   Refine `Any` types to be more specific.
        *   Add detailed docstrings, parameter descriptions, and examples.
        *   Add signatures for dynamically generated methods (like those from Polars delegation) that `stubgen` might miss.
3.  **Configure CI Guards:** Implement checks to prevent drift between implementation and stubs (see §4.4).

### 4.4 CI Guards & Trade-offs

| Drawback                 | Mitigation                                                                      |
| :----------------------- | :------------------------------------------------------------------------------ |
| **Stub Drift**           | Add `mypy --strict` and `stubtest gaspatchio_core` to CI; fail build on mismatch. |
| **Wheel Size Increase**  | Keep runtime `.py` docstrings minimal; detailed docs live only in `.pyi`.         |
| **Dual‑Edit Burden**     | Use `stubgen` for baseline generation; focus manual edits on docstrings/types.    |
| **Runtime `help()` Thin** | Minimal `.py` docstring can link to full online/HTML documentation.              |

*   **Additional CI Checks:**
    *   **Wheel‑Size / Import Time Audit**: Fail CI if wheel size or estimated import time exceeds a defined threshold.
    *   **Docs Build**: Configure Sphinx (or other doc generator) to build documentation primarily from the `.pyi` files, leveraging the detailed docstrings there (`autodoc_typehints = "both"` or similar).

---

## 5. Incremental Migration Path

| Step | Action                                                                       | Safe‑Guard                                                                 |
| :--- | :--------------------------------------------------------------------------- | :------------------------------------------------------------------------- |
| 1    | Create new package skeleton (`frame/`, `column/`, etc.); add `py.typed`; add façade re‑exports in `gaspatchio_core/__init__.py`. | Tests import old symbols unchanged via `__init__.py`.                  |
| 2    | Move *stateless* helpers/util and error formatting logic first.              | No major side‑effects. Update imports. Create corresponding `.pyi` stubs. |
| 3    | Split `ColumnProxy` & `ExpressionProxy` into `column/`.                       | Leave shim in old location emitting deprecation warning, update imports. Create `.pyi`. |
| 4    | Move registry + decorators; wire into frame & column.                        | Unit test: registering dummy accessor yields `af.dummy.*`. Create `.pyi`. |
| 5    | Extract accessor modules one‑by‑one into `accessors/`.                       | Each move accompanied by `.pyi` stub + detailed docs.                      |
| 6    | Move core function wrappers into `functions/`.                               | Update imports. Create `.pyi`.                                             |
| 7    | Delete legacy code from `core.py`; remove façade re-exports eventually.       | CI ensures everything imports from new paths. Delete `core.pyi`.           |
| 8    | Enable `mypy --strict` and `stubtest` over runtime *and* stubs.              | Ensures type safety and stub/runtime parity.                               |

---

## 6. Testing & Continuous Integration

*Import safety, performance, and type coverage stay intact throughout.*

*   **Path-Agnostic Tests**: Ensure tests import only from the public API (e.g., `from gaspatchio_core import ActuarialFrame, functions`).
*   **Stub Parity Check (`stubtest`)**: Implement `stubtest gaspatchio_core` as a CI step to verify that signatures in `.pyi` stubs accurately match the runtime `.py` implementation.
*   **Docstring Example Testing (Future)**: Plan for integrating `pytest-examples` or similar to run code snippets found in *`.pyi`* docstrings (or linked files), ensuring examples stay correct.
*   **Linting & Formatting**: Use Ruff/Black to enforce style consistency in both `.py` and `.pyi` files.
*   **Type Checking (`mypy --strict`)**: Run `mypy` on the runtime code. Since `py.typed` is present, `mypy` will automatically use the collocated `.pyi` files for checking.
*   **Benchmark Guardrails**: Assert refactor does **not** negatively impact performance beyond an acceptable tolerance.

---

## 7. Future‑Proofing Notes

* **Plugin Auto‑Discovery**: Consider `importlib.metadata.entry_points('gaspatchio_core.accessors')` for third-party accessor registration.
* **External Stubs**: Encourage third‑party plugin authors to ship their own `py.typed` and `.pyi` files.
* **Docs Generation**: With separated accessors and stubs, Sphinx can generate cleaner, more focused documentation pages per namespace/module.

---

## 8. Deliverables Checklist

- [ ] New directory skeleton committed (`frame`, `column`, `accessors`, `functions`, `errors`, `util`) with initial `__init__.py` / `.pyi` pairs.
- [ ] `py.typed` file added to `gaspatchio_core/`.
- [ ] Core logic from `core.py` moved to respective submodules.
- [ ] Collocated `.pyi` stubs created for all public modules/symbols.
- [ ] `.pyi` stubs contain detailed type hints and documentation.
- [ ] Runtime `.py` docstrings are minimal.
- [ ] `ActuarialFrame` and `ColumnProxy` correctly use the accessor registry.
- [ ] CI pipeline includes `mypy --strict` check.
- [ ] CI pipeline includes `stubtest gaspatchio_core` check.
- [ ] CI pipeline includes wheel size/import time audit (optional but recommended).
- [ ] Documentation build process configured to use `.pyi` docstrings.
- [ ] Legacy `core.py` removed or reduced to minimal shims/exports.