// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

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
    let out0 = pv(
        &[rate_month.clone(), nper_months.clone(), pmt.clone()],
        &PvKwargs {
            fv: Some(0.0),
            typ: Some(0),
        },
    )
    .unwrap();
    let v0 = out0.f64().unwrap().get(0).unwrap();
    let r = 0.12_f64 / 12.0;
    let n = 360.0;
    let p = -1000.0;
    let a = (1.0 - (1.0 + r).powf(-n)) / r;
    let lhs0 = v0 + p * (1.0 + r * 0.0) * a + 0.0 * (1.0 + r).powf(-n);
    assert!(lhs0.abs() < 1e-9);

    // type 1
    let out1 = pv(
        &[rate_month, nper_months, pmt],
        &PvKwargs {
            fv: Some(0.0),
            typ: Some(1),
        },
    )
    .unwrap();
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
    let kwargs = PvKwargs {
        fv: Some(1_000_000.0),
        typ: Some(1),
    };

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

#[test]
fn a_list_operand_is_read_from_its_slices_own_values() -> PolarsResult<()> {
    // A sliced list keeps the whole column's inner values; the operand the
    // formula reads is cut to the slice's rows, whatever its element type.
    let floats = l(vec![
        vec![0.01, 0.02],
        vec![0.03, 0.04],
        vec![0.05, 0.06],
        vec![0.07, 0.08],
    ]);
    let ints = floats.cast(&DataType::List(Box::new(DataType::Int64)))?;
    for sliced in [floats.slice(1, 2), ints.slice(1, 2)] {
        assert_eq!(sliced.list()?.get_inner().len(), 8);
        let read = cast_to_float_if_needed(&sliced)?;
        assert_eq!(read.list()?.get_inner().len(), 4, "{}", sliced.dtype());
    }

    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let nper = s(&[10.0, 20.0, 30.0, 40.0]);
    let pmt = s(&[100.0, 100.0, 100.0, 100.0]);
    let all = pv(&[floats.clone(), nper.clone(), pmt.clone()], &kwargs)?;
    let part = pv(
        &[floats.slice(1, 2), nper.slice(1, 2), pmt.slice(1, 2)],
        &kwargs,
    )?;
    assert!(part.equals_missing(&all.slice(1, 2)));
    Ok(())
}

#[test]
fn per_period_operands_of_another_length_are_refused_not_cut_short() {
    // Two policies; the second has three periods of rate and two of the
    // other list, which used to answer two present values and say nothing.
    let kwargs = PvKwargs {
        fv: Some(0.0),
        typ: Some(0),
    };
    let rate = l(vec![vec![0.05, 0.05], vec![0.05, 0.05, 0.05]]);
    let short = l(vec![vec![10.0, 10.0], vec![10.0, 10.0]]);
    let cases = [
        (
            "pmt against rate",
            vec![rate.clone(), s(&[10.0]), short.clone()],
        ),
        (
            "nper against rate",
            vec![rate.clone(), short.clone(), s(&[1.0])],
        ),
        (
            "pmt against nper",
            vec![s(&[0.05]), rate.clone(), short.clone()],
        ),
        (
            "pmt against rate",
            vec![rate.clone(), rate.clone(), short.clone()],
        ),
    ];
    for (sentence, inputs) in cases {
        let err = pv(&inputs, &kwargs).unwrap_err().to_string();
        assert!(
            err.contains(&format!(
                "mismatched inner list lengths in one policy: {sentence}"
            )),
            "{sentence}: {err}"
        );
        assert!(!err.contains("at row"), "{err}");
    }
    // Lists that fit answer as before, one value per period.
    let out = pv(&[rate.clone(), rate.clone(), rate], &kwargs).unwrap();
    assert_eq!(out.list().unwrap().get_as_series(1).unwrap().len(), 3);
}

/// The present value at `rate` as spec 11.1.35 states it, for the checks
/// below: the payments and the future value of `nper` periods, end of period.
fn pv_at(rate: f64, nper: f64, pmt: f64, fv: f64, typ: i32) -> f64 {
    let kwargs = PvKwargs {
        fv: Some(fv),
        typ: Some(typ),
    };
    let out = pv(&[s(&[rate]), s(&[nper]), s(&[pmt])], &kwargs).unwrap();
    out.f64().unwrap().get(0).unwrap()
}

