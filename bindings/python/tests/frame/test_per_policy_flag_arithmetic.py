# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy flag in arithmetic: read as its 0/1 double, refused beside a flag.

``af.smoker * 100.0`` computed a Float64 and the frame's schema stated
``Unknown`` for it -- Polars widens a Boolean beside an untyped decimal only
when the frame runs -- so ``gspio calc-graph`` refused to export the model:
"Column 'a' has type Unknown, which the calculation graph has no name for".
The decimal is now held as the Float64 it was written as, which the answer
already was, so the schema states the type and the record carries it.

``af.smoker * af.rider`` failed inside Polars when the frame ran --
"`multiply` operation not supported for dtype `bool`" -- with no gaspatchio
sentence; ``-``, ``//``, ``%`` and ``**`` the same, ``+`` answered an unsigned
count the record called ``i64``, and the JAX engine answers a double. Section
11.1.25 does not admit a per-policy flag on both sides of one operation, so
each is refused at the assignment, naming the move. A per-period flag reads as
its 0/1 run first and is untouched by either rule.

Beside any number a per-policy flag reads as 0.0 or 1.0, a Float64, under all
seven operators and on either side -- as a per-period flag, a stored comparison
and the JAX engine already read one. ``af.smoker + 1`` answered an Int32 the
record called ``i64``, ``2 // af.smoker`` a null where the per-period form
answers infinity, and ``af.smoker ** 2.0`` failed inside Polars.
"""

from __future__ import annotations

import json
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_OPERATORS: dict[str, Callable[[object, object], object]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}


def _book() -> ActuarialFrame:
    """Two policies with a smoker flag, a rider flag, a count and a rate."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A", "B", "C"],
                "smoker": [True, False, None],
                "rider": [True, True, False],
                "n": [2, 3, 4],
                "x": [0.5, 0.5, 0.5],
            }
        )
    )


def _computed_dtypes(af: ActuarialFrame) -> dict[str, str]:
    """Return each computed node's exported type, by node id."""
    document = json.loads(GraphExporter(af).export(af.collect()))
    return {
        node["id"]: node["dtype"]
        for node in document["nodes"]
        if node["kind"] == "computed"
    }


# --- a decimal beside a per-policy flag -------------------------------------------

_BESIDE_A_DECIMAL: dict[str, Callable[[ActuarialFrame], object]] = {
    "smoker * 100.0": lambda af: af.smoker * 100.0,
    "100.0 * smoker": lambda af: 100.0 * af.smoker,
    "smoker + 0.5": lambda af: af.smoker + 0.5,
    "smoker - 0.5": lambda af: af.smoker - 0.5,
    "1.0 - smoker": lambda af: 1.0 - af.smoker,
    "(smoker & rider) * 100.0": lambda af: (af.smoker & af.rider) * 100.0,
}


@pytest.mark.parametrize("line", list(_BESIDE_A_DECIMAL))
def test_a_flag_beside_a_decimal_states_its_type(line: str) -> None:
    """The frame's schema says Float64 where it said Unknown."""
    af = _book()
    af.a = _BESIDE_A_DECIMAL[line](af)

    assert af.schema["a"] == pl.Float64


@pytest.mark.parametrize("line", list(_BESIDE_A_DECIMAL))
def test_a_flag_beside_a_decimal_exports(line: str) -> None:
    """The defect as found: the model exports, the column typed ``f64``."""
    af = _book()
    af.a = _BESIDE_A_DECIMAL[line](af)

    assert _computed_dtypes(af) == {"a@1": "f64"}


def test_the_answer_is_the_one_it_was() -> None:
    """Nothing the frame computes moves: the values and the type are unchanged."""
    af = _book()
    af.a = af.smoker * 100.0
    af.b = 1.0 - af.smoker
    out = af.collect()

    assert out["a"].dtype == pl.Float64
    assert out["a"].to_list() == [100.0, 0.0, None]
    assert out["b"].to_list() == [0.0, 1.0, None]


