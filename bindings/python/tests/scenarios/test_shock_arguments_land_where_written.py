# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A shock argument written in the wrong slot is refused where the shock is built.

``PipelineShock(MultiplicativeShock(1.4), ClipShock(1.0))`` -- a spelling the
extending skill once printed -- built a pipeline whose ``table`` was a
``ClipShock``, and the plan failed only when it ran, with "'ClipShock' object
is not iterable". A shock's arguments are read in order, so a second shock or a
filter written without its keyword lands in the next slot. Every shock class
now refuses, at construction, a ``table`` or ``column`` that is not a name, a
nested shock that is not a shock, pipeline steps that are not a sequence of
shocks and a filter that is not a mapping, naming the keyword spelling.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio.assumptions import Table
from gaspatchio.scenarios import shocks as shock_module
from gaspatchio.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    Shock,
    TimeConditionalShock,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_MULT = MultiplicativeShock(1.4)
_CLIP = ClipShock(max_value=1.0)

# Each shock class, built with a target that is not a name in the slot where a
# positional spelling puts one.
_TARGET_IN_THE_WRONG_SLOT: dict[str, Callable[[], Shock]] = {
    "MultiplicativeShock": lambda: MultiplicativeShock(1.2, _CLIP),  # type: ignore[arg-type]
    "AdditiveShock": lambda: AdditiveShock(0.01, None, 0.02),  # type: ignore[arg-type]
    "OverrideShock": lambda: OverrideShock(0.0, 5),  # type: ignore[arg-type]
    "ClipShock": lambda: ClipShock(0.0, 1.0, _MULT),  # type: ignore[arg-type]
    "PipelineShock": lambda: PipelineShock((_MULT,), _CLIP),  # type: ignore[arg-type]
    "FilteredShock": lambda: FilteredShock(_MULT, {"age": 60}, _CLIP),  # type: ignore[arg-type]
    "TimeConditionalShock": lambda: TimeConditionalShock(_MULT, {"t": 0}, 1),  # type: ignore[arg-type]
    "MaxShock": lambda: MaxShock(_MULT, _CLIP, _CLIP),  # type: ignore[arg-type]
    "MinShock": lambda: MinShock(_MULT, _CLIP, None, 0.5),  # type: ignore[arg-type]
}


def _shock_classes() -> list[str]:
    """Return every concrete shock class the module exports."""
    return sorted(
        name
        for name in shock_module.__all__
        if isinstance(getattr(shock_module, name), type)
        and issubclass(getattr(shock_module, name), Shock)
        and getattr(shock_module, name) is not Shock
    )


def _spelled_out(kind: str) -> str:
    """Return the keyword spelling the module quotes for one shock class."""
    spellings: dict[str, str] = getattr(shock_module, "_SPELLED_OUT", {})
    return spellings.get(kind, f"<no spelling for {kind}>")


def test_every_shock_class_is_covered() -> None:
    """A new shock class has to say how a misplaced target is refused."""
    assert sorted(_TARGET_IN_THE_WRONG_SLOT) == _shock_classes()


def test_the_defect_as_found_is_refused_at_construction() -> None:
    """The positional pipeline no longer builds, and says how to write it."""
    with pytest.raises(TypeError) as refused:
        PipelineShock(MultiplicativeShock(1.4), ClipShock(1.0))  # type: ignore[arg-type]
    said = str(refused.value)
    assert said.startswith("PipelineShock: table= holds a ClipShock")
    assert "the name of the assumption table the shock moves" in said
    assert (
        "PipelineShock(shocks=(MultiplicativeShock(1.4), "
        'ClipShock(max_value=1.0)), column="lapse_rate")'
    ) in said


@pytest.mark.parametrize("kind", sorted(_TARGET_IN_THE_WRONG_SLOT))
def test_a_target_that_is_not_a_name_is_refused(kind: str) -> None:
    """Every class refuses it, naming the slot and its own keyword spelling."""
    with pytest.raises(TypeError) as refused:
        _TARGET_IN_THE_WRONG_SLOT[kind]()
    said = str(refused.value)
    assert re.match(rf"{kind}: (table|column)= holds ", said), said
    assert _spelled_out(kind) in said


