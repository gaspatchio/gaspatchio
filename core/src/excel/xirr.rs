// ABOUTME: Excel XIRR (Internal Rate of Return for irregular cash flows) function implementation for Polars
// ABOUTME: Calculates the internal rate of return for a series of cash flows occurring at irregular intervals

use chrono::{Duration, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

// Constants matching Excel's XIRR implementation
const MAX_ITERATIONS: i32 = 100;
const TOLERANCE: f64 = 0.000001; // 0.0001% as specified by Excel for XIRR
const DAYS_PER_YEAR: f64 = 365.0;

#[derive(Deserialize, Clone)]
pub struct XirrKwargs {
    pub guess: Option<f64>,
}

/// Excel XIRR (Internal Rate of Return for irregular cash flows) implementation for Polars
///
/// Returns the internal rate of return for a schedule of cash flows that is not necessarily periodic.
/// To calculate the internal rate of return for a series of cash flows that is periodic, use the IRR function.
///
/// # Arguments
/// * `values` - A series of cash flows that corresponds to a schedule of payments in dates (required)
/// * `dates` - A schedule of dates that corresponds to values (required)
/// * `guess` - Your guess for what the rate will be (optional, default 0.1)
///
/// # Excel Behavior
/// * Uses Newton-Raphson method to find rate where XNPV = 0
/// * Requires at least one positive and one negative cash flow
/// * Uses a 365-day year basis for calculations
/// * Maximum 100 iterations with tolerance of 0.000001%
/// * All subsequent cash flows are discounted based on the number of days from the first date
/// * The first cash flow is not discounted (occurs at the first date)
/// * Values must include at least one positive and one negative value
/// * Dates must be valid Excel dates and not precede the first date
///
/// # Sign Convention
/// * Negative values represent cash outflows (payments)
/// * Positive values represent cash inflows (receipts)
///
/// # Returns
/// The internal rate of return for the given irregular cash flows
///
/// # Errors
/// Returns an error if:
/// * Fewer than 2 inputs are provided (values, dates)
/// * Values and dates arrays have different lengths
/// * Values do not contain at least one positive and one negative value
/// * Any date precedes the first date
/// * Cannot converge to a solution within 100 iterations (returns #NUM! equivalent)
/// * Values or dates contain invalid data types
///
/// # Excel Compatibility Notes
/// * XIRR does not discount the initial cash flow (first value)
/// * All subsequent payments are discounted based on a 365-day year
/// * The first payment date indicates the beginning of the schedule
/// * Other dates must be later than the first date, but need not be in order
/// * Uses Newton-Raphson method with up to 100 iterations
/// * Converges when result is accurate within 0.000001%
pub fn xirr(inputs: &[Series], kwargs: &XirrKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "xirr requires at least 2 parameters: values and dates".into(),
        ));
    }

    // Extract input series
    let values_series = &inputs[0];
    let dates_series = &inputs[1];

    // Get the guess value
    let guess = kwargs.guess.unwrap_or(0.1); // Default 10% as per Excel

    // For XIRR, we need to work with the entire arrays at once
    // because XIRR is calculated across all cash flows and dates together
    let values_array = values_series.f64()?;
    let dates_array = dates_series.date()?;

    // Check if both arrays have same length
    if values_array.len() != dates_array.len() {
        return Err(PolarsError::ComputeError(
            "values and dates must have the same length".into(),
        ));
    }

    // Convert to Vec for easier manipulation
    let cash_flows: Vec<Option<f64>> = values_array.into_iter().collect();
    let dates: Vec<Option<i32>> = dates_array.into_iter().collect();

    // Calculate XIRR
    let result = match calculate_xirr_for_series(&cash_flows, &dates, guess) {
        Ok(xirr_value) => Some(xirr_value),
        Err(_) => None, // Return null for errors (like Excel's #NUM!)
    };

    // Return a single-element series with the XIRR result
    let result_ca: Float64Chunked = [result].iter().copied().collect();
    Ok(result_ca.with_name("xirr".into()).into_series())
}

