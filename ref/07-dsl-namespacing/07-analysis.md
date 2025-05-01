# ActuarialFrame Accessor and Namespacing Architecture

## Insights from Existing Libraries

### Polars: Namespaces and Expression vs. Series Context

Polars uses namespaced accessors (like `.str`, `.dt`, `.arr` for list, etc.) to group domain-specific methods on columns. Internally, Polars defines separate accessor classes for different contexts – one for expressions (lazy column operations) and one for series (eager column data) – each with methods appropriate to that context ￼ ￼. For example, `pl.Expr.str.contains()` returns a new expression, while `pl.Series.str.contains()` executes immediately and returns a Series. These accessors improve API organization and discoverability by clustering dozens of string or datetime functions under a single attribute instead of the top-level namespace. Polars registers its accessors dynamically: it keeps a registry of accessor names (e.g. "str", "dt" in an internal `_accessors` set) and attaches the corresponding class as a property on the base class ￼. This means a user can write `col.str.split()` or `col.dt.year()` and get autocompletion for all string or datetime methods.

Polars' approach cleanly separates frame-level operations from column-level (expression) operations. A Polars DataFrame doesn't directly have a `.str` or `.dt` (those are column-specific), but one can register custom frame accessors if needed ￼. Polars provides decorators like `@pl.api.register_expr_namespace("name")` to let library authors add new accessor namespaces to the expression API ￼. (Similar decorators exist for DataFrame, Series, and LazyFrame ￼.) This extensibility is intended for domain-specific extensions – exactly the scenario for `ActuarialFrame`. Notably, Polars forbids overriding built-in accessors like `.str` or `.dt` ￼, preventing name collisions. Instead, new domains get their own namespace (e.g., `.greetings` in Polars' docs example) ￼ ￼.

**Pros:** Polars' namespacing keeps the API surface clean and logical. Column methods are highly discoverable (type `df.column_name.str.` in an IDE to see all string functions). This aligns with our need for high discoverability for both humans and AI assistants. Polars also demonstrates efficient functional/immutable usage – expressions are built up and then materialized, without in-place mutation. This encourages a declarative style that we can emulate in `ActuarialFrame`.

**Cons:** A challenge with Polars' dynamic approach is static type introspection. Because accessors are added at runtime, static type checkers and IDEs may not know about custom ones by default ￼. In Polars, custom accessors don't automatically appear in type hints, causing tools like MyPy or Pyright to complain or miss autocompletion ￼. Polars' community has suggested adding dummy `__getattr__` definitions or stub files to mitigate this ￼. This is a key consideration for `ActuarialFrame`: we want dynamic extensibility and strong IDE/LLM support. We'll need to augment the dynamic approach with static hints (e.g. providing `.pyi` stubs) to get "the best of both."

### Pandas and Xarray: Accessor Patterns and Extensibility

Pandas pioneered this accessor pattern with attributes like `.dt` (for datetime components) and `.str` (string methods) on Series. These are implemented via accessor classes (e.g. `DatetimeProperties`) and are only available when the data dtype is appropriate – otherwise accessing `.dt` on a non-datetime series raises an `AttributeError` ￼. This pattern ensures correctness (you can't call `.dt` on an integer column) and mirrors how `ActuarialFrame` might conditionally expose certain actuarial methods only on valid data types. Xarray, a library for labeled multi-dimensional data, copied this pattern: Xarray DataArray provides a `.dt` accessor for datetime fields, giving properties like `.dt.dayofyear` similar to Pandas ￼ ￼. Both Pandas and Xarray thereby confirm that namespacing by domain (datetime, string, etc.) leads to an intuitive, discoverable API: users naturally type `.dt` to explore datetime operations ￼.

Extensibility in Pandas is available via the `pandas.api.extensions.register_*_accessor` decorators. One can register a custom accessor on DataFrame or Series by naming it (e.g. "geo" for geospatial) ￼. Under the hood, Pandas will attach your accessor object to the class so that `df.geo` returns an instance of your accessor, initialized with the dataframe ￼ ￼. This is analogous to Polars' approach, though Pandas additionally encourages raising `AttributeError` in your accessor `__init__` if the data is incompatible (to mimic the `.dt` behavior) ￼.

**Pros:** The Pandas/xarray model shows that even in a dynamic language like Python, a consistent accessor design can feel static and reliable to users. By grouping functionality, it avoids polluting the core namespace (e.g., imagine if every string method were a top-level DataFrame method – a mess!). It also reinforces using domain language: an actuary using `ActuarialFrame` would expect to find date conversion tools under a `.date` namespace, much as a Pandas user expects `.dt` for datetime.

**Cons:** As with Polars, these accessors are dynamically added. Pandas does not automatically inform static analyzers of custom accessors either – developers sometimes resort to workarounds for IDE autocompletion (like creating dummy subclasses in `TYPE_CHECKING` blocks) ￼. This underscores that for `ActuarialFrame`, if we rely on dynamic attachment, we should accompany it with type hints or stub files for tooling. Another minor drawback is that using accessors means an extra attribute lookup in code; for example `af["col"].date.function()` vs perhaps a direct function `date_function(af["col"])`. But this trade-off is worth the clarity and organization – as our goal is code that "an experienced actuary would be delighted to have written" ￼, clarity is paramount.

### Pydantic: Plugins and Introspectable APIs

Pydantic isn't a data frame library, but it offers lessons in extensibility and introspection. Pydantic models are highly introspectable: you can programmatically get field names, types, and even generate JSON schemas. This introspection is great for tools and LLMs. In fact, Pydantic advertises itself as "playing nicely with your linters/IDE/brain" ￼ – meaning its API is designed to be predictable and clear. For `ActuarialFrame`, adopting a similar philosophy means using standard Python conventions (classes, attributes with clear names, type hints) so that both static tools and "brains" (human or AI) can easily understand the API.

On the extensibility front, Pydantic 2 introduced a plugin system that uses entry points for discovery ￼ ￼. A plugin can hook into Pydantic's validation process by registering via `pyproject.toml` (so it's auto-discovered) and implementing specific hook functions (e.g., to alter how data is validated or serialized) ￼ ￼. The details differ from our use case, but the concept to glean is decoupled extensibility: third-party code can extend functionality without modifying the core library. We can apply this by allowing `ActuarialFrame` to load external "accessor packs." For example, a package `actuarial-mortality` could declare a plugin that adds a `.mort` accessor with life table functions. Using entry points means `ActuarialFrame` could automatically discover and register that accessor if the plugin is installed, offering a seamless experience for the user (no manual registration call needed).

**Pros:** Pydantic's approach ensures that extensions integrate cleanly and configurably. By passing a `plugin_settings` dict, Pydantic even allows user control over plugin behavior ￼. For `ActuarialFrame`, we might not need user settings for plugins, but we do want the ability to turn them on/off or avoid conflicts. Entry points also allow packaging of extensions in a modular way (e.g., `pip install actuarialframe-mortality` could add a whole suite of mortality-related methods). Additionally, Pydantic's focus on well-defined models suggests we provide robust type definitions for our API; for example, we might supply `.pyi` type stubs so that IDEs know the exact signature of `from_excel_serial()` or `create_timeline()` methods.

**Cons:** Managing a plugin system adds complexity — we have to handle version compatibility and name collisions. We must design a clear protocol for plugin accessors (perhaps requiring them to subclass a base class or use a decorator) to ensure consistency. Also, if we auto-load via entry points, we should do so carefully to not slow down import times or unintentionally grab entry points that aren't relevant. Nonetheless, given the plug-in extensibility requirement, this approach is worth implementing for `ActuarialFrame`'s longevity.

### Julia Actuary: Domain-Specific Organization and DSL Design

The JuliaActuary ecosystem demonstrates how breaking functionality into domain-focused components helps discoverability and scalability. Instead of one giant monolithic library, JuliaActuary has packages like `MortalityTables.jl`, `ActuaryUtilities.jl`, and `FinanceModels.jl`, each providing a set of cohesive features ￼. For example, `ActuaryUtilities.jl` provides functions such as `present_value(...)`, `duration(...)`, `convexity(...)` for cashflow analysis ￼. An actuary using Julia can intuitively find "present value" in the utilities package and "mortality table lookup" in the mortality tables package. This modular design is essentially namespacing at the package level.

For `ActuarialFrame` (a single Python package), we emulate this by creating nested accessor namespaces per domain. Instead of dumping everything into `ActuarialFrame` or a single `.af` namespace, we will have `af.date`, `af.finance`, `af.mortality`, etc., akin to Julia's separate packages but as organized accessors. This way, advanced actuarial methods are grouped logically. An actuary thinking "I need to do a mortality-related calculation" would instinctively check `af.mortality` in the API and find, say, `af.mortality.period_life_expectancy(...)`. This design resonates with domain experts and improves cognitive mapping of the API.

Julia's multiple-dispatch design also encourages writing functions that operate on well-defined types (e.g., a `present_value` function might accept any cashflow type). In `ActuarialFrame`, we can mirror this by ensuring our accessor methods accept clear inputs (perhaps an `ActuarialFrame` column of a certain type) and return well-defined outputs (maybe a new column or scalar). The emphasis is on clear, self-describing method names and groupings. We should also note that JuliaActuary code, being in Julia, is quite performative; our design will leverage Polars (written in Rust) to ensure that even though we add Python DSL sugar, the execution under the hood is fast.

**Pros:** The JuliaActuary example validates the idea of domain-based separation. It shows that actuaries are comfortable switching contexts (using `MortalityTables` for one task, `FinanceModels` for another). In our design, switching context is as simple as accessing a different attribute (`af.date` vs `af.finance`), which is even easier since it's on the same object. This should enhance discoverability: by typing `af.` and seeing `date`, `finance`, `mortality`, etc., an actuary or an LLM will immediately see the scope of what's possible ￼ ￼.

**Cons:** One possible downside is slight verbosity. Users must remember which domain their function belongs to (e.g., `.date.from_excel_serial` vs maybe having a top-level `from_excel_date`). However, this is mitigated by good naming and documentation. Also, if a function logically spans domains, we must decide where to put it (for instance, "convert an Excel date serial" is clearly date-related, but something like "calculate reserves" might involve finance and mortality). In such cases, we choose the most relevant namespace or even allow duplicate entry points via different accessors if truly needed (though that can confuse discoverability, so it should be rare). Overall, the benefits of clear grouping outweigh these minor issues.

## Proposed Accessor Design for ActuarialFrame

### Domain-Specific Nested Accessors (Frame vs. Column Level)

We will introduce multiple accessor namespaces on the `ActuarialFrame` object, each corresponding to a functional domain (e.g. `af.date`, `af.finance`, `af.mortality`, `af.stats`, etc.) ￼. Each namespace will also exist on the column/expression level (likely via a proxy object for columns). In practice, this means if you select a column (or an expression representing a column) from the frame, you can access the same domain-specific namespace on that column. For example:

*   **Frame-level:** `af.date.create_timeline(start_col, end_col, freq)` – perhaps creates a new DataFrame (or adds columns) representing a timeline between two date columns.
*   **Column-level:** `af["policy_start"].date.to_period("M")` – converts a date column to a period (e.g., year-month period). Or `af["raw_date"].date.from_excel_serial()` – converts an Excel serial number in that column to an actual date.

This dual placement is similar to Polars, where `.dt` exists on expressions (for column-wise transforms) and certain DataFrame methods handle whole-table ops. By clearly separating frame vs column operations, we prevent confusion. Users learn that if they want to generate new columns or analyses involving multiple columns, they'll use a frame-level method (accessible on `af.<namespace>.<method>`). If they want to transform or analyze one column's values, they go to `af["col"].<namespace>.<method>`. This satisfies the requirement of a "clear frame vs. column-level distinction" ￼.

**Implementation:** We'll create accessor classes for each domain and each context. For instance, a `DateFrameAccessor` class with methods like `create_timeline` and perhaps `pivot_calendar`, etc., and a `DateColumnAccessor` class with methods like `from_excel_serial`, `to_datetime`, `yearfrac`, etc. `ActuarialFrame` will have a property `date` that instantiates a `DateFrameAccessor(self)` ￼. Similarly, our internal `ColumnProxy` class (which behaves like a polars Series/Expr) will have a `date` property that returns a `DateColumnAccessor(column=self)`. This design means the accessor classes can hold a reference to the parent object (frame or column) and operate on it. It mirrors Pandas' pattern (accessor `__init__` takes the host object) ￼ and Polars' (accessor classes store the `PySeries` or `PyExpr` pointer) ￼ ￼.

By using Python properties or `__getattr__`, we can make these accessors appear as normal attributes. For example, in `ActuarialFrame`'s class definition, we might do:

```python
class ActuarialFrame:
    @property
    def date(self) -> DateFrameAccessor:
        return DateFrameAccessor(self)
```

And similarly for the column proxy. Alternatively, we could use a metaclass or a registration decorator to attach them. A decorator approach (like `@register_frame_accessor("date")`) might automate adding the property and also store the accessor in a registry for introspection. This is analogous to Pandas' `register_dataframe_accessor` but within our library. The trade-off between manually coding the property vs. a decorator is mostly maintenance convenience. Given we have only a few core domains to start, manual definition is fine, but for user-extensions, a decorator will be provided to simplify it (see Extensibility appendix).

**Why not a single namespace?** We considered a single custom namespace (e.g., `af.x.` or `af.gs.` for "actuarial functions") ￼. While easier to implement initially, that would become a grab-bag of unrelated methods and quickly lose the organizational clarity. Multiple nested accessors keep things tidy and scalable. Each accessor class remains focused, and new methods can be added to their logical group without cluttering others. This structure directly addresses the goals of organization and scalability ￼ ￼.

### Functional and Immutable by Default

All accessor methods will follow a functional style, meaning they do not mutate the `ActuarialFrame` or column in-place. Instead, they will return a new object (new frame or new column/expression). This aligns with Polars (where DataFrames are immutable and operations produce new DataFrames or LazyFrames) and with best practices for predictable code (no side effects) ￼. Users will thus use chaining or re-assignment. For example:

```python
af = af.date.create_timeline("PolicyStart", "PolicyEnd", freq="M")
# af now has new monthly timeline columns, original af was left unchanged
```

Or for column operations:

```python
af["survival"] = af["Exposure"].mortality.apply_survival_curve(curve)
```

In this pseudo-example, `apply_survival_curve` under `.mortality` might return a Polars expression representing the transformed values, which we assign directly to the `survival` column using the `af[...] = ...` syntax. We could also provide sugar like `af = af.assign(newcol = af["Exposure"].mortality.apply_survival_curve(curve))` depending on how much of Pandas-like API we want to mimic. But the key is: no implicit in-place mutation. This approach reduces errors and follows the principle of least surprise for users coming from functional data libraries.

**One consideration:** While defaulting to immutable operations, we can allow in-place operations explicitly (e.g., an argument `inplace=True` or a separate method like `af.date.create_timeline_inplace(...)`) if needed for performance. Polars itself has some in-place operations on Series, but they are not the common path. We expect most `ActuarialFrame` usage to be in pipelines where immutable style is fine. And because we plan to use Polars under the hood, lazy evaluation can mitigate performance costs by optimizing the query before execution.

Aligning with immutability also means easier undo/redo logic and audit trails, which might be relevant in actuarial workflows (reproducibility is important). Each transformation yields a new frame, so you can always keep the original. This design also meshes well with LLMs generating code: an LLM can safely create new intermediate frames without risk, rather than guessing which operations mutate and which return new objects.

### Discoverability and Tooling Friendliness

**Autocompletion & Introspection:** By having named accessors (`date`, `finance`, etc.) as actual attributes, we immediately benefit from Python's introspection. Calling `dir(af)` will list `date`, `finance`, etc., making them visible to IDEs. We will also override `__dir__` on `ActuarialFrame` and the column proxy to ensure all custom accessor names (including any registered via plugins) appear. This way, even dynamically added namespaces show up in autocompletion. For instance, after loading a plugin that registers "mortality", `dir(af)` should include `"mortality"` so that IDEs know about it.

**Type Hints (.pyi stubs):** To further assist IDEs and static analyzers, we will ship a `.pyi` stub file with the library that explicitly declares these accessors. In the stub, `ActuarialFrame` can be defined as:

```python
class ActuarialFrame:
    @property
    def date(self) -> DateFrameAccessor: ...
    @property
    def finance(self) -> FinanceFrameAccessor: ...
    # etc.
```

And similarly for the `ColumnProxy` class. This ensures tools like MyPy, PyCharm, VSCode, and even LLMs that ingest context can see the full API surface. (As an example, the lack of such hints in Polars led to type checkers complaining about custom `.greetings` in their docs ￼; we will avoid that pitfall by being explicit in stubs.)

We'll also make heavy use of type hints in the accessor method signatures themselves. For example, `def from_excel_serial(self, epoch: str = "1900") -> "ActuarialFrameColumn": ...` (return type maybe an Expression/Column of dates). Clear parameter types and docstrings will be provided. With stub files and/or inline type hints, an LLM-based assistant can much more reliably suggest correct usage because it "knows" the method signatures and documentation.

**LLM Parseability:** The structure of `<object>.<domain>.<method>` is very LLM-friendly because it provides strong context. For example, if an LLM sees code `af.finance.duration(...)`, the very structure tells it that `duration` is likely a financial calculation method under a `finance` namespace. We will further support LLMs by producing documentation that is easy to parse. Possibly, we could include an `llm_support.md` or simply rely on the fact that our docstrings and stub make the API self-evident. The goal is that an LLM can ask itself "what can I do with this `ActuarialFrame`? and by looking at `dir(ActuarialFrame)` or reading the `.pyi`, it will see all the domains and their methods ￼ ￼. This explicitness enables an AI to generate correct code on the first try, which was one of our success criteria.

**Note on Naming:** We will choose intuitive, descriptive names for both accessor namespaces and methods. For domain names, we prefer full words (`date`, `finance`, `mortality`) over cryptic abbreviations, even if a bit longer, because they are clearer to newcomers and LLMs. For method names, we follow Python conventions and domain clarity. For example, `.date.from_excel_serial()` is verbose but immediately clear in purpose – it converts Excel serial dates to real dates. An alternative could be `.date.from_excel()` or `.date.excel_to_date()`; these shorter names are possible if documentation is clear, but "from_excel_serial" explicitly mentions serial, which is a term actuaries familiar with Excel will recognize. We'll document these decisions so that actuaries coming from Excel or other environments can map concepts (indeed, the design should "draw parallels to common actuarial terminology or Excel concepts where appropriate" ￼ without being un-Pythonic).

Finally, by structuring the API with classes and methods, we naturally allow Sphinx or similar tools to generate documentation pages grouped by namespace. For instance, a documentation section could list all `ActuarialFrame.date` methods together, making it easy to scan advanced date handling features. This structured documentation further aids discoverability.

### Integration with Underlying Polars (Frame vs Expression Distinctions)

`ActuarialFrame` will likely be built atop Polars (for performance and its expression DSL). We will use that to our advantage. The column-level accessors can internally create Polars `Expr` objects or use Polars `Series` methods. For example, implementing `from_excel_serial()` could internally do something like:

```python
# inside DateColumnAccessor.from_excel_serial
return self._col.apply(lambda x: datetime_from_excel_serial(x), return_dtype=Date)
```

where `self._col` might be a Polars expression if the frame is in lazy mode, or a Series if in eager mode. Thanks to Polars' design, we could use `expr_dispatch` (like Polars does ￼) or write logic to handle both: if the `ActuarialFrame` is tracking a lazy query, we attach a `.apply` expression; if it's an in-memory frame, we apply to the Series values. We will strive to mirror Polars' behavior: if `ActuarialFrame` is primarily a lazy DSL, all column ops will yield an `Expr` until collected. If it's an eager frame, ops return a new `Series` which we then wrap back into the frame. This detail will be handled behind scenes, so the user experience remains the same.

We must also ensure we coexist with Polars' own accessors when relevant. If `ActuarialFrame` exposes the entire Polars DataFrame API (via inheritance or composition), a user might still do `af["col"].str.split()` (Polars string method) in addition to our `af["col"].date....` We should allow that for completeness. That means our `ColumnProxy` might need to forward unknown attributes to the underlying Polars Series/Expr. However, to keep things simple, we might encourage users to use Polars functions through our interface (perhaps by exposing common ones or just documenting that they can always fall back to `af._df` to get the raw Polars DataFrame if needed).

A safer approach is composition: `ActuarialFrame` holds a Polars DataFrame or LazyFrame internally (e.g., `self._pl_df`). We implement our own `__getitem__` to return a `ColumnProxy` (instead of Polars Series) so we can control the `.date`, `.finance` on it. We can still expose Polars methods by implementing `__getattr__` on `ColumnProxy`: if an attribute name doesn't match any of our custom accessors (say user calls `.str` or `.dt`), we forward it to the polars Series/Expr. In effect, `af["col"].str.split()` would work by delegating to Polars. This delegation gives us the best of both: our DSL for specialized needs and full Polars power when needed, all while keeping the namespaces distinct (no name collisions, since we won't use names like `str` or `dt` for our accessors).

