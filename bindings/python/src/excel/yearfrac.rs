#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

#[polars_expr(output_type_func = same_output_type)]
pub fn yearfrac(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::YearFracKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::yearfrac(inputs, &kwargs)
}
