# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What each operation says about itself, and the census that keeps it honest.

A substitution shows a line's arithmetic. For ``a * b - c`` that is the
whole meaning; for ``.cumulative_survival()`` it is a number, a method name
and nothing in between. So a walk-through of a named operation carries one
sentence saying what that operation did, filled in from the node's own
configuration and the run in front of the reader.

The claim held here is that **every sentence is pinned against a model that
ran**, so the words a reader meets are the words this framework produces
over real values, not a string somebody hoped was reachable.

That every identifier the format owns is answered -- it has a sentence, or
it is named as one whose substituted arithmetic already is its meaning --
is no longer a separate check. Both tables are comprehensions over the one
row per operation, and ``test_vocabulary.py`` holds each to its own column:
``test_the_sentence_table_is_the_row_s_voice_column`` and
``test_the_operators_are_the_rows_that_carry_no_sentence`` are the two
halves of that partition, so an operation cannot be added and left
voiceless and cannot be answered twice. Which fifteen operators the second
half comes out as is still said once, below.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, walk
from gaspatchio.curves import Curve
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.trace_voice import (
    SENTENCES,
    SPOKEN_BY_SUBSTITUTION,
    sentence_for,
)
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Iterator

# A content identity is a fact about the fixture beside it rather than
# about the sentence, and it is pinned where it belongs -- in the identity
# tests. Held to its shape here so that a sentence naming a base, a curve,
# a schedule or a compilation is checked for naming one, without this file
# becoming a second place a fixture change has to be typed into.
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_STOOD_FOR = "sha256:<digest>"


def _voice_of(frame: ActuarialFrame) -> Iterator[tuple[str, str]]:
    """Yield the identifier and the sentence of every call one model makes."""
    for tree in fold(frame).op_trees.values():
        for node in walk(tree):
            if isinstance(node, Call):
                spoken = sentence_for(node, None)
                if spoken is not None:
                    yield node.name, _DIGEST.sub(_STOOD_FOR, spoken)


def _a_model_of_ordinary_per_policy_lines() -> ActuarialFrame:
    """Return a model writing the lines an actuary writes about one policy.

    Rounding, banding, membership, the plain maths, the tests of a value
    that is not there, a parse out of an administration extract, and the
    Excel functions a spreadsheet conversion arrives carrying. Nothing here
    has a projection: these are all one value per policy, which is where
    most of a model's setup lives.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "age": [45.0, 55.0],
                "code": ["A", "B"],
                "premium": [1234.567, 2345.678],
                "rate": [0.05, 0.04],
                "entry": ["2020/01/15", "2021/06/30"],
                "serial": [44000, 45000],
                "start": [datetime.date(2020, 1, 15), datetime.date(2021, 6, 30)],
                "end": [datetime.date(2025, 1, 15), datetime.date(2026, 6, 30)],
                "nper": [10, 12],
                "pmt": [-100.0, -200.0],
            }
        )
    )
    frame.years_up = frame.age.ceil()
    frame.years_down = frame.age.floor()
    frame.billed = frame.premium.round(2)
    frame.capped = frame.age.clip(40.0, 50.0)
    frame.member = frame.code.is_in(["A"])
    frame.mapped = frame.code.replace(["A", "B"], ["TERM", "WL"])
    frame.parsed = frame.entry.str.to_date("%Y/%m/%d")
    frame.rounded_excel = frame.premium.excel.round(2)
    frame.monthly = frame.rate.finance.to_monthly()
    frame.year_fraction = frame.start.excel.yearfrac(frame.end)
    frame.from_serial = frame.serial.excel.from_excel_serial()
    frame.days_between = frame.end.excel.days(frame.start)
    frame.moved = frame.start.excel.edate(3)
    frame.month_end = frame.start.excel.eomonth(3)
    frame.annuity = frame.rate.excel.pv(frame.nper, frame.pmt)
    frame.snapped = frame.start.date.to_period("M")
    frame.months_run = frame.start.date.months_between(frame.end)
    frame.not_old = ~(frame.age > 50.0)
    frame.exposure = frame.rate.abs()
    frame.direction = frame.rate.sign()
    frame.headline = frame.premium.round_sig_figs(3)
    frame.root = frame.age.sqrt()
    frame.cube_root = frame.age.cbrt()
    frame.grown = frame.rate.exp()
    frame.force = frame.age.log()
    frame.decades = frame.age.log10()
    frame.force_of_rate = frame.rate.log1p()
    frame.rate_quantile = frame.rate.norm_cdf()
    frame.rate_given = frame.rate.fill_null(0.0)
    frame.rate_named = frame.rate.fill_nan(0.0)
    frame.rate_present = frame.rate.is_not_null()
    frame.rate_missing = frame.rate.is_null()
    frame.rate_nameable = frame.rate.is_not_nan()
    frame.rate_unnameable = frame.rate.is_nan()
    frame.rate_finite = frame.rate.is_finite()
    frame.rate_unbounded = frame.rate.is_infinite()
    frame.whole_age = frame.age.to_integer()
    frame.age_written = frame.age.to_text()
    frame.age_widened = frame.age.to_float()
    return frame


def _a_model_reading_a_fixed_width_array() -> ActuarialFrame:
    """Return a model unpinning an array a parquet file arrived carrying.

    Its own model because the array column cannot stay on an exported
    frame: section 10 has no name for a fixed width, which is the refusal
    that names this operation. So the model converts and drops the column
    it converted, which is what an author following that refusal does.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "quarterly_charges": pl.Series(
                    [[1.5, 2.5], [3.5, 4.5]], dtype=pl.Array(pl.Float64, 2)
                ),
            }
        )
    )
    frame.charge_run = frame.quarterly_charges.to_list()
    return frame.drop("quarterly_charges")


