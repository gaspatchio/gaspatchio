# Gaspatchio‑Core Refactor Plan

This document is a self‑contained blueprint for splitting `core.py` into a clean, scalable package **and** shipping first‑class `.pyi` stubs with rich documentation—without bloating runtime size or import time.

---

## Table of Contents
1. [Target Package Layout](#1-target-package-layout)
2. [Carving Up *core.py*](#2-carving-up-corepy)
3. [Accessor & Namespace Plumbing](#3-accessor--namespace-plumbing)
4. [Shipping Rich `.pyi` Stubs Without Code Bloat](#4-shipping-rich-pyi-stubs-without-code-bloat)
5. [Incremental Migration Path](#5-incremental-migration-path)
6. [Testing & Continuous Integration](#6-testing--continuous-integration)
7. [Future‑Proofing Notes](#7-futureproofing-notes)
8. [Deliverables Checklist](#8-deliverables-checklist)

---

## 1. Target Package Layout

```text
gaspatchio_core/
├── __init__.py                # Re‑export public surface
├── py.typed                   # PEP 561 marker file
├── frame/                     # Frame‑level concerns
│   ├── __init__.py
│   ├── base.py                # ActuarialFrame + ExecutionContext
│   ├── tracing.py             # Tracer / computation‑graph helpers
│   └── registry.py            # Accessor registration + plugin discovery
├── column/
│   ├── __init__.py
│   └── proxy.py               # ColumnProxy / ExpressionProxy
├── accessors/
│   ├── __init__.py            # Auto‑register built‑ins
│   ├── date.py                # DateFrameAccessor / DateColumnAccessor
│   ├── finance.py             # FinanceFrameAccessor / FinanceColumnAccessor
│   └── … (mortality, stats, etc.)
├── functions/                 # Wrappers for Rust core functions
│   ├── __init__.py
│   └── vector.py              # Mirrors core/src/polars_functions/vector.rs
├── errors/                    # Custom error handling/formatting
│   ├── __init__.py
│   └── formatting_errors.py   # Enhanced error message generation
├── plugins/                   # Optional built‑in plugins
│   └── __init__.py
├── util/                      # Logging, typing helpers, misc utilities
│   └── __init__.py
└── typing/                     # *published* stubs (see §4)
    ├── __init__.pyi           # Mirrors runtime structure
    ├── frame/
    │   ├── __init__.pyi
    │   └── base.pyi
    ├── column/
    │   ├── __init__.pyi
    │   └── proxy.pyi
    └── ... etc ...
```

*Mirrors the multi‑layer architecture already outlined in `layout.md` and the accessor spec discussed in project docs.*
*Includes dedicated `functions/` mirroring Rust source and `errors/` for specific handling.*
*Renamed `typing/` to `stubs/` for clarity.*

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

## 4. Shipping Rich `.pyi` Stubs Without Code Bloat

### 4.1 Mirror the Runtime Tree in `typing/`

* Create `gaspatchio_core/typing/` that **mirrors the runtime directory tree** but contains only `.pyi` files.
* Add empty `__init__.pyi` files so the stub packages are importable by type checkers.

### 4.2 Hybrid Documentation Strategy for Runtime, Tooling, and RAG

This project adopts a hybrid approach to documentation to balance several goals: providing rich information for developers and tooling (IDE hints, API docs), enabling automated testing of code examples, keeping the runtime library lean, and creating a structured input for the planned RAG system.

**Core Principles:**

1.  **`.pyi` Files as Primary Documentation Source:** The `.pyi` files in the `typing/` directory are the canonical source for type hints, detailed prose documentation (explanations, parameters, return values, usage notes), and serve as the input for API documentation generation (e.g., Sphinx) and the RAG ingestion pipeline.
2.  **Lean Runtime (`.py` Files):** The runtime `.py` files contain the actual implementation. Their docstrings are kept minimal to reduce package size and import time, *except* where needed for testable examples.
3.  **Differentiated Approach based on Method Origin:**
    *   **Proxied Polars Methods (via `_delegation.py`):** Since these methods are added dynamically, their signatures **must be manually added** to the relevant `.pyi` file (e.g., `typing/column/proxy.pyi`) after initial `stubgen` creation. The detailed documentation, including **crucial notes on custom behavior** (like handling scalars vs. vectors differently from standard Polars), resides *exclusively* within these `.pyi` docstrings. There are no corresponding docstrings or examples for these in the runtime `.py` files. These methods are tested via standard `pytest` test functions.
    *   **Custom Project Methods/Functions (e.g., in Accessors, Functions):** These are explicitly defined in the `.py` files.
        *   **Testable Examples:** Runnable code examples intended for automated testing with tools like `pytest-examples` are placed within the docstrings of the runtime `.py` files (or potentially separate Markdown files referenced by tests). This is where `pytest-examples` will discover and execute them.
        *   **Detailed Documentation:** The comprehensive prose documentation (purpose, parameters, returns, notes) resides in the corresponding `.pyi` file's docstring.
4.  **Automation for Unified View (Documentation/RAG) - PLANED (DO NOT IMPLEMENTED YET):**
    *   An automated script (run via CI/pre-commit) will parse the `.py` files (and/or Markdown example files) to extract the runnable code examples associated with *custom* project methods.
    *   This script will then append these extracted examples (e.g., under a `Runnable Example:` heading) to the existing prose docstring within the corresponding method's entry in the `.pyi` file.
    *   **Result:** The `.pyi` file becomes a complete documentation unit containing detailed prose *and* a verified code example, suitable for both developers browsing the stubs and the RAG system's structured data requirements (`name`, `description`, `code example`).
    *   **Crucially:** `pytest-examples` still tests the *original* example source in the `.py`/Markdown file, ensuring the copied example reflects working code.

**Generation & Maintenance Workflow Summary:**

1.  **Develop Code:** Write the implementation in `.py` files. For custom methods, include testable examples in their `.py` docstrings.
2.  **Generate Initial Stubs:** Run `stubgen` to create the basic `.pyi` file structure and capture explicitly defined members.
3.  **Manually Enhance `.pyi`:**
    *   Add signatures for all dynamically delegated Polars methods.
    *   Write detailed prose documentation, parameter explanations, custom behavior notes, etc., for *all* methods (proxied and custom) in the `.pyi` docstrings.
    *   Refine types (`Any` -> specific types, add generics, overloads).


PLANNED , DO NOT IMPLEMENTED YET:


4.  **Run Automation Script:** Execute the script to copy runnable examples from `.py` docstrings into the corresponding `.pyi` docstrings.
5.  **Testing & CI:**
    *   Run `pytest` (including `pytest-examples` on `.py` docstrings).
    *   Run type checkers (`mypy`/`pyright`) against the code using the `.pyi` files.
    *   Run stub parity checks.
    *   Build API documentation from the enhanced `.pyi` files.
    *   (Eventually) Run RAG ingestion pipeline on the `.pyi` files.

### 4.3 Add `py.typed` Marker File

* Place an **empty** `py.typed` file at the root of the `gaspatchio_core` package (`gaspatchio_core/py.typed`).
* **Purpose**: This file signals to PEP 561 compliant type checkers (like Mypy, Pyright) that the package ships its own type stubs (`.pyi` files). When present, checkers will prioritize these shipped stubs over trying to infer types from the `.py` files directly or looking for separate typeshed stubs. This ensures users get the benefit of the rich, accurate types defined in our `.pyi` files.

### 4.4 Expose Stubs via `typing.TYPE_CHECKING`

```python
# gaspatchio_core/__init__.py
import typing as _t
from .frame.base import ActuarialFrame
# …other runtime exports…

if _t.TYPE_CHECKING:
    # Import from the stub directory *only* during static analysis
    # This makes the rich types from .pyi files available to type checkers
    # without incurring runtime import cost or dependencies.
    from .typing import *  # noqa: F401, F403 - Wildcard import ok here
```

*Zero runtime overhead; maximum tooling fidelity.*

### 4.5 CI Guards

* **Stub–Runtime Parity Test**: Ensure every public symbol (function, class, method) in the runtime `.py` files has a corresponding entry in the `.pyi` stubs, checking for signature consistency (parameter names, types, return types).
* **Wheel‑Size / Import Time Audit**: Fail CI if wheel size or estimated import time exceeds a defined threshold.
* **Docs Build**: Configure Sphinx (or other doc generator) to build documentation primarily from the `.pyi` files in the `typing/` directory, leveraging the detailed docstrings there.

---

## 5. Incremental Migration Path

| Step | Action | Safe‑Guard |
|------|--------|-----------|
| 1 | Create new package skeleton (`frame/`, `column/`, `accessors/`, `functions/`, `errors/`, `typing/`, `util/`); add `py.typed`; add façade re‑exports in `gaspatchio_core/__init__.py`. | Tests still import old symbols unchanged via `__init__.py`. |
| 2 | Move *stateless* helpers/util and error formatting logic first. | No major side‑effects. Update imports. |
| 3 | Split `ColumnProxy` & `ExpressionProxy` into `column/`. | Leave shim in old location emitting deprecation warning, update imports. |
| 4 | Move registry + decorators; wire into frame & column. | Unit test: registering a dummy accessor yields `af.dummy.*`. |
| 5 | Extract accessor modules one‑by‑one into `accessors/`. | Each move accompanied by `.pyi` stub + docs. |
| 6 | Move core function wrappers into `functions/`. | Update imports. |
| 7 | Delete legacy code from `core.py`; remove façade re-exports eventually. | CI ensures everything imports from new paths. |
| 8 | Enable `mypy --strict` (or equivalent) over runtime *and* stubs. | — |

---

## 6. Testing & Continuous Integration

*Import safety, performance, and type coverage stay intact throughout.*

* **Path-Agnostic Tests**: Ensure tests import only from the public API (e.g., `from gaspatchio_core import ActuarialFrame, functions`).
* **Stub Parity Check**: Implement a CI step to compare runtime module structure and signatures against the `.pyi` stubs. This verifies that the stubs accurately reflect the runtime API.
* **Docstring Example Testing (Future)**: Plan for integrating `pytest-examples` or a similar tool to run code snippets found in `.py` docstrings or linked Markdown files, ensuring examples stay correct.
* **Linting & Formatting**: Use tools like Ruff/Black to enforce style consistency in both `.py` and `.pyi` files.
* **Type Checking**: Run `mypy --strict` (or Pyright) on both the runtime code (using the stubs) and *on the stubs themselves* to validate correctness.
* **Benchmark Guardrails**: Assert refactor does **not** negatively impact performance (e.g., `collect()` time for standard operations) beyond an acceptable tolerance.

---

## 7. Future‑Proofing Notes

* **Plugin Auto‑Discovery**: Consider `importlib.metadata.entry_points('gaspatchio_core.accessors')` for third-party accessor registration.
* **External Stubs**: Encourage third‑party plugin authors to ship their own `py.typed` and `.pyi` files.
* **Docs Generation**: With separated accessors and stubs, Sphinx can generate cleaner, more focused documentation pages per namespace/module.

---

## 8. Deliverables Checklist

- [ ] New directory skeleton committed (`frame`, `