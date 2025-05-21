from typing import Union


class PremiumCalculator:
    """
    A conceptual class for premium calculations in an actuarial context.

    This class provides methods to initialize a premium calculator with a base rate
    and then calculate adjusted premiums based on various risk factors and policy details.
    It serves as a demonstration for docstring parsing, especially for multiple examples.

    !!! note "When to use"
        Use this class when you need to perform illustrative premium calculations.
        It's particularly useful for testing docstring parsing capabilities related
        to classes, methods, and multiple examples within a single docstring.

    Examples:
    ---------
    ```python
    # Define the class for the example to be self-contained
    class PremiumCalculator:
        def __init__(self, base_rate: float): self.base_rate = base_rate
        # Add a dummy method that might be called or type checked
        def calculate_adjusted_premium(self, age: int, risk_factor: float, coverage_amount: float, term_years: int = 10) -> float: return 0.0

    calc = PremiumCalculator(base_rate=100.0)
    print(type(calc))
    ```
    ```text
    <class '__main__.PremiumCalculator'>
    ```
    """

    def __init__(self, base_rate: float):
        """
        Initializes the calculator with a base rate.

        The base rate is a fundamental component for all subsequent premium calculations
        performed by instances of this class. It represents a starting point before
        adjustments for age, risk, coverage, and term are applied.

        !!! note "When to use"
            This constructor is called automatically when you create an instance
            of the `PremiumCalculator`. Provide a `base_rate` to set the foundational
            premium amount.

        Args:
            base_rate (float): The base premium rate.

        Examples:
        ---------
        ```python
        # Define the class for the example to be self-contained
        class PremiumCalculator:
            def __init__(self, base_rate: float): self.base_rate = base_rate
            # Add a dummy method that might be called or type checked
            def calculate_adjusted_premium(self, age: int, risk_factor: float, coverage_amount: float, term_years: int = 10) -> float: return 0.0

        calc_instance = PremiumCalculator(base_rate=150.0)
        print(calc_instance.base_rate)
        ```
        ```text
        150.0
        ```
        """
        self.base_rate = base_rate

    def calculate_adjusted_premium(
        self,
        age: int,
        risk_factor: float,
        coverage_amount: Union[int, float],
        term_years: int = 10,
    ) -> float:
        """
        Calculates an adjusted premium based on several factors.

        This method demonstrates parsing multiple examples from a single docstring.
        The actual calculation is illustrative and combines age, risk, coverage, and term
        to adjust the initial base rate. It shows how different profiles can lead to
        varying premium outcomes.

        !!! note "When to use"
            Use this method after initializing a `PremiumCalculator` with a `base_rate`.
            Provide the insured's age, a risk factor, the desired coverage amount, and
            the policy term to get an illustrative adjusted premium. It's good for
            demonstrating complex calculations with multiple parameters and for testing
            docstring example extraction where examples show DataFrame outputs.

        Args:
            age (int): The age of the insured individual.
            risk_factor (float): A numerical risk factor (e.g., 1.0 for standard, >1.0 for higher risk).
            coverage_amount (Union[int, float]): The amount of coverage.
            term_years (int): The term of the policy in years. Defaults to 10.

        Returns:
            float: The calculated adjusted premium.

        Examples:

            Example 1: Standard Risk Profile as DataFrame Output

            ```python
            import polars as pl
            # Define needed class for self-contained example
            class PremiumCalculator:
                def __init__(self, base_rate: float): self.base_rate = base_rate
                def calculate_adjusted_premium(self, age: int, risk_factor: float, coverage_amount: float, term_years: int = 10) -> float:
                    age_adjustment = 1 + (age / 100)
                    term_adjustment = 1 + (term_years / 50)
                    return round(self.base_rate * age_adjustment * risk_factor * (coverage_amount / 10000) * term_adjustment, 2)

            calc = PremiumCalculator(base_rate=100.0)
            premium_val = calc.calculate_adjusted_premium(age=30, risk_factor=1.0, coverage_amount=100000, term_years=20)
            df_ex1 = pl.DataFrame({"description": ["Standard Risk"], "age": [30], "risk_factor": [1.0], "coverage": [100000], "term_years": [20], "calculated_premium": [premium_val]})
            print(df_ex1)
            ```
            ```text
            shape: (1, 6)
            ┌───────────────┬─────┬─────────────┬──────────┬────────────┬────────────────────┐
            │ description   ┆ age ┆ risk_factor ┆ coverage ┆ term_years ┆ calculated_premium │
            │ ---           ┆ --- ┆ ---         ┆ ---      ┆ ---        ┆ ---                │
            │ str           ┆ i64 ┆ f64         ┆ i64      ┆ i64        ┆ f64                │
            ╞═══════════════╪═════╪═════════════╪══════════╪════════════╪════════════════════╡
            │ Standard Risk ┆ 30  ┆ 1.0         ┆ 100000   ┆ 20         ┆ 1820.0             │
            └───────────────┴─────┴─────────────┴──────────┴────────────┴────────────────────┘
            ```

            Example 2: Higher Risk Profile with Vector Coverage as DataFrame Output

            ```python
            import polars as pl
            # Define needed class for self-contained example
            class PremiumCalculator:
                def __init__(self, base_rate: float): self.base_rate = base_rate
                def calculate_adjusted_premium(self, age: int, risk_factor: float, coverage_amount: float, term_years: int = 10) -> float:
                    age_adjustment = 1 + (age / 100)
                    term_adjustment = 1 + (term_years / 50)
                    return round(self.base_rate * age_adjustment * risk_factor * (coverage_amount / 10000) * term_adjustment, 2)

            calc = PremiumCalculator(base_rate=100.0)
            coverages = [200000, 250000, 300000]
            premiums_hr_list = [
                calc.calculate_adjusted_premium(age=45, risk_factor=1.5, coverage_amount=cov, term_years=5)
                for cov in coverages
            ]
            df_ex2 = pl.DataFrame({
                "description": ["Higher Risk"],
                "age": [45],
                "risk_factor": [1.5],
                "coverages_list": [coverages],
                "term_years": [5],
                "calculated_premiums_list": [premiums_hr_list]
            })
            print(df_ex2)
            ```
            ```text
            shape: (1, 6)
            ┌─────────────┬─────┬─────────────┬──────────────────────────┬────────────┬───────────────────────────┐
            │ description ┆ age ┆ risk_factor ┆ coverages_list           ┆ term_years ┆ calculated_premiums_list  │
            │ ---         ┆ --- ┆ ---         ┆ ---                      ┆ ---        ┆ ---                       │
            │ str         ┆ i64 ┆ f64         ┆ list[i64]                ┆ i64        ┆ list[f64]                 │
            ╞═════════════╪═════╪═════════════╪══════════════════════════╪════════════╪═══════════════════════════╡
            │ Higher Risk ┆ 45  ┆ 1.5         ┆ [200000, 250000, 300000] ┆ 5          ┆ [4785.0, 5981.25, 7177.5] │
            └─────────────┴─────┴─────────────┴──────────────────────────┴────────────┴───────────────────────────┘
            ```
        """
        # Illustrative calculation
        age_adjustment = 1 + (age / 100)  # Simple age factor
        term_adjustment = 1 + (term_years / 50)  # Simple term factor
        adjusted_premium = (
            self.base_rate
            * age_adjustment
            * risk_factor
            * (coverage_amount / 10000)  # Scaled by coverage
            * term_adjustment
        )
        return round(adjusted_premium, 2)
