# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every aggregation read states which periods it read (section 9).

"Does the model's reserve read the same periods as the workbook's column?"
is the timing half of a reconciliation, and five of seven independent builds
answered it with regular expressions over the ``formula`` text because the
edge did not say. An offset said which period a shifted value came from; a
cumulative sum, a remaining sum and a total all read ``AGGREGATION`` and
said nothing about which run.

So a direct read now states its window in the narrowing facet:
``periods: {from, to}`` on an aggregation read, each bound a whole number
of periods from the period being computed or the run's ``first`` or
``last``, and ``position: k`` on a read a literal ``list.get`` made. The
tests below hold that from four ends: the table section 9 prints, quoted
from each identifier's own attributes; the windows a composition and a
second read give; the schema and the validator; and the perturbation
vectors, where moving an operand outside its stated window must leave the
answer where it was -- on the producer here, and on the JAX engine in
``engines/jax/tests/test_period_windows.py``.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col, Lit
from gaspatchio.column import ExpressionProxy
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.edges import (
    AGGREGATION,
    Periods,
    Position,
    ReadClaim,
    ReadWay,
    claim_over,
    classify_reads,
)
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.rollforward import RollforwardBuilder, compile_rollforward
from gaspatchio.schedule import Schedule
from gaspatchio.schemas import load_schema
from tests.graph.test_operation_vectors import (
    _decode,
    _dtype,
    _register_assumptions,
    _register_compilation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_FACET: Final[str] = "gaspatchio_column_transformation"
_VECTORS: Final[Path] = (
    Path(__file__).resolve().parents[2] / "gaspatchio/schemas/vectors/windows.json"
)

FIRST_TO_NOW: Final[dict[str, Any]] = {"from": "first", "to": 0}
BEFORE_NOW: Final[dict[str, Any]] = {"from": "first", "to": -1}
NOW_TO_LAST: Final[dict[str, Any]] = {"from": 0, "to": "last"}
WHOLE_RUN: Final[dict[str, Any]] = {"from": "first", "to": "last"}


def _aggregation(periods: dict[str, Any]) -> dict[str, Any]:
    return {"type": "DIRECT", "subtype": "AGGREGATION", "periods": periods}


AGGREGATION_ALONE: Final[dict[str, Any]] = {"type": "DIRECT", "subtype": "AGGREGATION"}
TRANSFORMATION_ALONE: Final[dict[str, Any]] = {
    "type": "DIRECT",
    "subtype": "TRANSFORMATION",
}


def _book() -> ActuarialFrame:
    """Return two policies of unequal runs, a per-policy value and a position."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "q": [[0.1, 0.2, 0.3, 0.4], [0.05, 0.1]],
                "cf": [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0]],
                "i": [[0.01, 0.02, 0.03, 0.04], [0.05, 0.05]],
                "s": [0.5, 2.0],
                "k": [1, 0],
            }
        )
    )


def _reads(frame: ActuarialFrame, column: str) -> dict[str, list[dict[str, Any]]]:
    """Return the audit file's transformations for one column's reads, by source."""
    document = json.loads(
        GraphExporter(frame).export(include_source=False, versions="withheld")
    )
    (node,) = [n for n in document["nodes"] if n["column"] == column]
    return {
        read["source"]: read["transformations"]
        for read in node["facets"][_FACET]["reads"]
    }


# --- the table section 9 prints, one identifier at a time -------------------


@pytest.mark.parametrize(
    ("write", "source", "stated"),
    [
        pytest.param(
            lambda af: af.cf.cum_sum(), "cf", [_aggregation(FIRST_TO_NOW)], id="cum_sum"
        ),
        pytest.param(
            lambda af: af.cf.cum_sum(reverse=True),
            "cf",
            [_aggregation(NOW_TO_LAST)],
            id="cum_sum-reverse",
        ),
        pytest.param(
            lambda af: af.cf.cum_prod(),
            "cf",
            [_aggregation(FIRST_TO_NOW)],
            id="cum_prod",
        ),
        pytest.param(
            lambda af: af.cf.cum_prod(reverse=True),
            "cf",
            [_aggregation(NOW_TO_LAST)],
            id="cum_prod-reverse",
        ),
        pytest.param(
            lambda af: af.q.projection.cumulative_survival(start_at=None),
            "q",
            [_aggregation(FIRST_TO_NOW)],
            id="cumulative_survival",
        ),
        pytest.param(
            lambda af: af.q.projection.cumulative_survival(start_at=1.0),
            "q",
            [_aggregation(BEFORE_NOW)],
            id="cumulative_survival-start_at",
        ),
        pytest.param(
            lambda af: af.cf.projection.remaining_sum(),
            "cf",
            [_aggregation(NOW_TO_LAST)],
            id="remaining_sum",
        ),
        pytest.param(
            lambda af: af.cf.projection.prospective_value(discount_rate=af.i),
            "cf",
            [_aggregation(NOW_TO_LAST)],
            id="prospective_value-cashflows",
        ),
        pytest.param(
            lambda af: af.cf.projection.prospective_value(discount_rate=af.i),
            "i",
            [_aggregation(NOW_TO_LAST)],
            id="prospective_value-list-rate",
        ),
        pytest.param(
            lambda af: af.cf.list.sum(), "cf", [_aggregation(WHOLE_RUN)], id="sum"
        ),
        pytest.param(
            lambda af: af.cf.list.mean(), "cf", [_aggregation(WHOLE_RUN)], id="mean"
        ),
        pytest.param(
            lambda af: af.cf.list.min(), "cf", [_aggregation(WHOLE_RUN)], id="min"
        ),
        pytest.param(
            lambda af: af.cf.list.max(), "cf", [_aggregation(WHOLE_RUN)], id="max"
        ),
        pytest.param(
            lambda af: af.cf.excel.irr(), "cf", [_aggregation(WHOLE_RUN)], id="irr"
        ),
        pytest.param(
            lambda af: af.cf.list.reverse(),
            "cf",
            [_aggregation(WHOLE_RUN)],
            id="list.reverse",
        ),
        pytest.param(
            lambda af: af.cf.list.get(0),
            "cf",
            [{**TRANSFORMATION_ALONE, "position": 0}],
            id="list.get-first",
        ),
        pytest.param(
            lambda af: af.cf.list.get(-1),
            "cf",
            [{**TRANSFORMATION_ALONE, "position": -1}],
            id="list.get-last",
        ),
    ],
)
def test_each_aggregation_states_the_window_its_identifier_fixes(
    write: Callable[[ActuarialFrame], object],
    source: str,
    stated: list[dict[str, Any]],
) -> None:
    af = _book()
    af.answer = write(af)
    assert _reads(af, "answer")[source] == stated


@pytest.mark.parametrize(
    ("reverse", "window"), [(False, FIRST_TO_NOW), (True, NOW_TO_LAST)]
)
def test_a_recurrence_states_its_steps_window_and_none_for_its_opening(
    reverse: bool,  # noqa: FBT001 -- a parametrised flag
    window: dict[str, Any],
) -> None:
    """The step operands run with the recurrence; the opening has no periods."""
    af = _book()
    af.answer = af.cf.projection.accumulate(
        initial=af.s, multiplier=af.i, addend=af.cf, reverse=reverse
    )
    reads = _reads(af, "answer")
    assert reads["i"] == [_aggregation(window)]
    assert reads["cf"] == [_aggregation(window)]
    assert reads["s"] == [AGGREGATION_ALONE]


def test_a_forward_discount_factor_reads_the_rates_before_this_period() -> None:
    """11.1.30: d[t] multiplies the rates of 0..t-1; the period operand reads none."""
    af = _book().finance.discount_factor("i", "cf", "answer", method="forward")
    reads = _reads(af, "answer")
    assert reads["i"] == [_aggregation(BEFORE_NOW)]
    assert reads["cf"] == [AGGREGATION_ALONE]


def test_a_spot_discount_factor_folds_nothing_and_states_nothing() -> None:
    af = _book().finance.discount_factor("i", "cf", "answer", method="spot")
    assert all(
        transformations == [TRANSFORMATION_ALONE]
        for transformations in _reads(af, "answer").values()
    )


def test_a_per_policy_value_states_no_window_it_does_not_have() -> None:
    """A scalar rate has one value per policy, so no period of it to name."""
    af = _book()
    af.answer = af.cf.projection.prospective_value(discount_rate=af.s)
    reads = _reads(af, "answer")
    assert reads["cf"] == [_aggregation(NOW_TO_LAST)]
    assert reads["s"] == [AGGREGATION_ALONE]


def test_a_position_held_in_a_column_is_no_one_position() -> None:
    af = _book()
    af.answer = af.cf.list.get(af.k)
    reads = _reads(af, "answer")
    assert reads["cf"] == [TRANSFORMATION_ALONE]
    assert reads["k"] == [{"type": "INDIRECT", "subtype": "FILTER"}]


def test_a_read_of_the_period_being_computed_states_no_window() -> None:
    af = _book()
    af.answer = af.cf * af.i + af.s
    assert set(map(json.dumps, _reads(af, "answer").values())) == {
        json.dumps([TRANSFORMATION_ALONE])
    }


# --- quoted from the attributes, not derived from text ----------------------


def test_the_window_is_the_attribute_s_and_not_the_lowered_text_s() -> None:
    """The same fold under its two directions states two windows, by the flag alone."""
    forward = Call("cum_sum", (Col("x"),), (("reverse", False),))
    backward = Call("cum_sum", (Col("x"),), (("reverse", True),))
    assert classify_reads(forward)["x"] == claim_over(
        AGGREGATION, (Periods("first", 0),)
    )
    assert classify_reads(backward)["x"] == claim_over(
        AGGREGATION, (Periods(0, "last"),)
    )


def test_a_scan_that_states_no_direction_states_no_window() -> None:
    """11.1.9 has reverse always present; a tree without it is not guessed at."""
    assert classify_reads(Call("cum_sum", (Col("x"),)))["x"] == ReadClaim(AGGREGATION)


def test_a_recurrence_written_before_reverse_was_stated_runs_forward() -> None:
    """11.1.20: a document with no reverse holds the forward recurrence."""
    tree = Call("projection.accumulate", (Col("initial"), Col("m"), Col("a")))
    assert classify_reads(tree)["m"] == claim_over(AGGREGATION, (Periods("first", 0),))


def test_a_factor_form_prospective_value_states_no_window_for_its_factors() -> None:
    """11.1.21 states the rate form only; the factor form's discount is not guessed."""
    tree = Call(
        "projection.prospective_value",
        (Col("cf"), Col("df")),
        (("timing", "end_of_period"), ("discount_kind", "factor")),
    )
    reads = classify_reads(tree)
    assert reads["cf"] == claim_over(AGGREGATION, (Periods(0, "last"),))
    assert reads["df"] == ReadClaim(AGGREGATION)


# --- a read through two operations ------------------------------------------


@pytest.mark.parametrize(
    ("tree", "window"),
    [
        pytest.param(
            Call(
                "cum_sum",
                (Call("projection.previous_period", (Col("x"), Lit(0.0))),),
                (("reverse", False),),
            ),
            Periods("first", -1),
            id="cum_sum-of-previous_period",
        ),
        pytest.param(
            Call(
                "projection.previous_period",
                (Call("cum_sum", (Col("x"),), (("reverse", False),)), Lit(0.0)),
            ),
            Periods("first", -1),
            id="previous_period-of-cum_sum",
        ),
        pytest.param(
            Call(
                "list.get",
                (Call("cum_sum", (Col("x"),), (("reverse", False),)), Lit(-1)),
            ),
            Periods("first", "last"),
            id="last-period-of-cum_sum",
        ),
        pytest.param(
            Call("list.get", (Call("projection.remaining_sum", (Col("x"),)), Lit(0))),
            Periods("first", "last"),
            id="first-period-of-remaining_sum",
        ),
        pytest.param(
            Call("sum", (Call("cum_sum", (Col("x"),), (("reverse", False),)),)),
            Periods("first", "last"),
            id="sum-of-cum_sum",
        ),
        pytest.param(
            Call(
                "cum_sum",
                (Call("list.get", (Col("x"), Lit(2))),),
                (("reverse", False),),
            ),
            Position(2),
            id="position-inside-a-fold",
        ),
    ],
)
def test_a_composition_states_the_window_its_parts_compose_to(
    tree: Call, window: Periods | Position
) -> None:
    (way,) = classify_reads(tree)["x"].ways
    assert way.window == window


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(
            Call(
                "cum_sum",
                (Call("projection.next_period", (Col("x"), Lit(0.0))),),
                (("reverse", False),),
            ),
            id="a-fold-of-next-period",
        ),
        pytest.param(
            Call(
                "list.get",
                (Call("cum_sum", (Col("x"),), (("reverse", False),)), Lit(2)),
            ),
            id="a-middle-position-of-a-fold",
        ),
        pytest.param(
            Call(
                "cum_sum",
                (Call("list.get", (Col("x"), Col("k"))),),
                (("reverse", False),),
            ),
            id="a-column-position-inside-a-fold",
        ),
    ],
)
def test_a_composition_the_members_cannot_write_states_none(tree: Call) -> None:
    """No approximate window: a read of 1..t+1 is not written {first, +1}."""
    assert classify_reads(tree)["x"] == ReadClaim(AGGREGATION)


