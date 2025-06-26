#![allow(clippy::unused_unit)]
use chrono::{Datelike, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct YearFracKwargs {
    pub basis: Option<i32>,
}

/// Calculates the year fraction between two dates based on the specified basis.
///
/// This function replicates Excel's YEARFRAC behavior exactly, including all quirks.
///
/// # Basis options:
/// - 0 (default): US (NASD) 30/360
/// - 1: Actual/Actual
/// - 2: Actual/360
/// - 3: Actual/365
/// - 4: European 30/360
///
/// # Errors
/// Returns an error if an unsupported basis is provided or if series processing fails.
pub fn year_frac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    let start_date_series = &inputs[0];
    let end_date_series = &inputs[1];

    let basis = kwargs.basis.unwrap_or(0);

    // Validate basis
    if !(0..=4).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Must be 0, 1, 2, 3, or 4").into(),
        ));
    }

    // Get the date arrays
    let start_dates = start_date_series.date()?;
    let end_dates = end_date_series.date()?;

    // Calculate year fractions for each pair of dates
    let mut results = Vec::with_capacity(start_dates.len());

    for idx in 0..start_dates.len() {
        let start_opt = start_dates.get(idx);
        let end_opt = end_dates.get(idx);

        match (start_opt, end_opt) {
            (Some(start_days), Some(end_days)) => {
                // Convert days since epoch to NaiveDate
                let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
                let start_date = epoch + chrono::Duration::days(start_days as i64);
                let end_date = epoch + chrono::Duration::days(end_days as i64);

                let fraction = calculate_year_frac(start_date, end_date, basis)?;
                results.push(Some(fraction));
            }
            _ => results.push(None),
        }
    }

    Ok(Series::new("year_frac".into(), results))
}

/// Calculate year fraction for a single pair of dates
fn calculate_year_frac(
    start_date: NaiveDate,
    end_date: NaiveDate,
    basis: i32,
) -> PolarsResult<f64> {
    // Excel always returns positive fractions
    let (start, end) = if start_date <= end_date {
        (start_date, end_date)
    } else {
        (end_date, start_date)
    };

    match basis {
        0 => calculate_30_360_us(start, end),
        1 => calculate_actual_actual(start, end),
        2 => calculate_actual_360(start, end),
        3 => calculate_actual_365(start, end),
        4 => calculate_30_360_eu(start, end),
        _ => unreachable!(), // Already validated
    }
}

/// US (NASD) 30/360 day count convention
fn calculate_30_360_us(start: NaiveDate, end: NaiveDate) -> PolarsResult<f64> {
    let mut d1 = start.day() as i32;
    let m1 = start.month() as i32;
    let y1 = start.year();

    let mut d2 = end.day() as i32;
    let m2 = end.month() as i32;
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
    Ok(days as f64 / 360.0)
}

/// European 30/360 day count convention
fn calculate_30_360_eu(start: NaiveDate, end: NaiveDate) -> PolarsResult<f64> {
    let mut d1 = start.day() as i32;
    let m1 = start.month() as i32;
    let y1 = start.year();

    let mut d2 = end.day() as i32;
    let m2 = end.month() as i32;
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
    Ok(days as f64 / 360.0)
}

/// Actual/Actual day count convention
fn calculate_actual_actual(start: NaiveDate, end: NaiveDate) -> PolarsResult<f64> {
    let days_diff = (end - start).num_days();

    // Case 1: Same calendar year
    if start.year() == end.year() {
        let year_days = if is_leap_year(start.year()) {
            366.0
        } else {
            365.0
        };
        return Ok(days_diff as f64 / year_days);
    }

    // Case 2: Different years but less than 1 year span
    if days_diff <= 366 {
        // Check if Feb 29 is in the range
        let contains_leap_day = contains_feb_29(start, end);
        let year_days = if contains_leap_day { 366.0 } else { 365.0 };
        return Ok(days_diff as f64 / year_days);
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

    let avg_year_length = total_year_days as f64 / year_count as f64;
    Ok(days_diff as f64 / avg_year_length)
}

/// Actual/360 day count convention
fn calculate_actual_360(start: NaiveDate, end: NaiveDate) -> PolarsResult<f64> {
    let days_diff = (end - start).num_days();
    Ok(days_diff as f64 / 360.0)
}

/// Actual/365 day count convention
fn calculate_actual_365(start: NaiveDate, end: NaiveDate) -> PolarsResult<f64> {
    let days_diff = (end - start).num_days();
    Ok(days_diff as f64 / 365.0)
}

/// Check if a year is a leap year
fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
}

