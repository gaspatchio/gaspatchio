# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Live documentation for the explicit Polars escape.

Only methods that already had Gaspatchio documentation are explicit here.
Every other public Polars method remains available through dynamic lookup.
The wrappers add signatures, help and retrieval text; execution remains the
one ``PolarsNative._mint`` path. No core operation imports this module.

Five of those names mean the axis they run along, and through the escape
that axis is the model points: ``shift``, ``diff``, ``interpolate``,
``forward_fill`` and ``backward_fill``. Each is refused on a per-period
column, because Polars reads such a column as one value per policy and would
move values between policies rather than between periods -- returning the
right shape with nothing to say which axis it used. The per-period form is
``polars_native().list.eval(pl.element().<method>(...))``, which the refusal
names; on a per-policy column all five are ordinary row semantics and are
unaffected. Only the first three have a wrapper below, so the other two say
it through that refusal alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Protocol

    from gaspatchio.column.expression_proxy import ExpressionProxy

    class _NativeMint(Protocol):
        def _mint(
            self,
            method: str,
            args: tuple[object, ...],
            kwargs: dict[str, object],
            namespace: str | None,
        ) -> ExpressionProxy: ...


def _mint(
    receiver: object,
    method: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    *,
    namespace: str | None = None,
) -> ExpressionProxy:
    """Call the engine escape from an explicit documentation wrapper.

    This keeps typed, discoverable methods on the same minting path as
    dynamically discovered Polars methods.
    """
    escape = cast("_NativeMint", getattr(receiver, "_escape", receiver))
    receiver_namespace = getattr(receiver, "_namespace", None)
    resolved_namespace = namespace
    if resolved_namespace is None and isinstance(receiver_namespace, str):
        resolved_namespace = receiver_namespace
    return escape._mint(  # noqa: SLF001 - paired private protocol helper
        method, args, kwargs, resolved_namespace
    )


