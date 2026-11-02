# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A conditional states what the branch that did not fire would have held.

"What would this have been if the condition had gone the other way?" is the
question a reviewer puts to every ``when`` in a model, and the record could
not answer it: the walk-through names the branch that fired, and the other
branch is in no column of the finished frame. So a producer that is asked
evaluates both -- through the same lowering the model ran under, against the
same row every sample was read off -- and writes them beside the sample,
with the branch the condition chose named.

Asked, and not otherwise. The member is opt-in because it costs an
evaluation of both branches of every conditional, and the tests below hold
that from both ends: every shape stating its two branches under the flag,
and a default export that is the document it always was.
"""

from __future__ import annotations

import copy
import datetime
import json
from typing import TYPE_CHECKING, Any, Final, cast

import polars as pl
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame, when
from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter, GraphExportConfig, validate_artifact

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# The digest of the model below, measured on the producer that had never
# heard of ``branches``. It is pinned here rather than recomputed because
# that is half the claim: the member is enrichment, it sits outside the
# canonical bytes, and a node that gained one is the same calculation it
# was before.
_GRAPH_FINGERPRINT: Final[str] = (
    "sha256:27cb7cb6c194005e716f41a7be92257dc391d99814030dd4c160878485223b1c"
)

# The run the model below lays down: seven periods, months 0 to 6, and a
# term that ends inside them so that a per-period condition has somewhere
# to change its mind.
_PERIODS: Final[int] = 7

MODEL_SRC = """
from gaspatchio import ActuarialFrame, when


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")
    return af
"""


def _the_model() -> ActuarialFrame:
    """Return a seven-period run holding one of each shape a conditional comes in.

    A conditional on a per-policy column, whose two branches are two
    values; a nested one on the same, where the outer ``otherwise`` is
    itself a conditional; a per-period conditional whose condition changes
    inside the run; and a nested per-period one. Beside them an ordinary
    multiplication and four arriving columns, none of which is a
    conditional at all.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A"],
                "profit": [-95.0],
                "sum_assured": [100_000.0],
                "term_months": [4],
            }
        )
    )
    af = frame.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=6, frequency="monthly"
    )
    af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")
    af.capped_term = (
        when(af.term_months < 0)
        .then(0)
        .otherwise(when(af.term_months > 5).then(5).otherwise(af.term_months))
    )
    af.in_force = when(af.month < af.term_months).then(1.0).otherwise(0.0)
    af.band = (
        when(af.month < 2)
        .then(0.0)
        .otherwise(when(af.month < 4).then(1.0).otherwise(2.0))
    )
    af.claims = af.sum_assured * 0.001
    return af


def _exported(*, branches: bool) -> dict[str, Any]:
    """Return the artifact that model exports, parsed back from the wire."""
    af = _the_model()
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(af.collect(), GraphExportConfig(branches=branches))
    )
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    (found,) = [entry for entry in artifact["nodes"] if entry["id"] == node_id]
    return found


# --- the four shapes a conditional comes in ----------------------------------


def test_a_conditional_on_a_per_policy_column_states_two_values() -> None:
    """The gap this closes, in the line that showed it.

    ``"No"`` is in the record and always was. ``"Yes"`` -- what the column
    would have held had the profit been positive -- was nowhere, and no
    consumer holding the file could work it out.
    """
    node = _node(_exported(branches=True), "is_profitable@1")

    assert node["value_sample"] == "No"
    assert node["branches"] == {"then": "Yes", "otherwise": "No", "fired": "otherwise"}


def test_a_nested_conditional_states_the_outer_branch_only() -> None:
    """Two branches, because two is what the reader is choosing between.

    ``when(term < 0).then(0).otherwise(when(term > 5).then(5).otherwise(term))``
    states ``0`` and ``4``: the inner conditional is evaluated as part of
    the outer ``otherwise`` and states nothing of its own. A record naming
    all four would leave a reader asking which two of them the line chose
    between.
    """
    node = _node(_exported(branches=True), "capped_term@1")

    assert node["value_sample"] == 4
    assert node["branches"] == {"then": 0, "otherwise": 4, "fired": "otherwise"}


