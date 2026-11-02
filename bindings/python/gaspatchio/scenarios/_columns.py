# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: column= shocks: a model-point column rewritten per scenario at the door.
# ABOUTME: Recorded as an assignment at the plan's line, its formula the shock's recipe.

"""A scenario plan's shock on a single number the model reads off each policy.

A valuation rate, a maintenance expense, a solved premium: the conversion
skill's rule is that a single-cell defined name becomes a model-point
column, and a plan shocks it there. ``AdditiveShock(0.01,
column="valuation_rate")`` rewrites that column for the scenario before the
model runs, so the model reads the shocked value through the line it always
read the column with and nothing in the model changes.

The rewrite is recorded, not hidden. It is an ``assignment`` of the column
-- superseding the book's own column, as any reassignment does -- located at
the line the plan was run or declared at, and its formula is the shock's
recipe: ``af.valuation_rate + 0.01`` for one scenario composed on its own.

**A batch reads each scenario's recipe for its own rows, in one of two
forms.** A sweep of affine shocks -- multiply, add, set, and pipelines of
them -- on a float column, which is what a sensitivity sweep is, reads
per-scenario factors from a table the plan builds for the batch, keyed by
the scenario axis: each step is ``x * a + b``, or ``b`` where the step sets
the value. A multiply is ``a = f, b = -0.0`` and an add ``a = 1.0, b = d``,
both exact, so the batch's numbers are bit for bit the direct recipe's at any
batch size. Every other column shock is a ``when`` chain over the axis, one
branch per scenario. The chain was measured before this choice: at 200
scenarios in one batch it cost 20 times the factor read to collect, and at
1000 its depth overflowed the recursion every tree walk takes. Every
operation in either form is in the core vocabulary (``lookup``, ``mul``,
``add``, ``when_then``, ``eq``), so the record exports and runs on every
engine.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from gaspatchio.frame.calculations import CalculationRecord, capture_source_span
from gaspatchio.functions.conditional import when
from gaspatchio.scenarios._targets import did_you_mean, target_of
from gaspatchio.scenarios._with_scenarios import SCENARIO_COLUMN, SEED_COLUMN
from gaspatchio.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import polars as pl

    from gaspatchio.frame import ActuarialFrame
    from gaspatchio.frame.calculations import SourceSpan
    from gaspatchio.scenarios.shocks import Shock

ScenarioID = str | int

# The conversion skill's rule, quoted where a column shock names a column the
# book does not hold: what a scalar is in a model built from a workbook.
_RULE: Final[str] = (
    "single-cell defined names become model-point columns "
    "(skills/gaspatchio-model-discovery/references/spreadsheet-conversion.md)"
)


def column_targets(scenarios: Mapping[ScenarioID, Sequence[Shock]]) -> list[str]:
    """Return every model-point column the run's shocks name, in first-seen order."""
    found: dict[str, None] = {}
    for shocks in scenarios.values():
        for shock in shocks:
            target = target_of(shock)
            if target is not None and target[0] == "column":
                found.setdefault(target[1])
    return list(found)


def check_columns(
    scenarios: Mapping[ScenarioID, Sequence[Shock]], book: Sequence[str]
) -> None:
    """Refuse a column shock on a column the book does not hold.

    Raises:
        ValueError: A shock names a column the model points do not carry, or
            the scenario axis or seed column the run itself hands the model.

    """
    for sid, shocks in scenarios.items():
        for shock in shocks:
            target = target_of(shock)
            if target is None or target[0] != "column":
                continue
            column = target[1]
            if column in (SCENARIO_COLUMN, SEED_COLUMN):
                msg = (
                    f"Scenario {sid!r} shocks column {column!r}, which the run "
                    "itself hands the model; a shock moves the model's own "
                    "inputs, not the scenario axis or its seed."
                )
                raise ValueError(msg)
            if column in book:
                continue
            msg = (
                f"Scenario {sid!r} shocks model-point column {column!r}, but the "
                "model points hold no column by that name."
                f"{did_you_mean(column, book)}\n"
                f"A column shock moves a single number the model reads off each "
                f"policy, and {_RULE}. Add {column!r} to the model points, or "
                "name a table the model reads with table=."
            )
            raise ValueError(msg)