class _DocumentedPolarsNativeMethods:
    """Previously documented real ``pl.Expr`` methods on the explicit door.

    Each wrapper adds a signature and retrieval text, then delegates to the
    existing native minting implementation.
    """

    __slots__ = ()

    def alias(self, name: str) -> ExpressionProxy:
        r"""Assign a new name to this expression for use in selections and computations.

        Creates a new ExpressionProxy with the specified column name. This is
        fundamental for creating derived columns, renaming computed values, and
        organizing actuarial calculations with meaningful, business-relevant names
        that enhance readability and maintainability of analytical workflows.

        !!! note "When to use"
            * **Derived Calculations:** Name computed values like "adjusted_premium",
              "net_present_value", or "mortality_adjustment" for clarity in analysis.
            * **Business Terminology:** Use actuarial terms like
              "reserves_best_estimate", "risk_margin", or
              "solvency_capital_requirement" for regulatory reporting.
            * **Data Standardization:** Rename columns from different sources to
              consistent naming conventions for portfolio analysis.
            * **Intermediate Results:** Name intermediate calculations in complex
              formulas for debugging and validation purposes.
            * **Reporting Clarity:** Create user-friendly column names for management
              dashboards and regulatory reports.
            * **Model Documentation:** Use descriptive names that match actuarial
              model specifications and documentation.

        Parameters
        ----------
        name : str
            The new name to assign to this expression. Should follow standard
            naming conventions and be descriptive of the value's purpose.

        Returns
        -------
        ExpressionProxy
            A new ExpressionProxy with the specified alias name.

        Examples
        --------
        **Scalar Example: Naming a Premium Calculation**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "base_premium": [1000.0, 1200.0, 800.0],
            "loading_factor": [1.15, 1.20, 1.10],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            (af["base_premium"] * af["loading_factor"])
            .polars_native()
            .alias("gross_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 3)
        ┌──────────────┬────────────────┬───────────────┐
        │ base_premium ┆ loading_factor ┆ gross_premium │
        │ ---          ┆ ---            ┆ ---           │
        │ f64          ┆ f64            ┆ f64           │
        ╞══════════════╪════════════════╪═══════════════╡
        │ 1000.0       ┆ 1.15           ┆ 1150.0        │
        │ 1200.0       ┆ 1.2            ┆ 1440.0        │
        │ 800.0        ┆ 1.1            ┆ 880.0         │
        └──────────────┴────────────────┴───────────────┘
        ```

        **Vector Example: Multiple Derived Calculations**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "sum_assured": [100000.0, 250000.0, 500000.0],
            "premium": [1200.0, 2800.0, 4500.0],
            "age": [35, 45, 55],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            (af["premium"] / af["sum_assured"] * 1000)
            .polars_native()
            .alias("premium_per_1000"),
            ((af["age"] // 10) * 10).polars_native().alias("age_decade"),
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 5)
        ┌─────────────┬─────────┬─────┬──────────────────┬────────────┐
        │ sum_assured ┆ premium ┆ age ┆ premium_per_1000 ┆ age_decade │
        │ ---         ┆ ---     ┆ --- ┆ ---              ┆ ---        │
        │ f64         ┆ f64     ┆ i64 ┆ f64              ┆ i64        │
        ╞═════════════╪═════════╪═════╪══════════════════╪════════════╡
        │ 100000.0    ┆ 1200.0  ┆ 35  ┆ 12.0             ┆ 30         │
        │ 250000.0    ┆ 2800.0  ┆ 45  ┆ 11.2             ┆ 40         │
        │ 500000.0    ┆ 4500.0  ┆ 55  ┆ 9.0              ┆ 50         │
        └─────────────┴─────────┴─────┴──────────────────┴────────────┘
        ```
        """
        return _mint(self, "alias", (name,), {}, namespace=None)

    def cast(
        self, dtype: object, *, strict: bool = True, wrap_numerical: bool = False
    ) -> ExpressionProxy:
        r"""Cast values in this expression to a different data type.

        Converts the data type of values in the column or expression to the specified
        target type. This is essential for ensuring data consistency, preparing data
        for calculations, and meeting specific type requirements in actuarial analysis.

        !!! note "When to use"
            * **Data Type Alignment:** Convert integer policy numbers to strings for
              concatenation, or string amounts to numeric types for calculations.
            * **Precision Control:** Cast floating-point values to specific decimal
              precision for financial calculations and regulatory reporting.
            * **Date/Time Handling:** Convert string dates to proper date types for
              temporal analysis and policy duration calculations.
            * **Memory Optimization:** Cast large integers to smaller types when range
              permits, reducing memory usage for large datasets.
            * **API Compatibility:** Ensure data types match requirements of external
              systems, databases, or regulatory reporting formats.
            * **Calculation Preparation:** Convert string percentages to decimals,
              or ensure all monetary amounts are in consistent numeric formats.

        Parameters
        ----------
        dtype : PolarsDataType
            Target data type to cast to (e.g., pl.Float64, pl.String, pl.Date).
        strict : bool, default True
            If True, raises an error when conversion fails. If False, returns null
            for values that cannot be converted.
        wrap_numerical : bool, default False
            Whether overflowing numerical casts wrap instead of raising.

        Returns
        -------
        ExpressionProxy
            An expression with values cast to the specified data type.

        Examples
        --------
        **Scalar Example: Convert String Policy Numbers to Integers**

        ```python
        from gaspatchio import ActuarialFrame
        import polars as pl

        data = {
            "policy_number": ["1001", "1002", "1003", "1004"],
            "premium": [1200.0, 1500.0, 800.0, 2000.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_number"]
            .polars_native()
            .cast(pl.Int64)
            .polars_native()
            .alias("policy_id"),
            af["premium"],
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬─────────┐
        │ policy_id ┆ premium │
        │ ---       ┆ ---     │
        │ i64       ┆ f64     │
        ╞═══════════╪═════════╡
        │ 1001      ┆ 1200.0  │
        │ 1002      ┆ 1500.0  │
        │ 1003      ┆ 800.0   │
        │ 1004      ┆ 2000.0  │
        └───────────┴─────────┘
        ```

        **Vector Example: Cast Premium Rates to Higher Precision**

        ```python
        from gaspatchio import ActuarialFrame
        import polars as pl

        data = {
            "age_group": ["25-35", "36-45", "46-55", "56-65"],
            "mortality_rate": [0.001, 0.002, 0.004, 0.008],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["age_group"],
            precise_rate=af["mortality_rate"]
            .polars_native()
            .cast(pl.Decimal(precision=10, scale=6)),
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 2)
        ┌───────────┬───────────────┐
        │ age_group ┆ precise_rate  │
        │ ---       ┆ ---           │
        │ str       ┆ decimal[10,6] │
        ╞═══════════╪═══════════════╡
        │ 25-35     ┆ 0.001000      │
        │ 36-45     ┆ 0.002000      │
        │ 46-55     ┆ 0.004000      │
        │ 56-65     ┆ 0.008000      │
        └───────────┴───────────────┘
        ```
        """
        return _mint(
            self,
            "cast",
            (dtype,),
            {"strict": strict, "wrap_numerical": wrap_numerical},
            namespace=None,
        )

    def cum_min(self, *, reverse: bool = False) -> ExpressionProxy:
        r"""Compute the cumulative minimum of numeric values.

        Returns the running minimum at each position. Essential for tracking
        guarantee floors, minimum account values, and worst-case scenarios
        in actuarial projections.

        !!! note "When to use"
            * **Guarantee Floors:** Track the minimum account value reached
                over time for secondary guarantee calculations.
            * **Minimum Balance Tracking:** Monitor the lowest point of a
                policy's account value for risk analysis.

        Parameters
        ----------
        reverse : bool, default False
            If True, compute the cumulative minimum in reverse order.

        Returns
        -------
            ExpressionProxy with the cumulative minimum applied.

        Examples
        --------
            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {"policy_id": ["P001"], "av": [[100, 90, 85, 95, 80]]}
            af = ActuarialFrame(data)
            af["min_av"] = af["av"].polars_native().list.eval(pl.element().cum_min())
            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬─────────────────┬─────────────────┐
            │ policy_id ┆ av              ┆ min_av          │
            │ ---       ┆ ---             ┆ ---             │
            │ str       ┆ list[i64]       ┆ list[i64]       │
            ╞═══════════╪═════════════════╪═════════════════╡
            │ P001      ┆ [100, 90, … 80] ┆ [100, 90, … 80] │
            └───────────┴─────────────────┴─────────────────┘
            ```
        """
        return _mint(self, "cum_min", (), {"reverse": reverse}, namespace=None)

    def cum_max(self, *, reverse: bool = False) -> ExpressionProxy:
        r"""Compute the cumulative maximum of numeric values.

        Returns the running maximum at each position. Essential for tracking
        high-water marks, GMDB ratchet bases, and peak account values
        in actuarial projections.

        !!! note "When to use"
            * **GMDB High-Water Mark:** Track the maximum account value
                reached for guaranteed minimum death benefit calculations.
            * **Peak Exposure:** Monitor the highest account value for
                fee-tier determination and risk management.

        Parameters
        ----------
        reverse : bool, default False
            If True, compute the cumulative maximum in reverse order.

        Returns
        -------
            ExpressionProxy with the cumulative maximum applied.

        Examples
        --------
            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {"policy_id": ["P001"], "av": [[100, 110, 105, 120, 115]]}
            af = ActuarialFrame(data)
            af["max_av"] = af["av"].polars_native().list.eval(pl.element().cum_max())
            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬───────────────────┬───────────────────┐
            │ policy_id ┆ av                ┆ max_av            │
            │ ---       ┆ ---               ┆ ---               │
            │ str       ┆ list[i64]         ┆ list[i64]         │
            ╞═══════════╪═══════════════════╪═══════════════════╡
            │ P001      ┆ [100, 110, … 115] ┆ [100, 110, … 120] │
            └───────────┴───────────────────┴───────────────────┘
            ```
        """
        return _mint(self, "cum_max", (), {"reverse": reverse}, namespace=None)

    def diff(self, n: object = 1, null_behavior: str = "ignore") -> ExpressionProxy:
        r"""Compute the difference between consecutive values.

        Returns the change from one period to the next. Essential for
        deriving incremental cashflows from cumulative totals, computing
        period-over-period reserve movements, and calculating year-on-year
        changes in mortality or lapse rates.

        !!! note "When to use"
            * **Incremental Cashflows:** Derive period cashflows from
                cumulative totals (e.g., incremental claims from cumulative).
            * **Reserve Movements:** Compute the change in reserves between
                valuation dates for IFRS 17 analysis of change.
            * **Rate Changes:** Calculate year-on-year changes in mortality
                or lapse rates for experience studies.

        Through the escape this differences down the model points, so a
        per-period column is refused: Polars reads the whole column as one
        value per policy and would difference between policies rather than
        between periods, returning the right shape with nothing to say which
        axis it used. The example below is already the per-period form,
        ``polars_native().list.eval(pl.element().diff())``; the bare call is
        for a per-policy column, where it is ordinary row semantics.

        Parameters
        ----------
        n : int, default 1
            Number of periods to look back.
        null_behavior : {"ignore", "drop"}, default "ignore"
            How to handle nulls in the input.

        Returns
        -------
            ExpressionProxy with the differences applied.

        Examples
        --------
            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {"policy_id": ["P001"], "reserves": [[100, 120, 115, 130, 125]]}
            af = ActuarialFrame(data)
            af["reserve_change"] = (
                af["reserves"].polars_native().list.eval(pl.element().diff())
            )
            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬───────────────────┬──────────────────┐
            │ policy_id ┆ reserves          ┆ reserve_change   │
            │ ---       ┆ ---               ┆ ---              │
            │ str       ┆ list[i64]         ┆ list[i64]        │
            ╞═══════════╪═══════════════════╪══════════════════╡
            │ P001      ┆ [100, 120, … 125] ┆ [null, 20, … -5] │
            └───────────┴───────────────────┴──────────────────┘
            ```
        """
        return _mint(self, "diff", (n, null_behavior), {}, namespace=None)

    def fill_nan(self, value: object) -> ExpressionProxy:
        r"""Replace NaN values with a specified value.

        Distinct from ``fill_null`` — this targets IEEE 754 NaN values
        specifically, which commonly appear when loading assumption tables
        from Excel or CSV where blank cells become NaN.

        ``af.<column>.fill_nan(value)`` is a declared gaspatchio operation, so
        written through this door with a value it is refused and the message
        names the declared spelling. The door is for the forms the operation
        does not hold: ``fill_nan(None)``, which turns a NaN into a null, and
        Polars' own expressions inside ``list.eval``.

        !!! note "When to use"
            * **Assumption Table Cleanup:** Replace NaN gaps in mortality
                rate tables loaded from Excel.
            * **Investment Return Data:** Clean NaN values in market data
                feeds before using in projections.

        Parameters
        ----------
        value : object
            The required replacement value. Explicit ``None`` replaces NaN
            with null.

        Returns
        -------
            ExpressionProxy with NaN values replaced.

        Examples
        --------
            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {"policy_id": ["P001"], "rates": [[0.01, float("nan"), 0.03]]}
            af = ActuarialFrame(data)
            af["clean_rates"] = (
                af["rates"].polars_native().list.eval(pl.element().fill_nan(0.0))
            )
            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬───────────────────┬───────────────────┐
            │ policy_id ┆ rates             ┆ clean_rates       │
            │ ---       ┆ ---               ┆ ---               │
            │ str       ┆ list[f64]         ┆ list[f64]         │
            ╞═══════════╪═══════════════════╪═══════════════════╡
            │ P001      ┆ [0.01, NaN, 0.03] ┆ [0.01, 0.0, 0.03] │
            └───────────┴───────────────────┴───────────────────┘
            ```
        """
        return _mint(self, "fill_nan", (value,), {}, namespace=None)

    def interpolate(self, method: str = "linear") -> ExpressionProxy:
        r"""Interpolate null values using the specified method.

        Fills gaps in data by interpolating between known values. Useful
        for filling missing points in assumption tables where rates are
        only provided at quinquennial ages or select durations.

        !!! note "When to use"
            * **Mortality Table Gaps:** Fill rates between quinquennial
                age points (e.g., interpolate between age 30 and 35).
            * **Yield Curve Interpolation:** Fill missing tenors in a
                yield curve for discount rate calculations.

        Through the escape this interpolates down the model points, so a
        per-period column is refused: Polars reads the whole column as one
        value per policy and would interpolate between policies rather than
        between periods, returning the right shape with nothing to say which
        axis it used. The example below is already the per-period form,
        ``polars_native().list.eval(pl.element().interpolate())``; the bare
        call is for a per-policy column, where it is ordinary row semantics.

        Parameters
        ----------
        method : {"linear", "nearest"}, default "linear"
            Interpolation method to apply between known values.

        Returns
        -------
            ExpressionProxy with interpolated values.

        Examples
        --------
            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {"policy_id": ["P001"], "rates": [[0.01, None, None, 0.04]]}
            af = ActuarialFrame(data)
            af["filled"] = (
                af["rates"].polars_native().list.eval(pl.element().interpolate())
            )
            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬──────────────────────┬──────────────────────┐
            │ policy_id ┆ rates                ┆ filled               │
            │ ---       ┆ ---                  ┆ ---                  │
            │ str       ┆ list[f64]            ┆ list[f64]            │
            ╞═══════════╪══════════════════════╪══════════════════════╡
            │ P001      ┆ [0.01, null, … 0.04] ┆ [0.01, 0.02, … 0.04] │
            └───────────┴──────────────────────┴──────────────────────┘
            ```
        """
        return _mint(self, "interpolate", (method,), {}, namespace=None)

    def mean(self) -> ExpressionProxy:
        r"""Compute the arithmetic mean of numeric values in this expression or column.

        Returns the arithmetic mean (average) of all non-null numeric values.
        For grouped operations, computes the mean within each group. This
        fundamental statistic is used to calculate average claim amounts,
        average premiums, or mean mortality rates across different segments.

        !!! note "When to use"
            * **Premium Analysis:** Calculate average premium amounts by policy type,
              age group, or geographic region to understand pricing patterns and
              identify potential underpricing or overpricing scenarios.
            * **Claim Analysis:** Determine mean claim amounts to assess loss ratios,
              set reserves, and evaluate the financial impact of different risk factors.
            * **Mortality Analysis:** Compute average mortality rates across different
              demographic segments to validate actuarial assumptions and pricing models.
            * **Performance Metrics:** Calculate average policy duration, average time
              to claim, or average customer lifetime value for business intelligence.
            * **Risk Assessment:** Determine mean exposure amounts, mean policy values,
              or average risk scores to understand portfolio composition and
              concentration.
            * **Benchmarking:** Compare mean values against industry standards or
              historical performance to evaluate competitive positioning.

        Returns
        -------
        ExpressionProxy
            An expression representing the mean value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the mean per group or window.

        Examples
        --------
        **Scalar Example: Average Premium Amount**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": [1, 2, 3, 4, 5],
            "premium": [1200.0, 1500.0, 800.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        avg_premium_expr = af["premium"].polars_native().mean()
        result = af.with_columns(
            avg_premium_expr.polars_native().alias("avg_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌───────────┬─────────┬─────────────┐
        │ policy_id ┆ premium ┆ avg_premium │
        │ ---       ┆ ---     ┆ ---         │
        │ i64       ┆ f64     ┆ f64         │
        ╞═══════════╪═════════╪═════════════╡
        │ 1         ┆ 1200.0  ┆ 1320.0      │
        │ 2         ┆ 1500.0  ┆ 1320.0      │
        │ 3         ┆ 800.0   ┆ 1320.0      │
        │ 4         ┆ 2000.0  ┆ 1320.0      │
        │ 5         ┆ 1100.0  ┆ 1320.0      │
        └───────────┴─────────┴─────────────┘
        ```

        **Vector Example: Average Premium by Policy Type**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 1500.0, 800.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].polars_native().mean().polars_native().alias("avg_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────┬─────────────┐
        │ policy_type ┆ premium ┆ avg_premium │
        │ ---         ┆ ---     ┆ ---         │
        │ str         ┆ f64     ┆ f64         │
        ╞═════════════╪═════════╪═════════════╡
        │ TERM        ┆ 1200.0  ┆ 1320.0      │
        │ TERM        ┆ 1500.0  ┆ 1320.0      │
        │ WHOLE       ┆ 800.0   ┆ 1320.0      │
        │ WHOLE       ┆ 2000.0  ┆ 1320.0      │
        │ UL          ┆ 1100.0  ┆ 1320.0      │
        └─────────────┴─────────┴─────────────┘
        ```
        """
        return _mint(self, "mean", (), {}, namespace=None)

    def min(self) -> ExpressionProxy:
        r"""Find the minimum value in this expression or column.

        Returns the smallest non-null value in a numeric column. For grouped operations,
        computes the minimum within each group. This is essential for actuarial analysis
        to identify floor values, minimum thresholds, or the most favorable outcomes
        across different risk segments or time periods.

        !!! note "When to use"
            * **Risk Analysis:** Find minimum claim amounts, lowest mortality rates,
              or smallest policy values to understand best-case scenarios and
              floor risks.
            * **Pricing Validation:** Identify minimum premiums charged to ensure they
              meet profitability thresholds and regulatory requirements.
            * **Performance Tracking:** Determine minimum policy durations, shortest
              claim settlement times, or lowest customer satisfaction scores.
            * **Portfolio Analysis:** Find minimum exposure amounts or smallest policy
              sizes to understand concentration risks and diversification levels.
            * **Regulatory Compliance:** Identify minimum reserves, capital
              requirements,
              or solvency ratios to ensure compliance with regulatory standards.
            * **Benchmarking:** Compare minimum values against industry standards or
              historical performance to evaluate competitive positioning.

        Returns
        -------
        ExpressionProxy
            An expression representing the minimum value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the minimum per group or window.

        Examples
        --------
        **Scalar Example: Minimum Claim Amount**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, 500.0, 2800.0, 150.0, 3500.0],
        }
        af = ActuarialFrame(data)
        min_claim_expr = af["claim_amount"].polars_native().min()
        result = af.with_columns(
            min_claim_expr.polars_native().alias("min_claim")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────┬──────────────┬───────────┐
        │ claim_id ┆ claim_amount ┆ min_claim │
        │ ---      ┆ ---          ┆ ---       │
        │ i64      ┆ f64          ┆ f64       │
        ╞══════════╪══════════════╪═══════════╡
        │ 1        ┆ 1200.0       ┆ 150.0     │
        │ 2        ┆ 500.0        ┆ 150.0     │
        │ 3        ┆ 2800.0       ┆ 150.0     │
        │ 4        ┆ 150.0        ┆ 150.0     │
        │ 5        ┆ 3500.0       ┆ 150.0     │
        └──────────┴──────────────┴───────────┘
        ```

        **Vector Example: Minimum Premium by Policy Type**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 800.0, 1500.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].polars_native().min().polars_native().alias("min_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────┬─────────────┐
        │ policy_type ┆ premium ┆ min_premium │
        │ ---         ┆ ---     ┆ ---         │
        │ str         ┆ f64     ┆ f64         │
        ╞═════════════╪═════════╪═════════════╡
        │ TERM        ┆ 1200.0  ┆ 800.0       │
        │ TERM        ┆ 800.0   ┆ 800.0       │
        │ WHOLE       ┆ 1500.0  ┆ 800.0       │
        │ WHOLE       ┆ 2000.0  ┆ 800.0       │
        │ UL          ┆ 1100.0  ┆ 800.0       │
        └─────────────┴─────────┴─────────────┘
        ```
        """
        return _mint(self, "min", (), {}, namespace=None)

    def max(self) -> ExpressionProxy:
        r"""Find the maximum value in this expression or column.

        Returns the largest non-null value in a numeric column. For grouped operations,
        computes the maximum within each group. This is crucial for actuarial analysis
        to identify peak values, maximum exposures, or worst-case scenarios across
        different risk segments or time periods.

        !!! note "When to use"
            * **Risk Analysis:** Find maximum claim amounts, highest mortality rates,
              or largest policy values to understand worst-case scenarios and
              tail risks.
            * **Exposure Management:** Identify maximum exposure amounts or largest
              policy concentrations to manage catastrophic risk and reinsurance needs.
            * **Performance Tracking:** Determine maximum policy durations, longest
              claim settlement times, or highest customer satisfaction scores.
            * **Pricing Analysis:** Find maximum premiums charged to validate pricing
              models and ensure competitive positioning in the market.
            * **Regulatory Compliance:** Identify maximum risk concentrations or largest
              exposures to ensure compliance with regulatory capital requirements.
            * **Portfolio Optimization:** Find maximum returns, highest profit margins,
              or best-performing segments for strategic decision making.

        Returns
        -------
        ExpressionProxy
            An expression representing the maximum value. If used in a `select` or
            `with_columns` context without a `group_by` or `over`, this will
            result in a single value. If used within a `group_by` or `over`
            context, it computes the maximum per group or window.

        Examples
        --------
        **Scalar Example: Maximum Claim Amount**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, 500.0, 2800.0, 150.0, 3500.0],
        }
        af = ActuarialFrame(data)
        max_claim_expr = af["claim_amount"].polars_native().max()
        result = af.with_columns(
            max_claim_expr.polars_native().alias("max_claim")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────┬──────────────┬───────────┐
        │ claim_id ┆ claim_amount ┆ max_claim │
        │ ---      ┆ ---          ┆ ---       │
        │ i64      ┆ f64          ┆ f64       │
        ╞══════════╪══════════════╪═══════════╡
        │ 1        ┆ 1200.0       ┆ 3500.0    │
        │ 2        ┆ 500.0        ┆ 3500.0    │
        │ 3        ┆ 2800.0       ┆ 3500.0    │
        │ 4        ┆ 150.0        ┆ 3500.0    │
        │ 5        ┆ 3500.0       ┆ 3500.0    │
        └──────────┴──────────────┴───────────┘
        ```

        **Vector Example: Maximum Premium by Policy Type**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "premium": [1200.0, 800.0, 1500.0, 2000.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["premium"].polars_native().max().polars_native().alias("max_premium")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────┬─────────────┐
        │ policy_type ┆ premium ┆ max_premium │
        │ ---         ┆ ---     ┆ ---         │
        │ str         ┆ f64     ┆ f64         │
        ╞═════════════╪═════════╪═════════════╡
        │ TERM        ┆ 1200.0  ┆ 2000.0      │
        │ TERM        ┆ 800.0   ┆ 2000.0      │
        │ WHOLE       ┆ 1500.0  ┆ 2000.0      │
        │ WHOLE       ┆ 2000.0  ┆ 2000.0      │
        │ UL          ┆ 1100.0  ┆ 2000.0      │
        └─────────────┴─────────┴─────────────┘
        ```
        """
        return _mint(self, "max", (), {}, namespace=None)

    def count(self) -> ExpressionProxy:
        r"""Count the number of non-null values in this expression or column.

        Returns the count of non-null values in the column. For grouped operations,
        computes the count within each group. This is fundamental for actuarial analysis
        to understand data completeness, calculate exposure counts, and determine sample
        sizes for statistical analysis and regulatory reporting.

        !!! note "When to use"
            * **Data Quality Assessment:** Count non-null values to assess data
              completeness and identify missing information that might affect analysis.
            * **Exposure Calculation:** Count the number of policies, claims, or lives
              exposed to risk for rate calculations and reserve estimations.
            * **Sample Size Analysis:** Determine sample sizes for statistical
              significance
              testing and confidence interval calculations in actuarial studies.
            * **Regulatory Reporting:** Count policies, claims, or transactions for
              regulatory filings and compliance reporting requirements.
            * **Business Intelligence:** Count active policies, new business, lapses,
              or claims by various dimensions for management reporting.
            * **Risk Segmentation:** Count observations in different risk categories
              to ensure adequate sample sizes for credible rate calculations.

        Returns
        -------
        ExpressionProxy
            An expression representing the count of non-null values. If used in a
            `select` or `with_columns` context without a `group_by` or `over`, this
            will result in a single value. If used within a `group_by` or `over`
            context, it computes the count per group or window.

        Examples
        --------
        **Scalar Example: Total Number of Valid Claims**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": [1, 2, 3, 4, 5],
            "claim_amount": [1200.0, None, 2800.0, 150.0, None],
        }
        af = ActuarialFrame(data)
        count_claims_expr = af["claim_amount"].polars_native().count()
        result = af.with_columns(
            count_claims_expr.polars_native().alias("valid_claims")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────┬──────────────┬──────────────┐
        │ claim_id ┆ claim_amount ┆ valid_claims │
        │ ---      ┆ ---          ┆ ---          │
        │ i64      ┆ f64          ┆ u64          │
        ╞══════════╪══════════════╪══════════════╡
        │ 1        ┆ 1200.0       ┆ 3            │
        │ 2        ┆ null         ┆ 3            │
        │ 3        ┆ 2800.0       ┆ 3            │
        │ 4        ┆ 150.0        ┆ 3            │
        │ 5        ┆ null         ┆ 3            │
        └──────────┴──────────────┴──────────────┘
        ```

        **Vector Example: Policy Count by Product Type**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "policy_id": ["P001", "P002", None, "P004", "P005"],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["policy_id"].polars_native().count().polars_native().alias("policy_count")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬───────────┬──────────────┐
        │ policy_type ┆ policy_id ┆ policy_count │
        │ ---         ┆ ---       ┆ ---          │
        │ str         ┆ str       ┆ u64          │
        ╞═════════════╪═══════════╪══════════════╡
        │ TERM        ┆ P001      ┆ 4            │
        │ TERM        ┆ P002      ┆ 4            │
        │ WHOLE       ┆ null      ┆ 4            │
        │ WHOLE       ┆ P004      ┆ 4            │
        │ UL          ┆ P005      ┆ 4            │
        └─────────────┴───────────┴──────────────┘
        ```
        """
        return _mint(self, "count", (), {}, namespace=None)

    def unique(self, *, maintain_order: bool = False) -> ExpressionProxy:
        r"""Return unique values from this expression or column.

        Extracts distinct values and removes duplicates. Set ``maintain_order=True``
        when the first occurrence determines the reported order; the Polars default
        may return the values in any order.

        !!! note "When to use"
            * **Data Exploration:** Identify unique policy types, product codes,
              or geographic
              regions to understand portfolio composition and coverage diversity.
            * **Reference Data Creation:** Extract unique values to create lookup
              tables,
              validation lists, or categorical mappings for data standardization.
            * **Portfolio Segmentation:** Find distinct risk categories, age bands, or
              coverage levels for actuarial analysis and pricing model development.
            * **Quality Assurance:** Verify expected categorical values and identify
              unexpected or erroneous entries in key classification fields.
            * **Regulatory Reporting:** Create lists of unique jurisdictions,
              product lines,
              or regulatory categories for compliance reporting requirements.
            * **Business Intelligence:** Generate unique customer segments, distribution
              channels, or sales territories for strategic analysis and planning.

        Parameters
        ----------
        maintain_order : bool, default False
            Preserve first-occurrence order when true. Leaving the Polars default
            allows a faster result whose order is unspecified.

        Returns
        -------
        ExpressionProxy
            An expression containing the distinct values.
            If used within group_by context, returns unique values per group.

        Examples
        --------
        **Scalar Example: Unique Policy Types**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": [1, 2, 3, 4, 5, 6],
            "policy_type": ["TERM", "WHOLE", "TERM", "UL", "WHOLE", "TERM"],
        }
        af = ActuarialFrame(data)
        result = af.select(
            unique_types=af["policy_type"].polars_native().unique(maintain_order=True)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌──────────────┐
        │ unique_types │
        │ ---          │
        │ str          │
        ╞══════════════╡
        │ TERM         │
        │ WHOLE        │
        │ UL           │
        └──────────────┘
        ```

        **Vector Example: Unique Values in List Column**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "monthly_premiums": [
                [1200.0, 1200.0, 1250.0, 1250.0],
                [1100.0, 1150.0, 1100.0, 1200.0],
            ],
        }
        af = ActuarialFrame(data)

        af.unique_premiums = af.monthly_premiums.polars_native().list.unique()

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬────────────────────────────┬──────────────────────────┐
        │ policy_id ┆ monthly_premiums           ┆ unique_premiums          │
        │ ---       ┆ ---                        ┆ ---                      │
        │ str       ┆ list[f64]                  ┆ list[f64]                │
        ╞═══════════╪════════════════════════════╪══════════════════════════╡
        │ P001      ┆ [1200.0, 1200.0, … 1250.0] ┆ [1200.0, 1250.0]         │
        │ P002      ┆ [1100.0, 1150.0, … 1200.0] ┆ [1100.0, 1150.0, 1200.0] │
        └───────────┴────────────────────────────┴──────────────────────────┘
        ```
        """
        return _mint(
            self, "unique", (), {"maintain_order": maintain_order}, namespace=None
        )

    def sort(
        self, *, descending: bool = False, nulls_last: bool = False
    ) -> ExpressionProxy:
        r"""Sort values in this expression or column.

        Arranges values in ascending or descending order while maintaining
        positional relationships
        with other columns when used in select contexts. Essential for ranking analysis,
        identifying top/bottom performers, and creating ordered datasets for
        actuarial reporting.

        !!! note "When to use"
            * **Risk Ranking:** Sort policies by claim amounts, risk scores, or premium
              values to identify highest exposure cases requiring special attention.
            * **Performance Analysis:** Order sales agents by production volume,
              policies
              by profitability, or claims by settlement time for performance evaluation.
            * **Regulatory Reporting:** Create sorted lists of largest policies, highest
              reserves, or top risk concentrations for regulatory compliance.
            * **Portfolio Management:** Sort by policy expiration dates, renewal dates,
              or premium due dates for operational scheduling and cash flow planning.
            * **Statistical Analysis:** Order data for percentile calculations, trend
              analysis, or creating cumulative distribution functions.
            * **Customer Segmentation:** Sort customers by lifetime value, claim
              frequency,
              or policy tenure for targeted marketing and retention strategies.

        Parameters
        ----------
        descending : bool, default False
            If True, sort in descending order (largest to smallest).
            If False, sort in ascending order (smallest to largest).
        nulls_last : bool, default False
            Whether null values appear after all non-null values.

        Returns
        -------
        ExpressionProxy
            An expression with values sorted according to the specified order.
            When used in group_by context, sorts values within each group.

        Examples
        --------
        **Scalar Example: Sort Claims by Amount**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004"],
            "claim_amount": [2500.0, 1200.0, 4800.0, 800.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            sorted_amounts=af["claim_amount"].polars_native().sort(descending=True)
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 1)
        ┌────────────────┐
        │ sorted_amounts │
        │ ---            │
        │ f64            │
        ╞════════════════╡
        │ 4800.0         │
        │ 2500.0         │
        │ 1200.0         │
        │ 800.0          │
        └────────────────┘
        ```

        **Vector Example: Sort Ages within Policy Types**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "UL"],
            "age": [45, 32, 58, 41, 62],
        }
        af = ActuarialFrame(data)
        result = af.with_columns(
            af["age"].polars_native().sort().polars_native().alias("sorted_ages")
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────┬─────────────┐
        │ policy_type ┆ age ┆ sorted_ages │
        │ ---         ┆ --- ┆ ---         │
        │ str         ┆ i64 ┆ i64         │
        ╞═════════════╪═════╪═════════════╡
        │ TERM        ┆ 45  ┆ 32          │
        │ TERM        ┆ 32  ┆ 41          │
        │ WHOLE       ┆ 58  ┆ 45          │
        │ WHOLE       ┆ 41  ┆ 58          │
        │ UL          ┆ 62  ┆ 62          │
        └─────────────┴─────┴─────────────┘
        ```
        """
        return _mint(
            self,
            "sort",
            (),
            {"descending": descending, "nulls_last": nulls_last},
            namespace=None,
        )

    def head(self, n: object = 10) -> ExpressionProxy:
        r"""Return the first n values from this expression or column.

        Retrieves the top n values in their original order, useful for sampling data,
        previewing datasets, and analyzing leading observations in actuarial analysis.
        It supports data exploration and focused subsets for detailed analysis.

        !!! note "When to use"
            * **Data Sampling:** Preview first few policies, claims, or transactions
              to understand data structure and validate import processes.
            * **Top Performance Analysis:** Extract first n highest-performing policies,
              agents, or products after sorting by relevant metrics.
            * **Time Series Analysis:** Get first n periods of policy data, premium
              payments, or claim events for trend analysis and forecasting.
            * **Quality Control:** Sample first n records from data loads to verify
              format, completeness, and accuracy before full processing.
            * **Reporting Limits:** Create executive summaries showing top n risks,
              largest policies, or most significant claims for management review.
            * **Model Development:** Use first n observations for initial model
              training or validation in actuarial modeling workflows.

        Parameters
        ----------
        n : int | Expr, default 10
            Number of values to return from the beginning of the column.
            Must be non-negative.

        Returns
        -------
        ExpressionProxy
            An expression containing the first n values in original order.
            If used within group_by context, returns first n values per group.

        Examples
        --------
        **Scalar Example: First 3 Largest Claims**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            top_claims=af["claim_amount"]
            .polars_native()
            .sort(descending=True)
            .polars_native()
            .head(3)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌────────────┐
        │ top_claims │
        │ ---        │
        │ f64        │
        ╞════════════╡
        │ 4800.0     │
        │ 3200.0     │
        │ 2500.0     │
        └────────────┘
        ```

        **Vector Example: First 3 Premium Payments**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "monthly_payments": [
                [1200.0, 1200.0, 1250.0, 1250.0, 1300.0],
                [1100.0, 1150.0, 1100.0, 1200.0, 1250.0],
            ],
        }
        af = ActuarialFrame(data)

        af.first_payments = af.monthly_payments.polars_native().list.head(3)

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬────────────────────────────┬──────────────────────────┐
        │ policy_id ┆ monthly_payments           ┆ first_payments           │
        │ ---       ┆ ---                        ┆ ---                      │
        │ str       ┆ list[f64]                  ┆ list[f64]                │
        ╞═══════════╪════════════════════════════╪══════════════════════════╡
        │ P001      ┆ [1200.0, 1200.0, … 1300.0] ┆ [1200.0, 1200.0, 1250.0] │
        │ P002      ┆ [1100.0, 1150.0, … 1250.0] ┆ [1100.0, 1150.0, 1100.0] │
        └───────────┴────────────────────────────┴──────────────────────────┘
        ```
        """
        return _mint(self, "head", (n,), {}, namespace=None)

    def tail(self, n: object = 10) -> ExpressionProxy:
        r"""Return the last n values from this expression or column.

        Retrieves the bottom n values in their original order, useful for analyzing
        recent observations, final periods, and ending patterns in actuarial datasets.
        Essential for understanding recent trends and validating data completeness.

        !!! note "When to use"
            * **Recent Analysis:** Extract last n policy renewals, recent claims,
              or latest premium payments to analyze current portfolio trends.
            * **Data Validation:** Check last n records from data loads to ensure
              complete file transmission and proper ending sequences.
            * **Time Series Endings:** Analyze final periods of policy lifecycles,
              claim development patterns, or investment performance cycles.
            * **Quality Control:** Sample last n transactions to verify batch
              processing completeness and identify potential truncation issues.
            * **Performance Tracking:** Review most recent n sales, lapses, or
              claim settlements for current performance assessment.
            * **Model Validation:** Use recent n observations for out-of-time
              testing and model performance evaluation on latest data.

        Parameters
        ----------
        n : int | Expr, default 10
            Number of values to return from the end of the column.
            Must be non-negative.

        Returns
        -------
        ExpressionProxy
            An expression containing the last n values in original order.
            If used within group_by context, returns last n values per group.

        Examples
        --------
        **Scalar Example: Last 3 Claims by Amount**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            recent_claims=af["claim_amount"].polars_native().tail(3)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌───────────────┐
        │ recent_claims │
        │ ---           │
        │ f64           │
        ╞═══════════════╡
        │ 1200.0        │
        │ 800.0         │
        │ 3200.0        │
        └───────────────┘
        ```

        **Vector Example: Last 3 Premium Payments**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "monthly_payments": [
                [1200.0, 1200.0, 1250.0, 1250.0, 1300.0],
                [1100.0, 1150.0, 1100.0, 1200.0, 1250.0],
            ],
        }
        af = ActuarialFrame(data)

        af.last_payments = af.monthly_payments.polars_native().list.tail(3)

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬────────────────────────────┬──────────────────────────┐
        │ policy_id ┆ monthly_payments           ┆ last_payments            │
        │ ---       ┆ ---                        ┆ ---                      │
        │ str       ┆ list[f64]                  ┆ list[f64]                │
        ╞═══════════╪════════════════════════════╪══════════════════════════╡
        │ P001      ┆ [1200.0, 1200.0, … 1300.0] ┆ [1250.0, 1250.0, 1300.0] │
        │ P002      ┆ [1100.0, 1150.0, … 1250.0] ┆ [1100.0, 1200.0, 1250.0] │
        └───────────┴────────────────────────────┴──────────────────────────┘
        ```
        """
        return _mint(self, "tail", (n,), {}, namespace=None)

    def filter(self, *predicates: object, **constraints: object) -> ExpressionProxy:
        r"""Filter values based on a boolean condition.

        Selects only values that meet the specified criteria, returning a subset
        of the original data. Essential for subsetting actuarial datasets based
        on business rules, risk criteria, or analytical requirements.

        !!! note "When to use"
            * **Risk Segmentation:** Filter policies by age bands, coverage amounts,
              or risk scores to create homogeneous groups for analysis.
            * **Claim Analysis:** Select claims above certain thresholds, within
              specific date ranges, or meeting particular criteria for investigation.
            * **Regulatory Compliance:** Filter data to meet reporting requirements,
              such as policies above regulatory minimums or within jurisdiction rules.
            * **Performance Analysis:** Select high-performing agents, profitable
              products, or customers meeting specific value criteria.
            * **Data Quality:** Filter out invalid, incomplete, or suspicious records
              before performing actuarial calculations or statistical analysis.
            * **Portfolio Management:** Select policies due for renewal, claims
              requiring review, or customers eligible for specific programs.

        Parameters
        ----------
        *predicates : object
            One or more positional boolean predicates, combined with AND.
        **constraints : object
            Column-name equality constraints, combined with the predicates.

        Returns
        -------
        ExpressionProxy
            An expression containing only values that satisfy the predicate.
            When used within group_by context, filters values within each group.

        Examples
        --------
        **Scalar Example: Filter High-Value Claims**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": ["C001", "C002", "C003", "C004", "C005"],
            "claim_amount": [2500.0, 4800.0, 1200.0, 800.0, 3200.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            high_claims=af["claim_amount"]
            .polars_native()
            .filter(af["claim_amount"] > 2000.0)
        ).collect()
        print(result)
        ```

        ```text
        shape: (3, 1)
        ┌─────────────┐
        │ high_claims │
        │ ---         │
        │ f64         │
        ╞═════════════╡
        │ 2500.0      │
        │ 4800.0      │
        │ 3200.0      │
        └─────────────┘
        ```

        **Vector Example: Filter High Premium Payments**

        ```python
        from gaspatchio import ActuarialFrame
        import polars as pl

        data = {
            "policy_id": ["P001", "P002"],
            "monthly_payments": [
                [1200.0, 1100.0, 1250.0, 1050.0, 1300.0],
                [1100.0, 1150.0, 1300.0, 1200.0, 1050.0],
            ],
        }
        af = ActuarialFrame(data)

        af.high_payments = (
            af.monthly_payments.polars_native()
            .list.eval(pl.when(pl.element() >= 1200).then(pl.element()))
            .polars_native()
            .list.drop_nulls()
        )

        print(af.collect())
        ```

        ```text
        shape: (2, 3)
        ┌───────────┬────────────────────────────┬──────────────────────────┐
        │ policy_id ┆ monthly_payments           ┆ high_payments            │
        │ ---       ┆ ---                        ┆ ---                      │
        │ str       ┆ list[f64]                  ┆ list[f64]                │
        ╞═══════════╪════════════════════════════╪══════════════════════════╡
        │ P001      ┆ [1200.0, 1100.0, … 1300.0] ┆ [1200.0, 1250.0, 1300.0] │
        │ P002      ┆ [1100.0, 1150.0, … 1050.0] ┆ [1300.0, 1200.0]         │
        └───────────┴────────────────────────────┴──────────────────────────┘
        ```
        """
        return _mint(self, "filter", predicates, constraints, namespace=None)

    def shift(
        self, n: object = 1, *, fill_value: object | None = None
    ) -> ExpressionProxy:
        r"""Shift values by a specified number of periods.

        Moves values forward or backward in the sequence, creating lag or lead variables
        essential for time series analysis, policy lifecycle tracking, and comparative
        calculations in actuarial modeling and trend analysis.

        !!! note "When to use"
            * **Time Series Analysis:** Create lag variables for premium payments,
              claim frequencies, or mortality rates to analyze trends and correlations.
            * **Policy Lifecycle Tracking:** Compare current year values with previous
              years for renewal analysis, lapse prediction, and persistency studies.
            * **Comparative Analysis:** Calculate period-over-period changes in
              reserves, capital requirements, or portfolio performance metrics.
            * **Risk Modeling:** Create lagged risk factors for predictive models,
              such as previous claims history or prior period exposures.
            * **Regulatory Reporting:** Generate comparative figures showing changes
              from previous reporting periods for regulatory filings.
            * **Performance Measurement:** Calculate growth rates, variance analysis,
              and trend indicators using historical comparison periods.

        Through the escape this shifts down the model points, so a per-period
        column is refused: Polars reads the whole column as one value per
        policy and would move values between policies rather than between
        periods, returning the right shape with nothing to say which axis it
        used. Both examples below take a per-policy column, where the shift is
        ordinary row semantics. For the per-period meaning, evaluate it inside
        each policy's own list --
        ``polars_native().list.eval(pl.element().shift(...))``.

        Parameters
        ----------
        n : int, default 1
            Number of periods to shift. Positive values shift forward (creating lags),
            negative values shift backward (creating leads). Zero returns the
            original values.
        fill_value : any, optional
            Value used to fill shifted positions. If None, uses null values.
            Can be a scalar value, expression, or column reference.

        Returns
        -------
        ExpressionProxy
            An expression with values shifted by the specified number of periods.
            Shifted positions contain ``fill_value``, or null when it is omitted.

        Examples
        --------
        **Scalar Example: Create Lag Variable for Premium Analysis**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_year": [1, 2, 3, 4, 5],
            "annual_premium": [1200.0, 1260.0, 1323.0, 1389.0, 1458.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_year"],
            current_premium=af["annual_premium"],
            prior_premium=af["annual_premium"].polars_native().shift(1),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────────────┬───────────────┐
        │ policy_year ┆ current_premium ┆ prior_premium │
        │ ---         ┆ ---             ┆ ---           │
        │ i64         ┆ f64             ┆ f64           │
        ╞═════════════╪═════════════════╪═══════════════╡
        │ 1           ┆ 1200.0          ┆ null          │
        │ 2           ┆ 1260.0          ┆ 1200.0        │
        │ 3           ┆ 1323.0          ┆ 1260.0        │
        │ 4           ┆ 1389.0          ┆ 1323.0        │
        │ 5           ┆ 1458.0          ┆ 1389.0        │
        └─────────────┴─────────────────┴───────────────┘
        ```

        **Vector Example: Quarterly Claims Comparison with Fill Value**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "quarter": ["Q1", "Q2", "Q3", "Q4"],
            "claim_count": [45, 52, 38, 49],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["quarter"],
            current_claims=af["claim_count"],
            next_quarter_claims=af["claim_count"].polars_native().shift(-1),
            prior_quarter_with_fill=af["claim_count"]
            .polars_native()
            .shift(1, fill_value=0),
        ).collect()
        print(result)
        ```

        ```text
        shape: (4, 4)
        ┌─────────┬────────────────┬─────────────────────┬─────────────────────────┐
        │ quarter ┆ current_claims ┆ next_quarter_claims ┆ prior_quarter_with_fill │
        │ ---     ┆ ---            ┆ ---                 ┆ ---                     │
        │ str     ┆ i64            ┆ i64                 ┆ i64                     │
        ╞═════════╪════════════════╪═════════════════════╪═════════════════════════╡
        │ Q1      ┆ 45             ┆ 52                  ┆ 0                       │
        │ Q2      ┆ 52             ┆ 38                  ┆ 45                      │
        │ Q3      ┆ 38             ┆ 49                  ┆ 52                      │
        │ Q4      ┆ 49             ┆ null                ┆ 38                      │
        └─────────┴────────────────┴─────────────────────┴─────────────────────────┘
        ```
        """
        return _mint(self, "shift", (n,), {"fill_value": fill_value}, namespace=None)

    def over(
        self,
        partition_by: object = None,
        *more_exprs: object,
        order_by: object = None,
        descending: bool = False,
        nulls_last: bool = False,
        mapping_strategy: str = "group_to_rows",
    ) -> ExpressionProxy:
        r"""Apply window function over partitions defined by grouping columns.

        Performs calculations within groups while maintaining the original row
        structure,
        enabling sophisticated analytical computations like running totals, rankings,
        and comparative metrics essential for actuarial analysis and portfolio
        management.

        !!! note "When to use"
            * **Running Calculations:** Compute cumulative premiums, running
              claim totals,
              or progressive reserves within policy groups or time periods.
            * **Ranking Analysis:** Rank policies by premium size, claims by amount,
              or agents by performance within their respective categories.
            * **Comparative Metrics:** Calculate percentiles, relative positions, or
              comparative ratios within peer groups for benchmarking analysis.
            * **Window Statistics:** Compute rolling averages, moving sums, or
              time-based aggregations within policy or customer segments.
            * **Portfolio Analytics:** Calculate portfolio-level metrics while
              maintaining individual policy detail for drill-down analysis.
            * **Regulatory Reporting:** Generate group-level statistics required
              for regulatory filings while preserving transaction-level detail.

        Parameters
        ----------
        partition_by : object
            Expression or name defining the primary window group.
        *more_exprs : object
            Additional expressions or names defining the window group.
        mapping_strategy : str, default "group_to_rows"
            Strategy for mapping grouped results back to the original rows.
        order_by : object or None, default None
            Expression used to order rows within each window group.
        descending : bool, default False
            Whether ``order_by`` uses descending order.
        nulls_last : bool, default False
            Whether null ordering values appear last.

        Returns
        -------
        ExpressionProxy
            An expression with window function results mapped to each row based
            on its partition membership.

        Examples
        --------
        **Scalar Example: Running Premium Total by Policy Type**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_type": ["TERM", "TERM", "WHOLE", "WHOLE", "TERM"],
            "premium": [1200.0, 1500.0, 2000.0, 2200.0, 1100.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["policy_type"],
            af["premium"],
            running_total=af["premium"]
            .polars_native()
            .sum()
            .polars_native()
            .over("policy_type"),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌─────────────┬─────────┬───────────────┐
        │ policy_type ┆ premium ┆ running_total │
        │ ---         ┆ ---     ┆ ---           │
        │ str         ┆ f64     ┆ f64           │
        ╞═════════════╪═════════╪═══════════════╡
        │ TERM        ┆ 1200.0  ┆ 3800.0        │
        │ TERM        ┆ 1500.0  ┆ 3800.0        │
        │ WHOLE       ┆ 2000.0  ┆ 4200.0        │
        │ WHOLE       ┆ 2200.0  ┆ 4200.0        │
        │ TERM        ┆ 1100.0  ┆ 3800.0        │
        └─────────────┴─────────┴───────────────┘
        ```

        **Vector Example: Rank Claims within Age Groups**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "age_band": ["30-39", "30-39", "40-49", "40-49", "30-39"],
            "claim_amount": [1200.0, 2500.0, 1800.0, 3200.0, 900.0],
        }
        af = ActuarialFrame(data)
        result = af.select(
            af["age_band"],
            af["claim_amount"],
            rank_in_band=af["claim_amount"]
            .polars_native()
            .rank(method="ordinal")
            .polars_native()
            .over("age_band"),
        ).collect()
        print(result)
        ```

        ```text
        shape: (5, 3)
        ┌──────────┬──────────────┬──────────────┐
        │ age_band ┆ claim_amount ┆ rank_in_band │
        │ ---      ┆ ---          ┆ ---          │
        │ str      ┆ f64          ┆ u64          │
        ╞══════════╪══════════════╪══════════════╡
        │ 30-39    ┆ 1200.0       ┆ 2            │
        │ 30-39    ┆ 2500.0       ┆ 3            │
        │ 40-49    ┆ 1800.0       ┆ 1            │
        │ 40-49    ┆ 3200.0       ┆ 2            │
        │ 30-39    ┆ 900.0        ┆ 1            │
        └──────────┴──────────────┴──────────────┘
        ```
        """
        return _mint(
            self,
            "over",
            (partition_by, *more_exprs),
            {
                "order_by": order_by,
                "descending": descending,
                "nulls_last": nulls_last,
                "mapping_strategy": mapping_strategy,
            },
            namespace=None,
        )


