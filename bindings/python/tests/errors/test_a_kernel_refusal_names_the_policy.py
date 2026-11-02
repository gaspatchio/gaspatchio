# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A list kernel's refusal names the policy, and never a row of its batch.

The engine hands a list kernel one batch of rows per call and no offset, so
the row a kernel could count was the batch's. Under the default streaming
engine that is not the frame's: ``when(af.x > 1).then(af.short)`` with the
short list on frame row 1 (policy P002) said ``mismatched inner list lengths
at row 0: left=3, then=2``, and in memory ``row 1``. Under streaming the
replay -- which compares first lines exactly -- then could not match the
failure at all, so the block naming the column was missing too.

Now every kernel says "in one policy", the operand and both lengths (or what
was null), and the error report reads the frame once to name the policy: by
the run's policy-id column -- ``--policy-id-column``, else ``policy_id``,
``point_id`` and the other names the runner reads -- and its row, with a
count of the rest.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.errors.policy_locator import (
    locate_refused_policies,
    telling_the_policy_id_column,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_ENGINES = ("streaming", "in-memory")

# A number counted as a row anywhere in the kernel's own words.
_A_ROW = re.compile(r"\brow \d")


def _book() -> pl.DataFrame:
    """Three policies; only P002, on frame row 1, carries a misfit."""
    day = dt.date
    return pl.DataFrame(
        {
            "policy_id": ["P001", "P002", "P003"],
            "x": [[1.0, 2.0], [1.0, 2.0, 3.0], [1.0]],
            "short": [[10.0, 20.0], [10.0, 20.0], [5.0]],
            "lo": [[0.0, 0.0], [0.0, 0.0], [0.0]],
            "hi": [[9.0, 9.0], [9.0, 9.0, 9.0], [9.0]],
            "init": [100.0, 100.0, 100.0],
            "floor": [0.0, None, 0.0],
            "start": [
                [day(2025, 1, 1), day(2025, 2, 1)],
                [day(2025, 1, 1), day(2025, 2, 1), day(2025, 3, 1)],
                [day(2025, 1, 1)],
            ],
            "end": [
                [day(2026, 1, 1), day(2026, 2, 1)],
                [day(2026, 1, 1), day(2026, 2, 1)],
                [day(2026, 1, 1)],
            ],
            "age": [[30, 30], [31, 31, 31], [30]],
            "dur": [[0, 1], [0, 1], [0]],
        }
    )


def _table() -> Table:
    return Table(
        name="w3cf_policy_named_lookup",
        source=pl.DataFrame(
            {
                "age": [30, 30, 30, 31, 31, 31],
                "dur": [0, 1, 2, 0, 1, 2],
                "rate": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            }
        ),
        dimensions={"age": "age", "dur": "dur"},
        value="rate",
    )


# Each kernel that pairs per-period operands, with the operand it names.
_LENGTHS: dict[str, tuple[Callable[[ActuarialFrame], object], str]] = {
    "a conditional": (
        lambda af: when(af.x > 1).then(af.short).otherwise(0.0),
        "then against left",
    ),
    "a conditional inside a product": (
        lambda af: when(af.x > 1).then(af.short).otherwise(0.0) * 2.0,
        "then against left",
    ),
    "a comparison": (lambda af: af.x > af.short, "right against left"),
    "a power": (lambda af: af.x**af.short, "exponent against base"),
    "a quotient": (lambda af: af.x / af.short, "divisor against numerator"),
    "a clip": (lambda af: af.x.clip(af.lo, af.hi), "lower bound against values"),
    "a recurrence": (
        lambda af: af.x.projection.accumulate(
            initial=af.init, multiplier=af.x, addend=af.short
        ),
        "addend against multiplier",
    ),
    "a year fraction": (
        lambda af: af.start.excel.yearfrac(af.end),
        "end against start",
    ),
    # The keys are named as the plugin is handed them; the sentence's form
    # is what is pinned here, and the Rust test pins the names.
    "a lookup": (
        lambda af: _table().lookup(age=af.age, dur=af.dur),
        "key ",
    ),
}


def _refusal(formula: Callable[[ActuarialFrame], object], engine: str) -> str:
    af = ActuarialFrame(_book())
    af.out = formula(af)
    with pytest.raises(pl.exceptions.PolarsError) as refused:
        af.collect(engine=engine)
    return str(refused.value)


def _kernels_words(message: str) -> str:
    """Return the engine's part of the message, before the frame's block."""
    return message.split("\n\n  Failing column:", 1)[0]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("case", list(_LENGTHS), ids=list(_LENGTHS))
def test_a_length_refusal_names_the_policy_and_no_batch_row(
    case: str, engine: str
) -> None:
    """P002 is named by its id and frame row, in both engines.

    On the base the streaming run said ``row 0`` and carried no block; in
    memory it said ``row 1``.
    """
    formula, operand = _LENGTHS[case]
    message = _refusal(formula, engine)

    assert f"mismatched inner list lengths in one policy: {operand}" in message
    assert _A_ROW.search(_kernels_words(message)) is None, message
    assert "  Failing column: 'out'" in message
    assert "  Policy:         policy_id=P002 (row 1)\n" in message + "\n", message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_null_refusal_names_the_policy_and_no_batch_row(engine: str) -> None:
    """A clip bound null for P002 is named by P002, not a batch row.

    The spec states nothing for a null bound (11.1.3), so the kernel still
    refuses it; a null exponent now answers null (11.1.25) and is tested
    with the other null operands.
    """
    message = _refusal(lambda af: af.x.clip(af.floor, af.hi), engine)

    assert "the lower bound of a clip is null for one policy" in message
    assert _A_ROW.search(_kernels_words(message)) is None, message
    assert "  Policy:         policy_id=P002 (row 1)" in message, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_several_policies_are_counted(engine: str) -> None:
    """The first policy is named, and the rest are counted."""
    book = pl.DataFrame(
        {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "x": [[1.0, 2.0], [1.0, 2.0, 3.0], [1.0], [1.0, 2.0, 3.0, 4.0]],
            "y": [[1.0, 2.0], [1.0, 2.0], [1.0, 2.0], [1.0]],
        }
    )
    af = ActuarialFrame(book)
    af.out = af.x / af.y
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine=engine)

    assert "  Policy:         policy_id=P002 (row 1), and 2 more" in str(refused.value)


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_book_with_no_policy_id_column_is_named_by_its_row(engine: str) -> None:
    """With no identifier column the frame row is what can be named."""
    af = ActuarialFrame(_book().drop("policy_id"))
    af.out = when(af.x > 1).then(af.short).otherwise(0.0)
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine=engine)

    assert "  Policy:         row 1\n" in str(refused.value) + "\n"


