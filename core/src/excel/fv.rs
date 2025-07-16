// ABOUTME: Excel FV (Future Value) function implementation for Polars
// ABOUTME: Calculates the future value of an investment based on periodic, constant payments and a constant interest rate

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct FVKwargs {
    pub pv: Option<f64>,
    pub payment_type: Option<i32>,
}

/// Excel FV (Future Value) implementation for Polars
///
/// Calculates the future value of an investment based on periodic, constant payments
/// and a constant interest rate. You can use FV with either periodic, constant payments,
/// or a single lump sum payment.
///
/// The FV function is commonly used in financial analysis to determine how much an
/// investment will be worth in the future, given regular contributions and a fixed
/// interest rate.
///
/// # Arguments
/// * `rate` - The interest rate per period (required)
/// * `nper` - The total number of payment periods (required)
/// * `pmt` - The payment made each period; it cannot change over the life of the annuity (required)
/// * `pv` - The present value, or the lump-sum amount that a series of future payments is worth right now (optional, default 0)
/// * `payment_type` - When payments are due: 0 = end of period, 1 = beginning of period (optional, default 0)
///
/// # Sign Convention
/// * Negative values represent cash outflows (money paid out)
/// * Positive values represent cash inflows (money received)
/// * The result follows the same convention based on the input signs
///
/// # Returns
/// The future value of the investment
///
/// # Errors
/// Returns an error if:
/// * Input series have incompatible lengths
/// * Invalid payment_type is provided (must be 0 or 1)
pub fn fv(inputs: &[Series], kwargs: &FVKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 3 {
        return Err(PolarsError::ComputeError(
            "fv requires at least 3 parameters: rate, nper, and pmt".into(),
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
    let pv = kwargs.pv.unwrap_or(0.0);
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
                    Some(calculate_fv(rate, nper, pmt, pv, payment_type))
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("fv".into()).into_series())
}

/// Calculate the future value for a single set of parameters
///
/// This implements Excel's FV calculation logic exactly, including special handling
/// for the edge case when rate = 0.
///
/// # Excel Formula
/// When rate ≠ 0:
/// For ordinary annuity (type = 0):
/// FV = -pv × (1 + rate)^nper - pmt × [((1 + rate)^nper - 1) / rate]
///
/// For annuity due (type = 1):
/// FV = -pv × (1 + rate)^nper - pmt × (1 + rate) × [((1 + rate)^nper - 1) / rate]
///
/// When rate = 0:
/// FV = -pv - pmt × nper
///
/// The negative signs ensure proper cash flow convention where outflows are negative
/// and inflows are positive.
#[inline]
fn calculate_fv(rate: f64, nper: f64, pmt: f64, pv: f64, payment_type: i32) -> f64 {
    if rate == 0.0 {
        // Special case: when rate is 0, there's no compound interest
        // FV is simply the negative of present value plus all payments
        -pv - pmt * nper
    } else {
        // Standard case: apply compound interest calculations
        let compound_factor = (1.0 + rate).powf(nper);

        // Calculate future value of present value: -pv × (1 + rate)^nper
        let fv_pv = -pv * compound_factor;

        // Calculate future value of payments (annuity): -pmt × [((1 + rate)^nper - 1) / rate]
        let annuity_factor = (compound_factor - 1.0) / rate;
        let fv_annuity = -pmt * annuity_factor;

        // Adjust for payment timing (beginning vs end of period)
        let adjusted_fv_annuity = if payment_type == 1 {
            // For annuity due, multiply by (1 + rate)
            fv_annuity * (1.0 + rate)
        } else {
            fv_annuity
        };

        // Excel's FV formula combines both components
        fv_pv + adjusted_fv_annuity
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    // Test the calculation function directly
    #[test]
    fn test_calculate_fv_normal_case() {
        // Example: $100 monthly payment for 12 months at 1% monthly interest
        let result = calculate_fv(0.01, 12.0, 100.0, 0.0, 0);
        // Expected: approximately -$1268.25
        assert_relative_eq!(result, -1268.250, epsilon = 0.01);
    }

    #[test]
    fn test_calculate_fv_with_present_value() {
        // Example: $100 monthly payment for 12 months at 1% monthly interest, with $500 present value
        let result = calculate_fv(0.01, 12.0, 100.0, 500.0, 0);
        // FV should include both the annuity and compounded present value
        assert_relative_eq!(result, -1831.663, epsilon = 0.01);
    }

    #[test]
    fn test_calculate_fv_zero_rate() {
        // When rate is 0, FV = -(pv + pmt * nper)
        let result = calculate_fv(0.0, 12.0, 100.0, 500.0, 0);
        assert_relative_eq!(result, -1700.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_fv_beginning_of_period() {
        // Payments at beginning of period (type = 1)
        let result_end = calculate_fv(0.01, 12.0, 100.0, 0.0, 0);
        let result_beginning = calculate_fv(0.01, 12.0, 100.0, 0.0, 1);

        // Beginning payments should have higher future value (more negative)
        assert!(result_beginning < result_end);
        assert_relative_eq!(result_beginning, -1280.933, epsilon = 0.01);
    }

    // Test the Polars interface
    #[test]
    fn test_fv_polars_interface() {
        let rate_series = Series::new("rate".into(), vec![0.01, 0.02, 0.0]);
        let nper_series = Series::new("nper".into(), vec![12.0, 24.0, 36.0]);
        let pmt_series = Series::new("pmt".into(), vec![100.0, 200.0, 150.0]);

        let kwargs = FVKwargs {
            pv: Some(0.0),
            payment_type: Some(0),
        };
        let result = fv(&[rate_series, nper_series, pmt_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value: 1% rate, 12 periods, $100 payment
        assert_relative_eq!(values.get(0).unwrap(), -1268.250, epsilon = 0.01);

        // Second value: 2% rate, 24 periods, $200 payment
        assert_relative_eq!(values.get(1).unwrap(), -6084.375, epsilon = 0.01);

        // Third value: 0% rate, 36 periods, $150 payment
        assert_relative_eq!(values.get(2).unwrap(), -5400.0, epsilon = 1e-10);
    }

    #[test]
    fn test_null_handling() {
        let rate_series = Series::new("rate".into(), vec![Some(0.01), None, Some(0.02)]);
        let nper_series = Series::new("nper".into(), vec![Some(12.0), Some(24.0), None]);
        let pmt_series = Series::new("pmt".into(), vec![Some(100.0), Some(200.0), Some(300.0)]);

        let kwargs = FVKwargs {
            pv: None,
            payment_type: None,
        };
        let result = fv(&[rate_series, nper_series, pmt_series], &kwargs).unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated
        assert!(values.get(0).is_some());
        assert_relative_eq!(values.get(0).unwrap(), -1268.250, epsilon = 0.01);

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

        let kwargs = FVKwargs {
            pv: None,
            payment_type: Some(2),
        };
        let result = fv(&[rate_series, nper_series, pmt_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_negative_interest_rate() {
        // FV function should work with negative interest rates
        let result = calculate_fv(-0.01, 12.0, 100.0, 0.0, 0);
        // With negative rate, future value should be less (closer to zero)
        assert!(result > -1200.0);
        assert_relative_eq!(result, -1136.151, epsilon = 0.01);
    }

    #[test]
    fn test_single_period() {
        // Test with nper = 1
        let result = calculate_fv(0.01, 1.0, 100.0, 0.0, 0);
        // FV of single payment = -pmt
        assert_relative_eq!(result, -100.0, epsilon = 0.0001);
    }

    #[test]
    fn test_large_number_of_periods() {
        // Test with large nper (e.g., 30-year investment = 360 months)
        let result = calculate_fv(0.005, 360.0, 1000.0, 0.0, 0);
        // Should converge to a finite value
        assert!(result.is_finite());
        assert_relative_eq!(result, -1004515.043, epsilon = 0.1);
    }

    #[test]
    fn test_insufficient_parameters() {
        let rate_series = Series::new("rate".into(), vec![0.01]);
        let nper_series = Series::new("nper".into(), vec![12.0]);

        let kwargs = FVKwargs {
            pv: None,
            payment_type: None,
        };
        let result = fv(&[rate_series, nper_series], &kwargs);

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

            // Example 1: Basic savings calculation
            // $500 monthly payment, 6% annual rate (6%/12 monthly), 10 years (120 months)
            let result = calculate_fv(0.06 / 12.0, 120.0, 500.0, 0.0, 0);
            assert_relative_eq!(result, -81939.673, epsilon = 0.01);

            // Example 2: Investment with present value
            // $100 monthly, 8% annual (8%/12 monthly), 5 years (60 months), $5,000 PV
            let result = calculate_fv(0.08 / 12.0, 60.0, 100.0, 5000.0, 0);
            assert_relative_eq!(result, -14796.914, epsilon = 0.01);

            // Example 3: Annuity due (payments at beginning)
            // $1000 quarterly, 4% annual (4%/4 quarterly), 5 years (20 quarters)
            let result = calculate_fv(0.04 / 4.0, 20.0, 1000.0, 0.0, 1);
            assert_relative_eq!(result, -22239.194, epsilon = 0.01);
        }

        #[test]
        fn test_excel_edge_cases() {
            // Very small interest rate (approaching 0 but not 0)
            let result1 = calculate_fv(0.0001, 12.0, 100.0, 0.0, 0);
            let result2 = calculate_fv(0.0, 12.0, 100.0, 0.0, 0);
            // Should be very close but not exactly equal
            assert_relative_eq!(result1, result2, epsilon = 0.8);

            // High interest rate
            let result = calculate_fv(0.5, 12.0, 100.0, 0.0, 0);
            // With 50% interest, FV should be much larger
            assert!(result < -10000.0);
            assert_relative_eq!(result, -25749.268, epsilon = 0.1);
        }

        #[test]
        fn test_excel_financial_scenarios() {
            // Retirement savings: $200 monthly, 30 years, 7% annual return
            let monthly_rate = 0.07 / 12.0;
            let months = 30.0 * 12.0;
            let payment = 200.0;

            let result = calculate_fv(monthly_rate, months, payment, 0.0, 0);
            // Should have significant growth over 30 years
            assert_relative_eq!(result, -243994.199, epsilon = 0.1);

            // College savings: $5000 initial, $250 monthly, 18 years, 5% annual
            let monthly_rate_college = 0.05 / 12.0;
            let months_college = 18.0 * 12.0;

            let result = calculate_fv(monthly_rate_college, months_college, 250.0, 5000.0, 0);
            assert_relative_eq!(result, -99575.547, epsilon = 0.1);
        }

        #[test]
        fn test_excel_zero_payment() {
            // Only present value, no periodic payments
            let result = calculate_fv(0.05, 10.0, 0.0, 1000.0, 0);
            // FV = -PV × (1 + rate)^nper
            assert_relative_eq!(result, -1628.895, epsilon = 0.01);
        }

        #[test]
        fn test_excel_mixed_signs() {
            // Negative payment (outflow) with positive present value (inflow)
            let result = calculate_fv(0.01, 12.0, -100.0, 1000.0, 0);
            // With present value compounding faster than negative payments
            assert!(result > 0.0);
            assert_relative_eq!(result, 141.425, epsilon = 0.01);
        }

        #[test]
        fn test_excel_compound_interest_power() {
            // Test the power of compound interest over long periods
            // Small monthly amount over very long period
            let result = calculate_fv(0.08 / 12.0, 480.0, 100.0, 0.0, 0); // 40 years
                                                                          // Should show exponential growth
            assert_relative_eq!(result, -349100.783, epsilon = 1.0);
        }

        #[test]
        fn test_excel_negative_rate_depreciation() {
            // Asset depreciation scenario
            let result = calculate_fv(-0.10 / 12.0, 60.0, 0.0, 10000.0, 0);
            // Asset should depreciate over time
            assert!(result > -10000.0 && result < 0.0);
            assert_relative_eq!(result, -6052.613, epsilon = 0.01);
        }
    }
}
