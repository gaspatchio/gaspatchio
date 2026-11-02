# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the model read, by identity, and which column read which of it.

An artifact that says how every column was computed and stays silent about
the bases those columns were computed *from* answers half the question a
reviewer arrives with. "Which mortality table was this run against, and had
its content moved since last quarter?" is not a question about a formula; it
is a question about the bases the formulas read, and the envelope's
``assumptions`` section is where it is answered.

Each test names the claim rather than the digest: that the base appears, that
it appears once however many times it was read, that the order does not
depend on the run, and that a node names the entries its own formula read so
that a reader can follow one figure to the base it rests on.

The entry also carries the base's own contents, up to a guard the caller
sets, and the claim there is one sentence long: **a reader re-hashes what is
in front of them and reaches the fingerprint written beside it.** That is
what makes an audit-profile artifact checkable by somebody holding the file
and nothing else -- no model, no assumption directory, no library in common
with the producer.
"""

from __future__ import annotations

import datetime
import json
import warnings
from typing import TYPE_CHECKING, Any, Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, GaspatchioWarning
from gaspatchio._identity import content_sha_of, source_sha_of
from gaspatchio.assumptions import Table, TableSupersededError
from gaspatchio.assumptions._api import _REGISTERED_TABLE_SHAS
from gaspatchio.curves import Curve
from gaspatchio.frame.graph import GraphExporter, build_artifact, validate_artifact
from gaspatchio.frame.graph.artifact import (
    PAYLOAD_DIRECTORY,
    TABLE_PAYLOAD_LIMIT,
    payload_file_name,
)
from gaspatchio.frame.graph.assumptions import (
    ArtefactReference,
    artefacts_read,
    assumptions_read_by_node,
    payload_of,
)
from gaspatchio.frame.graph.fingerprint import local_fingerprint
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.frame.lowering import artefacts
from gaspatchio.frame.lowering.artefacts import (
    register_table,
    table_for,
    table_named,
)
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# What a consumer holding the payload and the published grammar builds each
# column back as. Neutral names in, storage types out: the grammar collapses
# width deliberately, so any width carrying the same values re-derives the
# same digest.
_POLARS_BY_NEUTRAL: dict[str, pl.DataType] = {
    "bool": pl.Boolean(),
    "i64": pl.Int64(),
    "f64": pl.Float64(),
    "str": pl.String(),
    "date": pl.Date(),
    "datetime": pl.Datetime(),
}

# A guard set far below anything a real basis weighs, so that a test about
# what happens above the guard is about the guard rather than about how big
# the fixture happens to be.
_A_SMALL_GUARD = 1024


def _artifact(
    frame: ActuarialFrame,
    *,
    include_tables: bool | Literal["all"] = True,
    table_payload_limit: int | None = TABLE_PAYLOAD_LIMIT,
) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(
            include_tables=include_tables,
            table_payload_limit=table_payload_limit,
        )
    )
    return artifact


# What a non-finite float is written as on the wire, and what a consumer
# reads it back to before hashing. JSON has no token for one that a strict
# parser accepts, and null is spoken for as the missing-value marker.
_SENTINELS: dict[str, float] = {
    "NaN": float("nan"),
    "Infinity": float("inf"),
    "-Infinity": float("-inf"),
}


def _content_sha_of_payload(entry: dict[str, Any]) -> str:
    """Return the digest a consumer re-derives from an inlined table payload.

    Exactly what a reader holding the values does: rebuild the columns the
    payload declares, in the order it declares them, with the rows in the
    order it declares them and no re-sort, and hash them under the published
    content grammar. A string in a column declared ``f64`` is the sentinel
    for a non-finite float and is read back to the float first. Nothing here
    reads the table it came from.
    """
    payload = entry["payload"]
    schema = {
        column["name"]: _POLARS_BY_NEUTRAL[column["dtype"]]
        for column in payload["columns"]
    }
    floating = [
        column["name"] for column in payload["columns"] if column["dtype"] == "f64"
    ]
    rows = [
        [
            _SENTINELS[value] if name in floating and isinstance(value, str) else value
            for name, value in zip(schema, row, strict=True)
        ]
        for row in payload["rows"]
    ]
    return content_sha_of(pl.DataFrame(rows, schema=schema, orient="row"))


def _mortality_table(name: str = "mortality") -> Table:
    """Build a one-dimension mortality table under the name given."""
    ages = list(range(20, 121))
    return Table(
        name=name,
        source=pl.DataFrame(
            {
                "age": ages,
                "rate": [round(0.000_5 + 0.000_4 * (age - 20), 6) for age in ages],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _lapse_table() -> Table:
    """Build a one-dimension lapse table, so a model can read more than one."""
    return Table(
        name="lapse",
        source=pl.DataFrame(
            {"duration": [0, 1, 2, 3], "rate": [0.10, 0.08, 0.06, 0.05]}
        ),
        dimensions={"duration": "duration"},
        value="rate",
    )


def _expense_table() -> Table:
    """Build a third table, named so its place in the order is not its place here."""
    return Table(
        name="expenses",
        source=pl.DataFrame(
            {"duration": [0, 1, 2, 3], "amount": [50.0, 25.0, 25.0, 25.0]}
        ),
        dimensions={"duration": "duration"},
        value="amount",
    )


# --- the models the claims are made about ------------------------------------


def _a_two_column_model() -> ActuarialFrame:
    """Return a model with two arriving columns and one calculation over them."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _a_model_with_a_mortality_lookup() -> ActuarialFrame:
    """Return a model whose one rate comes out of a named mortality table."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.mortality_rate = _mortality_table().lookup(age=frame.issue_age)
    return frame


def _a_model_with_a_schedule_and_a_curve() -> ActuarialFrame:
    """Return a model reading a projection timeline and a yield curve."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2]}))
    frame = frame.projection.set(
        schedule=Schedule.from_calendar_grid(
            start_date=datetime.date(2026, 1, 31), n_periods=6, frequency="1M"
        )
    )
    frame.years_elapsed = frame.projection.t_years()
    curve = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.02, 0.025, 0.03])
    frame.spot_rate = curve.spot_rate(frame.years_elapsed)
    return frame


def _a_model_looking_up_mortality_twice() -> ActuarialFrame:
    """Return a model reading one table from two different formulas."""
    table = _mortality_table()
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.mortality_rate = table.lookup(age=frame.issue_age)
    frame.mortality_rate_next_year = table.lookup(age=frame.issue_age + 1)
    return frame