def check_column_conditions_select(
    scenarios: Mapping[ScenarioID, Sequence[Shock]],
    book: pl.DataFrame | pl.LazyFrame,
) -> None:
    """Refuse a column shock whose condition selects no policy of the book.

    A ``FilteredShock(..., column=...)`` moves the column on the policies its
    ``where=`` selects, read against the book the run values. One that
    selects none moves nothing, so the scenario would equal BASE to the bit;
    it is refused here, naming the condition and what the book holds, as a
    table shock whose condition selects no row of its table is
    (:func:`~gaspatchio.scenarios._targets.check_conditions_select`). A
    condition on a column the book does not hold is refused by name too.
    The cost is stated in the refusal: a plan run on a sample book that
    lacks the segment is refused, naming the condition.

    Raises:
        ValueError: A column shock's condition names a column the book lacks,
            or selects none of its policies.

    """
    import polars as pl  # noqa: PLC0415 -- the frame types only

    from gaspatchio.scenarios._targets import (  # noqa: PLC0415 -- private helper
        _held_values,
        inner_shocks,
    )
    from gaspatchio.scenarios.shocks import (  # noqa: PLC0415 -- private helper
        _build_filter_expr,
    )

    held_columns = book.collect_schema().names()
    for sid, shocks in scenarios.items():
        for shock in shocks:
            target = target_of(shock)
            if target is None or target[0] != "column":
                continue
            stack = [shock]
            while stack:
                one = stack.pop()
                stack.extend(inner_shocks(one))
                if not isinstance(one, FilteredShock):
                    continue
                condition = dict(one.where)
                said = f"FilteredShock where={condition!r}"
                missing = [name for name in condition if name not in held_columns]
                if missing:
                    msg = (
                        f"Scenario {sid!r} shocks model-point column {target[1]!r} "
                        f"with {said}, but the book holds no column {missing[0]!r}."
                        f"{did_you_mean(missing[0], held_columns)}\n"
                        "A column shock's condition reads the book's own "
                        "columns. Write it on a column the model points carry."
                    )
                    raise ValueError(msg)
                selected = (
                    book.lazy()
                    .filter(_build_filter_expr(condition))
                    .select(pl.len())
                    .collect()
                    .item()
                )
                if selected:
                    continue
                rows = book.lazy().select(list(condition)).collect()
                held = "; ".join(_held_values(rows, name) for name in condition)
                msg = (
                    f"Scenario {sid!r} shocks model-point column {target[1]!r} "
                    f"with {said}, but no policy of the book this run values "
                    "meets the condition, so the shock moves nothing and the "
                    f"scenario would equal BASE.\nIn the book, {held}. Write the "
                    "condition on values the book holds, or drop the shock. A "
                    "plan run on a sample book that lacks the segment is refused "
                    "here too, naming the condition: run it on a book that holds "
                    "the segment, or leave the shock out of that run."
                )
                raise ValueError(msg)


# Structural steps a model can take that read or carry a column outside any
# recorded line: a filter's predicate, a join's keys, a rename or a select's
# aliases. Where the model returned through one of them, the record cannot
# say that a column went unread, and the unread-column check does not refuse.
_STEPS_THAT_HIDE_A_READ: Final = frozenset({"filter", "join", "rename", "select"})


