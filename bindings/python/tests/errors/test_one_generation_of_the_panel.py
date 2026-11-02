# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One generation of the panel, and one question deciding which failure gets it.

Two generations of the same diagnosis used to live in ``formatting_errors``.
The one still here builds from the calculation record -- the failing column,
the line the actuary wrote, and what the graph says that formula read. The
one retired here was built from the message: a ``Data type mismatch`` panel
scraped out of ``got invalid or ambiguous dtypes: '...'`` and a general
``Query compilation failed during optimization`` wall with a fixed list of
things to check. Both fired, on one shape each, and neither shape reaches
them without a source of the message that is not polars. The scrape wanted a
``ComputeError`` carrying ``got invalid or ambiguous dtypes``; polars raises
that sentence as an ``InvalidOperationError``, which the branch's
``isinstance`` test refused, so nothing in the suite ever reached it -- but
polars re-raises an exception raised
inside a UDF with the class the UDF chose, so a ``map_elements`` raising a
``ComputeError`` that carries the sentence reached the scrape through the
public API and was answered with a panel naming no column. The wall's shape
is a plugin refusing the dtypes it was handed while polars was still deciding
the plugin's output schema. Both shapes read as the attribution block now --
the failing column, the line the actuary wrote, the dtype the graph holds --
and pinning both ends of that is what these tests do.

Deciding which failure takes the missing-column route was two questions over
fifteen phrases, asked in sequence; it is one question over seven now (three
plan-resolution markers and four missing-column phrases), with the class
asked before any wording.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import polars as pl
import pytest

import gaspatchio.errors as errors_package
from gaspatchio import ActuarialFrame, when
from gaspatchio.errors.formatting_errors import (
    _classify_error_type,
    _is_column_reference_compilation_error,
)
from gaspatchio.errors.models import ErrorType
from gaspatchio.util import set_error_mode

# The headings of the retired generation. Named as data so the assertion
# that no source file builds them reads as the retirement it is.
_RETIRED_HEADINGS = (
    "❌ Data type mismatch in ",
    "❌ Query compilation failed during optimization",
)

_PACKAGE_ROOT = Path(errors_package.__file__).parents[1]

# Polars' own plan dump, trimmed to the two markers that say the failure
# happened while the plan was still being resolved.
_PLAN_DUMP = (
    "\n\nResolved plan until failure:\n\n"
    "\t---> FAILED HERE RESOLVING 'with_columns' <---\n"
    'DF ["a", "b"]; PROJECT */2 COLUMNS'
)


def _frame(**columns: object) -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame(columns))


# --- the two shapes the retired panels used to take -------------------------


def test_a_plugin_refusal_at_plan_resolution_names_the_failing_column() -> None:
    """A first-party plugin refusing its inputs is diagnosed, not walled off.

    ``excel.yearfrac`` on a string column fails while polars is deriving the
    plugin's output schema, so polars appends the plan dump to a
    ``ComputeError``. That combination -- a ``ComputeError`` carrying
    ``FAILED HERE RESOLVING`` -- was the one live way into the general
    compilation wall, which threw the attribution away and printed four
    generic things to check. The failing column is on the record and the
    operand dtype is on the graph, so the block says both.
    """
    set_error_mode("enhanced")
    af = _frame(policy_id=["1"], not_a_date=["2020-01-01"], number=[42])
    af.year_frac = af["not_a_date"].excel.yearfrac(datetime.date(2020, 7, 1))

    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()

    message = str(caught.value)
    assert "Failing column: 'year_frac'" in message
    assert "Reading:        not_a_date (str)" in message
    # Polars' own diagnosis survives ahead of the block.
    assert "yearfrac requires Date/Datetime" in message
    for heading in _RETIRED_HEADINGS:
        assert heading not in message


def test_a_udf_raising_polars_dtype_sentence_names_the_failing_column() -> None:
    """The scrape's one live door, pinned at what it reaches instead.

    Polars re-raises an exception raised inside a UDF with the class the UDF
    chose, so a ``map_elements`` whose body raises a
    ``pl.exceptions.ComputeError`` carrying polars' own ``got invalid or
    ambiguous dtypes`` sentence arrives carrying both -- the one combination
    the retired scrape was behind. It answered with a ``Data type mismatch``
    panel that read the operation and the dtypes back out of the sentence and
    named no column at all. Nothing in the suite reached it, because no
    polars-native producer of that sentence raises it as a ``ComputeError``;
    this one goes through the public API and needs no plugin.
    """
    set_error_mode("enhanced")

    def boom(_value: object) -> float:
        message = (
            "got invalid or ambiguous dtypes: '[i64, str]' "
            "in expression 'min_horizontal'"
        )
        raise pl.exceptions.ComputeError(message)

    af = _frame(policy_id=["1"], amount=[1.0])
    af.mapped = af.amount.map_elements(boom, return_dtype=pl.Float64)

    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect()

    message = str(caught.value)
    assert "Failing column: 'mapped'" in message
    assert "Reading:        amount (f64)" in message
    # Polars' own sentence -- what the scrape read -- survives ahead of it.
    assert "got invalid or ambiguous dtypes" in message
    for heading in _RETIRED_HEADINGS:
        assert heading not in message