def _a_model_with_several_tables() -> ActuarialFrame:
    """Return a model reading three tables, written in no useful order."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55], "duration": [0, 2]}))
    frame.mortality_rate = _mortality_table().lookup(age=frame.issue_age)
    frame.lapse_rate = _lapse_table().lookup(duration=frame.duration)
    frame.expense_amount = _expense_table().lookup(duration=frame.duration)
    return frame


def _a_model_whose_lookup_is_continued_by_an_engine_method() -> ActuarialFrame:
    """Return a model whose one lookup is continued by an undeclared engine method.

    A lookup carries the node it was built from, so combining it with
    anything by an *operator* keeps that node as a subtree of the result, and
    so does a method the vocabulary declares (``fill_null``, ``fill_nan``,
    ``round``). A method the vocabulary does *not* name is Polars' own and
    returns a plain expression: the line would reach the fold as one
    engine-native fragment whose text names the lookup plugin and not the
    table, which is why the frame refuses it (spec Annex A.2).
    """
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.filled_mortality_rate = (
        _mortality_table().lookup(age=frame.issue_age).cast(pl.Float32)
    )
    return frame


def _a_model_whose_lookup_is_composed_into_a_larger_formula() -> ActuarialFrame:
    """Return a model whose one lookup is combined with a scalar literal.

    Nothing about the model is unusual -- an annual rate over twelve is how
    a monthly rate is written -- and that is the point: this is the everyday
    shape, not a corner.
    """
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.monthly_mortality_rate = _mortality_table().lookup(age=frame.issue_age) / 12
    return frame


def _a_model_reading_two_curves() -> ActuarialFrame:
    """Return a model reading two curves of one shape and different rates."""
    frame = ActuarialFrame(pl.DataFrame({"years_elapsed": [1.0, 2.0]}))
    base = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.02, 0.025, 0.03])
    shocked = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.03, 0.035, 0.04])
    frame.base_rate = base.spot_rate(frame.years_elapsed)
    frame.shocked_rate = shocked.spot_rate(frame.years_elapsed)
    return frame


def _a_model_with_a_large_table() -> ActuarialFrame:
    """Return a model whose one base is far larger than the guard beneath it."""
    durations = list(range(2_000))
    table = Table(
        name="surrender_charges",
        source=pl.DataFrame(
            {
                "duration": durations,
                "charge": [round(0.08 - 0.000_03 * step, 6) for step in durations],
            }
        ),
        dimensions={"duration": "duration"},
        value="charge",
    )
    frame = ActuarialFrame(pl.DataFrame({"duration": [0, 7]}))
    frame.surrender_charge = table.lookup(duration=frame.duration)
    return frame


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the artifact for a model that reads no assumption base at all."""
    return _artifact(_a_two_column_model())


def _artifact_for_a_model_with_a_mortality_lookup(
    *, include_tables: bool | Literal["all"] = True
) -> dict[str, Any]:
    """Return the artifact for the one-lookup model."""
    return _artifact(_a_model_with_a_mortality_lookup(), include_tables=include_tables)


def _artifact_for_a_model_with_a_large_table(
    *,
    include_tables: bool | Literal["all"] = True,
    table_payload_limit: int | None = _A_SMALL_GUARD,
) -> dict[str, Any]:
    """Return the artifact for the large-table model, under a guard it exceeds."""
    return _artifact(
        _a_model_with_a_large_table(),
        include_tables=include_tables,
        table_payload_limit=table_payload_limit,
    )


def _artifact_from_a_graph_whose_table_is_not_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Return the artifact for a model whose base this process no longer holds.

    The graph is folded first and the directory of tables emptied after, which
    is what a log carried across a process boundary looks like from the
    inside: every node still names the base it read, and nothing in this
    interpreter can hand over its values.
    """
    graph = fold(_a_model_with_a_mortality_lookup())
    monkeypatch.setattr(artefacts, "_TABLES", {})
    return build_artifact(graph)


def _artifact_for_a_model_with_a_schedule_and_a_curve() -> dict[str, Any]:
    """Return the artifact for the timeline-and-curve model."""
    return _artifact(_a_model_with_a_schedule_and_a_curve())


def _artifact_for_a_model_looking_up_mortality_twice() -> dict[str, Any]:
    """Return the artifact for the model reading one table twice."""
    return _artifact(_a_model_looking_up_mortality_twice())


def _artifact_for_a_model_with_several_tables() -> dict[str, Any]:
    """Return the artifact for the three-table model."""
    return _artifact(_a_model_with_several_tables())


# --- what the section says ---------------------------------------------------


def test_a_model_that_reads_nothing_carries_an_empty_section() -> None:
    """Empty is a claim: this model rests on no assumption base at all."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["assumptions"] == []


def test_a_lookup_puts_its_table_in_the_section() -> None:
    """The base a formula read is named in the envelope, with its own identity."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()

    (entry,) = artifact["assumptions"]

    assert entry["kind"] == "table"
    assert entry["name"] == "mortality"
    assert entry["fingerprint"].startswith("sha256:")


def test_a_projection_schedule_and_a_curve_appear_beside_the_tables() -> None:
    """Three primitives publish a content identity, and all three are bases."""
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()

    kinds = sorted(entry["kind"] for entry in artifact["assumptions"])

    assert kinds == ["curve", "schedule"]


def test_one_table_read_twice_appears_once() -> None:
    """The section is a directory of the bases, not a log of the reads."""
    artifact = _artifact_for_a_model_looking_up_mortality_twice()

    assert len(artifact["assumptions"]) == 1


def test_the_section_is_ordered_the_same_way_on_every_run() -> None:
    """Two artifacts of one model compare as written, or they compare as noise.

    Two exports of one model agreeing is not the claim. One process holds
    one set in one iteration order, so that comparison would hold whatever
    order the producer wrote. The claim is that the order is the stated one
    -- kind, then name, then identity -- which is a property of the model
    rather than of the run, and it is checked against that order written
    out rather than against a second run.
    """
    artifact = _artifact_for_a_model_with_several_tables()

    section = artifact["assumptions"]

    assert [entry["name"] for entry in section] == ["expenses", "lapse", "mortality"]
    assert section == sorted(
        section,
        key=lambda entry: (entry["kind"], entry["name"] or "", entry["fingerprint"]),
    )


def test_a_schedule_and_a_curve_are_named_after_their_own_contents() -> None:
    """A value object states no name, so the entry is called what it is made of.

    The name a reader meets is the entry's kind and the first eight digits of
    the identity written beside it -- a name wearing its derivation on its
    face. It is not a claim about the model: nobody called this curve
    anything, and the record does not pretend somebody did.
    """
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()

    section = artifact["assumptions"]

    assert [entry["kind"] for entry in section] == ["curve", "schedule"]
    assert [entry["name"] for entry in section] == [
        f"{entry['kind']}:{entry['fingerprint'].removeprefix('sha256:')[:8]}"
        for entry in section
    ]


def test_a_node_reading_a_curve_names_the_entry_that_curve_is() -> None:
    """The join Article 244(g) asks for, followed on the kind that used to skip it.

    A name on the entry is worth having only if the node that did the
    reading gives it, so this follows the join rather than asserting the
    name: from the node whose formula read the curve, by the one name that
    node gives, to the entry of the section it belongs to.
    """
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()
    section = {entry["name"]: entry for entry in artifact["assumptions"]}

    node = next(node for node in artifact["nodes"] if node["column"] == "spot_rate")

    (name,) = node["reads_assumptions"]
    assert section[name]["kind"] == "curve"


def test_a_node_reading_the_timeline_names_the_schedule_behind_it() -> None:
    """The same join on the other value object, which no node could name before."""
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()
    section = {entry["name"]: entry for entry in artifact["assumptions"]}

    node = next(node for node in artifact["nodes"] if node["column"] == "years_elapsed")

    (name,) = node["reads_assumptions"]
    assert section[name]["kind"] == "schedule"


# --- and what the entry carries of the base itself ---------------------------


def test_a_table_arrives_with_its_values() -> None:
    """The reader asking which basis this ran on gets the basis, not a digest."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()

    payload = artifact["assumptions"][0]["payload"]

    assert payload["dimensions"] == ["age"]
    assert payload["value"] == "rate"
    assert [45, 0.010_5] in payload["rows"]