def columns_the_folds_read(aggregations: Sequence[object]) -> frozenset[str] | None:
    """Return every column the run's aggregators read, or None where one cannot say.

    A fold reads the column it sums -- a shocked column summed directly is a
    scenario that differs from BASE whatever the model's lines read -- and a
    partitioned fold reads its partition columns too. An aggregator that
    states no expression it reads leaves the question open.
    """
    import polars as pl  # noqa: PLC0415 -- the expression type only

    read: set[str] = set()
    for aggregation in aggregations:
        inner = getattr(aggregation, "inner", aggregation)
        read.update(str(one) for one in getattr(aggregation, "by", ()) or ())
        within = getattr(inner, "within_expr", None)
        if not callable(within):
            return None
        try:
            expr = within()
        except Exception:  # noqa: BLE001 -- an aggregator of the user's own making
            return None
        if not isinstance(expr, pl.Expr):
            return None
        read.update(expr.meta.root_names())
    return frozenset(read)


def check_columns_read(
    projected: ActuarialFrame,
    scenarios: Mapping[ScenarioID, Sequence[Shock]],
    *,
    plans_own: set[int],
    folds_read: frozenset[str] | None,
) -> None:
    """Refuse a column shock on a column no line of the model reads.

    The column equivalent of the table shock no read reached: the plan
    rewrites the column at the door, and where nothing the model computes
    reads it (and no aggregator folds it), the scenario equals BASE to every
    digit while its fingerprint says something changed. Asked only where the
    record can answer (``_lines_read``).

    Raises:
        ValueError: A scenario shocks a column the model's lines never read.

    """
    read = None if folds_read is None else _lines_read(projected, plans_own)
    if read is None or folds_read is None:
        return
    for sid, shocks in scenarios.items():
        for shock in shocks:
            target = target_of(shock)
            if target is None or target[0] != "column":
                continue
            column = target[1]
            if column in read or column in folds_read:
                continue
            raise ValueError(_unread_column_message(sid, column, read, projected))


def _lines_read(
    projected: ActuarialFrame, plans_own: set[int]
) -> dict[str, str] | None:
    """Return each column the model's own lines read, with the first line; or None.

    None where the record cannot answer: the plan's own rewrite must still be
    on the record the model returned -- a model that collected and built a
    new frame starts a new record, and its reads before that are not on it
    -- and the model took no step that reads a column outside a recorded
    line.
    """
    from gaspatchio._semantic.ir import col_refs  # noqa: PLC0415 -- cycle
    from gaspatchio.frame.calculations import (  # noqa: PLC0415 -- cycle
        StructuralOperation,
    )

    entries = projected._calculations  # noqa: SLF001 -- the batch record
    if not plans_own or not plans_own <= {id(entry) for entry in entries}:
        return None
    if any(
        isinstance(entry, StructuralOperation) and entry.kind in _STEPS_THAT_HIDE_A_READ
        for entry in entries
    ):
        return None
    read: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, CalculationRecord) or id(entry) in plans_own:
            continue
        where = entry.source
        at = entry.column if where is None else f"{Path(where.file).name}:{where.line}"
        for column in col_refs(entry.node):
            read.setdefault(column, at)
    return read


def _unread_column_message(
    sid: ScenarioID,
    column: str,
    read: Mapping[str, str],
    projected: ActuarialFrame,
) -> str:
    """Return the refusal for a column shock no line of the model reads."""
    computed = {
        entry.column
        for entry in projected._calculations  # noqa: SLF001 -- the batch record
        if isinstance(entry, CalculationRecord)
    }
    book = {name: at for name, at in read.items() if name not in computed}
    if book:
        named = ", ".join(f"{name!r} (at {at})" for name, at in sorted(book.items()))
        seen = f"The model's lines read these model-point columns: {named}."
        seen += did_you_mean(column, list(book))
    else:
        seen = "No line of the model reads a model-point column."
    return (
        f"Scenario {sid!r} shocks model-point column {column!r}, but no line "
        "of the model reads it and no aggregation folds it, so the scenario "
        f"would equal BASE.\n{seen} A column shock moves the column only "
        "through the model's reads of it -- a rate the model writes as a "
        "literal, or reads from a Curve, is not moved by it. Read the column "
        "where the model uses the number, shock what the model does read, or "
        "drop the shock."
    )


