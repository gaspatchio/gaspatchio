# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The attribution block names what the failure blocks and what it was reading.

The block appended to a collect-time error named the column, quoted the
line and said where it was written, and stopped there. The frame's own
calculation graph already knows two more things about that column: every
column downstream of it -- the reported figures this one failure means
cannot be produced -- and the columns its formula read, each with the dtype
the frame holds it at. Both are one question to ``af.graph`` and the graph
is folded once and cached against the calculation log, so a later question
on the same frame pays nothing.

Two lines join the block. ``Blocks:`` is ``af.graph.affected`` minus the
failing node itself, capped at four names with a ``(+N more)`` tail so a
wide model does not print a wall, and it says ``nothing downstream`` when
the walk finds nothing rather than going quiet -- so the line's absence
means exactly one thing, that the graph could not answer. ``Reading:`` is
``af.graph.precedents`` with each node's dtype printed as the graph holds
it, ``unknown`` included and never guessed; it is left out when the
failure's own diagnosis already quotes every operand, which a polars dtype
refusal does and a jagged-list clash does not.

Every graph call sits inside ``_rendered_attribution``'s guard, and each
question is guarded on its own as well: a question that raises costs its
line and nothing else, the block still prints, and the user's error arrives
alone. The refusal line gains nothing here. ``format_for_llm`` carries the
same two facts as ``blocks`` and ``reading``, structured.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.errors import __all__ as errors_exports
from gaspatchio.errors.formatter import FriendlyErrorFormatter
from gaspatchio.errors.formatting_errors import _attribution_block
from gaspatchio.frame.graph import calc_graph
from gaspatchio.frame.graph.calc_graph import GraphFrameAccessor

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio.frame.calculations import CalculationRecord

# The graph-facts surface this file pins is imported inside the tests that
# read it, so that at a package without it the behaviour pins above still
# collect and fail on behaviour rather than the whole file failing to import.

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what the block carries.
NAMED = "Failing column:"
REFUSAL = "Not attributed:"
BLOCKS = "Blocks:"
READING = "Reading:"
UNNAMED = "Graph:"

# Where every value in the block starts, as the block itself pads it.
_GUTTER = " " * len("  Failing column: ")


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _line(message: str, label: str) -> str:
    """Return the block's one ``label`` line, stripped of its indent."""
    lines = [line for line in message.splitlines() if line.strip().startswith(label)]
    assert len(lines) == 1, f"expected exactly one {label} line in:\n{message}"
    return lines[0].strip()


def _arrived_alone(raised: BaseException, *foreign: str) -> None:
    """Assert ``raised`` carries no chained error and no foreign text."""
    assert raised.__context__ is None
    assert raised.__cause__ is None
    rendered = "".join(traceback.format_exception(raised))
    assert "another exception occurred" not in rendered
    for text in foreign:
        assert text not in rendered


# --- the shapes -------------------------------------------------------------