def test_a_table_names_the_type_of_every_column_it_carries() -> None:
    """A neutral name, so a consumer builds the column back without the engine."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()

    payload = artifact["assumptions"][0]["payload"]

    assert [column["name"] for column in payload["columns"]] == ["age", "rate"]
    assert {column["dtype"] for column in payload["columns"]} <= set(_POLARS_BY_NEUTRAL)


def test_an_inline_payload_re_hashes_to_its_declared_fingerprint() -> None:
    """What makes an audit-profile artifact checkable without the model."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()

    entry = artifact["assumptions"][0]

    assert _content_sha_of_payload(entry) == entry["fingerprint"]


def _a_model_reading_a_table_with_a_non_finite_rate() -> ActuarialFrame:
    """Return a model whose basis holds a NaN, which is a value it holds.

    Section 12.3 is explicit that a NaN in a column of data is a value and
    not a configuration mistake: two runs that both produced one have not
    drifted. So the artifact carries it, and the only question is how.
    """
    table = Table(
        name="mortality_with_a_gap",
        source=pl.DataFrame(
            {"age": [40, 41, 42], "rate": [0.001, float("nan"), 0.003]}
        ),
        dimensions={"age": "age"},
        value="rate",
    )
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 42]}))
    frame.mortality_rate = table.lookup(age=frame.issue_age)
    return frame


def _refuse_a_bare_constant(token: str) -> float:
    """Refuse the tokens JSON has no grammar for, as a strict parser does."""
    message = f"{token!r} is not a value the JSON grammar defines"
    raise ValueError(message)


def test_a_non_finite_rate_exports_a_document_a_strict_parser_accepts() -> None:
    """serde_json, Go and JSON.parse refuse a bare NaN, and refuse the whole file.

    Python's encoder writes one happily and Python's decoder reads it back,
    so the defect is invisible from inside the producer -- and the schema
    validator runs on an object somebody has already parsed, which means it
    never sees the bytes that would have stopped them. The check that
    catches it is a strict parse.
    """
    document = GraphExporter(_a_model_reading_a_table_with_a_non_finite_rate()).export()

    parsed = json.loads(document, parse_constant=_refuse_a_bare_constant)

    assert parsed["assumptions"][0]["payload"]["rows"] == [
        [40.0, 0.001],
        [41.0, "NaN"],
        [42.0, 0.003],
    ]


def test_a_non_finite_rate_is_carried_in_a_column_still_declared_f64() -> None:
    """The declared type is what makes the string unambiguously the sentinel."""
    artifact = _artifact(_a_model_reading_a_table_with_a_non_finite_rate())

    payload = artifact["assumptions"][0]["payload"]

    assert [column["dtype"] for column in payload["columns"]] == ["f64", "f64"]


def test_a_payload_holding_a_non_finite_re_hashes_to_its_fingerprint() -> None:
    """The one check the payload exists to pass, over a basis with a gap in it.

    A consumer maps the sentinel back to the float and hashes as usual; the
    content grammar's own NaN normalisation then applies to it like any other
    value. Collapsing the sentinel to null instead would hash a missing value
    where the frame holds a present one, and the digest would not match.
    """
    artifact = _artifact(_a_model_reading_a_table_with_a_non_finite_rate())

    entry = artifact["assumptions"][0]

    assert _content_sha_of_payload(entry) == entry["fingerprint"]


def test_the_producer_refuses_to_write_what_a_strict_parser_would_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backstop, so that no future path ships an unparseable file quietly.

    Not a restatement of the carriage above. That pins the one path known to
    need it; this pins what happens on a path nobody has thought of yet --
    the producer stops, loudly, rather than handing on a file that looks
    valid right up until somebody with a strict parser opens it.
    """
    from gaspatchio.frame.graph import calc_graph

    def _a_document_carrying_a_bare_non_finite(*_a: object, **_k: object) -> dict:
        return {"schema": "gaspatchio-graph/v0-preview.1", "rate": float("nan")}

    monkeypatch.setattr(
        calc_graph, "build_artifact", _a_document_carrying_a_bare_non_finite
    )

    with pytest.raises(ValueError, match="Out of range float"):
        GraphExporter(_a_two_column_model()).export()


def test_a_table_above_the_guard_says_why_it_is_not_here() -> None:
    """A value that exists and was left out, weighed so the reader knows the cost."""
    artifact = _artifact_for_a_model_with_a_large_table(
        table_payload_limit=_A_SMALL_GUARD
    )

    payload = artifact["assumptions"][0]["payload"]

    assert payload["omitted"] == "size"
    assert payload["bytes"] > _A_SMALL_GUARD


def test_the_guard_can_be_lifted() -> None:
    """The guard is the caller's, not the format's: asked to, it carries anything."""
    artifact = _artifact_for_a_model_with_a_large_table(include_tables="all")

    assert "rows" in artifact["assumptions"][0]["payload"]


def test_no_guard_at_all_is_the_same_answer_as_lifting_it() -> None:
    """None is the absence of a limit, which for these entries is 'carry it'."""
    artifact = _artifact_for_a_model_with_a_large_table(table_payload_limit=None)

    assert "rows" in artifact["assumptions"][0]["payload"]


def test_the_slim_artifact_keeps_every_identity_and_no_values() -> None:
    """For a repository that versions its assumption bases somewhere else.

    The stand-in keeps the table's roles -- its columns and which answers --
    and no row, so a reviewer holding the file can still read it as the table.
    """
    artifact = _artifact_for_a_model_with_a_mortality_lookup(include_tables=False)

    entry = artifact["assumptions"][0]

    assert entry["fingerprint"].startswith("sha256:")
    assert set(entry["payload"]) == {"omitted", "bytes", "roles"}
    assert entry["payload"]["omitted"] == "size"
    assert entry["payload"]["bytes"] > 0
    assert set(entry["payload"]["roles"]) == {"dimensions", "value", "columns"}


def test_a_schedule_and_a_curve_carry_their_own_canonical_form() -> None:
    """Neither is re-described here: each hands over the form it already publishes."""
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()

    by_kind = {entry["kind"]: entry for entry in artifact["assumptions"]}

    assert by_kind["curve"]["payload"]["tenors"]
    assert by_kind["schedule"]["payload"]["frequency"]


def test_a_schedule_and_a_curve_re_hash_to_their_declared_fingerprints() -> None:
    """The same check the table gets, under the grammar those two are stamped by."""
    artifact = _artifact_for_a_model_with_a_schedule_and_a_curve()

    for entry in artifact["assumptions"]:
        assert source_sha_of(entry["payload"]) == entry["fingerprint"], entry["kind"]


def test_an_artefact_this_process_did_not_build_keeps_its_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A log carried across a process boundary still names what it read.

    And says why the values are missing in the words that are true of them.
    Nothing was weighed here, because nothing was in front of the producer to
    weigh -- so the entry claims no weight rather than claiming nought, which
    would be a measurement nobody made standing beside a reason that is not
    the reason.
    """
    artifact = _artifact_from_a_graph_whose_table_is_not_registered(monkeypatch)

    entry = artifact["assumptions"][0]

    assert entry["name"] == "mortality"
    assert entry["fingerprint"].startswith("sha256:")
    assert entry["payload"] == {"omitted": "unavailable"}