def _a_projection_reading_its_own_periods() -> ActuarialFrame:
    """Return a projection writing the closed forms the framework prefers.

    A timeline, a rate broadcast onto it, the two accumulations along the
    period axis, the three time shifts, and the two prospective folds --
    the shape of a cashflow projection with no state machine in it.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "rate": [0.05, 0.04],
                "av0": [1000.0, 2000.0],
            }
        )
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.period_dates = frame.projection.period_dates()
    frame.t_years = frame.projection.t_years()
    frame.year_fracs = frame.projection.year_fractions()
    frame.anniversary = frame.projection.anniversary_mask()
    frame.in_force = frame.projection.is_in_force()
    frame.after_boundary = frame.projection.contract_boundary()
    frame.rate_mth = frame.rate.projection.broadcast_to_periods()
    frame.growth = frame.rate_mth + 1.0
    frame.cumulative_growth = frame.growth.cum_prod()
    frame.premium_to_date = frame.rate_mth.cum_sum()
    frame.total_premium = frame.rate_mth.list.sum()
    frame.average_rate = frame.rate_mth.list.mean()
    frame.lowest_rate = frame.rate_mth.list.min()
    frame.highest_rate = frame.rate_mth.list.max()
    frame.opening_rate = frame.rate_mth.list.get(0)
    frame.rate_last_first = frame.rate_mth.list.reverse()
    frame.growth_prev = frame.cumulative_growth.projection.previous_period()
    frame.growth_next = frame.cumulative_growth.projection.next_period()
    frame.growth_two_back = frame.cumulative_growth.projection.at_period(-2)
    frame.still_to_come = frame.rate_mth.projection.remaining_sum()
    frame.prospective = frame.rate_mth.projection.prospective_value(discount_rate=0.05)
    frame.opened_at_zero = frame.rate_mth.projection.with_period(0, 0.0)
    frame.account = frame.growth.projection.accumulate(
        initial=frame.av0, multiplier=frame.growth, addend=frame.rate_mth
    )
    return frame


def _a_model_reading_a_curve_and_discounting() -> ActuarialFrame:
    """Return a model reading a yield curve and discounting cashflows."""
    curve = Curve.from_zero_rates(tenors=[1.0, 2.0, 3.0], rates=[0.02, 0.025, 0.03])
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "t": [1.0, 2.0],
                "age": [45.0, 55.0],
                "month": [12, 24],
                "cashflow": [100.0, 200.0],
                "rate": [0.05, 0.04],
                "period": [1, 2],
                "fv": [1050.0, 2080.0],
                "n": [1, 2],
            }
        )
    )
    frame.spot = curve.spot_rate(frame["t"])
    frame.discount = curve.discount_factor(frame["t"])
    frame.is_youngest_band = frame.age.cut([40.0, 50.0]) == "(-inf, 40]"
    frame.inflation = frame.month.finance.compound(rate=0.01, periods_per_year=12)
    frame.discounted = frame.fv.finance.discount(frame.rate, frame.n)
    frame.present = frame.finance.present_value("cashflow", "rate", "period")
    return frame


def _a_model_on_a_schedule_of_its_own() -> ActuarialFrame:
    """Return a model whose timeline is a schedule object rather than kwargs."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "inception": [
                    datetime.date(2024, 1, 31),
                    datetime.date(2024, 6, 30),
                ],
                "cash": [[-100.0, 50.0, 80.0], [-200.0, 120.0, 130.0]],
            }
        )
    )
    frame.internal_rate = frame.cash.excel.irr()
    frame = frame.date.add_duration("inception", "1mo", new_col_name="a_month_on")
    return frame.projection.set(
        schedule=Schedule.from_inception(
            inception_column="inception", n_periods=6, frequency="1M"
        )
    )


