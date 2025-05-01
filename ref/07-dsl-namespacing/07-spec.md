# ActuarialFrame Accessor Design Specification

This document outlines the implementation plan for the ActuarialFrame accessor design, based on the analysis in `07-analysis.md`.

## 1. Overall Goal

Implement a namespaced accessor system for `ActuarialFrame` and its columns (`ColumnProxy`/`ExpressionProxy`) to provide domain-specific functionality (e.g., `.date`, `.finance`, `.mortality`) in a discoverable, extensible, and functional manner, integrating smoothly with the underlying Polars engine and existing proxy mechanisms.

## 2. Core Design Principles (from 07-analysis.md)

*   **Domain-Specific Nested Accessors:** Separate namespaces for different functional areas (`date`, `finance`, etc.).
*   **Frame vs. Column Distinction:** Clear separation of methods applicable to the whole frame versus individual columns/expressions.
*   **Functional and Immutable:** Accessor methods return new objects (frames or expressions), avoiding in-place mutation by default.
*   **Discoverability & Tooling Friendliness:** Use Python properties, `__dir__`, and `.pyi` stubs for excellent autocompletion and static analysis support.
*   **Integration with Polars:** Leverage Polars expressions and lazy evaluation; coexist with native Polars accessors (`.str`, `.dt`).
*   **Extensibility:** Provide a plugin system (decorators and entry points) for users to add custom accessors.

## 3. Implementation Plan - Iterative Steps

The implementation will proceed in small, testable steps:

1.  **Define Base Accessor Classes:** Create abstract base classes for Frame and Column accessors to establish a common structure.
2.  **Implement Core `Date` Accessor (Column-level):**
    *   Create `DateColumnAccessor`.
    *   Implement a simple method like `from_excel_serial` using Polars expressions.
    *   Write unit tests for `from_excel_serial`.
3.  **Integrate Column Accessor:**
    *   Modify `ColumnProxy` (and potentially `ExpressionProxy`) to instantiate and expose the `DateColumnAccessor` via a `.date` property.
    *   Ensure existing proxy logic (`_delegation.py`) doesn't conflict or is adjusted appropriately.
    *   Add tests to verify `af['col'].date.from_excel_serial()` works.
4.  **Implement Core `Date` Accessor (Frame-level):**
    *   Create `DateFrameAccessor`.
    *   Implement a simple frame method, e.g., `create_timeline(start_col, end_col)` (initially maybe just returning a placeholder or a basic structure).
    *   Write unit tests.
5.  **Integrate Frame Accessor:**
    *   Modify `ActuarialFrame` to instantiate and expose the `DateFrameAccessor` via a `.date` property.
    *   Add tests to verify `af.date.create_timeline(...)` can be called.
6.  **Refine Proxy/Delegation for Namespaces:** Ensure that accessing `af.date` or `af['col'].date` correctly returns the accessor instance and that method calls on the accessor work. Verify interaction with `_delegation.py`'s `_autopatch` and potentially exclude accessor names from dynamic delegation.
7.  **Add `.pyi` Stubs:** Create/update `gaspatchio_core/dsl.pyi` (or similar) to provide static type information for the new accessors and their methods, enhancing IDE/tooling support.
8.  **Develop Decorator-Based Plugin System:**
    *   Implement `register_accessor` decorator.
    *   Define how the decorator adds the accessor to `ActuarialFrame`/`ColumnProxy`.
    *   Write tests demonstrating registration and usage of a custom accessor.
9.  **Develop Entry-Point Plugin System:**
    *   Define an entry point group (e.g., `"gaspatchio.accessors"`).
    *   Implement logic (likely on import or initialization) to discover and register plugins via `importlib.metadata`.
    *   Write tests involving a dummy installable package defining an entry point.
10. **Expand Accessor Methods:** Incrementally add more methods to the `date` accessor and potentially introduce other core accessors (`finance`, etc.) following the established pattern.

## 4. LLM Prompts for Implementation (Test-Driven)

Each prompt represents a distinct step from the plan above.

---

### Prompt 1: Define Base Accessor Classes

