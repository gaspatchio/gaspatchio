# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A rollforward refusal through a frame is named by the line that read the run.

A frame runs a compiled rollforward as a hidden ``__rollforward_<fp>`` struct
column, put on the plan when its first reader is assigned. That is a
structural operation with no record of its own, so it seals the attribution
window before it and opens the next over the plan that already holds the
struct. When the rollforward is what breaks -- an input a period short for one
policy -- that window's baseline holds the break and never collects, and the
sealed window behind it replays clean. On the base the refusal reached the
user with no ``Failing column`` block, in either engine.

Now the search rebuilds that window from the plan before the struct (its
baseline less the struct, which Polars' projection pushdown prunes the unread
kernel from) and replays the materialisation as its first step, owned by its
reader: the record whose assignment put the struct on the plan. A step the
window replays on a record's behalf is named by that record.
Pinned here, in both engines: the shapes that are now named, the controls that
name some other record, the refusals, the shapes that stay bare, the traced
panel, and the Polars observation it rests on.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.errors.boundary import (
    _opening_steps,
    replay_windows,
    search_collect_failure,
)
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.schedule import Schedule

_ENGINES = ("streaming", "in-memory")

# The kernel's own first line for an input short for one policy: policy-free,
# so the replay compares it exactly.
_SHORT_PREMIUM = (
    "the plugin failed with message: mismatched inner list lengths in one "
    "policy: rollforward input column premium against the policy's period count"
)
_P002 = "  Policy:         policy_id=P002 (row 1)"


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _projected(*, traced: bool = False) -> ActuarialFrame:
    """Three policies on their own terms; P002 runs three months, the others two.

    ``premium`` holds two periods for every policy, so it is a period short
    for P002 alone. ``ok`` fits every policy, and ``x``/``short`` are a
    jagged pair for a list multiply of Polars' own.
    """
    af = ActuarialFrame(
        {
            "policy_id": ["P001", "P002", "P003"],
            "init": [100.0] * 3,
            "term_months": [2, 3, 2],
            "premium": [[10.0, 10.0]] * 3,
            "fee": [[1.0, 1.0]] * 3,
            "ok": [[10.0, 10.0], [10.0, 10.0, 10.0], [10.0, 10.0]],
            "x": [[1.0, 2.0], [1.0, 2.0], [1.0, 2.0]],
            "short": [[1.0, 2.0], [1.0], [1.0, 2.0]],
        }
    )
    if traced:
        af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    return af.projection.set(
        valuation_date=dt.date(2025, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )


def _refusal(af: ActuarialFrame, engine: str) -> str:
    with pytest.raises(pl.exceptions.PolarsError) as refused:
        af.collect(engine=engine)
    return str(refused.value)


def _run_over(af: ActuarialFrame, column: str) -> ActuarialFrame:
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af[column])
    af.av = compile_rollforward(builder).expr_for("av")
    return af


