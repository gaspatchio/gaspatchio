# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Two definitions that reproduce one failure name neither of them.

The collect-time replay names the first recorded calculation that raises the
original error's class and leading line. "First" is the order the model wrote
its columns in, and that is not evidence about which of them failed: two
lookups on one table with one key name raise byte-identical first lines, and
when the earlier one is healed at run time by a later ``filter()``'s predicate
pushdown, the scan named it -- a column that never failed, at its own source
line. The same shape with a jagged ``list_pow`` did the same, and its first
line carries no identity at all.

So after a candidate is found, every later calculation in the window is
replayed on its own over the prefix before the candidate. A second
reproduction of the same class and leading line makes the window ambiguous,
and the error arrives with one line saying so and no column named. Pinned
here: the two attack shapes and their controls, the shapes that stay right,
the shapes that stay bare, the one right answer the refusal spends, and that
neither the refusal path nor the rendering of either outcome ever turns one
error into two.
"""

from __future__ import annotations

import dataclasses
import traceback
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import (
    AmbiguousAttribution,
    SearchOutcome,
    _AttributionReplayFinder,
    search_collect_failure,
)
from gaspatchio.errors.formatting_errors import (
    _handle_plan_lowering_panic,
    _refusal_line,
)
from gaspatchio.errors.suggestions import ErrorSuggestionEngine
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan

if TYPE_CHECKING:
    from collections.abc import Callable

# The label the refusal line opens with, spelled out here rather than
# imported: these tests are the record of what a user reads.
REFUSAL = "Not attributed:"
NAMED = "Failing column:"

# The refusal line as it would read if it carried every word the retired
# substring chain turned on. The real line carries none of them and the
# second half of the test below pins that; this one is the attack the
# router has to survive on its own terms rather than on the line's good
# manners.
POISONED_LINE = (
    "\n\n  Not attributed: null date time cast path missing lengths "
    "out of bounds parse assumption lookup"
)


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
    Both key expressions carry the output name ``issue_age``, so the two
    refusals open with the same first line.
    """
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "status": ["IF", "LAPSED"],
            "issue_age": [30, 40],
            "dur_a": [0, 59],
            "dur_b": [69, 0],
            "dur_ok": [0, 0],
        }
    )


def _in_force(af: ActuarialFrame) -> ActuarialFrame:
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


# --- the attack shapes ------------------------------------------------------


def test_a_healthy_lookup_healed_by_a_later_filter_is_not_named() -> None:
    """The defect: the healthy ``rate_a`` was named at its own line.

    Both lookups raise the same first line on the unfiltered baseline;
    only ``rate_b`` raises in the plan the user collected. The control
    proves ``rate_a`` sound: the same model with ``rate_b`` healthy
    collects.
    """
    table = _table("ambiguity_healthy_first")
    control = ActuarialFrame(_policies())
    control.rate_a = table.lookup(age=control.issue_age + control.dur_a)
    control.rate_b = table.lookup(age=control.issue_age + control.dur_ok)
    assert _in_force(control).collect().height == 1

    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)
    af = _in_force(af)

    message = str(_failure(af))
    _refused(message, "rate_a", "rate_b")


def test_a_jagged_list_pow_healed_by_a_later_filter_is_not_named() -> None:
    """The second attack shape: a first line with no identity in it at all."""
    lists = pl.DataFrame(
        {
            "status": ["IF", "LAPSED"],
            "p": [[1.0, 2.0], [1.0, 2.0]],
            "q_a": [[1.0, 2.0], [1.0, 2.0, 3.0]],
            "q_b": [[1.0, 2.0, 3.0], [1.0, 2.0]],
            "q_ok": [[1.0, 2.0], [1.0, 2.0]],
        }
    )
    control = ActuarialFrame(lists)
    control.pow_a = control.p**control.q_a
    control.pow_b = control.p**control.q_ok
    assert _in_force(control).collect().height == 1

    af = ActuarialFrame(lists)
    af.pow_a = af.p**af.q_a
    af.pow_b = af.p**af.q_b
    af = _in_force(af)

    message = str(_failure(af))
    _refused(message, "pow_a", "pow_b")


