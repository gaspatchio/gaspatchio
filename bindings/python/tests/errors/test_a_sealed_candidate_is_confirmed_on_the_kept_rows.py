# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sealed window's candidate is confirmed on the rows the operation kept.

The replay's head is ``_REPLAY_MAX_ROWS`` rows. A sealed window's head is
the first rows of its own baseline -- input rows 0 to 9,999 -- while the
live window's head is the first rows of the plan the user collected, which
under a filter reach past input row 10,000 by however many rows the filter
dropped before it. Between the two lies a band: a break on a surviving row
that the live head reaches and the sealed head does not. With one healthy
line after the filter, the live window's baseline fails on the break and the
window is passed over -- the everyday walk-back; with nothing after it, the
empty live window's head fails and hands on. Either way the sealed window
was searched next, and on its own head it found only the sibling a
``filter()`` had healed: a lookup that misses on a dropped row, named at its
own line for a failure it never raised.

Now a sealed candidate is confirmed before it is named: the candidate alone,
over its clean prefix, is re-run through the structural operations recorded
on the window at seal time -- the same callables the frame ran its own plan
through -- capped at the head. A candidate that raises the failure's class
and leading line there broke on a row the plan computed; one that collects
was healed by the operation and is not evidence, and the answer is bare. An
operation the candidate cannot be re-run through -- a predicate reading a
column recorded after the candidate -- is declined, with the reason in the
debug log. The line is compared with digits masked, because the row index a
``ShapeError`` carries is the engine's rather than the data's; a match on
the mask alone is then checked against the operations run without the
candidate, so an operation breaking on its own is not read as the
candidate's break. The confirmation lives in the sealed search, so both
entry paths reach it. The engine is the replay's: every replay in this
family collects on polars' default engine and the live collect streams, and
the rows a filter keeps do not depend on which engine walks them.

Pinned here: the band and its control on both entry paths and under a
traced run, the surviving-row break the sealed head reaches still named, the
two engines' disagreement as an observation of its own, a structural
operation's own break confirming nothing and what that decline costs when
the candidate was broken too, the mechanism as a fact about windows, a
second operation with nothing between joining the chain and the bound on
how long that chain grows, the decline, and every seal site recording an
operation the baseline can be re-run through.
"""

from __future__ import annotations

import pickle
from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest
from loguru import logger

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import (
    _REPLAY_MAX_ROWS,
    _AttributionReplayFinder,
    _digits_masked,
    replay_windows,
    search_collect_failure,
)
from gaspatchio.frame.calculation_log import _MAX_WINDOW_OPERATIONS
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what the message carries.
NAMED = "Failing column:"
REFUSAL = "Not attributed:"
PANEL = "Calculation Error"

_ROWS = 24_000
# Odd, so the even-rows filter drops it: the plain lookup misses here only
# and is healthy in the plan the user collected.
_HEALED_ROW = 5
# Even, so kept; past the sealed head and inside the live head, which
# under the even-rows filter reaches input row 19,998.
_BAND_ROW = 15_000
# Even, so kept; inside both heads.
_KEPT_IN_HEAD = 6
# One below the table, so ``issue_age`` misses and ``issue_age + 1`` lands.
_UNDER_THE_TABLE = 39
# The table's top age, so ``issue_age`` lands and ``issue_age + 1`` misses.
_TOP_OF_THE_TABLE = 43
# What the even-rows filter keeps of the frame.
_KEPT = _ROWS // 2


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _table(name: str) -> Table:
    """Build an age table covering 40 to 43; anything else misses it."""
    return Table(
        name=name,
        source=pl.DataFrame(
            {"age": [40, 41, 42, 43], "rate": [0.001, 0.0011, 0.0012, 0.0013]}
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _policies(
    *, break_row: int | None, under_at: tuple[int, ...] = (_HEALED_ROW,)
) -> pl.DataFrame:
    """Build the policies; ages cycle over 40 to 42 but for the rows named."""
    ages = [40 + (i % 3) for i in range(_ROWS)]
    for row in under_at:
        ages[row] = _UNDER_THE_TABLE
    if break_row is not None:
        ages[break_row] = _TOP_OF_THE_TABLE
    return pl.DataFrame({"policy_id": list(range(_ROWS)), "issue_age": ages})


def _keep_even(af: ActuarialFrame) -> ActuarialFrame:
    return af.filter(pl.col("policy_id") % 2 == 0)


def _band(
    name: str, *, break_row: int | None = _BAND_ROW, trailing: bool
) -> ActuarialFrame:
    """Build the band: a healed lookup, a break past the sealed head, the filter.

    Both key expressions carry the output name ``issue_age``, so the two
    lookups' refusals open with the same first line. ``trailing`` adds the
    healthy line that makes the live window a searched one.
    """
    table = _table(name)
    af = ActuarialFrame(_policies(break_row=break_row))
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age + 1)
    af = _keep_even(af)
    if trailing:
        af.doubled = af.rate_b * 2.0
    return af


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _bare(message: str) -> None:
    """Assert ``message`` is polars' own text: no name, no refusal, no panel."""
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert NAMED not in message
    assert REFUSAL not in message
    assert PANEL not in message
    assert "'rate_a'" not in message


