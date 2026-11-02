# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Two artifacts of one model, a quarter apart, and what actually moved.

A model-change review does not ask "are these two files different?" -- two
exports of an untouched model are different, because one of them was written
later. It asks the two questions a valuation committee has to answer: which
calculations were edited, and which numbers can no longer be the same because
the data underneath them was re-sourced. Those are different findings with
different owners, and a report that ran them together would be a report
nobody could act on.

What is asserted here is the report's claims rather than any digest this
particular model happens to produce: that an edit is attributed to the line
that holds it, that everything below it says it inherited the movement, that
a new quarter of mortality is data and not a model change, and that a rename
the framework saw is a rename while a rename it did not see is a removal, an
addition, and a hint that never hardens into a claim.
"""

from __future__ import annotations

import copy
import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.curves import Curve
from gaspatchio.frame.graph.artifact import FINGERPRINT_ALGORITHM
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.diff import (
    DIFF_REPORT_VERSION,
    Change,
    DataChange,
    diff_artifacts,
)
from gaspatchio.frame.graph.graph_models import GraphExportConfig, ModelIdentity

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gaspatchio.frame.graph.diff import DiffReport

# --- the model the report is written about ----------------------------------


def _mortality_table(rate: float) -> Table:
    """Return the one mortality basis this valuation rests on."""
    return Table(
        name="mortality",
        source=pl.DataFrame(
            {"age": [40, 41, 55, 56], "rate": [rate, rate, rate, rate]}
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _policies() -> pl.DataFrame:
    """Return the two policies every fixture below is run over."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "attained_age": [40, 55],
            "sum_assured": [100_000.0, 250_000.0],
            "premium": [1_200.0, 3_400.0],
        }
    )


def _next_quarters_policies() -> pl.DataFrame:
    """Return the same two policies a quarter on, one sum assured revised."""
    return _policies().with_columns(pl.Series("sum_assured", [100_000.0, 275_000.0]))


def _a_quarterly_valuation(
    mortality_rate: float = 0.001, policies: pl.DataFrame | None = None
) -> ActuarialFrame:
    """Write the valuation: one lookup, claims off it, a cashflow and a reserve."""
    table = _mortality_table(mortality_rate)
    af = ActuarialFrame(_policies() if policies is None else policies)
    af.mortality_rate = table.lookup(age=af.attained_age)
    af.death_claims = af.sum_assured * af.mortality_rate
    af.net_cashflow = af.premium - af.death_claims
    af.reserve = af.net_cashflow * 0.9
    return af


def _the_valuation_with_the_claims_formula_edited(
    mortality_rate: float = 0.001,
) -> ActuarialFrame:
    """Write the same valuation with a loading added to the claims line."""
    table = _mortality_table(mortality_rate)
    af = ActuarialFrame(_policies())
    af.mortality_rate = table.lookup(age=af.attained_age)
    af.death_claims = af.sum_assured * af.mortality_rate * 1.05
    af.net_cashflow = af.premium - af.death_claims
    af.reserve = af.net_cashflow * 0.9
    return af


def _the_valuation_with_the_lookup_key_edited(
    mortality_rate: float = 0.001,
) -> ActuarialFrame:
    """Write the same valuation, the mortality looked up a year further on."""
    table = _mortality_table(mortality_rate)
    af = ActuarialFrame(_policies())
    af.mortality_rate = table.lookup(age=af.attained_age + 1)
    af.death_claims = af.sum_assured * af.mortality_rate
    af.net_cashflow = af.premium - af.death_claims
    af.reserve = af.net_cashflow * 0.9
    return af


def _the_valuation_with_the_reserve_column_renamed() -> ActuarialFrame:
    """Write the same valuation with the last column written under a new name."""
    table = _mortality_table(0.001)
    af = ActuarialFrame(_policies())
    af.mortality_rate = table.lookup(age=af.attained_age)
    af.death_claims = af.sum_assured * af.mortality_rate
    af.net_cashflow = af.premium - af.death_claims
    af.policy_reserve = af.net_cashflow * 0.9
    return af


def _artifact(
    frame: ActuarialFrame, config: GraphExportConfig | None = None
) -> dict[str, Any]:
    """Return the artifact for ``frame``, which is what the report compares.

    Exported the way a model is, so the document records the book the frame
    was built over: a document written with no book beside it gives a
    comparison nothing to say about the policy data, and is reported so.
    """
    document: dict[str, Any] = json.loads(GraphExporter(frame).export(config=config))
    return document


