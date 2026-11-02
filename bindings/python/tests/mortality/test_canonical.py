# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""MortalityTable canonical-form + source_sha tests."""

from __future__ import annotations

import polars as pl

from gaspatchio.assumptions import Table
from gaspatchio.mortality._mortality_table import MortalityTable


class TestCanonicalForm:
    """Canonical form keys: kind, table_name, table_dimensions, table_fingerprint, age_basis, structure, select_period."""  # noqa: E501

    def test_aggregate_canonical_shape(self, aggregate_table: Table) -> None:
        """Aggregate canonical form has all expected keys."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        cf = m.canonical_form()
        assert cf == {
            "kind": "MortalityTable",
            "table_name": "cso_2017_male_aggregate",
            "table_dimensions": ["age"],
            "table_fingerprint": aggregate_table.fingerprint(),
            "age_basis": "age_last_birthday",
            "structure": "aggregate",
            "select_period": None,
        }

    def test_select_ultimate_canonical_shape(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate canonical form includes the select_period."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        cf = m.canonical_form()
        assert cf == {
            "kind": "MortalityTable",
            "table_name": "select_ultimate_demo",
            "table_dimensions": ["age", "duration"],
            "table_fingerprint": select_ultimate_table.fingerprint(),
            "age_basis": "age_last_birthday",
            "structure": "select_ultimate",
            "select_period": 10,
        }

    def test_canonical_dimensions_are_sorted(self, joint_life_table: Table) -> None:
        """Dimensions list is sorted alphabetically for determinism."""
        m = MortalityTable(
            table=joint_life_table,
            age_basis="age_last_birthday",
            structure="joint",
        )
        cf = m.canonical_form()
        assert cf["table_dimensions"] == ["age_1", "age_2"]


class TestSourceSha:
    """sha256:<hex> over canonical_bytes, carrying the Table's content fingerprint."""

    def test_identical_mortality_tables_have_identical_sha(
        self,
        aggregate_table: Table,
    ) -> None:
        """Two identically-constructed MortalityTables hash equal."""
        a = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        b = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        assert a.source_sha() == b.source_sha()

    def test_different_age_basis_changes_sha(self, aggregate_table: Table) -> None:
        """Two tables differing only in age_basis have different SHAs."""
        a = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        b = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )
        assert a.source_sha() != b.source_sha()

    def test_different_select_period_changes_sha(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """Two select_ultimate tables differing only in select_period hash differently."""  # noqa: E501
        a = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=10,
        )
        b = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=15,
        )
        assert a.source_sha() != b.source_sha()

    def test_different_table_name_changes_sha(self) -> None:
        """Two MortalityTables with different underlying Table.name hash differently."""
        frame = pl.DataFrame({"age": [30, 35], "qx": [0.001, 0.002]})
        t1 = Table(
            name="cso_2017_male",
            source=frame,
            dimensions={"age": "age"},
            value="qx",
        )
        t2 = Table(
            name="cso_2017_female",
            source=frame,
            dimensions={"age": "age"},
            value="qx",
        )
        a = MortalityTable(
            table=t1,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        b = MortalityTable(
            table=t2,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self, aggregate_table: Table) -> None:
        """source_sha format is `sha256:<64-hex>`."""
        m = MortalityTable(
            table=aggregate_table,
            age_basis="age_last_birthday",
            structure="aggregate",
        )
        sha = m.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64


class TestContentIdentity:
    """The rates are part of the wrapper's identity (spec section 11.1.10)."""

    def test_same_name_different_rates_never_share_an_identity(self) -> None:
        """Two bases under one name and one convention, rates apart, stamp apart."""
        stamps = []
        for rate in (0.001, 0.002):
            table = Table(
                name="mortality_content_identity",
                source=pl.DataFrame({"age": [40, 41], "qx": [rate, rate * 1.1]}),
                dimensions={"age": "age"},
                value="qx",
            )
            basis = MortalityTable(
                table=table, age_basis="age_last_birthday", structure="aggregate"
            )
            assert basis.fingerprint() == table.fingerprint()
            stamps.append((basis.source_sha(), basis.fingerprint()))

        assert stamps[0][0] != stamps[1][0]
        assert stamps[0][1] != stamps[1][1]

    def test_the_rates_alone_do_not_carry_the_convention(
        self, aggregate_table: Table
    ) -> None:
        """One table under two conventions: one fingerprint, two source_shas."""
        alb = MortalityTable(
            table=aggregate_table, age_basis="age_last_birthday", structure="aggregate"
        )
        anb = MortalityTable(
            table=aggregate_table,
            age_basis="age_nearest_birthday",
            structure="aggregate",
        )

        assert alb.fingerprint() == anb.fingerprint()
        assert alb.source_sha() != anb.source_sha()