def _recorded_and_logged(
    build: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[warnings.WarningMessage]]:
    """Build an artifact; return it, the log records and the warnings raised."""
    from loguru import logger

    logged: list[str] = []
    sink = logger.add(lambda m: logged.append(m.record["message"]), level="WARNING")
    try:
        with warnings.catch_warnings(record=True) as raised:
            warnings.simplefilter("always")
            artifact = build()
    finally:
        logger.remove(sink)
    return artifact, logged, raised


def test_an_artefact_this_process_did_not_build_is_recorded_and_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A section that came back short is never short in silence: the file says so.

    The document records the omission, which validate and the viewer show;
    a warning is kept for what nothing records, so this one is logged.
    """
    artifact, logged, raised = _recorded_and_logged(
        lambda: _artifact_from_a_graph_whose_table_is_not_registered(monkeypatch)
    )

    assert artifact["assumptions"][0]["payload"] == {"omitted": "unavailable"}
    assert any("is not registered in this process" in line for line in logged)
    assert [w for w in raised if issubclass(w.category, GaspatchioWarning)] == []


def _a_table_extended_after_it_was_read() -> tuple[ActuarialFrame, Table, str]:
    """Return a model, its table, and the identity the formula read it under.

    ``Table.extend`` re-stamps the live object in place, so this is the shape
    of a base that has moved off the identity the artifact still legitimately
    records.
    """
    table = Table(
        name="extended_after_the_read",
        source=pl.DataFrame({"age": [41, 42], "rate": [0.555_555, 0.666_666]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode="hash",  # the only mode a later extend is allowed on
    )
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [41, 42]}))
    frame.mortality_rate = table.lookup(age=frame.issue_age)
    read_under = table.source_sha()
    table.extend(pl.DataFrame({"age": [43], "rate": [0.777_777]}))
    return frame, table, read_under


def test_a_table_that_moved_after_it_was_read_carries_no_values() -> None:
    """Values that no longer hash to the digest beside them must not be published.

    The directory holds the live table, and a live table can be extended
    after a formula has read it. Publishing the extended rows under the
    identity that formula recorded would put an artifact in front of a
    reader that fails the very check the section invites them to run.

    The reason has to be the true one. These values were not weighed and
    declined: they were not in front of the producer at all, and "left out
    for its size, nought bytes" would state a reason that never happened
    beside a measurement nobody took.
    """
    frame, table, read_under = _a_table_extended_after_it_was_read()

    artifact = _artifact(frame)

    (entry,) = artifact["assumptions"]
    assert table.source_sha() != read_under, "the fixture did not actually move"
    assert entry["payload"] == {"omitted": "unavailable"}


def test_a_table_that_moved_after_it_was_read_is_recorded_and_logged() -> None:
    """The drift is in the document, and the log names the table and the remedy."""
    frame, _table, _read_under = _a_table_extended_after_it_was_read()

    artifact, logged, raised = _recorded_and_logged(lambda: _artifact(frame))

    (entry,) = artifact["assumptions"]
    assert entry["payload"] == {"omitted": "unavailable"}
    drift = [line for line in logged if "has moved since" in line]
    assert "extended_after_the_read" in drift[0]
    assert [w for w in raised if issubclass(w.category, GaspatchioWarning)] == []


def test_values_two_tables_share_under_different_roles_are_recorded_and_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identical values read with different keys: left out, said in plain words.

    A second table in this process holding exactly the same values, with the
    key and rate columns the other way round, gives the values two meanings
    the file could not tell apart. The document records the omission; the
    log says why in an actuary's words and names the next move.
    """
    frame = _a_model_with_a_mortality_lookup()
    # The values this model reads, by the identity its own artifact records:
    # other tables named "mortality" may have been built in this process.
    fingerprint = _artifact(frame)["assumptions"][0]["fingerprint"]
    schemas = artefacts._TABLE_SCHEMAS  # noqa: SLF001 -- the roles a table was read under
    monkeypatch.setitem(schemas, ("mortality_by_rate", fingerprint), (("rate",), "age"))

    artifact, logged, raised = _recorded_and_logged(lambda: _artifact(frame))

    (entry,) = artifact["assumptions"]
    assert entry["payload"] == {"omitted": "unavailable"}
    (said,) = [line for line in logged if "'mortality'" in line]
    assert "portable payload" not in said
    assert "sidecar" not in said
    assert "key" in said
    assert "Export" in said
    assert [w for w in raised if issubclass(w.category, GaspatchioWarning)] == []


# --- the node names what it read --------------------------------------------


def test_a_node_names_the_entries_its_own_formula_read() -> None:
    """The join a reader follows from one figure to the base it rests on."""
    artifact = _artifact_for_a_model_with_a_mortality_lookup()

    node = next(
        node
        for node in artifact["nodes"]
        if node["column"] == "mortality_rate" and node["in_final_schema"]
    )

    assert node["reads_assumptions"] == ["mortality"]


def test_a_node_reading_no_assumption_base_says_so_rather_than_omitting_it() -> None:
    """Required and usually empty: the empty array is the node's own answer."""
    artifact = _artifact_for_a_two_column_model()

    assert all(node["reads_assumptions"] == [] for node in artifact["nodes"])


def test_every_name_a_node_reads_resolves_to_an_entry_of_the_section() -> None:
    """A name naming nothing would be a join a reader cannot follow."""
    artifact = _artifact_for_a_model_with_several_tables()

    named = {entry["name"] for entry in artifact["assumptions"]}

    for node in artifact["nodes"]:
        assert set(node["reads_assumptions"]) <= named, node["id"]


# --- the walk the section and the field are both taken from ------------------


