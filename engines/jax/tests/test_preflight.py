# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What refuses before anything is compiled, and what the report says about it."""

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.engines.protocol import EngineResult, FrameSink, digest_of_inputs
from gaspatchio.engines.report import EngineRefusal, RunReport
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import invocation

if TYPE_CHECKING:
    from gaspatchio_jax.vectors import Invocation


def _sum_of_two() -> object:
    return invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "i64", "values": [1, 2]},
            "b": {"dtype": "i64", "values": [10, 20]},
        },
        "i64",
    )


def _unpack(one: object) -> tuple[dict, pl.DataFrame]:
    """Return one invocation's document and book, for a call that takes both."""
    return one.document, one.inputs


def _sealed_again(document: dict) -> dict:
    """Return a hand-extended document with its digests taken again."""
    from gaspatchio_jax.vectors import (
        _sealed,
    )

    return _sealed(document)


def _run(document: dict, inputs: pl.DataFrame) -> EngineRefusal:
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(document, inputs, FrameSink())
    return refused.value


def test_a_book_missing_a_column_the_artifact_reads_refuses_by_name() -> None:
    one = _sum_of_two()
    report = _run(one.document, one.inputs.drop("b")).report
    assert report.refusals[0].group == "inputs"
    assert report.refusals[0].where == "b"
    assert report.closing_sentence() == "Nothing was computed."


def test_a_column_in_the_wrong_type_refuses_with_both_types_named() -> None:
    one = _sum_of_two()
    wrong = one.inputs.with_columns(pl.col("b").cast(pl.Float64))
    report = _run(one.document, wrong).report
    assert "as i64" in report.refusals[0].what
    assert "as f64" in report.refusals[0].what


def test_a_null_in_a_column_a_node_reads_refuses_with_its_row_count() -> None:
    one = _sum_of_two()
    nulled = one.inputs.with_columns(
        pl.when(pl.col("a") == 1).then(None).otherwise(pl.col("a")).alias("a")
    )
    report = _run(one.document, nulled).report
    assert report.refusals[0].count == 1
    # 11.1.13: a null and a NaN are two absences, and fill_null is the move.
    assert report.refusals[0].clause == "11.1.13"


def test_every_finding_travels_in_one_report_rather_than_the_first_one_found() -> None:
    one = _sum_of_two()
    report = _run(one.document, pl.DataFrame({"c": [1, 2]})).report
    assert {refusal.where for refusal in report.refusals} == {"a", "b"}


def test_an_audit_profile_refuses_by_naming_the_profile_to_export() -> None:
    one = _sum_of_two()
    document = copy.deepcopy(one.document)
    document["profile"] = "audit"
    report = _run(document, one.inputs).report
    assert any("executable" in refusal.move for refusal in report.refusals)


def test_a_document_whose_digests_do_not_reproduce_refuses_in_the_tree_group() -> None:
    one = _sum_of_two()
    document = copy.deepcopy(one.document)
    document["nodes"][-1]["local_fingerprint"] = "sha256:" + "0" * 64
    report = _run(document, one.inputs).report
    assert all(refusal.group == "tree" for refusal in report.refusals)


def _refused_on(af: object, where: str) -> list:
    """Return the refusals a run of ``af`` on this engine makes at ``where``."""
    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")
    return [one for one in refused.value.report.refusals if one.where == where]


def test_a_column_written_into_the_plan_is_refused_with_its_own_move() -> None:
    """The move is the line to write through the frame, and nothing general."""
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(pl.lit(0.0).alias("commission"))  # noqa: SLF001
    af.net = af.premium - af.commission

    [hole] = _refused_on(af, "/nodes/commission@2")

    assert "written straight into the query plan" in hole.what
    assert "af['commission'] = ..." in hole.move
    assert "payloads" not in hole.move


def test_a_column_rebuilt_from_another_frame_is_refused_with_its_own_move() -> None:
    """The move is the door that keeps the calculation, and nothing general."""
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))
    af.reserve = af.premium * 0.5
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0

    [hole] = _refused_on(wrapped, "/nodes/reserve")

    assert "calculation on another frame" in hole.what
    assert "ActuarialFrame(df, continue_from=af)" in hole.move
    assert "payloads" not in hole.move


def test_a_column_nothing_recorded_is_refused_with_the_move_that_records_it() -> None:
    """Exporting again records nothing, so that is not the move the report names."""
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))
    af._df = af._df.with_columns(  # noqa: SLF001
        (pl.col("premium") * 0.1).alias("loading")
    )
    af.charged = af.premium + af["loading"]

    [hole] = _refused_on(af, "/nodes/loading")

    assert "nothing recorded how it was made" in hole.what
    assert "af['loading'] = ..." in hole.move
    assert "model points" in hole.move
    assert "payloads" not in hole.move


