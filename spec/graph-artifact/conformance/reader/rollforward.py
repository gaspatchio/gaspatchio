# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Independent BOP/EOP execution over the stated compilation subset."""

from __future__ import annotations

import calendar
import math
from datetime import date

from .finance import recipe_for
from .shared import Column, DomainRefusal

_FIELDS = {
    "points",
    "states",
    "increments",
    "track_increments",
    "lapse_when_all_non_positive",
    "contract_boundary",
    "engine_binding",
    "batch_axes",
    "schedule",
}

# What one operand of an admitted operation is, and the column types each
# admits. A rate is a number; a gate is a test; neither takes the other's.
AMOUNT, LIFT, GATE, BALANCE = "amount", "lift", "gate", "balance"
_NUMERIC = ("f64", "list[f64]")
_PREDICATE = ("bool", "list[bool]")


def compilation_for(tree: dict, compilations: dict) -> dict:
    body = compilations.get(tree["attrs"]["fingerprint"])
    if body is None:
        raise DomainRefusal("compilation-missing")
    required = {
        "points": ["bop", "eop"],
        "engine_binding": "portable",
        "batch_axes": ["policy"],
        "contract_boundary": None,
        "lapse_when_all_non_positive": [],
    }
    if set(body) != _FIELDS or any(
        body[key] != value for key, value in required.items()
    ):
        raise DomainRefusal("rollforward-capability")
    tracking = tree["name"] == "rollforward.increment"
    if body["track_increments"] is not tracking:
        raise DomainRefusal("rollforward-tracking-capability")
    return body


def machine_periods(body: dict, assumptions: list[dict]) -> int:
    recipe = recipe_for("schedule", body["schedule"], assumptions)
    if recipe["kind"] == "fixed_step":
        # 16.1's second form: a fixed step supplies T and nothing else.
        periods = recipe["n_periods"]
        if (
            set(recipe)
            not in (
                {"kind", "n_periods", "step_years"},
                {"kind", "n_periods", "steps_per_year"},
            )
            or type(periods) is not int
            or periods < 0
        ):
            raise DomainRefusal("rollforward-schedule-capability")
        return periods
    required = {
        "kind": "from_calendar_grid",
        "frequency": "1M",
        "calendar": "NullCalendar",
        "convention": "Unadjusted",
        "day_count": "OneTwelfth",
        "anchor": "month_end",
    }
    if any(recipe.get(key) != value for key, value in required.items()):
        raise DomainRefusal("rollforward-schedule-capability")
    start = date.fromisoformat(recipe["start_date"])
    periods = recipe["n_periods"]
    if (
        start.day != calendar.monthrange(start.year, start.month)[1]
        or type(periods) is not int
        or periods < 0
    ):
        raise DomainRefusal("rollforward-schedule-capability")
    return periods


def state_reference(name: str, states: set[str]) -> tuple[str, str]:
    parts = name.split("@")
    if len(parts) != 2 or parts[0] not in states or parts[1] not in {"bop", "eop"}:
        raise DomainRefusal("rollforward-state-reference")
    return parts[0], parts[1]


def column_binding(
    operand: dict, inputs: dict[str, Column], periods: int, dtypes: tuple[str, ...]
) -> None:
    if operand.get("op") != "col" or operand.get("name") not in inputs:
        raise DomainRefusal("rollforward-column-binding")
    column = inputs[operand["name"]]
    if column.dtype not in dtypes:
        raise DomainRefusal("rollforward-column-type")
    for row in column.values:
        if column.listed and (row is None or len(row) != periods):
            raise DomainRefusal("rollforward-period-count")
        cells = row if column.listed else [row]
        if any(value is None or not math.isfinite(value) for value in cells):
            raise DomainRefusal("rollforward-nonfinite-input")


def floor_bound(settings: dict) -> float | None:
    # A floor's lower bound is configuration and not an amount, so it travels
    # in the settings rather than as an operand. None is "no such bound".
    value = settings.get("value")
    if set(settings) != {"value"} or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def operation_contract(operation: dict, states: set[str]) -> tuple[str, ...]:
    # Returns what each operand is, positionally: an amount the operation
    # applies, the state a ratchet lifts to, the test that gates it, or the
    # running balance the operation's own shape consumes.
    target, point = state_reference(operation["target"], states)
    if point != "eop":
        raise DomainRefusal("rollforward-target-point")
    name, operands, settings = (
        operation["operation"],
        operation["operands"],
        operation["settings"],
    )
    balance = {"op": "state", "name": f"{target}@eop"}
    if name in {"Add", "Subtract"} and len(operands) == 1 and settings == {}:
        return (AMOUNT,)
    if (
        name in {"Charge", "Grow"}
        and len(operands) == 2
        and settings == {"round_charge": None}
        and operands[1] == balance
    ):
        return (AMOUNT, BALANCE)
    if name == "Floor" and operands == [balance] and floor_bound(settings) is not None:
        return (BALANCE,)
    if (
        name == "Ratchet"
        and len(operands) == 3
        and settings == {}
        and operands[0].get("op") == "state"
        and operands[1].get("op") == "col"
        and operands[2] == balance
    ):
        return (LIFT, GATE, BALANCE)
    raise DomainRefusal("rollforward-operation-capability")