def test_the_walk_sorts_by_kind_then_name_then_identity() -> None:
    """One order, stated in one place, so both readers of the walk share it."""
    found = artefacts_read(fold(_a_model_with_several_tables()))

    assert all(isinstance(reference, ArtefactReference) for reference in found)
    assert [(reference.kind, reference.name) for reference in found] == [
        ("table", "expenses"),
        ("table", "lapse"),
        ("table", "mortality"),
    ]


def test_two_bases_of_one_kind_named_after_their_contents_still_sort_by_identity() -> (
    None
):
    """The last key still does work: two curves are told apart by their content.

    A content name orders two curves exactly as their identities do, because
    it is the first eight digits of that identity -- so the order is the one
    it always was. What the last key settles is the pair whose names tie: two
    entries of one kind now tie only where their digests agree in eight
    digits, and the identity beside them is what tells those apart. Two
    artifacts of one model have to compare as written for the models most
    likely to carry a shocked basis.
    """
    found = artefacts_read(fold(_a_model_reading_two_curves()))

    fingerprints = [reference.fingerprint for reference in found]

    assert [reference.kind for reference in found] == ["curve", "curve"]
    assert [reference.name for reference in found] == [
        f"curve:{fingerprint.removeprefix('sha256:')[:8]}"
        for fingerprint in fingerprints
    ]
    assert len(set(fingerprints)) == 2, "the two curves must actually differ"
    assert fingerprints == sorted(fingerprints)


def test_a_base_read_inside_an_engine_native_fragment_is_refused() -> None:
    """A table read never reaches the record inside an engine fragment.

    The walk reads what a node's own tree names, and a fragment's text is
    Polars' display, which names the lookup plugin and not the table: the
    section would be empty, the node would name nothing, and -- what made
    this a false identity rather than a partial account -- two models
    reading two different tables would carry one fingerprint. Annex A.2
    closes the case by refusing it, naming the table and the two ways to
    keep the read a node of its own.
    """
    with pytest.raises(ValueError, match="assumption table 'mortality'") as refusal:
        _a_model_whose_lookup_is_continued_by_an_engine_method()

    message = str(refusal.value)
    assert "to_float()" in message
    assert "a NaN fill is fill_nan(0.0)" in message
    assert "af.filled_mortality_rate_read = <the read>" in message


