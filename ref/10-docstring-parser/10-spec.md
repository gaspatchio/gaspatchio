# Gaspatchio Docstring Processor: Implementation Specification & LLM Prompts

This document outlines the step-by-step implementation plan for the Gaspatchio docstring processing engine, as envisioned in `10-into.md`. Each section below represents a prompt that can be given to a code-generation LLM to implement a specific part of the project in a test-driven manner.

**Project Context:** The overall goal is to create a system that can parse, validate, lint, execute, and optionally rewrite Python docstring examples within the Gaspatchio framework. This will improve documentation quality, ensure examples are always correct, and provide a reliable source for RAG (Retrieval Augmented Generation) systems.

**Source Document:** `gaspatchio-core/ref/10-docstring-parser/10-into.md`

---

## Milestone 1: Core Models and Parsing Foundation

### Prompt 1.1: Setup Directory Structure and Basic Pydantic Models

```text
**Context:**
We are starting to build the Gaspatchio docstring processing engine. The first step is to establish the directory structure and define the core Pydantic models that will represent parsed docstrings and their components. Refer to Section 2 and Section 3 of `10-into.md` for the proposed layout and initial model fields.

**Task:**
1.  Create the following directory structure if it doesn\'t exist:
    *   `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/`
    *   `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/`
2.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/models.py`, define the following Pydantic models:
    *   `DocstringCodeExample(BaseModel)`:
        *   `snippet: str` (the raw code snippet, e.g., ">>> print(\'hello\')\\nhello")
        *   `output: Optional[str]` (the expected output following the snippet, if any)
        *   `object_context: str` (e.g., "my_module.my_function")
        *   `example_index: int` (0-based index of the example within its docstring)
        *   `raw_source_location: tuple[str, int]` (filename, starting line number of the example in the docstring)
    *   `DocstringParameter(BaseModel)`: (Placeholder for now)
        *   `name: str`
        *   `type_name: Optional[str]`
        *   `description: str`
    *   `DocstringReturn(BaseModel)`: (Placeholder for now)
        *   `type_name: Optional[str]`
        *   `description: str`
    *   `GaspatchioDocstring(BaseModel)`:
        *   `short_description: Optional[str]`
        *   `long_description: Optional[str]`
        *   `parameters: list[DocstringParameter]`
        *   `returns: Optional[DocstringReturn]`
        *   `examples: list[DocstringCodeExample]`
        *   `raw_docstring: str` (the full, original docstring text)
        *   `object_path: str` (fully qualified path to the object, e.g., "module.submodule.ClassName.method_name")
        *   `file_path: str` (path to the source file containing the docstring)
        *   `start_line: int` (1-indexed starting line number of the docstring in the file)

3.  Ensure all necessary imports (e.g., `BaseModel`, `Optional`, `list`, `Any`, `Iterable` from `pydantic` and `typing`) are included.
4.  Create an empty `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/__init__.py`.
5.  Create an empty `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/__init__.py`.

**Testing:**
No direct runtime tests for this step, but the model definitions should be syntactically correct and importable. Subsequent steps will test their usage.
```

### Prompt 1.2: Initial Docstring Parsing Logic

```text
**Context:**
With the basic Pydantic models defined in `models.py`, we now need to implement the initial parsing logic. This will involve identifying and migrating useful functionality from the existing `gaspatchio-mix/src/gaspatchio_mix/docs/doc_string_parser.py` into the new, specified structure. The old `doc_string_parser.py` will eventually be deleted. The goal is to extract docstrings from Python files and populate our `GaspatchioDocstring` and `DocstringCodeExample` models, focusing on correctly identifying and extracting example blocks. Refer to Section 1 (Objective 1) and Section 2 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/parse.py`, create a class `GaspatchioDocstringParser`.
2.  Review `gaspatchio-mix/src/gaspatchio_mix/docs/doc_string_parser.py`. Identify core logic for file processing, AST node iteration, docstring retrieval, and example extraction (especially from `_process_node_docstring`, `_extract_examples_from_doc`, `_parse_custom_examples`). This logic will be selectively migrated and refactored, not directly copied.
3.  Implement a method `parse_docstring_from_text(self, docstring_text: str, object_path: str, file_path: str, start_line: int) -> Optional[GaspatchioDocstring]` within the new `GaspatchioDocstringParser`.
    *   This method should take raw docstring text and its context.
    *   It should use `docstring_parser` (the library) for parsing short/long descriptions, parameters, and returns, similar to how the old parser does. Map the parsed data to the new `DocstringParameter` and `DocstringReturn` Pydantic models.
    *   Crucially, migrate and adapt the logic for identifying and parsing code example blocks from the old parser. An example starts with `>>>` and includes subsequent lines until a non-indented line or another `>>>`. If an example has output, it appears directly after its code lines. The approaches in `_extract_examples_from_doc` and `_parse_custom_examples` should be refactored into this method or helper methods within the new class.
    *   Populate `DocstringCodeExample` instances:
        *   `snippet`: The part starting with `>>>` up to the start of its output or the next example (migrate logic from how `code` and `output` fields were derived in the old parser).
        *   `output`: The lines immediately following the snippet if they don't start with `>>>` and are part of the example output.
        *   `object_context`: The `object_path` passed to the method.
        *   `example_index`: The 0-based index (the old parser's `example_index` logic can be a reference).
        *   `raw_source_location`: (`file_path`, line_number_of_`>>>`_in_docstring). This will require careful implementation. The `start_line` of the docstring is a known input; the relative line of the `>>>` within the docstring text must be calculated. A placeholder like `(file_path, 0)` is acceptable for an initial pass if precise calculation is too complex upfront.
    *   Return a `GaspatchioDocstring` instance.
4.  Implement a method `process_file(self, file_path: Path) -> list[GaspatchioDocstring]` in the new parser.
    *   This method will use `ast` to find all functions, classes, and methods in the Python file.
    *   For each discovered object, it will retrieve its docstring using `ast.get_docstring()`.
    *   It will then use the `parse_docstring_from_text` method (or its underlying refactored logic) to parse the docstring. The way the old `_process_node_docstring` handled AST nodes can serve as a reference for structuring this.
    *   Collect and return all successfully parsed `GaspatchioDocstring` objects.
5.  Implement `GaspatchioDocstringParser.process_files(self, root_dir: Path) -> list[GaspatchioDocstring]` in the new parser.
    *   This method should scan all `*.py` files in `root_dir` (recursively). The old parser's `process_files` (which used `directory_path` from `__init__`) is conceptually similar.
    *   It will call `process_file` for each Python file found and aggregate the list of `GaspatchioDocstring` objects.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_parse.py`:
