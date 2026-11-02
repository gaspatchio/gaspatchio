# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compiled rollforward's identity is its machine; the schedule is data.

The compiled fingerprint is taken over the machine alone -- every state,
operation, operand, rounding and stopping rule -- and leaves out the schedule
the machine runs on. Every rollforward call carries that schedule's own
``source_sha()`` beside the fingerprint, so a re-sourced schedule still moves
``graph_fingerprint`` (through the compilation's own node and the lines that
read it) and leaves ``formulas_fingerprint`` where it was, while an edit to
the machine moves both.

The fingerprint is no longer enough to tell two kernel runs apart, so the
process files a compilation under the pair, the kernel's scratch column is
named for the pair, and one model holding one machine on two schedules is
refused by name rather than merged into one node.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule
from gaspatchio.frame.graph import (
    GraphExporter,
    document_digest_of,
    inspect_execution,
    validate_artifact,
)
from gaspatchio.frame.graph.fingerprint import canonical_bytes, formulas_tree
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.frame.lowering import artefacts
from gaspatchio.rollforward import RollforwardBuilder, compile_rollforward

if TYPE_CHECKING:
    from gaspatchio.rollforward._compiled import CompiledRollforward

_PERIODS = 12


def _calendar(start: datetime.date, frequency: str = "1M") -> Schedule:
    """Return a calendar grid of twelve periods from ``start``."""
    return Schedule.from_calendar_grid(
        start_date=start, n_periods=_PERIODS, frequency=frequency
    )


_SCHEDULES: dict[str, Schedule] = {
    "calendar, January": _calendar(datetime.date(2026, 1, 31)),
    "calendar, April": _calendar(datetime.date(2026, 4, 30)),
    "calendar, quarterly": _calendar(datetime.date(2026, 1, 31), "3M"),
    "fixed step, a twelfth spelt as twelve a year": Schedule.fixed_step(
        n_periods=_PERIODS, steps_per_year=12
    ),
    "fixed step of 0.1 years": Schedule.fixed_step(n_periods=_PERIODS, step_years=0.1),
}

# Each pair is one schedule-only change: a calendar re-dated, a calendar
# re-cadenced, a fixed-step axis re-stepped, and a calendar exchanged for a
# fixed-step axis.
_CHANGES = (
    ("calendar, January", "calendar, April"),
    ("calendar, January", "calendar, quarterly"),
    ("fixed step, a twelfth spelt as twelve a year", "fixed step of 0.1 years"),
    ("calendar, January", "fixed step of 0.1 years"),
)


def _machine(
    frame: ActuarialFrame,
    schedule: Schedule,
    *,
    edit: str | None = None,
) -> CompiledRollforward:
    """Compile one fund's machine on ``schedule``, or the same machine edited."""
    builder = RollforwardBuilder(states={"fund": frame.av_init}, schedule=schedule)
    if edit == "operation":
        builder["fund"].charge(frame.rate, label="interest")
    elif edit == "operand":
        builder["fund"].grow(frame.bonus, label="interest")
    elif edit == "rounding":
        builder["fund"].grow(frame.rate, label="interest", round_charge=2)
    else:
        builder["fund"].grow(frame.rate, label="interest")
    return compile_rollforward(builder)


def _frame() -> ActuarialFrame:
    """Return two policies with an opening fund and a rate per period.

    No projection is set: each machine is handed its schedule directly, so
    nothing but the compilation reads the schedule and a move in either
    figure is the rollforward's own.
    """
    return ActuarialFrame(
        {
            "av_init": [100.0, 250.0],
            "rate": [[0.01] * _PERIODS] * 2,
            "bonus": [[0.02] * _PERIODS] * 2,
        }
    )


def _model(schedule: Schedule, *, edit: str | None = None) -> ActuarialFrame:
    """Return a model extracting one fund rolled forward on ``schedule``."""
    frame = _frame()
    frame.fund = _machine(frame, schedule, edit=edit).expr_for("fund")
    return frame


def _document(frame: ActuarialFrame) -> dict[str, Any]:
    """Return the executable document, required to pass its deep checks."""
    document: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )
    report = validate_artifact(document, deep=True)
    assert report.ok, report.findings
    return document


def _by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the document's nodes by id."""
    return {node["id"]: node for node in document["nodes"]}


def _masked_local(node: dict[str, Any]) -> str:
    """Return a node's local digest over its masked tree, as section 12.6 takes it."""
    if "expr" not in node:
        return str(node["local_fingerprint"])
    tree = formulas_tree(op_node_from_json(node["expr"]))
    return hashlib.sha256(canonical_bytes(tree)).hexdigest()


# --- the identity leaves the schedule out ---------------------------------------