# --- a read through two windows ---------------------------------------------


def test_a_name_read_through_two_windows_states_both_strongest_first() -> None:
    """cum_sum(x) - x: the read of this period first, then the run to date."""
    af = _book()
    af.answer = af.cf.cum_sum() - af.cf
    assert _reads(af, "answer")["cf"] == [
        TRANSFORMATION_ALONE,
        _aggregation(FIRST_TO_NOW),
    ]


def test_two_aggregations_of_one_name_state_each_run_in_the_order_written() -> None:
    af = _book()
    af.answer = af.cf.projection.remaining_sum() + af.cf.cum_sum()
    assert _reads(af, "answer")["cf"] == [
        _aggregation(NOW_TO_LAST),
        _aggregation(FIRST_TO_NOW),
    ]


def test_two_positions_of_one_list_state_each_position() -> None:
    af = _book()
    af.answer = af.cf.list.get(-1) - af.cf.list.get(0)
    assert _reads(af, "answer")["cf"] == [
        {**TRANSFORMATION_ALONE, "position": -1},
        {**TRANSFORMATION_ALONE, "position": 0},
    ]


def test_one_window_read_twice_is_stated_once() -> None:
    af = _book()
    af.answer = af.cf.cum_sum() * af.cf.cum_sum()
    assert _reads(af, "answer")["cf"] == [_aggregation(FIRST_TO_NOW)]


