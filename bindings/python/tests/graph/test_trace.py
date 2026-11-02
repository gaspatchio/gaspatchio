# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The walk-through beside a formula, and what it is allowed to say.

A trace is the first thing an actuary reads: the formula, the numbers put
into it, the number that came out. Its whole value is that a reader can
check the middle line by eye, which means the middle line has to be true.
Two ways it was not.

A fold down the model points -- ``af.total_claims =
af.expected_claims.sum()`` -- had one policy's number substituted into it
and read ``(500).sum()`` with a result of 5,950: arithmetic nobody could
check, because nobody could do it. And a per-period column had one period's
arithmetic shown for a line that computes the whole timeline at once, with
nothing saying which period it was.

The tests here are what hold the walk-through to the two rules that follow
from that: a trace never puts a value where no single value stands, and it
never shows one period without naming it.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import math
from typing import Any, cast

import polars as pl
import pytest
from polars.expr.meta import ExprMetaNameSpace
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.cli import app
from gaspatchio.frame.graph import calc_graph
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.graph_models import GraphExportConfig
from gaspatchio.frame.graph.trace_generator import (
    _counts_of_numbers,
    _direction,
    _hotspot,
)
from gaspatchio.frame.graph.trace_voice import sentence_for
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio.frame.graph.value_extractor import PeriodNotInTimelineError


def _artifact(
    af: ActuarialFrame, config: GraphExportConfig | None = None
) -> dict[str, Any]:
    """Export the frame's graph against its own collected values."""
    frame = af.collect()
    return json.loads(GraphExporter(af).export(frame, config))  # type: ignore[no-any-return]


def _exported(
    af: ActuarialFrame, config: GraphExportConfig | None = None
) -> dict[str, dict[str, Any]]:
    """Export the frame's graph against its own collected values, by node id."""
    return {node["id"]: node for node in _artifact(af, config)["nodes"]}


def _steps(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one node's trace steps, or nothing where it carries no trace."""
    trace = node.get("trace")
    return trace if isinstance(trace, list) else []


def _a_book_with_a_portfolio_total() -> ActuarialFrame:
    """Return a model whose last line folds a column down the model points.

    Three policies, each with its own expected claims, and a total that is
    one number for the whole book. The shape the falsehood was found on.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "mortality_rate": [0.005, 0.004, 0.003],
            }
        )
    )
    frame.expected_claims = frame.sum_assured * frame.mortality_rate
    frame.total_claims = frame.expected_claims.polars_native().sum()
    return frame


def _a_projection_with_a_present_value() -> ActuarialFrame:
    """Return a model that reduces each policy's own periods to one number.

    ``.list.sum()`` over one policy's own cashflow list is the ``pv_*``
    shape, and it is honest: the whole operand is inside the sampled row.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.005, 0.004],
            }
        )
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.claims = frame.sum_assured * frame.mortality_rate * (frame.month + 1)
    frame.pv_claims = frame.claims.list.sum()
    return frame


# --- a fold down the model points -------------------------------------------


def test_a_whole_book_total_does_not_show_one_policy_inside_the_fold() -> None:
    """The defect itself: ``(500).sum()`` is arithmetic nobody can check."""
    nodes = _exported(_a_book_with_a_portfolio_total())
    rendered = " ".join(step["expr"] for step in _steps(nodes["total_claims@1"]))
    assert "(500)" not in rendered
    assert "(500.0)" not in rendered


def test_a_whole_book_total_names_the_population_it_was_taken_over() -> None:
    """A reader has to be told what was summed, since no value is shown."""
    nodes = _exported(_a_book_with_a_portfolio_total())
    steps = _steps(nodes["total_claims@1"])
    substitution = steps[1]
    assert "expected_claims" in substitution["expr"]
    assert "3 model points" in substitution["expr"]


def test_a_whole_book_total_says_why_no_value_is_substituted() -> None:
    """Silence with no reason reads as a producer that forgot the step."""
    nodes = _exported(_a_book_with_a_portfolio_total())
    comment = _steps(nodes["total_claims@1"])[1]["comment"]
    assert "model points" in comment
    assert "policy" in comment


def test_a_whole_book_total_still_reaches_the_value_the_column_holds() -> None:
    """Saying less is not saying nothing: the result stays on the record."""
    nodes = _exported(_a_book_with_a_portfolio_total())
    steps = _steps(nodes["total_claims@1"])
    assert steps[-1]["result"] == 3000.0
    assert nodes["total_claims@1"]["value_sample"] == 3000.0