Keeping the frame vs. column distinction clear also means we won't put, say, `.mortality` on `ActuarialFrame` if all its methods truly operate on column data. If a user calls `af.mortality`, we could either raise an error or design a few frame-level mortality methods (perhaps something like `af.mortality.validate_table(...)` to validate the whole DataFrame's mortality table columns). Each accessor will document whether its methods are frame-level or column-level. If the accessor is accessed from the wrong context, it can throw a helpful `AttributeError` (just like Pandas `.dt` does on invalid dtypes ￼). This prevents misuse and clarifies the API contract.

## Example Usage and Trade-offs

### Example 1 (Date operations)

An actuary wants to convert an Excel date column and add a policy duration. Using `ActuarialFrame`:

```python
af = ActuarialFrame({"pol_start": [44927, 44958]})  # Excel serial dates for 2023-01-01, 2023-02-01
af["pol_start_dt"] = af["pol_start"].date.from_excel_serial()
# Note: Frame-level operations like add_duration might not fit the assignment syntax directly.
# Depending on implementation, it might return a new column/expression or modify the frame.
# Assuming it returns an expression for the new column:
af["pol_end_dt"] = af.date.add_duration("pol_start_dt", periods=12, period_type="M")
```

Here, `af["pol_start"].date.from_excel_serial()` converts the Excel serial to an actual datetime. Then `af.date.add_duration(...)` is a frame-level method that might add a year's worth (12 months) to the start date to get an end date. Assuming it returns an expression, we assign it to the new column `pol_end_dt`. The final `ActuarialFrame` now has original `pol_start` (serial), `pol_start_dt` (datetime), and `pol_end_dt` (datetime after 12 months). This chain shows how frame and column accessors interplay.

