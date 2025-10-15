// ABOUTME: Excel-compatible IRR function implementation
// ABOUTME: Computes internal rate of return for cash flow lists with list-column support

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct IrrKwargs {
    pub guess: Option<f64>,
}

/// Returns the output type for the IRR function
pub fn irr_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let values_type = &input_fields[0].dtype;
    match values_type {
        // IRR returns one scalar per row, even when input is a list
        DataType::List(_) | DataType::Float64 => Ok(Field::new("irr".into(), DataType::Float64)),
        _ => Ok(Field::new("irr".into(), DataType::Float64)),
    }
}

/// Excel-like IRR. Inputs:
/// - inputs[0]: values (List[Float64] preferred; Float64 allowed and treated as 1-length list)
/// - inputs[1] (optional): per-row guess as Float64 Series
/// - kwargs.guess: scalar guess if per-row Series not provided (default 0.1)
///
/// Errors when:
/// - A row has all non-null values that do not contain both signs
/// - Non-convergence within iteration limits
pub fn irr(inputs: &[Series], kwargs: &IrrKwargs) -> PolarsResult<Series> {
    let values_series = &inputs[0];
    let maybe_guess_series = if inputs.len() > 1 {
        Some(&inputs[1])
    } else {
        None
    };

    // Validate optional guess series type if provided
    if let Some(gs) = maybe_guess_series {
        if gs.dtype() != &DataType::Float64 {
            return Err(PolarsError::ComputeError(
                format!(
                    "irr optional guess column must be Float64, got {}",
                    gs.dtype()
                )
                .into(),
            ));
        }
    }

    let default_guess = kwargs.guess.unwrap_or(0.1);

    match values_series.dtype() {
        DataType::List(inner) => {
            // Ensure inner type is Float64 if known
            if let DataType::Float64 = inner.as_ref() {
            } else {
                // We'll try to cast to List[Float64]
            }
            let list = values_series.list()?;
            let guesses: Option<&Float64Chunked> = maybe_guess_series.and_then(|s| s.f64().ok());

            let out: Float64Chunked = match guesses {
                Some(gs) => {
                    // Per-row guess column
                    list.into_iter()
                        .zip(gs)
                        .map(|(opt_series, guess_opt)| match (opt_series, guess_opt) {
                            (Some(s), Some(g)) => irr_for_series(&s, g).ok(),
                            (Some(s), None) => irr_for_series(&s, default_guess).ok(),
                            (None, _) => None, // null list -> null result
                        })
                        .collect()
                }
                None => {
                    // Single scalar guess
                    list.into_iter()
                        .map(|opt_series| match opt_series {
                            Some(s) => irr_for_series(&s, default_guess).ok(),
                            None => None,
                        })
                        .collect()
                }
            };
            Ok(out.with_name("irr".into()).into_series())
        }
        DataType::Float64 => {
            // Treat each row as 1-length list. This will likely error due to sign requirement,
            // but we follow the same path for consistency.
            let vals = values_series.f64()?;
            let gs_col: Option<&Float64Chunked> = maybe_guess_series.and_then(|s| s.f64().ok());

            let out: Float64Chunked = match gs_col {
                Some(gs) => vals
                    .into_iter()
                    .zip(gs)
                    .map(|(v_opt, g_opt)| match (v_opt, g_opt) {
                        (Some(v), Some(g)) => calculate_irr(&[v], g).ok(),
                        (Some(v), None) => calculate_irr(&[v], default_guess).ok(),
                        (None, _) => None,
                    })
                    .collect(),
                None => vals
                    .into_iter()
                    .map(|v_opt| match v_opt {
                        Some(v) => calculate_irr(&[v], default_guess).ok(),
                        None => None,
                    })
                    .collect(),
            };
            Ok(out.with_name("irr".into()).into_series())
        }
        other => Err(PolarsError::ComputeError(
            format!(
                "irr requires List[Float64] or Float64 inputs; got {}",
                other
            )
            .into(),
        )),
    }
}

