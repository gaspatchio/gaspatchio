# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fold answers null from the period it does not have onward, and so does a total.

Three identifiers fold along a projection's periods and report a number at
every one of them: ``cum_sum``, ``cum_prod`` and
``projection.cumulative_survival``. When such a fold reaches a period carrying
no value it has lost a term of its own running answer, and it says so at that
period and at every period it would have carried the lost term into. The
direction of the fold is the direction of that run, so a reverse scan's nulls
go toward period zero. ``projection.remaining_sum`` and
``projection.prospective_value`` are reverse folds and run the same way, from
the hole back toward period zero.

The same rule reaches the totals, which is where it used to stop. ``sum``,
``mean``, ``min`` and ``max`` answer one number, and one number cannot say a
period went missing underneath it -- so each of them answers null when any
period of its operand does. A survival curve folded past a missing decrement
is the case that decided the running rule: it reads correct against the
periods it has, and only the one null cell in the middle would ever have said
otherwise. A present value taken over that curve is the case that decided the
rest, because the total is the number a reviewer signs.

``projection.accumulate`` is the last member of the family and the only one
whose fold is a compiled kernel: a linear recurrence, running forward, with a
multiplier and an addend at every period. It used to null the hole and then
carry a NaN state through every period after it, which is a fourth answer for
the one shape, and it now takes the family's rule. A NaN is left where it is:
it is a value the arithmetic carries, not a period that went missing.

A modeller who means nought writes it: ``fill_null(0.0)`` before the total
restores every answer these rules null, and puts the assumption where a
reviewer can read it.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

# The run the specification's own null examples use, with the hole at period 1.
LOST_AT_ONE = [10.0, None, 30.0, 40.0]


def _periods(values: list[list[float | None] | None]) -> pl.Series:
    return pl.Series("x", values, dtype=pl.List(pl.Float64))


def _fold(values: pl.Series, name: str, **kwargs: object) -> list:
    frame = ActuarialFrame(pl.DataFrame({"x": values}))
    frame.answer = getattr(frame.x, name)(**kwargs)
    return frame.collect()["answer"].to_list()


def _total(values: pl.Series, name: str) -> list:
    frame = ActuarialFrame(pl.DataFrame({"x": values}))
    frame.answer = getattr(frame.x.list, name)()
    return frame.collect()["answer"].to_list()


def _survival(values: pl.Series, **kwargs: object) -> list:
    frame = ActuarialFrame(pl.DataFrame({"x": values}))
    frame.answer = frame.x.projection.cumulative_survival(**kwargs)
    return frame.collect()["answer"].to_list()


def _recurrence_frame(
    initial: list[float | None],
    multiplier: list[list[float | None]],
    addend: list[list[float | None]],
) -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "initial": pl.Series("initial", initial, dtype=pl.Float64),
                "multiplier": pl.Series(
                    "multiplier", multiplier, dtype=pl.List(pl.Float64)
                ),
                "addend": pl.Series("addend", addend, dtype=pl.List(pl.Float64)),
            }
        )
    )


def _accumulate(
    initial: list[float | None],
    multiplier: list[list[float | None]],
    addend: list[list[float | None]],
) -> list:
    frame = _recurrence_frame(initial, multiplier, addend)
    frame.answer = frame.multiplier.projection.accumulate(
        initial=frame.initial, multiplier=frame.multiplier, addend=frame.addend
    )
    return frame.collect()["answer"].to_list()


@pytest.mark.parametrize(
    ("name", "reverse", "expected"),
    [
        # Forward: only period 0 is reached before the hole.
        ("cum_sum", False, [10.0, None, None, None]),
        # Reverse: the fold starts at period 3, so 40.0 and 30.0 + 40.0 = 70.0
        # are both reached before the hole and the nulls run the other way.
        ("cum_sum", True, [None, None, 70.0, 40.0]),
        ("cum_prod", False, [10.0, None, None, None]),
        # 30.0 * 40.0 = 1200.0.
        ("cum_prod", True, [None, None, 1200.0, 40.0]),
    ],
)
def test_a_scan_answers_null_from_its_lost_period_onward_in_its_own_direction(
    name: str,
    expected: list[float | None],
    *,
    reverse: bool,
) -> None:
    """The direction of the fold is the direction the missing value runs in."""
    assert _fold(_periods([LOST_AT_ONE]), name, reverse=reverse) == [expected]