def test_the_population_is_the_filtered_set_where_a_filter_cut_the_frame() -> None:
    """A filtered export folded fewer rows, and the sentence says how many."""
    nodes = _exported(
        _a_book_with_a_portfolio_total(),
        GraphExportConfig(filter_expr="col('sum_assured') > 150000"),
    )
    assert "2 model points" in _steps(nodes["total_claims@1"])[1]["expr"]


# --- a fold along one policy's own periods ----------------------------------


def test_a_present_value_over_one_policys_periods_still_substitutes() -> None:
    """UNCHANGED, deliberately: the whole operand is inside the sampled row.

    ``.list.sum()`` reduces one policy's own cashflow list, so the sampled
    policy's own values are exactly what the fold ran over and putting them
    in the walk-through states nothing that is not true. A later change that
    swept this into the model-point rule would take a true statement away.
    """
    nodes = _exported(_a_projection_with_a_present_value())
    substitution = _steps(nodes["pv_claims@1"])[1]
    assert "claims" in substitution["values"]
    assert "model points" not in substitution["expr"]


# --- the arithmetic shape, byte for byte ------------------------------------


def test_a_scalar_arithmetic_trace_is_what_it_always_was() -> None:
    """The scalar path does not move: same steps, same text, same values."""
    nodes = _exported(_a_book_with_a_portfolio_total())
    assert _steps(nodes["expected_claims@1"]) == [
        {"step": 1, "expr": "(sum_assured) * (mortality_rate)"},
        {
            "step": 2,
            "expr": "((100000)) * ((0.005))",
            "values": {"mortality_rate": 0.005, "sum_assured": 100000.0},
        },
        {"step": 3, "expr": "500", "result": 500.0},
    ]


# --- a per-period line, walked through as the timeline it is ----------------


def _a_projection_that_turns_negative() -> ActuarialFrame:
    """Return a one-policy projection whose net cashflow crosses zero.

    A level premium against a claim that grows with the month: positive
    while the premium covers it, negative afterwards. The shape a reserve
    or an account value has when something is about to go wrong, and the
    one a reader wants pointed at.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "premium": [100.0], "claim": [40.0]})
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.net_cf = frame.premium - frame.claim * frame.month
    return frame


def test_a_per_period_operand_is_substituted_as_its_whole_run() -> None:
    """The run goes in, not its first period: the line computes all of it."""
    substitution = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])[1]
    assert "[0, 1, 2, ‥, 6]" in substitution["expr"]


def test_a_per_policy_operand_beside_it_stays_one_number() -> None:
    """Scalar times run is the framework's own idiom, shown as itself."""
    substitution = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])[1]
    assert substitution["values"]["premium"] == 100.0
    assert substitution["values"]["claim"] == 40.0
    assert "(100)" in substitution["expr"]


def test_a_per_period_step_says_how_many_periods_it_is_showing() -> None:
    """Never left to be assumed, in the default case as much as any other."""
    steps = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])
    assert steps[1]["expr"].endswith("(7 periods)")
    assert steps[2]["expr"].endswith("(7 periods)")


def test_the_result_line_names_the_one_period_it_reports() -> None:
    """``result`` is one number out of seven, and it says which one."""
    final = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])[-1]
    assert final["comment"] == "``result`` is period 0 of 7."
    assert final["result"] == 100.0


def test_a_per_period_step_states_the_runs_own_shape() -> None:
    """Length, both endpoints, direction, holes and negatives, in one line."""
    final = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])[-1]
    assert final["shape"] == (
        "7 periods · first 100 · last -140 · ↓ · "
        "0 without a number · 4 negative (first at t=3)"
    )


def test_the_pointer_names_the_period_and_the_rule_that_chose_it() -> None:
    """A pointer with no rule beside it is a number a reader cannot place."""
    final = _steps(_exported(_a_projection_that_turns_negative())["net_cf@1"])[-1]
    assert final["pointer"] == (
        "first sign change at t=3 (the first period whose sign differs "
        "from the period before it)"
    )


def test_a_run_with_nothing_anomalous_in_it_gets_no_pointer() -> None:
    """Silence is the statement. A model that is fine should read as one."""
    final = _steps(_exported(_a_projection_with_a_present_value())["claims@1"])[-1]
    assert final["shape"].startswith("7 periods")
    assert "pointer" not in final


def test_a_period_holding_no_number_is_what_the_pointer_names_first() -> None:
    """A hole beats a sign change: everything after it is arithmetic on it."""
    assert _hotspot([1.0, 2.0, None, -3.0]) == (
        "no value at t=2 (the first period holding neither a number nor a value at all)"
    )


