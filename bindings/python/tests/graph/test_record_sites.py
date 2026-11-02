# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the doors that mint a column name without an assignment.

``__setitem__`` and ``with_columns`` are the obvious ways a column appears
on a frame, and ``test_log.py`` covers both. They are not the only ways. A
``rename`` moves a calculation to a new name. A ``join`` brings columns in
from another table. ``projection.set`` stamps the timeline's own index.
Each of those puts a name on the frame that a reviewer can later ask about,
so each leaves a record.

The records these doors mint are deliberately kept OUT of the attribution
window. Replay splices a window's records onto the window's baseline as
grouped ``with_columns`` calls -- an honest re-application for a
calculation, and a fiction for a rename (whose source name no longer
exists after the operation) or for a joined column (which no expression on
this frame ever computed). Every site below therefore advances the cursor
past its own records: the log answers "where did this column come from?",
and attribution never tries to re-run the answer.

``materialize()`` is the fourth door and mints no column at all. It freezes
the plan's values, which makes every calculation before it a fact rather
than a recipe, and marks that with the log's one non-calculation entry.
"""

from __future__ import annotations

import datetime
from inspect import currentframe
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio._source import is_framework_or_interpreter_file
from gaspatchio.frame.calculations import BoundaryRecord, CalculationRecord
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import AttrValue

# --- fixtures ---------------------------------------------------------------


def _policy_frame() -> ActuarialFrame:
    """Return a three-policy model point frame, named the way an actuary would."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "product_code": ["TERM", "TERM", "WHOLE_LIFE"],
                "issue_age": [30, 31, 30],
                "sum_assured": [100_000.0, 200_000.0, 150_000.0],
                "annual_premium": [1_200.0, 2_400.0, 1_800.0],
                "mortality_rate": [0.001, 0.002, 0.0015],
            }
        )
    )


def _expense_table() -> pl.DataFrame:
    """Return a product-level expense loading table, the classic join right side."""
    return pl.DataFrame(
        {
            "product_code": ["TERM", "WHOLE_LIFE"],
            "expense_loading": [0.05, 0.08],
            "commission_rate": [0.40, 0.55],
        }
    )


def _records(frame: ActuarialFrame) -> list[CalculationRecord]:
    """Return every calculation record on ``frame``, boundaries excluded."""
    return [
        entry
        for entry in frame._calculations  # noqa: SLF001 -- the log under test
        if isinstance(entry, CalculationRecord)
    ]


def _by_column(frame: ActuarialFrame, column: str) -> list[CalculationRecord]:
    """Return every record ``frame`` holds for one column, in log order."""
    return [record for record in _records(frame) if record.column == column]


def _attrs(record: CalculationRecord) -> dict[str, AttrValue]:
    """Return the record node's attributes as a mapping, for readable asserts."""
    assert isinstance(record.node, Call)
    return dict(record.node.attrs)


# --- rename -----------------------------------------------------------------


def test_a_rename_records_the_new_name_as_a_move_of_its_source() -> None:
    """A rename is a name-move: the record's node is the column it came from."""
    af = _policy_frame()

    af = af.rename({"annual_premium": "gross_annual_premium"})

    record = _by_column(af, "gross_annual_premium")[-1]
    assert record.node == Col("annual_premium")
    assert record.origin == "rename"
    assert record.ordinal == 1


def test_a_rename_records_the_expression_that_would_perform_the_move() -> None:
    """The recorded expression names both ends of the move, not just one."""
    af = _policy_frame()

    af = af.rename({"annual_premium": "gross_annual_premium"})

    expression_text = str(_by_column(af, "gross_annual_premium")[-1].expr)
    assert "annual_premium" in expression_text
    assert "gross_annual_premium" in expression_text


def test_one_rename_call_is_one_transaction_however_many_columns_it_moves() -> None:
    """Renaming three columns is one statement, so the records share one id."""
    af = _policy_frame()

    af = af.rename(
        {
            "policy_id": "policy_number",
            "issue_age": "age_at_issue",
            "sum_assured": "face_amount",
        }
    )

    renamed = [record for record in _records(af) if record.origin == "rename"]
    assert len(renamed) == 3
    assert len({record.operation_id for record in renamed}) == 1


