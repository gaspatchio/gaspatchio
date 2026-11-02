# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The producer's own side of a comparison, bound to node ids rather than names.

A comparison is between two engines' answers for the same node, and a frame
hands back columns under the model's names. Those are not the same thing the
moment a model writes a column twice: one name, two definitions, and only
one of them survives in the schema. This adapter is where the frame's own
retention machinery is read out under node ids, so both sides of a
comparison are speaking about nodes.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.reference import _reference_from_collection, polars_reference
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.graph_models import STATE_NAMESPACE
from gaspatchio.rollforward import compile_rollforward

PERIODS = 12


@pytest.mark.parametrize("profiled", [False, True])
def test_completed_reference_uses_its_own_values_without_recollecting(
    monkeypatch: pytest.MonkeyPatch,
    *,
    profiled: bool,
) -> None:
    from gaspatchio.cli import _every_node_result
    from gaspatchio.runner import ModelRunResult

    af = ActuarialFrame({"policy_id": [9, 2], "amount": [100.0, 200.0]})
    af.result = af.amount + 1
    af.result = af.result * 2
    values = af.profile()[0] if profiled else af.collect()
    # Mutating the caller's container cannot rewrite the completed account.
    values.replace_column(2, pl.Series("result", [999.0, 999.0]))

    def no_recollect(*_args: object, **_kwargs: object) -> pl.DataFrame:
        pytest.fail("The completed run was collected again")

    monkeypatch.setattr(ActuarialFrame, "collect", no_recollect)
    columns = _every_node_result(ModelRunResult(frame=af, result=values), None)
    assert columns["policy_id"].to_list() == [9, 2]
    assert columns["result@1"].to_list() == [101.0, 201.0]
    assert columns["result@2"].to_list() == [202.0, 402.0]
    _, manifest = _reference_from_collection(
        af, every_node=True, row_identity="policy_id"
    )
    assert manifest.producer == "polars"
    assert manifest.row_identity == ("policy_id",)


def test_completed_reference_refuses_an_uncollected_or_changed_plan() -> None:
    af = ActuarialFrame({"amount": [1]})
    with pytest.raises(ValueError, match="no completed Polars collection"):
        _reference_from_collection(af)
    af.collect()
    af.reserve = af.amount * 2
    with pytest.raises(ValueError, match="no completed Polars collection"):
        _reference_from_collection(af)


def _fund_pattern() -> ActuarialFrame:
    """Return the separate-account fund: grow with the return, take the charge."""
    frame = ActuarialFrame(
        {
            "policy_id": [1],
            "av_init": [100_000.0],
            "fund_return": [[0.01] * PERIODS],
            "me_charge": [[0.001] * PERIODS],
        }
    )
    frame = frame.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=PERIODS,
        frequency="monthly",
    )
    builder = frame.projection.rollforward(states={"fund_value": frame["av_init"]})
    (
        builder["fund_value"]
        .grow(frame["fund_return"], label="fund_return")
        .charge(frame["me_charge"], label="me_charge")
        .floor(value=0.0)
    )
    frame.account_value = compile_rollforward(builder).expr_for("fund_value")
    return frame


def _document(af: ActuarialFrame) -> dict[str, Any]:
    return json.loads(GraphExporter(af).export(profile="executable"))


def test_two_definitions_of_one_name_are_two_reference_columns() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    af.result = af.result * 2

    frame, manifest = polars_reference(af, every_node=True)

    assert set(manifest.columns) == {"policy_id", "amount", "result@1", "result@2"}
    assert frame["result@1"].to_list() == [101.0, 201.0]
    assert frame["result@2"].to_list() == [202.0, 402.0]
    assert manifest.scope == "every-node"
    assert manifest.producer == "polars"


def test_final_schema_scope_carries_the_final_schema_only() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    af.result = af.result * 2

    frame, manifest = polars_reference(af)

    assert set(manifest.columns) == {"policy_id", "amount", "result@2"}
    assert set(frame.columns) == {"policy_id", "amount", "result@2"}
    assert manifest.scope == "final-schema"


def test_every_reference_column_states_the_type_the_record_declares() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount * 2

    _, manifest = polars_reference(af, every_node=True)

    assert manifest.dtypes["policy_id"] == "i64"
    assert manifest.dtypes["amount"] == "f64"
    assert manifest.dtypes["result@1"] == "f64"


def test_a_compiled_state_balance_is_a_reference_column_and_the_structural_node_is_not() -> (  # noqa: E501 -- the name is the claim
    None
):
    af = _fund_pattern()
    document = _document(af)
    structural = {
        node["id"] for node in document["nodes"] if node["kind"] == "rollforward"
    }

    frame, manifest = polars_reference(af, every_node=True)

    assert structural, "the pattern compiled no rollforward"
    assert f"{STATE_NAMESPACE}fund_value@eop" in manifest.columns
    assert not structural & set(manifest.columns)
    balance = frame[manifest.columns[f"{STATE_NAMESPACE}fund_value@eop"]].to_list()[0]
    assert len(balance) == PERIODS


def test_the_manifest_binds_to_the_artifact_the_same_frame_exports() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1

    _, manifest = polars_reference(af, every_node=True)

    assert manifest.graph_fingerprint == _document(af)["graph_fingerprint"]


def test_the_book_is_digested_over_the_input_columns_the_artifact_names() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    other = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [1.0, 2.0]}))
    other.result = other.amount + 1

    _, one = polars_reference(af, every_node=True)
    _, two = polars_reference(other, every_node=True)

    assert one.inputs_digest.startswith("sha256:")
    assert one.inputs_digest != two.inputs_digest


def test_an_identity_column_is_named_rather_than_guessed() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1

    _, silent = polars_reference(af, every_node=True)
    _, told = polars_reference(af, every_node=True, row_identity="policy_id")

    assert silent.row_identity is None
    assert told.row_identity == ("policy_id",)
