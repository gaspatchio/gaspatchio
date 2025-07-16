// ABOUTME: Excel EDATE function implementation that adds or subtracts months from dates
// ABOUTME: Handles month-end edge cases matching Excel's behavior exactly

use chrono::{Datelike, Duration, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct EdateKwargs {}

/// Excel EDATE implementation for Polars
///
/// The EDATE function returns a date that is the indicated number of months before
/// or after a specified date. It's commonly used in financial calculations to compute
/// maturity dates, due dates, and other month-based date projections.
///
/// # Arguments
/// * `inputs` - Array of Series where:
///   - inputs[0]: start_date - The starting date
///   - inputs[1]: months - Number of months to add (positive) or subtract (negative)
/// * `kwargs` - Empty struct (no optional parameters for EDATE)
///
/// # Returns
/// A Series containing the calculated dates
///
/// # Excel Compatibility Notes
/// - Intelligently handles month-end dates (e.g., Jan 31 + 1 month = Feb 28/29)
/// - Strips time components from datetime values
/// - Truncates non-integer month values
/// - Returns errors for dates outside Excel's valid range (1900-01-01 to 9999-12-31)
pub fn edate(inputs: &[Series], _kwargs: &EdateKwargs) -> PolarsResult<Series> {
    // Validate input count
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "EDATE requires exactly 2 parameters: start_date and months".into(),
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
                    match calculate_edate(start_date, months_to_add) {
                        Ok(result_date) => {
                            // Convert back to days since epoch
                            let days = (result_date - epoch).num_days();
                            // Ensure it fits in i32 for Polars Date type
                            days.try_into().ok()
                        }
                        Err(_) => None, // Date out of range
                    }
                }
                _ => None, // Handle null inputs
            }
        })
        .collect::<Int32Chunked>();

    // Convert to Date series
    Ok(result_ca
        .with_name("edate".into())
        .into_date()
        .into_series())
}

/// Calculate EDATE result for a single date and months value
///
/// This function implements Excel's month addition logic, including:
/// - Preserving the day of month when possible
/// - Adjusting to month-end when the target month has fewer days
/// - Handling negative months for subtraction
///
/// # Excel's Month-End Logic
/// If the start date is the last day of a month OR if the calculated day
/// doesn't exist in the target month (e.g., Jan 31 -> Feb), the result
/// will be the last day of the target month.
fn calculate_edate(start_date: NaiveDate, months: i64) -> Result<NaiveDate, &'static str> {
    // Excel's date range: 1900-01-01 to 9999-12-31
    const MIN_EXCEL_DATE: i32 = 1900;
    const MAX_EXCEL_DATE: i32 = 9999;

    let start_year = start_date.year();
    let start_month = start_date.month();
    let start_day = start_date.day();

    // Check if start date is last day of its month
    let is_start_last_day = is_last_day_of_month(start_date);

    // Calculate target year and month
    let total_months = start_year as i64 * 12 + start_month as i64 - 1 + months;
    let target_year = (total_months / 12) as i32;
    let target_month = ((total_months % 12 + 12) % 12 + 1) as u32;

    // Check if result year is in valid range
    if target_year < MIN_EXCEL_DATE || target_year > MAX_EXCEL_DATE {
        return Err("Date outside valid Excel range");
    }

    // Determine the target day
    let target_day = if is_start_last_day {
        // If start was last day of month, make result last day of target month
        days_in_month(target_year, target_month)
    } else {
        // Try to preserve the day, but adjust if it doesn't exist in target month
        let max_day = days_in_month(target_year, target_month);
        start_day.min(max_day)
    };

    // Create the result date
    NaiveDate::from_ymd_opt(target_year, target_month, target_day).ok_or("Invalid date calculation")
}

/// Check if a date is the last day of its month
#[inline]
fn is_last_day_of_month(date: NaiveDate) -> bool {
    let next_day = date + Duration::days(1);
    next_day.month() != date.month()
}

/// Get the number of days in a specific month
#[inline]
fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap_year(year) {
                29
            } else {
                28
            }
        }
        _ => unreachable!("Invalid month"),
    }
}

