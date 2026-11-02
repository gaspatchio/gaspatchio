# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A rate-scenario label reaches its own curve however parquet stored it.

Two shipped models decide which discount curve a policy is on by reading the
dtype of ``scenario_id``: labels name rate scenarios, integers index
simulations. The reading is right and the criterion has to be wide enough for
it, because a low-cardinality label is exactly the column a writer
dictionary-encodes -- ``pl.read_parquet`` hands back ``Categorical``, and an
``Enum`` is what a model point declares when the scenario names are fixed.

Neither of those is ``String``, and neither of them is an integer either. A
criterion that tests for ``String`` alone puts a policy labelled ``"UP"`` on
the BASE curve and says nothing at all about having done so -- a wrong number
with no refusal in front of it, which is the failure *Sharp knives, no magic*
names by hand.

So what is asserted is the discounting itself, on the shipped models, on
their own model points: the same label discounts the same way in all three
encodings, and the label is one that really does move the answer.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.tutorials import get_tutorials_dir

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

# The two shipped models that read the dtype, and the column each one's
# reading lands on: level 4 looks a rate up per scenario, level 5 reads a
# Curve per scenario. Different mechanisms, one criterion.
_LIFELIB = "level-4-lifelib"
_SCENARIOS = "level-5-scenarios"
_DISCOUNTING = {_LIFELIB: "disc_rate", _SCENARIOS: "disc_factors"}

# The three ways a model point can carry the same label. ``Enum`` is given
# the scenario names the models themselves name.
_ENCODINGS: dict[str, pl.DataType | type[pl.DataType]] = {
    "string": pl.String,
    "categorical": pl.Categorical,
    "enum": pl.Enum(["BASE", "UP", "DOWN"]),
}

# Two model points are a projection; eight are the same projection eight
# times. The models run once per (encoding, label) pair and are memoised,
# because each run is a full monthly projection.
_POLICIES = 2

_runs: dict[tuple[str, str, str], tuple[list[float] | None, str]] = {}


def _path_of(level: str) -> Path:
    return get_tutorials_dir() / level / "base" / "model.py"


def _module_of(level: str) -> ModuleType:
    """Import one shipped model from its own file, under its own name."""
    path = _path_of(level)
    spec = importlib.util.spec_from_file_location(
        "label_encoding_" + level.replace("-", "_"), path
    )
    if spec is None or spec.loader is None:
        pytest.skip(f"The shipped model at {path} is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(level: str, encoding: str, label: str) -> tuple[list[float] | None, str]:
    """Return what one run came to: the first policy's discounting, or a refusal.

    Both are answers. What a model may not do is come back with the numbers
    of a scenario nobody asked for, so a run that refuses is handed back in
    its own words rather than swallowed.
    """
    key = (level, encoding, label)
    if key not in _runs:
        points = _path_of(level).parent / "model_points.parquet"
        if not points.is_file():
            pytest.skip(f"The model points for {level} are not available")
        frame = (
            pl.read_parquet(points)
            .head(_POLICIES)
            .with_columns(pl.lit(label).cast(_ENCODINGS[encoding]).alias("scenario_id"))
        )
        try:
            result = _module_of(level).main(ActuarialFrame(frame)).collect()
        except pl.exceptions.PolarsError as refusal:
            _runs[key] = (None, str(refusal))
        else:
            answer: Any = result[_DISCOUNTING[level]][0]
            _runs[key] = ([float(value) for value in answer], "")
    return _runs[key]


def _discounting(level: str, encoding: str, label: str) -> list[float]:
    """Return one run's discounting, failing the test if the run refused."""
    numbers, refusal = _run(level, encoding, label)
    assert numbers is not None, refusal
    return numbers


@pytest.fixture(scope="module")
def tutorials_present() -> None:
    for level in (_LIFELIB, _SCENARIOS):
        if not _path_of(level).is_file():
            pytest.skip(f"The shipped model for {level} is not available")


@pytest.mark.usefixtures("tutorials_present")
@pytest.mark.parametrize("level", [_LIFELIB, _SCENARIOS])
def test_the_shocked_label_really_does_move_the_discounting(level: str) -> None:
    """Without this, the comparison below could hold by both halves being wrong.

    ``"UP"`` and ``"BASE"`` have to discount differently before "the encoded
    label discounts like the plain one" says anything at all. This is that
    check, taken in the encoding the models were written against.
    """
    assert _discounting(level, "string", "UP") != _discounting(level, "string", "BASE")


@pytest.mark.usefixtures("tutorials_present")
@pytest.mark.parametrize("level", [_LIFELIB, _SCENARIOS])
@pytest.mark.parametrize("encoding", ["categorical", "enum"])
def test_a_dictionary_encoded_label_is_never_quietly_discounted_as_base(
    level: str,
    encoding: str,
) -> None:
    """The encoded label reaches its own curve, in every encoding.

    Not honest: BASE numbers, returned without a word, for a policy the model
    point says is on ``"UP"``. That is what is pinned here, and it is pinned
    the strong way round -- by the number the run comes back with, not by a
    disjunction that a refusal would also satisfy. A refusal is a fair answer
    to a label a table does not hold; it is not a fair answer to a label the
    table holds and the encoding hid, so no encoding of ``"UP"`` may refuse
    and none may return BASE's discounting.

    Level 5 reads a ``Curve`` per label and level 4 looks the rate up in a
    table: different mechanisms, and the ``Enum`` case distinguishes itself
    from the ``Categorical`` one because an ``Enum`` numbers its categories
    in the order they were declared. ``["BASE", "UP", "DOWN"]`` puts ``"UP"``
    at position 1 where the table, built from sorted labels, holds it at 2 --
    so a lookup that read the position rather than the name would land on
    ``"DOWN"``'s rate and this test would see it.
    """
    numbers, refusal = _run(level, encoding, "UP")
    assert numbers is not None, refusal
    assert numbers == _discounting(level, "string", "UP")
    assert numbers != _discounting(level, "string", "BASE")