### Example 2 (Mortality and Finance)

Suppose an `ActuarialFrame` has a column of exposure amounts and we want to apply a mortality curve to get expected losses, then discount them. One might do:

```python
af = ActuarialFrame({"Exposure": [1000, 800, 600]})
af["survived"] = af["Exposure"].mortality.apply_curve(qx_curve)
af["discounted_survival"] = af["survived"].finance.discount(rate=0.03, periods=1)
```

Here, `.mortality.apply_curve(qx_curve)` could multiply the exposure by survival probabilities (perhaps vectorized across a life table), and `.finance.discount` could apply a discount factor for one period at 3%. Each returns a new column expression, which we assign directly using the `af["new_col"] = ...` syntax. The end result has new columns for survived amount and its discounted value. The code reads clearly: the chain of transformations is evident, and each domain-specific piece is in its place.

### Trade-offs

One trade-off with this design is verbosity versus implicitness. We favor explicit accessor calls to maximize clarity. An alternative design could automatically expose every method at the frame level (e.g., allow `af.from_excel_serial("col")` as a top-level method). That would be less to type, but it conflates different kinds of operations and doesn't guide the user in discovering related methods. Our namespacing requires a bit more typing but in return gives structure. It also avoids method name collisions – e.g., a `.rate()` method under `.finance` (for interest rate conversion) won't collide with a `.rate()` under `.mortality` (maybe for rating factors), since they live in different namespaces.