```text
Task: Define abstract base classes for Frame and Column accessors in `gaspatchio_core.dsl.accessors.base`.

Context:
We are building a namespaced accessor system for `ActuarialFrame`. We need base classes to enforce structure for different accessor types (frame-level vs. column/expression-level). These bases will ensure consistency and hold references to the parent object (`ActuarialFrame` or the column proxy).

Requirements:
1.  Create a new file: `gaspatchio_core/dsl/accessors/base.py`.
2.  Define `BaseFrameAccessor`:
    *   Should be an abstract base class (use `abc.ABC`).
    *   Should accept an `ActuarialFrame` instance in `__init__` and store it (e.g., as `self._frame`).
3.  Define `BaseColumnAccessor`:
    *   Should be an abstract base class.
    *   Should accept a column proxy instance (initially maybe type hint as `Any`, later refine to `ColumnProxy | ExpressionProxy`) in `__init__` and store it (e.g., as `self._proxy`).
4.  Add basic docstrings explaining the purpose of each class.
5.  Add a corresponding test file `tests/dsl/accessors/test_base.py`.
6.  Write simple tests in `test_base.py` to verify:
    *   Instances of concrete subclasses (even dummy ones for the test) store the parent object correctly.
    *   Attempting to instantiate the base classes directly raises `TypeError`.

Files to Modify:
- Create: `gaspatchio_core/dsl/accessors/base.py`
- Create: `tests/dsl/accessors/test_base.py`
- Potentially add `gaspatchio_core/dsl/accessors/__init__.py` if it doesn't exist.

Reference Code (`core.py`):
- Note how `ColumnProxy` and `ExpressionProxy` store `_parent`. Our accessors will do something similar.

Analysis Quote (`07-analysis.md`):
> "Implementation: We'll create accessor classes for each domain and each context. For instance, a `DateFrameAccessor` class ... and a `DateColumnAccessor` class ... `ActuarialFrame` will have a property `date` that instantiates a `DateFrameAccessor(self)`. Similarly, our internal `ColumnProxy` class ... will have a `date` property that returns a `DateColumnAccessor(column=self)`. This design means the accessor classes can hold a reference to the parent object (frame or column) and operate on it."
```

---

### Prompt 2: Implement Core `Date` Column Accessor

```text
Task: Implement the initial `DateColumnAccessor` with a `from_excel_serial` method in `gaspatchio_core.dsl.accessors.date`.

Context:
Building on the base classes, we'll create the first concrete accessor for date-related column operations. The first method will convert Excel serial numbers to dates using Polars expressions. This accessor should inherit from `BaseColumnAccessor`.

Requirements:
1.  Create a new file: `gaspatchio_core.dsl.accessors.date.py`.
2.  Import `BaseColumnAccessor` from `.base`.
3.  Define `DateColumnAccessor(BaseColumnAccessor)`:
    *   Implement the `__init__` method calling `super().__init__`.
4.  Implement the method `from_excel_serial(self, epoch: str = "1900") -> ExpressionProxy`:
    *   This method should operate on the column represented by `self._proxy`.
    *   Get the underlying Polars expression using `self._proxy._expr` if it's an `ExpressionProxy` or `pl.col(self._proxy.name)` if it's a `ColumnProxy`. You might need a helper or conditional logic to handle both proxy types robustly. (Review `_convert_to_expr` in `core.py` for inspiration).
    *   Construct a Polars expression to convert the Excel serial number to a date. A common formula involves adding the number of days (minus adjustments for Excel's leap year bug) to the epoch date. Consider potential performance and edge cases (e.g., non-numeric input).
        *   Example Polars logic might involve: `base_expr = self._get_polars_expr()` then `(pl.lit(epoch_date) + pl.duration(days=base_expr - adjustment))` cast to `pl.Date`. Define `epoch_date` and `adjustment` based on the `epoch` parameter.
    *   The method must return a *new* `ExpressionProxy` wrapping the resulting Polars date expression. You'll need access to the parent `ActuarialFrame` (`self._proxy._parent`) to instantiate the `ExpressionProxy`.
5.  Add imports for `polars as pl`, `ExpressionProxy`, `ColumnProxy`, `BaseColumnAccessor`, and necessary date/time types.
6.  Add docstrings explaining the accessor and its method.
7.  Create a corresponding test file `tests/dsl/accessors/test_date_col.py`.
8.  Write unit tests in `test_date_col.py`:
    *   Test `from_excel_serial` with various inputs (integers, floats representing Excel dates).
    *   Test different epochs if supported (e.g., "1900", "1904").
    *   Verify the output is an `ExpressionProxy`.
    *   Verify the underlying Polars expression produces the correct date values when executed on a sample `ActuarialFrame`. Use `af.collect()` within the test.

Files to Modify:
- Create: `gaspatchio_core/dsl/accessors/date.py`
- Create: `tests/dsl/accessors/test_date_col.py`
- Update: `gaspatchio_core/dsl/accessors/__init__.py` (export `DateColumnAccessor`)

Reference Code (`core.py`, `_delegation.py`):
- `_convert_to_expr`: Handles converting proxies/values to Polars expressions.
- `ExpressionProxy`: The required return type.
- `_wrap`: Might be useful for wrapping the final Polars expression.

Analysis Quote (`07-analysis.md`):
> "Column-level: `af["raw_date"].date.from_excel_serial()` – converts an Excel serial number in that column to an actual date."
> "All accessor methods will follow a functional style... they will return a new object (new frame or new column/expression)."
```