def test_a_per_period_node_is_lowered_and_broadcasts_by_11_1_18() -> None:
    """The shape that refused as a whole class now runs, and broadcasts.

    A per-policy value beside a per-period one repeats to that policy's own
    length, which is 11.1.18's own sentence -- and what stood here before was
    the blanket refusal of every list-shaped node, which is lifted.
    """
    per_period = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "list[f64]", "values": [[1.0, 2.0], [3.0]]},
            "b": {"dtype": "f64", "values": [1.0, 10.0]},
        },
        "list[f64]",
    )
    statuses = JaxEngine().validate_tree(per_period.document)
    assert all(status.status == "lowered" for status in statuses)
    answered = JaxEngine().run(per_period.document, per_period.inputs, FrameSink())
    assert answered.columns["answer"].to_list() == [[2.0, 3.0], [13.0]]


def _date_against_a_number() -> object:
    return invocation(
        {
            "op": "binop",
            "kind": "lt",
            "left": {"op": "col", "name": "d"},
            "right": {"op": "col", "name": "n"},
        },
        {
            "d": {"dtype": "date", "values": ["2024-01-31"]},
            "n": {"dtype": "i64", "values": [5]},
        },
        "bool",
    )


def _figures_keeping_none() -> object:
    return invocation(
        {
            "op": "call",
            "name": "round_sig_figs",
            "args": [{"op": "col", "name": "x"}],
            "attrs": {"digits": 0},
        },
        {"x": {"dtype": "f64", "values": [1234.5]}},
        "f64",
    )


def _a_banding_over_dates() -> object:
    return invocation(
        {
            "op": "call",
            "name": "cut",
            "args": [
                {"op": "col", "name": "d"},
                {"op": "lit", "values": [1, 2]},
                {"op": "lit", "values": ["low", "mid", "high"]},
            ],
            "attrs": {"left_closed": False, "include_breaks": False},
        },
        _a_date_column(),
        "str",
    )


def _a_date_parsed_from_a_number() -> object:
    return invocation(
        {
            "op": "call",
            "name": "str.to_date",
            "args": [{"op": "col", "name": "n"}],
            "attrs": {"format": "%Y-%m-%d", "strict": True, "exact": True},
        },
        {"n": {"dtype": "i64", "values": [20240131]}},
        "date",
    )


def _a_date_column() -> dict[str, dict[str, object]]:
    return {"d": {"dtype": "date", "values": ["2024-01-31"]}}


def _membership_over_dates() -> object:
    return invocation(
        {
            "op": "call",
            "name": "is_in",
            "args": [
                {"op": "col", "name": "d"},
                {"op": "lit", "values": [1, 2]},
            ],
            "attrs": {"nulls_equal": False},
        },
        _a_date_column(),
        "bool",
    )


def _substitution_over_dates() -> object:
    return invocation(
        {
            "op": "call",
            "name": "replace",
            "args": [
                {"op": "col", "name": "d"},
                {"op": "lit", "values": [1]},
                {"op": "lit", "values": [2]},
            ],
            "attrs": {},
        },
        _a_date_column(),
        "date",
    )


def _a_date_filled_with_a_number() -> object:
    return invocation(
        {
            "op": "call",
            "name": "fill_null",
            "args": [{"op": "col", "name": "d"}, {"op": "lit", "value": 0}],
            "attrs": {},
        },
        _a_date_column(),
        "date",
    )


@pytest.mark.parametrize(
    ("build", "inside"),
    [
        (_date_against_a_number, "infers no ordering"),
        (_figures_keeping_none, "digits=0"),
        (_membership_over_dates, "is_in is written over a calendar date"),
        (_substitution_over_dates, "replace is written over a calendar date"),
        (_a_date_filled_with_a_number, "infers no ordering"),
        (_a_banding_over_dates, "cut is written over a calendar date"),
        (_a_date_parsed_from_a_number, "str.to_date is written over a whole number"),
    ],
    ids=[
        "date-against-a-number",
        "figures-keeping-none",
        "membership-over-dates",
        "substitution-over-dates",
        "a-date-filled-with-a-number",
        "a-banding-over-dates",
        "a-date-parsed-from-a-number",
    ],
)
def test_validate_tree_and_run_refuse_the_same_invocations(build, inside) -> None:
    """A status is about an invocation, so the two halves cannot disagree."""
    one = build()
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1, refused
    assert inside in (refused[0].condition or "")

    report = _run(one.document, one.inputs).report
    assert report.refusals
    assert report.refusals[0].clause == refused[0].clause
    assert report.closing_sentence() == "Nothing was computed."