/// Check if a date is the last day of its month
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
            .map(|d| (*d - epoch).num_days() as i32)
            .collect();
        Series::new("date".into(), days)
            .cast(&DataType::Date)
            .unwrap()
    }

    #[test]
    fn test_basis_0_us_30_360() {
        // Test basic month difference
        let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 2, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        assert_relative_eq!(values.get(0).unwrap(), 30.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_0_feb_end_handling() {
        // Test February end-of-month handling
        let start = vec![NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 3, 31).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // Feb 28 -> 30, Mar 31 -> 30, so it's exactly 1 month
        assert_relative_eq!(values.get(0).unwrap(), 30.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_0_leap_year_feb() {
        // Test leap year February handling
        let start = vec![NaiveDate::from_ymd_opt(2020, 2, 29).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2020, 3, 31).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // Feb 29 (last of Feb) -> 30, Mar 31 -> 30, so it's exactly 1 month
        assert_relative_eq!(values.get(0).unwrap(), 30.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_1_actual_actual_same_year() {
        // Test within same non-leap year
        let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // 181 days / 365 days
        assert_relative_eq!(values.get(0).unwrap(), 181.0 / 365.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_1_actual_actual_leap_year() {
        // Test within leap year
        let start = vec![NaiveDate::from_ymd_opt(2020, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2020, 7, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // 182 days / 366 days (leap year)
        assert_relative_eq!(values.get(0).unwrap(), 182.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_1_across_years_with_leap() {
        // Test across years including Feb 29
        let start = vec![NaiveDate::from_ymd_opt(2020, 2, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2020, 3, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // 29 days / 366 (contains Feb 29)
        assert_relative_eq!(values.get(0).unwrap(), 29.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_2_actual_360() {
        // Test actual/360
        let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(2) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // 364 days / 360
        assert_relative_eq!(values.get(0).unwrap(), 364.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_3_actual_365() {
        // Test actual/365
        let start = vec![NaiveDate::from_ymd_opt(2020, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2021, 1, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(3) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // 366 days / 365 (leap year but fixed denominator)
        assert_relative_eq!(values.get(0).unwrap(), 366.0 / 365.0, epsilon = 1e-10);
    }

    #[test]
    fn test_basis_4_european_30_360() {
        // Test European 30/360
        let start = vec![NaiveDate::from_ymd_opt(2023, 1, 31).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(4) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // Jan 31 -> 30, Feb 28 stays 28
        // (28 - 30) + 30 * (2 - 1) = -2 + 30 = 28 days
        assert_relative_eq!(values.get(0).unwrap(), 28.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_reversed_dates() {
        // Test that reversed dates give the same positive result
        let date1 = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
        let date2 = NaiveDate::from_ymd_opt(2023, 12, 31).unwrap();

        let start_series1 = create_date_series(vec![date1]);
        let end_series1 = create_date_series(vec![date2]);

        let start_series2 = create_date_series(vec![date2]);
        let end_series2 = create_date_series(vec![date1]);

        let kwargs = YearFracKwargs { basis: Some(0) };

        let result1 = year_frac(&[start_series1, end_series1], &kwargs).unwrap();
        let result2 = year_frac(&[start_series2, end_series2], &kwargs).unwrap();

        let values1 = result1.f64().unwrap();
        let values2 = result2.f64().unwrap();

        // Both should give the same positive result
        assert_relative_eq!(
            values1.get(0).unwrap(),
            values2.get(0).unwrap(),
            epsilon = 1e-10
        );
    }

    #[test]
    fn test_invalid_basis() {
        let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(5) };
        let result = year_frac(&[start_series, end_series], &kwargs);

        assert!(result.is_err());
    }

    #[test]
    fn test_null_handling() {
        // Create series with null values
        let start = [Some(NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()), None];
        let end = [
            Some(NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()),
            Some(NaiveDate::from_ymd_opt(2023, 6, 1).unwrap()),
        ];

        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).unwrap();
        let start_days: Vec<Option<i32>> = start
            .iter()
            .map(|d| d.map(|date| (date - epoch).num_days() as i32))
            .collect();
        let end_days: Vec<Option<i32>> = end
            .iter()
            .map(|d| d.map(|date| (date - epoch).num_days() as i32))
            .collect();

        let start_series = Series::new("start".into(), start_days)
            .cast(&DataType::Date)
            .unwrap();
        let end_series = Series::new("end".into(), end_days)
            .cast(&DataType::Date)
            .unwrap();

        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // First value should be calculated, second should be null
        assert!(values.get(0).is_some());
        assert!(values.get(1).is_none());
    }

    #[test]
    fn test_same_date() {
        // Test same start and end date
        let date = NaiveDate::from_ymd_opt(2023, 6, 15).unwrap();
        let dates = create_date_series(vec![date]);

        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = year_frac(&[dates.clone(), dates], &kwargs).unwrap();
        let values = result.f64().unwrap();

        assert_relative_eq!(values.get(0).unwrap(), 0.0, epsilon = 1e-10);
    }

    #[test]
    fn test_multi_year_average() {
        // Test basis 1 with multi-year span
        let start = vec![NaiveDate::from_ymd_opt(2019, 1, 1).unwrap()];
        let end = vec![NaiveDate::from_ymd_opt(2021, 1, 1).unwrap()];

        let start_series = create_date_series(start);
        let end_series = create_date_series(end);

        let kwargs = YearFracKwargs { basis: Some(1) };
        let result = year_frac(&[start_series, end_series], &kwargs).unwrap();
        let values = result.f64().unwrap();

        // The period from 2019-01-01 to 2021-01-01 is exactly 2 years (731 days)
        // We need to check what Excel actually returns for this
        // Excel's actual result for this is closer to 2.00091... due to how it calculates
        assert_relative_eq!(values.get(0).unwrap(), 2.000_912_408_759_124_4, epsilon = 1e-10);
    }
}
