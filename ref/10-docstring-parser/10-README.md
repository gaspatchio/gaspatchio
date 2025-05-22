# Gaspatchio Docstring Processor Engine

This document outlines the functionality of the Gaspatchio docstring processing engine. This engine is designed to:

* Parse every Gaspatchio docstring into a strict Pydantic model.
* Validate the structure of docstrings and their embedded code examples.
* Lint and execute examples in a workflow similar to `pytest-examples`, compatible with Ruff and doctest.
* Optionally rewrite docstring examples in-place to reflect updated outputs (`run_print_update`).
* Ensure that standard `uv run pytest -v --doctest-modules` commands continue to work as expected.

---

## CLI Usage

The docstring processing tools are available via the `gp-docstrings` command-line interface. Ensure that `gaspatchio-core` is installed in your environment (e.g., via `uv add . -p gaspatchio-core/bindings/python` if `gaspatchio-core/bindings/python` is your project root, or ensure your Python environment recognizes the `gp-docstrings` script).

Commands are typically run from the `gaspatchio-core/bindings/python` directory or any location where `uv` can resolve the `gp-docstrings` script and its dependencies.

### Parse Docstrings

Extracts docstrings from Python files and outputs them as JSON. This is useful for inspection, analysis, or feeding into other tools.

**General Examples:**

```bash
# Parse all Python files in a specific directory
# (Assumes you are in gaspatchio-core/bindings/python or have set up paths)
uv run gp-docstrings parse gaspatchio_core/column/namespaces

# Parse a single file
uv run gp-docstrings parse --file gaspatchio_core/column/namespaces/dt_proxy.py

# Parse a single file and filter for a specific method
uv run gp-docstrings parse --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.year"

# Save output to a file
uv run gp-docstrings parse --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.year" --out dt_proxy_year_docstring.json
```

**Understanding the JSON Output:**

When you run the `parse` command, it outputs a JSON array. Each element in the array is a `GaspatchioDocstring` object representing a parsed docstring from your code.

For example, running:
```bash
uv run gp-docstrings parse --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.year"
```

Will produce output similar to this (showing one example object for brevity):

```json
[
  {
    "short_description": "Extract the year from the underlying datetime expression.",
    "long_description": "Corresponds to Polars ``Expr.dt.year()``.",
    "parameters": [],
    "returns": null,
    "examples": [
      {
        "snippet": "import polars as pl\n",
        "output": null,
        "object_context": "dt_proxy.DtNamespaceProxy.year",
        "example_index": 0,
        "raw_source_location": [
          "/path/to/your/gaspatchio-core/bindings/python/gaspatchio_core/column/namespaces/dt_proxy.py",
          0
        ]
      },
      // ... more examples ...
      {
        "snippet": "print(af.select(year_expr.alias(\"year\")).collect())\n",
        "output": "shape: (2, 1)\n\u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2510\n\u2502 year \u2502\n\u2502 ---  \u2502\n\u2502 i32  \u2502\n\u255e\u2550\u2550\u2550\u2550\u2550\u2550\u2561\n\u2502 2020 \u2502\n\u2502 2021 \u2502\n\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2518",
        "object_context": "dt_proxy.DtNamespaceProxy.year",
        "example_index": 5,
        "raw_source_location": [
          "/path/to/your/gaspatchio-core/bindings/python/gaspatchio_core/column/namespaces/dt_proxy.py",
          0
        ]
      }
    ],
    "raw_docstring": "Extract the year from the underlying datetime expression.\n\n... (full raw docstring text) ...",
    "object_path": "dt_proxy.DtNamespaceProxy.year",
    "file_path": "/path/to/your/gaspatchio-core/bindings/python/gaspatchio_core/column/namespaces/dt_proxy.py",
    "start_line": 182
  }
]
```

