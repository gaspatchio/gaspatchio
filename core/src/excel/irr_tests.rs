// ABOUTME: Tests for the IRR Excel function implementation
// ABOUTME: Includes unit and behavior tests with list-column inputs

use super::irr::*;
use polars::prelude::*;

fn list_of_vecs_to_series(data: Vec<Vec<f64>>) -> Series {
    let inner: Vec<Series> = data
        .into_iter()
        .map(|v| Series::new("vals".into(), v))
        .collect();
    Series::new("values".into(), inner)
}

fn npv(rate: f64, values: &[f64]) -> f64 {
    let mut acc = 0.0;
    let denom = 1.0 + rate;
    let mut d = 1.0;
    for &v in values {
        acc += v / d;
        d *= denom;
    }
    acc
}

#[test]
fn test_vba_learn_example_bounds_and_npv() {
    // Microsoft Learn VBA IRR example flows; validate npv ~ 0 and reasonable rate range
    // https://learn.microsoft.com/en-us/office/vba/language/reference/user-interface-help/irr-function
    let values = vec![vec![-70000.0, 22000.0, 25000.0, 28000.0, 31000.0]];
    let s = list_of_vecs_to_series(values);
    let kwargs = IrrKwargs { guess: Some(0.1) };
    let out = irr(&[s], &kwargs).unwrap();
    let r = out.f64().unwrap().get(0).unwrap();

    // Validate NPV approximately zero at returned r
    let cf = vec![-70000.0, 22000.0, 25000.0, 28000.0, 31000.0];
    let npv_at_r = npv(r, &cf);
    assert!(npv_at_r.abs() < 1e-6);
    // Excel formats rate as percentage in example; ensure plausible range
    assert!(r > 0.15 && r < 0.30);
}

#[test]
fn test_numpy_financial_golden() {
    // Corroborated golden value from numpy-financial docs
    // https://github.com/numpy/numpy-financial/blob/main/numpy_financial/_financial.py
    let values = vec![vec![-100.0, 39.0, 59.0, 55.0, 20.0]];
    let s = list_of_vecs_to_series(values);
    let out = irr(&[s], &IrrKwargs { guess: Some(0.1) }).unwrap();
    let r = out.f64().unwrap().get(0).unwrap();
    // npf.irr([...]) ~= 0.28095
    assert!((r - 0.28095).abs() < 1e-4);
}

#[test]
fn test_sign_requirement() {
    // All positives should error (become null for the row)
    let values = vec![vec![100.0, 200.0, 50.0]];
    let s = list_of_vecs_to_series(values);
    let kwargs = IrrKwargs { guess: None };
    let out = irr(&[s], &kwargs).unwrap();
    assert!(out.f64().unwrap().get(0).is_none());
}

#[test]
fn test_multiple_rows_and_guess_broadcast() {
    let values = vec![
        vec![-100.0, 39.0, 59.0, 55.0, 20.0], // classic example ~0.2809
        vec![-1000.0, 300.0, 300.0, 300.0, 300.0, 300.0],
    ];
    let s = list_of_vecs_to_series(values);
    let kwargs = IrrKwargs { guess: Some(0.1) };
    let out = irr(&[s], &kwargs).unwrap();
    let c0 = out.f64().unwrap().get(0).unwrap();
    let c1 = out.f64().unwrap().get(1).unwrap();

    // NPV approximately zero for both rows
    let cf0 = vec![-100.0, 39.0, 59.0, 55.0, 20.0];
    let cf1 = vec![-1000.0, 300.0, 300.0, 300.0, 300.0, 300.0];
    assert!(npv(c0, &cf0).abs() < 1e-5);
    assert!(npv(c1, &cf1).abs() < 1e-5);
}

#[test]
fn test_per_row_guess_column() {
    let values = vec![vec![-100.0, 60.0, 60.0], vec![-100.0, 10.0, 200.0]];
    let s = list_of_vecs_to_series(values);
    let guess_series = Series::new("guess".into(), vec![0.1_f64, 0.5_f64]);
    let out = irr(&[s, guess_series], &IrrKwargs { guess: None }).unwrap();
    let r0 = out.f64().unwrap().get(0).unwrap();
    let r1 = out.f64().unwrap().get(1).unwrap();

    let cf0 = vec![-100.0, 60.0, 60.0];
    let cf1 = vec![-100.0, 10.0, 200.0];
    assert!(npv(r0, &cf0).abs() < 1e-5);
    assert!(npv(r1, &cf1).abs() < 1e-5);
}

#[test]
fn test_null_in_list_propagates() {
    let inner0 = Series::new("vals".into(), vec![Some(-100.0), None, Some(120.0)]);
    let inner1 = Series::new("vals".into(), vec![Some(-100.0), Some(60.0), Some(60.0)]);
    let s = Series::new("values".into(), vec![inner0, inner1]);

    let out = irr(&[s], &IrrKwargs { guess: Some(0.1) }).unwrap();
    let ca = out.f64().unwrap();
    assert!(ca.get(0).is_none());
    assert!(ca.get(1).is_some());
}

#[test]
fn test_output_type() {
    let field = Field::new("values".into(), DataType::List(Box::new(DataType::Float64)));
    let out = irr_output_type(&[field]).unwrap();
    assert_eq!(out.name().as_str(), "irr");
    assert_eq!(out.dtype(), &DataType::Float64);
}

#[test]
fn test_guess_sensitivity_multiple_sign_changes() {
    // Multiple sign changes can yield multiple IRRs; different guesses may converge differently
    // This test asserts both results have NPV close to zero and may differ
    let values = vec![vec![-100.0, 230.0, -132.0]];
    let s = list_of_vecs_to_series(values);

    let r1 = irr(std::slice::from_ref(&s), &IrrKwargs { guess: Some(0.05) })
        .unwrap()
        .f64()
        .unwrap()
        .get(0)
        .unwrap();
    let r2 = irr(&[s], &IrrKwargs { guess: Some(0.9) })
        .unwrap()
        .f64()
        .unwrap()
        .get(0)
        .unwrap();

    let cf = vec![-100.0, 230.0, -132.0];
    assert!(npv(r1, &cf).abs() < 1e-6);
    assert!(npv(r2, &cf).abs() < 1e-6);
    // It's acceptable for r1 and r2 to be different roots
    assert!((r1 - r2).abs() > 1e-6);
}
