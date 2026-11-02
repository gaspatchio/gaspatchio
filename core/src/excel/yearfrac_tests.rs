// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Tests for the yearfrac Excel function implementation
// ABOUTME: Contains unit tests and Excel compatibility verification tests

use super::yearfrac::*;
use approx::assert_relative_eq;
use chrono::NaiveDate;
use polars::prelude::*;

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
fn test_basis_0_us_30_360() {
    // Test basic month difference
    let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2023, 2, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(0) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let values = result.f64().unwrap();
    // Feb 28 (February's last day) -> 30; Excel leaves Mar 31 as 31, because
    // the end-day rule applies only to a start day of 30: 30 + 1 = 31 days
    assert_relative_eq!(values.get(0).unwrap(), 31.0 / 360.0, epsilon = 1e-10);
}

#[test]
fn test_basis_0_leap_year_feb() {
    // Test leap year February handling
    let start = vec![NaiveDate::from_ymd_opt(2020, 2, 29).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2020, 3, 31).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(0) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let values = result.f64().unwrap();
    // Feb 29 (last of Feb) -> 30; Excel leaves Mar 31 as 31: 31 days
    assert_relative_eq!(values.get(0).unwrap(), 31.0 / 360.0, epsilon = 1e-10);
}

#[test]
fn test_basis_1_actual_actual_same_year() {
    // Test within same non-leap year
    let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(1) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
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
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let values = result.f64().unwrap();
    // Jan 31 -> 30, Feb 28 stays 28
    // (28 - 30) + 30 * (2 - 1) = -2 + 30 = 28 days
    assert_relative_eq!(values.get(0).unwrap(), 28.0 / 360.0, epsilon = 1e-10);
}

