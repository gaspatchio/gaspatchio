# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How much of a node the format can account for, and what an unclassified one costs.

An artifact says how every column was computed. Whether anything but this
producer could *run* that account is a separate question, and the tier is
where it is answered: every operation in the format's own vocabulary, a
fragment written in one engine's own expression language, or an identifier
nobody has classified at all.

The tests below hold the classification to the three things it has to get
right. The weakest tier anywhere in a tree is the tier of the whole node,
because a reader told the strongest thing found would think the node more
portable than it is. A node with nothing to execute says nothing. And the
table the specification prints and the table this producer classifies from
are one table, not two that can drift.

The fourth thing -- that the table covers every operation this package can
lower, so a new one cannot land unclassified -- is asserted once, in
``census.py``, beside the other tripwire that fires when the framework's
own expression surface grows somewhere unreviewed. Asserting it here as
well would put one claim in two places that could disagree about it.
"""

from __future__ import annotations

import datetime
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
)
from gaspatchio._semantic.vocabulary import Operation
from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph import tiers as tiers_module
from gaspatchio.frame.graph.tiers import TIERS, tier_of

if TYPE_CHECKING:
    from gaspatchio.frame.graph.tiers import OpTier

# Where the specification prints the vocabulary this producer classifies
# from, so that the document and the table can be read against each other
# rather than trusted to agree.
_SPECIFICATION = (
    Path(__file__).resolve().parents[4] / "spec" / "graph-artifact" / "v0-preview.md"
)
_VOCABULARY_SECTION = "### 11.1 The core vocabulary"
_VOCABULARY_HEADER = ("Identifier", "Tier")


def _artifact(
    frame: ActuarialFrame, *, profile: Literal["audit", "executable"] = "audit"
) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire.

    The tier is on every node under either profile; ``executable`` is asked
    for only where a claim is about the tree the tier was read off, which
    the audit profile does not carry.
    """
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export(profile=profile))
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the artifact for two arriving columns and one calculation over them."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return _artifact(frame)


def _artifact_for_a_model_reaching_into_an_engine() -> dict[str, Any]:
    """Return the artifact for a model carrying one engine's own expression text."""
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.running_total = pl.col("sum_assured").cum_sum()
    return _artifact(frame)


def _artifact_for_a_model_with_a_column_nothing_accounts_for() -> dict[str, Any]:
    """Return the artifact for a model holding a column no recording door saw."""
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * 0.001_23
    frame._df = frame._df.with_columns(  # noqa: SLF001 — writing the plan past every recording door is what mints a hole
        (pl.col("sum_assured") * 0.02).alias("lapse_reserve")
    )
    return _artifact(frame)


def _artifact_for_a_model_injecting_simulated_deaths() -> dict[str, Any]:
    """Return the artifact for a model handed a whole column of values at a line."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    frame.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])
    return _artifact(frame)


def _artifact_for_a_projected_model() -> dict[str, Any]:
    """Return the artifact for a model that declares a projection timeline."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1", "P2"], "sum_assured": [100_000.0, 250_000.0]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.death_claims = frame.sum_assured * 0.001_23
    return _artifact(frame)


def _artifact_for_a_model_joining_an_expense_basis() -> dict[str, Any]:
    """Return the artifact for a model that brings a rate in from the right side."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1", "P2"], "product_code": ["TERM", "WL"]})
    )
    frame = frame.join(
        pl.DataFrame({"product_code": ["TERM", "WL"], "expense_rate": [0.05, 0.08]}),
        on="product_code",
    )
    frame.expenses = frame.expense_rate * 1_000.0
    return _artifact(frame)


def _artifact_for_a_model_the_date_door_stamped(
    *, profile: Literal["audit", "executable"] = "audit"
) -> dict[str, Any]:
    """Return the artifact for a model whose dates the frame verbs derived.

    Both frame-level date verbs, over columns named the way the frame level
    names one -- an anniversary a year on from entry, and the monthly
    timeline between entry and expiry. ``date.offset_by`` and
    ``date.date_ranges`` are both identifiers section 11.1 lists, so both
    nodes are ones the format can account for in full.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "entry_date": [datetime.date(2026, 1, 1), datetime.date(2026, 6, 1)],
                "expiry_date": [datetime.date(2027, 1, 1), datetime.date(2027, 6, 1)],
            }
        )
    )
    frame.date.add_duration("entry_date", "12mo", new_col_name="anniversary")
    frame.date.create_timeline(
        "entry_date", "expiry_date", freq="1mo", new_col_name="period_date"
    )
    return _artifact(frame, profile=profile)


