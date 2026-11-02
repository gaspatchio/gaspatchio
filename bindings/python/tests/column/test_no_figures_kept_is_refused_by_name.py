# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round_sig_figs`` below one figure is refused by name.

``round_sig_figs`` keeps the leading figures, at least one:
``round_sig_figs(0)`` on a decimal failed in Polars' words, and on a whole
number answered 5 as 10. It is refused where it is written, and the reader
refuses the record.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -1.0]})


@pytest.mark.parametrize("digits", [0, -1])
@pytest.mark.parametrize("column", ["x", "k"])
def test_no_figures_kept_is_refused_by_name(column: str, digits: int) -> None:
    af = ActuarialFrame(_BOOK)

    with pytest.raises(TypeError, match="a whole number of at least one"):
        af[column].round_sig_figs(digits)


def test_one_figure_kept_answers() -> None:
    af = ActuarialFrame(_BOOK)
    af.d = af.x.round_sig_figs(1)
    af.w = af.k.round_sig_figs(1)

    out = af.collect()

    assert out["d"].to_list() == [3.0, -1.0]
    assert out["w"].to_list() == [5, 1]


def _reader() -> tuple[type, type, type]:
    sys.path.insert(0, str(_CONFORMANCE))
    try:
        from reader.shared import Column, DomainRefusal
        from reference import Reader
    finally:
        sys.path.remove(str(_CONFORMANCE))
    return Reader, Column, DomainRefusal


@pytest.mark.parametrize(
    ("tree", "refusal"),
    [
        (
            {
                "op": "call",
                "name": "round_sig_figs",
                "args": [{"op": "col", "name": "x"}],
                "attrs": {"digits": 0},
            },
            "significant-figures-digits",
        ),
        (
            {
                "op": "call",
                "name": "round_sig_figs",
                "args": [{"op": "col", "name": "k"}],
                "attrs": {"digits": 0},
            },
            "significant-figures-digits",
        ),
    ],
)
def test_the_reference_reader_refuses_the_record(tree: dict, refusal: str) -> None:
    reader, column, domain_refusal = _reader()
    tree = {"attrs": {}, **tree}
    book = {
        "x": column("f64", [2.5, -1.0]),
        "k": column("i64", [5, 1]),
    }

    with pytest.raises(domain_refusal, match=refusal):
        reader(book, [], {}).evaluate(tree)
