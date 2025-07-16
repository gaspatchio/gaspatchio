// ABOUTME: Excel PV (Present Value) function implementation for Polars
// ABOUTME: Calculates the present value of an investment based on periodic, constant payments and a constant interest rate

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct PVKwargs {
    pub fv: Option<f64>,
    pub payment_type: Option<i32>,
}

/// Excel PV (Present Value) implementation for Polars
///
/// Calculates the present value of an investment based on a series of future payments
/// and/or a future value, assuming a constant interest rate.
///
/// The PV function is commonly used in financial analysis to determine how much a series
/// of future payments is worth in today's dollars, accounting for the time value of money.
///
/// # Arguments
/// * `rate` - The interest rate per period (required)
/// * `nper` - The total number of payment periods (required)  
/// * `pmt` - The payment made each period; it cannot change over the life of the investment (required)
/// * `fv` - The future value, or cash balance after the last payment (optional, default 0)
/// * `payment_type` - When payments are due: 0 = end of period, 1 = beginning of period (optional, default 0)
///
/// # Sign Convention
/// * Positive values represent cash inflows (money received)
/// * Negative values represent cash outflows (money paid out)
/// * The result follows the same convention based on the input signs
///
/// # Returns
/// The present value of the investment
///
/// # Errors
/// Returns an error if:
/// * Input series have incompatible lengths
/// * Invalid payment_type is provided (must be 0 or 1)
pub fn pv(inputs: &[Series], kwargs: &PVKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 3 {
        return Err(PolarsError::ComputeError(
            "pv requires at least 3 parameters: rate, nper, and pmt".into(),
        ));
    }

    // Extract input series
    let rate_series = &inputs[0];
    let nper_series = &inputs[1];
    let pmt_series = &inputs[2];

    // Extract typed arrays
    let rate_array = rate_series.f64()?;
    let nper_array = nper_series.f64()?;
    let pmt_array = pmt_series.f64()?;

    // Process optional parameters
    let fv = kwargs.fv.unwrap_or(0.0);
    let payment_type = kwargs.payment_type.unwrap_or(0);

    // Validate payment_type
    if payment_type != 0 && payment_type != 1 {
        return Err(PolarsError::ComputeError(
            format!("Invalid payment_type '{payment_type}'. Must be 0 or 1").into(),
        ));
    }

    // Use iterator pattern for better performance and Polars integration
    #[allow(clippy::useless_conversion)]
    let result_ca = rate_array
        .into_iter()
        .zip(nper_array.into_iter())
        .zip(pmt_array.into_iter())
        .map(|((rate_opt, nper_opt), pmt_opt)| {
            match (rate_opt, nper_opt, pmt_opt) {
                (Some(rate), Some(nper), Some(pmt)) => {
                    Some(calculate_pv(rate, nper, pmt, fv, payment_type))
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("pv".into()).into_series())
}

/// Calculate the present value for a single set of parameters
///
/// This implements Excel's PV calculation logic exactly, including special handling
/// for the edge case when rate = 0.
///
/// # Excel Formula
/// When rate ≠ 0:
/// PV = -[pmt × (1 + rate × type) × ((1 - (1 + rate)^(-nper)) / rate) + fv × (1 + rate)^(-nper)]
///
/// When rate = 0:
/// PV = -(pmt × nper + fv)
///
/// The negative sign ensures proper cash flow convention where outflows are negative
/// and inflows are positive.
#[inline]
fn calculate_pv(rate: f64, nper: f64, pmt: f64, fv: f64, payment_type: i32) -> f64 {
    if rate == 0.0 {
        // Special case: when rate is 0, there's no time value of money
        // PV is simply the sum of all payments plus future value
        -(pmt * nper + fv)
    } else {
        // Standard case: apply time value of money calculations
        let type_factor = if payment_type == 1 { 1.0 + rate } else { 1.0 };

        // Calculate present value of payments (annuity)
        let pv_annuity = pmt * type_factor * ((1.0 - (1.0 + rate).powf(-nper)) / rate);

        // Calculate present value of future value
        let pv_fv = fv * (1.0 + rate).powf(-nper);

        // Return negative to match Excel's sign convention
        -(pv_annuity + pv_fv)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    // Test the calculation function directly
    #[test]
    fn test_calculate_pv_normal_case() {
        // Example: $100 monthly payment for 12 months at 1% monthly interest
        let result = calculate_pv(0.01, 12.0, 100.0, 0.0, 0);
        // Expected: approximately -$1125.51
        assert_relative_eq!(result, -1125.508, epsilon = 0.01);
    }

    #[test]
    fn test_calculate_pv_with_future_value() {
        // Example: $100 monthly payment for 12 months at 1% monthly interest, with $500 future value
        let result = calculate_pv(0.01, 12.0, 100.0, 500.0, 0);
        // PV should include both the annuity and discounted future value
        assert_relative_eq!(result, -1569.232, epsilon = 0.01);
    }

    #[test]
    fn test_calculate_pv_zero_rate() {
        // When rate is 0, PV = -(pmt * nper + fv)
        let result = calculate_pv(0.0, 12.0, 100.0, 500.0, 0);
        assert_relative_eq!(result, -1700.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_pv_beginning_of_period() {
        // Payments at beginning of period (type = 1)
        let result_end = calculate_pv(0.01, 12.0, 100.0, 0.0, 0);
        let result_beginning = calculate_pv(0.01, 12.0, 100.0, 0.0, 1);

        // Beginning payments should have higher present value (more negative because we're receiving more value)
        assert!(result_beginning < result_end);
        assert_relative_eq!(result_beginning, -1136.763, epsilon = 0.01);
    }

    // Test the Polars interface
    #[test]
    fn test_pv_polars_interface() {
        let rate_series = Series::new("rate".into(), vec![0.01, 0.02, 0.0]);
        let nper_series = Series::new("nper".into(), vec![12.0, 24.0, 36.0]);
        let pmt_series = Series::new("pmt".into(), vec![100.0, 200.0, 150.0]);

        let kwargs = PVKwargs {
            fv: Some(0.0),
            payment_type: Some(0),
        };
        let result = pv(&[rate_series, nper_series, pmt_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value: 1% rate, 12 periods, $100 payment
        assert_relative_eq!(values.get(0).unwrap(), -1125.508, epsilon = 0.01);

        // Second value: 2% rate, 24 periods, $200 payment
        assert_relative_eq!(values.get(1).unwrap(), -3782.785, epsilon = 0.01);

        // Third value: 0% rate, 36 periods, $150 payment
        assert_relative_eq!(values.get(2).unwrap(), -5400.0, epsilon = 1e-10);
    }

    #[test]
    fn test_null_handling() {
        let rate_series = Series::new("rate".into(), vec![Some(0.01), None, Some(0.02)]);
        let nper_series = Series::new("nper".into(), vec![Some(12.0), Some(24.0), None]);
        let pmt_series = Series::new("pmt".into(), vec![Some(100.0), Some(200.0), Some(300.0)]);

        let kwargs = PVKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pv(&[rate_series, nper_series, pmt_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated
        assert!(values.get(0).is_some());
        assert_relative_eq!(values.get(0).unwrap(), -1125.508, epsilon = 0.01);

        // Second value should be null (rate is null)
        assert!(values.get(1).is_none());

        // Third value should be null (nper is null)
        assert!(values.get(2).is_none());
    }

    #[test]
    fn test_invalid_payment_type() {
        let rate_series = Series::new("rate".into(), vec![0.01]);
        let nper_series = Series::new("nper".into(), vec![12.0]);
        let pmt_series = Series::new("pmt".into(), vec![100.0]);

        let kwargs = PVKwargs {
            fv: None,
            payment_type: Some(2),
        };
        let result = pv(&[rate_series, nper_series, pmt_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_negative_interest_rate() {
        // PV function should work with negative interest rates
        let result = calculate_pv(-0.01, 12.0, 100.0, 0.0, 0);
        // With negative rate, present value should be more negative (lower)
        assert!(result < -1200.0);
        assert_relative_eq!(result, -1281.781, epsilon = 0.01);
    }

    #[test]
    fn test_single_period() {
        // Test with nper = 1
        let result = calculate_pv(0.01, 1.0, 100.0, 0.0, 0);
        // PV of single payment = -pmt / (1 + rate)
        assert_relative_eq!(result, -99.0099, epsilon = 0.0001);
    }

    #[test]
    fn test_large_number_of_periods() {
        // Test with large nper (e.g., 30-year mortgage = 360 months)
        let result = calculate_pv(0.005, 360.0, 1000.0, 0.0, 0);
        // Should converge to a finite value
        assert!(result.is_finite());
        assert_relative_eq!(result, -166791.614, epsilon = 0.1);
    }

    #[test]
    fn test_insufficient_parameters() {
        let rate_series = Series::new("rate".into(), vec![0.01]);
        let nper_series = Series::new("nper".into(), vec![12.0]);

        let kwargs = PVKwargs {
            fv: None,
            payment_type: None,
        };
        let result = pv(&[rate_series, nper_series], &kwargs);

        assert!(result.is_err());
    }

    // Excel compatibility tests
    #[cfg(test)]
    mod excel_verification_tests {
        use super::*;
        use approx::assert_relative_eq;

        #[test]
        fn test_excel_known_values() {
            // Test against known Excel outputs

            // Example 1: Basic loan calculation
            // $500 monthly payment, 5% annual rate (5%/12 monthly), 60 months
            let result = calculate_pv(0.05 / 12.0, 60.0, 500.0, 0.0, 0);
            assert_relative_eq!(result, -26495.353, epsilon = 0.01);

            // Example 2: Investment with future value
            // $100 monthly, 8% annual (8%/12 monthly), 120 months, $10,000 FV
            let result = calculate_pv(0.08 / 12.0, 120.0, 100.0, 10000.0, 0);
            assert_relative_eq!(result, -12747.383, epsilon = 0.01);

            // Example 3: Annuity due (payments at beginning)
            // $1000 quarterly, 6% annual (6%/4 quarterly), 20 quarters
            let result = calculate_pv(0.06 / 4.0, 20.0, 1000.0, 0.0, 1);
            assert_relative_eq!(result, -17426.168, epsilon = 0.01);
        }

        #[test]
        fn test_excel_edge_cases() {
            // Very small interest rate (approaching 0 but not 0)
            let result1 = calculate_pv(0.0001, 12.0, 100.0, 0.0, 0);
            let result2 = calculate_pv(0.0, 12.0, 100.0, 0.0, 0);
            // Should be very close but not exactly equal (within 0.8)
            assert_relative_eq!(result1, result2, epsilon = 0.8);

            // High interest rate
            let result = calculate_pv(0.5, 12.0, 100.0, 0.0, 0);
            // With 50% interest, PV should be much smaller
            assert!(result > -200.0);
            assert_relative_eq!(result, -198.459, epsilon = 0.01);
        }

        #[test]
        fn test_excel_financial_scenarios() {
            // Mortgage calculation: $200,000 loan, 30 years, 4% annual
            // This calculates the present value of payments needed
            let monthly_rate = 0.04 / 12.0;
            let months = 30.0 * 12.0;
            let payment = 954.83; // Known monthly payment for this loan

            let result = calculate_pv(monthly_rate, months, payment, 0.0, 0);
            // Should approximately equal the loan amount
            assert_relative_eq!(result, -200000.0, epsilon = 1.0);

            // Bond pricing: $1000 face value, 5% coupon, 10 years, 6% yield
            let coupon_payment = 50.0; // Annual coupon
            let face_value = 1000.0;
            let yield_rate = 0.06;
            let years = 10.0;

            let result = calculate_pv(yield_rate, years, coupon_payment, face_value, 0);
            // Bond should trade at discount when yield > coupon
            assert!(result > -1000.0);
            assert_relative_eq!(result, -926.399, epsilon = 0.01);
        }

        #[test]
        fn test_excel_zero_payment() {
            // Only future value, no periodic payments
            let result = calculate_pv(0.05, 10.0, 0.0, 1000.0, 0);
            // PV = -FV / (1 + rate)^nper
            assert_relative_eq!(result, -613.913, epsilon = 0.01);
        }

        #[test]
        fn test_excel_mixed_signs() {
            // Negative payment (outflow) with positive future value (inflow)
            let result = calculate_pv(0.01, 12.0, -100.0, 1000.0, 0);
            // Should partially offset
            assert!(result < 1000.0 && result > 0.0);
            assert_relative_eq!(result, 238.059, epsilon = 0.01);
        }
    }
}
