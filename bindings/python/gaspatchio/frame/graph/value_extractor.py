# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Sample value extraction from DataFrames for calculation graphs.

This module handles extracting and formatting sample values from Polars DataFrames.
"""

from __future__ import annotations

import datetime
import math
import re
from typing import TYPE_CHECKING, Any, Final, cast

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from polars import DataFrame

    from gaspatchio.typing import PolarsDataType


# How many of the ids the frame does hold a refusal reads back. Enough to see
# the shape of the identifier -- a dropped leading zero, a number where a
# string was expected -- without printing a model-point file at somebody.
_IDS_SHOWN: Final[int] = 5

# The name an evaluated expression is given for the one select that reads
# it. It never reaches the wire -- the value does, under the field that
# asked for it -- and it is spelled once here so that the select and the
# read cannot drift apart.
_EVALUATED: Final[str] = "__evaluated__"

# One value as a document writes it: what :func:`one_value_on_the_wire` turns
# any cell into. A per-period value is a list of them, in period order.
_WireScalar = float | int | str | bool | None
_WireValue = _WireScalar | list["_WireValue"]

# How a non-finite f64 travels (section 10): a string naming itself,
# wherever a value appears. JSON has no token for one, and null is spoken
# for -- it means "no value here", where a NaN or an infinity is a value the
# column holds. The column's declared ``f64`` is what keeps the string
# unambiguous.
_NAN_ON_THE_WIRE: Final[str] = "NaN"
_INFINITY_ON_THE_WIRE: Final[str] = "Infinity"
_NEGATIVE_INFINITY_ON_THE_WIRE: Final[str] = "-Infinity"


def non_finite_on_the_wire(value: float) -> str:
    """Return the sentinel section 10 writes for one non-finite float."""
    if math.isnan(value):
        return _NAN_ON_THE_WIRE
    return _INFINITY_ON_THE_WIRE if value > 0 else _NEGATIVE_INFINITY_ON_THE_WIRE


def spelled_for_the_wire(value: object) -> object:
    """Return ``value`` with each non-finite float in it spelled as section 10 says.

    For a value a calculation already holds in wire form apart from that one
    question -- a walk-through's operands and its result, which are read as
    numbers while the walk-through is written and are written only at the
    end. Lists and mappings are walked; everything else is returned as it is.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return non_finite_on_the_wire(value)
    if isinstance(value, list):
        return [spelled_for_the_wire(item) for item in value]
    if isinstance(value, dict):
        return {key: spelled_for_the_wire(item) for key, item in value.items()}
    return value


def one_value_on_the_wire(value: object) -> _WireScalar:
    """Return one value -- never a run of them -- in the shape the document writes.

    The one place a sampled number's formatting is decided, so that every
    value in a document is written the same way whichever reading produced
    it. A policy's number comes off a frame and the book's fold comes off a
    batched driver, and a reader comparing the two should not have to
    notice that one of them was written differently from the other.

    **A float is the number, not a display of it.** It travels as the full
    binary64 value the column held, and JSON writes it as the shortest
    decimal that reads back to that same double, so a sample parsed out of
    the document is bit for bit the cell in the results file. It used to be
    rounded to six decimal places, and a reader rebuilding a timeline from
    the artifact then matched only some of its cells against the run that
    wrote it: a monthly rate of ``0.0008712345`` reached them as
    ``0.000871``, and a check at ``1e-9`` called an honest book wrong.
    Rounding for reading is the viewer's business, and it does it.

    Args:
        value: What was read, of whatever type the column holds.

    Returns:
        The value as JSON carries it: a float as the full binary64 value, a
        NaN or an infinity as section 10's sentinel (``"NaN"``,
        ``"Infinity"``, ``"-Infinity"``), a date as its ISO text, a null,
        integer, string or boolean unchanged, and anything else as its own
        text.

    """
    if isinstance(value, float) and not math.isfinite(value):
        return non_finite_on_the_wire(value)
    return _as_a_number_is_read(value)


