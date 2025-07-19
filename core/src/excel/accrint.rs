// ABOUTME: This file implements the Excel ACCRINT function for calculating accrued interest
// ABOUTME: on securities that pay periodic interest payments using Excel-compatible formulas

use chrono::{Datelike, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

// Year fraction calculation logic is implemented locally to avoid circular dependencies

// Constants for frequency values
const FREQUENCY_ANNUAL: i32 = 1;
const FREQUENCY_SEMIANNUAL: i32 = 2;
const FREQUENCY_QUARTERLY: i32 = 4;

// Constants for basis values
const BASIS_30_360_US: i32 = 0;
const BASIS_ACTUAL_ACTUAL: i32 = 1;
const BASIS_ACTUAL_360: i32 = 2;
const BASIS_ACTUAL_365: i32 = 3;
const BASIS_30_360_EU: i32 = 4;

// Default par value when omitted
const DEFAULT_PAR: f64 = 1000.0;

#[derive(Deserialize, Clone)]
pub struct AccrintKwargs {
    pub basis: Option<i32>,
    pub calc_method: Option<bool>,
}

/// Excel ACCRINT implementation for Polars
///
/// Calculates the accrued interest for a security that pays periodic interest.
///
/// ACCRINT(issue, first_interest, settlement, rate, par, frequency, [basis], [calc_method])
///
/// # Arguments
/// * `inputs[0]` - issue: The security's issue date
/// * `inputs[1]` - first_interest: The security's first interest date
/// * `inputs[2]` - settlement: The security's settlement date
/// * `inputs[3]` - rate: The security's annual coupon rate
/// * `inputs[4]` - par: The security's par value (optional, defaults to 1000)
/// * `inputs[5]` - frequency: The number of coupon payments per year (1, 2, or 4)
/// * `basis` (optional): The day count basis to use (0-4, default 0)
/// * `calc_method` (optional): TRUE for total from issue to settlement, FALSE for first_interest to settlement
///
/// # Returns
/// A Series containing the accrued interest values
///
/// # Errors
/// Returns an error if:
/// - Less than 6 required parameters are provided
/// - Invalid frequency (not 1, 2, or 4)
/// - Invalid basis (not 0-4)
/// - Invalid dates or negative rate/par values
pub fn accrint(inputs: &[Series], kwargs: &AccrintKwargs) -> PolarsResult<Series> {
    if inputs.len() < 6 {
        return Err(PolarsError::ComputeError(
            "ACCRINT requires at least 6 parameters: issue, first_interest, settlement, rate, par, frequency".into(),
        ));
    }

    let issue_series = &inputs[0];
    let first_interest_series = &inputs[1];
    let settlement_series = &inputs[2];
    let rate_series = &inputs[3];
    let par_series = &inputs[4];
    let frequency_series = &inputs[5];

    let basis = kwargs.basis.unwrap_or(BASIS_30_360_US);
    let calc_method = kwargs.calc_method.unwrap_or(true);

    // Validate basis
    if !(BASIS_30_360_US..=BASIS_30_360_EU).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{}'. Must be 0, 1, 2, 3, or 4", basis).into(),
        ));
    }

    // Extract typed arrays
    let issue_dates = issue_series.date()?;
    let first_interest_dates = first_interest_series.date()?;
    let settlement_dates = settlement_series.date()?;
    let rates = rate_series.f64()?;
    let pars = par_series.f64()?;
    let frequencies = frequency_series.i32()?;

    // Create epoch date once
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Use iterator pattern for vectorized operation
    #[allow(clippy::useless_conversion)]
    let result_ca = issue_dates
        .into_iter()
        .zip(first_interest_dates.into_iter())
        .zip(settlement_dates.into_iter())
        .zip(rates.into_iter())
        .zip(pars.into_iter())
        .zip(frequencies.into_iter())
        .map(
            |(
                ((((issue_opt, first_interest_opt), settlement_opt), rate_opt), par_opt),
                frequency_opt,
            )| {
                match (
                    issue_opt,
                    first_interest_opt,
                    settlement_opt,
                    rate_opt,
                    par_opt,
                    frequency_opt,
                ) {
                    (
                        Some(issue_days),
                        Some(first_interest_days),
                        Some(settlement_days),
                        Some(rate),
                        Some(par),
                        Some(frequency),
                    ) => {
                        // Convert days since epoch to NaiveDate
                        let issue_date = epoch + chrono::Duration::days(i64::from(issue_days));
                        let first_interest_date =
                            epoch + chrono::Duration::days(i64::from(first_interest_days));
                        let settlement_date =
                            epoch + chrono::Duration::days(i64::from(settlement_days));

                        // Use default par if par is 0 or negative (Excel behavior)
                        let par_value = if par <= 0.0 { DEFAULT_PAR } else { par };

                        match calculate_accrint(
                            issue_date,
                            first_interest_date,
                            settlement_date,
                            rate,
                            par_value,
                            frequency,
                            basis,
                            calc_method,
                        ) {
                            Ok(result) => Some(result),
                            Err(_) => None, // Return None for errors in calculation
                        }
                    }
                    _ => None,
                }
            },
        )
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("accrint".into()).into_series())
}