def test_one_move_that_dominates_the_run_is_pointed_at_with_its_bar() -> None:
    """A break the whole timeline turns on, and the rule that found it."""
    assert _hotspot([100.0, 99.0, 98.0, 2.0, 1.0]) == (
        "largest single-period move at t=3 (more than half of all the "
        "period-to-period movement in this run, a reading taken only over "
        "3 moves or more)"
    )


def test_a_smooth_ramp_has_a_largest_move_and_is_not_pointed_at() -> None:
    """Every run has a largest move; only one that dominates is a hotspot."""
    assert _hotspot([1.0, 2.0, 3.0, 4.0, 5.0]) is None


# --- the period knob --------------------------------------------------------


def test_a_pinned_period_substitutes_that_periods_own_values() -> None:
    """What a reader zooming in on one month asked to see."""
    nodes = _exported(_a_projection_that_turns_negative(), GraphExportConfig(period=3))
    substitution = _steps(nodes["net_cf@1"])[1]
    assert substitution["values"]["month"] == 3
    assert substitution["expr"].endswith("(period 3 of 7)")


def test_a_pinned_period_says_which_period_the_result_is() -> None:
    """The knob moves the window and the window says where it is."""
    nodes = _exported(_a_projection_that_turns_negative(), GraphExportConfig(period=3))
    final = _steps(nodes["net_cf@1"])[-1]
    assert final["comment"] == "``result`` is period 3 of 7."
    assert final["result"] == -20.0


def test_a_pinned_period_moves_the_value_sample_with_it() -> None:
    """The sample and the walk-through are read at one point of the run."""
    nodes = _exported(_a_projection_that_turns_negative(), GraphExportConfig(period=3))
    assert nodes["net_cf@1"]["value_sample"] == -20.0


def test_the_document_states_which_period_its_values_were_read_at() -> None:
    """Two artifacts of one model read at two points are not two models."""
    artifact = _artifact(
        _a_projection_that_turns_negative(), GraphExportConfig(period=3)
    )
    assert artifact["enrichment"]["periods"] == [3]


def test_every_period_taken_is_what_a_null_periods_states() -> None:
    """The default reads the whole run, which is what the format's null means."""
    artifact = _artifact(_a_projection_that_turns_negative())
    assert artifact["enrichment"]["periods"] is None


def test_a_pinned_period_narrows_nothing_a_line_folded_the_periods_away() -> None:
    """The model-point rule again, with the axes swapped.

    A present value is one number per policy reached from every period of
    a run. Narrowing its operand to the pinned period would put one period
    inside a fold that ran over all of them -- ``(200).sum()`` -- which is
    the falsehood this file exists to keep out, in the other direction.
    """
    nodes = _exported(_a_projection_with_a_present_value(), GraphExportConfig(period=3))
    substitution = _steps(nodes["pv_claims@1"])[1]
    assert "‥" in substitution["expr"]
    assert "(200).sum()" not in substitution["expr"]


def test_a_period_past_the_end_of_the_projection_is_refused_by_length() -> None:
    """The reader who got the number wrong needs the number, not the news."""
    with pytest.raises(PeriodNotInTimelineError, match="runs to 7 periods"):
        _exported(_a_projection_that_turns_negative(), GraphExportConfig(period=120))


def test_a_period_asked_of_a_model_with_no_timeline_is_refused() -> None:
    """A frame of per-policy columns has no period for a knob to turn to."""
    with pytest.raises(PeriodNotInTimelineError, match="no projection timeline"):
        _exported(_a_book_with_a_portfolio_total(), GraphExportConfig(period=0))


# --- what the document says about itself either way -------------------------


@pytest.mark.parametrize("period", [None, 3])
def test_the_artifact_is_valid_at_every_window_it_can_be_read_at(
    period: int | None,
) -> None:
    """A trace ends at the sample beside it, whichever period both are."""
    report = validate_artifact(
        _artifact(_a_projection_that_turns_negative(), GraphExportConfig(period=period))
    )
    assert report.ok, [f.message for f in report.findings]


def test_the_command_line_offers_the_period_beside_the_policy() -> None:
    """One narrowing per axis, and both reachable the same way.

    ``--policy-id`` picks the model point and ``--period`` picks the point
    of the timeline. A knob that existed only in the library would be one
    an actuary at a terminal could not turn.
    """
    result = CliRunner().invoke(app, ["calc-graph", "--help"])
    assert result.exit_code == 0
    assert "--period" in result.output
    assert "--policy-id" in result.output


