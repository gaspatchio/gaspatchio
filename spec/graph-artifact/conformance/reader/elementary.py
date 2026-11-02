# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent elementary rules for the published synthetic vectors."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from functools import partial
from operator import add, mul

from .base import as_indicator, check_exact_conversion
from .shared import Column, DomainRefusal, as_double, held_whole, map_values

# The significant figures a spreadsheet holds of a double (11.1.35).
_HELD_FIGURES = 15
# Room for every digit a double's exact value has, and a carry.
_EXACT = Context(prec=800, Emin=-9999, Emax=9999)


def _at_the_pole(function, pole: float):
    """Return a logarithm answering -inf at its pole, as binary64 does.

    The logarithm of 0.0 -- a flag that is false read as its 0.0 (11.1.25)
    among them -- is minus infinity in every engine, where the host's raises.
    """
    return lambda value: -math.inf if value == pole else function(value)


UNARY_MATH = {
    "abs": abs,
    # 11.1.12: the sign of a NaN is NaN -- it is neither below nought nor
    # above it nor at it.
    "sign": lambda value: value if math.isnan(value) else float((value > 0) - (value < 0)),
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,
    "exp": math.exp,
    "log": _at_the_pole(math.log, 0.0),
    "log10": _at_the_pole(math.log10, 0.0),
    "log1p": _at_the_pole(math.log1p, -1.0),
    # 11.1.12: the standard normal distribution function, in the
    # complementary form that keeps the lower tail's digits.
    "norm_cdf": lambda value: 0.5 * math.erfc(-value / math.sqrt(2.0)),
    "floor": math.floor,
    "ceil": math.ceil,
}


# The calls of 11.1.8 and 11.1.12, each reading a number.
READS_A_NUMBER = frozenset(UNARY_MATH) | {"round", "round_sig_figs"}

# 11.1.8 and 11.1.12: the four of them that keep a whole number whole, and
# answer it in whole-number arithmetic rather than through a double. The
# absolute value of the least i64 is the one answer an i64 does not hold.
WHOLE_MATH = {
    "abs": lambda value: held_whole(abs(value)),
    "sign": lambda value: (value > 0) - (value < 0),
    "floor": lambda value: value,
    "ceil": lambda value: value,
}


def checked_integer(value) -> int:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainRefusal("checked-integer-conversion")
    # 11.1.23: an integer stored in a width wider than i64 is an integer for
    # this call and is judged on its value. A whole number past the range is
    # whole, so it is refused as a range rather than as a lossy conversion --
    # the two refusals are about different defects and name different doors.
    if isinstance(value, int):
        if not -(2**63) <= value <= 2**63 - 1:
            raise DomainRefusal("integer-range-conversion")
        return value
    if not math.isfinite(value) or int(value) != value or not -(2**63) <= value < 2**63:
        raise DomainRefusal("checked-integer-conversion")
    return int(value)


# 11.1.38: the closed interval in which every whole number has a double of
# its own. Past it two neighbouring whole numbers share a double.
EXACT_IN_DOUBLE = 2**53