@pytest.mark.parametrize(
    ("name", "reverse", "carried_on"),
    [
        # What a fold that skipped the hole and continued reports: 10 + 30,
        # then 40 + 40.
        ("cum_sum", False, [10.0, None, 40.0, 80.0]),
        # Reversed: 40, then 30 + 40, then 10 + 70 across the hole.
        ("cum_sum", True, [80.0, None, 70.0, 40.0]),
        # 10 * 30, then 300 * 40.
        ("cum_prod", False, [10.0, None, 300.0, 12000.0]),
        # 40, then 30 * 40, then 10 * 1200 across the hole.
        ("cum_prod", True, [12000.0, None, 1200.0, 40.0]),
    ],
)
def test_a_scan_no_longer_reports_the_total_a_fold_past_the_hole_would(
    name: str,
    carried_on: list[float | None],
    *,
    reverse: bool,
) -> None:
    """The reading this rule replaced left a plausible number after the hole.

    Named so the change is legible. The periods the fold reached before the
    hole answer what they always answered; the periods after it carried a
    number and now carry a null, which is the whole of the difference.
    """
    answer = _fold(_periods([LOST_AT_ONE]), name, reverse=reverse)[0]
    reached = slice(2, None) if reverse else slice(0, 1)
    lost = slice(0, 2) if reverse else slice(1, None)
    assert answer[reached] == carried_on[reached]
    assert all(value is None for value in answer[lost])
    assert any(value is not None for value in carried_on[lost])


@pytest.mark.parametrize("name", ["cum_sum", "cum_prod"])
@pytest.mark.parametrize("reverse", [False, True])
def test_a_scan_over_periods_that_all_carry_a_value_is_untouched(
    name: str,
    *,
    reverse: bool,
) -> None:
    """A run with no hole in it folds exactly as it always did."""
    expected = {
        ("cum_sum", False): [1.0, 3.0, 6.0],
        ("cum_sum", True): [6.0, 5.0, 3.0],
        ("cum_prod", False): [1.0, 2.0, 6.0],
        ("cum_prod", True): [6.0, 6.0, 3.0],
    }[name, reverse]
    assert _fold(_periods([[1.0, 2.0, 3.0], []]), name, reverse=reverse) == [
        expected,
        [],
    ]


@pytest.mark.parametrize("name", ["cum_sum", "cum_prod"])
@pytest.mark.parametrize("reverse", [False, True])
def test_a_null_outer_list_is_a_policy_with_no_column_at_all(
    name: str,
    *,
    reverse: bool,
) -> None:
    """A null policy answers null; an empty one answers the empty run."""
    assert _fold(_periods([[1.0, 2.0], None, []]), name, reverse=reverse)[1:] == [
        None,
        [],
    ]


def test_a_scan_keeps_the_inner_dtype_it_was_handed() -> None:
    """The mask must not widen an integer timeline to float on its way past."""
    frame = ActuarialFrame({"x": pl.Series([[1, None, 3, 4]], dtype=pl.List(pl.Int64))})
    frame.answer = frame.x.cum_sum()

    result = frame.collect()
    assert result["answer"].to_list() == [[1, None, None, None]]
    assert result.schema["answer"] == pl.List(pl.Int64)


def test_a_survival_that_lost_a_decrement_is_unknown_from_there_on() -> None:
    """1 - 0.1 = 0.9 is reached; the missing decrement ends the product."""
    assert _survival(_periods([[0.1, None, 0.3]]), start_at=None) == [[0.9, None, None]]