@pytest.mark.parametrize(("was", "now"), _CHANGES)
def test_the_compiled_identity_and_its_node_id_leave_the_schedule_out(
    was: str, now: str
) -> None:
    """One machine on two schedules is one fingerprint and one node id."""
    frame = _frame()
    before = _machine(frame, _SCHEDULES[was])
    after = _machine(frame, _SCHEDULES[now])

    assert before.fingerprint() == after.fingerprint()
    assert "schedule" not in before.canonical_form()
    ids = [
        [node["id"] for node in _document(_model(_SCHEDULES[name]))["nodes"]]
        for name in (was, now)
    ]
    assert ids[0] == ids[1]
    assert any(node_id.startswith("rollforward:") for node_id in ids[0])


@pytest.mark.parametrize(("was", "now"), _CHANGES)
def test_a_schedule_change_moves_the_graph_through_the_compilation_s_own_node(
    was: str, now: str
) -> None:
    """The schedule reaches the record as the ``schedule`` attribute of its calls.

    Nothing else in these models reads the schedule, so the nodes whose
    digests move are exactly the compilation's own node and the line that
    reads it -- and both move again on nothing once the schedule is masked.
    """
    documents = [_document(_model(_SCHEDULES[name])) for name in (was, now)]
    before, after = (_by_id(document) for document in documents)

    assert documents[0]["graph_fingerprint"] != documents[1]["graph_fingerprint"]
    assert documents[0]["formulas_fingerprint"] == documents[1]["formulas_fingerprint"]

    (compilation,) = [
        node_id for node_id in before if node_id.startswith("rollforward:")
    ]
    for document, name in zip(documents, (was, now), strict=True):
        tree = _by_id(document)[compilation]["expr"]
        assert tree["attrs"]["schedule"] == _SCHEDULES[name].source_sha()

    moved = {
        node_id
        for node_id in before
        if before[node_id]["local_fingerprint"] != after[node_id]["local_fingerprint"]
    }
    assert moved == {compilation, "fund@1"}
    assert all(_masked_local(before[n]) == _masked_local(after[n]) for n in before)


def test_on_the_frame_s_own_fixed_step_axis_the_rollforward_moves_nothing_masked() -> (
    None
):
    """On a projection's fixed-step axis, the rollforward adds no formula movement.

    A fixed-step axis is recorded on the projection by its two numbers, which
    the model typed (section 11.1.1), so re-stepping it is a formula change
    with or without a rollforward. The rollforward contributes none of it:
    its node and the line reading it are the same under the mask.
    """

    def model(schedule: Schedule) -> ActuarialFrame:
        frame = ActuarialFrame(
            {"av_init": [100.0, 250.0], "rate": [[0.01] * _PERIODS] * 2}
        )
        frame = frame.projection.set(schedule=schedule)
        builder = frame.projection.rollforward(states={"fund": frame.av_init})
        builder["fund"].grow(frame.rate, label="interest")
        frame.fund = compile_rollforward(builder).expr_for("fund")
        return frame

    before, after = (
        _by_id(_document(model(_SCHEDULES[name])))
        for name in (
            "fixed step, a twelfth spelt as twelve a year",
            "fixed step of 0.1 years",
        )
    )
    (compilation,) = [
        node_id for node_id in before if node_id.startswith("rollforward:")
    ]

    assert compilation in after
    for node_id in (compilation, "fund@1"):
        assert (
            before[node_id]["local_fingerprint"] != after[node_id]["local_fingerprint"]
        )
        assert _masked_local(before[node_id]) == _masked_local(after[node_id])


@pytest.mark.parametrize("edit", ["operation", "operand", "rounding"])
def test_an_edit_to_the_machine_moves_both_figures_and_the_id(edit: str) -> None:
    """An operation, an operand or a rounding is the machine, and is logic."""
    schedule = _SCHEDULES["calendar, January"]
    frame = _frame()
    assert _machine(frame, schedule).fingerprint() != (
        _machine(frame, schedule, edit=edit).fingerprint()
    )

    before, after = (_document(_model(schedule, edit=e)) for e in (None, edit))

    assert before["graph_fingerprint"] != after["graph_fingerprint"]
    assert before["formulas_fingerprint"] != after["formulas_fingerprint"]
    assert {n["id"] for n in before["nodes"] if n["kind"] == "rollforward"} != {
        n["id"] for n in after["nodes"] if n["kind"] == "rollforward"
    }


# --- nothing keyed on the identity collides ------------------------------------


