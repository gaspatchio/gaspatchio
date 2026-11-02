# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The advice under a failure is chosen by facts, never by a word in the message.

``ErrorSuggestionEngine.suggest_fixes`` used to pick an advice family by
testing lowercased substrings of the message the user was about to read, in
order. The message routinely quotes the user's own column names, so the
family was decided by what the actuary had called a column: an arithmetic
clash beside one called ``valuation_date`` was answered with "Check date
format matches your data"; one beside ``nan_flag`` with "Handle null
values"; one beside ``file_path`` with "Check file path is correct"; and a
mortality table that stopped at 42 was answered with null handling.

Every failure below is raised for real, through the framework, so the
record and the graph the router reads are the ones a run produces. Two
helpers stand for the two things a caller may have: ``_advice`` is the one
call site's full hand (record, columns, graph facts), and
``_advice_without_facts`` is the same failure with the graph unasked --
because the guarantee that a column's NAME chooses nothing must hold
whether or not the graph could answer.
"""

from __future__ import annotations

import datetime
from typing import cast

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import search_collect_failure
from gaspatchio.errors.formatter import FriendlyErrorFormatter, graph_facts
from gaspatchio.errors.suggestions import ErrorSuggestionEngine
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan
from gaspatchio.frame.lowering._polars.plugins import list_pow

# The opening words of each advice family, so a test can say which family
# answered without repeating a whole line of prose.
DATE_ADVICE = "Check date format matches your data"
NULL_ADVICE = "Handle null values with"
FILE_ADVICE = "Check file path is correct"
CAST_ADVICE = "Try converting strings to numbers"
JAGGED_ADVICE = "List lengths differ across rows"
LOOKUP_ADVICE = "Check assumption key matches exactly"
INDEX_ADVICE = "The index into"
DECLARED_TYPE_ADVICE = "do not have the type it was declared to produce"

# The line the index family offers last, and only where a projection could
# have built the values it is offered about.
PROJECTION_CLAUSE = "came from a projection"

# The clauses the index family used to open with, and the reason each
# had to go. The first two were measured false of shapes that reach the
# family: a ragged list read straight off a model-point extract has no
# projection to have run past, a grid built from a whole term is one
# shared axis rather than a horizon per policy, and `list.get(-5)`
# ran off the START. The third named a column the failing frame need not
# have, and an actuary copying it writes a formula against a name that is
# not there.
WITHDRAWN_INDEX_CLAUSES = (
    "past the end of that policy's own projection",
    "each policy stops at its own horizon",
    "`af.cashflow.list.len()`",
)

# The clause that shipped off by one, and the arithmetic that replaced
# it. A list of three read at index three RAISES, and three is not
# SHORTER than three -- so an actuary who read the old clause, checked
# whether the row's list was shorter than the index and answered no, was
# sent past the fix. A count used as an index is how this is written.
OFF_BY_ONE_CLAUSE = "shorter than the index asked for"
BOUNDARY_CLAUSE = "one less than the number of elements that row holds"

# The arithmetic's own first spelling, retired for naming nothing on the
# two rows where it mattered most. "One less than that row's own length"
# is minus one on a row holding no elements, and on an `Array` row whose
# value is null there is no row length at all while the column's declared
# width still bounds the read. The boundary is now named per spelling,
# and the empty row is stated rather than computed.
ROW_LENGTH_CLAUSE = "one less than that row's own length"
ARRAY_BOUND_CLAUSE = "one less than the column's own fixed width"
EMPTY_ROW_CLAUSE = "a row holding none raises at every index"

# The clamp the remedy used to offer without a condition. `len() - 1` on a
# row holding no elements is minus one -- the frame reads the unsigned count
# as the i64 it fits, so it no longer wraps to 18446744073709551615 -- and a
# row holding none has no index at all, so the clamp reaches back past the
# start. Advice that steers into that is worse than advice that steers
# nowhere, so `null_on_oob=True` leads and the clamp carries the condition
# it is safe under.
EMPTY_ROW_CLAMP_CLAUSE = "a row holding none has no index to clamp to"
NULL_ON_OOB_CLAUSE = "Pass `null_on_oob=True`"

# The three lines the retired chain printed for the same failure. They
# spoke of the frame's height and of `.head()`/`.tail()` limits, which is
# not what ran out when one policy's timeline stopped short of its term,
# so the family came back on a structural route with new words rather
# than with these.
RETIRED_INDEX_LINES = (
    "Check data length before indexing",
    "Use .head() or .tail() with explicit limits",
    "Validate row count: use .height",
)


def _attributed(
    af: ActuarialFrame,
    raised: Exception,
) -> tuple[CalculationRecord, list[str]]:
    """Return the record the search attributed and the last good columns."""
    record, last_good = search_collect_failure(af, raised)
    assert isinstance(record, CalculationRecord), record
    return record, ([] if last_good is None else list(last_good.columns))


def _advice(af: ActuarialFrame, raised: Exception) -> list[str]:
    """Return the advice for a failure, with everything the call site holds."""
    record, columns = _attributed(af, raised)
    return ErrorSuggestionEngine().suggest_fixes(
        raised,
        record,
        columns,
        graph_facts(af, record),
    )


def _advice_without_facts(af: ActuarialFrame, raised: Exception) -> list[str]:
    """Return the advice for a failure with the graph never asked."""
    record, columns = _attributed(af, raised)
    return ErrorSuggestionEngine().suggest_fixes(raised, record, columns)


def _raise_dtype_clash(numeric_column: str) -> tuple[ActuarialFrame, Exception]:
    """Raise ``str * f64`` for real, with the numeric operand named as asked.

    Written as an engine fragment: the frame's own arithmetic between text
    and a number is refused where it is written, so a clash reaches the
    engine, and this advice, only through Polars written by hand.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "product_code": ["A", "B", "C"],
                numeric_column: [1.0, 2.0, 3.0],
            },
        ),
    )
    af.reserve_factor = pl.col("product_code") * pl.col(numeric_column)
    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()
    return af, caught.value