def test_the_opening_value_is_the_boundary_and_never_the_missing_factor() -> None:
    """``start_at`` shifts the masked product; it does not fill the hole.

    The mask goes on ``[0.9, null, null]`` first, and prepending the opening
    value and dropping the last element then gives ``[1.0, 0.9, null]``. One
    more period carries a value than in the ``start_at=None`` spelling above,
    and that is the shift rather than the fold: masking after the shift would
    put the null a period late and claim a survival the decrements never
    supported.
    """
    assert _survival(_periods([[0.1, None, 0.3]])) == [[1.0, 0.9, None]]
    assert _survival(_periods([[0.1, None, 0.3]]), start_at=0.5) == [[0.5, 0.9, None]]


def test_the_survival_rule_is_about_the_fold_not_the_factor_it_folds() -> None:
    """``from_survival`` cumulates the column itself and loses a term too.

    The rate spelling and the survival spelling of the same policy are the
    same product with the same hole in it, so they must null the same periods.
    """
    rates = _survival(_periods([[0.1, None, 0.3]]), start_at=None)
    factors = _survival(_periods([[0.9, None, 0.7]]), start_at=None, from_survival=True)
    assert rates == factors == [[0.9, None, None]]
    assert _survival(_periods([[0.9, None, 0.7]]), from_survival=True) == [
        [1.0, 0.9, None]
    ]


def test_a_survival_over_decrements_that_all_arrived_is_untouched() -> None:
    """The published survival answers do not move under this rule.

    Written as the running product rather than as its three decimals, because
    the product is what the clause states and rounding it here would pin a
    different number from the one the fold reaches.
    """
    first = 1 - 0.1
    second = first * (1 - 0.2)
    third = second * (1 - 0.3)
    assert _survival(_periods([[0.1, 0.2, 0.3], []]), start_at=None) == [
        [first, second, third],
        [],
    ]
    assert _survival(_periods([[0.1, 0.2, 0.3], []])) == [[1.0, first, second], []]


def test_a_null_outer_list_survives_the_survival_fold_as_null() -> None:
    """A policy with no decrement column has no survival curve either."""
    assert _survival(_periods([[0.1, 0.2], None])) == [[1.0, 0.9], None]


def test_a_total_over_a_nulled_survival_no_longer_folds_past_the_tail() -> None:
    """The asymmetry this file used to pin is gone: the total nulls too.

    §§11.1.14-11.1.17 used to keep the rule that a null period is absent to
    the fold, so a total taken over a survival the running rule had nulled
    folded past the tail and reported 1.9 over ``[1.0, 0.9, null]``. That was
    the cost weighed when the running rule was taken, and it is the last
    place a missing period disappeared without a word.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[0.1, None, 0.3]])}))
    frame.survival = frame.x.projection.cumulative_survival()
    frame.total = frame.survival.list.sum()

    result = frame.collect()
    assert result["survival"].to_list() == [[1.0, 0.9, None]]
    assert result["total"].to_list() == [None]


def test_a_run_of_nothing_but_nulls_answers_null_through_every_fold() -> None:
    """The all-null run: ``sum`` answered nought here and answers null now.

    ``mean``, ``min`` and ``max`` already answered null, on the reading that
    an average, a least and a greatest of nothing are not numbers. ``sum``
    kept the empty run's nought, which read a run of missing periods as a run
    of no periods; it joins its siblings, and a modeller who means nought
    says so with ``fill_null``.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[None, None, None]])}))
    frame.total = frame.x.list.sum()
    frame.average = frame.x.list.mean()
    frame.least = frame.x.list.min()
    frame.greatest = frame.x.list.max()
    frame.running = frame.x.cum_sum()

    result = frame.collect()
    assert result["total"].to_list() == [None]
    assert result["average"].to_list() == [None]
    assert result["least"].to_list() == [None]
    assert result["greatest"].to_list() == [None]
    assert result["running"].to_list() == [[None, None, None]]