Another consideration is that adding many accessors increases the number of objects and indirections, but these are lightweight (each accessor is a small wrapper around the parent). The performance overhead is negligible compared to the heavy numeric computations which Polars/Rust will handle. We prioritize API ergonomics over micro-optimization here, and in practice accessor methods will likely be fused in Polars' lazy execution anyway.

## Appendix: Extensibility and Plugin Design

To facilitate external, user-defined domains, we will provide a clear plugin API. There are a couple of approaches, and we can support both:

*   **Decorator Registration:** Similar to Pandas/Polars, we offer a decorator `actframe.register_accessor(name: str, *, kind: str = "column"|"frame")`. A user could write:

    ```python
    @actframe.register_accessor("risk", kind="column")
    class RiskMetricsAccessor:
        def __init__(self, col_proxy):
            self._col = col_proxy
        def var(self, confidence: float) -> float:
            # calculate value-at-risk on the series in self._col
            ...
    ```

    This would attach a `.risk` accessor to all `ColumnProxy` objects. The new methods (like `.risk.var()`) can then be used on any column. Under the hood, `register_accessor` will set the attribute on the target class and perhaps add it to a registry for introspection. We'd likely prevent using names that clash with existing attributes (issuing a warning or error) ￼. This approach is straightforward but requires the user to import the module (so that the decorator runs) before the accessor becomes available. This is fine in many cases (just documenting "import your plugins before use"), but we can improve it with the next approach.