def test_an_offset_is_unchanged_and_rides_the_entry_without_a_window() -> None:
    """A shifted read keeps its offset; two shifts still state none (section 9)."""
    af = _book()
    af.shifted = af.cf.projection.previous_period(fill_value=0.0)
    af.both = af.cf.projection.previous_period(
        fill_value=0.0
    ) + af.cf.projection.next_period(fill_value=0.0)
    assert _reads(af, "shifted")["cf"] == [{**TRANSFORMATION_ALONE, "offset": -1}]
    assert _reads(af, "both")["cf"] == [TRANSFORMATION_ALONE]


def test_an_indirect_read_states_no_window() -> None:
    """A test, a key and a selection's position read no value for a window to bound."""
    tree = Call(
        "cum_sum",
        (Call("list.get", (Col("x"), Call("list.get", (Col("y"), Lit(0))))),),
        (("reverse", False),),
    )
    assert classify_reads(tree)["y"] == ReadClaim(("INDIRECT", "FILTER"))


# --- a compiled rollforward -------------------------------------------------


def test_a_rollforward_reads_every_column_it_consumes_up_to_this_period() -> None:
    """Section 16 is a forward recurrence: the operand columns read {first, 0}."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {"initial": [100.0], "credit": [[10.0, 0.0]], "rate": [[0.5, 0.25]]}
        )
    )
    builder = RollforwardBuilder(
        states={"fund": frame["initial"]},
        schedule=Schedule.from_calendar_grid(
            start_date=datetime.date(2024, 1, 31), n_periods=2, frequency="1M"
        ),
        track_increments=False,
    )
    builder["fund"].add(frame["credit"], label="credit")
    builder["fund"].charge(frame["rate"], label="fee")
    frame.answer = compile_rollforward(builder).expr_for("fund")
    document = json.loads(GraphExporter(frame).export(include_source=False))
    (machine,) = [n for n in document["nodes"] if n["kind"] == "rollforward"]
    reads = {
        read["source"]: read["transformations"]
        for read in machine["facets"][_FACET]["reads"]
    }
    assert reads["credit"] == [_aggregation(FIRST_TO_NOW)]
    assert reads["rate"] == [_aggregation(FIRST_TO_NOW)]
    assert reads["initial"] == [AGGREGATION_ALONE]
    assert reads["state:fund@eop"] == [TRANSFORMATION_ALONE]


# --- what the record says, and what reads it --------------------------------


def test_the_windows_are_outside_the_canonical_bytes() -> None:
    """A facet member moves no digest: the model is the calculation it was."""
    af = _book()
    af.answer = af.cf.cum_sum() + af.cf.projection.remaining_sum()
    document = json.loads(GraphExporter(af).export())
    for node in document["nodes"]:
        node.get("facets", {}).pop(_FACET, None)
    assert (
        json.loads(GraphExporter(af).export())["graph_fingerprint"]
        == (document["graph_fingerprint"])
    )
    assert validate_artifact(GraphExporter(af).export(), deep=True).ok


def _artifact_with(narrowing: dict[str, Any]) -> dict[str, Any]:
    af = _book()
    af.answer = af.cf.cum_sum()
    document: dict[str, Any] = json.loads(GraphExporter(af).export())
    (node,) = [n for n in document["nodes"] if n["column"] == "answer"]
    node["facets"][_FACET]["reads"][0]["transformations"] = [narrowing]
    return document


@pytest.mark.parametrize(
    "narrowing",
    [
        pytest.param(
            {"type": "DIRECT", "subtype": "TRANSFORMATION", "periods": FIRST_TO_NOW},
            id="periods-beside-a-transformation",
        ),
        pytest.param(
            {"type": "INDIRECT", "subtype": "CONDITIONAL", "position": 0},
            id="position-beside-an-indirect-read",
        ),
        pytest.param(
            {**_aggregation(FIRST_TO_NOW), "position": 0},
            id="periods-and-position-together",
        ),
        pytest.param(
            _aggregation({"from": "first", "to": 0.5}), id="a-bound-that-is-no-period"
        ),
        pytest.param(_aggregation({"from": "first"}), id="a-window-with-one-end"),
    ],
)
def test_the_schema_refuses_a_window_the_specification_does_not_define(
    narrowing: dict[str, Any],
) -> None:
    validator = jsonschema.Draft202012Validator(load_schema())
    assert list(validator.iter_errors(_artifact_with(narrowing)))


def test_the_schema_accepts_every_window_the_producer_writes() -> None:
    validator = jsonschema.Draft202012Validator(load_schema())
    af = _book()
    af.a = af.cf.cum_sum() - af.cf
    af.b = af.cf.list.get(-1)
    af.c = af.q.projection.cumulative_survival(start_at=1.0)
    assert not list(validator.iter_errors(json.loads(GraphExporter(af).export())))


@pytest.mark.parametrize(
    "periods",
    [{"from": 0, "to": -1}, {"from": "last", "to": 0}, {"from": 2, "to": "first"}],
)
def test_the_validator_refuses_a_window_that_holds_no_period(
    periods: dict[str, Any],
) -> None:
    report = validate_artifact(json.dumps(_artifact_with(_aggregation(periods))))
    assert not report.ok
    assert any("starts after it ends" in finding.message for finding in report.findings)


def test_the_validator_accepts_an_opening_period_that_reads_nothing_yet() -> None:
    """{first, -1} reads no period at t = 0 and one at t = 1: a run, not a refusal."""
    report = validate_artifact(json.dumps(_artifact_with(_aggregation(BEFORE_NOW))))
    assert report.ok


# --- the perturbation vectors, on this engine -------------------------------


def _moved_cases() -> list[dict[str, Any]]:
    return [
        case
        for case in json.loads(_VECTORS.read_text())["cases"]
        if "perturbation" in case
    ]


def _by_id() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in json.loads(_VECTORS.read_text())["cases"]}


def _frame_of(case: dict[str, Any]) -> ActuarialFrame:
    """Return the case's book with its answer written the way a formula is."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                name: pl.Series(
                    name, _decode(item["values"]), dtype=_dtype(item["dtype"])
                )
                for name, item in case["inputs"].items()
            }
        )
    )
    _register_assumptions(case)
    _register_compilation(case, frame)
    frame.answer = ExpressionProxy._from_node(op_node_from_json(case["expr"]), frame)  # noqa: SLF001
    return frame