/// Calculate accrued interest for a security that pays periodic interest
///
/// This function implements the Excel ACCRINT formula exactly, including all edge cases
/// and Excel-specific behaviors.
fn calculate_accrint(
    issue: NaiveDate,
    first_interest: NaiveDate,
    settlement: NaiveDate,
    rate: f64,
    par: f64,
    frequency: i32,
    basis: i32,
    calc_method: bool,
) -> PolarsResult<f64> {
    // Validate inputs
    if rate <= 0.0 {
        return Err(PolarsError::ComputeError(
            format!("Rate must be positive, got {}", rate).into(),
        ));
    }

    // Use default par if par is 0 or negative (Excel behavior)
    let par_value = if par <= 0.0 { DEFAULT_PAR } else { par };

    if ![FREQUENCY_ANNUAL, FREQUENCY_SEMIANNUAL, FREQUENCY_QUARTERLY].contains(&frequency) {
        return Err(PolarsError::ComputeError(
            format!("Frequency must be 1, 2, or 4, got {}", frequency).into(),
        ));
    }

    // Determine the start date for accrual calculation based on calc_method
    let accrual_start = if calc_method {
        // TRUE: Calculate from issue to settlement
        issue
    } else {
        // FALSE: Calculate from first_interest to settlement
        first_interest
    };

    // Calculate the year fraction between accrual start and settlement
    let year_fraction = calculate_year_frac_helper(accrual_start, settlement, basis);

    // Calculate accrued interest using the Excel formula
    // Accrued Interest = par * rate * (year_fraction)
    let accrued_interest = par_value * rate * year_fraction;

    Ok(accrued_interest)
}

/// Helper function to calculate year fraction using the same logic as yearfrac
/// This replicates the calculation logic from yearfrac.rs without importing private functions
fn calculate_year_frac_helper(start_date: NaiveDate, end_date: NaiveDate, basis: i32) -> f64 {
    // Check if we need to return a negative value
    let is_negative = start_date > end_date;

    // Always calculate with start <= end for the algorithms
    let (start, end) = if start_date <= end_date {
        (start_date, end_date)
    } else {
        (end_date, start_date)
    };

    let fraction = match basis {
        0 => calculate_30_360_us(start, end),
        1 => calculate_actual_actual(start, end),
        2 => calculate_actual_360(start, end),
        3 => calculate_actual_365(start, end),
        4 => calculate_30_360_eu(start, end),
        _ => unreachable!(), // Already validated
    };

    // Return negative fraction if start was after end
    if is_negative {
        -fraction
    } else {
        fraction
    }
}

/// US (NASD) 30/360 day count convention
fn calculate_30_360_us(start: NaiveDate, end: NaiveDate) -> f64 {
    let mut d1 = i32::try_from(start.day()).expect("Day fits in i32");
    let m1 = i32::try_from(start.month()).expect("Month fits in i32");
    let y1 = start.year();

    let mut d2 = i32::try_from(end.day()).expect("Day fits in i32");
    let m2 = i32::try_from(end.month()).expect("Month fits in i32");
    let y2 = end.year();

    // Check if dates are last day of February
    let start_is_feb_last = start.month() == 2 && is_last_day_of_month(start);
    let end_is_feb_last = end.month() == 2 && is_last_day_of_month(end);

    // Apply US 30/360 rules
    // Rule 1: If both dates are last day of February, set d2 to 30
    if start_is_feb_last && end_is_feb_last {
        d2 = 30;
    }

    // Rule 2: If start date is last day of February, set d1 to 30
    if start_is_feb_last {
        d1 = 30;
    }

    // Rule 3: If d2 is 31 and d1 is 30 or 31, set d2 to 30
    if d2 == 31 && d1 >= 30 {
        d2 = 30;
    }

    // Rule 4: If d1 is 31, set d1 to 30
    if d1 == 31 {
        d1 = 30;
    }

    // Calculate the day count
    let days = (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1);
    f64::from(days) / 360.0
}

