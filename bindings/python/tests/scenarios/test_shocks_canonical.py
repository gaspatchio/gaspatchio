# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test Shock.canonical_form for all 11 subclasses."""

from __future__ import annotations

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    RelativeFloorShock,
    TimeConditionalShock,
)


def test_multiplicative_canonical_form():
    """MultiplicativeShock encodes kind plus every dataclass field, keys sorted."""
    shock = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    cf = shock.canonical_form()
    assert cf == {
        "kind": "MultiplicativeShock",
        "column": None,
        "factor": 1.15,
        "table": "mortality",
    }


def test_additive_canonical_form():
    """AdditiveShock encodes delta plus targeting fields."""
    shock = AdditiveShock(delta=0.005, table="rates", column="value")
    cf = shock.canonical_form()
    assert cf == {
        "kind": "AdditiveShock",
        "column": "value",
        "delta": 0.005,
        "table": "rates",
    }


def test_pipeline_canonical_form_recurses():
    """PipelineShock recurses into its tuple of inner shocks."""
    inner_a = MultiplicativeShock(factor=1.5, table="lapse", column=None)
    inner_b = ClipShock(min_value=None, max_value=1.0, table="lapse", column=None)
    shock = PipelineShock(shocks=(inner_a, inner_b), table="lapse", column=None)
    cf = shock.canonical_form()
    assert cf["kind"] == "PipelineShock"
    assert cf["shocks"][0]["kind"] == "MultiplicativeShock"
    assert cf["shocks"][1]["kind"] == "ClipShock"
    assert cf["shocks"][0]["factor"] == 1.5
    assert cf["shocks"][1]["max_value"] == 1.0


def test_filtered_canonical_form_dict_sorted():
    """FilteredShock encodes its filter dict (sorted) and recurses into inner shock."""
    inner = MultiplicativeShock(factor=2.0, table="mortality", column=None)
    shock = FilteredShock(
        shock=inner,
        where={"duration": {"lte": 5}},
        table="mortality",
        column=None,
    )
    cf = shock.canonical_form()
    assert cf["kind"] == "FilteredShock"
    assert cf["where"] == {"duration": {"lte": 5}}
    assert cf["shock"]["kind"] == "MultiplicativeShock"


def test_time_conditional_canonical_form():
    """TimeConditionalShock encodes when-clause plus time_column."""
    inner = AdditiveShock(delta=0.001, table="rates", column=None)
    shock = TimeConditionalShock(
        shock=inner,
        when={"t": {"eq": 0}},
        table="rates",
        column=None,
        time_column="t",
    )
    cf = shock.canonical_form()
    assert cf["kind"] == "TimeConditionalShock"
    assert cf["time_column"] == "t"
    assert cf["when"] == {"t": {"eq": 0}}


def test_max_min_canonical_form():
    """MaxShock/MinShock recurse into both shock_a and shock_b."""
    a = MultiplicativeShock(factor=0.9, table="lapse", column=None)
    b = MultiplicativeShock(factor=1.1, table="lapse", column=None)
    max_shock = MaxShock(shock_a=a, shock_b=b, table="lapse", column=None)
    min_shock = MinShock(shock_a=a, shock_b=b, table="lapse", column=None)
    assert max_shock.canonical_form()["kind"] == "MaxShock"
    assert min_shock.canonical_form()["kind"] == "MinShock"
    assert max_shock.canonical_form()["shock_a"]["factor"] == 0.9


def test_override_canonical_form_scalar():
    """OverrideShock with a scalar float encodes cleanly."""
    shock = OverrideShock(value=0.5, table="mortality", column=None)
    cf = shock.canonical_form()
    assert cf["value"] == 0.5


def test_override_canonical_form_rejects_non_scalar():
    """OverrideShock with a non-scalar value raises TypeError at canonical_form time."""
    import pytest

    shock = OverrideShock(value={1, 2, 3}, table="mortality", column=None)
    with pytest.raises(TypeError, match="not canonical-encodable"):
        shock.canonical_form()


def test_relative_floor_canonical_form():
    """RelativeFloorShock encodes its delta field."""
    shock = RelativeFloorShock(delta=0.001, table="rates", column=None)
    assert shock.canonical_form()["kind"] == "RelativeFloorShock"


def test_canonical_form_keys_sorted():
    """canonical_form returns a dict with keys in sorted order."""
    shock = MultiplicativeShock(factor=1.2, table="z_table", column="a_col")
    cf = shock.canonical_form()
    keys = list(cf.keys())
    assert keys == sorted(keys)


def test_two_equal_shocks_same_canonical_form():
    """Two shocks with identical fields produce identical canonical forms."""
    a = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    b = MultiplicativeShock(factor=1.15, table="mortality", column=None)
    assert a.canonical_form() == b.canonical_form()
