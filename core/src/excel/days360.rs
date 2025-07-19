// ABOUTME: Implements Excel's DAYS360 function for calculating days between dates using a 360-day year
// ABOUTME: Supports both US (NASD) and European methods for day count conventions used in financial calculations

use chrono::{Datelike, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct Days360Kwargs {
    pub method: Option<bool>,
}

/// Calculates the number of days between two dates based on a 360-day year.
///
/// This function replicates Excel's DAYS360 behavior exactly, including all quirks.
/// The 360-day year assumes 12 months of 30 days each, which is commonly used
/// in financial calculations.
///
/// # Method options:
/// - false (default): US (NASD) method with complex February and month-end handling
/// - true: European method where any 31st becomes 30th
///
/// # Returns
/// The number of days between the dates. Returns negative values when start_date > end_date.
///
/// # Errors
/// Returns an error if series processing fails.
pub fn days360(inputs: &[Series], kwargs: &Days360Kwargs) -> PolarsResult<Series> {
    if inputs.len() < 2 {
        return Err(PolarsError::ComputeError(
            "days360 requires at least 2 parameters".into(),
        ));
    }

    let start_date_series = &inputs[0];
    let end_date_series = &inputs[1];

    let use_european_method = kwargs.method.unwrap_or(false);

    // Get the date arrays
    let start_dates = start_date_series.date()?;
    let end_dates = end_date_series.date()?;

    // Create epoch date once
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Use iterator pattern for vectorized operation
    #[allow(clippy::useless_conversion)]
    let result_ca = start_dates
        .into_iter()
        .zip(end_dates.into_iter())
        .map(|(start_opt, end_opt)| {
            match (start_opt, end_opt) {
                (Some(start_days), Some(end_days)) => {
                    // Convert days since epoch to NaiveDate
                    let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                    let end_date = epoch + chrono::Duration::days(i64::from(end_days));

                    Some(calculate_days360(start_date, end_date, use_european_method))
                }
                _ => None,
            }
        })
        .collect::<Int64Chunked>();

    Ok(result_ca.with_name("days360".into()).into_series())
}

/// Calculate the number of days between two dates using 360-day year convention
fn calculate_days360(start_date: NaiveDate, end_date: NaiveDate, use_european_method: bool) -> i64 {
    let start_year = start_date.year();
    let start_month = i32::try_from(start_date.month()).expect("Month fits in i32");
    let mut start_day = i32::try_from(start_date.day()).expect("Day fits in i32");

    let end_year = end_date.year();
    let end_month = i32::try_from(end_date.month()).expect("Month fits in i32");
    let mut end_day = i32::try_from(end_date.day()).expect("Day fits in i32");

    if use_european_method {
        // European method: Simply adjust any 31st to 30th
        if start_day == 31 {
            start_day = 30;
        }
        if end_day == 31 {
            end_day = 30;
        }
    } else {
        // US (NASD) method: Complex rules for February and month-end handling

        // Check if dates are last day of February
        let start_is_feb_last = start_date.month() == 2 && is_last_day_of_month(start_date);
        let end_is_feb_last = end_date.month() == 2 && is_last_day_of_month(end_date);

        // Rule 1: If both dates are last day of February, set end day to 30
        if start_is_feb_last && end_is_feb_last {
            end_day = 30;
        }

        // Rule 2: If start date is last day of February, set start day to 30
        if start_is_feb_last {
            start_day = 30;
        }

        // Rule 3: If start day is 30 or 31 and end day is 31, set end day to 30
        if start_day >= 30 && end_day == 31 {
            end_day = 30;
        }

        // Rule 4: If start day is 31, set start day to 30
        if start_day == 31 {
            start_day = 30;
        }
    }

    // Calculate days using 360-day year formula
    i64::from(end_year - start_year) * 360
        + i64::from(end_month - start_month) * 30
        + i64::from(end_day - start_day)
}

/// Check if a date is the last day of its month
#[inline]
fn is_last_day_of_month(date: NaiveDate) -> bool {
    let next_day = date + chrono::Duration::days(1);
    next_day.month() != date.month()
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

    #[test]
    fn test_calculate_days360_us_method_basic() {
        // Test basic calculation for US method
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 2, 1).unwrap();

        let result = calculate_days360(start, end, false);
        assert_eq!(result, 30); // 1 month = 30 days
    }

    #[test]
    fn test_calculate_days360_european_method_basic() {
        // Test basic calculation for European method
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 2, 1).unwrap();

        let result = calculate_days360(start, end, true);
        assert_eq!(result, 30); // 1 month = 30 days
    }

    #[test]
    fn test_calculate_days360_us_method_31st_handling() {
        // Test US method handling of 31st days
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 3, 31).unwrap();

        let result = calculate_days360(start, end, false);
        // Jan 31 -> 30, Mar 31 -> 30 (since start is 30)
        // (30 - 30) + 30 * (3 - 1) = 0 + 60 = 60
        assert_eq!(result, 60);
    }

    #[test]
    fn test_calculate_days360_european_method_31st_handling() {
        // Test European method handling of 31st days
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 3, 31).unwrap();

        let result = calculate_days360(start, end, true);
        // Jan 31 -> 30, Mar 31 -> 30
        // (30 - 30) + 30 * (3 - 1) = 0 + 60 = 60
        assert_eq!(result, 60);
    }

    #[test]
    fn test_calculate_days360_us_method_february_last_day() {
        // Test US method handling of February last day
        let start = NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(); // Last day of Feb (non-leap)
        let end = NaiveDate::from_ymd_opt(2023, 3, 31).unwrap();

        let result = calculate_days360(start, end, false);
        // Feb 28 (last of Feb) -> 30, Mar 31 -> 30 (since start is 30)
        // (30 - 30) + 30 * (3 - 2) = 0 + 30 = 30
        assert_eq!(result, 30);
    }

    #[test]
    fn test_calculate_days360_us_method_leap_year_february() {
        // Test US method handling of leap year February
        let start = NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(); // Last day of Feb (leap year)
        let end = NaiveDate::from_ymd_opt(2020, 3, 31).unwrap();

        let result = calculate_days360(start, end, false);
        // Feb 29 (last of Feb) -> 30, Mar 31 -> 30 (since start is 30)
        // (30 - 30) + 30 * (3 - 2) = 0 + 30 = 30
        assert_eq!(result, 30);
    }

    #[test]
    fn test_calculate_days360_both_feb_last_days() {
        // Test US method when both dates are last day of February
        let start = NaiveDate::from_ymd_opt(2019, 2, 28).unwrap(); // Last day of Feb (non-leap)
        let end = NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(); // Last day of Feb (leap year)

        let result = calculate_days360(start, end, false);
        // Both Feb last days: start 28->30, end 29->30
        // (30 - 30) + 30 * (2 - 2) + 360 * (2020 - 2019) = 0 + 0 + 360 = 360
        assert_eq!(result, 360);
    }

    #[test]
    fn test_calculate_days360_negative_result() {
        // Test negative result when start > end
        let start = NaiveDate::from_ymd_opt(2023, 3, 1).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();

        let result = calculate_days360(start, end, false);
        assert_eq!(result, -60); // -2 months = -60 days
    }

    #[test]
    fn test_calculate_days360_same_date() {
        // Test same start and end date
        let date = NaiveDate::from_ymd_opt(2023, 6, 15).unwrap();

        let result = calculate_days360(date, date, false);
        assert_eq!(result, 0);
    }

    #[test]
    fn test_calculate_days360_full_year() {
        // Test full year calculation
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let end = NaiveDate::from_ymd_opt(2024, 1, 1).unwrap();

        let result = calculate_days360(start, end, false);
        assert_eq!(result, 360); // 1 year = 360 days
    }

    #[test]
    fn test_polars_interface_us_method() {
        // Test the Polars interface with US method
        let start_dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
        ];
        let end_dates = vec![
            NaiveDate::from_ymd_opt(2023, 2, 1).unwrap(),
            NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
        ];

        let start_series = create_date_series(start_dates);
        let end_series = create_date_series(end_dates);

        let kwargs = Days360Kwargs {
            method: Some(false),
        };
        let result = days360(&[start_series, end_series], &kwargs).unwrap();

        let values = result.i64().unwrap();
        assert_eq!(values.get(0).unwrap(), 30); // Jan 1 to Feb 1
        assert_eq!(values.get(1).unwrap(), 30); // Feb 28 (last) to Mar 31
    }

    #[test]
    fn test_polars_interface_european_method() {
        // Test the Polars interface with European method
        let start_dates = vec![
            NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
            NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
        ];
        let end_dates = vec![
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
            NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
        ];

        let start_series = create_date_series(start_dates);
        let end_series = create_date_series(end_dates);

        let kwargs = Days360Kwargs { method: Some(true) };
        let result = days360(&[start_series, end_series], &kwargs).unwrap();

        let values = result.i64().unwrap();
        assert_eq!(values.get(0).unwrap(), 28); // Jan 31 (->30) to Feb 28 = 28 days
        assert_eq!(values.get(1).unwrap(), -60); // Mar 31 (->30) to Jan 31 (->30) = -60 days
    }

    #[test]
    fn test_polars_interface_default_method() {
        // Test the Polars interface with default method (US)
        let start_dates = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        let end_dates = vec![NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()];

        let start_series = create_date_series(start_dates);
        let end_series = create_date_series(end_dates);

        let kwargs = Days360Kwargs { method: None }; // Default should be US method
        let result = days360(&[start_series, end_series], &kwargs).unwrap();

        let values = result.i64().unwrap();
        assert_eq!(values.get(0).unwrap(), 360); // Full year
    }

    #[test]
    fn test_null_handling() {
        // Test handling of null values
        let start = [Some(NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()), None];
        let end = [
            Some(NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()),
            Some(NaiveDate::from_ymd_opt(2023, 6, 1).unwrap()),
        ];

        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let start_days: Vec<Option<i32>> = start
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
        let end_days: Vec<Option<i32>> = end
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

        let start_series = Series::new("start".into(), start_days)
            .cast(&DataType::Date)
            .unwrap();
        let end_series = Series::new("end".into(), end_days)
            .cast(&DataType::Date)
            .unwrap();

        let kwargs = Days360Kwargs {
            method: Some(false),
        };
        let result = days360(&[start_series, end_series], &kwargs).unwrap();
        let values = result.i64().unwrap();

        // First value should be calculated, second should be null
        assert!(values.get(0).is_some());
        assert!(values.get(1).is_none());
    }

    #[test]
    fn test_insufficient_parameters() {
        // Test error handling for insufficient parameters
        let series = create_date_series(vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()]);
        let kwargs = Days360Kwargs {
            method: Some(false),
        };

        let result = days360(&[series], &kwargs);
        assert!(result.is_err());
    }
}

