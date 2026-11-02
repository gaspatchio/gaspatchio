# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The retired public names refuse, and the refusal is the assertion.

Most of the names below were reachable by import or attribute from a
model and referenced by nothing -- not the package, not the tests, not
the tutorials, not the skills, not the specification, not the
documentation site. They were retired: one door to each thing, and nothing
that can be mistaken for one.

``RollforwardCollector`` is the one that was referenced, and it was
retired on its own reading: a deprecated second door to the
extractions ``CompiledRollforward`` already publishes. Every reference
was a test, and the kernel tests that need the standalone form now emit
it through a helper under ``tests/`` rather than through a name a model
could import.

Each assertion here is that a door has stayed shut. Not unused, not
dead -- do not "fix" one away.
"""

from __future__ import annotations

from importlib import import_module

import pytest

from gaspatchio.errors.models import (
    ColumnInfo,
    DataFrameContext,
    OperationContext,
    SourceLocation,
    Suggestion,
    SuggestionType,
)
from gaspatchio.errors.validation import ValidationError


def test_the_table_registry_module_is_refused() -> None:
    """``gaspatchio.registry`` no longer resolves.

    It wrapped the Rust table registry in two classes nothing imported;
    ``gaspatchio.assumptions`` is the door to a lookup table. The import
    IS the assertion, so it must fail.
    """
    with pytest.raises(ModuleNotFoundError):
        import_module("gaspatchio.registry")


@pytest.mark.parametrize("retired_value", ["type_cast", "operation_split", "code_example"])
def test_a_retired_suggestion_type_is_refused(retired_value: str) -> None:
    """Three members nothing ever constructed are gone from the enum.

    ``TYPO_FIX`` and ``DOCUMENTATION`` are the two the advice builder
    actually stamps on a suggestion; the rest described kinds of advice
    this package does not give.
    """
    with pytest.raises(ValueError, match=retired_value):
        SuggestionType(retired_value)


def test_the_kept_suggestion_types_still_answer() -> None:
    """The two members in use are untouched, so the cut was the three."""
    assert SuggestionType("typo_fix") is SuggestionType.TYPO_FIX
    assert SuggestionType("documentation") is SuggestionType.DOCUMENTATION


@pytest.mark.parametrize(
    "retired_member", ["dataframe_schema", "display_columns", "display_preview"]
)
def test_a_retired_dataframe_context_member_is_refused(retired_member: str) -> None:
    """A field nothing set and two formatters nothing called are gone.

    ``EnhancedError.to_console`` writes the columns and the preview out
    of the model itself; these three were a second way to say it that no
    caller ever took.
    """
    context = DataFrameContext(shape=(2, 1), columns=[])
    assert not hasattr(context, retired_member)


def test_the_enhanced_message_property_is_refused() -> None:
    """The message lives in ``args``, and now only there.

    Both sites that once set the private ``_enhanced_message`` already
    assigned the same text to ``e.args`` on the line above, so the text a
    reader sees is unchanged by the property's removal.
    """
    error = ValidationError("x")
    assert not hasattr(error, "enhanced_message")
    assert not hasattr(error, "_enhanced_message")
    assert str(error) == "x"


def test_the_rollforward_collector_is_refused_from_the_top_level() -> None:
    """``from gaspatchio import RollforwardCollector`` no longer resolves.

    The class was a facade over ``CompiledRollforward``, deprecated since
    v0.6. ``compiled.expr_for(state)`` and ``compiled.increment_for(label)``
    are the extractions, and on an ``ActuarialFrame`` they share one kernel
    call where the facade cost one per extraction.
    """
    with pytest.raises(ImportError):
        from gaspatchio import RollforwardCollector  # noqa: F401


def test_the_rollforward_collector_is_refused_from_its_subpackage() -> None:
    """``gaspatchio.rollforward`` stops publishing it too.

    Both spellings went in the same commit, so neither is a surviving
    path to the other's name.
    """
    with pytest.raises(ImportError):
        from gaspatchio.rollforward import RollforwardCollector  # noqa: F401


def test_the_collector_module_is_refused() -> None:
    """``gaspatchio.rollforward._collector`` is gone, not merely unexported.

    The module held the class and nothing else. The import IS the
    assertion, so it must fail.
    """
    with pytest.raises(ModuleNotFoundError):
        import_module("gaspatchio.rollforward._collector")


@pytest.mark.parametrize(
    "model",
    [
        ColumnInfo(name="premium", dtype="f64"),
        OperationContext(
            index=0,
            total_operations=1,
            alias="premium",
            expression='col("premium")',
            source=SourceLocation(
                file_path="model.py",
                line_number=1,
                function_name=None,
                source_line=None,
            ),
        ),
        Suggestion(
            text="check the column name",
            type=SuggestionType.TYPO_FIX,
            relevance_score=1.0,
        ),
    ],
    ids=["column_info", "operation_context", "suggestion"],
)
def test_a_retired_display_formatter_is_refused(model: object) -> None:
    """Three per-model console formatters nothing called are gone.

    Each rendered one line of a console error, and the only caller of any
    of them was ``DataFrameContext.display_columns``, which was retired
    with the fourteen. ``EnhancedError.to_console`` writes the whole
    report out of the models themselves, and is the one door to the
    rendered text.
    """
    assert not hasattr(model, "display")


def test_the_source_location_display_helper_is_refused() -> None:
    """``SourceLocation.display_location`` is gone with its one reader.

    It formatted ``file:line`` for ``OperationContext.display``, which was
    retired first; with its one reader gone, the helper goes too. The two
    fields it read are the record, and the console report writes them out
    itself.
    """
    location = SourceLocation(
        file_path="model.py", line_number=1, function_name=None, source_line=None
    )
    assert not hasattr(location, "display_location")
