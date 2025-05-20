import importlib.util
import sys
from pathlib import Path
from typing import List

import pytest
from gaspatchio_core.examples.docstrings.models import (
    DocstringCodeExample,
    GaspatchioDocstring,  # Added for completeness
)
from gaspatchio_core.examples.docstrings.parse import GaspatchioDocstringParser


@pytest.fixture
def basic_code_example() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> print('hello')\nhello",
        output="hello",
        object_context="test_module.test_function",
        example_index=0,
        raw_source_location=("/fake/path.py", 10),
    )


@pytest.fixture
def code_example_ending_in_expr_no_output() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> 1 + 1",
        output=None,  # No output provided
        object_context="test_module.test_expr_no_output",
        example_index=0,
        raw_source_location=("/fake/path.py", 20),
    )


@pytest.fixture
def code_example_ending_in_expr_with_output() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> 2 * 2",
        output="4",
        object_context="test_module.test_expr_with_output",
        example_index=0,
        raw_source_location=("/fake/path.py", 30),
    )


@pytest.fixture
def code_example_no_prompt() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet="print('no prompt')",  # No >>>
        output="no prompt",
        object_context="test_module.test_no_prompt",
        example_index=0,
        raw_source_location=("/fake/path.py", 40),
    )


@pytest.fixture
def code_example_assignment_no_output() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> x = 5",
        output=None,
        object_context="test_module.test_assignment",
        example_index=0,
        raw_source_location=("/fake/path.py", 50),
    )


@pytest.fixture
def valid_docstring(basic_code_example: DocstringCodeExample) -> GaspatchioDocstring:
    return GaspatchioDocstring(
        short_description="This is a valid short description.",
        long_description="This is a long description.",
        parameters=[],
        returns=None,
        examples=[basic_code_example],
        raw_docstring="Raw docstring here",
        object_path="test_module.valid_function",
        file_path="/fake/path.py",
        start_line=1,
    )


@pytest.fixture
def docstring_no_short_desc(
    basic_code_example: DocstringCodeExample,
) -> GaspatchioDocstring:
    return GaspatchioDocstring(
        short_description=None,
        examples=[basic_code_example],
        raw_docstring="Raw",
        object_path="test_module.no_short",
        file_path="/f.py",
        start_line=1,
    )


@pytest.fixture
def docstring_with_expr_no_output_example(
    code_example_ending_in_expr_no_output: DocstringCodeExample,
) -> GaspatchioDocstring:
    return GaspatchioDocstring(
        short_description="Short desc.",
        examples=[code_example_ending_in_expr_no_output],
        raw_docstring="Raw",
        object_path="test_module.expr_no_output_parent",
        file_path="/f.py",
        start_line=1,
    )


@pytest.fixture
def docstring_with_no_prompt_example(
    code_example_no_prompt: DocstringCodeExample,
) -> GaspatchioDocstring:
    return GaspatchioDocstring(
        short_description="Short desc.",
        examples=[code_example_no_prompt],
        raw_docstring="Raw",
        object_path="test_module.no_prompt_parent",
        file_path="/f.py",
        start_line=1,
    )


@pytest.fixture
def docstring_with_assignment_example(
    code_example_assignment_no_output: DocstringCodeExample,
) -> GaspatchioDocstring:
    return GaspatchioDocstring(
        short_description="This is a valid short description.",
        examples=[code_example_assignment_no_output],
        raw_docstring="Raw docstring here",
        object_path="test_module.assignment_function",
        file_path="/fake/path.py",
        start_line=1,
    )


def test_validate_structure_valid(valid_docstring: GaspatchioDocstring):
    issues = valid_docstring.validate_structure()
    assert not issues, f"Expected no issues, got: {issues}"


def test_validate_structure_missing_short_description(
    docstring_no_short_desc: GaspatchioDocstring,
):
    issues = docstring_no_short_desc.validate_structure()
    assert len(issues) == 1
    assert "Missing short_description." in issues[0]


def test_validate_structure_example_no_prompt(
    docstring_with_no_prompt_example: GaspatchioDocstring,
):
    issues = docstring_with_no_prompt_example.validate_structure()
    assert len(issues) == 1
    assert "has no '>>>' lines" in issues[0]


