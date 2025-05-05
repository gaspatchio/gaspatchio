# Gaspatchio-Core Refactor Implementation Blueprint

This document details the step-by-step implementation plan for refactoring the `gaspatchio_core.dsl.core` module into a structured package, following the strategy outlined in `08-refactor.md`. It includes a series of prompts designed for a code-generation LLM to execute each step in a test-driven manner.

**Core Principles:**

*   **Incremental Changes:** Each step should be small, verifiable, and build upon the previous one.
*   **Test-Driven Development (TDD):** Write tests *before* or alongside implementation for each component.
*   **Collocated Stubs (`.pyi`):** Create and maintain detailed `.pyi` files alongside `.py` files from the start.
*   **Façade First:** Use the main `__init__.py` as a façade initially to avoid breaking existing imports, then clean up.
*   **CI Integration:** Incorporate type checking (`mypy`) and stub validation (`stubtest`) early.

---

## Phase 1: Foundation Setup

### Step 0: Directory Structure & Initial Files

**Goal:** Create the target package structure and necessary boilerplate files.

**Tasks:**

1.  Create directories: `gaspatchio_core/frame`, `gaspatchio_core/column`, `gaspatchio_core/accessors`, `gaspatchio_core/functions`, `gaspatchio_core/errors`, `gaspatchio_core/util`.
2.  Add empty `__init__.py` and `__init__.pyi` files to `gaspatchio_core` and each new subdirectory.
3.  Create `gaspatchio_core/py.typed` (empty marker file).
4.  Modify `gaspatchio_core/__init__.py` to temporarily re-export everything from the *old* `dsl.core` module to act as a façade. This keeps imports working during the transition.
5.  Run existing tests to ensure the façade works and no imports are broken.

**LLM Prompt 0:**

```text
Context: We are refactoring the monolithic `gaspatchio_core.dsl.core` module into a structured package. The target layout involves subdirectories like `frame`, `column`, `accessors`, etc., as defined in `08-refactor.md`.

Task:
1.  Create the following directories within `gaspatchio-core/bindings/python/gaspatchio_core/`:
    *   `frame/`
    *   `column/`
    *   `accessors/`
    *   `functions/`
    *   `errors/`
    *   `util/`
2.  Inside `gaspatchio_core/` and each new subdirectory (`frame`, `column`, etc.), create an empty `__init__.py` file and an empty `__init__.pyi` file.
3.  Create an empty marker file named `py.typed` inside `gaspatchio_core/`.
4.  Modify `gaspatchio_core/__init__.py` to re-export all symbols from the *existing* `gaspatchio_core.dsl.core` module. Use `from .dsl.core import *` for now. This acts as a temporary façade.
5.  Modify `gaspatchio_core/__init__.pyi` to declare the re-exported symbols from `dsl.core` (you might need to inspect `dsl/core.py` or use a tool like `stubgen` as a starting point for the list of symbols).

Goal: Establish the basic package structure and ensure existing code relying on top-level imports from `gaspatchio_core` continues to function via the façade. Verify by running existing project tests.
```

---

## Phase 2: Extracting Core Components

### Step 1: Utilities

**Goal:** Move stateless utility functions out of `core.py`.

**Tasks:**

1.  Identify stateless helper functions in `dsl/core.py` (e.g., `get_default_mode`, `set_default_mode`, `get_default_verbose`, `set_default_verbose`, `_expr_to_str`).
2.  Move these functions to `util/__init__.py`.
3.  Create `util/__init__.pyi` with accurate type hints and docstrings for the moved functions.
4.  Write unit tests for these utility functions in a new `tests/util/test_utils.py` file.
5.  Update imports within the *old* `dsl/core.py` to use the new location (`from ..util import ...`).
6.  Run tests.

**LLM Prompt 1:**

```text
Context: We have set up the basic package structure for `gaspatchio_core`. The next step is to extract stateless utility functions from `gaspatchio_core/dsl/core.py`.

Task:
1.  Identify stateless helper functions in `gaspatchio_core/dsl/core.py`. Candidates include `get_default_mode`, `set_default_mode`, `get_default_verbose`, `set_default_verbose`, `_expr_to_str`, and potentially the `execution_mode` context manager.
2.  Move the identified functions from `dsl/core.py` to `gaspatchio_core/util/__init__.py`.
3.  Update the corresponding `gaspatchio_core/util/__init__.pyi` file with accurate type signatures and comprehensive docstrings for the moved functions.
4.  Create a new test file `tests/util/test_utils.py`. Write unit tests using `pytest` for each moved utility function, covering typical usage and edge cases.
5.  Modify the *original* `gaspatchio_core/dsl/core.py` file: update the import statements at the top to import the moved functions from their new location (e.g., `from ..util import get_default_mode`).
6.  Ensure all project tests pass after these changes.

Goal: Isolate utility functions into their own module with proper stubs and tests, preparing `dsl/core.py` for further decomposition.
```

### Step 2: Error Handling

**Goal:** Move custom error classes and formatting logic.