def _raise_clash_with_string_named(
    string_column: str,
) -> tuple[ActuarialFrame, Exception]:
    """Raise ``str * f64`` for real, with the STRING operand named as asked.

    An engine fragment, as :func:`_raise_dtype_clash` is.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                string_column: ["A", "B", "C"],
                "premium": [1.0, 2.0, 3.0],
            },
        ),
    )
    af.reserve_factor = pl.col(string_column) * pl.col("premium")
    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()
    return af, caught.value


def _raise_jagged_clash_beside_a_path_column() -> tuple[ActuarialFrame, Exception]:
    """Raise a jagged-list clash on a frame that also carries ``path``."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "path": ["/a/b.parquet", "/c/d.parquet"],
                "per_policy": [[1.0, 2.0], [1.0, 2.0, 3.0]],
                "curve": [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]],
            },
        ),
    )
    af.discounted = af.per_policy * af.curve
    with pytest.raises(pl.exceptions.ShapeError) as caught:
        af.collect()
    return af, caught.value


def _raise_lookup_miss() -> tuple[ActuarialFrame, Exception]:
    """Raise a real miss: a life at 99 against a table that stops at 42."""
    table = Table(
        name="advice_routed_on_facts_mortality",
        source=pl.DataFrame({"age": [40, 41, 42], "rate": [0.001, 0.0011, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "attained_age": [40, 41, 99]}),
    )
    af.mortality_rate = table.lookup(age=af.attained_age)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_index_past_the_horizon(
    index_column: str = "term",
    list_column: str = "cashflow",
    target: str = "final_cf",
) -> tuple[ActuarialFrame, Exception]:
    """Raise a real read past one policy's own horizon.

    The second policy's timeline is two periods long and its term says
    seven, which is the jagged-projection mistake this framework's own
    per-policy default invites: right for every policy whose timeline
    reaches its term, out of bounds for the first one whose does not.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                index_column: [1, 7],
                list_column: [[10.0, 11.0, 12.0], [20.0, 21.0]],
            },
        ),
    )
    af[target] = af[list_column].list.get(af[index_column])
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_a_ragged_input_list_read_past_its_end() -> tuple[ActuarialFrame, Exception]:
    """Raise on a ragged list that came off the extract, with no projection at all.

    Rider sums assured, a premium schedule, anything a Phase 1
    ``group_by(...).agg()`` builds: the lists differ in length per policy
    because the data does, and the model has no timeline, no
    ``projection.set`` call and no column called ``cashflow``.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "n_riders": [1, 4],
                "rider_sum_assured": [
                    [50000.0, 25000.0],
                    [100000.0, 10000.0, 5000.0],
                ],
            },
        ),
    )
    af.top_up_rider = af.rider_sum_assured.list.get(af.n_riders)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_an_index_off_the_start() -> tuple[ActuarialFrame, Exception]:
    """Raise on a negative index that reaches back past the list's start."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "cashflow": [[1.0, 2.0], [3.0, 4.0]]}),
    )
    af.lookback = af.cashflow.list.get(-5)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_a_count_used_as_an_index() -> tuple[ActuarialFrame, Exception]:
    """Raise the commonest shape of this mistake: a count read as an index.

    Three riders, a list of three, and the read written at the count.
    The row's list is not SHORTER than the index asked for -- it is
    exactly as long -- and the read raises anyway, because the last
    element of a list of three sits at 2.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "n_riders": [3, 3],
                "rider_premium": [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
            },
        ),
    )
    af.last_rider = af.rider_premium.list.get(af.n_riders)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_past_a_fixed_width_array() -> tuple[ActuarialFrame, Exception]:
    """Raise `.arr.get` past the width of a fixed-width ``Array`` column.

    A parquet whose cashflow column was written as a fixed-size list
    arrives as polars' ``Array``, and the read past its width raises the
    same ``ComputeError: get index is out of bounds`` a list read raises,
    under a payload one key away: ``{"ArrayExpr": {"Get": false}}``. The
    formula holds ``.arr.get`` and not ``.list.get``, which is the whole
    reason the advice names the call it found rather than one spelling.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "term": [1, 7],
                "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
            },
            schema={
                "policy_id": pl.Int64,
                "term": pl.Int64,
                "cashflow": pl.Array(pl.Float64, 3),
            },
        ),
    )
    af.final_cf = af.cashflow.polars_native().arr.get(af.term)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_past_a_real_projection_grid() -> tuple[ActuarialFrame, Exception]:
    """Raise on a timeline ``projection.set`` built, not on a hand-made list.

    A whole term, ``until="term_years"`` of 20, lays ONE grid every policy
    shares, so both policies get 21 boundaries here whatever their own
    terms -- which is the shape a hand-built fixture cannot tell from a
    per-policy timeline, and the one that showed the family's old first
    line to be false.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {"policy_id": [1, 2], "issue_age": [40, 55], "policy_term": [30, 10]},
        ),
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=20,
        frequency="annual",
    )
    af.terminal_month = af.month.list.get(af.policy_term)
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _raise_a_kernel_refusal(*, beside: str) -> tuple[ActuarialFrame, Exception]:
    """Raise the framework's own ``list_pow`` kernel on a mismatched jagged pair.

    ``beside`` chooses what stands next to the refusal in the same
    assignment: ``"nothing"``, a ``list.first()`` read that CANNOT go out
    of bounds, or a ``list.get(0)`` read that could. The failure is
    identical in all three -- one policy's ``growth_factor`` holds one
    element where its ``fund_value`` holds two -- and it is a length clash
    arriving as a ``ComputeError`` rather than as a ``ShapeError``.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "fund_value": [[1000.0, 1100.0], [2000.0, 2200.0]],
                "growth_factor": [[1.05, 1.05], [1.05]],
            },
        ),
    )
    refusal = af.growth_factor**af.fund_value
    if beside == "a read that cannot raise":
        af.accumulated = af.fund_value.polars_native().list.first() * refusal
    elif beside == "a read that could raise":
        af.accumulated = af.fund_value.list.get(0) * refusal
    else:
        af.accumulated = refusal
    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()
    return af, caught.value


def _record(
    node: Call | Col,
    column: str = "parsed",
    expr: pl.Expr | None = None,
) -> CalculationRecord:
    """Build one calculation record around a node, with nothing else real.

    ``expr`` stands in for the lowering the assignment would have built;
    it defaults to a plain column reference, which names no family.
    """
    return CalculationRecord(
        column=column,
        ordinal=1,
        operation_id=0,
        node=node,
        expr=pl.col(column) if expr is None else expr,
        dtype=None,
        source=SourceSpan(
            file="model.py",
            line=11,
            end_line=11,
            function="main",
            statement=f"af.{column} = ...",
            rhs="...",
            target_literal=True,
        ),
        origin="assignment",
    )


class TestTheNameOfAColumnNoLongerChoosesTheAdvice:
    """The shapes the error-path investigation recorded, each raised for real."""

    def test_a_clash_beside_valuation_date_is_not_answered_about_dates(self):
        """A float column called `valuation_date` is not a date, and says so."""
        advice = _advice_without_facts(*_raise_dtype_clash("valuation_date"))

        assert not any(DATE_ADVICE in line for line in advice), advice
        assert not any("to_datetime" in line for line in advice), advice

    def test_a_clash_beside_nan_flag_is_not_answered_about_nulls(self):
        """A float column called `nan_flag` holds no nulls, and says so."""
        advice = _advice_without_facts(*_raise_dtype_clash("nan_flag"))

        assert not any(NULL_ADVICE in line for line in advice), advice

    def test_a_clash_beside_file_path_is_not_answered_about_files(self):
        """A string column called `file_path` is not a file, and says so."""
        advice = _advice_without_facts(*_raise_clash_with_string_named("file_path"))

        assert not any(FILE_ADVICE in line for line in advice), advice

    def test_a_jagged_clash_beside_a_path_column_keeps_the_length_advice(self):
        """The one family whose advice is excellent keeps it, on list operands."""
        af, raised = _raise_jagged_clash_beside_a_path_column()
        advice = _advice(af, raised)

        assert any(JAGGED_ADVICE in line for line in advice), advice
        assert not any(FILE_ADVICE in line for line in advice), advice

    def test_a_lookup_miss_is_answered_about_the_table_it_read(self):
        """A table that stops at 42 is a table problem, not a null problem."""
        advice = _advice_without_facts(*_raise_lookup_miss())

        assert any(LOOKUP_ADVICE in line for line in advice), advice
        assert any("advice_routed_on_facts_mortality" in line for line in advice), (
            advice
        )
        assert not any(NULL_ADVICE in line for line in advice), advice
        assert not any(DATE_ADVICE in line for line in advice), advice


class TestTheOperandDtypesChooseTheRefinement:
    """What the graph says the formula read is what sharpens the advice."""

    def test_a_string_against_a_number_earns_the_cast_advice(self):
        """`str` beside `f64` on the graph, whatever the operands are called."""
        advice = _advice(*_raise_dtype_clash("valuation_date"))

        assert any(CAST_ADVICE in line for line in advice), advice
        assert not any(DATE_ADVICE in line for line in advice), advice

    @pytest.mark.parametrize(
        "numeric_column",
        ["valuation_date", "nan_flag", "missing_count", "parse_order", "plain"],
    )
    def test_one_clash_earns_one_answer_whatever_the_operand_is_called(
        self,
        numeric_column,
    ):
        """Five names for one column, one dtype clash, one answer."""
        under_test = _advice(*_raise_dtype_clash(numeric_column))
        plain = _advice(*_raise_dtype_clash("plain"))

        assert under_test == plain, (numeric_column, under_test, plain)
        assert any(CAST_ADVICE in line for line in under_test), under_test

    def test_a_string_exponent_over_a_list_earns_the_cast_advice_too(self):
        """`af.fund_value ** af.code` is a string used as a power, and is said so.

        It reached this repository's ``list_pow``, which refused, and the
        refusal came back as a ``ComputeError`` carrying no subject -- so
        the panel named the failing column and printed nothing under it.
        A ``str`` beside a column of numbers is the same mistake whether
        the numbers sit one per policy or one per period, and it takes the
        same cast, so the axis they sit on is not allowed to silence the
        line: ``list[f64]`` counts among the numbers for this test. The
        frame's own ``**`` now refuses the pair where it is written, so the
        kernel is reached here as an engine fragment calls it.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "fund_value": [[1000.0, 1100.0], [2000.0, 2200.0]],
                    "code": ["A", "B"],
                },
            ),
        )
        af.accumulated = list_pow(pl.col("fund_value"), pl.col("code"))
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert any(CAST_ADVICE in line for line in advice), advice
        assert not any(JAGGED_ADVICE in line for line in advice), advice

    def test_the_same_kernel_over_two_lists_is_a_length_clash_not_a_cast(self):
        """The falsification: it is the `str` on the graph that moves the answer.

        The identical kernel, the identical class, and a pair of list
        operands rather than a string beside one -- which is a length
        clash and earns the jagged family, not the cast line.
        """
        advice = _advice(*_raise_a_kernel_refusal(beside="nothing"))

        assert any(JAGGED_ADVICE in line for line in advice), advice
        assert not any(CAST_ADVICE in line for line in advice), advice


