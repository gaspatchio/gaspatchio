# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compilation panel keeps polars' diagnosis whole, as the traced-run one does.

There are two error panels. ``FriendlyErrorFormatter`` builds the traced-run
one; ``EnhancedError.to_console()`` builds the compilation one, and the
compilation-error route is checked *first*, so a ``ColumnNotFoundError`` is
answered by this panel and never reaches the other. Both carried the same
truncator -- flatten the whole polars text onto one line, then cut it at 117
characters and append ``...`` -- and only the traced-run one was repaired.

The cut lands on the part of the message that answers the question. A
``ColumnNotFoundError`` names the missing column and then lists the columns
that do exist, which is the reader's next move; the budget ran out two column
names into that list. The plan dump polars appends after
``PLAN_DUMP_BOUNDARY`` never even had to contribute -- the diagnosis alone
overran the budget -- so a smaller dump would not have saved it.

The repaired contract is the one already shipping on the other panel: split on
that boundary, keep the diagnosis entire (no budget, because a truncated
diagnosis is the defect), and state the omission with ``PLAN_DUMP_OMITTED``
rather than smearing a slice of a tree onto one line. Both panels now read
those two literals from ``gaspatchio.errors.constants``, and the last test
here holds each of them to that one home -- the boundary as well as the
marker, since the boundary is the literal with three readers and the one
whose three-way duplication left this defect half-fixed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.errors.constants import PLAN_DUMP_BOUNDARY, PLAN_DUMP_OMITTED
from gaspatchio.errors.models import (
    ColumnInfo,
    DataFrameContext,
    EnhancedError,
    ErrorMetadata,
    ErrorType,
    OperationContext,
    SourceLocation,
)
from gaspatchio.util import set_error_mode

# The column the model asks for and the frame does not have.
_MISSING_COLUMN = "a_column_that_does_not_exist_anywhere_in_this_frame"

# The last name in polars' valid-columns list. It is the far end of the
# answer, and the first casualty of a budget applied to the front of it.
_LAST_VALID_COLUMN = "policies_in_force"

# What the old cut left behind: the second column name, chopped mid-word.
_TRUNCATED_TAIL = "sum_assure..."

# A token that appears only inside the query-plan dump.
_PLAN_NODE_LABEL = "WITH_COLUMNS"

# The budget the whole message used to have to fit inside.
_OLD_BUDGET = 120

# The package as imported, so the scan below reads the files that ran.
_PACKAGE_ROOT = Path(gaspatchio.__file__).resolve().parent


def _failing_frame() -> ActuarialFrame:
    """Build a traced frame whose last assignment reads a column that is absent.

    Seven input columns and one calculated one, so polars' valid-columns list
    is the length an ordinary model produces -- long enough that the old
    budget ran out inside it, which is the defect, and not so long that it is
    a contrivance.
    """
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3],
            "sum_assured": [100.0, 200.0, 300.0],
            "mortality_rate": [0.01, 0.02, 0.03],
            "product_code": ["TERM", "TERM", "WL"],
            "policy_term_years": [10, 20, 30],
            "annual_premium": [1.0, 2.0, 3.0],
            "commission_rate": [0.1, 0.2, 0.3],
        },
    )
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    af.policies_in_force = 1.0 - af.mortality_rate
    af.reserve_factor = af.sum_assured * pl.col(_MISSING_COLUMN)
    return af


def _detail_line(panel: str) -> str:
    """Return the panel's single ``Error Details:`` field -- what got truncated."""
    lines = panel.splitlines()
    for index, line in enumerate(lines):
        if line.strip().endswith("Error Details:"):
            return lines[index + 1]
    msg = "the panel carried no Error Details: field"
    raise AssertionError(msg)


def _panel(message: str) -> str:
    """Render the compilation panel for one polars message, nothing else varying.

    The frame, operation and column context are the smallest that render; the
    message is the subject.
    """
    enhanced = EnhancedError(
        metadata=ErrorMetadata(
            error_type=ErrorType.COLUMN_NOT_FOUND,
            original_message=message,
            timestamp=datetime(2026, 9, 4, tzinfo=UTC),
        ),
        operation=OperationContext(
            index=1,
            total_operations=2,
            alias="reserve_factor",
            expression='col("sum_assured")',
            source=SourceLocation(
                file_path="model_calculation.py",
                line_number=17,
                function_name=None,
                source_line="af.reserve_factor = af.sum_assured * af.mortality_rate",
            ),
        ),
        dataframe=DataFrameContext(
            shape=(3, 1),
            columns=[ColumnInfo(name="sum_assured", dtype="Float64")],
        ),
    )
    return enhanced.to_console(use_emoji=False)


