from __future__ import annotations

from typing import TypedDict


class LintingSuggestion(TypedDict, total=False):
    """Structure for providing linting error suggestions."""

    error_code: str
    title: str
    description: str
    example_bad_code: str | None
    example_good_code: str | None
    explanation: str | None


def get_linting_suggestion(
    error_code: str, error_message: str
) -> LintingSuggestion | None:
    """
    Provides a detailed suggestion for a given linting error.
    """
    if "E401" == error_code or "Multiple imports on one line" in error_message:
        return {
            "error_code": "E401",
            "title": "Multiple imports on one line",
            "description": "Split multiple imports onto separate lines.",
            "example_bad_code": "import datetime, polars as pl",
            "example_good_code": "import datetime\nimport polars as pl",
            "explanation": "PEP 8 E401 advises against multiple imports on a single line for clarity and readability. Each import should be on its own line.",
        }
    elif "F401" == error_code or "imported but unused" in error_message:
        return {
            "error_code": "F401",
            "title": "Unused import",
            "description": "Remove the unused import or ensure the imported module/variable is used.",
            "explanation": "F401 indicates that a module or name was imported but not used in the code. This can clutter the namespace and potentially confuse readers. Remove it if it's not needed.",
        }
    elif "F821" == error_code or "Undefined name" in error_message:
        return {
            "error_code": "F821",
            "title": "Undefined name",
            "description": "Ensure the variable or name is defined before use (e.g., assignment, import).",
            "explanation": "F821 means a name (variable, function, class, etc.) was used before it was assigned a value or imported. Check for typos or ensure proper initialization.",
        }
    elif "E501" == error_code or "Line too long" in error_message:
        return {
            "error_code": "E501",
            "title": "Line too long",
            "description": "Keep lines under the configured character limit (often 79 or 99 characters) for better readability.",
            "example_bad_code": "long_variable_name = 'this_is_a_very_long_string_that_exceeds_the_typical_line_length_limit_in_python_and_should_be_broken_down'",
            "example_good_code": "long_variable_name = (\n    'this_is_a_very_long_string_that_exceeds_the_typical_line_length_limit'\n    '_in_python_and_should_be_broken_down'\n)",
            "explanation": "PEP 8 E501 suggests limiting line length to improve readability, especially when viewing multiple files side-by-side or on smaller displays.",
        }
    elif "W292" == error_code or "No newline at end of file" in error_message:
        return {
            "error_code": "W292",
            "title": "No newline at end of file",
            "description": "Add a single newline character at the end of the file.",
            "explanation": "PEP 8 W292 recommends a single newline at the end of a file. This is a common convention and can prevent issues with some tools and version control systems.",
        }
    elif (
        "F841" == error_code
        or "local variable" in error_message
        and "is assigned to but never used" in error_message
    ):
        return {
            "error_code": "F841",
            "title": "Unused local variable",
            "description": "Remove the unused local variable or prefix it with an underscore if it's intentionally unused.",
            "example_bad_code": "def my_function():\\n    x = 10\\n    y = 20\\n    return y",
            "example_good_code": "def my_function():\\n    # x = 10 # Removed or commented out\\n    y = 20\\n    return y\\n\\n# Or if intentionally unused for later:\\ndef my_other_function():\\n    _x = 10 # Intentionally unused\\n    y = 20\\n    return y",
            "explanation": "F841 indicates a variable was assigned a value but never used. This can make code harder to read and might indicate a bug or leftover code from refactoring.",
        }
    elif (
        "B006" == error_code
        or "Do not use mutable data structures for argument defaults" in error_message
    ):
        return {
            "error_code": "B006",
            "title": "Mutable default argument",
            "description": "Avoid using mutable objects (like lists or dictionaries) as default values for function arguments. Initialize them to None and create the mutable object inside the function if needed.",
            "example_bad_code": "def add_item(item, my_list=[]):\\n    my_list.append(item)\\n    return my_list",
            "example_good_code": "def add_item(item, my_list=None):\\n    if my_list is None:\\n        my_list = []\\n    my_list.append(item)\\n    return my_list",
            "explanation": "B006 warns against mutable default arguments because the default value is created only once when the function is defined. Subsequent calls without providing that argument will reuse and modify the same mutable object, often leading to unexpected behavior.",
        }
    elif "E722" == error_code or "Do not use bare except" in error_message:
        return {
            "error_code": "E722",
            "title": "Bare except",
            "description": "Avoid using a bare `except:` clause. Specify the exception type(s) you intend to catch.",
            "example_bad_code": "try:\\n    # some operation\\n    x = 1 / 0\\nexcept:\\n    print('An error occurred')",
            "example_good_code": "try:\\n    # some operation\\n    x = 1 / 0\\nexcept ZeroDivisionError:\\n    print('Cannot divide by zero!')\\nexcept Exception as e:\\n    print(f'An unexpected error occurred: {e}')",
            "explanation": "E722 advises against bare `except:` because it catches all exceptions, including system-exiting ones like `SystemExit` or `KeyboardInterrupt`, making it harder to debug and control program flow. Always catch specific exceptions.",
        }
    elif "E711" == error_code or (
        "Comparison to None should be" in error_message and "is None" in error_message
    ):
        return {
            "error_code": "E711",
            "title": "Comparison to None",
            "description": "Use `is None` or `is not None` for comparisons to the `None` singleton.",
            "example_bad_code": "if my_var == None:\\n    print('Variable is None')",
            "example_good_code": "if my_var is None:\\n    print('Variable is None')",
            "explanation": "E711 recommends using `is` or `is not` for None checks because `None` is a singleton object. `is` checks for object identity, which is more reliable and Pythonic for this case than `==` (equality).",
        }
    elif (
        "E712" == error_code
        or "Comparison to True" in error_message
        or "Comparison to False" in error_message
    ):
        return {
            "error_code": "E712",
            "title": "Comparison to True/False",
            "description": "Do not compare boolean values directly to `True` or `False`. Use the value directly in conditions or `not value`.",
            "example_bad_code": "if is_valid == True:\\n    print('Valid')\\nif processed == False:\\n    print('Not processed')",
            "example_good_code": "if is_valid:\\n    print('Valid')\\nif not processed:\\n    print('Not processed')",
            "explanation": "E712 suggests avoiding direct comparison to `True` or `False` (e.g., `var == True`) because it's redundant. Boolean values can be used directly in conditional statements.",
        }
    # Default suggestion if no specific match is found
    return {
        "error_code": error_code,  # Use the original error code
        "title": "Generic Linting Suggestion",
        "description": (
            "Review the linting error message provided by Ruff and correct the code accordingly. "
            "Ensure all imports are used, names are defined, syntax is correct, "
            "and the code adheres to project style guides and best practices."
        ),
        "explanation": (
            f"No specific suggestion is available for error code '{error_code}' yet. "
            "This is a general piece of advice. Please refer to Ruff documentation or web search for more details on this specific error."
        ),
    }


def format_suggestion_for_report(suggestion: LintingSuggestion) -> list[str]:
    """Formats a LintingSuggestion into a list of strings for the report."""
    report_lines = []
    report_lines.append(
        f"  Suggestion (for {suggestion['error_code']} - {suggestion['title']}):"
    )
    report_lines.append(f"    {suggestion['description']}")
    if suggestion.get("example_bad_code") and suggestion.get("example_good_code"):
        report_lines.append("    For example, change:")
        report_lines.append(
            f"      ```python\n      {suggestion['example_bad_code']}\n      ```"
        )
        report_lines.append("    To:")
        report_lines.append(
            f"      ```python\n      {suggestion['example_good_code']}\n      ```"
        )
    if suggestion.get("explanation"):
        report_lines.append(f"    Explanation: {suggestion['explanation']}")
    return report_lines
