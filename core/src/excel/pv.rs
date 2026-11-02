// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Excel-compatible PV function implementation
// ABOUTME: Computes present value with list broadcasting and kwargs support

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

use crate::polars_functions::list_pow::as_float_lists;
use crate::polars_functions::slices::{own_rows, rows_per_policy, same_periods};

#[derive(Deserialize, Clone)]
pub struct PvKwargs {
    pub fv: Option<f64>,
    pub typ: Option<i32>,
}

/// Fetch a per-row scalar value, broadcasting a genuine length-1 (literal) input
/// to every row. Polars passes literal args as a length-1 series while column
/// args are full length; without this a plugin silently reads row 0 for everyone.
#[inline]
fn scalar_at(ca: &Float64Chunked, i: usize) -> Option<f64> {
    if ca.len() == 1 {
        ca.get(0)
    } else {
        ca.get(i)
    }
}

/// Helper function to cast numeric types to Float64 if needed
/// Handles both scalar and list types (e.g., Int64 -> Float64, List[Int64] -> List[Float64])
///
/// A list column comes back cut to its own rows: a streamed slice keeps the
/// whole column's inner values, and the cast must not convert them all.
pub(crate) fn cast_to_float_if_needed(series: &Series) -> PolarsResult<Series> {
    let series = &own_rows(series);
    match series.dtype() {
        DataType::Float64 => Ok(series.clone()),
        DataType::List(inner) => {
            // If it's a list of non-floats, cast the inner type
            if inner.as_ref() != &DataType::Float64 {
                series.cast(&DataType::List(Box::new(DataType::Float64)))
            } else {
                Ok(series.clone())
            }
        }
        // Any other numeric type (Int64, Int32, Float32, etc.) -> cast to Float64
        _ => series.cast(&DataType::Float64),
    }
}

/// Returns the output type for the pv function
pub fn pv_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let rate_t = &input_fields[0].dtype;
    let nper_t = &input_fields[1].dtype;
    let pmt_t = &input_fields[2].dtype;

    if matches!(rate_t, DataType::List(_))
        || matches!(nper_t, DataType::List(_))
        || matches!(pmt_t, DataType::List(_))
    {
        Ok(Field::new(
            "pv".into(),
            DataType::List(Box::new(DataType::Float64)),
        ))
    } else {
        Ok(Field::new("pv".into(), DataType::Float64))
    }
}

/// Excel-compatible PV. Inputs are rate, nper, pmt. `fv` and `typ` provided via kwargs.
pub fn pv(inputs: &[Series], kwargs: &PvKwargs) -> PolarsResult<Series> {
    // A one-row list (a literal the in-memory engine hands over unbroadcast)
    // is repeated for every policy, as the streaming engine reads it.
    let operands = rows_per_policy(inputs, false)?;
    let [rate_s, nper_s, pmt_s] = operands.as_slice() else {
        return Err(PolarsError::ComputeError(
            format!("pv takes three operands, got {}", operands.len()).into(),
        ));
    };

    let fv = kwargs.fv.unwrap_or(0.0);
    let mut typ = kwargs.typ.unwrap_or(0);
    // Coerce typ to 0 or 1 following Excel semantics (any nonzero -> 1)
    if typ != 0 {
        typ = 1;
    }

    // Cast integer inputs to Float64 for better usability (matches IRR behavior)
    // Handles both scalar (Int64 -> Float64) and list (List[Int64] -> List[Float64])
    let rate_s = cast_to_float_if_needed(rate_s)?;
    let nper_s = cast_to_float_if_needed(nper_s)?;
    let pmt_s = cast_to_float_if_needed(pmt_s)?;

    match (rate_s.dtype(), nper_s.dtype(), pmt_s.dtype()) {
        (DataType::Float64, DataType::Float64, DataType::Float64) => {
            pv_scalar(rate_s.f64()?, nper_s.f64()?, pmt_s.f64()?, fv, typ)
        }
        // Any list present -> handle with list strategies
        (DataType::List(_), DataType::Float64, DataType::Float64) => {
            pv_list_scalar(&rate_s, &nper_s, &pmt_s, fv, typ, 0)
        }
        (DataType::Float64, DataType::List(_), DataType::Float64) => {
            pv_list_scalar(&nper_s, &rate_s, &pmt_s, fv, typ, 1)
        }
        (DataType::Float64, DataType::Float64, DataType::List(_)) => {
            pv_list_scalar(&pmt_s, &rate_s, &nper_s, fv, typ, 2)
        }
        (DataType::List(_), DataType::List(_), DataType::Float64)
        | (DataType::List(_), DataType::Float64, DataType::List(_))
        | (DataType::Float64, DataType::List(_), DataType::List(_)) => {
            pv_two_lists(&rate_s, &nper_s, &pmt_s, fv, typ)
        }
        (DataType::List(_), DataType::List(_), DataType::List(_)) => {
            pv_three_lists(&rate_s, &nper_s, &pmt_s, fv, typ)
        }
        _ => Err(PolarsError::ComputeError(
            format!(
                "pv requires Float64 or List[Float64] inputs, got {}, {}, {}",
                rate_s.dtype(),
                nper_s.dtype(),
                pmt_s.dtype()
            )
            .into(),
        )),
    }
}

