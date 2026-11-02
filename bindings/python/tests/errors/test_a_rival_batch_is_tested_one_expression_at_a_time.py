# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A later batch's rivals are found one expression at a time.

After the scan names a candidate, ``later_reproductions`` replays every
later operation over the prefix before the candidate, and a second
reproduction of the class and leading line makes the window ambiguous
(``test_ambiguous_attribution.py``). A later multi-column ``with_columns``
used to be narrowed the way the candidate is, by widening prefixes of its
expressions -- and that scan stops at the first expression raising a
different class or line, because for the CANDIDATE a different failure
masks every wider prefix and naming nothing is the safe direction. For a
rival, "naming nothing" means "no rival" and the healed candidate stands:
a strict cast failing only on the dropped row, first in a batch whose
second expression is the real break with the candidate's own first line,
hid that break, and the healed lookup written before the batch was named
at both ends.

Siblings in one call never see each other's values -- every expression is
evaluated against the frame as it stood before the call -- so each
expression of a later batch is now tested ALONE over the prefix, which is
exactly what the live call computed for it, and every one that reproduces
is a rival. The candidate's own narrowing keeps widening prefixes: the
candidate must be the FIRST reproducing expression in call order, and a
different failure ahead of it means that cannot be told. Pinned here: the
shape and its control, the batch in the other order, both siblings
reproducing, the mechanism, and the two scans differing on purpose.
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
)

# The labels a user reads, spelled out rather than imported: these tests are
# the record of what the message carries.
REFUSAL = "Not attributed:"
NAMED = "Failing column:"


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
    ``text`` casts to an integer on the first policy only, so a strict cast
    of it fails on the dropped row alone and is healed by the filter too.
    """
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "status": ["IF", "LAPSED"],
            "issue_age": [30, 40],
            "dur_a": [0, 59],
            "dur_b": [69, 0],
            "dur_ok": [0, 0],
            "text": ["1", "x"],
        }
    )


def _healed_then_a_masked_batch(
    name: str, *, real_break: bool = True, cast_first: bool = True
) -> ActuarialFrame:
    """Build the shape: a healed lookup, then one batch holding a cast and the break.

    The cast raises a different class; the break raises the healed
    lookup's own first line. ``cast_first`` puts the cast ahead of the
    break in the batch, where widening prefixes met it first.
    """
    table = _table(name)
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    bad_cast = (
        af.text.polars_native()
        .cast(pl.Int64, strict=True)
        .polars_native()
        .alias("bad_cast")
    )
    key = af.dur_b if real_break else af.dur_ok
    rate_b = table.lookup(age=af.issue_age + key).alias("rate_b")
    batch = (bad_cast, rate_b) if cast_first else (rate_b, bad_cast)
    af = af.with_columns(*batch)
    return af.filter(pl.col("status") == "IF")


def _failure(af: ActuarialFrame) -> BaseException:
    """Collect ``af``, which must fail, and return what it raised."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the class is the shape's
        af.collect()
    return excinfo.value


def _refused(message: str, *columns: str) -> None:
    """Assert ``message`` names no column and lists ``columns`` as reproducing."""
    assert REFUSAL in message, message
    assert NAMED not in message, message
    line = next(line for line in message.splitlines() if REFUSAL in line)
    assert f"{len(columns)} definitions reproduce" in line, line
    for column in columns:
        assert repr(column) in line, line
    assert line.endswith("so none is named as the one that failed."), line


def _sealed_finder(
    af: ActuarialFrame, raised: BaseException
) -> _AttributionReplayFinder:
    """Build the attribution finder over the one sealed window, as the search does."""
    windows = [window for window in replay_windows(af) if window.records]
    columns = [[record.column for record in window.records] for window in windows]
    assert columns == [["rate_a", "bad_cast", "rate_b"]]
    return _AttributionReplayFinder(
        af, raised, max_rows=_REPLAY_MAX_ROWS, window=windows[0]
    )


# --- the defect and its control ---------------------------------------------


def test_a_rival_masked_by_a_different_class_sibling_is_still_found() -> None:
    """The defect: ``rate_a`` was named, at its own line, for ``rate_b``'s failure.

    ``rate_a`` and the cast are both healed by the filter; the control
    proves it. ``rate_b`` is the real break and reproduces ``rate_a``'s
    first line on the unfiltered baseline, but it sits behind the cast in
    its batch, and widening prefixes stopped at the cast. Tested alone,
    it is a rival, and the window is refused.
    """
    control = _healed_then_a_masked_batch("batch_rival_control", real_break=False)
    assert control.collect().height == 1

    message = str(_failure(_healed_then_a_masked_batch("batch_rival_masked")))

    _refused(message, "rate_a", "rate_b")


def test_the_batch_in_the_other_order_refuses_too() -> None:
    """With the break ahead of the cast, both scans found it; the answer is the same."""
    af = _healed_then_a_masked_batch("batch_rival_reversed", cast_first=False)

    message = str(_failure(af))

    _refused(message, "rate_a", "rate_b")


def test_two_reproducing_siblings_are_both_listed() -> None:
    """Every reproducing expression of a later batch is a rival, not only the first."""
    table = _table("batch_rival_pair")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af = af.with_columns(
        table.lookup(age=af.issue_age + af.dur_b).alias("rate_b"),
        table.lookup(age=af.issue_age + af.dur_b).alias("rate_c"),
    )
    af = af.filter(pl.col("status") == "IF")

    message = str(_failure(af))

    _refused(message, "rate_a", "rate_b", "rate_c")


# --- the mechanism ------------------------------------------------------------


def test_later_reproductions_lists_the_masked_rival() -> None:
    """The finder's own answer: the batch behind the candidate holds one rival."""
    af = _healed_then_a_masked_batch("batch_rival_mechanism")
    finder = _sealed_finder(af, _failure(af))

    rivals = finder.later_reproductions(0)

    assert [rival.column for rival in rivals] == ["rate_b"]


def test_the_candidate_scan_and_the_rival_scan_differ_on_purpose() -> None:
    """Over the same prefix, the same batch: masked as a candidate, found as a rival.

    Widening prefixes meet the cast first and stop, naming nothing --
    right for a candidate, which must be the first reproducing expression
    in call order. Each expression alone finds ``rate_b`` -- right for a
    rival, which is any reproducing expression.
    """
    af = _healed_then_a_masked_batch("batch_rival_two_scans")
    finder = _sealed_finder(af, _failure(af))
    prefix = finder.original_df.lazy()
    batch = finder.groups[1]
    assert [record.column for record in batch] == ["bad_cast", "rate_b"]

    as_candidate = finder._reproducing_calculation(prefix, batch)  # noqa: SLF001
    as_rivals = finder._reproductions_alone(prefix, batch)  # noqa: SLF001

    assert as_candidate is None
    assert [rival.column for rival in as_rivals] == ["rate_b"]
