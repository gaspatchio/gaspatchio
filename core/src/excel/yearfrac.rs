// ABOUTME: Excel-compatible YEARFRAC function implementation
// ABOUTME: Calculates year fractions between dates using various day count conventions

#![allow(clippy::unused_unit)]
use chrono::{Datelike, NaiveDate};
use polars::prelude::*;
use serde::Deserialize;

// Day count convention constants
const DAYS_30_360: f64 = 360.0;
const DAYS_ACTUAL_365: f64 = 365.0;
const DAYS_ACTUAL_366: f64 = 366.0;
const DAYS_PER_MONTH_30_360: i32 = 30;
const DAYS_PER_YEAR_30_360: i32 = 360;

// Basis constants
const BASIS_30_360_US: i32 = 0;
const BASIS_ACTUAL_ACTUAL: i32 = 1;
const BASIS_ACTUAL_360: i32 = 2;
const BASIS_ACTUAL_365: i32 = 3;
const BASIS_30_360_EU: i32 = 4;

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
pub fn yearfrac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    let start_date_series = &inputs[0];
    let end_date_series = &inputs[1];

    let basis = kwargs.basis.unwrap_or(BASIS_30_360_US);

    // Validate basis
    if !(BASIS_30_360_US..=BASIS_30_360_EU).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Must be 0, 1, 2, 3, or 4").into(),
        ));
    }

    // Handle different input types (scalar dates or list of dates)
    match (start_date_series.dtype(), end_date_series.dtype()) {
        (DataType::Date, DataType::Date) => {
            // Both are scalar dates
            let start_dates = start_date_series.date()?;
            let end_dates = end_date_series.date()?;
            yearfrac_scalar(start_dates, end_dates, basis)
        }
        (DataType::List(_), DataType::Date) => {
            // Start is list, end is scalar - broadcast end
            yearfrac_list_scalar(start_date_series, end_date_series, basis, false)
        }
        (DataType::Date, DataType::List(_)) => {
            // Start is scalar, end is list - broadcast start
            yearfrac_list_scalar(end_date_series, start_date_series, basis, true)
        }
        (DataType::List(_), DataType::List(_)) => {
            // Both are lists
            yearfrac_list_list(start_date_series, end_date_series, basis)
        }
        _ => Err(PolarsError::ComputeError(
            format!(
                "yearfrac requires Date or List[Date] inputs, got {} and {}",
                start_date_series.dtype(),
                end_date_series.dtype()
            )
            .into(),
        )),
    }
}

/// Handle scalar date inputs
fn yearfrac_scalar(
    start_dates: &DateChunked,
    end_dates: &DateChunked,
    basis: i32,
) -> PolarsResult<Series> {

    // Create epoch date once
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Use binary_elementwise pattern for vectorized operation
    let result_ca = start_dates
        .into_iter()
        .zip(end_dates.into_iter())
        .map(|(start_opt, end_opt)| {
            match (start_opt, end_opt) {
                (Some(start_days), Some(end_days)) => {
                    // Convert days since epoch to NaiveDate
                    let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                    let end_date = epoch + chrono::Duration::days(i64::from(end_days));

                    Some(calculate_yearfrac(start_date, end_date, basis))
                }
                _ => None,
            }
        })
        .collect::<Float64Chunked>();

    Ok(result_ca.with_name("year_frac".into()).into_series())
}

/// Handle list-scalar combinations (broadcasting)
fn yearfrac_list_scalar(
    list_series: &Series,
    scalar_series: &Series,
    basis: i32,
    reverse_args: bool,
) -> PolarsResult<Series> {
    let list_ca = list_series.list()?;
    let scalar_date = scalar_series.date()?.get(0);
    
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    let result: ListChunked = list_ca
        .apply_amortized(|s| {
            if let Ok(dates) = s.as_ref().date() {
                let result_ca = dates
                    .into_iter()
                    .map(|date_opt| match (date_opt, scalar_date) {
                        (Some(list_days), Some(scalar_days)) => {
                            let list_date = epoch + chrono::Duration::days(i64::from(list_days));
                            let scalar_date = epoch + chrono::Duration::days(i64::from(scalar_days));
                            let yearfrac = if reverse_args {
                                calculate_yearfrac(scalar_date, list_date, basis)
                            } else {
                                calculate_yearfrac(list_date, scalar_date, basis)
                            };
                            Some(yearfrac)
                        }
                        _ => None,
                    })
                    .collect::<Float64Chunked>();
                result_ca.into_series()
            } else {
                let len = s.as_ref().len();
                let nulls = Float64Chunked::full_null("".into(), len);
                nulls.into_series()
            }
        });

    Ok(result.into_series())
}