fn pv_scalar(
    rate_ca: &Float64Chunked,
    nper_ca: &Float64Chunked,
    pmt_ca: &Float64Chunked,
    fv: f64,
    typ: i32,
) -> PolarsResult<Series> {
    // Broadcast length-1 (literal) inputs to the full row count instead of
    // zip-truncating to the shortest, which collapsed the result to length 1
    // (and raised a height-mismatch when a literal rate met column nper/pmt).
    let len = rate_ca.len().max(nper_ca.len()).max(pmt_ca.len());
    let result: Float64Chunked = (0..len)
        .map(|i| {
            match (
                scalar_at(rate_ca, i),
                scalar_at(nper_ca, i),
                scalar_at(pmt_ca, i),
            ) {
                (Some(r), Some(n), Some(p)) => Some(calculate_pv(r, n, p, fv, typ)),
                _ => None,
            }
        })
        .collect();

    Ok(result.with_name("pv".into()).into_series())
}

// list_index: which of (rate, nper, pmt) is the list: 0->rate, 1->nper, 2->pmt
fn pv_list_scalar(
    list_series: &Series,
    scalar_a: &Series,
    scalar_b: &Series,
    fv: f64,
    typ: i32,
    list_index: i32,
) -> PolarsResult<Series> {
    let list_ca = list_series.list()?;
    let a_ca = scalar_a.f64()?;
    let b_ca = scalar_b.f64()?;

    // Combine each list row with THIS row's scalars (broadcasting length-1
    // literals via scalar_at) rather than row 0's — the previous get(0)
    // outside the loop applied policy 0's values to every policy.
    let result: ListChunked = list_ca
        .into_iter()
        .enumerate()
        .map(|(i, opt_s)| {
            let a_opt = scalar_at(a_ca, i);
            let b_opt = scalar_at(b_ca, i);
            let s = opt_s?;
            if let Ok(vals) = s.f64() {
                let out: Float64Chunked = vals
                    .iter()
                    .map(|x_opt| match (x_opt, a_opt, b_opt) {
                        (Some(x), Some(a), Some(b)) => {
                            let (rate, nper, pmt) = match list_index {
                                0 => (x, a, b),
                                1 => (a, x, b),
                                _ => (a, b, x),
                            };
                            Some(calculate_pv(rate, nper, pmt, fv, typ))
                        }
                        _ => None,
                    })
                    .collect();
                Some(out.into_series())
            } else {
                let len = s.len();
                Some(Float64Chunked::full_null("".into(), len).into_series())
            }
        })
        .collect();

    // A streamed chunk whose every policy answers a null list gives the
    // collector no inner type to infer: List(Null) beside the List(Float64)
    // of the next chunk was a panic, not an answer.
    as_float_lists(result)
}