def _before() -> dict[str, Any]:
    """Return last quarter's artifact."""
    return _artifact(_a_quarterly_valuation())


def _after_editing_the_death_claims_formula() -> dict[str, Any]:
    """Return this quarter's artifact, with one formula edited."""
    return _artifact(_the_valuation_with_the_claims_formula_edited())


def _after_re_sourcing_the_mortality_table() -> dict[str, Any]:
    """Return this quarter's artifact, with the same model and new mortality."""
    return _artifact(_a_quarterly_valuation(mortality_rate=0.002))


def _after_renaming_through_the_frame() -> dict[str, Any]:
    """Return this quarter's artifact, the reserve renamed through the frame."""
    return _artifact(_a_quarterly_valuation().rename({"reserve": "policy_reserve"}))


def _after_renaming_in_the_source_text() -> dict[str, Any]:
    """Return this quarter's artifact, the reserve renamed in the model source."""
    return _artifact(_the_valuation_with_the_reserve_column_renamed())


def _changes_by_node(changes: Iterable[Change]) -> dict[str, Change]:
    """Return the calculation changes keyed by the node each is about."""
    return {change.node: change for change in changes}


def _what_moved(report: DiffReport) -> tuple[Any, ...]:
    """Return everything a report says moved, and nothing about the documents."""
    return (report.drift, report.calculations, report.data)


# --- an edit, and everything below it ---------------------------------------


def test_an_edited_formula_is_a_change_of_its_own() -> None:
    """The line that was edited is the line the report holds responsible."""
    report = diff_artifacts(_before(), _after_editing_the_death_claims_formula())

    (change,) = [c for c in report.calculations if c.node == "death_claims@1"]

    assert (change.kind, change.change_origin) == ("changed", "self")


def test_everything_downstream_says_it_inherited_the_change() -> None:
    """The cashflow was not touched and its answer still cannot be what it was."""
    report = diff_artifacts(_before(), _after_editing_the_death_claims_formula())

    downstream = [c for c in report.calculations if c.node == "net_cashflow@1"]

    assert downstream[0].change_origin == "inherited"


def test_an_edit_reaches_every_column_below_it_and_no_column_above_it() -> None:
    """The whole account of one edit: three nodes move, four do not."""
    report = diff_artifacts(_before(), _after_editing_the_death_claims_formula())

    found = {c.node: c.change_origin for c in report.calculations}

    assert found == {
        "death_claims@1": "self",
        "net_cashflow@1": "inherited",
        "reserve@1": "inherited",
    }


def test_a_change_names_the_column_it_is_about() -> None:
    """A node id is the report's key; the column is what a reviewer reads."""
    report = diff_artifacts(_before(), _after_editing_the_death_claims_formula())

    (change,) = [c for c in report.calculations if c.node == "death_claims@1"]

    assert change.column == "death_claims"


def test_drift_is_true_as_soon_as_one_calculation_moved() -> None:
    """One question a pipeline step asks, answered without reading the list."""
    report = diff_artifacts(_before(), _after_editing_the_death_claims_formula())

    assert report.drift is True


# --- data moving is not the model moving ------------------------------------


def test_a_new_quarter_of_data_is_not_a_model_change() -> None:
    """The mortality basis was re-sourced and nothing in the model was touched."""
    report = diff_artifacts(_before(), _after_re_sourcing_the_mortality_table())

    assert [c.kind for c in report.data] == ["table"]
    assert not any(c.change_origin == "self" for c in report.calculations)


def test_a_re_sourced_table_names_itself_and_both_of_its_digests() -> None:
    """What the data section is for: which basis moved, and from what to what."""
    before, after = _before(), _after_re_sourcing_the_mortality_table()

    (change,) = diff_artifacts(before, after).data

    assert change.name == "mortality"
    assert change.before == before["assumptions"][0]["fingerprint"]
    assert change.after == after["assumptions"][0]["fingerprint"]
    assert change.before != change.after


def test_the_numbers_a_re_sourced_table_reaches_are_still_reported_as_moved() -> None:
    """Not a model change is not "no change": the reserve is a different number."""
    report = diff_artifacts(_before(), _after_re_sourcing_the_mortality_table())

    found = {c.node: c.change_origin for c in report.calculations}

    assert found == {
        "mortality_rate@1": "inherited",
        "death_claims@1": "inherited",
        "net_cashflow@1": "inherited",
        "reserve@1": "inherited",
    }
    assert report.drift is True


