# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Undeclared source columns are set aside, not promoted to dimension keys.

`dimensions=` is the user's statement of the key set, and the framework uses
exactly that. The old behaviour treated every non-value column as a key, so a
frame carrying an extra published column (an earned rate next to a credited
rate) failed several steps later with a key-dtype error that never named the
column (gh#66).
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import (
    CategoricalDimension,
    ComputedDimension,
    MeltDimension,
    Table,
)


def test_extra_float_column_is_ignored_not_promoted() -> None:
    """The gh#66 repro: an unreferenced Float64 column must not become a key."""
    source = pl.DataFrame(
        {
            "year": [1, 2, 3],
            "earned_rate": [0.044, 0.047, 0.055],  # never referenced below
            "credited_rate": [0.03, 0.032, 0.04],
        },
    )
    table = Table(
        name="undeclared_credited",
        source=source,
        dimensions={"policy_year": "year"},
        value="credited_rate",
    )
    result = pl.DataFrame({"policy_year": [2]}).with_columns(
        rate=table.lookup(policy_year=pl.col("policy_year")),
    )
    assert result.get_column("rate").to_list() == [0.032]


def test_lookup_result_matches_pre_trimmed_source() -> None:
    """Ignoring the extra column must equal the user trimming it by hand."""
    wide = pl.DataFrame(
        {
            "year": [1, 2],
            "note_count": [7, 9],
            "rate": [0.1, 0.2],
        },
    )
    with_extra = Table(
        name="undeclared_wide",
        source=wide,
        dimensions={"policy_year": "year"},
        value="rate",
    )
    trimmed = Table(
        name="undeclared_trimmed",
        source=wide.select("year", "rate"),
        dimensions={"policy_year": "year"},
        value="rate",
    )
    keys = pl.DataFrame({"policy_year": [1, 2]})
    got = keys.with_columns(rate=with_extra.lookup(policy_year=pl.col("policy_year")))
    want = keys.with_columns(rate=trimmed.lookup(policy_year=pl.col("policy_year")))
    assert got.equals(want)


def test_melt_dimension_keeps_only_declared_columns() -> None:
    """A wide table with a stray column melts on the declared columns only."""
    source = pl.DataFrame(
        {
            "age": [40, 41],
            "MNS": [0.001, 0.002],
            "FNS": [0.003, 0.004],
            "source_note": ["a", "b"],  # would become a String key
        },
    )
    table = Table(
        name="undeclared_melt",
        source=source,
        dimensions={
            "age": "age",
            "rate_class": MeltDimension(columns=["MNS", "FNS"], name="rate_class"),
        },
        value="value",
    )
    result = pl.DataFrame({"age": [41], "rate_class": ["FNS"]}).with_columns(
        rate=table.lookup(age=pl.col("age"), rate_class=pl.col("rate_class")),
    )
    assert result.get_column("rate").to_list() == [0.004]


def test_computed_dimension_consumed_inputs_do_not_become_keys() -> None:
    """A ComputedDimension's input column must not leak into the key set.

    The expression reads ``issue_age`` to build ``age_next``; only
    ``age_next`` is a declared dimension, so only it registers as a key.
    Previously the consumed input stayed in the frame and was promoted.
    """
    source = pl.DataFrame(
        {
            "issue_age": [40, 41],
            "unused_note": [1.5, 2.5],
            "rate": [0.1, 0.2],
        },
    )
    table = Table(
        name="undeclared_computed",
        source=source,
        dimensions={
            "age_next": ComputedDimension(
                expression=pl.col("issue_age") + 1, name="age_next"
            ),
        },
        value="rate",
    )
    result = pl.DataFrame({"age_next": [42]}).with_columns(
        rate=table.lookup(age_next=pl.col("age_next")),
    )
    assert result.get_column("rate").to_list() == [0.2]


def test_categorical_dimension_still_registers() -> None:
    """A constant dimension consumes nothing and must survive the trim."""
    source = pl.DataFrame(
        {
            "year": [1, 2],
            "stray": [9.9, 8.8],
            "rate": [0.1, 0.2],
        },
    )
    table = Table(
        name="undeclared_categorical",
        source=source,
        dimensions={
            "policy_year": "year",
            "basis": CategoricalDimension(value="best_estimate", name="basis"),
        },
        value="rate",
    )
    keys = pl.DataFrame({"policy_year": [1], "basis": ["best_estimate"]})
    result = keys.with_columns(
        rate=table.lookup(policy_year=pl.col("policy_year"), basis=pl.col("basis")),
    )
    assert result.get_column("rate").to_list() == [0.1]


def test_missing_value_column_still_raises() -> None:
    """The trim must not swallow the existing value-column validation."""
    source = pl.DataFrame({"year": [1], "rate": [0.1]})
    with pytest.raises(ValueError, match="not found"):
        Table(
            name="undeclared_missing_value",
            source=source,
            dimensions={"policy_year": "year"},
            value="credited_rate",
        )