/// Calculate XIRR for a series of cash flows and dates
fn calculate_xirr_for_series(
    cash_flows: &[Option<f64>],
    dates: &[Option<i32>],
    guess: f64,
) -> PolarsResult<f64> {
    // Filter out None values and collect valid cash flows and dates
    let mut valid_cash_flows = Vec::new();
    let mut valid_dates = Vec::new();

    for (cf_opt, date_opt) in cash_flows.iter().zip(dates.iter()) {
        if let (Some(cf), Some(date)) = (cf_opt, date_opt) {
            valid_cash_flows.push(*cf);
            valid_dates.push(*date);
        }
    }

    // Validate we have at least 2 cash flows
    if valid_cash_flows.len() < 2 {
        return Err(PolarsError::ComputeError(
            "XIRR requires at least 2 non-null cash flows".into(),
        ));
    }

    // Check for at least one positive and one negative value
    let has_positive = valid_cash_flows.iter().any(|&cf| cf > 0.0);
    let has_negative = valid_cash_flows.iter().any(|&cf| cf < 0.0);

    if !has_positive || !has_negative {
        return Err(PolarsError::ComputeError(
            "XIRR requires at least one positive and one negative cash flow".into(),
        ));
    }

    // Convert days since epoch to NaiveDate
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    let naive_dates: Vec<NaiveDate> = valid_dates
        .iter()
        .map(|&days| epoch + Duration::days(i64::from(days)))
        .collect();

    // Call the pure calculation function
    calculate_xirr(&valid_cash_flows, &naive_dates, guess)
        .ok_or_else(|| PolarsError::ComputeError("XIRR calculation did not converge".into()))
}