**Tasks:**

1.  Identify error-related code in `dsl/core.py`: `PerformanceWarning`, `_extract_missing_column_robust`, `_format_column_error`, `_handle_execution_error`.
2.  Move this code to `errors/formatting_errors.py`.
3.  Create `errors/__init__.py` and `errors/__init__.pyi` (exporting symbols from `formatting_errors`).
4.  Create `errors/formatting_errors.pyi` with types and docstrings.
5.  Write unit tests for the error formatting functions in `tests/errors/test_formatting.py`. Mock dependencies (like `_df.columns` or `_find_similar_columns`) as needed.
6.  Update imports in `dsl/core.py` (`from ..errors import ...`).
7.  Run tests.

**LLM Prompt 2:**

```text
Context: Utilities have been moved to `gaspatchio_core/util`. Now, we focus on extracting error handling logic from `gaspatchio_core/dsl/core.py`.

Task:
1.  Identify error-related definitions and functions in `gaspatchio_core/dsl/core.py`. Candidates: `PerformanceWarning` class, `_extract_missing_column_robust`, `_format_column_error`, `_handle_execution_error`.
2.  Move this code into a new file: `gaspatchio_core/errors/formatting_errors.py`.
3.  Create/update `gaspatchio_core/errors/__init__.py` to export the necessary symbols (e.g., `PerformanceWarning`, `_handle_execution_error`) from `formatting_errors.py`.
4.  Create `gaspatchio_core/errors/formatting_errors.pyi` with accurate type hints and docstrings for the contents of `formatting_errors.py`.
5.  Update `gaspatchio_core/errors/__init__.pyi` to declare the exported symbols.
6.  Create a new test file `tests/errors/test_formatting.py`. Write unit tests for the moved functions (`_extract_missing_column_robust`, `_format_column_error`, `_handle_execution_error`), mocking any `ActuarialFrame` dependencies (like `self._df`, `self._column_order`, `self._find_similar_columns`).
7.  Modify `gaspatchio_core/dsl/core.py`: update imports to use the new error handling location (e.g., `from ..errors import _handle_execution_error, PerformanceWarning`).
8.  Ensure all project tests pass.

Goal: Centralize error handling logic, making it independently testable and removing it from the main `core.py` file.
```

### Step 3: Proxies

**Goal:** Extract `ColumnProxy` and `ExpressionProxy`.

**Tasks:**

1.  Identify `ColumnProxy` and `ExpressionProxy` classes in `dsl/core.py`.
2.  Move these classes to `column/proxy.py`.
3.  Update internal references within the classes (e.g., `self._parent` usage, imports for accessors if they exist yet - likely deferred).
4.  Create `column/__init__.py` (exporting the proxies) and `column/__init__.pyi`.
5.  Create `column/proxy.pyi` with full type hints (including operator overloads) and docstrings.
6.  Write unit tests in `tests/column/test_proxy.py` focusing on operator overloading, attribute access (like `.alias()`, `.cast()`), and interaction with a mock parent object.
7.  Update imports in `dsl/core.py` (`from ..column import ColumnProxy, ExpressionProxy`).
8.  Run tests.

**LLM Prompt 3:**

```text
Context: Utilities and error handling are extracted. We now target the `ColumnProxy` and `ExpressionProxy` classes in `gaspatchio_core/dsl/core.py`.

Task:
1.  Move the `ColumnProxy` and `ExpressionProxy` class definitions from `gaspatchio_core/dsl/core.py` to a new file: `gaspatchio_core/column/proxy.py`.
2.  Update any internal imports within these classes if necessary (e.g., if they currently import accessors directly, adjust paths or prepare for later injection). Ensure references like `self._parent._convert_to_expr` still make sense in the context of the `ActuarialFrame` being the parent.
3.  Create/update `gaspatchio_core/column/__init__.py` to export `ColumnProxy` and `ExpressionProxy`.
4.  Create `gaspatchio_core/column/proxy.pyi` providing complete type hints for methods, properties (including future accessor properties like `.date: DateColumnAccessor`), and all operator overloads (`__add__`, `__eq__`, etc.). Add detailed docstrings.
5.  Update `gaspatchio_core/column/__init__.pyi` to declare the exported proxy classes.
6.  Create `tests/column/test_proxy.py`. Write unit tests for both proxy classes. Focus on:
    *   Correct operator overloading behavior (e.g., `proxy + 1` returns `ExpressionProxy`).
    *   Method calls (`.alias()`, `.cast()`).
    *   Interaction with a mock parent object that implements `_convert_to_expr`.
    *   Test the `__dir__` methods (if they exist) to ensure they list standard methods and potentially future accessors.
7.  Modify `gaspatchio_core/dsl/core.py`: update imports (`from ..column import ColumnProxy, ExpressionProxy`).
8.  Ensure all project tests pass.

Goal: Isolate the proxy classes responsible for expression building into their own module, with tests and stubs.
```

### Step 4: Base Frame

