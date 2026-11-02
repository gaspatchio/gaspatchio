# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A decimal held between whole-number bounds answers decimals, as 11.1.3 states.

"``clip()`` keeps the column's own type, whatever its bound is ... a decimal
value answers decimals." The engine refused ``av.clip(lower_bound=0)`` on a
per-policy decimal value, citing that same clause, while the reference
producer, the reader and this engine's own per-period form all answered
(audit S1b-F1). A whole-number bound beside a decimal value has one answer,
the bound read as its double; only a decimal bound on a whole-number value has
two, and that one stays refused by name.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from tests.conftest import answered, invocation

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import ScalarOutcome

_BOOK = pl.DataFrame(
    {
        "pid": [1, 2, 3],
        "av": [-50.0, 12.5, 300.0],
        "floor_at": [0, 0, 0],
        "units": [3, 7, 12],
        "term_m": [2, 2, 2],
    }
)


def _frame() -> ActuarialFrame:
    return ActuarialFrame(_BOOK).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )


_FORMS: dict[str, tuple[Callable[[ActuarialFrame], object], list[object]]] = {
    "a literal floor": (
        lambda af: af.av.clip(lower_bound=0),
        [0.0, 12.5, 300.0],
    ),
    "a literal floor and cap": (
        lambda af: af.av.clip(0, 200),
        [0.0, 12.5, 200.0],
    ),
    "a column floor": (
        lambda af: af.av.clip(lower_bound=af.floor_at),
        [0.0, 12.5, 300.0],
    ),
    "a literal floor, per period": (
        lambda af: (af.av + af.month * 1.0).clip(lower_bound=0),
        [[0.0, 0.0, 0.0], [12.5, 13.5, 14.5], [300.0, 301.0, 302.0]],
    ),
}


@pytest.mark.parametrize("form", list(_FORMS))
def test_a_decimal_between_whole_bounds_answers_decimals_on_both_engines(
    form: str,
) -> None:
    written, want = _FORMS[form]
    af = _frame()
    af.c = written(af)
    producer = af.collect()
    engine = af.collect(engine="jax")
    assert producer["c"].to_list() == want
    assert engine["c"].to_list() == want
    assert engine.schema["c"] == producer.schema["c"]
    assert engine.schema["c"] in (pl.Float64, pl.List(pl.Float64))


def _clip(value: dict[str, object], bound: object) -> ScalarOutcome:
    """Return what this engine does with ``clip(x, lower=bound)`` in a document."""
    one = invocation(
        {
            "op": "call",
            "name": "clip",
            "args": [{"op": "col", "name": "x"}, {"op": "lit", "value": bound}],
            "attrs": {"bounds": "lower"},
        },
        {"x": value},
        "f64" if value["dtype"] == "f64" else "i64",
    )
    return answered(one)


def test_a_document_s_decimal_value_with_a_whole_bound_is_answered() -> None:
    """The record a third party writes, not only the producer's: one answer."""
    outcome = _clip({"dtype": "f64", "values": [-50.0, 12.5]}, 0)
    assert outcome.refused_with is None, outcome.report
    assert outcome.value == 0.0


def test_a_whole_number_between_decimal_bounds_is_still_refused_by_name() -> None:
    """A document carrying a decimal bound on a whole number is refused here.

    The producer refuses the line where it is written; 11.1.3 states neither
    of its two answers.
    """
    outcome = _clip({"dtype": "i64", "values": [3, 7]}, 4.5)
    assert outcome.value is None
    assert "decimal bound on a whole-number value" in outcome.report