# --- what a named operation says about itself -------------------------------


def test_a_named_operation_says_what_it_did_beside_the_arithmetic() -> None:
    """The substitution shows numbers; the sentence shows the calculation.

    ``(0.001).cumulative_survival()`` is a number and a method name with
    nothing in between. The sentence is the eighty-four-period running
    product the reader is actually checking.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "decrement": [0.001]}))
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.combined_decrement = frame.decrement.projection.broadcast_to_periods()
    frame.survival = frame.combined_decrement.projection.cumulative_survival()
    substitution = _steps(_exported(frame)["survival@1"])[1]
    assert substitution["comment"] == (
        "cumulative survival from combined_decrement: a running product of "
        "one minus each period's decrement across 7 periods, opening at 1.0"
    )


def test_a_line_written_with_operators_carries_no_sentence() -> None:
    """The arithmetic is the meaning; saying it twice is noise on every line."""
    substitution = _steps(
        _exported(_a_book_with_a_portfolio_total())["expected_claims@1"]
    )[1]
    assert "comment" not in substitution


# --- a fold INSIDE a line is not the line being a fold -----------------------


def _a_book_with_each_policys_share_of_the_total() -> ActuarialFrame:
    """Return a line that is per-policy outside and a fold inside.

    ``af.share = af.claims / af.claims.sum()`` gives every policy its own
    share of the book. The denominator ran over every policy; the line did
    not, and each policy's answer is its own.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "claims": [100.0, 200.0, 700.0]})
    )
    frame.share = frame.claims / frame.claims.polars_native().sum()
    return frame


def _a_book_measured_against_its_own_mean() -> ActuarialFrame:
    """Return the other shape of the same thing: a whole-book mean inside."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "claims": [100.0, 200.0, 700.0]})
    )
    frame.excess = frame.claims - frame.claims.polars_native().mean()
    return frame


def _a_lookup_measured_against_a_book_mean() -> ActuarialFrame:
    """Return a composed lookup with a whole-book mean subtracted from it.

    Two operands, one of them folded. The rate the sampled policy's own age
    reads out of the base is that policy's; the baseline mean is the book's.
    """
    base = Table(
        name="mortality",
        source=pl.DataFrame({"age": [45, 55], "rate": [0.00123, 0.00456]}),
        dimensions={"age": "age"},
        value="rate",
    )
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "age": [45, 55], "baseline": [0.002, 0.004]})
    )
    frame.excess_rate = (
        base.lookup(age=frame.age) - frame.baseline.polars_native().mean()
    )
    return frame


def _a_book_with_a_share_of_its_own_product_group() -> ActuarialFrame:
    """Return an aggregate scoped to a group rather than to the book.

    ``.sum().over("product")`` totals the policies of one product. That is
    not a fold down the model points -- the line still answers once per
    policy -- and a walk-through that called it one would be naming rows
    the aggregate never touched.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3, 4],
                "product": ["term", "term", "wl", "wl"],
                "claims": [100.0, 300.0, 200.0, 200.0],
            }
        )
    )
    frame.share_of_product = (
        frame.claims
        / frame.claims.polars_native().sum().polars_native().over("product")
    )
    return frame


def test_a_fold_inside_a_line_is_not_the_line_being_a_fold() -> None:
    """Two fields of one node contradicted each other, and one was wrong.

    The step announced a fold down the model points while ``result`` two
    lines below printed the sampled policy's own share of the book. The
    node-level reading is the node's own outermost result, not whatever a
    descent found somewhere inside it.
    """
    steps = _steps(_exported(_a_book_with_each_policys_share_of_the_total())["share@1"])
    rendered = " ".join(step.get("comment", "") + " " + step["expr"] for step in steps)
    assert "This line folds down the model points" not in rendered
    assert steps[-1]["result"] == 0.1


def test_the_operand_that_folded_keeps_its_name_instead_of_a_policys_value() -> None:
    """The descent's answer still has a job: it says what may not be shown."""
    steps = _steps(_exported(_a_book_with_each_policys_share_of_the_total())["share@1"])
    substitution = steps[1]
    assert "claims" not in (substitution.get("values") or {})
    assert substitution["comment"].startswith(
        "claims: folded over all 3 model points in this export inside this line"
    )