def _dtype_chain() -> ActuarialFrame:
    """Build a string times a float, with three reported figures downstream of it."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "product_code": ["TERM", "WL"],
                "sum_assured": [100.0, 200.0],
            }
        )
    )
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    af.reserve = af.reserve_factor * 2.0
    af.net_cashflow = af.reserve + 1.0
    af.solvency_margin = af.net_cashflow - 1.0
    return af


def _jagged() -> ActuarialFrame:
    """Build a ragged list multiply, alone: nothing downstream, operands unnamed."""
    af = ActuarialFrame(
        pl.DataFrame({"six": [[1.0] * 6], "three": [[1.0] * 3]}),
    )
    af.mismatched = af.six * af.three
    return af


def _lookup_on_an_expression_key() -> ActuarialFrame:
    """Build a lookup keyed on a sum; the miss names the key, not both operands."""
    table = Table(
        name="graph_eyes_expression_key",
        source=pl.DataFrame({"age": [30, 40], "rate": [0.1, 0.2]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"issue_age": [30, 99], "dur": [0, 0]}))
    af.rate = table.lookup(age=af.issue_age + af.dur)
    return af


# --- Blocks: ----------------------------------------------------------------


def test_the_block_names_what_the_failure_blocks() -> None:
    """The three reported figures downstream of the break are named, in order."""
    message = str(_failure(_dtype_chain()))

    assert NAMED in message
    assert _line(message, BLOCKS) == (
        "Blocks:         reserve@1, net_cashflow@1, solvency_margin@1"
    )


def test_the_blocks_line_is_capped_at_four_names() -> None:
    """A wide model gets four names and a count, not a wall."""
    af = ActuarialFrame(
        pl.DataFrame({"product_code": ["TERM"], "sum_assured": [100.0]})
    )
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    for index in range(1, 7):
        setattr(af, f"figure_{index}", af.reserve_factor * float(index))

    message = str(_failure(af))

    assert _line(message, BLOCKS) == (
        "Blocks:         figure_1@1, figure_2@1, figure_3@1, figure_4@1 (+2 more)"
    )


def test_a_failure_nothing_reads_says_so() -> None:
    """The line is present and says nothing is downstream, rather than absent."""
    message = str(_failure(_jagged()))

    assert _line(message, BLOCKS) == "Blocks:         nothing downstream"


def test_the_blocks_line_sits_under_the_at_line_in_the_blocks_column() -> None:
    """The new lines keep the block one column, after ``At:``."""
    lines = str(_failure(_dtype_chain())).splitlines()
    at = next(i for i, line in enumerate(lines) if line.strip().startswith("At:"))

    assert lines[at + 1].startswith(f"  {BLOCKS}")
    assert lines[at + 1].index("reserve@1") == len(_GUTTER)


# --- Reading: ---------------------------------------------------------------


def test_the_block_names_the_operands_and_their_dtypes() -> None:
    """A jagged clash names nothing itself, so the block names both lists."""
    message = str(_failure(_jagged()))

    assert (
        _line(message, READING) == "Reading:        six (list[f64]), three (list[f64])"
    )


def test_reading_is_left_out_when_the_diagnosis_already_names_every_operand() -> None:
    """Polars' dtype refusal quotes both columns; restating them is noise."""
    raised = _failure(_dtype_chain())
    diagnosis = str(raised).split("\n", 1)[0]

    # The premise, asserted: the first line quotes both operands.
    assert "'product_code'" in diagnosis
    assert "'sum_assured'" in diagnosis

    assert NAMED in str(raised)
    assert READING not in str(raised)


def test_reading_is_printed_when_the_diagnosis_names_only_some_operands() -> None:
    """A lookup miss names the key column; the other operand is the graph's to add."""
    raised = _failure(_lookup_on_an_expression_key())
    diagnosis = str(raised).split("\n", 1)[0]

    assert "'issue_age'" in diagnosis
    assert "'dur'" not in diagnosis
    assert _line(str(raised), READING) == "Reading:        issue_age (i64), dur (i64)"


def test_an_unknown_dtype_is_printed_as_unknown() -> None:
    """The graph holds ``unknown`` for a node it could not resolve; so does the line.

    Rendered from the record and the frame's own graph rather than from a
    collect failure: the failing calculation here is ``reserve_factor``, and
    the record whose operand is unresolved is the one that reads it.
    """
    from gaspatchio.errors.formatter import Operand, graph_facts

    af = _dtype_chain()
    reserve = next(
        record
        for record in af._calculations  # noqa: SLF001 -- the record under test
        if record.column == "reserve"
    )

    facts = graph_facts(af, reserve)
    block = _attribution_block(reserve, facts)

    assert facts.reading == (Operand("reserve_factor@1", "reserve_factor", "unknown"),)
    assert _line(block, READING) == "Reading:        reserve_factor@1 (unknown)"


def test_the_naming_rule_reads_the_leading_line_only() -> None:
    """What polars appends names every column; only the leading line counts.

    The expression the error occurred in and the plan dump both quote the
    operands of a jagged clash, and reading either would silence the line
    for exactly the failure that needs it.
    """
    from gaspatchio.errors.formatter import Operand, operands_already_named

    reading = (
        Operand("six", "six", "list[f64]"),
        Operand("three", "three", "list[f64]"),
    )
    with_expression = (
        "list lengths differed at index 0: 6 != 3\n\n"
        "This error occurred in the following expression:\n"
        '\t[(col("six")) * (col("three"))]'
    )
    with_dump = (
        "list lengths differed\n\nResolved plan until failure:\n"
        " col('six') col('three')"
    )

    assert not operands_already_named(with_expression, reading)
    assert not operands_already_named(with_dump, reading)
    assert operands_already_named("cannot add 'six' to 'three'", reading)
    assert operands_already_named('cannot add "six" to "three"\n col(\'six\')', reading)
    assert not operands_already_named("cannot add 'six' to it", reading)
    assert not operands_already_named("cannot add 'six' to 'three'", ())


# --- the guard: each question raises, the block prints without its line -----


def _raising(*_args: object, **_kwargs: object) -> tuple[str, ...]:
    msg = "the graph broke"
    raise RuntimeError(msg)