class _DocumentedPolarsStringMethods:
    """Previously documented real methods of Polars' string namespace.

    Historical aliases are retired and their useful guidance belongs under
    the corresponding current Polars spelling.
    """

    __slots__ = ()

    def contains(
        self, pattern: object, *, literal: bool = False, strict: bool = True
    ) -> ExpressionProxy:
        r"""Check whether strings in a column contain a specified pattern.

        This method searches for a pattern within string values, returning a boolean
        indicating if the pattern exists in each string. It's useful for filtering,
        data categorization, and identifying records with specific text patterns.

        !!! note "When to use"
            * Identify policies with specific riders or endorsements from
              description fields
            * Find claims that mention particular medical conditions or causes
            * Filter customer feedback containing specific keywords for risk analysis
            * Segment policyholders based on address information (e.g., rural vs urban)
            * Flag policies or claims with special handling notes (e.g., "legal review")
            * Screen underwriting notes for high-risk indicators

        Args:
            pattern (str | pl.Expr): The substring or regex pattern to search for.
                Can be a literal string (e.g., "RiderX") or a Polars expression
                (e.g., `pl.col("other_column_with_patterns")`).
            literal (bool, optional): If True, `pattern` is treated as a literal string.
                If False (default), `pattern` is treated as a regex.
            strict (bool, optional): If True and `pattern` is a Polars expression,
                an error is raised if `pattern` is not a string type. If False
                (default), `pattern` is cast to string if possible.

        Returns:
            ExpressionProxy: A new `ExpressionProxy` containing a boolean Series
                indicating for each input string whether the pattern was found.
                If the input was `List[String]`, the output will be `List[bool]`.

        Examples:
            **Scalar Example: Identifying policies with an Accidental Death
            Benefit (ADB) rider**

            Imagine you have a dataset of policy descriptions and you want to flag
            all policies that include an "ADB" rider.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003", "POL004"],
                "description": [
                    "Term Life Plan with ADB rider",
                    "Whole Life - Standard",
                    "Universal Life, includes ADB rider and Accidental Death "
                    "Benefit (ADB)",
                    "Term Life, no Accidental Death Benefit rider",
                ],
            }
            af = ActuarialFrame(data)
            af_with_adb_rider = af.select(
                af["description"]
                .polars_native()
                .str.contains("ADB rider", literal=True)
                .polars_native()
                .alias("has_adb_rider")
            )
            print(af_with_adb_rider.collect())
            ```

            ```text
            shape: (4, 1)
            ┌───────────────┐
            │ has_adb_rider │
            │ ---           │
            │ bool          │
            ╞═══════════════╡
            │ true          │
            │ false         │
            │ true          │
            │ false         │
            └───────────────┘
            ```

            **Vector Example: Checking underwriter notes for high-risk keywords**

            Suppose each policy has a list of notes from underwriters. We want to check
            if any note for a given policy contains keywords like "medical history"
            or "hazardous occupation", which might indicate higher risk.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            uw_notes_data = {
                "policy_id": ["UW001", "UW002", "UW003"],
                "underwriter_notes": [
                    "Standard risk. Family history clear.",
                    "Applicant works in construction. Reviewed medical history: "
                    "smoker.",
                    "No concerning notes. Possible hazardous occupation mentioned.",
                ],
            }
            af_notes = ActuarialFrame(uw_notes_data)
            af_results = af_notes.select(
                af_notes["underwriter_notes"]
                .polars_native()
                .str.contains("medical history")
                .polars_native()
                .alias("mentions_medical_history"),
                af_notes["underwriter_notes"]
                .polars_native()
                .str.contains("(?i)hazardous occupation")
                .polars_native()
                .alias("mentions_hazardous_occupation"),
            )
            print(af_results.collect())
            ```

            ```text
            shape: (3, 2)
            ┌──────────────────────────┬───────────────────────────────┐
            │ mentions_medical_history ┆ mentions_hazardous_occupation │
            │ ---                      ┆ ---                           │
            │ bool                     ┆ bool                          │
            ╞══════════════════════════╪═══════════════════════════════╡
            │ false                    ┆ false                         │
            │ true                     ┆ false                         │
            │ false                    ┆ true                          │
            └──────────────────────────┴───────────────────────────────┘
            ```

            **Using `contains` with a list of patterns (regex and literal)**

            Suppose we want to check for multiple keywords in underwriter notes
            using both
            literal and regex matching.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            uw_notes_data_multi = {  # Renamed to avoid conflict
                "policy_id": ["UW001", "UW002", "UW003"],
                "underwriter_notes": [
                    "Standard risk. Family history clear.",
                    "Applicant works in construction. Reviewed medical history: "
                    "smoker.",
                    "No concerning notes. Possible hazardous occupation mentioned.",
                ],
            }
            af_multi = ActuarialFrame(uw_notes_data_multi)
            af_multi_processed = af_multi.select(
                # Literal check
                af_multi["underwriter_notes"]
                .polars_native()
                .str.contains("medical history", literal=True)
                .polars_native()
                .alias("literal_medical"),
                # Regex check (case insensitive)
                af_multi["underwriter_notes"]
                .polars_native()
                .str.contains(r"(?i)hazardous occupation")
                .polars_native()
                .alias("regex_hazardous"),
                # Another Regex check (case insensitive) for medical history
                af_multi["underwriter_notes"]
                .polars_native()
                .str.contains(r"(?i)medical history")
                .polars_native()
                .alias("regex_medical"),
            )
            print(af_multi_processed.collect())
            ```

            ```text
            shape: (3, 3)
            ┌─────────────────┬─────────────────┬───────────────┐
            │ literal_medical ┆ regex_hazardous ┆ regex_medical │
            │ ---             ┆ ---             ┆ ---           │
            │ bool            ┆ bool            ┆ bool          │
            ╞═════════════════╪═════════════════╪═══════════════╡
            │ false           ┆ false           ┆ false         │
            │ true            ┆ false           ┆ true          │
            │ false           ┆ true            ┆ false         │
            └─────────────────┴─────────────────┴───────────────┘
            ```
        """
        return _mint(
            self,
            "contains",
            (pattern,),
            {"literal": literal, "strict": strict},
            namespace="str",
        )

    def to_uppercase(self) -> ExpressionProxy:
        r"""Convert all characters in string columns to uppercase.

        This function standardizes textual data by converting all characters in a
        string column to uppercase. This is essential for ensuring consistency
        in data fields critical for actuarial analysis, such as policy status
        codes, product identifiers, or geographical regions, facilitating
        accurate matching, aggregation, and reporting.

        !!! note "When to use"
            *   **Standardizing Categorical Data:** Ensuring that codes like
                policy status
                (e.g., "active", "Lapsed", "ACTIVE" all become "ACTIVE"), gender codes
                (e.g., "m", "F" become "M", "F"), or smoker status (e.g. "non-smoker",
                "Smoker" become "NON-SMOKER", "SMOKER") are consistent for grouping
                and analysis.
            *   **Improving Data Matching:** Facilitating joins and lookups between
                different datasets where case sensitivity might cause mismatches
                (e.g., matching policyholder names or addresses from different sources).
            *   **Enhancing Readability and Reporting:** Presenting data in a uniform
                case for reports and dashboards, especially for identifiers or codes.
            *   **Preparing Text for Analysis:** As a preprocessing step before text
                mining or natural language processing tasks on fields like claim
                descriptions or underwriter notes, where case normalization can
                simplify pattern recognition.
            *   **Simplifying Rule-Based Logic:** When applying business rules that
                depend on string comparisons (e.g., identifying policies with specific
                rider codes like "ADB" or "WP" irrespective of their original casing).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with strings converted to
                uppercase.

        Examples:
            **Scalar Example: Standardizing policy status codes**

            Policy status might be entered in various cases ("active",
            "lapsed", "ACTIVE").
            Converting to uppercase ensures consistency for analysis.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data = {
                "policy_id": ["S3001", "S3002", "S3003", "S3004"],
                "status_raw": ["active", "lapsed", "Active", "PENDING"],
            }
            af = ActuarialFrame(data)
            af_upper_status = af.select(
                af["status_raw"]
                .polars_native()
                .str.to_uppercase()
                .polars_native()
                .alias("status_standardized")
            )
            print(af_upper_status.collect())
            ```

            ```text
            shape: (4, 1)
            ┌─────────────────────┐
            │ status_standardized │
            │ ---                 │
            │ str                 │
            ╞═════════════════════╡
            │ ACTIVE              │
            │ LAPSED              │
            │ ACTIVE              │
            │ PENDING             │
            └─────────────────────┘
            ```

            **Vector Example: Uppercasing rider codes for a policy**

            A policy might have multiple rider codes stored in a list. To ensure
            uniformity, we can convert all rider codes to uppercase.

            ```python
            import polars as pl
            from gaspatchio.frame.base import ActuarialFrame

            data_policy_riders = {
                "policy_id": ["R4001", "R4002", "R4003"],
                "rider_codes_str": ["adb,wp", "ci,ltc,acc_death", "gio"],
            }
            af_riders = ActuarialFrame(data_policy_riders)
            # Convert string to list for the string operation
            af_riders = af_riders.with_columns(
                af_riders["rider_codes_str"]
                .polars_native()
                .str.split(",")
                .polars_native()
                .alias("rider_codes_list")
            )
            af_upper_riders = af_riders.select(
                af_riders["rider_codes_list"]
                .polars_native()
                .list.eval(pl.element().str.to_uppercase())
                .polars_native()
                .alias("upper_rider_codes")
            )
            print(af_upper_riders.collect())
            ```

            ```text
            shape: (3, 1)
            ┌────────────────────────────┐
            │ upper_rider_codes          │
            │ ---                        │
            │ list[str]                  │
            ╞════════════════════════════╡
            │ ["ADB", "WP"]              │
            │ ["CI", "LTC", "ACC_DEATH"] │
            │ ["GIO"]                    │
            └────────────────────────────┘
            ```
        """
        return _mint(self, "to_uppercase", (), {}, namespace="str")

    def to_lowercase(self) -> ExpressionProxy:
        r"""Convert all characters in string columns to lowercase.

        This function standardizes textual data by converting all characters in a
        string column to lowercase. This is essential for ensuring consistency
        in data fields critical for actuarial analysis, such as system codes,
        free-text fields like occupation or medical conditions, or external data
        sources,
        facilitating accurate matching, aggregation, and text analysis.

        !!! note "When to use"
            *   **Normalizing Text for Analysis:** Preparing free-text fields (e.g.,
                underwriting notes, claim descriptions, occupation details) for
                text mining
                or NLP by ensuring terms like "SMOKER", "Smoker", and "smoker" are
                treated identically.
            *   **Improving Data Matching with External Sources:** When integrating data
                from various systems or third-party providers where case consistency
                is not guaranteed (e.g., matching addresses, names, or city
                information).
            *   **Standardizing User Input:** Converting user-entered data (e.g., search
                terms, filter criteria) to a consistent case before processing or
                querying.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings converted to lowercase.

        Examples:
            **Scalar Example: Normalizing occupation descriptions for risk analysis**

            Occupation descriptions might be entered in various casings. Converting to
            lowercase helps in standardizing them for consistent risk factor analysis
            or grouping.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003", "POL004"],
                "occupation_raw": [
                    "Engineer",
                    "software DEVELOPER",
                    "Teacher",
                    "Project Manager",
                ],
            }
            af = ActuarialFrame(data)
            af_lower_occupation = af.select(
                af["occupation_raw"]
                .polars_native()
                .str.to_lowercase()
                .polars_native()
                .alias("occupation_normalized")
            )
            print(af_lower_occupation.collect())
            ```

            ```text
            shape: (4, 1)
            ┌───────────────────────┐
            │ occupation_normalized │
            │ ---                   │
            │ str                   │
            ╞═══════════════════════╡
            │ engineer              │
            │ software developer    │
            │ teacher               │
            │ project manager       │
            └───────────────────────┘
            ```

            **Vector Example: Lowercasing medical condition codes from multiple
            sources**

            Medical condition codes can arrive from systems with varying casing.
            Lowercasing them ensures they can be consistently mapped or analyzed.

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "claim_id": ["C001", "C002"],
                "condition_codes": [
                    ["DIAB_T2", "HBP", "ASTHMA"],
                    ["hbp", None, "COPD"],
                ],
            }
            af = ActuarialFrame(data)

            af.lower_codes = af.condition_codes.polars_native().list.eval(
                pl.element().str.to_lowercase()
            )

            print(af.collect())
            ```

            ```text
            shape: (2, 3)
            ┌──────────┬──────────────────────────────┬──────────────────────────────┐
            │ claim_id ┆ condition_codes              ┆ lower_codes                  │
            │ ---      ┆ ---                          ┆ ---                          │
            │ str      ┆ list[str]                    ┆ list[str]                    │
            ╞══════════╪══════════════════════════════╪══════════════════════════════╡
            │ C001     ┆ ["DIAB_T2", "HBP", "ASTHMA"] ┆ ["diab_t2", "hbp", "asthma"] │
            │ C002     ┆ ["hbp", null, "COPD"]        ┆ ["hbp", null, "copd"]        │
            └──────────┴──────────────────────────────┴──────────────────────────────┘
            ```
        """
        return _mint(self, "to_lowercase", (), {}, namespace="str")

    def len_chars(self) -> ExpressionProxy:
        r"""Alias for `n_chars`. Get the number of characters in each string.

        Calculates the length of each string in a column, returning an integer
        representing the number of characters. This is an alias for `n_chars()`.

        !!! note "When to use"
            *   **Data Validation:** Ensuring identifiers like policy numbers, social
                security numbers, or postal codes adhere to expected length constraints,
                helping to identify data entry errors.
            *   **System Integration:** Verifying that string data, such as
                client names or
                addresses, does not exceed length limitations of downstream systems or
                databases.
            *   **Feature Engineering:** Using the length of free-text fields
                (e.g., claim
                descriptions, underwriter notes) as a potential feature in predictive
                models, where length might correlate with complexity or severity.
            *   **Data Quality Assessment:** Identifying outliers or anomalies in string
                lengths that might indicate corrupted or incomplete data.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the character count (as UInt32)
                             for each string. If the input was `List[String]`,
                             the output will be `List[UInt32]`.

        Examples:
            **Scalar Example: Validating policy number length**

            Scenario: You need to check if policy numbers in your dataset conform to an
            expected length, say 7 characters.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data = {
                "policy_id_raw": ["POL1234", "POL567", "POL89012", None, "POL3456"],
                "premium": [100.0, 150.0, 200.0, 50.0, 120.0],
            }
            af = ActuarialFrame(data)

            # Calculate the length of each policy_id_raw
            af_len_check = af.select(
                af["policy_id_raw"]
                .polars_native()
                .str.len_chars()
                .polars_native()
                .alias("policy_id_length")
            )
            print(af_len_check.collect())
            ```

            ```text
            shape: (5, 1)
            ┌──────────────────┐
            │ policy_id_length │
            │ ---              │
            │ u32              │
            ╞══════════════════╡
            │ 7                │
            │ 6                │
            │ 8                │
            │ null             │
            │ 7                │
            └──────────────────┘
            ```

            **Vector Example: Character count of claim notes**

            Scenario: Each policy may have a list of associated claim notes.
            Measure each note's character length for display or analysis.

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P7001", "P7002"],
                "claim_notes": [
                    [
                        "Short note.",
                        "This is a much longer note regarding the claim details.",
                        None,
                    ],
                    ["Urgent review needed!", "All clear."],
                ],
            }
            af = ActuarialFrame(data)

            af.note_lengths = af.claim_notes.polars_native().list.eval(
                pl.element().str.len_chars()
            )

            print(af.select("note_lengths").collect())
            ```

            ```text
            shape: (2, 1)
            ┌────────────────┐
            │ note_lengths   │
            │ ---            │
            │ list[u32]      │
            ╞════════════════╡
            │ [11, 55, null] │
            │ [21, 10]       │
            └────────────────┘
            ```
        """
        return _mint(self, "len_chars", (), {}, namespace="str")

    def len_bytes(self) -> ExpressionProxy:
        r"""Get the number of bytes in each string.

        Calculates the byte length of each string in a column. This is particularly
        useful when dealing with multi-byte character encodings (like UTF-8) where
        the number of characters may not equal the number of bytes.

        !!! note "When to use"
            *   **Data Storage Estimation:** Estimating storage requirements for
                datasets containing text fields, especially with international
                character sets
                (e.g., policyholder names, addresses from various regions).
            *   **System Integration Limits:** Ensuring that exported string data
                sent to other systems, conforms to byte-length restrictions imposed by
                those systems (e.g., fixed-width files or database constraints
                defined in bytes).
            *   **Performance Considerations:** Recognizing that operations on
                strings with
                many multi-byte characters might be more resource-intensive.
            *   **Encoding Issue Detection:** Unexpected byte lengths compared to
                character lengths might hint at encoding problems
                or the presence of unusual characters.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with the byte count (as UInt32)
                             for each string. If the input was `List[String]`,
                             the output will be `List[UInt32]`.

        Examples:
            **Scalar Example: Byte length of UTF-8 encoded client names**

            Scenario: You have client names that may include characters from various
            languages, and you need to understand their storage size in bytes.

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data = {
                "client_id": ["C001", "C002", "C003", "C004"],
                "client_name": [
                    "René",
                    "沐宸",
                    "Zoë",
                    "John Doe",
                ],  # French, Chinese, German, English names
            }
            af = ActuarialFrame(data)
            af_byte_len = af.select(
                af["client_name"]
                .polars_native()
                .str.len_bytes()
                .polars_native()
                .alias("name_byte_length")
            )
            print(af_byte_len.collect())
            ```

            ```text
            shape: (4, 1)
            ┌──────────────────┐
            │ name_byte_length │
            │ ---              │
            │ u32              │
            ╞══════════════════╡
            │ 5                │
            │ 6                │
            │ 4                │
            │ 8                │
            └──────────────────┘
            ```

            **Vector Example: Byte length of free-text comments in a list**

            Scenario: A policy record contains a list of comments, potentially with
            special characters or different languages. You need to find the byte
            length of each comment.

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P501", "P502"],
                "comments": [
                    ["Test € symbol", "Standard comment.", None],
                    ["Résumé", "日本語のコメント"],
                ],
            }
            af = ActuarialFrame(data)

            af.byte_lengths = af.comments.polars_native().list.eval(
                pl.element().str.len_bytes()
            )

            print(af.select("byte_lengths").collect())
            ```

            ```text
            shape: (2, 1)
            ┌────────────────┐
            │ byte_lengths   │
            │ ---            │
            │ list[u32]      │
            ╞════════════════╡
            │ [15, 17, null] │
            │ [8, 24]        │
            └────────────────┘
            ```
        """
        return _mint(self, "len_bytes", (), {}, namespace="str")

    def strip_chars(self, characters: object = None) -> ExpressionProxy:
        r"""Remove specified leading and trailing characters from strings.

        This is useful for cleaning data, such as removing unwanted prefixes,
        suffixes, or whitespace from policy numbers, client names, or address fields.
        It mirrors Polars' `Expr.str.strip_chars`. If no characters are specified,
        it defaults to removing leading and trailing whitespace.
        For `List[String]` columns, like a list of addresses for a client,
        the operation is applied element-wise to each string in the list.

        !!! note "When to use"
            *   **Cleanse Identifier Fields:** Remove spaces, hyphens, and
                symbols from identifiers for consistent matching and lookups.
                For example, "POL- 123* " could become "POL-123" by stripping " *".
            *   **Standardize Textual Data:** Trim surrounding whitespace from
                descriptions, addresses, or notes before analysis or storage.
            *   **Prepare Data for Joins:** Clean and standardize string join
                keys to avoid failures caused by trailing spaces.
            *   **Sanitize User Input:** Clean user-provided search terms or
                filter values by removing
                unwanted characters before using them in queries.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from both ends of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with the specified characters
                stripped from the strings.

        Examples:
            **Scalar Example: Cleaning Policy Numbers**

            Policy numbers might contain inconsistent characters that need
            removal.

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003", "P004"],
                "policy_number_raw": [" POL-123* ", "ID-456-", "*789*", " ABC-999 "],
            }
            af = ActuarialFrame(data)

            af.policy_number_clean = (
                af.policy_number_raw.polars_native().str.strip_chars(" *-")
            )

            print(af.collect())
            ```

            ```text
            shape: (4, 3)
            ┌───────────┬───────────────────┬─────────────────────┐
            │ policy_id ┆ policy_number_raw ┆ policy_number_clean │
            │ ---       ┆ ---               ┆ ---                 │
            │ str       ┆ str               ┆ str                 │
            ╞═══════════╪═══════════════════╪═════════════════════╡
            │ P001      ┆  POL-123*         ┆ POL-123             │
            │ P002      ┆ ID-456-           ┆ ID-456              │
            │ P003      ┆ *789*             ┆ 789                 │
            │ P004      ┆  ABC-999          ┆ ABC-999             │
            └───────────┴───────────────────┴─────────────────────┘
            ```

            **Vector Example: Cleaning Lists of Rider Codes**

            Product codes for riders might be stored in a list with unwanted characters.

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P1001", "P1002"],
                "rider_codes_raw": [
                    ["*RIDER_A- ", " -RIDER_B*", "BASE_PLAN"],
                    [None, " *-RIDER_C- ", "    RIDER_D *"],
                ],
            }
            af = ActuarialFrame(data)

            af.rider_codes_clean = af.rider_codes_raw.polars_native().list.eval(
                pl.element().str.strip_chars(" *-      ")
            )

            print(af.select("rider_codes_clean").collect())
            ```

            ```text
            shape: (2, 1)
            ┌─────────────────────────────────────┐
            │ rider_codes_clean                   │
            │ ---                                 │
            │ list[str]                           │
            ╞═════════════════════════════════════╡
            │ ["RIDER_A", "RIDER_B", "BASE_PLAN"] │
            │ [null, "RIDER_C", "RIDER_D"]        │
            └─────────────────────────────────────┘
            ```
        """
        return _mint(self, "strip_chars", (characters,), {}, namespace="str")

    def strip_chars_start(self, characters: object = None) -> ExpressionProxy:
        r"""Remove specified leading characters from strings.

        Useful for standardizing data by removing known prefixes or initial
        whitespace. For instance, cleaning policy numbers by removing a
        "TEMP-" prefix or trimming spaces from the beginning of address lines.
        It mirrors Polars' `Expr.str.strip_chars_start`. If no characters are
        specified, it defaults to removing leading whitespace.
        When applied to `List[String]` columns (e.g., a list of historical
        status codes for a policy), the operation is performed element-wise.

        !!! note "When to use"
            *   **Normalizing Prefixed Identifiers:** Removing consistent prefixes from
                identifiers like policy numbers (e.g., "PN-", "TEMP_"), claim codes
                (e.g., "CL-"), or agent codes to get the core identifier.
            *   **Cleaning Leading Characters in Text Fields:** Remove leading
                bullets, numbers, symbols, or spaces from free-text fields.
            *   **Standardizing Data from Multiple Sources:** If source systems
                prefix
                the same data differently, this function can help unify them by removing
                those specific leading characters.

        Args:
            characters (str | pl.Expr, optional): A string of characters to remove
                from the start of each string. Can also be a Polars expression that
                evaluates to a string of characters. If None (default), removes
                leading whitespace (spaces, tabs, newlines, etc.).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` with specified leading
                characters stripped from the strings.

        Examples:
            **Scalar Example: Removing Leading Characters from Policy IDs**

            Legacy IDs might have prefixes or leading whitespace to clean.

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003", "P004"],
                "legacy_id": ["TEMP-123", "  456", " *789", "TEMP-ABC"],
            }
            af = ActuarialFrame(data)

            af.clean_id = af.legacy_id.polars_native().str.strip_chars_start(" TEMP-*")

            print(af.collect())
            ```

            ```text
            shape: (4, 3)
            ┌───────────┬───────────┬──────────┐
            │ policy_id ┆ legacy_id ┆ clean_id │
            │ ---       ┆ ---       ┆ ---      │
            │ str       ┆ str       ┆ str      │
            ╞═══════════╪═══════════╪══════════╡
            │ P001      ┆ TEMP-123  ┆ 123      │
            │ P002      ┆   456     ┆ 456      │
            │ P003      ┆  *789     ┆ 789      │
            │ P004      ┆ TEMP-ABC  ┆ ABC      │
            └───────────┴───────────┴──────────┘
            ```

            **Vector Example: Transaction Remarks**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002"],
                "remarks": [
                    [
                        "TEMP: Initial assessment",
                        "  Adjustment processed",
                        "Final Review",
                    ],
                    ["TEMP: Hold for now", "TEMP: Resolved", "Status: OK"],
                ],
            }
            af = ActuarialFrame(data)

            af.clean_remarks = af.remarks.polars_native().list.eval(
                pl.element().str.strip_chars_start("TEMP: ")
            )

            print(af.select("clean_remarks").collect())
            ```

            ```text
            shape: (2, 1)
            ┌────────────────────────────────────────────────────────────────┐
            │ clean_remarks                                                  │
            │ ---                                                            │
            │ list[str]                                                      │
            ╞════════════════════════════════════════════════════════════════╡
            │ ["Initial assessment", "Adjustment processed", "Final Review"] │
            │ ["Hold for now", "Resolved", "Status: OK"]                     │
            └────────────────────────────────────────────────────────────────┘
            ```
        """
        return _mint(self, "strip_chars_start", (characters,), {}, namespace="str")

    def strip_prefix(self, prefix: object) -> ExpressionProxy:
        r"""Remove a prefix from each string.

        The prefix is stripped whenever it occurs at the start of the string.
        Strings without the prefix are returned unchanged. On columns containing
        lists of strings, the removal happens element by element.

        !!! note "When to use"
            *   Cleaning temporary identifiers such as ``TEMP-123`` once a policy
                is fully underwritten.
            *   Harmonizing product codes from different administration systems
                before mapping them to an actuarial model.
            *   Stripping ``LEGACY-`` markers from lists of rider codes imported
                from historical sources.

        Args:
            prefix: Prefix to remove. May be a literal string or an expression
                that evaluates to a string.

        Returns:
            ExpressionProxy with the prefix removed.

        Examples:
            **Scalar Example: Policy IDs**

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003", "P004"],
                "pol_id_raw": ["TEMP-001", "TEMP-002", "003", None],
            }
            af = ActuarialFrame(data)

            af.pol_id_clean = af.pol_id_raw.polars_native().str.strip_prefix("TEMP-")

            print(af.collect())
            ```
            ```text
            shape: (4, 3)
            ┌───────────┬────────────┬──────────────┐
            │ policy_id ┆ pol_id_raw ┆ pol_id_clean │
            │ ---       ┆ ---        ┆ ---          │
            │ str       ┆ str        ┆ str          │
            ╞═══════════╪════════════╪══════════════╡
            │ P001      ┆ TEMP-001   ┆ 001          │
            │ P002      ┆ TEMP-002   ┆ 002          │
            │ P003      ┆ 003        ┆ 003          │
            │ P004      ┆ null       ┆ null         │
            └───────────┴────────────┴──────────────┘
            ```

            **Vector Example: Feature Codes**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002"],
                "feature_codes": [
                    ["LEGACY-RIDER1", "NEW_FEATURE_X", "LEGACY-BENEFIT2"],
                    ["LEGACY-COVERAGE_Y", "STANDARD_Z"],
                ],
            }
            af = ActuarialFrame(data)

            af.clean_codes = af.feature_codes.polars_native().list.eval(
                pl.element().str.strip_prefix("LEGACY-")
            )

            print(af.select("clean_codes").collect())
            ```
            ```text
            shape: (2, 1)
            ┌─────────────────────────────────────────┐
            │ clean_codes                             │
            │ ---                                     │
            │ list[str]                               │
            ╞═════════════════════════════════════════╡
            │ ["RIDER1", "NEW_FEATURE_X", "BENEFIT2"] │
            │ ["COVERAGE_Y", "STANDARD_Z"]            │
            └─────────────────────────────────────────┘
            ```
        """
        return _mint(self, "strip_prefix", (prefix,), {}, namespace="str")

    def strip_suffix(self, suffix: object) -> ExpressionProxy:
        r"""Remove a suffix from each string.

        If a string does not end with the given suffix, it is returned unchanged.
        For ``List[String]`` columns, the operation is applied element-wise.

        !!! note "When to use"
            *   **Normalizing coverage names** that include trailing version
                codes such as "-OLD".
            *   **Preparing ledger accounts** by removing year suffixes like
                "-2024" before comparing periods.
            *   **Cleaning temporary identifiers** by removing suffixes such as
                "-TMP" from values imported from external systems.

        Args:
            suffix: The suffix to remove, as a string literal or expression.

        Returns:
            ExpressionProxy: The expression with the suffix removed.

        Examples:
            **Scalar Example: Plan Names**

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003", "P004"],
                "plan_name_raw": [
                    "Term Basic-OLD",
                    "Income Protection-OLD",
                    "Annuity Plus",
                    None,
                ],
            }
            af = ActuarialFrame(data)

            af.plan_name = af.plan_name_raw.polars_native().str.strip_suffix("-OLD")

            print(af.collect())
            ```

            ```text
            shape: (4, 3)
            ┌───────────┬───────────────────────┬───────────────────┐
            │ policy_id ┆ plan_name_raw         ┆ plan_name         │
            │ ---       ┆ ---                   ┆ ---               │
            │ str       ┆ str                   ┆ str               │
            ╞═══════════╪═══════════════════════╪═══════════════════╡
            │ P001      ┆ Term Basic-OLD        ┆ Term Basic        │
            │ P002      ┆ Income Protection-OLD ┆ Income Protection │
            │ P003      ┆ Annuity Plus          ┆ Annuity Plus      │
            │ P004      ┆ null                  ┆ null              │
            └───────────┴───────────────────────┴───────────────────┘
            ```

            **Vector Example: Claim Notes**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002"],
                "notes": [
                    ["Approved.", "Paid."],
                    ["In Review."],
                ],
            }
            af = ActuarialFrame(data)

            af.notes_clean = af.notes.polars_native().list.eval(
                pl.element().str.strip_suffix(".")
            )

            print(af.collect())
            ```

            ```text
            shape: (2, 3)
            ┌───────────┬────────────────────────┬──────────────────────┐
            │ policy_id ┆ notes                  ┆ notes_clean          │
            │ ---       ┆ ---                    ┆ ---                  │
            │ str       ┆ list[str]              ┆ list[str]            │
            ╞═══════════╪════════════════════════╪══════════════════════╡
            │ P001      ┆ ["Approved.", "Paid."] ┆ ["Approved", "Paid"] │
            │ P002      ┆ ["In Review."]         ┆ ["In Review"]        │
            └───────────┴────────────────────────┴──────────────────────┘
            ```
        """
        return _mint(self, "strip_suffix", (suffix,), {}, namespace="str")

    def zfill(self, length: object) -> ExpressionProxy:
        r"""Pad strings with leading zeros to a minimum width.

        Shorter values are padded on the left with zeros so each entry reaches
        ``length`` characters. For list columns, the padding occurs element-wise.

        !!! note "When to use"
            *   Standardizing policy numbers from different administration
                systems before merging with valuation data
            *   Preparing zero-padded claim numbers for extracts sent to
                reinsurers or regulators
            *   Building fixed-width keys when joining to rating tables or
                mapping grids

        Args:
            length: The desired minimum length of the string.

        Returns:
            ExpressionProxy: Strings padded with leading zeros.

        Examples:
            **Scalar Example: Policy Serial Numbers**

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003", "P004", "P005"],
                "policy_serial": ["123", "45", "6789", None, "1"],
            }
            af = ActuarialFrame(data)

            af.zfilled_serial = af.policy_serial.polars_native().str.zfill(5)

            print(af.collect())
            ```

            ```text
            shape: (5, 3)
            ┌───────────┬───────────────┬────────────────┐
            │ policy_id ┆ policy_serial ┆ zfilled_serial │
            │ ---       ┆ ---           ┆ ---            │
            │ str       ┆ str           ┆ str            │
            ╞═══════════╪═══════════════╪════════════════╡
            │ P001      ┆ 123           ┆ 00123          │
            │ P002      ┆ 45            ┆ 00045          │
            │ P003      ┆ 6789          ┆ 06789          │
            │ P004      ┆ null          ┆ null           │
            │ P005      ┆ 1             ┆ 00001          │
            └───────────┴───────────────┴────────────────┘
            ```

            **Vector Example: Claim Item Codes**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002"],
                "item_codes": [
                    ["A1", "B123", "C04"],
                    ["D56"],
                ],
            }
            af = ActuarialFrame(data)

            af.zfilled_codes = af.item_codes.polars_native().list.eval(
                pl.element().str.zfill(4)
            )

            print(af.collect())
            ```

            ```text
            shape: (2, 3)
            ┌───────────┬───────────────────────┬──────────────────────────┐
            │ policy_id ┆ item_codes            ┆ zfilled_codes            │
            │ ---       ┆ ---                   ┆ ---                      │
            │ str       ┆ list[str]             ┆ list[str]                │
            ╞═══════════╪═══════════════════════╪══════════════════════════╡
            │ P001      ┆ ["A1", "B123", "C04"] ┆ ["00A1", "B123", "0C04"] │
            │ P002      ┆ ["D56"]               ┆ ["0D56"]                 │
            └───────────┴───────────────────────┴──────────────────────────┘
            ```
        """
        return _mint(self, "zfill", (length,), {}, namespace="str")

    def pad_start(self, length: object, fill_char: str = " ") -> ExpressionProxy:
        r"""Alias for `rjust`. Pads the start of strings (right-aligns content).

        Adds characters to the beginning of each string until it reaches the
        given width. This is handy when preparing fixed-width extracts or
        aligning numeric text fields in actuarial reports.

        !!! note "When to use"
            *   Preparing policy identifiers for legacy mainframe interfaces
                that expect fixed-width fields.
            *   Aligning premium or reserve amounts in textual summaries
                generated for regulators or management.
            *   Standardizing rider codes stored in lists so that they can be
                compared consistently across policies.

        Args:
            length: The desired minimum length of the string.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An `ExpressionProxy` with strings padded at the
            start.

        Examples:
            **Scalar Example: Premium Amounts**

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003"],
                "premium_str": ["1200.5", "85.75", None],
            }
            af = ActuarialFrame(data)

            af.padded_premium = af.premium_str.polars_native().str.pad_start(8, " ")

            print(af.collect())
            ```

            ```text
            shape: (3, 3)
            ┌───────────┬─────────────┬────────────────┐
            │ policy_id ┆ premium_str ┆ padded_premium │
            │ ---       ┆ ---         ┆ ---            │
            │ str       ┆ str         ┆ str            │
            ╞═══════════╪═════════════╪════════════════╡
            │ P001      ┆ 1200.5      ┆   1200.5       │
            │ P002      ┆ 85.75       ┆    85.75       │
            │ P003      ┆ null        ┆ null           │
            └───────────┴─────────────┴────────────────┘
            ```

            **Vector Example: Rider Codes**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001"],
                "rider_codes": [["RID1", "LONGRID", "RD2"]],
            }
            af = ActuarialFrame(data)

            af.padded_codes = af.rider_codes.polars_native().list.eval(
                pl.element().str.pad_start(8, "0")
            )

            print(af.select("padded_codes").collect())
            ```

            ```text
            shape: (1, 1)
            ┌──────────────────────────────────────┐
            │ padded_codes                         │
            │ ---                                  │
            │ list[str]                            │
            ╞══════════════════════════════════════╡
            │ ["0000RID1", "0LONGRID", "00000RD2"] │
            └──────────────────────────────────────┘
            ```
        """
        return _mint(self, "pad_start", (length, fill_char), {}, namespace="str")

    def pad_end(self, length: object, fill_char: str = " ") -> ExpressionProxy:
        r"""Left-align strings by padding on the right.

        Strings shorter than ``length`` are padded on the right with ``fill_char``.
        If the column is ``List[String]`` the padding is applied to each element
        of the list.

        !!! note "When to use"
            *   Format policy numbers or claim identifiers for extracts that
                require fixed-width fields.
            *   Pad abbreviations in list columns (such as rider codes) so that
                they line up cleanly in cross-system feeds.

        Args:
            length: The desired total length of the string after padding.
            fill_char: The character to pad with. Defaults to a space.

        Returns:
            ExpressionProxy: An ``ExpressionProxy`` with strings padded at the
                end.

        Examples:
            **Scalar Example: Policy Codes**

            ```python
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003"],
                "policy_code": ["L101", "L20", None],
            }
            af = ActuarialFrame(data)

            af.fixed_length_code = af.policy_code.polars_native().str.pad_end(6, "0")

            print(af.collect())
            ```

            ```text
            shape: (3, 3)
            ┌───────────┬─────────────┬───────────────────┐
            │ policy_id ┆ policy_code ┆ fixed_length_code │
            │ ---       ┆ ---         ┆ ---               │
            │ str       ┆ str         ┆ str               │
            ╞═══════════╪═════════════╪═══════════════════╡
            │ P001      ┆ L101        ┆ L10100            │
            │ P002      ┆ L20         ┆ L20000            │
            │ P003      ┆ null        ┆ null              │
            └───────────┴─────────────┴───────────────────┘
            ```

            **Vector Example: Claim Codes**

            ```python
            import polars as pl
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": ["P001"],
                "claim_codes": [["A1", "XYZ", "C1234"]],
            }
            af = ActuarialFrame(data)

            af.aligned_codes = af.claim_codes.polars_native().list.eval(
                pl.element().str.pad_end(6, "_")
            )

            print(af.collect())
            ```

            ```text
            shape: (1, 3)
            ┌───────────┬────────────────────────┬────────────────────────────────┐
            │ policy_id ┆ claim_codes            ┆ aligned_codes                  │
            │ ---       ┆ ---                    ┆ ---                            │
            │ str       ┆ list[str]              ┆ list[str]                      │
            ╞═══════════╪════════════════════════╪════════════════════════════════╡
            │ P001      ┆ ["A1", "XYZ", "C1234"] ┆ ["A1____", "XYZ___", "C1234_"] │
            └───────────┴────────────────────────┴────────────────────────────────┘
            ```
        """
        return _mint(self, "pad_end", (length, fill_char), {}, namespace="str")

    def starts_with(self, prefix: object) -> ExpressionProxy:
        r"""Check if strings in a column start with a given substring.

        This is useful for categorizing or flagging records based on prefixes in
        textual data. For example, identifying policies based on product code prefixes
        (e.g., "TERM-" for term life, "WL-" for whole life) or segmenting claims
        by a prefix in their claim ID (e.g., "AUTO-" for auto claims).

        When applied to a column of `List[String]`, such as a list of associated
        product features for a policy, the operation is performed element-wise on
        each string within each list, returning a list of booleans.

        !!! note "When to use"
            * Classify policies by prefix to drive product-specific assumptions.
            * Identify riders with a particular prefix when they are stored in
              a list column.
            * Validate codes against expected prefixes coming from another column.

        Args:
            prefix: The substring to check for at the beginning of each string.
                Can be a literal string (e.g., "TERM-") or a Polars expression
                (e.g., `pl.col("another_column_with_prefixes")`).

        Returns:
            ExpressionProxy: A new `ExpressionProxy` containing a boolean Series
                indicating for each input string whether it starts with the prefix.
                If the input was `List[String]`, the output will be `List[bool]`.

        Examples:
            **Scalar example - policy prefixes**

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            data_policies = {
                "policy_no": [
                    "TERM-1001",
                    "WL-2002",
                    "TERM-1003",
                    None,
                    "UL-3004",
                    "TERM-1004",
                ],
                "issue_age": [25, 30, 28, 45, 35, 40],
            }
            af = ActuarialFrame(data_policies)

            # Check if policy_no starts with "TERM-"
            af_term_policies = af.select(
                af["policy_no"]
                .polars_native()
                .str.starts_with("TERM-")
                .polars_native()
                .alias("is_term_policy")
            )
            print(af_term_policies.collect())
            ```

            ```text
            shape: (6, 1)
            ┌────────────────┐
            │ is_term_policy │
            │ ---            │
            │ bool           │
            ╞════════════════╡
            │ true           │
            │ false          │
            │ true           │
            │ null           │
            │ false          │
            │ true           │
            └────────────────┘
            ```

            **Vector (list) example - rider prefixes**

            ```python
            from gaspatchio.frame.base import ActuarialFrame
            import polars as pl

            data_policy_riders = {
                "policy_id": ["P201", "P202", "P203"],
                "rider_codes_list": [
                    [
                        "B-ADB",
                        "S-WP",
                        "S-CI",
                    ],  # B-AccidentalDeathBenefit, S-WaiverOfPremium, S-CriticalIllness
                    ["S-LTC", None, "B-GIO"],
                    ["S-WPR", "S-CIR"],
                ],
            }
            af_riders = ActuarialFrame(data_policy_riders).with_columns(
                pl.col("rider_codes_list").cast(pl.List(pl.String))
            )

            af_primary_benefit_check = af_riders.select(
                af_riders["rider_codes_list"]
                .polars_native()
                .list.eval(pl.element().str.starts_with("B-"))
                .polars_native()
                .alias("has_primary_benefit_rider")
            )
            print(af_primary_benefit_check.collect())
            ```

            ```text
            shape: (3, 1)
            ┌───────────────────────────┐
            │ has_primary_benefit_rider │
            │ ---                       │
            │ list[bool]                │
            ╞═══════════════════════════╡
            │ [true, false, false]      │
            │ [false, null, true]       │
            │ [false, false]            │
            └───────────────────────────┘
            ```
        """
        return _mint(self, "starts_with", (prefix,), {}, namespace="str")

    def ends_with(self, suffix: object) -> ExpressionProxy:
        r"""Check if strings end with a specific substring.

        This method returns a boolean expression showing whether each string
        value ends with the provided suffix. For columns containing
        `List[String]`, the check is applied to every element within each list.

        !!! note "When to use"
            * Verify that policy identifiers end with region or product codes.
            * Flag claim or log entries that end with status markers like "OK"
              or "PENDING".
            * Validate strings against suffixes supplied in another column, such
              as checking payout account numbers.

        Args:
            suffix: The substring to test for at the end of each string. It can
                be a literal value or a Polars expression.

        Returns:
            ExpressionProxy: A boolean result indicating whether each string
            ends with ``suffix``. For list columns, the result is a list of
            booleans.

        Examples:
            **Scalar example - region codes**

            ```python
            from gaspatchio.frame.base import ActuarialFrame

            af = ActuarialFrame(
                {"policy_id": ["P100-US", "P101-CA", "P102-US", None, "P103-EU"]}
            )
            result = af.select(
                af["policy_id"]
                .polars_native()
                .str.ends_with("-US")
                .polars_native()
                .alias("is_us_policy")
            )
            print(result.collect())
            ```

            ```text
            shape: (5, 1)
            ┌──────────────┐
            │ is_us_policy │
            │ ---          │
            │ bool         │
            ╞══════════════╡
            │ true         │
            │ false        │
            │ true         │
            │ null         │
            │ false        │
            └──────────────┘
            ```

            **Vector (list) example - status flags**

            ```python
            from gaspatchio.frame.base import ActuarialFrame
            import polars as pl

            logs = {
                "policy_id": ["A100", "A101"],
                "update_notes_str": [
                    "Issued OK,Review PENDING",
                    "None,Paid OK",
                ],
            }
            af_logs = ActuarialFrame(logs)
            af_logs = af_logs.with_columns(
                af_logs["update_notes_str"]
                .polars_native()
                .str.split(",")
                .polars_native()
                .alias("update_notes")
                .polars_native()
                .list.eval(
                    pl.when(pl.element() == "None")
                    .then(None)
                    .otherwise(pl.element())
                )
            )
            status_ok = af_logs.select(
                af_logs["update_notes"]
                .polars_native()
                .list.eval(pl.element().str.ends_with("OK"))
                .polars_native()
                .alias("ends_with_ok")
            )
            print(status_ok.collect())
            ```

            ```text
            shape: (2, 1)
            ┌───────────────┐
            │ ends_with_ok  │
            │ ---           │
            │ list[bool]    │
            ╞═══════════════╡
            │ [true, false] │
            │ [null, true]  │
            └───────────────┘
            ```
        """
        return _mint(self, "ends_with", (suffix,), {}, namespace="str")

    def strptime(  # noqa: PLR0913 - mirrors the Polars signature
        self,
        dtype: object,
        format: str | None = None,  # noqa: A002 - mirrors the Polars signature
        *,
        strict: bool = True,
        exact: bool = True,
        cache: bool = True,
        ambiguous: object = "raise",
    ) -> ExpressionProxy:
        r"""Convert string values to Date, Datetime, or Time.

        This method parses textual date or time information into Polars temporal
        types. For `List[String]` columns, each element is parsed individually.

        !!! note "When to use"
            *   Convert policy issue or claim reporting dates that are stored as
                strings in raw data extracts.
            *   Parse lists of event timestamps—such as claim status updates—when
                building experience studies or exposure models.
            *   Ingest external datasets from underwriting or administration
                systems where date fields come in a variety of text formats.

        Args:
            dtype: The Polars temporal type to convert to (``pl.Date``, ``pl.Datetime``,
                or ``pl.Time``).
            format: The strf/strptime format string. If ``None``, the format is
                inferred where possible.
            strict: If ``True`` (default), raise an error on parsing failure.
            exact: If ``True`` (default), require an exact format match.
            cache: If ``True`` (default), cache parsing results for performance.
            ambiguous: How to handle ambiguous datetimes, such as daylight-saving
                transitions. Options are ``"raise"`` (default), ``"earliest"``,
                ``"latest"``, or ``"null"``. Can also be a Polars expression.

        Returns:
            ExpressionProxy: Strings converted to the specified temporal type.

        Examples:
            **Scalar Example: Parsing policy issue dates**

            ```python
            from gaspatchio.frame.base import ActuarialFrame
            import polars as pl

            data = {
                "policy_id": ["A100", "B200", "C300"],
                "issue_date_str": ["2021-01-15", "20/02/2022", "2023-03-10 14:30:00"],
            }
            af = ActuarialFrame(data)
            af_parsed_dates = af.select(
                af["issue_date_str"]
                .polars_native()
                .str.strptime(pl.Date, "%Y-%m-%d", strict=False)
                .polars_native()
                .alias("issue_date_strict_fmt"),
                af["issue_date_str"]
                .polars_native()
                .str.strptime(pl.Date, "%d/%m/%Y", strict=False)
                .polars_native()
                .alias("issue_date_dmy_fmt"),
                af["issue_date_str"]
                .polars_native()
                .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False)
                .polars_native()
                .alias("issue_datetime"),
            )
            result = af_parsed_dates.collect()
            print(result)
            ```

            ```text
            shape: (3, 3)
            ┌───────────────────────┬────────────────────┬─────────────────────┐
            │ issue_date_strict_fmt ┆ issue_date_dmy_fmt ┆ issue_datetime      │
            │ ---                   ┆ ---                ┆ ---                 │
            │ date                  ┆ date               ┆ datetime[μs]        │
            ╞═══════════════════════╪════════════════════╪═════════════════════╡
            │ 2021-01-15            ┆ null               ┆ null                │
            │ null                  ┆ 2022-02-20         ┆ null                │
            │ null                  ┆ null               ┆ 2023-03-10 14:30:00 │
            └───────────────────────┴────────────────────┴─────────────────────┘
            ```

            **Vector Example: Parsing lists of event timestamps**

            ```python
            from gaspatchio.frame.base import ActuarialFrame
            import polars as pl

            data_list = {
                "claim_id": ["CL001"],
                "event_timestamps_str": [
                    ["2023-04-01T10:00:00", "2023-04-01T10:05:00", "Invalid"]
                ],
            }
            af_list = ActuarialFrame(data_list).with_columns(
                pl.col("event_timestamps_str").cast(pl.List(pl.String))
            )
            af_parsed_list = af_list.select(
                af_list["event_timestamps_str"]
                .polars_native()
                .list.eval(
                    pl.element().str.strptime(
                        pl.Datetime, "%Y-%m-%dT%H:%M:%S", strict=False
                    )
                )
                .polars_native()
                .alias("event_datetimes_μs")
            )
            result = af_parsed_list.collect()
            print(result)
            ```

            ```text
            shape: (1, 1)
            ┌──────────────────────────────────────────────────┐
            │ event_datetimes_μs                               │
            │ ---                                              │
            │ list[datetime[μs]]                               │
            ╞══════════════════════════════════════════════════╡
            │ [2023-04-01 10:00:00, 2023-04-01 10:05:00, null] │
            └──────────────────────────────────────────────────┘
            ```
        """
        return _mint(
            self,
            "strptime",
            (dtype, format),
            {"strict": strict, "exact": exact, "cache": cache, "ambiguous": ambiguous},
            namespace="str",
        )

    def extract(self, pattern: object, group_index: int = 1) -> ExpressionProxy:
        r"""Extract a capturing group from a regex pattern.

        Return group ``group_index`` from each string that matches ``pattern``.
        Works element-wise on ``List[String]`` columns.

        !!! note "When to use"
            * **Identifiers**: Pull policy/claim numbers from mixed strings.
            * **Amounts**: Capture monetary values from notes for validation.

        Args:
            pattern: Regex with the desired capturing group.
            group_index: 1-based index of the group to extract.

        Returns:
            ExpressionProxy

        Examples:
        **Scalar example: extract policy number**

        ```python
        from gaspatchio import ActuarialFrame

        data = {"policy_id": ["P1", "P2"], "raw": ["POL-12345-AB", "CLAIM-678-X"]}
        af = ActuarialFrame(data)

        af.policy_num = af.raw.polars_native().str.extract(
            r"POL-([A-Z0-9]+)-", group_index=1
        )

        print(af.select(af.policy_num).collect())
        ```

        ```text
        shape: (2, 1)
        ┌────────────┐
        │ policy_num │
        │ ---        │
        │ str        │
        ╞════════════╡
        │ 12345      │
        │ null       │
        └────────────┘
        ```

        **Vector example: extract amounts from list of notes**

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P1"],
            "txn": [["Premium $100.50", "Fee $10.00", "Adj $-5.25"]],
        }
        af = ActuarialFrame(data)

        af.amounts = af.txn.polars_native().list.eval(
            pl.element().str.extract(r"\$?([-+]?[0-9]+\.[0-9]{2})", group_index=1)
        )

        print(af.select(af.amounts).collect())
        ```

        ```text
        shape: (1, 1)
        ┌──────────────────────────────┐
        │ amounts                      │
        │ ---                          │
        │ list[str]                    │
        ╞══════════════════════════════╡
        │ ["100.50", "10.00", "-5.25"] │
        └──────────────────────────────┘
        ```
        """
        return _mint(self, "extract", (pattern, group_index), {}, namespace="str")

    def extract_all(self, pattern: object) -> ExpressionProxy:
        r"""Extract all non-overlapping regex matches as a list.

        Works element-wise on ``List[String]`` columns.

        Args:
            pattern: Regex pattern to search for.

        Returns:
            ExpressionProxy

        !!! note "When to use"
            * **Amounts**: Collect every currency amount from notes.
            * **IDs**: Gather all reference numbers embedded in text.

        Examples:
        **Scalar example: amounts in claim descriptions**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "claim_id": ["C1", "C2"],
            "details": ["Paid $150.00 and $25.50 fee", "Refunded $10.00"],
        }
        af = ActuarialFrame(data)

        af.amounts = af.details.polars_native().str.extract_all(r"\$[0-9]+\.[0-9]{2}")

        print(af.select(af.amounts).collect())
        ```

        ```text
        shape: (2, 1)
        ┌───────────────────────┐
        │ amounts               │
        │ ---                   │
        │ list[str]             │
        ╞═══════════════════════╡
        │ ["$150.00", "$25.50"] │
        │ ["$10.00"]            │
        └───────────────────────┘
        ```

        **Vector example: policy numbers from list of notes**

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P1"],
            "notes": [["Policy 12345 reported", "Adjustment for policy 98765"]],
        }
        af = ActuarialFrame(data)

        af.policy_numbers = af.notes.polars_native().list.eval(
            pl.element().str.extract_all(r"[0-9]+")
        )

        print(af.select(af.policy_numbers).collect())
        ```

        ```text
        shape: (1, 1)
        ┌────────────────────────┐
        │ policy_numbers         │
        │ ---                    │
        │ list[list[str]]        │
        ╞════════════════════════╡
        │ [["12345"], ["98765"]] │
        └────────────────────────┘
        ```
        """
        return _mint(self, "extract_all", (pattern,), {}, namespace="str")

    def replace(
        self, pattern: object, value: object, *, literal: bool = False, n: int = 1
    ) -> ExpressionProxy:
        r"""Replace occurrences of a pattern in each string.

        Search each string for a substring or regex and replace up to ``n``
        matches with ``value``. If ``literal`` is ``True`` the ``pattern`` is
        treated as plain text; otherwise it is interpreted as a regex.

        !!! note "When to use"
            * **Normalize legacy codes**: Map outdated product/policy codes to
              your current standard before joining to assumptions.
            * **Clean underwriting/claim notes**: Remove boilerplate prefixes
              or redact sensitive fragments prior to text analysis.
            * **Harmonize reference data**: Align naming conventions across
              multiple admin systems before aggregation.

        Args:
            pattern: Substring or regex pattern to search for. May also be a
                Polars expression yielding the pattern.
            value: Replacement text. Can be a string or a Polars expression.
            literal: If ``True``, treat ``pattern`` as a literal string.
            n: Maximum number of replacements per string (default ``1``).

        Returns:
            ExpressionProxy
                Expression with the specified replacements applied.

        Examples:
        --------
        **Scalar example: normalize policy status**

        ```python
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["P1", "P2", "P3"],
            "status_raw": ["IN FORCE", "LAPSED", "IN FORCE"],
        }
        af = ActuarialFrame(data)

        af.status = af.status_raw.polars_native().str.replace(
            "IN FORCE", "INFORCE", literal=True
        )

        print(af.collect())
        ```

        ```text
        shape: (3, 3)
        ┌───────────┬────────────┬─────────┐
        │ policy_id ┆ status_raw ┆ status  │
        │ ---       ┆ ---        ┆ ---     │
        │ str       ┆ str        ┆ str     │
        ╞═══════════╪════════════╪═════════╡
        │ P1        ┆ IN FORCE   ┆ INFORCE │
        │ P2        ┆ LAPSED     ┆ LAPSED  │
        │ P3        ┆ IN FORCE   ┆ INFORCE │
        └───────────┴────────────┴─────────┘
        ```

        **Vector example: remove "NOTE: " from claim notes**

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["A1", "A2"],
            "claim_notes": [
                ["NOTE: Initial review", "Payment authorised"],
                [None, "NOTE: Follow up required"],
            ],
        }
        af = ActuarialFrame(data)

        af.clean_notes = af.claim_notes.polars_native().list.eval(
            pl.element().str.replace("NOTE: ", "", literal=True, n=1)
        )

        print(af.select("clean_notes").collect())
        ```

        ```text
        shape: (2, 1)
        ┌──────────────────────────────────────────┐
        │ clean_notes                              │
        │ ---                                      │
        │ list[str]                                │
        ╞══════════════════════════════════════════╡
        │ ["Initial review", "Payment authorised"] │
        │ [null, "Follow up required"]             │
        └──────────────────────────────────────────┘
        ```
        """
        return _mint(
            self,
            "replace",
            (pattern, value),
            {"literal": literal, "n": n},
            namespace="str",
        )