def test_an_edit_downstream_of_a_re_sourced_basis_is_still_an_edit() -> None:
    """The basis moving does not excuse the one line somebody actually changed."""
    before = _before()
    after = _artifact(_the_valuation_with_the_claims_formula_edited(0.002))

    found = _changes_by_node(diff_artifacts(before, after).calculations)

    assert found["death_claims@1"].change_origin == "self"
    assert found["mortality_rate@1"].change_origin == "inherited"


def test_an_edit_to_the_lookup_itself_survives_its_basis_being_re_sourced() -> None:
    """The hard case, and the one the attribution has to get right.

    Here the edited line is the line that reads the re-sourced base, so the
    node's own digest has two reasons to have moved. What separates them is
    the as-written formula beside it: the lookup key is not the key it was,
    so the report holds the line responsible rather than the table.
    """
    before = _before()
    after = _artifact(_the_valuation_with_the_lookup_key_edited(0.002))

    found = _changes_by_node(diff_artifacts(before, after).calculations)

    assert found["mortality_rate@1"].change_origin == "self"


def test_a_re_sourced_basis_under_an_untouched_lookup_key_is_not_an_edit() -> None:
    """The control for the case above: the same lookup, only the table moved."""
    before = _artifact(_the_valuation_with_the_lookup_key_edited(0.001))
    after = _artifact(_the_valuation_with_the_lookup_key_edited(0.002))

    found = _changes_by_node(diff_artifacts(before, after).calculations)

    assert found["mortality_rate@1"].change_origin == "inherited"


def test_new_policy_data_under_one_model_is_a_data_change() -> None:
    """The model points are what the run consumed, and they are not the model."""
    first = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q1.parquet", "fingerprint": "sha256:a"}
        )
    )
    later = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q2.parquet", "fingerprint": "sha256:b"}
        )
    )

    q1 = _artifact(_a_quarterly_valuation(), first)
    q2 = _artifact(_a_quarterly_valuation(policies=_next_quarters_policies()), later)

    report = diff_artifacts(q1, q2)

    assert [(c.kind, c.name, c.before, c.after) for c in report.data] == [
        ("model_points", "q2.parquet", q1["book"]["digest"], q2["book"]["digest"])
    ]
    assert report.calculations == ()


def test_a_replaced_in_force_file_is_something_moving() -> None:
    """The one-word answer has to be yes when the in-force file was replaced.

    Policy data is the one kind of data that reaches no calculation: every
    node's digest is the same digest, because the model is the same model
    and it never reads a model point by name. So this is the case that
    settles what the headline field means. "Did anything change since last
    quarter" is the question it is read for, and a report answering "no"
    over a quarter's new business teaches a committee to stop trusting the
    one word and read the lists -- at which point the field is worse than
    absent. The split a specialist wants is still there, and it is
    ``calculations`` and ``data``, exactly where it always was.
    """
    first = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q1.parquet", "fingerprint": "sha256:a"}
        )
    )
    later = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q2.parquet", "fingerprint": "sha256:b"}
        )
    )

    report = diff_artifacts(
        _artifact(_a_quarterly_valuation(), first),
        _artifact(_a_quarterly_valuation(policies=_next_quarters_policies()), later),
    )

    assert report.drift is True
    assert report.calculations == ()
    assert [c.kind for c in report.data] == ["model_points"]


def test_the_model_only_reading_is_the_calculations_list_itself() -> None:
    """A reviewer asking only about the model reads the list, not the headline."""
    first = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q1.parquet", "fingerprint": "sha256:a"}
        )
    )
    later = GraphExportConfig(
        model=ModelIdentity(
            model_points={"path": "q2.parquet", "fingerprint": "sha256:b"}
        )
    )

    report = diff_artifacts(
        _artifact(_a_quarterly_valuation(), first),
        _artifact(_a_quarterly_valuation(policies=_next_quarters_policies()), later),
    )

    assert bool(report.calculations) is False
    assert json.loads(json.dumps(report.to_dict()))["drift"] is True


# --- renames ----------------------------------------------------------------


def test_a_rename_the_framework_saw_is_reported_as_a_rename() -> None:
    """The frame recorded the name-move, so the report may say it was one."""
    report = diff_artifacts(_before(), _after_renaming_through_the_frame())

    (change,) = [c for c in report.calculations if c.kind == "renamed"]

    assert change.renamed_from == "reserve@1"


def test_a_rename_the_framework_saw_is_the_only_thing_it_reports() -> None:
    """Nothing was recomputed, so nothing else has any business being listed."""
    report = diff_artifacts(_before(), _after_renaming_through_the_frame())

    assert [(c.node, c.kind) for c in report.calculations] == [
        ("policy_reserve@1", "renamed")
    ]