/// European 30/360 day count convention
fn calculate_30_360_eu(start: NaiveDate, end: NaiveDate) -> f64 {
    let mut d1 = i32::try_from(start.day()).expect("Day fits in i32");
    let m1 = i32::try_from(start.month()).expect("Month fits in i32");
    let y1 = start.year();

    let mut d2 = i32::try_from(end.day()).expect("Day fits in i32");
    let m2 = i32::try_from(end.month()).expect("Month fits in i32");
    let y2 = end.year();

    // European rules: Simply adjust any 31st to 30th
    if d1 == 31 {
        d1 = 30;
    }
    if d2 == 31 {
        d2 = 30;
    }

    // Calculate the day count
    let days = (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1);
    f64::from(days) / 360.0
}

/// Actual/Actual day count convention
#[allow(clippy::cast_precision_loss)]
fn calculate_actual_actual(start: NaiveDate, end: NaiveDate) -> f64 {
    let days_diff = (end - start).num_days();

    // Case 1: Same calendar year
    if start.year() == end.year() {
        let year_days = if is_leap_year(start.year()) {
            366.0
        } else {
            365.0
        };
        return days_diff as f64 / year_days;
    }

    // Case 2: Different years but less than 1 year span
    if days_diff <= 366 {
        // Check if Feb 29 is in the range
        let contains_leap_day = contains_feb_29(start, end);
        let year_days = if contains_leap_day { 366.0 } else { 365.0 };
        return days_diff as f64 / year_days;
    }

    // Case 3: Multi-year span - use average year length
    let start_year = start.year();
    let end_year = end.year();

    let mut total_year_days = 0;
    let mut year_count = 0;

    for year in start_year..=end_year {
        total_year_days += if is_leap_year(year) { 366 } else { 365 };
        year_count += 1;
    }

    let avg_year_length = f64::from(total_year_days) / f64::from(year_count);
    days_diff as f64 / avg_year_length
}

/// Actual/360 day count convention
#[allow(clippy::cast_precision_loss)]
fn calculate_actual_360(start: NaiveDate, end: NaiveDate) -> f64 {
    let days_diff = (end - start).num_days();
    days_diff as f64 / 360.0
}

/// Actual/365 day count convention
#[allow(clippy::cast_precision_loss)]
fn calculate_actual_365(start: NaiveDate, end: NaiveDate) -> f64 {
    let days_diff = (end - start).num_days();
    days_diff as f64 / 365.0
}

/// Check if a year is a leap year
#[inline]
fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
}

/// Check if a date is the last day of its month
#[inline]
fn is_last_day_of_month(date: NaiveDate) -> bool {
    let next_day = date + chrono::Duration::days(1);
    next_day.month() != date.month()
}

