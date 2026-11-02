# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The frame-level date verbs stamp in place and take a column by name."""

import datetime
import warnings

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        {
            "policy_id": [1, 2],
            "issue_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
            "end_date": [datetime.date(2023, 3, 15), datetime.date(2023, 8, 30)],
        }
    )


def test_add_duration_by_name_modifies_the_frame_in_place() -> None:
    """A column named by string is offset, and the frame handed back is the same one."""
    af = _frame()

    returned = af.date.add_duration("issue_date", "1y")

    assert returned is af
    out = af.collect()
    assert out["issue_date"].to_list() == [
        datetime.date(2024, 1, 15),
        datetime.date(2024, 6, 30),
    ]


def test_add_duration_by_name_with_a_new_column_is_in_place_too() -> None:
    """Naming a new column adds it to the frame rather than to a copy of it."""
    af = _frame()

    returned = af.date.add_duration("issue_date", "1y", new_col_name="anniversary")

    assert returned is af
    assert "anniversary" in af.columns


def test_add_duration_names_a_missing_column() -> None:
    """A name the frame does not carry is refused at the call, by name."""
    af = _frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError, match="issue_dat"):
        af.date.add_duration("issue_dat", "1y")


def test_create_timeline_names_a_missing_column() -> None:
    """The same refusal covers the timeline's start and end designators."""
    af = _frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError, match="end_dat"):
        af.date.create_timeline("issue_date", "end_dat", freq="1mo")


def test_create_timeline_returns_the_same_frame() -> None:
    """Exploding to one row per period reshapes this frame; it does not replace it."""
    af = _frame()

    returned = af.date.create_timeline(
        "issue_date", "end_date", freq="1mo", new_col_name="month_end"
    )

    assert returned is af
    assert af.collect().height == 4


def test_create_timeline_carries_the_calculation_log_and_the_hole() -> None:
    """The model's history survives the explode, holes included."""
    af = _frame()
    af.term_months = 12
    plan = af._df  # noqa: SLF001 -- the bypass that makes the hole
    assert plan is not None
    af._df = plan.with_columns(pl.lit(1.0).alias("shadow"))  # noqa: SLF001

    af.date.create_timeline(af.issue_date, af.end_date, freq="1mo")

    assert [h.column for h in af.graph.holes()] == ["shadow"]
    assert "term_months" in {r.column for r in af._calculation_records()}  # noqa: SLF001
    assert "timeline_date" in {r.column for r in af._calculation_records()}  # noqa: SLF001


def test_create_timeline_explodes_without_a_deprecation_warning() -> None:
    """The explode names the argument Polars 2.0 will stop defaulting for us."""
    af = _frame()

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        af.date.create_timeline(af.issue_date, af.end_date, freq="1mo")
        af.collect()


def test_reserved_accessor_names_are_documented() -> None:
    """Every frame accessor says that its own name is reserved on the frame."""
    from gaspatchio.accessors.date import DateFrameAccessor
    from gaspatchio.accessors.excel import ExcelFrameAccessor
    from gaspatchio.accessors.finance import FinanceFrameAccessor
    from gaspatchio.accessors.projection_frame import ProjectionFrameAccessor

    assert 'af["date"]' in (DateFrameAccessor.__doc__ or "")
    assert 'af["excel"]' in (ExcelFrameAccessor.__doc__ or "")
    assert 'af["finance"]' in (FinanceFrameAccessor.__doc__ or "")
    assert 'af["projection"]' in (ProjectionFrameAccessor.__doc__ or "")


def test_the_frame_lists_its_reserved_attribute_names() -> None:
    """Attribute access on the frame documents which names it keeps for itself."""
    doc = ActuarialFrame.__getattr__.__doc__ or ""

    for name in ("date", "excel", "finance", "graph", "projection"):
        assert f"``{name}``" in doc


def test_create_timeline_refuses_a_name_the_frame_already_holds() -> None:
    """The timeline is a new column, so it will not shadow one already there."""
    af = _frame()

    with pytest.raises(ValueError, match="end_date") as excinfo:
        af.date.create_timeline("issue_date", "end_date", new_col_name="end_date")

    message = str(excinfo.value)
    assert "already a column" in message
    assert "drop" in message


def test_the_graph_answers_for_the_timeline_the_moment_it_is_stamped() -> None:
    """Reading the graph before the explode does not stale the answer after it.

    The in-place stamp swaps the plan through the ``_df`` setter, which
    bumps the generation the graph cache is keyed on. Folding the graph
    first is what makes that load-bearing: a cache that did not notice
    would answer the post-timeline question with the pre-timeline model.
    """
    af = _frame()
    af.term_months = 12

    holes_before = [hole.column for hole in af.graph.holes()]
    assert af.graph.precedents("term_months") == ()
    with pytest.raises(ValueError, match="timeline_date"):
        af.graph.latest("timeline_date")

    af.date.create_timeline("issue_date", "end_date", freq="1mo")

    assert af.graph.latest("timeline_date") == "timeline_date@1"
    assert af.graph.precedents("timeline_date") == ("issue_date", "end_date")
    assert af.graph.precedents("term_months") == ()
    assert [hole.column for hole in af.graph.holes()] == holes_before
