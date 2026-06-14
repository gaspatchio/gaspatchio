# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test @scenario_aggregator decorator + register_aggregator + the registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from gaspatchio_core.scenarios._aggregators import (
    _AGGREGATOR_REGISTRY,
    Sum,
    register_aggregator,
    scenario_aggregator,
)
from gaspatchio_core.scenarios._metric import Aggregator

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:
    """Save and restore _AGGREGATOR_REGISTRY so tests don't pollute each other."""
    saved = dict(_AGGREGATOR_REGISTRY)
    yield
    _AGGREGATOR_REGISTRY.clear()
    _AGGREGATOR_REGISTRY.update(saved)


def test_builtin_aggregators_registered() -> None:
    """All built-ins are registered at module import."""
    expected = {
        "Sum",
        "Count",
        "Min",
        "Max",
        "Mean",
        "Variance",
        "Std",
        "ArgMin",
        "ArgMax",
        "Quantile",
        "Median",
        "CTE",
        "QuantileRank",
    }
    assert expected <= set(_AGGREGATOR_REGISTRY)


def test_sum_resolves_via_registry() -> None:
    """_AGGREGATOR_REGISTRY['Sum'] is the Sum class."""
    assert _AGGREGATOR_REGISTRY["Sum"] is Sum


def test_register_duplicate_raises() -> None:
    """Registering the same name twice raises ValueError."""
    with pytest.raises(ValueError, match="already registered"):
        register_aggregator("Sum", Sum)


def test_register_kind_mismatch_raises() -> None:
    """If canonical_form()['kind'] != name, registration raises."""

    @dataclass(frozen=True)
    class BadKind:
        column: str = "x"

        def within_expr(self) -> Any:  # noqa: ANN401
            ...

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: Any) -> int:  # noqa: ANN401, ARG002
            return s

        def merge_accumulators(self, a: int, b: int) -> int:  # noqa: ARG002
            return a

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "ActuallyDifferent"}

    with pytest.raises(ValueError, match="canonical_form"):
        register_aggregator("BadKind", BadKind)


def test_scenario_aggregator_decorator_registers() -> None:
    """@scenario_aggregator('Name') adds the class to the registry."""

    @scenario_aggregator("MyAgg")
    @dataclass(frozen=True)
    class MyAgg:
        column: str = "x"

        def within_expr(self) -> Any:  # noqa: ANN401
            ...

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: Any) -> int:  # noqa: ANN401, ARG002
            return s

        def merge_accumulators(self, a: int, b: int) -> int:  # noqa: ARG002
            return a

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "MyAgg"}

    assert _AGGREGATOR_REGISTRY["MyAgg"] is MyAgg


def test_registered_class_satisfies_protocol() -> None:
    """Every registered class implements the Aggregator Protocol (duck-typed)."""
    for name, cls in _AGGREGATOR_REGISTRY.items():
        try:
            inst = cls(column="x")  # type: ignore[call-arg]
        except TypeError:
            continue  # skip classes that need extra args
        assert isinstance(inst, Aggregator), (
            f"{name} does not satisfy Aggregator Protocol"
        )