def test_the_empty_run_still_sums_to_nought() -> None:
    """A run with no periods has lost none, so the nought stays where it was.

    The rule is about a period the fold reached and found empty. An empty
    list reaches no period at all, which is the case ``sum``'s "the sum of an
    empty run is nought" has always been about, and it is left exactly there.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[]])}))
    frame.total = frame.x.list.sum()

    assert frame.collect()["total"].to_list() == [0.0]


def test_a_null_outer_list_answers_null_through_all_six_folds() -> None:
    """The other closure: a policy with no column, through every fold."""
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[10.0, 30.0], None])}))
    frame.total = frame.x.list.sum()
    frame.average = frame.x.list.mean()
    frame.least = frame.x.list.min()
    frame.greatest = frame.x.list.max()
    frame.running_total = frame.x.cum_sum()
    frame.running_product = frame.x.cum_prod()

    result = frame.collect()
    assert result["total"].to_list() == [40.0, None]
    assert result["average"].to_list() == [20.0, None]
    assert result["least"].to_list() == [10.0, None]
    assert result["greatest"].to_list() == [30.0, None]
    assert result["running_total"].to_list() == [[10.0, 40.0], None]
    assert result["running_product"].to_list() == [[10.0, 300.0], None]


def test_the_row_axis_survival_fold_is_left_where_it_was() -> None:
    """The rule is about the period axis, and the row axis is not it.

    ``cum_sum`` and ``cum_prod`` refuse a receiver with no period axis at the
    door, so the down-the-column survival is the only row fold this vocabulary
    still spells -- and §11.1.19 states the per-period form only. Pinned so
    that changing the row axis is a decision someone takes rather than one
    that arrives with a shared helper.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"x": pl.Series([0.01, None, 0.01, 0.01], dtype=pl.Float64)})
    )
    frame.answer = frame.x.projection.cumulative_survival()
    assert frame.collect()["answer"].to_list() == [1.0, 0.99, None, 0.9801]

    with pytest.raises(TypeError, match="folds projection periods"):
        frame.x.cum_sum()


# The run the totals are measured over, with the hole at period 2. Four equal
# periods make every fold below readable without a calculator: the clean run
# beside it is the same four periods with the hole filled by the value the
# rest carry, so a fold that merely broke would report something other than
# the number written here.
TOTALLED = [100.0, 100.0, None, 100.0]
WHOLE = [100.0, 100.0, 100.0, 100.0]


@pytest.mark.parametrize(
    ("method", "over_the_whole_run"),
    [
        ("sum", 400.0),
        ("mean", 100.0),
        ("min", 100.0),
        ("max", 100.0),
    ],
)
def test_a_total_over_a_lost_period_is_null_and_over_a_whole_run_is_not(
    method: str,
    over_the_whole_run: float,
) -> None:
    """A total cannot say a period went missing, so it says null instead.

    The second policy is the same four periods with nothing missing from
    them, so the fold is shown still reaching its ordinary answer: a fold
    that had simply broken would null that one too.
    """
    assert _total(_periods([TOTALLED, WHOLE]), method) == [
        None,
        over_the_whole_run,
    ]


@pytest.mark.parametrize("method", ["sum", "mean", "min", "max"])
def test_a_total_of_a_run_of_nothing_but_nulls_is_null(method: str) -> None:
    """``sum`` used to answer nought here, reading the run as an empty one."""
    assert _total(_periods([[None, None]]), method) == [None]


@pytest.mark.parametrize("method", ["sum", "mean", "min", "max"])
def test_a_total_of_a_null_outer_list_stays_null(method: str) -> None:
    """A policy with no column at all answered null before and answers null now.

    Kept beside the rule above because the two look alike in the output and
    are different in the data: one policy has periods and one of them is
    empty, the other has no periods to lose.
    """
    assert _total(_periods([WHOLE, None]), method)[1] is None


