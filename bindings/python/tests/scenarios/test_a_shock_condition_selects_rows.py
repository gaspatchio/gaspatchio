# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A conditional shock whose condition selects no row of its table is refused.

``FilteredShock(where=...)`` and ``TimeConditionalShock(when=...)`` read their
condition against the rows of the table they move. The docstring's own mass
lapse, ``when={"t": {"eq": 0}}``, over a lapse table keyed by policy year
1..5 selected nothing: the scenario ran, equalled BASE to the bit and said
nothing, while the neighbouring case (a shock on a table no read reached) is
refused because "the scenario would equal BASE". A condition that selects
nothing is refused the same way, naming what the table holds. A condition on
a column the table does not hold is refused by name too, not in Polars'
``ColumnNotFoundError``.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MultiplicativeShock,
    PipelineShock,
    ScenarioRun,
    Sum,
    TimeConditionalShock,
)

W = [0.12, 0.09, 0.07, 0.05, 0.04]  # lapse by policy year 1..5
Q = {"M": 0.010, "F": 0.006}


def _model(af: ActuarialFrame) -> ActuarialFrame:
    lapse = Table(
        name="sel_lapse",
        source=pl.DataFrame({"t": [1, 2, 3, 4, 5], "w": W}),
        dimensions={"t": "t"},
        value="w",
    )
    mort = Table(
        name="sel_mort",
        source=pl.DataFrame({"sex": ["M", "F"], "q": [Q["M"], Q["F"]]}),
        dimensions={"sex": "sex"},
        value="q",
    )
    af = af.projection.set(
        valuation_date=dt.date(2025, 6, 30),
        until="term_years",
        until_value=4,
        frequency="annual",
    )
    af.yr = af.month // 12 + 1
    af.w = lapse.lookup(t=af.yr)
    af.q = mort.lookup(sex=af.sex)
    af.dec = 1.0 - (1.0 - af.q) * (1.0 - af.w)
    af.inf = af.dec.projection.cumulative_survival()
    af.cf = af.prem * af.inf
    af.pv = af.cf.list.sum()
    return af


BOOK = pl.DataFrame({"pid": [1, 2], "sex": ["M", "F"], "prem": [1000.0, 500.0]})


def _run(shock: object, batch_size: int | None) -> dict[str, float]:
    plan = ScenarioRun(
        shocks={"BASE": [], "S": [shock]},
        aggregations=(Sum("pv").alias("pv").over("scenario_id"),),
    )
    kwargs = {} if batch_size is None else {"batch_size": batch_size}
    result = plan.run(ActuarialFrame(BOOK), _model, **kwargs)
    return dict(result.aggregations["pv"].iter_rows())


def _hand(
    year_add: tuple[int, Fraction] | None = None, f_mult: Fraction = Fraction(1)
) -> float:
    """Five boundaries, in-force at the beginning of each period, Fractions only."""
    total = Fraction(0)
    for sex, prem in (("M", Fraction(1000)), ("F", Fraction(500))):
        inforce = Fraction(1)
        for k in range(5):
            total += prem * inforce
            if k == 4:
                break
            w = Fraction(str(W[k]))
            if year_add is not None and year_add[0] == k + 1:
                w += year_add[1]
            q = Fraction(str(Q[sex])) * (f_mult if sex == "F" else 1)
            inforce *= (1 - q) * (1 - w)
    return float(total)


@pytest.mark.parametrize("batch_size", [1, None])
def test_the_docstring_mass_lapse_on_a_one_based_table_is_refused(
    batch_size: int | None,
) -> None:
    shock = TimeConditionalShock(
        AdditiveShock(0.30), when={"t": {"eq": 0}}, table="sel_lapse"
    )
    with pytest.raises(ValueError, match=r"would equal BASE") as caught:
        _run(shock, batch_size)
    said = str(caught.value)
    assert "Scenario 'S'" in said
    assert "'t' holds 1 to 5" in said
    assert "when={'t': {'eq': 0}}" in said


@pytest.mark.parametrize(
    ("where", "held"),
    [
        ({"sex": "f"}, "'sex' holds 'F', 'M'"),
        ({"sex": {"in": ["x", "y"]}}, "'sex' holds 'F', 'M'"),
    ],
)
def test_a_label_no_row_holds_is_refused_naming_the_labels(
    where: dict[str, object], held: str
) -> None:
    shock = FilteredShock(MultiplicativeShock(1.5), where=where, table="sel_mort")
    with pytest.raises(ValueError, match=r"no row of 'sel_mort' meets") as caught:
        _run(shock, 1)
    assert held in str(caught.value)