# --- the band, and its control ------------------------------------------------


def test_the_band_lies_between_the_two_heads() -> None:
    """The premise: the live head reaches the break and the sealed head does not."""
    assert _BAND_ROW >= _REPLAY_MAX_ROWS > _KEPT_IN_HEAD
    control = _band("band_control", break_row=None, trailing=True)
    assert control.collect().height == _KEPT

    af = _band("band_premise", trailing=True)
    live, sealed = replay_windows(af)
    assert [r.column for r in live.records] == ["doubled"]
    assert [r.column for r in sealed.records] == ["rate_a", "rate_b"]
    assert live.baseline is not None
    assert sealed.baseline is not None
    with pytest.raises(pl.exceptions.ComputeError):
        live.baseline.limit(_REPLAY_MAX_ROWS).collect()
    head = sealed.baseline.limit(_REPLAY_MAX_ROWS).collect()
    assert head["policy_id"].max() < _BAND_ROW


def test_a_healed_lookup_is_not_named_for_a_break_in_the_band() -> None:
    """The defect: ``rate_a`` was named, at its own line, for ``rate_b``'s failure."""
    raised = _failure(_band("band_trailing", trailing=True))

    assert isinstance(raised, pl.exceptions.ComputeError)
    _bare(str(raised))


def test_the_twin_with_nothing_after_the_filter_is_bare_too() -> None:
    """The other entry path: the empty live window's head fails and hands on."""
    _bare(str(_failure(_band("band_nothing_after", trailing=False))))


def test_a_traced_run_answers_the_band_the_same_way() -> None:
    """The panel path runs the same search, so the band is bare there too."""
    af = _band("band_traced", trailing=True)
    af._traced_run = True  # noqa: SLF001 -- the flag the trace decorator sets

    _bare(str(_failure(af)))


# --- the everyday walk-back still names its column ---------------------------


def test_a_break_on_a_kept_row_the_sealed_head_reaches_is_still_named() -> None:
    """A real break on a surviving row reproduces on the kept rows too.

    ``rate_a`` misses on the dropped row and on a kept row inside both
    heads, so the live baseline fails, the sealed window reproduces it,
    and re-run through the filter it raises again: confirmed, and named.
    """
    table = _table("band_survivor")
    af = ActuarialFrame(
        _policies(break_row=None, under_at=(_HEALED_ROW, _KEPT_IN_HEAD))
    )
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age + 1)
    af = _keep_even(af)
    af.doubled = af.rate_b * 2.0

    message = str(_failure(af))

    assert "Failing column: 'rate_a'" in message
    assert REFUSAL not in message
    assert "'rate_b'" not in message