def _as_a_number_is_read(value: object) -> _WireScalar:
    """Return one value as the wire writes it, leaving a non-finite float a float.

    The reading a walk-through does its own arithmetic on: it measures a run
    -- which way it moves, how many periods hold no number, how many a
    negative one -- and a NaN it can recognise is a period without a number
    where the text ``"NaN"`` would be a word. Its values are spelled for the
    wire when the walk-through is written (:func:`spelled_for_the_wire`).
    """
    if isinstance(value, float):
        # Exactly the double the column held. ``float`` drops a NumPy
        # subclass's type and changes no bit of the value.
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (int, str, bool)):
        return value
    return str(value)


class PolicyNotInFrameError(ValueError):
    """The policy the samples were asked for is not in the frame they come from."""


class PeriodNotInTimelineError(ValueError):
    """The period the samples were pinned to is past the end of the timeline."""


def _no_such_period(period: int, longest: int, policy_id: str | None = None) -> str:
    """Return the refusal for a period the projection never reaches.

    The message carries the length the timeline actually has, because the
    reader asking for period 120 of a 84-period run needs the number they
    got wrong and not only the news that they did.

    **Whose timeline is named is whose the document is about.** With a
    policy pinned the document is an account of one row -- the first the
    frame carries for that id -- so the length quoted is that row's own and
    the message says so. A jagged axis -- the default whenever the horizon
    is a term column -- has a period one row reaches and another does not,
    and a refusal measured against the longest of them would tell a reader
    their period was fine and then print nothing at it.

    **The row, not the policy.** A policy number on more than one row is
    this framework's own native shape: a scenario axis is a cross-join, and
    rider rows and multiple coverages under one number reach it the same
    way. On such a frame policy '1' runs to four periods on the row the
    samples come off and to ten on another, so "policy '1' runs to 4
    periods" is a claim the frame itself contradicts -- and the document
    being refused is an account of the one row, not of every row that
    carries the id. Both halves of the sentence say the row.
    """
    if longest == 0:
        return (
            f"Period {period} was asked for, and this model has no "
            "projection timeline to take a period of: every column on the "
            "frame holds one value per policy. Export without a period, or "
            "lay a projection axis first."
        )
    if policy_id is not None:
        return (
            f"Period {period} was asked for, and the row sampled for policy "
            f"{policy_id!r} runs to {longest} periods -- periods 0 to "
            f"{longest - 1}. This document is an account of that row -- the "
            "first the frame carries for that id -- so the period has to be "
            "one that row's own timeline reaches. Ask for one it does, "
            "export without a period, or pin a policy whose sampled row "
            "projects that far."
        )
    return (
        f"Period {period} was asked for, and the longest timeline in this "
        f"frame runs to {longest} periods -- periods 0 to {longest - 1}. "
        "Ask for one the projection reaches, or export without a period, "
        "which shows every period of every column."
    )


def _longest_timeline(frame: DataFrame) -> int:
    """Return the most periods any list column of ``frame`` holds.

    Zero where the frame has no list column at all, which is a model whose
    every column is one value per policy and has no period to take.
    """
    longest = 0
    for name, dtype in frame.schema.items():
        if isinstance(dtype, pl.List):
            lengths = frame[name].list.len().max()
            if isinstance(lengths, int):
                longest = max(longest, lengths)
    return longest


