# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Collect-time errors must name the offending column.

Regression test for #39. A lazy chain failing at collect() surfaced a raw
Polars error ("list lengths differed at index 0: 6 != 3") that never said
WHICH assigned column produced it — a long hunt in a 50-column model.
Assign-time errors were already attributed; collect-time ones were not.

The fallback contract matters as much as the feature: if attribution is
ambiguous the ORIGINAL error must pass through untouched. A wrong column name
costs more than no column name.
"""

from __future__ import annotations

from inspect import currentframe
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.assumptions import Table
from gaspatchio.frame.lowering._polars.plugins import accumulate, list_clip

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode — earlier suites leak AF_ERROR_MODE.

    ``set_error_mode()`` writes the environment variable process-wide, and
    several pre-existing error-handling suites (which sort before this file)
    leave it at ``basic``/``off``. These tests exercise the default
    ``enhanced`` behaviour, so they pin it; the opt-out test overrides it
    per-test.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _ragged_frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
                "three": [[1.0, 2.0, 3.0]],
            }
        )
    )


def test_shape_error_names_the_offending_column() -> None:
    """The reported case: a ragged list op fails without naming its column."""
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()
    assert "mismatched" in str(excinfo.value)


def test_attribution_picks_the_right_column_in_a_chain() -> None:
    """Only the broken column is named — never its healthy neighbours."""
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af.fine_two = af.three + 1.0
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
    assert "fine_two" not in message


def test_unattributable_error_passes_through_unchanged() -> None:
    """The fallback contract: no recorded assignment, no decoration.

    The broken operation is baked into the input plan before the
    ActuarialFrame ever sees it, so nothing was recorded and replay has
    nothing to name. The original Polars error must arrive untouched —
    a wrong column name costs more than no column name.
    """
    lf = pl.LazyFrame(
        {
            "policy_id": [1],
            "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
            "three": [[1.0, 2.0, 3.0]],
        }
    ).with_columns((pl.col("six") * pl.col("three")).alias("baked_in"))
    af = ActuarialFrame(lf)
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_misspelled_column_keeps_friendly_formatting() -> None:
    """The most common user error must keep its did-you-mean panel.

    Always-on recording made the graph truthy on every frame, which routed
    ordinary missing-column errors into the enhanced compilation path; its
    builder crashed on the bare tuples and re-raised the RAW Polars error —
    losing the available-columns panel for a simple misspelling.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "premium": [100.0]}))
    af.doubled = af["premum"] * 2.0
    with pytest.raises(Exception, match="premum") as excinfo:
        af.collect()
    assert "Available columns" in str(excinfo.value)


def test_a_structural_op_in_a_traced_run_still_names_the_broken_column() -> None:
    """A structural op keeps every record and reopens the window.

    Two contracts at once: the calculation log survives the filter — a
    reviewer can still ask how ``fine`` was calculated — while the LIVE
    window narrows to nothing, because nothing recorded before a structural
    operation can honestly be replayed against the plan that follows. The
    column assigned AFTER the filter replays against the post-filter plan
    — the one it was actually applied to — and is named.

    The window the filter closed is kept and stays searchable against its
    own baseline (``tests/errors/test_filter_attribution.py``), which is
    why ``fine`` being absent here is a real assertion rather than a
    consequence of the record having been thrown away: ``fine`` is a
    healthy calculation, so no replay reproduces this failure from it.
    """
    af = _ragged_frame()
    af._traced_run = True  # noqa: SLF001 — the flag the trace decorator sets
    af.fine = af.six * 2.0
    af = af.filter(pl.col("policy_id") == 1)
    assert [record.column for record in af._calculations] == ["fine"]  # noqa: SLF001
    assert af._attribution_ops() == []  # noqa: SLF001

    af.broken = af.six - af.three
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "Operation: broken" in message
    assert "Operation: fine" not in message


def test_multi_expression_batch_never_blames_a_healthy_sibling() -> None:
    """A with_columns batch is ONE step live, and replays as ONE step.

    Every expression in a batch sees the pre-batch frame, so ``y`` below
    reads the OLD 3-element ``x`` and is healthy. Replaying the batch one
    expression at a time would feed it the NEW 6-element ``x``, reproduce a
    ShapeError, and blame it. Replay re-applies the whole batch as a single
    ``with_columns`` instead, so ``y`` is handed the old value again and
    only the genuinely broken column is attributed.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
                "x": [[9.0] * 3],
            }
        )
    )
    af = af.with_columns(
        pl.col("six").alias("x"),
        (pl.col("x") - pl.col("three")).alias("y"),
    )
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "Failing column: 'broken'" in message
    assert "'y'" not in message


def test_valid_self_referential_dtype_change_is_not_blamed() -> None:
    """Replay must never re-apply an op already present in the good prefix.

    ``a`` narrows itself List(f64) -> f64 — valid exactly once. The exact
    scan used to start one op EARLY on a frame that already contained it,
    double-applying the narrowing, which raises the same class as the real
    bug and got ``a`` blamed for ``bad``'s error.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "a": [[7.0, 8.0]],
                "c": [1.5],
            }
        )
    )
    af["a"] = pl.col("a").list.get(0)
    af["bad"] = pl.col("c").list.get(0)
    with pytest.raises(Exception, match="get") as excinfo:
        af.collect()
    message = str(excinfo.value)
    if "Failing column" in message:
        assert "Failing column: 'bad'" in message
        assert "Failing column: 'a'" not in message