def test_a_raising_affected_costs_the_blocks_line_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``affected`` forced to raise: no ``Blocks:``, the rest of the block stands."""
    monkeypatch.setattr(GraphFrameAccessor, "affected", _raising)

    raised = _failure(_jagged())
    message = str(raised)

    assert NAMED in message
    assert BLOCKS not in message
    assert READING in message
    _arrived_alone(raised, "the graph broke")


def test_a_raising_precedents_costs_the_reading_line_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``precedents`` forced to raise: no ``Reading:``, the rest of the block stands."""
    monkeypatch.setattr(GraphFrameAccessor, "precedents", _raising)

    raised = _failure(_jagged())
    message = str(raised)

    assert NAMED in message
    assert BLOCKS in message
    assert READING not in message
    _arrived_alone(raised, "the graph broke")


def test_a_raising_fold_costs_both_lines_and_leaves_todays_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fold itself forced to raise: the block is the one shipped before."""
    monkeypatch.setattr(calc_graph, "fold", _raising)

    raised = _failure(_jagged())
    message = str(raised)

    assert NAMED in message
    assert "Defined as:     af.six * af.three" in message
    assert BLOCKS not in message
    assert READING not in message
    _arrived_alone(raised, "the graph broke")


def test_a_record_the_graph_does_not_hold_gets_todays_block() -> None:
    """A record with no node -- the graph refuses it -- costs both lines only.

    ``projected`` is the frame's own fact rather than the graph's, so it
    still answers on a frame the graph could say nothing about: this
    stranger holds no projection schedule, and ``False`` is what the
    advice router needs to withhold a grid it knows is not there. A
    refusal that is not the graph's dtype vocabulary carries no move for
    the reader and leaves ``unnamed`` empty.
    """
    from gaspatchio.errors.formatter import GraphFacts, graph_facts

    af = _jagged()
    record = next(iter(af._calculations))  # noqa: SLF001 -- the record under test
    stranger = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))

    facts = graph_facts(stranger, record)

    assert facts == GraphFacts(blocks=None, reading=None, projected=False, unnamed=None)
    assert BLOCKS not in _attribution_block(record, facts)
    assert READING not in _attribution_block(record, facts)
    assert "Graph:" not in _attribution_block(record, facts)


# --- a type the graph cannot name -------------------------------------------


def _fixed_width_array() -> ActuarialFrame:
    """Read past the width of a `pl.Array` column, which the graph cannot name."""
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
        )
    )
    af.final_cf = af.cashflow.polars_native().arr.get(af.term)
    return af


def test_an_array_column_gets_the_graphs_refusal_instead_of_two_missing_lines() -> None:
    """A type the vocabulary has no name for loses both lines; the reason arrives.

    ``graph_facts`` asks two questions and a fixed-width ``Array`` refuses
    both with the same ``UnmappedDtypeError``, so the panel was two lines
    poorer on an array than on the identical list and said nothing about
    why -- the refusal went to a debug log the reader of the panel never
    sees. It names the column, says the vocabulary cannot name its type,
    and ends with the conversion that carries it, so it is printed where
    the two lines would have been.
    """
    message = str(_failure(_fixed_width_array()))

    assert NAMED in message
    assert BLOCKS not in message
    assert READING not in message
    assert UNNAMED in message
    assert "has type Array" in message
    assert ".to_list()" in message


def test_the_refusal_line_does_not_displace_a_graph_answer() -> None:
    """The falsification: a frame the graph CAN name keeps its two lines.

    The refusal takes the place of the two lines only where there are no
    two lines. A list column is in the vocabulary, so nothing is unnamed
    and nothing is printed about naming.
    """
    message = str(_failure(_jagged()))

    assert BLOCKS in message
    assert READING in message
    assert UNNAMED not in message


def test_the_verbose_panel_carries_the_refusal_too() -> None:
    """The traced run's panel prints it on the same rule the block does."""
    af = _fixed_width_array()
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator

    message = str(_failure(af))

    assert "❌ Calculation Error" in message
    assert BLOCKS not in message
    assert READING not in message
    assert UNNAMED in message
    assert ".to_list()" in message


# --- the refusal gains nothing ----------------------------------------------


def test_the_refusal_line_gains_neither_line() -> None:
    """Two definitions reproduce; the one-line refusal stays one line."""
    table = Table(
        name="graph_eyes_refusal",
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"issue_age": [30, 40], "dur_a": [0, 59], "dur_b": [69, 0]})
    )
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    message = str(_failure(af))

    assert REFUSAL in message
    assert NAMED not in message
    assert BLOCKS not in message
    assert READING not in message


# --- the fold is paid once --------------------------------------------------