def _window_cells(window: dict[str, Any], period: int, length: int) -> range:
    """Return the operand periods the window covers when the answer is at ``period``."""
    if "position" in window:
        at = (
            window["position"]
            if window["position"] >= 0
            else length + window["position"]
        )
        return range(at, at + 1)

    def at(bound: object) -> int:
        if bound == "first":
            return 0
        if bound == "last":
            return length - 1
        assert isinstance(bound, int)
        return period + bound

    low = max(at(window["periods"]["from"]), 0)
    high = min(at(window["periods"]["to"]), length - 1)
    return range(low, high + 1)


def _holds_the_window(case: dict[str, Any], base: list[Any], moved: list[Any]) -> None:
    """Assert ``moved`` departs from ``base`` only where the window lets it."""
    perturbation = case["perturbation"]
    policy, period = perturbation["policy"], perturbation["period"]
    length = len(case["inputs"][perturbation["operand"]]["values"][policy])
    for other, (was, now) in enumerate(zip(base, moved, strict=True)):
        if other != policy:
            assert now == was, f"policy {other} moved with policy {policy}'s operand"
    was, now = base[policy], moved[policy]
    answers = (
        list(enumerate(zip(was, now, strict=True)))
        if isinstance(was, list)
        else [(None, (was, now))]
    )
    inside_moved = False
    inside_any = False
    for at, (before, after) in answers:
        covered = period in _window_cells(perturbation["window"], at or 0, length)
        if not covered:
            assert after == before, f"period {at} moved from outside its window"
            continue
        inside_any = True
        inside_moved = inside_moved or after != before
    assert inside_moved or not inside_any, "nothing inside the window moved"