def _a_model_reading_a_schedule_object_directly() -> ActuarialFrame:
    """Return a model taking each reading off the schedule object itself."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "inception": [
                    datetime.date(2024, 1, 31),
                    datetime.date(2024, 6, 30),
                ],
                "term": [6, 4],
            }
        )
    )
    jagged = Schedule.from_per_policy_grid(
        start_date=datetime.date(2024, 1, 31),
        frequency="1M",
        until_kind="term_months",
        until_value_column="term",
    )
    shared = Schedule.from_inception(
        inception_column="inception", n_periods=6, frequency="1M"
    )
    frame.own_dates = jagged.per_policy_period_dates_expr()
    frame.own_count = jagged.per_policy_period_count_expr()
    frame.dates = shared.period_dates_expr()
    frame.year_fracs = shared.year_fractions_expr()
    frame.anniversary = shared.anniversary_mask_expr()
    return frame


def _a_model_exploding_a_date_range() -> ActuarialFrame:
    """Return a model turning a start and an end into a run of dates."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "inception": [
                    datetime.date(2024, 1, 31),
                    datetime.date(2024, 3, 31),
                ],
                "expiry": [datetime.date(2024, 4, 30), datetime.date(2024, 6, 30)],
            }
        )
    )
    return frame.date.create_timeline(
        "inception", "expiry", freq="1mo", new_col_name="timeline"
    )


def _a_compiled_rollforward_read_three_ways() -> ActuarialFrame:
    """Return the state machine, one state, one increment and the whole struct."""
    periods = 6
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "fund_return": [[0.01] * periods],
            "me_charge": [[0.001] * periods],
        }
    )
    frame = frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=periods,
        frequency="monthly",
    )
    builder = frame.projection.rollforward(
        states={"av": frame["av_init"]}, track_increments=True
    )
    (
        builder["av"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
    )
    compiled = compile_rollforward(builder)
    frame.av = compiled.expr_for("av")
    frame.growth_increment = compiled.increment_for("fund_return")
    frame.whole_machine = compiled.plugin_expr()
    return frame


def _a_model_that_looks_a_rate_up() -> ActuarialFrame:
    """Return a model reading a mortality rate out of an assumption base."""
    from gaspatchio.assumptions import Table

    base = Table(
        name="mortality",
        source=pl.DataFrame({"age": [45, 55], "rate": [0.001_23, 0.004_56]}),
        dimensions={"age": "age"},
        value="rate",
    )
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "age": [45, 55]}))
    frame.mortality_rate = base.lookup(age=frame.age)
    return frame


def _a_model_on_a_select_and_ultimate_basis() -> ActuarialFrame:
    """Return a model reading a rate under the convention its basis holds.

    The select and ultimate structure of the three, because it is the one
    that clamps: a duration past the select period reads the select
    period's own row, and that is a fact about the basis rather than about
    the line, which is why the sentence has to say it.
    """
    from gaspatchio.assumptions import Table
    from gaspatchio.mortality import MortalityTable

    base = Table(
        name="cso_2017_male_select",
        source=pl.DataFrame(
            {
                "age": [45, 45, 55, 55],
                "duration": [1, 2, 1, 2],
                "rate": [0.001_23, 0.001_44, 0.004_56, 0.005_01],
            }
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
    )
    basis = MortalityTable(
        table=base,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=2,
    )
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "age": [45, 55], "duration": [1, 7]})
    )
    frame.mortality_rate = basis.at(age=frame.age, duration=frame.duration)
    return frame