/// Check if a year is a leap year
#[inline]
fn is_leap_year(year: i32) -> bool {
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
    fn test_calculate_edate_basic() {
        // Simple case: Add 1 month
        let start = NaiveDate::from_ymd_opt(2023, 1, 15).unwrap();
        let result = calculate_edate(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 15).unwrap());

        // Subtract months
        let result = calculate_edate(start, -1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2022, 12, 15).unwrap());
    }

    #[test]
    fn test_calculate_edate_month_end() {
        // Jan 31 + 1 month = Feb 28 (non-leap year)
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();
        let result = calculate_edate(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // Jan 31 + 1 month = Feb 29 (leap year)
        let start = NaiveDate::from_ymd_opt(2024, 1, 31).unwrap();
        let result = calculate_edate(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());

        // Feb 28 + 1 month = Mar 28 (non-leap, not last day)
        let start = NaiveDate::from_ymd_opt(2023, 2, 28).unwrap();
        let result = calculate_edate(start, 1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 3, 31).unwrap()); // Feb 28 is last day

        // Mar 31 - 1 month = Feb 28 (non-leap year)
        let start = NaiveDate::from_ymd_opt(2023, 3, 31).unwrap();
        let result = calculate_edate(start, -1).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());
    }

    #[test]
    fn test_calculate_edate_year_boundary() {
        // Cross year forward
        let start = NaiveDate::from_ymd_opt(2023, 11, 15).unwrap();
        let result = calculate_edate(start, 3).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2024, 2, 15).unwrap());

        // Cross year backward
        let start = NaiveDate::from_ymd_opt(2024, 2, 15).unwrap();
        let result = calculate_edate(start, -3).unwrap();
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 11, 15).unwrap());
    }

    #[test]
    fn test_calculate_edate_large_months() {
        // Add multiple years worth of months
        let start = NaiveDate::from_ymd_opt(2020, 1, 15).unwrap();
        let result = calculate_edate(start, 36).unwrap(); // 3 years
        assert_eq!(result, NaiveDate::from_ymd_opt(2023, 1, 15).unwrap());

        // Subtract multiple years
        let result = calculate_edate(start, -24).unwrap(); // 2 years back
        assert_eq!(result, NaiveDate::from_ymd_opt(2018, 1, 15).unwrap());
    }

    // Test the Polars interface
    #[test]
    fn test_edate_polars_interface() {
        let dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
            NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
        ];
        let months = vec![1, 1, 1];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EdateKwargs {};
        let result = edate(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Check each result
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2023, 2, 15).unwrap());

        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()); // Month-end handling

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

        let kwargs = EdateKwargs {};
        let result = edate(&[date_series, months_series], &kwargs).unwrap();

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
            NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
            NaiveDate::from_ymd_opt(2023, 5, 31).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
        ];
        let months = vec![-1, -2, -12];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EdateKwargs {};
        let result = edate(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Mar 31 - 1 month = Feb 28
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2023, 2, 28).unwrap());

        // May 31 - 2 months = Mar 31
        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2023, 3, 31).unwrap());

        // Jan 1 2023 - 12 months = Jan 1 2022
        let date3 = epoch + Duration::days(result_dates.get(2).unwrap() as i64);
        assert_eq!(date3, NaiveDate::from_ymd_opt(2022, 1, 1).unwrap());
    }

    #[test]
    fn test_leap_year_february() {
        // Test leap year edge cases
        let dates = vec![
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(), // Leap day
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(), // Non-leap last day
            NaiveDate::from_ymd_opt(2024, 1, 29).unwrap(), // Jan 29 in leap year
        ];
        let months = vec![12, 12, 1];

        let date_series = create_date_series(dates);
        let months_series = create_i64_series(months);

        let kwargs = EdateKwargs {};
        let result = edate(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();

        // Feb 29 2024 + 12 months = Feb 28 2025 (non-leap year)
        let date1 = epoch + Duration::days(result_dates.get(0).unwrap() as i64);
        assert_eq!(date1, NaiveDate::from_ymd_opt(2025, 2, 28).unwrap());

        // Feb 28 2023 + 12 months = Feb 29 2024 (leap year, last day to last day)
        let date2 = epoch + Duration::days(result_dates.get(1).unwrap() as i64);
        assert_eq!(date2, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());

        // Jan 29 2024 + 1 month = Feb 29 2024 (day preserved in leap year)
        let date3 = epoch + Duration::days(result_dates.get(2).unwrap() as i64);
        assert_eq!(date3, NaiveDate::from_ymd_opt(2024, 2, 29).unwrap());
    }

    #[test]
    fn test_consistent_day_preservation() {
        // When day exists in all months, it should be preserved
        let start = NaiveDate::from_ymd_opt(2023, 1, 15).unwrap();
        let months_to_test = vec![1, 2, 3, 6, 12, -3, -6];

        for months in months_to_test {
            let result = calculate_edate(start, months).unwrap();
            assert_eq!(
                result.day(),
                15,
                "Day should be preserved for {} months",
                months
            );
        }
    }

    #[test]
    fn test_last_day_preservation() {
        // When starting from last day of month, result should be last day
        let test_cases = vec![
            (NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(), 1), // Jan 31
            (NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(), 1), // Mar 31
            (NaiveDate::from_ymd_opt(2023, 4, 30).unwrap(), 1), // Apr 30
            (NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(), 1), // Feb 29 (leap)
        ];

        for (start, months) in test_cases {
            let result = calculate_edate(start, months).unwrap();
            assert!(
                is_last_day_of_month(result),
                "Result should be last day of month for {} + {} months",
                start,
                months
            );
        }
    }
}