def test_a_rename_the_framework_did_not_see_is_a_removal_and_an_addition_with_a_hint() -> (  # noqa: E501
    None
):
    """Fingerprints are not unique by design, so the report hints and never asserts."""
    report = diff_artifacts(_before(), _after_renaming_in_the_source_text())

    kinds = {c.kind for c in report.calculations}

    assert kinds == {"removed", "added"}
    added = next(c for c in report.calculations if c.kind == "added")
    assert added.fingerprint_equal_to == "reserve@1"


def test_a_hint_is_withheld_where_the_pairing_is_not_unique() -> None:
    """Two columns computed alike share a fingerprint, and neither hint is safe."""
    before = ActuarialFrame(_policies())
    before.reserve = before.premium * 0.9
    before.margin = before.premium * 0.9

    after = ActuarialFrame(_policies())
    after.policy_reserve = after.premium * 0.9
    after.prudential_margin = after.premium * 0.9

    report = diff_artifacts(_artifact(before), _artifact(after))

    assert {c.kind for c in report.calculations} == {"removed", "added"}
    assert all(c.fingerprint_equal_to is None for c in report.calculations)


def test_a_removal_and_an_addition_carry_no_change_origin() -> None:
    """Self or inherited is a question about a node that is in both files."""
    report = diff_artifacts(_before(), _after_renaming_in_the_source_text())

    assert all(c.change_origin is None for c in report.calculations)


# --- a calculation arriving and a calculation stopping ----------------------


def test_a_new_calculation_is_reported_as_added() -> None:
    """A genuinely new column is added, and nothing else is disturbed."""
    extended = _a_quarterly_valuation()
    extended.margin = extended.reserve * 0.05

    report = diff_artifacts(_before(), _artifact(extended))

    assert [(c.node, c.kind) for c in report.calculations] == [("margin@1", "added")]


def test_a_calculation_the_model_stopped_doing_is_reported_as_removed() -> None:
    """The mirror image, so ``added`` is not the only answer the report can give."""
    trimmed = ActuarialFrame(_policies())
    trimmed.mortality_rate = _mortality_table(0.001).lookup(age=trimmed.attained_age)
    trimmed.death_claims = trimmed.sum_assured * trimmed.mortality_rate
    trimmed.net_cashflow = trimmed.premium - trimmed.death_claims

    report = diff_artifacts(_before(), _artifact(trimmed))

    assert [(c.node, c.kind, c.column) for c in report.calculations] == [
        ("reserve@1", "removed", "reserve")
    ]


def test_a_horizon_change_moves_the_timeline_and_everything_below_it() -> None:
    """The worked case: ``until_value`` 99 becomes 100.

    The four columns the projection stamps share one record and one node, so
    that one configuration attribute moving is an edit *there*. Every
    calculation below the timeline is the formula it always was, and only its
    answer moved. That distinction is the whole point of the report.
    """
    report = diff_artifacts(_artifact(_a_projection(99)), _artifact(_a_projection(100)))

    found = {c.node: c.change_origin for c in report.calculations}

    assert {node for node, origin in found.items() if origin == "self"} == {
        "projection_start_date@1",
        "projection_end_date@1",
        "num_proj_months@1",
        "month@1",
    }
    assert {node for node, origin in found.items() if origin == "inherited"} == {
        "attained_age@1",
        "mortality_rate@1",
        "death_claims@1",
    }


