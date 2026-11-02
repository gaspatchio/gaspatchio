# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A structural operation seals its attribution window; it does not lose it.

``filter()`` and ``sort()`` are the two structural operations that do not
resolve the schema on the way past, so a plan carrying a broken expression
survives them and fails at ``collect()`` instead. Both moved the attribution
cursor to the end of the log and dropped the baseline the window had opened
over, which left ``_attribution_ops()`` empty and the failure bare: the same
break, collected without the filter, named its column and its line.

What the cursor was protecting against is real -- calculations recorded
before a structural operation cannot be replayed against the plan that
FOLLOWS it. Replay never used that plan. It replays against ``_baseline_df``,
the snapshot the window opened over, and a sealed window plus its own
baseline reconstructs exactly the plan the frame held one step before the
filter. That plan is a plan the model really built, so an error the replay
reproduces there -- same class, same leading message line -- came from the
calculation it names.

Pinned here: the live window still answers first, a sealed window answers
when it does not, a healthy calculation is never blamed for a neighbour's
failure, and a successful collect still clears every suspect.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.errors.boundary import (
    _REPLAY_MAX_ROWS,
    _AttributionReplayFinder,
    replay_windows,
)
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _frame() -> ActuarialFrame:
    """Three policies, one string column that cannot take part in arithmetic."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "product_code": ["TERM", "TERM", "WL"],
                "sum_assured": [250_000.0, 100_000.0, 50_000.0],
                "mortality_rate": [0.001, 0.002, 0.003],
                "status": ["IF", "LAPSED", "IF"],
            }
        )
    )


def _in_force(af: ActuarialFrame) -> ActuarialFrame:
    return af.filter(pl.col("status") == "IF")


def test_a_filter_after_the_break_still_names_the_column() -> None:
    """The defect itself: the same break, one filter later, was arriving bare."""
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'reserve_factor'" in message
    assert excinfo.value._column_attributed is True  # noqa: SLF001


def test_a_sort_after_the_break_still_names_the_column() -> None:
    """``sort`` is the other operation that lets a broken plan reach collect."""
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    af = af.sort("policy_id")

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    assert "Failing column: 'reserve_factor'" in str(excinfo.value)


def test_two_structural_operations_deep_still_names_the_column() -> None:
    """One sealed window is not the contract -- every sealed window is."""
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    af = _in_force(af)
    af.headroom = af.sum_assured * 0.5
    af = af.sort("policy_id")

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'reserve_factor'" in message
    assert "Failing column: 'headroom'" not in message


def test_the_line_that_wrote_the_column_survives_the_filter() -> None:
    """``At:`` comes off the sealed record, so the filter must not cost it."""
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    expected_line = af._calculations[-1].source.line  # noqa: SLF001
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert f"{Path(__file__).name}:{expected_line}" in message


def test_the_live_window_answers_before_any_sealed_one() -> None:
    """A break after the filter is the live window's, and it is asked first."""
    af = _frame()
    af.healthy = af.sum_assured * 2.0
    af = _in_force(af)
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'reserve_factor'" in message
    assert "Failing column: 'healthy'" not in message


def test_a_healthy_calculation_before_the_filter_is_never_blamed() -> None:
    """Reaching further back must not mean blaming further back."""
    af = _frame()
    af.healthy = af.sum_assured * 2.0
    af.also_healthy = af.mortality_rate * 3.0
    af = _in_force(af)
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'healthy'" not in message
    assert "Failing column: 'also_healthy'" not in message


def test_a_successful_collect_clears_every_sealed_window() -> None:
    """A run that worked proves every recorded calculation sound, sealed or not."""
    af = _frame()
    af.healthy = af.sum_assured * 2.0
    af = _in_force(af)
    af.collect()

    assert af._attribution_ops() == []  # noqa: SLF001
    assert af._sealed_windows == []  # noqa: SLF001


def test_a_filter_still_advances_the_cursor() -> None:
    """The cursor semantics are unchanged -- sealing is what was added."""
    af = _frame()
    af.healthy = af.sum_assured * 2.0
    af = _in_force(af)

    assert af._attribution_ops() == []  # noqa: SLF001
    assert len(af._calculations) == 1  # noqa: SLF001
    assert len(af._sealed_windows) == 1  # noqa: SLF001


def test_the_kill_switch_still_refuses_to_diagnose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``AF_ERROR_MODE=off`` stops the diagnosis, sealed windows included."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    assert "Failing column" not in str(excinfo.value)
    assert not hasattr(excinfo.value, "_column_attributed")


