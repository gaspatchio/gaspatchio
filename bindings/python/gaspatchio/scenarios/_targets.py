# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Shock-target checks: a shock names one table or one model-point column.
# ABOUTME: Untargeted, doubly-targeted, unknown or period-bound column shocks refuse.

"""What a shock in a scenario plan is allowed to point at, checked before it runs.

A shock names exactly one target. ``table=`` is an assumption table the
model reads, by the name the ``Table`` was built with: inside a run, the
model's read of that table is lowered against it shocked for the run's
scenarios. ``column=`` is a model-point column -- a valuation rate, an
expense, a solved premium -- rewritten per scenario at the frame door before
the model runs. A shock naming neither would have to guess what it moves, and
one naming both would move one of them silently, so each is refused here,
naming the next thing to write. ``Table.with_shock()`` applies one shock to
one table, which is then its target.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, Literal

from gaspatchio.scenarios.shocks import FilteredShock, Shock, TimeConditionalShock

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    import polars as pl

    from gaspatchio.assumptions import Table

TargetKind = Literal["table", "column"]


def _names(names: Sequence[str]) -> str:
    """Return ``names`` quoted and comma-joined, or a phrase for none."""
    return ", ".join(repr(n) for n in names) if names else "none"


def did_you_mean(name: str, candidates: Sequence[str]) -> str:
    """Return a `` Did you mean 'x'?`` clause, or an empty string."""
    close = get_close_matches(name, list(candidates), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def inner_shocks(shock: Shock) -> Iterator[Shock]:
    """Yield the shocks nested inside ``shock`` (pipeline steps, wrapped shocks)."""
    if not is_dataclass(shock):
        return
    for fld in fields(shock):
        val = getattr(shock, fld.name)
        if isinstance(val, Shock):
            yield val
        elif isinstance(val, (tuple, list)):
            yield from (v for v in val if isinstance(v, Shock))


def target_of(shock: Shock) -> tuple[TargetKind, str] | None:
    """Return the one target ``shock`` names, or None where it names none or two."""
    if shock.table is not None and shock.column is None:
        return ("table", shock.table)
    if shock.column is not None and shock.table is None:
        return ("column", shock.column)
    return None


def _checked_target(
    who: str, shock: Shock, held: Sequence[str]
) -> tuple[TargetKind, str]:
    """Return the target ``shock`` names, refusing none or two."""
    target = target_of(shock)
    if target is not None:
        return target
    if shock.table is not None and shock.column is not None:
        msg = (
            f"{who} holds a shock naming two targets, table={shock.table!r} "
            f"and column={shock.column!r} ({_what_it_does(shock)}). A shock moves "
            "exactly one thing.\nTo move only some rows of the table, wrap the "
            f"shock: FilteredShock(shock=..., where={{...}}, table={shock.table!r}). "
            "To move a model-point column, drop table=."
        )
        raise ValueError(msg)
    tables = f"table= one of {_names(held)}" if held else "table= an assumption table"
    msg = (
        f"{who} holds a shock that names no target ({shock.describe()}). A "
        "shock moves exactly what it names, and one naming nothing would have "
        "to guess.\n"
        f"Name it with {tables} the model reads (the name its Table was built "
        "with), or column= a model-point column such as a valuation rate."
    )
    raise ValueError(msg)


# The fields a shock names its target with.
_TARGETS = ("table", "column")


def _what_it_does(shock: Shock) -> str:
    """Return what ``shock`` does, without the targets it names.

    A shock describes itself with its target, and two targets read as one
    dotted name -- "multiply to mortality.disc_rate" -- naming a column of a
    table that the two fields do not mean. The refusal names both fields
    itself, so the description says only the operation.
    """
    if not is_dataclass(shock):
        return shock.describe()
    targets = {field.name: None for field in fields(shock) if field.name in _TARGETS}
    return replace(shock, **targets).describe()


def _named(shock: Shock) -> str:
    """Return the target fields ``shock`` sets, as written."""
    parts = [
        f"{field}={value!r}"
        for field, value in (("table", shock.table), ("column", shock.column))
        if value is not None
    ]
    return ", ".join(parts)


def _check_inner(who: str, outer: Shock, target: tuple[TargetKind, str]) -> None:
    """Refuse a nested shock naming a different target than its outer shock."""
    kind, name = target
    for inner in inner_shocks(outer):
        names_one = inner.table is not None or inner.column is not None
        if names_one and target_of(inner) != target:
            msg = (
                f"{who} holds {type(outer).__name__} on {kind} {name!r} whose "
                f"inner {type(inner).__name__} names {_named(inner)}. The outer "
                "shock's target is the one moved, so the inner target would be "
                f"ignored.\nGive the inner shock {kind}={name!r} or no target, "
                "or make it a shock of its own."
            )
            raise ValueError(msg)
        _check_inner(who, inner, target)


def _refuse_periods(who: str, shock: Shock, column: str) -> None:
    """Refuse a time condition anywhere in a shock on a model-point column."""
    stack = [shock]
    while stack:
        one = stack.pop()
        if isinstance(one, TimeConditionalShock):
            msg = (
                f"{who} shocks model-point column {column!r} with "
                f"TimeConditionalShock ({shock.describe()}). A model-point column "
                "holds one value per policy, with no periods for when= to choose "
                "among, so the shock would move every period or none.\n"
                "Shock a table keyed by time with table= instead, or drop when=."
            )
            raise ValueError(msg)  # noqa: TRY004 -- a target the shock cannot move
        stack.extend(inner_shocks(one))


def check_shock_targets(
    scenarios: Mapping[Any, Sequence[object]],
    base_tables: Mapping[str, Table] | None,
) -> None:
    """Refuse any shock whose target the run would not honour.

    Every shock names exactly one target: ``table=`` an assumption table, or
    ``column=`` a model-point column. A nested shock (a pipeline step, the
    shock a filter wraps) may repeat its outer shock's target or name none,
    never another. A shock on a model-point column holds no time condition.
    Where ``base_tables`` are given, a table target is one of them: they are
    the plan's statement of the tables it shocks, checked against the model's
    own by content when it runs.

    Raises:
        TypeError: A scenario holds something other than a ``Shock``.
        ValueError: A shock names no target, two targets, a table the plan's
            ``base_tables`` do not hold, or a time condition on a column.

    """
    held = sorted(base_tables or {})
    for sid, shocks in scenarios.items():
        for shock in shocks:
            if not isinstance(shock, Shock):
                msg = (
                    f"Scenario {sid!r} holds {type(shock).__name__}, which is "
                    "not a shock; a shocks-dict scenario is a list of Shock "
                    "objects (MultiplicativeShock, AdditiveShock, ...). A scalar "
                    "is shocked as a model-point column: "
                    "AdditiveShock(0.01, column='valuation_rate')."
                )
                raise TypeError(msg)
            who = f"Scenario {sid!r}"
            kind, name = _checked_target(who, shock, held)
            _check_inner(who, shock, (kind, name))
            if kind == "column":
                _refuse_periods(who, shock, name)
            elif base_tables and name not in base_tables:
                msg = (
                    f"Scenario {sid!r} shocks table {name!r}, but the plan's "
                    f"base_tables hold no table by that name, so the shock "
                    f"would move nothing and the scenario would equal BASE."
                    f"{did_you_mean(name, held)}\n"
                    f"The tables this plan states it shocks: {_names(held)}."
                )
                raise ValueError(msg)


def check_shock_applies_to(shock: Shock, table: Table, origin: str | None) -> None:
    """Refuse a shock handed straight to one table that it would not honour.

    The table it is applied to is the target, so a shock naming no table is
    fine. A ``table=`` naming another table is refused, naming both: the shock
    was written for that table and would move this one. ``column=`` names a
    model-point column, which a table does not hold, so it is refused too.
    ``origin`` is the table a shocked copy was shocked from; a shock may name
    either. Nested shocks follow the same rules.

    Raises:
        ValueError: The shock (or a shock nested in it) names a different
            table, or a column.

    """
    name = table.name
    accepted = (name,) if origin is None else (name, origin)
    who = "A shock applied to one table (Table.with_shock or Table.from_shocks)"
    stack = [shock]
    while stack:
        one = stack.pop()
        if one.column is not None:
            msg = (
                f"{who} names column={one.column!r} ({one.describe()}), and "
                "column= names a model-point column, which a table does not "
                f"hold. A shock applied to {name!r} moves its value column.\n"
                "Drop column=, or put the shock in a scenario plan to move that "
                "model-point column."
            )
            raise ValueError(msg)
        if one.table is not None and one.table not in accepted:
            copy_of = f" (a shocked copy of {origin!r})" if origin is not None else ""
            msg = (
                f"{who} names table {one.table!r} but is applied to table "
                f"{name!r}{copy_of}, so it would move a table it was not "
                f"written for.\nApply it to {one.table!r}, or give it "
                f"table={name!r} or no table= (the table it is applied to is "
                "then its target)."
            )
            raise ValueError(msg)
        stack.extend(inner_shocks(one))


def _condition_of(shock: Shock) -> tuple[str, Mapping[str, Any]] | None:
    """Return a conditional shock's keyword and condition, or None for any other."""
    if isinstance(shock, FilteredShock):
        return "where", shock.where
    if isinstance(shock, TimeConditionalShock):
        return "when", shock.when
    return None


