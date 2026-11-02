# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A position that fell out of a multi-operation probe is not evidence.

The finder's multi-operation probes -- the full replay in
``find_failing_operation`` and every ``mid`` probe of the binary search --
apply several operations as chained ``with_columns``, which polars fuses
and evaluates in parallel. When two of them fail with different first
lines, which error surfaces is a scheduling matter: roughly even at the
collect, so three faces landing the same way named the wrong column about
one run in twenty. The walk on the shape pinned here -- a lookup healed by
the filter whose first line differs from the break's, the real break, a
clean ``f64 * f64`` line, then the filter -- was: the healed lookup's own
line surfaces on the ``mid=1`` probe, so the search moves right; the
break's line surfaces on the ``mid=2`` probe, so the failing index is 2;
the exact-operation scan then breaks on the healed lookup's different line
before reaching 2 and fell back to that position. ``premium``, which
raised nothing on any frame, was printed under ``Failing column:`` at its
own line.

The fallback is gone. ``_find_exact_failing_operation`` answers ``-1`` --
not narrowed -- when no one-operation step reproduced the failure over a
prefix that collected clean; ``_blame_within_group(-1)`` names nothing,
and both finders treat that as bare. A name now comes only from a
one-operation step, which is deterministic. Pinned here at the finder
level over enough draws that the parent's coin cannot pass, and once for
the reader; the scan's "not narrowed" exits are pinned directly, for the
attribution finder (a different first line), for the base finder the
traced panel uses (a different class), and for a position no step of the
scan can confirm.
"""

from __future__ import annotations

from collections import Counter

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import (
    _REPLAY_MAX_ROWS,
    ErrorBoundaryFinder,
    _AttributionReplayFinder,
    replay_windows,
)

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what the message carries.
REFUSAL = "Not attributed:"
NAMED = "Failing column:"

# Enough draws that a name surfacing one run in twenty cannot stay hidden.
_DRAWS = 200


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _table(name: str) -> Table:
    """Build an age table covering 30, 40 and 50, registered under its own name."""
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _policies() -> pl.DataFrame:
    """Two policies; a status filter keeps the first.

    ``issue_age + dur_a`` misses the table on the second policy only -- the
    one the filter drops -- so a lookup keyed on it is healed by the filter.
    ``issue_age + dur_b`` misses on the first policy, the one that survives,
    so a lookup keyed on it is the real break. ``dur_ok`` misses nowhere.
    """
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "status": ["IF", "LAPSED"],
            "issue_age": [30, 40],
            "dur_a": [0, 59],
            "dur_b": [69, 0],
            "dur_ok": [0, 0],
            "sum_assured": [1000.0, 2000.0],
        }
    )


def _healed_break_clean_then_filter(
    suffix: str, *, real_break: bool = True
) -> ActuarialFrame:
    """Build the shape: a healed lookup, the break, a clean line, then the filter.

    The two lookups are on two tables, so the healed one's first line
    differs from the break's -- the shape that lets the scheduling decide
    which surfaces from a multi-operation probe.
    """
    healed_table = _table(f"parallel_probe_x_{suffix}")
    broken_table = _table(f"parallel_probe_b_{suffix}")
    af = ActuarialFrame(_policies())
    af.rate_x = healed_table.lookup(age=af.issue_age + af.dur_a)
    key = af.dur_b if real_break else af.dur_ok
    af.rate_b = broken_table.lookup(age=af.issue_age + key)
    af.premium = af.sum_assured * 0.01
    return af.filter(pl.col("status") == "IF")


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _sealed_finder(
    af: ActuarialFrame, raised: BaseException
) -> _AttributionReplayFinder:
    """Build the attribution finder over the one sealed window, as the search does."""
    windows = [window for window in replay_windows(af) if window.records]
    columns = [[record.column for record in window.records] for window in windows]
    assert columns == [["rate_x", "rate_b", "premium"]]
    return _AttributionReplayFinder(
        af, raised, max_rows=_REPLAY_MAX_ROWS, window=windows[0]
    )


# --- the defect ---------------------------------------------------------------


def test_the_clean_line_is_never_named_for_a_break_behind_the_filter() -> None:
    """The defect at the finder, over enough draws that the parent's coin cannot pass.

    Every draw is the same search on the same window. The answer used to
    move between bare, ``rate_b`` and ``premium`` with the scheduling, and
    ``premium`` is a wrong name. Now every draw is bare: no prefix of this
    window collects clean -- the healed lookup raises its own line on the
    unfiltered baseline -- so no one-operation step can reproduce
    anything, and no position stands in for one.
    """
    control = _healed_break_clean_then_filter("control", real_break=False)
    assert control.collect().height == 1
    af = _healed_break_clean_then_filter("finder")
    finder = _sealed_finder(af, _failure(af))

    answers: Counter[tuple[int, str | None]] = Counter()
    for _ in range(_DRAWS):
        index, operation, _last_good = finder.find_failing_operation()
        answers[(index, None if operation is None else operation.column)] += 1

    split = dict(answers)
    assert not any(column == "premium" for _index, column in answers), split
    assert split == {(-1, None): _DRAWS}, split


def test_the_reader_never_sees_the_clean_line() -> None:
    """What the user reads on the shape: bare, and ``premium`` nowhere in it.

    One run cannot be red at the parent with certainty -- the wrong name
    reached the reader about one run in forty there -- so the pin above is
    the one that carries the defect; this one is the record of the message.
    """
    message = str(_failure(_healed_break_clean_then_filter("reader")))

    assert NAMED not in message
    assert REFUSAL not in message
    assert "'premium'" not in message


# --- the scan's "not narrowed" exits, pinned directly -------------------------


def test_a_scan_that_breaks_on_a_different_line_is_not_narrowed() -> None:
    """The exit itself, for the attribution finder: ``-1``, and ``-1`` blames nothing.

    The scan is handed the binary search's position, 2, and the pristine
    baseline. Its first one-operation step raises the healed lookup's own
    first line, which is not the original's, so nothing past it can be
    tested; it used to answer the position it was handed.
    """
    af = _healed_break_clean_then_filter("exit_line")
    finder = _sealed_finder(af, _failure(af))

    narrowed = finder._find_exact_failing_operation(2, finder.original_df, -1)  # noqa: SLF001
    assert narrowed == -1
    assert finder._blame_within_group(-1) is None  # noqa: SLF001


def test_a_scan_that_breaks_on_a_different_class_is_not_narrowed_either() -> None:
    """The same exit in the base finder the traced panel uses; "different" is the class.

    A strict cast raises ``InvalidOperationError``; the jagged subtraction
    behind it raises ``ShapeError``, the original. The base finder matches
    on class alone, so the scan breaks on the cast, and it answers ``-1``
    rather than the position it was handed.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "text": ["x"],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
            }
        )
    )
    af.bad_cast = af.text.polars_native().cast(pl.Int64, strict=True)
    af.broken = af.six - af.three
    original = pl.exceptions.ShapeError("list lengths differed at index 0: 6 != 3")
    finder = ErrorBoundaryFinder(af, original)
    assert [[r.column for r in group] for group in finder.groups] == [
        ["bad_cast"],
        ["broken"],
    ]

    narrowed = finder._find_exact_failing_operation(1, finder.original_df, -1)  # noqa: SLF001
    assert narrowed == -1


def test_a_position_no_step_of_the_scan_confirms_is_not_narrowed() -> None:
    """A position over a window whose every step collects clean is answered ``-1``.

    The position came from a multi-operation probe this scan could not
    reproduce one operation at a time, so it is not evidence either; the
    scan used to answer it back.
    """
    af = ActuarialFrame(_policies())
    af.premium = af.sum_assured * 0.01
    finder = ErrorBoundaryFinder(af, pl.exceptions.ShapeError("never raised here"))

    narrowed = finder._find_exact_failing_operation(0, finder.original_df, -1)  # noqa: SLF001
    assert narrowed == -1
