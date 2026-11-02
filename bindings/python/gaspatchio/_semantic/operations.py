# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Engine-neutral declarations for operations exposed on column proxies.

An operation declaration answers what a method means before any execution
engine is chosen: its stable identifier, the arguments the public spelling
accepts, and the ``Call`` payload those arguments produce.  Polars lowering
lives separately in :mod:`gaspatchio.frame.lowering`; the generated proxy
surface and the reflective escape recogniser both consume this module.
"""

import inspect
import math
import numbers
import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import AttrValue, BinOpKind, OpNode


@dataclass(frozen=True, slots=True)
class CoreCall:
    """One method call resolved to an operation of the core vocabulary."""

    name: str
    args: tuple["OpNode", ...]
    attrs: tuple[tuple[str, "AttrValue"], ...] = ()


@dataclass(frozen=True, slots=True)
class _BoundOperation:
    """Arguments bound by one declaration before its identifier is attached."""

    args: tuple["OpNode", ...]
    operands: tuple[object, ...] = ()
    attrs: tuple[tuple[str, "AttrValue"], ...] = ()


@dataclass(frozen=True, slots=True)
class _LiteralOperand:
    """A sequence validated here and converted at the ingress boundary."""

    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ProxyOperation:
    """One operation and the typed function that binds its proxy spelling."""

    identifier: str
    binder: Callable[..., _BoundOperation | None]
    signature: inspect.Signature = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Cache the binder signature once, when the declaration is built."""
        object.__setattr__(
            self,
            "signature",
            inspect.signature(self.binder),
        )

    def bind(
        self,
        receiver: "OpNode",
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
        adapt_operand: Callable[[object], "OpNode | None"],
    ) -> CoreCall | None:
        """Return the call this written form means, or decline the form."""
        try:
            bound = self.signature.bind(receiver, *args, **kwargs)
        except TypeError:
            return None
        payload = self.binder(*bound.args, **bound.kwargs)
        if payload is None:
            return None
        adapted = tuple(adapt_operand(value) for value in payload.operands)
        if any(value is None for value in adapted):
            return None
        return CoreCall(
            name=self.identifier,
            args=(
                *payload.args,
                *(value for value in adapted if value is not None),
            ),
            attrs=payload.attrs,
        )

    def surface_signature(self) -> inspect.Signature:
        """Return the public signature, with the internal receiver removed."""
        parameters = tuple(self.signature.parameters.values())[1:]
        return self.signature.replace(
            parameters=parameters,
            return_annotation=inspect.Signature.empty,
        )


