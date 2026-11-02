# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader reads a flag under the calls that read a number as its 0 or 1.

Sections 11.1.8 and 11.1.12 read a Boolean operand as the 0.0/1.0 section
11.1.25 reads it as, and answer ``f64``. The reader typed six of the answers
``bool`` (``sqrt``, ``exp``, ``floor``, ...), answered ``round`` of a false
flag as ``False``, refused ``abs``, and raised Python's ``math domain error``
for the logarithm of 0.0, which every engine answers as minus infinity. The
records the producer writes for these lines now read alike on both sides.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
_HAND: dict[str, tuple[float, float]] = {
    "abs": (1.0, 0.0),
    "sign": (1.0, 0.0),
    "sqrt": (1.0, 0.0),
    "cbrt": (1.0, 0.0),
    "exp": (math.e, 1.0),
    "log": (0.0, -math.inf),
    "log10": (0.0, -math.inf),
    "log1p": (math.log(2.0), 0.0),
    "norm_cdf": (0.5 * math.erfc(-1.0 / math.sqrt(2.0)), 0.5),
    "round_sig_figs": (1.0, 0.0),
    "round": (1.0, 0.0),
    "floor": (1.0, 0.0),
    "ceil": (1.0, 0.0),
}
_ARGUMENTS: dict[str, tuple[int, ...]] = {"round_sig_figs": (2,), "round": (0,)}
_BOOK = pl.DataFrame(
    {"k": [5, 1, None], "x": [2.5, -1.0, 1.0], "b": [True, False, None]}
)
_FLAGS = {
    "a stored flag": lambda af: af.b,
    "a comparison": lambda af: af.k > 2,
    "a mask": lambda af: (af.k > 2) & (af.x > 0),
}


def _hand(name: str, truth: object) -> object:
    if isinstance(truth, list):
        return [_hand(name, cell) for cell in truth]
    if truth is None:
        return None
    one, nought = _HAND[name]
    return one if truth else nought


def _reader() -> tuple[type, type]:
    sys.path.insert(0, str(_CONFORMANCE))
    try:
        from reader.shared import Column
        from reference import Reader
    finally:
        sys.path.remove(str(_CONFORMANCE))
    return Reader, Column


@pytest.mark.parametrize("flag", ["a stored flag", "a comparison", "a mask"])
@pytest.mark.parametrize("name", sorted(_HAND))
def test_the_record_is_a_double_and_the_reader_answers_it_alike(
    name: str, flag: str
) -> None:
    make, truth = _FLAGS[flag], [True, False, None]
    af = ActuarialFrame(_BOOK)
    af.r = getattr(make(af), name)(*_ARGUMENTS.get(name, ()))
    document = json.loads(GraphExporter(af).export(profile="executable"))
    node = next(n for n in document["nodes"] if n.get("column") == "r")
    reader, column = _reader()
    book = {
        "k": column("i64", [5, 1, None]),
        "x": column("f64", [2.5, -1.0, 1.0]),
        "b": column("bool", [True, False, None]),
    }

    answer = reader(book, [], {}).evaluate(node["expr"])

    assert node["dtype"] == "f64"
    assert answer.dtype == "f64"
    assert answer.values == _hand(name, truth) == af.collect()["r"].to_list()


@pytest.mark.parametrize("name", sorted(_HAND))
def test_the_reader_answers_a_run_of_flags_as_doubles(name: str) -> None:
    reader, column = _reader()
    runs = [[False, True, None], [True, False, False], None]
    tree = {
        "op": "call",
        "name": name,
        "args": [{"op": "col", "name": "runs"}],
        "attrs": {"digits": 2}
        if name == "round_sig_figs"
        else {"decimals": 0, "mode": "half_to_even"}
        if name == "round"
        else {},
    }

    answer = reader({"runs": column("list[bool]", runs)}, [], {}).evaluate(tree)

    assert answer.dtype == "list[f64]"
    assert answer.values == [_hand(name, runs[0]), _hand(name, runs[1]), None]


@pytest.mark.parametrize("name", ["log", "log10"])
def test_the_reader_answers_minus_infinity_for_the_logarithm_of_nought(
    name: str,
) -> None:
    reader, column = _reader()
    tree = {
        "op": "call",
        "name": name,
        "args": [{"op": "col", "name": "x"}],
        "attrs": {},
    }

    answer = reader({"x": column("f64", [0.0, -0.0, 1.0])}, [], {}).evaluate(tree)

    assert answer.values == [-math.inf, -math.inf, 0.0]