---

### Prompt 3: Integrate `Date` Column Accessor

```text
Task: Integrate the `DateColumnAccessor` into `ColumnProxy` and `ExpressionProxy` via a `.date` property.

Context:
Now that we have a `DateColumnAccessor`, we need to make it accessible via the `.date` attribute on column/expression proxies (e.g., `af['col'].date`). This involves adding a property to the proxy classes that instantiates the accessor. We also need to ensure this doesn't conflict with the existing dynamic delegation in `_delegation.py`.

Requirements:
1.  Modify `gaspatchio_core.dsl.core.py`:
    *   Import `DateColumnAccessor` (use a conditional import for type checking if needed to avoid circularity: `if TYPE_CHECKING: from .accessors.date import DateColumnAccessor`).
    *   In `ColumnProxy`, add a `@property` method named `date(self) -> 'DateColumnAccessor'`:
        *   This property should return `DateColumnAccessor(self)`.
    *   In `ExpressionProxy`, add a similar `@property` method named `date(self) -> 'DateColumnAccessor'`:
        *   This property should return `DateColumnAccessor(self)`.
2.  Modify `gaspatchio_core.dsl._delegation.py`:
    *   Explicitly *exclude* `"date"` (and potentially other future accessor names) from the `_autopatch` logic. The goal is to ensure that accessing `.date` *always* returns our specific accessor instance, not a dynamically proxied Polars attribute (even though Polars has `Expr.dt`, we want our own `.date`).
    *   One way is to add `"date"` to a `_RESERVED_ACCESSOR_NAMES` set and check against it within `_autopatch` before calling `setattr`.
3.  Update relevant test files (e.g., create `tests/dsl/test_integration.py` or add to existing tests):
    *   Verify that `af['some_col'].date` returns an instance of `DateColumnAccessor`.
    *   Verify that `(af['some_col'] + 1).date` (an `ExpressionProxy`) returns an instance of `DateColumnAccessor`.
    *   Verify that calling a method works: `af['excel_date_col'].date.from_excel_serial()` returns an `ExpressionProxy` and produces correct results when collected.
    *   Verify that standard Polars delegation still works for non-accessor names (e.g., `af['col'].is_null()` or potentially `af['date_col'].dt.year()` if we don't block `.dt` explicitly yet).

Files to Modify:
- `gaspatchio_core/dsl/core.py`
- `gaspatchio_core/dsl/_delegation.py`
- Test files (e.g., create `tests/dsl/test_integration.py`)

Analysis Quote (`07-analysis.md`):
> "Similarly, our internal `ColumnProxy` class (which behaves like a polars Series/Expr) will have a `date` property that returns a `DateColumnAccessor(column=self)`."
> "We must also ensure we coexist with Polars' own accessors when relevant... A safer approach is composition... We implement our own `__getitem__` to return a `ColumnProxy`... We can still expose Polars methods by implementing `__getattr__` on `ColumnProxy`: if an attribute name doesn't match any of our custom accessors... we forward it..." (Our `@property` approach preempts `__getattr__` for "date").
```

---

### Prompt 4: Implement Core `Date` Frame Accessor