Key fields in the JSON output:
*   `short_description`: The first line of the docstring.
*   `long_description`: The rest of the main docstring body.
*   `parameters`: A list of parsed parameters (name, type, description).
*   `returns`: Information about the return value (type, description).
*   `examples`: A list of `DocstringCodeExample` objects, each containing:
    *   `snippet`: The code part of the example (e.g., `>>> print('hello')`).
    *   `output`: The expected output following the snippet (if any).
    *   `object_context`: The fully qualified name of the object (function/method) the example belongs to.
    *   `example_index`: The 0-based index of this example within its parent docstring.
    *   `raw_source_location`: A tuple of `[file_path, line_number_of_example_in_docstring]` (line number is currently a placeholder `0`, see Prompt 1.2 in `10-spec.md` for future improvement).
*   `raw_docstring`: The complete, original docstring text.
*   `object_path`: The qualified path to the documented object (e.g., `module.ClassName.method_name`).
*   `file_path`: The absolute path to the source file containing the docstring.
*   `start_line`: The 1-indexed starting line number of the docstring in the source file.


### Check Docstring Examples (`run-print-check`)

Parses docstrings and runs execution checks (both doctest-style and custom validation) for all examples found.

```bash
# Check examples in a specific file like dt_proxy.py
uv run gp-docstrings run-print-check --file gaspatchio_core/column/namespaces/dt_proxy.py

# Check examples for a specific method in dt_proxy.py
uv run gp-docstrings run-print-check --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.month"
```
This command will report any discrepancies between an example's actual output and its documented output, or other execution errors. If all examples pass for the given scope, it will report success. If there are issues, it will provide details.

**Understanding the `run-print-check` Output:**

When you run this command, it will first indicate how many examples it found and is checking. If issues are found, it will print an "Error Summary" section.

For example, running:
```bash
uv run gp-docstrings run-print-check --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.month"
```

Might produce output like this if there are mismatches:

```text
Checking examples in single file: gaspatchio_core/column/namespaces/dt_proxy.py
Filtered 33 examples down to 10 matching method '*DtNamespaceProxy.month*' in gaspatchio_core/column/namespaces/dt_proxy.py
Found 10 examples to check.

--- Error Summary ---
Errors in dt_proxy.DtNamespaceProxy.month - Example #3 (File: /path/to/.../dt_proxy.py, Line: 0):
- [Custom Check Error] Output mismatch for dt_proxy.DtNamespaceProxy.month ex#3 (...):
EXPECTED:
shape: (3, 1)
┌─────┐
│ m   │
│ --- │
│ i8  │
╞═════╡
│ 1   │
│ 2   │
│ 3   │
└─────┘
ACTUAL:

SNIPPET:
print(af.select(af["d"].dt.month().alias("m")).collect())

Errors in dt_proxy.DtNamespaceProxy.month - Example #9 (File: /path/to/.../dt_proxy.py, Line: 0):
- [Custom Check Error] Output mismatch for dt_proxy.DtNamespaceProxy.month ex#9 (...):
EXPECTED:
shape: (2, 2)
┌───────────┬──────────────────┐
│ literal   ┆ lodgement_months │
│ ---       ┆ ---              │
│ str       ┆ list[i8]         │
╞═══════════╪══════════════════╡
│ policy_id ┆ [3, 4]           │
│ policy_id ┆ [1, 11]          │
└───────────┴──────────────────┘
ACTUAL:

SNIPPET:
print(af.select("policy_id", months_expr.alias("lodgement_months")).collect())

Found issues in 2 out of 10 examples checked.
```

Key things to note in the error output:
*   It specifies which example (by `object_context` and `example_index`) has an issue.
*   `[Custom Check Error] Output mismatch`: Indicates the documented output doesn't match the actual output when the snippet was run.
*   `EXPECTED`: Shows the output that is currently in the docstring.
*   `ACTUAL`: Shows what the code actually produced (empty in this truncated example, but would show the differing output).
*   `SNIPPET`: Shows the code that was run.
*   The summary line indicates how many examples had issues.

If all examples pass, the output would be simpler, e.g.:
```text
Checking examples in single file: gaspatchio_core/column/namespaces/dt_proxy.py
Filtered X examples down to Y matching method '*METHOD*' in gaspatchio_core/column/namespaces/dt_proxy.py
Found Y examples to check.

All Y examples checked passed execution checks.
```