*   **Entry Point Plugins:** We designate an entry point group, e.g., `"actuarialframe.accessors"`. Plugin packages can declare entry points in their setup (as Pydantic does with `"pydantic"` entry points ￼). On `ActuarialFrame` initialization (or module import), we scan `importlib.metadata.entry_points()` for our group and automatically import and register those accessors. This way, if an actuary has installed a plugin, they get the new `.mortality` or `.risk` namespace without any extra code. We will document the plugin interface (for instance, requiring a certain class signature and perhaps using our decorator internally). We might also allow plugin authors to specify whether their accessor is for columns or frames (or both, if applicable).

### Ensuring Type Support

When a new accessor is added via plugin, how do we keep our autocompletion and type hint promises? One way is to encourage plugin authors to ship their own stub files or use typing hacks (as was done in the Pandas accessor example on StackOverflow ￼). A better integrated approach is we could generate a unified stub at runtime that includes plugins – but that's complex and probably overkill. Instead, our stance can be: core accessors are in the core stubs; for third-party ones, the user's IDE will pick them up via the plugin's package (if the plugin includes type hints). We will at least make sure that our `__dir__` reflects them at runtime for introspection. Over time, if some plugins become essentially standard, we might merge their stubs into our distribution or provide an official way to declare them to static analyzers.