def test_a_domain_refusal_names_the_node_and_the_clause_it_rests_on() -> None:
    report = _run(*_unpack(_date_against_a_number())).report
    refusal = report.refusals[0]
    assert refusal.group == "tree"
    assert refusal.where == "answer@1"
    assert refusal.clause == "11.1.26"
    assert "answer@1 · " in report.render()


def test_every_refusal_met_while_lowering_travels_in_one_report() -> None:
    """Two nodes whose answer is not the type they record are two findings.

    A disagreement between a record's declared type and what its own tree
    produces is the one refusal the inspection stage cannot reach -- it needs
    the operand carriers, which come together only while lowering -- so it is
    what this pins the collecting on.
    """
    one = _sum_of_two()
    document = copy.deepcopy(one.document)
    for name, dtype in (("other", "date"), ("third", "str")):
        node = copy.deepcopy(document["nodes"][-1])
        node["id"] = f"{name}@1"
        node["column"] = name
        node["dtype"] = dtype
        document["nodes"].append(node)
        for read in node["reads"]:
            document["edges"].append(
                {"source": read, "target": node["id"], "relationship": "DIRECT"}
            )
    report = _run(_sealed_again(document), one.inputs).report
    assert {refusal.where for refusal in report.refusals} == {"other@1", "third@1"}
    assert all(refusal.group == "tree" for refusal in report.refusals)
    assert report.closing_sentence() == "Nothing was computed."


def test_a_null_in_a_column_nothing_reads_is_reported_and_not_refused() -> None:
    one = _sum_of_two()
    book = one.inputs.with_columns(pl.Series("spare", [None, 3], dtype=pl.Int64))
    result = JaxEngine().run(one.document, book, FrameSink())
    assert result.report.refusals == ()
    assert any("spare" in note for note in result.report.notes)
    assert (
        "Reported, not refused:"
        in RunReport(refusals=(), notes=result.report.notes).render()
    )


def test_the_inputs_digest_is_taken_over_the_artifact_s_own_columns() -> None:
    """A book with a column nothing reads is the same book."""
    one = _sum_of_two()
    wider = one.inputs.with_columns(pl.Series("spare", [7, 8], dtype=pl.Int64))
    plain = JaxEngine().run(one.document, one.inputs, FrameSink())
    padded = JaxEngine().run(one.document, wider, FrameSink())
    assert padded.manifest.inputs_digest == plain.manifest.inputs_digest
    assert plain.manifest.inputs_digest == digest_of_inputs(one.inputs, ["a", "b"])


def test_validate_tree_reads_no_book_and_answers_for_every_node() -> None:
    one = _sum_of_two()
    statuses = JaxEngine().validate_tree(one.document)
    assert {status.node_id for status in statuses} == {"a", "b", "answer@1"}
    assert all(status.status == "lowered" for status in statuses)


# One column of each carrier, for the sweep below. Two rows, so a comparison
# built over two of them is true on one row and false on the other -- which is
# what makes an indicator operand worth computing with.
_A_COLUMN_OF = {
    "i64": {"dtype": "i64", "values": [3, 7]},
    "f64": {"dtype": "f64", "values": [3.5, 1.5]},
    "bool": {"dtype": "bool", "values": [True, False]},
    "date": {"dtype": "date", "values": ["2024-01-31", "2023-06-01"]},
    "code": {"dtype": "str", "values": ["A", "B"]},
}

# The two columns every indicator operand is a comparison of.
_LEFT_OF_THE_COMPARISON = {"dtype": "i64", "values": [1, 5]}
_RIGHT_OF_THE_COMPARISON = {"dtype": "i64", "values": [3, 2]}

# What the sweep cannot build a form for on its own. ``cut``, ``is_in`` and
# ``replace`` take a sequence literal whose members have to be of the value's
# own kind, and ``str.to_date`` needs text the stated format actually parses --
# all four are pinned by hand in the parametrised test above. ``to_text``
# answers over every carrier, so there is no wrong carrier to offer it; its
# operand condition is pinned in tests/test_coverage.py and in the manifest.
# The three reads that select a row need a basis travelling with the document
# before their lowering has any opinion at all, so their operand domains are
# swept by hand against a real payload in tests/test_lowerings_tables.py.
# The twelve after them are the axis family: what a schedule reading takes as
# an operand is the column its own *kind* is sized or anchored from, so there
# is no form to build without a recipe travelling with the document. They are
# swept by hand in tests/test_lowerings_projection.py, against real recipes of
# all three kinds.
_AXIS_FAMILY = frozenset(
    {
        "projection_set",
        "projection_frame.period_dates",
        "projection_frame.year_fractions",
        "projection_frame.t_years",
        "projection_frame.anniversary_mask",
        "schedule.period_dates",
        "schedule.per_policy_period_dates",
        "schedule.per_policy_period_count",
        "schedule.year_fractions",
        "schedule.anniversary_mask",
        "schedule.is_in_force",
        "schedule.contract_boundary",
    }
)

