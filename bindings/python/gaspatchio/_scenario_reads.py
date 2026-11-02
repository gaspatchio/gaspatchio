# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where a scenario plan meets a read of a table it shocks.

A scenario plan names its targets: ``MultiplicativeShock(1.2,
table="mortality_select")`` says *this* table moves. The model the plan runs
is the one the modeller reconciled, and it reads its own tables. So inside a
run, a read of a table a shock names is lowered against that table shocked
for the scenarios being run -- stacked with the scenario axis as a key where
a batch carries several, or shocked alone where one scenario is composed on
its own -- and every other read is left exactly as the model wrote it.

The rebinding is declared, never inferred: only a table named by a shock in
the plan is rebound, and the plan refuses a target no read reached. That is
what keeps a read rebound by name on the right side of *Sharp knives, no
magic*.

It lives apart from both packages that use it, as
:mod:`gaspatchio._table_lifecycle` does: the assumption table and the
mortality wrapper ask it, the scenario run sets it, and each already imports
the other's neighbourhood.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from gaspatchio.assumptions._data import TableData


class ReadBinder(Protocol):
    """What a scenario run answers for a read of one of the model's tables."""

    def rebind(
        self, table: TableData, dimensions: Mapping[str, object]
    ) -> tuple[TableData, dict[str, object]] | None:
        """Return the table and keys this read lowers against, or None to leave it."""
        ...

    def refuse_frame_read(self, table: TableData) -> None:
        """Refuse reading the rows of a table whose rows differ by scenario."""
        ...


_BINDER: ContextVar[ReadBinder | None] = ContextVar("scenario_reads", default=None)


@contextmanager
def bound_reads(binder: ReadBinder) -> Iterator[None]:
    """Answer every table read made inside this block through ``binder``."""
    token = _BINDER.set(binder)
    try:
        yield
    finally:
        _BINDER.reset(token)


def rebound_read(
    table: TableData, dimensions: Mapping[str, object]
) -> tuple[TableData, dict[str, object]] | None:
    """Return what a read of ``table`` lowers against inside a run; None outside one."""
    binder = _BINDER.get()
    if binder is None:
        return None
    return binder.rebind(table, dimensions)


def check_frame_read(table: TableData) -> None:
    """Refuse ``table.to_dataframe()`` inside a run that shocks ``table``."""
    binder = _BINDER.get()
    if binder is not None:
        binder.refuse_frame_read(table)


__all__ = ["ReadBinder", "bound_reads", "check_frame_read", "rebound_read"]
