# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``fill_nan`` runs on this engine, and gives Polars' own doubles.

Section 11.1.13's NaN fill is ``where(isnan(value), fill, value)`` one cell at a
time, so there is no arithmetic for the two engines to round differently: the
answer is the value or the fill, moved and never computed. That is what lets
the comparison below be to the bit rather than to the agreement rule. A table
read cleaned on one line -- ``lookup(...).fill_nan(0.0)``, the line that had to
be two before the operation was declared -- reads as portable here and runs.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from tests.test_lowerings_projection import _call, _column, answered, refused

NAN = math.nan

# Two policies of three and two periods, with a NaN in each and a per-policy
# and a per-period fill beside them.
_BOOK = pl.DataFrame(
    {
        "q": [[0.25, NAN, 0.75], [NAN, 0.5]],
        "s": [NAN, 1.5],
        "i": [1, -2],
        "by": [9.0, 8.0],
        "by_period": [[1.0, 2.0, 3.0], [4.0, 5.0]],
    }
)


def _bits(rows: list[Any]) -> list[Any]:
    """Return every double as its exact bits, so equality is to the bit."""
    if isinstance(rows, list):
        return [_bits(row) for row in rows]
    return float(rows).hex()


def _model() -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    af.periods_value = af.q.fill_nan(0.0)
    af.periods_policy_fill = af.q.fill_nan(af.by)
    af.periods_period_fill = af.q.fill_nan(af.by_period)
    af.periods_expression_fill = af.q.fill_nan(af.by * 2.0)
    af.policy_value = af.s.fill_nan(0.0)
    af.policy_column = af.s.fill_nan(af.by)
    af.whole_decimal_fill = af.i.fill_nan(0.0)
    af.whole_whole_fill = af.i.fill_nan(0)
    return af


_FILLED = (
    "periods_value",
    "periods_policy_fill",
    "periods_period_fill",
    "periods_expression_fill",
    "policy_value",
    "policy_column",
    "whole_decimal_fill",
    "whole_whole_fill",
)


def test_every_fill_is_polars_own_answer_to_the_bit() -> None:
    on_polars = _model().collect()
    on_jax = _model().collect(engine="jax")
    for column in _FILLED:
        assert on_jax[column].dtype == on_polars[column].dtype, column
        assert _bits(on_jax[column].to_list()) == _bits(on_polars[column].to_list()), (
            column
        )


def test_a_nan_is_filled_and_an_infinity_kept() -> None:
    answers = answered(
        _call("fill_nan", [_column("x"), {"op": "lit", "value": 0.0}]),
        {"x": {"dtype": "f64", "values": [1.5, NAN, math.inf, -math.inf]}},
        "f64",
    )
    assert answers == [1.5, 0.0, math.inf, -math.inf]


def test_a_whole_number_holds_no_nan_and_keeps_its_type_under_a_whole_fill() -> None:
    answers = answered(
        _call("fill_nan", [_column("x"), {"op": "lit", "value": 0}]),
        {"x": {"dtype": "i64", "values": [1, -2, 3]}},
        "i64",
    )
    assert answers == [1, -2, 3]


@pytest.mark.parametrize(
    ("dtype", "values"),
    [("bool", [True, False]), ("date", ["2025-01-31", "2025-02-28"])],
    ids=["boolean", "date"],
)
def test_a_value_that_cannot_hold_a_nan_is_refused(dtype: str, values: list) -> None:
    """11.1.13 states no answer past the numbers; this engine refuses by name."""
    report = refused(
        _call("fill_nan", [_column("x"), {"op": "lit", "value": 0.0}]),
        {"x": {"dtype": dtype, "values": values}},
        "f64",
    )
    assert "fill_nan" in report
    assert "11.1.13" in report


def test_a_lookup_cleaned_on_one_line_reads_as_portable_and_runs() -> None:
    table = Table(
        name="lapse",
        source=pl.DataFrame({"duration": [1, 2, 3], "rate": [0.08, NAN, 0.04]}),
        dimensions={"duration": "duration"},
        value="rate",
        on_missing="nan",
    )
    af = ActuarialFrame(pl.DataFrame({"duration": [1, 2, 3]}))
    af.lapse_rate = table.lookup(duration=af.duration).fill_nan(0.0)
    document = GraphExporter(af).export(profile="executable")
    report = validate_artifact(document, engine="jax", deep=True)
    assert report.ok, report.findings
    assert af.collect(engine="jax")["lapse_rate"].to_list() == [0.08, 0.0, 0.04]