# And the four whose own attributes are values no sweep can invent: a curve
# is named by a recipe's whole digest, and a duration, an interval and a
# compounding basis are written in spellings this engine reads rather than in
# a set it could pick the first of. Each is pinned by hand in
# tests/test_lowerings_projection.py against a real one.
_ATTRIBUTES_NOBODY_CAN_INVENT = frozenset(
    {
        "curve.spot_rate",
        "curve.discount_factor",
        "date.offset_by",
        "date.date_ranges",
    }
)

# And the one whose operand domain is a *disjunction*: 11.1.30 states the
# forms with at least one per-period operand, which admits a per-period rate
# against a per-policy period and a per-policy rate against a per-period one
# and neither of the two per-policy. A shape domain states one set per
# position and cannot say "one of these two"; both admitted forms and the
# refused pair are pinned by hand in tests/test_lowerings_projection.py.
_A_DISJUNCTION = frozenset({"finance.discount_factor", "projection.accumulate"})

# And the one whose arguments are not its operands at all. Section 12.1 says
# outright that a rollforward door carries the *compilation's* own operand run
# rather than a call's argument list, so neither how many operands it has nor
# what any of them may be is the call's to state: both are facts about the
# machine in the facet, and 16.1's rules over them are enforced against that
# body. A sweep building forms from the registration would be sweeping an
# argument list nobody writes. The operand rules themselves are pinned in
# tests/test_rollforward.py and by the kit's own ``compilation-*`` cases.
_THE_MACHINE_S_OWN = frozenset({"rollforward.state"})

_SWEPT_BY_HAND = (
    frozenset(
        {
            "cut",
            "is_in",
            "replace",
            "str.to_date",
            "to_text",
            "lookup",
            "mortality.at",
            "join",
        }
    )
    | _AXIS_FAMILY
    | _ATTRIBUTES_NOBODY_CAN_INVENT
    | _A_DISJUNCTION
    | _THE_MACHINE_S_OWN
)

# The registrations whose operand count is not the engine's to state: 11.1.24
# pairs one operand with each key column of the processed table and a table
# may be keyed on any number of them, and a schedule reading's operand is
# whatever its own kind is sized or anchored from.
_VARIADIC = frozenset({"lookup", "mortality.at"}) | _AXIS_FAMILY | _THE_MACHINE_S_OWN

_BINARY_OPERATORS = frozenset(
    {
        "add",
        "sub",
        "mul",
        "div",
        "floordiv",
        "mod",
        "pow",
        "lt",
        "le",
        "gt",
        "ge",
        "eq",
        "ne",
        "and",
        "or",
    }
)

# 11.1.25's seven, which are the ones a stored indicator can stand as an
# operand of (11.1.26).
_ARITHMETIC = ("add", "sub", "mul", "div", "floordiv", "mod", "pow")


def _swept_registrations() -> list[tuple[str, int, int, str]]:
    """Return every (identifier, arity, operand position, carrier) to sweep.

    Every arity a registration declares, not only the smallest: ``clip``'s
    third operand is a bound like its second and is swept like one.

    Raises:
        AssertionError: If a registration that takes operands declares no
            operand domain at all. That is the widest claim a row can make --
            *this identifier, whatever you hand it* -- and it is exactly the
            shape a declaration wider than its lowering takes, so it fails
            here rather than being passed over. An operation with no operands
            has no domain to state: 11.1.2's join names its key as an
            attribute and its node reads nothing, and a carrier set on that
            registration would be describing operands nobody can write. So
            does a rollforward door, for the other reason -- its arguments
            are the compilation's operand run and not the call's (§12.1), so
            a domain stated here would be a claim about an argument list
            nobody writes, and 16.1's own rules are enforced against the
            machine instead.

    """
    from gaspatchio_jax.capability import ANY_CARRIER
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    found: list[tuple[str, int, int, str]] = []
    for name, (_lowering, capability) in sorted(LOWERINGS.items()):
        assert (
            capability.carriers is not None
            or capability.arity == (0,)
            or name in _THE_MACHINE_S_OWN
        ), name
        # Before the skip, not after it: a guard that only reaches the
        # registrations the sweep can build forms for is a guard the next
        # unpinned registration walks straight past. The two exemptions are
        # named rather than inferred -- a read whose operand count is the
        # basis's own key-column count has no count to state, and says as
        # much in its note.
        assert capability.arity is not None or name in _VARIADIC, name
        if name in _SWEPT_BY_HAND:
            continue
        found.extend(
            (name, count, position, carrier)
            for count in capability.arity
            for position in range(count)
            for carrier in sorted(ANY_CARRIER)
        )
    return found


