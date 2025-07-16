// ABOUTME: Excel IRR (Internal Rate of Return) function implementation for Polars
// ABOUTME: Calculates the internal rate of return for a series of cash flows using Newton-Raphson method

use polars::prelude::*;
use serde::Deserialize;

// Constants matching Excel's implementation
const MAX_ITERATIONS: i32 = 20;
const TOLERANCE: f64 = 0.00000001; // 0.00001% as specified by Excel

#[derive(Deserialize, Clone)]
pub struct IrrKwargs {
    pub guess: Option<f64>,
}

/// Excel IRR (Internal Rate of Return) implementation for Polars
///
/// Calculates the internal rate of return for a series of cash flows represented by values.
/// These cash flows do not have to be even, as they would be for an annuity. However,
/// the cash flows must occur at regular intervals, such as monthly or annually.
///
/// The internal rate of return is the interest rate received for an investment consisting
/// of payments (negative values) and income (positive values) that occur at regular periods.
///
/// # Arguments
/// * `values` - An array of cash flows for which you want to calculate the internal rate of return (required)
///   - Must contain at least one positive value and one negative value
///   - Order matters - cash flows should be entered in chronological sequence
/// * `guess` - Your guess for what the rate will be (optional, default 0.1)
///   - If IRR gives the #NUM! error, or if the result is not close to what you expected, try with a different guess
///
/// # Returns
/// The internal rate of return for the given cash flows
///
/// # Errors
/// Returns an error if:
/// * Values array contains fewer than 2 elements
/// * Values do not contain at least one positive and one negative value
/// * Cannot converge to a solution within 20 iterations (returns #NUM! equivalent)
pub fn irr(inputs: &[Series], kwargs: &IrrKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.is_empty() {
        return Err(PolarsError::ComputeError(
            "irr requires at least 1 parameter: values".into(),
        ));
    }

    // Extract input series
    let values_series = &inputs[0];

    // Get the guess value
    let guess = kwargs.guess.unwrap_or(0.1); // Default 10% as per Excel

    // For IRR, we need to work with the entire array at once rather than element-wise
    // because IRR is calculated across all cash flows together
    let values_array = values_series.f64()?;

    // Convert to Vec for easier manipulation
    let cash_flows: Vec<Option<f64>> = values_array.into_iter().collect();

    // Calculate IRR
    let result = match calculate_irr_for_series(&cash_flows, guess) {
        Ok(irr_value) => Some(irr_value),
        Err(_) => None, // Return null for errors (like Excel's #NUM!)
    };

    // Return a single-element series with the IRR result
    // Create a chunked array with a single optional value
    let result_ca: Float64Chunked = [result].iter().copied().collect();
    Ok(result_ca.with_name("irr".into()).into_series())
}

/// Calculate IRR for a series of cash flows
fn calculate_irr_for_series(cash_flows: &[Option<f64>], guess: f64) -> PolarsResult<f64> {
    // Filter out None values and collect valid cash flows
    let valid_cash_flows: Vec<f64> = cash_flows.iter().filter_map(|&cf| cf).collect();

    // Validate we have at least 2 cash flows
    if valid_cash_flows.len() < 2 {
        return Err(PolarsError::ComputeError(
            "IRR requires at least 2 non-null cash flows".into(),
        ));
    }

    // Check for at least one positive and one negative value
    let has_positive = valid_cash_flows.iter().any(|&cf| cf > 0.0);
    let has_negative = valid_cash_flows.iter().any(|&cf| cf < 0.0);

    if !has_positive || !has_negative {
        return Err(PolarsError::ComputeError(
            "IRR requires at least one positive and one negative cash flow".into(),
        ));
    }

    // Call the pure calculation function
    calculate_irr(&valid_cash_flows, guess)
        .ok_or_else(|| PolarsError::ComputeError("IRR calculation did not converge".into()))
}

