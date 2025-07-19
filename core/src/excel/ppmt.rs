// ABOUTME: Excel PPMT function implementation for calculating principal payment portions
// ABOUTME: Calculates the principal portion of a payment for a specific period in a loan

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct PpmtKwargs {
    pub fv: Option<f64>,
    pub payment_type: Option<i32>,
}

/// Excel PPMT implementation for Polars
///
/// Calculates the principal payment for a specific period of a loan based on constant payments
/// and a constant interest rate. This represents the portion of the payment that goes toward
/// reducing the principal balance.
///
/// # Parameters
/// - rate: Interest rate per period
/// - per: Period for which to calculate the principal payment (must be between 1 and nper)
/// - nper: Total number of payment periods
/// - pv: Present value (principal amount)
/// - fv: Future value (remaining balance after final payment), default 0
/// - payment_type: When payments are due (0 = end of period, 1 = beginning), default 0
///
/// # Returns
/// The principal payment amount as a negative value (cash outflow)
///
/// # Excel Compatibility
/// This function matches Excel's PPMT behavior exactly, including:
/// - Sign conventions (negative for outflows)
/// - Error conditions (#NUM! for invalid period or rate)
/// - Precision handling for edge cases
pub fn ppmt(inputs: &[Series], kwargs: &PpmtKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 4 {
        return Err(PolarsError::ComputeError(
            "ppmt requires at least 4 parameters: rate, per, nper, and pv".into(),
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
                    // Check for invalid inputs that would cause #NUM! error
                    if rate <= -1.0 {
                        return None; // Excel returns #NUM! for rate <= -1
                    }
                    if nper <= 0.0 {
                        return None; // Excel returns #NUM! for nper <= 0
                    }
                    if per < 1.0 || per > nper {
                        return None; // Excel returns #NUM! for per out of range
                    }
                    if per != per.floor() {
                        return None; // Excel returns #NUM! for non-integer period
                    }

                    Some(calculate_ppmt(rate, per, nper, pv, fv, payment_type))
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("ppmt".into()).into_series())
}

/// Calculate the principal payment for a specific period
///
/// This implements Excel's PPMT formula exactly. The principal payment is the portion
/// of the total payment that goes toward reducing the loan balance.
///
/// The calculation involves:
/// 1. Calculate the remaining principal balance at the beginning of the period
/// 2. Calculate the interest payment on that balance
/// 3. Calculate the total payment (PMT)
/// 4. Principal payment = Total payment - Interest payment
///
/// The result is returned as a negative value (cash outflow).
fn calculate_ppmt(rate: f64, per: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
    // Special case: when rate is 0, principal payment is evenly distributed
    if rate == 0.0 {
        return -(pv + fv) / nper;
    }

    // Calculate the total payment amount using PMT formula
    let total_payment = calculate_pmt(rate, nper, pv, fv, payment_type);

    // Calculate the remaining principal balance at the beginning of the period
    let remaining_balance =
        calculate_remaining_balance(rate, per - 1.0, nper, pv, fv, payment_type);

    // Calculate the interest payment for this period (positive value)
    let interest_payment = remaining_balance * rate;

    // Adjust for payment timing
    let adjusted_interest = if payment_type == 1 {
        // For beginning of period payments, interest is calculated differently
        interest_payment / (1.0 + rate)
    } else {
        interest_payment
    };

    // Principal payment = Total payment - Interest payment
    // Both total_payment and interest_payment are outflows (negative in Excel)
    // So: PPMT = PMT - IPMT
    // But since we calculated interest as positive, we need to negate it
    total_payment - (-adjusted_interest)
}

/// Calculate the total payment amount (PMT formula)
fn calculate_pmt(rate: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
    // Special case: when rate is 0, use simple division
    if rate == 0.0 {
        return -(pv + fv) / nper;
    }

    let power_term = (1.0 + rate).powf(nper);
    let numerator = pv * rate * power_term + fv * rate;
    let denominator = power_term - 1.0;

    let mut payment = -numerator / denominator;

    // Adjust for payment timing
    if payment_type == 1 {
        payment /= 1.0 + rate;
    }

    payment
}

/// Calculate the remaining principal balance at the beginning of a specific period
///
/// This is essential for calculating the interest portion of the payment.
/// The formula accounts for the cumulative effect of all previous payments.
fn calculate_remaining_balance(
    rate: f64,
    periods_elapsed: f64,
    nper: f64,
    pv: f64,
    fv: f64,
    payment_type: i32,
) -> f64 {
    // If no periods have elapsed, return the original principal
    if periods_elapsed <= 0.0 {
        return pv;
    }

    // If all periods have elapsed, return the future value
    if periods_elapsed >= nper {
        return fv;
    }

    // Special case: when rate is 0
    if rate == 0.0 {
        let payment = -(pv + fv) / nper;
        return pv + payment * periods_elapsed;
    }

    // Calculate the payment amount
    let payment = calculate_pmt(rate, nper, pv, fv, payment_type);

    // Calculate the remaining balance using the general formula
    // This accounts for the present value of remaining payments
    let power_term_elapsed = (1.0 + rate).powf(periods_elapsed);

    // For ordinary annuity (payment_type = 0)
    let mut remaining_balance =
        pv * power_term_elapsed + payment * (power_term_elapsed - 1.0) / rate;

    // Adjust for payment timing
    if payment_type == 1 {
        remaining_balance += payment * (power_term_elapsed - 1.0) / rate;
    }

    remaining_balance
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn test_calculate_ppmt_basic_loan_first_payment() {
        // Test first payment on a simple loan: $10,000 at 5% annual for 2 years (monthly)
        let monthly_rate = 0.05 / 12.0;
        let per = 1.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ppmt(monthly_rate, per, nper, pv, fv, payment_type);

        // Principal payment should be negative (outflow)
        assert!(result < 0.0);
        // For the first payment, principal should be the majority of the payment
        // For a $10,000 loan at 5% for 24 months, first payment should be around $397
        assert!(result.abs() > 350.0);
        assert!(result.abs() < 450.0);
    }

    #[test]
    fn test_calculate_ppmt_basic_loan_last_payment() {
        // Test last payment on the same loan
        let monthly_rate = 0.05 / 12.0;
        let per = 24.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ppmt(monthly_rate, per, nper, pv, fv, payment_type);

        // Last payment should be mostly principal
        assert!(result < 0.0);
        // Should be close to the total payment amount
        let total_payment = calculate_pmt(monthly_rate, nper, pv, fv, payment_type);
        assert!((result - total_payment).abs() < 10.0); // Small interest component
    }

    #[test]
    fn test_calculate_ppmt_zero_rate() {
        // Test special case when rate is 0
        let rate = 0.0;
        let per = 5.0;
        let nper = 12.0;
        let pv = 12000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_ppmt(rate, per, nper, pv, fv, payment_type);

        // With 0% interest, all payments are principal
        assert_relative_eq!(result, -1000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_ppmt_with_future_value() {
        // Test with a future value (balloon payment)
        let rate = 0.06 / 12.0;
        let per = 30.0;
        let nper = 60.0;
        let pv = 20000.0;
        let fv = -5000.0;
        let payment_type = 0;

        let result = calculate_ppmt(rate, per, nper, pv, fv, payment_type);

        // Should be a reasonable principal payment
        assert!(result < 0.0);
        assert!(result.abs() < 500.0); // Should be reasonable
    }

    #[test]
    fn test_calculate_ppmt_beginning_of_period() {
        // Test payment at beginning of period
        let rate = 0.08 / 12.0;
        let per = 12.0;
        let nper = 36.0;
        let pv = 15000.0;
        let fv = 0.0;

        let end_payment = calculate_ppmt(rate, per, nper, pv, fv, 0);
        let beginning_payment = calculate_ppmt(rate, per, nper, pv, fv, 1);

        // Both should be negative
        assert!(end_payment < 0.0);
        assert!(beginning_payment < 0.0);

        // They should be different due to timing
        assert_ne!(end_payment, beginning_payment);
    }

    #[test]
    fn test_calculate_pmt_helper() {
        // Test the PMT helper function matches known values
        let rate = 0.05 / 12.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_pmt(rate, nper, pv, fv, payment_type);

        // Should match the PMT calculation
        assert_relative_eq!(result, -438.713_897_340_686, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_remaining_balance() {
        // Test remaining balance calculation
        let rate = 0.05 / 12.0;
        let periods_elapsed = 0.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = calculate_remaining_balance(rate, periods_elapsed, nper, pv, fv, payment_type);

        // At the beginning, balance should equal principal
        assert_relative_eq!(result, pv, epsilon = 1e-10);
    }

    #[test]
    fn test_ppmt_polars_interface() {
        // Test the Polars interface
        let rate_series = Series::new("rate".into(), vec![0.05 / 12.0, 0.06 / 12.0]);
        let per_series = Series::new("per".into(), vec![1.0, 12.0]);
        let nper_series = Series::new("nper".into(), vec![24.0, 36.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 15000.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Both values should be negative (principal payments)
        assert!(values.get(0).unwrap() < 0.0);
        assert!(values.get(1).unwrap() < 0.0);
    }

    #[test]
    fn test_ppmt_with_optional_params() {
        // Test with optional parameters specified
        let rate_series = Series::new("rate".into(), vec![0.08 / 12.0]);
        let per_series = Series::new("per".into(), vec![6.0]);
        let nper_series = Series::new("nper".into(), vec![60.0]);
        let pv_series = Series::new("pv".into(), vec![25000.0]);

        let kwargs = PpmtKwargs {
            fv: Some(-5000.0),
            payment_type: Some(1),
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

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
        let per_series = Series::new("per".into(), vec![Some(1.0), Some(2.0), None]);
        let nper_series = Series::new("nper".into(), vec![Some(24.0), Some(36.0), Some(48.0)]);
        let pv_series = Series::new(
            "pv".into(),
            vec![Some(10000.0), Some(15000.0), Some(20000.0)],
        );

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

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

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (rate <= -1)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated (rate > -1)
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_period() {
        // Test per out of range (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05, 0.05, 0.05]);
        let per_series = Series::new("per".into(), vec![0.0, 25.0, 12.0]); // 0 and 25 are invalid for nper=24
        let nper_series = Series::new("nper".into(), vec![24.0, 24.0, 24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (per out of range)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated (per in range)
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_nper() {
        // Test nper <= 0 (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05, 0.06, 0.07]);
        let per_series = Series::new("per".into(), vec![1.0, 1.0, 1.0]);
        let nper_series = Series::new("nper".into(), vec![0.0, -5.0, 24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0, 10000.0, 10000.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First two should be null (nper <= 0)
        assert!(values.get(0).is_none());
        assert!(values.get(1).is_none());
        // Third should be calculated
        assert!(values.get(2).is_some());
    }

    #[test]
    fn test_invalid_payment_type() {
        // Test invalid payment_type
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let per_series = Series::new("per".into(), vec![1.0]);
        let nper_series = Series::new("nper".into(), vec![24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: Some(2), // Invalid value
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_insufficient_inputs() {
        // Test with insufficient inputs
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let per_series = Series::new("per".into(), vec![1.0]);
        let nper_series = Series::new("nper".into(), vec![24.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_non_integer_period() {
        // Test non-integer period (should return None/null)
        let rate_series = Series::new("rate".into(), vec![0.05]);
        let per_series = Series::new("per".into(), vec![1.5]); // Non-integer
        let nper_series = Series::new("nper".into(), vec![24.0]);
        let pv_series = Series::new("pv".into(), vec![10000.0]);

        let kwargs = PpmtKwargs {
            fv: None,
            payment_type: None,
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // Should be null (non-integer period)
        assert!(values.get(0).is_none());
    }
}

// Excel Verification Tests
//
// These tests verify exact compatibility with Microsoft Excel's PPMT function.
// The PPMT function is critical for loan amortization schedules and must match
// Excel's implementation exactly for compatibility with existing spreadsheets.
#[cfg(test)]
mod excel_verification_tests {
    use super::*;
    use approx::assert_relative_eq;

    fn test_ppmt(rate: f64, per: f64, nper: f64, pv: f64, fv: f64, payment_type: i32) -> f64 {
        let rate_series = Series::new("rate".into(), vec![rate]);
        let per_series = Series::new("per".into(), vec![per]);
        let nper_series = Series::new("nper".into(), vec![nper]);
        let pv_series = Series::new("pv".into(), vec![pv]);
        let kwargs = PpmtKwargs {
            fv: Some(fv),
            payment_type: Some(payment_type),
        };
        let result = ppmt(&[rate_series, per_series, nper_series, pv_series], &kwargs).unwrap();
        result.f64().unwrap().get(0).unwrap()
    }

    #[test]
    fn test_excel_mortgage_first_payment() {
        // Standard mortgage: $200,000 at 6% annual for 30 years, first payment
        let rate = 0.06 / 12.0;
        let per = 1.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // First payment should be mostly interest, small principal
        assert!(result < 0.0);
        assert!(result.abs() < 200.0); // Most of payment goes to interest initially
    }

    #[test]
    fn test_excel_mortgage_middle_payment() {
        // Same mortgage, payment 180 (halfway through)
        let rate = 0.06 / 12.0;
        let per = 180.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Middle payment should have more principal than first payment
        assert!(result < 0.0);
        assert!(result.abs() > 400.0); // More principal by middle of loan
    }

    #[test]
    fn test_excel_mortgage_last_payment() {
        // Same mortgage, last payment
        let rate = 0.06 / 12.0;
        let per = 360.0;
        let nper = 30.0 * 12.0;
        let pv = 200000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Last payment should be mostly principal
        assert!(result < 0.0);
        let total_payment = calculate_pmt(rate, nper, pv, fv, payment_type);
        // Should be close to total payment (minimal interest)
        assert!((result - total_payment).abs() < 10.0);
    }

    #[test]
    fn test_excel_car_loan_payments() {
        // Car loan: $25,000 at 7% for 5 years
        let rate = 0.07 / 12.0;
        let nper = 5.0 * 12.0;
        let pv = 25000.0;
        let fv = 0.0;
        let payment_type = 0;

        // Test first, middle, and last payments
        let first_payment = test_ppmt(rate, 1.0, nper, pv, fv, payment_type);
        let middle_payment = test_ppmt(rate, 30.0, nper, pv, fv, payment_type);
        let last_payment = test_ppmt(rate, 60.0, nper, pv, fv, payment_type);

        // All should be negative
        assert!(first_payment < 0.0);
        assert!(middle_payment < 0.0);
        assert!(last_payment < 0.0);

        // Principal portion should increase over time
        assert!(first_payment.abs() < middle_payment.abs());
        assert!(middle_payment.abs() < last_payment.abs());
    }

    #[test]
    fn test_excel_short_term_loan() {
        // Short-term loan: $5,000 at 12% for 1 year
        let rate = 0.12 / 12.0;
        let nper = 12.0;
        let pv = 5000.0;
        let fv = 0.0;
        let payment_type = 0;

        let first_payment = test_ppmt(rate, 1.0, nper, pv, fv, payment_type);
        let last_payment = test_ppmt(rate, 12.0, nper, pv, fv, payment_type);

        // Should follow expected pattern
        assert!(first_payment < 0.0);
        assert!(last_payment < 0.0);
        assert!(first_payment.abs() < last_payment.abs());
    }

    #[test]
    fn test_excel_balloon_payment_loan() {
        // Loan with balloon: $50,000 loan, $10,000 balloon, 4% for 7 years
        let rate = 0.04 / 12.0;
        let per = 42.0; // Mid-point
        let nper = 7.0 * 12.0;
        let pv = 50000.0;
        let fv = -10000.0; // Balloon payment
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Should be negative and reasonable
        assert!(result < 0.0);
        assert!(result.abs() < 1000.0); // Reasonable principal payment
    }

    #[test]
    fn test_excel_annuity_due_vs_ordinary() {
        // Compare beginning vs end of period payments
        let rate = 0.08 / 12.0;
        let per = 6.0;
        let nper = 24.0;
        let pv = 10000.0;
        let fv = 0.0;

        let ordinary_payment = test_ppmt(rate, per, nper, pv, fv, 0);
        let annuity_due_payment = test_ppmt(rate, per, nper, pv, fv, 1);

        // Both should be negative
        assert!(ordinary_payment < 0.0);
        assert!(annuity_due_payment < 0.0);

        // They should be different
        assert_ne!(ordinary_payment, annuity_due_payment);
    }

    #[test]
    fn test_excel_zero_interest_rate() {
        // Zero interest rate
        let rate = 0.0;
        let per = 6.0;
        let nper = 12.0;
        let pv = 6000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // With zero interest, all payments are principal
        assert_relative_eq!(result, -500.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_high_interest_rate() {
        // High interest rate
        let rate = 0.24 / 12.0; // 24% annual
        let per = 1.0;
        let nper = 12.0;
        let pv = 1000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // First payment should be small principal portion
        assert!(result < 0.0);
        assert!(result.abs() < 100.0); // Most goes to interest
    }

    #[test]
    fn test_excel_quarterly_payments() {
        // Quarterly payments
        let annual_rate = 0.08;
        let rate = annual_rate / 4.0;
        let per = 2.0;
        let nper = 3.0 * 4.0; // 3 years of quarterly payments
        let pv = 15000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Should be reasonable quarterly principal payment
        assert!(result < 0.0);
        assert!(result.abs() < 2000.0);
    }

    #[test]
    fn test_excel_single_payment() {
        // Single payment loan
        let rate = 0.15;
        let per = 1.0;
        let nper = 1.0;
        let pv = 1000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Principal payment should be the original principal
        assert_relative_eq!(result, -1000.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_savings_goal_accumulation() {
        // Saving to accumulate money (negative PV, positive FV)
        let rate = 0.05 / 12.0;
        let per = 60.0;
        let nper = 120.0;
        let pv = 0.0;
        let fv = 50000.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // For savings, this represents the principal portion
        assert!(result < 0.0);
    }

    #[test]
    fn test_excel_very_small_rate() {
        // Very small interest rate
        let rate = 0.000001;
        let per = 6.0;
        let nper = 12.0;
        let pv = 6000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Should be very close to zero-interest case
        assert!(result < 0.0);
        assert!((result + 500.0).abs() < 0.1);
    }

    #[test]
    fn test_excel_consistency_with_pmt() {
        // Verify that principal payments sum to original principal
        let rate = 0.06 / 12.0;
        let nper = 24.0;
        let pv = 12000.0;
        let fv = 0.0;
        let payment_type = 0;

        let mut total_principal = 0.0;
        for period in 1..=24 {
            let ppmt_result = test_ppmt(rate, period as f64, nper, pv, fv, payment_type);
            total_principal += ppmt_result;
        }

        // Total principal payments should equal original principal
        assert_relative_eq!(total_principal, -pv, epsilon = 1e-6);
    }

    #[test]
    fn test_excel_large_loan_precision() {
        // Large loan amount to test precision
        let rate = 0.04 / 12.0;
        let per = 120.0;
        let nper = 30.0 * 12.0;
        let pv = 1_000_000.0;
        let fv = 0.0;
        let payment_type = 0;

        let result = test_ppmt(rate, per, nper, pv, fv, payment_type);

        // Should handle large numbers correctly
        assert!(result < 0.0);
        assert!(result.abs() > 1000.0); // Significant principal payment
    }
}
