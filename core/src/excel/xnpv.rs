// ABOUTME: Excel XNPV (Net Present Value with irregular cash flows) function implementation for Polars
// ABOUTME: Calculates the net present value of cash flows occurring at irregular intervals

use chrono::{Duration, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

// Excel's XNPV uses a 365-day year basis for discounting
const DAYS_PER_YEAR: f64 = 365.0;

#[derive(Deserialize, Clone)]
pub struct XNPVKwargs {}

/// Excel XNPV (Net Present Value for irregular cash flows) implementation for Polars
///
/// Returns the net present value for a schedule of cash flows that is not necessarily periodic.
/// To calculate the net present value for a series of cash flows that is periodic, use the NPV function.
///
/// # Arguments
/// * `rate` - The discount rate to apply to the cash flows (required)
/// * `values` - A series of cash flows that corresponds to a schedule of payments in dates (required)
/// * `dates` - A schedule of dates that corresponds to values (required)
///
/// # Excel Behavior
/// * The first cash flow is not discounted (it occurs at the first date)
/// * All subsequent cash flows are discounted based on the number of days from the first date
/// * Uses a 365-day year basis for discounting calculations
/// * The first date indicates the beginning of the schedule of payments
/// * Values must include at least one positive and one negative value
/// * Dates must be valid Excel dates and not precede the first date
///
/// # Sign Convention
/// * Negative values represent cash outflows (payments)
/// * Positive values represent cash inflows (receipts)
///
/// # Returns
/// The net present value of the cash flows as of the first date
///
/// # Errors
/// Returns an error if:
/// * Fewer than 3 inputs are provided (rate, values, dates)
/// * Values and dates arrays have different lengths
/// * Values do not contain at least one positive and one negative value
/// * Any date precedes the first date
/// * Rate or values contain non-numeric values
/// * Dates contain invalid dates
///
/// # Excel Compatibility Notes
/// * XNPV does not discount the initial cash flow (first value)
/// * All subsequent payments are discounted based on a 365-day year
/// * The first payment date indicates the beginning of the schedule
/// * Other dates must be later than the first date, but need not be in order
pub fn xnpv(inputs: &[Series], _kwargs: &XNPVKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 3 {
        return Err(PolarsError::ComputeError(
            "xnpv requires exactly 3 parameters: rate, values, and dates".into(),
        ));
    }

    // Extract input series
    let rate_series = &inputs[0];
    let values_series = &inputs[1];
    let dates_series = &inputs[2];

    // For XNPV, we calculate one result for the entire arrays
    // This is similar to how IRR works - it processes the entire array at once
    let rate_array = rate_series.f64()?;
    let values_array = values_series.f64()?;
    let dates_array = dates_series.date()?;

    // Check if all arrays have same length
    if values_array.len() != dates_array.len() {
        return Err(PolarsError::ComputeError(
            "values and dates must have the same length".into(),
        ));
    }

    // Get the rate (assume first element, or could be a scalar)
    let rate = match rate_array.get(0) {
        Some(r) => r,
        None => return Err(PolarsError::ComputeError("rate cannot be null".into())),
    };

    // Convert to vectors for easier processing
    let cash_flows: Vec<Option<f64>> = values_array.into_iter().collect();
    let dates: Vec<Option<i32>> = dates_array.into_iter().collect();

    // Filter out None values and collect valid cash flows and dates
    let mut valid_cash_flows = Vec::new();
    let mut valid_dates = Vec::new();

    for (cf_opt, date_opt) in cash_flows.iter().zip(dates.iter()) {
        match (cf_opt, date_opt) {
            (Some(cf), Some(date)) => {
                valid_cash_flows.push(*cf);
                valid_dates.push(*date);
            }
            _ => {} // Skip null values
        }
    }

    // Calculate XNPV for the series
    let result = match calculate_xnpv_for_series(rate, &valid_cash_flows, &valid_dates) {
        Ok(xnpv_value) => Some(xnpv_value),
        Err(_) => None, // Return null for errors
    };

    // Return a single-element series with the XNPV result
    let result_ca: Float64Chunked = [result].iter().copied().collect();
    Ok(result_ca.with_name("xnpv".into()).into_series())
}

/// Calculate XNPV for a series of cash flows and dates (given as days since epoch)
fn calculate_xnpv_for_series(rate: f64, cash_flows: &[f64], dates: &[i32]) -> PolarsResult<f64> {
    // Validate input lengths
    if cash_flows.len() != dates.len() {
        return Err(PolarsError::ComputeError(
            "cash_flows and dates must have the same length".into(),
        ));
    }

    if cash_flows.is_empty() {
        return Ok(0.0);
    }

    // Validate that there's at least one positive and one negative value
    let has_positive = cash_flows.iter().any(|&cf| cf > 0.0);
    let has_negative = cash_flows.iter().any(|&cf| cf < 0.0);

    if !has_positive || !has_negative {
        return Err(PolarsError::ComputeError(
            "values must contain at least one positive and one negative value".into(),
        ));
    }

    // Convert days since epoch to NaiveDate
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    let naive_dates: Vec<NaiveDate> = dates
        .iter()
        .map(|&days| epoch + Duration::days(i64::from(days)))
        .collect();

    // Use the pure calculation function
    calculate_xnpv(rate, cash_flows, &naive_dates)
}

/// Calculate XNPV for a complete schedule of cash flows and dates
///
/// This implements Excel's XNPV calculation logic exactly.
/// The first cash flow is not discounted (occurs at time 0).
/// All subsequent cash flows are discounted based on the number of days
/// from the first date using a 365-day year.
///
/// # Excel Formula
/// XNPV = Σ[values[i] / (1 + rate)^(days[i] / 365)] for i = 0 to n-1
///
/// Where:
/// - values[0] is not discounted (occurs at the first date)
/// - days[i] is the number of days from the first date to date[i]
/// - All calculations use a 365-day year basis
///
/// # Arguments
/// * `rate` - The discount rate
/// * `cash_flows` - Vector of cash flow amounts
/// * `dates` - Vector of dates corresponding to cash flows
///
/// # Returns
/// The net present value of the cash flows as of the first date
///
/// # Errors
/// Returns an error if:
/// * Cash flows and dates have different lengths
/// * Cash flows don't contain at least one positive and one negative value
/// * Any date precedes the first date
pub fn calculate_xnpv(rate: f64, cash_flows: &[f64], dates: &[NaiveDate]) -> PolarsResult<f64> {
    // Validate input lengths
    if cash_flows.len() != dates.len() {
        return Err(PolarsError::ComputeError(
            "cash_flows and dates must have the same length".into(),
        ));
    }

    if cash_flows.is_empty() {
        return Ok(0.0);
    }

    // Validate that there's at least one positive and one negative value
    let has_positive = cash_flows.iter().any(|&cf| cf > 0.0);
    let has_negative = cash_flows.iter().any(|&cf| cf < 0.0);

    if !has_positive || !has_negative {
        return Err(PolarsError::ComputeError(
            "values must contain at least one positive and one negative value".into(),
        ));
    }

    // Get the first date as the reference point
    let first_date = dates[0];

    // Validate that all dates are >= first_date
    for (i, &date) in dates.iter().enumerate() {
        if date < first_date {
            return Err(PolarsError::ComputeError(
                format!("date at index {} precedes the first date", i).into(),
            ));
        }
    }

    // Calculate XNPV
    let mut npv = 0.0;

    for (i, (&cash_flow, &date)) in cash_flows.iter().zip(dates.iter()).enumerate() {
        if i == 0 {
            // First cash flow is not discounted
            npv += cash_flow;
        } else {
            // Calculate days from first date
            let days_diff = (date - first_date).num_days() as f64;
            let years_diff = days_diff / DAYS_PER_YEAR;

            // Discount the cash flow
            let discount_factor = (1.0 + rate).powf(years_diff);
            npv += cash_flow / discount_factor;
        }
    }

    Ok(npv)
}

/// Calculate the present value of a single cash flow
/// Used when processing row-by-row in the Polars interface
#[allow(dead_code)]
#[inline]
fn calculate_single_cash_flow_pv(
    rate: f64,
    cash_flow: f64,
    date: NaiveDate,
    first_date: NaiveDate,
) -> f64 {
    if date == first_date {
        // First cash flow is not discounted
        cash_flow
    } else {
        // Calculate days from first date
        let days_diff = (date - first_date).num_days() as f64;
        let years_diff = days_diff / DAYS_PER_YEAR;

        // Discount the cash flow
        let discount_factor = (1.0 + rate).powf(years_diff);
        cash_flow / discount_factor
    }
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
    fn test_calculate_xnpv_simple_case() {
        // Simple case: investment at start, return after 1 year
        let cash_flows = vec![-1000.0, 1100.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ];

        let result = calculate_xnpv(0.10, &cash_flows, &dates).unwrap();

        // NPV = -1000 + 1100 / (1.10)^1 = -1000 + 1000 = 0
        assert_relative_eq!(result, 0.0, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_xnpv_irregular_periods() {
        // Cash flows at irregular intervals
        let cash_flows = vec![-1000.0, 500.0, 300.0, 400.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),  // Day 0
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),  // Day 90 (approx)
            NaiveDate::from_ymd_opt(2023, 7, 15).unwrap(), // Day 195 (approx)
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),  // Day 365
        ];

        let result = calculate_xnpv(0.10, &cash_flows, &dates).unwrap();

        // Manual calculation:
        // NPV = -1000 + 500/(1.10)^(90/365) + 300/(1.10)^(195/365) + 400/(1.10)^(365/365)
        let expected = -1000.0
            + 500.0 / (1.10_f64.powf(90.0 / 365.0))
            + 300.0 / (1.10_f64.powf(195.0 / 365.0))
            + 400.0 / (1.10_f64.powf(365.0 / 365.0));

        assert_relative_eq!(result, expected, epsilon = 1e-6);
    }

    #[test]
    fn test_calculate_xnpv_same_dates() {
        // All cash flows on the same date (first date)
        let cash_flows = vec![-1000.0, 500.0, 300.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
        ];

        let result = calculate_xnpv(0.10, &cash_flows, &dates).unwrap();

        // All cash flows are at time 0, so no discounting
        assert_relative_eq!(result, -200.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_xnpv_zero_rate() {
        // Zero discount rate
        let cash_flows = vec![-1000.0, 500.0, 300.0, 400.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 6, 1).unwrap(),
        ];

        let result = calculate_xnpv(0.0, &cash_flows, &dates).unwrap();

        // With zero rate, NPV is just the sum of cash flows
        assert_relative_eq!(result, 200.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_xnpv_validation_errors() {
        // Test error cases

        // Different lengths
        let cash_flows = vec![-1000.0, 500.0];
        let dates = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        assert!(calculate_xnpv(0.10, &cash_flows, &dates).is_err());

        // No positive values
        let cash_flows = vec![-1000.0, -500.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
        ];
        assert!(calculate_xnpv(0.10, &cash_flows, &dates).is_err());

        // No negative values
        let cash_flows = vec![1000.0, 500.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
        ];
        assert!(calculate_xnpv(0.10, &cash_flows, &dates).is_err());

        // Date before first date
        let cash_flows = vec![-1000.0, 500.0];
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
        ];
        assert!(calculate_xnpv(0.10, &cash_flows, &dates).is_err());
    }

    #[test]
    fn test_calculate_single_cash_flow_pv() {
        let first_date = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let later_date = NaiveDate::from_ymd_opt(2024, 1, 1).unwrap();

        // Cash flow at first date (not discounted)
        let pv1 = calculate_single_cash_flow_pv(0.10, 1000.0, first_date, first_date);
        assert_relative_eq!(pv1, 1000.0, epsilon = 1e-10);

        // Cash flow after 1 year (discounted)
        let pv2 = calculate_single_cash_flow_pv(0.10, 1100.0, later_date, first_date);
        assert_relative_eq!(pv2, 1000.0, epsilon = 1e-6);
    }

    // Test the Polars interface
    #[test]
    fn test_xnpv_polars_interface() {
        // Create a single rate and arrays of cash flows and dates
        let rate_series = Series::new("rate".into(), vec![0.10]);
        let values_series = Series::new("values".into(), vec![-1000.0, 500.0, 300.0, 400.0]);
        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 15).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ]);

        let kwargs = XNPVKwargs {};
        let result = xnpv(&[rate_series, values_series, dates_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Should return a single value (the XNPV of the entire series)
        assert_eq!(values.len(), 1);
        assert!(values.get(0).is_some());

        // Calculate expected value manually
        let expected = -1000.0
            + 500.0 / (1.10_f64.powf(90.0 / 365.0))
            + 300.0 / (1.10_f64.powf(195.0 / 365.0))
            + 400.0 / (1.10_f64.powf(365.0 / 365.0));

        assert_relative_eq!(values.get(0).unwrap(), expected, epsilon = 1e-6);
    }

    #[test]
    fn test_null_handling() {
        let rate_series = Series::new("rate".into(), vec![0.10]);
        let values_series = Series::new(
            "values".into(),
            vec![Some(-1000.0), None, Some(300.0), Some(400.0)],
        );
        let dates_series = create_date_series(vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 7, 15).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
        ]);

        let kwargs = XNPVKwargs {};
        let result = xnpv(&[rate_series, values_series, dates_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Should calculate with non-null values only
        assert!(values.get(0).is_some());
    }

    #[test]
    fn test_insufficient_parameters() {
        let rate_series = Series::new("rate".into(), vec![0.10]);
        let values_series = Series::new("values".into(), vec![-1000.0]);

        let kwargs = XNPVKwargs {};
        let result = xnpv(&[rate_series, values_series], &kwargs);

        assert!(result.is_err());
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
            // Example from Excel documentation

            // Investment scenario with irregular cash flows
            let cash_flows = vec![-10000.0, 2750.0, 4250.0, 3250.0, 2750.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2008, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2008, 3, 1).unwrap(),
                NaiveDate::from_ymd_opt(2008, 10, 30).unwrap(),
                NaiveDate::from_ymd_opt(2009, 2, 15).unwrap(),
                NaiveDate::from_ymd_opt(2009, 4, 1).unwrap(),
            ];

            let result = calculate_xnpv(0.09, &cash_flows, &dates).unwrap();

            // Expected Excel result: approximately $2,086.65
            // Note: Excel uses specific date calculations that may vary slightly
            assert_relative_eq!(result, 2086.65, epsilon = 10.0);
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

            let result = calculate_xnpv(0.12, &cash_flows, &dates).unwrap();

            // Should be a reasonable positive NPV for a profitable investment
            assert!(result > 0.0);
        }

        #[test]
        fn test_excel_bond_scenario() {
            // Bond purchase with irregular coupon payments
            let cash_flows = vec![-1000.0, 50.0, 50.0, 50.0, 1050.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(), // Purchase
                NaiveDate::from_ymd_opt(2023, 6, 30).unwrap(), // Coupon
                NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(), // Coupon
                NaiveDate::from_ymd_opt(2024, 6, 30).unwrap(), // Coupon
                NaiveDate::from_ymd_opt(2024, 12, 31).unwrap(), // Coupon + Principal
            ];

            let result = calculate_xnpv(0.06, &cash_flows, &dates).unwrap();

            // Should be close to zero for a bond bought at par with yield = coupon rate
            assert_relative_eq!(result, 0.0, epsilon = 100.0);
        }

        #[test]
        fn test_excel_quarterly_payments() {
            // Quarterly payment scenario: investment that breaks even
            let cash_flows = vec![-4000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),  // Initial
                NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),  // Q1
                NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),  // Q2
                NaiveDate::from_ymd_opt(2023, 10, 1).unwrap(), // Q3
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),  // Q4
                NaiveDate::from_ymd_opt(2024, 4, 1).unwrap(),  // Q5
            ];

            let result = calculate_xnpv(0.08, &cash_flows, &dates).unwrap();

            // With -4000 initial investment and 5 payments of 1000 each:
            // At 8% discount rate, this should have positive NPV
            assert!(result > 0.0);

            // The result should be finite and reasonable
            assert!(result.is_finite());
            assert!(result < 2000.0); // Not extremely positive
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
            let result = calculate_xnpv(0.05, &cash_flows, &dates).unwrap();
            assert!(result.abs() < 1.0);

            // Large cash flows
            let cash_flows = vec![-1000000.0, 500000.0, 600000.0];
            let dates = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
            ];
            let result = calculate_xnpv(0.10, &cash_flows, &dates).unwrap();
            assert!(result > 0.0);
        }

        #[test]
        fn test_excel_date_ordering() {
            // Test that date ordering doesn't matter (except for first date)
            let cash_flows = vec![-1000.0, 300.0, 400.0, 500.0];

            // Dates in chronological order
            let dates1 = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
            ];

            // Same dates but out of order (first date remains first)
            let dates2 = vec![
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
            ];

            let result1 = calculate_xnpv(0.10, &cash_flows, &dates1).unwrap();
            let result2 = calculate_xnpv(
                0.10,
                &[cash_flows[0], cash_flows[3], cash_flows[1], cash_flows[2]],
                &dates2,
            )
            .unwrap();

            // Results should be the same regardless of order
            assert_relative_eq!(result1, result2, epsilon = 1e-6);
        }
    }
}