@pytest.mark.parametrize("engine", _ENGINES)
def test_an_input_short_for_one_policy_names_the_state_and_the_policy(
    engine: str,
) -> None:
    """The model's own input data, a period short for P002: ``av`` and P002."""
    message = _refusal(_run_over(_projected(), "premium"), engine)

    assert message.startswith(_SHORT_PREMIUM)
    assert "  Failing column: 'av'\n" in message, message
    assert '  Defined as:     compile_rollforward(builder).expr_for("av")' in message
    assert _P002 in message, message
    assert "  Reading:        rollforward:" in message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_recorded_input_with_a_reader_after_names_the_state(engine: str) -> None:
    """A recorded input and a later reader: the state is named, the reader blocked.

    The input ``prem2`` is a calculation in the window behind the struct;
    ``av_x2`` reads the state after it. Neither is named: the struct's
    materialisation, replayed as the live window's first step, reproduces
    the refusal, and its reader is ``av``.
    """
    af = _projected()
    af.prem2 = af.premium * 1.0
    af = _run_over(af, "prem2")
    af.av_x2 = af.av * 2.0

    message = _refusal(af, engine)

    assert "rollforward input column prem2 against" in message.splitlines()[0]
    assert "  Failing column: 'av'\n" in message, message
    assert _P002 in message, message
    assert "  Blocks:         av_x2@1" in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_two_states_of_one_run_name_the_first_reader(engine: str) -> None:
    """``av`` and ``fee`` read one run; ``av``'s assignment put it on the plan."""
    af = _projected()
    af.fee_amt = af.premium * 0.01
    builder = af.projection.rollforward(states={"av": af["init"], "fee": af["init"]})
    builder["av"].add(af["premium"])
    builder["fee"].add(af["fee_amt"])
    compiled = compile_rollforward(builder)
    af.av = compiled.expr_for("av")
    af.fee = compiled.expr_for("fee")

    message = _refusal(af, engine)

    assert "  Failing column: 'av'\n" in message, message
    assert _P002 in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_uniform_schedule_names_the_state_and_the_policy(engine: str) -> None:
    """A uniform three-period schedule, and P002's premium two periods long."""
    af = ActuarialFrame(
        {
            "policy_id": ["P001", "P002"],
            "init": [100.0, 100.0],
            "premium": [[10.0, 10.0, 10.0], [10.0, 10.0]],
        }
    )
    schedule = Schedule.from_calendar_grid(
        start_date=dt.date(2025, 1, 31), n_periods=3, frequency="1M"
    )
    builder = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule)
    builder["av"].add(pl.col("premium"))
    af.av = compile_rollforward(builder).expr_for("av")

    message = _refusal(af, engine)

    assert "rollforward input lists against the uniform schedule" in message
    assert "  Failing column: 'av'\n" in message, message
    assert _P002 in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_two_runs_on_one_first_line_refuse_listing_both_readers(engine: str) -> None:
    """Two rollforwards put on the plan by one call, both short on one input.

    Both materialisations open the same window and both reproduce the same
    first line, so the window is ambiguous: the refusal lists the two
    readers, ``av`` and ``bv``, and names no column.
    """
    af = _projected()
    first = af.projection.rollforward(states={"av": af["init"]})
    first["av"].add(af["premium"])
    second = af.projection.rollforward(states={"bv": af["init"]})
    second["bv"].add(af["premium"])
    second["bv"].add(af["fee"])
    af = af.with_columns(
        compile_rollforward(first).expr_for("av").alias("av"),
        compile_rollforward(second).expr_for("bv").alias("bv"),
    )

    message = _refusal(af, engine)

    assert "Failing column:" not in message
    assert "  Not attributed: 2 definitions reproduce" in message, message
    refusal = message.split("  Not attributed:", 1)[1]
    assert "'av' at " in refusal, refusal
    assert "'bv' at " in refusal, refusal
    assert "__rollforward_" not in refusal, refusal


@pytest.mark.parametrize("engine", _ENGINES)
def test_one_reader_of_two_runs_is_one_definition_and_is_named(engine: str) -> None:
    """Two runs read by one line are that one line: it is named, not refused."""
    af = _projected()
    first = af.projection.rollforward(states={"av": af["init"]})
    first["av"].add(af["premium"])
    second = af.projection.rollforward(states={"bv": af["init"]})
    second["bv"].add(af["premium"])
    second["bv"].add(af["fee"])
    af.total = compile_rollforward(first).expr_for("av") + compile_rollforward(
        second
    ).expr_for("bv")

    message = _refusal(af, engine)

    assert "  Failing column: 'total'\n" in message, message
    assert "Not attributed" not in message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_healthy_run_with_a_later_broken_record_names_that_record(
    engine: str,
) -> None:
    """The control: a run that fits, then a jagged multiply -- ``bad``, not ``av``."""
    af = _run_over(_projected(), "ok")
    af.bad = af.x * af.short

    message = _refusal(af, engine)

    assert "  Failing column: 'bad'\n" in message, message
    assert _P002 in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_break_recorded_before_the_run_names_that_record(engine: str) -> None:
    """The other control: the jagged multiply is written before the run."""
    af = _projected()
    af.bad = af.x * af.short
    af = _run_over(af, "ok")

    message = _refusal(af, engine)

    assert "  Failing column: 'bad'\n" in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_run_read_only_by_a_select_stays_bare(engine: str) -> None:
    """A struct no record of the window reads has no reader to be named by.

    The run is put on the plan by a ``select``, a structural operation, and
    the only record after it does not read the run: there is no record a
    reproduction could honestly be named by, so the refusal stays bare.
    """
    af = _projected()
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    af = af.select(
        pl.col("policy_id"),
        pl.col("init"),
        compile_rollforward(builder).expr_for("av").alias("av_selected"),
    )
    af.y = af.init * 2.0

    message = _refusal(af, engine)

    assert message.startswith(_SHORT_PREMIUM)
    assert "Failing column:" not in message
    assert "Not attributed" not in message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_run_read_only_by_a_filter_stays_bare(engine: str) -> None:
    """A struct whose only reader is a filter has no record to be named by.

    The filter puts the run on the plan and chooses rows on it: a selection
    step, which defines no column, so no calculation record reads the run and
    the record after the filter (``y``) never touched it. Naming ``y`` would
    blame a healthy line, so the kernel's own refusal reaches the user bare.
    """
    af = _projected()
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    af = af.filter(compile_rollforward(builder).expr_for("av").list.get(0) > 0)
    af.y = af.init * 2.0

    message = _refusal(af, engine)

    assert message.startswith(_SHORT_PREMIUM)
    assert "Failing column:" not in message
    assert "Not attributed" not in message
    assert "not found" not in message


