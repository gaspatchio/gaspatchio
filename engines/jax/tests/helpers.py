# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One small per-period model, for the tests that are about running it in parts.

Batching, publication, the cache and the three invariance properties are all
about *how* a book is run rather than about what any line of it computes, so
they run the smallest document that still has a projection axis in it: one
arriving per-period column and one cumulative sum over it. It compiles in a
fraction of a second, which is what lets a property be checked at three batch
sizes rather than argued about.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from gaspatchio.engines.protocol import FrameSink
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import invocation

if TYPE_CHECKING:
    import polars as pl
    from numpy.typing import ArrayLike

    from gaspatchio.engines.protocol import (
        ArrowStreamExportable,
        EngineResult,
        Sink,
    )
    from gaspatchio_jax.vectors import Invocation

__all__ = [
    "Watched",
    "a_read_that_misses",
    "a_running_sum",
    "cells",
    "ran",
    "streamed",
    "with_batches",
]


def cells(policy: int, periods: int) -> list[float]:
    """Return one policy's own per-period values, distinct from every other's."""
    return [float(policy * 1000 + period) for period in range(periods)]


def a_running_sum(policies: int, periods: int | list[int] = 8) -> Invocation:
    """Return a document of one per-period column and one cumulative sum of it.

    ``periods`` is one count for every policy, or one per policy where the
    book is jagged.
    """
    lengths = [periods] * policies if isinstance(periods, int) else periods
    return invocation(
        {
            "op": "call",
            "name": "cum_sum",
            "args": [{"op": "col", "name": "flow"}],
            "attrs": {},
        },
        {
            "flow": {
                "dtype": "list[f64]",
                "values": [
                    cells(policy, length) for policy, length in enumerate(lengths)
                ],
            }
        },
        "list[f64]",
    )


def ran(one: Invocation, sink: Sink | None = None, **taken: object) -> EngineResult:
    """Return what this engine answers for one document, run whole."""
    return JaxEngine().run(one.document, one.inputs, sink or FrameSink(), **taken)  # type: ignore[arg-type]


def with_batches(
    one: Invocation, batch: int | None = None, **taken: int
) -> pl.DataFrame:
    """Return one document's columns, run in batches of the size named."""
    return streamed(one, FrameSink(), batch=batch, **taken).columns


def streamed(
    one: Invocation, sink: Sink, batch: int | None = None, **taken: int
) -> EngineResult:
    """Return what one document publishes through a sink, in batches of a size.

    ``run``'s own stages and its own promise -- whatever leaves before
    publication, the sink is abandoned -- with the batch size pinned, which
    ``run`` itself never takes.
    """
    plan = ExecutionPlan.stage_inspect(one.document)
    settled = False
    try:
        prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
        stream = plan.stage_stream(prepared, sink, batch=batch, **taken)
        result = plan.stage_complete(stream, sink, prepared)
        settled = True
    finally:
        if not settled:
            sink.abandon()
    return result


class Watched(FrameSink):
    """A frame sink that remembers where every batch it was handed stands."""

    def __init__(self) -> None:
        """Start with no batch handed over."""
        super().__init__()
        self.handed: list[np.ndarray] = []

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        """Remember the batch's positions, then hold it as a frame sink does."""
        self.handed.append(np.asarray(rows))
        super().write_batch(frame, rows=rows)


# The basis the miss test reads: ten whole-number keys and one rate each.
_KEYS = tuple(range(10))


def a_read_that_misses(policies: int, *misses_at: int) -> Invocation:
    """Return a read under ``raise`` that some policies' own keys do not answer.

    The key is a calculation rather than a column, so the finding waits for
    completion: a key that arrived is answered before anything is compiled,
    which is a different test and not this one.
    """
    from tests.conftest import entry
    from tests.fixtures import make_tables

    payload = make_tables.one_key([float(key) for key in _KEYS])
    sealed = entry("table", payload, "misses")
    keys = [float(policy % len(_KEYS)) for policy in range(policies)]
    for policy in misses_at:
        keys[policy] = 99.0
    return invocation(
        {
            "op": "call",
            "name": "lookup",
            "args": [
                {
                    "op": "binop",
                    "kind": "add",
                    "left": {"op": "col", "name": "key"},
                    "right": {"op": "lit", "value": 0.0},
                }
            ],
            "attrs": {
                "table": "misses",
                "table_fingerprint": str(sealed["fingerprint"]),
                "on_missing": "raise",
                "fill_value": None,
            },
        },
        {"key": {"dtype": "f64", "values": keys}},
        "f64",
        [sealed],
    )
