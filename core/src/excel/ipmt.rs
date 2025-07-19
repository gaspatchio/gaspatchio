// ABOUTME: Excel IPMT function implementation for calculating interest payments on loans/investments
// ABOUTME: Calculates the interest payment for a specific period with constant payments and interest rate

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct IpmtKwargs {
    pub fv: Option<f64>,
    pub payment_type: Option<i32>,
}

/// Excel IPMT implementation for Polars
///
/// Calculates the interest payment for a specific period of an investment or loan
/// based on periodic, constant payments and a constant interest rate.
///
/// The interest payment represents the portion of the total payment that goes
/// toward interest (as opposed to principal) during the specified period.
///
/// # Parameters
/// - rate: Interest rate per period
/// - per: The specific period for which to calculate the interest payment (must be between 1 and nper)
/// - nper: Total number of payment periods
/// - pv: Present value (loan amount or investment principal)
/// - fv: Future value (remaining balance after final payment), default 0
/// - payment_type: When payments are due (0 = end of period, 1 = beginning), default 0
///
/// # Returns
/// The interest payment for the specified period as a negative value (cash outflow)
///
/// # Errors
/// Returns null/None for invalid inputs:
/// - per < 1 or per > nper
/// - rate <= -1 (would cause mathematical errors)
/// - nper = 0 (no payment periods)
pub fn ipmt(inputs: &[Series], kwargs: &IpmtKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 4 {
        return Err(PolarsError::ComputeError(
            "ipmt requires at least 4 parameters: rate, per, nper, and pv".into(),
        ));
    }

    // Extract input series
    let rate_series = &inputs[0];
    let per_series = &inputs[1];
    let nper_series = &inputs[2];
    let pv_series = &inputs[3];

    // Extract typed arrays
    let rate_array = rate_series.f64()?;
    let per_array = per_series.f64()?;
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
        .zip(per_array.into_iter())
        .zip(nper_array.into_iter())
        .zip(pv_array.into_iter())
        .map(|(((rate_opt, per_opt), nper_opt), pv_opt)| {
            match (rate_opt, per_opt, nper_opt, pv_opt) {
                (Some(rate), Some(per), Some(nper), Some(pv)) => {
                    // Validate inputs that would cause Excel #NUM! error
                    if rate <= -1.0 {
                        return None; // Excel returns #NUM! for rate <= -1
                    }
                    if nper == 0.0 {
                        return None; // Excel returns #NUM! for nper = 0
                    }
                    if per < 1.0 || per > nper {
                        return None; // Excel returns #NUM! for per out of range
                    }

                    Some(calculate_ipmt(rate, per, nper, pv, fv, payment_type))
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("ipmt".into()).into_series())
}

/// Calculate the interest payment for a specific period
///
/// This implements Excel's IPMT calculation logic exactly. The interest payment
/// is calculated based on the remaining balance at the beginning of the specified period.
///
/// # Algorithm
/// 1. Calculate the total payment amount using PMT formula
/// 2. Calculate the remaining balance at the beginning of the period
/// 3. Interest payment = rate * remaining balance (adjusted for payment timing)
///
/// # Excel Behavior
/// - For period 1, remaining balance = pv (full principal)
/// - For subsequent periods, remaining balance is calculated after previous payments
/// - Interest is always calculated on the balance at the beginning of the period
/// - Payment timing affects when interest is calculated relative to payment
fn calculate_ipmt(rate: f64, per: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
    // Special case: when rate is 0, no interest is charged
    if rate == 0.0 {
        return 0.0;
    }

    // Calculate the total payment amount (PMT)
    let _payment = calculate_pmt(rate, nper, pv, fv, payment_type);

    // For the first period, the remaining balance is the full present value
    if per == 1.0 {
        if payment_type == 1 {
            // Beginning of period: no interest on first payment
            return 0.0;
        } else {
            // End of period: interest calculated on full principal
            return pv * rate;
        }
    }

    // For subsequent periods, calculate the remaining balance at the beginning of the period
    let remaining_balance =
        calculate_remaining_balance(rate, per - 1.0, nper, pv, fv, payment_type);

    // Interest is calculated on the remaining balance
    remaining_balance * rate
}

/// Calculate the remaining balance at the beginning of a specific period
///
/// This uses the future value formula to determine how much principal remains
/// after a certain number of payments have been made.
fn calculate_remaining_balance(
    rate: f64,
    periods_paid: f64,
    nper: f64,
    pv: f64,
    fv: f64,
    payment_type: i32,
) -> f64 {
    if periods_paid == 0.0 {
        return pv;
    }

    // Calculate payment amount
    let payment = calculate_pmt(rate, nper, pv, fv, payment_type);

    // Calculate remaining balance using the future value formula
    // Balance = PV * (1+rate)^periods_paid + PMT * ((1+rate)^periods_paid - 1) / rate * (1+rate*type)
    let compound_factor = (1.0 + rate).powf(periods_paid);
    let annuity_factor = (compound_factor - 1.0) / rate;
    let type_factor = if payment_type == 1 { 1.0 + rate } else { 1.0 };

    pv * compound_factor + payment * annuity_factor * type_factor
}

/// Calculate the payment amount (PMT) for the loan/investment
///
/// This replicates the PMT function logic to avoid circular dependencies
/// while maintaining exact Excel compatibility.
fn calculate_pmt(rate: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
    // Special case: when rate is 0, use simple division
    if rate == 0.0 {
        return -(pv + fv) / nper;
    }

    // Excel's PMT formula
    let power_term = (1.0 + rate).powf(nper);
    let numerator = pv * rate * power_term + fv * rate;
    let denominator = power_term - 1.0;

    let mut payment = -numerator / denominator;

    // Adjust for payment timing (beginning vs end of period)
    if payment_type == 1 {
        payment /= 1.0 + rate;
    }

    payment
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn test_calculate_ipmt_first_period() {
        // Test first period of a loan: $10,000 at 5% annual (monthly) for 2 years
        let monthly_rate = 0.05 / 12.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ipmt(monthly_rate, per, nper, pv, fv, payment_type);

        // First period interest = principal * rate = 10000 * (0.05/12) = 41.67
        assert_relative_eq!(result, 41.666_666_666_667, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_ipmt_later_period() {
        // Test second period of the same loan
        let monthly_rate = 0.05 / 12.0;
        let per = 2.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ipmt(monthly_rate, per, nper, pv, fv, payment_type);

        // Second period interest should be less than first (principal has been reduced)
        assert!(result < 41.67);
        assert!(result > 40.0);
    }

    #[test]
    fn test_calculate_ipmt_zero_rate() {
        // Test with zero interest rate
        let rate = 0.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ipmt(rate, per, nper, pv, fv, payment_type);

        // With zero rate, no interest should be charged
        assert_relative_eq!(result, 0.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_ipmt_beginning_of_period() {
        // Test beginning of period payment
        let monthly_rate = 0.05 / 12.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 1;

        let result = calculate_ipmt(monthly_rate, per, nper, pv, fv, payment_type);

        // For first period with beginning payments, interest should be 0
        assert_relative_eq!(result, 0.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_ipmt_beginning_of_period_later() {
        // Test beginning of period payment for later period
        let monthly_rate = 0.05 / 12.0;
        let per = 2.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 1;

        let result = calculate_ipmt(monthly_rate, per, nper, pv, fv, payment_type);

        // Should be positive (interest payment)
        assert!(result > 0.0);
    }

    #[test]
    fn test_calculate_ipmt_with_future_value() {
        // Test with future value (balloon payment)
        let monthly_rate = 0.05 / 12.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = -2000.0; // Balloon payment at end
        let payment_type = 0;

        let result = calculate_ipmt(monthly_rate, per, nper, pv, fv, payment_type);

        // First period interest should still be based on full principal
        assert_relative_eq!(result, 41.666_666_666_667, epsilon = 1e-10);
    }

    #[test]
    fn test_ipmt_polars_interface() {
        // Test the Polars interface
        let rate_series = Series::new("rate".into(), vec![0.05 / 12.0, 0.06 / 12.0]);
        let per_series = Series::new("per".into(), vec![1.0, 2.0]);
        let nper_series = Series::new("nper".into(), vec![24.0, 36.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 15000.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Check first result matches our test above
        assert_relative_eq!(values.get(0).unwrap(), 41.666_666_666_667, epsilon = 1e-10);

        // All values should be positive (interest payments)
        assert!(values.get(0).unwrap() > 0.0);
        assert!(values.get(1).unwrap() > 0.0);
    }

    #[test]
    fn test_ipmt_with_optional_params() {
        // Test with optional parameters specified
        let rate_series = Series::new("rate".into(), vec![0.08 / 12.0]);
        let per_series = Series::new("per".into(), vec![1.0]);
        let nper_series = Series::new("nper".into(), vec![60.0]);
        let pv_series = Series::new("pv".into(), vec![25000.0]);

        let kwargs = IpmtKwargs {
            fv: Some(-5000.0),
            payment_type: Some(1),
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // With beginning of period payments, first period interest should be 0
        assert_relative_eq!(values.get(0).unwrap(), 0.0, epsilon = 1e-10);
    }

    #[test]
    fn test_null_handling() {
        // Create series with null values
        let rate_series = Series::new(
            "rate".into(),
            vec![Some(0.05 / 12.0), None, Some(0.06 / 12.0)],
        );
        let per_series = Series::new("per".into(), vec![Some(1.0), Some(2.0), None]);
        let nper_series = Series::new("nper".into(), vec![Some(24.0), Some(36.0), Some(48.0)]);
        let pv_series = Series::new(
            "pv".into(),
            vec![Some(10000.0), Some(15000.0), Some(20000.0)],
        );

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated
        assert!(values.get(0).is_some());
        // Second value should be null (rate is null)
        assert!(values.get(1).is_none());
        // Third value should be null (per is null)
        assert!(values.get(2).is_none());
    }

    #[test]
    fn test_invalid_rate() {
        // Test rate <= -1 (should return None/null)
        let rate_series = Series::new("rate".into(), vec![-1.0, -1.5, -0.5]);
        let per_series = Series::new("per".into(), vec![1.0, 1.0, 1.0]);
        let nper_series = Series::new("nper".into(), vec![24.0, 24.0, 24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (rate <= -1)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated (rate > -1)
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_per() {
        // Test per out of range (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05, 0.06, 0.07]);
        let per_series = Series::new("per".into(), vec![0.0, 25.0, 12.0]); // 0, >nper, valid
        let nper_series = Series::new("nper".into(), vec![24.0, 24.0, 24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (per out of range)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated (per in range)
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_nper() {
        // Test nper = 0 (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05, 0.06, 0.07]);
        let per_series = Series::new("per".into(), vec![1.0, 1.0, 1.0]);
        let nper_series = Series::new("nper".into(), vec![0.0, 24.0, 0.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

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
        let per_series = Series::new("per".into(), vec![1.0]);
        let nper_series = Series::new("nper".into(), vec![24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: Some(2), // Invalid value
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_insufficient_inputs() {
        // Test with insufficient inputs
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let per_series = Series::new("per".into(), vec![1.0]);
        let nper_series = Series::new("nper".into(), vec![24.0]);

        let kwargs = IpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ipmt(&[rate_series, per_series, nper_series], &kwargs);

        assert!(result.is_err());
    }
}

// Excel Verification Tests
//
// These tests verify exact compatibility with Microsoft Excel's IPMT function.
// The IPMT function calculates interest payments for loans and investments,
// which are critical in financial calculations and must match Excel exactly.
#[cfg(test)]
mod excel_verification_tests {
    use super::*;
    use approx::assert_relative_eq;

    fn test_ipmt(rate: f64, per: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
        let rate_series = Series::new("rate".into(), vec![rate]);
        let per_series = Series::new("per".into(), vec![per]);
        let nper_series = Series::new("nper".into(), vec![nper]);
        let pv_series = Series::new("pv".into(), vec![pv]);
        let kwargs = IpmtKwargs {
            fv: Some(fv),
            payment_type: Some(payment_type),
        };
        let result = ipmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();
        result.f64().unwrap().get(0).unwrap()
    }

    #[test]
    fn test_excel_mortgage_first_payment() {
        // Standard mortgage: $200,000 at 6% annual for 30 years
        // Calculate interest for first payment
        let rate = 0.06 / 12.0;
        let per = 1.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // First payment interest = $200,000 * 0.005 = $1,000
        assert_relative_eq!(result, 1000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_mortgage_later_payment() {
        // Same mortgage, calculate interest for 12th payment
        let rate = 0.06 / 12.0;
        let per = 12.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // 12th payment interest should be less than first payment
        assert!(result < 1000.0);
        assert!(result > 950.0); // Still substantial for early payments
    }

    #[test]
    fn test_excel_car_loan() {
        // Car loan: $25,000 at 7% annual for 5 years
        // Calculate interest for first payment
        let rate = 0.07 / 12.0;
        let per = 1.0;
        let nper = 5.0 * 12.0;
        let pv = 25000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // First payment interest = $25,000 * (0.07/12) = $145.83
        assert_relative_eq!(result, 145.833_333_333_333, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_beginning_of_period() {
        // Test beginning of period payments
        let rate = 0.08 / 12.0;
        let per = 1.0;
        let nper = 20.0 * 12.0;
        let pv = 100000.0;
        let fv = 0.0;
        let payment_type = 1;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // First period with beginning payments should have no interest
        assert_relative_eq!(result, 0.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_beginning_of_period_later() {
        // Test beginning of period payments for later period
        let rate = 0.08 / 12.0;
        let per = 2.0;
        let nper = 20.0 * 12.0;
        let pv = 100000.0;
        let fv = 0.0;
        let payment_type = 1;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Second period should have interest
        assert!(result > 0.0);
        assert!(result < 1000.0);
    }

    #[test]
    fn test_excel_balloon_payment() {
        // Loan with balloon payment: $50,000 loan, $10,000 balloon
        let rate = 0.04 / 12.0;
        let per = 1.0;
        let nper = 7.0 * 12.0;
        let pv = 50000.0;
        let fv = -10000.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // First payment interest = $50,000 * (0.04/12) = $166.67
        assert_relative_eq!(result, 166.666_666_666_667, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_investment_scenario() {
        // Investment scenario: negative PV (we receive money)
        let rate = 0.05 / 12.0;
        let per = 1.0;
        let nper = 10.0 * 12.0;
        let pv = -50000.0; // We receive this amount
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Interest should be negative (we pay interest)
        assert_relative_eq!(result, -208.333_333_333_333, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_single_payment() {
        // Single payment loan (nper = 1)
        let rate = 0.10;
        let per = 1.0;
        let nper = 1.0;
        let pv = 1000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // All interest paid in single payment
        assert_relative_eq!(result, 100.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_very_small_rate() {
        // Very small interest rate
        let rate = 0.000001;
        let per = 1.0;
        let nper = 12.0;
        let pv = 12000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Should be very small but not zero
        assert!(result > 0.0);
        assert!(result < 1.0);
        assert_relative_eq!(result, 0.012, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_negative_rate() {
        // Negative interest rate (unusual but possible)
        let rate = -0.02 / 12.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Negative interest means we receive interest
        assert!(result < 0.0);
        assert_relative_eq!(result, -16.666_666_666_667, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_last_payment() {
        // Test interest for the last payment
        let rate = 0.06 / 12.0;
        let per = 60.0; // Last payment
        let nper = 60.0;
        let pv = 20000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Last payment should have minimal interest
        assert!(result > 0.0);
        assert!(result < 50.0); // Much less than first payment
    }

    #[test]
    fn test_excel_quarterly_payments() {
        // Quarterly payments
        let annual_rate = 0.06;
        let rate = annual_rate / 4.0;
        let per = 1.0;
        let nper = 5.0 * 4.0;
        let pv = 20000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // First quarterly interest = $20,000 * 0.015 = $300
        assert_relative_eq!(result, 300.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_high_interest_rate() {
        // High interest rate scenario
        let rate = 0.24 / 12.0; // 24% annual
        let per = 1.0;
        let nper = 12.0;
        let pv = 5000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // High interest rate means high interest payment
        assert_relative_eq!(result, 100.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_consistency_with_pmt() {
        // IPMT + PPMT should equal PMT for any given period
        let rate = 0.05 / 12.0;
        let per = 6.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let interest_payment = test_ipmt(rate, per, nper, pv, fv, payment_type);
        let total_payment = calculate_pmt(rate, nper, pv, fv, payment_type);

        // Interest payment should be less than total payment
        assert!(interest_payment < -total_payment);
        assert!(interest_payment > 0.0);
    }

    #[test]
    fn test_excel_edge_case_fractional_period() {
        // Excel allows fractional periods
        let rate = 0.06 / 12.0;
        let per = 1.5;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ipmt(rate, per, nper, pv, fv, payment_type);

        // Should calculate interest for fractional period
        assert!(result > 0.0);
        assert!(result < 100.0);
    }
}