def test_the_break_written_first_is_refused_too() -> None:
    """The same two records in the other order are the same evidence.

    ``rate_b`` is the real break and is written first, so the scan lands
    on it; ``rate_a`` is healthy and written second, and replayed on its
    own over the baseline it reproduces the identical first line. The
    replay cannot tell this model from the one above -- the order the
    lines were written in is all that differs -- so it refuses here as
    well. Keeping this answer would mean keeping the wrong one above.
    """
    table = _table("ambiguity_broken_first")
    af = ActuarialFrame(_policies())
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af = _in_force(af)

    message = str(_failure(af))
    _refused(message, "rate_b", "rate_a")


def test_two_real_breaks_with_one_first_line_are_refused() -> None:
    """The one right answer the refusal spends.

    Both lookups genuinely fail and the plan hits the first; a replay
    that named it would be right. It cannot know that it would be, so it
    names neither -- and says both reproduce, which is true.
    """
    table = _table("ambiguity_both_broken")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    message = str(_failure(af))
    _refused(message, "rate_a", "rate_b")


def test_two_misses_on_different_keys_are_refused_rather_than_wrong() -> None:
    """With the sampled keys off the first line, these lines now agree.

    ``rate_a`` misses age 99 on the dropped policy; ``rate_b`` misses age
    100 on the kept one. The keys used to sit on the first line and keep
    the two apart, which left this shape bare. Now the first line names
    the table and the key column only, the two agree, and it is the
    ambiguity pass -- not the line -- that keeps ``rate_a`` from being
    named.
    """
    table = _table("ambiguity_distinct_keys")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b + 1)
    af = _in_force(af)

    message = str(_failure(af))
    _refused(message, "rate_a", "rate_b")


# --- the shapes that stay right -------------------------------------------


def test_a_break_written_after_the_filter_is_still_named() -> None:
    """Across a seal the live window answers alone, and it holds one record."""
    table = _table("ambiguity_across_seal")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af = _in_force(af)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    message = str(_failure(af))
    assert "Failing column: 'rate_b'" in message
    assert REFUSAL not in message
    assert "'rate_a'" not in message


def test_a_later_calculation_that_reads_the_candidate_is_not_a_rival() -> None:
    """Replayed with the candidate excluded, a dependant cannot find its input.

    ``doubled`` reads ``broken``; over the prefix before ``broken`` it
    raises a missing-column error, which is a different class, not a
    second reproduction. ``broken`` is named.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
            }
        )
    )
    af.broken = af.six - af.three
    af.doubled = af.broken * 2.0

    message = str(_failure(af))
    assert "Failing column: 'broken'" in message
    assert REFUSAL not in message


def test_a_later_calculation_whose_line_differs_only_in_digits_is_a_rival() -> None:
    """Same class, a line differing only in digits: ``6 != 3`` against ``3 != 6``.

    Both are real breaks. The exact compare kept them apart and named the
    first; the rival test masks digits now (see the jagged shapes below),
    so the second is seen and the window is refused -- the accepted trade,
    on a shape this file used to pin the other way.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
            }
        )
    )
    af.broken = af.six - af.three
    af.other = af.three - af.six

    message = str(_failure(af))
    _refused(message, "broken", "other")