def _artifact_for_a_model_present_valuing_its_cashflows(
    *, profile: Literal["audit", "executable"] = "audit"
) -> dict[str, Any]:
    """Return the artifact for a model discounting three columns it names.

    ``af.finance.present_value("cashflow", "rate", "period")`` is the form
    the method's own docstring leads with, over columns named the way the
    frame level names one. ``finance.present_value`` is an identifier
    section 11.1 lists, so this is a node the format can account for in
    full -- a closed form over three values standing at one period, which
    any implementation holding the vocabulary could evaluate.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "cashflow": [1_000.0, 2_000.0],
                "rate": [0.05, 0.04],
                "period": [1, 2],
            }
        )
    )
    frame.pv = frame.finance.present_value("cashflow", "rate", "period")
    return _artifact(frame, profile=profile)


def _tiers_behind(artifact: dict[str, Any], door: str) -> set[str | None]:
    """Return every tier the nodes that came through ``door`` report."""
    found = {node["tier"] for node in artifact["nodes"] if node["provenance"] == door}
    assert found, f"no node in this artifact came through the {door!r} door"
    return found


def _printed_vocabulary() -> dict[str, str]:
    """Return the identifier table the specification prints, keyed by identifier.

    Read back out of the document rather than restated here, so that the
    table a second implementer looks something up in and the table this
    producer classifies from cannot drift apart without a test failing.

    Raises:
        ValueError: If the table is not headed the way this reads it, which
            would mean the check below was silently checking something else.

    """
    text = _SPECIFICATION.read_text("utf-8")
    tail = text[text.index(_VOCABULARY_SECTION) + len(_VOCABULARY_SECTION) :]
    stop = tail.find("\n#")
    section = tail if stop < 0 else tail[:stop]
    rows = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|")
    ]
    header, *body = [row for row in rows if not all(set(c) <= set("-: ") for c in row)]
    if tuple(header) != _VOCABULARY_HEADER:
        msg = f"section 11.1's identifier table is headed {header!r}"
        raise ValueError(msg)
    return {row[0]: row[1] for row in body}


# --- what a tree is worth ----------------------------------------------------


def test_a_framework_built_formula_is_core() -> None:
    """A formula the framework built for itself reaches into no engine."""
    assert tier_of(BinOp("mul", Col("sum_assured"), Col("mortality_rate"))) == "core"


def test_one_escape_hatch_anywhere_makes_the_whole_node_engine_native() -> None:
    """The weakest tier reached is the node's, however ordinary the rest looks."""
    tree = BinOp(
        "mul",
        Col("mortality_rate"),
        EngineNative(engine="polars", text='col("x").cum_sum()', deps=("x",)),
    )

    assert tier_of(tree) == "engine_native"


def test_an_identifier_nothing_has_classified_is_opaque() -> None:
    """An operation the table does not list is carried, and declared unaccounted for."""
    assert tier_of(Call("acme.smoothing", args=(Col("reserve"),))) == "opaque"


def test_an_unclassified_identifier_outweighs_an_escape_hatch() -> None:
    """Weakest wins, and it is the whole ordering rather than the last thing seen.

    A tree holding both a declared engine fragment and an identifier
    nothing classified is opaque: the reader can at least act on "this
    needs Polars", and cannot act at all on an operation nobody has named.
    """
    tree = BinOp(
        "add",
        EngineNative(engine="polars", text='col("x").cum_sum()', deps=("x",)),
        Call("acme.smoothing", args=(Col("reserve"),)),
    )

    assert tier_of(tree) == "opaque"


def test_the_conditional_and_the_operands_it_selects_between_are_all_walked() -> None:
    """Every branch of a conditional is part of what the node has to execute."""
    engine_free = WhenThen(
        cond=BinOp("gt", Col("sum_assured"), Lit(200_000.0)),
        then=Col("death_claims"),
        otherwise=Lit(0.0),
    )
    with_an_escape_hatch = WhenThen(
        cond=BinOp("gt", Col("sum_assured"), Lit(200_000.0)),
        then=Col("death_claims"),
        otherwise=EngineNative(engine="polars", text='col("x").cum_sum()', deps=("x",)),
    )

    assert tier_of(engine_free) == "core"
    assert tier_of(with_an_escape_hatch) == "engine_native"


def test_a_rollforward_state_read_is_core_because_the_format_names_it() -> None:
    """A running state is a node the byte grammar tags, not an unnamed operation."""
    assert tier_of(State("account_value@eop")) == "core"


# --- the table cannot fall behind the operations ----------------------------