def shock_columns(
    af: ActuarialFrame,
    scenarios: Mapping[ScenarioID, Sequence[Shock]],
    *,
    stacked: bool,
    site: SourceSpan | None,
    widened: frozenset[str] = frozenset(),
) -> set[int]:
    """Rewrite each shocked column on ``af`` for the composed scenarios, recorded.

    ``scenarios`` are the scenarios being composed: a batch's, cross-joined
    on ``af`` (``stacked``), or one scenario's on its own. A column no
    composed scenario shocks is left as the book had it -- unless it is in
    ``widened``, the whole-number columns some scenario of the run shocks to
    a decimal (:func:`widened_by_the_plan`): those are read as doubles in
    every batch, so a scenario's column does not take its type from the
    scenarios that happen to share its batch.

    Returns the identities of the records written, so a reader asking
    whether the *model* reads the scenario axis can leave the plan's own
    ``when`` chains out of the answer.
    """
    written: set[int] = set()
    for column in sorted(widened - set(column_targets(scenarios))):
        written.add(_widen(af, column, site))
    for column in column_targets(scenarios):
        moved = {
            sid: [s for s in shocks if target_of(s) == ("column", column)]
            for sid, shocks in scenarios.items()
        }
        moved = {sid: shocks for sid, shocks in moved.items() if shocks}
        if not moved:
            continue
        operand = af[column]
        steps = _affine_steps(moved) if stacked and _is_float(af, column) else None
        if steps is not None:
            expr, text = _factored(af, column, list(scenarios), steps)
        elif stacked:
            expr, text = _chain(af, operand, _operand_text(column), moved)
        else:
            (shocks,) = moved.values()
            expr, text = _composed(af, operand, _operand_text(column), shocks)
        span = site if site is not None else capture_source_span()
        af[column] = expr
        written.add(_locate(af, column, span, text))
        if column in widened and not _is_float(af, column):
            written.add(_widen(af, column, site))
    return written


def _widen(af: ActuarialFrame, column: str, site: SourceSpan | None) -> int:
    """Read a whole-number column as the double the plan's shocks make it, recorded.

    Multiplied by ``1.0``, the step an unshocked scenario's rows take in a
    batch beside a shocked one: the same double for every whole number, so a
    batch of unshocked scenarios answers what a mixed batch answers.
    """
    span = site if site is not None else capture_source_span()
    af[column] = af[column] * 1.0
    return _locate(af, column, span, f"{_operand_text(column)} * 1.0")


def widened_by_the_plan(
    af: ActuarialFrame, scenarios: Mapping[ScenarioID, Sequence[Shock]]
) -> frozenset[str]:
    """Return the whole-number columns some scenario of the run shocks to a decimal.

    A run cut into batches composes each batch's scenarios together, and a
    column one of them shocks takes the type of every branch: ``n * 1.5``
    beside an unshocked ``n`` is a double for every scenario in that batch,
    and ``n`` alone, where no scenario of the batch moves it, is the book's
    whole number. So one scenario's column would be read at two types at two
    batch sizes, and a directory of batch files would hold two. The type is
    the run's instead: a whole-number column any scenario of the plan shocks
    to a double is read as a double in every batch, which every whole number
    up to ``2**53`` is exactly.

    Each distinct shape of shock -- its kinds and the types of its numbers,
    which are all a type follows from -- is composed once and typed against
    the book's schema, reading no row.
    """
    import polars as pl  # noqa: PLC0415 -- dtypes only

    from gaspatchio._shape import _resolve_expr_output_dtype  # noqa: PLC0415 -- cycle

    widened: set[str] = set()
    for column in column_targets(scenarios):
        if _is_float(af, column) or not af.schema.get(column, pl.Null).is_integer():
            continue
        shapes = {
            _shape_of(shocks): shocks
            for shocks in (
                [s for s in shocks if target_of(s) == ("column", column)]
                for shocks in scenarios.values()
            )
            if shocks
        }
        for shocks in shapes.values():
            expr, _ = _composed(af, af[column], _operand_text(column), shocks)
            typed = _resolve_expr_output_dtype(af, af._convert_to_expr(expr))  # noqa: SLF001 -- the door an assignment takes
            if typed is not None and typed.is_float():
                widened.add(column)
                break
    return frozenset(widened)


