# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Stored Float64 conditions have exact, checked indicator semantics."""

from __future__ import annotations

import datetime
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import Col, WhenThen


def test_raw_scalar_float_condition_selects_scalar_branches() -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([0.0, 1.0, -0.0], dtype=pl.Float64),
            "if_true": [10.0, 20.0, 30.0],
            "if_false": [-10.0, -20.0, -30.0],
        }
    )
    frame.selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    assert frame.collect()["selected"].to_list() == [-10.0, 20.0, -30.0]


@pytest.mark.parametrize("as_list", [False, True])
def test_float32_storage_has_the_same_exact_checked_meaning(*, as_list: bool) -> None:
    valid_flags = [[0.0, 1.0, -0.0]] if as_list else [0.0, 1.0, -0.0]
    valid_dtype = pl.List(pl.Float32) if as_list else pl.Float32
    valid = ActuarialFrame(
        {
            "flag": pl.Series("flag", valid_flags, dtype=valid_dtype),
            "value": [10.0] if as_list else [10.0, 20.0, 30.0],
        }
    )
    valid.selected = when(valid.flag).then(valid.value).otherwise(-1.0)
    expected = [[-1.0, 10.0, -1.0]] if as_list else [-1.0, 20.0, -1.0]
    assert valid.collect()["selected"].to_list() == expected

    invalid_flags = [[0.0, 0.5, 1.0]] if as_list else [0.0, 0.5, 1.0]
    invalid = ActuarialFrame(
        {
            "flag": pl.Series("flag", invalid_flags, dtype=valid_dtype),
            "value": [10.0] if as_list else [10.0, 20.0, 30.0],
        }
    )
    invalid.selected = when(invalid.flag).then(invalid.value).otherwise(-1.0)
    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        invalid.collect()


@pytest.mark.parametrize("list_is_then", [False, True])
def test_scalar_float_condition_broadcasts_over_either_list_branch(
    *, list_is_then: bool
) -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([1.0, 0.0], dtype=pl.Float64),
            "scalar": [5.0, 6.0],
            "periods": [[10.0, 20.0], [30.0]],
        }
    )
    then = frame.periods if list_is_then else frame.scalar
    otherwise = frame.scalar if list_is_then else frame.periods
    frame.selected = when(frame.flag).then(then).otherwise(otherwise)

    expected = [[10.0, 20.0], [6.0]] if list_is_then else [[5.0, 5.0], [30.0]]
    assert frame.collect()["selected"].to_list() == expected


@pytest.mark.parametrize("list_is_then", [False, True])
def test_list_float_condition_combines_scalar_and_list_branches(
    *, list_is_then: bool
) -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series(
                [[1.0, 0.0, -0.0], [0.0, 1.0]], dtype=pl.List(pl.Float64)
            ),
            "scalar": [5.0, 6.0],
            "periods": [[10.0, 20.0, 30.0], [40.0, 50.0]],
        }
    )
    then = frame.periods if list_is_then else frame.scalar
    otherwise = frame.scalar if list_is_then else frame.periods
    frame.selected = when(frame.flag).then(then).otherwise(otherwise)

    expected = (
        [[10.0, 5.0, 5.0], [6.0, 50.0]]
        if list_is_then
        else [[5.0, 20.0, 30.0], [40.0, 6.0]]
    )
    assert frame.collect()["selected"].to_list() == expected


def test_stored_comparison_results_remain_valid_scalar_and_list_conditions() -> None:
    frame = ActuarialFrame(
        {
            "scalar_value": [-1.0, 2.0],
            "period_values": [[-1.0, 2.0], [3.0]],
        }
    )
    frame.scalar_flag = frame.scalar_value > 0.0
    frame.list_flag = frame.period_values > 0.0
    frame.scalar_selected = when(frame.scalar_flag).then(10.0).otherwise(-10.0)
    frame.list_selected = when(frame.list_flag).then(10.0).otherwise(-10.0)

    result = frame.collect()
    assert result.schema["scalar_flag"] == pl.Float64
    assert result.schema["list_flag"] == pl.List(pl.Float64)
    assert result["scalar_selected"].to_list() == [-10.0, 10.0]
    assert result["list_selected"].to_list() == [[-10.0, 10.0], [10.0]]


