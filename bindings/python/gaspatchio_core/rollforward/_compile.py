"""Compile a RollforwardBuilder into (args, kwargs) for register_plugin_function."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._builder import RollforwardBuilder
    from gaspatchio_core.rollforward._step import StepDef


def _to_expr(ref: Any) -> pl.Expr:  # noqa: ANN401
    """Convert a column reference to a Polars expression.

    Parameters
    ----------
    ref
        A string column name, ColumnProxy, or ExpressionProxy.

    Returns
    -------
    pl.Expr
        The corresponding Polars expression.

    """
    if isinstance(ref, str):
        return pl.col(ref)
    if hasattr(ref, "_to_expr"):
        # ColumnProxy
        return ref._to_expr()  # noqa: SLF001
    if hasattr(ref, "_expr"):
        # ExpressionProxy
        return ref._expr  # noqa: SLF001
    msg = f"Cannot convert {type(ref).__name__} to pl.Expr"
    raise TypeError(msg)


def _ref_key(ref: Any) -> str:  # noqa: ANN401
    """Extract a deduplication key from a column reference.

    Parameters
    ----------
    ref
        A string, ColumnProxy, or ExpressionProxy.

    Returns
    -------
    str
        A key suitable for deduplication in the expr_index dict.

    """
    if isinstance(ref, str):
        return ref
    if hasattr(ref, "name"):
        return ref.name
    return str(ref)


def compile_rollforward(
    builder: RollforwardBuilder,
) -> tuple[list[pl.Expr], dict[str, Any]]:
    """Compile a RollforwardBuilder into plugin function arguments.

    Converts the builder's step sequence into a ``(args, kwargs)`` pair
    suitable for passing to ``rollforward_plugin``. Each unique column
    reference gets one index in the ``args`` list. States, captures, and
    step operations are resolved to integer indices.

    Parameters
    ----------
    builder
        A fully configured ``RollforwardBuilder`` instance.

    Returns
    -------
    tuple[list[pl.Expr], dict[str, Any]]
        A two-element tuple: the list of Polars expressions (args) and
        the serialized kwargs dict matching ``RollforwardKwargs``.

    """
    # ------------------------------------------------------------------
    # 1. Column deduplication registry
    # ------------------------------------------------------------------
    args: list[pl.Expr] = []
    expr_index: dict[str, int] = {}

    def _register(ref: Any) -> int:  # noqa: ANN401
        """Register a column reference, returning its index in args."""
        key = _ref_key(ref)
        if key in expr_index:
            return expr_index[key]
        idx = len(args)
        args.append(_to_expr(ref))
        expr_index[key] = idx
        return idx

    # ------------------------------------------------------------------
    # 2. State resolution
    # ------------------------------------------------------------------
    state_name_to_index: dict[str, int] = {}
    states_spec: list[dict[str, Any]] = []

    if builder.is_multi_state:
        assert builder._states is not None  # noqa: S101, SLF001
        for i, (state_name, state_ref) in enumerate(builder._states.items()):  # noqa: SLF001
            col_idx = _register(state_ref)
            state_name_to_index[state_name] = i
            states_spec.append(
                {
                    "name": state_name,
                    "initial_col_index": col_idx,
                }
            )
    else:
        assert builder._initial is not None  # noqa: S101, SLF001
        col_idx = _register(builder._initial)  # noqa: SLF001
        state_name_to_index["__default__"] = 0
        states_spec.append(
            {
                "name": "__default__",
                "initial_col_index": col_idx,
            }
        )

    # ------------------------------------------------------------------
    # 3. Capture resolution (pre-scan)
    # ------------------------------------------------------------------
    capture_name_to_index: dict[str, int] = {}
    capture_counter = 0
    for step in builder.steps:
        if step.operation == "capture":
            capture_name_to_index[step.label] = capture_counter
            capture_counter += 1

    # ------------------------------------------------------------------
    # 4. Step conversion
    # ------------------------------------------------------------------
    steps_spec: list[dict[str, Any]] = []

    for step in builder.steps:
        target_name = step.kwargs.get("_target", "__default__")
        target_index = state_name_to_index[target_name]

        spec = _compile_step(
            step,
            target_index=target_index,
            register=_register,
            state_name_to_index=state_name_to_index,
            capture_name_to_index=capture_name_to_index,
        )
        steps_spec.append(spec)

    # ------------------------------------------------------------------
    # 5. Lapse condition
    # ------------------------------------------------------------------
    lapse_condition: dict[str, Any] | None = None
    if builder._lapse_condition is not None:  # noqa: SLF001
        state_names = builder._lapse_condition["all_non_positive"]  # noqa: SLF001
        state_indices = [state_name_to_index[n] for n in state_names]
        lapse_condition = {"AllNonPositive": {"state_indices": state_indices}}

    # ------------------------------------------------------------------
    # 6. Assemble kwargs
    # ------------------------------------------------------------------
    kwargs: dict[str, Any] = {
        "states": states_spec,
        "steps": steps_spec,
        "track_increments": builder._track_increments,  # noqa: SLF001
        "assertion_mode": None,
        "num_captures": capture_counter,
        "lapse_condition": lapse_condition,
    }

    return args, kwargs


def _compile_step(
    step: StepDef,
    *,
    target_index: int,
    register: Any,  # noqa: ANN401
    state_name_to_index: dict[str, int],
    capture_name_to_index: dict[str, int],
) -> dict[str, Any]:
    """Convert a single StepDef into the serialized dict for Rust.

    Parameters
    ----------
    step
        The step definition to convert.
    target_index
        Pre-resolved target state index.
    register
        Callable that registers a column reference and returns its index.
    state_name_to_index
        Mapping from state names to their indices.
    capture_name_to_index
        Mapping from capture labels to their indices.

    Returns
    -------
    dict[str, Any]
        The step specification dict matching Rust's ``StepSpec`` enum.

    """
    op = step.operation

    # --- Simple input operations (Add, Subtract, Charge, Grow) ---
    if op in ("add", "subtract", "charge", "grow"):
        tag = {
            "add": "Add",
            "subtract": "Subtract",
            "charge": "Charge",
            "grow": "Grow",
        }[op]
        return {
            tag: {
                "target_index": target_index,
                "input_index": register(step.args[0]),
                "label": step.label,
                "expected_input_index": None,
            },
        }

    if op == "grow_capped":
        return {
            "GrowCapped": {
                "target_index": target_index,
                "input_index": register(step.args[0]),
                "rate_floor": step.kwargs["floor"],
                "rate_cap": step.kwargs["cap"],
                "label": step.label,
                "expected_input_index": None,
            },
        }

    if op == "deduct_nar":
        return {
            "DeductNar": {
                "target_index": target_index,
                "rate_index": register(step.args[0]),
                "db_index": register(step.kwargs["death_benefit"]),
                "label": step.label,
                "expected_input_index": None,
            },
        }

    if op == "floor":
        return {
            "Floor": {
                "target_index": target_index,
                "value": float(step.args[0]),
                "label": step.label,
            },
        }

    if op == "cap":
        return {
            "Cap": {
                "target_index": target_index,
                "value": float(step.args[0]),
                "label": step.label,
            },
        }

    if op == "ratchet_to":
        return {
            "RatchetTo": {
                "target_index": target_index,
                "other_state_index": state_name_to_index[step.args[0]],
                "label": step.label,
            },
        }

    if op == "pro_rata_with":
        return {
            "ProRataWith": {
                "target_index": target_index,
                "capture_index": capture_name_to_index[step.args[0]],
                "amount_index": register(step.args[1]),
                "label": step.label,
            },
        }

    if op == "capture":
        return {
            "Capture": {
                "target_index": target_index,
                "capture_index": capture_name_to_index[step.label],
            },
        }

    if op == "lapse_if_zero":
        return {
            "LapseIfZero": {
                "target_index": target_index,
            },
        }

    if op == "add_if":
        return {
            "AddIf": {
                "target_index": target_index,
                "condition_index": register(step.args[0]),
                "amount_index": register(step.args[1]),
                "label": step.label,
            },
        }

    if op == "charge_if":
        return {
            "ChargeIf": {
                "target_index": target_index,
                "condition_index": register(step.args[0]),
                "rate_index": register(step.args[1]),
                "label": step.label,
            },
        }

    msg = f"Unknown rollforward operation: {op!r}"
    raise ValueError(msg)
