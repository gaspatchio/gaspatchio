from typing import Union


class PremiumCalculator:
    """
    A conceptual class for premium calculations in an actuarial context.
    """

    def __init__(self, base_rate: float):
        """
        Initializes the calculator with a base rate.

        Args:
            base_rate (float): The base premium rate.
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
        The actual calculation is illustrative.

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
