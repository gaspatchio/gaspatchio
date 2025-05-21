# Adapting Docstring Parser for Markdown Fenced Code Blocks

This document outlines the necessary changes to adapt the Gaspatchio docstring parsing and validation tools to use Markdown fenced code blocks (```python ... ```) for examples, instead of the current doctest-style (>>> ...) format.
This design has been informed by reviewing libraries such as `pytest-examples`.

## 1. Docstring Format Specification for Examples

-   **Location**: Code examples should reside within the "Examples" section of a docstring.
-   **Code Blocks**: Python code examples must be enclosed in Markdown fenced code blocks with the `python` language identifier.
    ```
    ```python
    # Your Python code here
    print("Hello, world!")
    ```
    ```
-   **Code Block Prefixes/Tags (Metadata)**:
    -   The info string of the Python code block (the part after ` ```python ` on the same line) can be used to specify tags.
    -   Tags are space-separated strings. For example: ` ```python skip no-check-output `
    -   These tags will be parsed and stored in the `DocstringCodeExample` model (e.g., in a `prefix_tags` field) and can be used to control behavior like skipping execution or modifying validation checks.
    -   Common tags to consider:
        -   `skip`: Skip execution and validation of this example.
        -   `expect_failure`: The example is expected to raise an exception during execution.
        -   `no_output_check`: Execute the example, but do not validate its output.
-   **Output Blocks (Primary Method)**:
    -   The expected output of a Python code block should immediately follow it.
    -   The output should be enclosed in a generic fenced block (e.g., ` ``` ` or ` ```text `) or be a simple Markdown paragraph directly following the code block.
    -   The parser will capture the content of the first such paragraph or generic fenced block as its expected output.
    -   If no such block follows, the example is considered to have no expected output (unless specific tags indicate otherwise, e.g. `expect_failure`).
    -   Multi-line outputs are supported. Standard Polars DataFrame string representations, including `shape: ...` lines, are considered part of the output.

    Example with output in a generic fence:
    ```
    Examples
    --------
    Scalar example::

        ```python
        import polars as pl
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        print(df)
        ```
        ```
        shape: (2, 2)
        ┌─────┬─────┐
        │ a   ┆ b   │
        │ --- ┆ --- │
        │ i64 ┆ i64 │
        ╞═════╪═════╡
        │ 1   ┆ 3   │
        │ 2   ┆ 4   │
        └─────┴─────┘
        ```

    Example with output as a paragraph:
    ```
    Examples
    --------
    Simple result::

        ```python
        x = 1 + 1
        x
        ```
        2
    ```

    Example with `skip` tag and no output block:
    ```
    Examples
    --------
    Skipped example::

        ```python skip
        # This example will not be run or validated
        # It might be illustrative or incomplete.
        import os
        os.listdir('/')
        ```
    ```
-   **Alternative Output Styles (Not in initial scope)**:
    -   Libraries like `pytest-examples` support inline output comments (e.g., `print(x) #> output`). While flexible, this can clutter the code block.
    -   For the initial implementation, we will focus on the separate output block method described above for clarity and better handling of multi-line outputs. Support for inline comments could be a future enhancement.

## 2. Changes to `parse.py` (`GaspatchioDocstringParser`)

The primary change is in the `_extract_examples` method.

-   **Parsing Library**: Use `markdown-it-py` to parse the docstring content.
-   **Logic**:
    1.  Input to Markdown parser: The `docstring_text` (likely after `inspect.cleandoc(docstring_text)`).
    2.  Token Iteration: Parse the text using `md = MarkdownIt(); tokens = md.parse(text_to_parse)`.
    3.  Identify Python Code Blocks: Iterate through `tokens`. If `token.type == 'fence'` and `token.info.startswith('python')`, this is a potential code snippet.
        -   `snippet = token.content` (this is dedented by `markdown-it-py`).
        -   `line_in_docstring = token.map[0]` (0-indexed start line of the fence).
        -   `prefix_tags`: Parse `token.info` (e.g., `"python skip a=b"`) to extract tags (e.g., `["skip"]`). Settings like `a=b` could also be parsed if needed, similar to `pytest-examples`' `prefix_settings`. For now, focus on space-separated tags after `python`.
    4.  Identify Output:
        -   After finding a Python code block token, inspect the *next* significant tokens.
        -   If the next token is a generic fence (`token.type == 'fence'` and `not token.info` or `token.info == 'text'`), its content (`token.content`) is the output.
        -   Alternatively, if the next sequence of tokens represents a paragraph (`paragraph_open`, `inline`, `paragraph_close`), the `inline` token's content is the output.
        -   If neither is found directly after, the `output` for the `DocstringCodeExample` is `None`.
    5.  `DocstringCodeExample` Instantiation:
        -   `snippet`: Raw Python code from the fence.
        -   `output`: Extracted output string (stripped), or `None`.
        -   `prefix_tags`: List of parsed tags.
        -   `raw_source_location`: `(file_path_str, line_in_docstring)`.

### Conceptual `_extract_examples` (Illustrative Update):

```python
from markdown_it import MarkdownIt
import inspect
from typing import List, Optional
from .models import DocstringCodeExample # Assuming models.py is in the same directory

# Inside GaspatchioDocstringParser class
def _extract_examples(
    self,
    docstring_text: str,
    object_path: str,
    file_path_str: str,
) -> List[DocstringCodeExample]:
    examples_list: List[DocstringCodeExample] = []
    if not docstring_text:
        return examples_list

    cleaned_docstring_for_md = inspect.cleandoc(docstring_text)
    md = MarkdownIt()
    tokens = md.parse(cleaned_docstring_for_md)

    i = 0
    example_idx_counter = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == 'fence' and token.info.startswith('python'):
            code_snippet = token.content
            line_start_in_cleaned_docstring = token.map[0] if token.map else 0

            # Parse prefix_tags from token.info
            # Example: "python skip no-output-check" -> ["skip", "no-output-check"]
            info_parts = token.info.split()
            parsed_prefix_tags = [part for part in info_parts[1:] if part] # Skip 'python'

            extracted_output: Optional[str] = None
            consumed_output_tokens = 0

            # Look ahead for output: generic fence or a paragraph
            if i + 1 < len(tokens):
                next_token = tokens[i + 1]
                if next_token.type == 'fence' and (not next_token.info or next_token.info.lower() == 'text'):
                    extracted_output = next_token.content.strip()
                    consumed_output_tokens = 1 # Consumed the output fence token
                elif next_token.type == 'paragraph_open':
                    if i + 2 < len(tokens) and tokens[i + 2].type == 'inline' and \
                       i + 3 < len(tokens) and tokens[i + 3].type == 'paragraph_close':
                        extracted_output = tokens[i + 2].content.strip()
                        consumed_output_tokens = 3 # Consumed p_open, inline, p_close
                    # else: malformed paragraph, ignore for output

            example_model = DocstringCodeExample(
                snippet=code_snippet.rstrip("\\n"),
                output=extracted_output,
                object_context=object_path,
                example_index=example_idx_counter,
                raw_source_location=(file_path_str, line_start_in_cleaned_docstring),
                prefix_tags=parsed_prefix_tags, # Store parsed tags
                # parent_docstring will be linked later
            )
            examples_list.append(example_model)
            example_idx_counter += 1
            i += consumed_output_tokens # Advance past code fence and any consumed output tokens
        i += 1
    return examples_list
```

## 3. Changes to `models.py` (`DocstringCodeExample`)

-   **`snippet`**: Stores pure Python code from the ` ```python ` block.
-   **`_extract_code_from_snippet()`**: Can be simplified to `return inspect.cleandoc(self.snippet)` or just `return self.snippet` as the snippet is already clean Python.
-   **`output`**: Stores the string content of the expected output block.
-   **Add `prefix_tags` field**:
    ```python
    # In DocstringCodeExample model
    from typing import List # Add this
    # ...
    prefix_tags: List[str] = Field(default_factory=list)
    ```
-   **`run()` method**: Core logic remains unchanged. It could use `prefix_tags` to modify behavior (e.g., if "expect_failure" is a tag, catch exceptions differently).

## 4. Changes to `validate.py` (`GaspatchioEvalExample`)

-   **`run_custom_check()`**:
    -   Can use `example.prefix_tags` to alter validation logic.
        -   If "skip" in `example.prefix_tags`, this check might be bypassed entirely by the calling code (`cli.py` or `pytest_plugin.py`).
        -   If "no_output_check" in `example.prefix_tags`, skip the output comparison part.
        -   If "expect_failure" in `example.prefix_tags`:
            -   The check should assert that `exc` (exception) *is not* `None`.
            -   If `exc` is `None`, it's an error (failure was expected but didn't happen).
            -   The specific type of exception could also be checked if specified via another tag (e.g., `expect_failure:ValueError`).
    -   The existing output comparison logic remains valid when an output check is performed.

## 5. Changes to `pytest_plugin.py`

-   The plugin can utilize `example.prefix_tags` to modify test behavior.
    -   If "skip" is present, the test item could be marked as skipped by pytest.
    -   If "expect_failure" is present, the test run logic (`DocstringExampleItem.runtest`) should catch exceptions and pass if one occurs, fail if not. Pytest has mechanisms for `pytest.raises` that could be integrated or mimicked.
-   No major structural changes anticipated if the `DocstringCodeExample` interface is updated with tags.

## 6. Ruff Linting Considerations

-   `DocstringCodeExample.lint()` feeds clean Python to Ruff, which is good.
-   The `prefix_tags` could potentially be used to pass specific configurations to Ruff for a given example, though this is an advanced use case.

## 7. Migration and Backwards Compatibility

-   This is a breaking change from `>>>` doctest-style. Existing docstrings need updating.
-   A migration script might be beneficial.

## 8. Open Questions/Refinements from Initial Spec

-   **End of Output Detection**: The updated conceptual code for `_extract_examples` tries to be more specific (generic fence or a full paragraph open-inline-close sequence). This still needs careful implementation to avoid consuming unrelated Markdown elements. The "Vector (list) example::" case in `dt_proxy_month_md_fixture.py` has the output block directly followed by a new heading; the parser should correctly stop at the end of the output. `markdown-it-py`'s token stream should allow for robust detection of block boundaries.
-   **Line Number Precision**: `token.map[0]` from `markdown-it-py` is relative to the string it parsed (the cleaned docstring). This is consistent and usable for `raw_source_location`.
-   **Linking `parent_docstring`**: Continues to be handled externally, e.g., in `cli.py`.
