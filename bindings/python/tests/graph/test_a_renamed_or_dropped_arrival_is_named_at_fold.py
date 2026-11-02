# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An arriving column the model renamed, dropped or wrote over is typed as it arrived.

The graph names an input leaf for the field the data arrived under, typed by
the schema the data arrived with (section 10). The fold reads a book's wide
columns off the book as it arrived, by their arrival names, so a lazily handed
``UInt64`` whose values fit is ``i64`` -- and three paths around that read
went wrong:

* **Renamed on the way in**, the rename's own node was typed off the plan's
  schema, which still showed ``UInt64``, with no values under the new name:
  the lazy door refused the whole export on the width alone, where a
  DataFrame's door exported it. The frame, collected, handed the renamed
  column back ``UInt64`` from the lazy door and ``Int64`` from the other.
* **Dropped**, the leaf was ``unknown`` from the lazy door and ``i64`` from the
  other.
* **A name a later line took over** -- ``af.pid = af.x * 2`` after the
  arriving ``pid`` was renamed or dropped, or ``af.n = af.n * 1.5`` over it --
  typed the leaf with the new column's type: an ``i64`` field stated ``f64``,
  from either door.

Each is now named on the arrival type and the values read off the book; a
value past ``i64`` is refused naming it where the model holds the column, and
a dropped one keeps the ``unknown`` section 10 permits for history.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_FITS = pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.UInt64), "x": [1.0, 2.0]})
_PAST = pl.DataFrame(
    {"pid": pl.Series([7, 2**64 - 1], dtype=pl.UInt64), "x": [1.0, 2.0]}
)


def _renamed(af: ActuarialFrame) -> ActuarialFrame:
    af = af.rename({"pid": "policy"})
    af.r = af.policy + 1
    return af


def _renamed_twice(af: ActuarialFrame) -> ActuarialFrame:
    af = af.rename({"pid": "p"}).rename({"p": "policy"})
    af.r = af.x * 2
    return af


def _dropped(af: ActuarialFrame) -> ActuarialFrame:
    af = af.drop("pid")
    af.r = af.x * 2
    return af


def _renamed_then_reused(af: ActuarialFrame) -> ActuarialFrame:
    af = af.rename({"pid": "policy"})
    af.pid = af.x * 2
    return af


def _dropped_then_reused(af: ActuarialFrame) -> ActuarialFrame:
    af = af.drop("pid")
    af.pid = af.x * 2
    return af


_MODELS: dict[str, Callable[[ActuarialFrame], ActuarialFrame]] = {
    "renamed": _renamed,
    "renamed twice": _renamed_twice,
    "dropped": _dropped,
    "renamed, then the name reused": _renamed_then_reused,
    "dropped, then the name reused": _dropped_then_reused,
}


def _nodes(af: ActuarialFrame) -> dict[str, str]:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    return {node["id"]: node["dtype"] for node in document["nodes"]}


@pytest.mark.parametrize("model", sorted(_MODELS))
@pytest.mark.parametrize("lazy", [False, True], ids=["dataframe", "lazyframe"])
def test_a_fitting_wide_arrival_is_an_i64_leaf(model: str, *, lazy: bool) -> None:
    af = _MODELS[model](ActuarialFrame(_FITS.lazy() if lazy else _FITS))

    assert _nodes(af)["pid"] == "i64"


@pytest.mark.parametrize("model", ["renamed", "renamed twice"])
def test_the_renamed_column_is_an_i64_from_either_door(model: str) -> None:
    eager = _MODELS[model](ActuarialFrame(_FITS))
    lazy = _MODELS[model](ActuarialFrame(_FITS.lazy()))

    assert _nodes(lazy) == _nodes(eager)
    assert _nodes(lazy)["policy@1"] == "i64"
    assert lazy.graph.fingerprint() == eager.graph.fingerprint()


@pytest.mark.parametrize("model", ["renamed", "renamed twice"])
@pytest.mark.parametrize("lazy", [False, True], ids=["dataframe", "lazyframe"])
def test_the_renamed_column_is_collected_as_an_int64(model: str, *, lazy: bool) -> None:
    af = _MODELS[model](ActuarialFrame(_FITS.lazy() if lazy else _FITS))

    out = af.collect()

    assert out.schema["policy"] == pl.Int64
    assert out["policy"].to_list() == [7, 8]


@pytest.mark.parametrize("model", ["renamed", "renamed twice"])
@pytest.mark.parametrize("lazy", [False, True], ids=["dataframe", "lazyframe"])
def test_a_renamed_value_past_i64_is_refused_naming_it(
    model: str, *, lazy: bool
) -> None:
    af = _MODELS[model](ActuarialFrame(_PAST.lazy() if lazy else _PAST))

    with pytest.raises(UnmappedDtypeError, match="holds 18446744073709551615"):
        GraphExporter(af).export(profile="executable")


@pytest.mark.parametrize("lazy", [False, True], ids=["dataframe", "lazyframe"])
def test_a_dropped_value_past_i64_leaves_history_untyped(*, lazy: bool) -> None:
    af = _dropped(ActuarialFrame(_PAST.lazy() if lazy else _PAST))

    assert _nodes(af)["pid"] == "unknown"


@pytest.mark.parametrize(
    "model", ["renamed, then the name reused", "dropped, then the name reused"]
)
def test_a_name_taken_over_keeps_its_arrival_type_on_the_leaf(model: str) -> None:
    book = pl.DataFrame({"pid": [7, 8], "x": [1.0, 2.0]})
    nodes = _nodes(_MODELS[model](ActuarialFrame(book)))

    assert nodes["pid"] == "i64"
    assert nodes["pid@1"] == "f64"


def test_a_column_written_over_keeps_its_arrival_type_on_the_leaf() -> None:
    af = ActuarialFrame(pl.DataFrame({"n": [1, 2], "x": [1.0, 2.0]}))
    af.n = af.n * 1.5

    nodes = _nodes(af)

    assert nodes["n"] == "i64"
    assert nodes["n@1"] == "f64"


def test_a_column_kept_as_it_arrived_is_typed_as_the_frame_holds_it() -> None:
    af = ActuarialFrame(_FITS.lazy())
    af.r = af.x * 2

    assert _nodes(af) == {"pid": "i64", "x": "f64", "r@1": "f64"}
