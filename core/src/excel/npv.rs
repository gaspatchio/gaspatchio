// ABOUTME: Excel NPV (Net Present Value) function implementation for Polars
// ABOUTME: Calculates the net present value of an investment using a discount rate and a series of cash flows

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct NPVKwargs {}

/// Excel NPV (Net Present Value) implementation for Polars
///
/// Calculates the net present value of an investment by using a discount rate and
/// a series of future payments (negative values) and income (positive values).
///
/// IMPORTANT: Excel's NPV function assumes that the first cash flow occurs at the end
/// of the first period (time = 1), not at time = 0. This is a common source of confusion.
/// If you have an initial investment at time 0, you should NOT include it in the values
/// array but instead subtract it from the NPV result.
///
/// # Arguments
/// * `rate` - The rate of discount over the length of one period (required)
/// * `values` - Variable number of cash flow values (at least 1 required)
///
/// # Sign Convention
/// * Negative values represent cash outflows (payments)
/// * Positive values represent cash inflows (receipts)
///
/// # Returns
/// The net present value of the cash flows
///
/// # Errors
/// Returns an error if:
/// * Fewer than 2 inputs are provided (rate + at least one value)
/// * Rate is -1 (would cause division by zero)
///
/// # Excel Compatibility Notes
/// * Excel ignores text, logical values, and empty cells in the values array
/// * Cash flows must be equally spaced in time and occur at the end of each period
/// * The order of values is significant - NPV uses the order to determine timing
pub fn npv(inputs: &[Series], _kwargs: &NPVKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "npv requires at least 2 parameters: rate and at least one cash flow value".into(),
        ));
    }

    // Extract rate series (first input)
    let rate_series = &inputs[0];
    let rate_array = rate_series.f64()?;

    // Extract all value series (remaining inputs)
    let value_series: Vec<&Series> = inputs[1..].iter().collect();

    // Convert all value series to f64 arrays
    let value_arrays: Vec<Float64Chunked> = value_series
        .iter()
        .map(|s| s.f64().map(|ca| ca.clone()))
        .collect::<Result<Vec<_>, _>>()?;

    // Determine the length of the result series
    let len = rate_array.len();

    // Process each row
    let result_ca: Float64Chunked = (0..len)
        .map(|idx| {
            // Get rate for this row
            let rate_opt = rate_array.get(idx);

            // Collect all cash flow values for this row
            let mut cash_flows = Vec::with_capacity(value_arrays.len());
            let mut has_null = false;

            for value_array in &value_arrays {
                match value_array.get(idx) {
                    Some(val) => cash_flows.push(val),
                    None => {
                        has_null = true;
                        break;
                    }
                }
            }

            // Calculate NPV if we have all required values
            match (rate_opt, has_null) {
                (Some(rate), false) => {
                    // Check for rate = -1 which would cause division by zero
                    if rate == -1.0 {
                        // Return None for invalid rate
                        None
                    } else {
                        Some(calculate_npv(rate, &cash_flows))
                    }
                }
                _ => None, // Handle null inputs
            }
        })
        .collect();

    Ok(result_ca.with_name("npv".into()).into_series())
}

