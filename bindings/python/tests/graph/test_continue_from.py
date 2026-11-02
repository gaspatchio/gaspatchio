# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Bringing a DataFrame that genuinely left the frame back into the model.

``materialize()`` covers the freeze where nothing ever leaves: the values
settle and the frame carries on. The other half is the escape hatch the
skills themselves send people through -- collect the frame, hand the column
arrays to a numpy generator or an enrichment routine that only speaks
Polars, and come back with a DataFrame. Until now that DataFrame came back
as a stranger: every column in it arrived as a model-point field, and every
calculation that made it was gone.

``ActuarialFrame(df, continue_from=af)`` is the door back in. What it
promises is narrow on purpose. A column keeps the donor's lineage only if
its values are the ones the donor's calculations account for, checked
column by column against the donor's own plan; anything the trip changed,
and anything it added, arrives at the boundary as data from outside with
the line it came back on. Nothing here is automatic: the keyword is
written, or the DataFrame is a stranger as before.
"""

from __future__ import annotations

import json
from inspect import currentframe
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.calculations import BoundaryRecord, CalculationRecord
from gaspatchio.frame.graph import GraphExporter, fold, graph_fingerprint

if TYPE_CHECKING:
    from gaspatchio.frame.calculations import LogEntry


# --- the models these tests are about ---------------------------------------


def _priced_policies() -> ActuarialFrame:
    """Return a two-input model that has struck one claim column."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "q_mort": [0.001_23, 0.002_10, 0.004_05],
            }
        )
    )
    af.death_claims = af.sum_assured * af.q_mort
    return af


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _log(frame: ActuarialFrame) -> list[LogEntry]:
    """Return ``frame``'s durable log."""
    return frame._calculations  # noqa: SLF001 -- the frame's own log is the subject


def _shape_of(entries: list[LogEntry]) -> list[tuple[str, ...]]:
    """Return one comparable tuple per log entry, ignoring where it was written.

    Two frames that recorded the same model in the same order have the same
    shape here even though the statements that recorded them sit on
    different lines of this file, which is exactly the comparison the
    equivalence between the two doors is about.
    """
    shape: list[tuple[str, ...]] = []
    for entry in entries:
        if isinstance(entry, BoundaryRecord):
            shape.append(("boundary", entry.kind, str(entry.position)))
        else:
            shape.append(("record", entry.column, str(entry.ordinal), entry.origin))
    return shape


# --- the frame that never really left ---------------------------------------


def test_continuing_from_an_unchanged_collect_is_the_freeze_it_already_was() -> None:
    """The two doors are one door when nothing happened on the other side.

    ``materialize()`` is what a model writes when the frame never leaves.
    Handing its own collected values straight back through ``continue_from``
    is the same event described the long way round, and the record has to
    say so -- otherwise the escape hatch quietly means something different
    from the freeze it is standing in for.
    """
    frozen = _priced_policies().materialize()
    donor = _priced_policies()
    returned = ActuarialFrame(donor.collect(), continue_from=donor)

    assert _shape_of(_log(returned)) == _shape_of(_log(frozen))
    assert graph_fingerprint(fold(returned)) == graph_fingerprint(fold(frozen))


def test_an_unchanged_column_keeps_the_calculation_that_made_it() -> None:
    """The whole point: the claim column is still a claim the model struck."""
    donor = _priced_policies()
    returned = ActuarialFrame(donor.collect(), continue_from=donor)

    node = _node(_artifact(returned), "death_claims@1")
    assert node["kind"] == "computed"
    assert node["formula"] == "af.sum_assured * af.q_mort"
    assert node["reads"] == ["sum_assured", "q_mort"]


def test_an_unchanged_column_says_the_freeze_settled_it() -> None:
    """Downstream of the boundary a computed claim is data, and says which."""
    donor = _priced_policies()
    returned = ActuarialFrame(donor.collect(), continue_from=donor)

    assert _node(_artifact(returned), "death_claims@1")["materialized_at"] == 0