def test_materialize_leaves_no_sealed_window_behind() -> None:
    """A frozen plan ran: its suspects go, while the log it accounts for stays."""
    af = _frame()
    af.healthy = af.sum_assured * 2.0
    af = _in_force(af)
    assert len(af._sealed_windows) == 1  # noqa: SLF001

    af = af.materialize()

    assert af._sealed_windows == []  # noqa: SLF001
    columns = [
        entry.column
        for entry in af._calculations  # noqa: SLF001
        if isinstance(entry, CalculationRecord)
    ]
    assert columns == ["healthy"]


def _raw_frame() -> ActuarialFrame:
    """The same policies, with ``sum_assured`` delivered as text.

    The model over it writes its arithmetic in Polars: the frame's own
    arithmetic over text is refused where it is written, so the forgotten
    cast reaches the engine only through an engine fragment, and a line
    after a fragment the engine cannot type is written the same way.
    """
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "sum_assured": ["250000", "100000", "50000"],
                "mortality_rate": [0.001, 0.002, 0.003],
                "status": ["IF", "LAPSED", "IF"],
            }
        )
    )


def test_the_forgot_the_cast_model_is_sound_once_the_break_is_removed() -> None:
    """The control: without the break, every calculation below it collects.

    This is what makes the next two tests' assertions falsifiable. ``claims``
    is ``f64 * f64`` by the time it is written, so nothing about it can fail;
    a message that names it is naming a column that works.
    """
    af = _raw_frame()
    af["sum_assured"] = af.sum_assured.polars_native().cast(pl.Float64)
    af = _in_force(af)
    af.claims = pl.col("sum_assured") * pl.col("mortality_rate")
    af = _in_force(af)

    assert af.collect().height == 2


def test_a_sealed_window_that_cannot_rebuild_its_plan_names_nothing() -> None:
    """Forgot the cast, cast one line late, filtered twice.

    Every window behind the break has a baseline plan that CONTAINS the
    break, and on three policies the replay's row cap reaches the bad
    value, so that plan will not collect. Replaying such a window against
    a substituted frame reproduces the same class and the same leading
    line from healthy arithmetic -- ``f64 * f64`` replayed as
    ``str * f64`` -- and the message then sends the user to a line that
    was never wrong. A window that cannot rebuild its own plan has no
    standing to name a column. Carrying the break is not on its own what
    costs a window its standing --
    ``test_a_break_past_the_replay_cap_leaves_the_windows_behind_it_usable``
    is the shape where a window carries one and collects anyway.
    """
    af = _raw_frame()
    af.band = pl.col("sum_assured") * pl.col("mortality_rate")
    break_line = af._calculations[-1].source.line  # noqa: SLF001
    af["sum_assured"] = af.sum_assured.polars_native().cast(pl.Float64)
    af = _in_force(af)
    af.claims = pl.col("sum_assured") * pl.col("mortality_rate")
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'claims'" not in message
    assert "Failing column: 'band'" in message
    assert f"{Path(__file__).name}:{break_line}" in message


def test_the_live_window_must_rebuild_its_plan_too() -> None:
    """The same model with one filter: the healthy column is now LIVE.

    The live window is searched first and is not exempt from the standing
    requirement -- its baseline carries the break as surely as a sealed
    one's does. This shape blamed healthy ``claims`` before any window was
    ever sealed, so pinning it is what carries the repair back past the
    sealing.
    """
    af = _raw_frame()
    af.band = pl.col("sum_assured") * pl.col("mortality_rate")
    break_line = af._calculations[-1].source.line  # noqa: SLF001
    af["sum_assured"] = af.sum_assured.polars_native().cast(pl.Float64)
    af = _in_force(af)
    af.claims = pl.col("sum_assured") * pl.col("mortality_rate")

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'claims'" not in message
    assert "Failing column: 'band'" in message
    assert f"{Path(__file__).name}:{break_line}" in message


def test_a_dtype_flipped_after_the_window_cannot_make_it_answer() -> None:
    """A second shape of the same defect: the frame's schema moves on.

    ``product_code`` is text, then f64, then text again. The substituted
    frame is built from the frame's CURRENT schema, so the middle window's
    healthy ``f64 * f64`` replays against text and reproduces. The break is
    the first line, and it is the only line that can honestly be named.
    """
    af = _frame()
    af.boom = pl.col("product_code") * pl.col("sum_assured")
    break_line = af._calculations[-1].source.line  # noqa: SLF001
    af["product_code"] = af.mortality_rate
    af = _in_force(af)
    af.margin = pl.col("product_code") * pl.col("sum_assured")
    af = _in_force(af)
    af["product_code"] = af.status
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'margin'" not in message
    assert "Failing column: 'boom'" in message
    assert f"{Path(__file__).name}:{break_line}" in message