def test_renaming_a_calculated_column_leaves_its_original_record_intact() -> None:
    """The calculation stays answerable under the name it was computed with."""
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = af.rename({"acquisition_expenses": "initial_expenses"})

    assert [record.column for record in _records(af)] == [
        "acquisition_expenses",
        "initial_expenses",
    ]


def test_rename_records_sit_behind_the_attribution_cursor() -> None:
    """Replay must never re-apply a move whose source name is already gone."""
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = af.rename({"acquisition_expenses": "initial_expenses"})

    assert af._attribution_ops() == []  # noqa: SLF001


def test_a_rename_records_the_dtype_the_moved_column_carries() -> None:
    """The column's type survives the move, so the record can state it."""
    af = _policy_frame()

    af = af.rename({"annual_premium": "gross_annual_premium"})

    assert _by_column(af, "gross_annual_premium")[-1].dtype == pl.Float64


# --- join -------------------------------------------------------------------


def test_every_column_arriving_from_the_right_side_gets_a_record() -> None:
    """Two expense columns arrive, so two records name where they came from."""
    af = _policy_frame()

    af = af.join(_expense_table(), on="product_code")

    joined = [record for record in _records(af) if record.origin == "join"]
    assert [record.column for record in joined] == [
        "expense_loading",
        "commission_rate",
    ]


def test_a_join_key_already_on_the_frame_is_not_recorded_as_arriving() -> None:
    """The key column was already here; only genuinely new names are minted."""
    af = _policy_frame()

    af = af.join(_expense_table(), on="product_code")

    assert _by_column(af, "product_code") == []


def test_one_join_is_one_transaction() -> None:
    """Every column the join brought in came from one call, so one id."""
    af = _policy_frame()

    af = af.join(_expense_table(), on="product_code")

    joined = [record for record in _records(af) if record.origin == "join"]
    assert len({record.operation_id for record in joined}) == 1


def test_the_join_record_names_the_keys_and_the_join_type() -> None:
    """A reviewer asking how a column arrived gets the keys and the join type."""
    af = _policy_frame()

    af = af.join(_expense_table(), on="product_code", how="left")

    attrs = _attrs(_by_column(af, "expense_loading")[-1])
    assert attrs["on"] == "product_code"
    assert attrs["how"] == "left"


def test_several_join_keys_are_recorded_as_one_flat_value() -> None:
    """Attributes are flat typed values, so a key list is joined into one string."""
    af = _policy_frame()
    right = pl.DataFrame(
        {
            "product_code": ["TERM", "TERM"],
            "issue_age": [30, 31],
            "underwriting_class": ["STANDARD", "PREFERRED"],
        }
    )

    af = af.join(right, on=["product_code", "issue_age"], on_missing="null")

    attrs = _attrs(_by_column(af, "underwriting_class")[-1])
    assert attrs["on"] == "product_code,issue_age"


def test_the_join_record_fingerprints_the_right_sides_content() -> None:
    """The right side is identified by content, the way an assumption table is."""
    af = _policy_frame()

    af = af.join(_expense_table(), on="product_code")

    fingerprint = _attrs(_by_column(af, "expense_loading")[-1])["right_fingerprint"]
    assert isinstance(fingerprint, str)
    assert fingerprint.startswith("sha256:")


def test_the_right_side_fingerprint_changes_when_the_right_side_does() -> None:
    """A changed expense loading is a different table, so a different fingerprint."""
    baseline = _policy_frame().join(_expense_table(), on="product_code")
    changed_table = _expense_table().with_columns(
        pl.col("expense_loading") * 2.0,
    )

    revised = _policy_frame().join(changed_table, on="product_code")

    assert (
        _attrs(_by_column(revised, "expense_loading")[-1])["right_fingerprint"]
        != _attrs(_by_column(baseline, "expense_loading")[-1])["right_fingerprint"]
    )