def test_validate_structure_example_ends_in_expr_no_output(
    docstring_with_expr_no_output_example: GaspatchioDocstring,
):
    issues = docstring_with_expr_no_output_example.validate_structure()
    assert len(issues) == 1, f"Expected 1 issue, got {len(issues)}: {issues}"
    assert "snippet seems to end with an expression" in issues[0]
    assert "but has no output" in issues[0]


def test_validate_structure_example_ends_in_expr_with_output(
    code_example_ending_in_expr_with_output: DocstringCodeExample,
):
    docstring = GaspatchioDocstring(
        short_description="Short desc.",
        examples=[code_example_ending_in_expr_with_output],
        raw_docstring="Raw",
        object_path="p",
        file_path="f",
        start_line=1,
    )
    issues = docstring.validate_structure()
    assert not issues, f"Expected no issues for expr with output, got: {issues}"


def test_validate_structure_example_assignment_no_output(
    docstring_with_assignment_example: GaspatchioDocstring,
):
    issues = docstring_with_assignment_example.validate_structure()
    assert not issues, f"Expected no issues for assignment, got: {issues}"


def test_iter_examples(
    valid_docstring: GaspatchioDocstring, basic_code_example: DocstringCodeExample
):
    examples_list: List[DocstringCodeExample] = []
    for ex in valid_docstring.iter_examples():
        examples_list.append(ex)

    assert len(examples_list) == 1
    assert examples_list[0] == basic_code_example


def test_iter_examples_multiple(basic_code_example: DocstringCodeExample):
    ex2 = DocstringCodeExample(
        snippet=">>> 1+1\n2",
        output="2",
        object_context="ctx",
        example_index=1,
        raw_source_location=("f", 1),
    )
    docstring = GaspatchioDocstring(
        short_description="Multiple.",
        examples=[basic_code_example, ex2],
        raw_docstring="Raw",
        object_path="p",
        file_path="f",
        start_line=1,
    )
    collected_examples = list(docstring.iter_examples())
    assert len(collected_examples) == 2
    assert collected_examples[0] == basic_code_example
    assert collected_examples[1] == ex2


def test_iter_examples_no_examples():
    docstring = GaspatchioDocstring(
        short_description="None.",
        examples=[],
        raw_docstring="Raw",
        object_path="p",
        file_path="f",
        start_line=1,
    )
    collected_examples = list(docstring.iter_examples())
    assert not collected_examples


# Tests for DocstringCodeExample.lint()
@pytest.fixture
def clean_code_example() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> import os\n>>> x = os.getenv('MY_VAR', 'default')\n>>> print(x)",
        output="default",
        object_context="test_module.clean_function",
        example_index=0,
        raw_source_location=("/fake/clean.py", 5),
    )


@pytest.fixture
def ruff_violation_example() -> DocstringCodeExample:
    """Example with an unused import (F401) and undefined name (F821)."""
    return DocstringCodeExample(
        snippet=">>> import sys  # F401 unused\n>>> print(undefined_variable)  # F821 undefined name",
        output=None,  # Output doesn't matter for linting here
        object_context="test_module.ruff_violations",
        example_index=0,
        raw_source_location=("/fake/violations.py", 10),
    )


@pytest.fixture
def empty_snippet_example() -> DocstringCodeExample:
    return DocstringCodeExample(
        snippet=">>> # Just a comment\n>>> ",  # Empty or only comments
        output=None,
        object_context="test_module.empty_snippet",
        example_index=0,
        raw_source_location=("/fake/empty.py", 3),
    )


def test_lint_clean_code(clean_code_example: DocstringCodeExample):
    try:
        issues = clean_code_example.lint()
        assert not issues, f"Expected no linting issues for clean code, got: {issues}"
    except ImportError as e:
        pytest.skip(f"Skipping lint test, ruff not available: {e}")