class SampleValueExtractor:
    """Extracts and formats sample values from DataFrames."""

    def __init__(
        self,
        df: DataFrame,
        policy_id: str | None = None,
        policy_id_column: str = "Policy number",
        period: int | None = None,
        pin: Sequence[tuple[str, Any]] | None = None,
    ) -> None:
        """
        Initialize the extractor with a DataFrame.

        Args:
            df: The DataFrame to extract values from
            policy_id: Optional policy ID for filtering
            policy_id_column: Name of the policy ID column
            period: The projection period every per-period sample is taken
                at, or None to take every period of the sampled row's own
                timeline -- which is what the envelope's ``periods: null``
                already states, and what the samples now carry. A pinned
                period past the end of the frame's timelines is refused
                rather than clamped: a reader who asked for month 120 of a
                84-month run wants to be told so, not handed month 83's
                value under month 120's name.
            pin: The column-and-value pairs naming the row the samples come
                off, from
                :mod:`~gaspatchio.frame.graph.row_identity`. **Read first,
                ahead of ``policy_id``**, because it is the stronger
                statement: it is the identity the export stamped on the book
                before the model ran and then found again in the frame the
                model handed back, so it holds on a book that names no
                policy at all and on a model that moved the rows. A pin is
                matched rather than counted, so it survives this export's
                own filter -- including one that explodes a per-period
                column into a row per period, where it selects that policy's
                rows and the first is taken, exactly as a pinned id always
                has.

        """
        self.df = df
        self.policy_id = policy_id
        self.policy_id_column = policy_id_column
        self.period = period
        self.pin = pin
        self._year_index = self._get_year_index()
        self._sampled_row = self._the_sampled_row()
        if period is not None:
            self._refuse_a_period_the_timeline_does_not_reach(period)

    def _wanted_id(self) -> int | str | None:
        """Return the pinned policy's id in the type the id column holds.

        A policy number arrives as text -- from a command line, from a URL,
        from a JSON field -- and the column it has to be matched against is
        whatever the model-point file happened to carry. Coercing the id to
        an integer and putting it against a column of strings is not a
        lookup miss but a comparison the engine refuses to make, and the
        refusal used to arrive as a caught exception one column at a time:
        every sample None, every trace absent, and nothing anywhere saying
        the pin had failed.

        So the id is read in the column's own type. None where no value of
        that type could be the id asked for -- a name against a column of
        numbers -- which matches no row and reaches the loud refusal below,
        the same place an id simply not in the file reaches.
        """
        if self.policy_id is None:
            return None
        dtype = self.df.schema.get(self.policy_id_column)
        if dtype is not None and dtype.is_numeric():
            try:
                return int(self.policy_id)
            except ValueError:
                return None
        return self.policy_id

    def _the_sampled_row(self) -> DataFrame | None:
        """Return the row the pinned policy is, or None where none is pinned.

        Read once, because every column's sample and the pinned period's
        refusal are all statements about the same one row, and a frame that
        answered them from two different filters could disagree with itself.

        **One row, because one row is what a sample is read from.** A policy
        number on more than one row is this framework's own native shape --
        a scenario axis is a cross-join, and rider rows and multiple
        coverages under one number reach it the same way -- so a duplicate
        is not refused. But the samples come off the first matching row, and
        a refusal measured over all of them measured a timeline nothing in
        the document is read from: two rows sharing a number and running
        four periods and ten put period 6 through, left every per-period
        node silent, and let the envelope go on saying the values had been
        read there. Narrowing here is what keeps the two statements about
        the same row.

        **A pin stands in where the book names no policy, and stands ahead of
        one where it does.** Such a book can still be walked --
        ``--policies :3`` asks nothing of an id -- and the row the stamp
        names is as much one row as a matched id is. It is read first
        because it is the identity that was carried through the run rather
        than matched after it: a model that moved its rows moved the id with
        them, and only the stamp says which row was selected. A pin the
        frame does not carry is an empty answer, the same one an id it does
        not carry gets.

        An empty frame is an answer: the row was pinned and matched nothing.
        """
        if self.pin is not None:
            return self._the_pinned_row()
        if self.policy_id is None or self.policy_id_column not in self.df.columns:
            return None
        wanted = self._wanted_id()
        if wanted is None:
            return self.df.head(0)
        try:
            return self.df.filter(pl.col(self.policy_id_column) == wanted).head(1)
        except Exception as e:  # noqa: BLE001 -- a comparison the engine refuses is a miss
            logger.trace(f"Could not match policy {self.policy_id!r}: {e}")
            return self.df.head(0)

    def _the_pinned_row(self) -> DataFrame:
        """Return the one row the export's row stamp names, or an empty frame.

        The pin was resolved against the frame the model handed back, where
        exactly one row carried it; this frame is that one narrowed by the
        export's own filter, so the answer here is one row or none. None is
        a cut that removed the selected row, and the nulls that follow are
        the truth about a row this export was asked not to look at.
        """
        narrowed = self.df
        for column, value in self.pin or ():
            if column not in narrowed.columns:
                return self.df.head(0)
            narrowed = narrowed.filter(pl.col(column) == value)
        return narrowed.head(1)

    def _refuse_a_period_the_timeline_does_not_reach(self, period: int) -> None:
        """Refuse a pinned period the timeline this document reports has not got.

        **Whose timeline that is depends on whether a policy is pinned.**
        With one pinned the document is an account of the row that id was
        sampled at, so the period is measured against that row's own run: a
        jagged axis is the default whenever the horizon is a term column,
        and a period the sampled row never reaches would otherwise be
        accepted, leave every per-period node without a value, and take
        every trace with it -- while the envelope went on saying the values
        had been read there.

        It is measured against :attr:`_sampled_row`, which is the row every
        sample is read from, so the refusal and the samples are statements
        about the same row rather than about the same filter. Measuring over
        every row an id matched reopened the defect above on any frame
        carrying that id twice.

        With no policy pinned the frame is the subject and the measure is
        the longest timeline it holds: a period one policy reaches is a
        period this export can honestly show, and what the sample says for a
        row that does not reach it is a null, which is the truth about that
        row.

        A policy pinned and not present is a policy problem rather than a
        period one. It is measured as the unpinned case here and refused,
        loudly and by name, where the values are read.

        Raises:
            PeriodNotInTimelineError: If the timeline does not reach
                ``period``.

        """
        longest = _longest_timeline(self.df)
        if longest == 0:
            raise PeriodNotInTimelineError(_no_such_period(period, 0))
        if self._sampled_row is not None and len(self._sampled_row) > 0:
            reaches = _longest_timeline(self._sampled_row)
            if period < 0 or period >= reaches:
                raise PeriodNotInTimelineError(
                    _no_such_period(period, reaches, self.policy_id)
                )
            return
        if period < 0 or period >= longest:
            raise PeriodNotInTimelineError(_no_such_period(period, longest))

    def _get_year_index(self) -> int | None:
        """Get the year filter index if present."""
        if "__filter_year_index__" in self.df.columns:
            # Written by the filter handler as `pl.lit(target_year - 1)`, so
            # the cell is an integer index into each list column.
            return cast("int", self.df["__filter_year_index__"][0])
        return None

    def extract(self, column_name: str) -> _WireValue:
        """
        Extract the sampled value of the specified column.

        One value for a column holding one per policy. For a per-period
        column, the pinned period's own value where one was pinned, and
        otherwise the sampled row's every period -- no window is taken, for
        the reason :meth:`_format_list_value` states.

        Args:
            column_name: The column to extract value from

        Returns:
            A formatted sample value suitable for JSON serialization

        """
        if column_name not in self.df.columns:
            logger.debug(f"Column {column_name} not in DataFrame")
            return None

        try:
            value = self._get_raw_value(column_name)
            return self._format_value(value)
        except IndexError as e:
            # A frame with no rows has no first row to read; every other
            # read here is guarded. A PolicyNotInFrameError is a refusal, not
            # a failed extraction, and is not caught: downgrading it to "no
            # sample for this column" would leave the document stating a
            # policy it holds not one value for.
            logger.trace(f"Could not extract sample value for {column_name}: {e}")
            return None
        except ValueError as e:
            if _PAST_THE_CALENDAR.fullmatch(str(e)) is None:
                raise
            raise ValueError(_a_date_past_the_calendar(column_name, str(e))) from e

    def _get_raw_value(self, column_name: str) -> object:
        """Get the raw value from the DataFrame.

        The pin first, because it is the identity that was carried through
        the run: where one is held the row is already settled and an id
        comparison beside it could only disagree with it.
        """
        if self.pin is not None:
            sampled = self._sampled_row
            if sampled is None or sampled.is_empty():
                return None
            return _first_value(sampled[column_name])
        if self.policy_id is not None:
            return self._get_policy_specific_value(column_name, self.policy_id)
        return _first_value(self.df[column_name])

    def _get_policy_specific_value(self, column_name: str, policy_id: str) -> object:
        """Get the value for one policy, or refuse where the frame has no such row.

        Reading the first row instead would put one policy's numbers under
        another policy's name: the document states which policy its samples
        were read from, and a stand-in makes that statement false in a way
        nothing else in the document records. So a policy asked for and not
        there is a loud miss, in the shape the framework already uses for
        one -- the id asked for, the column looked in, and some of the ids
        that are there.

        **Every way of failing to find the row arrives here.** An id the
        file does not carry and an id no value of the column's type could be
        are the same news to a reader, and the second used to be a
        comparison error caught one column at a time -- leaving the document
        with no values at all and no statement anywhere that the pin had
        failed, which is exactly the downgrade this refusal exists to stop.

        Raises:
            PolicyNotInFrameError: If ``policy_id`` matches no row.

        """
        if self.policy_id_column not in self.df.columns:
            return _first_value(self.df[column_name])

        filtered = self._sampled_row
        if filtered is not None and len(filtered) > 0:
            return _first_value(filtered[column_name])

        present = (
            self.df[self.policy_id_column]
            .unique(maintain_order=True)
            .head(_IDS_SHOWN)
            .to_list()
        )
        msg = (
            f"Policy ID {policy_id!r} is not in column "
            f"{self.policy_id_column!r}, so there are no values to sample for "
            f"it. Ids present include: {present}. Ask for one the frame "
            "carries, or ask for no policy at all -- the samples are then "
            "whichever policy the frame holds first, and the document says "
            "which one that was."
        )
        raise PolicyNotInFrameError(msg)

    def extract_whole(self, column_name: str) -> _WireValue:
        """Extract the sampled value with no narrowing taken out of it.

        The same read as :meth:`extract` and a different answer for a
        per-period column only where a period or a year filter was asked
        for: this one leaves both unapplied. It is what a walk-through is
        built from, because a walk-through has things to say about the run
        as a whole -- how long it is, where it ends, whether it ever turns
        negative -- that a single pinned period would have thrown away.

        Unpinned the two now agree, and deliberately: :meth:`extract` no
        longer takes a window out of a per-period column, so the sample a
        reader holds and the run a walk-through was written from are the
        same list of numbers.

        Args:
            column_name: The column to read the sampled policy's value from.

        Returns:
            The value, per-period columns whole, or None where the column
            is not on the frame or could not be read.

        """
        if column_name not in self.df.columns:
            logger.debug(f"Column {column_name} not in DataFrame")
            return None
        try:
            value = self._get_raw_value(column_name)
        except IndexError as e:
            # As in :meth:`extract`: only a frame with no rows lands here.
            logger.trace(f"Could not extract sample value for {column_name}: {e}")
            return None
        if isinstance(value, pl.Series):
            value = value.to_list()
        # A non-finite float stays a float here: the walk-through measures
        # the run it is built from, and spells its values for the wire when
        # it is written.
        if isinstance(value, list):
            return [_as_a_number_is_read(item) for item in value]
        return _as_a_number_is_read(value)

    def extract_expression(self, expr: pl.Expr) -> _WireValue:
        """Evaluate one expression on the sampled row and read the answer back.

        The same row every :meth:`extract` reads from, and the same
        formatting on the way out, so a value computed here and a
        ``value_sample`` beside it are one convention rather than two: a
        pinned period narrows both, a year filter selects in both, and an
        unpinned per-period answer is the sampled row's every period.

        What it is for is the branch a conditional did not take. That value
        is in no column of the finished frame -- the frame holds the answer
        the condition chose -- so the only honest way to state it is to
        evaluate the branch, against the row the rest of the document is an
        account of.

        Args:
            expr: The expression to evaluate, already lowered against the
                frame this extractor's rows came off.

        Returns:
            The value, formatted as a sample of the same column would be.

        Raises:
            Exception: Whatever the engine raises for an expression it
                cannot evaluate against this row -- a column the frame no
                longer holds, a dtype the operation refuses. The caller
                decides what an unevaluable expression means; here it is
                not downgraded to a null, which would read as an answer.

        """
        row = self._the_row_samples_are_read_from()
        evaluated = _first_value(row.select(expr.alias(_EVALUATED))[_EVALUATED])
        return self._format_value(evaluated)

    def _the_row_samples_are_read_from(self) -> DataFrame:
        """Return the one row this extractor's samples come off.

        The row the export's stamp names first, exactly as
        :meth:`_get_raw_value` reads it: an axis of policies reaches here
        through the pin, often on a book whose identifier is not the
        configured id column, and a read that skipped the pin answered
        every entry of the axis off the frame's first row -- the first
        policy's ``then``, ``otherwise`` and ``fired`` stamped on every
        policy, beside samples that were each policy's own. Then the pinned
        policy's first matching row, or -- unpinned, or with no identifier
        column to pin against -- the frame's first row, which is what
        :meth:`_get_raw_value` reads by index. An empty frame comes back
        where the pin matched nothing, and evaluating against it raises
        rather than answering, which is the same loud miss
        :meth:`_get_policy_specific_value` makes for a sample.
        """
        if self.pin is not None:
            return self._the_pinned_row()
        if self.policy_id is None or self.policy_id_column not in self.df.columns:
            return self.df.head(1)
        return self._sampled_row if self._sampled_row is not None else self.df.head(1)

    def _format_value(self, value: object) -> _WireValue:
        """Format a value for JSON serialization."""
        if isinstance(value, (list, pl.Series)):
            return self._format_list_value(value)
        return self._format_scalar(value)

    def _format_scalar(self, value: object) -> _WireScalar:
        """Format one value -- never a run of them -- for the wire."""
        return one_value_on_the_wire(value)

    def _format_list_value(self, value: list[Any] | pl.Series) -> _WireValue:
        """Format list/series values.

        Three answers, and which one a reader gets is what the envelope's
        ``periods`` states. A pinned period gives that period's own value,
        which is what a reader zooming in on month 37 asked for. A year
        filter gives the year it selected, the same reading by another
        route. Otherwise every period of the sampled row's timeline,
        because ``periods: null`` is the document stating that every period
        was taken.

        **The window is gone, and this is why.** It was the first five
        values and an ellipsis, written under an envelope already saying
        that no period had been pinned -- so the document described a run it
        did not carry. A reviewer asking what the account value was at month
        84 and what month 83 it rolled from was asking for two adjacent
        cells of one column for one policy, and was handed months 0 to 4;
        the walk-through at month 84 could then substitute a number the file
        held nowhere else, which is a proof nobody holding the file can
        re-perform. One policy's every period is what this format's values
        section was specified to carry, and the cost is a fraction of the
        file it is written into: with every value the full double, 83
        periods over 70 per-period columns grow a thousand-policy export by
        12 % over a five-value window, and 241 periods over 40 of them grow
        a four-policy one -- whose inlined tables come to 7 KB -- by 70 %.
        """
        if isinstance(value, pl.Series):
            value = value.to_list()

        if not isinstance(value, list):
            return value

        # The period asked for, where one was, before the year filter's own
        # index: an explicit period is what the caller said, and the year
        # index is what a filter expression was read as meaning.
        if self.period is not None:
            if self.period < len(value):
                return self._format_value(value[self.period])
            # A row whose own timeline is shorter than the pinned period
            # reaches nowhere at that period, and null is the truth about
            # it. The export as a whole already refused a period no row
            # reaches at all.
            return None

        # Handle year-indexed extraction
        if self._year_index is not None and len(value) > self._year_index:
            return self._format_value(value[self._year_index])

        # Every period, in order. No cap and no marker: a list that ends at
        # a value is a list a reader can read the last period off.
        return [self._format_value(item) for item in value]


