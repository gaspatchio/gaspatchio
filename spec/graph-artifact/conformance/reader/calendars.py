# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent calendars rules for the published synthetic vectors."""

from __future__ import annotations

import calendar
import math
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .finance import recipe_for
from .shared import Column, DomainRefusal, map_values


def month_offset(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def whole_months(months):
    """Read 11.1.33's signed whole number of months, refusing anything else.

    A double that is a whole number is that number; one that is not is
    refused as a whole-number conversion refuses it (11.1.23), and text or a
    flag by kind.
    """
    if isinstance(months, bool) or not isinstance(months, (int, float)):
        raise DomainRefusal("calendar-months-kind")
    if isinstance(months, float):
        if not math.isfinite(months) or months != math.floor(months):
            raise DomainRefusal("checked-integer-conversion")
        return int(months)
    return months


def date_offset(day: date, duration: str) -> date:
    match = re.fullmatch(r"(-?\d+)(mo|y|w|d)", duration)
    if match is None:
        raise DomainRefusal("calendar-duration-capability")
    count, unit = int(match[1]), match[2]
    return (
        month_offset(day, count * (12 if unit == "y" else 1))
        if unit in {"mo", "y"}
        else day + timedelta(days=count * (7 if unit == "w" else 1))
    )


def year_fraction(start: date, end: date, basis: int | str) -> float:
    aliases = {
        "act/360": 2,
        "actual/360": 2,
        "act/365": 3,
        "actual/365": 3,
        "act/act": 1,
        "actual/actual": 1,
        "30/360": 0,
        "us_nasd_30_360": 0,
        "30e/360": 4,
        "european_30_360": 4,
        "actual_360": 2,
        "actual_365": 3,
    }
    basis = aliases.get(basis.lower(), basis) if isinstance(basis, str) else basis
    if start > end:
        return year_fraction(end, start, basis)
    if basis in {2, 3}:
        return (end - start).days / (360 if basis == 2 else 365)
    if basis in {0, 4}:
        return thirty_360(start, end, european=basis == 4)
    if basis != 1:
        raise DomainRefusal("yearfrac-basis")
    return actual_actual(start, end)


def thirty_360(start: date, end: date, *, european: bool) -> float:
    first, last = start.day, end.day
    if european:
        last = min(last, 30)
    else:
        feb_start = start.month == 2 and first == calendar.monthrange(start.year, 2)[1]
        feb_end = end.month == 2 and last == calendar.monthrange(end.year, 2)[1]
        if last == 31 and first >= 30:
            last = 30
        elif feb_start and feb_end:
            last = 30
        if feb_start:
            first = 30
    return (
        (end.year - start.year) * 360
        + (end.month - start.month) * 30
        + last
        - min(first, 30)
    ) / 360


def actual_actual(start: date, end: date) -> float:
    days = (end - start).days
    if start.year == end.year:
        return days / (366 if calendar.isleap(start.year) else 365)
    if end.year == start.year + 1 and (end.month, end.day) <= (start.month, start.day):
        has_leap = any(
            calendar.isleap(year) and start <= date(year, 2, 29) <= end
            for year in range(start.year, end.year + 1)
        )
        return days / (366 if has_leap else 365)
    years = range(start.year, end.year + 1)
    return days / (
        sum(366 if calendar.isleap(year) else 365 for year in years) / len(years)
    )


def date_cell(name: str, values: tuple, attrs: dict):
    if any(value is None for value in values):
        return None
    if name == "excel.from_excel_serial":
        return excel_serial(values[0], attrs["epoch"])
    first = date.fromisoformat(values[0])
    if name == "date.offset_by":
        return date_offset(first, attrs["duration"]).isoformat()
    if name == "date.to_period":
        return period_start(first, attrs["freq"]).isoformat()
    if name in {"excel.edate", "excel.eomonth"}:
        answer = month_offset(first, whole_months(values[1]))
        if name == "excel.eomonth":
            answer = answer.replace(
                day=calendar.monthrange(answer.year, answer.month)[1]
            )
        return answer.isoformat()
    second = date.fromisoformat(values[1])
    if name == "excel.days":
        return (first - second).days
    if name == "date.months_between":
        return (second.year - first.year) * 12 + second.month - first.month
    if name == "excel.yearfrac":
        return year_fraction(first, second, attrs["basis"])
    return date_range(first, second, attrs["interval"], attrs["closed"])


def excel_serial(value: float, epoch: str) -> str | None:
    if epoch not in {"1900", "1904"}:
        raise DomainRefusal("excel-epoch-capability")
    serial = math.floor(value)
    if serial < 1:
        return None
    if epoch == "1904":
        return (date(1904, 1, 1) + timedelta(days=serial)).isoformat()
    return (
        date(1899, 12, 30)
        + timedelta(days=60 if serial == 60 else serial + (serial < 60))
    ).isoformat()


def period_start(first: date, token: str) -> date:
    choices = {
        "Y": first.replace(month=1, day=1),
        "M": first.replace(day=1),
        "W": first - timedelta(days=first.weekday()),
        "D": first,
    }
    if token.upper() not in choices:
        raise DomainRefusal("date-period-capability")
    return choices[token.upper()]


def date_range(start: date, end: date, interval: str, closed: str) -> list[str]:
    match = re.fullmatch(r"([1-9]\d*)(mo|y|w|d)", interval)
    if match is None:
        raise DomainRefusal("calendar-range-capability")
    result, position = [], 0
    while True:
        current = date_offset(start, f"{position * int(match[1])}{match[2]}")
        if current > end:
            return result
        if (current != start or closed in {"both", "left"}) and (
            current != end or closed in {"both", "right"}
        ):
            result.append(current.isoformat())
        position += 1


def irr_value(row):
    """Bisection over the stated unique-root domain; no producer Newton code."""
    if row is None or not row or any(value is None for value in row):
        return None
    if not any(value > 0 for value in row) or not any(value < 0 for value in row):
        return None
    if row[0] >= 0 or any(value < 0 for value in row[1:]):
        raise DomainRefusal("irr-multiple-sign-changes")
    low, high = -0.9, 1.0

    def npv(rate: float) -> float:
        # Only the sign is needed. Scale negative-rate evaluations by
        # (1 + rate) ** (T - 1), avoiding underflowing denominators at T=600.
        value = 0.0
        if rate < 0:
            for cashflow in row:
                value = value * (1 + rate) + cashflow
        else:
            for cashflow in reversed(row):
                value = value / (1 + rate) + cashflow
        return value

    if npv(low) < 0 or npv(high) > 0:
        raise DomainRefusal("irr-root-outside-bracket")
    for _ in range(100):
        mid = (low + high) / 2
        if npv(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def spreadsheet_round(value: float, num_digits: int) -> float:
    """Round as section 11.1.35 states: the fifteen-digit value, half away.

    The operand's exact decimal expansion is taken to fifteen significant
    digits, a sixteenth of 5 or more going away from zero; that decimal is
    rounded to ``num_digits`` places, a half going away from zero; the
    nearest double is read back with the operand's sign. ``ROUND_HALF_UP``
    is Python's name for away from zero. Where fifteen digits are no finer
    than the step, the second rounding has nothing left to move.
    """
    if not math.isfinite(value) or value == 0.0:
        return value
    with localcontext() as context:
        # Enough for any double's exact expansion, which has at most 767
        # significant digits.
        context.prec = 800
        exact = Decimal(value)
        unit = exact.adjusted() - 14
        held = exact.quantize(Decimal(1).scaleb(unit), rounding=ROUND_HALF_UP)
        if unit < -num_digits:
            held = held.quantize(Decimal(1).scaleb(-num_digits), rounding=ROUND_HALF_UP)
        answer = float(held)
    # Fifteen digits of the largest doubles are past the largest double; the
    # clause's domain excludes an overflow, and the value answers itself.
    return value if math.isinf(answer) else math.copysign(abs(answer), value)


def excel_numeric(name: str, operands: list[Column], attrs: dict) -> Column:
    if name == "excel.irr":
        # 11.1.36: a supplied guess is a scalar Float64 operand.
        if len(operands) > 1 and operands[1].listed:
            raise DomainRefusal("irr-guess-per-period")
        return Column("f64", [irr_value(row) for row in operands[0].values])

    def cell(*values):
        if any(value is None for value in values):
            return None
        # 11.1.35: a whole-number operand answers a Float64 cell like any
        # other, so each operand is read as its double first.
        values = [float(value) for value in values]
        if name == "excel.round":
            return spreadsheet_round(values[0], attrs["num_digits"])
        rate, periods, payment = values
        future, timing = float(attrs["fv"] or 0.0), attrs["typ"] or 0
        if rate == 0:
            return -(payment * periods + future)
        # 11.1.35: (1 + r)^-n as exp(-n log1p(r)) and 1 - (1 + r)^-n as
        # -expm1(-n log1p(r)), so neither rounds 1 + r first and the 1e-12
        # bound holds however near nought the rate is.
        grown = periods * math.log1p(rate)
        paid_off = -math.expm1(-grown)
        return -(
            payment * ((1 + rate * timing) * paid_off / rate)
            + future * math.exp(-grown)
        )

    return map_values(cell, operands, "f64")


def dates(name: str, operands: list[Column], attrs: dict) -> Column:
    # 11.1.33 states every operation in it but excel.yearfrac over one value
    # per policy; an operand held per period is outside the entry.
    if name != "excel.yearfrac" and any(column.listed for column in operands):
        raise DomainRefusal("calendar-operand-per-period")
    inner = {
        "excel.days": "i64",
        "date.months_between": "i64",
        "excel.yearfrac": "f64",
        "date.date_ranges": "list[date]",
    }.get(name, "date")
    return map_values(lambda *values: date_cell(name, values, attrs), operands, inner)


def schedule_months(recipe: dict) -> int:
    if (recipe["calendar"], recipe["convention"], recipe["day_count"]) != (
        "NullCalendar",
        "Unadjusted",
        "OneTwelfth",
    ):
        raise DomainRefusal("schedule-calendar-capability")
    months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}.get(recipe["frequency"])
    if months is None:
        raise DomainRefusal("schedule-frequency-capability")
    if recipe["kind"] == "from_calendar_grid" and recipe.get("anchor") != "exact_date":
        raise DomainRefusal("schedule-anchor-capability")
    return months


def schedule_periods(
    recipe: dict, inputs: dict[str, Column], row: int, months: int
) -> int:
    if recipe["kind"] != "per_policy_grid":
        return recipe["n_periods"]
    term = inputs[recipe["until_value_column"]].values[row] or 0
    return max(0, term * (12 if recipe["until_kind"] == "term_years" else 1) // months)


def schedule_start(recipe: dict, inputs: dict[str, Column], row: int) -> date:
    if "start_date" in recipe:
        return date.fromisoformat(recipe["start_date"])
    return date.fromisoformat(inputs[recipe["inception_column"]].values[row])


def schedule_active(
    recipe: dict,
    inputs: dict[str, Column],
    row: int,
    attrs: dict,
    periods: int,
    months: int,
) -> list:
    if recipe["kind"] != "from_inception" or not attrs.get("end_date_column"):
        return [True] * periods
    end = inputs[attrs["end_date_column"]].values[row]
    if end is None:
        return [True] * periods
    start = schedule_start(recipe, inputs, row)
    return [
        month_offset(start, (t + 1) * months) <= date.fromisoformat(end)
        for t in range(periods)
    ]


def schedule_row(
    suffix: str,
    recipe: dict,
    inputs: dict[str, Column],
    row: int,
    attrs: dict,
    months: int,
) -> int | list:
    periods = schedule_periods(recipe, inputs, row, months)
    if suffix == "per_policy_period_count":
        return periods
    if suffix.endswith("period_dates"):
        return schedule_boundaries(recipe, inputs, row, periods, months)
    if suffix == "year_fractions":
        return [months / 12] * periods
    if suffix == "t_years":
        return [t * months / 12 for t in range(periods + 1)]
    if suffix == "anniversary_mask":
        return [((t + 1) * months) % 12 == 0 for t in range(periods)]
    active = schedule_active(recipe, inputs, row, attrs, periods, months)
    return active if suffix == "is_in_force" else [not flag for flag in active]


def schedule_boundaries(
    recipe: dict, inputs: dict[str, Column], row: int, periods: int, months: int
) -> list[str]:
    if recipe["kind"] == "per_policy_grid":
        term = inputs[recipe["until_value_column"]].values[row]
        if term is None or term < 0:
            raise DomainRefusal("schedule-boundary-term-domain")
    start = schedule_start(recipe, inputs, row)
    if recipe["kind"] != "from_calendar_grid":
        return [month_offset(start, t * months).isoformat() for t in range(periods + 1)]
    boundaries = [start.isoformat()]
    for _ in range(periods):
        start = month_offset(start, months)
        boundaries.append(start.isoformat())
    return boundaries


def fixed_step_row(suffix: str, recipe: dict, attrs: dict) -> list:
    # 11.1.37's fourth kind: one shared axis, no dates, time one IEEE operation
    # per boundary -- k * step_years or k / steps_per_year, never a running sum.
    if set(recipe) not in (
        {"kind", "n_periods", "step_years"},
        {"kind", "n_periods", "steps_per_year"},
    ):
        raise DomainRefusal("schedule-fixed-step-recipe")
    periods, per_year = recipe["n_periods"], recipe.get("steps_per_year")
    if suffix == "t_years":
        if per_year is not None:
            return [k / per_year for k in range(periods + 1)]
        return [k * recipe["step_years"] for k in range(periods + 1)]
    if suffix == "year_fractions":
        return [
            1 / per_year if per_year is not None else recipe["step_years"]
        ] * periods
    if suffix == "anniversary_mask" and per_year is not None:
        return [(t + 1) % per_year == 0 for t in range(periods)]
    if suffix in ("is_in_force", "contract_boundary") and not attrs.get(
        "end_date_column"
    ):
        return [suffix == "is_in_force"] * periods
    raise DomainRefusal("schedule-fixed-step-capability")


def schedule_value(
    name: str, inputs: dict[str, Column], attrs: dict, assumptions: list[dict]
) -> Column:
    recipe = recipe_for("schedule", attrs["schedule"], assumptions)
    if recipe["kind"] == "fixed_step":
        suffix = name.split(".")[1]
        inner = {"t_years": "list[f64]", "year_fractions": "list[f64]"}.get(
            suffix, "list[bool]"
        )
        count = len(next(iter(inputs.values())).values)
        return Column(
            inner, [fixed_step_row(suffix, recipe, attrs) for _ in range(count)]
        )
    months = schedule_months(recipe)
    count = len(next(iter(inputs.values())).values)
    suffix = name.split(".")[1]
    inner = {
        "per_policy_period_count": "i64",
        "period_dates": "list[date]",
        "per_policy_period_dates": "list[date]",
        "year_fractions": "list[f64]",
        "t_years": "list[f64]",
    }.get(suffix, "list[bool]")
    return Column(
        inner,
        [
            schedule_row(suffix, recipe, inputs, row, attrs, months)
            for row in range(count)
        ],
    )
