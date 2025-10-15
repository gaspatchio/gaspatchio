// ABOUTME: Excel-compatible YEARFRAC function implementation
// ABOUTME: Calculates year fractions between dates using various day count conventions

#![allow(clippy::unused_unit)]
#![allow(clippy::useless_conversion)]
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
    let mut start_date_series = inputs[0].clone();
    let mut end_date_series = inputs[1].clone();

    let basis = kwargs.basis.unwrap_or(BASIS_30_360_US);

    // Validate basis
    if !(BASIS_30_360_US..=BASIS_30_360_EU).contains(&basis) {
        return Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Must be 0, 1, 2, 3, or 4").into(),
        ));
    }

    // Convert datetime to date if needed (matching Excel behavior)
    // Debug: Print types before conversion
    let start_dtype = start_date_series.dtype().clone();
    let end_dtype = end_date_series.dtype().clone();
    
    match start_dtype.clone() {
        DataType::Datetime(_, _) => {
            // Try to cast datetime to date
            match start_date_series.cast(&DataType::Date) {
                Ok(series) => start_date_series = series,
                Err(e) => {
                    return Err(PolarsError::ComputeError(
                        format!("Failed to convert start datetime to date: {}", e).into(),
                    ));
                }
            }
        }
        DataType::List(inner) => {
            if let DataType::Datetime(_, _) = inner.as_ref() {
                // Convert List[Datetime] to List[Date]
                start_date_series = start_date_series.list()?.apply_amortized(|s| {
                    s.as_ref().cast(&DataType::Date).unwrap_or_else(|_| s.as_ref().clone())
                }).into_series();
            }
        }
        _ => {}
    }
    
    match end_dtype.clone() {
        DataType::Datetime(_, _) => {
            // Try to cast datetime to date
            match end_date_series.cast(&DataType::Date) {
                Ok(series) => end_date_series = series,
                Err(e) => {
                    return Err(PolarsError::ComputeError(
                        format!("Failed to convert end datetime to date: {}", e).into(),
                    ));
                }
            }
        }
        DataType::List(inner) => {
            if let DataType::Datetime(_, _) = inner.as_ref() {
                // Convert List[Datetime] to List[Date]
                end_date_series = end_date_series.list()?.apply_amortized(|s| {
                    s.as_ref().cast(&DataType::Date).unwrap_or_else(|_| s.as_ref().clone())
                }).into_series();
            }
        }
        _ => {}
    }

    // Handle different input types (scalar dates or list of dates)
    let final_start_dtype = start_date_series.dtype();
    let final_end_dtype = end_date_series.dtype();
    
    match (final_start_dtype, final_end_dtype) {
        (DataType::Date, DataType::Date) => {
            // Both are scalar dates
            let start_dates = start_date_series.date()?;
            let end_dates = end_date_series.date()?;
            yearfrac_scalar(start_dates, end_dates, basis)
        }
        (DataType::List(_), DataType::Date) => {
            // Start is list, end is scalar - broadcast end
            yearfrac_list_scalar(&start_date_series, &end_date_series, basis, false)
        }
        (DataType::Date, DataType::List(_)) => {
            // Start is scalar, end is list - broadcast start
            yearfrac_list_scalar(&end_date_series, &start_date_series, basis, true)
        }
        (DataType::List(_), DataType::List(_)) => {
            // Both are lists
            yearfrac_list_list(&start_date_series, &end_date_series, basis)
        }
        _ => {
            // Debug: show what types we actually have after conversion
            Err(PolarsError::ComputeError(
                format!(
                    "yearfrac requires Date or List[Date] inputs. After conversion, got {} (was {}) and {} (was {})",
                    final_start_dtype,
                    start_dtype,
                    final_end_dtype,
                    end_dtype
                )
                .into(),
            ))
        }
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
    let scalar_dates = scalar_series.date()?;

    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Iterate over both the list and scalar series together
    let result: ListChunked = list_ca
        .into_iter()
        .zip(scalar_dates.into_iter())
        .map(|(list_opt, scalar_date)| {
            if let Some(list_s) = list_opt {
                if let Ok(dates) = list_s.date() {
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
                    Some(result_ca.into_series())
                } else {
                    None
                }
            } else {
                None
            }
        })
        .collect();

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

    // First, validate that all list pairs have matching lengths
    for (idx, (start_opt, end_opt)) in start_list.into_iter().zip(end_list.into_iter()).enumerate() {
        if let (Some(start_s), Some(end_s)) = (start_opt, end_opt) {
            if start_s.len() != end_s.len() {
                return Err(PolarsError::ComputeError(
                    format!(
                        "List length mismatch at row {}: start has {} elements, end has {} elements. Lists must have the same length",
                        idx, start_s.len(), end_s.len()
                    ).into(),
                ));
            }
        }
    }

    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Valid epoch date");

    // Now process the lists, knowing they have matching lengths
    let result: ListChunked = start_list
        .into_iter()
        .zip(end_list)
        .map(|(start_opt, end_opt)| match (start_opt, end_opt) {
            (Some(start_s), Some(end_s)) => {
                let start_dates = start_s.date().ok()?;
                let end_dates = end_s.date().ok()?;

                let result_ca = start_dates
                    .into_iter()
                    .zip(end_dates.into_iter())
                    .map(|(start_d, end_d)| match (start_d, end_d) {
                        (Some(start_days), Some(end_days)) => {
                            let start_date = epoch + chrono::Duration::days(i64::from(start_days));
                            let end_date = epoch + chrono::Duration::days(i64::from(end_days));
                            Some(calculate_yearfrac(start_date, end_date, basis))
                        }
                        _ => None,
                    })
                    .collect::<Float64Chunked>();

                Some(result_ca.into_series())
            }
            _ => None,
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

    // Helper function to check if a type is a valid date/datetime type
    let is_valid_date_type = |dtype: &DataType| {
        matches!(dtype, DataType::Date | DataType::Datetime(_, _))
    };

    // Determine if output should be a list based on input types
    let is_list = matches!(start_type, DataType::List(_)) || matches!(end_type, DataType::List(_));

    // Validate input types
    let is_valid = match (start_type, end_type) {
        // Scalar types - both Date and Datetime are valid
        (DataType::Date, DataType::Date) 
        | (DataType::Datetime(_, _), DataType::Date) 
        | (DataType::Date, DataType::Datetime(_, _)) 
        | (DataType::Datetime(_, _), DataType::Datetime(_, _)) => true,
        
        // List types - check inner types
        (DataType::List(inner1), DataType::List(inner2)) => {
            is_valid_date_type(inner1.as_ref()) && is_valid_date_type(inner2.as_ref())
        }
        (DataType::List(inner), other) | (other, DataType::List(inner)) => {
            is_valid_date_type(inner.as_ref()) && is_valid_date_type(other)
        }
        
        _ => false,
    };

    if !is_valid {
        return Err(PolarsError::ComputeError(
            format!(
                "yearfrac requires Date/Datetime or List[Date/Datetime] inputs, got {} and {}",
                start_type, end_type
            )
            .into(),
        ));
    }

    let output_type = if is_list {
        DataType::List(Box::new(DataType::Float64))
    } else {
        DataType::Float64
    };

    Ok(Field::new("year_frac".into(), output_type))
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_yearfrac_output_type_accepts_datetime() {
        // Test that yearfrac_output_type accepts datetime inputs
        let datetime_field = Field::new("start".into(), DataType::Datetime(TimeUnit::Microseconds, None));
        let date_field = Field::new("end".into(), DataType::Date);
        
        let result = yearfrac_output_type(&[datetime_field.clone(), date_field.clone()]);
        assert!(result.is_ok(), "Should accept Datetime and Date combination");
        
        let result = yearfrac_output_type(&[datetime_field.clone(), datetime_field.clone()]);
        assert!(result.is_ok(), "Should accept Datetime and Datetime combination");
    }

    #[test]
    fn test_yearfrac_output_type_accepts_list_datetime() {
        // Test that yearfrac_output_type accepts List[Datetime] inputs
        let list_datetime_field = Field::new(
            "start".into(),
            DataType::List(Box::new(DataType::Datetime(TimeUnit::Microseconds, None)))
        );
        let list_date_field = Field::new(
            "end".into(),
            DataType::List(Box::new(DataType::Date))
        );
        
        let result = yearfrac_output_type(&[list_datetime_field.clone(), list_date_field.clone()]);
        assert!(result.is_ok(), "Should accept List[Datetime] and List[Date]");
        
        // Check output type is List[Float64]
        if let Ok(field) = result {
            assert_eq!(field.dtype, DataType::List(Box::new(DataType::Float64)));
        }
    }

    #[test]
    fn test_yearfrac_datetime_conversion_works() {
        // This test mimics what the Python test is trying to do
        use chrono::NaiveDateTime;
        
        // Create datetime values
        let datetime1 = NaiveDateTime::parse_from_str("2020-01-01 10:30:00", "%Y-%m-%d %H:%M:%S")
            .unwrap()
            .and_utc()
            .timestamp_micros();
        let datetime2 = NaiveDateTime::parse_from_str("2020-07-01 15:45:00", "%Y-%m-%d %H:%M:%S")
            .unwrap()
            .and_utc()
            .timestamp_micros();
        
        // Create series with datetime values
        let start_series = Series::new("start".into(), &[datetime1])
            .cast(&DataType::Datetime(TimeUnit::Microseconds, None))
            .unwrap();
        let end_series = Series::new("end".into(), &[datetime2])
            .cast(&DataType::Datetime(TimeUnit::Microseconds, None))
            .unwrap();
        
        // Test that yearfrac can handle datetime inputs
        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = yearfrac(&[start_series, end_series], &kwargs);
        
        assert!(result.is_ok(), "Should handle datetime inputs: {:?}", result.err());
        
        if let Ok(series) = result {
            let value = series.f64().unwrap().get(0).unwrap();
            // 2020-01-01 to 2020-07-01 is approximately 0.5 years
            assert!((value - 0.5).abs() < 0.01, "Expected ~0.5, got {}", value);
        }
    }

    #[test]
    fn test_yearfrac_list_length_mismatch_error() {
        // Create lists with mismatched lengths
        let date1 = NaiveDate::from_ymd_opt(2020, 1, 1).unwrap();
        let date2 = NaiveDate::from_ymd_opt(2020, 7, 1).unwrap();
        
        let days1 = (date1 - NaiveDate::from_ymd_opt(1970, 1, 1).unwrap()).num_days() as i32;
        let days2 = (date2 - NaiveDate::from_ymd_opt(1970, 1, 1).unwrap()).num_days() as i32;
        
        // Create inner series with different lengths
        let inner_start = Series::new("".into(), &[days1, days1])  // 2 elements
            .cast(&DataType::Date)
            .unwrap();
        let inner_end = Series::new("".into(), &[days2])  // 1 element
            .cast(&DataType::Date)
            .unwrap();
        
        // Create list series
        let start_list = ListChunked::from_iter([Some(inner_start)]).into_series();
        let end_list = ListChunked::from_iter([Some(inner_end)]).into_series();
        
        let kwargs = YearFracKwargs { basis: Some(0) };
        let result = yearfrac(&[start_list, end_list], &kwargs);
        
        assert!(result.is_err(), "Should error on mismatched list lengths");
        
        if let Err(e) = result {
            let error_msg = e.to_string();
            assert!(
                error_msg.contains("length") || error_msg.contains("mismatch"),
                "Error should mention length mismatch, got: {}",
                error_msg
            );
        }
    }
}