def _indicator_forms() -> list[tuple[str, tuple[int, ...]]]:
    """Return each arithmetic operator with one and with two indicator operands."""
    return [
        (name, positions) for name in _ARITHMETIC for positions in ((0,), (1,), (0, 1))
    ]


def _a_comparison(kind: str, left: str, right: str) -> dict[str, object]:
    """Return one comparison tree, which is a stored indicator where it stands."""
    return {
        "op": "binop",
        "kind": kind,
        "left": {"op": "col", "name": left},
        "right": {"op": "col", "name": right},
    }


def _tree_of(name: str, args: list[dict[str, object]]) -> dict[str, object]:
    """Return the operation tree one identifier writes over these operands."""
    from gaspatchio_jax.coverage import _admitted_attrs
    from gaspatchio_jax.lowerings import LOWERINGS

    if name in _BINARY_OPERATORS:
        return {"op": "binop", "kind": name, "left": args[0], "right": args[1]}
    if name == "when_then":
        return {
            "op": "when_then",
            "cond": args[0],
            "then": args[1],
            "otherwise": args[2],
        }
    return {
        "op": "call",
        "name": name,
        "args": args,
        "attrs": _admitted_attrs(LOWERINGS[name][1]),
    }


def _polars_answer(
    tree: dict[str, object], inputs: dict[str, dict[str, object]]
) -> pl.Series | None:
    """Return what the producer answers for this tree, or None where it refuses.

    Through the producer's own assignment door rather than a hand-written
    Polars expression per identifier: what this comparison is worth is that it
    is the *other* engine's answer, and an expression written here to match
    would be this engine's answer twice.
    """
    from gaspatchio import ActuarialFrame
    from gaspatchio.column import ExpressionProxy
    from gaspatchio.column.condition_expression import ConditionExpression
    from gaspatchio.engines.format import BinOp, op_node_from_json

    columns = {
        name: pl.Series(name, _read_dates(item), dtype=_polars_type(item["dtype"]))
        for name, item in inputs.items()
    }
    frame = ActuarialFrame(pl.DataFrame(columns))
    node = op_node_from_json(tree)
    try:
        if isinstance(node, BinOp) and node.op in ("lt", "le", "gt", "ge", "eq", "ne"):
            frame.answer = ConditionExpression(node, frame)
        else:
            frame.answer = ExpressionProxy._from_node(node, frame)  # noqa: SLF001
        return frame.collect()["answer"]
    except Exception:  # noqa: BLE001 -- the producer refusing is an answer here
        return None


_POLARS_TYPE = {
    "i64": pl.Int64,
    "f64": pl.Float64,
    "bool": pl.Boolean,
    "date": pl.Date,
    "str": pl.String,
}


def _polars_type(dtype: str) -> object:
    """Return the Polars type one of section 10's names stands for."""
    if dtype.startswith("list["):
        return pl.List(_polars_type(dtype[len("list[") : -1]))
    return _POLARS_TYPE[dtype]


def _read_dates(item: dict) -> list:
    """Return one column's written values, every ISO calendar day read back."""
    from datetime import date

    def one(value: object) -> object:
        if isinstance(value, list):
            return [one(cell) for cell in value]
        return date.fromisoformat(value) if isinstance(value, str) else value

    return (
        [one(value) for value in item["values"]]
        if "date" in item["dtype"]
        else item["values"]
    )


def _a_form(
    name: str,
    count: int,
    carriers: list[str],
    indicators: tuple[int, ...] = (),
    shapes: tuple[str, ...] = (),
) -> tuple[object, pl.Series | None]:
    """Return a swept invocation and the producer's answer for the same tree.

    The node's declared type is the type the producer resolved, where it
    answered at all. That is what makes the two comparable -- and it takes the
    synthetic record out of the question, since a record stating a type its own
    tree does not produce is a defect in this helper rather than in a
    registration.
    """
    inputs = {
        f"x{one}": _a_column_of(carriers[one], one, shapes) for one in range(count)
    }
    args: list[dict[str, object]] = []
    for position in range(count):
        if position in indicators:
            inputs[f"p{position}"] = dict(_LEFT_OF_THE_COMPARISON)
            inputs[f"q{position}"] = dict(_RIGHT_OF_THE_COMPARISON)
            args.append(
                _a_comparison(_COMPARISON_AT[position], f"p{position}", f"q{position}")
            )
            inputs.pop(f"x{position}", None)
        else:
            args.append({"op": "col", "name": f"x{position}"})
    tree = _tree_of(name, args)
    answered = _polars_answer(tree, inputs)
    return invocation(tree, inputs, _declared(name, answered, inputs, shapes)), answered


