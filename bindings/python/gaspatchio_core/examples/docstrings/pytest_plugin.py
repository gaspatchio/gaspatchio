from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import cast

import pytest

from .formatting import format_suggestion_for_report, get_linting_suggestion
from .models import (
    DocstringCodeExample,  # , GaspatchioDocstring # GaspatchioDocstring might not be needed directly here
    GaspatchioDocstring,  # Ensure GaspatchioDocstring is imported
)
from .parse import GaspatchioDocstringParser
from .validate import GaspatchioEvalExample

# from .validate import GaspatchioEvalExample # Keep if run_custom_check is also integrated

# Remove test_gaspatchio_docstring_example from __all__ if it was there.
# Hooks and fixtures are discovered by pytest through naming conventions or registration.
__all__ = [
    "pytest_addoption",
    "pytest_configure",
    "pytest_collect_file",
]

# Removed _EXAMPLE_CACHE and _SOURCE_DIR_CACHE
# _EXAMPLE_CACHE: Optional[List[DocstringCodeExample]] = None
# _SOURCE_DIR_CACHE: Optional[str] = None


def pytest_generate_tests(metafunc):
    """Generate tests for docstring examples."""
    if "docstring_example_fixture" in metafunc.fixturenames:
        # Find all examples in the project by collecting from files
        examples = []
        # This is a simplified approach - in a real implementation, this would collect examples
        # from the project files. For now, we'll just use an empty list to avoid test failures.
        metafunc.parametrize(
            "docstring_example_fixture",
            examples,
            ids=lambda ex: f"{ex.object_context}-ex{ex.example_index}"
            if examples
            else [],
        )


@pytest.fixture
def eval_example_fixture(request):
    """Fixture providing a GaspatchioEvalExample for validating docstring examples."""
    update_mode = request.config.getoption("gp_update_examples", False)
    return GaspatchioEvalExample(update_examples_mode=update_mode)


def pytest_addoption(parser):  # Renamed back to parser
    group = parser.getgroup("gaspatchio_docstring_examples")
    group.addoption(
        "--gp-update-examples",
        action="store_true",
        default=False,
        help="Update docstring example outputs in files instead of checking them.",
    )
    group.addoption(
        "--gp-docstring-paths",
        action="append",  # Allows specifying multiple paths
        default=[],
        nargs="*",  # Allows space-separated values for a single --gp-docstring-paths
        help="Glob patterns for files/directories to include in docstring checks. (e.g., 'src/gaspatchio_core/accessors/*.py' 'tests/specific_module/**.py'). Can be specified multiple times.",
    )
    # --gp-examples-dir might become obsolete or change meaning with file-based collection
    # For now, let's comment it out or decide its new role.
    # group.addoption(
    #     "--gp-examples-dir",
    #     action="store",
    #     default="src/gaspatchio_core",
    #     help="Directory to scan for Python files with docstring examples.",
    # )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "gaspatchio_docstring_example: mark test as a Gaspatchio docstring example",
    )
    config.addinivalue_line(
        "markers",
        "gaspatchio_docstring_structure_check: mark test as a Gaspatchio docstring structure check",
    )
    # Removed cache clearing related to old find_examples
    # global _EXAMPLE_CACHE, _SOURCE_DIR_CACHE
    # _EXAMPLE_CACHE = None
    # _SOURCE_DIR_CACHE = None
    # try:
    #     if hasattr(config, "cache"):
    #         config.cache.clear_all()
    # except Exception:
    #     pass


