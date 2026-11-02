# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The engine itself: three methods, and the plan behind all of them.

``validate_tree`` is the inputs-free half -- what this engine can do with each
node, reading no book, which is what ``gspio validate --engine jax`` prints.
``run`` is the whole of it. ``aggregate`` is the whole of it folded on the
device into the aggregators ``run_aggregated`` takes, handing back totals and
never a row. None of them holds any state between calls: a run's
state is the plan it built from the document it was handed, and an engine
object that remembered one document while answering about another is the
shape that makes a result impossible to place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio.engines.report import EngineRefusal, RunReport

from .aggregate import aggregate
from .plan import ENGINE_NAME, ExecutionPlan

if TYPE_CHECKING:
    from collections.abc import Sequence

    import polars as pl

    from gaspatchio.engines.aggregation import AggregatedResult
    from gaspatchio.engines.protocol import EngineResult, NodeStatus, Sink

__all__ = ["JaxEngine"]


class JaxEngine:
    """A second implementation of the model the executable artifact describes."""

    name: str
    version: str

    def __init__(self) -> None:
        """Take this engine's name and this package's version, for the manifest."""
        from importlib.metadata import version  # noqa: PLC0415 -- once, at construction

        self.name = ENGINE_NAME
        self.version = version("gaspatchio-jax")

    def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:
        """Say what this engine can do with each node, reading no book.

        Every node rather than the final schema's: a reader asking whether a
        model ports wants to know about the whole model, including the
        definitions a later one wrote over.
        """
        return ExecutionPlan.stage_inspect(document, every_node=True).statuses

    def run(
        self,
        document: dict[str, Any],
        inputs: pl.DataFrame,
        sink: Sink,
        *,
        every_node: bool = False,
    ) -> EngineResult:
        """Run the document over the book and publish through the sink.

        Each batch is written to the sink as it finishes, with the book
        positions of its rows, and nothing is visible until every batch and
        every completion check has passed.

        Raises:
            EngineRefusal: If the tree, the book, or a check the trace carried
                refuses the run. One report carries every finding, grouped by
                the moment it became knowable.

        """
        plan = ExecutionPlan.stage_inspect(document, every_node=every_node)
        if plan.tree_refusals:
            raise EngineRefusal(
                RunReport(refusals=plan.tree_refusals, notes=tuple(plan.notes))
            )
        settled = False
        try:
            prepared = plan.stage_prepare(plan.stage_validate_inputs(inputs))
            streamed = plan.stage_stream(prepared, sink)
            result = plan.stage_complete(streamed, sink, prepared)
            # Publication has happened and the sink has settled itself; a
            # second settling would be this method undoing it.
            settled = True
        finally:
            # Whatever leaves here, the sink is settled. A refusal is the
            # ordinary case and is what the report is for; a defect -- a
            # TypeError out of a lowering, an interrupt -- is not a refusal
            # and still propagates, but it must not propagate past a sink
            # that has staged batches nobody will ever publish. The tree
            # refusal above is raised before this block, where no sink has
            # been opened; every stage after it sits inside.
            if not settled:
                sink.abandon()
        return result

    def aggregate(
        self,
        document: dict[str, Any],
        inputs: pl.DataFrame,
        aggregations: Sequence[Any],
        *,
        batch: int | None = None,
    ) -> AggregatedResult:
        """Fold the document over the book into these aggregators, on the device.

        The aggregators are the ones ``run_aggregated`` takes, unchanged, and
        the answer is its own :class:`AggregatedResult`, agreeing with the
        Polars fold under the specification's agreement rule (section 11.1.12).
        No per-policy frame is built and no row is published: each batch is
        folded where it was computed.

        Args:
            document: The executable artifact.
            inputs: The book.
            aggregations: The caller's aliased aggregators.
            batch: How many policies to a batch, where the caller pins it;
                otherwise read off each compiled program's temporaries.

        Raises:
            EngineRefusal: If the tree, an aggregator, the book, or a check
                the trace carried refuses the run. Nothing is returned.

        """
        return aggregate(document, inputs, aggregations, batch=batch)
