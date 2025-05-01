# Background: Improving Polars Error Reporting in ActuarialFrame

## The Problem: Lazy Execution and Error Origin Obscurity

Polars operates using a lazy execution model. When using the `ActuarialFrame` DSL, which wraps Polars expressions, operations like column assignments, transformations, and calculations are not executed immediately. Instead, they build up a logical query plan.

```python
# Example: In user's model script (e.g., model_test.py)
import polars as pl
from gaspatchio_core.dsl import ActuarialFrame

af = ActuarialFrame({"col_a": [1.1, 2.2], "col_b": [3.3, 4.4]})

# These lines define steps in the logical plan, but don't run calculations yet
af["intermediate"] = af["col_a"] * 10.0 # Creates a List<Float64> in the plan
af["problematic"] = af["intermediate"].cast(pl.Int64) # Defines an invalid cast List<Float64> -> Int64

# ... many other operations ...

# Execution is triggered only when a result is requested
# e.g., in the runner script (e.g., run_model.py)
try:
    result_df = af.collect() # Or af.profile(), af.compute(), etc.
except pl.exceptions.InvalidOperationError as e:
    print(f"Error during execution: {e}")
    # Standard Python traceback points here (the .collect() call)
    # not to the af["problematic"] = ... line in model_test.py
```

The actual computation, and therefore any runtime errors (like type mismatches, invalid operations, missing columns), only occur when an action like `.collect()`, `.profile()`, `.compute()`, or writing to a file is called.

Consequently, the standard Python traceback points to the line that *triggered* the execution (e.g., `af.collect()` in the runner script), not the line in the user's model script that *defined* the faulty operation within the logical plan. This makes debugging difficult, especially in complex models with many steps, as the user has to manually trace back through their code to find the source of the Polars error (e.g., `InvalidOperationError: cannot cast List type (inner: 'Float64', to: 'Int64')`).

## Potential Approaches to Improve Error Localization

Several approaches were discussed to provide users with better information about the origin of Polars errors within their model scripts:

### 1. Manual Inspection and Educated Guessing

*   **How:** Analyze the Polars error message (e.g., "cannot cast List type (inner: 'Float64', to: 'Int64')", "Column 'xyz' not found"). Search the model script code for operations that match the error description (e.g., `.cast(pl.Int64)` calls, references to column `xyz`).
*   **Pros:** No changes needed to the framework.
*   **Cons:** Inefficient and error-prone for complex models. Relies heavily on user understanding of Polars and their own code structure.

### 2. Intermediate Debugging by User

*   **How:** The user manually inserts debugging steps within their model script before the anticipated error or execution trigger.
    ```python
    # In model_test.py
    af["intermediate"] = af["col_a"] * 10.0
    print("Schema before cast:", af.collect_schema()) # Check types
    # print("Data before cast:", af.select("intermediate").head().collect()) # Check values (triggers partial execution)
    af["problematic"] = af["intermediate"].cast(pl.Int64)
    ```
*   **Pros:** Allows fine-grained inspection.
*   **Cons:** Requires manual modification of model code for debugging. Running `.collect()` frequently can be slow and negate the benefits of laziness. `collect_schema()` is faster but only shows types, not potential value-related errors.

### 3. Enhanced Error Handling within `ActuarialFrame`

This approach involves modifying the `ActuarialFrame` class itself to intercept Polars errors during the execution phase and provide more contextually relevant information to the user.

*   **Goal:** Automatically provide users with stronger hints about the origin of a Polars error within their model script, reducing manual debugging effort.
*   **Mechanism:** Intercept Polars exceptions during execution (`collect`, `profile`, etc.), analyze the error and the query plan, and attempt to correlate the failing plan operation back to the user's Python code.

