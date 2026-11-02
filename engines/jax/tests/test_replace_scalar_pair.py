# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``replace(old, new)`` runs here as the one-entry mapping it is recorded as.

One value and its replacement, ``af.status.replace("IF", "INFORCE")``, was
refused by the producer; it is now read as ``replace({"IF": "INFORCE"})`` and
recorded as that mapping is, so nothing new reaches this engine: the node is
the mapping's node, and it lowers as the mapping always has.
"""

from __future__ import annotations

import json

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

_BOOK = pl.DataFrame(
    {
        "status": ["IF", "LA", "IF"],
        "periods": [["IF", "LA"], ["LA"], ["IF", "IF"]],
        "code": [1, 2, 1],
    }
)


def _model(*, as_pair: bool) -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    if as_pair:
        af.status_named = af.status.replace("IF", "INFORCE")
        af.periods_named = af.periods.replace(old="IF", new="INFORCE")
        af.code_moved = af.code.replace(1, 9)
    else:
        af.status_named = af.status.replace({"IF": "INFORCE"})
        af.periods_named = af.periods.replace({"IF": "INFORCE"})
        af.code_moved = af.code.replace({1: 9})
    return af


_WRITTEN = ("status_named", "periods_named", "code_moved")


def test_the_pair_and_its_mapping_are_one_record() -> None:
    pair = GraphExporter(_model(as_pair=True)).export(profile="executable")
    mapping = GraphExporter(_model(as_pair=False)).export(profile="executable")
    report = validate_artifact(pair, engine="jax", deep=True)
    assert report.ok, report.findings
    assert (
        json.loads(pair)["graph_fingerprint"]
        == json.loads(mapping)["graph_fingerprint"]
    )


def test_the_pair_runs_here_and_gives_polars_own_answer() -> None:
    on_polars = _model(as_pair=True).collect()
    on_jax = _model(as_pair=True).collect(engine="jax")
    for column in _WRITTEN:
        assert on_jax[column].dtype == on_polars[column].dtype, column
        assert on_jax[column].to_list() == on_polars[column].to_list(), column
    assert on_jax["status_named"].to_list() == ["INFORCE", "LA", "INFORCE"]
    assert on_jax["code_moved"].to_list() == [9, 2, 9]
