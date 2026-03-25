"""Inspection utilities for RollforwardBuilder.

Provides explain(), canonical(), and fingerprint() functions.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from gaspatchio_core.rollforward._step import _col_name

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._builder import RollforwardBuilder


def _formula(
    step_op: str, args: tuple[Any, ...], kwargs: dict[str, Any], av: str
) -> str:
    """Return a formula string for a single step.

    Parameters
    ----------
    step_op : str
        Operation name (e.g. "add", "grow", "floor").
    args : tuple
        Positional args stored on the StepDef.
    kwargs : dict
        Keyword args stored on the StepDef (excluding ``_target``).
    av : str
        The account-value variable name to use in the formula (e.g. ``"av"``).

    """
    if step_op == "add":
        col = _col_name(args[0])
        return f"{av}[t] = {av}[t] + {col}[t]"
    if step_op == "subtract":
        col = _col_name(args[0])
        return f"{av}[t] = {av}[t] - {col}[t]"
    if step_op == "charge":
        col = _col_name(args[0])
        return f"{av}[t] = {av}[t] * (1 - {col}[t])"
    if step_op == "grow":
        col = _col_name(args[0])
        return f"{av}[t] = {av}[t] * (1 + {col}[t])"
    if step_op == "grow_capped":
        col = _col_name(args[0])
        floor_val = kwargs.get("floor", 0)
        cap_val = kwargs.get("cap", 0)
        return f"{av}[t] = {av}[t] * (1 + clamp({col}[t], {floor_val}, {cap_val}))"
    if step_op == "deduct_nar":
        col = _col_name(args[0])
        db = _col_name(kwargs.get("death_benefit", "db"))
        return f"{av}[t] = {av}[t] - {col}[t] * max(0, {db}[t] - {av}[t])"
    if step_op == "floor":
        value = args[0]
        return f"{av}[t] = max({av}[t], {value})"
    if step_op == "cap":
        value = args[0]
        return f"{av}[t] = min({av}[t], {value})"
    if step_op == "ratchet_to":
        other = _col_name(args[0])
        return f"{av}[t] = max({av}[t], {other}[t])"
    if step_op == "pro_rata_with":
        amount = _col_name(args[1])
        ref = args[0]
        return f"{av}[t] = {av}[t] * (1 - {amount}[t] / {ref})"
    if step_op == "capture":
        name = kwargs.get("_target", av)
        return f"(capture {name})"
    if step_op == "lapse_if_zero":
        return f"if {av}[t] <= 0: zero remaining"
    if step_op == "add_if":
        cond = _col_name(args[0])
        col = _col_name(args[1])
        return f"if {cond}[t]: {av}[t] += {col}[t]"
    if step_op == "charge_if":
        cond = _col_name(args[0])
        col = _col_name(args[1])
        return f"if {cond}[t]: {av}[t] *= (1 - {col}[t])"
    return f"({step_op})"


def explain(builder: RollforwardBuilder) -> str:
    """Return a formatted table describing all steps in the builder.

    Parameters
    ----------
    builder : RollforwardBuilder
        The builder to introspect.

    Returns
    -------
    str
        A multi-line string with a header and one row per step.

    """
    steps = builder.steps
    n = len(steps)

    if builder.is_multi_state:
        assert builder._states is not None  # noqa: S101
        state_names = list(builder._states.keys())
        header_initial = f"states=[{', '.join(state_names)}]"
    else:
        header_initial = f"initial={builder._initial}"

    lines: list[str] = [
        f"Rollforward: {header_initial}, {n} step{'s' if n != 1 else ''}",
        "",
    ]

    # Column widths
    w_step = 4
    w_op = (
        max(len("Operation"), *(len(s.operation) for s in steps))
        if steps
        else len("Operation")
    )
    w_label = (
        max(len("Label"), *(len(s.label) for s in steps)) if steps else len("Label")
    )

    sep_step = "\u2500" * (w_step + 2)
    sep_op = "\u2500" * (w_op + 2)
    sep_label = "\u2500" * (w_label + 2)
    sep_formula = "\u2500" * 38

    header_row = (
        f"  {'Step':<{w_step}}  {'Operation':<{w_op}}    "
        f"{'Label':<{w_label}}  {'Formula'}"
    )
    sep_row = f"  {sep_step}  {sep_op}    {sep_label}  {sep_formula}"

    lines.append(header_row)
    lines.append(sep_row)

    for i, step in enumerate(steps, start=1):
        # Determine av variable name from _target kwarg or builder initial
        target = step.kwargs.get("_target")
        if target is not None:
            av = target
        elif not builder.is_multi_state:
            av = builder._initial or "av"
        else:
            assert builder._states is not None  # noqa: S101
            av = next(iter(builder._states))

        # Build kwargs without internal _target key for formula rendering
        display_kwargs = {k: v for k, v in step.kwargs.items() if k != "_target"}

        formula = _formula(step.operation, step.args, display_kwargs, av)

        lines.append(
            f"  {i:<{w_step + 2}} {step.operation:<{w_op + 4}} "
            f"{step.label:<{w_label}}  {formula}"
        )

    return "\n".join(lines)


def canonical(builder: RollforwardBuilder) -> dict[str, Any]:
    """Return a structural dict describing the builder.

    Excludes column names and labels.

    The canonical form captures only the operation types and structural
    parameters (e.g. floor/cap values). It is used as the basis for
    ``fingerprint()``.

    Parameters
    ----------
    builder : RollforwardBuilder
        The builder to introspect.

    Returns
    -------
    dict[str, Any]
        A JSON-serialisable dict with keys ``"num_states"``, ``"steps"``,
        and ``"track_increments"``.

    """
    num_states = len(builder._states) if builder._states is not None else 1

    canon_steps: list[dict[str, Any]] = []
    for step in builder.steps:
        entry: dict[str, Any] = {"operation": step.operation}
        if step.operation == "floor" or step.operation == "cap":
            entry["value"] = float(step.args[0])
        elif step.operation == "grow_capped":
            entry["floor"] = float(step.kwargs["floor"])
            entry["cap"] = float(step.kwargs["cap"])
        canon_steps.append(entry)

    return {
        "num_states": num_states,
        "steps": canon_steps,
        "track_increments": builder._track_increments,
    }


def fingerprint(builder: RollforwardBuilder) -> str:
    """Return a SHA-256 fingerprint of the builder's canonical form.

    Two builders with identical structure (same operations and structural
    parameters) but different column names or labels will produce the same
    fingerprint.

    Parameters
    ----------
    builder : RollforwardBuilder
        The builder to fingerprint.

    Returns
    -------
    str
        A string of the form ``"sha256:<64 hex chars>"``.

    """
    canon = canonical(builder)
    canonical_json = json.dumps(canon, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical_json.encode()).hexdigest()}"
