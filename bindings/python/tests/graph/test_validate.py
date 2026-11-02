# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Reading an exported artifact back, and asking whether it holds together.

An artifact is a record somebody else reads: a reviewer this quarter, a
supervisor next year, a second implementation that has never met this one.
What makes it worth reading is that its claims can be checked by whoever
holds it, rather than believed because of who wrote it -- and a claim nobody
can check is a claim nobody has to keep.

Five readings, and the tests below are grouped by them. The **schema** layer
resolves the artifact's own ``schema`` identifier through the table this
package ships and validates the document against what that table names; an
identifier this build does not carry is refused by name, rather than parsed
for a version or fetched as a URL. The **structure** layer reads what a
schema of this kind cannot reach: that every name a node reads resolves to a
node in the same file, that the dependencies do not run in a circle, that a
column's definitions count from 1 without a gap, that a reserved id namespace
holds nothing that is a column of the model, and that the two facet
declaration lists say what the document actually carries -- a facet the
producer marked *required* among them.

The **identity** reading is what ``deep=True`` adds, and it is the one that
turns the file's own digests from a claim into a check: every published
``fingerprint`` is recomputed from the ``local_fingerprint`` beside it and
what the node reads, the model's one digest is recomputed from the published
pairs, every inlined assumption payload is re-hashed against the fingerprint
written next to it, and -- where the artifact carries operation trees -- every
``local_fingerprint`` is recomputed from the tree it was taken over. The
**enrichment** reading holds the values an artifact carries to the walk-through
beside them. The **portability** reading answers one question about one named
engine: which nodes it cannot run, counted rather than described.

Every artifact this package produces is held to all of them, and the four
files checked in beside this one -- the published corpus, the supervisory
annex's example, and the two hand-built examples standing behind the payload
sections nothing emits -- are held to the structural ones. A validator its own
producer's output fails is a validator nobody runs twice.
"""

from __future__ import annotations

import copy
import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.curves import Curve
from gaspatchio.frame.graph import (
    REPORT_VERSION,
    Finding,
    GraphExporter,
    ValidationReport,
    validate_artifact,
)
from gaspatchio.frame.graph.artifact import TABLE_PAYLOAD_LIMIT
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable

_GOLDENS = Path(__file__).parent / "goldens"

# The two hand-built examples of section 17, the published corpus, the annex
# example, and one document carrying a policy axis with more than one entry
# on it. All of them are files a reader of this format will meet, so all of
# them are held to what a reader is told they can rely on.
#
# The multi-policy one earns its place because every other file here carries
# either one policy or none, and a reading that walked the axis wrongly --
# or did not walk it at all -- would pass on all four of them. It is an
# account of the awkward book in ``tests/fixtures``: string ids, out of
# order, one of them shaped like a slice.
#
# The fold-carrying one earns its place for what it puts on that axis that
# no other file here does: an entry whose ``policy_id`` is null because no
# policy is what it is an account of, an ``aggregation`` naming the fold --
# the member section 7 defined when the format was drafted and nothing wrote
# until there was an axis to write it on -- and nulls at that entry's
# position on every node the fold did not cover. A reading that took the
# null for a defect, or the entry for a policy, would refuse a document the
# producer writes.
_CHECKED_IN = (
    "conformance_corpus.json",
    "state_graph_example.json",
    "nested_valuation_example.json",
    "annex_example_artifact.json",
    "policy_axis_example.json",
    "portfolio_fold_example.json",
    "scenario_export_example.json",
)

# Long enough for the rollforward below to run and short enough to stay out
# of the way: nothing here projects anything.
_PERIODS = 6

# How many columns the hand-built ring runs through. Far more than a
# message can name and far fewer than a model has, which is the size a
# reader of somebody else's edited file has to survive being handed.
_RING = 2_000

# How many ids a cycle finding names, however long the loop is. Written out
# here rather than read off the module, so that moving the cap is a
# decision somebody made rather than a number that followed along.
_NAMED_IN_A_LOOP = 12


def _load(name: str) -> dict[str, Any]:
    """Return the checked-in artifact ``name`` from the goldens directory."""
    artifact: dict[str, Any] = json.loads((_GOLDENS / name).read_text("utf-8"))
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    nodes: list[dict[str, Any]] = artifact["nodes"]
    (found,) = [node for node in nodes if node["id"] == node_id]
    return found


def _artifact_for_a_two_column_model(
    *, profile: Literal["audit", "executable"] = "audit"
) -> dict[str, Any]:
    """Return the artifact of one arriving column times another.

    The smallest model that has anything to check: two inputs, one
    calculation reading both, and the two edges that say so. The
    ``executable`` profile writes each computed node's operation tree onto
    it, which is what lets a reader recompute a ``local_fingerprint`` rather
    than take it.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "death_rate": [0.001_23, 0.001_51],
            }
        )
    )
    af.death_claims = af.sum_assured * af.death_rate
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export(profile=profile))
    return artifact


def _artifact_for_a_model_handed_a_column_of_values() -> dict[str, Any]:
    """Return the artifact of a model handed a whole column at a line.

    ``af.simulated_shock = pl.Series(...)`` is data rather than a formula,
    and the file says both halves of that: ``kind: "input"``, which it shares
    with a column that arrived, and ``source: "injected"``, which is the
    producer saying the values were handed over at a line the model wrote.
    The two shapes are what a deep reading cannot recompute, and they are not
    unchecked for the same reason -- which is the whole of why this fixture
    carries one of each.
    """
    af = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0, 250_000.0, 300_000.0]})
    )
    af.simulated_shock = pl.Series([0.01, -0.02, 0.03])
    af.shocked_claims = af.sum_assured * (1.0 + af.simulated_shock)
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(profile="executable")
    )
    return artifact


def _artifact_for_a_model_with_a_mortality_lookup(
    table_payload_limit: int | None = TABLE_PAYLOAD_LIMIT,
) -> dict[str, Any]:
    """Return the artifact of a model whose one formula reads a mortality basis.

    The values travel with it by default: the entry carries the table's own
    processed frame, which is the frame the declared fingerprint was taken
    over, so a reader re-hashes what is in front of them rather than a
    reconstruction of it. A limit low enough to refuse them is how a caller
    asks for the other shape, where the entry keeps the identity and stands
    in for the values -- written by the producer rather than edited into the
    document afterwards, which is the edit the seal exists to catch.
    """
    mortality = Table(
        name="mortality",
        source=pl.DataFrame({"age": [40, 41, 42], "rate": [0.001, 0.001_2, 0.001_5]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"issue_age": [40, 42], "sum_assured": [100_000.0, 250_000.0]})
    )
    af.mort_rate = mortality.lookup(age=af.issue_age)
    af.death_claims = af.sum_assured * af.mort_rate
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(table_payload_limit=table_payload_limit)
    )
    return artifact


def _artifact_for_a_model_reading_a_schedule_and_a_curve() -> dict[str, Any]:
    """Return the artifact of a model reading the two bases that are not tables.

    A schedule and a curve are stamped under the recipe grammar rather than
    the content one, and each hands over the very canonical form its stamp
    was taken over -- so the deep reading has two grammars to get right, not
    one.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2]}))
    af = af.projection.set(
        schedule=Schedule.from_calendar_grid(
            start_date=datetime.date(2026, 1, 31), n_periods=_PERIODS, frequency="1M"
        )
    )
    af.years_elapsed = af.projection.t_years()
    curve = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.02, 0.025, 0.03])
    af.spot_rate = curve.spot_rate(af.years_elapsed)
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _an_enriched_artifact() -> dict[str, Any]:
    """Return the artifact of a projection carrying its own values and traces.

    A projection on purpose. A per-period column's sample is the whole run of
    values and a trace is a walk-through of one period, so the two agree at
    the first period and nowhere else -- which is the shape the enrichment
    reading has to be written against, and the one a model with only scalar
    columns would never show.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "issue_age": [40], "sum_assured": [100_000.0]})
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=45,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.mort_rate = af.attained_age * 0.000_1
    af.claims = af.sum_assured * af.mort_rate
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export(af.collect()))
    return artifact


def _an_enriched_artifact_with_a_broken_trace() -> dict[str, Any]:
    """Return an enriched artifact whose walk-through ends at the wrong number.

    A trace is a substitution: the formula with each name replaced by the
    value that column held. Its last line is therefore the sample beside it,
    and a trace ending somewhere else is a walk-through of a calculation the
    model did not do.
    """
    artifact = _an_enriched_artifact()
    _node(artifact, "claims@1")["trace"][-1]["result"] = 12.34
    return artifact


