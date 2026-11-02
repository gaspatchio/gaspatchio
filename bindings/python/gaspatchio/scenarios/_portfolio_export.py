# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Run declared portfolio aggregations for graph export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio.frame.graph.portfolio import (
    _ACROSS_THE_BOOK,
    _BY_NAME,
    _SHOWN,
    DECLARED_BESIDE_MAIN,
    PortfolioFold,
    PortfolioFoldError,
    _column_of,
    _partitioned,
    axis_entries,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import polars as pl

    from gaspatchio.frame.base import ActuarialFrame


def fold_the_book(  # noqa: PLR0913 — one parameter per thing a refusal has to be able to name; folding them into an object would rename the list rather than shorten it
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    *,
    book: pl.DataFrame,
    finished: pl.DataFrame,
    asked: Sequence[str],
    model_file: str,
    source: str,
    period: int | None,
) -> tuple[PortfolioFold, ...]:
    """Return the folds of ``book`` the model and the command line ask for.

    Args:
        model_fn: The model's own entry point, run again over the whole
            book as one batch. The frame is the book here, as it is in the
            first run, which already held every policy's values at once: a
            batch cut by the machine's memory would make the fold depend on
            the machine, and a setup that rebuilt its frame from collected
            values is refused in a batch of several, so one reviewer's
            command could total the book where another's refused it.
        book: The model points as they arrive. Every row of them: a fold
            of a selection would be a total of whatever the export happened
            to sample, published under the book's name.
        finished: The frame the first run produced, read for three things
            only -- whether a column the accumulators name exists, whether
            it holds one value per policy or one per period, and how many
            policies each cut of a grouped fold holds.
        asked: The accumulator specifications the command line gave, in
            the order it gave them. Empty reads the model's own
            ``AGGREGATIONS``; anything here overrides it.
        model_file: The model's file name, for the refusal that names what
            it would have to declare.
        source: The model-point file's own name, for the sentences.
        period: The projection period the document is pinned to, or None
            where every period was taken. A pinned document's fold is
            pinned with it: an entry stating ``periods: [37]`` beside a
            run of eighty-three numbers would be the document contradicting
            itself on its own axis.

    Returns:
        One entry per fold, in the order the accumulators were declared,
        with a grouped fold's own entries sorted by their group key so that
        two exports of one run compare as written. Never empty: a request
        that folds nothing is refused rather than returned.

    Raises:
        PortfolioFoldError: If nothing declares the accumulators, if a
            specification is not one of the forms, if an accumulator names
            a column the model did not produce or groups by one that is on
            no frame, or if the policy axis cannot carry the fold asked
            for.

    """
    aggregations = (
        _from_the_command_line(asked, finished=finished, source=source)
        if asked
        else _declared_by(model_fn, model_file=model_file)
    )
    aggregations = _aliased(aggregations)
    _refuse_columns_the_model_has_not_got(
        aggregations, finished=finished, source=source
    )
    _refuse_a_cut_no_frame_can_make(aggregations, book=book, finished=finished)
    result = _run(model_fn, book, aggregations)
    return axis_entries(
        result,
        aggregations,
        book=book,
        source=source,
        period=period,
        counted_on=finished,
    )


def _run(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    book: pl.DataFrame,
    aggregations: Sequence[Any],
) -> Any:  # noqa: ANN401 — AggregatedResult, imported where the driver is
    """Return ``run_aggregated``'s own result, its refusals passed on as ours.

    **One batch, the whole book.** The first run of the command has already
    held every policy's values at once, so a batch the size of the book asks
    nothing of memory that the command has not already spent. What it buys
    is a fold that does not depend on the machine: under ``"auto"`` the
    batches follow the memory budget and a seed of a tenth of the book, so a
    model whose setup collects and rebuilds its frame -- refused in a batch
    of several, because the batch cannot see whether that setup read across
    rows (section 13.2) -- was refused on a book of two policies and on a
    reviewer's laptop alike, by a rule about memory rather than about the
    model. Over the whole book the setup reads the rows the first run read,
    and the fold is that run's own total.

    The driver states plainly which aggregators the policy axis cannot
    carry -- ``Count`` counts scenarios, ``ArgMin`` needs a scenario to
    name, ``.of(...)`` reduces each batch to one value and so depends on
    the batch size. Those sentences are better than anything this module
    could write about the same mistake, so they are carried through under
    this module's own error type rather than restated.
    """
    from gaspatchio.scenarios import run_aggregated  # noqa: PLC0415 — would cycle

    try:
        return run_aggregated(
            model_fn, book, aggregations, batch_size=max(book.height, 1)
        )
    except (ValueError, NotImplementedError) as refusal:
        raise PortfolioFoldError(str(refusal)) from refusal


