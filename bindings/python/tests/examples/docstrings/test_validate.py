# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import polars as pl  # For multi_example_fixture global_vars
import pytest
from gaspatchio_core.examples.docstrings.models import DocstringCodeExample
from gaspatchio_core.examples.docstrings.parse import GaspatchioDocstringParser
from gaspatchio_core.examples.docstrings.validate import GaspatchioEvalExample

from tests.examples.docstrings.fixtures.multi_example_fixture import PremiumCalculator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def get_examples_from_fixture(
    fixture_file_name: str,
    object_context_filter: str | None = None,
    example_index_filter: int | None = None,
) -> list[DocstringCodeExample]:
    parser = GaspatchioDocstringParser()
    fixture_path = FIXTURES_DIR / fixture_file_name
    docstrings = parser.process_file(fixture_path)
    all_examples: list[DocstringCodeExample] = []
    for ds in docstrings:
        for i, ex in enumerate(ds.examples):
            if object_context_filter and ex.object_context != object_context_filter:
                continue
            if (
                example_index_filter is not None
                and ex.example_index != example_index_filter
            ):
                continue
            all_examples.append(ex)
    if not all_examples and (object_context_filter or example_index_filter is not None):
        raise ValueError(
            f"No example found for filter: {object_context_filter}, index: {example_index_filter} in {fixture_file_name}"
        )
    return all_examples


@pytest.mark.parametrize(
    "fixture_file, object_context, example_index, expected_errors_count, local_global_vars",
    [
        # Test cases for multi_example_fixture.py
        (
            "multi_example_fixture.py",
            "multi_example_fixture.PremiumCalculator.calculate_adjusted_premium",
            0,  # Example 1: Standard Risk Profile
            0,  # Expected to pass
            {"pl": pl, "PremiumCalculator": PremiumCalculator},
        ),
        (
            "multi_example_fixture.py",
            "multi_example_fixture.PremiumCalculator.calculate_adjusted_premium",
            1,  # Example 2: Higher Risk Profile
            0,  # Expected to pass
            {"pl": pl, "PremiumCalculator": PremiumCalculator},
        ),
    ],
)
def test_gaspatchio_eval_example_check_example_integration(
    fixture_file: str,
    object_context: str,
    example_index: int | None,
    expected_errors_count: int,
    local_global_vars: dict,
):
    """Integration test for GaspatchioEvalExample.check_example.

    This test uses examples parsed from fixture files to validate
    the `check_example` method of the `GaspatchioEvalExample` class.
    It covers various scenarios including simple function calls and method calls
    within classes, ensuring that the execution and output validation work correctly.

    !!! note "When to use"
        Run this test to ensure the core example evaluation logic is sound.
        It's crucial for verifying that docstring examples are correctly
        processed and validated against their expected outputs.

    Examples:
    ```python
    # This is a conceptual example of how one of the test cases might be structured.
    # It's not directly executable here but illustrates the pattern.
    # Assume fixture_file = "my_fixture.py"
    # Assume object_context = "my_fixture.MyClass.my_method"
    # Assume example_index = 0
    # Assume expected_errors_count = 0
    # Assume local_global_vars = {"MyClass": MyClassFromFixture}

    # example_to_test = get_examples_from_fixture(
    #     "my_fixture.py", "my_fixture.MyClass.my_method", 0
    # )[0]
    # eval_example = GaspatchioEvalExample(update_examples_mode=False)
    # errors = eval_example.check_example(example_to_test, global_vars=local_global_vars)
    # assert len(errors) == 0
    ```
    """
    if example_index is not None:
        examples_to_test = get_examples_from_fixture(
            fixture_file, object_context, example_index
        )
        assert len(examples_to_test) == 1, (
            f"Expected 1 example for {object_context} ex#{example_index}, got {len(examples_to_test)}"
        )
        example = examples_to_test[0]
    else:  # Test all examples for a given object_context if example_index is None
        examples_to_test = get_examples_from_fixture(fixture_file, object_context)
        assert len(examples_to_test) > 0, (
            f"Expected at least one example for {object_context}, got 0"
        )
        # This mode will test each example found for the object_context.
        # The assertion for expected_errors_count will apply to each.
        # Modify if different examples under same object_context have different error expectations.
        example = examples_to_test[
            0
        ]  # For simplicity, check the first if multiple, or adapt loop.

    eval_example = GaspatchioEvalExample(update_examples_mode=False)

    # For the utility_function, it's defined at the module level.
    # The snippet might be just `utility_function(...)`
    # For class methods, it's `processor = ...; processor.method(...)`
    # The provided global_vars should cover these.

    errors = eval_example.check_example(example, global_vars=local_global_vars)

    assert len(errors) == expected_errors_count, (
        f"Expected {expected_errors_count} errors, got {len(errors)}.\\nErrors:\\n{'\\n'.join(errors)}"
    )


""" # Copied and adapted from pytest_plugin.py
@pytest.mark.gaspatchio_docstring_example
def test_the_actual_docstring_examples(
    docstring_example_fixture: DocstringCodeExample,
    eval_example_fixture: GaspatchioEvalExample,  # This fixture comes from the plugin
):
    example = docstring_example_fixture

    if not hasattr(example, "parent_docstring") or example.parent_docstring is None:
        pytest.fail(
            f"Example {example.object_context}#{example.example_index} is missing parent_docstring link."
        )

    structure_errors = example.parent_docstring.validate_structure()
    if structure_errors:
        pytest.fail(
            f"Docstring structure errors for {example.object_context}:\n"
            + "\n".join(structure_errors),
            pytrace=False,
        )

    lint_errors = example.lint()
    if lint_errors:
        pytest.fail(
            f"Linting errors in {example.object_context}#{example.example_index}:\n"
            + "\n".join(lint_errors),
            pytrace=False,
        )

    global_vars = {}  # Keep it simple as discussed for self-contained examples

    if eval_example_fixture.update_examples_mode:
        updated_successfully = eval_example_fixture.update_example_output(
            example, global_vars=global_vars
        )
        if not updated_successfully:
            pytest.xfail(
                reason=f"Update attempt for {example.object_context} ex#{example.example_index} did not complete successfully (check logs)."
            )
    else:  # Not in update mode, so check the example
        execution_errors = eval_example_fixture.check_example(
            example, global_vars=global_vars
        )
        if execution_errors:
            pytest.fail(
                f"Execution/validation errors in {example.object_context}#{example.example_index}:\n"
                + "\n".join(execution_errors),
                pytrace=False,
            )
 """