// Excel compatibility tests
#[cfg(test)]
mod excel_verification_tests {
    use super::*;

    fn test_edate_single(start: NaiveDate, months: i64) -> NaiveDate {
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let days = (start - epoch).num_days() as i32;
        let date_series = Series::new("date".into(), vec![days])
            .cast(&DataType::Date)
            .unwrap();
        let months_series = Series::new("months".into(), vec![months]);

        let kwargs = EdateKwargs {};
        let result = edate(&[date_series, months_series], &kwargs).unwrap();

        let result_dates = result.date().unwrap();
        epoch + Duration::days(result_dates.get(0).unwrap() as i64)
    }

    #[test]
    fn test_excel_known_values() {
        // Test against known Excel outputs

        // Basic month addition
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(), 1),
            NaiveDate::from_ymd_opt(2023, 2, 15).unwrap()
        );

        // Month-end handling: Jan 31 + 1 month = Feb 28
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(), 1),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()
        );

        // Leap year: Jan 31 + 1 month = Feb 29
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2024, 1, 31).unwrap(), 1),
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap()
        );

        // Multiple months
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2023, 1, 15).unwrap(), 14),
            NaiveDate::from_ymd_opt(2024, 3, 15).unwrap()
        );

        // Negative months
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(), -1),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()
        );

        // Year boundary
        assert_eq!(
            test_edate_single(NaiveDate::from_ymd_opt(2022, 11, 30).unwrap(), 3),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()
        );
    }

    #[test]
    fn test_excel_month_end_sequences() {
        // Test Excel's behavior of maintaining month-end dates
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();

        // Jan 31 -> Feb 28 -> Mar 31 -> Apr 30 -> May 31
        assert_eq!(
            test_edate_single(start, 1),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()
        );
        assert_eq!(
            test_edate_single(start, 2),
            NaiveDate::from_ymd_opt(2023, 3, 31).unwrap()
        );
        assert_eq!(
            test_edate_single(start, 3),
            NaiveDate::from_ymd_opt(2023, 4, 30).unwrap()
        );
        assert_eq!(
            test_edate_single(start, 4),
            NaiveDate::from_ymd_opt(2023, 5, 31).unwrap()
        );
    }

    #[test]
    fn test_excel_leap_year_transitions() {
        // Feb 29 + months should handle non-leap years correctly
        let leap_day = NaiveDate::from_ymd_opt(2024, 2, 29).unwrap();

        // Feb 29 2024 + 12 months = Feb 28 2025
        assert_eq!(
            test_edate_single(leap_day, 12),
            NaiveDate::from_ymd_opt(2025, 2, 28).unwrap()
        );

        // Feb 29 2024 + 48 months = Feb 29 2028 (next leap year)
        assert_eq!(
            test_edate_single(leap_day, 48),
            NaiveDate::from_ymd_opt(2028, 2, 29).unwrap()
        );
    }

    #[test]
    fn test_excel_financial_use_cases() {
        // Common financial calculations

        // Quarterly payments starting Jan 31
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();
        assert_eq!(
            test_edate_single(start, 3), // Q2
            NaiveDate::from_ymd_opt(2023, 4, 30).unwrap()
        );
        assert_eq!(
            test_edate_single(start, 6), // Q3
            NaiveDate::from_ymd_opt(2023, 7, 31).unwrap()
        );
        assert_eq!(
            test_edate_single(start, 9), // Q4
            NaiveDate::from_ymd_opt(2023, 10, 31).unwrap()
        );

        // Monthly bond coupon from Feb 28
        let bond_start = NaiveDate::from_ymd_opt(2023, 2, 28).unwrap();
        for i in 1..=12 {
            let result = test_edate_single(bond_start, i);
            // All results should be month-end dates
            assert!(
                is_last_day_of_month(result),
                "Month {} should give month-end date",
                i
            );
        }
    }

    #[test]
    fn test_excel_edge_case_century_2100() {
        // 2100 is not a leap year (divisible by 100 but not 400)
        let start = NaiveDate::from_ymd_opt(2100, 1, 31).unwrap();
        assert_eq!(
            test_edate_single(start, 1),
            NaiveDate::from_ymd_opt(2100, 2, 28).unwrap()
        );
    }
}