# A two-element list and a three-element one: multiplied together they raise
# ``list lengths differed at index N: 2 != 3``, whichever pair of columns
# carries them, which is what makes one calculation's line and another's
# differ in a digit and nothing else.
_OK: list[float] = [1.0, 2.0]
_JAGGED: list[float] = [1.0, 2.0, 3.0]
# Row 0 is dropped by the in-force filter; rows 1 and 2 survive it.
_FIRST_KEPT_ROW = 1
_SECOND_KEPT_ROW = 2


def _kept_row_jag() -> ActuarialFrame:
    """Build a list multiply jagged on the dropped row and on a kept one, a line after.

    Three rows are enough to show the engines numbering the offending row
    differently, which the test below observes on its own; one healthy line
    after the filter, so the live window is a searched one and the
    walk-back reaches the sealed window.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": [_JAGGED, _OK, _JAGGED],
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(pl.col("status") == "IF")
    af.s = af.j.list.sum()
    return af


def _engine_lines(af: ActuarialFrame) -> dict[str, str]:
    """Return the leading line ``af``'s live plan raises on each engine."""
    lines: dict[str, str] = {}
    for engine in ("streaming", "in-memory"):
        with pytest.raises(pl.exceptions.ShapeError) as excinfo:
            af._df.collect(engine=engine)  # noqa: SLF001 -- the live plan, each engine
        lines[engine] = str(excinfo.value).split("\n", 1)[0]
    return lines


def test_the_two_engines_number_the_offending_row_differently() -> None:
    """The polars observation the digit mask rests on, pinned on its own.

    Measured on polars 1.42.1, the same ``j = a * b`` / in-force filter /
    line-after plan with the jag moved:

    ==========================================  =========  =========
    shape                                       streaming  in-memory
    ==========================================  =========  =========
    three rows, dropped row 0 only              collects   collects
    three rows, kept row 2 only                 index 0    index 1
    six rows, kept row 5 only                   index 0    index 4
    six rows, dropped rows 0 and 1, kept row 5  index 0    index 3
    ==========================================  =========  =========

    So neither number is a position in the frame the user collected. The
    in-memory index counts within the frame the filter left; the streaming
    one is not a position in either frame -- ``0`` for the third row of
    three and for the sixth of six -- which reads as an offset inside the
    chunk its kernel was computing. And a jag on a dropped row alone
    collects on BOTH, so neither engine computes the multiply over the
    dropped row: ``explain`` prints one optimised plan for both, ``FILTER``
    under the ``WITH_COLUMNS``. A ``ShapeError``'s row index is therefore
    not a fact about the user's data, and two engines' lines cannot be
    compared exactly.

    Its own test, so that a polars which makes the engines agree fails this
    observation and not the behaviour that rests on it.
    """
    lines = _engine_lines(_kept_row_jag())

    assert lines["streaming"] != lines["in-memory"]
    assert _digits_masked(lines["streaming"]) == _digits_masked(lines["in-memory"])


def test_a_jag_on_a_kept_row_is_confirmed_whichever_index_the_engine_reports() -> None:
    """A ``ShapeError``'s row index is the engine's, and the confirmation masks it.

    The confirmation replay runs in memory over the kept rows, so compared
    exactly against the streamed line a genuine kept-row break read as a
    different failure, the window declined, and the answer went bare where
    the parent named ``j``. Compared with digits masked it is confirmed --
    and the filter here breaks on nothing of its own, which is what the
    masked match is then allowed to mean.
    """
    message = str(_failure(_kept_row_jag()))

    assert message.startswith("list lengths differed at index ")
    assert "Failing column: 'j'" in message
    assert REFUSAL not in message


# --- an operation that breaks on its own is not the candidate breaking ---------


