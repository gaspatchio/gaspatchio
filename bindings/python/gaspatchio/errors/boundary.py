# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Error boundary detection using binary search replay
# ABOUTME: Finds the exact operation that causes compilation or runtime errors
"""Error boundary detection using binary search replay."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NamedTuple

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.frame.calculations import CalculationRecord, StructuralOperation


def is_plan_lowering_panic(exception: BaseException) -> bool:
    """Return True for pyo3 panics raised by plan lowering's schema derivation.

    A schema mismatch inside a ``when().then()`` branch fails during IR plan
    lowering, where polars panics ("no valid schema can be derived") instead
    of raising a typed error. pyo3 surfaces that as ``PanicException`` — a
    ``BaseException`` subclass that bypasses every ``except Exception``.
    Matched by type name rather than import: ``pyo3_runtime`` is a synthetic
    module and this predicate must be safe to call before/without it.

    Kept narrow deliberately (#54): only the schema-derivation panic is a
    data-shape failure that reproduces deterministically under replay. Any
    other panic — and any real interrupt — must pass through untouched.
    """
    return type(
        exception
    ).__name__ == "PanicException" and "no valid schema can be derived" in str(
        exception
    )


def _replayable(exception: BaseException) -> bool:
    """Return True when a replay probe may consume this exception.

    Probes catch ``BaseException`` so schema-derivation panics can be matched
    like any other failure, but anything that is neither an ``Exception`` nor
    such a panic (``KeyboardInterrupt``, ``SystemExit``, foreign panics) must
    propagate immediately.
    """
    return isinstance(exception, Exception) or is_plan_lowering_panic(exception)


def _group_columns(group: Sequence[CalculationRecord]) -> str:
    """Return a readable name for the columns one operation defines."""
    return ", ".join(record.column for record in group)


def _digits_masked(text: str) -> str:
    """Return ``text``'s first line with every run of digits replaced by ``#``.

    The rival matcher's view of a leading line: a ``ShapeError``'s row
    index and lengths are the frame's, not the calculation's, and two
    lines that differ only there are one line here.
    """
    return re.sub(r"\d+", "#", text.split("\n", 1)[0])


# Polars' own first lines whose every digit is a fact about the batch the
# engine was computing, not about the failure: a closed allowlist, today one
# entry, each a full-line template under the class that raises it. The
# streaming engine numbers ``list lengths differed at index N`` within the
# morsel it was computing and the in-memory replay within its head, so the
# two lines never meet on an exact compare; read against this template they
# are one line, and the lengths -- usually the same one period short -- are
# read the same way. Gaspatchio's own lines are never matched here: every
# kernel's opens ``the plugin failed with message:`` and the match is a
# ``fullmatch``, so they keep the exact first-line check.
# Closed: an entry needs a measured repro and a pin of Polars' wording
# (``test_polars_still_raises_the_allowlisted_list_length_line``). Polars'
# strict-cast line is deliberately not here: its sampled values vary by
# batch, which no digit mask reads past.
POLARS_LIST_LENGTH_LINE = re.compile(r"list lengths differed at index \d+: \d+ != \d+")
_POLARS_BATCH_LINES: tuple[tuple[type[Exception], re.Pattern[str]], ...] = (
    (pl.exceptions.ShapeError, POLARS_LIST_LENGTH_LINE),
)


# The line a refusal the lazy plan raises arrives under: a string cast to
# ``Int64`` that will not convert, the refusal's own sentence being the value
# (``require_valid_rows``). The column Polars names and the two counts are
# the batch's -- ``1 out of 12`` in memory, ``1 out of 3`` in a streaming
# morsel -- so the sentences reported, and nothing else, say which refusal
# it is.
_PLAN_REFUSAL_LINE = re.compile(
    r"conversion from `str` to `i64` failed in column '[^']*' "
    r"for \d+ out of \d+ values: \[(.*)\]"
)


# Polars' line for a strict cast of a book column -- text read as a date, say
# -- which names the column and the two types before the batch's counts and a
# sample of the values the batch held. The part before the counts is the
# failure; the rest is the batch's.
_STRICT_CAST_LINE = re.compile(
    r"(conversion from `[^`]+` to `[^`]+` failed in column '([^']*)') "
    r"for \d+ out of \d+ values: \[.*\]"
)


def _strict_cast_of_a_column(exception: BaseException) -> str | None:
    """Return the failure a strict cast of a named column states, or None.

    The cast of the plan's own refusal sentence (column ``literal``) is read
    by its sentences instead (:func:`_plan_refusal_sentences`).
    """
    if not isinstance(exception, pl.exceptions.InvalidOperationError):
        return None
    found = _STRICT_CAST_LINE.fullmatch(_first_line(exception))
    if found is None or found.group(2) == "literal":
        return None
    return found.group(1)


def _plan_refusal_sentences(exception: BaseException) -> frozenset[str] | None:
    """Return the sentences a plan refusal reported, or None if it is not one."""
    if not isinstance(exception, pl.exceptions.InvalidOperationError):
        return None
    found = _PLAN_REFUSAL_LINE.fullmatch(_first_line(exception))
    if found is None:
        return None
    return frozenset(re.findall(r'"((?:[^"\\]|\\.)*)"', found.group(1)))


def _first_line(exception: BaseException) -> str:
    """Return the first line the engine gave ``exception``'s message.

    The error door puts the framework's sentence above an engine line it
    reads (``formatting_errors``) and keeps that line as
    ``_engine_first_line``; the replay compares the engine's lines, so a
    lifted error is read by the line it was raised with.
    """
    kept = getattr(exception, "_engine_first_line", None)
    if isinstance(kept, str):
        return kept
    return str(exception).split("\n", 1)[0]


def _polars_batch_line(exception: BaseException) -> re.Pattern[str] | None:
    """Return the allowlisted template ``exception``'s first line fits, if any."""
    for raised_as, template in _POLARS_BATCH_LINES:
        if isinstance(exception, raised_as) and template.fullmatch(
            _first_line(exception)
        ):
            return template
    return None


def group_by_operation(
    records: Sequence[CalculationRecord],
) -> list[list[CalculationRecord]]:
    """Split a window of calculations into the operations that produced them.

    One operation is one call at an assignment door: a setter assignment
    defines a single column, a multi-column ``with_columns`` defines several
    and every record it produced carries the same ``operation_id``. Replay
    has to honour that grouping. Live, every expression in one call sees the
    frame as it stood BEFORE the call; replayed one expression at a time, an
    expression that read a sibling's old value would be handed the sibling's
    new one, reproduce a failure that never happened, and blame a healthy
    column.

    Records arrive in log order and one operation's records are contiguous,
    so a run of equal ids is exactly one group.

    Public because the grouping rule is the contract worth testing on its
    own, separately from any finder that replays it.
    """
    groups: list[list[CalculationRecord]] = []
    for record in records:
        if groups and groups[-1][0].operation_id == record.operation_id:
            groups[-1].append(record)
        else:
            groups.append([record])
    return groups


class ReplayWindow(NamedTuple):
    """One run of calculations and the plan they were applied to.

    The unit a replay works over. The frame's LIVE window is its
    ``_attribution_ops()`` paired with ``_baseline_df``; a window a
    structural operation closed is a ``SealedWindow``, which holds the same
    pair. Naming the pair is what lets one finder replay either.
    """

    records: list[CalculationRecord]
    baseline: pl.LazyFrame | None
    # The structural operations this window's plan went through before the
    # next window's baseline, in order; empty for the live window, which no
    # operation has followed. What a sealed candidate is confirmed through.
    operations: tuple[StructuralOperation, ...] = ()


def replay_windows(af: ActuarialFrame) -> list[ReplayWindow]:
    """Return the windows a failure may be attributed to, newest first.

    The live window comes first and is the one a failure normally belongs
    to. Behind it stand the windows structural operations closed, most
    recent first: each still reconstructs the plan the frame held one step
    before its operation, and carries the operations that followed it.
    Walking back is what keeps a break written before a ``filter()``
    attributable after one.

    This function only orders them. Which of them the search consults --
    a window whose plan will not collect is passed over, and a window that
    was searched and reproduced nothing ends the search -- is
    ``search_collect_failure``'s rule, stated there; what a reproduction
    against a sealed baseline is evidence of is
    :class:`~gaspatchio.frame.calculations.SealedWindow`'s.
    """
    windows = [
        ReplayWindow(
            records=af._attribution_ops(),  # noqa: SLF001
            baseline=getattr(af, "_baseline_df", None),
        )
    ]
    windows.extend(
        ReplayWindow(
            records=list(sealed.records),
            baseline=sealed.baseline,
            operations=sealed.operations,
        )
        for sealed in reversed(getattr(af, "_sealed_windows", []))
    )
    return windows


class ErrorBoundaryFinder:
    """Efficiently find the failing operation using binary search.

    The search runs over one attribution window — a run of calculations and
    the plan they were applied to — grouped into the operations that
    produced them. Each probe rebuilds the plan from that window's baseline
    by applying whole operations, one ``with_columns`` per operation, which
    is exactly how the frame built the plan that failed.
    """

    def __init__(
        self,
        af: ActuarialFrame,
        exception: BaseException,
        max_rows: int | None = None,
        *,
        window: ReplayWindow | None = None,
    ) -> None:
        """Initialize the error boundary finder.

        Args:
            af: The ActuarialFrame with failed computation
            exception: The exception that was raised
            max_rows: Optional row cap applied to the replay baseline. Replay
                collects real data repeatedly; on a 100K-policy frame an
                uncapped replay multiplies the failed run's full cost on the
                error path. A capped baseline keeps diagnosis fast — an error
                that only manifests beyond the cap simply fails to reproduce,
                which callers treat as "no attribution".
            window: The window to replay. Defaults to the frame's live one,
                which is what every caller wanted while a frame had only one
                window to offer; a caller walking back through the windows
                structural operations closed passes each in turn.

        """
        self.af = af
        self.exception = exception
        if window is None:
            window = ReplayWindow(
                records=af._attribution_ops(),  # noqa: SLF001
                baseline=getattr(af, "_baseline_df", None),
            )
        self.groups = group_by_operation(window.records)
        # Whether `original_df` below IS this window's own baseline, collected.
        # False means a substitute stands in its place, and what a replay does
        # against a substitute is evidence about the substitute. See the
        # collect handler below, and `_search_window` (under
        # `search_collect_failure`), which declines such a window rather
        # than replaying it.
        self.baseline_usable = True
        # Replay must start from the baseline the window opened over: _df
        # already contains every recorded calculation, so replaying the
        # window on top of it would re-apply self-referential assignments
        # during diagnosis and misattribute the failing calculation. A plan is
        # lazy; a hand-built log (the tests' mock frame, below) hands in an
        # eager frame, and both are read here.
        source: pl.LazyFrame | pl.DataFrame | None = window.baseline
        if source is None:
            # A frame that recorded its own calculations never arrives here
            # holding any: `_open_attribution_window_if_needed` snapshots the
            # baseline as a window's FIRST record is about to land, so a
            # window with records has a baseline, and one without records
            # names no column whichever plan it is handed. That is what keeps
            # this fallback from being the straddle it looks like — the
            # post-operation plan is never replayed under a window that
            # predates it. What does reach here holding records is a log
            # assembled by hand: `MockActuarialFrame` in
            # tests/errors/test_boundary.py omits `_baseline_df` on purpose,
            # and its `_df` is the pristine input those tests replay from.
            source = af._df  # noqa: SLF001
        # The window's plan, uncapped and lazy: what a sealed candidate is
        # run through the window's structural operations from, so that the
        # head is taken AFTER the operations, on the rows they keep.
        self.baseline_plan: pl.LazyFrame | None = (
            source.lazy() if isinstance(source, pl.DataFrame) else source
        )
        if source is not None and max_rows is not None:
            source = (
                source.limit(max_rows)
                if isinstance(source, pl.LazyFrame)
                else source.head(max_rows)
            )
        if source is not None:
            if isinstance(source, pl.LazyFrame):
                # It's a LazyFrame, collect it
                try:
                    self.original_df = source.collect()
                except Exception:  # noqa: BLE001
                    # This window's own plan does not collect. A window
                    # BEHIND a break is USUALLY in that position, because
                    # its baseline is a plan that contains the break —
                    # usually and not always, since the collect above is
                    # capped at `_REPLAY_MAX_ROWS` and a break the head
                    # never reaches leaves that same window collectible,
                    # and therefore never reaches this arm at all. What
                    # stands in here is an empty frame in the frame's
                    # CURRENT schema — the model's INPUT dtypes, not the
                    # ones this window opened over — so healthy arithmetic
                    # replayed against it can raise the very error being
                    # diagnosed, class and leading line and all. Kept for
                    # callers that only need the columns to exist, and
                    # flagged for the one that must be certain.
                    self.baseline_usable = False
                    # If collection fails, try to reconstruct original data
                    # using the stored schema (before any recorded calculation)
                    if hasattr(af, "_schema") and af._schema:  # noqa: SLF001
                        # Create empty DataFrame with original schema columns
                        self.original_df = pl.DataFrame(schema=af._schema)  # noqa: SLF001
                    else:
                        self.original_df = pl.DataFrame()
            else:
                # It's already a DataFrame
                self.original_df = source
        else:
            self.original_df = pl.DataFrame()
        self.exception_type = type(exception)

    def find_failing_operation(
        self,
    ) -> tuple[int, CalculationRecord | None, pl.DataFrame]:
        """Find the first operation that fails using binary search.

        The multi-operation probes here -- the full replay below and every
        ``mid`` probe of the binary search -- apply several operations as
        chained ``with_columns``, which polars fuses and evaluates in
        parallel, so when two of them fail with different first lines
        which one surfaces is scheduling and not evidence. Those probes
        decide only whether to keep searching; a name comes only from a
        one-operation step that reproduced the failure over a prefix that
        collected clean (``_find_exact_failing_operation``,
        ``_blame_within_group``), which is deterministic.

        Returns:
            Tuple of (failing_index, failing_calculation, last_good_dataframe)
            If no failing operation is found, or the search cannot be
            narrowed to one operation, returns (-1, None, ...).

        """
        # Handle an empty window
        if not self.groups:
            logger.debug("Empty attribution window, no operations to search")
            return -1, None, self.original_df

        # Early termination: check if first operation fails
        try:
            self._apply_operations_up_to(0)
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            if self._is_same_error_type(e):
                logger.debug("First operation fails, returning index 0")
                return 0, self._blame_within_group(0), self.original_df

        # Early termination: check if all operations succeed
        try:
            final_df = self._apply_operations_up_to(len(self.groups) - 1)
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            if not self._is_same_error_type(e):
                logger.debug(f"Different error type during full replay: {type(e)}")
                return -1, None, self.original_df
        else:
            logger.debug("All operations succeed, no failing operation found")
            return -1, None, final_df

        # Binary search for the failing operation
        return self._binary_search_failure()

    def _binary_search_failure(
        self,
    ) -> tuple[int, CalculationRecord | None, pl.DataFrame]:
        """Perform binary search to find the first failing operation.

        Returns:
            Tuple of (failing_index, failing_calculation, last_good_dataframe);
            ``failing_index`` is ``-1`` when the range the search found could
            not be narrowed to one operation.

        """
        operations = self.groups
        left, right = 0, len(operations) - 1
        last_good_df = self.original_df
        last_good_index = -1
        failing_index = -1

        logger.debug(f"Starting binary search on {len(operations)} operations")

        while left <= right:
            mid = (left + right) // 2
            logger.trace(
                f"Binary search: ops 0-{mid} (left={left}, right={right})",
            )

            try:
                test_df = self._apply_operations_up_to(mid)
                # This point succeeded, error is later
                last_good_df = test_df
                last_good_index = mid
                left = mid + 1
                logger.trace(f"Operations 0-{mid} succeeded, searching right half")
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_same_error_type(e):
                    # Error at or before this point
                    failing_index = mid
                    right = mid - 1
                    logger.trace(
                        f"Ops 0-{mid} failed with same error, searching left",
                    )
                else:
                    # Different error type, continue searching right
                    if mid > 0:
                        try:
                            last_good_df = self._apply_operations_up_to(mid - 1)
                            last_good_index = mid - 1
                        except (
                            BaseException
                        ) as retry_error:  # panic-aware probe, guarded below
                            if not _replayable(retry_error):
                                raise
                            last_good_df = self.original_df
                            last_good_index = -1
                    else:
                        last_good_df = self.original_df
                        last_good_index = -1
                    left = mid + 1
                    logger.trace(
                        f"Different error at ops 0-{mid}, searching right",
                    )

        # Refine to find exact failing operation
        if failing_index != -1:
            # Binary search found a range, now find exact operation
            exact_index = self._find_exact_failing_operation(
                failing_index,
                last_good_df,
                last_good_index,
            )
            failing_op = self._blame_within_group(exact_index)
            logger.debug(f"Exact-operation scan answered index {exact_index}")
            return exact_index, failing_op, last_good_df

        logger.debug("Binary search completed, no failing operation found")
        return -1, None, last_good_df

    def _find_exact_failing_operation(
        self,
        start_index: int,
        last_good_df: pl.DataFrame,
        last_good_index: int = -1,
    ) -> int:
        """Find the exact failing operation from a known-good prefix.

        Operations after ``last_good_index`` are applied one at a time, up
        to ``start_index``, and the first step that raises the original
        failure is the answer. That step is one operation over a prefix
        that collected clean, so it is evidence; ``start_index`` is not --
        it came from the multi-operation probes, and why a position that
        fell out of those is scheduling rather than evidence is stated
        once, on :meth:`find_failing_operation`. Answering ``start_index``
        when the scan broke on a different error before reaching it named,
        at its own line, a column that raised nothing on any frame; the
        answer is now "not narrowed".

        Args:
            start_index: Index at or before which failure is known to occur;
                the scan's last step.
            last_good_df: DataFrame with ops ``0..last_good_index`` applied.
            last_good_index: Largest op index already contained in
                ``last_good_df`` (``-1`` when it is the pristine baseline).
                The scan applies ops strictly AFTER this index — re-applying
                an op already present double-applies it, and a valid
                self-referential dtype-changing assignment then raises on
                its second application and gets blamed for another
                column's error.

        Returns:
            Exact index of the failing operation, or ``-1`` -- not narrowed
            -- when no one-operation step reproduced the failure: the scan
            broke on a different error first, or nothing it applied raised.
            ``_blame_within_group(-1)`` names nothing, and every caller of
            ``find_failing_operation`` treats ``(-1, None)`` as no
            attribution.

        """
        current_df = last_good_df.lazy()  # Convert to LazyFrame for operations

        for i in range(last_good_index + 1, start_index + 1):
            operation = self._get_operation_at(i)
            if operation is None:
                continue

            current_df = current_df.with_columns(*self._group_exprs(operation))
            try:
                # Test by collecting to see if it fails
                _ = current_df.collect()
                logger.trace(f"Operation {i} ({_group_columns(operation)}) succeeded")
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_same_error_type(e):
                    logger.debug(f"Exact failing operation found at index {i}")
                    return i
                # The plan now carries a different failure; every later
                # prefix would just re-raise it, so nothing past this step
                # can be tested. The position the binary search handed in
                # is not evidence of anything: not narrowed.
                logger.debug(f"Different error type at operation {i}; not narrowed")
                return -1

        logger.debug(f"No step up to operation {start_index} reproduced; not narrowed")
        return -1

    def _blame_within_group(self, index: int) -> CalculationRecord | None:
        """Name the calculation inside a failing operation that reproduces it.

        A single-column operation IS its calculation. A multi-column
        ``with_columns`` needs narrowing, and narrowing is legitimate here
        for the same reason grouping was required: every expression in one
        call is evaluated against the frame as it stood before the call, so
        applying a PREFIX of the call's expressions computes each of them
        exactly as the live call did. The prefix is still one
        ``with_columns`` — siblings are never fed each other's new values.

        Returns ``None`` when the operation cannot be narrowed (its prefix
        could not be rebuilt, or no prefix of it reproduces the failure),
        and for ``-1``, the exact-operation scan's "not narrowed", which
        names no operation at all. Per the fallback contract a caller must
        then attribute nothing: a wrong column name costs the user more
        than no column name.
        """
        operation = self._get_operation_at(index)
        if operation is None:
            return None
        if len(operation) == 1:
            return operation[0]

        try:
            base = self._apply_operations_up_to(index - 1).lazy()
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            logger.debug(f"Cannot rebuild the prefix of operation {index} to narrow it")
            return None

        blamed = self._reproducing_calculation(base, operation)
        if blamed is None:
            logger.debug(f"No column of operation {index} reproduces the failure alone")
        return blamed

    def _reproducing_calculation(
        self,
        base: pl.LazyFrame,
        operation: Sequence[CalculationRecord],
    ) -> CalculationRecord | None:
        """Return the first calculation of ``operation`` that reproduces on ``base``.

        Widening prefixes of the operation's expressions are applied to
        ``base`` as one ``with_columns`` each, which is how the frame
        applied the operation live. The first prefix that raises the same
        failure names its last expression; a prefix that raises a different
        failure masks every wider one, so the scan stops there and names
        nothing. ``None`` means no calculation of this operation reproduces
        the failure on this base.

        This is the CANDIDATE's narrowing, and stopping is its safe
        direction: the candidate must be the first reproducing expression
        in call order, and a different failure ahead of it means that
        cannot be told. A rival is any reproducing expression, so the
        ambiguity pass tests each on its own instead
        (``_reproductions_alone``).
        """
        for cut in range(1, len(operation) + 1):
            probe = base.with_columns(*self._group_exprs(operation[:cut]))
            try:
                _ = probe.collect()
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_same_error_type(e):
                    return operation[cut - 1]
                # A different failure now masks the one being diagnosed;
                # every wider prefix would just re-raise it.
                break
        return None

    def _reproductions_alone(
        self,
        base: pl.LazyFrame,
        operation: Sequence[CalculationRecord],
    ) -> list[CalculationRecord]:
        """Return every calculation of ``operation`` that reproduces on ``base`` alone.

        Each expression is applied to ``base`` on its own. Live, every
        expression of one call was evaluated against the frame as it stood
        before the call and never saw a sibling's new value, so one alone
        over ``base`` computes exactly what the live call computed for it.
        This is the RIVAL's scan: the candidate's
        (``_reproducing_calculation``) widens prefixes and stops at a
        different failure, and for a rival that stop meant "no rival" --
        a sibling raising a different class or line, first in the batch,
        hid the reproduction behind it and left a healed candidate named.
        """
        rivals: list[CalculationRecord] = []
        for record in operation:
            try:
                _ = base.with_columns(*self._group_exprs([record])).collect()
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_rival_error(e):
                    rivals.append(record)
        return rivals

    def _apply_operations_up_to(self, end_index: int) -> pl.DataFrame:
        """Apply operations from start to end_index (inclusive) efficiently.

        Each operation is applied as ONE ``with_columns`` holding every
        column it defined — the same shape the frame applied it in.

        Args:
            end_index: Last operation index to apply (inclusive)

        Returns:
            Resulting DataFrame after applying operations

        Raises:
            Exception: If any operation in the range fails

        """
        if end_index < 0:
            return self.original_df

        if end_index >= len(self.groups):
            end_index = len(self.groups) - 1

        # Check if we have any valid operations to apply
        valid_operations = [
            operation
            for i in range(end_index + 1)
            if (operation := self._get_operation_at(i)) is not None
        ]

        # If no valid operations, return original DataFrame
        if not valid_operations:
            return self.original_df

        # Start with the original DataFrame (already converted from LazyFrame)
        current_df = self.original_df.lazy()  # Convert to LazyFrame for operations

        for operation in valid_operations:
            current_df = current_df.with_columns(*self._group_exprs(operation))

        # Collect the result to DataFrame for return
        return current_df.collect()

    def _get_operation_at(self, index: int) -> list[CalculationRecord] | None:
        """Get the operation at ``index`` with bounds checking.

        An operation is every calculation one assignment call produced, so
        this returns a list: one entry for a setter assignment, several for
        a multi-column ``with_columns``.

        Args:
            index: Index of operation to retrieve

        Returns:
            Operation at index, or None if index is out of bounds

        """
        if 0 <= index < len(self.groups):
            return self.groups[index]
        return None

    @staticmethod
    def _group_exprs(group: Sequence[CalculationRecord]) -> list[pl.Expr]:
        """Return one operation's expressions, aliased to the columns they define.

        A method rather than a module-level helper so a subclass replaying
        at a different granularity inherits it instead of reaching across
        modules for a private name.
        """
        return [record.expr.alias(record.column) for record in group]

    def _is_same_error_type(self, exception: BaseException) -> bool:
        """Check if the given exception is the same type as the original error.

        Args:
            exception: Exception to check

        Returns:
            True if exception types match

        """
        return isinstance(exception, self.exception_type)

    def _is_rival_error(self, exception: BaseException) -> bool:
        """Return whether a sibling's replayed failure counts as a second reproduction.

        The base finder has one standard, the class, for candidates and
        rivals alike; the attribution finder loosens this one and only
        this one (see its override).
        """
        return self._is_same_error_type(exception)


# Error classes eligible for collect-time column attribution (#39). The
# class is the coarse admission test and no longer the narrow one: for the
# three shape classes and for ``ComputeError`` -- polars' catch-all, and the
# class the two commonest actuarial mistakes arrive as, an assumption-table
# lookup miss and a jagged-list clash -- what makes a replay evidence is the
# leading-line check in ``_AttributionReplayFinder`` (the replayed error must
# open with the same first line the original did), and where a first line
# cannot tell two calculations apart, the ambiguity pass that refuses to
# name either. A wrong column name still costs the user more than no column
# name; the line check and the refusal are what carry that promise now, so
# the class list carries reach instead.
_ATTRIBUTABLE_ERRORS = (
    pl.exceptions.ShapeError,
    pl.exceptions.InvalidOperationError,
    pl.exceptions.SchemaError,
    pl.exceptions.ComputeError,
)

# Replay baseline row cap. Attribution re-collects real data several times;
# uncapped, a 100K-policy failure would multiply the failed run's full cost
# on the error path (the edit-run-refine loop principle). Shape failures
# overwhelmingly reproduce within the head; one that does not simply yields
# no attribution.
_REPLAY_MAX_ROWS = 10_000


class _AttributionReplayFinder(ErrorBoundaryFinder):
    """Stricter finder for default-mode collect attribution (#39).

    Class-only matching can pair column A's name with column B's message
    when two operations raise the same exception class. Attribution
    therefore also requires the first line of the replayed message to match
    the original's — a mismatch means "not certainly the same failure",
    which per the fallback contract yields no attribution rather than a
    self-contradictory one. The one exception is a line on the closed
    allowlist of Polars' batch-counted lines (``_POLARS_BATCH_LINES``),
    matched by its template.
    """

    def _is_same_error_type(self, exception: BaseException) -> bool:
        """Return whether ``exception`` is the candidate's failure: the line check.

        The same class and the same first line, byte for byte -- or, for a
        line on the closed allowlist of Polars' batch-counted lines
        (``_POLARS_BATCH_LINES``), the same class with both first lines
        fitting the same template, their digits read as the batch's. That is
        the exact check relaxed for that one line and nothing else; what
        it protects holds, because a name still comes only from a single
        reproduction (``later_reproductions`` refuses two) and a sealed
        candidate is still confirmed on the kept rows by the exact helper.

        A refusal the plan raised (``require_valid_rows``) is matched by the
        sentences it reported, which are the framework's own and the same in
        every batch; the column and counts on its line are the batch's, so a
        streaming run's ``1 out of 3`` and the replay's ``1 out of 12`` are
        one refusal. A strict cast of a book column -- text parsed as a date --
        is matched by the column and the two types it names; the counts and
        the values it samples are the batch's.
        """
        if self._same_line_exactly(exception):
            return True
        if not isinstance(exception, self.exception_type):
            return False
        refused = _plan_refusal_sentences(self.exception)
        if refused and refused == _plan_refusal_sentences(exception):
            return True
        cast = _strict_cast_of_a_column(self.exception)
        if cast is not None and cast == _strict_cast_of_a_column(exception):
            return True
        template = _polars_batch_line(self.exception)
        return template is not None and template is _polars_batch_line(exception)

    def _same_line_exactly(self, exception: BaseException) -> bool:
        """Return whether ``exception`` is the original's class and exact first line.

        The standard ``confirmed_on_kept_rows`` tells a match on the digit
        mask alone from, whatever the candidate matcher admits.
        """
        if not isinstance(exception, self.exception_type):
            return False
        return _first_line(self.exception) == _first_line(exception)

    def _is_rival_error(self, exception: BaseException) -> bool:
        """Return whether ``exception`` is the original's class and line, digits masked.

        The rival test, and only the rival test: the candidate is still
        found by the matcher above, exact but for the allowlisted Polars
        line. A ``ShapeError``'s first line
        carries the row index of the frame it ran on, so a rival's jag at
        index 1 of the unfiltered baseline and the original's at index 0
        of the plan the user collected read as two lines to an exact
        compare and as one line here. A looser rival test can only add
        rivals, and a name is returned only when there are none, so masking
        can only refuse more and never name more. What it spends is two
        genuine breaks whose lines differ only in a digit -- a row index, a
        length, a digit in a table's name -- refused rather than the first
        named, which is the trade the lookup line already makes.
        """
        if not isinstance(exception, self.exception_type):
            return False
        return _digits_masked(_first_line(exception)) == _digits_masked(
            _first_line(self.exception)
        )

    def confirmed_on_kept_rows(
        self,
        index: int,
        candidate: CalculationRecord,
        operations: Sequence[StructuralOperation],
    ) -> bool:
        """Return whether ``candidate`` breaks on the rows ``operations`` keep.

        The candidate alone, over the prefix of operations before its own,
        on the window's uncapped plan, is run through every structural
        operation the plan then went through and collected on the replay's
        head of the rows that survive. Raising the failure's class and
        shape there -- ``_is_rival_error``'s digit-masked compare -- means
        it broke on a row the plan the user collected computed; collecting
        means the operation healed it, and it is not evidence. Why a sealed
        candidate is confirmed at all is ``search_collect_failure``'s.

        Why the compare masks digits: a ``ShapeError``'s row index is not a
        fact about the user's data, and the two engines do not number the
        offending row the same way -- the streaming engine reports it
        within the chunk it was computing, the in-memory replay within the
        frame the filter left -- so an exact compare read a genuine
        kept-row break as a different failure. The observation itself,
        engine by engine and shape by shape, is
        ``test_the_two_engines_number_the_offending_row_differently``'s.

        What the mask widens, and what that costs: it can only confirm
        more, never name a candidate the exact scan did not find, and
        cannot heal a rival, because rivals end the search before
        confirmation. It CAN read a structural operation's own break as the
        candidate's -- a ``select``, a sort key or a filter predicate
        carrying list arithmetic of its own raises the same class and, one
        digit apart, the same line, on a row it keeps. So a match on the
        mask alone asks one more question, ``_operations_break_alone``, and
        confirms only when the operations do not raise it without the
        candidate. A line that matches exactly (``_same_line_exactly``)
        asks nothing further; one the candidate matcher admitted on Polars'
        allowlisted template alone is a match on its digits and asks it too.

        An operation the candidate cannot be re-run through -- a predicate
        reading a column recorded after it, which the plan here does not
        hold, or an operation that came through a pickle without its
        callable -- raises something else, and the answer is ``False`` with
        the reason in the debug log: the window declines to name rather
        than naming on evidence it could not check.

        Every replay in this module collects on polars' default engine; the
        live collect streams. The rows a filter keeps do not depend on the
        engine, and the head is the first of them in plan order either way.
        """
        if self.baseline_plan is None:
            logger.debug(
                f"{candidate.column!r}: no plan to re-run through the window's "
                "operations; not confirming it on the kept rows"
            )
            return False
        kinds = ", ".join(operation.kind for operation in operations)
        try:
            plan = self._plan_through(self.baseline_plan, index, candidate, operations)
            _ = plan.limit(_REPLAY_MAX_ROWS).collect()
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            if self._is_rival_error(e):
                masked_only = not self._same_line_exactly(e)
                if masked_only and self._operations_break_alone(index, operations):
                    logger.debug(
                        f"({kinds}) raise the failure's class and shape on the rows "
                        f"they keep with {candidate.column!r} left off the plan: the "
                        "operation broke on its own, so the masked match is not "
                        "evidence about the candidate; naming nothing"
                    )
                    return False
                logger.debug(
                    f"{candidate.column!r} reproduces on the rows ({kinds}) kept; "
                    "confirmed"
                )
                return True
            reason = str(e).split("\n", 1)[0]
            logger.debug(
                f"{candidate.column!r} re-run through ({kinds}) raised "
                f"{type(e).__name__} ({reason}) rather than the failure under "
                "diagnosis; the sealed window cannot confirm it on the kept rows "
                "and names nothing"
            )
            return False
        logger.debug(
            f"{candidate.column!r} collects on the head of the rows ({kinds}) "
            "kept: healed by the operation, not evidence; naming nothing"
        )
        return False

    def _operations_break_alone(
        self,
        index: int,
        operations: Sequence[StructuralOperation],
    ) -> bool:
        """Return whether ``operations`` raise the failure's shape on their own.

        The confirmation puts the candidate on the plan and runs the whole
        chain, so an operation carrying list arithmetic of its own can
        raise the failure's class and, digits masked, its line, on a row it
        keeps -- and the mask cannot tell that raise from the candidate's.
        This asks what the mask cannot: the same prefix through the same
        operations with the candidate left off. A raise there is the
        operation's own break, and the candidate is not confirmed by it.

        An operation that READS the candidate raises something else without
        it -- a missing column -- which is not this question's answer and
        leaves the confirmation standing.

        A decline can cost a name that was right, when the candidate and
        the operation are both broken on the rows kept. That is the
        direction a name the window cannot stand behind has to go.
        """
        if self.baseline_plan is None:
            return False
        try:
            plan = self._plan_through(self.baseline_plan, index, None, operations)
            _ = plan.limit(_REPLAY_MAX_ROWS).collect()
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            return self._is_rival_error(e)
        return False

    def _plan_through(
        self,
        plan: pl.LazyFrame,
        index: int,
        candidate: CalculationRecord | None,
        operations: Sequence[StructuralOperation],
    ) -> pl.LazyFrame:
        """Return ``plan`` with only ``candidate`` over its prefix, then ``operations``.

        The operations before the candidate's own are applied whole, as the
        frame applied them; the candidate goes on alone, so a sibling's or a
        later record's failure cannot stand in for its own; then each
        structural operation in turn, the frame's own callables. A
        ``candidate`` of ``None`` leaves it off the plan, which is how
        ``_operations_break_alone`` asks its question.
        """
        for position in range(index):
            operation = self._get_operation_at(position)
            if operation is not None:
                plan = plan.with_columns(*self._group_exprs(operation))
        if candidate is not None:
            plan = plan.with_columns(*self._group_exprs([candidate]))
        for structural in operations:
            plan = structural.applied_to(plan)
        return plan

    def later_reproductions(self, index: int) -> list[CalculationRecord]:
        """Name every calculation after operation ``index`` that also reproduces it.

        The scan stops at the first operation that reproduces the class and
        the leading line, and "first" is a fact about the order the model
        wrote its columns in, not about which of them failed: two lookups
        on one table with one key name raise byte-identical first lines,
        and when the earlier one is healed at run time by a later
        ``filter()``'s predicate pushdown, the scan names it -- a column
        that never failed. So after a candidate is found, every LATER
        operation in the window is replayed on its own over the known-good
        prefix that precedes the candidate, with the candidate and the
        operations between excluded. One that raises the same class and
        leading line -- digits masked, which is ``_is_rival_error``'s
        looser standard for a rival and not the candidate's -- is a second
        reproduction, and the window is ambiguous. One that raises anything
        else -- a missing column, because it read the excluded candidate; a
        different first line -- is not a second reproduction, and neither
        is one that succeeds.

        A multi-column operation is tested one expression at a time over
        the prefix (``_reproductions_alone``), and every expression that
        reproduces is a rival, named as a calculation rather than as a
        batch. Siblings in one call never see each other's values, so each
        alone over the prefix is exactly what the live call computed for
        it. It is NOT narrowed the way ``_blame_within_group`` narrows the
        candidate: that scan widens prefixes and stops at a different
        failure, which for a candidate names nothing (the safe direction)
        and for a rival meant "no rival" -- a strict cast failing only on
        the dropped row, first in a batch whose second expression was the
        real break, hid it, and the healed candidate stood.

        The prefix is rebuilt from the baseline rather than reused from the
        scan: the binary search's last good frame is not always the frame
        one step before the candidate.
        """
        if index + 1 >= len(self.groups):
            return []
        prefix = self._apply_operations_up_to(index - 1).lazy()
        return [
            rival
            for later in range(index + 1, len(self.groups))
            for rival in self._reproductions_alone(prefix, self.groups[later])
        ]


@dataclass(frozen=True, slots=True)
class AmbiguousAttribution:
    """The replay reproduced the failure from two or more definitions; it names none.

    ``reproducing`` holds every recorded calculation whose replay raised the
    original error's class and leading line, in log order, the scan's
    candidate first. They reproduce the failure under replay; that is all
    the replay knows about them, and it is not the same as failing --
    a calculation healed at run time by a later structural operation
    reproduces on the window's baseline and never raised in the plan the
    user collected. A caller prints them as reproducing, never as failing,
    and names no column.
    """

    reproducing: tuple[CalculationRecord, ...]


def _head_collects(plan: pl.LazyFrame | None) -> bool:
    """Return True when the first ``_REPLAY_MAX_ROWS`` rows of ``plan`` collect.

    The fact ``search_collect_failure``'s ending turns on, read straight
    from a plan for the live window that holds no records and so builds no
    finder. Any replayable failure means "does not collect"; anything else
    -- an interrupt, a foreign panic -- propagates.
    """
    if plan is None:
        return False
    try:
        _ = plan.limit(_REPLAY_MAX_ROWS).collect()
    except BaseException as e:  # panic-aware probe, guarded below
        if not _replayable(e):
            raise
        return False
    return True


# The debug line both endings of the search share: a window that was
# searched and reproduced nothing, and a live window with no records whose
# plan collects on its head. The reason is `search_collect_failure`'s.
_ENDS_THE_SEARCH = (
    "Attribution window's baseline collected on its head and nothing in it "
    "reproduced; not consulting the windows behind it"
)


class SearchOutcome(NamedTuple):
    """What the search found, and the frame the named calculation was applied to.

    ``attribution`` is the finder's answer -- a record, a refusal, or
    ``None`` -- and the whole of what a caller that wants only the answer
    reads; the ``None`` contract is :func:`search_collect_failure`'s.
    ``last_good`` travels with a name only: the eager frame the named
    operation was applied to, which the traced run's panel previews as the
    state before the error. ``None`` for a refusal and for nothing found,
    since there is then no state a panel could honestly show.
    """

    attribution: CalculationRecord | AmbiguousAttribution | None
    last_good: pl.DataFrame | None


_NOTHING_FOUND = SearchOutcome(attribution=None, last_good=None)


def _operations_behind(
    windows: Sequence[ReplayWindow], position: int
) -> tuple[StructuralOperation, ...]:
    """Return the operations from ``windows[position]``'s seal to the live plan.

    Windows are newest first, so the chain reads the sealed windows from
    ``position`` back towards the live one, each window's own operations in
    order. Empty for the live window, which no operation has followed.
    """
    return tuple(
        operation
        for window in reversed(windows[1 : position + 1])
        for operation in window.operations
    )


def _search_window(
    af: ActuarialFrame,
    exception: BaseException,
    window: ReplayWindow,
    operations: Sequence[StructuralOperation],
    steps: Sequence[_OpeningStep] = (),
) -> SearchOutcome | None:
    """Search one window; ``None`` means it could not be searched and hands on.

    Every other answer ends the search: a name, a refusal, or a searched
    window that names nothing -- the reasons are ``search_collect_failure``'s.
    A candidate in a sealed window (``operations`` non-empty) is confirmed
    on the rows those operations keep before it is named, and one that is
    not confirmed ends the search bare. A refusal needs no confirmation: a
    healed candidate among the reproducing definitions is still one that
    reproduces under replay, which is all the line claims.

    ``steps`` are the replayed materialisations a window a rollforward
    opened begins with (``_opening_steps``); a step the replay names is
    named by the record it was replayed on behalf of, its reader.
    """
    finder = _AttributionReplayFinder(
        af, exception, max_rows=_REPLAY_MAX_ROWS, window=window
    )
    if not finder.baseline_usable:
        # No standing: this window's plan does not rebuild, so a replay
        # would run against a substituted frame and could reproduce the
        # failure out of calculations that are sound.
        logger.debug("Attribution window's baseline does not collect; not replaying it")
        return None
    index, failing_op, last_good = finder.find_failing_operation()
    if failing_op is None:
        # Searched, and nothing reproduced. This window's baseline collected
        # on its head with every older record applied on the rows that
        # survive its structural operation, so anything a window behind it
        # could reproduce is on a row -- or, under projection pushdown, a
        # column -- the live plan never computed. That is not evidence about
        # the failure the user saw: end here rather than hand on.
        logger.debug(_ENDS_THE_SEARCH)
        return _NOTHING_FOUND
    rivals = finder.later_reproductions(index)
    if rivals:
        reproducing = _owned_by_readers((failing_op, *rivals), steps)
        if len(reproducing) > 1:
            logger.debug(
                f"{len(reproducing)} calculations reproduce the failure; naming none"
            )
            return SearchOutcome(AmbiguousAttribution(reproducing=reproducing), None)
        # Two of a window's opening steps reproduced, both read by one
        # record: one definition, so it is named, with the head before the
        # steps as the frame its run's inputs are read over.
        return SearchOutcome(_owner(failing_op, steps), finder.original_df)
    if operations and not finder.confirmed_on_kept_rows(index, failing_op, operations):
        return _NOTHING_FOUND
    return SearchOutcome(_owner(failing_op, steps), last_good)


@dataclass(frozen=True, slots=True)
class _OpeningStep:
    """One rollforward materialisation a window opened on, replayed as its step.

    ``step`` is the record the replay applies: the reader's record with the
    hidden struct's name and the kernel's expression in place of its own.
    ``reader`` is the record whose assignment materialised the struct -- the
    first of the window's records to read it -- and the one a reproduction
    by the step is named by.
    """

    step: CalculationRecord
    reader: CalculationRecord


def _owned_by_readers(
    records: Sequence[CalculationRecord], steps: Sequence[_OpeningStep]
) -> tuple[CalculationRecord, ...]:
    """Return ``records`` with each opening step read as its reader, once each.

    A step the window replays on a record's behalf is named by that record.
    Two steps one record reads are that one record, and a reader is listed
    once however many of its steps reproduced.
    """
    owned: list[CalculationRecord] = []
    for record in records:
        owner = _owner(record, steps)
        if all(owner is not seen for seen in owned):
            owned.append(owner)
    return tuple(owned)


def _owner(
    record: CalculationRecord, steps: Sequence[_OpeningStep]
) -> CalculationRecord:
    """Return the reader ``record`` was replayed for, or ``record`` itself."""
    return next((s.reader for s in steps if s.step is record), record)


def _reads(record: CalculationRecord, name: str) -> bool:
    """Return whether ``record``'s expression reads the column ``name``."""
    try:
        return name in record.expr.meta.root_names()
    except Exception:  # noqa: BLE001 -- meta inspection is best-effort
        return False


def _opening_steps(
    af: ActuarialFrame, window: ReplayWindow
) -> tuple[ReplayWindow, tuple[_OpeningStep, ...]] | None:
    """Rebuild a window a rollforward opened from before its struct, if it was one.

    A frame runs a compiled rollforward as a hidden struct column it puts on
    the plan when the first reader is assigned. That is a structural
    operation with no record of its own, so it seals the window before it
    and opens the next over the plan that already holds the struct
    (``ActuarialFrame._ensure_rollforward_sources``). When the rollforward
    is what breaks, that baseline holds the break and never collects, and
    the sealed window behind it replays clean: nothing was named, in either
    engine.

    So the window is rebuilt from the plan before the struct, and the
    materialisation is replayed as its first step. The struct that opened
    the window is the one the frame noted at the window's start
    (``_rollforward_runs``); the plan before it is the window's baseline
    less that column, which Polars' projection pushdown prunes the unread
    kernel from. If it ever stops pruning, the rebuilt baseline does not
    collect, the search passes over it, and the answer is bare, as before.
    Each step is owned by its reader: the first record of the window that
    reads the struct, which is the record whose assignment materialised it.

    ``None`` when the window was not opened by a rollforward, or a struct it
    opened on has no reader among its records (only a ``filter`` read it,
    say): there is then no record a reproduction could honestly be named by.
    """
    runs: dict[str, int] = getattr(af, "_rollforward_runs", None) or {}
    start = getattr(af, "_window_start", None)
    baseline = window.baseline
    if not runs or start is None or not window.records:
        return None
    if not isinstance(baseline, pl.LazyFrame):
        return None
    try:
        held = set(baseline.collect_schema().names())
    except BaseException as e:  # panic-aware probe, guarded below
        if not _replayable(e):
            raise
        return None
    opening = [name for name, at in runs.items() if at == start and name in held]
    if not opening:
        return None
    from gaspatchio.rollforward import _registry  # noqa: PLC0415 -- import cycle

    steps: list[_OpeningStep] = []
    for order, name in enumerate(opening):
        reader = next((r for r in window.records if _reads(r, name)), None)
        if reader is None:
            logger.debug(f"{name}: no record of the window reads it; not replaying it")
            return None
        step = replace(
            reader,
            column=name,
            expr=_registry.plugin_expr_for(name),
            operation_id=-(order + 1),
        )
        steps.append(_OpeningStep(step=step, reader=reader))
    rebuilt = ReplayWindow(
        records=[opening_step.step for opening_step in steps] + window.records,
        baseline=baseline.drop(opening),
    )
    return rebuilt, tuple(steps)


def _search_from_before_the_rollforward(
    af: ActuarialFrame, exception: BaseException, window: ReplayWindow
) -> SearchOutcome | None:
    """Search the live window from before the rollforward that opened it.

    Asked only when the live window's own baseline did not collect. A name
    or a refusal is the answer; anything else -- the window was not opened
    by a rollforward, its rebuilt baseline does not collect either, or
    nothing reproduces -- hands on as the unusable window did before, so
    this can only add an answer and never take one away.
    """
    opened = _opening_steps(af, window)
    if opened is None:
        return None
    rebuilt, steps = opened
    outcome = _search_window(af, exception, rebuilt, (), steps)
    if outcome is None or outcome.attribution is None:
        return None
    return outcome


def search_collect_failure(
    af: ActuarialFrame,
    exception: BaseException,
) -> SearchOutcome:
    """Search the frame's windows for the calculation that reproduces a failure.

    Replays the frame's attribution windows, newest first, each against
    the baseline that window opened over (row-capped, via
    :class:`_AttributionReplayFinder`), until one of them can be searched;
    a searched window's answer is the answer, whether or not an operation
    in it reproduces the same error class AND leading message. The answer
    is the reproducing operation's own :class:`CalculationRecord` — which
    column, which of its definitions, and the statement in the user's
    source that wrote it — or ``None`` whenever attribution is not certain:
    unknown error class, no windows to search, a window whose own baseline
    plan will not rebuild, a replay that does not reproduce the error, a
    multi-column operation no single column of which reproduces it, a
    sealed candidate that does not reproduce on the rows the plan kept, or
    any failure inside the replay itself. Callers must treat ``None`` as
    "re-raise the original error untouched".

    One outcome is neither: a window in which a LATER calculation also
    reproduces the class and leading line
    (:meth:`_AttributionReplayFinder.later_reproductions`). Two definitions
    then stand as evidence for one failure and the order they were written
    in is all that separates them, so the answer is
    :class:`AmbiguousAttribution` naming both as reproducing — a caller
    says so in one line and names no column. That is the refusal a wrong
    name is traded for.

    A window that cannot rebuild its own plan is passed over rather than
    replayed. The frame substituted for an uncollectible baseline carries
    the model's input dtypes, so healthy arithmetic replayed against it can
    reproduce the failure's class AND its leading line — the whole standard
    of proof — and name a column that never failed. A window behind a break
    is usually in exactly that position; the exception is a break the
    replay's ``_REPLAY_MAX_ROWS`` head never reaches, where the window
    stays usable, is searched, and reproduces nothing — and the answer is
    then bare, which is the direction the cap promises.

    The live window is searched first, so a break written after a
    ``filter()`` is answered by the calculation that made it and never by
    an older one. Only when a window could NOT be searched — its baseline
    would not collect — does the search walk back to the window behind
    it; a window that was searched and reproduced nothing ENDS the search.
    Its baseline collected on its head with every older record applied on
    the rows that survive its structural operation, so any reproduction an
    older window offers is on a row (or, under projection pushdown, a
    column) the live plan never computed: a lookup that misses only on the
    row a later ``filter()`` drops reproduces on the unfiltered baseline
    and never raised in the plan the user collected. That is not evidence
    about the failure the user saw, and the framework says nothing rather
    than something that looks right. A live window with no records and a
    window behind it ends the search the same way when the plan the user
    collected — which is its baseline — collects on its head, every
    recorded calculation being healthy there, and hands on when it does
    not. The walk-back is the path that costs a replay per window, and
    the path a frame with no structural operations never takes.

    A sealed window that is searched and reproduces something is one more
    place the same reason applies, one row-cap further out. Its head is the
    first rows of its own baseline; the live head is the first rows of the
    plan the user collected, which under a filter reach past the sealed
    head by however many rows the filter dropped. A break on a surviving
    row in that band fails the live baseline and is passed over, and the
    sealed head then holds only the sibling the filter healed. So a sealed
    candidate is confirmed before it is named
    (:meth:`_AttributionReplayFinder.confirmed_on_kept_rows`): alone over
    its prefix, run through the structural operations recorded on the
    window from its seal to the live plan, capped at the head of the rows
    they keep. A candidate that raises there broke on a row the plan
    computed; one that collects was healed by the operation, is not
    evidence, and the answer is bare. Both entry paths -- a live baseline
    that fails to collect, an empty live window whose head fails -- reach
    the sealed search, so the confirmation lives there and in neither
    branch.

    One window that cannot rebuild its own plan is asked once more before
    it is passed over: the live window, when a compiled rollforward opened
    it. Its baseline then holds the rollforward's kernel, which is usually
    what broke, so it is rebuilt from the plan before the struct and the
    materialisation replayed as its first step
    (:func:`_opening_steps`). A reproduction by that step is named by its
    reader, the record whose assignment put the run on the plan; anything
    short of a name or a refusal hands on exactly as the unusable window
    did, so the rebuild can add an answer and never take one away.

    Replay never mutates the live frame: the finder works on eager copies
    collected from the baseline plan.

    Args:
        af: The frame whose ``collect()``/``profile()`` raised.
        exception: The exception raised by the failed execution.

    Returns:
        The attribution, with the frame the named calculation was applied
        to when there is one.

    """
    if not (
        isinstance(exception, _ATTRIBUTABLE_ERRORS) or is_plan_lowering_panic(exception)
    ):
        return _NOTHING_FOUND
    windows = replay_windows(af)
    for position, window in enumerate(windows):
        if not window.records:
            # Nothing to replay, but this window's baseline is the plan the
            # user collected, and whether its head collects is the fact the
            # ending below turns on. Read `af._df`, the current plan:
            # `_baseline_df` is stale after a seal until the next record
            # lands. If the head collects, every recorded calculation is
            # healthy on it and the failure is past the head -- the same
            # ending as a searched window that reproduced nothing. If it
            # does not, hand on as before. The collect exists to decide
            # whether to hand on, so with no window behind there is nothing
            # to decide and the plan is not collected (a failed collect with
            # nothing recorded stays one collect: `test_base.py`'s
            # `test_collect_handles_polars_error`).
            has_behind = position + 1 < len(windows)
            if not has_behind or not _head_collects(af._df):  # noqa: SLF001
                continue
            logger.debug(_ENDS_THE_SEARCH)
            break
        try:
            outcome = _search_window(
                af, exception, window, _operations_behind(windows, position)
            )
            if outcome is None and position == 0:
                outcome = _search_from_before_the_rollforward(af, exception, window)
        except BaseException as replay_error:  # never make the error worse
            if not _replayable(replay_error):
                raise
            logger.debug("Collect-error attribution replay failed; passing through")
            return _the_refusal_s_own_line(windows, exception)
        if outcome is not None:
            if outcome.attribution is None:
                return _the_refusal_s_own_line(windows, exception)
            return outcome
    return _the_refusal_s_own_line(windows, exception)


def _the_refusal_s_own_line(
    windows: Sequence[ReplayWindow], exception: BaseException
) -> SearchOutcome:
    """Return the one calculation whose plan carries the operation that failed.

    Where a replay reproduced nothing -- the failing row sits past the
    replay's head, in a book of more than ``_REPLAY_MAX_ROWS`` policies --
    some failures still say which operation raised them, and the line is the
    one calculation whose expression holds it:

    - a refusal the lazy plan raised (``require_valid_rows``) carries a
      sentence written into exactly the calculation that checks it;
    - Polars' ``get index is out of bounds`` comes only from a strict read
      by position, ``.list.get(``;
    - a strict cast of a named column -- text parsed as a date, or as a
      date and time in any unit and zone -- names the column it read,
      ``col("<name>").str.strptime(``.

    None where the failure is none of these, or where no one calculation, or
    more than one, holds the operation: two candidates name neither.
    """
    markers = _what_the_failure_names(exception)
    if not markers:
        return _NOTHING_FOUND
    owners = [
        record
        for window in windows
        for record in window.records
        if all(marker in str(record.expr) for marker in markers)
    ]
    if len(owners) != 1:
        return _NOTHING_FOUND
    return SearchOutcome(attribution=owners[0], last_good=None)


# Polars' one line for a strict read by position that finds no value.
_POSITION_NOT_HELD = "get index is out of bounds"
# A strict cast's two types where text was parsed by ``str.strptime``: to a
# date, or to a date and time in any unit and zone (``datetime[μs, UTC]``).
_A_DATE_PARSE = re.compile(r"`str` to `(?:date|datetime\[[^`]*\])`")


def _what_the_failure_names(exception: BaseException) -> frozenset[str]:
    """Return the text an expression holds where it is the failure's operation."""
    sentences = _plan_refusal_sentences(exception)
    if sentences:
        return sentences
    if (
        isinstance(exception, pl.exceptions.ComputeError)
        and _first_line(exception).strip() == _POSITION_NOT_HELD
    ):
        return frozenset({".list.get("})
    cast = _STRICT_CAST_LINE.fullmatch(_first_line(exception))
    if (
        isinstance(exception, pl.exceptions.InvalidOperationError)
        and cast is not None
        and cast.group(2) != "literal"
        and _A_DATE_PARSE.search(cast.group(1)) is not None
    ):
        return frozenset({f'col("{cast.group(2)}").str.strptime('})
    return frozenset()