def _declared_by(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame], *, model_file: str
) -> tuple[Any, ...]:
    """Return the accumulators the model declares beside ``main``."""
    import inspect  # noqa: PLC0415 — one reflective read, on one path

    module = inspect.getmodule(model_fn)
    declared = getattr(module, DECLARED_BESIDE_MAIN, None)
    if declared is None:
        raise PortfolioFoldError(_nothing_declared(model_file))
    if isinstance(declared, str) or not isinstance(declared, (tuple, list)):
        raise PortfolioFoldError(_declared_the_wrong_shape(model_file, declared))
    if not declared:
        raise PortfolioFoldError(_declared_nothing(model_file))
    return tuple(declared)


def _from_the_command_line(
    asked: Sequence[str], *, finished: pl.DataFrame, source: str
) -> tuple[Any, ...]:
    """Return the accumulators a run of ``<fold>:<column>,<column>`` names.

    The fold is named once and the columns after it, because that is the
    sentence a caller is saying: *sum these*. Which aggregator each column
    then gets is read off the column's own shape -- one value per policy
    takes the fold across the book, one value per period takes it down the
    timeline -- because those are two different aggregators in this
    framework and asking a caller to know which is asking them to know an
    implementation detail of the thing they already named.
    """
    import polars as pl  # noqa: PLC0415 — the frame types are only needed here

    built: list[Any] = []
    for spec in asked:
        name, _, columns = spec.strip().partition(":")
        wanted = [part.strip() for part in columns.split(",") if part.strip()]
        if name not in _BY_NAME or not wanted:
            raise PortfolioFoldError(_not_a_fold(spec))
        across, down = _BY_NAME[name]
        for column in wanted:
            if column not in finished.columns:
                raise PortfolioFoldError(
                    _no_such_column(column, finished=finished, source=source)
                )
            per_period = isinstance(finished.schema[column], pl.List)
            which = down if per_period else across
            if which is None:
                raise PortfolioFoldError(_only_down_the_timeline(name, column))
            built.append(_aggregator(which)(column))
    return tuple(built)


def _aggregator(name: str) -> Any:  # noqa: ANN401 — an aggregator class, by the framework's own name for it
    """Return the aggregator class the framework spells ``name``."""
    from gaspatchio import scenarios  # noqa: PLC0415 — module scope would cycle

    return getattr(scenarios, name)


def _aliased(aggregations: Sequence[Any]) -> tuple[Any, ...]:
    """Return every accumulator carrying an alias, adding the column's own where none.

    ``run_aggregated`` keys its outputs by alias and refuses an accumulator
    without one, which is right for a caller reading those outputs back by
    name. Here the outputs are read back by the column they are a fold of,
    so a model that wrote ``Sum("pv_net_cf")`` and nothing else has said
    everything this needs -- and making it write the column's name twice
    would be ceremony rather than clarity. An alias the model did state is
    left exactly as it stated it.
    """
    seen: set[str] = set()
    out: list[Any] = []
    for agg in aggregations:
        named = agg if isinstance(agg, _partitioned()) else _with_an_alias(agg)
        alias = named.alias if isinstance(named, _partitioned()) else named.alias_
        if alias in seen:
            raise PortfolioFoldError(_two_folds_under_one_name(alias))
        seen.add(alias)
        out.append(named)
    return tuple(out)


def _with_an_alias(agg: Any) -> Any:  # noqa: ANN401 — one aggregator, of whichever kind the model declared
    """Return the accumulator with an alias, the column's own where it had none."""
    if getattr(agg, "alias_", None):
        return agg
    return agg.alias(agg.column)


def _refuse_columns_the_model_has_not_got(
    aggregations: Sequence[Any], *, finished: pl.DataFrame, source: str
) -> None:
    """Refuse a fold of a column no run of this model produced.

    Checked against the finished frame before the second run rather than
    discovered inside it, because a fold that fails half way through a
    batched run of a hundred-thousand-policy book has spent the run to
    report a typo.
    """
    for agg in aggregations:
        column = _column_of(agg)
        if column not in finished.columns:
            raise PortfolioFoldError(
                _no_such_column(column, finished=finished, source=source)
            )


def _refuse_a_cut_no_frame_can_make(
    aggregations: Sequence[Any], *, book: pl.DataFrame, finished: pl.DataFrame
) -> None:
    """Refuse a grouped fold whose grouping column is on no frame.

    A scenario axis is a cross-join on the model points, so a model
    declaring ``.over("scenario_id")`` folds a book that carries scenarios
    and says nothing at all about a book that does not. Told here, the
    caller is pointed at the frame they meant; discovered inside the
    driver, it arrives as a column-not-found from a group-by nobody typed.
    """
    reachable = set(book.columns) | set(finished.columns)
    for agg in aggregations:
        if not isinstance(agg, _partitioned()):
            continue
        missing = [column for column in agg.by if column not in reachable]
        if missing:
            raise PortfolioFoldError(_nothing_to_group_by(missing, reachable))


