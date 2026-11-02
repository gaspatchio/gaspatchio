// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Tests for Excel's ROUND over the 15-significant-digit decimal
// ABOUTME: Workbook values, decimal ties, near-ties, magnitudes, signs and the plugin

use super::round::*;
use polars::prelude::*;

/// Assert one rounding, bit for bit, so a sign of zero is part of the check.
fn assert_rounds(x: f64, num_digits: i32, expected: f64) {
    let got = excel_round(x, num_digits);
    assert_eq!(
        got.to_bits(),
        expected.to_bits(),
        "ROUND({x:?}, {num_digits}) answered {got:?}, Excel answers {expected:?}"
    );
}

#[test]
fn the_workbook_values_round_as_excel_does() {
    // UniversalLife.xlsx, 'Account Values -- Type B'!O19 = ROUND(1.5*K19, 2)
    // with K19 = 45366.20999999999 caches 68049.32. The double is
    // 68049.31499999999…; its fifteen digits are 68049.3150000000.
    assert_rounds(1.5 * 45366.20999999999, 2, 68049.32);
    // 0.5 * 161451.33 is 80725.665 in decimal, 80725.66499999999… as a double.
    assert_rounds(0.5 * 161451.33, 2, 80725.67);
    // 'Account Values -- Type A', row 74, column Q = ROUND((H-P)*3%, 2) with
    // column H = 5657268.499999999 and column P = 0 caches 169718.06.
    assert_rounds(5657268.499999999 * 0.03, 2, 169718.06);
}

#[test]
fn a_decimal_tie_goes_away_from_zero_for_either_sign() {
    assert_rounds(0.125, 2, 0.13);
    assert_rounds(-0.125, 2, -0.13);
    assert_rounds(7558.485, 2, 7558.49);
    assert_rounds(2.5, 0, 3.0);
    assert_rounds(-2.5, 0, -3.0);
    assert_rounds(0.5, 0, 1.0);
    assert_rounds(1.25, 1, 1.3);
    // Doubles just under their decimal: 2.67499999999999982…, 1.00499999999999989…
    assert_rounds(2.675, 2, 2.68);
    assert_rounds(1.005, 2, 1.01);
    assert_rounds(-1.005, 2, -1.01);
    assert_rounds(8.325, 2, 8.33);
    assert_rounds(1.15, 1, 1.2);
}

#[test]
fn a_value_just_below_a_half_in_binary_is_a_half_at_fifteen_digits() {
    // 0.49999999999999994 is the double below 0.5; fifteen digits read 0.5.
    assert_rounds(0.49999999999999994, 0, 1.0);
    assert_rounds(1.4999999999999998, 0, 2.0);
    // Below a half at the fifteenth digit stays below it.
    assert_rounds(0.004999999999999, 2, 0.0);
    assert_rounds(0.00499999999999, 2, 0.0);
}

#[test]
fn the_fifteen_digits_are_kept_past_the_double_s_own() {
    // 0.1 + 0.2 is 0.30000000000000004 as a double and 0.3 at fifteen digits.
    assert_rounds(0.1 + 0.2, 17, 0.3);
    assert_rounds(0.1 + 0.2, 2, 0.3);
}

#[test]
fn negative_digits_round_to_the_left_of_the_point() {
    assert_rounds(1250.0, -2, 1300.0);
    assert_rounds(-1250.0, -2, -1300.0);
    assert_rounds(1249.0, -2, 1200.0);
    assert_rounds(125.0, -1, 130.0);
    assert_rounds(44.95, -1, 40.0);
    // Every finite value is below half of 10^309.
    assert_rounds(1.7e308, -309, 0.0);
    assert_rounds(-1.7e308, -400, -0.0);
}

#[test]
fn magnitudes_past_fifteen_digits_answer_the_fifteen_digit_value() {
    // A sixteenth digit of 5 goes away from zero at the fifteenth.
    assert_rounds(12345678901234.25, 1, 12345678901234.3);
    assert_rounds(12345678901234.25, 2, 12345678901234.3);
    assert_rounds(1e15 + 0.5, 0, 1e15);
    assert_rounds(999_999_999_999_999.5, 0, 1e15);
    assert_rounds(123_456_789_012_345_678.0, 0, 1.23456789012346e17);
    assert_rounds(-123_456_789_012_345_678.0, -2, -1.23456789012346e17);
    // The largest double's fifteen digits are past it: it answers itself.
    assert_rounds(f64::MAX, 0, f64::MAX);
    assert_rounds(f64::MIN, 2, f64::MIN);
}

#[test]
fn signs_zeros_and_non_finite_values() {
    assert_rounds(-0.001, 2, -0.0);
    assert_rounds(0.0, 2, 0.0);
    assert_rounds(-0.0, 2, -0.0);
    assert_rounds(5e-324, 400, 5e-324);
    assert!(excel_round(f64::NAN, 2).is_nan());
    assert_rounds(f64::INFINITY, 2, f64::INFINITY);
    assert_rounds(f64::NEG_INFINITY, -2, f64::NEG_INFINITY);
}