def _declared(
    name: str,
    answered: pl.Series | None,
    inputs: dict[str, dict[str, object]],
    shapes: tuple[str, ...],
) -> str:
    """Return the type the swept node's record declares.

    The producer's own answer where it answered, which is what makes the two
    engines comparable. Where the producer refused, the *registration's* own
    claim: a capability states what it answers in, and a record written
    against anything else would make every such form read as a disagreement
    about the document rather than about the domain.
    """
    from gaspatchio._dtypes import neutral_dtype
    from gaspatchio_jax.lowerings import LOWERINGS

    if answered is not None:
        return neutral_dtype(answered.dtype, column="answer")
    capability = LOWERINGS[name][1]
    carrier = capability.answers_carrier
    if carrier is None:
        # The operands' own, promoted the way 11.1.25 promotes them: a double
        # on any side carries the answer. A record written against the first
        # operand alone would call a clip of a whole number between decimal
        # bounds an integer, which is not what either engine answers.
        carried = [
            str(item["dtype"]).removeprefix("list[").removesuffix("]")
            for item in inputs.values()
        ]
        carrier = next(
            (one for one in ("f64", "i64", "bool") if one in carried),
            carried[0] if carried else "f64",
        )
    per_period = capability.answers == "list" or (
        capability.answers is None and "list" in shapes
    )
    return f"list[{carrier}]" if per_period else carrier


# One comparison per operand position, so two indicator operands are two
# different indicators rather than the same column twice -- which is what makes
# `(a < b) + (a <= b)` a sum of two and not a doubling of one.
_COMPARISON_AT = {0: "lt", 1: "le", 2: "gt"}


def _a_column_of(carrier: str, position: int, shapes: tuple[str, ...]) -> dict:
    """Return one swept operand column, per policy or per period.

    A per-period column is the same two values wrapped in one list each, so a
    registration handed one is handed the same *carrier* at the other shape
    and nothing else moves. Two rows either way, so a comparison built over
    two of them is still true on one and false on the other.
    """
    written = dict(_A_COLUMN_OF[carrier])
    if position >= len(shapes) or shapes[position] != "list":
        return written
    return {
        "dtype": f"list[{written['dtype']}]",
        "values": [[value] for value in written["values"]],
    }


def _swept_shapes() -> list[tuple[str, int, int]]:
    """Return every (identifier, arity, operand position) to sweep for shape.

    The second axis of an operand domain. A registration says what its
    operands are *carried in* and whether each stands per policy or per
    period, and the two are independent questions: ``sum`` takes a number per
    period and answers one per policy, ``finance.discount`` takes numbers per
    policy and no list at all. A declaration that admitted a shape its lowering
    refuses reads as a claim a reader can port on and cannot -- exactly as a
    carrier does -- so it is swept the same way.
    """
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    found: list[tuple[str, int, int]] = []
    for name, (_lowering, capability) in sorted(LOWERINGS.items()):
        if name in _SWEPT_BY_HAND or capability.arity is None:
            continue
        found.extend(
            (name, count, position)
            for count in capability.arity
            for position in range(count)
        )
    return found


@pytest.mark.parametrize(("name", "count", "position"), _swept_shapes(), ids=str)
def test_no_registration_claims_a_shape_its_lowering_refuses(
    name: str, count: int, position: int
) -> None:
    """The declared shape domain and the lowering answer the same question."""
    from gaspatchio_jax.lowerings import LOWERINGS

    capability = LOWERINGS[name][1]
    admitted = [_a_carrier_of(capability, other, count) for other in range(count)]
    shapes = tuple(
        "list" if other == position else _first_shape(capability, other)
        for other in range(count)
    )
    one, _answered = _a_form(name, count, admitted, shapes=shapes)
    refused_by_the_tree = any(
        status.status == "refused" for status in JaxEngine().validate_tree(one.document)
    )
    assert refused_by_the_tree == _the_engine_refused(one), (name, count, position)


def _a_carrier_of(capability: object, position: int, count: int) -> str:
    """Return one carrier this registration admits, a double where it takes one.

    A double rather than the alphabetically first, which is a Boolean: this
    sweep is about the *shape* of an operand, and a Boolean per period sends
    half the vocabulary down the indicator path where what is being asked
    about is the axis.
    """
    del count
    carriers = capability.carriers  # type: ignore[attr-defined]
    if carriers is None:
        return "f64"
    admitted = carriers[min(position, len(carriers) - 1)]
    return "f64" if "f64" in admitted else min(admitted)


def _first_shape(capability: object, position: int) -> str:
    """Return one shape this registration admits at a position."""
    stated = capability.shapes  # type: ignore[attr-defined]
    if stated is None:
        return "scalar"
    admitted = stated[min(position, len(stated) - 1)]
    return "scalar" if "scalar" in admitted else "list"


