# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The named conversions to text and to floating point, and what each refuses.

Conversions are a family of named, checked operations rather than one generic
``cast(type)``. What makes the family worth its cost is that each name is one
pair of meanings: a reviewer reading ``to_text`` off a trace knows nothing was
given up, and a reviewer reading ``to_float`` knows the value was inside the
interval where a double names every whole number. A generic cast would put
both behind one identifier and hand the reader the type pair to work out.

So these tests are written as the entry reads: what it accepts, what it
answers exactly, and what it refuses, on a scalar and on a list, at the
boundary, on a null and on an empty list.
"""

from __future__ import annotations

import datetime
import json
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.lowering.context import LoweringContext
from gaspatchio.frame.lowering.polars import lower_polars

_EXACT_IN_F64 = 2**53


def _answer(series: pl.Series, method: str) -> pl.Series:
    """Return the column ``method`` writes over a one-column frame."""
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    frame.answer = getattr(frame.value, method)()
    return frame.collect()["answer"]


# --- to_text ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        (pl.Series([10123, -7]), ["10123", "-7"]),
        (pl.Series([0.1, 1e21]), ["0.1", "1e+21"]),
        (pl.Series([True, False]), ["true", "false"]),
        (pl.Series([datetime.date(2025, 1, 31)]), ["2025-01-31"]),
        (pl.Series(["term", ""]), ["term", ""]),
        (pl.Series(["term"], dtype=pl.Categorical), ["term"]),
    ],
    ids=["integer", "float", "bool", "date", "text", "category"],
)
def test_to_text_writes_the_value_and_not_a_rendering_of_it(
    series: pl.Series, expected: list[str]
) -> None:
    """Each accepted type answers the value itself, written out."""
    answer = _answer(series, "to_text")
    assert answer.dtype == pl.String
    assert answer.to_list() == expected


@pytest.mark.parametrize("width", [pl.UInt64, pl.Int128, pl.UInt128])
def test_to_text_keeps_every_digit_of_a_number_no_i64_carries(
    width: type[pl.DataType],
) -> None:
    """A value past i64: the export refuses it, and this is the door it names.

    A warehouse identifier or a ``.hash()`` column runs past 2**63, which is
    where section 10 stops having an exact numeric name for it. Text has one,
    and the digits have to survive the trip whole or the remedy is no remedy.
    """
    offending = 2**64 - 59  # a prime past 2**63, so a double would move it
    answer = _answer(pl.Series([offending], dtype=width), "to_text")
    assert answer.to_list() == [str(offending)]
    assert int(answer[0]) == offending


def test_to_text_at_the_double_boundary_reads_back_to_the_same_number() -> None:
    """The shortest decimal that reads back, not the shortest decimal."""
    values = [0.1, 1e21, 1.0 / 3.0, float(_EXACT_IN_F64)]
    answer = _answer(pl.Series(values), "to_text")
    assert [float(text) for text in answer.to_list()] == values


def test_to_text_carries_a_null_on_a_scalar_and_at_every_period() -> None:
    scalar = _answer(pl.Series([7, None]), "to_text")
    assert scalar.to_list() == ["7", None]

    listed = _answer(pl.Series([[1, None], None], dtype=pl.List(pl.Int64)), "to_text")
    assert listed.dtype == pl.List(pl.String)
    assert listed.to_list() == [["1", None], None]


def test_to_text_keeps_an_empty_list_empty_and_keeps_the_shape() -> None:
    answer = _answer(pl.Series([[], [2.5]], dtype=pl.List(pl.Float64)), "to_text")
    assert answer.dtype == pl.List(pl.String)
    assert answer.to_list() == [[], ["2.5"]]


@pytest.mark.parametrize(
    "series",
    [
        pl.Series([datetime.timedelta(days=1)]),
        pl.Series([datetime.time(1, 2)]),
        pl.Series([b"x"], dtype=pl.Binary),
        pl.Series([[1.0, 2.0]], dtype=pl.Array(pl.Float64, 2)),
    ],
    ids=["duration", "time", "binary", "array"],
)
def test_to_text_refuses_a_type_it_would_have_to_invent_a_form_for(
    series: pl.Series,
) -> None:
    """A text nobody can read back is not a conversion, so it is refused by name."""
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    with pytest.raises(TypeError, match="to_text has no text form for"):
        frame.answer = frame.value.to_text()


# --- to_float ---------------------------------------------------------------


def test_to_float_widens_a_whole_number_on_a_scalar_and_on_a_list() -> None:
    scalar = _answer(pl.Series([12, 30]), "to_float")
    assert scalar.dtype == pl.Float64
    assert scalar.to_list() == [12.0, 30.0]

    listed = _answer(pl.Series([[1, 2], [3]], dtype=pl.List(pl.Int64)), "to_float")
    assert listed.dtype == pl.List(pl.Float64)
    assert listed.to_list() == [[1.0, 2.0], [3.0]]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("as_list", [False, True])
def test_to_float_converts_exactly_at_the_boundary_and_refuses_one_past_it(
    sign: int, *, as_list: bool
) -> None:
    """2**53 is where the doubles stop being closer together than one.

    At the boundary the whole number still has a double of its own, so it
    converts and converts exactly. One step past it, two neighbouring whole
    numbers share a double -- which is how two policy identifiers become one
    -- so the invocation refuses rather than merging them.
    """
    boundary = sign * _EXACT_IN_F64
    at = pl.Series(
        [[boundary]] if as_list else [boundary],
        dtype=pl.List(pl.Int64) if as_list else pl.Int64,
    )
    answer = _answer(at, "to_float")
    assert answer.to_list() == ([[float(boundary)]] if as_list else [float(boundary)])
    assert int(answer[0][0] if as_list else answer[0]) == boundary

    past = sign * (_EXACT_IN_F64 + 1)
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "value": pl.Series(
                    [[past]] if as_list else [past],
                    dtype=pl.List(pl.Int64) if as_list else pl.Int64,
                )
            }
        )
    )
    frame.answer = frame.value.to_float()
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        frame.collect()
    message = str(raised.value)
    assert "holds a whole number outside [-2**53, 2**53]" in message
    assert "no double names exactly" not in message
    assert "af.value.to_text()" in message


@pytest.mark.parametrize("past", [2**53 + 2, 374477 * 2**40])
def test_the_refusal_states_the_range_a_double_named_past_it_is_refused_by(
    past: int,
) -> None:
    """A whole number past 2**53 that is itself a double is refused all the same.

    The rule is the interval of section 11.1.38, so the sentence states the
    interval: it said "a whole number no double names exactly", which is false
    for 2**53 + 2 and for 374477 * 2**40 -- each a double, refused because the
    doubles around it are more than one apart.
    """
    assert float(past) == past
    frame = ActuarialFrame(pl.DataFrame({"value": pl.Series([past], dtype=pl.Int64)}))
    frame.answer = frame.value.to_float()
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        frame.collect()
    message = str(raised.value)
    assert "holds a whole number outside [-2**53, 2**53]" in message
    assert "no double names exactly" not in message


def test_to_float_returns_a_double_unchanged_including_what_is_not_a_number() -> None:
    """Every floating-point width widens exactly, so nothing here is measured."""
    answer = _answer(pl.Series([0.1, math.inf]), "to_float")
    assert answer.to_list() == [0.1, math.inf]

    narrow = _answer(pl.Series([0.5], dtype=pl.Float32), "to_float")
    assert narrow.dtype == pl.Float64
    assert narrow.to_list() == [0.5]

    assert math.isnan(_answer(pl.Series([math.nan]), "to_float")[0])


def test_to_float_carries_a_null_rather_than_refusing_it() -> None:
    """Nothing about an absent value is too large for a double.

    Which is where this parts company with ``to_integer``: that conversion
    refuses a null because there is no whole number to give, and this one
    carries it because there is no loss to refuse.
    """
    scalar = _answer(pl.Series([7, None]), "to_float")
    assert scalar.to_list() == [7.0, None]

    listed = _answer(pl.Series([[1, None], None], dtype=pl.List(pl.Int64)), "to_float")
    assert listed.to_list() == [[1.0, None], None]


def test_to_float_keeps_an_empty_list_empty_and_keeps_the_shape() -> None:
    answer = _answer(pl.Series([[], [2]], dtype=pl.List(pl.Int64)), "to_float")
    assert answer.dtype == pl.List(pl.Float64)
    assert answer.to_list() == [[], [2.0]]


@pytest.mark.parametrize(
    "series",
    [
        pl.Series([True]),
        pl.Series(["1"]),
        pl.Series([datetime.date(2026, 1, 1)]),
    ],
    ids=["bool", "text", "date"],
)
def test_to_float_refuses_what_is_not_a_quantity(series: pl.Series) -> None:
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    with pytest.raises(TypeError, match="only integer or floating-point"):
        frame.answer = frame.value.to_float()


def test_to_float_reads_a_wide_width_on_its_value_like_any_other_integer() -> None:
    assert _answer(pl.Series([7], dtype=pl.UInt64), "to_float").to_list() == [7.0]

    frame = ActuarialFrame(
        pl.DataFrame({"value": pl.Series([2**63 + 5], dtype=pl.UInt64)})
    )
    frame.answer = frame.value.to_float()
    with pytest.raises(
        pl.exceptions.InvalidOperationError, match=r"outside \[-2\*\*53, 2\*\*53\]"
    ):
        frame.collect()


# --- to_list ----------------------------------------------------------------


def _converted_array(series: pl.Series) -> pl.Series:
    """Return the list ``to_list`` writes, with the array column dropped.

    Dropped because the array column cannot stay: section 10 has no name
    for a fixed width, which is the refusal that sends an author here in
    the first place.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    frame.answer = frame.value.to_list()
    return frame.drop("value").collect()["answer"]