def _healed_beside_a_broken_select(*, operation_jag_row: int) -> ActuarialFrame:
    """Build a candidate the filter heals beside a ``select`` that breaks on its own.

    ``j`` is jagged on the dropped row alone, so ``j`` over the rows the
    filter keeps collects; the ``select``'s own ``c * d`` is jagged with
    the SAME lengths on the kept row named. The two raise the same class
    and lines that differ only in the row index -- exactly what the
    confirmation's mask stops reading as two failures.
    """
    d = [_OK, _OK, _OK]
    d[operation_jag_row] = _JAGGED
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": [_JAGGED, _OK, _OK],
                "c": [_OK] * 3,
                "d": d,
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(pl.col("status") == "IF")
    af = af.select(pl.col("*"), (pl.col("c") * pl.col("d")).alias("k"))
    af.s = af.j.list.sum()
    return af


def test_the_candidate_beside_a_broken_operation_is_healed_by_the_filter() -> None:
    """The premise the shapes below rest on: ``j`` over the kept rows collects.

    Its only jag is on the dropped row, so nothing the plan the user
    collected computed for ``j`` is broken, and any name the window gives
    ``j`` on these shapes is a name it cannot stand behind.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": [_JAGGED, _OK, _OK],
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(pl.col("status") == "IF")

    assert af.collect().height == 2


def test_a_select_that_breaks_on_a_kept_row_does_not_confirm_the_candidate() -> None:
    """A structural operation's own break is not evidence about the candidate.

    The ``select``'s ``c * d`` is jagged on the second kept row, so its
    raise reaches the confirmation replay and, digits masked, reads as
    ``j``'s. Re-running the prefix WITHOUT ``j`` through the same
    operations raises the same masked shape, so the break is the
    operation's and the window names nothing.
    """
    af = _healed_beside_a_broken_select(operation_jag_row=_SECOND_KEPT_ROW)

    message = str(_failure(af))

    assert message.startswith("list lengths differed at index ")
    assert NAMED not in message
    assert REFUSAL not in message


def _broken_beside_a_broken_select() -> ActuarialFrame:
    """Build a candidate broken on a kept row beside a ``select`` broken on one too.

    The sibling of ``_healed_beside_a_broken_select`` with ``j`` jagged on a
    KEPT row as well as the dropped one, so ``j`` really breaks on a row the
    plan the user collected computed. The ``select``'s ``c * d`` is jagged on
    that same kept row, with the same lengths, so both are broken at once.
    """
    d = [_OK, _OK, _OK]
    d[_SECOND_KEPT_ROW] = _JAGGED
    b = [_JAGGED, _OK, _OK]
    b[_SECOND_KEPT_ROW] = _JAGGED
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": b,
                "c": [_OK] * 3,
                "d": d,
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(pl.col("status") == "IF")
    af = af.select(pl.col("*"), (pl.col("c") * pl.col("d")).alias("k"))
    af.s = af.j.list.sum()
    return af


def test_the_candidate_broken_beside_a_broken_operation_is_named_without_it() -> None:
    """The premise: ``j``'s break is real, and a healthy operation names it.

    ``j`` is jagged on a kept row, so the plan the user collected did
    compute the break. With the ``select`` healthy the window confirms
    ``j`` on the kept rows and names it -- which is what the decline below
    gives up.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": [_JAGGED, _OK, _JAGGED],
                "c": [_OK] * 3,
                "d": [_OK] * 3,
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(pl.col("status") == "IF")
    af = af.select(pl.col("*"), (pl.col("c") * pl.col("d")).alias("k"))
    af.s = af.j.list.sum()

    assert "Failing column: 'j'" in str(_failure(af))


