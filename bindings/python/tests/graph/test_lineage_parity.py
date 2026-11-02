# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``af.graph`` on a frame and ``read_artifact`` on its audit file give one answer.

A reviewer holding only the file asks it what ``af.graph`` answers on the
frame: what a column read, what read it, everything behind and ahead of it,
which versions exist, which is live, what nothing reads. Both are answered by
one walk over one structure, and that is only a claim until every answer is
compared. So each model here is exported, read back, and asked every question
about every node id and every column name it holds -- plus names it does not
hold, whose refusals must read the same -- on both sides.

The models are the ones the package ships (each tutorial level and each
rollforward pattern, level 4 and level 5 among them), the model the
conformance corpus is an account of, and models shaped the way the workbook
conversions are shaped: a universal-life fund charged on its running balance,
a guarantee ratcheted to a fund, a valuation of lookups, joins, shifts,
windows and reductions, and a model with a scenario axis and two columns it
cannot account for.
"""

from __future__ import annotations

import datetime
import functools
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.lineage import Lineage
from gaspatchio.graph import GraphDocument, read_artifact
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.scenarios import with_scenarios

from .test_artifact_conformance import _SHIPPED_MODELS, _frame_for
from .test_conformance_corpus import _the_corpus_model

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# --- the room-shaped models --------------------------------------------------


def _universal_life() -> ActuarialFrame:
    """Return a fund charged a cost of insurance on its net amount at risk.

    The charge depends on the running balance, so the fund is a compiled
    rollforward; the surrender value reads the materialised fund, and the
    premium is written twice -- once as a draft nobody read.
    """
    af = ActuarialFrame(
        {
            "policy_id": ["UL1", "UL2"],
            "av_init": [10_000.0, 25_000.0],
            "face": [100_000.0, 250_000.0],
            "coi": [[0.0004] * 12, [0.0006] * 12],
            "credit": [[0.003] * 12, [0.003] * 12],
        }
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=11, frequency="monthly"
    )
    af.premium = af.face * 0.0
    af.premium = af.face * 0.001
    builder = af.projection.rollforward(states={"fund": af["av_init"]})
    builder["fund"].add(af["premium"], label="premium")
    builder["fund"].deduct_nar(af["coi"], death_benefit=af["face"], label="coi")
    builder["fund"].grow(af["credit"], label="interest")
    af.fund = compile_rollforward(builder).expr_for("fund")
    af.surrender_value = af.fund * 0.95
    af.flat_fee = af.policy_id.projection.broadcast_to_periods(like=af.month)
    return af


def _guarantee_ratchet() -> ActuarialFrame:
    """Return a death benefit base ratcheted to the fund on each anniversary."""
    af = ActuarialFrame(
        {
            "fund_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "fund_return": [[0.008] * 24],
            "anniversary": [[(period + 1) % 12 == 0 for period in range(24)]],
        }
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=23, frequency="monthly"
    )
    builder = af.projection.rollforward(
        states={"account_value": af["fund_init"], "benefit_base": af["gmdb_init"]}
    )
    builder["account_value"].grow(af["fund_return"], label="fund_growth")
    builder["benefit_base"].ratchet(
        to=pl.col("account_value@eop"), when=af["anniversary"], label="ratchet"
    )
    compiled = compile_rollforward(builder)
    af.fund = compiled.expr_for("account_value")
    af.gmdb = compiled.expr_for("benefit_base")
    af.net_amount_at_risk = af.gmdb - af.fund
    return af


def _valuation() -> ActuarialFrame:
    """Lookups, a join, shifts, windows and reductions, as a valuation has them."""
    mortality = Table(
        name="valuation_mortality",
        source=pl.DataFrame(
            {"age": list(range(30, 80)), "q": [0.001 + 0.0002 * a for a in range(50)]}
        ),
        dimensions={"age": "age"},
        value="q",
    )
    products = pl.DataFrame(
        {"product": ["term", "endow"], "expense_rate": [0.05, 0.08]}
    )
    af = ActuarialFrame(
        {
            "policy_id": ["P1", "P2"],
            "product": ["term", "endow"],
            "issue_age": [40, 55],
            "sum_assured": [100_000.0, 50_000.0],
            "premium": [1_200.0, 900.0],
        }
    )
    af = af.join(products, on="product")
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=11, frequency="monthly"
    )
    af.age = af.issue_age + af.month // 12
    af.q = mortality.lookup(age=af.age)
    af.q_monthly = af.q / 12.0
    af.survival = af.q_monthly.projection.cumulative_survival()
    af.deaths = af.survival * af.q_monthly
    af.claims = af.sum_assured * af.deaths
    af.claims_prior = af.claims.projection.previous_period()
    af.premiums = af.premium * af.survival
    af.expenses = af.premiums * af.expense_rate
    af.net_cf = af.premiums - af.claims - af.expenses
    af.net_cf = when(af.month == 0).then(af.net_cf - 100.0).otherwise(af.net_cf)
    af.reserve = af.net_cf.projection.prospective_value(discount_rate=0.003)
    af.claims_to_come = af.claims.projection.remaining_sum()
    af.claims_total = af.claims.list.sum()
    af.first_claim = af.claims.list.get(0)
    af.running_claims = af.claims.cum_sum()
    return af


def _scenarios_and_holes() -> ActuarialFrame:
    """Return a scenario axis, a column written past the frame, and one unseen."""
    af = ActuarialFrame(
        pl.DataFrame(
            {"sum_assured": [100_000.0, 250_000.0], "mortality_rate": [0.01, 0.02]}
        )
    )
    af.policies_in_force = 1.0 - af.mortality_rate
    af.death_claims = af.sum_assured * af.policies_in_force
    af.policies_in_force = af.policies_in_force - af.death_claims / af.sum_assured
    wide = with_scenarios(af, ["BASE", "UP"])
    wide.shock = when(wide.scenario_id == "UP").then(1.1).otherwise(1.0)
    wide.shocked_claims = wide.death_claims * wide.shock
    plan = wide._df  # noqa: SLF001 -- the writes past the frame under test
    assert plan is not None
    wide._df = plan.with_columns(  # noqa: SLF001
        (pl.col("death_claims") * 0.0).alias("death_claims"),
        (pl.col("sum_assured") * 0.02).alias("lapse_reserve"),
    )
    wide.reported = wide.death_claims + wide["lapse_reserve"]
    return wide


_ROOM_SHAPED: dict[str, Callable[[], ActuarialFrame]] = {
    "universal-life": _universal_life,
    "guarantee-ratchet": _guarantee_ratchet,
    "valuation": _valuation,
    "scenarios-and-holes": _scenarios_and_holes,
    "conformance-corpus": _the_corpus_model,
}
_MODELS: tuple[str, ...] = (*_SHIPPED_MODELS, *_ROOM_SHAPED)


@functools.cache
def _frame(model: str) -> ActuarialFrame:
    """Return one model's finished frame, built once per session."""
    if model in _ROOM_SHAPED:
        return _ROOM_SHAPED[model]()
    return _frame_for(model)