def test_a_later_calculation_with_a_different_first_line_is_not_a_rival() -> None:
    """Same class, a line that differs in its words: no digit mask reaches it.

    ``other`` raises the same class as ``broken`` with a first line that
    differs beyond its digits, so it is not a rival under either compare
    and ``broken`` is named.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
                "text": ["x"],
            }
        )
    )
    af.broken = af.six - af.three
    af.other = af.text.polars_native().cast(pl.Int64, strict=True)

    message = str(_failure(af))
    assert "Failing column: 'broken'" in message
    assert REFUSAL not in message
    assert "'other'" not in message


# --- the shapes that stay bare ---------------------------------------------


def test_lookups_keyed_on_differently_named_columns_stay_bare() -> None:
    """Different key names, different first lines: the healthy one never matches.

    Bare deterministically now. ``rate_b``'s name used to surface about
    one run in ten: the finder's multi-operation probes carry both
    lookups, which of the two errors surfaces from one is scheduling, and
    the exact-operation scan, breaking on ``rate_a``'s different line,
    fell back to the position the binary search had handed it. That
    fallback is gone -- a name comes only from a one-operation step over
    a prefix that collected clean, and no prefix here collects, because
    ``rate_a`` raises its own line on the unfiltered baseline. Naming
    ``rate_b`` on evidence would need a per-record candidate search;
    until then the answer is bare, which is the cap's direction.
    """
    table = _table("ambiguity_key_names")
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "status": ["IF", "LAPSED"],
                "age_a": [30, 99],
                "age_b": [99, 40],
            }
        )
    )
    af.rate_a = table.lookup(age=af.age_a)
    af.rate_b = table.lookup(age=af.age_b)
    af = _in_force(af)

    message = str(_failure(af))
    assert NAMED not in message
    assert REFUSAL not in message


def test_lookups_on_different_tables_stay_bare() -> None:
    """Different table names, different first lines, nothing reproduces.

    Bare deterministically now, for the reason
    ``test_lookups_keyed_on_differently_named_columns_stay_bare`` gives:
    the healthy lookup's own line breaks the exact-operation scan, and no
    position stands in for a step that reproduced.
    """
    healthy_table = _table("ambiguity_table_a")
    broken_table = _table("ambiguity_table_b")
    af = ActuarialFrame(_policies())
    af.rate_a = healthy_table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = broken_table.lookup(age=af.issue_age + af.dur_b)
    af = _in_force(af)

    message = str(_failure(af))
    assert NAMED not in message
    assert REFUSAL not in message


def _jagged_pair(b_1: list[list[float]], b_2: list[list[float]]) -> ActuarialFrame:
    """Two list multiplies over one left operand; the right operands are the shape's."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "status": ["LAPSED", "IF"][: len(b_1)],
                "a": [[1.0, 2.0]] * len(b_1),
                "b_1": b_1,
                "b_2": b_2,
            }
        )
    )
    af.j1 = af.a * af.b_1
    af.j2 = af.a * af.b_2
    return af


def test_a_jagged_multiply_healed_by_a_later_filter_is_not_named() -> None:
    """The ShapeError door, closed: rival lines are compared with digits masked.

    The same shape as the two attacks above, built on plain list
    arithmetic. A ``ShapeError``'s first line carries the row index of the
    frame it ran on: the rival's jag sits at index 1 of the unfiltered
    baseline and at index 0 of the plan the user collected, so the two
    first lines differed and the ambiguity pass could not see the rival.
    The rival test now masks digits before comparing -- the candidate's
    own matcher stays exact -- so ``j2`` is seen, the window is ambiguous,
    and the healthy ``j1`` is no longer named.
    """
    af = _jagged_pair([[1.0, 2.0, 3.0], [1.0, 2.0]], [[1.0, 2.0], [1.0, 2.0, 3.0]])
    af = _in_force(af)

    message = str(_failure(af))
    _refused(message, "j1", "j2")


def test_two_jagged_multiplies_broken_on_different_rows_are_refused() -> None:
    """The accepted trade: two real breaks whose lines differ only in the row index.

    Both multiplies genuinely fail, ``j1`` at index 0 and ``j2`` at index 1,
    and the plan hits one of them; the mask makes the two first lines one,
    so the window is refused rather than the first named. The same trade
    ``test_two_real_breaks_with_one_first_line_are_refused`` makes for the
    lookup line, and the cost of closing the door above.
    """
    af = _jagged_pair([[1.0, 2.0, 3.0], [1.0, 2.0]], [[1.0, 2.0], [1.0, 2.0, 3.0]])

    message = str(_failure(af))
    _refused(message, "j1", "j2")


def test_two_jagged_multiplies_broken_by_different_lengths_are_refused() -> None:
    """The other digit: ``2 != 3`` against ``2 != 4`` on the same row."""
    af = _jagged_pair([[1.0, 2.0, 3.0]], [[1.0, 2.0, 3.0, 4.0]])

    message = str(_failure(af))
    _refused(message, "j1", "j2")