def test_the_two_line_form_names_the_table_it_reads() -> None:
    """Stored first, the read is its own node and the record names its table."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.mortality_rate = _mortality_table().lookup(age=frame.issue_age)
    frame.filled_mortality_rate = frame.mortality_rate.polars_native().cast(pl.Float32)

    artifact = _artifact(frame)
    node = next(
        node for node in artifact["nodes"] if node["column"] == "filled_mortality_rate"
    )

    assert node["tier"] == "engine_native"
    assert node["reads"] == ["mortality_rate@1"]
    assert [entry["name"] for entry in artifact["assumptions"]] == ["mortality"]


def test_the_per_node_walk_answers_for_a_node_with_a_tree_and_no_other() -> None:
    """An arriving column has no tree, so it has no entry -- and no exception."""
    by_node = assumptions_read_by_node(fold(_a_model_with_a_mortality_lookup()))

    assert by_node["mortality_rate@1"] == ("mortality",)
    assert "issue_age" not in by_node


# --- the registry the entry's table is read back out of ----------------------


def _table_of(name: str, rates: list[float]) -> Table:
    """Build a two-row table whose values are this test's and nobody else's."""
    return Table(
        name=name,
        source=pl.DataFrame({"age": [41, 42], "rate": rates}),
        dimensions={"age": "age"},
        value="rate",
    )


def test_a_registered_table_is_reachable_by_the_identity_the_node_carries() -> None:
    """The attribute on the node and the key into the registry are one string."""
    table = _table_of("registry_round_trip", [0.111_111, 0.222_222])

    fingerprint = register_table(table)

    assert table_for(fingerprint) is table


def test_two_tables_holding_one_set_of_values_share_one_entry() -> None:
    """The key is content, so the name is no part of it: read the name off the node."""
    rates = [0.333_333, 0.444_444]
    first = _table_of("shared_content_first", rates)
    second = _table_of("shared_content_second", rates)

    assert register_table(first) == register_table(second)
    assert table_for(register_table(second)) is first


def test_a_table_this_process_never_built_is_refused_by_name() -> None:
    """A miss names the next move rather than only the miss."""
    with pytest.raises(KeyError, match="no assumption table registered"):
        table_for(f"sha256:{'0' * 64}")


def test_the_name_door_answers_with_the_table_that_name_belongs_to() -> None:
    """Where content is ambiguous the name is not, and the name is what answers.

    Both tables hold one set of rates, so one fingerprint covers them and
    the content door hands back whichever arrived first. A caller that will
    go on to look up *by name* -- which is what an assumption lookup does at
    execution time -- must be given the table whose name it asked for.
    """
    rates = [0.505_051, 0.606_061]
    first = _table_of("named_door_first", rates)
    second = _table_of("named_door_second", rates)
    fingerprint = register_table(first)

    assert register_table(second) == fingerprint
    assert table_for(fingerprint) is first
    assert table_named("named_door_second", fingerprint) is second
    assert table_named("named_door_first", fingerprint) is first


def test_the_name_door_refuses_a_base_whose_rates_have_since_moved() -> None:
    """A name is not an identity, so the hash beside it has to be checked.

    Answering here would serve rates the formula was never written over --
    the shape a scenario override is lost in -- so the door refuses and says
    which two sets of values are in play.
    """
    written_over = register_table(_table_of("moved_door", [0.777_777, 0.888_888]))
    now_holds = register_table(_table_of("moved_door", [0.999_999, 0.101_010]))

    with pytest.raises(TableSupersededError) as refusal:
        table_named("moved_door", written_over)

    message = str(refusal.value)
    assert written_over in message
    assert now_holds in message


def test_the_name_door_refuses_a_name_this_process_never_built() -> None:
    """A record can outlive the process that built its base; say so plainly.

    This is the one arrival the plain miss is true of -- nothing of that
    name is registered here -- so the message it has always given is the
    message it keeps, and building the ``Table`` in this process really is
    the reader's next move.
    """
    assert "never_built_here" not in _REGISTERED_TABLE_SHAS

    with pytest.raises(KeyError, match="under the name 'never_built_here'") as refusal:
        table_named("never_built_here", f"sha256:{'0' * 64}")

    assert "does not exist in this process" in str(refusal.value)


def test_the_name_door_refuses_a_moved_name_no_read_ever_filed() -> None:
    """A name this process holds is never reported as one it does not.

    Nothing reads either table, and a read is what files a base here, so
    the directory holds no entry for the name at all -- the state a sweep
    is in when it stacks its batches before it runs its models. The record
    still names rates the name has moved off, so this is the same supersede
    as the test above and has to read as one: a miss reported here would
    deny a name two of which are registered, downgrade a documented error
    to a bare ``KeyError``, and point the reader at a table they already
    built. The registry record settles it, and it is the same record
    ``register_table`` and ``Table.lookup`` decide on.
    """
    _table_of("unfiled_door", [0.121_212, 0.131_313])
    written_over = _REGISTERED_TABLE_SHAS["unfiled_door"]
    _table_of("unfiled_door", [0.141_414, 0.151_515])
    now_holds = _REGISTERED_TABLE_SHAS["unfiled_door"]
    assert written_over != now_holds

    with pytest.raises(TableSupersededError) as refusal:
        table_named("unfiled_door", written_over)

    message = str(refusal.value)
    assert written_over in message
    assert now_holds in message
    assert "does not exist in this process" not in message


def test_the_name_door_separates_a_base_never_read_from_a_base_never_built() -> None:
    """The values are right and the object is missing: say which of the two it is.

    An auditor replaying a record rebuilds the base from the same file, so
    the name comes to hold exactly the rates the record was written over --
    and still nothing has read through it, which is what files a base here.
    Nothing has moved, so this is not a supersede; the name is held here, so
    it is not the plain miss either. Answering from the content-keyed
    directory is the one thing this door may never do, so it refuses -- and
    the reader is owed the distinction and the move that closes it, not a
    sentence denying a table they are looking at.
    """
    _table_of("unread_door", [0.161_616, 0.171_717])
    holds = _REGISTERED_TABLE_SHAS["unread_door"]

    with pytest.raises(KeyError) as refusal:
        table_named("unread_door", holds)

    message = str(refusal.value)
    assert "unread_door" in message
    assert holds in message
    assert "no read has resolved a base under that name" in message
    assert holds in message
    assert "does not exist in this process" not in message


def test_a_refusal_names_the_hash_the_name_holds_and_not_the_one_filed_here() -> None:
    """The by-name directory lags a registration, and the sentence must not.

    ``register_table`` files the by-name entry on the read that resolves a
    base, so a base registered and never read leaves the directory holding
    the previous one. A node written over rates the record does *not* hold
    is refused either way -- but "``name`` now holds X" is a claim about the
    name, and the record is what answers it. Read off the stale directory
    the refusal names a hash the name does not hold, in a message whose
    whole job is to tell a reader which two sets of rates are in play.
    """
    _table_of("lagging_named_door", [0.212_121, 0.232_323])
    filed_by_a_read = register_table(
        _table_of("lagging_named_door", [0.242_424, 0.252_525])
    )
    _table_of("lagging_named_door", [0.262_626, 0.272_727])
    now_holds = _REGISTERED_TABLE_SHAS["lagging_named_door"]
    assert now_holds != filed_by_a_read

    with pytest.raises(TableSupersededError) as refusal:
        table_named("lagging_named_door", f"sha256:{'0' * 64}")

    message = str(refusal.value)
    assert now_holds in message
    assert filed_by_a_read not in message


def test_a_read_over_the_rates_the_name_holds_is_not_told_they_have_moved() -> None:
    """The sharpest state the lag reaches: current rates, an earlier object.

    Through a replay the node's own fingerprint can equal what the record
    holds while the directory still carries a base of that name read before
    the rebuild. Refusing is right -- this door answers from the base it
    named and holds no object over those rates -- but the rates have not
    moved, and a supersede saying they have is false in the same shape the
    door exists to remove. So the refusal keeps its type and says which of
    the two states it met.
    """
    read_here = register_table(_table_of("replayed_named_door", [0.282_828, 0.292_929]))
    _table_of("replayed_named_door", [0.303_030, 0.313_131])
    the_node_names = _REGISTERED_TABLE_SHAS["replayed_named_door"]
    assert the_node_names != read_here

    with pytest.raises(TableSupersededError) as refusal:
        table_named("replayed_named_door", the_node_names)

    message = str(refusal.value)
    assert "has been superseded" not in message
    assert "the only base of that name resolved in this process is an earlier one" in (
        message
    )
    assert the_node_names in message
    assert read_here not in message


# --- a lookup composed into a larger formula ---------------------------------


def test_a_lookup_divided_by_a_literal_is_still_a_lookup_in_the_tree() -> None:
    """The everyday shape of a monthly rate, and what the record makes of it.

    ``mortality.lookup(age=...) / 12`` is one arithmetic operation over one
    lookup, and that is what the tree says: a division whose left operand is
    the ``call`` the lookup minted, with the table's name and content
    identity on it. Recording the whole line as one engine fragment threw
    away a structure the framework had in its hand -- the lookup had already
    built its own node -- for no reason but the operator standing after it.
    """
    artifact = _artifact(_a_model_whose_lookup_is_composed_into_a_larger_formula())

    node = next(
        node for node in artifact["nodes"] if node["column"] == "monthly_mortality_rate"
    )
    tree = json.loads(
        GraphExporter(_a_model_whose_lookup_is_composed_into_a_larger_formula()).export(
            profile="executable"
        )
    )
    written = next(
        found["expr"]
        for found in tree["nodes"]
        if found["column"] == "monthly_mortality_rate"
    )

    assert node["tier"] == "core"
    assert written["op"] == "binop"
    assert written["kind"] == "div"
    assert written["left"]["op"] == "call"
    assert written["left"]["name"] == "lookup"
    assert written["left"]["attrs"]["table"] == "mortality"
    assert written["right"] == {"op": "lit", "value": 12}


def test_a_composed_lookup_still_names_the_base_it_read() -> None:
    """The regression that must never return, stated as the claim it is.

    A reviewer asking "which mortality basis is this monthly rate on?"
    follows ``reads_assumptions`` to the envelope's ``assumptions`` section.
    A lookup that dissolved into engine text answered neither: the node
    named nothing and the section was empty, so the model's account of what
    it rested on went missing at the first ``/ 12``.
    """
    artifact = _artifact(_a_model_whose_lookup_is_composed_into_a_larger_formula())

    node = next(
        node for node in artifact["nodes"] if node["column"] == "monthly_mortality_rate"
    )

    assert node["reads_assumptions"] == ["mortality"]
    assert [entry["name"] for entry in artifact["assumptions"]] == ["mortality"]


def test_the_operand_order_the_actuary_wrote_is_the_order_recorded() -> None:
    """``1 - qx`` is a survival probability, and it is not ``qx - 1``."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.survival = 1 - _mortality_table().lookup(age=frame.issue_age)
    written = json.loads(GraphExporter(frame).export(profile="executable"))
    tree = next(
        node["expr"] for node in written["nodes"] if node["column"] == "survival"
    )

    assert tree["kind"] == "sub"
    assert tree["left"] == {"op": "lit", "value": 1}
    assert tree["right"]["name"] == "lookup"
    assert frame.collect()["survival"].to_list() == pytest.approx(
        [1 - 0.008_5, 1 - 0.014_5]
    )