**Goal:** Extract the core `ActuarialFrame` structure and basic methods.

**Tasks:**

1.  Identify the `ActuarialFrame` class in `dsl/core.py`.
2.  Move the class definition to `frame/base.py`.
3.  Include only the essential methods for now: `__init__`, `__getitem__`, `__setitem__`, `_convert_to_expr`, `collect`, `profile`, `with_columns`, `pipe`, `get_column_order`, `show_query_plan`. Exclude tracing, accessor properties/methods, registry interaction, and complex error handling calls (they use the moved `_handle_execution_error` via imports).
4.  Update imports within `ActuarialFrame` for utilities, errors, and proxies (`from ..util import ...`, `from ..errors import ...`, `from ..column import ...`).
5.  Create `frame/__init__.py` (exporting `ActuarialFrame`) and `frame/__init__.pyi`.
6.  Create `frame/base.pyi` with types and docstrings for the included methods.
7.  Write unit tests in `tests/frame/test_base.py` for the basic frame functionality (initialization, item access, simple `with_columns`, `collect` on simple data). Mock the underlying `_df` (Polars LazyFrame) where necessary.
8.  Update the main `gaspatchio_core/__init__.py` façade: change `from .dsl.core import *` to explicitly import `ActuarialFrame` from `.frame` and other remaining symbols from `dsl.core`. Update `gaspatchio_core/__init__.pyi` accordingly.
9.  Run tests.

**LLM Prompt 4:**

```text
Context: Proxy classes are now in `gaspatchio_core/column`. The next major piece is the `ActuarialFrame` class itself from `gaspatchio_core/dsl/core.py`.

Task:
1.  Move the `ActuarialFrame` class definition from `gaspatchio_core/dsl/core.py` to a new file: `gaspatchio_core/frame/base.py`.
2.  Initially, include only the core structure and essential methods: `__init__`, `__getitem__`, `__setitem__`, `_convert_to_expr`, `collect`, `profile`, `with_columns`, `pipe`, `get_column_order`, `_find_similar_columns`, `show_query_plan`.
    *   Ensure methods like `__init__`, `__setitem__`, `collect`, `profile` correctly import and use the previously extracted utilities (`get_default_mode`) and error handlers (`_handle_execution_error`, `_format_column_error`).
    *   Ensure `__getitem__`, `__setitem__`, and `_convert_to_expr` import and use the `ColumnProxy` and `ExpressionProxy` from `..column.proxy`.
    *   Exclude methods/properties related to tracing (`trace`, `_computation_graph`, `_log_query_plan`), accessor registration/properties (`.date`, `.finance`, registry lookups), and direct calls to core Rust functions for now.
3.  Create/update `gaspatchio_core/frame/__init__.py` to export `ActuarialFrame`.
4.  Create `gaspatchio_core/frame/base.pyi` with accurate type hints and docstrings for the included methods and properties of `ActuarialFrame`.
5.  Update `gaspatchio_core/frame/__init__.pyi` to declare the exported `ActuarialFrame`.
6.  Create `tests/frame/test_base.py`. Write unit tests for the basic `ActuarialFrame` functionality:
    *   Initialization with different data types (dict, Polars DF, LazyFrame).
    *   `__getitem__` returning `ColumnProxy`.
    *   `__setitem__` modifying the underlying mock `_df` correctly.
    *   `with_columns` adding expressions.
    *   `collect`/`profile` calling the underlying mock `_df` methods and handling mocked errors via `_handle_execution_error`.
    *   `pipe` correctly applying a function.
7.  Modify the main façade `gaspatchio_core/__init__.py`:
    *   Remove `from .dsl.core import *`.
    *   Add `from .frame import ActuarialFrame`.
    *   Explicitly import any *remaining* necessary symbols directly from `gaspatchio_core.dsl.core` (e.g., `run_model`, accessor classes if they haven't been moved yet).
8.  Update `gaspatchio_core/__init__.pyi` to reflect these explicit imports.
9.  Ensure all project tests pass.

Goal: Establish the core `ActuarialFrame` class in its new location, importing its dependencies (utils, errors, proxies), with basic tests and updated top-level exports.
```

### Step 5: Tracing

**Goal:** Extract the computation tracing logic.

**Tasks:**

1.  Identify tracing-related attributes and methods in `dsl/core.py`'s `ActuarialFrame`: `_computation_graph`, `_tracing`, `trace`, `_log_query_plan`.
2.  Move this logic to `frame/tracing.py`. This might involve creating helper functions or a `Tracer` class used by `ActuarialFrame`.
3.  Modify `frame/base.py`: Import the tracing components from `frame.tracing` and integrate them back into `ActuarialFrame` (e.g., `__init__` initializes tracing attributes, `trace` method calls the extracted logic, `__setitem__` interacts with `_computation_graph` when `_tracing` is true).
4.  Create `frame/tracing.pyi` with types and docstrings.
5.  Write tests in `tests/frame/test_tracing.py` specifically for the `trace` decorator and computation graph capture. Test decorated functions, check the captured graph content.
6.  Run tests.