def _an_enriched_artifact_carrying_the_engines_own_rendering() -> dict[str, Any]:
    """Return an enriched artifact that also carries what the engine rendered.

    The pair the opening-line reading is about. A walk-through's first line
    is the engine's rendering of the calculation put through the producer's
    own cleaning, so an artifact carrying both the rendering and the
    walk-through has written one fact twice -- and two records of one fact
    are worth holding to each other.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "issue_age": [40], "sum_assured": [100_000.0]})
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=45,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.mort_rate = af.attained_age * 0.000_1
    af.claims = af.sum_assured * af.mort_rate
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(af.collect(), include_lowered=True)
    )
    return artifact


def _artifact_for_a_model_handed_a_discount_factor_vector() -> dict[str, Any]:
    """Return the artifact of discount factors worked out elsewhere and pasted in.

    The factors came off a curve, in Python, before the frame ever saw them,
    and what reaches the model is the answers with the question torn off.
    Nothing in the document ties them to the curve: the definition reads no
    column, names no assumption base, and is not a hole -- the assignment door
    recorded exactly what it was handed.
    """
    af = ActuarialFrame(pl.DataFrame({"claims": [100.0, 200.0]}))
    factors = [1.0 / 1.04**period for period in range(4)]
    af.disc_factors = pl.lit(
        pl.Series("disc_factors", [factors], dtype=pl.List(pl.Float64))
    ).first()
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_for_a_model_handed_a_mortality_vector() -> dict[str, Any]:
    """Return the artifact of a hand-typed mortality vector.

    The same shape as the discount factors above and a different subject, on
    purpose: the reading is about a definition that reads nothing and reaches
    into the engine, not about discounting. A tripwire that only knew about
    curves would let the basis through.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.qx = pl.lit(
        pl.Series("qx", [[0.001_23, 0.001_51, 0.001_88]], dtype=pl.List(pl.Float64))
    ).first()
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_for_a_model_handed_a_scalar_through_the_engine() -> dict[str, Any]:
    """Return the artifact of one number handed over in the engine's own language.

    ``pl.lit(0.05)`` and ``0.05`` are the same number and not the same record:
    the second is an operation this format names, whose value rides inside the
    node's own canonical bytes, and the first is a fragment of one engine's
    expression language that reads nothing. Both are written here so the
    boundary is pinned rather than described.
    """
    af = ActuarialFrame(pl.DataFrame({"reserve": [100.0, 200.0]}))
    af.lapse_shock = pl.lit(0.05)
    af.discount_rate = 0.04
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_for_a_model_handed_a_generator_that_determines_itself() -> dict[str, Any]:
    """Return the artifact of a line whose own recorded text fixes its values.

    ``pl.int_range(0, 2)`` reads nothing and reaches into the engine, so it
    wears the shape -- but nothing came off a curve and nothing was pasted:
    the text beside it determines every value it produces. The reading is
    right to fire, because the values still sit in a fragment of one
    engine's language rather than in the node's own bytes, and what the
    author can do about it is the other next move rather than the first.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.seq = pl.int_range(0, 2)
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_for_a_model_with_one_deliberate_escape_hatch() -> dict[str, Any]:
    """Return the artifact of a model with one line in the engine's own language.

    The framework's own operations reach into no engine, and this one line
    does -- deliberately, because the escape hatch is there to be used. What
    the artifact records is which engine it reached into, which is what makes
    the cost of it countable rather than a matter of opinion.
    """
    af = ActuarialFrame(pl.DataFrame({"reserve": [100.0, 200.0, 300.0]}))
    af.smoothed_reserve = pl.col("reserve").rolling_mean(window_size=2, min_samples=1)
    af.scaled_reserve = af.smoothed_reserve * 1.05
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _an_artifact_exported_with_the_source_spans_switched_off() -> dict[str, Any]:
    """Return an audit artifact carrying no as-written formula anywhere.

    What ``GASPATCHIO_SOURCE_SPANS=off`` produces: every field the format
    fills from a statement's own source is null. The nulls are written here
    rather than exported under the switch, because the point is the shape of
    the document a reader is handed, not the mechanism that produced it.
    """
    artifact = _artifact_for_a_two_column_model()
    for node in artifact["nodes"]:
        node["formula"] = None
        node["source_location"] = None
    return artifact


def _an_artifact_with_a_cycle() -> dict[str, Any]:
    """Return an artifact whose two calculations each claim to read the other.

    No model can be written this way. A definition is recorded after the
    statement that made it, so a column cannot read a result that does not
    exist yet, and the producer has no way to emit this. The loop is written
    into the exported record by hand -- which is the case a reader of
    somebody else's file has to be able to detect, because a file is a thing
    that can be edited after it was written.
    """
    af = ActuarialFrame(pl.DataFrame({"lapse_rate": [0.05, 0.06]}))
    af.policies_in_force = 1000.0 * (1.0 - af.lapse_rate)
    af.survivors = af.policies_in_force * 0.99
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())

    (opening,) = [n for n in artifact["nodes"] if n["id"] == "policies_in_force@1"]
    opening["reads"].append("survivors@1")
    artifact["edges"].append(
        {
            "source": "survivors@1",
            "target": "policies_in_force@1",
            "relationship": "DIRECT",
        }
    )
    return artifact


def _an_artifact_with_a_long_cycle() -> dict[str, Any]:
    """Return an artifact whose columns read each other round a long ring.

    Built by cloning one exported node, because nothing exports this either
    -- and a loop somebody edited into a file has no size the format
    promises, where a loop the producer wrote would have none at all. Every
    column reads the one before it and the first reads the last, so the
    whole file is one circle.
    """
    artifact = _artifact_for_a_two_column_model()
    template = _node(artifact, "death_claims@1")
    artifact["nodes"] = [
        {
            **copy.deepcopy(template),
            "id": f"c{index}@1",
            "column": f"c{index}",
            "reads": [f"c{(index - 1) % _RING}@1"],
        }
        for index in range(_RING)
    ]
    artifact["edges"] = []
    return artifact


def _artifact_for_a_model_that_redefines_policies_in_force() -> dict[str, Any]:
    """Return the artifact of a column the model wrote twice.

    The first definition is a whole-column literal, so nothing reads it and
    nothing it reads is a node: dropping it leaves a gap in the ordinals and
    nothing else wrong, which is what makes it the case to drop.
    """
    af = ActuarialFrame(pl.DataFrame({"lapse_rate": [0.05, 0.06]}))
    af.policies_in_force = 1000.0
    af.policies_in_force = 2000.0 * (1.0 - af.lapse_rate)
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


def _artifact_for_a_model_that_escalated_to_a_rollforward() -> dict[str, Any]:
    """Return the artifact of a model carrying a compiled state machine.

    The only shape this producer writes into a reserved id namespace: one
    compiled rollforward under ``rollforward:`` and one running state under
    ``state:``, each with a null column and a null version.
    """
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[0.01] * _PERIODS],
            "me_charge": [[0.001] * _PERIODS],
        }
    )
    frame = frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=_PERIODS,
        frequency="monthly",
    )
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    (
        builder["fund_value"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
    )
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")
    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )
    return artifact


def _artifact_for_a_term_model_with_a_hole_in_it() -> dict[str, Any]:
    """Return the artifact of a model reaching most of what a producer writes.

    A projection timeline, an assumption lookup varying by attained age, a
    cumulative survival, a conditional, a column the model defined twice, and
    one column written straight into the plan so that nothing accounts for
    it. Bigger than anything else here on purpose: the structural checks are
    about a whole graph, and a graph of three nodes is not one.
    """
    mortality = Table(
        name="validate_probe_mortality",
        source=pl.DataFrame(
            {
                "age": list(range(30, 122)),
                "rate": [0.001 * 1.05**step for step in range(92)],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "issue_age": [40, 45, 55],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "premium_pp": [500.0, 900.0, 1400.0],
            }
        )
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=121,
        frequency="monthly",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.mort_rate_mth = mortality.lookup(age=af.attained_age) / 12.0
    af.combined_decrement = af.mort_rate_mth + 0.005
    af.pols_if = af.combined_decrement.projection.cumulative_survival()
    af.claims = af.sum_assured * af.pols_if * af.mort_rate_mth
    af.premiums = af.premium_pp * af.pols_if
    af.commissions = when(af.month == 0).then(af.premiums).otherwise(0.0)
    af.net_cf = af.premiums - af.claims
    af.net_cf = af.net_cf - af.commissions
    # A column the model holds and nothing recorded: the one thing an
    # artifact says about itself that its own producer cannot explain.
    plan = af._df  # noqa: SLF001 -- written behind every door that records
    assert plan is not None
    af._df = plan.with_columns(pl.lit(1.0).alias("reserve_override"))  # noqa: SLF001
    artifact: dict[str, Any] = json.loads(GraphExporter(af).export())
    return artifact


# --- what a conforming artifact looks like -----------------------------------


def test_a_freshly_exported_artifact_is_valid() -> None:
    """The producer's own output passes its own reader."""
    assert validate_artifact(_artifact_for_a_two_column_model()).ok


@pytest.mark.parametrize("name", _CHECKED_IN)
def test_every_artifact_checked_in_beside_this_one_is_valid(name: str) -> None:
    """The corpus and the hand-built examples are held to the same bar.

    Two of these carry accounts nothing emits -- a product declared as states,
    a valuation struck by an inner model -- with null dtype and shape
    metadata and ids in namespaces this preview has not reserved. Every
    structural check has to hold for them as they are written, or the sections
    they stand behind are evidence of nothing.
    """
    assert validate_artifact(_load(name)).ok


def test_a_term_model_with_a_hole_in_it_is_still_a_valid_artifact() -> None:
    """A hole is something the artifact says, not something wrong with it.

    Nothing in the model accounts for that column, and the record of that is
    what the file is for: an artifact reporting an unexplained column is
    doing its job, and refusing it would be refusing the report.
    """
    artifact = _artifact_for_a_term_model_with_a_hole_in_it()
    report = validate_artifact(artifact)

    assert report.ok, [f.message for f in report.findings]
    assert [hole["column"] for hole in artifact["holes"]] == ["reserve_override"]
    assert {node["kind"] for node in artifact["nodes"]} == {
        "input",
        "computed",
        "hole",
    }


def test_a_model_that_escalated_to_a_rollforward_is_valid() -> None:
    """A compiled state machine and its running state are not columns.

    Both sit in a reserved id namespace with a null column and a null
    version, which is exactly what a node there is defined to look like.
    """
    assert validate_artifact(_artifact_for_a_model_that_escalated_to_a_rollforward()).ok