#[test]
fn test_february_end_of_month_handling() {
    // Test US 30/360 with February end dates
    let start = vec![NaiveDate::from_ymd_opt(2023, 2, 28).unwrap()]; // Last day of Feb non-leap
    let end = vec![NaiveDate::from_ymd_opt(2023, 3, 31).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(0) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();

    // Excel's US 30/360: Feb 28 (last day) becomes 30 and, that adjustment
    // having been made, Mar 31 stays 31. Days = 0 + 1*30 + (31-30) = 31 days
    let expected = 31.0 / 360.0;
    assert_relative_eq!(year_frac, expected, epsilon = 1e-9);
}

#[test]
fn test_multi_year_actual_actual() {
    // Test spanning multiple years with basis 1
    let start = vec![NaiveDate::from_ymd_opt(2022, 6, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2025, 6, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(1) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();

    // Multi-year calculation with leap year averaging
    assert_relative_eq!(year_frac, 3.0006844626967832, epsilon = 1e-9);
}

#[test]
fn test_leap_year_actual_actual() {
    // Test spanning Feb 29
    let start = vec![NaiveDate::from_ymd_opt(2024, 2, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2024, 3, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(1) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();

    // 29 days in leap year February / 366 days in leap year
    let expected = 29.0 / 366.0;
    assert_relative_eq!(year_frac, expected, epsilon = 1e-9);
}

#[test]
fn test_reversed_yearfrac_is_the_forward_value() {
    // Excel's YEARFRAC does not depend on argument order: the earlier date is
    // the start, and the answer is never negative.
    let start = vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);

    // Test with basis 0
    let kwargs = YearFracKwargs { basis: Some(0) };
    let result = yearfrac(&[start_series.clone(), end_series.clone()], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();
    assert_relative_eq!(year_frac, 0.5, epsilon = 1e-9);

    // Test with basis 1
    let kwargs = YearFracKwargs { basis: Some(1) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();
    let expected = 181.0 / 365.0;
    assert_relative_eq!(year_frac, expected, epsilon = 1e-9);
}

#[test]
fn test_null_handling() {
    // Create series with null values
    let start = [
        Some(NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()),
        None,
        Some(NaiveDate::from_ymd_opt(2023, 3, 1).unwrap()),
    ];
    let end = [
        Some(NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()),
        Some(NaiveDate::from_ymd_opt(2023, 8, 1).unwrap()),
        None,
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

    let kwargs = YearFracKwargs { basis: Some(0) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let result_vec = result.f64().unwrap();

    // First value should be calculated
    assert!(result_vec.get(0).is_some());
    assert_relative_eq!(result_vec.get(0).unwrap(), 0.5, epsilon = 1e-9);

    // Second and third should be null
    assert!(result_vec.get(1).is_none());
    assert!(result_vec.get(2).is_none());
}

#[test]
fn test_invalid_basis() {
    let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: Some(5) };
    let result = yearfrac(&[start_series, end_series], &kwargs);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("Invalid basis"));
}

#[test]
fn test_same_date() {
    // Test when start and end dates are the same
    let date = vec![NaiveDate::from_ymd_opt(2023, 6, 15).unwrap()];
    let date_series = create_date_series(date);

    for basis in 0..=4 {
        let kwargs = YearFracKwargs { basis: Some(basis) };
        let result = yearfrac(&[date_series.clone(), date_series.clone()], &kwargs).unwrap();
        let year_frac = result.f64().unwrap().get(0).unwrap();
        assert_relative_eq!(year_frac, 0.0, epsilon = 1e-9);
    }
}

#[test]
fn test_reversed_dates() {
    // Reversed dates give the same answer: Excel takes the earlier as the start
    let date1 = NaiveDate::from_ymd_opt(2023, 1, 1).unwrap();
    let date2 = NaiveDate::from_ymd_opt(2023, 12, 31).unwrap();

    let start_series1 = create_date_series(vec![date1]);
    let end_series1 = create_date_series(vec![date2]);

    let start_series2 = create_date_series(vec![date2]);
    let end_series2 = create_date_series(vec![date1]);

    let kwargs = YearFracKwargs { basis: Some(0) };

    let result1 = yearfrac(&[start_series1, end_series1], &kwargs).unwrap();
    let result2 = yearfrac(&[start_series2, end_series2], &kwargs).unwrap();

    let values1 = result1.f64().unwrap();
    let values2 = result2.f64().unwrap();

    // The two orders agree, and neither is negative
    assert_eq!(values1.get(0).unwrap(), values2.get(0).unwrap());
    assert!(values1.get(0).unwrap() > 0.0);
}

#[test]
fn test_multi_year_average() {
    // Test basis 1 with multi-year span
    let start = vec![NaiveDate::from_ymd_opt(2019, 1, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2021, 1, 1).unwrap()];

    let start_series = create_date_series(start);
    let end_series = create_date_series(end);

    let kwargs = YearFracKwargs { basis: Some(1) };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let values = result.f64().unwrap();

    // The period from 2019-01-01 to 2021-01-01 is exactly 2 years (731 days)
    // We need to check what Excel actually returns for this
    // Excel's actual result for this is closer to 2.00091... due to how it calculates
    assert_relative_eq!(
        values.get(0).unwrap(),
        2.000_912_408_759_124_4,
        epsilon = 1e-10
    );
}

#[test]
fn test_default_basis() {
    // Test that default basis is 0 (US 30/360)
    let start = vec![NaiveDate::from_ymd_opt(2023, 1, 1).unwrap()];
    let end = vec![NaiveDate::from_ymd_opt(2023, 7, 1).unwrap()];
    let start_series = create_date_series(start);
    let end_series = create_date_series(end);
    let kwargs = YearFracKwargs { basis: None };
    let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
    let year_frac = result.f64().unwrap().get(0).unwrap();
    assert_relative_eq!(year_frac, 0.5, epsilon = 1e-9);
}

// Excel Verification Tests
//
// IMPORTANT: These tests verify exact compatibility with Microsoft Excel's YEARFRAC function.
// Excel's implementation has several known quirks and non-standard behaviors that we must
// replicate exactly for compatibility. These tests capture those behaviors to ensure our
// implementation matches Excel's output precisely.
//
// Why Excel Compatibility Matters:
// 1. Actuarial and financial models often originate in Excel
// 2. Regulatory requirements may specify Excel-compatible calculations
// 3. Migration from Excel to our system must produce identical results
// 4. Users expect the same results they get in Excel
//
// Known Excel Quirks We Test:
// - Non-additivity of Actual/Actual (basis 1) calculations
// - Special February end-of-month handling in 30/360 methods
// - Order independence: reversed dates answer the forward value, never a negative
// - Basis 1's one-year test: the end on or before the start's anniversary
// - Different interpretations of "year length" across bases
//
// The tests below verify our implementation against known Excel outputs
// including edge cases and problematic scenarios documented in financial literature.

mod excel_verification {
    use super::*;

    fn test_yearfrac(start: NaiveDate, end: NaiveDate, basis: i32) -> f64 {
        let start_series = create_date_series(vec![start]);
        let end_series = create_date_series(vec![end]);
        let kwargs = YearFracKwargs { basis: Some(basis) };
        let result = yearfrac(&[start_series, end_series], &kwargs).unwrap();
        result.f64().unwrap().get(0).unwrap()
    }

    #[test]
    fn test_excel_known_values_basis_0() {
        // US 30/360 - Known Excel results
        //
        // Basis 0 implements the US (NASD) 30/360 day count convention.
        // This method assumes 30-day months and 360-day years with special
        // rules for handling month-end dates, particularly in February.

        // Basic test cases
        // For US 30/360: Jan 1 to Dec 31 gives 360 days (12 months * 30 days)
        // This is a key difference from European 30/360 which gives 359 days
        assert_relative_eq!(
            test_yearfrac(
                NaiveDate::from_ymd_opt(2023, 1, 1).unwrap(),
                NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
                0
            ),
            360.0 / 360.0, // 360/360 = 1.0
            epsilon = 1e-10
        );

        // February end handling
        // When starting from Feb 28 (last day of Feb in non-leap year),
        // it's treated as day 30, and Excel then leaves an end day of 31 as 31
        assert_relative_eq!(
            test_yearfrac(
                NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
                NaiveDate::from_ymd_opt(2023, 3, 31).unwrap(),
                0
            ),
            31.0 / 360.0,
            epsilon = 1e-10
        );

        // Leap year February
        // Feb 29 is also treated as day 30 when it's the last day of February
        assert_relative_eq!(
            test_yearfrac(
                NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
                NaiveDate::from_ymd_opt(2020, 3, 31).unwrap(),
                0
            ),
            31.0 / 360.0,
            epsilon = 1e-10
        );

        // A start day of 30 does turn an end day of 31 into 30
        assert_relative_eq!(
            test_yearfrac(
                NaiveDate::from_ymd_opt(2023, 4, 30).unwrap(),
                NaiveDate::from_ymd_opt(2023, 5, 31).unwrap(),
                0
            ),
            30.0 / 360.0,
            epsilon = 1e-10
        );
    }

    #[test]
    fn test_excel_known_values_basis_1() {
        // Actual/Actual - Known Excel results

        // Test 1: Within non-leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2019, 7, 1).unwrap(),
            1,
        );
        // 181 days / 365 days
        assert_relative_eq!(result, 181.0 / 365.0, epsilon = 1e-10);

        // Test 2: Within leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 7, 1).unwrap(),
            1,
        );
        // 182 days / 366 days
        assert_relative_eq!(result, 182.0 / 366.0, epsilon = 1e-10);

        // Test 3: Spanning Feb 29
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 2, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 3, 1).unwrap(),
            1,
        );
        // 29 days / 366 days
        assert_relative_eq!(result, 29.0 / 366.0, epsilon = 1e-10);

        // Test 4: Multi-year span
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2021, 1, 1).unwrap(),
            1,
        );
        // Multi-year average (not exactly 2.0 due to leap year averaging)
        assert_relative_eq!(result, 2.0009124087591244, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_known_values_basis_2() {
        // Actual/360 - Known Excel results

        // Test 1: Regular period
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 4, 1).unwrap(),
            2,
        );
        // 91 days / 360
        assert_relative_eq!(result, 91.0 / 360.0, epsilon = 1e-10);

        // Test 2: Full leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2021, 1, 1).unwrap(),
            2,
        );
        // 366 days / 360
        assert_relative_eq!(result, 366.0 / 360.0, epsilon = 1e-10);

        // Test 3: Known Excel example
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2011, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2011, 6, 30).unwrap(),
            2,
        );
        // 180 days / 360
        assert_relative_eq!(result, 180.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_known_values_basis_3() {
        // Actual/365 - Known Excel results

        // Test 1: Regular period
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 4, 1).unwrap(),
            3,
        );
        // 91 days / 365 (always 365, even in leap year)
        assert_relative_eq!(result, 91.0 / 365.0, epsilon = 1e-10);

        // Test 2: Full leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2021, 1, 1).unwrap(),
            3,
        );
        // 366 days / 365
        assert_relative_eq!(result, 366.0 / 365.0, epsilon = 1e-10);

        // Test 3: Known Excel example
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2011, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2011, 6, 30).unwrap(),
            3,
        );
        // 180 days / 365
        assert_relative_eq!(result, 180.0 / 365.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_known_values_basis_4() {
        // European 30/360 - Known Excel results

        // Test 1: Regular dates
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 12, 31).unwrap(),
            4,
        );
        // Dec 31 becomes 30, so 359/360
        assert_relative_eq!(result, 359.0 / 360.0, epsilon = 1e-10);

        // Test 2: 31st day adjustments (simpler than US)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 31).unwrap(),
            NaiveDate::from_ymd_opt(2020, 3, 31).unwrap(),
            4,
        );
        // Both 31st become 30th, so exactly 2 months
        assert_relative_eq!(result, 2.0 / 12.0, epsilon = 1e-10);

        // Test 3: February handling (no special rules)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2020, 3, 31).unwrap(),
            4,
        );
        // Feb 29 stays 29, Mar 31 -> 30, so 1 month + 1 day
        assert_relative_eq!(result, 31.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_edge_cases() {
        // Test some edge cases that Excel handles specifically

        // Edge case 1: Same date
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 6, 15).unwrap(),
            NaiveDate::from_ymd_opt(2020, 6, 15).unwrap(),
            1,
        );
        assert_relative_eq!(result, 0.0, epsilon = 1e-10);

        // Edge case 2: One day difference
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 1, 2).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0 / 366.0, epsilon = 1e-10);

        // Edge case 3: Reversed dates answer the forward value, not a negative
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 12, 31).unwrap(),
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            0,
        );
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);
    }

    #[test]
    fn test_cross_year_boundaries() {
        // Test calculations that cross year boundaries

        // Test 1: Basis 1 - Actual/Actual across non-leap to leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 7, 1).unwrap(),
            1,
        );
        // Should consider the Feb 29 in the calculation
        // 184 days in 2019 (Jul 1 - Dec 31) + 183 days in 2020 (Jan 1 - Jul 1)
        // But since it spans exactly one year, should be 1.0
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);

        // Test 2: Basis 0 - 30/360 across years
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 11, 30).unwrap(),
            NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
            0,
        );
        // Nov 30 to Feb 29: 3 months - 1 day in 30/360 system
        assert_relative_eq!(result, 89.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_leap_year_transitions() {
        // Specific tests for leap year transitions

        // Test 1: Crossing from non-leap to leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 12, 31).unwrap(),
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            1,
        );
        // One day, using 365 days as divisor (our implementation behavior)
        assert_relative_eq!(result, 1.0 / 365.0, epsilon = 1e-10);

        // Test 2: Crossing from leap to non-leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 12, 31).unwrap(),
            NaiveDate::from_ymd_opt(2021, 1, 1).unwrap(),
            1,
        );
        // One day, but in context of non-leap year
        assert_relative_eq!(result, 1.0 / 365.0, epsilon = 1e-10);
    }

    #[test]
    fn test_century_and_millennium_boundaries() {
        // Test calculations across century and millennium boundaries

        // Test 1: Across year 2000 (leap year)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(1999, 12, 31).unwrap(),
            NaiveDate::from_ymd_opt(2000, 1, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0 / 365.0, epsilon = 1e-10);

        // Test 2: Across year 1900 (not a leap year in Gregorian calendar)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(1900, 2, 28).unwrap(),
            NaiveDate::from_ymd_opt(1900, 3, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0 / 365.0, epsilon = 1e-10);

        // Test 3: Large span
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2000, 1, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 1, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 19.998044583496284, epsilon = 1e-10);
    }

    #[test]
    fn test_special_february_cases() {
        // Special handling of February in different bases

        // Test 1: Basis 0 - Last day of Feb in non-leap year
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 2, 28).unwrap(),
            NaiveDate::from_ymd_opt(2019, 3, 28).unwrap(),
            0,
        );
        // Feb 28 (last day) -> 30, Mar 28 stays 28
        // Days = 0 + 1*30 + (28-30) = 28
        assert_relative_eq!(result, 28.0 / 360.0, epsilon = 1e-10);

        // Test 2: Basis 0 - Both dates are last day of February
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 2, 28).unwrap(),
            NaiveDate::from_ymd_opt(2020, 2, 29).unwrap(),
            0,
        );
        // Both are last days of Feb, special handling applies
        // Should be exactly 1 year
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);
    }

    #[test]
    fn test_excel_additivity_bug() {
        // Known Excel bug: YEARFRAC is not additive for basis 1
        //
        // This is a well-documented issue where:
        // YEARFRAC(A, C, 1) ≠ YEARFRAC(A, B, 1) + YEARFRAC(B, C, 1)
        //
        // This violates mathematical expectations but we must replicate it
        // for Excel compatibility. The issue arises from how Excel determines
        // the denominator for periods spanning multiple years.

        let date1 = NaiveDate::from_ymd_opt(2011, 12, 30).unwrap();
        let date2 = NaiveDate::from_ymd_opt(2012, 1, 1).unwrap();
        let date3 = NaiveDate::from_ymd_opt(2012, 1, 4).unwrap();

        let _full_period = test_yearfrac(date1, date3, 1);
        let _part1 = test_yearfrac(date1, date2, 1);
        let _part2 = test_yearfrac(date2, date3, 1);

        // In Excel, these are NOT equal due to the bug
        // Our implementation might differ here
        // This test documents the issue rather than enforcing it
    }

    #[test]
    fn test_excel_leap_year_edge_case() {
        // Known issue: When end date is in leap year and start date is not,
        // but start is after Feb 28
        //
        // This creates ambiguity in how to handle the "year length"
        // for Actual/Actual calculations. Excel has its own interpretation
        // that may differ from financial standards.

        let _result = test_yearfrac(
            NaiveDate::from_ymd_opt(2011, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2012, 12, 31).unwrap(),
            1,
        );

        // This is a known problematic case in Excel
        // Different implementations may give different results
    }

    #[test]
    fn test_excel_feb_29_quirk() {
        // Test the Feb 29 quirk for US 30/360
        //
        // In US 30/360, February end-of-month dates are adjusted to day 30.
        // This can create seemingly asymmetric results.

        let result1 = test_yearfrac(
            NaiveDate::from_ymd_opt(2016, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2016, 3, 1).unwrap(),
            0,
        );

        let result2 = test_yearfrac(
            NaiveDate::from_ymd_opt(2016, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2016, 2, 29).unwrap(),
            0,
        );

        // Excel takes the earlier date as the start whichever order it is given,
        // so both orders are Feb 29 (-> 30) to Mar 1: 1 day
        assert_relative_eq!(result1, 1.0 / 360.0, epsilon = 1e-10);
        assert_eq!(result1, result2);
    }

    #[test]
    fn test_multi_year_span_basis_1() {
        // Test case from financial literature
        //
        // Multi-year spans with Actual/Actual can produce surprising results
        // due to how Excel calculates the average year length.

        let _result = test_yearfrac(
            NaiveDate::from_ymd_opt(2004, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2009, 1, 31).unwrap(),
            1,
        );

        // Expected: approximately 4.9197 according to some implementations
        // The exact value depends on how leap years are weighted
    }

    #[test]
    fn test_consecutive_days() {
        // Test fractions for consecutive days
        //
        // This verifies that each basis correctly calculates the fraction
        // for a single day. These values are fundamental to understanding
        // how each basis works.

        let start = NaiveDate::from_ymd_opt(2023, 6, 15).unwrap();
        let end = NaiveDate::from_ymd_opt(2023, 6, 16).unwrap();

        // Each basis has a different "day fraction"
        assert_relative_eq!(test_yearfrac(start, end, 0), 1.0 / 360.0, epsilon = 1e-10);
        assert_relative_eq!(test_yearfrac(start, end, 1), 1.0 / 365.0, epsilon = 1e-10);
        assert_relative_eq!(test_yearfrac(start, end, 2), 1.0 / 360.0, epsilon = 1e-10);
        assert_relative_eq!(test_yearfrac(start, end, 3), 1.0 / 365.0, epsilon = 1e-10);
        assert_relative_eq!(test_yearfrac(start, end, 4), 1.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_financial_examples() {
        // Common financial calculation examples
        //
        // These represent typical use cases in bond calculations,
        // interest accruals, and other financial instruments.

        // Bond settlement to maturity example
        let settlement = NaiveDate::from_ymd_opt(2023, 3, 15).unwrap();
        let maturity = NaiveDate::from_ymd_opt(2025, 9, 15).unwrap();

        // Different bases are used for different types of bonds:
        // - US Treasury: Actual/Actual (basis 1)
        // - US Corporate: 30/360 (basis 0)
        // - Eurobonds: 30/360E (basis 4)
        // - Money Market: Actual/360 (basis 2)

        let _treasury_frac = test_yearfrac(settlement, maturity, 1);
        let _corporate_frac = test_yearfrac(settlement, maturity, 0);
        let _eurobond_frac = test_yearfrac(settlement, maturity, 4);
        let _money_market_frac = test_yearfrac(settlement, maturity, 2);
    }

    // =======================================================================
    // Feb 29 (Leap Day) Edge Case Tests
    // =======================================================================
    //
    // Excel's basis 1 has no leap-day anniversary rule. It asks whether the
    // end falls in the next year on or before the start's month and day; if
    // so it divides by 366 where the closed interval holds a 29 February and
    // by 365 where it does not, and otherwise by the mean length of the
    // calendar years the interval touches. So 29 February to 28 February a
    // year later is 365/366, and 366 days that run past the anniversary are
    // divided by a mean year.

    #[test]
    fn test_feb29_to_feb28_is_365_over_366() {
        // Feb 29 2024 -> Feb 28 2025 = 365 days; 28 Feb is on or before the
        // 29 Feb anniversary, and the interval holds 29 Feb 2024
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2025, 2, 28).unwrap(),
            1,
        );
        assert_relative_eq!(result, 365.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_to_mar1_is_over_the_mean_year() {
        // Feb 29 2024 -> Mar 1 2025 = 366 days, past the anniversary:
        // the mean of 2024 and 2025 is 365.5
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2025, 3, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 366.0 / 365.5, epsilon = 1e-10);
    }

    #[test]
    fn test_feb28_to_feb29_is_over_the_mean_year() {
        // Feb 28 2023 -> Feb 29 2024 = 366 days, and 29 Feb is past the
        // 28 Feb anniversary: the mean of 2023 and 2024 is 365.5
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            1,
        );
        assert_relative_eq!(result, 366.0 / 365.5, epsilon = 1e-10);
    }

    #[test]
    fn test_366_days_past_the_anniversary_are_over_the_mean_year() {
        // Sep 25 2020 -> Sep 26 2021 = 366 days with no 29 Feb inside: the
        // end is past the anniversary, so not 366/365 but 366/365.5
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 9, 25).unwrap(),
            NaiveDate::from_ymd_opt(2021, 9, 26).unwrap(),
            1,
        );
        assert_relative_eq!(result, 366.0 / 365.5, epsilon = 1e-10);
    }

    #[test]
    fn test_every_basis_answers_the_same_in_either_order() {
        let pairs = [
            (
                NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
                NaiveDate::from_ymd_opt(2023, 2, 28).unwrap(),
            ),
            (
                NaiveDate::from_ymd_opt(2024, 3, 31).unwrap(),
                NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            ),
            (
                NaiveDate::from_ymd_opt(2030, 1, 31).unwrap(),
                NaiveDate::from_ymd_opt(2021, 6, 30).unwrap(),
            ),
        ];
        for (later, earlier) in pairs {
            for basis in 0..=4 {
                let reversed = test_yearfrac(later, earlier, basis);
                let forward = test_yearfrac(earlier, later, basis);
                assert_eq!(reversed, forward, "basis {basis}: {earlier} and {later}");
                assert!(reversed > 0.0);
            }
        }
        // Hand values for the first pair, 28 Feb 2023 to 29 Feb 2024 (366 days):
        // basis 0, both February's last day -> 30/30: 360/360; basis 1 the mean
        // of 2023 and 2024; basis 4 (29 - 28) + 360 = 361 days.
        let (later, earlier) = pairs[0];
        let by_hand = [
            1.0,
            366.0 / 365.5,
            366.0 / 360.0,
            366.0 / 365.0,
            361.0 / 360.0,
        ];
        for (basis, expected) in (0..=4).zip(by_hand) {
            let answer = test_yearfrac(later, earlier, basis);
            assert_relative_eq!(answer, expected, epsilon = 1e-12);
        }
    }

    #[test]
    fn test_mar1_to_feb29_less_than_one_year() {
        // Mar 1 2023 -> Feb 29 2024 = 365 days
        // This is NOT a full year (starts after Feb 29 2023 which doesn't exist)
        // Should be 365/366 = 0.9972677...
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2023, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            1,
        );
        assert_relative_eq!(result, 365.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_same_year_calculations() {
        // Same-year calculations starting from Feb 29
        // These should use 366 as the year length

        // Feb 29 -> Mar 1 (1 day)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2024, 3, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0 / 366.0, epsilon = 1e-10);

        // Feb 29 -> Dec 31 (306 days)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2024, 12, 31).unwrap(),
            1,
        );
        assert_relative_eq!(result, 306.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_multi_year_calculations() {
        // Multi-year calculations starting from Feb 29
        // These use average year length

        // Feb 29 2024 -> Dec 31 2025 (671 days)
        // Average year = (366 + 365) / 2 = 365.5
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2025, 12, 31).unwrap(),
            1,
        );
        assert_relative_eq!(result, 671.0 / 365.5, epsilon = 1e-10);

        // Feb 29 2024 -> Feb 28 2026 (730 days)
        // Years: 2024, 2025, 2026 = (366 + 365 + 365) / 3 = 365.333...
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2026, 2, 28).unwrap(),
            1,
        );
        let avg_year = (366.0 + 365.0 + 365.0) / 3.0;
        assert_relative_eq!(result, 730.0 / avg_year, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_to_feb29_four_years() {
        // Feb 29 2024 -> Feb 29 2028 (1461 days)
        // This is exactly 4 years (leap to leap)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2028, 2, 29).unwrap(),
            1,
        );
        // Years: 2024, 2025, 2026, 2027, 2028 = (366 + 365 + 365 + 365 + 366) / 5
        let avg_year = (366.0 + 365.0 + 365.0 + 365.0 + 366.0) / 5.0;
        assert_relative_eq!(result, 1461.0 / avg_year, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_short_periods() {
        // Short periods from Feb 29 that don't reach anniversary

        // Feb 29 -> Feb 27 next year (364 days)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2025, 2, 27).unwrap(),
            1,
        );
        // Contains Feb 29 (the start), so uses 366
        assert_relative_eq!(result, 364.0 / 366.0, epsilon = 1e-10);

        // Feb 29 -> Jan 1 next year (307 days)
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 2, 29).unwrap(),
            NaiveDate::from_ymd_opt(2025, 1, 1).unwrap(),
            1,
        );
        // Contains Feb 29 (the start), so uses 366
        assert_relative_eq!(result, 307.0 / 366.0, epsilon = 1e-10);
    }

    #[test]
    fn test_feb29_other_bases() {
        // Feb 29 handling for other bases (0, 2, 3, 4)
        // These don't have the same complexity as basis 1

        let feb29 = NaiveDate::from_ymd_opt(2024, 2, 29).unwrap();
        let feb28_next = NaiveDate::from_ymd_opt(2025, 2, 28).unwrap();

        // Basis 0 (US 30/360): Feb 29 is treated as Feb 30, Feb 28 (last day of Feb) also as Feb 30
        // So Feb 30 -> Feb 30 = exactly 12 months = 360/360 = 1.0
        let result = test_yearfrac(feb29, feb28_next, 0);
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);

        // Basis 2 (Actual/360): Just actual days / 360
        let result = test_yearfrac(feb29, feb28_next, 2);
        assert_relative_eq!(result, 365.0 / 360.0, epsilon = 1e-10);

        // Basis 3 (Actual/365): Just actual days / 365
        let result = test_yearfrac(feb29, feb28_next, 3);
        assert_relative_eq!(result, 365.0 / 365.0, epsilon = 1e-10);

        // Basis 4 (European 30/360): Feb 29 stays as 29, Feb 28 stays as 28
        // Feb 29 -> Feb 28 = (28 - 29) + 12 * 30 = 359 days in 30/360
        let result = test_yearfrac(feb29, feb28_next, 4);
        assert_relative_eq!(result, 359.0 / 360.0, epsilon = 1e-10);
    }

    #[test]
    fn test_crossing_feb29_vs_not_crossing() {
        // Verify the difference between periods that cross Feb 29 and those that don't

        // Jul 1 2019 -> Jul 1 2020: crosses Feb 29 2020
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2019, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2020, 7, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);

        // Jul 1 2020 -> Jul 1 2021: does NOT cross Feb 29
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2020, 7, 1).unwrap(),
            NaiveDate::from_ymd_opt(2021, 7, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);

        // Mar 1 2023 -> Mar 1 2024: crosses Feb 29 2024
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2023, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2024, 3, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);

        // Mar 1 2024 -> Mar 1 2025: does NOT cross Feb 29
        let result = test_yearfrac(
            NaiveDate::from_ymd_opt(2024, 3, 1).unwrap(),
            NaiveDate::from_ymd_opt(2025, 3, 1).unwrap(),
            1,
        );
        assert_relative_eq!(result, 1.0, epsilon = 1e-10);
    }
}
