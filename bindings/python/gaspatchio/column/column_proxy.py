# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Defines the ColumnProxy class."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, NoReturn, cast

from gaspatchio._shape import _UNSET, Shape, _shape_from_schema
from gaspatchio.frame.lowering.columns import column_reference

from ._declared import _accessor_attribute, _names_with_accessors
from ._generated_proxy import _GeneratedProxySurface
from .expression_proxy import ExpressionProxy  # Runtime import

# Use TYPE_CHECKING for imports that would cause circular dependencies at runtime
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import polars as pl

    from gaspatchio._authoring.escape import PolarsNative, ProxyType
    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.accessors.date import DateColumnAccessor
    from gaspatchio.accessors.excel import ExcelColumnAccessor
    from gaspatchio.accessors.finance import FinanceColumnAccessor
    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.frame.calculations import OverwriteRecord
    from gaspatchio.rollforward._compiled import CompiledRollforward

# Import the registry for accessor lookup
from gaspatchio.frame.registry import _ACCESSOR_REGISTRY

# The two reads that answer without the column: the compiled rollforward
# itself, asked for a step's movement or for a balance at a point.
_ASK_THE_COMPILATION = (
    "or ask the compiled rollforward directly: "
    "compiled.increment_for(label) for a step's movement, "
    "compiled.expr_for(state, point=...) for a balance at a point."
)