def test_a_remaining_sum_nulls_from_the_hole_back_toward_period_zero() -> None:
    """The suffix sum folds from the end, so its lost periods run that way.

    Period 3 is 100.0 and is reached before the fold meets the hole at period
    2; periods 2, 1 and 0 are the hole and what lies beyond it in the
    direction this fold runs. A fold that skipped the hole and carried on
    reported ``[300.0, 200.0, null, 100.0]``, a suffix total with a period
    missing from underneath it.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([TOTALLED, WHOLE])}))
    frame.answer = frame.x.projection.remaining_sum()

    assert frame.collect()["answer"].to_list() == [
        [None, None, None, 100.0],
        [400.0, 300.0, 200.0, 100.0],
    ]


def test_a_remaining_sum_answers_null_for_an_all_null_run_and_a_null_policy() -> None:
    """Both closures, on the fold that already gave them and must go on doing so."""
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[None, None], None])}))
    frame.answer = frame.x.projection.remaining_sum()

    assert frame.collect()["answer"].to_list() == [[None, None], None]


def test_a_prospective_value_nulls_from_the_hole_back_toward_period_zero() -> None:
    """The present value is a reverse fold and loses its periods the same way.

    At 5% end-of-period, the last period's cashflow of 100.0 is worth
    100 / 1.05 = 95.23809523809523 at period 3, which is the one position
    this fold reaches before the hole. It reported
    ``[268.21..., 181.62..., null, 95.23...]`` before this rule -- three
    reserves that had each quietly lost a period.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([TOTALLED, WHOLE])}))
    frame.answer = frame.x.projection.prospective_value(discount_rate=0.05)

    lost, whole = frame.collect()["answer"].to_list()
    assert lost == [None, None, None, pytest.approx(100.0 / 1.05)]
    assert whole == pytest.approx(
        [
            sum(100.0 / 1.05**period for period in range(1, 5)),
            sum(100.0 / 1.05**period for period in range(1, 4)),
            sum(100.0 / 1.05**period for period in range(1, 3)),
            100.0 / 1.05,
        ]
    )