**LLM Prompt 5:**

```text
Context: The base `ActuarialFrame` is in `gaspatchio_core/frame/base.py`. We now need to extract and reintegrate the computation tracing functionality previously part of this class in `dsl/core.py`.

Task:
1.  Identify tracing-related attributes and methods previously in `ActuarialFrame` (found in the original `dsl/core.py`): `_computation_graph`, `_tracing` flag, the `trace` decorator method, `_log_query_plan`, and the logic within `__setitem__` that appends to `_computation_graph` when `_tracing` is active.
2.  Create a new file `gaspatchio_core/frame/tracing.py`. Move the identified tracing logic here. You might structure this as standalone functions (e.g., `build_trace_decorator(frame_instance)`, `log_query_plan(operations, frame_df)`) or potentially a helper class if state management becomes complex.
3.  Modify `gaspatchio_core/frame/base.py`:
    *   Import the necessary components from `.tracing`.
    *   In `ActuarialFrame.__init__`, initialize tracing-related attributes (e.g., `self._computation_graph = []`, `self._tracing = False`).
    *   Implement the `ActuarialFrame.trace` method, likely calling a function from `.tracing` that generates the actual decorator.
    *   Modify `ActuarialFrame.__setitem__` to conditionally append to `self._computation_graph` by calling logic potentially moved to `.tracing`, when `self._tracing` is True.
    *   Ensure the `trace` decorator's wrapper function correctly handles applying the captured `operations` back to `self._df` after the decorated function runs in 'optimize' mode, possibly using logic moved to `.tracing`. Ensure `_log_query_plan` is called appropriately.
4.  Create `gaspatchio_core/frame/tracing.pyi` with accurate types and docstrings for the extracted tracing functions/classes.
5.  Update `gaspatchio_core/frame/base.pyi` to reflect any changes in `ActuarialFrame`'s public interface related to tracing (e.g., ensure the `trace` method signature is present).
6.  Create `tests/frame/test_tracing.py`. Write unit tests focused *specifically* on the tracing mechanism:
    *   Decorate simple functions with `@frame_instance.trace`.
    *   Verify that operations inside the decorated function are captured in `frame_instance._computation_graph` when mode is 'optimize'.
    *   Verify that the frame's underlying `_df` is updated correctly after the traced function executes in 'optimize' mode.
    *   Verify that the decorated function executes directly in 'debug' mode.
    *   Test that `_log_query_plan` (or its equivalent) gets called when verbose/show_plan is enabled.
7.  Ensure all project tests pass.

Goal: Separate the tracing concern from the base frame logic while ensuring it's correctly reintegrated and testable.
```

---

## Phase 3: Accessors and Extensibility

### Step 6: Registry

**Goal:** Implement the accessor registration mechanism.

**Tasks:**

1.  Create `frame/registry.py`.
2.  Implement the `_ACCESSOR_REGISTRY` dictionary and the `register_accessor` decorator function as specified in `08-refactor.md`.
3.  Create `frame/registry.pyi` with types and docstrings.
4.  Write unit tests in `tests/frame/test_registry.py` for the registration mechanism (registering dummy classes, checking registry content, handling name collisions).
5.  Run tests.

**LLM Prompt 6:**

```text
Context: We need a mechanism to register custom accessor classes (like `.date`, `.finance`) that can be attached to `ActuarialFrame` and `ColumnProxy` instances.

Task:
1.  Create a new file `gaspatchio_core/frame/registry.py`.
2.  Inside `registry.py`, implement the accessor registration system as described in `08-refactor.md`, section 3.1:
    *   Define a module-level dictionary `_ACCESSOR_REGISTRY: dict[str, tuple[type, str]] = {}`.
    *   Define the `register_accessor(name: str, *, kind: str = "column")` decorator factory. This decorator should add the decorated class and its kind ('column' or 'frame') to the `_ACCESSOR_REGISTRY`. Include error handling for duplicate registrations.
3.  Create `gaspatchio_core/frame/registry.pyi` with accurate type hints for the registry dictionary and the decorator, along with clear docstrings explaining their purpose.
4.  Create `tests/frame/test_registry.py`. Write unit tests for the registry:
    *   Define dummy accessor classes for testing.
    *   Test registering frame and column accessors using the `@register_accessor` decorator.
    *   Verify that the `_ACCESSOR_REGISTRY` contains the expected data after registration.
    *   Test that attempting to register the same name twice raises a `ValueError`.
5.  Ensure all project tests pass (no functional changes expected elsewhere yet).

Goal: Implement the core infrastructure for registering custom data accessors.
```

### Step 7: Wire Accessors to Proxies and Frame

**Goal:** Make `ActuarialFrame` and proxies use the registry to dynamically provide accessors.

**Tasks:**