@functools.cache
def _exported(model: str) -> str:
    """Return the audit file one model exports."""
    return GraphExporter(_frame(model)).export(profile="audit")


def _document(model: str) -> GraphDocument:
    """Return the model's audit file, read back as a reviewer would hold it."""
    return GraphDocument(json.loads(_exported(model)))


# --- comparing ----------------------------------------------------------------


def _outcome(question: Callable[[], Any]) -> tuple[str, Any]:
    """Return what a question came to: its answer, or the words it refused in."""
    try:
        return ("answered", question())
    except ValueError as error:
        return ("refused", str(error))


def _names(document: GraphDocument) -> list[str]:
    """Return every node id and every column name, and names that are not there."""
    ids = [node["id"] for node in document.document["nodes"]]
    columns = sorted({c for n in document.document["nodes"] if (c := n["column"])})
    misses = [f"{columns[0]}@99", f"{columns[0]}x", "no_such_column"] if columns else []
    return [*ids, *columns, *misses]


def _assumptions(document: GraphDocument) -> list[str]:
    """Return every assumption a node reads, and one name that none does."""
    names = sorted(
        {a for node in document.document["nodes"] for a in node["reads_assumptions"]}
    )
    return [*names, "no_such_table"]


@pytest.mark.parametrize("model", _MODELS)
def test_every_question_about_every_name_answers_the_same_on_both(model: str) -> None:
    """Sets, order and refusals: the frame and the file cannot drift."""
    af, document = _frame(model), _document(model)

    for name in _names(document):
        for question, on_frame, on_file in (
            ("precedents", af.graph.precedents, document.precedents),
            ("dependents", af.graph.dependents, document.dependents),
            ("versions", af.graph.versions, document.versions),
            ("latest", af.graph.latest, document.latest),
            ("trace", af.graph.trace, document.trace),
            ("affected", af.graph.affected, document.affected),
        ):
            assert _outcome(lambda f=on_frame, n=name: f(n)) == _outcome(
                lambda f=on_file, n=name: f(n)
            ), (question, name)
        for depth in (0, 1, 2):
            for question in ("trace", "affected"):
                on_frame = getattr(af.graph, question)
                on_file = getattr(document, question)
                assert _outcome(
                    lambda f=on_frame, n=name, d=depth: f(n, depth=d)
                ) == _outcome(lambda f=on_file, n=name, d=depth: f(n, depth=d)), (
                    question,
                    name,
                    depth,
                )