def _abs(receiver: "OpNode") -> _BoundOperation:
    """Compute the absolute value of numeric values in this expression or column.

    Returns the absolute value (magnitude) of all numeric values, converting
    negative values to positive while leaving positive values unchanged.
    This is essential in actuarial analysis for calculating differences,
    deviations, and ensuring positive values for regulatory calculations.

    !!! note "When to use"
        * **Loss Calculations:** Convert negative claim adjustments or refunds
          to positive values for loss ratio calculations and reserve analysis.
        * **Variance Analysis:** Calculate absolute deviations from expected
          values, budgets, or actuarial assumptions for performance measurement.
        * **Risk Metrics:** Compute absolute differences between actual and
          expected mortality, lapse rates, or investment returns.
        * **Data Validation:** Ensure all monetary amounts are positive for
          regulatory reporting where negative values are not permitted.
        * **Model Calibration:** Calculate absolute errors between model
          predictions and actual outcomes for model validation.
        * **Reinsurance Calculations:** Convert negative ceding commission
          adjustments to positive values for treaty accounting.

    Returns
    -------
    ExpressionProxy
        An expression containing the absolute values of the input.
        All negative values become positive, positive values remain unchanged.

    Examples
    --------
    **Scalar Example: Absolute Claim Adjustments**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "claim_id": ["C001", "C002", "C003", "C004"],
        "adjustment_amount": [150.0, -75.0, 200.0, -50.0],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["claim_id"], abs_adjustment=af["adjustment_amount"].abs()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌──────────┬────────────────┐
    │ claim_id ┆ abs_adjustment │
    │ ---      ┆ ---            │
    │ str      ┆ f64            │
    ╞══════════╪════════════════╡
    │ C001     ┆ 150.0          │
    │ C002     ┆ 75.0           │
    │ C003     ┆ 200.0          │
    │ C004     ┆ 50.0           │
    └──────────┴────────────────┘
    ```

    **Vector Example: Portfolio Variance Analysis**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_type": ["TERM", "WHOLE", "UL", "TERM", "WHOLE"],
        "actual_vs_expected": [0.05, -0.03, 0.08, -0.02, 0.04],
    }
    af = ActuarialFrame(data)
    result = af.with_columns(
        af["actual_vs_expected"].abs().polars_native().mean().polars_native().alias(
            "avg_abs_variance"
        )
    ).collect()
    print(result)
    ```

    ```text
    shape: (5, 3)
    ┌─────────────┬────────────────────┬──────────────────┐
    │ policy_type ┆ actual_vs_expected ┆ avg_abs_variance │
    │ ---         ┆ ---                ┆ ---              │
    │ str         ┆ f64                ┆ f64              │
    ╞═════════════╪════════════════════╪══════════════════╡
    │ TERM        ┆ 0.05               ┆ 0.044            │
    │ WHOLE       ┆ -0.03              ┆ 0.044            │
    │ UL          ┆ 0.08               ┆ 0.044            │
    │ TERM        ┆ -0.02              ┆ 0.044            │
    │ WHOLE       ┆ 0.04               ┆ 0.044            │
    └─────────────┴────────────────────┴──────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _sign(receiver: "OpNode") -> _BoundOperation:
    """Compute the sign of numeric values.

    Returns the mathematical sign of each value: 1 for positive, -1 for negative,
    and 0 for zero. Essential for directional analysis, variance decomposition,
    and understanding the nature of financial movements in actuarial datasets.

    !!! note "When to use"
        * **Directional Analysis:** Identify positive vs negative movements in
          claims experience, premium adjustments, or reserve changes.
        * **Performance Assessment:** Classify gains and losses, profit vs loss
          periods, or favorable vs unfavorable variance components.
        * **Risk Classification:** Categorize exposure changes, mortality
          deviations, or investment return directions for risk management analysis.
        * **Trend Analysis:** Identify periods of growth vs decline in policy
          counts, premium volumes, or claim frequencies.
        * **Model Validation:** Analyze residual patterns, prediction errors,
          or model bias detection through directional indicators.
        * **Financial Analysis:** Categorize cash flows, investment returns,
          or expense variances by their directional impact.

    Returns
    -------
    ExpressionProxy
        An expression containing 1.0 for positive values, -1.0 for negative values,
        and 0.0 for zero values. NaN values remain NaN.

    Examples
    --------
    **Scalar Example: Claims Experience Direction**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "period": ["Q1", "Q2", "Q3", "Q4"],
        "claims_variance": [150.0, -75.0, 0.0, -200.0],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["period"], af["claims_variance"], direction=af["claims_variance"].sign()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 3)
    ┌────────┬─────────────────┬───────────┐
    │ period ┆ claims_variance ┆ direction │
    │ ---    ┆ ---             ┆ ---       │
    │ str    ┆ f64             ┆ f64       │
    ╞════════╪═════════════════╪═══════════╡
    │ Q1     ┆ 150.0           ┆ 1.0       │
    │ Q2     ┆ -75.0           ┆ -1.0      │
    │ Q3     ┆ 0.0             ┆ 0.0       │
    │ Q4     ┆ -200.0          ┆ -1.0      │
    └────────┴─────────────────┴───────────┘
    ```

    **Vector Example: Investment Return Classification**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "asset_class": ["Bonds", "Equities", "Real Estate", "Cash"],
        "annual_return": [0.035, -0.12, 0.08, 0.002],
    }
    af = ActuarialFrame(data)
    result = af.with_columns(
        af["annual_return"].sign().polars_native().alias("return_direction"),
        af["asset_class"].polars_native().count().polars_native().alias("count")
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 4)
    ┌─────────────┬───────────────┬──────────────────┬───────┐
    │ asset_class ┆ annual_return ┆ return_direction ┆ count │
    │ ---         ┆ ---           ┆ ---              ┆ ---   │
    │ str         ┆ f64           ┆ f64              ┆ u64   │
    ╞═════════════╪═══════════════╪══════════════════╪═══════╡
    │ Bonds       ┆ 0.035         ┆ 1.0              ┆ 4     │
    │ Equities    ┆ -0.12         ┆ -1.0             ┆ 4     │
    │ Real Estate ┆ 0.08          ┆ 1.0              ┆ 4     │
    │ Cash        ┆ 0.002         ┆ 1.0              ┆ 4     │
    └─────────────┴───────────────┴──────────────────┴───────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _round_sig_figs(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode", digits: int
) -> _BoundOperation | None:
    """Round numeric values to a specified number of significant figures.

    Rounds values to the specified number of significant digits, preserving
    the most meaningful digits regardless of decimal position. Essential for
    maintaining appropriate precision in actuarial calculations and financial
    reporting while ensuring consistency across different magnitude values.

    A decimal is rounded as a spreadsheet shows it: its fifteen significant
    figures are read first, then kept to ``digits`` figures with a half going
    away from zero, so ``0.15`` to one figure is ``0.2`` and ``2.675`` to
    three is ``2.68``, as Excel's ROUND gives. A whole-number column keeps its
    own digits exactly. Decimals from ``10**(digits - 23)`` (``10**-8`` at
    fifteen figures or more) to below ``10**37`` are rounded exactly. Outside
    that range Polars' own rounding answers, which may sit a few units in the
    last place from the fifteen-digit reading, or a figure away where the
    value is within a few units of a half: ``3e-24`` left over where nought
    was meant rounds rather than stopping the run. Zero, NaN and infinity are
    their own answers.

    !!! note "When to use"
        * **Financial Reporting:** Round monetary values, reserve calculations,
          and capital requirements to appropriate significant figures for
          regulatory reports and financial statements.
        * **Mortality Tables:** Present mortality rates, survival probabilities,
          and life expectancies with consistent precision across age ranges.
        * **Statistical Analysis:** Display confidence intervals, standard
          errors, and statistical estimates with appropriate precision for
          actuarial studies.
        * **Pricing Calculations:** Round premium rates, loading factors, and
          policy values to significant figures for consistent presentation.

    Parameters
    ----------
    digits : int
        Number of significant figures to retain: a whole number of at least
        one. Zero or fewer is refused where the line is written.

    Returns
    -------
    ExpressionProxy
        An expression containing values rounded to the specified number of
        significant figures.

    Examples
    --------
    **Scalar Example: Round Claim Amounts**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "claim_amount": [1234567.89, 0.00123456, 98765.4321],
    }
    af = ActuarialFrame(data)

    af.rounded_3sf = af.claim_amount.round_sig_figs(3)

    print(af.collect())
    ```

    ```text
    shape: (3, 3)
    ┌───────────┬──────────────┬─────────────┐
    │ policy_id ┆ claim_amount ┆ rounded_3sf │
    │ ---       ┆ ---          ┆ ---         │
    │ str       ┆ f64          ┆ f64         │
    ╞═══════════╪══════════════╪═════════════╡
    │ P001      ┆ 1.2346e6     ┆ 1.23e6      │
    │ P002      ┆ 0.001235     ┆ 0.00123     │
    │ P003      ┆ 98765.4321   ┆ 98800.0     │
    └───────────┴──────────────┴─────────────┘
    ```

    **Vector Example: Round Mortality Rates**

    ```python
    from gaspatchio import ActuarialFrame
    data = {
        "policy_id": ["P001", "P002"],
        "monthly_mortality_q": [
            [0.000123, 0.000145, 0.000167, 0.000189],
            [0.00234, 0.00256, 0.00278, 0.00301],
        ],
    }
    af = ActuarialFrame(data)

    af.rounded_q = af.monthly_mortality_q.round_sig_figs(2)

    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬──────────────────────────────────┬───────────────────────────────┐
    │ policy_id ┆ monthly_mortality_q              ┆ rounded_q                     │
    │ ---       ┆ ---                              ┆ ---                           │
    │ str       ┆ list[f64]                        ┆ list[f64]                     │
    ╞═══════════╪══════════════════════════════════╪═══════════════════════════════╡
    │ P001      ┆ [0.000123, 0.000145, … 0.000189] ┆ [0.00012, 0.00015, … 0.00019] │
    │ P002      ┆ [0.00234, 0.00256, … 0.00301]    ┆ [0.0023, 0.0026, … 0.003]     │
    └───────────┴──────────────────────────────────┴───────────────────────────────┘
    ```
    """
    # Zero figures keep nothing to round to: Polars refused a decimal column
    # in its own words when the frame ran, and a whole-number column answered
    # 5 as 10. The form is declined where it is written, by name.
    if (
        not isinstance(digits, numbers.Integral)
        or isinstance(digits, bool)
        or digits < 1
    ):
        return None
    return _BoundOperation(
        args=(receiver,),
        attrs=(("digits", int(digits)),),
    )


def _exp(receiver: "OpNode") -> _BoundOperation:
    """Compute the exponential function (e^x) of numeric values.

    Calculates e raised to the power of each value, essential for actuarial
    mathematics including compound interest calculations, exponential growth
    models, and survival function computations in life insurance analytics.

    !!! note "When to use"
        * **Interest Rate Calculations:** Convert log rates back to multiplicative
          factors for compound interest and present value calculations.
        * **Survival Analysis:** Transform hazard rates or cumulative hazards
          back to survival probabilities in mortality modeling.
        * **Growth Models:** Calculate exponential growth factors for premium
          escalation, inflation adjustments, and benefit projections.
        * **Statistical Modeling:** Convert log-transformed variables back to
          original scale in regression models and statistical analysis.
        * **Risk Modeling:** Transform log-normal distributions or calculate
          exponential utility functions in economic capital models.
        * **Financial Mathematics:** Compute continuous compounding factors
          and exponential discounting in investment and pension calculations.

    Returns
    -------
    ExpressionProxy
        An expression containing e raised to the power of each input value.

    Examples
    --------
    **Scalar Example: Convert Log Interest Rates to Growth Factors**

    ```python
    from gaspatchio import ActuarialFrame
    import math

    data = {
        "year": [1, 2, 3, 4, 5],
        "log_interest_rate": [
            math.log(1.03),
            math.log(1.035),
            math.log(1.04),
            math.log(1.025),
            math.log(1.045),
        ],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["year"], growth_factor=af["log_interest_rate"].exp()
    ).collect()
    print(result)
    ```

    ```text
    shape: (5, 2)
    ┌──────┬───────────────┐
    │ year ┆ growth_factor │
    │ ---  ┆ ---           │
    │ i64  ┆ f64           │
    ╞══════╪═══════════════╡
    │ 1    ┆ 1.03          │
    │ 2    ┆ 1.035         │
    │ 3    ┆ 1.04          │
    │ 4    ┆ 1.025         │
    │ 5    ┆ 1.045         │
    └──────┴───────────────┘
    ```

    **Vector Example: Survival Probability from Cumulative Hazard**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "age": [65, 70, 75, 80, 85],
        "cumulative_hazard": [-0.05, -0.15, -0.35, -0.65, -1.20],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["age"],
        survival_prob=af["cumulative_hazard"].exp()
    ).collect()
    print(result)
    ```

    ```text
    shape: (5, 2)
    ┌─────┬───────────────┐
    │ age ┆ survival_prob │
    │ --- ┆ ---           │
    │ i64 ┆ f64           │
    ╞═════╪═══════════════╡
    │ 65  ┆ 0.951229      │
    │ 70  ┆ 0.860708      │
    │ 75  ┆ 0.704688      │
    │ 80  ┆ 0.522046      │
    │ 85  ┆ 0.301194      │
    └─────┴───────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _log(receiver: "OpNode") -> _BoundOperation:
    """Compute the natural logarithm of numeric values.

    Calculates the natural logarithm of each value, essential for
    actuarial mathematics including interest rate transformations, exponential model
    linearization, and statistical analysis requiring log-scale transformations.

    !!! note "When to use"
        * **Interest Rate Analysis:** Transform compound interest rates to additive
          log-scale for linear modeling and time series analysis.
        * **Statistical Modeling:** Apply log transformations to skewed
          distributions like claim amounts or policy values for improved model
          performance.
        * **Growth Rate Calculations:** Convert multiplicative growth factors to
          additive log-growth rates for trend analysis and forecasting.
        * **Risk Modeling:** Transform log-normal distributions to normal scale
          for parameter estimation and model calibration procedures.
        * **Financial Mathematics:** Calculate continuously compounded returns,
          discount factors, and present value calculations.
        * **Model Linearization:** Convert exponential relationships to linear
          form for regression analysis and parameter estimation.

    Returns
    -------
    ExpressionProxy
        An expression containing logarithm values. Returns NaN for
        non-positive inputs.

    Examples
    --------
    **Scalar Example: Interest Rate Transformation**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "year": [1, 2, 3, 4, 5],
        "growth_factor": [1.03, 1.035, 1.04, 1.025, 1.045],
    }
    af = ActuarialFrame(data)
    log_growth_rate = af["growth_factor"].log()
    result = af.select(af["year"], log_growth_rate=log_growth_rate).collect()
    print(result)
    ```

    ```text
    shape: (5, 2)
    ┌──────┬─────────────────┐
    │ year ┆ log_growth_rate │
    │ ---  ┆ ---             │
    │ i64  ┆ f64             │
    ╞══════╪═════════════════╡
    │ 1    ┆ 0.029559        │
    │ 2    ┆ 0.034401        │
    │ 3    ┆ 0.039221        │
    │ 4    ┆ 0.024693        │
    │ 5    ┆ 0.044017        │
    └──────┴─────────────────┘
    ```

    **Vector Example: Log10 Transformation for Analysis**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "claim_type": ["Property", "Liability", "Auto", "Health"],
        "claim_amount": [1000.0, 10000.0, 100000.0, 1000000.0],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["claim_type"],
        log10_amount=af["claim_amount"].polars_native().log(10.0)
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌────────────┬──────────────┐
    │ claim_type ┆ log10_amount │
    │ ---        ┆ ---          │
    │ str        ┆ f64          │
    ╞════════════╪══════════════╡
    │ Property   ┆ 3.0          │
    │ Liability  ┆ 4.0          │
    │ Auto       ┆ 5.0          │
    │ Health     ┆ 6.0          │
    └────────────┴──────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _log1p(receiver: "OpNode") -> _BoundOperation:
    """Compute the natural logarithm of (1 + x) with improved numerical precision.

    Calculates ln(1 + x) using a numerically stable algorithm, avoiding
    precision loss for small values near zero. Essential for actuarial
    calculations involving small interest rates, returns, or growth rates where
    standard logarithm functions would lose significant digits due to
    floating-point arithmetic limitations.

    !!! note "When to use"
        * **Interest Rate Calculations:** Convert small nominal rates to
          continuously compounded rates without precision loss in low-rate
          environments.
        * **Return Calculations:** Calculate log returns from small percentage
          changes in asset values, policy values, or investment performance metrics.
        * **Discount Rate Analysis:** Transform small discount rates for present
          value calculations requiring high numerical accuracy.
        * **Growth Rate Modeling:** Analyze small population growth rates, policy
          persistence changes, or incremental risk factor adjustments.

    Returns
    -------
    ExpressionProxy
        An expression containing ln(1 + x) computed with numerical stability
        for values near zero.

    Examples
    --------
    **Scalar Example: Log Returns from Small Changes**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "excess_return": [0.05, 0.12, -0.03],
    }
    af = ActuarialFrame(data)

    af.log_return = af.excess_return.log1p()

    print(af.collect())
    ```

    ```text
    shape: (3, 3)
    ┌───────────┬───────────────┬────────────┐
    │ policy_id ┆ excess_return ┆ log_return │
    │ ---       ┆ ---           ┆ ---        │
    │ str       ┆ f64           ┆ f64        │
    ╞═══════════╪═══════════════╪════════════╡
    │ P001      ┆ 0.05          ┆ 0.04879    │
    │ P002      ┆ 0.12          ┆ 0.113329   │
    │ P003      ┆ -0.03         ┆ -0.030459  │
    └───────────┴───────────────┴────────────┘
    ```

    **Vector Example: Continuously Compounded Returns**

    ```python
    from gaspatchio import ActuarialFrame
    data = {
        "policy_id": ["P001", "P002"],
        "monthly_returns": [
            [0.01, 0.015, 0.02, -0.005],
            [0.008, 0.012, -0.003, 0.018],
        ],
    }
    af = ActuarialFrame(data)

    af.log_returns = af.monthly_returns.log1p()

    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬─────────────────────────┬──────────────────────────────────┐
    │ policy_id ┆ monthly_returns         ┆ log_returns                      │
    │ ---       ┆ ---                     ┆ ---                              │
    │ str       ┆ list[f64]               ┆ list[f64]                        │
    ╞═══════════╪═════════════════════════╪══════════════════════════════════╡
    │ P001      ┆ [0.01, 0.015, … -0.005] ┆ [0.00995, 0.014889, … -0.005013] │
    │ P002      ┆ [0.008, 0.012, … 0.018] ┆ [0.007968, 0.011929, … 0.01784]  │
    └───────────┴─────────────────────────┴──────────────────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _log10(receiver: "OpNode") -> _BoundOperation:
    """Compute the base-10 logarithm of numeric values.

    Calculates the common logarithm (log base 10) of each value, useful for
    analyzing data that spans orders of magnitude and for converting values
    to logarithmic scales. Essential in actuarial work for handling highly
    skewed distributions and displaying large-range data on comprehensible scales.

    !!! note "When to use"
        * **Data Visualization:** Transform claim amounts, policy values, or
          exposure data spanning multiple orders of magnitude for clearer charts.
        * **Magnitude Analysis:** Analyze data by orders of magnitude for portfolio
          segmentation, premium banding, or risk classification schemes.
        * **Statistical Modeling:** Apply log-scale transformations to highly skewed
          distributions like catastrophic claims or large loss data.
        * **Richter-Style Scales:** Create logarithmic scales for internal risk
          ratings, severity classifications, or standardized reporting metrics.

    Returns
    -------
    ExpressionProxy
        An expression containing the base-10 logarithm of each value.

    Examples
    --------
    **Scalar Example: Claim Magnitude Analysis**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "claim_amount": [100.0, 1000.0, 10000.0],
    }
    af = ActuarialFrame(data)

    af.log10_amount = af.claim_amount.log10()

    print(af.collect())
    ```

    ```text
    shape: (3, 3)
    ┌───────────┬──────────────┬──────────────┐
    │ policy_id ┆ claim_amount ┆ log10_amount │
    │ ---       ┆ ---          ┆ ---          │
    │ str       ┆ f64          ┆ f64          │
    ╞═══════════╪══════════════╪══════════════╡
    │ P001      ┆ 100.0        ┆ 2.0          │
    │ P002      ┆ 1000.0       ┆ 3.0          │
    │ P003      ┆ 10000.0      ┆ 4.0          │
    └───────────┴──────────────┴──────────────┘
    ```

    **Vector Example: Policy Value Orders of Magnitude**

    ```python
    from gaspatchio import ActuarialFrame
    data = {
        "policy_id": ["P001", "P002"],
        "monthly_values": [
            [1000.0, 5000.0, 10000.0, 50000.0],
            [500.0, 2500.0, 12500.0, 62500.0],
        ],
    }
    af = ActuarialFrame(data)

    af.log10_values = af.monthly_values.log10()

    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬─────────────────────────────┬───────────────────────────────┐
    │ policy_id ┆ monthly_values              ┆ log10_values                  │
    │ ---       ┆ ---                         ┆ ---                           │
    │ str       ┆ list[f64]                   ┆ list[f64]                     │
    ╞═══════════╪═════════════════════════════╪═══════════════════════════════╡
    │ P001      ┆ [1000.0, 5000.0, … 50000.0] ┆ [3.0, 3.69897, … 4.69897]     │
    │ P002      ┆ [500.0, 2500.0, … 62500.0]  ┆ [2.69897, 3.39794, … 4.79588] │
    └───────────┴─────────────────────────────┴───────────────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _sqrt(receiver: "OpNode") -> _BoundOperation:
    """Compute the square root of numeric values.

    Calculates the positive square root of each value, essential for actuarial
    mathematics including standard deviation calculations, volatility measures,
    and risk metric computations in insurance and financial modeling.

    !!! note "When to use"
        * **Standard Deviation:** Calculate standard deviations from variance
          values for risk measurement and statistical analysis.
        * **Volatility Modeling:** Compute volatility measures from variance
          calculations in investment and market risk assessments.
        * **Risk Metrics:** Calculate standard errors, confidence intervals,
          and risk measures requiring square root transformations.
        * **Financial Mathematics:** Compute values in options pricing models,
          duration calculations, and portfolio optimization.
        * **Statistical Analysis:** Transform quadratic measures back to linear
          scale for interpretation and reporting purposes.
        * **Model Calibration:** Calculate parameter estimates requiring square
          root transformations in actuarial model fitting procedures.

    Returns
    -------
    ExpressionProxy
        An expression containing the square root of each input value.
        Returns NaN for negative input values.

    Examples
    --------
    **Scalar Example: Calculate Standard Deviation from Variance**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "portfolio": ["Life", "Health", "Property", "Annuity"],
        "variance": [2500.0, 1600.0, 3600.0, 900.0],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["portfolio"], standard_deviation=af["variance"].sqrt()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌───────────┬────────────────────┐
    │ portfolio ┆ standard_deviation │
    │ ---       ┆ ---                │
    │ str       ┆ f64                │
    ╞═══════════╪════════════════════╡
    │ Life      ┆ 50.0               │
    │ Health    ┆ 40.0               │
    │ Property  ┆ 60.0               │
    │ Annuity   ┆ 30.0               │
    └───────────┴────────────────────┘
    ```

    **Vector Example: Risk-Adjusted Returns**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "year": [2020, 2021, 2022, 2023],
        "squared_excess_return": [0.0025, 0.0016, 0.0036, 0.0049],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["year"],
        volatility=af["squared_excess_return"].sqrt()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌──────┬────────────┐
    │ year ┆ volatility │
    │ ---  ┆ ---        │
    │ i64  ┆ f64        │
    ╞══════╪════════════╡
    │ 2020 ┆ 0.05       │
    │ 2021 ┆ 0.04       │
    │ 2022 ┆ 0.06       │
    │ 2023 ┆ 0.07       │
    └──────┴────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _cbrt(receiver: "OpNode") -> _BoundOperation:
    """Compute the cube root of numeric values.

    Calculates the cube root (third root) of each value, useful for inverse
    transformations and specific actuarial calculations. Unlike square root,
    cube root is defined for negative numbers, preserving the sign of the input.

    !!! note "When to use"
        * **Volume Calculations:** Transform cubic measures back to linear
          scale for dimensional analysis in specialized insurance calculations.
        * **Statistical Transformations:** Apply cube root transformation to
          moderately skewed distributions for improved normality.
        * **Index Construction:** Create cube-root weighted indices or scoring
          systems that moderately compress large values.

    Returns
    -------
    ExpressionProxy
        An expression containing the cube root of each input value.
        Preserves sign for negative values.

    Examples
    --------
    **Scalar Example: Cube Root Transformation**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "volume": [8.0, 27.0, 64.0],
    }
    af = ActuarialFrame(data)

    af.side_length = af.volume.cbrt()

    print(af.collect())
    ```

    ```text
    shape: (3, 3)
    ┌───────────┬────────┬─────────────┐
    │ policy_id ┆ volume ┆ side_length │
    │ ---       ┆ ---    ┆ ---         │
    │ str       ┆ f64    ┆ f64         │
    ╞═══════════╪════════╪═════════════╡
    │ P001      ┆ 8.0    ┆ 2.0         │
    │ P002      ┆ 27.0   ┆ 3.0         │
    │ P003      ┆ 64.0   ┆ 4.0         │
    └───────────┴────────┴─────────────┘
    ```

    **Vector Example: Cube Root of Risk Scores**

    ```python
    from gaspatchio import ActuarialFrame
    data = {
        "policy_id": ["P001", "P002"],
        "risk_cubed": [
            [1000.0, 8000.0, 27000.0, 64000.0],
            [125.0, 343.0, 729.0, 1331.0],
        ],
    }
    af = ActuarialFrame(data)

    af.risk_score = af.risk_cubed.cbrt()

    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬─────────────────────────────┬──────────────────────┐
    │ policy_id ┆ risk_cubed                  ┆ risk_score           │
    │ ---       ┆ ---                         ┆ ---                  │
    │ str       ┆ list[f64]                   ┆ list[f64]            │
    ╞═══════════╪═════════════════════════════╪══════════════════════╡
    │ P001      ┆ [1000.0, 8000.0, … 64000.0] ┆ [10.0, 20.0, … 40.0] │
    │ P002      ┆ [125.0, 343.0, … 1331.0]    ┆ [5.0, 7.0, … 11.0]   │
    └───────────┴─────────────────────────────┴──────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


# --- tests of absence and non-finite values -------------------------------


def _norm_cdf(receiver: "OpNode") -> _BoundOperation:
    """Evaluate the standard normal distribution function, Φ, at each value.

    Returns the probability that a standard normal variable is at most the
    value: ``Φ(z)``, the N(...) of a Black-Scholes formula. It is computed as
    ``0.5 * erfc(-z / √2)``, one value at a time, in a native kernel.

    !!! note "When to use"
        * **Guarantees priced as options:** A GMDB or GMMB valued as a
          Black-Scholes put needs N(-d1) and N(-d2) at every period of every
          policy.
        * **Workbook conversion:** Excel's ``NORM.S.DIST(z, TRUE)`` and
          ``NORMSDIST(z)`` are ``z.norm_cdf()``. ``NORM.DIST(x, mean, sd,
          TRUE)`` is ``((x - mean) / sd).norm_cdf()``: standardise first.
          ``af.z.excel.norm_s_dist()`` is the Excel spelling of this same
          operation and records the same node.
        * **The standard normal cumulative distribution function:** Wherever
          a formula reads N(x), Φ(x) or a normal CDF -- including one built
          from the error function, ``0.5 * (1 + erf(x / √2))`` or
          ``0.5 * erfc(-x / √2)``, which this replaces.
        * **Normal tail probabilities:** The chance that a normally
          distributed loss, return or claim count stays below a threshold.

    **How accurate it is.** The contract is agreement with the mathematical
    Φ to **1e-12 relative** wherever Φ is a normal double, which is every
    ``z >= -37.5``, the same tolerance ``exp`` and ``log`` carry. The special
    values are exact: a null stays null, a NaN stays NaN, ``+inf`` gives 1.0
    and ``-inf`` gives 0.0. Measured against a 60-digit reference, the worst
    error is 6.0e-15 relative where ``|z| <= 6`` and 1.8e-13 in the far lower
    tail, near ``z = -37``. Below ``-37.5`` the answer is subnormal, and from
    about ``-38.5`` it is 0.0.

    **Excel's own bits are not reproduced.** Excel's algorithm is
    unpublished. Its cached values sit within about 1e-14 of the true Φ over
    the range workbooks use, so reconcile a converted workbook at that order,
    not to the last bit.

    **Not the textbook formula.** ``0.5 * (1 + erf(z / √2))`` is right to
    about eight digits in the body and wrong by 100% in the lower tail: at
    ``z = -8.36`` it answers 0.0 where Φ is 3.1e-17. This is why the
    vocabulary carries Φ itself rather than leaving it to be composed.

    The density, Excel's ``NORM.S.DIST(z, FALSE)``, is written in core
    operations: ``(-z**2 / 2).exp() / (2 * math.pi) ** 0.5``. The inverse,
    ``NORM.S.INV``, is not in 1.0. For a constant fixed before the
    projection, such as the 99.5% point of a capital shock, compute it in
    setup with ``statistics.NormalDist().inv_cdf(0.995)`` and use the number.

    Returns
    -------
    ExpressionProxy
        An expression with Φ of each value: a ``Float64`` per policy, or a
        ``List[Float64]`` per period, the receiver's own shape.

    Examples
    --------
    **Scalar Example: A GMDB Priced as a Black-Scholes Put**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "fund": [100_000.0, 80_000.0],
        "guarantee": [100_000.0, 100_000.0],
        "rate": [0.03, 0.03],
        "vol": [0.18, 0.18],
        "term": [10.0, 10.0],
    }
    af = ActuarialFrame(data)

    af.sd = af.vol * af.term.sqrt()
    af.drift = (af.rate + af.vol**2 / 2) * af.term
    af.d1 = ((af.fund / af.guarantee).log() + af.drift) / af.sd
    af.d2 = af.d1 - af.sd
    af.n_minus_d2 = (-af.d2).norm_cdf()
    af.n_minus_d1 = (-af.d1).norm_cdf()
    af.gmdb_put = (
        af.guarantee * (-af.rate * af.term).exp() * af.n_minus_d2
        - af.fund * af.n_minus_d1
    )

    print(af.collect().select("policy_id", "n_minus_d2", "n_minus_d1", "gmdb_put"))
    ```

    ```text
    shape: (2, 4)
    ┌───────────┬────────────┬────────────┬──────────────┐
    │ policy_id ┆ n_minus_d2 ┆ n_minus_d1 ┆ gmdb_put     │
    │ ---       ┆ ---        ┆ ---        ┆ ---          │
    │ str       ┆ f64        ┆ f64        ┆ f64          │
    ╞═══════════╪════════════╪════════════╪══════════════╡
    │ P001      ┆ 0.404219   ┆ 0.208496   ┆ 9095.700862  │
    │ P002      ┆ 0.559453   ┆ 0.337379   ┆ 14454.992571 │
    └───────────┴────────────┴────────────┴──────────────┘
    ```

    **Vector Example: Φ at Every Projection Period**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "z": [[-1.96, 0.0, 1.96], [-3.0, 3.0]],
    }
    af = ActuarialFrame(data)

    af.phi = af.z.norm_cdf()

    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬────────────────────┬───────────────────────────┐
    │ policy_id ┆ z                  ┆ phi                       │
    │ ---       ┆ ---                ┆ ---                       │
    │ str       ┆ list[f64]          ┆ list[f64]                 │
    ╞═══════════╪════════════════════╪═══════════════════════════╡
    │ P001      ┆ [-1.96, 0.0, 1.96] ┆ [0.024998, 0.5, 0.975002] │
    │ P002      ┆ [-3.0, 3.0]        ┆ [0.00135, 0.99865]        │
    └───────────┴────────────────────┴───────────────────────────┘
    ```

    **Excel's NORM.DIST: Standardise, Then Evaluate**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"claims": [110.0, 95.0]})

    # NORM.DIST(claims, 100, 10, TRUE)
    af.p_below = ((af.claims - 100.0) / 10.0).norm_cdf()

    print(af.collect())
    ```

    ```text
    shape: (2, 2)
    ┌────────┬──────────┐
    │ claims ┆ p_below  │
    │ ---    ┆ ---      │
    │ f64    ┆ f64      │
    ╞════════╪══════════╡
    │ 110.0  ┆ 0.841345 │
    │ 95.0   ┆ 0.308538 │
    └────────┴──────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_finite(receiver: "OpNode") -> _BoundOperation:
    """Check which values are finite numbers in this expression or column.

    Returns a boolean expression indicating which values are finite (neither
    NaN nor infinite). Essential for validating calculation results and
    ensuring numerical stability in actuarial computations.

    !!! note "When to use"
        * **Validation:** Ensure calculation results are within valid numerical
          ranges before using in reserves, premiums, or benefit calculations.
        * **Data Quality:** Filter records with valid finite values for statistical
          analysis and model fitting procedures.
        * **Numerical Stability:** Identify and handle overflow or underflow
          conditions in iterative calculations and model projections.

    Returns
    -------
    ExpressionProxy
        A boolean expression where True indicates finite values and False
        indicates NaN, infinity, or null values.

    Examples
    --------
    **Scalar Example: Validate Calculation Results**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "result": [1200.5, float("inf"), float("nan"), 1500.0],
    }
    af = ActuarialFrame(data)

    af.is_valid = af.result.is_finite()

    print(af.collect())
    ```

    ```text
    shape: (4, 3)
    ┌───────────┬────────┬──────────┐
    │ policy_id ┆ result ┆ is_valid │
    │ ---       ┆ ---    ┆ ---      │
    │ str       ┆ f64    ┆ bool     │
    ╞═══════════╪════════╪══════════╡
    │ P001      ┆ 1200.5 ┆ true     │
    │ P002      ┆ inf    ┆ false    │
    │ P003      ┆ NaN    ┆ false    │
    │ P004      ┆ 1500.0 ┆ true     │
    └───────────┴────────┴──────────┘
    ```

    **Vector Example: Validate Projection Results**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "reserves": [
            [1000.0, 1100.0, float('inf'), 1300.0],
            [2000.0, float('nan'), 2200.0, 2300.0],
        ],
    }
    af = ActuarialFrame(data)

    af.valid_reserves = af.reserves.is_finite()

    print(af.collect()["valid_reserves"].to_list())
    ```

    ```text
    [[True, True, False, True], [True, False, True, True]]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_infinite(receiver: "OpNode") -> _BoundOperation:
    """Check which values are infinite in this expression or column.

    Returns a boolean expression indicating which values are positive or
    negative infinity, typically resulting from overflow or division by zero.
    Essential for detecting numerical instability in actuarial calculations.

    !!! note "When to use"
        * **Overflow Detection:** Identify calculations that have overflowed
          in exponential growth models or compound interest calculations.
        * **Division Checks:** Find division by zero errors in rate calculations,
          ratios, or normalized metrics.
        * **Model Validation:** Detect numerical instability in iterative
          algorithms or projection models.

    Returns
    -------
    ExpressionProxy
        A boolean expression where True indicates infinite values (positive
        or negative) and False indicates finite numbers, NaN, or null.

    Examples
    --------
    **Scalar Example: Detect Overflow**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "growth_factor": [1.5, float("inf"), 2.0, float("-inf")],
    }
    af = ActuarialFrame(data)

    af.has_overflow = af.growth_factor.is_infinite()

    print(af.collect())
    ```

    ```text
    shape: (4, 3)
    ┌───────────┬───────────────┬──────────────┐
    │ policy_id ┆ growth_factor ┆ has_overflow │
    │ ---       ┆ ---           ┆ ---          │
    │ str       ┆ f64           ┆ bool         │
    ╞═══════════╪═══════════════╪══════════════╡
    │ P001      ┆ 1.5           ┆ false        │
    │ P002      ┆ inf           ┆ true         │
    │ P003      ┆ 2.0           ┆ false        │
    │ P004      ┆ -inf          ┆ true         │
    └───────────┴───────────────┴──────────────┘
    ```

    **Vector Example: Check Discount Factors**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "discount_factors": [
            [0.95, 0.90, 0.85, 0.80],
            [1.0, 0.0, float('inf'), 0.75],
        ],
    }
    af = ActuarialFrame(data)

    af.invalid_discount = af.discount_factors.is_infinite()

    print(af.collect()["invalid_discount"].to_list())
    ```

    ```text
    [[False, False, False, False], [False, False, True, False]]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_nan(receiver: "OpNode") -> _BoundOperation:
    """Check which values are NaN (Not a Number) in this expression or column.

    Returns a boolean expression indicating which values are NaN, typically
    resulting from invalid mathematical operations like 0/0 or sqrt(-1).
    Essential for data quality checks and handling computational edge cases.

    !!! note "When to use"
        * **Data Quality:** Identify invalid calculation results from mathematical
          operations in premium, reserve, or benefit calculations.
        * **Error Detection:** Find computational errors in model runs, such as
          division by zero or invalid log/sqrt operations.
        * **Data Cleaning:** Filter or flag records with NaN values before
          analysis or reporting to ensure data integrity.

    Returns
    -------
    ExpressionProxy
        A boolean expression where True indicates NaN values and False
        indicates valid numbers or null values.

    Examples
    --------
    **Scalar Example: Detect Invalid Calculations**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "calculation": [1.5, float("nan"), 2.3, float("inf")],
    }
    af = ActuarialFrame(data)

    af.has_nan = af.calculation.is_nan()

    print(af.collect())
    ```

    ```text
    shape: (4, 3)
    ┌───────────┬─────────────┬─────────┐
    │ policy_id ┆ calculation ┆ has_nan │
    │ ---       ┆ ---         ┆ ---     │
    │ str       ┆ f64         ┆ bool    │
    ╞═══════════╪═════════════╪═════════╡
    │ P001      ┆ 1.5         ┆ false   │
    │ P002      ┆ NaN         ┆ true    │
    │ P003      ┆ 2.3         ┆ false   │
    │ P004      ┆ inf         ┆ false   │
    └───────────┴─────────────┴─────────┘
    ```

    **Vector Example: Flag Invalid Mortality Rates**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "mortality_q": [
            [0.001, 0.002, float('nan'), 0.003],
            [0.004, 0.005, 0.006, float('nan')],
        ],
    }
    af = ActuarialFrame(data)

    af.invalid_q = af.mortality_q.is_nan()

    print(af.collect()["invalid_q"].to_list())
    ```

    ```text
    [[False, False, True, False], [False, False, False, True]]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_not_nan(receiver: "OpNode") -> _BoundOperation:
    """Check which values are not NaN (Not a Number) in this expression or column.

    Returns a boolean expression indicating which values are valid numbers or
    null (but not NaN). Complement of is_nan, useful for filtering valid
    computational results in actuarial calculations.

    !!! note "When to use"
        * **Valid Data Selection:** Filter records with valid calculation results
          for downstream analysis and reporting.
        * **Quality Assurance:** Identify successfully computed values in model
          projections and reserve calculations.
        * **Data Processing:** Select records without computational errors for
          aggregation and statistical analysis.

    Returns
    -------
    ExpressionProxy
        A boolean expression where True indicates non-NaN values (including
        null, finite numbers, and infinity) and False indicates NaN.

    Examples
    --------
    **Scalar Example: Filter Valid Calculations**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "premium": [1200.0, float("nan"), 1500.0, 1800.0],
    }
    af = ActuarialFrame(data)

    af.valid_premium = af.premium.is_not_nan()

    print(af.collect())
    ```

    ```text
    shape: (4, 3)
    ┌───────────┬─────────┬───────────────┐
    │ policy_id ┆ premium ┆ valid_premium │
    │ ---       ┆ ---     ┆ ---           │
    │ str       ┆ f64     ┆ bool          │
    ╞═══════════╪═════════╪═══════════════╡
    │ P001      ┆ 1200.0  ┆ true          │
    │ P002      ┆ NaN     ┆ false         │
    │ P003      ┆ 1500.0  ┆ true          │
    │ P004      ┆ 1800.0  ┆ true          │
    └───────────┴─────────┴───────────────┘
    ```

    **Vector Example: Count Valid Projections**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "monthly_benefits": [
            [100.0, 105.0, float('nan'), 115.0],
            [200.0, 210.0, 220.0, float('nan')],
        ],
    }
    af = ActuarialFrame(data)

    af.valid_months = af.monthly_benefits.is_not_nan().list.sum()

    print(af.collect()["valid_months"].to_list())
    ```

    ```text
    [3, 3]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_not_null(receiver: "OpNode") -> _BoundOperation:
    """Check which values are not null (not missing) in this expression or column.

    Returns a boolean expression indicating which values are present and valid.
    Essential for data quality assessment, filtering complete records, and
    implementing conditional logic based on data availability in actuarial analysis.

    !!! note "When to use"
        * **Data Quality Filtering:** Select only records with complete information
          for premium calculations, claim processing, or risk assessment.
        * **Conditional Processing:** Apply different business rules based on data
          availability, such as using default values only when primary data exists.
        * **Complete Case Analysis:** Identify policies or claims with full data
          sets for statistical analysis and model development.
        * **Validation Rules:** Ensure critical fields are populated before
          processing transactions, calculating reserves, or generating reports.
        * **Data Completeness Metrics:** Calculate percentages of complete records
          for data quality monitoring and process improvement.
        * **Business Logic:** Implement rules that require specific information
          to be present before applying rates, discounts, or risk adjustments.

    Returns
    -------
    ExpressionProxy
        An expression containing boolean values indicating whether each
        value in the original expression is not null (True) or null (False).

    Examples
    --------
    **Scalar Example: Filter Complete Policy Records**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "beneficiary": ["John Doe", None, "Jane Smith", "Bob Wilson"],
        "premium": [1200.0, 1500.0, None, 1800.0],
    }
    af = ActuarialFrame(data)
    result = af.with_columns(
        (af["beneficiary"].is_not_null() & af["premium"].is_not_null())
        .polars_native()
        .alias("complete_record")
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 4)
    ┌───────────┬─────────────┬─────────┬─────────────────┐
    │ policy_id ┆ beneficiary ┆ premium ┆ complete_record │
    │ ---       ┆ ---         ┆ ---     ┆ ---             │
    │ str       ┆ str         ┆ f64     ┆ bool            │
    ╞═══════════╪═════════════╪═════════╪═════════════════╡
    │ P001      ┆ John Doe    ┆ 1200.0  ┆ true            │
    │ P002      ┆ null        ┆ 1500.0  ┆ false           │
    │ P003      ┆ Jane Smith  ┆ null    ┆ false           │
    │ P004      ┆ Bob Wilson  ┆ 1800.0  ┆ true            │
    └───────────┴─────────────┴─────────┴─────────────────┘
    ```

    **List Example: Data Completeness by Projection Period**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "medical_exam": [
            ["Complete", None, "Complete"],
            [None, None, "Complete"],
        ],
    }
    af = ActuarialFrame(data)
    af.present = af.medical_exam.is_not_null()
    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬────────────────────────────────┬──────────────────────┐
    │ policy_id ┆ medical_exam                   ┆ present              │
    │ ---       ┆ ---                            ┆ ---                  │
    │ str       ┆ list[str]                      ┆ list[bool]           │
    ╞═══════════╪════════════════════════════════╪══════════════════════╡
    │ P001      ┆ ["Complete", null, "Complete"] ┆ [true, false, true]  │
    │ P002      ┆ [null, null, "Complete"]       ┆ [false, false, true] │
    └───────────┴────────────────────────────────┴──────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _is_null(receiver: "OpNode") -> _BoundOperation:
    """Check which values are null (missing) in this expression or column.

    Returns a boolean expression indicating which values are null/missing.
    This is essential for data quality assessment, missing data analysis,
    and implementing conditional logic based on data availability in
    actuarial datasets.

    !!! note "When to use"
        * **Data Quality Checks:** Identify missing premium payments, incomplete
          policy information, or missing claim details for data validation.
        * **Conditional Logic:** Create business rules that handle missing data
          differently, such as excluding incomplete records from calculations.
        * **Missing Data Analysis:** Assess patterns of missingness across
          different variables to understand data collection issues.
        * **Regulatory Compliance:** Identify incomplete records that may need
          special handling for regulatory reporting requirements.
        * **Risk Assessment:** Flag policies or claims with missing critical
          information that might require manual review or adjustment.
        * **Data Imputation:** Identify which values need imputation or
          estimation before performing actuarial calculations.

    Returns
    -------
    ExpressionProxy
        An expression containing boolean values indicating whether each
        value in the original expression is null (True) or not null (False).

    Examples
    --------
    **Scalar Example: Identifying Missing Claim Amounts**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "claim_id": ["C001", "C002", "C003", "C004"],
        "claim_amount": [1200.0, None, 2800.0, None],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["claim_id"], missing_amount=af["claim_amount"].is_null()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌──────────┬────────────────┐
    │ claim_id ┆ missing_amount │
    │ ---      ┆ ---            │
    │ str      ┆ bool           │
    ╞══════════╪════════════════╡
    │ C001     ┆ false          │
    │ C002     ┆ true           │
    │ C003     ┆ false          │
    │ C004     ┆ true           │
    └──────────┴────────────────┘
    ```

    **List Example: Identify Missing Beneficiaries by Period**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "beneficiary": [
            ["John", None, "Jane"],
            [None, "Alex", None],
        ],
    }
    af = ActuarialFrame(data)
    af.missing = af.beneficiary.is_null()
    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬────────────────────────┬──────────────────────┐
    │ policy_id ┆ beneficiary            ┆ missing              │
    │ ---       ┆ ---                    ┆ ---                  │
    │ str       ┆ list[str]              ┆ list[bool]           │
    ╞═══════════╪════════════════════════╪══════════════════════╡
    │ P001      ┆ ["John", null, "Jane"] ┆ [false, true, false] │
    │ P002      ┆ [null, "Alex", null]   ┆ [true, false, true]  │
    └───────────┴────────────────────────┴──────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


# --- whole-step rounding ---------------------------------------------------


def _ceil(receiver: "OpNode") -> _BoundOperation:
    """Round numeric values up to the nearest integer.

    Applies ceiling function to each value, returning the smallest integer greater
    than or equal to the input. Essential for actuarial calculations requiring
    conservative upward rounding, capacity planning, and regulatory calculations
    with prudent assumptions.

    !!! note "When to use"
        * **Conservative Estimates:** Apply prudent upward rounding for reserve
          calculations, capital requirements, or risk margin computations.
        * **Capacity Planning:** Round up exposure units, policy counts, or
          resource requirements to ensure adequate capacity and coverage.
        * **Regulatory Compliance:** Implement conservative rounding rules required
          by prudential regulations or solvency frameworks.
        * **Policy Limits:** Calculate coverage units, deductible periods, or
          benefit payment periods requiring full unit coverage.
        * **Resource Allocation:** Round up staffing requirements, system capacity,
          or operational resources to meet service level agreements.
        * **Risk Management:** Apply conservative assumptions for stress testing,
          scenario analysis, or worst-case planning exercises.

    Returns
    -------
    ExpressionProxy
        An expression containing values rounded up to the nearest integer.

    Examples
    --------
    **Scalar Example: Conservative Reserve Calculation**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "claim_type": ["Property", "Liability", "Auto", "Health"],
        "reserve_estimate": [15432.3, 28901.7, 7234.1, 45678.9],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["claim_type"], conservative_reserve=af["reserve_estimate"].ceil()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌────────────┬──────────────────────┐
    │ claim_type ┆ conservative_reserve │
    │ ---        ┆ ---                  │
    │ str        ┆ f64                  │
    ╞════════════╪══════════════════════╡
    │ Property   ┆ 15433.0              │
    │ Liability  ┆ 28902.0              │
    │ Auto       ┆ 7235.0               │
    │ Health     ┆ 45679.0              │
    └────────────┴──────────────────────┘
    ```

    **List Example: Policy Count Planning by Period**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "region": ["North", "South"],
        "projected_policies": [
            [1234.2, 2567.8, 1890.3],
            [3421.6, 100.1, 99.0],
        ],
    }
    af = ActuarialFrame(data)
    af.capacity_needed = af.projected_policies.ceil()
    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌────────┬──────────────────────────┬──────────────────────────┐
    │ region ┆ projected_policies       ┆ capacity_needed          │
    │ ---    ┆ ---                      ┆ ---                      │
    │ str    ┆ list[f64]                ┆ list[f64]                │
    ╞════════╪══════════════════════════╪══════════════════════════╡
    │ North  ┆ [1234.2, 2567.8, 1890.3] ┆ [1235.0, 2568.0, 1891.0] │
    │ South  ┆ [3421.6, 100.1, 99.0]    ┆ [3422.0, 101.0, 99.0]    │
    └────────┴──────────────────────────┴──────────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _floor(receiver: "OpNode") -> _BoundOperation:
    """Round numeric values down to the nearest integer.

    Applies floor function to each value, returning the largest integer less than
    or equal to the input. Essential for actuarial calculations requiring
    conservative rounding, age calculations, and regulatory computations with
    specific rounding rules.

    !!! note "When to use"
        * **Age Calculations:** Convert decimal ages to completed years for
          underwriting, pricing tables, and regulatory age classifications.
        * **Conservative Estimates:** Apply conservative rounding for reserve
          calculations, capital requirements, or risk assessments.
        * **Regulatory Compliance:** Implement specific rounding rules required
          by insurance regulations or accounting standards.
        * **Policy Duration:** Calculate completed policy years or months for
          persistency analysis and commission calculations.
        * **Rate Table Lookups:** Round continuous values to discrete table
          entries for mortality tables, lapse rates, or premium factors.
        * **Financial Calculations:** Apply floor rounding for guaranteed minimum
          benefits, surrender values, or dividend calculations.

    Returns
    -------
    ExpressionProxy
        An expression containing values rounded down to the nearest integer.

    Examples
    --------
    **Scalar Example: Age Calculation**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "age_decimal": [35.8, 42.2, 58.9, 67.1],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["policy_id"], completed_age=af["age_decimal"].floor()
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 2)
    ┌───────────┬───────────────┐
    │ policy_id ┆ completed_age │
    │ ---       ┆ ---           │
    │ str       ┆ f64           │
    ╞═══════════╪═══════════════╡
    │ P001      ┆ 35.0          │
    │ P002      ┆ 42.0          │
    │ P003      ┆ 58.0          │
    │ P004      ┆ 67.0          │
    └───────────┴───────────────┘
    ```

    **List Example: Policy Year Calculation by Period**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_type": ["TERM", "WHOLE"],
        "duration_decimal": [
            [2.3, 5.7, 1.9],
            [10.4, 3.0, 7.8],
        ],
    }
    af = ActuarialFrame(data)
    af.completed_years = af.duration_decimal.floor()
    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌─────────────┬──────────────────┬──────────────────┐
    │ policy_type ┆ duration_decimal ┆ completed_years  │
    │ ---         ┆ ---              ┆ ---              │
    │ str         ┆ list[f64]        ┆ list[f64]        │
    ╞═════════════╪══════════════════╪══════════════════╡
    │ TERM        ┆ [2.3, 5.7, 1.9]  ┆ [2.0, 5.0, 1.0]  │
    │ WHOLE       ┆ [10.4, 3.0, 7.8] ┆ [10.0, 3.0, 7.0] │
    └─────────────┴──────────────────┴──────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,))


def _round(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    decimals: int | None = 0,
    mode: str | None = "half_to_even",
) -> _BoundOperation | None:
    """Round numeric values to specified number of decimal places.

    Performs standard mathematical rounding of floating-point values to control
    precision in financial calculations, ensure regulatory compliance, and maintain
    consistent presentation standards in actuarial reporting and analysis.

    A decimal is rounded as a spreadsheet shows it: its fifteen significant
    figures are read first (a sixteenth digit of 5 or more going away from
    zero), then moved to ``decimals`` places by ``mode``. So ``2.675`` -- the
    double ``2.67499999999999982...`` -- reads as a half and is ``2.68`` at two
    places under either rule, and ``0.285`` is ``0.28`` to the even neighbour
    and ``0.29`` away from zero; with ``mode="half_away_from_zero"`` the answer
    is ``.excel.round``'s. A negative ``decimals`` rounds to tens, hundreds
    and coarser steps, as a spreadsheet's ``ROUND(x, -2)`` does: ``1234.5``
    to hundreds is ``1200.0``. A whole-number column keeps its type: it is
    already on every step at or after the point, and to tens and coarser it
    is rounded exactly in whole numbers -- ``25`` to tens is ``20`` to the
    even neighbour and ``30`` away from zero -- an answer outside the signed
    64-bit range refused by name. Values below ``10**37`` at up to 22 places
    either side of the point are rounded exactly; from ``10**37`` a double is
    whole and its own answer, and past 22 places Polars' own rounding answers,
    or past 22 places to the left the same scaling written out.

    !!! note "When to use"
        * **Financial Precision:** Round premium calculations, reserve amounts,
          or claim payments to currency-appropriate decimal places (typically 2).
        * **Regulatory Compliance:** Ensure reported figures meet regulatory
          precision requirements for filings, statutory reports, and audits.
        * **Rate Calculations:** Round mortality rates, lapse rates, or interest
          rates to standard industry precision levels for model consistency.
        * **Presentation Standards:** Standardize decimal precision for management
          reports, dashboards, and customer communications.
        * **Calculation Stability:** Control rounding errors in iterative
          calculations and ensure reproducible results across model runs.
        * **Data Export:** Prepare data for external systems with specific
          precision requirements or legacy system constraints.

    Parameters
    ----------
    decimals : int, default 0
        Number of decimal places to round to. Positive values specify decimal
        places, zero rounds to whole numbers, and a negative value rounds to a
        multiple of a power of ten: ``-1`` to tens, ``-3`` to thousands.
    mode : str or None, default "half_to_even"
        Rule for values exactly halfway between two rounded values. Use
        ``"half_to_even"`` or ``"half_away_from_zero"``. ``None`` uses the
        default ``"half_to_even"`` rule.

    Returns
    -------
    ExpressionProxy
        An expression with values rounded to the specified decimal precision.

    Examples
    --------
    **Scalar Example: Round Premium Calculations**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "calculated_premium": [1234.5678, 2567.1234, 987.9876],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["policy_id"], rounded_premium=af["calculated_premium"].round(2)
    ).collect()
    print(result)
    ```

    ```text
    shape: (3, 2)
    ┌───────────┬─────────────────┐
    │ policy_id ┆ rounded_premium │
    │ ---       ┆ ---             │
    │ str       ┆ f64             │
    ╞═══════════╪═════════════════╡
    │ P001      ┆ 1234.57         │
    │ P002      ┆ 2567.12         │
    │ P003      ┆ 987.99          │
    └───────────┴─────────────────┘
    ```

    **List Example: Round Monthly Rates with an Explicit Tie Rule**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "monthly_rate": [
            [0.01234, 0.05678, 0.0325],
            [0.0475, 0.01125, 0.09999],
        ],
    }
    af = ActuarialFrame(data)
    af.rounded_rate = af.monthly_rate.round(3, "half_away_from_zero")
    print(af.collect())
    ```

    ```text
    shape: (2, 3)
    ┌───────────┬────────────────────────────┬───────────────────────┐
    │ policy_id ┆ monthly_rate               ┆ rounded_rate          │
    │ ---       ┆ ---                        ┆ ---                   │
    │ str       ┆ list[f64]                  ┆ list[f64]             │
    ╞═══════════╪════════════════════════════╪═══════════════════════╡
    │ P001      ┆ [0.01234, 0.05678, 0.0325] ┆ [0.012, 0.057, 0.033] │
    │ P002      ┆ [0.0475, 0.01125, 0.09999] ┆ [0.048, 0.011, 0.1]   │
    └───────────┴────────────────────────────┴───────────────────────┘
    ```

    **Scalar Example: Band Sums Assured to the Nearest Thousand**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "sum_assured": [102500, 97499, 250000],
        "face_amount": [102500.0, 97499.5, 1234.5],
    }
    af = ActuarialFrame(data)
    af.sa_band = af.sum_assured.round(-3)
    af.face_band = af.face_amount.round(-2, "half_away_from_zero")
    print(af.collect())
    ```

    ```text
    shape: (3, 5)
    ┌───────────┬─────────────┬─────────────┬─────────┬───────────┐
    │ policy_id ┆ sum_assured ┆ face_amount ┆ sa_band ┆ face_band │
    │ ---       ┆ ---         ┆ ---         ┆ ---     ┆ ---       │
    │ str       ┆ i64         ┆ f64         ┆ i64     ┆ f64       │
    ╞═══════════╪═════════════╪═════════════╪═════════╪═══════════╡
    │ P001      ┆ 102500      ┆ 102500.0    ┆ 102000  ┆ 102500.0  │
    │ P002      ┆ 97499       ┆ 97499.5     ┆ 97000   ┆ 97500.0   │
    │ P003      ┆ 250000      ┆ 1234.5      ┆ 250000  ┆ 1200.0    │
    └───────────┴─────────────┴─────────────┴─────────┴───────────┘
    ```
    """
    if decimals is not None and (
        not isinstance(decimals, numbers.Integral) or isinstance(decimals, bool)
    ):
        return None
    if mode is not None and mode not in (
        "half_to_even",
        "half_away_from_zero",
    ):
        return None
    return _BoundOperation(
        args=(receiver,),
        attrs=(
            ("decimals", 0 if decimals is None else int(decimals)),
            ("mode", "half_to_even" if mode is None else str(mode)),
        ),
    )


def _cum_prod(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode", *, reverse: bool = False
) -> _BoundOperation:
    """Compute the cumulative product of numeric values.

    This operation folds periods within each policy, so the direct method
    needs a list column. A scalar column holds one value per policy;
    folding those rows is a different calculation, reached explicitly
    through ``.polars_native().cum_prod()``.

    Returns the cumulative product of all values in order, with each position
    containing the product of all values up to and including that position.
    Essential for compound interest calculations, premium accumulation, and
    mortality probability chains in actuarial modeling.

    !!! note "When to use"
        * **Compound Interest Calculations:** Calculate accumulated values where
            each period's interest compounds with previous periods.
        * **Mortality Probability Chains:** Compute survival probabilities by
            multiplying individual period survival rates sequentially.
        * **Premium Growth Factors:** Track how premiums grow when multiple
            rate increases are applied consecutively over policy years.
        * **Investment Return Accumulation:** Calculate portfolio values when
            multiple investment returns compound over time.
        * **Discount Factor Chains:** Build discount factor sequences for
            present value calculations across multiple time periods.

    Parameters
    ----------
    reverse : bool, default False
        When True, computes the cumulative product in reverse order.

    Returns
    -------
    ExpressionProxy
        An expression containing the cumulative product values.

    Examples
    --------
    **Scalar Example: Interest Rate Accumulation**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "year": [1, 2, 3, 4],
        "interest_rate": [1.03, 1.025, 1.04, 1.035],
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["year"],
        af["interest_rate"],
        cumulative_factor=af["interest_rate"].polars_native().cum_prod(),
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 3)
    ┌──────┬───────────────┬───────────────────┐
    │ year ┆ interest_rate ┆ cumulative_factor │
    │ ---  ┆ ---           ┆ ---               │
    │ i64  ┆ f64           ┆ f64               │
    ╞══════╪═══════════════╪═══════════════════╡
    │ 1    ┆ 1.03          ┆ 1.03              │
    │ 2    ┆ 1.025         ┆ 1.05575           │
    │ 3    ┆ 1.04          ┆ 1.09798           │
    │ 4    ┆ 1.035         ┆ 1.1364093         │
    └──────┴───────────────┴───────────────────┘
    ```

    **Vector Example: Survival Probability Chains**

    ```python
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002"],
        "age": [55, 38],
        "month": [
            [1, 2, 3, 4],
            [1, 2, 3, 4]
        ],
        "monthly_survival_rate": [
            [0.9995, 0.9994, 0.9993, 0.9992],
            [0.9998, 0.9998, 0.9997, 0.9997]
        ]
    }
    af = ActuarialFrame(data)

    af["cumulative_survival"] = af["monthly_survival_rate"].cum_prod()

    print(af.select("policy_id", "cumulative_survival").collect())
    ```

    ```text
    shape: (2, 2)
    ┌───────────┬─────────────────────────────────┐
    │ policy_id ┆ cumulative_survival             │
    │ ---       ┆ ---                             │
    │ str       ┆ list[f64]                       │
    ╞═══════════╪═════════════════════════════════╡
    │ P001      ┆ [0.9995, 0.9989003, … 0.997403] │
    │ P002      ┆ [0.9998, 0.9996, … 0.999]       │
    └───────────┴─────────────────────────────────┘
    ```
    """
    return _BoundOperation(args=(receiver,), attrs=(("reverse", bool(reverse)),))


def _cum_sum(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode", *, reverse: bool = False
) -> _BoundOperation:
    """Compute the cumulative sum of numeric values.

    This operation folds periods within each policy, so the direct method
    needs a list column. A scalar column holds one value per policy;
    folding those rows is a different calculation, reached explicitly
    through ``.polars_native().cum_sum()``.

    Returns the cumulative sum of all values in order, with each position
    containing the sum of all values up to and including that position.
    Essential for cumulative premium calculations, cumulative claims, and
    running balance projections in actuarial modeling.

    !!! note "When to use"
        * **Cumulative Premiums:** Calculate total premiums paid up to each
            period for persistency analysis or surrender value calculations.
        * **Cumulative Claims:** Track total claim amounts over time for
            loss development and reserving.
        * **Running Balances:** Compute cumulative deposits or withdrawals
            for account balance projections.

    Parameters
    ----------
    reverse : bool, default False
        If True, compute the cumulative sum from the last period to the first.

    Returns
    -------
        ExpressionProxy with the cumulative sum applied.

    Examples
    --------
    **Scalar Example: An Ordered Premium Ledger**

    ```python
    from gaspatchio import ActuarialFrame

    ledger = ActuarialFrame({"premium": [100, 100, 150]})
    ledger.paid_so_far = ledger.premium.polars_native().cum_sum()
    print(ledger.collect()["paid_so_far"].to_list())
    ```

    ```text
    [100, 200, 350]
    ```

    **Vector Example: Paid and Remaining Premiums by Policy**

    ```python
    from gaspatchio import ActuarialFrame

    policies = ActuarialFrame({
        "monthly_premium": [[100, 100, 150], [50, 75]],
    })
    policies.paid_so_far = policies.monthly_premium.cum_sum()
    policies.still_to_come = policies.monthly_premium.cum_sum(reverse=True)
    result = policies.collect()
    print(result["paid_so_far"].to_list())
    print(result["still_to_come"].to_list())
    ```

    ```text
    [[100, 200, 350], [50, 125]]
    [[350, 250, 150], [125, 75]]
    ```
    """
    return _BoundOperation(args=(receiver,), attrs=(("reverse", bool(reverse)),))


# --- direct method operations ------------------------------------------------


def _members(value: object) -> tuple[object, ...] | None:
    """Return a non-empty list or tuple's members, or ``None``."""
    if not isinstance(value, (list, tuple)) or not value:
        return None
    return tuple(value)