def _the_engine_refused(one: object) -> bool:
    """Return whether the run refused this form before it computed anything.

    Every tree-group refusal counts, the record disagreement included. That
    exclusion used to stand here and it hid a whole class of defect: a
    lowering that answers a carrier its own registration does not declare
    refuses at ``_settled`` with a sentence about the *record*, while
    ``validate_tree`` and the coverage manifest read *lowered* — which is a
    reader told they can port a form the runtime will not run, the one thing
    the capability system exists to prevent.

    A *value* check is still not a domain finding: a stored indicator that is
    neither 0.0 nor 1.0, an integer past its range, a key the basis does not
    carry. Those are completion findings and the tree could never have made
    them.
    """
    try:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    except EngineRefusal as refused:
        return any(
            one_refusal.group == "tree" for one_refusal in refused.report.refusals
        )
    return False


@pytest.mark.parametrize(
    ("name", "count", "position", "carrier"),
    _swept_registrations(),
    ids=str,
)
def test_no_registration_claims_an_operand_its_lowering_refuses(
    name: str, count: int, position: int, carrier: str
) -> None:
    """The declared domain and the lowering answer the same question.

    Swept rather than argued: every registration that declares an operand
    domain is offered every carrier at every position of every arity it
    declares, and what ``validate_tree`` says has to be what ``run`` does. A
    declaration wider than its lowering reads as a claim a reader can port on
    and cannot.
    """
    from gaspatchio_jax.lowerings import LOWERINGS

    capability = LOWERINGS[name][1]
    admitted = [
        min(capability.carriers[min(other, len(capability.carriers) - 1)])
        for other in range(count)
    ]
    admitted[position] = carrier
    one, _answered = _a_form(name, count, admitted)
    refused_by_the_tree = any(
        status.status == "refused" for status in JaxEngine().validate_tree(one.document)
    )
    assert refused_by_the_tree == _the_engine_refused(one), (
        name,
        count,
        position,
        carrier,
    )


@pytest.mark.parametrize(("name", "indicators"), _indicator_forms(), ids=str)
def test_an_arithmetic_operand_that_is_a_comparison_is_the_indicator_the_clause_states(
    name: str, indicators: tuple[int, ...]
) -> None:
    """11.1.26's other half: a comparison as an arithmetic operand is 1.0 / 0.0.

    One indicator operand and two, against the producer's own answer over the
    same book. The pair is the case that was wrong: two Boolean carriers met
    and nothing promoted them, so the answer came out of the integer path --
    where a sum of two indicators is not 2.0 and a difference has no
    arithmetic at all.
    """
    one, answered = _a_form(name, 2, ["i64", "i64"], indicators=indicators)
    assert answered is not None, (name, indicators)
    published = JaxEngine().run(one.document, one.inputs, FrameSink()).columns["answer"]
    _assert_same_values(published.to_list(), answered.to_list(), (name, indicators))


def _assert_same_values(published: list, answered: list, where: object) -> None:
    """Assert two answers agree, with the agreement band over the finite numbers."""
    assert len(published) == len(answered), where
    for found, expected in zip(published, answered, strict=True):
        if isinstance(expected, float) and math.isnan(expected):
            assert isinstance(found, float), (where, found)
            assert math.isnan(found), (where, found)
            continue
        if isinstance(expected, float) and not math.isfinite(expected):
            # An infinity of a sign is exact on both sides: 11.1.25 gives a
            # nonzero numerator over a signed zero its own signed infinity,
            # and a band around one would not mean anything.
            assert found == expected, (where, found, expected)
            continue
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            scale = max(abs(float(expected)), abs(float(found)), 1.0)
            assert abs(float(found) - float(expected)) <= 1e-12 * scale, (
                where,
                found,
                expected,
            )
            continue
        assert found == expected, (where, found, expected)


def test_two_indicators_answer_what_the_clause_answers() -> None:
    """The two documents the Critical was measured on, against literal values."""
    book = {
        "a": {"dtype": "i64", "values": [1, 5]},
        "b": {"dtype": "i64", "values": [3, 2]},
    }
    summed = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": _a_comparison("lt", "a", "b"),
            "right": _a_comparison("le", "a", "b"),
        },
        book,
        "f64",
    )
    assert JaxEngine().run(summed.document, summed.inputs, FrameSink()).columns[
        "answer"
    ].to_list() == [2.0, 0.0]

    signed = invocation(
        {
            "op": "binop",
            "kind": "sub",
            "left": _a_comparison("lt", "a", "b"),
            "right": _a_comparison("gt", "a", "b"),
        },
        book,
        "f64",
    )
    assert JaxEngine().run(signed.document, signed.inputs, FrameSink()).columns[
        "answer"
    ].to_list() == [1.0, -1.0]