def test_the_right_side_fingerprint_ignores_the_order_the_rows_arrived_in() -> None:
    """The same table loaded in a different row order is the same table."""
    baseline = _policy_frame().join(_expense_table(), on="product_code")
    reordered = _policy_frame().join(
        _expense_table().sort("product_code", descending=True),
        on="product_code",
    )

    assert (
        _attrs(_by_column(reordered, "expense_loading")[-1])["right_fingerprint"]
        == _attrs(_by_column(baseline, "expense_loading")[-1])["right_fingerprint"]
    )


def test_a_lazy_right_side_claims_no_content_fingerprint() -> None:
    """Reading a lazy right side to hash it would defeat the point of it being lazy."""
    af = _policy_frame()

    af = af.join(_expense_table().lazy(), on="product_code")

    assert _attrs(_by_column(af, "expense_loading")[-1])["right_fingerprint"] is None


def test_join_records_sit_behind_the_attribution_cursor() -> None:
    """No expression on this frame computed the arriving column, so none replays."""
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = af.join(_expense_table(), on="product_code")

    assert af._attribution_ops() == []  # noqa: SLF001


# --- projection.set ---------------------------------------------------------


def _projected(af: ActuarialFrame) -> ActuarialFrame:
    """Stamp a thirty-year monthly timeline anchored at a valuation date."""
    return af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=30,
        frequency="monthly",
    )


def test_the_projection_timeline_records_the_month_index_it_stamps() -> None:
    """The period index is a column the framework computed, so it has a record."""
    af = _projected(_policy_frame())

    record = _by_column(af, "month")[-1]
    assert isinstance(record.node, Call)
    assert record.node.name == "projection_set"
    assert record.origin == "projection"
    assert record.ordinal == 1


def test_the_projection_record_carries_the_horizon_as_a_typed_integer() -> None:
    """A thirty-year horizon is the integer thirty, never the text "30"."""
    af = _projected(_policy_frame())

    until_value = _attrs(_by_column(af, "month")[-1])["until_value"]
    assert until_value == 30
    assert isinstance(until_value, int)
    assert not isinstance(until_value, str)


def test_the_projection_record_carries_the_frequency_and_the_horizon_kind() -> None:
    """The timeline's shape is recorded as the caller declared it."""
    af = _projected(_policy_frame())

    attrs = _attrs(_by_column(af, "month")[-1])
    assert attrs["frequency"] == "monthly"
    assert attrs["until"] == "term_years"


def test_the_projection_record_carries_the_valuation_date_as_an_iso_string() -> None:
    """A date is not one of the flat attribute types, so it is recorded as ISO text."""
    af = _projected(_policy_frame())

    assert _attrs(_by_column(af, "month")[-1])["valuation_date"] == "2026-01-01"


def test_the_projection_timeline_records_every_column_it_stamps() -> None:
    """The dates and the period count are minted names too, not free columns."""
    af = _projected(_policy_frame())

    projection_records = [
        record for record in _records(af) if record.origin == "projection"
    ]
    assert {record.column for record in projection_records} == {
        "projection_start_date",
        "projection_end_date",
        "num_proj_months",
        "month",
    }
    assert len({record.operation_id for record in projection_records}) == 1


def test_the_policy_anchored_call_form_records_every_attribute() -> None:
    """The horizon call form is the one that fills the record completely."""
    af = _projected(_policy_frame())

    assert _attrs(_by_column(af, "month")[-1]) == {
        "frequency": "monthly",
        "until": "term_years",
        "until_value": 30,
        "valuation_date": "2026-01-01",
    }


def test_the_synthetic_call_form_records_its_own_parameters() -> None:
    """A start date and a period count are this form's own arguments.

    The gap this test used to pin -- a six-period and a six-hundred-period
    projection recording identically -- is now closed: ``start`` (ISO date
    text, the same encoding ``valuation_date`` gets) and ``n_periods`` (int)
    are this call form's actual timeline-shaping arguments, so they join
    ``frequency`` in the record. ``until``/``until_value``/``valuation_date``
    still read ``None`` -- this call form simply has no such arguments, the
    same way ``start``/``n_periods`` are absent from the other two forms.
    """
    af = _policy_frame().projection.set(
        start_date=datetime.date(2026, 1, 1),
        n_periods=6,
        frequency="monthly",
    )

    assert _attrs(_by_column(af, "month")[-1]) == {
        "frequency": "monthly",
        "until": None,
        "until_value": None,
        "valuation_date": None,
        "start": "2026-01-01",
        "n_periods": 6,
    }