/// Handle list-list combinations
fn yearfrac_list_list(
    start_series: &Series,
    end_series: &Series,
    basis: i32,
) -> PolarsResult<Series> {
    let start_list = start_series.list()?;
    let end_list = end_series.list()?;
    
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");
    
    let result: ListChunked = start_list
        .into_iter()
        .zip(end_list.into_iter())
        .map(|(start_opt, end_opt)| {
            match (start_opt, end_opt) {
                (Some(start_s), Some(end_s)) => {
                    let start_dates = start_s.date().ok()?;
                    let end_dates = end_s.date().ok()?;
                    
                    let result_ca = start_dates
                        .into_iter()
                        .zip(end_dates.into_iter())
                        .map(|(start_d, end_d)| {
                            match (start_d, end_d) {
                                (Some(start_days), Some(end_days)) => {
                                    let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                                    let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                                    Some(calculate_yearfrac(start_date, end_date, basis))
                                }
                                _ => None,
                            }
                        })
                        .collect::<Float64Chunked>();
                    
                    Some(result_ca.into_series())
                }
                _ => None,
            }
        })
        .collect();
    
    Ok(result.into_series())
}

/// Calculate year fraction for a single pair of dates
#[inline]
fn calculate_yearfrac(start_date: NaiveDate, end_date: NaiveDate, basis: i32) -> f64 {
    // Check if we need to return a negative value
    let is_negative = start_date > end_date;

    // Always calculate with start <= end for the algorithms
    let (start, end) = if start_date <= end_date {
        (start_date, end_date)
    } else {
        (end_date, start_date)
    };

    let fraction = match basis {
        BASIS_30_360_US => calculate_30_360_us(start, end),
        BASIS_ACTUAL_ACTUAL => calculate_actual_actual(start, end),
        BASIS_ACTUAL_360 => calculate_actual_360(start, end),
        BASIS_ACTUAL_365 => calculate_actual_365(start, end),
        BASIS_30_360_EU => calculate_30_360_eu(start, end),
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
        d2 = DAYS_PER_MONTH_30_360;
    }

    // Rule 2: If start date is last day of February, set d1 to 30
    if start_is_feb_last {
        d1 = DAYS_PER_MONTH_30_360;
    }

    // Rule 3: If d2 is 31 and d1 is 30 or 31, set d2 to 30
    if d2 == 31 && d1 >= DAYS_PER_MONTH_30_360 {
        d2 = DAYS_PER_MONTH_30_360;
    }

    // Rule 4: If d1 is 31, set d1 to 30
    if d1 == 31 {
        d1 = DAYS_PER_MONTH_30_360;
    }

    // Calculate the day count
    let days = (y2 - y1) * DAYS_PER_YEAR_30_360 + (m2 - m1) * DAYS_PER_MONTH_30_360 + (d2 - d1);
    f64::from(days) / DAYS_30_360
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
        d1 = DAYS_PER_MONTH_30_360;
    }
    if d2 == 31 {
        d2 = DAYS_PER_MONTH_30_360;
    }

    // Calculate the day count
    let days = (y2 - y1) * DAYS_PER_YEAR_30_360 + (m2 - m1) * DAYS_PER_MONTH_30_360 + (d2 - d1);
    f64::from(days) / DAYS_30_360
}

/// Actual/Actual day count convention
#[allow(clippy::cast_precision_loss)]
fn calculate_actual_actual(start: NaiveDate, end: NaiveDate) -> f64 {
    let days_diff = (end - start).num_days();

    // Case 1: Same calendar year
    if start.year() == end.year() {
        let year_days = if is_leap_year(start.year()) {
            DAYS_ACTUAL_366
        } else {
            DAYS_ACTUAL_365
        };
        return days_diff as f64 / year_days;
    }

    // Case 2: Different years but less than 1 year span
    if days_diff <= 366 {
        // Check if Feb 29 is in the range
        let contains_leap_day = contains_feb_29(start, end);
        let year_days = if contains_leap_day {
            DAYS_ACTUAL_366
        } else {
            DAYS_ACTUAL_365
        };
        return days_diff as f64 / year_days;
    }

    // Case 3: Multi-year span - use average year length (matches existing tests)
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
    days_diff as f64 / DAYS_30_360
}

/// Actual/365 day count convention
#[allow(clippy::cast_precision_loss)]
fn calculate_actual_365(start: NaiveDate, end: NaiveDate) -> f64 {
    let days_diff = (end - start).num_days();
    days_diff as f64 / DAYS_ACTUAL_365
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

/// Returns the output type for the yearfrac function
pub fn yearfrac_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let start_type = &input_fields[0].dtype;
    let end_type = &input_fields[1].dtype;
    
    match (start_type, end_type) {
        (DataType::Date, DataType::Date) => {
            Ok(Field::new("year_frac".into(), DataType::Float64))
        }
        (DataType::List(_), _) | (_, DataType::List(_)) => {
            Ok(Field::new("year_frac".into(), DataType::List(Box::new(DataType::Float64))))
        }
        _ => Ok(Field::new("year_frac".into(), DataType::Float64)),
    }
}