def test_a_per_period_conditional_names_the_branch_for_every_period() -> None:
    """The condition changes inside the run, and the record says where.

    The term ends at month 4, so the four months before it took the
    ``then`` branch and the three after it the ``otherwise`` one. Both
    branches are written across the whole run even though each is one
    literal, so period 5's value and period 5's alternative are indexed
    the same way.
    """
    node = _node(_exported(branches=True), "in_force@1")

    assert node["value_sample"] == [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    assert node["branches"] == {
        "then": [1.0] * _PERIODS,
        "otherwise": [0.0] * _PERIODS,
        "fired": ["then", "then", "then", "then"] + ["otherwise"] * 3,
    }


def test_a_nested_per_period_conditional_states_the_run_its_inner_branch_came_to() -> (
    None
):
    """The outer ``otherwise`` is the inner conditional's own run of values.

    Months 0 and 1 take the outer ``then``; the rest take the outer
    ``otherwise``, which is itself ``1.0`` up to month 4 and ``2.0``
    after. What the node states is the two runs, not the three.
    """
    node = _node(_exported(branches=True), "band@1")

    assert node["value_sample"] == [0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 2.0]
    assert node["branches"] == {
        "then": [0.0] * _PERIODS,
        "otherwise": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0],
        "fired": ["then", "then"] + ["otherwise"] * 5,
    }


def test_the_branch_that_fired_reconstructs_the_sample_on_every_conditional() -> None:
    """Reading the named branch at each period gives the column back.

    This is the one check that ties the member to the model rather than to
    itself: the values were evaluated separately from the column, and
    picking the named one period by period has to come back to what the
    column held. Anything else means a branch was evaluated against
    something the line did not run on.
    """
    artifact = _exported(branches=True)

    for node in artifact["nodes"]:
        if "branches" not in node:
            continue
        stated, sample = node["branches"], node["value_sample"]
        if isinstance(stated["fired"], list):
            taken = [
                stated[word][period] for period, word in enumerate(stated["fired"])
            ]
        else:
            taken = stated[stated["fired"]]
        assert taken == sample, node["id"]


def test_the_shape_of_the_branch_that_fired_is_the_shape_of_the_column() -> None:
    """One word for one value, one word per period for a run of them."""
    artifact = _exported(branches=True)

    for node_id in ("is_profitable@1", "capped_term@1"):
        assert isinstance(_node(artifact, node_id)["branches"]["fired"], str)
    for node_id in ("in_force@1", "band@1"):
        fired = _node(artifact, node_id)["branches"]["fired"]
        assert isinstance(fired, list)
        assert len(fired) == len(_node(artifact, node_id)["value_sample"])


# --- and nothing else states any -------------------------------------------


def test_a_node_that_is_not_a_conditional_states_no_branches() -> None:
    """A multiplication has one answer, so it has no second one to show."""
    assert "branches" not in _node(_exported(branches=True), "claims@1")


def test_the_four_conditionals_are_the_only_nodes_that_state_branches() -> None:
    """Named in full, because the absence is the claim on every other node."""
    artifact = _exported(branches=True)

    stated = [node["id"] for node in artifact["nodes"] if "branches" in node]

    assert stated == ["is_profitable@1", "capped_term@1", "in_force@1", "band@1"]
    assert len(artifact["nodes"]) - len(stated) == 9


def test_nobody_asking_gets_no_member_anywhere() -> None:
    """Opt-in, and the default is the document that has always been written."""
    artifact = _exported(branches=False)

    for node in artifact["nodes"]:
        assert "branches" not in node, node["id"]


def test_an_artifact_carrying_no_values_carries_no_branches() -> None:
    """The member is enrichment, so it travels with the context it means under.

    Asked for on an export with no frame behind it, there is no row to
    evaluate a branch against and no ``enrichment`` block to read one
    under -- so the node states nothing rather than stating a branch
    nobody can place.
    """
    artifact = json.loads(
        GraphExporter(_the_model()).export(config=GraphExportConfig(branches=True))
    )

    assert artifact["enrichment"] is None
    for node in artifact["nodes"]:
        assert "branches" not in node, node["id"]


# --- and no digest moves, and nothing else on the default path --------------


def test_stating_both_branches_moves_no_fingerprint() -> None:
    """The member is enrichment and enrichment is no part of the canonical bytes.

    The digest below was taken on the producer before ``branches`` existed.
    A member that moved it would say the model changed when what changed is
    what the file says about it, and every quarter-on-quarter comparison
    drawn on these digests would report a difference nobody made.
    """
    asked = _exported(branches=True)
    default = _exported(branches=False)

    assert asked["graph_fingerprint"] == _GRAPH_FINGERPRINT
    assert default["graph_fingerprint"] == _GRAPH_FINGERPRINT
    assert [node["fingerprint"] for node in asked["nodes"]] == [
        node["fingerprint"] for node in default["nodes"]
    ]
    assert [node["local_fingerprint"] for node in asked["nodes"]] == [
        node["local_fingerprint"] for node in default["nodes"]
    ]