def _shape_of(value: object) -> object:
    """Return a shock with every number replaced by its type, for its result type."""
    if isinstance(value, bool):
        return bool
    if isinstance(value, (int, float)):
        return type(value)
    if isinstance(value, (list, tuple)):
        return tuple(_shape_of(one) for one in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _shape_of(v)) for k, v in value.items()))
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple((f.name, _shape_of(getattr(value, f.name))) for f in fields(value)),
        )
    return repr(value)


def _locate(af: ActuarialFrame, column: str, span: SourceSpan | None, text: str) -> int:
    """Place the assignment just recorded at the plan's line, its formula the recipe."""
    record = af._calculations[-1]  # noqa: SLF001 -- the record this door wrote
    if not isinstance(record, CalculationRecord) or record.column != column:
        msg = f"the column shock on {column!r} left no record of its assignment"
        raise RuntimeError(msg)
    record.source = (
        None if span is None else replace(span, rhs=text, target_literal=True)
    )
    return id(record)


# One affine step of a column shock: ``x * a + b``, or ``b`` where it sets.
_Step = tuple[float, float, bool]

# The step a scenario that leaves the column alone takes: ``x * 1.0 + -0.0``,
# which is ``x`` exactly for every float, signed zeros and NaN included.
_IDENTITY: Final[_Step] = (1.0, -0.0, False)


def _is_float(af: ActuarialFrame, column: str) -> bool:
    """Return whether ``column`` is a float column; the factor form keeps it float."""
    import polars as pl  # noqa: PLC0415 -- dtypes only

    return af.schema.get(column) in (pl.Float64, pl.Float32)


def _steps_of(shock: Shock) -> list[_Step] | None:
    """Return ``shock`` as affine steps, or None where it is not affine."""
    if isinstance(shock, PipelineShock):
        steps: list[_Step] = []
        for one in shock.shocks:
            inner = _steps_of(one)
            if inner is None:
                return None
            steps += inner
        return steps
    if isinstance(shock, MultiplicativeShock):
        return [(float(shock.factor), -0.0, False)]
    if isinstance(shock, AdditiveShock):
        return [(1.0, float(shock.delta), False)]
    if isinstance(shock, OverrideShock) and isinstance(shock.value, (int, float)):
        return [(0.0, float(shock.value), True)]
    return None


def _affine_steps(
    moved: Mapping[ScenarioID, Sequence[Shock]],
) -> dict[ScenarioID, list[_Step]] | None:
    """Return each moving scenario's steps, or None where any shock is not affine."""
    out: dict[ScenarioID, list[_Step]] = {}
    for sid, shocks in moved.items():
        steps: list[_Step] = []
        for shock in shocks:
            one = _steps_of(shock)
            if one is None:
                return None
            steps += one
        out[sid] = steps
    return out