def _numbers(value: object) -> tuple[object, ...] | None:
    """Return a written-out sequence containing only non-Boolean numbers."""
    members = _members(value)
    if members is None:
        return None
    if all(
        isinstance(member, numbers.Real) and not isinstance(member, bool)
        for member in members
    ):
        return members
    return None


def _text(value: object) -> tuple[object, ...] | None:
    """Return a written-out sequence containing only text labels."""
    members = _members(value)
    if members is None or not all(isinstance(member, str) for member in members):
        return None
    return members


def _scalars(value: object) -> tuple[object, ...] | None:
    """Return a written-out sequence of scalar values."""
    members = _members(value)
    if members is None or not all(
        isinstance(member, (bool, int, float, str)) for member in members
    ):
        return None
    return members


def _clip(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    lower_bound: object | None = None,
    upper_bound: object | None = None,
) -> _BoundOperation | None:
    """Constrain values to specified minimum and maximum bounds.

    Limits values to a specified range by setting any value below the lower bound
    to the lower bound and any value above the upper bound to the upper bound.
    Essential for risk management, regulatory compliance, and data standardization
    in actuarial analysis. At least one bound must be supplied.

    !!! note "When to use"
        * **Risk Limits:** Enforce maximum exposure limits, claim caps, or
          minimum reserve requirements for regulatory compliance.
        * **Data Standardization:** Constrain outliers to reasonable ranges
          for statistical analysis and model development.
        * **Premium Bounds:** Apply minimum and maximum premium limits based
          on underwriting guidelines or regulatory requirements.
        * **Age Restrictions:** Enforce age eligibility ranges for specific
          products, benefits, or pricing tables.

    Parameters
    ----------
    lower_bound : object, optional
        The minimum value allowed. Values below it take this value.
    upper_bound : object, optional
        The maximum value allowed. Values above it take this value.

    Returns
    -------
    ExpressionProxy
        An expression with values constrained to the specified bounds.

    Examples
    --------
    **Scalar Example: Age Eligibility Bounds**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"age": [16, 35, 85]})
    af.eligible_age = af.age.clip(18, 65)
    print(af.collect()["eligible_age"].to_list())
    ```

    ```text
    [18, 35, 65]
    ```

    **List Example: Claim Limits by Period**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"claim": [[5000.0, 25000.0, 150000.0]]})
    af.capped_claim = af.claim.clip(10000.0, 100000.0)
    print(af.collect()["capped_claim"].to_list())
    ```

    ```text
    [[10000.0, 25000.0, 100000.0]]
    ```
    """
    given = tuple(bound for bound in (lower_bound, upper_bound) if bound is not None)
    if not given:
        return None
    bounds = {
        (True, True): "both",
        (True, False): "lower",
        (False, True): "upper",
    }[(lower_bound is not None, upper_bound is not None)]
    return _BoundOperation(
        args=(receiver,), operands=given, attrs=(("bounds", bounds),)
    )