#[test]
fn the_binary_path_and_the_decimal_path_agree_where_both_can_answer() {
    // Amounts in whole cents up to 100,000, plus three tenths of a cent (which
    // rounds down) or six tenths (which rounds up): far from a half, so the
    // binary path answers, and it answers what the decimal rule does.
    for cents in (0..10_000_000_i64).step_by(9_973) {
        let base = cents as f64 / 100.0;
        assert_rounds(base + 0.003, 2, cents as f64 / 100.0);
        assert_rounds(base + 0.006, 2, (cents + 1) as f64 / 100.0);
        assert_rounds(-(base + 0.006), 2, -((cents + 1) as f64 / 100.0));
    }
}

fn kwargs(num_digits: i32) -> ExcelRoundKwargs {
    ExcelRoundKwargs { num_digits }
}

#[test]
fn the_plugin_rounds_a_column_and_keeps_its_nulls() {
    let column = Series::new("x".into(), vec![Some(0.125), None, Some(-2.5)]);
    let out = excel_round_series(&[column], &kwargs(2)).unwrap();
    assert_eq!(out.dtype(), &DataType::Float64);
    let values: Vec<Option<f64>> = out.f64().unwrap().into_iter().collect();
    assert_eq!(values, vec![Some(0.13), None, Some(-2.5)]);
}

#[test]
fn the_plugin_rounds_a_list_column_element_wise() {
    let inners = vec![
        Series::new("".into(), vec![10.125, 1.5 * 45366.20999999999]),
        Series::new("".into(), Vec::<f64>::new()),
        Series::new("".into(), vec![0.005, -0.005]),
    ];
    let column = Series::new("coi".into(), inners);
    let out = excel_round_series(&[column], &kwargs(2)).unwrap();
    assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
    let rows: Vec<Vec<f64>> = out
        .list()
        .unwrap()
        .into_iter()
        .map(|row| row.unwrap().f64().unwrap().into_no_null_iter().collect())
        .collect();
    assert_eq!(rows, vec![vec![10.13, 68049.32], vec![], vec![0.01, -0.01]]);
}

#[test]
fn the_plugin_answers_doubles_for_whole_numbers_at_every_place() {
    // Section 11.1.35 states Float64 cells.
    let column = Series::new("n".into(), vec![1250_i64, -1249]);
    let kept = excel_round_series(&[column.clone()], &kwargs(2)).unwrap();
    assert_eq!(kept.dtype(), &DataType::Float64);
    assert_eq!(kept.f64().unwrap().get(0), Some(1250.0));
    let banded = excel_round_series(&[column], &kwargs(-2)).unwrap();
    assert_eq!(banded.dtype(), &DataType::Float64);
    let values: Vec<Option<f64>> = banded.f64().unwrap().into_iter().collect();
    assert_eq!(values, vec![Some(1300.0), Some(-1200.0)]);
}

#[test]
fn the_plugin_refuses_a_column_that_is_not_numbers() {
    let column = Series::new("x".into(), vec!["0.125"]);
    let refusal = excel_round_series(&[column], &kwargs(2)).unwrap_err();
    assert!(refusal.to_string().contains("excel.round rounds numbers"));
}

#[test]
fn the_output_type_follows_the_input() {
    let field = |dtype: DataType| Field::new("x".into(), dtype);
    let typed = |dtype: DataType, digits: i32| {
        excel_round_output_type(&[field(dtype)], &kwargs(digits))
            .unwrap()
            .dtype()
            .clone()
    };
    assert_eq!(typed(DataType::Float64, 2), DataType::Float64);
    assert_eq!(typed(DataType::Int64, 2), DataType::Float64);
    assert_eq!(typed(DataType::Int64, -1), DataType::Float64);
    assert_eq!(typed(DataType::Float32, 2), DataType::Float32);
    assert_eq!(
        typed(DataType::List(Box::new(DataType::Float64)), 2),
        DataType::List(Box::new(DataType::Float64))
    );
    assert!(excel_round_output_type(&[field(DataType::String)], &kwargs(2)).is_err());
}

#[test]
fn the_plugin_rounds_only_the_slice_of_a_list_column_it_is_handed() {
    // The streaming engine passes a slice whose inner values are the whole
    // column's; the answer is the slice's lists, and its values are its own.
    let inners: Vec<Series> = (0..4)
        .map(|row| Series::new("".into(), vec![row as f64 + 0.125, row as f64 + 0.375]))
        .collect();
    let column = Series::new("x".into(), inners).slice(1, 2);
    let out = excel_round_series(&[column], &kwargs(2)).unwrap();
    let rows: Vec<Vec<f64>> = out
        .list()
        .unwrap()
        .into_iter()
        .map(|row| row.unwrap().f64().unwrap().into_no_null_iter().collect())
        .collect();
    assert_eq!(rows, vec![vec![1.13, 1.38], vec![2.13, 2.38]]);
    assert_eq!(out.list().unwrap().get_inner().len(), 4);
}
