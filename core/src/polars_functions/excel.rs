#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct YearFracKwargs {
    pub basis: String,
}

/// Calculates the year fraction between two dates based on the specified basis.
///
/// # Errors
/// Returns an error if an unsupported basis is provided or if series processing fails.
pub fn year_frac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    let start_date_series = &inputs[0];

    let basis = kwargs.basis.as_str();

    match basis {
        "act/360" | "act/365" => {
            // Stub implementation: return a series of 1.0 with same length as input
            let len = start_date_series.len();
            let year_fractions = vec![1.0f64; len];
            Ok(Series::new("year_frac".into(), year_fractions))
        }
        _ => Err(PolarsError::ComputeError(
            format!("Invalid basis '{basis}'. Supported bases: act/360, act/365").into(),
        )),
    }
}
