# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A failing ``with_columns`` batch names the alias that broke it.

``with_columns`` resolves its schema eagerly, so a batch of aliased
expressions with one bad alias fails inside the call rather than at
``collect()``. That failure used to leave the frame in the one state the
calculation log is meant to make impossible: the batch was already in the
query plan, and the log had no record of any of it -- ``_record_batch_calculations``
ran on the line *after* the one that threw. The re-raise then bypassed the
error handler entirely, so the user was handed every expression in the batch
and a diagnosis of none of them.

Pinned here: the batch that reached the plan also reaches the log, the
failure routes through the same handler every other frame error does, and
per-column replay names the one bad alias. And the other direction of the
same invariant -- a batch that never reached the plan records nothing --
because a log that claims a column the frame does not hold is the defect
this repair could have introduced.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.base import _INCREMENTAL_SCHEMA_MIN_COLS
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.frame.graph.holes import find_holes


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _frame() -> ActuarialFrame:
    """Three policies, one string column that cannot take part in arithmetic."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "product_code": ["TERM", "TERM", "WL"],
                "sum_assured": [250_000.0, 100_000.0, 50_000.0],
                "mortality_rate": [0.001, 0.002, 0.003],
            }
        )
    )
    af.duration = af.policy_id * 0
    return af


def _wide_frame() -> ActuarialFrame:
    """``_frame()`` padded so the lazy assignment lands ON the incremental door.

    Same four columns and the same ``duration = policy_id * 0``, with
    arriving padding sized off ``_INCREMENTAL_SCHEMA_MIN_COLS`` so that
    the assignment takes the frame to exactly that width. The constant is
    the anchor, never the number: if the door moves, this fixture moves
    with it and stays on the far side.
    """
    data: dict[str, list[object]] = {
        "policy_id": [1, 2, 3],
        "product_code": ["TERM", "TERM", "WL"],
        "sum_assured": [250_000.0, 100_000.0, 50_000.0],
        "mortality_rate": [0.001, 0.002, 0.003],
    }
    for i in range(_INCREMENTAL_SCHEMA_MIN_COLS - 1 - len(data)):
        data[f"pad_{i}"] = [1.0, 2.0, 3.0]
    af = ActuarialFrame(pl.DataFrame(data))
    af.duration = af.policy_id * 0
    return af


def _frame_the_dtype_probe_cannot_type() -> ActuarialFrame:
    """One column past ``_wide_frame()``, with a ``duration`` nothing can type.

    Same shape, same arriving padding sized off the constant, but the
    assignment multiplies a string column by a float. ``__setitem__``
    takes the incremental path at this width and then
    ``_resolve_assigned_dtype`` cannot type the expression, so
    ``_apply_incremental_schema`` returns before writing and the flag the
    ``_df`` setter set stays set. The plan takes the expression
    regardless: ``with_columns`` on a ``LazyFrame`` resolves nothing.
    """
    data: dict[str, list[object]] = {
        "policy_id": [1, 2, 3],
        "product_code": ["TERM", "TERM", "WL"],
        "sum_assured": [250_000.0, 100_000.0, 50_000.0],
        "mortality_rate": [0.001, 0.002, 0.003],
    }
    for i in range(_INCREMENTAL_SCHEMA_MIN_COLS - len(data)):
        data[f"pad_{i}"] = [1.0, 2.0, 3.0]
    af = ActuarialFrame(pl.DataFrame(data))
    af.duration = pl.col("product_code") * pl.col("sum_assured")
    return af


def _bad_batch(af: ActuarialFrame) -> None:
    """Three aliases in one call; the middle one multiplies a string by a float."""
    af.with_columns(
        (pl.col("sum_assured") * 2.0).alias("good_col"),
        (pl.col("product_code") * pl.col("sum_assured")).alias("reserve_factor"),
        (pl.col("mortality_rate") * 3.0).alias("other_col"),
    )


def _batch_reusing(af: ActuarialFrame, alias: str) -> None:
    """Run the same failing batch, first alias reusing a name the frame holds."""
    af.with_columns(
        (pl.col(alias) * 2.0).alias(alias),
        (pl.col("product_code") * pl.col("sum_assured")).alias("reserve_factor"),
    )


def _batch_reusing_with_a_typo(af: ActuarialFrame, alias: str) -> None:
    """Run the same reuse with the read misspelled, so a hole is punched under it."""
    af.with_columns((pl.col("mortalty_rate") * 2.0).alias(alias))


def _records(af: ActuarialFrame) -> list[CalculationRecord]:
    return [e for e in af._calculations if isinstance(e, CalculationRecord)]  # noqa: SLF001


def test_a_failed_batch_lands_in_the_calculation_log() -> None:
    """The plan carries the batch, so the log has to carry it too."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _bad_batch(af)

    columns = [r.column for r in _records(af)]
    assert columns == ["duration", "good_col", "reserve_factor", "other_col"]