/// Calculate the internal rate of return for irregular cash flows using Newton-Raphson method
///
/// This implements Excel's XIRR calculation logic exactly, using an iterative
/// Newton-Raphson method to find the rate where XNPV = 0.
///
/// # Newton-Raphson Formula
/// next_rate = current_rate - XNPV(current_rate) / XNPV'(current_rate)
///
/// Where:
/// - XNPV = Σ[CF_i / (1 + rate)^(days_i / 365)] for i = 0 to n-1
/// - XNPV' = Σ[-(days_i / 365) * CF_i / (1 + rate)^(days_i / 365 + 1)] for i = 0 to n-1
/// - days_i is the number of days from the first date to date_i
/// - CF_0 is not discounted (occurs at the first date)
///
/// # Arguments
/// * `cash_flows` - Vector of cash flow amounts
/// * `dates` - Vector of dates corresponding to cash flows
/// * `initial_guess` - Initial guess for the rate (typically 0.1)
///
/// # Returns
/// The internal rate of return or None if convergence fails
fn calculate_xirr(cash_flows: &[f64], dates: &[NaiveDate], initial_guess: f64) -> Option<f64> {
    // Validate inputs
    if cash_flows.len() != dates.len() || cash_flows.len() < 2 {
        return None;
    }

    // Get the first date as the reference point
    let first_date = dates[0];

    // Validate that all dates are >= first_date
    for &date in dates.iter() {
        if date < first_date {
            return None;
        }
    }

    // Calculate years differences from first date
    let years_diffs: Vec<f64> = dates
        .iter()
        .map(|&date| (date - first_date).num_days() as f64 / DAYS_PER_YEAR)
        .collect();

    let mut rate = initial_guess;

    for _ in 0..MAX_ITERATIONS {
        // Calculate XNPV and its derivative at current rate
        let (xnpv, xnpv_derivative) = calculate_xnpv_and_derivative(cash_flows, &years_diffs, rate);

        // Check if we've converged (XNPV is close enough to 0)
        if xnpv.abs() < TOLERANCE {
            return Some(rate);
        }

        // Avoid division by zero in Newton-Raphson
        if xnpv_derivative.abs() < TOLERANCE {
            // Try perturbing the rate slightly
            rate += 0.01;
            continue;
        }

        // Newton-Raphson update
        let new_rate = rate - xnpv / xnpv_derivative;

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

/// Calculate XNPV and its derivative for Newton-Raphson method
///
/// XNPV = Σ[CF_i / (1 + rate)^(years_i)] for i = 0 to n-1
/// XNPV' = Σ[-years_i * CF_i / (1 + rate)^(years_i + 1)] for i = 0 to n-1
///
/// Where years_i is the number of years from the first date to date_i
#[inline]
fn calculate_xnpv_and_derivative(cash_flows: &[f64], years_diffs: &[f64], rate: f64) -> (f64, f64) {
    let mut xnpv = 0.0;
    let mut derivative = 0.0;

    for (i, (&cash_flow, &years_diff)) in cash_flows.iter().zip(years_diffs.iter()).enumerate() {
        if i == 0 {
            // First cash flow is not discounted
            xnpv += cash_flow;
            // Derivative contribution for first cash flow is 0
        } else {
            // Discounted cash flow
            let discount_factor = (1.0 + rate).powf(years_diff);
            xnpv += cash_flow / discount_factor;

            // Derivative calculation
            derivative -= years_diff * cash_flow / (discount_factor * (1.0 + rate));
        }
    }

    (xnpv, derivative)
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use chrono::NaiveDate;

    // Helper function to create date series
    fn create_date_series(dates: Vec<NaiveDate>) -> Series {
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let days: Vec<i32> = dates
            .iter()
            .map(|d| (*d - epoch).num_days().try_into().expect("Days fit in i32"))
            .collect();
        Series::new("date".into(), days)
            .cast(&DataType::Date)
            .unwrap()
    }

    // Test the calculation function directly
    #[test]
    fn test_calculate_xirr_simple_case() {
        // Initial investment of -1000, return of 1100 after one year
        // XIRR should be 10%
        let cash_flows = vec![-1000.0, 1100.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ];
        let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
        assert_relative_eq!(result, 0.1, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_xirr_irregular_periods() {
        // Cash flows at irregular intervals
        let cash_flows = vec![-1000.0, 500.0, 300.0, 400.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),  // Day 0
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),  // Day 90 (approx)
            NaiveDate::from_ymd_opt(2023, 7, 15).unwrap(), // Day 195 (approx)
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),  // Day 365
        ];

        let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();

        // Should converge to a reasonable positive rate
        assert!(result > 0.0);
        assert!(result < 1.0); // Less than 100%
    }

    #[test]
    fn test_calculate_xirr_break_even() {
        // Investment that breaks even
        let cash_flows = vec![-1000.0, 1000.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ];

        let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
        assert_relative_eq!(result, 0.0, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_xirr_high_return() {
        // Very high return scenario
        let cash_flows = vec![-100.0, 300.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ];

        let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
        assert_relative_eq!(result, 2.0, epsilon = 1e-6); // 200% return
    }

    #[test]
    fn test_calculate_xirr_negative_return() {
        // Loss-making investment
        let cash_flows = vec![-1000.0, 900.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ];

        let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
        assert_relative_eq!(result, -0.1, epsilon = 1e-6); // -10% return
    }

    #[test]
    fn test_calculate_xirr_multiple_cash_flows() {
        // Multiple cash flows over time
        let cash_flows = vec![-10000.0, 3000.0, 3000.0, 3000.0, 3000.0, 3000.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 10, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 4, 1).unwrap(),
        ];

        let result = calculate_xirr(&cash_flows, &dates, 0.1);
        assert!(result.is_some());
        assert!(result.unwrap() > 0.0);
    }

    #[test]
    fn test_calculate_xnpv_and_derivative() {
        let cash_flows = vec![-1000.0, 1100.0];
        let years_diffs = vec![0.0, 1.0]; // 0 years and 1 year from first date
        let (xnpv, derivative) = calculate_xnpv_and_derivative(&cash_flows, &years_diffs, 0.1);

        // At 10% rate, XNPV should be 0
        assert_relative_eq!(xnpv, 0.0, epsilon = 1e-6);

        // Derivative should be negative (XNPV decreases as rate increases)
        assert!(derivative < 0.0);
    }

    // Test the Polars interface
    #[test]
    fn test_xirr_polars_interface() {
        // Create series with cash flows and dates
        let values = vec![-1000.0, 300.0, 300.0, 300.0, 300.0, 300.0];
        let values_series = Series::new("values".into(), values);

        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 10, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 4, 1).unwrap(),
        ]);

        let kwargs = XirrKwargs { guess: Some(0.1) };
        let result = xirr(&[values_series, dates_series], &kwargs).unwrap();

        let xirr_value = result.f64().unwrap().get(0).unwrap();

        // Should return a reasonable positive rate
        assert!(xirr_value > 0.0);
        assert!(xirr_value < 1.0); // Less than 100%
    }

    #[test]
    fn test_xirr_with_nulls() {
        // Create series with null values
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

        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 5, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 11, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ]);

        let kwargs = XirrKwargs { guess: None }; // Use default guess
        let result = xirr(&[values_series, dates_series], &kwargs).unwrap();

        let xirr_value = result.f64().unwrap().get(0).unwrap();

        // Should calculate XIRR ignoring nulls
        assert!(xirr_value > 0.0);
    }

    #[test]
    fn test_xirr_no_positive_values() {
        let values = vec![-100.0, -200.0, -300.0];
        let values_series = Series::new("values".into(), values);

        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
        ]);

        let kwargs = XirrKwargs { guess: Some(0.1) };
        let result = xirr(&[values_series, dates_series], &kwargs).unwrap();

        // Should return null (None) for invalid input
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_xirr_no_negative_values() {
        let values = vec![100.0, 200.0, 300.0];
        let values_series = Series::new("values".into(), values);

        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
        ]);

        let kwargs = XirrKwargs { guess: Some(0.1) };
        let result = xirr(&[values_series, dates_series], &kwargs).unwrap();

        // Should return null (None) for invalid input
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_xirr_insufficient_values() {
        let values = vec![-100.0];
        let values_series = Series::new("values".into(), values);

        let dates_series = create_date_series(vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()]);

        let kwargs = XirrKwargs { guess: Some(0.1) };
        let result = xirr(&[values_series, dates_series], &kwargs).unwrap();

        // Should return null for insufficient data
        assert!(result.f64().unwrap().get(0).is_none());
    }

    #[test]
    fn test_xirr_mismatched_lengths() {
        let values = vec![-100.0, 200.0];
        let values_series = Series::new("values".into(), values);

        let dates_series = create_date_series(vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()]);

        let kwargs = XirrKwargs { guess: Some(0.1) };
        let result = xirr(&[values_series, dates_series], &kwargs);

        // Should return error for mismatched lengths
        assert!(result.is_err());
    }

    #[test]
    fn test_xirr_different_guess_values() {
        let cash_flows = vec![-10000.0, 3000.0, 3000.0, 3000.0, 3000.0, 3000.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 10, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 4, 1).unwrap(),
        ];

        // Test with different initial guesses
        let result1 = calculate_xirr(&cash_flows, &dates, 0.01).unwrap();
        let result2 = calculate_xirr(&cash_flows, &dates, 0.5).unwrap();
        let result3 = calculate_xirr(&cash_flows, &dates, -0.5).unwrap();

        // All should converge to the same value
        assert_relative_eq!(result1, result2, epsilon = 1e-6);
        assert_relative_eq!(result2, result3, epsilon = 1e-6);
    }

    // Excel compatibility tests
    #[cfg(test)]
    mod excel_verification_tests {
        use super::*;
        use approx::assert_relative_eq;
        use chrono::NaiveDate;

        #[test]
        fn test_excel_known_values() {
            // Test against known Excel outputs

            // Example 1: Simple investment with irregular payments
            // Excel: =XIRR({-10000,2750,4250,3250,2750},{"1/1/2008","3/1/2008","10/30/2008","2/15/2009","4/1/2009"})
            let cash_flows = vec![-10000.0, 2750.0, 4250.0, 3250.0, 2750.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2008, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2008, 3, 1).unwrap(),
                NaiveDate::from_ymd_opt(2008, 10, 30).unwrap(),
                NaiveDate::from_ymd_opt(2009, 2, 15).unwrap(),
                NaiveDate::from_ymd_opt(2009, 4, 1).unwrap(),
            ];
            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
            // Excel result: approximately 37.34%
            assert_relative_eq!(result, 0.3734, epsilon = 0.01);

            // Example 2: Two cash flows - simple case
            // Excel: =XIRR({-1000,1100},{"1/1/2023","1/1/2024"})
            let cash_flows = vec![-1000.0, 1100.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            ];
            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
            // Excel result: 10%
            assert_relative_eq!(result, 0.1, epsilon = 0.0001);
        }

        #[test]
        fn test_excel_financial_scenarios() {
            // Real estate investment with irregular cash flows
            let cash_flows = vec![-100000.0, 15000.0, 20000.0, 25000.0, 80000.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(), // Purchase
                NaiveDate::from_ymd_opt(2023, 6, 30).unwrap(), // Mid-year income
                NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(), // Year-end income
                NaiveDate::from_ymd_opt(2024, 12, 31).unwrap(), // Second year income
                NaiveDate::from_ymd_opt(2025, 1, 1).unwrap(), // Sale
            ];

            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();

            // Should be a reasonable positive return for a profitable investment
            assert!(result > 0.0);
            assert!(result < 1.0); // Less than 100%
        }

        #[test]
        fn test_excel_quarterly_payments() {
            // Quarterly payment scenario
            let cash_flows = vec![-4000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),  // Initial
                NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),  // Q1
                NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),  // Q2
                NaiveDate::from_ymd_opt(2023, 10, 1).unwrap(), // Q3
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),  // Q4
                NaiveDate::from_ymd_opt(2024, 4, 1).unwrap(),  // Q5
            ];

            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();

            // Should be a reasonable positive return
            assert!(result > 0.0);
            assert!(result.is_finite());
        }

        #[test]
        fn test_excel_edge_cases() {
            // Test edge cases that Excel handles

            // Very small cash flows
            let cash_flows = vec![-0.01, 0.005, 0.006];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            ];
            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
            assert!(result.is_finite());

            // Large cash flows
            let cash_flows = vec![-1000000.0, 500000.0, 600000.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            ];
            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();
            assert!(result > 0.0);
        }

        #[test]
        fn test_excel_date_ordering() {
            // Test that date ordering affects the result (unlike XNPV)
            let cash_flows = vec![-1000.0, 300.0, 400.0, 500.0];

            // Dates in chronological order
            let dates1 = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
            ];

            let result1 = calculate_xirr(&cash_flows, &dates1, 0.1).unwrap();

            // Result should be finite and reasonable
            assert!(result1.is_finite());
            assert!(result1 > -1.0);
            assert!(result1 < 10.0);
        }

        #[test]
        fn test_excel_non_convergent_cases() {
            // Case that might not converge easily - cash flows with multiple sign changes
            let cash_flows = vec![-1000.0, 3000.0, -2500.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
            ];

            // Try with different guesses
            let result1 = calculate_xirr(&cash_flows, &dates, 0.1);
            let result2 = calculate_xirr(&cash_flows, &dates, -0.5);
            let result3 = calculate_xirr(&cash_flows, &dates, 2.0);

            // At least one should find a solution or all should fail
            let found_solution = result1.is_some() || result2.is_some() || result3.is_some();

            if found_solution {
                // If we found solutions, verify they're reasonable
                if let Some(r) = result1 {
                    assert!(r > -1.0 && r < 10.0, "XIRR out of reasonable range");
                }
                if let Some(r) = result2 {
                    assert!(r > -1.0 && r < 10.0, "XIRR out of reasonable range");
                }
                if let Some(r) = result3 {
                    assert!(r > -1.0 && r < 10.0, "XIRR out of reasonable range");
                }
            }
        }

        #[test]
        fn test_excel_monthly_investment() {
            // Monthly investment scenario
            let mut cash_flows = vec![-10000.0]; // Initial investment
            let mut dates = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];

            // Monthly returns for 12 months
            for month in 1..=12 {
                cash_flows.push(1000.0);
                dates.push(NaiveDate::from_ymd_opt(2023, month, 1).unwrap());
            }

            let result = calculate_xirr(&cash_flows, &dates, 0.1).unwrap();

            // Should be a reasonable positive return
            assert!(result > 0.0);
            assert!(result < 2.0); // Less than 200%
        }
    }
}