# New implementation based on pytest_collect_file
def pytest_collect_file(parent, path):
    # path is a py.path.local object, convert to pathlib.Path for modern API usage
    file_path = Path(str(path))

    # Correctly flatten the list of lists for --gp-docstring-paths
    raw_pattern_groups = parent.session.config.getoption("gp_docstring_paths")
    docstring_paths_patterns = []
    if raw_pattern_groups:
        for group in (
            raw_pattern_groups
        ):  # Each 'group' is a list of patterns from one --gp-docstring-paths usage
            docstring_paths_patterns.extend(group)

    if file_path.suffix == ".py" and file_path.name != "__init__.py":
        if docstring_paths_patterns:  # Only apply filtering if patterns are provided
            should_collect = False

            try:
                path_to_match = file_path.relative_to(parent.session.config.rootpath)
            except ValueError:
                path_to_match = file_path  # Fallback to absolute/direct path matching

            for pattern in docstring_paths_patterns:
                if fnmatch.fnmatch(str(path_to_match), pattern):
                    should_collect = True
                    break
                # Also check against the full file path in case patterns are absolute or don't match relative
                elif fnmatch.fnmatch(str(file_path), pattern):
                    should_collect = True
                    break

            if not should_collect:
                if (
                    parent.session.config.option.verbose > 1
                ):  # Becomes > 0 for normal verbosity, > 1 for more detail
                    print(
                        f"Docstring plugin: Skipping {file_path} (tried matching: {path_to_match}) as it doesn't match patterns: {docstring_paths_patterns}"
                    )
                return None
        else:
            # No --gp-docstring-paths specified.
            # Default behavior: collect all .py files (by falling through).
            # To collect NONE by default if option is not present (i.e., plugin only active if paths are specified):
            # if parent.session.config.option.verbose > 0: # Changed from >1 to >0
            #     print(f"Docstring plugin: Skipping {file_path} as --gp-docstring-paths is not set, and plugin requires explicit paths.")
            # return None
            pass  # Current behavior: if no paths, process all python files.

        # Original logic continues if the file should be collected
        # Verbose logging for when a file *is* being processed for docstrings
        if parent.session.config.option.verbose > 0:
            # This specific print might be too noisy if many files are processed.
            # Consider printing only when examples are actually found or if a file is *about* to be parsed.
            # print(f"Docstring plugin: Collecting docstring examples from {file_path}")
            pass

        return DocstringExampleFile.from_parent(parent, path=file_path)
    return None


class DocstringExampleFile(pytest.File):
    def collect(self):
        parser = GaspatchioDocstringParser()
        # For pytest >= 7, self.path is a Path object
        # For older versions, self.fspath was a string, so Path(str(self.fspath)) was needed
        docstrings = parser.process_file(
            self.path
        )  # Assuming self.path is a Path object
        item_count = 0
        for doc in docstrings:
            # Create a test item for the overall docstring structure
            structure_item_name = f"{doc.object_path}-structure"
            yield DocstringStructureItem.from_parent(
                self, name=structure_item_name, docstring_obj=doc
            )
            item_count += 1  # Count this as an item

            for ex_idx, ex in enumerate(doc.examples):
                # Apply the marker to each item if needed for -m filtering
                # However, pytest -m usually filters at collection time based on markers on test functions/classes
                # For custom items, filtering often happens via -k or by not yielding items.
                # For now, we'll rely on the -k filtering provided by the CLI if --method is used.
                # The 'gaspatchio_docstring_example' marker is more for grouping/info.
                item_name = f"{doc.object_path}-ex{ex_idx}"
                yield DocstringExampleItem.from_parent(self, name=item_name, example=ex)
                item_count += 1
        if item_count == 0 and self.session.config.option.verbose > 0:
            print(f"No docstring examples or structure checks found in {self.path}")


