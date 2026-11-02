# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Name the policy a list kernel refused, from the frame where the row is known.

A list kernel is handed one batch of rows per call and no offset with it, so
the row it could count is the batch's. Under the default streaming engine that
is not the frame's row: a policy at frame row 1 was reported as ``row 0``, and
a reader who opened row 0 found nothing wrong there. The kernels now say "in
one policy" and give the operand and its two lengths, or the value that was
null, and name no row.

This module puts the row back, and the policy with it. When the collect-time
replay has named the calculation that failed (its ``CalculationRecord``) and
handed over the frame that calculation was applied to, one plain Polars pass
over that frame finds every policy the kernel's rule refuses: for a length
refusal, a policy whose per-period operands of one operation have different
lengths (spec 11.1.18: two lists must have equal lengths within each policy);
for a null refusal, a policy whose per-policy clip bound is null. The policy is
named by the run's policy-id column -- the one ``--policy-id-column`` named,
else the first of the identifier names the runner reads (``policy_id``,
``point_id``, ...) -- and by its row of that frame, with a count of the rest.

The pass runs only after a run has failed and the replay has named the
calculation, so a run that succeeds pays nothing for it. It never makes the
error worse: anything it cannot evaluate leaves the line out.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from gaspatchio._semantic.ir import BinOp, Call, WhenThen
from gaspatchio.errors.boundary import POLARS_LIST_LENGTH_LINE

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.frame.calculations import CalculationRecord

# What the kernels' refusals say, on the first line, for the two kinds this
# module can locate (``core/src/polars_functions/slices.rs``). Polars' own
# list arithmetic's length refusal, whose row index is its batch's too, is the
# replay's allowlisted template (``POLARS_LIST_LENGTH_LINE``), read from there
# so the two can never disagree about what the line looks like.
_LENGTH_REFUSAL = "mismatched inner list lengths in one policy"
_NULL_REFUSAL = "is null for one policy"
# Polars' line for a strict read by position that finds no value: past a
# policy's run, or -- as ``rules/selection.py`` lowers them -- in a missing run
# or at a missing position.
_POSITION_REFUSAL = "get index is out of bounds"

# The operations whose list operands must share their policy's period count,
# beyond every binary operation and conditional: the calls lowered to a list
# kernel that pairs its operands period by period.
_PAIRED_CALLS = frozenset(
    {"clip", "projection.accumulate", "excel.pv", "excel.yearfrac", "lookup"}
)
_ROLLFORWARD_CALLS = frozenset(
    {"rollforward.state", "rollforward.increment", "rollforward.struct"}
)

# The column the row index is written to for the pass, chosen not to collide.
_ROW = "__gaspatchio_policy_row"

_TOLD_ID_COLUMN: ContextVar[str | None] = ContextVar(
    "gaspatchio_told_policy_id_column", default=None
)


@contextmanager
def telling_the_policy_id_column(name: str | None) -> Iterator[None]:
    """Name the run's policy-id column for any refusal raised inside the block.

    The runner wraps a model run in this with the ``--policy-id-column`` it
    was given, so a refusal names the policy by the column the user named.
    ``None`` leaves the identifier names the runner reads as the default.
    """
    token = _TOLD_ID_COLUMN.set(name)
    try:
        yield
    finally:
        _TOLD_ID_COLUMN.reset(token)


@dataclass(frozen=True, slots=True)
class LocatedPolicies:
    """The policies one kernel refusal is about, found in the frame.

    ``row`` is the first such policy's row of the frame the calculation was
    applied to; ``policy`` is its identifier where an id column resolved;
    ``more`` counts the others found; ``capped_at`` is the replay's row cap
    when the frame reached it, so policies past it were not looked at.
    """

    row: int
    id_column: str | None
    policy: str | None
    more: int
    capped_at: int | None

    def text(self) -> str:
        """Render the policy as one line: ``policy_id=P002 (row 1), and 2 more``."""
        first = (
            f"row {self.row}"
            if self.id_column is None
            else f"{self.id_column}={self.policy} (row {self.row})"
        )
        if self.more:
            first += f", and {self.more} more"
        if self.capped_at is not None:
            first += f" among the first {self.capped_at:,} rows"
        return first


@dataclass(frozen=True, slots=True)
class _Group:
    """The operands of one operation, as the kernel pairs them for a policy."""

    members: tuple[pl.Expr, ...]
    # Lengths the operands' own must equal, beside them: a rollforward's
    # declared period count. Empty for every other operation.
    lengths: tuple[pl.Expr, ...] = ()