### Instrumentation

We will also consider adding instrumentation hooks for logging or performance. For example, when a plugin method is called, we could have an internal mechanism to log "Plugin X's method Y was used" for audit or debugging. This is an advanced feature and can be done by wrapping plugin method calls if needed. Pydantic's plugin system passes a `plugin_settings` dict to plugins ￼; in our simpler case, we might not need explicit settings, but we could allow plugins to read some global `ActuarialFrame` config if that becomes necessary (e.g., a plugin that needs to know a base interest rate assumption).

### Example Plugin

Suppose a company wants to add a proprietary insurance namespace with methods to calculate premiums. They create a package `mycompany-actframe-insurance`. In it, they use our API:

```python
@actframe.register_accessor("insurance", kind="frame")
class InsuranceFrameAccessor:
    def __init__(self, frame):
        self._frame = frame
    def calc_premium(self, rate_col: str, exposure_col: str) -> ActuarialFrame:
        # use self._frame[rate_col] and self._frame[exposure_col] to compute premium
        new_series = self._frame[rate_col]._col * self._frame[exposure_col]._col  # for example
        return self._frame.with_column(new_series.alias("premium"))
```

After installing this package, the `ActuarialFrame` API would transparently gain `af.insurance.calc_premium()`. The user (or an LLM) typing `af.insurance.` would see `calc_premium` in autocompletion. This shows how extensibility allows customization for specific domains without bloat in the core library.

