# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Run the independent synthetic-vector conformance reader (standard library only)."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

# Script mode under -I omits its directory from sys.path. Add only this
# reader's own directory; no producer package is imported or discovered.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reader.base import (
    COMPARISONS,
    arithmetic,
    check_exact_conversion,
    comparison,
    logical,
    stored_indicator,
    unknown,
)
from reader.calendars import dates, excel_numeric, schedule_value
from reader.elementary import (
    UNARY_MATH,
    elementwise_call,
    fold_call,
    nan_filled,
    projection_values,
    reversed_rows,
    unpinned_list,
)
from reader.finance import curve_value, finance, projection_simple
from reader.rollforward import rollforward_value
from reader.selection import kept_rows
from reader.shared import (
    Column,
    DomainRefusal,
    as_double,
    contradicts,
    decode,
    differences,
    map_values,
)
from reader.tables import lookup_value, recording_value

# Dispatch is closed and grouped by the value clauses it implements.
_CALL_GROUPS = [
    (
        finance,
        "finance.to_monthly finance.compound finance.discount finance.present_value finance.discount_factor",
    ),
    (projection_simple, "projection.with_period projection.broadcast_to_periods"),
    (excel_numeric, "excel.irr excel.pv excel.round"),
    (
        dates,
        "date.to_period date.offset_by date.months_between date.date_ranges excel.days excel.edate excel.eomonth excel.from_excel_serial excel.yearfrac",
    ),
    (
        elementwise_call,
        "round round_sig_figs fill_null is_null is_not_null is_nan is_not_nan is_finite is_infinite to_integer to_float to_text clip cut is_in replace str.to_date",
    ),
    (nan_filled, "fill_nan"),
    (unpinned_list, "to_list"),
    (reversed_rows, "list.reverse"),
    (fold_call, "sum mean min max list.get cum_sum cum_prod projection.remaining_sum"),
    (
        projection_values,
        "projection.accumulate projection.prospective_value projection.cumulative_survival projection.previous_period projection.next_period projection.at_period",
    ),
]
_CALLS = {name: function for function, names in _CALL_GROUPS for name in names.split()}
_CALLS.update({name: elementwise_call for name in UNARY_MATH})
_SCHEDULE_CALLS = {
    "schedule.per_policy_period_dates",
    "schedule.per_policy_period_count",
    "schedule.period_dates",
    "schedule.year_fractions",
    "schedule.anniversary_mask",
    "schedule.is_in_force",
    "schedule.contract_boundary",
    "projection_frame.period_dates",
    "projection_frame.year_fractions",
    "projection_frame.anniversary_mask",
    "projection_frame.t_years",
}


_READS_A_DURATION_AS_A_NUMBER = frozenset(
    {
        "sign",
        "round",
        "floor",
        "ceil",
        "sqrt",
        "cbrt",
        "exp",
        "log",
        "log10",
        "log1p",
        "round_sig_figs",
        "norm_cdf",
        "cum_prod",
        "projection.cumulative_survival",
    }
)


def literal(tree: dict, policies: int) -> Column:
    if "date" in tree:
        return Column("date", [tree["date"]] * policies)
    if "values" in tree:
        values = tree["values"]
        inner = "i64"
        if values and isinstance(values[0], str):
            inner = "str"
        elif any(isinstance(value, float) for value in values):
            inner = "f64"
            values = [as_double(value) for value in values]
        return Column(f"list[{inner}]", [values] * policies)
    value = tree["value"]
    inner = {bool: "bool", int: "i64", float: "f64", str: "str", type(None): "f64"}[
        type(value)
    ]
    return Column(inner, [value] * policies)


def select_value(flag, yes, no, *, stored: bool, listed: bool, inner: str):
    if stored and (flag is None or not math.isfinite(flag) or flag not in (0.0, 1.0)):
        raise DomainRefusal("stored-numeric-predicate")
    # 11.1.28: a condition with no truth value (a NaN reached its comparison)
    # selects nothing: NaN where the answer is a double, null where not.
    if isinstance(flag, float) and math.isnan(flag):
        return math.nan if inner == "f64" else None
    if flag is None and listed:
        return None
    result = yes if flag else no
    return float(result) if inner == "f64" and result is not None else result


