# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table's metadata is the metadata that table was given.

A governance pack reads ``table.metadata`` to say which experience study a
basis came from. The metadata was once kept in a registry keyed by the
table's name and written only when some was given, so a second table built
under the same name with none reported the first one's study, and a third
built with other metadata rewrote what the first one reported.
"""

from __future__ import annotations

import contextlib

import polars as pl

from gaspatchio.assumptions import Table, get_table_metadata


def _rates(scale: float) -> pl.DataFrame:
    return pl.DataFrame({"age": [40, 41], "rate": [0.001 * scale, 0.002 * scale]})


def test_a_table_given_no_metadata_reports_none() -> None:
    Table("meta_basis_a", _rates(1.0), {"age": "age"}, metadata={"basis": "2015 study"})
    later = Table("meta_basis_a", _rates(1.2), {"age": "age"})
    assert later.metadata is None
    assert get_table_metadata("meta_basis_a") is None


def test_a_later_table_does_not_rewrite_an_earlier_one() -> None:
    first = Table(
        "meta_basis_b", _rates(1.0), {"age": "age"}, metadata={"basis": "2018 study"}
    )
    Table("meta_basis_b", _rates(1.1), {"age": "age"}, metadata={"basis": "2025 study"})
    assert first.metadata == {"basis": "2018 study"}
    assert get_table_metadata("meta_basis_b") == {"basis": "2025 study"}


def test_the_name_reports_the_table_it_answers_to() -> None:
    Table("meta_basis_c", _rates(1.0), {"age": "age"}, metadata={"basis": "2015 study"})
    newest = Table(
        "meta_basis_c", _rates(1.3), {"age": "age"}, metadata={"basis": "2024 study"}
    )
    assert get_table_metadata("meta_basis_c") == newest.metadata


def test_a_table_that_fails_to_build_leaves_the_name_s_metadata() -> None:
    Table("meta_basis_d", _rates(1.0), {"age": "age"}, metadata={"basis": "kept"})
    with contextlib.suppress(Exception):
        Table("meta_basis_d", pl.DataFrame({"age": [40]}), {"age": "age"})
    assert get_table_metadata("meta_basis_d") == {"basis": "kept"}


def test_the_returned_metadata_is_a_copy() -> None:
    table = Table(
        "meta_basis_e", _rates(1.0), {"age": "age"}, metadata={"basis": "2019 study"}
    )
    held = table.metadata
    assert held is not None
    held["basis"] = "edited"
    assert table.metadata == {"basis": "2019 study"}