@pytest.mark.parametrize(
    ("series", "expected", "dtype"),
    [
        (
            pl.Series([[1.5, 2.5]], dtype=pl.Array(pl.Float64, 2)),
            [[1.5, 2.5]],
            pl.List(pl.Float64),
        ),
        (
            pl.Series([[7, 8]], dtype=pl.Array(pl.Int64, 2)),
            [[7, 8]],
            pl.List(pl.Int64),
        ),
        (
            pl.Series([[True, False]], dtype=pl.Array(pl.Boolean, 2)),
            [[True, False]],
            pl.List(pl.Boolean),
        ),
        (
            pl.Series([["a", "b"]], dtype=pl.Array(pl.String, 2)),
            [["a", "b"]],
            pl.List(pl.String),
        ),
        (
            pl.Series(
                [[datetime.date(2025, 1, 31), datetime.date(2025, 2, 28)]],
                dtype=pl.Array(pl.Date, 2),
            ),
            [[datetime.date(2025, 1, 31), datetime.date(2025, 2, 28)]],
            pl.List(pl.Date),
        ),
    ],
    ids=["float", "integer", "bool", "text", "date"],
)
def test_to_list_keeps_the_elements_and_their_order(
    series: pl.Series, expected: list[list[object]], dtype: pl.DataType
) -> None:
    """The fixed width is the only thing given up, and no artifact records one."""
    answer = _converted_array(series)
    assert answer.dtype == dtype
    assert answer.to_list() == expected