def test_a_mean_the_whole_book_is_measured_against_reads_the_same_way() -> None:
    """``claims - claims.mean()`` is the nested fold the descent was built for."""
    steps = _steps(_exported(_a_book_measured_against_its_own_mean())["excess@1"])
    assert "This line folds down the model points" not in str(steps)
    assert "claims" in steps[1]["comment"]
    assert steps[-1]["result"] == pytest.approx(-233.333333)


def test_a_fold_names_only_the_operand_that_actually_folded() -> None:
    """Naming every dependency as folded says something false about most of them."""
    substitution = _steps(
        _exported(_a_lookup_measured_against_a_book_mean())["excess_rate@1"]
    )[1]
    assert substitution["comment"].startswith(
        "baseline: folded over all 2 model points"
    )
    assert "age" not in substitution["comment"]
    assert substitution["values"]["age"] == 45


def test_a_group_scoped_aggregate_is_not_a_fold_down_the_model_points() -> None:
    """An aggregate over one product is not an aggregate over the book.

    Announcing it as one would name two policies of another product as rows
    this line folded, which it never read.
    """
    steps = _steps(
        _exported(_a_book_with_a_share_of_its_own_product_group())["share_of_product@1"]
    )
    rendered = str(steps)
    assert "model points" not in rendered
    assert "claims" not in (steps[1].get("values") or {})
    # The key the aggregate was partitioned by is the sampled policy's own,
    # so it stands: it says which group's rows the total ran over.
    assert steps[1]["values"]["product"] == "term"
    assert steps[1]["comment"].startswith(
        "claims: folded over the rows of each group inside this line"
    )
    assert steps[-1]["result"] == 0.25


def test_a_window_this_build_cannot_read_names_no_population_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe that cannot answer must not answer with the widest population.

    The group/book discriminator reads the engine's own account of the
    expression. A build that cannot read that account -- a serialization
    this one does not speak -- knows nothing about which rows the aggregate
    folded, and "all 4 model points in this export" is a claim about a
    population rather than the absence of one. Answering it there printed
    two policies of the *other* product as rows this line folded: the exact
    falsehood the pin above exists to stop, restored by the failure route of
    the mechanism that stops it.

    So the unreadable answer is its own answer: the operand is named as
    folded and whose rows it folded is left unsaid.
    """

    def _refuses(*_args: object, **_kwargs: object) -> str:
        msg = "this build cannot read the engine's account of an expression"
        raise RuntimeError(msg)

    monkeypatch.setattr(ExprMetaNameSpace, "serialize", _refuses)
    steps = _steps(
        _exported(_a_book_with_a_share_of_its_own_product_group())["share_of_product@1"]
    )
    rendered = str(steps)
    assert "over all" not in rendered
    assert "model points in this export" not in rendered
    assert steps[1]["comment"].startswith("claims: folded inside this line")
    assert steps[-1]["result"] == 0.25


def test_a_build_whose_engine_renamed_its_windows_names_no_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A readable account whose window key moved reads as no window at all.

    The membership test above is only evidence of a window while the key it
    looks for is the key the engine writes. Rename the key and every
    expression answers the way one with no window in it answers, which hands
    the descent the export's whole population: a total over one product
    printed as a fold over every model point in the file -- the same
    falsehood, arriving by the route that was supposed to remove it.

    The discriminator is a control question. This build serializes an
    expression it wrote itself and knows to be a window, and where the key
    is absent from *that* account it knows the key has moved rather than
    that the expression has no window. Every window answer then degrades to
    the population this export cannot name.

    Rebinding the key is the stand-in for the rename; the pin above stays as
    the tripwire that says which spelling moved.
    """
    monkeypatch.setattr(calc_graph, "_A_WINDOW", "OverWindowExpr")
    steps = _steps(
        _exported(_a_book_with_a_share_of_its_own_product_group())["share_of_product@1"]
    )
    rendered = str(steps)
    assert "over all" not in rendered
    assert "model points in this export" not in rendered
    assert steps[1]["comment"].startswith("claims: folded inside this line")
    assert steps[-1]["result"] == 0.25


def test_the_control_question_answers_yes_for_the_key_this_build_looks_for() -> None:
    """The engine this build runs against writes the key this build reads."""
    assert calc_graph._the_engine_names_its_windows(calc_graph._A_WINDOW)  # noqa: SLF001


def test_the_control_question_answers_no_for_a_key_the_engine_never_writes() -> None:
    """An account of a known window that lacks the key says the key is wrong.

    This is the whole discriminator: the expression asked about is one this
    build constructed out of ``.sum().over()``, so there is no reading of a
    missing key other than "this build cannot read windows".
    """
    assert not calc_graph._the_engine_names_its_windows("OverWindowExpr")  # noqa: SLF001


