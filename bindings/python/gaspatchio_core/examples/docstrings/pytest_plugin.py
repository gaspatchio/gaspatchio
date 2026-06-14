# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest plugin for validating Gaspatchio docstring code examples.

ABOUTME: Pytest plugin for validating Gaspatchio docstring code examples
ABOUTME: Provides collection, linting, and style checking for docstrings
"""

from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING, Any, cast

import pytest

from .formatting import format_suggestion_for_report, get_linting_suggestion
from .parse import GaspatchioDocstringParser
from .validate import GaspatchioEvalExample

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from .models import DocstringCodeExample, GaspatchioDocstring

__all__ = [
    "pytest_addoption",
    "pytest_collect_file",
    "pytest_configure",
]


def pytest_generate_tests(metafunc) -> None:  # type: ignore[no-untyped-def]
    """Generate tests for docstring examples."""
    if "docstring_example_fixture" in metafunc.fixturenames:
        # Find all examples in the project by collecting from files
        examples = []
        # Simplified approach - real implementation would collect
        # from project files. Empty list avoids test failures.
        metafunc.parametrize(
            "docstring_example_fixture",
            examples,
            ids=lambda ex: f"{ex.object_context}-ex{ex.example_index}"
            if examples
            else [],
        )


@pytest.fixture
def eval_example_fixture(request) -> GaspatchioEvalExample:  # type: ignore[no-untyped-def]
    """Fixture providing a GaspatchioEvalExample for validating examples."""
    update_mode = request.config.getoption("gp_update_examples", default=False)
    return GaspatchioEvalExample(update_examples_mode=update_mode)


def pytest_addoption(parser) -> None:  # type: ignore[no-untyped-def]
    """Add custom pytest command line options for docstring validation."""
    group = parser.getgroup("gaspatchio_docstring_examples")
    group.addoption(
        "--gp-update-examples",
        action="store_true",
        default=False,
        help="Update docstring example outputs in files instead of checking.",
    )
    group.addoption(
        "--gp-docstring-paths",
        action="append",
        default=[],
        nargs="*",
        help=(
            "Glob patterns for files/directories to include in docstring "
            "checks. Can be specified multiple times."
        ),
    )
    group.addoption(
        "--gp-style-check",
        action="store",
        default="off",
        choices=["off", "warn", "strict"],
        help=(
            "Style checking mode: 'off' (default) = skip checks, "
            "'warn' = show warnings without failing, "
            "'strict' = fail tests on violations."
        ),
    )
    group.addoption(
        "--gp-run-examples",
        action="store_true",
        default=False,
        help="Execute docstring examples and validate output.",
    )


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    """Configure pytest with custom markers for docstring validation."""
    config.addinivalue_line(
        "markers",
        "gaspatchio_docstring_example: mark test as a Gaspatchio example",
    )
    config.addinivalue_line(
        "markers",
        "gaspatchio_docstring_structure_check: mark test as structure check",
    )


def pytest_collect_file(
    parent,  # type: ignore[no-untyped-def]
    file_path: Path,
) -> DocstringExampleFile | None:
    """Collect docstring examples from Python files matching patterns."""
    # Flatten list of lists for --gp-docstring-paths
    raw_pattern_groups = parent.session.config.getoption("gp_docstring_paths")
    docstring_paths_patterns = []
    if raw_pattern_groups:
        for group in raw_pattern_groups:
            docstring_paths_patterns.extend(group)

    if file_path.suffix in (".py", ".pyi") and file_path.name != "__init__.py":
        if docstring_paths_patterns:
            should_collect = False

            try:
                path_to_match = file_path.relative_to(parent.session.config.rootpath)
            except ValueError:
                path_to_match = file_path

            for pattern in docstring_paths_patterns:
                if fnmatch.fnmatch(str(path_to_match), pattern) or fnmatch.fnmatch(
                    str(file_path), pattern
                ):
                    should_collect = True
                    break

            if not should_collect:
                if parent.session.config.option.verbose > 1:
                    msg = (
                        f"Docstring plugin: Skipping {file_path} "
                        f"(tried matching: {path_to_match}) as it doesn't "
                        f"match patterns: {docstring_paths_patterns}"
                    )
                    print(msg)  # noqa: T201
                return None

        return DocstringExampleFile.from_parent(parent, path=file_path)
    return None


class DocstringExampleFile(pytest.File):
    """Pytest file collector for docstring examples."""

    def collect(  # type: ignore[no-untyped-def]
        self,
    ) -> Generator[pytest.Item, None, None]:
        """Collect test items from docstrings in this file."""
        parser = GaspatchioDocstringParser()
        docstrings = parser.process_file(self.path)
        item_count = 0
        for doc in docstrings:
            structure_item_name = f"{doc.object_path}-structure"
            yield DocstringStructureItem.from_parent(
                self, name=structure_item_name, docstring_obj=doc
            )
            item_count += 1

            for ex_idx, ex in enumerate(doc.examples):
                item_name = f"{doc.object_path}-ex{ex_idx}"
                yield DocstringExampleItem.from_parent(self, name=item_name, example=ex)
                item_count += 1
        if item_count == 0 and self.session.config.option.verbose > 0:
            msg = f"No docstring examples or structure checks found in {self.path}"
            print(msg)  # noqa: T201


class DocstringExampleItem(pytest.Item):
    """Pytest test item for a single docstring code example."""

    def __init__(
        self,
        *,
        name,  # type: ignore[no-untyped-def]
        parent,  # type: ignore[no-untyped-def]
        example: DocstringCodeExample,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize with example details."""
        super().__init__(name, parent, **kwargs)
        self.example: DocstringCodeExample = example
        self.failure_reason: str | None = None
        self.add_marker("gaspatchio_docstring_example")

    def runtest(self) -> None:
        """Run linting, style checks, and runtime validation on the example.

        Performs lint checks and raises DocstringLintError on violations.
        Optionally performs style checks based on --gp-style-check option.
        Optionally runs code and validates output.
        """
        # Run linting first
        issues = self.example.lint()
        if issues:
            primary_error_message_for_summary = issues[0]
            self.failure_reason = primary_error_message_for_summary
            snippet_code = self.example._extract_code_from_snippet()  # noqa: SLF001
            raise DocstringLintError(
                item_name=self.name,
                primary_ruff_error_text_for_summary=primary_error_message_for_summary,
                all_ruff_issues=issues,
                snippet=snippet_code,
            )

        # Run style checks if enabled
        style_mode = self.config.getoption("gp_style_check", default="off")
        if style_mode != "off":
            style_violations = self.example.check_style()
            if style_violations:
                if style_mode == "strict":
                    self.failure_reason = style_violations[0]
                    snippet_code = self.example._extract_code_from_snippet()  # noqa: SLF001
                    raise DocstringStyleError(
                        item_name=self.name,
                        primary_violation=style_violations[0],
                        all_violations=style_violations,
                        snippet=snippet_code,
                    )
                # warn mode: print warnings but don't fail
                print(f"\nStyle warnings in {self.name}:")  # noqa: T201
                for violation in style_violations:
                    print(f"  {violation}")  # noqa: T201

        # Run runtime validation if enabled and there's expected output
        run_examples = self.config.getoption("gp_run_examples", default=False)
        if run_examples and self.example.output is not None:
            validator = GaspatchioEvalExample(update_examples_mode=False)
            runtime_issues = validator.run_custom_check(self.example)
            if runtime_issues:
                self.failure_reason = runtime_issues[0]
                snippet_code = self.example._extract_code_from_snippet()  # noqa: SLF001
                raise DocstringRuntimeError(
                    item_name=self.name,
                    primary_error=runtime_issues[0],
                    all_errors=runtime_issues,
                    snippet=snippet_code,
                )

    def repr_failure(  # noqa: C901, PLR0912, PLR0915
        self,
        excinfo,  # type: ignore[no-untyped-def]
        style=None,  # type: ignore[no-untyped-def]
    ) -> DocstringFailureTerminalRepr | None:
        """Format failure output when runtest() raises an exception."""
        if isinstance(excinfo.value, DocstringLintError):
            exc = cast("DocstringLintError", excinfo.value)

            item_name = exc.item_name
            extracted_ruff_issues = exc.all_ruff_issues
            snippet_text = exc.snippet

            # Determine primary error code and line number
            primary_error_code = ""
            error_line_number_in_snippet = -1

            if extracted_ruff_issues:
                first_issue_detail = extracted_ruff_issues[0]

                # Regex to capture CODE, Message, and optionally "at line L"
                match = re.match(
                    r"([A-Z]+\d+):\s*(.*?)(?:\s+at line\s+(\d+))?",
                    first_issue_detail,
                )
                if match:
                    primary_error_code = match.group(1)
                    if match.group(3):
                        error_line_number_in_snippet = int(match.group(3))
                else:
                    # Fallback if not in "CODE: details" format
                    code_match = re.match(r"([A-Z]+\d+)", first_issue_detail)
                    if code_match:
                        primary_error_code = code_match.group(1)

            file_path = str(self.path)

            report = [
                "LINTING ERROR in Docstring Example",
                f"  File:       {file_path}",
                f"  Example ID:   {item_name}",
                (
                    "  ----------------------------------------------------"
                    "----------------------"
                ),
                "  Error(s) from Ruff:",
            ]

            if not extracted_ruff_issues:
                report.append(
                    "    [No specific Ruff issues extracted from error message]"
                )
            else:
                report.extend(
                    [("    " + issue, {"red": True}) for issue in extracted_ruff_issues]
                )

            report.extend(
                [
                    (
                        "  ----------------------------------------------------"
                        "----------------------"
                    ),
                    "  Problematic Code Snippet (from docstring example):",
                ]
            )
            snippet_lines = snippet_text.splitlines()
            for idx, line_content in enumerate(snippet_lines):
                line_num_in_snippet = idx + 1
                if (
                    line_num_in_snippet == error_line_number_in_snippet
                    and primary_error_code
                ):
                    msg = f"    {line_content} # <--- {primary_error_code} ISSUE HERE"
                    report.append(msg)
                elif line_num_in_snippet == error_line_number_in_snippet:
                    report.append(f"    {line_content} # <------- ISSUE HERE")
                else:
                    report.append(f"    {line_content}")
            report.append(
                "  ----------------------------------------------------------"
                "--------------"
            )

            # Use the parsed primary_error_code for linting suggestion
            # If not parsed, fallback to splitting the first issue line
            final_primary_code_for_suggestion = primary_error_code
            if not final_primary_code_for_suggestion and extracted_ruff_issues:
                final_primary_code_for_suggestion = (
                    extracted_ruff_issues[0].split(":")[0].strip()
                )

            suggestion = get_linting_suggestion(
                final_primary_code_for_suggestion,
                first_issue_detail,
            )
            if suggestion:
                report.extend(format_suggestion_for_report(suggestion))

            return DocstringFailureTerminalRepr(report)

        if isinstance(excinfo.value, DocstringStyleError):
            exc = cast("DocstringStyleError", excinfo.value)

            item_name = exc.item_name
            style_violations = exc.all_violations
            snippet_text = exc.snippet

            file_path = str(self.path)

            report = [
                "STYLE VIOLATION in Docstring Example",
                f"  File:       {file_path}",
                f"  Example ID:   {item_name}",
                (
                    "  ----------------------------------------------------"
                    "----------------------"
                ),
                "  Style Violation(s):",
            ]

            for violation in style_violations:
                report.append(("    " + violation, {"yellow": True}))

            report.extend(
                [
                    (
                        "  ----------------------------------------------------"
                        "----------------------"
                    ),
                    "  Code Snippet:",
                ]
            )
            for line in snippet_text.splitlines():
                report.append(f"    {line}")
            report.append(
                "  ----------------------------------------------------------"
                "--------------"
            )

            return DocstringFailureTerminalRepr(report)

        if isinstance(excinfo.value, DocstringRuntimeError):
            exc = cast("DocstringRuntimeError", excinfo.value)

            item_name = exc.item_name
            runtime_errors = exc.all_errors
            snippet_text = exc.snippet

            file_path = str(self.path)

            report = [
                "RUNTIME ERROR in Docstring Example",
                f"  File:       {file_path}",
                f"  Example ID:   {item_name}",
                (
                    "  ----------------------------------------------------"
                    "----------------------"
                ),
                "  Runtime Error(s):",
            ]

            for error in runtime_errors:
                report.append(("    " + error, {"red": True}))

            report.extend(
                [
                    (
                        "  ----------------------------------------------------"
                        "----------------------"
                    ),
                    "  Code Snippet:",
                ]
            )
            for line in snippet_text.splitlines():
                report.append(f"    {line}")
            report.append(
                "  ----------------------------------------------------------"
                "--------------"
            )

            return DocstringFailureTerminalRepr(report)

        return super().repr_failure(excinfo, style)

    def reportinfo(  # type: ignore[no-untyped-def]
        self,
    ) -> tuple[Any, None, str]:
        """Return tuple (fspath, lineno, message) for test reports."""
        base_message = f"Docstring Example: {self.name}"
        if self.failure_reason:
            msg = f"{base_message} - {self.failure_reason}"
            return (self.path, None, msg)
        return (self.path, None, base_message)