*   **Detailed Steps:**

    1.  **Catch Specific Exceptions:** Modify the methods in `ActuarialFrame` that trigger execution (e.g., `collect`, `profile`, `compute`, `write_*`) to include `try...except` blocks. These blocks should specifically catch relevant Polars exceptions like `polars.exceptions.InvalidOperationError`, `polars.exceptions.ComputeError`, `polars.exceptions.SchemaError`, `polars.exceptions.ColumnNotFoundError`, etc.

    2.  **Retrieve Logical Plan:** Inside the `except` block, immediately retrieve the *unoptimized* logical plan of the `LazyFrame` that was being executed. Using the unoptimized plan is crucial because it more closely resembles the sequence of operations defined by the user's Python code before Polars applies optimizations that might reorder or combine steps.
        ```python
        # Inside the except block in ActuarialFrame
        try:
            # ... attempt execution (e.g., self._df.collect()) ...
        except polars.exceptions.PolarsError as e: # Catch broad Polars error or specific ones
            try:
                plan_str = self._df.explain(optimized=False)
            except Exception:
                plan_str = "Could not retrieve logical plan."
            # ... proceed to analyze error and plan ...
        ```

    3.  **Analyze Error Message and Plan:**
        *   **Parse Error:** Extract key details from the specific Polars exception message (`str(e)`). For example:
            *   `InvalidOperationError: cannot cast List type (inner: 'Float64', to: 'Int64')` -> Keywords: "cast", "List", "Float64", "Int64".
            *   `ColumnNotFoundError: 'column_xyz'` -> Keyword: "'column_xyz'".
        *   **Search Plan:** Perform a textual search within the `plan_str` for lines or nodes that contain the keywords extracted from the error message. This helps identify the likely *step* in the computation plan that failed. For instance, look for lines containing `CAST(..., Int64)` or references to `column_xyz`.

    4.  **(Hard Part) Link Plan Step to Python Code:** This is the most challenging step due to the disconnect between the lazily defined Python code and the eagerly executed plan. Several strategies exist, with varying complexity and feasibility:
        *   **Strategy A: AST Analysis + Plan Matching (Very Complex & Brittle):**
            *   Parse the user's model script (e.g., `model_test.py`) into an Abstract Syntax Tree (AST) using Python's `ast` module.
            *   Analyze the structure of the relevant part of the logical plan identified in Step 3.
            *   Attempt to heuristically match patterns in the logical plan (e.g., a `CAST` operation applied to the result of a `FLOOR` operation on a column named `policy duration`) back to corresponding AST nodes in the model script (e.g., the assignment `af["policy_duration_as_int"] = af.floor(af["policy duration"]).cast(pl.Int64)`).
            *   Extract the line number from the matched AST node.
            *   *Challenges:* Extremely difficult to implement robustly. Polars plan representations can change, optimizations obscure the original structure, and mapping complex expressions reliably is non-trivial.
        *   **Strategy B: Runtime Stack Inspection (Adds Overhead):**
            *   Modify the expression creation points in `ActuarialFrame` (e.g., `__setitem__`, or the proxy mechanism in `_delegation._make_wrapper`).
            *   When a Polars expression is *created* (e.g., when `.cast(pl.Int64)` is called on a proxy), use Python's `inspect` module to capture the current Python call stack.
            *   Store a mapping (e.g., in a dictionary on the `ActuarialFrame` instance) associating some identifier of the created Polars expression or plan node fragment with its creation stack trace (specifically the frame corresponding to the user's model script).
            *   When an error occurs during execution, identify the failing plan node (from Step 3) and try to look up its associated creation stack trace from the stored mapping.
            *   Report the file and line number from the relevant frame in the user's model script.
            *   *Challenges:* Adds performance overhead to every DSL operation as stack inspection is not free. Mapping runtime expression objects to specific plan nodes during error analysis can still be complex. Requires careful memory management.
        *   **Strategy C: Polars Expression Annotation (Hypothetical/Future Feature):**
            *   Ideally, Polars itself would allow attaching arbitrary metadata (like `{"source_file": "model_test.py", "source_line": 115}`) to expressions during their creation.
            *   If Polars could preserve this metadata through plan optimizations and surface it as part of the error context when an exception occurs, this would directly solve the problem.
            *   *Status:* This functionality does not currently exist in Polars.

    5.  **Construct and Raise Enhanced Error Message:** Based on the analysis, construct a more informative error message. This might involve wrapping the original Polars exception or raising a new custom exception. The message should include:
        *   The original Polars error message (`str(e)`).
        *   Relevant snippet(s) identified in the logical plan (`plan_str`).
        *   **If linking succeeded (Strategy A or B):** The suspected originating file and line number from the model script. (e.g., "Error likely originated near line X in file Y.")
        *   **If only plan analysis was possible:** Guidance based on the plan analysis. (e.g., "Error seems related to a CAST operation involving List<Float64> -> Int64 found in the logical plan. Please check `.cast(pl.Int64)` calls in your model script, especially those operating on columns like 'intermediate' which appear to be List<Float64> according to the plan.")

*   **Pros:**
    *   Provides automated, improved feedback directly to the user upon error.
    *   Reduces the need for manual debugging steps (like inserting `print` or `collect_schema`) in the model code.
    *   Leverages the logical plan, which contains valuable intermediate information.

*   **Cons:**
    *   Implementation complexity varies significantly depending on how accurately we want to pinpoint the source line (Step 4).
    *   Basic plan analysis (Steps 1-3, 5 without line number) is feasible but provides only general hints.
    *   Accurate line number pinpointing (Strategies 4A/4B) is very complex, potentially brittle, and may introduce performance overhead.
    *   The ideal solution (Strategy 4C) depends on currently unavailable features in Polars.