def test_an_artifact_arrives_as_a_document_a_file_or_the_text_of_one() -> None:
    """Whatever the caller is holding, they hold an artifact.

    ``GraphExporter.export()`` returns the text; a stored artifact is a path.
    Making a caller parse one and read the other before asking a question
    about it would be the framework reshaping itself to nobody's benefit.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.death_claims = af.sum_assured * 0.001_23
    text = GraphExporter(af).export()

    assert validate_artifact(text).ok
    assert validate_artifact(json.loads(text)).ok
    assert validate_artifact(_GOLDENS / "conformance_corpus.json").ok
    assert validate_artifact(str(_GOLDENS / "conformance_corpus.json")).ok


def test_a_string_that_is_neither_reading_is_reported_rather_than_raised() -> None:
    """Nothing was read, and what comes back says so in the reader's own voice.

    A string is two readings, and a caller who pasted something that is
    neither has read nothing at all -- so the answer names both attempts.
    An errno naming somebody's pasted text as a filename would be the one
    input in this module answered by the filesystem instead of by the
    reader.
    """
    report = validate_artifact("not json {{{")

    assert not report.ok
    assert report.schema == ""
    assert report.findings[0].where == "envelope"
    assert "not json {{{" in report.findings[0].message
    assert "does not parse as JSON" in report.findings[0].message
    assert "path of a stored file" in report.findings[0].message


def test_a_pasted_document_is_never_offered_to_the_filesystem() -> None:
    """Several kilobytes of text is not a filename and is not answered as one.

    What the filesystem would say about a name that long is about names,
    where the caller is asking about a document -- and the finding quotes
    the opening of what arrived rather than reciting all of it back.
    """
    pasted = "a pasted document that is not an artifact, " * 300
    report = validate_artifact(pasted)

    assert not report.ok
    assert "longer than any path" in report.findings[0].message
    assert len(report.findings[0].message) < 1_000


def test_a_bare_json_scalar_is_read_as_the_document_it_is() -> None:
    """``null`` is a document, and what is wrong with it is what it is.

    Nothing in it opens a document, so it is offered to the filesystem
    first and parsed after that -- and what comes back is the reading of a
    document with no envelope, which is the true thing to say about it.
    """
    report = validate_artifact("null")

    assert not report.ok
    assert report.findings[0].where == "envelope"
    assert "a null" in report.findings[0].message


# --- the schema layer --------------------------------------------------------


def test_an_unknown_schema_identifier_is_refused_by_name() -> None:
    """An identifier is a key, so an unknown one names the keys there are.

    The refusal cannot say "that version is too new", because nothing here
    parses the string for a version -- so what it can say, and does, is which
    identifiers this build resolves.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["schema"] = "gaspatchio-graph/v9"
    report = validate_artifact(artifact)

    assert not report.ok
    assert "gaspatchio-graph/v0-preview.1" in report.findings[0].message


def test_a_field_the_schema_refuses_is_reported_where_it_sits() -> None:
    """A finding a reader cannot locate is a finding they cannot act on."""
    artifact = _artifact_for_a_two_column_model()
    artifact["nodes"][0]["dtype"] = "decimal128"
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["schema"]
    assert report.findings[0].where == "/nodes/0/dtype"


def test_the_report_says_which_schema_it_read_the_artifact_under() -> None:
    """Two artifacts read under two schemas are two different readings."""
    report = validate_artifact(_artifact_for_a_two_column_model())

    assert report.report_version == REPORT_VERSION
    assert report.schema == "gaspatchio-graph/v0-preview.3"


# --- the structure layer -----------------------------------------------------


def test_an_edge_pointing_at_a_node_that_is_not_here_is_an_error() -> None:
    """An edge is two names, and both have to be accounts the file holds."""
    artifact = _artifact_for_a_two_column_model()
    artifact["edges"].append(
        {
            "source": "not_a_node",
            "target": "death_claims@1",
            "relationship": "DIRECT",
        }
    )
    report = validate_artifact(artifact)

    assert [f.section for f in report.findings] == ["semantic"]
    assert "not_a_node" in report.findings[0].message


def test_a_node_reading_a_name_the_file_does_not_carry_is_an_error() -> None:
    """``reads`` is the audit trail an impact cone is drawn through."""
    artifact = _artifact_for_a_two_column_model()
    (claims,) = [n for n in artifact["nodes"] if n["id"] == "death_claims@1"]
    claims["reads"].append("reinsurance_share")
    report = validate_artifact(artifact)

    assert not report.ok
    assert "reinsurance_share" in report.findings[0].message
    assert report.findings[0].where == "death_claims@1"


def test_a_cycle_is_an_error_naming_the_columns_in_it() -> None:
    """A column that reads its own result has no order to be evaluated in."""
    report = validate_artifact(_an_artifact_with_a_cycle())

    assert not report.ok
    assert "policies_in_force" in report.findings[0].message
    assert "survivors" in report.findings[0].message


def test_a_cycle_through_thousands_of_columns_is_still_a_message_to_read() -> None:
    """A finding is read by somebody, whatever a file was edited into.

    The loop is given at both ends with a count of what sits between them:
    where the walk met the circle, where it closes, and how much of the
    model is caught in it. Naming every column in a ring of two thousand
    would be a finding nobody reads to the end of.
    """
    report = validate_artifact(_an_artifact_with_a_long_cycle())

    (circle,) = [f for f in report.findings if "runs in a circle" in f.message]
    assert len(circle.message) < 1_000
    assert f"and {_RING + 1 - _NAMED_IN_A_LOOP} more in the loop" in circle.message
    assert "c0@1" in circle.message
    assert circle.message.count("->") == _NAMED_IN_A_LOOP


def test_a_missing_definition_ordinal_is_an_error() -> None:
    """The definitions before the last one are the history a diff is read from."""
    artifact = _artifact_for_a_model_that_redefines_policies_in_force()
    artifact["nodes"] = [
        n for n in artifact["nodes"] if n["id"] != "policies_in_force@1"
    ]
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["semantic"]
    assert "policies_in_force" in report.findings[0].message


def test_two_nodes_claiming_one_id_is_an_error() -> None:
    """Every read and every edge resolves through an id, so it has to be one."""
    artifact = _artifact_for_a_two_column_model()
    artifact["nodes"].append(dict(artifact["nodes"][0]))
    report = validate_artifact(artifact)

    assert not report.ok
    assert "sum_assured" in report.findings[0].message


def test_a_column_sitting_in_a_reserved_namespace_is_an_error() -> None:
    """What a reserved namespace is for is that a reader can trust it.

    A node under ``state:`` is one running rollforward state and not a column
    of the model, so a reader taking it for one would be reading the artifact
    correctly and getting the wrong answer.
    """
    artifact = _artifact_for_a_model_that_escalated_to_a_rollforward()
    (state,) = [n for n in artifact["nodes"] if n["id"].startswith("state:")]
    state["column"] = "fund_value"
    report = validate_artifact(artifact)

    assert not report.ok
    assert "state:" in report.findings[0].message


# --- reads and edges, which are one fact recorded twice -----------------------


def test_a_read_no_edge_accounts_for_refuses_the_artifact() -> None:
    """The lineage a reviewer traces and the graph they draw are one claim.

    Section 9 writes one edge per entry of the target's ``reads``, and puts
    no condition on it -- so a file short of one contradicts the format
    rather than falling short of it. What the reader is left holding is a
    dependency they can trace down the page and no impact cone drawn through
    the graph will ever reach.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["edges"] = [
        edge for edge in artifact["edges"] if edge["source"] != "death_rate"
    ]
    report = validate_artifact(artifact)

    (finding,) = [f for f in report.findings if f.severity == "error"]
    assert finding.where == "death_claims@1"
    assert "death_rate" in finding.message
    assert not report.ok


def test_an_edge_no_read_accounts_for_is_said_out_loud_and_not_refused() -> None:
    """And the other way round, which is the direction still settling.

    Section 9's narrowing vocabulary carries four row-shaping kinds no
    emission rule produces yet. A producer that shapes rows in one of them
    and records the dependency as an edge alone is writing a document the
    section arguably tolerates, and an error grade would refuse it, so this
    direction stays a warning until those four settle.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["nodes"] = [
        node | {"reads": []} if node["id"] == "death_claims@1" else node
        for node in artifact["nodes"]
    ]
    report = validate_artifact(artifact)

    warnings = [f for f in report.findings if f.severity == "warning"]
    assert len(warnings) == 2
    assert all("death_claims@1" in f.where for f in warnings)
    assert report.ok


def test_a_read_that_resolves_to_nothing_is_not_also_reported_as_a_missing_edge() -> (
    None
):
    """One defect, one finding. The dangling name is already an error."""
    artifact = _artifact_for_a_two_column_model()
    _node(artifact, "death_claims@1")["reads"].append("not_a_node")
    report = validate_artifact(artifact)

    assert [f.severity for f in report.findings] == ["error"]


def test_every_shipped_shape_records_its_reads_and_its_edges_alike() -> None:
    """The clean baseline: nothing this producer writes disagrees with itself."""
    for artifact in (
        _artifact_for_a_term_model_with_a_hole_in_it(),
        _artifact_for_a_model_that_escalated_to_a_rollforward(),
        _artifact_for_a_model_with_a_mortality_lookup(),
    ):
        assert not validate_artifact(artifact).findings


