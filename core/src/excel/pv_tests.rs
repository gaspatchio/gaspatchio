// ABOUTME: Tests for the PV Excel function implementation
// ABOUTME: Covers scalar and list cases, edge cases, and output typing

use super::pv::*;
use approx::assert_relative_eq;
use polars::prelude::*;

fn s(v: &[f64]) -> Series {
    Series::new("x".into(), v.to_vec())
}

fn s_opt(v: &[Option<f64>]) -> Series {
    Series::new("x".into(), v.to_vec())
}

fn l(vs: Vec<Vec<f64>>) -> Series {
    let inners: Vec<Series> = vs.into_iter().map(|v| Series::new("".into(), v)).collect();
    Series::new("list".into(), inners)
}

#[test]
fn test_known_values_end_type() {
    // Example: rate=10%, nper=3, pmt=100, fv=0, type=0
    let rate = s(&[0.10]);
    let nper = s(&[3.0]);
    let pmt = s(&[100.0]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let out = pv(&[rate, nper, pmt], &kwargs).unwrap();
    let val = out.f64().unwrap().get(0).unwrap();
    // Hand-computed
    let expected = -((100.0_f64
        * (1.0_f64 + 0.10_f64 * 0.0_f64)
        * (1.0_f64 - (1.0_f64 + 0.10_f64).powf(-3.0_f64))
        / 0.10_f64)
        + 0.0_f64 * (1.0_f64 + 0.10_f64).powf(-3.0_f64));
    assert_relative_eq!(val, expected, epsilon = 1e-12);
}

#[test]
fn test_rate_zero() {
    let rate = s(&[0.0]);
    let nper = s(&[5.0]);
    let pmt = s(&[200.0]);
    let kwargs = PvKwargs {
        fv: Some(1000.0),
        typ: Some(0),
    };
    let out = pv(&[rate, nper, pmt], &kwargs).unwrap();
    let val = out.f64().unwrap().get(0).unwrap();
    assert_relative_eq!(val, -(200.0 * 5.0 + 1000.0), epsilon = 1e-12);
}

#[test]
fn test_type_beginning() {
    let rate = s(&[0.05]);
    let nper = s(&[10.0]);
    let pmt = s(&[100.0]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(1),
    };
    let out = pv(&[rate, nper, pmt], &kwargs).unwrap();
    let val = out.f64().unwrap().get(0).unwrap();
    // Compare with explicit formula
    let expected = -((100.0_f64
        * (1.0_f64 + 0.05_f64 * 1.0_f64)
        * (1.0_f64 - (1.0_f64 + 0.05_f64).powf(-10.0_f64))
        / 0.05_f64)
        + 0.0_f64 * (1.0_f64 + 0.05_f64).powf(-10.0_f64));
    assert_relative_eq!(val, expected, epsilon = 1e-12);
}

#[test]
fn test_pv_monthly_type0_and_type1_identity() {
    // Excel monthly-style inputs: convert annual rate to monthly, multiply nper by months
    // Validate identity holds for type 0 and 1
    let rate_month = s(&[0.12_f64 / 12.0]);
    let nper_months = s(&[360.0_f64]);
    let pmt = s(&[-1000.0_f64]);

    // type 0
    let out0 = pv(&[rate_month.clone(), nper_months.clone(), pmt.clone()], &PvKwargs { fv: Some(0.0), typ: Some(0) }).unwrap();
    let v0 = out0.f64().unwrap().get(0).unwrap();
    let r = 0.12_f64 / 12.0;
    let n = 360.0;
    let p = -1000.0;
    let a = (1.0 - (1.0 + r).powf(-n)) / r;
    let lhs0 = v0 + p * (1.0 + r * 0.0) * a + 0.0 * (1.0 + r).powf(-n);
    assert!(lhs0.abs() < 1e-9);

    // type 1
    let out1 = pv(&[rate_month, nper_months, pmt], &PvKwargs { fv: Some(0.0), typ: Some(1) }).unwrap();
    let v1 = out1.f64().unwrap().get(0).unwrap();
    let lhs1 = v1 + p * (1.0 + r * 1.0) * a + 0.0 * (1.0 + r).powf(-n);
    assert!(lhs1.abs() < 1e-9);
}

#[test]
fn test_sign_convention() {
    // Positive pmt yields negative PV
    let rate = s(&[0.10]);
    let nper = s(&[3.0]);
    let pmt = s(&[100.0]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let out = pv(&[rate.clone(), nper.clone(), pmt], &kwargs).unwrap();
    assert!(out.f64().unwrap().get(0).unwrap() < 0.0);

    // Negative pmt yields positive PV
    let pmt2 = s(&[-100.0]);
    let out2 = pv(&[rate, nper, pmt2], &kwargs).unwrap();
    assert!(out2.f64().unwrap().get(0).unwrap() > 0.0);
}

#[test]
fn test_list_times_list() {
    let rates = l(vec![vec![0.05, 0.05], vec![0.10]]);
    let npers = l(vec![vec![10.0, 5.0], vec![3.0]]);
    let pmts = l(vec![vec![100.0, 200.0], vec![50.0]]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let out = pv(&[rates, npers, pmts], &kwargs).unwrap();
    let lc = out.list().unwrap();
    assert_eq!(lc.len(), 2);

    let first = lc.get_as_series(0).unwrap();
    let a = first.f64().unwrap().get(0).unwrap();
    let b = first.f64().unwrap().get(1).unwrap();

    let second = lc.get_as_series(1).unwrap();
    let c = second.f64().unwrap().get(0).unwrap();

    assert!(a.is_finite() && b.is_finite() && c.is_finite());
}

#[test]
fn test_scalar_times_list_broadcast() {
    let rate = s(&[0.05]);
    let nper = s(&[10.0]);
    let pmt_list = l(vec![vec![100.0, 200.0, 300.0]]);
    let kwargs = PvKwargs {
        fv: None,
        typ: None,
    };
    let out = pv(&[rate, nper, pmt_list], &kwargs).unwrap();
    let inner = out.list().unwrap().get_as_series(0).unwrap();
    assert_eq!(inner.len(), 3);
}

#[test]
fn test_list_times_scalar_broadcast() {
    let rate_list = l(vec![vec![0.01, 0.02, 0.03]]);
    let nper = s(&[12.0]);
    let pmt = s(&[100.0]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(1),
    };
    let out = pv(&[rate_list, nper, pmt], &kwargs).unwrap();
    let inner = out.list().unwrap().get_as_series(0).unwrap();
    assert_eq!(inner.len(), 3);
}

#[test]
fn test_null_handling() {
    let rate = s_opt(&[Some(0.05), None, Some(0.10)]);
    let nper = s_opt(&[Some(10.0), Some(5.0), None]);
    let pmt = s_opt(&[Some(100.0), Some(200.0), Some(50.0)]);
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let out = pv(&[rate, nper, pmt], &kwargs).unwrap();
    let ca = out.f64().unwrap();
    assert!(ca.get(0).unwrap().is_finite());
    assert!(ca.get(1).is_none());
    assert!(ca.get(2).is_none());
}

#[test]
fn test_output_type_function() {
    let f_rate = Field::new("rate".into(), DataType::Float64);
    let f_nper = Field::new("nper".into(), DataType::Float64);
    let f_pmt = Field::new("pmt".into(), DataType::Float64);
    let out = pv_output_type(&[f_rate.clone(), f_nper.clone(), f_pmt.clone()]).unwrap();
    assert_eq!(out.dtype, DataType::Float64);

    let f_rate_l = Field::new("rate".into(), DataType::List(Box::new(DataType::Float64)));
    let out2 = pv_output_type(&[f_rate_l, f_nper, f_pmt]).unwrap();
    assert_eq!(out2.dtype, DataType::List(Box::new(DataType::Float64)));
}

#[test]
fn test_pv_excel_learn_example() {
    // Microsoft Learn VBA PV example:
    // https://learn.microsoft.com/en-us/office/vba/language/reference/user-interface-help/pv-function
    let rate = Series::new("rate".into(), vec![0.0825_f64]);
    let nper = Series::new("nper".into(), vec![20.0_f64]);
    let pmt = Series::new("pmt".into(), vec![-50000.0_f64]);
    let kwargs = PvKwargs { fv: Some(1_000_000.0), typ: Some(1) };

    let out = pv(&[rate.clone(), nper.clone(), pmt.clone()], &kwargs).unwrap();
    let v = out.f64().unwrap().get(0).unwrap();

    // Validate Excel formula identity: PV + PMT*(1+r*type)*A + FV*df ≈ 0
    let r = rate.f64().unwrap().get(0).unwrap();
    let n = nper.f64().unwrap().get(0).unwrap();
    let p = pmt.f64().unwrap().get(0).unwrap();
    let t = 1.0_f64; // type=1 beginning
    let a = (1.0 - (1.0 + r).powf(-n)) / r;
    let df = (1.0 + r).powf(-n);
    let lhs = v + p * (1.0 + r * t) * a + 1_000_000.0 * df;
    assert!(lhs.abs() < 1e-6);
}
