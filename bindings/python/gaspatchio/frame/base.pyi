# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable, Iterable
from typing import Any, Concatenate, Self
from weakref import ReferenceType

import polars as pl

from gaspatchio._semantic.ir import OpNode

# ADDED: Import accessor types (use forward references if needed initially)
from gaspatchio.accessors.date import DateFrameAccessor
from gaspatchio.accessors.excel import ExcelFrameAccessor
from gaspatchio.accessors.finance import FinanceFrameAccessor
from gaspatchio.accessors.projection_frame import ProjectionFrameAccessor

# ADDED: Import ExpressionProxy for method return types
from gaspatchio.column import ColumnProxy, ConditionExpression, ExpressionProxy
from gaspatchio.engines.report import RunSummary
from gaspatchio.typing import IntoExprColumn

# ADDED: Import the durable calculation log's record vocabulary
from .calculation_log import _RunScan
from .calculations import (
    BoundaryRecord,
    CalculationRecord,
    LogEntry,
    MintedColumns,
    OverwriteRecord,
    RecordOrigin,
    SelectionRecord,
    SourceSpan,
    StructuralOperation,
)
from .graph.calc_graph import GraphFrameAccessor
from .plan_writes import Origin, PlanReading

# The module's other helpers are only ever reached through the frame, so the
# stub leaves them out. This one is also asked about a dtype on its own, for
# the nestings Polars declines to build a Series over.
def _holds_python_objects(dtype: pl.DataType) -> bool: ...

# And this one is asked for on its own by the calculation graph, which drops
# the rollforward kernel's scratch columns from a record's references and
# reads the prefix from here rather than repeating it.
def _kernel_scratch_prefix() -> str: ...

# And this one by the accessor registry, which refuses a frame accessor under
# a name the class already carries and says which class attribute would have
# hidden it -- in the same sentence the frame's own assignment refusal uses,
# read from here rather than written twice.
def _frame_attribute_kind(name: str, attribute: object) -> str: ...

# And this one by the command line and the batched runs, which build the
# frame a model runs over from the book they were handed, and so do not ask
# which of its columns another frame calculated.
def _frame_over_the_book(
    data: pl.DataFrame | pl.LazyFrame,
    *,
    mode: str | None = None,
    retain_superseded: bool = True,
    judged: bool = False,
) -> ActuarialFrame: ...

class _AggregationResult:
    _df: pl.DataFrame

    def __init__(self, df: pl.DataFrame) -> None: ...
    def __getitem__(self, key: str) -> Any: ...  # noqa: ANN401 -- one cell, of whatever dtype the column holds, read for arithmetic (`af.max()["premium"] * 2`); Polars types the same read, DataFrame.item(), as Any
    @property
    def to_frame(self) -> pl.DataFrame: ...

class MaxResult(_AggregationResult): ...
class MinResult(_AggregationResult): ...
class MeanResult(_AggregationResult): ...
class StdResult(_AggregationResult): ...
class VarResult(_AggregationResult): ...
class MedianResult(_AggregationResult): ...
class SumResult(_AggregationResult): ...
class CountResult(_AggregationResult): ...
class ProductResult(_AggregationResult): ...
class QuantileResult(_AggregationResult): ...