# --- and the retirement itself ----------------------------------------------


def test_no_source_file_builds_the_retired_panels() -> None:
    """The second generation is gone from the package, not merely unreachable.

    A generation that no path reaches is still a generation a reader has to
    rule out, and the two here disagreed with the surviving one about what a
    dtype failure is called. Asserted over the package's own sources so that
    reintroducing either heading anywhere fails here rather than in whichever
    panel a user happens to see.
    """
    offenders = [
        f"{path.relative_to(_PACKAGE_ROOT)}: {heading}"
        for path in _PACKAGE_ROOT.rglob("*.py")
        for heading in _RETIRED_HEADINGS
        if heading in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --- one question, asked once ------------------------------------------------


def _polars_column_not_found() -> pl.exceptions.ColumnNotFoundError:
    """Polars' own missing-column error, plan dump and all."""
    try:
        pl.DataFrame({"age": [30]}).lazy().select(pl.col("premium_pp")).collect()
    except pl.exceptions.ColumnNotFoundError as err:
        return err
    msg = "polars accepted a column that is not there"
    raise AssertionError(msg)


def test_a_failure_raised_after_the_plan_resolved_is_not_a_column_reference() -> None:
    """The plan-resolution marker is read before the class, and it decides.

    A ``ColumnNotFoundError`` with no plan dump was never raised while polars
    was resolving anything -- it is a name a caller looked up on a frame it
    already had. Sending it down the did-you-mean route would skip the
    attribution replay that can name the calculation which asked for it, so
    the marker is tested first and this one is refused.
    """
    assert not _is_column_reference_compilation_error(
        pl.exceptions.ColumnNotFoundError('unable to find column "premium_pp"')
    )


def test_polars_own_missing_column_takes_the_route_by_its_class() -> None:
    """The class is the structural answer, and it is asked before any wording."""
    assert _is_column_reference_compilation_error(_polars_column_not_found())


def test_a_look_alike_needs_both_the_marker_and_the_words() -> None:
    """A class that is not polars' own reaches the route only by saying so.

    The look-alike arm exists for a plugin that words its own refusal as a
    missing column. No first-party plugin does, and no shape built through
    the public API reaches it -- these three construct the exception
    directly, which is the only way it can be reached today. Both halves of
    the name are asserted: the marker without the words is refused, and so
    are the words without the marker. That second refusal is the narrowing
    the merge introduced here, and it is the whole of what keeps a failure
    raised after the plan resolved out of the did-you-mean route however it
    words itself. It moves nothing a user sees: of the two questions this one
    replaced, the first found no marker here either, so the pair refused this
    input too.
    """
    assert _is_column_reference_compilation_error(
        pl.exceptions.ComputeError(
            f"the plugin failed with message: no column named 'rate'{_PLAN_DUMP}"
        )
    )
    assert not _is_column_reference_compilation_error(
        pl.exceptions.ComputeError(
            "the plugin failed with message: yearfrac requires Date/Datetime "
            f"or List[Date/Datetime] inputs, got str and date{_PLAN_DUMP}"
        )
    )
    assert not _is_column_reference_compilation_error(
        pl.exceptions.ComputeError("no column named 'rate'")
    )


# --- the category is the class ----------------------------------------------


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            pl.exceptions.ColumnNotFoundError('unable to find column "premium_pp"'),
            ErrorType.COLUMN_NOT_FOUND,
        ),
        (
            pl.exceptions.SchemaError(
                "datatypes of join keys don't match - `a`: i64 on left"
            ),
            ErrorType.SCHEMA_CONFLICT,
        ),
        (
            pl.exceptions.InvalidOperationError(
                "arithmetic on dtypes str and f64 is not allowed"
            ),
            ErrorType.INVALID_OPERATION,
        ),
        (
            pl.exceptions.ComputeError("column datatype mismatch: left-hand = 'i64'"),
            ErrorType.UNKNOWN,
        ),
    ],
)
def test_the_category_is_the_exception_class(
    exception: Exception, expected: ErrorType
) -> None:
    """Reading the category off the words mistakes any sentence carrying them.

    ``column datatype mismatch`` is polars' own wording and it contains
    ``type mismatch``; ``schema`` answered ``SCHEMA_CONFLICT`` for any
    message carrying the word, wherever it came from. Over forty-two failure
    shapes driven for this pin, twenty-three carried a plan dump and no dump
    contained it -- the four messages that did took it from polars' own
    diagnosis, where it describes the failure rather than naming a category.
    Both tests used to decide the category. The class decides it now, and the
    last row is the one that changes: a ``ComputeError`` quoting polars at
    itself earns no category rather than the wrong one.
    """
    assert _classify_error_type(exception) is expected