def widened_double(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainRefusal("float-conversion-type")
    if isinstance(value, float):
        return value
    if not -EXACT_IN_DOUBLE <= value <= EXACT_IN_DOUBLE:
        raise DomainRefusal("checked-float-conversion")
    return float(value)


# 11.1.39: the decimal exponents a double is written out in fixed form
# between. Outside them it goes in exponent form. Stated as the two numbers
# the clause states rather than derived from anything.
WRITTEN_FIXED_BETWEEN = (-5, 15)


def written_float(value: float) -> str:
    """Write a double out as 11.1.39 states it.

    The digits are the shortest decimal that reads back to the same double,
    which is what ``repr`` produces; the *layout* of those digits is what
    11.1.39 states and ``repr`` does not follow, so the digits are taken
    apart and laid out here. Fixed form between the two exponents above,
    with at least one digit after the point; exponent form outside them,
    with the exponent's sign always written and never padded. ``repr``
    pads a one-digit exponent and switches forms at other thresholds, so
    this is not ``repr`` with a wrapper around it.
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    sign = "-" if math.copysign(1.0, value) < 0 else ""
    if value == 0.0:
        return sign + "0.0"
    mantissa, _, written = repr(abs(value)).partition("e")
    exponent = int(written or 0)
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    # Where the first significant digit stands, counting from the point the
    # shortest decimal put it at and then from the leading zeros it wrote.
    exponent += len(whole) - 1 - (len(whole + fraction) - len(digits))
    digits = digits.rstrip("0") or "0"
    low, high = WRITTEN_FIXED_BETWEEN
    if low <= exponent <= high:
        if exponent < 0:
            return f"{sign}0.{'0' * (-exponent - 1)}{digits}"
        whole = digits[: exponent + 1].ljust(exponent + 1, "0")
        return f"{sign}{whole}.{digits[exponent + 1 :] or '0'}"
    lead, rest = digits[0], digits[1:]
    written = f"{lead}.{rest}" if rest else lead
    return f"{sign}{written}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def written_text(value) -> str | None:
    """Write one value out as 11.1.39 states it, and nothing else.

    A date arrives as its ISO calendar day already, and a category arrives
    as its string, so both are carried unchanged. A float is laid out by
    the function above, which is where the whole of 11.1.39's convention
    for one lives.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return written_float(value)
    return str(value)


def parse_date(value: str, *, attrs: dict) -> str | None:
    if attrs["format"] is None or not attrs["exact"]:
        raise DomainRefusal("date-parser-capability")
    try:
        return datetime.strptime(value, attrs["format"]).date().isoformat()
    except ValueError:
        if attrs["strict"]:
            raise DomainRefusal("invalid-date") from None
        return None


def rounding(value: float, *, name: str, attrs: dict) -> float:
    """Round to decimal places (11.1.8) or to significant figures (11.1.12).

    Both read a double as the fifteen significant figures a spreadsheet
    holds (:func:`fifteen_figures`) and round that decimal in decimal
    arithmetic. ``round`` carries its tie rule as an attribute and is
    dispatched on it. ``round_sig_figs`` carries none, and 11.1.12 states
    one: a tie rounds half away from zero, for either sign. A whole number is
    on every step ``round`` takes at or after the point and is its own
    answer there; to tens and coarser it is moved in whole-number arithmetic,
    as ``round_sig_figs`` keeps its figures.
    """
    if name == "round_sig_figs" and type(value) is int:
        return whole_sig_figs(value, attrs["digits"])
    if name == "round_sig_figs":
        return decimal_sig_figs(value, attrs["digits"])
    if type(value) is int:
        return whole_places(value, attrs.get("decimals", 0), attrs["mode"])
    return decimal_places(value, attrs.get("decimals", 0), attrs["mode"])


def whole_places(value: int, decimals: int, mode: str) -> int:
    """Move a whole number to the nearest multiple of ``10**-decimals`` (11.1.8).

    At or after the point a whole number is already on the step. To tens and
    coarser it is moved exactly in whole numbers by the tie rule: 25 to tens
    is 20 to the even neighbour and 30 away from zero. An answer outside
    ``i64`` is refused.
    """
    if decimals >= 0:
        return value
    step = 10**-decimals
    kept, rest = divmod(abs(value), step)
    if 2 * rest > step or (
        2 * rest == step and (mode == "half_away_from_zero" or kept % 2 == 1)
    ):
        kept += 1
    rounded = kept * step if value >= 0 else -kept * step
    if not -(2**63) <= rounded <= 2**63 - 1:
        raise DomainRefusal("integer-overflow")
    return rounded


# 11.1.8's two tie rules, as decimal arithmetic names them.
_TIE_RULES = {"half_to_even": ROUND_HALF_EVEN, "half_away_from_zero": ROUND_HALF_UP}


def decimal_places(value: float, decimals: int, mode: str) -> float:
    """Move a double's fifteen-digit reading to ``decimals`` places (11.1.8).

    The double is read as its fifteen-significant-digit decimal
    (:func:`fifteen_figures`), that decimal is moved to the nearest multiple
    of ten to the minus ``decimals`` by the tie rule, and the answer is the
    double nearest the result, with the value's sign. 2.675 reads as
    2.67500000000000, a half, so it is 2.68 at two places under either rule;
    0.285 is 0.28 to the even neighbour and 0.29 away from zero. A negative
    ``decimals`` moves it to tens and coarser the same way: 1234.5 to
    hundreds is 1200.0. A reading already on a step is its own answer, and
    one past the largest double is refused.
    """
    if not value or not math.isfinite(value):
        return value
    held = fifteen_figures(value)
    step = Decimal((0, (1,), -decimals))
    if step.as_tuple().exponent > held.as_tuple().exponent:
        held = held.quantize(step, rounding=_TIE_RULES[mode], context=_EXACT)
    rounded = float(held)
    if not math.isfinite(rounded):
        raise DomainRefusal("rounding-past-the-largest-double")
    return math.copysign(rounded, value)


def fifteen_figures(value: float) -> Decimal:
    """Read a double as a spreadsheet holds it: fifteen significant figures.

    The double's exact decimal expansion is cut to fifteen significant digits,
    a sixteenth digit of 5 or more going away from zero -- a double that is
    itself exactly a sixteen-digit tie included (11.1.35). 0.15, exactly
    0.1499999999999999944..., reads as 0.150000000000000.
    """
    exact = Decimal(value)
    step = Decimal((0, (1,), exact.adjusted() - _HELD_FIGURES + 1))
    return exact.quantize(step, rounding=ROUND_HALF_UP, context=_EXACT)


def decimal_sig_figs(value: float, digits: int) -> float:
    """Keep a double's leading ``digits`` figures as a spreadsheet does (11.1.12).

    The double is read as its fifteen-significant-digit decimal
    (:func:`fifteen_figures`), that decimal is cut to ``digits`` figures in
    decimal arithmetic with a half away from zero, and the answer is the
    double nearest the result: 0.15 to one figure is 0.2, 2.675 to three is
    2.68, and 781098.0 to one is 800000.0. Scaled by a power of ten in
    doubles the figures were not: 781098.0 answered 799999.9999999999.
    From fifteen figures up the answer is the fifteen-digit value itself.
    The arithmetic is exact at every magnitude; an answer past the largest
    double is refused.
    """
    if not value or not math.isfinite(value):
        return value
    held = fifteen_figures(value)
    if digits < _HELD_FIGURES:
        step = Decimal((0, (1,), held.adjusted() - digits + 1))
        held = held.quantize(step, rounding=ROUND_HALF_UP, context=_EXACT)
    rounded = float(held)
    if not math.isfinite(rounded):
        raise DomainRefusal("significant-figures-past-the-largest-double")
    return rounded


def whole_sig_figs(value: int, digits: int) -> int:
    """Keep a whole number's leading ``digits`` figures exactly (11.1.12).

    A whole number keeps its type and is rounded in whole-number arithmetic,
    a tie away from zero; through a double 781,098 to one figure answered
    799,999. An answer outside ``i64`` is refused.
    """
    magnitude = abs(value)
    cut = len(str(magnitude)) - digits
    if cut <= 0:
        return value
    step = 10**cut
    kept, rest = divmod(magnitude, step)
    kept += 2 * rest >= step
    # The sign goes back on in whole numbers too: a double here is the
    # detour this paragraph exists to keep out, and 2^62 to seventeen
    # figures came back as 2^62 through one.
    return held_whole(kept * step if value >= 0 else -(kept * step))


def interval_label(value: float, breaks: list, labels: list, *, attrs: dict) -> str | None:
    # 11.1.4: a NaN lies in no interval -- it is neither above a breakpoint
    # nor below it -- so it takes none and is null, as a null value is.
    if isinstance(value, float) and math.isnan(value):
        return None
    index = sum(
        value >= point if attrs["left_closed"] else value > point for point in breaks
    )
    return labels[index]


def replacement(value, old: list, new):
    if value not in old:
        return value
    return new[old.index(value)] if isinstance(new, list) else new


def clip(value: float, *bounds: float, attrs: dict) -> float:
    if attrs["bounds"] in {"both", "lower"}:
        if value < bounds[0]:
            return bounds[0]
    if attrs["bounds"] in {"both", "upper"}:
        value = min(value, bounds[-1])
    return value


_ELEMENTS = {
    "is_nan": math.isnan,
    "is_not_nan": lambda value: not math.isnan(value),
    "is_finite": math.isfinite,
    "is_infinite": math.isinf,
    # Equality, member by member: Python's ``in`` tries identity first, so a
    # NaN would be a member of a set holding that very NaN object. 11.1.26:
    # a NaN equals no member, so is_in of a NaN is false on every side.
    "is_in": lambda value, choices: any(value == choice for choice in choices),
    "replace": replacement,
}


def element_function(name: str, attrs: dict, inner: str):
    if name in WHOLE_MATH and inner == "i64":
        return WHOLE_MATH[name]
    if name in UNARY_MATH:
        return lambda value: float(UNARY_MATH[name](value))
    if name in {"round", "round_sig_figs"}:
        return partial(rounding, name=name, attrs=attrs)
    if name in {"clip", "cut", "str.to_date"}:
        function = {"clip": clip, "cut": interval_label, "str.to_date": parse_date}[
            name
        ]
        return partial(function, attrs=attrs)
    return _ELEMENTS[name]


def nullable_cell(value, *extra, function, null_result, double: bool = False):
    if value is None:
        return null_result
    answer = function(value, *extra)
    return as_double(answer) if double else answer


def filled_type(value: Column, fill: Column) -> str:
    """Name the type a value and its fill share (11.1.13).

    Two of ``i64``, ``f64`` and a ``bool`` fill share ``f64`` where either
    is, the whole number inside the exact range a double names every whole
    number in; a ``bool`` fill stands as the 0 or 1 it indicates. Two of one
    other family share it. A fill of another family is outside the entry.
    """
    pair = {value.inner, fill.inner}
    if value.inner in {"i64", "f64"} and fill.inner in {"i64", "f64", "bool"}:
        if "f64" in pair:
            check_exact_conversion(value, fill)
            return "f64"
        return "i64"
    if value.inner == fill.inner:
        return value.inner
    raise DomainRefusal("fill-null-domain")


def filled(value, fill, *, inner: str):
    chosen = fill if value is None else value
    if chosen is None or inner not in {"i64", "f64"}:
        return chosen
    return float(chosen) if inner == "f64" else int(chosen)


_CONVERSION_RESULT = {"to_integer": "i64", "to_float": "f64", "to_text": "str"}
_CONVERSION_ON_AN_ARRAY = {
    "to_integer": "checked-integer-conversion",
    "to_float": "float-conversion-type",
    "to_text": "text-conversion-type",
}


def elementwise_call(name: str, operands: list[Column], attrs: dict) -> Column:
    # 11.1.8 and 11.1.12: the thirteen calls that read a number read a flag as
    # the 0.0 or 1.0 it indicates (11.1.25), and answer a double.
    if name in READS_A_NUMBER and operands[0].inner == "bool":
        operands = [as_indicator(operands[0]), *operands[1:]]
    inner = source = operands[0].inner
    # 11.1.12: the six calls held to a tolerance answer a double over a whole
    # number, as the producer records them; only the four whole-number calls
    # above keep an i64's type.
    if name in UNARY_MATH and name not in WHOLE_MATH and inner == "i64":
        inner = "f64"
    # 11.1.12: the leading figures kept, at least one of them.
    if name == "round_sig_figs" and attrs["digits"] < 1:
        raise DomainRefusal("significant-figures-digits")
    if name.startswith("is_"):
        inner = "bool"
    # 11.1.12: Φ answers a double whatever numeric type the value arrives in.
    if name == "norm_cdf":
        inner = "f64"
    if name in _CONVERSION_RESULT:
        inner = _CONVERSION_RESULT[name]
    # A fixed-width array goes through to_list (11.1.40) first: none of the
    # three conversions above has a form for the shape itself.
    if name in _CONVERSION_RESULT and operands[0].arrayed:
        raise DomainRefusal(_CONVERSION_ON_AN_ARRAY[name])
    if name == "to_integer" and (
        operands[0].listed and any(row is None for row in operands[0].values)
    ):
        raise DomainRefusal("checked-integer-conversion")
    if name in {"str.to_date", "cut"}:
        inner = "date" if name == "str.to_date" else "str"
    # 11.1.3: clip keeps the value's own type, and a whole number has no
    # answer in it under a decimal bound -- the producer refuses the line.
    if name == "clip" and inner == "i64" and "f64" in {o.inner for o in operands}:
        raise DomainRefusal("clip-bound-type")
    if name == "fill_null":
        inner = filled_type(*operands)
    if name in {"is_in", "replace", "cut"}:
        operands = [
            operands[0],
            *(
                Column("set", operand.values) if operand.listed else operand
                for operand in operands[1:]
            ),
        ]

    null_handlers = {
        "is_null": lambda value: value is None,
        "is_not_null": lambda value: value is not None,
        "fill_null": partial(filled, inner=inner),
        "to_integer": checked_integer,
        "to_float": widened_double,
        "to_text": written_text,
    }
    if name in null_handlers:
        return map_values(null_handlers[name], operands, inner)
    null_result = False if name == "is_in" and attrs["nulls_equal"] else None
    cell = partial(
        nullable_cell,
        function=element_function(name, attrs, source),
        null_result=null_result,
        double=inner == "f64",
    )
    return map_values(cell, operands, inner)


def nan_filled(name: str, operands: list[Column], attrs: dict) -> Column:
    """11.1.13: the fill where the value is NaN; a null and every number kept.

    A null is the other absence and is not a NaN, so it stays null. The value
    and the fill are numbers: a whole number holds no NaN and stands, in the
    type the two share, and past the numbers the clause states no answer, so
    this reader refuses. The answer keeps the value's shape, so a per-period
    fill for a per-policy value is outside the entry too.
    """
    value, fill = operands
    if value.inner not in {"i64", "f64"} or fill.inner not in {"i64", "f64"}:
        raise DomainRefusal("fill-nan-domain")
    if fill.listed and not value.listed:
        raise DomainRefusal("fill-nan-shape")
    inner = "f64" if "f64" in {value.inner, fill.inner} else "i64"
    # The whole number meets the double inside the range a double names
    # every whole number in; past it the double would lose its digits.
    if inner == "f64":
        check_exact_conversion(value, fill)

    def cell(present, stated):
        chosen = (
            stated if isinstance(present, float) and math.isnan(present) else present
        )
        return float(chosen) if inner == "f64" and chosen is not None else chosen

    return map_values(cell, operands, inner)


def list_get(row: list | None, position: int | None):
    if not row or position is None or not -len(row) <= position < len(row):
        raise DomainRefusal("list-get-bounds")
    return row[position]


def reduce_row(row: list | None, *, name: str, whole: bool) -> float | int | None:
    # 11.1.14: a total is one number and has no room to say a period went
    # missing under it, so a null period anywhere makes it null -- a run of
    # nothing but nulls with them, where sum used to give the empty run's
    # nought. The empty run has lost no period and keeps that nought.
    if row is None or any(value is None for value in row):
        return None
    if name == "sum":
        # A run of whole numbers totals exactly, and a total an i64 does not
        # hold is refused rather than wrapped or carried into a double.
        # A run of doubles starts from -0.0, IEEE's additive identity, so the
        # sum of one period is that period, a negative nought included; the
        # empty run's is +0.0 (11.1.14).
        if whole:
            return held_whole(sum(row, 0))
        return in_period_order(row) if row else 0.0
    if not row:
        return None
    # A mean is a double, its whole-number total divided once: Python's
    # division of two whole numbers is correctly rounded.
    # A run of doubles is totalled in period order (11.1.14): Python's own sum
    # is compensated from 3.12, which is an exactly rounded total no engine
    # takes, and a floor of it can land a whole step away.
    if name == "mean":
        return (sum(row) if whole else in_period_order(row)) / len(row)
    # 11.1.16-17: a NaN period has no place in the run's order, so a run
    # holding one has no least and no greatest, wherever the NaN stands.
    if any(isinstance(value, float) and math.isnan(value) for value in row):
        return math.nan
    return {"min": min, "max": max}[name](row)


def in_period_order(row: list) -> float:
    """Return a run of doubles' total, folded left to right in binary64 (11.1.14).

    From -0.0, IEEE's additive identity, so one period of -0.0 totals -0.0.
    """
    total = -0.0
    for value in row:
        total += value
    return total


def scan_row(row: list | None, *, name: str, reverse: bool, whole: bool) -> list | None:
    if row is None:
        return None
    # 11.1.9: a running total that has passed a period carrying no value is
    # unknown from there on, in the fold's own direction. remaining_sum
    # (11.1.20) folds from the last period and follows the same rule, so its
    # lost periods run toward period zero rather than away from it.
    # A run of whole numbers, or of flags as their 0 or 1, folds exactly from
    # a whole-number seed, and every period's answer is one an i64 holds.
    if name == "cum_prod":
        current, combine = (1 if whole else 1.0), mul
    else:
        current, combine = (0 if whole else -0.0), add
    output, lost = [], False
    for value in reversed(row) if reverse else row:
        if value is None:
            lost = True
        elif not lost:
            current = combine(current, value)
            if whole:
                held_whole(current)
        output.append(None if lost else current)
    return output[::-1] if reverse else output


def fold_call(name: str, operands: list[Column], attrs: dict) -> Column:
    source = operands[0]
    if name == "list.get":
        if operands[1].dtype != "i64":
            raise DomainRefusal("list-get-position-type")
        return Column(
            source.inner,
            [
                list_get(row, index)
                for row, index in zip(source.values, operands[1].values)
            ],
        )
    # 11.1.9 and 11.1.14 to 11.1.17 fold one policy's own periods; over one
    # value per policy there are none to fold.
    if not source.listed and name != "projection.remaining_sum":
        raise DomainRefusal("fold-over-a-value-per-policy")
    # 11.1.9, 11.1.14 and 11.1.15: whole numbers and flags total as whole
    # numbers, as the producer records them; a mean is a double.
    whole = source.inner in {"i64", "bool"}
    if name in {"sum", "mean", "min", "max"}:
        inner = {"sum": "i64" if whole else source.inner, "mean": "f64"}
        return Column(
            inner.get(name, source.inner),
            [reduce_row(row, name=name, whole=whole) for row in source.values],
        )
    reverse = attrs.get("reverse", False) or name == "projection.remaining_sum"
    return Column(
        "list[i64]" if whole else source.dtype,
        [
            scan_row(row, name=name, reverse=reverse, whole=whole)
            for row in source.values
        ],
    )


def accumulate_row(
    initial: float | None, multipliers: list, addends: list, *, reverse: bool = False
) -> list:
    # 11.1.20: this fold runs from the opening state -- forward from period
    # zero, or under reverse back from the policy's own last period -- so a
    # period with no multiplier or no addend costs it a term and it answers
    # null there and at every position the run reaches after it. A null
    # initial is the same loss at the opening boundary and nulls the whole run.
    if multipliers is None or addends is None or len(multipliers) != len(addends):
        raise DomainRefusal("accumulation-period-domain")
    if initial is None:
        return [None] * len(multipliers)
    steps = list(zip(multipliers, addends))
    state, result, lost = initial, [], False
    for multiplier, addend in reversed(steps) if reverse else steps:
        if multiplier is None or addend is None:
            lost = True
        elif not lost:
            state = multiplier * state + addend
        result.append(None if lost else state)
    return result[::-1] if reverse else result


def reversed_rows(name: str, operands: list[Column], attrs: dict) -> Column:
    """11.1.41: each policy's own list end for end, a null moving with it."""
    source = operands[0]
    if not source.listed:
        raise DomainRefusal("list-reverse-shape")
    return Column(
        source.dtype,
        [None if row is None else row[::-1] for row in source.values],
    )


def prospective_row(row: list | None, rates: list, *, timing: str) -> list | None:
    # 11.1.21: this fold also starts at the last period, so a cashflow period
    # carrying no value makes that position and every earlier one null. The
    # rule is about the cashflows' own periods; a null rate stays outside the
    # entry and is not reached by these vectors.
    if row is None:
        return None
    if len(row) != len(rates):
        raise DomainRefusal("period-count-mismatch")
    value, sequence, lost = 0.0, [], False
    for cashflow, rate in reversed(list(zip(row, rates))):
        if cashflow is None:
            lost = True
        elif not lost:
            value = (
                (cashflow + value) / (1 + rate)
                if timing == "end_of_period"
                else cashflow + value / (1 + rate)
            )
        sequence.append(None if lost else value)
    return sequence[::-1]


def survival_row(row: list, *, start_at: float | None) -> list:
    # 11.1.19: a period carrying no decrement loses the running survival a
    # factor, so it and every later period answer null. The mask goes on
    # before start_at shifts the sequence: the opening value is the boundary
    # the projection starts from, never the factor that went missing.
    value, sequence, lost = 1.0, [], False
    for rate in row:
        if rate is None:
            lost = True
        elif not lost:
            value *= 1 - rate
        sequence.append(None if lost else value)
    if start_at is None or not sequence:
        return sequence
    return [float(start_at), *sequence[:-1]]


def projection_values(name: str, operands: list[Column], attrs: dict) -> Column:
    if name == "projection.accumulate":
        return accumulation_values(operands, reverse=attrs.get("reverse", False))
    if name == "projection.cumulative_survival":
        return Column(
            "list[f64]",
            [
                survival_row(row, start_at=attrs["start_at"])
                for row in operands[0].values
            ],
        )
    if name == "projection.prospective_value":
        return prospective_values(operands, attrs)
    offset = {"projection.previous_period": -1, "projection.next_period": 1}.get(
        name, attrs.get("relative_period", 0)
    )
    return Column(
        "list[f64]",
        [
            [
                row[t + offset] if 0 <= t + offset < len(row) else fill
                for t in range(len(row))
            ]
            for row, fill in zip(operands[0].values, operands[1].values)
        ],
    )


def accumulation_values(operands: list[Column], *, reverse: bool = False) -> Column:
    steps = operands[1:]
    # 11.1.20: the initial value is a literal or a scalar column.
    if operands[0].listed:
        raise DomainRefusal("accumulate-initial-per-period")
    axes = [column for column in steps if column.listed]
    if not axes:
        raise DomainRefusal("accumulation-period-domain")
    result = []
    for row, initial in enumerate(operands[0].values):
        count = len(axes[0].values[row])
        values = [
            column.values[row] if column.listed else [column.values[row]] * count
            for column in steps
        ]
        result.append(accumulate_row(initial, *values, reverse=reverse))
    return Column("list[f64]", result)


def prospective_values(operands: list[Column], attrs: dict) -> Column:
    if attrs["discount_kind"] != "rate":
        raise DomainRefusal("prospective-factor-capability")
    if attrs["timing"] not in {"end_of_period", "beginning_of_period"}:
        raise DomainRefusal("prospective-timing-capability")
    result = []
    for policy, row in enumerate(operands[0].values):
        rates = operands[1].values[policy]
        if not operands[1].listed:
            rates = [rates] * (0 if row is None else len(row))
        result.append(prospective_row(row, rates, timing=attrs["timing"]))
    return Column("list[f64]", result)


def unpinned_list(name: str, operands: list[Column], attrs: dict) -> Column:
    """11.1.40: an array's own elements, in order, with the width given up.

    A list refuses rather than passing through, and so does a scalar: the
    clause is about one conversion, and a node that sometimes did nothing
    would mean two things to a reader of the trace.
    """
    source = operands[0]
    if not source.arrayed:
        raise DomainRefusal("list-conversion-shape")
    return Column(
        f"list[{source.inner}]",
        [None if row is None else list(row) for row in source.values],
    )