def test_a_prospective_value_nulls_the_same_way_under_either_timing() -> None:
    """The rule is about the fold, not about where in the period the cash lands.

    Beginning-of-period leaves the current cashflow undiscounted, so period
    3 answers its own 100.0; the periods the fold has lost are the same
    three either way.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([TOTALLED])}))
    frame.answer = frame.x.projection.prospective_value(
        discount_rate=0.05, timing="beginning_of_period"
    )

    assert frame.collect()["answer"].to_list() == [[None, None, None, 100.0]]


def test_a_prospective_value_answers_null_for_an_all_null_run_and_a_null_policy() -> (
    None
):
    """Both closures again, on the second reverse fold."""
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([[None, None], None])}))
    frame.answer = frame.x.projection.prospective_value(discount_rate=0.05)

    assert frame.collect()["answer"].to_list() == [[None, None], None]


def test_declaring_the_nought_with_fill_null_restores_every_total() -> None:
    """The route out, and the only one: say the missing period is a nought.

    This is the line the rule asks a modeller to write, and the graph records
    it, so a reviewer reading the model sees the assumption instead of
    inferring it from an answer that never mentioned the hole.
    """
    frame = ActuarialFrame(pl.DataFrame({"x": _periods([TOTALLED])}))
    frame.declared = frame.x.fill_null(0.0)
    frame.total = frame.declared.list.sum()
    frame.least = frame.declared.list.min()
    frame.suffix = frame.declared.projection.remaining_sum()
    frame.present_value = frame.declared.projection.prospective_value(
        discount_rate=0.05
    )

    result = frame.collect()
    assert result["total"].to_list() == [300.0]
    assert result["least"].to_list() == [0.0]
    assert result["suffix"].to_list() == [[300.0, 200.0, 100.0, 100.0]]
    assert result["present_value"].to_list()[0][3] == pytest.approx(100.0 / 1.05)


# The recurrence's own runs. Whole numbers throughout, so every state is
# exact in a double and each one can be read off the line above it:
# s[t] = s[t-1] * multiplier[t] + addend[t], opening at initial.
OPENING = [10.0]
GROWTH = [[2.0, None, 3.0, 4.0]]
FLOW = [[1.0, 1.0, 1.0, 1.0]]


def test_a_recurrence_that_lost_a_growth_factor_is_unknown_from_there_on() -> None:
    """10 * 2 + 1 = 21 is reached; the missing factor ends the recurrence.

    This is the family's forward rule on the one fold that had a fourth
    answer of its own. The state after the hole is not nought, not the state
    before it, and not a number at all.
    """
    assert _accumulate(OPENING, GROWTH, FLOW) == [[21.0, None, None, None]]


def test_a_recurrence_no_longer_carries_a_nan_state_past_the_hole() -> None:
    """The reading this replaced: null at the hole, then NaN for ever.

    Named so the change is legible. A NaN there was not the arithmetic's
    answer -- the kernel put it in as a stand-in for a state it had lost --
    and it made every later period non-finite, which is the shape a reviewer
    reads as a broken calculation rather than as a missing input.
    """
    answer = _accumulate(OPENING, GROWTH, FLOW)[0]
    assert answer[0] == 21.0
    assert all(value is None for value in answer[1:])
    assert not any(isinstance(value, float) and math.isnan(value) for value in answer)


def test_the_recurrence_rule_is_about_the_period_not_which_step_lost_it() -> None:
    """A null addend ends the fold exactly as a null multiplier does.

    The hole is moved to period 2 as well as swapped between the operands,
    so the two periods before it are shown still reporting their states:
    10 * 2 + 1 = 21, then 21 * 2 + 2 = 44.
    """
    assert _accumulate(OPENING, [[2.0, 2.0, 2.0, 2.0]], [[1.0, 2.0, None, 4.0]]) == [
        [21.0, 44.0, None, None]
    ]


def test_a_recurrence_with_no_opening_state_answers_a_run_of_nulls() -> None:
    """A null initial: both steps arrived, and there is nothing to open with."""
    assert _accumulate([None], [[2.0, 3.0]], [[1.0, 1.0]]) == [[None, None]]


def test_a_recurrence_whose_every_step_is_null_answers_a_run_of_nulls() -> None:
    """The closure: the hole is the first period, so it reaches every position."""
    assert _accumulate(OPENING, [[None, None]], [[1.0, 1.0]]) == [[None, None]]


def test_a_recurrence_over_steps_that_all_arrived_is_untouched() -> None:
    """A run with no hole in it folds exactly as it always did.

    21, then 21 * 3 + 1 = 64, then 64 * 4 + 1 = 257 -- which is also the
    answer a fold that skipped the hole above and carried on would have
    reported at periods 2 and 3, on a state it no longer had.
    """
    assert _accumulate(OPENING, [[2.0, 3.0, 4.0]], [[1.0, 1.0, 1.0]]) == [
        [21.0, 64.0, 257.0]
    ]


def test_a_nan_step_is_a_value_the_recurrence_keeps_and_not_a_lost_period() -> None:
    """A NaN is arithmetic, a null is a period that never arrived.

    21 * NaN + 1 is NaN and so is every state after it, which is what the
    multiplication says and what the rest of the package does with a NaN in a
    column. The two must not answer alike: a modeller who sees nulls knows an
    input was missing, and one who sees NaN knows a number went non-finite.
    """
    answer = _accumulate(OPENING, [[2.0, math.nan, 3.0]], [[1.0, 1.0, 1.0]])[0]
    assert answer[0] == 21.0
    assert math.isnan(answer[1])
    assert math.isnan(answer[2])


def test_declaring_the_nought_with_fill_null_restores_the_recurrence() -> None:
    """The route out is the family's, and the graph records that it was taken.

    With the missing growth factor declared nought, period 1 multiplies the
    state away and keeps the period's flow: 21 * 0 + 1 = 1, then 1 * 3 + 1 = 4,
    then 4 * 4 + 1 = 17. Nothing infers that for the modeller.
    """
    frame = _recurrence_frame(OPENING, GROWTH, FLOW)
    frame.declared = frame.multiplier.fill_null(0.0)
    frame.answer = frame.declared.projection.accumulate(
        initial=frame.initial, multiplier=frame.declared, addend=frame.addend
    )

    result = frame.collect()
    assert result["answer"].to_list() == [[21.0, 1.0, 4.0, 17.0]]
    assert "declared@1" in frame.graph.precedents("answer")