def test_a_failed_batch_is_one_operation() -> None:
    """One call, one operation id -- what keeps replay from splitting it."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _bad_batch(af)

    batch = _records(af)[1:]
    assert len({r.operation_id for r in batch}) == 1
    assert batch[0].operation_id != _records(af)[0].operation_id


def test_a_failed_batch_records_no_dtype_for_an_alias_new_to_the_frame() -> None:
    """A failed batch never advanced the schema, so a new alias records none.

    Read in that direction only. All three aliases in ``_bad_batch`` are
    new to ``_frame()``, and a name the frame never held is in no schema
    it ever resolved, so the last resolved schema has nothing to give
    them and each records ``None``. An alias reusing a name records
    whatever that schema holds for it, which may be ``None`` for a name
    the frame itself holds; what resolves that schema is enumerated in
    ``base.py``'s ``_record_batch_calculations`` docstring, and the tests
    below pin every door it names. The marker on the record is a false
    negative either way, never a false positive.
    """
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _bad_batch(af)

    assert [r.dtype for r in _records(af)[1:]] == [None, None, None]


def test_a_reused_alias_records_what_the_last_resolved_schema_holds() -> None:
    """The boundary of the test above, and it is not "the names the frame holds".

    ``_frame()`` holds ``sum_assured`` and ``duration`` alike, and the
    same failed batch records them differently. The dtype comes off
    ``self._schema`` -- the last schema that *resolved* -- and
    ``sum_assured`` arrived with the data, so it is in that schema and
    its alias comes back typed. ``duration`` was minted by a lazy
    assignment, and on this frame nothing has resolved the schema since,
    so it is on the frame and in no resolved schema and its alias records
    ``None`` in exactly the batch the sentence above describes.

    The blocks below then walk what does and does not change that, and
    two of the three doors ``base.py``'s ``_record_batch_calculations``
    docstring enumerates are here: ``af.collect()`` resolves nothing, a
    read of the frame's schema resolves (the property door), and one
    ordinary successful ``with_columns()`` before the failing batch
    resolves too (the setter door) -- both of them here on a frame far
    below the incremental door, which is the point. Where one of the two
    that resolve has, the old ``Int64`` comes back rather than the
    ``Float64`` the failed expression would have produced. The third
    door has its own two tests below.

    So a reused alias records whatever the last resolved schema holds
    for the name -- which may be nothing. The direction is untouched:
    a batch that succeeds resolves the schema and types every alias, so
    a batch record with no dtype still means the batch failed. A false
    negative, never a false positive.
    """
    af = _frame()
    assert "duration" in af.columns
    assert "sum_assured" in af.columns

    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "sum_assured")
    assert [(r.column, r.dtype) for r in _records(af)[1:]] == [
        ("sum_assured", pl.Float64),
        ("reserve_factor", None),
    ]

    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "duration")
    assert [(r.column, r.dtype) for r in _records(af)[1:]] == [
        ("duration", None),
        ("reserve_factor", None),
    ]

    af = _frame()
    af.collect()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "duration")
    assert [(r.column, r.dtype) for r in _records(af)[1:]] == [
        ("duration", None),
        ("reserve_factor", None),
    ]

    af = _frame()
    assert "duration" in (af._schema or {})  # noqa: SLF001 -- the resolve itself
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "duration")
    assert [(r.column, r.dtype) for r in _records(af)[1:]] == [
        ("duration", pl.Int64),
        ("reserve_factor", None),
    ]

    af = _frame()
    af.with_columns((pl.col("policy_id") * 1).alias("touch"))
    assert len(af.columns) < _INCREMENTAL_SCHEMA_MIN_COLS
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "duration")
    assert [(r.column, r.dtype) for r in _records(af)[2:]] == [
        ("duration", pl.Int64),
        ("reserve_factor", None),
    ]


def test_a_frame_wide_enough_to_advance_its_schema_types_the_reused_alias() -> None:
    """The third door, first condition: the assignment resolves its own dtype.

    ``__setitem__`` computes ``do_incremental`` from
    ``len(self._column_order) >= _INCREMENTAL_SCHEMA_MIN_COLS`` and only
    then resolves the assigned dtype and calls
    ``_apply_incremental_schema``, which writes the name into the cache
    and clears the dirty flag. So this width decides whether the
    *assignment* advances the schema; it does not on its own decide which
    names the last resolved schema holds, which is the rule written once
    in ``base.py``'s ``_record_batch_calculations`` docstring, with two
    other doors beside this one. Both sides of this one are here, a
    column apart and sized off the constant: the same reused alias in the
    same failing batch records ``None`` below the width and ``Int64`` at
    it. The test below holds the second condition on the same branch.

    The consequence where this door is the only one in play: a hole read
    under that alias takes the spelling hint below the width and the
    general "the record naming it is wrong" wording at it. Any model an
    actuary writes is past that width, which is one of the reasons the
    marker's miss is the ordinary case rather than the edge -- the
    limitation ``_names_a_failed_batch_read`` states. Still a false
    negative and never a false positive: the actuary is told less, not
    told something untrue.
    """
    narrow = _frame()
    assert len(narrow.columns) < _INCREMENTAL_SCHEMA_MIN_COLS
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(narrow, "duration")
    assert [(r.column, r.dtype) for r in _records(narrow)[1:]] == [
        ("duration", None),
        ("reserve_factor", None),
    ]

    wide = _wide_frame()
    assert len(wide.columns) == _INCREMENTAL_SCHEMA_MIN_COLS
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(wide, "duration")
    assert [(r.column, r.dtype) for r in _records(wide)[1:]] == [
        ("duration", pl.Int64),
        ("reserve_factor", None),
    ]

    narrow = _frame()
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        _batch_reusing_with_a_typo(narrow, "duration")
    (narrow_hole,) = find_holes(narrow)
    assert narrow_hole.column == "mortalty_rate"
    assert "spelled" in narrow_hole.hint

    wide = _wide_frame()
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        _batch_reusing_with_a_typo(wide, "duration")
    (wide_hole,) = find_holes(wide)
    assert wide_hole.column == "mortalty_rate"
    assert "spelled" not in wide_hole.hint
    assert "the record naming it is wrong" in wide_hole.hint


def test_an_assignment_the_dtype_probe_declines_advances_no_schema() -> None:
    """The second condition on the same branch, a full column past the width.

    ``__setitem__`` takes the incremental path here, and then
    ``_apply_incremental_schema`` returns before writing anything because
    ``_resolve_assigned_dtype`` could not type the expression cheaply --
    the second condition, which the call site names in as many words. So
    the flag the ``_df`` setter just set stays set, nothing was written
    into the cache, and the reused alias still records ``None`` a column
    past the width the test above pins. Width decides whether the
    assignment *tries*; this is the try that declines.

    The two assertions on the raw cache are what make this a pin rather
    than a transcript. Read through the ``_schema`` property they would
    resolve the very plan they came to observe, and an
    ``_apply_incremental_schema`` that wrote the unresolved ``None`` into
    the schema instead of returning would record the same ``None`` below
    while leaving the frame clean.
    """
    af = _frame_the_dtype_probe_cannot_type()

    assert len(af.columns) > _INCREMENTAL_SCHEMA_MIN_COLS
    assert af.__dict__["_schema_dirty"] is True
    assert "duration" not in (af.__dict__.get("_schema_value") or {})

    with pytest.raises(pl.exceptions.InvalidOperationError):
        _batch_reusing(af, "duration")
    assert [(r.column, r.dtype) for r in _records(af)[1:]] == [
        ("duration", None),
        ("reserve_factor", None),
    ]


def test_a_failed_batch_records_the_line_that_wrote_it() -> None:
    """Attribution's ``At:`` line comes off the record, so it has to be there."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _bad_batch(af)

    spans = [r.source for r in _records(af)[1:]]
    assert all(span is not None for span in spans)
    assert {Path(span.file).name for span in spans} == {Path(__file__).name}


