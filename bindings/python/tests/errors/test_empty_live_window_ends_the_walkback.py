# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A live window with no records ends the walk-back when its plan collects.

The search ends at a window that was searched and reproduced nothing
(``test_searched_window_ends_the_walkback.py``): its baseline collected on
its head with every older record applied on the rows that survive its
structural operation, so nothing a window behind it could reproduce is
evidence about the failure the user saw. A live window with NO records --
nothing written after the ``filter()`` -- was never searched, and it used
to hand on before any finder was built. Its baseline is the plan the user
collected, and whether that plan's head collects is the very fact the rule
turns on; the rule never looked. So a lookup that misses only on the row
the filter drops was named, at its own line, for a break past the replay
head whenever no line followed the filter, and bare when one did: the two
are one defect with one right answer.

Now the empty window's plan is collected on its head before anything is
handed on. When it collects, every recorded calculation is healthy on the
plan the user collected and the failure lies past the head, so the search
ends bare -- the same ending as a searched window that reproduced nothing.
When it does not, the window hands on as before, and the everyday case --
a break on a surviving row inside the head, nothing written after the
filter -- is still named behind the filter. The plan is read from ``_df``,
the frame's current plan: ``_baseline_df`` is the snapshot the last window
opened over and goes stale at a seal until the next record lands.

Pinned here: the shape and its control, its trailing-line twin, the
mechanism as a fact about windows, and the everyday case.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import (
    _REPLAY_MAX_ROWS,
    _AttributionReplayFinder,
    replay_windows,
    search_collect_failure,
)

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what the message carries.
REFUSAL = "Not attributed:"
NAMED = "Failing column:"

_ROWS = 12_000
# The row the filter drops: the plain lookup misses here and nowhere else,
# so it is healthy in the plan the user collected.
_HEALED_ROW = 5
# A row the replayed head never reaches, and one it does.
_PAST_THE_HEAD = 11_000
_IN_THE_HEAD = 7
# One below the table, so ``issue_age`` misses and ``issue_age + 1`` lands.
_UNDER_THE_TABLE = 39
# The table's top age, so ``issue_age`` lands and ``issue_age + 1`` misses.
_TOP_OF_THE_TABLE = 43


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
    """Build twelve thousand policies whose ages cycle over 40 to 42.

    Rows in ``under_at`` carry an age one below the table, so ``issue_age``
    misses there and ``issue_age + 1`` does not; ``break_row`` carries the
    table's top age, so ``issue_age + 1`` misses there and ``issue_age``
    does not.
    """
    ages = [40 + (i % 3) for i in range(_ROWS)]
    for row in under_at:
        ages[row] = _UNDER_THE_TABLE
    if break_row is not None:
        ages[break_row] = _TOP_OF_THE_TABLE
    return pl.DataFrame({"policy_id": list(range(_ROWS)), "issue_age": ages})


def _healed_then_a_break_past_the_head(
    name: str, *, break_row: int | None = _PAST_THE_HEAD
) -> ActuarialFrame:
    """Build the shape: a healed lookup, a break past the head, then the filter.

    Nothing is written after the filter. Both key expressions carry the
    output name ``issue_age``, so the two lookups' refusals open with the
    same first line.
    """
    table = _table(name)
    af = ActuarialFrame(_policies(break_row=break_row))
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age + 1)
    return af.filter(pl.col("policy_id") != _HEALED_ROW)


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


# --- the defect and its control ---------------------------------------------


def test_a_healed_lookup_is_not_named_when_nothing_follows_the_filter() -> None:
    """The defect: ``rate_a`` was named, at its own line, for ``rate_b``'s failure.

    ``rate_a`` misses only on the row the filter drops; the control proves
    the filter heals it. ``rate_b`` misses only past the replayed head, so
    the plan the user collected collects on its head -- and with nothing
    written after the filter the live window held no records, handed on
    unsearched, and the sealed window reproduced ``rate_a`` on the
    unfiltered head. Bare now: the empty window's plan collects, and that
    ends the search.
    """
    assert _PAST_THE_HEAD >= _REPLAY_MAX_ROWS > _IN_THE_HEAD
    control = _healed_then_a_break_past_the_head("empty_live_control", break_row=None)
    assert control.collect().height == _ROWS - 1

    raised = _failure(_healed_then_a_break_past_the_head("empty_live_healed"))

    assert isinstance(raised, pl.exceptions.ComputeError)
    message = str(raised)
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert NAMED not in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message


def test_the_same_shape_with_a_line_after_the_filter_is_bare_too() -> None:
    """The trailing-line twin, already bare by the searched-window rule.

    One healthy line after the filter gives the live window a record, so
    it is searched, reproduces nothing, and ends the search. Whether a
    line happens to follow the filter is not a fact about the failure;
    the two variants have one right answer.
    """
    af = _healed_then_a_break_past_the_head("empty_live_trailing")
    af.doubled = af.rate_b * 2.0

    message = str(_failure(af))

    assert NAMED not in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message


def test_the_window_behind_an_empty_live_window_is_not_consulted() -> None:
    """The mechanism, as a fact about windows rather than about text.

    The live window holds no records; the plan the user collected -- the
    frame's current plan, not the stale ``_baseline_df`` -- collects on
    its head. The sealed window behind it is usable and, replayed on its
    own, names ``rate_a``: the reproduction the old walk-back returned.
    The search answers ``None``.
    """
    af = _healed_then_a_break_past_the_head("empty_live_mechanism")
    raised = _failure(af)

    live, *sealed = replay_windows(af)
    assert live.records == []
    assert [[r.column for r in w.records] for w in sealed] == [["rate_a", "rate_b"]]
    head = af._df.limit(_REPLAY_MAX_ROWS).collect()  # noqa: SLF001
    assert head.height == _REPLAY_MAX_ROWS
    finder = _AttributionReplayFinder(
        af, raised, max_rows=_REPLAY_MAX_ROWS, window=sealed[0]
    )
    assert finder.baseline_usable
    _, sealed_hit, _ = finder.find_failing_operation()
    assert sealed_hit is not None
    assert sealed_hit.column == "rate_a"

    assert search_collect_failure(af, raised).attribution is None


# --- the everyday case still names its column -------------------------------


def test_a_break_on_a_surviving_row_in_the_head_is_still_named_behind_it() -> None:
    """The everyday walk-back: the plan's head fails, the empty window hands on.

    ``rate_a`` misses on the dropped row and on a surviving row inside the
    head, so the plan the user collected does not collect on its head, the
    empty live window hands on as it always did, and the sealed window
    names ``rate_a`` -- which is the break.
    """
    table = _table("empty_live_names")
    af = ActuarialFrame(_policies(break_row=None, under_at=(_HEALED_ROW, _IN_THE_HEAD)))
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age + 1)
    af = af.filter(pl.col("policy_id") != _HEALED_ROW)

    message = str(_failure(af))

    assert "Failing column: 'rate_a'" in message
    assert REFUSAL not in message
    assert "'rate_b'" not in message