class TestTheDeletedFamiliesCannotBeReachedByAWord:
    """Null, file and division advice had no structural route and are gone.

    The index family is not among them: a read past a policy's own horizon
    reaches the panel for real, so it came back on a structural route
    (``TestTheIndexFamilyIsRoutedByItsLowering``). Its retired WORDS stay
    retired, and are listed here with the other three.
    """

    RETIRED = (
        NULL_ADVICE,
        FILE_ADVICE,
        "Check for zero values in denominator",
        "Check data length before indexing",
        "Consider using .map_elements()",
    )

    def test_a_message_full_of_the_retired_words_reaches_none_of_them(self):
        """Every trigger word at once, on an ordinary arithmetic record."""
        message = (
            "null values are missing, NaN at a date and time; could not parse "
            "the path; division by zero; index out of bounds"
        )
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ComputeError(message),
            _record(Col("reserve"), column="reserve"),
            ["reserve"],
        )

        for retired in self.RETIRED:
            assert not any(retired in line for line in advice), (retired, advice)


class TestWhatTheRouterDoesWithNoRecord:
    """The strict cast and strict date parse reach the router with nothing."""

    def test_an_invalid_operation_with_no_record_is_answered_with_silence(self):
        """No lowering and no operands: the class alone cannot choose a family."""
        parse_failure = pl.exceptions.InvalidOperationError(
            "conversion from `str` to `date` failed in column 'd' for 1 out "
            'of 1 values: ["nope"]',
        )

        assert ErrorSuggestionEngine().suggest_fixes(parse_failure, None, []) == []

    def test_a_strict_cast_with_no_record_is_answered_with_silence(self):
        """The sibling shape, whose text says `i64` where the other says `date`."""
        cast_failure = pl.exceptions.InvalidOperationError(
            "conversion from `str` to `i64` failed in column 'code' for 1 out "
            'of 1 values: ["nope"]',
        )

        assert ErrorSuggestionEngine().suggest_fixes(cast_failure, None, []) == []