def test_the_rival_matcher_masks_digits_and_the_candidate_matcher_does_not() -> None:
    """The mechanism: one finder, two matchers, and only the rival's is loose.

    A looser rival test can only add rivals, and a name is returned only
    when there are none, so masking can only refuse more and never name
    more. The candidate is found by the exact matcher for every line of
    gaspatchio's own: a kernel line whose digits differ is not a candidate.
    The one exception is the closed allowlist of Polars' batch-counted
    lines, read by template: Polars' list-length line at
    another index, or with other lengths, is the same failure to the
    candidate matcher too, and to nothing looser than its template.
    """
    af = _jagged_pair([[1.0, 2.0, 3.0], [1.0, 2.0]], [[1.0, 2.0], [1.0, 2.0, 3.0]])
    original = pl.exceptions.ShapeError("list lengths differed at index 0: 2 != 3")
    finder = _AttributionReplayFinder(af, original)
    same_digits = pl.exceptions.ShapeError("list lengths differed at index 0: 2 != 3")
    other_digits = pl.exceptions.ShapeError("list lengths differed at index 1: 2 != 3")
    other_lengths = pl.exceptions.ShapeError("list lengths differed at index 0: 2 != 4")
    other_words = pl.exceptions.ShapeError("list lengths differed at index 0: 2 vs 3")
    other_class = pl.exceptions.ComputeError("list lengths differed at index 1: 2 != 3")
    trailing = pl.exceptions.ShapeError("list lengths differed at index 1: 2 != 3 (x)")

    assert finder._is_same_error_type(same_digits)  # noqa: SLF001 -- the matchers under test
    assert finder._is_same_error_type(other_digits)  # noqa: SLF001
    assert finder._is_same_error_type(other_lengths)  # noqa: SLF001
    assert not finder._is_same_error_type(other_words)  # noqa: SLF001
    assert not finder._is_same_error_type(other_class)  # noqa: SLF001
    assert not finder._is_same_error_type(trailing)  # noqa: SLF001
    assert finder._same_line_exactly(same_digits)  # noqa: SLF001
    assert not finder._same_line_exactly(other_digits)  # noqa: SLF001
    assert finder._is_rival_error(same_digits)  # noqa: SLF001
    assert finder._is_rival_error(other_digits)  # noqa: SLF001
    assert not finder._is_rival_error(other_words)  # noqa: SLF001
    assert not finder._is_rival_error(other_class)  # noqa: SLF001

    ours = pl.exceptions.ComputeError(
        "the plugin failed with message: Lookup on table 'mort_7' found no "
        "rate for 3 keys"
    )
    ours_elsewhere = pl.exceptions.ComputeError(
        "the plugin failed with message: Lookup on table 'mort_7' found no "
        "rate for 4 keys"
    )
    own_finder = _AttributionReplayFinder(af, ours)

    assert own_finder._is_same_error_type(ours)  # noqa: SLF001
    assert not own_finder._is_same_error_type(ours_elsewhere)  # noqa: SLF001
    assert own_finder._is_rival_error(ours_elsewhere)  # noqa: SLF001


# --- the refusal never makes the error worse ---------------------------------


