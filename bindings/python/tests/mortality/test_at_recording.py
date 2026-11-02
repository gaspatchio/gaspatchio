# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a convention-aware mortality read puts on the record.

A select and ultimate basis holds a duration at its select period before it
reads. That clamp is the convention, and until this recording door existed
the convention reached the artifact nowhere: the clamp arrived as one
engine's rendering of a bounded column, and the structure, the select
period and the age basis arrived not at all. Two models over one grid
differing only in the age definition their rates were built on exported as
the same calculation with the same digest.

These tests hold the door to three things. The read records under its own
name, with the convention on it. The assumption base underneath is named
exactly as it was before -- the same `reads_assumptions` entry, the same
section of the artifact -- because a door that moved a base's account of
itself would have traded one gap for another. And a convention that
changes is a calculation that changes, which is the whole point.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio import ActuarialFrame, MortalityTable
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.tiers import tier_of

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode


def _tree_of(frame: ActuarialFrame, node_id: str) -> OpNode:
    """Return the operation tree the fold holds for one node."""
    return fold(frame).op_trees[node_id]


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s audit-profile artifact, parsed back from the wire."""
    exported: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return exported


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _a_select_and_ultimate_read(select_ultimate_table: Table) -> ActuarialFrame:
    """Return a frame whose rate came from a select and ultimate basis."""
    basis = MortalityTable(
        table=select_ultimate_table,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=4,
    )
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "age": [30, 40], "duration": [1, 3]})
    )
    frame.qx = basis.at(age=frame.age, duration=frame.duration)
    return frame


class TestTheReadRecordsUnderItsOwnName:
    """One identifier, carrying the convention the read was made under."""

    def test_a_select_and_ultimate_read_is_one_recorded_operation(
        self, select_ultimate_table: Table
    ) -> None:
        """The clamp and the read are one node, not a fragment around a lookup."""
        tree = _tree_of(_a_select_and_ultimate_read(select_ultimate_table), "qx@1")

        assert isinstance(tree, Call)
        assert tree.name == "mortality.at"
        assert tree.args == (Col("age"), Col("duration"))

    def test_the_convention_is_on_the_node(self, select_ultimate_table: Table) -> None:
        """Structure, select period and age basis, each readable without a rerun."""
        tree = _tree_of(_a_select_and_ultimate_read(select_ultimate_table), "qx@1")
        assert isinstance(tree, Call)
        attrs = dict(tree.attrs)

        assert attrs["structure"] == "select_ultimate"
        assert attrs["select_period"] == 4
        assert attrs["age_basis"] == "age_last_birthday"
        assert attrs["dimensions"] == "age,duration"

    def test_the_wrapper_carries_its_own_published_identity(
        self, select_ultimate_table: Table
    ) -> None:
        """The digest on the node is the wrapper's own ``source_sha()``."""
        basis = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = ActuarialFrame(pl.DataFrame({"age": [30], "duration": [1]}))
        frame.qx = basis.at(age=frame.age, duration=frame.duration)
        tree = _tree_of(frame, "qx@1")
        assert isinstance(tree, Call)

        assert dict(tree.attrs)["mortality"] == basis.source_sha()

    def test_a_read_the_vocabulary_names_is_core(
        self, select_ultimate_table: Table
    ) -> None:
        """The clamp used to make every downstream column engine-native."""
        tree = _tree_of(_a_select_and_ultimate_read(select_ultimate_table), "qx@1")

        assert tier_of(tree) == "core"

    def test_an_aggregate_read_records_under_the_same_identifier(
        self, aggregate_table: Table
    ) -> None:
        """One identifier for all three structures; the structure tells them apart."""
        basis = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        frame = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
        frame.qx = basis.at(age=frame.age)
        tree = _tree_of(frame, "qx@1")
        assert isinstance(tree, Call)

        assert tree.name == "mortality.at"
        assert dict(tree.attrs)["structure"] == "aggregate"

    def test_a_basis_with_no_select_period_records_none(
        self, aggregate_table: Table
    ) -> None:
        """Absent, not null: a basis with no select period has none to record."""
        basis = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        frame = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
        frame.qx = basis.at(age=frame.age)
        tree = _tree_of(frame, "qx@1")
        assert isinstance(tree, Call)

        assert "select_period" not in dict(tree.attrs)

    def test_a_joint_read_records_both_ages_as_its_dimensions(
        self, joint_life_table: Table
    ) -> None:
        """A joint basis reads a pair of lives, and the node says which columns."""
        basis = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        frame = ActuarialFrame(pl.DataFrame({"age_1": [60, 65], "age_2": [65, 70]}))
        frame.qx = basis.at(age_1=frame.age_1, age_2=frame.age_2)
        tree = _tree_of(frame, "qx@1")
        assert isinstance(tree, Call)

        assert dict(tree.attrs)["dimensions"] == "age_1,age_2"
        assert tree.args == (Col("age_1"), Col("age_2"))

    def test_a_further_dimension_stands_after_the_structure_s_own(self) -> None:
        """A table identifier follows in the order the read was written."""
        table = Table(
            name="select_by_table_id",
            source=pl.DataFrame(
                {
                    "table_id": ["M", "M", "F", "F"],
                    "age": [30, 30, 30, 30],
                    "duration": [1, 2, 1, 2],
                    "qx": [0.0011, 0.0012, 0.0009, 0.0010],
                }
            ),
            dimensions={
                "age": "age",
                "duration": "duration",
                "table_id": "table_id",
            },
            value="qx",
        )
        basis = MortalityTable(
            table=table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=2,
        )
        frame = ActuarialFrame(
            pl.DataFrame({"age": [30, 30], "duration": [1, 9], "sex": ["M", "F"]})
        )
        frame.qx = basis.at(age=frame.age, duration=frame.duration, table_id=frame.sex)
        tree = _tree_of(frame, "qx@1")
        assert isinstance(tree, Call)

        assert dict(tree.attrs)["dimensions"] == "age,duration,table_id"
        assert tree.args == (Col("age"), Col("duration"), Col("sex"))
        assert frame.collect()["qx"].to_list() == [0.0011, 0.0010]