def test_the_flag_adds_the_member_and_moves_nothing_else() -> None:
    """Byte for byte the same document, apart from the member and the clock.

    Asserted by taking the member back out: what is left has to serialise
    to exactly what the default path writes. A field reordered, a value
    formatted differently, a node key added anywhere else would all fail
    here, which is what "opt-in" has to mean if it is to mean anything.
    """
    asked = _exported(branches=True)
    default = _exported(branches=False)
    for node in asked["nodes"]:
        node.pop("branches", None)
    asked["created_at"] = default["created_at"] = ""
    asked.pop("document_digest", None)
    default.pop("document_digest", None)

    assert json.dumps(asked, indent=2) == json.dumps(default, indent=2)


def test_the_document_the_flag_writes_is_a_conforming_one() -> None:
    """Schema and semantic reading both, against the published schema."""
    assert validate_artifact(_exported(branches=True)).ok


# --- from the command line ---------------------------------------------------


def _from_the_command_line(tmp_path: Path, *options: str) -> dict[str, Any]:
    """Export the one-line model from the command line and read it back."""
    model = tmp_path / "model.py"
    model.write_text(MODEL_SRC)
    points = tmp_path / "points.parquet"
    pl.DataFrame({"policy_id": ["A"], "profit": [-95.0]}).write_parquet(points)
    out = tmp_path / "graph.json"
    result = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(out), *options]
    )
    assert result.exit_code == 0, result.output
    return cast("dict[str, Any]", json.loads(out.read_text()))


def test_the_command_line_flag_writes_the_member(tmp_path: Path) -> None:
    """``--branches`` is how a reader asks, and this is what they get."""
    node = _node(_from_the_command_line(tmp_path, "--branches"), "is_profitable@1")

    assert node["branches"] == {"then": "Yes", "otherwise": "No", "fired": "otherwise"}


def test_the_command_line_without_the_flag_writes_none(tmp_path: Path) -> None:
    """Default off, which is the whole of what opt-in costs a reader who did not ask."""
    artifact = _from_the_command_line(tmp_path)

    for node in artifact["nodes"]:
        assert "branches" not in node, node["id"]


# --- the ways it can be mis-stated, and the refusals -------------------------