# --- what a leaf may claim ---------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "build", "leaf", "tier"),
    [
        ("input", _artifact_for_a_two_column_model, "sum_assured", "core"),
        (
            "state",
            _artifact_for_a_model_that_escalated_to_a_rollforward,
            "state:fund_value@eop",
            "opaque",
        ),
        (
            "hole",
            _artifact_for_a_term_model_with_a_hole_in_it,
            "reserve_override",
            "core",
        ),
    ],
)
def test_no_leaf_of_any_kind_may_state_a_tier(
    kind: str,
    build: Callable[[], dict[str, Any]],
    leaf: str,
    tier: str,
) -> None:
    """A tier says how much of a node's *tree* this format can account for.

    A leaf has no tree, which is why section 8 nulls the field on all three
    of them -- so a tier written on one is an accountability claim about a
    calculation that is not in the file. Section 8's three leaf kinds are
    covered together because the refusal is about what a leaf is rather than
    about which of the three it is: a column that arrived, a column nothing
    accounts for, and a running rollforward state each have their identity
    in a name and a type.
    """
    artifact = build()
    node = _node(artifact, leaf)
    assert node["kind"] == kind
    node["tier"] = tier
    report = validate_artifact(artifact)

    assert not report.ok
    (finding,) = [f for f in report.findings if f.severity == "error"]
    assert finding.where == leaf
    assert tier in finding.message


def _the_payload_example(kind: str) -> dict[str, Any]:
    """Return the hand-built example that carries a payload section of ``kind``."""
    return _load(f"{kind}_example.json")


@pytest.mark.parametrize(
    ("kind", "build"),
    [
        ("computed", _artifact_for_a_two_column_model),
        ("rollforward", _artifact_for_a_model_that_escalated_to_a_rollforward),
        ("state_graph", lambda: _the_payload_example("state_graph")),
        ("nested_valuation", lambda: _the_payload_example("nested_valuation")),
    ],
)
def test_a_node_that_computes_must_state_its_tier(
    kind: str,
    build: Callable[[], dict[str, Any]],
) -> None:
    """The rule a leaf is held to, the other way round.

    Section 11.2 states a tier on every node that has anything to execute,
    and section 8 nulls it only on a leaf. A null tier on a calculation
    reads as nothing to account for, which a calculation cannot be: a
    census of the model's tiers can count it nowhere, and a consumer
    deciding what runs in its own engine is told nothing about it. The
    schema allows the null, because a leaf needs it, so the semantic
    reading is where the rule is held. The four kinds that compute are
    covered together, the two payload sections among them.
    """
    artifact = build()
    node = next(one for one in artifact["nodes"] if one["kind"] == kind)
    node["tier"] = None
    report = validate_artifact(artifact)

    assert not report.ok
    errors = [f for f in report.findings if f.severity == "error"]
    assert [f.where for f in errors] == [node["id"]]
    assert "states no tier" in errors[0].message


def test_a_compiled_rollforward_states_a_tier_like_anything_else_that_computes() -> (
    None
):
    """It has a null column and a null version and is not a leaf.

    Section 8 is explicit that a compiled rollforward carries a tree of its
    own and therefore a stated tier. A reading keyed on the null version
    rather than on what the node is would refuse three shipped models.
    """
    artifact = _artifact_for_a_model_that_escalated_to_a_rollforward()
    (compiled,) = [node for node in artifact["nodes"] if node["kind"] == "rollforward"]

    assert (compiled["version"], compiled["tier"]) == (None, "core")
    assert validate_artifact(artifact).ok


# --- a vector handed over rather than computed --------------------------------


def test_a_discount_factor_vector_handed_over_has_nothing_tying_it_to_a_source() -> (
    None
):
    """The paste-as-values shape, in the artifact's own terms."""
    report = validate_artifact(_artifact_for_a_model_handed_a_discount_factor_vector())

    (finding,) = [f for f in report.findings if f.where == "disc_factors@1"]
    assert finding.severity == "warning"
    assert "curve.discount_factor" in finding.message
    assert report.ok


def test_a_hand_typed_mortality_vector_is_read_exactly_the_same_way() -> None:
    """The reading is about the shape of the record, not about discounting."""
    report = validate_artifact(_artifact_for_a_model_handed_a_mortality_vector())

    (finding,) = [f for f in report.findings if f.where == "qx@1"]
    assert finding.severity == "warning"


def test_a_line_that_determines_its_own_values_is_given_the_move_that_fits_it() -> None:
    """Reading it through a curve is no move at all for ``pl.int_range(0, 2)``.

    Nothing came off a curve or a table there -- the recorded text fixes
    every value the line produces -- so a remark offering only that next
    move would be telling the author to go and find a source that does not
    exist. The move that does fit is the one the format's own vocabulary
    supports: write the values in the framework's terms so they ride in the
    node's canonical bytes.
    """
    report = validate_artifact(
        _artifact_for_a_model_handed_a_generator_that_determines_itself()
    )

    (finding,) = [f for f in report.findings if f.where == "seq@1"]
    assert finding.severity == "warning"
    assert "the framework's own terms" in finding.message
    assert "node's canonical bytes" in finding.message


def test_an_engine_native_line_that_reads_a_column_is_not_a_handed_over_value() -> None:
    """The escape hatch is there to be used; using it on a column is not this."""
    report = validate_artifact(_artifact_for_a_model_with_one_deliberate_escape_hatch())

    assert not report.findings


def test_a_scalar_handed_over_through_the_engine_is_the_same_class() -> None:
    """And a scalar the format's own vocabulary carries is not.

    ``pl.lit(0.05)`` reads nothing and reaches into the engine; the number is
    in a fragment of one engine's language and nothing says where it came
    from. ``0.05`` records under the format's own ``lit`` operation at tier
    ``core``, so the value rides inside the node's canonical bytes and the
    model's own line is what states it.
    """
    report = validate_artifact(
        _artifact_for_a_model_handed_a_scalar_through_the_engine()
    )

    assert [f.where for f in report.findings] == ["lapse_shock@1"]


def test_a_column_of_values_injected_at_a_line_is_not_read_as_pasted() -> None:
    """An injection is located data, and the file says where it was located."""
    assert not validate_artifact(
        _artifact_for_a_model_handed_a_column_of_values()
    ).findings


# --- an answer the document states no type for --------------------------------


def test_a_column_the_frame_holds_with_no_type_stated_is_an_error() -> None:
    """Section 10's rule, on the half of a node that says what is in it.

    ``unknown`` is not a type, and the definition a frame ends on is the one
    place the format does not let a producer leave it. This producer never
    writes the shape -- an unnameable type on a column the frame holds is
    refused at export -- so the document is edited to reach it, which is the
    only way a reader meets one.
    """
    artifact = _artifact_for_a_two_column_model()
    node = _node(artifact, "death_claims@1")
    assert node["in_final_schema"] is True
    node["dtype"] = "unknown"
    report = validate_artifact(artifact)

    assert not report.ok
    (finding,) = [f for f in report.findings if f.severity == "error"]
    assert (finding.section, finding.where) == ("semantic", "death_claims@1")
    assert "``dtype: unknown``" in finding.message


def test_a_column_the_frame_holds_with_no_shape_stated_is_read_the_same_way() -> None:
    """The other half of the question, under the same rule rather than a weaker one.

    ``shape`` says how many values a column holds per policy. A consumer that
    cannot tell one number per policy from one per projection period has no
    account of the column either, which is why section 10 carries ``shape``
    in the same sentence.
    """
    artifact = _artifact_for_a_two_column_model()
    _node(artifact, "death_claims@1")["shape"] = "unknown"
    report = validate_artifact(artifact)

    assert not report.ok
    (finding,) = [f for f in report.findings if f.severity == "error"]
    assert finding.where == "death_claims@1"
    assert "``shape: unknown``" in finding.message


def test_a_node_short_of_both_is_one_finding_naming_both() -> None:
    """One node, one defect, one finding: the file has no account of a column.

    Two findings would report the shape of this reading rather than the state
    of the artifact. The reader's next move is the same either way, and a
    node short of both halves is not twice as wrong as one short of a half.
    """
    artifact = _artifact_for_a_two_column_model()
    node = _node(artifact, "death_claims@1")
    node["dtype"] = "unknown"
    node["shape"] = "unknown"
    report = validate_artifact(artifact)

    (finding,) = [f for f in report.findings if f.severity == "error"]
    assert "``dtype: unknown``" in finding.message
    assert "``shape: unknown``" in finding.message


def test_a_definition_the_model_wrote_over_may_go_untyped() -> None:
    """Only the model's answers carry real types; its history need not.

    This is the producer's own routine output rather than an edited document:
    a whole-column literal nothing reads is written over before the frame is
    collected, so no column is left to read a type off and the node goes out
    ``unknown``. Section 10 permits exactly that, and the reading above must
    not refuse a file this producer writes every time a model defines a
    column twice.
    """
    artifact = _artifact_for_a_model_that_redefines_policies_in_force()
    superseded = _node(artifact, "policies_in_force@1")

    assert (superseded["dtype"], superseded["shape"]) == ("unknown", "unknown")
    assert superseded["in_final_schema"] is False
    assert validate_artifact(artifact).ok


# --- the two facet declaration lists -----------------------------------------


def test_a_required_facet_nobody_understands_refuses_the_artifact() -> None:
    """The producer said the file does not mean what it looks like without it.

    Reading it anyway would be reading a document the producer did not write,
    which is the one thing the required list exists to stop.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["facets_required"] = ["acme_overlay"]
    report = validate_artifact(artifact)

    assert not report.ok
    assert "acme_overlay" in report.findings[0].message


def test_a_required_facet_the_file_does_not_hold_is_an_error() -> None:
    """Required and absent is the case only the required list can see.

    ``gaspatchio_lowered`` is a facet this build understands, so nothing
    refuses it for being unknown -- and with the file neither announcing it
    nor carrying it, neither of the other two readings of the lists has
    anything to say about it either. What is left is a producer requiring
    something the document does not hold, which is the producer saying the
    file does not mean what it appears to and then not supplying what would
    make it mean anything else.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["facets_required"] = ["gaspatchio_lowered"]
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["semantic"]
    assert report.findings[0].where == "envelope"
    assert report.findings[0].message == (
        "The facet 'gaspatchio_lowered' is named in ``facets_required`` and "
        "this file neither announces it in ``facets_used`` nor carries it -- "
        "not on the envelope, and not on any node. Required is the producer "
        "saying the artifact does not mean what it appears to mean without "
        "that facet, so a reader that understands the name has nothing here "
        "to read the document under, and a reader that does not is refused "
        "the file over something that is not in it. Anything required is "
        "announced, and anything announced is carried. Export the model "
        "again."
    )