class _RollforwardFieldAccessor:
    """Read the rest of a compiled rollforward through a column it produced.

    ``af.av = compiled.expr_for("av")`` records which compilation the column
    came from, so ``af.av.increments["growth"]`` and
    ``af.av.captures["after_growth"]`` ask that compilation for what
    ``compiled.increment_for("growth")`` and
    ``compiled.expr_for("av", point="after_growth")`` give. Each is read from
    the one struct the state's own assignment materialised, so the kernel
    still runs once however many are read -- and only while the frame still
    holds that run. After ``materialize()``, a select that drops it, or a
    frame rebuilt from collected values, a read would run the rollforward
    again over its inputs as they are by then, and it is refused instead.
    """

    __slots__ = ("_column_name", "_kind", "_parent")

    def __init__(
        self,
        parent: ActuarialFrame,
        column_name: str,
        kind: Literal["increments", "captures"],
    ) -> None:
        self._parent = parent
        self._column_name = column_name
        self._kind = kind

    def __getitem__(self, key: str) -> ExpressionProxy:
        """Return one labelled step's movement, or the state's balance at a point.

        Parameters
        ----------
        key : str
            The step's label (for increments) or the declared point (for
            captures).

        Returns
        -------
        ExpressionProxy
            The per-period series, read from the compiled rollforward this
            column was assigned from.

        Raises
        ------
        ValueError
            If this column was not assigned from a compiled rollforward's
            state, if the frame no longer holds the run it came from, or if
            the rollforward does not track its increments.
        KeyError
            If no step carries the label, or the point is not captured.

        """
        from gaspatchio.frame.lowering.ingress import to_node  # noqa: PLC0415 — cycle
        from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — cycle
            hidden_column_name,
        )

        compiled, state, run, defined_at = self._compilation()
        self._refuse_another_run(run, defined_at)
        if self._kind == "increments":
            read = compiled.increment_for(key)
            self._refuse_another_states_step(compiled, state, run, key)
        else:
            read = compiled.expr_for(state, point=key)
        node = to_node(read)
        # The run checked above is the state's own, so this read answers from
        # it even where an input has moved since: the state's movements are
        # what the state is. The frame is told by the node itself, which an
        # expression written around the read carries as one of its parts.
        self._parent._held_reads[id(node)] = (  # noqa: SLF001
            node,
            hidden_column_name(*run),
        )
        return ExpressionProxy._from_node(node, self._parent)  # noqa: SLF001

    def _refuse_another_states_step(
        self,
        compiled: CompiledRollforward,
        state: str,
        run: tuple[str, str],
        key: str,
    ) -> None:
        """Refuse a step that moves a different state from this column's.

        Labels name steps across the whole compilation, so a label can name a
        step that moves another state. Read through this column, its movement
        would be reported under the wrong state's name.
        """
        from gaspatchio.rollforward._ops import (  # noqa: PLC0415 — cycle
            increment_key,
        )

        moves = {
            increment_key(op, ordinal): getattr(
                getattr(op, "target", None), "state", None
            )
            for ordinal, op in enumerate(compiled.ir.transitions, start=1)
        }
        moved = moves.get(key)
        if moved is None or moved == state:
            return
        column = self._column_name
        holder = self._column_holding(run, moved)
        through = (
            f"af[{holder!r}].increments[{key!r}]"
            if holder is not None
            else (
                f"the column that holds {moved!r} -- assign it with "
                f"af[{moved!r}] = compiled.expr_for({moved!r}) --"
            )
        )
        msg = (
            f"The step {key!r} moves the state {moved!r}, not {state!r}, which "
            f"af[{column!r}] holds, and a state's increments are the steps "
            f"that move it. Read it through {through} or as "
            f"compiled.increment_for({key!r})."
        )
        raise ValueError(msg)

    def _column_holding(self, run: tuple[str, str], state: str) -> str | None:
        """Return the frame column whose live definition is this compilation's state.

        ``run`` is the compilation's fingerprint and the schedule it runs on,
        as its calls carry them: the fingerprint is the machine alone, so a
        column extracted from the same machine on another schedule is not
        this compilation's.

        A column written over in the query plan since is no such column, and
        is never suggested: what it holds is the write's, not the state's.
        """
        from gaspatchio._semantic.ir import Call  # noqa: PLC0415 — cycle

        for column in self._parent.columns:
            _position, node, _origin, _written = self._live_definition(column)
            if isinstance(node, Call) and node.name == "rollforward.state":
                attrs = dict(node.attrs)
                if (
                    attrs.get("fingerprint"),
                    attrs.get("schedule"),
                ) == run and attrs.get("state") == state:
                    return column
        return None

    def _live_definition(
        self, column: str
    ) -> tuple[int, OpNode | None, str, OverwriteRecord | None]:
        """Return where a column's live definition is in the log, what, and whose.

        A rename is a name-move, so a renamed column is followed back to the
        definition its old name held. **One rename() call moves every name
        it maps at once**, and writes one record per name under one
        operation id: in ``af.rename({"fund": "gmdb", "gmdb": "fund"})`` the
        new ``fund`` is the old ``gmdb``, not the ``gmdb`` the same call has
        just written. So the old name is read as it stood before the whole
        call -- before the first record carrying the call's operation id --
        and never before one record of it.

        Returns the definition's position, its node, and the name it was
        written under -- the column itself, or the name it was renamed
        from. Where the log holds no definition, the position is -1 and the
        node None, and the name is the last one followed back to.

        A write over the name straight into the query plan is an entry of its
        own, so the latest entry says whether the last definition is still
        what the name holds. Where it is such a write, the node is None and
        the write is returned last; it is None everywhere else.
        """
        from gaspatchio._semantic.ir import Col  # noqa: PLC0415 — cycle
        from gaspatchio.frame.calculations import (  # noqa: PLC0415 — cycle
            CalculationRecord,
            OverwriteRecord,
        )

        calculations = self._parent._calculations  # noqa: SLF001
        name, before = column, len(calculations)
        while True:
            position, entry = next(
                (
                    (at, candidate)
                    for at in range(before - 1, -1, -1)
                    if isinstance(
                        candidate := calculations[at],
                        CalculationRecord | OverwriteRecord,
                    )
                    and candidate.column == name
                ),
                (-1, None),
            )
            if entry is None:
                return -1, None, name, None
            if isinstance(entry, OverwriteRecord):
                return position, None, name, entry
            if entry.origin == "rename" and isinstance(entry.node, Col):
                # What the old name held before the whole call that renamed it.
                call = entry.operation_id
                before = next(
                    at
                    for at, candidate in enumerate(calculations)
                    if isinstance(candidate, CalculationRecord)
                    and candidate.operation_id == call
                )
                name = entry.node.name
                continue
            return position, entry.node, name, None

    def _compilation(
        self,
    ) -> tuple[CompiledRollforward, str, tuple[str, str], int]:
        """Return the compilation this column was assigned from, and where.

        Read off the column's live definition in the frame's calculation log:
        a state extracted with ``compiled.expr_for`` is logged as the call
        that names its compilation by fingerprint and schedule. Returned with
        the state it extracts, that pair, and the definition's position in
        the log.
        A rename is a name-move, so a renamed column is followed back to the
        definition it carried (see ``_live_definition``). Anything else -- a
        column the data arrived with, a formula, an expression written around
        an extraction -- has no state behind it, and is refused saying which
        it is.

        Two more are refused for what the frame saw of them, because the
        log's word on them is not what they hold: a column written straight
        into the query plan after its last logged definition, and a column
        the frame was built holding whose values another frame calculated.
        Either may hold a state's values, and neither holds the run that made
        them; reading one through it would pair a column with movements it
        does not hold.
        """
        from gaspatchio._semantic.ir import Call  # noqa: PLC0415 — cycle
        from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — cycle
            rollforward_for,
        )
        from gaspatchio.rollforward._compiled import (  # noqa: PLC0415 — cycle
            CompiledRollforward,
        )

        position, node, origin, written = self._live_definition(self._column_name)
        if written is not None:
            self._refuse_written_over(origin, written)
        if node is None:
            refusal = self._calculated_elsewhere(origin)
            if refusal is not None:
                raise ValueError(refusal)
        if isinstance(node, Call) and node.name == "rollforward.state":
            attrs = dict(node.attrs)
            run = (str(attrs["fingerprint"]), str(attrs["schedule"]))
            compiled = rollforward_for(*run)
            if isinstance(compiled, CompiledRollforward):
                return compiled, str(attrs["state"]), run, position
        raise ValueError(self._not_a_state(node, origin))

    def _not_a_state(self, node: OpNode | None, origin: str) -> str:
        """Say what the column's live definition is, since it is no state.

        ``origin`` is the name the definition was followed back to -- the
        column's own, or the one it was renamed from.
        """
        from gaspatchio._semantic.ir import (  # noqa: PLC0415 — cycle
            Call,
            EngineNative,
            walk,
        )
        from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — cycle
            _is_minted_name,
        )

        column = self._column_name
        if node is None:
            what = self._why_no_definition(origin)
        elif any(
            (isinstance(part, Call) and part.name.startswith("rollforward."))
            or (
                isinstance(part, EngineNative)
                and any(_is_minted_name(dep) for dep in part.deps)
            )
            for part in walk(node)
        ):
            what = (
                f"{column!r} was written as an expression around a compiled "
                "rollforward's extraction -- an alias, or arithmetic around "
                "expr_for -- which keeps the values but not which state they are"
            )
        else:
            what = f"{column!r} is defined by a formula of the model's own"
        return (
            f"af[{column!r}].{self._kind} reads the compiled rollforward behind "
            f"the column's live definition, and the live definition of "
            f"{column!r} is not a rollforward's state: {what}. Assign the state "
            "itself, with nothing written around it -- "
            "af.av = compiled.expr_for('av') -- or ask the compiled rollforward "
            "directly: compiled.increment_for(label) for a step's movement, "
            "compiled.expr_for(state, point=...) for a balance at a point."
        )

    def _why_no_definition(self, origin: str) -> str:
        """Say why the calculation log holds no definition of the column.

        Three reasons, and the frame can tell them apart: the column arrived
        with the data (under this name, or under the one it was renamed
        from); it is on the frame with no account of itself, as a column
        written straight into the query plan under a new name is; or the
        frame holds no column of that name at all.
        """
        column, parent = self._column_name, self._parent
        if column in parent._initial_columns:  # noqa: SLF001
            renamed = f" as {origin!r}" if origin != column else ""
            return (
                f"the calculation log holds no definition of {column!r}, which "
                f"arrived with the data{renamed}"
            )
        if column in parent._unaccounted_columns():  # noqa: SLF001
            return (
                f"the calculation log holds no definition of {column!r}, which "
                "is on the frame with no account of itself -- written straight "
                "into the query plan under a name of its own, af._df = ..., "
                "which the frame does not record"
            )
        return (
            f"the calculation log holds no definition of {column!r}, and the "
            "frame holds no column of that name"
        )

    def _refuse_another_run(self, run: tuple[str, str], defined_at: int) -> None:
        """Refuse a read the plan's struct cannot answer for this column.

        A read comes from the struct the plan holds for this compilation,
        and it answers for the column only where that struct is the run the
        column came from: still on the plan, and put there before the column
        was defined. Otherwise the read would run the rollforward again over
        its inputs as they are by then -- after ``materialize()``, on a frame
        rebuilt from collected values, after a select that dropped the struct
        -- and could answer for a different run than the column's own.
        """
        from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — cycle
            hidden_column_name,
        )

        parent = self._parent
        struct = hidden_column_name(*run)
        put_on_at = parent._rollforward_runs.get(struct)  # noqa: SLF001
        if (
            struct in (parent._schema or {})  # noqa: SLF001
            and put_on_at is not None
            and put_on_at <= defined_at
        ):
            return
        column = self._column_name
        msg = (
            f"af[{column!r}].{self._kind} reads the rest of the kernel run that "
            f"produced {column!r}, and that run is no longer in the frame: "
            "materialize() leaves it behind, as do a select that drops it and "
            "a frame rebuilt out of collected values, and a later extraction "
            "runs it again over its inputs as they are by then, so a read now "
            "could answer for a different run than the one this column holds. "
            f"Read {self._kind} before materialize(), a select or a rebuild -- "
            "or call compiled.increment_for(label) or compiled.expr_for(state, "
            "point=...) deliberately, knowing it runs on the inputs as they "
            "are now, which the frame allows only while each is as it stood "
            "when the frame first read the rollforward."
        )
        raise ValueError(msg)

    def _refuse_written_over(self, name: str, entry: OverwriteRecord) -> NoReturn:
        """Refuse a column the log reads that was written over in the plan.

        Raises:
            ValueError: Naming the line of the write, and the two reads that
                answer instead.

        """
        from gaspatchio.frame.graph.graph_utils import (  # noqa: PLC0415 — cycle
            source_location,
        )

        column = self._column_name
        held = (
            f"{column!r}"
            if name == column
            else (
                f"{column!r} holds what {name!r} held when it was renamed, and {name!r}"
            )
        )
        location = source_location(entry.source)
        at = f" at {location}" if location else ""
        msg = (
            f"af[{column!r}].{self._kind} reads the compiled rollforward behind "
            f"the column's live definition, and {held} was written straight into "
            f"the query plan{at}, outside the frame's own operations, so the "
            "frame cannot say which rollforward run, if any, its values came "
            "from. Assign the state itself through the frame and write nothing "
            f"over it -- af.av = compiled.expr_for('av') -- {_ASK_THE_COMPILATION}"
        )
        raise ValueError(msg)

    def _calculated_elsewhere(self, name: str) -> str | None:
        """Say that the column arrived holding another frame's state, or None.

        The run that made the values is on the frame that calculated them, so
        the read that answers is taken there, before that frame is collected:
        a frame that carries the calculation across with ``continue_from=``
        still holds values rather than the run.
        """
        origin = self._parent._rebuilt.get(name)  # noqa: SLF001
        if origin is None:
            return None
        column = self._column_name
        at = f" at {origin.source_location}" if origin.source_location else ""
        return (
            f"af[{column!r}].{self._kind} reads the kernel run behind the column, "
            f"and {column!r} arrived holding values {origin.node_id} calculated "
            f"on another frame{at}: the run is on that frame and not on this "
            f"one. Read {self._kind} on that frame, before it is collected -- "
            f"{_ASK_THE_COMPILATION}"
        )

    def __repr__(self) -> str:
        return f"_RollforwardFieldAccessor({self._column_name!r}, kind={self._kind!r})"