def _a_line_whose_operand_hides_inside_a_method_name() -> ActuarialFrame:
    """Return a line where one column's name sits inside the text around it.

    ``a`` is a substring of ``mean``, and the operand the fold sentence
    tells the reader to go and look at is the one the substitution walks
    through on its way past.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "a": [1.0, 2.0, 3.0],
                "b": [10.0, 20.0, 30.0],
                "c": [4.0, 5.0, 6.0],
            }
        )
    )
    frame.mixed = frame.a * frame.b - frame.c.polars_native().mean()
    return frame


def test_an_operand_name_inside_another_word_is_not_substituted_there() -> None:
    """``c.mean()`` came out as ``c.me(1)n()`` under a whole-word comment.

    The step's own comment sends a reader to ``c``, and the operation that
    folded it had a number put in the middle of its name on the way.
    """
    nodes = _exported(_a_line_whose_operand_hides_inside_a_method_name())
    step = _steps(nodes["mixed@1"])[1]
    assert "c.mean()" in step["expr"]
    assert "me(" not in step["expr"]
    assert step["comment"].startswith("c: folded over all 3 model points")


# --- a direction only where there is one to read ----------------------------


def _a_projection_with_a_run_of_dates() -> ActuarialFrame:
    """Return a model carrying one boundary date per projection period."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "premium": [100.0]}))
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.period_start = frame.projection.period_dates()
    return frame


def test_a_run_of_dates_is_not_a_run_that_never_moves() -> None:
    """Six months of boundaries, and the shape line said the run was flat."""
    final = _steps(_exported(_a_projection_with_a_run_of_dates())["period_start@1"])[-1]
    assert final["shape"] == (
        "7 periods · first 2025-01-31 · last 2025-07-31 · no direction to read · "
        "no numbers in this run to count"
    )


def test_a_run_holding_no_numbers_counts_nothing_rather_than_zero() -> None:
    """A zero count of periods without a number is the ``flat`` species again.

    Nothing in that run is a number, so a count of the periods that are not
    reads as *every period is*, which is a positive claim about a column
    that has no numbers in it at all. It says it has none to count, the way
    the field beside it says it has no direction to read.
    """
    final = _steps(_exported(_a_projection_with_a_run_of_dates())["period_start@1"])[-1]
    assert "0 without a number" not in final["shape"]
    assert "0 negative" not in final["shape"]


def test_a_run_of_nulls_still_counts_the_periods_holding_no_number() -> None:
    """A run of holes is not a run with no numbers to count.

    "Every period holds no number" is a true and useful reading of a column
    that came back empty, and it is the pointer's first reading too, so the
    count stays where the periods are actually missing.
    """
    assert _counts_of_numbers([None, None]) == [
        "2 without a number (first at t=0)",
        "0 negative",
    ]