def _nothing_declared(model_file: str) -> str:
    """Return the refusal for a fold of a model that declares no accumulators."""
    return (
        f"{model_file} declares no {DECLARED_BESIDE_MAIN}, and a portfolio "
        "fold is a total of the columns the model says are worth totalling. "
        "Which those are is an actuarial decision -- a sum of every numeric "
        "output would publish a total of a mortality rate -- so nothing here "
        "picks them for you. Declare them beside main(), as the tuple "
        "run_aggregated takes:\n\n"
        "    from gaspatchio.scenarios import PeriodSum, Sum\n\n"
        f'    {DECLARED_BESIDE_MAIN} = (Sum("pv_net_cf"), PeriodSum("net_cf"))\n\n'
        "or say it on the command line instead, which supplies the same "
        "thing for one run: --portfolio-by sum:pv_net_cf,net_cf. A column "
        "holding one value per period takes the fold down its timeline, and "
        "the entry records that it did."
    )


def _declared_nothing(model_file: str) -> str:
    """Return the refusal for an empty ``AGGREGATIONS``."""
    return (
        f"{model_file} declares {DECLARED_BESIDE_MAIN} and it is empty, so "
        "there is nothing for the fold to total. An entry on the policy "
        "axis with no values under it says nothing about the book. Name at "
        "least one column to fold -- "
        f'{DECLARED_BESIDE_MAIN} = (Sum("pv_net_cf"),) -- or drop '
        "--portfolio and export the per-policy values alone."
    )


def _declared_the_wrong_shape(model_file: str, declared: object) -> str:
    """Return the refusal for an ``AGGREGATIONS`` that is not a run of aggregators."""
    return (
        f"{model_file} declares {DECLARED_BESIDE_MAIN} as "
        f"{type(declared).__name__}, and it has to be the tuple "
        "run_aggregated takes -- a run of aggregators, each naming the "
        "column it folds:\n\n"
        f'    {DECLARED_BESIDE_MAIN} = (Sum("pv_net_cf"), PeriodSum("net_cf"))\n\n'
        "That is the same tuple a scenario sweep hands to run_aggregated, so "
        "a model already folding its book declares nothing new here."
    )


def _not_a_fold(spec: str) -> str:
    """Return the refusal for a specification that names no fold."""
    return (
        f"{spec!r} is not a way of naming a fold. One is written "
        "'<fold>:<column>,<column>' -- 'sum:pv_net_cf,net_cf' totals both "
        "columns over the book. The folds a command line may name are: "
        f"{', '.join(sorted(_BY_NAME))}. A column holding one value per "
        "period takes the fold down its timeline and the entry records that "
        "it did, so the name here is the fold you mean rather than the "
        "aggregator that performs it. Folds taking a level as well as a "
        f"column -- a quantile, a CTE -- are declared in the model's "
        f"{DECLARED_BESIDE_MAIN} instead, where there is Python to write "
        "the level in."
    )


def _no_such_column(column: str, *, finished: pl.DataFrame, source: str) -> str:
    """Return the refusal for a fold of a column this model never produced."""
    return (
        f"No column named {column!r} came out of this model over {source}, "
        "so there is nothing to fold. A portfolio total is a total of a "
        "column the run produced -- the accumulators are read against the "
        "finished frame, not against the model points. Columns the run did "
        f"produce include: {finished.columns[:_SHOWN]}."
    )


def _only_down_the_timeline(name: str, column: str) -> str:
    """Return the refusal for a fold this axis only has in its per-period form."""
    return (
        f"A {name} over the book is not a fold this axis carries, and "
        f"{column!r} holds one value per policy rather than one per period. "
        f"A {name} counts the scenarios a value arrived from, and a plain "
        "run has no scenario axis to count -- section 7.4's axis is "
        "policies. Fold a per-period column instead, where the count is "
        "taken down the timeline, or name a fold that reduces across the "
        f"book: {', '.join(_ACROSS_THE_BOOK)}."
    )


def _two_folds_under_one_name(alias: str) -> str:
    """Return the refusal for two accumulators the driver cannot tell apart."""
    return (
        f"Two accumulators are named {alias!r}, and the fold reads its "
        "outputs back by that name, so one of them would be published under "
        "the other's. Give each its own .alias(name). Where an accumulator "
        "states none, the column it folds is used as the name -- so two "
        "folds of one column need one alias each."
    )


def _nothing_to_group_by(missing: Sequence[str], reachable: set[str]) -> str:
    """Return the refusal for a grouped fold whose grouping column is on no frame."""
    names = ", ".join(repr(one) for one in missing)
    return (
        f"The fold groups by {names}, and neither the model points nor the "
        "frame this run produced carries that column, so there are no cuts "
        "to fold over. A scenario axis is a cross-join on the model points "
        "-- the scenario column is on the book the run was given, not on "
        "the plain one -- so a model declaring .over('scenario_id') folds a "
        "scenario frame and says nothing about a book without one. Run it "
        "over the frame the scenarios were joined onto, or drop the "
        "grouping. Columns that are reachable include: "
        f"{sorted(reachable)[:_SHOWN]}."
    )