## In conclusion

The proposed architecture leverages proven patterns (Polars/Pandas style accessors, Pydantic style plugins, Julia-style domain grouping) to create a discoverable, extensible, and clean DSL for actuarial computations. It emphasizes clarity (both in code and for tool ingestion) and flexibility, ensuring that `ActuarialFrame` can grow with new methods and domains while remaining user-friendly. By balancing dynamic extensibility with static introspection aids, we make the API not just powerful, but also approachable for both actuaries and AI copilots.

## Sources

*   Polars documentation on custom namespaces ￼ ￼ – demonstrates dynamic accessor registration and reserved names.
*   Polars source code for accessors ￼ ￼ – shows how namespaces like `.str` are implemented for expressions/series.
*   Pandas extension accessor docs ￼ ￼ – outlines how to register and structure an accessor class.
*   Stack Overflow discussion on accessor type hints ￼ – highlights the static typing challenge with dynamic attributes.
*   Pydantic plugin documentation ￼ ￼ – explains entry point based extensibility in a data library context.
*   JuliaActuary examples ￼ ￼ – illustrate domain-specific functions and the value of logical grouping in an actuarial library.
*   Xarray datetime accessor documentation ￼ ￼ – example of Pandas-like `.dt` accessor in another library, confirming the pattern's viability for our use case.