@pytest.mark.parametrize("case", _moved_cases(), ids=lambda case: case["id"])
def test_the_producer_states_the_window_the_vector_holds(case: dict[str, Any]) -> None:
    """The window a moved case is held to is the one the base's export states."""
    base = _by_id()[case["perturbation"]["of"]]
    document = json.loads(GraphExporter(_frame_of(base)).export(include_source=False))
    operand = case["perturbation"]["operand"]
    stated = [
        {key: narrowing[key] for key in ("periods", "position") if key in narrowing}
        for node in document["nodes"]
        for read in node.get("facets", {}).get(_FACET, {}).get("reads", [])
        if read["source"] == operand
        for narrowing in read["transformations"]
    ]
    assert case["perturbation"]["window"] in stated


@pytest.mark.parametrize("case", _moved_cases(), ids=lambda case: case["id"])
def test_moving_an_operand_outside_its_window_moves_nothing_on_polars(
    case: dict[str, Any],
) -> None:
    base = _by_id()[case["perturbation"]["of"]]
    before = _frame_of(base).collect()["answer"].to_list()
    after = _frame_of(case).collect()["answer"].to_list()
    _holds_the_window(case, before, after)
    _holds_the_window(case, base["expected"]["values"], case["expected"]["values"])


def test_every_windowed_identifier_has_a_perturbation_vector() -> None:
    """One per row of section 9's table, the rollforward and a composition included."""
    covered = {
        identifier for case in _moved_cases() for identifier in case["covers"]
    } | {
        identifier
        for case in _moved_cases()
        for identifier in case.get("structural_covers", [])
    }
    assert covered >= {
        "cum_sum",
        "cum_prod",
        "projection.cumulative_survival",
        "projection.accumulate",
        "projection.remaining_sum",
        "projection.prospective_value",
        "sum",
        "mean",
        "min",
        "max",
        "excel.irr",
        "list.reverse",
        "finance.discount_factor",
        "list.get",
        "rollforward",
    }


def test_a_vector_whose_answer_moves_outside_its_window_is_caught() -> None:
    """The check is not vacuous: a fold reading one period further fails it."""
    case = next(c for c in _moved_cases() if c["id"] == "window-cum_sum-moved")
    base = _by_id()[case["perturbation"]["of"]]["expected"]["values"]
    leaked = json.loads(json.dumps(case["expected"]["values"]))
    leaked[0][1] += 1.0
    with pytest.raises(AssertionError, match="outside its window"):
        _holds_the_window(case, base, leaked)


def test_a_claim_over_no_window_is_the_one_way_read() -> None:
    assert claim_over(AGGREGATION, (None,)) == ReadClaim(AGGREGATION)
    assert claim_over(AGGREGATION, (Periods("first", 0),)).ways == (
        ReadWay("AGGREGATION", Periods("first", 0)),
    )