# Hand values: smoker reads 1.0, 0.0 and null; n is 2, 3, 4 and x 0.5.
_BESIDE_A_NUMBER: dict[str, tuple[Callable[[ActuarialFrame], object], list[object]]] = {
    "smoker + 1": (lambda af: af.smoker + 1, [2.0, 1.0, None]),
    "1 - smoker": (lambda af: 1 - af.smoker, [0.0, 1.0, None]),
    "smoker * n": (lambda af: af.smoker * af.n, [2.0, 0.0, None]),
    "n * smoker": (lambda af: af.n * af.smoker, [2.0, 0.0, None]),
    "n - smoker": (lambda af: af.n - af.smoker, [1.0, 3.0, None]),
    "smoker // 2": (lambda af: af.smoker // 2, [0.0, 0.0, None]),
    "2 // smoker": (lambda af: 2 // af.smoker, [2.0, float("inf"), None]),
    "smoker % n": (lambda af: af.smoker % af.n, [1.0, 0.0, None]),
    "smoker ** 2.0": (lambda af: af.smoker**2.0, [1.0, 0.0, None]),
    "smoker ** x": (lambda af: af.smoker**af.x, [1.0, 0.0, None]),
    "2.0 ** smoker": (lambda af: 2.0**af.smoker, [2.0, 1.0, None]),
    "n ** smoker": (lambda af: af.n**af.smoker, [2.0, 1.0, None]),
    "smoker / n": (lambda af: af.smoker / af.n, [0.5, 0.0, None]),
}


@pytest.mark.parametrize("line", list(_BESIDE_A_NUMBER))
def test_a_flag_beside_any_number_reads_as_its_double(line: str) -> None:
    """Every operator, either side, a whole number or a decimal: ``f64``."""
    build, by_hand = _BESIDE_A_NUMBER[line]
    af = _book()
    af.b = build(af)

    out = af.collect()["b"]
    assert out.dtype == pl.Float64
    assert out.to_list() == by_hand
    assert _computed_dtypes(af) == {"b@1": "f64"}


def test_a_per_policy_flag_beside_a_per_period_count_reads_as_its_double() -> None:
    af = ActuarialFrame(pl.DataFrame({"s": [True, False], "n": [[2, 3], [4, 5]]}))
    af.r = af.s * af.n
    out = af.collect()["r"]
    assert out.dtype == pl.List(pl.Float64)
    assert out.to_list() == [[2.0, 3.0], [0.0, 0.0]]


# --- a flag beside a flag ----------------------------------------------------------


@pytest.mark.parametrize("symbol", list(_OPERATORS))
def test_two_per_policy_flags_in_one_operation_are_refused_at_the_line(
    symbol: str,
) -> None:
    """Every operator, at the assignment rather than in Polars at the collect."""
    af = _book()
    with pytest.raises(TypeError) as refused:
        af.r = _OPERATORS[symbol](af.smoker, af.rider)
    said = str(refused.value)
    assert f"af.smoker {symbol} af.rider: both operands are flags" in said
    assert "section 11.1.25" in said
    assert f"when(af.smoker).then(1.0).otherwise(0.0) {symbol} af.rider" in said


def test_flag_times_flag_names_and() -> None:
    """The defect as found: ``*`` of two flags most often means both."""
    af = _book()
    with pytest.raises(
        TypeError, match=r"If the line means both, write af\.smoker & af\.rider"
    ):
        af.r = af.smoker * af.rider


def test_flag_plus_flag_names_or() -> None:
    af = _book()
    with pytest.raises(
        TypeError, match=r"If the line means either, write af\.smoker \| af\.rider"
    ):
        af.r = af.smoker + af.rider


@pytest.mark.parametrize(
    "build",
    [
        lambda af: af.smoker * True,
        lambda af: (af.smoker & af.rider) * af.rider,
        lambda af: af.smoker.is_null() * af.rider,
    ],
    ids=["literal", "logical", "call"],
)
def test_a_flag_however_written_is_a_flag(
    build: Callable[[ActuarialFrame], object],
) -> None:
    """A literal, a logical expression and a call answering a flag count too."""
    af = _book()
    with pytest.raises(TypeError, match="both operands are flags"):
        af.r = build(af)


def test_the_conversion_the_refusal_names_runs() -> None:
    """What the refusal hands over is a line that answers."""
    af = _book()
    af.r = when(af.smoker).then(1.0).otherwise(0.0) * af.rider
    af.both = af.smoker & af.rider

    out = af.collect()
    assert out["r"].to_list() == [1.0, 0.0, 0.0]
    assert out["both"].to_list() == [True, False, False]


def test_a_per_period_flag_beside_a_flag_still_reads_as_its_run() -> None:
    """Per period, a flag is read as its 0/1 run first, and both rules pass it by."""
    af = ActuarialFrame(
        pl.DataFrame(
            {"flag": [[True, False, None]], "g": [[True, True, False]], "s": [True]}
        )
    )
    af.r = af.flag * af.g
    af.q = af.flag * af.s

    out = af.collect()
    assert out["r"].to_list() == [[1.0, 0.0, None]]
    assert out["q"].to_list() == [[1.0, 0.0, None]]