def test_a_raising_replay_inside_the_pass_leaves_the_original_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One error in, one error out: the refusal path is guarded like the scan."""

    def _explode(
        _self: _AttributionReplayFinder, _index: int
    ) -> list[CalculationRecord]:
        msg = "the replay itself broke"
        raise RuntimeError(msg)

    monkeypatch.setattr(_AttributionReplayFinder, "later_reproductions", _explode)
    table = _table("ambiguity_raising_pass")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    raised = _failure(af)

    assert isinstance(raised, pl.exceptions.ComputeError)
    message = str(raised)
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert NAMED not in message
    assert REFUSAL not in message
    assert "the replay itself broke" not in message


def test_a_record_without_a_source_still_renders_in_the_line() -> None:
    """An odd record -- no span -- is listed by name alone; the line still closes."""
    with_source = _record(
        "rate_b",
        SourceSpan(
            file="model.py",
            line=17,
            end_line=17,
            function="main",
            statement="af.rate_b = T.lookup(age=af.issue_age + af.dur_b)",
            rhs="T.lookup(age=af.issue_age + af.dur_b)",
            target_literal=True,
        ),
    )
    without = _record("rate_a", None)

    line = _refusal_line(AmbiguousAttribution(reproducing=(without, with_source)))

    assert line.startswith("\n\n  Not attributed: 2 definitions reproduce")
    assert "('rate_a', 'rate_b' at model.py:17)" in line
    assert line.count("\n") == 2


def test_the_refusal_is_appended_exactly_once() -> None:
    """Re-entering the handler must not print the line twice."""
    table = _table("ambiguity_once")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    message = str(_failure(af))
    assert message.count(REFUSAL) == 1


def test_a_refused_panic_is_converted_and_carries_the_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The panic door converts on reproduction, and a refusal is a reproduction."""

    class PanicException(BaseException):
        """What pyo3 raises; matched by type name, so the name is the contract."""

    refusal = AmbiguousAttribution(reproducing=(_record("a", None), _record("b", None)))
    monkeypatch.setattr(
        "gaspatchio.errors.boundary.search_collect_failure",
        lambda _frame, _exception: SearchOutcome(attribution=refusal, last_good=None),
    )
    panic = PanicException("no valid schema can be derived for the branch")
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))

    with pytest.raises(pl.exceptions.SchemaError) as excinfo:
        _handle_plan_lowering_panic(af, panic)

    assert excinfo.value.__cause__ is panic
    message = str(excinfo.value)
    assert message.startswith("no valid schema can be derived")
    assert REFUSAL in message
    assert NAMED not in message


# --- the rendering never makes the error worse -------------------------------


def _rendering_broke(*_args: object, **_kwargs: object) -> str:
    msg = "rendering broke"
    raise TypeError(msg)


def _arrived_alone(raised: BaseException) -> None:
    """Assert ``raised`` carries no chained error and its traceback shows none."""
    assert raised.__context__ is None
    assert raised.__cause__ is None
    rendered = "".join(traceback.format_exception(raised))
    assert "another exception occurred" not in rendered
    assert "rendering broke" not in rendered


def test_a_raising_formula_reader_leaves_the_named_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The block reads ``graph_builder._as_written``; forced to raise, no block.

    The degraded output is today's for an unattributed error: the plain
    message, one error, the user's. A block printed under the lowered
    label instead would claim the as-written formula was not recorded,
    and it was -- the reader failed -- so the block is dropped whole.
    """
    monkeypatch.setattr(
        "gaspatchio.frame.graph.graph_builder._as_written", _rendering_broke
    )
    table = _table("guard_named")
    af = ActuarialFrame(_policies())
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    raised = _failure(af)

    assert isinstance(raised, pl.exceptions.ComputeError)
    message = str(raised)
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert NAMED not in message
    assert REFUSAL not in message
    _arrived_alone(raised)


def test_a_raising_refusal_renderer_leaves_the_refused_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal's one line, forced to raise: the error arrives without it."""
    monkeypatch.setattr(
        "gaspatchio.errors.formatting_errors._refusal_line", _rendering_broke
    )
    table = _table("guard_refused")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    raised = _failure(af)

    assert isinstance(raised, pl.exceptions.ComputeError)
    message = str(raised)
    assert message.startswith("the plugin failed with message: Lookup on table")
    assert REFUSAL not in message
    assert NAMED not in message
    _arrived_alone(raised)