@pytest.mark.parametrize(
    "invalid",
    [0.5, -1.0, 2.0, math.nan, math.inf, -math.inf, None],
    ids=("fraction", "minus-one", "two", "nan", "positive-inf", "negative-inf", "null"),
)
def test_invalid_raw_scalar_float_condition_refuses(invalid: float | None) -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([0.0, invalid, 1.0], dtype=pl.Float64),
            "value": [10.0, 20.0, 30.0],
        }
    )
    frame.selected = when(frame.flag).then(frame.value).otherwise(0.0)

    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        frame.collect()


@pytest.mark.parametrize(
    "flag",
    [
        pl.Series("flag", [[1.0, 0.5]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[-1.0]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[2.0]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[math.nan]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[math.inf]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[-math.inf]], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [None], dtype=pl.List(pl.Float64)),
        pl.Series("flag", [[1.0, None]], dtype=pl.List(pl.Float64)),
    ],
    ids=(
        "fraction",
        "minus-one",
        "two",
        "nan",
        "positive-inf",
        "negative-inf",
        "outer-null",
        "element-null",
    ),
)
def test_invalid_raw_list_float_condition_refuses(flag: pl.Series) -> None:
    frame = ActuarialFrame({"flag": flag, "value": [10.0]})
    frame.selected = when(frame.flag).then(frame.value).otherwise(0.0)

    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        frame.collect()


@pytest.mark.parametrize("as_list", [False, True])
def test_invalid_earlier_computed_float_condition_refuses(*, as_list: bool) -> None:
    seed = [[0.0, 1.0, 2.0]] if as_list else [0.0, 1.0, 2.0]
    value = [10.0] if as_list else [10.0, 20.0, 30.0]
    frame = ActuarialFrame({"seed": seed, "value": value})
    frame.flag = frame.seed / 2.0
    frame.selected = when(frame.flag).then(frame.value).otherwise(0.0)

    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        frame.collect()


def test_empty_list_float_conditions_produce_empty_results() -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([[], []], dtype=pl.List(pl.Float64)),
            "value": [10.0, 20.0],
        }
    )
    frame.selected = when(frame.flag).then(frame.value).otherwise(-1.0)

    result = frame.collect()["selected"]
    assert result.to_list() == [[], []]
    assert result.dtype == pl.List(pl.Float64)


@pytest.mark.parametrize(
    ("schema", "expected_dtype"),
    [
        ({"flag": pl.Float64, "value": pl.Float64}, pl.Float64),
        (
            {"flag": pl.List(pl.Float64), "value": pl.Float64},
            pl.List(pl.Float64),
        ),
    ],
)
def test_float_conditions_over_no_policies_succeed_vacuously(
    schema: dict[str, pl.DataType], expected_dtype: pl.DataType
) -> None:
    frame = ActuarialFrame(pl.DataFrame(schema=schema))
    frame.selected = when(frame.flag).then(frame.value).otherwise(0.0)

    result = frame.collect()["selected"]
    assert result.len() == 0
    assert result.dtype == expected_dtype


def test_non_null_boolean_conditions_keep_their_existing_meaning() -> None:
    frame = ActuarialFrame(
        {
            "scalar_flag": [True, False],
            "list_flag": [[True, False], [False]],
            "value": [10.0, 20.0],
        }
    )
    frame.scalar_selected = when(frame.scalar_flag).then(frame.value).otherwise(-1.0)
    frame.list_selected = when(frame.list_flag).then(frame.value).otherwise(-1.0)

    result = frame.collect()
    assert result["scalar_selected"].to_list() == [10.0, -1.0]
    assert result["list_selected"].to_list() == [[10.0, -1.0], [-1.0]]