def test_the_told_policy_id_column_names_the_policy() -> None:
    """``--policy-id-column`` wins over the names the runner would read."""
    af = ActuarialFrame(_book().with_columns(contract=pl.Series(["C1", "C2", "C3"])))
    af.out = when(af.x > 1).then(af.short).otherwise(0.0)
    with (
        telling_the_policy_id_column("contract"),
        pytest.raises(pl.exceptions.ComputeError) as refused,
    ):
        af.collect()

    assert "  Policy:         contract=C2 (row 1)" in str(refused.value)


def test_the_traced_panel_names_the_policy() -> None:
    """The debug run's panel carries the same line."""
    af = ActuarialFrame(_book())
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    af.out = when(af.x > 1).then(af.short).otherwise(0.0)
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect()

    message = str(refused.value)
    assert "Calculation Error" in message
    assert "   Policy: policy_id=P002 (row 1)" in message
    assert refused.value.llm_context["policy"] == "policy_id=P002 (row 1)"  # type: ignore[attr-defined]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_rollforward_input_of_another_length_names_no_batch_row(engine: str) -> None:
    """A rollforward input short for one policy says so, and no row."""
    from gaspatchio.rollforward._builder import RollforwardBuilder
    from gaspatchio.rollforward._compile import compile_rollforward
    from gaspatchio.schedule import Schedule
    from tests.rollforward.conftest import _standalone_state_expr

    schedule = Schedule.from_per_policy_grid(
        start_date=dt.date(2025, 1, 31),
        frequency="1M",
        until_kind="term_months",
        until_value_column="term",
    )
    builder = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule)
    builder["av"].add(pl.col("premium"))
    builder["av"].add(pl.col("bonus"))
    compiled = compile_rollforward(builder)
    book = pl.DataFrame(
        {
            "init": [100.0, 100.0],
            "term": [2, 3],
            "premium": [[10.0, 20.0], [10.0, 20.0, 30.0]],
            "bonus": [[1.0, 1.0], [1.0, 1.0]],
        }
    )
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        book.lazy().with_columns(av=_standalone_state_expr(compiled, "av")).collect(
            engine=engine  # type: ignore[call-overload]
        )

    message = str(refused.value)
    assert (
        "mismatched inner list lengths in one policy: rollforward input column "
        "bonus against the policy's period count" in message
    )
    assert "the policy's period count=3, rollforward input column bonus=2" in message
    assert _A_ROW.search(message) is None, message