class ActuarialFrame:
    _df: pl.LazyFrame | None
    _column_order: list[str]
    _schema: dict[str, pl.DataType] | None
    # Bumped on every query-plan swap, which is how a reader of the frame
    # tells that its schema moved without a calculation being recorded.
    _schema_generation: int
    _mode: str
    _verbose: bool
    _threads: int
    _show_query_plan: bool
    _traced_run: bool
    # ADDED: the durable calculation log and its attribution cursor
    _calculations: list[LogEntry]
    _selections: list[SelectionRecord]
    _calculation_counts: dict[str, int]
    _next_operation_id: int
    _window_start: int
    _baseline_df: pl.LazyFrame | None
    _initial_columns: frozenset[str]
    _arrival_names: frozenset[str]
    _bare_arrivals: frozenset[str]
    _arrival_schema: dict[str, pl.DataType]
    _arrival_data: pl.LazyFrame | None
    _book_columns: frozenset[str] | None
    # ADDED: the columns the frame arrived holding that another frame
    # calculated, with the definition each one's values came from
    _rebuilt: dict[str, Origin]
    # ADDED: what a collect set aside of the definitions a later write
    # replaced, the tie to the rows it read them from, and the hidden names
    # the plan carries them under
    _retained_values: pl.DataFrame | None
    _retained_for: ReferenceType[pl.DataFrame] | None
    _collected_values: pl.DataFrame | None
    _last_run: RunSummary | None
    _retained_columns: set[str]
    _retain_superseded: bool
    # where in the calculation log each compiled rollforward's struct went on
    _rollforward_runs: dict[str, int]
    # the plan a write past the doors left, read, under its generation
    _plan_reading: tuple[int, PlanReading] | None
    # the reads a state's increments and captures handed out, by node identity
    _held_reads: dict[int, tuple[OpNode, str]]
    # how far the log has been read for each run, and each record's columns
    _rollforward_scans: dict[str, _RunScan]
    _record_roots: dict[int, tuple[CalculationRecord, frozenset[str]]]
    # ADDED: Accessor instance cache stubs
    _date_accessor_instance: DateFrameAccessor | None
    _finance_accessor_instance: FinanceFrameAccessor | None
    _excel_accessor_instance: ExcelFrameAccessor | None
    _projection_accessor_instance: ProjectionFrameAccessor | None
    _graph_accessor_instance: GraphFrameAccessor | None
    # ADDED: attribute-eligible column set
    _attr_columns_set: set[str]

    def __init__(
        self,
        data: pl.LazyFrame | pl.DataFrame | dict[str, Any] | None = None,
        mode: str | None = None,
        verbose: bool | None = None,
        threads: int | None = None,
        *,
        continue_from: ActuarialFrame | None = None,
        retain_superseded: bool = True,
    ) -> None: ...
    def __getitem__(self, key: str) -> ColumnProxy: ...
    def __setitem__(self, key: str, value: object) -> None: ...
    def __getattr__(self, name: str) -> ColumnProxy: ...
    def __setattr__(self, name: str, value: object) -> None: ...
    def __dir__(self) -> list[str]: ...
    def _convert_to_expr(self, value: object) -> pl.Expr: ...
    def _set_plan(self, new_df: pl.LazyFrame | None) -> None: ...
    def _refuse_a_door_past_a_break(self, door: str) -> None: ...
    def _calculation_records(self) -> list[CalculationRecord]: ...
    def _live_entries(self) -> dict[str, CalculationRecord | OverwriteRecord]: ...
    def _attribution_ops(self) -> list[CalculationRecord]: ...
    def _unaccounted_columns(self) -> frozenset[str]: ...
    def _for_an_engine(self) -> tuple[dict[str, Any], pl.DataFrame]: ...
    def _carry_calculation_log(
        self,
        successor: ActuarialFrame,
        minted: MintedColumns | None = None,
        *,
        boundary: BoundaryRecord | None = None,
    ) -> None: ...
    def _continue_from_donor(
        self, donor: ActuarialFrame, *, held: pl.DataFrame
    ) -> None: ...
    def _record_minted_columns(
        self,
        columns: dict[str, tuple[OpNode, pl.Expr]],
        *,
        origin: RecordOrigin,
        source: SourceSpan | None = ...,
    ) -> None: ...
    def _reset_attribution_window(self, operation: StructuralOperation) -> None: ...
    def _refresh_attr_columns_set(self) -> None: ...
    def show_query_plan(self, enabled: bool = True) -> Self: ...
    def trace(
        self, func: Callable[..., Any]
    ) -> Callable[..., ActuarialFrame | None]: ...
    def collect(self, *, engine: str = "streaming") -> pl.DataFrame: ...
    def materialize(self, *, engine: str | None = None) -> Self: ...
    def profile(self) -> tuple[pl.DataFrame, pl.DataFrame]: ...
    def with_columns(self, *exprs: IntoExprColumn) -> Self: ...
    def select(
        self,
        *exprs: IntoExprColumn | Iterable[IntoExprColumn],
        **named_exprs: IntoExprColumn,
    ) -> Self: ...
    def pipe[**P](
        self,
        func: Callable[Concatenate[ActuarialFrame, P], ActuarialFrame | None],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Self: ...
    def get_column_order(self) -> list[str]: ...

    # ADDED: Declare accessor properties
    @property
    def date(self) -> DateFrameAccessor: ...
    @property
    def finance(self) -> FinanceFrameAccessor: ...
    @property
    def excel(self) -> ExcelFrameAccessor: ...
    @property
    def projection(self) -> ProjectionFrameAccessor: ...
    @property
    def graph(self) -> GraphFrameAccessor: ...
    @property
    def columns(self) -> list[str]: ...
    @property
    def schema(self) -> pl.Schema: ...
    @property
    def dtypes(self) -> list[pl.DataType]: ...

    # Everyday frame verbs (declared so they don't fall into __getattr__)
    def drop(self, *columns: str) -> Self: ...
    def filter(
        self, predicate: pl.Expr | ConditionExpression | ExpressionProxy | ColumnProxy
    ) -> Self: ...
    def _selection_predicate(self, predicate: object) -> tuple[OpNode, pl.Expr]: ...
    def _book_for_a_selecting_engine(
        self, document: dict[str, Any]
    ) -> pl.DataFrame: ...
    def join(
        self,
        other: pl.DataFrame | pl.LazyFrame,
        on: str | list[str] | None = None,
        left_on: str | list[str] | None = None,
        right_on: str | list[str] | None = None,
        how: str = "left",
        maintain_order: str | None = None,
        *,
        on_missing: str = "raise",
    ) -> Self: ...
    def rename(self, mapping: dict[str, str]) -> Self: ...
    def sort(
        self,
        by: str | list[str],
        *,
        descending: bool = False,
    ) -> Self: ...

    # ADDED: Core function wrapper method signatures
    def fill_series(
        self,
        column: IntoExprColumn,
        start: int = 0,
        increment: int = 1,
    ) -> ExpressionProxy: ...
    def max(self) -> MaxResult: ...
    def min(self) -> MinResult: ...
    def mean(self) -> MeanResult: ...
    def std(self, ddof: int = 1) -> StdResult: ...
    def var(self, ddof: int = 1) -> VarResult: ...
    def median(self) -> MedianResult: ...
    def sum(self) -> SumResult: ...
    def count(self) -> CountResult: ...
    def product(self) -> ProductResult: ...
    def quantile(
        self, quantile: float, interpolation: str = "nearest"
    ) -> QuantileResult: ...

# What the API reference documents from this module.
__all__ = ["ActuarialFrame"]