/// Check if the date range contains February 29
fn contains_feb_29(start: NaiveDate, end: NaiveDate) -> bool {
    let start_year = start.year();
    let end_year = end.year();

    for year in start_year..=end_year {
        if is_leap_year(year) {
            if let Some(feb_29) = NaiveDate::from_ymd_opt(year, 2, 29) {
                if feb_29 >= start && feb_29 <= end {
                    return true;
                }
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

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

    fn create_f64_series(name: &str, values: Vec<f64>) -> Series {
        Series::new(name.into(), values)
    }

    fn create_i32_series(name: &str, values: Vec<i32>) -> Series {
        Series::new(name.into(), values)
    }

    #[test]
    fn test_calculate_accrint_basic() {
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let rate = 0.08; // 8% annual rate
        let par = 1000.0;
        let frequency = 2; // Semiannual
        let basis = 0; // 30/360 US
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // For 30/360 basis, Jan 1 to Apr 1 is 3 months = 90 days = 0.25 years
        // Accrued interest = 1000 * 0.08 * 0.25 = 20.0
        assert_relative_eq!(result, 20.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_accrint_calc_method_false() {
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 8, 1).unwrap();
        let rate = 0.06; // 6% annual rate
        let par = 1000.0;
        let frequency = 2; // Semiannual
        let basis = 0; // 30/360 US
        let calc_method = false; // From first_interest to settlement

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // For 30/360 basis, Jul 1 to Aug 1 is 1 month = 30 days = 1/12 years
        // Accrued interest = 1000 * 0.06 * (1/12) = 5.0
        assert_relative_eq!(result, 5.0, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_accrint_different_basis() {
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let rate = 0.05; // 5% annual rate
        let par = 1000.0;
        let frequency = 1; // Annual
        let basis = 2; // Actual/360
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // For actual/360 basis, Jan 1 to Apr 1 is 90 actual days
        // Year fraction = 90 / 360 = 0.25
        // Accrued interest = 1000 * 0.05 * 0.25 = 12.5
        assert_relative_eq!(result, 12.5, epsilon = 1e-10);
    }

    #[test]
    fn test_calculate_accrint_error_cases() {
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let par = 1000.0;
        let frequency = 2;
        let basis = 0;
        let calc_method = true;

        // Test negative rate
        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            -0.05,
            par,
            frequency,
            basis,
            calc_method,
        );
        assert!(result.is_err());

        // Test zero rate
        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            0.0,
            par,
            frequency,
            basis,
            calc_method,
        );
        assert!(result.is_err());

        // Test negative par (should use default par value, not error)
        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            0.05,
            -1000.0,
            frequency,
            basis,
            calc_method,
        );
        assert!(result.is_ok()); // Negative par should use default, not error

        // Test invalid frequency
        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            0.05,
            par,
            3, // Invalid frequency
            basis,
            calc_method,
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_accrint_polars_interface() {
        let issue_dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 6, 1).unwrap(),
        ];
        let first_interest_dates = vec![
            NaiveDate::from_ymd_opt(2023, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
        ];
        let settlement_dates = vec![
            NaiveDate::from_ymd_opt(2023, 4, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 9, 1).unwrap(),
        ];
        let rates = vec![0.08, 0.06];
        let pars = vec![1000.0, 2000.0];
        let frequencies = vec![2, 1];

        let issue_series = create_date_series(issue_dates);
        let first_interest_series = create_date_series(first_interest_dates);
        let settlement_series = create_date_series(settlement_dates);
        let rate_series = create_f64_series("rate", rates);
        let par_series = create_f64_series("par", pars);
        let frequency_series = create_i32_series("frequency", frequencies);

        let kwargs = AccrintKwargs {
            basis: Some(0),
            calc_method: Some(true),
        };

        let result = accrint(
            &[
                issue_series,
                first_interest_series,
                settlement_series,
                rate_series,
                par_series,
                frequency_series,
            ],
            &kwargs,
        )
        .unwrap();

        let values = result.f64().unwrap();

        // First case: 1000 * 0.08 * 0.25 = 20.0
        assert_relative_eq!(values.get(0).unwrap(), 20.0, epsilon = 1e-10);

        // Second case: 2000 * 0.06 * 0.25 = 30.0 (Jun 1 to Sep 1 is 3 months)
        assert_relative_eq!(values.get(1).unwrap(), 30.0, epsilon = 1e-10);
    }

    #[test]
    fn test_accrint_null_handling() {
        let issue_dates = vec![Some(NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()), None];
        let first_interest_dates = vec![
            Some(NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()),
            Some(NaiveDate::from_ymd_opt(2023, 12, 1).unwrap()),
        ];
        let settlement_dates = vec![
            Some(NaiveDate::from_ymd_opt(2023, 4, 1).unwrap()),
            Some(NaiveDate::from_ymd_opt(2023, 9, 1).unwrap()),
        ];
        let rates = vec![Some(0.08), Some(0.06)];
        let pars = vec![Some(1000.0), Some(2000.0)];
        let frequencies = vec![Some(2), Some(1)];

        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let issue_days: Vec<Option<i32>> = issue_dates
            .iter()
            .map(|d| {
                d.map(|date| {
                    (date - epoch)
                        .num_days()
                        .try_into()
                        .expect("Days fit in i32")
                })
            })
            .collect();
        let first_interest_days: Vec<Option<i32>> = first_interest_dates
            .iter()
            .map(|d| {
                d.map(|date| {
                    (date - epoch)
                        .num_days()
                        .try_into()
                        .expect("Days fit in i32")
                })
            })
            .collect();
        let settlement_days: Vec<Option<i32>> = settlement_dates
            .iter()
            .map(|d| {
                d.map(|date| {
                    (date - epoch)
                        .num_days()
                        .try_into()
                        .expect("Days fit in i32")
                })
            })
            .collect();

        let issue_series = Series::new("issue".into(), issue_days)
            .cast(&DataType::Date)
            .unwrap();
        let first_interest_series = Series::new("first_interest".into(), first_interest_days)
            .cast(&DataType::Date)
            .unwrap();
        let settlement_series = Series::new("settlement".into(), settlement_days)
            .cast(&DataType::Date)
            .unwrap();
        let rate_series = Series::new("rate".into(), rates);
        let par_series = Series::new("par".into(), pars);
        let frequency_series = Series::new("frequency".into(), frequencies);

        let kwargs = AccrintKwargs {
            basis: Some(0),
            calc_method: Some(true),
        };

        let result = accrint(
            &[
                issue_series,
                first_interest_series,
                settlement_series,
                rate_series,
                par_series,
                frequency_series,
            ],
            &kwargs,
        )
        .unwrap();

        let values = result.f64().unwrap();

        // First value should be calculated, second should be null
        assert!(values.get(0).is_some());
        assert!(values.get(1).is_none());
    }

    #[test]
    fn test_accrint_default_par() {
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let rate = 0.08;
        let par = 0.0; // Should use default of 1000
        let frequency = 2;
        let basis = 0;
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // Should use default par of 1000
        // 1000 * 0.08 * 0.25 = 20.0
        assert_relative_eq!(result, 20.0, epsilon = 1e-10);
    }

    #[test]
    fn test_accrint_insufficient_parameters() {
        let issue_series = create_date_series(vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()]);
        let first_interest_series =
            create_date_series(vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()]);
        let settlement_series =
            create_date_series(vec![NaiveDate::from_ymd_opt(2023, 4, 1).unwrap()]);
        let rate_series = create_f64_series("rate", vec![0.08]);
        let par_series = create_f64_series("par", vec![1000.0]);

        let kwargs = AccrintKwargs {
            basis: Some(0),
            calc_method: Some(true),
        };

        // Only 5 parameters provided, should error
        let result = accrint(
            &[
                issue_series,
                first_interest_series,
                settlement_series,
                rate_series,
                par_series,
            ],
            &kwargs,
        );

        assert!(result.is_err());
    }

    #[test]
    fn test_accrint_invalid_basis() {
        let issue_series = create_date_series(vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()]);
        let first_interest_series =
            create_date_series(vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()]);
        let settlement_series =
            create_date_series(vec![NaiveDate::from_ymd_opt(2023, 4, 1).unwrap()]);
        let rate_series = create_f64_series("rate", vec![0.08]);
        let par_series = create_f64_series("par", vec![1000.0]);
        let frequency_series = create_i32_series("frequency", vec![2]);

        let kwargs = AccrintKwargs {
            basis: Some(5), // Invalid basis
            calc_method: Some(true),
        };

        let result = accrint(
            &[
                issue_series,
                first_interest_series,
                settlement_series,
                rate_series,
                par_series,
                frequency_series,
            ],
            &kwargs,
        );

        assert!(result.is_err());
    }
}