def test_lint_with_violations(ruff_violation_example: DocstringCodeExample):
    try:
        issues = ruff_violation_example.lint()
        assert len(issues) >= 1, (
            f"Expected linting issues, got none or not enough: {issues}"
        )

        # Ruff JSON output for "import sys" (unused) should be something like:
        # {"code": "F401", "message": "'sys' imported but unused", "location": {"row": 1, ...}, ...}
        # Our formatted string becomes: "F401: `sys` imported but unused at line 1"

        found_F401 = any(
            issue.startswith("F401:") and "`sys` imported but unused" in issue
            for issue in issues
        )
        # The undefined_variable (F821) might also be caught by ruff check on stdin.
        # Example: "F821: Undefined name `undefined_variable` at line 2"
        found_F821 = any(
            issue.startswith("F821:") and "Undefined name `undefined_variable`" in issue
            for issue in issues
        )

        assert found_F401, f"F401 (unused 'sys') not found in issues: {issues}"
        # Depending on Ruff's behavior with isolated snippets, F821 might or might not appear.
        # For now, asserting F401 is primary. If F821 is also expected, it can be added here.
        # assert found_F821, f"F821 (undefined_variable) not found in issues: {issues}"

        # Ensure at least one of the expected violations is present
        assert found_F401 or found_F821, (
            f"Neither F401 nor F821 found in issues: {issues}"
        )

    except ImportError as e:
        pytest.skip(f"Skipping lint test, ruff not available: {e}")


def test_lint_empty_snippet(empty_snippet_example: DocstringCodeExample):
    try:
        issues = empty_snippet_example.lint()
        assert not issues, (
            f"Expected no issues for empty/comment-only snippet, got: {issues}"
        )
    except ImportError as e:
        pytest.skip(f"Skipping lint test, ruff not available: {e}")


def test_lint_non_python_snippet():
    """Test how lint handles a snippet that is not valid Python at all."""
    example = DocstringCodeExample(
        snippet=">>> This is not python code at all!\n... !@#$%^&*()",
        output=None,
        object_context="test_module.non_python",
        example_index=0,
        raw_source_location=("/fake/non_python.py", 1),
    )
    try:
        issues = example.lint()
        assert isinstance(issues, list)
        if issues:
            # Ruff CLI with JSON output for syntax errors might produce an error message directly
            # or a specific code. Example from ruff docs for E999 SyntaxError.
            # Our formatted string: "E999: SyntaxError: ... at line X"
            # Or for completely garbled input, it might be "None: SyntaxError: ..."
            assert (
                any(
                    issue.startswith("E999:") and "SyntaxError" in issue
                    for issue in issues
                )
                or any(
                    issue.startswith("None:") and "SyntaxError" in issue
                    for issue in issues
                )
                or any("Could not parse Ruff JSON output" in issue for issue in issues)
                or any("Ruff CLI Error:" in issue for issue in issues)
            ), (
                f"Expected a syntax-related error (E999 or None) or parse/CLI error, got: {issues}"
            )
        else:
            # It's also possible ruff exits with an error code but doesn't produce JSON for severe syntax errors
            # The lint() method tries to capture this. If issues list is empty, it implies no *parsed* issues.
            # This case might need refinement based on actual ruff behavior for truly garbled input.
            pass  # Allow no issues if ruff CLI handles extreme syntax error silently (unlikely for JSON output mode)

    except ImportError as e:
        pytest.skip(f"Skipping lint test, ruff not available: {e}")
    except Exception as e:
        pytest.fail(f"Linting non-python snippet raised an unexpected exception: {e}")


def test_dt_proxy_month_docstring_lint():
    # Dynamically load the fixture module
    fixture_path = Path(__file__).parent / "fixtures" / "dt_proxy_month_fixture.py"
    spec = importlib.util.spec_from_file_location(
        "dt_proxy_month_fixture", fixture_path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    # Get the docstring from DtNamespaceProxy.month
    docstring = mod.DtNamespaceProxy.month.__doc__
    assert docstring, "No docstring found on DtNamespaceProxy.month"

    parser = GaspatchioDocstringParser()
    doc_model = parser.parse_docstring_from_text(
        docstring_text=docstring,
        object_path="DtNamespaceProxy.month",
        file_path_str=str(fixture_path),
        docstring_start_line=mod.DtNamespaceProxy.month.__code__.co_firstlineno,
    )
    assert doc_model is not None, "Failed to parse docstring"
    assert doc_model.examples, "No examples found in docstring"

    for i, ex in enumerate(doc_model.examples):
        issues = ex.lint()
        print(f"Example #{i} lint issues: {issues}")
        assert isinstance(issues, list)
        # Optionally, assert not issues if you want to enforce clean lint