def _is_in(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    other: object,
    nulls_equal: bool | None = False,  # noqa: FBT001, FBT002 - positional form owned
) -> _BoundOperation | None:
    """Test whether each value belongs to a set written in the formula.

    Use this for product groups, eligibility codes, and other membership tests.
    A list or tuple is recorded literally; a column or expression is recorded as
    an operand. Use ``.polars_native().is_in(...)`` for an engine-specific form.

    !!! note "When to use"
        * **Product Groups:** Mark policies whose product code belongs to an
          explicitly stated eligibility set.
        * **Projection Status:** Test period statuses against the states that
          remain in force.

    Parameters
    ----------
    other : object
        The values, column, or expression to test membership against.
    nulls_equal : bool, optional
        Whether a null is a member when the set also contains null.

    Returns
    -------
    ExpressionProxy
        One Boolean for each input value.

    Examples
    --------
    **Scalar Example: Product Eligibility**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"product": ["TERM", "WL", "UL"]})
    af.eligible = af["product"].is_in(["TERM", "WL"])
    print(af.collect()["eligible"].to_list())
    ```

    ```text
    [True, True, False]
    ```

    **List Example: Period Statuses**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"status": [["ACTIVE", "PAID", "LAPSED"]]})
    af.in_force = af.status.is_in(["ACTIVE", "PAID"])
    print(af.collect()["in_force"].to_list())
    ```

    ```text
    [[True, True, False]]
    ```
    """
    written = _scalars(other)
    operand = _LiteralOperand(written) if written is not None else other
    return _BoundOperation(
        args=(receiver,),
        operands=(operand,),
        attrs=(("nulls_equal", bool(nulls_equal)),),
    )


