# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The calendar, in whole days, and the eight operations §11.1.33 states over it.

A calendar day enters the trace as a count of days from 1970-01-01 and every
rule below is arithmetic on that count. The two conversions between a count
and a year, a month and a day are Howard Hinnant's, written with floor
division so that the negative-year corrections his truncating version needs
fall away -- which matters because a policy issued in 1948 is an ordinary
model point and a calendar that was only right after 1970 would be wrong
quietly.

**The month clamp is the rule everything here shares.** Moving a month or a
year changes the year and the month and then holds the day at the last valid
day of the month it lands in, so 31 January plus one month is 29 February in
a leap year and 28 February otherwise. Every operation that moves by months --
``date.offset_by``, ``excel.edate``, ``excel.eomonth``, the schedule family's
boundaries -- shares this one function rather than each rounding its own way.

**A range is a generator.** ``date.date_ranges`` answers a different number of
days for every policy, so it sizes a bucket from the longest and each row is
cut back to its own count on the way out; candidate ``k`` is offset from the
**original** start rather than from the previously clamped date, which is what
makes a monthly range from 31 January run 29 February and then 31 March.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import jax.numpy as jnp
from jax import lax

from gaspatchio_jax.capability import DATE, NUMERIC, PER_POLICY, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import Horizon
from gaspatchio_jax.lowerings import register, register_sizing
from gaspatchio_jax.typed import (
    JNP_OF,
    DomainRefused,
    Value,
    outside_integer_conversion,
    require_carrier,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext

_CALENDAR: Final = "11.1.33"

# 11.1.33 states every operation in it but excel.yearfrac over one value per
# policy, and the reference producer refuses each one written over a value per
# period by name. What each reads for a policy, and the move its refusal names
# -- the producer's own, so the two engines send a reader the same way.
_RUN_OF_DATES: Final = (
    "for a date in every period, build the run of dates from the start date "
    "with date.date_ranges"
)
PER_POLICY_READING: Final[dict[str, tuple[str, str]]] = {
    "excel.edate": (
        "one date and one count of months",
        f"move a per-policy date by a per-policy count of months; {_RUN_OF_DATES}",
    ),
    "excel.eomonth": (
        "one date and one count of months",
        f"move a per-policy date by a per-policy count of months; {_RUN_OF_DATES}",
    ),
    "date.offset_by": ("one date", f"move a per-policy date; {_RUN_OF_DATES}"),
    "date.months_between": (
        "one start date and one end date",
        (
            "count between per-policy dates; for the months elapsed at every "
            "period, add the timeline's own month count to that per-policy count"
        ),
    ),
    "excel.days": (
        "one end date and one start date",
        (
            "count between per-policy dates; for the time elapsed to a date in "
            "every period, excel.yearfrac reads one"
        ),
    ),
    "date.to_period": (
        "one date",
        (
            "snap a per-policy date; for the start of every period's month, "
            "build the run of dates with date.date_ranges from a snapped start "
            "date"
        ),
    ),
    "date.date_ranges": (
        "one start date and one end date",
        "build the run from a per-policy start date and a per-policy end date",
    ),
    "excel.from_excel_serial": (
        "one spreadsheet serial",
        f"convert a per-policy serial; {_RUN_OF_DATES}",
    ),
}


# The move a month count of the wrong kind is refused with: the producer's own.
_MONTHS_KIND: Final = (
    "convert the months where they are loaded, to the whole number they stand "
    "for (to_integer() over a number)"
)


def _alike(name: str, operands: int) -> dict[str, str]:
    """Return the moves a refusal of a per-period operand names, at every position.

    The reference producer refuses each of these operations over a value per
    period too, so the declaration names the operation's own move rather than
    sending a reader to Polars.
    """
    return {
        f"shape@{position}": PER_POLICY_READING[name][1] for position in range(operands)
    }


# The era arithmetic's two constants: days in four hundred years, and the
# distance from the proleptic era's own zero to 1970-01-01.
_DAYS_PER_ERA: Final = 146097
_EPOCH_SHIFT: Final = 719468

# The units a duration or an interval is written in, and what each one moves
# by: the two that change a month and clamp the day, and the two that add
# calendar days.
_MONTH_UNITS: Final[dict[str, int]] = {"mo": 1, "y": 12}
_DAY_UNITS: Final[dict[str, int]] = {"d": 1, "w": 7}

# 11.1.33's four interval spellings, longest first so that "mo" is matched
# before "m" could be.
_UNITS: Final[tuple[str, ...]] = ("mo", "y", "w", "d")

# The two epochs ``excel.from_excel_serial`` states. They differ by more than
# four years: the 1900 system carries a 29 February 1900 that never happened,
# and every serial past it stands one day later than the count of days would
# put it.
_EPOCH_1904: Final = "1904"
_EPOCH_1900: Final = "1900"

# 1904-01-01 and 1900-01-01, as counts of days from 1970-01-01.
_DAYS_TO_1904: Final = -24107
_DAYS_TO_1900: Final = -25567

# The month the era arithmetic starts its year at, and the month it shifts
# past when it comes back -- which is what makes the leap day the last day of
# the year rather than a day in the middle of it.
_MARCH_SHIFT: Final = 10
_FEBRUARY: Final = 2

# The serial the 1900 system's phantom 29 February stands at, and the last
# real serial before it: 1 to 59 are 1 January to 28 February 1900, 60 is a
# day that never happened and reads as 28 February with them, and from 61 the
# serials run on from 1 March.
_PHANTOM: Final = 60
_LAST_REAL: Final = 59


# The calendar's intermediate values are each read many times downstream, and
# a compiler that fuses a value into every one of its readers computes it once
# per reader. XLA's CPU compiler from JAX 0.11 does exactly that here: the
# month clamp over one batch's boundary rectangle took 5.2 s compiled against
# 0.55 s for its parts (GPU runner, JAX 0.11.2), where JAX 0.4.38 took 36 ms.
# An optimization barrier returns its operands unchanged and stops fusion
# across it, so each value is computed once and read from memory after --
# on that runner's CPU the grid went from 2.53 s to 0.11 s and settling a
# batch from 5.24 s to 0.31 s.
#
# **Only on the CPU.** The GPU compiler does not recompute these, and there the
# barrier costs what fusion saved: the T4's grid went from 3.0 ms to 5.6 ms.
# Where a trade-off is JAX's alone the engine favours the GPU and keeps the CPU
# correct, so the barrier is chosen per platform when the program is compiled
# and the GPU program is the one it was before. Integer arithmetic either way:
# the days are the same days.
_BARRIER: Callable[[object], object] = lax.optimization_barrier


def _held(*values: jax.Array) -> tuple[jax.Array, ...]:
    """Return ``values`` unchanged behind a barrier, each computed once."""
    return cast("tuple[jax.Array, ...]", _BARRIER(values))


def _passed(*values: jax.Array) -> tuple[jax.Array, ...]:
    """Return ``values`` unchanged, free to fuse into their readers."""
    return values


def _each_once(*values: jax.Array) -> tuple[jax.Array, ...]:
    """Return ``values`` unchanged; on the CPU, each computed once rather than fused."""
    chosen: object = lax.platform_dependent(*values, cpu=_held, default=_passed)
    return cast("tuple[jax.Array, ...]", chosen)


def _once(value: jax.Array) -> jax.Array:
    """Return ``value`` unchanged; on the CPU, computed once rather than fused."""
    return _each_once(value)[0]


def civil_from_days(days: jax.Array) -> tuple[jax.Array, jax.Array, jax.Array]:
    """Return the year, month and day one count of days from the epoch stands at."""
    shifted = days + _EPOCH_SHIFT
    era = jnp.floor_divide(shifted, _DAYS_PER_ERA)
    era, day_of_era = _each_once(era, shifted - era * _DAYS_PER_ERA)
    year_of_era = jnp.floor_divide(
        day_of_era
        - jnp.floor_divide(day_of_era, 1460)
        + jnp.floor_divide(day_of_era, 36524)
        - jnp.floor_divide(day_of_era, _DAYS_PER_ERA - 1),
        365,
    )
    year_of_era = _once(year_of_era)
    year = year_of_era + era * 400
    day_of_year = day_of_era - (
        365 * year_of_era
        + jnp.floor_divide(year_of_era, 4)
        - jnp.floor_divide(year_of_era, 100)
    )
    day_of_year = _once(day_of_year)
    shifted_month = _once(jnp.floor_divide(5 * day_of_year + 2, 153))
    day = day_of_year - jnp.floor_divide(153 * shifted_month + 2, 5) + 1
    month = shifted_month + jnp.where(shifted_month < _MARCH_SHIFT, 3, -9)
    year, month, day = _each_once(year + (month <= _FEBRUARY), month, day)
    return year, month, day


def days_from_civil(year: jax.Array, month: jax.Array, day: jax.Array) -> jax.Array:
    """Return the count of days from the epoch one calendar day stands at."""
    shifted_year = year - (month <= _FEBRUARY)
    era = jnp.floor_divide(shifted_year, 400)
    year_of_era = shifted_year - era * 400
    day_of_year = (
        jnp.floor_divide(153 * (month + jnp.where(month > _FEBRUARY, -3, 9)) + 2, 5)
        + day
        - 1
    )
    day_of_era = (
        year_of_era * 365
        + jnp.floor_divide(year_of_era, 4)
        - jnp.floor_divide(year_of_era, 100)
        + day_of_year
    )
    return era * _DAYS_PER_ERA + day_of_era - _EPOCH_SHIFT


def is_leap(year: jax.Array) -> jax.Array:
    """Return whether each year carries a 29 February."""
    return ((year % 4) == 0) & (((year % 100) != 0) | ((year % 400) == 0))


def last_day_of(year: jax.Array, month: jax.Array) -> jax.Array:
    """Return the last day of the month each pair names."""
    lengths = jnp.asarray([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    ordinary = jnp.take(lengths, month - 1, mode="clip")
    return jnp.where((month == _FEBRUARY) & is_leap(year), 29, ordinary)


def moved_by_months(days: jax.Array, months: jax.Array) -> jax.Array:
    """Return each day moved by a signed count of months, the day clamped.

    The Gregorian clamp §11.1.33 states: the year and the month move, and the
    original day is held at the last valid day of the month it lands in.
    """
    year, month, day = civil_from_days(days)
    ordinal = year * 12 + (month - 1) + months
    landed_year = jnp.floor_divide(ordinal, 12)
    landed_year, landed_month = _each_once(landed_year, ordinal - landed_year * 12 + 1)
    held = jnp.minimum(day, last_day_of(landed_year, landed_month))
    return days_from_civil(landed_year, landed_month, held)


def _dates(value: Value, name: str) -> Value:
    """Return one operand as a calendar day, refusing anything else."""
    return require_carrier(value, DATE, name, _CALENDAR)


def _as_date(array: jax.Array, shape: str, horizon: Horizon | None) -> Value:
    """Return one answer as a calendar day in the shape its operands had."""
    named = "list[date]" if shape == "list" else "date"
    return Value(array.astype(JNP_OF["date"]), "date", shape, named, horizon)  # type: ignore[arg-type]


def _duration(written: str) -> tuple[int, str]:
    """Return the signed count and the unit one duration string names.

    Raises:
        DomainRefused: If the spelling is not a signed whole number followed
            by one of the four units 11.1.33 admits. A compound duration --
            "1y6mo" -- is outside this entry and refuses rather than being
            read as its first half.

    """
    for unit in _UNITS:
        if written.endswith(unit):
            count = written[: -len(unit)]
            try:
                return int(count), unit
            except ValueError:
                break
    raise DomainRefused(
        what=(
            f"this operation names a duration of {written!r}, and this entry "
            "states a signed whole count followed by mo, y, w or d"
        ),
        move="write the offset as one count and one unit; a compound duration "
        "is outside this entry",
        clause=_CALENDAR,
    )


@register(
    Capability(
        identifier="date.months_between",
        refused_alike=_alike("date.months_between", 2),
        arity=(2,),
        carriers=(DATE, DATE),
        shapes=(PER_POLICY, PER_POLICY),
        answers_carrier="i64",
        clause=_CALENDAR,
        note="days are ignored: 31 January to 1 February is one month",
    )
)
def _months_between(call: Call, ctx: LoweringContext) -> Value:
    """Return the whole calendar months from the first day to the second."""
    start = _per_policy(
        _dates(ctx.lower(call.args[0]), "date.months_between"), "date.months_between"
    )
    end = _per_policy(
        _dates(ctx.lower(call.args[1]), "date.months_between"), "date.months_between"
    )
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    axis = aligned(start, end)
    start_year, start_month, _ = civil_from_days(axis.arrays[0])
    end_year, end_month, _ = civil_from_days(axis.arrays[1])
    months = 12 * (end_year - start_year) + (end_month - start_month)
    return Value(months.astype(JNP_OF["i64"]), "i64", axis.shape, "i64", axis.horizon)


@register(
    Capability(
        identifier="excel.days",
        refused_alike=_alike("excel.days", 2),
        arity=(2,),
        carriers=(DATE, DATE),
        shapes=(PER_POLICY, PER_POLICY),
        answers_carrier="i64",
        clause=_CALENDAR,
        note="the end date is written first, as the spreadsheet function takes it",
    )
)
def _days(call: Call, ctx: LoweringContext) -> Value:
    """Return the signed count of elapsed calendar days, end first."""
    end = _per_policy(_dates(ctx.lower(call.args[0]), "excel.days"), "excel.days")
    start = _per_policy(_dates(ctx.lower(call.args[1]), "excel.days"), "excel.days")
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    axis = aligned(end, start)
    elapsed = axis.arrays[0] - axis.arrays[1]
    return Value(elapsed.astype(JNP_OF["i64"]), "i64", axis.shape, "i64", axis.horizon)


@register(
    Capability(
        identifier="date.to_period",
        # The reference producer refuses a freq that is no interval at all --
        # 'Q' -- and answers one written with its count, '1q', outside the
        # entry; the move says both.
        refused_alike={
            **_alike("date.to_period", 1),
            "attr:freq": (
                "write freq as Y, M, W or D, the periods 11.1.33 states; an "
                "interval written with its count, such as '1q', runs on Polars"
            ),
        },
        arity=(1,),
        carriers=(DATE,),
        shapes=(PER_POLICY,),
        answers_carrier="date",
        attrs={"freq": ("Y", "M", "W", "D", "y", "m", "w", "d")},
        attrs_required=("freq",),
        clause=_CALENDAR,
        note="a Monday-starting week, which can open in the preceding year",
    )
)
def _to_period(call: Call, ctx: LoweringContext) -> Value:
    """Return the first day of the year, month or week each day falls in."""
    value = _per_policy(
        _dates(ctx.lower(call.args[0]), "date.to_period"), "date.to_period"
    )
    freq = str(dict(call.attrs)["freq"]).upper()
    days = value.array
    year, month, _ = civil_from_days(days)
    if freq == "Y":
        started = days_from_civil(year, jnp.ones_like(month), jnp.ones_like(month))
    elif freq == "M":
        started = days_from_civil(year, month, jnp.ones_like(month))
    elif freq == "W":
        # 1970-01-01 was a Thursday, so the Monday of a day's own week is
        # that day less however far past Monday it stands.
        started = days - ((days + 3) % 7)
    else:
        started = days
    return _as_date(started, value.shape, value.horizon)


@register(
    Capability(
        identifier="date.offset_by",
        refused_alike=_alike("date.offset_by", 1),
        arity=(1,),
        carriers=(DATE,),
        shapes=(PER_POLICY,),
        answers_carrier="date",
        attrs_required=("duration",),
        clause=_CALENDAR,
        note="months and years clamp the day; weeks and days add calendar days",
    )
)
def _offset_by(call: Call, ctx: LoweringContext) -> Value:
    """Return each day moved by the duration the node names."""
    value = _per_policy(
        _dates(ctx.lower(call.args[0]), "date.offset_by"), "date.offset_by"
    )
    count, unit = _duration(str(dict(call.attrs)["duration"]))
    if unit in _MONTH_UNITS:
        moved = moved_by_months(value.array, jnp.asarray(count * _MONTH_UNITS[unit]))
    else:
        moved = value.array + count * _DAY_UNITS[unit]
    return _as_date(moved, value.shape, value.horizon)


@register(
    Capability(
        identifier="excel.edate",
        refused_alike=_alike("excel.edate", 2) | {"carrier@1": _MONTHS_KIND},
        answers_carrier="date",
        arity=(2,),
        # A double that is a whole number of months is that number, on every
        # side; one that is not is refused by value, as a whole-number
        # conversion refuses it, and text or a flag by kind.
        carriers=(DATE, NUMERIC - frozenset({"bool"})),
        # 11.1.33 states one date and one count of months per policy; the
        # reference producer refuses either held per period by name.
        shapes=(PER_POLICY, PER_POLICY),
        checks=("to_integer.integral",),
        clause=_CALENDAR,
        note="the same month clamp every month move in this family takes",
    )
)
def _edate(call: Call, ctx: LoweringContext) -> Value:
    """Return each day moved a signed whole number of calendar months."""
    value = _per_policy(_dates(ctx.lower(call.args[0]), "excel.edate"), "excel.edate")
    months = _whole_months(
        require_carrier(
            _per_policy(ctx.lower(call.args[1]), "excel.edate"),
            frozenset({"i64", "f64"}),
            "excel.edate",
            _CALENDAR,
        )
    )
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    axis = aligned(value, months)
    return _as_date(
        moved_by_months(axis.arrays[0], axis.arrays[1]), axis.shape, axis.horizon
    )


def _per_policy(value: Value, name: str) -> Value:
    """Return a calendar operand where it is one value per policy, or refuse.

    The declaration refuses an input or a node held per period before
    anything is lowered; an operand that is itself a calculation declares no
    shape, so it reaches here unchecked and the clause's bound is kept here.

    Raises:
        DomainRefused: If the operand stands per period.

    """
    if value.shape != "list":
        return value
    reads, move = PER_POLICY_READING[name]
    raise DomainRefused(
        what=(
            f"{name} is written over one value per period, and this clause "
            f"states {reads} for each policy"
        ),
        move=move,
        clause=_CALENDAR,
    )


def _whole_months(months: Value) -> Value:
    """Return a count of months held as a double as its whole number, or refuse.

    11.1.33's move is a signed whole number of months; a double that is not
    one is refused cell by cell under the whole-number conversion's check
    (11.1.23), and a whole one is carried exactly.
    """
    if months.carrier == "i64":
        return months
    outside = outside_integer_conversion(months.array)
    flag("to_integer.integral", outside)
    safe = jnp.where(outside, jnp.zeros_like(months.array), months.array)
    return Value(safe.astype(JNP_OF["i64"]), "i64", months.shape, "i64", months.horizon)


@register(
    Capability(
        identifier="excel.eomonth",
        refused_alike=_alike("excel.eomonth", 2) | {"carrier@1": _MONTHS_KIND},
        answers_carrier="date",
        arity=(2,),
        # Its months are excel.edate's: a whole double is that number, one
        # that is not is refused by value, and text or a flag by kind.
        carriers=(DATE, NUMERIC - frozenset({"bool"})),
        # 11.1.33 states one date and one count of months per policy; the
        # reference producer refuses either held per period by name.
        shapes=(PER_POLICY, PER_POLICY),
        checks=("to_integer.integral",),
        clause=_CALENDAR,
        note="the month is moved first and the last day of it taken after",
    )
)
def _eomonth(call: Call, ctx: LoweringContext) -> Value:
    """Return the last day of the month each day lands in after the move."""
    value = _per_policy(
        _dates(ctx.lower(call.args[0]), "excel.eomonth"), "excel.eomonth"
    )
    months = _whole_months(
        require_carrier(
            _per_policy(ctx.lower(call.args[1]), "excel.eomonth"),
            frozenset({"i64", "f64"}),
            "excel.eomonth",
            _CALENDAR,
        )
    )
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    axis = aligned(value, months)
    landed = moved_by_months(axis.arrays[0], axis.arrays[1])
    year, month, _ = civil_from_days(landed)
    return _as_date(
        days_from_civil(year, month, last_day_of(year, month)),
        axis.shape,
        axis.horizon,
    )


@register(
    Capability(
        identifier="excel.from_excel_serial",
        refused_alike=_alike("excel.from_excel_serial", 1),
        arity=(1,),
        carriers=(NUMERIC - frozenset({"bool"}),),
        shapes=(PER_POLICY,),
        answers_carrier="date",
        checks=("excel.serial.epoch",),
        attrs={"epoch": (_EPOCH_1900, _EPOCH_1904)},
        clause=_CALENDAR,
        note=(
            "the 1900 system's phantom 29 February is read as 28 February, "
            "as the spreadsheet does"
        ),
    )
)
def _from_excel_serial(call: Call, ctx: LoweringContext) -> Value:
    """Return the calendar day one spreadsheet serial stands for.

    A serial below 1 is a null under both epoch systems, and a null is a
    value this engine states no answer over -- flagged rather than counted
    here, so it refuses at completion with the rest.
    """
    value = _per_policy(ctx.lower(call.args[0]), "excel.from_excel_serial")
    whole = jnp.floor(value.array.astype(JNP_OF["f64"]))
    flag("excel.serial.epoch", whole < 1)
    numbers = whole.astype(JNP_OF["i64"])
    if str(dict(call.attrs).get("epoch", _EPOCH_1900)) == _EPOCH_1904:
        return _as_date(_DAYS_TO_1904 + numbers, value.shape, value.horizon)
    # Up to the phantom day the serials count on from 1 January 1900 and the
    # phantom itself reads as the day before it; past it they carry the extra
    # day the system never had, which is what makes 61 the first of March.
    return _as_date(
        jnp.where(
            numbers <= _PHANTOM,
            _DAYS_TO_1900 + jnp.minimum(numbers, _LAST_REAL) - 1,
            _DAYS_TO_1900 + numbers - 2,
        ),
        value.shape,
        value.horizon,
    )


@register(
    Capability(
        identifier="date.date_ranges",
        refused_alike=_alike("date.date_ranges", 2),
        arity=(2,),
        carriers=(DATE, DATE),
        shapes=(PER_POLICY, PER_POLICY),
        answers="list",
        answers_carrier="date",
        attrs={"closed": ("both", "left", "right", "none")},
        attrs_required=("interval",),
        horizon="generator",
        sizes_its_own_axis=True,
        clause=_CALENDAR,
        note=(
            "every candidate is offset from the original start, never from "
            "the previously clamped date; the row width is the longest span "
            "in the book divided by the interval, with no grid bounding it"
        ),
    )
)
def _date_ranges(call: Call, ctx: LoweringContext) -> Value:
    """Return the candidate days from each start to each end, as the interval steps."""
    start = _per_policy(
        _dates(ctx.lower(call.args[0]), "date.date_ranges"), "date.date_ranges"
    )
    end = _per_policy(
        _dates(ctx.lower(call.args[1]), "date.date_ranges"), "date.date_ranges"
    )
    attrs = dict(call.attrs)
    count, unit = _duration(str(attrs["interval"]))
    if count <= 0:
        raise DomainRefused(
            what=(
                f"this range steps by {count}, and an interval is a positive "
                "count of its unit"
            ),
            move="write a positive interval, and swap the endpoints if the "
            "range runs backwards",
            clause=_CALENDAR,
        )
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    axis = aligned(start, end)
    opened, closed_at = axis.arrays
    reach = _candidates(opened, closed_at, count, unit)
    # Over the candidates the host already counted for this call, so the
    # rectangle's width is not read back off the device.
    horizon = Horizon.over(jnp.maximum(reach, 0), host=ctx.cells_of(call))
    steps = jnp.arange(horizon.bucket)[None, :]
    if unit in _MONTH_UNITS:
        cells = moved_by_months(
            jnp.broadcast_to(opened[:, None], (opened.shape[0], horizon.bucket)),
            jnp.asarray(steps * count * _MONTH_UNITS[unit]),
        )
    else:
        cells = opened[:, None] + steps * count * _DAY_UNITS[unit]
    kept = _endpoints_kept(cells, opened, closed_at, str(attrs.get("closed", "both")))
    return _shrunk(cells, kept, horizon)


@register_sizing("date.date_ranges")
def _range_cells(call: Call, ctx: LoweringContext) -> jax.Array:
    """Return how many candidate days each row of this range lays down.

    **No grid bounds this one, and that is stated rather than hidden.** Every
    other axis in this engine is rounded up to one of a dozen widths, because
    a term book has hundreds of period counts and one program each would cost
    a quarter of an hour. A calendar range is not a term: its width is the
    longest span in the book divided by the interval, and a daily range over
    a century is thirty-six thousand cells per row whether or not any row
    needs them. What keeps that honest is that the width is read here, on the
    host, before anything is allocated -- so a book that would ask for an
    array of that size is a fact about the book, visible in the shape the
    report carries, and not a surprise inside a compiled program.
    """
    start = _per_policy(
        _dates(ctx.lower(call.args[0]), "date.date_ranges"), "date.date_ranges"
    )
    end = _per_policy(
        _dates(ctx.lower(call.args[1]), "date.date_ranges"), "date.date_ranges"
    )
    count, unit = _duration(str(dict(call.attrs)["interval"]))
    if count <= 0:
        # The lowering refuses this by name; a sizing asked before it has run
        # answers nothing rather than refusing twice.
        return jnp.zeros((ctx.rows,), dtype=JNP_OF["i64"])
    from gaspatchio_jax.horizon import aligned  # noqa: PLC0415 -- one alignment

    opened, closed_at = aligned(start, end).arrays
    return jnp.maximum(_candidates(opened, closed_at, count, unit), 0)


def _candidates(
    opened: jax.Array, closed_at: jax.Array, count: int, unit: str
) -> jax.Array:
    """Return how many candidates each row has before the endpoint rule.

    An upper bound taken in whole units and then trimmed by the rule itself:
    a month candidate lands on a clamped day, so counting elapsed months and
    adding one reaches every candidate at or before the end and never fewer.
    """
    if unit in _MONTH_UNITS:
        start_year, start_month, _ = civil_from_days(opened)
        end_year, end_month, _ = civil_from_days(closed_at)
        elapsed = 12 * (end_year - start_year) + (end_month - start_month)
        reach = jnp.floor_divide(elapsed, count * _MONTH_UNITS[unit]) + 2
    else:
        elapsed = closed_at - opened
        reach = jnp.floor_divide(elapsed, count * _DAY_UNITS[unit]) + 1
    return jnp.where(closed_at < opened, 0, jnp.maximum(reach, 0))


def _endpoints_kept(
    cells: jax.Array, opened: jax.Array, closed_at: jax.Array, closed: str
) -> jax.Array:
    """Return which cells the interval and the endpoint rule keep."""
    inside = cells <= closed_at[:, None]
    if closed in ("right", "none"):
        inside = inside & (cells != opened[:, None])
    if closed in ("left", "none"):
        inside = inside & (cells != closed_at[:, None])
    return inside


def _shrunk(cells: jax.Array, kept: jax.Array, horizon: Horizon) -> Value:
    """Return the kept cells packed to the front of each row, with its own count.

    A candidate the endpoint rule dropped is at the *start* of a row, never in
    the middle of it, so what packing has to do is move each row left by
    however many of its own leading cells were dropped -- and the count each
    row keeps is what the trim cuts it back to.

    **That count is read back off the device**, the one count a settlement
    still reads: which candidates the endpoint rule keeps depends on the days
    themselves, and the host holds only how many candidates there are. A
    model that lays a calendar range therefore settles each batch after the
    card has finished the one before it, as every model did before settling
    was made to read nothing back; the answer is the same either way.
    """
    dropped = jnp.sum(~kept & horizon.active, axis=1)
    leading = jnp.argmax(kept & horizon.active, axis=1)
    steps = jnp.arange(horizon.bucket)[None, :] + leading[:, None]
    packed = jnp.take_along_axis(cells, jnp.clip(steps, 0, horizon.bucket - 1), axis=1)
    held = Horizon.over(jnp.maximum(horizon.t - dropped, 0), bucket=horizon.bucket)
    return Value(packed.astype(JNP_OF["date"]), "date", "list", "list[date]", held)