def test_a_lookup_compared_against_a_threshold_keeps_its_identity() -> None:
    """A rate tested against a limit is a comparison over a lookup, and says so."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    frame.above_limit = _mortality_table().lookup(age=frame.issue_age) > 0.01
    artifact = _artifact(frame)
    written = json.loads(GraphExporter(frame).export(profile="executable"))
    tree = next(
        node["expr"] for node in written["nodes"] if node["column"] == "above_limit"
    )
    node = next(
        found for found in artifact["nodes"] if found["column"] == "above_limit"
    )

    assert tree["kind"] == "gt"
    assert tree["left"]["name"] == "lookup"
    assert node["tier"] == "core"
    assert node["reads_assumptions"] == ["mortality"]
    assert frame.collect()["above_limit"].to_list() == [False, True]


def test_two_lookups_composed_together_both_reach_the_section() -> None:
    """A rate built from two bases rests on two bases, and names both."""
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55], "duration": [0, 3]}))
    frame.combined = _mortality_table().lookup(
        age=frame.issue_age
    ) + _lapse_table().lookup(duration=frame.duration)
    artifact = _artifact(frame)

    node = next(found for found in artifact["nodes"] if found["column"] == "combined")

    assert node["tier"] == "core"
    assert node["reads_assumptions"] == ["lapse", "mortality"]
    assert sorted(entry["name"] for entry in artifact["assumptions"]) == [
        "lapse",
        "mortality",
    ]


def test_an_engine_operand_beside_a_lookup_still_makes_the_node_engine_native() -> None:
    """The fallback bites, and the base is named anyway.

    An actuary who reaches past the frame and hands ``pl.col(...)`` in has
    written an engine expression, and one escape hatch anywhere makes the
    whole node engine-native -- that does not change. What does change is
    that the lookup beside it is still a ``call`` in the tree, so a reviewer
    is told both which basis the figure rests on and that the record's
    account of the rest of the line is partial.
    """
    frame = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55], "loading": [1.1, 1.2]}))
    frame.loaded = _mortality_table().lookup(age=frame.issue_age) * pl.col("loading")
    artifact = _artifact(frame)

    node = next(found for found in artifact["nodes"] if found["column"] == "loaded")

    assert node["tier"] == "engine_native"
    assert node["engines"] == ["polars"]
    assert node["reads_assumptions"] == ["mortality"]


def test_a_composed_lookup_authenticates_itself() -> None:
    """Parse what is written, hash what was parsed, reach the node's own stamp."""
    frame = _a_model_whose_lookup_is_composed_into_a_larger_formula()
    written = json.loads(GraphExporter(frame).export(profile="executable"))
    node = next(
        found
        for found in written["nodes"]
        if found["column"] == "monthly_mortality_rate"
    )

    assert (
        f"sha256:{local_fingerprint(op_node_from_json(node['expr'])).hex()}"
        == node["local_fingerprint"]
    )


def test_composing_a_lookup_gives_the_values_it_always_gave() -> None:
    """The record of the line changed; the numbers it computes did not."""
    frame = _a_model_whose_lookup_is_composed_into_a_larger_formula()

    assert frame.collect()["monthly_mortality_rate"].to_list() == pytest.approx(
        [0.008_5 / 12, 0.014_5 / 12]
    )


# --- a join's right side ------------------------------------------------------
#
# A column that arrived from a second table rests on that table exactly as a
# rate rests on a mortality basis. The artifact used to identify it and not
# carry it, so a consumer holding the file could read what a joined model
# did and could not do it: three of level-4's hundred and fourteen nodes
# lowered from the file alone, and twenty-three columns per model arrive by
# join. The right side is now an entry of its own, kind ``join``, and these
# are the claims that makes.


def _product_table() -> pl.DataFrame:
    """Return the right side two of the model's joins are written against."""
    return pl.DataFrame(
        {
            "product_code": ["TERM", "WL"],
            "expense_loading": [0.05, 0.08],
            "commission_rate": [0.40, 0.60],
        }
    )


def _lapse_parameters() -> pl.DataFrame:
    """Return a second, differently shaped right side, keyed on its own column."""
    return pl.DataFrame(
        {"lapse_id": [1, 2], "floor": [0.02, 0.03], "power": [1.5, 2.0]}
    )


def _a_model_shaped_like_level_four() -> ActuarialFrame:
    """Return a model with three joins over two distinct right sides.

    The shape level 4 and level 5 actually carry: several joins, one of the
    right sides read more than once, and calculations downstream of the
    columns that arrived. Reading one right side twice is what makes the
    directory's claim a claim -- one entry per distinct right side, not one
    per join -- and the rename between the two reads is what lets the second
    read land its columns without contending with the first's.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "product_code": ["TERM", "WL", "TERM"],
                "renewal_code": ["WL", "TERM", "WL"],
                "lapse_id": [1, 2, 1],
                "sum_assured": [100_000.0, 250_000.0, 150_000.0],
            }
        )
    )
    frame = frame.join(_product_table(), on="product_code")
    frame = frame.join(_lapse_parameters(), on="lapse_id")
    frame = frame.rename(
        {"expense_loading": "initial_loading", "commission_rate": "initial_commission"}
    )
    frame = frame.join(
        _product_table(), left_on="renewal_code", right_on="product_code"
    )
    frame.expenses = frame.sum_assured * frame.initial_loading
    return frame


def _entries_of(artifact: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Return the directory's entries of one kind, in the order it wrote them."""
    return [entry for entry in artifact["assumptions"] if entry["kind"] == kind]


def test_each_distinct_right_side_reaches_one_entry() -> None:
    """A directory of what the model rests on, not a log of the joins."""
    artifact = _artifact(_a_model_shaped_like_level_four())

    entries = _entries_of(artifact, "join")

    assert len(entries) == 2
    assert len({entry["fingerprint"] for entry in entries}) == 2


def test_a_joined_node_names_the_entry_its_right_side_became() -> None:
    """The node's own attribute is the whole of the join to its base."""
    artifact = json.loads(
        GraphExporter(_a_model_shaped_like_level_four()).export(profile="executable")
    )
    declared = {entry["fingerprint"] for entry in _entries_of(artifact, "join")}

    joined = [
        node
        for node in artifact["nodes"]
        if (node.get("expr") or {}).get("name") == "join"
    ]

    assert len(joined) == 6
    assert {
        dict(node["expr"]["attrs"])["right_fingerprint"] for node in joined
    } == declared


def test_a_join_entry_is_named_after_its_own_contents() -> None:
    """A right side is a frame handed to one call, and nobody named it."""
    artifact = _artifact(_a_model_shaped_like_level_four())
    entries = _entries_of(artifact, "join")

    assert entries
    for entry in entries:
        digest = entry["fingerprint"].removeprefix("sha256:")
        assert entry["name"] == f"join:{digest[:8]}"


