#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn yearfrac_output_type(_input_fields: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new("year_frac".into(), DataType::Float64))
}

#[polars_expr(output_type_func = yearfrac_output_type)]
pub fn yearfrac(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::YearFracKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::yearfrac(inputs, &kwargs)
}