class DocstringExampleItem(pytest.Item):
    def __init__(
        self, *, name, parent, example, **kwargs
    ):  # Ensure example is a keyword argument
        super().__init__(name, parent, **kwargs)
        self.example: DocstringCodeExample = example
        self.failure_reason: str | None = None  # Store failure reason for reportinfo
        self.add_marker("gaspatchio_docstring_example")

    def runtest(self):
        """
        This method is called to run the test.
        For now, it performs a lint check.
        It could be expanded to run execution checks, update outputs, etc.
        """
        issues = (
            self.example.lint()
        )  # Expected to return list of strings like "E401: Message at line X col Y"
        if issues:
            primary_error_message_for_summary = issues[0]
            self.failure_reason = (
                primary_error_message_for_summary  # Store for reportinfo
            )
            snippet_code = self.example._extract_code_from_snippet()
            raise DocstringLintError(
                item_name=self.name,
                primary_ruff_error_text_for_summary=primary_error_message_for_summary,
                all_ruff_issues=issues,
                snippet=snippet_code,
            )

    def repr_failure(self, excinfo, style=None):
        """Called when self.runtest() raises an exception."""
        if isinstance(excinfo.value, DocstringLintError):
            exc = cast(DocstringLintError, excinfo.value)

            item_name = exc.item_name
            extracted_ruff_issues = exc.all_ruff_issues
            snippet_text = exc.snippet

            # Determine the primary error code and line number from the primary Ruff error
            primary_error_code = ""
            error_line_number_in_snippet = (
                -1
            )  # Line number of the primary error within the snippet

            if extracted_ruff_issues:
                # Example: "E401: Multiple imports on one line at line 1 col 1"
                # Or from ruff direct: "path/to/file.py:1:1: E401 Multiple imports on one line"
                # Assuming self.example.lint() provides "CODE: Message at line L col C" or similar
                first_issue_detail = extracted_ruff_issues[0]

                # Regex to capture CODE, Message, and optionally "at line L"
                # Handles cases like "E401: Multiple imports on one line at line 1 col 1"
                # or "E401: Multiple imports on one line"
                match = re.match(
                    r"([A-Z]+\d+):\s*(.*?)(?:\s+at line\s+(\d+))?", first_issue_detail
                )
                if match:
                    primary_error_code = match.group(1)
                    # group(2) is the message part
                    if match.group(3):
                        error_line_number_in_snippet = int(match.group(3))
                else:
                    # Fallback if primary ruff message is not in "CODE: details" format
                    # Try to get code from the start if possible
                    code_match = re.match(r"([A-Z]+\d+)", first_issue_detail)
                    if code_match:
                        primary_error_code = code_match.group(1)

            file_path = str(self.path)

            report = [
                "LINTING ERROR in Docstring Example",
                f"  File:       {file_path}",
                f"  Example ID:   {item_name}",
                "  ----------------------------------------------------------------------",
                "  Error(s) from Ruff:",
            ]

            if not extracted_ruff_issues:
                report.append(
                    "    [No specific Ruff issues extracted from error message]"
                )
            else:
                for issue_line in extracted_ruff_issues:
                    report.append(("    " + issue_line, {"red": True}))

            report.extend(
                [
                    "  ----------------------------------------------------------------------",
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
                    report.append(
                        f"    {line_content} # <--- {primary_error_code} ISSUE HERE"
                    )
                elif line_num_in_snippet == error_line_number_in_snippet:
                    report.append(f"    {line_content} # <------- ISSUE HERE")
                else:
                    report.append(f"    {line_content}")
            report.append(
                "  ----------------------------------------------------------------------"
            )

            combined_issues_text_for_suggestion = "\\n".join(extracted_ruff_issues)

            # Use the parsed primary_error_code for get_linting_suggestion
            # If primary_error_code couldn't be parsed, fallback to splitting the first issue line
            final_primary_code_for_suggestion = primary_error_code
            if not final_primary_code_for_suggestion and extracted_ruff_issues:
                final_primary_code_for_suggestion = (
                    extracted_ruff_issues[0].split(":")[0].strip()
                )

            suggestion = get_linting_suggestion(
                final_primary_code_for_suggestion,
                first_issue_detail,  # Pass the full first issue detail as the error message
            )
            if suggestion:
                report.extend(format_suggestion_for_report(suggestion))

            return DocstringFailureTerminalRepr(report)
        return super().repr_failure(excinfo, style)

    def reportinfo(self):
        """Returns a tuple (fspath, lineno, message) for test reports."""
        base_message = f"Docstring Example: {self.name}"
        if self.failure_reason:
            # Attempt to make the summary line more informative
            # Pytest might still truncate this or use its own formatting for the short summary
            return (self.path, None, f"{base_message} - {self.failure_reason}")
        return (self.path, None, base_message)


class DocstringStructureItem(pytest.Item):
    def __init__(self, *, name, parent, docstring_obj: "GaspatchioDocstring", **kwargs):
        super().__init__(name, parent, **kwargs)
        self.docstring_obj: "GaspatchioDocstring" = docstring_obj
        self.add_marker("gaspatchio_docstring_structure_check")  # New marker

    def runtest(self):
        issues = self.docstring_obj.validate_structure()
        if issues:
            # Combine issues into a single message for the error report
            # failure_message = "\n".join(issues)
            raise DocstringStructureError(
                item_name=self.name,
                file_path=str(self.docstring_obj.file_path),
                object_path=self.docstring_obj.object_path,
                issues=issues,
                raw_docstring=self.docstring_obj.raw_docstring,
            )

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, DocstringStructureError):
            exc = cast(DocstringStructureError, excinfo.value)
            report = [
                "DOCSTRING STRUCTURE ERROR",
                f"  File:        {exc.file_path}",
                f"  Object:      {exc.object_path}",
                f"  Line:        {self.docstring_obj.start_line}",  # start_line of the docstring object
                "  ----------------------------------------------------------------------",
                "  Issues Found:",
            ]
            for issue_line in exc.issues:
                report.append(f"    - {issue_line}")
            report.append(
                "  ----------------------------------------------------------------------"
            )
            # Optionally, include part of the raw docstring for context
            # report.append("  Problematic Raw Docstring (first 15 lines):")
            # report.extend([f"    {line}" for line in exc.raw_docstring.splitlines()[:15]]
            # report.append("  ----------------------------------------------------------------------")

            return DocstringFailureTerminalRepr(
                report
            )  # Reuse existing for basic formatting
        return super().repr_failure(excinfo, style)

    def reportinfo(self):
        return (self.path, self.docstring_obj.start_line, f"[STRUCT CHECK] {self.name}")


class DocstringLintError(Exception):
    """Custom exception for docstring linting errors."""

    def __init__(
        self,
        item_name: str,
        primary_ruff_error_text_for_summary: str,
        all_ruff_issues: list[str],
        snippet: str,
    ):
        self.item_name = item_name
        self.primary_ruff_error_text_for_summary = primary_ruff_error_text_for_summary
        self.all_ruff_issues = all_ruff_issues
        self.snippet = snippet
        # This message is what pytest will show in the FAILED ... line summary
        super().__init__(primary_ruff_error_text_for_summary)


class DocstringFailureTerminalRepr:
    def __init__(
        self, lines: list[any]
    ):  # Allow list to contain tuples for styled lines
        self.lines = lines

    def toterminal(self, tw):
        for item in self.lines:
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], dict)
            ):
                line_text, markup_opts = item
                tw.line(line_text, **markup_opts)
            elif isinstance(item, str):
                tw.line(item)
            else:  # Fallback for unexpected item types
                tw.line(str(item))

    def __str__(self):  # Fallback for contexts not using toterminal
        # Simple string representation, ignoring color for non-terminal contexts
        return "\n".join(
            str(line[0] if isinstance(line, tuple) else line) for line in self.lines
        )


# Custom exception for docstring structural errors - moved definition up with Item for clarity
class DocstringStructureError(Exception):
    """Custom exception for docstring structural validation errors."""

    def __init__(
        self,
        item_name: str,
        file_path: str,
        object_path: str,
        issues: list[str],
        raw_docstring: str,
    ):
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