# --- what a user sees on each shape -----------------------------------------


def _projected(frame: ActuarialFrame) -> ActuarialFrame:
    return frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=3,
        frequency="annual",
    )


def _dtype_clash() -> ActuarialFrame:
    af = _projected(_frame(policy_id=["1"], code=["TERM"], sum_assured=[100.0]))
    af.reserve_factor = pl.col("code") * pl.col("sum_assured")
    return af


def _missing_column() -> ActuarialFrame:
    af = _projected(_frame(policy_id=["1"], sum_assured=[100.0]))
    af.boom = af.sum_assured * pl.col("no_such_column")
    return af


def _jagged_list() -> ActuarialFrame:
    df = pl.DataFrame(
        {
            "policy_id": ["1", "2"],
            "left": [[1.0, 2.0, 3.0], [1.0, 2.0]],
            "right": [[1.0, 2.0], [1.0, 2.0]],
        }
    )
    af = ActuarialFrame(df)
    af.jagged = af.left * af.right
    return af


def _ambiguous_supertype() -> ActuarialFrame:
    af = _projected(_frame(policy_id=["1"], issue_age=[40], code=["TERM"]))
    af.mixed = pl.min_horizontal(pl.col("issue_age"), pl.col("code"))
    return af


def _strict_cast() -> ActuarialFrame:
    af = _projected(_frame(policy_id=["1"], code=["TERM"]))
    af.coded = af.code.polars_native().cast(pl.Float64, strict=True)
    return af


# Each row: the shape, the class the user catches, and a fragment of the one
# panel they read. Five rows, four of them from the seven shapes the work
# order names -- a dtype clash, a missing column, a jagged list, a strict
# cast -- with an ambiguous supertype added. Of the other three, the
# compilation error and the plan-lowering panic have tests of their own,
# each arriving through a different entry point; the lookup miss has none
# here, because it reads byte for byte the same at both ends of the
# retirement.
_SHAPES = [
    (
        "a dtype clash",
        _dtype_clash,
        pl.exceptions.InvalidOperationError,
        "Failing column: 'reserve_factor'",
    ),
    (
        "a missing column",
        _missing_column,
        pl.exceptions.ColumnNotFoundError,
        "Column 'no_such_column' not found",
    ),
    (
        "a jagged list",
        _jagged_list,
        pl.exceptions.ShapeError,
        "Failing column: 'jagged'",
    ),
    (
        "an ambiguous supertype",
        _ambiguous_supertype,
        pl.exceptions.InvalidOperationError,
        "Failing column: 'mixed'",
    ),
    (
        "a strict cast",
        _strict_cast,
        pl.exceptions.InvalidOperationError,
        "Failing column: 'coded'",
    ),
]


@pytest.mark.parametrize(("name", "build", "raises", "fragment"), _SHAPES)
def test_the_panel_each_shape_reaches(
    name: str,
    build: object,
    raises: type[Exception],
    fragment: str | None,
) -> None:
    """One diagnosis per shape, and the retired headings on none of them.

    The missing column is the one shape that does not read as the block:
    it takes the did-you-mean route, where the frame's own column list
    answers better than a replay can.
    """
    set_error_mode("enhanced")
    with pytest.raises(raises) as caught:
        build().collect()

    message = str(caught.value)
    assert fragment in message, name
    for heading in _RETIRED_HEADINGS:
        assert heading not in message, name


def test_a_plan_lowering_panic_still_converts_and_carries_its_block() -> None:
    """The panic door is untouched: the third entry point keeps its contract."""
    set_error_mode("enhanced")
    af = ActuarialFrame(
        {"policy_id": [1], "issue_age": [40], "dur": [0], "a": [100.0], "b": [0.05]}
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=60,
        issue_age_column="issue_age",
        frequency="annual",
    )
    af.t = af.month // 12
    af.infl = (af.t * 0.0) + 1.01
    unbroadcastable = pl.col("a") * pl.col("b") + pl.col("a") * pl.col("infl")
    af.x = when(af.dur == 0).then(unbroadcastable).otherwise(0.0)

    with pytest.raises(pl.exceptions.SchemaError) as caught:
        af.collect()

    assert "Failing column: 'x'" in str(caught.value)