```text
Task: Implement the initial `DateFrameAccessor` with a basic `create_timeline` method in `gaspatchio_core.dsl.accessors.date`.

Context:
Complementing the column accessor, we now create the frame-level accessor for date operations that involve the whole `ActuarialFrame` or multiple columns. We'll start with a placeholder or simplified `create_timeline` method.

Requirements:
1.  Modify `gaspatchio_core.dsl.accessors.date.py`:
    *   Import `BaseFrameAccessor` from `.base`.
    *   Import `ActuarialFrame` (use `TYPE_CHECKING` guard).
    *   Define `DateFrameAccessor(BaseFrameAccessor)`:
        *   Implement `__init__` calling `super().__init__`.
2.  Implement a method `create_timeline(self, start_col: str, end_col: str, freq: str = "1M") -> 'ActuarialFrame'`:
    *   This method operates on the `ActuarialFrame` stored in `self._frame`.
    *   Access columns via `self._frame[start_col]` and `self._frame[end_col]`.
    *   **Initial Implementation:** For this step, the method can simply return `self._frame` without modification, or perhaps add placeholder columns using `self._frame._df.with_columns(...)`. The goal is to establish the structure. A more complex implementation using `pl.date_ranges` can follow later.
    *   The method *must* return a *new* `ActuarialFrame` instance wrapping the modified underlying Polars frame (`self._frame._df`). Instantiate it like `ActuarialFrame(new_polars_df)`.
3.  Add docstrings.
4.  Modify `tests/dsl/accessors/test_date_col.py` (or create `test_date_frame.py`):
    *   Add tests for `DateFrameAccessor`.
    *   Test `create_timeline`:
        *   Verify it returns an `ActuarialFrame`.
        *   Verify the returned frame is a *new* instance (check object identity).
        *   (Optional: If placeholder columns are added, verify their existence).

Files to Modify:
- `gaspatchio_core/dsl/accessors/date.py`
- Test files (e.g., `tests/dsl/accessors/test_date_col.py` or create `test_date_frame.py`)
- Update `gaspatchio_core/dsl/accessors/__init__.py` (export `DateFrameAccessor`)

Analysis Quote (`07-analysis.md`):
> "Frame-level: `af.date.create_timeline(start_col, end_col, freq)` – perhaps creates a new DataFrame (or adds columns) representing a timeline between two date columns."
> "We'll create accessor classes for each domain and each context. For instance, a `DateFrameAccessor` class with methods like `create_timeline`..."
> "All accessor methods will follow a functional style... they will return a new object (new frame or new column/expression)."
```

---

### Prompt 5: Integrate `Date` Frame Accessor

```text
Task: Integrate the `DateFrameAccessor` into `ActuarialFrame` via a `.date` property.

Context:
Similar to the column accessor integration, we now make the frame-level `DateFrameAccessor` available via `af.date`.

Requirements:
1.  Modify `gaspatchio_core.dsl.core.py`:
    *   Import `DateFrameAccessor` (use `TYPE_CHECKING` guard).
    *   In `ActuarialFrame`, add a `@property` method named `date(self) -> 'DateFrameAccessor'`:
        *   This property should return `DateFrameAccessor(self)`.
2.  Modify `gaspatchio_core.dsl._delegation.py`:
    *   Ensure the check implemented in Prompt 3 (e.g., `_RESERVED_ACCESSOR_NAMES`) also prevents `_autopatch` from overriding the `.date` property on `ActuarialFrame` itself (if `_autopatch` were ever adapted to patch `ActuarialFrame`, which it currently doesn't seem to). It's good practice to ensure the exclusion applies broadly.
3.  Update integration tests (e.g., `tests/dsl/test_integration.py`):
    *   Verify that `af.date` returns an instance of `DateFrameAccessor`.
    *   Verify that calling a method works: `af.date.create_timeline(...)` returns an `ActuarialFrame`.

Files to Modify:
- `gaspatchio_core/dsl/core.py`
- `gaspatchio_core/dsl/_delegation.py` (confirm exclusion logic)
- Test files (e.g., `tests/dsl/test_integration.py`)

Analysis Quote (`07-analysis.md`):
> "`ActuarialFrame` will have a property `date` that instantiates a `DateFrameAccessor(self)`."
> "By having named accessors (`date`, `finance`, etc.) as actual attributes, we immediately benefit from Python's introspection."
```

---

### Prompt 6: Refine Proxy/Delegation for Namespaces