def test_a_panic_whose_attribution_cannot_be_rendered_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The panic door keeps its fallback contract when the renderer fails.

    Reproduction earns the conversion, and the conversion exists to carry
    the attribution. When that text cannot be rendered there is nothing to
    carry, so the panic passes through untouched -- the door an
    unattributed panic takes -- rather than being rewritten into a
    ``SchemaError`` that merely looks diagnosed. One error, the user's,
    with nothing chained to it.
    """

    class PanicException(BaseException):
        """What pyo3 raises; matched by type name, so the name is the contract."""

    refusal = AmbiguousAttribution(reproducing=(_record("a", None), _record("b", None)))
    monkeypatch.setattr(
        "gaspatchio.errors.boundary.search_collect_failure",
        lambda _frame, _exception: SearchOutcome(attribution=refusal, last_good=None),
    )
    monkeypatch.setattr(
        "gaspatchio.errors.formatting_errors._attribution_text", _rendering_broke
    )
    panic = PanicException("no valid schema can be derived for the branch")
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))

    with pytest.raises(PanicException) as excinfo:
        _handle_plan_lowering_panic(af, panic)

    assert excinfo.value is panic
    _arrived_alone(panic)


# --- the result, and its words ----------------------------------------------


def _ambiguous_lookup(name: str) -> ActuarialFrame:
    table = _table(name)
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)
    return af


def _ambiguous_pow() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "p": [[1.0, 2.0]],
                "q_a": [[1.0, 2.0, 3.0]],
                "q_b": [[1.0, 2.0, 3.0]],
            }
        )
    )
    af.pow_a = af.p**af.q_a
    af.pow_b = af.p**af.q_b
    return af


def _record(column: str, source: SourceSpan | None) -> CalculationRecord:
    return CalculationRecord(
        column=column,
        ordinal=1,
        operation_id=0,
        node=Col(column),
        expr=pl.col(column),
        dtype=None,
        source=source,
        origin="assignment",
    )


def test_the_search_returns_the_refusal_with_both_records() -> None:
    """The finder's answer is the records themselves, the scan's candidate first."""
    table = _table("ambiguity_result")
    af = ActuarialFrame(_policies())
    af.rate_a = table.lookup(age=af.issue_age + af.dur_a)
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)
    af = _in_force(af)

    result = search_collect_failure(af, _failure(af)).attribution

    assert isinstance(result, AmbiguousAttribution)
    assert [record.column for record in result.reproducing] == ["rate_a", "rate_b"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reproducing = ()  # type: ignore[misc]


def test_a_window_with_one_reproduction_still_returns_the_record() -> None:
    """The ``None``/record contract is untouched where nothing is ambiguous."""
    table = _table("ambiguity_single")
    af = ActuarialFrame(_policies())
    af.rate_b = table.lookup(age=af.issue_age + af.dur_b)

    result = search_collect_failure(af, _failure(af)).attribution

    assert isinstance(result, CalculationRecord)
    assert result.column == "rate_b"


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: _ambiguous_lookup("ambiguity_router_lookup"), id="lookup"),
        pytest.param(_ambiguous_pow, id="list_pow"),
    ],
)
def test_the_refusal_line_moves_no_advice(
    build: Callable[[], ActuarialFrame],
) -> None:
    """The advice is the same with the line, with a poisoned line, and without.

    The router chooses a family from the exception's class, the failing
    column's lowering and the operand dtypes, and reads no part of the
    message, so no wording appended to one can move the advice beneath it.
    Pinned on a record the router does ANSWER -- an ordinary column
    reference earns no family, and an equality between two empty lists
    pins nothing -- and against a line carrying every word the retired
    substring chain turned on, on both attack shapes: a lookup miss and a
    jagged kernel.
    """
    raised = _failure(build())
    message = str(raised)
    assert REFUSAL in message
    bare, _, line = message.partition("\n\n  Not attributed:")
    engine = ErrorSuggestionEngine()
    record = dataclasses.replace(
        _record("x", None),
        node=Call(
            name="lookup",
            args=(Col("attained_age"),),
            attrs=(("table", "refusal_line_probe"),),
        ),
    )

    with_line = engine.suggest_fixes(Exception(message), record, ["issue_age"])
    poisoned_message = Exception(bare + POISONED_LINE)
    poisoned = engine.suggest_fixes(poisoned_message, record, ["issue_age"])
    without = engine.suggest_fixes(Exception(bare), record, ["issue_age"])

    assert without, "the shape must earn advice, or 'unchanged' pins nothing"
    assert with_line == without
    assert poisoned == without
    lowered = line.lower()
    for word in (
        "not found",
        "lengths",
        "cast",
        "convert",
        "mismatch",
        "date",
        "time",
        "parse",
        "null",
        "missing",
        "nan",
        "path",
        "out of bounds",
        "assumption",
        "lookup",
    ):
        assert word not in lowered.split(" (")[0], (word, line)