def _with_branches(node_id: str, stated: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return the artifact with one node's ``branches`` replaced by ``stated``."""
    artifact = _exported(branches=True)
    _node(artifact, node_id)["branches"] = stated
    return artifact


def _refusals(artifact: dict[str, Any]) -> list[str]:
    """Return the error-grade messages the semantic reading draws.

    Filtered to that reading on purpose. Most of the mis-statements below
    are refused twice over -- the published schema constrains the member
    too -- and what these tests are about is the reading that states the
    rule in the model's own terms.
    """
    return [
        finding.message
        for finding in validate_artifact(artifact).findings
        if finding.severity == "error" and finding.section == "semantic"
    ]


def _schema_refuses(artifact: dict[str, Any]) -> bool:
    """Return whether the published schema refuses the document as it stands."""
    return any(
        finding.section == "schema" and finding.severity == "error"
        for finding in validate_artifact(artifact).findings
    )


def test_branches_on_a_node_that_executes_nothing_is_refused() -> None:
    """A column that arrived ran no conditional, so it chose between nothing."""
    refused = _refusals(
        _with_branches("profit", {"then": 1, "otherwise": 2, "fired": "then"})
    )

    assert refused, "branches on a leaf drew no refusal"
    assert "its ``kind`` is 'input'" in refused[0]
    assert "only a 'computed' node has any" in refused[0]


def test_a_branches_object_that_is_not_the_three_parts_is_refused() -> None:
    """A key missing and a key too many read the same way to a reviewer."""
    a_key_short = _refusals(
        _with_branches("is_profitable@1", {"then": "Yes", "otherwise": "No"})
    )
    a_key_over = _refusals(
        _with_branches(
            "is_profitable@1",
            {"then": "Yes", "otherwise": "No", "fired": "then", "cond": True},
        )
    )
    nothing_at_all = _refusals(_with_branches("is_profitable@1", {}))

    assert a_key_short, "a missing member drew no refusal"
    assert "the three parts are ['fired', 'otherwise', 'then']" in a_key_short[0]
    assert a_key_over, "an unknown member drew no refusal"
    assert nothing_at_all, "an empty object drew no refusal"
    assert _schema_refuses(
        _with_branches("is_profitable@1", {"then": "Yes", "otherwise": "No"})
    )


def test_a_branch_named_in_a_word_that_is_not_one_is_refused() -> None:
    """Two branches, and the two words the formula itself uses."""
    a_third_word = _refusals(
        _with_branches(
            "is_profitable@1", {"then": "Yes", "otherwise": "No", "fired": "neither"}
        )
    )
    inside_a_run = _refusals(
        _with_branches(
            "in_force@1",
            {
                "then": [1.0] * _PERIODS,
                "otherwise": [0.0] * _PERIODS,
                "fired": ["then", "then", "then", "then", "else", "else", "else"],
            },
        )
    )

    assert a_third_word, "a third word drew no refusal"
    assert "names the branch that fired as 'neither'" in a_third_word[0]
    assert inside_a_run, "a third word inside the run drew no refusal"
    assert "names the branch that fired as 'else'" in inside_a_run[0]
    assert _schema_refuses(
        _with_branches(
            "is_profitable@1", {"then": "Yes", "otherwise": "No", "fired": "neither"}
        )
    )


def test_a_run_of_words_on_a_column_holding_one_value_is_refused() -> None:
    """A per-policy column was decided once, so there is one branch to name."""
    refused = _refusals(
        _with_branches(
            "is_profitable@1",
            {"then": "Yes", "otherwise": "No", "fired": ["otherwise"]},
        )
    )

    assert refused, "a run of words on a per-policy column drew no refusal"
    assert "once per period and its ``shape`` is 'scalar'" in refused[0]


def test_one_word_beside_a_run_of_values_is_refused() -> None:
    """A per-period conditional is decided period by period, and says so."""
    refused = _refusals(
        _with_branches(
            "in_force@1",
            {
                "then": [1.0] * _PERIODS,
                "otherwise": [0.0] * _PERIODS,
                "fired": "then",
            },
        )
    )

    assert refused, "one word beside a run of values drew no refusal"
    assert f"carries {_PERIODS} periods of values beside it" in refused[0]


def test_a_run_of_words_that_is_not_the_run_of_values_is_refused() -> None:
    """The two are read against each other, period by period, or not at all."""
    refused = _refusals(
        _with_branches(
            "in_force@1",
            {
                "then": [1.0] * _PERIODS,
                "otherwise": [0.0] * _PERIODS,
                "fired": ["then", "otherwise"],
            },
        )
    )

    assert refused, "a run of the wrong length drew no refusal"
    assert "fired for 2 periods" in refused[0]
    assert f"carries {_PERIODS} periods of values" in refused[0]


def test_one_finding_per_node_however_many_ways_it_is_wrong() -> None:
    """Four readings of one object, and a reader fixes it once."""
    wrong = copy.deepcopy(_exported(branches=True))
    _node(wrong, "in_force@1")["branches"] = {"fired": ["neither"], "then": 1}

    assert len(_refusals(wrong)) == 1


def test_a_well_stated_pair_of_branches_is_accepted() -> None:
    """The refusals bite on the mis-statement rather than on the member."""
    assert validate_artifact(_exported(branches=True)).ok


def test_every_policy_on_the_axis_states_its_own_branches(tmp_path: Path) -> None:
    """``--policies all`` reads each policy's branches off that policy's row.

    The branches were evaluated off the frame's first row whatever the axis
    entry, so a book whose flag ran False/True/False said ``fired:
    otherwise`` for all three -- beside a sample and a walk-through that
    were each policy's own, and that said ``then`` for the second.
    """
    model = tmp_path / "model.py"
    model.write_text(
        "from gaspatchio import ActuarialFrame, when\n\n\n"
        "def main(af: ActuarialFrame) -> ActuarialFrame:\n"
        "    af.picked = when(af.flag).then(af.a).otherwise(af.b)\n"
        "    return af\n"
    )
    points = tmp_path / "points.parquet"
    pl.DataFrame(
        {
            "policy_id": ["P1", "P2", "P3"],
            "flag": [False, True, False],
            "a": [1.0, 2.0, 3.0],
            "b": [10.0, 20.0, 30.0],
        }
    ).write_parquet(points)
    out = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(out),
            "--policies",
            "all",
            "--branches",
        ],
    )
    assert result.exit_code == 0, result.output
    artifact = json.loads(out.read_text())
    node = next(entry for entry in artifact["nodes"] if entry["column"] == "picked")

    assert node["branches"] == [
        {"then": 1.0, "otherwise": 10.0, "fired": "otherwise"},
        {"then": 2.0, "otherwise": 20.0, "fired": "then"},
        {"then": 3.0, "otherwise": 30.0, "fired": "otherwise"},
    ]
    assert node["value_sample"] == [10.0, 2.0, 30.0]
