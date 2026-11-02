# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every operation this format names, one row each, with all that is said of it.

An operation's tier, the specification clause that answers for it, the
sentence a walk-through speaks for it and the rule its clause states for a
period carrying no value used to be four hand-kept copies in four files,
each pinned verbatim by its own test and none of them checked against the
others. When the four reductions changed what they do with a null period, one
of the copies was left saying the old thing and nothing failed. They are one
row here, and the three tables that held three of them --
:data:`~gaspatchio.frame.graph.tiers.TIERS`,
:data:`~gaspatchio.frame.graph.trace_voice.SENTENCES` and
:data:`~gaspatchio.frame.graph.trace_voice.SPOKEN_BY_SUBSTITUTION` -- are
views over it.

**The specification is the authority and this table is checked against it,
never written from it.** ``clause`` says where the document answers for the
identifier, and ``rule`` quotes what that clause states about a period
carrying no value. A census test reads the document and fails when either
has drifted, and a row that disagrees with its clause is a wrong row rather
than a stale document.

**The order is section 11.1's own**: the fifteen binary operators a formula
is written with rather than called, and then every other identifier
alphabetically. Reading this table against the one the document prints is
then a scan down two columns instead of a lookup per line.

It is a plain literal, and deliberately not assembled at import out of
whatever happened to declare itself: the whole vocabulary has to be
reviewable at a glance, and a table a reader must run the package to see is
one nobody reviews.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

OpTier = Literal["core", "engine_native", "opaque"]

__all__ = ["VOCABULARY", "Operation"]


@dataclass(frozen=True, slots=True)
class Operation:
    """One identifier, and everything this package says about it.

    Attributes:
        identifier: The operation's name in the format's own vocabulary,
            exactly as a node records it.
        tier: How much of the operation the format can account for. Every
            entry is ``core``: the weaker tiers are reached through a node's
            tree and never through this table.
        clause: The specification section that answers for the identifier,
            written the way the conformance kit holds it -- ``"11.1.15"``,
            and ``"16.1"`` for the rollforward family. Several identifiers
            share one clause where the document answers for a family in one
            entry.
        voice: The sentence a walk-through speaks for the operation, with a
            field in braces filled from the node itself, or None for the
            fifteen operators whose substituted arithmetic is already their
            meaning.
        rule: What the clause states about a period carrying no value,
            quoted from the clause word for word, or None where the clause
            states no such rule. Ten rows carry one: the two running folds,
            the four reductions, and the four operations that fold or
            recur along a projection's periods.
        node_kind: Whether an identifier names a callable operation, binary
            syntax or a structural record. Only calls are authorable as Call nodes.

    """

    identifier: str
    tier: OpTier
    clause: str
    voice: str | None
    rule: str | None
    node_kind: Literal["call", "binary", "structural"] = "call"