@pytest.mark.parametrize("engine", _ENGINES)
def test_polars_own_list_arithmetic_names_the_policy(engine: str) -> None:
    """``af.x * af.short`` is Polars' kernel, not ours, and names P002 too.

    Its refusal is ``list lengths differed at index N: 3 != 2``, with N the
    batch's row: the streaming run reads ``index 0`` where the in-memory
    replay reads ``index 1``. On the base the exact first-line check kept
    those apart and the streaming error had no block; the line is now on
    the replay's closed allowlist of Polars' batch-counted lines, read with
    its digits as the batch's, so both engines name the
    column and the locator names the policy.
    """
    af = ActuarialFrame(_book())
    af.out = af.x * af.short
    with pytest.raises(pl.exceptions.ShapeError) as refused:
        af.collect(engine=engine)

    message = str(refused.value)
    assert "list lengths differed at index" in message
    assert "  Failing column: 'out'" in message
    assert "  Policy:         policy_id=P002 (row 1)" in message


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_uniform_rollforward_refusal_opens_on_a_policy_free_line(engine: str) -> None:
    """The uniform-schedule refusal's first line is the same for every policy.

    It used to open on the policy's own length (``one policy has input lists
    of length 2``), so two policies short by different amounts gave two first
    lines and the replay, which matches first lines exactly, could not match
    the one the run raised. The length is on the next line now; the gh#73
    advice for an axis-derived input one element long follows it.
    """
    from gaspatchio.rollforward._builder import RollforwardBuilder
    from gaspatchio.rollforward._compile import compile_rollforward
    from gaspatchio.schedule import Schedule
    from tests.rollforward.conftest import _standalone_state_expr

    schedule = Schedule.from_calendar_grid(
        start_date=dt.date(2025, 1, 31), n_periods=3, frequency="1M"
    )
    builder = RollforwardBuilder(states={"av": pl.col("init")}, schedule=schedule)
    builder["av"].add(pl.col("premium"))
    compiled = compile_rollforward(builder)

    first_lines = set()
    for premium in ([10.0, 10.0], [10.0], [10.0, 10.0, 10.0, 10.0]):
        book = pl.DataFrame(
            {"init": [100.0, 100.0], "premium": [[10.0, 10.0, 10.0], premium]}
        )
        with pytest.raises(pl.exceptions.ComputeError) as refused:
            book.lazy().with_columns(av=_standalone_state_expr(compiled, "av")).collect(
                engine=engine
            )  # type: ignore[call-overload]
        message = str(refused.value)
        first_lines.add(message.splitlines()[0])
        assert _A_ROW.search(message) is None, message
        assert (
            f"the uniform schedule's n_periods=3, rollforward input lists="
            f"{len(premium)} in that policy." in message
        )

    assert first_lines == {
        "the plugin failed with message: mismatched inner list lengths in one "
        "policy: rollforward input lists against the uniform schedule's n_periods"
    }


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_rollforward_refusal_through_a_frame_names_the_policy(engine: str) -> None:
    """Through a frame, a rollforward input short for P002 names P002.

    A frame runs a compiled rollforward as a hidden struct column it puts on
    the plan as a structural operation, sealing the attribution window
    (#39), and the window it opens holds the failing kernel in its
    baseline. On the base the refusal reached the user with no ``Failing
    column`` block in either engine; the search now rebuilds that window
    from before the struct and names the state by its reader, ``av``
    (``test_a_rollforward_refusal_is_named_by_its_reader.py``).
    """
    from gaspatchio import compile_rollforward

    af = ActuarialFrame(
        {
            "policy_id": ["P001", "P002", "P003"],
            "init": [100.0] * 3,
            "term_months": [2, 3, 2],
            "premium": [[10.0, 10.0]] * 3,
        }
    )
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    af.av = compile_rollforward(builder).expr_for("av")
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine=engine)

    assert "  Failing column: 'av'" in str(refused.value)
    assert "  Policy:         policy_id=P002 (row 1)" in str(refused.value)