def test_a_window_with_no_reader_of_its_struct_is_not_rebuilt() -> None:
    """``_opening_steps`` declines a struct none of the window's records reads."""
    af = _run_over(_projected(), "premium")
    af.y = af.init * 2.0
    live = replay_windows(af)[0]
    assert [record.column for record in live.records] == ["av", "y"]

    rebuilt = _opening_steps(af, live)
    assert rebuilt is not None
    assert [step.reader.column for step in rebuilt[1]] == ["av"]

    without_reader = live._replace(
        records=[r for r in live.records if r.column != "av"]
    )
    assert _opening_steps(af, without_reader) is None


def test_the_traced_panel_names_the_state_and_the_policy() -> None:
    """The debug run's panel, through the same search, names ``av`` and P002."""
    af = _run_over(_projected(traced=True), "premium")
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect()

    message = str(refused.value)
    assert "Calculation Error" in message, message
    assert "   Operation: av\n" in message, message
    assert "   Policy: policy_id=P002 (row 1)" in message, message
    assert refused.value.llm_context["policy"] == "policy_id=P002 (row 1)"  # type: ignore[attr-defined]


def test_the_search_names_the_reader_not_the_hidden_struct() -> None:
    """The record handed back is the reader's own, with its line, never the step."""
    af = _run_over(_projected(), "premium")
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af._df.collect()  # noqa: SLF001 -- the plan, undecorated

    outcome = search_collect_failure(af, refused.value)

    reader = next(r for r in af._attribution_ops() if r.column == "av")  # noqa: SLF001
    assert outcome.attribution is reader
    assert outcome.last_good is not None
    assert not any(c.startswith("__rollforward_") for c in outcome.last_good.columns)


@pytest.mark.parametrize("engine", _ENGINES)
def test_an_unread_hidden_struct_is_pruned(engine: str) -> None:
    """The Polars observation S0 rests on: an unread plugin column is never run.

    The live window's baseline holds the failing kernel and does not
    collect; the same plan less the struct collects, because projection
    pushdown prunes the plugin no remaining column reads. If Polars ever
    stops pruning, this fails by name -- and the rebuilt baseline then does
    not collect, so the search passes over it and the refusal is bare
    again, never wrongly named.
    """
    af = _run_over(_projected(), "premium")
    baseline = replay_windows(af)[0].baseline
    assert baseline is not None
    hidden = [
        name
        for name in baseline.collect_schema().names()
        if name.startswith("__rollforward_")
    ]
    assert len(hidden) == 1

    with pytest.raises(pl.exceptions.ComputeError):
        baseline.collect(engine=engine)  # type: ignore[call-overload]
    pruned = baseline.drop(hidden).collect(engine=engine)  # type: ignore[call-overload]

    assert pruned.height == 3