@pytest.mark.parametrize(
    "where",
    [{"t": {"gt": 9}}, {"t": {"between": [7, 6]}}, {"t": 2.5}],
)
def test_a_range_outside_the_keys_is_refused(where: dict[str, object]) -> None:
    shock = FilteredShock(MultiplicativeShock(2.0), where=where, table="sel_lapse")
    with pytest.raises(ValueError, match=r"would equal BASE"):
        _run(shock, None)


def test_a_condition_nested_in_a_pipeline_is_checked() -> None:
    inner = FilteredShock(MultiplicativeShock(2.0), where={"t": {"gt": 9}})
    shock = PipelineShock(shocks=(inner, ClipShock(max_value=1.0)), table="sel_lapse")
    with pytest.raises(ValueError, match=r"would equal BASE"):
        _run(shock, 1)


def test_conditions_that_select_rows_answer_the_hand_values() -> None:
    lapse = TimeConditionalShock(
        AdditiveShock(0.30), when={"t": {"eq": 1}}, table="sel_lapse"
    )
    assert _run(lapse, 1)["S"] == pytest.approx(_hand((1, Fraction(3, 10))), rel=1e-12)
    female = FilteredShock(
        MultiplicativeShock(1.5), where={"sex": "F"}, table="sel_mort"
    )
    got = _run(female, None)
    assert got["S"] == pytest.approx(_hand(f_mult=Fraction(3, 2)), rel=1e-12)
    assert got["BASE"] == pytest.approx(_hand(), rel=1e-12)


def test_a_cap_that_binds_nowhere_still_runs() -> None:
    """Values unchanged is a real scenario; only an empty selection is refused."""
    shock = FilteredShock(
        ClipShock(max_value=0.5), where={"t": {"lte": 2}}, table="sel_lapse"
    )
    got = _run(shock, 1)
    assert got["S"] == got["BASE"]


def test_table_with_shock_refuses_an_empty_selection() -> None:
    table = Table(
        name="sel_ws",
        source=pl.DataFrame({"age": [30, 31], "q": [0.01, 0.02]}),
        dimensions={"age": "age"},
        value="q",
    )
    with pytest.raises(ValueError, match=r"'age' holds 30 to 31"):
        table.with_shock(
            FilteredShock(MultiplicativeShock(2.0), where={"age": {"gte": 200}})
        )
    moved = table.with_shock(FilteredShock(MultiplicativeShock(2.0), where={"age": 31}))
    assert moved.to_dataframe().sort("age")["q"].to_list() == [0.01, 0.04]


@pytest.mark.parametrize("batch_size", [1, None])
@pytest.mark.parametrize(
    ("shock", "column", "time_hint"),
    [
        (
            TimeConditionalShock(
                AdditiveShock(0.40), when={"yr": {"eq": 1}}, table="sel_lapse"
            ),
            "yr",
            True,
        ),
        (
            FilteredShock(
                MultiplicativeShock(1.2), where={"age": {"gte": 2}}, table="sel_mort"
            ),
            "age",
            False,
        ),
    ],
)
def test_a_condition_on_a_column_the_table_lacks_is_refused_by_name(
    shock: object, column: str, *, time_hint: bool, batch_size: int | None
) -> None:
    """Not Polars' ColumnNotFoundError: the column, the table's columns, the move."""
    with pytest.raises(ValueError, match=rf"has no column '{column}'") as caught:
        _run(shock, batch_size)
    said = str(caught.value)
    assert "holds: " in said
    assert "Write the condition on a column" in said
    assert ("not the model's projection time" in said) is time_hint


def test_table_with_shock_refuses_a_condition_on_a_missing_column() -> None:
    table = Table(
        name="sel_ws_missing",
        source=pl.DataFrame({"duration": [1, 2], "rate": [0.1, 0.2]}),
        dimensions={"duration": "duration"},
        value="rate",
    )
    shock = FilteredShock(MultiplicativeShock(2.0), where={"durationn": 1})
    with pytest.raises(ValueError, match=r"Did you mean 'duration'\?"):
        table.with_shock(shock)
