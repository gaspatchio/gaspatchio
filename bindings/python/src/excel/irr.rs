#![allow(clippy::unused_unit)]
use gaspatchio_core_lib::excel::irr::irr_output_type as core_irr_output_type;
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn irr_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    core_irr_output_type(input_fields)
}

#[polars_expr(output_type_func = irr_output_type)]
pub fn irr(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::IrrKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::irr(inputs, &kwargs)
}