def test_the_synthetic_call_forms_period_count_now_distinguishes_the_record() -> None:
    """A six-period and a six-hundred-period request no longer record alike."""
    short = _policy_frame().projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=6, frequency="monthly"
    )
    long_ = _policy_frame().projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=600, frequency="monthly"
    )

    assert _attrs(_by_column(short, "month")[-1])["n_periods"] == 6
    assert _attrs(_by_column(long_, "month")[-1])["n_periods"] == 600


def test_the_schedule_call_form_states_the_schedules_own_identity() -> None:
    """Handing over a built Schedule states what the object itself carries.

    ``frequency`` is a required field on every ``Schedule``, so it is always
    genuinely present here -- unlike the kwargs forms, this one has no raw
    caller argument to echo, so it is read straight off the object.
    ``start`` is this schedule's own ``start_date`` -- a ``from_calendar_grid``
    schedule always has one (see the ``from_inception`` test below for the
    kind that does not). ``schedule_source_sha`` is the object's own
    ``source_sha()``, reused rather than rehashed. ``until_value`` still
    reads ``None``: a schedule's ``n_periods`` is a period count, not a term
    in one of ``until_value``'s shapes, so recording it under that name
    would assert a horizon kind nobody declared. ``valuation_date`` reads
    ``None`` too, but only because that name belongs to the policy-anchored
    form's own argument -- this schedule's start date is the one genuinely
    present here, reported as ``start`` instead.
    """
    schedule = Schedule.from_calendar_grid(
        start_date=datetime.date(2026, 1, 31),
        n_periods=12,
        frequency="1M",
    )

    af = _policy_frame().projection.set(schedule=schedule)

    assert _attrs(_by_column(af, "month")[-1]) == {
        "frequency": "1M",
        "until": None,
        "until_value": None,
        "valuation_date": None,
        "start": "2026-01-31",
        "schedule_source_sha": schedule.source_sha(),
    }
    assert af.projection.source_sha().startswith("sha256:")


def test_the_schedule_call_form_states_until_for_a_per_policy_schedule() -> None:
    """A per-policy (jagged) Schedule genuinely carries an ``until_kind``.

    A shared calendar grid (the test above) has no ``until`` concept at all
    -- only ``n_periods``. A per-policy grid is built with one, so the
    record states it honestly rather than reporting ``None`` where a real
    answer sits on the object. It also has its own shared ``start_date``,
    same as a calendar grid, so ``start`` is populated here too.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "term": [6, 12]}))
    schedule = Schedule.from_per_policy_grid(
        start_date=datetime.date(2026, 1, 31),
        frequency="1M",
        until_kind="term_months",
        until_value_column="term",
    )

    af = af.projection.set(schedule=schedule)

    assert _attrs(_by_column(af, "month")[-1]) == {
        "frequency": "1M",
        "until": "term_months",
        "until_value": None,
        "valuation_date": None,
        "start": "2026-01-31",
        "schedule_source_sha": schedule.source_sha(),
    }


def test_the_schedule_call_form_states_no_start_for_a_from_inception_schedule() -> None:
    """A ``from_inception`` Schedule has no single shared ``start_date``.

    Its axis is anchored per-policy on a column of inception dates instead
    -- there is no one date the object itself carries, so ``start`` reads
    ``None`` here genuinely, the same way ``until`` reads ``None`` for the
    calendar-grid test above. ``from_inception`` never stamps ``month``
    (see the period-index tests), so this reads the record off
    ``num_proj_months`` instead -- every stamped column shares one record.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "policy_inception": [
                    datetime.date(2020, 6, 15),
                    datetime.date(2021, 3, 1),
                ],
            }
        )
    )
    schedule = Schedule.from_inception(
        inception_column="policy_inception",
        n_periods=12,
        frequency="1M",
    )

    af = af.projection.set(schedule=schedule)

    assert _attrs(_by_column(af, "num_proj_months")[-1]) == {
        "frequency": "1M",
        "until": None,
        "until_value": None,
        "valuation_date": None,
        "start": None,
        "schedule_source_sha": schedule.source_sha(),
    }


