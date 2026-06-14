# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import textwrap
from typing import Any, Dict, List, Optional

from .models import DocstringCodeExample

# from .rewrite import _format_output_block, _rewrite_raw_docstring, _apply_new_docstring_to_file_ast
# Will import these specifically in the method that uses them to avoid circular dependency if rewrite imports from validate.


class GaspatchioEvalExample:
    def __init__(self, update_examples_mode: bool = False):
        self.update_examples_mode = update_examples_mode

    def run_custom_check(
        self,
        example: DocstringCodeExample,
        global_vars: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Runs custom check on the example and returns a list of error messages."""
        if not hasattr(example, "run"):
            return [
                f"[Custom Check Error] DocstringCodeExample missing 'run' method for {example.object_context} ex#{example.example_index} (file: {example.raw_source_location[0]}, line: {example.raw_source_location[1]})."
            ]

        # example.snippet is already clean code
        captured_stdout, last_expr_value, exc = example.run(global_vars=global_vars)

        if exc is not None:
            return [
                f"[Custom Check Error] Runtime error for {example.object_context} ex#{example.example_index} (file: {example.raw_source_location[0]}, line: {example.raw_source_location[1]}): {type(exc).__name__}: {exc}. Snippet:\n{example.snippet}"
            ]

        issues: List[str] = []

        if example.output is not None:
            expected_output_str = textwrap.dedent(example.output).rstrip("\n")
            actual_output_parts = []
            if captured_stdout.strip():  # Only add if there's actual stdout content
                actual_output_parts.append(captured_stdout.rstrip("\n"))

            actual_combined_output_str = ""
            if last_expr_value is not None:
                # If expected_output_str looks like a repr (e.g., string with quotes, or list/dict repr)
                # then compare with repr(last_expr_value). Otherwise, compare with str(last_expr_value).
                # This is a heuristic. Doctest has more involved logic.
                # Simple heuristic: if expected is quoted like a string, or starts with [ { (, assume repr was intended.
                if (
                    (
                        expected_output_str.startswith("'")
                        and expected_output_str.endswith("'")
                    )
                    or (
                        expected_output_str.startswith('"')
                        and expected_output_str.endswith('"')
                    )
                    or expected_output_str.startswith("[")
                    or expected_output_str.startswith("{")
                    or expected_output_str.startswith("(")
                ):
                    actual_value_str = repr(last_expr_value)
                else:
                    actual_value_str = str(last_expr_value)
                actual_output_parts.append(actual_value_str)

            # Join stdout (if any) and value string (if any)
            actual_combined_output_str = "\n".join(
                actual_output_parts
            ).strip()  # Use strip() to handle cases where only one is present and to match rstrip('\n') on expected

            if actual_combined_output_str != expected_output_str:
                issues.append(
                    f"[Custom Check Error] Output mismatch for {example.object_context} ex#{example.example_index} (file: {example.raw_source_location[0]}, line: {example.raw_source_location[1]}):\n"
                    f"EXPECTED:\n{expected_output_str}\n"
                    f"ACTUAL:\n{actual_combined_output_str}\n"
                    f"SNIPPET (code run):\n{example.snippet}"
                )
        # If example.output is None (not specified in docstring):
        else:
            # This case was discussed in Prompt 3.2.
            # "if example.output is None: this check mainly verifies no unexpected stdout and no errors."
            # "if last_expr_value is not None, this implies an error because the docstring is *missing* an output"
            if last_expr_value is not None:
                issues.append(
                    f"[Custom Check Error] Missing output in docstring for {example.object_context} ex#{example.example_index} (file: {example.raw_source_location[0]}, line: {example.raw_source_location[1]}). "
                    f"Expression yielded: {repr(last_expr_value)[:100]}. Snippet:\n{example.snippet}"
                )
            # If there was stdout but no output was expected (example.output is None)
            # This could be an issue depending on strictness. For now, let's flag it if not updating.
            if captured_stdout and not self.update_examples_mode:
                issues.append(
                    f"[Custom Check Error] Unexpected stdout for {example.object_context} ex#{example.example_index} (file: {example.raw_source_location[0]}, line: {example.raw_source_location[1]}) "
                    f"(no output was defined in docstring):\n{captured_stdout[:200]}\n"
                    f"SNIPPET:\n{example.snippet}"
                )
        return issues

    def check_example(
        self,
        example: DocstringCodeExample,
        global_vars: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Orchestrates checks for an example. Now only runs custom_check."""
        errors: List[str] = []

        # Previously, there was a call to run_doctest_check here.
        # With DocstringCodeExample.snippet being clean, multi-line code,
        # run_custom_check is the more direct validation.
        # run_doctest_check was causing issues with doctest's assumptions
        # about "single" statements when given a pre-formatted block.

        custom_errors = self.run_custom_check(example, global_vars=global_vars)
        if custom_errors:
            errors.extend(custom_errors)

        return errors
