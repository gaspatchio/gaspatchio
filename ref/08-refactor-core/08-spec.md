# Gaspatchio-Core Refactor Implementation Blueprint

This document outlines the detailed, step-by-step process for refactoring the `gaspatchio-core` library according to the plan described in `08-refactor.md`. The goal is to create a more modular, maintainable, and type-safe codebase with excellent developer tooling support, while adhering to the principles of incremental development and continuous testing.

## Target Package Layout

The final structure will adhere to the layout defined in `08-refactor.md`:

```text
gaspatchio_core/
├── __init__.py                # Re-export public surface
├── py.typed                   # PEP 561 marker file
├── frame/                     # Frame-level concerns
│   ├── __init__.py
│   ├── base.py                # ActuarialFrame + ExecutionContext
│   ├── tracing.py             # Tracer / computation-graph helpers
│   └── registry.py            # Accessor registration + plugin discovery
├── column/
│   ├── __init__.py
│   └── proxy.py               # ColumnProxy / ExpressionProxy
├── accessors/
│   ├── __init__.py            # Auto-register built-ins
│   ├── date.py                # DateFrameAccessor / DateColumnAccessor
│   ├── finance.py             # FinanceFrameAccessor / FinanceColumnAccessor
│   └── … (mortality, stats, etc.)
├── functions/                 # Wrappers for Rust core functions
│   ├── __init__.py
│   └── vector.py              # Mirrors core/src/polars_functions/vector.rs
├── errors/                    # Custom error handling/formatting
│   ├── __init__.py
│   └── formatting_errors.py   # Enhanced error message generation
├── plugins/                   # Optional built-in plugins
│   └── __init__.py
├── util/                      # Logging, typing helpers, misc utilities
│   └── __init__.py
└── typing/                     # *published* stubs (see §4 in 08-refactor.md)
    ├── __init__.pyi           # Mirrors runtime structure
    ├── frame/
    │   ├── __init__.pyi
    │   └── base.pyi
    ├── column/
    │   ├── __init__.pyi
    │   └── proxy.pyi
    └── ... etc ...
```

## Guiding Principles

*   **Incremental Changes:** Break down the refactor into the smallest viable steps.
*   **Test-Driven:** Write tests *before* or *alongside* moving/creating code. Ensure tests pass after each step.
*   **Continuous Integration:** Leverage CI checks (linting, formatting, type checking, stub parity) early and often.
*   **Façade First:** Use the main `__init__.py` as a façade to maintain backward compatibility during the transition.
*   **Stub Parallelism:** Develop `.pyi` stubs in parallel with code movement to ensure type information is rich and accurate from the start.
*   **Documentation as Code:** Treat `.pyi` docstrings as the primary source of detailed API documentation.
*   **Existing `dsl` Directory Removal:** The existing `gaspatchio_core/dsl/` directory and its contents will be removed as part of this refactor. Its functionality should be either obsolete, replaced by the new accessor/function structure, or explicitly migrated if still required (though the primary plan is removal). Tests previously covering `dsl` functionality must be updated or replaced to ensure coverage within the new structure.

## Phase 1: Setup and Foundation (Steps 1-3)

**Goal:** Establish the new package structure, basic CI, and initial type stub infrastructure, acknowledging the removal of the `dsl` directory.

1.  **Create Directory Structure & Basic Files:**
    *   Create directories: `frame/`, `column/`, `accessors/`, `functions/`, `errors/`, `util/`, `typing/` (as per Target Layout).
    *   **Note:** Do *not* create a top-level `dsl/` directory as part of the new structure.
    *   Add empty `__init__.py` files to each new runtime directory (`frame`, `column`, etc.).
    *   Add empty `__init__.pyi` files to each new `typing/` subdirectory mirroring the runtime structure.
    *   Create the `py.typed` marker file at the root (`gaspatchio_core/py.typed`).
    *   **Test:** N/A (Structure verification).
2.  **Establish Façade & Basic CI:**
    *   Modify `gaspatchio_core/__init__.py` to explicitly re-export all public symbols currently defined in `core.py`. This acts as a temporary façade.
    *   Configure basic CI pipeline: Ruff for linting/formatting, `pytest` execution.
    *   **Test:** Ensure existing tests still pass by importing *only* from `gaspatchio_core`.
3.  **Initial Stub Generation & Type Checking:**
    *   Run `stubgen gaspatchio_core -o gaspatchio_core/typing` to generate initial `.pyi` files based on the *current* `core.py` and **excluding the existing `dsl/` directory** (if possible with `stubgen`, otherwise manually remove `typing/dsl.pyi` if generated). Place these raw stubs appropriately within the `typing/` subdirectory structure (e.g., `typing/core.pyi` initially).
    *   Update `gaspatchio_core/__init__.py`: Add `if TYPE_CHECKING:` block to import `*` from `.typing`.
    *   Add `mypy` (or `pyright`) to the CI pipeline, initially configured non-strictly, checking the runtime code against the generated stubs.
    *   **Test:** CI `mypy` check should pass (or show manageable initial errors to fix).

## Phase 2: Core Logic Migration (Steps 4-7)

**Goal:** Move core components (`util`, `errors`, `column`, `frame`) into their new modules, updating tests and stubs accordingly.

