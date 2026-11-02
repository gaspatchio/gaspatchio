# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Vector operation plugins for Gaspatchio.

Provides Rust-powered Polars expression plugins for high-performance
vector operations on list columns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from polars.plugins import register_plugin_function

from gaspatchio._internal import __file__ as native_path
from gaspatchio.frame.lowering._polars._shared import _unwrap_proxy

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.typing import IntoExprColumn


# The compiled extension every plugin below registers against. Read at import,
# as the ``_excel`` lowerings read it: ``import gaspatchio`` loads the extension
# whatever this module does (``gaspatchio._identity`` and
# ``gaspatchio.engines._versions`` import it at module level), so deferring the
# read here saved nothing.
_LIB = Path(native_path)


def _get_lib() -> Path:
    """Return the path of the compiled extension the plugins register against."""
    return _LIB


def fill_series(expr: IntoExprColumn, start: int = 0, increment: int = 1) -> pl.Expr:
    """Fill a list column with sequential integers.

    Args:
        expr: Column or expression to fill
        start: Starting value for sequence
        increment: Increment between values

    Returns:
        Expression with filled list column

    """
    expr = _unwrap_proxy(expr)

    return register_plugin_function(
        args=[expr],
        plugin_path=_get_lib(),
        function_name="fill_series",
        is_elementwise=True,
        kwargs={"start": start, "increment": increment},
    )


def accumulate(initial: pl.Expr, multiplier: pl.Expr, addend: pl.Expr) -> pl.Expr:
    """Compute linear recurrence: out[t] = out[t-1] * multiplier[t] + addend[t].

    Produces all intermediate states of the accumulation, returning a list
    column with one value per time step per policy.

    A null multiplier or a null addend at position ``t`` makes ``s[t]`` and
    every later position null. A modeller who means nought writes
    ``af.col.fill_null(0.0)`` before the recurrence, and the graph then records
    that they said so.

    Parameters
    ----------
    initial
        Scalar initial state per row (e.g., initial account value per policy).
    multiplier
        List column of multiplicative factors per time step.
    addend
        List column of additive flows per time step.

    Returns
    -------
    pl.Expr
        List column of accumulated values.

    Examples
    --------
    >>> import polars as pl
    >>> from gaspatchio.frame.lowering._polars.plugins import accumulate
    >>> df = pl.DataFrame(
    ...     {
    ...         "initial": [100.0],
    ...         "multiplier": [[1.01, 1.01, 1.01]],
    ...         "addend": [[10.0, 10.0, 10.0]],
    ...     }
    ... )
    >>> out = df.with_columns(
    ...     accumulate(pl.col("initial"), pl.col("multiplier"), pl.col("addend")).alias(
    ...         "result"
    ...     )
    ... )
    >>> out["result"].to_list()
    [[111.0, 122.11, 133.3311]]

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="accumulate",
        args=[initial, multiplier, addend],
        is_elementwise=True,
    )


def ieee_quotient(
    numerator: pl.Expr,
    divisor: pl.Expr,
    op: Literal["div", "floordiv", "mod"] = "div",
) -> pl.Expr:
    """Divide exactly, one IEEE operation per element, on either column shape.

    ``/``, ``//`` and ``%`` lower here whenever the operands are numbers.
    Polars' own float kernels, handed one divisor for a whole array --
    a literal, a column holding one constant, and how often that happens
    depends on the engine and on how it splits the rows -- multiply by the
    divisor's reciprocal instead of dividing, and ``x * (1 / c)`` is not
    ``x / c``. This kernel divides every element by its own divisor:

    - ``div``: ``n / d``
    - ``floordiv``: ``floor(n / d)``, the floor of the binary64 quotient
    - ``mod``: ``n - d * floor(n / d)``, in binary64

    Either side may be a per-policy column, a per-period (list) column or a
    single value, and a single value broadcasts. The result is ``Float64``,
    or ``List(Float64)`` when either side is a list. A null on either side
    is null at that position; a null list is a null result list; a zero
    divisor gives IEEE's infinity or NaN.

    Args:
        numerator: The value divided.
        divisor: The value it is divided by.
        op: ``"div"``, ``"floordiv"`` or ``"mod"``.

    Returns:
        Expression computing the quotient element by element.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio.frame.lowering._polars.plugins import ieee_quotient
        >>> df = pl.DataFrame({"k": [[135.021, 1.892]], "x": [135.021]})
        >>> out = df.select(
        ...     per_period=ieee_quotient(pl.col("k"), pl.lit(1000)),
        ...     per_policy=ieee_quotient(pl.col("x"), pl.lit(1000)),
        ... )
        >>> out["per_period"].to_list()
        [[0.13502099999999997, 0.0018919999999999998]]
        >>> out["per_policy"].to_list()
        [0.13502099999999997]

    """
    # One symbol per quotient -- ``ieee_div``, ``ieee_floordiv``, ``ieee_mod``
    # -- because Polars renders a plugin call by its symbol and leaves its
    # keywords out: the symbol is what lets a rendered plan say which ran.
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name=f"ieee_{op}",
        args=[numerator, divisor],
        is_elementwise=True,
    )


def norm_cdf(values: pl.Expr) -> pl.Expr:
    """Evaluate the standard normal distribution function at every value.

    Computes ``0.5 * erfc(-x / sqrt(2))`` in the native kernel, one value at a
    time, for a per-policy column and a per-period list column alike. A null
    stays null, a NaN stays NaN, ``+inf`` answers 1.0 and ``-inf`` 0.0. Every
    number is evaluated in double precision and answers a double.

    Args:
        values: The points to evaluate at (a numeric or List column, or an
            expression).

    Returns:
        Expression with the same shape as ``values``: ``Float64``, or
        ``List<Float64>`` for a list column.

    Raises:
        ComputeError: If ``values`` is not numeric.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio.frame.lowering._polars.plugins import norm_cdf
        >>>
        >>> df = pl.DataFrame({"z": [0.0, None, float("inf"), float("-inf")]})
        >>> df.select(phi=norm_cdf(pl.col("z")))["phi"].to_list()
        [0.5, None, 1.0, 0.0]

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="norm_cdf",
        args=[_unwrap_proxy(values)],
        is_elementwise=True,
    )