def test_the_specification_prints_the_table_this_producer_classifies_from() -> None:
    """One vocabulary, in two places, saying the same thing about every operation."""
    printed = _printed_vocabulary()

    assert printed == dict(TIERS)


def test_every_classified_operation_is_core() -> None:
    """The weaker tiers come from a node's tree, never from the table."""
    weaker: dict[str, OpTier] = {
        name: tier for name, tier in TIERS.items() if tier != "core"
    }

    assert weaker == {}


def test_the_module_states_that_fact_without_dating_it() -> None:
    """Both tables say every entry is core as a fact, not as a stage of release.

    A reader of the published module page is told what the table holds and
    why. A qualifier naming the release it holds in would date the sentence
    as soon as the format's version moved, while the fact beside it would
    not have moved at all. The vocabulary row the table is read out of says
    the same of its tier column, in the same terms.
    """
    said = " ".join((tiers_module.__doc__ or "").split())
    row = " ".join((inspect.getdoc(Operation) or "").split())

    assert "which is why every entry in it is ``core``." in said
    assert "in this preview" not in said
    assert "Every entry is ``core``: the weaker tiers are reached" in row
    assert "in this preview" not in row


# --- what the artifact says about a node -------------------------------------


def test_a_leaf_has_no_tier_because_it_has_nothing_to_execute() -> None:
    """A column that arrived was not computed, so no tier is the honest answer."""
    artifact = _artifact_for_a_two_column_model()

    assert _node(artifact, "sum_assured")["tier"] is None


def test_a_column_nothing_accounts_for_has_no_tier_either() -> None:
    """A hole has no recorded calculation, so there is nothing to account for."""
    artifact = _artifact_for_a_model_with_a_column_nothing_accounts_for()

    assert _node(artifact, "lapse_reserve")["tier"] is None


def test_a_column_of_values_handed_over_at_a_line_has_no_tier() -> None:
    """Located data still computes nothing, whatever door recorded it."""
    artifact = _artifact_for_a_model_injecting_simulated_deaths()

    assert _node(artifact, "simulated_deaths@1")["tier"] is None


def test_a_computed_node_carries_the_tier_of_its_own_tree() -> None:
    """Every node with something to execute states how much of it is accounted for."""
    engine_free = _artifact_for_a_two_column_model()
    reaching_into_an_engine = _artifact_for_a_model_reaching_into_an_engine()

    assert _node(engine_free, "death_claims@1")["tier"] == "core"
    assert _node(reaching_into_an_engine, "running_total@1")["tier"] == "engine_native"


def test_a_door_that_computes_no_formula_still_reports_what_it_can_account_for() -> (
    None
):
    """Two doors mint computed columns behind an identifier no formula calls.

    A projection timeline's own configuration and a join both write columns
    that no expression in the model derives: what accounts for them is the
    door, which ``provenance`` names. This test used to pin both at ``opaque``,
    and said so in the form of a gap -- a reader told where the vocabulary
    stopped rather than discovering it when a port failed -- with a note that
    whichever way the gap was closed, this was the test that would close it.
    It was closed by listing them: section 11.1 now carries ``projection_set``
    and ``join``, each with stated semantics (11.1.1 and 11.1.2), so both
    doors report ``core``. What the semantics do not yet cover is stated in
    those two sections rather than in a tier, which is the right place for it:
    a tier says whether the vocabulary reaches an operation, not whether every
    last argument of it is on the wire.

    An injected column never reaches this question either way -- it is an
    input, and an input has no tier.
    """
    projected = _artifact_for_a_projected_model()
    joined = _artifact_for_a_model_joining_an_expense_basis()

    assert _tiers_behind(projected, "projection") == {"core"}
    assert _tiers_behind(projected, "assignment") == {"core"}
    assert _tiers_behind(joined, "join") == {"core"}
    assert _tiers_behind(joined, "assignment") == {"core"}


def test_a_door_whose_operations_the_vocabulary_names_reports_them_as_core() -> None:
    """The date door's two verbs are both section 11.1 identifiers.

    Read against the door test above it: ``projection`` and ``join`` mint
    columns behind an identifier that names a provenance rather than a
    calculation, and the vocabulary reaches both. ``date`` is the plainer
    case -- ``date.offset_by`` and ``date.date_ranges`` are operations a
    formula calls, and are in the table -- so a node this door minted
    reporting anything weaker than ``core`` is the producer, not the
    vocabulary, falling short.
    """
    stamped = _artifact_for_a_model_the_date_door_stamped()

    assert _tiers_behind(stamped, "date") == {"core"}