# --- the locator itself, against the refusal's words ---------------------------


def _record(af: ActuarialFrame, column: str) -> object:
    return next(
        record
        for record in af._attribution_ops()  # noqa: SLF001 -- the calculation log
        if record.column == column
    )


_A_LENGTH_REFUSAL = pl.exceptions.ComputeError(
    "the plugin failed with message: mismatched inner list lengths in one "
    "policy: then against left\nleft=3, then=2 in that policy."
)


def test_another_failure_is_not_located() -> None:
    """Only the length and null refusals are located; anything else is left alone."""
    af = ActuarialFrame(_book())
    af.out = when(af.x > 1).then(af.short).otherwise(0.0)
    record = _record(af, "out")

    assert (
        locate_refused_policies(
            record,  # type: ignore[arg-type]
            _book(),
            pl.exceptions.ComputeError("cannot compare string with numeric type"),
        )
        is None
    )
    located = locate_refused_policies(record, _book(), _A_LENGTH_REFUSAL)  # type: ignore[arg-type]
    assert located is not None
    assert located.text() == "policy_id=P002 (row 1)"


def test_polars_own_length_line_is_located() -> None:
    """The batch-counted line Polars' list arithmetic writes is a length refusal."""
    af = ActuarialFrame(_book())
    af.out = af.x * af.short

    located = locate_refused_policies(
        _record(af, "out"),  # type: ignore[arg-type]
        _book(),
        pl.exceptions.ShapeError("list lengths differed at index 0: 3 != 2"),
    )

    assert located is not None
    assert located.text() == "policy_id=P002 (row 1)"


def test_a_frame_at_the_replay_cap_says_so() -> None:
    """Policies past the replay's head were not looked at, and the line says so."""
    af = ActuarialFrame(_book())
    af.out = when(af.x > 1).then(af.short).otherwise(0.0)

    located = locate_refused_policies(
        _record(af, "out"),  # type: ignore[arg-type]
        _book(),
        _A_LENGTH_REFUSAL,
        capped_at=3,
    )

    assert located is not None
    assert located.text() == "policy_id=P002 (row 1) among the first 3 rows"


def test_a_frame_that_breaks_no_rule_names_nothing() -> None:
    """Where every operand fits, there is no policy to name and no line."""
    af = ActuarialFrame(_book())
    af.out = when(af.x > 1).then(af.x).otherwise(0.0)

    assert (
        locate_refused_policies(_record(af, "out"), _book(), _A_LENGTH_REFUSAL)  # type: ignore[arg-type]
        is None
    )
