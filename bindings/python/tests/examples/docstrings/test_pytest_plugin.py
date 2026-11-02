# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def sample_py_file_1(tmp_path: Path) -> Path:
    content = textwrap.dedent("""
    def func_a():
        \"\"\"Short desc for A.

        >>> print("Hello from A")
        Hello from A
        >>> 1 + 1
        2
        \"\"\"
        pass

    class MyClass:
        \"\"\"Docs for MyClass.\"\"\"
        def method_b(self):
            \"\"\"Short desc for method_b.

            >>> print("Method B here")
            Method B here
            \"\"\"
            pass
    """)
    file_path = tmp_path / "sample_module_1.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_py_file_2(tmp_path: Path) -> Path:
    content = textwrap.dedent("""
    def func_c():
        \"\"\"Only one example.
        >>> "C".lower()
        'c'
        \"\"\"
        pass
    """)
    file_path = tmp_path / "sample_module_2.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def empty_py_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "empty_module.py"
    file_path.write_text("# No docstrings here")
    return file_path


def test_a_lint_failure_without_issues_still_reports(
    request: pytest.FixtureRequest,
) -> None:
    """The lint report has a line for an error that carries no issue: it prints.

    The suggestion lookup read the first issue unconditionally, so a lint
    error with an empty issue list raised UnboundLocalError while its report
    was being written instead of showing it.
    """
    from gaspatchio.examples.docstrings.models import DocstringCodeExample
    from gaspatchio.examples.docstrings.pytest_plugin import (
        DocstringExampleItem,
        DocstringLintError,
    )

    example = DocstringCodeExample(
        snippet="x = 1",
        object_context="module.function",
        example_index=0,
        raw_source_location=("module.py", 1),
    )
    item = DocstringExampleItem.from_parent(
        request.node.parent, name="module.function-ex0", example=example
    )
    with pytest.raises(DocstringLintError) as excinfo:
        raise DocstringLintError(
            item_name=item.name,
            primary_ruff_error_text_for_summary="",
            all_ruff_issues=[],
            snippet="x = 1",
        )

    report = str(item.repr_failure(excinfo))

    assert "LINTING ERROR in Docstring Example" in report
    assert "[No specific Ruff issues extracted from error message]" in report