def _a_point_on_the_line(value: object) -> bool:
    """Return whether a breakpoint is a finite point on the number line."""
    return isinstance(value, numbers.Real) and math.isfinite(float(value))


def _refuse_a_band_whose_breakpoints_do_not_run_up_the_line(
    break_values: tuple[object, ...],
) -> None:
    """Refuse labelled breakpoints that would silently mislabel intervals."""
    for lower, upper in pairwise(break_values):
        if not _a_point_on_the_line(lower) or not _a_point_on_the_line(upper):
            continue
        if not lower < upper:  # type: ignore[operator]
            written = ", ".join(str(value) for value in break_values)
            msg = (
                f"A band's breakpoints run up the line they cut, and "
                f"[{written}] does not: {upper} does not sit above {lower}. "
                f"Out of order and all different, the labels are what makes "
                f"that dangerous: where every breakpoint is finite and the "
                f"labels are one per interval and all different, the engine "
                f"puts the intervals in order and leaves the labels in the "
                f"order they were written, so bands are reported under other "
                f"bands' names -- a life aged 25 filed as 'over 50' -- and "
                f"nothing anywhere says so. Repeated, a breakpoint names an "
                f"interval no life can fall in, and the engine refuses that "
                f"band too -- but only when the frame is collected, a run "
                f"away from the line that wrote it; this refusal is at the "
                f"line. Write the breakpoints from lowest to highest, each "
                f"above the last, with the labels beside them in that same "
                f"order."
            )
            raise ValueError(msg)