class TestTheBaseIsNamedExactlyAsBefore:
    """A door that hid the assumption base would trade one gap for another."""

    def test_the_node_still_reads_the_base_it_always_read(
        self, select_ultimate_table: Table
    ) -> None:
        """``reads_assumptions`` finds this node the way it found the lookup."""
        artifact = _artifact(_a_select_and_ultimate_read(select_ultimate_table))

        assert _node(artifact, "qx@1")["reads_assumptions"] == ["select_ultimate_demo"]

    def test_the_artifact_still_carries_the_base_and_its_values(
        self, select_ultimate_table: Table
    ) -> None:
        """One entry, under the assumption table's own content identity."""
        artifact = _artifact(_a_select_and_ultimate_read(select_ultimate_table))

        (entry,) = artifact["assumptions"]
        assert (entry["kind"], entry["name"]) == ("table", "select_ultimate_demo")
        assert entry["payload"]["dimensions"] == ["age", "duration"]

    def test_the_node_carries_the_table_identity_a_lookup_carries(
        self, select_ultimate_table: Table
    ) -> None:
        """The same pair, in the same attributes, as the read it stands for."""
        tree = _tree_of(_a_select_and_ultimate_read(select_ultimate_table), "qx@1")
        assert isinstance(tree, Call)
        attrs = dict(tree.attrs)

        assert attrs["table"] == "select_ultimate_demo"
        assert str(attrs["table_fingerprint"]).startswith("sha256:")


class TestAConventionThatChangesIsACalculationThatChanges:
    """The defect this door closes, stated as the thing that must not happen."""

    def test_two_reads_of_one_grid_on_two_age_bases_are_two_calculations(
        self, aggregate_table: Table
    ) -> None:
        """Half a year of mortality, and nothing in the record used to show it.

        ``age_last_birthday`` and ``age_nearest_birthday`` are different
        definitions of the same integer. A basis built on one and read with
        ages computed on the other is wrong by up to half a year, and both
        sides are integers, so no run reports it. Before this door the two
        models exported byte for byte alike.
        """
        exported = []
        for basis_age in ("age_last_birthday", "age_nearest_birthday"):
            basis = MortalityTable(
                table=aggregate_table,
                age_basis=basis_age,  # type: ignore[arg-type]
                structure="aggregate",
            )
            frame = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
            frame.qx = basis.at(age=frame.age)
            exported.append(_artifact(frame))

        first, second = exported
        assert first["graph_fingerprint"] != second["graph_fingerprint"]
        assert (
            _node(first, "qx@1")["local_fingerprint"]
            != _node(second, "qx@1")["local_fingerprint"]
        )

    def test_the_rates_the_two_bases_answer_with_are_the_same(
        self, aggregate_table: Table
    ) -> None:
        """The record moved; the numbers did not. Identity is not arithmetic."""
        answers = []
        for basis_age in ("age_last_birthday", "age_nearest_birthday"):
            basis = MortalityTable(
                table=aggregate_table,
                age_basis=basis_age,  # type: ignore[arg-type]
                structure="aggregate",
            )
            frame = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
            frame.qx = basis.at(age=frame.age)
            answers.append(frame.collect()["qx"].to_list())

        assert answers[0] == answers[1] == [0.001, 0.002]