def list_pow(base: pl.Expr, exp: pl.Expr) -> pl.Expr:
    """Element-wise power operation on list or scalar columns.

    Computes base ** exp element-wise, eliminating the need for the
    EXPLODE/GROUP_BY pattern. Always returns Float64 values.

    Supports:
        - list ** list (pairwise, requires same inner lengths)
        - list ** scalar (broadcasts scalar exponent to each element)
        - Float64 ** Float64 (element-wise scalar columns; output is a flat
          Float64 series, not a List — the output dtype mirrors the base shape)
        - Float64 ** list (a per-row base raised to each period's exponent;
          output is ``List<Float64>``)

    For the Float64-base case a length-1 operand on either side broadcasts
    across the other; a true length mismatch returns a ComputeError.

    Args:
        base: Base values (List column, Float64 scalar column, or expression)
        exp: Exponent values (List column, scalar column, or expression)

    Returns:
        Expression with element-wise power results. Returns ``List<Float64>``
        when either operand is a List column; returns a flat ``Float64``
        series when neither is.

    Raises:
        ComputeError: If base is a Float64 scalar column and lengths differ
            (neither operand is length 1)
        ComputeError: If inner list lengths don't match (for list ** list)

    Examples:
        >>> import polars as pl
        >>> from gaspatchio.frame.lowering._polars.plugins import list_pow
        >>>
        >>> # List ** List
        >>> df = pl.DataFrame(
        ...     {"base": [[2.0, 3.0], [4.0, 5.0]], "exp": [[2.0, 3.0], [2.0, 2.0]]}
        ... )
        >>> out = df.with_columns(result=list_pow(pl.col("base"), pl.col("exp")))
        >>> out["result"].to_list()
        [[4.0, 27.0], [16.0, 25.0]]

        >>> # List ** Scalar
        >>> out = df.with_columns(result=list_pow(pl.col("base"), pl.lit(2.0)))
        >>> out["result"].to_list()
        [[4.0, 9.0], [16.0, 25.0]]

        >>> # Scalar ** List: 10 ** 14 is exactly 1e14
        >>> out = df.select(result=list_pow(pl.lit(10.0), pl.col("exp") * 7))
        >>> out["result"].to_list()
        [[100000000000000.0, 1e+21], [100000000000000.0, 100000000000000.0]]

    Note:
        This is an internal function used by the finance accessor.
        Actuaries should use `af.finance.discount_factor()` instead.

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="list_pow",
        args=[base, exp],
        is_elementwise=True,
    )


def list_clip(values: pl.Expr, lower: pl.Expr, upper: pl.Expr) -> pl.Expr:
    """Element-wise clip operation on list columns with per-row bounds.

    Clips each element in the list column to be within [lower, upper] bounds.
    Supports per-row scalar bounds or list bounds for element-wise clipping.
    Always returns Float64 values.

    Supports:
        - list.clip(scalar_col, scalar_col) - per-row bounds from columns
        - list.clip(list_col, list_col) - per-element bounds from lists
        - list.clip(scalar_col, literal) - mixed bounds

    Args:
        values: Values to clip (List column or expression)
        lower: Lower bound (List/scalar column or expression)
        upper: Upper bound (List/scalar column or expression)

    Returns:
        Expression with clipped values as List<Float64>

    Raises:
        ComputeError: If values is not a List type
        ComputeError: If inner list lengths don't match bounds (for list bounds)

    Examples:
        >>> import polars as pl
        >>> from gaspatchio.frame.lowering._polars.plugins import list_clip
        >>>
        >>> # List with scalar column bounds
        >>> df = pl.DataFrame(
        ...     {
        ...         "values": [[0.5, 1.5, 2.5, 3.5], [0.0, 5.0, 10.0]],
        ...         "lower": [1.0, 2.0],
        ...         "upper": [3.0, 8.0],
        ...     }
        ... )
        >>> out = df.with_columns(
        ...     clipped=list_clip(pl.col("values"), pl.col("lower"), pl.col("upper"))
        ... )
        >>> out["clipped"].to_list()
        [[1.0, 1.5, 2.5, 3.0], [2.0, 5.0, 8.0]]

        >>> # List with literal bounds
        >>> out = df.with_columns(
        ...     clipped=list_clip(pl.col("values"), pl.lit(0.0), pl.lit(5.0))
        ... )
        >>> out["clipped"].to_list()
        [[0.5, 1.5, 2.5, 3.5], [0.0, 5.0, 5.0]]

    Note:
        This is an internal function used by the dispatch system.
        Actuaries should use `af.values.clip(af.lower, af.upper)` syntax.

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="list_clip",
        args=[values, lower, upper],
        is_elementwise=True,
    )