def locate_refused_policies(
    record: CalculationRecord,
    frame: pl.DataFrame,
    exception: BaseException,
    *,
    capped_at: int | None = None,
) -> LocatedPolicies | None:
    """Find the policies a list kernel refused, or ``None`` when it cannot.

    Args:
        record: The calculation the replay named as the one that failed.
        frame: The frame that calculation was applied to.
        exception: The refusal, whose first line says which kind it is.
        capped_at: The replay's row cap; reported when ``frame`` reached it.

    Returns:
        The first policy found, with a count of the rest, or ``None`` when the
        refusal is not one this module locates or nothing in the frame breaks
        the rule.

    """
    text = str(exception)
    if _LENGTH_REFUSAL in text or POLARS_LIST_LENGTH_LINE.search(text):
        kind = "lengths"
    elif _NULL_REFUSAL in text:
        kind = "null"
    elif _POSITION_REFUSAL in text:
        kind = "position"
    else:
        return None
    from gaspatchio.frame.lowering.context import (  # noqa: PLC0415 -- import cycle
        LoweringContext,
    )

    ctx = LoweringContext(frame=_FrameSchema(frame))
    masks = [
        mask
        for group in _groups(record.node, kind, ctx)
        if (mask := _mask(group, kind, frame)) is not None
    ]
    if not masks:
        return None
    rows = _refused_rows(frame, masks)
    if not rows:
        return None
    id_column = _policy_id_column(frame)
    policy = None if id_column is None else str(frame[id_column][rows[0]])
    reached_cap = capped_at is not None and frame.height >= capped_at
    return LocatedPolicies(
        row=rows[0],
        id_column=id_column,
        policy=policy,
        more=len(rows) - 1,
        capped_at=capped_at if reached_cap else None,
    )


def policy_line(
    record: CalculationRecord,
    last_good: pl.DataFrame | None,
    exception: BaseException,
) -> str | None:
    """Name the policy a list kernel refused, as the error report's line.

    ``last_good`` is the frame the replay applied the named calculation to;
    ``None`` -- no frame was handed over -- names nothing. The line is left
    out (``None``) for any other failure, where nothing can be named, and
    where locating it raised: a diagnosis never makes the error worse.
    """
    if last_good is None:
        return None
    from . import boundary  # noqa: PLC0415 -- boundary reads the frame layer

    try:
        located = locate_refused_policies(
            record,
            last_good,
            exception,
            # The replay's own row cap, read where a test may have moved it.
            capped_at=boundary._REPLAY_MAX_ROWS,  # noqa: SLF001
        )
    except Exception as locate_error:  # noqa: BLE001 -- never make the error worse
        logger.debug(f"Policy location failed ({locate_error!r}); leaving it out")
        return None
    return None if located is None else located.text()


class _FrameSchema:
    """The two things lowering reads off a frame, for an eager one.

    Read-only: this stands in for a frame only so that lowering can type
    the operands, and it has no plan of its own to set.
    """

    def __init__(self, frame: pl.DataFrame) -> None:
        self._frame = frame

    @property
    def _schema(self) -> pl.Schema:
        return self._frame.schema

    @property
    def _df(self) -> pl.LazyFrame:
        return self._frame.lazy()


def _groups(node: OpNode, kind: str, ctx: object) -> Iterator[_Group]:
    """Yield every operation in ``node``'s tree whose operands the kernel pairs."""
    for operands in _operand_sets(node, kind):
        members = _lowered(operands, ctx)
        if members is not None:
            yield _Group(members)
    if kind == "lengths":
        yield from _rollforward_groups(node)


def _operand_sets(node: OpNode, kind: str) -> Iterator[list[OpNode]]:
    """Walk the tree, yielding each pairing operation's operands as nodes.

    A length refusal is about any operation that pairs per-period operands.
    The one null refusal left is a clip's per-policy bound. A position
    refusal is a read by position, ``list.get``.
    """
    match node:
        case BinOp(left=left, right=right):
            if kind == "lengths":
                yield [left, right]
            yield from _operand_sets(left, kind)
            yield from _operand_sets(right, kind)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            if kind == "lengths":
                condition = (
                    [cond.left, cond.right] if isinstance(cond, BinOp) else [cond]
                )
                yield [*condition, then, otherwise]
            yield from _operand_sets(cond, kind)
            yield from _operand_sets(then, kind)
            yield from _operand_sets(otherwise, kind)
        case Call(name=name, args=args):
            pairs = kind == "lengths" and name in _PAIRED_CALLS
            if (
                pairs
                or (kind == "null" and name == "clip")
                or (kind == "position" and name == "list.get")
            ):
                yield list(args)
            for arg in args:
                yield from _operand_sets(arg, kind)
        case _:
            return


def _lowered(operands: list[OpNode], ctx: object) -> tuple[pl.Expr, ...] | None:
    """Lower each operand, or ``None`` when any of them does not lower."""
    from gaspatchio.frame.lowering.polars import lower_polars  # noqa: PLC0415

    try:
        return tuple(lower_polars(operand, ctx) for operand in operands)  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001 -- never make the error worse
        logger.debug(f"Policy location: an operand did not lower ({error!r})")
        return None


def _rollforward_groups(node: OpNode) -> Iterator[_Group]:
    """Yield each rollforward's list inputs, wherever one stands in the tree."""
    match node:
        case Call(name=name, attrs=attrs) if name in _ROLLFORWARD_CALLS:
            named = dict(attrs)
            group = _rollforward_group(named.get("fingerprint"), named.get("schedule"))
            if group is not None:
                yield group
        case BinOp(left=left, right=right):
            yield from _rollforward_groups(left)
            yield from _rollforward_groups(right)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            for child in (cond, then, otherwise):
                yield from _rollforward_groups(child)
        case Call(args=args):
            for arg in args:
                yield from _rollforward_groups(arg)
        case _:
            return