1.  Modify `frame/base.py` (`ActuarialFrame`) and `column/proxy.py` (`ColumnProxy`, `ExpressionProxy`):
    *   Import `_ACCESSOR_REGISTRY` and potentially a helper function from `frame.registry`.
    *   Implement dynamic attribute access (e.g., using `__getattr__` or by defining properties dynamically in `__init__` based on the registry) to instantiate and return the correct accessor class when an attribute like `.date` is accessed. Pass `self` (the frame or proxy instance) to the accessor's constructor.
    *   Implement/update the `__dir__` method in each class to include the names of registered accessors relevant to their kind ('frame' or 'column').
2.  Update `frame/base.pyi` and `column/proxy.pyi` to *declare* the known built-in accessor properties (e.g., `date: DateFrameAccessor`, `finance: FinanceFrameAccessor`). This helps static analysis even though access is dynamic.
3.  Write tests in `tests/frame/test_accessor_wiring.py` and `tests/column/test_accessor_wiring.py` to:
    *   Register dummy accessors.
    *   Verify that accessing `frame.dummy_frame_accessor` or `proxy.dummy_column_accessor` returns an instance of the correct dummy class.
    *   Verify that `dir(frame)` and `dir(proxy)` include the names of the registered dummy accessors.
4.  Run tests.

**LLM Prompt 7:**

```text
Context: The accessor registry (`frame/registry.py`) is implemented. Now, we need to modify `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy` to use this registry to dynamically provide accessors like `.date`.

Task:
1.  Modify `gaspatchio_core/frame/base.py`:
    *   Import the `_ACCESSOR_REGISTRY` from `..frame.registry`.
    *   Implement dynamic attribute lookup for *frame* accessors in `ActuarialFrame`. A common pattern is using `@property` for known accessors or overriding `__getattr__`. For `@property`:
        \`\`\`python
        # Inside ActuarialFrame class
        _date_accessor_instance = None # Cache instance
        @property
        def date(self) -> "DateFrameAccessor": # Forward reference ok in stub
            if self._date_accessor_instance is None:
                AccessorClass, kind = _ACCESSOR_REGISTRY.get("date", (None, None))
                if not AccessorClass or kind != "frame":
                     raise AttributeError("No 'date' frame accessor registered.")
                 # Import locally inside method to avoid circular deps
                 from ..accessors.date import DateFrameAccessor
                 self._date_accessor_instance = DateFrameAccessor(self) # Pass frame instance
            return self._date_accessor_instance
        \`\`\`
       Adapt this pattern for other known built-in frame accessors (like `.finance`). Use forward references (`"DateFrameAccessor"`) for type hints if needed initially.
    *   Update `ActuarialFrame.__dir__` to include the names of all registered *frame* accessors found in `_ACCESSOR_REGISTRY`.
2.  Modify `gaspatchio_core/column/proxy.py`:
    *   Apply a similar dynamic attribute lookup pattern to `ColumnProxy` and `ExpressionProxy` for *column* accessors (using `_ACCESSOR_REGISTRY` and filtering for `kind='column'`). Define properties like `.date` and `.finance`.
    *   Update `ColumnProxy.__dir__` and `ExpressionProxy.__dir__` to include registered *column* accessor names.
3.  Update `gaspatchio_core/frame/base.pyi`: Explicitly declare the known accessor properties on `ActuarialFrame` (e.g., `date: DateFrameAccessor`). Import the accessor types.
4.  Update `gaspatchio_core/column/proxy.pyi`: Explicitly declare the known accessor properties on `ColumnProxy` and `ExpressionProxy` (e.g., `date: DateColumnAccessor`). Import the accessor types.
5.  Create tests (e.g., `tests/frame/test_accessor_wiring.py`, `tests/column/test_accessor_wiring.py`):
    *   Use `unittest.mock.patch.dict` to temporarily add dummy frame and column accessors to `frame.registry._ACCESSOR_REGISTRY` for testing.
    *   Instantiate `ActuarialFrame` and proxies.
    *   Assert that accessing the registered dummy accessor name (e.g., `frame.dummy_frame_acc`) returns an instance of the dummy class.
    *   Assert that `dir(frame)` and `dir(proxy)` include the names of the relevant registered dummy accessors.
    *   Assert that accessing an unregistered name raises an `AttributeError`.
6.  Ensure all project tests pass.

Goal: Connect the registry to the core classes, enabling dynamic accessor discovery and usage, verified by tests.
```

### Step 8: Extract Date Accessor

**Goal:** Move the first concrete accessor (`.date`) into its own module.

**Tasks:**

1.  Create `accessors/date.py`.
2.  Move the `DateFrameAccessor` and `DateColumnAccessor` class definitions from `dsl/core.py` (or wherever they currently reside after previous steps, possibly still inline properties) to `accessors/date.py`.
3.  Add the `@register_accessor("date", kind="frame")` and `@register_accessor("date", kind="column")` decorators to the respective classes. Import `register_accessor` from `..frame.registry`.
4.  Update `accessors/__init__.py` to import `accessors.date` (this ensures the decorators run and register the accessors when `gaspatchio_core` is imported).
5.  Create `accessors/date.pyi` with full types and docstrings for the date accessor methods.
6.  Update `accessors/__init__.pyi`.
7.  Write specific unit tests for the date accessor methods in `tests/accessors/test_date.py`. Mock the frame/column object passed to the accessor's `__init__`.
8.  Remove any old definitions or direct imports of these classes from `dsl/core.py` or `frame/base.py`/`column/proxy.py` (the dynamic wiring should now handle them).
9.  Run tests, ensuring `frame.date.*` and `proxy.date.*` calls work correctly using the newly registered accessors.