class TestTheParseFamilyIsRoutedByItsLowering:
    """`str.to_date` IS a date parse, whatever the refusal happens to say."""

    def test_a_parse_record_earns_the_format_advice_from_a_wordless_message(self):
        """The message carries no date word; the lowering carries the family."""
        record = _record(Call("str.to_date", (Col("d"),), (("format", "%Y-%m-%d"),)))
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.InvalidOperationError("the operation was refused"),
            record,
            ["d"],
        )

        assert any(DATE_ADVICE in line for line in advice), advice

    def test_an_arithmetic_record_earns_no_format_advice_from_a_dated_message(self):
        """The mirror: polars' own word `date` moves nothing without the verb."""
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.InvalidOperationError(
                "conversion from `str` to `date` failed in column 'd'",
            ),
            _record(Col("reserve"), column="reserve"),
            ["reserve"],
        )

        assert not any(DATE_ADVICE in line for line in advice), advice


class _AnExpressionPolarsWillNotSerialise:
    """Stands in for a lowering polars declines to hand back as JSON.

    The real shape is a ``map_elements`` closure with no pickler
    installed, and pinning it that way rests on an optional dependency
    being ABSENT: install ``cloudpickle`` and the expression serialises,
    the guard is never entered, and the test goes on passing while
    pinning nothing. The refusal is what this family has to survive, so
    it is raised here rather than waited for.
    """

    @property
    def meta(self) -> _AnExpressionPolarsWillNotSerialise:
        """Return self, standing in for the expression's meta namespace."""
        return self

    def serialize(self, **_: object) -> str:
        """Refuse, the way polars refuses a closure it cannot pickle."""
        message = "python: ModuleNotFoundError: No module named 'cloudpickle'"
        raise pl.exceptions.ComputeError(message)


