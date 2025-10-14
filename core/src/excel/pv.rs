// ABOUTME: Excel-compatible PV function implementation
// ABOUTME: Computes present value with list broadcasting and kwargs support

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct PvKwargs {
    pub fv: Option<f64>,
    pub typ: Option<i32>,
}

const EPS: f64 = 1e-12;

/// Helper function to cast numeric types to Float64 if needed
/// Handles both scalar and list types (e.g., Int64 -> Float64, List[Int64] -> List[Float64])
fn cast_to_float_if_needed(series: &Series) -> PolarsResult<Series> {
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
    let rate_s = &inputs[0];
    let nper_s = &inputs[1];
    let pmt_s = &inputs[2];

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
    let result = rate_ca
        .into_iter()
        .zip(nper_ca)
        .zip(pmt_ca)
        .map(|((r_opt, n_opt), p_opt)| match (r_opt, n_opt, p_opt) {
            (Some(r), Some(n), Some(p)) => Some(calculate_pv(r, n, p, fv, typ)),
            _ => None,
        })
        .collect::<Float64Chunked>();

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

    // Extract scalars (may be null if empty); we broadcast each element's value
    let a_opt = scalar_a.f64()?.get(0);
    let b_opt = scalar_b.f64()?.get(0);

    let result: ListChunked = list_ca.apply_amortized(|s| {
        // Each inner series should be Float64
        if let Ok(vals) = s.as_ref().f64() {
            let out = vals
                .into_iter()
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
                .collect::<Float64Chunked>();
            out.into_series()
        } else {
            let len = s.as_ref().len();
            Float64Chunked::full_null("".into(), len).into_series()
        }
    });

    Ok(result.into_series())
}

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
            // rate and nper are lists, pmt scalar
            let pmt_opt = pmt_s.f64()?.get(0);
            let result: ListChunked = r_l
                .into_iter()
                .zip(n_l)
                .map(|(r_opt, n_opt)| match (r_opt, n_opt, pmt_opt) {
                    (Some(r_s), Some(n_s), Some(p)) => {
                        let r_ca = r_s.f64().ok()?;
                        let n_ca = n_s.f64().ok()?;
                        let out = r_ca
                            .into_iter()
                            .zip(n_ca)
                            .map(|(r, n)| match (r, n) {
                                (Some(rv), Some(nv)) => Some(calculate_pv(rv, nv, p, fv, typ)),
                                _ => None,
                            })
                            .collect::<Float64Chunked>();
                        Some(out.into_series())
                    }
                    _ => None,
                })
                .collect();
            Ok(result.into_series())
        }
        (Ok(r_l), Err(_), Ok(p_l)) => {
            // rate and pmt lists, nper scalar
            let nper_opt = nper_s.f64()?.get(0);
            let result: ListChunked = r_l
                .into_iter()
                .zip(p_l)
                .map(|(r_opt, p_opt)| match (r_opt, p_opt, nper_opt) {
                    (Some(r_s), Some(p_s), Some(n)) => {
                        let r_ca = r_s.f64().ok()?;
                        let p_ca = p_s.f64().ok()?;
                        let out = r_ca
                            .into_iter()
                            .zip(p_ca)
                            .map(|(r, p)| match (r, p) {
                                (Some(rv), Some(pv)) => Some(calculate_pv(rv, n, pv, fv, typ)),
                                _ => None,
                            })
                            .collect::<Float64Chunked>();
                        Some(out.into_series())
                    }
                    _ => None,
                })
                .collect();
            Ok(result.into_series())
        }
        (Err(_), Ok(n_l), Ok(p_l)) => {
            // nper and pmt lists, rate scalar
            let rate_opt = rate_s.f64()?.get(0);
            let result: ListChunked = n_l
                .into_iter()
                .zip(p_l)
                .map(|(n_opt, p_opt)| match (n_opt, p_opt, rate_opt) {
                    (Some(n_s), Some(p_s), Some(r)) => {
                        let n_ca = n_s.f64().ok()?;
                        let p_ca = p_s.f64().ok()?;
                        let out = n_ca
                            .into_iter()
                            .zip(p_ca)
                            .map(|(n, p)| match (n, p) {
                                (Some(nv), Some(pv2)) => Some(calculate_pv(r, nv, pv2, fv, typ)),
                                _ => None,
                            })
                            .collect::<Float64Chunked>();
                        Some(out.into_series())
                    }
                    _ => None,
                })
                .collect();
            Ok(result.into_series())
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

    Ok(result.into_series())
}

#[inline]
fn calculate_pv(rate: f64, nper: f64, pmt: f64, fv: f64, typ: i32) -> f64 {
    if rate.abs() < EPS {
        return -(pmt * nper + fv);
    }
    let typf = if typ != 0 { 1.0 } else { 0.0 };
    let one_plus_r = 1.0 + rate;
    let pow = one_plus_r.powf(-nper);
    // Use fused multiply-add where possible
    let ann = (1.0 + rate * typf) * (1.0 - pow) / rate;
    -(pmt * ann + fv * pow)
}