def test_to_list_carries_a_null_element_and_a_null_array() -> None:
    answer = _converted_array(pl.Series([[None, 5], None], dtype=pl.Array(pl.Int64, 2)))
    assert answer.to_list() == [[None, 5], None]


def test_to_list_answers_an_empty_list_for_an_array_of_no_width() -> None:
    answer = _converted_array(pl.Series([[]], dtype=pl.Array(pl.Float64, 0)))
    assert answer.dtype == pl.List(pl.Float64)
    assert answer.to_list() == [[]]


@pytest.mark.parametrize(
    ("series", "refusal"),
    [
        (
            pl.Series([[1.0, 2.0]], dtype=pl.List(pl.Float64)),
            "to_list converts a fixed-width array",
        ),
        (pl.Series([1.0]), "to_list converts a fixed-width array"),
        (
            pl.Series(
                [[datetime.timedelta(days=1)]], dtype=pl.Array(pl.Duration("us"), 1)
            ),
            "to_list has no element name for",
        ),
    ],
    ids=["already_a_list", "a_scalar", "an_element_with_no_name"],
)
def test_to_list_refuses_what_it_would_not_convert(
    series: pl.Series, refusal: str
) -> None:
    """A node that sometimes converts and sometimes does nothing means two things."""
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    with pytest.raises(TypeError, match=refusal):
        frame.answer = frame.value.to_list()