def test_setting_the_timeline_keeps_the_frame_it_was_called_on() -> None:
    """The timeline is a step in the same model, not a different frame."""
    af = _policy_frame()

    projected = _projected(af)

    assert projected is af


def test_calculations_before_and_after_the_timeline_share_one_unbroken_log() -> None:
    """Phase one and phase three are one model, so one continuous history.

    The timeline used to be stamped onto a freshly constructed frame, which
    is the shape that loses a log. Stamping it on the frame the model is
    already holding is what keeps ``acquisition_expenses`` answerable after
    the projection axis exists.
    """
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = _projected(af)
    af.acquisition_expenses = af.acquisition_expenses * 1.1

    expense_records = _by_column(af, "acquisition_expenses")
    assert [record.ordinal for record in expense_records] == [1, 2]
    assert expense_records[0].origin == "assignment"


def test_setting_the_timeline_leaves_the_frames_input_columns_alone() -> None:
    """The model points arrived as inputs and stay inputs after the timeline."""
    af = _policy_frame()
    inputs_before = af._initial_columns  # noqa: SLF001

    af = _projected(af)

    assert af._initial_columns == inputs_before  # noqa: SLF001


def test_the_projection_record_sits_behind_the_attribution_cursor() -> None:
    """The stamped plan is structurally new; nothing across it may be replayed."""
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = _projected(af)

    assert af._attribution_ops() == []  # noqa: SLF001


def test_a_column_read_after_the_timeline_still_binds_to_its_earlier_version() -> None:
    """A phase-one column keeps its value once the projection axis exists."""
    af = _policy_frame()
    af.acquisition_expenses = af.annual_premium * 0.05

    af = _projected(af)
    af.total_expenses = af.acquisition_expenses * 2.0

    result = af.collect()
    assert result["total_expenses"].to_list() == pytest.approx([120.0, 240.0, 180.0])


def test_the_timeline_registers_its_stamped_columns_for_attribute_access() -> None:
    """``af.month`` has to resolve after the stamp, exactly as before."""
    af = _projected(_policy_frame())

    assert "month" in af.columns
    assert "num_proj_months" in af.columns


# --- materialize ------------------------------------------------------------


def _plan_text(frame: ActuarialFrame) -> str:
    """Return the frame's unoptimised query plan as text."""
    plan = frame._df  # noqa: SLF001 -- the plan under test
    assert plan is not None
    return plan.explain(optimized=False)


def test_materialize_freezes_the_plan_into_values() -> None:
    """Downstream work starts from data, not from the recipe that produced it."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    assert "WITH_COLUMNS" in _plan_text(af)

    af = af.materialize()

    assert "WITH_COLUMNS" not in _plan_text(af)


def test_materialize_preserves_every_value_it_froze() -> None:
    """Freezing changes when the work happens, never what the answer is."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    expected = af.collect()["death_claims"].to_list()

    af = af.materialize()

    assert af.collect()["death_claims"].to_list() == pytest.approx(expected)


def test_materialize_returns_the_frame_it_was_called_on() -> None:
    """Materialising is a step in the same model, not a new one."""
    af = _policy_frame()

    assert af.materialize() is af


def test_materialize_marks_the_log_with_a_materialization_boundary() -> None:
    """The one event that mints no column still leaves its mark on the log."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate

    af = af.materialize()

    boundary = af._calculations[-1]  # noqa: SLF001
    assert isinstance(boundary, BoundaryRecord)
    assert boundary.kind == "materialization"
    assert boundary.position == 1


def test_materialize_records_where_the_freeze_was_asked_for() -> None:
    """A freeze nobody can locate is one found only by reading the whole model."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    freeze_line = currentframe().f_lineno + 1
    af = af.materialize()

    boundary = af._calculations[-1]  # noqa: SLF001
    assert isinstance(boundary, BoundaryRecord)
    assert boundary.source is not None
    assert boundary.source.file == __file__
    assert boundary.source.line == freeze_line
    assert boundary.source.statement == "af = af.materialize()"