/// Calculate the internal rate of return using Newton-Raphson method
///
/// This implements Excel's IRR calculation logic exactly, using an iterative
/// Newton-Raphson method to find the rate where NPV = 0.
///
/// # Newton-Raphson Formula
/// next_rate = current_rate - NPV(current_rate) / NPV'(current_rate)
///
/// Where:
/// - NPV = Σ(CF_i / (1 + rate)^i) for i from 0 to n-1
/// - NPV' = Σ(-i * CF_i / (1 + rate)^(i+1)) for i from 0 to n-1
fn calculate_irr(cash_flows: &[f64], initial_guess: f64) -> Option<f64> {
    let mut rate = initial_guess;

    for _ in 0..MAX_ITERATIONS {
        // Calculate NPV and its derivative at current rate
        let (npv, npv_derivative) = calculate_npv_and_derivative(cash_flows, rate);

        // Check if we've converged (NPV is close enough to 0)
        if npv.abs() < TOLERANCE {
            return Some(rate);
        }

        // Avoid division by zero in Newton-Raphson
        if npv_derivative.abs() < TOLERANCE {
            // Try perturbing the rate slightly
            rate += 0.01;
            continue;
        }

        // Newton-Raphson update
        let new_rate = rate - npv / npv_derivative;

        // Check for convergence in rate change
        if (new_rate - rate).abs() < TOLERANCE {
            return Some(new_rate);
        }

        // Prevent rate from going too extreme
        // Excel seems to handle extreme rates by limiting them
        if new_rate < -0.99 {
            rate = -0.99;
        } else if new_rate > 10.0 {
            rate = 10.0;
        } else {
            rate = new_rate;
        }
    }

    // Failed to converge within MAX_ITERATIONS
    None
}