class ColumnProxy(_GeneratedProxySurface):
    """Represents a column identifier within an ActuarialFrame.

    It acts as a starting point for expressions.
    """

    # Cache for accessor instances
    _date_accessor_instance: DateColumnAccessor | None = None
    _excel_accessor_instance: ExcelColumnAccessor | None = None
    _finance_accessor_instance: FinanceColumnAccessor | None = None

    def __init__(self, name: str, parent: ActuarialFrame) -> None:
        """Initialize a ColumnProxy.

        Note: Users should not typically instantiate this directly.
        Obtain instances via ActuarialFrame indexing (e.g., `af['column_name']`).
        """
        if not isinstance(name, str) or not name:
            msg = "ColumnProxy name must be a non-empty string."
            raise ValueError(msg)
        # Avoid holding a direct reference to the parent's LazyFrame/DataFrame
        # if possible, but we need it for context (schema, _convert_to_expr,
        # apply_function).
        # Consider passing only necessary context if this becomes an issue.
        self.name = name
        self._parent = parent  # Reference to the parent ActuarialFrame
        self._dynamic_accessor_cache: dict[str, Any] = {}  # Initialize cache
        self._shape_cached: tuple[int, str] | object = _UNSET
        self._node_cached: OpNode | None = None

    @property
    def _node(self) -> OpNode:
        """The column as an op-tree node: the leaf every formula starts from.

        Built on first use rather than in ``__init__``: a ``ColumnProxy`` is
        created for every attribute access on a frame, including the many
        that never become part of a formula.
        """
        node = self._node_cached
        if node is None:
            from gaspatchio._semantic.ir import Col  # noqa: PLC0415

            node = Col(self.name)
            self._node_cached = node
        return node

    @property
    def shape(self) -> Shape:
        """Resolved shape of this column reference (`scalar`, `list`, or `unknown`)."""
        gen = getattr(self._parent, "_schema_generation", 0)
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
            self._shape_cached = (gen, _shape_from_schema(self._parent, self.name))
        return self._shape_cached[1]  # type: ignore[index]

    kind: ClassVar[str] = "value"

    def _to_expr(self) -> pl.Expr:
        """Convert this proxy to a base Polars column expression."""
        return column_reference(self.name)

    def __repr__(self) -> str:
        """Return the proxy's debug representation, naming its column."""
        return f"ColumnProxy(name='{self.name}')"

    # --- Operator Overloads ---
    # Every operator emits a semantic BinOp node; the Polars expression that
    # computes it is derived later, by lowering (see _authoring/emit.py).

    # Comparison operators

    # --- Reverse Operators ---
    # The other operand is the receiver the author wrote first, so it becomes
    # the node's left child: `1 - af.pols_if` emits BinOp("sub", Lit(1), ...).

    # --- Explicitly Defined Methods/Properties ---
    # Frame-specific methods sit beside the generated operation surface.

    @property
    def increments(self) -> _RollforwardFieldAccessor:
        """Read a labelled step's movement from the rollforward behind this column.

        ``af.av.increments["Premium"]`` is ``compiled.increment_for("Premium")``
        for the compiled rollforward ``af.av`` was assigned from, read from
        the same kernel run. A step that moves another state is refused,
        naming the column that holds it, and so is a read once the frame no
        longer holds the run -- after ``materialize()``, a select that drops
        it, or a frame rebuilt from collected values.

        Requires the rollforward to be built with ``track_increments=True``;
        each step then emits its signed per-period delta (negative for
        charges, positive for credits, zero after a stop or lapse).
        """
        return _RollforwardFieldAccessor(self._parent, self.name, "increments")

    @property
    def captures(self) -> _RollforwardFieldAccessor:
        """Read this column's state at another point of its rollforward.

        ``af.av.captures["after_growth"]`` is
        ``compiled.expr_for("av", point="after_growth")`` for the compiled
        rollforward ``af.av`` was assigned from: the balance the kernel
        captured at that point in each period, read from the same kernel run
        and refused once the frame no longer holds it. A point is captured
        where an operation targets it, and every state's ``eop`` always is.
        """
        return _RollforwardFieldAccessor(self._parent, self.name, "captures")

    def polars_native(self, *, deps: Sequence[str] | None = None) -> PolarsNative:
        """Reach a Polars expression method gaspatchio's vocabulary does not name.

        Gaspatchio names the operations an actuarial model is made of, and a
        formula written in them records as those operations: any engine
        holding the vocabulary can evaluate it, and a reader of the exported
        record can check it. Polars can do more than the vocabulary names,
        and this is the way to reach the rest of it -- in the open.

        What comes back is an ordinary expression and the calculation runs
        exactly as it would have. What changes is the record: the node is
        engine text rather than an operation, so the artifact carries a
        rendering of the formula and not a program, **and only the process
        that wrote it can run it** -- exported and read back somewhere else,
        an engine-native node is a record of a calculation rather than one.
        It also takes the column off the portable subset, since one engine's
        own text is by construction what another engine cannot lower.

        !!! note "When to use"
            * **A portfolio-level ordering:** ranking the book by sum assured
                or picking out the largest exposures, where the answer is a
                position rather than an actuarial quantity.
            * **A Polars method no operation names:** a running maximum, a
                rolling window, an exponentially weighted mean.
            * **A form of an operation the vocabulary declines:** where the
                framework recognises the calculation only in another shape
                and will not record something narrower than what you wrote.
            * **Not** for anything the vocabulary already covers: that call
                is refused here, naming the operation, so one calculation
                never has two different records.

        Parameters
        ----------
        deps : Sequence[str], optional
            The columns the resulting expression reads. Needed only where the
            expression will not report them itself -- a compiled plugin can
            decline -- and checked against what it does report where it will,
            since this declaration is the model's lineage claim for a formula
            nothing else can read.

        Returns
        -------
        PolarsNative
            The open escape, on which one Polars expression method is called.

        Raises
        ------
        ValueError
            If the call is one gaspatchio's own vocabulary already names, or
            if the expression will not say which columns it reads and none
            were declared.

        Examples
        --------
        Ranking a book by size -- an ordering across model points, which is a
        position rather than an actuarial quantity, and which no operation
        names:

        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> af = ActuarialFrame(
        ...     pl.DataFrame({"sum_assured": [50000.0, 250000.0, 100000.0]})
        ... )
        >>> af.size_rank = af.sum_assured.polars_native().rank(method="ordinal")
        >>> af.collect()["size_rank"].to_list()
        [1, 3, 2]

        The lineage survives the escape -- the column the calculation reads
        stays declared, so the graph can still be asked what feeds it:

        >>> af.graph.precedents("size_rank")
        ('sum_assured',)

        """
        from gaspatchio._authoring.escape import PolarsNative  # noqa: PLC0415

        # The escape's receiver type names ColumnProxy as this module's stub
        # declares it, and pyright, checking this file, holds the class
        # defined here to be another one. They are one class at run time.
        return PolarsNative(cast("ProxyType", self), deps)

    def map_elements(self, func: Callable, return_dtype=None) -> ExpressionProxy:
        """Apply a Python function to each element of the column.

        Args:
            func: Function to apply to each element
            return_dtype: Optional polars DataType for the result

        Returns:
            ExpressionProxy: Result of applying the function

        """
        # Directly call the (potentially monkey-patched) Polars method.
        # The telemetry wrapper should handle this transparently.
        base_expr = self._to_expr()
        result_expr = base_expr.map_elements(func, return_dtype=return_dtype)
        return ExpressionProxy(result_expr, self._parent)

    def map_batches(self, func: Callable, return_dtype=None) -> ExpressionProxy:
        """Apply a Python function to the entire column as a Series.

        This is more efficient than apply for operations that can process
        multiple values at once, especially for NumPy or vector operations.

        Args:
            func: Function that receives a Series and returns a Series or array
            return_dtype: Optional polars DataType for the result

        Returns:
            ExpressionProxy: Result of applying the function

        """
        # Directly call the (potentially monkey-patched) Polars method.
        base_expr = self._to_expr()
        result_expr = base_expr.map_batches(func, return_dtype=return_dtype)
        return ExpressionProxy(result_expr, self._parent)

    # --- Accessor Properties ---
    # These properties provide access to specialized namespaces (e.g., date, finance).
    # They are explicitly defined here and use the accessor registry.

    @property
    def date(self) -> DateColumnAccessor:
        """Access date-related column operations."""
        cached = self._date_accessor_instance
        if cached is not None:
            return cached
        # Look up specifically for 'column' kind using the registry
        accessor_class = _ACCESSOR_REGISTRY.get("date", {}).get("column")
        if not accessor_class:
            msg = "No 'date' column accessor registered or kind mismatch."
            raise AttributeError(msg)
        # Instantiate the accessor, passing this ColumnProxy instance. The
        # registry stores bare classes, so the class registered under
        # ("date", "column") is what the cast names -- the AttributeError
        # above is the check that something is registered at all.
        accessor = cast("DateColumnAccessor", accessor_class(self))
        self._date_accessor_instance = accessor
        return accessor

    @property
    def finance(self) -> FinanceColumnAccessor:
        """Access finance-related column operations."""
        cached = self._finance_accessor_instance
        if cached is not None:
            return cached
        # Look up specifically for 'column' kind using the registry
        accessor_class = _ACCESSOR_REGISTRY.get("finance", {}).get("column")
        if not accessor_class:
            msg = "No 'finance' column accessor registered or kind mismatch."
            raise AttributeError(msg)
        # Instantiate the accessor, passing this ColumnProxy instance
        accessor = cast("FinanceColumnAccessor", accessor_class(self))
        self._finance_accessor_instance = accessor
        return accessor

    @property
    def excel(self) -> ExcelColumnAccessor:
        """Access excel-related column operations."""
        cached = self._excel_accessor_instance
        if cached is not None:
            return cached
        accessor_class = _ACCESSOR_REGISTRY.get("excel", {}).get("column")
        if not accessor_class:
            msg = "No 'excel' column accessor registered or kind mismatch."
            raise AttributeError(msg)
        accessor = cast("ExcelColumnAccessor", accessor_class(self))
        self._excel_accessor_instance = accessor
        return accessor

    # --- Dynamic Accessor Handling --- ADDED BACK
    # The registered column accessors, reached as attributes: one definition
    # for a column and an expression alike.
    __getattr__ = _accessor_attribute

    def __dir__(self) -> list[str]:
        """Include registered accessors beside the declared method surface."""
        return _names_with_accessors(self)


# What the API reference documents from this module.
__all__ = ["ColumnProxy"]