def _refuse_a_band_whose_labels_do_not_name_its_intervals(
    break_values: tuple[object, ...], label_values: tuple[object, ...]
) -> None:
    """Refuse a label count that cannot name every interval exactly once."""
    wanted = len(break_values) + 1
    if len(label_values) != wanted:
        msg = (
            f"A band's labels name the intervals its breakpoints cut the "
            f"line into: {len(break_values)} breakpoints cut it into "
            f"{wanted} -- the one below the first breakpoint, one between "
            f"each pair, and the one above the last -- and "
            f"{len(label_values)} labels were written for them. The engine "
            f"refuses the pair when the frame is collected, a long way from "
            f"the line that wrote it. Name every interval, the open one at "
            f"each end included."
        )
        raise ValueError(msg)


def _cut(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    breaks: object,
    labels: object | None = None,
    left_closed: bool | None = False,  # noqa: FBT001, FBT002 - positional form owned
    include_breaks: bool | None = False,  # noqa: FBT001, FBT002 - positional form owned
) -> _BoundOperation | None:
    """Place each value into an interval defined by written breakpoints.

    Breakpoints must be a non-empty list or tuple of numbers. Optional labels
    name the intervals in ascending breakpoint order. Labelled breakpoints that
    could silently attach the wrong label are refused at the model line.

    The band is an ordered category, and the calculation graph's type
    vocabulary has no name for one, so a column holding a bare band cannot
    be exported: the export refuses it, naming the column. A band reaches the
    record as text, ``.to_text()``, which carries every label unchanged, or
    through a comparison against a label. Write the column that way when it is
    one the model keeps.

    !!! note "When to use"
        * **Age Bands:** Assign each policy to a stated underwriting interval.
        * **Ratio Bands:** Name projection-period ratios by materiality range.

    Parameters
    ----------
    breaks : object
        A list or tuple of numeric breakpoints.
    labels : object, optional
        One text label for each interval.
    left_closed : bool, optional
        Close each interval on the left instead of the right.
    include_breaks : bool, optional
        Include a struct field containing the breakpoint used.

    Returns
    -------
    ExpressionProxy
        The interval or label assigned to each value, as an ordered category;
        ``.to_text()`` turns it into the text the record can carry.

    Examples
    --------
    **Scalar Example: Age Bands**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"age": [25, 45, 65]})
    af.band = af.age.cut([30.0, 50.0], labels=["young", "mid", "old"]).to_text()
    print(af.collect()["band"].to_list())
    ```

    ```text
    ['young', 'mid', 'old']
    ```

    **List Example: Period Bands**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"ratio": [[0.5, 1.2, 2.1]]})
    af.band = af.ratio.cut([1.0, 2.0], labels=["low", "mid", "high"]).to_text()
    print(af.collect()["band"].to_list())
    ```

    ```text
    [['low', 'mid', 'high']]
    ```
    """
    break_values = _numbers(breaks)
    if break_values is None:
        return None
    if labels is not None:
        _refuse_a_band_whose_breakpoints_do_not_run_up_the_line(break_values)
    label_values = None if labels is None else _text(labels)
    if labels is not None and label_values is None:
        return None
    if label_values is not None:
        _refuse_a_band_whose_labels_do_not_name_its_intervals(
            break_values, label_values
        )
    operands = (
        (_LiteralOperand(break_values),)
        if label_values is None
        else (_LiteralOperand(break_values), _LiteralOperand(label_values))
    )
    return _BoundOperation(
        args=(receiver,),
        operands=operands,
        attrs=(
            ("left_closed", bool(left_closed)),
            ("include_breaks", bool(include_breaks)),
        ),
    )


def _where_a_value_sorts(value: object) -> tuple[str, str]:
    """Return a stable total ordering key for one substitution value."""
    return (str(value), type(value).__name__)