def curve_eval(
    t: pl.Expr,
    *,
    method: str,
    xs: list[float] | None = None,
    ys: list[float] | None = None,
    slopes: list[float] | None = None,
    extrapolation: str = "flat",
    b0: float | None = None,
    b1: float | None = None,
    b2: float | None = None,
    b3: float | None = None,
    tau1: float | None = None,
    tau2: float | None = None,
    u: list[float] | None = None,
    zeta: list[float] | None = None,
    omega: float | None = None,
    alpha: float | None = None,
) -> pl.Expr:
    """Evaluate a yield curve over a column of year-fractions.

    Dispatch on ``method``; each method reads only its relevant kwargs. The
    result is annually-compounded spot rates, shape-polymorphic in ``t``: a
    ``Float64`` column in, a ``Float64`` column out; a ``List<Float64>`` column
    in, a ``List<Float64>`` column out.

    Args:
        t: Year-fraction column — either a scalar ``Float64`` column or a
            ``List<Float64>`` column (one list per row).
        method: Curve method: ``"linear"``, ``"log_linear"``, ``"pchip"``,
            ``"svensson"``, or ``"smith_wilson"``.
        xs: Knot tenors (year-fractions) for the knot-based methods
            (``linear``, ``log_linear``, ``pchip``).
        ys: Knot values at each ``xs`` — rates for ``linear`` / ``pchip``,
            log-discount-factors for ``log_linear``.
        slopes: Per-knot slopes for the ``pchip`` monotone-cubic Hermite
            interpolant.
        extrapolation: Extrapolation mode outside the knot range. ``"flat"``
            (default) holds the boundary knot's spot rate. ``"forward"`` holds
            the boundary segment's forward rate and applies to ``log_linear``
            only — rate-space methods reject it. Unknown values raise; they
            are never silently ignored.
        b0: Nelson-Siegel-Svensson level parameter (``svensson``).
        b1: Nelson-Siegel-Svensson slope parameter (``svensson``).
        b2: Nelson-Siegel-Svensson first-curvature parameter (``svensson``).
        b3: Nelson-Siegel-Svensson second-curvature parameter (``svensson``).
        tau1: Nelson-Siegel-Svensson first decay factor (``svensson``).
        tau2: Nelson-Siegel-Svensson second decay factor (``svensson``).
        u: Smith-Wilson knot tenors used in the Wilson solve (``smith_wilson``).
        zeta: Smith-Wilson weight vector from the Wilson solve (``smith_wilson``).
        omega: ``log(1 + UFR)`` — the continuously-compounded ultimate forward
            rate (``smith_wilson``).
        alpha: Smith-Wilson mean-reversion / convergence speed (``smith_wilson``).

    Returns:
        Expression producing annually-compounded spot rates with the same
        per-row shape as ``t`` — ``Float64`` for a scalar column,
        ``List<Float64>`` for a list column.

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="curve_eval",
        args=[t],
        is_elementwise=True,
        kwargs={
            "method": method,
            "xs": xs,
            "ys": ys,
            "slopes": slopes,
            "extrapolation": extrapolation,
            "b0": b0,
            "b1": b1,
            "b2": b2,
            "b3": b3,
            "tau1": tau1,
            "tau2": tau2,
            "u": u,
            "zeta": zeta,
            "omega": omega,
            "alpha": alpha,
        },
    )


def list_conditional(  # noqa: PLR0913 -- four operands, the comparison, and its NaN reading
    left: pl.Expr,
    right: pl.Expr,
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    operator: str,
    *,
    unknown_is_nan: bool = False,
) -> pl.Expr:
    """Element-wise conditional operation on list columns.

    Computes when/then/otherwise conditionals element-wise for list columns,
    eliminating the need for EXPLODE/GROUP_BY pattern. Always returns Float64 values.

    Supports:
        - list op list (pairwise comparison, requires same inner lengths)
        - list op scalar (broadcasts scalar to each element)
        - then/otherwise can be list or scalar

    Args:
        left: Left values for comparison (List column or expression)
        right: Right values for comparison (List/scalar column or expression)
        then_val: Values when condition is true (List/scalar column or expression)
        otherwise_val: Values when condition is false (List/scalar or expression)
        operator: Comparison operator - "eq", "ne", "lt", "lte", "gt", "gte"
        unknown_is_nan: Answer NaN in a period where either comparison operand
            is NaN, whichever branch holds there: the condition has no truth
            value and selects neither branch (spec 11.1.28). Only for an
            answer that is a double; off, a NaN compares false.

    Returns:
        Expression with element-wise conditional results as List<Float64>

    Raises:
        ComputeError: If left is not a List type
        ComputeError: If inner list lengths don't match (for list op list)
        ComputeError: If operator is not valid

    Examples:
        >>> import polars as pl
        >>> from gaspatchio.frame.lowering._polars.plugins import list_conditional
        >>>
        >>> # List == List with scalar then/otherwise
        >>> df = pl.DataFrame(
        ...     {
        ...         "month": [[0, 1, 2], [0, 1]],
        ...         "term": [[2, 2, 2], [1, 1]],
        ...         "benefit": [100.0, 200.0],
        ...     }
        ... )
        >>> out = df.with_columns(
        ...     payment=list_conditional(
        ...         pl.col("month"),
        ...         pl.col("term"),
        ...         pl.col("benefit"),
        ...         pl.lit(0.0),
        ...         "eq",
        ...     )
        ... )
        >>> out["payment"].to_list()
        [[0.0, 0.0, 100.0], [0.0, 200.0]]

        >>> # List < Scalar with scalar then/otherwise
        >>> out = df.with_columns(
        ...     in_force=list_conditional(
        ...         pl.col("month"), pl.lit(12), pl.lit(1.0), pl.lit(0.0), "lt"
        ...     )
        ... )
        >>> out["in_force"].to_list()
        [[1.0, 1.0, 1.0], [1.0, 1.0]]

    Note:
        This is an internal function used by the conditional module.
        Actuaries should use `when().then().otherwise()` pattern instead.

    """
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="list_conditional",
        args=[left, right, then_val, otherwise_val],
        is_elementwise=True,
        kwargs=conditional_kwargs(operator, unknown_is_nan=unknown_is_nan),
    )


def conditional_kwargs(operator: str, *, unknown_is_nan: bool) -> dict[str, object]:
    """Return the conditional kernel's keyword arguments for one call.

    The flag is written only where it is set, so every other call carries the
    one argument it always did.
    """
    if unknown_is_nan:
        return {"operator": operator, "unknown_is_nan": True}
    return {"operator": operator}


def rollforward_kernel(args: tuple[pl.Expr, ...], kwargs: dict[str, object]) -> pl.Expr:
    """Build the native rollforward call from already compiled operands."""
    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="rollforward",
        args=list(args),
        kwargs=kwargs,
        is_elementwise=True,
    )