# What the host language says when the engine hands it a date whose year it
# has no calendar for: the engine holds the date as a count of days, and only
# turning it into a date for the record fails.
_PAST_THE_CALENDAR = re.compile(r"year -?\d+ is out of range")

# The calendar a sampled date or timestamp is written in: ISO-8601 text for
# the years 1 to 9999, which is also every year the host language's own date
# holds. As counts of days, and of seconds, from 1970-01-01.
_FIRST_DAY: Final[int] = (datetime.date(1, 1, 1) - datetime.date(1970, 1, 1)).days
_LAST_DAY: Final[int] = (datetime.date(9999, 12, 31) - datetime.date(1970, 1, 1)).days
_SECONDS_PER_DAY: Final[int] = 86_400
_PER_SECOND: Final[dict[str, int]] = {"ms": 1_000, "us": 1_000_000, "ns": 1_000_000_000}


def _first_value(column: pl.Series) -> object:
    """Return a column's first value, refusing by name a date past the calendar.

    A date or timestamp the row holds outside the years 1 to 9999 is refused
    on its count, before it is read as a value at all: past about 262,000
    years from 1970 the engine's own conversion panics, with an exception no
    ``except Exception`` catches, and from the year 10000 up to there the
    host language refuses it naming no column. Both are one refusal here,
    naming the column, whichever unit or zone it is held in, per policy or
    in any period of a per-period column.
    """
    head = column.head(1)
    past = _a_count_past_the_calendar(head)
    if past is not None:
        raise ValueError(_a_date_past_the_calendar(column.name, past))
    return head[0]