def test_a_join_payload_carries_no_roles() -> None:
    """Equality of key values is the whole matching rule, so there are none."""
    artifact = _artifact(_a_model_shaped_like_level_four())

    payload = _entries_of(artifact, "join")[0]["payload"]

    assert set(payload) == {"columns", "rows"}


def test_a_join_payload_re_hashes_to_its_declared_fingerprint() -> None:
    """The one check carrying the values exists to pass, over a right side."""
    artifact = _artifact(_a_model_shaped_like_level_four())
    entries = _entries_of(artifact, "join")

    assert entries
    for entry in entries:
        assert _content_sha_of_payload(entry) == entry["fingerprint"]


def test_a_join_payload_carries_the_rows_in_the_order_they_were_hashed() -> None:
    """Columns by name, rows sorted by every column: §12.3's form of a right side."""
    artifact = _artifact(_a_model_shaped_like_level_four())

    entry = next(
        found
        for found in _entries_of(artifact, "join")
        if "product_code" in [column["name"] for column in found["payload"]["columns"]]
    )

    assert [column["name"] for column in entry["payload"]["columns"]] == [
        "commission_rate",
        "expense_loading",
        "product_code",
    ]
    assert entry["payload"]["rows"] == [
        [0.40, 0.05, "TERM"],
        [0.60, 0.08, "WL"],
    ]


def test_a_joined_node_reads_no_assumption() -> None:
    """The field says what a formula read, and an arriving column read nothing.

    The directory carries the right side; the per-node index does not name
    it. A consumer reading a non-empty ``reads_assumptions`` as a lookup --
    the viewer's proof classifier is one -- would otherwise read every
    arriving column as one, and an arriving column resolved no base: the key
    selected the row and computed no value.
    """
    artifact = json.loads(
        GraphExporter(_a_model_shaped_like_level_four()).export(profile="executable")
    )

    joined = [
        node
        for node in artifact["nodes"]
        if (node.get("expr") or {}).get("name") == "join"
    ]

    assert joined
    assert all(node["reads_assumptions"] == [] for node in joined)
    assert _entries_of(artifact, "join")


def test_a_join_that_brings_no_column_reaches_no_entry() -> None:
    """No node was minted, so there is no read for the directory to report."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "product_code": ["TERM", "WL"]})
    )
    frame = frame.join(
        pl.DataFrame({"product_code": ["TERM", "WL"]}), on="product_code"
    )
    frame.doubled = frame.policy_id * 2

    artifact = _artifact(frame)

    assert _entries_of(artifact, "join") == []


def test_a_lazy_right_side_reaches_no_entry() -> None:
    """No identity was taken, so there is nothing to file an entry under."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "product_code": ["TERM", "WL"]})
    )
    frame = frame.join(_product_table().lazy(), on="product_code")
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))

    joined = next(
        node
        for node in artifact["nodes"]
        if (node.get("expr") or {}).get("name") == "join"
    )

    assert dict(joined["expr"]["attrs"])["right_fingerprint"] is None
    assert _entries_of(artifact, "join") == []


def _a_model_joining_a_right_side_the_guard_will_refuse() -> ActuarialFrame:
    """Return a model whose one right side weighs more than a small guard."""
    codes = [f"P{index:04d}" for index in range(500)]
    frame = ActuarialFrame(pl.DataFrame({"product_code": codes[:3]}))
    return frame.join(
        pl.DataFrame(
            {
                "product_code": codes,
                "expense_loading": [0.05 + index / 10_000 for index in range(500)],
            }
        ),
        on="product_code",
    )


def test_a_right_side_above_the_guard_says_so_and_states_its_weight() -> None:
    """The guard governs a join entry exactly as it governs a table's."""
    artifact = _artifact(
        _a_model_joining_a_right_side_the_guard_will_refuse(),
        table_payload_limit=_A_SMALL_GUARD,
    )

    payload = _entries_of(artifact, "join")[0]["payload"]

    assert payload["omitted"] == "size"
    assert payload["bytes"] > _A_SMALL_GUARD


def test_a_right_side_travels_beside_the_document_when_it_is_not_inlined(
    tmp_path: Path,
) -> None:
    """The sidecar door files a join entry's values like any other entry's."""
    document: dict[str, Any] = json.loads(
        GraphExporter(
            _a_model_joining_a_right_side_the_guard_will_refuse()
        ).export_with_sidecar(tmp_path)
    )

    entry = _entries_of(document, "join")[0]
    beside = tmp_path / PAYLOAD_DIRECTORY / payload_file_name(entry["fingerprint"])

    fetched = json.loads(beside.read_text("utf-8"))

    assert _content_sha_of_payload({"payload": fetched}) == entry["fingerprint"]


def test_payload_of_round_trips_a_right_side_by_its_identity() -> None:
    """Read back under the digest the node carries, and it hashes to it."""
    artifact = _artifact(_a_model_shaped_like_level_four())
    entry = _entries_of(artifact, "join")[0]

    payload = payload_of(
        ArtefactReference(
            kind="join", name=entry["name"], fingerprint=entry["fingerprint"]
        )
    )

    assert payload is not None
    assert _content_sha_of_payload({"payload": payload}) == entry["fingerprint"]


def test_a_right_side_this_process_cannot_reach_keeps_its_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model exported from a log that crossed a process boundary, from inside."""
    frame = _a_model_shaped_like_level_four()
    exporter = GraphExporter(frame)
    monkeypatch.setattr(artefacts, "_JOIN_RIGHTS", {})

    artifact: dict[str, Any] = json.loads(exporter.export())

    for entry in _entries_of(artifact, "join"):
        assert entry["payload"] == {"omitted": "unavailable"}
        assert entry["fingerprint"].startswith("sha256:")


def test_a_join_entry_passes_the_validator_as_written() -> None:
    """A good entry is a good entry, and the deep reading says so."""
    document = GraphExporter(_a_model_shaped_like_level_four()).export(
        profile="executable"
    )

    assert _entries_of(json.loads(document), "join")
    assert validate_artifact(document, deep=True).ok


def test_one_edited_cell_in_a_right_side_is_an_error() -> None:
    """A payload that hashes to something else is not the table the run used."""
    artifact = json.loads(GraphExporter(_a_model_shaped_like_level_four()).export())
    entry = _entries_of(artifact, "join")[0]
    entry["payload"]["rows"][0][-1] += 0.01

    report = validate_artifact(json.dumps(artifact), deep=True)

    assert not report.ok
    assert any(
        finding.severity == "error" and "/assumptions/" in finding.where
        for finding in report.findings
    )


def test_a_join_entry_stating_a_dimension_is_refused_by_the_schema() -> None:
    """A join declares no roles, so an entry claiming one is not this kind."""
    artifact = json.loads(GraphExporter(_a_model_shaped_like_level_four()).export())
    entry = _entries_of(artifact, "join")[0]
    entry["payload"]["dimensions"] = ["product_code"]

    report = validate_artifact(json.dumps(artifact))

    assert not report.ok
    assert any(finding.section == "schema" for finding in report.findings)