def test_both_broken_declines_and_gives_up_a_name_that_was_right() -> None:
    """The cost the decline is written to pay, pinned on the shape that pays it.

    The candidate and the operation are broken on the same kept row. The
    confirmation replay raises, the mask cannot tell whose raise it is, and
    the operations run without ``j`` raise it too -- so the window declines
    and says nothing, where the premise above shows ``j`` was the right
    name. That is the direction a name the window cannot stand behind has
    to go, and it is a decline rather than an inability to check.
    """
    captured: list[str] = []
    sink = logger.add(
        lambda message: captured.append(message.record["message"]), level="DEBUG"
    )
    try:
        message = str(_failure(_broken_beside_a_broken_select()))
    finally:
        logger.remove(sink)

    assert message.startswith("list lengths differed at index ")
    assert NAMED not in message
    assert REFUSAL not in message
    broke_alone = [line for line in captured if "broke on its own" in line]
    assert len(broke_alone) == 1
    assert "'j'" in broke_alone[0]
    assert "cannot confirm" not in " ".join(captured)


def test_a_filter_predicate_that_breaks_on_a_kept_row_confirms_nothing() -> None:
    """The same hole reached through the operation a walk-back most often holds.

    The break is inside the filter's own predicate rather than in a door
    after it, and ``j`` is healed by that same filter.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF", "IF"],
                "a": [_OK] * 3,
                "b": [_JAGGED, _OK, _OK],
                "c": [_OK] * 3,
                "d": [_OK, _OK, _JAGGED],
            }
        )
    )
    af.j = af.a * af.b
    af = af.filter(
        (pl.col("status") == "IF") & ((pl.col("c") * pl.col("d")).list.sum() > 0)
    )
    af.s = af.j.list.sum()

    message = str(_failure(af))

    assert message.startswith("list lengths differed at index ")
    assert NAMED not in message
    assert REFUSAL not in message


def test_an_operations_break_whose_line_matches_exactly_is_still_confirmed() -> None:
    """Pinned as it stands: ``j`` is named here, and was before the mask existed.

    With the ``select``'s jag on the FIRST kept row the replayed line is
    byte-identical to the live one, so the confirmation matches exactly and
    the extra replay the masked-only path pays is not run. The name is
    wrong -- ``j`` is healed by the filter, as the premise above pins --
    but it is the standard the candidate was found by rather than anything
    the mask opened, and closing it would cost a replay on every
    confirmation instead of only on the masked-only path. Recorded here as
    it behaves, for the candidate matcher's own tidy.
    """
    af = _healed_beside_a_broken_select(operation_jag_row=_FIRST_KEPT_ROW)

    message = str(_failure(af))

    assert "Failing column: 'j'" in message


# --- the mechanism ------------------------------------------------------------


def test_the_seal_records_the_operation_it_closed_the_window_with() -> None:
    """The window holds the filter; its plan re-run through it is the frame's plan."""
    af = _band("band_operation", break_row=None, trailing=True)
    (sealed,) = af._sealed_windows  # noqa: SLF001 -- the window under test

    assert [op.kind for op in sealed.operations] == ["filter"]
    assert sealed.baseline is not None
    pre_filter = sealed.baseline.with_columns(
        *(record.expr.alias(record.column) for record in sealed.records)
    )
    replayed = sealed.operations[0].applied_to(pre_filter).collect()
    assert replayed.equals(af._df.drop("doubled").collect())  # noqa: SLF001


def test_a_healed_candidate_does_not_reproduce_on_the_kept_rows() -> None:
    """The finder's own answer: the reproduction the band named is not confirmed."""
    af = _band("band_mechanism", trailing=True)
    raised = _failure(af)
    _live, sealed = replay_windows(af)
    finder = _AttributionReplayFinder(
        af, raised, max_rows=_REPLAY_MAX_ROWS, window=sealed
    )

    assert finder.baseline_usable
    index, hit, _ = finder.find_failing_operation()
    assert hit is not None
    assert hit.column == "rate_a"
    assert finder.later_reproductions(index) == []
    assert finder.confirmed_on_kept_rows(index, hit, sealed.operations) is False
    assert search_collect_failure(af, raised).attribution is None