def test_a_required_facet_announced_and_never_carried_is_still_one_error() -> None:
    """Required is announced and present, and one absence is one finding.

    The file announces the facet and does not carry it, which is already a
    reading of the lists: an announcement with nothing behind it. Marking it
    required as well does not make that a second thing wrong, so the reader
    is told the one true thing once rather than twice.
    """
    artifact = _artifact_for_a_two_column_model()
    artifact["facets_used"] = sorted([*artifact["facets_used"], "gaspatchio_lowered"])
    artifact["facets_required"] = ["gaspatchio_lowered"]
    report = validate_artifact(artifact)

    assert not report.ok
    assert len(report.findings) == 1
    assert "nothing in this file carries it" in report.findings[0].message


def test_a_facet_nobody_understands_that_is_not_required_is_accepted() -> None:
    """An extension a reader ignores is the mechanism working, not failing."""
    artifact = _artifact_for_a_two_column_model()
    artifact["facets"]["acme_overlay"] = {
        "_producer": "https://acme.example",
        "_schemaURL": "https://acme.example/s.json",
    }
    artifact["facets_used"] = sorted([*artifact["facets_used"], "acme_overlay"])

    assert validate_artifact(artifact).ok


def test_a_facet_carried_and_never_announced_is_an_error() -> None:
    """``facets_used`` is read instead of the whole document, so it has to be true."""
    artifact = _artifact_for_a_two_column_model()
    artifact["nodes"][0]["facets"]["acme_overlay"] = {
        "_producer": "https://acme.example",
        "_schemaURL": "https://acme.example/s.json",
    }
    report = validate_artifact(artifact)

    assert not report.ok
    assert "acme_overlay" in report.findings[0].message


def test_a_facet_announced_and_never_carried_is_an_error() -> None:
    """A name with nothing behind it sends a reader looking for what is not there."""
    artifact = _artifact_for_a_two_column_model()
    artifact["facets_used"] = sorted([*artifact["facets_used"], "acme_overlay"])
    report = validate_artifact(artifact)

    assert not report.ok
    assert "acme_overlay" in report.findings[0].message


def test_the_facets_this_build_produces_are_the_ones_it_understands() -> None:
    """Requiring what this build writes is not a refusal.

    The executable profile's own rollforward facet is announced in
    ``facets_used`` and never required; a producer that did require it would
    still be asking for something this build knows.
    """
    artifact = _artifact_for_a_model_that_escalated_to_a_rollforward()
    artifact["facets_required"] = list(artifact["facets_used"])

    assert artifact["facets_used"] == [
        "gaspatchio_column_transformation",
        "gaspatchio_rollforward_ir",
    ]
    assert validate_artifact(artifact).ok


# --- the report itself -------------------------------------------------------


def test_a_report_says_what_it_found_in_a_form_a_pipeline_can_read() -> None:
    """Hole-freeness and conformance become things a step can check."""
    artifact = _artifact_for_a_two_column_model()
    artifact["facets_required"] = ["acme_overlay"]
    written = validate_artifact(artifact).to_dict()

    assert written["report_version"] == REPORT_VERSION
    assert written["schema"] == "gaspatchio-graph/v0-preview.3"
    assert written["sections"] == ["schema", "semantic"]
    assert written["ok"] is False
    assert written["findings"][0]["section"] == "semantic"
    assert written["findings"][0]["severity"] == "error"
    assert json.loads(json.dumps(written)) == written


def test_a_report_carrying_only_warnings_is_still_ok() -> None:
    """``ok`` is about errors: a warning is something to read, not a refusal."""
    report = ValidationReport(
        report_version=REPORT_VERSION,
        schema="gaspatchio-graph/v0-preview.1",
        sections=("schema", "semantic"),
        findings=(
            Finding(
                section="semantic",
                severity="warning",
                where="envelope",
                message="Something worth a reader's attention.",
            ),
        ),
    )

    assert report.ok
    assert report.to_dict()["findings"][0]["severity"] == "warning"


def test_the_deep_reading_adds_to_the_shallow_one_rather_than_replacing_it() -> None:
    """Asking for more is asking for more, and a clean artifact stays clean.

    The deep reading recomputes what the shallow one takes as written, so it
    can only ever add findings to a document the shallow one already read.
    On an artifact with nothing wrong with it, what it adds is the one thing
    an ``audit`` artifact cannot check about itself: its leaves, whose
    canonical bytes are the operation trees the profile does not carry.

    It used to add two. The second was that the document carried no seal, and
    that remark retired when the seal became the default emission: this
    artifact carries one, the deep reading recomputes it, and a recomputation
    that agrees has nothing to remark on.
    """
    artifact = _artifact_for_a_two_column_model()
    shallow = validate_artifact(artifact)
    deep = validate_artifact(artifact, deep=True)

    assert shallow.ok
    assert deep.ok
    assert shallow.findings == ()
    assert [f.severity for f in deep.findings] == ["warning"]


def test_a_document_that_is_not_an_envelope_is_reported_rather_than_raised() -> None:
    """A validator that crashes on a bad file has told the reader nothing."""
    report = validate_artifact("[]")

    assert not report.ok
    assert report.schema == ""
    assert report.findings[0].where == "envelope"


# --- the identity reading ----------------------------------------------------


def test_the_published_corpus_survives_the_deep_reading() -> None:
    """The digests this format published are the digests this reader derives.

    The corpus exists so a second implementation can prove agreement before
    claiming it, and this reader is a consumer of the format like any other:
    it recomputes every propagation and the one digest standing for the whole
    model, from the file and section 12's rules alone.
    """
    report = validate_artifact(_load("conformance_corpus.json"), deep=True)

    assert report.ok, [f.message for f in report.findings]


def test_a_tampered_fingerprint_is_caught_by_the_deep_check() -> None:
    """A node's fingerprint follows from what it computes and what it reads.

    So a digest edited in the file no longer follows from either, and the
    recomputation is what turns "the producer says so" into something the
    holder of the file checked.
    """
    artifact = _artifact_for_a_two_column_model()
    _node(artifact, "death_claims@1")["fingerprint"] = "sha256:" + "0" * 64

    assert not validate_artifact(artifact, deep=True).ok


def test_a_tampered_graph_fingerprint_is_caught_by_the_deep_check() -> None:
    """One digest stands for the whole model, and it is derived, not declared."""
    artifact = _artifact_for_a_two_column_model()
    artifact["graph_fingerprint"] = "sha256:" + "0" * 64
    report = validate_artifact(artifact, deep=True)

    assert not report.ok
    assert any(f.where == "envelope" and f.severity == "error" for f in report.findings)


def test_the_deep_check_cannot_verify_a_leaf_in_the_audit_profile() -> None:
    """Stated as a test because it is what the specification promises.

    An ``audit`` artifact carries no operation trees, so nothing in it can be
    hashed back to a ``local_fingerprint``. What the profile verifies is its
    structure and its propagation -- the joins between the links rather than
    the links themselves -- and a reader is told which of the two they got.
    """
    artifact = _artifact_for_a_two_column_model()
    _node(artifact, "sum_assured")["local_fingerprint"] = "sha256:" + "1" * 64
    report = validate_artifact(artifact, deep=True)

    assert any(f.severity == "warning" and "leaf" in f.message for f in report.findings)


def test_the_executable_profile_verifies_its_own_computed_trees() -> None:
    """The profile that carries the trees is the one that checks its own links.

    Named for what it verifies rather than for the word "leaf": in this
    profile every *computed* node's operation tree is present and is hashed
    back to the digest beside it, while a node carrying no tree is still
    unchecked.

    Not "verifies its own leaves", because a node carrying no tree is not one
    thing here. ``kind: "input"`` covers both a column that arrived with the
    data, whose bytes are its tag, its name and its type, and a column of
    values handed over at a line, whose ``local_fingerprint`` was taken over
    the values themselves in a record neither profile writes. A claim about
    "the leaves" would therefore be a claim about only some of the nodes it
    appeared to be about.
    """
    artifact = _artifact_for_a_two_column_model(profile="executable")
    _node(artifact, "death_claims@1")["local_fingerprint"] = "sha256:" + "2" * 64
    report = validate_artifact(artifact, deep=True)

    assert not report.ok
    # Named against the message rather than against ``ok``: a moved
    # ``local_fingerprint`` also stops its own ``fingerprint`` following from
    # it, so propagation refuses this artifact in either profile. What only
    # this profile can say is which of the two digests moved.
    assert any(
        "operation tree beside it" in f.message and f.where == "death_claims@1"
        for f in report.findings
    )


def test_a_column_the_data_arrived_with_is_described_as_the_leaf_it_is() -> None:
    """The remark about what was not recomputed says why, for that node.

    An arriving column is a node nothing on the model defines, so its
    identity is its name and its type -- and the reader is pointed at the
    one place that claim can be read against anything, which is the column
    the data actually arrived with.
    """
    artifact = _artifact_for_a_model_handed_a_column_of_values()
    report = validate_artifact(artifact, deep=True)
    (leaf,) = [f for f in report.findings if "a leaf carries no" in f.message]

    assert report.ok, [f.message for f in report.findings]
    assert leaf.severity == "warning"
    assert leaf.where == "envelope"
    assert "One of this artifact's 3 nodes had its" in leaf.message
    assert "the column the data actually arrived with" in leaf.message


