# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Checked integer conversion refuses loss and preserves exact integer values."""

from __future__ import annotations

import datetime
import json
import math
import re

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.lowering.context import LoweringContext
from gaspatchio.frame.lowering.polars import lower_polars


@pytest.mark.parametrize("as_list", [False, True])
def test_signed_integer_limits_never_pass_through_a_float(*, as_list: bool) -> None:
    values = [-(2**63), -(2**53 + 1), 0, 2**53 + 1, 2**63 - 1]
    series = pl.Series("value", [values] if as_list else values)
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    result = frame.collect()["converted"]
    assert result.to_list() == series.to_list()
    assert result.dtype == (pl.List(pl.Int64) if as_list else pl.Int64)


@pytest.mark.parametrize("as_list", [False, True])
def test_float_conversion_accepts_the_representable_boundaries(
    *, as_list: bool
) -> None:
    values = [float(-(2**63)), -0.0, 42.0, math.nextafter(float(2**63), -math.inf)]
    frame = ActuarialFrame({"value": [values] if as_list else values})
    frame.converted = frame.value.to_integer()
    expected = [int(value) for value in values]
    assert frame.collect()["converted"].to_list() == (
        [expected] if as_list else expected
    )


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        1.5,
        -0.5,
        math.nan,
        math.inf,
        -math.inf,
        float(2**63),
        math.nextafter(float(-(2**63)), -math.inf),
    ],
)
@pytest.mark.parametrize("as_list", [False, True])
def test_lossy_or_missing_values_refuse_instead_of_truncating(
    invalid: float | None, *, as_list: bool
) -> None:
    values = [0.0, invalid]
    series = pl.Series(
        "value",
        [values] if as_list else values,
        dtype=pl.List(pl.Float64) if as_list else pl.Float64,
    )
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    with pytest.raises(pl.exceptions.InvalidOperationError, match="checked Int64"):
        frame.collect()


@pytest.mark.parametrize("inner", [pl.Int64, pl.Float64])
def test_null_lists_refuse_even_though_they_have_no_elements(
    inner: type[pl.DataType],
) -> None:
    frame = ActuarialFrame({"value": pl.Series([None], dtype=pl.List(inner))})
    frame.converted = frame.value.to_integer()
    with pytest.raises(pl.exceptions.InvalidOperationError, match="checked Int64"):
        frame.collect()


@pytest.mark.parametrize(
    "series",
    [
        pl.Series([True]),
        pl.Series(["1"]),
        pl.Series([datetime.date(2026, 1, 1)]),
    ],
)
@pytest.mark.parametrize("as_list", [False, True])
def test_non_numeric_meanings_are_not_inferred(
    series: pl.Series, *, as_list: bool
) -> None:
    if as_list:
        series = pl.Series([series.to_list()], dtype=pl.List(series.dtype))
    frame = ActuarialFrame({"value": series})
    with pytest.raises(TypeError, match="only integer or floating-point"):
        frame.converted = frame.value.to_integer()


@pytest.mark.parametrize("width", [pl.UInt64, pl.Int128, pl.UInt128])
@pytest.mark.parametrize("as_list", [False, True])
def test_a_width_wider_than_i64_converts_on_the_values_it_holds(
    width: type[pl.DataType], *, as_list: bool
) -> None:
    """An over-wide column is an integer column, judged like any other.

    The storage width is the warehouse's decision and the artifact records
    no width, so refusing the type refused a completed run for a fact about
    a Parquet writer. What has no ``i64`` is a value, and only a value.
    """
    values = [7, 2**62]
    series = pl.Series(
        "value",
        [values] if as_list else values,
        dtype=pl.List(width) if as_list else width,
    )
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    result = frame.collect()["converted"]
    assert result.to_list() == ([values] if as_list else values)
    assert result.dtype == (pl.List(pl.Int64) if as_list else pl.Int64)


@pytest.mark.parametrize(
    ("width", "offending"),
    [(pl.UInt64, 2**63), (pl.Int128, -(2**63) - 1), (pl.UInt128, 2**100)],
    ids=["unsigned_past_the_top", "signed_past_the_bottom", "unsigned_far_past"],
)
@pytest.mark.parametrize("as_list", [False, True])
def test_a_value_no_i64_carries_refuses_as_a_range_rather_than_a_fraction(
    width: type[pl.DataType], offending: int, *, as_list: bool
) -> None:
    """The refusal says which defect it met, and offers the door that fits it.

    A whole number too wide for an ``i64`` is whole, so the fractional
    refusal's advice -- floor, ceil, round -- is advice about a defect this
    column does not have. Text is what keeps every digit, which is the same
    remedy the audit export offers at the same boundary.
    """
    values = [1, offending]
    series = pl.Series(
        "value",
        [values] if as_list else values,
        dtype=pl.List(width) if as_list else width,
    )
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        frame.collect()
    message = str(raised.value)
    assert "holds a whole number outside the signed 64-bit range" in message
    assert "af.value.to_text()" in message
    assert "floor()" not in message


