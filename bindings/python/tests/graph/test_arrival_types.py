# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the leaf for a vendor field a model renamed says about its type.

A model that renames its columns on the way in -- ``Sum Assured`` to
``sum_assured`` -- keeps the vendor name in the graph on purpose: the input
leaf is named for the field of the source file, not for what the model calls
it afterwards. The type was the half of that leaf nobody could answer. The
collected schema holds the new name, so the lookup missed and the leaf went
out ``unknown`` -- a producer writing that for a type it had met, which
section 10 of the format says is never allowed.

The frame keeps the schema its data arrived with beside the names it already
kept, so the leaf states the type the field came in under. Its
``value_sample`` stays null, and the two absences are not the same absence:
the type is remembered, and the values really are gone from the collected
frame.

Two shapes reach that state and both are ordinary. ``rename()`` moves the
name; assigning the column to a new name and dropping the old one moves the
values and leaves the name behind. A model that renames nothing is the
control, and nothing here may move it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

# --- the three shapes -------------------------------------------------------


def _model_points() -> pl.DataFrame:
    """Return two policies under the field names a vendor extract uses."""
    return pl.DataFrame(
        {
            "policy_id": ["P001", "P002"],
            "Sum Assured": [100_000.0, 250_000.0],
        }
    )


def _a_model_that_renames_its_vendor_field() -> ActuarialFrame:
    """Return the model that moves the name and calculates under the new one."""
    af = ActuarialFrame(_model_points())
    af = af.rename({"Sum Assured": "sum_assured"})
    af.death_claims = af.sum_assured * 0.001_23
    return af


def _a_model_that_aliases_then_drops_its_vendor_field() -> ActuarialFrame:
    """Return the model that copies the column to a new name and drops the old."""
    af = ActuarialFrame(_model_points())
    af.sum_assured = af["Sum Assured"]
    af = af.drop("Sum Assured")
    af.death_claims = af.sum_assured * 0.001_23
    return af


def _a_model_that_keeps_its_vendor_field() -> ActuarialFrame:
    """Return the control: the vendor name is what the model calculates from."""
    af = ActuarialFrame(_model_points())
    af.death_claims = af["Sum Assured"] * 0.001_23
    return af


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, with its own values read into it."""
    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(result_df=frame.collect())
    )
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _vendor_leaf(build: Callable[[], ActuarialFrame]) -> dict[str, Any]:
    """Return the input leaf naming the vendor field, for one of the shapes."""
    return _node(_artifact(build()), "Sum Assured")


# --- what the leaf says -----------------------------------------------------


def test_a_renamed_arrivals_leaf_states_the_type_it_arrived_under() -> None:
    """The name moved; the type the field came in under did not."""
    leaf = _vendor_leaf(_a_model_that_renames_its_vendor_field)

    assert leaf["kind"] == "input"
    assert leaf["dtype"] == "f64"


def test_an_aliased_then_dropped_arrivals_leaf_states_its_type_too() -> None:
    """The other way to leave a vendor name behind, answered the same way."""
    leaf = _vendor_leaf(_a_model_that_aliases_then_drops_its_vendor_field)

    assert leaf["kind"] == "input"
    assert leaf["dtype"] == "f64"


def test_the_shape_of_a_renamed_arrival_is_stated_beside_its_type() -> None:
    """``shape`` carries ``unknown`` under section 10's same rule, so it moves too.

    A leaf reading ``dtype: f64`` and ``shape: unknown`` would say in one
    field that the producer met the type and in the next that it did not.
    """
    for build in (
        _a_model_that_renames_its_vendor_field,
        _a_model_that_aliases_then_drops_its_vendor_field,
    ):
        assert _vendor_leaf(build)["shape"] == "scalar"


def test_a_renamed_arrival_carries_no_sample_because_the_values_are_gone() -> None:
    """The type is remembered; the values are not, and the record says both.

    Samples are read out of the collected frame, and neither shape's
    collected frame holds a column under the vendor name any more. The null
    is the true answer rather than a second statement that nothing is known
    about the column.
    """
    for build in (
        _a_model_that_renames_its_vendor_field,
        _a_model_that_aliases_then_drops_its_vendor_field,
    ):
        leaf = _vendor_leaf(build)
        assert leaf["dtype"] == "f64"
        assert leaf["value_sample"] is None


def test_a_kept_arrival_still_carries_its_type_and_its_sample() -> None:
    """The control, which none of this may move."""
    leaf = _vendor_leaf(_a_model_that_keeps_its_vendor_field)

    assert (leaf["dtype"], leaf["shape"]) == ("f64", "scalar")
    assert leaf["value_sample"] == 100_000.0


# --- and what that does to the leaf's identity ------------------------------


def test_a_renamed_arrival_is_now_the_same_leaf_as_a_kept_one() -> None:
    """A leaf's bytes are its tag, its name and its type -- and nothing else.

    Which is why stating the type moves these two documents' fingerprints:
    the leaf used to be hashed over ``unknown``. The movement is expressible
    as this equality rather than as a digest literal -- the same vendor
    field, at the same type, under the same tag is the same leaf whatever
    the model went on to call it -- and the control's leaf is what both of
    them now agree with.
    """
    kept = _vendor_leaf(_a_model_that_keeps_its_vendor_field)

    for build in (
        _a_model_that_renames_its_vendor_field,
        _a_model_that_aliases_then_drops_its_vendor_field,
    ):
        assert _vendor_leaf(build)["local_fingerprint"] == kept["local_fingerprint"]


def test_two_arrivals_of_one_name_at_two_types_are_two_leaves() -> None:
    """The type is in the bytes, so a field that changed type is visible as one.

    The point of the equality above is that it is an equality *of types*,
    not a rename being ignored. A vendor field that arrived as text last
    quarter and as a number this one is a different leaf, renamed or not.
    """

    def renamed_from(values: pl.Series) -> str:
        af = ActuarialFrame(pl.DataFrame({"policy_id": ["P001"]}).with_columns(values))
        af = af.rename({"Sum Assured": "sum_assured"})
        af.carried = af.sum_assured
        return _node(_artifact(af), "Sum Assured")["local_fingerprint"]

    as_a_number = renamed_from(pl.Series("Sum Assured", [100_000.0]))
    as_text = renamed_from(pl.Series("Sum Assured", ["100000"]))

    assert as_a_number != as_text


# --- the type this vocabulary has no name for -------------------------------


def test_an_arrival_type_with_no_name_here_leaves_the_leaf_untyped() -> None:
    """A dropped column the vocabulary cannot name stays ``unknown``, not refused.

    ``to_text()`` exists so that a vendor ``Categorical`` -- which section 10
    has no name for -- can be carried into the vocabulary and the original
    let go of. Refusing the export on the type the dropped column arrived
    under would refuse a model that had done exactly that, over a column it
    no longer holds. Section 10's permission covers it: a column defined and
    then dropped, where the value is history rather than the answer.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P001", "P002"]}).with_columns(
            pl.Series("Product Code", ["TERM", "WOL"], dtype=pl.Categorical)
        )
    )
    af.product_code = af["Product Code"].to_text()
    af = af.drop("Product Code")

    leaf = _node(_artifact(af), "Product Code")

    assert leaf["kind"] == "input"
    assert leaf["dtype"] == "unknown"