def _a_model_joining_a_second_table() -> ActuarialFrame:
    """Return a model whose column arrived from the right side of a join."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "product_id": ["TERM", "WL"]})
    )
    return frame.join(
        pl.DataFrame({"product_id": ["TERM", "WL"], "loading": [0.05, 0.07]}),
        on="product_id",
        how="left",
    )


def _a_model_of_a_survival_curve() -> ActuarialFrame:
    """Return the closed-form survival probability every projection writes."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "decrement": [0.001, 0.002]})
    )
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.combined_decrement = frame.decrement.projection.broadcast_to_periods()
    frame.survival = frame.combined_decrement.projection.cumulative_survival()
    return frame.finance.discount_factor("combined_decrement", "month", "v_t")


# Every model above, and the operations each of them reaches. A sentence is
# only in this file if a model here produced it.
_WORKED_MODELS = (
    _a_model_of_ordinary_per_policy_lines,
    _a_projection_reading_its_own_periods,
    _a_model_reading_a_curve_and_discounting,
    _a_model_on_a_schedule_of_its_own,
    _a_model_reading_a_schedule_object_directly,
    _a_model_exploding_a_date_range,
    _a_compiled_rollforward_read_three_ways,
    _a_model_that_looks_a_rate_up,
    _a_model_on_a_select_and_ultimate_basis,
    _a_model_joining_a_second_table,
    _a_model_of_a_survival_curve,
    _a_model_reading_a_fixed_width_array,
)


def _spoken() -> dict[str, str]:
    """Return every sentence the worked models above produce, by identifier."""
    spoken: dict[str, str] = {}
    for build in _WORKED_MODELS:
        for identifier, sentence in _voice_of(build()):
            spoken.setdefault(identifier, sentence)
    return spoken


_SPOKEN: dict[str, str] = _spoken()


# --- the census -------------------------------------------------------------


def test_the_operations_that_speak_through_substitution_are_the_operators() -> None:
    """Fifteen, and they are exactly what a formula is written with."""
    assert set(SPOKEN_BY_SUBSTITUTION) == {
        "add",
        "sub",
        "mul",
        "div",
        "floordiv",
        "mod",
        "pow",
        "lt",
        "le",
        "gt",
        "ge",
        "eq",
        "ne",
        "and",
        "or",
    }


def test_an_expression_written_with_operators_gets_no_sentence() -> None:
    """The substitution is the semantics; saying it again would be noise."""
    frame = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0], "mortality_rate": [0.001]})
    )
    frame.claims = frame.sum_assured * frame.mortality_rate
    tree = fold(frame).op_trees["claims@1"]
    assert sentence_for(tree, None) is None


def test_a_node_with_no_tree_behind_it_gets_no_sentence() -> None:
    """A column the data arrived with has no operation to speak for."""
    assert sentence_for(None, None) is None


# --- every sentence, against a model that ran -------------------------------


def test_every_operation_with_a_sentence_is_reached_by_a_worked_model() -> None:
    """No sentence is written here that nothing in this file produces.

    The other half of the census. A table of sentences nobody can reach is
    a table nobody can check, and the one that goes stale first is the one
    for the operation no model writes.
    """
    assert set(_SPOKEN) == set(SENTENCES)


@pytest.mark.parametrize("identifier", sorted(SENTENCES))
def test_the_sentence_each_operation_speaks(
    identifier: str, expected_sentences: dict[str, str]
) -> None:
    """Each operation's own sentence, as one of the models above produced it."""
    assert _SPOKEN[identifier] == expected_sentences[identifier]


def test_no_sentence_leaves_a_clause_it_could_not_fill() -> None:
    """Refuse a sentence with a clause it could not fill.

    ``not recorded`` in a sentence is a template naming a field the
    operation does not carry -- a hole a reader would read as a lost value
    rather than as a mistake in the table.
    """
    unfilled = {
        identifier: sentence
        for identifier, sentence in _SPOKEN.items()
        if "not recorded" in sentence
    }
    assert unfilled == {}


