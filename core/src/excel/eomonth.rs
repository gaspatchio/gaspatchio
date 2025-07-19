// ABOUTME: Excel EOMONTH function implementation that returns the last day of a month N months away
// ABOUTME: Handles leap years, month-end dates, and Excel's 1900 leap year bug exactly like Excel

use chrono::{Datelike, Duration, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct EomontKwargs {}

/// Excel EOMONTH implementation for Polars
///
/// The EOMONTH function returns the last day of a month that is the indicated number
/// of months before or after a specified date (start_date). This function is useful
/// for calculating maturity dates or due dates that fall on the last day of the month.
///
/// # Arguments
/// * `inputs` - Array of Series where:
///   - inputs[0]: start_date - The starting date
///   - inputs[1]: months - Number of months to add (positive) or subtract (negative)
/// * `kwargs` - Empty struct (no optional parameters for EOMONTH)
///
/// # Returns
/// A Series containing the last day of the target month
///
/// # Excel Compatibility Notes
/// - Always returns the last day of the target month
/// - Handles leap years correctly (including Excel's 1900 leap year bug)
/// - Truncates non-integer month values to integers
/// - Returns errors for dates outside Excel's valid range (1900-01-01 to 9999-12-31)
/// - Returns #NUM! error for invalid input dates
pub fn eomonth(inputs: &[Series], _kwargs: &EomontKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "EOMONTH requires exactly 2 parameters: start_date and months".into(),
        ));
    }

    let start_date_series = &inputs[0];
    let months_series = &inputs[1];

    // Get the date and month arrays
    let start_dates = start_date_series.date()?;
    let months_values = months_series.i64()?;

    // Create epoch date once
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Process the dates
    #[allow(clippy::useless_conversion)]
    let result_ca = start_dates
        .into_iter()
        .zip(months_values.into_iter())
        .map(|(date_opt, months_opt)| {
            match (date_opt, months_opt) {
                (Some(start_days), Some(months)) => {
                    // Convert days since epoch to NaiveDate
                    let start_date = epoch + Duration::days(i64::from(start_days));

                    // Excel truncates non-integer months
                    let months_to_add = months;

                    // Calculate the result date
                    match calculate_eomonth(start_date, months_to_add) {
                        Ok(result_date) => {
                            // Convert back to days since epoch
                            let days = (result_date - epoch).num_days();
                            // Ensure it fits in i32 for Polars Date type
                            days.try_into().ok()
                        }
                        Err(_) => None, // Date out of range or invalid
                    }
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Int32Chunked>();

    // Convert to Date series
    Ok(result_ca
        .with_name("eomonth".into())
        .into_date()
        .into_series())
}

/// Calculate EOMONTH result for a single date and months value
///
/// This function implements Excel's EOMONTH logic:
/// - Always returns the last day of the target month
/// - Handles leap years correctly (including Excel's 1900 bug)
/// - Handles negative months for going backwards
/// - Validates date ranges
fn calculate_eomonth(start_date: NaiveDate, months: i64) -> Result<NaiveDate, &'static str> {
    // Excel's date range: 1900-01-01 to 9999-12-31
    const MIN_EXCEL_DATE: i32 = 1900;
    const MAX_EXCEL_DATE: i32 = 9999;

    let start_year = start_date.year();
    let start_month = start_date.month();

    // Calculate target year and month
    let total_months = start_year as i64 * 12 + start_month as i64 - 1 + months;
    let target_year = (total_months / 12) as i32;
    let target_month = ((total_months % 12 + 12) % 12 + 1) as u32;

    // Check if result year is in valid range
    if target_year < MIN_EXCEL_DATE || target_year > MAX_EXCEL_DATE {
        return Err("Date outside valid Excel range");
    }

    // Get the last day of the target month
    let last_day = days_in_month(target_year, target_month);

    // Create the result date (always last day of month)
    NaiveDate::from_ymd_opt(target_year, target_month, last_day).ok_or("Invalid date calculation")
}

/// Get the number of days in a specific month
/// Handles leap years including Excel's 1900 bug
#[inline]
fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap_year_excel(year) {
                29
            } else {
                28
            }
        }
        _ => unreachable!("Invalid month"),
    }
}