def _factored(
    af: ActuarialFrame,
    column: str,
    batch: Sequence[ScenarioID],
    steps: Mapping[ScenarioID, Sequence[_Step]],
) -> tuple[Any, str]:
    """Return the column read through per-scenario factors, and the text of it.

    The factors are a table keyed by the scenario axis, the step and the
    part (``a``, ``b``, ``set``), built for this batch's scenarios; a
    scenario that leaves the column alone takes identity steps. It is built
    on the framework's own lifecycle, as a stacked table is, because each
    batch builds it again under the same name after the last was collected.
    """
    import polars as pl  # noqa: PLC0415 -- the factor frame only

    from gaspatchio._table_lifecycle import (  # noqa: PLC0415 -- cycle
        framework_owned_tables,
    )
    from gaspatchio.assumptions import (  # noqa: PLC0415 -- cycle
        DataDimension,
        Table,
    )

    depth = max(len(s) for s in steps.values())
    rows: dict[str, list[object]] = {
        SCENARIO_COLUMN: [],
        "step": [],
        "part": [],
        "value": [],
    }
    for sid in batch:
        own = list(steps.get(sid, ()))
        for k, (a, b, sets) in enumerate(own + [_IDENTITY] * (depth - len(own)), 1):
            for part, value in (("a", a), ("b", b), ("set", 1.0 if sets else 0.0)):
                rows[SCENARIO_COLUMN].append(sid)
                rows["step"].append(str(k))
                rows["part"].append(part)
                rows["value"].append(value)
    name = f"scenario_shocks__{column}"
    with framework_owned_tables():
        factors = Table(
            name=name,
            source=pl.DataFrame(rows),
            dimensions={
                # Labels, never quantities: an axis "001" stays "001".
                SCENARIO_COLUMN: (
                    DataDimension(column=SCENARIO_COLUMN, dtype=pl.String())
                    if all(isinstance(sid, str) for sid in batch)
                    else SCENARIO_COLUMN
                ),
                "step": DataDimension(column="step", dtype=pl.String()),
                "part": DataDimension(column="part", dtype=pl.String()),
            },
            value="value",
            validate=False,
        )
    axis = af[SCENARIO_COLUMN]
    expr: Any = af[column]
    text = _operand_text(column)
    for k in range(1, depth + 1):

        def read(part: str, step: str = str(k)) -> Any:  # noqa: ANN401 -- a lookup
            return factors.lookup(scenario_id=axis, step=step, part=part)

        def said(part: str, step: str = str(k)) -> str:
            return (
                f"{name}.lookup(scenario_id=af.{SCENARIO_COLUMN}, step={step!r}, "
                f"part={part!r})"
            )

        expr = (
            when(read("set") == 1.0)
            .then(read("b"))
            .otherwise(expr * read("a") + read("b"))
        )
        text = (
            f"when({said('set')} == 1.0).then({said('b')})"
            f".otherwise({text} * {said('a')} + {said('b')})"
        )
    return expr, text


def _chain(
    af: ActuarialFrame,
    operand: Any,  # noqa: ANN401 -- a column proxy
    operand_text: str,
    moved: Mapping[ScenarioID, Sequence[Shock]],
) -> tuple[Any, str]:
    """Return the per-scenario ``when`` chain over the axis, and its text."""
    axis = af[SCENARIO_COLUMN]
    chain: Any = None
    texts: list[str] = []
    for sid, shocks in moved.items():
        expr, text = _composed(af, operand, operand_text, shocks)
        condition = axis == sid
        chain = (
            when(condition).then(expr)
            if chain is None
            else chain.when(condition).then(expr)
        )
        texts.append(f"when(af.{SCENARIO_COLUMN} == {sid!r}).then({text})")
    return chain.otherwise(operand), ".".join(texts) + f".otherwise({operand_text})"


def _composed(
    af: ActuarialFrame,
    operand: Any,  # noqa: ANN401 -- a column proxy
    operand_text: str,
    shocks: Sequence[Shock],
) -> tuple[Any, str]:
    """Return one scenario's shocks on the column applied in order, and the text."""
    expr, text = operand, operand_text
    for shock in shocks:
        expr, text = _lowered(af, shock, expr, text)
    return expr, text


