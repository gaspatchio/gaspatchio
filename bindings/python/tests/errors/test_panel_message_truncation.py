# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The panel keeps polars' diagnosis whole and drops the plan dump instead.

``FriendlyErrorFormatter._clean_error_message`` used to flatten the whole
exception -- diagnosis *and* the query-plan dump polars appends after
``Resolved plan until failure`` -- into one string, then cut it at 117
characters. Two things went wrong at once. The dump was smeared onto the
single-line ``Message:`` field, where a plan tree with its newlines removed
says nothing; and the budget it shared was smaller than polars' own advice, so
the panel cut its diagnosis mid-word: ``try an expli...`` instead of ``try an
explicit cast first``. The actionable half of the sentence was the half that
never arrived.

The repaired contract: split on that boundary, keep the diagnosis entire --
no budget, because a truncated diagnosis is the defect -- and say the dump was
dropped rather than smearing a slice of it. The dump itself is not lost: the
traced-run handler stamps the untouched polars text on ``llm_context`` before
it replaces the message, and the tests below check that too, because "we
dropped it" is only defensible while it remains reachable.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Col
from gaspatchio.errors.formatter import FriendlyErrorFormatter
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan
from gaspatchio.util import set_error_mode

# Polars' advice, and the point the old 117-character budget cut it at.
_FULL_ADVICE = "try an explicit cast first"
_TRUNCATED_ADVICE = "try an expli..."

# The boundary polars puts between diagnosis and plan dump, and a token that
# appears only inside the dump.
_PLAN_BOUNDARY = "Resolved plan until failure"
_PLAN_NODE_LABEL = "WITH_COLUMNS"

# The budget the diagnosis used to have to fit inside.
_OLD_BUDGET = 120


def _failing_frame() -> ActuarialFrame:
    """Build a traced frame whose last assignment multiplies a string by a float.

    Three healthy calculations run first so the plan polars dumps is deep
    enough to be the thing that would eat the old budget, and so the panel
    has to choose which assignment failed rather than take the only one.
    """
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3],
            "sum_assured": [100.0, 200.0, 300.0],
            "mortality_rate": [0.01, 0.02, 0.03],
            "product_code": ["TERM", "TERM", "WL"],
        },
    )
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    af.policies_in_force = 1.0 - af.mortality_rate
    af.expected_deaths = af.policies_in_force * af.mortality_rate
    af.death_claims = af.sum_assured * af.expected_deaths
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    return af


def _message_line(panel: str) -> str:
    """Return the panel's single ``Message:`` field -- what got truncated."""
    for line in panel.splitlines():
        if line.strip().startswith("Message:"):
            return line
    msg = "the panel carried no Message: line"
    raise AssertionError(msg)


def _record(column: str) -> CalculationRecord:
    """One recorded calculation, as the frame's log would hold it."""
    return CalculationRecord(
        column=column,
        ordinal=1,
        operation_id=0,
        node=Col(column),
        expr=pl.col(column),
        dtype=None,
        source=SourceSpan(
            file="model_calculation.py",
            line=17,
            end_line=17,
            function=None,
            statement=f"af.{column} = af.product_code * af.sum_assured",
            rhs=None,
            target_literal=True,
        ),
        origin="assignment",
    )


def _formatter(exception: Exception) -> FriendlyErrorFormatter:
    """Build the panel formatter the way the traced-run handler wires it."""
    return FriendlyErrorFormatter(
        record=_record("reserve_factor"),
        exception=exception,
        last_good_df=pl.DataFrame({"sum_assured": [100.0]}),
    )


def test_the_panel_keeps_advice_the_old_budget_cut() -> None:
    """Through the real traced-run panel: the whole sentence arrives.

    This is the A.2b defect end to end -- the frame, the collect, the
    handler and the panel, not the helper in isolation. The premise is
    asserted rather than assumed: the raw polars text really does carry a
    plan dump, and its diagnosis really is longer than the budget that used
    to hold both.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    panel = str(caught.value)
    assert caught.value._enhanced_processed is True  # noqa: SLF001 -- the panel path's own marker
    assert "Calculation Error" in panel

    # Premise: polars appended a plan dump, and the diagnosis alone overruns
    # the old budget. Without both, this test would pass for the wrong reason.
    raw = caught.value.llm_context["error_details"]["message"]
    assert _PLAN_BOUNDARY in raw
    assert len(raw.split(_PLAN_BOUNDARY, 1)[0].split()) > 0
    assert len(" ".join(raw.split(_PLAN_BOUNDARY, 1)[0].split())) > _OLD_BUDGET

    # The repair: the advice survives, and the cut that used to replace it
    # is gone.
    assert _FULL_ADVICE in panel
    assert _TRUNCATED_ADVICE not in panel


def test_the_panel_drops_the_plan_dump_instead_of_smearing_it() -> None:
    """The ``Message:`` field carries diagnosis, and says what it left out."""
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    message_line = _message_line(str(caught.value))

    assert _FULL_ADVICE in message_line
    assert _PLAN_BOUNDARY not in message_line
    assert _PLAN_NODE_LABEL not in message_line
    assert "omitted" in message_line


def test_the_dropped_plan_dump_is_still_reachable_on_the_exception() -> None:
    """Dropping it from the panel is only honest while it survives elsewhere.

    The traced-run handler builds ``llm_context`` before it overwrites
    ``e.args``, so the untouched polars text -- plan dump included -- stays
    on the delivered exception.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    raw = caught.value.llm_context["error_details"]["message"]

    assert _PLAN_BOUNDARY in raw
    assert _PLAN_NODE_LABEL in raw
    assert _FULL_ADVICE in raw


def test_a_long_diagnosis_with_no_plan_dump_is_not_cut() -> None:
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

    panel = _formatter(pl.exceptions.ComputeError(diagnosis)).format_error()

    assert " ".join(diagnosis.split()) in _message_line(panel)
    assert "omitted" not in _message_line(panel)


def test_the_diagnosis_is_still_flattened_onto_one_line() -> None:
    """The field is one line, so the diagnosis' own newlines still collapse."""
    formatter = _formatter(pl.exceptions.ComputeError("first line\n\n  second line"))

    assert "Message: first line second line" in formatter.format_error()