4.  **Migrate Utilities & Error Handling:**
    *   Identify stateless helper functions/classes and error formatting logic in `core.py`.
    *   *Write Tests:* Add specific unit tests for these components if they don't exist.
    *   *Move Code:* Relocate helpers to `util/__init__.py` and error logic to `errors/formatting_errors.py` (and `errors/__init__.py` for exports).
    *   *Update Imports:* Change imports within the (still monolithic) `core.py` to use the new locations (`from .util import ...`, `from .errors import ...`).
    *   *Update Stubs:* Manually move/refactor corresponding definitions from `typing/core.pyi` to `typing/util/__init__.pyi` and `typing/errors/formatting_errors.pyi`. Add docstrings.
    *   **Test:** Ensure all unit tests and integration tests pass. CI `mypy` check passes.
5.  **Migrate Column/Expression Proxy:**
    *   *Write Tests:* Add specific unit tests for `ColumnProxy` and `ExpressionProxy` features (e.g., operator overloading, attribute access) focusing on their logic independent of `ActuarialFrame`.
    *   *Move Code:* Create `column/proxy.py`. Move the `ColumnProxy` and `ExpressionProxy` class definitions here.
    *   *Update Imports:* Change imports within `core.py` to use `from .column.proxy import ...`.
    *   *Update Stubs:* Create `typing/column/proxy.pyi`. Move corresponding definitions from `typing/core.pyi`, refine types, and add detailed docstrings (especially for proxied methods later).
    *   **Test:** Ensure all unit tests and integration tests pass. CI `mypy` check passes.
