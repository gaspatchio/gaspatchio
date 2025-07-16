// ABOUTME: Excel PMT function implementation for calculating loan payment amounts
// ABOUTME: Handles constant payments and interest rates with Excel-compatible behavior

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct PmtKwargs {
    pub fv: Option<f64>,
    pub payment_type: Option<i32>,
}

/// Excel PMT implementation for Polars
///
/// Calculates the payment for a loan based on constant payments and a constant interest rate.
/// The payment includes principal and interest but not taxes, reserve payments, or fees.
///
/// # Parameters
/// - rate: Interest rate per period
/// - nper: Total number of payment periods
/// - pv: Present value (principal amount)
/// - fv: Future value (remaining balance after final payment), default 0
/// - payment_type: When payments are due (0 = end of period, 1 = beginning), default 0
///
/// # Returns
/// The payment amount as a negative value (cash outflow)
pub fn pmt(inputs: &[Series], kwargs: &PmtKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 3 {
        return Err(PolarsError::ComputeError(
            "pmt requires at least 3 parameters: rate, nper, and pv".into(),
        ));
    }

    // Extract input series
    let rate_series = &inputs[0];
    let nper_series = &inputs[1];
    let pv_series = &inputs[2];

    // Extract typed arrays
    let rate_array = rate_series.f64()?;
    let nper_array = nper_series.f64()?;
    let pv_array = pv_series.f64()?;

    // Process optional parameters
    let fv = kwargs.fv.unwrap_or(0.0);
    let payment_type = kwargs.payment_type.unwrap_or(0);

    // Validate payment_type
    if payment_type != 0 && payment_type != 1 {
        return Err(PolarsError::ComputeError(
            "payment_type must be 0 (end of period) or 1 (beginning of period)".into(),
        ));
    }

    // Use iterator pattern for better performance
    #[allow(clippy::useless_conversion)]
    let result_ca = rate_array
        .into_iter()
        .zip(nper_array.into_iter())
        .zip(pv_array.into_iter())
        .map(|((rate_opt, nper_opt), pv_opt)| {
            match (rate_opt, nper_opt, pv_opt) {
                (Some(rate), Some(nper), Some(pv)) => {
                    // Check for invalid inputs that would cause #NUM! error
                    if rate <= -1.0 {
                        return None; // Excel returns #NUM! for rate <= -1
                    }
                    if nper == 0.0 {
                        return None; // Excel returns #NUM! for nper = 0
                    }

                    Some(calculate_pmt(rate, nper, pv, fv, payment_type))
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("pmt".into()).into_series())
}

/// Calculate the payment amount for a loan
///
/// This implements Excel's PMT formula exactly, including all edge cases and quirks.
/// The payment is returned as a negative value (cash outflow).
fn calculate_pmt(rate: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
    // Special case: when rate is 0, use simple division
    if rate == 0.0 {
        return -(pv + fv) / nper;
    }

    // Excel's PMT formula:
    // For ordinary annuity (type=0):
    //   PMT = -(PV * rate * (1+rate)^nper + FV * rate) / ((1+rate)^nper - 1)
    // For annuity due (type=1):
    //   PMT = -(PV * rate * (1+rate)^nper + FV * rate) / ((1+rate)^nper - 1) / (1+rate)

    let power_term = (1.0 + rate).powf(nper);

    // Calculate numerator: PV * rate * (1+rate)^nper + FV * rate
    let numerator = pv * rate * power_term + fv * rate;

    // Calculate denominator: (1+rate)^nper - 1
    let denominator = power_term - 1.0;

    // Calculate base payment (negative for cash outflow)
    let mut payment = -numerator / denominator;

    // Adjust for payment timing (beginning vs end of period)
    if payment_type == 1 {
        // Payments at beginning of period - divide by (1+rate)
        payment /= 1.0 + rate;
    }

    payment
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn test_calculate_pmt_basic_loan() {
        // Test a simple loan: $10,000 at 5% annual (monthly payments) for 2 years
        let monthly_rate = 0.05 / 12.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_pmt(monthly_rate, nper, pv, fv, payment_type);

        // Expected payment is approximately -$438.71
        assert_relative_eq!(result, -438.713_897_340_686, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_pmt_with_future_value() {
        // Test with a future value (balloon payment)
        let rate = 0.06 / 12.0;
        let nper = 60.0;
        let pv = 20000.0;
        let fv = -5000.0; // Negative because it's money we receive back
        let payment_type = 0;

        let result = calculate_pmt(rate, nper, pv, fv, payment_type);

        // Payment should be lower due to the balloon payment at the end
        assert!(result > -387.0); // Less than if no future value
        assert!(result < -300.0); // But still a significant payment
    }

    #[test]
    fn test_calculate_pmt_beginning_of_period() {
        // Test payment at beginning of period
        let rate = 0.08 / 12.0;
        let nper = 36.0;
        let pv = 15000.0;
        let fv = 0.0;

        // Calculate both end and beginning of period
        let end_payment = calculate_pmt(rate, nper, pv, fv, 0);
        let beginning_payment = calculate_pmt(rate, nper, pv, fv, 1);

        // Beginning payments should be less (in absolute value) due to time value
        assert!(beginning_payment.abs() < end_payment.abs());

        // The ratio should be 1/(1+rate)
        assert_relative_eq!(
            beginning_payment,
            end_payment / (1.0 + rate),
            epsilon = 1e-10
        );
    }

    #[test]
    fn test_calculate_pmt_zero_rate() {
        // Test special case when rate is 0
        let rate = 0.0;
        let nper = 12.0;
        let pv = 12000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_pmt(rate, nper, pv, fv, payment_type);

        // With 0% interest, payment is simply principal / periods
        assert_relative_eq!(result, -1000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_pmt_zero_rate_with_fv() {
        // Test zero rate with future value
        let rate = 0.0;
        let nper = 10.0;
        let pv = 5000.0;
        let fv = -1000.0;
        let payment_type = 0;

        let result = calculate_pmt(rate, nper, pv, fv, payment_type);

        // Payment = -(pv + fv) / nper = -(5000 - 1000) / 10 = -400
        assert_relative_eq!(result, -400.0, epsilon = 1e-10);
    }

    #[test]
    fn test_pmt_polars_interface() {
        // Test the Polars interface
        let rate_series = Series::new("rate".into(), vec![0.05 / 12.0, 0.06 / 12.0, 0.07 / 12.0]);
        let nper_series = Series::new("nper".into(), vec![24.0, 36.0, 48.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 15000.0, 20000.0]);

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Check first result matches our basic test
        assert_relative_eq!(
            values.get(0).unwrap(),
            -438.713_897_340_686,
            epsilon = 1e-10
        );

        // All values should be negative (payments)
        assert!(values.get(0).unwrap() < 0.0);
        assert!(values.get(1).unwrap() < 0.0);
        assert!(values.get(2).unwrap() < 0.0);
    }

    #[test]
    fn test_pmt_with_optional_params() {
        // Test with optional parameters specified
        let rate_series = Series::new("rate".into(), vec![0.08 / 12.0]);
        let nper_series = Series::new("nper".into(), vec![60.0]);
        let pv_series = Series::new("pv".into(), vec![25000.0]);

        let kwargs = PmtKwargs {
            fv: Some(-5000.0),
            payment_type: Some(1),
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();
        assert!(values.get(0).is_some());
        assert!(values.get(0).unwrap() < 0.0);
    }

    #[test]
    fn test_null_handling() {
        // Create series with null values
        let rate_series = Series::new(
            "rate".into(),
            vec![Some(0.05 / 12.0), None, Some(0.06 / 12.0)],
        );
        let nper_series = Series::new("nper".into(), vec![Some(24.0), Some(36.0), None]);
        let pv_series = Series::new(
            "pv".into(),
            vec![Some(10000.0), Some(15000.0), Some(20000.0)],
        );

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated
        assert!(values.get(0).is_some());
        // Second value should be null (rate is null)
        assert!(values.get(1).is_none());
        // Third value should be null (nper is null)
        assert!(values.get(2).is_none());
    }

    #[test]
    fn test_invalid_rate() {
        // Test rate <= -1 (should return None/null)
        let rate_series = Series::new("rate".into(), vec![-1.0, -1.5, -0.5]);
        let nper_series = Series::new("nper".into(), vec![24.0, 24.0, 24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (rate <= -1)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated (rate > -1)
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_nper() {
        // Test nper = 0 (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05, 0.06, 0.07]);
        let nper_series = Series::new("nper".into(), vec![0.0, 24.0, 0.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First and third should be null (nper = 0)
        assert!(values.get(0).is_none());
        assert!(values.get(2).is_none());
        // Second should be calculated
        assert!(values.get(1).is_some());
    }

    #[test]
    fn test_invalid_payment_type() {
        // Test invalid payment_type
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let nper_series = Series::new("nper".into(), vec![24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0]);

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: Some(2), // Invalid value
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_insufficient_inputs() {
        // Test with insufficient inputs
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let nper_series = Series::new("nper".into(), vec![24.0]);

        let kwargs = PmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pmt(&[rate_series, nper_series], &kwargs);

        assert!(result.is_err());
    }
}

// Excel Verification Tests
//
// These tests verify exact compatibility with Microsoft Excel's PMT function.
// The PMT function is widely used in financial calculations and must match
// Excel's implementation exactly for compatibility with existing spreadsheets.
#[cfg(test)]
mod excel_verification_tests {
    use super::*;
    use approx::assert_relative_eq;

    fn test_pmt(rate: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
        let rate_series = Series::new("rate".into(), vec![rate]);
        let nper_series = Series::new("nper".into(), vec![nper]);
        let pv_series = Series::new("pv".into(), vec![pv]);
        let kwargs = PmtKwargs {
            fv: Some(fv),
            payment_type: Some(payment_type),
        };
        let result = pmt(&[rate_series, nper_series, pv_series], &kwargs).unwrap();
        result.f64().unwrap().get(0).unwrap()
    }

    #[test]
    fn test_excel_mortgage_example() {
        // Standard mortgage example from Excel documentation
        // $200,000 loan at 6% annual rate for 30 years
        let rate = 0.06 / 12.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Excel result: -$1,199.10
        assert_relative_eq!(result, -1199.101_050_305_514, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_car_loan_example() {
        // Car loan example: $25,000 at 7% for 5 years
        let rate = 0.07 / 12.0;
        let nper = 5.0 * 12.0;
        let pv = 25000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Expected monthly payment
        assert_relative_eq!(result, -495.029_963_508_737, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_savings_goal() {
        // Saving for a goal: accumulate $50,000 in 10 years at 3% interest
        let rate = 0.03 / 12.0;
        let nper = 10.0 * 12.0;
        let pv = 0.0;
        let fv = 50000.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Monthly payment needed (should be negative - we're paying in)
        assert!(result < 0.0);
        assert_relative_eq!(result, -357.803_723_491_957, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_annuity_due() {
        // Annuity due (payments at beginning): $100,000 at 8% for 20 years
        let rate = 0.08 / 12.0;
        let nper = 20.0 * 12.0;
        let pv = 100000.0;
        let fv = 0.0;
        let payment_type = 1; // Beginning of period

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Payment at beginning of period is less than at end
        assert!(result < 0.0);
        assert_relative_eq!(result, -830.900_730_788_212, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_balloon_payment() {
        // Loan with balloon payment: $50,000 loan, $10,000 balloon, 4% for 7 years
        let rate = 0.04 / 12.0;
        let nper = 7.0 * 12.0;
        let pv = 50000.0;
        let fv = -10000.0; // Negative because we receive it back
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Monthly payment is reduced due to balloon payment
        assert!(result < 0.0);
        assert!(result.abs() < 600.0); // Less than full amortization
    }

    #[test]
    fn test_excel_negative_interest_rate() {
        // Negative interest rate (unusual but possible)
        let rate = -0.02 / 12.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // With negative rate, payments are less than principal/periods
        assert!(result < 0.0);
        assert!(result.abs() < 10000.0 / 24.0);
    }

    #[test]
    fn test_excel_very_high_interest() {
        // Very high interest rate
        let rate = 0.50 / 12.0; // 50% annual
        let nper = 12.0;
        let pv = 1000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Payment should be significantly higher than principal/periods
        assert!(result < 0.0);
        assert!(result.abs() > 1000.0 / 12.0);
    }

    #[test]
    fn test_excel_combination_pv_fv() {
        // Both present and future value
        // Start with $5,000 debt, want to have $2,000 saved at end
        let rate = 0.05 / 12.0;
        let nper = 36.0;
        let pv = 5000.0;
        let fv = 2000.0; // Positive because we want to accumulate
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Need to pay off debt AND save
        assert!(result < 0.0);
        assert_relative_eq!(result, -201.462_946_399_326, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_quarterly_payments() {
        // Quarterly payments instead of monthly
        let annual_rate = 0.06;
        let rate = annual_rate / 4.0; // Quarterly
        let nper = 5.0 * 4.0; // 5 years of quarterly payments
        let pv = 20000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Quarterly payment on $20,000
        assert!(result < 0.0);
        assert_relative_eq!(result, -1164.914_717_489_332, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_single_payment() {
        // Single payment loan (nper = 1)
        let rate = 0.10;
        let nper = 1.0;
        let pv = 1000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Should be principal plus interest
        assert_relative_eq!(result, -1100.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_edge_case_small_rate() {
        // Very small interest rate (near zero but not zero)
        let rate = 0.000001;
        let nper = 12.0;
        let pv = 12000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Should be very close to simple division
        assert!(result < 0.0);
        assert!((result + 1000.0).abs() < 0.01);
    }

    #[test]
    fn test_excel_known_discrepancy() {
        // Document any known discrepancies with Excel
        // Excel may have floating point precision differences

        // Very large loan amount
        let rate = 0.045 / 12.0;
        let nper = 30.0 * 12.0;
        let pv = 1_000_000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_pmt(rate, nper, pv, fv, payment_type);

        // Our implementation should handle large numbers correctly
        assert!(result < 0.0);
        assert!(result.abs() > 5000.0); // Significant monthly payment
    }
}