def _a_projection(until_value: int) -> ActuarialFrame:
    """Build one projection horizon with three columns below it."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "issue_age": [40, 55],
                "sum_assured": [100_000.0, 250_000.0],
            }
        )
    )
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="maximum_age",
        until_value=until_value,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.mortality_rate = af.attained_age * 0.001
    af.death_claims = af.sum_assured * af.mortality_rate
    return af


# --- the identity core, and what is only metadata ---------------------------


def test_two_exports_of_an_unchanged_model_report_no_change() -> None:
    """The claim the whole report rests on, and a condition of releasing it.

    Two exports of one untouched model are written at different moments and
    say so -- but the timestamp is stamped to the second, so two exports
    taken back to back say the same moment and the document would be
    compared with itself. The metadata is therefore moved on purpose here
    rather than left to whether the two exports landed either side of a
    second boundary: the later document is stamped a quarter on and by a
    release of the exporter the earlier one never saw. The report compares
    the identity core and never the bytes, so the only honest answer is that
    nothing moved -- and it says which two documents it is answering about.
    """
    before, after = _before(), _before()
    after["created_at"] = "2027-04-01T00:00:00Z"
    after["producer"] = dict(after["producer"], version="99.0.0")

    report = diff_artifacts(before, after)

    assert (report.drift, report.calculations, report.data) == (False, (), ())
    earlier, later = report.compared
    assert earlier.graph_fingerprint == before["graph_fingerprint"]
    assert (earlier.created_at, later.created_at) != (None, None)
    assert earlier != later


def test_the_producing_tool_and_the_model_version_block_are_not_drift() -> None:
    """A new release of the exporter is not a change to anybody's valuation."""
    before = _before()
    after = _before()
    after["created_at"] = "2027-01-01T00:00:00Z"
    after["producer"] = {"name": "gaspatchio", "version": "99.0.0"}
    after["model"] = dict(after["model"], label="renamed in the run configuration")

    report = diff_artifacts(before, after)

    assert (report.drift, report.calculations, report.data) == (False, (), ())


def test_the_report_says_which_grammar_the_digests_were_taken_under() -> None:
    """Every claim in the report is a claim about digests of one grammar."""
    report = diff_artifacts(_before(), _before())

    assert report.fingerprint_algorithm == _before()["fingerprint_algorithm"]


def test_two_artifacts_from_different_grammars_refuse_to_be_compared() -> None:
    """There is no translation between byte grammars, so there is no answer.

    The other token is derived from the live one rather than written out.
    Both artifacts here come from this producer, so a token spelled in full
    is one the producer catches up with the day it moves -- and on that day
    the two documents agree, the refusal never fires, and this test passes by
    testing nothing.
    """
    before = _before()
    other = f"{FINGERPRINT_ALGORITHM}-and-a-half"
    after = _before() | {"fingerprint_algorithm": other}

    with pytest.raises(ValueError, match=other):
        diff_artifacts(before, after)


def test_the_refusal_names_both_grammars_and_the_next_move() -> None:
    """A refusal a reader can act on: which two, and what to do about it."""
    before = _before()
    other = f"{FINGERPRINT_ALGORITHM}-and-a-half"
    after = _before() | {"fingerprint_algorithm": other}

    with pytest.raises(ValueError, match=FINGERPRINT_ALGORITHM) as raised:
        diff_artifacts(before, after)

    assert FINGERPRINT_ALGORITHM in str(raised.value)
    assert other in str(raised.value)
    assert "Re-derive the fingerprints" in str(raised.value)


# --- the report as a document -----------------------------------------------


def test_the_report_is_json_serialisable_and_carries_its_own_version() -> None:
    """A report a pipeline stores is read back under the grammar it names."""
    report = diff_artifacts(_before(), _before())

    payload = json.loads(json.dumps(report.to_dict()))

    assert payload["report_version"] == "gaspatchio-graph-diff/v0-preview.2"
    assert payload["calculations"] == []
    assert payload["drift"] is False
    # Two audit files alone carry no numbers to measure.
    assert payload["values"] is None


def test_the_published_version_is_the_one_the_module_names() -> None:
    """The constant and the document say one thing, so neither can drift."""
    assert DIFF_REPORT_VERSION == "gaspatchio-graph-diff/v0-preview.2"


def test_the_report_says_which_two_documents_it_compared() -> None:
    """A stored report names its own subject, on the wire as well as in hand.

    The caller who held the two documents knows which two they were. The
    committee reading the report a quarter later holds the report and
    nothing else, so the report has to say.
    """
    before = _before()
    after = _after_editing_the_death_claims_formula()

    report = diff_artifacts(before, after)

    earlier, later = report.compared
    assert (earlier.graph_fingerprint, later.graph_fingerprint) == (
        before["graph_fingerprint"],
        after["graph_fingerprint"],
    )
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["compared"] == {
        "before": earlier.to_dict(),
        "after": later.to_dict(),
    }
    assert payload["compared"]["before"]["created_at"] == before["created_at"]
    assert payload["compared"]["after"]["producer"] is not None


def test_how_the_documents_are_described_never_reaches_what_moved() -> None:
    """Two reports over one pair say the same thing about what moved.

    When a document was written and which release of the exporter wrote it
    ride along as description, so a stored report can say what it compared.
    They are not evidence: the same pair described differently is the same
    pair, and the findings are identical.
    """
    before, after = _before(), _before()
    described_later = dict(after)
    described_later["created_at"] = "2027-04-01T00:00:00Z"
    described_later["producer"] = {"name": "gaspatchio", "version": "99.0.0"}

    plainly = diff_artifacts(before, after)
    lately = diff_artifacts(before, described_later)

    assert _what_moved(plainly) == _what_moved(lately)
    assert plainly.compared != lately.compared
    assert [document.graph_fingerprint for document in plainly.compared] == [
        document.graph_fingerprint for document in lately.compared
    ]