def test_a_surviving_candidate_is_confirmed_on_the_kept_rows() -> None:
    """The same question on the survivor shape answers yes."""
    table = _table("band_confirmed")
    af = ActuarialFrame(
        _policies(break_row=None, under_at=(_HEALED_ROW, _KEPT_IN_HEAD))
    )
    af.rate_a = table.lookup(age=af.issue_age)
    af = _keep_even(af)
    af.doubled = af.rate_a * 2.0
    raised = _failure(af)
    _live, sealed = replay_windows(af)
    finder = _AttributionReplayFinder(
        af, raised, max_rows=_REPLAY_MAX_ROWS, window=sealed
    )

    index, hit, _ = finder.find_failing_operation()

    assert hit is not None
    assert finder.confirmed_on_kept_rows(index, hit, sealed.operations) is True


def test_a_second_operation_with_nothing_between_joins_the_chain() -> None:
    """Two filters back to back: the second is recorded on the same window.

    The first filter keeps the row ``rate_a`` misses on; the second drops
    it. Confirmed through the first alone, ``rate_a`` would stand; through
    both, it collects, and the answer is bare. ``rate_b`` breaks on the
    last row of the live head and past the sealed one.
    """
    table = _table("band_chain")
    second_filter_drops = _HEALED_ROW
    first_filter_drops = 7
    last_of_the_live_head = _REPLAY_MAX_ROWS + 1
    af = ActuarialFrame(_policies(break_row=last_of_the_live_head))
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age + 1)
    af = af.filter(pl.col("policy_id") != first_filter_drops)
    af = af.filter(pl.col("policy_id") != second_filter_drops)
    af.doubled = af.rate_b * 2.0
    (sealed,) = af._sealed_windows  # noqa: SLF001 -- the window under test
    assert [op.kind for op in sealed.operations] == ["filter", "filter"]

    _bare(str(_failure(af)))


def test_the_chain_over_an_empty_window_keeps_the_newest_and_no_more() -> None:
    """Structural calls back to back grow one chain, and it is bounded.

    Every operation over an empty window joins the last sealed window's
    chain instead of sealing one of its own, so nothing bounds the run but
    this cap: 2,000 consecutive ``filter`` calls built a chain of 2,000.
    The tuple is rebuilt on every join and the confirmation replays all of
    it per candidate, so the length is a cost on the model's build and on
    the error path alike.

    A ``sort`` at each end of a run of filters says which end survives: the
    oldest falls off the front, the newest is still there, and what is kept
    is the operations nearest the plan the user collected.
    """
    af = ActuarialFrame(_policies(break_row=None))
    af.rate_a = _table("chain_cap").lookup(age=af.issue_age)
    af = af.sort("policy_id")
    for _ in range(_MAX_WINDOW_OPERATIONS):
        af = _keep_even(af)
    af = af.sort("policy_id", descending=True)

    (sealed,) = af._sealed_windows  # noqa: SLF001 -- the window under test
    kinds = [operation.kind for operation in sealed.operations]

    assert len(kinds) == _MAX_WINDOW_OPERATIONS
    assert kinds[-1] == "sort"
    assert kinds[0] == "filter"
    assert kinds.count("sort") == 1
    # Capping the chain leaves the frame's own plan untouched.
    assert af.collect().height == _KEPT