**Key Differences: `run-print-check` vs. `lint`**

It's important to understand the distinct roles of `run-print-check` and the `lint` commands:

*   **`uv run gp-docstrings run-print-check`**:
    *   **Purpose**: Primarily focused on the **runtime correctness of code examples and their documented output**.
    *   **What it does**:
        1.  Parses docstrings.
        2.  Performs an initial structural lint check on the docstrings (e.g., identifying legacy `>>>` examples that should be converted to Markdown). If this fails, it stops.
        3.  Executes each Python code snippet found in the docstring examples.
        4.  Compares the *actual output* (from `stdout` or the value of the last expression) against the *expected output* documented in the docstring.
        5.  Reports any runtime errors during snippet execution or mismatches between actual and expected output.
    *   **Use when**: You want to verify that your code examples run correctly and produce the output you've documented. This is crucial for ensuring examples stay up-to-date with code changes.
    *   **Example**: `uv run gp-docstrings run-print-check --file gaspatchio_core/column/namespaces/string_proxy.py --method "StringNamespaceProxy.contains"` will execute the examples for the `contains` method and check if their output matches what's in the docstring.

*   **`uv run gp-docstrings lint` or `uv run pytest ... --gp-docstring-paths=...`**:
    *   **Purpose**: Focused on the **structural integrity of the docstring and the code style/quality of the embedded examples**.
    *   **What it does (via `pytest` plugin integration for the latter)**:
        1.  Parses docstrings.
        2.  **Structural Validation**: Checks if the docstring adheres to the expected format (e.g., presence of required sections like `short_description`, `long_description`, `when_to_use`; correct parameter and return type annotations; no legacy `>>>` examples). This is handled by `DocstringStructureItem` in the `pytest` plugin.
        3.  **Code Snippet Linting**: Uses **Ruff** to lint the Python code within each example for style issues, potential bugs, and adherence to coding standards (e.g., unused imports, line length, proper syntax). This is handled by `DocstringExampleItem.lint()` in the `pytest` plugin.
        4.  It does *not* primarily focus on comparing the runtime output of the example with the documented output in the same way `run-print-check` does. While the `pytest` items *could* be extended to do full execution checks, their main role in the current setup is structural and style linting.
    *   **Use when**: You want to ensure your docstrings are well-formed and that the code examples within them are clean, well-styled, and free of common linting errors. This helps maintain overall code quality and readability.
    *   **Example**: `uv run pytest gaspatchio_core/column/namespaces/string_proxy.py --gp-docstring-paths="gaspatchio_core/column/namespaces/string_proxy.py"` will check the structure of docstrings in `string_proxy.py` and lint the code snippets within its examples using Ruff.

In summary:
*   Use `run-print-check` to ensure your examples **work as advertised**.
*   Use `lint` (either variant) to ensure your docstrings and example code are **well-written and structured**.

Both are important for maintaining high-quality documentation.

### Lint and Validate Docstring Examples (`lint`)

Uses `pytest` to discover and validate docstring examples. This includes structural validation, Ruff linting, and execution checks.

The `gp-docstrings lint` command is still available for focused linting via its own machinery:
```bash
# Lint examples in the dt_proxy.py file using the gp-docstrings command
uv run gp-docstrings lint --file gaspatchio_core/column/namespaces/dt_proxy.py

# Lint a specific method, e.g., DtNamespaceProxy.day, using the gp-docstrings command
uv run gp-docstrings lint --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.day"

# Run gp-docstrings lint in strict mode (stops on first failure)
uv run gp-docstrings lint --file gaspatchio_core/column/namespaces/dt_proxy.py --strict
```

**Alternatively, and for CI/broader checks, you can run linting directly with `pytest`**:

This leverages the `pytest` plugin for docstring checking. You need to tell `pytest` which files to check using the `--gp-docstring-paths` option.