def _a_projection_with_a_banded_label_that_has_holes() -> ActuarialFrame:
    """Return a per-period banded label whose later periods hold nothing.

    A label column acquires holes the ordinary way -- a conditional with no
    value for the periods it does not band, a left join that does not reach
    every period -- so this is the shape a reading of non-numeric runs has
    to be true of rather than a contrived one. Three periods carry a band
    and four are empty.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "premium": [100.0]}))
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.band = (
        when(frame.month < 3)
        .then(pl.lit("early"))
        .otherwise(pl.lit(None, dtype=pl.String))
    )
    return frame


def test_a_label_run_with_a_hole_in_it_has_no_numbers_to_count_either() -> None:
    """Seven periods hold no number, and the line said that four did not.

    Whether a run holds numbers is one question and whether any period of
    it is empty is another, and the reading only depends on the first. Asked
    together, every non-numeric run carrying a single hole went back to the
    counting branch and had its numbers counted: "4 without a number" beside
    seven periods where none has one, and "0 negative" read off a run of
    strings, on the same line as a direction field saying -- correctly --
    that it has none to read.
    """
    final = _steps(
        _exported(_a_projection_with_a_banded_label_that_has_holes())["band@1"]
    )[-1]
    assert "no numbers in this run to count" in final["shape"]
    assert "without a number" not in final["shape"]
    assert "negative" not in final["shape"]


def test_the_empty_periods_of_a_label_run_are_named_as_what_they_are() -> None:
    """The half of that count which was true keeps its place, under its own name.

    Four of seven periods holding nothing is worth a reader's attention;
    "without a number" was simply the wrong name for it beside a run where
    no period has one.
    """
    final = _steps(
        _exported(_a_projection_with_a_banded_label_that_has_holes())["band@1"]
    )[-1]
    assert final["shape"] == (
        "7 periods · first early · last null · no direction to read · "
        "no numbers in this run to count · 4 empty periods (first at t=3)"
    )


def test_a_run_holding_numbers_and_holes_counts_them_as_it_always_did() -> None:
    """UNCHANGED: a run with a number in it is a run whose numbers count."""
    assert _counts_of_numbers([1.0, None, -2.0]) == [
        "1 without a number (first at t=1)",
        "1 negative (first at t=2)",
    ]


def test_one_empty_period_of_a_label_run_is_named_in_the_singular() -> None:
    """A count a reader reads aloud should be a count they can read aloud."""
    assert _counts_of_numbers(["early", None]) == [
        "no numbers in this run to count",
        "1 empty period (first at t=1)",
    ]


def test_a_run_of_booleans_has_no_direction_to_read_either() -> None:
    """A mask is not a level, and neither arrow is true of one."""
    assert _direction([True, False, True]) == "no direction to read"


def test_a_run_of_numbers_that_does_not_move_is_still_flat() -> None:
    """``flat`` keeps its meaning: a run of numbers that never moves."""
    assert _direction([2.0, 2.0, 2.0]) == "flat"


def test_a_hole_in_a_run_is_stepped_over_rather_than_read_as_a_turn() -> None:
    """NaN is a period with no number, which is what the docstring promised."""
    assert _direction([1.0, math.nan, 3.0]) == "↑"


# --- a pinned policy is measured against its own timeline -------------------


def _a_jagged_book_of_two_terms() -> ActuarialFrame:
    """Return two policies whose projections are different lengths.

    Jagged is the default whenever the horizon is a term column, so this is
    the ordinary shape rather than an exotic one: policy 1 runs four periods
    and policy 2 runs ten.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "term_months": [3, 9],
                "premium": [100.0, 200.0],
            }
        )
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
    )
    frame.premiums = frame.premium * (frame.month + 1)
    return frame


def test_a_pinned_policy_is_refused_a_period_its_own_timeline_never_reaches() -> None:
    """The document is an account of one policy, so the period is that policy's.

    Measured against the longest timeline instead, period 6 was accepted for
    a policy that stops at four -- and then every per-period node went silent
    while the envelope said the values had been read at period 6.
    """
    with pytest.raises(
        PeriodNotInTimelineError,
        match="the row sampled for policy '1' runs to 4 periods",
    ):
        _exported(
            _a_jagged_book_of_two_terms(),
            GraphExportConfig(policy_id="1", policy_id_column="policy_id", period=6),
        )


def test_a_pinned_policy_still_gets_every_period_its_own_timeline_reaches() -> None:
    """Saying no to period six is not saying no to period three."""
    nodes = _exported(
        _a_jagged_book_of_two_terms(),
        GraphExportConfig(policy_id="1", policy_id_column="policy_id", period=3),
    )
    assert nodes["premiums@1"]["value_sample"] == 400.0
    assert _steps(nodes["premiums@1"])[-1]["result"] == 400.0


def test_an_unpinned_export_still_measures_against_the_longest_timeline() -> None:
    """UNCHANGED, deliberately: with no policy pinned the frame is the subject.

    A period one policy reaches is a period this export can honestly show,
    so period 6 is accepted here even though the first row stops at four.
    """
    artifact = _artifact(_a_jagged_book_of_two_terms(), GraphExportConfig(period=6))
    assert artifact["enrichment"]["periods"] == [6]