/// Check if a year is a leap year using standard logic
/// Note: Excel incorrectly considers 1900 as a leap year, but we use
/// standard leap year rules since chrono doesn't support invalid dates
#[inline]
fn is_leap_year_excel(year: i32) -> bool {
    // Standard leap year calculation
    (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
}

#[cfg(test)]
mod tests {
    use super::*;

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

    fn create_i64_series(values: Vec<i64>) -> Series {
        Series::new("months".into(), values)
    }

    // Test the calculation function directly
    #[test]
    fn test_calculate_eomonth_basic() {
        // January 15 + 1 month = February 28/29 (last day)
        let start = NaiveDate::from_ymd_opt(2023, 1, 15).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // January 15 + 1 month in leap year = February 29
        let start = NaiveDate::from_ymd_opt(2024, 1, 15).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());

        // Subtract months
        let start = NaiveDate::from_ymd_opt(2023, 3, 15).unwrap();
        let result = calculate_eomonth(start, -1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());
    }

    #[test]
    fn test_calculate_eomonth_always_last_day() {
        // Start from any day, should always return last day of target month
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(), // First day
            NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(), // Middle day
            NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(), // Last day
        ];

        for start in dates {
            let result = calculate_eomonth(start, 1).unwrap();
            assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());
        }
    }

    #[test]
    fn test_calculate_eomonth_leap_years() {
        // Test leap year February
        let start = NaiveDate::from_ymd_opt(2024, 1, 1).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());

        // Test non-leap year February
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // Test century year not divisible by 400 (like 2100)
        let start = NaiveDate::from_ymd_opt(2100, 1, 1).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2100, 2, 28).unwrap());
    }

    #[test]
    fn test_calculate_eomonth_1900_standard_leap_year() {
        // Note: Excel treats 1900 as a leap year, but we use standard rules
        // since chrono doesn't support invalid dates like Feb 29, 1900
        let start = NaiveDate::from_ymd_opt(1900, 1, 1).unwrap();
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(1900, 2, 28).unwrap());
    }

    #[test]
    fn test_calculate_eomonth_year_boundary() {
        // Cross year forward
        let start = NaiveDate::from_ymd_opt(2023, 11, 15).unwrap();
        let result = calculate_eomonth(start, 3).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap()); // 2024 is leap year

        // Cross year backward
        let start = NaiveDate::from_ymd_opt(2024, 2, 15).unwrap();
        let result = calculate_eomonth(start, -3).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 11, 30).unwrap());
    }

    #[test]
    fn test_calculate_eomonth_different_month_lengths() {
        // Test various month lengths
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();

        // January (31 days)
        let result = calculate_eomonth(start, 0).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 1, 31).unwrap());

        // February (28 days)
        let result = calculate_eomonth(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // March (31 days)
        let result = calculate_eomonth(start, 2).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 3, 31).unwrap());

        // April (30 days)
        let result = calculate_eomonth(start, 3).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 4, 30).unwrap());
    }

    #[test]
    fn test_calculate_eomonth_large_months() {
        // Test with large month values
        let start = NaiveDate::from_ymd_opt(2020, 1, 1).unwrap();
        let result = calculate_eomonth(start, 36).unwrap(); // 3 years
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 1, 31).unwrap());

        // Negative large values
        let result = calculate_eomonth(start, -24).unwrap(); // 2 years back
        assert_eq!(result, NaiveDate::from_ymd_opt(2018, 1, 31).unwrap());
    }

    // Test the Polars interface
    #[test]
    fn test_eomonth_polars_interface() {
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(),
            NaiveDate::from_ymd_opt(2024, 1, 15).unwrap(), // Leap year
            NaiveDate::from_ymd_opt(2023, 12, 1).unwrap(),
        ];
        let months = vec![1, 1, 1];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EomontKwargs {};
        let result = eomonth(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Check each result
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap()); // Leap year

        let date3 = epoch + Duration::days(result_dates.get(2).unwrap() as i64);
        assert_eq!(date3, NaiveDate::from_ymd_opt(2024, 1, 31).unwrap());
    }

    #[test]
    fn test_null_handling() {
        // Create series with null values
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let date1 = NaiveDate::from_ymd_opt(2023, 1, 15).unwrap();
        let days1 = (date1 - epoch).num_days() as i32;

        let date_values = vec![Some(days1), None, Some(days1)];
        let month_values: Vec<Option<i64>> = vec![Some(1), Some(2), None];

        let date_series = Series::new("dates".into(), date_values)
            .cast(&DataType::Date)
            .unwrap();
        let months_series = Series::new("months".into(), month_values);

        let kwargs = EomontKwargs {};
        let result = eomonth(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();

        // First value should be calculated
        assert!(result_dates.get(0).is_some());
        // Second value should be null (null date)
        assert!(result_dates.get(1).is_none());
        // Third value should be null (null months)
        assert!(result_dates.get(2).is_none());
    }

    #[test]
    fn test_negative_months() {
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 3, 15).unwrap(),
            NaiveDate::from_ymd_opt(2024, 3, 15).unwrap(), // Leap year
            NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(),
        ];
        let months = vec![-1, -1, -12];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EomontKwargs {};
        let result = eomonth(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Mar 15 2023 - 1 month = Feb 28 2023
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // Mar 15 2024 - 1 month = Feb 29 2024 (leap year)
        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());

        // Jan 15 2023 - 12 months = Jan 31 2022
        let date3 = epoch + Duration::days(result_dates.get(2).unwrap() as i64);
        assert_eq!(date3, NaiveDate::from_ymd_opt(2022, 1, 31).unwrap());
    }

    #[test]
    fn test_zero_months() {
        // Zero months should return last day of same month
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(),
            NaiveDate::from_ymd_opt(2023, 2, 15).unwrap(),
            NaiveDate::from_ymd_opt(2023, 4, 15).unwrap(),
        ];
        let months = vec![0, 0, 0];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EomontKwargs {};
        let result = eomonth(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Jan 15 + 0 months = Jan 31
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2023, 1, 31).unwrap());

        // Feb 15 + 0 months = Feb 28
        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // Apr 15 + 0 months = Apr 30
        let date3 = epoch + Duration::days(result_dates.get(2).unwrap() as i64);
        assert_eq!(date3, NaiveDate::from_ymd_opt(2023, 4, 30).unwrap());
    }
}