# How many distinct labels a refusal quotes before it counts the rest.
_LABELS_SHOWN = 12


def _number(value: object) -> str:
    """Return a key as a person writes it: a whole float without its ``.0``."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value)


def _held_values(rows: pl.DataFrame, column: str) -> str:
    """Return what ``column`` of a table holds, as a refusal names it."""
    values = rows.get_column(column).drop_nulls()
    if values.is_empty():
        return f"{column!r} holds no value"
    if values.dtype.is_numeric():
        low, high = _number(values.min()), _number(values.max())
        if low == high:
            return f"{column!r} holds {low}"
        return f"{column!r} holds {low} to {high}"
    labels = sorted({repr(v) for v in values.unique().to_list()})
    shown = ", ".join(labels[:_LABELS_SHOWN])
    extra = len(labels) - _LABELS_SHOWN
    more = f" and {extra} more" if extra > 0 else ""
    return f"{column!r} holds {shown}{more}"


def check_conditions_select(
    who: str, shock: Shock, table: str, rows: pl.DataFrame
) -> None:
    """Refuse a condition that names a column the table lacks, or selects no row of it.

    A ``FilteredShock``'s ``where=`` and a ``TimeConditionalShock``'s ``when=``
    are read against the rows of the table the shock moves -- its own key
    columns, not the model's projection time. A condition on a column the
    table does not hold cannot be read; one that selects no row moves
    nothing, so the scenario would equal BASE. Each is refused here, naming
    the condition, what the table holds and the next move, as a shock on a
    table no read reached is. A shock that selects rows and leaves them as
    they were (a cap that binds nowhere) is a real scenario and is not asked
    about. Nested shocks are checked the same way.

    Raises:
        ValueError: A condition names a column ``rows`` lacks, or selects
            none of its rows.

    """
    from gaspatchio.scenarios.shocks import (  # noqa: PLC0415 -- private helper
        _build_filter_expr,
    )

    stack = [shock]
    while stack:
        one = stack.pop()
        stack.extend(inner_shocks(one))
        found = _condition_of(one)
        if found is None:
            continue
        keyword, condition = found
        said = f"{type(one).__name__} {keyword}={dict(condition)!r}"
        missing = [c for c in condition if c not in rows.columns]
        if missing:
            time_hint = (
                " A when= condition reads the table's own key columns, not "
                "the model's projection time."
                if keyword == "when"
                else ""
            )
            msg = (
                f"{who} shocks table {table!r} with {said}, but {table!r} has no "
                f"column {missing[0]!r}.{did_you_mean(missing[0], rows.columns)}"
                f"{time_hint}\n{table!r} holds: {_names(rows.columns)}. Write the "
                f"condition on a column {table!r} holds."
            )
            raise ValueError(msg)
        if rows.filter(_build_filter_expr(dict(condition))).height:
            continue
        held = "; ".join(_held_values(rows, c) for c in condition)
        msg = (
            f"{who} shocks table {table!r} with {said}, but no row of {table!r} "
            "meets the condition, so the shock moves nothing and the scenario "
            f"would equal BASE.\nIn {table!r}, {held}. Write the condition on "
            "values the table holds, or drop the shock."
        )
        raise ValueError(msg)


__all__ = [
    "TargetKind",
    "check_conditions_select",
    "check_shock_applies_to",
    "check_shock_targets",
    "did_you_mean",
    "inner_shocks",
    "target_of",
]