def test_a_column_a_reorder_cannot_change_keeps_its_definition_through_one() -> None:
    """The rule is the values, so what a permutation leaves alone is not lost.

    A whole-row reorder outside moves most columns' values and the carry
    records those as arriving data. A flat loading, a level rate, an
    all-true indicator are not among them: a constant compares equal row for
    row after any permutation, so the comparison passes and the node goes on
    saying what made it. Not a corner case -- these are ordinary model-point
    columns -- and a conformance test written from "every column arrives as
    data" would mark this producer non-conforming for behaving correctly.
    """
    donor = _priced_policies()
    donor.policy = pl.int_range(0, 3, eager=False)
    donor.flat_load = donor.sum_assured * 0.0 + 5.0
    outside = donor.collect()
    returned = ActuarialFrame(
        outside.sort("policy", descending=True), continue_from=donor
    )

    artifact = _artifact(returned)
    kept = _node(artifact, "flat_load@1")
    moved = _node(artifact, "death_claims@2")

    assert (kept["kind"], kept["provenance"]) == ("computed", "assignment")
    assert (moved["kind"], moved["provenance"]) == ("input", "continuation")


# --- the columns the trip outside changed or added --------------------------


def test_a_column_the_trip_added_arrives_at_the_boundary() -> None:
    """A simulated decrement is data from outside, located at the line it re-entered."""
    donor = _priced_policies()
    outside = donor.collect()
    rng = np.random.default_rng(20_260_903)
    outside = outside.with_columns(
        pl.Series("simulated_deaths", rng.binomial(1, outside["q_mort"].to_numpy()))
    )
    returned = ActuarialFrame(outside, continue_from=donor)
    line = currentframe().f_lineno - 1  # type: ignore[union-attr]

    node = _node(_artifact(returned), "simulated_deaths@1")
    assert node["kind"] == "input"
    assert node["provenance"] == "continuation"
    assert node["formula"] is None
    assert node["source_location"].endswith(f":{line}")


def test_a_column_whose_values_changed_outside_stops_claiming_the_old_formula() -> None:
    """A stale lineage claim is worse than the amnesia this door is fixing.

    The donor computed ``death_claims`` from a sum assured and a mortality
    rate. Something outside the frame rescaled it. The values in front of a
    reader are no longer the ones that formula produces, so the node holding
    them must not be the node stating it.
    """
    donor = _priced_policies()
    outside = donor.collect().with_columns(
        (pl.col("death_claims") * 1.10).alias("death_claims")
    )
    returned = ActuarialFrame(outside, continue_from=donor)

    artifact = _artifact(returned)
    superseded = _node(artifact, "death_claims@1")
    arrived = _node(artifact, "death_claims@2")
    assert superseded["in_final_schema"] is False
    assert arrived["in_final_schema"] is True
    assert (arrived["kind"], arrived["provenance"]) == ("input", "continuation")


def test_an_arriving_column_is_not_stamped_by_the_freeze_it_arrived_at() -> None:
    """It was not on the frame when the plan froze, so no freeze settled it."""
    donor = _priced_policies()
    outside = donor.collect().with_columns(
        pl.Series("reinsurance_share", [0.2, 0.3, 0.4])
    )
    returned = ActuarialFrame(outside, continue_from=donor)

    assert _node(_artifact(returned), "reinsurance_share@1")["materialized_at"] is None


def test_two_columns_of_one_re_entry_are_one_step_of_the_model() -> None:
    """One statement brought them back, so one operation id covers them both."""
    donor = _priced_policies()
    outside = donor.collect().with_columns(
        pl.Series("simulated_deaths", [1, 0, 1]),
        pl.Series("reinsurance_share", [0.2, 0.3, 0.4]),
    )
    returned = ActuarialFrame(outside, continue_from=donor)

    arrivals = [
        entry
        for entry in _log(returned)
        if isinstance(entry, CalculationRecord) and entry.origin == "continuation"
    ]
    assert [entry.column for entry in arrivals] == [
        "simulated_deaths",
        "reinsurance_share",
    ]
    assert len({entry.operation_id for entry in arrivals}) == 1


