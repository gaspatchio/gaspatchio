# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``when`` that reads a policy with no run answers null for that policy.

A null outer list is a policy with no periods (11.1.18). In a ``when``'s
condition it already made the policy null; in a branch the kernel read it
as a null in each period, so ``when(af.in_force).then(af.gmdb).otherwise(
af.av)`` with one policy's ``gmdb`` absent answered that policy's ``av``
in the periods the condition did not select and nulls in those it did, and
the answer moved with the route the line took (a per-policy condition
already answered null where the run stood in ``otherwise``, not in
``then``). Section 11.1.28 now says one thing: the policy is null whenever
any run in the line is null, selected or not -- the reference reader's
reading -- and the producer answers so on both engines.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader.shared import Column  # noqa: E402
from reference import Reader  # noqa: E402

_D = datetime.date
_BOOK = pl.DataFrame(
    [
        pl.Series("av", [[100.0, 90.0], [50.0, 40.0]], dtype=pl.List(pl.Float64)),
        pl.Series("gm", [[95.0, 95.0], None], dtype=pl.List(pl.Float64)),
        pl.Series("n", [[1, 2], [3, 4]], dtype=pl.List(pl.Int64)),
        pl.Series("nn", [[2, 2], None], dtype=pl.List(pl.Int64)),
        pl.Series("b", [[True, False], [True, False]], dtype=pl.List(pl.Boolean)),
        pl.Series(
            "dn",
            [[_D(2026, 1, 1), _D(2026, 2, 1)], None],
            dtype=pl.List(pl.Date),
        ),
        pl.Series(
            "d",
            [[_D(2025, 1, 1), _D(2025, 2, 1)], [_D(2024, 1, 1), _D(2024, 2, 1)]],
            dtype=pl.List(pl.Date),
        ),
        pl.Series("s", [96.0, 45.0], dtype=pl.Float64),
        pl.Series("f", [True, False], dtype=pl.Boolean),
    ]
)

# Each line, and its answer by hand: the first policy's run, then null.
_LINES: dict[str, tuple[Callable[[ActuarialFrame], object], list]] = {
    "comparison condition, the run in then": (
        lambda af: when(af.av > 60.0).then(af.gm).otherwise(af.av),
        [[95.0, 95.0], None],
    ),
    "comparison condition, the run in otherwise": (
        lambda af: when(af.av > 95.0).then(af.av).otherwise(af.gm),
        [[100.0, 95.0], None],
    ),
    "flag-run condition, the run in then": (
        lambda af: when(af.b).then(af.gm).otherwise(af.av),
        [[95.0, 90.0], None],
    ),
    "flag-run condition, the run beside a literal": (
        lambda af: when(af.b).then(0.0).otherwise(af.gm),
        [[0.0, 95.0], None],
    ),
    "per-policy condition, the run in then": (
        lambda af: when(af.f).then(af.gm).otherwise(af.av),
        [[95.0, 95.0], None],
    ),
    "per-policy condition, the run beside a per-policy value": (
        lambda af: when(af.s > 50.0).then(af.gm).otherwise(af.s),
        [[95.0, 95.0], None],
    ),
    "whole numbers": (
        lambda af: when(af.b).then(af.nn).otherwise(af.n),
        [[2, 2], None],
    ),
    "dates": (
        lambda af: when(af.b).then(af.dn).otherwise(af.d),
        [[_D(2026, 1, 1), _D(2025, 2, 1)], None],
    ),
    "a chain, the run in an inner branch": (
        lambda af: when(af.b).then(af.av).when(af.av > 60.0).then(af.gm).otherwise(0.0),
        [[100.0, 95.0], None],
    ),
    "a chain, the run in the outer branch": (
        lambda af: when(af.b).then(af.gm).when(af.av > 60.0).then(1.0).otherwise(0.0),
        [[95.0, 1.0], None],
    ),
}


@pytest.mark.parametrize("line", list(_LINES))
@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_a_null_run_anywhere_in_the_line_nulls_the_policy(
    line: str, engine: str
) -> None:
    make, hand = _LINES[line]
    af = ActuarialFrame(_BOOK)
    af.r = make(af)

    assert af.collect(engine=engine)["r"].to_list() == hand


def test_a_line_with_no_null_run_answers_every_policy() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = when(af.b).then(af.av).otherwise(af.n * 1.0)

    assert af.collect()["r"].to_list() == [[100.0, 2.0], [50.0, 4.0]]


def test_the_reference_reader_answers_the_same() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = when(af.b).then(af.gm).otherwise(af.av)
    doc = json.loads(GraphExporter(af).export(af.collect(), profile="executable"))
    node = next(n for n in doc["nodes"] if n.get("column") == "r")
    inputs = {
        "av": Column("list[f64]", [[100.0, 90.0], [50.0, 40.0]]),
        "gm": Column("list[f64]", [[95.0, 95.0], None]),
        "b": Column("list[bool]", [[True, False], [True, False]]),
    }

    read = Reader(inputs, [], {}).evaluate(node["expr"])

    assert (read.dtype, read.values) == ("list[f64]", [[95.0, 90.0], None])


def test_the_walk_through_still_reads_as_the_when_written() -> None:
    af = ActuarialFrame(_BOOK.with_columns(pl.col("gm").fill_null([1.0, 2.0])))
    af.r = when(af.b).then(af.av).when(af.av > 60.0).then(af.gm).otherwise(0.0)
    doc = json.loads(GraphExporter(af).export(af.collect(), profile="audit"))
    node = next(n for n in doc["nodes"] if n.get("column") == "r")

    written = node["trace"][0]["expr"]

    assert written.startswith(".when((b) == (1)).then(av).otherwise(.when((av) > (60))")
    assert "is_null" not in written
    assert "list_conditional" not in written