def test_the_error_path_folds_once_and_a_later_question_pays_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph is cached against the log; the block's fold is the only fold."""
    folds: list[int] = []
    real_fold = calc_graph.fold

    def _counting(frame: ActuarialFrame, *, refuse_unnamed: bool) -> object:
        folds.append(1)
        return real_fold(frame, refuse_unnamed=refuse_unnamed)

    monkeypatch.setattr(calc_graph, "fold", _counting)
    af = _dtype_chain()

    message = str(_failure(af))
    assert BLOCKS in message
    assert len(folds) == 1

    assert af.graph.precedents("reserve_factor") == ("product_code", "sum_assured")
    assert af.graph.affected("reserve") == (
        "reserve@1",
        "net_cashflow@1",
        "solvency_margin@1",
    )
    assert len(folds) == 1


# --- the structured fields --------------------------------------------------


def _record_of(af: ActuarialFrame, column: str) -> CalculationRecord:
    return next(
        record
        for record in af._calculations  # noqa: SLF001 -- the record under test
        if record.column == column
    )


def test_format_for_llm_carries_blocks_and_reading_structured() -> None:
    """The panel's LLM payload holds both facts uncapped, as data."""
    from gaspatchio.errors.formatter import graph_facts

    af = _dtype_chain()
    raised = _failure(af)
    record = _record_of(af, "reserve_factor")

    payload = FriendlyErrorFormatter(
        record=record,
        exception=raised,
        last_good_df=pl.DataFrame({"sum_assured": [100.0]}),
        facts=graph_facts(af, record),
    ).format_for_llm()

    assert payload["blocks"] == ["reserve@1", "net_cashflow@1", "solvency_margin@1"]
    assert payload["reading"] == [
        {"node": "product_code", "column": "product_code", "dtype": "str"},
        {"node": "sum_assured", "column": "sum_assured", "dtype": "f64"},
    ]


def test_format_for_llm_says_none_when_the_graph_could_not_answer() -> None:
    """No facts is ``None`` on both fields -- distinct from an empty answer."""
    af = _jagged()
    record = _record_of(af, "mismatched")

    payload = FriendlyErrorFormatter(
        record=record,
        exception=RuntimeError("x"),
        last_good_df=pl.DataFrame({"six": [[1.0]]}),
    ).format_for_llm()

    assert payload["blocks"] is None
    assert payload["reading"] is None
    assert payload["unnamed"] is None


def test_format_for_llm_says_why_a_type_the_graph_cannot_name_answers_nothing() -> None:
    """Two nulls with a reason beside them, not two nulls on their own.

    The same silence the panel printed on a fixed-width ``Array``, in the
    payload an agent reads instead of the panel. The refusal names the
    column and ends with the cast that carries it into the vocabulary.
    """
    from gaspatchio.errors.formatter import graph_facts

    af = _fixed_width_array()
    raised = _failure(af)
    record = _record_of(af, "final_cf")

    payload = FriendlyErrorFormatter(
        record=record,
        exception=raised,
        last_good_df=pl.DataFrame({"term": [1]}),
        facts=graph_facts(af, record),
    ).format_for_llm()

    assert payload["blocks"] is None
    assert payload["reading"] is None
    assert "has type Array" in payload["unnamed"]
    assert ".to_list()" in payload["unnamed"]


def test_a_traced_run_stamps_blocks_and_reading_on_the_exception() -> None:
    """End to end under the trace flag: the panel's payload carries both."""
    af = _dtype_chain()
    af._traced_run = True  # noqa: SLF001 -- the flag the trace decorator sets

    raised = _failure(af)

    assert raised.llm_context["blocks"] == [
        "reserve@1",
        "net_cashflow@1",
        "solvency_margin@1",
    ]
    assert [operand["dtype"] for operand in raised.llm_context["reading"]] == [
        "str",
        "f64",
    ]
    assert "Blocks: reserve@1, net_cashflow@1, solvency_margin@1" in str(raised)


# --- the export -------------------------------------------------------------


def test_ambiguous_attribution_is_exported_from_the_errors_package() -> None:
    """A caller pattern-matching the finder's answer imports it from one place."""
    from gaspatchio.errors import AmbiguousAttribution, boundary

    assert AmbiguousAttribution is boundary.AmbiguousAttribution
    assert "AmbiguousAttribution" in errors_exports


@pytest.mark.parametrize(
    "build",
    [pytest.param(_dtype_chain, id="dtype"), pytest.param(_jagged, id="jagged")],
)
def test_the_block_is_appended_exactly_once(
    build: Callable[[], ActuarialFrame],
) -> None:
    """The new lines ride the one block; re-entry prints nothing twice."""
    message = str(_failure(build()))

    assert message.count(NAMED) == 1
    assert message.count(BLOCKS) == 1