def test_an_operation_the_candidate_cannot_be_re_run_through_is_declined() -> None:
    """A predicate reading a column recorded after the candidate cannot be replayed.

    The candidate alone over its prefix has no ``flag``; the filter raises a
    different error, the window cannot confirm, and it names nothing --
    saying so in the debug log. The cost is stated by the shape: ``rate_a``
    misses on a kept row here as well as the dropped one, so the name the
    window declines would have been right. It declines because it cannot
    check it, which is the direction a name it cannot check must go; the
    later records are left out of the re-run on purpose, since one of them
    reading the candidate could raise the candidate's own line on the kept
    rows and confirm a healed candidate by proxy.
    """
    captured: list[str] = []
    sink = logger.add(
        lambda message: captured.append(message.record["message"]), level="DEBUG"
    )
    try:
        table = _table("band_declined")
        af = ActuarialFrame(
            _policies(break_row=None, under_at=(_HEALED_ROW, _KEPT_IN_HEAD))
        )
        af.rate_a = table.lookup(age=af.issue_age)
        # A comparison is stamped as a 0/1 float, so the predicate reads it
        # back as one rather than as the Boolean a filter wants.
        af.flag = af.issue_age > 0
        af = af.filter((pl.col("flag") > 0.5) & (pl.col("policy_id") != _HEALED_ROW))
        af.rate_b = table.lookup(age=af.issue_age + 1)

        message = str(_failure(af))
    finally:
        logger.remove(sink)

    assert NAMED not in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message
    declined = [line for line in captured if "cannot confirm" in line]
    assert len(declined) == 1
    assert "ColumnNotFoundError" in declined[0]
    assert "'rate_a'" in declined[0]


# --- every seal site records an operation the baseline can be re-run through ---


def _seed() -> ActuarialFrame:
    """Three policies with a healthy calculation recorded before the operation."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "premium": [10.0, 20.0, 30.0],
                "start": [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
                "end": [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)],
                "init": [100.0, 200.0, 300.0],
                "rate": [[0.0, 0.0, 0.0]] * 3,
            }
        )
    )
    af.loaded = af.premium * 1.1
    return af


def _rollforward(af: ActuarialFrame) -> ActuarialFrame:
    schedule = Schedule.from_calendar_grid(
        start_date=date(2026, 1, 31), n_periods=3, frequency="1M"
    )
    builder = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule)
    builder["av"].grow(pl.col("rate"), label="G")
    af.av = compile_rollforward(builder).expr_for("av")
    return af


_SEAL_SITES: list[tuple[str, Callable[[ActuarialFrame], ActuarialFrame], str]] = [
    ("filter", lambda af: af.filter(pl.col("policy_id") != 2), "filter"),
    ("sort", lambda af: af.sort("premium", descending=True), "sort"),
    ("select", lambda af: af.select("policy_id", "premium", "loaded"), "select"),
    ("drop", lambda af: af.drop("start", "end"), "drop"),
    ("rename", lambda af: af.rename({"premium": "annual_premium"}), "rename"),
    (
        "join",
        lambda af: af.join(
            pl.DataFrame({"policy_id": [1, 2, 3], "band": ["a", "b", "c"]}),
            on="policy_id",
            maintain_order="left",
        ),
        "join",
    ),
    (
        "projection",
        lambda af: af.projection.set(
            start_date=date(2026, 1, 1), n_periods=3, frequency="monthly"
        ),
        "projection",
    ),
    (
        "date-timeline",
        lambda af: af.date.create_timeline("start", "end", freq="1mo"),
        "date",
    ),
    (
        "date-duration",
        lambda af: af.date.add_duration("start", "1mo", new_col_name="later"),
        "date",
    ),
    ("rollforward", _rollforward, "rollforward"),
]


@pytest.mark.parametrize(
    ("operate", "kind"),
    [pytest.param(operate, kind, id=name) for name, operate, kind in _SEAL_SITES],
)
def test_every_seal_site_records_an_operation_the_baseline_re_runs_through(
    operate: Callable[[ActuarialFrame], ActuarialFrame], kind: str
) -> None:
    """Each structural door seals with its own operation, and it is the frame's.

    Re-running the sealed baseline plus its records through the recorded
    operation collects to the plan the next window opened over, which is
    what makes the confirmation a replay of the model and not a description
    of one.
    """
    from gaspatchio.frame.calculations import StructuralOperation

    af = operate(_seed())
    af.tail = af.loaded * 2.0

    (sealed,) = af._sealed_windows  # noqa: SLF001 -- the window under test
    assert [op.kind for op in sealed.operations] == [kind]
    assert isinstance(sealed.operations[0], StructuralOperation)
    assert sealed.baseline is not None
    pre_operation = sealed.baseline.with_columns(
        *(record.expr.alias(record.column) for record in sealed.records)
    )
    replayed = sealed.operations[0].applied_to(pre_operation).collect()
    next_baseline = af._baseline_df  # noqa: SLF001 -- the plan the tail opened over
    assert next_baseline is not None
    assert replayed.equals(next_baseline.collect())


def test_the_windows_carry_their_operations_to_the_search() -> None:
    """``replay_windows`` hands each sealed window's chain on, live window first."""
    af = _seed()
    af = af.filter(pl.col("policy_id") != 2)
    af.after = af.loaded * 3.0
    af = af.sort("premium")
    af = af.drop("start")
    af.last = af.after * 1.0

    live, newest, oldest = replay_windows(af)

    assert live.operations == ()
    assert [op.kind for op in newest.operations] == ["sort", "drop"]
    assert [op.kind for op in oldest.operations] == ["filter"]