def increment_keys(body: dict) -> list[str]:
    # The kernel's name for each movement: the author's label, or the reserved
    # {kind}@{ordinal} where the step carries none, which is the only name a
    # chain holding two structural steps can tell them apart by.
    return [
        operation["label"]
        if operation["label"] is not None
        else f"{operation['operation'].lower()}@{ordinal}"
        for ordinal, operation in enumerate(body["increments"], 1)
    ]


def validate_machine(body: dict, inputs: dict[str, Column], periods: int) -> set[str]:
    states = [state["name"] for state in body["states"]]
    if (
        not states
        or any(not name for name in states)
        or len(states) != len(set(states))
    ):
        raise DomainRefusal("rollforward-duplicate-or-empty-state")
    for state in body["states"]:
        column_binding(state["init"], inputs, periods, ("f64",))
    keys = increment_keys(body)
    if len(keys) != len(set(keys)):
        raise DomainRefusal("rollforward-ambiguous-label")
    for operation in body["increments"]:
        roles = operation_contract(operation, set(states))
        for role, operand in zip(roles, operation["operands"]):
            if role == GATE:
                column_binding(operand, inputs, periods, _PREDICATE)
            elif operand["op"] == "state":
                state_reference(operand["name"], set(states))
            else:
                column_binding(operand, inputs, periods, _NUMERIC)
    return set(states)


def extraction_contract(tree: dict, body: dict, states: set[str]) -> None:
    attrs = tree["attrs"]
    if tree["name"] == "rollforward.state":
        if attrs["state"] not in states or attrs["point"] != "eop":
            raise DomainRefusal("rollforward-extraction-missing")
    elif increment_keys(body).count(attrs["label"]) != 1:
        raise DomainRefusal("rollforward-extraction-missing")


def operand_value(
    operand: dict,
    inputs: dict[str, Column],
    states: dict,
    opening: dict,
    row: int,
    period: int,
) -> float:
    if operand["op"] == "state":
        state, point = operand["name"].split("@")
        return (opening if point == "bop" else states)[state]
    column = inputs[operand["name"]]
    return column.values[row][period] if column.listed else column.values[row]


def update_state(operation: dict, before: float, operands: list) -> float:
    name = operation["operation"]
    if name == "Add":
        return before + operands[0]
    if name == "Subtract":
        return before - operands[0]
    if name == "Charge":
        return before * (1 - operands[0])
    if name == "Grow":
        return before * (1 + operands[0])
    if name == "Floor":
        return max(before, float(operation["settings"]["value"]))
    return max(before, operands[0]) if operands[1] else before


def run_period(
    body: dict, inputs: dict[str, Column], states: dict, row: int, period: int
) -> dict:
    opening, deltas = dict(states), {}
    for key, operation in zip(increment_keys(body), body["increments"]):
        target = operation["target"].split("@")[0]
        values = [
            operand_value(operand, inputs, states, opening, row, period)
            for operand in operation["operands"]
        ]
        before = states[target]
        states[target] = update_state(operation, before, values)
        if not math.isfinite(states[target]):
            raise DomainRefusal("rollforward-nonfinite-state")
        deltas[key] = states[target] - before
    return deltas


def rollforward_value(
    tree: dict, inputs: dict[str, Column], assumptions: list[dict], compilations: dict
) -> Column:
    body = compilation_for(tree, compilations)
    periods = machine_periods(body, assumptions)
    declared = validate_machine(body, inputs, periods)
    extraction_contract(tree, body, declared)
    output = []
    for row in range(len(next(iter(inputs.values())).values)):
        states = {
            state["name"]: inputs[state["init"]["name"]].values[row]
            for state in body["states"]
        }
        result = []
        for period in range(periods):
            deltas = run_period(body, inputs, states, row, period)
            selected = (
                states[tree["attrs"]["state"]]
                if tree["name"] == "rollforward.state"
                else deltas[tree["attrs"]["label"]]
            )
            result.append(selected)
        output.append(result)
    return Column("list[f64]", output)