def test_the_column_a_date_verb_was_handed_stays_a_column_in_the_tree() -> None:
    """A name resolved at the frame level is a reference, not an engine fragment.

    The frame-level verbs take a column by name, and the framework is what
    turns that name into the operand. Turning it into the engine's own
    rendering of a column reference first put an ``engine_native`` leaf
    inside a tree whose operation the format names -- and because a node is
    only as portable as the weakest thing in it, the whole node reported as
    an engine escape over an operation any implementation holding the
    vocabulary could run. The tree is pinned whole here: nothing else would
    notice the wrap coming back, since the tier reads correctly the moment
    the leaf is a ``col`` and no other field of the record changes.
    """
    stamped = _artifact_for_a_model_the_date_door_stamped(profile="executable")

    assert _node(stamped, "anniversary@1")["expr"] == {
        "op": "call",
        "name": "date.offset_by",
        "args": [{"op": "col", "name": "entry_date"}],
        "attrs": {"duration": "12mo"},
    }
    assert _node(stamped, "period_date@1")["expr"] == {
        "op": "call",
        "name": "date.date_ranges",
        "args": [
            {"op": "col", "name": "entry_date"},
            {"op": "col", "name": "expiry_date"},
        ],
        "attrs": {"interval": "1mo", "closed": "left"},
    }
    assert _node(stamped, "anniversary@1")["engines"] == []
    assert _node(stamped, "period_date@1")["engines"] == []


def test_a_present_value_over_named_columns_reports_as_core() -> None:
    """``finance.present_value`` is in the table, so the node it mints is too.

    The same claim as the date door's above, at the other frame-level
    accessor that takes its operands by name. A discounted cashflow is a
    closed form over three values -- ``CF / (1 + rate) ** period`` -- and
    every part of it is something the vocabulary spells, so a reader
    deciding whether this model ports should be told nothing weaker.
    """
    discounted = _artifact_for_a_model_present_valuing_its_cashflows()

    assert _node(discounted, "pv@1")["tier"] == "core"
    assert _node(discounted, "pv@1")["engines"] == []


def test_the_columns_a_present_value_was_handed_stay_columns_in_the_tree() -> None:
    """A name resolved at the frame level is a reference, not an engine fragment.

    The date verbs' negative pin, made again here because the wrap it
    guards against was a separate copy of the same three lines rather
    than one shared helper: three column names, each turned into the
    engine's own rendering of a column reference before the tree saw it,
    put three ``engine_native`` leaves inside a tree whose operation the
    format names. The tree is pinned whole, because the tier reads
    correctly the moment the leaves are ``col`` and no other field of the
    record changes -- so an assertion on the tier alone would not notice
    one operand's wrap coming back.
    """
    discounted = _artifact_for_a_model_present_valuing_its_cashflows(
        profile="executable"
    )

    assert _node(discounted, "pv@1")["expr"] == {
        "op": "call",
        "name": "finance.present_value",
        "args": [
            {"op": "col", "name": "cashflow"},
            {"op": "col", "name": "rate"},
            {"op": "col", "name": "period"},
        ],
        "attrs": {},
    }


def test_an_engine_expression_a_present_value_was_handed_is_still_declared() -> None:
    """The framework stops wrapping its own answer, not the author's fragment.

    An actuary who reaches past the accessor and hands ``pl.col(...)`` in
    has written an engine expression, and the record says so: that operand
    stays ``engine_native``, and one escape hatch anywhere makes the whole
    node engine-native. Pinned beside the flip so that the fix cannot be
    read as "``present_value`` is always core" -- what changed is whose
    engine reference it is, not whether one counts.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "cashflow": [1_000.0, 2_000.0],
                "rate": [0.05, 0.04],
                "period": [1, 2],
            }
        )
    )
    frame.pv = frame.finance.present_value(pl.col("cashflow"), "rate", "period")
    honest = _artifact(frame, profile="executable")

    assert _node(honest, "pv@1")["tier"] == "engine_native"
    assert _node(honest, "pv@1")["engines"] == ["polars"]
    assert _node(honest, "pv@1")["expr"]["args"][0]["op"] == "engine_native"
    assert _node(honest, "pv@1")["expr"]["args"][1:] == [
        {"op": "col", "name": "rate"},
        {"op": "col", "name": "period"},
    ]


def test_the_tier_sits_between_what_a_node_reads_and_what_identifies_it() -> None:
    """The format tabulates it there, and a reader meets the record in that order."""
    computed = _node(_artifact_for_a_two_column_model(), "death_claims@1")

    fields = list(computed)

    assert fields[fields.index("reads") + 1 :][:4] == [
        "reads_assumptions",
        "engines",
        "tier",
        "local_fingerprint",
    ]