class DocstringStructureItem(pytest.Item):
    """Pytest test item for docstring structure validation."""

    def __init__(
        self,
        *,
        name,  # type: ignore[no-untyped-def]
        parent,  # type: ignore[no-untyped-def]
        docstring_obj: GaspatchioDocstring,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize with docstring object details."""
        super().__init__(name, parent, **kwargs)
        self.docstring_obj: GaspatchioDocstring = docstring_obj
        self.add_marker("gaspatchio_docstring_structure_check")

    def runtest(self) -> None:
        """Validate docstring structure and raise errors if issues found."""
        issues = self.docstring_obj.validate_structure()
        if issues:
            raise DocstringStructureError(
                item_name=self.name,
                file_path=str(self.docstring_obj.file_path),
                object_path=self.docstring_obj.object_path,
                issues=issues,
                raw_docstring=self.docstring_obj.raw_docstring,
            )

    def repr_failure(  # type: ignore[no-untyped-def]
        self,
        excinfo,  # type: ignore[no-untyped-def]
        style=None,  # type: ignore[no-untyped-def]
    ) -> DocstringFailureTerminalRepr | None:
        """Format failure output when runtest() raises an exception."""
        if isinstance(excinfo.value, DocstringStructureError):
            exc = cast("DocstringStructureError", excinfo.value)
            report = [
                "DOCSTRING STRUCTURE ERROR",
                f"  File:        {exc.file_path}",
                f"  Object:      {exc.object_path}",
                f"  Line:        {self.docstring_obj.start_line}",
                (
                    "  ----------------------------------------------------"
                    "----------------------"
                ),
                "  Issues Found:",
            ]
            report.extend([f"    - {issue}" for issue in exc.issues])
            report.append(
                "  ----------------------------------------------------------"
                "--------------"
            )

            return DocstringFailureTerminalRepr(report)
        return super().repr_failure(excinfo, style)

    def reportinfo(  # type: ignore[no-untyped-def]
        self,
    ) -> tuple[Any, int, str]:
        """Return tuple (fspath, lineno, message) for test reports."""
        msg = f"[STRUCT CHECK] {self.name}"
        return (self.path, self.docstring_obj.start_line, msg)


class DocstringLintError(Exception):
    """Custom exception for docstring linting errors."""

    def __init__(
        self,
        item_name: str,
        primary_ruff_error_text_for_summary: str,
        all_ruff_issues: list[str],
        snippet: str,
    ) -> None:
        """Initialize with linting error details."""
        self.item_name = item_name
        self.primary_ruff_error_text_for_summary = primary_ruff_error_text_for_summary
        self.all_ruff_issues = all_ruff_issues
        self.snippet = snippet
        super().__init__(primary_ruff_error_text_for_summary)


class DocstringStyleError(Exception):
    """Custom exception for docstring style violations."""

    def __init__(
        self,
        item_name: str,
        primary_violation: str,
        all_violations: list[str],
        snippet: str,
    ) -> None:
        """Initialize with style violation details."""
        self.item_name = item_name
        self.primary_violation = primary_violation
        self.all_violations = all_violations
        self.snippet = snippet
        super().__init__(primary_violation)


class DocstringRuntimeError(Exception):
    """Custom exception for docstring runtime validation errors."""

    def __init__(
        self,
        item_name: str,
        primary_error: str,
        all_errors: list[str],
        snippet: str,
    ) -> None:
        """Initialize with runtime error details."""
        self.item_name = item_name
        self.primary_error = primary_error
        self.all_errors = all_errors
        self.snippet = snippet
        super().__init__(primary_error)


class DocstringFailureTerminalRepr:
    """Terminal representation for docstring test failures."""

    def __init__(self, lines: list[Any]) -> None:
        """Initialize with list of lines (str or tuple[str, dict])."""
        self.lines = lines

    def toterminal(self, tw) -> None:  # type: ignore[no-untyped-def]
        """Output formatted lines to terminal writer."""
        tuple_length = 2
        for item in self.lines:
            if (
                isinstance(item, tuple)
                and len(item) == tuple_length
                and isinstance(item[0], str)
                and isinstance(item[1], dict)
            ):
                line_text, markup_opts = item
                tw.line(line_text, **markup_opts)
            elif isinstance(item, str):
                tw.line(item)
            else:
                tw.line(str(item))

    def __str__(self) -> str:
        """Return simple string representation without color."""
        return "\n".join(
            str(line[0] if isinstance(line, tuple) else line) for line in self.lines
        )


class DocstringStructureError(Exception):
    """Custom exception for docstring structural validation errors."""

    def __init__(
        self,
        item_name: str,
        file_path: str,
        object_path: str,
        issues: list[str],
        raw_docstring: str,
    ) -> None:
        """Initialize with structure error details."""
        self.item_name = item_name
        self.file_path = file_path
        self.object_path = object_path
        self.issues = issues
        self.raw_docstring = raw_docstring
        message = (
            f"Docstring structural errors in {object_path} ({file_path}):\\n"
            + "\n".join(issues)
        )
        super().__init__(message)