```text
Task: Review and refine the interaction between accessor properties and the dynamic delegation mechanism in `_delegation.py`.

Context:
We've added `.date` properties that should take precedence over dynamic delegation for that specific name. This step involves confirming the mechanism works correctly and doesn't have unintended side effects. It also includes ensuring `__dir__` includes our custom accessors.

Requirements:
1.  **Review `_delegation.py`:**
    *   Confirm that the logic added in Prompt 3 correctly prevents `_autopatch` from adding a `DelegatorDescriptor` for `"date"` (and any other reserved accessor names) to `ColumnProxy` and `ExpressionProxy`.
    *   Ensure the `__dir__` method added by `_autopatch` correctly *includes* `"date"` in the list of attributes for `ColumnProxy` and `ExpressionProxy`. It should merge the dynamically patched attributes with explicitly defined ones like our `@property`.
2.  **Review `core.py`:**
    *   Add a `__dir__` method to `ActuarialFrame` if it doesn't have one. This method should list standard attributes, columns (`self._df.columns`), and explicitly defined accessor properties like `.date`.
3.  **Refine Tests (`tests/dsl/test_integration.py`):**
    *   Add tests using `dir(af)` and `dir(af['col'])` to assert that `"date"` is present in the output.
    *   Add tests to specifically confirm that accessing a *different* Polars attribute (e.g., `af['str_col'].str.contains(...)` or `af['num_col'].abs()`) still works correctly via the delegation mechanism, demonstrating that excluding `"date"` didn't break other dynamic proxies.
    *   Test accessing `.date` on a column that *doesn't* exist yet (if possible within the proxy structure) - what should happen? Define and test the expected behavior (likely an error during method execution, not attribute access).

Files to Modify:
- `gaspatchio_core/dsl/_delegation.py`
- `gaspatchio_core/dsl/core.py`
- `tests/dsl/test_integration.py`

Analysis Quote (`07-analysis.md`):
> "Discoverability and Tooling Friendliness: By having named accessors (`date`, `finance`, etc.) as actual attributes, we immediately benefit from Python's introspection. Calling `dir(af)` will list `date`, `finance`, etc... We will also override `__dir__` on `ActuarialFrame` and the column proxy to ensure all custom accessor names... appear."
```

---

### Prompt 7: Add `.pyi` Stubs

```text
Task: Create or update a `.pyi` stub file to provide static type hints for the new accessor system.

Context:
To improve IDE autocompletion, static analysis (MyPy, Pyright), and LLM understanding, we need to provide explicit type hints for the dynamically added accessor properties and their methods.

Requirements:
1.  Locate or create the stub file (e.g., `gaspatchio_core/dsl.pyi` or `gaspatchio_core/dsl/core.pyi`).
2.  In the stub file:
    *   Declare the `ActuarialFrame` class. Add the `.date` property with its type hint: `date: DateFrameAccessor`.
    *   Declare the `ColumnProxy` class. Add the `.date` property: `date: DateColumnAccessor`.
    *   Declare the `ExpressionProxy` class. Add the `.date` property: `date: DateColumnAccessor`.
    *   Declare the `DateFrameAccessor` class with signatures for its methods (e.g., `create_timeline(...) -> ActuarialFrame:`).
    *   Declare the `DateColumnAccessor` class with signatures for its methods (e.g., `from_excel_serial(...) -> ExpressionProxy:`).
    *   Ensure necessary imports (e.g., `from .accessors.date import DateFrameAccessor, DateColumnAccessor`) are present *within* the stub file.
3.  Configure static analysis tools (like MyPy if used in the project) to pick up these stubs.
4.  Manually verify in an IDE (like VSCode with Pylance/Pyright) that:
    *   Typing `af.` shows `date` with the correct type.
    *   Typing `af.date.` shows `create_timeline` with its signature.
    *   Typing `af['col'].date.` shows `from_excel_serial` with its signature.

Files to Modify:
- Create or update: `gaspatchio_core/dsl.pyi` (or similar path)

Analysis Quote (`07-analysis.md`):
> "Type Hints (.pyi stubs): To further assist IDEs and static analyzers, we will ship a `.pyi` stub file... In the stub, `ActuarialFrame` can be defined as: `class ActuarialFrame: @property def date(self) -> DateFrameAccessor: ...` ... This ensures tools like MyPy, PyCharm, VSCode, and even LLMs... can see the full API surface."
```

---

### Prompt 8: Develop Decorator-Based Plugin System