/// Refuse a policy whose per-period operands do not share its number of
/// periods.
///
/// Two or three of rate, nper and pmt may be per-period; each policy's
/// lists are paired period by period, so they must have equal lengths
/// within the policy (graph-artifact spec 11.1.18). Zipping them instead
/// answered the policy with a run cut to the shortest list: three periods
/// of rate against two of pmt gave two present values, and nothing said.
/// A null list has no periods to pair and is not measured.
fn same_periods_in_each_policy(named: &[(&str, &ListChunked)]) -> PolarsResult<()> {
    let [(first_name, first), rest @ ..] = named else {
        return Ok(());
    };
    for (other_name, other) in rest {
        for (one, another) in first.amortized_iter().zip(other.amortized_iter()) {
            if let (Some(one), Some(another)) = (one, another) {
                same_periods(
                    first_name,
                    one.as_ref().len(),
                    other_name,
                    another.as_ref().len(),
                )?;
            }
        }
    }
    Ok(())
}

/// Two of rate, nper and pmt per period and the third per policy.
///
/// The per-policy operand is repeated to the policy's periods, a null one a
/// null in each period (graph-artifact spec 11.1.18): the policy keeps its
/// run, every cell of it null. A null run on either per-period side is a
/// policy with no periods and answers a null run.
fn pv_two_lists(
    rate_s: &Series,
    nper_s: &Series,
    pmt_s: &Series,
    fv: f64,
    typ: i32,
) -> PolarsResult<Series> {
    let rate_l = rate_s.list();
    let nper_l = nper_s.list();
    let pmt_l = pmt_s.list();

    match (rate_l, nper_l, pmt_l) {
        (Ok(r_l), Ok(n_l), Err(_)) => {
            // rate and nper are lists, pmt scalar (broadcast per row via scalar_at)
            same_periods_in_each_policy(&[("rate", r_l), ("nper", n_l)])?;
            let pmt_ca = pmt_s.f64()?;
            let result: ListChunked = r_l
                .into_iter()
                .zip(n_l)
                .enumerate()
                .map(
                    |(i, (r_opt, n_opt))| match (r_opt, n_opt, scalar_at(pmt_ca, i)) {
                        (Some(r_s), Some(n_s), p_opt) => {
                            let r_ca = r_s.f64().ok()?;
                            let n_ca = n_s.f64().ok()?;
                            let out = r_ca
                                .into_iter()
                                .zip(n_ca)
                                .map(|(r, n)| match (r, n, p_opt) {
                                    (Some(rv), Some(nv), Some(p)) => {
                                        Some(calculate_pv(rv, nv, p, fv, typ))
                                    }
                                    _ => None,
                                })
                                .collect::<Float64Chunked>();
                            Some(out.into_series())
                        }
                        _ => None,
                    },
                )
                .collect();
            as_float_lists(result)
        }
        (Ok(r_l), Err(_), Ok(p_l)) => {
            // rate and pmt lists, nper scalar (broadcast per row via scalar_at)
            same_periods_in_each_policy(&[("rate", r_l), ("pmt", p_l)])?;
            let nper_ca = nper_s.f64()?;
            let result: ListChunked = r_l
                .into_iter()
                .zip(p_l)
                .enumerate()
                .map(
                    |(i, (r_opt, p_opt))| match (r_opt, p_opt, scalar_at(nper_ca, i)) {
                        (Some(r_s), Some(p_s), n_opt) => {
                            let r_ca = r_s.f64().ok()?;
                            let p_ca = p_s.f64().ok()?;
                            let out = r_ca
                                .into_iter()
                                .zip(p_ca)
                                .map(|(r, p)| match (r, p, n_opt) {
                                    (Some(rv), Some(pv), Some(n)) => {
                                        Some(calculate_pv(rv, n, pv, fv, typ))
                                    }
                                    _ => None,
                                })
                                .collect::<Float64Chunked>();
                            Some(out.into_series())
                        }
                        _ => None,
                    },
                )
                .collect();
            as_float_lists(result)
        }
        (Err(_), Ok(n_l), Ok(p_l)) => {
            // nper and pmt lists, rate scalar (broadcast per row via scalar_at)
            same_periods_in_each_policy(&[("nper", n_l), ("pmt", p_l)])?;
            let rate_ca = rate_s.f64()?;
            let result: ListChunked = n_l
                .into_iter()
                .zip(p_l)
                .enumerate()
                .map(
                    |(i, (n_opt, p_opt))| match (n_opt, p_opt, scalar_at(rate_ca, i)) {
                        (Some(n_s), Some(p_s), r_opt) => {
                            let n_ca = n_s.f64().ok()?;
                            let p_ca = p_s.f64().ok()?;
                            let out = n_ca
                                .into_iter()
                                .zip(p_ca)
                                .map(|(n, p)| match (n, p, r_opt) {
                                    (Some(nv), Some(pv2), Some(r)) => {
                                        Some(calculate_pv(r, nv, pv2, fv, typ))
                                    }
                                    _ => None,
                                })
                                .collect::<Float64Chunked>();
                            Some(out.into_series())
                        }
                        _ => None,
                    },
                )
                .collect();
            as_float_lists(result)
        }
        _ => unreachable!(),
    }
}