/// Calculate the net present value for a single set of parameters
///
/// This implements Excel's NPV calculation logic exactly. Note that Excel's NPV
/// assumes the first cash flow occurs at time = 1, not time = 0.
///
/// # Excel Formula
/// NPV = Σ[values[i] / (1 + rate)^i] for i = 1 to n
///
/// Where i starts at 1 because the first cash flow is assumed to be at the end
/// of the first period.
///
/// # Special Cases
/// * When rate = 0: NPV is simply the sum of all cash flows
/// * When rate = -1: Would cause division by zero (handled by caller)
/// * Empty cash flows: Returns 0
#[inline]
fn calculate_npv(rate: f64, cash_flows: &[f64]) -> f64 {
    if cash_flows.is_empty() {
        return 0.0;
    }

    if rate == 0.0 {
        // Special case: when rate is 0, NPV is just the sum of cash flows
        cash_flows.iter().sum()
    } else {
        // Standard case: discount each cash flow by (1 + rate)^period
        // Note: period starts at 1 for the first cash flow (Excel convention)
        cash_flows
            .iter()
            .enumerate()
            .map(|(i, &cf)| {
                let period = (i + 1) as f64; // Period 1, 2, 3, ...
                cf / (1.0 + rate).powf(period)
            })
            .sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    // Test the calculation function directly
    #[test]
    fn test_calculate_npv_normal_case() {
        // Example: Initial investment -10000, returns 3000, 4200, 6800 at 10% discount rate
        let cash_flows = vec![-10000.0, 3000.0, 4200.0, 6800.0];
        let result = calculate_npv(0.1, &cash_flows);

        // Manual calculation:
        // -10000/(1.1)^1 + 3000/(1.1)^2 + 4200/(1.1)^3 + 6800/(1.1)^4
        // = -9090.91 + 2479.34 + 3155.25 + 4643.78
        // = 1187.46
        assert_relative_eq!(result, 1188.44, epsilon = 1.0);
    }

    #[test]
    fn test_calculate_npv_zero_rate() {
        // When rate is 0, NPV is just the sum
        let cash_flows = vec![1000.0, 2000.0, 3000.0];
        let result = calculate_npv(0.0, &cash_flows);
        assert_relative_eq!(result, 6000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_npv_negative_rate() {
        // NPV should work with negative rates (though economically unusual)
        let cash_flows = vec![1000.0, 1000.0];
        let result = calculate_npv(-0.1, &cash_flows);

        // 1000/(0.9)^1 + 1000/(0.9)^2
        // = 1111.11 + 1234.57
        // = 2345.68
        assert_relative_eq!(result, 2345.68, epsilon = 0.01);
    }

    #[test]
    fn test_calculate_npv_single_cash_flow() {
        // Single cash flow
        let cash_flows = vec![1000.0];
        let result = calculate_npv(0.1, &cash_flows);

        // 1000/(1.1)^1 = 909.09
        assert_relative_eq!(result, 909.0909, epsilon = 0.0001);
    }

    #[test]
    fn test_calculate_npv_empty_cash_flows() {
        // Empty cash flows should return 0
        let cash_flows = vec![];
        let result = calculate_npv(0.1, &cash_flows);
        assert_eq!(result, 0.0);
    }

    #[test]
    fn test_calculate_npv_all_negative_flows() {
        // All outflows (negative NPV expected)
        let cash_flows = vec![-1000.0, -2000.0, -3000.0];
        let result = calculate_npv(0.1, &cash_flows);
        assert!(result < 0.0);
        // Calculation: -1000/1.1 - 2000/1.1^2 - 3000/1.1^3
        // = -909.09 - 1652.89 - 2253.94
        // = -4815.93
        assert_relative_eq!(result, -4815.93, epsilon = 0.01);
    }

    // Test the Polars interface
    #[test]
    fn test_npv_polars_interface() {
        let rate_series = Series::new("rate".into(), vec![0.1, 0.08, 0.0]);
        let value1_series = Series::new("value1".into(), vec![-10000.0, -40000.0, 1000.0]);
        let value2_series = Series::new("value2".into(), vec![3000.0, 8000.0, 2000.0]);
        let value3_series = Series::new("value3".into(), vec![4200.0, 9200.0, 3000.0]);
        let value4_series = Series::new("value4".into(), vec![6800.0, 10100.0, 4000.0]);

        let kwargs = NPVKwargs {};
        let result = npv(
            &[
                rate_series,
                value1_series,
                value2_series,
                value3_series,
                value4_series,
            ],
            &kwargs,
        )
        .unwrap();

        let values = result.f64().unwrap();

        // First row: 10% rate with cash flows matching Excel example
        assert_relative_eq!(values.get(0).unwrap(), 1188.44, epsilon = 1.0);

        // Second row: 8% rate
        let expected_npv2 = -40000.0 / 1.08_f64.powf(1.0)
            + 8000.0 / 1.08_f64.powf(2.0)
            + 9200.0 / 1.08_f64.powf(3.0)
            + 10100.0 / 1.08_f64.powf(4.0);
        assert_relative_eq!(values.get(1).unwrap(), expected_npv2, epsilon = 0.01);

        // Third row: 0% rate (sum of cash flows)
        assert_relative_eq!(values.get(2).unwrap(), 10000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_npv_variable_number_of_values() {
        // Test with different numbers of cash flow values
        let rate_series = Series::new("rate".into(), vec![0.1, 0.1]);
        let value1_series = Series::new("value1".into(), vec![1000.0, 2000.0]);
        let value2_series = Series::new("value2".into(), vec![2000.0, 3000.0]);
        let value3_series = Series::new("value3".into(), vec![3000.0, 4000.0]);

        let kwargs = NPVKwargs {};

        // Test with 2 values
        let result = npv(
            &[
                rate_series.clone(),
                value1_series.clone(),
                value2_series.clone(),
            ],
            &kwargs,
        )
        .unwrap();
        let values = result.f64().unwrap();
        assert!(values.get(0).is_some());

        // Test with 3 values
        let result = npv(
            &[rate_series, value1_series, value2_series, value3_series],
            &kwargs,
        )
        .unwrap();
        let values = result.f64().unwrap();
        assert!(values.get(0).is_some());
    }

    #[test]
    fn test_null_handling() {
        let rate_series = Series::new("rate".into(), vec![Some(0.1), None, Some(0.1)]);
        let value1_series = Series::new("value1".into(), vec![Some(1000.0), Some(2000.0), None]);
        let value2_series = Series::new(
            "value2".into(),
            vec![Some(2000.0), Some(3000.0), Some(4000.0)],
        );

        let kwargs = NPVKwargs {};
        let result = npv(&[rate_series, value1_series, value2_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated
        assert!(values.get(0).is_some());
        // Calculation: 1000/1.1 + 2000/1.1^2 = 909.09 + 1652.89 = 2561.98
        assert_relative_eq!(values.get(0).unwrap(), 2561.98, epsilon = 0.01);

        // Second value should be null (rate is null)
        assert!(values.get(1).is_none());

        // Third value should be null (value1 is null)
        assert!(values.get(2).is_none());
    }

    #[test]
    fn test_insufficient_parameters() {
        let rate_series = Series::new("rate".into(), vec![0.1]);

        let kwargs = NPVKwargs {};
        let result = npv(&[rate_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_rate_negative_one() {
        let rate_series = Series::new("rate".into(), vec![-1.0]);
        let value_series = Series::new("value".into(), vec![1000.0]);

        let kwargs = NPVKwargs {};
        let result = npv(&[rate_series, value_series], &kwargs).unwrap();

        // Rate of -1 should return None (null) instead of error to match Excel behavior
        let values = result.f64().unwrap();
        assert!(values.get(0).is_none());
    }

    // Excel compatibility tests
    #[cfg(test)]
    mod excel_verification_tests {
        use super::*;
        use approx::assert_relative_eq;

        #[test]
        fn test_excel_known_values() {
            // Example 1 from Excel documentation
            // Investment of $10,000 with returns over 4 years
            let cash_flows = vec![-10000.0, 3000.0, 4200.0, 6800.0];
            let result = calculate_npv(0.1, &cash_flows);
            // Excel result: $1,188.44
            assert_relative_eq!(result, 1188.44, epsilon = 1.0);

            // Example 2: Complex investment scenario
            // Values: -40000, 8000, 9200, 10100, 14500 at 8% rate
            // Note: In Excel NPV, all values are discounted starting from period 1
            let cash_flows = vec![-40000.0, 8000.0, 9200.0, 10100.0, 14500.0];
            let result = calculate_npv(0.08, &cash_flows);
            // Calculation: -40000/1.08 + 8000/1.08^2 + 9200/1.08^3 + 10100/1.08^4 + 14500/1.08^5
            // = -37037.04 + 6858.71 + 7302.07 + 7423.62 + 9869.83
            // = -5582.81
            assert_relative_eq!(result, -5582.81, epsilon = 1.0);
        }

        #[test]
        fn test_excel_initial_investment_handling() {
            // IMPORTANT: Excel's NPV assumes first value is at t=1, not t=0
            // If you have initial investment at t=0, calculate separately

            // Method 1: Include all values (assumes first is at t=1)
            let all_values = vec![-10000.0, 3000.0, 4200.0, 6800.0];
            let npv_all = calculate_npv(0.1, &all_values);

            // Method 2: Exclude initial investment, add it separately
            let future_values = vec![3000.0, 4200.0, 6800.0];
            let npv_future = calculate_npv(0.1, &future_values);
            let npv_with_initial = npv_future - 10000.0;

            // These should NOT be equal due to timing difference
            assert!(npv_all != npv_with_initial);

            // The difference is due to different timing assumptions
            // npv_all treats -10000 as occurring at t=1
            // npv_with_initial treats -10000 as occurring at t=0
            let difference = npv_with_initial - npv_all;
            // The actual difference should be around 118.84
            assert_relative_eq!(difference, 118.84, epsilon = 0.01);
        }

        #[test]
        fn test_excel_financial_scenarios() {
            // Project evaluation: 5-year project with varying cash flows
            let project_flows = vec![-50000.0, 10000.0, 15000.0, 20000.0, 25000.0, 30000.0];
            let result = calculate_npv(0.12, &project_flows);
            // NPV calculation with all values discounted from period 1
            // = -50000/1.12 + 10000/1.12^2 + 15000/1.12^3 + 20000/1.12^4 + 25000/1.12^5 + 30000/1.12^6
            // = -44642.86 + 7971.94 + 10676.12 + 12712.38 + 14185.68 + 15197.49
            // = 16100.75
            assert!(result > 0.0);
            assert_relative_eq!(result, 16100.75, epsilon = 1.0);

            // Bond valuation: $1000 bond with 5% coupon for 5 years at 6% yield
            let bond_flows = vec![50.0, 50.0, 50.0, 50.0, 1050.0];
            let result = calculate_npv(0.06, &bond_flows);
            // Bond should trade at discount (NPV < 1000)
            assert!(result < 1000.0);
            assert_relative_eq!(result, 957.88, epsilon = 0.01);
        }

        #[test]
        fn test_excel_edge_cases() {
            // Very high discount rate
            let cash_flows = vec![1000.0, 1000.0, 1000.0];
            let result = calculate_npv(1.0, &cash_flows); // 100% discount rate
                                                          // Should heavily discount future cash flows
                                                          // = 1000/2 + 1000/4 + 1000/8 = 500 + 250 + 125 = 875
            assert_relative_eq!(result, 875.0, epsilon = 0.01);

            // Very small discount rate (approaching 0)
            let result1 = calculate_npv(0.0001, &cash_flows);
            let result2 = calculate_npv(0.0, &cash_flows);
            // Should be very close to undiscounted sum
            assert_relative_eq!(result1, result2, epsilon = 0.6);

            // Mixed positive and negative cash flows
            let mixed_flows = vec![-5000.0, 2000.0, -1000.0, 3000.0, 2000.0];
            let result = calculate_npv(0.05, &mixed_flows);
            // Calculation: -5000/1.05 + 2000/1.05^2 + -1000/1.05^3 + 3000/1.05^4 + 2000/1.05^5
            // = -4761.90 + 1814.06 - 863.84 + 2468.11 + 1567.05
            // = 223.48
            assert_relative_eq!(result, 223.48, epsilon = 0.01);
        }

        #[test]
        fn test_excel_order_significance() {
            // Excel NPV is sensitive to the order of cash flows
            let flows_a = vec![1000.0, 2000.0, 3000.0];
            let flows_b = vec![3000.0, 2000.0, 1000.0];

            let npv_a = calculate_npv(0.1, &flows_a);
            let npv_b = calculate_npv(0.1, &flows_b);

            // Different order should give different NPV
            assert!(npv_a != npv_b);
            // Earlier large cash flows should have higher NPV
            assert!(npv_b > npv_a);
        }

        #[test]
        fn test_excel_perpetuity_approximation() {
            // For very long series, NPV approaches perpetuity value
            let mut long_series = Vec::new();
            for _ in 0..100 {
                long_series.push(100.0);
            }

            let npv_long = calculate_npv(0.05, &long_series);

            // For a large but finite series, NPV approaches but doesn't equal perpetuity
            // The NPV of 100 payments should be close to the perpetuity value
            // Perpetuity formula for first payment at t=1: PV = CF/r * 1/(1+r) = 100/0.05 * 1/1.05
            // But with 100 periods, we're very close to this value

            // The actual NPV should be around 1984.79 for 100 periods
            assert_relative_eq!(npv_long, 1984.79, epsilon = 0.01);
        }
    }
}