def _canonical(
    keys: tuple[object, ...], values: tuple[object, ...]
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """Return a substitution's two sides in one deterministic order."""
    pairs = sorted(
        zip(keys, values, strict=True),
        key=lambda pair: (
            *_where_a_value_sorts(pair[0]),
            *_where_a_value_sorts(pair[1]),
        ),
    )
    return (
        tuple(key for key, _ in pairs),
        tuple(value for _, value in pairs),
    )


def _substitution(old: object, new: object) -> tuple[tuple[object, ...], object] | None:
    """Return a substitution's canonical old and new sides, or decline it.

    One value and its replacement, ``replace("IF", "INFORCE")``, is the
    one-entry mapping ``{"IF": "INFORCE"}``, and is read as that mapping:
    the two spellings are one calculation and one record.
    """
    scalar = (bool, int, float, str)
    if isinstance(old, scalar) and isinstance(new, scalar):
        old, new = {old: new}, None
    if isinstance(old, dict):
        if new is not None:
            return None
        keys = _scalars(list(old))
        values = _scalars(list(old.values()))
        return None if keys is None or values is None else _canonical(keys, values)
    keys = _scalars(old)
    if keys is None:
        return None
    if isinstance(new, (bool, int, float, str)):
        return tuple(sorted(keys, key=_where_a_value_sorts)), new
    values = _scalars(new)
    if values is None or len(values) != len(keys):
        return None
    return _canonical(keys, values)


def _replace(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    old: object,
    new: object | None = None,
    default: object | None = None,
    return_dtype: object | None = None,
) -> _BoundOperation | None:
    """Substitute written values one for one, leaving other values unchanged.

    A mapping, equivalent old/new sequences and a single old/new pair
    (``replace("IF", "INFORCE")``, the one-entry mapping it means) produce the
    same canonical record. A single replacement value may stand for every old
    value. Engine-specific unmatched defaults and return dtypes use
    ``.polars_native().replace(...)``, which records the line as engine_native.

    !!! note "When to use"
        * **Code Translation:** Replace source-system product codes with the
          model's stable terminology.
        * **Status Translation:** Name projection status codes consistently
          across each policy timeline.

    Parameters
    ----------
    old : object
        A mapping, a non-empty list or tuple of values to replace, or one value
        to replace with ``new``.
    new : object, optional
        Corresponding replacement values, or one value used for every old value.
    default : object, optional
        Unsupported on the portable operation; use the explicit engine escape.
    return_dtype : object, optional
        Unsupported on the portable operation; use the explicit engine escape.

    Returns
    -------
    ExpressionProxy
        Values after applying the substitution.

    Examples
    --------
    **Scalar Example: Product Codes**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"code": ["A", "B", "C"]})
    af.basis = af.code.replace({"A": "TERM", "B": "WL"})
    print(af.collect()["basis"].to_list())
    ```

    ```text
    ['TERM', 'WL', 'C']
    ```

    **List Example: Period Status Codes**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"status": [["A", "P", "L"]]})
    af.named_status = af.status.replace(["A", "P"], ["active", "paid"])
    print(af.collect()["named_status"].to_list())
    ```

    ```text
    [['active', 'paid', 'L']]
    ```
    """
    if default is not None or return_dtype is not None:
        return None
    pairs = _substitution(old, new)
    if pairs is None:
        return None
    old_values, new_values = pairs
    return _BoundOperation(
        args=(receiver,),
        operands=(
            _LiteralOperand(old_values),
            (
                _LiteralOperand(new_values)
                if isinstance(new_values, tuple)
                else new_values
            ),
        ),
    )


def _fill_null(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    value: object | None = None,
    strategy: str | None = None,
    limit: int | None = None,
) -> _BoundOperation | None:
    """Replace missing values with a stated value or column.

    The direct operation records the fill as an operand, so a scheme-specific
    default column is as auditable as a fixed zero. Row-order strategies and
    fill limits are different calculations; write those explicitly through
    ``.polars_native().fill_null(...)``.

    !!! note "When to use"
        * **Data Imputation:** Replace missing claims, premiums, or rates with
          a stated value that the model can audit.
        * **Scheme Defaults:** Fill one column from another policy attribute.
        * **Projection Gaps:** Fill missing periods with a scalar value.

    Parameters
    ----------
    value : object, optional
        The scalar, column, or expression used where the receiver is null.
    strategy : str, optional
        An engine-specific row strategy, available through ``polars_native``.
    limit : int, optional
        An engine-specific strategy limit, available through ``polars_native``.

    Returns
    -------
    ExpressionProxy
        Values with nulls replaced by the stated operand.

    Examples
    --------
    **Scalar Example: Missing Claims**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"claim": [1200.0, None, 2800.0]})
    af.claim_filled = af.claim.fill_null(0.0)
    print(af.collect()["claim_filled"].to_list())
    ```

    ```text
    [1200.0, 0.0, 2800.0]
    ```

    **List Example: Missing Premium Periods**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"premium": [[100.0, None, 150.0]]})
    af.premium_filled = af.premium.fill_null(0.0)
    print(af.collect()["premium_filled"].to_list())
    ```

    ```text
    [[100.0, 0.0, 150.0]]
    ```
    """
    if value is None or strategy is not None or limit is not None:
        return None
    return _BoundOperation(args=(receiver,), operands=(value,))


def _fill_nan(  # noqa: D417 - receiver is internal, not public documentation
    receiver: "OpNode",
    value: object | None,
) -> _BoundOperation | None:
    """Replace NaN values with a stated value or column.

    A NaN is a number an arithmetic produced and cannot name -- zero over
    zero, an assumption cell a spreadsheet left blank -- and it is a
    different absence from a null. This replaces the NaN and leaves a null
    as it is; ``fill_null`` is the operation for a value that was never
    there. The fill is recorded as an operand, so a fill read from a column
    is as auditable as a fixed zero, and a table read followed by its fill
    is one line whose record names the table.

    !!! note "When to use"
        * **Assumption Table Gaps:** Zero the NaN a lookup built with
          ``on_missing="nan"`` answers for a cell its source left blank, on
          the same line as the lookup.
        * **Undefined Ratios:** Replace the NaN a zero-over-zero ratio
          produces with the value the model means there.
        * **Projection Periods:** Fill NaN periods of a per-period rate
          with a stated value or with another column, period for period.

    Over a whole-number column there is no NaN to replace and every value
    is returned as it stands. A Boolean, text or date column cannot hold a
    NaN and is refused.

    Parameters
    ----------
    value : object
        The scalar, column, or expression used where the receiver is NaN.
        ``None`` is not a declared fill; turning a NaN into a null is
        written through ``.polars_native().fill_nan(None)``.

    Returns
    -------
    ExpressionProxy
        Values with NaN replaced by the stated operand and nulls unchanged.

    Examples
    --------
    **Scalar Example: A Blank Assumption Cell**

    ```python
    import polars as pl

    from gaspatchio import ActuarialFrame
    from gaspatchio.assumptions import Table

    lapse = Table(
        name="lapse",
        source=pl.DataFrame(
            {"duration": [1, 2, 3], "rate": [0.08, float("nan"), 0.04]}
        ),
        dimensions={"duration": "duration"},
        value="rate",
        on_missing="nan",
    )
    af = ActuarialFrame({"duration": [1, 2, 3]})
    af.lapse_rate = lapse.lookup(duration=af.duration).fill_nan(0.0)
    print(af.collect()["lapse_rate"].to_list())
    ```

    ```text
    [0.08, 0.0, 0.04]
    ```

    **List Example: NaN Periods, Nulls Kept**

    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"loss_ratio": [[0.6, float("nan"), None, 0.7]]})
    af.loss_ratio_filled = af.loss_ratio.fill_nan(0.0)
    print(af.collect()["loss_ratio_filled"].to_list())
    ```

    ```text
    [[0.6, 0.0, None, 0.7]]
    ```
    """
    if value is None:
        return None
    return _BoundOperation(args=(receiver,), operands=(value,))


def _to_integer(receiver: "OpNode") -> _BoundOperation:
    """Convert whole numeric values to signed 64-bit integers, or refuse.

    !!! note "When to use"
        Convert an already whole duration or rebase position before selecting
        a period. Write floor(), ceil() or round() first when rounding is intended.

    The conversion accepts signed integer values directly. Floating-point
    values must be present, finite, mathematically integral, and in the
    half-open signed 64-bit interval ``[-2**63, 2**63)``. The same check is
    applied to every element of a per-period list; a missing list, value, or
    element is an error.

    Boolean, unsigned integer, text and date values are not numeric inputs to
    this operation. An empty non-null list stays empty. No value is rounded,
    truncated or replaced with null to make the conversion succeed.

    Returns
    -------
    ExpressionProxy
        Signed 64-bit integer values on the receiver's existing shape.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"duration": [0.0, 12.0, 24.0]})
    af.duration_months = af.duration.to_integer()
    print(af.collect()["duration_months"].to_list())
    ```

    ```text
    [0, 12, 24]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _to_float(receiver: "OpNode") -> _BoundOperation:
    """Widen a whole number into a double, or refuse the one no double names.

    !!! note "When to use"
        Put a counted quantity -- units held, lives in force -- on the same
        footing as the rates it is about to be multiplied by.

    The conversion accepts an integer of any storage width and any
    floating-point value. A floating-point value comes back as the double it
    already is. An integer is exact where it lies in ``[-2**53, 2**53]``; one
    outside that interval refuses the whole invocation rather than arriving
    as the nearest double and reading equal to its neighbour. A null stays
    null, on a scalar and at every period of a list. An empty non-null list
    stays empty.

    Boolean, text and date values are not quantities and are refused by name.

    Returns
    -------
    ExpressionProxy
        Double-precision values on the receiver's existing shape.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"units": [12, 30]})
    af.units_held = af.units.to_float()
    print(af.collect()["units_held"].to_list())
    ```

    ```text
    [12.0, 30.0]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _to_list(receiver: "OpNode") -> _BoundOperation:
    """Unpin a fixed-width array's length, keeping its elements, or refuse.

    !!! note "When to use"
        Read a quarterly charge vector or a fixed-length rate run that a
        parquet file stored as an array, so the projection can hold it.

    The conversion accepts a fixed-width array whose element type this
    vocabulary names -- a boolean, an integer, a floating-point value, text,
    a date or a datetime. It answers a list of the same elements in the same
    order, with the element type unchanged; the fixed length is the only
    thing given up. A null element stays null, and a null array stays null.

    A column that is already a list is refused rather than passed through,
    so the node means one thing wherever a reviewer reads it. So is a value
    that is not a run of elements at all, and an array whose element type
    has no name here.

    Returns
    -------
    ExpressionProxy
        A list of the array's own elements, one per policy.

    Examples
    --------
    ```python
    import polars as pl

    from gaspatchio import ActuarialFrame

    charges = pl.Series("charges", [[1.5, 2.5]], dtype=pl.Array(pl.Float64, 2))
    af = ActuarialFrame(pl.DataFrame({"charges": charges}))
    af.charge_run = af.charges.to_list()
    print(af.collect()["charge_run"].to_list())
    ```

    ```text
    [[1.5, 2.5]]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _to_text(receiver: "OpNode") -> _BoundOperation:
    """Carry a value into text with every digit kept, or refuse.

    !!! note "When to use"
        Hold a policy number or scheme identifier whose digits run past what
        a signed 64-bit integer names, so the audit export carries it whole.

    The conversion accepts a boolean, an integer of any storage width, a
    floating-point value, text, a date, a datetime, a category, and a list of
    any of those. It answers the value written out: an integer by its digits,
    a floating-point value by the shortest decimal that reads back to the
    same number at its own width, a boolean as ``true`` or ``false``, a date
    as ISO ``YYYY-MM-DD``, and text and categories unchanged. A null stays
    null, on a scalar and at every period of a list.

    A duration, a decimal, a time of day, a binary value and a fixed-width
    array are refused by name: each would have to be written out under a
    convention the model never stated.

    Returns
    -------
    ExpressionProxy
        Text on the receiver's existing shape.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"policy_number": [10123, 10124]})
    af.policy_reference = af.policy_number.to_text()
    print(af.collect()["policy_reference"].to_list())
    ```

    ```text
    ['10123', '10124']
    ```
    """
    return _BoundOperation(args=(receiver,))


# The order is the generated source order.  Each identifier is written once;
# every consumer derives its name map or lowering registrations from this tuple.
PLAIN_MATH_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("abs", _abs),
    ProxyOperation("sign", _sign),
    ProxyOperation("round_sig_figs", _round_sig_figs),
    ProxyOperation("exp", _exp),
    ProxyOperation("log", _log),
    ProxyOperation("log1p", _log1p),
    ProxyOperation("log10", _log10),
    ProxyOperation("sqrt", _sqrt),
    ProxyOperation("cbrt", _cbrt),
    ProxyOperation("norm_cdf", _norm_cdf),
)

ABSENCE_PREDICATE_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("is_finite", _is_finite),
    ProxyOperation("is_infinite", _is_infinite),
    ProxyOperation("is_nan", _is_nan),
    ProxyOperation("is_not_nan", _is_not_nan),
    ProxyOperation("is_not_null", _is_not_null),
    ProxyOperation("is_null", _is_null),
)

ROUNDING_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("ceil", _ceil),
    ProxyOperation("floor", _floor),
    ProxyOperation("round", _round),
)

ACCUMULATION_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("cum_prod", _cum_prod),
    ProxyOperation("cum_sum", _cum_sum),
)

DIRECT_CALL_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("clip", _clip),
    ProxyOperation("cut", _cut),
    ProxyOperation("fill_nan", _fill_nan),
    ProxyOperation("fill_null", _fill_null),
    ProxyOperation("is_in", _is_in),
    ProxyOperation("replace", _replace),
    ProxyOperation("to_float", _to_float),
    ProxyOperation("to_integer", _to_integer),
    ProxyOperation("to_list", _to_list),
    ProxyOperation("to_text", _to_text),
)

GENERATED_PROXY_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    *PLAIN_MATH_OPERATIONS,
    *ABSENCE_PREDICATE_OPERATIONS,
    *ROUNDING_OPERATIONS,
    *ACCUMULATION_OPERATIONS,
    *DIRECT_CALL_OPERATIONS,
)

PROXY_OPERATIONS: Final[dict[str, ProxyOperation]] = {
    operation.identifier: operation for operation in GENERATED_PROXY_OPERATIONS
}
if len(PROXY_OPERATIONS) != len(GENERATED_PROXY_OPERATIONS):
    _message = "Two proxy operation declarations use the same identifier"
    raise RuntimeError(_message)

ROUND_SIG_FIGS_OPERATION: Final[ProxyOperation] = next(
    operation
    for operation in PLAIN_MATH_OPERATIONS
    if operation.binder is _round_sig_figs
)
NORM_CDF_OPERATION: Final[ProxyOperation] = next(
    operation for operation in PLAIN_MATH_OPERATIONS if operation.binder is _norm_cdf
)
ROUND_OPERATION: Final[ProxyOperation] = next(
    operation for operation in ROUNDING_OPERATIONS if operation.binder is _round
)
CLIP_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _clip
)
CUT_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _cut
)
FILL_NAN_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _fill_nan
)
FILL_NULL_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _fill_null
)
IS_IN_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _is_in
)
REPLACE_OPERATION: Final[ProxyOperation] = next(
    operation for operation in DIRECT_CALL_OPERATIONS if operation.binder is _replace
)


@dataclass(frozen=True, slots=True)
class BinaryOperation:
    """An operator identifier and the ordinary Python spellings it exposes."""

    identifier: "BinOpKind"
    method: str
    symbol: str
    family: Literal["arithmetic", "comparison", "logical"]


BINARY_OPERATIONS: Final[tuple[BinaryOperation, ...]] = (
    BinaryOperation("add", "add", "+", "arithmetic"),
    BinaryOperation("sub", "sub", "-", "arithmetic"),
    BinaryOperation("mul", "mul", "*", "arithmetic"),
    BinaryOperation("div", "truediv", "/", "arithmetic"),
    BinaryOperation("floordiv", "floordiv", "//", "arithmetic"),
    BinaryOperation("mod", "mod", "%", "arithmetic"),
    BinaryOperation("pow", "pow", "**", "arithmetic"),
    BinaryOperation("eq", "eq", "==", "comparison"),
    BinaryOperation("ne", "ne", "!=", "comparison"),
    BinaryOperation("lt", "lt", "<", "comparison"),
    BinaryOperation("le", "le", "<=", "comparison"),
    BinaryOperation("gt", "gt", ">", "comparison"),
    BinaryOperation("ge", "ge", ">=", "comparison"),
    BinaryOperation("and", "and", "&", "logical"),
    BinaryOperation("or", "or", "|", "logical"),
)


@dataclass(frozen=True, slots=True)
class ProxyOperator:
    """One public spelling of an existing unary or binary operation."""

    name: str
    operation: BinaryOperation | None = None
    unary: Literal["absolute", "negative", "not"] | None = None
    reflected: bool = False
    signature: inspect.Signature = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Build the spelling's signature without consulting an execution engine."""
        parameter = "exponent" if self.name == "pow" else "other"
        parameters = (
            []
            if self.operation is None
            else [
                inspect.Parameter(
                    parameter,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=object,
                )
            ]
        )
        object.__setattr__(self, "signature", inspect.Signature(parameters))

    @property
    def documentation(self) -> str:
        """Describe the formula and give a small independently checkable example."""
        if self.name == "pow":
            return _POWER_DOCUMENTATION
        boolean = self.unary == "not" or (
            self.operation is not None and self.operation.family == "logical"
        )
        values = [True, False] if boolean else [4, 8]
        other = (
            True
            if boolean
            else 6
            if (self.operation is not None and self.operation.family == "comparison")
            else 2
        )
        column = "in_force" if boolean else "amount"
        if self.operation is not None:
            op = self.operation
            apply = getattr(
                operator, op.method + "_" if op.family == "logical" else op.method
            )
            expected = [
                apply(other, value) if self.reflected else apply(value, other)
                for value in values
            ]
            if op.family == "comparison":
                expected = [float(value) for value in expected]
            formula = (
                f"{other!r} {op.symbol} af.{column}"
                if self.reflected
                else f"af.{column} {op.symbol} {other!r}"
            )
            if not self.name.startswith("__"):
                formula = f"af.{column}.{self.name}({other!r})"
            formula = formula.replace(" ** ", "**")
            purpose = f"Apply {op.symbol} to policy values."
        elif self.unary == "absolute":
            values = [-4, 8]
            expected = [4, 8]
            formula = "abs(af.amount)"
            purpose = "Take the magnitude of a policy amount."
        elif self.unary == "negative":
            expected = [-4, -8]
            formula = "af.amount.neg()" if self.name == "neg" else "-af.amount"
            purpose = "Reverse the sign of a policy amount."
        else:
            expected = [False, True]
            formula = "~af.in_force"
            purpose = "Negate a Boolean value or a predicate mask."
        return f"""{purpose}

!!! note "When to use"
    Combine cashflows, compare policy attributes, or combine Boolean eligibility
    conditions in the formula itself. Logical operators take Boolean values,
    predicate masks, or a stored Float64 column holding exactly 0.0 or 1.0;
    use an explicit comparison for any other numeric flag.

Examples
--------
```python
from gaspatchio import ActuarialFrame

af = ActuarialFrame({{"{column}": {values!r}}})
af.result = {formula}
print(af.collect()["result"].to_list())
```

```text
{expected!r}
```
"""


GENERATED_OPERATOR_SPELLINGS: Final[tuple[ProxyOperator, ...]] = (
    *(
        spelling
        for operation in BINARY_OPERATIONS
        for spelling in (
            (ProxyOperator(operation.method, operation),)
            if operation.family != "logical"
            else ()
        )
        + (ProxyOperator(f"__{operation.method}__", operation),)
        + (
            (ProxyOperator(f"__r{operation.method}__", operation, reflected=True),)
            if operation.family != "comparison"
            else ()
        )
    ),
    ProxyOperator("__abs__", unary="absolute"),
    ProxyOperator("__neg__", unary="negative"),
    ProxyOperator("neg", unary="negative"),
    ProxyOperator("__invert__", unary="not"),
)
PROXY_OPERATORS: Final[dict[str, ProxyOperator]] = {
    spelling.name: spelling for spelling in GENERATED_OPERATOR_SPELLINGS
}


def _to_date(  # noqa: D417 - receiver is internal
    receiver: "OpNode",
    format: str | None = None,  # noqa: A002 - public spelling
    strict: bool | None = True,  # noqa: FBT001, FBT002 - owned positional form
    exact: bool | None = True,  # noqa: FBT001, FBT002 - owned positional form
    cache: bool | None = True,  # noqa: FBT001, FBT002 - owned positional form
) -> _BoundOperation | None:
    """Read policy dates from text, including one list of dates per policy.

    !!! note "When to use"
        Parse issue dates or claim dates before calculating durations.
        State the format when its meaning is known; ambiguous text should
        not silently choose a date convention.

    Parameters
    ----------
    format : str, optional
        Date format such as ``%Y-%m-%d``; omitted to infer it.
    strict : bool, optional
        Refuse dates that cannot be parsed; False produces nulls for them.
    exact : bool, optional
        Require the format to match the whole string.
    cache : bool, optional
        Reuse repeated parses. This affects execution, not the dates returned.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"issue_date": ["2025-01-31", "2025-02-28"]})
    af.parsed = af.issue_date.str.to_date("%Y-%m-%d")
    print([date.isoformat() for date in af.collect()["parsed"].to_list()])
    claims = [["2025-01-31"], ["2025-02-28", "2025-03-31"]]
    af = ActuarialFrame({"claim_dates": claims})
    af.parsed = af.claim_dates.str.to_date("%Y-%m-%d")
    parsed = af.collect()["parsed"].to_list()
    print([[date.isoformat() for date in dates] for dates in parsed])
    ```

    ```text
    ['2025-01-31', '2025-02-28']
    [['2025-01-31'], ['2025-02-28', '2025-03-31']]
    ```
    """
    del cache  # Memoisation changes execution cost, never operation identity.
    if format is not None and not isinstance(format, str):
        return None
    return _BoundOperation(
        args=(receiver,),
        attrs=(
            ("format", format),
            ("strict", True if strict is None else bool(strict)),
            ("exact", True if exact is None else bool(exact)),
        ),
    )


def _list_max(receiver: "OpNode") -> _BoundOperation:
    """Take the max of each policy's own projection periods.

    !!! note "When to use"
        Report the peak a policy reaches -- the largest reserve it ever
        holds, the heaviest month of its cashflow.

    A null period makes the answer null. A modeller who means nought writes
    ``af.col.fill_null(0.0)`` before the total, and the graph then records
    that they said so.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"reserve": [[120.0, 260.0, 180.0], [40.0]]})
    af.peak_reserve = af.reserve.list.max()
    print(af.collect()["peak_reserve"].to_list())
    ```

    ```text
    [260.0, 40.0]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _list_mean(receiver: "OpNode") -> _BoundOperation:
    """Take the mean of each policy's own projection periods.

    !!! note "When to use"
        Report an average per-period amount -- the typical monthly
        expense a policy carries -- over however many periods it has.

    A null period makes the answer null. A modeller who means nought writes
    ``af.col.fill_null(0.0)`` before the total, and the graph then records
    that they said so.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"expense": [[12.0, 14.0, 16.0], [9.0]]})
    af.average_expense = af.expense.list.mean()
    print(af.collect()["average_expense"].to_list())
    ```

    ```text
    [14.0, 9.0]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _list_min(receiver: "OpNode") -> _BoundOperation:
    """Take the min of each policy's own projection periods.

    !!! note "When to use"
        Report the worst period a policy sees -- the deepest negative
        net cashflow, the lowest its account value ever falls to.

    A null period makes the answer null. A modeller who means nought writes
    ``af.col.fill_null(0.0)`` before the total, and the graph then records
    that they said so.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"net_cashflow": [[5.0, -3.0, 8.0], [2.0]]})
    af.worst_period = af.net_cashflow.list.min()
    print(af.collect()["worst_period"].to_list())
    ```

    ```text
    [-3.0, 2.0]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _list_sum(receiver: "OpNode") -> _BoundOperation:
    """Take the sum of each policy's own projection periods.

    !!! note "When to use"
        Add a whole discounted cashflow up into one number -- the
        present value a policy contributes to the liability.

    A null period makes the total null. A modeller who means nought writes
    ``af.col.fill_null(0.0)`` before the total, and the graph then records
    that they said so.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"discounted_cashflow": [[100.0, 95.0, 90.0], [50.0]]})
    af.present_value = af.discounted_cashflow.list.sum()
    print(af.collect()["present_value"].to_list())
    ```

    ```text
    [285.0, 50.0]
    ```
    """
    return _BoundOperation(args=(receiver,))