fn irr_for_series(values_series: &Series, guess: f64) -> Result<f64, &'static str> {
    // Accept Float64, or attempt to cast
    let vs = if values_series.dtype() == &DataType::Float64 {
        values_series.clone()
    } else {
        values_series.cast(&DataType::Float64).map_err(|_| "type")?
    };

    let vals = vs.f64().map_err(|_| "type")?;

    // If any null inside list -> null at caller; return error marker the caller will turn into None via transpose()
    if vals.null_count() > 0 {
        return Err("null_in_list");
    }

    let vec: Vec<f64> = vals.into_no_null_iter().collect();
    calculate_irr(&vec, guess)
}

#[inline]
fn npv(rate: f64, values: &[f64]) -> f64 {
    // sum_{t=0..n} values[t] / (1+rate)^t
    let one_plus = 1.0 + rate;
    let mut acc = 0.0;
    if one_plus <= 0.0 {
        // If rate <= -1, discount factors alternate/overflow; still compute naively
        for (t, &v) in values.iter().enumerate() {
            acc += v / one_plus.powi(t as i32);
        }
        return acc;
    }
    let mut denom = 1.0; // (1+r)^t
    for &v in values {
        acc += v / denom;
        denom *= one_plus;
    }
    acc
}

#[inline]
fn d_npv(rate: f64, values: &[f64]) -> f64 {
    // derivative of NPV wrt rate: sum_{t=1..n} -t * values[t] / (1+rate)^(t+1)
    let one_plus = 1.0 + rate;
    let mut acc = 0.0;
    if one_plus == 0.0 {
        return f64::INFINITY;
    }
    let mut denom = one_plus; // (1+r)^1
    for (t, &v) in values.iter().enumerate().skip(1) {
        acc -= (t as f64) * v / (denom * one_plus);
        denom *= one_plus;
    }
    acc
}

fn sign_change(values: &[f64]) -> bool {
    let mut has_pos = false;
    let mut has_neg = false;
    for &v in values {
        if v > 0.0 {
            has_pos = true;
        } else if v < 0.0 {
            has_neg = true;
        }
        if has_pos && has_neg {
            return true;
        }
    }
    false
}

fn calculate_irr(values: &[f64], guess: f64) -> Result<f64, &'static str> {
    if values.is_empty() {
        return Err("empty");
    }
    if !sign_change(values) {
        return Err("no_sign_change");
    }

    // Newton-Raphson
    let mut r = guess;
    let tol = 1e-7;
    let max_iter = 50;

    for _ in 0..max_iter {
        let f = npv(r, values);
        if f.abs() < tol {
            return Ok(r);
        }
        let df = d_npv(r, values);
        if df.abs() < 1e-12 || !df.is_finite() {
            break; // fallback to bisection
        }
        let step = f / df;
        let next = r - step;
        if !next.is_finite() {
            break;
        }
        // If NR jumps beyond limits (e.g., r <= -1), dampen
        if next <= -0.999_999_9 {
            r = (r - 0.999_999_9) * 0.5 - 0.5; // some damping
        } else {
            r = next;
        }
    }

    // Bracket and bisection fallback
    let mut low = -0.999_999_9; // cannot be <= -1 (division by zero in discount)
    let mut high = 1.0;
    let mut f_low = npv(low, values);
    let mut f_high = npv(high, values);
    // Expand until sign change or bounds large enough
    let mut expand_steps = 0;
    while f_low * f_high > 0.0 && expand_steps < 60 {
        // Expand to the side with larger magnitude
        if f_low.abs() < f_high.abs() {
            high = high * 2.0 + 0.1;
            f_high = npv(high, values);
        } else {
            low = (low - 1.0) * 2.0 + 1.0; // move lower further negative but keep > -1
            if low <= -0.999_999_9 {
                low = -0.999_999_9 + (expand_steps as f64) * 1e-6;
            }
            f_low = npv(low, values);
        }
        expand_steps += 1;
    }
    if f_low * f_high > 0.0 {
        return Err("no_bracket");
    }

    let mut mid;
    for _ in 0..200 {
        mid = 0.5 * (low + high);
        let f_mid = npv(mid, values);
        if f_mid.abs() < tol {
            return Ok(mid);
        }
        if f_low.signum() * f_mid.signum() < 0.0 {
            high = mid;
        } else {
            low = mid;
            f_low = f_mid;
        }
        if (high - low).abs() < tol.max(1e-12) {
            return Ok(0.5 * (low + high));
        }
    }

    Err("non_converge")
}
