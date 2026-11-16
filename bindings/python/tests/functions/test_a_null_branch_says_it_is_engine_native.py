# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``None`` branch of ``when`` says, at the author's line, what it costs.

Section 11.1.28 of the graph-artifact spec: "The tree has no null literal in
this preview: a producer writes a null branch as an engine-native fragment".
So ``when(cond).then(x).otherwise(None)`` runs in Polars and is recorded
``engine_native``, and an engine that runs only core calculations refuses
the model. That used to happen in silence -- the author who wrote ``None``
for "blank" learned of it only when a portable run refused. The line now
warns, names the tier, and names the core spelling when blank means zero.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from gaspatchio import ActuarialFrame, GaspatchioWarning, when


def _frame() -> ActuarialFrame:
    return ActuarialFrame({"n": [1, 2, 3], "f": [10.0, 20.0, 30.0]})


def _the_one_warning(caught: pytest.WarningsRecorder) -> warnings.WarningMessage:
    (warning,) = [w for w in caught if issubclass(w.category, GaspatchioWarning)]
    return warning


def _says_what_it_costs(warning: warnings.WarningMessage, branch: str) -> None:
    message = str(warning.message)
    assert f"{branch} branch" in message
    assert "engine_native" in message
    assert f".{branch}(0.0)" in message
    assert Path(warning.filename) == Path(__file__)


def test_a_none_then_warns_at_the_authors_line() -> None:
    """``then(None)`` warns, located in this file."""
    af = _frame()
    with pytest.warns(GaspatchioWarning) as caught:
        af.a = when(af.n > 1).then(None).otherwise(af.f)
    _says_what_it_costs(_the_one_warning(caught), "then")


def test_a_none_otherwise_warns_at_the_authors_line() -> None:
    """``otherwise(None)`` warns, located in this file."""
    af = _frame()
    with pytest.warns(GaspatchioWarning) as caught:
        af.a = when(af.n > 1).then(af.f).otherwise(None)
    _says_what_it_costs(_the_one_warning(caught), "otherwise")


def test_the_line_still_runs_and_is_still_recorded_engine_native() -> None:
    """The warning changes what the author hears, not what the line does."""
    af = _frame()
    with pytest.warns(GaspatchioWarning):
        af.a = when(af.n > 1).then(af.f).otherwise(None)
    assert af.collect()["a"].to_list() == [None, 20.0, 30.0]
    assert af.graph.tiers().engine_native == ("a@1",)


def test_a_number_branch_says_nothing_and_stays_core() -> None:
    """The spelling the warning names is core and silent."""
    af = _frame()
    with warnings.catch_warnings():
        warnings.simplefilter("error", GaspatchioWarning)
        af.a = when(af.n > 1).then(af.f).otherwise(0.0)
    assert af.graph.tiers().engine_native == ()
    assert af.graph.tiers().core == ("a@1",)