def test_one_change_writes_out_as_the_seven_things_it_says() -> None:
    """Every field a consumer reads is on the wire, including the empty ones."""
    change = Change(
        node="policy_reserve@1",
        column="policy_reserve",
        kind="renamed",
        change_origin=None,
        renamed_from="reserve@1",
        fingerprint_equal_to=None,
        values_equal_to=None,
    )

    assert change.to_dict() == {
        "node": "policy_reserve@1",
        "column": "policy_reserve",
        "kind": "renamed",
        "change_origin": None,
        "renamed_from": "reserve@1",
        "fingerprint_equal_to": None,
        "values_equal_to": None,
    }


def test_one_data_change_writes_out_as_what_it_says() -> None:
    """A base that moved, named, with the digest on each side and no reason.

    ``reason`` is written whatever it holds, null here: the two digests were
    compared, so there is nothing to explain.
    """
    change = DataChange(
        kind="table", name="mortality", before="sha256:aa", after="sha256:bb"
    )

    assert change.to_dict() == {
        "kind": "table",
        "name": "mortality",
        "before": "sha256:aa",
        "after": "sha256:bb",
        "reason": None,
    }


# --- the nodes whose identity is a digest and nothing else ------------------


def _a_model_with_an_unexplained_column() -> ActuarialFrame:
    """Write one column straight into the query plan, past every recording door."""
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 250.0]}))
    af.gross_reserve = af.premium * 0.9
    plan = af._df  # noqa: SLF001 -- the bypass under test
    assert plan is not None
    af._df = plan.with_columns((pl.col("premium") * 0.5).alias("lapse_reserve"))  # noqa: SLF001
    return af


def _a_model_that_accounts_for_every_column() -> ActuarialFrame:
    """Write the same model with nothing slipped past the recording."""
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 250.0]}))
    af.gross_reserve = af.premium * 0.9
    return af


def test_a_column_nothing_accounts_for_in_both_quarters_is_no_change() -> None:
    """A hole has no formula: its identity is a digest, and the digest held."""
    report = diff_artifacts(
        _artifact(_a_model_with_an_unexplained_column()),
        _artifact(_a_model_with_an_unexplained_column()),
    )

    assert report.calculations == ()


def test_a_column_nothing_accounts_for_arriving_is_reported_as_an_addition() -> None:
    """A hole that was not there last quarter is a column to explain."""
    report = diff_artifacts(
        _artifact(_a_model_that_accounts_for_every_column()),
        _artifact(_a_model_with_an_unexplained_column()),
    )

    assert [(c.node, c.kind, c.column) for c in report.calculations] == [
        ("lapse_reserve", "added", "lapse_reserve")
    ]


def test_a_column_nothing_accounted_for_being_explained_is_a_removal_and_an_addition() -> (  # noqa: E501
    None
):
    """Closing a hole retires the unexplained node and mints a computed one."""
    explained = _a_model_that_accounts_for_every_column()
    explained.lapse_reserve = explained.premium * 0.5

    report = diff_artifacts(
        _artifact(_a_model_with_an_unexplained_column()), _artifact(explained)
    )

    assert {(c.node, c.kind) for c in report.calculations} == {
        ("lapse_reserve", "removed"),
        ("lapse_reserve@1", "added"),
    }


def _a_model_handed_a_column_of_values(values: list[float]) -> ActuarialFrame:
    """Hand a whole column over wholesale, the way a simulation does."""
    af = ActuarialFrame({"policy_id": [1, 2, 3]})
    af.shock = pl.Series("", values)
    af.shocked_reserve = af.shock * 1_000.0
    return af


def test_the_same_values_injected_twice_are_no_change() -> None:
    """An injected column's identity is its contents, and the contents held."""
    report = diff_artifacts(
        _artifact(_a_model_handed_a_column_of_values([1.0, 2.0, 3.0])),
        _artifact(_a_model_handed_a_column_of_values([1.0, 2.0, 3.0])),
    )

    assert (report.drift, report.data) == (False, ())