```bash
# Lint examples in a specific file using pytest directly
uv run pytest gaspatchio_core/column/namespaces/string_proxy.py --gp-docstring-paths="gaspatchio_core/column/namespaces/string_proxy.py"

# Lint examples in multiple files or using glob patterns
uv run pytest --gp-docstring-paths="gaspatchio_core/column/namespaces/*.py" "gaspatchio_core/utils/another_module.py"

# To run all docstring tests discovered by the plugin based on pyproject.toml configuration (see below):
uv run pytest -m gaspatchio_docstring_example
# To run only structural checks:
uv run pytest -m gaspatchio_docstring_structure_check
# To run both:
uv run pytest -m "gaspatchio_docstring_example or gaspatchio_docstring_structure_check"
```

**Configuring Docstring Test Discovery in `pyproject.toml`:**

To avoid specifying `--gp-docstring-paths` every time, you can configure the default paths for the `pytest` plugin in your `pyproject.toml` file. This is the recommended way to manage which files are included in docstring testing.

Add or modify the `tool.pytest.ini_options` section:

```toml
[tool.pytest.ini_options]
# Add or append to existing addopts
# For example, if you have other addopts: addopts = ["--cov=.", "--gp-docstring-paths=gaspatchio_core/column/**/*.py"]
addopts = ["--gp-docstring-paths=gaspatchio_core/column/namespaces/dt_proxy.py", "--gp-docstring-paths=gaspatchio_core/frame/*.py"]
# You can specify multiple paths. Each path is a glob pattern.
# Example to include all .py files under gaspatchio_core/column/namespaces:
# addopts = ["--gp-docstring-paths=gaspatchio_core/column/namespaces/**/*.py"]
# Example to include specific files:
# addopts = ["--gp-docstring-paths=gaspatchio_core/column/namespaces/dt_proxy.py", "--gp-docstring-paths=gaspatchio_core/utils/specific_util.py"]

# It's also good practice to register the markers used by the plugin:
markers = [
    "gaspatchio_docstring_example: Marks test as a Gaspatchio docstring example execution/lint check",
    "gaspatchio_docstring_structure_check: Marks test as a Gaspatchio docstring structure validation check",
]
# testpaths = ["tests", "gaspatchio_core"] # Optional: define where pytest looks for tests in general
```

With `pyproject.toml` configured, you can simply run:
```bash
uv run pytest
# or to run only docstring related tests:
uv run pytest -m "gaspatchio_docstring_example or gaspatchio_docstring_structure_check"
```
This will use the paths defined in `addopts` to discover docstring examples.

The `gp-docstrings lint` command remains useful for quick checks on specific files or methods without relying on the full `pytest` collection and execution cycle, especially if you haven't configured `pyproject.toml` or want to override its settings for a one-off check.

### Update Docstring Example Outputs (`update`)

Uses `pytest` to run docstring examples. If an example's output differs from what's documented (and the example runs successfully), this command updates the docstring in the source file with the new output.

```bash
# Update examples in dt_proxy.py
uv run gp-docstrings update --file gaspatchio_core/column/namespaces/dt_proxy.py

# Update examples for a specific method, e.g., DtNamespaceProxy.year, in dt_proxy.py
uv run gp-docstrings update --file gaspatchio_core/column/namespaces/dt_proxy.py --method "DtNamespaceProxy.year"
```
This is useful for automatically correcting example outputs after code changes.

---

## Polars DataFrame Print Formatting

All docstring example checks now use a standardized Polars print configuration: wide tables, no wrapping, and long string display. This ensures that DataFrame output in examples matches expected output regardless of environment. You can globally override this by calling:

```python
from gaspatchio_core.examples.docstrings.parse import GaspatchioDocstringParser
GaspatchioDocstringParser.set_polars_print_config(tbl_width_chars=2000, tbl_cols=-1, tbl_rows=50, fmt_str_lengths=200)
```

before running checks or tests.

### How Code Blocks Are Parsed and Executed

- Code blocks in docstrings now support multi-line Python code.
- The last line of a code block is evaluated if it's an expression; otherwise, the whole block is executed.
- Output matching is robust to multi-line code and Polars pretty-printing (with the new config).

---

*(The rest of this document refers to the detailed design and implementation specification, `10-spec.md`, for this engine.)*
