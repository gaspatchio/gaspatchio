# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What one run's refusals read like, and what the closing sentence claims.

A refusal carries the actuarial thing, where it is, how many rows it is
about, the next move and the clause it rests on. The three groups are the
three moments a refusal can be known in, and the closing sentence is the
one claim the reader needs: whether anything ran at all.
"""

from __future__ import annotations

import json

from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport

TREE_HEADING = "From the model's tree and its payloads, before any book was read:"
INPUTS_HEADING = "From the book, before anything was compiled:"
COMPLETION_HEADING = "At completion, with every output withheld:"
NOTES_HEADING = "Reported, not refused:"

TREE = Refusal(
    group="tree",
    where="reserve@3",
    count=None,
    what="the model writes a state graph, which no engine here lowers",
    move="rewrite the balance as a compiled rollforward, or run it on Polars",
    clause="17",
)
INPUTS = Refusal(
    group="inputs",
    where="premium_pp",
    count=412,
    what="a null in a column the projection reads as a value",
    move="fill or exclude those policies before the run",
    clause="11.1.13",
)
COMPLETION = Refusal(
    group="completion",
    where="fund_value",
    count=3,
    what="the account value stopped being finite part way through the term",
    move="check the credited rate and the charge basis on those policies",
    clause="§16.1",
)


def test_the_three_groups_are_headed_and_ordered() -> None:
    report = RunReport(refusals=(COMPLETION, INPUTS, TREE), notes=())
    rendered = report.render()

    assert TREE_HEADING in rendered
    assert INPUTS_HEADING in rendered
    assert COMPLETION_HEADING in rendered
    assert (
        rendered.index(TREE_HEADING)
        < rendered.index(INPUTS_HEADING)
        < rendered.index(COMPLETION_HEADING)
    )


def test_one_refusal_reads_as_where_count_what_move_clause() -> None:
    rendered = RunReport(refusals=(INPUTS,), notes=()).render()

    assert (
        "  premium_pp · 412 · a null in a column the projection reads as a "
        "value · fill or exclude those policies before the run · 11.1.13"
    ) in rendered


def test_a_field_with_no_value_leaves_no_separator_behind() -> None:
    rendered = RunReport(refusals=(TREE,), notes=()).render()

    assert (
        "  reserve@3 · the model writes a state graph, which no engine here "
        "lowers · rewrite the balance as a compiled rollforward, or run it "
        "on Polars · 17"
    ) in rendered
    assert " ·  · " not in rendered


def test_a_refusal_no_clause_states_ends_at_its_move() -> None:
    # A fold into aggregates is outside the artifact, so no section of the
    # specification states its refusals and the line stops at the next move.
    unfolded = Refusal(
        group="tree",
        where="running",
        count=None,
        what="the running engine cannot fold a model into aggregates",
        move="aggregate on Polars",
        clause=None,
    )
    line = unfolded.line()

    assert line.endswith("· aggregate on Polars")
    assert unfolded.to_dict()["clause"] is None


def test_nothing_was_computed_unless_a_completion_refusal_exists() -> None:
    assert (
        RunReport(refusals=(TREE, INPUTS), notes=()).closing_sentence()
        == "Nothing was computed."
    )
    assert (
        RunReport(refusals=(TREE, COMPLETION), notes=()).closing_sentence()
        == "No results were published."
    )
    # An empty report closes with nothing at all: both sentences are claims
    # about a run that stopped, and this one describes a run that did not.
    assert RunReport(refusals=(), notes=()).closing_sentence() == ""


def test_the_closing_sentence_ends_the_rendered_report() -> None:
    rendered = RunReport(refusals=(COMPLETION,), notes=()).render()

    assert rendered.rstrip().endswith("No results were published.")


def test_the_notes_are_printed_apart_from_the_refusals() -> None:
    report = RunReport(
        refusals=(TREE,),
        notes=("mortality_select on the fallback path: density 3.1 %",),
    )
    rendered = report.render()

    assert NOTES_HEADING in rendered
    assert "  mortality_select on the fallback path: density 3.1 %" in rendered
    assert rendered.index(TREE_HEADING) < rendered.index(NOTES_HEADING)


def test_the_report_round_trips_through_json() -> None:
    report = RunReport(refusals=(TREE, INPUTS, COMPLETION), notes=("one note",))

    written = json.dumps(report.to_dict())
    read = json.loads(written)

    assert read["notes"] == ["one note"]
    assert [one["group"] for one in read["refusals"]] == [
        "tree",
        "inputs",
        "completion",
    ]
    assert read["refusals"][1]["count"] == 412
    assert read["refusals"][0]["count"] is None
    assert read["closing_sentence"] == "No results were published."


def test_the_one_exception_class_carries_the_report_as_its_message() -> None:
    report = RunReport(refusals=(INPUTS,), notes=())

    raised = EngineRefusal(report)

    assert raised.report is report
    assert str(raised) == report.render()


def test_a_report_with_no_refusals_has_nothing_to_close() -> None:
    """A run that merely had something to say finished and published.

    Both closing sentences are claims about a run that stopped. Printing
    either one under a note would have the report contradicting the values
    the caller is holding -- which is what a successful run's report does
    carry, now that a null in a column nothing reads is reported rather than
    refused.
    """
    report = RunReport(refusals=(), notes=("one table fell back",))

    rendered = report.render()

    assert report.closing_sentence() == ""
    assert rendered == "Reported, not refused:\n  one table fell back"
    assert "Nothing was computed." not in rendered
    assert "No results were published." not in rendered
    assert not report.refused()


def test_a_report_carrying_a_refusal_still_closes_beneath_its_notes() -> None:
    report = RunReport(refusals=(TREE,), notes=("one table fell back",))

    rendered = report.render()

    assert rendered.endswith("Nothing was computed.")
    assert "Reported, not refused:" in rendered
    assert report.closing_sentence() == "Nothing was computed."