class TestTheIndexFamilyIsRoutedByItsLowering:
    """A read whose index can leave the row's own list is answered, not passed over.

    The family was deleted as unreachable on the reasoning that
    ``OutOfBoundsError`` is not admitted at the one call site. True of
    ``gather``; not true of the read an actuary actually writes.
    ``af.cashflow.list.get(af.term)`` raises an admitted ``ComputeError``,
    is attributed to the column, and builds the panel -- so for one
    release it built the panel and printed nothing under it.

    What selects the family is the read that CAN raise: ``.list.get`` with
    ``null_on_oob`` false. ``list.first()`` and ``list.last()`` are
    ``get(0, null_on_oob=True)`` and ``get(-1, null_on_oob=True)``, so a
    formula that merely contains one is not a formula that can fail this
    way, and answering it here was answering a failure the advice did not
    describe.
    """

    def test_a_period_past_the_policys_horizon_earns_the_index_advice(self):
        """The shape the per-policy default invites, raised for real."""
        af, raised = _raise_index_past_the_horizon()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice

    def test_the_same_shape_earns_it_with_the_graph_never_asked(self):
        """The lowering carries the family; what the caller knows only refines it.

        The two answers were identical until the projection line learned to
        withhold itself. It is offered as a cause to check IF the values
        came from a grid, and this frame has none -- a caller that says so
        (``GraphFacts.projected``) gets the line dropped, and a caller that
        never asked keeps it, because a question nobody put costs the
        refinement rather than the advice. Everything the family says about
        the read itself is the same either way, which is the guarantee this
        test was written for.
        """
        af, raised = _raise_index_past_the_horizon()

        unasked = _advice_without_facts(af, raised)
        asked = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in unasked), unasked
        assert any(INDEX_ADVICE in line for line in asked), asked
        assert [line for line in unasked if PROJECTION_CLAUSE not in line] == asked
        assert any(PROJECTION_CLAUSE in line for line in unasked), unasked
        assert not any(PROJECTION_CLAUSE in line for line in asked), asked

    def test_a_constant_index_past_every_horizon_earns_it_too(self):
        """The same read with the period written as a number, not a column."""
        af = ActuarialFrame(
            pl.DataFrame(
                {"policy_id": [1, 2], "cashflow": [[1.0, 2.0], [3.0, 4.0]]},
            ),
        )
        af.late = af.cashflow.list.get(99)
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert any(INDEX_ADVICE in line for line in advice), advice

    def test_renaming_every_column_moves_only_the_list_the_advice_names(self):
        """The names an actuary chose select no family; one of them is QUOTED.

        The advice names the list the raising read took its element from,
        because a remedy written against an example column is a remedy
        against a column the failing frame need not have. That name is
        read off the read's own receiver in the core op-tree,
        never off the message and never off a family test -- so renaming
        every column in the shape moves exactly that one word and nothing
        else, the family included.
        """
        baseline = _advice(*_raise_index_past_the_horizon())
        assert any(INDEX_ADVICE in line for line in baseline), baseline
        assert any("cashflow" in line for line in baseline), baseline

        for name in ("null", "valuation_date", "file_path", "ListExpr"):
            af, raised = _raise_index_past_the_horizon(
                index_column=name,
                list_column=f"{name}_values",
                target=f"{name}_result",
            )

            advice = _advice(af, raised)

            assert advice == [
                line.replace("cashflow", f"{name}_values") for line in baseline
            ], name
            assert not any(f"{name}_result" in line for line in advice), name

    @pytest.mark.parametrize("beside", ["nothing", "core", "native"])
    def test_a_computed_receiver_is_not_named_after_one_of_its_inputs(
        self, beside: str
    ) -> None:
        """An unnamed read must not borrow a column from a neighbouring read.

        The columns are tested in the BACKTICKS the advice quotes them in,
        not as bare substrings, for the reason ``operands_already_named``
        gives about ``age`` inside ``coverage``: a bare test for ``fixed``
        found the words "fixed width", which is the line describing an
        array's bound and names no column at all.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1],
                    "cashflow": [[10.0, 20.0]],
                    "term": [7],
                    "fixed": pl.Series([[1.0, 2.0]], dtype=pl.Array(pl.Float64, 2)),
                }
            )
        )
        selected = (af.cashflow + 1.0).list.get(af.term)
        if beside == "core":
            selected = selected + af.cashflow.list.get(0)
        elif beside == "native":
            selected = selected + af.fixed.polars_native().arr.get(0)
        af.selected = selected
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert advice[0].startswith("The index must be inside"), advice
        assert "`cashflow`" not in advice[0], advice
        assert "`fixed`" not in advice[0], advice
        assert ".polars_native()" in advice[1], advice

    def test_the_words_of_the_refusal_earn_it_nothing(self):
        """polars' own `index is out of bounds` moves nothing without the read."""
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ComputeError("get index is out of bounds"),
            _record(Col("reserve"), column="reserve"),
            ["reserve"],
        )

        assert not any(INDEX_ADVICE in line for line in advice), advice

    def test_a_shape_error_over_an_indexed_read_is_still_a_jagged_clash(self):
        """An indexed read is a part of a formula, not what the formula is.

        So the classes that name a subject of their own answer first, and
        this family answers the failure they leave. The name says
        ``ShapeError`` because that is the class this one pins; the same
        length clash arriving from a Rust kernel is a ``ComputeError``
        that no class question owns, and the kernel's own symbol answers
        it instead -- which the three tests below pin.
        """
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ShapeError("lengths don't match"),
            _record(
                Col("discounted"),
                column="discounted",
                expr=pl.col("cashflow").list.get(0) * pl.col("curve"),
            ),
            ["discounted"],
        )

        assert any(JAGGED_ADVICE in line for line in advice), advice
        assert not any(INDEX_ADVICE in line for line in advice), advice

    def test_a_kernel_refusal_beside_a_read_that_cannot_raise_is_the_jagged_clash(self):
        """A healthy `list.first()` is not what failed, and does not answer for it.

        The framework's own ``**`` kernel refusing a mismatched jagged
        pair is not an index failure at all: nothing ran off a list, and
        the read that used to select the index family --
        ``af.fund_value.list.first()`` -- is ``get(0, null_on_oob=True)``
        and cannot raise out of bounds.

        It is a LENGTH clash, though, and for one release it earned
        nothing, because polars hands a plugin's refusal back as a
        ``ComputeError`` and no class owned it. Written with ``*`` the
        identical mismatch raises ``ShapeError`` and earns three useful
        lines; written with ``**`` it went through this repository's
        ``list_pow`` and earned silence. The kernel's own symbol in the
        lowering says the operands clashed, so both spellings reach the
        one family now.
        """
        af, raised = _raise_a_kernel_refusal(beside="a read that cannot raise")

        advice = _advice(af, raised)

        assert any(JAGGED_ADVICE in line for line in advice), advice
        assert not any(INDEX_ADVICE in line for line in advice), advice

    def test_the_kernel_refusal_answers_the_same_with_and_without_that_read(self):
        """One failure, one answer: an incidental read must not flip it.

        The identical refusal with nothing beside it earns the same
        family. A router that answered one and not the other was keyed on
        what the formula happened to contain rather than on what failed in
        it.
        """
        alone = _advice(*_raise_a_kernel_refusal(beside="nothing"))
        beside = _advice(*_raise_a_kernel_refusal(beside="a read that cannot raise"))

        assert any(JAGGED_ADVICE in line for line in alone), alone
        assert beside == alone, (beside, alone)

    def test_the_two_spellings_of_one_jagged_clash_are_answered_alike(self):
        """A jagged pair says the same thing under `*` and under `**`.

        The mismatch is one mismatch and which operator the actuary
        reached for decided, for one release, whether they were told
        anything at all. ``*`` raises polars' ``ShapeError`` and earned
        three lines; ``**`` goes through this repository's ``list_pow``,
        comes back as a ``ComputeError`` carrying no subject, and earned
        an empty suggestion list under a panel that had named the failing
        column.
        """
        multiplied = _advice(*_raise_jagged_clash_beside_a_path_column())
        raised_to = _advice(*_raise_a_kernel_refusal(beside="nothing"))

        assert any(JAGGED_ADVICE in line for line in multiplied), multiplied
        assert raised_to == multiplied, (raised_to, multiplied)

    @pytest.mark.parametrize(
        "expr",
        [
            pl.col("fund_value").list.first(),
            pl.col("fund_value").list.last(),
            pl.col("fund_value").list.get(pl.col("term"), null_on_oob=True),
            pl.col("cashflow").arr.first(),
            pl.col("cashflow").arr.last(),
            pl.col("cashflow").arr.get(pl.col("term"), null_on_oob=True),
        ],
        ids=[
            "first",
            "last",
            "null_on_oob",
            "arr_first",
            "arr_last",
            "arr_null_on_oob",
        ],
    )
    def test_a_read_that_cannot_go_out_of_bounds_is_not_an_index_failure(self, expr):
        """`null_on_oob=True` reads a null where the element is missing.

        So it can never be the read this family is about, whatever else
        the calculation went on to do. The array reads are here for the
        same reason as the list ones: admitting ``.arr.get`` admits the
        read that RAISES, and ``arr.first()``/``arr.last()`` carry the
        flag true exactly as their list siblings do.
        """
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ComputeError("the plugin failed with message: ..."),
            _record(Col("accumulated"), column="accumulated", expr=expr),
            ["accumulated"],
        )

        assert advice == [], advice

    def test_a_kernel_refusal_beside_a_raising_read_is_answered_about_the_clash(self):
        """The shape that used to answer about the wrong half of the formula.

        ``af.fund_value.list.get(0) * (af.growth_factor ** af.fund_value)``
        on a pair where ``fund_value`` holds two elements in every row:
        the ``.get(0)`` is in range on every row and cannot be what
        failed, and the ``**`` is the jagged pair that did. The panel gave
        three lines about index bounds, naming ``fund_value`` -- a column
        whose read was fine -- because the read that CAN raise was asked
        about before anything asked what refused.

        The kernel's own symbol is the fact that separates them, and it is
        asked first now: a formula lowered onto one of this repository's
        list kernels is answered about the operands that kernel was handed.
        """
        af, raised = _raise_a_kernel_refusal(beside="a read that could raise")

        advice = _advice(af, raised)

        assert any(JAGGED_ADVICE in line for line in advice), advice
        assert not any(INDEX_ADVICE in line for line in advice), advice
        assert not any("`fund_value`" in line for line in advice), advice

    def test_the_index_family_still_answers_a_read_with_no_kernel_beside_it(self):
        """The same in-range `.get(0)` with nothing that can refuse next to it.

        The falsification for the test above: it is the KERNEL that moves
        the answer, not the presence of a second operand. The identical
        read multiplied by an ordinary list column reaches the index
        family, because nothing in that formula is one of this
        repository's kernels.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "fund_value": [[1000.0, 1100.0], [2000.0, 2200.0]],
                    "growth_factor": [[1.05, 1.05], [1.05]],
                },
            ),
        )
        af.accumulated = af.fund_value.list.get(2) * af.growth_factor
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("`fund_value`" in line for line in advice), advice

    def test_a_ragged_input_list_is_not_told_it_outran_a_projection(self):
        """A list off the extract has no projection to have run past.

        Rider sums assured indexed at a rider count: no timeline, no
        ``projection.set``, and no column called ``cashflow`` for a
        remedy to be written against.
        """
        af, raised = _raise_a_ragged_input_list_read_past_its_end()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("rider_sum_assured" in line for line in advice), advice
        for withdrawn in WITHDRAWN_INDEX_CLAUSES:
            assert not any(withdrawn in line for line in advice), (withdrawn, advice)

    def test_an_index_off_the_start_is_not_told_it_ran_past_the_end(self):
        """`list.get(-5)` reached back past the start, which is the other end."""
        af, raised = _raise_an_index_off_the_start()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("negative index" in line for line in advice), advice
        for withdrawn in WITHDRAWN_INDEX_CLAUSES:
            assert not any(withdrawn in line for line in advice), (withdrawn, advice)

    def test_a_count_used_as_an_index_is_told_the_boundary_it_crossed(self):
        """A list of three read at three: the shape the old clause answered wrong.

        "raises where a row's list is shorter than the index asked for"
        is off by one at the equality boundary, and the boundary is where
        this failure lives -- an actuary writes the count and reads at
        it. The line now states the arithmetic instead, and the
        arithmetic is executed in ``TestTheAdvisedRemediesRun``.
        """
        af, raised = _raise_a_count_used_as_an_index()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("rider_premium" in line for line in advice), advice
        assert any(BOUNDARY_CLAUSE in line for line in advice), advice
        assert not any(OFF_BY_ONE_CLAUSE in line for line in advice), advice

    def test_a_row_holding_no_elements_is_not_told_its_last_index_is_minus_one(self):
        """The old clause names nothing at all on a row holding no elements.

        A row whose list is empty has length zero, and an actuary who
        subtracts one from it reaches an index that is not merely invalid
        but, written the obvious way, not even negative -- see
        ``TestTheAdvisedRemediesRun``. The boundary line states the empty
        row outright instead of leaving it to arithmetic that does not
        work there.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {"policy_id": [1, 2], "n": [0, 1], "cf": [[], [1.0, 2.0]]},
                schema={
                    "policy_id": pl.Int64,
                    "n": pl.Int64,
                    "cf": pl.List(pl.Float64),
                },
            ),
        )
        af.picked = af.cf.list.get(af.n)
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any(EMPTY_ROW_CLAUSE in line for line in advice), advice
        assert not any(ROW_LENGTH_CLAUSE in line for line in advice), advice

    def test_a_fixed_width_array_read_past_its_end_earns_the_same_family(self):
        """`.arr.get` past the width is the same failure and is answered like one.

        Same class, same message, and a serialised payload one key from
        the list read's. It earned nothing at all until this ride, which
        was conspicuous rather than harmless once the family became
        precise about which reads it answers. The lines name ``.arr.get``:
        a remedy written against ``.list.get`` is a remedy against a call
        this formula does not contain.

        The BOUND they name is the array's own, and the difference is not
        cosmetic. "One less than that row's own length" is wrong of an
        ``Array``: the width is declared once for the column, every row
        has it, and a row whose value is null has no length at all while
        the read is still bounded by that width.
        """
        af, raised = _raise_past_a_fixed_width_array()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("cashflow" in line for line in advice), advice
        assert any(".arr.get" in line for line in advice), advice
        assert all(".list.get(" not in line for line in advice), advice
        assert any(ARRAY_BOUND_CLAUSE in line for line in advice), advice
        assert not any(ROW_LENGTH_CLAUSE in line for line in advice), advice

    def test_an_array_read_is_not_offered_a_projection_as_the_cause(self):
        """A projection builds `List` columns, so it cannot have built an `Array`.

        The line was offered to every read this family answers, array
        included, where it could never be true: ``projection.set(...)``
        materialises ``month`` and every timeline beside it as ``List``.
        An actuary sent to check `until`/`until_value` over a fixed-width
        column read a cause that is not available to them.

        The frame here really does carry a grid -- ``projected`` is
        measured True on it -- so the array's own fact is the only thing
        that can withhold the line, and this test fails if it stops
        doing so.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "issue_age": [40, 55],
                    "policy_term": [30, 10],
                    "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
                },
                schema={
                    "policy_id": pl.Int64,
                    "issue_age": pl.Int64,
                    "policy_term": pl.Int64,
                    "cashflow": pl.Array(pl.Float64, 3),
                },
            ),
        )
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="maximum_age",
            until_value=60,
            frequency="annual",
        )
        af.final_cf = af.cashflow.polars_native().arr.get(af.policy_term)
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()
        record, _ = _attributed(af, caught.value)
        assert graph_facts(af, record).projected is True

        advice = _advice(af, caught.value)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert not any(PROJECTION_CLAUSE in line for line in advice), advice

    def test_a_frame_with_no_projection_is_not_offered_one_as_the_cause(self):
        """The grid line is withheld where the frame is known to have no grid.

        It used to close every panel this family built, because the router
        could not see the frame. It can now: ``graph_facts`` is handed the
        frame at the one call site, and carries whether it holds a
        ``Schedule`` at all. A ragged rider list off a model-point extract
        has none.
        """
        af, raised = _raise_a_ragged_input_list_read_past_its_end()
        assert af._projection is None  # noqa: SLF001 -- the fact under test

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert not any(PROJECTION_CLAUSE in line for line in advice), advice

    def test_a_read_inside_list_eval_earns_the_family_too(self):
        """The same out-of-bounds read, written inside `list.eval`.

        ``af.cashflow.polars_native().list.eval(pl.element().get(7))``
        raises the identical ``ComputeError: get index is out of bounds``
        a direct read raises, and earned nothing, because it serialises as
        an ``Eval`` carrying a ``Gather`` rather than as a ``function``
        slot -- a distinction the actuary who wrote the line cannot see.
        The flag it carries is the same ``null_on_oob``, so the same
        question answers it, and the advice quotes the call the formula
        actually holds.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {"policy_id": [1, 2], "cashflow": [[1.0, 2.0], [3.0, 4.0]]},
            ),
        )
        af.picked = af.cashflow.polars_native().list.eval(pl.element().get(7))
        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()

        advice = _advice(af, caught.value)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("`cashflow`" in line for line in advice), advice
        assert any("pl.element().get(...)" in line for line in advice), advice
        assert all(".list.get(" not in line for line in advice), advice

    def test_an_eval_that_cannot_go_out_of_bounds_earns_nothing(self):
        """`pl.element().first()` inside the same `list.eval` reads a null.

        The falsification for the test above: it is the ``Gather``'s own
        ``null_on_oob`` that selects the family, not the presence of an
        ``Eval``. An aggregation in the evaluation slot cannot raise out
        of bounds and is not answered.
        """
        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ComputeError("the plugin failed with message: ..."),
            _record(
                Col("picked"),
                column="picked",
                expr=pl.col("cashflow").list.eval(pl.element().first()),
            ),
            ["picked"],
        )

        assert advice == [], advice

    def test_a_real_projection_grid_is_not_called_a_per_policy_horizon(self):
        """The one test here whose timeline `projection.set` actually built.

        A whole term lays ONE grid, so both lives get the same 21
        boundaries and no policy stops at a horizon of its own. The grid
        line survives as the cause to check, conditionally; the per-policy
        explanation does not survive at all.

        The uniformity is MEASURED here, off the state the panel itself
        prints, rather than left in the fixture's docstring: a life aged
        40 and one aged 55 on the same grid, and the whole reason this
        shape is in the file is that their timelines are the same length.
        """
        af, raised = _raise_past_a_real_projection_grid()

        _, last_good = search_collect_failure(af, raised)
        assert last_good is not None
        periods = last_good.select(pl.col("month").list.len()).to_series().to_list()
        assert periods == [21, 21], periods

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        assert any("until`/`until_value" in line for line in advice), advice
        for withdrawn in WITHDRAWN_INDEX_CLAUSES:
            assert not any(withdrawn in line for line in advice), (withdrawn, advice)

    def test_the_retired_row_count_lines_did_not_come_back(self):
        """The family returned; its words about the frame's height did not."""
        af, raised = _raise_index_past_the_horizon()

        advice = _advice(af, raised)

        assert any(INDEX_ADVICE in line for line in advice), advice
        for retired in RETIRED_INDEX_LINES:
            assert not any(retired in line for line in advice), (retired, advice)

    def test_every_line_the_family_gives_is_a_line_the_panel_prints(self):
        """Three lines, because the panel prints three.

        ``FriendlyErrorFormatter`` renders ``suggestions[:3]``, so a
        fourth line would be built, counted by a test that reads the
        router's return value, and never read by anybody. This pins the
        family against the surface that shows it rather than against the
        list it returns.
        """
        af, raised = _raise_index_past_the_horizon()
        record, last_good = search_collect_failure(af, raised)
        assert isinstance(record, CalculationRecord), record
        assert last_good is not None
        facts = graph_facts(af, record)
        advice = ErrorSuggestionEngine().suggest_fixes(
            raised,
            record,
            list(last_good.columns),
            facts,
        )

        panel = FriendlyErrorFormatter(
            record=record,
            exception=raised,
            last_good_df=last_good,
            suggestions=advice,
            facts=facts,
        ).format_error()

        assert advice, advice
        for line in advice:
            assert line in panel, line

    def test_an_expression_polars_declines_to_serialise_costs_nothing(self):
        """A lowering it will not hand back reaches the silence it reached before."""
        stand_in = _AnExpressionPolarsWillNotSerialise()
        with pytest.raises(pl.exceptions.ComputeError):
            stand_in.meta.serialize(format="json")

        advice = ErrorSuggestionEngine().suggest_fixes(
            pl.exceptions.ComputeError("the plugin refused"),
            _record(
                Col("reserve"),
                column="reserve",
                expr=cast("pl.Expr", stand_in),
            ),
            ["reserve"],
        )

        assert advice == []