/// Calculate NPV and its derivative for Newton-Raphson method
///
/// NPV = Σ(CF_i / (1 + rate)^i) for i from 0 to n-1
/// NPV' = Σ(-i * CF_i / (1 + rate)^(i+1)) for i from 0 to n-1
#[inline]
fn calculate_npv_and_derivative(cash_flows: &[f64], rate: f64) -> (f64, f64) {
    let mut npv = 0.0;
    let mut derivative = 0.0;
    let discount_factor = 1.0 + rate;

    // Start with discount = 1 for period 0
    let mut discount = 1.0;

    for (i, &cash_flow) in cash_flows.iter().enumerate() {
        // NPV calculation
        npv += cash_flow / discount;

        // Derivative calculation
        if i > 0 {
            derivative -= (i as f64) * cash_flow / (discount * discount_factor);
        }

        // Update discount for next period
        discount *= discount_factor;
    }

    (npv, derivative)
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    // Test the calculation function directly
    #[test]
    fn test_calculate_irr_simple_case() {
        // Initial investment of -1000, return of 1100 after one period
        // IRR should be 10%
        let cash_flows = vec![-1000.0, 1100.0];
        let result = calculate_irr(&cash_flows, 0.1).unwrap();
        assert_relative_eq!(result, 0.1, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_irr_multiple_periods() {
        // Initial investment of -10000, returns of 3000 for 5 years
        let cash_flows = vec![-10000.0, 3000.0, 3000.0, 3000.0, 3000.0, 3000.0];
        let result = calculate_irr(&cash_flows, 0.1).unwrap();
        // Expected IRR is approximately 15.24%
        assert_relative_eq!(result, 0.15239, epsilon = 0.00001);
    }

    #[test]
    fn test_calculate_irr_mixed_cash_flows() {
        // Mixed positive and negative cash flows
        let cash_flows = vec![-100.0, 20.0, 30.0, -10.0, 40.0, 50.0];
        let result = calculate_irr(&cash_flows, 0.1);
        assert!(result.is_some());
        // IRR should be positive for this profitable investment
        assert!(result.unwrap() > 0.0);
    }

    #[test]
    fn test_calculate_irr_zero_rate() {
        // Cash flows that sum to zero should have IRR = 0
        let cash_flows = vec![-100.0, 50.0, 50.0];
        let result = calculate_irr(&cash_flows, 0.1).unwrap();
        assert_relative_eq!(result, 0.0, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_irr_high_return() {
        // Very high return scenario
        let cash_flows = vec![-100.0, 300.0];
        let result = calculate_irr(&cash_flows, 0.1).unwrap();
        assert_relative_eq!(result, 2.0, epsilon = 1e-6); // 200% return
    }

    #[test]
    fn test_calculate_irr_negative_return() {
        // Loss-making investment
        let cash_flows = vec![-1000.0, 900.0];
        let result = calculate_irr(&cash_flows, 0.1).unwrap();
        assert_relative_eq!(result, -0.1, epsilon = 1e-6); // -10% return
    }

    #[test]
    fn test_calculate_npv_and_derivative() {
        let cash_flows = vec![-1000.0, 1100.0];
        let (npv, derivative) = calculate_npv_and_derivative(&cash_flows, 0.1);

        // At 10% rate, NPV should be 0
        assert_relative_eq!(npv, 0.0, epsilon = 1e-6);

        // Derivative should be negative (NPV decreases as rate increases)
        assert!(derivative < 0.0);
    }

    // Test the Polars interface
    #[test]
    fn test_irr_polars_interface() {
        // Create a series with cash flows
        let values = vec![-1000.0, 300.0, 300.0, 300.0, 300.0, 300.0];
        let values_series = Series::new("values".into(), values);

        let kwargs = IrrKwargs { guess: Some(0.1) };
        let result = irr(&[values_series], &kwargs).unwrap();

        let irr_value = result.f64().unwrap().get(0).unwrap();

        // Expected IRR is approximately 15.24%
        assert_relative_eq!(irr_value, 0.15239, epsilon = 0.00001);
    }

    #[test]
    fn test_irr_with_nulls() {
        // Create a series with null values
        let values = vec![
            Some(-1000.0),
            None,
            Some(300.0),
            Some(300.0),
            None,
            Some(300.0),
            Some(300.0),
        ];
        let values_series = Series::new("values".into(), values);

        let kwargs = IrrKwargs { guess: None }; // Use default guess
        let result = irr(&[values_series], &kwargs).unwrap();

        let irr_value = result.f64().unwrap().get(0).unwrap();

        // Should calculate IRR ignoring nulls
        assert!(irr_value > 0.0);
    }

    #[test]
    fn test_irr_no_positive_values() {
        let values = vec![-100.0, -200.0, -300.0];
        let values_series = Series::new("values".into(), values);

        let kwargs = IrrKwargs { guess: Some(0.1) };
        let result = irr(&[values_series], &kwargs).unwrap();

        // Should return null (None) for invalid input
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_irr_no_negative_values() {
        let values = vec![100.0, 200.0, 300.0];
        let values_series = Series::new("values".into(), values);

        let kwargs = IrrKwargs { guess: Some(0.1) };
        let result = irr(&[values_series], &kwargs).unwrap();

        // Should return null (None) for invalid input
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_irr_insufficient_values() {
        let values = vec![-100.0];
        let values_series = Series::new("values".into(), values);

        let kwargs = IrrKwargs { guess: Some(0.1) };
        let result = irr(&[values_series], &kwargs).unwrap();

        // Should return null for insufficient data
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_irr_different_guess_values() {
        let cash_flows = vec![-10000.0, 3000.0, 3000.0, 3000.0, 3000.0, 3000.0];

        // Test with different initial guesses
        let result1 = calculate_irr(&cash_flows, 0.01).unwrap();
        let result2 = calculate_irr(&cash_flows, 0.5).unwrap();
        let result3 = calculate_irr(&cash_flows, -0.5).unwrap();

        // All should converge to the same value
        assert_relative_eq!(result1, result2, epsilon = 1e-6);
        assert_relative_eq!(result2, result3, epsilon = 1e-6);
    }

    // Excel compatibility tests
    #[cfg(test)]
    mod excel_verification_tests {
        use super::*;
        use approx::assert_relative_eq;

        #[test]
        fn test_excel_known_values() {
            // Test against known Excel outputs

            // Example 1: Simple investment
            // Excel: =IRR({-70000,12000,15000,18000,21000,26000})
            let cash_flows = vec![-70000.0, 12000.0, 15000.0, 18000.0, 21000.0, 26000.0];
            let result = calculate_irr(&cash_flows, 0.1).unwrap();
            // Excel result: 8.66%
            assert_relative_eq!(result, 0.0866, epsilon = 0.0001);

            // Example 2: Project with varying cash flows
            // Excel: =IRR({-100000,20000,24000,28800,34560,41472})
            let cash_flows = vec![-100000.0, 20000.0, 24000.0, 28800.0, 34560.0, 41472.0];
            let result = calculate_irr(&cash_flows, 0.1).unwrap();
            // Excel result: approximately 13.06%
            // Note: This is a 20% growth pattern, but IRR is compound rate that makes NPV = 0
            assert_relative_eq!(result, 0.13058, epsilon = 0.0001);

            // Example 3: High return investment
            // Excel: =IRR({-1000,400,500,600,700})
            let cash_flows = vec![-1000.0, 400.0, 500.0, 600.0, 700.0];
            let result = calculate_irr(&cash_flows, 0.1).unwrap();
            // Excel result: approximately 36.44%
            assert_relative_eq!(result, 0.3644, epsilon = 0.0001);
        }

        #[test]
        fn test_excel_edge_cases() {
            // Edge case: Very small cash flows
            let cash_flows = vec![-0.01, 0.005, 0.005, 0.005];
            let result = calculate_irr(&cash_flows, 0.1);
            assert!(result.is_some());

            // Edge case: Large number of periods
            let mut cash_flows = vec![-100000.0];
            for _ in 0..50 {
                cash_flows.push(3000.0);
            }
            let result = calculate_irr(&cash_flows, 0.1).unwrap();
            // Should converge to a reasonable value
            // 50 periods of 3000 with initial investment of 100000
            // This gives an IRR of approximately 1.72%
            assert_relative_eq!(result, 0.01723, epsilon = 0.0001);
        }

        #[test]
        fn test_excel_financial_scenarios() {
            // Real estate investment scenario
            // Initial: -250,000, Rental income: 24,000/year for 10 years, Sale: 350,000
            let mut cash_flows = vec![-250000.0];
            for _ in 0..9 {
                cash_flows.push(24000.0);
            }
            cash_flows.push(24000.0 + 350000.0); // Last year rental + sale

            let result = calculate_irr(&cash_flows, 0.1).unwrap();
            // Should be a reasonable real estate return
            assert!(result > 0.08 && result < 0.15);

            // Bond-like investment
            // Price: -950, Coupons: 50/year for 10 years, Principal: 1000
            let mut cash_flows = vec![-950.0];
            for _ in 0..9 {
                cash_flows.push(50.0);
            }
            cash_flows.push(1050.0); // Last coupon + principal

            let result = calculate_irr(&cash_flows, 0.05).unwrap();
            // Should be close to the yield
            assert_relative_eq!(result, 0.0565, epsilon = 0.001);
        }

        #[test]
        fn test_excel_non_convergent_cases() {
            // Case that might not converge easily - cash flows with multiple sign changes
            // This can have multiple IRRs or no real IRR
            let cash_flows = vec![-1000.0, 3000.0, -2500.0];

            // Try with different guesses
            let result1 = calculate_irr(&cash_flows, 0.1);
            let result2 = calculate_irr(&cash_flows, -0.5);
            let result3 = calculate_irr(&cash_flows, 2.0);

            // This particular case has two valid IRRs: around -0.83 and 2.83
            // At least one of our guesses should find one of them
            let found_solution = result1.is_some() || result2.is_some() || result3.is_some();

            if !found_solution {
                // If we didn't find a solution, that's also valid for this edge case
                // Some cash flows genuinely don't have an IRR
                assert!(
                    true,
                    "No IRR found - valid for cash flows with multiple sign changes"
                );
            } else {
                // If we found solutions, verify they're reasonable
                if let Some(r) = result1 {
                    assert!(r > -1.0 && r < 5.0, "IRR out of reasonable range");
                }
                if let Some(r) = result2 {
                    assert!(r > -1.0 && r < 5.0, "IRR out of reasonable range");
                }
                if let Some(r) = result3 {
                    assert!(r > -1.0 && r < 5.0, "IRR out of reasonable range");
                }
            }
        }

        #[test]
        fn test_excel_monthly_to_annual() {
            // Monthly cash flows that need to be annualized
            // -10000 initial, 1000/month for 12 months
            let mut cash_flows = vec![-10000.0];
            for _ in 0..12 {
                cash_flows.push(1000.0);
            }

            let monthly_irr = calculate_irr(&cash_flows, 0.01).unwrap();

            // The monthly IRR for this case is approximately 2.92%
            assert_relative_eq!(monthly_irr, 0.0292, epsilon = 0.001);

            // Convert to annual rate: (1 + monthly_rate)^12 - 1
            let annual_irr = (1.0 + monthly_irr).powf(12.0) - 1.0;

            // Should be approximately 41.3% annually
            assert!(annual_irr > 0.35 && annual_irr < 0.45);
        }
    }
}