def test_a_type_with_no_name_that_is_still_on_the_frame_is_refused_as_before() -> None:
    """The permission above is for history only; a live column is unchanged.

    The collected schema answers for a column the frame still holds, so the
    arrival record is never consulted for one and the refusal is the one it
    always was.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P001", "P002"]}).with_columns(
            pl.Series("Product Code", ["TERM", "WOL"], dtype=pl.Categorical)
        )
    )
    af.policy_count = af["policy_id"].polars_native().len()

    with pytest.raises(UnmappedDtypeError, match="Product Code"):
        _artifact(af)


# --- what the frame remembers, and for how long -----------------------------


def _arrival_schema(af: ActuarialFrame) -> dict[str, pl.DataType]:
    """Return the schema ``af``'s data arrived under."""
    return af._arrival_schema  # noqa: SLF001 -- the frame's own record is the subject


def test_the_arrival_types_are_the_schema_the_data_came_in_under() -> None:
    """Every arriving column, at the type it arrived at, from the first moment."""
    af = ActuarialFrame(_model_points())

    assert _arrival_schema(af) == {
        "policy_id": pl.String(),
        "Sum Assured": pl.Float64(),
    }


def test_a_rename_does_not_move_the_arrival_types() -> None:
    """A rename moves the name the frame calls a column by, and nothing else."""
    af = ActuarialFrame(_model_points())
    af = af.rename({"Sum Assured": "sum_assured"})

    assert _arrival_schema(af)["Sum Assured"] == pl.Float64()
    assert "sum_assured" not in _arrival_schema(af)


def test_a_drop_does_not_shrink_the_arrival_types() -> None:
    """The column left the schema; it did not stop having had a type."""
    af = ActuarialFrame(_model_points())
    af.sum_assured = af["Sum Assured"]
    af = af.drop("Sum Assured")

    assert _arrival_schema(af)["Sum Assured"] == pl.Float64()


def test_a_calculated_column_is_not_an_arrival() -> None:
    """``with_columns`` writes calculations, and a calculation never arrived."""
    af = ActuarialFrame(_model_points())
    af = af.with_columns((pl.col("Sum Assured") * 0.001_23).alias("death_claims"))

    assert "death_claims" not in _arrival_schema(af)
    assert _arrival_schema(af)["Sum Assured"] == pl.Float64()


def test_a_continued_frame_carries_the_donors_arrival_types() -> None:
    """The vendor field the donor renamed is still typed on the far side.

    A frame rebuilt from values that went outside carries the donor's log,
    so it carries the donor's inputs -- and the type of a field the donor
    renamed away is not in the returning DataFrame's schema to be recovered
    from. Without the donor's record the leaf would go back to ``unknown``
    the moment a scenario axis or an escape hatch widened the model.
    """
    donor = _a_model_that_renames_its_vendor_field()
    returned = ActuarialFrame(donor.collect(), continue_from=donor)

    assert _arrival_schema(returned)["Sum Assured"] == pl.Float64()
    assert _node(_artifact(returned), "Sum Assured")["dtype"] == "f64"


def test_a_scenario_axis_keeps_the_donors_vendor_field_typed() -> None:
    """Widening a model does not cost the donor's record of what arrived.

    The cross-join's own ``scenario_id`` is not in the arriving set and
    should not be: the model-points file has no such column, so the axis is
    recorded as the thing it is -- a column of values handed over at a
    line -- rather than filed under the data the model was run over. What
    the arriving set still has to carry across the widening is the vendor
    field the donor renamed, whose type only the donor's record knows.
    """
    widened = with_scenarios(_a_model_that_renames_its_vendor_field(), ["BASE", "UP"])

    assert "scenario_id" not in _arrival_schema(widened)
    assert _arrival_schema(widened)["Sum Assured"] == pl.Float64()
    assert _node(_artifact(widened), "Sum Assured")["dtype"] == "f64"
