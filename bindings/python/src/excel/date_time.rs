#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

#[polars_expr(output_type_func = same_output_type)]
pub fn year_frac(inputs: &[Series], kwargs: &YearFracKwargs) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::year_frac(inputs, &kwargs)
}