# --- both, as the artifact records them -------------------------------------


def test_all_three_conversions_export_as_core_with_the_tree_written() -> None:
    """The node a reviewer reads is the call, at the tier the format claims."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_number": [10123],
                "units": [12],
                "charges": pl.Series([[1.5, 2.5]], dtype=pl.Array(pl.Float64, 2)),
            }
        )
    )
    frame.reference = frame.policy_number.to_text()
    frame.held = frame.units.to_float()
    frame.charge_run = frame.charges.to_list()
    frame = frame.drop("charges")
    artifact = GraphExporter(frame).export(profile="executable")
    assert validate_artifact(artifact, deep=True).ok

    nodes = {node["column"]: node for node in json.loads(artifact)["nodes"]}
    assert nodes["reference"]["tier"] == "core"
    assert nodes["held"]["tier"] == "core"
    assert nodes["reference"]["expr"] == {
        "op": "call",
        "name": "to_text",
        "args": [{"op": "col", "name": "policy_number"}],
        "attrs": {},
    }
    assert nodes["reference"]["dtype"] == "str"
    assert nodes["held"]["dtype"] == "f64"
    assert nodes["charge_run"]["tier"] == "core"
    assert nodes["charge_run"]["dtype"] == "list[f64]"


@pytest.mark.parametrize(
    ("node", "refusal"),
    [
        (Call("to_text", (), ()), "to_text carries no operands and takes exactly one"),
        (
            Call("to_text", (Col("units"),), (("format", "0.00"),)),
            "to_text does not carry the attribute 'format', which arrived here",
        ),
        (
            Call("to_float", (Col("units"), Col("units")), ()),
            "to_float carries 2 operands and takes exactly one",
        ),
        (
            Call("to_float", (Col("units"),), (("saturate", True),)),
            "to_float does not carry the attribute 'saturate', which arrived here",
        ),
        (
            Call("to_list", (), ()),
            "to_list carries no operands and takes exactly one",
        ),
        (
            Call("to_list", (Col("units"),), (("width", 2),)),
            "to_list does not carry the attribute 'width', which arrived here",
        ),
    ],
    ids=[
        "to_text_no_operand",
        "to_text_stray_attribute",
        "to_float_two_operands",
        "to_float_stray_attribute",
        "to_list_no_operand",
        "to_list_stray_attribute",
    ],
)
def test_replay_refuses_a_signature_outside_the_declared_contract(
    node: Call, refusal: str
) -> None:
    """Each rule says which half broke: the operand count, or the attribute named.

    Swap any case's node for its neighbour's and that case fails, which is
    the property that makes these four sentences worth writing separately.
    """
    frame = ActuarialFrame(pl.DataFrame({"units": [12]}))
    with pytest.raises(TypeError, match=refusal):
        lower_polars(node, LoweringContext(frame))