def test_one_machine_on_two_schedules_in_one_process_runs_each_on_its_own() -> None:
    """Two runs of one machine in one process are two compilations and two kernels.

    Last quarter's model and this quarter's, built side by side: the
    fingerprint is shared, and nothing that resolves a compilation, names its
    kernel column or materialises it treats the two as one. Both expressions
    are built before either is assigned, so a registry keyed on the
    fingerprint alone would hand the second frame the first one's kernel.
    """
    short = Schedule.from_calendar_grid(
        start_date=datetime.date(2026, 4, 30), n_periods=6, frequency="1M"
    )
    long_frame = _frame()
    short_frame = ActuarialFrame(
        {"av_init": [100.0, 250.0], "rate": [[0.01] * 6] * 2, "bonus": [[0.0] * 6] * 2}
    )
    long_run = _machine(long_frame, _SCHEDULES["calendar, January"])
    short_run = _machine(short_frame, short)
    long_read, short_read = long_run.expr_for("fund"), short_run.expr_for("fund")
    long_frame.fund = long_read
    short_frame.fund = short_read

    assert long_run.fingerprint() == short_run.fingerprint()
    assert long_run._hidden_column != short_run._hidden_column  # noqa: SLF001 -- the key under test
    # Each run is filed under its own schedule, and what is filed there runs
    # on that schedule -- whichever equal compilation of it was filed first.
    held = artefacts._ROLLFORWARDS  # noqa: SLF001 -- the registry under test
    for run, schedule in (
        (long_run, _SCHEDULES["calendar, January"]),
        (short_run, short),
    ):
        filed = held[run.fingerprint(), schedule.source_sha()]
        assert filed.ir.schedule.source_sha() == schedule.source_sha()
        assert filed._hidden_column == run._hidden_column  # noqa: SLF001
    assert artefacts.rollforward_named_by(long_run._hidden_column) == (  # noqa: SLF001
        long_run.fingerprint(),
        _SCHEDULES["calendar, January"].source_sha(),
    )

    long_fund = long_frame.collect()["fund"].to_list()
    short_fund = short_frame.collect()["fund"].to_list()
    assert [len(fund) for fund in long_fund] == [_PERIODS, _PERIODS]
    assert [len(fund) for fund in short_fund] == [6, 6]
    assert long_fund[0][:6] == pytest.approx(short_fund[0])
    assert long_fund[0][-1] == pytest.approx(100.0 * 1.01**_PERIODS)


def test_one_model_holding_one_machine_on_two_schedules_is_refused() -> None:
    """Two kernel runs cannot share the one node id their machine names.

    The frame runs both -- each has its own scratch column -- and the graph
    refuses to give an account of them, naming the machine and both
    schedules, rather than reporting the second run's reads as the first's.
    """
    frame = ActuarialFrame({"av_init": [100.0], "rate": [[0.01] * _PERIODS]})
    january, april = _SCHEDULES["calendar, January"], _SCHEDULES["calendar, April"]
    for column, schedule in (("fund_january", january), ("fund_april", april)):
        builder = RollforwardBuilder(states={"fund": frame.av_init}, schedule=schedule)
        builder["fund"].grow(frame.rate, label="interest")
        frame[column] = compile_rollforward(builder).expr_for("fund")

    values = frame.collect()
    assert values["fund_january"].to_list() == values["fund_april"].to_list()
    with pytest.raises(ValueError, match="on two schedules") as refused:
        GraphExporter(frame).export(profile="audit")
    assert january.source_sha()[7:19] in str(refused.value)
    assert april.source_sha()[7:19] in str(refused.value)


def test_a_wrapped_extraction_kept_as_engine_text_names_the_run() -> None:
    """The one place a schedule change still reaches the formulas figure.

    A line that wraps an extraction in an expression the record keeps as
    engine text -- an opening period prepended -- names the kernel's scratch
    column in that text, and the scratch column is named for the run, the
    schedule included, so that two runs never share one. Section 12.6 states
    the position: an engine-native fragment's text is hashed as written.
    Pinned so that a change to it is deliberate. The fragment is not refused:
    a rollforward read inside engine text is reached through its own node.
    """

    def model(schedule: Schedule) -> ActuarialFrame:
        frame = ActuarialFrame(
            {
                "av_init": [100.0, 250.0],
                "opening": [[0.0], [0.0]],
                "rate": [[0.01] * _PERIODS] * 2,
            }
        )
        compiled = _machine(frame, schedule)
        frame.fund = pl.concat_list([pl.col("opening"), compiled.expr_for("fund")])
        return frame

    before, after = (
        _document(model(_SCHEDULES[name]))
        for name in ("calendar, January", "calendar, April")
    )
    wrapped = _by_id(before)["fund@1"]["expr"]

    assert wrapped["op"] == "engine_native"
    assert "__rollforward_" in wrapped["text"]
    assert before["graph_fingerprint"] != after["graph_fingerprint"]
    assert before["formulas_fingerprint"] != after["formulas_fingerprint"]
    moved = {
        node_id
        for node_id, node in _by_id(before).items()
        if _masked_local(node) != _masked_local(_by_id(after)[node_id])
    }
    assert moved == {"fund@1"}


def test_a_machine_running_on_another_schedule_than_its_node_states_is_caught() -> None:
    """The node's call and the facet's body state one schedule, read twice.

    A document whose compilation node names one schedule while the machine it
    carries runs on another has no single period count, and the execution
    reading says so rather than picking one.
    """
    document = _document(_model(_SCHEDULES["calendar, January"]))
    (compilation,) = document["facets"]["gaspatchio_rollforward_ir"][
        "compilations"
    ].values()
    assert inspect_execution(document).checks["declared_payloads"] == "passed"

    compilation["schedule"] = _SCHEDULES["calendar, April"].source_sha()
    document["document_digest"] = document_digest_of(document)

    codes = {finding.code for finding in inspect_execution(document).findings}
    assert "compilation_schedule_disagrees" in codes