def test_a_failed_batch_names_the_bad_alias() -> None:
    """The point of the repair: one of three aliases is blamed, and the right one."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        _bad_batch(af)

    message = str(excinfo.value)
    assert "Failing column: 'reserve_factor'" in message
    assert "Failing column: 'good_col'" not in message
    assert "Failing column: 'other_col'" not in message
    assert excinfo.value._column_attributed is True  # noqa: SLF001


def test_a_failed_batch_keeps_polars_diagnosis_and_its_type() -> None:
    """The framework adds to what polars said; it does not replace or retype it."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        _bad_batch(af)

    assert "arithmetic on dtypes str and f64 is not allowed" in str(excinfo.value)


def test_off_records_the_batch_and_attributes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kill-switch stops the diagnosis, never the frame's own bookkeeping."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError) as excinfo:
        _bad_batch(af)

    assert "Failing column" not in str(excinfo.value)
    assert not hasattr(excinfo.value, "_column_attributed")
    assert [r.column for r in _records(af)[1:]] == [
        "good_col",
        "reserve_factor",
        "other_col",
    ]


def test_a_batch_that_never_reached_the_plan_records_nothing() -> None:
    """The other direction: the log must not claim a column the plan never got."""
    af = _frame()
    before = len(af._calculations)  # noqa: SLF001

    with pytest.raises(ValueError, match="Could not determine output name"):
        af.with_columns(pl.col("sum_assured", "mortality_rate") * 2.0)

    assert len(af._calculations) == before  # noqa: SLF001