def _exponent_past_the_integer_rule(tree: dict) -> bool:
    """Return whether a power's exponent is an integer literal outside [0, 2^32-1].

    11.1.25: "Where the exponent is written as an integer literal outside that
    range ... the answer is f64": the record holds the exponent, so the type is
    known where the line is written.
    """
    if tree["kind"] != "pow" or tree["right"]["op"] != "lit":
        return False
    value = tree["right"]["value"]
    return type(value) is int and not 0 <= value <= 2**32 - 1


@dataclass(frozen=True)
class Reader:
    inputs: dict[str, Column]
    assumptions: list[dict]
    compilations: dict

    def answer(self, tree: dict) -> Column:
        """Evaluate a node's tree as the column it publishes.

        A test combined with ``&``, ``|`` or ``~`` per policy is a ``bool``,
        and a ``bool`` holds no NaN: where it has no truth value (11.1.26)
        it is published as a null, as the reference producer stores it.
        """
        result = self.evaluate(tree)
        if result.dtype != "bool":
            return result
        return Column(
            result.dtype,
            [None if unknown(value) else value for value in result.values],
        )

    def evaluate(self, tree: dict, *, indicator: bool = True) -> Column:
        kind = tree["op"]
        if kind == "col":
            return self.inputs[tree["name"]]
        if kind == "lit":
            return literal(tree, len(next(iter(self.inputs.values())).values))
        if kind == "binop":
            return self.binary(tree, indicator=indicator)
        if kind == "call":
            return self.call(tree)
        if kind == "when_then":
            return self.conditional(tree)
        raise DomainRefusal(f"unsupported-operation:{kind}")

    def binary(self, tree: dict, *, indicator: bool) -> Column:
        name = tree["kind"]
        if name in {"and", "or"}:
            left = self.logical_operand(tree["left"])
            return logical(name, left, self.logical_operand(tree["right"]))
        if name in {"lt", "le", "gt", "ge"} and any(
            side["op"] == "call" and side["name"] == "cut"
            for side in (tree["left"], tree["right"])
        ):
            # 11.1.26: a band is an ordered category, whose order this
            # vocabulary does not hold; its text's order is not its own.
            raise DomainRefusal("ordered-category-comparison")
        left = self.evaluate(tree["left"])
        right = self.evaluate(tree["right"])
        if name in COMPARISONS:
            return comparison(name, left, right, indicator=indicator)
        return arithmetic(
            name, left, right, exponent_written=_exponent_past_the_integer_rule(tree)
        )

    def logical_operand(self, tree: dict) -> Column:
        """Evaluate one logical operand, reading a stored f64 column as a flag."""
        operand = self.evaluate(tree, indicator=False)
        if tree["op"] == "col" and operand.inner == "f64":
            return stored_indicator(operand)
        return operand

    def call(self, tree: dict) -> Column:
        name, attrs = tree["name"], tree["attrs"]
        if name == "rollforward.struct":
            raise DomainRefusal("raw-struct-outside-portable-output")
        if name == "not_":
            return logical("not_", self.logical_operand(tree["args"][0]))
        if name in {"rollforward.increment", "rollforward.state"}:
            return rollforward_value(
                tree, self.inputs, self.assumptions, self.compilations
            )
        operands = [self.evaluate(arg) for arg in tree["args"]]
        # 10: there is no duration type, so a call that reads a number has no
        # number of the vocabulary's own to read out of one, per policy or
        # per period, and is refused where it is written.
        if name in _READS_A_DURATION_AS_A_NUMBER and operands[0].inner == "duration":
            raise DomainRefusal("duration-read-as-a-number")
        if name in {"curve.spot_rate", "curve.discount_factor"}:
            return curve_value(name, operands[0], attrs, self.assumptions)
        if name in _SCHEDULE_CALLS:
            return schedule_value(name, self.inputs, attrs, self.assumptions)
        if name in {"lookup", "mortality.at"}:
            return lookup_value(name, operands, attrs, self.assumptions)
        if name not in _CALLS:
            raise DomainRefusal(f"unsupported-operation:{name}")
        return _CALLS[name](name, operands, attrs)

    def conditional(self, tree: dict) -> Column:
        condition = self.evaluate(tree["cond"], indicator=False)
        yes = self.evaluate(tree["then"])
        no = self.evaluate(tree["otherwise"])
        if condition.inner not in {"bool", "f64"}:
            raise DomainRefusal("predicate-type")
        listed = condition.listed or yes.listed or no.listed
        # 11.1.28: an i64 beside an f64 answers f64 within the exact
        # integer-conversion range, and so does a flag beside an i64 -- the
        # flag the 0.0/1.0 section 11.1.25 reads it as beside a number, under
        # the same range. A whole number past it is outside the entry, as it
        # is in arithmetic, and refused rather than rounded into the double.
        pair = {yes.inner, no.inner}
        a_flag_beside_a_whole_number = pair == {"bool", "i64"}
        if a_flag_beside_a_whole_number or pair == {"f64", "i64"}:
            check_exact_conversion(yes, no)
        inner = "f64" if "f64" in pair or a_flag_beside_a_whole_number else yes.inner
        stored = tree["cond"]["op"] == "col" and condition.inner == "f64"
        choose = partial(select_value, stored=stored, listed=listed, inner=inner)
        return map_values(choose, [condition, yes, no], inner)