@pytest.mark.parametrize(
    "flag",
    [
        pl.Series("flag", [[True, False]], dtype=pl.List(pl.Boolean)),
        pl.Series("flag", [[1.0, 0.0]], dtype=pl.List(pl.Float64)),
    ],
    ids=("boolean", "stored-float"),
)
def test_direct_list_conditions_preserve_string_branch_results(flag: pl.Series) -> None:
    frame = ActuarialFrame(
        {
            "flag": flag,
            "if_true": pl.Series(
                "if_true", [["active", "ignored"]], dtype=pl.List(pl.String)
            ),
            "if_false": pl.Series(
                "if_false", [["ignored", "expired"]], dtype=pl.List(pl.String)
            ),
        }
    )
    frame.selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    result = frame.collect()["selected"]
    assert result.dtype == pl.List(pl.String)
    assert result.to_list() == [["active", "expired"]]


def test_zero_policy_list_float_condition_preserves_string_output_type() -> None:
    frame = ActuarialFrame(
        pl.DataFrame(
            schema={
                "flag": pl.List(pl.Float64),
                "if_true": pl.List(pl.String),
                "if_false": pl.List(pl.String),
            }
        )
    )
    frame.selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    result = frame.collect()["selected"]
    assert result.len() == 0
    assert result.dtype == pl.List(pl.String)


@pytest.mark.parametrize(
    ("if_true", "if_false", "dtype", "expected"),
    [
        # Two integer branches are an integer conditional (section 11.1.28):
        # the plugin selects in Float64, and the lowering hands the answer
        # back in the branches' own type rather than as a conversion the
        # model never wrote.
        (
            pl.Series("if_true", [[1, 2]], dtype=pl.List(pl.Int64)),
            pl.Series("if_false", [[3, 4]], dtype=pl.List(pl.Int64)),
            pl.List(pl.Int64),
            [[1, 4]],
        ),
        # So are two date branches: a run of dates, not the day counts the
        # plugin selects them by.
        (
            pl.Series(
                "if_true",
                [[datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)]],
                dtype=pl.List(pl.Date),
            ),
            pl.Series(
                "if_false",
                [[datetime.date(2027, 1, 1), datetime.date(2027, 1, 2)]],
                dtype=pl.List(pl.Date),
            ),
            pl.List(pl.Date),
            [[datetime.date(2026, 1, 1), datetime.date(2027, 1, 2)]],
        ),
    ],
    ids=("integer", "date"),
)
def test_boolean_list_condition_keeps_existing_plugin_output_types(
    if_true: pl.Series,
    if_false: pl.Series,
    dtype: pl.DataType,
    expected: list[list[object]],
) -> None:
    frame = ActuarialFrame(
        {"flag": [[True, False]], "if_true": if_true, "if_false": if_false}
    )
    frame.selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    result = frame.collect()["selected"]
    assert result.dtype == dtype
    assert result.to_list() == expected


def test_invalid_scalar_float_refuses_even_when_list_branches_are_empty() -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([0.5], dtype=pl.Float64),
            "if_true": pl.Series([[]], dtype=pl.List(pl.Float64)),
            "if_false": pl.Series([[]], dtype=pl.List(pl.Float64)),
        }
    )
    frame.selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        frame.collect()


def test_stored_float_guard_does_not_change_the_operation_tree() -> None:
    frame = ActuarialFrame(
        {
            "flag": pl.Series([[1.0, 0.0]], dtype=pl.List(pl.Float64)),
            "if_true": [[10.0, 20.0]],
            "if_false": [[-10.0, -20.0]],
        }
    )
    selected = when(frame.flag).then(frame.if_true).otherwise(frame.if_false)

    assert selected._node == WhenThen(  # noqa: SLF001
        cond=Col("flag"),
        then=Col("if_true"),
        otherwise=Col("if_false"),
    )


