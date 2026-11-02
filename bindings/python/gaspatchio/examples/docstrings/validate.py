# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Run docstring code examples and check them against their expected output."""

import textwrap
from typing import Any

from .models import DocstringCodeExample


class GaspatchioEvalExample:
    """Run a docstring code example and compare it with its expected output."""

    def __init__(self, update_examples_mode: bool = False) -> None:
        """Create a checker; in update mode, stray stdout is not reported."""
        self.update_examples_mode = update_examples_mode

    def run_custom_check(
        self,
        example: DocstringCodeExample,
        global_vars: dict[str, Any] | None = None,
    ) -> list[str]:
        """Run custom check on the example and return a list of error messages."""
        if not hasattr(example, "run"):
            return [
                (
                    "[Custom Check Error] DocstringCodeExample missing 'run' method "
                    f"for {example.object_context} ex#{example.example_index} "
                    f"(file: {example.raw_source_location[0]}, "
                    f"line: {example.raw_source_location[1]})."
                )
            ]

        # example.snippet is already clean code
        captured_stdout, last_expr_value, exc = example.run(global_vars=global_vars)

        if exc is not None:
            return [
                (
                    f"[Custom Check Error] Runtime error for {example.object_context} "
                    f"ex#{example.example_index} "
                    f"(file: {example.raw_source_location[0]}, "
                    f"line: {example.raw_source_location[1]}): "
                    f"{type(exc).__name__}: {exc}. Snippet:\n{example.snippet}"
                )
            ]

        issues: list[str] = []

        if example.output is not None:
            expected_output_str = textwrap.dedent(example.output).rstrip("\n")
            actual_output_parts = []
            if captured_stdout.strip():  # Only add if there's actual stdout content
                actual_output_parts.append(captured_stdout.rstrip("\n"))

            actual_combined_output_str = ""
            if last_expr_value is not None:
                # If expected_output_str looks like a repr (e.g., string with
                # quotes, or list/dict repr) then compare with
                # repr(last_expr_value). Otherwise, compare with
                # str(last_expr_value). This is a heuristic. Doctest has more
                # involved logic. Simple heuristic: if expected is quoted like a
                # string, or starts with [ { (, assume repr was intended.
                if (
                    (
                        expected_output_str.startswith("'")
                        and expected_output_str.endswith("'")
                    )
                    or (
                        expected_output_str.startswith('"')
                        and expected_output_str.endswith('"')
                    )
                    or expected_output_str.startswith(("[", "{", "("))
                ):
                    actual_value_str = repr(last_expr_value)
                else:
                    actual_value_str = str(last_expr_value)
                actual_output_parts.append(actual_value_str)

            # Join stdout (if any) and value string (if any). Use strip() to
            # handle cases where only one is present and to match rstrip('\n')
            # on expected
            actual_combined_output_str = "\n".join(actual_output_parts).strip()

            if actual_combined_output_str != expected_output_str:
                issues.append(
                    "[Custom Check Error] Output mismatch for "
                    f"{example.object_context} ex#{example.example_index} (file: "
                    f"{example.raw_source_location[0]}, line: "
                    f"{example.raw_source_location[1]}):\n"
                    f"EXPECTED:\n{expected_output_str}\n"
                    f"ACTUAL:\n{actual_combined_output_str}\n"
                    f"SNIPPET (code run):\n{example.snippet}"
                )
        # If example.output is None (not specified in docstring):
        else:
            # This case was discussed in Prompt 3.2. With no output in the
            # docstring, this check mainly verifies no unexpected stdout and no
            # errors; a last_expr_value that is not None implies an error,
            # because the docstring is *missing* an output.
            if last_expr_value is not None:
                issues.append(
                    "[Custom Check Error] Missing output in docstring for "
                    f"{example.object_context} ex#{example.example_index} (file: "
                    f"{example.raw_source_location[0]}, line: "
                    f"{example.raw_source_location[1]}). "
                    f"Expression yielded: {repr(last_expr_value)[:100]}. Snippet:\n"
                    f"{example.snippet}"
                )
            # If there was stdout but no output was expected (example.output is
            # None). This could be an issue depending on strictness. For now,
            # let's flag it if not updating.
            if captured_stdout and not self.update_examples_mode:
                issues.append(
                    "[Custom Check Error] Unexpected stdout for "
                    f"{example.object_context} ex#{example.example_index} (file: "
                    f"{example.raw_source_location[0]}, line: "
                    f"{example.raw_source_location[1]}) "
                    f"(no output was defined in docstring):\n{captured_stdout[:200]}\n"
                    f"SNIPPET:\n{example.snippet}"
                )
        return issues

    def check_example(
        self,
        example: DocstringCodeExample,
        global_vars: dict[str, Any] | None = None,
    ) -> list[str]:
        """Orchestrates checks for an example. Now only runs custom_check."""
        errors: list[str] = []

        # Previously, there was a call to run_doctest_check here.
        # With DocstringCodeExample.snippet being clean, multi-line code,
        # run_custom_check is the more direct validation.
        # run_doctest_check was causing issues with doctest's assumptions
        # about "single" statements when given a pre-formatted block.

        custom_errors = self.run_custom_check(example, global_vars=global_vars)
        if custom_errors:
            errors.extend(custom_errors)

        return errors