def test_a_model_carries_on_reading_what_came_back() -> None:
    """The columns either side of the boundary compose into one model."""
    donor = _priced_policies()
    outside = donor.collect().with_columns(pl.Series("simulated_deaths", [1, 0, 1]))
    returned = ActuarialFrame(outside, continue_from=donor)
    returned.simulated_claims = returned.sum_assured * returned.simulated_deaths

    node = _node(_artifact(returned), "simulated_claims@1")
    assert node["reads"] == ["sum_assured", "simulated_deaths@1"]
    assert returned.collect()["simulated_claims"].to_list() == [
        100_000.0,
        0.0,
        500_000.0,
    ]


def test_a_setup_that_joined_its_parameters_keeps_every_calculation() -> None:
    """The Phase-1 shape, which is where the naive check would fall over.

    A left join is free to hand the same rows back in a different order, so
    a re-run of this setup disagrees with the values it produced the first
    time on every row of every column. Verified against a second execution,
    a model like this one would come back with nothing but arriving data --
    which is the amnesia the door exists to fix, reached the long way round.
    """
    products = pl.DataFrame(
        {"product_id": ["P1", "P2"], "maint_fee_rate": [0.001, 0.002]}
    )
    donor = ActuarialFrame(
        pl.DataFrame(
            {
                "point_id": list(range(1_000)),
                "product_id": ["P1", "P2"] * 500,
                "sum_assured": [100_000.0, 250_000.0] * 500,
            }
        )
    )
    donor = donor.join(products, on="product_id", how="left")
    donor.maint_fee = donor.sum_assured * donor.maint_fee_rate

    returned = ActuarialFrame(donor.collect(), continue_from=donor)

    arrivals = [
        entry
        for entry in _log(returned)
        if isinstance(entry, CalculationRecord) and entry.origin == "continuation"
    ]
    assert arrivals == []
    assert _node(_artifact(returned), "maint_fee@1")["kind"] == "computed"


# --- the trip that wrote through the values the door checks against ---------


def test_the_donor_holds_its_own_container_not_the_one_the_caller_got() -> None:
    """A check against values the caller can still edit is not a check.

    ``collect()`` hands the caller a DataFrame and keeps what the call
    produced. Were those one object, Polars' in-place calls would write
    through the very values the door verifies a returning column against,
    and the comparison would be the tampered column against itself.
    """
    donor = _priced_policies()
    out = donor.collect()
    held = donor._collected_values  # noqa: SLF001 -- the held values are the subject

    assert held is not out
    assert held is not None
    assert held.equals(out)


def test_a_column_replaced_in_place_stops_claiming_the_formula_that_made_it() -> None:
    """``replace_column`` writes into the frame the caller was handed.

    The numbers under ``death_claims`` are no longer the ones
    ``sum_assured * q_mort`` produces, so the node holding them must not be
    the node stating it -- exactly as when the rescale returned a new frame.
    """
    donor = _priced_policies()
    out = donor.collect()
    out.replace_column(2, pl.Series("death_claims", [999.0, 999.0, 999.0]))
    returned = ActuarialFrame(out, continue_from=donor)

    artifact = _artifact(returned)
    assert _node(artifact, "death_claims@1")["in_final_schema"] is False
    arrived = _node(artifact, "death_claims@2")
    assert (arrived["kind"], arrived["provenance"]) == ("input", "continuation")
    assert arrived["formula"] is None
    assert returned.collect()["death_claims"].to_list() == [999.0, 999.0, 999.0]


def test_a_column_inserted_in_place_arrives_as_data_from_outside() -> None:
    """``insert_column`` writes into the frame the caller was handed.

    A decrement drawn outside the model is not a model point, however it
    got onto the frame.
    """
    donor = _priced_policies()
    out = donor.collect()
    out.insert_column(1, pl.Series("simulated_deaths", [1, 0, 1]))
    returned = ActuarialFrame(out, continue_from=donor)

    node = _node(_artifact(returned), "simulated_deaths@1")
    assert (node["kind"], node["provenance"]) == ("input", "continuation")