**LLM Prompt 8:**

```text
Context: Accessor registration and dynamic wiring are in place. We will now extract the first concrete accessor implementation, the 'date' accessor, from `dsl/core.py` into its dedicated module.

Task:
1.  Create the file `gaspatchio_core/accessors/date.py`.
2.  Locate the `DateFrameAccessor` and `DateColumnAccessor` class definitions in the original `gaspatchio_core/dsl/core.py` (or potentially inline properties in `frame/base.py` / `column/proxy.py` if they were implemented that way). Move these class definitions into `gaspatchio_core/accessors/date.py`.
3.  In `accessors/date.py`:
    *   Import `register_accessor` from `..frame.registry`.
    *   Add the `@register_accessor("date", kind="frame")` decorator to `DateFrameAccessor`.
    *   Add the `@register_accessor("date", kind="column")` decorator to `DateColumnAccessor`.
    *   Ensure these classes correctly receive and store the parent frame/proxy object in their `__init__` (e.g., `self._f` or `self._c`).
4.  Modify `gaspatchio_core/accessors/__init__.py`: Add `from . import date` to ensure the module is loaded and the decorators run upon import of the `accessors` package.
5.  Create `gaspatchio_core/accessors/date.pyi` with complete type signatures and detailed docstrings for all methods within `DateFrameAccessor` and `DateColumnAccessor`.
6.  Update `gaspatchio_core/accessors/__init__.pyi`.
7.  Create `tests/accessors/test_date.py`. Write specific unit tests for the methods within `DateFrameAccessor` and `DateColumnAccessor`.
    *   Use mocking (`unittest.mock.Mock` or `MagicMock`) to simulate the parent frame or column proxy object passed to the accessor's constructor.
    *   Test the logic of each accessor method (e.g., that `date_col.from_excel_serial()` constructs the correct Polars expression).
8.  Remove any leftover definitions or direct imports of `DateFrameAccessor`/`DateColumnAccessor` from `dsl/core.py` or `frame/base.py`/`column/proxy.py`. The dynamic wiring done in the previous step should now find and use these registered classes.
9.  Ensure all project tests pass. Verify that code previously using `frame.date.*` or `col.date.*` still functions correctly.

Goal: Isolate the date accessor implementation into its own module, register it correctly, provide stubs, and ensure it's testable and integrated via the registry.
```

### Step 9: Extract Finance Accessor

**Goal:** Move the `.finance` accessor, following the pattern from Step 8.

**Tasks:** (Identical pattern to Step 8, but for `FinanceFrameAccessor` / `FinanceColumnAccessor` and `accessors/finance.py`)

**LLM Prompt 9:**

```text
Context: The 'date' accessor has been successfully extracted and registered. Repeat this process for the 'finance' accessor.

Task:
1.  Create the file `gaspatchio_core/accessors/finance.py`.
2.  Locate and move the `FinanceFrameAccessor` and `FinanceColumnAccessor` class definitions into `gaspatchio_core/accessors/finance.py`.
3.  In `accessors/finance.py`:
    *   Import `register_accessor` from `..frame.registry`.
    *   Add the appropriate `@register_accessor("finance", ...)` decorators.
    *   Ensure `__init__` is correct.
4.  Modify `gaspatchio_core/accessors/__init__.py`: Add `from . import finance`.
5.  Create `gaspatchio_core/accessors/finance.pyi` with full types and docstrings.
6.  Update `gaspatchio_core/accessors/__init__.pyi`.
7.  Create `tests/accessors/test_finance.py`. Write specific unit tests for the finance accessor methods, mocking the parent object.
8.  Remove any old definitions/imports of these classes elsewhere.
9.  Ensure all project tests pass, verifying `frame.finance.*` and `col.finance.*` calls.

Goal: Isolate the finance accessor following the established pattern.
```

*(Repeat Step 8/9 pattern for any other built-in accessors like mortality, stats, etc.)*

---

## Phase 4: Core Function Wrappers & Finalization

### Step 10: Extract Core Function Wrappers

**Goal:** Move Python wrappers for Rust core functions.

**Tasks:**