def test_two_identical_breaks_name_the_one_the_plan_hits() -> None:
    """Newest-first must not outrank "the failure the plan actually raised".

    Both assignments are the same broken arithmetic and produce the same
    message, one on each side of a filter. The plan fails on the earlier
    one; the later one sits in a window whose baseline already carries it,
    so that window cannot rebuild its plan and does not answer.
    """
    af = _frame()
    af.boom_first = pl.col("product_code") * pl.col("sum_assured")
    first_line = af._calculations[-1].source.line  # noqa: SLF001
    af = _in_force(af)
    af.boom_second = pl.col("product_code") * pl.col("sum_assured")
    af = _in_force(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'boom_second'" not in message
    assert "Failing column: 'boom_first'" in message
    assert f"{Path(__file__).name}:{first_line}" in message


def test_a_rollforward_materialisation_seals_its_window() -> None:
    """The third seal site, and the one no other test reaches.

    Materialising a compiled rollforward's hidden columns changes the plan
    without leaving a calculation record, so the window is sealed there for
    the same reason a filter seals one. It is the only seal site outside
    ``filter``/``sort``, it fires inside Phase 3 rather than Phase 1, and
    without this the break above it goes back to arriving bare.
    """
    schedule = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
    )
    builder = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule)
    builder["av"].add(pl.col("premium"), label="P").grow(pl.col("rate"), label="G")
    compiled = compile_rollforward(builder)

    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "init": [100.0],
                "premium": [[10.0, 10.0, 10.0]],
                "rate": [[0.0, 0.0, 0.0]],
                "product_code": ["TERM"],
                "sum_assured": [250_000.0],
            }
        )
    )
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")
    break_line = af._calculations[-1].source.line  # noqa: SLF001
    af.av = compiled.expr_for("av")

    assert len(af._sealed_windows) == 1  # noqa: SLF001

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert "Failing column: 'reserve_factor'" in message
    assert f"{Path(__file__).name}:{break_line}" in message


# The break is placed past `_REPLAY_MAX_ROWS` deliberately: the replay
# baseline is collected as `source.limit(_REPLAY_MAX_ROWS)`, so a value that
# only breaks beyond the cap never reaches the replay at all.
_CAP_ROWS = 20_000
_BREAK_ROW = 15_000


def _past_the_cap_frame() -> ActuarialFrame:
    """Build twenty thousand policies whose one unparseable value sits past the cap."""
    text = [str(100 + i) for i in range(_CAP_ROWS)]
    text[_BREAK_ROW] = "not a number"
    return ActuarialFrame(
        pl.DataFrame({"sum_assured": text, "mortality_rate": [0.001] * _CAP_ROWS})
    )


def _every_policy(af: ActuarialFrame) -> ActuarialFrame:
    return af.filter(pl.col("mortality_rate") > 0.0)


def test_a_break_past_the_replay_cap_leaves_the_windows_behind_it_usable() -> None:
    """A window behind a break USUALLY cannot rebuild its plan. Not always.

    The two tests above turn on a window whose baseline plan contains the
    break and therefore will not collect, and that is the everyday case.
    It is not the rule. The baseline is collected as
    ``source.limit(_REPLAY_MAX_ROWS)``, so a break the head never reaches
    leaves every window behind it perfectly collectible -- here the strict
    cast fails on one value at ``_BREAK_ROW``, well past the cap, and all
    three windows come back usable. Only the live one is searched: it
    finds nothing that reproduces, since the replayed head holds no bad
    value, and a searched window that reproduces nothing ends the search,
    so the two behind it are never consulted.

    Nothing is wrong with that. The answer is bare rather than a healthy
    column's name by rule now, not by the accident of which classes the
    windows behind happen to raise -- the safe direction the cap's own
    contract already promises. The assertion on ``claims`` is what makes
    that falsifiable: it is ``f64 * f64`` behind the break, exactly the
    shape the substituted frame used to blame.
    """
    af = _past_the_cap_frame()
    af.assured_num = af.sum_assured.polars_native().cast(pl.Float64, strict=True)
    af = _every_policy(af)
    af.claims = af.mortality_rate * 2.0
    af = _every_policy(af)
    af.band = af.assured_num * 2.0

    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        af.collect()

    windows = [w for w in replay_windows(af) if w.records]
    usable = [
        _AttributionReplayFinder(
            af, excinfo.value, max_rows=_REPLAY_MAX_ROWS, window=w
        ).baseline_usable
        for w in windows
    ]
    assert usable == [True, True, True]

    message = str(excinfo.value)
    assert "Failing column:" not in message
    assert "claims" not in message
