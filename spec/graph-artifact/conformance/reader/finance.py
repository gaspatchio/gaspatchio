# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent finance rules for the published synthetic vectors."""

from __future__ import annotations

import hashlib
import json
import math
from functools import partial

from .base import check_exact_conversion, divide
from .shared import Column, DomainRefusal, as_double, map_values


def forward_factors(rates: Column) -> Column:
    if rates.dtype != "list[f64]":
        raise DomainRefusal("forward-requires-rate-list")
    result = []
    for row in rates.values:
        if row is None or any(
            r is None or not math.isfinite(r) or r <= -1 for r in row
        ):
            raise DomainRefusal("forward-rate-domain")
        factor, sequence = 1.0, []
        for rate in row:
            sequence.append(factor)
            factor /= 1 + rate
        result.append(sequence)
    return Column("list[f64]", result)


def monthly_rate(rate: float, *, attrs: dict) -> float:
    if attrs["method"] == "simple":
        return rate / 12
    if rate < -1:
        raise DomainRefusal("monthly-rate-domain")
    return (1 + rate) ** (1 / 12) - 1


def compound_factor(period: float, *, attrs: dict) -> float:
    return (1 + attrs["rate"]) ** (period / attrs["periods_per_year"])


def spot_factor(rate: float, period: float, *, attrs: dict) -> float:
    if rate <= -1:
        raise DomainRefusal("spot-rate-domain")
    return (1 + rate) ** -period


def discounted_value(
    value: float, rate: float, period: float, *, contribution: bool
) -> float | None:
    if rate < -1 or rate == -1 and (period < 0 or int(period) != period):
        raise DomainRefusal("discount-rate-domain")
    if contribution and period < 1:
        return None
    factor = (1 + rate) ** period
    if not contribution and factor == 0:
        return None
    return divide(value, factor)


def finance_configuration(name: str, operands: list[Column], attrs: dict) -> None:
    if name == "finance.to_monthly" and attrs["method"] not in {"simple", "compound"}:
        raise DomainRefusal("monthly-method-capability")
    if name == "finance.compound":
        periods = attrs["periods_per_year"]
        if (
            attrs["rate"] <= -1
            or not math.isfinite(attrs["rate"])
            or type(periods) is not int
            or periods <= 0
        ):
            raise DomainRefusal("compound-configuration")
    if name == "finance.discount_factor":
        if attrs["method"] not in {"spot", "forward"}:
            raise DomainRefusal("discount-factor-method-capability")
        if not any(column.listed for column in operands):
            raise DomainRefusal("discount-factor-list-required")
    if name in {"finance.discount", "finance.present_value"} and any(
        column.listed for column in operands
    ):
        raise DomainRefusal("discount-scalar-domain")


def finance(name: str, operands: list[Column], attrs: dict) -> Column:
    """Select a stated formula only after checking its configuration."""
    finance_configuration(name, operands, attrs)
    if name == "finance.discount_factor" and attrs["method"] == "forward":
        return forward_factors(operands[0])
    functions = {
        "finance.to_monthly": partial(monthly_rate, attrs=attrs),
        "finance.compound": partial(compound_factor, attrs=attrs),
        "finance.discount_factor": partial(spot_factor, attrs=attrs),
        "finance.discount": partial(discounted_value, contribution=False),
        "finance.present_value": partial(discounted_value, contribution=True),
    }

    def cell(*values: float | None) -> float | None:
        if any(value is None for value in values):
            if name == "finance.discount_factor":
                raise DomainRefusal("spot-null-domain")
            return None
        if any(not math.isfinite(value) for value in values):
            raise DomainRefusal("finance-nonfinite-domain")
        # A whole-number rate and period meet in whole numbers, and (1 + 0)
        # to the minus 0 is the whole number 1; the answer is the double.
        return as_double(functions[name](*values))

    return map_values(cell, operands, "f64")


def projection_simple(name: str, operands: list[Column], attrs: dict) -> Column:
    source = operands[0]
    if name == "projection.broadcast_to_periods":
        if len(operands) != 2 or source.listed or not operands[1].listed:
            raise DomainRefusal("explicit-broadcast-axis-required")
        return Column(
            f"list[{source.inner}]",
            [
                None if axis is None else [value] * len(axis)
                for value, axis in zip(source.values, operands[1].values)
            ],
        )
    # 11.1.32: an override replaces a cell of one policy's own periods.
    if not source.listed:
        raise DomainRefusal("period-override-over-a-value-per-policy")
    # 11.1.32 states a list[f64] and a double; the producer records a whole
    # number put into a whole-number run as list[i64], and a double put into
    # one, or anything put into a list[f64], as list[f64].
    double = source.inner == "f64" or isinstance(attrs["value"], float)
    if double and source.inner == "i64":
        check_exact_conversion(source)
    result = []
    for row in source.values:
        if row is None:
            result.append(None)
            continue
        values = list(row)
        position = attrs["period"]
        if -len(values) <= position < len(values):
            values[position] = attrs["value"]
        result.append([as_double(value) for value in values] if double else values)
    return Column("list[f64]" if double else source.dtype, result)


def recipe_for(kind: str, sha: str, assumptions: list[dict]) -> dict:
    matches = [
        item
        for item in assumptions
        if item["kind"] == kind and item["source_sha"] == sha
    ]
    if len(matches) != 1:
        raise DomainRefusal(f"{kind}-payload-missing-or-ambiguous")
    payload = matches[0]["payload"]
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != sha:
        raise DomainRefusal(f"{kind}-payload-identity")
    return payload


def curve_value(
    name: str, operand: Column, attrs: dict, assumptions: list[dict]
) -> Column:
    payload = recipe_for("curve", attrs["curve"], assumptions)
    if (
        payload["interpolation"] != "linear"
        or payload.get("extrapolation", "flat") != "flat"
    ):
        raise DomainRefusal("curve-interpolation-capability")
    xs, ys = payload["tenors"], payload["rates"]

    def cell(time):
        if time is None:
            return None
        rate = ys[0] if time <= xs[0] else ys[-1]
        for index in range(1, len(xs)):
            if xs[index - 1] <= time <= xs[index]:
                weight = (time - xs[index - 1]) / (xs[index] - xs[index - 1])
                rate = ys[index - 1] + weight * (ys[index] - ys[index - 1])
                break
        return rate if name == "curve.spot_rate" else (1 + rate) ** -time

    return map_values(cell, [operand], "f64")