// Excel Verification Tests
//
// These tests verify exact compatibility with Microsoft Excel's DAYS360 function.
// The function implements the 360-day year convention used in financial calculations
// where each month is assumed to have 30 days.

#[cfg(test)]
mod excel_verification_tests {
    use super::*;
    use chrono::NaiveDate;

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

    fn test_days360(start: NaiveDate, end: NaiveDate, method: Option<bool>) -> i64 {
        let start_series = create_date_series(vec![start]);
        let end_series = create_date_series(vec![end]);
        let kwargs = Days360Kwargs { method };
        let result = days360(&[start_series, end_series], &kwargs).unwrap();
        result.i64().unwrap().get(0).unwrap()
    }

    #[test]
    fn test_excel_known_values_us_method() {
        // US method (default) - Known Excel results
        //
        // These test cases verify against known Excel DAYS360 outputs
        // using the US (NASD) method which is the default behavior.

        // Basic month calculation
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 2, 1).unwrap(),
                Some(false)
            ),
            30
        );

        // Full year calculation
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
                Some(false)
            ),
            360
        );

        // 31st day handling - start date
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
                NaiveDate::from_ymd_opt(2023, 2, 1).unwrap(),
                Some(false)
            ),
            1 // Jan 31 -> 30, so 1 day to Feb 1
        );

        // 31st day handling - end date
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
                Some(false)
            ),
            30 // Jan 31 -> 30, so 30 days from Jan 1
        );

        // February last day handling (non-leap year)
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
                NaiveDate::from_ymd_opt(2023, 3, 1).unwrap(),
                Some(false)
            ),
            1 // Feb 28 (last day) -> 30, so 1 day to Mar 1
        );

        // February last day handling (leap year)
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
                NaiveDate::from_ymd_opt(2020, 3, 1).unwrap(),
                Some(false)
            ),
            1 // Feb 29 (last day) -> 30, so 1 day to Mar 1
        );

        // Both dates are February last days
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2019, 2, 28).unwrap(),
                NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
                Some(false)
            ),
            360 // Both adjusted to 30, exactly 1 year
        );
    }

    #[test]
    fn test_excel_known_values_european_method() {
        // European method - Known Excel results
        //
        // These test cases verify against known Excel DAYS360 outputs
        // using the European method (method=TRUE).

        // Basic month calculation
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 2, 1).unwrap(),
                Some(true)
            ),
            30
        );

        // 31st day handling - both dates
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
                NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
                Some(true)
            ),
            60 // Both 31st -> 30th, 2 months = 60 days
        );

        // February handling (European method doesn't treat Feb last day specially)
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
                NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
                Some(true)
            ),
            32 // Feb 28 stays 28, Mar 31 -> 30, so 30-28+30 = 32
        );

        // Full year with European method
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
                Some(true)
            ),
            360
        );
    }

    #[test]
    fn test_excel_negative_values() {
        // Test negative values when start > end

        // US method
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 3, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                Some(false)
            ),
            -60 // -2 months
        );

        // European method
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
                NaiveDate::from_ymd_opt(2023, 1, 31).unwrap(),
                Some(true)
            ),
            -60 // Both 31st -> 30th, -2 months = -60 days
        );
    }

    #[test]
    fn test_excel_consecutive_days() {
        // Test consecutive day calculations

        let start = NaiveDate::from_ymd_opt(2023, 6, 15).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 6, 16).unwrap();

        // Both methods should give same result for consecutive days
        assert_eq!(test_days360(start, end, Some(false)), 1);
        assert_eq!(test_days360(start, end, Some(true)), 1);
    }

    #[test]
    fn test_excel_same_date() {
        // Test same date for both methods
        let date = NaiveDate::from_ymd_opt(2023, 6, 15).unwrap();

        assert_eq!(test_days360(date, date, Some(false)), 0);
        assert_eq!(test_days360(date, date, Some(true)), 0);
    }

    #[test]
    fn test_excel_default_method() {
        // Test that default method is US method
        let start = NaiveDate::from_ymd_opt(2023, 1, 31).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 3, 31).unwrap();

        let default_result = test_days360(start, end, None);
        let us_result = test_days360(start, end, Some(false));

        assert_eq!(default_result, us_result);
    }

    #[test]
    fn test_excel_financial_examples() {
        // Real-world financial calculation examples

        // Bond settlement period
        let settlement = NaiveDate::from_ymd_opt(2023, 3, 15).unwrap();
        let maturity = NaiveDate::from_ymd_opt(2023, 9, 15).unwrap();

        // 6 months = 180 days in 360-day year
        assert_eq!(test_days360(settlement, maturity, Some(false)), 180);

        // Quarterly period
        let start = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 4, 1).unwrap();

        // 3 months = 90 days
        assert_eq!(test_days360(start, end, Some(false)), 90);
    }

    #[test]
    fn test_excel_edge_cases() {
        // Test edge cases that might cause issues

        // End of year to beginning of next year
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
                NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(),
                Some(false)
            ),
            1 // Dec 31 -> 30, so 1 day to Jan 1
        );

        // Cross-year February handling
        assert_eq!(
            test_days360(
                NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
                NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
                Some(false)
            ),
            360 // Both Feb last days -> 30, exactly 1 year
        );
    }
}
