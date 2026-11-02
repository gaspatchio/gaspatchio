# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: A run's binding of its table shocks to the model's own reads of those tables.
# ABOUTME: Stacked per batch with the axis as a key, or shocked alone for one scenario.

"""How a scenario plan reaches the reads of the tables its shocks name.

The model the plan runs is the one the modeller reconciled: it loads its own
tables and reads them, and it has no door for the plan to come in through.
So the plan comes in at the read. While a batch is composed, every
``Table.lookup`` and ``MortalityTable.at`` the model makes is offered to a
:class:`TableBinder`. A read of a table no shock names is left exactly as the
model wrote it. A read of a table a shock names is lowered against that
table stacked for the batch's scenarios, with the injected scenario axis as
its leading key -- byte for byte the read a model handed the stacked table by
hand would have made. One scenario composed on its own reads the table
shocked for that scenario alone, with no axis, which is what lets BASE be
the reconciled model and its fingerprint the standalone model's.

The binding is declared and strict, never inferred. Only a name a shock
states is rebound; a shock whose table no read reached is refused after the
first batch, naming the tables the model did read; a read whose frame has
dropped the scenario axis is refused at the line that made it; and where the
plan states its ``base_tables``, a model table that differs from the stated
one by content is refused rather than shocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gaspatchio._semantic.ir import Col
from gaspatchio._table_lifecycle import framework_owned_tables
from gaspatchio.frame.lowering.context import context_for_operands
from gaspatchio.scenarios._stack import shocked_table, stack_shocked_table
from gaspatchio.scenarios._targets import did_you_mean, target_of
from gaspatchio.scenarios._with_scenarios import SCENARIO_COLUMN

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from gaspatchio.assumptions import Table
    from gaspatchio.assumptions._data import TableData
    from gaspatchio.frame import ActuarialFrame
    from gaspatchio.scenarios.shocks import Shock

ScenarioID = str | int


def table_targets(scenarios: Mapping[ScenarioID, Sequence[Shock]]) -> list[str]:
    """Return every table the run's shocks name, in the order they first appear."""
    found: dict[str, None] = {}
    for shocks in scenarios.values():
        for shock in shocks:
            target = target_of(shock)
            if target is not None and target[0] == "table":
                found.setdefault(target[1])
    return list(found)


def _shocks_on(shocks: Sequence[Shock], name: str) -> list[Shock]:
    """Return the shocks in ``shocks`` that move table ``name``, in order."""
    return [s for s in shocks if target_of(s) == ("table", name)]