1.  Create a test file (e.g., `sample_module.py`) with various docstrings:
    *   Function with a simple `>>> print("Hello")`
    *   Function with `>>> print("World")\\nWorld`
    *   Function with multiple examples.
    *   Function with examples that have multi-line inputs (`...`) and outputs.
    *   Class with docstring and method with docstring examples.
    *   Docstrings without examples.
2.  Write tests for `GaspatchioDocstringParser`:
    *   Test `parse_docstring_from_text` directly with sample docstring texts. Verify correct extraction of snippets and outputs.
    *   Test `process_file` with your `sample_module.py`. Verify the number of `GaspatchioDocstring` objects returned and the content of `DocstringCodeExample` instances (especially `snippet` and `output`).
```

---

## Milestone 2: Validation and Pytest Integration

### Prompt 2.1: `validate_structure` Method and `iter_examples`

```text
**Context:**
Now that we can parse docstrings into `GaspatchioDocstring` models, we need to add structural validation capabilities as described in Section 3 of `10-into.md`. We\'ll also add a helper to iterate through examples.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/models.py`:
    *   Add the following methods to `GaspatchioDocstring`:
        *   `validate_structure(self) -> list[str]`:
            *   Checks:
                *   `short_description` exists and is not empty.
                *   (Skip parameter count/name matching for now, as `inspect.signature` integration is complex. Add a TODO).
                *   Each `DocstringCodeExample` in `self.examples` has at least one line starting with `>>>` in its `snippet`.
                *   For each example, if its `snippet` seems to end with a pure expression (e.g., not an assignment, not a print, not a def/class), its `output` should be non-empty. (This is a heuristic; e.g. last line doesn\'t start with `print(` and is not an assignment).
                *   (Skip `returns` section check for now. Add a TODO).
            *   Return a list of human-readable issue strings. An empty list means no issues.
        *   `iter_examples(self) -> Iterable[DocstringCodeExample]`:
            *   A simple generator that yields each example in `self.examples`.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_models.py` (use this file):
1.  Create test cases for `GaspatchioDocstring.validate_structure`:
    *   A valid docstring model instance.
    *   Instance with missing `short_description`.
    *   Instance with an example that has no `>>>` lines in its `snippet`.
    *   Instance with an example ending in an expression but `output` is `None` or empty.
    *   Verify that the returned list of issues is accurate.
2.  Test `iter_examples` to ensure it yields all examples correctly.
```

### Prompt 2.2: Ruff Linting for Examples

```text
**Context:**
Docstring examples should be high-quality code. We will integrate Ruff for linting these examples directly via its Python API, as outlined in Section 4.1 of `10-into.md`.

**Task:**
1.  Ensure `ruff` is added as a project dependency.
2.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/models.py`:
    *   Add the following method to `DocstringCodeExample`:
        *   `lint(self) -> list[str]`:
            *   This method should use `ruff.check` (or its modern equivalent, e.g., `ruff.lint` from `ruff_api` if available and preferred for stability) to lint `self.snippet`.
            *   To use `ruff.check`, you might need to extract only the Python code from the `>>>` and `...` lines, stripping the prompts. Create a helper for this if necessary (e.g. `_extract_code_from_snippet() -> str`).
            *   The `filename` argument to `ruff.check` can be a virtual filename like `f"{self.object_context}_example_{self.example_index}.py"`.
            *   Ruff configuration will be picked up from `pyproject.toml` if run in the project context.
            *   Return a list of human-readable Ruff issue messages (e.g., `f"LINT {problem[\'code\']}: {problem[\'message\']} at line {problem[\'location\'][\'row\']}"`). An empty list means no issues.
            *   Handle potential exceptions during Ruff invocation gracefully.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_models.py`:
1.  Add test cases for `DocstringCodeExample.lint`:
    *   An example snippet with clean code (should return an empty list).
    *   An example snippet with obvious Ruff violations (e.g., unused import, undefined variable if Ruff checks for that by default). Ensure `pyproject.toml` has some basic Ruff rules enabled for testing this.
    *   Verify that the returned list of issues is accurate.
    *   Test how it handles snippets that are not pure Python (e.g. if a snippet is just `>>> # some comment`, or `>>> 1 / 0` without output check yet). Ruff should ideally not crash.
```

### Prompt 2.3: Pytest Plugin - Initial Setup and Example Discovery

```text
**Context:**
We want to use pytest to discover and run our docstring examples. This step involves creating the basic pytest plugin structure, registering a custom marker, and implementing the example discovery mechanism (`find_examples`) as described in Section 5 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/pytest_plugin.py`:
    *   Import necessary modules: `pytest`, `Path` from `pathlib`.
    *   Import `DocstringCodeExample` from `.models` and `GaspatchioDocstringParser` from `.parse`.
    *   Implement `pytest_configure(config)`:
        *   Register a marker: `config.addinivalue_line("markers", "gaspatchio_docstring_example: mark test as a Gaspatchio docstring example")`.
    *   Implement `find_examples(root_dir_str: str) -> list[DocstringCodeExample]`:
        *   Takes a string path `root_dir_str` (e.g., "src", or the project root).
        *   Converts `root_dir_str` to a `Path` object.
        *   Instantiates `GaspatchioDocstringParser()`.
        *   Calls `parser.process_files(root_path)` to get all `GaspatchioDocstring` objects.
        *   Iterates through these docstrings and their examples, collecting all `DocstringCodeExample` instances.
        *   For each `DocstringCodeExample`, ensure its `parent_docstring: GaspatchioDocstring` attribute is set (you might need to modify `GaspatchioDocstringParser` or `GaspatchioDocstring.iter_examples` to pass this context or add a backreference when parsing). This is needed for `validate_structure`.
        *   Return the flat list of all found `DocstringCodeExample` objects.
    *   Add an `__all__` to export necessary symbols if planning to make this a more formal sub-package.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_pytest_plugin.py` (create this file):
1.  Set up a small test directory with a few Python files containing docstring examples (similar to `test_parse.py`).
2.  Write a test for `find_examples`:
    *   Call `find_examples` pointing to your test directory.
    *   Verify that the correct number of `DocstringCodeExample` objects are returned.
    *   Check attributes of a few returned examples (e.g., `snippet`, `object_context`).
    *   Verify that `example.parent_docstring` is correctly populated and accessible.
3.  To test `pytest_configure`, you might need a `pytester` fixture if doing more advanced pytest plugin testing. For now, a manual check by running pytest with a placeholder test using the marker later will suffice.
```

### Prompt 2.4: Pytest Test Function - Initial Validation (xfail)

```text
**Context:**
With examples discovered by `find_examples`, we now create the actual pytest test function that will validate each example. This test will perform structural validation and Ruff linting. Initially, we will mark it as `xfail` because many existing examples might not pass yet. This is based on Section 5 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/pytest_plugin.py`:
    *   Define `pytest_generate_tests(metafunc)`:
        *   If `'docstring_example_fixture'` (choose a unique fixture name) is in `metafunc.fixturenames`:
            *   Get the project root or a configurable source directory (e.g., from a pytest option or hardcoded for now like "src/gaspatchio_core" or a more specific test path).
            *   Call `examples = find_examples(source_directory_path)`.
            *   Parametrize the test with these examples: `metafunc.parametrize("docstring_example_fixture", examples, ids=lambda ex: f"{ex.object_context}-ex{ex.example_index}")`.
    *   Define the test function:
        ```python
        import pytest # at the top

        @pytest.mark.gaspatchio_docstring_example
        @pytest.mark.xfail(reason="Initial run; examples may need fixing or validation logic refinement.")
        def test_gaspatchio_docstring_example(docstring_example_fixture: DocstringCodeExample):
            example = docstring_example_fixture # clarity

            # 1. Structural validation of the parent docstring
            # Assuming parent_docstring is now an attribute of DocstringCodeExample
            if not hasattr(example, \'parent_docstring\') or example.parent_docstring is None:
                pytest.fail(f"Example {example.object_context}#{example.example_index} is missing parent_docstring link.")
            
            structure_errors = example.parent_docstring.validate_structure()
            if structure_errors:
                pytest.fail(
                    f"Docstring structure errors for {example.object_context}:\\n" +
                    "\\n".join(structure_errors),
                    pytrace=False
                )

            # 2. Ruff linting of the example snippet
            lint_errors = example.lint()
            if lint_errors:
                pytest.fail(
                    f"Linting errors in {example.object_context}#{example.example_index}:\\n" +
                    "\\n".join(lint_errors),
                    pytrace=False
                )
        ```

**Testing:**
1.  Create a `conftest.py` at `gaspatchio-core/bindings/python/gaspatchio_core/tests/conftest.py` (or a higher level if it makes sense for pytest discovery) and ensure it has:
    `pytest_plugins = "gaspatchio_core.examples.docstrings.pytest_plugin"`
2.  Run `uv run pytest -m gaspatchio_docstring_example` (or your marker name) from the `gaspatchio-core/bindings/python/` directory (or wherever your tests are runnable).
3.  You should see tests being discovered and marked as `XFAIL` or `XPASS` (if some examples happen to pass).
4.  Intentionally introduce a structural error in one test docstring and a lint error in another. Verify that if you were to remove `xfail`, these tests would fail with the correct messages.
```

---

## Milestone 3: Execution, Output Diff, Rewrite, and Strict Mode

### Prompt 3.1: `DocstringCodeExample.run` Method

```text
**Context:**
To check if docstring examples are correct, we need to execute their code and capture their output. This step implements the `run` method on `DocstringCodeExample` as described in Section 3 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/models.py`:
    *   Add necessary imports: `import io`, `import contextlib`, `from typing import Any, Tuple`.
    *   Add the `run(self, global_vars: Optional[dict] = None) -> Tuple[str, Any, Optional[Exception]]` method to `DocstringCodeExample`:
        *   The method should prepare the snippet for execution. This involves:
            *   Extracting executable Python code: Remove `>>>` and `...` prompts.
            *   If the snippet is a single expression, it can be run with `eval()`. If it\'s multiple statements, it needs `exec()`. Handle both. A simple heuristic: if it contains newlines, use `exec`.
        *   Create a local dictionary for `exec` or `eval` to run in. If `global_vars` is provided, copy it to initialize this local scope.
        *   Use `io.StringIO` and `contextlib.redirect_stdout` to capture anything printed to standard output.
        *   Execute the code:
            *   If using `exec()`: Iterate through lines. If the *last* line can be `eval`ed (e.g. it's not an assignment or statement), `eval` it separately after `exec`ing preceding lines, to get its value. Otherwise, the value of the last expression is `None`.
            *   If using `eval()`: The result of `eval()` is the value.
        *   Store the captured stdout (as a string) and the value of the last expression (if any).
        *   The method should catch any exceptions during execution.
        *   Return a tuple: `(captured_stdout_str, last_expression_value, exception_if_any)`.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_models.py`:
1.  Test `DocstringCodeExample.run` with various snippets:
    *   Snippet with `print()` statements: Verify captured stdout.
    *   Snippet ending in a simple expression (e.g., `1 + 1`): Verify `last_expression_value` and empty stdout.
    *   Snippet with multiple statements and a final expression.
    *   Snippet with assignments and then an expression.
    *   Snippet that raises an exception: Verify the exception is returned and stdout/value are as expected.
    *   Snippet with multi-line statements.
    *   Provide `global_vars` (e.g. pre-defined variables or imports) and test if the snippet can use them.
```

### Prompt 3.2: `EvalExample` Class for Checking and Doctest Compatibility

```text
**Context:**
We need a mechanism similar to `pytest-examples`' `EvalExample` to manage the checking of example outputs against expected outputs, including doctest compatibility. This step focuses on the `run_print_check` part, incorporating doctest execution and output normalization, as per Sections 4.2 and 4.3 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/validate.py` (create this file):
    *   Import necessary modules: `doctest`, `textwrap`, `io`, `contextlib`.
    *   Import `DocstringCodeExample` from `.models`.
    *   Create a class `GaspatchioEvalExample`:
        *   `__init__(self, update_examples_mode: bool = False)`
        *   Method `run_doctest_check(self, example: DocstringCodeExample) -> list[str]`:
            *   Creates a `doctest.DocTestParser` and parses `example.snippet` (potentially prefixed with `example.object_context` for namespacing if needed by doctest, though usually not for simple snippets).
            *   Creates a `doctest.DocTestRunner`.
            *   Runs the test.
            *   Captures failures/mismatches from the runner.
            *   Return a list of failure messages. Empty if OK.
        *   Method `run_custom_check(self, example: DocstringCodeExample, global_vars: Optional[dict] = None) -> list[str]`:
            *   Calls `example.run(global_vars=global_vars)` to get `captured_stdout, last_expr_value, exc`.
            *   If `exc` is not None: return `[f"Runtime error: {type(exc).__name__}: {exc}"]`.
            *   Determine the `actual_output`:
                *   If `example.output` is not None (i.e., output is explicitly in the docstring):
                    *   The `actual_output` to compare against is `captured_stdout.rstrip()`.
                    *   The `expected_output` is `textwrap.dedent(example.output).rstrip()`.
                *   Else (no explicit output in docstring, implies we check the last expression value):
                    *   The `actual_output` is `repr(last_expr_value)` if `last_expr_value` is not None, else `""`. (Consider `str()` for Polars objects later, but `repr` is safer generally).
                    *   The `expected_output` is what would have been generated if `run_print_update` ran. This is tricky for check mode. For now, if `example.output` is None, this check passes if `captured_stdout` is empty, and we rely on `run_doctest_check` or assume the user will use `--update-examples` if the value needs to be captured. *Alternatively, and perhaps better for `run_print_check` when `example.output` is `None`: if `last_expr_value` is not `None`, this implies an error because the docstring is *missing* an output for an expression that yields a value. If `last_expr_value` is `None` and `captured_stdout` is empty, it passes.* For now, let\'s simplify: if `example.output` is `None`, this check mainly verifies no unexpected stdout and no errors. The main comparison happens when `example.output` is present.
            *   If `example.output` is not None:
                *   Compare `textwrap.dedent(actual_output).rstrip()` with `textwrap.dedent(expected_output).rstrip()`.
                *   If they differ, return a list with a diff string or mismatch message.
            *   Return an empty list if checks pass.
        *   Method `check_example(self, example: DocstringCodeExample, global_vars: Optional[dict] = None) -> list[str]`:
            *   This method orchestrates the checks.
            *   Call `run_doctest_check`. If errors, return them.
            *   Call `run_custom_check`. If errors, return them.
            *   Return empty list if all pass.

**Testing:**
In `gaspatchio-core/bindings/python/gaspatchio_core/tests/examples/docstrings/test_validate.py` (create this file):
1.  Test `GaspatchioEvalExample.run_doctest_check`:
    *   Example that passes doctest.
    *   Example that fails doctest (e.g., output mismatch).
2.  Test `GaspatchioEvalExample.run_custom_check`:
    *   Example with explicit `output` that matches `captured_stdout`.
    *   Example with explicit `output` that mismatches.
    *   Example with no explicit `output`, `run()` produces some stdout (should ideally be flagged if we expect no output).
    *   Example with no explicit `output`, `run()` produces a `last_expr_value` (how to handle this in check mode needs clarification based on the chosen logic above; for now, test that it doesn't crash).
    *   Example that raises an error during `run()`.
    *   Test whitespace normalization (`textwrap.dedent`, `rstrip`).
3.  Test `GaspatchioEvalExample.check_example` orchestrates these correctly.
```

### Prompt 3.3: Integrate `GaspatchioEvalExample` into Pytest Test Function

```text
**Context:**
Now we integrate the `GaspatchioEvalExample` logic into our pytest test function. This will replace the `xfail` with actual checks for example execution and output correctness. This follows Section 5 of `10-into.md`.

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/pytest_plugin.py`:
    *   Import `GaspatchioEvalExample` from `.validate`.
    *   Create a pytest fixture `eval_example_fixture(request)`:
        ```python
        @pytest.fixture
        def eval_example_fixture(request):
            # update_examples_mode = getattr(request.config, "update_examples_mode", False) # Or however you pass this flag
            # A more robust way to get --update-examples or --accept:
            update_mode = request.config.getoption("gp_update_examples") # Matches addoption
            # update_examples_mode = request.config.getoption("update_examples", False) or \\
            #                        request.config.getoption("accept", False) # if you add these options
            return GaspatchioEvalExample(update_examples_mode=update_mode)
        ```
    *   Modify `test_gaspatchio_docstring_example`:
        *   Remove `@pytest.mark.xfail`.
        *   Add `eval_example_fixture` as a parameter.
        *   After linting, if there are no errors:
            ```python
            # ... (structure and lint checks as before) ...

            # 3. Execute and check example output
            eval_example = eval_example_fixture # Use the fixture
            
            global_vars = {} # Placeholder

            if eval_example.update_examples_mode:
                # In update mode, for now, we'll just pass the test or log.
                # The actual call to eval_example.update_example_output() 
                # and related file writing will be added in Prompt 3.5 (Rewriting Logic).
                # For example, one might skip the test or mark as passed:
                print(f"INFO: Update mode ON for {example.object_context}#{example.example_index}. Actual update will be handled in a later stage.")
                # pytest.skip("Update mode active, actual update handled in rewrite stage.") 
                # Or simply let it pass without assertion for now.
                # The test should not fail if in update mode at this stage.
            else:
                execution_errors = eval_example.check_example(example, global_vars=global_vars)
                if execution_errors:
                    pytest.fail(
                        f"Execution/validation errors in {example.object_context}#{example.example_index}:\\n" +
                        "\\n".join(execution_errors),
                        pytrace=False
                    )
            ```
    *   Add `pytest_addoption(parser)` to register an `--gp-update-examples` flag (renamed for clarity and consistency):
        ```python
        def pytest_addoption(parser):
            group = parser.getgroup("gaspatchio_docstring_examples")
            group.addoption(
                "--gp-update-examples", # Consistent naming
                action="store_true",
                default=False,
                help="Update docstring example outputs in files instead of checking them.",
            )
            # Example of adding the source directory option if it wasn't there
            # This option is now defined in Prompt 2.3 (Pytest Plugin - Initial Setup)
            # Ensure it's correctly named and accessed if needed here or in pytest_generate_tests.
            # group.addoption(
            #     "--gp-examples-dir",
            #     action="store",
            #     default="src/gaspatchio_core", 
            #     help="Directory to scan for Python files with docstring examples.",
            # )
        ```
    *   Ensure the `eval_example_fixture` uses `request.config.getoption("gp_update_examples")`.
    *   The test function signature will be `def test_gaspatchio_docstring_example(docstring_example_fixture: DocstringCodeExample, eval_example_fixture: GaspatchioEvalExample):`.


**Testing:**
1.  Run `uv run pytest -m gaspatchio_docstring_example`.
2.  Tests should now run without `xfail`.
3.  Correct examples should pass. Incorrect examples should fail.
4.  Run with `uv run pytest -m gaspatchio_docstring_example --gp-update-examples`. Tests that would have failed due to output mismatch should now pass (or be skipped/logged as per the implementation decision above), as the update logic is not yet active.
```

### Prompt 3.4: CLI Entry Points

```text
**Context:**
To make the docstring tools easily usable from the command line and in CI, we need to create CLI entry points as described in Section 8 of `10-into.md`. We'll use a library like Typer or Click.

**Task:**
1.  Add `typer` as a project dependency.
2.  Create `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/cli.py`:
    ```python
    import typer
    from pathlib import Path
    import json
    from typing import List, Optional # Ensure Optional is imported

    # Assume these modules and classes will exist and be importable
    from .parse import GaspatchioDocstringParser
    from .models import DocstringCodeExample, GaspatchioDocstring 
    from .validate import GaspatchioEvalExample 

    app = typer.Typer(help="Gaspatchio Docstring Utilities.")

    @app.command()
    def parse(
        root_dir: Optional[Path] = typer.Argument(None, help="Root directory to scan for Python files. Ignored if --file is used.", exists=True, file_okay=False, dir_okay=True, readable=True),
        target_file: Optional[Path] = typer.Option(None, "--file", help="Target a single Python file.", exists=True, file_okay=True, dir_okay=False, readable=True),
        target_method: Optional[str] = typer.Option(None, "--method", help="Target a specific method/function (e.g., 'ClassName.method'). Requires --file."),
        output_file: Optional[Path] = typer.Option(None, "--out", help="JSON output file path. Prints to stdout if not provided.")
    ):
        """Parses Gaspatchio docstrings and outputs them as JSON."""
        if target_method and not target_file:
            typer.echo(typer.style("Error: --method option requires --file option to be specified.", fg=typer.colors.RED))
            raise typer.ExitCode(1)
        if not root_dir and not target_file:
            typer.echo(typer.style("Error: Either root_dir argument or --file option must be provided.", fg=typer.colors.RED))
            raise typer.ExitCode(1)

        parser = GaspatchioDocstringParser()
        docstrings: List[GaspatchioDocstring] = []

        if target_file:
            typer.echo(f"Parsing single file: {target_file}")
            docstrings = parser.process_file(target_file)
        elif root_dir: # root_dir is now Optional, so check it
            typer.echo(f"Parsing directory: {root_dir}")
            docstrings = parser.process_files(root_dir)
        
        if target_method:
            if not target_file: # Should be caught above, but as a safeguard
                typer.echo(typer.style("Error: --method option requires --file to be specified for filtering.", fg=typer.colors.RED))
                raise typer.ExitCode(1)
            original_count = len(docstrings)
            docstrings = [
                d for d in docstrings 
                if target_method in d.object_path 
            ]
            typer.echo(f"Filtered {original_count} docstrings down to {len(docstrings)} matching method '*{target_method}*' in file {target_file}")

        docstrings_json = [d.model_dump() for d in docstrings]
        
        if not docstrings_json:
            typer.echo(typer.style("No docstrings found or matched the criteria.", fg=typer.colors.YELLOW))

        if output_file:
            with open(output_file, "w") as f:
                json.dump(docstrings_json, f, indent=2)
            typer.echo(f"Docstrings saved to {output_file}")
        elif docstrings_json: 
            typer.echo(json.dumps(docstrings_json, indent=2))

    @app.command(name="run-print-check")
    def run_print_check_command(
        root_dir: Optional[Path] = typer.Argument(None, help="Root directory to scan. Ignored if --file is used.", exists=True, file_okay=False, dir_okay=True, readable=True),
        target_file: Optional[Path] = typer.Option(None, "--file", help="Target a single Python file.", exists=True, file_okay=True, dir_okay=False, readable=True),
        target_method: Optional[str] = typer.Option(None, "--method", help="Target a specific method/function (e.g., 'ClassName.method'). Requires --file.")
    ):
        """Parses and runs execution checks (doctest & custom) for examples."""
        if target_method and not target_file:
            typer.echo(typer.style("Error: --method option requires --file option.", fg=typer.colors.RED))
            raise typer.ExitCode(1)
        if not root_dir and not target_file:
            typer.echo(typer.style("Error: Either root_dir argument or --file option must be provided.", fg=typer.colors.RED))
            raise typer.ExitCode(1)

        parser = GaspatchioDocstringParser()
        parsed_docstrings: List[GaspatchioDocstring] = []

        if target_file:
            typer.echo(f"Checking examples in single file: {target_file}")
            parsed_docstrings = parser.process_file(target_file)
        elif root_dir:
            typer.echo(f"Checking examples in directory: {root_dir}")
            parsed_docstrings = parser.process_files(root_dir)
        
        if not parsed_docstrings:
            typer.echo(typer.style("No docstrings found to check.", fg=typer.colors.YELLOW))
            raise typer.ExitCode(0)

        all_examples: List[DocstringCodeExample] = []
        for docstring_obj in parsed_docstrings:
            for example_obj in docstring_obj.examples:
                example_obj.parent_docstring = docstring_obj 
                all_examples.append(example_obj)
        
        if target_method:
            if not target_file: 
                typer.echo(typer.style("Error: --method requires --file for filtering examples.", fg=typer.colors.RED))
                raise typer.ExitCode(1)
            original_count = len(all_examples)
            all_examples = [
                ex for ex in all_examples 
                if target_method in ex.object_context 
            ]
            typer.echo(f"Filtered {original_count} examples down to {len(all_examples)} matching method '*{target_method}*' in file {target_file}")

        if not all_examples:
            typer.echo(typer.style("No examples found or matched the criteria to check.", fg=typer.colors.YELLOW))
            raise typer.ExitCode(0)

        eval_example_checker = GaspatchioEvalExample(update_examples_mode=False)
        total_examples_checked = 0
        total_errors_found = 0
        
        typer.echo(f"Found {len(all_examples)} examples to check.")

        for example in all_examples:
            total_examples_checked += 1
            global_vars = {} 
            errors = eval_example_checker.check_example(example, global_vars=global_vars)
            if errors:
                total_errors_found += len(errors)
                error_header = f"Errors in {example.object_context} - Example #{example.example_index} (File: {example.raw_source_location[0]}, Line: {example.raw_source_location[1]}):"
                typer.echo(typer.style(error_header, fg=typer.colors.RED, bold=True))
                for error_msg in errors:
                    typer.echo(f"- {error_msg}")
            else:
                pass 

        if total_errors_found > 0:
            summary_message = f"\\nFound {total_errors_found} errors in {total_examples_checked} examples checked."
            typer.echo(typer.style(summary_message, fg=typer.colors.RED, bold=True))
            raise typer.ExitCode(1)
        else:
            summary_message = f"\\nAll {total_examples_checked} examples checked passed execution checks."
            typer.echo(typer.style(summary_message, fg=typer.colors.GREEN, bold=True))


    @app.command()
    def lint(
        root_dir: Optional[Path] = typer.Argument(None, help="Root directory to scan. Ignored if --file is used.", exists=True, file_okay=False, dir_okay=True, readable=True),
        target_file: Optional[Path] = typer.Option(None, "--file", help="Target a single Python file for linting.", exists=True, file_okay=True, dir_okay=False, readable=True),
        target_method: Optional[str] = typer.Option(None, "--method", help="Target a specific method/function (pytest -k pattern). Requires --file or uses root_dir context."),
        strict: bool = typer.Option(False, "--strict", help="Enable strict mode (passes -x to pytest).")
    ):
        """Lints and validates Gaspatchio docstring examples using pytest."""
        if target_method and not target_file and not root_dir:
             typer.echo(typer.style("Error: --method requires --file or a root_dir to be specified.", fg=typer.colors.RED))
             raise typer.ExitCode(1)
        if not root_dir and not target_file:
            typer.echo(typer.style("Error: Either root_dir argument or --file option must be provided for linting.", fg=typer.colors.RED))
            raise typer.ExitCode(1)
        
        path_to_lint = str(target_file) if target_file else str(root_dir)
        typer.echo(f"Running comprehensive lint and validation for examples in: {path_to_lint}")
        if target_method:
            typer.echo(f"Focusing on method/context: '*{target_method}*'")
        
        typer.echo("Actual implementation would call pytest or refactored validation logic.")
        pytest_args_sim = ["-m", "gaspatchio_docstring_example"]
        if target_file:
            pytest_args_sim.append(str(target_file))
            if target_method:
                pytest_args_sim.extend(["-k", target_method]) 
        elif root_dir: 
            pytest_args_sim.append(str(root_dir))
            if target_method: 
                 pytest_args_sim.extend(["-k", target_method])
        else: 
            pass 

        if strict:
            pytest_args_sim.append("-x")
        typer.echo(f"Simulated pytest call with: {pytest_args_sim}")


    @app.command()
    def update(
        root_dir: Optional[Path] = typer.Argument(None, help="Root directory to scan. Ignored if --file is used.", exists=True, file_okay=False, dir_okay=True, readable=True),
        target_file: Optional[Path] = typer.Option(None, "--file", help="Target a single Python file for update.", exists=True, file_okay=True, dir_okay=False, readable=True),
        target_method: Optional[str] = typer.Option(None, "--method", help="Target a specific method/function (pytest -k pattern). Requires --file or uses root_dir context.")
    ):
        """Updates Gaspatchio docstring example outputs in-place using pytest."""
        if target_method and not target_file and not root_dir:
             typer.echo(typer.style("Error: --method requires --file or a root_dir to be specified.", fg=typer.colors.RED))
             raise typer.ExitCode(1)
        if not root_dir and not target_file:
            typer.echo(typer.style("Error: Either root_dir argument or --file option must be provided for update.", fg=typer.colors.RED))
            raise typer.ExitCode(1)

        path_to_update = str(target_file) if target_file else str(root_dir)
        typer.echo(f"Running example updates for examples in: {path_to_update}")
        if target_method:
            typer.echo(f"Focusing on method/context: '*{target_method}*\' for update")

        typer.echo("Actual implementation would call pytest with the update flag.")
        pytest_args_sim = ["-m", "gaspatchio_docstring_example", "--gp-update-examples"]

        if target_file:
            pytest_args_sim.append(str(target_file))
            if target_method:
                pytest_args_sim.extend(["-k", target_method])
        elif root_dir:
            pytest_args_sim.append(str(root_dir))
            if target_method:
                 pytest_args_sim.extend(["-k", target_method])
        
        typer.echo(f"Simulated pytest call with: {pytest_args_sim}")


    if __name__ == "__main__":
        app()
    ```
3.  Add this entry point to your `pyproject.toml`:
    ```toml
    [project.scripts]
    gp-docstrings = "gaspatchio_core.examples.docstrings.cli:app"
    ```
    With this setup, you would invoke commands like:
    *   `gp-docstrings parse path/to/src`
    *   `gp-docstrings parse --file path/to/file.py --method \"MyClass.my_method\"`
    *   `gp-docstrings parse path/to/your/src/gaspatchio_core` (verify stdout).
    *   `gp-docstrings run-print-check path/to/test/dir_with_examples`
    *   `gp-docstrings run-print-check --file path/to/file.py --method \"month\"`
    *   Run `gp-docstrings lint path/to/src` and `gp-docstrings update path/to/src`.
    *   Run `gp-docstrings lint --file path/to/file.py --method \"ClassName.methodName\" --strict`.
    *   To make `lint` and `update` functional, you would typically use `pytest.main(...)` as detailed in the \"Refinement for `lint` and `update` CLI\" section. The `-k` option for pytest would be key for method-specific targeting.

**Refinement for `lint` and `update` CLI:**
The CLI for `lint` and `update` should ideally not just print simulation messages but actually invoke the pytest execution process.
This typically involves:
```python
# In cli.py commands for lint/update
import pytest
import os # os might not be needed if Path.cwd() and chdir are used from pathlib

# ...
# For lint command:
    # (Inside the lint Typer command function)
    # path_to_lint, target_method (str, optional) would be determined from CLI options.

    typer.echo(f"Executing Pytest for linting in: {path_to_lint}") # path_to_lint defined based on root_dir/target_file
    pytest_args = [
        "-m", "gaspatchio_docstring_example", 
        path_to_lint, 
    ]
    if target_method:
        pytest_args.extend(["-k", target_method]) 
    if strict:
        pytest_args.append("-x") 

    try:
        exit_code = pytest.main(pytest_args)
    finally:
        pass
    
    if exit_code == pytest.ExitCode.OK:
        typer.echo(typer.style("Lint checks passed.", fg=typer.colors.GREEN, bold=True))
    elif exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
        typer.echo(typer.style("No docstring examples found to lint.", fg=typer.colors.YELLOW))
    else:
        typer.echo(typer.style(f"Lint checks failed. Pytest exited with code {exit_code}", fg=typer.colors.RED, bold=True))
        raise typer.ExitCode(1)


# For update command:
    # (Inside the update Typer command function)
    # path_to_update, target_method (str, optional) would be determined similarly.
    typer.echo(f"Executing Pytest for updating examples in: {path_to_update}")
    pytest_args = [
        "-m", "gaspatchio_docstring_example",
        "--gp-update-examples", 
        path_to_update, 
    ]
    if target_method:
        pytest_args.extend(["-k", target_method])
    
    try:
        exit_code = pytest.main(pytest_args)
    finally:
        pass 
        
    if exit_code == pytest.ExitCode.OK:
        typer.echo(typer.style("Docstring examples update process completed successfully.", fg=typer.colors.GREEN, bold=True))
    elif exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
        typer.echo(typer.style("No docstring examples found to update.", fg=typer.colors.YELLOW))
    else:
        typer.echo(typer.style(f"Docstring examples update process failed or had issues. Pytest exited with code {exit_code}", fg=typer.colors.RED, bold=True))
        # raise typer.ExitCode(1) # Or decide based on specific exit_code values
```
This makes the CLI a thin wrapper around the pytest execution logic for `lint` and `update`.
The `parse` and `run-print-check` commands would use the direct parsing and validation logic.
```

### Prompt 3.5: Implement `run_print_update` and Docstring Rewriting Logic

```text
**Context:**
This is a crucial step: implementing the `run_print_update` functionality that regenerates example outputs in docstrings and writes them back to the source files. This involves AST parsing to locate and replace docstrings. Refer to Section 6 of `10-into.md`. The Polars formatting aspect can be simplified for now (use default `repr`/`str`).

**Task:**
1.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/rewrite.py` (create this file):
    *   Import `ast`, `tokenize`, `io`, `pathlib.Path`, `DocstringCodeExample` from `.models`.
    *   Helper function `_format_output_block(captured_stdout: str, last_expr_value: Any) -> str`:
        *   If `captured_stdout` is not empty, format it (e.g., ensure trailing newline).
        *   If `last_expr_value` is not `None`, append `repr(last_expr_value)` (or `str()` if it looks better for common types) to the output block.
        *   Return the combined, formatted string for the new output.
    *   Main function `rewrite_docstring_example_in_file(example_to_update: DocstringCodeExample, new_output_text: str)`:
        *   This is the most complex part. It needs to:
            *   Read the content of `example_to_update.parent_docstring.file_path`.
            *   Use `ast.parse()` to get the AST of the file.
            *   Iterate through AST nodes (functions, classes, methods) to find the AST node corresponding to `example_to_update.parent_docstring.object_path`. This requires matching names and potentially nested structures.
            *   Once the AST node for the object (e.g., `ast.FunctionDef`) is found, get its docstring node (`ast.get_docstring(node, clean=False)` to preserve exact source).
            *   The challenge is to replace *only the output part* of a *specific example* within that docstring.
                *   A simpler initial approach: Regenerate the *entire* docstring for the object, incorporating the new output for the specific example, and then replace the whole docstring. This avoids fine-grained replacement within the docstring text initially.
                *   To do this, you'd re-construct the docstring: short/long desc, params, then iterate `parent_docstring.examples`. If an example is `example_to_update`, use `new_output_text` for its output. Otherwise, use its existing `snippet` and `output`. Then format returns.
                *   Use `ast` utilities or careful string manipulation if you try to replace just the docstring content of the node. The `ast.Constant.value` (for Python 3.8+) or `ast.Str.s` holds the docstring. Modifying it directly in the AST and then using `ast.unparse` (Python 3.9+) or a library like `astor` could work.
            *   A more robust, but harder, method using `tokenize`:
                *   Tokenize the file. Find the docstring token(s).
                *   Within the docstring string, find the start of `example_to_update.snippet`.
                *   Find the end of its old output (or end of snippet if no old output).
                *   Splice in the `new_output_text`.
                *   Reconstruct the file content from tokens or by string slicing the original content.
            *   For now, let's aim for a strategy that reads the file, reconstructs the specific docstring with the updated example, and then replaces that entire docstring in the original file content string. Overwrite the file.
                *   Locate the line range of the original docstring (e.g., from `example_to_update.parent_docstring.start_line` and its length).
                *   Reconstruct the full docstring text for `example_to_update.parent_docstring`, but when it comes to `example_to_update`, use its `snippet` followed by `new_output_text` as its output block. For other examples in the same docstring, use their existing snippet and output.
                *   Read all lines of the file. Replace the lines corresponding to the old docstring with lines of the new docstring. Write back. This is line-based and might be error-prone with multi-line docstrings if line counts change.
        *   **Alternative, simpler strategy for first pass**: The `pytest-examples` tool itself has logic for this via `CodeExampleUpdater`. It might be too complex to replicate fully. A very simplified `rewrite.py` could just print what *would* be written, or save to a new file, deferring in-place updates.
        *   **Compromise for this step**: Focus on getting the *new complete docstring text* for the parent object. The function `rewrite_docstring_example_in_file` will take the `example_to_update`, compute its new output via `example.run()`, format this output, then construct the *entire new text for its parent docstring*, and then replace the old docstring text in the original file. This means we need to be able to reconstruct a docstring from its parts.

2.  In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/validate.py` (class `GaspatchioEvalExample`):
    *   Add method `update_example_output(self, example: DocstringCodeExample, global_vars: Optional[dict] = None) -> bool`:
        *   Calls `example.run(global_vars=global_vars)` to get `captured_stdout, last_expr_value, exc`.
        *   If `exc` is not None, print/log an error and return `False` (cannot update an example that errors).
        *   Format the new output block using a helper like `_format_output_block(captured_stdout, last_expr_value)` from `rewrite.py`.
        *   Call a function from `rewrite.py` (e.g., `rewrite_docstring_example_in_file(example, new_output_block_text)`). This function will handle the file I/O and AST/string manipulation.
        *   Return `True` if update was attempted/successful.

3.  **Update Pytest Plugin**: In `gaspatchio-core/bindings/python/gaspatchio_core/examples/docstrings/pytest_plugin.py` (modify `test_gaspatchio_docstring_example` from Prompt 3.3):
    *   If `eval_example.update_examples_mode` is true (and after other checks like linting pass):
        *   Now, call `eval_example.update_example_output(example, global_vars=global_vars)`.
        *   The test should probably pass if update mode is on, or handle the boolean status returned by `update_example_output` to determine if it should report an issue with the update attempt itself.

**Testing:**
In `gaspatchio-core/bindings/python/tests/examples/docstrings/test_rewrite.py` (create this file):
1.  Prepare a sample Python file with a docstring example.
2.  Test `_format_output_block` with various inputs.
3.  Test `rewrite_docstring_example_in_file` (or its equivalent core logic):
    *   Create a `DocstringCodeExample` instance manually for an example in your sample file.
    *   Provide a `new_output_text`.
    *   Run the rewrite function.
    *   Read the modified file and assert that the docstring example output has been correctly updated.
    *   Test with examples that initially have no output, and examples that have existing output.
    *   Test with a file that has multiple functions/docstrings to ensure only the target one is modified.
4.  For `pytest_plugin.py` integration:
    *   Run pytest with `--gp-update-examples` on a test file where an example's output is intentionally wrong or missing.
    *   After the run, inspect the file to see if the docstring was updated correctly.
    *   Ensure examples that errored during run are not updated.

**Note on `rewrite.py` complexity:**
This is the hardest part. If full AST-based rewrite is too much, a simpler version for `rewrite_docstring_example_in_file` could be:
```python
# In rewrite.py
def generate_updated_docstring_text(parent_docstring: GaspatchioDocstring, example_to_update: DocstringCodeExample, new_output_for_example: str) -> str:
    # Reconstructs the entire text of parent_docstring,
    # replacing the output of example_to_update with new_output_for_example.
    # This requires having all parts of GaspatchioDocstring (desc, params, etc.)
    # and being able to format them back into a string.
    # ... implementation ...
    pass

def replace_docstring_in_file(file_path: str, object_qualname: str, original_docstring_start_line: int, new_docstring_text: str):
    # Reads the file, finds the line range of the old docstring (potentially using ast to confirm location of object_qualname)
    # and replaces those lines with the lines from new_docstring_text.
    # This is still complex due to line number management.
    # ... implementation ...
    pass
```
The key is to isolate the file modification. The `update_example_output` in `validate.py` would call these.
Using `ast.unparse` after modifying the docstring in the AST node is the most robust way if Python 3.9+ is a target.
For Python <3.9, `astor.to_source()` can be used.
If `ast.get_docstring(node, clean=False)` gives the exact original docstring, and `node.body[0]` is the docstring expression `Expr(Constant(value="..."))`, one could modify `node.body[0].value.value` (for Py 3.8+) or `node.body[0].value.s` (older Pythons) and then unparse.
This would change the *content* of the docstring. If only one example changes, the whole docstring string is replaced.
```

---

## Milestone 4: Refinements and Finalization (Conceptual Prompts)

These would be more about reviewing, refining, and adding smaller features from `10-into.md` that might not have been fully covered.

### Prompt 4.1: Strict Mode Implementation and Configuration

```text
**Context:**
Review the "Strictness matrix" (Section 7) and "Ruff config" (Section 11) from `10-into.md`. Ensure that the `--strict` flag (or equivalent mechanism) in the `lint` CLI and pytest runs enforces stricter checks. Also, confirm Ruff configuration is handled as intended.

**Task:**
1.  **Strict Mode Logic**:
    *   In `GaspatchioDocstring.validate_structure()`: If strict mode is active, ensure checks like "Missing Examples section", "Parameter mismatch" (if implemented), and "output absent for expression" lead to failure messages that will fail the test.
    *   In `pytest_plugin.py` / `GaspatchioEvalExample`: If strict mode is active, ensure Ruff lint errors and doctest runner failures are hard failures.
    *   The `--strict` CLI flag for `gp-examples-docstrings-lint` should correctly signal strict mode to the underlying validation logic (e.g., via an environment variable or by passing a flag to `pytest.main`).
2.  **Ruff Configuration**:
    *   Verify that Ruff linting (`DocstringCodeExample.lint`) correctly uses the `pyproject.toml` from the project root.
    *   Test the `# noqa: GP_DOC_EXAMPLE` mechanism (this might require custom Ruff plugin or just a convention that your linting logic respects). For now, standard `# noqa` for specific Ruff codes should work.
3.  **Polars Formatting (Conceptual for `run_print_update`)**:
    *   While full `pyproject.toml` based Polars formatting for `run_print_update` (Section 11) is advanced, ensure that `repr(df)` or `str(df)` for Polars objects in `_format_output_block` (in `rewrite.py`) produces reasonable, consistent output. If specific formatting is critical, this part might need a dedicated effort using `pl.Config`.

**Testing:**
*   Test the `lint` command and pytest runs with and without strict mode, ensuring failures occur as expected under strict settings.
*   Test Ruff linting with examples that should be ignored due to `noqa` comments.
```

### Prompt 4.2: RAG-Specific Hooks and Forward Compatibility

```text
**Context:**
Address Section 10 of `10-into.md` regarding forward compatibility and RAG-specific hooks.

**Task:**
1.  **Serialization**: Ensure `GaspatchioDocstring.model_dump()` produces JSON compatible with existing RAG ingestion pipelines (as mentioned in `10-into.md`).
2.  **Embeddable Chunks (Optional Method)**:
    *   Consider adding an optional method `GaspatchioDocstring.get_embeddable_chunks(self) -> Iterable[tuple[str, dict]]`.
    *   This method would yield tuples of `(text_chunk, metadata_dict)`.
    *   Chunks could be the short/long description, parameter descriptions, and individual examples (code + output).
    *   Metadata could include `object_path`, `chunk_type: "description" | "example" | "parameter"`, `file_path`, `start_line`.
3.  **Error Metadata**:
    *   When `validate_structure` or `lint` produce errors, store these errors in an optional field like `metadata: dict` on the `GaspatchioDocstring` or `DocstringCodeExample` models (e.g., `example.metadata["lint_errors"] = [...]`).
    *   This metadata should be part of the JSON serialization if present.

**Testing:**
*   Verify the JSON output of `GaspatchioDocstring.model_dump()` includes any new metadata fields.
*   If `get_embeddable_chunks` is implemented, test its output structure and content.
```

This set of prompts should guide the LLM through the development of the Gaspatchio docstring processing engine in a structured and testable way.