def test_a_column_of_values_handed_over_at_a_line_is_not_called_an_arriving_one() -> (
    None
):
    """``af.simulated_shock = pl.Series(...)`` is defined by the model.

    It carries no operation tree either, so it is counted among the nodes
    whose digest was read rather than taken again -- but nothing else the
    leaf sentence says is true of it. The model does define it, at a line
    the file records; its identity is not its name and its type but the
    values themselves; and a reader sent looking for "the column the data
    arrived with" would find no such column. What is true of it is said
    instead, and the next move is one that exists for it.
    """
    artifact = _artifact_for_a_model_handed_a_column_of_values()
    (injected,) = [n for n in artifact["nodes"] if n.get("provenance") == "injected"]
    report = validate_artifact(artifact, deep=True)
    (handed_over,) = [f for f in report.findings if "handed to the model" in f.message]

    assert injected["id"] == "simulated_shock@1"
    assert injected["kind"] == "input"
    assert handed_over.severity == "warning"
    assert handed_over.where == "envelope"
    assert handed_over.message == (
        "One of this artifact's 3 nodes had its ``local_fingerprint`` read "
        "rather than recomputed, because a column of values handed to the "
        "model at a line carries no operation tree in either profile, and it "
        "is not a leaf either -- the model does define it, and its "
        "``local_fingerprint`` was taken over the values themselves rather "
        "than over its name and its type, in an injection record neither "
        "profile writes beside the node. A ``local_fingerprint`` is the leaf "
        "of the identity chain; what was checked here is that every "
        "``fingerprint`` follows from the leaf published beside it and from "
        "what the node reads -- the joins between the links rather than the "
        "links themselves. Read such a column against the same column in "
        "another run: the same values stamp alike wherever they were handed "
        "over and under whatever name, so what moves that digest is the data "
        "itself changing -- which is the comparison it exists for."
    )


def test_an_operation_tree_the_vocabulary_does_not_hold_is_reported() -> None:
    """A tree this reader cannot parse is a finding, not a traceback."""
    artifact = _artifact_for_a_two_column_model(profile="executable")
    _node(artifact, "death_claims@1")["expr"] = {"op": "acme_native"}
    report = validate_artifact(artifact, deep=True)

    assert not report.ok
    assert any(f.where == "death_claims@1" for f in report.findings)


def test_a_tampered_assumption_payload_is_caught() -> None:
    """The values travel so that a reader can check them, and this is the check."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()
    artifact["assumptions"][0]["payload"]["rows"][0][1] = 0.99
    report = validate_artifact(artifact, deep=True)

    assert not report.ok
    assert any(
        "mortality" in finding.message
        for finding in report.findings
        if finding.severity == "error"
    )


def test_an_untouched_assumption_payload_re_hashes_to_what_is_written_beside_it() -> (
    None
):
    """A table's payload is the frame the producer hashed, not a view of it."""
    report = validate_artifact(
        _artifact_for_a_model_with_a_mortality_lookup(), deep=True
    )

    assert report.ok, [f.message for f in report.findings]


def test_a_payload_read_back_in_another_row_order_no_longer_hashes_to_its_digest() -> (
    None
):
    """Section 13's rule: the payload's own row order, no projection, no re-sort.

    The values are the ones the producer hashed and only the order has moved,
    so a reader that tidied the payload first -- sorting by the dimension, on
    the reasonable-looking theory that a table is keyed -- would reach the
    declared digest again and report a file that agrees with itself when it
    does not. Two rows are swapped rather than the whole payload reversed:
    the order left behind is neither ascending nor descending, so it cannot
    be arrived at by sorting in either direction, and the rule is pinned by
    what the re-hash refuses rather than by what the fixture happened to
    arrive in.
    """
    artifact = _artifact_for_a_model_with_a_mortality_lookup()
    entry = artifact["assumptions"][0]
    rows = entry["payload"]["rows"]
    entry["payload"]["rows"] = [rows[1], rows[0], *rows[2:]]
    report = validate_artifact(artifact, deep=True)

    assert sorted(entry["payload"]["rows"]) == sorted(rows)
    assert entry["payload"]["rows"] != sorted(rows)
    assert entry["payload"]["rows"] != sorted(rows, reverse=True)
    assert not report.ok
    (disagrees,) = [f for f in report.findings if f.where == "/assumptions/0"]
    assert entry["fingerprint"] in disagrees.message
    assert "not a view of it and not a re-sort of it" in disagrees.message


def test_a_schedule_and_a_curve_are_re_hashed_under_the_recipe_grammar() -> None:
    """Two of the three kinds are stamped under the other grammar, and both check."""
    artifact = _artifact_for_a_model_reading_a_schedule_and_a_curve()

    assert {entry["kind"] for entry in artifact["assumptions"]} == {"schedule", "curve"}
    assert validate_artifact(artifact, deep=True).ok


def test_a_tampered_curve_payload_is_caught() -> None:
    """A recipe is a canonical JSON encoding, so a rate moved in it moves the stamp."""
    artifact = _artifact_for_a_model_reading_a_schedule_and_a_curve()
    (curve,) = [e for e in artifact["assumptions"] if e["kind"] == "curve"]
    curve["payload"]["rates"][0] = 0.99
    report = validate_artifact(artifact, deep=True)

    assert not report.ok


def test_a_payload_left_out_is_a_claim_about_data_held_somewhere_else() -> None:
    """Nothing to re-hash is not the same as a re-hash that failed.

    The producer weighed the values and declined to carry them, so what the
    fingerprint says is a claim about a file the reader has to go and get.
    Saying so is the finding; refusing the artifact would be refusing the
    producer's own honest account of what it left out.

    The document is asked of the producer rather than edited into shape, and
    the difference matters now that a document carries its own seal: an
    exported-then-edited document is precisely what the seal refuses, so a
    test that edited one would be checking the payload reading through a
    refusal about something else. A payload limit of zero is how a caller
    asks for this shape, and what comes back is a file its producer wrote.
    """
    artifact = _artifact_for_a_model_with_a_mortality_lookup(table_payload_limit=0)
    report = validate_artifact(artifact, deep=True)

    assert artifact["assumptions"][0]["payload"]["omitted"] == "size"
    assert report.ok
    assert any(
        f.severity == "warning" and "held elsewhere" in f.message
        for f in report.findings
    )


def test_the_hand_built_examples_hold_up_to_the_deep_reading() -> None:
    """Every identity that follows from their records was taken over them.

    Section 17's two examples stand behind the *shape* of what a producer
    would write, and they are written again by
    ``tests/graph/test_hand_built_goldens.py`` rather than edited: each leaf's
    digest from its own name and type, every fingerprint folded over what the
    node reads, the graph's, and the seal. So the deep reading, which takes
    all of those again, finds nothing to refuse; what it cannot reach -- a
    computed node's tree, absent from the ``audit`` profile -- it says it read
    as written rather than passing over it.
    """
    for name in ("state_graph_example.json", "nested_valuation_example.json"):
        artifact = _load(name)

        assert validate_artifact(artifact).ok
        deep = validate_artifact(artifact, deep=True)
        assert deep.ok, [f.message for f in deep.findings if f.severity == "error"]
        assert any("read rather than recomputed" in f.message for f in deep.findings)


# --- the enrichment reading --------------------------------------------------


def test_a_freshly_enriched_export_passes_its_own_enrichment_reading() -> None:
    """A per-period column's trace ends at the first period, and that is right."""
    report = validate_artifact(_an_enriched_artifact())

    assert report.ok, [f.message for f in report.findings]
    assert _node(_an_enriched_artifact(), "claims@1")["trace"]


def test_a_trace_that_does_not_produce_its_own_stated_result_is_an_error() -> None:
    """A walk-through ending somewhere other than the number beside it."""
    artifact = _an_enriched_artifact_with_a_broken_trace()
    report = validate_artifact(artifact)

    assert [f.section for f in report.findings] == ["enrichment"]
    assert report.findings[0].where == "claims@1"


def test_a_trace_with_no_sample_beside_it_is_an_error() -> None:
    """The trace substitutes the sample in, so a trace without one shows nothing."""
    artifact = _an_enriched_artifact()
    _node(artifact, "claims@1")["value_sample"] = None
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["enrichment"]


def test_a_value_on_a_definition_the_frame_no_longer_holds_is_an_error() -> None:
    """A superseded definition shown carrying the value that replaced it.

    The wrong number against the right formula, which is worse than no number
    at all: a reader checking the calculation would find it correct and would
    be reading the wrong calculation.
    """
    artifact = _an_enriched_artifact()
    _node(artifact, "claims@1")["in_final_schema"] = False
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["enrichment"]


def test_a_sample_on_a_superseded_definition_that_declares_nothing_is_an_error() -> (
    None
):
    """The refusal is on the value alone, with no walk-through beside it.

    What lifts it is one thing and one thing only -- the producer stating
    that it held this definition's own output to the export. A value with no
    such statement is still read off the finished frame, and the finished
    frame holds the definition that replaced this one.
    """
    artifact = _an_enriched_artifact()
    superseded = _node(artifact, "claims@1")
    superseded["in_final_schema"] = False
    superseded["trace"] = None
    report = validate_artifact(artifact)

    assert not report.ok
    assert [f.section for f in report.findings] == ["enrichment"]
    assert "carries enrichment" in report.findings[0].message