def test_the_panel_keeps_the_valid_columns_list_the_old_budget_cut() -> None:
    """Through the real compilation panel: the whole diagnosis arrives.

    The frame, the collect, the handler and the panel -- not the model in
    isolation. The premise is asserted rather than assumed: polars really did
    append a plan dump, and its diagnosis alone really is longer than the
    budget that used to hold both.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()

    panel = str(caught.value)
    assert "column_not_found" in panel

    raw = caught.value.enhanced_error.metadata.original_message
    diagnosis = " ".join(raw.partition(PLAN_DUMP_BOUNDARY)[0].split())
    assert PLAN_DUMP_BOUNDARY in raw
    assert len(diagnosis) > _OLD_BUDGET

    # The repair: every valid column polars listed survives, and the cut that
    # used to replace them is gone.
    assert diagnosis in _detail_line(panel)
    assert _LAST_VALID_COLUMN in _detail_line(panel)
    assert _TRUNCATED_TAIL not in panel


def test_the_panel_drops_the_plan_dump_instead_of_smearing_it() -> None:
    """The field carries the diagnosis, and says what it left out."""
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()

    detail = _detail_line(str(caught.value))

    assert _MISSING_COLUMN in detail
    assert PLAN_DUMP_BOUNDARY not in detail
    assert _PLAN_NODE_LABEL not in detail
    assert detail.endswith(PLAN_DUMP_OMITTED)


def test_the_dropped_plan_dump_is_still_reachable_on_the_exception() -> None:
    """Dropping it from the panel is only honest while it survives elsewhere.

    The compilation handler stamps ``llm_context`` from the same
    ``EnhancedError``, and the metadata it reads holds polars' text untouched.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()

    raw = caught.value.llm_context["original_error"]

    assert PLAN_DUMP_BOUNDARY in raw
    assert _PLAN_NODE_LABEL in raw
    assert _MISSING_COLUMN in raw


def test_a_long_message_with_no_plan_dump_is_not_cut() -> None:
    """No boundary means nothing to drop -- and still nothing to truncate.

    An assumption-table lookup miss is the live case: a long, entirely
    actionable message that polars hands over with no plan dump behind it.
    The old budget cut it too. It arrives as two lines -- the stable first
    line the replay matches on, then the batch's keys -- and the
    field flattens them onto one, so the fixture is compared flattened.
    """
    diagnosis = (
        "the plugin failed with message: Lookup on table 'mortality' has "
        "missing keys (or NaN-valued entries) for key column 'attained_age'.\n"
        "Missed keys (first 3 distinct): (attained_age=77). The engine hands "
        "this lookup one batch of rows per call, so it can say neither how many "
        "of the frame's rows missed nor which frame row -- filter the frame on "
        "the keys above to find those rows. The keys named are the ones this "
        "batch missed; other batches may miss different keys. Keys must exist "
        'in the table (exact match). Pass on_missing="nan" or a numeric fill '
        "value to Table(...) or lookup(...) to restore silent-NaN behaviour."
    )
    assert len(diagnosis) > _OLD_BUDGET

    detail = _detail_line(_panel(diagnosis))

    assert " ".join(diagnosis.split()) in detail
    assert PLAN_DUMP_OMITTED not in detail


def test_the_message_is_still_flattened_onto_one_line() -> None:
    """The field is one line, so the message's own newlines still collapse."""
    detail = _detail_line(_panel("first line\n\n  second line"))

    assert detail.strip() == "first line second line"


def test_the_two_panels_read_both_plan_dump_literals_from_one_home() -> None:
    """Each literal is spelled once in the package: the module that defines it.

    Two panels stating an omission in two spellings is how the defect got
    half-fixed the first time. Written as a scan rather than an equality
    because a second copy is exactly what an equality check cannot see, and
    over both literals rather than the marker alone: the boundary is the one
    with three readers, and its duplication is what this repair retires. The
    assertion is a mapping so a failure names which literal drifted.
    """
    sources = {
        path: path.read_text(encoding="utf-8") for path in _PACKAGE_ROOT.rglob("*.py")
    }
    spelled_in = {
        name: sorted(
            path.relative_to(_PACKAGE_ROOT).as_posix()
            for path, text in sources.items()
            if literal in text
        )
        for name, literal in (
            ("PLAN_DUMP_BOUNDARY", PLAN_DUMP_BOUNDARY),
            ("PLAN_DUMP_OMITTED", PLAN_DUMP_OMITTED),
        )
    }

    assert spelled_in == {
        "PLAN_DUMP_BOUNDARY": ["errors/constants.py"],
        "PLAN_DUMP_OMITTED": ["errors/constants.py"],
    }