# Every sentence, word for word, as one of the models above produced it.
# Pinned rather than derived: a table that generated its own expectations
# would pass whatever it happened to say, and what has to be checked here
# is that the words a reader meets are the words somebody read and meant.
_EXPECTED: dict[str, str] = {
    "abs": ("rate with its sign dropped"),
    "cbrt": ("the cube root of age"),
    "ceil": ("the smallest whole number not below age"),
    "clip": (
        "age held between its bounds -- a lower and an upper bound -- so that a value outside one becomes that bound"  # noqa: E501
    ),
    "cum_prod": (
        "a running product of growth along the projection's periods, from the start of the projection"  # noqa: E501
    ),
    "cum_sum": (
        "a running total of rate_mth along the projection's periods, from the start of the projection"  # noqa: E501
    ),
    "curve.discount_factor": (
        "each time in t discounted at its own spot rate off the sha256:<digest> curve"
    ),
    "max": ("the greatest of rate_mth across the projection's periods"),
    "mean": ("the average of rate_mth across the projection's periods"),
    "min": ("the least of rate_mth across the projection's periods"),
    "sum": ("the total of rate_mth across the projection's periods"),
    "list.get": (
        "the value in rate_mth at position 0: zero is first, "
        "negative positions count from the end"
    ),
    "list.reverse": (
        "rate_mth turned end for end within each policy's own periods, "
        "its last period first"
    ),
    "to_integer": "age checked to be whole and in signed 64-bit range",
    "to_float": (
        "age carried to floating point, exact out to the largest whole "
        "number a double names"
    ),
    "to_text": "age carried to text, every digit kept",
    "to_list": (
        "quarterly_charges carried from a fixed-width array to a list, the "
        "same elements in the same order"
    ),
    "curve.spot_rate": (
        "the spot rate the sha256:<digest> curve gives at each time in t"
    ),
    "cut": (
        "age placed in the interval the breakpoints [40.0, 50.0] divide the line into, a value on a breakpoint belonging to the interval below it"  # noqa: E501
    ),
    "date.date_ranges": (
        "one run of dates per policy from inception to expiry, one every 1mo"
    ),
    "date.months_between": (
        "whole calendar months from start to end, the day of the month playing no part"
    ),
    "date.offset_by": ("inception shifted by 1mo on the calendar"),
    "date.to_period": ("start snapped back to the start of the M period holding it"),
    "excel.days": ("whole days from start to end, Excel's DAYS"),
    "excel.edate": (
        "start moved 3 whole months, keeping the day of the month, Excel's EDATE"
    ),
    "excel.eomonth": (
        "start moved 3 whole months and then taken to that month's last day, Excel's EOMONTH"  # noqa: E501
    ),
    "excel.from_excel_serial": (
        "serial read as an Excel serial day number on the 1900 epoch"
    ),
    "excel.irr": (
        "the rate at which the cashflows in cash discount to nothing -- the internal rate of return"  # noqa: E501
    ),
    "excel.pv": (
        "the present value of a level payment of pmt over nper periods at rate, Excel's PV"  # noqa: E501
    ),
    "excel.round": (
        "premium rounded to 2 places, a tie going to the neighbour further from zero as Excel rounds"  # noqa: E501
    ),
    "excel.yearfrac": (
        "the year fraction from start to end on day-count basis act/act"
    ),
    "exp": ("e raised to the power of rate"),
    "fill_nan": ("rate, with 0.0 wherever a value is NaN"),
    "fill_null": ("rate, with 0.0 wherever a value is missing"),
    "finance.compound": (
        "a growth factor of one plus 0.01 raised to month over 12 periods a year"
    ),
    "finance.discount": ("fv divided by one plus rate, raised to n"),
    "finance.discount_factor": (
        "a discount factor for each period of the projection, from the rate combined_decrement over month, on the spot method"  # noqa: E501
    ),
    "finance.present_value": ("cashflow discounted at rate over period periods"),
    "finance.to_monthly": (
        "rate converted from an annual rate to the monthly equivalent, on the compound method"  # noqa: E501
    ),
    "floor": ("the largest whole number not above age"),
    "is_finite": ("whether rate is a finite number, neither infinite nor NaN"),
    "is_in": ("whether code is one of [A], a null equal to nothing and answering null"),
    "is_infinite": ("whether rate is an infinity, of either sign"),
    "is_nan": ("whether rate is NaN: a value an arithmetic could not name"),
    "is_not_nan": ("whether rate is anything other than NaN"),
    "is_not_null": ("whether rate is present at all"),
    "is_null": ("whether rate is missing -- a value that was never there"),
    "join": (
        "a column that arrived from a second table, matched on product_id under a left join"  # noqa: E501
    ),
    "log": ("the natural logarithm of age, to base e"),
    "log10": ("the logarithm of age to base ten"),
    "log1p": ("the natural logarithm of one plus rate, kept accurate near zero"),
    "norm_cdf": (
        "the standard normal distribution function at rate: the chance a standard normal value is at most it"  # noqa: E501
    ),
    "lookup": (
        "one value per row read out of the mortality base at age, a key the base does not carry stopping the run"  # noqa: E501
    ),
    "mortality.at": (
        "one rate per row read out of the cso_2017_male_select mortality base at age, duration -- a select and ultimate basis, a duration past the select period clamped back to it -- with ages taken as age last birthday and not converted"  # noqa: E501
    ),
    "not_": ("the negation of age: true wherever it is false"),
    "projection.accumulate": (
        "the linear recurrence: each state is the state the run just left x growth + rate_mth, run from the start of the projection and opening at av0"  # noqa: E501
    ),
    "projection.at_period": (
        "cumulative_growth read -2 periods away, a negative offset being a prior period and a positive one a later"  # noqa: E501
    ),
    "projection.broadcast_to_periods": ("rate repeated once per projection period"),
    "projection.cumulative_survival": (
        "cumulative survival from combined_decrement: a running product of one minus each period's decrement across the projection's periods, opening at 1.0"  # noqa: E501
    ),
    "projection.next_period": (
        "cumulative_growth read one period ahead -- t+1 -- with 0.0 where the projection ends"  # noqa: E501
    ),
    "projection.previous_period": (
        "cumulative_growth read one period back -- t-1 -- with 0.0 at the projection's start"  # noqa: E501
    ),
    "projection.prospective_value": (
        "the present value of rate_mth at each period and every period after it, discounted by 0.05, each period's cashflow falling at its end"  # noqa: E501
    ),
    "projection.remaining_sum": (
        "the sum of rate_mth at each period and every period after it"
    ),
    "projection.with_period": ("rate_mth with period 0 replaced by 0.0"),
    "projection_frame.anniversary_mask": (
        "the periods closing a contract anniversary on the frame's own timeline (sha256:<digest>)"  # noqa: E501
    ),
    "projection_frame.period_dates": (
        "the boundary date opening each period of the frame's own timeline (sha256:<digest>)"  # noqa: E501
    ),
    "projection_frame.t_years": (
        "elapsed time in years at each boundary of the frame's own timeline (sha256:<digest>), counting from zero"  # noqa: E501
    ),
    "projection_frame.year_fractions": (
        "the year fraction each period of the frame's own timeline spans (sha256:<digest>)"  # noqa: E501
    ),
    "projection_set": (
        "a column the model's own projection axis mints: monthly boundaries, whose configuration this node carries"  # noqa: E501
    ),
    "replace": (
        "each value of code standing in [A, B] swapped for the one opposite it in [TERM, WL], every other value kept"  # noqa: E501
    ),
    "rollforward": (
        "one whole compiled rollforward (sha256:<digest>) -- the state machine every extraction from it reads"  # noqa: E501
    ),
    "rollforward.increment": (
        "the signed movement the fund_return step of the compiled rollforward made in each period"  # noqa: E501
    ),
    "rollforward.state": (
        "the av state of the compiled rollforward, read at the end of each period"
    ),
    "rollforward.struct": (
        "the compiled rollforward run whole, every state it declares arriving together"
    ),
    "round": (
        "premium moved to the nearest multiple of ten to the power of minus 2, a tie going to whichever neighbour is even"  # noqa: E501
    ),
    "round_sig_figs": ("premium kept to its leading 3 significant figures"),
    "schedule.anniversary_mask": (
        "the periods closing a contract anniversary on the sha256:<digest> schedule"
    ),
    "schedule.contract_boundary": (
        "the periods the contract has terminated by, on the sha256:<digest> schedule"
    ),
    "schedule.is_in_force": (
        "the periods the contract is still in force in, on the sha256:<digest> schedule"
    ),
    "schedule.per_policy_period_count": (
        "how many periods each policy projects for on the sha256:<digest> schedule"
    ),
    "schedule.per_policy_period_dates": (
        "each policy's own period boundary dates on the sha256:<digest> schedule, each run its own length"  # noqa: E501
    ),
    "schedule.period_dates": (
        "each policy's period boundary dates on the sha256:<digest> schedule, anchored on its own inception"  # noqa: E501
    ),
    "schedule.year_fractions": (
        "the year fraction each projection period spans on the sha256:<digest> schedule's day count"  # noqa: E501
    ),
    "sign": ("which way rate points: minus one, zero, or one"),
    "sqrt": ("the square root of age"),
    "str.to_date": (
        "entry read as a calendar date under the format %Y/%m/%d, refusing a string the format does not fit"  # noqa: E501
    ),
}


@pytest.fixture(scope="module")
def expected_sentences() -> dict[str, str]:
    """Return the sentence each operation speaks, pinned word for word."""
    return _EXPECTED