```text
Task: Implement a decorator (`@register_accessor`) for adding custom accessors to `ActuarialFrame` and proxies.

Context:
To allow users to extend `ActuarialFrame` with their own domain logic (e.g., a `.risk` accessor), we need a registration mechanism. A decorator is a user-friendly way to achieve this.

Requirements:
1.  Create a new file: `gaspatchio_core/dsl/plugins.py` (or similar).
2.  Define a registry dictionary (e.g., `_ACCESSOR_REGISTRY = {"frame": {}, "column": {}}`) at the module level to store registered accessor classes.
3.  Implement the decorator function `register_accessor(name: str, *, kind: str = "column")`:
    *   `kind` should be validated (`"column"` or `"frame"`).
    *   The decorator should take an accessor class as input.
    *   It should store the class in the `_ACCESSOR_REGISTRY` under the given `name` and `kind`.
    *   Crucially, it needs to *dynamically add a property* to the target class (`ActuarialFrame` for `kind="frame"`, `ColumnProxy` and `ExpressionProxy` for `kind="column"`) that instantiates the registered accessor class, similar to how we added `.date` manually. This might involve modifying the target class directly or using a metaclass approach (metaclass is likely more complex). Directly modifying might be simpler initially:
        \`\`\`python
        def register_accessor(...):
            def decorator(cls):
                _ACCESSOR_REGISTRY[kind][name] = cls
                target_classes = ... # Get ActuarialFrame or ColumnProxy/ExpressionProxy
                for target_cls in target_classes:
                    setattr(target_cls, name, property(lambda self: cls(self)))
                return cls
            return decorator
        \`\`\`
    *   Ensure the registration logic handles potential name collisions (e.g., warn or raise error if registering an existing name).
    *   Ensure the dynamic property addition works correctly with type hinting (it likely won't automatically update stubs, this is a known limitation).
4.  Modify `_delegation.py`'s `_autopatch` logic (and `__dir__` methods) to be aware of the `_ACCESSOR_REGISTRY`. Dynamically added accessors should also be excluded from `_autopatch` and included in `__dir__`.
5.  Create a test file `tests/dsl/test_plugins.py`.
6.  Write tests:
    *   Define a dummy `RiskColumnAccessor` and `RiskFrameAccessor` in the test file.
    *   Register them using `@register_accessor("risk", kind="column")` and `@register_accessor("risk", kind="frame")`.
    *   Verify that `af.risk` and `af['col'].risk` return instances of the respective dummy accessors *after* the module containing the registration has been imported.
    *   Verify methods on the dummy accessors can be called.
    *   Verify `"risk"` appears in `dir(af)` and `dir(af['col'])`.

Files to Modify:
- Create: `gaspatchio_core/dsl/plugins.py`
- Create: `tests/dsl/test_plugins.py`
- Modify: `gaspatchio_core/dsl/core.py` (Import registration module? Add properties dynamically?)
- Modify: `gaspatchio_core/dsl/_delegation.py` (Integrate with registry)

Analysis Quote (`07-analysis.md`):
> "Decorator Registration: Similar to Pandas/Polars, we offer a decorator `actframe.register_accessor(name: str, *, kind: str = "column"|"frame")`. A user could write: `@actframe.register_accessor("risk", kind="column") class RiskMetricsAccessor: ...` This would attach a `.risk` accessor..."
> "Under the hood, `register_accessor` will set the attribute on the target class and perhaps add it to a registry for introspection."
```

---

### Prompt 9: Develop Entry-Point Plugin System