# --- the window survives a pickle, and declines there -------------------------


def _pickled(af: ActuarialFrame) -> ActuarialFrame:
    """Round-trip ``af`` through pickle, as a worker process would receive it."""
    copy: ActuarialFrame = pickle.loads(pickle.dumps(af))  # noqa: S301 -- own bytes
    return copy


def test_a_frame_with_a_sealed_window_pickles_and_collects_the_same_rows() -> None:
    """The closure a door built is dropped at pickle time; the plan travels whole.

    At the parent ``pickle.dumps`` raised ``Can't get local object
    'ActuarialFrame.filter.<locals>._filtered'``: the sealed window held the
    filter as the callable the frame ran its plan through, which pickle
    cannot carry. The operation now pickles as its kind alone, and the
    unpickled frame's window says so with an ``apply`` of ``None``.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": list(range(100)), "x": [1.0] * 100}))
    af.y = af.x * 2.0
    af = af.filter(pl.col("policy_id") % 2 == 0)
    af.z = af.y * 3.0

    copy = _pickled(af)

    (sealed,) = copy._sealed_windows  # noqa: SLF001 -- the window under test
    assert [op.kind for op in sealed.operations] == ["filter"]
    assert sealed.operations[0].apply is None
    assert copy.collect().equals(af.collect())


def test_the_projection_timelines_window_pickles_too() -> None:
    """The other door the parent failed on: ``with_columns_operation``'s closure."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "x": [1.0, 2.0]}))
    af.y = af.x * 2.0
    af = af.projection.set(
        start_date=date(2026, 1, 1), n_periods=3, frequency="monthly"
    )

    copy = _pickled(af)

    (sealed,) = copy._sealed_windows  # noqa: SLF001 -- the window under test
    assert [op.kind for op in sealed.operations] == ["projection"]
    assert copy.collect().equals(af.collect())


def test_a_walk_back_over_an_unpickled_frame_declines_at_the_sealed_window() -> None:
    """Through a pickle, the kept-row jag that names ``j`` declines instead.

    The sealed window's operation arrived without its callable, so the
    candidate cannot be re-run through it: the window declines to confirm,
    with the reason in the debug log, rather than raising or naming on
    evidence it could not check -- the same decline as a predicate the
    candidate cannot be re-run through, reached the same way.
    """
    captured: list[str] = []
    sink = logger.add(
        lambda message: captured.append(message.record["message"]), level="DEBUG"
    )
    try:
        message = str(_failure(_pickled(_kept_row_jag())))
    finally:
        logger.remove(sink)

    assert message.startswith("list lengths differed at index ")
    assert NAMED not in message
    assert REFUSAL not in message
    declined = [line for line in captured if "cannot confirm" in line]
    assert len(declined) == 1
    assert "'j'" in declined[0]
    assert "pickle" in declined[0]
