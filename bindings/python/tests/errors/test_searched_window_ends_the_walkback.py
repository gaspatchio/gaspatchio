# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A window that was searched and reproduced nothing ends the walk-back.

The replay searches the live window first and, when it cannot, the windows
structural operations sealed behind it, newest first. It used to walk back
whenever the live window named nothing -- including when that window's
baseline had collected on its head and every calculation in it replayed
clean. That walk-back reached a sealed window whose baseline holds rows the
live plan never computed: a lookup that misses only on the row a later
``filter()`` drops is healthy in the plan the user collected -- predicate
pushdown puts the filter under it, so it never ran on that row -- but on
the sealed window's unfiltered baseline it misses, raises the same class
and leading line as the real break, and was named at its own source line.

The rule now: a window whose baseline collected on its head and which was
searched has every older record applied on the rows that survive its
structural operation, so any reproduction an older window offers is on a
row (or, under projection pushdown, a column) the live plan never
computed. That is not evidence about the failure the user saw, and the
search ends there. A window passed over because its baseline would not
collect still hands on -- that is the everyday walk-back, pinned in
``test_filter_attribution.py`` -- and so does a window with no records,
which was never searched.

The two lookups key on expressions with one output name, ``issue_age``,
so their refusals open with the same first line; the later one adds a
``bump`` column that is zero everywhere but one row, which is what lets
the earlier lookup miss only on the row the filter drops while the later
one misses only where the shape says. Pinned here: the shape and its
control, the refusal variant, the mechanism as a fact about windows (the
one behind IS usable and WOULD reproduce, and is not consulted), and the
two everyday cases that still name their column.
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
# The row the filter drops: the earlier lookup misses here and nowhere else,
# so it is healthy in the plan the user collected.
_HEALED_ROW = 5
# A row the replayed head never reaches, and one it does.
_PAST_THE_HEAD = 11_000
_IN_THE_HEAD = 7
# Added to an in-table age, lands off the table.
_BUMP = 60


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _table(name: str) -> Table:
    """Build an age table covering 40 to 42; anything else misses it."""
    return Table(
        name=name,
        source=pl.DataFrame({"age": [40, 41, 42], "rate": [0.001, 0.0011, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _policies(*, bump_at: int | None) -> pl.DataFrame:
    """Build twelve thousand policies whose ages cycle over the table.

    Row ``_HEALED_ROW`` carries an age off the table. ``bump`` is zero
    everywhere except ``bump_at``, so ``issue_age + bump`` misses there and
    nowhere the plain ``issue_age`` does not.
    """
    ages = [40 + (i % 3) for i in range(_ROWS)]
    ages[_HEALED_ROW] = 99
    bump = [0] * _ROWS
    if bump_at is not None:
        bump[bump_at] = _BUMP
    return pl.DataFrame(
        {"policy_id": list(range(_ROWS)), "issue_age": ages, "bump": bump}
    )


def _without_the_healed_row(af: ActuarialFrame) -> ActuarialFrame:
    return af.filter(pl.col("policy_id") != _HEALED_ROW)


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _healed_then_break_past_the_head(name: str) -> ActuarialFrame:
    """Build the shape: one healed lookup sealed, one live break past the head."""
    table = _table(name)
    af = ActuarialFrame(_policies(bump_at=_PAST_THE_HEAD))
    af.rate_a = table.lookup(age=af.issue_age)
    af = _without_the_healed_row(af)
    af.rate_c = table.lookup(age=af.issue_age + af.bump)
    return af


# --- the defect and its control ---------------------------------------------


def test_a_healed_lookup_is_not_named_for_a_break_past_the_head() -> None:
    """The defect: ``rate_a`` was named, at its own line, for ``rate_c``'s failure.

    ``rate_a`` misses only on the row the filter drops; the control proves
    the filter heals it. ``rate_c`` misses only past the replayed head, so
    the live window's baseline collects and ``rate_c`` replays clean, and
    the walk-back used to reach the sealed window, where ``rate_a``
    reproduces the first line on the unfiltered head. The answer is bare
    now: the live window was searched, and that ended the search.
    """
    assert _PAST_THE_HEAD >= _REPLAY_MAX_ROWS > _IN_THE_HEAD
    table = _table("walkback_healed_control")
    control = ActuarialFrame(_policies(bump_at=None))
    control.rate_a = table.lookup(age=control.issue_age)
    control = _without_the_healed_row(control)
    control.rate_c = table.lookup(age=control.issue_age + control.bump)
    assert control.collect().height == _ROWS - 1

    raised = _failure(_healed_then_break_past_the_head("walkback_healed_lookup"))

    assert isinstance(raised, pl.exceptions.ComputeError)
    message = str(raised)
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert NAMED not in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message


def test_two_healed_lookups_are_not_listed_for_a_break_past_the_head() -> None:
    """The refusal variant: two healed lookups sealed, one live break past the head.

    The walk-back used to reach the sealed pair, find both reproducing,
    and refuse -- listing ``rate_a`` and ``rate_b``, both healthy, with the
    real break in neither. True in every word, and the wrong pair. Bare
    now, for the same reason.
    """
    table = _table("walkback_healed_pair")
    af = ActuarialFrame(_policies(bump_at=_PAST_THE_HEAD))
    af.rate_a = table.lookup(age=af.issue_age)
    af.rate_b = table.lookup(age=af.issue_age)
    af = _without_the_healed_row(af)
    af.rate_c = table.lookup(age=af.issue_age + af.bump)

    message = str(_failure(af))

    assert REFUSAL not in message
    assert NAMED not in message
    assert "'rate_a'" not in message
    assert "'rate_b'" not in message


def test_the_window_behind_a_searched_bare_window_is_not_consulted() -> None:
    """The mechanism, as a fact about windows rather than about text.

    Both windows are usable. Replayed on its own, the sealed one names
    ``rate_a`` -- the reproduction the old walk-back returned. The search
    still answers ``None``, because the live window was searched first,
    reproduced nothing, and ended it there.
    """
    af = _healed_then_break_past_the_head("walkback_mechanism")
    raised = _failure(af)

    windows = [window for window in replay_windows(af) if window.records]
    assert [[r.column for r in w.records] for w in windows] == [["rate_c"], ["rate_a"]]
    finders = [
        _AttributionReplayFinder(af, raised, max_rows=_REPLAY_MAX_ROWS, window=w)
        for w in windows
    ]
    assert [finder.baseline_usable for finder in finders] == [True, True]
    _, live_hit, _ = finders[0].find_failing_operation()
    _, sealed_hit, _ = finders[1].find_failing_operation()
    assert live_hit is None
    assert sealed_hit is not None
    assert sealed_hit.column == "rate_a"

    assert search_collect_failure(af, raised).attribution is None


# --- the everyday cases still name their column -----------------------------


def test_a_break_in_the_head_after_the_filter_is_still_named() -> None:
    """Same shape, the break inside the head: the live window names it."""
    table = _table("walkback_live_names")
    af = ActuarialFrame(_policies(bump_at=_IN_THE_HEAD))
    af.rate_a = table.lookup(age=af.issue_age)
    af = _without_the_healed_row(af)
    af.rate_c = table.lookup(age=af.issue_age + af.bump)

    message = str(_failure(af))

    assert "Failing column: 'rate_c'" in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message


def test_a_break_in_the_head_before_the_filter_is_still_named_behind_it() -> None:
    """The everyday walk-back: the live baseline carries the break and is skipped.

    ``rate_a`` misses on a surviving row inside the head, so the live
    window's baseline will not collect, the window hands on, and the
    sealed window behind it answers.
    """
    table = _table("walkback_sealed_names")
    af = ActuarialFrame(_policies(bump_at=_IN_THE_HEAD))
    af.rate_a = table.lookup(age=af.issue_age + af.bump)
    af = _without_the_healed_row(af)
    af.doubled = af.rate_a * 2.0

    message = str(_failure(af))

    assert "Failing column: 'rate_a'" in message
    assert REFUSAL not in message
    assert "'doubled'" not in message