class TestTheAdvisedRemediesRun:
    """Each remedy the index family offers, executed on the failure it answers.

    A line that string-matches is a line nobody ran. Both of these were
    written from the advice and collected: the model that raised now
    returns figures.
    """

    def test_the_advised_null_on_oob_reads_a_null_where_the_period_is_missing(self):
        """`null_on_oob=True` on the failing read, run end to end."""
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "term": [1, 7],
                    "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0]],
                },
            ),
        )
        af.final_cf = af.cashflow.polars_native().list.get(af.term, null_on_oob=True)

        assert af.collect().select("final_cf").to_series().to_list() == [11.0, None]

    def test_the_advised_null_on_oob_survives_a_row_holding_no_elements(self):
        """The one remedy true of every row, run on the row that breaks the other.

        This is why ``null_on_oob=True`` leads the remedy line and the
        clamp follows it carrying a condition. An empty list row has no
        valid index at all, so nothing can be clamped to it; the read
        with the flag returns a null there and collects.
        """
        af = ActuarialFrame(
            pl.DataFrame(
                {"policy_id": [1, 2], "n": [0, 1], "cf": [[], [1.0, 2.0]]},
                schema={
                    "policy_id": pl.Int64,
                    "n": pl.Int64,
                    "cf": pl.List(pl.Float64),
                },
            ),
        )
        af.picked = af.cf.polars_native().list.get(af.n, null_on_oob=True)

        assert af.collect().select("picked").to_series().to_list() == [None, 2.0]

    def test_the_remedy_line_leads_with_the_flag_and_conditions_the_clamp(self):
        """The order and the condition, read off the line the panel prints.

        ``null_on_oob=True`` first because it is the one remedy true of
        every row, and the clamp behind it naming the unsigned count that
        makes it unsafe on a row holding no elements. The arithmetic of
        that underflow is executed in the test below.
        """
        advice = _advice(*_raise_a_count_used_as_an_index())

        remedy = next(line for line in advice if NULL_ON_OOB_CLAUSE in line)
        assert EMPTY_ROW_CLAMP_CLAUSE in remedy, remedy
        leads = remedy.index(NULL_ON_OOB_CLAUSE)
        assert leads < remedy.index(EMPTY_ROW_CLAMP_CLAUSE), remedy

    def test_the_clamp_the_line_used_to_advise_unconditionally_has_no_index(self):
        """`len() - 1` is -1 on an empty row, and no index is there to read.

        The remedy line used to say "clamp the INDEX" with no condition on
        it. An actuary writing that clamp the obvious way reaches the
        row's own length and subtracts one. ``.list.len()`` is unsigned,
        and that subtraction used to wrap to 18446744073709551615 on a row
        holding no elements; the frame now reads the count as the i64 it
        fits, so the row answers -1 (an i64 line never wraps). Both halves
        are executed here: the value lands in the frame, and the clamp
        built from it fails at the run, because an empty row has no index
        for it to reach.

        So the line says to clamp only where every row holds an element, and
        names the empty row as the reason. Advice that steers into this is
        worse than advice that steers nowhere.
        """
        rows = {"policy_id": [1, 2], "n": [0, 5], "cf": [[], [1.0, 2.0]]}
        schema = {
            "policy_id": pl.Int64,
            "n": pl.Int64,
            "cf": pl.List(pl.Float64),
        }
        wrapped = ActuarialFrame(pl.DataFrame(rows, schema=schema))
        wrapped.last_index = wrapped.cf.polars_native().list.len() - 1

        collected = wrapped.collect()
        assert collected.schema["last_index"] == pl.Int64
        assert collected.select("last_index").to_series().to_list() == [-1, 1]

        clamped = ActuarialFrame(pl.DataFrame(rows, schema=schema))
        clamped.last_index = clamped.cf.polars_native().list.len() - 1
        clamped.picked = clamped.cf.list.get(clamped.last_index)
        with pytest.raises(pl.exceptions.ComputeError, match="out of bounds"):
            clamped.collect()

    def test_a_guard_around_the_read_still_raises_and_the_clamp_does_not(self):
        """Why the line says clamp the INDEX rather than guard the read.

        polars evaluates both branches of a ``when/then/otherwise``, so
        the guard an actuary writes from the framework's own conditional
        idiom reproduces the failure it was written to prevent. The same
        condition moved INSIDE ``.list.get(...)`` collects.
        """
        guarded = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "term": [1, 7],
                    "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0]],
                },
            ),
        )
        guarded.horizon = guarded.cashflow.polars_native().list.len()
        guarded.final_cf = (
            when(guarded.term < guarded.horizon)
            .then(guarded.cashflow.list.get(guarded.term))
            .otherwise(None)
        )
        with pytest.raises(pl.exceptions.ComputeError):
            guarded.collect()

        clamped = ActuarialFrame(
            pl.DataFrame(
                {
                    "policy_id": [1, 2],
                    "term": [1, 7],
                    "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0]],
                },
            ),
        )
        clamped.horizon = clamped.cashflow.polars_native().list.len()
        clamped.final_cf = clamped.cashflow.list.get(
            when(clamped.term < clamped.horizon)
            .then(clamped.term)
            .otherwise(clamped.horizon - 1),
        )

        assert clamped.collect().select("final_cf").to_series().to_list() == [
            11.0,
            21.0,
        ]

    def test_the_boundary_the_line_states_is_the_boundary_the_read_has(self):
        """The arithmetic line 1 gives, executed at both sides of the boundary.

        The line says the last valid index is one less than that row's
        own length. One frame, two reads: at the count it raises, at the
        count less one it returns the last element. This is the shape a
        clause about lists "shorter than the index" answered wrongly.
        """
        rows = {
            "policy_id": [1, 2],
            "n_riders": [3, 3],
            "rider_premium": [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
        }
        past_the_end = ActuarialFrame(pl.DataFrame(rows))
        past_the_end.last_rider = past_the_end.rider_premium.list.get(
            past_the_end.n_riders,
        )
        with pytest.raises(pl.exceptions.ComputeError):
            past_the_end.collect()

        inside = ActuarialFrame(pl.DataFrame(rows))
        inside.last_rider = inside.rider_premium.list.get(inside.n_riders - 1)

        assert inside.collect().select("last_rider").to_series().to_list() == [
            12.0,
            22.0,
        ]

    def test_both_remedies_run_on_a_fixed_width_array_too(self):
        """The lines an `.arr.get` failure now earns, run on the array itself.

        Admitting the array read means advising ``null_on_oob=True`` and
        the clamp for a call the family had never answered. Both are
        collected here, and the guard around the read raises on an array
        exactly as it does on a list -- so line 2's trap clause is true
        of the shape it is now shown to.
        """
        rows = {
            "policy_id": [1, 2],
            "term": [1, 7],
            "cashflow": [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
        }
        schema = {
            "policy_id": pl.Int64,
            "term": pl.Int64,
            "cashflow": pl.Array(pl.Float64, 3),
        }
        nulled = ActuarialFrame(pl.DataFrame(rows, schema=schema))
        nulled.final_cf = nulled.cashflow.polars_native().arr.get(
            nulled.term, null_on_oob=True
        )

        assert nulled.collect().select("final_cf").to_series().to_list() == [
            11.0,
            None,
        ]

        guarded = ActuarialFrame(pl.DataFrame(rows, schema=schema))
        guarded.width = guarded.cashflow.polars_native().arr.len()
        guarded.final_cf = (
            when(guarded.term < guarded.width)
            .then(guarded.cashflow.polars_native().arr.get(guarded.term))
            .otherwise(None)
        )
        with pytest.raises(pl.exceptions.ComputeError):
            guarded.collect()

        clamped = ActuarialFrame(pl.DataFrame(rows, schema=schema))
        clamped.width = clamped.cashflow.polars_native().arr.len()
        clamped.final_cf = clamped.cashflow.polars_native().arr.get(
            when(clamped.term < clamped.width)
            .then(clamped.term)
            .otherwise(clamped.width - 1),
        )

        assert clamped.collect().select("final_cf").to_series().to_list() == [
            11.0,
            22.0,
        ]
