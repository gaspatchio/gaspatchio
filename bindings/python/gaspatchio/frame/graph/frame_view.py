# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The frame state graph inspection consumes, independent of model execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from weakref import ReferenceType

    import polars as pl

    from gaspatchio.engines.report import RunSummary
    from gaspatchio.frame.calculations import LogEntry, SelectionRecord
    from gaspatchio.frame.plan_writes import Origin


class GraphSource(Protocol):
    """Expose the calculation log, arrivals and completed values to inspection.

    The exporter may release retained superseded values. Those two mutable fields
    are explicit; all other state is read from the frame that owns it.
    """

    _retained_values: pl.DataFrame | None
    _retained_for: ReferenceType[pl.DataFrame] | None

    @property
    def _calculations(self) -> Sequence[LogEntry]: ...

    @property
    def _selections(self) -> Sequence[SelectionRecord]: ...

    @property
    def _df(self) -> pl.LazyFrame | None: ...

    @property
    def _schema(self) -> Mapping[str, pl.DataType] | None: ...

    @property
    def _column_order(self) -> Sequence[str]: ...

    @property
    def _arrival_names(self) -> frozenset[str]: ...

    @property
    def _arrival_schema(self) -> Mapping[str, pl.DataType]: ...

    @property
    def _bare_arrivals(self) -> frozenset[str]: ...

    @property
    def _arrival_data(self) -> pl.LazyFrame | None: ...

    @property
    def _initial_columns(self) -> frozenset[str]: ...

    @property
    def _rebuilt(self) -> Mapping[str, Origin]: ...

    @property
    def _schema_generation(self) -> int: ...

    @property
    def _collected_values(self) -> pl.DataFrame | None: ...

    @property
    def _last_run(self) -> RunSummary | None: ...

    @property
    def columns(self) -> list[str]:
        """Read the model's current column names."""
        ...

    def _unaccounted_columns(self) -> frozenset[str]: ...