fn pv_three_lists(
    rate_s: &Series,
    nper_s: &Series,
    pmt_s: &Series,
    fv: f64,
    typ: i32,
) -> PolarsResult<Series> {
    let rate_l = rate_s.list()?;
    let nper_l = nper_s.list()?;
    let pmt_l = pmt_s.list()?;
    same_periods_in_each_policy(&[("rate", rate_l), ("nper", nper_l), ("pmt", pmt_l)])?;

    let result: ListChunked = rate_l
        .into_iter()
        .zip(nper_l)
        .zip(pmt_l)
        .map(|((r_opt, n_opt), p_opt)| match (r_opt, n_opt, p_opt) {
            (Some(r_s), Some(n_s), Some(p_s)) => {
                let r_ca = r_s.f64().ok()?;
                let n_ca = n_s.f64().ok()?;
                let p_ca = p_s.f64().ok()?;
                let out = r_ca
                    .into_iter()
                    .zip(n_ca)
                    .zip(p_ca)
                    .map(|((r, n), p)| match (r, n, p) {
                        (Some(rv), Some(nv), Some(pv2)) => Some(calculate_pv(rv, nv, pv2, fv, typ)),
                        _ => None,
                    })
                    .collect::<Float64Chunked>();
                Some(out.into_series())
            }
            _ => None,
        })
        .collect();

    as_float_lists(result)
}

/// Return the present value of `nper` payments of `pmt` and a future value
/// `fv` at `rate` per period (spec 11.1.35).
///
/// The discount factor `(1 + r)^-n` is taken as `exp(-n * ln_1p(r))` and the
/// paid-off fraction `1 - (1 + r)^-n` as `-exp_m1(-n * ln_1p(r))`, so neither
/// rounds `1 + r` first: near nought `1 + r` loses the rate's last digits, and
/// the old `powf` form was 8.9e-5 relative wrong at `r = 1e-12` and jumped by
/// 0.044 at the `1e-12` threshold it switched to the flat form at. Both
/// functions keep their accuracy as their argument goes to nought, so the
/// 1e-12 relative bound holds at every nonzero rate, and the flat form
/// `-(pmt * nper + fv)` is the answer only at a rate of exactly nought.
#[inline]
fn calculate_pv(rate: f64, nper: f64, pmt: f64, fv: f64, typ: i32) -> f64 {
    if rate == 0.0 {
        return -(pmt * nper + fv);
    }
    let typf = if typ != 0 { 1.0 } else { 0.0 };
    let grown = nper * rate.ln_1p();
    let discount = (-grown).exp();
    let paid_off = -(-grown).exp_m1();
    let ann = (1.0 + rate * typf) * paid_off / rate;
    -(pmt * ann + fv * discount)
}