def verify(case: dict) -> list[str]:
    inputs = {
        name: Column(item["dtype"], decode(item["values"]))
        for name, item in case["inputs"].items()
    }

    def evaluate(tree: dict, columns: dict[str, Column]) -> Column:
        reader = Reader(
            columns, case.get("assumptions", []), case.get("compilations", {})
        )
        return reader.evaluate(tree, indicator=False)

    try:
        # A door that refuses where it is written carries its setup too, and
        # is read through the door rather than as an operation of its own.
        if case["case_kind"] == "recording-door-value" or (
            case.get("producer_setup", {}).get("kind") == "join"
        ):
            result = recording_value(case, inputs)
        elif case["case_kind"] == "selection-value":
            # The steps read their predicates as truth values; the column the
            # case publishes is answered over the kept rows as any value is.
            result = Reader(
                kept_rows(case, inputs, evaluate),
                case.get("assumptions", []),
                case.get("compilations", {}),
            ).answer(case["expr"])
        else:
            result = Reader(
                inputs, case.get("assumptions", []), case.get("compilations", {})
            ).answer(case["expr"])
    except DomainRefusal as error:
        return (
            []
            if case.get("refusal") == str(error)
            else [f"unexpected refusal: {error}"]
        )
    if "refusal" in case:
        return ["expected domain refusal"]
    if result.dtype != case["expected"]["dtype"]:
        return [f"dtype: {result.dtype} != {case['expected']['dtype']}"]
    # The label is the type, so every value must be held as it: 2 and 2.0
    # compare equal below and would let a whole number pass as a double.
    if contradicts(result):
        return [f"values: held as another type than {result.dtype}"]
    return differences(
        result.values,
        decode(case["expected"]["values"]),
        case["comparison"]["atol"],
        case["comparison"]["rtol"],
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Pass one or more vector bundle paths.")
    failures = {}
    count = 0
    for filename in sys.argv[1:]:
        bundle = json.loads(Path(filename).read_text())
        for case in bundle["cases"]:
            findings = verify(case)
            count += 1
            if findings:
                failures[case["id"]] = findings
    print(json.dumps({"cases": count, "failures": failures}, indent=2, allow_nan=False))
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