def test_materialize_keeps_every_calculation_record() -> None:
    """A frozen model is exactly the model someone will ask questions about."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af.acquisition_expenses = af.annual_premium * 0.05

    af = af.materialize()

    assert [record.column for record in _records(af)] == [
        "death_claims",
        "acquisition_expenses",
    ]


def test_ordinals_continue_across_a_materialization() -> None:
    """Reassigning a frozen column continues its count; it does not restart it."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate

    af = af.materialize()
    af.death_claims = af.death_claims * 1.05

    assert [record.ordinal for record in _by_column(af, "death_claims")] == [1, 2]


def test_the_materialization_boundary_never_lands_in_the_attribution_window() -> None:
    """A boundary in a window tail replays pre-freeze records onto a frozen plan."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate

    af = af.materialize()

    assert af._attribution_ops() == []  # noqa: SLF001


def test_calculations_after_a_materialization_open_a_fresh_window() -> None:
    """The next assignment after a freeze is the new window's first suspect."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af = af.materialize()

    af.acquisition_expenses = af.annual_premium * 0.05

    assert [record.column for record in af._attribution_ops()] == [  # noqa: SLF001
        "acquisition_expenses",
    ]


def test_materialize_keeps_the_projection_timeline() -> None:
    """Freezing values does not forget which time axis the model is on."""
    af = _projected(_policy_frame())
    schedule = af._projection  # noqa: SLF001

    af = af.materialize()

    assert af._projection is schedule  # noqa: SLF001


def test_a_rollforward_state_read_after_a_materialization_still_resolves() -> None:
    """Freezing drops the kernel's hidden column; the next read rebuilds it.

    ``collect()`` strips the ``__rollforward_*`` struct column before
    materialising, so the frozen plan no longer carries it. A state read
    after the freeze references a column the schema does not have, and
    ``_ensure_rollforward_sources`` re-materialises it over the frozen
    plan. This is the chain that keeps a rollforward usable either side
    of a freeze, and it is worth a test rather than a reading.
    """
    from gaspatchio.rollforward._compile import compile_rollforward

    n_periods = 6
    af = ActuarialFrame(
        {
            "account_value_initial": [100_000.0],
            "charges_paid_initial": [0.0],
            "fund_return": [[0.01] * n_periods],
            "expense_charge": [[0.001] * n_periods],
        }
    )
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 31),
        n_periods=n_periods,
        frequency="monthly",
    )
    builder = af.projection.rollforward(
        states={
            "account_value": af["account_value_initial"],
            "charges_paid": af["charges_paid_initial"],
        },
    )
    builder["account_value"].grow(af["fund_return"], label="fund_return").charge(
        af["expense_charge"], label="expense_charge"
    )
    builder["charges_paid"].add(af["expense_charge"], label="expense_charge")
    compiled = compile_rollforward(builder)

    af.account_value = compiled.expr_for("account_value")
    af = af.materialize()
    af.charges_paid = compiled.expr_for("charges_paid")

    result = af.collect()
    period_factor = 1.01 * (1 - 0.001)
    assert result["account_value"][0][-1] == pytest.approx(
        100_000.0 * period_factor**n_periods
    )
    assert result["charges_paid"][0][-1] == pytest.approx(0.001 * n_periods)
    assert not [name for name in result.columns if name.startswith("__rollforward_")]


def test_materialize_refuses_an_uninitialised_frame() -> None:
    """There is nothing to freeze, and silently inventing an empty frame is worse."""
    af = ActuarialFrame()

    with pytest.raises(ValueError, match="uninitialized"):
        af.materialize()


# --- source attribution through the accessor layer --------------------------