#[test]
// The expected values are written as the exact decimals they were computed
// as; the compiler rounds each to its double, which is what the bound reads.
#[allow(clippy::excessive_precision)]
fn test_near_zero_rate_meets_the_relative_bound() {
    // Exact values by 80-digit decimal arithmetic over the doubles' own
    // values: 360 payments of 100 and a future value of 1000.
    let cases = [
        (1e-15, 0, -36999.999999993139_f64),
        (1e-15, 1, -36999.999999993175_f64),
        (9.99e-13, 0, -36999.999993148856_f64),
        (1e-12, 0, -36999.999993142002_f64),
        (1e-12, 1, -36999.999993177997_f64),
        (1e-9, 0, -36999.993142000851_f64),
        (1e-8, 1, -36999.931780084255_f64),
        (1e-5, 0, -36931.504828261612_f64),
    ];
    for (rate, typ, exact) in cases {
        let got = pv_at(rate, 360.0, 100.0, 1000.0, typ);
        assert_relative_eq!(got, exact, max_relative = 1e-12);
    }
}

#[test]
fn test_no_step_at_a_threshold_near_zero() {
    // The old form switched to the flat form below 1e-12 and stepped by
    // 0.044 there; the two neighbours now differ by what the rate moves.
    let below = pv_at(9.99e-13, 360.0, 100.0, 1000.0, 0);
    let at = pv_at(1e-12, 360.0, 100.0, 1000.0, 0);
    assert!((below - at).abs() < 1e-6, "{below} {at}");
}

#[test]
fn test_the_flat_form_is_the_answer_only_at_zero() {
    assert_eq!(pv_at(0.0, 360.0, 100.0, 1000.0, 0), -37000.0);
    assert_eq!(pv_at(-0.0, 360.0, 100.0, 1000.0, 1), -37000.0);
    assert_ne!(pv_at(1e-13, 360.0, 100.0, 1000.0, 0), -37000.0);
}

/// A run of policies every one of which answers a null list.
fn null_lists(rows: usize) -> PolarsResult<Series> {
    Series::new_null("r".into(), rows).cast(&DataType::List(Box::new(DataType::Float64)))
}

#[test]
fn a_chunk_of_null_lists_answers_the_type_the_plugin_declares() -> PolarsResult<()> {
    // The streaming engine hands a plugin one chunk at a time. A chunk whose
    // every policy answers a null list gave the collector no inner type and
    // came back List(Null), which beside the next chunk's List(Float64) was a
    // panic. One per-period operand, two, and three.
    let kwargs = PvKwargs {
        fv: None,
        typ: None,
    };
    let declared = DataType::List(Box::new(DataType::Float64));
    let one = pv(
        &[null_lists(2)?, s(&[10.0, 4.0]), s(&[100.0, 1.0])],
        &kwargs,
    )?;
    let two = pv(
        &[
            null_lists(2)?,
            l(vec![vec![1.0], vec![4.0]]),
            s(&[100.0, 1.0]),
        ],
        &kwargs,
    )?;
    let three = pv(
        &[
            null_lists(2)?,
            l(vec![vec![1.0], vec![4.0]]),
            l(vec![vec![100.0], vec![1.0]]),
        ],
        &kwargs,
    )?;
    for answered in [&one, &two, &three] {
        assert_eq!(answered.dtype(), &declared);
        assert_eq!(answered.null_count(), 2);
    }
    Ok(())
}

#[test]
fn a_null_policy_value_beside_two_runs_is_null_in_each_period() -> PolarsResult<()> {
    // 11.1.18: a null scalar is repeated to the other operands' length, a
    // null in each period. Beside one per-period operand the kernel answered
    // that; beside two it answered a null run, as if the policy had no
    // periods. Each of the three operands as the per-policy one in turn.
    let kwargs = PvKwargs {
        fv: None,
        typ: None,
    };
    let runs = || l(vec![vec![0.05, 0.04], vec![1.0]]);
    let held = s_opt(&[None, Some(2.0)]);
    for operands in [
        [runs(), runs(), held.clone()],
        [runs(), held.clone(), runs()],
        [held.clone(), runs(), runs()],
    ] {
        let answered = pv(&operands, &kwargs)?;
        let rows = answered.list()?;
        let first = rows
            .get_as_series(0)
            .ok_or_else(|| PolarsError::ComputeError("a null run, not a run of nulls".into()))?;
        assert_eq!(first.len(), 2);
        assert_eq!(first.null_count(), 2);
        let second = rows
            .get_as_series(1)
            .ok_or_else(|| PolarsError::ComputeError("the second policy's run is null".into()))?;
        assert_eq!(second.null_count(), 0);
    }
    Ok(())
}