def test_a_column_of_values_that_moved_is_data_rather_than_a_model_change() -> None:
    """Nothing but values is in those bytes, so nothing but data can have moved."""
    report = diff_artifacts(
        _artifact(_a_model_handed_a_column_of_values([1.0, 2.0, 3.0])),
        _artifact(_a_model_handed_a_column_of_values([1.0, 2.0, 9.0])),
    )

    (data,) = report.data
    assert (data.kind, data.name) == ("injection", "shock")
    assert data.before != data.after
    assert not any(c.change_origin == "self" for c in report.calculations)
    assert {c.node for c in report.calculations} == {"shock@1", "shocked_reserve@1"}


def _a_model_handed_one_column_of_values_under_a_name(name: str) -> ActuarialFrame:
    """Hand the same three numbers over under whichever name is asked for."""
    af = ActuarialFrame({"policy_id": [1, 2, 3]})
    af[name] = pl.Series("", [1.0, 2.0, 3.0])
    af.shocked_reserve = af[name] * 1_000.0
    return af


def test_a_pairing_between_two_handed_over_columns_says_the_values_match() -> None:
    """The same digest, and a weaker claim, because it was taken over values.

    A computed node's fingerprint stands for a calculation, so two of them
    agreeing is evidence -- never proof -- that the same calculation is
    present under a new name. An injected column's is a stamp over the
    numbers themselves, and two of those agreeing says the same numbers were
    handed over twice and nothing at all about a computation. Under the
    rename hint's own label a reviewer would be offered the stronger reading
    of the weaker evidence.
    """
    report = diff_artifacts(
        _artifact(_a_model_handed_one_column_of_values_under_a_name("shock")),
        _artifact(_a_model_handed_one_column_of_values_under_a_name("stress")),
    )

    added = next(c for c in report.calculations if c.node == "stress@1")

    assert added.values_equal_to == "shock@1"
    assert added.fingerprint_equal_to is None


# --- a base named after its own contents ------------------------------------


def _a_model_reading_a_curve(rates: list[float]) -> ActuarialFrame:
    """Return a model discounting on one yield curve."""
    af = ActuarialFrame(pl.DataFrame({"years_elapsed": [1.0, 2.0]}))
    curve = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=rates)
    af.spot_rate = curve.spot_rate(af.years_elapsed)
    return af


def _curve_named_in(artifact: dict[str, Any]) -> str:
    """Return the name the one curve entry of ``artifact`` carries."""
    (entry,) = [e for e in artifact["assumptions"] if e["kind"] == "curve"]
    name: str = entry["name"]
    return name


def test_a_base_named_after_its_contents_is_one_gone_and_one_arrived() -> None:
    """A curve is a value object, and its name moves with the values.

    A table is re-sourced under its own name and the entry says so from one
    digest to another. A curve is called after what it is made of, so a
    re-sourced one is not that entry under a new digest -- it is an entry
    gone and another arrived, which is the honest reading of a model that no
    longer reads what it read. What the name adds is that a reader can say
    *which* curve went and which came, and follow either back to the nodes
    that read it.
    """
    before = _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))
    after = _artifact(_a_model_reading_a_curve([0.03, 0.035, 0.04]))

    report = diff_artifacts(before, after)

    went, arrived = _curve_named_in(before), _curve_named_in(after)

    assert went.startswith("curve:")
    assert arrived.startswith("curve:")
    assert sorted((c.kind, c.name) for c in report.data) == sorted(
        [("curve", went), ("curve", arrived)]
    )
    assert {(c.before is None, c.after is None) for c in report.data} == {
        (False, True),
        (True, False),
    }


def test_a_node_reading_a_re_named_base_cannot_have_its_movement_attributed() -> None:
    """The stated limit of the attribution, pinned so it stays visible.

    A node reading a re-sourced *table* is reported as having inherited the
    change, because the table's name is the same string on both sides. A
    curve's name is its contents, so re-sourcing one changes the name the
    node gives as well as the digest the entry carries: there is no entry
    both files hold, and the movement is reported against the calculation.
    The data section beside it is what tells a reader what actually happened.
    """
    before = _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))
    after = _artifact(_a_model_reading_a_curve([0.03, 0.035, 0.04]))

    found = _changes_by_node(diff_artifacts(before, after).calculations)

    assert found["spot_rate@1"].change_origin == "self"


# --- the two files were written either side of an upgrade -------------------