@dataclass
class TableBinder:
    """What one composition answers for the model's reads of its tables.

    ``shocks`` holds, per table a shock names, each composed scenario's
    shocks on it (an empty list where that scenario leaves it alone).
    ``stacked`` is True for a batch, which reads every such table stacked
    with the scenario axis as a key, and False for one scenario composed on
    its own, which reads the table shocked for it with no axis.
    """

    shocks: dict[str, dict[ScenarioID, list[Shock]]]
    stacked: bool
    checks: Mapping[str, Table] = field(default_factory=dict)
    read: dict[str, None] = field(default_factory=dict)
    reached: dict[str, TableData] = field(default_factory=dict)
    _built: dict[tuple[str, str | None], TableData] = field(default_factory=dict)
    _checked: set[tuple[str, str | None]] = field(default_factory=set)

    @classmethod
    def for_batch(
        cls,
        scenarios: Mapping[ScenarioID, Sequence[Shock]],
        batch_sids: Sequence[ScenarioID],
        checks: Mapping[str, Table] | None,
    ) -> TableBinder:
        """Return the binder for one batch: every table the run shocks, stacked.

        A table only another batch's scenarios shock is stacked here too, with
        the base rows under each of this batch's scenarios, so every batch
        reads the same tables the same way whatever the memory search cut.
        """
        return cls(
            shocks={
                name: {sid: _shocks_on(scenarios[sid], name) for sid in batch_sids}
                for name in table_targets(scenarios)
            },
            stacked=True,
            checks=checks or {},
        )

    @classmethod
    def for_alone(
        cls,
        scenarios: Mapping[ScenarioID, Sequence[Shock]],
        sid: ScenarioID,
        checks: Mapping[str, Table] | None,
    ) -> TableBinder:
        """Return the binder for one scenario alone: only its own tables, shocked."""
        own = {sid: list(scenarios[sid])}
        return cls(
            shocks={
                name: {sid: _shocks_on(own[sid], name)} for name in table_targets(own)
            },
            stacked=False,
            checks=checks or {},
        )

    def rebind(
        self, table: TableData, dimensions: Mapping[str, object]
    ) -> tuple[TableData, dict[str, object]] | None:
        """Return the table and keys this read lowers against, or None to leave it.

        Raises:
            ValueError: The plan states this table in ``base_tables`` with
                other content, or the read's frame has dropped the scenario
                axis a stacked table is keyed by.

        """
        name = table.name
        self.read.setdefault(name)
        per_scenario = self.shocks.get(name)
        if per_scenario is None:
            return None
        self._cross_check(table)
        self.reached.setdefault(name, table)
        key = (name, table._registered_sha)  # noqa: SLF001 -- the content read
        built = self._built.get(key)
        if built is None:
            # Built per composition and collected (or discarded) before the
            # next one rebuilds it under the same name: the framework's own.
            with framework_owned_tables():
                built = (
                    stack_shocked_table(table, per_scenario)  # type: ignore[arg-type]
                    if self.stacked
                    else _shocked_alone(table, per_scenario)
                )
            self._built[key] = built
        if not self.stacked:
            return built, dict(dimensions)
        self._refuse_a_dropped_axis(name, dimensions)
        return built, {**dimensions, SCENARIO_COLUMN: Col(SCENARIO_COLUMN)}

    def refuse_frame_read(self, table: TableData) -> None:
        """Refuse reading the rows of a table a shock in this run moves.

        Raises:
            ValueError: ``table`` is one a shock in this run names.

        """
        if table.name not in self.shocks:
            return
        msg = (
            f"{table.name}.to_dataframe() was read inside a scenario run that "
            f"shocks {table.name!r}, so its rows differ by scenario and the "
            "base rows handed back here would be BASE's alone -- a setup step "
            "built on them would put BASE's numbers into every scenario.\n"
            f"Read {table.name!r} through lookup() (or MortalityTable.at()), "
            "which the run answers per scenario, or take its rows before the "
            "run starts."
        )
        raise ValueError(msg)

    def _cross_check(self, table: TableData) -> None:
        """Refuse a model table that differs by content from the one the plan states."""
        name = table.name
        stated = self.checks.get(name)
        key = (name, table._registered_sha)  # noqa: SLF001 -- the content read
        if stated is None or key in self._checked:
            return
        model_sha, stated_sha = table.fingerprint(), stated.fingerprint()  # type: ignore[attr-defined]
        if model_sha != stated_sha:
            msg = (
                f"The plan states base table {name!r} holding {stated_sha}, but "
                f"the model read {name!r} holding {model_sha}, so the table the "
                "plan says it shocks is not the table the model reads.\n"
                "Pass the model's own table in base_tables, or leave base_tables "
                "out: the plan shocks whatever table the model reads under that "
                "name, and the run record names its content."
            )
            raise ValueError(msg)
        self._checked.add(key)

    @staticmethod
    def _refuse_a_dropped_axis(name: str, dimensions: Mapping[str, object]) -> None:
        """Refuse a read of a stacked table from a frame that no longer has the axis."""
        ctx = context_for_operands(dimensions.values())
        frame: Any = None if ctx is None else ctx.frame
        if frame is None or SCENARIO_COLUMN in frame.columns:
            return
        msg = (
            f"A read of {name!r}, which this scenario run shocks, came from a "
            f"frame that no longer carries the {SCENARIO_COLUMN!r} column the run "
            "cross-joined on, so the read cannot be told which scenario each "
            "row is in.\nKeep the scenario axis on the frame through the model: "
            "a select, a group_by or a frame rebuilt from a subset of columns "
            f"drops it. Carry {SCENARIO_COLUMN!r} along."
        )
        raise ValueError(msg)

    def check_reached(self, scenarios: Mapping[ScenarioID, Sequence[Shock]]) -> None:
        """Refuse a shock whose table no read of the model reached.

        Raises:
            ValueError: A scenario shocks a table the model never read; that
                scenario would equal BASE.

        """
        for sid, shocks in scenarios.items():
            for shock in shocks:
                target = target_of(shock)
                if target is None or target[0] != "table":
                    continue
                if target[1] in self.reached:
                    continue
                raise ValueError(_unread_message(sid, target[1], list(self.read)))

    def built_names(self) -> set[str]:
        """Return the names of the tables this binder lowered reads against."""
        return {table.name for table in self._built.values()}

    def read_as(self) -> dict[str, str]:
        """Return each shocked copy's name with the name of the table it copies.

        A scenario composed alone reads its shocked table through a copy
        registered under ``<name>_shocked``, so the base stays registered
        under its own name for every other read. The copy's name is a
        registry's convenience, not the model's: the scenario's record reads
        it back as the table the model named. Empty for a batch's binder,
        whose stacked table carries the scenario axis no model wrote.
        """
        if self.stacked:
            return {}
        return {built.name: name for (name, _), built in self._built.items()}

    def bases(self) -> dict[str, dict[str, Any]]:
        """Return, per shocked table, the content it was applied to and its file."""
        return {
            name: {
                "fingerprint": table.fingerprint(),  # type: ignore[attr-defined]
                "source_file": _recorded_path(table._source_file),  # noqa: SLF001
            }
            for name, table in sorted(self.reached.items())
        }