def test_window_closes_after_successful_collect_without_dropping_records() -> None:
    """A successful collect closes the window and keeps the model's history.

    The retired graph emptied itself here, to bound its own growth. The
    durable log does not: a model that ran successfully is exactly the one
    someone will ask questions about afterwards, so what it calculated
    stays answerable for as long as the frame lives. Narrowing is the
    cursor's job, and it is the cursor — not deletion — that bounds what
    replay has to re-apply.
    """
    af = _ragged_frame()
    af.fine = af.six * 2.0
    af.collect()
    assert [record.column for record in af._calculations] == ["fine"]  # noqa: SLF001
    assert af._attribution_ops() == []  # noqa: SLF001 — the property under test


def test_error_mode_optout_disables_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AF_ERROR_MODE=off is an opt-out a debug-mode frame must not override."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _ragged_frame()
    af._mode = "debug"  # noqa: SLF001 — the mode/env combination under test
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_attribution_appears_exactly_once() -> None:
    """No double decoration when control re-enters the handler."""
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()
    assert str(excinfo.value).count("Failing column") == 1


def test_run_to_parquet_names_the_offending_column(tmp_path: Path) -> None:
    """The at-scale batched path was the reported pain case — cover it."""
    from gaspatchio.scenarios._spill import run_to_parquet

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.mismatched = af.six * af.three
        return af

    points = pl.DataFrame({"policy_id": [1], "six": [[1.0] * 6], "three": [[1.0] * 3]})
    with pytest.raises(Exception, match="mismatched"):
        run_to_parquet(
            model,
            points,
            tmp_path,
            batch_size=1,
            mounts_text="/dev/disk1 / ext4 rw 0 0\n",
        )


def test_a_redefined_column_is_blamed_at_the_definition_that_broke_it() -> None:
    """Replay lands on a RECORD, not merely on a column name.

    ``reserves`` is defined twice in one window. Naming the column is not
    enough — the user needs the line that broke, and the two definitions
    sit on different lines. The record's ordinal says which definition it
    is; its source span says where it was written.
    """
    from gaspatchio.errors.boundary import search_collect_failure

    af = _ragged_frame()
    af.reserves = af.six * 2.0
    broken_line = currentframe().f_lineno + 1
    af.reserves = af.six - af.three

    try:
        af.collect()
    except Exception as raised:  # noqa: BLE001 — the failure under diagnosis
        failure = raised
    else:
        pytest.fail("collect() unexpectedly succeeded on a ragged list operation")
    record = search_collect_failure(af, failure).attribution

    assert record is not None
    assert record.column == "reserves"
    assert record.ordinal == 2
    assert record.source is not None
    assert record.source.line == broken_line


def test_the_attribution_block_reports_where_the_column_was_written() -> None:
    """Every recorded calculation carries a span, so the terse path reports one."""
    af = _ragged_frame()
    broken_line = currentframe().f_lineno + 1
    af.mismatched = af.six * af.three

    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()

    assert f"{__file__}:{broken_line}" in str(excinfo.value)