1.  Identify Python functions in `dsl/core.py` that primarily wrap calls to the underlying Rust extension (`gaspatchio_core.functions.*` like `core_fill_series`). Also identify the `ActuarialFrame` methods that expose these (`fill_series`, `floor`, `round`, `round_to_int`).
2.  Move the *wrapper functions* (like the original `core_fill_series` import and any logic around it if it wasn't just a direct call) to `functions/vector.py` (or other appropriate files mirroring the Rust structure). Re-export them from `functions/__init__.py`.
3.  Modify `frame/base.py`: Ensure the `ActuarialFrame` methods (`fill_series`, `floor`, etc.) now import and call the wrappers from `..functions`.
4.  Create `functions/vector.pyi` (and others) with types/docs for the wrapper functions. Update `functions/__init__.pyi`.
5.  Write tests in `tests/functions/test_vector.py` that call the `ActuarialFrame` methods (`frame.floor(...)`) and verify they produce the correct Polars expressions, potentially mocking the underlying `gaspatchio_core.functions` Rust calls if direct testing is difficult.
6.  Remove old definitions/imports from `dsl/core.py`.
7.  Run tests.

**LLM Prompt 10:**

```text
Context: Accessors are extracted. We now focus on the Python functions in `dsl/core.py` that wrap functions implemented in the Rust core (originally imported like `from gaspatchio_core.functions import fill_series as core_fill_series`) and the `ActuarialFrame` methods that expose them.

Task:
1.  Identify the Python functions in `gaspatchio_core/dsl/core.py` that wrap the Rust core functions (e.g., `core_fill_series`, `core_floor`, etc., likely imported from `gaspatchio_core.functions` initially).
2.  Create `gaspatchio_core/functions/vector.py` (assuming these are vector operations, adjust filename if needed). Move the *wrapper logic* (the Python functions themselves, including their imports from the Rust extension) into this file.
3.  Modify `gaspatchio_core/functions/__init__.py` to import and re-export these wrapper functions from `.vector`.
4.  Identify the `ActuarialFrame` methods in `gaspatchio_core/frame/base.py` that provide a high-level interface to these wrappers (e.g., `ActuarialFrame.fill_series`, `.floor`, `.round`, `.round_to_int`).
5.  Modify these `ActuarialFrame` methods in `frame/base.py`: Ensure they now import the wrapper functions from `..functions` (e.g., `from ..functions import floor as floor_wrapper`) and call them, passing the necessary arguments (`self._convert_to_expr(expr)`, etc.).
6.  Create `gaspatchio_core/functions/vector.pyi` with accurate type signatures and docstrings for the wrapper functions.
7.  Update `gaspatchio_core/functions/__init__.pyi` to declare the re-exported wrapper functions.
8.  Update `gaspatchio_core/frame/base.pyi` to ensure the signatures of methods like `ActuarialFrame.floor` are correct.
9.  Create `tests/functions/test_vector.py`. Write tests that call the *`ActuarialFrame` methods* (e.g., `frame.floor(col_proxy, divisor=10)`). Verify that these methods construct and return `ExpressionProxy` objects containing the expected Polars expressions resulting from calling the (potentially mocked) underlying wrapper functions. You might need to mock the actual Rust function import (`gaspatchio_core.functions.floor`) if testing the wrapper logic in isolation is preferred.
10. Remove any related old imports or definitions from `dsl/core.py`.
11. Ensure all project tests pass.

Goal: Separate the Rust function wrappers into a dedicated `functions` module and ensure `ActuarialFrame` uses them correctly.
```

### Step 11: Finalize Public API Exports

**Goal:** Clean up the main `__init__.py` to define the stable public API.

**Tasks:**

1.  Review `gaspatchio_core/__init__.py`. Ensure it explicitly imports and exports only the intended public API symbols (`ActuarialFrame`, `ColumnProxy`, `ExpressionProxy`, `functions` module, maybe specific errors or utilities) from their new submodule locations.
2.  Remove any remaining imports from `dsl.core`.
3.  Update `gaspatchio_core/__init__.pyi` to accurately reflect this final public API surface, including types and docstrings if desired at the top level.
4.  Run tests.

**LLM Prompt 11:**

```text
Context: All major components (`ActuarialFrame`, proxies, accessors, functions, utils, errors) have been extracted into submodules. The final step before cleanup is to define the official public API in the top-level `gaspatchio_core/__init__.py`.

Task:
1.  Modify `gaspatchio_core/__init__.py`:
    *   Remove *all* remaining imports from `.dsl.core`.
    *   Add explicit imports for the intended public API symbols from their respective submodules. This should likely include:
        *   `from .frame import ActuarialFrame`
        *   `from .column import ColumnProxy, ExpressionProxy`
        *   `from . import functions` (to expose the module)
        *   Optionally, specific error classes like `from .errors import PerformanceWarning`
        *   Optionally, key utilities like `from .util import execution_mode`
    *   Define `__all__` if desired to explicitly list the public names.
2.  Modify `gaspatchio_core/__init__.pyi`:
    *   Ensure this stub file accurately reflects the public API defined in `__init__.py`. Declare all exported symbols with their types. Import types from submodules as needed.
3.  Review the original `dsl/core.py` one last time – are there any other top-level functions (like `run_model`) that need to be moved or explicitly exposed? If `run_model` is public, move it (e.g., to `frame/execution.py`) and export it.
4.  Ensure all project tests pass. Test that importing the public symbols directly from `gaspatchio_core` works as expected.

Goal: Define a clean, explicit public API for the package in the top-level `__init__.py` and its corresponding stub file.
```

### Step 12: CI Integration (Mypy & Stubtest)

**Goal:** Add static analysis checks to CI to maintain type safety and stub consistency.

**Tasks:**

1.  Modify the project's CI configuration file (e.g., `.github/workflows/python-ci.yml`):
    *   Add a step to install `mypy` and `pytest` (if not already present).
    *   Add a step to run `mypy --strict .` (or `mypy --strict gaspatchio_core tests`) within the `bindings/python` directory.
    *   Add a step to run `stubtest gaspatchio_core`. Note: `stubtest` often needs the package to be *installed* first, so run it after an installation step (like `pip install .` or `uv pip install .`).
2.  Run the CI pipeline or these commands locally. Fix any errors reported by `mypy` or `stubtest`. This often involves correcting type hints in `.py` or `.pyi` files, or ensuring signatures match between the implementation and the stub.
3.  Commit the CI configuration changes and any code fixes.

**LLM Prompt 12:**

```text
Context: The code refactoring is complete, and the public API is defined. We need to add static analysis tools to the Continuous Integration (CI) pipeline to ensure ongoing code quality and consistency between `.py` files and `.pyi` stubs.

Task:
1.  Locate the primary CI workflow file for Python testing (e.g., `.github/workflows/python-ci.yml` or similar).
2.  Modify the workflow file to add two new checking steps, typically placed after dependency installation and before or after running `pytest`:
    *   **Mypy Check:**
        *   Ensure `mypy` is installed (add `mypy` to dependency installation command if needed).
        *   Add a step that runs `mypy --strict gaspatchio_core tests` (adjust path/target as needed). Run this command from the `bindings/python` directory.
    *   **Stubtest Check:**
        *   Ensure `mypy` is installed (as `stubtest` is part of it).
        *   Ensure the `gaspatchio_core` package itself is installed in the CI environment (`pip install .` or `uv pip install .` within `bindings/python`).
        *   Add a step that runs `stubtest gaspatchio_core` after the package installation. Run this command from the `bindings/python` directory.
3.  Trigger the CI pipeline (e.g., by pushing the changes or manually running it).
4.  Analyze the output of the `mypy` and `stubtest` steps.
    *   If `mypy` reports errors, fix the type annotations in the `.py` or `.pyi` files as indicated.
    *   If `stubtest` reports errors, it means there's a mismatch between the signature in a `.py` file and its corresponding `.pyi` file. Adjust the `.pyi` file (most common) or the `.py` file's type hints to match exactly. Pay attention to argument names, types, return types, and decorators like `@property`.
5.  Iteratively fix errors and re-run CI until both `mypy --strict` and `stubtest` pass cleanly.

Goal: Integrate strict type checking and stub validation into the CI pipeline to automatically catch errors and inconsistencies.
```

### Step 13: Cleanup

**Goal:** Remove the old monolithic file and ensure tests use the new structure.

**Tasks:**

1.  Delete the original `gaspatchio_core/dsl/core.py` file.
2.  Search the `tests/` directory for any remaining imports that might still reference `gaspatchio_core.dsl.core` or import directly from submodules (e.g., `from gaspatchio_core.frame.base import ActuarialFrame`). Refactor these tests to import only from the public API surface (e.g., `from gaspatchio_core import ActuarialFrame`). Exceptions can be made for tests *specifically* targeting internal submodule logic.
3.  Run all tests one final time to ensure everything works after the cleanup.

**LLM Prompt 13:**

```text
Context: All components are extracted, the public API is defined, and CI checks (`mypy`, `stubtest`) are passing. The final step is to remove the original monolithic file and clean up test imports.

Task:
1.  Delete the file `gaspatchio-core/bindings/python/gaspatchio_core/dsl/core.py`.
2.  Review all files within the `gaspatchio-core/bindings/python/tests/` directory.
    *   Search for any import statements that still reference `gaspatchio_core.dsl.core`. Remove or update them.
    *   Search for import statements that import directly from the *submodules* (e.g., `from gaspatchio_core.frame import ActuarialFrame` or `from gaspatchio_core.column.proxy import ColumnProxy`).
    *   Refactor these test imports to use the public API whenever possible (e.g., change `from gaspatchio_core.frame import ActuarialFrame` to `from gaspatchio_core import ActuarialFrame`).
    *   Leave imports from submodules *only* if a test is specifically designed to target internal implementation details of that submodule (which should be less common).
3.  Run the full test suite (`pytest` or `uv run pytest` in `bindings/python`) one last time.
4.  Ensure all tests pass after removing the old file and refactoring test imports.

Goal: Complete the refactoring by removing the legacy `core.py` file and ensuring tests primarily rely on the official public package interface.
```

---

</rewritten_file>
