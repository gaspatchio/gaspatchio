# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Formula recognition and backend execution have independent contracts."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio._authoring import emit
from gaspatchio._semantic import calls
from gaspatchio._semantic.ir import Call, Col
from gaspatchio._semantic.vocabulary import VOCABULARY
from gaspatchio.frame.lowering import polars
from gaspatchio.frame.lowering.context import LoweringContext


def test_builtin_emission_does_not_load_or_require_polars_rules(monkeypatch) -> None:
    def unavailable() -> None:
        raise ImportError("test backend unavailable")

    monkeypatch.setattr(polars, "_RULES_LOADED", False)
    monkeypatch.setattr(polars, "_load_rules", unavailable)
    node = emit.call_node("abs", (Col("amount"),))
    assert node == Call("abs", (Col("amount"),), ())
    with pytest.raises(ImportError, match="test backend unavailable"):
        polars.lower_polars(node)
    assert not polars._RULES_LOADED
    assert not polars._RULES_LOADING


def test_vocabulary_call_kinds_match_the_existing_builtin_backend() -> None:
    polars.ensure_rules_loaded()
    declared = {op.identifier for op in VOCABULARY if op.node_kind == "call"}
    assert declared == set(polars.LOWERINGS)


@pytest.mark.parametrize(
    "name", ["add", "lt", "and", "join", "projection_set", "rollforward"]
)
def test_syntax_and_structural_records_are_not_builtin_calls(name: str) -> None:
    with pytest.raises(ValueError, match="is not a known operation"):
        emit.call_node(name, ())


def test_custom_polars_registration_and_removal_remain_live(monkeypatch) -> None:
    name = "test.custom_double"
    polars.ensure_rules_loaded()
    monkeypatch.setitem(polars.LOWERINGS, name, lambda node, ctx: pl.lit(0))
    del polars.LOWERINGS[name]

    @polars.register_lowering(name)
    def lower_double(node: Call, ctx: LoweringContext | None) -> pl.Expr:
        return polars.lower_polars(node.args[0], ctx) * 2

    node = emit.call_node(name, (3,))
    assert pl.select(polars.lower_polars(node)).item() == 6
    with pytest.raises(ValueError, match="already has a registered Polars lowering"):
        polars.register_lowering(name)(lower_double)
    del polars.LOWERINGS[name]
    with pytest.raises(ValueError, match="is not a known operation"):
        emit.call_node(name, (3,))


def test_another_engine_can_publish_calls_without_a_polars_lowering(
    monkeypatch,
) -> None:
    monkeypatch.setattr(calls, "_ENGINE_CALLS", {})
    names = {"test.other_engine"}
    calls.register_engine_calls("test", names)
    calls.register_engine_calls("test", names)
    node = emit.call_node("test.other_engine", (2,))
    with pytest.raises(polars.LoweringError, match="test.other_engine"):
        polars.lower_polars(node)
    names.clear()
    with pytest.raises(ValueError, match="is not a known operation"):
        emit.call_node("test.other_engine", (2,))
    with pytest.raises(ValueError, match="already has a call registry"):
        calls.register_engine_calls("test", {"test.replacement"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_recognized_calls_still_refuse_nonfinite_configuration(value: float) -> None:
    with pytest.raises(ValueError, match="start_at"):
        emit.call_node(
            "projection.cumulative_survival", (Col("qx"),), (("start_at", value),)
        )


def test_unknown_call_preserves_the_existing_authoring_error() -> None:
    with pytest.raises(ValueError) as raised:
        emit.call_node("test.typo", ())
    assert str(raised.value) == (
        "'test.typo' is not a known operation: it has no registered "
        "lowering, so nothing can compute it. Check the spelling "
        "against the names registered in gaspatchio/frame/lowering/rules/."
    )
