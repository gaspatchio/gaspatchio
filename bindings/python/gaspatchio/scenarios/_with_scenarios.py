# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Implementation of with_scenarios() for scenario expansion.
# ABOUTME: Cross-joins ActuarialFrame with scenario IDs to enable multi-scenario runs.
# ruff: noqa: SLF001

"""Implementation of with_scenarios() for scenario expansion."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame._across_rows import crossing_a_book, hold_a_crossing
from gaspatchio.frame.calculation_log import (
    _refuse_reserved_column_names,
    _working_columns,
)
from gaspatchio.rollforward import _registry as _rollforward_registry
from gaspatchio.scenarios._validate import (
    check_no_duplicate_ids,
    check_no_scenario_column,
    check_non_empty,
)

# How many scenario axes the stamp above remembers. A run has one, and a
# process holds a handful at once -- a sensitivity script running a
# one-dimensional sweep beside a two-dimensional one is the shape that has
# more than one. Small enough that the tuples kept alive are nothing beside
# the frames the run is holding.
_AXES_REMEMBERED: Final[int] = 8

# The column a scenario run cross-joins its axis under, and the column a
# seeded plan hands each scenario its seed in. The seed travels beside the
# axis as data rather than as an argument, so it reaches the model at any
# batch size; it is never an axis of its own, being one value per scenario.
SCENARIO_COLUMN: Final[str] = "scenario_id"
SEED_COLUMN: Final[str] = "rng_seed"

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.frame.calculations import MintedColumns, SourceSpan


def with_scenarios(  # noqa: PLR0913 — one parameter per thing the cross-join or its record has to be told; folding them into an object would rename the list rather than shorten it
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    *,
    categorical: bool = False,
    site: SourceSpan | None = None,
    axis: Sequence[str] | Sequence[int] | None = None,
) -> ActuarialFrame:
    """
    Expand ActuarialFrame across scenarios via cross-join.

    Creates a new ActuarialFrame with len(af) x len(scenario_ids) rows,
    preserving all original columns and adding a scenario_id column.

    This is the fundamental operation for running actuarial models across
    multiple economic scenarios in a single vectorized execution.

    **The axis is a column handed to the model, and the record says so.**
    The scenario column is written into the calculation log as an
    injection -- ``kind: input``, ``provenance: injected``, stamped with a
    content hash over the scenario identifiers and located at the line
    that asked for the expansion. It is not the policy data the model was
    run over: the model-points file has no such column, and an artifact
    calling it one would put the framework's own doing under the book's
    name. What it is, is a whole column of values arriving at a known
    line, which is the arrival ``injected`` was defined for.

    **The stamp is over the identifiers, not over the cross-join's
    product.** What was handed over is the axis -- three labels, or ten
    thousand -- and the rows are what the join then made of it. Hashing
    the expanded column would give one axis a different identity on every
    book it was run over, which is the same mistake as hashing the name
    the values landed under.

    **And it is the axis of the run, not of the batch.** A batched run
    cross-joins one slice of the scenarios at a time; those slices are how
    the run was cut for memory and are not a fact about the calculation.
    Stamping each slice would make "did every scenario fold the same
    graph?" answer no on every run that has more than one scenario, which
    is the question :func:`~gaspatchio.scenarios.for_each_scenario`'s own
    record exists to answer honestly. So a caller that is cutting a run
    into batches states the whole axis with ``axis=`` and the record names
    what the run was given; every other caller hands over exactly what it
    cross-joined, and the two are the same thing.

    **A frame rebuilt over the crossing is judged against it.** Crossed
    with more than one scenario, the frame holds every scenario's copy of
    every policy, so a share of the book taken in plain Polars over its
    collected values is taken over every copy at once. A frame built over
    such values -- ``ActuarialFrame(af.collect().with_columns(...))`` -- is
    refused by name unless they are the crossed frame's own; compute the
    column on the book before crossing it, or join a side table through
    the frame (spec section 13.2). Crossed with one scenario, nothing is
    judged.

    Args:
        af: Input ActuarialFrame to expand
        scenario_ids: List of scenario identifiers (strings or integers)
        scenario_column: Name for the scenario ID column (default: "scenario_id")
        categorical: If True and scenario_ids are strings, use Categorical dtype
                    for better join/groupby performance (default: False)
        site: Where the record should say the axis arrived, for a caller
            that ran the expansion on somebody else's behalf. None -- the
            ordinary case -- walks the live stack out to the line the
            modeller wrote, which is the ``.run(...)`` in their own script.
        axis: Every scenario of the run this expansion is one batch of,
            for the record's content stamp. None -- the ordinary case --
            stamps what is being cross-joined, which is the whole axis
            whenever nobody is batching.

    Returns:
        ActuarialFrame with expanded rows and scenario_column added.

    Examples:
    --------
    **Basic scenario expansion:**

    ```python
    from gaspatchio import ActuarialFrame
    from gaspatchio.scenarios import with_scenarios

    # 2 policies
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})

    # Expand to 3 scenarios → 6 rows
    af = with_scenarios(af, ["BASE", "UP", "DOWN"])
    print(af.collect())
    ```

    **Single deterministic scenario (scenario-ready-by-default):**

    ```python
    # Even single-scenario models should use with_scenarios
    af = with_scenarios(af, ["DETERMINISTIC"])
    ```

    **Integer scenarios for stochastic runs:**

    ```python
    # For 10K stochastic scenarios, use integers for performance
    af = with_scenarios(af, list(range(1, 10001)))
    ```

    **Categorical encoding for named scenarios:**

    ```python
    # Use categorical=True for better groupby/join performance with string IDs
    af = with_scenarios(af, ["BASE", "UP", "DOWN"], categorical=True)
    ```

    """
    crossed = cross_the_axis(
        af,
        scenario_ids,
        scenario_column,
        categorical=categorical,
        site=site,
        axis=axis,
    )
    # The frame is handed back with no runner around the model it is given
    # to, so the crossing itself is held: a frame the model builds over its
    # values is judged against it (spec section 13.2), as a scenario plan's
    # batch holding more than one scenario is.
    if crossed._df is not None:
        hold_a_crossing(
            crossed._df,
            column=scenario_column,
            scenarios=scenario_ids,
            columns=crossed.columns,
        )
    return crossed


def cross_the_axis(  # noqa: PLR0913 -- with_scenarios' own parameters
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    *,
    categorical: bool = False,
    site: SourceSpan | None = None,
    axis: Sequence[str] | Sequence[int] | None = None,
) -> ActuarialFrame:
    """Cross ``af`` with ``scenario_ids`` as :func:`with_scenarios` does, holding none.

    A scenario plan crossing one batch calls this: it holds the batch
    itself, around the model, so the crossing is not held here.
    """
    check_non_empty(scenario_ids)  # type: ignore[misc]
    check_no_duplicate_ids(scenario_ids)  # type: ignore[misc]
    check_no_scenario_column(af, scenario_column)
    _refuse_reserved_column_names((scenario_column,), door="scenario_column")
    return _crossed(
        af,
        {scenario_column: list(scenario_ids)},
        stamped={scenario_column: axis if axis is not None else scenario_ids},
        site=site,
        categorical=scenario_column if categorical else None,
    )


def scenario_axis(  # noqa: PLR0913 -- the batch, the run, their seeds and the site
    af: ActuarialFrame,
    scenario_ids: Sequence[str] | Sequence[int],
    *,
    axis: Sequence[str] | Sequence[int],
    seeds: Sequence[int] | None,
    run_seeds: Sequence[int] | None,
    site: SourceSpan | None,
) -> ActuarialFrame:
    """Cross-join one batch of a run's scenarios, with each seed where there is one.

    The seed is a second column the plan hands the model at the same line as
    the axis: one value per scenario, injected, stamped over the whole run's
    seeds as the axis is stamped over the whole run's identifiers. A seeded
    plan's seed therefore reaches the model at any batch size, as data the
    model reads with ``af.rng_seed``.
    """
    check_no_scenario_column(af, SCENARIO_COLUMN)
    columns: dict[str, list[object]] = {SCENARIO_COLUMN: list(scenario_ids)}
    stamped: dict[str, Sequence[object]] = {SCENARIO_COLUMN: axis}
    if seeds is not None and run_seeds is not None:
        check_no_scenario_column(af, SEED_COLUMN)
        columns[SEED_COLUMN] = list(seeds)
        stamped[SEED_COLUMN] = run_seeds
    return _crossed(af, columns, stamped=stamped, site=site)


def composed_alone(
    af: ActuarialFrame, *, seed: int | None, site: SourceSpan | None
) -> ActuarialFrame:
    """Return a fresh successor of ``af`` for one scenario composed on its own.

    The scenario's own composition is the model run over the book with no
    axis at all, so its record is the standalone model's wherever nothing
    was shocked. The successor carries the log exactly as a cross-join
    would, so the model's assignments land on a frame of their own and the
    caller's ``af`` is left as it was. A seeded scenario has its one seed
    handed over as the run hands it to every batch.
    """
    if seed is None:
        return _crossed(af, {}, stamped={}, site=site)
    check_no_scenario_column(af, SEED_COLUMN)
    return _crossed(af, {SEED_COLUMN: [seed]}, stamped={SEED_COLUMN: [seed]}, site=site)


def _crossed(
    af: ActuarialFrame,
    columns: dict[str, list[object]],
    *,
    stamped: dict[str, Sequence[object]],
    site: SourceSpan | None,
    categorical: str | None = None,
) -> ActuarialFrame:
    """Return ``af`` cross-joined with ``columns``, each recorded as injected.

    No columns is the frame over the same plan, as a successor that carries
    the log: the model the caller hands it to writes onto a frame of its own.
    """
    base_df = af._df if af._df is not None else pl.LazyFrame()
    if columns:
        scenarios_df = pl.DataFrame(columns)
        # Apply categorical encoding if requested
        if categorical is not None and scenarios_df[categorical].dtype == pl.Utf8:
            scenarios_df = scenarios_df.with_columns(
                pl.col(categorical).cast(pl.Categorical)
            )
        # Lazy cross-join: keep the plan lazy so downstream streaming/aggregation
        # can push through without materialising the n_policies x n_scenarios frame.
        #
        # maintain_order="left_right" pins model points major, scenarios minor -- the
        # order every tutorial and worked example already implies. Without it the two
        # engines disagree: the in-memory engine emits model-point-major, while the
        # streaming engine (what ActuarialFrame.collect() uses by default) emits
        # scenario-major, so the same frame reads differently depending on which
        # engine ran it. Nothing downstream should have to know which one that was.
        expanded = base_df.join(
            scenarios_df.lazy(), how="cross", maintain_order="left_right"
        )
    else:
        expanded = base_df

    # Return as ActuarialFrame, preserving mode
    # The scenario axis is the same model one step wider, so what the frame
    # was told about itself comes with it -- including whether a column
    # written twice keeps the output of the definition that was replaced.
    #
    # The frame's own working columns ride in the plan too -- the rollforward
    # kernel's struct, a replaced definition's values -- and they are not
    # data arriving at the new frame, which refuses a column under their
    # prefixes. So it is built over the model's own columns and then handed
    # the whole plan, which keeps them out of its `columns` as well. They
    # are read off the plan itself, the one account of them that cannot lag,
    # and only where the frame can hold any: a reassignment it retained, or a
    # rollforward compiled in this process -- the guard `_batch` puts on the
    # same columns, which spares an ordinary model the schema resolve.
    working = (
        _working_columns(expanded.collect_schema().names())
        if af._retained_columns or _rollforward_registry.has_entries()
        else []
    )
    # A new crossing of a book crossed before is not a rebuild over the
    # earlier one, so it is not judged against it.
    with crossing_a_book():
        expanded_af = ActuarialFrame(
            expanded.drop(working) if working else expanded,
            mode=af._mode,
            verbose=af._verbose,
            retain_superseded=af._retain_superseded,
        )
    if working:
        expanded_af._set_plan(expanded)
    # The scenario axis widens the same model; anything calculated before the
    # cross-join stays answerable on the expanded frame, and the axis column
    # itself is recorded as what it is -- values handed over at this line.
    af._carry_calculation_log(
        expanded_af,
        _injections(stamped, site=site) if stamped else None,
    )
    return expanded_af


def _injections(
    stamped: dict[str, Sequence[object]],
    *,
    site: SourceSpan | None,
) -> MintedColumns:
    """Return the axis, and a seeded run's seeds, as columns handed to the model.

    ``origin`` is ``join`` because a cross-join is the statement that put
    the column on the frame, and the graph reads the node rather than the
    door to decide what the column *is*: an ``injected`` call carries its
    own values, so the record comes out ``kind: input``,
    ``provenance: injected``, with the door dropped exactly as it is
    dropped for every other injection.

    The identifiers are stamped as they were declared, before any
    categorical encoding: the encoding is a choice about how the column
    sits in memory and is not part of what was handed over. Stamping the
    encoded column would also refuse outright, since a categorical is a
    type this format's vocabulary has no name for -- and a performance
    flag must not be able to stop a model exporting.
    """
    from gaspatchio._semantic.ir import Call  # noqa: PLC0415 — cycle
    from gaspatchio.frame.calculations import MintedColumns  # noqa: PLC0415 — cycle

    return MintedColumns(
        origin="join",
        columns={
            column: (
                Call(
                    "injected",
                    args=(),
                    attrs=(
                        ("content", _stamp_of(tuple(values), column)),
                        ("origin", "series"),
                    ),
                ),
                pl.col(column),
            )
            for column, values in stamped.items()
        },
        source=site,
    )


@lru_cache(maxsize=_AXES_REMEMBERED)
def _stamp_of(axis: tuple[str, ...] | tuple[int, ...], scenario_column: str) -> str:
    """Return the content stamp over one scenario axis, taken once per run.

    Memoized because a batched run composes the same axis once per batch: a
    ten-thousand-scenario sweep at ``batch_size=1`` would otherwise hash ten
    thousand identifiers ten thousand times, which is 14 seconds of SHA-256
    added to a run that gained nothing by it. The axis is a tuple of labels
    and the stamp is a pure function of it, so remembering the last few costs
    a tuple and buys every batch after the first.
    """
    from gaspatchio._identity import injected_content_sha_of  # noqa: PLC0415 — cycle

    return injected_content_sha_of(pl.Series("injected", list(axis)), scenario_column)


def scenario_axis_columns(af: ActuarialFrame) -> tuple[str, ...]:
    """Return the columns this frame's calculation log records as a scenario axis.

    Read from the record :func:`_injections` writes and nowhere
    else: a column a cross-join handed the model, recorded with origin
    ``join`` and an ``injected`` node. That is what tells the axis apart
    from a table joined on (a ``join`` node) and from values a model
    assigned itself (an ``assignment`` origin), whatever ``scenario_column``
    named it. A results writer reads it to name a row on a scenario run by
    its policy and its scenario together.
    """
    from gaspatchio._semantic.ir import Call  # noqa: PLC0415 — cycle
    from gaspatchio.frame.calculations import CalculationRecord  # noqa: PLC0415 — cycle

    found: list[str] = []
    for entry in af._calculations:
        if (
            isinstance(entry, CalculationRecord)
            and entry.origin == "join"
            and isinstance(entry.node, Call)
            and entry.node.name == "injected"
            and entry.column not in found
            and entry.column != SEED_COLUMN
        ):
            found.append(entry.column)
    return tuple(found)