def _a_jagged_book_carrying_one_id_on_two_rows() -> ActuarialFrame:
    """Return one policy number on two rows whose projections differ in length.

    A scenario axis is a cross-join, so one id over many rows is this
    framework's own native shape rather than an exotic one; rider rows and
    multiple coverages under one number reach it the same way. The first row
    runs four periods and the second ten.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 1],
                "term_months": [3, 9],
                "premium": [100.0, 200.0],
            }
        )
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
    )
    frame.premiums = frame.premium * (frame.month + 1)
    return frame


def test_a_duplicated_id_still_samples_a_period_its_own_row_reaches() -> None:
    """UNCHANGED, and the control: refusing period 6 is not refusing period 3.

    A duplicated id is not itself refused -- a scenario frame carries one on
    every row -- so a period the sampled row does reach still answers, from
    that row.
    """
    nodes = _exported(
        _a_jagged_book_carrying_one_id_on_two_rows(),
        GraphExportConfig(policy_id="1", policy_id_column="policy_id", period=3),
    )
    assert nodes["premiums@1"]["value_sample"] == 400.0
    assert _steps(nodes["premiums@1"])[-1]["result"] == 400.0


def test_the_refusal_names_the_row_it_measured_rather_than_the_policy() -> None:
    """One policy id on a cross-join runs to two lengths at once.

    The row the samples are read from runs four periods and the other row
    carrying that id runs ten, so "policy '1' runs to 4 periods" is a claim
    about the policy that the frame itself contradicts -- and the document
    it is refusing to write is an account of one row rather than of the
    policy. Both halves of the message are narrowed to what is true: the row
    sampled for that id, which is the first the frame carries.

    That there is a refusal here at all is the other half, and it is this
    test's too: measured against the longest of the matching rows instead,
    period 6 went through -- no refusal, an envelope saying the values were
    read at period 6, and every per-period node silent underneath it.
    """
    with pytest.raises(PeriodNotInTimelineError) as refusal:
        _exported(
            _a_jagged_book_carrying_one_id_on_two_rows(),
            GraphExportConfig(policy_id="1", policy_id_column="policy_id", period=6),
        )
    message = str(refusal.value)
    assert "the row sampled for policy '1' runs to 4 periods" in message
    assert "an account of that row" in message
    assert "an account of that policy" not in message


# --- a reading that needs a run long enough to mean something ---------------


def test_a_two_period_run_has_no_move_that_dominates_anything() -> None:
    """One move is always all of the movement, which points at nothing."""
    assert _hotspot([100.0, 1.0]) is None


# --- the voice reaches the document, not only the table ---------------------


def _a_model_joining_a_second_table() -> ActuarialFrame:
    """Return a model whose column arrived from the right side of a join."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "product_id": ["TERM", "WL"]})
    )
    return frame.join(
        pl.DataFrame({"product_id": ["TERM", "WL"], "loading": [0.05, 0.07]}),
        on="product_id",
        how="left",
    )


def _level_4() -> ActuarialFrame:
    """Return the reconciled lifelib model, run over its own model points.

    The largest model the package ships and the one every operation an
    actuary meets turns up in: 114 calculations, twenty-three of them
    columns that arrived from a second table.
    """
    from gaspatchio.tutorials import get_tutorials_dir

    path = get_tutorials_dir() / "level-4-lifelib" / "base" / "model.py"
    spec = importlib.util.spec_from_file_location("level_4_for_traces", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    points = pl.read_parquet(path.parent / "model_points.parquet")
    return cast("ActuarialFrame", module.main(ActuarialFrame(points)))


def test_a_column_that_arrived_from_a_join_says_so_in_its_own_document() -> None:
    """A join reads no column, so there was nothing to hang the sentence on.

    Twenty-three of level 4's columns arrive this way and every one of them
    was silent, with a sentence the specification states semantics for
    reachable only from the table it is written in.
    """
    # Pinned to one policy, because a join does not promise which row comes
    # back first and the sample is read from one row.
    nodes = _exported(
        _a_model_joining_a_second_table(),
        GraphExportConfig(policy_id="1", policy_id_column="policy_id"),
    )
    steps = _steps(nodes["loading@1"])
    assert steps[1]["comment"] == (
        "a column that arrived from a second table, matched on product_id "
        "under a left join"
    )
    assert steps[-1]["result"] == 0.05


def test_the_projection_axis_says_what_it_minted() -> None:
    """The other silent door: a column the model's own timeline created."""
    steps = _steps(_exported(_a_projection_that_turns_negative())["month@1"])
    assert steps[1]["comment"] == (
        "a column the model's own projection axis mints: monthly boundaries, "
        "whose configuration this node carries"
    )


def test_every_operation_the_format_names_speaks_in_a_whole_model() -> None:
    """The census, put through the export rather than through the table.

    ``sentence_for`` answering for an operation is not the same claim as a
    reader meeting that sentence in a document, and the two came apart on
    every operation whose line reads no column at all.
    """
    frame = _level_4()
    nodes = _exported(frame)
    silent = [
        node_id
        for node_id, tree in fold(frame).op_trees.items()
        if sentence_for(tree, None) is not None
        and (steps := _steps(nodes.get(node_id, {})))
        and not any(step.get("comment") for step in steps[:-1])
    ]
    assert silent == []