def _lowered(  # noqa: PLR0911 -- one branch per shock kind
    af: ActuarialFrame,
    shock: Shock,
    x: Any,  # noqa: ANN401 -- a proxy, an expression proxy or a literal
    xt: str,
) -> tuple[Any, str]:
    """Return ``shock`` applied to ``x`` in the core vocabulary, with its text."""
    if isinstance(shock, MultiplicativeShock):
        return x * shock.factor, f"{xt} * {shock.factor!r}"
    if isinstance(shock, AdditiveShock):
        sign = "-" if shock.delta < 0 else "+"
        return x + shock.delta, f"{xt} {sign} {abs(shock.delta)!r}"
    if isinstance(shock, OverrideShock):
        return shock.value, repr(shock.value)
    if isinstance(shock, ClipShock):
        expr, text = x, xt
        if shock.min_value is not None:
            low = shock.min_value
            expr = when(expr < low).then(low).otherwise(expr)
            text = f"when({text} < {low!r}).then({low!r}).otherwise({text})"
        if shock.max_value is not None:
            high = shock.max_value
            expr = when(expr > high).then(high).otherwise(expr)
            text = f"when({text} > {high!r}).then({high!r}).otherwise({text})"
        return expr, text
    if isinstance(shock, PipelineShock):
        return _composed(af, x, xt, shock.shocks)
    if isinstance(shock, (MaxShock, MinShock)):
        a, at = _lowered(af, shock.shock_a, x, xt)
        b, bt = _lowered(af, shock.shock_b, x, xt)
        keep = ">=" if isinstance(shock, MaxShock) else "<="
        test = (a >= b) if isinstance(shock, MaxShock) else (a <= b)
        return (
            when(test).then(a).otherwise(b),
            f"when({at} {keep} {bt}).then({at}).otherwise({bt})",
        )
    if isinstance(shock, FilteredShock):
        condition, ct = _condition(af, shock.where)
        inner, it = _lowered(af, shock.shock, x, xt)
        return (
            when(condition).then(inner).otherwise(x),
            f"when({ct}).then({it}).otherwise({xt})",
        )
    msg = (
        f"A {type(shock).__name__} cannot move a model-point column: a column "
        "shock is built from multiply, add, set, clip, pipeline, max, min and "
        "where."
    )
    raise ValueError(msg)


_COMPARISONS: Final[dict[str, str]] = {
    "eq": "==",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _condition(af: ActuarialFrame, where: Mapping[str, Any]) -> tuple[Any, str]:
    """Return ``where`` over the model-point columns, joined with AND, and its text."""
    parts: list[tuple[Any, str]] = []
    for column, condition in where.items():
        col, ct = af[column], _operand_text(column)
        if not isinstance(condition, dict):
            parts.append((col == condition, f"{ct} == {condition!r}"))
            continue
        for op, value in condition.items():
            if op in _COMPARISONS:
                symbol = _COMPARISONS[op]
                parts.append((_compare(col, symbol, value), f"{ct} {symbol} {value!r}"))
            elif op == "between":
                low, high = value
                parts.append(
                    (
                        (col >= low) & (col <= high),
                        f"({ct} >= {low!r}) & ({ct} <= {high!r})",
                    )
                )
            elif op == "in":
                parts.append((col.is_in(list(value)), f"{ct}.is_in({list(value)!r})"))
            elif op == "not_in":
                parts.append((~col.is_in(list(value)), f"~{ct}.is_in({list(value)!r})"))
            else:
                msg = f"Unknown filter operator: {op}"
                raise ValueError(msg)
    expr, text = parts[0]
    for more, more_text in parts[1:]:
        expr = expr & more
        text = f"({text}) & ({more_text})"
    return expr, text


def _compare(col: Any, symbol: str, value: object) -> Any:  # noqa: ANN401 -- proxies
    """Return ``col <symbol> value`` through the proxy's own operators."""
    if symbol == "==":
        return col == value
    if symbol == "!=":
        return col != value
    if symbol == ">":
        return col > value
    if symbol == ">=":
        return col >= value
    if symbol == "<":
        return col < value
    return col <= value


def _operand_text(column: str) -> str:
    """Return how a model refers to ``column``: ``af.name`` or ``af['name']``."""
    return f"af.{column}" if column.isidentifier() else f"af[{column!r}]"


__all__ = [
    "check_columns",
    "check_columns_read",
    "column_targets",
    "columns_the_folds_read",
    "shock_columns",
    "widened_by_the_plan",
]