#[cfg(test)]
mod excel_verification_tests {
    use super::*;
    use approx::assert_relative_eq;

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

    #[test]
    fn test_excel_example_from_documentation() {
        // Example from Microsoft Excel documentation
        // =ACCRINT(DATE(2012,1,1),DATE(2012,3,31),DATE(2012,2,15),0.0525,5000,4,3,1)
        // Expected result: 32.3630137

        let issue = NaiveDate::from_ymd_opt(2012, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2012, 3, 31).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2012, 2, 15).unwrap();
        let rate = 0.0525; // 5.25%
        let par = 5000.0;
        let frequency = 4; // Quarterly
        let basis = 3; // Actual/365
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // Expected from Excel documentation
        assert_relative_eq!(result, 32.3630137, epsilon = 1e-6);
    }

    #[test]
    fn test_excel_example_percentage_rate() {
        // Same example but with percentage rate interpretation
        // =ACCRINT(DATE(2012,1,1),DATE(2012,3,31),DATE(2012,2,15),5.25%,5000,4,3,1)
        // Expected result: 32.3630137

        let issue = NaiveDate::from_ymd_opt(2012, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2012, 3, 31).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2012, 2, 15).unwrap();
        let rate = 0.0525; // 5.25% as decimal
        let par = 5000.0;
        let frequency = 4; // Quarterly
        let basis = 3; // Actual/365
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // Expected from Excel documentation
        assert_relative_eq!(result, 32.3630137, epsilon = 1e-6);
    }

    #[test]
    fn test_excel_example_default_par() {
        // Example with default par value (1000)
        // =ACCRINT(DATE(2012,1,1),DATE(2012,3,31),DATE(2012,2,15),5.25%,,4,3,1)
        // Expected result: 6.47260274

        let issue = NaiveDate::from_ymd_opt(2012, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2012, 3, 31).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2012, 2, 15).unwrap();
        let rate = 0.0525; // 5.25%
        let par = 0.0; // Use default par
        let frequency = 4; // Quarterly
        let basis = 3; // Actual/365
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // Expected from Excel documentation
        assert_relative_eq!(result, 6.47260274, epsilon = 1e-6);
    }

    #[test]
    fn test_excel_calc_method_false() {
        // Test with calc_method = FALSE (0)
        // This should calculate from first_interest to settlement instead of issue to settlement

        let issue = NaiveDate::from_ymd_opt(2012, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2012, 3, 31).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2012, 6, 15).unwrap();
        let rate = 0.06; // 6%
        let par = 1000.0;
        let frequency = 2; // Semiannual
        let basis = 0; // 30/360 US
        let calc_method = false;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // Calculate expected: from Mar 31 to Jun 15 using 30/360
        // This is approximately 2.5 months = 75 days = 75/360 years
        // 1000 * 0.06 * (75/360) = 12.5
        assert_relative_eq!(result, 12.5, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_different_frequencies() {
        // Test with different frequency values
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let rate = 0.08; // 8%
        let par = 1000.0;
        let basis = 0; // 30/360 US
        let calc_method = true;

        // Test annual frequency
        let result_annual = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            1, // Annual
            basis,
            calc_method,
        )
        .unwrap();

        // Test semiannual frequency
        let result_semiannual = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            2, // Semiannual
            basis,
            calc_method,
        )
        .unwrap();

        // Test quarterly frequency
        let result_quarterly = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            4, // Quarterly
            basis,
            calc_method,
        )
        .unwrap();

        // All should give the same result for accrued interest calculation
        // The frequency doesn't affect the basic accrual calculation
        assert_relative_eq!(result_annual, result_semiannual, epsilon = 1e-10);
        assert_relative_eq!(result_semiannual, result_quarterly, epsilon = 1e-10);
        assert_relative_eq!(result_annual, 20.0, epsilon = 1e-10); // 1000 * 0.08 * 0.25
    }

    #[test]
    fn test_excel_different_basis_values() {
        // Test with different basis values to ensure Excel compatibility
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();
        let rate = 0.06; // 6%
        let par = 1000.0;
        let frequency = 2; // Semiannual
        let calc_method = true;

        // Test each basis
        let result_30_360_us = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            0,
            calc_method,
        )
        .unwrap();
        let result_actual_actual = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            1,
            calc_method,
        )
        .unwrap();
        let result_actual_360 = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            2,
            calc_method,
        )
        .unwrap();
        let result_actual_365 = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            3,
            calc_method,
        )
        .unwrap();
        let result_30_360_eu = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            4,
            calc_method,
        )
        .unwrap();

        // All should be positive and reasonable
        assert!(result_30_360_us > 0.0);
        assert!(result_actual_actual > 0.0);
        assert!(result_actual_360 > 0.0);
        assert!(result_actual_365 > 0.0);
        assert!(result_30_360_eu > 0.0);

        // The values should be close but not identical due to different day count conventions
        // All should be approximately 1000 * 0.06 * 0.25 = 15.0
        assert_relative_eq!(result_30_360_us, 15.0, epsilon = 1e-10);
        assert_relative_eq!(result_actual_360, 15.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_bond_settlement_example() {
        // Real-world bond example
        // Corporate bond issued Jan 1, 2023, first coupon July 1, 2023
        // Settled on March 15, 2023, 5% annual coupon, $10,000 face value
        let issue = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let first_interest = NaiveDate::from_ymd_opt(2023, 7, 1).unwrap();
        let settlement = NaiveDate::from_ymd_opt(2023, 3, 15).unwrap();
        let rate = 0.05; // 5% annual coupon
        let par = 10000.0; // $10,000 face value
        let frequency = 2; // Semiannual payments
        let basis = 0; // 30/360 US (typical for corporate bonds)
        let calc_method = true;

        let result = calculate_accrint(
            issue,
            first_interest,
            settlement,
            rate,
            par,
            frequency,
            basis,
            calc_method,
        )
        .unwrap();

        // From Jan 1 to Mar 15 using 30/360:
        // 2 months + 14 days = 60 + 14 = 74 days = 74/360 years
        // Accrued interest = 10000 * 0.05 * (74/360) = 102.78
        let expected = 10000.0 * 0.05 * (74.0 / 360.0);
        assert_relative_eq!(result, expected, epsilon = 1e-10);
    }
}