VOCABULARY: Final[tuple[Operation, ...]] = (
    Operation("add", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("sub", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("mul", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("div", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("floordiv", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("mod", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("pow", "core", "11.1.25", None, None, node_kind="binary"),
    Operation("lt", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("le", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("gt", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("ge", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("eq", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("ne", "core", "11.1.26", None, None, node_kind="binary"),
    Operation("and", "core", "11.1.27", None, None, node_kind="binary"),
    Operation("or", "core", "11.1.27", None, None, node_kind="binary"),
    # The ten plain maths a projection is written with, spread through the
    # table below in the alphabetical order it takes: "abs", "cbrt", "exp",
    # "log", "log10", "log1p", "norm_cdf", "round_sig_figs", "sign" and
    # "sqrt". Each answers one value at a time. Seven of them are
    # transcendental and carry a stated relative tolerance rather than a
    # bitwise contract (11.1.12); the other three are decided by the value's
    # own digits and are exact.
    Operation("abs", "core", "11.1.12", "{operand} with its sign dropped", None),
    Operation("cbrt", "core", "11.1.12", "the cube root of {operand}", None),
    # Three ways of moving a value to a whole step: up, down, and to the
    # nearest one of a size the call names. A rounding carries both the
    # number of places and the tie rule, because both move the money.
    Operation(
        "ceil",
        "core",
        "11.1.8",
        "the smallest whole number not below {operand}",
        None,
    ),
    # A value held between a floor and a cap, one value at a time. The
    # bounds are operands like anything else, so a bound that reads a
    # column stands in the tree rather than in the configuration, and the
    # configuration says only which of the two sides they are.
    Operation(
        "clip",
        "core",
        "11.1.3",
        "{operand} held between its bounds -- {bounds} -- so that a value outside one becomes that bound",  # noqa: E501
        None,
    ),
    # The two closed-form folds along a projection's period axis, within
    # one policy: a cumulative product is a fund's growth from the start
    # of the projection, a cumulative sum the premium taken so far. Both
    # are along the periods and neither is along the model points, which
    # is a different calculation this vocabulary does not name.
    Operation(
        "cum_prod",
        "core",
        "11.1.9",
        "a running product of {operand} along the projection's periods, {reverse}",
        "A period carrying no value ends the fold's knowledge of its own total",
    ),
    Operation(
        "cum_sum",
        "core",
        "11.1.9",
        "a running total of {operand} along the projection's periods, {reverse}",
        "A period carrying no value ends the fold's knowledge of its own total",
    ),
    # A curve reads its knots out of band, the way a lookup and a schedule
    # do, and lowers to ordinary expressions over them. Out-of-band data is
    # not an engine fragment: what an implementation needs to reproduce a
    # spot rate is the curve, not this engine.
    Operation(
        "curve.discount_factor",
        "core",
        "11.1.31",
        "each time in {operand} discounted at its own spot rate off the {curve} curve",
        None,
    ),
    Operation(
        "curve.spot_rate",
        "core",
        "11.1.31",
        "the spot rate the {curve} curve gives at each time in {operand}",
        None,
    ),
    # Three ways of sorting values into named groups: placement in one of a
    # band's intervals ("cut"), membership of a set ("is_in"), substitution
    # one for one ("replace"). What identifies each is the values written
    # into it, which the tree holds as sequence literals rather than handing
    # to an engine to keep.
    Operation(
        "cut",
        "core",
        "11.1.4",
        "{operand} placed in the interval the breakpoints {second} divide the line into, {left_closed}",  # noqa: E501
        None,
    ),
    Operation(
        "date.date_ranges",
        "core",
        "11.1.33",
        "one run of dates per policy from {operand} to {second}, one every {interval}",
        None,
    ),
    Operation(
        "date.months_between",
        "core",
        "11.1.33",
        "whole calendar months from {operand} to {second}, the day of the month playing no part",  # noqa: E501
        None,
    ),
    Operation(
        "date.offset_by",
        "core",
        "11.1.33",
        "{operand} shifted by {duration} on the calendar",
        None,
    ),
    Operation(
        "date.to_period",
        "core",
        "11.1.33",
        "{operand} snapped back to the start of the {freq} period holding it",
        None,
    ),
    Operation(
        "excel.days",
        "core",
        "11.1.33",
        "whole days from {second} to {operand}, Excel's DAYS",
        None,
    ),
    Operation(
        "excel.edate",
        "core",
        "11.1.33",
        "{operand} moved {second} whole months, keeping the day of the month, Excel's EDATE",  # noqa: E501
        None,
    ),
    Operation(
        "excel.eomonth",
        "core",
        "11.1.33",
        "{operand} moved {second} whole months and then taken to that month's last day, Excel's EOMONTH",  # noqa: E501
        None,
    ),
    Operation(
        "excel.from_excel_serial",
        "core",
        "11.1.33",
        "{operand} read as an Excel serial day number on the {epoch} epoch",
        None,
    ),
    Operation(
        "excel.irr",
        "core",
        "11.1.36",
        "the rate at which the cashflows in {operand} discount to nothing -- the internal rate of return",  # noqa: E501
        None,
    ),
    Operation(
        "excel.pv",
        "core",
        "11.1.35",
        "the present value of a level payment of {third} over {second} periods at {operand}, Excel's PV",  # noqa: E501
        None,
    ),
    Operation(
        "excel.round",
        "core",
        "11.1.35",
        "{operand} rounded to {num_digits} places, a tie going to the neighbour further from zero as Excel rounds",  # noqa: E501
        None,
    ),
    Operation(
        "excel.yearfrac",
        "core",
        "11.1.34",
        "the year fraction from {operand} to {second} on day-count basis {basis}",
        None,
    ),
    Operation("exp", "core", "11.1.12", "e raised to the power of {operand}", None),
    # A stated value put where an arithmetic left a NaN. A null is a
    # different absence and is left as it is, which is why this is its own
    # identifier rather than fill_null carrying a flag.
    Operation(
        "fill_nan",
        "core",
        "11.1.13",
        "{operand}, with {second} wherever a value is NaN",
        None,
    ),
    # A stated value put where one is missing. The fill is an operand and
    # never an attribute, because what fills a gap is as often a column as
    # a number, and a configuration slot could hold neither.
    Operation(
        "fill_null",
        "core",
        "11.1.13",
        "{operand}, with {second} wherever a value is missing",
        None,
    ),
    Operation(
        "finance.compound",
        "core",
        "11.1.29",
        "a growth factor of one plus {rate} raised to {operand} over {periods_per_year} periods a year",  # noqa: E501
        None,
    ),
    Operation(
        "finance.discount",
        "core",
        "11.1.29",
        "{operand} divided by one plus {second}, raised to {third}",
        None,
    ),
    Operation(
        "finance.discount_factor",
        "core",
        "11.1.30",
        "a discount factor for each period of the projection, from the rate {operand} over {second}, on the {method} method",  # noqa: E501
        None,
    ),
    Operation(
        "finance.present_value",
        "core",
        "11.1.29",
        "{operand} discounted at {second} over {third} periods",
        None,
    ),
    Operation(
        "finance.to_monthly",
        "core",
        "11.1.29",
        "{operand} converted from an annual rate to the monthly equivalent, on the {method} method",  # noqa: E501
        None,
    ),
    Operation(
        "floor",
        "core",
        "11.1.8",
        "the largest whole number not above {operand}",
        None,
    ),
    # The six tests of a value that is not there. A null is a value that
    # was never present and a NaN one an arithmetic produced and cannot
    # name, so the two are separate operations rather than one with a flag.
    # The negations are their own operations too: composing them out of
    # "not_" would hand back a Float64 mask where these hand back a
    # Boolean, and would stop the artifact saying what the actuary wrote.
    Operation(
        "is_finite",
        "core",
        "11.1.13",
        "whether {operand} is a finite number, neither infinite nor NaN",
        None,
    ),
    Operation(
        "is_in",
        "core",
        "11.1.5",
        "whether {operand} is one of {second}, {nulls_equal}",
        None,
    ),
    Operation(
        "is_infinite",
        "core",
        "11.1.13",
        "whether {operand} is an infinity, of either sign",
        None,
    ),
    Operation(
        "is_nan",
        "core",
        "11.1.13",
        "whether {operand} is NaN: a value an arithmetic could not name",
        None,
    ),
    Operation(
        "is_not_nan",
        "core",
        "11.1.13",
        "whether {operand} is anything other than NaN",
        None,
    ),
    Operation(
        "is_not_null",
        "core",
        "11.1.13",
        "whether {operand} is present at all",
        None,
    ),
    Operation(
        "is_null",
        "core",
        "11.1.13",
        "whether {operand} is missing -- a value that was never there",
        None,
    ),
    # The relational join, over the keys, the join type and the right
    # side's content identity the node already carries. Its right side is
    # out of band, the way a lookup's table is: what an implementation
    # needs to reproduce an arriving column is that table, not this engine.
    Operation(
        "join",
        "core",
        "11.1.2",
        "a column that arrived from a second table, matched on {on} under a {how} join",
        None,
        node_kind="structural",
    ),
    Operation(
        "list.get",
        "core",
        "11.1.22",
        "the value in {operand} at position {second}: zero is first, negative positions count from the end",  # noqa: E501
        None,
    ),
    # A permutation of one policy's own list, last period first. Nothing is
    # combined, so no period carrying no value is lost: it moves with its
    # position, which is why the row quotes no null rule.
    Operation(
        "list.reverse",
        "core",
        "11.1.41",
        "{operand} turned end for end within each policy's own periods, its last period first",  # noqa: E501
        None,
    ),
    # The natural logarithm, and only that: an engine's method taking a
    # base is not this operation, because recording the default base as a
    # truncated double would put the constant where the operation is.
    Operation(
        "log",
        "core",
        "11.1.12",
        "the natural logarithm of {operand}, to base e",
        None,
    ),
    Operation(
        "log10",
        "core",
        "11.1.12",
        "the logarithm of {operand} to base ten",
        None,
    ),
    Operation(
        "log1p",
        "core",
        "11.1.12",
        "the natural logarithm of one plus {operand}, kept accurate near zero",
        None,
    ),
    Operation(
        "lookup",
        "core",
        "11.1.24",
        "one value per row read out of the {table} base at {operands}, {on_missing}",
        None,
    ),
    # Three of the four folds that reduce a policy's own periods to one
    # number; "sum", the present value that adds a whole discounted
    # cashflow up, stands at its own place in the alphabet below. The same
    # axis and the same discipline as the two scans above; what is
    # different is that the answer's shape is not the operand's, which
    # 11.1.14 states in prose rather than in a field.
    Operation(
        "max",
        "core",
        "11.1.17",
        "the greatest of {operand} across the projection's periods",
        "A null period makes the answer null",
    ),
    Operation(
        "mean",
        "core",
        "11.1.15",
        "the average of {operand} across the projection's periods",
        "A null period makes the answer null",
    ),
    Operation(
        "min",
        "core",
        "11.1.16",
        "the least of {operand} across the projection's periods",
        "A null period makes the answer null",
    ),
    # A mortality basis read under the convention its wrapper holds. The
    # structure, the select period and the age basis are attributes of the
    # node, so the clamp a select and ultimate basis applies is something
    # an implementation can apply again rather than read back out of one
    # engine's rendering of a bounded column.
    Operation(
        "mortality.at",
        "core",
        "11.1.10",
        "one rate per row read out of the {table} mortality base at {operands} -- {structure} -- with ages taken as {age_basis} and not converted",  # noqa: E501
        None,
    ),
    # The standard normal distribution function, the N(d1) and N(d2) of a
    # guarantee priced as an option. Excel's NORM.S.DIST(z, TRUE) is a second
    # door to this same row, never a second identifier: one function, one
    # identity, whichever way the model was written.
    Operation(
        "norm_cdf",
        "core",
        "11.1.12",
        "the standard normal distribution function at {operand}: the chance a standard normal value is at most it",  # noqa: E501
        None,
    ),
    Operation(
        "not_",
        "core",
        "11.1.27",
        "the negation of {operand}: true wherever it is false",
        None,
    ),
    Operation(
        "projection.accumulate",
        "core",
        "11.1.20",
        "the linear recurrence: each state is the state the run just left x {second} + {third}, run {reverse} and opening at {operand}",  # noqa: E501
        "A null multiplier or a null addend at position `t` makes `s[t]` and every later position null",  # noqa: E501
    ),
    Operation(
        "projection.at_period",
        "core",
        "11.1.19",
        "{operand} read {relative_period} periods away, a negative offset being a prior period and a positive one a later",  # noqa: E501
        None,
    ),
    Operation(
        "projection.broadcast_to_periods",
        "core",
        "11.1.32",
        "{operand} repeated once per projection period",
        None,
    ),
    Operation(
        "projection.cumulative_survival",
        "core",
        "11.1.19",
        "cumulative survival from {operand}: a running product of {from_survival} across {periods}, opening at {start_at}",  # noqa: E501
        "A null decrement ends the running survival's knowledge of itself",
    ),
    Operation(
        "projection.next_period",
        "core",
        "11.1.19",
        "{operand} read one period ahead -- t+1 -- with {second} where the projection ends",  # noqa: E501
        None,
    ),
    Operation(
        "projection.previous_period",
        "core",
        "11.1.19",
        "{operand} read one period back -- t-1 -- with {second} at the projection's start",  # noqa: E501
        None,
    ),
    Operation(
        "projection.prospective_value",
        "core",
        "11.1.21",
        "the present value of {operand} at each period and every period after it, discounted by {second}, {timing}",  # noqa: E501
        "A null cashflow period makes that position and every earlier position null",
    ),
    Operation(
        "projection.remaining_sum",
        "core",
        "11.1.20",
        "the sum of {operand} at each period and every period after it",
        "A null period makes that position and every earlier position null",
    ),
    Operation(
        "projection.with_period",
        "core",
        "11.1.32",
        "{operand} with period {period} replaced by {value}",
        None,
    ),
    Operation(
        "projection_frame.anniversary_mask",
        "core",
        "11.1.37",
        "the periods closing a contract anniversary on the frame's own timeline ({schedule})",  # noqa: E501
        None,
    ),
    Operation(
        "projection_frame.period_dates",
        "core",
        "11.1.37",
        "the boundary date opening each period of the frame's own timeline ({schedule})",  # noqa: E501
        None,
    ),
    Operation(
        "projection_frame.t_years",
        "core",
        "11.1.37",
        "elapsed time in years at each boundary of the frame's own timeline ({schedule}), counting from zero",  # noqa: E501
        None,
    ),
    Operation(
        "projection_frame.year_fractions",
        "core",
        "11.1.37",
        "the year fraction each period of the frame's own timeline spans ({schedule})",
        None,
    ),
    # The projection time axis itself, standing as the node behind every
    # column its declaration mints. The configuration is on the record and
    # the columns are functions of it, which is what makes the boundaries
    # something an implementation can lay again rather than read back.
    Operation(
        "projection_set",
        "core",
        "11.1.1",
        "a column the model's own projection axis mints: {frequency} boundaries, whose configuration this node carries",  # noqa: E501
        None,
        node_kind="structural",
    ),
    Operation(
        "replace",
        "core",
        "11.1.6",
        "each value of {operand} standing in {second} swapped for the one opposite it in {third}, every other value kept",  # noqa: E501
        None,
    ),
    # One whole compiled rollforward, standing as the node every
    # extraction from it reads. The identifier is the format's own; what
    # a second implementation would need beside it -- the compiled state
    # machine itself -- is a question the profile answers, not the tier.
    Operation(
        "rollforward",
        "core",
        "16.1",
        "one whole compiled rollforward ({fingerprint}) -- the state machine every extraction from it reads",  # noqa: E501
        None,
        node_kind="structural",
    ),
    Operation(
        "rollforward.increment",
        "core",
        "16.2",
        "the signed movement the {label} step of the compiled rollforward made in each period",  # noqa: E501
        None,
    ),
    Operation(
        "rollforward.state",
        "core",
        "16.1",
        "the {state} state of the compiled rollforward, read at {point}",
        None,
    ),
    Operation(
        "rollforward.struct",
        "core",
        "16.3",
        "the compiled rollforward run whole, every state it declares arriving together",
        None,
    ),
    Operation(
        "round",
        "core",
        "11.1.8",
        "{operand} moved to the nearest multiple of ten to the power of minus {decimals}, a tie {mode}",  # noqa: E501
        None,
    ),
    # Significant figures are not decimal places, so this is its own
    # identifier and not "round" carrying a different attribute.
    Operation(
        "round_sig_figs",
        "core",
        "11.1.12",
        "{operand} kept to its leading {digits} significant figures",
        None,
    ),
    Operation(
        "schedule.anniversary_mask",
        "core",
        "11.1.37",
        "the periods closing a contract anniversary on the {schedule} schedule",
        None,
    ),
    Operation(
        "schedule.contract_boundary",
        "core",
        "11.1.37",
        "the periods the contract has terminated by, on the {schedule} schedule",
        None,
    ),
    Operation(
        "schedule.is_in_force",
        "core",
        "11.1.37",
        "the periods the contract is still in force in, on the {schedule} schedule",
        None,
    ),
    Operation(
        "schedule.per_policy_period_count",
        "core",
        "11.1.37",
        "how many periods each policy projects for on the {schedule} schedule",
        None,
    ),
    Operation(
        "schedule.per_policy_period_dates",
        "core",
        "11.1.37",
        "each policy's own period boundary dates on the {schedule} schedule, each run its own length",  # noqa: E501
        None,
    ),
    Operation(
        "schedule.period_dates",
        "core",
        "11.1.37",
        "each policy's period boundary dates on the {schedule} schedule, anchored on its own inception",  # noqa: E501
        None,
    ),
    Operation(
        "schedule.year_fractions",
        "core",
        "11.1.37",
        "the year fraction each projection period spans on the {schedule} schedule's day count",  # noqa: E501
        None,
    ),
    Operation(
        "sign",
        "core",
        "11.1.12",
        "which way {operand} points: minus one, zero, or one",
        None,
    ),
    Operation("sqrt", "core", "11.1.12", "the square root of {operand}", None),
    # Text read as a calendar date. The format string is the whole of what
    # makes one parse different from another, and the engine's own
    # rendering of the expression drops it, so the call carries it.
    Operation(
        "str.to_date",
        "core",
        "11.1.7",
        "{operand} read as a calendar date under the format {format}, {strict}",
        None,
    ),
    Operation(
        "sum",
        "core",
        "11.1.14",
        "the total of {operand} across the projection's periods",
        "A null period makes the total null",
    ),
    # The three named conversions beside the date parse above, and the
    # array-to-list carriage with them. Each is one pair of types and says
    # what it refuses, which is what a second implementation can hold; a
    # generic cast taking a type argument would hand that implementation a
    # matrix instead.
    Operation(
        "to_float",
        "core",
        "11.1.38",
        "{operand} carried to floating point, exact out to the largest whole number a double names",  # noqa: E501
        None,
    ),
    Operation(
        "to_integer",
        "core",
        "11.1.23",
        "{operand} checked to be whole and in signed 64-bit range",
        None,
    ),
    Operation(
        "to_list",
        "core",
        "11.1.40",
        "{operand} carried from a fixed-width array to a list, the same elements in the same order",  # noqa: E501
        None,
    ),
    Operation(
        "to_text",
        "core",
        "11.1.39",
        "{operand} carried to text, every digit kept",
        None,
    ),
)