# --- what the refusal reads like ------------------------------------------

# A lazy plan cannot raise, so a per-row refusal travels as a string that will
# not cast and arrives headlined as somebody else's type error. The sentence
# is the framework's; these say it reaches the reader as one.


def _refusal_from(frame: ActuarialFrame) -> str:
    """Collect ``frame``, expecting the stored-predicate refusal, and return it."""
    with pytest.raises(pl.exceptions.PolarsError) as caught:
        frame.collect()
    return str(caught.value)


def test_the_refusal_leads_with_the_sentence_and_names_the_column() -> None:
    """The first line is the refusal, not a conversion from `str` to `i64`."""
    frame = ActuarialFrame(
        {"flag": pl.Series([1.0, 0.0, 0.5], dtype=pl.Float64), "a": [10.0, 20.0, 30.0]}
    )
    frame.picked = when(frame.flag).then(frame.a).otherwise(0.0)

    message = _refusal_from(frame)

    first = message.splitlines()[0]
    assert first == (
        "Column 'flag' is used as a condition but holds a value that is "
        "neither 0.0 nor 1.0."
    )
    # The next move, in the spelling the model would have to type back.
    assert "when(af.flag == 1.0)" in message
    # And the engine's own account is kept, under the sentence rather than over it.
    assert "conversion from `str` to `i64`" in message
    assert message.index(first) < message.index("conversion from `str` to `i64`")


def test_a_per_period_indicator_names_its_column_too() -> None:
    """The list-shaped route reaches the same door with the same name on it."""
    frame = ActuarialFrame(
        {
            "lapsed": pl.Series([[1.0, 0.0, 0.5]], dtype=pl.List(pl.Float64)),
            "a": [10.0],
        }
    )
    frame.picked = when(frame.lapsed).then(frame.a).otherwise(0.0)

    assert _refusal_from(frame).startswith("Column 'lapsed' is used as a condition")


def test_a_column_needing_brackets_is_offered_back_in_brackets() -> None:
    """The remedy has to be typeable, and `af.mass lapse` is not."""
    frame = ActuarialFrame(
        {
            "mass lapse": pl.Series([0.5], dtype=pl.Float64),
            "a": [10.0],
        }
    )
    frame.picked = when(frame["mass lapse"]).then(frame.a).otherwise(0.0)

    message = _refusal_from(frame)

    assert message.startswith("Column 'mass lapse' is used as a condition")
    assert "when(af['mass lapse'] == 1.0)" in message


def test_an_exact_indicator_is_still_a_condition() -> None:
    """The refusal is about values that are not 0 or 1, and nothing else."""
    frame = ActuarialFrame(
        {"flag": pl.Series([1.0, 0.0], dtype=pl.Float64), "a": [10.0, 20.0]}
    )
    frame.picked = when(frame.flag).then(frame.a).otherwise(-1.0)

    assert frame.collect()["picked"].to_list() == [10.0, -1.0]


def test_the_remedy_the_refusal_offers_runs_on_the_column_it_refused() -> None:
    """The move the sentence names, on the values that earned the sentence."""
    frame = ActuarialFrame(
        {"flag": pl.Series([1.0, 0.0, 0.5], dtype=pl.Float64), "a": [10.0, 20.0, 30.0]}
    )
    frame.picked = when(frame.flag == 1.0).then(frame.a).otherwise(0.0)

    assert frame.collect()["picked"].to_list() == [10.0, 0.0, 0.0]


# --- which errors the lift may touch, and which it may not ------------------