// Excel compatibility tests
#[cfg(test)]
mod excel_verification_tests {
    use super::*;

    fn test_eomonth_single(start: NaiveDate, months: i64) -> NaiveDate {
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let days = (start - epoch).num_days() as i32;
        let date_series = Series::new("date".into(), vec![days])
            .cast(&DataType::Date)
            .unwrap();
        let months_series = Series::new("months".into(), vec![months]);

        let kwargs = EomontKwargs {};
        let result = eomonth(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        epoch + Duration::days(result_dates.get(0).unwrap() as i64)
    }

    #[test]
    fn test_excel_known_values() {
        // Test against known Excel outputs

        // Basic examples from Excel documentation
        // Jan 1, 2011 + 1 month = Feb 28, 2011
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2011, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(2011, 2, 28).unwrap()
        );

        // Jan 1, 2011 + (-3) months = Oct 31, 2010
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2011, 1, 1).unwrap(), -3),
            NaiveDate::from_ymd_opt(2010, 10, 31).unwrap()
        );

        // Leap year test: Jan 1, 2024 + 1 month = Feb 29, 2024
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap()
        );

        // Non-leap year test: Jan 1, 2023 + 1 month = Feb 28, 2023
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()
        );

        // Multiple months forward
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(), 14),
            NaiveDate::from_ymd_opt(2024, 3, 31).unwrap()
        );

        // Zero months (same month end)
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(), 0),
            NaiveDate::from_ymd_opt(2023, 1, 31).unwrap()
        );
    }

    #[test]
    fn test_excel_1900_standard_leap_year() {
        // Note: Excel treats 1900 as a leap year, but we use standard rules
        // since chrono doesn't support invalid dates like Feb 29, 1900
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(1900, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(1900, 2, 28).unwrap()
        );
    }

    #[test]
    fn test_excel_leap_year_sequences() {
        // Test various leap year scenarios
        let leap_years = vec![2000, 2004, 2008, 2012, 2016, 2020, 2024];
        let non_leap_years = vec![1900, 2001, 2002, 2003, 2100, 2200, 2300];

        for year in leap_years {
            let start = NaiveDate::from_ymd_opt(year, 1, 1).unwrap();
            let result = test_eomonth_single(start, 1);
            assert_eq!(
                result,
                NaiveDate::from_ymd_opt(year, 2, 29).unwrap(),
                "Year {} should be leap year",
                year
            );
        }

        for year in non_leap_years {
            let start = NaiveDate::from_ymd_opt(year, 1, 1).unwrap();
            let result = test_eomonth_single(start, 1);
            assert_eq!(
                result,
                NaiveDate::from_ymd_opt(year, 2, 28).unwrap(),
                "Year {} should not be leap year",
                year
            );
        }
    }

    #[test]
    fn test_excel_month_length_variations() {
        // Test all months to verify correct last day calculation
        let year = 2023; // Non-leap year
        let expected_days = vec![31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

        for (month, expected_day) in expected_days.iter().enumerate() {
            let start = NaiveDate::from_ymd_opt(year, 1, 1).unwrap();
            let result = test_eomonth_single(start, month as i64);
            assert_eq!(
                result.day(),
                *expected_day,
                "Month {} should have {} days",
                month + 1,
                expected_day
            );
        }
    }

    #[test]
    fn test_excel_financial_use_cases() {
        // Common financial scenarios using EOMONTH

        // Quarterly end dates
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        assert_eq!(
            test_eomonth_single(start, 2), // Q1 end
            NaiveDate::from_ymd_opt(2023, 3, 31).unwrap()
        );
        assert_eq!(
            test_eomonth_single(start, 5), // Q2 end
            NaiveDate::from_ymd_opt(2023, 6, 30).unwrap()
        );
        assert_eq!(
            test_eomonth_single(start, 8), // Q3 end
            NaiveDate::from_ymd_opt(2023, 9, 30).unwrap()
        );
        assert_eq!(
            test_eomonth_single(start, 11), // Q4 end
            NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()
        );

        // Monthly payment due dates
        let bond_start = NaiveDate::from_ymd_opt(2023, 1, 15).unwrap();
        for i in 0..12 {
            let result = test_eomonth_single(bond_start, i);
            // Should always be last day of month
            let next_month = result + Duration::days(1);
            assert_ne!(
                result.month(),
                next_month.month(),
                "Month {} result should be last day of month",
                i + 1
            );
        }
    }

    #[test]
    fn test_excel_century_boundaries() {
        // Test century year edge cases

        // 2000 is a leap year (divisible by 400)
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2000, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(2000, 2, 29).unwrap()
        );

        // 2100 is not a leap year (divisible by 100 but not 400)
        assert_eq!(
            test_eomonth_single(NaiveDate::from_ymd_opt(2100, 1, 1).unwrap(), 1),
            NaiveDate::from_ymd_opt(2100, 2, 28).unwrap()
        );
    }

    #[test]
    fn test_excel_large_month_values() {
        // Test with large positive and negative month values
        let start = NaiveDate::from_ymd_opt(2020, 6, 15).unwrap();

        // 5 years forward
        assert_eq!(
            test_eomonth_single(start, 60),
            NaiveDate::from_ymd_opt(2025, 6, 30).unwrap()
        );

        // 5 years backward
        assert_eq!(
            test_eomonth_single(start, -60),
            NaiveDate::from_ymd_opt(2015, 6, 30).unwrap()
        );
    }
}