@pytest.mark.parametrize("model", _MODELS)
def test_every_assumption_cone_answers_the_same_on_both(model: str) -> None:
    af, document = _frame(model), _document(model)

    for name in _assumptions(document):
        assert _outcome(lambda n=name: af.graph.affected(assumption=n)) == _outcome(
            lambda n=name: document.affected(assumption=n)
        ), name


@pytest.mark.parametrize("model", _MODELS)
def test_the_census_questions_answer_the_same_on_both(model: str) -> None:
    """Unused, holes, tiers and the model's own stamp."""
    af, document = _frame(model), _document(model)
    unused = af.graph.unused()
    keep = list(unused.terminal[:2])

    assert unused == document.unused()
    assert af.graph.unused(keep=keep) == document.unused(keep=keep)
    assert [(h.column, h.reason) for h in af.graph.holes()] == [
        (h.column, h.reason) for h in document.holes()
    ]
    assert af.graph.tiers() == document.tiers()
    assert af.graph.fingerprint() == document.fingerprint()


@pytest.mark.parametrize("model", _MODELS)
def test_the_core_reads_the_versions_the_fold_minted(model: str) -> None:
    """The lineage derives each column's definitions; the fold keeps its own index.

    The two are compared on every column so that a definition the fold
    indexes and the node record does not mark -- or the other way about --
    is caught here rather than by a reviewer whose file disagrees with the
    frame.
    """
    graph = _frame(model).graph._graph  # noqa: SLF001 -- the fold under test
    lineage = Lineage.of_graph(graph)
    columns = {node.data.column for node in graph.nodes.values() if node.data.column}

    for column in columns:
        assert lineage.versions_of(column) == graph.versions(column), column


def test_the_room_shaped_models_reach_every_class_and_every_kind_of_read() -> None:
    """The fixtures above are only worth what they cover, so the coverage is held.

    A balance materialised and read on, a superseded definition, a read for a
    length alone, an assumption cone, a joined column, a written-over column
    and one nothing accounts for, an offset, an aggregation window and a
    stored position.
    """
    documents = [_document(model) for model in _ROOM_SHAPED]
    unused = [document.unused() for document in documents]
    ways = [
        way
        for document in documents
        for node in document.document["nodes"]
        for read in node["facets"]
        .get("gaspatchio_column_transformation", {})
        .get("reads", [])
        for way in read["transformations"]
    ]

    assert any(u.superseded for u in unused)
    assert any(u.length_only for u in unused)
    assert any(u.data for u in unused)
    assert any(u.stamp for u in unused)
    assert any(u.terminal for u in unused)
    assert {"overwritten", "unrecorded"} <= {
        hole.reason for document in documents for hole in document.holes()
    }
    assert any("extracts" in n for d in documents for n in d.document["nodes"])
    assert any(way.get("offset") == -1 for way in ways)
    assert any(way.get("periods") == {"from": "first", "to": 0} for way in ways)
    assert any("position" in way for way in ways)
    assert _document("valuation").affected(assumption="valuation_mortality")


def test_a_file_read_off_disk_answers_as_the_one_handed_over(tmp_path: Path) -> None:
    """``read_artifact`` and a document in memory are one reader."""
    written = tmp_path / "audit.json"
    written.write_text(_exported("valuation"))

    audit = read_artifact(written)

    assert audit.path == written
    assert audit.trace("reserve") == _frame("valuation").graph.trace("reserve")
    assert audit.unused() == _document("valuation").unused()


def test_the_executable_profile_answers_as_the_audit_profile() -> None:
    """A profile adds operation trees; it changes no node, read or extract."""
    executable = GraphDocument(
        json.loads(GraphExporter(_frame("valuation")).export(profile="executable"))
    )
    audit = _document("valuation")

    for name in _names(audit):
        assert _outcome(lambda n=name: executable.trace(n)) == _outcome(
            lambda n=name: audit.trace(n)
        )
    assert executable.unused() == audit.unused()
