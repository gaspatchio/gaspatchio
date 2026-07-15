# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Debug (tracing) mode must produce the same numbers as optimize mode.

The tracing setter both records each operation to the computation graph AND
applies it to the LazyFrame; collect()/profile() then replayed the graph on
top of the already-applied frame. For fresh columns the replay recomputed the
same value; for self-referential assignments (af["x"] = af["x"] + 1) it
applied the operation twice, so the CLI's default debug mode produced
different numbers from production. The graph is record-only metadata now.
"""

import polars as pl

from gaspatchio_core import ActuarialFrame


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"x": [10.0, 20.0, 30.0]}))


def test_self_referential_bracket_assignment_applies_once_under_tracing():
    af = _frame()
    af._tracing = True
    af["x"] = af["x"] + 1
    out = af.collect()
    assert out["x"].to_list() == [11.0, 21.0, 31.0]


def test_self_referential_attribute_assignment_applies_once_under_tracing():
    af = _frame()
    af._tracing = True
    af.x = af.x + 1
    out = af.collect()
    assert out["x"].to_list() == [11.0, 21.0, 31.0]


def test_tracing_and_non_tracing_collect_identical_frames():
    results = {}
    for tracing in (False, True):
        af = _frame()
        af._tracing = tracing
        af["x"] = af["x"] + 1
        af["y"] = af["x"] * 2
        results[tracing] = af.collect()
    assert results[True].equals(results[False])


def test_profile_matches_collect_under_tracing():
    af = _frame()
    af._tracing = True
    af["x"] = af["x"] + 1
    collected = af.collect()

    af2 = _frame()
    af2._tracing = True
    af2["x"] = af2["x"] + 1
    profiled, _profile_info = af2.profile()

    assert profiled["x"].to_list() == collected["x"].to_list()


def test_graph_still_records_operations_under_tracing():
    # The graph is record-only, but it must still record — calc-graph
    # display and query-plan logging depend on it.
    af = _frame()
    af._tracing = True
    af["y"] = af["x"] * 2
    assert len(af._computation_graph) == 1