def _rollforward_group(fingerprint: object, schedule: object) -> _Group | None:
    """Return one compiled rollforward's list inputs and the count they share.

    Found by the pair the call carries -- the machine's fingerprint and the
    schedule it runs on -- because the count is the schedule's.

    The kernel reads its inputs from the compiled payload, not from the
    call's operands: the state initials, then the input columns, then --
    on a per-policy grid -- each policy's period count. A uniform schedule
    declares one count for every policy instead.
    """
    if not isinstance(fingerprint, str) or not isinstance(schedule, str):
        return None
    try:
        from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415
            rollforward_for,
        )

        compiled = rollforward_for(fingerprint, schedule)
    except Exception as error:  # noqa: BLE001 -- never make the error worse
        logger.debug(f"Policy location: no compiled rollforward ({error!r})")
        return None
    kwargs = compiled.plugin_kwargs
    args = compiled.plugin_args
    n_states = int(kwargs.get("n_states", 0))
    inputs = args[n_states : n_states + len(kwargs.get("input_columns", ()))]
    at = kwargs.get("per_policy_lengths_arg")
    if isinstance(at, int) and at < len(args):
        lengths: tuple[pl.Expr, ...] = (args[at],)
    elif kwargs.get("require_uniform"):
        lengths = (pl.lit(int(kwargs.get("n_periods", 0))),)
    else:
        lengths = ()
    return _Group(tuple(inputs), lengths=lengths)


def _mask(group: _Group, kind: str, frame: pl.DataFrame) -> pl.Expr | None:
    """Return the expression true on each policy ``group`` breaks the rule for."""
    try:
        schema = (
            frame.lazy()
            .select(member.alias(f"m{i}") for i, member in enumerate(group.members))
            .collect_schema()
        )
    except Exception as error:  # noqa: BLE001 -- never make the error worse
        logger.debug(f"Policy location: an operation did not type ({error!r})")
        return None
    if kind == "position":
        # A read by position: the run, then the position.
        run, position = group.members
        length = run.list.len().cast(pl.Int64)
        return (
            run.is_null()
            | position.is_null()
            | (position >= length)
            | (position < -length)
        )
    is_list = [isinstance(dtype, pl.List) for dtype in schema.dtypes()]
    lists = [m for m, listed in zip(group.members, is_list, strict=True) if listed]
    if kind == "lengths":
        lengths = [m.list.len().cast(pl.Int64) for m in lists]
        lengths += [length.cast(pl.Int64) for length in group.lengths]
        if len(lengths) < 2:  # noqa: PLR2004 -- a pair is what can disagree
            return None
        return pl.concat_list(lengths).list.drop_nulls().list.n_unique() > 1
    values = [m for m, listed in zip(group.members, is_list, strict=True) if not listed]
    if not values or not lists:
        return None
    return pl.any_horizontal(value.is_null() for value in values)


def _refused_rows(frame: pl.DataFrame, masks: list[pl.Expr]) -> list[int]:
    """Return the rows any mask holds on, in one pass where the frame allows it.

    One operand can itself be a kernel call that refuses -- a conditional
    nested inside a product -- so a pass over every mask together can raise.
    The masks are then evaluated one at a time and the ones that raise left
    out: the refusing operation's own operands are among the others.
    """
    indexed = frame.with_row_index(_ROW)
    try:
        hits = indexed.filter(pl.any_horizontal(masks)).get_column(_ROW)
        return [int(row) for row in hits]
    except Exception:  # noqa: BLE001 -- fall back to one pass per mask
        found: set[int] = set()
        for mask in masks:
            try:
                found.update(int(row) for row in indexed.filter(mask).get_column(_ROW))
            except Exception as error:  # noqa: BLE001 -- never make the error worse
                logger.debug(f"Policy location: a mask did not evaluate ({error!r})")
        return sorted(found)


def _policy_id_column(frame: pl.DataFrame) -> str | None:
    """Resolve the column that names each policy, as the runner resolves it.

    The column the run was told (``--policy-id-column``) where the frame
    carries it, else the first of the identifier names the runner reads,
    matched without regard to case.
    A per-period column names no policy and is passed over; nothing found is
    ``None``, and the policy is then named by its row alone.
    """
    from gaspatchio.runner import _ID_COLUMN_CANDIDATES  # noqa: PLC0415 -- import cycle

    by_lower = {
        name.lower(): name
        for name, dtype in frame.schema.items()
        if not isinstance(dtype, (pl.List, pl.Array, pl.Struct))
    }
    told = _TOLD_ID_COLUMN.get()
    candidates = ((told,) if told is not None else ()) + _ID_COLUMN_CANDIDATES
    for candidate in candidates:
        name = by_lower.get(candidate.lower())
        if name is not None:
            return name
    return None