def test_a_defect_that_is_not_a_refusal_still_leaves_the_sink_settled(
    monkeypatch,
) -> None:
    """Not every exception is a refusal, and none of them may leave a sink open."""
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()

    def burst(*_args: object, **_kwargs: object) -> None:
        message = "a defect, not a refusal"
        raise TypeError(message)

    swapped = dict(LOWERINGS)
    swapped["add"] = (burst, LOWERINGS["add"][1])
    monkeypatch.setattr("gaspatchio_jax.plan.LOWERINGS", swapped)

    one = _sum_of_two()
    sink = _CountingSink()
    with pytest.raises(TypeError, match="a defect, not a refusal"):
        JaxEngine().run(one.document, one.inputs, sink)

    assert sink.abandoned == 1
    assert sink.published == 0


def test_a_host_operation_that_refuses_is_one_report_and_an_abandoned_sink(
    monkeypatch,
) -> None:
    """The host stage refuses the way every other stage does, and settles the sink."""
    from gaspatchio_jax import plan as plan_module
    from gaspatchio_jax.typed import DomainRefused

    one = invocation(
        {
            "op": "call",
            "name": "to_text",
            "args": [{"op": "col", "name": "x"}],
            "attrs": {},
        },
        {"x": {"dtype": "i64", "values": [1, 2]}},
        "str",
    )

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise DomainRefused(
            what="this host operation met something it has no answer for",
            move="run this model on Polars",
            clause="11.1.39",
        )

    monkeypatch.setattr(plan_module, "_host_value", refuse)
    sink = _CountingSink()
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, sink)

    report = caught.value.report
    assert len(report.refusals) == 1
    assert report.refusals[0].group == "tree"
    assert report.refusals[0].where == "answer@1"
    assert report.refusals[0].clause == "11.1.39"
    assert report.closing_sentence() == "Nothing was computed."
    assert sink.abandoned == 1
    assert sink.published == 0


def test_a_completion_refusal_settles_the_sink_once_and_publishes_nothing() -> None:
    """One refusal, one settling: the stage reports and ``run`` owns the sink.

    A sum past the top of the type is the shortest path to a finding the
    trace can only have at the end, and what this reads is the count: the
    stage that meets it does not abandon the sink on its way out, because
    the method that opened the door is the one that closes it.
    """
    one = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "i64", "values": [2**63 - 1]},
            "b": {"dtype": "i64", "values": [1]},
        },
        "i64",
    )
    sink = _CountingSink()
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, sink)

    assert refused.value.report.refusals[0].group == "completion"
    assert refused.value.report.closing_sentence() == "No results were published."
    assert sink.abandoned == 1
    assert sink.published == 0


class _CountingSink(FrameSink):
    """A frame sink that remembers whether it was settled, and how."""

    def __init__(self) -> None:
        super().__init__()
        self.abandoned = 0
        self.published = 0

    def abandon(self) -> None:
        self.abandoned += 1
        super().abandon()

    def publish(self, report: RunReport) -> EngineResult:
        self.published += 1
        return super().publish(report)


def _a_range_over_serials() -> Invocation:
    """Return a range whose two endpoints are computed, one of them outside its clause.

    ``date.date_ranges`` reads the width of its own answer, so the engine
    lowers both endpoint trees twice: once on the host, to find out how wide
    the rectangle is, and once for real when the node is built. A spreadsheet
    serial below 1 is no date at all (11.1.33), and it is caught in both.
    """

    def serial(name: str) -> dict[str, object]:
        return {
            "op": "call",
            "name": "excel.from_excel_serial",
            "args": [{"op": "col", "name": name}],
            "attrs": {"epoch": "1900"},
        }

    return invocation(
        {
            "op": "call",
            "name": "date.date_ranges",
            "args": [serial("from"), serial("to")],
            "attrs": {"interval": "1d", "closed": "both"},
        },
        {
            "from": {"dtype": "i64", "values": [0, 45000]},
            "to": {"dtype": "i64", "values": [3, 45002]},
        },
        "list[date]",
    )


def test_one_cell_caught_twice_by_the_width_and_the_value_is_one_finding() -> None:
    """The stage that reads a width records into a book nobody reads.

    A sizing lowers whatever its operands stand on, and a check raised in
    there is the same cell the node will raise again when it is built for
    real. Kept in the run's own book that cell is reported twice -- once
    under the node, and once under no node at all, because the sizing stage
    names none. One cell is one finding.
    """
    one = _a_range_over_serials()
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    report = refused.value.report
    assert len(report.refusals) == 1, report.render()
    assert report.refusals[0].where == "answer@1"
    assert report.refusals[0].count == 1
    assert "excel.serial.epoch" in report.refusals[0].what