def _shocked_alone(
    table: TableData, per_scenario: Mapping[ScenarioID, list[Shock]]
) -> TableData:
    """Return ``table`` shocked for the one scenario composed on its own."""
    ((sid, shocks),) = per_scenario.items()
    return shocked_table(table, shocks, scenario=sid)  # type: ignore[arg-type]


def _unread_message(sid: ScenarioID, name: str, read: Iterable[str]) -> str:
    """Return the refusal for a shock on a table no read reached."""
    names = list(read)
    if names:
        what = ", ".join(repr(n) for n in names)
        seen = f"The model read: {what}.{did_you_mean(name, names)}"
    else:
        seen = (
            "The model read no assumption table through Table.lookup() or "
            "MortalityTable.at(), so no table shock can reach it."
        )
    return (
        f"Scenario {sid!r} shocks table {name!r}, but no read in the model "
        f"reached a table by that name, so the scenario would equal BASE.\n"
        f"{seen} A shock names a table by the name its Table was built with; "
        "correct the name, or drop the shock."
    )


def _recorded_path(path: Path | None) -> str | None:
    """Return ``path`` as the run record writes it: relative where it can be."""
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return f"<{Path(path).name}>"


def reads_the_axis(
    projected: ActuarialFrame, *, bound: set[str], plans_own: set[int]
) -> bool:
    """Return whether the model's own calculations read the scenario axis.

    A model that dispatches on ``scenario_id`` -- picking a rate curve per
    scenario, say -- calculates something different under each scenario
    even where nothing is shocked, so the axis is part of what each
    scenario folded. The plan's own reads of it are left out: the axis
    operand it binds into a read of a table it stacked (``bound``), and
    the ``when`` chains its column shocks wrote (``plans_own``).
    """
    from gaspatchio.frame.calculations import (  # noqa: PLC0415 -- cycle
        CalculationRecord,
    )

    for entry in projected._calculations:  # noqa: SLF001 -- the batch record
        if not isinstance(entry, CalculationRecord) or id(entry) in plans_own:
            continue
        if _node_reads_the_axis(entry.node, bound):
            return True
    return False


def _node_reads_the_axis(node: object, bound: set[str]) -> bool:
    """Return whether ``node`` reads ``scenario_id`` other than through a bound read."""
    from gaspatchio._semantic.ir import (  # noqa: PLC0415 -- cycle
        BinOp,
        Call,
        EngineNative,
        WhenThen,
    )

    axis = Col(SCENARIO_COLUMN)
    stack = [node]
    while stack:
        one = stack.pop()
        if one == axis:
            return True
        if isinstance(one, EngineNative) and SCENARIO_COLUMN in one.deps:
            return True
        if isinstance(one, Call):
            args = one.args
            if dict(one.attrs).get("table") in bound:
                args = tuple(arg for arg in args if arg != axis)
            stack.extend(args)
        elif isinstance(one, BinOp):
            stack.extend((one.left, one.right))
        elif isinstance(one, WhenThen):
            stack.extend((one.cond, one.then, one.otherwise))
    return False


def keeps_the_axis(projected: ActuarialFrame) -> None:
    """Refuse a model whose returned frame dropped the scenario axis.

    Raises:
        ValueError: ``projected`` has no ``scenario_id`` column, so no
            scenario's rows could be folded apart.

    """
    if SCENARIO_COLUMN in projected.columns:
        return
    msg = (
        f"The model returned a frame without the {SCENARIO_COLUMN!r} column the "
        "run cross-joined on, so no scenario's rows can be folded apart from "
        "another's.\nKeep the scenario axis on the frame the model returns: a "
        "select, a group_by or a frame rebuilt from a subset of columns drops "
        f"it. Carry {SCENARIO_COLUMN!r} along."
    )
    raise ValueError(msg)


__all__ = ["TableBinder", "keeps_the_axis", "reads_the_axis", "table_targets"]