def _as_a_producer_that_named_no_value_object_wrote_it(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    """Return ``artifact`` in the shape a producer wrote before the naming.

    A schedule and a curve carried ``name: null`` then, and a node could name
    no entry that had no name, so ``reads_assumptions`` stood empty on the
    node that read one. Nothing else about the document differs: the name
    enters no node's bytes, so every digest here is a digest that producer
    wrote for that model.
    """
    stored = copy.deepcopy(artifact)
    for entry in stored["assumptions"]:
        entry["name"] = None
    for node in stored["nodes"]:
        node["reads_assumptions"] = []
    return stored


def test_a_base_that_only_gained_a_name_is_not_a_base_gone_and_another_arrived() -> (
    None
):
    """The first comparison after an upgrade, on a model nobody touched.

    A change report's subject is two files, and the earlier one can have been
    written by a producer that named no value object. That entry states no
    name and this one states ``curve:<digest>``, under the digest neither of
    them moved -- read as two partitions it is a curve gone and a curve
    arrived, on the quarterly review of a model that was not edited. The
    label is not the identity; the digest beside it is, and one digest on
    both sides of the name partition is one entry.
    """
    stored = _as_a_producer_that_named_no_value_object_wrote_it(
        _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))
    )
    exported = _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))

    report = diff_artifacts(stored, exported)

    assert (report.drift, report.calculations, report.data) == (False, (), ())


def test_a_base_re_sourced_across_that_same_upgrade_still_went_and_came() -> None:
    """The reconciliation is by digest, so a moved digest is untouched by it.

    The same two producers, and this time the curve was re-sourced in the
    quarter between them. Nothing holds one digest on both sides, so there is
    nothing to reconcile: the earlier document's curve went, the later
    document's arrived, and a reader can say which was which from the name on
    the one and the digest on both.
    """
    stored = _as_a_producer_that_named_no_value_object_wrote_it(
        _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))
    )
    exported = _artifact(_a_model_reading_a_curve([0.03, 0.035, 0.04]))

    report = diff_artifacts(stored, exported)

    assert {(c.kind, c.before is None, c.after is None) for c in report.data} == {
        ("curve", False, True),
        ("curve", True, False),
    }


def _a_model_reading_two_curves(
    discounting: list[float], reinvestment: list[float]
) -> ActuarialFrame:
    """Return a model reading two yield curves rather than one."""
    af = ActuarialFrame(pl.DataFrame({"years_elapsed": [1.0, 2.0]}))
    af.spot_rate = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 3.0], rates=discounting
    ).spot_rate(af.years_elapsed)
    af.reinvestment_rate = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 3.0], rates=reinvestment
    ).spot_rate(af.years_elapsed)
    return af


def _with_one_entrys_name_taken_off(
    artifact: dict[str, Any], name: str
) -> dict[str, Any]:
    """Return ``artifact`` as a producer that had not named *that* base wrote it.

    The upgrade helper above nulls every name at once, which is the real
    shape of the two producers. This one nulls a single entry, so that one
    base can be mid-bridge while another beside it, of the same kind, is
    a base the later document genuinely no longer reads.
    """
    stored = copy.deepcopy(artifact)
    for entry in stored["assumptions"]:
        if entry["name"] == name:
            entry["name"] = None
    for node in stored["nodes"]:
        node["reads_assumptions"] = [
            read for read in node["reads_assumptions"] if read != name
        ]
    return stored


def test_a_base_that_really_went_still_reports_beside_one_that_only_bridged() -> None:
    """The reconciliation is per digest, and one bridge does not cover a kind.

    Two curves in the earlier document and one in the later: the discounting
    curve gained its name across the upgrade, and the reinvestment curve was
    dropped from the model in the same quarter. The first is the entry the
    reconciliation exists for; the second is a base that really went, and it
    is the finding a committee is reading for.

    Both are curves, so a reconciliation that asked whether the *kind* had
    anything bridged -- rather than whether this digest was the bridged one
    -- would swallow the removal and leave every other test here green. The
    two are put in one comparison so that they cannot be.
    """
    both = _artifact(
        _a_model_reading_two_curves([0.02, 0.025, 0.03], [0.04, 0.045, 0.05])
    )
    exported = _artifact(_a_model_reading_a_curve([0.02, 0.025, 0.03]))
    kept = _curve_named_in(exported)
    dropped = next(
        entry["name"]
        for entry in both["assumptions"]
        if entry["kind"] == "curve" and entry["name"] != kept
    )
    stored = _with_one_entrys_name_taken_off(both, kept)

    report = diff_artifacts(stored, exported)

    assert [
        (change.kind, change.name, change.before is None, change.after is None)
        for change in report.data
    ] == [("curve", dropped, False, True)]
