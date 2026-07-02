// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Yield-curve evaluation over List<Float64> year-fraction columns.
// ABOUTME: Dispatches on `method` in kwargs; returns List<Float64> of annually-compounded spot rates.

use polars::prelude::*;
use serde::Deserialize;

/// Kwargs for the `curve_eval` kernel.
///
/// Only the fields relevant to the chosen `method` need to be populated;
/// the rest can be `None`.
#[derive(Debug, Deserialize)]
pub struct CurveEvalKwargs {
    /// Interpolation / curve-fitting method (e.g. `"linear"`).
    pub method: String,
    /// X-axis knot points (year-fractions) for piecewise methods.
    pub xs: Option<Vec<f64>>,
    /// Y-axis values (rates) at each knot for piecewise methods.
    pub ys: Option<Vec<f64>>,
    /// Per-knot slopes for the `pchip` monotone-cubic Hermite interpolant.
    pub slopes: Option<Vec<f64>>,
    /// Extrapolation mode outside the knot range. Currently always flat (the only
    /// supported value); reserved for future methods.
    pub extrapolation: Option<String>,
    // Nelson-Siegel-Svensson parameters (`svensson`).
    pub b0: Option<f64>,
    pub b1: Option<f64>,
    pub b2: Option<f64>,
    pub b3: Option<f64>,
    pub tau1: Option<f64>,
    pub tau2: Option<f64>,
    // Smith-Wilson parameters (`smith_wilson`).
    pub u: Option<Vec<f64>>,
    pub zeta: Option<Vec<f64>>,
    pub omega: Option<f64>,
    pub alpha: Option<f64>,
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/// Linear interpolation of `ys` over sorted `xs` with flat extrapolation.
///
/// Mirrors `bindings/_interpolation.linear_interpolate` exactly:
/// - non-finite `t` (NaN or ±inf) is out of domain and returns `f64::NAN`
///   (the uniform cross-path sentinel)
/// - clamps to `ys[0]` for finite `t <= xs[0]`
/// - clamps to `ys[n-1]` for `t >= xs[n-1]`
/// - linear blend between bracketing knots otherwise
///
/// # Panics
///
/// Does not panic; a non-finite `t` returns `f64::NAN` rather than panicking,
/// and all index arithmetic is guarded by the finite-range checks.
fn eval_linear(t: f64, xs: &[f64], ys: &[f64]) -> f64 {
    if !t.is_finite() {
        return f64::NAN;
    }
    if t <= xs[0] {
        return ys[0];
    }
    let n = xs.len();
    if t >= xs[n - 1] {
        return ys[n - 1];
    }
    // `partition_point` returns the index of the first element > t.
    let i = xs.partition_point(|&x| x <= t);
    let (x0, x1) = (xs[i - 1], xs[i]);
    let (y0, y1) = (ys[i - 1], ys[i]);
    y0 + (y1 - y0) * (t - x0) / (x1 - x0)
}

/// C1 cubic Hermite evaluation with flat extrapolation (shared by pchip).
///
/// Evaluates the Hermite spline defined by knots `(xs, ys)` and tangent
/// slopes `m` at point `t`.  Flat extrapolation is applied outside the knot
/// range: values below `xs[0]` clamp to `ys[0]`, values above `xs[n-1]`
/// clamp to `ys[n-1]`.  A non-finite `t` (NaN or ±inf) is out of domain and
/// returns `f64::NAN` (the uniform cross-path sentinel).
///
/// # Panics
///
/// Does not panic; a non-finite `t` returns `f64::NAN`, and all index
/// arithmetic is guarded by the finite-range checks.
fn eval_hermite(t: f64, xs: &[f64], ys: &[f64], m: &[f64]) -> f64 {
    if !t.is_finite() {
        return f64::NAN;
    }
    if t <= xs[0] {
        return ys[0];
    }
    let n = xs.len();
    if t >= xs[n - 1] {
        return ys[n - 1];
    }
    let k = xs.partition_point(|&x| x <= t) - 1;
    let h = xs[k + 1] - xs[k];
    let s = (t - xs[k]) / h;
    let (s2, s3) = (s * s, s * s * s);
    let h00 = 2.0 * s3 - 3.0 * s2 + 1.0;
    let h10 = s3 - 2.0 * s2 + s;
    let h01 = -2.0 * s3 + 3.0 * s2;
    let h11 = s3 - s2;
    ys[k] * h00 + h * m[k] * h10 + ys[k + 1] * h01 + h * m[k + 1] * h11
}

/// Wilson heart H(u,v) (scalar form).
///
/// Min/max-free formulation: ``0.5 * [α(u+v) + e^{-α(u+v)} - α|u-v| - e^{-α|u-v|}]``.
fn sw_heart_scalar(u: f64, v: f64, alpha: f64) -> f64 {
    0.5 * (alpha * (u + v) + (-alpha * (u + v)).exp()
        - alpha * (u - v).abs()
        - (-alpha * (u - v).abs()).exp())
}

/// NSS loading pair for x = t/tau: returns ((1-e^-x)/x, that - e^-x). Limits at x->0: (1, 0).
fn svensson_load(x: f64) -> (f64, f64) {
    if x < 1e-8 {
        return (1.0, 0.0);
    }
    let e = (-x).exp();
    let l = (1.0 - e) / x;
    (l, l - e)
}

/// Evaluate a single year-fraction `t` using the configured method.
///
/// Out-of-domain `t` resolves to `f64::NAN` (the uniform cross-path sentinel),
/// mirroring the Python eager helpers exactly:
/// - any non-finite `t` (NaN or ±inf) → `NAN` for every method (guarded BEFORE
///   the closed form, so e.g. `svensson(+inf)` does not silently return the
///   long-rate level);
/// - additionally for `log_linear` and `smith_wilson`, `t <= 0.0` → `NAN`
///   (the spot rate `P(t)^(-1/t) - 1` is undefined at `t = 0`);
/// - for `linear` and `pchip`, finite `t <= 0` is in domain and flat-
///   extrapolates to `ys[0]` (handled inside `eval_linear` / `eval_hermite`).
fn eval_one(t: f64, kw: &CurveEvalKwargs) -> PolarsResult<f64> {
    // Non-finite `t` is out of domain for every method. Guard before the
    // closed form so plausible-but-wrong finite results cannot leak out.
    if !t.is_finite() {
        return Ok(f64::NAN);
    }
    // The spot-rate methods r(t) = P(t)^(-1/t) - 1 are undefined at t = 0 and
    // meaningless for t < 0.
    if matches!(kw.method.as_str(), "log_linear" | "smith_wilson") && t <= 0.0 {
        return Ok(f64::NAN);
    }
    match kw.method.as_str() {
        "linear" => {
            let xs = kw
                .xs
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval linear: missing xs"))?;
            let ys = kw
                .ys
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval linear: missing ys"))?;
            if xs.is_empty() || xs.len() != ys.len() {
                return Err(polars_err!(
                    ComputeError: "curve_eval linear: xs must be non-empty and the same length as ys"
                ));
            }
            Ok(eval_linear(t, xs, ys))
        }
        "log_linear" => {
            let xs = kw
                .xs
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval log_linear: missing xs"))?;
            let ys = kw
                .ys
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval log_linear: missing ys"))?;
            if xs.is_empty() || xs.len() != ys.len() {
                return Err(polars_err!(
                    ComputeError: "curve_eval log_linear: xs must be non-empty and the same length as ys"
                ));
            }
            // ys are log-DF knots: y_i = -u_i * ln(1 + r_i).
            // Interpolate linearly in log-DF space, then convert back to spot rate.
            let log_df = eval_linear(t, xs, ys);
            let df = log_df.exp();
            Ok(df.powf(-1.0 / t) - 1.0) // annually-compounded spot
        }
        "pchip" => {
            let xs = kw
                .xs
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing xs"))?;
            let ys = kw
                .ys
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing ys"))?;
            let m = kw
                .slopes
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval pchip: missing slopes"))?;
            if xs.is_empty() || xs.len() != ys.len() || xs.len() != m.len() {
                return Err(polars_err!(
                    ComputeError: "curve_eval pchip: xs, ys, slopes must be non-empty and equal length"
                ));
            }
            Ok(eval_hermite(t, xs, ys, m))
        }
        "svensson" => {
            let b0 = kw
                .b0
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing b0"))?;
            let b1 = kw
                .b1
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing b1"))?;
            let b2 = kw
                .b2
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing b2"))?;
            let b3 = kw
                .b3
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing b3"))?;
            let t1 = kw
                .tau1
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing tau1"))?;
            let t2 = kw
                .tau2
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval svensson: missing tau2"))?;
            let (l1, c1) = svensson_load(t / t1);
            let (_, c2) = svensson_load(t / t2);
            let cc = b0 + b1 * l1 + b2 * c1 + b3 * c2;
            Ok(cc.exp() - 1.0)
        }
        "smith_wilson" => {
            let u = kw
                .u
                .as_ref()
                .ok_or_else(|| polars_err!(ComputeError: "curve_eval smith_wilson: missing u"))?;
            let zeta = kw.zeta.as_ref().ok_or_else(
                || polars_err!(ComputeError: "curve_eval smith_wilson: missing zeta"),
            )?;
            let omega = kw.omega.ok_or_else(
                || polars_err!(ComputeError: "curve_eval smith_wilson: missing omega"),
            )?;
            let alpha = kw.alpha.ok_or_else(
                || polars_err!(ComputeError: "curve_eval smith_wilson: missing alpha"),
            )?;
            if u.len() != zeta.len() {
                return Err(
                    polars_err!(ComputeError: "curve_eval smith_wilson: u and zeta length differ"),
                );
            }
            let mut p = (-omega * t).exp();
            for (uj, zj) in u.iter().zip(zeta.iter()) {
                p += (-omega * (t + uj)).exp() * sw_heart_scalar(t, *uj, alpha) * zj;
            }
            Ok(p.powf(-1.0 / t) - 1.0)
        }
        other => Err(polars_err!(ComputeError: "curve_eval: unknown method '{}'", other)),
    }
}

// ---------------------------------------------------------------------------
// Public kernel
// ---------------------------------------------------------------------------

/// Evaluate the configured method across a `Float64Chunked` of year-fractions.
fn eval_chunk(ca: &Float64Chunked, kw: &CurveEvalKwargs) -> PolarsResult<Vec<Option<f64>>> {
    ca.iter()
        .map(|o| match o {
            Some(t) => eval_one(t, kw).map(Some),
            None => Ok(None),
        })
        .collect()
}

/// Evaluate a yield curve over a year-fraction column `t`, mirroring its shape.
///
/// Shape-polymorphic:
/// - `List<any numeric>` input → `List<Float64>` output with the same per-row shape.
/// - Any numeric (scalar-column) input → `Float64` output, one rate per row.
///
/// Integer columns (e.g., `month`, `year`, `duration`) are cast to `Float64`
/// automatically, matching the behaviour of all other gaspatchio kernels.
///
/// Null inner values propagate as null output.  Null rows (the outer list itself
/// being null) propagate as null rows.  An Expr's dtype is unknown at plan-build
/// time, so the scalar-vs-list dispatch happens here, at execution time.
///
/// # Arguments
///
/// * `inputs[0]` - Numeric or `List<numeric>` column of year-fraction values
/// * `kwargs`    - [`CurveEvalKwargs`] describing the curve method and parameters
///
/// # Errors
///
/// Returns a `PolarsError::ComputeError` if:
/// - The input series is neither a numeric type nor `List<numeric>`; expected a numeric or List(Float64) column
/// - `method` is not recognised
/// - Required kwargs for the chosen method are absent
pub fn curve_eval(inputs: &[Series], kwargs: &CurveEvalKwargs) -> PolarsResult<Series> {
    let s = &inputs[0];
    match s.dtype() {
        DataType::List(_) => {
            let t_list = s.list()?;
            let out: ListChunked = t_list
                .amortized_iter()
                .map(|opt| match opt {
                    None => Ok(None),
                    Some(inner) => {
                        let casted = inner.as_ref().cast(&DataType::Float64)?;
                        let ca = casted.f64()?;
                        Ok(Some(
                            Float64Chunked::from_iter(eval_chunk(ca, kwargs)?).into_series(),
                        ))
                    }
                })
                .collect::<PolarsResult<ListChunked>>()?;
            Ok(out.into_series())
        }
        dt if dt.is_numeric() => {
            let casted = s.cast(&DataType::Float64)?;
            let ca = casted.f64()?;
            Ok(Float64Chunked::from_iter(eval_chunk(ca, kwargs)?).into_series())
        }
        dt => Err(
            polars_err!(ComputeError: "curve_eval: unsupported input dtype {:?}; expected a numeric or List(Float64) column", dt),
        ),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a minimal `CurveEvalKwargs` for the linear method.
    fn lin_kwargs(xs: Vec<f64>, ys: Vec<f64>) -> CurveEvalKwargs {
        CurveEvalKwargs {
            method: "linear".into(),
            xs: Some(xs),
            ys: Some(ys),
            slopes: None,
            extrapolation: Some("flat".into()),
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        }
    }

    #[test]
    fn test_linear_interp_and_flat_extrap() {
        // t values: below range, at knot, interpolated, at knot, above range
        let t = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![0.5_f64, 1.0, 3.0, 5.0, 11.0],
        ))])
        .into_series();
        // knots: xs=[1.0, 5.0, 10.0], ys=[0.03, 0.03, 0.05]
        let kw = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.03, 0.05]);

        let out = curve_eval(&[t], &kw).unwrap();
        let inner = out.list().unwrap().get_as_series(0).unwrap();
        let v = inner.f64().unwrap();

        // t=0.5  → below xs[0]=1.0 → flat 0.03
        assert!((v.get(0).unwrap() - 0.03).abs() < 1e-12);
        // t=3.0  → between 1.0 and 5.0, rate is flat 0.03 the whole way → 0.03
        assert!((v.get(2).unwrap() - 0.03).abs() < 1e-12);
        // t=11.0 → above xs[2]=10.0 → flat 0.05
        assert!((v.get(4).unwrap() - 0.05).abs() < 1e-12);
    }

    #[test]
    fn test_linear_midpoint() {
        // t=7.5 midway between xs=[5.0, 10.0], ys=[0.04, 0.05] → 0.045
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![7.5_f64]))]).into_series();
        let kw = lin_kwargs(vec![5.0, 10.0], vec![0.04, 0.05]);

        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        assert!((v.f64().unwrap().get(0).unwrap() - 0.045).abs() < 1e-12);
    }

    /// Parity test against `bindings/_interpolation.linear_interpolate`.
    ///
    /// Uses a genuinely sloped multi-segment curve to pin the bracket-index logic,
    /// the `t == xs[0]` boundary (lower clamp), interior-knot exact-hit, and
    /// `t == xs[last]` boundary (upper clamp).
    ///
    /// Expected values were derived by reading `linear_interpolate` directly:
    ///   xs = [1.0, 2.0, 5.0, 10.0], ys = [0.01, 0.02, 0.03, 0.04]
    ///   t=0.5  → <= xs[0]   → 0.01
    ///   t=1.0  → <= xs[0]   → 0.01
    ///   t=1.5  → interp     → 0.01 + 0.01 * 0.5/1.0 = 0.015
    ///   t=2.0  → interp     → 0.02 + 0.01 * 0.0/3.0 = 0.02
    ///   t=3.5  → interp     → 0.02 + 0.01 * 1.5/3.0 = 0.025
    ///   t=5.0  → interp     → 0.03 + 0.01 * 0.0/5.0 = 0.03
    ///   t=7.5  → interp     → 0.03 + 0.01 * 2.5/5.0 = 0.035
    ///   t=10.0 → >= xs[last]→ 0.04
    ///   t=12.0 → >= xs[last]→ 0.04
    #[test]
    fn test_linear_parity_vs_interpolate() {
        let t_vals = vec![0.5_f64, 1.0, 1.5, 2.0, 3.5, 5.0, 7.5, 10.0, 12.0];
        let expected = [0.01, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.04];
        let t = ListChunked::from_iter([Some(Series::new("".into(), t_vals))]).into_series();
        let kw = lin_kwargs(vec![1.0, 2.0, 5.0, 10.0], vec![0.01, 0.02, 0.03, 0.04]);

        let out = curve_eval(&[t], &kw).unwrap();
        let inner = out.list().unwrap().get_as_series(0).unwrap();
        let v = inner.f64().unwrap();

        for (i, &exp) in expected.iter().enumerate() {
            assert!(
                (v.get(i).unwrap() - exp).abs() < 1e-12,
                "index {i}: got {:.15}, expected {exp}",
                v.get(i).unwrap()
            );
        }
    }

    /// Null propagation: null inner values become null output values; null outer
    /// rows (the entire list is null) propagate as null rows.
    #[test]
    fn test_linear_null_propagation() {
        let kw = lin_kwargs(vec![1.0, 2.0, 5.0, 10.0], vec![0.01, 0.02, 0.03, 0.04]);

        // Row with a null element inside the list.
        let inner_vals: Vec<Option<f64>> = vec![Some(2.0), None, Some(7.5)];
        let inner_series = Float64Chunked::from_iter(inner_vals).into_series();

        // Two-row input: first row is null (outer), second row has an inner null.
        let t = ListChunked::from_iter([None, Some(inner_series)]).into_series();

        let out = curve_eval(&[t], &kw).unwrap();
        let list_out = out.list().unwrap();

        // Row 0: outer null → null row.
        assert!(
            list_out.get_as_series(0).is_none(),
            "expected null outer row at index 0"
        );

        // Row 1: inner null propagates.
        let row1 = list_out.get_as_series(1).unwrap();
        let v = row1.f64().unwrap();
        assert!((v.get(0).unwrap() - 0.02).abs() < 1e-12, "row1[0]");
        assert!(v.get(1).is_none(), "row1[1] should be null");
        assert!((v.get(2).unwrap() - 0.035).abs() < 1e-12, "row1[2]");
    }

    /// Jagged rows, empty inner list, and null row all handled independently.
    ///
    /// Pins the per-row independence guaranteed by `amortized_iter`.
    #[test]
    fn test_linear_jagged_and_empty() {
        let kw = lin_kwargs(vec![1.0, 2.0, 5.0, 10.0], vec![0.01, 0.02, 0.03, 0.04]);

        let row0 = Some(Series::new("".into(), vec![1.0_f64, 5.0]));
        let row2 = Some(Float64Chunked::from_iter(Vec::<Option<f64>>::new()).into_series());
        let row3 = Some(Series::new("".into(), vec![2.0_f64, 3.5, 10.0]));
        let t = ListChunked::from_iter([row0, None, row2, row3]).into_series();

        let out = curve_eval(&[t], &kw).unwrap();
        let list_out = out.list().unwrap();

        // Row 0: [1.0 → 0.01, 5.0 → 0.03]
        let r0 = list_out.get_as_series(0).unwrap();
        let v0 = r0.f64().unwrap();
        assert!((v0.get(0).unwrap() - 0.01).abs() < 1e-12, "row0[0]");
        assert!((v0.get(1).unwrap() - 0.03).abs() < 1e-12, "row0[1]");

        // Row 1: null outer row.
        assert!(list_out.get_as_series(1).is_none(), "row1 should be null");

        // Row 2: empty inner list → empty output.
        let r2 = list_out.get_as_series(2).unwrap();
        assert_eq!(r2.len(), 0, "row2 should be empty");

        // Row 3: [2.0 → 0.02, 3.5 → 0.025, 10.0 → 0.04]
        let r3 = list_out.get_as_series(3).unwrap();
        let v3 = r3.f64().unwrap();
        assert!((v3.get(0).unwrap() - 0.02).abs() < 1e-12, "row3[0]");
        assert!((v3.get(1).unwrap() - 0.025).abs() < 1e-12, "row3[1]");
        assert!((v3.get(2).unwrap() - 0.04).abs() < 1e-12, "row3[2]");
    }

    /// Single knot: the interpolation branch is never reached; all `t` clamp to
    /// the single `ys[0]` value, producing a constant curve.
    #[test]
    fn test_linear_single_knot_constant() {
        // xs.len() == ys.len() == 1 passes the guard.
        let kw = lin_kwargs(vec![3.0], vec![0.02]);
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0_f64, 3.0, 5.0]))])
            .into_series();

        let out = curve_eval(&[t], &kw).unwrap();
        let inner = out.list().unwrap().get_as_series(0).unwrap();
        let v = inner.f64().unwrap();

        for i in 0..3 {
            assert!(
                (v.get(i).unwrap() - 0.02).abs() < 1e-12,
                "index {i} should be 0.02"
            );
        }
    }

    /// Log-linear interpolation on a genuinely sloped curve.
    ///
    /// Knots: u=[1, 5], r=[0.03, 0.05]; ys_i = -u_i * ln(1 + r_i).
    /// At t=3: log-DF = linear interp of ys at 3; df = exp(log_df); r3 = df^(-1/3) - 1.
    #[test]
    fn test_log_linear_sloped() {
        let xs = vec![1.0_f64, 5.0];
        let r = [0.03_f64, 0.05];
        let ys: Vec<f64> = xs
            .iter()
            .zip(r)
            .map(|(u, ri)| -u * (1.0 + ri).ln())
            .collect();
        // hand-compute expected at t=3
        let log_df_3 = ys[0] + (ys[1] - ys[0]) * (3.0 - 1.0) / (5.0 - 1.0);
        let expected = log_df_3.exp().powf(-1.0 / 3.0) - 1.0;
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![3.0_f64]))]).into_series();
        let kw = CurveEvalKwargs {
            method: "log_linear".into(),
            xs: Some(xs),
            ys: Some(ys),
            extrapolation: Some("flat".into()),
            slopes: None,
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        };
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (v.f64().unwrap().get(0).unwrap() - expected).abs() < 1e-12,
            "log_linear sloped: got {:.15}, expected {expected:.15}",
            v.f64().unwrap().get(0).unwrap()
        );
    }

    /// The knot guard rejects structurally-invalid kwargs (empty `xs`, or
    /// `xs`/`ys` length mismatch) with an error rather than panicking.
    /// A non-empty `t` list is required so `eval_one` is actually invoked.
    #[test]
    fn test_linear_guard_rejects_bad_knots() {
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0_f64]))]).into_series();

        // Empty xs -> error.
        let kw_empty = lin_kwargs(vec![], vec![]);
        assert!(
            curve_eval(&[t.clone()], &kw_empty).is_err(),
            "empty xs should error, not panic"
        );

        // xs/ys length mismatch -> error.
        let kw_mismatch = lin_kwargs(vec![1.0, 2.0], vec![0.01]);
        assert!(
            curve_eval(&[t], &kw_mismatch).is_err(),
            "xs/ys length mismatch should error"
        );
    }

    /// Straight-line pchip: slopes equal the secant, so the Hermite basis
    /// reproduces the linear function exactly.  Midpoint of [1.0, 2.0] with
    /// ys=[0.0, 1.0] and slopes=[1.0, 1.0] must give exactly 0.5.
    #[test]
    fn test_pchip_matches_hermite() {
        let xs = vec![1.0_f64, 2.0];
        let ys = vec![0.0_f64, 1.0];
        let slopes = vec![1.0_f64, 1.0];
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1.5_f64]))]).into_series();
        let kw = CurveEvalKwargs {
            method: "pchip".into(),
            xs: Some(xs),
            ys: Some(ys),
            slopes: Some(slopes),
            extrapolation: Some("flat".into()),
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        };
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.list().unwrap().get_as_series(0).unwrap();
        assert!(
            (v.f64().unwrap().get(0).unwrap() - 0.5).abs() < 1e-12,
            "pchip straight-line midpoint: expected 0.5, got {}",
            v.f64().unwrap().get(0).unwrap()
        );
    }

    /// Svensson short-rate limit: at t→0 with b2=b3=0 the loadings are both 1
    /// and 0 respectively, so spot rate = exp(b0 + b1) - 1.
    #[test]
    fn test_svensson_short_rate_limit() {
        let kw = CurveEvalKwargs {
            method: "svensson".into(),
            b0: Some(0.04),
            b1: Some(-0.01),
            b2: Some(0.0),
            b3: Some(0.0),
            tau1: Some(1.5),
            tau2: Some(10.0),
            xs: None,
            ys: None,
            slopes: None,
            extrapolation: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        };
        let t =
            ListChunked::from_iter([Some(Series::new("".into(), vec![1e-9_f64]))]).into_series();
        let v = curve_eval(&[t], &kw)
            .unwrap()
            .list()
            .unwrap()
            .get_as_series(0)
            .unwrap();
        let got = v.f64().unwrap().get(0).unwrap();
        // At t→0: cc = b0 + b1 = 0.03; annually-compounded = exp(0.03) - 1
        assert!(
            (got - (0.03_f64.exp() - 1.0)).abs() < 1e-6,
            "svensson short-rate limit: got {got:.10}, expected {:.10}",
            0.03_f64.exp() - 1.0
        );
    }

    /// Integer (Int64) scalar column is cast to Float64 and routed through the
    /// numeric arm; output is a plain Float64 series.
    #[test]
    fn test_int64_scalar_input_casts() {
        let t = Series::new("".into(), vec![1_i64, 5, 10]);
        let kw = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]);
        let out = curve_eval(&[t], &kw).unwrap();
        let v = out.f64().unwrap();
        assert!((v.get(0).unwrap() - 0.03).abs() < 1e-12);
        assert!((v.get(2).unwrap() - 0.05).abs() < 1e-12);
    }

    /// Integer (Int64) list column is cast to Float64 inside the List arm.
    #[test]
    fn test_int64_list_input_casts() {
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![1_i64, 5, 10]))])
            .into_series();
        let kw = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]);
        let out = curve_eval(&[t], &kw).unwrap();
        let inner = out.list().unwrap().get_as_series(0).unwrap();
        let v = inner.f64().unwrap();
        assert!((v.get(1).unwrap() - 0.04).abs() < 1e-12);
    }

    /// Smith-Wilson oracle test against the lifelib worked example.
    ///
    /// U=[1,2,4,5,6,7], R=[.01,.02,.03,.032,.035,.04], UFR=0.04, alpha=0.15.
    /// zeta and omega are vendored constants precomputed from the Python
    /// ``solve_zeta`` implementation (MIT, (c) 2022 lifelib Developers).
    /// At t=3 the expected annual spot rate is 0.0264236322 to 9 d.p.
    #[test]
    fn test_smith_wilson_lifelib() {
        let u = vec![1.0_f64, 2.0, 4.0, 5.0, 6.0, 7.0];
        let zeta = vec![
            15.431915738208142_f64,
            -5.1725350404740285,
            -6.185724520443802,
            -2.2092015968509995,
            19.61339154504473,
            -13.063021960583592,
        ];
        let omega = 0.03922071315328133_f64;
        let alpha = 0.15_f64;
        let kw = CurveEvalKwargs {
            method: "smith_wilson".into(),
            u: Some(u),
            zeta: Some(zeta),
            omega: Some(omega),
            alpha: Some(alpha),
            xs: None,
            ys: None,
            slopes: None,
            extrapolation: None,
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
        };
        let t = ListChunked::from_iter([Some(Series::new("".into(), vec![3.0_f64]))]).into_series();
        let v = curve_eval(&[t], &kw)
            .unwrap()
            .list()
            .unwrap()
            .get_as_series(0)
            .unwrap();
        assert!((v.f64().unwrap().get(0).unwrap() - 0.0264236322).abs() < 1e-9);
    }

    /// Scalar (non-list) `Float64` input takes the native scalar path and yields
    /// a plain `Float64` series (NOT a list), one rate per row.
    #[test]
    fn test_scalar_float64_input() {
        // xs=[1, 5, 10], ys=[0.03, 0.04, 0.05]:
        //   t=0.5  → below xs[0]   → flat 0.03
        //   t=7.5  → midway 5..10  → 0.045
        //   t=11.0 → above xs[last]→ flat 0.05
        let t = Series::new("".into(), vec![0.5_f64, 7.5, 11.0]);
        let kw = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]);

        let out = curve_eval(&[t], &kw).unwrap();

        // Output must be a flat Float64 series, not a List.
        assert_eq!(
            out.dtype(),
            &DataType::Float64,
            "scalar input → Float64 out"
        );

        let v = out.f64().unwrap();
        assert!((v.get(0).unwrap() - 0.03).abs() < 1e-12, "t=0.5");
        assert!((v.get(1).unwrap() - 0.045).abs() < 1e-12, "t=7.5");
        assert!((v.get(2).unwrap() - 0.05).abs() < 1e-12, "t=11.0");
    }

    // -----------------------------------------------------------------------
    // Out-of-domain / non-finite contract (GSP-116)
    //
    // The Rust kernel must mirror the Python eager helpers exactly: a single
    // sentinel (`f64::NAN`) on every path. See `eval_one` for the predicate.
    // -----------------------------------------------------------------------

    /// Build `CurveEvalKwargs` for `log_linear` from (tenor, rate) knots.
    fn log_linear_kwargs(xs: Vec<f64>, rates: Vec<f64>) -> CurveEvalKwargs {
        let ys: Vec<f64> = xs
            .iter()
            .zip(rates.iter())
            .map(|(u, r)| -u * (1.0 + r).ln())
            .collect();
        CurveEvalKwargs {
            method: "log_linear".into(),
            xs: Some(xs),
            ys: Some(ys),
            slopes: None,
            extrapolation: Some("flat".into()),
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        }
    }

    /// Build `CurveEvalKwargs` for `pchip` (slopes equal to the secant -> linear).
    fn pchip_kwargs(xs: Vec<f64>, ys: Vec<f64>, slopes: Vec<f64>) -> CurveEvalKwargs {
        CurveEvalKwargs {
            method: "pchip".into(),
            xs: Some(xs),
            ys: Some(ys),
            slopes: Some(slopes),
            extrapolation: Some("flat".into()),
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        }
    }

    /// Build `CurveEvalKwargs` for `svensson`.
    fn svensson_kwargs() -> CurveEvalKwargs {
        CurveEvalKwargs {
            method: "svensson".into(),
            b0: Some(0.040),
            b1: Some(-0.010),
            b2: Some(0.005),
            b3: Some(0.002),
            tau1: Some(1.5),
            tau2: Some(10.0),
            xs: None,
            ys: None,
            slopes: None,
            extrapolation: None,
            u: None,
            zeta: None,
            omega: None,
            alpha: None,
        }
    }

    /// Build `CurveEvalKwargs` for `smith_wilson` (lifelib vendored constants).
    fn smith_wilson_kwargs() -> CurveEvalKwargs {
        CurveEvalKwargs {
            method: "smith_wilson".into(),
            u: Some(vec![1.0, 2.0, 4.0, 5.0, 6.0, 7.0]),
            zeta: Some(vec![
                15.431915738208142,
                -5.1725350404740285,
                -6.185724520443802,
                -2.2092015968509995,
                19.61339154504473,
                -13.063021960583592,
            ]),
            omega: Some(0.03922071315328133),
            alpha: Some(0.15),
            xs: None,
            ys: None,
            slopes: None,
            extrapolation: None,
            b0: None,
            b1: None,
            b2: None,
            b3: None,
            tau1: None,
            tau2: None,
        }
    }

    /// One representative kwargs per method, for the all-methods sweeps.
    fn all_method_kwargs() -> Vec<CurveEvalKwargs> {
        vec![
            lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]),
            log_linear_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]),
            pchip_kwargs(vec![1.0, 2.0], vec![0.0, 1.0], vec![1.0, 1.0]),
            svensson_kwargs(),
            smith_wilson_kwargs(),
        ]
    }

    /// Non-finite `t` (NaN, +inf, -inf) → `NAN` for every method, via `eval_one`.
    #[test]
    fn test_eval_one_non_finite_t_is_nan_all_methods() {
        for kw in all_method_kwargs() {
            for &t in &[f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
                let got = eval_one(t, &kw).unwrap();
                assert!(
                    got.is_nan(),
                    "method {} at t={t} should be NaN, got {got}",
                    kw.method
                );
            }
        }
    }

    /// `t <= 0` → `NAN` for `log_linear` and `smith_wilson` only.
    #[test]
    fn test_eval_one_nonpositive_t_is_nan_for_log_linear_and_smith_wilson() {
        let ll = log_linear_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]);
        let sw = smith_wilson_kwargs();
        for kw in [&ll, &sw] {
            for &t in &[0.0_f64, -1.0] {
                let got = eval_one(t, kw).unwrap();
                assert!(
                    got.is_nan(),
                    "method {} at t={t} should be NaN, got {got}",
                    kw.method
                );
            }
        }
    }

    /// Regression: `linear` and `pchip` at finite `t = 0` still return `ys[0]`
    /// (flat extrapolation below the first knot), NOT NaN.
    #[test]
    fn test_eval_one_linear_and_pchip_t_zero_returns_first_knot() {
        // linear: ys[0] = 0.03
        let lin = lin_kwargs(vec![1.0, 5.0, 10.0], vec![0.03, 0.04, 0.05]);
        let got_lin = eval_one(0.0, &lin).unwrap();
        assert!(
            (got_lin - 0.03).abs() < 1e-12,
            "linear at t=0 should be ys[0]=0.03, got {got_lin}"
        );

        // pchip: ys[0] = 0.01
        let pc = pchip_kwargs(vec![1.0, 2.0], vec![0.01, 0.02], vec![0.01, 0.01]);
        let got_pc = eval_one(0.0, &pc).unwrap();
        assert!(
            (got_pc - 0.01).abs() < 1e-12,
            "pchip at t=0 should be ys[0]=0.01, got {got_pc}"
        );
    }

    /// `eval_linear` / `eval_hermite` return `NAN` for non-finite `t` rather
    /// than panicking (their own contract, exercised directly).
    #[test]
    fn test_eval_linear_and_hermite_non_finite_t_is_nan() {
        let xs = [1.0_f64, 5.0, 10.0];
        let ys = [0.03_f64, 0.04, 0.05];
        let m = [0.0_f64, 0.0, 0.0];
        for &t in &[f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert!(eval_linear(t, &xs, &ys).is_nan(), "eval_linear t={t}");
            assert!(eval_hermite(t, &xs, &ys, &m).is_nan(), "eval_hermite t={t}");
        }
    }
}