def _list_get(  # noqa: D417 - receiver is internal
    receiver: "OpNode",
    index: object,
) -> _BoundOperation | None:
    """Select one position from each policy's projection values.

    !!! note "When to use"
        Read an opening reserve or a policy's value at its rebase position
        without reducing the whole timeline to a sum.

    This is positional list selection: zero is the first stored value and a
    negative index counts back from the end. It is different from
    ``projection.at_period()``, which shifts every value along the period axis.

    The index may be one Python integer used for every policy or a signed
    integer scalar column/expression giving each policy its own position.
    Floats require an explicit checked integer conversion before selection;
    they are never truncated here. A null index, null list, empty list, or
    out-of-bounds position refuses the calculation. A null element selected
    from a present list remains null.

    Parameters
    ----------
    index : object
        A signed integer position or per-policy signed integer expression.

    Returns
    -------
    ExpressionProxy
        One scalar per policy, retaining the list's inner dtype.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"cashflow": [[10.0, 20.0], [30.0]], "position": [1, 0]})
    af.selected = af.cashflow.list.get(af.position)
    print(af.collect()["selected"].to_list())
    ```

    ```text
    [20.0, 30.0]
    ```
    """
    if isinstance(index, bool):
        return None
    if isinstance(index, numbers.Real):
        if not isinstance(index, numbers.Integral):
            return None
        position = int(index)
        if position < -(1 << 63) or position >= 1 << 63:
            return None
    return _BoundOperation(args=(receiver,), operands=(index,))


def _list_reverse(receiver: "OpNode") -> _BoundOperation:
    """Reverse each policy's own projection periods, last period first.

    !!! note "When to use"
        Turn a timeline end for end, so that a calculation written to run
        forward can run from a policy's last period back to its first --
        the step a workbook's ``R[1]C`` rollback takes when it is spelled
        as "reverse, accumulate, reverse back".

    For a linear rollback, ``V[t] = m[t] * V[t+1] + a[t]``, write the one
    named recurrence instead:
    ``af.reserve = af.cf.projection.accumulate(initial=0.0,
    multiplier=af.v, addend=af.cf, reverse=True)``. Discounting alone is
    ``projection.prospective_value``, and a suffix sum is
    ``projection.remaining_sum``. Keep this operation for a rollback that is
    not linear, which is written as reverse, a forward calculation, and
    reverse back.

    Each policy is reversed within its own length, so a short policy's last
    period becomes its first and no period of one policy reaches another.
    The values move and nothing else happens to them: a null period moves
    to its mirrored position and stays a null, and an empty list stays
    empty.

    Returns
    -------
    ExpressionProxy
        One list per policy, the same length and type as the receiver.

    Examples
    --------
    ```python
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"cashflow": [[10.0, 20.0, 30.0], [5.0], []]})
    af.reversed_cashflow = af.cashflow.list.reverse()
    print(af.collect()["reversed_cashflow"].to_list())
    ```

    ```text
    [[30.0, 20.0, 10.0], [5.0], []]
    ```
    """
    return _BoundOperation(args=(receiver,))


STRING_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("str.to_date", _to_date),
)
LIST_OPERATIONS: Final[tuple[ProxyOperation, ...]] = (
    ProxyOperation("max", _list_max),
    ProxyOperation("mean", _list_mean),
    ProxyOperation("min", _list_min),
    ProxyOperation("sum", _list_sum),
    ProxyOperation("list.get", _list_get),
    ProxyOperation("list.reverse", _list_reverse),
)
PROXY_NAMESPACE_OPERATIONS: Final[dict[str, tuple[ProxyOperation, ...]]] = {
    "str": STRING_OPERATIONS,
    "list": LIST_OPERATIONS,
}

_POWER_DOCUMENTATION = """Raise numeric values to specified power.

Computes the power operation element-wise, raising each value to the specified
exponent. Essential for actuarial calculations involving compound growth,
present value computations, mortality rate adjustments, and exponential
modeling in insurance and pension mathematics.

!!! note "When to use"
    * **Present Value Calculations:** Apply discount factors using compound
      interest formulas like (1 + i)^(-t) for cash flow valuations.
    * **Compound Interest:** Calculate future values using (1 + i)^n for
      policy cash values, premium accumulations, and benefit projections.
    * **Mortality Rate Adjustments:** Apply exponential improvements or
      deteriorations to base mortality rates over projection periods.
    * **Risk Factor Scaling:** Transform linear risk scores to exponential
      scales for underwriting models and pricing adjustments.
    * **Reserve Calculations:** Compute actuarial present values using
      discount factors in life insurance and annuity valuations.
    * **Stochastic Modeling:** Generate power-law distributions for
      catastrophic loss modeling and reinsurance pricing.

Parameters
----------
exponent : float | int | ExpressionProxy
    The power to raise values to. Can be a scalar or column expression.

Returns
-------
ExpressionProxy
    An expression containing values raised to the specified power.

Examples
--------
**Scalar Example: Present Value Discount Factors**

```python
from gaspatchio import ActuarialFrame

data = {
    "policy_id": ["P001", "P002", "P003", "P004"],
    "discount_base": [1.05, 1.04, 1.06, 1.03],
    "time_years": [10, 15, 20, 25],
}
af = ActuarialFrame(data)
result = af.select(
    af["policy_id"],
    discount_factor=af["discount_base"].pow(-1 * af["time_years"]),
).collect()
print(result)
```

```text
shape: (4, 2)
┌───────────┬─────────────────┐
│ policy_id ┆ discount_factor │
│ ---       ┆ ---             │
│ str       ┆ f64             │
╞═══════════╪═════════════════╡
│ P001      ┆ 0.613913        │
│ P002      ┆ 0.555265        │
│ P003      ┆ 0.311805        │
│ P004      ┆ 0.477606        │
└───────────┴─────────────────┘
```

**Vector Example: Interest Compounding Factors**

```python
from gaspatchio import ActuarialFrame

data = {
    "policy_id": ["P001", "P002"],
    "age": [35, 45],
    "month": [
        [1, 2, 3, 4],
        [1, 2, 3, 4]
    ],
    "base_rate": [
        [1.04, 1.045, 1.05, 1.055],
        [1.03, 1.035, 1.04, 1.045]
    ]
}
af = ActuarialFrame(data)

af["squared_growth"] = af["base_rate"].pow(2.0)

rows = af.collect()["squared_growth"].to_list()
print([round(value, 6) for value in rows[0]])
print([round(value, 6) for value in rows[1]])
```

```text
[1.0816, 1.092025, 1.1025, 1.113025]
[1.0609, 1.071225, 1.0816, 1.092025]
```
"""

__all__ = [
    "ABSENCE_PREDICATE_OPERATIONS",
    "ACCUMULATION_OPERATIONS",
    "BINARY_OPERATIONS",
    "CLIP_OPERATION",
    "CUT_OPERATION",
    "DIRECT_CALL_OPERATIONS",
    "FILL_NAN_OPERATION",
    "FILL_NULL_OPERATION",
    "GENERATED_PROXY_OPERATIONS",
    "IS_IN_OPERATION",
    "LIST_OPERATIONS",
    "PLAIN_MATH_OPERATIONS",
    "PROXY_NAMESPACE_OPERATIONS",
    "PROXY_OPERATIONS",
    "PROXY_OPERATORS",
    "REPLACE_OPERATION",
    "ROUNDING_OPERATIONS",
    "ROUND_OPERATION",
    "ROUND_SIG_FIGS_OPERATION",
    "STRING_OPERATIONS",
    "BinaryOperation",
    "CoreCall",
    "ProxyOperation",
    "ProxyOperator",
]