```text
Task: Implement discovery and registration of accessors via package entry points.

Context:
To allow seamless integration of third-party accessor packages, we'll use Python's entry points mechanism. `ActuarialFrame` should automatically discover and register accessors defined in installed packages.

Requirements:
1.  Modify `gaspatchio_core.dsl.plugins.py`:
    *   Define an entry point group name (e.g., `ENTRY_POINT_GROUP = "gaspatchio.accessors"`).
    *   Create a function `discover_plugins()`:
        *   Use `importlib.metadata.entry_points()` to find entry points in our group.
        *   Iterate through the found entry points.
        *   Load the accessor class referenced by the entry point (`entry_point.load()`).
        *   Use the `register_accessor` decorator (or its underlying logic) to register the loaded class. The name and kind (`"frame"`/`"column"`) might need to be defined by the entry point itself (e.g., entry point name format `frame.risk` or `column.risk`, or the loaded object could have attributes). Decide on a convention.
        *   Handle potential errors during loading or registration gracefully (e.g., log warnings).
    *   Call `discover_plugins()` automatically, perhaps when the `plugins` module is first imported or when an `ActuarialFrame` is first initialized. Be mindful of import-time side effects.
2.  Modify `tests/dsl/test_plugins.py`:
    *   Simulate an installed package with an entry point. This is tricky in tests. One approach is to use `unittest.mock` to patch `importlib.metadata.entry_points` to return a dummy `EntryPoint` object pointing to a locally defined dummy accessor class within the test file.
    *   Write a test that verifies an accessor defined only via the mocked entry point becomes available on `ActuarialFrame`/proxies after discovery is triggered.
3.  Document the entry point convention for plugin authors (e.g., how to name entry points, what the loaded object should provide).

Files to Modify:
- `gaspatchio_core/dsl/plugins.py`
- `tests/dsl/test_plugins.py`

Analysis Quote (`07-analysis.md`):
> "Entry Point Plugins: We designate an entry point group, e.g., `"actuarialframe.accessors"`. Plugin packages can declare entry points... On `ActuarialFrame` initialization (or module import), we scan `importlib.metadata.entry_points()` for our group and automatically import and register those accessors."
> "This way, if an actuary has installed a plugin, they get the new `.mortality` or `.risk` namespace without any extra code."
```

---

### Prompt 10: Expand Accessor Methods & Add Finance Accessor

```text
Task: Add more methods to the `Date` accessors and implement a basic `Finance` accessor.

Context:
Now that the core infrastructure is in place, we can expand the functionality by adding more useful methods to the existing `.date` accessor and introducing a new `.finance` accessor following the same pattern.

Requirements:
1.  Modify `gaspatchio_core.dsl.accessors.date.py`:
    *   Implement the `DateFrameAccessor.create_timeline` method more fully, using Polars expressions like `pl.date_ranges` to generate the timeline columns.
    *   Add other useful date methods (e.g., `DateColumnAccessor.yearfrac`, `DateColumnAccessor.to_period`, `DateFrameAccessor.add_duration`). Implement using Polars expressions and return `ExpressionProxy` or `ActuarialFrame` as appropriate.
2.  Create `gaspatchio_core.dsl.accessors.finance.py`:
    *   Define `FinanceColumnAccessor(BaseColumnAccessor)` and `FinanceFrameAccessor(BaseFrameAccessor)`.
    *   Implement basic finance methods, e.g., `FinanceColumnAccessor.discount(self, rate_expr, n_periods_expr)` or `FinanceFrameAccessor.present_value(self, cashflow_col, rate_col)`. Use Polars expressions.
3.  Modify `gaspatchio_core.dsl.core.py`:
    *   Add the `.finance` property to `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy`, instantiating the finance accessors.
4.  Modify `gaspatchio_core.dsl._delegation.py`:
    *   Add `"finance"` to the set of reserved names excluded from `_autopatch`.
5.  Update `.pyi` stubs:
    *   Add signatures for the new date methods.
    *   Add the `.finance` property hints to `ActuarialFrame`/proxies.
    *   Add declarations for `FinanceFrameAccessor`, `FinanceColumnAccessor`, and their methods.
6.  Add extensive tests:
    *   In `test_date_*.py`, add tests for the new date methods.
    *   Create `tests/dsl/accessors/test_finance_*.py` and test the new finance methods thoroughly.
    *   Update `test_integration.py` to verify `af.finance` and `af['col'].finance` work and appear in `dir()`.

Files to Modify:
- `gaspatchio_core/dsl/accessors/date.py`
- Create: `gaspatchio_core/dsl/accessors/finance.py`
- `gaspatchio_core/dsl/core.py`
- `gaspatchio_core/dsl/_delegation.py`
- Stub file (`.pyi`)
- Test files (`test_date_*.py`, create `test_finance_*.py`, `test_integration.py`)
- Update `gaspatchio_core/dsl/accessors/__init__.py`

Analysis Quote (`07-analysis.md`):
> Example Usage sections provide ideas for methods like `add_duration`, `apply_curve`, `discount`.
> The overall design supports adding more domains like `.finance`, `.mortality`.
```

---

</rewritten_file>