def test_two_consecutive_single_expression_batches_replay_in_order() -> None:
    """Separate calls are separate operations: the second sees the first's output.

    The mirror image of the batch case. Here ``x`` is widened by its OWN
    ``with_columns`` call, so the next call genuinely reads the widened
    value and genuinely fails — and replay must reproduce that rather than
    fusing the two calls into one.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
                "x": [[9.0] * 3],
            }
        )
    )
    af = af.with_columns(pl.col("six").alias("x"))
    af = af.with_columns((pl.col("x") - pl.col("three")).alias("broken"))

    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column: 'broken'" in str(excinfo.value)


def test_structural_mutation_resets_attribution_rather_than_misattributing() -> None:
    """After an unrecorded plan change, attribution restarts cleanly.

    filter() mutates the plan without being recorded, so earlier
    assignments are no longer sound to replay. The next assignment opens a
    fresh window against the post-filter baseline — the broken column
    assigned AFTER the filter is still attributed correctly.
    """
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af = af.filter(pl.col("policy_id") == 1)
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message


# --- ComputeError: the two commonest mistakes gain a column and a line -------
#
# A lookup miss and a jagged-list clash both arrive as ``ComputeError``,
# polars' catch-all, which used to pass through unattributed: no column, no
# line, no formula. Each shape below is attributed by the leading-line
# check, and the block quotes the right-hand side the model wrote -- never
# the lowered form, whose plugin path is the build's ``.so``.


def _rate_table(name: str) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _lookup_miss_on_a_scalar_key() -> ActuarialFrame:
    table = _rate_table("attribution_lookup_scalar")
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3], "age": [30, 40, 99]}))
    af.healthy = af.age * 2
    af.mort_rate = table.lookup(age=af.age)
    return af


def _lookup_miss_on_a_list_key() -> ActuarialFrame:
    table = _rate_table("attribution_lookup_list")
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "ages": [[30, 40], [40, 99]]})
    )
    af.mort_rate = table.lookup(age=af.ages)
    return af


def _jagged_list_pow() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"a": [[1.0, 2.0]], "b": [[1.0, 2.0, 3.0]]}))
    af.powed = af.a**af.b
    return af


def _jagged_when_then() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {"a": [[1.0, 2.0]], "b": [[1.0, 2.0, 3.0]], "flag": [[True, False]]}
        )
    )
    af.picked = when(af.flag).then(af.a).otherwise(af.b)
    return af


def _jagged_accumulate() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame({"init": [1.0], "m": [[1.0, 2.0]], "a": [[1.0, 2.0, 3.0]]})
    )
    af.fund = accumulate(pl.col("init"), pl.col("m"), pl.col("a"))
    return af


def _jagged_list_clip() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame({"v": [[1.0, 2.0]], "lo": [[0.0, 0.0, 0.0]], "hi": [[9.0, 9.0]]})
    )
    af.clipped = list_clip(pl.col("v"), pl.col("lo"), pl.col("hi"))
    return af


def _list_get_past_the_end() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"a": [[1.0, 2.0]]}))
    af.picked = af.a.polars_native().list.get(5, null_on_oob=False)
    return af


def _strict_integer_parse() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"s": ["1", "x"]}))
    af.n = af.s.polars_native().str.to_integer(base=10)
    return af


@pytest.mark.parametrize(
    ("build", "column", "written"),
    [
        pytest.param(
            _lookup_miss_on_a_scalar_key,
            "mort_rate",
            "table.lookup(age=af.age)",
            id="lookup-scalar-key",
        ),
        pytest.param(
            _lookup_miss_on_a_list_key,
            "mort_rate",
            "table.lookup(age=af.ages)",
            id="lookup-list-key",
        ),
        pytest.param(_jagged_list_pow, "powed", "af.a**af.b", id="list-pow"),
        pytest.param(
            _jagged_when_then,
            "picked",
            "when(af.flag).then(af.a).otherwise(af.b)",
            id="when-then",
        ),
        pytest.param(
            _jagged_accumulate,
            "fund",
            'accumulate(pl.col("init"), pl.col("m"), pl.col("a"))',
            id="accumulate",
        ),
        pytest.param(
            _jagged_list_clip,
            "clipped",
            'list_clip(pl.col("v"), pl.col("lo"), pl.col("hi"))',
            id="list-clip",
        ),
        pytest.param(
            _list_get_past_the_end,
            "picked",
            "af.a.polars_native().list.get(5, null_on_oob=False)",
            id="list-get",
        ),
        pytest.param(
            _strict_integer_parse,
            "n",
            "af.s.polars_native().str.to_integer(base=10)",
            id="to-integer",
        ),
    ],
)
def test_a_compute_error_names_its_column_and_quotes_the_formula(
    build: Callable[[], ActuarialFrame],
    column: str,
    written: str,
) -> None:
    """Eight ``ComputeError`` shapes, each bare before, each named now."""
    af = build()

    with pytest.raises(pl.exceptions.ComputeError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert f"Failing column: {column!r}" in message
    block = message.partition("Failing column:")[2]
    assert f"Defined as:     {written}" in block
    assert ".so" not in block
    assert "healthy" not in block


# The replay collects a head of ``_REPLAY_MAX_ROWS`` rows; the live collect
# streams the whole frame in batches. A refusal whose first line carried the
# batch's miss count matched only when the two happened to count the same,
# which at model scale they do not. The count is on the second line now.
_REACH_ROWS = 12_000
_REACH_STEP = 100


def test_a_miss_scattered_past_the_replay_head_is_still_attributed() -> None:
    """The reach the stable first line buys: a miss the head alone cannot count.

    One hundred and twenty policies at an age the table does not hold,
    every hundredth row, twenty of them past the replay head. The
    streaming collect reports its batch's count; the replay reports the
    head's. Neither is the other, and the column is named anyway.
    """
    from gaspatchio.errors.boundary import _REPLAY_MAX_ROWS

    miss_rows = list(range(0, _REACH_ROWS, _REACH_STEP))
    assert len(miss_rows) >= 10
    assert max(miss_rows) > _REPLAY_MAX_ROWS
    ages = [40 + (row % 3) for row in range(_REACH_ROWS)]
    for row in miss_rows:
        ages[row] = 99
    table = Table(
        name="attribution_reach",
        source=pl.DataFrame({"age": [40, 41, 42], "rate": [0.001, 0.0011, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": list(range(_REACH_ROWS)), "attained_age": ages})
    )
    af.mortality_rate = table.lookup(age=af.attained_age)

    with pytest.raises(pl.exceptions.ComputeError) as excinfo:
        af.collect()

    assert "Failing column: 'mortality_rate'" in str(excinfo.value)
