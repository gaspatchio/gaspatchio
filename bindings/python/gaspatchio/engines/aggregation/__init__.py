# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What an engine folds a book into: the aggregators ``run_aggregated`` takes.

An engine that reduces on its own device is handed the caller's aggregator
objects -- the ``Sum``, the ``PeriodSum``, the ``.over("product_id")`` -- and
has to answer with the number Polars would have answered. The only way to
promise that is to fold into the very same accumulators through the very same
code, so this door publishes the core's own objects rather than a description
of them:

- :class:`AggregatingEngine` and :func:`aggregating`, the optional capability
  an engine that folds answers to, and the check both folding doors make
  before anything is built. They live here rather than beside the base
  :class:`~gaspatchio.engines.protocol.Engine` because a fold answers the
  core's own result type, and the engine protocol does not depend on model
  execution;
- :class:`AggregatedResult`, the one result type both paths return;
- :func:`fold_per_policy`, the Polars path's own fold of one batch's
  per-policy columns, which an engine hands the handful of columns a batch's
  aggregators of one value per policy read -- grouping by ``.over(by)``
  included, exactly as ``run_aggregated`` groups. It is that path's
  per-policy half only: a per-period kind is refused, so an engine cannot
  ask Polars for the per-period partials it exists to compute itself;
- :func:`extract_outputs`, which turns the accumulators into the values and
  frames a caller reads;
- :func:`reject_scenario_axis_only` and :func:`reject_multi_level_over`, the
  refusals ``run_aggregated`` applies before it starts -- ``Count``,
  ``ArgMin``, ``ArgMax`` and ``.of()`` on the policy axis, and a multi-level
  quantile partitioned with ``.over()`` -- so an engine refuses exactly what
  Polars refuses;
- :func:`alias_of`, :func:`inner_of` and :class:`Partitioned`, which read an
  aggregator the way the drivers read it;
- the seven per-period kinds whose batch partial is a closed form -- a sum, a
  count, an extremum, a sum beside a count, a count, mean and sum of squared
  deviations -- which an engine may compute where it computed the column and
  then hand to the aggregator's own ``add_input``.

**Everything here is the producer's own object, held by test.** A second
reading of an accumulator's arithmetic could disagree with the first and never
say so; a fold through the first cannot.

Importing this door loads the scenarios package, which ``import gaspatchio``
has already loaded. It is imported by name when an engine folds, never from
:mod:`gaspatchio.engines` itself, so discovering an engine stays as cheap as it
was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from gaspatchio.engines.protocol import Engine
from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport
from gaspatchio.scenarios._aggregated import AggregatedResult
from gaspatchio.scenarios._aggregated import _alias_of as alias_of
from gaspatchio.scenarios._aggregated import _fold_per_policy as fold_per_policy
from gaspatchio.scenarios._aggregated import (
    _reject_multi_level_over as reject_multi_level_over,
)
from gaspatchio.scenarios._aggregated import (
    _reject_scenario_axis_only as reject_scenario_axis_only,
)
from gaspatchio.scenarios._fold import _extract_outputs as extract_outputs
from gaspatchio.scenarios._fold import _inner as inner_of
from gaspatchio.scenarios._metric import _Partitioned as Partitioned
from gaspatchio.scenarios._period_aggregators import (
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import polars as pl

__all__ = [
    "AggregatedResult",
    "AggregatingEngine",
    "Partitioned",
    "PeriodCount",
    "PeriodMax",
    "PeriodMean",
    "PeriodMin",
    "PeriodStd",
    "PeriodSum",
    "PeriodVariance",
    "aggregating",
    "alias_of",
    "extract_outputs",
    "fold_per_policy",
    "inner_of",
    "reject_multi_level_over",
    "reject_scenario_axis_only",
]


class AggregatingEngine(Engine, Protocol):
    """An engine that can also fold a book into ``run_aggregated``'s aggregators.

    An optional capability, and so a protocol of its own. An engine that runs
    a model is an engine whether or not it can reduce one, and the base
    protocol does not grow a method most engines will not have. The two doors
    that fold -- ``run_aggregated(engine=...)`` and ``gspio run-artifact
    --aggregate`` -- ask for this one, and refuse by name an engine that does
    not answer to it (:func:`aggregating`).

    The aggregators are the caller's own objects, the ones the Polars path
    takes unchanged, and the result is the core's own
    :class:`~gaspatchio.scenarios.AggregatedResult`. What an engine promises
    is Polars' answer under the specification's agreement rule (section
    11.1.12): the only permitted difference is the order floating-point
    additions were made in.
    """

    def aggregate(
        self,
        document: dict[str, object],
        inputs: pl.DataFrame,
        aggregations: Sequence[Any],
        *,
        batch: int | None = None,
    ) -> AggregatedResult:
        """Fold the document's final schema over the book, never publishing a row."""
        ...


def aggregating(engine: Engine, name: str) -> AggregatingEngine:
    """Return the engine as one that folds, or refuse it by name.

    Asked of the object rather than of its type, because an engine is a
    duck: a package outside this one registers a factory and nothing here
    has its class to inspect. What is asked is the one thing the doors will
    call, so an engine that answers ``aggregate`` is taken at its word and
    one that does not is told so before anything is built.

    Raises:
        EngineRefusal: If the engine has no ``aggregate`` to call. The
            refusal is in the tree group, because nothing was read or run,
            and it names the engine and the way round.

    """
    if callable(getattr(engine, "aggregate", None)):
        return cast("AggregatingEngine", engine)
    raise EngineRefusal(
        RunReport(
            refusals=(
                Refusal(
                    group="tree",
                    where=name,
                    count=None,
                    what=(
                        f"the {name} engine runs a model and cannot fold one "
                        "into aggregates: it has no aggregate method"
                    ),
                    move=(
                        "aggregate on Polars (run_aggregated without engine=), "
                        "or on an engine that folds, such as jax"
                    ),
                    # No section of the specification states this: a fold is
                    # outside the artifact (section 4), so the refusal cites
                    # no clause and its own sentence carries the reason.
                    clause=None,
                ),
            ),
            notes=(),
        )
    )