@pytest.mark.parametrize("kind", sorted(_TARGET_IN_THE_WRONG_SLOT))
def test_every_spelling_a_refusal_quotes_builds(kind: str) -> None:
    """The keyword spelling a refusal hands over is one that constructs."""
    namespace: dict[str, Any] = {
        name: getattr(shock_module, name) for name in shock_module.__all__
    }
    built = eval(_spelled_out(kind), namespace)  # noqa: S307 -- the module's own text
    assert type(built).__name__ == kind


@pytest.mark.parametrize(
    ("build", "slot"),
    [
        (lambda: FilteredShock("lapse", {"age": 60}), "shock"),  # type: ignore[arg-type]
        (lambda: TimeConditionalShock(1.1, {"t": 0}), "shock"),  # type: ignore[arg-type]
        (lambda: MaxShock(_MULT, 0.5), "shock_b"),  # type: ignore[arg-type]
        (lambda: MinShock({"factor": 1.5}, _MULT), "shock_a"),  # type: ignore[arg-type]
    ],
    ids=["filtered", "time-conditional", "max", "min"],
)
def test_a_nested_shock_that_is_not_a_shock_is_refused(
    build: Callable[[], Shock], slot: str
) -> None:
    with pytest.raises(TypeError, match=rf"{slot}= holds .*, where a shock belongs"):
        build()


def test_a_pipeline_of_one_bare_shock_is_refused() -> None:
    """``shocks=`` takes the steps as a sequence, not one shock."""
    with pytest.raises(
        TypeError, match="shocks= holds a MultiplicativeShock, where a sequence"
    ):
        PipelineShock(_MULT, table="lapse")  # type: ignore[arg-type]


def test_a_pipeline_step_that_is_not_a_shock_is_refused() -> None:
    with pytest.raises(TypeError, match=r"shocks= holds 1\.0, a float, where a shock"):
        PipelineShock((_MULT, 1.0), table="lapse")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda: FilteredShock(_MULT, "lapse"),  # type: ignore[arg-type]
        lambda: TimeConditionalShock(_MULT, 0),  # type: ignore[arg-type]
    ],
    ids=["where", "when"],
)
def test_a_condition_that_is_not_a_mapping_is_refused(
    build: Callable[[], Shock],
) -> None:
    with pytest.raises(TypeError, match=r"(where|when)= holds .*, where a condition"):
        build()


def test_a_table_passed_for_its_name_is_told_the_name() -> None:
    """A ``Table`` in ``table=`` is refused, and the refusal names the Table's name."""
    mortality = Table(
        name="mortality",
        source=pl.DataFrame({"age": [30], "q": [0.01]}),
        dimensions={"age": "age"},
        value="q",
    )
    with pytest.raises(TypeError, match=r"pass its name: table='mortality'"):
        MultiplicativeShock(1.2, table=mortality)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda: PipelineShock(shocks=(_MULT, _CLIP), table="lapse"),
        lambda: PipelineShock(shocks=[_MULT, _CLIP], column="lapse_rate"),
        lambda: ClipShock(1.0),
        lambda: ClipShock(0.0, 1.0, "lapse"),
        lambda: MultiplicativeShock(1.2, "mortality"),
        lambda: AdditiveShock(0.01, None, "valuation_rate"),
        lambda: FilteredShock(_MULT, {"age": {"gte": 60}}, "mortality"),
        lambda: TimeConditionalShock(_MULT, {"t": {"eq": 0}}),
        lambda: MaxShock(_MULT, _CLIP),
        lambda: MinShock(_MULT, _CLIP, table="lapse"),
    ],
)
def test_every_well_placed_spelling_still_builds(build: Callable[[], Shock]) -> None:
    """Positional arguments in the slots they belong to construct as before."""
    assert isinstance(build(), Shock)