@pytest.mark.parametrize("as_list", [False, True])
def test_an_absent_wide_value_still_refuses_as_an_absence(*, as_list: bool) -> None:
    """The two refusals on the wide path stay disjoint, both ways round."""
    values = [1, None]
    series = pl.Series(
        "value",
        [values] if as_list else values,
        dtype=pl.List(pl.UInt64) if as_list else pl.UInt64,
    )
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        frame.collect()
    message = str(raised.value)
    assert "holds a value that is not one" in message
    assert "holds a whole number outside the signed 64-bit range" not in message


def test_empty_lists_and_no_policies_preserve_shape_and_integer_dtype() -> None:
    for values in ([], [[], []]):
        frame = ActuarialFrame({"value": pl.Series(values, dtype=pl.List(pl.Float64))})
        frame.converted = frame.value.to_integer()
        result = frame.collect()["converted"]
        assert result.to_list() == values
        assert result.dtype == pl.List(pl.Int64)


@pytest.mark.parametrize("as_list", [False, True])
def test_null_signed_integers_refuse_on_the_exact_integer_path(
    *, as_list: bool
) -> None:
    values = [2**63 - 1, None]
    series = pl.Series(
        [values] if as_list else values,
        dtype=pl.List(pl.Int64) if as_list else pl.Int64,
    )
    frame = ActuarialFrame({"value": series})
    frame.converted = frame.value.to_integer()
    with pytest.raises(pl.exceptions.InvalidOperationError, match="checked Int64"):
        frame.collect()


def test_checked_conversion_and_selection_export_as_core_with_the_index_read() -> None:
    frame = ActuarialFrame({"position": [1.0], "cash": [[100.0, 200.0]]})
    frame.index = frame.position.to_integer()
    frame.selected = frame.cash.list.get(frame.index)
    artifact = GraphExporter(frame).export(profile="executable")
    assert validate_artifact(artifact, deep=True).ok
    nodes = {node["id"]: node for node in json.loads(artifact)["nodes"]}
    assert nodes["index@1"]["dtype"] == "i64"
    assert nodes["index@1"]["tier"] == "core"
    assert nodes["index@1"]["expr"] == {
        "op": "call",
        "name": "to_integer",
        "args": [{"op": "col", "name": "position"}],
        "attrs": {},
    }
    assert nodes["selected@1"]["tier"] == "core"
    assert nodes["selected@1"]["reads"] == ["cash", "index@1"]
    assert frame.collect()["selected"].to_list() == [200.0]


# What each of these six defects raises, one sentence per defect. They used
# to share `match="requires"`, which 32 refusals in the package satisfy, and
# then the full sentence of their own operation -- which still left the three
# to_integer defects indistinguishable from each other and the three list.get
# defects likewise, because each rule restated the signature it wanted rather
# than the way this call missed it. Both rules now say which half broke: the
# operand count they were handed, or the attribute they do not carry, named.
# Swap any case's node for its neighbour's and that case fails. `re.escape`
# because the sentences quote attribute names and end on a section number.


@pytest.mark.parametrize(
    ("node", "refusal"),
    [
        (
            Call("to_integer", (), ()),
            "to_integer carries no operands and takes exactly one",
        ),
        (
            Call("to_integer", (Col("position"), Col("position")), ()),
            "to_integer carries 2 operands and takes exactly one",
        ),
        (
            Call("to_integer", (Col("position"),), (("truncate", True),)),
            (
                "to_integer does not carry the attribute 'truncate', which "
                "arrived here as True"
            ),
        ),
        (
            Call("list.get", (Col("cash"),), ()),
            "list.get carries one operand and takes exactly two",
        ),
        (
            Call("list.get", (Col("cash"), Col("position"), Col("position")), ()),
            "list.get carries 3 operands and takes exactly two",
        ),
        (
            Call("list.get", (Col("cash"), Col("position")), (("null_on_oob", True),)),
            (
                "list.get does not carry the attribute 'null_on_oob', which "
                "arrived here as True"
            ),
        ),
    ],
    ids=[
        "to_integer_no_operand",
        "to_integer_two_operands",
        "to_integer_stray_attribute",
        "list_get_one_operand",
        "list_get_three_operands",
        "list_get_stray_attribute",
    ],
)
def test_replay_refuses_a_signature_outside_the_declared_contract(
    node: Call, refusal: str
) -> None:
    frame = ActuarialFrame({"position": [0], "cash": [[100.0]]})
    with pytest.raises(TypeError, match=re.escape(refusal)):
        lower_polars(node, LoweringContext(frame))