def test_a_successful_batch_still_records_resolved_dtypes() -> None:
    """The success path is untouched: its records carry the schema's own answer."""
    af = _frame()
    af.with_columns(
        (pl.col("sum_assured") * 2.0).alias("good_col"),
        (pl.col("mortality_rate") * 3.0).alias("other_col"),
    )

    dtypes = {r.column: r.dtype for r in _records(af)}
    assert dtypes["good_col"] == pl.Float64
    assert dtypes["other_col"] == pl.Float64


def test_a_recorder_that_raises_leaves_no_column_claimed_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler must not mint a batch the success path was already minting.

    Not reachable from user code -- recording is bookkeeping over a name,
    a node and an expression -- but the window is what says who owns the
    log entry, and while the recorder holds it the handler does not. A
    batch recorded half by one call and whole by another would claim a
    column twice, under two operation ids, for one step of the plan.
    """
    af = _frame()
    record = ActuarialFrame._record_calculation  # noqa: SLF001 -- the recorder under test
    seen = itertools.count()

    def _raise_on_the_second_column(
        self: ActuarialFrame, column: str, **kwargs: object
    ) -> None:
        if next(seen) == 1:
            msg = "simulated recorder failure"
            raise RuntimeError(msg)
        record(self, column, **kwargs)

    monkeypatch.setattr(
        ActuarialFrame, "_record_calculation", _raise_on_the_second_column
    )

    with pytest.raises(RuntimeError, match="simulated recorder failure"):
        af.with_columns(
            (pl.col("sum_assured") * 2.0).alias("good_col"),
            (pl.col("mortality_rate") * 3.0).alias("other_col"),
        )

    columns = [r.column for r in _records(af)]
    assert columns == ["duration", "good_col"]
    assert len({r.operation_id for r in _records(af)[1:]}) == 1


def test_the_graph_answers_for_a_failed_batch() -> None:
    """The log feeds the graph, so the graph can name the column too."""
    af = _frame()
    with pytest.raises(pl.exceptions.InvalidOperationError):
        _bad_batch(af)

    assert af.graph.versions("reserve_factor") == ("reserve_factor@1",)
    assert af.graph.precedents("reserve_factor") == ("product_code", "sum_assured")
    assert af.graph.holes() == []