def test_a_walk_through_on_a_superseded_definition_that_declares_nothing_is_too() -> (
    None
):
    """And on the walk-through alone, which is the same number one step longer."""
    artifact = _an_enriched_artifact()
    superseded = _node(artifact, "claims@1")
    superseded["in_final_schema"] = False
    superseded["value_sample"] = None
    report = validate_artifact(artifact)

    assert not report.ok
    assert any("carries enrichment" in f.message for f in report.findings)


def test_the_refusal_names_retention_as_well_as_re_export() -> None:
    """A reader met by this refusal has two moves, and the message says both.

    Re-exporting from the frame the values were read from was the only way
    out when the refusal was written, and it is the wrong one for a producer
    that wanted these values kept: what it should reach for is holding this
    definition's own output to the export and declaring it. A message naming
    only the first would send that reader to throw away the very thing they
    were trying to show.
    """
    artifact = _an_enriched_artifact()
    _node(artifact, "claims@1")["in_final_schema"] = False
    (finding,) = validate_artifact(artifact).findings

    assert "Export the model again" in finding.message
    assert "``retained: true``" in finding.message


def test_a_superseded_definition_declaring_its_retention_may_carry_values() -> None:
    """``retained: true`` is the producer saying which frame the number is from.

    It held that definition's own output to the export and read the value off
    it, which is the one reading under which the number belongs to the formula
    printed beside it. A producer that did not retain cannot write the word by
    accident, which is why it lifts the refusal rather than weakening it.
    """
    artifact = _an_enriched_artifact()
    superseded = _node(artifact, "claims@1")
    superseded["in_final_schema"] = False
    superseded["retained"] = True
    report = validate_artifact(artifact)

    assert report.ok, [f.message for f in report.findings]


def test_retention_claimed_by_the_definition_the_frame_holds_is_an_error() -> None:
    """A live column has nothing to retain, so the claim describes no frame.

    Read under the structural layer rather than the enrichment one: it is a
    claim the record makes about itself, and a node can carry the field with
    no values for the enrichment reading to have met it at all.
    """
    artifact = _an_enriched_artifact()
    _node(artifact, "claims@1")["retained"] = True
    report = validate_artifact(artifact)

    assert not report.ok
    (finding,) = [f for f in report.findings if f.section == "semantic"]
    assert finding.where == "claims@1"
    assert finding.severity == "error"


def test_a_walk_through_opens_on_the_rendering_the_artifact_carries() -> None:
    """The clean baseline: the producer's own pair agrees with itself."""
    report = validate_artifact(
        _an_enriched_artifact_carrying_the_engines_own_rendering()
    )

    assert not report.findings


def test_a_walk_through_that_opens_on_something_else_is_a_warning() -> None:
    """Two records of one calculation, and they must tell one story."""
    artifact = _an_enriched_artifact_carrying_the_engines_own_rendering()
    _node(artifact, "claims@1")["trace"][0]["expr"] = "(sum_assured) * (lapse_rate)"
    report = validate_artifact(artifact)

    (finding,) = [f for f in report.findings if f.where == "claims@1"]
    assert finding.severity == "warning"
    assert "lapse_rate" in finding.message
    assert report.ok


def test_the_rendering_moving_under_an_unchanged_walk_through_reads_the_same() -> None:
    """Which of the two moved is not on the wire, so neither is accused."""
    artifact = _an_enriched_artifact_carrying_the_engines_own_rendering()
    lowered = _node(artifact, "claims@1")["facets"]["gaspatchio_lowered"]
    lowered["text"] = 'col("sum_assured") * col("premium_rate")'
    report = validate_artifact(artifact)

    (finding,) = [f for f in report.findings if f.where == "claims@1"]
    assert finding.severity == "warning"


def test_an_export_carrying_no_rendering_says_nothing_about_its_walk_through() -> None:
    """The reading needs both records; one of them is off by default."""
    artifact = _an_enriched_artifact()
    assert all("gaspatchio_lowered" not in node["facets"] for node in artifact["nodes"])

    assert not validate_artifact(artifact).findings


# --- the portability reading -------------------------------------------------


def test_the_portability_section_names_exactly_the_nodes_that_refuse() -> None:
    """Making the escape hatches countable is what turns portability into a number.

    One refusal here and two remarks beside it. The refusal is the line that
    has to be rewritten, and it is the only one: ``scaled_reserve`` is a
    multiplication in the format's own vocabulary and needs no rewriting at
    all. The remarks are the caveat on the question -- nothing in this
    artifact names ``jax``, and a reading silent about that hands back the
    same answer for an engine this model does not need and for an engine
    somebody misspelt -- and the reach, because ``scaled_reserve`` reads the
    escaped column and so is a column ``jax`` does not produce either.
    """
    artifact = _artifact_for_a_model_with_one_deliberate_escape_hatch()
    report = validate_artifact(artifact, engine="jax")
    refusing = [
        f.where
        for f in report.findings
        if f.section == "portability" and f.severity == "error"
    ]

    assert refusing == ["smoothed_reserve@1"]
    assert [f.where for f in report.findings if f.severity == "warning"] == [
        "envelope",
        "scaled_reserve@1",
    ]


def test_the_engine_a_node_actually_names_can_run_it() -> None:
    """The same artifact against the engine its one escape hatch is written for."""
    artifact = _artifact_for_a_model_with_one_deliberate_escape_hatch()
    report = validate_artifact(artifact, engine="polars")

    assert report.ok
    assert [f for f in report.findings if f.section == "portability"] == []


def test_an_absent_engines_field_is_no_claim_rather_than_a_refusal() -> None:
    """A producer that cannot see what a node needs says nothing, not nothing-needed."""
    artifact = _artifact_for_a_two_column_model()
    for node in artifact["nodes"]:
        node.pop("engines", None)
    report = validate_artifact(artifact, engine="jax")

    assert report.ok
    assert all(f.severity == "warning" for f in report.findings)


def test_a_node_the_producer_could_not_classify_refuses_every_engine() -> None:
    """``opaque`` is the producer saying it does not know what this node does.

    This build classifies everything it emits, so the tier is written in by
    hand -- which is the case a reader of somebody else's file meets, and the
    one an engine has to be told about before it plans a run.
    """
    artifact = _artifact_for_a_two_column_model()
    _node(artifact, "death_claims@1")["tier"] = "opaque"
    report = validate_artifact(artifact, engine="polars")

    assert not report.ok
    assert [
        f.where
        for f in report.findings
        if f.section == "portability" and f.severity == "error"
    ] == ["death_claims@1"]


def test_no_engine_named_is_no_portability_reading_at_all() -> None:
    """The section answers a question about one engine, so it needs one named."""
    artifact = _artifact_for_a_model_with_one_deliberate_escape_hatch()
    report = validate_artifact(artifact)

    assert report.ok
    assert [f for f in report.findings if f.section == "portability"] == []


def test_an_engine_this_artifact_names_nowhere_is_said_out_loud() -> None:
    """A mistyped engine name otherwise reads as a portability answer.

    ``"polar"`` for ``polars`` returns the node that names ``polars`` as a
    refusal, which is what a genuinely unsupported engine returns too. The
    reader is told which of the two they are holding by being told what the
    file does name -- and no list of real engines is kept here to check the
    name against, because the artifact is what the question is asked of.
    """
    artifact = _artifact_for_a_model_with_one_deliberate_escape_hatch()
    report = validate_artifact(artifact, engine="polar")
    (unnamed,) = [f for f in report.findings if f.where == "envelope"]

    assert not report.ok
    assert unnamed.section == "portability"
    assert unnamed.severity == "warning"
    assert "No node in this artifact names 'polar'" in unnamed.message
    assert "The engines it does name are 'polars'." in unnamed.message


def test_a_model_naming_no_engine_at_all_says_that_rather_than_nothing() -> None:
    """Every node reaching into no engine is an answer, and it is stated as one.

    The same remark fires, because the name reaches nothing here either --
    and what it says of this artifact is the true and reassuring half: no
    node names any engine, which is what a model written entirely in the
    format's own operations looks like.
    """
    report = validate_artifact(_artifact_for_a_two_column_model(), engine="polars")
    (unnamed,) = [f for f in report.findings if f.section == "portability"]

    assert report.ok
    assert "No node in it names any engine at all" in unnamed.message


# --- which readings the report gave ------------------------------------------


def test_the_report_names_the_readings_it_gave() -> None:
    """Nothing found and never asked are one answer until the report says.

    Both come back as a section with no findings under it, so a caller
    reading ``ok`` on an artifact nobody asked a portability question about
    would be reading a clean bill for a reading that never happened.
    """
    artifact = _artifact_for_a_model_with_one_deliberate_escape_hatch()

    assert validate_artifact(artifact).sections == ("schema", "semantic")
    assert validate_artifact(artifact, engine="polars").sections == (
        "schema",
        "semantic",
        "portability",
    )
    assert validate_artifact(_an_enriched_artifact()).sections == (
        "schema",
        "semantic",
        "enrichment",
    )


def test_a_deep_reading_names_no_section_of_its_own() -> None:
    """What ``deep`` recomputes is reported under ``semantic``, which ran anyway.

    Whether the digests were taken again is the caller's own argument, and a
    report restating it would be the report agreeing with the caller rather
    than saying anything about the artifact.
    """
    artifact = _artifact_for_a_two_column_model()

    assert validate_artifact(artifact, deep=True).sections == ("schema", "semantic")


def test_a_document_nothing_could_be_read_from_names_no_readings() -> None:
    """Nothing was read, so no reading ran, and the report says so twice over."""
    report = validate_artifact("not json {{{")

    assert report.sections == ()
    assert report.to_dict()["sections"] == []