# The lift reads the list of values Polars reports a strict cast could not
# convert. The first version of it matched the refusal sentence anywhere in
# the message, and the sentence is a literal in the plan, so it is also in the
# resolved-plan dump of any resolution-time failure on a model that holds a
# stored indicator. That put this project's refusal on top of somebody else's
# error. A stored comparison is Float64, so `af.in_force = af.month < af.term`
# followed by `when(af.in_force)` is enough to arm it: ordinary models.


def _a_valid_indicator_and_an_unrelated_mistake() -> ActuarialFrame:
    """Return a frame whose predicate is fine and whose arithmetic is not."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "flag": [1.0, 0.0],
                "premium": [10.0, 20.0],
                "product_code": ["A", "B"],
            }
        )
    )
    frame.selected = when(frame.flag).then(frame.premium).otherwise(0.0)
    frame.oops = pl.col("product_code") - 1.0
    return frame


def test_an_unrelated_failure_keeps_the_engine_s_own_headline() -> None:
    """NEGATIVE CONTROL, and the reason this section exists.

    Nothing in the first version's tests could have caught the defect: every
    one of them collected a frame whose predicate really was invalid, so the
    lifted sentence was always the right sentence, and a lift that fired on
    every error carrying the plan dump passed them all. This is the input that
    falsifies it -- a *valid* predicate beside a mistake of another kind --
    and it must stay a case where the lift does nothing.
    """
    message = _refusal_from(_a_valid_indicator_and_an_unrelated_mistake())

    first = message.splitlines()[0]
    assert "arithmetic on dtypes str and dyn float" in first
    assert "product_code" in first
    # 'flag' may appear further down, inside the plan the engine dumps; what
    # must not happen is the predicate's refusal being announced as the fault.
    assert "is used as a condition" not in first
    assert message.index("product_code") < message.index("flag")


def test_the_error_mode_that_says_do_not_touch_is_obeyed() -> None:
    """``off`` re-raises what the engine raised, this door included."""
    frame = _a_valid_indicator_and_an_unrelated_mistake()

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AF_ERROR_MODE", "off")
        with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
            frame.collect()

    message = str(caught.value)
    assert message.splitlines()[0].startswith("arithmetic on dtypes str and dyn float")
    assert "is used as a condition" not in message
    # `off` adds nothing either: no attribution block, no lifted sentence.
    assert "Failing column" not in message


def test_a_genuine_refusal_is_still_lifted_under_the_narrower_match() -> None:
    """Narrowing the match must not cost the refusal its own headline."""
    frame = ActuarialFrame(
        {"flag": pl.Series([1.0, 0.0, 0.5], dtype=pl.Float64), "a": [10.0, 20.0, 30.0]}
    )
    frame.picked = when(frame.flag).then(frame.a).otherwise(0.0)

    assert _refusal_from(frame).startswith(
        "Column 'flag' is used as a condition but holds a value that is "
        "neither 0.0 nor 1.0."
    )


def test_a_whole_number_conversion_refusal_reads_as_a_sentence_too() -> None:
    """The same smuggling trick, the same unreadable delivery, now lifted."""
    frame = ActuarialFrame(pl.DataFrame({"value": [1.5]}))
    frame.whole = frame.value.to_integer()

    message = _refusal_from(frame)

    assert message.splitlines()[0] == (
        "Column 'value' is converted to a whole number but holds a value "
        "that is not one."
    )
    assert "af.value.floor().to_integer()" in message


def test_two_smuggled_refusals_on_one_plan_do_not_borrow_each_other() -> None:
    """The conversion failed, so the conversion's sentence is the one owed.

    The predicate here is valid and never fires; its sentence is in the plan
    all the same, which is exactly the confusion a match over the whole
    message makes.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"flag": [1.0], "premium": [10.0], "value": [1.5]})
    )
    frame.selected = when(frame.flag).then(frame.premium).otherwise(0.0)
    frame.whole = frame.value.to_integer()

    message = _refusal_from(frame)

    assert message.splitlines()[0].startswith("Column 'value' is converted to a whole")
    assert "is used as a condition" not in message