def test_a_column_hstacked_in_place_arrives_as_data_from_outside() -> None:
    """``hstack(in_place=True)`` is the same mutation by another name."""
    donor = _priced_policies()
    out = donor.collect()
    out.hstack([pl.Series("rider_premium", [1.0, 2.0, 3.0])], in_place=True)
    returned = ActuarialFrame(out, continue_from=donor)

    node = _node(_artifact(returned), "rider_premium@1")
    assert (node["kind"], node["provenance"]) == ("input", "continuation")


# --- what the door refuses --------------------------------------------------


def test_continuing_from_something_that_is_not_a_frame_is_refused() -> None:
    values = _priced_policies().collect()
    with pytest.raises(TypeError, match="ActuarialFrame"):
        ActuarialFrame(values, continue_from=values)  # type: ignore[arg-type]


def test_continuing_from_a_frame_that_never_collected_is_refused_by_name() -> None:
    """With no values on the donor's side there is nothing to check against."""
    with pytest.raises(ValueError, match="has not collected"):
        ActuarialFrame(_priced_policies().collect(), continue_from=_priced_policies())


def test_a_donor_written_to_since_its_collect_is_refused_by_name() -> None:
    """The values in hand are no longer the ones the donor's log accounts for.

    A frame that carried on calculating after handing its values out has a
    log that produces different numbers from the ones coming back. Verifying
    against the old values would let a column inherit a formula that never
    made it -- so the frame drops them the moment its plan moves, and the
    door says so rather than guessing.
    """
    donor = _priced_policies()
    outside = donor.collect()
    donor.death_claims = donor.sum_assured * 0.5
    with pytest.raises(ValueError, match="has not collected"):
        ActuarialFrame(outside, continue_from=donor)


def test_continuing_with_nothing_to_come_back_with_is_refused_by_name() -> None:
    donor = _priced_policies()
    donor.collect()
    with pytest.raises(ValueError, match="continue_from"):
        ActuarialFrame(continue_from=donor)


def test_an_unexecuted_plan_has_no_values_to_check_and_is_refused() -> None:
    """Verification is over values; a plan that has not run has none."""
    donor = _priced_policies()
    values = donor.collect()
    with pytest.raises(TypeError, match="collect"):
        ActuarialFrame(values.lazy(), continue_from=donor)


def test_a_frame_sharing_no_column_with_the_donor_is_refused_by_name() -> None:
    """Coming back is not the same as arriving, and the refusal says so."""
    donor = _priced_policies()
    donor.collect()
    stranger = pl.DataFrame({"scenario_id": ["BASE"], "shock": [0.25]})
    with pytest.raises(ValueError, match="scenario_id"):
        ActuarialFrame(stranger, continue_from=donor)


# --- the boundary, through a real export ------------------------------------


def test_a_continued_model_exports_the_boundary_it_crossed() -> None:
    """End to end: the envelope names the freeze, and the arrivals point at it.

    A model that leaves the frame for a generator and comes back is the
    shape the ``boundaries`` section was defined for. This is that shape
    exported whole -- the section populated, the freeze located in the
    model's own source, and every column of the run placed on one side of
    it or the other.
    """
    donor = _priced_policies()
    outside = donor.collect()
    rng = np.random.default_rng(20_260_903)
    outside = outside.with_columns(
        pl.Series("simulated_deaths", rng.binomial(1, outside["q_mort"].to_numpy()))
    )
    returned = ActuarialFrame(outside, continue_from=donor)
    re_entry = currentframe().f_lineno - 1  # type: ignore[union-attr]
    returned.simulated_claims = returned.sum_assured * returned.simulated_deaths

    artifact = _artifact(returned)

    (boundary,) = artifact["boundaries"]
    assert boundary["ordinal"] == 0
    assert boundary["source_location"].endswith(f":{re_entry}")

    frozen_by_it = {
        node["id"] for node in artifact["nodes"] if node["materialized_at"] == 0
    }
    assert frozen_by_it == {"sum_assured", "q_mort", "death_claims@1"}

    arrival = _node(artifact, "simulated_deaths@1")
    assert (arrival["kind"], arrival["provenance"]) == ("input", "continuation")
    assert arrival["materialized_at"] is None
    assert artifact["holes"] == []