# --- an artifact with no audit surface ---------------------------------------


def test_an_audit_artifact_with_no_as_written_formulas_is_a_warning() -> None:
    """It is permitted, it is honest, and it has nothing for a reviewer to read.

    ``formula`` is the audit surface: it is what a reviewer reads to see the
    calculation and what a comparison between two quarters is a comparison
    of. An export with source spans switched off produces a document with
    none of it, and the validator is where that is said out loud rather than
    noticed on the morning of the meeting.

    Both ways of arriving here are named, because only one of them is the
    switch. A model built at a prompt or in an interactive session has no
    source text behind its statements at all, reaches this same document
    with the spans fully on, and would otherwise be advised to switch on
    what is already on.
    """
    artifact = _an_artifact_exported_with_the_source_spans_switched_off()
    report = validate_artifact(artifact)

    assert report.ok
    assert [(f.section, f.severity, f.where) for f in report.findings] == [
        ("semantic", "warning", "envelope")
    ]
    assert "formula" in report.findings[0].message
    assert "GASPATCHIO_SOURCE_SPANS=off" in report.findings[0].message
    assert "no source text for the exporter to read" in report.findings[0].message
    assert "from a file the statements were written in" in report.findings[0].message


def test_one_formula_still_written_is_not_a_document_with_no_audit_surface() -> None:
    """The warning is about a document with nothing to read, not about a gap.

    A null ``formula`` is routine and normative -- a rename, a join, a batch
    call and a timeline configuration all write one -- so a document is short
    of its audit surface only when every computed node is.
    """
    artifact = _an_artifact_exported_with_the_source_spans_switched_off()
    _node(artifact, "death_claims@1")["formula"] = "af.sum_assured * af.death_rate"

    assert validate_artifact(artifact).findings == ()


# --- the operation tree's branches are closed --------------------------------


_A_CALL_RELABELLED: Final[dict[str, Any]] = {
    "op": "state",
    "name": "projection.at_period",
    "args": [
        {"op": "col", "name": "sum_assured"},
        {"op": "lit", "value": 0.0},
    ],
    "attrs": {"relative_period": -1},
}


def _with_tree(tree: dict[str, Any]) -> dict[str, Any]:
    """Return an executable artifact whose one computed node carries ``tree``."""
    artifact = _artifact_for_a_two_column_model(profile="executable")
    _node(artifact, "death_claims@1")["expr"] = tree
    return artifact


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(_A_CALL_RELABELLED, id="a call relabelled to state"),
        pytest.param(
            {
                "op": "col",
                "name": "projection.at_period",
                "args": [{"op": "col", "name": "sum_assured"}],
            },
            id="a call relabelled to col",
        ),
        pytest.param(
            {
                "op": "binop",
                "kind": "mul",
                "left": {"op": "col", "name": "sum_assured"},
                "right": {"op": "col", "name": "death_rate"},
                "attrs": {},
            },
            id="a binop carrying a stray attrs",
        ),
        pytest.param(
            {"op": "call", "name": "x", "engine": "polars", "text": "t"},
            id="engine_native relabelled to call",
        ),
        pytest.param(
            {
                "op": "when_then",
                "cond": {"op": "col", "name": "death_rate"},
                "then": {"op": "col", "name": "sum_assured"},
                "otherwise": {"op": "lit", "value": 0.0},
                "elsewhen": {"op": "lit", "value": 1.0},
            },
            id="a when_then carrying a fourth branch",
        ),
        pytest.param(
            {"op": "lit", "value": 1.0, "name": "x"},
            id="a lit carrying a name",
        ),
    ],
)
def test_a_tree_node_carrying_a_key_its_kind_does_not_declare_is_refused(
    tree: dict[str, Any],
) -> None:
    """Six documents that were accepted before the seven branches were closed.

    The first is the one that matters and the reason the others are here
    with it. A node's keys are closed because its identity is not: the byte
    grammar reads the kind off ``op`` and encodes what that kind carries, so
    a ``call`` relabelled to ``state`` hashes as a state reference and its
    operands and configuration simply leave the digest -- while the document
    validates on the way out.
    """
    report = validate_artifact(_with_tree(tree))

    assert not report.ok
    assert any(finding.section == "schema" for finding in report.findings)


def test_the_refusal_names_the_key_because_the_schema_cannot() -> None:
    """``oneOf`` says "not valid under any of the given schemas" and names none.

    That message leaves a producer comparing its document against seven
    branches by eye. The schema is what refuses; this finding is what says
    why, naming the kind, the key and where in the document it sits.
    """
    report = validate_artifact(_with_tree(_A_CALL_RELABELLED))
    named = [
        finding for finding in report.findings if "carries the key" in finding.message
    ]

    assert [finding.where for finding in named] == [
        "/nodes/2/expr/args",
        "/nodes/2/expr/attrs",
    ]
    assert "'state'" in named[0].message
    assert "'args'" in named[0].message
    assert "name, op" in named[0].message


def test_the_refusal_reaches_a_stray_key_buried_in_an_operand() -> None:
    """A tree is walked whole, so a stray key deep in one is named where it is."""
    report = validate_artifact(
        _with_tree(
            {
                "op": "call",
                "name": "abs",
                "args": [{"op": "col", "name": "sum_assured", "attrs": {}}],
                "attrs": {},
            }
        )
    )
    named = [
        finding for finding in report.findings if "carries the key" in finding.message
    ]

    assert [finding.where for finding in named] == ["/nodes/2/expr/args/0/attrs"]
    assert "'col'" in named[0].message


def test_every_tree_this_producer_writes_still_validates() -> None:
    """The closure refuses nothing the reference producer writes.

    Every operation-tree node across the shipped models validated before the
    branches were closed and validates after, which is what makes the
    closure a refusal of documents nobody should write rather than a
    narrowing of the format.
    """
    artifact = _artifact_for_a_two_column_model(profile="executable")

    assert validate_artifact(artifact).ok


def test_the_envelope_and_the_node_record_stay_open() -> None:
    """The closure is of the seven trees and of nothing above them.

    Section 6's round-trip promise -- a consumer meeting a facet it does not
    know must preserve it unchanged -- rests on that openness, and closing an
    operation-tree branch does not touch it.
    """
    artifact = _artifact_for_a_two_column_model(profile="executable")
    artifact["an_unknown_envelope_member"] = {"held": True}
    _node(artifact, "death_claims@1")["an_unknown_node_member"] = 1

    assert validate_artifact(artifact).ok


# --- a deep operation tree is read, however deep (W5 S-F4) ---------------------


def _summed(terms: int, *, leaf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return ``sum_assured + death_rate + ...`` as the producer nests it, left-deep."""
    tree: dict[str, Any] = {"op": "col", "name": "sum_assured"}
    for term in range(terms):
        right = leaf if (leaf is not None and term == 0) else None
        tree = {
            "op": "binop",
            "kind": "add",
            "left": tree,
            "right": right or {"op": "col", "name": "death_rate"},
        }
    return tree


def test_a_wide_sum_the_producer_writes_is_read_back() -> None:
    """A 220-term sum exports, and validates rather than overflowing."""
    terms = 220
    af = ActuarialFrame(pl.DataFrame({f"c{i}": [float(i)] for i in range(terms)}))
    total = af.c0
    for i in range(1, terms):
        total = total + af[f"c{i}"]
    af.total = total
    artifact = json.loads(GraphExporter(af).export(profile="executable"))

    report = validate_artifact(artifact)

    assert report.ok, [finding.message for finding in report.findings]


@pytest.mark.parametrize("depth", [65, 400, 1500])
def test_a_deep_tree_is_held_to_the_schema_without_running_out_of_recursion(
    depth: int,
) -> None:
    """Past the depth read whole, each tree node is read on its own, to the bottom."""
    report = validate_artifact(_with_tree(_summed(depth)))

    assert [f for f in report.findings if f.section == "schema"] == []


def test_a_deep_tree_s_bad_leaf_is_refused_where_it_sits() -> None:
    """A bad leaf at the bottom of a deep tree is named at its own pointer."""
    report = validate_artifact(_with_tree(_summed(400, leaf={"op": "col", "name": 7})))

    (refused,) = [f for f in report.findings if f.section == "schema"]
    assert refused.where == "/nodes/2/expr" + "/left" * 399 + "/right"
    assert "{'op': 'col', 'name': 7}" in refused.message


def test_a_deep_tree_s_stray_key_is_still_named() -> None:
    """The closed-branch finding reaches the bottom of a deep tree too."""
    leaf = {"op": "col", "name": "death_rate", "extra": 1}
    report = validate_artifact(_with_tree(_summed(400, leaf=leaf)))

    assert any(
        f.where.endswith("/right/extra") and "carries the key 'extra'" in f.message
        for f in report.findings
    )


def test_a_tree_deeper_than_this_reader_parses_is_a_finding_not_a_traceback() -> None:
    """``deep=True`` takes each digest again, reading a tree one level inside the next.

    The schema reading holds a tree of any depth (above); recomputing its
    ``local_fingerprint`` parses it back into operations, and past Python's
    call depth that raised ``RecursionError`` out of ``gspio validate --deep``
    and out of every engine's inspection. It is a finding on the node now,
    naming how deep the tree goes.
    """
    report = validate_artifact(_with_tree(_summed(1500)), deep=True)

    deep = [f for f in report.findings if "deeper than this reader" in f.message]
    assert [f.where for f in deep] == ["death_claims@1"]
    assert deep[0].section == "semantic"
    assert "1501 operations deep" in deep[0].message
    assert not report.ok