def _a_count_past_the_calendar(values: pl.Series) -> str | None:
    """Return the count of a date or timestamp in ``values`` past the calendar."""
    inner: PolarsDataType = values.dtype
    flat = values
    while isinstance(inner, pl.List | pl.Array):
        flat = (
            flat.cast(pl.List(inner.inner)).explode(empty_as_null=True)
            if isinstance(inner, pl.Array)
            else flat.explode(empty_as_null=True)
        )
        inner = inner.inner
    if isinstance(inner, pl.Date):
        unit, per_day = "days", 1
    elif isinstance(inner, pl.Datetime):
        unit = inner.time_unit
        per_day = _PER_SECOND[unit] * _SECONDS_PER_DAY
    else:
        return None
    first, last = _FIRST_DAY * per_day, (_LAST_DAY + 1) * per_day - 1
    past = _past(flat.to_physical(), first - per_day, last + per_day)
    zone = getattr(inner, "time_zone", None)
    if past is None and zone is not None:
        # A zoned instant is written as its wall-clock time in its zone, which
        # can be a day either side of the instant: read within a day of the
        # calendar's ends, where the engine reads it safely, and judged there.
        past = _past(flat.dt.replace_time_zone(None).to_physical(), first, last)
    elif past is None:
        past = _past(flat.to_physical(), first, last)
    return None if past is None else f"the count {past:,} {unit} from 1970-01-01"


def _past(counts: pl.Series, first: int, last: int) -> int | None:
    """Return a count outside ``first`` to ``last``, or None where all are inside."""
    held = counts.drop_nulls()
    if held.is_empty():
        return None
    for count in (held.min(), held.max()):
        if isinstance(count, int) and not first <= count <= last:
            return count
    return None


def _a_date_past_the_calendar(column: str, said: str) -> str:
    """Return the refusal a sampled date outside the years 1 to 9999 earns."""
    return (
        f"Column {column!r} holds a date outside the years 1 to 9999 in the row "
        f"the record samples ({said}), so the export is refused. The record "
        "writes a date as ISO-8601 calendar text, which has no such year, and "
        "section 11.1.33 puts a date result outside those years outside the "
        "domain. The run answered it, as a count of its unit. The usual causes "
        "are an open-ended 9999-12-31 carried past the calendar -- excel.edate "
        "or excel.eomonth on it -- and a count read in another unit than it was "
        "written in, as epoch nanoseconds cast to milliseconds. Keep the "
        "sentinel out of the arithmetic with a when() on it, read the count in "
        "its own unit, or drop the column before the export."
    )