def test_setting_the_timeline_attributes_to_the_callers_own_statement() -> None:
    """The projection record reports the model author's line, not the accessor's.

    ``projection.set`` mints its record from inside
    ``gaspatchio/accessors/``. Without that directory in the capture's
    internal-frame patterns the walk stops at the accessor and blames
    framework code for a column the author asked for.
    """
    af = _policy_frame()

    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=30,
        frequency="monthly",
    )

    source = _by_column(af, "month")[-1].source
    assert source is not None
    assert source.file == __file__
    assert "projection.set(" in source.statement


def test_a_frame_accessor_column_attributes_to_the_callers_own_statement() -> None:
    """A frame accessor computing a column reports the caller's line too."""
    af = ActuarialFrame(
        {
            "policy_id": [1],
            "forward_rates": [[0.003, 0.004, 0.005]],
            "period_index": [[0, 1, 2]],
        }
    )

    af = af.finance.discount_factor(
        rate_col="forward_rates",
        periods_col="period_index",
        output_col="discount_factors",
        method="forward",
    )

    source = _by_column(af, "discount_factors")[-1].source
    assert source is not None
    assert source.file == __file__
    assert "discount_factor(" in source.statement


def test_the_internal_frame_rule_covers_the_accessor_package() -> None:
    """The accessor directory is framework machinery the capture walks past."""
    from gaspatchio.accessors import projection_frame

    assert is_framework_or_interpreter_file(projection_frame.__file__)


def test_the_internal_frame_rule_leaves_shipped_tutorial_models_alone() -> None:
    """A tutorial model is user code: its own lines must stay attributable.

    The tutorials ship as worked examples an actuary reads and edits, so
    they have to report themselves the way a model in the user's own
    directory does. Widening the internal patterns to the accessor
    package, or the whole of it, must not reach them.

    Every shipped Python file under ``tutorials/`` is walked, not just the
    ones named ``model.py``: the pattern files are numbered
    (``01_single_state_fund.py`` and friends) and are model code just the
    same.
    """
    from pathlib import Path

    import gaspatchio

    tutorials_root = Path(gaspatchio.__file__).parent / "tutorials"
    tutorial_files = sorted(tutorials_root.rglob("*.py"))
    assert tutorial_files, "expected shipped tutorial model code to walk"

    for tutorial_file in tutorial_files:
        assert not is_framework_or_interpreter_file(str(tutorial_file)), (
            f"{tutorial_file} would be treated as framework code"
        )


# --- the finance frame accessor keeps the frame's state ---------------------


def test_the_finance_frame_accessor_returns_the_frame_it_was_called_on() -> None:
    """Adding a discount factor column transforms the frame, it does not replace it."""
    af = ActuarialFrame(
        {
            "policy_id": [1],
            "forward_rates": [[0.003, 0.004, 0.005]],
            "period_index": [[0, 1, 2]],
        }
    )

    result = af.finance.discount_factor(
        rate_col="forward_rates",
        periods_col="period_index",
        output_col="discount_factors",
    )

    assert result is af


def test_the_finance_frame_accessor_keeps_the_calculation_log() -> None:
    """A discount factor does not erase how the rates it discounts were built."""
    af = ActuarialFrame(
        {
            "policy_id": [1],
            "annual_rates": [[0.003, 0.004, 0.005]],
            "period_index": [[0, 1, 2]],
        }
    )
    af.forward_rates = af.annual_rates * 1.0

    af = af.finance.discount_factor(
        rate_col="forward_rates",
        periods_col="period_index",
        output_col="discount_factors",
    )

    assert [record.column for record in _records(af)] == [
        "forward_rates",
        "discount_factors",
    ]


def test_the_finance_frame_accessor_records_what_it_computed() -> None:
    """The discount factor column names the operation that produced it."""
    af = ActuarialFrame(
        {
            "policy_id": [1],
            "forward_rates": [[0.003, 0.004, 0.005]],
            "period_index": [[0, 1, 2]],
        }
    )

    af = af.finance.discount_factor(
        rate_col="forward_rates",
        periods_col="period_index",
        output_col="discount_factors",
        method="forward",
    )

    node = _by_column(af, "discount_factors")[-1].node
    assert isinstance(node, Call)
    assert node.name == "finance.discount_factor"
    assert ("method", "forward") in node.attrs