6.  **Migrate Frame Base & Tracing:**
    *   *Write Tests:* Add specific unit tests for `ActuarialFrame` core features (initialization, context, properties) and the tracing mechanism, isolating them from accessor logic.
    *   *Move Code:* Create `frame/base.py`. Move the `ActuarialFrame` definition and related constants/flags here.
    *   *Move Code:* Create `frame/tracing.py`. Move tracing/computation graph logic here. Update `frame/base.py` to import from `frame/tracing.py`.
    *   *Update Imports:* Change necessary imports within `core.py` (it's getting smaller).
    *   *Update Stubs:* Create `typing/frame/base.pyi` and `typing/frame/tracing.pyi`. Move corresponding definitions, refine types, add docstrings.
    *   **Test:** Ensure all unit tests and integration tests pass. CI `mypy` check passes.
7.  **Implement Accessor Registry:**
    *   *Write Tests:* Create `tests/frame/test_registry.py`. Add unit tests for `register_accessor` decorator (check registration, error on duplicates).
    *   *Implement Code:* Create `frame/registry.py`. Implement `_ACCESSOR_REGISTRY` and `register_accessor` as per `08-refactor.md`.
    *   *Integrate:* Modify `ActuarialFrame.__getattr__` (in `frame/base.py`) and `ColumnProxy.__getattr__` (in `column/proxy.py`) to consult the registry. Initially, they might do nothing if no accessors are registered.
    *   *Update Stubs:* Create `typing/frame/registry.pyi` with definitions and docstrings.
    *   **Test:** Ensure registry unit tests pass. Existing integration tests should still pass (no behavior change yet). CI `mypy` passes.

## Phase 3: Accessor and Function Migration (Steps 8-9)

**Goal:** Move accessors and core function wrappers iteratively, establishing the plugin pattern and CI stub parity checks.

8.  **Migrate Accessors (Iteratively):**
    *   For *each* accessor (e.g., `date`, `finance`, `stats`):
        *   *Identify:* Locate the accessor classes (`...FrameAccessor`, `...ColumnAccessor`) in `core.py`.
        *   *Write Tests:* Create specific tests for this accessor's methods (e.g., `tests/accessors/test_date.py`), importing *only* via the eventual public API (e.g., `actuarial_frame.date.some_method`). These might fail initially.
        *   *Move Code:* Create the accessor module (e.g., `accessors/date.py`). Move the class definitions here. Add the `@register_accessor(...)` decorators.
        *   *Register:* Add `from . import date` to `accessors/__init__.py`. Ensure `gaspatchio_core/__init__.py` imports `accessors` (e.g., `from . import accessors`).
        *   *Remove:* Delete the original accessor class definitions from `core.py`.
        *   *Update Stubs:* Create the corresponding stub file (e.g., `typing/accessors/date.pyi`). Move/add definitions, add *detailed* docstrings explaining purpose, parameters, returns, and usage notes. Add `__init__.pyi` to `typing/accessors/`.
        *   *Implement Parity Check:* Add a CI step (or enhance an existing one) to perform basic signature comparison between the runtime accessor module (`accessors/date.py`) and its stub (`typing/accessors/date.pyi`).
        *   **Test:** Ensure accessor-specific tests now pass. All integration tests pass. CI `mypy` and stub parity checks pass.
9.  **Migrate Core Function Wrappers:**
    *   Identify Python wrappers for Rust functions in `core.py` or elsewhere.
    *   *Write Tests:* Create tests for these wrapper functions (e.g., `tests/functions/test_vector.py`).
    *   *Move Code:* Create `functions/vector.py` (or other relevant files mirroring Rust structure). Move the wrapper function definitions here.
    *   *Create Namespace:* Create `functions/__init__.py` and explicitly re-export the functions (`from .vector import ...`). Consider exposing `functions` via `gaspatchio_core/__init__.py`.
    *   *Update Imports:* Change imports within accessors or other code that used these wrappers directly.
    *   *Update Stubs:* Create corresponding `.pyi` files (e.g., `typing/functions/vector.pyi`, `typing/functions/__init__.pyi`). Add definitions and detailed docstrings.
    *   *Update Parity Check:* Ensure the CI stub parity check covers the `functions/` module.
    *   **Test:** Ensure function-specific tests pass. All integration tests pass. CI `mypy` and stub parity checks pass.

## Phase 4: Finalization and Cleanup (Steps 10-12)

**Goal:** Remove legacy code, tighten CI checks, and prepare for documentation generation.

10. **Remove Legacy `core.py`, `dsl/` & Façade:**
    *   Verify that `core.py` is now empty or contains only imports (which should also be removable).
    *   Delete `core.py`.
    *   Delete `typing/core.pyi`.
    *   **Explicitly delete the entire `gaspatchio_core/dsl/` directory.**
    *   **Explicitly delete the entire `tests/dsl/` directory (or equivalent tests covering the old `dsl` module). Ensure equivalent test coverage exists within the new structure's tests.**
    *   Review `gaspatchio_core/__init__.py`. Remove explicit re-exports that are no longer needed (users should import from submodules like `gaspatchio_core.frame`, `gaspatchio_core.functions`, or accessors via frame/column instances). Keep exports for core classes like `ActuarialFrame`.
    *   **Test:** Ensure all tests still pass after removing the façade and the `dsl` directory/tests. Perform a search for any remaining imports *from* `.core` or `.dsl`.
11. **Refine Stubs & Tighten CI:**
    *   Perform a full review of all `.pyi` files in `typing/`. Ensure:
        *   All public APIs are present.
        *   Signatures match runtime (checked by parity tool).
        *   Type hints are specific (`Any` minimized). Generics/Overloads used where appropriate.
        *   **Crucially:** Add signatures and detailed docstrings for dynamically *proxied* Polars methods in `typing/column/proxy.pyi`, explaining any behavioral differences.
        *   Docstrings are comprehensive for all custom methods/functions/classes.
    *   Configure CI `mypy` check to run in `--strict` mode. Fix any revealed type errors.
    *   Implement CI checks for wheel size and import time against defined thresholds.
    *   Ensure the stub parity check covers *all* public modules and their members.
    *   **Test:** All CI checks (lint, tests, `mypy --strict`, parity, performance) must pass.
12. **Documentation & Future Prep:**
    *   Configure Sphinx (or chosen tool) to build API documentation primarily from the `.pyi` files in the `typing/` directory.
    *   (Future Task) Plan/Implement `pytest-examples` integration to test code examples within `.py` docstrings (as per `08-refactor.md`).
    *   (Future Task) Plan/Implement automation script to merge `.py` examples into `.pyi` docstrings for RAG.
    *   **Test:** Generate documentation locally and review for correctness and completeness.

---

## LLM Implementation Prompts

Below are prompts designed to guide a code-generation LLM through the refactoring steps outlined above in a test-driven manner. Each prompt assumes the previous one has been successfully completed.

### Prompt 1: Setup Directory Structure and Basic Files

```text
Task: Create the initial directory structure and necessary files for the `gaspatchio-core` refactor based on the target layout in `08-spec.md`.

Context: We are starting the refactor of the `gaspatchio-core` Python library. The current code resides primarily in `gaspatchio_core/core.py` and includes an existing `gaspatchio_core/dsl/` directory which will be removed.

Steps:
1. Inside the `gaspatchio_core` directory, create the following subdirectories: `frame`, `column`, `accessors`, `functions`, `errors`, `util`, `typing`. **Do not create a `dsl` directory.**
2. Inside `typing`, create subdirectories mirroring the runtime ones: `frame`, `column`, `accessors`, `functions`, `errors`, `util`.
3. Create an empty `__init__.py` file inside each *runtime* subdirectory created in step 1 (`frame`, `column`, `accessors`, `functions`, `errors`, `util`).
4. Create an empty `__init__.pyi` file inside the `typing` directory *and* inside each of its subdirectories created in step 2.
5. Create an empty file named `py.typed` directly inside the `gaspatchio_core` directory.

Verification: Manually inspect the directory structure to confirm all files and folders exist as specified, and that no `dsl` directory was created in the new structure.
```

### Prompt 2: Establish Façade & Basic CI

```text
Task: Set up the main `__init__.py` to act as a façade for the existing `core.py` and configure basic CI checks.

Context: We have created the new directory structure (Prompt 1). Now, we need to ensure existing code and tests continue to work by re-exporting symbols from the old `core.py` via the main `__init__.py`. We also need basic linting/formatting CI.

Steps:
1. Read the contents of `gaspatchio_core/core.py` to identify all public classes, functions, and constants currently defined.
2. Modify `gaspatchio_core/__init__.py`:
    - Add imports for all public symbols identified in step 1, e.g., `from .core import ActuarialFrame, ColumnProxy, ...`.
    - Optionally, add an `__all__ = [...]` list containing the names of these public symbols.
3. Assume a basic CI configuration file exists (e.g., `.github/workflows/ci.yml` or `pyproject.toml` for Ruff). Ensure it includes steps for:
    - Checking out code.
    - Setting up Python.
    - Installing dependencies (including `pytest` and `ruff`).
    - Running `ruff check .` and `ruff format --check .`.
    - Running `pytest`.
4. If CI configuration doesn't exist, create a basic one using GitHub Actions or modify `pyproject.toml` for Ruff.

Verification:
- Run `pytest` locally. All existing tests should pass, as they should now be importing symbols transparently through `gaspatchio_core/__init__.py`.
- Run `ruff check .` and `ruff format --check .` locally. Fix any reported issues.
- Commit the changes and push to trigger the CI pipeline. Ensure all CI steps pass.
```

### Prompt 3: Initial Stub Generation & Type Checking Setup

```text
Task: Generate initial type stubs (`.pyi`) for the existing codebase (excluding `dsl`) and integrate basic type checking (`mypy`) into the CI pipeline.

Context: The directory structure and façade are set up (Prompts 1-2). We now generate baseline type stubs and add static analysis to CI. We will ignore the existing `dsl` directory during stub generation.

Steps:
1. Install `mypy` if not already present (`uv add mypy`).
2. Run the command `stubgen gaspatchio_core -o gaspatchio_core/typing`. **Critically, after running, manually delete the `gaspatchio_core/typing/dsl/` directory and `gaspatchio_core/typing/dsl.pyi` if they were generated.** We only want stubs for `core.py` and other non-`dsl` modules at this stage.
3. Modify `gaspatchio_core/__init__.py`:
    - Add `import typing as _t`.
    - Add the conditional block:
      ```python
      if _t.TYPE_CHECKING:
          # Import from the stub directory *only* during static analysis
          from .typing import *  # noqa: F401, F403
      ```
4. Update the CI configuration:
    - Add a step to install `mypy`.
    - Add a step to run `mypy gaspatchio_core`. Configure `mypy` (e.g., in `pyproject.toml [tool.mypy]`) to follow imports (`follow_imports = "normal"` or `"skip"` initially if needed) but disable strict checks for now. Aim for a passing state with minimal errors. Address any critical import errors revealed by `mypy`.

Verification:
- Run `mypy gaspatchio_core` locally. It should run without crashing, though it might report type errors (which is expected at this stage). Fix any fundamental configuration or import errors reported.
- Commit the changes and push. Ensure the new `mypy` step in the CI pipeline passes (or reports the expected, non-blocking errors).
```

### Prompt 4: Migrate Utilities & Error Handling

```text
Task: Move stateless utility functions/classes and error formatting logic from `core.py` to `util/` and `errors/` modules, including tests and stub updates.

Context: We have the basic structure, façade, stubs, and CI (Prompts 1-3). This is the first step of actual code migration.

Steps:
1. **Identify Code:** Examine `gaspatchio_core/core.py` and identify functions or classes that are general utilities (not tied to Frame/Column state) or specifically related to error formatting.
2. **Write/Verify Tests:**
    - Locate existing tests for these utilities/error functions. If they don't exist, write unit tests for them in appropriate test files (e.g., `tests/util/test_helpers.py`, `tests/errors/test_formatting.py`). Ensure these tests pass against the code in its current location (`core.py`).
3. **Move Runtime Code:**
    - Move the identified utility functions/classes to `gaspatchio_core/util/__init__.py`.
    - Move the error formatting logic to `gaspatchio_core/errors/formatting_errors.py`.
    - Add necessary imports and re-exports in `gaspatchio_core/errors/__init__.py` (e.g., `from .formatting_errors import ...`).
4. **Update Imports:** Modify `gaspatchio_core/core.py` to import these components from their new locations (e.g., `from .util import ...`, `from .errors import ...`). Also, update any tests that might have imported directly from `core.py`.
5. **Move/Refactor Stubs:**
    - Create `gaspatchio_core/typing/util/__init__.pyi` and `gaspatchio_core/typing/errors/formatting_errors.pyi`.
    - Manually cut the corresponding function/class definitions from `gaspatchio_core/typing/core.pyi` and paste them into the new stub files.
    - Add basic docstrings to the definitions in the new `.pyi` files explaining their purpose.
    - Refine type hints in the new `.pyi` files if obvious improvements can be made.
    - Create `gaspatchio_core/typing/errors/__init__.pyi` and add re-exports mirroring `errors/__init__.py`.

Verification:
- Run `pytest`. All tests (including the newly added/verified unit tests) must pass.
- Run `mypy gaspatchio_core`. It should pass (or show the same manageable errors as before).
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass.
```

### Prompt 5: Migrate Column/Expression Proxy

```text
Task: Move `ColumnProxy` and `ExpressionProxy` from `core.py` to `column/proxy.py`, including tests and stub updates.

Context: Utilities and errors are migrated (Prompt 4). Now we extract the column proxy logic.

Steps:
1. **Write/Verify Tests:**
    - Locate or write specific unit tests for `ColumnProxy` and `ExpressionProxy` in `tests/column/test_proxy.py`. Focus on testing their independent behavior (operator overloading, attribute handling, expression creation) without relying heavily on `ActuarialFrame`. Ensure tests pass against `core.py`.
2. **Move Runtime Code:**
    - Create `gaspatchio_core/column/proxy.py`.
    - Cut the class definitions for `ColumnProxy` and `ExpressionProxy` from `gaspatchio_core/core.py` and paste them into `gaspatchio_core/column/proxy.py`.
    - Ensure necessary imports within `column/proxy.py` are correct (they might now need relative imports like `from ..errors import ...`).
3. **Update Imports:** Modify `gaspatchio_core/core.py` to import these classes from the new location: `from .column.proxy import ColumnProxy, ExpressionProxy`. Update any tests importing them directly.
4. **Move/Refactor Stubs:**
    - Create `gaspatchio_core/typing/column/proxy.pyi`.
    - Cut the corresponding class definitions from `gaspatchio_core/typing/core.pyi` and paste them into `typing/column/proxy.pyi`.
    - Add/refine docstrings in the `.pyi` file, particularly noting that this file will later contain definitions for Polars methods proxied by these classes.
    - Refine type hints.
    - Ensure `gaspatchio_core/typing/column/__init__.pyi` exists.

Verification:
- Run `pytest`. All tests must pass.
- Run `mypy gaspatchio_core`. It should pass.
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass.
```

### Prompt 6: Migrate Frame Base & Tracing

```text
Task: Move `ActuarialFrame` core logic and tracing mechanisms from `core.py` to `frame/base.py` and `frame/tracing.py`.

Context: Column proxies are migrated (Prompt 5). Now extract the main frame class and tracing logic.

Steps:
1. **Write/Verify Tests:**
    - Locate or write specific unit tests for `ActuarialFrame`'s core initialization, properties (e.g., `_df`, `_context`), and context management in `tests/frame/test_base.py`.
    - Locate or write tests for the tracing/computation graph mechanism (whatever form it takes) in `tests/frame/test_tracing.py`. Isolate these tests from specific accessor logic. Ensure tests pass against `core.py`.
2. **Move Runtime Code (Tracing):**
    - Create `gaspatchio_core/frame/tracing.py`.
    - Cut the tracing-related functions/classes from `core.py` and paste them into `frame/tracing.py`. Adjust imports as needed.
3. **Move Runtime Code (Frame):**
    - Create `gaspatchio_core/frame/base.py`.
    - Cut the `ActuarialFrame` class definition and any related constants/global flags (like execution context or mode flags) from `core.py` and paste them into `frame/base.py`.
    - Update `ActuarialFrame` in `frame/base.py` to import necessary components from `frame.tracing`, `..column.proxy`, `..util`, `..errors`, etc., using relative imports.
4. **Update Imports:** Modify `gaspatchio_core/core.py` to import `ActuarialFrame` from `frame.base`: `from .frame.base import ActuarialFrame`. Update any tests importing it directly. Remember `gaspatchio_core/__init__.py` already re-exports it from `.core`, so that façade still works.
5. **Move/Refactor Stubs:**
    - Create `gaspatchio_core/typing/frame/tracing.pyi` and `gaspatchio_core/typing/frame/base.pyi`.
    - Cut corresponding definitions from `typing/core.pyi` and paste them into the new stub files.
    - Add/refine docstrings and type hints.
    - Ensure `gaspatchio_core/typing/frame/__init__.pyi` exists.

Verification:
- Run `pytest`. All tests must pass.
- Run `mypy gaspatchio_core`. It should pass.
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass.
```

### Prompt 7: Implement Accessor Registry

```text
Task: Implement the accessor registration mechanism in `frame/registry.py` and integrate it into `ActuarialFrame` and `ColumnProxy`.

Context: Frame and Column logic is mostly migrated (Prompt 6). Now we add the infrastructure for dynamically attaching accessor namespaces.

Steps:
1. **Write Tests:**
    - Create `tests/frame/test_registry.py`.
    - Add unit tests for the `register_accessor` decorator:
        - Test successful registration of a dummy frame accessor.
        - Test successful registration of a dummy column accessor.
        - Test that retrieving the registry content (if possible) reflects registration.
        - Test that attempting to register the same name twice raises a `ValueError`.
2. **Implement Runtime Code:**
    - Create `gaspatchio_core/frame/registry.py`.
    - Implement the `_ACCESSOR_REGISTRY: dict[str, tuple[type, str]] = {}` dictionary.
    - Implement the `register_accessor(name: str, *, kind: str = "column")` decorator exactly as specified in `08-refactor.md`. Ensure it correctly populates `_ACCESSOR_REGISTRY`.
3. **Integrate with Frame/Column:**
    - Modify `ActuarialFrame.__getattr__` in `gaspatchio_core/frame/base.py`:
        - Add logic to check if the requested `name` exists in `_ACCESSOR_REGISTRY` with `kind="frame"`.
        - If found, instantiate the registered accessor class (`cls(self)`) and cache it on the instance (e.g., `setattr(self, name, accessor_instance)`). Return the instance.
        - If not found, proceed with existing `__getattr__` logic (e.g., proxying to the underlying DataFrame or raising `AttributeError`).
    - Modify `ColumnProxy.__getattr__` in `gaspatchio_core/column/proxy.py`:
        - Add similar logic to check `_ACCESSOR_REGISTRY` for the `name` with `kind="column"`.
        - Instantiate (`cls(self)`), cache, and return the accessor instance if found.
        - If not found, proceed with existing logic (e.g., creating expressions or raising `AttributeError`).
4. **Create Stubs:**
    - Create `gaspatchio_core/typing/frame/registry.pyi`.
    - Add definitions for `_ACCESSOR_REGISTRY` (using `typing.Dict`, `typing.Type`, `typing.Tuple`) and `register_accessor`. Include docstrings.
    - Update `typing/frame/base.pyi` and `typing/column/proxy.pyi` to reflect the potential dynamic attributes added by accessors (though we won't list specific ones yet, maybe add a comment).

Verification:
- Run `pytest`. The new registry tests must pass. Existing integration tests should continue to pass (as no accessors are registered yet, the new `__getattr__` logic shouldn't change behavior).
- Run `mypy gaspatchio_core`. It should pass.
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass.
```

### Prompt 8: Migrate 'date' Accessor (Example Iteration)

```text
Task: Migrate the 'date' accessor (both Frame and Column versions) from `core.py` to `accessors/date.py`, including tests, registration, and stub updates with detailed documentation. Implement a basic stub parity check.

Context: The registry is implemented (Prompt 7). We now migrate the first accessor as a template for others.

Steps:
1. **Identify Code:** Locate `DateFrameAccessor` and `DateColumnAccessor` classes within `gaspatchio_core/core.py`.
2. **Write/Verify Tests:**
    - Create `tests/accessors/test_date.py`.
    - Write/move unit tests that specifically target methods within `DateFrameAccessor` and `DateColumnAccessor`.
    - These tests should instantiate an `ActuarialFrame` or get a `ColumnProxy` and then call methods via the accessor namespace (e.g., `af.date.create_timeline(...)`, `af['col'].date.from_excel_serial(...)`). They might fail initially if run before moving the code. Ensure tests exist and cover key functionality.
3. **Move Runtime Code:**
    - Create `gaspatchio_core/accessors/date.py`.
    - Cut the `DateFrameAccessor` and `DateColumnAccessor` class definitions from `core.py` and paste them into `accessors/date.py`.
    - Add `from ..frame.registry import register_accessor` at the top.
    - Add the `@register_accessor("date", kind="frame")` decorator to `DateFrameAccessor`.
    - Add the `@register_accessor("date", kind="column")` decorator to `DateColumnAccessor`.
    - Ensure internal imports within the accessor classes are updated (e.g., `from ...column.proxy import ...`, `from ...errors import ...`).
4. **Register Accessor Module:**
    - Create `gaspatchio_core/accessors/__init__.py`.
    - Add the line `from . import date` to trigger registration when `accessors` is imported.
    - Modify `gaspatchio_core/__init__.py` to ensure the accessors module is imported at some point, perhaps by adding `from . import accessors`.
5. **Remove from Core:** Delete the `DateFrameAccessor` and `DateColumnAccessor` definitions from `gaspatchio_core/core.py`.
6. **Create/Update Stubs:**
    - Create `gaspatchio_core/typing/accessors/date.pyi`.
    - Add the class definitions for `DateFrameAccessor` and `DateColumnAccessor`.
    - **Crucially:** Add detailed docstrings to the classes and their methods, explaining purpose, parameters, returns, and any important usage notes or examples (even if examples aren't testable yet). Use type hints matching the implementation.
    - Create `gaspatchio_core/typing/accessors/__init__.pyi`. Add `from .date import DateFrameAccessor, DateColumnAccessor`.
    - Update `typing/frame/base.pyi`: Add `date: DateFrameAccessor` attribute to `ActuarialFrame`.
    - Update `typing/column/proxy.pyi`: Add `date: DateColumnAccessor` attribute to `ColumnProxy`.
7. **Implement Basic Stub Parity Check (CI):**
    - Add a new step to the CI workflow (or use a dedicated tool/script).
    - This step should perform a simple check: For the module `gaspatchio_core.accessors.date`, compare the public members (`__all__` or members not starting with `_`) found via runtime introspection with the members defined in the stub file `gaspatchio_core/typing/accessors/date.pyi`. Report discrepancies (missing or extra members). Signature checking can be added later.

Verification:
- Run `pytest`. The `test_date.py` tests should now pass, along with all other tests.
- Run `mypy gaspatchio_core`. It should pass, now utilizing the specific accessor types added to the Frame/Column stubs.
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass, including the new (basic) stub parity check.
```

**(Repeat Prompt 8 structure for each subsequent accessor: `finance`, `stats`, etc., adjusting names and potentially the parity check implementation.)**

### Prompt 9: Migrate Core Function Wrappers

```text
Task: Move Python wrappers for Rust core functions (assuming they exist) into the `functions/` module, update imports, add tests, and update stubs/parity checks.

Context: Accessors are being migrated (Prompt 8 repeated). Now move any low-level function wrappers. Assume these are currently in `core.py` or maybe `util.py`. Let's assume they relate to vector operations and belong in `functions/vector.py`.

Steps:
1. **Identify Code:** Locate Python functions in `core.py` (or elsewhere) that directly wrap calls to the Rust extension (e.g., functions calling `gaspatchio_core._rust_bindings.some_vector_op`).
2. **Write/Verify Tests:**
    - Create `tests/functions/test_vector.py`.
    - Write/move unit tests specifically for these wrapper functions, ensuring they handle inputs/outputs correctly and call the underlying Rust function (mocking might be needed if direct calls are complex/undesirable in unit tests).
3. **Move Runtime Code:**
    - Create `gaspatchio_core/functions/vector.py`.
    - Cut the identified wrapper functions from their current location and paste them into `vector.py`. Adjust imports as needed (e.g., import the Rust binding).
4. **Create Namespace:**
    - Create `gaspatchio_core/functions/__init__.py`.
    - Add explicit re-exports: `from .vector import func1, func2, ...`.
    - Consider if `gaspatchio_core/__init__.py` should expose the `functions` module itself (`from . import functions`) or specific commonly used functions.
5. **Update Imports:** Refactor any code (likely within accessors moved in previous steps) that previously imported these wrappers from `core.py` or `util` to now import them from `gaspatchio_core.functions`.
6. **Create/Update Stubs:**
    - Create `gaspatchio_core/typing/functions/vector.pyi`. Add function signatures with type hints and detailed docstrings.
    - Create `gaspatchio_core/typing/functions/__init__.pyi`. Add re-exports mirroring `functions/__init__.py`.
7. **Update Parity Check:** Ensure the CI stub parity check now also covers modules within the `functions/` directory (e.g., `gaspatchio_core.functions.vector`).

Verification:
- Run `pytest`. All tests, including `test_vector.py`, must pass.
- Run `mypy gaspatchio_core`. It should pass.
- Run linters/formatters. Fix any issues.
- Commit and ensure all CI checks pass, including the updated parity check.
```

### Prompt 10: Remove Legacy core.py, dsl/ & Façade Elements

```text
Task: Delete the now-empty `core.py` file, the entire existing `dsl/` directory and its tests, and remove unnecessary façade re-exports from `gaspatchio_core/__init__.py`.

Context: All functional code (utilities, errors, frame, column, accessors, functions) has been migrated to new modules (Prompts 4-9). `core.py` should be empty. The legacy `dsl` directory needs to be removed.

Steps:
1. **Verify `core.py`:** Open `gaspatchio_core/core.py`. Confirm it contains no functional code.
2. **Delete Files & Directories:**
    - Delete `gaspatchio_core/core.py`.
    - Delete `gaspatchio_core/typing/core.pyi`.
    - **Delete the entire `gaspatchio_core/dsl/` directory.** Use `rm -rf gaspatchio_core/dsl/`.
    - **Delete the corresponding test directory for dsl (e.g., `tests/dsl/`).** Use `rm -rf tests/dsl/`.
3. **Clean `__init__.py`:**
    - Edit `gaspatchio_core/__init__.py`.
    - Remove all imports that were importing *from* `.core`.
    - Ensure no imports remain related to `.dsl`.
    - Add back necessary imports from the new locations for the main public API (e.g., `ActuarialFrame`, potentially `ColumnProxy`, `ExpressionProxy`, `functions` namespace, `accessors` for registration).
    - Update `__all__` accordingly.
4. **Search for Imports:** Perform a project-wide search for any remaining code that might still be trying to import `from gaspatchio_core.core`, `from .core`, `from gaspatchio_core.dsl`, or `from .dsl`. Fix any instances found.
5. **Verify Test Coverage:** Review test coverage reports (if available) or manually inspect tests to ensure functionality previously covered by `tests/dsl/` is now adequately covered by tests in `tests/frame/`, `tests/column/`, `tests/accessors/`, etc. Add missing tests if gaps are found.

Verification:
- Run `pytest`. All tests must pass. Pay close attention to ensure no tests were silently relying on the `dsl` module.
- Run `mypy gaspatchio_core`. It should pass.
- Run linters/formatters. Fix any issues.
- Manually inspect `git status` and `git diff` to confirm `core.py`, `typing/core.pyi`, the `dsl` directory, and its associated test directory were deleted, and `__init__.py` was cleaned appropriately.
- Commit and ensure all CI checks pass.
```

### Prompt 11: Refine Stubs & Tighten CI

```text
Task: Perform a full review and refinement of all `.pyi` stubs, add definitions for proxied methods, and configure CI checks for strictness, parity, and performance.

Context: The runtime code is refactored, and `core.py` is removed (Prompt 10). Now, focus on perfecting the type stubs and locking down CI.

Steps:
1. **Review/Refine Stubs:**
    - Go through every `.pyi` file in `gaspatchio_core/typing/`.
    - **Check Completeness:** Ensure all public runtime APIs have corresponding stub definitions.
    - **Check Accuracy:** Use the CI parity check results (and potentially manual comparison) to ensure signatures match.
    - **Improve Specificity:** Replace `Any` with specific types where possible. Add generics (`TypeVar`) and `overload` where appropriate.
    - **Enhance Docstrings:** Ensure all public classes, methods, and functions have comprehensive docstrings explaining purpose, parameters (with types), returns, and usage notes/examples.
2. **Add Proxied Method Stubs:**
    - **Identify Proxied Methods:** Determine which Polars methods are intended to be accessible via `ActuarialFrame` (through its underlying DataFrame) and `ColumnProxy`/`ExpressionProxy`.
    - **Edit `typing/column/proxy.pyi`:** For each proxied Polars method (e.g., `sum`, `mean`, `cast`, `alias`, etc.), add its method signature to both `ColumnProxy` and `ExpressionProxy` classes in the stub file. Use accurate Polars type hints where possible, or reasonable approximations. Add a docstring explaining it's a proxied Polars method and *crucially note any differences in behavior* compared to standard Polars (e.g., scalar handling).
    - **Edit `typing/frame/base.pyi`:** Similarly, add stubs for Polars DataFrame methods intended to be directly accessible on `ActuarialFrame` (if any beyond the core `__init__`, `__getitem__` etc.).
3. **Tighten CI - MyPy:**
    - Configure the `mypy` check in CI (e.g., in `pyproject.toml [tool.mypy]`) to run in strict mode. Common strict settings include: `disallow_untyped_defs = True`, `disallow_any_unimported = True`, `no_implicit_optional = True`, `warn_redundant_casts = True`, `warn_unused_ignores = True`, etc. (or simply `strict = True`).
    - Run `mypy --strict gaspatchio_core` locally and fix *all* reported errors. This may involve adding more precise types, handling `Optional`, or adding `# type: ignore` comments *judiciously* with explanations.
4. **Enhance CI - Stub Parity:**
    - Improve the stub parity check (if it was basic before) to compare function/method signatures (parameter names, types, return types) between runtime and stubs, not just member existence. Tools like `mypy --strict` itself or dedicated stub checking tools can help here.
5. **Add CI - Performance:**
    - Add CI steps to measure key performance indicators:
        - **Wheel Size:** Check the size of the built wheel (`python -m build` then check `dist/*.whl` size) against a baseline threshold. Fail the build if thresholds are exceeded.
        - **Import Time:** Use `python -X importtime -c "import gaspatchio_core"` and check the total time against a baseline threshold. Fail the build if thresholds are exceeded.

Verification:
- Run `pytest`. All tests must pass.
- Run `mypy --strict gaspatchio_core` locally. It MUST pass with zero errors.
- Run linters/formatters. Fix any issues.
- Build the wheel and check its size. Check import time.
- Commit and ensure ALL CI checks pass, including the strict `mypy`, enhanced parity check, and new performance checks.
```

### Prompt 12: Documentation Generation Setup

```text
Task: Configure Sphinx (or preferred tool) to build API documentation primarily from the `.pyi` stubs in the `typing/` directory.

Context: The refactor is complete, code is organized, stubs are detailed, and CI is strict (Prompt 11). The final step is setting up documentation generation.

Steps:
1. **Install Sphinx & Theme:** Ensure `sphinx` and a theme (e.g., `sphinx-rtd-theme`, `furo`, or `mkdocs-material` if using MkDocs with `mkdocstrings`) are installed.
2. **Configure Sphinx (`conf.py`):**
    - Set up the basic Sphinx configuration (`docs/conf.py`).
    - Configure the `autodoc` extension (`sphinx.ext.autodoc`).
    - **Crucially:** Configure `autodoc` (or `mkdocstrings`) to look for modules within the *package directory* (`gaspatchio_core`) but to preferentially read documentation and signatures from the corresponding `.pyi` files in `gaspatchio_core/typing/`. This might involve setting `autodoc_typehints = 'signature'` and ensuring the Python path includes the project root so stubs are found alongside the runtime code by Sphinx's introspection mechanism, leveraging the `py.typed` file. Some configurations might involve pointing directly to the stub path or using tools aware of stub files.
    - Configure other extensions like `napoleon` (for Google/NumPy style docstrings), `intersphinx`, `viewcode`.
3. **Create Documentation Source Files (`.rst` or `.md`):**
    - Create index file (`docs/index.rst` or `docs/index.md`).
    - Create API pages using `automodule`, `autoclass`, `autofunction` directives (or `mkdocstrings` identifiers) pointing to the modules and objects within `gaspatchio_core` (e.g., `gaspatchio_core.frame.base`, `gaspatchio_core.accessors.date`, `gaspatchio_core.functions.vector`).
    - Example (`api/frame.rst`):
      ```rst
      .. automodule:: gaspatchio_core.frame.base
         :members:
      .. automodule:: gaspatchio_core.frame.registry
         :members:
      .. automodule:: gaspatchio_core.frame.tracing
         :members:
      ```
4. **Build Documentation:** Run `sphinx-build -b html docs docs/_build/html` (or `mkdocs build`).
5. **Add CI Step:** Add a step to the CI pipeline to build the documentation and optionally upload it as an artifact.

Verification:
- Build the documentation locally.
- Open the generated HTML files in `docs/_build/html`.
- Verify that:
    - API pages are generated for the core modules (`frame`, `column`, `functions`, `accessors`, etc.).
    - Signatures and parameter lists are correctly extracted.
    - **Docstrings displayed are the detailed ones from the `.pyi` files.**
- Commit and ensure the CI documentation build step passes.
```