class _DocumentedPolarsDateTimeMethods:
    """Previously documented real methods of Polars' datetime namespace.

    Scalar examples call ``dt`` directly; list examples spell Polars'
    ``list.eval(pl.element().dt...)`` semantics explicitly.
    """

    __slots__ = ()

    def year(self) -> ExpressionProxy:
        r"""Extract the year from the underlying datetime expression.

        This function isolates the year component from a date or datetime,
        returning it as an integer (e.g., 2023). It is applicable to both
        single date values and lists of dates within your `ActuarialFrame`.

        !!! note "When to use"
            Extracting the year is fundamental in actuarial analysis for:

            *   **Valuation and Reporting:** Determining the calendar year
                for financial reporting or regulatory submissions.
            *   **Experience Studies:** Grouping data by calendar year of
                event (e.g., year of claim, year of lapse) to analyze trends.
            *   **Cohort Analysis:** Defining cohorts based on the year of
                policy issue or birth year.
            *   **Projection Models:** Calculating durations or projecting
                cash flows based on calendar years.

        Examples
        --------
        Scalar example (single-date column)::

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "dates": pl.Series(["2020-01-15", "2021-07-20"]).str.to_date(
                format="%Y-%m-%d"
            )
        }
        af = ActuarialFrame(data)
        year_expr = af.dates.polars_native().dt.year()
        print(af.select(year_expr.polars_native().alias("year")).collect())
        ```
        ```text
        shape: (2, 1)
        ┌──────┐
        │ year │
        │ ---  │
        │ i32  │
        ╞══════╡
        │ 2020 │
        │ 2021 │
        └──────┘
        ```

        Vector example (list-of-dates per policy)::

        ```python
        import datetime
        import polars as pl
        from gaspatchio import ActuarialFrame

        data_vec = {
            "policy_id": ["A001", "B002"],
            "policy_event_dates": [
                [datetime.date(2019, 12, 1), datetime.date(2020, 1, 20)],
                [
                    datetime.date(2021, 5, 10),
                    datetime.date(2021, 8, 15),
                    datetime.date(2022, 2, 25),
                ],
            ],
        }
        af_vec = ActuarialFrame(data_vec)
        af_vec = af_vec.with_columns(
            pl.col("policy_event_dates").cast(pl.List(pl.Date))
        )
        years_expr = af_vec.policy_event_dates.polars_native().list.eval(
            pl.element().dt.year()
        )
        result = af_vec.select(
            pl.col("policy_id"), years_expr.polars_native().alias("event_years")
        )
        print(result.collect())
        ```
        ```text
        shape: (2, 2)
        ┌───────────┬────────────────────┐
        │ policy_id ┆ event_years        │
        │ ---       ┆ ---                │
        │ str       ┆ list[i32]          │
        ╞═══════════╪════════════════════╡
        │ A001      ┆ [2019, 2020]       │
        │ B002      ┆ [2021, 2021, 2022] │
        └───────────┴────────────────────┘
        ```
        """
        return _mint(self, "year", (), {}, namespace="dt")

    def month(self) -> ExpressionProxy:
        r"""Extract the month number (1-12) from a date or datetime expression.

        This function allows you to isolate the month component from a series of
        dates or datetimes. The result is an integer representing the month,
        where January is 1 and December is 12.

        !!! note "When to use"
            In actuarial modeling, extracting the month from dates is
            crucial for various analyses. For instance, you might use this to:

            *   Analyze seasonality in claims (e.g., identifying if certain
                types of claims are more frequent in specific months).
            *   Group policies by their issue month for cohort analysis or
                to study underwriting patterns.
            *   Determine premium due dates or benefit payment schedules
                that occur on a monthly basis.
            *   Calculate fractional year components for financial
                calculations.

        Examples
        --------
        Scalar example::

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {
                "d": pl.Series(["2022-01-01", "2022-02-01", "2022-03-01"]).str.to_date(
                    "%Y-%m-%d"
                )
            }
        )
        result = af.select(
            af.d.polars_native().dt.month().polars_native().alias("m")
        ).collect()
        print(result)
        ```
        ```text
        shape: (3, 1)
        ┌─────┐
        │ m   │
        │ --- │
        │ i8  │
        ╞═════╡
        │ 1   │
        │ 2   │
        │ 3   │
        └─────┘
        ```

        Vector (list) example - claim-lodgement months::

        ```python
        import datetime
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["C003", "D004"],
            "claim_lodgement_dates": [
                [datetime.date(2022, 3, 10), datetime.date(2022, 4, 5)],
                [datetime.date(2023, 1, 20), datetime.date(2023, 11, 30)],
            ],
        }
        af = ActuarialFrame(data).with_columns(
            pl.col("claim_lodgement_dates").cast(pl.List(pl.Date))
        )
        months_expr = af.claim_lodgement_dates.polars_native().list.eval(
            pl.element().dt.month()
        )
        result = af.select(
            pl.col("policy_id"), months_expr.polars_native().alias("lodgement_months")
        )
        print(result.collect())
        ```

        ```text
        shape: (2, 2)
        ┌───────────┬──────────────────┐
        │ policy_id ┆ lodgement_months │
        │ ---       ┆ ---              │
        │ str       ┆ list[i8]         │
        ╞═══════════╪══════════════════╡
        │ C003      ┆ [3, 4]           │
        │ D004      ┆ [1, 11]          │
        └───────────┴──────────────────┘
        ```
        """
        return _mint(self, "month", (), {}, namespace="dt")

    def day(self) -> ExpressionProxy:
        r"""Extract the day number of the month (1-31) from a date/datetime expression.

        This function isolates the day component from a date or datetime,
        returning it as an integer (e.g., 15 for the 15th of the month).
        It works for both individual dates and lists of dates.

        !!! note "When to use"
            Extracting the day of the month can be useful in actuarial
            contexts for:

            *   **Specific Date Checks:** Identifying events occurring on
                particular days (e.g., end-of-month processing).
            *   **Intra-month Analysis:** Analyzing patterns within a month,
                though less common than month or year analysis.
            *   **Data Validation:** Ensuring dates fall within expected day
                ranges for specific calculations.

        Examples
        --------
        Scalar example::

        ```python
        import polars as pl
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame(
            {"d": pl.Series(["2023-06-05", "2023-06-15"]).str.to_date()}
        )
        result = af.select(
            af.d.polars_native().dt.day().polars_native().alias("day")
        ).collect()
        print(result)
        ```
        ```text
        shape: (2, 1)
        ┌─────┐
        │ day │
        │ --- │
        │ i8  │
        ╞═════╡
        │ 5   │
        │ 15  │
        └─────┘
        ```

        Vector (list) example - loss-event days::

        ```python
        import datetime
        import polars as pl
        from gaspatchio import ActuarialFrame

        data = {
            "policy_id": ["E005", "F006"],
            "loss_event_dates": [
                [datetime.date(2023, 6, 5), datetime.date(2023, 6, 15)],
                [datetime.date(2024, 2, 1), datetime.date(2024, 2, 29)],
            ],
        }
        af = ActuarialFrame(data).with_columns(
            pl.col("loss_event_dates").cast(pl.List(pl.Date))
        )
        days_expr = af.loss_event_dates.polars_native().list.eval(pl.element().dt.day())
        result = af.select("policy_id", days_expr.polars_native().alias("event_days"))
        print(result.collect())
        ```
        ```text
        shape: (2, 2)
        ┌───────────┬────────────┐
        │ policy_id ┆ event_days │
        │ ---       ┆ ---        │
        │ str       ┆ list[i8]   │
        ╞═══════════╪════════════╡
        │ E005      ┆ [5, 15]    │
        │ F006      ┆ [1, 29]    │
        └───────────┴────────────┘
        ```
        """
        return _mint(self, "day", (), {}, namespace="dt")
